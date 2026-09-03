import os
import time
from uuid import uuid4
from datetime import datetime, timezone
from typing import Any

from .alpha_vantage_common import AlphaVantageRateLimitError
from .config import get_config
from .providers import build_default_registry
from .trade_calendar import is_cn_symbol

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": ["get_stock_data"],
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": ["get_indicators"],
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
            "get_fina_indicator",
            "fetch_fina_indicator_df",
            "get_forecast",
            "get_express",
            "get_holdernumber_series",
        ],
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ],
    },
    "realtime_data": {
        "description": "Real-time market quotes",
        "tools": ["get_realtime_quotes", "fetch_rt_daily_bar_df", "fetch_stk_auction"],
    },
    "cn_market_data": {
        "description": "China A-share market sentiment and fund flow data",
        "tools": [
            "get_board_fund_flow",
            "get_individual_fund_flow",
            "get_lhb_detail",
            "get_zt_pool",
            "get_hot_stocks_xq",
            "get_limit_list_summary",
            "get_individual_money_flow_detail",
            "get_margin_detail",
            "get_hsgt_top10",
            "get_opening_auction",
            "fetch_opening_auction_o_df",
            "fetch_opening_auction_c_df",
            "get_top_list_history",
            "fetch_individual_moneyflow_df",
            "fetch_limit_list_d",
            "fetch_top_list_df",
            "fetch_block_trade_df",
            "fetch_north_money_df",
            "fetch_hsgt_top10_df",
        ],
    },
    "valuation_data": {
        "description": "Valuation and turnover data",
        "tools": [
            "get_daily_basic",
        ],
    },
    "factor_data": {
        "description": "Factor and chip distribution data",
        "tools": [
            "get_stk_factor_pro_window",
            "get_cyq_perf",
            "get_cyq_chips",
            "fetch_stk_factor_pro_df",
            "fetch_cyq_perf_df",
            "fetch_cyq_chips_df",
        ],
    },
    "corp_event_data": {
        "description": "Corporate events and earnings related datasets",
        "tools": [
            "fetch_forecast_df",
            "fetch_express_df",
            "fetch_fina_indicator_df",
            "fetch_dividend_df",
            "fetch_stk_holdertrade_df",
        ],
    },
    "l2_data": {
        "description": "Level2 order queue depth data",
        "tools": [
            "get_l2_orderqueue_window",
        ],
    },
    "fast_snapshot": {
        "description": "Fast analysis snapshot helpers",
        "tools": [
            "fetch_rt_k",
            "fetch_index_realtime",
            "fetch_stk_auction",
            "fetch_opening_auction_o_df",
            "fetch_opening_auction_c_df",
            "fetch_stk_mins",
            "fetch_moneyflow_dc",
            "fetch_moneyflow_industry_dc",
            "fetch_stk_factor_pro",
            "fetch_top_list",
            "fetch_limit_list_d",
            "fetch_anns_d",
            "fetch_daily_basic",
            "fetch_cyq_perf_df",
            "fetch_cyq_chips_df",
            "fetch_individual_moneyflow_df",
            "fetch_stk_factor_pro_df",
            "fetch_top_list_df",
            "fetch_block_trade_df",
            "fetch_north_money_df",
            "fetch_hsgt_top10_df",
            "fetch_daily_basic_df",
            "fetch_forecast_df",
            "fetch_express_df",
            "fetch_dividend_df",
            "fetch_stk_holdertrade_df",
        ],
    },
}

_registry = build_default_registry()

VENDOR_LIST = _registry.list_names()


def _is_trace_enabled() -> bool:
    env_value = os.getenv("TA_TRACE")
    if env_value is not None:
        return env_value.strip().lower() in ("1", "true", "yes", "on")

    config = get_config()
    return bool(config.get("provider_trace", True))


def _trace(msg: str) -> None:
    if _is_trace_enabled():
        print(f"[provider-trace] {msg}", flush=True)


def _log_vendor_call(
    *,
    method: str,
    vendor: str,
    category: str,
    market: str,
    status: str,
    latency_ms: int | None = None,
    error_code: str | None = None,
) -> None:
    try:
        from api.database import get_marketdata_db_ctx, is_marketdata_db_healthy
        from api.services.market_data_service import insert_vendor_call_log

        if not is_marketdata_db_healthy():
            return
        with get_marketdata_db_ctx() as db:
            insert_vendor_call_log(
                db,
                id=uuid4().hex,
                method=method,
                vendor=vendor,
                category=category,
                market=market,
                status=status,
                latency_ms=latency_ms,
                error_code=error_code,
            )
    except Exception:
        # Logging failures must never break inference path.
        pass


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str = None, market: str | None = None) -> str:
    """Get configured vendor for category or tool method."""
    config = get_config()

    target_market = market or "global"
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return _pick_vendor_for_market(tool_vendors[method], target_market)

    configured = config.get("data_vendors", {}).get(category, "yfinance")
    return _pick_vendor_for_market(configured, target_market)


def _infer_market(method: str | None, args: tuple, kwargs: dict) -> str:
    """Infer market from symbol-like arguments.

    Returns one of: cn / us / global.
    """
    del method  # keep signature explicit for future method-specific routing

    symbol = kwargs.get("symbol") or kwargs.get("ticker")
    if not symbol and args:
        first = args[0]
        if isinstance(first, str):
            symbol = first
        elif isinstance(first, (list, tuple)) and first and isinstance(first[0], str):
            symbol = first[0]

    if isinstance(symbol, str) and symbol.strip():
        return "cn" if is_cn_symbol(symbol.strip().upper()) else "us"
    return "global"


