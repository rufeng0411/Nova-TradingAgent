from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider


class _DummyPro:
    def __getattr__(self, name):
        def _call(**kwargs):
            return None

        return _call


def test_extended_methods_return_string_with_empty_df(monkeypatch):
    p = CnTushareProvider(token="dummy")
    monkeypatch.setattr(p, "_pro", lambda: _DummyPro())
    monkeypatch.setattr(p, "_normalize_symbol", lambda s: "600519.SH")
    monkeypatch.setattr(p, "_to_ymd", lambda s: "20260101")

    assert "无数据" in p.get_daily_basic("600519.SH", "2026-01-01", "2026-01-10")
    assert "无数据" in p.get_stk_factor_pro_window("600519.SH", "2026-01-01", "2026-01-10")
    assert "无数据" in p.get_cyq_chips("600519.SH", "2026-01-10")
    assert "无数据" in p.get_l2_orderqueue_window("600519.SH", "2026-01-10")
    assert p.fetch_opening_auction_o_df("600519.SH", "2026-01-10").empty
    assert p.fetch_opening_auction_c_df("600519.SH", "2026-01-10").empty
