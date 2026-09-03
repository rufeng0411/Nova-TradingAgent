#!/usr/bin/env python3
"""End-to-end smoke: inbox -> worker -> outbox import (synthetic panel if DB empty)."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Enable bridge for smoke
os.environ.setdefault("TA_QLIB_EVAL_ENABLED", "1")
os.environ.setdefault("TA_QLIB_BRIDGE_ENABLED", "1")


def _synthetic_panel() -> pd.DataFrame:
    rows = []
    for i in range(12):
        rows.append(
            {
                "symbol": "600519.SH" if i % 2 == 0 else "300750.SZ",
                "trade_date": f"2026-01-{2 + (i % 5):02d}",
                "ob_ask_bid_ratio": 1.0 + (i % 3) * 0.1,
                "auc_vol_growth_pct": 0.2 + i * 0.05,
                "mf_main_net_inflow_5d": (i - 6) * 1e7,
                "label_t2": (i - 6) * 0.005,
                "feature_coverage": 0.4 + (i % 5) * 0.1,
                "release_version": "smoke",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    from tradingagents.qlib_eval.bridge.inbox import submit_inbox_package
    from tradingagents.qlib_eval.bridge.outbox import import_outbox_result
    from tradingagents.qlib_eval.config import bridge_root

    run_id = f"smoke_{uuid.uuid4().hex[:8]}"
    panel = _synthetic_panel()
    inbox = submit_inbox_package(panel, run_id=run_id)
    print("inbox:", json.dumps(inbox, ensure_ascii=False, indent=2))

    worker = Path(__file__).resolve().parents[1] / "QLIB" / "ta_bridge" / "worker.py"
    import subprocess

    rc = subprocess.call([sys.executable, str(worker), "--run-id", run_id, "--bridge-dir", str(bridge_root())])
    if rc != 0:
        return rc

    imported = import_outbox_result(run_id)
    print("import:", json.dumps({k: v for k, v in imported.items() if k != "summary_md"}, ensure_ascii=False, indent=2))
    return 0 if imported.get("imported") else 1


if __name__ == "__main__":
    sys.exit(main())
