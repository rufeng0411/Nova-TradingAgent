from tradingagents.dataflows.interface import TOOLS_CATEGORIES, get_category_for_method


def test_new_tool_categories_registered():
    assert "valuation_data" in TOOLS_CATEGORIES
    assert "factor_data" in TOOLS_CATEGORIES
    assert "l2_data" in TOOLS_CATEGORIES


def test_new_methods_can_resolve_category():
    assert get_category_for_method("get_daily_basic") == "valuation_data"
    assert get_category_for_method("get_stk_factor_pro_window") == "factor_data"
    assert get_category_for_method("get_l2_orderqueue_window") == "l2_data"
    assert get_category_for_method("get_fina_indicator") == "fundamental_data"
