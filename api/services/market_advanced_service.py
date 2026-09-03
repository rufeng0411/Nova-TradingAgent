"""Advanced intraday / orderbook / trades / company profile — cached AkShare-backed."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List

import pandas as pd

from api.symbol_utils import cn_symbol_supports_extended_kline, normalize_exchange_symbol
from api.services.cache_service import get_tiered_cache
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.providers.cn_akshare_provider import AKSHARE_LIGHT_CALL_LOCK

logger = logging.getLogger(__name__)

_INTRADAY_TTL = 30.0
_ORDERBOOK_TTL = 15.0
_PROFILE_TTL = 86400.0

_cache = get_tiered_cache("market_advanced")


def _norm_symbol(symbol: str) -> str:
    return normalize_exchange_symbol((symbol or "").strip()).upper()


def _six_digit(symbol: str) -> str:
    s = _norm_symbol(symbol)
    if "." in s:
        return s.split(".")[0]
    if len(s) >= 6 and s[:6].isdigit():
        return s[:6]
    return s


def _sina_symbol(symbol: str) -> str:
    s = _norm_symbol(symbol)
    code = _six_digit(symbol)
    if s.endswith(".SH"):
        return f"sh{code}"
    if s.endswith(".SZ"):
        return f"sz{code}"
    if s.endswith(".BJ"):
        return f"bj{code}"
    return f"sh{code}" if code.startswith(("5", "6", "9")) else f"sz{code}"


def _cache_get(key: str) -> Any | None:
    return _cache.get(key)


def _cache_set(key: str, value: Any, ttl: float) -> None:
    _cache.set(key, value, ttl)


def fetch_intraday(symbol: str) -> Dict[str, Any]:
    sym = _norm_symbol(symbol)
    if not cn_symbol_supports_extended_kline(sym):
        return {"unsupported": True, "detail": "仅支持沪深京 A 股"}
    code = _six_digit(sym)
    key = f"intraday|{code}"
    hit = _cache_get(key)
    if hit is not None:
        return hit

    try:
        import akshare as ak

        try:
            with AKSHARE_LIGHT_CALL_LOCK:
                df = ak.stock_intraday_em(symbol=code)
        except Exception as em_exc:
            logger.info("[advanced] stock_intraday_em failed %s, fallback minute: %s", sym, em_exc)
            with AKSHARE_LIGHT_CALL_LOCK:
                df = ak.stock_zh_a_minute(symbol=_sina_symbol(sym), period="1", adjust="")
        if df is None or df.empty:
            out = {"symbol": sym, "bars": [], "summary": None}
            _cache_set(key, out, _INTRADAY_TTL)
            return out

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            try:
                cols = list(df.columns)
                if "day" in cols and "close" in cols:
                    rows.append(
                        {
                            "time": str(row.get("day")),
                            "price": float(row.get("close")) if pd.notna(row.get("close")) else None,
                            "volume": float(row.get("volume")) if pd.notna(row.get("volume")) else None,
                            "note": "1分钟",
                        }
                    )
                    continue
                rows.append(
                    {
                        "time": str(row.iloc[0]),
                        "price": float(row.iloc[1]) if pd.notna(row.iloc[1]) else None,
                        "volume": float(row.iloc[2]) if len(row) > 2 and pd.notna(row.iloc[2]) else None,
                        "note": str(row.iloc[3]) if len(row) > 3 else None,
                    }
                )
            except Exception:
                continue
        tail = rows[-240:] if len(rows) > 240 else rows
        prices = [r["price"] for r in tail if r.get("price") is not None]
        summary = None
        if prices:
            summary = {"last": prices[-1], "high": max(prices), "low": min(prices), "points": len(tail)}
        out = {"symbol": sym, "bars": tail, "summary": summary}
        _cache_set(key, out, _INTRADAY_TTL)
        return out
    except Exception as exc:
        logger.warning("[advanced] intraday failed %s: %s", sym, exc)
        return {"symbol": sym, "error": type(exc).__name__, "detail": "分时数据源暂不可用，请稍后重试", "bars": []}


def fetch_orderbook(symbol: str) -> Dict[str, Any]:
    sym = _norm_symbol(symbol)
    if not cn_symbol_supports_extended_kline(sym):
        return {"unsupported": True}
    code = _six_digit(sym)
    key = f"orderbook|{code}"
    hit = _cache_get(key)
    if hit is not None:
        return hit

    try:
        import akshare as ak

        with AKSHARE_LIGHT_CALL_LOCK:
            df = ak.stock_bid_ask_em(symbol=code)
        if df is None or df.empty:
            out = {"symbol": sym, "levels": []}
            _cache_set(key, out, _ORDERBOOK_TTL)
            return out

        levels: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            try:
                levels.append({"item": str(row.iloc[0]), "value": float(row.iloc[1]) if pd.notna(row.iloc[1]) else None})
            except Exception:
                continue
        out = {"symbol": sym, "levels": levels[:40]}
        _cache_set(key, out, _ORDERBOOK_TTL)
        return out
    except Exception as exc:
        logger.warning("[advanced] orderbook failed %s: %s", sym, exc)
        return {"symbol": sym, "error": type(exc).__name__, "detail": "五档盘口数据源暂不可用，请稍后重试", "levels": []}


def fetch_trades(symbol: str, limit: int = 40) -> Dict[str, Any]:
    intra = fetch_intraday(symbol)
    bars = intra.get("bars") or []
    tail = bars[-limit:] if len(bars) > limit else bars
    return {"symbol": _norm_symbol(symbol), "trades": tail, "source": "intraday_em"}


def fetch_company_profile(symbol: str) -> Dict[str, Any]:
    sym = _norm_symbol(symbol)
    if not cn_symbol_supports_extended_kline(sym):
        return {"unsupported": True}
    key = f"profile|{sym}"
    hit = _cache_get(key)
    if hit is not None:
        return hit

    try:
        from tradingagents.dataflows.trade_calendar import cn_today_str

        raw = route_to_vendor("get_fundamentals", sym, cn_today_str())
        text = raw if isinstance(raw, str) else str(raw)
        excerpt = text[:12000]
        ver = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:12]
        out = {"symbol": sym, "markdown_excerpt": excerpt, "content_version": ver}
        _cache_set(key, out, _PROFILE_TTL)
        return out
    except Exception as exc:
        logger.warning("[advanced] fundamentals failed %s: %s", sym, exc)
        return {"symbol": sym, "error": type(exc).__name__, "detail": "企业资料数据源暂不可用，请稍后重试", "markdown_excerpt": ""}


def collect_insight_context(symbol: str, *, for_chart_insight: bool = False) -> Dict[str, Any]:
    """Aggregates advanced market snippets for the LLM.

    `for_chart_insight=True`: skip slow `fetch_company_profile` (fundamentals) to keep
    POST /v1/market/chart/insight responsive; intraday tail is reused for recent trades
    instead of calling `fetch_trades` (which would fetch intraday twice).
    """
    sym = _norm_symbol(symbol)
    intra = fetch_intraday(sym)
    ob = fetch_orderbook(sym)
    bars = intra.get("bars") or []
    tail = bars[-30:] if len(bars) > 30 else bars
    if for_chart_insight:
        prof: Dict[str, Any] = {"symbol": sym, "markdown_excerpt": "", "content_version": None}
    else:
        prof = fetch_company_profile(sym)

    ctx: Dict[str, Any] = {
        "intraday_summary": intra.get("summary"),
        "intraday_bar_count": len(bars),
        "orderbook_level_rows": len(ob.get("levels") or []),
        "recent_trades_tail": tail,
        "company_profile_excerpt": (prof.get("markdown_excerpt") or "")[:4000],
        "company_profile_version": prof.get("content_version"),
    }
    try:
        from api.services import rt_quote_service

        rt_quotes, _missing, _ttl = rt_quote_service.get_rt_daily_bulk([sym])
        rt = rt_quotes.get(sym) or {}
        if rt:
            ctx["rt_k_snapshot"] = {
                "open": rt.get("open"),
                "high": rt.get("high"),
                "low": rt.get("low"),
                "close": rt.get("close"),
                "pre_close": rt.get("pre_close"),
                "change": rt.get("change"),
                "pct_chg": rt.get("change_pct"),
                "vol": rt.get("vol"),
                "amount": rt.get("amount"),
                "num": rt.get("num"),
                "ask_price1": rt.get("ask_price1"),
                "bid_price1": rt.get("bid_price1"),
                "trade_time": rt.get("trade_time"),
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": rt.get("source"),
            }
    except Exception:
        pass
    if for_chart_insight:
        ctx["chart_insight_advanced_mode"] = "lite"
    if intra.get("error"):
        ctx["intraday_error"] = intra["error"]
    if ob.get("error"):
        ctx["orderbook_error"] = ob["error"]
    if prof.get("error"):
        ctx["company_profile_error"] = prof["error"]
    ctx["symbol"] = sym
    return ctx
