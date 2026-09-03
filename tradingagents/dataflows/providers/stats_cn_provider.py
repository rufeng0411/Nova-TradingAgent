from __future__ import annotations

import pandas as pd

from .base import BaseMarketDataProvider


class StatsCnProvider(BaseMarketDataProvider):
    """Macro indicator provider using AkShare wrappers / public CN stats."""

    @property
    def name(self) -> str:
        return "stats_cn"

    def fetch_macro_series_df(self, series_id: str) -> pd.DataFrame:
        try:
            import akshare as ak  # type: ignore
        except ImportError as exc:
            raise NotImplementedError("stats_cn requires akshare for macro wrappers") from exc

        map_fn = {
            "CN_CPI_YOY": getattr(ak, "macro_china_cpi_yearly", None),
            "CN_PPI_YOY": getattr(ak, "macro_china_ppi_yearly", None),
            "CN_M2_YOY": getattr(ak, "macro_china_money_supply", None),
            "CN_GDP_YOY": getattr(ak, "macro_china_gdp_yearly", None),
        }
        fn = map_fn.get(series_id)
        if fn is None:
            raise NotImplementedError(f"Unsupported series_id: {series_id}")
        df = fn()
        return df if df is not None else pd.DataFrame()

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("stats_cn only supports macro series")

    def get_indicators(self, symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
        raise NotImplementedError("stats_cn only supports macro series")

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError("stats_cn only supports macro series")

    def get_balance_sheet(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("stats_cn only supports macro series")

    def get_cashflow(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("stats_cn only supports macro series")

    def get_income_statement(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("stats_cn only supports macro series")

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("stats_cn only supports macro series")

    def get_global_news(self, curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
        raise NotImplementedError("stats_cn only supports macro series")

    def get_insider_transactions(self, symbol: str) -> str:
        raise NotImplementedError("stats_cn only supports macro series")
