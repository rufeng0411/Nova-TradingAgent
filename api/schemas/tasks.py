"""Schemas for user task queue center."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


TaskStatus = Literal["queued", "paused", "running", "completed", "failed"]
TaskSubmitStatus = Literal["pending", "queued", "rejected", "failed"]


class TaskCenterItem(BaseModel):
    job_id: str
    task_kind: str
    task_name: str
    description: Optional[str] = None
    symbol: Optional[str] = None
    trade_date: Optional[str] = None
    status: TaskStatus
    queue_status: Optional[Literal["queued", "paused"]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error: Optional[str] = None
    waiting_ahead_count: Optional[int] = None


class TaskCenterListResponse(BaseModel):
    running: list[TaskCenterItem] = Field(default_factory=list)
    queued: list[TaskCenterItem] = Field(default_factory=list)
    recent: list[TaskCenterItem] = Field(default_factory=list)


class TaskReorderRequest(BaseModel):
    job_ids: list[str] = Field(default_factory=list)


class TaskOperationResponse(BaseModel):
    ok: bool = True
    job_id: str
    status: str
    detail: Optional[str] = None


class TaskSubmitRequest(BaseModel):
    text: str = Field(..., min_length=1)
    selected_analysts: list[str] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals", "macro", "smart_money", "volume_price"]
    )
    config_overrides: dict = Field(default_factory=dict)
    dry_run: bool = False
    objective: Optional[str] = None
    risk_profile: Optional[str] = None
    investment_horizon: Optional[str] = None
    cash_available: Optional[float] = None
    current_position: Optional[float] = None
    current_position_pct: Optional[float] = None
    average_cost: Optional[float] = None
    max_loss_pct: Optional[float] = None
    constraints: list[str] = Field(default_factory=list)
    user_notes: Optional[str] = None


class TaskSubmitResponse(BaseModel):
    job_id: str
    status: TaskSubmitStatus
    symbol: Optional[str] = None
    trade_date: Optional[str] = None
    task_label: Optional[str] = None
    waiting_ahead_count: int = 0
    message: Optional[str] = None
