from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any, Dict, Iterable, Literal, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy.orm import Session

from api.database import AnalysisJobDB, ReportDB, ReportOutcomeDB
from api.symbol_utils import normalize_exchange_symbol
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider
from tradingagents.dataflows.trade_calendar import cn_today_str, is_cn_trading_day

CN_TZ = ZoneInfo("Asia/Shanghai")

OutcomeStatus = Literal["hit", "neutral", "miss", "pending"]

FAST_WEIGHTS = {"t0": 0.5, "t1": 0.5}
# 智能分析窗口：T+1（次日反应）、T+2（主窗口/第二日确认）、T+3（中段验证）、T+5（中线兑现）
FULL_WEIGHTS = {"t1": 0.15, "t2": 0.35, "t3": 0.25, "t5": 0.25}


def outcome_enabled() -> bool:
    """默认开启报告兑现度（T+N）；仅在显式关闭时跳过计算与回填。

    历史原因：早期实现用「未设置=关闭」，导致本地/生产未配环境变量时列表一直无 outcome。
    """
    raw = (os.getenv("TA_REPORT_OUTCOME_ENABLED") or "").strip().lower()
    if raw in ("0", "false", "no", "off", "disabled"):
        return False
    return True


def release_version() -> str:
    return str(os.getenv("TA_RELEASE_VERSION") or "dev").strip() or "dev"


def _safe_float(v: Any) -> float | None:
    try:
        n = float(v)
    except Exception:
        return None
    if math.isnan(n) or math.isinf(n):
        return None
    return n


def _parse_trade_date(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return cn_today_str()
    if " " in s:
        s = s.split(" ", 1)[0]
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except Exception:
        return cn_today_str()


def _advance_cn_trading_days(base_date: str, trading_days: int) -> str:
    d = datetime.strptime(base_date, "%Y-%m-%d").date()
    if trading_days <= 0:
        return d.strftime("%Y-%m-%d")
    remain = trading_days
    cur = d
    while remain > 0:
        cur = cur + timedelta(days=1)
        if is_cn_trading_day(cur.strftime("%Y-%m-%d")):
            remain -= 1
    return cur.strftime("%Y-%m-%d")


def _task_kind_for_report(db: Session, report: ReportDB) -> str:
    payload = dict(getattr(report, "result_data", None) or {})
    tk = str(payload.get("task_kind") or "").strip()
    if tk:
        return tk
    row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == str(report.id)).first()
    req = dict(getattr(row, "request_payload", None) or {}) if row else {}
    tk = str(req.get("task_kind") or "").strip()
    return tk or "full_analysis"


def _horizons_for_task_kind(task_kind: str) -> list[str]:
    return ["t0", "t1"] if task_kind == "fast_analysis" else ["t1", "t2", "t3", "t5"]


def _weights_for_task_kind(task_kind: str) -> dict[str, float]:
    return FAST_WEIGHTS if task_kind == "fast_analysis" else FULL_WEIGHTS


def _primary_horizon(task_kind: str) -> str:
    return "t0" if task_kind == "fast_analysis" else "t2"


def _direction_label(report: ReportDB) -> str:
    d = str(getattr(report, "direction", "") or "").strip().lower()
    dec = str(getattr(report, "decision", "") or "").strip().lower()
    if any(k in d for k in ("看多", "偏多")) or any(k in dec for k in ("buy", "增持", "看多")):
        return "bull"
    if any(k in d for k in ("看空", "偏空")) or any(k in dec for k in ("sell", "减持", "看空")):
        return "bear"
    return "neutral"


def _score_for_status(status: OutcomeStatus) -> int:
    if status == "hit":
        return 100
    if status == "neutral":
        return 50
    if status == "miss":
        return 0
    return 0


def _outcome_threshold(baseline: float | None, atr20: float | None) -> float:
    """自适应兑现度阈值：按标的自身波动率分档，避免高 β 一律「震荡」。

    分档（ATR / baseline 比例 = 日均波幅%）：
      - 低波（< 1.5%）：threshold = ATR × 0.5（约 ≤0.75%）
      - 中波（1.5% – 3%）：threshold = ATR × 0.4（约 0.6% – 1.2%）
      - 高波（> 3%）：threshold = max(ATR × 0.3, baseline × 1.5%)
                       且对真实 ATR 设上限 cap = baseline × `TA_REPORT_OUTCOME_ATR_CAP_PCT`（默认 4%），
                       让高波股也能稳定触发命中/偏离，而不是反复落到「震荡」。

    无 ATR 时回退到 `baseline × 1%` 作为兜底阈值。
    可通过 `TA_REPORT_OUTCOME_THRESHOLD_FACTOR` 全局缩放（默认 1.0）。
    """
    if not baseline or baseline <= 0:
        baseline = baseline or 0.0

    try:
        scale = float(os.getenv("TA_REPORT_OUTCOME_THRESHOLD_FACTOR", "1.0"))
    except (TypeError, ValueError):
        scale = 1.0
    scale = max(0.2, min(scale, 3.0))

    if not atr20 or atr20 <= 0:
        return max(baseline * 0.01, 1e-6) * scale

    try:
        cap_pct = float(os.getenv("TA_REPORT_OUTCOME_ATR_CAP_PCT", "0.04"))
    except (TypeError, ValueError):
        cap_pct = 0.04
    cap_pct = max(0.005, min(cap_pct, 0.10))

    atr_pct = atr20 / baseline if baseline > 0 else 0.0
    eff_atr = atr20
    if baseline > 0:
        eff_atr = min(atr20, baseline * cap_pct)

    if atr_pct < 0.015:
        thr = eff_atr * 0.5
    elif atr_pct < 0.03:
        thr = eff_atr * 0.4
    else:
        thr = max(eff_atr * 0.3, baseline * 0.015)
    return max(thr, 1e-6) * scale


def _evaluate_direction(
    *,
    direction: str,
    delta: float,
    threshold: float,
) -> OutcomeStatus:
    if direction == "bull":
        if delta >= threshold:
            return "hit"
        if delta <= -threshold:
            return "miss"
        return "neutral"
    if direction == "bear":
        if delta <= -threshold:
            return "hit"
        if delta >= threshold:
            return "miss"
        return "neutral"
    if abs(delta) < threshold:
        return "hit"
    return "miss"


def _to_cn_close_utc(date_str: str) -> datetime:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=16, minute=0, second=0)
    dt = dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(timezone.utc)


def _normalize_kline_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    columns = {str(c).strip().lower(): c for c in df.columns}
    date_col = columns.get("date") or columns.get("trade_date")
    close_col = columns.get("close")
    high_col = columns.get("high")
    low_col = columns.get("low")
    if not date_col or not close_col:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    out["close"] = pd.to_numeric(df[close_col], errors="coerce")
    out["high"] = pd.to_numeric(df[high_col], errors="coerce") if high_col else out["close"]
    out["low"] = pd.to_numeric(df[low_col], errors="coerce") if low_col else out["close"]
    out = out.dropna(subset=["date", "close", "high", "low"])
    out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return out.reset_index(drop=True)


def _fetch_kline_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    # 优先 Tushare 历史日线，确保兑现度 T+N 有稳定数据源。
    try:
        tsh = CnTushareProvider()
        tsh_df = tsh.fetch_daily_bar_df(symbol, start_date, end_date, adjust="qfq")
        frame = _normalize_kline_frame(tsh_df)
        if not frame.empty:
            return frame
    except Exception:
        pass

    # 兜底走通用 provider 链。返回的 CSV 通常前面带 `# ...` 注释 + 空行 + 表头，
    # 默认 pd.read_csv 不识别 `#`，遇到「字段数不一致」直接 ParserError；用更宽松解析。
    raw = route_to_vendor("get_stock_data", symbol, start_date, end_date)
    if not isinstance(raw, str) or not raw.strip():
        return pd.DataFrame()
    try:
        df = pd.read_csv(StringIO(raw), comment="#", skip_blank_lines=True)
    except Exception:
        try:
            df = pd.read_csv(
                StringIO(raw),
                comment="#",
                skip_blank_lines=True,
                engine="python",
                on_bad_lines="skip",
            )
        except Exception:
            return pd.DataFrame()
    return _normalize_kline_frame(df)


def _backfill_outcomes_for_reports(
    db: Session,
    *,
    user_id: str,
    report_ids: Iterable[str],
) -> None:
    """补齐 outcome 行：1) 缺失则首次入队 + 评估；2) 已存在但窗口未结算（T+N 到期）则重评。

    步骤 (2) 设有限流（默认 8 个/请求），避免列表加载触发大批量 K 线拉取。可通过
    `TA_REPORT_OUTCOME_RELOAD_LIMIT` 调整；置 0 关闭重评仅保留缺失补齐。
    """
    if not outcome_enabled():
        return
    ids = [str(x).strip() for x in report_ids if str(x).strip()]
    if not ids:
        return
    existing_ids = {
        str(x[0])
        for x in db.query(ReportOutcomeDB.id)
        .filter(ReportOutcomeDB.user_id == str(user_id), ReportOutcomeDB.id.in_(ids))
        .all()
    }
    missing = [rid for rid in ids if rid not in existing_ids]
    if missing:
        reports = (
            db.query(ReportDB)
            .filter(
                ReportDB.user_id == str(user_id),
                ReportDB.id.in_(missing),
                ReportDB.status == "completed",
            )
            .all()
        )
        for report in reports:
            rid = str(getattr(report, "id", "")).strip()
            if not rid:
                continue
            enqueue_for_report(db, report)
            evaluate_report_outcome(db, rid)

    try:
        reload_limit = int(os.getenv("TA_REPORT_OUTCOME_RELOAD_LIMIT", "8"))
    except Exception:
        reload_limit = 8
    if reload_limit <= 0:
        return

    now = datetime.now(timezone.utc)
    # MySQL 不支持 ORDER BY ... NULLS FIRST；MySQL ASC 默认 NULL 在前，
    # PostgreSQL/SQLite 也会先按 NULL 排序（NULL 视为最小值），跨方言兼容。
    due_rows = (
        db.query(ReportOutcomeDB.id)
        .filter(
            ReportOutcomeDB.user_id == str(user_id),
            ReportOutcomeDB.id.in_(ids),
            ReportOutcomeDB.total_windows > ReportOutcomeDB.settled_count,
            (ReportOutcomeDB.next_evaluate_after.is_(None))
            | (ReportOutcomeDB.next_evaluate_after <= now),
        )
        .order_by(ReportOutcomeDB.next_evaluate_after.asc())
        .limit(reload_limit)
        .all()
    )
    for (rid,) in due_rows:
        try:
            evaluate_report_outcome(db, str(rid))
        except Exception:
            continue


def enqueue_for_report(db: Session, report: ReportDB) -> Optional[ReportOutcomeDB]:
    if not outcome_enabled():
        return None
    if str(getattr(report, "status", "")).strip() != "completed":
        return None
    uid = str(getattr(report, "user_id", None) or "").strip()
    if not uid:
        return None

    task_kind = _task_kind_for_report(db, report)
    trade_date = _parse_trade_date(getattr(report, "trade_date", ""))
    horizons = _horizons_for_task_kind(task_kind)
    now = datetime.now(timezone.utc)
    next_horizon = horizons[0]
    next_days = 0 if next_horizon == "t0" else int(next_horizon[1:])
    next_after = _to_cn_close_utc(_advance_cn_trading_days(trade_date, next_days))
    baseline = _safe_float(getattr(report, "analysis_price", None))

    row = db.query(ReportOutcomeDB).filter(ReportOutcomeDB.id == str(report.id)).first()
    if row is None:
        row = ReportOutcomeDB(
            id=str(report.id),
            user_id=uid,
            task_kind=task_kind,
            symbol=str(report.symbol),
            trade_date=trade_date,
            release_version=str(getattr(report, "release_version", "") or release_version()),
            baseline_price=baseline,
            baseline_source="analysis_price" if baseline is not None else "kline_close",
            outcomes_json={h: {"status": "pending"} for h in horizons},
            settled_count=0,
            total_windows=len(horizons),
            primary_horizon=_primary_horizon(task_kind),
            primary_status="pending",
            next_evaluate_after=next_after,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.task_kind = task_kind
        row.symbol = str(report.symbol)
        row.trade_date = trade_date
        row.release_version = str(getattr(report, "release_version", "") or row.release_version or release_version())
        row.baseline_price = baseline if baseline is not None else row.baseline_price
        row.baseline_source = "analysis_price" if baseline is not None else (row.baseline_source or "kline_close")
        row.total_windows = len(horizons)
        row.primary_horizon = _primary_horizon(task_kind)
        row.next_evaluate_after = next_after
        row.updated_at = now
        if not isinstance(row.outcomes_json, dict):
            row.outcomes_json = {h: {"status": "pending"} for h in horizons}
    db.commit()
    db.refresh(row)
    return row


def evaluate_report_outcome(db: Session, report_id: str) -> Optional[ReportOutcomeDB]:
    row = db.query(ReportOutcomeDB).filter(ReportOutcomeDB.id == str(report_id)).first()
    report = db.query(ReportDB).filter(ReportDB.id == str(report_id)).first()
    if row is None or report is None:
        return None

    trade_date = _parse_trade_date(row.trade_date or report.trade_date)
    task_kind = row.task_kind or _task_kind_for_report(db, report)
    horizons = _horizons_for_task_kind(task_kind)
    max_days = max([0 if h == "t0" else int(h[1:]) for h in horizons], default=0)
    end_date = _advance_cn_trading_days(trade_date, max_days)
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=80)).strftime("%Y-%m-%d")

    try:
        symbol = normalize_exchange_symbol(str(row.symbol or report.symbol)).upper()
        frame = _fetch_kline_frame(symbol, start_date, end_date)
        if frame.empty:
            row.error = "kline_unavailable"
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            return row

        dates = frame["date"].tolist()
        close_by_date = {str(r["date"]): float(r["close"]) for _, r in frame.iterrows()}
        high_by_date = {str(r["date"]): float(r["high"]) for _, r in frame.iterrows()}
        low_by_date = {str(r["date"]): float(r["low"]) for _, r in frame.iterrows()}

        baseline_date = trade_date
        if baseline_date not in close_by_date:
            le = [d for d in dates if d <= trade_date]
            if not le:
                row.error = "baseline_not_found"
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
                return row
            baseline_date = le[-1]

        baseline = _safe_float(row.baseline_price)
        if baseline is None:
            baseline = close_by_date.get(baseline_date)
            row.baseline_price = baseline
            row.baseline_source = "kline_close"
        if baseline is None:
            row.error = "baseline_missing"
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            return row

        idx = dates.index(baseline_date)
        trs: list[float] = []
        for i in range(max(1, idx - 20), idx + 1):
            d = dates[i]
            prev_close = close_by_date.get(dates[i - 1], close_by_date[d])
            high = high_by_date[d]
            low = low_by_date[d]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        atr20 = (sum(trs) / len(trs)) if trs else None
        row.atr20 = atr20
        row.atr_window_end = baseline_date
        threshold = _outcome_threshold(baseline, atr20)
        direction = _direction_label(report)

        outcomes: dict[str, Any] = dict(row.outcomes_json or {})
        now_cn = datetime.now(CN_TZ).date()
        settled = 0
        weighted = 0.0
        weight_sum = 0.0
        weights = _weights_for_task_kind(task_kind)
        next_after: datetime | None = None

        for h in horizons:
            days = 0 if h == "t0" else int(h[1:])
            target_date = _advance_cn_trading_days(baseline_date, days)
            target_close = close_by_date.get(target_date)
            is_due = datetime.strptime(target_date, "%Y-%m-%d").date() <= now_cn
            if target_close is None:
                status: OutcomeStatus = "pending"
                if is_due and next_after is None:
                    next_after = datetime.now(timezone.utc) + timedelta(hours=2)
                elif not is_due:
                    candidate = _to_cn_close_utc(target_date)
                    next_after = candidate if (next_after is None or candidate < next_after) else next_after
                delta = None
                delta_pct = None
                atr_mult = None
                score = 0
            else:
                delta = float(target_close - baseline)
                delta_pct = float((delta / baseline) * 100.0) if baseline else None
                atr_mult = float(delta / atr20) if atr20 else None
                status = _evaluate_direction(direction=direction, delta=delta, threshold=threshold)
                score = _score_for_status(status)
                settled += 1
                w = weights.get(h, 0.0)
                weighted += score * w
                weight_sum += w

            outcomes[h] = {
                "horizon": h,
                "target_date": target_date,
                "close_price": target_close,
                "delta": delta,
                "delta_pct": delta_pct,
                "atr_mult": atr_mult,
                "status": status,
                "score": score,
            }

        for k in list(outcomes.keys()):
            if k not in horizons:
                outcomes.pop(k, None)

        row.outcomes_json = outcomes
        row.weighted_score = (weighted / weight_sum) if weight_sum > 0 else None
        row.settled_count = settled
        row.total_windows = len(horizons)
        ph = _primary_horizon(task_kind)
        row.primary_horizon = ph
        row.primary_status = str((outcomes.get(ph) or {}).get("status") or "pending")
        row.last_evaluated_at = datetime.now(timezone.utc)
        row.next_evaluate_after = next_after
        row.error = None
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:
        row.error = f"{type(exc).__name__}: {exc}"
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        return row


