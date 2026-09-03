"""Import QLIB worker outbox results into main system."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.qlib_eval.bridge.contract import (
    OUTBOX_FILES,
    BridgePaths,
    outbox_dir,
    read_status,
)


def validate_outbox(run_path: Path) -> tuple[bool, list[str]]:
    missing = [f for f in OUTBOX_FILES if not (run_path / f).exists()]
    return len(missing) == 0, missing


def load_outbox_package(run_id: str, *, paths: BridgePaths | None = None) -> dict[str, Any] | None:
    from tradingagents.qlib_eval.config import bridge_root

    bp = paths or BridgePaths.from_root(bridge_root())
    run_path = outbox_dir(bp, run_id)
    if not run_path.exists():
        return None
    ok, missing = validate_outbox(run_path)
    if not ok:
        return {"run_id": run_id, "valid": False, "missing": missing}

    metrics = json.loads((run_path / "metrics.json").read_text(encoding="utf-8"))
    model_card = json.loads((run_path / "model_card.json").read_text(encoding="utf-8"))
    summary_md = (run_path / "summary.md").read_text(encoding="utf-8")
    status = read_status(run_path / "status.json")

    predictions_path = None
    for name in ("predictions.parquet", "predictions.csv"):
        p = run_path / name
        if p.exists():
            predictions_path = str(p)
            break

    return {
        "run_id": run_id,
        "valid": True,
        "outbox_dir": str(run_path),
        "status": status,
        "metrics": metrics,
        "model_card": model_card,
        "summary_md": summary_md,
        "predictions_path": predictions_path,
    }


def list_pending_outbox(paths: BridgePaths | None = None) -> list[str]:
    from tradingagents.qlib_eval.config import bridge_root

    bp = paths or BridgePaths.from_root(bridge_root())
    if not bp.outbox.exists():
        return []
    ready: list[str] = []
    for child in sorted(bp.outbox.iterdir()):
        if not child.is_dir():
            continue
        st = read_status(child / "status.json")
        if str(st.get("status") or "") == "completed":
            ok, _ = validate_outbox(child)
            if ok:
                ready.append(child.name)
    return ready


def import_outbox_result(run_id: str, *, paths: BridgePaths | None = None) -> dict[str, Any]:
    pkg = load_outbox_package(run_id, paths=paths)
    if not pkg:
        return {"run_id": run_id, "imported": False, "error": "outbox_not_found"}
    if not pkg.get("valid"):
        return {"run_id": run_id, "imported": False, "error": "outbox_invalid", "missing": pkg.get("missing")}

    metrics = dict(pkg.get("metrics") or {})
    return {
        "run_id": run_id,
        "imported": True,
        "metrics": metrics,
        "model_card": pkg.get("model_card"),
        "summary_md": pkg.get("summary_md"),
        "predictions_path": pkg.get("predictions_path"),
        "payload_for_gate": {
            "hit_rate_pct": metrics.get("hit_rate_pct"),
            "ic": metrics.get("ic"),
            "rank_ic": metrics.get("rank_ic"),
            "coverage_pct": metrics.get("coverage_pct"),
        },
    }
