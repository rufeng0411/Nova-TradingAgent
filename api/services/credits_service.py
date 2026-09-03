"""Credit / points accounting: reserve → commit or refund per analysis job."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from api.database import CreditTransactionDB, UsageRecordDB, UserDB

logger = logging.getLogger(__name__)

REF_ANALYSIS_JOB = "analysis_job"


class InsufficientCreditsError(Exception):
    pass


def _cost() -> int:
    return int(os.getenv("TA_COST_ANALYSIS", "10"))


def analysis_cost() -> int:
    return _cost()


def get_balance(db: Session, user_id: str) -> int:
    u = db.query(UserDB).filter(UserDB.id == user_id).first()
    return int(u.credits or 0) if u else 0


def _ensure_usage(db: Session, user_id: str, job_id: str) -> UsageRecordDB:
    r = db.query(UsageRecordDB).filter(UsageRecordDB.user_id == user_id, UsageRecordDB.task_id == job_id).first()
    if r:
        return r
    r = UsageRecordDB(
        id=str(uuid4()),
        user_id=user_id,
        task_id=job_id,
        report_id=None,
        credits_reserved=0,
        credits_consumed=0,
        tokens_prompt=0,
        tokens_completion=0,
        cost_cents_estimated=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(r)
    return r


def _already_reserved(db: Session, user_id: str, job_id: str) -> bool:
    return (
        db.query(CreditTransactionDB)
        .filter(
            CreditTransactionDB.user_id == user_id,
            CreditTransactionDB.ref_type == REF_ANALYSIS_JOB,
            CreditTransactionDB.ref_id == job_id,
            CreditTransactionDB.type == "reserve",
        )
        .first()
        is not None
    )


def reserve_for_analysis(db: Session, user_id: str, job_id: str, amount: Optional[int] = None) -> None:
    """Deduct credits immediately; idempotent per (user_id, job_id)."""
    amt = amount if amount is not None else _cost()
    if amt <= 0:
        return
    if _already_reserved(db, user_id, job_id):
        return
    u = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not u:
        raise InsufficientCreditsError("user not found")
    bal = int(u.credits or 0)
    if bal < amt:
        raise InsufficientCreditsError("insufficient credits")
    u.credits = bal - amt
    tx = CreditTransactionDB(
        id=str(uuid4()),
        user_id=user_id,
        delta=-amt,
        type="reserve",
        reason="analysis_reserve",
        ref_type=REF_ANALYSIS_JOB,
        ref_id=job_id,
        balance_after=u.credits,
        operator_id=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(tx)
    ur = _ensure_usage(db, user_id, job_id)
    ur.credits_reserved = int(ur.credits_reserved or 0) + amt
    db.commit()


def _has_commit(db: Session, user_id: str, job_id: str) -> bool:
    return (
        db.query(CreditTransactionDB)
        .filter(
            CreditTransactionDB.user_id == user_id,
            CreditTransactionDB.ref_type == REF_ANALYSIS_JOB,
            CreditTransactionDB.ref_id == job_id,
            CreditTransactionDB.type == "commit",
        )
        .first()
        is not None
    )


def commit_analysis(db: Session, user_id: str, job_id: str, amount: Optional[int] = None) -> None:
    """Mark analysis charge as final (increment consumed counter)."""
    amt = amount if amount is not None else _cost()
    if amt <= 0:
        return
    if _has_commit(db, user_id, job_id):
        return
    u = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not u:
        return
    u.total_credits_consumed = int(u.total_credits_consumed or 0) + amt
    tx = CreditTransactionDB(
        id=str(uuid4()),
        user_id=user_id,
        delta=0,
        type="commit",
        reason="analysis_commit",
        ref_type=REF_ANALYSIS_JOB,
        ref_id=job_id,
        balance_after=int(u.credits or 0),
        operator_id=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(tx)
    ur = db.query(UsageRecordDB).filter(UsageRecordDB.user_id == user_id, UsageRecordDB.task_id == job_id).first()
    if ur:
        ur.credits_consumed = int(ur.credits_consumed or 0) + amt
    db.commit()


def refund_analysis(db: Session, user_id: str, job_id: str, amount: Optional[int] = None) -> None:
    """Refund reserved credits if analysis failed (idempotent)."""
    amt = amount if amount is not None else _cost()
    if amt <= 0:
        return
    if _has_refund(db, user_id, job_id):
        return
    if not _already_reserved(db, user_id, job_id):
        return
    u = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not u:
        return
    u.credits = int(u.credits or 0) + amt
    tx = CreditTransactionDB(
        id=str(uuid4()),
        user_id=user_id,
        delta=amt,
        type="refund",
        reason="analysis_refund",
        ref_type=REF_ANALYSIS_JOB,
        ref_id=job_id,
        balance_after=u.credits,
        operator_id=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(tx)
    ur = db.query(UsageRecordDB).filter(UsageRecordDB.user_id == user_id, UsageRecordDB.task_id == job_id).first()
    if ur:
        ur.credits_reserved = max(0, int(ur.credits_reserved or 0) - amt)
    db.commit()
    from api.services import admin_signals_service

    admin_signals_service.insert_signal_safe(
        type="credits.analysis_refund",
        severity="info",
        payload={"job_id": job_id, "amount": amt},
        user_id=user_id,
    )


def _has_refund(db: Session, user_id: str, job_id: str) -> bool:
    return (
        db.query(CreditTransactionDB)
        .filter(
            CreditTransactionDB.user_id == user_id,
            CreditTransactionDB.ref_type == REF_ANALYSIS_JOB,
            CreditTransactionDB.ref_id == job_id,
            CreditTransactionDB.type == "refund",
        )
        .first()
        is not None
    )


def grant(
    db: Session,
    user_id: str,
    delta: int,
    reason: str,
    *,
    operator_id: Optional[str] = None,
    ref_type: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> int:
    """Add credits (positive delta). Returns new balance."""
    if delta == 0:
        return get_balance(db, user_id)
    u = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not u:
        raise ValueError("user not found")
    u.credits = int(u.credits or 0) + delta
    tx = CreditTransactionDB(
        id=str(uuid4()),
        user_id=user_id,
        delta=delta,
        type="grant" if delta > 0 else "adjust",
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
        balance_after=u.credits,
        operator_id=operator_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(tx)
    db.commit()
    return u.credits


def list_transactions(
    db: Session, user_id: str, *, skip: int = 0, limit: int = 50
) -> Tuple[List[CreditTransactionDB], int]:
    q = db.query(CreditTransactionDB).filter(CreditTransactionDB.user_id == user_id)
    total = q.count()
    rows = q.order_by(CreditTransactionDB.created_at.desc()).offset(skip).limit(limit).all()
    return rows, total
