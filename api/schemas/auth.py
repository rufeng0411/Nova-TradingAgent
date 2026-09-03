"""Auth-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    id: str
    email: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    role: str = "user"
    status: str = "active"
    credits: int = 0
    plan_code: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None
    phone_masked: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    email_report_enabled: bool = True
    wecom_report_enabled: bool = True
    admin_permissions: Optional[List[str]] = None

    model_config = {"from_attributes": True}


class CaptchaResponse(BaseModel):
    captcha_id: str = ""
    image: str = ""
    enabled: bool = True


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str = Field(..., min_length=3, max_length=50)
    email: str
    password: str
    phone: Optional[str] = None
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    identifier: str = Field(..., description="用户名或邮箱")
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
