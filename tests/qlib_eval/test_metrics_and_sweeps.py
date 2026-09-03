from __future__ import annotations

import pandas as pd

from tradingagents.qlib_eval.eval.version_gate import evaluate_gate
from tradingagents.qlib_eval.metrics.ic import direction_hit_rate, spearman_ic
from tradingagents.qlib_eval.sweeps.rule_sweeps import sweep_all_rules


def test_spearman_ic_basic():
    df = pd.DataFrame({"f": [1, 2, 3, 4, 5], "y": [0.1, 0.2, 0.3, 0.4, 0.5]})
    ic = spearman_ic(df["f"], df["y"])
    assert ic is not None
    assert ic > 0.9


def test_direction_hit_rate():
    df = pd.DataFrame({"signal": [1, -1, 0, 1], "label_t1": [0.02, -0.01, 0.001, 0.03]})
    hit = direction_hit_rate(df, signal_col="signal", label_col="label_t1")
    assert hit["hit_rate_pct"] is not None
    assert hit["sample_count"] == 4


def test_evaluate_gate_pass():
    gate = evaluate_gate({"hit_rate_pct": 60.0, "ic": 0.05, "coverage_pct": 40.0})
    assert gate["passed"] is True


def test_evaluate_gate_fail():
    gate = evaluate_gate({"hit_rate_pct": 40.0, "ic": 0.001, "coverage_pct": 10.0})
    assert gate["passed"] is False
    assert gate["reasons"]


def test_sweep_all_rules_smoke():
    panel = pd.DataFrame(
        {
            "ob_ask_bid_ratio": [0.8, 1.5, 1.0, 1.6],
            "auc_vol_growth_pct": [0.1, 0.6, 0.2, 0.8],
            "mf_main_net_inflow_5d": [1e8, -2e8, 3e8, -1e8],
            "ab_active_buy_ratio": [0.55, 0.45, 0.6, 0.5],
            "label_t0": [0.01, -0.02, 0.005, 0.03],
            "label_t1": [0.02, -0.01, 0.01, 0.04],
            "label_t2": [0.03, -0.02, 0.015, 0.05],
        }
    )
    out = sweep_all_rules(panel)
    assert out["items"]
    assert out["best"] is not None
