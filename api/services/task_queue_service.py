"""Per-user heavy task queue service."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.database import AnalysisJobDB, UserTaskQueueDB
from api.services import analysis_job_service

QUEUE_STATUS_QUEUED = "queued"
QUEUE_STATUS_PAUSED = "paused"
PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"
ACTIVE_RUNNING_STATUSES = ("pending", "running", "resuming")
_schedule_callback: Optional[Callable[[str], None]] = None


def is_queue_enabled() -> bool:
    raw = (os.getenv("TA_USER_TASK_QUEUE_ENABLED", "1") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def max_queue_size() -> int:
    raw = (os.getenv("TA_USER_TASK_QUEUE_MAX_SIZE", "5") or "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 5
    return max(1, value)


def register_schedule_callback(callback: Callable[[str], None]) -> None:
    global _schedule_callback
    _schedule_callback = callback


def request_schedule(user_id: Optional[str]) -> None:
    if _schedule_callback is None:
        return
    normalized = _normalize_user_id(user_id)
    if not normalized:
        return
    _schedule_callback(normalized)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_user_id(user_id: Optional[str]) -> str:
    return str(user_id or "").strip()


def _normalize_job_id(job_id: str) -> str:
    return str(job_id or "").strip()


def _next_sort_order(db: Session, user_id: str) -> int:
    max_order = (
        db.query(func.max(UserTaskQueueDB.sort_order))
        .filter(UserTaskQueueDB.user_id == user_id)
        .scalar()
    )
    return int(max_order) + 1 if max_order is not None else 0


def _shift_all_queued_back(db: Session, user_id: str) -> None:
    rows = (
        db.query(UserTaskQueueDB)
        .filter(
            UserTaskQueueDB.user_id == user_id,
            UserTaskQueueDB.queue_status.in_((QUEUE_STATUS_QUEUED, QUEUE_STATUS_PAUSED)),
        )
        .all()
    )
    now = _now()
    for row in rows:
        row.sort_order = int(row.sort_order or 0) + 1
        row.updated_at = now


def has_active_running_job(db: Session, user_id: str, *, exclude_job_id: Optional[str] = None) -> bool:
    q = db.query(AnalysisJobDB).filter(
        AnalysisJobDB.user_id == user_id,
        AnalysisJobDB.status.in_(ACTIVE_RUNNING_STATUSES),
    )
    if exclude_job_id:
        q = q.filter(AnalysisJobDB.id != exclude_job_id)
    return q.first() is not None


def has_pending_queue_items(db: Session, user_id: str) -> bool:
    return (
        db.query(UserTaskQueueDB)
        .filter(
            UserTaskQueueDB.user_id == user_id,
            UserTaskQueueDB.queue_status.in_((QUEUE_STATUS_QUEUED, QUEUE_STATUS_PAUSED)),
        )
        .first()
        is not None
    )


def queue_size(db: Session, user_id: str) -> int:
    return int(
        db.query(UserTaskQueueDB)
        .filter(
            UserTaskQueueDB.user_id == user_id,
            UserTaskQueueDB.queue_status.in_((QUEUE_STATUS_QUEUED, QUEUE_STATUS_PAUSED)),
        )
        .count()
    )


def enqueue_job(
    db: Session,
    *,
    user_id: str,
    job_id: str,
    task_kind: str,
    title: Optional[str],
    description: Optional[str],
    symbol: Optional[str],
    trade_date: Optional[str],
    queue_status: str = QUEUE_STATUS_QUEUED,
    priority: str = PRIORITY_NORMAL,
) -> UserTaskQueueDB:
    now = _now()
    row = (
        db.query(UserTaskQueueDB)
        .filter(
            UserTaskQueueDB.user_id == user_id,
            UserTaskQueueDB.job_id == job_id,
        )
        .first()
    )
    if row is None:
        sort_order = 0 if priority == PRIORITY_HIGH else _next_sort_order(db, user_id)
        if priority == PRIORITY_HIGH:
            _shift_all_queued_back(db, user_id)
        row = UserTaskQueueDB(
            id=str(uuid4()),
            user_id=user_id,
            job_id=job_id,
            task_kind=task_kind,
            queue_status=queue_status,
            sort_order=sort_order,
            title=title,
            description=description,
            symbol=symbol,
            trade_date=trade_date,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.queue_status = queue_status
        if priority == PRIORITY_HIGH:
            _shift_all_queued_back(db, user_id)
            row.sort_order = 0
        row.task_kind = task_kind
        row.title = title
        row.description = description
        row.symbol = symbol
        row.trade_date = trade_date
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def waiting_ahead_count(db: Session, user_id: str, job_id: str) -> int:
    row = (
        db.query(UserTaskQueueDB)
        .filter(UserTaskQueueDB.user_id == user_id, UserTaskQueueDB.job_id == job_id)
        .first()
    )
    if not row:
        return 0
    return int(
        db.query(UserTaskQueueDB)
        .filter(
            UserTaskQueueDB.user_id == user_id,
            UserTaskQueueDB.queue_status == QUEUE_STATUS_QUEUED,
            UserTaskQueueDB.sort_order < row.sort_order,
        )
        .count()
    )


def set_analysis_job_status(
    db: Session,
    job_id: str,
    *,
    status: str,
    error: Optional[str] = None,
) -> bool:
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    if row is None:
        return False
    row.status = status
    if error is not None:
        row.error = error
    row.updated_at = _now()
    db.commit()
    return True


def dequeue_next_job(db: Session, user_id: str) -> Optional[Dict[str, Any]]:
    user_id = _normalize_user_id(user_id)
    if not user_id:
        return None
    blocking_rows = (
        db.query(AnalysisJobDB)
        .filter(
            AnalysisJobDB.user_id == user_id,
            AnalysisJobDB.status.in_(ACTIVE_RUNNING_STATUSES),
        )
        .all()
    )
    if any(analysis_job_service.row_blocks_user_task_queue_dispatch(r) for r in blocking_rows):
        return None

    row = (
        db.query(UserTaskQueueDB)
        .filter(
            UserTaskQueueDB.user_id == user_id,
            UserTaskQueueDB.queue_status == QUEUE_STATUS_QUEUED,
        )
        .order_by(UserTaskQueueDB.sort_order.asc(), UserTaskQueueDB.created_at.asc())
        .first()
    )
    if row is None:
        return None

    payload = {
        "job_id": row.job_id,
        "task_kind": row.task_kind,
        "symbol": row.symbol,
        "trade_date": row.trade_date,
        "title": row.title,
        "description": row.description,
    }

    db.delete(row)
    db.flush()
    _compact_user_sort_order(db, user_id)
    db.commit()
    return payload


def _compact_user_sort_order(db: Session, user_id: str) -> None:
    rows = (
        db.query(UserTaskQueueDB)
        .filter(UserTaskQueueDB.user_id == user_id)
        .order_by(UserTaskQueueDB.sort_order.asc(), UserTaskQueueDB.created_at.asc())
        .all()
    )
    now = _now()
    for idx, row in enumerate(rows):
        row.sort_order = idx
        row.updated_at = now


def list_user_queue_items(db: Session, user_id: str) -> List[UserTaskQueueDB]:
    return (
        db.query(UserTaskQueueDB)
        .filter(UserTaskQueueDB.user_id == user_id)
        .order_by(UserTaskQueueDB.sort_order.asc(), UserTaskQueueDB.created_at.asc())
        .all()
    )


def list_users_with_queued_tasks(db: Session) -> List[str]:
    rows = (
        db.query(UserTaskQueueDB.user_id)
        .filter(UserTaskQueueDB.queue_status == QUEUE_STATUS_QUEUED)
        .distinct()
        .all()
    )
    return [str(r[0]) for r in rows if r and r[0]]


def list_user_recent_jobs(db: Session, user_id: str, limit: int = 20) -> List[AnalysisJobDB]:
    return (
        db.query(AnalysisJobDB)
        .filter(AnalysisJobDB.user_id == user_id)
        .order_by(AnalysisJobDB.updated_at.desc(), AnalysisJobDB.created_at.desc())
        .limit(max(1, int(limit)))
        .all()
    )


def reorder_queue(db: Session, user_id: str, job_ids: List[str]) -> List[UserTaskQueueDB]:
    normalized_ids = [_normalize_job_id(x) for x in job_ids if _normalize_job_id(x)]
    rows = list_user_queue_items(db, user_id)
    existing_ids = [row.job_id for row in rows]
    if set(normalized_ids) != set(existing_ids):
        raise ValueError("reorder payload does not match queued items")
    row_map = {row.job_id: row for row in rows}
    now = _now()
    for idx, job_id in enumerate(normalized_ids):
        row = row_map[job_id]
        row.sort_order = idx
        row.updated_at = now
    db.commit()
    return list_user_queue_items(db, user_id)


def set_queue_status(db: Session, user_id: str, job_id: str, *, queue_status: str) -> Optional[UserTaskQueueDB]:
    row = (
        db.query(UserTaskQueueDB)
        .filter(UserTaskQueueDB.user_id == user_id, UserTaskQueueDB.job_id == job_id)
        .first()
    )
    if row is None:
        return None
    row.queue_status = queue_status
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def remove_queued_job(
    db: Session,
    *,
    user_id: str,
    job_id: str,
    cancel_error: str = "用户已取消排队任务",
) -> bool:
    row = (
        db.query(UserTaskQueueDB)
        .filter(UserTaskQueueDB.user_id == user_id, UserTaskQueueDB.job_id == job_id)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.flush()
    _compact_user_sort_order(db, user_id)

    job = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    if job is not None and job.status in ("queued", "paused", "pending"):
        job.status = "failed"
        job.error = cancel_error
        job.updated_at = _now()
    db.commit()
    return True
