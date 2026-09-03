#!/usr/bin/env python3
"""Export marketdata_* to Qlib-compatible CSV and dump bin."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

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


def _to_qlib_fname(symbol: str) -> str:
    s = symbol.strip().upper()
    if "." in s:
        code, exch = s.split(".", 1)
        return f"{exch.lower()}{code}"
    return s.lower()


def _load_bars(db, symbol: str, start: str, end: str) -> pd.DataFrame:
    from api.database import MarketDataDailyBarDB

    rows = (
        db.query(MarketDataDailyBarDB)
        .filter(
            MarketDataDailyBarDB.symbol == symbol,
            MarketDataDailyBarDB.trade_date >= start,
            MarketDataDailyBarDB.trade_date <= end,
        )
        .order_by(MarketDataDailyBarDB.trade_date.asc())
        .all()
    )
    if not rows:
        return pd.DataFrame()
    data = []
    for r in rows:
        factor = float(r.adj_factor) if r.adj_factor is not None else 1.0
        data.append(
            {
                "date": r.trade_date.strftime("%Y-%m-%d"),
                "open": float(r.open) if r.open is not None else None,
                "high": float(r.high) if r.high is not None else None,
                "low": float(r.low) if r.low is not None else None,
                "close": float(r.close) if r.close is not None else None,
                "volume": float(r.volume) if r.volume is not None else 0.0,
                "factor": factor,
            }
        )
    return pd.DataFrame(data)


def _merge_extras(db, symbol: str, df: pd.DataFrame, *, include_ta_factors: bool) -> pd.DataFrame:
    if df.empty or not include_ta_factors:
        return df
    from api.database import MarketDataDailyBasicDB, MarketDataMoneyflowDB, MarketDataStkFactorProDB

    out = df.copy()
    for model, cols in (
        (MarketDataStkFactorProDB, ["main_net_flow", "turnover_rate_z", "vol_ratio"]),
        (MarketDataMoneyflowDB, ["net_lg", "net_md", "net_sm"]),
        (MarketDataDailyBasicDB, ["pe", "pb", "turnover_rate"]),
    ):
        rows = (
            db.query(model)
            .filter(model.symbol == symbol)
            .filter(model.trade_date >= out["date"].min())
            .filter(model.trade_date <= out["date"].max())
            .all()
        )
        if not rows:
            continue
        ext = pd.DataFrame(
            [
                {"date": r.trade_date.strftime("%Y-%m-%d"), **{c: float(getattr(r, c)) if getattr(r, c) is not None else None for c in cols if hasattr(r, c)}}
                for r in rows
            ]
        )
        if not ext.empty:
            out = out.merge(ext, on="date", how="left")
    return out


def _resolve_symbols(universe: str, symbols_arg: str) -> list[str]:
    if symbols_arg.strip():
        return [s.strip().upper() for s in symbols_arg.split(",") if s.strip()]
    if universe == "csi300":
        import importlib.util

        uni_path = ROOT / "scripts" / "qlib" / "universe_csi300.py"
        spec = importlib.util.spec_from_file_location("universe_csi300_mod", uni_path)
        uni_mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(uni_mod)
        syms = uni_mod.load_csi300_symbols()
        if syms:
            return syms
    return DEFAULT_SYMBOLS


def _write_instruments_file(symbols: list[str], universe: str, qlib_dir: Path, start: str, end: str) -> None:
    inst_dir = qlib_dir / "instruments"
    inst_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for s in symbols:
        code = _to_qlib_fname(s)
        lines.append(f"{code}\t{start}\t{end}")
    content = "\n".join(lines) + "\n"
    # Qlib benchmark reads instruments/csi300.txt — always mirror exported symbols.
    (inst_dir / "csi300.txt").write_text(content, encoding="utf-8")
    (inst_dir / "all.txt").write_text(content, encoding="utf-8")


def export_csv(
    symbols: list[str],
    start: str,
    end: str,
    *,
    include_ta_factors: bool = False,
    include_index: bool = True,
) -> dict:
    from api.database import get_marketdata_db_ctx, init_db
    from tradingagents.qlib_eval.config import qlib_exports_csv_dir

    init_db()
    csv_dir = qlib_exports_csv_dir()
    csv_dir.mkdir(parents=True, exist_ok=True)

    export_symbols = list(symbols)
    if include_index:
        from tradingagents.qlib_eval.config import csi300_index_code

        idx = csi300_index_code()
        if idx not in export_symbols:
            export_symbols.append(idx)

    exported = []
    with get_marketdata_db_ctx() as db:
        for sym in export_symbols:
            df = _load_bars(db, sym, start, end)
            if df.empty:
                continue
            df = _merge_extras(db, sym, df, include_ta_factors=include_ta_factors)
            fname = _to_qlib_fname(sym) + ".csv"
            path = csv_dir / fname
            df.to_csv(path, index=False)
            exported.append({"symbol": sym, "file": str(path), "rows": len(df)})

    return {"csv_dir": str(csv_dir), "exported": exported, "count": len(exported)}


def dump_bin(csv_dir: Path, qlib_dir: Path) -> dict:
    dump_script = ROOT / "QLIB" / "qlib-official" / "scripts" / "dump_bin.py"
    if not dump_script.exists():
        return {"ok": False, "error": "dump_bin.py not found"}
    cmd = [
        sys.executable,
        str(dump_script),
        "dump_all",
        "--data_path",
        str(csv_dir),
        "--qlib_dir",
        str(qlib_dir),
        "--include_fields",
        "open,close,high,low,volume,factor",
        "--date_field_name",
        "date",
        "--file_suffix",
        ".csv",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def download_official_ref(target: Path) -> dict:
    try:
        from qlib.tests.data import GetData

        GetData().qlib_data(target_dir=str(target), region="cn", exists_skip=True)
        return {"ok": True, "path": str(target)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export marketdata to Qlib bin")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--universe", default=None, choices=["sample", "csi300", "custom"])
    parser.add_argument("--include-ta-factors", action="store_true")
    parser.add_argument("--skip-dump", action="store_true")
    parser.add_argument("--download-ref", action="store_true")
    args = parser.parse_args()

    from tradingagents.qlib_eval.config import (
        qlib_data_uri,
        qlib_universe,
        qlib_validation_end,
        qlib_validation_log_dir,
        qlib_validation_start,
    )

    start = args.start or qlib_validation_start()
    end = args.end or qlib_validation_end()
    universe = args.universe or qlib_universe()
    symbols = _resolve_symbols(universe, args.symbols)

    manifest: dict = {
        "start": start,
        "end": end,
        "universe": universe,
        "symbols": symbols,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    if args.download_ref:
        ref = ROOT / "data" / "qlib_cn_data_ref"
        manifest["official_ref"] = download_official_ref(ref)

    exp = export_csv(symbols, start, end, include_ta_factors=args.include_ta_factors, include_index=True)
    manifest["export"] = exp

    if exp["count"] == 0:
        manifest["warning"] = "no_csv_exported_check_backfill"
        log_dir = qlib_validation_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "export_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 1

    qlib_dir = qlib_data_uri()
    if not args.skip_dump:
        qlib_dir.mkdir(parents=True, exist_ok=True)
        manifest["dump_bin"] = dump_bin(Path(exp["csv_dir"]), qlib_dir)
        from tradingagents.qlib_eval.config import csi300_index_code

        inst_symbols = list(symbols)
        idx = csi300_index_code()
        if idx not in inst_symbols:
            inst_symbols.append(idx)
        _write_instruments_file(inst_symbols, universe, qlib_dir, start, end)

    log_dir = qlib_validation_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "export_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = manifest.get("dump_bin", {}).get("ok", True) and exp["count"] > 0
    try:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    except UnicodeEncodeError:
        print(json.dumps({"ok": ok, "count": exp["count"], "dump_ok": manifest.get("dump_bin", {}).get("ok")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
