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


def _to_df(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, list):
        return pd.DataFrame(value)
    return pd.DataFrame()


def build_moneyflow_structure(
    moneyflow_dc: Any,
    moneyflow_industry_dc: Any,
    top_list: Any,
) -> tuple[dict[str, Any], str]:
    mf_df = _to_df(moneyflow_dc)
    ind_df = _to_df(moneyflow_industry_dc)
    tl_df = _to_df(top_list)

    if mf_df.empty and ind_df.empty and tl_df.empty:
        return (
            {"method": "moneyflow_structure_v1", "error": "insufficient_data", "confidence": "medium"},
            "资金流与龙虎榜数据不足，暂无法形成资金结构化结论。",
        )

    net_col = "net_mf_amount" if "net_mf_amount" in mf_df.columns else None
    net_5d = None
    if net_col:
        series = pd.to_numeric(mf_df[net_col], errors="coerce").dropna()
        if not series.empty:
            net_5d = float(series.tail(5).sum())

    industry_rank_pct = None
    if not ind_df.empty:
        rank_col = "rank" if "rank" in ind_df.columns else None
        if rank_col:
            rank_series = pd.to_numeric(ind_df[rank_col], errors="coerce").dropna()
            if not rank_series.empty:
                top_rank = float(rank_series.iloc[0])
                industry_rank_pct = max(0.0, min(1.0, 1.0 - (top_rank - 1.0) / max(len(ind_df), 1)))

    inst_net_buy = None
    for col in ("net_buy", "net_buy_amount", "net_amount"):
        if col in tl_df.columns:
            vals = pd.to_numeric(tl_df[col], errors="coerce").dropna()
            if not vals.empty:
                inst_net_buy = float(vals.tail(7).sum())
                break

    summary = (
        f"近5日主力净流入 {((net_5d or 0.0) / 1e8):+.2f} 亿；"
        f"行业资金梯队分位 {(industry_rank_pct or 0.0) * 100:.1f}%；"
        f"龙虎榜机构净买 {((inst_net_buy or 0.0) / 1e8):+.2f} 亿。"
    )

    return (
        {
            "method": "moneyflow_structure_v1",
            "main_net_inflow_5d": net_5d,
            "industry_rank_pct": industry_rank_pct,
            "inst_net_buy_7d": inst_net_buy,
            "confidence": "medium",
        },
        summary,
    )
