from __future__ import annotations

import math
from datetime import datetime, date, timezone
from typing import Iterable, Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from api.database import (
    MarketDataCompanyBasicDB,
    MarketDataDailyBarDB,
    MarketDataFinancialReportDB,
    MarketDataMacroIndicatorDB,
    MarketDataNorthMoneyDB,
    MarketDataDisclosureDB,
    MarketDataVendorCallLogDB,
    MarketDataDailyBasicDB,
    MarketDataLimitListDB,
    MarketDataMoneyflowDB,
    MarketDataMarginDetailDB,
    MarketDataTopListDB,
    MarketDataTopInstDB,
    MarketDataHsgtTop10DB,
    MarketDataStkFactorProDB,
    MarketDataCyqPerfDB,
    MarketDataFinaIndicatorDB,
    MarketDataForecastDB,
    MarketDataExpressDB,
    MarketDataHolderNumberDB,
)


def _now():
    return datetime.now(timezone.utc)


def _json_safe(obj: Any) -> Any:
    """Recursively convert values so SQLAlchemy JSON columns can serialize."""
    if obj is None:
        return None
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, np.generic):
        try:
            return obj.item()
        except Exception:
            return float(obj)
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return obj


def bulk_upsert(
    db: Session,
    *,
    table,
    rows: list[dict[str, Any]],
    unique_keys: list[str],
) -> int:
    """Dialect-aware bulk upsert for postgres/mysql, fallback for sqlite."""
    if not rows:
        return 0
    safe_rows = [{k: _json_safe(v) for k, v in row.items()} for row in rows]
    dialect = db.bind.dialect.name if db.bind is not None else ""

    if dialect == "postgresql":
        stmt = pg_insert(table).values(safe_rows)
        update_cols = {
            c.name: stmt.excluded[c.name]
            for c in table.columns
            if c.name not in unique_keys
        }
        db.execute(stmt.on_conflict_do_update(index_elements=unique_keys, set_=update_cols))
        db.commit()
        return len(safe_rows)

    if dialect == "mysql":
        stmt = mysql_insert(table).values(safe_rows)
        update_cols = {
            c.name: stmt.inserted[c.name]
            for c in table.columns
            if c.name not in unique_keys
        }
        db.execute(stmt.on_duplicate_key_update(**update_cols))
        db.commit()
        return len(safe_rows)

    count = 0
    model = table.mapper.class_
    for row in safe_rows:
        key = {k: row[k] for k in unique_keys}
        obj = db.get(model, key)
        if obj is None:
            obj = model(**key)
            db.add(obj)
        for k, v in row.items():
            setattr(obj, k, v)
        count += 1
    if count:
        db.commit()
    return count


def upsert_daily_bar_batch(
    db: Session,
    rows: Iterable[dict[str, Any]],
) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        if not symbol or trade_date is None:
            continue
        normalized.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
                "adj_factor": row.get("adj_factor"),
                "source_primary": row.get("source_primary"),
                "source_secondary": row.get("source_secondary"),
                "recon_status": row.get("recon_status") or "unknown",
                "updated_at": _now(),
            }
        )
    return bulk_upsert(
        db,
        table=MarketDataDailyBarDB.__table__,
        rows=normalized,
        unique_keys=["symbol", "trade_date"],
    )


