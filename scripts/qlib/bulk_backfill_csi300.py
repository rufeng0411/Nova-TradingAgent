#!/usr/bin/env python3
"""Bulk backfill CSI300 universe: kline+adj_factor, index benchmark, cross-section factors."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _load_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {"kline_done": [], "index_done": False, "cross_section_days": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"kline_done": [], "index_done": False, "cross_section_days": []}


def _save_checkpoint(path: Path, ckpt: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2), encoding="utf-8")


def _date_range(start: str, end: str) -> list[str]:
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    out = []
    cur = s
    while cur <= e:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def _backfill_symbol_kline(ts, symbol: str, start: str, end: str) -> int:
    from api.database import get_marketdata_db_ctx
    from api.services import market_data_service

    df = ts.fetch_daily_bar_df(symbol, start, end, adjust="none")
    if df is None or df.empty:
        return 0
    rows = []
    for _, row in df.iterrows():
        dt = row.get("Date")
        if dt is None:
            continue
        trade_date = dt.date() if hasattr(dt, "date") else datetime.strptime(str(dt)[:10], "%Y-%m-%d").date()
        rows.append(
            {
                "symbol": symbol.upper(),
                "trade_date": trade_date,
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
                "amount": row.get("Amount"),
                "adj_factor": row.get("AdjFactor"),
                "source_primary": "cn_tushare",
                "recon_status": "unknown",
            }
        )
    if not rows:
        return 0
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_daily_bar_batch(db, rows)


def _backfill_index_daily(ts, index_code: str, start: str, end: str) -> int:
    import pandas as pd
    from api.database import get_marketdata_db_ctx
    from api.services import market_data_service

    pro = ts._pro()
    start_ymd = start.replace("-", "")
    end_ymd = end.replace("-", "")
    df = ts._call(pro.index_daily, ts_code=index_code, start_date=start_ymd, end_date=end_ymd)
    if df is None or df.empty:
        return 0
    rows = []
    for _, row in df.iterrows():
        dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
        if pd.isna(dt):
            continue
        rows.append(
            {
                "symbol": index_code.upper(),
                "trade_date": dt.date(),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("vol"),
                "amount": row.get("amount"),
                "adj_factor": 1.0,
                "source_primary": "cn_tushare_index",
                "recon_status": "unknown",
            }
        )
    if not rows:
        return 0
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_daily_bar_batch(db, rows)


def _sync_cross_section_day(ts, symbols: list[str], trade_date: str) -> dict:
    import pandas as pd
    from api.database import get_marketdata_db_ctx
    from api.services import market_data_service

    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    basic_rows: list[dict] = []
    factor_rows: list[dict] = []
    flow_rows: list[dict] = []

    for symbol in symbols:
        try:
            db_df = ts.fetch_daily_basic_df(symbol, start_date, trade_date)
            if db_df is not None and not db_df.empty:
                for _, row in db_df.iterrows():
                    dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
                    if pd.isna(dt) or dt.strftime("%Y-%m-%d") != trade_date:
                        continue
                    basic_rows.append(
                        {
                            "symbol": symbol,
                            "trade_date": dt.date(),
                            "pe": row.get("pe"),
                            "pb": row.get("pb"),
                            "turnover_rate": row.get("turnover_rate"),
                            "source_primary": "cn_tushare",
                        }
                    )
        except Exception:
            pass
        try:
            fp_df = ts.fetch_stk_factor_pro_df(symbol, start_date, trade_date)
            if fp_df is not None and not fp_df.empty:
                for _, row in fp_df.iterrows():
                    dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
                    if pd.isna(dt) or dt.strftime("%Y-%m-%d") != trade_date:
                        continue
                    factor_rows.append(
                        {
                            "symbol": symbol,
                            "trade_date": dt.date(),
                            "main_net_flow": row.get("main_net_flow"),
                            "turnover_rate_z": row.get("turnover_rate_z"),
                            "vol_ratio": row.get("vol_ratio"),
                            "source_primary": "cn_tushare",
                        }
                    )
        except Exception:
            pass
        try:
            mf_df = ts.fetch_individual_moneyflow_df(symbol, start_date, trade_date)
            if mf_df is not None and not mf_df.empty:
                for _, row in mf_df.iterrows():
                    dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
                    if pd.isna(dt) or dt.strftime("%Y-%m-%d") != trade_date:
                        continue
                    flow_rows.append(
                        {
                            "symbol": symbol,
                            "trade_date": dt.date(),
                            "net_lg": row.get("net_lg_amount"),
                            "net_md": row.get("net_md_amount"),
                            "net_sm": row.get("net_sm_amount"),
                            "source_primary": "cn_tushare",
                        }
                    )
        except Exception:
            pass

    counts = {"daily_basic": 0, "stk_factor_pro": 0, "moneyflow": 0}
    with get_marketdata_db_ctx() as db:
        if basic_rows:
            counts["daily_basic"] = market_data_service.upsert_daily_basic_batch(db, basic_rows)
        if factor_rows:
            counts["stk_factor_pro"] = market_data_service.upsert_stk_factor_pro_batch(db, factor_rows)
        if flow_rows:
            counts["moneyflow"] = market_data_service.upsert_moneyflow_batch(db, flow_rows)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk backfill CSI300 data")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-symbols", type=int, default=0, help="0 = all universe")
    parser.add_argument("--sleep-sec", type=float, default=0.15)
    parser.add_argument("--kline-only", action="store_true")
    parser.add_argument("--cross-section-only", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--test-window-only", action="store_true", help="Cross-section only for test window")
    args = parser.parse_args()

    from tradingagents.qlib_eval.config import (
        backfill_checkpoint_path,
        csi300_index_code,
        qlib_validation_end,
        qlib_validation_start,
        qlib_validation_test_start,
    )
    from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider
    from scheduler.jobs import marketdata_loop as ml

    start = args.start or qlib_validation_start()
    end = args.end or qlib_validation_end()
    test_start = qlib_validation_test_start()
    index_code = csi300_index_code()

    token = (os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        print(json.dumps({"ok": False, "error": "TUSHARE_TOKEN missing"}, ensure_ascii=False))
        return 1

    import importlib.util

    uni_path = ROOT / "scripts" / "qlib" / "universe_csi300.py"
    spec = importlib.util.spec_from_file_location("universe_csi300_mod", uni_path)
    uni_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(uni_mod)
    load_csi300_symbols = uni_mod.load_csi300_symbols

    symbols = load_csi300_symbols()
    if not symbols:
        print("[bulk] universe missing, run universe_csi300.py first", file=sys.stderr)
        return 1
    if args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]

    ts = CnTushareProvider(token=token)
    ckpt_path = backfill_checkpoint_path()
    ckpt = _load_checkpoint(ckpt_path)
    log = {"start": start, "end": end, "symbols": len(symbols), "kline": {}, "index": 0, "cross_section": {}, "errors": []}

    if not args.cross_section_only:
        for sym in symbols:
            if sym in ckpt.get("kline_done", []):
                continue
            try:
                n = _backfill_symbol_kline(ts, sym, start, end)
                log["kline"][sym] = n
                ckpt.setdefault("kline_done", []).append(sym)
                _save_checkpoint(ckpt_path, ckpt)
                if len(log["kline"]) % 20 == 0:
                    print(f"[kline] progress {len(log['kline'])}/{len(symbols)}")
            except Exception as exc:
                log["errors"].append({"symbol": sym, "phase": "kline", "error": str(exc)})
            time.sleep(max(args.sleep_sec, 0))

        if not args.skip_index and not ckpt.get("index_done"):
            try:
                log["index"] = _backfill_index_daily(ts, index_code, start, end)
                ckpt["index_done"] = True
                _save_checkpoint(ckpt_path, ckpt)
            except Exception as exc:
                log["errors"].append({"phase": "index", "error": str(exc)})

    if not args.kline_only:
        cs_start = test_start if args.test_window_only else start
        done_days = set(ckpt.get("cross_section_days") or [])
        for td in _date_range(cs_start, end):
            if not ml.is_cn_trading_day(td):
                continue
            if td in done_days:
                continue
            try:
                counts = _sync_cross_section_day(ts, symbols, td)
                log["cross_section"][td] = counts
                ckpt.setdefault("cross_section_days", []).append(td)
                _save_checkpoint(ckpt_path, ckpt)
                if len(log["cross_section"]) % 10 == 0:
                    print(f"[cross] {td} done ({len(log['cross_section'])} days)")
            except Exception as exc:
                log["errors"].append({"phase": "cross_section", "date": td, "error": str(exc)})
            time.sleep(max(args.sleep_sec, 0))

    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    (ckpt_path.parent / "backfill_log_csi300.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": len(log["errors"]) == 0, "summary": log}, ensure_ascii=False, indent=2))
    return 0 if len(log["errors"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
