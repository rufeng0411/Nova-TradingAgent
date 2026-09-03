"""Billing helpers: plans, subscriptions, user balance projection."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from api.database import PlanDB, SubscriptionDB, UserDB


def get_plan_by_code(db: Session, code: str) -> Optional[PlanDB]:
    return db.query(PlanDB).filter(PlanDB.code == code.strip().lower()).first()


def user_plan_snapshot(db: Session, user: UserDB) -> Tuple[Optional[str], Optional[datetime], Optional[str]]:
    """Returns (plan_code, subscription_expires_at, subscription_status)."""
    sid = getattr(user, "current_subscription_id", None)
    if not sid:
        return None, None, None
    sub = db.query(SubscriptionDB).filter(SubscriptionDB.id == sid).first()
    if not sub:
        return None, None, None
    plan = db.query(PlanDB).filter(PlanDB.id == sub.plan_id).first()
    code = plan.code if plan else None
    return code, sub.expires_at, sub.status


def list_active_plans(db: Session) -> list[PlanDB]:
    return (
        db.query(PlanDB)
        .filter(PlanDB.is_active.is_(True))
        .order_by(PlanDB.sort_order.asc(), PlanDB.code.asc())
        .all()
    )


def plan_to_public(p: PlanDB) -> dict:
    feats: list = []
    if p.features_json:
        try:
            feats = json.loads(p.features_json)
        except json.JSONDecodeError:
            feats = []
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "price_cents": p.price_cents,
        "currency": p.currency,
        "period_days": p.period_days,
        "monthly_credits": p.monthly_credits,
        "features": feats,
        "is_active": p.is_active,
        "sort_order": p.sort_order,
    }


def create_pending_subscription(db: Session, user_id: str, plan_code: str) -> SubscriptionDB:
    plan = get_plan_by_code(db, plan_code)
    if not plan:
        raise ValueError("unknown_plan")
    now = datetime.now(timezone.utc)
    sub = SubscriptionDB(
        id=str(uuid4()),
        user_id=user_id,
        plan_id=plan.id,
        status="pending",
        started_at=None,
        expires_at=None,
        auto_renew=False,
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub
