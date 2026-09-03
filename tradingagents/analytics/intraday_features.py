from __future__ import annotations

from typing import Any

import pandas as pd


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def intraday_vwap_deviation(mins_df: pd.DataFrame, current_price: float | None) -> float | None:
    if mins_df is None or mins_df.empty or current_price in (None, 0):
        return None
    close_col = "close" if "close" in mins_df.columns else ("price" if "price" in mins_df.columns else None)
    vol_col = "vol" if "vol" in mins_df.columns else ("volume" if "volume" in mins_df.columns else None)
    if not close_col or not vol_col:
        return None
    px = pd.to_numeric(mins_df[close_col], errors="coerce")
    vv = pd.to_numeric(mins_df[vol_col], errors="coerce").fillna(0)
    if vv.sum() <= 0:
        return None
    if "amount" in mins_df.columns:
        amt = pd.to_numeric(mins_df["amount"], errors="coerce").fillna(0)
        vwap = float(amt.sum() / vv.sum()) if vv.sum() > 0 else None
    else:
        vwap = float((px * vv).sum() / vv.sum()) if vv.sum() > 0 else None
    if vwap in (None, 0):
        return None
    return (float(current_price) - vwap) / vwap


def orderbook_imbalance(orderbook_row: dict[str, Any], *, level_count: int = 5) -> float | None:
    ask_sum = 0.0
    bid_sum = 0.0
    for i in range(1, max(1, level_count) + 1):
        ask_sum += _safe_float(orderbook_row.get(f"ask_volume{i}")) or 0.0
        bid_sum += _safe_float(orderbook_row.get(f"bid_volume{i}")) or 0.0
    denom = ask_sum + bid_sum
    if denom <= 0:
        return None
    return (bid_sum - ask_sum) / denom


def relative_strength_vs_index(symbol_pct: float | None, index_pct: float | None) -> float | None:
    if symbol_pct is None or index_pct is None:
        return None
    return float(symbol_pct) - float(index_pct)


def intraday_position_in_range(high: float | None, low: float | None, close: float | None) -> float | None:
    if high is None or low is None or close is None or high <= low:
        return None
    return (float(close) - float(low)) / (float(high) - float(low))


def summarize_intraday_features(features: dict[str, Any]) -> str:
    parts: list[str] = []
    vwap_dev = _safe_float(features.get("intraday_vwap_dev"))
    if vwap_dev is not None:
        parts.append(f"现价较日内VWAP偏离{vwap_dev * 100:+.2f}%")
    ob_imb = _safe_float(features.get("bid_ask_imbalance"))
    if ob_imb is not None:
        side = "买盘承接占优" if ob_imb > 0 else "卖盘抛压占优"
        parts.append(f"盘口失衡{ob_imb:+.2f}（{side}）")
    rs = _safe_float(features.get("relative_strength_vs_index"))
    if rs is not None:
        parts.append(f"相对指数强弱{rs * 100:+.2f}%")
    pos = _safe_float(features.get("intraday_pos_in_range"))
    if pos is not None:
        parts.append(f"当前位于当日振幅{pos * 100:.1f}%分位")
    text = "；".join(parts)
    if len(text) > 80:
        return text[:79] + "…"
    return text or "盘中派生特征暂不可用"
