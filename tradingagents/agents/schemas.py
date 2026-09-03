"""Pydantic schemas for structured decision outputs."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from tradingagents.agents.utils.rating import PortfolioRating


class TraderAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ResearchPlan(BaseModel):
    direction: str = Field(description="偏多/中性/偏空")
    confidence: int = Field(ge=0, le=100, default=50)
    reason: str = Field(default="")


class TraderProposal(BaseModel):
    action: TraderAction
    confidence: int = Field(ge=0, le=100, default=50)
    rationale: str = Field(default="")


class PortfolioDecision(BaseModel):
    rating: PortfolioRating
    direction: str = Field(description="偏多/中性/偏空")
    confidence: int = Field(ge=0, le=100, default=50)
    summary: str = Field(default="")


def render_research_plan(plan: ResearchPlan) -> str:
    verdict = {
        "direction": plan.direction,
        "confidence": plan.confidence,
        "reason": plan.reason,
    }
    import json

    body = f"投资计划方向：{plan.direction}\n置信度：{plan.confidence}\n理由：{plan.reason}\n"
    return body + f"\n<!-- VERDICT: {json.dumps(verdict, ensure_ascii=False)} -->\n"


def render_trader_proposal(proposal: TraderProposal) -> str:
    action = proposal.action.value
    body = f"{proposal.rationale}\n\nFINAL TRANSACTION PROPOSAL: **{action}**\n"
    return body


def render_pm_decision(decision: PortfolioDecision) -> str:
    body = (
        f"沙盘综合研判结论：{decision.direction}\n"
        f"五档评级：{decision.rating.value}\n"
        f"置信度：{decision.confidence}\n"
        f"{decision.summary}\n"
    )
    import json

    verdict = {
        "direction": decision.direction,
        "confidence": decision.confidence,
        "reason": decision.summary,
        "rating_5tier": decision.rating.value,
    }
    return body + f"\n<!-- VERDICT: {json.dumps(verdict, ensure_ascii=False)} -->\n"
