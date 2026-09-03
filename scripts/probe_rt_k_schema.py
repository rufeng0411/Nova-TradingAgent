from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe rt_k schema and check whether bid/ask depth exists.")
    parser.add_argument("--symbol", default="600519.SH", help="A-share symbol, default 600519.SH")
    parser.add_argument("--out", default="logs/rt_k_schema_probe.json", help="Output json path")
    args = parser.parse_args()

    load_dotenv()
    provider = CnTushareProvider(token=None)
    try:
        df = provider.fetch_rt_k(args.symbol)
        cols = [str(c) for c in list(df.columns)]
        depth_cols = {
            "bid_price_depth": len([c for c in cols if c.startswith("bid_price")]),
            "bid_volume_depth": len([c for c in cols if c.startswith("bid_volume")]),
            "ask_price_depth": len([c for c in cols if c.startswith("ask_price")]),
            "ask_volume_depth": len([c for c in cols if c.startswith("ask_volume")]),
        }
        has_depth10 = (
            depth_cols["bid_price_depth"] >= 10
            and depth_cols["bid_volume_depth"] >= 10
            and depth_cols["ask_price_depth"] >= 10
            and depth_cols["ask_volume_depth"] >= 10
        )
        payload = {
            "symbol": args.symbol,
            "row_count": int(len(df)),
            "columns": cols,
            "depth": depth_cols,
            "has_depth10": has_depth10,
            "decision": "use_rt_k_depth" if has_depth10 else "fallback_to_orderbook_service",
        }
    except Exception as exc:
        payload = {
            "symbol": args.symbol,
            "row_count": 0,
            "columns": [],
            "depth": {},
            "has_depth10": False,
            "decision": "fallback_to_orderbook_service",
            "error": f"{type(exc).__name__}: {exc}",
        }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