def upsert_north_money_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        trade_date = row.get("trade_date")
        symbol = (row.get("symbol") or "").strip().upper()
        if trade_date is None or not symbol:
            continue
        normalized.append(
            {
                "trade_date": trade_date,
                "symbol": symbol,
                "hold_amount": row.get("hold_amount"),
                "hold_ratio": row.get("hold_ratio"),
                "net_flow": row.get("net_flow"),
                "raw_json": row.get("raw_json"),
                "source_primary": row.get("source_primary"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(
        db,
        table=MarketDataNorthMoneyDB.__table__,
        rows=normalized,
        unique_keys=["trade_date", "symbol"],
    )


def upsert_company_basic_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        normalized.append(
            {
                "symbol": symbol,
                "name": row.get("name"),
                "market": row.get("market"),
                "industry": row.get("industry"),
                "list_date": row.get("list_date"),
                "status": row.get("status"),
                "raw_json": row.get("raw_json"),
                "source_primary": row.get("source_primary"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(
        db,
        table=MarketDataCompanyBasicDB.__table__,
        rows=normalized,
        unique_keys=["symbol"],
    )


def upsert_financial_report_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        period_end = row.get("period_end")
        report_type = (row.get("report_type") or "").strip()
        if not symbol or not period_end or not report_type:
            continue
        normalized.append(
            {
                "symbol": symbol,
                "period_end": period_end,
                "report_type": report_type,
                "report_date": row.get("report_date"),
                "raw_json": row.get("raw_json"),
                "source_primary": row.get("source_primary"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(
        db,
        table=MarketDataFinancialReportDB.__table__,
        rows=normalized,
        unique_keys=["symbol", "period_end", "report_type"],
    )


def upsert_disclosure_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        row_id = (row.get("id") or "").strip()
        symbol = (row.get("symbol") or "").strip().upper()
        if not row_id or not symbol:
            continue
        normalized.append(
            {
                "id": row_id,
                "symbol": symbol,
                "title": row.get("title"),
                "ann_type": row.get("ann_type"),
                "ann_time": row.get("ann_time"),
                "url": row.get("url"),
                "raw_json": row.get("raw_json"),
                "source_primary": row.get("source_primary"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(
        db,
        table=MarketDataDisclosureDB.__table__,
        rows=normalized,
        unique_keys=["id"],
    )


def upsert_macro_indicator_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        series_id = (row.get("series_id") or "").strip()
        period = (row.get("period") or "").strip()
        if not series_id or not period:
            continue
        v = row.get("value")
        if hasattr(v, "item"):
            try:
                v = v.item()
            except Exception:
                v = float(v)
        normalized.append(
            {
                "series_id": series_id,
                "period": period,
                "value": v,
                "unit": row.get("unit"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(
        db,
        table=MarketDataMacroIndicatorDB.__table__,
        rows=normalized,
        unique_keys=["series_id", "period"],
    )


def query_daily_bar_range(
    db: Session,
    symbol: str,
    start_date: date,
    end_date: date,
) -> list[MarketDataDailyBarDB]:
    return (
        db.query(MarketDataDailyBarDB)
        .filter(
            MarketDataDailyBarDB.symbol == symbol.strip().upper(),
            MarketDataDailyBarDB.trade_date >= start_date,
            MarketDataDailyBarDB.trade_date <= end_date,
        )
        .order_by(MarketDataDailyBarDB.trade_date.asc())
        .all()
    )


def insert_vendor_call_log(
    db: Session,
    *,
    id: str,
    method: str,
    vendor: str,
    category: str | None,
    market: str | None,
    status: str,
    latency_ms: int | None = None,
    error_code: str | None = None,
) -> None:
    obj = MarketDataVendorCallLogDB(
        id=id,
        method=method,
        vendor=vendor,
        category=category,
        market=market,
        status=status,
        latency_ms=latency_ms,
        error_code=error_code,
    )
    db.add(obj)
    db.commit()


def cleanup_vendor_call_log(db: Session, retain_days: int = 90) -> int:
    """Delete old vendor call logs in a dialect-safe way."""
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        stmt = text(
            "DELETE FROM marketdata_vendor_call_log "
            "WHERE created_at < NOW() - CAST(:ival AS INTERVAL)"
        )
        result = db.execute(stmt, {"ival": f"{int(retain_days)} days"})
    elif dialect == "mysql":
        stmt = text(
            "DELETE FROM marketdata_vendor_call_log "
            "WHERE created_at < DATE_SUB(NOW(), INTERVAL :days DAY)"
        )
        result = db.execute(stmt, {"days": int(retain_days)})
    else:
        stmt = text(
            "DELETE FROM marketdata_vendor_call_log "
            "WHERE created_at < datetime('now', :offset)"
        )
        result = db.execute(stmt, {"offset": f"-{int(retain_days)} days"})
    db.commit()
    return int(result.rowcount or 0)


def upsert_daily_basic_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        if not symbol or trade_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "pe": row.get("pe"),
                "pb": row.get("pb"),
                "ps": row.get("ps"),
                "total_mv": row.get("total_mv"),
                "circ_mv": row.get("circ_mv"),
                "turnover_rate": row.get("turnover_rate"),
                "free_share": row.get("free_share"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataDailyBasicDB.__table__, rows=payload, unique_keys=["symbol", "trade_date"])


def upsert_limit_list_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        if not symbol or trade_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "limit_type": row.get("limit_type"),
                "fd_amount": row.get("fd_amount"),
                "open_times": row.get("open_times"),
                "lu_time": row.get("lu_time"),
                "last_time": row.get("last_time"),
                "status": row.get("status"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataLimitListDB.__table__, rows=payload, unique_keys=["symbol", "trade_date"])


def upsert_moneyflow_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        if not symbol or trade_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "buy_sm": row.get("buy_sm"),
                "buy_md": row.get("buy_md"),
                "buy_lg": row.get("buy_lg"),
                "buy_elg": row.get("buy_elg"),
                "sell_sm": row.get("sell_sm"),
                "sell_md": row.get("sell_md"),
                "sell_lg": row.get("sell_lg"),
                "sell_elg": row.get("sell_elg"),
                "net_sm": row.get("net_sm"),
                "net_md": row.get("net_md"),
                "net_lg": row.get("net_lg"),
                "net_elg": row.get("net_elg"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataMoneyflowDB.__table__, rows=payload, unique_keys=["symbol", "trade_date"])


def upsert_margin_detail_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        if not symbol or trade_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "rzye": row.get("rzye"),
                "rzmre": row.get("rzmre"),
                "rqye": row.get("rqye"),
                "rqmcl": row.get("rqmcl"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataMarginDetailDB.__table__, rows=payload, unique_keys=["symbol", "trade_date"])


def upsert_top_list_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        rank = row.get("rank")
        if not symbol or trade_date is None or rank is None:
            continue
        payload.append(
            {
                "trade_date": trade_date,
                "symbol": symbol,
                "rank": int(rank),
                "close": row.get("close"),
                "pct_change": row.get("pct_change"),
                "turnover_rate": row.get("turnover_rate"),
                "l_buy": row.get("l_buy"),
                "l_sell": row.get("l_sell"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataTopListDB.__table__, rows=payload, unique_keys=["trade_date", "symbol", "rank"])


def upsert_top_inst_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        exalter = (row.get("exalter") or "").strip()
        if not symbol or trade_date is None or not exalter:
            continue
        payload.append(
            {
                "trade_date": trade_date,
                "symbol": symbol,
                "exalter": exalter,
                "buy": row.get("buy"),
                "sell": row.get("sell"),
                "net": row.get("net"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataTopInstDB.__table__, rows=payload, unique_keys=["trade_date", "symbol", "exalter"])


def upsert_hsgt_top10_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        if not symbol or trade_date is None:
            continue
        payload.append(
            {
                "trade_date": trade_date,
                "symbol": symbol,
                "market_type": row.get("market_type"),
                "rank": row.get("rank"),
                "hold_amount": row.get("hold_amount"),
                "net_buy": row.get("net_buy"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataHsgtTop10DB.__table__, rows=payload, unique_keys=["trade_date", "symbol"])


def upsert_stk_factor_pro_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        if not symbol or trade_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "fd_amount": row.get("fd_amount"),
                "bid1_vol": row.get("bid1_vol"),
                "ask1_vol": row.get("ask1_vol"),
                "main_net_flow": row.get("main_net_flow"),
                "super_large_net": row.get("super_large_net"),
                "large_net": row.get("large_net"),
                "mid_net": row.get("mid_net"),
                "small_net": row.get("small_net"),
                "limit_up_days": row.get("limit_up_days"),
                "limit_up_height": row.get("limit_up_height"),
                "net_subscribe": row.get("net_subscribe"),
                "turnover_rate_z": row.get("turnover_rate_z"),
                "amplitude_pct": row.get("amplitude_pct"),
                "vol_ratio": row.get("vol_ratio"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataStkFactorProDB.__table__, rows=payload, unique_keys=["symbol", "trade_date"])


def upsert_cyq_perf_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        trade_date = row.get("trade_date")
        if not symbol or trade_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "his_low": row.get("his_low"),
                "his_high": row.get("his_high"),
                "cost_5pct": row.get("cost_5pct"),
                "cost_15pct": row.get("cost_15pct"),
                "cost_50pct": row.get("cost_50pct"),
                "cost_85pct": row.get("cost_85pct"),
                "cost_95pct": row.get("cost_95pct"),
                "weight_avg": row.get("weight_avg"),
                "winner_rate": row.get("winner_rate"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataCyqPerfDB.__table__, rows=payload, unique_keys=["symbol", "trade_date"])


def upsert_fina_indicator_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        end_date = row.get("end_date")
        if not symbol or end_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "end_date": end_date,
                "roe": row.get("roe"),
                "gross_margin": row.get("gross_margin"),
                "debt_ratio": row.get("debt_ratio"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataFinaIndicatorDB.__table__, rows=payload, unique_keys=["symbol", "end_date"])


def upsert_forecast_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        end_date = row.get("end_date")
        ann_date = row.get("ann_date")
        if not symbol or end_date is None or ann_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "end_date": end_date,
                "ann_date": ann_date,
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataForecastDB.__table__, rows=payload, unique_keys=["symbol", "end_date", "ann_date"])


def upsert_express_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        end_date = row.get("end_date")
        ann_date = row.get("ann_date")
        if not symbol or end_date is None or ann_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "end_date": end_date,
                "ann_date": ann_date,
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataExpressDB.__table__, rows=payload, unique_keys=["symbol", "end_date", "ann_date"])


def upsert_holdernumber_batch(db: Session, rows: Iterable[dict[str, Any]]) -> int:
    payload = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        end_date = row.get("end_date")
        if not symbol or end_date is None:
            continue
        payload.append(
            {
                "symbol": symbol,
                "end_date": end_date,
                "holder_num": row.get("holder_num"),
                "source_primary": row.get("source_primary"),
                "raw_json": row.get("raw_json"),
                "updated_at": _now(),
            }
        )
    return bulk_upsert(db, table=MarketDataHolderNumberDB.__table__, rows=payload, unique_keys=["symbol", "end_date"])
