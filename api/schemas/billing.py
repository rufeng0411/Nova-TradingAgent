"""Billing / subscription schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    id: str
    code: str
    name: str
    price_cents: int
    currency: str
    period_days: int
    monthly_credits: int
    features: List[Any] = Field(default_factory=list)
    is_active: bool = True
    sort_order: int = 0

    model_config = {"from_attributes": True}


class BalanceOut(BaseModel):
    credits: int
    plan_code: Optional[str] = None
    subscription_status: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None


class CreditTransactionOut(BaseModel):
    id: str
    delta: int
    type: str
    reason: Optional[str] = None
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    balance_after: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    total: int
    items: List[CreditTransactionOut]


class SubscriptionOut(BaseModel):
    id: str
    plan_id: str
    plan_code: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    auto_renew: bool = False

    model_config = {"from_attributes": True}


class SubscribeRequest(BaseModel):
    plan_code: str = Field(..., description="目标套餐 code，如 pro")
