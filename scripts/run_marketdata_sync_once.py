"""
One-off market data sync for local verification (bypasses scheduler time windows).

Usage (from repo root, same Python that runs the API / with .env loaded):
  python scripts/run_marketdata_sync_once.py
  python scripts/run_marketdata_sync_once.py --no-daily
  python scripts/run_marketdata_sync_once.py --macro-only
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from tradingagents.dataflows.providers.cn_akshare_provider import CnAkshareProvider  # noqa: E402
from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider  # noqa: E402
from tradingagents.dataflows.providers.fred_provider import FredProvider  # noqa: E402
from tradingagents.dataflows.providers.juchao_provider import JuChaoProvider  # noqa: E402
from tradingagents.dataflows.providers.stats_cn_provider import StatsCnProvider  # noqa: E402
from scheduler.jobs import marketdata_loop as ml  # noqa: E402


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run marketdata upserts once.")
    parser.add_argument("--macro-only", action="store_true", help="Only macro (stats_cn + optional FRED).")
    parser.add_argument("--no-daily", action="store_true", help="Skip daily bar sync (slow).")
    parser.add_argument("--disclosure-limit", type=int, default=30, help="Max symbols for disclosure.")
    parser.add_argument(
        "--include",
        default="",
        help="Comma-separated optional sync items: daily_basic,limit_list,moneyflow,top_list,margin,hsgt_top10,stk_factor_pro,cyq_perf,fina,holdernumber",
    )
    args = parser.parse_args()
    _setup_logging()
    log = logging.getLogger("run_marketdata_sync_once")

    today = ml._today_cn()
    os.environ.setdefault("TA_DISCLOSURE_SYMBOL_LIMIT", str(max(args.disclosure_limit, 1)))

    stats_provider = StatsCnProvider()
    fred_provider = FredProvider() if (os.getenv("FRED_API_KEY") or "").strip() else None
    juchao_provider = JuChaoProvider()

    count_macro = ml._sync_macro(stats_provider, fred_provider)
    log.info("macro rows upserted: %s", count_macro)

    if args.macro_only:
        return 0

    ts_provider = ml._build_tushare_provider()
    ak_provider = CnAkshareProvider()
    if ts_provider is None:
        log.warning("TUSHARE_TOKEN missing — skipping daily/disclosure/company.")
        return 0

    count_cb = ml._sync_company_basic(ts_provider)
    log.info("company_basic rows upserted: %s", count_cb)

    symbols = ml._load_symbol_universe(ts_provider)
    if not symbols:
        symbols = ["600519.SH", "000001.SZ"]
        log.warning("symbol universe empty, using fallback: %s", symbols)

    count_disc = ml._sync_disclosure(juchao_provider, symbols, today)
    log.info("disclosure rows upserted: %s", count_disc)

    if not args.no_daily:
        compared, anomalies = ml._sync_daily_bar(ts_provider, ak_provider, today)
        log.info("daily_bar compared=%s anomalies=%s", compared, anomalies)
    else:
        log.info("skipped daily_bar (--no-daily)")

    include = {x.strip() for x in (args.include or "").split(",") if x.strip()}
    if "daily_basic" in include:
        log.info("daily_basic rows upserted: %s", ml._sync_daily_basic(ts_provider, today))
    if "limit_list" in include:
        log.info("limit_list rows upserted: %s", ml._sync_limit_list(ts_provider, today))
    if "moneyflow" in include:
        log.info("moneyflow rows upserted: %s", ml._sync_moneyflow_market(ts_provider, today))
    if "top_list" in include:
        t1, t2 = ml._sync_top_list_and_inst(ts_provider, today)
        log.info("top_list rows=%s top_inst rows=%s", t1, t2)
    if "margin" in include:
        log.info("margin_detail rows upserted: %s", ml._sync_margin_detail(ts_provider, today))
    if "hsgt_top10" in include:
        log.info("hsgt_top10 rows upserted: %s", ml._sync_hsgt_top10(ts_provider, today))
    if "stk_factor_pro" in include:
        log.info("stk_factor_pro rows upserted: %s", ml._sync_stk_factor_pro_market(ts_provider, today))
    if "cyq_perf" in include:
        log.info("cyq_perf rows upserted: %s", ml._sync_cyq_perf_market(ts_provider, today))
    if "fina" in include:
        a, b, c = ml._sync_fina_indicator_forecast_express(ts_provider, today)
        log.info("fina_indicator rows=%s forecast rows=%s express rows=%s", a, b, c)
    if "holdernumber" in include:
        log.info("holdernumber rows upserted: %s", ml._sync_holdernumber(ts_provider, today))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
