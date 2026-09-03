"""Admin commerce API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.database import UserDB, get_db
from api.deps import _require_admin, _require_admin_finance, require_finance_step_up
from api.services import admin_commerce_service, admin_idempotency_service, admin_service

router = APIRouter(prefix="/v1/admin/commerce", tags=["admin-commerce"])


class CreditPackageCreate(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    credits: int = 0
    price_cents: int = 0
    currency: str = "CNY"
    is_active: bool = True
    valid_days: Optional[int] = None
    meta_json: Optional[str] = None


class CreditPackagePatch(BaseModel):
    name: Optional[str] = None
    credits: Optional[int] = None
    price_cents: Optional[int] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None
    valid_days: Optional[int] = None
    meta_json: Optional[str] = None


class ReconciliationRunCreate(BaseModel):
    label: str = Field(..., min_length=1)


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/orders")
def commerce_orders(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_finance),
):
    rows, total = admin_commerce_service.list_orders(db, user_id=user_id, status=status, page=page, page_size=page_size)
    return {"total": total, "items": [admin_commerce_service.order_to_dict(r) for r in rows]}


@router.get("/orders/{order_id}")
def commerce_order_detail(order_id: str, db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_finance)):
    o = admin_commerce_service.get_order(db, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="未找到")
    return admin_commerce_service.order_to_dict(o)


@router.post("/orders/{order_id}/manual-confirm")
def commerce_manual_confirm(
    order_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(require_finance_step_up),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="请提供 Idempotency-Key 请求头。")
    route = f"POST:/v1/admin/commerce/orders/{order_id}/manual-confirm"
    cached = admin_idempotency_service.get_cached_response(db, route=route, idempotency_key=idempotency_key)
    if cached is not None:
        return cached
    try:
        o = admin_commerce_service.manual_confirm_order(db, order_id, admin_id=admin.id, idempotency_key=idempotency_key)
    except ValueError as e:
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="未找到") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    out: Dict[str, Any] = {"message": "ok", "order": admin_commerce_service.order_to_dict(o)}
    admin_idempotency_service.store_response(db, route=route, idempotency_key=idempotency_key, response_body=out)
    admin_service._audit(
        db, admin_id=admin.id, action="commerce.manual_confirm", payload={"order_id": order_id}, ip=_ip(request)
    )
    return out


@router.post("/orders/{order_id}/refund")
def commerce_refund(
    order_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(require_finance_step_up),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    amount_cents: Optional[int] = Query(None),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="请提供 Idempotency-Key 请求头。")
    route = f"POST:/v1/admin/commerce/orders/{order_id}/refund"
    cached = admin_idempotency_service.get_cached_response(db, route=route, idempotency_key=idempotency_key)
    if cached is not None:
        return cached
    try:
        o = admin_commerce_service.refund_order(db, order_id, admin_id=admin.id, amount_cents=amount_cents)
    except ValueError as e:
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="未找到") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = {"message": "ok", "order": admin_commerce_service.order_to_dict(o)}
    admin_idempotency_service.store_response(db, route=route, idempotency_key=idempotency_key, response_body=out)
    admin_service._audit(
        db, admin_id=admin.id, action="commerce.refund", payload={"order_id": order_id, "amount_cents": amount_cents}, ip=_ip(request)
    )
    return out


@router.get("/credit-packages")
def commerce_packages_list(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_finance)):
    return [admin_commerce_service.package_to_dict(p) for p in admin_commerce_service.list_credit_packages(db)]


@router.post("/credit-packages")
def commerce_packages_create(
    body: CreditPackageCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_finance),
):
    p = admin_commerce_service.upsert_credit_package(db, body.model_dump())
    admin_service._audit(db, admin_id=admin.id, action="commerce.credit_package.create", payload={"id": p.id}, ip=_ip(request))
    return admin_commerce_service.package_to_dict(p)


@router.patch("/credit-packages/{package_id}")
def commerce_packages_patch(
    package_id: str,
    body: CreditPackagePatch,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_finance),
):
    try:
        p = admin_commerce_service.upsert_credit_package(db, body.model_dump(exclude_unset=True), package_id=package_id)
    except ValueError as e:
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="未找到") from e
        raise
    admin_service._audit(db, admin_id=admin.id, action="commerce.credit_package.patch", payload={"id": package_id}, ip=_ip(request))
    return admin_commerce_service.package_to_dict(p)


@router.get("/credit-ledger")
def commerce_ledger(
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_finance),
):
    rows, total = admin_commerce_service.credit_ledger(db, user_id=user_id, page=page, page_size=page_size)
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "delta": r.delta,
                "type": r.type,
                "reason": r.reason,
                "ref_type": r.ref_type,
                "ref_id": r.ref_id,
                "balance_after": r.balance_after,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/reconciliation/runs")
def commerce_recon_list(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_finance)):
    runs = admin_commerce_service.list_reconciliation_runs(db)
    return {
        "items": [
            {
                "id": r.id,
                "label": r.label,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }


@router.post("/reconciliation/runs")
def commerce_recon_create(
    body: ReconciliationRunCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_finance),
):
    r = admin_commerce_service.create_reconciliation_run(db, label=body.label, admin_id=admin.id)
    admin_service._audit(db, admin_id=admin.id, action="commerce.reconciliation.create", payload={"id": r.id}, ip=_ip(request))
    return {"id": r.id, "label": r.label, "status": r.status}


@router.get("/api-costs")
def commerce_api_costs(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_finance)):
    return admin_commerce_service.api_costs_summary(db)


@router.get("/payment-settings")
def commerce_payment_settings(_: UserDB = Depends(_require_admin_finance)):
    return {"channels": ["manual", "wechat", "alipay", "stripe"], "note": "真实渠道验签与回调后续接入；当前为配置占位。"}


@router.get("/pricing-table")
def commerce_pricing_table(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin)):
    from api.services import billing_service

    return [billing_service.plan_to_public(p) for p in admin_service.list_plans_admin(db)]
