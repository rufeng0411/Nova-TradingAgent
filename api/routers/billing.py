"""Billing: plans, balance, transactions, subscription (MVP)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import SubscriptionDB, UserDB, get_db
from api.deps import _require_web_user
from api.schemas.billing import (
    BalanceOut,
    CreditTransactionOut,
    PlanOut,
    SubscribeRequest,
    SubscriptionOut,
    TransactionListResponse,
)
from api.services import billing_service, credits_service

router = APIRouter(prefix="/v1/billing", tags=["billing"])


@router.get("/plans", response_model=List[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    rows = billing_service.list_active_plans(db)
    out = []
    for p in rows:
        d = billing_service.plan_to_public(p)
        out.append(PlanOut(**d))
    return out


@router.get("/balance", response_model=BalanceOut)
def balance(db: Session = Depends(get_db), current_user: UserDB = Depends(_require_web_user)):
    u = db.query(UserDB).filter(UserDB.id == current_user.id).first() or current_user
    code, exp, st = billing_service.user_plan_snapshot(db, u)
    return BalanceOut(
        credits=int(getattr(u, "credits", 0) or 0),
        plan_code=code,
        subscription_status=st,
        subscription_expires_at=exp,
    )


@router.get("/transactions", response_model=TransactionListResponse)
def transactions(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    rows, total = credits_service.list_transactions(db, current_user.id, skip=skip, limit=min(limit, 200))
    items = [
        CreditTransactionOut(
            id=r.id,
            delta=r.delta,
            type=r.type,
            reason=r.reason,
            ref_type=r.ref_type,
            ref_id=r.ref_id,
            balance_after=r.balance_after,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return TransactionListResponse(total=total, items=items)


@router.get("/subscription", response_model=Optional[SubscriptionOut])
def current_subscription(db: Session = Depends(get_db), current_user: UserDB = Depends(_require_web_user)):
    sid = getattr(current_user, "current_subscription_id", None)
    if not sid:
        return None
    sub = db.query(SubscriptionDB).filter(SubscriptionDB.id == sid).first()
    if not sub:
        return None
    from api.database import PlanDB

    plan = db.query(PlanDB).filter(PlanDB.id == sub.plan_id).first()
    return SubscriptionOut(
        id=sub.id,
        plan_id=sub.plan_id,
        plan_code=plan.code if plan else None,
        status=sub.status,
        started_at=sub.started_at,
        expires_at=sub.expires_at,
        auto_renew=sub.auto_renew,
    )


@router.post("/subscribe")
def subscribe(
    body: SubscribeRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    try:
        sub = billing_service.create_pending_subscription(db, current_user.id, body.plan_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"message": "已提交订阅申请，请等待管理员审核", "subscription_id": sub.id}
