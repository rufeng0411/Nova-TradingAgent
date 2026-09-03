from __future__ import annotations

import pandas as pd

from tradingagents.qlib_eval.schema import (
    build_feature_snapshot,
    compute_forward_return_labels,
    extract_derived_features,
    merge_feature_label_rows,
)


def test_extract_derived_features_orderbook():
    ds = {
        "orderbook_pressure_signal_v1": {"ask_bid_ratio": 1.5, "ask_total": 100.0, "bid_total": 66.0},
        "auction_intraday_strength_v1": {"vol_growth_pct": 0.6, "price_move_pct": 0.01},
    }
    feats = extract_derived_features(ds)
    assert feats["ob_ask_bid_ratio"] == 1.5
    assert feats["auc_vol_growth_pct"] == 0.6


def test_compute_forward_return_labels_no_lookahead():
    from pytest import approx

    bars = pd.DataFrame(
        {
            "trade_date": ["2026-01-02", "2026-01-03", "2026-01-06", "2026-01-07"],
            "close": [10.0, 10.5, 11.0, 10.8],
        }
    )
    label = compute_forward_return_labels(bars, symbol="600519.SH", trade_date="2026-01-03")
    assert label is not None
    assert label.labels["t1"] == approx(11.0 / 10.5 - 1.0, rel=1e-6)


def test_merge_feature_label_row():
    snap = build_feature_snapshot(
        symbol="600519.SH",
        trade_date="2026-01-03",
        derived_signals={"orderbook_pressure_signal_v1": {"ask_bid_ratio": 1.2}},
    )
    row = merge_feature_label_rows(snap, None)
    assert row["symbol"] == "600519.SH"
    assert row["ob_ask_bid_ratio"] == 1.2
    assert row["label_t2"] is None
