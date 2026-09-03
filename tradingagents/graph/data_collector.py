"""DataCollector: fetch all data once, serve windowed views to analyst agents."""
from __future__ import annotations

import io
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from stockstats import wrap

from tradingagents.analytics.financial_health import build_financial_health_score
from tradingagents.analytics.intraday_features import (
    intraday_position_in_range,
    intraday_vwap_deviation,
    orderbook_imbalance,
    relative_strength_vs_index,
    summarize_intraday_features,
)
from tradingagents.analytics.moneyflow_features import build_moneyflow_structure
from tradingagents.analytics.orderbook_proxy import (
    build_active_buy_proxy,
    build_orderbook_pressure_signal,
)
from tradingagents.dataflows.data_source_catalog import enrich_data_source_item
from tradingagents.dataflows.interface import route_to_vendor_with_meta
from tradingagents.dataflows.trade_calendar import cn_market_phase, cn_today_str

try:
    from api.services.cache_service import get_tiered_cache
except Exception:  # pragma: no cover
    get_tiered_cache = None

INDICATORS = [
    "close_50_sma", "close_200_sma", "close_10_ema",
    "rsi", "macd", "boll", "boll_ub", "boll_lb", "atr", "vwma",
]
SHORT_DAYS = 14
LONG_DAYS = 90

# 单条数据源写入报告的预览长度上限（避免 JSON 过大）
_DATA_SOURCE_PREVIEW_MAX_CHARS = 14_000


def _detail_preview_for_data_source(value: Any, *, max_chars: int = _DATA_SOURCE_PREVIEW_MAX_CHARS) -> str | None:
    """将采集结果格式化为可读文本，供前端「数据源详情」折叠展示。"""
    if value is None:
        return None
    text: str
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            text = str(value)
    else:
        text = str(value)
    stripped = text.strip()
    if not stripped:
        return None
    if len(stripped) > max_chars:
        return stripped[:max_chars] + "\n\n…（已截断，完整数据已参与本次分析）"
    return stripped

_OHLCV_COLS = ["date", "open", "high", "low", "close", "volume"]


def _parse_csv_to_dataframe(raw_csv: str) -> Optional[pd.DataFrame]:
    """Parse raw CSV string into a normalized OHLCV DataFrame.

    Returns None if parsing fails or the CSV is too short/empty.
    """
    if not isinstance(raw_csv, str) or len(raw_csv) <= 50:
        return None
    try:
        df = pd.read_csv(io.StringIO(raw_csv), on_bad_lines='skip', comment='#')
    except Exception:
        return None
    if df.empty:
        return None
    cols_map = {c.lower(): c for c in df.columns}
    rename_dict = {}
    for target in _OHLCV_COLS:
        if target in cols_map:
            rename_dict[cols_map[target]] = target
    df = df.rename(columns=rename_dict)
    return df


def _intraday_poll_seconds() -> int:
    raw = (os.getenv("TA_INTRADAY_RT_POLL_SEC") or "20").strip()
    try:
        sec = int(raw)
    except (TypeError, ValueError):
        sec = 20
    return max(5, min(300, sec))


def _suggest_intraday_poll_sec(trade_date: str) -> Optional[int]:
    if trade_date != cn_today_str():
        return None
    if cn_market_phase() in ("in_session", "lunch_break"):
        return _intraday_poll_seconds()
    return None


