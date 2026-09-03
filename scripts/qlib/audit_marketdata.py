#!/usr/bin/env python3
"""Audit marketdata_* coverage for Qlib validation window."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

DEFAULT_SYMBOLS = ["600519.SH", "300750.SZ", "000001.SZ", "601318.SH", "000858.SZ"]
MIN_COVERAGE_PCT = 95.0


def _load_csi300_symbols() -> list[str]:
    uni_path = ROOT / "scripts" / "qlib" / "universe_csi300.py"
    spec = importlib.util.spec_from_file_location("universe_csi300_mod", uni_path)
    uni_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(uni_mod)
    return uni_mod.load_csi300_symbols()


def _count_table(db, model, start: str, end: str, symbols: list[str] | None = None) -> dict:
    from sqlalchemy import func

    q = db.query(func.count()).select_from(model).filter(
        model.trade_date >= start,
        model.trade_date <= end,
    )
    if symbols and hasattr(model, "symbol"):
        q = q.filter(model.symbol.in_(symbols))
    total = int(q.scalar() or 0)
    sym_q = db.query(model.symbol).filter(model.trade_date >= start, model.trade_date <= end)
    if symbols:
        sym_q = sym_q.filter(model.symbol.in_(symbols))
    distinct_symbols = len({r[0] for r in sym_q.distinct().all()})
    return {"rows": total, "symbols": distinct_symbols}


def _coverage_daily_bar(db, model, symbols: list[str], start: str, end: str) -> dict:
    from sqlalchemy import and_, func

    per_symbol = []
    for sym in symbols:
        cnt = (
            db.query(func.count())
            .select_from(model)
            .filter(
                and_(
                    model.symbol == sym,
                    model.trade_date >= start,
                    model.trade_date <= end,
                    model.close.isnot(None),
                    model.volume.isnot(None),
                )
            )
            .scalar()
            or 0
        )
        adj_cnt = (
            db.query(func.count())
            .select_from(model)
            .filter(
                and_(
                    model.symbol == sym,
                    model.trade_date >= start,
                    model.trade_date <= end,
                    model.adj_factor.isnot(None),
                )
            )
            .scalar()
            or 0
        )
        per_symbol.append({"symbol": sym, "rows": int(cnt), "adj_factor_rows": int(adj_cnt)})

    with_rows = sum(1 for x in per_symbol if x["rows"] > 0)
    coverage_pct = round(100.0 * with_rows / max(1, len(symbols)), 2)
    return {
        "symbols_total": len(symbols),
        "symbols_with_data": with_rows,
        "coverage_pct": coverage_pct,
        "pass": coverage_pct >= MIN_COVERAGE_PCT,
        "per_symbol_sample": per_symbol[:10],
    }


def run_audit(*, universe: str, start: str, end: str, test_start: str | None = None) -> dict:
    from api.database import (
        MarketDataCyqPerfDB,
        MarketDataDailyBarDB,
        MarketDataDailyBasicDB,
        MarketDataMoneyflowDB,
        MarketDataStkFactorProDB,
        get_marketdata_db_ctx,
        init_db,
    )

    init_db()
    if universe == "csi300":
        symbols = _load_csi300_symbols() or DEFAULT_SYMBOLS
    else:
        symbols = DEFAULT_SYMBOLS

    test_window_start = test_start or start
    with get_marketdata_db_ctx() as db:
        audit = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "universe": universe,
            "window": {"start": start, "end": end},
            "test_window": {"start": test_window_start, "end": end},
            "universe_symbols": len(symbols),
            "tables": {
                "daily_bar": _count_table(db, MarketDataDailyBarDB, start, end, symbols),
                "daily_basic": _count_table(db, MarketDataDailyBasicDB, start, end, symbols),
                "stk_factor_pro": _count_table(db, MarketDataStkFactorProDB, start, end, symbols),
                "moneyflow": _count_table(db, MarketDataMoneyflowDB, start, end, symbols),
                "cyq_perf": _count_table(db, MarketDataCyqPerfDB, start, end, symbols),
            },
            "coverage": {
                "full_window": _coverage_daily_bar(db, MarketDataDailyBarDB, symbols, start, end),
                "test_window": _coverage_daily_bar(db, MarketDataDailyBarDB, symbols, test_window_start, end),
            },
        }
    audit["gate_pass"] = audit["coverage"]["test_window"].get("pass", False)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit marketdata coverage")
    parser.add_argument("--universe", default=None, choices=["sample", "csi300"])
    args = parser.parse_args()

    from tradingagents.qlib_eval.config import (
        qlib_universe,
        qlib_validation_end,
        qlib_validation_log_dir,
        qlib_validation_start,
        qlib_validation_test_start,
    )

    universe = args.universe or qlib_universe()
    start = qlib_validation_start()
    end = qlib_validation_end()
    audit = run_audit(universe=universe, start=start, end=end, test_start=qlib_validation_test_start())

    log_dir = qlib_validation_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    out_name = "marketdata_audit_csi300.json" if universe == "csi300" else "marketdata_audit.json"
    out = log_dir / out_name
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (log_dir / "marketdata_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit.get("gate_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
