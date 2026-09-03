from __future__ import annotations

from typing import Any

DATA_KEY_DISPLAY: dict[str, tuple[str, str]] = {
    "stock_data": ("日K线", "core_stock_apis"),
    "indicators": ("技术指标", "internal"),
    "vpa_indicators": ("量价分析", "internal"),
    "news": ("个股新闻", "news_data"),
    "global_news": ("全球/宏观新闻", "news_data"),
    "fund_flow_board": ("板块资金流", "cn_market_data"),
    "fund_flow_individual": ("个股资金流", "cn_market_data"),
    "lhb": ("龙虎榜", "cn_market_data"),
    "zt_pool": ("涨停池", "cn_market_data"),
    "hot_stocks": ("雪球热搜", "cn_market_data"),
    "insider_transactions": ("内部/股东交易", "news_data"),
    "fundamentals": ("基本面", "fundamental_data"),
    "balance_sheet": ("资产负债表", "fundamental_data"),
    "cashflow": ("现金流量表", "fundamental_data"),
    "income_statement": ("利润表", "fundamental_data"),
    "daily_basic_window": ("估值与换手", "valuation_data"),
    "individual_money_flow_detail": ("主力资金流明细", "cn_market_data"),
    "margin_detail_window": ("融资融券明细", "cn_market_data"),
    "hsgt_top10_window": ("北向持仓Top10", "cn_market_data"),
    "opening_auction": ("开盘集合竞价", "cn_market_data"),
    "opening_auction_o": ("开盘前竞价快照（o）", "cn_market_data"),
    "opening_auction_c": ("尾盘竞价快照（c）", "cn_market_data"),
    "opening_auction_signal": ("竞价强弱信号", "internal"),
    "auction_intraday_strength": ("竞价时段强度信号", "internal"),
    "top_list_history": ("龙虎榜历史", "cn_market_data"),
    "stk_factor_pro_window": ("专业因子（stk_factor_pro）", "factor_data"),
    "cyq_perf_window": ("筹码胜率", "factor_data"),
    "cyq_chips_recent": ("筹码分布", "factor_data"),
    "l2_orderqueue_recent": ("L2委托队列", "l2_data"),
    "orderbook_pressure_signal": ("盘口压力代理", "internal"),
    "active_buy_proxy": ("主动买入近似", "internal"),
    "moneyflow_structure": ("资金流结构信号", "internal"),
    "financial_health": ("财务健康度信号", "internal"),
    "fina_indicator": ("财务指标（VIP）", "fundamental_data"),
    "forecast": ("业绩预告（VIP）", "fundamental_data"),
    "express": ("业绩快报（VIP）", "fundamental_data"),
    "holdernumber_series": ("股东户数变化", "fundamental_data"),
    "disclosure_snapshot": ("公告披露快照", "news_data"),
    "macro_cn_snapshot": ("中国宏观快照", "news_data"),
    "macro_us_snapshot": ("美国宏观快照", "news_data"),
}

VENDOR_META: dict[str, dict[str, str]] = {
    "cn_akshare": {"display": "AkShare（聚合东财/新浪/腾讯/雪球）", "site": "https://akshare.akfamily.xyz/"},
    "cn_baostock": {"display": "BaoStock", "site": "http://baostock.com/"},
    "cn_tushare": {"display": "Tushare Pro", "site": "https://tushare.pro/"},
    "juchao": {"display": "巨潮资讯（CNINFO）", "site": "http://www.cninfo.com.cn/"},
    "stats_cn": {"display": "国家统计局/宏观数据", "site": "http://data.stats.gov.cn/"},
    "fred": {"display": "FRED（圣路易斯联储）", "site": "https://fred.stlouisfed.org/"},
    "yfinance": {"display": "Yahoo Finance", "site": "https://finance.yahoo.com/"},
    "alpha_vantage": {"display": "Alpha Vantage", "site": "https://www.alphavantage.co/"},
    "internal": {"display": "本地计算（指标/VPA）", "site": ""},
}


def enrich_data_source_item(key: str, meta: dict[str, Any]) -> dict[str, Any]:
    display_name, category = DATA_KEY_DISPLAY.get(key, (key, meta.get("category") or "unknown"))
    fallback_chain = meta.get("fallback_chain")
    fallback_vendor = None
    if isinstance(fallback_chain, list) and fallback_chain:
        first = fallback_chain[0]
        if isinstance(first, str) and first.strip():
            fallback_vendor = first.strip()
    vendor = meta.get("vendor") or fallback_vendor
    vendor_info = VENDOR_META.get(vendor or "", {})
    item = dict(meta)
    item.update(
        {
            "key": key,
            "display_name": display_name,
            "category": category,
            "vendor": vendor,
            "vendor_display": vendor_info.get("display", vendor or "未知来源"),
            "vendor_site": vendor_info.get("site", ""),
        }
    )
    return item
