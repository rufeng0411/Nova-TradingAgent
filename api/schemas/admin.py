"""Admin API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AdminUserListItem(BaseModel):
    id: str
    email: str
    username: Optional[str] = None
    role: str = "user"
    status: str = "active"
    credits: int = 0
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AdminUserListResponse(BaseModel):
    total: int
    items: List[AdminUserListItem]


class AdminUserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    admin_permissions: Optional[List[str]] = None


class AdminResetPasswordBody(BaseModel):
    new_password: str


class AdminAdjustCreditsBody(BaseModel):
    delta: int
    reason: str = "admin_adjust"


class AdminSubscriptionBody(BaseModel):
    plan_code: str
    days: int = 30
    status: str = "active"


class AdminDashboardOut(BaseModel):
    total_users: int
    users_today: int
    credits_consumed_today: int
    active_subscriptions: int


class AdminConfirmBody(BaseModel):
    password: str = Field(..., min_length=1)


class AdminFeaturePatchBody(BaseModel):
    key: str
    value: Any


class AdminBootstrapOut(BaseModel):
    admin: Dict[str, Any]
    features: Dict[str, Any]
    server_time: datetime
    api_version: str
    enabled_modules: Dict[str, bool] = Field(
        default_factory=lambda: {
            "reports": True,
            "commerce": True,
            "ops": True,
            "security": True,
            "content": True,
        }
    )


class AccessLogOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    ip: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AccessLogListResponse(BaseModel):
    total: int
    items: List[AccessLogOut]


class AdminAuditOut(BaseModel):
    id: str
    admin_id: str
    action: str
    target_user_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    ip: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PlanAdminCreate(BaseModel):
    code: str
    name: str
    price_cents: int = 0
    currency: str = "CNY"
    period_days: int = 30
    monthly_credits: int = 0
    is_active: bool = True
    sort_order: int = 0


class PlanAdminPatch(BaseModel):
    name: Optional[str] = None
    price_cents: Optional[int] = None
    monthly_credits: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
