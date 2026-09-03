import pytest

from tradingagents.dataflows.utils import safe_ticker_component


@pytest.mark.parametrize(
    "bad",
    [
        "../etc/passwd",
        "..\\windows\\system32",
        "foo/bar",
        "foo\\bar",
        "a\x00b",
    ],
)
def test_safe_ticker_rejects_malicious(bad):
    with pytest.raises(ValueError):
        safe_ticker_component(bad)


def test_safe_ticker_accepts_normal():
    assert safe_ticker_component("600519.SH") == "600519.SH"
    assert safe_ticker_component("000001.SZ") == "000001.SZ"