def _feature_on(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _parse_opening_auction_metrics(raw: Any) -> dict[str, float | None]:
    text = str(raw or "")
    metrics: dict[str, float | None] = {
        "price": None,
        "gap_pct": None,
        "amount": None,
        "vol": None,
        "turnover_rate": None,
        "volume_ratio": None,
    }
    if not text.strip():
        return metrics

    patterns = {
        "price": r"竞价均价:\s*([+-]?\d+(?:\.\d+)?)",
        "gap_pct": r"较昨收涨跌:\s*([+-]?\d+(?:\.\d+)?)%",
        "amount": r"竞价成交额:\s*([+-]?\d[\d,]*(?:\.\d+)?)\s*元",
        "vol": r"竞价成交量:\s*([+-]?\d[\d,]*(?:\.\d+)?)\s*股",
        "turnover_rate": r"竞价换手率:\s*([+-]?\d+(?:\.\d+)?)%",
        "volume_ratio": r"竞价量比:\s*([+-]?\d+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if not m:
            continue
        raw_num = m.group(1).replace(",", "")
        try:
            metrics[key] = float(raw_num)
        except Exception:
            metrics[key] = None
    return metrics


def _build_opening_auction_signal(raw: Any) -> str:
    metrics = _parse_opening_auction_metrics(raw)
    if not any(v is not None for v in metrics.values()):
        return "## 开盘集合竞价信号\n\n无可用竞价特征（可能未命中交易时段或数据源未返回）。"

    score = 0
    reasons: list[str] = []
    tags: list[str] = []

    gap_pct = metrics["gap_pct"]
    amount = metrics["amount"]
    turnover_rate = metrics["turnover_rate"]
    volume_ratio = metrics["volume_ratio"]

    if gap_pct is not None:
        if gap_pct >= 2.5:
            score += 2
            reasons.append("高开幅度偏强")
        elif gap_pct >= 1.0:
            score += 1
            reasons.append("小幅高开")
        elif gap_pct <= -2.5:
            score -= 2
            reasons.append("低开幅度偏弱")
        elif gap_pct <= -1.0:
            score -= 1
            reasons.append("小幅低开")

    if amount is not None:
        if amount >= 100_000_000:
            score += 2
            reasons.append("竞价成交额显著放大")
        elif amount >= 30_000_000:
            score += 1
            reasons.append("竞价成交额中等偏强")
        elif amount < 5_000_000:
            score -= 1
            reasons.append("竞价成交额偏低")

    if volume_ratio is not None:
        if volume_ratio >= 2.0:
            score += 2
            reasons.append("竞价量比明显放大")
        elif volume_ratio >= 1.2:
            score += 1
            reasons.append("竞价量比偏强")
        elif volume_ratio < 0.6:
            score -= 1
            reasons.append("竞价量比偏弱")

    if turnover_rate is not None:
        if turnover_rate >= 0.8:
            score += 2
            reasons.append("竞价换手活跃")
        elif turnover_rate >= 0.2:
            score += 1
            reasons.append("竞价换手尚可")
        elif turnover_rate < 0.05:
            score -= 1
            reasons.append("竞价换手偏低")

    if gap_pct is not None and volume_ratio is not None:
        if gap_pct >= 4.0 and volume_ratio < 1.0:
            tags.append("高开缩量-冲高回落风险")
            score -= 1
        if gap_pct <= -3.0 and volume_ratio >= 1.5:
            tags.append("低开放量-情绪承压")
            score -= 1

    if score >= 5:
        grade = "强势竞价"
        action = "可优先观察开盘后 5-15 分钟是否延续放量上攻，回踩不破开盘价可考虑试仓。"
    elif score >= 2:
        grade = "中性偏强"
        action = "等待首 15 分钟方向确认；若量价同向可轻仓跟随。"
    elif score >= -1:
        grade = "中性"
        action = "不抢开盘，等待分时二次确认后再决策。"
    elif score >= -4:
        grade = "偏弱竞价"
        action = "以防守为主，若反弹无量宜减少追涨行为。"
    else:
        grade = "弱势/高风险"
        action = "优先回避；仅在出现显著资金反转信号时再观察。"

    reason_text = "；".join(reasons) if reasons else "特征不完整"
    tag_text = "、".join(tags) if tags else "无"

    return (
        "## 开盘集合竞价信号\n\n"
        f"- 评分: {score}\n"
        f"- 等级: {grade}\n"
        f"- 特征结论: {reason_text}\n"
        f"- 风险标签: {tag_text}\n"
        f"- 快速建议: {action}"
    )


def _coerce_auction_df(raw: Any) -> pd.DataFrame:
    if isinstance(raw, pd.DataFrame):
        return raw
    if isinstance(raw, list):
        return pd.DataFrame(raw)
    return pd.DataFrame()


def _build_auction_intraday_strength(raw_o: Any, raw_c: Any, fallback_text: str) -> tuple[dict[str, Any], str]:
    df_o = _coerce_auction_df(raw_o)
    df_c = _coerce_auction_df(raw_c)
    if df_o.empty and df_c.empty:
        return (
            {"method": "auction_intraday_strength_v1", "error": "insufficient_data", "confidence": "low"},
            fallback_text,
        )

    def _latest(df: pd.DataFrame, col: str) -> float | None:
        if df.empty or col not in df.columns:
            return None
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            return None
        return float(series.iloc[-1])

    vol_o = _latest(df_o, "vol") or _latest(df_o, "volume")
    vol_c = _latest(df_c, "vol") or _latest(df_c, "volume")
    price_o = _latest(df_o, "price")
    price_c = _latest(df_c, "price")
    amount_o = _latest(df_o, "amount")
    amount_c = _latest(df_c, "amount")

    vol_growth = ((vol_c - vol_o) / vol_o) if (vol_o and vol_c is not None) else None
    price_move = ((price_c - price_o) / price_o) if (price_o and price_c is not None) else None
    amount_growth = ((amount_c - amount_o) / amount_o) if (amount_o and amount_c is not None) else None
    tone = "抢筹偏强" if (vol_growth or 0) > 0.5 and (price_move or 0) > 0 else "竞价中性"
    summary = (
        f"竞价量变化 {(vol_growth or 0) * 100:+.1f}%，价格变化 {(price_move or 0) * 100:+.2f}%，"
        f"委托金额变化 {(amount_growth or 0) * 100:+.1f}%，整体{tone}。"
    )
    return (
        {
            "method": "auction_intraday_strength_v1",
            "vol_growth_pct": vol_growth,
            "price_move_pct": price_move,
            "amount_growth_pct": amount_growth,
            "tone": tone,
            "confidence": "medium" if vol_growth is not None else "low",
        },
        summary,
    )


# ── VPA (Volume Price Analysis) 预计算 ──────────────────────────


def _compute_vpa_indicators(df: pd.DataFrame, window: int = 20) -> str:
    """Pre-compute Volume Price Analysis indicators from OHLCV DataFrame.

    Returns a human-readable text block for the VPA analyst agent.
    All numerical comparisons are done here so the LLM only needs to
    interpret the results, not do arithmetic.
    """
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        return "VPA 数据不足：缺少 OHLCV 列"

    df = df.copy()
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["open"] = pd.to_numeric(df["open"], errors="coerce")
    df["high"] = pd.to_numeric(df["high"], errors="coerce")
    df["low"] = pd.to_numeric(df["low"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])

    if len(df) < window + 5:
        return "VPA 数据不足：历史 K 线数量不够"

    # ── 派生指标 ──
    df["vol_ma"] = df["volume"].rolling(window).mean()
    df["volume_ratio"] = df["volume"] / df["vol_ma"]

    hl_range = df["high"] - df["low"]
    df["bar_spread"] = hl_range / df["close"]  # 实体相对大小
    df["close_position"] = np.where(
        hl_range > 0,
        (df["close"] - df["low"]) / hl_range,
        0.5,
    )
    df["bar_type"] = np.where(
        df["close"] > df["open"], "阳线",
        np.where(df["close"] < df["open"], "阴线", "十字星"),
    )

    # 上下影线比例
    df["upper_shadow"] = np.where(
        hl_range > 0,
        (df["high"] - np.maximum(df["open"], df["close"])) / hl_range,
        0.0,
    )
    df["lower_shadow"] = np.where(
        hl_range > 0,
        (np.minimum(df["open"], df["close"]) - df["low"]) / hl_range,
        0.0,
    )

    # 价格变化率
    df["pct_change"] = df["close"].pct_change()

    # 量能趋势 (5日均量 vs 20日均量)
    df["vol_ma5"] = df["volume"].rolling(5).mean()
    df["vol_trend_ratio"] = df["vol_ma5"] / df["vol_ma"]

    # 量价一致性
    df["vp_harmony"] = np.where(
        (df["pct_change"] > 0) & (df["volume_ratio"] > 1.0), "一致(涨+放量)",
        np.where(
            (df["pct_change"] < 0) & (df["volume_ratio"] > 1.0), "一致(跌+放量)",
            np.where(
                (df["pct_change"] > 0) & (df["volume_ratio"] < 0.8), "背离(涨+缩量)",
                np.where(
                    (df["pct_change"] < 0) & (df["volume_ratio"] < 0.8), "背离(跌+缩量)",
                    "中性",
                ),
            ),
        ),
    )

    # OBV (On Balance Volume) 简易趋势 — vectorized
    close_diff = df["close"].diff()
    obv_sign = np.where(close_diff > 0, 1, np.where(close_diff < 0, -1, 0))
    obv_sign[0] = 0
    df["obv"] = (obv_sign * df["volume"].values).cumsum()
    obv_ma = df["obv"].rolling(10).mean()
    obv_trend = "上升" if len(obv_ma.dropna()) >= 2 and obv_ma.iloc[-1] > obv_ma.iloc[-5] else "下降"

    # ── 格式化输出（取最近 N 天）──
    output_days = min(30, len(df) - window)
    recent = df.tail(output_days).copy()

    lines = []
    lines.append(f"## VPA 预计算指标（基于 {window} 日均量基准）\n")
    lines.append(f"**OBV 趋势（10日）**: {obv_trend}")

    # 量能概况
    last = recent.iloc[-1]
    vol_5d = recent["volume"].tail(5).mean()
    vol_20d = last["vol_ma"] if pd.notna(last["vol_ma"]) else 0
    vol_summary = "放量" if vol_5d > vol_20d * 1.2 else ("缩量" if vol_5d < vol_20d * 0.8 else "平稳")
    lines.append(f"**近5日量能趋势**: {vol_summary}（5日均量/20日均量 = {last.get('vol_trend_ratio', 0):.2f}）\n")

    lines.append("### 逐日量价数据\n")
    lines.append("| 日期 | 类型 | 涨跌幅 | 实体大小 | 收盘位置 | 上影线 | 下影线 | 量比 | 量价关系 |")
    lines.append("|------|------|--------|----------|----------|--------|--------|------|----------|")

    for _, row in recent.iterrows():
        dt = row.get("date", "")
        if hasattr(dt, "strftime"):
            dt = dt.strftime("%m-%d")
        else:
            dt = str(dt)[-5:]

        pct = row["pct_change"] * 100 if pd.notna(row["pct_change"]) else 0
        spread_label = "宽" if row["bar_spread"] > 0.03 else ("窄" if row["bar_spread"] < 0.015 else "中")
        cp = row["close_position"]
        cp_label = "高位" if cp > 0.7 else ("低位" if cp < 0.3 else "中位")
        vr = row["volume_ratio"] if pd.notna(row["volume_ratio"]) else 0
        vr_label = f"{vr:.1f}"
        if vr > 2.0:
            vr_label += "(巨量)"
        elif vr > 1.5:
            vr_label += "(明显放量)"
        elif vr > 1.0:
            vr_label += "(温和放量)"
        elif vr < 0.5:
            vr_label += "(极度缩量)"
        elif vr < 0.8:
            vr_label += "(缩量)"

        lines.append(
            f"| {dt} | {row['bar_type']} | {pct:+.1f}% | {spread_label}({row['bar_spread']:.3f}) "
            f"| {cp_label}({cp:.2f}) | {row['upper_shadow']:.2f} | {row['lower_shadow']:.2f} "
            f"| {vr_label} | {row['vp_harmony']} |"
        )

    # ── 关键模式识别 ──
    lines.append("\n### 关键量价模式识别\n")

    # 量价背离检测（近5天）
    last5 = recent.tail(5)
    price_up = (last5["close"].iloc[-1] > last5["close"].iloc[0])
    vol_down = (last5["volume"].iloc[-1] < last5["volume"].iloc[0])
    price_down = (last5["close"].iloc[-1] < last5["close"].iloc[0])
    vol_up = (last5["volume"].iloc[-1] > last5["volume"].iloc[0])

    if price_up and vol_down:
        lines.append("- **⚠ 顶部背离信号**: 近5日价格上涨但成交量递减，上涨动能可能衰竭")
    if price_down and vol_up:
        lines.append("- **⚠ 底部放量信号**: 近5日价格下跌但成交量递增，可能是恐慌抛售或换手")
    if price_down and vol_down:
        lines.append("- **卖压衰竭信号**: 近5日价格下跌且成交量递减，空方力量可能枯竭")
    if price_up and vol_up:
        lines.append("- **健康上涨信号**: 近5日价格上涨且成交量配合递增")

    # Selling climax 检测
    for i in range(-3, 0):
        if i < -len(recent):
            continue
        row = recent.iloc[i]
        if (row.get("volume_ratio", 0) > 2.0
                and row.get("pct_change", 0) < -0.03
                and row.get("close_position", 0.5) > 0.5):
            lines.append(f"- **卖出高潮(Selling Climax)**: {str(row.get('date', ''))[-5:]} 急跌巨量但收盘收回过半，可能是恐慌见底")

    # 高位放量滞涨
    for i in range(-3, 0):
        if i < -len(recent):
            continue
        row = recent.iloc[i]
        if (row.get("volume_ratio", 0) > 1.8
                and abs(row.get("pct_change", 0)) < 0.01
                and row.get("bar_spread", 0) < 0.015):
            lines.append(f"- **放量滞涨**: {str(row.get('date', ''))[-5:]} 巨量但价格几乎不动（窄实体），多空分歧大")

    if not any("**" in l for l in lines[-5:]):
        lines.append("- 近期无显著量价异常模式")

    return "\n".join(lines)


def make_cache_key(ticker: str, trade_date: str) -> str:
    return f"{ticker}_{trade_date}"


TASK_TO_METHOD = {
    "stock_data": "get_stock_data",
    "news": "get_news",
    "global_news": "get_global_news",
    "fund_flow_board": "get_board_fund_flow",
    "fund_flow_individual": "get_individual_fund_flow",
    "lhb": "get_lhb_detail",
    "insider_transactions": "get_insider_transactions",
    "zt_pool": "get_zt_pool",
    "hot_stocks": "get_hot_stocks_xq",
    "fundamentals": "get_fundamentals",
    "balance_sheet": "get_balance_sheet",
    "cashflow": "get_cashflow",
    "income_statement": "get_income_statement",
    "daily_basic_window": "get_daily_basic",
    "individual_money_flow_detail": "get_individual_money_flow_detail",
    "margin_detail_window": "get_margin_detail",
    "hsgt_top10_window": "get_hsgt_top10",
    "opening_auction": "get_opening_auction",
    "opening_auction_o": "fetch_opening_auction_o_df",
    "opening_auction_c": "fetch_opening_auction_c_df",
    "top_list_history": "get_top_list_history",
    "stk_factor_pro_window": "get_stk_factor_pro_window",
    "cyq_perf_window": "get_cyq_perf",
    "cyq_chips_recent": "get_cyq_chips",
    "l2_orderqueue_recent": "get_l2_orderqueue_window",
    "fina_indicator": "get_fina_indicator",
    "forecast": "get_forecast",
    "express": "get_express",
    "holdernumber_series": "get_holdernumber_series",
    "individual_moneyflow_df_window": "fetch_individual_moneyflow_df",
    "top_list_df_window": "fetch_top_list_df",
    "fina_indicator_df": "fetch_fina_indicator_df",
    "stk_mins_intraday": "fetch_stk_mins",
}


def _utc_isoz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append_tier3_snapshot_items(source_items: list[dict[str, Any]], ticker: str, trade_date: str) -> None:
    del trade_date
    macro_on = os.getenv("TA_MACRO_SYNC_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
    if not macro_on:
        return

    try:
        from api.database import (
            MarketDataDisclosureDB,
            MarketDataMacroIndicatorDB,
            get_marketdata_db_ctx,
            is_marketdata_db_healthy,
        )
    except Exception:
        return

    try:
        if not is_marketdata_db_healthy():
            return
        with get_marketdata_db_ctx() as db:
            disclosure = (
                db.query(MarketDataDisclosureDB)
                .filter(MarketDataDisclosureDB.symbol == ticker)
                .order_by(MarketDataDisclosureDB.ann_time.desc())
                .first()
            )
            if disclosure is not None:
                fetched_at = (
                    disclosure.ann_time.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    if disclosure.ann_time
                    else _utc_isoz()
                )
                source_items.append(
                    enrich_data_source_item(
                        "disclosure_snapshot",
                        {
                            "method": "query_disclosure",
                            "vendor": disclosure.source_primary or "juchao",
                            "status": "hit",
                            "fetched_at": fetched_at,
                            "latency_ms": None,
                            "fallback_chain": [disclosure.source_primary or "juchao"],
                            "error": None,
                        },
                    )
                )

            macro_cn = (
                db.query(MarketDataMacroIndicatorDB)
                .filter(MarketDataMacroIndicatorDB.source_primary.in_(["stats_cn", "akshare"]))
                .order_by(MarketDataMacroIndicatorDB.updated_at.desc())
                .first()
            )
            if macro_cn is not None:
                source_items.append(
                    enrich_data_source_item(
                        "macro_cn_snapshot",
                        {
                            "method": "query_macro_series",
                            "vendor": "stats_cn",
                            "status": "hit",
                            "fetched_at": _utc_isoz(),
                            "latency_ms": None,
                            "fallback_chain": ["stats_cn"],
                            "error": None,
                        },
                    )
                )

            macro_us = (
                db.query(MarketDataMacroIndicatorDB)
                .filter(MarketDataMacroIndicatorDB.source_primary == "fred")
                .order_by(MarketDataMacroIndicatorDB.updated_at.desc())
                .first()
            )
            if macro_us is not None:
                source_items.append(
                    enrich_data_source_item(
                        "macro_us_snapshot",
                        {
                            "method": "query_macro_series",
                            "vendor": "fred",
                            "status": "hit",
                            "fetched_at": _utc_isoz(),
                            "latency_ms": None,
                            "fallback_chain": ["fred"],
                            "error": None,
                        },
                    )
                )
    except Exception:
        # Snapshot enrichment must not break analysis.
        return


def _safe_route(key: str, method: str, payload: dict) -> tuple[str, Any, dict]:
    start_t = time.time()
    try:
        res, meta = route_to_vendor_with_meta(method, **payload)
        duration = time.time() - start_t
        if duration > 0.5:
            print(f"  [Timer] {method} took {duration:.2f}s")
        if meta.get("fetched_at"):
            meta["fetched_at"] = str(meta["fetched_at"]).replace("+00:00", "Z")
        return key, res, meta
    except Exception as exc:
        meta = {
            "method": method,
            "vendor": None,
            "status": "error",
            "latency_ms": int((time.time() - start_t) * 1000),
            "fetched_at": _utc_isoz(),
            "fallback_chain": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
        return key, f"{method} 调用失败：{type(exc).__name__}: {exc}", meta


def _fetch_all(ticker: str, trade_date: str) -> Dict[str, Any]:
    """Fetch all data sources in parallel.

    Always fetches full data including financial statements, regardless of horizon.
    The horizon only affects the analysis window, not data collection.
    """
    lookback = LONG_DAYS
    end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    # 为了计算指标准确（如 200 SMA），需要比分析窗口更长的历史数据
    fetch_lookback = 365
    start_str = (end_dt - timedelta(days=fetch_lookback)).strftime("%Y-%m-%d")

    tasks: Dict[str, dict] = {
        "stock_data": {"symbol": ticker, "start_date": start_str, "end_date": trade_date},
        "news": {"ticker": ticker, "start_date": (end_dt - timedelta(days=lookback)).strftime("%Y-%m-%d"), "end_date": trade_date},
        "global_news": {"curr_date": trade_date, "look_back_days": lookback, "limit": 30},
        "fund_flow_board": {},
        "fund_flow_individual": {"symbol": ticker},
        "lhb": {"symbol": ticker, "date": trade_date},
        # get_insider_transactions provider contract uses symbol (not ticker).
        "insider_transactions": {"symbol": ticker},
        "zt_pool": {"date": trade_date},
        "hot_stocks": {},
        "fundamentals": {"ticker": ticker, "curr_date": trade_date},
        "balance_sheet": {"ticker": ticker, "freq": "quarterly", "curr_date": trade_date},
        "cashflow": {"ticker": ticker, "freq": "quarterly", "curr_date": trade_date},
        "income_statement": {"ticker": ticker, "freq": "quarterly", "curr_date": trade_date},
        "daily_basic_window": {"symbol": ticker, "start_date": start_str, "end_date": trade_date},
        "individual_money_flow_detail": {"symbol": ticker, "start_date": (end_dt - timedelta(days=60)).strftime("%Y-%m-%d"), "end_date": trade_date},
        "margin_detail_window": {"symbol": ticker, "start_date": (end_dt - timedelta(days=60)).strftime("%Y-%m-%d"), "end_date": trade_date},
        "hsgt_top10_window": {"symbol": ticker, "start_date": (end_dt - timedelta(days=60)).strftime("%Y-%m-%d"), "end_date": trade_date},
        "opening_auction": {"symbol": ticker, "date": trade_date},
        "opening_auction_o": {"symbol": ticker, "trade_date": trade_date},
        "opening_auction_c": {"symbol": ticker, "trade_date": trade_date},
        "top_list_history": {"symbol": ticker, "start_date": (end_dt - timedelta(days=180)).strftime("%Y-%m-%d"), "end_date": trade_date},
        "stk_factor_pro_window": {"symbol": ticker, "start_date": (end_dt - timedelta(days=60)).strftime("%Y-%m-%d"), "end_date": trade_date},
        "cyq_perf_window": {"symbol": ticker, "start_date": (end_dt - timedelta(days=60)).strftime("%Y-%m-%d"), "end_date": trade_date},
        "cyq_chips_recent": {"symbol": ticker, "date": trade_date},
        "l2_orderqueue_recent": {"symbol": ticker, "date": trade_date},
        "fina_indicator": {"ticker": ticker, "curr_date": trade_date},
        "forecast": {"ticker": ticker, "curr_date": trade_date},
        "express": {"ticker": ticker, "curr_date": trade_date},
        "holdernumber_series": {"ticker": ticker, "curr_date": trade_date},
        "individual_moneyflow_df_window": {
            "symbol": ticker,
            "start_date": (end_dt - timedelta(days=10)).strftime("%Y-%m-%d"),
            "end_date": trade_date,
        },
        "top_list_df_window": {
            "symbol": ticker,
            "start_date": (end_dt - timedelta(days=30)).strftime("%Y-%m-%d"),
            "end_date": trade_date,
        },
        "fina_indicator_df": {"symbol": ticker, "end_date": trade_date},
        "stk_mins_intraday": {
            "ts_code": ticker,
            "freq": "1min",
            "start": trade_date,
            "end": trade_date,
        },
    }
    if not _feature_on("TA_TUSHARE_AUCTION_OC_ENABLED", "0"):
        tasks.pop("opening_auction_o", None)
        tasks.pop("opening_auction_c", None)
    priority = {
        "stock_data": 0,
        "daily_basic_window": 0,
        "opening_auction": 0,
        "news": 1,
        "global_news": 1,
        "fundamentals": 2,
        "balance_sheet": 2,
        "cashflow": 2,
        "income_statement": 2,
    }
    ordered_task_items = sorted(tasks.items(), key=lambda kv: (priority.get(kv[0], 3), kv[0]))

    results: Dict[str, Any] = {}
    source_items: list[dict[str, Any]] = []
    fetch_start = time.time()
    with ThreadPoolExecutor(max_workers=min(5, len(tasks))) as executor:
        future_to_key = {
            executor.submit(_safe_route, key, TASK_TO_METHOD[key], payload): key
            for key, payload in ordered_task_items
        }
        for future in future_to_key:
            key, value, meta = future.result()
            results[key] = value
            meta_out = dict(meta)
            meta_out["detail_preview"] = _detail_preview_for_data_source(value)
            source_items.append(enrich_data_source_item(key, meta_out))

    # ── Parse CSV once, reuse for indicators and VPA ──────────────────
    raw_csv = results.get("stock_data", "")
    df = _parse_csv_to_dataframe(raw_csv)

    # ── 核心加速：本地计算所有技术指标 ──────────────────
    indicators_res = {}
    try:
        if df is not None and "close" in df.columns:
            ss = wrap(df.copy())

            calc_map = {
                "close_50_sma": "close_50_sma",
                "close_200_sma": "close_200_sma",
                "close_10_ema": "close_10_ema",
                "rsi": "rsi_14",
                "macd": "macd",
                "boll": "close_20_sma",
                "boll_ub": "boll_ub",
                "boll_lb": "boll_lb",
                "atr": "atr",
                "vwma": "vwma"
            }

            for key, ss_key in calc_map.items():
                try:
                    val = ss[ss_key].iloc[-1]
                    indicators_res[key] = round(float(val), 2) if isinstance(val, (int, float)) else str(val)
                except Exception:
                    indicators_res[key] = "N/A"
        else:
            print(f"  [Warning] No valid stock_data for indicator calculation.")
    except Exception as e:
        print(f"  [Error] Local indicator calculation failed: {e}")

    for ind in INDICATORS:
        if ind not in indicators_res:
            indicators_res[ind] = "无数据"

    results["indicators"] = indicators_res
    source_items.append(
        enrich_data_source_item(
            "indicators",
            {
                "method": "internal_indicators",
                "vendor": "internal",
                "status": "internal",
                "fetched_at": _utc_isoz(),
                "latency_ms": None,
                "fallback_chain": [],
                "error": None,
                "detail_preview": _detail_preview_for_data_source(indicators_res),
            },
        )
    )

    # ── VPA 预计算指标 ──────────────────────────────
    try:
        if df is not None:
            results["vpa_indicators"] = _compute_vpa_indicators(df.copy())
        else:
            results["vpa_indicators"] = "VPA 数据不足"
    except Exception as e:
        results["vpa_indicators"] = f"VPA 计算失败：{e}"

    source_items.append(
        enrich_data_source_item(
            "vpa_indicators",
            {
                "method": "internal_vpa",
                "vendor": "internal",
                "status": "internal",
                "fetched_at": _utc_isoz(),
                "latency_ms": None,
                "fallback_chain": [],
                "error": None,
                "detail_preview": _detail_preview_for_data_source(results.get("vpa_indicators")),
            },
        )
    )

    auction_raw = results.get("opening_auction")
    results["opening_auction_signal"] = _build_opening_auction_signal(auction_raw)
    source_items.append(
        enrich_data_source_item(
            "opening_auction_signal",
            {
                "method": "internal_opening_auction_signal",
                "vendor": "internal",
                "status": "internal",
                "fetched_at": _utc_isoz(),
                "latency_ms": None,
                "fallback_chain": [],
                "error": None,
                "detail_preview": _detail_preview_for_data_source(results.get("opening_auction_signal")),
            },
        )
    )
    auction_strength_dict, auction_strength_text = _build_auction_intraday_strength(
        results.get("opening_auction_o"),
        results.get("opening_auction_c"),
        results.get("opening_auction_signal", ""),
    )
    results["auction_intraday_strength"] = auction_strength_text

    # 派生信号池：供报告 result_data.derived_signals 与 audit_provenance 使用
    derived_signals: dict[str, Any] = {}
    if _feature_on("TA_TRANSLATOR_ENABLED", "0"):
        close_px = None
        high_px = None
        low_px = None
        symbol_pct = None
        if df is not None and not df.empty:
            close_series = pd.to_numeric(df.get("close"), errors="coerce").dropna() if "close" in df.columns else pd.Series(dtype=float)
            high_series = pd.to_numeric(df.get("high"), errors="coerce").dropna() if "high" in df.columns else pd.Series(dtype=float)
            low_series = pd.to_numeric(df.get("low"), errors="coerce").dropna() if "low" in df.columns else pd.Series(dtype=float)
            if not close_series.empty:
                close_px = float(close_series.iloc[-1])
                if len(close_series) >= 2 and close_series.iloc[-2] != 0:
                    symbol_pct = (float(close_series.iloc[-1]) - float(close_series.iloc[-2])) / float(close_series.iloc[-2])
            if not high_series.empty:
                high_px = float(high_series.iloc[-1])
            if not low_series.empty:
                low_px = float(low_series.iloc[-1])

        mins_df = _coerce_auction_df(results.get("stk_mins_intraday"))
        intraday_feats = {
            "intraday_vwap_dev": intraday_vwap_deviation(mins_df, close_px),
            "intraday_pos_in_range": intraday_position_in_range(high_px, low_px, close_px),
            "relative_strength_vs_index": relative_strength_vs_index(symbol_pct, None),
            "bid_ask_imbalance": None,
        }
        # 优先尝试 rt_k 快照；拿不到则用五档盘口兜底
        orderbook_row: dict[str, Any] = {}
        try:
            from api.services import rt_quote_service

            rt_quotes, _missing, _ttl = rt_quote_service.get_rt_daily_bulk([ticker])
            orderbook_row = dict(rt_quotes.get(ticker) or {})
        except Exception:
            orderbook_row = {}
        if not orderbook_row:
            try:
                from api.services import market_advanced_service

                ob = market_advanced_service.fetch_orderbook(ticker)
                levels = list(ob.get("levels") or [])
                for item in levels:
                    name = str(item.get("item") or "")
                    value = float(item.get("value")) if item.get("value") is not None else None
                    if value is None:
                        continue
                    if name.startswith("卖") and "价" in name:
                        idx = "".join(ch for ch in name if ch.isdigit()) or "1"
                        orderbook_row[f"ask_price{idx}"] = value
                    if name.startswith("卖") and ("量" in name or "手" in name):
                        idx = "".join(ch for ch in name if ch.isdigit()) or "1"
                        orderbook_row[f"ask_volume{idx}"] = value
                    if name.startswith("买") and "价" in name:
                        idx = "".join(ch for ch in name if ch.isdigit()) or "1"
                        orderbook_row[f"bid_price{idx}"] = value
                    if name.startswith("买") and ("量" in name or "手" in name):
                        idx = "".join(ch for ch in name if ch.isdigit()) or "1"
                        orderbook_row[f"bid_volume{idx}"] = value
            except Exception:
                orderbook_row = {}

        intraday_feats["bid_ask_imbalance"] = orderbook_imbalance(orderbook_row, level_count=5)
        results["intraday_features"] = {
            **intraday_feats,
            "summary": summarize_intraday_features(intraday_feats),
        }

        if _feature_on("TA_TRANSLATOR_ORDERBOOK_ENABLED", "1"):
            ob_dict, ob_text = build_orderbook_pressure_signal(orderbook_row, level_count=5)
            derived_signals["orderbook_pressure_signal_v1"] = ob_dict
            results["orderbook_pressure_signal"] = ob_text
            source_items.append(
                enrich_data_source_item(
                    "orderbook_pressure_signal",
                    {
                        "method": "orderbook_pressure_signal_v1",
                        "vendor": "internal",
                        "status": "internal",
                        "fetched_at": _utc_isoz(),
                        "latency_ms": None,
                        "fallback_chain": [],
                        "error": None,
                        "detail_preview": _detail_preview_for_data_source(ob_text),
                    },
                )
            )

        if _feature_on("TA_TRANSLATOR_ACTIVE_BUY_ENABLED", "1"):
            ab_dict, ab_text = build_active_buy_proxy(results.get("individual_moneyflow_df_window"))
            derived_signals["active_buy_proxy_v1"] = ab_dict
            results["active_buy_proxy"] = ab_text
            source_items.append(
                enrich_data_source_item(
                    "active_buy_proxy",
                    {
                        "method": "active_buy_proxy_v1",
                        "vendor": "internal",
                        "status": "internal",
                        "fetched_at": _utc_isoz(),
                        "latency_ms": None,
                        "fallback_chain": [],
                        "error": None,
                        "detail_preview": _detail_preview_for_data_source(ab_text),
                    },
                )
            )

        if _feature_on("TA_TRANSLATOR_MONEYFLOW_ENABLED", "1"):
            mf_dict, mf_text = build_moneyflow_structure(
                results.get("individual_moneyflow_df_window"),
                results.get("fund_flow_board"),
                results.get("top_list_df_window"),
            )
            derived_signals["moneyflow_structure_v1"] = mf_dict
            results["moneyflow_structure"] = mf_text
            source_items.append(
                enrich_data_source_item(
                    "moneyflow_structure",
                    {
                        "method": "moneyflow_structure_v1",
                        "vendor": "internal",
                        "status": "internal",
                        "fetched_at": _utc_isoz(),
                        "latency_ms": None,
                        "fallback_chain": [],
                        "error": None,
                        "detail_preview": _detail_preview_for_data_source(mf_text),
                    },
                )
            )

        if _feature_on("TA_TRANSLATOR_FINANCIAL_ENABLED", "1"):
            fundamentals_df = results.get("fundamentals")
            industry_code = None
            if isinstance(fundamentals_df, pd.DataFrame) and not fundamentals_df.empty:
                for col in ("industry", "industry_code", "sw_l1"):
                    if col in fundamentals_df.columns:
                        industry_code = str(fundamentals_df.iloc[0].get(col) or "").strip() or None
                        if industry_code:
                            break
            fh_dict, fh_text = build_financial_health_score(
                results.get("fina_indicator_df"),
                results.get("income_statement"),
                results.get("cashflow"),
                results.get("balance_sheet"),
                results.get("daily_basic_window"),
                industry_code=industry_code,
            )
            derived_signals["financial_health_v1"] = fh_dict
            results["financial_health"] = fh_text
            source_items.append(
                enrich_data_source_item(
                    "financial_health",
                    {
                        "method": "financial_health_v1",
                        "vendor": "internal",
                        "status": "internal",
                        "fetched_at": _utc_isoz(),
                        "latency_ms": None,
                        "fallback_chain": [],
                        "error": None,
                        "detail_preview": _detail_preview_for_data_source(fh_text),
                    },
                )
            )

        if _feature_on("TA_TUSHARE_AUCTION_OC_ENABLED", "0"):
            derived_signals["auction_intraday_strength_v1"] = auction_strength_dict
            source_items.append(
                enrich_data_source_item(
                    "auction_intraday_strength",
                    {
                        "method": "auction_intraday_strength_v1",
                        "vendor": "internal",
                        "status": "internal",
                        "fetched_at": _utc_isoz(),
                        "latency_ms": None,
                        "fallback_chain": [],
                        "error": None,
                        "detail_preview": _detail_preview_for_data_source(auction_strength_text),
                    },
                )
            )

    results["derived_signals"] = derived_signals
    _append_tier3_snapshot_items(source_items, ticker=ticker, trade_date=trade_date)

    # Grounded sentiment_data — reuse news cache, avoid duplicate Tushare news fetch
    sentiment_data = {
        "xueqiu_hot": results.get("hot_stocks"),
        "guba_posts": results.get("hot_stocks"),  # placeholder until dedicated guba fetch
        "tushare_news": results.get("news"),
    }
    results["sentiment_data"] = sentiment_data
    for sub_key, payload in sentiment_data.items():
        status = "ok" if payload and str(payload).strip() not in ("", "无数据") else "hint"
        source_items.append(
            enrich_data_source_item(
                f"sentiment_data.{sub_key}",
                {
                    "method": sub_key,
                    "vendor": "cn_akshare" if sub_key != "tushare_news" else "cn_tushare",
                    "status": status,
                    "fetched_at": _utc_isoz(),
                    "latency_ms": None,
                    "fallback_chain": [],
                    "error": None if status == "ok" else "本日无对应记录",
                    "detail_preview": _detail_preview_for_data_source(str(payload or "")),
                    "category": "sentiment_data",
                },
            )
        )

    results["_data_sources"] = {
        "generated_at": datetime.fromtimestamp(fetch_start, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "total_latency_ms": int((time.time() - fetch_start) * 1000),
        "suggest_intraday_poll_sec": _suggest_intraday_poll_sec(trade_date),
        "items": source_items,
    }

    print(f"[Timer] Total Data Collection for {ticker} took {time.time() - fetch_start:.2f}s")
    return results


class DataCollector:
    """Collect and cache data, thread-safe and shareable across jobs."""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()
        self._refcounts: Dict[str, int] = {}
        cache_enabled = os.getenv("TA_DATA_COLLECTOR_CACHE_ENABLED", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self._tiered_cache = (
            get_tiered_cache("data_collector", enabled=cache_enabled)
            if cache_enabled and get_tiered_cache is not None
            else None
        )

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._meta_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def collect(self, ticker: str, trade_date: str, horizons: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fetch all data and store in cache.

        Thread-safe: concurrent calls for the same ticker+date will block
        on a per-key lock, so data is fetched only once.
        """
        key = make_cache_key(ticker, trade_date)
        if self._tiered_cache is not None:
            hit = self._tiered_cache.get(key)
            if isinstance(hit, dict):
                with self._meta_lock:
                    self._cache[key] = hit
                return hit
        key_lock = self._get_key_lock(key)
        with key_lock:
            if key not in self._cache:
                self._cache[key] = _fetch_all(ticker, trade_date)
                if self._tiered_cache is not None:
                    self._tiered_cache.set(key, self._cache[key], 3600)
        return self._cache[key]

    def get(self, ticker: str, trade_date: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached pool, or None if not collected yet."""
        return self._cache.get(make_cache_key(ticker, trade_date))

    def get_window(
        self,
        pool: Dict[str, Any],
        horizon: str,
        trade_date: str,
    ) -> Dict[str, Any]:
        """Return pool copy annotated with horizon window metadata."""
        days = SHORT_DAYS if horizon == "short" else LONG_DAYS
        result = dict(pool)
        result["_data_window"] = f"{days}天"
        result["_horizon"] = horizon
        return result

    def ref(self, ticker: str, trade_date: str) -> None:
        """Increment reference count (call before using cached data)."""
        key = make_cache_key(ticker, trade_date)
        with self._meta_lock:
            self._refcounts[key] = self._refcounts.get(key, 0) + 1

    def evict(self, ticker: str, trade_date: str) -> None:
        """Decrement refcount and remove cached data when no one needs it."""
        key = make_cache_key(ticker, trade_date)
        with self._meta_lock:
            count = self._refcounts.get(key, 1) - 1
            if count <= 0:
                self._cache.pop(key, None)
                self._refcounts.pop(key, None)
                # 不删除 _locks[key]：其他线程可能仍持有该锁的引用，
                # 删除会导致新 collect() 创建新锁，破坏互斥。
                # 锁对象很轻量，留着不影响内存。
            else:
                self._refcounts[key] = count
