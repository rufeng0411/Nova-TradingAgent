"""Ensure analysis jobs never prefer LLM Chinese-only tickers over normalized exchange codes."""

import pytest

pytestmark = pytest.mark.no_init_db

from api.symbol_utils import effective_data_ticker, normalize_exchange_symbol


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("宁德时代 300750.SZ", "300750.SZ"),
        ("300750.SZ宁德时代", "300750.SZ"),
        ("虚构公司名不存在于映射表ZZ", "虚构公司名不存在于映射表ZZ"),
        ("600519", "600519.SH"),
        ("920001.BJ", "920001.BJ"),
        ("920001", "920001.BJ"),
    ],
)
def test_normalize_symbol_extracts_listed_code(raw: str, expected: str) -> None:
    assert normalize_exchange_symbol(raw) == expected


def test_effective_data_ticker_prefers_request_over_chinese_intent() -> None:
    assert effective_data_ticker("300750.SZ", "宁德时代") == "300750.SZ"


def test_effective_data_ticker_uses_intent_when_request_not_listed() -> None:
    assert effective_data_ticker("虚构中文ZZ", "300750.SZ") == "300750.SZ"


def test_effective_data_ticker_us_ticker_not_replaced_by_chinese() -> None:
    assert effective_data_ticker("AAPL", "苹果公司") == "AAPL"


def test_intent_merge_prefers_fallback_when_llm_name_only() -> None:
    from tradingagents.ticker_merge import merge_llm_ticker_with_fallback

    assert merge_llm_ticker_with_fallback("宁德时代", "300750.SZ") == "300750.SZ"
    assert merge_llm_ticker_with_fallback("300750.SZ", "600519.SH") == "300750.SZ"
