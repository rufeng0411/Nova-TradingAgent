from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import traceback
from contextlib import asynccontextmanager, contextmanager
from io import StringIO
from pathlib import Path
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fastapi import Body
from threading import Lock
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import uuid4

import logging
import math
import time

# Windows: force Selector loop to improve async driver compatibility.
if os.name == "nt":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:
        pass

# Configure standard logging to include timestamps
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv

load_dotenv()

TA_INSTANCE_ID = os.getenv("TA_INSTANCE_ID", "").strip() or uuid4().hex[:12]

from fastapi import FastAPI, File, HTTPException, Depends, Header, Query, Request, UploadFile, status, BackgroundTasks
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session
import pandas as pd


def _safe_fnum(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _row_date_yyyy_mm_dd(row: pd.Series, key: str = "Date") -> Optional[str]:
    try:
        v = row.get(key) if hasattr(row, "get") else row[key]
    except Exception:
        return None
    if v is None or pd.isna(v):
        return None
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d")
        except Exception:
            pass
    s = str(v).strip()
    return s[:10] if len(s) >= 10 else None


from api.database import (
    AnalysisJobDB,
    FastAnalysisDB,
    JobEventDB,
    ReportOutcomeDB,
    UserDB,
    UserLLMConfigDB,
    VersionStatsDB,
    ReportDB,
    ImportedPortfolioPositionDB,
    FeedbackDB,
    SponsorDB,
    init_db,
    get_db,
    get_db_ctx,
)
from api.job_store import get_job_store as _new_job_store
from api.services import (
    access_log_service,
    admin_metrics_service,
    admin_signals_service,
    analysis_job_service,
    auth_service,
    credits_service,
    feedback_service,
    portfolio_import_service,
    report_service,
    report_outcome_service,
    scheduled_service,
    sponsor_service,
    symbol_service,
    task_queue_service,
    token_service,
    tracking_board_service,
    watchlist_service,
)
from api.symbol_utils import (
    cn_symbol_supports_extended_kline as _cn_symbol_supports_extended_kline,
    effective_data_ticker as _effective_data_ticker_for_job,
    normalize_exchange_symbol,
)

def _get_real_ip(request: Request) -> Optional[str]:
    """Extract real client IP, preferring Cloudflare/proxy headers."""
    if request is None:
        return None
    # Cloudflare Tunnel injects the real client IP here
    ip = request.headers.get("CF-Connecting-IP")
    if ip:
        return ip.strip()
    # Standard proxy header fallback
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import (
    TradingAgentsGraph,
    close_shared_langgraph_checkpointer_async,
    init_shared_langgraph_checkpointer_async,
)
from tradingagents.graph.data_collector import DataCollector

# 全局共享 DataCollector：同一 ticker+date 的数据只拉一次，所有 job 复用缓存
_shared_data_collector = DataCollector()
from tradingagents.dataflows.trade_calendar import cn_today_str
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.graph.intent_parser import parse_intent as _parse_intent
from tradingagents.agents.utils.context_utils import USER_CONTEXT_KEYS, normalize_user_context
from tradingagents.agents.utils.agent_states import current_tracker_var


def _cors_allow_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    default_origins = [
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:5175",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:4174",
        "http://localhost:4174",
    ]
    if not raw:
        return default_origins
    return [item.strip() for item in raw.split(",") if item.strip()]


def _cors_allow_origin_regex() -> str | None:
    raw = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip()
    if raw:
        return raw
    # 非生产环境：允许典型局域网 Origin，便于同一台机器上用局域网 IP 打开前端（:5173/:4173）并直连 :8000 API。
    if os.getenv("ENV", "").lower() != "prod":
        return (
            r"^https?://("
            r"localhost|127\.0\.0\.1|"
            r"192\.168\.\d{1,3}\.\d{1,3}|"
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
            r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r")(:\d+)?$"
        )
    return None


def _resolve_scheduled_trade_date(trade_date: str) -> str:
    """Use the requested trading day, or fall back to the latest CN trading day."""
    from tradingagents.dataflows.trade_calendar import is_cn_trading_day, previous_cn_trading_day

    return trade_date if is_cn_trading_day(trade_date) else previous_cn_trading_day(trade_date)


def _build_scheduled_analyze_request(
    db: Session,
    user_id: str,
    symbol: str,
    horizon: str,
    trade_date: str,
    scheduled_user_context: Optional[Dict[str, Any]] = None,
) -> "AnalyzeRequest":
    scheduled_user_context = scheduled_user_context or _build_imported_user_context(db, user_id, symbol)
    # Read user's saved analyst selection from DB
    user_cfg = auth_service.get_user_llm_config(db, user_id)
    selected = None
    if user_cfg and user_cfg.default_analysts:
        try:
            selected = json.loads(user_cfg.default_analysts)
        except Exception:
            pass
    req = AnalyzeRequest(
        symbol=symbol,
        trade_date=trade_date,
        horizons=[horizon],
        query=f"定时分析 {symbol}",
        user_intent={
            "ticker": symbol,
            "horizons": [horizon],
            "focus_areas": [],
            "specific_questions": [],
            "user_context": scheduled_user_context,
        },
        objective=scheduled_user_context.get("objective"),
        current_position=scheduled_user_context.get("current_position"),
        current_position_pct=scheduled_user_context.get("current_position_pct"),
        average_cost=scheduled_user_context.get("average_cost"),
        user_notes=scheduled_user_context.get("user_notes"),
    )
    if selected:
        req.selected_analysts = selected
    return req


async def _run_manual_trigger(
    task: dict,
    requested_trade_date: str,
    job_id: str,
) -> None:
    """Execute a manual-trigger analysis (no scheduler concurrency control).

    Used by the /v1/scheduled/{id}/trigger and /v1/scheduled/batch/trigger
    endpoints. Calls _run_job directly then records the test result.
    """
    task_id = task["id"]
    user_id = task["user_id"]
    symbol = task["symbol"]
    horizon = task.get("horizon") or "short"

    actual_trade_date = _resolve_scheduled_trade_date(requested_trade_date)
    _log(f"[Manual Trigger] {symbol} trade_date={actual_trade_date} (requested={requested_trade_date})")

    try:
        with get_db_ctx() as db:
            scheduled_user_context = task.get("manual_user_context") or _build_imported_user_context(
                db, user_id, symbol
            )
            req = _build_scheduled_analyze_request(
                db=db,
                user_id=user_id,
                symbol=symbol,
                horizon=horizon,
                trade_date=actual_trade_date,
                scheduled_user_context=scheduled_user_context,
            )

        await _run_job(job_id, req, False, True, user_id, "scheduled_manual")
        job_state = _get_job(job_id)
        if job_state.get("status") == "failed":
            raise RuntimeError(job_state.get("error") or f"manual trigger job {job_id} failed")
        with get_db_ctx() as db:
            scheduled_service.record_manual_test_result(db, task_id, "success", report_id=job_id)
        _log(f"[Manual Trigger] Completed {symbol}")
    except Exception as e:
        logger.error(f"[Manual Trigger] Failed {symbol}: {e}\n{traceback.format_exc()}")
        with get_db_ctx() as db:
            scheduled_service.record_manual_test_result(db, task_id, "failed")


async def _resume_claimed_analysis_job(job_id: str) -> None:
    """Continue a reclaimed job after API restart or lease expiry."""
    try:
        with get_db_ctx() as db:
            row = analysis_job_service.get_job_row(db, job_id)
            if not row or not row.request_payload:
                logger.warning("[Reconcile] missing payload for job %s", job_id)
                return
            payload = dict(row.request_payload)
            user_id = row.user_id
            src = row.request_source or "api"
        req = AnalyzeRequest.model_validate(payload)
        logger.info(
            "[Reconcile] job_id=%s resume_from_checkpoint user_id=%s source=%s instance=%s",
            job_id,
            user_id,
            src,
            TA_INSTANCE_ID,
        )
        await _run_job(job_id, req, True, True, user_id, src, resume_mode=True)
    except Exception as e:
        logger.exception("[Reconcile] resume failed for %s: %s", job_id, e)


async def _admin_metrics_roll_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            with get_db_ctx() as db:
                admin_metrics_service.rollup_recent_days(db, days=32)
        except Exception as e:
            logger.warning("admin metrics rollup: %s", e)


async def _queue_watchdog_loop() -> None:
    """Periodic self-heal for queued tasks that should have been dispatched."""
    interval = _queue_watchdog_interval_seconds()
    logger.info("Queue watchdog started (interval=%ss)", int(interval))
    while True:
        await asyncio.sleep(interval)
        try:
            if not task_queue_service.is_queue_enabled():
                continue
            with get_db_ctx() as db:
                user_ids = task_queue_service.list_users_with_queued_tasks(db)
            for user_id in user_ids:
                task_queue_service.request_schedule(user_id)
        except Exception as exc:
            logger.warning("queue watchdog failed: %s", exc)


def _report_outcome_eval_interval_seconds() -> float:
    try:
        return max(60.0, float(os.getenv("TA_REPORT_OUTCOME_EVAL_SEC", "1200")))
    except Exception:
        return 1200.0


async def _report_outcome_eval_loop() -> None:
    interval = _report_outcome_eval_interval_seconds()
    logger.info("Report outcome watchdog started (interval=%ss)", int(interval))
    while True:
        await asyncio.sleep(interval)
        try:
            if not report_outcome_service.outcome_enabled():
                continue
            with get_db_ctx() as db:
                done = report_outcome_service.evaluate_due_outcomes(db, limit=120)
            if done:
                logger.info("Report outcome watchdog evaluated rows=%s", done)
        except Exception as exc:
            logger.warning("report outcome watchdog failed: %s", exc)


class _HealthAccessLogFilter(logging.Filter):
    """压制 uvicorn 访问日志中高频健康检查噪声。

    Electron 一键启动器约每秒拉一次 /healthz，会把真正有用的 API 请求日志冲掉；
    `/v1/features` 也类似（首页轮询，每分钟多次）。这两条对排障没价值，过滤即可。
    `TA_ACCESS_LOG_VERBOSE=1` 可关闭过滤。
    """

    _SUPPRESS_PATTERNS = (' /healthz ', ' /v1/features ')

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return not any(p in msg for p in self._SUPPRESS_PATTERNS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup and cleanup on shutdown."""
    global _main_event_loop
    if (os.getenv("TA_ACCESS_LOG_VERBOSE", "") or "").strip().lower() not in ("1", "true", "yes", "on"):
        access_logger = logging.getLogger("uvicorn.access")
        if not any(isinstance(f, _HealthAccessLogFilter) for f in access_logger.filters):
            access_logger.addFilter(_HealthAccessLogFilter())
    _log("API startup: init_db() …")
    init_db()
    _log("API startup: init_db() done; LangGraph checkpointer …")
    await init_shared_langgraph_checkpointer_async()
    _log("API startup: checkpointer ready; default admin / plans …")
    with get_db_ctx() as db:
        auth_service.ensure_default_admin(db)
        auth_service.ensure_default_plans(db)
    _log("API startup: access log retention …")
    access_log_service.retention_cleanup_sync()
    _log("Database initialized.")
    _jt = _job_timeout_seconds()
    _jh = _job_heartbeat_seconds()
    _timeout_desc = "unlimited" if _jt is None else f"{int(_jt)}s"
    _log(
        f"Analysis outer timeout: {_timeout_desc} (TA_JOB_TIMEOUT={os.getenv('TA_JOB_TIMEOUT')!r}); "
        f"heartbeat every {int(_jh)}s (TA_JOB_HEARTBEAT_SEC)"
    )
    store = get_job_store()
    if os.getenv("TA_JOBSTORE_CLEAR_ON_START", "").strip().lower() in ("1", "true", "yes"):
        store.clear()
        _log("Job store cleared on startup (TA_JOBSTORE_CLEAR_ON_START).")
    _background_tasks.clear()

    async def _reconcile_analysis_jobs():
        await asyncio.sleep(2)
        try:
            with get_db_ctx() as db:
                ids = analysis_job_service.list_jobs_to_reclaim(db)
            for jid in ids:
                with get_db_ctx() as db:
                    if not analysis_job_service.try_claim_for_resume(db, jid, TA_INSTANCE_ID):
                        continue
                _log(f"[Reconcile] reclaiming analysis job {jid} (instance={TA_INSTANCE_ID})")
                _create_tracked_task(_resume_claimed_analysis_job(jid), label=f"resume-job-{jid[:8]}")
        except Exception as e:
            logger.warning("analysis job reconcile failed: %s", e)

    _create_tracked_task(_reconcile_analysis_jobs(), label="Analysis job reconcile")

    # Security: warn loudly if using default secret key
    if not os.getenv("TA_APP_SECRET_KEY"):
        _log("=" * 70)
        _log("WARNING: TA_APP_SECRET_KEY is not set!")
        _log("Using hardcoded default key. ALL encryption and JWT signing")
        _log("is INSECURE. Set TA_APP_SECRET_KEY env var before production use.")
        _log("=" * 70)

    # Warm trade calendar + stock map in the background so uvicorn binds to the port
    # immediately. Blocking here caused Vite proxy ECONNREFUSED during dev startup.
    # 另：开发脚本 scripts/dev-api.mjs 已对 uvicorn 使用 --reload-dir（api/tradingagents）
    # 与 --reload-delay，避免监视 frontend 或 StatReload 误触导致启动期整进程重载。
    async def _warm_trade_calendar_and_stock_map():
        try:
            from tradingagents.dataflows.trade_calendar import _load_cn_trade_dates

            await asyncio.to_thread(_load_cn_trade_dates)
            _log("Trade calendar pre-loaded.")
        except Exception as e:
            logger.warning("Trade calendar preload failed: %s", e)
        try:
            await asyncio.to_thread(symbol_service.load_cn_stock_map)
            _log("Stock map pre-loaded on startup.")
        except Exception as e:
            logger.warning("Stock map preload failed: %s", e)

    _create_tracked_task(_warm_trade_calendar_and_stock_map(), label="Warm trade calendar + stock map")
    from api.services import admin_events_service

    _main_event_loop = asyncio.get_running_loop()
    admin_events_service.set_main_loop(_main_event_loop)
    _log("API startup: admin metrics rollup …")
    try:
        with get_db_ctx() as db:
            admin_metrics_service.rollup_recent_days(db, days=5)
    except Exception:
        pass
    _log("API startup: background tasks (flush / metrics / queue watchdog / outcome watchdog) …")
    if report_outcome_service.outcome_enabled():
        _log("Report outcomes: enabled (TA_REPORT_OUTCOME_ENABLED unset or truthy; set to 0 to disable)")
    else:
        _log("Report outcomes: disabled (TA_REPORT_OUTCOME_ENABLED=0/false/off)")
    _access_log_flush_task = asyncio.create_task(access_log_service.flush_loop())
    _admin_metrics_task = asyncio.create_task(_admin_metrics_roll_loop())
    _queue_watchdog_task = asyncio.create_task(_queue_watchdog_loop())
    _report_outcome_watchdog_task = asyncio.create_task(_report_outcome_eval_loop())
    _log("API startup: complete — now serving HTTP (including /healthz)")
    try:
        yield
    finally:
        _report_outcome_watchdog_task.cancel()
        try:
            await _report_outcome_watchdog_task
        except asyncio.CancelledError:
            pass
        _queue_watchdog_task.cancel()
        try:
            await _queue_watchdog_task
        except asyncio.CancelledError:
            pass
        _admin_metrics_task.cancel()
        try:
            await _admin_metrics_task
        except asyncio.CancelledError:
            pass
        _access_log_flush_task.cancel()
        try:
            await _access_log_flush_task
        except asyncio.CancelledError:
            pass
        access_log_service.flush_to_db()
        _log("Shutting down: Cleaning up resources...")
        await close_shared_langgraph_checkpointer_async()
        _executor.shutdown(wait=True)
        _log("Executor shutdown complete.")
        _main_event_loop = None


_is_prod = os.getenv("ENV", "").lower() == "prod"


def _get_version() -> str:
    """Get app version: APP_VERSION env > package metadata > 'dev'."""
    v = os.getenv("APP_VERSION")
    if v:
        return v
    try:
        from importlib.metadata import version as pkg_version
        return pkg_version("tradingagents")
    except Exception:
        return "dev"


APP_VERSION = _get_version()

app = FastAPI(
    title="Nova-TradingAgent API",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=_cors_allow_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from api.middleware.access_log import AccessLogMiddleware

app.add_middleware(AccessLogMiddleware)

from api.middleware.maintenance_middleware import MaintenanceMiddleware

app.add_middleware(MaintenanceMiddleware)

from api.routers import admin as admin_router
from api.routers import admin_commerce as admin_commerce_router
from api.routers import admin_content as admin_content_router
from api.routers import admin_ops as admin_ops_router
from api.routers import admin_reports as admin_reports_router
from api.routers import auth as auth_router
from api.routers import billing as billing_router
from api.routers import features as features_router
from api.routers import fast_analysis as fast_analysis_router
from api.routers import tasks as tasks_router
from api.routers import users as users_router
from api.routers import market_advanced as market_advanced_router
from api.routers import llm as llm_router
from api.routers import system as system_router
from api.routers import jobs_checkpoint as jobs_checkpoint_router
from api.routers import qlib_eval as qlib_eval_router

app.include_router(features_router.router)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(tasks_router.router)
app.include_router(fast_analysis_router.router)
app.include_router(market_advanced_router.router, prefix="/v1/market")
app.include_router(billing_router.router)
app.include_router(admin_router.router)
app.include_router(admin_reports_router.router)
app.include_router(admin_commerce_router.router)
app.include_router(admin_ops_router.router)
app.include_router(admin_content_router.router)
app.include_router(llm_router.router)
app.include_router(system_router.router)
app.include_router(jobs_checkpoint_router.router)
app.include_router(qlib_eval_router.router)

_executor = ThreadPoolExecutor(max_workers=int(os.getenv("TA_MAX_WORKERS", "2")))

# ── Singleton job store (in-memory or Redis depending on REDIS_URL) ─────────
_job_store_instance: Optional[Any] = None

def get_job_store():
    global _job_store_instance
    if _job_store_instance is None:
        _job_store_instance = _new_job_store()
    return _job_store_instance

# Runtime config overrides via PATCH /v1/config
_global_config_overrides: Dict[str, Any] = {}

# Allowlist for config_overrides from client requests.
# Security: prevents injection of api_key, backend_url, or other sensitive keys.
_CONFIG_OVERRIDES_ALLOWLIST = {
    "llm_provider", "deep_think_llm", "quick_think_llm",
    "max_debate_rounds", "max_risk_discuss_rounds",
    "prompt_language",
}
_RUNTIME_ENV_OVERRIDES_ALLOWLIST = {
    "TA_TRANSLATOR_ENABLED",
    "TA_TRANSLATOR_ORDERBOOK_ENABLED",
    "TA_TRANSLATOR_ACTIVE_BUY_ENABLED",
    "TA_TRANSLATOR_MONEYFLOW_ENABLED",
    "TA_TRANSLATOR_FINANCIAL_ENABLED",
    "TA_TUSHARE_AUCTION_OC_ENABLED",
}
# Hold references to fire-and-forget tasks so they are not garbage collected
_background_tasks: set = set()

# Uvicorn 主事件循环；供从 run_in_threadpool 等无线程内循环的上下文里投递 asyncio 任务。
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None

# Running `_run_job_inner` tasks for user-initiated cancellation (single-process only).
_running_analysis_inner_tasks: Dict[str, asyncio.Task] = {}
_running_analysis_inner_tasks_lock = asyncio.Lock()


async def _register_running_analysis_inner_task(job_id: str, task: asyncio.Task) -> None:
    async with _running_analysis_inner_tasks_lock:
        _running_analysis_inner_tasks[job_id] = task


async def _unregister_running_analysis_inner_task(job_id: str, task: asyncio.Task) -> None:
    async with _running_analysis_inner_tasks_lock:
        if _running_analysis_inner_tasks.get(job_id) is task:
            _running_analysis_inner_tasks.pop(job_id, None)

# ── Stock map / 标的展示（实现见 api.services.symbol_service）──────────────────
CN_INDEX_SYMBOL_MAP = symbol_service.CN_INDEX_SYMBOL_MAP
CN_INDEX_DISPLAY_NAMES = symbol_service.CN_INDEX_DISPLAY_NAMES


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_timeout_seconds() -> Optional[float]:
    """整 job 外层墙钟上限；None 表示不限制（仅依赖进程/k8s 自身策略）。"""
    raw = (os.getenv("TA_JOB_TIMEOUT") or "3600").strip().lower()
    if raw in ("0", "none", "off", "unlimited", "inf"):
        return None
    try:
        v = float(raw)
        return None if v <= 0 else v
    except (TypeError, ValueError):
        return 3600.0


def _job_heartbeat_seconds() -> float:
    try:
        return max(30.0, float(os.getenv("TA_JOB_HEARTBEAT_SEC", "120")))
    except (TypeError, ValueError):
        return 120.0


def _create_tracked_task(coro, *, label: str = "Background task") -> asyncio.Task:
    """Create an asyncio task and keep a reference to prevent GC.
    Also logs unhandled exceptions via a done callback."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task):
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception():
            logger.error("%s failed: %s", label, t.exception())

    task.add_done_callback(_on_done)
    return task


def _log(msg: str):
    """Helper to log with timestamp via standard logging."""
    logger.info(msg)


def _extract_runtime_env_overrides(config_overrides: Dict[str, Any] | None) -> Dict[str, str]:
    if not isinstance(config_overrides, dict):
        return {}
    env_overrides = config_overrides.get("env")
    if not isinstance(env_overrides, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in env_overrides.items():
        if key not in _RUNTIME_ENV_OVERRIDES_ALLOWLIST:
            continue
        if value is None:
            continue
        out[key] = str(value).strip()
    return out


@contextmanager
def _temporary_env_overrides(overrides: Dict[str, str]):
    if not overrides:
        yield
        return
    old_values: Dict[str, str | None] = {}
    for key, value in overrides.items():
        old_values[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old in old_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _serialize_datetime_utc(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _load_cn_stock_map() -> Dict[str, str]:
    return symbol_service.load_cn_stock_map()


def _get_reverse_stock_map() -> Dict[str, str]:
    return symbol_service.get_reverse_stock_map()


def _get_reverse_stock_map_cached_only() -> Dict[str, str]:
    return symbol_service.get_reverse_stock_map_cached_only()


def _normalize_symbol(raw: str) -> str:
    return symbol_service.normalize_symbol(raw)


def _search_cn_stock_by_name(query: str) -> Optional[str]:
    return symbol_service.search_cn_stock_by_name(query)


def _split_watchlist_batch_text(text: str) -> List[str]:
    return symbol_service.split_watchlist_batch_text(text)


def _resolve_watchlist_identifier(
    raw: str,
    name_to_code: Dict[str, str],
    code_to_name: Dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    return symbol_service.resolve_watchlist_identifier(raw, name_to_code, code_to_name)


def _attach_stock_names(items: List[dict], code_to_name: Dict[str, str]) -> List[dict]:
    return symbol_service.attach_stock_names(items, code_to_name)


def _resolve_cn_display_name(symbol_key: str) -> Optional[str]:
    return symbol_service.resolve_cn_display_name(symbol_key)


def _is_cn_index_symbol(symbol: str) -> bool:
    return symbol_service.is_cn_index_symbol(symbol)


from api.deps import (
    _require_admin,
    _require_api_user,
    _require_web_user,
    optional_user as _optional_user,
)

FIXED_TEAMS = {
    "Analyst Team": [
        "Market Analyst",
        "Social Analyst",
        "News Analyst",
        "Fundamentals Analyst",
        "Macro Analyst",
        "Smart Money Analyst",
        "Volume Price Analyst",
    ],
    "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team": ["Trader"],
    "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
    "Portfolio Management": ["Portfolio Manager"],
}
ANALYST_ORDER = ["market", "social", "news", "fundamentals", "macro", "smart_money", "volume_price"]
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
    "macro": "Macro Analyst",
    "volume_price": "Volume Price Analyst",
    "smart_money": "Smart Money Analyst",
    "bull": "Bull Researcher",
    "bear": "Bear Researcher",
    "Bull_Initial": "Bull Researcher",
    "Bear_Initial": "Bear Researcher",
    "Bull_Rebuttal": "Bull Researcher",
    "Bear_Rebuttal": "Bear Researcher",
    "research_manager": "Research Manager",
    "trader": "Trader",
    "aggressive": "Aggressive Analyst",
    "neutral": "Neutral Analyst",
    "conservative": "Conservative Analyst",
    "portfolio_manager": "Portfolio Manager",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
    "macro": "macro_report",
    "smart_money": "smart_money_report",
    "volume_price": "volume_price_report",
}

# All analysts always run — each uses its own natural time window
# (technical/funds → short, fundamentals/macro → medium)
def _get_horizon_analysts(horizon: str, available: List[str]) -> List[str]:
    """Return all available analysts regardless of horizon."""
    return list(available)


def _announcements_file() -> Path:
    return Path(__file__).resolve().parent / "announcements.json"


def _load_latest_announcement() -> Optional[Dict[str, Any]]:
    path = _announcements_file()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log(f"[Announcements] Failed to read {path.name}: {exc}")
        return None

    announcements = raw.get("announcements") if isinstance(raw, dict) else raw
    if not isinstance(announcements, list):
        return None

    for item in announcements:
        if not isinstance(item, dict):
            continue
        if item.get("active", True) is False:
            continue
        return item
    return None


class UserContextInput(BaseModel):
    objective: Optional[str] = Field(None, description="用户目标动作，如建仓/加仓/减仓/止损/观察")
    risk_profile: Optional[str] = Field(None, description="风险偏好，如保守/平衡/激进")
    investment_horizon: Optional[str] = Field(None, description="持有周期，如短线/波段/中线")
    cash_available: Optional[float] = Field(None, description="可用资金")
    current_position: Optional[float] = Field(None, description="当前持仓数量")
    current_position_pct: Optional[float] = Field(None, description="当前仓位占比")
    average_cost: Optional[float] = Field(None, description="当前持仓成本")
    max_loss_pct: Optional[float] = Field(None, description="最大容忍亏损百分比")
    constraints: List[str] = Field(default_factory=list, description="用户的硬约束列表")
    user_notes: Optional[str] = Field(None, description="用户补充说明")


class AnalyzeRequest(UserContextInput):
    symbol: str = Field(default="", description="股票代码，如 600519.SH（当 query 包含代码时可省略）")
    trade_date: str = Field(default_factory=cn_today_str, description="交易日期 YYYY-MM-DD")
    selected_analysts: List[str] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals", "macro", "smart_money", "volume_price"]
    )
    config_overrides: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    # When set, triggers intent-driven analysis via streaming dual-horizon path
    query: Optional[str] = Field(default=None, description="自然语言查询，如：分析贵州茅台短线机会")
    horizons: List[str] = Field(default_factory=lambda: ["short"], description="分析周期列表，如 ['short'] 或 ['short','medium']")
    # Pre-parsed intent from _ai_extract_symbol_and_date (avoids second LLM call in _run_job)
    user_intent: Optional[Dict[str, Any]] = Field(default=None, description="预解析的用户意图，由 chat_completions 传入")


class AnalyzeResponse(BaseModel):
    job_id: str
    status: Literal["pending", "queued", "paused", "running", "completed", "failed"]
    created_at: str


class BatchScheduledTriggerJob(BaseModel):
    item_id: str
    job_id: str
    symbol: str
    name: str
    display_label: Optional[str] = None
    status: Literal["pending", "running", "completed", "failed"]
    created_at: str
    current_position: Optional[float] = None
    average_cost: Optional[float] = None
    waiting_ahead_count: Optional[int] = None
    scheduled_running_count: Optional[int] = None
    scheduled_concurrency_limit: Optional[int] = None


class BatchScheduledTriggerResponse(BaseModel):
    summary: Dict[str, int]
    jobs: List[BatchScheduledTriggerJob]


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "queued", "paused", "running", "completed", "failed"]
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    symbol: str
    trade_date: str
    error: Optional[str] = None
    waiting_ahead_count: Optional[int] = None
    scheduled_running_count: Optional[int] = None
    scheduled_concurrency_limit: Optional[int] = None
    display_label: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(UserContextInput):
    model: Optional[str] = "tradingagents-ashare"
    messages: List[ChatMessage]
    stream: bool = True
    selected_analysts: List[str] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals", "macro", "smart_money", "volume_price"]
    )
    config_overrides: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class KlineResponse(BaseModel):
    symbol: str
    display_label: Optional[str] = None
    start_date: str
    end_date: str
    candles: List[Dict[str, Any]]


class MarketQuotesRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list)


class RealtimeQuoteItem(BaseModel):
    price: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    quote_time: Optional[str] = None
    source: Optional[str] = None


class MarketQuotesResponse(BaseModel):
    quotes: Dict[str, RealtimeQuoteItem]
    missing: List[str] = Field(default_factory=list)
    cache_ttl_seconds: int


class ChartInsightRequest(BaseModel):
    symbol: str
    period: Literal["1d", "1w", "1mo"] = "1d"
    adjust: Literal["none", "qfq", "hfq"] = "none"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    selected_indicators: List[str] = Field(default_factory=list)
    level: Literal["brief", "normal", "deep"] = "normal"
    language: Literal["zh", "en"] = "zh"
    bypass_cache: bool = False
    context_level: Literal["basic", "advanced"] = "basic"


class ChartInsightResponsePayload(BaseModel):
    insight: Dict[str, Any]
    fallback_only: bool = False
    cached: bool = False


# Report API Models
class ReportCreateRequest(BaseModel):
    symbol: str = Field(..., description="股票代码")
    trade_date: str = Field(..., description="交易日期 YYYY-MM-DD")
    decision: Optional[str] = Field(
        None,
        description="报告中归纳的方向关键词（BUY/SELL/HOLD 等标签；非投资建议）",
    )
    result_data: Optional[Dict[str, Any]] = Field(None, description="完整分析结果")


class ReportResponse(BaseModel):
    id: str
    user_id: Optional[str]
    symbol: str
    name: Optional[str] = None
    display_label: Optional[str] = None
    trade_date: str
    status: Literal["pending", "running", "completed", "failed"] = "completed"
    error: Optional[str] = None
    decision: Optional[str]
    direction: Optional[str]
    rating_5tier: Optional[str] = None
    confidence: Optional[int]
    target_price: Optional[float]
    stop_loss_price: Optional[float]
    analysis_price: Optional[float] = None
    analysis_price_time: Optional[str] = None
    risk_items: Optional[List[Dict[str, Any]]] = None
    key_metrics: Optional[List[Dict[str, Any]]] = None
    analyst_traces: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    waiting_ahead_count: Optional[int] = None
    scheduled_running_count: Optional[int] = None
    scheduled_concurrency_limit: Optional[int] = None
    final_decision_summary: Optional[str] = None
    task_kind: Optional[str] = None
    release_version: Optional[str] = None
    outcome_summary: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "updated_at", when_used="json")
    def serialize_report_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        return _serialize_datetime_utc(value)


