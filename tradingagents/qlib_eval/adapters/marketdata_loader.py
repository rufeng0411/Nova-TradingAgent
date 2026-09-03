"""Load marketdata_* rows for Qlib feature enrichment."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from api.database import (
    MarketDataCyqPerfDB,
    MarketDataDailyBasicDB,
    MarketDataMoneyflowDB,
    MarketDataStkFactorProDB,
    MarketdataSessionLocal,
)


def _parse_date(value: str):
    s = str(value or "").strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_marketdata_row(db: Session, *, symbol: str, trade_date: str) -> dict[str, Any]:
    td = _parse_date(trade_date)
    if not td:
        return {}
    out: dict[str, Any] = {"symbol": symbol, "trade_date": trade_date}

    basic = (
        db.query(MarketDataDailyBasicDB)
        .filter(MarketDataDailyBasicDB.symbol == symbol, MarketDataDailyBasicDB.trade_date == td)
        .first()
    )
    if basic:
        out.update(
            {
                "pe_ttm": float(basic.pe) if basic.pe is not None else None,
                "pb": float(basic.pb) if basic.pb is not None else None,
                "turnover_rate": float(basic.turnover_rate) if basic.turnover_rate is not None else None,
                "total_mv": float(basic.total_mv) if basic.total_mv is not None else None,
            }
        )

    factor = (
        db.query(MarketDataStkFactorProDB)
        .filter(MarketDataStkFactorProDB.symbol == symbol, MarketDataStkFactorProDB.trade_date == td)
        .first()
    )
    if factor:
        for attr in ("pe", "pe_ttm", "pb", "turnover_rate"):
            val = getattr(factor, attr, None)
            if val is not None and out.get(attr if attr != "pe" else "pe_ttm") is None:
                out["pe_ttm" if attr == "pe" else attr] = float(val)

    mf = (
        db.query(MarketDataMoneyflowDB)
        .filter(MarketDataMoneyflowDB.symbol == symbol, MarketDataMoneyflowDB.trade_date == td)
        .first()
    )
    if mf and mf.net_mf_amount is not None:
        out["net_mf_amount"] = float(mf.net_mf_amount)

    cyq = (
        db.query(MarketDataCyqPerfDB)
        .filter(MarketDataCyqPerfDB.symbol == symbol, MarketDataCyqPerfDB.trade_date == td)
        .first()
    )
    if cyq:
        if cyq.winner_rate is not None:
            out["winner_rate"] = float(cyq.winner_rate)
        if cyq.cost_50pct is not None:
            out["cost_50pct"] = float(cyq.cost_50pct)

    return out


def load_daily_bars(db: Session, *, symbol: str, start_date: str, end_date: str):
    from api.database import MarketDataDailyBarDB

    sd = _parse_date(start_date)
    ed = _parse_date(end_date)
    if not sd or not ed:
        return []
    rows = (
        db.query(MarketDataDailyBarDB)
        .filter(
            MarketDataDailyBarDB.symbol == symbol,
            MarketDataDailyBarDB.trade_date >= sd,
            MarketDataDailyBarDB.trade_date <= ed,
        )
        .order_by(MarketDataDailyBarDB.trade_date.asc())
        .all()
    )
    return [
        {
            "trade_date": r.trade_date.strftime("%Y-%m-%d") if r.trade_date else None,
            "open": float(r.open) if r.open is not None else None,
            "high": float(r.high) if r.high is not None else None,
            "low": float(r.low) if r.low is not None else None,
            "close": float(r.close) if r.close is not None else None,
            "volume": int(r.volume) if r.volume is not None else None,
        }
        for r in rows
    ]


def with_marketdata_session(fn):
    """Helper decorator-style context for scripts."""

    def wrapper(*args, **kwargs):
        db = MarketdataSessionLocal()
        try:
            return fn(db, *args, **kwargs)
        finally:
            db.close()

    return wrapper
