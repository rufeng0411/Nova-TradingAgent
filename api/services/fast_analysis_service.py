from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import desc
from sqlalchemy.orm import Session

from api.database import AnalysisJobDB, FastAnalysisDB, ImportedPortfolioPositionDB, ReportDB, UserPreferenceDB, get_db_ctx
from api.services import (
    analysis_job_service,
    auth_service,
    credits_service,
    report_outcome_service,
    report_service,
    symbol_service,
    task_queue_service,
)
from api.symbol_utils import normalize_exchange_symbol
from tradingagents.dataflows.trade_calendar import cn_today_str
from tradingagents.fastline.data_snapshot import SOURCE_LABELS, collect_snapshot
from tradingagents.fastline.fast_analyst import run_fast_analyst
from tradingagents.fastline.json_safe import json_safe
from tradingagents.fastline.feature_extractor import FAST_FEATURE_SLOT_COUNT, extract_fast_features
from tradingagents.fastline.risk_profile import get_risk_profile_rule, normalize_risk_profile

STAGES = [
    ("queued", "排队等待", 0, 5),
    ("collecting_data", "数据快照", 5, 50),
    ("extracting_features", "特征抽取", 50, 60),
    ("llm_reasoning", "AI 推断", 60, 95),
    ("finalizing", "结果落库", 95, 100),
]
STAGE_LABEL = {k: l for k, l, _, _ in STAGES}
STAGE_LOW = {k: lo for k, _, lo, _ in STAGES}
STAGE_HIGH = {k: hi for k, _, _, hi in STAGES}

# Dedicated single-thread executor for progress DB writes so they cannot
# starve the default asyncio executor (which FastAPI also uses for sync
# endpoints like /login, /reports). Coalesces concurrent updates per fast_id.
_PROGRESS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fast-progress")
_PROGRESS_BUFFER: dict[str, dict[str, Any]] = {}
_PROGRESS_BUFFER_LOCK = threading.Lock()
_PROGRESS_LAST_FLUSH: dict[str, float] = {}
_PROGRESS_MIN_INTERVAL_SEC = 0.25  # at most ~4 commits/sec per fast_id

# 与 _flush_progress_db（线程池）之间串行化 snapshot_json 的读改写，避免最终带 sources 的快照
# 被「先读后写」的进度刷新用旧行覆盖，导致前端只能走 progress 摘要、数据源明细为空。
_FAST_SNAPSHOT_JSON_LOCK = threading.Lock()

logger = logging.getLogger(__name__)

FAST_TASK_KIND = "fast_analysis"


def _fast_direction_to_decision(raw: str) -> tuple[str, str]:
    """(direction_cn, decision) for ReportDB / 历史列表。"""
    s = (raw or "").strip().lower()
    if s in ("bull", "long", "buy", "long_bias", "多", "看多"):
        return "偏多", "BUY"
    if s in ("bear", "short", "sell", "short_bias", "空", "看空"):
        return "偏空", "SELL"
    return "中性", "HOLD"


def _verdict_confidence_pct(conf: Any) -> int | None:
    if conf is None:
        return None
    try:
        c = int(float(conf))
    except (TypeError, ValueError):
        return None
    if 1 <= c <= 5:
        return min(100, max(0, c * 20))
    if 0 <= c <= 100:
        return c
    return None


