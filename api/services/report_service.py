"""Report service for database operations."""

import json
import json_repair
import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import String, cast, func, literal
from sqlalchemy.orm import Session, load_only
from uuid import uuid4

from api.database import AnalysisJobDB, ReportDB
from api.services import report_outcome_service

from tradingagents.agents.utils.debate_utils import strip_public_debate_machine_blocks

logger = logging.getLogger(__name__)

# ReportDB 列宽（与 api/database.py 中 ReportDB 定义一致）
_DB_SYMBOL_MAX = 20
_DB_TRADE_DATE_MAX = 20
_DB_DECISION_MAX = 50
_DB_DIRECTION_MAX = 50
_DB_ANALYSIS_PRICE_TIME_MAX = 20


def _clip_db_str(value: Optional[str], max_len: int) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) <= max_len:
        return s
    return s[:max_len]


def _normalize_analysis_price_time_for_db(value: Optional[str]) -> Optional[str]:
    """写入 ReportDB.analysis_price_time（String(20)）：优先压成 YYYY-MM-DD HH:MM，避免行情 ISO 串触发 MySQL Data too long。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        out = dt.strftime("%Y-%m-%d %H:%M")
        return out[:_DB_ANALYSIS_PRICE_TIME_MAX]
    except Exception:
        return _clip_db_str(s, _DB_ANALYSIS_PRICE_TIME_MAX)


def _markdown_field(val: Any) -> Optional[str]:
    """LangGraph 状态里偶见非 str；ReportDB 报告列为 Text，必须落字符串。"""
    if val is None:
        return None
    if not isinstance(val, str):
        val = str(val)
    return strip_public_debate_machine_blocks(val)


def _json_safe_for_db(obj: Any, depth: int = 0) -> Any:
    """保证 JSON 列可序列化（datetime / 自定义对象等），避免落库阶段静默失败。"""
    if depth > 48:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, datetime):
        if obj.tzinfo is not None:
            return obj.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe_for_db(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe_for_db(v, depth + 1) for v in obj]
    if isinstance(obj, set):
        return [_json_safe_for_db(v, depth + 1) for v in obj]
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return str(obj)
    return str(obj)


REPORT_SUMMARY_COLUMNS = (
    ReportDB.id,
    ReportDB.user_id,
    ReportDB.symbol,
    ReportDB.trade_date,
    ReportDB.status,
    ReportDB.error,
    ReportDB.decision,
    ReportDB.direction,
    ReportDB.rating_5tier,
    ReportDB.confidence,
    ReportDB.target_price,
    ReportDB.stop_loss_price,
    ReportDB.risk_items,
    ReportDB.key_metrics,
    ReportDB.analyst_traces,
    ReportDB.final_decision_summary,
    ReportDB.analysis_price,
    ReportDB.analysis_price_time,
    ReportDB.release_version,
    ReportDB.created_at,
    ReportDB.updated_at,
)


def _json_text_key(column, key: str):
    """JSON 路径取值并转为可比较的字符串（跨 MySQL / SQLite / PostgreSQL）。"""
    return cast(column[key], String)


def _apply_report_task_kind_filter(query, task_kind: Optional[str]):
    """按任务类型筛选报告：fast_analysis 或 full_analysis（含缺省）。"""
    if not task_kind or task_kind not in ("fast_analysis", "full_analysis"):
        return query
    query = query.outerjoin(AnalysisJobDB, AnalysisJobDB.id == ReportDB.id)
    job_tk = _json_text_key(AnalysisJobDB.request_payload, "task_kind")
    res_tk = _json_text_key(ReportDB.result_data, "task_kind")
    effective = func.coalesce(job_tk, res_tk, literal("full_analysis"))
    if task_kind == "fast_analysis":
        return query.filter(effective == "fast_analysis")
    return query.filter(effective != "fast_analysis")


def _extract_task_kind_value(payload: Any) -> Optional[str]:
    """Best-effort extract task_kind from json payload-like objects."""
    if isinstance(payload, dict):
        raw = payload.get("task_kind")
        tk = str(raw or "").strip()
        return tk if tk else None
    return None


def _load_effective_task_kind_map(db: Session, report_ids: List[str]) -> Dict[str, str]:
    """Resolve effective task_kind for a report batch without join-based filesort."""
    normalized_ids: List[str] = []
    seen: set[str] = set()
    for rid in report_ids:
        srid = str(rid or "").strip()
        if not srid or srid in seen:
            continue
        seen.add(srid)
        normalized_ids.append(srid)
    if not normalized_ids:
        return {}

    resolved: Dict[str, str] = {}
    # Prefer analysis_jobs.request_payload.task_kind when available.
    job_rows = (
        db.query(AnalysisJobDB.id, AnalysisJobDB.request_payload)
        .filter(AnalysisJobDB.id.in_(normalized_ids))
        .all()
    )
    for rid, payload in job_rows:
        tk = _extract_task_kind_value(payload)
        if tk:
            resolved[str(rid)] = tk

    missing_ids = [rid for rid in normalized_ids if rid not in resolved]
    if missing_ids:
        # Fallback to reports.result_data.task_kind for records without analysis_job.
        report_rows = (
            db.query(ReportDB.id, ReportDB.result_data)
            .filter(ReportDB.id.in_(missing_ids))
            .all()
        )
        for rid, payload in report_rows:
            tk = _extract_task_kind_value(payload)
            if tk:
                resolved[str(rid)] = tk

    for rid in normalized_ids:
        resolved.setdefault(rid, "full_analysis")
    return resolved


def _matches_task_kind_filter(effective_task_kind: str, task_kind_filter: str) -> bool:
    tk = str(effective_task_kind or "").strip() or "full_analysis"
    if task_kind_filter == "fast_analysis":
        return tk == "fast_analysis"
    return tk != "fast_analysis"


ACTIVE_REPORT_STATUSES = ("pending", "running")
STALE_REPORT_ERROR_MESSAGE = "分析任务已中断，请重新发起分析"

_REPORT_MARKDOWN_COLUMNS = frozenset(
    {
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "macro_report",
        "smart_money_report",
        "volume_price_report",
        "game_theory_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    }
)


# ─── Structured extraction schemas ───────────────────────────────────────────


class RiskItemSchema(BaseModel):
    name: str = Field(..., description="风险名称，15字以内")
    level: str = Field("medium", description="风险等级")
    description: str = Field("", description="一句话说明，30字以内")

    @field_validator("level", mode="before")
    @classmethod
    def _coerce_level(cls, v):
        if isinstance(v, str) and v.lower() in ("high", "medium", "low"):
            return v.lower()
        return "medium"


class KeyMetricSchema(BaseModel):
    name: str = Field(..., description="指标名称，如 PE、ROE、营收增速")
    value: str = Field(..., description="指标值，包含单位，如 28.5x、15.2%")
    status: str = Field("neutral", description="优劣判断")

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v):
        # LLM 可能返回数字而非字符串
        return str(v) if not isinstance(v, str) else v

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v):
        if isinstance(v, str) and v.lower() in ("good", "neutral", "bad"):
            return v.lower()
        return "neutral"


class StructuredReport(BaseModel):
    decision: str = Field(
        "HOLD",
        description="报告中归纳的方向关键词：BUY/SELL/HOLD/增持/减持/持有 等（非投资建议）",
    )
    confidence: Optional[int] = Field(None, description="整体置信度 0-100")
    target_price: Optional[float] = Field(None, description="偏多参考峰值（数字，无单位）")
    stop_loss_price: Optional[float] = Field(None, description="偏空参考风控（数字，无单位）")
    risks: List[RiskItemSchema] = Field(default_factory=list, description="主要风险，最多5条")
    key_metrics: List[KeyMetricSchema] = Field(default_factory=list, description="关键指标，最多6条")

    @field_validator("target_price", "stop_loss_price", mode="before")
    @classmethod
    def _coerce_price(cls, v):
        # LLM 可能返回数组 [34.0, 32.5] 而非单个数字，取第一个
        if isinstance(v, list):
            return v[0] if v else None
        return v


def extract_structured_data(
    final_trade_decision: str,
    fundamentals_report: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> Optional[StructuredReport]:
    """Use LLM structured output to extract key data from report text."""
    if not final_trade_decision:
        return None
    if config is None:
        from tradingagents.default_config import DEFAULT_CONFIG
        config = DEFAULT_CONFIG

    try:
        from langchain_core.messages import HumanMessage
        from tradingagents.llm_clients import create_llm_client

        client = create_llm_client(
            provider=config.get("llm_provider", "openai"),
            model=config.get("quick_think_llm", "gpt-4o-mini"),
            base_url=config.get("backend_url"),
            api_key=config.get("api_key"),
        )
        llm = client.get_llm()

        prompt = (
            "请从以下投资分析报告中提取结构化信息，并以 JSON 格式返回。\n\n"
            f"【沙盘综合研判结论】\n{final_trade_decision[:3000]}\n\n"
            f"【基本面报告摘要】\n{fundamentals_report[:1000]}\n\n"
            "提取要求（请确保输出为有效的 JSON 对象，不要包裹在 markdown 代码块中）：\n"
            "1. decision：决策方向关键词（BUY/SELL/HOLD 或 增持/减持/持有）\n"
            "2. confidence：整体置信度（0-100整数），若文中未明确给出则根据语气判断\n"
            "3. target_price / stop_loss_price：纯数字，若未提及则为 null\n"
            "4. risks：最多5条主要风险，每条包含名称（15字内）、等级（high/medium/low）、一句话说明\n"
            "5. key_metrics：最多6条关键财务/估值指标，每条包含名称、值（含单位）、优劣（good/neutral/bad）"
        )

        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content if hasattr(response, "content") else str(response)
        parsed = json_repair.loads(raw)
        result = StructuredReport(**parsed)
        if result.confidence is not None and not (0 <= result.confidence <= 100):
            result.confidence = None
        return result
    except Exception as e:
        logger.warning(f"LLM structured extraction failed: {e}")
        if 'raw' in locals():
            logger.warning(f"Raw LLM output:\n{raw}")
        return None


def _trim_summary_cn(text: str, *, max_chars: int = 450) -> str:
    """硬上限，防止模型超长输出撑爆卡片。"""
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def summarize_final_decision_for_card(
    final_trade_decision: str,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """用 LLM 将沙盘综合研判压成约 300–400 字中文要点，供决策卡「要点梳理」。"""
    raw = (os.getenv("TA_FINAL_DECISION_SUMMARY_ENABLED", "1") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return None
    body = (final_trade_decision or "").strip()
    if not body:
        return None
    if config is None:
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG

    try:
        from langchain_core.messages import HumanMessage
        from tradingagents.llm_clients import create_llm_client

        client = create_llm_client(
            provider=config.get("llm_provider", "openai"),
            model=config.get("quick_think_llm", "gpt-4o-mini"),
            base_url=config.get("backend_url"),
            api_key=config.get("api_key"),
        )
        llm = client.get_llm()
        src = body[:14000]
        prompt = (
            "你是 A 股投研编辑。请将下列「沙盘综合研判结论」改写成一段**要点梳理**。\n\n"
            "硬性要求：\n"
            "1. 使用**简体中文**，纯叙述，不要用 Markdown 标题（#）、不要用列表符号起行。\n"
            "2. 总长度控制在 **300–400 个汉字**（约等于 300–400 个字符），不要短于 260 字。\n"
            "3. 保留：最终立场/方向、关键风控硬化条款、与执行相关的约束（如价位、仓位、触发条件）；删除套话与重复辩论过程。\n"
            "4. **禁止编造**文中没有的事实；信息不足就如实收敛表述，不要虚构数字。\n\n"
            f"【原文】\n{src}\n\n"
            "请直接输出要点梳理正文，不要前缀说明。"
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        out = response.content if hasattr(response, "content") else str(response)
        out = (out or "").strip()
        if len(out) < 80:
            logger.warning("final_decision_summary too short (%s chars), ignored", len(out))
            return None
        return _trim_summary_cn(out)
    except Exception as e:
        logger.warning("summarize_final_decision_for_card failed: %s", e)
        return None


# ─── Fallback regex extraction (used when LLM extraction unavailable) ─────────

def _extract_confidence_regex(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    for pattern in (r'置信度[:：]\s*(\d+)%', r'confidence[:：]\s*(\d+)%'):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            v = int(m.group(1))
            return v if 0 <= v <= 100 else None
    return None


def _extract_price_regex(text: Optional[str], price_type: str = "target") -> Optional[float]:
    if not text:
        return None
    if price_type == "target":
        patterns = [
            r'目标价[:：]\s*[¥$]?\s*(\d+\.?\d*)',
            r'目标价格[:：]\s*[¥$]?\s*(\d+\.?\d*)',
            r'target[:：]\s*[¥$]?\s*(\d+\.?\d*)',
        ]
    else:
        patterns = [
            r'止损价[:：]\s*[¥$]?\s*(\d+\.?\d*)',
            r'止损价格[:：]\s*[¥$]?\s*(\d+\.?\d*)',
            r'stop[-\s_]?loss[:：]\s*[¥$]?\s*(\d+\.?\d*)',
        ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def _extract_verdict(text: Optional[str]) -> Optional[Dict[str, str]]:
    if not text:
        return None
    match = re.search(r"<!--\s*VERDICT:\s*(\{.*?\})\s*-->", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    try:
        # Clean potential newlines or invisible characters common in LLM outputs
        raw_json = match.group(1).strip().replace('\n', ' ').replace('\r', ' ')
        payload = json.loads(raw_json)
    except Exception:
        return None
    direction = str(payload.get("direction") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if not direction:
        return None
    result: Dict[str, str] = {"direction": direction, "reason": reason}
    rating = payload.get("rating_5tier") or payload.get("rating")
    if rating:
        result["rating_5tier"] = str(rating).strip()
    return result


def resolve_report_fields(
    result_data: Optional[Dict[str, Any]] = None,
    confidence_override: Optional[int] = None,
    target_price_override: Optional[float] = None,
    stop_loss_override: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolve the final structured fields once for both SSE payloads and DB writes."""
    market_report = sentiment_report = news_report = None
    fundamentals_report = macro_report = smart_money_report = volume_price_report = game_theory_report = None
    investment_plan = trader_investment_plan = None
    final_trade_decision = None

    if result_data:
        market_report = result_data.get("market_report")
        sentiment_report = result_data.get("sentiment_report")
        news_report = result_data.get("news_report")
        fundamentals_report = result_data.get("fundamentals_report")
        macro_report = result_data.get("macro_report")
        smart_money_report = result_data.get("smart_money_report")
        volume_price_report = result_data.get("volume_price_report")
        game_theory_report = result_data.get("game_theory_report")
        investment_plan = result_data.get("investment_plan")
        trader_investment_plan = result_data.get("trader_investment_plan")
        final_trade_decision = result_data.get("final_trade_decision")

    verdict = _extract_verdict(final_trade_decision)
    direction = verdict["direction"] if verdict else None

    confidence = confidence_override if confidence_override is not None else _extract_confidence_regex(final_trade_decision)

    from tradingagents.agents.utils.rating import extract_rating_5tier_from_text, parse_rating

    rating_raw = verdict.get("rating_5tier") if verdict else None
    rating_5tier = parse_rating(rating_raw) if rating_raw else None
    if not rating_5tier:
        rating_5tier = extract_rating_5tier_from_text(
            final_trade_decision,
            direction=direction,
            confidence=confidence,
            decision=(result_data or {}).get("decision") if result_data else None,
        )

    target_price = target_price_override if target_price_override is not None else _extract_price_regex(final_trade_decision, "target")
    if target_price is None:
        target_price = _extract_price_regex(trader_investment_plan, "target")

    stop_loss_price = stop_loss_override if stop_loss_override is not None else _extract_price_regex(final_trade_decision, "stop_loss")
    if stop_loss_price is None:
        stop_loss_price = _extract_price_regex(trader_investment_plan, "stop_loss")

    return {
        "market_report": _markdown_field(market_report),
        "sentiment_report": _markdown_field(sentiment_report),
        "news_report": _markdown_field(news_report),
        "fundamentals_report": _markdown_field(fundamentals_report),
        "macro_report": _markdown_field(macro_report),
        "smart_money_report": _markdown_field(smart_money_report),
        "volume_price_report": _markdown_field(volume_price_report),
        "game_theory_report": _markdown_field(game_theory_report),
        "investment_plan": _markdown_field(investment_plan),
        "trader_investment_plan": _markdown_field(trader_investment_plan),
        "final_trade_decision": _markdown_field(final_trade_decision),
        "direction": direction,
        "confidence": confidence,
        "target_price": target_price,
        "stop_loss_price": stop_loss_price,
        "rating_5tier": rating_5tier,
    }


