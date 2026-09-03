"""Admin API (web JWT + role=admin only)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.database import AccessLogDB, AdminAuditLogDB, CreditTransactionDB, PlanDB, UserDB, get_db
from api.deps import _require_admin, _require_admin_finance, require_ops_step_up
from api.schemas.admin import (
    AccessLogListResponse,
    AccessLogOut,
    AdminAdjustCreditsBody,
    AdminAuditOut,
    AdminBootstrapOut,
    AdminConfirmBody,
    AdminDashboardOut,
    AdminFeaturePatchBody,
    AdminResetPasswordBody,
    AdminSubscriptionBody,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserUpdate,
    PlanAdminCreate,
    PlanAdminPatch,
)
from api.services import (
    admin_confirm_service,
    admin_export_service,
    admin_idempotency_service,
    admin_metrics_service,
    admin_signals_service,
    admin_events_service,
    billing_service,
    features_service,
    password_service,
)
from api.services import admin_service

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/dashboard", response_model=AdminDashboardOut)
def dashboard(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin)):
    d = admin_service.dashboard_stats(db)
    return AdminDashboardOut(**d)


@router.get("/users", response_model=AdminUserListResponse)
def admin_list_users(
    q: Optional[str] = None,
    role: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    items, total = admin_service.list_users(db, q=q, role=role, page=page, page_size=page_size)
    return AdminUserListResponse(
        total=total,
        items=[
            AdminUserListItem(
                id=u.id,
                email=u.email,
                username=getattr(u, "username", None),
                role=getattr(u, "role", "user") or "user",
                status=getattr(u, "status", "active") or "active",
                credits=int(getattr(u, "credits", 0) or 0),
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            )
            for u in items
        ],
    )


@router.get("/users/{user_id}")
def admin_get_user(user_id: str, db: Session = Depends(get_db), _: UserDB = Depends(_require_admin)):
    u = admin_service.get_user(db, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="未找到")
    code, exp, st = billing_service.user_plan_snapshot(db, u)
    return {
        "id": u.id,
        "email": u.email,
        "username": getattr(u, "username", None),
        "display_name": getattr(u, "display_name", None),
        "role": getattr(u, "role", "user"),
        "status": getattr(u, "status", "active"),
        "credits": int(getattr(u, "credits", 0) or 0),
        "plan_code": code,
        "subscription_expires_at": exp,
        "created_at": u.created_at,
        "last_login_at": u.last_login_at,
        "admin_permissions": getattr(u, "admin_permissions", None),
    }


@router.patch("/users/{user_id}")
def admin_patch_user(
    user_id: str,
    body: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin),
):
    try:
        u = admin_service.update_user(
            db,
            user_id,
            body.model_dump(exclude_unset=True),
            admin_id=admin.id,
            ip=_ip(request),
        )
    except ValueError as e:
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="未找到") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"message": "ok", "id": u.id}


@router.post("/users/{user_id}/reset-password")
def admin_reset_pw(
    user_id: str,
    body: AdminResetPasswordBody,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(require_ops_step_up),
):
    try:
        admin_service.admin_reset_password(db, user_id, body.new_password, admin_id=admin.id, ip=_ip(request))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"message": "ok"}


@router.post("/users/{user_id}/credits")
def admin_credits(
    user_id: str,
    body: AdminAdjustCreditsBody,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_finance),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_admin_confirm: Optional[str] = Header(None, alias="X-Admin-Confirm"),
):
    route = f"POST:/v1/admin/users/{user_id}/credits"
    if idempotency_key:
        cached = admin_idempotency_service.get_cached_response(db, route=route, idempotency_key=idempotency_key)
        if cached is not None:
            return cached
    if not admin_confirm_service.consume_token(db, admin.id, x_admin_confirm):
        raise HTTPException(status_code=412, detail="敏感操作需二次确认：请先输入管理员登录密码获取确认令牌（X-Admin-Confirm），令牌约 5 分钟内有效。")
    bal = admin_service.adjust_credits(
        db, user_id, body.delta, body.reason, admin_id=admin.id, ip=_ip(request)
    )
    out = {"balance": bal}
    if idempotency_key:
        admin_idempotency_service.store_response(db, route=route, idempotency_key=idempotency_key, response_body=out)
    return out


@router.post("/users/{user_id}/subscription")
def admin_sub(
    user_id: str,
    body: AdminSubscriptionBody,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_finance),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_admin_confirm: Optional[str] = Header(None, alias="X-Admin-Confirm"),
):
    route = f"POST:/v1/admin/users/{user_id}/subscription"
    if idempotency_key:
        cached = admin_idempotency_service.get_cached_response(db, route=route, idempotency_key=idempotency_key)
        if cached is not None:
            return cached
    if not admin_confirm_service.consume_token(db, admin.id, x_admin_confirm):
        raise HTTPException(status_code=412, detail="敏感操作需二次确认：请先输入管理员登录密码获取确认令牌（X-Admin-Confirm），令牌约 5 分钟内有效。")
    try:
        admin_service.set_subscription(
            db,
            user_id,
            body.plan_code,
            body.days,
            body.status,
            admin_id=admin.id,
            ip=_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = {"message": "ok"}
    if idempotency_key:
        admin_idempotency_service.store_response(db, route=route, idempotency_key=idempotency_key, response_body=out)
    return out


@router.get("/access-logs", response_model=AccessLogListResponse)
def access_logs(
    user_id: Optional[str] = None,
    path: Optional[str] = None,
    status_code: Optional[int] = None,
    failures_only: bool = False,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    rows, total = admin_service.list_access_logs(
        db,
        user_id=user_id,
        path_like=path,
        status_code=status_code,
        failures_only=failures_only,
        page=page,
        page_size=page_size,
    )
    return AccessLogListResponse(
        total=total,
        items=[
            AccessLogOut(
                id=r.id,
                user_id=r.user_id,
                ip=r.ip,
                method=r.method,
                path=r.path,
                status_code=r.status_code,
                latency_ms=r.latency_ms,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.get("/audit-logs")
def audit_logs(
    page: int = 1,
    page_size: int = 50,
    target_user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    rows, total = admin_service.list_audit_logs(db, page=page, page_size=page_size, target_user_id=target_user_id)
    items = []
    for r in rows:
        payload = None
        if r.payload_json:
            try:
                payload = json.loads(r.payload_json)
            except json.JSONDecodeError:
                payload = {"raw": r.payload_json}
        items.append(
            AdminAuditOut(
                id=r.id,
                admin_id=r.admin_id,
                action=r.action,
                target_user_id=r.target_user_id,
                payload=payload,
                ip=r.ip,
                created_at=r.created_at,
            )
        )
    return {"total": total, "items": items}


@router.get("/plans")
def admin_plans_list(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin)):
    return [billing_service.plan_to_public(p) for p in admin_service.list_plans_admin(db)]


@router.post("/plans")
def admin_plans_create(
    body: PlanAdminCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin),
):
    p = admin_service.create_plan(db, body.model_dump(), admin_id=admin.id, ip=_ip(request))
    return billing_service.plan_to_public(p)


@router.patch("/plans/{plan_id}")
def admin_plans_patch(
    plan_id: str,
    body: PlanAdminPatch,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin),
    x_admin_confirm: Optional[str] = Header(None, alias="X-Admin-Confirm"),
):
    from api.deps import admin_has_scope

    data = body.model_dump(exclude_unset=True)
    sensitive = bool({"price_cents", "monthly_credits"} & set(data.keys()))
    if sensitive:
        if not admin_has_scope(admin, "finance"):
            raise HTTPException(status_code=403, detail="当前管理员账号没有执行此操作的权限。")
        if not admin_confirm_service.consume_token(db, admin.id, x_admin_confirm):
            raise HTTPException(status_code=412, detail="敏感操作需二次确认：请先输入管理员登录密码获取确认令牌（X-Admin-Confirm），令牌约 5 分钟内有效。")
    try:
        p = admin_service.patch_plan(db, plan_id, body.model_dump(exclude_unset=True), admin_id=admin.id, ip=_ip(request))
    except ValueError as e:
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="未找到") from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    return billing_service.plan_to_public(p)


def _api_version() -> str:
    import os
    from importlib.metadata import version as pkg_version

    v = os.getenv("APP_VERSION")
    if v:
        return v
    try:
        return pkg_version("tradingagents")
    except Exception:
        return "dev"


@router.get("/bootstrap", response_model=AdminBootstrapOut)
def admin_bootstrap(db: Session = Depends(get_db), admin: UserDB = Depends(_require_admin)):
    feats = features_service.get_merged(db)
    mods = {
        "reports": True,
        "commerce": True,
        "ops": True,
        "security": True,
        "content": True,
    }
    return AdminBootstrapOut(
        admin={
            "id": admin.id,
            "email": admin.email,
            "role": getattr(admin, "role", "user"),
            "admin_permissions": getattr(admin, "admin_permissions", None),
        },
        features=feats,
        server_time=datetime.now(timezone.utc),
        api_version=_api_version(),
        enabled_modules=mods,
    )


@router.get("/metrics/overview")
def admin_metrics_overview(
    from_: datetime = Query(..., alias="from"),
    to: datetime = Query(..., alias="to"),
    granularity: str = Query("day", pattern="^(day|hour)$"),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    pts = admin_metrics_service.metrics_overview(db, from_ts=from_, to_ts=to, granularity=granularity)  # type: ignore[arg-type]
    return {"items": pts, "granularity": granularity}


@router.get("/metrics/credits")
def admin_metrics_credits(
    from_: datetime = Query(..., alias="from"),
    to: datetime = Query(..., alias="to"),
    granularity: str = Query("day", pattern="^(day|hour)$"),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    pts = admin_metrics_service.metrics_credits(db, from_ts=from_, to_ts=to, granularity=granularity, user_id=user_id)  # type: ignore[arg-type]
    return {"items": pts}


@router.get("/metrics/traffic")
def admin_metrics_traffic(
    from_: datetime = Query(..., alias="from"),
    to: datetime = Query(..., alias="to"),
    granularity: str = Query("day", pattern="^(day|hour)$"),
    path_prefix: Optional[str] = None,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    data = admin_metrics_service.metrics_traffic(
        db, from_ts=from_, to_ts=to, granularity=granularity, path_prefix=path_prefix  # type: ignore[arg-type]
    )
    return data


@router.get("/signals")
def admin_signals(
    severity: Optional[str] = None,
    type: Optional[str] = None,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None, alias="to"),
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    rows, total = admin_signals_service.list_signals(
        db,
        severity=severity,
        type_prefix=type,
        from_ts=from_,
        to_ts=to,
        page=page,
        page_size=page_size,
    )
    items = []
    for r in rows:
        payload = None
        if r.payload_json:
            try:
                payload = json.loads(r.payload_json)
            except json.JSONDecodeError:
                payload = {"raw": r.payload_json}
        items.append(
            {
                "id": r.id,
                "type": r.type,
                "severity": r.severity,
                "user_id": r.user_id,
                "payload": payload,
                "created_at": r.created_at,
            }
        )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/events/stream")
async def admin_events_stream(admin: UserDB = Depends(_require_admin)):
    q = await admin_events_service.subscribe()

    async def gen():
        try:
            init = {"kind": "hello", "admin_id": admin.id}
            yield f"data: {json.dumps(init, ensure_ascii=False)}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(ev, default=str, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"kind\":\"ping\"}\n\n"
        finally:
            await admin_events_service.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/confirm")
def admin_confirm(
    body: AdminConfirmBody,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin),
):
    u = db.query(UserDB).filter(UserDB.id == admin.id).first()
    if not u or not u.password_hash or not password_service.verify_password(body.password, u.password_hash):
        raise HTTPException(status_code=400, detail="管理员密码不正确。")
    tok, exp = admin_confirm_service.issue_token(db, admin.id, created_ip=_ip(request))
    return {"confirm_token": tok, "expires_at": datetime.fromtimestamp(exp, tz=timezone.utc)}


@router.get("/features")
def admin_features_get(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin)):
    return features_service.get_merged(db)


@router.patch("/features")
def admin_features_patch(
    body: AdminFeaturePatchBody,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin),
):
    try:
        merged = features_service.patch(db, body.key, body.value, admin_id=admin.id)
    except ValueError as e:
        if str(e) == "unknown_feature_key":
            raise HTTPException(status_code=400, detail="未知的功能开关名称。") from e
        raise
    admin_service._audit(
        db,
        admin_id=admin.id,
        action="features.patch",
        payload={"key": body.key, "value": body.value},
        ip=_ip(request),
    )
    return merged


@router.post("/export")
def admin_export_create(
    request: Request,
    background_tasks: BackgroundTasks,
    export_type: str = Query(..., pattern="^(users|access_logs|credits)$"),
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin),
):
    job = admin_export_service.create_job(db, export_type=export_type, admin_id=admin.id)
    background_tasks.add_task(admin_export_service.run_export_job, job.id)
    admin_service._audit(db, admin_id=admin.id, action="export.create", payload={"job_id": job.id, "type": export_type}, ip=_ip(request))
    return {"id": job.id, "status": job.status}


@router.get("/export/{job_id}")
def admin_export_status(job_id: str, db: Session = Depends(get_db), _: UserDB = Depends(_require_admin)):
    job = admin_export_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="未找到")
    return {
        "id": job.id,
        "export_type": job.export_type,
        "status": job.status,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "download_ready": bool(job.status == "completed" and job.file_path and not job.download_consumed),
        "download_token": job.download_token if job.status == "completed" and not job.download_consumed else None,
    }


@router.get("/export/{job_id}/download")
def admin_export_download(
    job_id: str,
    token: str,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    from pathlib import Path

    from fastapi.responses import FileResponse

    job = admin_export_service.get_job(db, job_id)
    if not job or job.download_token != token:
        raise HTTPException(status_code=404, detail="未找到")
    if job.status != "completed" or not job.file_path:
        raise HTTPException(status_code=400, detail="导出任务尚未完成，请稍后再试。")
    if job.download_consumed:
        raise HTTPException(status_code=410, detail="该下载链接已使用或已失效，请重新导出。")
    p = Path(job.file_path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="导出文件不存在或已被清理。")
    job.download_consumed = True
    db.commit()
    return FileResponse(str(p), filename=f"{job.export_type}_{job_id}.csv", media_type="text/csv")


@router.get("/users/{user_id}/credit-transactions")
def admin_user_credits(
    user_id: str,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    rows, total = admin_service.list_credit_transactions(db, user_id=user_id, page=page, page_size=page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "delta": r.delta,
                "type": r.type,
                "reason": r.reason,
                "ref_type": r.ref_type,
                "ref_id": r.ref_id,
                "created_at": r.created_at,
            }
            for r in rows
        ],
    }