def evaluate_due_outcomes(db: Session, limit: int = 120) -> int:
    if not outcome_enabled():
        return 0
    now = datetime.now(timezone.utc)
    rows = (
        db.query(ReportOutcomeDB)
        .filter(
            ReportOutcomeDB.total_windows > ReportOutcomeDB.settled_count,
            (ReportOutcomeDB.next_evaluate_after.is_(None)) | (ReportOutcomeDB.next_evaluate_after <= now),
        )
        .order_by(ReportOutcomeDB.next_evaluate_after.asc(), ReportOutcomeDB.updated_at.asc())
        .limit(max(1, int(limit)))
        .all()
    )
    done = 0
    for row in rows:
        if evaluate_report_outcome(db, str(row.id)) is not None:
            done += 1
    return done


def get_outcome_for_report(db: Session, report_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    _backfill_outcomes_for_reports(db, user_id=str(user_id), report_ids=[str(report_id)])
    row = (
        db.query(ReportOutcomeDB)
        .filter(ReportOutcomeDB.id == str(report_id), ReportOutcomeDB.user_id == str(user_id))
        .first()
    )
    if not row:
        return None
    return {
        "report_id": str(row.id),
        "task_kind": row.task_kind,
        "release_version": row.release_version,
        "baseline_price": row.baseline_price,
        "baseline_source": row.baseline_source,
        "atr20": row.atr20,
        "atr_window_end": row.atr_window_end,
        "weighted_score": row.weighted_score,
        "settled_count": row.settled_count,
        "total_windows": row.total_windows,
        "primary_horizon": row.primary_horizon,
        "primary_status": row.primary_status,
        "outcomes": dict(row.outcomes_json or {}),
        "last_evaluated_at": row.last_evaluated_at.isoformat() if row.last_evaluated_at else None,
        "next_evaluate_after": row.next_evaluate_after.isoformat() if row.next_evaluate_after else None,
        "error": row.error,
    }


def list_outcome_summaries_by_report_ids(
    db: Session,
    *,
    user_id: str,
    report_ids: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    ids = [str(x).strip() for x in report_ids if str(x).strip()]
    if not ids:
        return {}
    _backfill_outcomes_for_reports(db, user_id=str(user_id), report_ids=ids)
    rows = (
        db.query(ReportOutcomeDB)
        .filter(ReportOutcomeDB.user_id == str(user_id), ReportOutcomeDB.id.in_(ids))
        .all()
    )
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        oj = dict(row.outcomes_json or {}) if isinstance(row.outcomes_json, dict) else {}
        entry: Dict[str, Any] = {
            "weighted_score": row.weighted_score,
            "primary_horizon": row.primary_horizon,
            "primary_status": row.primary_status,
            "settled_count": row.settled_count,
            "total_windows": row.total_windows,
            "release_version": row.release_version,
        }
        for hk in ("t0", "t1", "t2", "t3", "t5"):
            cell = oj.get(hk)
            if isinstance(cell, dict):
                if cell.get("status") is not None:
                    entry[f"{hk}_status"] = str(cell.get("status"))
                if cell.get("close_price") is not None:
                    try:
                        entry[f"{hk}_close"] = float(cell.get("close_price"))
                    except (TypeError, ValueError):
                        pass
                if cell.get("delta_pct") is not None:
                    try:
                        entry[f"{hk}_delta_pct"] = float(cell.get("delta_pct"))
                    except (TypeError, ValueError):
                        pass
                if cell.get("atr_mult") is not None:
                    try:
                        entry[f"{hk}_atr_mult"] = float(cell.get("atr_mult"))
                    except (TypeError, ValueError):
                        pass
                if cell.get("target_date"):
                    entry[f"{hk}_target_date"] = str(cell.get("target_date"))
        if row.baseline_price is not None:
            try:
                entry["baseline_price"] = float(row.baseline_price)
            except (TypeError, ValueError):
                pass
        if row.atr20 is not None:
            try:
                entry["atr20"] = float(row.atr20)
            except (TypeError, ValueError):
                pass
        out[str(row.id)] = entry
    if outcome_enabled():
        pending_lite: Dict[str, Any] = {
            "weighted_score": None,
            "primary_horizon": None,
            "primary_status": "pending",
            "settled_count": 0,
            "total_windows": 0,
            "release_version": None,
            "t0_status": "pending",
            "t1_status": "pending",
            "t2_status": "pending",
            "t3_status": "pending",
            "t5_status": "pending",
        }
        for rid in ids:
            if rid not in out:
                out[rid] = dict(pending_lite)
    return out


def summarize_outcomes(
    db: Session,
    *,
    user_id: str,
    task_kind: Optional[str] = None,
    since_days: Optional[int] = 30,
    group_by: Literal["overall", "version", "week"] = "overall",
) -> Dict[str, Any]:
    if outcome_enabled():
        seed_query = db.query(ReportDB.id).filter(
            ReportDB.user_id == str(user_id),
            ReportDB.status == "completed",
        )
        if since_days and since_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=int(since_days))
            seed_query = seed_query.filter(ReportDB.created_at >= cutoff)
        seed_ids = [str(x[0]) for x in seed_query.order_by(ReportDB.created_at.desc()).limit(200).all()]
        if seed_ids:
            _backfill_outcomes_for_reports(db, user_id=str(user_id), report_ids=seed_ids)

    q = db.query(ReportOutcomeDB).filter(ReportOutcomeDB.user_id == str(user_id))
    if task_kind in ("full_analysis", "fast_analysis"):
        q = q.filter(ReportOutcomeDB.task_kind == task_kind)
    if since_days and since_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(since_days))
        q = q.filter(ReportOutcomeDB.created_at >= cutoff)
    rows = q.order_by(ReportOutcomeDB.created_at.desc()).all()

    def _row_payload(r: ReportOutcomeDB) -> dict[str, Any]:
        return {
            "report_id": str(r.id),
            "task_kind": r.task_kind,
            "release_version": r.release_version or "dev",
            "weighted_score": r.weighted_score,
            "primary_status": r.primary_status or "pending",
            "settled_count": int(r.settled_count or 0),
            "total_windows": int(r.total_windows or 0),
            "trade_date": _parse_trade_date(r.trade_date),
        }

    payloads = [_row_payload(r) for r in rows]

    def _aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        sample = len(items)
        settled = [x for x in items if x["settled_count"] > 0]
        settled_count = len(settled)
        avg_score = (
            sum(float(x["weighted_score"] or 0.0) for x in settled) / settled_count
            if settled_count
            else None
        )
        hit_like = 0.0
        miss = 0
        pending = 0
        for x in items:
            st = x["primary_status"]
            if st == "hit":
                hit_like += 1.0
            elif st == "neutral":
                hit_like += 0.5
            elif st == "miss":
                miss += 1
            else:
                pending += 1
        denom = max(1, sample - pending)
        hit_rate = (hit_like / denom) * 100.0 if sample else None
        return {
            "sample_count": sample,
            "settled_count": settled_count,
            "pending_count": pending,
            "hit_rate": hit_rate,
            "avg_weighted_score": avg_score,
            "miss_count": miss,
        }

    if group_by == "overall":
        return {"group_by": "overall", "summary": _aggregate(payloads), "items": []}
    if group_by == "version":
        by: dict[str, list[dict[str, Any]]] = {}
        for x in payloads:
            by.setdefault(x["release_version"] or "dev", []).append(x)
        items = [{"key": k, **_aggregate(v)} for k, v in sorted(by.items(), key=lambda kv: kv[0])]
        return {"group_by": "version", "summary": _aggregate(payloads), "items": items}

    by_week: dict[str, list[dict[str, Any]]] = {}
    for x in payloads:
        dt = datetime.strptime(x["trade_date"], "%Y-%m-%d")
        iso = dt.isocalendar()
        wk = f"{iso.year}-W{iso.week:02d}"
        by_week.setdefault(wk, []).append(x)
    items = [{"key": k, **_aggregate(v)} for k, v in sorted(by_week.items(), key=lambda kv: kv[0])]
    return {"group_by": "week", "summary": _aggregate(payloads), "items": items}