def ensure_rating_5tier(db: Session, report: ReportDB, *, persist: bool = True) -> Optional[str]:
    """Backfill missing five-tier rating from stored decision fields."""
    from tradingagents.agents.utils.rating import extract_rating_5tier_from_text

    existing = getattr(report, "rating_5tier", None)
    if existing:
        return str(existing)
    rating = extract_rating_5tier_from_text(
        getattr(report, "final_trade_decision", None),
        direction=getattr(report, "direction", None),
        confidence=getattr(report, "confidence", None),
        decision=getattr(report, "decision", None),
    )
    if not rating:
        return None
    if persist:
        report.rating_5tier = rating
        report.updated_at = datetime.now(timezone.utc)
        db.commit()
        try:
            db.refresh(report)
        except Exception:
            pass
    else:
        report.rating_5tier = rating
    return rating


# ─── CRUD ────────────────────────────────────────────────────────────────────

def init_report(
    db: Session,
    report_id: str,
    symbol: str,
    trade_date: str,
    user_id: Optional[str] = None,
) -> ReportDB:
    """Create a pending report record when a job is submitted."""
    if user_id is None or not str(user_id).strip():
        raise ValueError("user_id is required for init_report")
    existing = db.query(ReportDB).filter(ReportDB.id == report_id).first()
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    db_report = ReportDB(
        id=report_id,
        user_id=user_id,
        symbol=symbol,
        trade_date=trade_date,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    try:
        report_outcome_service.enqueue_for_report(db, db_report)
        report_outcome_service.evaluate_report_outcome(db, str(db_report.id))
    except Exception as exc:
        logger.warning("enqueue report outcome failed report_id=%s err=%s", db_report.id, exc)
    return db_report


def update_report_partial(
    db: Session,
    report_id: str,
    status: Optional[str] = None,
    **fields: Any
) -> Optional[ReportDB]:
    """Update specific fields of an existing report (e.g., partial analyst reports)."""
    db_report = db.query(ReportDB).filter(ReportDB.id == report_id).first()
    if not db_report:
        return None
    
    if status:
        db_report.status = status
    
    for key, value in fields.items():
        if hasattr(db_report, key):
            if key in _REPORT_MARKDOWN_COLUMNS and isinstance(value, str):
                value = strip_public_debate_machine_blocks(value)
            setattr(db_report, key, value)
    
    db_report.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_report)
    return db_report


