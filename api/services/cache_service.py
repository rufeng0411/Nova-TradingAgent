from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
from hashlib import md5
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _safe_redis_key(namespace: str, key: str) -> str:
    if len(key) <= 240:
        return f"{namespace}:{key}"
    digest = md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"{namespace}:{digest}"


@dataclass
class _Entry:
    expires_at: float
    value: Any


class TieredCache:
    """In-process L1 + optional Redis L2 cache with single-flight support."""

    def __init__(self, namespace: str, *, enabled: bool = True):
        self.namespace = namespace
        self.enabled = enabled
        self._l1: Dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._inflight: Dict[str, Future[Any]] = {}
        self._ainflight: Dict[str, asyncio.Future[Any]] = {}
        self._alock = asyncio.Lock()
        self._redis = self._build_redis_client()

    @staticmethod
    def _build_redis_client():
        if not _env_bool("TA_REDIS_CACHE_ENABLED", False):
            return None
        try:
            import redis

            url = (os.getenv("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()
            timeout = _env_float("TA_REDIS_TIMEOUT_SEC", 0.35)
            client = redis.Redis.from_url(
                url,
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
                decode_responses=False,
            )
            client.ping()
            logger.info("[tiered-cache] redis enabled namespace=%s url=%s", "global", url)
            return client
        except Exception as exc:
            logger.warning("[tiered-cache] redis disabled, fallback L1 only: %s", exc)
            return None

    def _l1_get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        now = time.time()
        with self._lock:
            entry = self._l1.get(key)
            if entry and entry.expires_at > now:
                return deepcopy(entry.value)
            if entry:
                self._l1.pop(key, None)
        return None

    def _l1_set(self, key: str, value: Any, ttl_sec: float) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._l1[key] = _Entry(expires_at=time.time() + max(0.1, ttl_sec), value=deepcopy(value))

    def _l2_get(self, key: str) -> Any | None:
        if not self.enabled or self._redis is None:
            return None
        try:
            redis_key = _safe_redis_key(self.namespace, key)
            raw = self._redis.get(redis_key)
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _l2_set(self, key: str, value: Any, ttl_sec: float) -> None:
        if not self.enabled or self._redis is None:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
            redis_key = _safe_redis_key(self.namespace, key)
            self._redis.setex(redis_key, max(1, int(ttl_sec)), payload)
        except Exception:
            return

    def get(self, key: str) -> Any | None:
        hit = self._l1_get(key)
        if hit is not None:
            return hit
        hit = self._l2_get(key)
        if hit is not None:
            self._l1_set(key, hit, ttl_sec=10.0)
        return hit

    def set(self, key: str, value: Any, ttl_sec: float) -> None:
        self._l1_set(key, value, ttl_sec)
        self._l2_set(key, value, ttl_sec)

    def get_or_set(self, key: str, ttl_sec: float, loader: Callable[[], T]) -> T:
        hit = self.get(key)
        if hit is not None:
            return hit
        with self._lock:
            fut = self._inflight.get(key)
            if fut is None:
                fut = Future()
                self._inflight[key] = fut
                is_owner = True
            else:
                is_owner = False

        if not is_owner:
            return fut.result()

        try:
            value = loader()
            self.set(key, value, ttl_sec)
            fut.set_result(value)
            return value
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    async def get_or_set_async(self, key: str, ttl_sec: float, loader: Callable[[], "asyncio.Future[T] | T"]) -> T:
        hit = self.get(key)
        if hit is not None:
            return hit
        async with self._alock:
            fut = self._ainflight.get(key)
            if fut is None:
                fut = asyncio.get_running_loop().create_future()
                self._ainflight[key] = fut
                is_owner = True
            else:
                is_owner = False

        if not is_owner:
            return await fut

        try:
            res = loader()
            if asyncio.iscoroutine(res):
                value = await res
            else:
                value = res
            self.set(key, value, ttl_sec)
            fut.set_result(value)
            return value
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            async with self._alock:
                self._ainflight.pop(key, None)


_GLOBAL_CACHES: Dict[str, TieredCache] = {}
_GLOBAL_CACHE_LOCK = threading.Lock()


def get_tiered_cache(namespace: str, *, enabled: bool = True) -> TieredCache:
    with _GLOBAL_CACHE_LOCK:
        cache = _GLOBAL_CACHES.get(namespace)
        if cache is None:
            cache = TieredCache(namespace=namespace, enabled=enabled)
            _GLOBAL_CACHES[namespace] = cache
        return cache
