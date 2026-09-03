from langchain_core.tools import tool
from typing import Annotated

from tradingagents.dataflows.local_first import route_with_local_first


@tool
def get_daily_basic(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期 YYYY-MM-DD"],
) -> str:
    """获取估值与换手率（daily_basic）窗口数据。"""
    return route_with_local_first("get_daily_basic", symbol, start_date, end_date)


@tool
def get_individual_money_flow_detail(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期 YYYY-MM-DD"],
) -> str:
    """获取个股主力资金流明细（Tushare moneyflow）。"""
    return route_with_local_first("get_individual_money_flow_detail", symbol, start_date, end_date)


@tool
def get_margin_detail(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期 YYYY-MM-DD"],
) -> str:
    """获取融资融券明细（margin_detail）。"""
    return route_with_local_first("get_margin_detail", symbol, start_date, end_date)


@tool
def get_hsgt_top10(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期 YYYY-MM-DD"],
) -> str:
    """获取北向持仓 Top10 变化。"""
    return route_with_local_first("get_hsgt_top10", symbol, start_date, end_date)


@tool
def get_opening_auction(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    date: Annotated[str, "交易日 YYYY-MM-DD"],
) -> str:
    """获取个股开盘集合竞价成交摘要（stk_auction）。"""
    return route_with_local_first("get_opening_auction", symbol, date)


@tool
def get_top_list_history(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期 YYYY-MM-DD"],
) -> str:
    """获取龙虎榜历史明细。"""
    return route_with_local_first("get_top_list_history", symbol, start_date, end_date)


@tool
def get_stk_factor_pro_window(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期 YYYY-MM-DD"],
) -> str:
    """获取专业因子窗口（stk_factor_pro）。"""
    return route_with_local_first("get_stk_factor_pro_window", symbol, start_date, end_date)


@tool
def get_cyq_perf(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    start_date: Annotated[str, "开始日期 YYYY-MM-DD"],
    end_date: Annotated[str, "结束日期 YYYY-MM-DD"],
) -> str:
    """获取筹码胜率窗口（cyq_perf）。"""
    return route_with_local_first("get_cyq_perf", symbol, start_date, end_date)


@tool
def get_cyq_chips(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    date: Annotated[str, "交易日 YYYY-MM-DD"],
) -> str:
    """获取指定交易日筹码分布（cyq_chips）。"""
    return route_with_local_first("get_cyq_chips", symbol, date)


@tool
def get_l2_orderqueue_window(
    symbol: Annotated[str, "股票代码，格式如 600519.SH"],
    date: Annotated[str, "交易日 YYYY-MM-DD"],
) -> str:
    """获取 Level2 委托队列（l2_orderqueue）。"""
    return route_with_local_first("get_l2_orderqueue_window", symbol, date)


@tool
def get_fina_indicator(
    ticker: Annotated[str, "股票代码，格式如 600519.SH"],
    curr_date: Annotated[str, "截止日期 YYYY-MM-DD"] = "",
) -> str:
    """获取财务指标（fina_indicator_vip）。"""
    return route_with_local_first("get_fina_indicator", ticker, curr_date)


@tool
def get_forecast(
    ticker: Annotated[str, "股票代码，格式如 600519.SH"],
    curr_date: Annotated[str, "截止日期 YYYY-MM-DD"] = "",
) -> str:
    """获取业绩预告（forecast_vip）。"""
    return route_with_local_first("get_forecast", ticker, curr_date)


@tool
def get_express(
    ticker: Annotated[str, "股票代码，格式如 600519.SH"],
    curr_date: Annotated[str, "截止日期 YYYY-MM-DD"] = "",
) -> str:
    """获取业绩快报（express_vip）。"""
    return route_with_local_first("get_express", ticker, curr_date)


@tool
def get_holdernumber_series(
    ticker: Annotated[str, "股票代码，格式如 600519.SH"],
    curr_date: Annotated[str, "截止日期 YYYY-MM-DD"] = "",
) -> str:
    """获取股东户数变化序列（stk_holdernumber）。"""
    return route_with_local_first("get_holdernumber_series", ticker, curr_date)