def finalize_orphan_report(
    db: Session,
    report: ReportDB,
    *,
    error_message: str = STALE_REPORT_ERROR_MESSAGE,
) -> ReportDB:
    """Mark an orphaned pending/running report as failed."""
    if str(report.status or "") not in ACTIVE_REPORT_STATUSES:
        return report

    report.status = "failed"
    report.error = error_message
    report.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    return report


def recover_stale_active_reports(
    db: Session,
    *,
    active_job_ids: Optional[Iterable[str]] = None,
    error_message: str = STALE_REPORT_ERROR_MESSAGE,
) -> Dict[str, int]:
    """Recover stale pending/running reports left behind by interrupted jobs."""
    active_job_id_set = {str(job_id) for job_id in (active_job_ids or []) if str(job_id).strip()}
    rows = (
        db.query(ReportDB)
        .filter(ReportDB.status.in_(ACTIVE_REPORT_STATUSES))
        .all()
    )
    if not rows:
        return {"total": 0, "completed": 0, "failed": 0}

    failed = 0
    skipped = 0
    changed = False
    now = datetime.now(timezone.utc)
    for row in rows:
        if str(row.id) in active_job_id_set:
            skipped += 1
            continue
        row.status = "failed"
        row.error = error_message
        row.updated_at = now
        changed = True
        failed += 1

    if changed:
        db.commit()

    return {
        "total": len(rows),
        "completed": skipped,
        "failed": failed,
    }


