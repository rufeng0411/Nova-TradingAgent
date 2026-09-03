"""In-process broadcast for admin SSE (single-worker deployments)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_subscribers: List[asyncio.Queue] = []
_lock = asyncio.Lock()
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


async def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    async with _lock:
        _subscribers.append(q)
    return q


async def unsubscribe(q: asyncio.Queue) -> None:
    async with _lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


async def broadcast_dict(event: Dict[str, Any]) -> None:
    async with _lock:
        targets = list(_subscribers)
    for q in targets:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(event)
            except Exception:
                pass
        except Exception as e:
            logger.debug("admin broadcast drop: %s", e)


def publish_admin_event(event: Dict[str, Any]) -> None:
    """Fire-and-forget from sync or async contexts."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_dict(event))
        return
    except RuntimeError:
        pass
    if _main_loop is not None and _main_loop.is_running():

        def _schedule() -> None:
            asyncio.create_task(broadcast_dict(event))

        try:
            _main_loop.call_soon_threadsafe(_schedule)
        except Exception as e:
            logger.debug("admin publish threadsafe failed: %s", e)
