"""Advanced CN-A-share market snapshots (intraday, order book, trades tail, company profile)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.database import UserDB
from api.deps import require_advanced_market
from api.services import market_advanced_service, market_chart_service, rt_quote_service
from api.symbol_utils import normalize_exchange_symbol

router = APIRouter(tags=["market-advanced"])


class RtDailyQuoteItem(BaseModel):
    name: str | None = None
    pre_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    vol: float | None = None
    amount: float | None = None
    num: float | None = None
    ask_price1: float | None = None
    ask_volume1: float | None = None
    bid_price1: float | None = None
    bid_volume1: float | None = None
    trade_time: str | None = None
    change: float | None = None
    change_pct: float | None = None
    source: str | None = None


class RtDailyResponse(BaseModel):
    quotes: dict[str, RtDailyQuoteItem] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    cache_ttl_seconds: int


class RtBoardResponse(BaseModel):
    pattern: str
    sort: str
    limit: int
    items: list[dict[str, Any]]


class ChartAuctionResponse(BaseModel):
    enabled: bool = True
    symbol: str
    snapshot: dict[str, Any] | None = None


class ChartCyqResponse(BaseModel):
    enabled: bool = True
    symbol: str
    trade_date: str | None = None
    summary: dict[str, Any] | None = None
    distribution: list[dict[str, Any]] = Field(default_factory=list)


class ChartSeriesResponse(BaseModel):
    enabled: bool = True
    symbol: str
    snapshot: dict[str, Any] | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    market: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/intraday")
async def get_intraday(
    symbol: str,
    _user: UserDB = Depends(require_advanced_market),
):
    return await asyncio.to_thread(market_advanced_service.fetch_intraday, symbol)


@router.get("/orderbook")
async def get_orderbook(
    symbol: str,
    _user: UserDB = Depends(require_advanced_market),
):
    return await asyncio.to_thread(market_advanced_service.fetch_orderbook, symbol)


@router.get("/trades")
async def get_trades(
    symbol: str,
    limit: int = Query(40, ge=5, le=100),
    _user: UserDB = Depends(require_advanced_market),
):
    return await asyncio.to_thread(market_advanced_service.fetch_trades, symbol, limit)


@router.get("/company-profile")
async def get_company_profile(
    symbol: str,
    _user: UserDB = Depends(require_advanced_market),
):
    return await asyncio.to_thread(market_advanced_service.fetch_company_profile, symbol)


@router.get("/rt-daily", response_model=RtDailyResponse)
async def get_rt_daily(
    symbols: str = Query(..., description="逗号分隔代码或通配符，如 600519.SH,000001.SZ,3*.SZ"),
    _user: UserDB = Depends(require_advanced_market),
) -> RtDailyResponse:
    parts = [x.strip() for x in symbols.split(",") if x.strip()]
    quotes, missing, ttl = await asyncio.to_thread(rt_quote_service.get_rt_daily_bulk, parts)
    return RtDailyResponse(quotes=quotes, missing=missing, cache_ttl_seconds=ttl)


@router.get("/rt-board", response_model=RtBoardResponse)
async def get_rt_board(
    pattern: str = Query(..., description="通配符，如 6*.SH / 3*.SZ / 688*.SH / 9*.BJ"),
    sort: str = Query("change_pct", pattern="^(change_pct|change|amount|vol)$"),
    limit: int = Query(50, ge=1, le=200),
    _user: UserDB = Depends(require_advanced_market),
) -> RtBoardResponse:
    norm_pattern = normalize_exchange_symbol(pattern.strip()).upper() if "*" not in pattern else pattern.strip().upper()
    rows = await asyncio.to_thread(rt_quote_service.get_rt_board, norm_pattern, sort, limit)
    items = [item.__dict__ for item in rows]
    return RtBoardResponse(pattern=norm_pattern, sort=sort, limit=limit, items=items)


@router.get("/chart/auction", response_model=ChartAuctionResponse)
async def get_chart_auction(
    symbol: str,
    _user: UserDB = Depends(require_advanced_market),
) -> ChartAuctionResponse:
    payload = await asyncio.to_thread(market_chart_service.get_auction_snapshot, symbol)
    return ChartAuctionResponse(**payload)


@router.get("/chart/cyq", response_model=ChartCyqResponse)
async def get_chart_cyq(
    symbol: str,
    days: int = Query(60, ge=20, le=360),
    _user: UserDB = Depends(require_advanced_market),
) -> ChartCyqResponse:
    payload = await asyncio.to_thread(market_chart_service.get_cyq_snapshot, symbol, days)
    return ChartCyqResponse(**payload)


@router.get("/chart/moneyflow", response_model=ChartSeriesResponse)
async def get_chart_moneyflow(
    symbol: str,
    days: int = Query(90, ge=20, le=360),
    _user: UserDB = Depends(require_advanced_market),
) -> ChartSeriesResponse:
    payload = await asyncio.to_thread(market_chart_service.get_moneyflow_series, symbol, days)
    return ChartSeriesResponse(**payload)


@router.get("/chart/factor-pro", response_model=ChartSeriesResponse)
async def get_chart_factor_pro(
    symbol: str,
    days: int = Query(120, ge=20, le=720),
    _user: UserDB = Depends(require_advanced_market),
) -> ChartSeriesResponse:
    payload = await asyncio.to_thread(market_chart_service.get_factor_pro_snapshot, symbol, days)
    return ChartSeriesResponse(**payload)


@router.get("/chart/daily-basic", response_model=ChartSeriesResponse)
async def get_chart_daily_basic(
    symbol: str,
    days: int = Query(90, ge=20, le=360),
    _user: UserDB = Depends(require_advanced_market),
) -> ChartSeriesResponse:
    payload = await asyncio.to_thread(market_chart_service.get_daily_basic_snapshot, symbol, days)
    return ChartSeriesResponse(**payload)


@router.get("/chart/events", response_model=ChartSeriesResponse)
async def get_chart_events(
    symbol: str,
    start: str,
    end: str,
    _user: UserDB = Depends(require_advanced_market),
) -> ChartSeriesResponse:
    payload = await asyncio.to_thread(market_chart_service.get_event_markers, symbol, start, end)
    return ChartSeriesResponse(**payload)


@router.get("/chart/hsgt", response_model=ChartSeriesResponse)
async def get_chart_hsgt(
    symbol: str,
    days: int = Query(90, ge=20, le=360),
    _user: UserDB = Depends(require_advanced_market),
) -> ChartSeriesResponse:
    payload = await asyncio.to_thread(market_chart_service.get_hsgt_series, symbol, days)
    return ChartSeriesResponse(**payload)


@router.get("/chart/corp-events", response_model=ChartSeriesResponse)
async def get_chart_corp_events(
    symbol: str,
    start: str,
    end: str,
    _user: UserDB = Depends(require_advanced_market),
) -> ChartSeriesResponse:
    payload = await asyncio.to_thread(market_chart_service.get_corp_event_markers, symbol, start, end)
    return ChartSeriesResponse(**payload)