class ReportDetailResponse(ReportResponse):
    market_report: Optional[str]
    sentiment_report: Optional[str]
    news_report: Optional[str]
    fundamentals_report: Optional[str]
    macro_report: Optional[str]
    smart_money_report: Optional[str]
    volume_price_report: Optional[str]
    game_theory_report: Optional[str]
    investment_plan: Optional[str]
    trader_investment_plan: Optional[str]
    final_trade_decision: Optional[str]
    result_data: Optional[Dict[str, Any]]
    data_sources: Optional[Dict[str, Any]] = None


class ReportListResponse(BaseModel):
    total: int
    reports: List[ReportResponse]


class ReportOutcomeDetailResponse(BaseModel):
    report_id: str
    task_kind: str
    release_version: Optional[str] = None
    baseline_price: Optional[float] = None
    baseline_source: Optional[str] = None
    atr20: Optional[float] = None
    atr_window_end: Optional[str] = None
    weighted_score: Optional[float] = None
    settled_count: int = 0
    total_windows: int = 0
    primary_horizon: Optional[str] = None
    primary_status: Optional[str] = None
    outcomes: Dict[str, Any] = Field(default_factory=dict)
    last_evaluated_at: Optional[str] = None
    next_evaluate_after: Optional[str] = None
    error: Optional[str] = None


class ReportOutcomeSummaryItemResponse(BaseModel):
    key: str
    sample_count: int
    settled_count: int
    pending_count: int
    hit_rate: Optional[float] = None
    avg_weighted_score: Optional[float] = None
    miss_count: int


class ReportOutcomeSummaryResponse(BaseModel):
    group_by: Literal["overall", "version", "week"]
    summary: Dict[str, Any]
    items: List[ReportOutcomeSummaryItemResponse] = Field(default_factory=list)


class ReportBatchDeleteRequest(BaseModel):
    report_ids: List[str] = Field(default_factory=list)


class ReportBatchDeleteResponse(BaseModel):
    deleted_ids: List[str]
    missing_ids: List[str]


class LatestReportsBySymbolsRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list)


class LatestReportsBySymbolsResponse(BaseModel):
    reports: List[ReportResponse]


class PortfolioOverviewResponse(BaseModel):
    watchlist: List[dict]
    scheduled: List[dict]
    latest_reports: List[ReportResponse]
    portfolio_import: Optional[dict] = None


class WatchlistAddRequest(BaseModel):
    text: Optional[str] = None
    symbol: Optional[str] = None


class ScheduledBatchIdsRequest(BaseModel):
    item_ids: List[str] = Field(default_factory=list)


class ScheduledBatchUpdateRequest(BaseModel):
    item_ids: List[str] = Field(default_factory=list)
    is_active: Optional[bool] = None
    horizon: Optional[str] = None
    trigger_time: Optional[str] = None


class AnnouncementItemResponse(BaseModel):
    title: str
    detail: str


class AnnouncementResponse(BaseModel):
    id: str
    tag: Optional[str] = None
    title: str
    summary: Optional[str] = None
    published_at: str
    items: List[AnnouncementItemResponse]
    cta_label: Optional[str] = None
    cta_path: Optional[str] = None


class LatestAnnouncementResponse(BaseModel):
    announcement: Optional[AnnouncementResponse] = None


class UserRuntimeConfigResponse(BaseModel):
    llm_provider: str
    deep_think_llm: str
    quick_think_llm: str
    backend_url: str
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    has_api_key: bool = False
    has_wecom_webhook: bool = False
    wecom_webhook_display: Optional[str] = None
    server_fallback_enabled: bool = True
    email_report_enabled: bool = True
    wecom_report_enabled: bool = True
    default_analysts: List[str] = Field(default_factory=lambda: ["market", "social", "news", "fundamentals", "macro", "smart_money", "volume_price"])


class UserRuntimeConfigUpdateRequest(BaseModel):
    llm_provider: Optional[str] = None
    deep_think_llm: Optional[str] = None
    quick_think_llm: Optional[str] = None
    backend_url: Optional[str] = None
    max_debate_rounds: Optional[int] = None
    max_risk_discuss_rounds: Optional[int] = None
    email_report_enabled: Optional[bool] = None
    wecom_report_enabled: Optional[bool] = None
    api_key: Optional[str] = None
    wecom_webhook_url: Optional[str] = None
    clear_api_key: bool = False
    clear_wecom_webhook: bool = False
    warmup: bool = True
    force_warmup: bool = False
    default_analysts: Optional[List[str]] = None


class UserRuntimeWarmupRequest(UserRuntimeConfigUpdateRequest):
    prompt: str = "你好"


class RuntimeWarmupResult(BaseModel):
    model: str
    targets: List[str] = Field(default_factory=list)
    content: Optional[str] = None
    error: Optional[str] = None


class UserRuntimeWarmupResponse(BaseModel):
    prompt: str
    results: List[RuntimeWarmupResult]


class WecomWebhookWarmupRequest(BaseModel):
    wecom_webhook_url: Optional[str] = None
    content: Optional[str] = None


class WecomWebhookWarmupResponse(BaseModel):
    sent: bool = True
    message: str
    webhook_display: Optional[str] = None


class PortfolioPositionItem(BaseModel):
    symbol: str = Field(..., description="股票代码，如 600519.SH 或 600519")
    name: Optional[str] = Field(None, description="股票名称")
    current_position: Optional[float] = Field(None, description="持仓数量")
    available_position: Optional[float] = Field(None, description="可用数量")
    average_cost: Optional[float] = Field(None, description="成本价")
    market_value: Optional[float] = Field(None, description="市值")
    current_position_pct: Optional[float] = Field(None, description="仓位占比 %")


class PortfolioImportSyncRequest(BaseModel):
    positions: List[PortfolioPositionItem] = Field(..., description="持仓列表")
    source: str = Field("manual", description="持仓来源标识")
    auto_apply_scheduled: bool = Field(True, description="是否自动将持仓股票加入定时任务")


class UserTokenResponse(BaseModel):
    id: str
    name: str
    token: str
    token_hint: Optional[str] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "last_used_at", when_used="json")
    def serialize_token_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        return _serialize_datetime_utc(value)


class UserTokenListItem(BaseModel):
    """Token info for list endpoint — never exposes the full token."""
    id: str
    name: str
    token_hint: Optional[str] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "last_used_at", when_used="json")
    def serialize_token_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        return _serialize_datetime_utc(value)


class UserTokenCreateRequest(BaseModel):
    name: str


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _user_config_overrides(user_id: Optional[str], db: Optional[Session] = None) -> Dict[str, Any]:
    if not user_id:
        return {}

    def _query(sess: Session) -> Dict[str, Any]:
        user_cfg = auth_service.get_user_llm_config(sess, user_id)
        if not user_cfg:
            return {}
        result: Dict[str, Any] = {}
        for key in (
            "llm_provider",
            "backend_url",
            "quick_think_llm",
            "deep_think_llm",
            "max_debate_rounds",
            "max_risk_discuss_rounds",
        ):
            value = getattr(user_cfg, key, None)
            if value is not None:
                result[key] = value
        api_key = auth_service.decrypt_secret(user_cfg.api_key_encrypted)
        if api_key:
            result["api_key"] = api_key
        return result

    if db is not None:
        return _query(db)
    with get_db_ctx() as own_db:
        return _query(own_db)


def _build_runtime_config(overrides: Dict[str, Any], user_id: Optional[str] = None, db: Optional[Session] = None) -> Dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    server_fallback_enabled = os.getenv("ALLOW_SERVER_LLM_FALLBACK", "1").strip().lower() in ("1", "true", "yes", "on")
    config["server_fallback_enabled"] = server_fallback_enabled

    # Security: filter request overrides to allowlist only
    overrides = {k: v for k, v in overrides.items() if k in _CONFIG_OVERRIDES_ALLOWLIST}

    # Apply global config overrides (from PATCH /v1/config)
    if _global_config_overrides:
        config = _deep_merge(config, dict(_global_config_overrides))
    
    # Fetch user specific overrides from DB (pass db to reuse caller's session)
    user_overrides = _user_config_overrides(user_id, db=db)

    # ── Critical: Filter out empty strings before merging ──
    # This prevents an empty DB field from wiping out an Env Var default.
    filtered_user_overrides = {k: v for k, v in user_overrides.items() if v not in (None, "", [])}
    filtered_request_overrides = {k: v for k, v in overrides.items() if v not in (None, "", [])}

    if filtered_user_overrides:
        config = _deep_merge(config, filtered_user_overrides)
    if filtered_request_overrides:
        config = _deep_merge(config, filtered_request_overrides)

    # ── Intelligent fallback between models ──
    # If one is provided but the other is missing (even after env var merge), cross-fill.
    quick = config.get("quick_think_llm")
    deep = config.get("deep_think_llm")

    if not deep and quick:
        config["deep_think_llm"] = quick
    if not quick and deep:
        config["quick_think_llm"] = deep

    return config


def _try_hydrate_job_from_db(job_id: str) -> bool:
    """Reload durable job row into the process-local JobStore (survives API restart)."""
    try:
        with get_db_ctx() as db:
            row = analysis_job_service.get_job_row(db, job_id)
            if not row:
                return False
            get_job_store().set_job(job_id, **analysis_job_service.memory_job_from_row(row))
            return True
    except Exception as exc:
        logger.debug("hydrate job from db failed %s: %s", job_id, exc)
        return False


def _set_job(job_key: str, **kwargs) -> None:
    # Callers may pass job_id=<value> as a stored field.  Since
    # store.set_job()'s first positional param is also called job_id,
    # we must strip it from kwargs to avoid a "got multiple values" TypeError.
    # _get_job() always injects job_id back into the returned dict.
    kwargs.pop("job_id", None)
    get_job_store().set_job(job_key, **kwargs)
    serializable = {}
    for k in ("status", "error", "decision", "symbol", "trade_date", "user_id"):
        if k in kwargs and kwargs[k] is not None:
            serializable[k] = kwargs[k]
    if serializable:
        try:
            with get_db_ctx() as db:
                analysis_job_service.persist_store_fields(db, job_key, serializable)
        except Exception as exc:
            logger.debug("persist_store_fields %s: %s", job_key, exc)


def _get_job(job_key: str) -> Dict[str, Any]:
    d = get_job_store().get_job(job_key)
    if d:
        d.setdefault("job_id", job_key)
    return d


def _emit_job_event(job_id: str, event: str, data: Dict[str, Any]) -> None:
    seq: Optional[int] = None
    try:
        with get_db_ctx() as db:
            seq = analysis_job_service.append_event(db, job_id, event, data)
    except Exception as exc:
        logger.warning("append_job_event failed job_id=%s event=%s: %s", job_id, event, exc)
    get_job_store().emit_event(job_id, event, data, event_id=seq)


async def _langgraph_resume_input(
    compiled_graph: Any,
    config: Dict[str, Any],
    init_state: Dict[str, Any],
    resume_mode: bool,
) -> Any:
    """Return None to continue a persisted LangGraph checkpoint; else fresh init_state."""
    if not resume_mode:
        return init_state
    try:
        aget = getattr(compiled_graph, "aget_state", None)
        if aget is None:
            st = compiled_graph.get_state(config)
        else:
            st = await aget(config)
        if st is not None and getattr(st, "values", None):
            tid = (config or {}).get("configurable", {}).get("thread_id")
            logger.info("[Job] LangGraph resume_from_checkpoint thread_id=%s", tid)
            return None
    except Exception as exc:
        logger.debug("LangGraph resume probe failed: %s", exc)
    return init_state


def _attach_job_runtime_state(target: Any, job_id: Optional[str]) -> Any:
    if not job_id:
        return target
    job = _get_job(job_id)
    if not job:
        return target

    for field in ("waiting_ahead_count", "scheduled_running_count", "scheduled_concurrency_limit"):
        value = job.get(field)
        if value is not None or hasattr(target, field):
            setattr(target, field, value)
    return target


def _attach_report_task_kind(db: Session, target: Any, report_id: Optional[str]) -> Any:
    if not report_id:
        return target
    try:
        payload = dict(getattr(target, "result_data", None) or {})
        task_kind = str(payload.get("task_kind") or "").strip()
        if task_kind:
            setattr(target, "task_kind", task_kind)
            return target
    except Exception:
        pass

    try:
        row = analysis_job_service.get_job_row(db, str(report_id))
        req_payload = dict(getattr(row, "request_payload", None) or {}) if row else {}
        task_kind = str(req_payload.get("task_kind") or "full_analysis").strip()
        setattr(target, "task_kind", task_kind or "full_analysis")
    except Exception:
        setattr(target, "task_kind", "full_analysis")
    return target


def _attach_report_outcome_summary(
    target: Any,
    by_report_id: Dict[str, Dict[str, Any]],
    report_id: Optional[str],
) -> Any:
    if not report_id:
        return target
    summary = by_report_id.get(str(report_id))
    if summary is not None:
        setattr(target, "outcome_summary", summary)
    return target


def _report_payload_has_substance(result: Dict[str, Any]) -> bool:
    ftd = result.get("final_trade_decision")
    mr = result.get("market_report")
    return (isinstance(ftd, str) and ftd.strip()) or (isinstance(mr, str) and mr.strip())


def _reconcile_stale_running_report_from_job(db: Session, row: ReportDB, user_id: str) -> None:
    """报告行仍为 pending/running 时，尽量用「已完成」的任务结果补写 DB。

    来源优先级：进程内 JobStore（含完整 result）→ durable job 行 completed +
    ``job_events`` 中最近一次 ``job.completed`` 的 payload（API 重启后内存无 result 场景）。

    若报告已被 ``finalize_orphan_report`` 标成 failed（典型提示「分析任务已中断」）但事件流显示
    任务实际完成，则同样尝试补写，以修复历史列表/详情误显示失败的问题。
    """
    try:
        st = str(row.status or "")
        rescue_stale_failed = st == "failed" and str(row.error or "").strip() == (
            report_service.STALE_REPORT_ERROR_MESSAGE
        )
        if st not in report_service.ACTIVE_REPORT_STATUSES and not rescue_stale_failed:
            return
        jid = str(row.id or "").strip()
        if not jid:
            return
        if str(row.user_id or "").strip() != str(user_id or "").strip():
            return

        result: Optional[Dict[str, Any]] = None
        decision: str = "UNKNOWN"

        job = _get_job(jid)
        if job and str(job.get("status") or "").lower() == "completed":
            cand = job.get("result")
            if isinstance(cand, dict) and _report_payload_has_substance(cand):
                result = cand
                decision = str(job.get("decision") or cand.get("decision") or "UNKNOWN").strip()

        if result is None:
            aj = analysis_job_service.get_job_row(db, jid)
            if aj and str(aj.status or "").lower() == "completed":
                payload = analysis_job_service.fetch_latest_event_payload(db, jid, "job.completed")
                if payload:
                    cand = payload.get("result")
                    if isinstance(cand, dict) and _report_payload_has_substance(cand):
                        result = cand
                        decision = str(
                            payload.get("decision") or cand.get("decision") or "UNKNOWN"
                        ).strip()

        if not result and rescue_stale_failed:
            payload = analysis_job_service.fetch_latest_event_payload(db, jid, "job.completed")
            if payload:
                cand = payload.get("result")
                if isinstance(cand, dict) and _report_payload_has_substance(cand):
                    result = cand
                    decision = str(
                        payload.get("decision") or cand.get("decision") or "UNKNOWN"
                    ).strip()

        if not result:
            return

        conf_raw = result.get("confidence")
        confidence_override = None
        if isinstance(conf_raw, (int, float)):
            confidence_override = int(conf_raw)
        elif isinstance(conf_raw, str) and conf_raw.strip().isdigit():
            confidence_override = int(conf_raw.strip())

        symbol = str(result.get("symbol") or row.symbol or "").strip().upper()
        trade_date = str(result.get("trade_date") or row.trade_date or "").strip()
        report_service.create_report(
            db=db,
            symbol=symbol,
            trade_date=trade_date,
            decision=decision,
            result_data=result,
            data_sources_json=result.get("data_sources"),
            user_id=str(user_id),
            risk_items=None,
            key_metrics=None,
            confidence_override=confidence_override,
            target_price_override=result.get("target_price")
            if isinstance(result.get("target_price"), (int, float))
            else None,
            stop_loss_override=result.get("stop_loss_price")
            if isinstance(result.get("stop_loss_price"), (int, float))
            else None,
            analysis_price=None,
            analysis_price_time=None,
            report_id=jid,
            analyst_traces=result.get("analyst_traces"),
            llm_config=result.get("llm_config") if isinstance(result.get("llm_config"), dict) else None,
        )
        db.refresh(row)
    except Exception as exc:
        logger.warning("reconcile stale report id=%s: %s", getattr(row, "id", None), exc)
        try:
            db.rollback()
        except Exception:
            pass


def _maybe_kick_queue_for_job(job: Dict[str, Any]) -> None:
    """Best-effort queue watchdog: queued(0 ahead) should be dispatched quickly."""
    if not task_queue_service.is_queue_enabled():
        return
    if str(job.get("status") or "") != "queued":
        return
    waiting = job.get("waiting_ahead_count")
    try:
        waiting_n = int(waiting) if waiting is not None else 0
    except (TypeError, ValueError):
        waiting_n = 0
    if waiting_n > 0:
        return
    user_id = str(job.get("user_id") or "").strip()
    if not user_id:
        return
    task_queue_service.request_schedule(user_id)


def _build_task_queue_metadata(request: AnalyzeRequest, request_source: str) -> tuple[str, str]:
    symbol = (request.symbol or "").strip().upper()
    trade_date = (request.trade_date or "").strip()
    display = symbol_service.format_display_label(symbol_service.resolve_cn_display_name(symbol), symbol) if symbol else ""
    title = f"{display or symbol} {trade_date}".strip() or "智能分析任务"
    desc_parts = [f"来源: {request_source}"]
    if request.query:
        desc_parts.append(str(request.query).strip()[:200])
    elif request.user_notes:
        desc_parts.append(str(request.user_notes).strip()[:200])
    description = " | ".join([p for p in desc_parts if p])
    return title, description


async def _enqueue_or_start_job(
    job_id: str,
    request: AnalyzeRequest,
    *,
    user_id: Optional[str],
    request_source: str,
) -> tuple[str, int]:
    if not task_queue_service.is_queue_enabled():
        return "pending", 0
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return "pending", 0
    if request.dry_run:
        return "pending", 0

    title, description = _build_task_queue_metadata(request, request_source)

    def _persist_queue_state() -> tuple[str, int]:
        with get_db_ctx() as db:
            should_queue = (
                task_queue_service.has_active_running_job(
                    db,
                    normalized_user_id,
                    exclude_job_id=job_id,
                )
                or task_queue_service.has_pending_queue_items(db, normalized_user_id)
            )
            if not should_queue:
                return "pending", 0
            max_size = task_queue_service.max_queue_size()
            current_size = task_queue_service.queue_size(db, normalized_user_id)
            if current_size >= max_size:
                msg = f"排队已满（最多 {max_size} 个），请在任务中心处理后再提交"
                task_queue_service.set_analysis_job_status(db, job_id, status="failed", error=msg)
                return "rejected", current_size
            task_queue_service.enqueue_job(
                db,
                user_id=normalized_user_id,
                job_id=job_id,
                task_kind="full_analysis",
                title=title,
                description=description,
                symbol=request.symbol,
                trade_date=request.trade_date,
                queue_status=task_queue_service.QUEUE_STATUS_QUEUED,
            )
            task_queue_service.set_analysis_job_status(db, job_id, status="queued")
            ahead = task_queue_service.waiting_ahead_count(db, normalized_user_id, job_id)
            return "queued", ahead

    status, waiting_count = await asyncio.to_thread(_persist_queue_state)
    if status == "rejected":
        _set_job(
            job_id,
            status="failed",
            error=f"排队已满（最多 {task_queue_service.max_queue_size()} 个），请在任务中心处理后再提交",
            finished_at=_utcnow_iso(),
        )
        _emit_job_event(
            job_id,
            "job.failed",
            {
                "job_id": job_id,
                "error": f"排队已满（最多 {task_queue_service.max_queue_size()} 个），请在任务中心处理后再提交",
            },
        )
        return status, waiting_count
    if status == "queued":
        _set_job(job_id, status="queued", waiting_ahead_count=waiting_count)
        _emit_job_event(
            job_id,
            "job.queued",
            {
                "job_id": job_id,
                "symbol": request.symbol,
                "trade_date": request.trade_date,
                "waiting_ahead_count": waiting_count,
                "message": "任务已进入排队队列",
            },
        )
        # 进入队列后立即触发一次调度：如果当前没有运行中任务，会立刻出队并启动。
        task_queue_service.request_schedule(normalized_user_id)
    return status, waiting_count


async def _dispatch_next_queued_job_for_user(user_id: str) -> None:
    if not task_queue_service.is_queue_enabled():
        return
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return

    def _dequeue() -> Optional[Dict[str, Any]]:
        with get_db_ctx() as db:
            item = task_queue_service.dequeue_next_job(db, normalized_user_id)
            if not item:
                return None
            row = analysis_job_service.get_job_row(db, item["job_id"])
            payload = dict(row.request_payload or {}) if row and row.request_payload else {}
            request_source = str(row.request_source or "api") if row else "api"
            return {
                "job_id": item["job_id"],
                "request_payload": payload,
                "request_source": request_source,
            }

    dequeued = await asyncio.to_thread(_dequeue)
    if not dequeued:
        return

    job_id = str(dequeued["job_id"])
    payload = dequeued.get("request_payload") or {}
    if str(payload.get("task_kind") or "") == "fast_analysis":
        from api.services.fast_analysis_service import run_fast_analysis_job

        _set_job(job_id, status="pending", waiting_ahead_count=0)
        _emit_job_event(
            job_id,
            "job.dequeued",
            {"job_id": job_id, "message": "快速分析任务已出队，准备执行"},
        )
        _create_tracked_task(
            run_fast_analysis_job(job_id, normalized_user_id, payload),
            label="Queued fast analysis task",
        )
        return
    try:
        request = AnalyzeRequest(**payload)
    except Exception as exc:
        err = f"排队任务参数无效，无法启动：{exc}"
        _set_job(job_id, status="failed", error=err, finished_at=_utcnow_iso())
        _emit_job_event(job_id, "job.failed", {"job_id": job_id, "error": err})
        task_queue_service.request_schedule(normalized_user_id)
        return

    _set_job(job_id, status="pending", waiting_ahead_count=0)
    _emit_job_event(
        job_id,
        "job.dequeued",
        {"job_id": job_id, "message": "任务已出队，准备开始执行"},
    )
    _create_tracked_task(
        _run_job(job_id, request, True, True, normalized_user_id, str(dequeued.get("request_source") or "api")),
        label="Queued analysis task",
    )


