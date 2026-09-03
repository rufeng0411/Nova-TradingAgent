from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.database import FastAnalysisDB, UserDB, get_db, get_db_ctx
from api.deps import require_fast_analysis
from api.schemas.fast_analysis import (
    FastAnalysisDetailResponse,
    FastAnalyzeRequest,
    FastAnalyzeResponse,
    FastRiskProfileResponse,
)
from api.services.fast_analysis_service import (
    create_fast_analysis_job,
    fast_enabled,
    get_user_risk_profile,
    list_recent_fast_analyses,
    run_fast_analysis_job,
    set_user_risk_profile,
)

router = APIRouter(prefix="/v1", tags=["fast-analysis"])


def _to_iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def _detail(row: FastAnalysisDB) -> FastAnalysisDetailResponse:
    sn = (getattr(row, "symbol_name", None) or "").strip() or None
    return FastAnalysisDetailResponse(
        id=row.id,
        status=row.status,
        symbol=row.symbol,
        symbol_name=sn,
        trade_date=row.trade_date,
        created_at=_to_iso(row.created_at),
        finished_at=_to_iso(row.finished_at),
        elapsed_ms=row.elapsed_ms,
        request_context_json=dict(row.request_context_json or {}),
        snapshot_json=dict(row.snapshot_json or {}),
        features_json=dict(row.features_json or {}),
        kline_features_json=dict(row.kline_features_json or {}),
        verdict_json=dict(row.verdict_json or {}),
        time_phased_json=dict(row.time_phased_json or {}),
        position_advice_json=dict(row.position_advice_json or {}),
        executability_json=dict(row.executability_json or {}),
        kline_insight_json=dict(row.kline_insight_json or {}),
    )


@router.post("/analyze/fast", response_model=FastAnalyzeResponse)
async def analyze_fast(
    body: FastAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_fast_analysis),
) -> FastAnalyzeResponse:
    if not fast_enabled():
        raise HTTPException(status_code=503, detail="fast_analysis_disabled")
    payload = body.model_dump(mode="json")
    payload["trade_date"] = datetime.now().strftime("%Y-%m-%d")
    job_id, fast_id, status, waiting = create_fast_analysis_job(
        db,
        user_id=current_user.id,
        symbol=body.symbol,
        request_payload=payload,
        request_source="api_fast",
    )
    if status == "pending":
        asyncio.create_task(run_fast_analysis_job(job_id, current_user.id, {**payload, "fast_analysis_id": fast_id}))
    if status == "rejected":
        raise HTTPException(status_code=409, detail=f"排队已满（{waiting}）")
    return FastAnalyzeResponse(fast_analysis_id=fast_id, job_id=job_id, status="queued" if status == "queued" else "running")


@router.get("/fast-analyses/recent")
def get_recent_fast_analyses(
    symbol: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_fast_analysis),
):
    rows = list_recent_fast_analyses(db, current_user.id, symbol=symbol, limit=limit)
    return {"items": [_detail(r).model_dump(mode="json") for r in rows]}


@router.get("/fast-analyses/{fast_id}", response_model=FastAnalysisDetailResponse)
def get_fast_analysis(
    fast_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_fast_analysis),
) -> FastAnalysisDetailResponse:
    fid = str(fast_id)
    row = db.query(FastAnalysisDB).filter(FastAnalysisDB.id == fid, FastAnalysisDB.user_id == current_user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return _detail(row)


@router.get("/fast-analyses/{fast_id}/events")
async def fast_analysis_events(
    fast_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_fast_analysis),
):
    fid = str(fast_id)
    row = db.query(FastAnalysisDB).filter(FastAnalysisDB.id == fid, FastAnalysisDB.user_id == current_user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    async def _stream() -> AsyncIterator[str]:
        sent = None
        while True:
            with get_db_ctx() as s:
                latest = s.query(FastAnalysisDB).filter(FastAnalysisDB.id == fid).first()
            if not latest:
                break
            payload = {
                "id": latest.id,
                "status": latest.status,
                "stage": (latest.snapshot_json or {}).get("stage"),
                "elapsed_ms": latest.elapsed_ms,
                "updated_at": _to_iso(latest.updated_at),
            }
            mark = json.dumps(payload, ensure_ascii=False)
            if mark != sent:
                sent = mark
                yield f"event: fast.progress\ndata: {mark}\n\n"
            if latest.status in ("succeeded", "degraded", "failed"):
                yield f"event: fast.done\ndata: {mark}\n\n"
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/user/risk-profile", response_model=FastRiskProfileResponse)
def get_risk_profile(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_fast_analysis),
) -> FastRiskProfileResponse:
    risk_profile, fast_model = get_user_risk_profile(db, current_user.id)
    return FastRiskProfileResponse(risk_profile=risk_profile, fast_model=fast_model)


@router.put("/user/risk-profile", response_model=FastRiskProfileResponse)
def put_risk_profile(
    body: FastRiskProfileResponse,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(require_fast_analysis),
) -> FastRiskProfileResponse:
    risk_profile, fast_model = set_user_risk_profile(db, current_user.id, body.risk_profile, body.fast_model)
    return FastRiskProfileResponse(risk_profile=risk_profile, fast_model=fast_model)

