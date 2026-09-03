from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

from scheduler.jobs import marketdata_loop as ml

load_dotenv()


def _date_range(days: int) -> list[str]:
    today = datetime.now()
    return [
        (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(days, -1, -1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill marketdata_* tables by trade_date.")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    args = parser.parse_args()

    ts_provider = ml._build_tushare_provider()
    if ts_provider is None:
        raise SystemExit("TUSHARE_TOKEN missing")

    for trade_date in _date_range(max(args.days, 1)):
        if not ml.is_cn_trading_day(trade_date):
            continue
        print(f"[backfill] {trade_date}")
        try:
            ml._sync_daily_basic(ts_provider, trade_date)
            ml._sync_limit_list(ts_provider, trade_date)
            ml._sync_moneyflow_market(ts_provider, trade_date)
            ml._sync_margin_detail(ts_provider, trade_date)
            ml._sync_hsgt_top10(ts_provider, trade_date)
            ml._sync_top_list_and_inst(ts_provider, trade_date)
            ml._sync_stk_factor_pro_market(ts_provider, trade_date)
            ml._sync_cyq_perf_market(ts_provider, trade_date)
        except Exception as exc:
            print(f"[backfill] failed {trade_date}: {type(exc).__name__}: {exc}")
        time.sleep(max(args.sleep_sec, 0))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