def mark_report_failed(
    db: Session,
    report_id: str,
    error_message: str
) -> Optional[ReportDB]:
    """Mark a report as failed with an error message."""
    return update_report_partial(db, report_id, status="failed", error=error_message)


def create_report(
    db: Session,
    symbol: str,
    trade_date: str,
    decision: Optional[str] = None,
    result_data: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    risk_items: Optional[List[dict]] = None,
    key_metrics: Optional[List[dict]] = None,
    analyst_traces: Optional[List[dict]] = None,
    confidence_override: Optional[int] = None,
    target_price_override: Optional[float] = None,
    stop_loss_override: Optional[float] = None,
    analysis_price: Optional[float] = None,
    analysis_price_time: Optional[str] = None,
    data_sources_json: Optional[Dict[str, Any]] = None,
    report_id: Optional[str] = None,  # If provided, update existing
    llm_config: Optional[Dict[str, Any]] = None,
) -> ReportDB:
    """Create or finalize a report."""
    merged_result = dict(result_data or {})
    if decision and not merged_result.get("decision"):
        merged_result["decision"] = decision
    resolved = resolve_report_fields(
        result_data=merged_result,
        confidence_override=confidence_override,
        target_price_override=target_price_override,
        stop_loss_override=stop_loss_override,
    )
    final_decision_summary = summarize_final_decision_for_card(
        resolved.get("final_trade_decision") or "",
        llm_config,
    )

    safe_result_data = _json_safe_for_db(result_data) if result_data else None
    safe_data_sources = _json_safe_for_db(data_sources_json) if data_sources_json else None
    safe_risks = _json_safe_for_db(risk_items) if risk_items else None
    safe_metrics = _json_safe_for_db(key_metrics) if key_metrics else None
    safe_traces = _json_safe_for_db(analyst_traces) if analyst_traces else None

    sym = _clip_db_str(str(symbol or "").strip(), _DB_SYMBOL_MAX) or ""
    td = _clip_db_str(str(trade_date or "").strip(), _DB_TRADE_DATE_MAX) or ""
    dec = _clip_db_str(str(decision).strip() if decision is not None else "", _DB_DECISION_MAX)
    apt = _normalize_analysis_price_time_for_db(analysis_price_time)
    rd = resolved.get("direction")
    direction_clip = (
        _clip_db_str(str(rd).strip(), _DB_DIRECTION_MAX)
        if rd is not None and str(rd).strip()
        else None
    )

    now = datetime.now(timezone.utc)
    release_version = str(os.getenv("TA_RELEASE_VERSION") or "dev").strip() or "dev"

    # Check if we should update an existing record (initialized via init_report)
    db_report = None
    if report_id:
        db_report = db.query(ReportDB).filter(ReportDB.id == report_id).first()

    if db_report is None and (user_id is None or not str(user_id).strip()):
        raise ValueError("user_id is required for create_report when creating a new report")

    if db_report:
        # Update existing
        db_report.status = "completed"
        db_report.symbol = sym
        db_report.trade_date = td
        db_report.decision = dec
        db_report.direction = direction_clip
        db_report.rating_5tier = _clip_db_str(resolved.get("rating_5tier") or "", 16) or None
        db_report.confidence = resolved["confidence"]
        db_report.target_price = resolved["target_price"]
        db_report.stop_loss_price = resolved["stop_loss_price"]
        if analysis_price is not None:
            db_report.analysis_price = analysis_price
        if apt is not None:
            db_report.analysis_price_time = apt
        db_report.result_data = safe_result_data
        db_report.data_sources_json = safe_data_sources
        db_report.risk_items = safe_risks
        db_report.key_metrics = safe_metrics
        db_report.analyst_traces = safe_traces
        db_report.market_report = resolved["market_report"]
        db_report.sentiment_report = resolved["sentiment_report"]
        db_report.news_report = resolved["news_report"]
        db_report.fundamentals_report = resolved["fundamentals_report"]
        db_report.macro_report = resolved["macro_report"]
        db_report.smart_money_report = resolved["smart_money_report"]
        db_report.volume_price_report = resolved["volume_price_report"]
        db_report.game_theory_report = resolved["game_theory_report"]
        db_report.investment_plan = resolved["investment_plan"]
        db_report.trader_investment_plan = resolved["trader_investment_plan"]
        db_report.final_trade_decision = resolved["final_trade_decision"]
        db_report.final_decision_summary = final_decision_summary
        db_report.release_version = release_version
        db_report.updated_at = now
    else:
        # Create new
        db_report = ReportDB(
            id=report_id or str(uuid4()),
            user_id=user_id,
            symbol=sym,
            trade_date=td,
            status="completed",
            decision=dec,
            direction=direction_clip,
            rating_5tier=_clip_db_str(resolved.get("rating_5tier") or "", 16) or None,
            confidence=resolved["confidence"],
            target_price=resolved["target_price"],
            stop_loss_price=resolved["stop_loss_price"],
            analysis_price=analysis_price,
            analysis_price_time=apt,
            result_data=safe_result_data,
            data_sources_json=safe_data_sources,
            risk_items=safe_risks,
            key_metrics=safe_metrics,
            analyst_traces=safe_traces,
            market_report=resolved["market_report"],
            sentiment_report=resolved["sentiment_report"],
            news_report=resolved["news_report"],
            fundamentals_report=resolved["fundamentals_report"],
            macro_report=resolved["macro_report"],
            smart_money_report=resolved["smart_money_report"],
            volume_price_report=resolved["volume_price_report"],
            game_theory_report=resolved["game_theory_report"],
            investment_plan=resolved["investment_plan"],
            trader_investment_plan=resolved["trader_investment_plan"],
            final_trade_decision=resolved["final_trade_decision"],
            final_decision_summary=final_decision_summary,
            release_version=release_version,
            created_at=now,
            updated_at=now,
        )
        db.add(db_report)

    db.commit()
    db.refresh(db_report)
    return db_report


