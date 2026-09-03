from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import random

import pandas as pd

from tradingagents.dataflows.providers.cn_akshare_provider import CnAkshareProvider
from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider


def _pick_symbols(ts_provider: CnTushareProvider, sample_size: int) -> list[str]:
    df = ts_provider.fetch_company_basic_df()
    if df is None or df.empty:
        return []
    symbols = [str(v).upper() for v in df.get("ts_code", pd.Series(dtype=str)).dropna().tolist()]
    if len(symbols) <= sample_size:
        return symbols
    return random.sample(symbols, sample_size)


def _latest_close(df: pd.DataFrame) -> float | None:
    if df is None or df.empty:
        return None
    val = pd.to_numeric(df.iloc[-1].get("Close"), errors="coerce")
    return float(val) if pd.notna(val) else None


def main():
    parser = argparse.ArgumentParser(description="Compare AkShare vs Tushare latest close")
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    token = input("TUSHARE_TOKEN (leave blank to use env): ").strip() or None
    ts_provider = CnTushareProvider(token=token)
    ak_provider = CnAkshareProvider()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=max(args.days, 10))).strftime("%Y-%m-%d")
    symbols = _pick_symbols(ts_provider, max(args.sample_size, 1))
    if not symbols:
        print("No symbols found")
        return

    print("symbol,ts_close,ak_close,diff_ratio")
    for sym in symbols:
        try:
            ts_df = ts_provider.fetch_daily_bar_df(sym, start_date, end_date)
            ak_df = ak_provider.fetch_daily_bar_df(sym, start_date, end_date)
            ts_close = _latest_close(ts_df)
            ak_close = _latest_close(ak_df)
            if ts_close is None or ak_close is None:
                print(f"{sym},{ts_close},{ak_close},N/A")
                continue
            diff_ratio = abs(ts_close - ak_close) / (abs(ts_close) or 1.0)
            print(f"{sym},{ts_close:.4f},{ak_close:.4f},{diff_ratio:.6f}")
        except Exception as exc:
            print(f"{sym},ERROR,ERROR,{type(exc).__name__}:{exc}")


if __name__ == "__main__":
    main()
