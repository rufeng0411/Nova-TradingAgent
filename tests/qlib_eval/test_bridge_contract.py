from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tradingagents.qlib_eval.agent.quant_context import build_quant_signal_context, format_agent_prompt_block
from tradingagents.qlib_eval.bridge.contract import BRIDGE_SCHEMA_VERSION, BridgePaths
from tradingagents.qlib_eval.bridge.inbox import submit_inbox_package
from tradingagents.qlib_eval.bridge.outbox import import_outbox_result, list_pending_outbox


def test_submit_and_import_outbox_smoke(tmp_path: Path):
    panel = pd.DataFrame(
        {
            "symbol": ["600519.SH", "300750.SZ", "600519.SH", "300750.SZ"],
            "trade_date": ["2026-01-02", "2026-01-02", "2026-01-03", "2026-01-03"],
            "ob_ask_bid_ratio": [1.1, 0.9, 1.2, 0.8],
            "label_t2": [0.01, -0.02, 0.015, 0.03],
            "feature_coverage": [0.5, 0.6, 0.55, 0.7],
        }
    )
    paths = BridgePaths.from_root(tmp_path)
    inbox = submit_inbox_package(panel, run_id="test-run-1", paths=paths)
    assert inbox["run_id"] == "test-run-1"
    manifest = json.loads((paths.inbox / "test-run-1" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == BRIDGE_SCHEMA_VERSION

    # simulate worker outbox
    out_dir = paths.outbox / "test-run-1"
    out_dir.mkdir(parents=True)
    metrics = {"ic": 0.05, "rank_ic": 0.04, "hit_rate_pct": 62.0, "coverage_pct": 75.0, "mean_prediction": 0.01}
    (out_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (out_dir / "model_card.json").write_text(json.dumps({"backend": "lightgbm", "label_horizon": "t2"}), encoding="utf-8")
    (out_dir / "summary.md").write_text("# summary\n量化测试摘要", encoding="utf-8")
    (out_dir / "status.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    assert "test-run-1" in list_pending_outbox(paths)
    imported = import_outbox_result("test-run-1", paths=paths)
    assert imported["imported"] is True
    assert imported["payload_for_gate"]["hit_rate_pct"] == 62.0


def test_agent_quant_context():
    ctx = build_quant_signal_context(
        metrics={"ic": 0.03, "hit_rate_pct": 58, "coverage_pct": 40, "mean_prediction": 0.01},
        model_card={"backend": "lightgbm", "feature_importance": {"ob_ask_bid_ratio": 0.2}},
        summary_md="# x\n测试摘要",
        report_direction="偏多",
    )
    assert ctx["quant_signal"]["direction"] == "bull"
    assert ctx["comparison"]["aligned"] is True
    block = format_agent_prompt_block(ctx)
    assert "量化引擎摘要" in block
