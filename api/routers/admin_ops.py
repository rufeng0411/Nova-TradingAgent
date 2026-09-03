"""Admin ops API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import ReportDB, UserDB, get_db
from api.deps import _require_admin_ops
from api.services import admin_ops_service

router = APIRouter(prefix="/v1/admin/ops", tags=["admin-ops"])


@router.get("/tasks")
def ops_tasks(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_ops),
):
    rows, total = admin_ops_service.list_tasks(db, user_id=user_id, status=status, page=page, page_size=page_size)
    return {"total": total, "items": [admin_ops_service.report_task_dict(r) for r in rows]}


@router.get("/tasks/{task_id}")
def ops_task_detail(task_id: str, db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_ops)):
    row = db.query(ReportDB).filter(ReportDB.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到")
    return admin_ops_service.report_task_dict(row)


@router.post("/tasks/{task_id}/retry")
def ops_task_retry(task_id: str, _: UserDB = Depends(_require_admin_ops)):
    raise HTTPException(status_code=501, detail="重试入口需与任务队列联动；当前未实现。")


@router.post("/tasks/{task_id}/cancel")
def ops_task_cancel(task_id: str, _: UserDB = Depends(_require_admin_ops)):
    raise HTTPException(status_code=501, detail="取消入口需与任务队列联动；当前未实现。")


@router.get("/usage")
def ops_usage(
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_ops),
):
    rows, total = admin_ops_service.list_usage_records(db, user_id=user_id, page=page, page_size=page_size)
    return {"total": total, "items": [admin_ops_service.usage_dict(u) for u in rows]}


@router.get("/ai-calls")
def ops_ai_calls(
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_ops),
):
    rows, total = admin_ops_service.list_ai_calls(db, user_id=user_id, page=page, page_size=page_size)
    return {"total": total, "items": [admin_ops_service.ai_call_dict(a) for a in rows]}


@router.get("/marketdata/vendor-stats")
def ops_marketdata_vendor_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_ops),
):
    return {
        "days": max(1, days),
        "items": admin_ops_service.vendor_stats(db, days=days),
    }


@router.get("/marketdata/recon-anomalies")
def ops_marketdata_recon_anomalies(
    trade_date: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_ops),
):
    return {
        "items": admin_ops_service.recon_anomalies(db, trade_date=trade_date, limit=limit),
    }


@router.get("/marketdata/sync-status")
def ops_marketdata_sync_status(
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_ops),
):
    return admin_ops_service.sync_status(db)


@router.get("/fast-analysis/metrics")
def ops_fast_analysis_metrics(
    days: int = 7,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin_ops),
):
    return admin_ops_service.fast_analysis_metrics(db, days=days)
