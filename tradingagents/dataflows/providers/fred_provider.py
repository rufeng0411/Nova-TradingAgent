from __future__ import annotations

import os
import requests
import pandas as pd

from .base import BaseMarketDataProvider


class FredProvider(BaseMarketDataProvider):
    """US macro data provider via FRED."""

    @property
    def name(self) -> str:
        return "fred"

    def _api_key(self) -> str:
        key = (os.getenv("FRED_API_KEY") or "").strip()
        if not key:
            raise NotImplementedError("FRED_API_KEY is required for fred provider")
        return key

    def fetch_series_df(
        self, series_id: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        params = {
            "series_id": series_id,
            "api_key": self._api_key(),
            "file_type": "json",
        }
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date
        resp = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params=params,
            timeout=12,
        )
        resp.raise_for_status()
        body = resp.json()
        obs = body.get("observations") or []
        return pd.DataFrame(obs)

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("fred only supports macro series")

    def get_indicators(self, symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
        raise NotImplementedError("fred only supports macro series")

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError("fred only supports macro series")

    def get_balance_sheet(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("fred only supports macro series")

    def get_cashflow(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("fred only supports macro series")

    def get_income_statement(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("fred only supports macro series")

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("fred only supports macro series")

    def get_global_news(self, curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
        raise NotImplementedError("fred only supports macro series")

    def get_insider_transactions(self, symbol: str) -> str:
        raise NotImplementedError("fred only supports macro series")
