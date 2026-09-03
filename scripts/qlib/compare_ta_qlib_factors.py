#!/usr/bin/env python3
"""Compare TA exported CSV values vs Qlib D.features sample alignment."""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare TA CSV vs Qlib features")
    parser.add_argument("--samples", type=int, default=100)
    args = parser.parse_args()

    from tradingagents.qlib_eval.config import qlib_data_uri, qlib_exports_csv_dir, qlib_validation_log_dir

    csv_dir = qlib_exports_csv_dir()
    data_uri = str(qlib_data_uri().resolve())
    files = list(csv_dir.glob("*.csv"))
    if not files:
        print(json.dumps({"ok": False, "error": "no_csv_files"}, ensure_ascii=False))
        return 1

    import qlib
    from qlib.config import REG_CN
    from qlib.data import D
    from qlib.utils import fname_to_code

    qlib.init(provider_uri=data_uri, region=REG_CN)

    sample_n = min(max(args.samples, 1), 500)
    samples = []
    attempts = 0
    while len(samples) < sample_n and attempts < sample_n * 3:
        attempts += 1
        fp = random.choice(files)
        ta_df = pd.read_csv(fp)
        if ta_df.empty:
            continue
        code = fname_to_code(fp.stem.lower())
        row = ta_df.sample(1).iloc[0]
        dt = str(row["date"])[:10]
        try:
            q = D.features([code], ["$close", "$open", "$high", "$low", "$volume"], start_time=dt, end_time=dt)
            if q is None or q.empty:
                samples.append({"file": fp.name, "date": dt, "aligned": False, "reason": "qlib_empty"})
                continue
            q_close = float(q["$close"].iloc[0])
            ta_close = float(row["close"])
            diff = abs(q_close - ta_close)
            samples.append(
                {
                    "file": fp.name,
                    "code": code,
                    "date": dt,
                    "ta_close": ta_close,
                    "qlib_close": q_close,
                    "abs_diff": diff,
                    "aligned": diff <= 1e-4,
                }
            )
        except Exception as exc:
            samples.append({"file": fp.name, "date": dt, "aligned": False, "error": str(exc)})

    aligned = sum(1 for s in samples if s.get("aligned"))
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "samples": samples,
        "sample_count": len(samples),
        "aligned_rate": aligned / max(1, len(samples)),
        "price_tolerance": 1e-4,
    }
    log_dir = qlib_validation_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "factor_compare.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["aligned_rate"] >= 0.99 else 1


if __name__ == "__main__":
    sys.exit(main())