def _request_user_queue_schedule(user_id: str) -> None:
    """从任意线程安全地触发队列调度（含 run_in_threadpool 的工作线程）。"""
    main = _main_event_loop
    if main is None or main.is_closed():
        logger.warning(
            "queue schedule skipped (no asyncio loop available): user_id=%s",
            user_id,
        )
        return

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    # 仅当当前线程正在运行的就是主 API 循环时才 create_task；否则（同步路由线程池、
    # 其它后台线程或嵌套 loop）一律 threadsafe 投递，避免 “no running event loop”。
    if running is not None and running is main:
        _create_tracked_task(
            _dispatch_next_queued_job_for_user(user_id),
            label="Queue dispatcher",
        )
        return

    def _log_future_result(fut: Future) -> None:
        try:
            fut.result()
        except Exception as exc:
            logger.error("Queue dispatcher failed: %s", exc, exc_info=exc)

    fut = asyncio.run_coroutine_threadsafe(
        _dispatch_next_queued_job_for_user(user_id),
        main,
    )
    fut.add_done_callback(_log_future_result)


task_queue_service.register_schedule_callback(_request_user_queue_schedule)


def _queue_watchdog_interval_seconds() -> float:
    raw = (os.getenv("TA_QUEUE_WATCHDOG_INTERVAL_SEC") or "8").strip()
    try:
        return max(2.0, float(raw))
    except (TypeError, ValueError):
        return 8.0


def _extract_request_user_context(request: UserContextInput) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for key in USER_CONTEXT_KEYS:
        value = getattr(request, key, None)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if key == "constraints" and not value:
            continue
        payload[key] = value
    return payload


