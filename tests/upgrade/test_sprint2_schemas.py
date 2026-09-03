from tradingagents.agents.schemas import (
    PortfolioDecision,
    ResearchPlan,
    TraderProposal,
    TraderAction,
    render_pm_decision,
    render_research_plan,
    render_trader_proposal,
)
from tradingagents.agents.utils.rating import PortfolioRating, map_five_to_three, parse_rating


def test_render_research_plan_contains_verdict():
    text = render_research_plan(ResearchPlan(direction="偏多", confidence=70, reason="test"))
    assert "<!-- VERDICT:" in text
    assert "偏多" in text


def test_render_trader_proposal_trailing_line():
    text = render_trader_proposal(
        TraderProposal(action=TraderAction.BUY, confidence=80, rationale="ok")
    )
    assert "FINAL TRANSACTION PROPOSAL: **BUY**" in text


def test_render_pm_decision_five_tier():
    text = render_pm_decision(
        PortfolioDecision(
            rating=PortfolioRating.OVERWEIGHT,
            direction="偏多",
            confidence=65,
            summary="summary",
        )
    )
    assert "Overweight" in text or "五档评级" in text


def test_parse_rating_and_map():
    assert parse_rating("增持") == "Overweight"
    assert map_five_to_three("Overweight") == "BUY"