def internal_get_report_by_id(db: Session, report_id: str) -> Optional[ReportDB]:
    """Internal/job use only — no tenant filter."""
    return db.query(ReportDB).filter(ReportDB.id == report_id).first()


def get_report(db: Session, report_id: str, user_id: str) -> Optional[ReportDB]:
    if user_id is None:
        raise ValueError("user_id is required for get_report")
    return (
        db.query(ReportDB)
        .filter(ReportDB.id == report_id, ReportDB.user_id == user_id)
        .first()
    )


def get_reports_by_user(
    db: Session,
    user_id: str,
    symbol: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    task_kind: Optional[str] = None,
) -> List[ReportDB]:
    if user_id is None:
        raise ValueError("user_id is required")
    query = db.query(ReportDB).options(load_only(*REPORT_SUMMARY_COLUMNS))
    query = query.filter(ReportDB.user_id == user_id)
    if symbol:
        query = query.filter(ReportDB.symbol == symbol)
    if not task_kind or task_kind not in ("fast_analysis", "full_analysis"):
        return query.order_by(ReportDB.created_at.desc()).offset(skip).limit(limit).all()

    base_query = query.order_by(ReportDB.created_at.desc())
    page_size = max(limit * 3, 120)
    cursor = 0
    remaining_skip = skip
    matched: List[ReportDB] = []
    scanned_rows = 0
    max_scan_rows = max(skip + limit * 30, 5000)

    while len(matched) < limit and scanned_rows < max_scan_rows:
        batch = base_query.offset(cursor).limit(page_size).all()
        if not batch:
            break
        scanned_rows += len(batch)
        tk_map = _load_effective_task_kind_map(db, [str(getattr(r, "id", "")) for r in batch])
        for row in batch:
            rid = str(getattr(row, "id", ""))
            if not _matches_task_kind_filter(tk_map.get(rid, "full_analysis"), task_kind):
                continue
            if remaining_skip > 0:
                remaining_skip -= 1
                continue
            matched.append(row)
            if len(matched) >= limit:
                break
        cursor += len(batch)
        if len(batch) < page_size:
            break
    return matched


