#!/usr/bin/env python3
"""Qlib local preflight: imports, init, directories."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    from tradingagents.qlib_eval.config import (
        qlib_data_uri,
        qlib_exports_csv_dir,
        qlib_validation_log_dir,
    )

    report: dict = {"ok": True, "checks": []}

    def check(name: str, fn):
        try:
            fn()
            report["checks"].append({"name": name, "ok": True})
        except Exception as exc:
            report["ok"] = False
            report["checks"].append({"name": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"})

    check("import_qlib", lambda: __import__("qlib"))
    check("import_lightgbm", lambda: __import__("lightgbm"))
    check("import_vectorbt", lambda: __import__("vectorbt"))
    check("import_scipy", lambda: __import__("scipy"))

    import qlib
    import lightgbm
    import vectorbt
    import scipy

    report["versions"] = {
        "qlib": getattr(qlib, "__version__", "unknown"),
        "lightgbm": lightgbm.__version__,
        "vectorbt": str(getattr(vectorbt, "__version__", "unknown")),
        "scipy": scipy.__version__,
    }

    data_uri = qlib_data_uri()
    csv_dir = qlib_exports_csv_dir()
    log_dir = qlib_validation_log_dir()
    for d in (data_uri, csv_dir, log_dir):
        d.mkdir(parents=True, exist_ok=True)
        test = d / ".write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink()

    report["paths"] = {
        "data_uri": str(data_uri.resolve()),
        "csv_dir": str(csv_dir.resolve()),
        "log_dir": str(log_dir.resolve()),
    }

    from qlib.config import REG_CN

    def _init_qlib():
        qlib.init(provider_uri=str(data_uri.resolve()), region=REG_CN)

    check("qlib_init", _init_qlib)

    out = log_dir / "preflight.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
