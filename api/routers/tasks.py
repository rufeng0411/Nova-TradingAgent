"""User task center queue APIs."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.database import AnalysisJobDB, JobEventDB, UserDB, get_db
from api.deps import _require_api_user
from api.schemas.tasks import (
    TaskCenterItem,
    TaskCenterListResponse,
    TaskOperationResponse,
    TaskReorderRequest,
    TaskSubmitRequest,
    TaskSubmitResponse,
)
from api.services import task_queue_service
from api.services import symbol_service

router = APIRouter(prefix="/v1/me/tasks", tags=["tasks"])


def _to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _derive_task_name(job: Optional[AnalysisJobDB], fallback_symbol: Optional[str], fallback_trade_date: Optional[str]) -> str:
    symbol = (fallback_symbol or getattr(job, "symbol", None) or "").strip()
    trade_date = (fallback_trade_date or getattr(job, "trade_date", None) or "").strip()
    display = ""
    if symbol:
        display = symbol_service.format_display_label(
            symbol_service.resolve_cn_display_name(symbol),
            symbol,
        )
    if symbol and trade_date:
        return f"{display or symbol} {trade_date}"
    if symbol:
        return display or symbol
    return "智能分析任务"


def _submit_v2_enabled() -> bool:
    return os.getenv("TA_CHAT_TASK_SUBMIT_V2_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def _build_task_label(symbol: Optional[str], trade_date: Optional[str]) -> Optional[str]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None
    display = symbol_service.format_display_label(symbol_service.resolve_cn_display_name(sym), sym)
    td = str(trade_date or "").strip()
    return f"{display} {td}" if td else display


def _task_kind_from_job(job: Optional[AnalysisJobDB]) -> str:
    payload = dict(getattr(job, "request_payload", None) or {})
    return str(payload.get("task_kind") or "full_analysis")


@router.get("", response_model=TaskCenterListResponse)
def list_my_tasks(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
) -> TaskCenterListResponse:
    queue_rows = task_queue_service.list_user_queue_items(db, current_user.id)
    queue_job_ids = {row.job_id for row in queue_rows}
    job_map = {}
    if queue_job_ids:
        for row in (
            db.query(AnalysisJobDB)
            .filter(AnalysisJobDB.user_id == current_user.id, AnalysisJobDB.id.in_(list(queue_job_ids)))
            .all()
        ):
            job_map[row.id] = row

    queued_items: list[TaskCenterItem] = []
    for row in queue_rows:
        job = job_map.get(row.job_id)
        status = "paused" if row.queue_status == task_queue_service.QUEUE_STATUS_PAUSED else "queued"
        queued_items.append(
            TaskCenterItem(
                job_id=row.job_id,
                task_kind=row.task_kind,
                task_name=_derive_task_name(job, row.symbol, row.trade_date),
                description=row.description,
                symbol=row.symbol or (job.symbol if job else None),
                trade_date=row.trade_date or (job.trade_date if job else None),
                status=status,
                queue_status=row.queue_status,
                created_at=_to_iso(row.created_at),
                updated_at=_to_iso(row.updated_at),
                error=job.error if job else None,
                waiting_ahead_count=task_queue_service.waiting_ahead_count(db, current_user.id, row.job_id)
                if row.queue_status == task_queue_service.QUEUE_STATUS_QUEUED
                else None,
            )
        )

    running_rows = (
        db.query(AnalysisJobDB)
        .filter(
            AnalysisJobDB.user_id == current_user.id,
            AnalysisJobDB.status.in_(task_queue_service.ACTIVE_RUNNING_STATUSES),
        )
        .order_by(AnalysisJobDB.updated_at.desc(), AnalysisJobDB.created_at.desc())
        .all()
    )
    running_items = [
        TaskCenterItem(
            job_id=row.id,
            task_kind=_task_kind_from_job(row),
            task_name=_derive_task_name(row, row.symbol, row.trade_date),
            description=None,
            symbol=row.symbol,
            trade_date=row.trade_date,
            status="running",
            created_at=_to_iso(row.created_at),
            updated_at=_to_iso(row.updated_at),
            error=row.error,
        )
        for row in running_rows
    ]

    recent_rows = task_queue_service.list_user_recent_jobs(db, current_user.id, limit=30)
    recent_items: list[TaskCenterItem] = []
    for row in recent_rows:
        if row.id in queue_job_ids:
            continue
        if row.status not in ("completed", "failed"):
            continue
        item_status = "failed"
        if row.status == "completed":
            item_status = "completed"
        elif row.error and ("取消" in row.error or "cancel" in row.error.lower()):
            item_status = "failed"
        recent_items.append(
            TaskCenterItem(
                job_id=row.id,
                task_kind=_task_kind_from_job(row),
                task_name=_derive_task_name(row, row.symbol, row.trade_date),
                description=None,
                symbol=row.symbol,
                trade_date=row.trade_date,
                status=item_status,  # type: ignore[arg-type]
                created_at=_to_iso(row.created_at),
                updated_at=_to_iso(row.updated_at),
                error=row.error,
            )
        )

    return TaskCenterListResponse(running=running_items, queued=queued_items, recent=recent_items)


@router.post("/submit", response_model=TaskSubmitResponse)
async def submit_my_task(
    body: TaskSubmitRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
) -> TaskSubmitResponse:
    if not _submit_v2_enabled():
        raise HTTPException(status_code=503, detail="task submit v2 disabled")

    text = (body.text or "").strip()
    if not text:
        return TaskSubmitResponse(
            job_id="",
            status="failed",
            message="请输入要分析的标的或公司名称。",
        )

    from api import main as main_api

    config = await asyncio.to_thread(
        main_api._build_runtime_config,
        body.config_overrides or {},
        current_user.id,
    )
    symbol, trade_date, horizons, focus_areas, specific_questions, inferred_user_context = await asyncio.to_thread(
        main_api._ai_extract_symbol_and_date,
        text,
        config,
    )
    if not symbol:
        return TaskSubmitResponse(
            job_id="",
            status="failed",
            message="抱歉，我没能从您的消息中识别出股票标的。请输入代码（如 600519.SH）或可识别的公司名称。",
        )

    explicit_context = main_api._extract_request_user_context(body)
    merged_user_context = main_api._compose_analysis_user_context(
        db,
        current_user.id,
        symbol,
        explicit_context=explicit_context,
        inferred_context=inferred_user_context,
    )
    pre_intent = {
        "raw_query": text,
        "ticker": symbol,
        "horizons": horizons,
        "focus_areas": focus_areas,
        "specific_questions": specific_questions,
        "user_context": merged_user_context,
    }
    analyze_req = main_api.AnalyzeRequest(
        symbol=symbol,
        trade_date=trade_date or main_api.cn_today_str(),
        selected_analysts=body.selected_analysts,
        config_overrides=body.config_overrides,
        dry_run=body.dry_run,
        query=text,
        horizons=horizons,
        user_intent=pre_intent,
        objective=merged_user_context.get("objective"),
        risk_profile=merged_user_context.get("risk_profile"),
        investment_horizon=merged_user_context.get("investment_horizon"),
        cash_available=merged_user_context.get("cash_available"),
        current_position=merged_user_context.get("current_position"),
        current_position_pct=merged_user_context.get("current_position_pct"),
        average_cost=merged_user_context.get("average_cost"),
        max_loss_pct=merged_user_context.get("max_loss_pct"),
        constraints=merged_user_context.get("constraints", []),
        user_notes=merged_user_context.get("user_notes"),
    )

    job_id = uuid4().hex
    now = main_api._utcnow_iso()
    main_api.analysis_job_service.upsert_job_row(
        db,
        job_id,
        user_id=current_user.id,
        symbol=analyze_req.symbol,
        trade_date=analyze_req.trade_date,
        status="pending",
        request_payload=analyze_req.model_dump(mode="json"),
        request_source="chat_submit",
        dry_run=analyze_req.dry_run,
    )
    main_api._set_job(
        job_id,
        job_id=job_id,
        user_id=current_user.id,
        status="pending",
        created_at=now,
        started_at=None,
        finished_at=None,
        symbol=analyze_req.symbol,
        trade_date=analyze_req.trade_date,
        error=None,
        result=None,
        decision=None,
    )
    main_api._emit_job_event(
        job_id,
        "job.created",
        {"job_id": job_id, "symbol": analyze_req.symbol, "trade_date": analyze_req.trade_date},
    )

    queue_status, waiting_ahead_count = await main_api._enqueue_or_start_job(
        job_id,
        analyze_req,
        user_id=current_user.id,
        request_source="chat_submit",
    )
    task_label = _build_task_label(analyze_req.symbol, analyze_req.trade_date)
    if queue_status == "queued":
        return TaskSubmitResponse(
            job_id=job_id,
            status="queued",
            symbol=analyze_req.symbol,
            trade_date=analyze_req.trade_date,
            task_label=task_label,
            waiting_ahead_count=max(0, int(waiting_ahead_count or 0)),
            message="任务已进入排队队列。",
        )
    if queue_status == "rejected":
        return TaskSubmitResponse(
            job_id=job_id,
            status="failed",
            symbol=analyze_req.symbol,
            trade_date=analyze_req.trade_date,
            task_label=task_label,
            waiting_ahead_count=max(0, int(waiting_ahead_count or 0)),
            message=f"排队已满（最多 {task_queue_service.max_queue_size()} 个），请在任务中心处理后再提交。",
        )

    main_api._create_tracked_task(
        main_api._run_job(job_id, analyze_req, True, True, current_user.id, "chat_submit"),
        label="Task submit run_job",
    )
    return TaskSubmitResponse(
        job_id=job_id,
        status="pending",
        symbol=analyze_req.symbol,
        trade_date=analyze_req.trade_date,
        task_label=task_label,
        waiting_ahead_count=0,
        message="任务已开始执行。",
    )


@router.patch("/reorder", response_model=TaskOperationResponse)
def reorder_my_tasks(
    body: TaskReorderRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
) -> TaskOperationResponse:
    try:
        task_queue_service.reorder_queue(db, current_user.id, body.job_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    task_queue_service.request_schedule(current_user.id)
    first_job_id = body.job_ids[0] if body.job_ids else ""
    return TaskOperationResponse(ok=True, job_id=first_job_id, status="reordered")


@router.post("/{job_id}/pause", response_model=TaskOperationResponse)
def pause_queued_task(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
) -> TaskOperationResponse:
    row = task_queue_service.set_queue_status(
        db,
        current_user.id,
        job_id,
        queue_status=task_queue_service.QUEUE_STATUS_PAUSED,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="queued task not found")
    task_queue_service.set_analysis_job_status(db, job_id, status="paused")
    return TaskOperationResponse(ok=True, job_id=job_id, status="paused")


@router.post("/{job_id}/resume", response_model=TaskOperationResponse)
def resume_queued_task(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
) -> TaskOperationResponse:
    row = task_queue_service.set_queue_status(
        db,
        current_user.id,
        job_id,
        queue_status=task_queue_service.QUEUE_STATUS_QUEUED,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="queued task not found")
    task_queue_service.set_analysis_job_status(db, job_id, status="queued")
    task_queue_service.request_schedule(current_user.id)
    return TaskOperationResponse(ok=True, job_id=job_id, status="queued")


@router.delete("/{job_id}", response_model=TaskOperationResponse)
def cancel_queued_task(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
) -> TaskOperationResponse:
    removed = task_queue_service.remove_queued_job(db, user_id=current_user.id, job_id=job_id)
    if not removed:
        raise HTTPException(status_code=404, detail="queued task not found")
    task_queue_service.request_schedule(current_user.id)
    return TaskOperationResponse(ok=True, job_id=job_id, status="cancelled")


@router.delete("/{job_id}/record", response_model=TaskOperationResponse)
def delete_task_record(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
) -> TaskOperationResponse:
    row = (
        db.query(AnalysisJobDB)
        .filter(AnalysisJobDB.id == job_id, AnalysisJobDB.user_id == current_user.id)
        .first()
    )
    if row and str(row.status or "") in task_queue_service.ACTIVE_RUNNING_STATUSES:
        raise HTTPException(status_code=409, detail="job is still running, stop first")

    removed_queue = task_queue_service.remove_queued_job(
        db,
        user_id=current_user.id,
        job_id=job_id,
        cancel_error="用户已删除任务",
    )
    if not row and not removed_queue:
        raise HTTPException(status_code=404, detail="task not found")

    # 清理事件日志与持久元数据；运行中任务需先停止后再删除。
    db.query(JobEventDB).filter(JobEventDB.job_id == job_id).delete(synchronize_session=False)
    if row is not None:
        db.delete(row)
    db.commit()

    try:
        from api import main as main_api

        main_api.get_job_store().delete_job(job_id)
    except Exception:
        # Best effort: no-op for store backends that do not keep the key.
        pass

    return TaskOperationResponse(ok=True, job_id=job_id, status="deleted")
