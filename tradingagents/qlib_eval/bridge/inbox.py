"""Submit feature/label packages to qlib_bridge inbox."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from tradingagents.qlib_eval.bridge.contract import (
    BRIDGE_SCHEMA_VERSION,
    BridgePaths,
    InboxManifest,
    inbox_dir,
    write_status,
)
from tradingagents.qlib_eval.config import bridge_root, release_version
from tradingagents.qlib_eval.schema import all_feature_names


def _provenance_from_panel(panel: pd.DataFrame) -> dict[str, Any]:
    feature_cols = [c for c in all_feature_names() if c in panel.columns]
    coverage: dict[str, float] = {}
    for col in feature_cols:
        if panel.empty:
            coverage[col] = 0.0
        else:
            coverage[col] = float(panel[col].notna().mean())
    return {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "feature_columns": feature_cols,
        "field_coverage": coverage,
        "avg_feature_coverage": float(panel["feature_coverage"].mean()) if "feature_coverage" in panel.columns and not panel.empty else None,
        "sources": {
            "derived_signals": [c for c in feature_cols if not c.startswith("md_")],
            "marketdata": [c for c in feature_cols if c.startswith("md_")],
        },
    }


def submit_inbox_package(
    panel: pd.DataFrame,
    *,
    run_id: str,
    label_horizon: str = "t2",
    paths: BridgePaths | None = None,
) -> dict[str, Any]:
    """Write inbox task package for QLIB worker."""
    bp = paths or BridgePaths.from_root(bridge_root())
    bp.ensure()
    run_path = inbox_dir(bp, run_id)
    run_path.mkdir(parents=True, exist_ok=True)

    csv_name = "feature_label_panel.csv"
    csv_path = run_path / csv_name
    panel.to_csv(csv_path, index=False, encoding="utf-8-sig")

    parquet_path = run_path / "feature_label_panel.parquet"
    parquet_rel: str | None = None
    try:
        panel.to_parquet(parquet_path, index=False)
        parquet_rel = parquet_path.name
    except Exception:
        parquet_path = None

    provenance = _provenance_from_panel(panel)
    (run_path / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    symbols = panel["symbol"].nunique() if "symbol" in panel.columns and not panel.empty else 0
    date_min = str(panel["trade_date"].min()) if "trade_date" in panel.columns and not panel.empty else None
    date_max = str(panel["trade_date"].max()) if "trade_date" in panel.columns and not panel.empty else None

    manifest = InboxManifest(
        run_id=run_id,
        release_version=release_version(),
        label_horizon=label_horizon,
        rows=int(len(panel)),
        symbol_count=int(symbols),
        date_range={"start": date_min, "end": date_max},
        feature_panel_csv=csv_name,
        feature_panel_parquet=parquet_rel,
        sources=provenance.get("sources") or {},
    )
    (run_path / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_status(run_path / "status.json", "pending", run_id=run_id)

    return {
        "run_id": run_id,
        "inbox_dir": str(run_path),
        "manifest": manifest.to_dict(),
        "provenance": provenance,
        "rows": int(len(panel)),
    }


def list_pending_inbox(paths: BridgePaths | None = None) -> list[str]:
    bp = paths or BridgePaths.from_root(bridge_root())
    if not bp.inbox.exists():
        return []
    pending: list[str] = []
    for child in sorted(bp.inbox.iterdir()):
        if not child.is_dir():
            continue
        st = json.loads((child / "status.json").read_text(encoding="utf-8")) if (child / "status.json").exists() else {}
        if str(st.get("status") or "pending") == "pending":
            pending.append(child.name)
    return pending
