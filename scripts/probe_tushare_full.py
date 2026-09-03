from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider
from tradingagents.dataflows.trade_calendar import cn_today_str, previous_cn_trading_day


def _latency(fn, *args):
    t0 = time.perf_counter()
    ok = True
    err = None
    try:
        data = fn(*args)
        rows = len(data) if hasattr(data, "__len__") else 0
    except Exception as exc:
        ok = False
        rows = 0
        err = str(exc)
    return {
        "ok": ok,
        "rows": rows,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "error": err,
    }


def main() -> None:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=True)
    p = CnTushareProvider(token=(os.getenv("TUSHARE_TOKEN") or "").strip())
    trade_date = cn_today_str()
    symbol = "600519.SH"
    day = previous_cn_trading_day(trade_date)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "trade_date": trade_date,
        "methods": {
            "rt_k": _latency(p.fetch_rt_k, [symbol]),
            "index_realtime": _latency(p.fetch_index_realtime),
            "stk_auction": _latency(p.fetch_stk_auction, symbol, trade_date),
            "stk_mins": _latency(p.fetch_stk_mins, symbol, "1min", day, trade_date),
            "moneyflow_dc": _latency(p.fetch_moneyflow_dc, symbol, day),
            "moneyflow_industry_dc": _latency(p.fetch_moneyflow_industry_dc, day),
            "stk_factor_pro": _latency(p.fetch_stk_factor_pro, symbol, day, trade_date),
            "top_list": _latency(p.fetch_top_list, day),
            "limit_list_d": _latency(p.fetch_limit_list_d, day),
            "anns_d": _latency(p.fetch_anns_d, symbol, day),
            "daily_basic": _latency(p.fetch_daily_basic, symbol, day),
        },
    }
    out_dir = Path("logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tushare_baseline.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    capability = {
        "baseline": "tushare_10000_plus + independent(rt_k, stk_auction) + akshare",
        "stk_auction": result["methods"]["stk_auction"]["ok"],
        "rt_k": result["methods"]["rt_k"]["ok"],
        "anns_d": result["methods"]["anns_d"]["ok"],
    }
    (out_dir / "tushare_capability.json").write_text(json.dumps(capability, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote logs/tushare_baseline.json and logs/tushare_capability.json")


if __name__ == "__main__":
    main()

