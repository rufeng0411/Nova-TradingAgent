from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

BASELINE_VERSION = "2026-05"
BASELINE_TABLE_V1: dict[str, dict[str, float]] = {
    "食品饮料": {"roe": 12.0, "debt_ratio": 55.0},
    "银行": {"roe": 9.0, "debt_ratio": 92.0},
    "医药生物": {"roe": 10.0, "debt_ratio": 48.0},
    "电子": {"roe": 8.5, "debt_ratio": 52.0},
    "电力设备": {"roe": 8.0, "debt_ratio": 60.0},
}


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


def _is_baseline_expired(version_ym: str) -> bool:
    try:
        ts = datetime.strptime(version_ym, "%Y-%m").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        months = (now.year - ts.year) * 12 + (now.month - ts.month)
        return months > 12
    except Exception:
        return True


def build_financial_health_score(
    fina_indicator: Any,
    income: Any,
    cashflow: Any,
    balancesheet: Any,
    daily_basic: Any = None,
    industry_code: str | None = None,
) -> tuple[dict[str, Any], str]:
    fi_df = _to_df(fina_indicator)
    income_df = _to_df(income)
    cf_df = _to_df(cashflow)
    bs_df = _to_df(balancesheet)
    db_df = _to_df(daily_basic)
    if fi_df.empty and income_df.empty and cf_df.empty and bs_df.empty:
        return (
            {
                "method": "financial_health_v1",
                "error": "insufficient_data",
                "baseline_freshness": BASELINE_VERSION,
                "confidence": "medium",
            },
            "财务报表数据不足，暂无法计算财务健康度。",
        )

    industry = (industry_code or "").strip()
    baseline = BASELINE_TABLE_V1.get(industry) or {"roe": 10.0, "debt_ratio": 60.0}

    def _latest_row(df: pd.DataFrame) -> dict[str, Any]:
        if df.empty:
            return {}
        work = df.copy()
        for c in ("end_date", "ann_date", "trade_date"):
            if c in work.columns:
                work[c] = pd.to_numeric(work[c], errors="coerce")
        sort_cols = [c for c in ("end_date", "ann_date", "trade_date") if c in work.columns]
        if sort_cols:
            work = work.sort_values(by=sort_cols, ascending=False, na_position="last")
        return work.iloc[0].to_dict()

    latest_fi = _latest_row(fi_df)
    latest_cf = _latest_row(cf_df)
    latest_bs = _latest_row(bs_df)
    latest_db = _latest_row(db_df)

    roe = _safe_float(latest_fi.get("roe")) or _safe_float(latest_fi.get("roe_avg"))
    debt_ratio = _safe_float(latest_bs.get("debt_to_assets")) or _safe_float(latest_fi.get("debt_to_assets"))

    gross_margin_trend = None
    if not income_df.empty and "grossprofit_margin" in income_df.columns:
        gm = pd.to_numeric(income_df["grossprofit_margin"], errors="coerce").dropna().tail(4)
        if len(gm) >= 2:
            gross_margin_trend = float(gm.iloc[-1] - gm.iloc[0])
    elif "gross_margin" in fi_df.columns:
        gm = pd.to_numeric(fi_df["gross_margin"], errors="coerce").dropna().tail(4)
        if len(gm) >= 2:
            gross_margin_trend = float(gm.iloc[-1] - gm.iloc[0])

    ocf = _safe_float(latest_cf.get("n_cashflow_act")) or _safe_float(latest_cf.get("n_cashflow_acti"))
    net_profit = (
        _safe_float(latest_fi.get("n_income"))
        or _safe_float(latest_fi.get("profit_dedt"))
        or _safe_float(latest_fi.get("netprofit"))
    )
    cash_quality = (ocf / net_profit) if (ocf is not None and net_profit not in (None, 0)) else None
    pe_ttm = _safe_float(latest_db.get("pe_ttm")) or _safe_float(latest_fi.get("pe_ttm"))
    pb = _safe_float(latest_db.get("pb")) or _safe_float(latest_fi.get("pb"))

    score = 50.0
    if roe is not None:
        score += max(-20.0, min(20.0, (roe - baseline["roe"]) * 1.5))
    if debt_ratio is not None:
        score -= max(-15.0, min(15.0, (debt_ratio - baseline["debt_ratio"]) * 0.5))
    if gross_margin_trend is not None:
        score += max(-10.0, min(10.0, gross_margin_trend * 2.0))
    if cash_quality is not None:
        score += max(-15.0, min(15.0, (cash_quality - 1.0) * 10.0))
    score = max(0.0, min(100.0, score))

    stale = _is_baseline_expired(BASELINE_VERSION)
    tail = "（行业基线已过期，仅供方向参考）" if stale else ""
    summary = (
        f"ROE {roe if roe is not None else 'NA'}%，资产负债率 {debt_ratio if debt_ratio is not None else 'NA'}%，"
        f"毛利率趋势 {gross_margin_trend if gross_margin_trend is not None else 'NA'}，"
        f"现金流质量 {cash_quality if cash_quality is not None else 'NA'}，"
        f"PE(TTM) {pe_ttm if pe_ttm is not None else 'NA'}，PB {pb if pb is not None else 'NA'}，"
        f"综合健康分 {score:.1f}/100。{tail}"
    )
    return (
        {
            "method": "financial_health_v1",
            "industry_code": industry or None,
            "roe": roe,
            "debt_ratio": debt_ratio,
            "gross_margin_trend": gross_margin_trend,
            "cash_quality": cash_quality,
            "pe_ttm": pe_ttm,
            "pb": pb,
            "health_score": score,
            "baseline_freshness": BASELINE_VERSION,
            "confidence": "medium",
        },
        summary,
    )
