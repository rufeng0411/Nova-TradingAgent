from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import os
from zoneinfo import ZoneInfo

import pandas as pd

from api.database import get_marketdata_db_ctx
from api.services import market_data_service, market_data_recon_service
from tradingagents.dataflows.providers.cn_akshare_provider import CnAkshareProvider
from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider
from tradingagents.dataflows.providers.juchao_provider import JuChaoProvider
from tradingagents.dataflows.providers.stats_cn_provider import StatsCnProvider
from tradingagents.dataflows.providers.fred_provider import FredProvider
from tradingagents.dataflows.trade_calendar import is_cn_trading_day

logger = logging.getLogger(__name__)


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _today_cn() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")


def _now_hhmm() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%H:%M")


def _build_tushare_provider() -> CnTushareProvider | None:
    token = (os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        return None
    return CnTushareProvider(token=token)


def _load_symbol_universe(ts_provider: CnTushareProvider) -> list[str]:
    try:
        basic = ts_provider.fetch_company_basic_df()
        if basic is None or basic.empty:
            return []
        symbols = []
        if "ts_code" in basic.columns:
            symbols = [str(v).upper() for v in basic["ts_code"].dropna().tolist()]
        elif "symbol" in basic.columns:
            symbols = [str(v).upper() for v in basic["symbol"].dropna().tolist()]
        limit = int(os.getenv("TA_MARKETDATA_SYMBOL_LIMIT", "3000") or "3000")
        return symbols[: max(limit, 0)] if limit > 0 else symbols
    except Exception as exc:
        logger.warning("[marketdata] load symbol universe failed: %s", exc)
        return []


def _iter_daily_rows(df: pd.DataFrame, symbol: str, source: str):
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        dt = pd.to_datetime(row.get("Date"), errors="coerce")
        if pd.isna(dt):
            continue
        yield {
            "symbol": symbol,
            "trade_date": dt.date(),
            "open": pd.to_numeric(row.get("Open"), errors="coerce"),
            "high": pd.to_numeric(row.get("High"), errors="coerce"),
            "low": pd.to_numeric(row.get("Low"), errors="coerce"),
            "close": pd.to_numeric(row.get("Close"), errors="coerce"),
            "volume": pd.to_numeric(row.get("Volume"), errors="coerce"),
            "amount": pd.to_numeric(row.get("Amount"), errors="coerce"),
            "adj_factor": pd.to_numeric(row.get("AdjFactor"), errors="coerce"),
            "source_primary": source,
        }


def _sync_company_basic(ts_provider: CnTushareProvider) -> int:
    df = ts_provider.fetch_company_basic_df()
    rows: list[dict] = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            symbol = str(row.get("ts_code") or row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            list_date = pd.to_datetime(row.get("list_date"), format="%Y%m%d", errors="coerce")
            rows.append(
                {
                    "symbol": symbol,
                    "name": row.get("name"),
                    "market": row.get("market"),
                    "industry": row.get("industry"),
                    "list_date": list_date.date() if pd.notna(list_date) else None,
                    "status": "listed",
                    "raw_json": row.to_dict(),
                    "source_primary": "cn_tushare",
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_company_basic_batch(db, rows)


def _sync_daily_bar(ts_provider: CnTushareProvider, ak_provider: CnAkshareProvider, trade_date: str) -> tuple[int, int]:
    symbols = _load_symbol_universe(ts_provider)
    if not symbols:
        return (0, 0)
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

    upsert_rows: list[dict] = []
    compared = 0
    anomalies = 0
    threshold = float(os.getenv("TA_MARKETDATA_RECON_THRESHOLD", "0.005") or "0.005")

    for symbol in symbols:
        try:
            ts_df = ts_provider.fetch_daily_bar_df(symbol, start_date, trade_date, adjust="qfq")
        except Exception:
            ts_df = pd.DataFrame()
        try:
            ak_df = ak_provider.fetch_daily_bar_df(symbol, start_date, trade_date, adjust="qfq")
        except Exception:
            ak_df = pd.DataFrame()

        if ts_df is not None and not ts_df.empty:
            upsert_rows.extend(list(_iter_daily_rows(ts_df, symbol, "cn_tushare")))
        elif ak_df is not None and not ak_df.empty:
            upsert_rows.extend(list(_iter_daily_rows(ak_df, symbol, "cn_akshare")))
            for r in upsert_rows[-len(ak_df):]:
                r["recon_status"] = "single_source"

        if _flag("TA_MARKETDATA_RECON_ENABLED", "0") and not ts_df.empty and not ak_df.empty:
            with get_marketdata_db_ctx() as db:
                stat = market_data_recon_service.recon_daily_bar_frames(
                    db,
                    trade_date=datetime.strptime(trade_date, "%Y-%m-%d").date(),
                    primary_df=ts_df.assign(symbol=symbol),
                    secondary_df=ak_df.assign(symbol=symbol),
                    source_primary="cn_tushare",
                    source_secondary="cn_akshare",
                    threshold=threshold,
                )
            compared += stat["compared"]
            anomalies += stat["anomalies"]

    with get_marketdata_db_ctx() as db:
        market_data_service.upsert_daily_bar_batch(db, upsert_rows)
    return (compared, anomalies)


def _sync_north_money(ts_provider: CnTushareProvider, trade_date: str) -> int:
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    df = ts_provider.fetch_north_money_df(start_date, trade_date)
    rows: list[dict] = []
    if df is not None and not df.empty:
        date_col = "trade_date" if "trade_date" in df.columns else None
        symbol_col = "ts_code" if "ts_code" in df.columns else ("code" if "code" in df.columns else None)
        for _, row in df.iterrows():
            dt = pd.to_datetime(row.get(date_col), format="%Y%m%d", errors="coerce") if date_col else pd.NaT
            if pd.isna(dt):
                continue
            symbol = str(row.get(symbol_col) or "").strip().upper()
            if not symbol:
                continue
            rows.append(
                {
                    "trade_date": dt.date(),
                    "symbol": symbol,
                    "hold_amount": pd.to_numeric(row.get("vol"), errors="coerce"),
                    "hold_ratio": pd.to_numeric(row.get("ratio"), errors="coerce"),
                    "net_flow": pd.to_numeric(row.get("net_amount"), errors="coerce"),
                    "raw_json": row.to_dict(),
                    "source_primary": "cn_tushare",
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_north_money_batch(db, rows)


def _sync_financial_report(ts_provider: CnTushareProvider) -> int:
    total = 0
    for report_type in ("balancesheet", "income", "cashflow"):
        df = ts_provider.fetch_financial_report_df(report_type)
        rows = []
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                symbol = str(row.get("ts_code") or "").strip().upper()
                end_dt = pd.to_datetime(row.get("end_date"), format="%Y%m%d", errors="coerce")
                ann_dt = pd.to_datetime(row.get("ann_date"), format="%Y%m%d", errors="coerce")
                if not symbol or pd.isna(end_dt):
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "period_end": end_dt.date(),
                        "report_type": report_type,
                        "report_date": ann_dt.date() if pd.notna(ann_dt) else None,
                        "raw_json": row.to_dict(),
                        "source_primary": "cn_tushare",
                    }
                )
        with get_marketdata_db_ctx() as db:
            total += market_data_service.upsert_financial_report_batch(db, rows)
    return total


def _sync_disclosure(juchao_provider: JuChaoProvider, symbols: list[str], trade_date: str) -> int:
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    rows = []
    limit = int(os.getenv("TA_DISCLOSURE_SYMBOL_LIMIT", "300") or "300")
    for symbol in symbols[: max(limit, 0)]:
        try:
            df = juchao_provider.fetch_disclosure_df(symbol, start_date, trade_date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            ann_time = pd.to_datetime(row.get("ann_time"), errors="coerce")
            rows.append(
                {
                    "id": str(row.get("id") or ""),
                    "symbol": symbol,
                    "title": row.get("title"),
                    "ann_type": row.get("ann_type"),
                    "ann_time": ann_time.to_pydatetime() if pd.notna(ann_time) else None,
                    "url": row.get("url"),
                    "raw_json": row.get("raw_json"),
                    "source_primary": "juchao",
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_disclosure_batch(db, rows)


def _sync_macro(stats_provider: StatsCnProvider, fred_provider: FredProvider | None) -> int:
    rows = []
    cn_series = ("CN_CPI_YOY", "CN_PPI_YOY", "CN_M2_YOY", "CN_GDP_YOY")
    for sid in cn_series:
        try:
            df = stats_provider.fetch_macro_series_df(sid)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        # AkShare 国统局表常见首列为「商品」，日期在「日期/月份」列，勿默认 columns[0] 为时间。
        date_col = None
        val_col = None
        for c in df.columns:
            s = str(c)
            if date_col is None and ("日期" in s or "月份" in s):
                date_col = c
        if date_col is None:
            for c in df.columns:
                lc = str(c).lower()
                if "date" in lc or "time" in lc:
                    date_col = c
                    break
        for c in df.columns:
            s = str(c)
            if val_col is None and any(x in s for x in ("今值", "公布值")):
                val_col = c
        if val_col is None:
            for c in df.columns:
                s = str(c)
                lc = s.lower()
                if "value" in lc or "数值" in s:
                    val_col = c
                    break
        if val_col is None:
            for c in df.columns:
                s = str(c)
                if val_col is None and "同比" in s and "商品" not in s:
                    val_col = c
                    break
        date_col = date_col or (df.columns[1] if len(df.columns) > 1 else df.columns[0])
        val_col = val_col or df.columns[-1]
        for _, row in df.tail(60).iterrows():
            raw_pv = row.get(date_col)
            dt_pv = pd.to_datetime(raw_pv, errors="coerce")
            if pd.notna(dt_pv):
                period_val = dt_pv.strftime("%Y-%m-%d")[:10]
            else:
                period_val = str(raw_pv or "").strip()[:10]
            if not period_val:
                continue
            val = pd.to_numeric(row.get(val_col), errors="coerce")
            if pd.isna(val):
                continue
            rows.append(
                {
                    "series_id": sid,
                    "period": period_val,
                    "value": val,
                    "unit": "%",
                    "source_primary": "stats_cn",
                    "raw_json": row.to_dict(),
                }
            )

    if fred_provider is not None:
        for sid in ("FEDFUNDS", "UNRATE", "DGS10", "DGS2", "CPIAUCSL"):
            try:
                df = fred_provider.fetch_series_df(sid)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            for _, row in df.tail(180).iterrows():
                fv = pd.to_numeric(row.get("value"), errors="coerce")
                if pd.isna(fv):
                    continue
                rows.append(
                    {
                        "series_id": f"US_{sid}",
                        "period": str(row.get("date") or ""),
                        "value": fv,
                        "unit": "",
                        "source_primary": "fred",
                        "raw_json": row.to_dict(),
                    }
                )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_macro_indicator_batch(db, rows)


def _sync_daily_basic(ts_provider: CnTushareProvider, trade_date: str) -> int:
    symbols = _load_symbol_universe(ts_provider)
    rows: list[dict] = []
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    for symbol in symbols:
        try:
            df = ts_provider.fetch_daily_basic_df(symbol, start_date, trade_date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(dt):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": dt.date(),
                    "pe": pd.to_numeric(row.get("pe"), errors="coerce"),
                    "pb": pd.to_numeric(row.get("pb"), errors="coerce"),
                    "ps": pd.to_numeric(row.get("ps"), errors="coerce"),
                    "total_mv": pd.to_numeric(row.get("total_mv"), errors="coerce"),
                    "circ_mv": pd.to_numeric(row.get("circ_mv"), errors="coerce"),
                    "turnover_rate": pd.to_numeric(row.get("turnover_rate"), errors="coerce"),
                    "free_share": pd.to_numeric(row.get("free_share"), errors="coerce"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_daily_basic_batch(db, rows)


def _sync_limit_list(ts_provider: CnTushareProvider, trade_date: str) -> int:
    rows: list[dict] = []
    try:
        df = ts_provider.fetch_limit_list_df(trade_date)
    except Exception:
        df = pd.DataFrame()
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            symbol = str(row.get("ts_code") or "").strip().upper()
            if not symbol:
                continue
            dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(dt):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": dt.date(),
                    "limit_type": row.get("limit"),
                    "fd_amount": pd.to_numeric(row.get("fd_amount"), errors="coerce"),
                    "open_times": pd.to_numeric(row.get("open_times"), errors="coerce"),
                    "lu_time": row.get("first_time"),
                    "last_time": row.get("last_time"),
                    "status": row.get("limit"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_limit_list_batch(db, rows)


def _sync_moneyflow_market(ts_provider: CnTushareProvider, trade_date: str) -> int:
    symbols = _load_symbol_universe(ts_provider)
    rows: list[dict] = []
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    for symbol in symbols:
        try:
            df = ts_provider.fetch_individual_moneyflow_df(symbol, start_date, trade_date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(dt):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": dt.date(),
                    "buy_sm": pd.to_numeric(row.get("buy_sm_amount"), errors="coerce"),
                    "buy_md": pd.to_numeric(row.get("buy_md_amount"), errors="coerce"),
                    "buy_lg": pd.to_numeric(row.get("buy_lg_amount"), errors="coerce"),
                    "buy_elg": pd.to_numeric(row.get("buy_elg_amount"), errors="coerce"),
                    "sell_sm": pd.to_numeric(row.get("sell_sm_amount"), errors="coerce"),
                    "sell_md": pd.to_numeric(row.get("sell_md_amount"), errors="coerce"),
                    "sell_lg": pd.to_numeric(row.get("sell_lg_amount"), errors="coerce"),
                    "sell_elg": pd.to_numeric(row.get("sell_elg_amount"), errors="coerce"),
                    "net_sm": pd.to_numeric(row.get("net_sm_amount"), errors="coerce"),
                    "net_md": pd.to_numeric(row.get("net_md_amount"), errors="coerce"),
                    "net_lg": pd.to_numeric(row.get("net_lg_amount"), errors="coerce"),
                    "net_elg": pd.to_numeric(row.get("net_elg_amount"), errors="coerce"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_moneyflow_batch(db, rows)


def _sync_margin_detail(ts_provider: CnTushareProvider, trade_date: str) -> int:
    symbols = _load_symbol_universe(ts_provider)
    rows: list[dict] = []
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    for symbol in symbols:
        try:
            df = ts_provider.fetch_margin_detail_df(symbol, start_date, trade_date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(dt):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": dt.date(),
                    "rzye": pd.to_numeric(row.get("rzye"), errors="coerce"),
                    "rzmre": pd.to_numeric(row.get("rzmre"), errors="coerce"),
                    "rqye": pd.to_numeric(row.get("rqye"), errors="coerce"),
                    "rqmcl": pd.to_numeric(row.get("rqmcl"), errors="coerce"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_margin_detail_batch(db, rows)


def _sync_hsgt_top10(ts_provider: CnTushareProvider, trade_date: str) -> int:
    symbols = _load_symbol_universe(ts_provider)
    rows: list[dict] = []
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    for symbol in symbols[:300]:
        try:
            df = ts_provider.fetch_hsgt_top10_df(symbol, start_date, trade_date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(dt):
                continue
            rows.append(
                {
                    "trade_date": dt.date(),
                    "symbol": symbol,
                    "market_type": row.get("market_type"),
                    "rank": pd.to_numeric(row.get("rank"), errors="coerce"),
                    "hold_amount": pd.to_numeric(row.get("amount"), errors="coerce"),
                    "net_buy": pd.to_numeric(row.get("net_amount"), errors="coerce"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_hsgt_top10_batch(db, rows)


def _sync_top_list_and_inst(ts_provider: CnTushareProvider, trade_date: str) -> tuple[int, int]:
    symbols = _load_symbol_universe(ts_provider)
    top_rows: list[dict] = []
    inst_rows: list[dict] = []
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    for symbol in symbols[:500]:
        try:
            top_df = ts_provider.fetch_top_list_df(symbol, start_date, trade_date)
        except Exception:
            top_df = pd.DataFrame()
        if top_df is not None and not top_df.empty:
            for idx, row in top_df.iterrows():
                dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
                if pd.isna(dt):
                    continue
                top_rows.append(
                    {
                        "trade_date": dt.date(),
                        "symbol": symbol,
                        "rank": int(idx + 1),
                        "close": pd.to_numeric(row.get("close"), errors="coerce"),
                        "pct_change": pd.to_numeric(row.get("pct_change"), errors="coerce"),
                        "turnover_rate": pd.to_numeric(row.get("turnover_rate"), errors="coerce"),
                        "l_buy": pd.to_numeric(row.get("l_buy"), errors="coerce"),
                        "l_sell": pd.to_numeric(row.get("l_sell"), errors="coerce"),
                        "source_primary": "cn_tushare",
                        "raw_json": row.to_dict(),
                    }
                )
    with get_marketdata_db_ctx() as db:
        top_count = market_data_service.upsert_top_list_batch(db, top_rows)
        inst_count = market_data_service.upsert_top_inst_batch(db, inst_rows)
    return top_count, inst_count


def _sync_stk_factor_pro_market(ts_provider: CnTushareProvider, trade_date: str) -> int:
    symbols = _load_symbol_universe(ts_provider)
    rows: list[dict] = []
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    for symbol in symbols:
        try:
            df = ts_provider.fetch_stk_factor_pro_df(symbol, start_date, trade_date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(dt):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": dt.date(),
                    "fd_amount": pd.to_numeric(row.get("fd_amount"), errors="coerce"),
                    "bid1_vol": pd.to_numeric(row.get("bid1_vol"), errors="coerce"),
                    "ask1_vol": pd.to_numeric(row.get("ask1_vol"), errors="coerce"),
                    "main_net_flow": pd.to_numeric(row.get("main_net_flow"), errors="coerce"),
                    "super_large_net": pd.to_numeric(row.get("super_large_net"), errors="coerce"),
                    "large_net": pd.to_numeric(row.get("large_net"), errors="coerce"),
                    "mid_net": pd.to_numeric(row.get("mid_net"), errors="coerce"),
                    "small_net": pd.to_numeric(row.get("small_net"), errors="coerce"),
                    "limit_up_days": pd.to_numeric(row.get("limit_up_days"), errors="coerce"),
                    "limit_up_height": pd.to_numeric(row.get("limit_up_height"), errors="coerce"),
                    "net_subscribe": pd.to_numeric(row.get("net_subscribe"), errors="coerce"),
                    "turnover_rate_z": pd.to_numeric(row.get("turnover_rate_z"), errors="coerce"),
                    "amplitude_pct": pd.to_numeric(row.get("amplitude_pct"), errors="coerce"),
                    "vol_ratio": pd.to_numeric(row.get("vol_ratio"), errors="coerce"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_stk_factor_pro_batch(db, rows)


def _sync_cyq_perf_market(ts_provider: CnTushareProvider, trade_date: str) -> int:
    symbols = _load_symbol_universe(ts_provider)
    rows: list[dict] = []
    start_date = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    for symbol in symbols:
        try:
            df = ts_provider.fetch_cyq_perf_df(symbol, start_date, trade_date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            dt = pd.to_datetime(row.get("trade_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(dt):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": dt.date(),
                    "his_low": pd.to_numeric(row.get("his_low"), errors="coerce"),
                    "his_high": pd.to_numeric(row.get("his_high"), errors="coerce"),
                    "cost_5pct": pd.to_numeric(row.get("cost_5pct"), errors="coerce"),
                    "cost_15pct": pd.to_numeric(row.get("cost_15pct"), errors="coerce"),
                    "cost_50pct": pd.to_numeric(row.get("cost_50pct"), errors="coerce"),
                    "cost_85pct": pd.to_numeric(row.get("cost_85pct"), errors="coerce"),
                    "cost_95pct": pd.to_numeric(row.get("cost_95pct"), errors="coerce"),
                    "weight_avg": pd.to_numeric(row.get("weight_avg"), errors="coerce"),
                    "winner_rate": pd.to_numeric(row.get("winner_rate"), errors="coerce"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_cyq_perf_batch(db, rows)


def _sync_fina_indicator_forecast_express(ts_provider: CnTushareProvider, trade_date: str) -> tuple[int, int, int]:
    symbols = _load_symbol_universe(ts_provider)
    fina_rows: list[dict] = []
    forecast_rows: list[dict] = []
    express_rows: list[dict] = []
    for symbol in symbols[:1200]:
        try:
            fina_df = ts_provider.fetch_fina_indicator_df(symbol, trade_date)
        except Exception:
            fina_df = pd.DataFrame()
        try:
            forecast_df = ts_provider.fetch_forecast_df(symbol, trade_date)
        except Exception:
            forecast_df = pd.DataFrame()
        try:
            express_df = ts_provider.fetch_express_df(symbol, trade_date)
        except Exception:
            express_df = pd.DataFrame()
        for _, row in fina_df.iterrows() if fina_df is not None else []:
            end_dt = pd.to_datetime(row.get("end_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(end_dt):
                continue
            fina_rows.append(
                {
                    "symbol": symbol,
                    "end_date": end_dt.date(),
                    "roe": pd.to_numeric(row.get("roe"), errors="coerce"),
                    "gross_margin": pd.to_numeric(row.get("grossprofit_margin"), errors="coerce"),
                    "debt_ratio": pd.to_numeric(row.get("debt_to_assets"), errors="coerce"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
        for rows_bucket, dfx in ((forecast_rows, forecast_df), (express_rows, express_df)):
            if dfx is None or dfx.empty:
                continue
            for _, row in dfx.iterrows():
                end_dt = pd.to_datetime(row.get("end_date"), format="%Y%m%d", errors="coerce")
                ann_dt = pd.to_datetime(row.get("ann_date"), format="%Y%m%d", errors="coerce")
                if pd.isna(end_dt) or pd.isna(ann_dt):
                    continue
                rows_bucket.append(
                    {
                        "symbol": symbol,
                        "end_date": end_dt.date(),
                        "ann_date": ann_dt.date(),
                        "source_primary": "cn_tushare",
                        "raw_json": row.to_dict(),
                    }
                )
    with get_marketdata_db_ctx() as db:
        a = market_data_service.upsert_fina_indicator_batch(db, fina_rows)
        b = market_data_service.upsert_forecast_batch(db, forecast_rows)
        c = market_data_service.upsert_express_batch(db, express_rows)
    return a, b, c


def _sync_holdernumber(ts_provider: CnTushareProvider, trade_date: str) -> int:
    symbols = _load_symbol_universe(ts_provider)
    rows: list[dict] = []
    for symbol in symbols[:1200]:
        try:
            df = ts_provider.fetch_holdernumber_df(symbol, trade_date)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            end_dt = pd.to_datetime(row.get("end_date"), format="%Y%m%d", errors="coerce")
            if pd.isna(end_dt):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "end_date": end_dt.date(),
                    "holder_num": pd.to_numeric(row.get("holder_num"), errors="coerce"),
                    "source_primary": "cn_tushare",
                    "raw_json": row.to_dict(),
                }
            )
    with get_marketdata_db_ctx() as db:
        return market_data_service.upsert_holdernumber_batch(db, rows)


async def run() -> None:
    """Long-running market data scheduler loop."""
    logger.info("[marketdata] loop started")
    ts_provider = _build_tushare_provider()
    ak_provider = CnAkshareProvider()
    juchao_provider = JuChaoProvider()
    stats_provider = StatsCnProvider()
    fred_provider = None
    if (os.getenv("FRED_API_KEY") or "").strip():
        fred_provider = FredProvider()
    if ts_provider is None:
        logger.warning("[marketdata] TUSHARE_TOKEN missing, loop disabled")
        return

    # In-memory once-per-day guards
    last_run: dict[str, str] = {}
    while True:
        await asyncio.sleep(30)
        if not _flag("TA_DATASOURCE_TIER3_ENABLED", "0"):
            continue
        if not _flag("TA_MARKETDATA_SYNC_ENABLED", "0"):
            continue
        today = _today_cn()
        hhmm = _now_hhmm()
        if not is_cn_trading_day(today):
            continue
        try:
            # sync_company_basic weekly (Monday 06:00+)
            if datetime.now(ZoneInfo("Asia/Shanghai")).weekday() == 0 and hhmm >= "06:00":
                key = f"company_basic:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_company_basic, ts_provider)
                    logger.info("[marketdata] sync_company_basic rows=%s", count)
                    last_run[key] = today

            # sync_daily_bar
            if hhmm >= "16:30":
                key = f"daily_bar:{today}"
                if last_run.get(key) != today:
                    compared, anomalies = await asyncio.to_thread(
                        _sync_daily_bar, ts_provider, ak_provider, today
                    )
                    logger.info(
                        "[marketdata] sync_daily_bar done compared=%s anomalies=%s",
                        compared,
                        anomalies,
                    )
                    last_run[key] = today

            if hhmm >= "16:40":
                key = f"daily_basic:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_daily_basic, ts_provider, today)
                    logger.info("[marketdata] sync_daily_basic rows=%s", count)
                    last_run[key] = today

            if hhmm >= "15:40":
                key = f"limit_list:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_limit_list, ts_provider, today)
                    logger.info("[marketdata] sync_limit_list rows=%s", count)
                    last_run[key] = today

            if hhmm >= "17:10":
                key = f"moneyflow:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_moneyflow_market, ts_provider, today)
                    logger.info("[marketdata] sync_moneyflow rows=%s", count)
                    last_run[key] = today

            # sync_north_money
            if hhmm >= "18:00":
                key = f"north_money:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_north_money, ts_provider, today)
                    logger.info("[marketdata] sync_north_money rows=%s", count)
                    last_run[key] = today

            if hhmm >= "21:30":
                key = f"hsgt_top10:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_hsgt_top10, ts_provider, today)
                    logger.info("[marketdata] sync_hsgt_top10 rows=%s", count)
                    last_run[key] = today

            if hhmm >= "21:00":
                key = f"margin_detail:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_margin_detail, ts_provider, today)
                    logger.info("[marketdata] sync_margin_detail rows=%s", count)
                    last_run[key] = today

            if hhmm >= "19:00":
                key = f"top_list_and_inst:{today}"
                if last_run.get(key) != today:
                    top_count, inst_count = await asyncio.to_thread(_sync_top_list_and_inst, ts_provider, today)
                    logger.info("[marketdata] sync_top_list rows=%s top_inst rows=%s", top_count, inst_count)
                    last_run[key] = today

            if hhmm >= "22:00":
                key = f"stk_factor_pro:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_stk_factor_pro_market, ts_provider, today)
                    logger.info("[marketdata] sync_stk_factor_pro rows=%s", count)
                    last_run[key] = today

            if hhmm >= "22:30":
                key = f"cyq_perf:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_cyq_perf_market, ts_provider, today)
                    logger.info("[marketdata] sync_cyq_perf rows=%s", count)
                    last_run[key] = today

            # sync_financial_report (1st or 15th monthly)
            sh_dt = datetime.now(ZoneInfo("Asia/Shanghai"))
            if sh_dt.day in (1, 15) and hhmm >= "23:00":
                key = f"financial_report:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_financial_report, ts_provider)
                    logger.info("[marketdata] sync_financial_report rows=%s", count)
                    last_run[key] = today

            if sh_dt.day in (1, 15) and hhmm >= "23:10":
                key = f"fina_forecast_express:{today}"
                if last_run.get(key) != today:
                    a, b, c = await asyncio.to_thread(_sync_fina_indicator_forecast_express, ts_provider, today)
                    logger.info("[marketdata] sync_fina_indicator rows=%s forecast rows=%s express rows=%s", a, b, c)
                    last_run[key] = today

            if sh_dt.weekday() == 0 and hhmm >= "06:30":
                key = f"holdernumber:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_holdernumber, ts_provider, today)
                    logger.info("[marketdata] sync_holdernumber rows=%s", count)
                    last_run[key] = today

            if hhmm >= "09:30":
                key = f"disclosure_am:{today}"
                if last_run.get(key) != today:
                    symbols = _load_symbol_universe(ts_provider)
                    count = await asyncio.to_thread(_sync_disclosure, juchao_provider, symbols, today)
                    logger.info("[marketdata] sync_disclosure_am rows=%s", count)
                    last_run[key] = today

            if hhmm >= "17:00":
                key = f"disclosure_pm:{today}"
                if last_run.get(key) != today:
                    symbols = _load_symbol_universe(ts_provider)
                    count = await asyncio.to_thread(_sync_disclosure, juchao_provider, symbols, today)
                    logger.info("[marketdata] sync_disclosure_pm rows=%s", count)
                    last_run[key] = today

            if _flag("TA_MACRO_SYNC_ENABLED", "0") and hhmm >= "20:30":
                key = f"macro:{today}"
                if last_run.get(key) != today:
                    count = await asyncio.to_thread(_sync_macro, stats_provider, fred_provider)
                    logger.info("[marketdata] sync_macro rows=%s", count)
                    last_run[key] = today

            if hhmm >= "02:00":
                key = f"vendor_call_log_cleanup:{today}"
                if last_run.get(key) != today:
                    with get_marketdata_db_ctx() as db:
                        cleaned = market_data_service.cleanup_vendor_call_log(db, retain_days=90)
                    logger.info("[marketdata] cleanup_vendor_call_log deleted=%s", cleaned)
                    last_run[key] = today
        except Exception as exc:
            logger.exception("[marketdata] loop tick failed: %s", exc)
