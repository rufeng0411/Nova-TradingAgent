"""Persistent analysis job rows + append-only job event log for SSE replay and resume."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from api.database import AnalysisJobDB, JobEventDB

logger = logging.getLogger(__name__)

LEASE_PENDING_SEC = int(os.getenv("TA_ANALYSIS_LEASE_PENDING_SEC", "3600"))
LEASE_RUNNING_SEC = int(os.getenv("TA_ANALYSIS_LEASE_RUNNING_SEC", "900"))
RECLAIM_GRACE_SEC = int(os.getenv("TA_ANALYSIS_RECLAIM_GRACE_SEC", "120"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def upsert_job_row(
    db: Session,
    job_id: str,
    *,
    user_id: Optional[str],
    symbol: Optional[str],
    trade_date: Optional[str],
    status: str = "pending",
    request_payload: Optional[Dict[str, Any]] = None,
    request_source: Optional[str] = None,
    dry_run: bool = False,
) -> AnalysisJobDB:
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    now = _utcnow()
    lease_until = now + timedelta(seconds=LEASE_PENDING_SEC)
    if row is None:
        row = AnalysisJobDB(
            id=job_id,
            user_id=user_id,
            symbol=symbol,
            trade_date=trade_date,
            status=status,
            request_payload=request_payload,
            request_source=request_source,
            dry_run=dry_run,
            lease_until=lease_until,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.user_id = user_id or row.user_id
        row.symbol = symbol or row.symbol
        row.trade_date = trade_date or row.trade_date
        row.status = status
        if request_payload is not None:
            row.request_payload = request_payload
        if request_source is not None:
            row.request_source = request_source
        row.dry_run = dry_run
        row.lease_until = lease_until
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def merge_request_payload(
    db: Session,
    job_id: str,
    payload: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
    symbol: Optional[str] = None,
    trade_date: Optional[str] = None,
    request_source: Optional[str] = None,
    dry_run: Optional[bool] = None,
) -> None:
    """Merge full AnalyzeRequest dict into the durable row (upsert)."""
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    now = _utcnow()
    if row is None:
        row = AnalysisJobDB(
            id=job_id,
            user_id=user_id,
            symbol=symbol,
            trade_date=trade_date,
            status="pending",
            request_payload=dict(payload),
            request_source=request_source,
            dry_run=bool(dry_run),
            lease_until=now + timedelta(seconds=LEASE_PENDING_SEC),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.request_payload = dict(payload)
        if user_id is not None:
            row.user_id = user_id
        if symbol is not None:
            row.symbol = symbol
        if trade_date is not None:
            row.trade_date = trade_date
        if request_source is not None:
            row.request_source = request_source
        if dry_run is not None:
            row.dry_run = dry_run
        row.updated_at = now
        row.lease_until = now + timedelta(
            seconds=LEASE_RUNNING_SEC if row.status in ("running", "resuming") else LEASE_PENDING_SEC
        )
    db.commit()


def persist_store_fields(db: Session, job_id: str, fields: Dict[str, Any]) -> None:
    """Persist a subset of in-memory JobStore fields onto AnalysisJobDB."""
    if not fields:
        return
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    if row is None:
        return
    now = _utcnow()
    if "status" in fields and fields["status"] is not None:
        row.status = str(fields["status"])
    if "error" in fields:
        row.error = fields["error"]
    if "decision" in fields:
        row.decision = fields["decision"]
    if "symbol" in fields and fields["symbol"]:
        row.symbol = str(fields["symbol"])
    if "trade_date" in fields and fields["trade_date"]:
        row.trade_date = str(fields["trade_date"])
    if "user_id" in fields and fields["user_id"]:
        row.user_id = str(fields["user_id"])
    row.updated_at = now
    db.commit()


def patch_resume_state(db: Session, job_id: str, patch: Dict[str, Any]) -> None:
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    if row is None:
        return
    base = dict(row.resume_state or {})
    base.update(patch)
    row.resume_state = base
    row.updated_at = _utcnow()
    db.commit()


def renew_lease(db: Session, job_id: str, owner: str, seconds: Optional[int] = None) -> None:
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    if row is None:
        return
    sec = seconds if seconds is not None else LEASE_RUNNING_SEC
    row.lease_owner = owner
    row.lease_until = _utcnow() + timedelta(seconds=sec)
    row.updated_at = _utcnow()
    db.commit()


def release_lease(db: Session, job_id: str) -> None:
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    if row is None:
        return
    row.lease_until = None
    row.lease_owner = None
    row.updated_at = _utcnow()
    db.commit()


def try_claim_for_resume(db: Session, job_id: str, owner: str) -> bool:
    """Atomically claim a stale job for resume (single winner per expiry window)."""
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    if row is None:
        return False
    now = _utcnow()
    if row.status not in ("pending", "running", "resuming"):
        return False
    lu = _as_aware_utc(row.lease_until)
    if lu and lu > now and row.lease_owner and row.lease_owner != owner:
        return False
    row.status = "resuming"
    row.lease_owner = owner
    row.lease_until = now + timedelta(seconds=LEASE_RUNNING_SEC)
    row.attempt_count = int(row.attempt_count or 0) + 1
    row.updated_at = now
    db.commit()
    return True


def append_event(db: Session, job_id: str, event: str, data: Dict[str, Any]) -> int:
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).with_for_update().first()
    now = _utcnow()
    if row is None:
        row = AnalysisJobDB(
            id=job_id,
            user_id=None,
            status="pending",
            lease_until=now + timedelta(seconds=LEASE_PENDING_SEC),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()

    next_seq = int(row.last_event_seq or 0) + 1
    row.last_event_seq = next_seq
    row.updated_at = now
    db.add(
        JobEventDB(
            job_id=job_id,
            seq=next_seq,
            event=event,
            payload=dict(data),
            created_at=now,
        )
    )
    db.commit()
    return next_seq


def fetch_latest_event_payload(
    db: Session,
    job_id: str,
    event: str,
) -> Optional[Dict[str, Any]]:
    """Return the JSON payload for the latest job_events row matching ``event`` (highest seq)."""
    row = (
        db.query(JobEventDB)
        .filter(JobEventDB.job_id == job_id, JobEventDB.event == event)
        .order_by(JobEventDB.seq.desc())
        .first()
    )
    if row is None or row.payload is None:
        return None
    return dict(row.payload)


def fetch_events_after(
    job_id: str,
    after_seq: int,
    limit: int = 5000,
    db: Optional[Session] = None,
) -> List[Tuple[int, str, Dict[str, Any]]]:
    def _run(sess: Session) -> List[Tuple[int, str, Dict[str, Any]]]:
        q = (
            sess.query(JobEventDB)
            .filter(JobEventDB.job_id == job_id, JobEventDB.seq > int(after_seq))
            .order_by(JobEventDB.seq.asc())
            .limit(limit)
        )
        return [(r.seq, r.event, dict(r.payload or {})) for r in q.all()]

    if db is not None:
        return _run(db)
    from api.database import get_db_ctx

    with get_db_ctx() as sess:
        return _run(sess)


def get_job_row(db: Session, job_id: str) -> Optional[AnalysisJobDB]:
    return db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()


def list_jobs_to_reclaim(db: Session) -> List[str]:
    """Jobs that lost their worker (lease expired or stuck pending)."""
    now = _utcnow()
    grace = timedelta(seconds=RECLAIM_GRACE_SEC)
    q = (
        db.query(AnalysisJobDB)
        .filter(
            AnalysisJobDB.status.in_(("pending", "running", "resuming")),
            AnalysisJobDB.request_payload.isnot(None),
        )
        .all()
    )
    out: List[str] = []
    for row in q:
        updated = _as_aware_utc(row.updated_at) or _as_aware_utc(row.created_at) or now
        lu = _as_aware_utc(row.lease_until)
        lease_ok = bool(lu and lu > now)
        if row.status == "pending":
            if not lease_ok and now - updated > grace:
                out.append(row.id)
            continue
        # running / resuming
        if not lease_ok:
            out.append(row.id)
    return out


def row_blocks_user_task_queue_dispatch(row: AnalysisJobDB, *, now: Optional[datetime] = None) -> bool:
    """Return True if this row should prevent dequeuing the next per-user queued task.

    Mirrors the lease / grace rules in :func:`list_jobs_to_reclaim`: rows that are already
    reclaim-eligible (wedged worker or stale pending) do *not* block, so they cannot freeze
    the user task queue indefinitely.
    """
    now = now or _utcnow()
    status = str(row.status or "")
    if status not in ("pending", "running", "resuming"):
        return False
    grace = timedelta(seconds=RECLAIM_GRACE_SEC)
    updated = _as_aware_utc(row.updated_at) or _as_aware_utc(row.created_at) or now
    lu = _as_aware_utc(row.lease_until)
    lease_ok = bool(lu and lu > now)
    if status == "pending":
        reclaim_eligible = (not lease_ok) and (now - updated > grace)
        return not reclaim_eligible
    reclaim_eligible = not lease_ok
    return not reclaim_eligible


def memory_job_from_row(row: AnalysisJobDB) -> Dict[str, Any]:
    """Shape compatible with JobStore.get_job() consumers."""
    created = row.created_at.isoformat() if row.created_at else ""
    return {
        "job_id": row.id,
        "user_id": row.user_id,
        "status": row.status,
        "symbol": row.symbol,
        "trade_date": row.trade_date,
        "error": row.error,
        "decision": row.decision,
        "created_at": created,
        "started_at": None,
        "finished_at": None,
        "result": None,
        "resume_state": row.resume_state,
        "attempt_count": row.attempt_count,
        "last_event_seq": row.last_event_seq,
        "request_source": row.request_source,
    }
