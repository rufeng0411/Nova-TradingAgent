"""Operational admin signals (DB + optional SSE fan-out)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from api.database import AdminSignalDB, get_db_ctx

logger = logging.getLogger(__name__)


def insert_signal(
    db: Session,
    *,
    type: str,
    severity: str = "info",
    payload: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> AdminSignalDB:
    row = AdminSignalDB(
        id=str(uuid4()),
        type=type,
        severity=severity or "info",
        payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        from api.services import admin_events_service

        admin_events_service.publish_admin_event(
            {
                "kind": "admin_signal",
                "id": row.id,
                "type": row.type,
                "severity": row.severity,
                "user_id": row.user_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    except Exception as e:
        logger.debug("signal fan-out: %s", e)
    return row


def insert_signal_safe(
    *,
    type: str,
    severity: str = "info",
    payload: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> None:
    try:
        with get_db_ctx() as db:
            insert_signal(db, type=type, severity=severity, payload=payload, user_id=user_id)
    except Exception as e:
        logger.warning("insert_signal_safe failed: %s", e)


def list_signals(
    db: Session,
    *,
    severity: Optional[str] = None,
    type_prefix: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[AdminSignalDB], int]:
    q = db.query(AdminSignalDB)
    if severity:
        q = q.filter(AdminSignalDB.severity == severity)
    if type_prefix:
        q = q.filter(AdminSignalDB.type.ilike(f"{type_prefix}%"))
    if from_ts:
        q = q.filter(AdminSignalDB.created_at >= from_ts)
    if to_ts:
        q = q.filter(AdminSignalDB.created_at <= to_ts)
    total = q.count()
    rows = (
        q.order_by(AdminSignalDB.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total
