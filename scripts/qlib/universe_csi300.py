#!/usr/bin/env python3
"""Fetch CSI300 historical constituent union via Tushare index_weight."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

CSI300_INDEX = "000300.SH"


def _to_qlib_code(ts_code: str) -> str:
    s = ts_code.strip().upper()
    if "." in s:
        code, exch = s.split(".", 1)
        return f"{exch.lower()}{code}"
    return s.lower()


def _instruments_lines(symbols: list[str], start: str, end: str) -> list[str]:
    return [f"{_to_qlib_code(s)}\t{start}\t{end}" for s in symbols]


def fetch_csi300_universe(start: str, end: str, index_code: str = CSI300_INDEX) -> dict:
    token = (os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        raise SystemExit("TUSHARE_TOKEN missing")

    import pandas as pd
    import tushare as ts

    pro = ts.pro_api(token)
    start_ymd = start.replace("-", "")
    end_ymd = end.replace("-", "")

    frames = []
    for api_name, kwargs in (
        ("index_weight", {"index_code": index_code, "start_date": start_ymd, "end_date": end_ymd}),
        ("index_member", {"index_code": index_code, "is_new": "Y"}),
    ):
        fn = getattr(pro, api_name, None)
        if fn is None:
            continue
        try:
            df = fn(**kwargs)
            if df is not None and not df.empty:
                frames.append(df)
        except Exception as exc:
            print(f"[universe] {api_name} failed: {exc}")

    if not frames:
        raise SystemExit("index_weight/index_member returned no rows")

    all_df = pd.concat(frames, ignore_index=True)
    code_col = "con_code" if "con_code" in all_df.columns else "ts_code"
    if code_col not in all_df.columns:
        raise SystemExit(f"unexpected columns: {list(all_df.columns)}")

    symbols = sorted({str(v).strip().upper() for v in all_df[code_col].dropna().tolist() if str(v).strip()})
    qlib_codes = [_to_qlib_code(s) for s in symbols]

    membership = []
    if "trade_date" in all_df.columns:
        for _, row in all_df.iterrows():
            sym = str(row.get(code_col) or "").strip().upper()
            if not sym:
                continue
            td = row.get("trade_date")
            membership.append({"symbol": sym, "trade_date": str(td), "weight": row.get("weight")})

    return {
        "index_code": index_code,
        "start": start,
        "end": end,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "qlib_codes": qlib_codes,
        "membership_rows": len(membership),
        "membership_sample": membership[:20],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def write_universe_files(payload: dict, out_dir: Path, *, start: str, end: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / "csi300.txt"
    meta_path = out_dir / "csi300_meta.json"
    ts_symbols_path = out_dir / "csi300_ts_symbols.json"

    lines = _instruments_lines(payload["symbols"], start, end)
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ts_symbols_path.write_text(json.dumps(payload["symbols"], ensure_ascii=False, indent=2), encoding="utf-8")

    qlib_data = ROOT / "data" / "qlib_cn_data" / "instruments"
    qlib_data.mkdir(parents=True, exist_ok=True)
    (qlib_data / "csi300.txt").write_text(txt_path.read_text(encoding="utf-8"), encoding="utf-8")

    return {"txt": str(txt_path), "meta": str(meta_path), "symbols_json": str(ts_symbols_path)}


def load_csi300_symbols() -> list[str]:
    from tradingagents.qlib_eval.config import csi300_index_code, qlib_exports_universe_dir

    path = qlib_exports_universe_dir() / "csi300_ts_symbols.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CSI300 universe files")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--index-code", default=CSI300_INDEX)
    args = parser.parse_args()

    from tradingagents.qlib_eval.config import csi300_index_code, qlib_exports_universe_dir, qlib_validation_end, qlib_validation_start

    start = args.start or qlib_validation_start()
    end = args.end or qlib_validation_end()
    index_code = args.index_code or csi300_index_code()

    payload = fetch_csi300_universe(start, end, index_code=index_code)
    paths = write_universe_files(payload, qlib_exports_universe_dir(), start=start, end=end)
    payload["files"] = paths
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["symbol_count"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
