from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider


class _FakePro:
    def daily(self, ts_code: str, start_date: str, end_date: str):
        assert ts_code == "600519.SH"
        assert start_date == "20250101"
        assert end_date == "20250110"
        return pd.DataFrame(
            [
                {
                    "ts_code": ts_code,
                    "trade_date": "20250110",
                    "open": 100.0,
                    "high": 110.0,
                    "low": 90.0,
                    "close": 105.0,
                    "vol": 1000,
                    "amount": 1_000_000,
                },
                {
                    "ts_code": ts_code,
                    "trade_date": "20250109",
                    "open": 95.0,
                    "high": 108.0,
                    "low": 92.0,
                    "close": 100.0,
                    "vol": 1200,
                    "amount": 1_200_000,
                },
            ]
        )

    def adj_factor(self, ts_code: str, start_date: str, end_date: str):
        return pd.DataFrame(
            [
                {"ts_code": ts_code, "trade_date": "20250109", "adj_factor": 1.0},
                {"ts_code": ts_code, "trade_date": "20250110", "adj_factor": 1.1},
            ]
        )

    def stock_basic(self, **kwargs):
        return pd.DataFrame([{"ts_code": "600519.SH", "name": "贵州茅台", "industry": "白酒", "market": "主板"}])

    def balancesheet(self, **kwargs):
        return pd.DataFrame([{"ts_code": "600519.SH", "ann_date": "20250331", "end_date": "20250331"}])

    def income(self, **kwargs):
        return pd.DataFrame([{"ts_code": "600519.SH", "ann_date": "20250331", "end_date": "20250331"}])

    def cashflow(self, **kwargs):
        return pd.DataFrame([{"ts_code": "600519.SH", "ann_date": "20250331", "end_date": "20250331"}])

    def moneyflow_hsgt(self, **kwargs):
        return pd.DataFrame([{"trade_date": "20250110", "north_money": 123.0}])


def _provider() -> CnTushareProvider:
    p = CnTushareProvider(token="test-token")
    p._client = _FakePro()
    return p


def test_fetch_daily_bar_df_returns_normalized_columns():
    p = _provider()
    df = p.fetch_daily_bar_df("600519.SH", "2025-01-01", "2025-01-10")
    assert list(df.columns) == ["Date", "Open", "High", "Low", "Close", "Volume", "Amount", "AdjFactor"]
    assert len(df) == 2
    assert df["Date"].iloc[-1].strftime("%Y-%m-%d") == "2025-01-10"


def test_get_stock_data_formats_csv_text():
    p = _provider()
    out = p.get_stock_data("600519.SH", "2025-01-01", "2025-01-10")
    assert out.startswith("# Stock data for 600519.SH")
    assert "Date,Open,High,Low,Close,Volume,Amount,AdjFactor" in out


def test_missing_token_raises_not_implemented():
    p = CnTushareProvider(token="")
    with pytest.raises(NotImplementedError):
        p.fetch_company_basic_df()


def test_fetch_company_basic_df():
    p = _provider()
    df = p.fetch_company_basic_df()
    assert not df.empty
    assert "ts_code" in df.columns


def test_get_balance_sheet_uses_financial_table():
    p = _provider()
    text = p.get_balance_sheet("600519.SH")
    assert "Balance Sheet" in text
    assert "600519.SH" in text
