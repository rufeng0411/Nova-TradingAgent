"""Admin commerce: orders, packages, ledger, reconciliation, API cost placeholders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from api.database import CreditPackageDB, CreditTransactionDB, OrderDB, PaymentEventDB, ReconciliationRunDB
from api.services import admin_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def list_orders(
    db: Session,
    *,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[OrderDB], int]:
    q = db.query(OrderDB)
    if user_id:
        q = q.filter(OrderDB.user_id == user_id)
    if status:
        q = q.filter(OrderDB.status == status)
    total = q.count()
    rows = q.order_by(OrderDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def get_order(db: Session, order_id: str) -> Optional[OrderDB]:
    return db.query(OrderDB).filter(OrderDB.id == order_id).first()


def create_order_placeholder(
    db: Session,
    *,
    user_id: str,
    subject_type: str,
    subject_id: Optional[str],
    amount_cents: int,
    currency: str = "CNY",
    pay_channel: str = "manual",
) -> OrderDB:
    o = OrderDB(
        id=str(uuid4()),
        order_no=f"ORD-{uuid4().hex[:12].upper()}",
        user_id=user_id,
        subject_type=subject_type,
        subject_id=subject_id,
        amount_cents=amount_cents,
        currency=currency,
        status="pending",
        pay_channel=pay_channel,
        paid_at=None,
        refunded_cents=0,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def manual_confirm_order(
    db: Session, order_id: str, *, admin_id: str, idempotency_key: Optional[str]
) -> OrderDB:
    o = get_order(db, order_id)
    if not o:
        raise ValueError("not_found")
    if o.status == "paid":
        return o
    if o.status not in ("pending",):
        raise ValueError("invalid_status")
    o.status = "paid"
    o.paid_at = _now()
    o.updated_at = _now()
    ev = PaymentEventDB(
        id=str(uuid4()),
        order_id=o.id,
        provider=o.pay_channel,
        event_type="manual_confirmed",
        provider_trade_no=None,
        amount_cents=o.amount_cents,
        raw_payload_json=json.dumps({"admin_id": admin_id, "idempotency_key": idempotency_key}, ensure_ascii=False),
        created_at=_now(),
    )
    db.add(ev)
    db.commit()
    db.refresh(o)
    return o


def refund_order(db: Session, order_id: str, *, admin_id: str, amount_cents: Optional[int]) -> OrderDB:
    o = get_order(db, order_id)
    if not o:
        raise ValueError("not_found")
    if o.status not in ("paid", "partially_refunded"):
        raise ValueError("invalid_status")
    refund_amt = amount_cents if amount_cents is not None else o.amount_cents - int(o.refunded_cents or 0)
    if refund_amt <= 0:
        raise ValueError("invalid_amount")
    remaining = o.amount_cents - int(o.refunded_cents or 0)
    if refund_amt > remaining:
        raise ValueError("invalid_amount")
    o.refunded_cents = int(o.refunded_cents or 0) + refund_amt
    o.status = "refunded" if o.refunded_cents >= o.amount_cents else "partially_refunded"
    o.updated_at = _now()
    ev = PaymentEventDB(
        id=str(uuid4()),
        order_id=o.id,
        provider=o.pay_channel,
        event_type="refund_succeeded",
        provider_trade_no=None,
        amount_cents=refund_amt,
        raw_payload_json=json.dumps({"admin_id": admin_id}, ensure_ascii=False),
        created_at=_now(),
    )
    db.add(ev)
    db.commit()
    db.refresh(o)
    return o


def list_credit_packages(db: Session) -> List[CreditPackageDB]:
    return db.query(CreditPackageDB).order_by(CreditPackageDB.created_at.desc()).all()


def upsert_credit_package(db: Session, data: Dict[str, Any], package_id: Optional[str] = None) -> CreditPackageDB:
    now = _now()
    if package_id:
        p = db.query(CreditPackageDB).filter(CreditPackageDB.id == package_id).first()
        if not p:
            raise ValueError("not_found")
        for k in ("name", "credits", "price_cents", "currency", "is_active", "valid_days", "meta_json"):
            if k in data and data[k] is not None:
                setattr(p, k, data[k])
        p.updated_at = now
        db.commit()
        db.refresh(p)
        return p
    p = CreditPackageDB(
        id=str(uuid4()),
        code=str(data.get("code", "")).strip().lower() or f"pkg-{uuid4().hex[:8]}",
        name=data.get("name", "礼包"),
        credits=int(data.get("credits", 0)),
        price_cents=int(data.get("price_cents", 0)),
        currency=data.get("currency", "CNY"),
        is_active=bool(data.get("is_active", True)),
        valid_days=data.get("valid_days"),
        meta_json=data.get("meta_json"),
        created_at=now,
        updated_at=now,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def credit_ledger(db: Session, *, user_id: Optional[str], page: int, page_size: int) -> Tuple[List[CreditTransactionDB], int]:
    return admin_service.list_credit_transactions(db, user_id=user_id, page=page, page_size=page_size)


def list_reconciliation_runs(db: Session) -> List[ReconciliationRunDB]:
    return db.query(ReconciliationRunDB).order_by(ReconciliationRunDB.created_at.desc()).limit(50).all()


def create_reconciliation_run(db: Session, *, label: str, admin_id: str) -> ReconciliationRunDB:
    r = ReconciliationRunDB(
        id=str(uuid4()),
        label=label,
        status="open",
        summary_json=None,
        created_by=admin_id,
        created_at=_now(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def api_costs_summary(db: Session) -> Dict[str, Any]:
    """占位：后续接 ai_call_logs 聚合。"""
    return {"items": [], "note": "按模型/供应商的成本汇总将基于 AI 调用日志；当前返回占位。"}


def order_to_dict(o: OrderDB) -> Dict[str, Any]:
    return {
        "id": o.id,
        "order_no": o.order_no,
        "user_id": o.user_id,
        "subject_type": o.subject_type,
        "subject_id": o.subject_id,
        "amount_cents": o.amount_cents,
        "currency": o.currency,
        "status": o.status,
        "pay_channel": o.pay_channel,
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "refunded_cents": int(o.refunded_cents or 0),
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def package_to_dict(p: CreditPackageDB) -> Dict[str, Any]:
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "credits": p.credits,
        "price_cents": p.price_cents,
        "currency": p.currency,
        "is_active": p.is_active,
        "valid_days": p.valid_days,
        "meta_json": p.meta_json,
    }