def _merge_user_context_payload(
    explicit_context: Dict[str, Any],
    inferred_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged = normalize_user_context(inferred_context or {})
    merged.update(normalize_user_context(explicit_context or {}))
    return merged


def _compose_analysis_user_context(
    db: Session,
    user_id: str,
    symbol: str,
    *,
    explicit_context: Optional[Dict[str, Any]] = None,
    inferred_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    imported_context = _build_manual_imported_user_context(db, user_id, symbol)
    merged_with_imported = _merge_user_context_payload(inferred_context or {}, imported_context)
    return _merge_user_context_payload(explicit_context or {}, merged_with_imported)


def _apply_user_context_to_request(request: "AnalyzeRequest", user_context: Dict[str, Any]) -> "AnalyzeRequest":
    request.objective = user_context.get("objective")
    request.risk_profile = user_context.get("risk_profile")
    request.investment_horizon = user_context.get("investment_horizon")
    request.cash_available = user_context.get("cash_available")
    request.current_position = user_context.get("current_position")
    request.current_position_pct = user_context.get("current_position_pct")
    request.average_cost = user_context.get("average_cost")
    request.max_loss_pct = user_context.get("max_loss_pct")
    request.constraints = user_context.get("constraints", [])
    request.user_notes = user_context.get("user_notes")
    return request


def _build_result_payload(final_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": final_state.get("company_of_interest"),
        "trade_date": final_state.get("trade_date"),
        "direction": None,
        "instrument_context": final_state.get("instrument_context"),
        "market_context": final_state.get("market_context"),
        "user_context": final_state.get("user_context"),
        "workflow_context": final_state.get("workflow_context"),
        "market_report": final_state.get("market_report"),
        "sentiment_report": final_state.get("sentiment_report"),
        "news_report": final_state.get("news_report"),
        "fundamentals_report": final_state.get("fundamentals_report"),
        "macro_report": final_state.get("macro_report"),
        "smart_money_report": final_state.get("smart_money_report"),
        "volume_price_report": final_state.get("volume_price_report"),
        "game_theory_report": final_state.get("game_theory_report"),
        "game_theory_signals": final_state.get("game_theory_signals"),
        "analyst_traces": final_state.get("analyst_traces"),
        "investment_plan": final_state.get("investment_plan"),
        "trader_investment_plan": final_state.get("trader_investment_plan"),
        "risk_feedback_state": final_state.get("risk_feedback_state"),
        "final_trade_decision": final_state.get("final_trade_decision"),
        "data_sources": final_state.get("data_sources"),
        "derived_signals": final_state.get("derived_signals"),
    }


class AgentProgressTracker:
    # 阶段标题映射
    STAGE_TITLES = {
        "market_analysis": "市场分析完成",
        "sentiment_analysis": "舆情分析完成",
        "news_analysis": "新闻分析完成",
        "fundamentals_analysis": "基本面分析完成",
        "research_decision": "研究团队阶段完成",
        "trader_plan": "路径推演完成",
        "risk_assessment": "风险评估完成",
        "final_decision": "沙盘最终研判结论",
    }
    
    def __init__(self, selected_analysts: List[str], job_id: str, horizon: Optional[str] = None):
        self.job_id = job_id
        self.horizon = horizon
        self.selected_analysts = [a.lower() for a in selected_analysts]
        self.status: Dict[str, str] = {}
        self.start_times: Dict[str, float] = {}  # 记录每个 agent 开始时间
        self.report_sections: Dict[str, Optional[str]] = {
            "market_report": None,
            "sentiment_report": None,
            "news_report": None,
            "fundamentals_report": None,
            "macro_report": None,
            "smart_money_report": None,
            "volume_price_report": None,
            "game_theory_report": None,
            "investment_plan": None,
            "trader_investment_plan": None,
            "final_trade_decision": None,
        }
        # 跟踪已完成的阶段，避免重复发送里程碑
        self._completed_stages: set = set()
        # 跟踪已发送的 writing 状态，避免重复发送
        self._writing_status_sent: set = set()
        
        for team_agents in FIXED_TEAMS.values():
            for agent in team_agents:
                self.status[agent] = "pending"

        # 未选中的分析师标记为 skipped（仍展示，便于固定 12-agent 看板）
        for key in ANALYST_ORDER:
            agent = ANALYST_AGENT_NAMES[key]
            if key not in self.selected_analysts:
                self.status[agent] = "skipped"

    def _emit_milestone(self, stage: str, summary: str = "") -> None:
        """发送用户可见的里程碑事件"""
        if stage in self._completed_stages:
            return
        self._completed_stages.add(stage)
        
        title = self.STAGE_TITLES.get(stage, stage)
        _emit_job_event(
            self.job_id,
            "agent.milestone",
            {
                "stage": stage,
                "title": title,
                "summary": summary,
                "timestamp": _utcnow_iso(),
                "horizon": self.horizon,
            },
        )
        _log(f"[Milestone] {title}: {summary[:100]}...")

    def _emit_report_chunked(self, job_id: str, section: str, content: str) -> None:
        """将报告内容分片发送，直接透传不做人工延迟
        
        按较大块分片（如按段落），让前端自然渲染
        """
        # 按段落分割，保持Markdown结构
        paragraphs = content.split('\n\n')
        
        for i, para in enumerate(paragraphs):
            if not para.strip():
                continue
                
            _emit_job_event(
                job_id,
                "agent.report.chunk",
                {
                    "section": section,
                    "chunk": para + '\n\n',
                    "index": i,
                    "is_complete": False,
                    "horizon": self.horizon,
                },
            )
        
        # 发送完成标记
        _emit_job_event(
            job_id,
            "agent.report.chunk",
            {
                "section": section,
                "chunk": "",
                "index": -1,
                "is_complete": True,
                "horizon": self.horizon,
            },
        )

    def snapshot(self) -> Dict[str, Any]:
        agents = []
        for team, members in FIXED_TEAMS.items():
            for m in members:
                agents.append({"team": team, "agent": m, "status": self.status.get(m, "pending")})
        return {"agents": agents, "horizon": self.horizon}

    def _set_status(self, agent: str, status: str) -> None:
        prev = self.status.get(agent)
        if prev == status:
            return
        self.status[agent] = status
        
        # 记录时间
        if status == "in_progress":
            self.start_times[agent] = time.time()
        elif status == "completed" and agent in self.start_times:
            duration = time.time() - self.start_times[agent]
            _log(f"[Timer] Agent {agent} ({self.horizon or 'main'}) finished in {duration:.2f}s")

        _emit_job_event(
            self.job_id,
            "agent.status",
            {"agent": agent, "status": status, "previous_status": prev, "horizon": self.horizon},
        )

    def _update_research_team_status(self, status: str) -> None:
        for agent in ["Bull Researcher", "Bear Researcher", "Research Manager"]:
            self._set_status(agent, status)

    def _generate_stage_summary(self, stage: str, chunk: Dict[str, Any]) -> str:
        """根据阶段生成简要总结"""
        if stage == "market_analysis":
            report = chunk.get("market_report", "")
            # 提取关键信息
            if "支撑" in report or "压力" in report:
                return "技术面关键位已识别"
            return "技术面分析完成"
        elif stage == "sentiment_analysis":
            return "舆情数据已收集"
        elif stage == "news_analysis":
            return "新闻影响已评估"
        elif stage == "fundamentals_analysis":
            return "基本面指标已计算"
        elif stage == "research_decision":
            return "多空观点已形成"
        elif stage == "trader_plan":
            return "路径推演已整理"
        elif stage == "risk_assessment":
            return "风险水平已评估"
        elif stage == "final_decision":
            decision = chunk.get("final_trade_decision", "")
            prefix = "沙盘综合研判结论: "
            return f"{prefix}{decision[:50]}..." if len(decision) > 50 else f"{prefix}{decision}"
        return ""

    def _emit_writing_status(self, agent_name: str, report_type: str) -> None:
        """发送正在编写报告的状态（每个agent只发送一次）"""
        # 检查是否已经发送过
        status_key = f"{agent_name}:{report_type}"
        if status_key in self._writing_status_sent:
            return
        self._writing_status_sent.add(status_key)
        
        report_names = {
            "market_report": "市场分析",
            "sentiment_report": "舆情分析",
            "news_report": "新闻分析",
            "fundamentals_report": "基本面分析",
            "investment_plan": "沙盘草案",
            "trader_investment_plan": "路径推演",
            "final_trade_decision": "沙盘综合研判结论",
        }
        _emit_job_event(
            self.job_id,
            "agent.writing",
            {
                "agent": agent_name,
                "report": report_type,
                "report_name": report_names.get(report_type, report_type),
                "status": "writing",
                "horizon": self.horizon,
            },
        )

    def _emit_token(self, agent_name: str, report_type: str, token: str) -> None:
        """推送 Token 级别的流式内容（跳过空 token，避免思维模型推理阶段刷屏）"""
        if not token:
            return
        _emit_job_event(
            self.job_id,
            "agent.token",
            {
                "agent": agent_name,
                "report": report_type,
                "token": token,
                "horizon": self.horizon,
            },
        )

    def emit_debate_token(
        self, debate: str, agent: str, round_num: int, token: str,
    ) -> None:
        """推送辩论 token（流式输出，每个 chunk 调用一次）"""
        if not token:
            return
        try:
            _emit_job_event(
                self.job_id,
                "agent.debate.token",
                {
                    "debate": debate,
                    "agent": agent,
                    "round": round_num,
                    "token": token,
                    "horizon": self.horizon,
                },
            )
        except Exception:
            pass

    def emit_debate_message(
        self, debate: str, agent: str, round_num: int,
        content: str, is_verdict: bool = False,
    ) -> None:
        """推送辩论消息（每个 agent 每轮完成后调用一次）"""
        if not content:
            return
        try:
            _emit_job_event(
                self.job_id,
                "agent.debate",
                {
                    "debate": debate,
                    "agent": agent,
                    "round": round_num,
                    "content": content,
                    "is_verdict": is_verdict,
                    "horizon": self.horizon,
                },
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "Failed to emit debate message for %s in %s", agent, debate, exc_info=True,
            )

    def apply_chunk(self, chunk: Dict[str, Any]) -> None:
        # 分析师阶段状态推进
        found_active = False
        for analyst_key in ANALYST_ORDER:
            if analyst_key not in self.selected_analysts:
                continue

            agent_name = ANALYST_AGENT_NAMES[analyst_key]
            report_key = ANALYST_REPORT_MAP[analyst_key]
            has_report = bool(chunk.get(report_key))

            if has_report:
                if self.status.get(agent_name) != "completed":
                    self._set_status(agent_name, "completed")
                    self.report_sections[report_key] = chunk.get(report_key)
            elif not found_active:
                # 只在状态从 pending 变为 in_progress 时发送 writing 状态
                prev_status = self.status.get(agent_name)
                if prev_status != "in_progress":
                    self._set_status(agent_name, "in_progress")
                    # 发送正在分析的状态（只发送一次）
                    self._emit_writing_status(agent_name, report_key)
                found_active = True
            else:
                self._set_status(agent_name, "pending")

        # 分析师全部完成后，启动 Bull Researcher
        if not found_active and self.selected_analysts:
            if self.status.get("Bull Researcher") == "pending":
                self._set_status("Bull Researcher", "in_progress")

        # 研究团队状态更新
        debate_state = chunk.get("investment_debate_state") or {}
        bull_hist = str(debate_state.get("bull_history", "")).strip()
        bear_hist = str(debate_state.get("bear_history", "")).strip()
        judge = str(debate_state.get("judge_decision", "")).strip()
        if bull_hist or bear_hist:
            self._update_research_team_status("in_progress")
        if judge:
            self._update_research_team_status("completed")
            if self.status.get("Trader") != "in_progress":
                self._set_status("Trader", "in_progress")
                self._emit_writing_status("Trader", "trader_investment_plan")

        # 交易团队
        if chunk.get("trader_investment_plan"):
            if self.status.get("Trader") != "completed":
                self._set_status("Trader", "completed")
                self._set_status("Aggressive Analyst", "in_progress")

        # 风控与组合团队（发送最终决策）
        risk_state = chunk.get("risk_debate_state") or {}
        risk_judge = str(risk_state.get("judge_decision", "")).strip()

        if risk_judge:
            if self.status.get("Portfolio Manager") != "completed":
                self._set_status("Portfolio Manager", "in_progress")
                self._set_status("Aggressive Analyst", "completed")
                self._set_status("Conservative Analyst", "completed")
                self._set_status("Neutral Analyst", "completed")
                self._set_status("Portfolio Manager", "completed")
                final_summary = self._generate_stage_summary("final_decision", chunk)
                self._emit_milestone("final_decision", final_summary)


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content)


def _generate_tool_description(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """生成工具调用的可读描述"""
    if tool_name == "get_indicators":
        indicator = tool_args.get("indicator")
        if isinstance(indicator, str) and indicator:
            indicator_map = {
                "close_50_sma": "50日均线",
                "close_200_sma": "200日均线",
                "close_10_ema": "10日EMA",
                "close_20_ema": "20日EMA",
                "rsi": "RSI",
                "macd": "MACD",
                "boll": "布林中轨",
                "boll_ub": "布林上轨",
                "boll_lb": "布林下轨",
                "atr": "ATR波动率",
                "vwma": "VWMA量价均线",
                "obv": "OBV能量潮",
            }
            return f"计算 {indicator_map.get(indicator, indicator)}"
        return "获取技术指标"
    elif tool_name == "get_stock_data":
        return "获取股票历史数据"
    elif tool_name == "get_fundamentals":
        metrics = tool_args.get("metrics", [])
        if metrics:
            return f"获取 {', '.join(metrics[:2])}{' 等' if len(metrics) > 2 else ''} 基本面数据"
        return "获取基本面数据"
    elif tool_name == "get_income_statement":
        return "获取利润表"
    elif tool_name == "get_balance_sheet":
        return "获取资产负债表"
    elif tool_name == "get_cash_flow":
        return "获取现金流量表"
    elif tool_name == "get_news":
        return "获取相关新闻"
    elif tool_name == "get_social_sentiment":
        return "获取舆情数据"
    return f"调用 {tool_name}"


def _finalize_job_credits(job_id: str, user_id: Optional[str], dry_run: bool) -> None:
    if dry_run or not user_id:
        return
    job = _get_job(job_id)
    if not job or not job.get("credit_reserved"):
        return
    need = credits_service.analysis_cost()
    if need <= 0:
        return
    st = (job.get("status") or "").lower()
    try:
        with get_db_ctx() as db:
            if st == "completed":
                credits_service.commit_analysis(db, user_id, job_id, need)
            else:
                credits_service.refund_analysis(db, user_id, job_id, need)
    except Exception as e:
        logger.warning("credit finalize failed for %s: %s", job_id, e)


def _analysis_job_max_attempts() -> int:
    try:
        return max(1, int(os.getenv("TA_ANALYSIS_JOB_MAX_ATTEMPTS", "3")))
    except (TypeError, ValueError):
        return 3


_JOB_SSE_TECHNICAL_FAILURE = "任务未能完成，请稍后重试。"
_JOB_SSE_RETRYING_MESSAGE = "正在自动重试并从断点继续…"
_JOB_USER_CANCELLED_MESSAGE = "用户已终止分析"


async def _finalize_technical_analysis_failure(
    job_id: str,
    exc: BaseException,
    request_source: str,
    user_id: Optional[str],
) -> None:
    """对用户仅暴露通用文案；完整异常写入日志与管理员信号。"""
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    internal_detail = f"{type(exc).__name__}: {exc}"
    logger.error(
        "[Job %s] analysis terminated after retries | %s\n%s",
        job_id,
        internal_detail,
        tb_str,
    )
    _set_job(
        job_id,
        status="failed",
        error=_JOB_SSE_TECHNICAL_FAILURE,
        finished_at=_utcnow_iso(),
    )
    try:

        def _record_failure():
            with get_db_ctx() as err_db:
                report_service.mark_report_failed(err_db, job_id, _JOB_SSE_TECHNICAL_FAILURE)

        await asyncio.to_thread(_record_failure)
    except Exception as db_exc:
        _log(f"Failed to record failure in DB: {db_exc}")

    _emit_job_event(
        job_id,
        "job.failed",
        {"job_id": job_id, "error": _JOB_SSE_TECHNICAL_FAILURE},
    )
    admin_signals_service.insert_signal_safe(
        type="job.failed",
        severity="error",
        payload={
            "job_id": job_id,
            "error": internal_detail,
            "traceback": tb_str,
            "source": request_source,
        },
        user_id=user_id,
    )


async def _run_job(
    job_id: str,
    request: AnalyzeRequest,
    stream_events: bool = False,
    save_report: bool = True,
    user_id: Optional[str] = None,
    request_source: str = "api",
    *,
    resume_mode: bool = False,
) -> None:
    # 用 asyncio.Task + 分段 wait，避免 wait_for/cancel 卡在 to_thread。
    # 超时后标记失败但不 cancel 内部协程（让线程自然结束）；中段下发 heartbeat 便于前端感知仍在执行。
    inner_task = asyncio.create_task(
        _run_job_inner(
            job_id,
            request,
            stream_events,
            save_report,
            user_id,
            request_source,
            resume_mode=resume_mode,
        )
    )
    await _register_running_analysis_inner_task(job_id, inner_task)
    try:
        timeout_sec = _job_timeout_seconds()
        heartbeat_sec = _job_heartbeat_seconds()
        elapsed = 0.0
        while True:
            if timeout_sec is not None and elapsed >= timeout_sec:
                break
            slice_wait = heartbeat_sec
            if timeout_sec is not None:
                slice_wait = min(slice_wait, timeout_sec - elapsed)
            slice_wait = max(1.0, slice_wait)
            done, _ = await asyncio.wait({inner_task}, timeout=slice_wait)
            if inner_task in done:
                if inner_task.cancelled():
                    err_msg = _JOB_USER_CANCELLED_MESSAGE
                    _log(f"[Job {job_id}] {err_msg}")
                    _set_job(job_id, status="failed", error=err_msg, finished_at=_utcnow_iso())
                    try:
                        with get_db_ctx() as db:
                            report_service.mark_report_failed(db, job_id, err_msg)
                    except Exception:
                        pass
                    _emit_job_event(job_id, "job.failed", {"job_id": job_id, "error": err_msg})
                    admin_signals_service.insert_signal_safe(
                        type="job.failed",
                        severity="warning",
                        payload={"job_id": job_id, "error": err_msg, "reason": "user_cancel"},
                        user_id=user_id,
                    )
                elif inner_task.exception():
                    _log(f"[Job {job_id}] failed: {inner_task.exception()}")
                _finalize_job_credits(job_id, user_id, request.dry_run)
                return
            elapsed += slice_wait
            if timeout_sec is None or elapsed < timeout_sec:
                _emit_job_event(
                    job_id,
                    "job.heartbeat",
                    {
                        "job_id": job_id,
                        "elapsed_sec": int(elapsed),
                        "timeout_sec": int(timeout_sec) if timeout_sec is not None else None,
                        "message": "分析仍在进行，请稍候…",
                    },
                )
        assert timeout_sec is not None
        err_msg = f"任务超时（已超过 {int(timeout_sec)} 秒），已自动终止"
        _log(f"[Job {job_id}] {err_msg}")
        _set_job(job_id, status="failed", error=err_msg, finished_at=_utcnow_iso())
        # 注意：不能用 asyncio.to_thread 写 DB，因为线程池可能被僵尸任务占满导致死锁。
        # 用同步方式直接写，SQLite 的写入足够快不会阻塞事件循环。
        try:
            with get_db_ctx() as db:
                report_service.mark_report_failed(db, job_id, err_msg)
        except Exception:
            pass
        _emit_job_event(job_id, "job.failed", {"job_id": job_id, "error": err_msg})
        admin_signals_service.insert_signal_safe(
            type="job.failed",
            severity="error",
            payload={"job_id": job_id, "error": err_msg, "reason": "timeout"},
            user_id=user_id,
        )
        _finalize_job_credits(job_id, user_id, request.dry_run)
    finally:
        await _unregister_running_analysis_inner_task(job_id, inner_task)
        if task_queue_service.is_queue_enabled() and user_id:
            task_queue_service.request_schedule(str(user_id))


async def _run_job_inner(
    job_id: str,
    request: AnalyzeRequest,
    stream_events: bool = False,
    save_report: bool = True,
    user_id: Optional[str] = None,
    request_source: str = "api",
    *,
    resume_mode: bool = False,
) -> None:
    stop_lease = asyncio.Event()

    async def _lease_keepalive():
        while not stop_lease.is_set():
            await asyncio.sleep(45)
            try:
                def _renew():
                    with get_db_ctx() as db:
                        analysis_job_service.renew_lease(db, job_id, TA_INSTANCE_ID)

                await asyncio.to_thread(_renew)
            except Exception:
                pass

    lease_task = asyncio.create_task(_lease_keepalive())
    try:
        def _merge_payload():
            with get_db_ctx() as db:
                analysis_job_service.merge_request_payload(
                    db,
                    job_id,
                    request.model_dump(mode="json"),
                    user_id=user_id,
                    symbol=_normalize_symbol(request.symbol),
                    trade_date=request.trade_date,
                    request_source=request_source,
                    dry_run=request.dry_run,
                )

        await asyncio.to_thread(_merge_payload)

        if resume_mode:
            att = 0
            try:
                with get_db_ctx() as db:
                    row = analysis_job_service.get_job_row(db, job_id)
                    if row:
                        att = int(row.attempt_count or 0)
            except Exception:
                pass
            _emit_job_event(
                job_id,
                "job.resumed",
                {"job_id": job_id, "attempt": att, "instance": TA_INSTANCE_ID},
            )

        # Normalize for logic but keep original for display
        display_name = request.symbol
        normalized_symbol = _normalize_symbol(request.symbol)

        cost = credits_service.analysis_cost()
        if user_id and not request.dry_run and cost > 0:

            def _do_reserve():
                with get_db_ctx() as db:
                    credits_service.reserve_for_analysis(db, user_id, job_id, cost)

            try:
                await asyncio.to_thread(_do_reserve)
                _set_job(job_id, credit_reserved=True)
            except credits_service.InsufficientCreditsError:
                err_msg = "点数不足，请前往订阅页或联系管理员充值"
                _set_job(job_id, status="failed", error=err_msg, finished_at=_utcnow_iso())
                _emit_job_event(job_id, "job.failed", {"job_id": job_id, "error": err_msg})
                admin_signals_service.insert_signal_safe(
                    type="job.failed",
                    severity="error",
                    payload={"job_id": job_id, "error": err_msg, "reason": "insufficient_credits"},
                    user_id=user_id,
                )
                return

        # ── Step 0: Initialize report in DB (short-lived session) ──
        def _init_and_configure():
            with get_db_ctx() as db:
                try:
                    report_service.init_report(
                        db=db,
                        report_id=job_id,
                        symbol=normalized_symbol,
                        trade_date=request.trade_date,
                        user_id=user_id,
                    )
                    report_service.update_report_partial(db, job_id, status="running")
                    db.commit()
                except Exception as e:
                    _log(f"CRITICAL: Failed to initialize report in DB: {e}")
            return _build_runtime_config(request.config_overrides, user_id=user_id)

        config = await asyncio.to_thread(_init_and_configure)

        _set_job(job_id, status="running", started_at=_utcnow_iso(), symbol=normalized_symbol)

        _emit_job_event(
            job_id,
            "job.running",
            {
                "job_id": job_id,
                "symbol": normalized_symbol,
                "display_name": display_name,
                "trade_date": request.trade_date
            },
        )
        # Ensure request object uses the normalized symbol for internal logic
        request.symbol = normalized_symbol
        user_context_payload = _extract_request_user_context(request)
        tracker = AgentProgressTracker(request.selected_analysts, job_id)
        _emit_job_event(job_id, "agent.snapshot", tracker.snapshot())

        job_start_t = time.time()
        max_attempts = _analysis_job_max_attempts()
        resume_analysis = resume_mode
        last_analysis_exc: Optional[BaseException] = None
        runtime_env_overrides = _extract_runtime_env_overrides(request.config_overrides)
        runtime_env_old_values: Dict[str, Optional[str]] = {}
        for _k, _v in runtime_env_overrides.items():
            runtime_env_old_values[_k] = os.environ.get(_k)
            os.environ[_k] = _v

        for attempt_num in range(1, max_attempts + 1):
            try:
                if request.dry_run:
                    result = {
                        "mode": "dry_run",
                        "symbol": request.symbol,
                        "trade_date": request.trade_date,
                        "selected_analysts": request.selected_analysts,
                        "user_context": user_context_payload,
                        "llm_provider": config.get("llm_provider"),
                        "data_vendors": config.get("data_vendors"),
                    }
                    _set_job(
                        job_id,
                        status="completed",
                        result=result,
                        decision="DRY_RUN",
                        finished_at=_utcnow_iso(),
                    )
                    _emit_job_event(
                        job_id,
                        "job.completed",
                        {"job_id": job_id, "decision": "DRY_RUN", "result": result},
                    )
                    return

                _shared_data_collector.ref(request.symbol, request.trade_date)
                graph = TradingAgentsGraph(
                    selected_analysts=request.selected_analysts,
                    debug=False,
                    config=config,
                    data_collector=_shared_data_collector,
                )
                final_state: Optional[Dict[str, Any]] = None

                # 强制单周期：多个 horizon 时只取第一个，避免 dual-horizon 双倍开销
                if not request.horizons:
                    request.horizons = ["short"]
                elif len(request.horizons) > 1:
                    request.horizons = [request.horizons[0]]

                # ── Dual-horizon intent-driven path ──────────────────────────────────
                if request.query:
                    # 1. 组装用户意图
                    intent_start_t = time.time()
                    ticker = request.symbol or display_name

                    # 优先使用已由 chat_completions 预解析的 intent（单次 LLM），避免二次调用
                    if request.user_intent:
                        user_intent = dict(request.user_intent)
                        user_intent["ticker"] = ticker
                        user_intent["horizons"] = request.horizons
                    else:
                        # 直接 POST /v1/analyze 时的兜底（无预解析 intent）
                        user_intent = await asyncio.to_thread(_parse_intent, request.query, graph.quick_thinking_llm, fallback_ticker=ticker)
                        if not request.horizons:
                            request.horizons = user_intent["horizons"]
                        user_intent["horizons"] = request.horizons
                    _log(f"[Timer] Intent Parsing took {time.time() - intent_start_t:.2f}s")

                    inferred_user_context = user_intent.get("user_context") or {}
                    user_context_payload = _merge_user_context_payload(
                        user_context_payload,
                        inferred_user_context,
                    )
                    user_intent["user_context"] = user_context_payload

                    # intent JSON 的 ticker 常为中文简称；必须以已规范化的 request.symbol 为准，避免 AkShare 走中文报错
                    coerced = _effective_data_ticker_for_job(
                        request.symbol,
                        user_intent.get("ticker"),
                        name_to_code=_load_cn_stock_map(),
                    )
                    if coerced != (user_intent.get("ticker") or "").strip().upper():
                        _log(
                            f"[DualHorizon] ticker coercion: intent={user_intent.get('ticker')!r} "
                            f"request={request.symbol!r} -> effective={coerced!r}"
                        )
                    ticker = coerced
                    user_intent["ticker"] = ticker

                    # 2. 一次性采集数据，短线/中线共用缓存
                    lookback_label = "14天关键行情" if request.horizons == ["short"] else "90天全量行情、财务、新闻、资金"
                    _emit_job_event(job_id, "agent.tool_call", {
                        "agent": "数据采集", "tool": "data_collector",
                        "description": f"预加载 {ticker} 近{lookback_label}数据…",
                    })
                    _log(f"[DualHorizon] Collecting data for {ticker} {request.trade_date} (horizons={request.horizons})…")
                    collect_start_t = time.time()
                    await asyncio.to_thread(graph.data_collector.collect, ticker, request.trade_date, horizons=request.horizons)
                    _log(f"[Timer] Data Collection step in _run_job took {time.time() - collect_start_t:.2f}s")
                    collected_pool = graph.data_collector.get(ticker, request.trade_date) or {}
                    data_sources_bundle = collected_pool.get("_data_sources")
                    derived_signals_bundle = collected_pool.get("derived_signals")

                    _emit_job_event(job_id, "agent.tool_call", {
                        "agent": "数据采集", "tool": "data_collector",
                        "description": "数据采集完成，开始多维度分析",
                    })

                    report_keys = (
                        "market_report", "sentiment_report", "news_report", "fundamentals_report",
                        "macro_report", "smart_money_report", "volume_price_report",
                        "investment_plan", "trader_investment_plan", "final_trade_decision",
                    )

                    horizon_states: Dict[str, Any] = {}

                    async def _process_horizon(horizon: str):
                        """Async helper to run analysis for a single horizon."""
                        # 根据周期过滤 analyst，共享已采集的数据缓存
                        horizon_analysts = _get_horizon_analysts(horizon, request.selected_analysts)
                        horizon_graph = TradingAgentsGraph(
                            selected_analysts=horizon_analysts,
                            debug=False,
                            config=config,
                            data_collector=graph.data_collector,
                        )

                        horizon_label = "短线" if horizon == "short" else "中线"
                        _emit_job_event(job_id, "agent.horizon_start", {
                            "horizon": horizon, "label": horizon_label,
                        })
                        # 每轮重置 tracker，前端进度条重新走一遍
                        h_tracker = AgentProgressTracker(horizon_analysts, job_id, horizon=horizon)
                        _emit_job_event(job_id, "agent.snapshot", h_tracker.snapshot())
                        # 告知前端本轮参与的 analyst 即将开始
                        for analyst_key in ANALYST_ORDER:
                            if analyst_key in horizon_analysts:
                                aname = ANALYST_AGENT_NAMES[analyst_key]
                                h_tracker._set_status(aname, "in_progress")
                                h_tracker._emit_writing_status(aname, ANALYST_REPORT_MAP[analyst_key])

                        h_args = horizon_graph.propagator.get_graph_args()

                        # Use thread_id for LangGraph checkpointer persistence
                        if "config" not in h_args:
                            h_args["config"] = {}
                        h_args["config"]["configurable"] = {"thread_id": f"{job_id}_{horizon}"}

                        init_state = horizon_graph.propagator.create_initial_state(
                            ticker, request.trade_date,
                            user_context=user_context_payload,
                            selected_analysts=horizon_analysts,
                            request_source=request_source,
                            user_intent=user_intent, horizon=horizon,
                        )
                        if data_sources_bundle:
                            init_state["data_sources"] = data_sources_bundle
                        last_report: Dict[str, str] = {}
                        seen: Dict[str, bool] = {}   # 追踪哪些字段已出现过，避免重复事件
                        horizon_final = None

                        # DB 更新使用短生命周期 session，避免长期占用连接池
                        def _horizon_partial_update(updates: dict):
                            with get_db_ctx() as _hdb:
                                report_service.update_report_partial(_hdb, job_id, **updates)

                        # 通过 ContextVar 将 tracker 传入 async 节点（LangGraph 不传递 schema 外的字段）
                        _tracker_token = current_tracker_var.set(h_tracker)
                        try:
                            stream_input = await _langgraph_resume_input(
                                horizon_graph.graph,
                                h_args["config"],
                                init_state,
                                resume_analysis,
                            )
                            async for chunk in horizon_graph.graph.astream(stream_input, **h_args):
                                horizon_final = chunk

                                # ── 并行感知的状态推进 ──────────────────
                                # 1. 每个 analyst 报告首次出现 → completed
                                for analyst_key in ANALYST_ORDER:
                                    if analyst_key not in horizon_analysts:
                                        continue
                                    rkey = ANALYST_REPORT_MAP[analyst_key]
                                    aname = ANALYST_AGENT_NAMES[analyst_key]
                                    if chunk.get(rkey) and not seen.get(rkey):
                                        seen[rkey] = True
                                        h_tracker._set_status(aname, "completed")

                                # 2. 分析师全部完成后 → Bull/Bear/ResearchManager 开始
                                all_analysts_done = all(
                                    seen.get(ANALYST_REPORT_MAP.get(a, "")) for a in h_tracker.selected_analysts
                                )
                                if all_analysts_done and not seen.get("_research_started"):
                                    seen["_research_started"] = True
                                    h_tracker._set_status(ANALYST_AGENT_NAMES["bull"], "in_progress")
                                    h_tracker._set_status(ANALYST_AGENT_NAMES["bear"], "in_progress")
                                    h_tracker._set_status(ANALYST_AGENT_NAMES["research_manager"], "in_progress")

                                # 3. research judge → 研究团队完成, Trader 开始
                                debate = chunk.get("investment_debate_state") or {}
                                if debate.get("judge_decision") and not seen.get("judge_decision"):
                                    seen["judge_decision"] = True
                                    for r_key in ["bull", "bear", "research_manager"]:
                                        h_tracker._set_status(ANALYST_AGENT_NAMES[r_key], "completed")
                                    h_tracker._set_status(ANALYST_AGENT_NAMES["trader"], "in_progress")
                                    h_tracker._emit_writing_status(ANALYST_AGENT_NAMES["trader"], "trader_investment_plan")

                                # 4. trader plan → Trader completed, 风控开始
                                if chunk.get("trader_investment_plan") and not seen.get("trader_investment_plan"):
                                    seen["trader_investment_plan"] = True
                                    h_tracker._set_status(ANALYST_AGENT_NAMES["trader"], "completed")
                                    h_tracker._set_status(ANALYST_AGENT_NAMES["aggressive"], "in_progress")

                                # 5. risk judge → 风控全部完成
                                risk = chunk.get("risk_debate_state") or {}
                                if risk.get("judge_decision") and not seen.get("risk_judge_decision"):
                                    seen["risk_judge_decision"] = True
                                    for r_key in ["aggressive", "neutral", "conservative", "portfolio_manager"]:
                                        h_tracker._set_status(ANALYST_AGENT_NAMES[r_key], "completed")
                                # ── end 并行感知 ────────────────────────────────────────────

                                # 报告分片推送与数据库即时更新
                                db_updates = {}
                                for key in report_keys:
                                    value = chunk.get(key)
                                    if value and value != last_report.get(key):
                                        last_report[key] = value
                                        db_updates[key] = str(value)
                                        h_tracker._emit_report_chunked(job_id, key, str(value))

                                if db_updates:
                                    await asyncio.to_thread(_horizon_partial_update, db_updates)
                        except Exception as e:
                            _log(f"Error during horizon streaming ({horizon}): {e}")
                            raise
                        finally:
                            current_tracker_var.reset(_tracker_token)

                        horizon_states[horizon] = horizon_final
                        for agent, st in h_tracker.status.items():
                            if st not in ("completed", "skipped"):
                                h_tracker._set_status(agent, "completed")
                        _emit_job_event(job_id, "agent.horizon_done", {"horizon": horizon})

                    # 3. 按解析出的 horizons 并行运行 astream()，事件实时推给前端
                    results = await asyncio.gather(
                        *[_process_horizon(h) for h in request.horizons],
                        return_exceptions=True,
                    )
                    horizon_errors = []
                    for i, r in enumerate(results):
                        if isinstance(r, Exception):
                            _log(f"Horizon '{request.horizons[i]}' failed: {r}")
                            horizon_errors.append(f"{request.horizons[i]}: {r}")
                    if horizon_errors:
                        raise RuntimeError(f"Horizon analysis failed: {'; '.join(horizon_errors)}")

                    short_r = graph._build_horizon_result("short", horizon_states.get("short") or {})
                    medium_r = graph._build_horizon_result("medium", horizon_states.get("medium") or {})
                    primary_r = short_r if horizon_states.get("short") else medium_r
                    # 防御：若主周期缺少最终结论或交易员方案，说明 astream 中途退出但未抛错，
                    # 直接落库会得到 "未知 · HOLD" 的伪完成；此处主动抛错走外层重试 / 失败兜底。
                    if not str(primary_r.get("final_trade_decision") or "").strip():
                        raise RuntimeError("primary horizon missing final_trade_decision; refusing to mark job completed")
                    if not str(primary_r.get("trader_investment_plan") or "").strip():
                        raise RuntimeError("primary horizon missing trader_investment_plan; refusing to mark job completed")
                    decision = graph.process_signal(primary_r.get("final_trade_decision", "")) or "UNKNOWN"
                    result = {
                        "symbol": ticker,
                        "trade_date": request.trade_date,
                        "mode": "dual_horizon",
                        "user_intent": user_intent,
                        "short_term": short_r,
                        "medium_term": medium_r,
                        "decision": decision,
                        # Hoist primary horizon's report fields to top level so that
                        # resolve_report_fields / create_report can find them directly.
                        "final_trade_decision": primary_r.get("final_trade_decision", ""),
                        "investment_plan": primary_r.get("investment_plan", ""),
                        "trader_investment_plan": primary_r.get("trader_investment_plan", ""),
                        "market_report": primary_r.get("market_report", ""),
                        "sentiment_report": primary_r.get("sentiment_report", ""),
                        "news_report": primary_r.get("news_report", ""),
                        "fundamentals_report": primary_r.get("fundamentals_report", ""),
                        "macro_report": primary_r.get("macro_report", ""),
                        "smart_money_report": primary_r.get("smart_money_report", ""),
                        "volume_price_report": primary_r.get("volume_price_report", ""),
                        "analyst_traces": (
                            short_r.get("analyst_traces", []) + medium_r.get("analyst_traces", [])
                        ),
                        "data_sources": data_sources_bundle,
                        "derived_signals": derived_signals_bundle,
                    }
                    # LLM 结构化提取（目标价、止损、信心、风险、关键指标）
                    # 注意：必须在 _set_job(status="completed") 之前完成，否则 SSE 超时
                    # 会因为看到 status="completed" 而提前关闭流，导致 job.completed 事件丢失。
                    structured = None
                    try:
                        structured = await asyncio.to_thread(
                            report_service.extract_structured_data,
                            final_trade_decision=primary_r.get("final_trade_decision", ""),
                            fundamentals_report=primary_r.get("fundamentals_report", ""),
                            config=config,
                        )
                    except Exception as e:
                        _log(f"Structured extraction failed (non-fatal): {e}")

                    resolved = await asyncio.to_thread(
                        report_service.resolve_report_fields,
                        result_data=result,
                        confidence_override=structured.confidence if structured else None,
                        target_price_override=structured.target_price if structured else None,
                        stop_loss_override=structured.stop_loss_price if structured else None,
                    )
                    result.update({
                        "direction": resolved["direction"],
                        "confidence": resolved["confidence"],
                        "target_price": resolved["target_price"],
                        "stop_loss_price": resolved["stop_loss_price"],
                    })

                    # 自动保存报告到数据库（未要求落库时视为已成功）
                    report_saved = not save_report
                    if save_report:
                        def _save_report_sync():
                            with get_db_ctx() as save_db:
                                # Fetch current analysis price
                                try:
                                    quotes = _get_cached_market_quotes([request.symbol])
                                    quote = quotes.get(request.symbol, {})
                                    analysis_price = float(quote.get("price")) if quote.get("price") is not None else None
                                    analysis_price_time = quote.get("quote_time") or _utcnow_iso()
                                except Exception:
                                    analysis_price = None
                                    analysis_price_time = None
                                
                                # Format trade_date to include time if available
                                trade_date_with_time = request.trade_date
                                if analysis_price_time:
                                    try:
                                        dt = datetime.fromisoformat(analysis_price_time.replace('Z', '+00:00'))
                                        trade_date_with_time = dt.strftime('%Y-%m-%d %H:%M')
                                    except Exception:
                                        pass

                                rep = report_service.create_report(
                                    db=save_db,
                                    symbol=request.symbol,
                                    trade_date=trade_date_with_time,
                                    decision=decision,
                                    result_data=result,
                                    data_sources_json=result.get("data_sources"),
                                    user_id=user_id,
                                    risk_items=([r.model_dump() for r in structured.risks] if structured else None),
                                    key_metrics=([m.model_dump() for m in structured.key_metrics] if structured else None),
                                    confidence_override=result["confidence"],
                                    target_price_override=result["target_price"],
                                    stop_loss_override=result["stop_loss_price"],
                                    analysis_price=analysis_price,
                                    analysis_price_time=analysis_price_time,
                                    report_id=job_id,
                                    analyst_traces=result.get("analyst_traces"),
                                    llm_config=config,
                                )
                                save_db.commit()
                                return getattr(rep, "final_decision_summary", None)

                        try:
                            fd_summary = await asyncio.to_thread(_save_report_sync)
                            if fd_summary:
                                result["final_decision_summary"] = fd_summary
                            report_saved = True
                        except Exception as e:
                            logger.exception("Failed to save report (dual_horizon finalize)")
                            _log(f"Failed to save report: {e}")
                            report_saved = False

                    if report_saved:
                        _set_job(job_id, status="completed", result=result,
                                 decision=decision, finished_at=_utcnow_iso())
                        _emit_job_event(job_id, "job.completed", {
                            "job_id": job_id, "decision": decision,
                            "direction": result["direction"],
                            "result": result, "mode": "dual_horizon",
                            "risk_items": [r.model_dump() for r in structured.risks] if structured else [],
                            "key_metrics": [m.model_dump() for m in structured.key_metrics] if structured else [],
                            "confidence": result["confidence"],
                            "target_price": result["target_price"],
                            "stop_loss_price": result["stop_loss_price"],
                        })
                        _log(f"Job completed successfully: {job_id}")
                    else:
                        persist_err = "分析结果未能写入报告库，请稍后重试或联系管理员。"
                        try:
                            with get_db_ctx() as edb:
                                report_service.update_report_partial(edb, job_id, status="failed", error=persist_err)
                        except Exception:
                            pass
                        _set_job(job_id, status="failed", error=persist_err, finished_at=_utcnow_iso())
                        _emit_job_event(job_id, "job.failed", {"job_id": job_id, "error": persist_err})
                        _log(f"Job {job_id} marked failed after report persist error")
                    _log(f"[Timer] TOTAL Job execution (dual_horizon) took {time.time() - job_start_t:.2f}s")
                    return
                # ── End dual-horizon path ─────────────────────────────────────────────

                if stream_events:
                    init_state = graph.propagator.create_initial_state(
                        request.symbol,
                        request.trade_date,
                        user_context=user_context_payload,
                        selected_analysts=request.selected_analysts,
                        request_source=request_source,
                    )
                    collected_pool = graph.data_collector.get(request.symbol, request.trade_date) or {}
                    if collected_pool.get("_data_sources"):
                        init_state["data_sources"] = collected_pool.get("_data_sources")
                    args = graph.propagator.get_graph_args()
            
                    # Pass job_id as thread_id for LangGraph checkpointer persistence
                    if "config" not in args:
                        args["config"] = {}
                    args["config"]["configurable"] = {"thread_id": job_id}

                    report_keys = (
                        "market_report",
                        "sentiment_report",
                        "news_report",
                        "fundamentals_report",
                        "macro_report",
                        "smart_money_report",
                        "volume_price_report",
                        "investment_plan",
                        "trader_investment_plan",
                        "final_trade_decision",
                    )
                    last_report: Dict[str, str] = {}
                    seen: Dict[str, bool] = {}

                    _tracker_token = current_tracker_var.set(tracker)
                    try:
                        stream_input = await _langgraph_resume_input(
                            graph.graph,
                            args["config"],
                            init_state,
                            resume_analysis,
                        )
                        async for chunk in graph.graph.astream(stream_input, **args):
                            final_state = chunk
                            # ── 并行感知的状态推进 ──────────────────
                            # 1. 每个 analyst 报告首次出现 → completed
                            for analyst_key in ANALYST_ORDER:
                                if analyst_key not in request.selected_analysts:
                                    continue
                                rkey = ANALYST_REPORT_MAP[analyst_key]
                                aname = ANALYST_AGENT_NAMES[analyst_key]
                                if chunk.get(rkey) and not seen.get(rkey):
                                    seen[rkey] = True
                                    tracker._set_status(aname, "completed")

                            # 2. 分析师全部完成 → 研究团队开始
                            all_analysts_done = all(
                                seen.get(ANALYST_REPORT_MAP.get(a, "")) for a in tracker.selected_analysts
                            )
                            if all_analysts_done and not seen.get("_research_started"):
                                seen["_research_started"] = True
                                tracker._set_status(ANALYST_AGENT_NAMES["bull"], "in_progress")
                                tracker._set_status(ANALYST_AGENT_NAMES["bear"], "in_progress")
                                tracker._set_status(ANALYST_AGENT_NAMES["research_manager"], "in_progress")

                            debate = chunk.get("investment_debate_state") or {}
                            if debate.get("judge_decision") and not seen.get("judge_decision"):
                                seen["judge_decision"] = True
                                for r_key in ["bull", "bear", "research_manager"]:
                                    tracker._set_status(ANALYST_AGENT_NAMES[r_key], "completed")
                                tracker._set_status(ANALYST_AGENT_NAMES["trader"], "in_progress")

                            if chunk.get("trader_investment_plan") and not seen.get("trader_investment_plan"):
                                seen["trader_investment_plan"] = True
                                tracker._set_status(ANALYST_AGENT_NAMES["trader"], "completed")
                                tracker._set_status(ANALYST_AGENT_NAMES["aggressive"], "in_progress")

                            risk = chunk.get("risk_debate_state") or {}
                            if risk.get("judge_decision") and not seen.get("risk_judge_decision"):
                                seen["risk_judge_decision"] = True
                                for r_key in ["aggressive", "neutral", "conservative", "portfolio_manager"]:
                                    tracker._set_status(ANALYST_AGENT_NAMES[r_key], "completed")
                            # ────────────────────────────────────────────

                            # ── Partial DB Persistence & UI Streaming ──
                            db_updates = {}
                            for key in report_keys:
                                value = chunk.get(key)
                                if value and value != last_report.get(key):
                                    last_report[key] = value
                                    db_updates[key] = str(value)
                                    # 立即推送报告分片，前端即可“即产即看”
                                    tracker._emit_report_chunked(job_id, key, str(value))
                    
                            if db_updates:
                                def _partial_update(updates=db_updates):
                                    with get_db_ctx() as _db:
                                        report_service.update_report_partial(_db, job_id, **updates)
                                await asyncio.to_thread(_partial_update)
                    
                            # ── Message & Tool Call Handling ──
                            messages = chunk.get("messages", [])
                            if messages:
                                msg = messages[-1]
                                content = _extract_message_text(getattr(msg, "content", ""))
                                agent_name = getattr(msg, "name", None)

                                if content:
                                    _log(f"[Agent Message] {agent_name}: {content[:200]}...")

                                for tool_call in getattr(msg, "tool_calls", []) or []:
                                    tool_name = tool_call.get("name", "unknown") if isinstance(tool_call, dict) else getattr(tool_call, "name", "unknown")
                                    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
                                    _log(f"[Tool Call] {agent_name}: {tool_name}")

                                    agent_display = agent_name
                                    if not agent_display:
                                        tool_to_agent = {
                                            "get_stock_data": "数据获取",
                                            "get_indicators": "技术分析师",
                                            "get_fundamentals": "基本面分析师",
                                            "get_income_statement": "基本面分析师",
                                            "get_balance_sheet": "基本面分析师",
                                            "get_cash_flow": "基本面分析师",
                                            "get_news": "新闻分析师",
                                            "get_social_sentiment": "舆情分析师",
                                        }
                                        agent_display = tool_to_agent.get(tool_name, "系统")

                                    tool_description = _generate_tool_description(tool_name, tool_args)
                                    _emit_job_event(
                                        job_id,
                                        "agent.tool_call",
                                        {
                                            "agent": agent_display,
                                            "tool": tool_name,
                                            "description": tool_description,
                                        },
                                    )
                
                    except Exception as e:
                        _log(f"Error during default streaming: {e}")
                    finally:
                        current_tracker_var.reset(_tracker_token)
                else:
                    final_state, _ = await asyncio.to_thread(
                        graph.propagate,
                        request.symbol,
                        request.trade_date,
                        user_context=user_context_payload,
                        selected_analysts=request.selected_analysts,
                        request_source=request_source,
                        thread_id=job_id,
                        resume_from_checkpoint=resume_analysis,
                    )

                if not final_state:
                    raise RuntimeError("graph returned empty final state")
                if not str(final_state.get("final_trade_decision") or "").strip():
                    raise RuntimeError("final_state missing final_trade_decision; refusing to mark job completed")
                if not str(final_state.get("trader_investment_plan") or "").strip():
                    raise RuntimeError("final_state missing trader_investment_plan; refusing to mark job completed")
                if not final_state.get("data_sources"):
                    fallback_pool = graph.data_collector.get(request.symbol, request.trade_date) or {}
                    if fallback_pool.get("_data_sources"):
                        final_state["data_sources"] = fallback_pool.get("_data_sources")
                    if fallback_pool.get("derived_signals"):
                        final_state["derived_signals"] = fallback_pool.get("derived_signals")

                decision = graph.process_signal(final_state["final_trade_decision"]) or "UNKNOWN"
                result = _build_result_payload(final_state)
                result["decision"] = decision

                # 全量收口为 completed/skipped
                for agent, status in tracker.status.items():
                    if status not in ("completed", "skipped"):
                        tracker._set_status(agent, "completed")

                # LLM 结构化提取（非阻塞，失败不影响主流程）
                # 注意：_set_job(status="completed") 必须在此之后调用，否则 SSE 超时会提前关闭流
                structured = None
                try:
                    structured = await asyncio.to_thread(
                        report_service.extract_structured_data,
                        final_trade_decision=result.get("final_trade_decision", ""),
                        fundamentals_report=result.get("fundamentals_report", ""),
                        config=config,
                    )
                except Exception as e:
                    _log(f"Structured extraction failed (non-fatal): {e}")

                # 一次性解析所有字段（方向、信心、目标价等）
                resolved = await asyncio.to_thread(
                    report_service.resolve_report_fields,
                    result_data=result,
                    confidence_override=structured.confidence if structured else None,
                    target_price_override=structured.target_price if structured else None,
                    stop_loss_override=structured.stop_loss_price if structured else None,
                )

                # 注入结果字典以便通知和保存使用
                result.update({
                    "direction": resolved["direction"],
                    "confidence": resolved["confidence"],
                    "target_price": resolved["target_price"],
                    "stop_loss_price": resolved["stop_loss_price"],
                })

                # 自动保存/收口报告到数据库（未要求落库时视为已成功，避免跳过 completed）
                report_saved = not save_report
                if save_report:
                    def _save_report_final_sync():
                        with get_db_ctx() as save_db:
                            # Fetch current analysis price
                            try:
                                quotes = _get_cached_market_quotes([request.symbol])
                                quote = quotes.get(request.symbol, {})
                                analysis_price = float(quote.get("price")) if quote.get("price") is not None else None
                                analysis_price_time = quote.get("quote_time") or _utcnow_iso()
                            except Exception:
                                analysis_price = None
                                analysis_price_time = None
                            
                            # Format trade_date to include time if available
                            trade_date_with_time = request.trade_date
                            if analysis_price_time:
                                try:
                                    dt = datetime.fromisoformat(analysis_price_time.replace('Z', '+00:00'))
                                    trade_date_with_time = dt.strftime('%Y-%m-%d %H:%M')
                                except Exception:
                                    pass

                            rep = report_service.create_report(
                                db=save_db,
                                symbol=request.symbol,
                                trade_date=trade_date_with_time,
                                decision=decision,
                                result_data=result,
                                data_sources_json=result.get("data_sources"),
                                user_id=user_id,
                                risk_items=([r.model_dump() for r in structured.risks] if structured else None),
                                key_metrics=([m.model_dump() for m in structured.key_metrics] if structured else None),
                                confidence_override=result["confidence"],
                                target_price_override=result["target_price"],
                                stop_loss_override=result["stop_loss_price"],
                                analysis_price=analysis_price,
                                analysis_price_time=analysis_price_time,
                                report_id=job_id,
                                analyst_traces=result.get("analyst_traces"),
                                llm_config=config,
                            )
                            save_db.commit()
                            return getattr(rep, "final_decision_summary", None)

                    try:
                        fd_summary = await asyncio.to_thread(_save_report_final_sync)
                        if fd_summary:
                            result["final_decision_summary"] = fd_summary
                        report_saved = True
                    except Exception as e:
                        logger.exception("Failed to finalize report (single_horizon persist)")
                        _log(f"Failed to finalize report: {e}")
                        report_saved = False

                if report_saved:
                    _set_job(
                        job_id,
                        status="completed",
                        result=result,
                        decision=decision,
                        finished_at=_utcnow_iso(),
                    )
                    _emit_job_event(
                        job_id,
                        "job.completed",
                        {
                            "job_id": job_id,
                            "decision": decision,
                            "direction": result["direction"],
                            "result": result,
                            "risk_items": [r.model_dump() for r in structured.risks] if structured else [],
                            "key_metrics": [m.model_dump() for m in structured.key_metrics] if structured else [],
                            "confidence": result["confidence"],
                            "target_price": result["target_price"],
                            "stop_loss_price": result["stop_loss_price"],
                        },
                    )
                    _log(f"Job completed successfully: {job_id}")
                else:
                    persist_err = "分析结果未能写入报告库，请稍后重试或联系管理员。"
                    try:
                        with get_db_ctx() as edb:
                            report_service.update_report_partial(edb, job_id, status="failed", error=persist_err)
                    except Exception:
                        pass
                    _set_job(job_id, status="failed", error=persist_err, finished_at=_utcnow_iso())
                    _emit_job_event(job_id, "job.failed", {"job_id": job_id, "error": persist_err})
                    _log(f"Job {job_id} marked failed after report persist error")
                _log(f"[Timer] TOTAL Job execution (single_horizon) took {time.time() - job_start_t:.2f}s")
            except Exception as exc:
                last_analysis_exc = exc
                logger.exception(
                    '[Job %s] analysis attempt %s/%s failed',
                    job_id,
                    attempt_num,
                    max_attempts,
                )
                if attempt_num >= max_attempts:
                    break
                _emit_job_event(
                    job_id,
                    'job.retrying',
                    {
                        'job_id': job_id,
                        'attempt': attempt_num,
                        'max_attempts': max_attempts,
                        'message': _JOB_SSE_RETRYING_MESSAGE,
                    },
                )
                resume_analysis = True
                await asyncio.sleep(min(2.0 * attempt_num, 20.0))

        if last_analysis_exc is not None:
            await _finalize_technical_analysis_failure(
                job_id=job_id,
                exc=last_analysis_exc,
                request_source=request_source,
                user_id=user_id,
            )
    finally:
        stop_lease.set()
        lease_task.cancel()
        try:
            await lease_task
        except asyncio.CancelledError:
            pass
        try:
            with get_db_ctx() as db:
                analysis_job_service.release_lease(db, job_id)
        except Exception:
            pass
        for _k, _old in runtime_env_old_values.items():
            if _old is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _old
        _shared_data_collector.evict(request.symbol, request.trade_date)


def _extract_chat_text(messages: List[ChatMessage]) -> str:
    if not messages:
        return ""
    last = messages[-1]
    return _extract_message_text(last.content)


def _extract_symbol_and_date(text: str) -> tuple[Optional[str], Optional[str]]:
    # Date extraction (flexible boundaries)
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    date = date_match.group(0) if date_match else None

    # Priority 1: A-Share 6-digit code (even if stuck to Chinese characters)
    sym_match = re.search(r"(\d{6}(?:\.(?:SH|SZ|SS))?)", text, re.IGNORECASE)
    if sym_match:
        return _normalize_symbol(sym_match.group(1)), date

    # Priority 2: US Stocks or other Tickers (use boundaries for letters to avoid partial words)
    us_match = re.search(r"\b([A-Z]{1,6}(?:\.[A-Z]{1,3})?)\b", text.upper())
    if us_match:
        return us_match.group(1), date

    return None, date


def _sse_pack(event: str, data: Dict[str, Any], event_id: Optional[int] = None) -> str:
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    return f"{id_line}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_stock_csv(raw: str) -> List[Dict[str, Any]]:
    if not raw:
        return []
    lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines:
        return []

    try:
        df = pd.read_csv(StringIO("\n".join(lines)))
    except Exception:
        return []

    if "Date" not in df.columns:
        return []

    rename_map = {k: k.strip() for k in df.columns}
    df = df.rename(columns=rename_map)
    required = ["Date", "Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            return []

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Open", "High", "Low", "Close"]).sort_values("Date")
    if df.empty:
        return []

    candles: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        candles.append(
            {
                "date": row["Date"].strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]) if "Volume" in df.columns and pd.notna(row.get("Volume")) else None,
            }
        )
    return candles


def _normalize_kline_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    col_map = {
        "日期": "Date",
        "date": "Date",
        "Date": "Date",
        "开盘": "Open",
        "open": "Open",
        "Open": "Open",
        "最高": "High",
        "high": "High",
        "High": "High",
        "最低": "Low",
        "low": "Low",
        "Low": "Low",
        "收盘": "Close",
        "close": "Close",
        "Close": "Close",
        "成交量": "Volume",
        "volume": "Volume",
        "Volume": "Volume",
        "成交额": "Amount",
        "amount": "Amount",
        "Amount": "Amount",
        "涨跌幅": "ChangePercent",
        "涨跌额": "Change",
        "换手率": "TurnoverRate",
    }
    out = df.rename(columns=col_map).copy()
    required = ["Date", "Open", "High", "Low", "Close"]
    if any(col not in out.columns for col in required):
        return pd.DataFrame()

    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out = out.dropna(subset=["Date"]).sort_values("Date")
    for col in ["Open", "High", "Low", "Close", "Volume", "Amount", "ChangePercent", "Change", "TurnoverRate"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    return out.reset_index(drop=True)


def _dataframe_to_kline_candles(df: pd.DataFrame) -> List[Dict[str, Any]]:
    candles: List[Dict[str, Any]] = []
    prev_close: Optional[float] = None
    for _, row in df.iterrows():
        dstr = _row_date_yyyy_mm_dd(row, "Date")
        if not dstr:
            continue
        open_ = _safe_fnum(row.get("Open"))
        high = _safe_fnum(row.get("High"))
        low = _safe_fnum(row.get("Low"))
        close = _safe_fnum(row.get("Close"))
        if open_ is None or high is None or low is None or close is None:
            continue
        chg_raw = row.get("Change") if "Change" in df.columns else None
        change = None
        if chg_raw is not None and pd.notna(chg_raw):
            change = _safe_fnum(chg_raw)
        else:
            if prev_close is not None:
                change = close - prev_close
        pct_raw = row.get("ChangePercent") if "ChangePercent" in df.columns else None
        change_pct = None
        if pct_raw is not None and pd.notna(pct_raw):
            change_pct = _safe_fnum(pct_raw)
        elif prev_close not in (None, 0) and change is not None:
            change_pct = (change / prev_close) * 100 if prev_close else None

        vol = None
        if "Volume" in df.columns and pd.notna(row.get("Volume")):
            vol = _safe_fnum(row.get("Volume"))
        amt = None
        if "Amount" in df.columns and pd.notna(row.get("Amount")):
            amt = _safe_fnum(row.get("Amount"))
        tor = None
        if "TurnoverRate" in df.columns and pd.notna(row.get("TurnoverRate")):
            tor = _safe_fnum(row.get("TurnoverRate"))

        candles.append(
            {
                "date": dstr,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": vol,
                "amount": amt,
                "change": change,
                "change_percent": change_pct,
                "turnover_rate": tor,
            }
        )
        prev_close = close
    return candles


AK_KLINE_PERIOD_MAP = {"1d": "daily", "1w": "weekly", "1mo": "monthly"}


def _fetch_index_kline_ak_hist(symbol: str, start_date: str, end_date: str, period: str) -> List[Dict[str, Any]]:
    import akshare as ak  # type: ignore

    if not _is_cn_index_symbol(symbol):
        return []
    code = symbol.upper().split(".")[0]
    per = AK_KLINE_PERIOD_MAP.get(period, "daily")
    y0, y1 = start_date.replace("-", ""), end_date.replace("-", "")
    try:
        raw_df = ak.index_zh_a_hist(symbol=code, period=per, start_date=y0, end_date=y1)
    except Exception as exc:
        _log(f"[kline] index_zh_a_hist extended failed {symbol}: {exc}")
        return []
    df = _normalize_kline_df(raw_df)
    if df.empty:
        return []
    df = df[(df["Date"] >= pd.to_datetime(start_date)) & (df["Date"] <= pd.to_datetime(end_date))]
    return _dataframe_to_kline_candles(df)


def _fetch_stock_kline_ak_hist(symbol: str, start_date: str, end_date: str, period: str, adjust: str) -> List[Dict[str, Any]]:
    import akshare as ak  # type: ignore

    code = symbol.upper().split(".")[0]
    per = AK_KLINE_PERIOD_MAP.get(period, "daily")
    adj = "" if adjust == "none" else adjust
    y0, y1 = start_date.replace("-", ""), end_date.replace("-", "")
    try:
        raw_df = ak.stock_zh_a_hist(symbol=code, period=per, start_date=y0, end_date=y1, adjust=adj)
    except Exception as exc:
        _log(f"[kline] stock_zh_a_hist extended failed {symbol}: {exc}")
        return []
    df = _normalize_kline_df(raw_df)
    if df.empty:
        return []
    df = df[(df["Date"] >= pd.to_datetime(start_date)) & (df["Date"] <= pd.to_datetime(end_date))]
    return _dataframe_to_kline_candles(df)


def _fetch_index_kline(symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    import akshare as ak  # type: ignore

    symbol_key = symbol.upper()
    vendor_symbol = CN_INDEX_SYMBOL_MAP.get(symbol_key)
    if not vendor_symbol:
        return []

    yyyymmdd_start = start_date.replace("-", "")
    yyyymmdd_end = end_date.replace("-", "")
    last_exc: Exception | None = None

    for fetcher in (
        lambda: ak.stock_zh_index_daily_em(
            symbol=vendor_symbol,
            start_date=yyyymmdd_start,
            end_date=yyyymmdd_end,
        ),
        lambda: ak.stock_zh_index_daily(symbol=vendor_symbol),
        lambda: ak.index_zh_a_hist(
            symbol=symbol_key.split(".")[0],
            period="daily",
            start_date=yyyymmdd_start,
            end_date=yyyymmdd_end,
        ),
    ):
        try:
            raw_df = fetcher()
            df = _normalize_kline_df(raw_df)
            if df.empty:
                continue
            df = df[(df["Date"] >= pd.to_datetime(start_date)) & (df["Date"] <= pd.to_datetime(end_date))]
            if df.empty:
                continue
            return _dataframe_to_kline_candles(df)
        except Exception as exc:
            last_exc = exc
            continue

    if last_exc:
        _log(f"[kline] index fetch failed for {symbol}: {type(last_exc).__name__}: {last_exc}")
    return []


async def _stream_job_events(job_id: str, after: int = 0):
    store = get_job_store()
    rows = await asyncio.to_thread(analysis_job_service.fetch_events_after, job_id, after)
    if not rows and after == 0:
        yield _sse_pack("job.ready", {"job_id": job_id})
    terminal_hit = False
    for seq, evt_name, payload in rows:
        yield _sse_pack(evt_name, payload, event_id=seq)
        if evt_name in ("job.completed", "job.failed", "job.queued", "job.paused"):
            terminal_hit = True
    if terminal_hit:
        yield "event: done\ndata: [DONE]\n\n"
        return

    async for event in store.subscribe(job_id):
        evt_name = event["event"]
        eid = event.get("event_id")
        if isinstance(eid, str):
            try:
                eid = int(eid)
            except ValueError:
                eid = None
        yield _sse_pack(evt_name, event["data"], event_id=eid if isinstance(eid, int) else None)
        if evt_name in ("job.completed", "job.failed", "job.queued", "job.paused"):
            yield "event: done\ndata: [DONE]\n\n"
            return


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


# Simple in-memory rate limiter for version stats: {ip: last_timestamp}
_vs_rate_limit: Dict[str, float] = {}
_VS_RATE_INTERVAL = 3600  # at most once per hour per IP


_MARKET_QUOTES_CACHE_TTL = 10.0
_MARKET_QUOTES_MAX_SYMBOLS = 50
_MARKET_QUOTES_RATE_WINDOW = 60.0
_MARKET_QUOTES_RATE_MAX = 30
_market_quotes_cache: Dict[Tuple[str, ...], Tuple[float, Dict[str, Dict[str, Any]]]] = {}
_market_quotes_rate: Dict[str, List[float]] = {}
_market_quotes_lock = Lock()


def _normalize_market_quote_symbols(raw_symbols: List[str]) -> List[str]:
    symbols: List[str] = []
    seen: set[str] = set()
    for raw in raw_symbols:
        sym = normalize_exchange_symbol(str(raw or "")).strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        symbols.append(sym)
    return symbols


def _enforce_market_quote_rate_limit(user_id: str) -> None:
    now = time.time()
    with _market_quotes_lock:
        recent = [t for t in _market_quotes_rate.get(user_id, []) if now - t < _MARKET_QUOTES_RATE_WINDOW]
        if len(recent) >= _MARKET_QUOTES_RATE_MAX:
            _market_quotes_rate[user_id] = recent
            raise HTTPException(status_code=429, detail="实时行情请求过于频繁，请稍后再试")
        recent.append(now)
        _market_quotes_rate[user_id] = recent


def _get_cached_market_quotes(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    key = tuple(symbols)
    now = time.time()
    with _market_quotes_lock:
        cached = _market_quotes_cache.get(key)
        if cached and cached[0] > now:
            return deepcopy(cached[1])

    quotes = tracking_board_service._fetch_live_quotes(symbols)
    filtered = {
        sym: dict(quotes.get(sym) or {})
        for sym in symbols
        if isinstance(quotes.get(sym), dict) and quotes.get(sym)
    }

    with _market_quotes_lock:
        _market_quotes_cache[key] = (time.time() + _MARKET_QUOTES_CACHE_TTL, deepcopy(filtered))
    return filtered


@app.post("/v1/market/quotes", response_model=MarketQuotesResponse)
def get_market_quotes(
    request: MarketQuotesRequest,
    current_user: UserDB = Depends(_require_api_user),
) -> MarketQuotesResponse:
    symbols = _normalize_market_quote_symbols(request.symbols)
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols 不能为空")
    if len(symbols) > _MARKET_QUOTES_MAX_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"实时行情每次最多查询 {_MARKET_QUOTES_MAX_SYMBOLS} 个标的")

    _enforce_market_quote_rate_limit(current_user.id)
    quotes = _get_cached_market_quotes(symbols)
    missing = [sym for sym in symbols if sym not in quotes]
    return MarketQuotesResponse(
        quotes=quotes,
        missing=missing,
        cache_ttl_seconds=int(_MARKET_QUOTES_CACHE_TTL),
    )


@app.post("/api/version-stats")
def version_stats(payload: Dict[str, Any] = Body(...), request: Request = None, db: Session = Depends(get_db)):
    """Collect anonymous version statistics from deployed instances."""
    remote_ip = _get_real_ip(request)

    # Rate limit by IP
    now = time.time()
    if remote_ip:
        last = _vs_rate_limit.get(remote_ip, 0)
        if now - last < _VS_RATE_INTERVAL:
            return {"status": "ok"}
        _vs_rate_limit[remote_ip] = now

    record = VersionStatsDB(
        version=str(payload.get("v", ""))[:50],
        nonce=str(payload.get("nonce", ""))[:64],
        remote_ip=remote_ip,
    )
    db.add(record)
    db.commit()
    return {"status": "ok"}


def _load_kline_candles_unsafe(
    symbol: str,
    start: str,
    end: str,
    period: Literal["1d", "1w", "1mo"] = "1d",
    adjust: Literal["none", "qfq", "hfq"] = "none",
) -> List[Dict[str, Any]]:
    use_legacy = period == "1d" and adjust == "none"
    sym_u = symbol.strip()
    if not use_legacy and not _cn_symbol_supports_extended_kline(sym_u):
        return []

    if use_legacy:
        if _is_cn_index_symbol(sym_u):
            return _fetch_index_kline(sym_u, start, end)
        sym_norm = _normalize_symbol(sym_u)
        # 个股日 K：与周 K/月 K 一致，优先 AkShare stock_zh_a_hist（周月已验证可用）。
        # 旧逻辑先走 vendor CSV，若 CSV 能解析但数据不对，会跳过 AkShare，导致「只有日 K 不出来」。
        if _cn_symbol_supports_extended_kline(sym_norm):
            ak_hist = _fetch_stock_kline_ak_hist(sym_norm, start, end, "1d", "none")
            if ak_hist:
                return ak_hist
        config = _build_runtime_config({})
        set_config(config)
        try:
            raw = route_to_vendor("get_stock_data", sym_norm, start, end)
            parsed = _parse_stock_csv(raw) or []
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning("[kline] get_stock_data/parsed failed %s: %s", sym_norm, exc)
        return []
    if _is_cn_index_symbol(sym_u):
        return _fetch_index_kline_ak_hist(sym_u, start, end, period)
    sym_norm = _normalize_symbol(sym_u)
    if not _cn_symbol_supports_extended_kline(sym_norm):
        return []
    return _fetch_stock_kline_ak_hist(sym_norm, start, end, period, adjust)


_KLINE_CACHE_TODAY_TTL = 45.0
_KLINE_CACHE_HISTORY_TTL = 900.0
_kline_cache: Dict[Tuple[str, str, str, str, str], Tuple[float, List[Dict[str, Any]]]] = {}
_kline_inflight: Dict[Tuple[str, str, str, str, str], Future[List[Dict[str, Any]]]] = {}
_kline_cache_lock = Lock()


def _kline_cache_ttl(end: str) -> float:
    try:
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        today = datetime.strptime(cn_today_str(), "%Y-%m-%d").date()
    except Exception:
        return _KLINE_CACHE_TODAY_TTL
    return _KLINE_CACHE_TODAY_TTL if end_date >= today else _KLINE_CACHE_HISTORY_TTL


def _load_kline_candles_cached(
    symbol: str,
    start: str,
    end: str,
    period: Literal["1d", "1w", "1mo"] = "1d",
    adjust: Literal["none", "qfq", "hfq"] = "none",
) -> List[Dict[str, Any]]:
    key = (symbol.strip().upper(), start, end, period, adjust)
    now = time.time()
    with _kline_cache_lock:
        cached = _kline_cache.get(key)
        if cached and cached[0] > now:
            return deepcopy(cached[1])
        future = _kline_inflight.get(key)
        if future is None:
            future = Future()
            _kline_inflight[key] = future
            is_owner = True
        else:
            is_owner = False

    if not is_owner:
        return deepcopy(future.result())

    try:
        candles = _load_kline_candles_unsafe(symbol, start, end, period, adjust)
        ttl = _kline_cache_ttl(end)
        with _kline_cache_lock:
            if candles:
                _kline_cache[key] = (time.time() + ttl, deepcopy(candles))
            else:
                _kline_cache.pop(key, None)
            _kline_inflight.pop(key, None)
        future.set_result(deepcopy(candles))
        logger.info("[kline] cache miss key=%s rows=%s ttl=%ss", key, len(candles), int(ttl))
        return candles
    except Exception as exc:
        with _kline_cache_lock:
            _kline_inflight.pop(key, None)
        future.set_exception(exc)
        raise


def _load_kline_candles(
    symbol: str,
    start: str,
    end: str,
    period: Literal["1d", "1w", "1mo"] = "1d",
    adjust: Literal["none", "qfq", "hfq"] = "none",
) -> List[Dict[str, Any]]:
    try:
        return _load_kline_candles_cached(symbol, start, end, period, adjust)
    except Exception:
        logger.exception("[kline] load pipeline failed symbol=%r period=%s adjust=%s", symbol, period, adjust)
        return []


def _parse_iso_date_param(label: str, value: str) -> str:
    """Validate YYYY-MM-DD; raise HTTP 400 instead of letting ValueError become 500."""
    v = (value or "").strip()
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{label}日期须为 YYYY-MM-DD 格式") from exc
    return v


@app.get("/v1/market/kline", response_model=KlineResponse)
def get_kline(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: Literal["1d", "1w", "1mo"] = Query("1d"),
    adjust: Literal["none", "qfq", "hfq"] = Query("none"),
) -> KlineResponse:
    try:
        sym = symbol.strip()
        if not sym:
            raise HTTPException(status_code=400, detail="symbol 不能为空")

        raw_end = (end_date or "").strip()
        raw_start = (start_date or "").strip()

        if raw_end:
            end = _parse_iso_date_param("结束", raw_end)
        else:
            end = cn_today_str()

        if raw_start:
            start = _parse_iso_date_param("开始", raw_start)
        else:
            start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=120)).strftime("%Y-%m-%d")

        d_s = datetime.strptime(start, "%Y-%m-%d").date()
        d_e = datetime.strptime(end, "%Y-%m-%d").date()
        if d_s > d_e:
            d_s, d_e = d_e, d_s
        start = d_s.strftime("%Y-%m-%d")
        end = d_e.strftime("%Y-%m-%d")

        if not (period == "1d" and adjust == "none") and not _cn_symbol_supports_extended_kline(sym):
            raise HTTPException(
                status_code=400,
                detail="非 A 股标的暂仅支持日K、不复权；请使用 period=1d&adjust=none",
            )

        sym = _normalize_symbol(sym)
        candles = _load_kline_candles(sym, start, end, period, adjust)
        if not candles:
            raise HTTPException(status_code=404, detail="no kline data")
        code_to_name = _get_reverse_stock_map()
        dl_payload = {"symbol": sym}
        symbol_service.enrich_dict_with_display(dl_payload, code_to_name=code_to_name)
        return KlineResponse(
            symbol=sym,
            display_label=dl_payload.get("display_label"),
            start_date=start,
            end_date=end,
            candles=jsonable_encoder(candles),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[kline] unhandled error symbol=%s", symbol)
        raise HTTPException(
            status_code=503,
            detail=f"K线暂不可用：{type(exc).__name__}",
        ) from exc


_CHART_INSIGHT_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_CHART_INSIGHT_RATE: Dict[str, List[float]] = {}
_CHART_CACHE_TTL = 600.0
_CHART_RATE_MAX = 6
_CHART_RATE_WINDOW = 60.0


@app.post("/v1/market/chart/insight", response_model=ChartInsightResponsePayload)
def chart_insight_endpoint(
    request: ChartInsightRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
) -> ChartInsightResponsePayload:
    from tradingagents.analytics.ta_features import build_fallback_insight, extract_features
    from tradingagents.analytics.insight_prompt import build_chart_insight_system_prompt, build_chart_insight_user_prompt
    from tradingagents.llm_clients.factory import create_llm_client

    from api.services.entitlements_service import user_has_advanced_market
    from api.services.market_advanced_service import collect_insight_context

    now = time.time()
    uid = str(current_user.id)
    window = _CHART_INSIGHT_RATE.setdefault(uid, [])
    window[:] = [t for t in window if now - t < _CHART_RATE_WINDOW]
    if len(window) >= _CHART_RATE_MAX:
        raise HTTPException(status_code=429, detail="解读请求过频，请稍后再试")
    window.append(now)

    end = request.end_date or cn_today_str()
    start = request.start_date or (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=180)).strftime("%Y-%m-%d")
    ctx_level = (request.context_level or "basic").strip().lower()
    if ctx_level not in ("basic", "advanced"):
        ctx_level = "basic"

    adv_digest = ""
    adv_payload: Optional[Dict[str, Any]] = None
    if ctx_level == "advanced":
        if not user_has_advanced_market(db, current_user):
            raise HTTPException(status_code=403, detail="需要高级 VIP 行情权益（管理员默认可用）")
        adv_payload = collect_insight_context(request.symbol, for_chart_insight=True)
        adv_digest = hashlib.md5(
            json.dumps(adv_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]

    cache_key = (
        f"{uid}|{request.symbol.upper()}|{request.period}|{request.adjust}|{start}|{end}|"
        f"{request.level}|{ctx_level}|{adv_digest}"
    )
    if not request.bypass_cache and cache_key in _CHART_INSIGHT_CACHE:
        exp, ins = _CHART_INSIGHT_CACHE[cache_key]
        if time.time() < exp:
            return ChartInsightResponsePayload(insight=ins, cached=True, fallback_only=ins.get("_fallback") is True)

    cfg = _build_runtime_config({}, user_id=uid, db=db)
    candles = _load_kline_candles(request.symbol, start, end, request.period, request.adjust)
    if not candles:
        raise HTTPException(status_code=404, detail="no kline data for insight")

    features = extract_features(candles, level=request.level)
    if adv_payload is not None:
        features["advanced_market_context"] = adv_payload

    fallback = build_fallback_insight(features, request.symbol, level=request.level)
    prompt_user = build_chart_insight_user_prompt(
        request.symbol, features, request.level, request.language
    )
    system_prompt = build_chart_insight_system_prompt(request.level, include_advanced=adv_payload is not None)

    insight_dict: Dict[str, Any] = dict(fallback)
    llm_ok = False

    lvl = (request.level or "normal").strip().lower()
    # 与前端一致：brief=快速 / normal=标准 / deep=专业（均 POST 当前 K 线特征至 LLM）
    if lvl not in ("brief", "normal", "deep"):
        lvl = "normal"
    # Chart insight: prefer faster fallback over hanging UI (full LLM timeouts used elsewhere)
    # 专业档需要更长 JSON 输出；默认 max_tokens 过小会导致截断→解析失败→退回简短 fallback，观感像「快速版」
    if lvl == "deep":
        model_name = str(cfg.get("deep_think_llm") or cfg.get("quick_think_llm") or "gpt-4o-mini")
        invoke_timeout = 52.0
        max_out_tokens = 6144
    elif lvl == "brief":
        model_name = str(cfg.get("quick_think_llm") or "gpt-4o-mini")
        invoke_timeout = 26.0
        max_out_tokens = 1536
    else:
        model_name = str(cfg.get("quick_think_llm") or "gpt-4o-mini")
        invoke_timeout = 38.0
        max_out_tokens = 3584

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        client = create_llm_client(
            provider=str(cfg.get("llm_provider") or "openai"),
            model=model_name,
            base_url=cfg.get("backend_url"),
            api_key=cfg.get("api_key"),
            timeout=invoke_timeout,
            max_retries=0,
            max_tokens=max_out_tokens,
        )
        llm = client.get_llm()
        raw = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt_user),
            ]
        )
        text = raw if isinstance(raw, str) else getattr(raw, "content", str(raw))
        m = re.search(r"\{[\s\S]*\}\s*$", str(text).strip())
        if m:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict) and "summary_plain" in parsed:
                insight_dict = parsed
                llm_ok = True
    except Exception as exc:
        logger.warning("[chart_insight] llm failed: %s", exc)

    if not llm_ok:
        insight_dict = dict(fallback)

    clean = {k: v for k, v in insight_dict.items() if k != "_fallback"}
    _CHART_INSIGHT_CACHE[cache_key] = (time.time() + _CHART_CACHE_TTL, clean)
    return ChartInsightResponsePayload(
        insight=clean,
        fallback_only=not llm_ok,
        cached=False,
    )


