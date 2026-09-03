#!/usr/bin/env python3
"""One-click full backtest orchestration for CSI300 Qlib pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def _run(script: str, *args: str, check: bool = True) -> int:
    cmd = [PY, str(ROOT / script), *args]
    print(f"[orchestrator] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if check and proc.returncode != 0:
        print(f"[orchestrator] failed: {script}", file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full CSI300 backtest pipeline")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Use max 20 symbols for quick path")
    args = parser.parse_args()

    steps: list[tuple[str, list[str], bool]] = [
        ("scripts/qlib/preflight_qlib.py", [], True),
        ("scripts/qlib/universe_csi300.py", [], True),
    ]
    if not args.skip_backfill:
        backfill_args = ["--max-symbols", str(args.max_symbols or (20 if args.smoke else 0))]
        if args.smoke:
            backfill_args += ["--kline-only"]
        steps.append(("scripts/qlib/bulk_backfill_csi300.py", backfill_args, not args.smoke))
    steps += [
        ("scripts/qlib/audit_marketdata.py", ["--universe", "csi300"], False),
        ("QLIB/ta_bridge/export_tushare_to_qlib.py", ["--universe", "csi300"], True),
        ("scripts/qlib/compare_ta_qlib_factors.py", ["--samples", "100"], False),
    ]
    if not args.skip_benchmark:
        steps.append(("scripts/qlib/run_benchmarks.py", ["--suite", "professional"], False))
        steps.append(("scripts/qlib/run_benchmarks.py", ["--suite", "ta_extra"], False))
        steps.append(("scripts/qlib/run_t7_ta_factors.py", [], False))
    steps.append(("scripts/qlib/bridge_e2e_smoke.py", [], False))
    steps.append(("scripts/qlib/generate_full_backtest_report.py", [], False))

    rc = 0
    for script, sargs, strict in steps:
        code = _run(script, *sargs, check=False)
        if code != 0 and strict:
            return code
        rc = rc or code
    return rc


if __name__ == "__main__":
    sys.exit(main())
