#!/usr/bin/env python3
"""Backfill marketdata for Qlib validation date range (Tushare + optional kline)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

DEFAULT_SYMBOLS = [
    "600519.SH",
    "300750.SZ",
    "000001.SZ",
    "601318.SH",
    "000858.SZ",
    "600036.SH",
    "601012.SH",
    "002594.SZ",
]


def _date_range(start: str, end: str) -> list[str]:
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    out = []
    cur = s
    while cur <= e:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill marketdata for qlib validation")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--symbols", default="", help="Comma-separated, default CSI sample")
    parser.add_argument("--sleep-sec", type=float, default=0.25)
    parser.add_argument("--kline-only", action="store_true")
    parser.add_argument("--cross-section-only", action="store_true")
    args = parser.parse_args()

    from tradingagents.qlib_eval.config import qlib_validation_end, qlib_validation_log_dir, qlib_validation_start

    start = args.start or qlib_validation_start()
    end = args.end or qlib_validation_end()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or DEFAULT_SYMBOLS

    log = {"start": start, "end": end, "symbols": symbols, "kline": {}, "cross_section_days": 0, "errors": []}

    backfill_kline = None
    if not args.cross_section_only:
        kline_path = ROOT / "scripts" / "backfill_marketdata_kline.py"
        spec = importlib.util.spec_from_file_location("backfill_kline_mod", kline_path)
        kline_mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(kline_mod)
        backfill_kline = kline_mod.backfill

    from scheduler.jobs import marketdata_loop as ml

    if not args.cross_section_only and backfill_kline is not None:
        for sym in symbols:
            try:
                n = backfill_kline(sym, start, end)
                log["kline"][sym] = n
                print(f"[kline] {sym} upserted={n}")
            except Exception as exc:
                log["errors"].append({"symbol": sym, "phase": "kline", "error": str(exc)})
            time.sleep(max(args.sleep_sec, 0))

    if not args.kline_only:
        ts = ml._build_tushare_provider()
        if ts is None:
            log["errors"].append({"phase": "cross_section", "error": "TUSHARE_TOKEN missing"})
        else:
            days = _date_range(start, end)
            for td in days:
                if not ml.is_cn_trading_day(td):
                    continue
                try:
                    ml._sync_daily_basic(ts, td)
                    ml._sync_stk_factor_pro_market(ts, td)
                    ml._sync_cyq_perf_market(ts, td)
                    ml._sync_moneyflow_market(ts, td)
                    ml._sync_limit_list(ts, td)
                    ml._sync_top_list_and_inst(ts, td)
                    log["cross_section_days"] += 1
                    if log["cross_section_days"] % 20 == 0:
                        print(f"[cross] {td} done ({log['cross_section_days']} trading days)")
                except Exception as exc:
                    log["errors"].append({"phase": "cross_section", "date": td, "error": str(exc)})
                time.sleep(max(args.sleep_sec, 0))

    log_dir = qlib_validation_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "backfill_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

    # capability probe
    try:
        import subprocess

        subprocess.run([sys.executable, str(ROOT / "scripts" / "probe_tushare_full.py")], check=False)
        src = ROOT / "logs" / "tushare_baseline.json"
        if src.exists():
            dst = log_dir / "tushare_capability.json"
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass

    print(json.dumps({"ok": len(log["errors"]) == 0, "summary": log}, ensure_ascii=False, indent=2))
    return 0 if len(log["errors"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