def _normalize_ths_code(code: str) -> str:
    """Convert THS/XQ code like SH601xxx → 601xxx.SH"""
    code = str(code).strip()
    if code.upper().startswith("SH"):
        return f"{code[2:]}.SH"
    if code.upper().startswith("SZ"):
        return f"{code[2:]}.SZ"
    if code.upper().startswith("BJ") or code.upper().startswith("NQ"):
        return f"{code[2:]}.BJ"
    # Bare 6-digit code — guess exchange
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    if code.startswith(("0", "3", "2")):
        return f"{code}.SZ"
    return code


@app.get("/v1/market/hot-stocks")
def get_hot_stocks(source: str = "em", limit: int = 30) -> Dict:
    """Return hot A-share stocks from different sources.
    
    Args:
        source: Data source selection
            - 'em': 东方财富热榜 (EastMoney hot stocks)
            - 'xq': 雪球热门 (Xueqiu most-followed stocks)
            - 'ths': 连涨榜 (Consecutive rising stocks, not general hot list)
        limit: Maximum number of stocks to return
    
    Returns:
        Dict with stocks list, total count, source info, and fallback status
    """
    import akshare as ak

    # 定义数据源尝试顺序（如果主数据源失败，自动尝试备用源）
    source_configs = {
        "em": ("stock_hot_rank_em", None, "东方财富热榜"),
        "xq": ("stock_hot_follow_xq", "最热门", "雪球热门"),
        "ths": ("stock_rank_lxsz_ths", None, "连涨榜"),
    }

    if source not in source_configs:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")

    # 尝试主数据源，失败则尝试其他源
    sources_to_try = [source] + [s for s in ["xq", "em", "ths"] if s != source]
    last_error = None

    for src in sources_to_try:
        try:
            func_name, param, desc = source_configs[src]
            func = getattr(ak, func_name)

            # 调用 akshare 函数
            if param:
                df = func(symbol=param).head(limit)
            else:
                df = func().head(limit)

            stocks = []

            if src == "em":
                for i, (_, row) in enumerate(df.iterrows()):
                    stocks.append({
                        "rank": i + 1,
                        "symbol": _normalize_ths_code(str(row.get("代码", ""))),
                        "name": str(row.get("股票名称", "")),
                        "price": float(row.get("最新价", 0) or 0),
                        "change": float(row.get("涨跌额", 0) or 0),
                        "change_pct": float(row.get("涨跌幅", 0) or 0),
                        "extra": "",
                    })

            elif src == "xq":
                for i, (_, row) in enumerate(df.iterrows()):
                    stocks.append({
                        "rank": i + 1,
                        "symbol": _normalize_ths_code(str(row.get("股票代码", ""))),
                        "name": str(row.get("股票简称", "")),
                        "price": float(row.get("最新价", 0) or 0),
                        "change": 0.0,
                        "change_pct": 0.0,
                        "extra": f"关注 {int(row.get('关注', 0)):,}",
                    })

            elif src == "ths":
                for i, (_, row) in enumerate(df.iterrows()):
                    days = int(row.get("连涨天数", 0) or 0)
                    change_pct = float(row.get("连续涨跌幅", 0) or 0)
                    stocks.append({
                        "rank": i + 1,
                        "symbol": _normalize_ths_code(str(row.get("股票代码", ""))),
                        "name": str(row.get("股票简称", "")),
                        "price": float(row.get("收盘价", 0) or 0),
                        "change": 0.0,
                        "change_pct": change_pct,
                        "extra": f"连涨{days}天",
                    })

            # 成功获取数据
            fallback_msg = f" (fallback from {source_configs[source][2]})" if src != source else ""
            _log(f"Hot stocks: successfully fetched from {desc}{fallback_msg}")
            return {
                "stocks": stocks,
                "total": len(stocks),
                "source": src,
                "requested_source": source,
                "fallback": src != source,
            }

        except Exception as e:
            last_error = e
            _log(f"Hot stocks: {desc} failed - {type(e).__name__}: {str(e)[:100]}")
            continue

    # 所有数据源都失败
    raise HTTPException(
        status_code=503,
        detail=f"All data sources failed. Last error: {type(last_error).__name__}: {str(last_error)[:200]}"
    )


