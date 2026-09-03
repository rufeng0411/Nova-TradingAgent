from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.rating import (
    PortfolioRating,
    extract_rating_5tier_from_text,
    infer_rating_5tier,
)
from api.services import report_service


def test_infer_rating_5tier_bullish_high_confidence():
    assert infer_rating_5tier(direction="偏多", confidence=85, decision="BUY") == "Buy"


def test_infer_rating_5tier_bullish_moderate():
    assert infer_rating_5tier(direction="偏多", confidence=65, decision="BUY") == "Overweight"


def test_extract_from_render_pm_decision():
    text = render_pm_decision(
        PortfolioDecision(
            rating=PortfolioRating.OVERWEIGHT,
            direction="偏多",
            confidence=65,
            summary="summary",
        )
    )
    assert extract_rating_5tier_from_text(text) == "Overweight"


def test_resolve_report_fields_includes_rating_5tier():
    text = render_pm_decision(
        PortfolioDecision(
            rating=PortfolioRating.BUY,
            direction="偏多",
            confidence=90,
            summary="ok",
        )
    )
    resolved = report_service.resolve_report_fields(
        result_data={"final_trade_decision": text, "decision": "BUY"},
        confidence_override=90,
    )
    assert resolved["rating_5tier"] == "Buy"


def test_resolve_report_fields_infers_when_verdict_missing():
    resolved = report_service.resolve_report_fields(
        result_data={
            "final_trade_decision": "风控委员会批准观望方案。",
            "decision": "BUY",
        },
        confidence_override=85,
    )
    assert resolved["direction"] is None
    assert resolved["rating_5tier"] == "Buy"
