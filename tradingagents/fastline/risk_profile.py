from __future__ import annotations

from typing import Literal, TypedDict

RiskProfileName = Literal["conservative", "balanced", "aggressive"]


class RiskProfileRule(TypedDict):
    max_position_pct: float
    stop_loss_atr_mult: float
    force_split_orders: bool


RISK_PROFILE_RULES: dict[RiskProfileName, RiskProfileRule] = {
    "conservative": {
        "max_position_pct": 0.20,
        "stop_loss_atr_mult": 1.0,
        "force_split_orders": True,
    },
    "balanced": {
        "max_position_pct": 0.35,
        "stop_loss_atr_mult": 1.5,
        "force_split_orders": False,
    },
    "aggressive": {
        "max_position_pct": 0.50,
        "stop_loss_atr_mult": 2.0,
        "force_split_orders": False,
    },
}


def normalize_risk_profile(raw: str | None) -> RiskProfileName:
    value = str(raw or "balanced").strip().lower()
    if value in RISK_PROFILE_RULES:
        return value  # type: ignore[return-value]
    return "balanced"


def get_risk_profile_rule(raw: str | None) -> RiskProfileRule:
    return RISK_PROFILE_RULES[normalize_risk_profile(raw)]

