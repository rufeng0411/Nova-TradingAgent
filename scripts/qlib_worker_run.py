#!/usr/bin/env python3
"""Run QLIB worker once (process pending inbox job)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    worker = Path(__file__).resolve().parents[1] / "QLIB" / "ta_bridge" / "worker.py"
    return subprocess.call([sys.executable, str(worker), "--once"] + sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
