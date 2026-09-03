"""Unified feature / label schema for Qlib evaluation.

Maps Tushare L2, marketdata_* rows, and derived_signals v1 payloads into a
flat numeric feature vector plus T+N forward-return labels (no lookahead).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Literal

import pandas as pd

LabelHorizon = Literal["t0", "t1", "t2", "t3", "t5"]

LABEL_HORIZONS: tuple[LabelHorizon, ...] = ("t0", "t1", "t2", "t3", "t5")
FULL_LABEL_HORIZONS: tuple[LabelHorizon, ...] = ("t1", "t2", "t3", "t5")
FAST_LABEL_HORIZONS: tuple[LabelHorizon, ...] = ("t0", "t1")

# Trading-day offsets for each horizon (t0 = same session close vs baseline)
HORIZON_TRADING_DAYS: dict[LabelHorizon, int] = {
    "t0": 0,
    "t1": 1,
    "t2": 2,
    "t3": 3,
    "t5": 5,
}


@dataclass(frozen=True)
class FeatureFieldSpec:
    name: str
    source: str  # derived_signals | marketdata | l2 | intraday
    dtype: str = "float"
    description: str = ""


# Flat numeric fields extracted from derived_signals v1 payloads.
DERIVED_SIGNAL_FIELDS: tuple[FeatureFieldSpec, ...] = (
    FeatureFieldSpec("ob_ask_bid_ratio", "derived_signals", description="orderbook_pressure ask/bid ratio"),
    FeatureFieldSpec("ob_ask_total", "derived_signals", description="orderbook ask notional sum"),
    FeatureFieldSpec("ob_bid_total", "derived_signals", description="orderbook bid notional sum"),
    FeatureFieldSpec("ab_active_buy_ratio", "derived_signals", description="active buy proxy ratio"),
    FeatureFieldSpec("ab_net_main", "derived_signals", description="main force net inflow"),
    FeatureFieldSpec("mf_main_net_inflow_5d", "derived_signals", description="5d main net inflow"),
    FeatureFieldSpec("mf_industry_rank_pct", "derived_signals", description="industry moneyflow rank percentile"),
    FeatureFieldSpec("mf_inst_net_buy_7d", "derived_signals", description="7d institutional net buy from top_list"),
    FeatureFieldSpec("fh_score", "derived_signals", description="financial health composite score"),
    FeatureFieldSpec("auc_vol_growth_pct", "derived_signals", description="auction volume growth"),
    FeatureFieldSpec("auc_price_move_pct", "derived_signals", description="auction price move"),
    FeatureFieldSpec("auc_amount_growth_pct", "derived_signals", description="auction amount growth"),
    FeatureFieldSpec("intraday_vwap_dev", "intraday", description="intraday VWAP deviation"),
    FeatureFieldSpec("intraday_pos_in_range", "intraday", description="close position in day range"),
    FeatureFieldSpec("relative_strength_vs_index", "intraday", description="symbol vs index relative strength"),
)

# marketdata_* columns merged into the feature row (prefix md_)
MARKETDATA_FIELDS: tuple[FeatureFieldSpec, ...] = (
    FeatureFieldSpec("md_pe_ttm", "marketdata", description="PE TTM from daily_basic / factor"),
    FeatureFieldSpec("md_pb", "marketdata", description="PB"),
    FeatureFieldSpec("md_turnover_rate", "marketdata", description="turnover rate"),
    FeatureFieldSpec("md_total_mv", "marketdata", description="total market cap"),
    FeatureFieldSpec("md_net_mf_amount", "marketdata", description="daily net moneyflow"),
    FeatureFieldSpec("md_winner_rate", "marketdata", description="CYQ winner rate"),
    FeatureFieldSpec("md_cost_50pct", "marketdata", description="CYQ 50pct cost"),
)


def all_feature_names() -> list[str]:
    return [f.name for f in DERIVED_SIGNAL_FIELDS + MARKETDATA_FIELDS]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(n):
        return None
    return n


def extract_derived_features(derived_signals: dict[str, Any] | None) -> dict[str, float | None]:
    """Flatten derived_signals v1 dict into schema field names."""
    ds = dict(derived_signals or {})
    ob = dict(ds.get("orderbook_pressure_signal_v1") or {})
    ab = dict(ds.get("active_buy_proxy_v1") or {})
    mf = dict(ds.get("moneyflow_structure_v1") or {})
    fh = dict(ds.get("financial_health_v1") or {})
    auc = dict(ds.get("auction_intraday_strength_v1") or {})

    return {
        "ob_ask_bid_ratio": _safe_float(ob.get("ask_bid_ratio")),
        "ob_ask_total": _safe_float(ob.get("ask_total")),
        "ob_bid_total": _safe_float(ob.get("bid_total")),
        "ab_active_buy_ratio": _safe_float(ab.get("active_buy_proxy_ratio")),
        "ab_net_main": _safe_float(ab.get("net_main")),
        "mf_main_net_inflow_5d": _safe_float(mf.get("main_net_inflow_5d")),
        "mf_industry_rank_pct": _safe_float(mf.get("industry_rank_pct")),
        "mf_inst_net_buy_7d": _safe_float(mf.get("inst_net_buy_7d")),
        "fh_score": _safe_float(fh.get("health_score")),
        "auc_vol_growth_pct": _safe_float(auc.get("vol_growth_pct")),
        "auc_price_move_pct": _safe_float(auc.get("price_move_pct")),
        "auc_amount_growth_pct": _safe_float(auc.get("amount_growth_pct")),
    }


def extract_intraday_features(intraday: dict[str, Any] | None) -> dict[str, float | None]:
    row = dict(intraday or {})
    return {
        "intraday_vwap_dev": _safe_float(row.get("intraday_vwap_dev")),
        "intraday_pos_in_range": _safe_float(row.get("intraday_pos_in_range")),
        "relative_strength_vs_index": _safe_float(row.get("relative_strength_vs_index")),
    }


def extract_marketdata_features(row: dict[str, Any] | None) -> dict[str, float | None]:
    md = dict(row or {})
    return {
        "md_pe_ttm": _safe_float(md.get("pe_ttm") or md.get("pe")),
        "md_pb": _safe_float(md.get("pb")),
        "md_turnover_rate": _safe_float(md.get("turnover_rate")),
        "md_total_mv": _safe_float(md.get("total_mv") or md.get("circ_mv")),
        "md_net_mf_amount": _safe_float(md.get("net_mf_amount")),
        "md_winner_rate": _safe_float(md.get("winner_rate")),
        "md_cost_50pct": _safe_float(md.get("cost_50pct")),
    }


@dataclass
class FeatureSnapshot:
    symbol: str
    trade_date: str
    features: dict[str, float | None] = field(default_factory=dict)
    source_tags: dict[str, str] = field(default_factory=dict)
    schema_version: str = "qlib_feature_v1"

    def to_row(self) -> dict[str, Any]:
        out: dict[str, Any] = {"symbol": self.symbol, "trade_date": self.trade_date}
        for name in all_feature_names():
            out[name] = self.features.get(name)
        out["schema_version"] = self.schema_version
        return out

    def coverage_ratio(self) -> float:
        names = all_feature_names()
        if not names:
            return 0.0
        filled = sum(1 for n in names if self.features.get(n) is not None)
        return filled / len(names)


def build_feature_snapshot(
    *,
    symbol: str,
    trade_date: str,
    derived_signals: dict[str, Any] | None = None,
    intraday_features: dict[str, Any] | None = None,
    marketdata_row: dict[str, Any] | None = None,
) -> FeatureSnapshot:
    feats: dict[str, float | None] = {}
    tags: dict[str, str] = {}
    for k, v in extract_derived_features(derived_signals).items():
        feats[k] = v
        if v is not None:
            tags[k] = "derived_signals"
    for k, v in extract_intraday_features(intraday_features).items():
        feats[k] = v
        if v is not None:
            tags[k] = "intraday"
    for k, v in extract_marketdata_features(marketdata_row).items():
        feats[k] = v
        if v is not None:
            tags[k] = "marketdata"
    return FeatureSnapshot(symbol=symbol, trade_date=trade_date, features=feats, source_tags=tags)


@dataclass
class LabelSnapshot:
    symbol: str
    trade_date: str
    baseline_close: float
    labels: dict[LabelHorizon, float | None] = field(default_factory=dict)
    schema_version: str = "qlib_label_v1"

    def to_row(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "symbol": self.symbol,
            "trade_date": self.trade_date,
            "baseline_close": self.baseline_close,
            "schema_version": self.schema_version,
        }
        for h in LABEL_HORIZONS:
            out[f"label_{h}"] = self.labels.get(h)
        return out


def _normalize_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    s = str(value or "").strip()
    if " " in s:
        s = s.split(" ", 1)[0]
    if "T" in s:
        s = s.split("T", 1)[0]
    return s


def compute_forward_return_labels(
    bars: pd.DataFrame,
    *,
    symbol: str,
    trade_date: str,
    horizons: Iterable[LabelHorizon] = FULL_LABEL_HORIZONS,
) -> LabelSnapshot | None:
    """Compute T+N close-to-close returns from an OHLCV panel (no future leak on features).

    bars must contain columns: trade_date (or date), close. Rows sorted ascending by date.
    """
    if bars is None or bars.empty:
        return None
    df = bars.copy()
    date_col = "trade_date" if "trade_date" in df.columns else ("date" if "date" in df.columns else None)
    if not date_col or "close" not in df.columns:
        return None
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=[date_col, "close"]).sort_values(date_col).reset_index(drop=True)
    td = _normalize_date(trade_date)
    idx_list = df.index[df[date_col] == td].tolist()
    if not idx_list:
        return None
    base_idx = idx_list[0]
    baseline = float(df.loc[base_idx, "close"])
    if baseline <= 0:
        return None

    labels: dict[LabelHorizon, float | None] = {}
    for h in horizons:
        offset = HORIZON_TRADING_DAYS.get(h, 0)
        target_idx = base_idx + offset
        if target_idx >= len(df):
            labels[h] = None
        else:
            future_close = float(df.loc[target_idx, "close"])
            labels[h] = (future_close - baseline) / baseline
    return LabelSnapshot(symbol=symbol, trade_date=td, baseline_close=baseline, labels=labels)


def merge_feature_label_rows(
    feature: FeatureSnapshot,
    label: LabelSnapshot | None,
) -> dict[str, Any]:
    row = feature.to_row()
    if label:
        for h in LABEL_HORIZONS:
            row[f"label_{h}"] = label.labels.get(h)
        row["baseline_close"] = label.baseline_close
    else:
        for h in LABEL_HORIZONS:
            row[f"label_{h}"] = None
        row["baseline_close"] = None
    row["feature_coverage"] = feature.coverage_ratio()
    return row
