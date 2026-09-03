from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

from api.database import get_marketdata_db_ctx
from api.services import market_data_service
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.default_config import DEFAULT_CONFIG


def _parse_stock_csv(raw: str) -> List[Dict[str, Any]]:
    import pandas as pd
    from io import StringIO

    text = str(raw or "")
    csv_idx = text.find("\nDate,")
    if csv_idx >= 0:
        text = text[csv_idx + 1 :]
    elif text.startswith("Date,"):
        pass
    else:
        for i, line in enumerate(text.splitlines()):
            if line.strip().startswith("Date,"):
                text = "\n".join(text.splitlines()[i:])
                break
    try:
        df = pd.read_csv(StringIO(text))
    except Exception:
        return []
    if "Date" not in df.columns:
        return []
    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        out.append(
            {
                "date": str(row.get("Date") or "")[:10],
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
                "adj_factor": row.get("AdjFactor"),
            }
        )
    return [x for x in out if x.get("date")]


def backfill(symbol: str, start: str, end: str) -> int:
    set_config(DEFAULT_CONFIG)
    raw = route_to_vendor("get_stock_data", symbol, start, end)
    candles = _parse_stock_csv(raw)
    rows: List[Dict[str, Any]] = []
    for c in candles:
        try:
            trade_date = datetime.strptime(c["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        rows.append(
            {
                "symbol": symbol.upper(),
                "trade_date": trade_date,
                "open": c.get("open"),
                "high": c.get("high"),
                "low": c.get("low"),
                "close": c.get("close"),
                "volume": c.get("volume"),
                "adj_factor": c.get("adj_factor"),
                "source_primary": "backfill_vendor",
                "recon_status": "unknown",
            }
        )
    if not rows:
        return 0
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_daily_bar_batch(db, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill marketdata_daily_bar from vendor stock_data.")
    parser.add_argument("--symbol", required=True, help="例如 600519.SH")
    parser.add_argument("--start", help="YYYY-MM-DD")
    parser.add_argument("--end", help="YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=180, help="未指定 start 时回溯天数")
    args = parser.parse_args()

    end = args.end or datetime.now().strftime("%Y-%m-%d")
    start = args.start or (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=max(7, args.days))).strftime("%Y-%m-%d")
    inserted = backfill(args.symbol.strip().upper(), start, end)
    print(f"[backfill] symbol={args.symbol} start={start} end={end} upserted={inserted}")


if __name__ == "__main__":
    main()