def _sync_fast_report_row(
    db: Session,
    *,
    job_id: str,
    user_id: str,
    symbol: str,
    trade_date: str,
    fast_id: str,
    status: str,
    error: str | None = None,
    result: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> None:
    """同步 reports 行：/v1/reports 以 ReportDB 为主表，仅 Job 无 Report 时快速分析不会出现在历史列表。"""
    sym = normalize_exchange_symbol(str(symbol or "")).strip().upper()
    td = str(trade_date or cn_today_str()).strip()
    release_version = str(os.getenv("TA_RELEASE_VERSION") or "dev").strip() or "dev"
    if db.query(ReportDB).filter(ReportDB.id == job_id).first() is None:
        report_service.init_report(db, job_id, sym, td, user_id)

    err_clip = (error or "").strip()
    if len(err_clip) > 4000:
        err_clip = err_clip[:3997] + "…"

    if status == "failed":
        report_service.update_report_partial(
            db,
            job_id,
            status="failed",
            error=err_clip or "快速分析失败",
            release_version=release_version,
            result_data=json_safe({"task_kind": FAST_TASK_KIND, "fast_analysis_id": fast_id}),
        )
        return

    res = result or {}
    vd = dict(res.get("verdict") or {})
    raw_dir = str(vd.get("direction") or "neutral")
    reason = str(vd.get("reason") or "").strip() or "（模型未给出文字结论，请以 VERDICT 方向为准）"
    dir_cn, decision = _fast_direction_to_decision(raw_dir)
    confidence_pct = _verdict_confidence_pct(vd.get("confidence"))

    verdict_payload = json.dumps({"direction": dir_cn, "reason": reason}, ensure_ascii=False)
    final_md = f"<!-- VERDICT: {verdict_payload} -->\n\n## 快速分析结论\n\n{reason}\n"

    result_data: dict[str, Any] = {
        "task_kind": FAST_TASK_KIND,
        "fast_analysis_id": fast_id,
        "data_completeness": float((snapshot or {}).get("data_completeness") or 0.0),
    }

    data_sources_json = None
    try:
        if snapshot and isinstance(snapshot.get("sources"), dict):
            data_sources_json = json_safe({"sources": snapshot.get("sources"), "trade_date": td})
    except Exception:
        data_sources_json = None

    report_service.update_report_partial(
        db,
        job_id,
        status="completed",
        decision=decision,
        direction=dir_cn,
        confidence=confidence_pct,
        final_trade_decision=final_md,
        release_version=release_version,
        result_data=json_safe(result_data),
        data_sources_json=data_sources_json,
    )


def _resolve_llm_config(db: Session, user_id: str, model_override: str | None) -> dict[str, Any]:
    """Build LLM config: user DB overrides > env defaults.

    Mirrors the resolution used by /v1/analyze and chart insight so the user's
    saved Settings (provider/base_url/api_key/model) are honored.
    """
    cfg: dict[str, Any] = {
        "llm_provider": (os.getenv("TA_LLM_PROVIDER") or "openai").strip(),
        "backend_url": (os.getenv("TA_BASE_URL") or "").strip() or None,
        "api_key": (os.getenv("TA_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip() or None,
        "quick_think_llm": (os.getenv("TA_LLM_QUICK") or "").strip() or None,
        "deep_think_llm": (os.getenv("TA_LLM_DEEP") or "").strip() or None,
    }
    try:
        user_cfg = auth_service.get_user_llm_config(db, user_id)
    except Exception:
        user_cfg = None
    if user_cfg is not None:
        for key in ("llm_provider", "backend_url", "quick_think_llm", "deep_think_llm"):
            val = getattr(user_cfg, key, None)
            if val not in (None, ""):
                cfg[key] = val
        try:
            api_key = auth_service.decrypt_secret(getattr(user_cfg, "api_key_encrypted", None))
        except Exception:
            api_key = None
        if api_key:
            cfg["api_key"] = api_key

    model_env = (os.getenv("TA_FAST_LLM_MODEL") or "").strip()
    chosen_model = (
        (model_override or "").strip()
        or model_env
        or str(cfg.get("quick_think_llm") or "").strip()
        or str(cfg.get("deep_think_llm") or "").strip()
        or "gpt-4o-mini"
    )
    cfg["fast_model"] = chosen_model
    return cfg


def fast_enabled() -> bool:
    return os.getenv("TA_FAST_ANALYSIS_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def fast_cost_points() -> int:
    try:
        return max(0, int(os.getenv("TA_FAST_COST_POINTS", "2")))
    except Exception:
        return 2


def fast_budget_sec() -> int:
    try:
        return max(30, int(os.getenv("TA_FAST_BUDGET_SEC", "120")))
    except Exception:
        return 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def _load_user_position(db: Session, user_id: str, symbol: str) -> dict[str, Any] | None:
    row = (
        db.query(ImportedPortfolioPositionDB)
        .filter(ImportedPortfolioPositionDB.user_id == user_id, ImportedPortfolioPositionDB.symbol == symbol)
        .order_by(desc(ImportedPortfolioPositionDB.updated_at))
        .first()
    )
    if not row:
        return None
    return {
        "shares": row.current_position,
        "avg_cost": row.average_cost,
        "portfolio_pct": row.current_position_pct,
        "available_cash_pct": None,
    }


def _get_or_init_user_pref(db: Session, user_id: str) -> UserPreferenceDB:
    row = db.query(UserPreferenceDB).filter(UserPreferenceDB.user_id == user_id).first()
    if row is None:
        row = UserPreferenceDB(user_id=user_id, risk_profile="balanced")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_user_risk_profile(db: Session, user_id: str) -> tuple[str, Optional[str]]:
    row = _get_or_init_user_pref(db, user_id)
    return normalize_risk_profile(row.risk_profile), row.fast_model


def set_user_risk_profile(db: Session, user_id: str, risk_profile: str, fast_model: str | None) -> tuple[str, Optional[str]]:
    row = _get_or_init_user_pref(db, user_id)
    row.risk_profile = normalize_risk_profile(risk_profile)
    if fast_model is not None:
        row.fast_model = str(fast_model).strip() or None
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return normalize_risk_profile(row.risk_profile), row.fast_model


def _find_existing_fast_job(db: Session, user_id: str, symbol: str) -> tuple[str, str] | None:
    rows = (
        db.query(AnalysisJobDB)
        .filter(
            AnalysisJobDB.user_id == user_id,
            AnalysisJobDB.symbol == symbol,
            AnalysisJobDB.status.in_(("queued", "pending", "running", "resuming")),
        )
        .order_by(AnalysisJobDB.created_at.desc())
        .all()
    )
    for row in rows:
        payload = dict(row.request_payload or {})
        if payload.get("task_kind") == FAST_TASK_KIND:
            return row.id, str(payload.get("fast_analysis_id") or "")
    return None


def _persist_fast_job_row(
    db: Session,
    *,
    user_id: str,
    symbol: str,
    request_payload: dict[str, Any],
    request_source: str,
) -> tuple[str, str]:
    job_id = uuid4().hex
    fast_id = str(uuid4())
    now = _utcnow()
    analysis_job_service.upsert_job_row(
        db,
        job_id,
        user_id=user_id,
        symbol=symbol,
        trade_date=request_payload.get("trade_date"),
        status="pending",
        request_payload={**request_payload, "task_kind": FAST_TASK_KIND, "fast_analysis_id": fast_id},
        request_source=request_source,
        dry_run=False,
    )
    td0 = str(request_payload.get("trade_date") or cn_today_str())
    report_service.init_report(db, job_id, symbol, td0, user_id)
    initial_progress = _new_progress(symbol, str(request_payload.get("intent_hint") or ""))
    row = FastAnalysisDB(
        id=fast_id,
        user_id=user_id,
        symbol=symbol,
        symbol_name=symbol_service.resolve_cn_display_name(symbol),
        trade_date=str(request_payload.get("trade_date") or cn_today_str()),
        job_id=job_id,
        status="running",
        triggered_at=now,
        created_at=now,
        updated_at=now,
        request_context_json=request_payload,
        snapshot_json={"stage": "queued", "progress": initial_progress},
        disclaimer_version="v1",
    )
    db.add(row)
    with _FAST_SNAPSHOT_JSON_LOCK:
        db.commit()
    return job_id, fast_id


def create_fast_analysis_job(
    db: Session,
    *,
    user_id: str,
    symbol: str,
    request_payload: dict[str, Any],
    request_source: str = "api_fast",
) -> tuple[str, str, str, int]:
    symbol = normalize_exchange_symbol(symbol).upper()
    existing = _find_existing_fast_job(db, user_id, symbol)
    if existing:
        job_id, fast_id = existing
        row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
        return job_id, fast_id, str(getattr(row, "status", "queued")), 0

    request_payload = dict(request_payload)
    request_payload["symbol"] = symbol
    request_payload["trade_date"] = str(request_payload.get("trade_date") or cn_today_str())
    request_payload["task_kind"] = FAST_TASK_KIND
    job_id, fast_id = _persist_fast_job_row(
        db,
        user_id=user_id,
        symbol=symbol,
        request_payload=request_payload,
        request_source=request_source,
    )

    should_queue = (
        task_queue_service.is_queue_enabled()
        and (
            task_queue_service.has_active_running_job(db, user_id, exclude_job_id=job_id)
            or task_queue_service.has_pending_queue_items(db, user_id)
        )
    )
    if should_queue:
        if task_queue_service.queue_size(db, user_id) >= task_queue_service.max_queue_size():
            task_queue_service.set_analysis_job_status(db, job_id, status="failed", error="排队已满")
            row = db.query(FastAnalysisDB).filter(FastAnalysisDB.id == fast_id).first()
            if row:
                row.status = "failed"
                with _FAST_SNAPSHOT_JSON_LOCK:
                    row.snapshot_json = {"stage": "queue_rejected"}
                    row.updated_at = _utcnow()
                    db.commit()
            report_service.update_report_partial(
                db,
                job_id,
                status="failed",
                error="排队已满",
                result_data=json_safe({"task_kind": FAST_TASK_KIND, "fast_analysis_id": fast_id}),
            )
            return job_id, fast_id, "rejected", task_queue_service.max_queue_size()
        task_queue_service.enqueue_job(
            db,
            user_id=user_id,
            job_id=job_id,
            task_kind=FAST_TASK_KIND,
            title=f"⚡ 快速分析 {symbol}",
            description=str(request_payload.get("intent_hint") or "")[:200] or "快速分析任务",
            symbol=symbol,
            trade_date=request_payload["trade_date"],
            queue_status=task_queue_service.QUEUE_STATUS_QUEUED,
            priority=task_queue_service.PRIORITY_HIGH,
        )
        task_queue_service.set_analysis_job_status(db, job_id, status="queued")
        ahead = task_queue_service.waiting_ahead_count(db, user_id, job_id)
        row = db.query(FastAnalysisDB).filter(FastAnalysisDB.id == fast_id).first()
        if row:
            payload = dict(row.snapshot_json or {})
            progress = dict(payload.get("progress") or _new_progress(symbol, str(request_payload.get("intent_hint") or "")))
            progress.update({
                "stage": "queued",
                "stage_label": STAGE_LABEL["queued"],
                "percent": STAGE_LOW["queued"],
                "waiting_ahead_count": ahead,
            })
            _append_log(progress, f"已加入队列（前方 {ahead} 个任务）")
            payload["progress"] = progress
            payload["stage"] = "queued"
            payload["waiting_ahead_count"] = ahead
            with _FAST_SNAPSHOT_JSON_LOCK:
                row.snapshot_json = payload
                row.updated_at = _utcnow()
                db.commit()
        task_queue_service.request_schedule(user_id)
        return job_id, fast_id, "queued", ahead
    return job_id, fast_id, "pending", 0


def _new_progress(symbol: str, intent_hint: str | None) -> dict[str, Any]:
    now_iso = _utcnow().isoformat()
    return {
        "stage": "queued",
        "stage_label": STAGE_LABEL["queued"],
        "percent": STAGE_LOW["queued"],
        "started_at": now_iso,
        "updated_at": now_iso,
        "symbol": symbol,
        "intent_hint": intent_hint or "",
        "sources_total": 0,
        "sources_done": 0,
        "sources": [],
        "logs": [{"ts": now_iso, "level": "info", "msg": "任务已派发，等待开始"}],
        "feature_count": 0,
        "expected_features": FAST_FEATURE_SLOT_COUNT,
        "llm_model": None,
        "llm_provider": None,
        "elapsed_ms": 0,
    }


def _append_log(progress: dict[str, Any], msg: str, level: str = "info") -> None:
    logs = list(progress.get("logs") or [])
    logs.append({"ts": _utcnow().isoformat(), "level": level, "msg": msg})
    progress["logs"] = logs[-40:]


def _flush_progress_db(fast_id: str) -> None:
    """Write the buffered progress for fast_id to DB. Runs on the dedicated executor.

    Uses one short-lived session. Errors are logged but never raised so they cannot
    cascade into the fast-analysis pipeline or starve the default thread pool.
    """
    with _PROGRESS_BUFFER_LOCK:
        progress = _PROGRESS_BUFFER.get(fast_id)
        if progress is None:
            return
        # Take a shallow copy so subsequent mutations don't race with the commit below.
        snapshot_progress = dict(progress)
        snapshot_progress["logs"] = list(snapshot_progress.get("logs") or [])
        snapshot_progress["sources"] = list(snapshot_progress.get("sources") or [])
        _PROGRESS_LAST_FLUSH[fast_id] = time.monotonic()
    try:
        with _FAST_SNAPSHOT_JSON_LOCK:
            with get_db_ctx() as db:
                row = db.query(FastAnalysisDB).filter(FastAnalysisDB.id == fast_id).first()
                if not row:
                    return
                payload = dict(row.snapshot_json or {})
                payload["progress"] = snapshot_progress
                payload["stage"] = snapshot_progress.get("stage")
                row.snapshot_json = payload
                row.updated_at = _utcnow()
                db.commit()
    except Exception as exc:
        logger.warning("[fast] flush progress DB failed fast_id=%s: %s", fast_id, exc)


def _schedule_flush(fast_id: str, *, force: bool = False) -> None:
    now = time.monotonic()
    last = _PROGRESS_LAST_FLUSH.get(fast_id, 0.0)
    if not force and (now - last) < _PROGRESS_MIN_INTERVAL_SEC:
        return
    _PROGRESS_LAST_FLUSH[fast_id] = now
    try:
        _PROGRESS_EXECUTOR.submit(_flush_progress_db, fast_id)
    except RuntimeError:
        # Executor shut down (test teardown / app exit); skip silently.
        pass


def _mutate_progress(fast_id: str, mutator, *, force_flush: bool = False) -> None:
    with _PROGRESS_BUFFER_LOCK:
        progress = _PROGRESS_BUFFER.get(fast_id)
        if progress is None:
            progress = _new_progress("", "")
            _PROGRESS_BUFFER[fast_id] = progress
        mutator(progress)
        progress["updated_at"] = _utcnow().isoformat()
    _schedule_flush(fast_id, force=force_flush)


def _init_progress_buffer(fast_id: str, base: dict[str, Any]) -> None:
    with _PROGRESS_BUFFER_LOCK:
        _PROGRESS_BUFFER[fast_id] = dict(base)
    _PROGRESS_LAST_FLUSH[fast_id] = 0.0


def _drop_progress_buffer(fast_id: str) -> None:
    with _PROGRESS_BUFFER_LOCK:
        _PROGRESS_BUFFER.pop(fast_id, None)
    _PROGRESS_LAST_FLUSH.pop(fast_id, None)


def _set_stage(db: Session, fast_id: str, stage: str, *, percent: int | None = None, msg: str | None = None, extra: Optional[dict[str, Any]] = None) -> None:
    del db  # the dedicated executor owns DB writes for progress updates
    def _mutate(progress: dict[str, Any]) -> None:
        progress["stage"] = stage
        progress["stage_label"] = STAGE_LABEL.get(stage, stage)
        if percent is not None:
            progress["percent"] = max(progress.get("percent") or 0, int(percent))
        else:
            progress["percent"] = max(progress.get("percent") or 0, STAGE_LOW.get(stage, 0))
        if extra:
            progress.update(extra)
        if msg:
            _append_log(progress, msg)

    _mutate_progress(fast_id, _mutate, force_flush=True)
    logger.info("[fast] stage=%s fast_id=%s extra=%s", stage, fast_id, extra)


async def run_fast_analysis_job(job_id: str, user_id: str, request_payload: dict[str, Any]) -> None:
    fast_id = str(request_payload.get("fast_analysis_id") or "")
    symbol = normalize_exchange_symbol(str(request_payload.get("symbol") or "")).upper()
    started = time.perf_counter()
    points = fast_cost_points()
    logger.info("[fast] start job_id=%s user_id=%s symbol=%s fast_id=%s", job_id, user_id, symbol, fast_id)
    # Hydrate the in-memory progress buffer from the row created at submit time so that
    # logs/sources persist across stages without needing a DB round-trip per mutation.
    try:
        with get_db_ctx() as db:
            existing = db.query(FastAnalysisDB).filter(FastAnalysisDB.id == fast_id).first()
            seed_progress = dict(((existing.snapshot_json or {}).get("progress") or {})) if existing else {}
        if not seed_progress:
            seed_progress = _new_progress(symbol, str(request_payload.get("intent_hint") or ""))
        _init_progress_buffer(fast_id, seed_progress)
    except Exception as exc:
        logger.warning("[fast] init progress buffer failed: %s", exc)
        _init_progress_buffer(fast_id, _new_progress(symbol, str(request_payload.get("intent_hint") or "")))

    with get_db_ctx() as db:
        try:
            credits_service.reserve_for_analysis(db, user_id, job_id, amount=points)
        except Exception as exc:
            logger.warning("[fast] reserve credits failed: %s", exc)
        analysis_job_service.persist_store_fields(db, job_id, {"status": "running", "user_id": user_id, "symbol": symbol})

    snapshot: dict[str, Any] | None = None
    features: dict[str, Any] | None = None
    kline_features: dict[str, Any] | None = None
    runtime_model = ""
    llm_cfg: dict[str, Any] = {}

    try:
        with get_db_ctx() as db:
            _set_stage(
                db,
                fast_id,
                "collecting_data",
                percent=STAGE_LOW["collecting_data"],
                msg=f"开始并行采集 Tushare 快照明细（标的 {symbol}，含日K/日线RT/集合竞价等核心权限数据）",
            )
        trade_date = str(request_payload.get("trade_date") or cn_today_str())

        def _on_progress_sync(label: str, payload: dict[str, Any], done: int, total: int) -> None:
            display = SOURCE_LABELS.get(label, label)
            latency = payload.get("latency_ms") or 0
            status = str(payload.get("status") or "?")
            level = "info" if status == "ok" else "warn"
            data_rows = len(payload.get("data") or []) if isinstance(payload.get("data"), list) else 0
            span = STAGE_HIGH["collecting_data"] - STAGE_LOW["collecting_data"]
            pct = STAGE_LOW["collecting_data"] + int(span * (done / max(1, total)))

            def _mutate(progress: dict[str, Any]) -> None:
                progress["sources_total"] = total
                progress["sources_done"] = done
                sources = list(progress.get("sources") or [])
                idx = next((i for i, s in enumerate(sources) if s.get("key") == label), -1)
                entry = {
                    "key": label,
                    "label": display,
                    "status": status,
                    "latency_ms": latency,
                    "rows": data_rows,
                }
                if idx >= 0:
                    sources[idx] = entry
                else:
                    sources.append(entry)
                progress["sources"] = sources
                progress["percent"] = max(progress.get("percent") or 0, pct)
                _append_log(
                    progress,
                    f"{display} → {status}（{latency}ms，{data_rows} 行）",
                    level=level,
                )

            # IMPORTANT: do not block the event loop / default executor here.
            # The mutation is in-memory; the DB flush is throttled to ≤4/sec and
            # runs on a private executor so it cannot starve FastAPI sync handlers.
            _mutate_progress(fast_id, _mutate, force_flush=(done == total))

        try:
            snapshot = await collect_snapshot(
                symbol,
                trade_date,
                timeout_sec=30.0,
                on_progress=_on_progress_sync,
            )
        except Exception as exc:
            logger.exception("[fast] collect_snapshot failed symbol=%s: %s", symbol, exc)
            raise RuntimeError(f"数据快照采集失败：{type(exc).__name__}: {exc}") from exc
        snapshot = json_safe(snapshot)
        if not isinstance(snapshot, dict):
            snapshot = {}
        logger.info(
            "[fast] snapshot completeness=%.2f elapsed_ms=%s sources=%s",
            float(snapshot.get("data_completeness") or 0.0),
            snapshot.get("elapsed_ms"),
            list((snapshot.get("sources") or {}).keys()),
        )

        with get_db_ctx() as db:
            _set_stage(
                db,
                fast_id,
                "extracting_features",
                percent=STAGE_LOW["extracting_features"],
                msg=f"数据采集完成（完整度 {int(float(snapshot.get('data_completeness') or 0) * 100)}%），开始抽取 {FAST_FEATURE_SLOT_COUNT} 个特征槽位",
            )
            current_position = request_payload.get("current_position") or _load_user_position(db, user_id, symbol)
            rp = request_payload.get("risk_profile")
            if not rp:
                rp, _ = get_user_risk_profile(db, user_id)
            else:
                rp = normalize_risk_profile(str(rp))
            try:
                features, kline_features = extract_fast_features(snapshot, current_position=current_position)
            except Exception as exc:
                logger.exception("[fast] feature extraction failed: %s", exc)
                raise RuntimeError(f"特征抽取失败：{type(exc).__name__}: {exc}") from exc
            features = json_safe(features)
            kline_features = json_safe(kline_features)
            if not isinstance(features, dict):
                features = {}
            if not isinstance(kline_features, dict):
                kline_features = {}
            llm_cfg = _resolve_llm_config(db, user_id, str(request_payload.get("model_override") or ""))
            runtime_model = str(llm_cfg["fast_model"])
            feat_populated = sum(1 for v in (features or {}).values() if v is not None)
            _set_stage(
                db,
                fast_id,
                "llm_reasoning",
                percent=STAGE_LOW["llm_reasoning"],
                msg=f"特征抽取完成（{FAST_FEATURE_SLOT_COUNT} 项槽位已计算，其中 {feat_populated} 项含有效数值），调用模型 {runtime_model}",
                extra={
                    "feature_count": FAST_FEATURE_SLOT_COUNT,
                    "feature_populated_count": feat_populated,
                    "expected_features": FAST_FEATURE_SLOT_COUNT,
                    "llm_model": runtime_model,
                    "llm_provider": llm_cfg.get("llm_provider"),
                },
            )

        llm_payload = {
            "symbol": symbol,
            "trade_date": trade_date,
            "intent_hint": request_payload.get("intent_hint"),
            "risk_profile": rp,
            "risk_rule": get_risk_profile_rule(rp),
            "current_position": current_position,
            "market_context": snapshot.get("sources", {}).get("index_pulse", {}),
            "snapshot": snapshot,
            "features": features,
            "kline_features": kline_features,
            "data_completeness": snapshot.get("data_completeness"),
        }
        logger.info(
            "[fast] LLM invoke provider=%s base_url=%s model=%s",
            llm_cfg.get("llm_provider"),
            llm_cfg.get("backend_url"),
            runtime_model,
        )

        llm_started_at = time.perf_counter()
        llm_task = asyncio.create_task(
            asyncio.to_thread(
                run_fast_analyst,
                llm_provider=str(llm_cfg.get("llm_provider") or "openai"),
                model_name=runtime_model,
                base_url=llm_cfg.get("backend_url"),
                api_key=llm_cfg.get("api_key"),
                payload=llm_payload,
                kline_features=kline_features,
                timeout_sec=55.0,
            )
        )
        # Heartbeat: smoothly advance the percent bar during the (non-streaming) LLM call.
        # Tick every 3s to avoid hammering DB; the actual flush is also throttled to ≤4/sec.
        span = STAGE_HIGH["llm_reasoning"] - STAGE_LOW["llm_reasoning"]
        deadline = float(fast_budget_sec())
        tick = 0
        while not llm_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(llm_task), timeout=3.0)
                break
            except asyncio.TimeoutError:
                tick += 1
                elapsed_llm = time.perf_counter() - llm_started_at
                if elapsed_llm > deadline:
                    llm_task.cancel()
                    raise asyncio.TimeoutError(f"LLM 调用超过 {int(deadline)}s 上限")
                projected = STAGE_LOW["llm_reasoning"] + int(min(span - 1, span * min(0.95, elapsed_llm / 45.0)))

                def _mutate(progress: dict[str, Any], pct=projected, secs=int(elapsed_llm)) -> None:
                    progress["percent"] = max(progress.get("percent") or 0, pct)
                    progress["llm_elapsed_sec"] = secs
                    if tick % 3 == 0:
                        _append_log(progress, f"模型推断中…已耗时 {secs}s")

                _mutate_progress(fast_id, _mutate)
        result = await llm_task
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        llm_error = str(result.get("llm_error") or "").strip()
        completeness = float(snapshot.get("data_completeness") or 0.0)
        if llm_error:
            final_status = "degraded"
        elif completeness >= 0.6:
            final_status = "succeeded"
        else:
            final_status = "degraded"
        with _FAST_SNAPSHOT_JSON_LOCK:
            with get_db_ctx() as db:
                row = db.query(FastAnalysisDB).filter(FastAnalysisDB.id == fast_id).first()
                if row:
                    row.status = final_status
                    row.finished_at = _utcnow()
                    row.elapsed_ms = elapsed_ms
                    row.model_provider = str(llm_cfg.get("llm_provider") or "openai")
                    row.model_name = runtime_model
                    row.cost_credit_points = points
                    snap_payload = dict(snapshot)
                    snap_payload["stage"] = "completed"
                    with _PROGRESS_BUFFER_LOCK:
                        buffered = dict(_PROGRESS_BUFFER.get(fast_id) or {})
                    prev_progress = buffered or dict((row.snapshot_json or {}).get("progress") or {})
                    feat_populated_done = sum(1 for v in (features or {}).values() if v is not None)
                    prev_progress.update(
                        {
                            "stage": "finalizing",
                            "stage_label": STAGE_LABEL["finalizing"],
                            "percent": 100,
                            "elapsed_ms": elapsed_ms,
                            "final_status": final_status,
                            "feature_count": FAST_FEATURE_SLOT_COUNT,
                            "feature_populated_count": feat_populated_done,
                            "expected_features": FAST_FEATURE_SLOT_COUNT,
                            "llm_error": llm_error or None,
                        }
                    )
                    _append_log(
                        prev_progress,
                        f"分析完成（状态 {final_status}，总耗时 {elapsed_ms}ms）",
                        level="info" if final_status == "succeeded" else "warn",
                    )
                    snap_payload["progress"] = prev_progress
                    if llm_error:
                        snap_payload["llm_error"] = llm_error
                    row.snapshot_json = snap_payload
                    row.features_json = features
                    row.kline_features_json = kline_features
                    row.verdict_json = dict(result.get("verdict") or {})
                    row.time_phased_json = dict(result.get("time_phased_strategy") or {})
                    row.position_advice_json = dict(result.get("position_recommendation") or {})
                    row.executability_json = dict(result.get("executability_assessment") or {})
                    row.kline_insight_json = dict(result.get("kline_insight") or {})
                    row.updated_at = _utcnow()
                analysis_job_service.persist_store_fields(
                    db,
                    job_id,
                    {
                        "status": "completed",
                        "decision": str((result.get("verdict") or {}).get("direction") or "neutral"),
                    },
                )
                credits_service.commit_analysis(db, user_id, job_id, amount=points)
                _sync_fast_report_row(
                    db,
                    job_id=job_id,
                    user_id=user_id,
                    symbol=symbol,
                    trade_date=trade_date,
                    fast_id=fast_id,
                    status="completed",
                    result=result,
                    snapshot=snapshot,
                )
                try:
                    rep = db.query(ReportDB).filter(ReportDB.id == job_id).first()
                    if rep is not None:
                        report_outcome_service.enqueue_for_report(db, rep)
                        report_outcome_service.evaluate_report_outcome(db, job_id)
                except Exception as exc:
                    logger.warning("[fast] enqueue outcome failed job_id=%s err=%s", job_id, exc)
        _drop_progress_buffer(fast_id)
        logger.info(
            "[fast] done job_id=%s status=%s elapsed_ms=%s llm_error=%s",
            job_id,
            final_status,
            elapsed_ms,
            llm_error or "none",
        )
        task_queue_service.request_schedule(user_id)
    except asyncio.TimeoutError as exc:
        err = f"分析超时（>{fast_budget_sec()}s）：{exc}"
        logger.error("[fast] timeout job_id=%s: %s", job_id, err)
        _finalize_failure(
            job_id,
            user_id,
            fast_id,
            err,
            started,
            points,
            snapshot,
            features,
            kline_features,
            symbol=symbol,
            trade_date=trade_date,
        )
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        logger.exception("[fast] failed job_id=%s: %s", job_id, err)
        _finalize_failure(
            job_id,
            user_id,
            fast_id,
            err,
            started,
            points,
            snapshot,
            features,
            kline_features,
            traceback.format_exc(),
            symbol=symbol,
            trade_date=trade_date,
        )


def _finalize_failure(
    job_id: str,
    user_id: str,
    fast_id: str,
    error: str,
    started: float,
    points: int,
    snapshot: dict[str, Any] | None,
    features: dict[str, Any] | None,
    kline_features: dict[str, Any] | None,
    tb: str | None = None,
    *,
    symbol: str,
    trade_date: str,
) -> None:
    with _FAST_SNAPSHOT_JSON_LOCK:
        with get_db_ctx() as db:
            row = db.query(FastAnalysisDB).filter(FastAnalysisDB.id == fast_id).first()
            if row:
                row.status = "failed"
                row.finished_at = _utcnow()
                row.elapsed_ms = int((time.perf_counter() - started) * 1000)
                snap_payload: dict[str, Any] = dict(snapshot or {})
                snap_payload["stage"] = "failed"
                snap_payload["error"] = error
                if tb:
                    snap_payload["traceback"] = tb[-2000:]
                with _PROGRESS_BUFFER_LOCK:
                    buffered = dict(_PROGRESS_BUFFER.get(fast_id) or {})
                prev_progress = buffered or dict((row.snapshot_json or {}).get("progress") or {})
                prev_progress.update(
                    {
                        "stage": "failed",
                        "stage_label": "已失败",
                        "percent": prev_progress.get("percent") or 0,
                        "final_status": "failed",
                        "elapsed_ms": row.elapsed_ms,
                        "error": error,
                    }
                )
                _append_log(prev_progress, error, level="error")
                snap_payload["progress"] = prev_progress
                row.snapshot_json = snap_payload
                if features is not None:
                    row.features_json = features
                if kline_features is not None:
                    row.kline_features_json = kline_features
                row.updated_at = _utcnow()
            analysis_job_service.persist_store_fields(db, job_id, {"status": "failed", "error": error})
            try:
                credits_service.refund_analysis(db, user_id, job_id, amount=points)
            except Exception as exc:
                logger.warning("[fast] refund credits failed: %s", exc)
            _sync_fast_report_row(
                db,
                job_id=job_id,
                user_id=user_id,
                symbol=symbol,
                trade_date=trade_date,
                fast_id=fast_id,
                status="failed",
                error=error,
            )
            try:
                rep = db.query(ReportDB).filter(ReportDB.id == job_id).first()
                if rep is not None:
                    report_outcome_service.enqueue_for_report(db, rep)
                    report_outcome_service.evaluate_report_outcome(db, job_id)
            except Exception as exc:
                logger.warning("[fast] enqueue outcome failed(failed) job_id=%s err=%s", job_id, exc)
    _drop_progress_buffer(fast_id)
    task_queue_service.request_schedule(user_id)


def list_recent_fast_analyses(db: Session, user_id: str, *, symbol: str | None = None, limit: int = 20) -> list[FastAnalysisDB]:
    """Recent fast-analysis rows for a user, newest first.

    fast_analyses 表带 9 个 JSON 大列（snapshot/features/verdict/...），直接 SELECT * + ORDER BY
    会把所有 JSON 塞进 sort buffer，本机 MySQL 默认 sort_buffer_size 偏小时会触发
    `(1038, 'Out of sort memory, ...')`。改用两阶段：先按主键 ORDER BY 拿到 id 列表
    （只排 id+created_at 小列），再用 IN 取完整行（无排序，靠 Python 还原顺序）。
    """
    capped = max(1, int(limit))
    id_query = db.query(FastAnalysisDB.id).filter(FastAnalysisDB.user_id == user_id)
    if symbol:
        id_query = id_query.filter(FastAnalysisDB.symbol == normalize_exchange_symbol(symbol).upper())
    id_rows = (
        id_query.order_by(FastAnalysisDB.created_at.desc())
        .limit(capped)
        .all()
    )
    ordered_ids: list[str] = [str(r[0]) for r in id_rows]
    if not ordered_ids:
        return []
    rows = db.query(FastAnalysisDB).filter(FastAnalysisDB.id.in_(ordered_ids)).all()
    by_id = {str(r.id): r for r in rows}
    return [by_id[i] for i in ordered_ids if i in by_id]

