"""Regression: chart insight prompts stay JSON-only and level-aware."""

from tradingagents.analytics.insight_prompt import (
    build_chart_insight_system_prompt,
    build_chart_insight_user_prompt,
)


def test_system_prompt_contains_level_persona_and_json_rules():
    brief = build_chart_insight_system_prompt("brief")
    assert "快速" in brief or "Desk Brief" in brief
    assert "JSON" in brief
    assert "bias" in brief

    deep = build_chart_insight_system_prompt("deep")
    assert "专业" in deep or "资深技术" in deep
    assert "若…则…" in deep or "若...则..." in deep


def test_user_prompt_maps_levels_to_product_labels():
    feats = {"bars": 60, "insight_level": "deep", "total_return_pct": 1.0}
    u = build_chart_insight_user_prompt("600519.SH", feats, "deep", "zh")
    assert "600519.SH" in u
    assert "专业" in u
    assert "deep" in u

    u2 = build_chart_insight_user_prompt("600519.SH", feats, "brief", "zh")
    assert "快速" in u2


def test_user_prompt_deep_asks_for_extended_fields_when_present():
    feats = {
        "bars": 60,
        "rsi14_last": 55.0,
        "close_vs_ma20_pct": 0.5,
        "volume_vs_ma20_ratio": 1.2,
    }
    u = build_chart_insight_user_prompt("000001.SH", feats, "deep", "zh")
    assert "rsi14_last" in u or "交叉引用" in u
