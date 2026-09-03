from __future__ import annotations

from langchain_core.tools import tool
from typing import Annotated
from datetime import datetime

from api.database import (
    MarketDataDisclosureDB,
    MarketDataMacroIndicatorDB,
    get_marketdata_db_ctx,
    is_marketdata_db_healthy,
)


@tool
def query_macro_series(
    series_id: Annotated[str, "series id such as CN_CPI_YOY, CN_M2_YOY, US_FEDFUNDS"],
    start_date: Annotated[str, "start date YYYY-mm-dd"],
    end_date: Annotated[str, "end date YYYY-mm-dd"],
) -> str:
    """查询已同步的宏观指标时间序列（按月），用于宏观报告引用。"""
    if not is_marketdata_db_healthy():
        return "市场数据仓不可用，宏观序列降级为实时拉取路径。"
    with get_marketdata_db_ctx() as db:
        rows = (
            db.query(MarketDataMacroIndicatorDB)
            .filter(
                MarketDataMacroIndicatorDB.series_id == series_id,
                MarketDataMacroIndicatorDB.period >= start_date[:7],
                MarketDataMacroIndicatorDB.period <= end_date[:7],
            )
            .order_by(MarketDataMacroIndicatorDB.period.asc())
            .all()
        )
    if not rows:
        return f"未查询到序列 {series_id} 在 {start_date}~{end_date} 的数据"
    lines = ["period,value,unit,source"]
    for row in rows:
        lines.append(
            f"{row.period},{row.value if row.value is not None else ''},{row.unit or ''},{row.source_primary or ''}"
        )
    return "\n".join(lines)


@tool
def query_disclosure(
    symbol: Annotated[str, "ticker symbol like 600519.SH"],
    start_date: Annotated[str, "start date YYYY-mm-dd"],
    end_date: Annotated[str, "end date YYYY-mm-dd"],
    ann_type: Annotated[str, "optional announcement type filter"] = "",
) -> str:
    """查询标的在日期区间内的公告披露摘要（结构化入库数据），供新闻/合规分析引用。"""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return f"日期格式错误：{start_date} ~ {end_date}"
    if not is_marketdata_db_healthy():
        return f"{symbol} 公告库暂不可用，已降级到非结构化新闻路径"
    with get_marketdata_db_ctx() as db:
        q = (
            db.query(MarketDataDisclosureDB)
            .filter(
                MarketDataDisclosureDB.symbol == symbol.strip().upper(),
                MarketDataDisclosureDB.ann_time >= start_dt,
                MarketDataDisclosureDB.ann_time <= end_dt.replace(hour=23, minute=59, second=59),
            )
            .order_by(MarketDataDisclosureDB.ann_time.desc())
        )
        if ann_type:
            q = q.filter(MarketDataDisclosureDB.ann_type.contains(ann_type))
        rows = q.limit(20).all()
    if not rows:
        return f"{symbol} 在 {start_date}~{end_date} 无公告记录"
    lines = ["time,type,title,url,source"]
    for row in rows:
        time_val = row.ann_time.isoformat() if row.ann_time else ""
        lines.append(
            f"{time_val},{row.ann_type or ''},{(row.title or '').replace(',', '，')},{row.url or ''},{row.source_primary or ''}"
        )
    return "\n".join(lines)
