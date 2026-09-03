"""Buffered HTTP access logs for admin observability."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from api.database import AccessLogDB, get_db_ctx

logger = logging.getLogger(__name__)

_buffer: List[Dict[str, Any]] = []
_lock = Lock()
_enabled = os.getenv("TA_ACCESS_LOG_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def enqueue(
    *,
    user_id: Optional[str],
    ip: Optional[str],
    method: str,
    path: str,
    status_code: int,
    latency_ms: int,
    user_agent: Optional[str],
) -> None:
    if not _enabled:
        return
    row = {
        "id": str(uuid4()),
        "user_id": user_id,
        "ip": ip,
        "method": method[:10] if method else None,
        "path": path[:500] if path else None,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "user_agent": (user_agent or "")[:500] or None,
        "created_at": datetime.now(timezone.utc),
    }
    with _lock:
        _buffer.append(row)
        flush_now = len(_buffer) >= 100
    if flush_now:
        flush_to_db()


def flush_to_db() -> None:
    with _lock:
        if not _buffer:
            return
        batch = _buffer[:]
        _buffer.clear()
    try:
        with get_db_ctx() as db:
            for row in batch:
                db.add(AccessLogDB(**row))
            db.commit()
    except Exception as e:
        logger.warning("access log flush failed: %s", e)


async def flush_loop() -> None:
    while True:
        await asyncio.sleep(30)
        flush_to_db()


def retention_cleanup_sync() -> None:
    days = int(os.getenv("TA_ACCESS_LOG_RETENTION_DAYS", "30"))
    if days <= 0:
        return
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with get_db_ctx() as db:
            db.execute(text("DELETE FROM access_logs WHERE created_at < :cutoff"), {"cutoff": cutoff})
            db.commit()
    except Exception as e:
        logger.warning("access log retention: %s", e)
