"""Admin/user endpoints for Qlib evaluation sandbox (feature-flagged)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.database import UserDB, get_db
from api.deps import _require_admin, _require_api_user
from api.services import qlib_eval_service
from tradingagents.qlib_eval.config import qlib_bridge_enabled, qlib_sandbox_enabled, qlib_sweeps_enabled

router = APIRouter(prefix="/v1/qlib-eval", tags=["qlib-eval"])


@router.get("/status")
def qlib_eval_status(_: UserDB = Depends(_require_api_user)):
    return {
        "enabled": qlib_eval_service.is_enabled(),
        "sandbox_enabled": qlib_sandbox_enabled(),
        "sweeps_enabled": qlib_sweeps_enabled(),
        "bridge_enabled": qlib_bridge_enabled(),
    }


@router.get("/gates")
def qlib_eval_gates(
    since_days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_api_user),
):
    payload = qlib_eval_service.get_gate_summary(db, since_days=since_days)
    if not payload.get("enabled"):
        raise HTTPException(status_code=404, detail="qlib_eval_disabled")
    return payload


@router.get("/runs")
def qlib_eval_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_api_user),
):
    if getattr(user, "role", "user") != "admin" and not qlib_eval_service.is_enabled():
        raise HTTPException(status_code=403, detail="forbidden")
    return qlib_eval_service.list_recent_runs(db, limit=limit)


@router.post("/sandbox/export")
def qlib_eval_sandbox_export(
    since_days: int = Query(90, ge=7, le=365),
    limit: int = Query(500, ge=50, le=2000),
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_admin),
):
    payload = qlib_eval_service.run_sandbox_export(
        db,
        since_days=since_days,
        limit=limit,
        created_by=str(user.id),
    )
    if not payload.get("enabled"):
        raise HTTPException(status_code=404, detail="qlib_sandbox_disabled")
    return payload


@router.post("/bridge/submit")
def qlib_eval_bridge_submit(
    since_days: int = Query(90, ge=7, le=365),
    limit: int = Query(500, ge=50, le=2000),
    label_horizon: str = Query("t2", pattern="^(t0|t1|t2|t3|t5)$"),
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_admin),
):
    payload = qlib_eval_service.submit_bridge_job(
        db,
        since_days=since_days,
        limit=limit,
        label_horizon=label_horizon,
        created_by=str(user.id),
    )
    if not payload.get("enabled"):
        raise HTTPException(status_code=404, detail="qlib_bridge_disabled")
    return payload


@router.post("/bridge/import")
def qlib_eval_bridge_import(
    run_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_admin),
):
    if run_id:
        payload = qlib_eval_service.import_bridge_result(db, run_id=run_id)
    else:
        payload = qlib_eval_service.import_all_pending_outbox(db)
    if not payload.get("enabled"):
        raise HTTPException(status_code=404, detail="qlib_bridge_disabled")
    return payload


@router.get("/bridge/context/{run_id}")
def qlib_eval_bridge_context(
    run_id: str,
    report_direction: str | None = Query(None),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_api_user),
):
    if not qlib_bridge_enabled():
        raise HTTPException(status_code=404, detail="qlib_bridge_disabled")
    return qlib_eval_service.get_quant_context_for_run(db, run_id, report_direction=report_direction)


@router.post("/sweeps/run")
def qlib_eval_sweeps_run(
    since_days: int = Query(90, ge=7, le=365),
    limit: int = Query(500, ge=50, le=2000),
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_admin),
):
    payload = qlib_eval_service.run_rule_sweeps(
        db,
        since_days=since_days,
        limit=limit,
        created_by=str(user.id),
    )
    if not payload.get("enabled"):
        raise HTTPException(status_code=404, detail="qlib_sweeps_disabled")
    return payload
