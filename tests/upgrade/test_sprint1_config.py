from tradingagents.dataflows import config as dc


def test_set_config_preserves_sibling_defaults():
    dc.initialize_config()
    before_vendors = dict(dc.get_config()["data_vendors"])
    before_tools = dict(dc.get_config()["tool_vendors"])
    dc.set_config({"tool_vendors": {"fetch_stk_auction": "cn_tushare"}})
    after = dc.get_config()
    assert after["data_vendors"] == before_vendors
    assert "fetch_rt_daily_bar_df" in after["tool_vendors"]
    assert after["tool_vendors"]["fetch_stk_auction"] == "cn_tushare"
    # restore
    dc.set_config({"tool_vendors": before_tools, "data_vendors": before_vendors})
