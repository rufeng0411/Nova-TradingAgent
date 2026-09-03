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


def _sum_levels(row: dict[str, Any], side: str, level_count: int) -> float:
    total = 0.0
    for i in range(1, max(1, level_count) + 1):
        vol = _safe_float(row.get(f"{side}_volume{i}")) or _safe_float(row.get(f"{side}_vol{i}")) or 0.0
        px = _safe_float(row.get(f"{side}_price{i}")) or 0.0
        total += vol * px if px > 0 else vol
    return total


def build_orderbook_pressure_signal(orderbook_row: dict[str, Any], *, level_count: int = 5) -> tuple[dict[str, Any], str]:
    if not isinstance(orderbook_row, dict) or not orderbook_row:
        return (
            {"method": "orderbook_pressure_signal_v1", "error": "insufficient_data", "confidence": "medium"},
            "盘口数据不足，暂无法生成盘口压力代理。",
        )
    ask_total = _sum_levels(orderbook_row, "ask", level_count)
    bid_total = _sum_levels(orderbook_row, "bid", level_count)
    if ask_total <= 0 and bid_total <= 0:
        return (
            {"method": "orderbook_pressure_signal_v1", "error": "insufficient_data", "confidence": "medium"},
            "盘口挂单数据为空，暂无法生成盘口压力代理。",
        )
    ratio = ask_total / max(bid_total, 1e-6)
    pressure = "卖压偏重" if ratio >= 1.4 else ("买盘承接偏强" if ratio <= 0.75 else "买卖力量均衡")
    summary = (
        f"卖{level_count}档累计挂单约 {ask_total / 1e8:.2f} 亿元，"
        f"买{level_count}档约 {bid_total / 1e8:.2f} 亿元，"
        f"卖买比 {ratio:.2f}，{pressure}。"
    )
    return (
        {
            "method": "orderbook_pressure_signal_v1",
            "ask_total": ask_total,
            "bid_total": bid_total,
            "ask_bid_ratio": ratio,
            "level_count": int(level_count),
            "pressure": pressure,
            "confidence": "medium",
        },
        summary,
    )


def build_active_buy_proxy(moneyflow_dc_df: Any) -> tuple[dict[str, Any], str]:
    if isinstance(moneyflow_dc_df, pd.DataFrame):
        df = moneyflow_dc_df
    elif isinstance(moneyflow_dc_df, list):
        df = pd.DataFrame(moneyflow_dc_df)
    else:
        df = pd.DataFrame()
    if df.empty:
        return (
            {"method": "active_buy_proxy_v1", "error": "insufficient_data", "confidence": "low"},
            "资金流数据不足，暂无法估算主动买入近似（近似指标，非真 L2 逐笔）。",
        )

    latest = df.iloc[-1].to_dict()
    buy_lg = _safe_float(latest.get("buy_lg_amount")) or 0.0
    sell_lg = _safe_float(latest.get("sell_lg_amount")) or 0.0
    buy_elg = _safe_float(latest.get("buy_elg_amount")) or 0.0
    sell_elg = _safe_float(latest.get("sell_elg_amount")) or 0.0
    net_main = _safe_float(latest.get("net_mf_amount"))
    amount = _safe_float(latest.get("amount")) or _safe_float(latest.get("turnover")) or 0.0
    if amount <= 0:
        amount = (
            buy_lg
            + sell_lg
            + buy_elg
            + sell_elg
            + (_safe_float(latest.get("buy_md_amount")) or 0.0)
            + (_safe_float(latest.get("sell_md_amount")) or 0.0)
            + (_safe_float(latest.get("buy_sm_amount")) or 0.0)
            + (_safe_float(latest.get("sell_sm_amount")) or 0.0)
        )

    buy_flow = buy_lg + buy_elg
    sell_flow = sell_lg + sell_elg
    gross = buy_flow + sell_flow
    if gross <= 0:
        proxy_ratio = None
    else:
        proxy_ratio = buy_flow / gross
    net_inflow_pct = (net_main / amount) if (net_main is not None and amount > 0) else None
    detail = "近似主动买入占比缺失"
    if proxy_ratio is not None:
        detail = f"近似主动买入占比 {proxy_ratio * 100:.1f}%"
    summary = (
        f"大单+超大单净流入 {((net_main or 0.0) / 1e8):+.2f} 亿元，"
        f"占成交额 {((net_inflow_pct or 0.0) * 100):.2f}%；{detail}（近似指标，非真 L2 逐笔）。"
    )
    return (
        {
            "method": "active_buy_proxy_v1",
            "net_main": net_main,
            "turnover_amount": amount,
            "net_inflow_pct": net_inflow_pct,
            "active_buy_proxy_ratio": proxy_ratio,
            "confidence": "low",
        },
        summary,
    )