def get_latest_reports_by_symbols(
    db: Session,
    symbols: List[str],
    user_id: str,
) -> List[ReportDB]:
    if user_id is None:
        raise ValueError("user_id is required")
    normalized_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    if not normalized_symbols:
        return []

    query = db.query(ReportDB).options(load_only(*REPORT_SUMMARY_COLUMNS))
    query = query.filter(ReportDB.user_id == user_id)
    rows = (
        query.filter(ReportDB.symbol.in_(normalized_symbols))
        .order_by(ReportDB.symbol.asc(), ReportDB.created_at.desc())
        .all()
    )

    latest_by_symbol: dict[str, ReportDB] = {}
    for row in rows:
        symbol = str(row.symbol or "").upper()
        if symbol and symbol not in latest_by_symbol:
            latest_by_symbol[symbol] = row

    return [latest_by_symbol[symbol] for symbol in normalized_symbols if symbol in latest_by_symbol]


def count_reports(
    db: Session,
    user_id: str,
    symbol: Optional[str] = None,
    task_kind: Optional[str] = None,
) -> int:
    if user_id is None:
        raise ValueError("user_id is required")
    query = db.query(func.count(func.distinct(ReportDB.id))).select_from(ReportDB)
    query = query.filter(ReportDB.user_id == user_id)
    if symbol:
        query = query.filter(ReportDB.symbol == symbol)
    if not task_kind or task_kind not in ("fast_analysis", "full_analysis"):
        return query.scalar() or 0

    # Avoid JSON_EXTRACT + JOIN count on MySQL that may trigger huge filesort memory.
    id_query = db.query(ReportDB.id).filter(ReportDB.user_id == user_id)
    if symbol:
        id_query = id_query.filter(ReportDB.symbol == symbol)

    total = 0
    cursor = 0
    batch_size = 500
    while True:
        rows = id_query.offset(cursor).limit(batch_size).all()
        if not rows:
            break
        ids = [str(row[0]) for row in rows]
        tk_map = _load_effective_task_kind_map(db, ids)
        total += sum(1 for rid in ids if _matches_task_kind_filter(tk_map.get(rid, "full_analysis"), task_kind))
        cursor += len(rows)
        if len(rows) < batch_size:
            break
    return total


