from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Callable

import pandas as pd

from api.database import (
    MarketDataDailyBarDB,
    MarketDataDailyBasicDB,
    MarketDataMoneyflowDB,
    MarketDataMarginDetailDB,
    MarketDataHsgtTop10DB,
    MarketDataTopListDB,
    MarketDataStkFactorProDB,
    MarketDataCyqPerfDB,
    MarketDataFinaIndicatorDB,
    MarketDataForecastDB,
    MarketDataExpressDB,
    MarketDataHolderNumberDB,
    get_marketdata_db_ctx,
    is_marketdata_db_healthy,
)

from .interface import route_to_vendor


def _enabled() -> bool:
    tier3 = os.getenv("TA_DATASOURCE_TIER3_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    local_first = os.getenv("TA_DATASOURCE_LOCAL_FIRST", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    return tier3 and local_first


def _estimate_expected_rows(start_date: str, end_date: str) -> int:
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = max(0, (end_dt - start_dt).days + 1)
        # Trading days are usually about 5/7 of natural days.
        return max(1, int(days * 5 / 7))
    except Exception:
        return 0


def _local_get_stock_data(symbol: str, start_date: str, end_date: str) -> str | None:
    try:
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return None

    if not is_marketdata_db_healthy():
        return None

    with get_marketdata_db_ctx() as db:
        rows = (
            db.query(MarketDataDailyBarDB)
            .filter(
                MarketDataDailyBarDB.symbol == symbol.strip().upper(),
                MarketDataDailyBarDB.trade_date >= start_d,
                MarketDataDailyBarDB.trade_date <= end_d,
                MarketDataDailyBarDB.recon_status != "mismatch",
            )
            .order_by(MarketDataDailyBarDB.trade_date.asc())
            .all()
        )
        if not rows:
            return None

    expected = _estimate_expected_rows(start_date, end_date)
    if expected and len(rows) < max(1, int(expected * 0.8)):
        return None

    data = pd.DataFrame(
        [
            {
                "Date": r.trade_date.strftime("%Y-%m-%d") if r.trade_date else None,
                "Open": float(r.open) if r.open is not None else None,
                "High": float(r.high) if r.high is not None else None,
                "Low": float(r.low) if r.low is not None else None,
                "Close": float(r.close) if r.close is not None else None,
                "Volume": float(r.volume) if r.volume is not None else None,
                "Amount": float(r.amount) if r.amount is not None else None,
                "AdjFactor": float(r.adj_factor) if r.adj_factor is not None else None,
            }
            for r in rows
        ]
    )
    header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += "# Source: local marketdata_daily_bar\n\n"
    return header + data.to_csv(index=False)


def _local_query_table(model, symbol: str, start_date: str, end_date: str, date_field: str = "trade_date") -> str | None:
    if not is_marketdata_db_healthy():
        return None
    try:
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    with get_marketdata_db_ctx() as db:
        col = getattr(model, date_field)
        rows = (
            db.query(model)
            .filter(
                model.symbol == symbol.strip().upper(),
                col >= start_d,
                col <= end_d,
            )
            .order_by(col.asc())
            .limit(120)
            .all()
        )
    if not rows:
        return None
    data = pd.DataFrame(
        [{k: v for k, v in r.__dict__.items() if not k.startswith("_")} for r in rows]
    )
    return data.to_csv(index=False)


def _local_get_daily_basic(symbol: str, start_date: str, end_date: str) -> str | None:
    return _local_query_table(MarketDataDailyBasicDB, symbol, start_date, end_date)


def _local_get_moneyflow(symbol: str, start_date: str, end_date: str) -> str | None:
    return _local_query_table(MarketDataMoneyflowDB, symbol, start_date, end_date)


def _local_get_margin(symbol: str, start_date: str, end_date: str) -> str | None:
    return _local_query_table(MarketDataMarginDetailDB, symbol, start_date, end_date)


def _local_get_hsgt_top10(symbol: str, start_date: str, end_date: str) -> str | None:
    return _local_query_table(MarketDataHsgtTop10DB, symbol, start_date, end_date)


def _local_get_top_list(symbol: str, start_date: str, end_date: str) -> str | None:
    return _local_query_table(MarketDataTopListDB, symbol, start_date, end_date)


def _local_get_factor(symbol: str, start_date: str, end_date: str) -> str | None:
    return _local_query_table(MarketDataStkFactorProDB, symbol, start_date, end_date)


def _local_get_cyq_perf(symbol: str, start_date: str, end_date: str) -> str | None:
    return _local_query_table(MarketDataCyqPerfDB, symbol, start_date, end_date)


def _local_get_fina_indicator(symbol: str, curr_date: str = "") -> str | None:
    end_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    return _local_query_table(MarketDataFinaIndicatorDB, symbol, start_date, end_date, date_field="end_date")


def _local_get_forecast(symbol: str, curr_date: str = "") -> str | None:
    end_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=365 * 2)).strftime("%Y-%m-%d")
    return _local_query_table(MarketDataForecastDB, symbol, start_date, end_date, date_field="end_date")


def _local_get_express(symbol: str, curr_date: str = "") -> str | None:
    end_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=365 * 2)).strftime("%Y-%m-%d")
    return _local_query_table(MarketDataExpressDB, symbol, start_date, end_date, date_field="end_date")


def _local_get_holdernumber(symbol: str, curr_date: str = "") -> str | None:
    end_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    return _local_query_table(MarketDataHolderNumberDB, symbol, start_date, end_date, date_field="end_date")


LOCAL_FIRST_HANDLERS: dict[str, Callable[..., Any]] = {
    "get_stock_data": _local_get_stock_data,
    "get_daily_basic": _local_get_daily_basic,
    "get_individual_money_flow_detail": _local_get_moneyflow,
    "get_margin_detail": _local_get_margin,
    "get_hsgt_top10": _local_get_hsgt_top10,
    "get_top_list_history": _local_get_top_list,
    "get_stk_factor_pro_window": _local_get_factor,
    "get_cyq_perf": _local_get_cyq_perf,
    "get_fina_indicator": _local_get_fina_indicator,
    "get_forecast": _local_get_forecast,
    "get_express": _local_get_express,
    "get_holdernumber_series": _local_get_holdernumber,
}


def route_with_local_first(method: str, *args, **kwargs):
    if _enabled():
        handler = LOCAL_FIRST_HANDLERS.get(method)
        if handler:
            try:
                result = handler(*args, **kwargs)
                if result is not None:
                    return result
            except Exception:
                pass
    return route_to_vendor(method, *args, **kwargs)