@app.post("/v1/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    current_user: UserDB = Depends(_require_api_user),
) -> AnalyzeResponse:
    request.symbol = _normalize_symbol((request.symbol or "").strip())
    if not request.dry_run:
        need = credits_service.analysis_cost()
        if need > 0:
            with get_db_ctx() as db:
                if credits_service.get_balance(db, current_user.id) < need:
                    raise HTTPException(
                        status_code=402,
                        detail="insufficient_credits",
                    )
    with get_db_ctx() as db:
        merged_user_context = _compose_analysis_user_context(
            db,
            current_user.id,
            request.symbol,
            explicit_context=_extract_request_user_context(request),
        )
    _apply_user_context_to_request(request, merged_user_context)

    job_id = uuid4().hex
    now = _utcnow_iso()
    with get_db_ctx() as db:
        analysis_job_service.upsert_job_row(
            db,
            job_id,
            user_id=current_user.id,
            symbol=request.symbol,
            trade_date=request.trade_date,
            status="pending",
            request_payload=request.model_dump(mode="json"),
            request_source="api",
            dry_run=request.dry_run,
        )
    _set_job(
        job_id,
        job_id=job_id,
        user_id=current_user.id,
        status="pending",
        created_at=now,
        started_at=None,
        finished_at=None,
        symbol=request.symbol,
        trade_date=request.trade_date,
        error=None,
        result=None,
        decision=None,
    )
    _emit_job_event(
        job_id,
        "job.created",
        {"job_id": job_id, "symbol": request.symbol, "trade_date": request.trade_date},
    )
    if request.dry_run:
        await _run_job(job_id, request, True, True, current_user.id, "api")
        final_status = _get_job(job_id).get("status", "completed")
        return AnalyzeResponse(job_id=job_id, status=final_status, created_at=now)

    queue_status, _waiting_ahead_count = await _enqueue_or_start_job(
        job_id,
        request,
        user_id=current_user.id,
        request_source="api",
    )
    if queue_status == "queued":
        return AnalyzeResponse(job_id=job_id, status="queued", created_at=now)
    if queue_status == "rejected":
        raise HTTPException(
            status_code=409,
            detail=f"排队已满（最多 {task_queue_service.max_queue_size()} 个），请在任务中心处理后再提交",
        )

    _create_tracked_task(_run_job(job_id, request, True, True, current_user.id, "api"))
    return AnalyzeResponse(job_id=job_id, status="pending", created_at=now)


def _require_job_owner(job_id: str, current_user: UserDB) -> Dict[str, Any]:
    job = _get_job(job_id)
    if not job:
        _try_hydrate_job_from_db(job_id)
        job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    owner_id = job.get("user_id")
    if not owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="job ownership could not be verified",
        )
    if str(owner_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _report_job_snapshot(job_id: str, current_user: UserDB) -> Optional[Dict[str, Any]]:
    """Fallback job snapshot from the persisted report row after an API restart.

    The live JobStore is in-memory by default, so uvicorn reloads lose job state even though
    partial report rows are already persisted. Returning a terminal snapshot lets clients
    recover cleanly instead of surfacing a raw 404.
    """
    with get_db_ctx() as db:
        report = report_service.get_report(db, job_id, user_id=current_user.id)
        if not report:
            return None

        st = str(report.status or "")
        needs_job_hydrate = (
            st in report_service.ACTIVE_REPORT_STATUSES
            or (
                st == "failed"
                and str(report.error or "").strip() == report_service.STALE_REPORT_ERROR_MESSAGE
            )
        )
        if needs_job_hydrate:
            if not _get_job(job_id):
                _try_hydrate_job_from_db(job_id)
            _reconcile_stale_running_report_from_job(db, report, str(current_user.id))
            try:
                db.refresh(report)
            except Exception:
                pass
            if str(report.status or "") in report_service.ACTIVE_REPORT_STATUSES and not _get_job(job_id):
                report = report_service.finalize_orphan_report(db, report)

        status_value = str(report.status or "failed")
        if status_value not in {"pending", "queued", "paused", "running", "completed", "failed"}:
            status_value = "failed"
        terminal_time = report.updated_at if status_value in {"completed", "failed"} else None
        return {
            "job_id": report.id,
            "status": status_value,
            "created_at": _serialize_datetime_utc(report.created_at) or "",
            "started_at": None,
            "finished_at": _serialize_datetime_utc(terminal_time),
            "symbol": report.symbol,
            "trade_date": report.trade_date,
            "error": report.error,
            "decision": report.decision,
            "direction": report.direction,
            "confidence": report.confidence,
            "target_price": report.target_price,
            "stop_loss_price": report.stop_loss_price,
            "result": report.result_data,
            "risk_items": report.risk_items or [],
            "key_metrics": report.key_metrics or [],
        }


def _require_job_or_report_snapshot(job_id: str, current_user: UserDB) -> Dict[str, Any]:
    try:
        return _require_job_owner(job_id, current_user)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        snapshot = _report_job_snapshot(job_id, current_user)
        if snapshot:
            return snapshot
        raise


@app.get("/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, current_user: UserDB = Depends(_require_api_user)) -> JobStatusResponse:
    job = _require_job_or_report_snapshot(job_id, current_user)
    _maybe_kick_queue_for_job(job)
    status_value = str(job.get("status") or "failed")
    if status_value == "resuming":
        status_value = "running"
    cmap = _get_reverse_stock_map()
    dl_row = {"symbol": job["symbol"]}
    symbol_service.enrich_dict_with_display(dl_row, code_to_name=cmap)
    return JobStatusResponse(
        job_id=job["job_id"],
        status=status_value,
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        symbol=job["symbol"],
        trade_date=job["trade_date"],
        error=job.get("error"),
        waiting_ahead_count=job.get("waiting_ahead_count"),
        scheduled_running_count=job.get("scheduled_running_count"),
        scheduled_concurrency_limit=job.get("scheduled_concurrency_limit"),
        display_label=dl_row.get("display_label"),
    )


@app.get("/v1/jobs/{job_id}/result")
def get_job_result(job_id: str, current_user: UserDB = Depends(_require_api_user)) -> Dict[str, Any]:
    job = _require_job_or_report_snapshot(job_id, current_user)
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"job status is {job['status']}")
    return {
        "job_id": job_id,
        "status": job["status"],
        "decision": job.get("decision"),
        "result": job.get("result"),
        "finished_at": job.get("finished_at"),
    }


@app.get("/v1/jobs/{job_id}/events")
def stream_job_events(
    job_id: str,
    after: int = Query(0, ge=0),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    current_user: UserDB = Depends(_require_api_user),
):
    cursor = after
    if last_event_id:
        try:
            cursor = max(cursor, int(last_event_id))
        except ValueError:
            pass

    job = _require_job_or_report_snapshot(job_id, current_user)
    if job["status"] in ("completed", "failed") and not _get_job(job_id):
        async def _terminal_report_stream():
            rows = await asyncio.to_thread(analysis_job_service.fetch_events_after, job_id, cursor)
            if not rows and cursor == 0:
                yield _sse_pack("job.ready", {"job_id": job_id})
            had_terminal = False
            for seq, evt_name, payload in rows:
                yield _sse_pack(evt_name, payload, event_id=seq)
                if evt_name in ("job.completed", "job.failed"):
                    had_terminal = True
            if not had_terminal:
                if job["status"] == "completed":
                    yield _sse_pack(
                        "job.completed",
                        {
                            "job_id": job_id,
                            "decision": job.get("decision"),
                            "direction": job.get("direction"),
                            "result": job.get("result"),
                            "risk_items": job.get("risk_items") or [],
                            "key_metrics": job.get("key_metrics") or [],
                            "confidence": job.get("confidence"),
                            "target_price": job.get("target_price"),
                            "stop_loss_price": job.get("stop_loss_price"),
                        },
                    )
                else:
                    yield _sse_pack(
                        "job.failed",
                        {"job_id": job_id, "error": job.get("error") or report_service.STALE_REPORT_ERROR_MESSAGE},
                    )
            yield "event: done\ndata: [DONE]\n\n"

        return StreamingResponse(
            _terminal_report_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _stream_job_events(job_id, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/v1/jobs/{job_id}/resume")
async def resume_analysis_job(job_id: str, current_user: UserDB = Depends(_require_api_user)) -> Dict[str, Any]:
    """Explicitly reclaim/resume a stale or interrupted job (same body as startup reconcile)."""
    with get_db_ctx() as db:
        row = analysis_job_service.get_job_row(db, job_id)
        if not row or str(row.user_id or "") != str(current_user.id):
            raise HTTPException(status_code=404, detail="job not found")
        if row.status in ("completed", "failed"):
            raise HTTPException(status_code=409, detail="job already finished")
        if not row.request_payload:
            raise HTTPException(status_code=409, detail="job has no persisted request; cannot resume")
        if not analysis_job_service.try_claim_for_resume(db, job_id, TA_INSTANCE_ID):
            raise HTTPException(status_code=409, detail="job is being resumed elsewhere")
        payload = dict(row.request_payload)
        src = row.request_source or "api"
    req = AnalyzeRequest.model_validate(payload)
    _create_tracked_task(
        _run_job(job_id, req, True, True, current_user.id, src, resume_mode=True),
        label=f"manual-resume-{job_id[:8]}",
    )
    return {"status": "resuming", "job_id": job_id}


async def _cancel_analysis_job_core(job_id: str, current_user: UserDB) -> Dict[str, Any]:
    """POST /v1/jobs/{id}/cancel 与报告删除前终止任务共用（须在已鉴权上下文中调用）。"""
    with get_db_ctx() as db:
        row = analysis_job_service.get_job_row(db, job_id)
        if not row or str(row.user_id or "") != str(current_user.id):
            raise HTTPException(status_code=404, detail="job not found")
        if row.status in ("completed", "failed"):
            raise HTTPException(status_code=409, detail="job already finished")
        if row.status in ("queued", "paused"):
            removed = task_queue_service.remove_queued_job(db, user_id=current_user.id, job_id=job_id)
            if not removed:
                raise HTTPException(status_code=409, detail="job is not queued")
            _set_job(job_id, status="failed", error="用户已取消排队任务", finished_at=_utcnow_iso())
            _emit_job_event(
                job_id,
                "job.failed",
                {"job_id": job_id, "error": "用户已取消排队任务"},
            )
            task_queue_service.request_schedule(current_user.id)
            return {"status": "cancelled", "job_id": job_id}

    async with _running_analysis_inner_tasks_lock:
        inner_task = _running_analysis_inner_tasks.get(job_id)

    if inner_task is None or inner_task.done():
        # Fallback: the in-memory task map may be empty after process restart/reload.
        # For single-node UX, allow user-initiated cancellation to converge state.
        with get_db_ctx() as db:
            row = analysis_job_service.get_job_row(db, job_id)
            if not row or str(row.user_id or "") != str(current_user.id):
                raise HTTPException(status_code=404, detail="job not found")
            if row.status in ("completed", "failed"):
                raise HTTPException(status_code=409, detail="job already finished")
            analysis_job_service.persist_store_fields(
                db,
                job_id,
                {"status": "failed", "error": "用户已取消任务", "user_id": current_user.id},
            )
            analysis_job_service.release_lease(db, job_id)
        _set_job(job_id, status="failed", error="用户已取消任务", finished_at=_utcnow_iso())
        _emit_job_event(
            job_id,
            "job.failed",
            {"job_id": job_id, "error": "用户已取消任务"},
        )
        task_queue_service.request_schedule(current_user.id)
        return {"status": "cancelled", "job_id": job_id}

    inner_task.cancel()
    return {"status": "cancel_requested", "job_id": job_id}


@app.post("/v1/jobs/{job_id}/cancel")
async def cancel_analysis_job(job_id: str, current_user: UserDB = Depends(_require_api_user)) -> Dict[str, Any]:
    """请求取消当前进程内正在运行的分析任务（单实例部署）；完成后通过 SSE 下发 job.failed。"""
    return await _cancel_analysis_job_core(job_id, current_user)


async def _ai_extract_symbol_and_date_streaming(
    text: str, config: Dict[str, Any], job_id: str
) -> tuple[Optional[str], Optional[str], List[str], List[str], List[str], Dict[str, Any]]:
    """
    Async streaming version of _ai_extract_symbol_and_date.
    Emits agent.token events so the frontend can show streaming output during extraction.
    """
    from tradingagents.llm_clients.factory import create_llm_client
    import json as _json

    today = datetime.now().strftime("%Y-%m-%d")
    llm_name: Optional[str] = None
    llm_date: Optional[str] = None
    llm_horizons: List[str] = ["short"]
    llm_focus_areas: List[str] = []
    llm_specific_questions: List[str] = []
    llm_user_context: Dict[str, Any] = {}

    try:
        client = create_llm_client(
            provider=config.get("llm_provider", "openai"),
            model=config.get("quick_think_llm"),
            base_url=config.get("backend_url"),
            api_key=config.get("api_key"),
        )
        prompt = f"""你是金融数据助手。从用户消息中提取以下字段并以 JSON 输出。

字段说明：
- stock_name：用户提到的公司名称或股票代码原文（如"华盛天成"、"贵州茅台"、"600519"、"AAPL"）；美股直接填 ticker。
- date：YYYY-MM-DD 格式。今天是 {today}，如未提及则填今天。
- horizons：分析周期，只能选一个：
  * 用户明确提到"中线/中期/几个月/季度/长期/趋势投资"→ ["medium"]
  * 其他所有情况（含未提及）→ ["short"]
- focus_areas：用户关注的分析维度关键词列表，如 ["技术面", "资金面", "业绩"]，未提及则 []。
- specific_questions：用户提出的具体问题列表，如 ["近期有无催化剂？", "主力是否出货？"]，未提及则 []。
- user_context：从自然语言中提取的账户与约束对象。若未提及返回 {{}}。可包含：
  * objective：建仓 / 加仓 / 减仓 / 止损 / 观察 / 持有处理
  * risk_profile：保守 / 平衡 / 激进
  * investment_horizon：短线 / 波段 / 中线 / 长期
  * cash_available / current_position / current_position_pct / average_cost / max_loss_pct：数字
  * constraints：字符串数组
  * user_notes：仅保留重要但未能结构化归类的信息

仅输出 JSON，不要任何其他文字：
{{"stock_name": "...", "date": "YYYY-MM-DD", "horizons": ["short"], "focus_areas": [], "specific_questions": [], "user_context": {{}}}}

如果无法识别股票标的：{{"stock_name": null, "date": null, "horizons": ["short"], "focus_areas": [], "specific_questions": [], "user_context": {{}}}}

用户消息："{text}"
"""
        llm = client.get_llm()
        _log(f"[LLM Debug] Streaming StockExtract with model: {getattr(llm, 'model_name', 'unknown')}")

        full_content = ""
        async for chunk in llm.astream(prompt):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_content += token
            if token:
                _emit_job_event(job_id, "agent.token", {
                    "agent": "意图解析",
                    "report": "stock_extract",
                    "token": token,
                })

        _log(f"[LLM Debug] StockExtract response: {full_content[:200]}")
        m = re.search(r"\{.*\}", full_content, re.DOTALL)
        if m:
            data = _json.loads(m.group(0))
            llm_name = (data.get("stock_name") or "").strip() or None
            llm_date = data.get("date") or today
            llm_horizons = data.get("horizons") or ["short"]
            llm_focus_areas = data.get("focus_areas") or []
            llm_specific_questions = data.get("specific_questions") or []
            llm_user_context = normalize_user_context(data.get("user_context") or {})
    except Exception as e:
        _log(f"[StockExtract streaming] LLM failed: {e}")

    if not llm_name:
        return None, None, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

    _log(f"[StockExtract] extracted name='{llm_name}', date={llm_date}, horizons={llm_horizons}")
    if re.match(r"^\d{6}$", llm_name) or re.match(r"^[A-Za-z]{1,6}(\.[A-Za-z]+)?$", llm_name):
        symbol = _normalize_symbol(llm_name)
        return symbol or None, llm_date, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

    local_code = await asyncio.to_thread(_search_cn_stock_by_name, llm_name)
    if local_code:
        return local_code, llm_date, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

    fallback = _normalize_symbol(llm_name)
    if fallback:
        return fallback, llm_date, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

    return None, llm_date, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context


def _ai_extract_symbol_and_date(
    text: str, config: Dict[str, Any]
) -> tuple[Optional[str], Optional[str], List[str], List[str], List[str], Dict[str, Any]]:
    """
    Single-LLM extraction: stock name, date, horizons, focus_areas, specific_questions.
    Then resolves the stock name to an authoritative code via akshare.
    Returns (symbol, date, horizons, focus_areas, specific_questions, inferred_user_context).
    """
    from tradingagents.llm_clients.factory import create_llm_client
    import json as _json

    today = datetime.now().strftime("%Y-%m-%d")

    llm_name: Optional[str] = None
    llm_date: Optional[str] = None
    llm_horizons: List[str] = ["short"]
    llm_focus_areas: List[str] = []
    llm_specific_questions: List[str] = []
    llm_user_context: Dict[str, Any] = {}
    try:
        client = create_llm_client(
            provider=config.get("llm_provider", "openai"),
            model=config.get("quick_think_llm"),
            base_url=config.get("backend_url"),
            api_key=config.get("api_key"),
        )
        prompt = f"""你是金融数据助手。从用户消息中提取以下字段并以 JSON 输出。

字段说明：
- stock_name：用户提到的公司名称或股票代码原文（如"华盛天成"、"贵州茅台"、"600519"、"AAPL"）；美股直接填 ticker。
- date：YYYY-MM-DD 格式。今天是 {today}，如未提及则填今天。
- horizons：分析周期，只能选一个：
  * 用户明确提到"中线/中期/几个月/季度/长期/趋势投资"→ ["medium"]
  * 其他所有情况（含未提及）→ ["short"]
- focus_areas：用户关注的分析维度关键词列表，如 ["技术面", "资金面", "业绩"]，未提及则 []。
- specific_questions：用户提出的具体问题列表，如 ["近期有无催化剂？", "主力是否出货？"]，未提及则 []。
- user_context：从自然语言中提取的账户与约束对象。若未提及返回 {{}}。可包含：
  * objective：建仓 / 加仓 / 减仓 / 止损 / 观察 / 持有处理
  * risk_profile：保守 / 平衡 / 激进
  * investment_horizon：短线 / 波段 / 中线 / 长期
  * cash_available / current_position / current_position_pct / average_cost / max_loss_pct：数字
  * constraints：字符串数组
  * user_notes：仅保留重要但未能结构化归类的信息

仅输出 JSON，不要任何其他文字：
{{"stock_name": "...", "date": "YYYY-MM-DD", "horizons": ["short"], "focus_areas": [], "specific_questions": [], "user_context": {{}}}}

如果无法识别股票标的：{{"stock_name": null, "date": null, "horizons": ["short"], "focus_areas": [], "specific_questions": [], "user_context": {{}}}}

用户消息："{text}"
"""
        llm = client.get_llm()
        
        # 调试日志：打印请求参数
        target_url = getattr(llm, 'openai_api_base', 'default')
        _log(f"[LLM Debug] Requesting StockExtract with model: {getattr(llm, 'model_name', 'unknown')} at {target_url}")
        _log(f"[LLM Debug] Prompt: {prompt[:500]}...")

        response = llm.invoke(prompt)
        raw = response if isinstance(response, str) else getattr(response, "content", str(response))
        
        # 调试日志：打印原始响应
        _log(f"[LLM Debug] Raw Response: {raw}")

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = _json.loads(m.group(0))
            llm_name = (data.get("stock_name") or "").strip() or None
            llm_date = data.get("date") or today
            llm_horizons = data.get("horizons") or ["short"]
            llm_focus_areas = data.get("focus_areas") or []
            llm_specific_questions = data.get("specific_questions") or []
            llm_user_context = normalize_user_context(data.get("user_context") or {})
    except Exception as e:
        _log(f"[StockExtract] LLM failed: {e}")

    if not llm_name:
        _log(f"[StockExtract] LLM returned no stock name for: '{text[:40]}'")
        return None, None, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

    _log(f"[StockExtract] LLM extracted name='{llm_name}', date={llm_date}, horizons={llm_horizons}")

    # ── Step 2: If looks like a direct code (digits / letters), normalize it ──
    if re.match(r"^\d{6}$", llm_name) or re.match(r"^[A-Za-z]{1,6}(\.[A-Za-z]+)?$", llm_name):
        symbol = _normalize_symbol(llm_name)
        _log(f"[StockExtract] Direct code: {symbol}")
        return symbol or None, llm_date, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

    # ── Step 3: Search akshare A-share name database ──────────────────────────
    local_code = _search_cn_stock_by_name(llm_name)
    if local_code:
        _log(f"[StockExtract] akshare match: '{llm_name}' → {local_code}")
        return local_code, llm_date, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

    # ── Step 4: Last resort — treat LLM name as a raw code ────────────────────
    fallback = _normalize_symbol(llm_name)
    if fallback:
        _log(f"[StockExtract] Fallback normalize: '{llm_name}' → {fallback}")
        return fallback, llm_date, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

    _log(f"[StockExtract] Could not resolve '{llm_name}' to a stock code")
    return None, llm_date, llm_horizons, llm_focus_areas, llm_specific_questions, llm_user_context

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    current_user: UserDB = Depends(_require_api_user),
):
    text = _extract_chat_text(request.messages)
    config = await asyncio.to_thread(_build_runtime_config, request.config_overrides, user_id=current_user.id)

    # ── 流式模式：立刻返回 SSE 流，在后台异步提取意图再启动任务 ──────────────────
    # 这样用户提交查询后立刻收到 job.ready，不用等待 thinking 模型的 StockExtract。
    if request.stream:
        job_id = uuid4().hex

        async def _extract_and_run():
            try:
                symbol, trade_date, horizons, focus_areas, specific_questions, inferred_user_context = \
                    await _ai_extract_symbol_and_date_streaming(text, config, job_id)

                if not symbol:
                    _emit_job_event(job_id, "job.failed", {
                        "error": "抱歉，我没能从您的消息中识别出股票标的。请输入代码（如 600519.SH）或可识别的公司名称。"
                    })
                    return

                pre_intent = {
                    "raw_query": text,
                    "ticker": symbol,
                    "horizons": horizons,
                    "focus_areas": focus_areas,
                    "specific_questions": specific_questions,
                }
                with get_db_ctx() as db:
                    merged_user_context = _compose_analysis_user_context(
                        db,
                        current_user.id,
                        symbol,
                        explicit_context=_extract_request_user_context(request),
                        inferred_context=inferred_user_context,
                    )
                pre_intent["user_context"] = merged_user_context
                analyze_req = AnalyzeRequest(
                    symbol=symbol,
                    trade_date=trade_date or cn_today_str(),
                    selected_analysts=request.selected_analysts,
                    config_overrides=request.config_overrides,
                    dry_run=request.dry_run,
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
                now = _utcnow_iso()
                with get_db_ctx() as db:
                    analysis_job_service.upsert_job_row(
                        db,
                        job_id,
                        user_id=current_user.id,
                        symbol=analyze_req.symbol,
                        trade_date=analyze_req.trade_date,
                        status="pending",
                        request_payload=analyze_req.model_dump(mode="json"),
                        request_source="chat",
                        dry_run=analyze_req.dry_run,
                    )
                _set_job(
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
                _emit_job_event(
                    job_id,
                    "job.created",
                    {"job_id": job_id, "symbol": analyze_req.symbol, "trade_date": analyze_req.trade_date},
                )
                queue_status, _waiting_ahead_count = await _enqueue_or_start_job(
                    job_id,
                    analyze_req,
                    user_id=current_user.id,
                    request_source="chat",
                )
                if queue_status in ("queued", "rejected"):
                    return
                await _run_job(job_id, analyze_req, True, True, current_user.id, "chat")
            except Exception as exc:
                _log(f"[chat] _extract_and_run failed: {exc}")
                _emit_job_event(job_id, "job.failed", {"error": str(exc)})

        _create_tracked_task(_extract_and_run())
        return StreamingResponse(
            _stream_job_events(job_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # ── 非流式模式：保持原有阻塞行为 ─────────────────────────────────────────────
    symbol, trade_date, horizons, focus_areas, specific_questions, inferred_user_context = \
        await asyncio.to_thread(_ai_extract_symbol_and_date, text, config)

    if not symbol:
        raise HTTPException(status_code=400, detail="抱歉，我没能从您的消息中识别出股票标的。请输入代码（如 600519.SH）或可识别的公司名称。")

    pre_intent = {
        "raw_query": text,
        "ticker": symbol,
        "horizons": horizons,
        "focus_areas": focus_areas,
        "specific_questions": specific_questions,
    }
    with get_db_ctx() as db:
        merged_user_context = _compose_analysis_user_context(
            db,
            current_user.id,
            symbol,
            explicit_context=_extract_request_user_context(request),
            inferred_context=inferred_user_context,
        )
    pre_intent["user_context"] = merged_user_context
    analyze_req = AnalyzeRequest(
        symbol=symbol,
        trade_date=trade_date or cn_today_str(),
        selected_analysts=request.selected_analysts,
        config_overrides=request.config_overrides,
        dry_run=request.dry_run,
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
    now = _utcnow_iso()
    with get_db_ctx() as db:
        analysis_job_service.upsert_job_row(
            db,
            job_id,
            user_id=current_user.id,
            symbol=analyze_req.symbol,
            trade_date=analyze_req.trade_date,
            status="pending",
            request_payload=analyze_req.model_dump(mode="json"),
            request_source="chat",
            dry_run=analyze_req.dry_run,
        )
    _set_job(
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
    _emit_job_event(
        job_id,
        "job.created",
        {"job_id": job_id, "symbol": analyze_req.symbol, "trade_date": analyze_req.trade_date},
    )
    if request.dry_run:
        await _run_job(job_id, analyze_req, True, True, current_user.id, "chat")
        status_text = _get_job(job_id).get("status", "completed")
        decision_text = _get_job(job_id).get("decision", "DRY_RUN")
        return {
            "id": f"chatcmpl-{job_id}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": (
                            f"已完成分析任务：{job_id}\n"
                            f"symbol={analyze_req.symbol}, trade_date={analyze_req.trade_date}\n"
                            f"status={status_text}, decision={decision_text}"
                        ),
                    },
                }
            ],
        }
    queue_status, waiting_ahead_count = await _enqueue_or_start_job(
        job_id,
        analyze_req,
        user_id=current_user.id,
        request_source="chat",
    )
    if queue_status == "queued":
        return {
            "id": f"chatcmpl-{job_id}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": (
                            f"分析任务已进入队列：{job_id}\n"
                            f"symbol={analyze_req.symbol}, trade_date={analyze_req.trade_date}\n"
                            f"前方排队任务约 {waiting_ahead_count} 个，可在任务中心查看与调整顺序。"
                        ),
                    },
                }
            ],
        }
    if queue_status == "rejected":
        return {
            "id": f"chatcmpl-{job_id}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": f"排队已满（最多 {task_queue_service.max_queue_size()} 个），请在任务中心处理后再提交。",
                    },
                }
            ],
        }
    _create_tracked_task(_run_job(job_id, analyze_req, True, True, current_user.id, "chat"))
    return {
        "id": f"chatcmpl-{job_id}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": (
                        f"已启动分析任务：{job_id}\n"
                        f"symbol={analyze_req.symbol}, trade_date={analyze_req.trade_date}\n"
                        f"可通过 /v1/jobs/{job_id} 与 /v1/jobs/{job_id}/result 查询结果。"
                    ),
                },
            }
        ],
    }


