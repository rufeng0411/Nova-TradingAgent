#!/usr/bin/env python3
"""T7: compare core Alpha158 IC vs TA-factor columns from export CSV."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

TA_FACTOR_COLS = [
    "main_net_flow",
    "turnover_rate_z",
    "vol_ratio",
    "net_lg",
    "net_md",
    "net_sm",
    "pe",
    "pb",
    "turnover_rate",
]


def _ic_from_qlib(data_uri: str) -> dict:
    import numpy as np
    import pandas as pd
    import qlib
    from qlib.config import REG_CN
    from qlib.data import D

    qlib.init(provider_uri=data_uri, region=REG_CN)
    inst = D.list_instruments(D.instruments("all"), start_time="2025-01-01", end_time="2026-05-25", as_list=True)
    if not inst:
        return {"ok": False, "error": "no_instruments"}
    sample = inst[: min(8, len(inst))]
    df = D.features(sample, ["$close"], start_time="2025-01-01", end_time="2026-05-25")
    close = df["$close"].unstack(level=0)
    signal = close.pct_change(5)
    label = close.pct_change(2).shift(-2)
    ics = []
    for dt in signal.index[-40:]:
        s = signal.loc[dt].dropna()
        y = label.loc[dt].reindex(s.index).dropna()
        idx = s.index.intersection(y.index)
        if len(idx) >= 3:
            v = float(pd.Series(s.loc[idx]).corr(pd.Series(y.loc[idx]), method="spearman"))
            if v == v:
                ics.append(v)
    return {"ok": True, "mean_ic": float(np.mean(ics)) if ics else None, "samples": len(ics)}


def _ic_from_ta_csv(csv_dir: Path) -> dict:
    import numpy as np
    import pandas as pd

    files = sorted(csv_dir.glob("*.csv"))
    if not files:
        return {"ok": False, "error": "no_csv_files"}

    per_factor: dict[str, list[float]] = {c: [] for c in TA_FACTOR_COLS}
    for fp in files[:12]:
        try:
            df = pd.read_csv(fp)
        except Exception:
            continue
        if "date" not in df.columns or "close" not in df.columns:
            continue
        df = df.sort_values("date")
        df["label_t2"] = df["close"].pct_change(2).shift(-2)
        for col in TA_FACTOR_COLS:
            if col not in df.columns:
                continue
            sig = df[col]
            lab = df["label_t2"]
            mask = sig.notna() & lab.notna()
            if mask.sum() < 20:
                continue
            ic = float(sig[mask].corr(lab[mask], method="spearman"))
            if ic == ic:
                per_factor[col].append(ic)

    summary = {}
    best = None
    for col, vals in per_factor.items():
        if not vals:
            continue
        mean_ic = float(np.mean(vals))
        summary[col] = {"mean_ic": mean_ic, "samples": len(vals)}
        if best is None or abs(mean_ic) > abs(best["mean_ic"]):
            best = {"factor": col, "mean_ic": mean_ic, "samples": len(vals)}

    return {
        "ok": bool(summary),
        "factors": summary,
        "best_factor": best,
        "csv_files_scanned": len(files),
    }


def main() -> int:
    from tradingagents.qlib_eval.config import qlib_data_uri, qlib_exports_csv_dir, qlib_validation_log_dir

    data_uri = str(qlib_data_uri().resolve())
    csv_dir = qlib_exports_csv_dir()
    core = _ic_from_qlib(data_uri)
    ta = _ic_from_ta_csv(csv_dir)

    uplift = None
    if core.get("mean_ic") is not None and ta.get("best_factor"):
        uplift = float(ta["best_factor"]["mean_ic"]) - float(core["mean_ic"])

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "note": "Alpha158TaExtra handler == Alpha158 until TA cols enter qlib bin; CSV IC is proxy",
        "core_alpha158_proxy": core,
        "ta_factor_csv": {"enabled": True, "path": str(csv_dir), **ta},
        "ic_uplift_best_ta_vs_core": uplift,
    }
    log_dir = qlib_validation_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "t7_ta_factors.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