def _pick_vendor_for_market(configured: object, market: str) -> str:
    """Resolve vendor config that may be str or dict by market."""
    if isinstance(configured, str):
        return configured
    if isinstance(configured, dict):
        if market in configured and configured[market]:
            return str(configured[market])
        for key in ("default", "global", "cn", "us"):
            if key in configured and configured[key]:
                return str(configured[key])
        for value in configured.values():
            if value:
                return str(value)
    return "yfinance"


def _resolve_vendor_chain(method: str, configured_vendor: str) -> list[str]:
    configured = [v.strip() for v in str(configured_vendor).split(",") if v.strip()]
    fallback = configured.copy()

    for provider_name in _registry.list_names():
        if provider_name not in fallback:
            fallback.append(provider_name)

    return fallback


def route_to_vendor_with_meta(method: str, *args, **kwargs) -> tuple[Any, dict]:
    """Route method calls and return (result, metadata)."""
    category = get_category_for_method(method)
    market = _infer_market(method, args, kwargs)
    vendor_config = get_vendor(category, method, market=market)
    fallback_vendors = _resolve_vendor_chain(method, vendor_config)
    if method in {"get_lhb_detail", "get_zt_pool", "get_board_fund_flow"} and "cn_tushare" in fallback_vendors:
        fallback_vendors = ["cn_tushare"] + [v for v in fallback_vendors if v != "cn_tushare"]
    last_exc = None
    primary_exc: tuple[str, Exception] | None = None
    t0 = time.monotonic()
    _trace(
        f"method={method} category={category} market={market} configured='{vendor_config}' "
        f"chain={fallback_vendors}"
    )

    for vendor in fallback_vendors:
        started_at = time.monotonic()
        provider = _registry.get(vendor)
        if provider is None:
            _trace(f"method={method} vendor={vendor} status=skip reason=not-registered")
            continue

        impl_func = getattr(provider, method, None)
        if impl_func is None:
            _trace(f"method={method} vendor={vendor} status=skip reason=not-implemented")
            continue

        try:
            result = impl_func(*args, **kwargs)
            status = "hit" if vendor == fallback_vendors[0] else "fallback"
            _trace(f"method={method} vendor={vendor} status={status}")
            latency_ms = int((time.monotonic() - started_at) * 1000)
            _log_vendor_call(
                method=method,
                vendor=vendor,
                category=category,
                market=market,
                status=status,
                latency_ms=latency_ms,
            )
            return result, {
                "method": method,
                "category": category,
                "market": market,
                "vendor": vendor,
                "status": status,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "latency_ms": latency_ms,
                "total_latency_ms": int((time.monotonic() - t0) * 1000),
                "fallback_chain": fallback_vendors,
            }
        except (AlphaVantageRateLimitError, NotImplementedError) as exc:
            last_exc = exc
            if primary_exc is None and str(exc).strip():
                primary_exc = (vendor, exc)
            _trace(
                f"method={method} vendor={vendor} status=fallback "
                f"reason={type(exc).__name__}: {exc}"
            )
            _log_vendor_call(
                method=method,
                vendor=vendor,
                category=category,
                market=market,
                status="fallback",
                latency_ms=int((time.monotonic() - started_at) * 1000),
                error_code=type(exc).__name__,
            )
            continue
        except Exception as exc:
            last_exc = exc
            if primary_exc is None:
                primary_exc = (vendor, exc)
            _trace(
                f"method={method} vendor={vendor} status=fallback "
                f"reason={type(exc).__name__}: {exc}"
            )
            _log_vendor_call(
                method=method,
                vendor=vendor,
                category=category,
                market=market,
                status="fallback",
                latency_ms=int((time.monotonic() - started_at) * 1000),
                error_code=type(exc).__name__,
            )
            continue

    _trace(f"method={method} status=failed reason=no-available-vendor")
    # 优先暴露第一个携带可读消息的异常（通常是配置好的主 vendor 抛出的真错），
    # 避免被 fallback 链尾部的空 NotImplementedError 覆盖、导致排障困难。
    if primary_exc is not None:
        report_vendor, report_exc = primary_exc
        error_text = f"[{report_vendor}] {type(report_exc).__name__}: {report_exc}"
        error_code = type(report_exc).__name__
    elif last_exc is not None:
        error_text = f"{type(last_exc).__name__}: {last_exc}"
        error_code = type(last_exc).__name__
    else:
        error_text = "no-available-vendor"
        error_code = "no-available-vendor"
    _log_vendor_call(
        method=method,
        vendor="none",
        category=category,
        market=market,
        status="error",
        error_code=error_code,
    )
    meta = {
        "method": method,
        "category": category,
        "market": market,
        "vendor": None,
        "status": "error",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "total_latency_ms": int((time.monotonic() - t0) * 1000),
        "fallback_chain": fallback_vendors,
        "error": error_text,
    }
    return None, meta


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to provider implementations with fallback support."""
    result, _meta = route_to_vendor_with_meta(method, *args, **kwargs)
    if _meta.get("status") == "error":
        raise RuntimeError(
            f"No available vendor for method '{method}'. "
            f"Configured chain: {_meta.get('fallback_chain', [])}. "
            f"Last error: {_meta.get('error')}"
        )
    return result