# Report API Endpoints
@app.post("/v1/reports", response_model=ReportResponse)
def create_report_endpoint(
    request: ReportCreateRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
):
    """手动创建报告（通常由系统自动调用）."""
    report = report_service.create_report(
        db=db,
        symbol=request.symbol,
        trade_date=request.trade_date,
        decision=request.decision,
        result_data=request.result_data,
        user_id=current_user.id,
        llm_config=_build_runtime_config({}, user_id=str(current_user.id), db=db),
    )
    return report


@app.get("/v1/announcements/latest", response_model=LatestAnnouncementResponse)
def get_latest_announcement():
    return {"announcement": _load_latest_announcement()}


@app.get("/v1/reports", response_model=ReportListResponse)
def list_reports(
    symbol: Optional[str] = Query(None, description="按股票代码筛选"),
    task_kind: Optional[str] = Query(
        None,
        description="按任务类型筛选：full_analysis（智能分析）或 fast_analysis（快速分析）",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
):
    """获取报告列表."""
    tk = str(task_kind or "").strip()
    if tk and tk not in ("full_analysis", "fast_analysis"):
        raise HTTPException(status_code=400, detail="task_kind 仅支持 full_analysis 或 fast_analysis")
    tk_filter = tk if tk in ("full_analysis", "fast_analysis") else None
    total = report_service.count_reports(db=db, user_id=current_user.id, symbol=symbol, task_kind=tk_filter)
    reports = report_service.get_reports_by_user(
        db=db,
        user_id=current_user.id,
        symbol=symbol,
        skip=skip,
        limit=limit,
        task_kind=tk_filter,
    )
    outcome_summaries = report_outcome_service.list_outcome_summaries_by_report_ids(
        db,
        user_id=str(current_user.id),
        report_ids=[str(getattr(r, "id", "")) for r in reports],
    )
    code_to_name = _get_reverse_stock_map()
    for r in reports:
        jid = str(getattr(r, "id", "")).strip()
        st = str(r.status or "")
        needs_job_hydrate = (
            st in report_service.ACTIVE_REPORT_STATUSES
            or (
                st == "failed"
                and str(r.error or "").strip() == report_service.STALE_REPORT_ERROR_MESSAGE
            )
        )
        if jid and needs_job_hydrate and not _get_job(jid):
            _try_hydrate_job_from_db(jid)
        symbol_service.apply_display_label_to_report_row(r, code_to_name=code_to_name or None)
        _attach_job_runtime_state(r, jid)
        _attach_report_task_kind(db, r, jid)
        _attach_report_outcome_summary(r, outcome_summaries, jid)
        _reconcile_stale_running_report_from_job(db, r, str(current_user.id))
        report_service.ensure_rating_5tier(db, r)
    return {"total": total, "reports": reports}


@app.post("/v1/reports/latest-by-symbols", response_model=LatestReportsBySymbolsResponse)
def list_latest_reports_by_symbols(
    body: LatestReportsBySymbolsRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
):
    reports = report_service.get_latest_reports_by_symbols(
        db=db,
        user_id=current_user.id,
        symbols=body.symbols,
    )
    code_to_name = _get_reverse_stock_map()
    outcome_summaries = report_outcome_service.list_outcome_summaries_by_report_ids(
        db,
        user_id=str(current_user.id),
        report_ids=[str(getattr(r, "id", "")) for r in reports],
    )
    for r in reports:
        symbol_service.apply_display_label_to_report_row(r, code_to_name=code_to_name or None)
        rid = str(getattr(r, "id", ""))
        _attach_report_task_kind(db, r, rid)
        _attach_report_outcome_summary(r, outcome_summaries, rid)
    return {"reports": reports}


@app.get("/v1/reports/outcomes/summary", response_model=ReportOutcomeSummaryResponse)
def get_report_outcome_summary(
    task_kind: Optional[str] = Query(
        None,
        description="full_analysis|fast_analysis；不填表示全部",
    ),
    since_days: int = Query(30, ge=0, le=3650),
    group_by: Literal["overall", "version", "week"] = Query("overall"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
):
    payload = report_outcome_service.summarize_outcomes(
        db,
        user_id=str(current_user.id),
        task_kind=task_kind,
        since_days=since_days,
        group_by=group_by,
    )
    return payload


@app.get("/v1/reports/{report_id}/outcome", response_model=ReportOutcomeDetailResponse)
def get_report_outcome_detail(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
):
    payload = report_outcome_service.get_outcome_for_report(db, report_id, str(current_user.id))
    if not payload:
        raise HTTPException(status_code=404, detail="报告兑现度不存在")
    return payload


@app.get("/v1/reports/{report_id}", response_model=ReportDetailResponse)
def get_report_endpoint(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
):
    """获取报告详情."""
    report = report_service.get_report(db, report_id, user_id=current_user.id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    rid = str(report_id).strip()
    st = str(report.status or "")
    needs_job_hydrate = (
        st in report_service.ACTIVE_REPORT_STATUSES
        or (
            st == "failed"
            and str(report.error or "").strip() == report_service.STALE_REPORT_ERROR_MESSAGE
        )
    )
    if needs_job_hydrate and not _get_job(rid):
        _try_hydrate_job_from_db(rid)
    _reconcile_stale_running_report_from_job(db, report, str(current_user.id))
    try:
        db.refresh(report)
    except Exception:
        report = report_service.get_report(db, report_id, user_id=current_user.id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")
    if str(report.status or "") in report_service.ACTIVE_REPORT_STATUSES and not _get_job(rid):
        report = report_service.finalize_orphan_report(db, report)
    code_to_name = _get_reverse_stock_map()
    symbol_service.apply_display_label_to_report_row(report, code_to_name=code_to_name or None)
    _attach_job_runtime_state(report, report_id)
    _attach_report_task_kind(db, report, report_id)
    outcome_summary = report_outcome_service.list_outcome_summaries_by_report_ids(
        db,
        user_id=str(current_user.id),
        report_ids=[str(report_id)],
    )
    _attach_report_outcome_summary(report, outcome_summary, report_id)
    report_service.ensure_rating_5tier(db, report)
    return report


@app.delete("/v1/reports/{report_id}")
async def delete_report_endpoint(
    report_id: str,
    current_user: UserDB = Depends(_require_api_user),
):
    """删除报告，并终止关联分析任务（与任务中心「先停再删」一致：取消运行/排队 + 清理 job 元数据）。"""
    with get_db_ctx() as db:
        report = (
            db.query(ReportDB)
            .filter(ReportDB.id == report_id, ReportDB.user_id == current_user.id)
            .first()
        )
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

    try:
        await _cancel_analysis_job_core(report_id, current_user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise

    with get_db_ctx() as db:
        task_queue_service.remove_queued_job(
            db,
            user_id=current_user.id,
            job_id=report_id,
            cancel_error="用户已从报告列表删除",
        )

    with get_db_ctx() as db:
        job_row = analysis_job_service.get_job_row(db, report_id)
        if job_row and str(job_row.user_id or "") == str(current_user.id):
            if str(job_row.status or "") in task_queue_service.ACTIVE_RUNNING_STATUSES:
                analysis_job_service.persist_store_fields(
                    db,
                    report_id,
                    {"status": "failed", "error": "用户删除报告并终止任务", "user_id": current_user.id},
                )
                analysis_job_service.release_lease(db, report_id)
        db.query(JobEventDB).filter(JobEventDB.job_id == report_id).delete(synchronize_session=False)
        row_aj = (
            db.query(AnalysisJobDB)
            .filter(AnalysisJobDB.id == report_id, AnalysisJobDB.user_id == current_user.id)
            .first()
        )
        if row_aj is not None:
            payload = dict(row_aj.request_payload or {})
            fast_id = str(payload.get("fast_analysis_id") or "").strip()
            if fast_id:
                db.query(FastAnalysisDB).filter(
                    FastAnalysisDB.id == fast_id,
                    FastAnalysisDB.user_id == current_user.id,
                ).delete(synchronize_session=False)
            db.delete(row_aj)
        rep = (
            db.query(ReportDB)
            .filter(ReportDB.id == report_id, ReportDB.user_id == current_user.id)
            .first()
        )
        if rep is not None:
            db.delete(rep)
        db.query(ReportOutcomeDB).filter(
            ReportOutcomeDB.id == report_id,
            ReportOutcomeDB.user_id == current_user.id,
        ).delete(synchronize_session=False)
        db.commit()

    try:
        get_job_store().delete_job(report_id)
    except Exception:
        pass

    task_queue_service.request_schedule(current_user.id)
    return {"message": "报告已删除"}


@app.post("/v1/reports/batch/delete", response_model=ReportBatchDeleteResponse)
def batch_delete_reports_endpoint(
    body: ReportBatchDeleteRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
):
    try:
        return report_service.batch_delete_reports(db, body.report_ids, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── API Token Endpoints ────────────────────────────────────────────────────

@app.get("/v1/tokens", response_model=List[UserTokenListItem])
def list_tokens(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    """获取当前用户的所有 API Token（不返回完整 token）。"""
    return token_service.list_user_tokens(db, current_user.id)


@app.post("/v1/tokens", response_model=UserTokenResponse)
def create_token(
    request: UserTokenCreateRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    """创建一个新的 API Token。完整 token 仅在此接口返回一次。"""
    try:
        return token_service.create_token(db, current_user.id, request.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/v1/tokens/{token_id}")
def delete_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    """吊销并删除一个 API Token。"""
    success = token_service.delete_token(db, current_user.id, token_id)
    if not success:
        raise HTTPException(status_code=404, detail="Token 不存在")
    return {"message": "Token 已吊销"}


# ─── Backtest Endpoints ───────────────────────────────────────────────────────

from api.services import backtest_service as _bt


class BacktestRequest(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    selected_analysts: List[str] = ["market", "news", "fundamentals", "sentiment"]
    hold_days: int = 5
    sample_interval: int = 7
    config_overrides: Optional[Dict[str, Any]] = None


@app.post("/v1/backtest")
def submit_backtest(
    request: BacktestRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
) -> Dict:
    """提交历史回测任务，返回 job_id."""
    config = _build_runtime_config(request.config_overrides or {}, user_id=current_user.id, db=db)
    job_id = _bt.submit(
        symbol=request.symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        selected_analysts=request.selected_analysts,
        hold_days=request.hold_days,
        sample_interval=request.sample_interval,
        config=config,
        user_id=current_user.id,
    )
    return {"job_id": job_id, "status": "pending"}


@app.get("/v1/backtest")
def list_backtests(current_user: UserDB = Depends(_require_api_user)) -> Dict:
    """列出当前用户的回测任务."""
    jobs = _bt.list_jobs(current_user.id)
    return {"jobs": jobs, "total": len(jobs)}


@app.get("/v1/backtest/{job_id}")
def get_backtest(job_id: str, current_user: UserDB = Depends(_require_api_user)) -> Dict:
    """获取回测任务状态和结果."""
    job = _bt.get_job(job_id, current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    return job


@app.delete("/v1/backtest/{job_id}")
def delete_backtest(job_id: str, current_user: UserDB = Depends(_require_api_user)) -> Dict:
    """删除回测任务."""
    if not _bt.delete_job(job_id, current_user.id):
        raise HTTPException(status_code=404, detail="回测任务不存在")
    return {"message": "已删除"}


# ─── Runtime Config Endpoints ────────────────────────────────────────────────

_CONFIG_ALLOWED_KEYS = {
    "llm_provider", "deep_think_llm", "quick_think_llm",
    "backend_url", "max_debate_rounds", "max_risk_discuss_rounds",
}
_CONFIG_PREFERENCE_KEYS = {"email_report_enabled", "wecom_report_enabled"}
_CONFIG_MODEL_KEYS = ("llm_provider", "backend_url", "quick_think_llm", "deep_think_llm")
_CONFIG_MODEL_LABELS = {
    "quick_think_llm": "常规模型",
    "deep_think_llm": "推理模型",
}
_CONFIG_PROBE_TIMEOUT_SECONDS = 12.0
_CONFIG_PROBE_PROMPT = "Reply with the single word OK."
_CONFIG_WARMUP_TIMEOUT_SECONDS = 20.0
_CONFIG_WARMUP_PROMPT = "Reply with the single word OK."


def _mask_secret_value(value: Optional[str], *, head: int = 4, tail: int = 4) -> Optional[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= head + tail:
        return "*" * max(6, len(normalized))
    return f"{normalized[:head]}{'*' * max(6, len(normalized) - head - tail)}{normalized[-tail:]}"


def _mask_wecom_webhook(webhook_url: Optional[str]) -> Optional[str]:
    normalized = str(webhook_url or "").strip()
    if not normalized:
        return None
    prefix = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="
    if normalized.startswith(prefix):
        masked_key = _mask_secret_value(normalized[len(prefix):])
        return f"{prefix}{masked_key}"
    if normalized.startswith("http"):
        if "key=" in normalized:
            base, key = normalized.rsplit("key=", 1)
            return f"{base}key={_mask_secret_value(key)}"
        return _mask_secret_value(normalized, head=18, tail=8)
    return _mask_secret_value(normalized)


def _warmup_model_names(config: Dict[str, Any]) -> List[str]:
    seen: set[str] = set()
    models: List[str] = []
    for key in ("quick_think_llm", "deep_think_llm"):
        value = str(config.get(key) or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        models.append(value)
    return models


def _warmup_model_targets(config: Dict[str, Any]) -> List[Tuple[str, List[str]]]:
    targets: Dict[str, List[str]] = {}
    for key in ("quick_think_llm", "deep_think_llm"):
        model = str(config.get(key) or "").strip()
        if not model:
            continue
        labels = targets.setdefault(model, [])
        label = _CONFIG_MODEL_LABELS.get(key, key)
        if label not in labels:
            labels.append(label)
    return [(model, labels) for model, labels in targets.items()]


def _should_trigger_config_warmup(
    before_cfg: UserRuntimeConfigResponse,
    after_cfg: UserRuntimeConfigResponse,
    updates: UserRuntimeConfigUpdateRequest,
) -> bool:
    if not updates.warmup:
        return False
    if updates.force_warmup:
        return True
    if updates.api_key:
        return True
    before = before_cfg.model_dump()
    after = after_cfg.model_dump()
    return any(before.get(key) != after.get(key) for key in _CONFIG_MODEL_KEYS)


def _build_pending_runtime_config(
    updates: UserRuntimeConfigUpdateRequest,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    config = _build_runtime_config({}, user_id=user_id, db=db)
    for key in _CONFIG_ALLOWED_KEYS:
        value = getattr(updates, key, None)
        if value is not None:
            config[key] = value

    if updates.clear_api_key:
        config["api_key"] = ""
    elif updates.api_key:
        config["api_key"] = updates.api_key

    quick = config.get("quick_think_llm")
    deep = config.get("deep_think_llm")
    if not deep and quick:
        config["deep_think_llm"] = quick
    if not quick and deep:
        config["quick_think_llm"] = deep
    return config


def _should_probe_runtime_config(
    before_cfg: UserRuntimeConfigResponse,
    pending_cfg: Dict[str, Any],
    updates: UserRuntimeConfigUpdateRequest,
) -> bool:
    del before_cfg, pending_cfg
    if updates.clear_api_key:
        return False
    return bool(updates.api_key)


def _probe_runtime_config(config: Dict[str, Any]) -> Dict[str, str]:
    from tradingagents.llm_clients.factory import create_llm_client

    provider = str(config.get("llm_provider") or "openai")
    base_url = config.get("backend_url")
    api_key = str(config.get("api_key") or "").strip()
    model = str(config.get("quick_think_llm") or config.get("deep_think_llm") or "").strip()

    if not model or not api_key:
        return {"status": "skipped", "reason": "missing_model_or_key"}

    try:
        client = create_llm_client(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=_CONFIG_PROBE_TIMEOUT_SECONDS,
            max_retries=0,
        )
        llm = client.get_llm()
        response = llm.invoke(_CONFIG_PROBE_PROMPT)
        raw = response if isinstance(response, str) else getattr(response, "content", str(response))
        preview = str(raw).strip().replace("\n", " ")[:80] or "<empty>"
        return {"status": "ok", "model": model, "preview": preview}
    except Exception as exc:
        detail = str(exc).strip()
        lowered = detail.lower()
        if "401" in lowered or "invalid authentication" in lowered or "authenticationerror" in lowered:
            raise HTTPException(
                status_code=400,
                detail="模型 Key 验证失败：上游返回 401 Invalid Authentication，请检查 API Key 是否正确。",
            ) from exc
        raise HTTPException(
            status_code=400,
            detail=f"模型连接验证失败：{detail[:200] or 'unknown error'}",
        ) from exc


def _invoke_runtime_warmup(
    config: Dict[str, Any],
    prompt: str,
    user_id: str,
    timeout: float = _CONFIG_WARMUP_TIMEOUT_SECONDS,
) -> List[Dict[str, Any]]:
    from tradingagents.llm_clients.factory import create_llm_client

    provider = str(config.get("llm_provider") or "openai")
    base_url = config.get("backend_url")
    api_key = config.get("api_key")
    targets = _warmup_model_targets(config)

    if not targets:
        raise HTTPException(status_code=400, detail="请先配置至少一个可用模型。")

    _log(
        f"[LLM Warmup] user={user_id} invoking provider={provider} "
        f"models={[model for model, _ in targets]} base_url={base_url or 'default'}"
    )

    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    for model, labels in targets:
        try:
            client = create_llm_client(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
                max_retries=0,
            )
            llm = client.get_llm()
            response = llm.invoke(prompt)
            raw = response if isinstance(response, str) else getattr(response, "content", str(response))
            content = str(raw).strip() or "<empty>"
            preview = content.replace("\n", " ")[:80]
            _log(f"[LLM Warmup] user={user_id} model={model} success response={preview}")
            results.append({
                "model": model,
                "targets": labels,
                "content": content,
                "error": None,
            })
        except Exception as exc:
            detail = str(exc).strip() or "unknown error"
            errors.append(f"{model}: {detail}")
            logger.warning(
                "[LLM Warmup] user=%s model=%s failed: %s",
                user_id,
                model,
                exc,
            )
            results.append({
                "model": model,
                "targets": labels,
                "content": None,
                "error": detail[:200],
            })

    if not any(item.get("content") for item in results):
        raise HTTPException(
            status_code=400,
            detail=f"模型 warmup 失败：{'; '.join(errors)[:300]}",
        )

    return results


def _run_config_warmup(config: Dict[str, Any], user_id: str) -> None:
    models = _warmup_model_names(config)
    if not models:
        _log(f"[LLM Warmup] user={user_id} skipped: no models configured")
        return
    try:
        _invoke_runtime_warmup(config, _CONFIG_WARMUP_PROMPT, user_id, timeout=_CONFIG_WARMUP_TIMEOUT_SECONDS)
    except HTTPException as exc:
        logger.warning("[LLM Warmup] user=%s failed: %s", user_id, exc.detail)


def _config_response_for_user(user: Optional[UserDB], db: Session) -> UserRuntimeConfigResponse:
    cfg = _build_runtime_config({}, user_id=user.id if user else None, db=db)
    user_cfg = auth_service.get_user_llm_config(db, user.id) if user else None
    webhook_url = auth_service.decrypt_secret(getattr(user_cfg, "wecom_webhook_encrypted", None))
    return UserRuntimeConfigResponse(
        llm_provider=cfg["llm_provider"],
        deep_think_llm=cfg["deep_think_llm"],
        quick_think_llm=cfg["quick_think_llm"],
        backend_url=cfg["backend_url"],
        max_debate_rounds=cfg["max_debate_rounds"],
        max_risk_discuss_rounds=cfg["max_risk_discuss_rounds"],
        has_api_key=bool(user_cfg and user_cfg.api_key_encrypted),
        has_wecom_webhook=bool(webhook_url),
        wecom_webhook_display=_mask_wecom_webhook(webhook_url),
        server_fallback_enabled=bool(cfg.get("server_fallback_enabled", True)),
        email_report_enabled=user.email_report_enabled if user and hasattr(user, 'email_report_enabled') else True,
        wecom_report_enabled=user.wecom_report_enabled if user and hasattr(user, "wecom_report_enabled") else True,
        default_analysts=json.loads(user_cfg.default_analysts) if user_cfg and user_cfg.default_analysts else ["market", "social", "news", "fundamentals", "macro", "smart_money", "volume_price"],
    )


@app.get("/v1/config", response_model=UserRuntimeConfigResponse)
def get_runtime_config(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    """获取当前用户运行时配置。"""
    return _config_response_for_user(current_user, db)


@app.patch("/v1/config")
def update_runtime_config(
    updates: UserRuntimeConfigUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    """更新当前用户运行时配置，下次分析时生效。"""
    normalized_wecom_webhook = None
    if updates.wecom_webhook_url:
        from api.services.wecom_notification_service import normalize_webhook_url

        try:
            normalized_wecom_webhook = normalize_webhook_url(updates.wecom_webhook_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    persistent_user = db.query(UserDB).filter(UserDB.id == current_user.id).first() or current_user
    before_cfg = _config_response_for_user(persistent_user, db)
    pending_cfg = _build_pending_runtime_config(updates, persistent_user.id, db)
    if _should_probe_runtime_config(before_cfg, pending_cfg, updates):
        probe = _probe_runtime_config(pending_cfg)
        _log(
            f"[LLM Probe] user={persistent_user.id} provider={pending_cfg.get('llm_provider')} "
            f"model={probe.get('model', '')} status={probe.get('status')}"
        )
    row = auth_service.upsert_user_llm_config(
        db,
        persistent_user.id,
        llm_provider=updates.llm_provider,
        deep_think_llm=updates.deep_think_llm,
        quick_think_llm=updates.quick_think_llm,
        backend_url=updates.backend_url,
        max_debate_rounds=updates.max_debate_rounds,
        max_risk_discuss_rounds=updates.max_risk_discuss_rounds,
        api_key=updates.api_key,
        wecom_webhook_url=normalized_wecom_webhook,
        clear_api_key=updates.clear_api_key,
        clear_wecom_webhook=updates.clear_wecom_webhook,
        default_analysts=updates.default_analysts,
    )
    user_pref_updated = False
    if updates.email_report_enabled is not None:
        persistent_user.email_report_enabled = updates.email_report_enabled
        user_pref_updated = True
    if updates.wecom_report_enabled is not None:
        persistent_user.wecom_report_enabled = updates.wecom_report_enabled
        user_pref_updated = True
    if user_pref_updated:
        db.commit()
    current_cfg = _config_response_for_user(persistent_user, db)
    warmup_models = _warmup_model_names(current_cfg.model_dump())
    should_warmup = _should_trigger_config_warmup(before_cfg, current_cfg, updates)
    warmup_payload: Dict[str, Any]
    if should_warmup and warmup_models:
        warmup_payload = {
            "requested": True,
            "triggered": True,
            "status": "scheduled",
            "models": warmup_models,
            "message": f"模型配置已保存，后台正在预热 {len(warmup_models)} 个模型。",
        }
        background_tasks.add_task(
            _run_config_warmup,
            _build_runtime_config({}, user_id=persistent_user.id, db=db),
            persistent_user.id,
        )
    elif updates.warmup:
        warmup_payload = {
            "requested": True,
            "triggered": False,
            "status": "skipped",
            "models": warmup_models,
            "message": "模型配置已保存，本次未触发 warmup。",
        }
    else:
        warmup_payload = {
            "requested": False,
            "triggered": False,
            "status": "disabled",
            "models": [],
            "message": "模型配置已保存。",
        }
    filtered = {
        k: v
        for k, v in updates.model_dump().items()
        if v is not None
        and k not in {"api_key", "wecom_webhook_url", "warmup", "force_warmup"}
        and (
            k in _CONFIG_ALLOWED_KEYS
            or k in _CONFIG_PREFERENCE_KEYS
            or (k in {"clear_api_key", "clear_wecom_webhook"} and bool(v))
        )
    }
    return {
        "message": "用户配置已更新",
        "applied": filtered,
        "has_api_key": bool(row.api_key_encrypted),
        "current": current_cfg,
        "warmup": warmup_payload,
    }


@app.post("/v1/config/warmup", response_model=UserRuntimeWarmupResponse)
def warmup_runtime_config(
    request: UserRuntimeWarmupRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    pending_cfg = _build_pending_runtime_config(request, current_user.id, db)
    prompt = (request.prompt or "").strip() or "你好"
    results = _invoke_runtime_warmup(pending_cfg, prompt, current_user.id)
    return {
        "prompt": prompt,
        "results": results,
    }


@app.post("/v1/config/wecom/warmup", response_model=WecomWebhookWarmupResponse)
async def warmup_wecom_webhook(
    request: WecomWebhookWarmupRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    from api.services.wecom_notification_service import build_test_message, normalize_webhook_url, send_message

    webhook_url = (request.wecom_webhook_url or "").strip()
    if not webhook_url:
        user_cfg = auth_service.get_user_llm_config(db, current_user.id)
        webhook_url = auth_service.decrypt_secret(getattr(user_cfg, "wecom_webhook_encrypted", None)) or ""
    if not webhook_url:
        raise HTTPException(status_code=400, detail="请先填写或保存企业微信 Webhook")
    try:
        webhook_url = normalize_webhook_url(webhook_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        sent = await asyncio.to_thread(send_message, build_test_message(request.content), webhook_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Webhook 测试发送失败：{exc}") from exc
    if not sent:
        raise HTTPException(status_code=400, detail="Webhook 测试发送失败，请检查地址或机器人状态")

    return {
        "sent": True,
        "message": "Webhook 测试发送成功",
        "webhook_display": _mask_wecom_webhook(webhook_url),
    }


# ── Stock Search ──────────────────────────────────────────────────────────────

@app.get("/v1/market/stock-search")
def search_stocks(
    q: str = Query("", min_length=1, max_length=20),
    _maybe_user: Optional[UserDB] = Depends(_optional_user),
):
    """Search stocks by code prefix or name substring (无需登录也可检索，便于 K 线页选标的)。"""
    q = q.strip()
    if not q:
        return {"results": []}

    name_to_code = _load_cn_stock_map()
    code_to_name = _get_reverse_stock_map()
    results = []
    q_upper = q.upper()

    for code, name in code_to_name.items():
        if code.upper().startswith(q_upper) or code.split(".")[0].startswith(q):
            results.append({"symbol": code, "name": name})
            if len(results) >= 20:
                break

    if len(results) < 20:
        for name, code in name_to_code.items():
            if q in name and not any(r["symbol"] == code for r in results):
                results.append({"symbol": code, "name": name})
                if len(results) >= 20:
                    break

    # 指数等不在全市场表中的代码：按规范代码补一条，否则前端 stock-search 返回空、无法显示中文名
    norm = _normalize_symbol(q)
    if norm and re.match(r"^\d{6}\.(SH|SZ|BJ)$", norm):
        if not any(str(r.get("symbol") or "").upper() == norm for r in results):
            dn = _resolve_cn_display_name(norm)
            if dn:
                results.insert(0, {"symbol": norm, "name": dn})

    for r in results:
        r["display_label"] = symbol_service.format_display_label(r.get("name"), r["symbol"])

    return {"results": results}


@app.get("/v1/market/stock-resolve")
def resolve_stock_query(
    q: str = Query("", min_length=1, max_length=64),
    _maybe_user: Optional[UserDB] = Depends(_optional_user),
):
    """将单行输入解析为规范 symbol、名称与 display_label（登录可选）。"""
    return symbol_service.resolve_stock(q.strip())


def _annotate_scheduled_with_imported_context(items: List[dict], db: Session, user_id: str) -> List[dict]:
    imported_map: Dict[str, Dict[str, Any]] = {}
    for item in portfolio_import_service.list_imported_positions(db, user_id):
        imported_map[item["symbol"]] = item
    for item in items:
        imported = imported_map.get(item["symbol"])
        item["has_imported_context"] = imported is not None
        item["imported_current_position"] = imported.get("current_position") if imported else None
        item["imported_average_cost"] = imported.get("average_cost") if imported else None
        item["imported_trade_points_count"] = imported.get("trade_points_count") if imported else 0
    return items


def _merge_imported_user_context(*contexts: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    note_parts: List[str] = []
    for ctx in contexts:
        if not ctx:
            continue
        for key, value in ctx.items():
            if key == "user_notes":
                if value:
                    note_parts.append(str(value).strip())
                continue
            if value is not None:
                merged[key] = value
    if note_parts:
        merged["user_notes"] = "\n\n".join(part for part in note_parts if part)
    return normalize_user_context(merged)


def _build_imported_user_context(db: Session, user_id: str, symbol: str) -> Dict[str, Any]:
    context = portfolio_import_service.build_scheduled_user_context(db, user_id, symbol)
    return _merge_imported_user_context(context)


def _build_manual_imported_user_context(db: Session, user_id: str, symbol: str) -> Dict[str, Any]:
    """Build imported position context for manual/ad-hoc analysis runs."""
    return _build_imported_user_context(db, user_id, symbol)


@app.get("/v1/portfolio/imports")
def get_portfolio_import_state(
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    return portfolio_import_service.get_import_state(db, current_user.id)


@app.post("/v1/portfolio/imports")
def sync_portfolio_import(
    body: PortfolioImportSyncRequest,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    try:
        return portfolio_import_service.sync_positions(
            db=db,
            user_id=current_user.id,
            positions=[p.model_dump() for p in body.positions],
            source=body.source,
            auto_apply_scheduled=body.auto_apply_scheduled,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/v1/portfolio/imports", status_code=204)
def clear_portfolio_import_state(
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    portfolio_import_service.clear_imported_portfolio(db, current_user.id)


@app.post("/v1/portfolio/parse-image")
async def parse_position_image_endpoint(
    file: UploadFile = File(...),
    current_user: UserDB = Depends(_require_api_user),
):
    """Parse a broker position screenshot using server-side VLM."""
    from api.services.vlm_position_parser import parse_position_image

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "只支持图片文件")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过 10MB")

    try:
        positions = await asyncio.to_thread(parse_position_image, image_bytes, file.content_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.warning("[parse-image] VLM parsing failed: %s", exc)
        raise HTTPException(500, "图片解析失败，请稍后重试") from exc

    return {"positions": positions}


@app.get("/v1/dashboard/tracking-board")
def get_dashboard_tracking_board(
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    return tracking_board_service.get_tracking_board(db, current_user.id)


# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.get("/v1/watchlist")
def list_watchlist(
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    items = watchlist_service.list_watchlist(db, current_user.id)
    _attach_stock_names(items, _get_reverse_stock_map())
    return {"items": items}


@app.post("/v1/watchlist")
def add_to_watchlist(
    body: WatchlistAddRequest,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    text = str(body.text or body.symbol or "").strip()
    if not text:
        raise HTTPException(400, "text or symbol is required")

    tokens = _split_watchlist_batch_text(text)
    if not tokens:
        raise HTTPException(400, "至少提供一个股票代码或名称")

    name_to_code = _load_cn_stock_map()
    code_to_name = _get_reverse_stock_map()

    resolved_entries: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    for idx, token in enumerate(tokens):
        symbol, name, error = _resolve_watchlist_identifier(token, name_to_code, code_to_name)
        if error:
            results.append({
                "_order": idx,
                "input": token,
                "status": "invalid",
                "message": error,
            })
            continue
        resolved_entries.append({
            "_order": idx,
            "input": token,
            "symbol": symbol,
            "name": name,
            "display_label": symbol_service.format_display_label(name, symbol),
        })

    add_results = watchlist_service.add_watchlist_items(
        db,
        current_user.id,
        [entry["symbol"] for entry in resolved_entries],
    )
    for entry, result in zip(resolved_entries, add_results):
        item = result.get("item")
        if item:
            item["name"] = entry["name"]
            item["display_label"] = entry["display_label"]
            item["has_scheduled"] = False
        results.append({
            "_order": entry["_order"],
            "input": entry["input"],
            "symbol": entry["symbol"],
            "name": entry["name"],
            "display_label": entry["display_label"],
            "status": result["status"],
            "message": result["message"],
            "item": item,
        })

    results.sort(key=lambda row: row["_order"])
    for row in results:
        row.pop("_order", None)
    summary = {
        "total": len(tokens),
        "added": sum(1 for row in results if row["status"] == "added"),
        "duplicate": sum(1 for row in results if row["status"] == "duplicate"),
        "failed": sum(1 for row in results if row["status"] in {"invalid", "failed"}),
    }
    message_parts = [f"共处理 {summary['total']} 项"]
    if summary["added"]:
        message_parts.append(f"新增 {summary['added']} 项")
    if summary["duplicate"]:
        message_parts.append(f"重复 {summary['duplicate']} 项")
    if summary["failed"]:
        message_parts.append(f"失败 {summary['failed']} 项")
    return {
        "message": "，".join(message_parts),
        "summary": summary,
        "results": results,
    }


@app.delete("/v1/watchlist/{item_id}", status_code=204)
def delete_from_watchlist(
    item_id: str,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    if not watchlist_service.delete_watchlist_item(db, current_user.id, item_id):
        raise HTTPException(404, "未找到该自选股")


# ── Scheduled Analysis ────────────────────────────────────────────────────────

@app.get("/v1/scheduled")
def list_scheduled_analyses(
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    items = scheduled_service.list_scheduled(db, current_user.id)
    _attach_stock_names(items, _get_reverse_stock_map())
    return {"items": _annotate_scheduled_with_imported_context(items, db, current_user.id)}


@app.get("/v1/portfolio/overview", response_model=PortfolioOverviewResponse)
def get_portfolio_overview(
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    code_to_name = _get_reverse_stock_map()

    watchlist_items = watchlist_service.list_watchlist(db, current_user.id)
    _attach_stock_names(watchlist_items, code_to_name)

    scheduled_items = scheduled_service.list_scheduled(db, current_user.id)
    _attach_stock_names(scheduled_items, code_to_name)
    scheduled_items = _annotate_scheduled_with_imported_context(scheduled_items, db, current_user.id)

    latest_reports = report_service.get_latest_reports_by_symbols(
        db=db,
        user_id=current_user.id,
        symbols=[item["symbol"] for item in watchlist_items],
    )
    for report in latest_reports:
        symbol_service.apply_display_label_to_report_row(report, code_to_name=code_to_name or None)

    portfolio_import = portfolio_import_service.get_import_state(db, current_user.id)

    return {
        "watchlist": watchlist_items,
        "scheduled": scheduled_items,
        "latest_reports": latest_reports,
        "portfolio_import": portfolio_import,
    }


@app.post("/v1/scheduled", status_code=201)
def create_scheduled_analysis(
    body: dict,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    symbol = _normalize_symbol(str(body.get("symbol", "")).strip())
    horizon = body.get("horizon", "short")
    trigger_time = body.get("trigger_time", "20:00")
    if not symbol:
        raise HTTPException(400, "symbol is required")
    code_to_name = _get_reverse_stock_map()
    if symbol not in code_to_name:
        raise HTTPException(400, f"未知的股票代码: {symbol}")
    try:
        item = scheduled_service.create_scheduled(db, current_user.id, symbol, horizon, trigger_time)
        _attach_stock_names([item], code_to_name)
        _annotate_scheduled_with_imported_context([item], db, current_user.id)
        return item
    except ValueError as e:
        raise HTTPException(400, str(e))


def _extract_scheduled_update_kwargs(body: dict) -> dict:
    kwargs = {}
    if "is_active" in body:
        kwargs["is_active"] = bool(body["is_active"])
    if "horizon" in body:
        kwargs["horizon"] = body["horizon"]
    if "trigger_time" in body:
        kwargs["trigger_time"] = body["trigger_time"]
    return kwargs


@app.patch("/v1/scheduled/batch")
def batch_update_scheduled_analyses(
    body: ScheduledBatchUpdateRequest,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    kwargs = _extract_scheduled_update_kwargs(body.model_dump(exclude_unset=True))
    if not kwargs:
        raise HTTPException(400, "至少提供一个更新字段")
    try:
        items = scheduled_service.batch_update_scheduled(
            db,
            current_user.id,
            body.item_ids,
            **kwargs,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    code_to_name = _get_reverse_stock_map()
    _attach_stock_names(items, code_to_name)
    return {"items": _annotate_scheduled_with_imported_context(items, db, current_user.id)}


@app.post("/v1/scheduled/batch/delete")
def batch_delete_scheduled_analyses(
    body: ScheduledBatchIdsRequest,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    try:
        return scheduled_service.batch_delete_scheduled(db, current_user.id, body.item_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/v1/scheduled/batch/trigger", response_model=BatchScheduledTriggerResponse)
async def trigger_scheduled_analyses_batch(
    body: ScheduledBatchIdsRequest,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    if not body.item_ids:
        raise HTTPException(400, "请至少选择 1 个定时任务")

    requested_trade_date = cn_today_str()
    actual_trade_date = _resolve_scheduled_trade_date(requested_trade_date)
    code_to_name = _get_reverse_stock_map()
    jobs: List[Dict[str, Any]] = []
    with_position_context = 0
    available_tasks = {
        task["id"]: task
        for task in scheduled_service.list_scheduled(db, current_user.id)
    }
    valid_item_ids = []
    missing_item_ids = []
    for raw_item_id in body.item_ids:
        item_id = str(raw_item_id or "").strip()
        if not item_id:
            continue
        if item_id in available_tasks:
            valid_item_ids.append(item_id)
        else:
            missing_item_ids.append(item_id)

    if not valid_item_ids:
        raise HTTPException(400, "选中的定时任务已失效，请刷新页面后重试")

    if missing_item_ids:
        _log(
            f"[Scheduled Batch Trigger] user={current_user.id} skipped missing item_ids={missing_item_ids}"
        )

    for item_id in valid_item_ids:
        task = available_tasks[item_id]

        task_snapshot = dict(task)
        task_snapshot["user_id"] = current_user.id
        task_snapshot["manual_user_context"] = _build_manual_imported_user_context(db, current_user.id, task["symbol"])

        scheduled_user_context = task_snapshot["manual_user_context"]
        if scheduled_user_context.get("current_position") is not None:
            with_position_context += 1

        now = _utcnow_iso()
        job_id = uuid4().hex
        _set_job(
            job_id,
            job_id=job_id,
            status="pending",
            created_at=now,
            symbol=task["symbol"],
            trade_date=actual_trade_date,
            user_id=current_user.id,
            request_source="scheduled_manual_batch",
        )
        _emit_job_event(
            job_id,
            "job.queued",
            {"job_id": job_id, "symbol": task["symbol"], "trade_date": actual_trade_date},
        )
        _create_tracked_task(
            _run_manual_trigger(
                task_snapshot,
                requested_trade_date,
                job_id,
            )
        )

        nm = code_to_name.get(task["symbol"], task["symbol"])
        jobs.append({
            "item_id": task["id"],
            "job_id": job_id,
            "symbol": task["symbol"],
            "name": nm,
            "display_label": symbol_service.format_display_label(nm, task["symbol"]),
            "status": "pending",
            "created_at": now,
            "current_position": scheduled_user_context.get("current_position"),
            "average_cost": scheduled_user_context.get("average_cost"),
        })

    return {
        "summary": {
            "total": len(jobs),
            "with_position_context": with_position_context,
        },
        "jobs": jobs,
    }


@app.post("/v1/scheduled/{item_id}/trigger", response_model=AnalyzeResponse)
async def trigger_scheduled_analysis_once(
    item_id: str,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    task = scheduled_service.get_scheduled(db, current_user.id, item_id)
    if task is None:
        raise HTTPException(404, "未找到该定时任务")

    requested_trade_date = cn_today_str()
    actual_trade_date = _resolve_scheduled_trade_date(requested_trade_date)
    now = _utcnow_iso()
    job_id = uuid4().hex

    task_snapshot = dict(task)
    task_snapshot["user_id"] = current_user.id
    task_snapshot["manual_user_context"] = _build_manual_imported_user_context(db, current_user.id, task["symbol"])

    _set_job(
        job_id,
        job_id=job_id,
        status="pending",
        created_at=now,
        symbol=task["symbol"],
        trade_date=actual_trade_date,
        user_id=current_user.id,
        request_source="scheduled_manual",
    )
    _emit_job_event(
        job_id,
        "job.queued",
        {"job_id": job_id, "symbol": task["symbol"], "trade_date": actual_trade_date},
    )
    _create_tracked_task(
        _run_manual_trigger(
            task_snapshot,
            requested_trade_date,
            job_id,
        )
    )
    return AnalyzeResponse(job_id=job_id, status="pending", created_at=now)


@app.patch("/v1/scheduled/{item_id}")
def update_scheduled_analysis(
    item_id: str,
    body: dict,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    kwargs = _extract_scheduled_update_kwargs(body)
    try:
        result = scheduled_service.update_scheduled(db, current_user.id, item_id, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if result is None:
        raise HTTPException(404, "未找到该定时任务")
    code_to_name = _get_reverse_stock_map()
    result["name"] = code_to_name.get(result["symbol"], result["symbol"])
    _annotate_scheduled_with_imported_context([result], db, current_user.id)
    return result


@app.delete("/v1/scheduled/{item_id}", status_code=204)
def delete_scheduled_analysis(
    item_id: str,
    current_user: UserDB = Depends(_require_api_user),
    db: Session = Depends(get_db),
):
    if not scheduled_service.delete_scheduled(db, current_user.id, item_id):
        raise HTTPException(404, "未找到该定时任务")


# ─── Sponsor endpoints (public, no auth) ────────────────────────────────────


class SponsorItem(BaseModel):
    id: str
    sponsor_type: str
    name: str
    github: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None
    provider: Optional[str] = None
    date: str
    # NOTE: amount is intentionally excluded from the public API


class SponsorsResponse(BaseModel):
    money: List[SponsorItem]
    token: List[SponsorItem]


def _sponsor_to_item(s: SponsorDB) -> SponsorItem:
    return SponsorItem(
        id=s.id,
        sponsor_type=s.sponsor_type,
        name=s.name,
        github=s.github,
        avatar=s.avatar,
        email=s.email,
        provider=s.provider,
        date=s.date,
    )


@app.get("/v1/sponsors", response_model=SponsorsResponse)
def list_sponsors(db: Session = Depends(get_db)):
    """Public endpoint: list all visible sponsors grouped by type."""
    all_sponsors = sponsor_service.list_sponsors(db)
    money = [_sponsor_to_item(s) for s in all_sponsors if s.sponsor_type == "money"]
    token = [_sponsor_to_item(s) for s in all_sponsors if s.sponsor_type == "token"]
    return SponsorsResponse(money=money, token=token)


# ─── Feedback endpoints ─────────────────────────────────────────────────────


class FeedbackCreateRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)


class FeedbackItem(BaseModel):
    id: str
    user_email: str
    subject: str
    content: str
    admin_reply: Optional[str] = None
    replied_at: Optional[datetime] = None
    is_read: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_serializer("replied_at", "created_at", "updated_at")
    def serialize_dt(self, v: Optional[datetime], _info: Any) -> Optional[str]:
        return v.isoformat() if v else None


class FeedbackListResponse(BaseModel):
    total: int
    feedbacks: List[FeedbackItem]


class FeedbackUnreadResponse(BaseModel):
    unread_count: int


def _fb_to_item(fb: FeedbackDB) -> FeedbackItem:
    return FeedbackItem(
        id=fb.id,
        user_email=fb.user_email,
        subject=fb.subject,
        content=fb.content,
        admin_reply=fb.admin_reply,
        replied_at=fb.replied_at,
        is_read=fb.is_read,
        created_at=fb.created_at,
        updated_at=fb.updated_at,
    )


@app.post("/v1/feedbacks", response_model=FeedbackItem, status_code=201)
def create_feedback(
    req: FeedbackCreateRequest,
    current_user: UserDB = Depends(_require_web_user),
    db: Session = Depends(get_db),
):
    fb = feedback_service.create_feedback(db, current_user, req.subject, req.content)
    return _fb_to_item(fb)


@app.get("/v1/feedbacks", response_model=FeedbackListResponse)
def list_feedbacks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserDB = Depends(_require_web_user),
    db: Session = Depends(get_db),
):
    items, total = feedback_service.list_feedbacks(db, current_user.id, page, page_size)
    return FeedbackListResponse(total=total, feedbacks=[_fb_to_item(fb) for fb in items])


@app.get("/v1/feedbacks/unread-count", response_model=FeedbackUnreadResponse)
def feedback_unread_count(
    current_user: UserDB = Depends(_require_web_user),
    db: Session = Depends(get_db),
):
    count = feedback_service.unread_count(db, current_user.id)
    return FeedbackUnreadResponse(unread_count=count)


@app.get("/v1/feedbacks/{feedback_id}", response_model=FeedbackItem)
def get_feedback(
    feedback_id: str,
    current_user: UserDB = Depends(_require_web_user),
    db: Session = Depends(get_db),
):
    fb = feedback_service.get_feedback(db, feedback_id, current_user.id)
    if not fb:
        raise HTTPException(404, "未找到该反馈")
    # auto mark read
    if not fb.is_read and fb.admin_reply:
        feedback_service.mark_read(db, feedback_id, current_user.id)
        fb.is_read = True
    return _fb_to_item(fb)


@app.post("/v1/feedbacks/{feedback_id}/read")
def mark_feedback_read(
    feedback_id: str,
    current_user: UserDB = Depends(_require_web_user),
    db: Session = Depends(get_db),
):
    fb = feedback_service.mark_read(db, feedback_id, current_user.id)
    if not fb:
        raise HTTPException(404, "未找到该反馈")
    return {"ok": True}


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ─── Static Files & SPA Routing ──────────────────────────────────────────────

# Serve uploaded files (avatars etc.) from shared uploads directory
_uploads_dir = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent.parent / "uploads")))
if _uploads_dir.is_dir():
    app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")

# Mount frontend if dist exists
dist_path = os.path.join(os.getcwd(), "frontend/dist")
if os.path.exists(dist_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # 1. Define and resolve the absolute safe root
        base_path = os.path.realpath(dist_path)
        
        # 2. Resolve the requested path (handling .. and symlinks)
        # We lstrip("/") to prevent os.path.join from treating it as an absolute path
        fullpath = os.path.realpath(os.path.join(base_path, full_path.lstrip("/")))
        
        # 3. Security Check: The normalized path must start with the base_path
        if not fullpath.startswith(base_path):
            return FileResponse(os.path.join(base_path, "index.html"))
            
        # 4. Final check: if it's a valid file, serve it
        if os.path.isfile(fullpath):
            return FileResponse(fullpath)
            
        # Otherwise fallback to index.html for SPA routing
        return FileResponse(os.path.join(base_path, "index.html"))


def run() -> None:
    import uvicorn
    from pathlib import Path

    log_config = str(Path(__file__).parent / "logging_config.yaml")
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False, log_config=log_config)
