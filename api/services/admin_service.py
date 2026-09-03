"""Admin operations: users, credits, audit, dashboard."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from api.database import (
    AccessLogDB,
    AdminAuditLogDB,
    CreditTransactionDB,
    PlanDB,
    SYSTEM_LEGACY_USER_ID,
    SubscriptionDB,
    UserDB,
)
from api.services import auth_service, credits_service
from api.services import billing_service

logger = logging.getLogger(__name__)


def _audit(
    db: Session,
    *,
    admin_id: str,
    action: str,
    target_user_id: Optional[str] = None,
    payload: Optional[dict] = None,
    ip: Optional[str] = None,
) -> None:
    row = AdminAuditLogDB(
        id=str(uuid4()),
        admin_id=admin_id,
        action=action,
        target_user_id=target_user_id,
        payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        ip=ip,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()


def dashboard_stats(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = start_day + timedelta(days=1)
    total_users = db.query(func.count(UserDB.id)).scalar() or 0
    users_today = (
        db.query(func.count(UserDB.id))
        .filter(UserDB.created_at >= start_day, UserDB.created_at < end_day)
        .scalar()
        or 0
    )
    start = start_day
    consumed = (
        db.query(func.coalesce(func.sum(CreditTransactionDB.delta * -1), 0))
        .filter(
            CreditTransactionDB.created_at >= start,
            CreditTransactionDB.type == "reserve",
        )
        .scalar()
        or 0
    )
    active_subs = (
        db.query(func.count(SubscriptionDB.id))
        .filter(SubscriptionDB.status == "active")
        .scalar()
        or 0
    )
    return {
        "total_users": int(total_users),
        "users_today": int(users_today),
        "credits_consumed_today": int(consumed),
        "active_subscriptions": int(active_subs),
    }


def list_users(
    db: Session,
    *,
    q: Optional[str] = None,
    role: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[UserDB], int]:
    query = db.query(UserDB).filter(UserDB.id != SYSTEM_LEGACY_USER_ID, UserDB.role != "system")
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(UserDB.email.ilike(like), UserDB.username.ilike(like)))
    if role:
        query = query.filter(UserDB.role == role)
    total = query.count()
    items = (
        query.order_by(UserDB.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_user(db: Session, user_id: str) -> Optional[UserDB]:
    return db.query(UserDB).filter(UserDB.id == user_id).first()


def update_user(
    db: Session,
    target_id: str,
    data: dict,
    *,
    admin_id: str,
    ip: Optional[str] = None,
) -> UserDB:
    u = get_user(db, target_id)
    if not u:
        raise ValueError("not_found")
    if "email" in data and data["email"]:
        u.email = auth_service.normalize_email(data["email"])
    if "username" in data and data["username"]:
        u.username = auth_service.normalize_username(data["username"])
    if "display_name" in data:
        u.display_name = data["display_name"] or None
    if "role" in data and data["role"]:
        u.role = data["role"]
    if "status" in data and data["status"]:
        u.status = data["status"]
    if "admin_permissions" in data and data["admin_permissions"] is not None:
        v = data["admin_permissions"]
        u.admin_permissions = v if isinstance(v, list) and len(v) > 0 else None
    db.commit()
    db.refresh(u)
    _audit(db, admin_id=admin_id, action="user.update", target_user_id=target_id, payload=data, ip=ip)
    return u


def admin_reset_password(
    db: Session,
    target_id: str,
    new_password: str,
    *,
    admin_id: str,
    ip: Optional[str] = None,
) -> None:
    auth_service.admin_set_password(db, target_id, new_password)
    _audit(db, admin_id=admin_id, action="user.reset_password", target_user_id=target_id, ip=ip)


def adjust_credits(
    db: Session,
    target_id: str,
    delta: int,
    reason: str,
    *,
    admin_id: str,
    ip: Optional[str] = None,
) -> int:
    bal = credits_service.grant(db, target_id, delta, reason or "admin_adjust", operator_id=admin_id)
    _audit(
        db,
        admin_id=admin_id,
        action="user.adjust_credits",
        target_user_id=target_id,
        payload={"delta": delta, "reason": reason},
        ip=ip,
    )
    return bal


def set_subscription(
    db: Session,
    target_id: str,
    plan_code: str,
    days: int,
    status: str,
    *,
    admin_id: str,
    ip: Optional[str] = None,
) -> SubscriptionDB:
    plan = billing_service.get_plan_by_code(db, plan_code)
    if not plan:
        raise ValueError("unknown_plan")
    now = datetime.now(timezone.utc)
    sub = SubscriptionDB(
        id=str(uuid4()),
        user_id=target_id,
        plan_id=plan.id,
        status=status,
        started_at=now,
        expires_at=now + timedelta(days=max(1, days)),
        auto_renew=False,
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    u = db.query(UserDB).filter(UserDB.id == target_id).first()
    if u:
        u.current_subscription_id = sub.id
        u.updated_at = now
    db.commit()
    db.refresh(sub)
    _audit(
        db,
        admin_id=admin_id,
        action="user.subscription",
        target_user_id=target_id,
        payload={"plan_code": plan_code, "days": days, "status": status},
        ip=ip,
    )
    return sub


def list_access_logs(
    db: Session,
    *,
    user_id: Optional[str] = None,
    path_like: Optional[str] = None,
    status_code: Optional[int] = None,
    failures_only: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[AccessLogDB], int]:
    q = db.query(AccessLogDB)
    if user_id:
        q = q.filter(AccessLogDB.user_id == user_id)
    if path_like:
        q = q.filter(AccessLogDB.path.ilike(f"%{path_like}%"))
    if status_code is not None:
        q = q.filter(AccessLogDB.status_code == status_code)
    if failures_only:
        q = q.filter(AccessLogDB.status_code.isnot(None), AccessLogDB.status_code >= 400)
    total = q.count()
    rows = q.order_by(AccessLogDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def list_audit_logs(
    db: Session, *, page: int = 1, page_size: int = 50, target_user_id: Optional[str] = None
) -> Tuple[List[AdminAuditLogDB], int]:
    q = db.query(AdminAuditLogDB)
    if target_user_id:
        q = q.filter(AdminAuditLogDB.target_user_id == target_user_id)
    total = q.count()
    rows = q.order_by(AdminAuditLogDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def list_credit_transactions(
    db: Session,
    *,
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[CreditTransactionDB], int]:
    q = db.query(CreditTransactionDB)
    if user_id:
        q = q.filter(CreditTransactionDB.user_id == user_id)
    total = q.count()
    rows = (
        q.order_by(CreditTransactionDB.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def list_plans_admin(db: Session) -> List[PlanDB]:
    return db.query(PlanDB).order_by(PlanDB.sort_order.asc()).all()


def create_plan(db: Session, data: dict, *, admin_id: str, ip: Optional[str] = None) -> PlanDB:
    now = datetime.now(timezone.utc)
    p = PlanDB(
        id=str(uuid4()),
        code=data["code"].strip().lower(),
        name=data["name"],
        price_cents=int(data.get("price_cents", 0)),
        currency=data.get("currency", "CNY"),
        period_days=int(data.get("period_days", 30)),
        monthly_credits=int(data.get("monthly_credits", 0)),
        features_json=json.dumps(data.get("features") or [], ensure_ascii=False),
        is_active=bool(data.get("is_active", True)),
        sort_order=int(data.get("sort_order", 0)),
        created_at=now,
        updated_at=now,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    _audit(db, admin_id=admin_id, action="plan.create", payload={"code": p.code}, ip=ip)
    return p


def patch_plan(db: Session, plan_id: str, data: dict, *, admin_id: str, ip: Optional[str] = None) -> PlanDB:
    p = db.query(PlanDB).filter(PlanDB.id == plan_id).first()
    if not p:
        raise ValueError("not_found")
    for k in ("name", "currency"):
        if k in data and data[k] is not None:
            setattr(p, k, data[k])
    if "price_cents" in data and data["price_cents"] is not None:
        p.price_cents = int(data["price_cents"])
    if "monthly_credits" in data and data["monthly_credits"] is not None:
        p.monthly_credits = int(data["monthly_credits"])
    if "is_active" in data and data["is_active"] is not None:
        p.is_active = bool(data["is_active"])
    if "sort_order" in data and data["sort_order"] is not None:
        p.sort_order = int(data["sort_order"])
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)
    _audit(db, admin_id=admin_id, action="plan.patch", payload={"id": plan_id, **data}, ip=ip)
    return p
