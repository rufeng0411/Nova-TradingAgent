"""Strip machine-readable debate markers from public-facing markdown."""

from tradingagents.agents.utils.debate_utils import strip_public_debate_machine_blocks


def test_strip_nested_debate_state_and_label():
    raw = """结论段落。

机读块
<!-- DEBATE_STATE: {"responded_claim_ids": ["INV-3"], "new_claims": [{"claim": "x", "evidence": ["a", "b"], "confidence": 0.5}], "resolved_claim_ids": [], "unresolved_claim_ids": [], "next_focus_claim_ids": [], "round_summary": "s", "round_goal": "g"} -->

尾部。
"""
    out = strip_public_debate_machine_blocks(raw)
    assert "<!-- DEBATE_STATE" not in out
    assert "机读块" not in out
    assert "结论段落" in out
    assert "尾部" in out


def test_strip_risk_state():
    raw = '分析\n<!-- RISK_STATE: {"a": {"b": 1}} -->\n完'
    out = strip_public_debate_machine_blocks(raw)
    assert "<!-- RISK_STATE" not in out
    assert "分析" in out
    assert "完" in out
