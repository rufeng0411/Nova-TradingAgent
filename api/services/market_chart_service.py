"""Chart-oriented Tushare data aggregation with TTL cache + singleflight."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future
from datetime import datetime, timedelta
from typing import Any, Callable

import pandas as pd

from api.symbol_utils import normalize_exchange_symbol
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.trade_calendar import cn_today_str

_cache: dict[str, tuple[float, Any]] = {}
_inflight: dict[str, Future[Any]] = {}
_lock = threading.Lock()


def _is_on(env_name: str, default: str = "0") -> bool:
    return os.getenv(env_name, default).strip().lower() in ("1", "true", "yes", "on")


def _norm_symbol(symbol: str) -> str:
    return normalize_exchange_symbol((symbol or "").strip()).upper()


def _ensure_df(result: Any) -> pd.DataFrame:
    return result if isinstance(result, pd.DataFrame) else pd.DataFrame()


def _pick_float(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for n in names:
        if n not in row:
            continue
        try:
            v = float(row[n])
            if v == v:
                return v
        except Exception:
            continue
    return None


def _with_cache(key: str, ttl: float, producer: Callable[[], Any]) -> Any:
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        future = _inflight.get(key)
        if future is None:
            future = Future()
            _inflight[key] = future
            owner = True
        else:
            owner = False
    if not owner:
        return future.result()

    try:
        value = producer()
        with _lock:
            _cache[key] = (time.time() + ttl, value)
            _inflight.pop(key, None)
        future.set_result(value)
        return value
    except Exception as exc:
        with _lock:
            _inflight.pop(key, None)
        future.set_exception(exc)
        raise


def _ymd_days_before(days: int) -> str:
    return (datetime.strptime(cn_today_str(), "%Y-%m-%d") - timedelta(days=max(1, days))).strftime("%Y-%m-%d")


def get_auction_snapshot(symbol: str) -> dict[str, Any]:
    if not _is_on("TA_TS_AUCTION_ENABLED", "0"):
        return {"enabled": False, "symbol": _norm_symbol(symbol)}
    sym = _norm_symbol(symbol)
    key = f"auction|{sym}|{cn_today_str()}"

    def _load() -> dict[str, Any]:
        df = _ensure_df(route_to_vendor("fetch_stk_auction", sym, cn_today_str()))
        if df.empty:
            return {"enabled": True, "symbol": sym, "snapshot": None}
        row = df.iloc[-1].to_dict()
        price = _pick_float(row, ("price", "close"))
        pre_close = _pick_float(row, ("pre_close",))
        gap_pct = ((price / pre_close - 1.0) * 100.0) if (price and pre_close and pre_close != 0) else None
        volume_ratio = _pick_float(row, ("volume_ratio", "vol_ratio"))
        return {
            "enabled": True,
            "symbol": sym,
            "snapshot": {
                "price": price,
                "pre_close": pre_close,
                "gap_pct": gap_pct,
                "volume_ratio": volume_ratio,
                "turnover_rate": _pick_float(row, ("turnover_rate", "turn_rate")),
                "amount": _pick_float(row, ("amount",)),
                "vol": _pick_float(row, ("vol", "volume")),
                "bull_bear_ratio": volume_ratio,
                "trade_time": str(row.get("trade_time") or row.get("trade_date") or "") or None,
            },
        }

    return _with_cache(key, ttl=5.0, producer=_load)


def get_cyq_snapshot(symbol: str, days: int = 60) -> dict[str, Any]:
    if not _is_on("TA_TS_CYQ_ENABLED", "0"):
        return {"enabled": False, "symbol": _norm_symbol(symbol), "distribution": []}
    sym = _norm_symbol(symbol)
    end = cn_today_str()
    start = _ymd_days_before(days)
    key = f"cyq|{sym}|{start}|{end}|{days}"

    def _load() -> dict[str, Any]:
        perf = _ensure_df(route_to_vendor("fetch_cyq_perf_df", sym, start, end))
        chips: pd.DataFrame = pd.DataFrame()
        trade_date = end
        if not perf.empty and "trade_date" in perf.columns:
            trade_date = str(perf["trade_date"].iloc[-1])
            if len(trade_date) == 8 and trade_date.isdigit():
                trade_date = f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        try:
            chips = _ensure_df(route_to_vendor("fetch_cyq_chips_df", sym, trade_date))
        except Exception:
            chips = pd.DataFrame()
        latest = perf.iloc[-1].to_dict() if not perf.empty else {}
        dist: list[dict[str, float]] = []
        if not chips.empty:
            for _, r in chips.tail(120).iterrows():
                rr = r.to_dict()
                p = _pick_float(rr, ("price", "cost"))
                ratio = _pick_float(rr, ("percent", "ratio", "chip", "weight"))
                if p is None or ratio is None:
                    continue
                dist.append({"price": p, "ratio": ratio})
        return {
            "enabled": True,
            "symbol": sym,
            "trade_date": trade_date,
            "summary": {
                "win_rate": _pick_float(latest, ("profit_ratio", "win_ratio", "profit_rate")),
                "locked_ratio": _pick_float(latest, ("cost_90pct", "cost_85pct", "cost_70pct")),
                "concentration": _pick_float(latest, ("cost_50pct", "cost_70pct")),
            },
            "distribution": dist,
        }

    return _with_cache(key, ttl=1800.0, producer=_load)


def get_moneyflow_series(symbol: str, days: int = 90) -> dict[str, Any]:
    if not _is_on("TA_TS_MONEYFLOW_ENABLED", "0"):
        return {"enabled": False, "symbol": _norm_symbol(symbol), "items": []}
    sym = _norm_symbol(symbol)
    end = cn_today_str()
    start = _ymd_days_before(days)
    key = f"moneyflow|{sym}|{start}|{end}|{days}"

    def _load() -> dict[str, Any]:
        df = _ensure_df(route_to_vendor("fetch_individual_moneyflow_df", sym, start, end))
        items: list[dict[str, Any]] = []
        if not df.empty:
            for _, row in df.sort_values("trade_date").iterrows():
                r = row.to_dict()
                td = str(r.get("trade_date") or "")
                if len(td) == 8 and td.isdigit():
                    td = f"{td[0:4]}-{td[4:6]}-{td[6:8]}"
                items.append(
                    {
                        "date": td,
                        "xl": _pick_float(r, ("net_mf_xl",)),
                        "l": _pick_float(r, ("net_mf_l",)),
                        "m": _pick_float(r, ("net_mf_m",)),
                        "s": _pick_float(r, ("net_mf_s",)),
                        "net": _pick_float(r, ("net_mf_amount",)),
                    }
                )
        return {"enabled": True, "symbol": sym, "items": items}

    return _with_cache(key, ttl=300.0, producer=_load)


def get_factor_pro_snapshot(symbol: str, days: int = 120) -> dict[str, Any]:
    if not _is_on("TA_TS_FACTOR_PRO_ENABLED", "0"):
        return {"enabled": False, "symbol": _norm_symbol(symbol), "snapshot": None}
    sym = _norm_symbol(symbol)
    end = cn_today_str()
    start = _ymd_days_before(days)
    key = f"factorpro|{sym}|{start}|{end}|{days}"

    def _load() -> dict[str, Any]:
        df = _ensure_df(route_to_vendor("fetch_stk_factor_pro_df", sym, start, end))
        if df.empty:
            return {"enabled": True, "symbol": sym, "snapshot": None}
        last = df.sort_values("trade_date").iloc[-1].to_dict()
        return {
            "enabled": True,
            "symbol": sym,
            "snapshot": {
                "main_net_inflow_rate": _pick_float(last, ("net_mf_main", "moneyflow_pct_value")),
                "momentum_pctile_60d": _pick_float(last, ("mom_60", "momentum_60d", "adj_factor")),
                "volatility_pctile": _pick_float(last, ("atr", "volatility", "rolling_std_20")),
                "trade_date": str(last.get("trade_date") or "") or None,
            },
        }

    return _with_cache(key, ttl=43200.0, producer=_load)


def get_daily_basic_snapshot(symbol: str, days: int = 90) -> dict[str, Any]:
    sym = _norm_symbol(symbol)
    end = cn_today_str()
    start = _ymd_days_before(days)
    key = f"dailybasic|{sym}|{start}|{end}|{days}"

    def _load() -> dict[str, Any]:
        df = _ensure_df(route_to_vendor("fetch_daily_basic_df", sym, start, end))
        if df.empty:
            return {"symbol": sym, "snapshot": None}
        last = df.sort_values("trade_date").iloc[-1].to_dict()
        return {
            "symbol": sym,
            "snapshot": {
                "trade_date": str(last.get("trade_date") or "") or None,
                "turnover_rate": _pick_float(last, ("turnover_rate", "turnover_rate_f")),
                "pe": _pick_float(last, ("pe", "pe_ttm")),
                "pb": _pick_float(last, ("pb",)),
                "total_mv": _pick_float(last, ("total_mv",)),
            },
        }

    return _with_cache(key, ttl=21600.0, producer=_load)


def get_hsgt_series(symbol: str, days: int = 90) -> dict[str, Any]:
    if not _is_on("TA_TS_HSGT_ENABLED", "0"):
        return {"enabled": False, "symbol": _norm_symbol(symbol), "items": []}
    sym = _norm_symbol(symbol)
    end = cn_today_str()
    start = _ymd_days_before(days)
    key = f"hsgt|{sym}|{start}|{end}|{days}"

    def _load() -> dict[str, Any]:
        stock_df = _ensure_df(route_to_vendor("fetch_hsgt_top10_df", sym, start, end))
        market_df = _ensure_df(route_to_vendor("fetch_north_money_df", start, end))
        items: list[dict[str, Any]] = []
        if not stock_df.empty:
            for _, row in stock_df.sort_values("trade_date").iterrows():
                r = row.to_dict()
                td = str(r.get("trade_date") or "")
                if len(td) == 8 and td.isdigit():
                    td = f"{td[0:4]}-{td[4:6]}-{td[6:8]}"
                items.append(
                    {
                        "date": td,
                        "stock_net": _pick_float(r, ("net_amount", "amount")),
                        "buy": _pick_float(r, ("buy",)),
                        "sell": _pick_float(r, ("sell",)),
                    }
                )
        market_points: list[dict[str, Any]] = []
        if not market_df.empty:
            for _, row in market_df.sort_values("trade_date").iterrows():
                r = row.to_dict()
                td = str(r.get("trade_date") or "")
                if len(td) == 8 and td.isdigit():
                    td = f"{td[0:4]}-{td[4:6]}-{td[6:8]}"
                market_points.append(
                    {
                        "date": td,
                        "north_net": _pick_float(r, ("north_money", "north_money_net", "hgt", "sgt")),
                    }
                )
        return {"enabled": True, "symbol": sym, "items": items, "market": market_points}

    return _with_cache(key, ttl=300.0, producer=_load)


def get_event_markers(symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
    sym = _norm_symbol(symbol)
    key = f"events|{sym}|{start_date}|{end_date}"

    def _load() -> dict[str, Any]:
        markers: list[dict[str, Any]] = []
        if _is_on("TA_TS_LIMIT_ENABLED", "0"):
            try:
                limit_df = _ensure_df(route_to_vendor("fetch_limit_list_d", end_date))
                if not limit_df.empty and "ts_code" in limit_df.columns:
                    limit_df = limit_df[limit_df["ts_code"].astype(str).str.upper() == sym]
                for _, row in limit_df.iterrows():
                    r = row.to_dict()
                    markers.append(
                        {
                            "type": "limit_up" if str(r.get("limit") or "").upper() != "D" else "limit_down",
                            "date": str(r.get("trade_date") or end_date),
                            "label": "涨跌停",
                            "severity": "medium",
                            "raw": r,
                        }
                    )
            except Exception:
                pass
        if _is_on("TA_TS_TOPLIST_ENABLED", "0"):
            try:
                top_df = _ensure_df(route_to_vendor("fetch_top_list_df", sym, start_date, end_date))
                for _, row in top_df.iterrows():
                    r = row.to_dict()
                    markers.append(
                        {
                            "type": "top_list",
                            "date": str(r.get("trade_date") or start_date),
                            "label": "龙虎榜",
                            "severity": "medium",
                            "raw": r,
                        }
                    )
            except Exception:
                pass
            try:
                block_df = _ensure_df(route_to_vendor("fetch_block_trade_df", sym, start_date, end_date))
                for _, row in block_df.iterrows():
                    r = row.to_dict()
                    markers.append(
                        {
                            "type": "block_trade",
                            "date": str(r.get("trade_date") or start_date),
                            "label": "大宗交易",
                            "severity": "low",
                            "raw": r,
                        }
                    )
            except Exception:
                pass
        return {"symbol": sym, "items": markers}

    return _with_cache(key, ttl=21600.0, producer=_load)


def get_corp_event_markers(symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
    if not _is_on("TA_TS_FIN_EVENT_ENABLED", "0"):
        return {"enabled": False, "symbol": _norm_symbol(symbol), "items": []}
    sym = _norm_symbol(symbol)
    key = f"corp|{sym}|{start_date}|{end_date}"

    def _date_value(row: dict[str, Any]) -> str:
        for name in ("ann_date", "trade_date", "end_date", "record_date", "ex_date"):
            v = str(row.get(name) or "").strip()
            if v:
                return v
        return start_date

    def _load() -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        loaders: list[tuple[str, str, tuple[Any, ...], str]] = [
            ("forecast", "业绩预告", ("fetch_forecast_df", sym, end_date), "high"),
            ("express", "业绩快报", ("fetch_express_df", sym, end_date), "medium"),
            ("dividend", "除权除息", ("fetch_dividend_df", sym, start_date, end_date), "medium"),
            ("holder_trade", "股东增减持", ("fetch_stk_holdertrade_df", sym, start_date, end_date), "medium"),
        ]
        for event_type, label, args, severity in loaders:
            try:
                df = _ensure_df(route_to_vendor(*args))
            except Exception:
                continue
            for _, row in df.iterrows():
                r = row.to_dict()
                items.append(
                    {
                        "type": event_type,
                        "date": _date_value(r),
                        "label": label,
                        "severity": severity,
                        "raw": r,
                    }
                )
        return {"enabled": True, "symbol": sym, "items": items}

    return _with_cache(key, ttl=86400.0, producer=_load)
