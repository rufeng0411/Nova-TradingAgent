from __future__ import annotations

from datetime import datetime
import os
import requests
import pandas as pd

from .base import BaseMarketDataProvider


class JuChaoProvider(BaseMarketDataProvider):
    """Disclosure provider for cninfo announcements."""

    @property
    def name(self) -> str:
        return "juchao"

    def fetch_disclosure_df(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        ann_type: str | None = None,
    ) -> pd.DataFrame:
        root = (os.getenv("JUCHAO_BASE_URL") or "http://www.cninfo.com.cn").rstrip("/")
        base_url = f"{root}/new/hisAnnouncement/query"
        sec_code = symbol.split(".")[0]
        payload = {
            "pageNum": 1,
            "pageSize": 30,
            "column": "szse",
            "tabName": "fulltext",
            "plate": "sz",
            "stock": f"{sec_code},{sec_code}",
            "searchkey": "",
            "secid": "",
            "category": ann_type or "",
            "trade": "",
            "seDate": f"{start_date}~{end_date}",
            "sortName": "time",
            "sortType": "desc",
            "isHLtitle": "true",
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        }
        resp = requests.post(base_url, data=payload, headers=headers, timeout=12)
        resp.raise_for_status()
        body = resp.json()
        rows = body.get("announcements") or []
        out = []
        for row in rows:
            ts = row.get("announcementTime")
            ann_time = (
                datetime.fromtimestamp(ts / 1000).isoformat() if isinstance(ts, (int, float)) else None
            )
            out.append(
                {
                    "id": str(row.get("announcementId") or ""),
                    "symbol": symbol,
                    "title": row.get("announcementTitle"),
                    "ann_type": row.get("announcementTypeName"),
                    "ann_time": ann_time,
                    "url": f"http://static.cninfo.com.cn/{row.get('adjunctUrl','')}" if row.get("adjunctUrl") else None,
                    "raw_json": row,
                }
            )
        return pd.DataFrame(out)

    # Base interface methods: not part of this provider scope.
    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("juchao only supports disclosure data")

    def get_indicators(self, symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
        raise NotImplementedError("juchao only supports disclosure data")

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError("juchao only supports disclosure data")

    def get_balance_sheet(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("juchao only supports disclosure data")

    def get_cashflow(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("juchao only supports disclosure data")

    def get_income_statement(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        raise NotImplementedError("juchao only supports disclosure data")

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("juchao only supports disclosure data")

    def get_global_news(self, curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
        raise NotImplementedError("juchao only supports disclosure data")

    def get_insider_transactions(self, symbol: str) -> str:
        raise NotImplementedError("juchao only supports disclosure data")
