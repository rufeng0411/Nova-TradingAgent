"""Admin ops: tasks (reports-backed), usage records, AI call logs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from api.database import (
    AiCallLogDB,
    FastAnalysisDB,
    MarketDataDailyBarDB,
    MarketDataReconAnomalyDB,
    MarketDataVendorCallLogDB,
    ReportDB,
    UsageRecordDB,
)


def list_tasks(
    db: Session,
    *,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[ReportDB], int]:
    q = db.query(ReportDB)
    if user_id:
        q = q.filter(ReportDB.user_id == user_id)
    if status:
        q = q.filter(ReportDB.status == status)
    total = q.count()
    rows = q.order_by(ReportDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def report_task_dict(r: ReportDB) -> Dict[str, Any]:
    return {
        "id": r.id,
        "kind": "analysis",
        "user_id": r.user_id,
        "symbol": r.symbol,
        "status": r.status or "completed",
        "error": (r.error or "")[:500] if r.error else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def list_usage_records(
    db: Session, *, user_id: Optional[str], page: int, page_size: int
) -> Tuple[List[UsageRecordDB], int]:
    q = db.query(UsageRecordDB)
    if user_id:
        q = q.filter(UsageRecordDB.user_id == user_id)
    total = q.count()
    rows = q.order_by(UsageRecordDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def usage_dict(u: UsageRecordDB) -> Dict[str, Any]:
    return {
        "id": u.id,
        "user_id": u.user_id,
        "task_id": u.task_id,
        "report_id": u.report_id,
        "credits_reserved": u.credits_reserved,
        "credits_consumed": u.credits_consumed,
        "tokens_prompt": u.tokens_prompt,
        "tokens_completion": u.tokens_completion,
        "cost_cents_estimated": u.cost_cents_estimated,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def list_ai_calls(
    db: Session, *, user_id: Optional[str], page: int, page_size: int
) -> Tuple[List[AiCallLogDB], int]:
    q = db.query(AiCallLogDB)
    if user_id:
        q = q.filter(AiCallLogDB.user_id == user_id)
    total = q.count()
    rows = q.order_by(AiCallLogDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def ai_call_dict(a: AiCallLogDB) -> Dict[str, Any]:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "task_id": a.task_id,
        "provider": a.provider,
        "model": a.model,
        "purpose": a.purpose,
        "prompt_tokens": a.prompt_tokens,
        "completion_tokens": a.completion_tokens,
        "latency_ms": a.latency_ms,
        "status": a.status,
        "error_code": a.error_code,
        "prompt_preview": a.prompt_preview,
        "response_preview": a.response_preview,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def vendor_stats(db: Session, *, days: int = 7) -> list[Dict[str, Any]]:
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    rows = (
        db.query(
            MarketDataVendorCallLogDB.method,
            MarketDataVendorCallLogDB.vendor,
            func.count().label("calls"),
            func.avg(MarketDataVendorCallLogDB.latency_ms).label("avg_latency_ms"),
            func.sum(case((MarketDataVendorCallLogDB.status == "hit", 1), else_=0)).label(
                "hit_count"
            ),
        )
        .filter(MarketDataVendorCallLogDB.created_at >= cutoff)
        .group_by(MarketDataVendorCallLogDB.method, MarketDataVendorCallLogDB.vendor)
        .order_by(func.count().desc())
        .all()
    )
    items = []
    for r in rows:
        calls = int(r.calls or 0)
        hit_count = int(r.hit_count or 0)
        items.append(
            {
                "method": r.method,
                "vendor": r.vendor,
                "calls": calls,
                "success_rate": round(hit_count / calls, 4) if calls else 0.0,
                "avg_latency_ms": round(float(r.avg_latency_ms or 0), 2),
            }
        )
    return items


def recon_anomalies(db: Session, *, trade_date: Optional[str] = None, limit: int = 200) -> list[Dict[str, Any]]:
    q = db.query(MarketDataReconAnomalyDB)
    if trade_date:
        q = q.filter(MarketDataReconAnomalyDB.trade_date == trade_date)
    rows = q.order_by(MarketDataReconAnomalyDB.created_at.desc()).limit(max(1, min(limit, 1000))).all()
    return [
        {
            "id": r.id,
            "trade_date": r.trade_date.isoformat() if r.trade_date else None,
            "symbol": r.symbol,
            "field": r.field,
            "value_primary": float(r.value_primary) if r.value_primary is not None else None,
            "value_secondary": float(r.value_secondary) if r.value_secondary is not None else None,
            "diff_ratio": float(r.diff_ratio) if r.diff_ratio is not None else None,
            "severity": r.severity,
            "source_primary": r.source_primary,
            "source_secondary": r.source_secondary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def sync_status(db: Session) -> Dict[str, Any]:
    latest_vendor_log = (
        db.query(MarketDataVendorCallLogDB)
        .order_by(MarketDataVendorCallLogDB.created_at.desc())
        .first()
    )
    latest_anomaly = (
        db.query(MarketDataReconAnomalyDB)
        .order_by(MarketDataReconAnomalyDB.created_at.desc())
        .first()
    )
    return {
        "latest_vendor_call_at": latest_vendor_log.created_at.isoformat()
        if latest_vendor_log and latest_vendor_log.created_at
        else None,
        "latest_recon_anomaly_at": latest_anomaly.created_at.isoformat()
        if latest_anomaly and latest_anomaly.created_at
        else None,
        "daily_bar_rows": db.query(MarketDataDailyBarDB).count(),
        "vendor_log_rows": db.query(MarketDataVendorCallLogDB).count(),
        "recon_anomaly_rows": db.query(MarketDataReconAnomalyDB).count(),
    }


def fast_analysis_metrics(db: Session, *, days: int = 7) -> Dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    rows = db.query(FastAnalysisDB).filter(FastAnalysisDB.created_at >= cutoff).all()
    total = len(rows)
    succeeded = sum(1 for r in rows if r.status == "succeeded")
    degraded = sum(1 for r in rows if r.status == "degraded")
    failed = sum(1 for r in rows if r.status == "failed")
    elapsed = [int(r.elapsed_ms or 0) for r in rows if r.elapsed_ms]
    model_counts: Dict[str, int] = {}
    for r in rows:
        key = str(r.model_name or "unknown")
        model_counts[key] = model_counts.get(key, 0) + 1
    return {
        "days": max(1, days),
        "total": total,
        "succeeded": succeeded,
        "degraded": degraded,
        "failed": failed,
        "avg_elapsed_ms": (sum(elapsed) / len(elapsed)) if elapsed else 0,
        "p95_elapsed_ms": sorted(elapsed)[int(len(elapsed) * 0.95) - 1] if elapsed else 0,
        "model_distribution": model_counts,
    }
