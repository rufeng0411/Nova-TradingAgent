"""User entitlements (advanced market, etc.) derived from role + subscription."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from api.database import PlanDB, SubscriptionDB, UserDB
from api.services import billing_service


def _plan_features(plan: PlanDB | None) -> list[str]:
    if not plan or not plan.features_json:
        return []
    try:
        raw = json.loads(plan.features_json)
        return [str(x) for x in raw] if isinstance(raw, list) else []
    except json.JSONDecodeError:
        return []


def user_has_advanced_market(db: Session, user: UserDB) -> bool:
    """高级行情：管理员默认放行；否则需有效订阅且套餐含 advanced_market 或为 team 档。"""
    if getattr(user, "role", "user") == "admin":
        return True

    code, expires_at, status = billing_service.user_plan_snapshot(db, user)
    if not code or str(status).lower() != "active":
        return False
    if expires_at is not None:
        exp = expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return False

    plan = billing_service.get_plan_by_code(db, code)
    feats = _plan_features(plan)
    if "advanced_market" in feats:
        return True
    if code and code.strip().lower() in ("team", "enterprise", "vip"):
        return True
    return False


def user_entitlements_payload(db: Session, user: UserDB) -> dict[str, Any]:
    advanced = user_has_advanced_market(db, user)
    fast_analysis = user_has_fast_analysis(db, user)
    rt_enabled = os.getenv("TA_TUSHARE_RT_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
    has_token = bool((os.getenv("TUSHARE_RT_TOKEN") or os.getenv("TUSHARE_TOKEN") or "").strip())
    pro_enabled = os.getenv("TA_TUSHARE_PRO_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
    return {
        "advanced_market": advanced,
        "tushare_rt": bool(advanced and rt_enabled and has_token),
        "tushare_pro": bool(advanced and pro_enabled and has_token),
        "fast_analysis": fast_analysis,
        "role": getattr(user, "role", "user") or "user",
    }


def user_has_fast_analysis(db: Session, user: UserDB) -> bool:
    """快速分析权益：管理员放行，或 active 订阅套餐含 fast_analysis / 属于 team+。"""
    if getattr(user, "role", "user") == "admin":
        return True

    code, expires_at, status = billing_service.user_plan_snapshot(db, user)
    if not code or str(status).lower() != "active":
        return False
    if expires_at is not None:
        exp = expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return False
    plan = billing_service.get_plan_by_code(db, code)
    feats = _plan_features(plan)
    if "fast_analysis" in feats:
        return True
    return code.strip().lower() in ("team", "enterprise", "vip")
