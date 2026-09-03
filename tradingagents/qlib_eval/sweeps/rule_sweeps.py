"""Fast parameter sweeps for short-horizon L2 / auction / moneyflow rules."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Callable

import numpy as np
import pandas as pd

from tradingagents.qlib_eval.metrics.ic import direction_hit_rate


@dataclass(frozen=True)
class RuleSpec:
    name: str
    signal_col: str
    label_col: str
    thresholds: tuple[float, ...]
    direction: str = "follow"  # follow | contrarian


RULE_SPECS: tuple[RuleSpec, ...] = (
    RuleSpec("orderbook_pressure", "ob_ask_bid_ratio", "label_t1", (0.75, 1.0, 1.25, 1.4, 1.6, 1.8), "contrarian"),
    RuleSpec("auction_vol_growth", "auc_vol_growth_pct", "label_t0", (0.2, 0.35, 0.5, 0.75, 1.0), "follow"),
    RuleSpec("moneyflow_5d", "mf_main_net_inflow_5d", "label_t2", (0.0,), "follow"),
    RuleSpec("active_buy_ratio", "ab_active_buy_ratio", "label_t1", (0.45, 0.5, 0.55, 0.6, 0.65), "follow"),
)


def _apply_rule_signal(series: pd.Series, threshold: float, *, direction: str, rule_name: str) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if rule_name == "orderbook_pressure":
        # High ask/bid ratio -> bearish signal (contrarian to bid support)
        sig = np.where(s >= threshold, -1.0, np.where(s <= (1.0 / max(threshold, 1e-6)), 1.0, 0.0))
        return pd.Series(sig, index=series.index)
    if rule_name == "moneyflow_5d":
        pos = s.quantile(0.7) if s.notna().sum() else 0.0
        neg = s.quantile(0.3) if s.notna().sum() else 0.0
        return pd.Series(np.where(s >= pos, 1.0, np.where(s <= neg, -1.0, 0.0)), index=series.index)
    # Default: follow momentum above threshold
    sig = np.where(s >= threshold, 1.0, np.where(s <= -threshold, -1.0, 0.0))
    if direction == "contrarian":
        sig = -sig
    return pd.Series(sig, index=series.index)


def sweep_rule(panel: pd.DataFrame, spec: RuleSpec) -> list[dict[str, Any]]:
    if spec.signal_col not in panel.columns or spec.label_col not in panel.columns:
        return []
    results: list[dict[str, Any]] = []
    for th in spec.thresholds:
        tmp = panel.copy()
        tmp["rule_signal"] = _apply_rule_signal(tmp[spec.signal_col], th, direction=spec.direction, rule_name=spec.name)
        hit = direction_hit_rate(tmp, signal_col="rule_signal", label_col=spec.label_col, threshold=0.0)
        results.append(
            {
                "rule": spec.name,
                "signal_col": spec.signal_col,
                "label_col": spec.label_col,
                "threshold": th,
                "hit_rate_pct": hit.get("hit_rate_pct"),
                "coverage_pct": hit.get("coverage_pct"),
                "sample_count": hit.get("sample_count"),
            }
        )
    return results


def sweep_all_rules(panel: pd.DataFrame, specs: tuple[RuleSpec, ...] = RULE_SPECS) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for spec in specs:
        items.extend(sweep_rule(panel, spec))
    best = None
    for row in items:
        hr = row.get("hit_rate_pct")
        if hr is None:
            continue
        if best is None or hr > best.get("hit_rate_pct", -1):
            best = row
    return {"items": items, "best": best, "rule_count": len(specs)}


def vectorbt_sweep_if_available(panel: pd.DataFrame, spec: RuleSpec) -> dict[str, Any] | None:
    """Optional vectorbt acceleration; returns None when not installed."""
    try:
        import vectorbt as vbt  # noqa: F401
    except ImportError:
        return None
    # vectorbt is optional; grid results already covered by sweep_rule
    return {"vectorbt_available": True, "note": "using_native_sweep", "rule": spec.name}
