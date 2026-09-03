from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class FastPositionInput(BaseModel):
    shares: Optional[float] = None
    avg_cost: Optional[float] = None
    portfolio_pct: Optional[float] = None
    available_cash_pct: Optional[float] = None


class FastAnalyzeRequest(BaseModel):
    symbol: str
    intent_hint: Optional[str] = None
    current_position: Optional[FastPositionInput] = None
    risk_profile: Optional[Literal["conservative", "balanced", "aggressive"]] = None
    include_market_context: bool = True
    model_override: Optional[str] = None


class FastAnalyzeResponse(BaseModel):
    fast_analysis_id: str
    job_id: str
    status: Literal["pending", "queued", "running", "succeeded", "degraded", "failed"]


class FastRiskProfileResponse(BaseModel):
    risk_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    fast_model: Optional[str] = None


class FastAnalysisDetailResponse(BaseModel):
    id: str
    status: str
    symbol: str
    symbol_name: Optional[str] = None
    trade_date: str
    created_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_ms: Optional[int] = None
    request_context_json: dict[str, Any] = Field(default_factory=dict)
    snapshot_json: dict[str, Any] = Field(default_factory=dict)
    features_json: dict[str, Any] = Field(default_factory=dict)
    kline_features_json: dict[str, Any] = Field(default_factory=dict)
    verdict_json: dict[str, Any] = Field(default_factory=dict)
    time_phased_json: dict[str, Any] = Field(default_factory=dict)
    position_advice_json: dict[str, Any] = Field(default_factory=dict)
    executability_json: dict[str, Any] = Field(default_factory=dict)
    kline_insight_json: dict[str, Any] = Field(default_factory=dict)