def delete_report(db: Session, report_id: str, user_id: str) -> bool:
    if user_id is None:
        raise ValueError("user_id is required")
    query = db.query(ReportDB).filter(ReportDB.id == report_id, ReportDB.user_id == user_id)
    report = query.first()
    if report:
        db.delete(report)
        db.commit()
        return True
    return False


def batch_delete_reports(db: Session, report_ids: Iterable[str], user_id: str) -> dict:
    if user_id is None:
        raise ValueError("user_id is required")
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for raw_report_id in report_ids:
        report_id = str(raw_report_id or "").strip()
        if not report_id or report_id in seen:
            continue
        seen.add(report_id)
        normalized_ids.append(report_id)

    if not normalized_ids:
        raise ValueError("请至少选择 1 份报告")

    query = db.query(ReportDB).filter(ReportDB.id.in_(normalized_ids), ReportDB.user_id == user_id)

    rows = query.all()
    row_by_id = {str(row.id): row for row in rows}
    deleted_ids: list[str] = []
    missing_ids: list[str] = []

    for report_id in normalized_ids:
        row = row_by_id.get(report_id)
        if row is None:
            missing_ids.append(report_id)
            continue
        db.delete(row)
        deleted_ids.append(report_id)

    if deleted_ids:
        db.commit()

    return {
        "deleted_ids": deleted_ids,
        "missing_ids": missing_ids,
    }
