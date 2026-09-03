#!/usr/bin/env python3
"""Bridge E2E smoke: synthetic panel submit -> worker -> import."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _load_csi300_sample_symbols(n: int = 4) -> list[str]:
    meta_path = ROOT / "data" / "qlib_exports" / "universe" / "csi300_ts_symbols.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            syms = data if isinstance(data, list) else data.get("symbols") or []
            if syms:
                return [str(s) for s in syms[:n]]
        except Exception:
            pass
    return ["600519.SH", "300750.SZ", "000001.SZ", "601318.SH"]


def _synthetic_panel(rows: int = 120) -> pd.DataFrame:
    from tradingagents.qlib_eval.schema import all_feature_names

    syms = _load_csi300_sample_symbols(4)
    dates = pd.date_range("2025-01-01", periods=30, freq="B")
    records = []
    for i in range(rows):
        sym = syms[i % len(syms)]
        dt = dates[i % len(dates)]
        rec = {"symbol": sym, "trade_date": dt.strftime("%Y-%m-%d")}
        for f in all_feature_names():
            rec[f] = float((hash(f"{sym}-{dt}-{f}") % 1000) / 1000.0)
        rec["label_t2"] = float(((hash(sym + str(dt)) % 200) - 100) / 10000.0)
        records.append(rec)
    return pd.DataFrame(records)


def main() -> int:
    os.environ.setdefault("TA_QLIB_EVAL_ENABLED", "1")
    os.environ.setdefault("TA_QLIB_BRIDGE_ENABLED", "1")

    from tradingagents.qlib_eval.bridge.contract import BridgePaths, InboxManifest, inbox_dir, write_status
    from tradingagents.qlib_eval.config import bridge_root, qlib_validation_log_dir

    import importlib.util

    worker_path = ROOT / "QLIB" / "ta_bridge" / "worker.py"
    spec = importlib.util.spec_from_file_location("qlib_worker_mod", worker_path)
    worker_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(worker_mod)

    run_id = f"e2e_{uuid.uuid4().hex[:10]}"
    paths = BridgePaths.from_root(bridge_root())
    paths.ensure()
    in_path = inbox_dir(paths, run_id)
    in_path.mkdir(parents=True, exist_ok=True)

    csv_name = "feature_label_panel.csv"
    panel = _synthetic_panel()
    panel.to_csv(in_path / csv_name, index=False, encoding="utf-8-sig")
    manifest = InboxManifest(
        run_id=run_id,
        release_version="e2e",
        label_horizon="t2",
        rows=len(panel),
        symbol_count=int(panel["symbol"].nunique()),
        feature_panel_csv=csv_name,
        provenance_file="provenance.json",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    (in_path / "manifest.json").write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (in_path / "provenance.json").write_text(json.dumps({"source": "bridge_e2e_smoke"}, ensure_ascii=False), encoding="utf-8")
    write_status(in_path / "status.json", "pending", run_id=run_id)

    out = worker_mod.process_run(run_id, paths)
    report = {"run_id": run_id, "worker": out}

    log_dir = qlib_validation_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "bridge_e2e_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if out.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
