"""Realtime daily-k snapshots backed by Tushare `rt_k`."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any

import pandas as pd

from api.symbol_utils import normalize_exchange_symbol
from tradingagents.dataflows.interface import route_to_vendor

_RT_TTL_SECONDS = max(2.0, float(__import__("os").getenv("TA_RT_K_TTL", "8") or "8"))
_RT_MAX_BATCH = max(1, int(__import__("os").getenv("TA_RT_K_MAX_BATCH", "200") or "200"))

_cache: dict[tuple[str, ...], tuple[float, dict[str, dict[str, Any]]]] = {}
_inflight: dict[tuple[str, ...], Future[dict[str, dict[str, Any]]]] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class RtBoardItem:
    symbol: str
    name: str | None
    pre_close: float | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    vol: float | None
    amount: float | None
    num: float | None
    ask_price1: float | None
    ask_volume1: float | None
    bid_price1: float | None
    bid_volume1: float | None
    trade_time: str | None
    change: float | None
    change_pct: float | None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _normalize_rt_symbol(raw: str) -> str:
    s = str(raw or "").strip().upper()
    if not s:
        return ""
    # Support Tushare wildcard fetch, e.g. 6*.SH / 3*.SZ / 688*.SH / 9*.BJ
    if "*" in s:
        return s
    return normalize_exchange_symbol(s).strip().upper()


def _normalize_rt_symbols(raw_symbols: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_symbols:
        sym = _normalize_rt_symbol(raw)
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _compute_change(close: float | None, pre_close: float | None) -> tuple[float | None, float | None]:
    if close is None or pre_close in (None, 0):
        return None, None
    change = close - pre_close
    pct = (change / pre_close) * 100
    return change, pct


def _row_to_payload(row: pd.Series) -> tuple[str, dict[str, Any]] | None:
    ts_code = str(row.get("ts_code") or "").strip().upper()
    if not ts_code:
        return None
    pre_close = _as_float(row.get("pre_close"))
    close = _as_float(row.get("close"))
    change, change_pct = _compute_change(close, pre_close)
    payload: dict[str, Any] = {
        "name": str(row.get("name") or "").strip() or None,
        "pre_close": pre_close,
        "open": _as_float(row.get("open")),
        "high": _as_float(row.get("high")),
        "low": _as_float(row.get("low")),
        "close": close,
        "vol": _as_float(row.get("vol")),
        "amount": _as_float(row.get("amount")),
        "num": _as_float(row.get("num")),
        "ask_price1": _as_float(row.get("ask_price1")),
        "ask_volume1": _as_float(row.get("ask_volume1")),
        "bid_price1": _as_float(row.get("bid_price1")),
        "bid_volume1": _as_float(row.get("bid_volume1")),
        "trade_time": str(row.get("trade_time") or "").strip() or None,
        "change": change,
        "change_pct": change_pct,
        "source": "tushare_rt",
    }
    return ts_code, payload


def _fetch_rt_quotes_uncached(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    # tushare provider accepts either comma-separated str or list[str]
    result = route_to_vendor("fetch_rt_daily_bar_df", symbols)
    if not isinstance(result, pd.DataFrame) or result.empty:
        return {}
    quotes: dict[str, dict[str, Any]] = {}
    for _, row in result.iterrows():
        item = _row_to_payload(row)
        if item is None:
            continue
        quotes[item[0]] = item[1]
    return quotes


def get_rt_daily_bulk(raw_symbols: list[str]) -> tuple[dict[str, dict[str, Any]], list[str], int]:
    symbols = _normalize_rt_symbols(raw_symbols)
    if not symbols:
        return {}, [], int(_RT_TTL_SECONDS)
    if len(symbols) > _RT_MAX_BATCH:
        symbols = symbols[:_RT_MAX_BATCH]
    key = tuple(sorted(symbols))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            cached = deepcopy(hit[1])
            missing = [sym for sym in symbols if sym not in cached]
            return cached, missing, int(_RT_TTL_SECONDS)
        future = _inflight.get(key)
        if future is None:
            future = Future()
            _inflight[key] = future
            owner = True
        else:
            owner = False
    if not owner:
        shared = deepcopy(future.result())
        missing = [sym for sym in symbols if sym not in shared]
        return shared, missing, int(_RT_TTL_SECONDS)

    try:
        quotes = _fetch_rt_quotes_uncached(symbols)
        with _lock:
            _cache[key] = (time.time() + _RT_TTL_SECONDS, deepcopy(quotes))
            _inflight.pop(key, None)
        future.set_result(deepcopy(quotes))
        missing = [sym for sym in symbols if sym not in quotes]
        return quotes, missing, int(_RT_TTL_SECONDS)
    except Exception:
        # fallback for concrete symbols (wildcard cannot be mapped reliably)
        fallback_input = [sym for sym in symbols if "*" not in sym]
        fallback_quotes: dict[str, dict[str, Any]] = {}
        if fallback_input:
            try:
                # IMPORTANT: do not call tracking_board_service._fetch_live_quotes here,
                # otherwise it can recurse back into get_rt_daily_bulk.
                raw = route_to_vendor("get_realtime_quotes", fallback_input)
                fallback_quotes = json.loads(raw) if isinstance(raw, str) else {}
            except Exception:
                fallback_quotes = {}
        with _lock:
            _cache[key] = (time.time() + min(3.0, _RT_TTL_SECONDS), deepcopy(fallback_quotes))
            _inflight.pop(key, None)
        future.set_result(deepcopy(fallback_quotes))
        missing = [sym for sym in symbols if sym not in fallback_quotes]
        return fallback_quotes, missing, int(min(3.0, _RT_TTL_SECONDS))


def get_rt_board(pattern: str, sort_by: str = "change_pct", limit: int = 50) -> list[RtBoardItem]:
    symbols = [_normalize_rt_symbol(pattern)]
    quotes, _missing, _ttl = get_rt_daily_bulk(symbols)
    items: list[RtBoardItem] = []
    for sym, q in quotes.items():
        items.append(
            RtBoardItem(
                symbol=sym,
                name=q.get("name"),
                pre_close=_as_float(q.get("pre_close")),
                open=_as_float(q.get("open")),
                high=_as_float(q.get("high")),
                low=_as_float(q.get("low")),
                close=_as_float(q.get("close")),
                vol=_as_float(q.get("vol")),
                amount=_as_float(q.get("amount")),
                num=_as_float(q.get("num")),
                ask_price1=_as_float(q.get("ask_price1")),
                ask_volume1=_as_float(q.get("ask_volume1")),
                bid_price1=_as_float(q.get("bid_price1")),
                bid_volume1=_as_float(q.get("bid_volume1")),
                trade_time=q.get("trade_time"),
                change=_as_float(q.get("change")),
                change_pct=_as_float(q.get("change_pct")),
            )
        )
    sort_key_map = {
        "change_pct": lambda x: x.change_pct if x.change_pct is not None else -10**9,
        "change": lambda x: x.change if x.change is not None else -10**9,
        "amount": lambda x: x.amount if x.amount is not None else -1,
        "vol": lambda x: x.vol if x.vol is not None else -1,
    }
    key_fn = sort_key_map.get(sort_by, sort_key_map["change_pct"])
    items.sort(key=key_fn, reverse=True)
    return items[: max(1, limit)]

