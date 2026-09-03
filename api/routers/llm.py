"""API routes for LLM catalog and provider preferences."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import uuid

from api.database import LlmProviderConfigDB, UserDB, get_db
from api.deps import _require_web_user
from tradingagents.llm_clients.model_catalog import build_catalog_response

router = APIRouter(prefix="/v1", tags=["llm"])


class LlmProviderConfigIn(BaseModel):
    provider: str
    region: str = "cn"
    deep_model: Optional[str] = None
    quick_model: Optional[str] = None
    custom_model_id: Optional[str] = None


@router.get("/llm/catalog")
def llm_catalog():
    if os.getenv("TA_UPGRADE_LLM_CATALOG", "0").strip().lower() not in ("1", "true", "yes", "on"):
        return {"providers": {}, "regions": [], "enabled": False}
    payload = build_catalog_response()
    payload["enabled"] = True
    return payload


@router.get("/llm/provider-config")
def get_llm_provider_config(
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_web_user),
):
    rows = (
        db.query(LlmProviderConfigDB)
        .filter(LlmProviderConfigDB.user_id == str(user.id))
        .all()
    )
    return {
        "items": [
            {
                "provider": r.provider,
                "region": r.region,
                "deep_model": r.deep_model,
                "quick_model": r.quick_model,
                "custom_model_id": r.custom_model_id,
            }
            for r in rows
        ]
    }


@router.put("/llm/provider-config")
def upsert_llm_provider_config(
    body: LlmProviderConfigIn,
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_web_user),
):
    row = (
        db.query(LlmProviderConfigDB)
        .filter(
            LlmProviderConfigDB.user_id == str(user.id),
            LlmProviderConfigDB.provider == body.provider,
            LlmProviderConfigDB.region == body.region,
        )
        .first()
    )
    if row is None:
        row = LlmProviderConfigDB(
            id=str(uuid.uuid4()),
            user_id=str(user.id),
            provider=body.provider,
            region=body.region,
        )
        db.add(row)
    row.deep_model = body.deep_model
    row.quick_model = body.quick_model
    row.custom_model_id = body.custom_model_id
    db.commit()
    return {"ok": True}
