from __future__ import annotations

from typing import Any

import pandas as pd

from tradingagents.analytics.intraday_features import (
    intraday_position_in_range,
    intraday_vwap_deviation,
    orderbook_imbalance,
    relative_strength_vs_index,
)
from tradingagents.analytics.ta_features import extract_features

# 与下方 `features` 字典键数量保持一致（用于进度条「槽位」统计，避免与「非空数值项」混淆）
FAST_FEATURE_SLOT_COUNT = 25


def _records_to_df(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _latest(records: list[dict[str, Any]]) -> dict[str, Any]:
    return records[-1] if records else {}


def extract_fast_features(
    snapshot: dict[str, Any],
    *,
    current_position: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = dict(snapshot.get("sources") or {})
    rt_k_records = list((sources.get("rt_k") or {}).get("data") or [])
    mins_records = list((sources.get("mins") or {}).get("data") or [])
    factor_records = list((sources.get("factor") or {}).get("data") or [])
    auction_records = list((sources.get("auction") or {}).get("data") or [])
    index_records = list((sources.get("index_pulse") or {}).get("data") or [])
    moneyflow_records = list((sources.get("moneyflow") or {}).get("data") or [])
    industry_records = list((sources.get("industry_flow") or {}).get("data") or [])
    basic_records = list((sources.get("basic") or {}).get("data") or [])
    anns_records = list((sources.get("anns") or {}).get("data") or [])
    limit_records = list((sources.get("limit_list") or {}).get("data") or [])
    top_records = list((sources.get("top_list") or {}).get("data") or [])
    kline_records = list((sources.get("kline_60d") or {}).get("data") or [])

    rt = _latest(rt_k_records)
    auction = _latest(auction_records)
    basic = _latest(basic_records)
    factor = _latest(factor_records)

    mins_df = _records_to_df(mins_records)
    intraday_vwap_dev = None
    vol_ratio_5min = None
    if not mins_df.empty:
        close_col = "close" if "close" in mins_df.columns else ("price" if "price" in mins_df.columns else None)
        vol_col = "vol" if "vol" in mins_df.columns else ("volume" if "volume" in mins_df.columns else None)
        amount_col = "amount" if "amount" in mins_df.columns else None
        if close_col and vol_col:
            px = pd.to_numeric(mins_df[close_col], errors="coerce")
            vv = pd.to_numeric(mins_df[vol_col], errors="coerce").fillna(0)
            if amount_col and amount_col in mins_df.columns:
                amt = pd.to_numeric(mins_df[amount_col], errors="coerce").fillna(0)
                vwap = float((amt.sum() / vv.sum())) if vv.sum() > 0 else None
            else:
                vwap = float(((px * vv).sum() / vv.sum())) if vv.sum() > 0 else None
            last_px = _safe_float(px.iloc[-1] if len(px) else None)
            intraday_vwap_dev = intraday_vwap_deviation(mins_df, last_px)
            if len(vv) >= 10:
                vol_ratio_5min = float(vv.tail(5).mean() / max(vv.head(max(1, len(vv) - 5)).mean(), 1e-6))

    bid_ask_imbalance = orderbook_imbalance(rt, level_count=5)

    high = _safe_float(rt.get("high"))
    low = _safe_float(rt.get("low"))
    close = _safe_float(rt.get("close"))
    intraday_pos_in_range = intraday_position_in_range(high, low, close)

    market_pulse_score = None
    if index_records:
        vals = []
        for row in index_records:
            cc = _safe_float(row.get("close"))
            pc = _safe_float(row.get("pre_close"))
            if cc is not None and pc not in (None, 0):
                vals.append((cc - pc) / pc)
        if vals:
            market_pulse_score = float(max(-1.0, min(1.0, sum(vals) / len(vals) * 10)))

    relative_strength = None
    if close is not None:
        pre_close = _safe_float(rt.get("pre_close"))
        if pre_close not in (None, 0) and market_pulse_score is not None:
            relative_strength = relative_strength_vs_index((close - pre_close) / pre_close, market_pulse_score / 10.0)

    position_pnl_state = None
    if current_position:
        avg_cost = _safe_float(current_position.get("avg_cost"))
        shares = _safe_float(current_position.get("shares"))
        portfolio_pct = _safe_float(current_position.get("portfolio_pct"))
        if avg_cost and close:
            position_pnl_state = {
                "holding_pct": portfolio_pct,
                "unrealized_pnl_pct": (close - avg_cost) / avg_cost,
                "distance_to_cost_pct": (close - avg_cost) / avg_cost,
                "shares": shares,
            }

    auction_price = _safe_float(auction.get("price"))
    auction_pre_close = _safe_float(auction.get("pre_close"))
    auction_premium_pct = None
    intraday_vs_auction_pct = None
    if auction_price and auction_pre_close:
        auction_premium_pct = (auction_price - auction_pre_close) / auction_pre_close
    if auction_price and close:
        intraday_vs_auction_pct = (close - auction_price) / auction_price

    # 归一化日K列名：cn_tushare_provider.fetch_daily_bar_df 返回首字母大写
    # （Date/Open/High/Low/Close/Volume/Amount/AdjFactor），而 ta_features.candles_to_df
    # 期望小写键名。不在这里转一次会被判定为 insufficient_data → kline_insight 空。
    def _normalize_kline_record(rec: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(rec, dict):
            return rec
        if "date" in rec or "Date" not in rec:
            return rec
        return {
            "date": rec.get("Date"),
            "open": rec.get("Open"),
            "high": rec.get("High"),
            "low": rec.get("Low"),
            "close": rec.get("Close"),
            "volume": rec.get("Volume"),
            "amount": rec.get("Amount"),
        }

    kline_records_norm = [_normalize_kline_record(r) for r in kline_records]
    kline_features = extract_features(kline_records_norm, level="brief")

    # 中长期 60 日 SR：把 extract_features 的支撑/压力重命名到 *_60d，避免与盘中坐标系混淆
    if isinstance(kline_features, dict) and "supports" in kline_features:
        sup_60d = list(kline_features.get("supports") or [])
        res_60d = list(kline_features.get("resistances") or [])
        kline_features["supports_60d"] = sup_60d
        kline_features["resistances_60d"] = res_60d

        # 当日 + 近 5 日盘中坐标系：以 rt_k 当日 high/low + auction 高低 + 近 5 根日 K 的 high/low 聚合
        intraday_levels: list[float] = []
        rt_high = _safe_float(rt.get("high"))
        rt_low = _safe_float(rt.get("low"))
        for v in (rt_high, rt_low, _safe_float(rt.get("pre_close")), _safe_float(rt.get("open"))):
            if v is not None and v > 0:
                intraday_levels.append(float(v))
        auc_high = _safe_float(auction.get("high")) or _safe_float(auction.get("price"))
        auc_low = _safe_float(auction.get("low")) or _safe_float(auction.get("price"))
        for v in (auc_high, auc_low):
            if v is not None and v > 0:
                intraday_levels.append(float(v))
        for rec in kline_records_norm[-5:]:
            for k in ("high", "low"):
                v = _safe_float(rec.get(k) if isinstance(rec, dict) else None)
                if v is not None and v > 0:
                    intraday_levels.append(float(v))
        if close is not None and close > 0 and intraday_levels:
            mid = float(close)
            uniq = sorted({round(x, 2) for x in intraday_levels})
            supports_intraday = [x for x in uniq if x <= mid][-2:]
            resistances_intraday = [x for x in uniq if x >= mid][:2]
            kline_features["supports_intraday"] = supports_intraday
            kline_features["resistances_intraday"] = resistances_intraday
        else:
            kline_features["supports_intraday"] = []
            kline_features["resistances_intraday"] = []

        # 兼容旧前端：保留 supports / resistances 字段，优先使用当日坐标（如果有）
        if kline_features.get("supports_intraday"):
            kline_features["supports"] = kline_features["supports_intraday"]
            kline_features["resistances"] = kline_features["resistances_intraday"]
    # 估值/换手率优先用日终 daily_basic；盘中若 basic skipped，则回退到 stk_factor_pro（盘中可拉）。
    pe_value = _safe_float(basic.get("pe_ttm"))
    if pe_value is None:
        pe_value = _safe_float(factor.get("pe_ttm")) or _safe_float(factor.get("pe"))
    turnover_value = _safe_float(basic.get("turnover_rate"))
    if turnover_value is None:
        turnover_value = _safe_float(factor.get("turnover_rate")) or _safe_float(factor.get("turnover_rate_f"))

    # 从 kline_features 派生 3 个槽位，保证盘中 EOD 源缺失时 LLM 仍能锚定中线技术面。
    kf = kline_features if isinstance(kline_features, dict) else {}

    def _ma_alignment_score(align: Any) -> float | None:
        s = str(align or "").strip().lower()
        if s == "bullish_stack":
            return 1.0
        if s == "bearish_stack":
            return -1.0
        if s == "neutral":
            return 0.0
        return None

    features = {
        "intraday_vwap_dev": intraday_vwap_dev,
        "vol_ratio_5min": vol_ratio_5min,
        "intraday_pos_in_range": intraday_pos_in_range,
        "bid_ask_imbalance": bid_ask_imbalance,
        "factor_rsi_14": _safe_float(factor.get("rsi_14")),
        "factor_macd_dif_signal": _safe_float(factor.get("macd_dif")),
        "factor_boll_pos": _safe_float(factor.get("boll_pos")),
        "factor_atr_pct": _safe_float(factor.get("atr")) / close if close and _safe_float(factor.get("atr")) else None,
        "big_order_net_inflow_pct": _safe_float(_latest(moneyflow_records).get("net_amount_main")) or None,
        "industry_strength_rank": _safe_float(_latest(industry_records).get("rank")) or None,
        "northbound_change_pct": None,
        "lhb_inst_net_buy_7d": _safe_float(_latest(top_records).get("net_buy")) or None,
        "limit_streak_today": _safe_float(_latest(limit_records).get("limit_times")) or 0.0,
        "market_pulse_score": market_pulse_score,
        "relative_strength_vs_index": relative_strength,
        "position_pnl_state": position_pnl_state,
        "news_catalyst_score": float(len(anns_records[:5])) / 5.0 if anns_records else 0.0,
        "valuation_percentile_3y": pe_value,
        "liquidity_turnover": turnover_value,
        "auction_premium_pct": auction_premium_pct,
        "auction_volume_ratio": _safe_float(auction.get("volume_ratio")),
        "intraday_vs_auction_pct": intraday_vs_auction_pct,
        # 从 60 日 K 派生：即便 EOD 源 skipped，LLM 也能锚定中线技术面
        "kline_ma_alignment_score": _ma_alignment_score(kf.get("ma_alignment")),
        "kline_total_return_pct": _safe_float(kf.get("total_return_pct")),
        "kline_close_vs_ma20_pct": _safe_float(kf.get("close_vs_ma20_pct")),
    }
    return features, kline_features

