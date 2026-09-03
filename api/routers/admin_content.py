"""Admin content API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.database import UserDB, get_db
from api.deps import _require_admin_content
from api.services import admin_confirm_service, admin_content_service, admin_service

router = APIRouter(prefix="/v1/admin/content", tags=["admin-content"])


class ContentBlockUpsert(BaseModel):
    title: str = Field(..., min_length=1)
    content: Any
    status: str = Field("draft", pattern="^(draft|published|archived)$")


class AssetCreate(BaseModel):
    name: str
    type: str = Field(..., pattern="^(image|document|qr|brand)$")
    url: str = Field(..., min_length=4)
    tags: Optional[List[str]] = None


class SiteMessageCreate(BaseModel):
    title: str
    body: str
    audience: str = "all"
    status: str = Field("draft", pattern="^(draft|published)$")


class AppearancePatch(BaseModel):
    values: Dict[str, Any]


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/blocks")
def content_blocks_list(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_content)):
    rows = admin_content_service.list_blocks(db)
    return {
        "items": [
            {
                "key": r.key,
                "title": r.title,
                "content_json": r.content_json,
                "status": r.status,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
    }


@router.put("/blocks/{key}")
def content_blocks_put(
    key: str,
    body: ContentBlockUpsert,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_content),
    x_admin_confirm: Optional[str] = Header(None, alias="X-Admin-Confirm"),
):
    if body.status == "published":
        if not admin_confirm_service.consume_token(db, admin.id, x_admin_confirm):
            raise HTTPException(
                status_code=412,
                detail="发布内容需二次确认（X-Admin-Confirm）。",
            )
    r = admin_content_service.upsert_block(
        db, key=key, title=body.title, content=body.content, status=body.status, updated_by=admin.id
    )
    admin_service._audit(db, admin_id=admin.id, action="content.block.upsert", payload={"key": key}, ip=_ip(request))
    return {"key": r.key, "title": r.title, "status": r.status}


@router.get("/assets")
def content_assets_list(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_content)):
    rows = admin_content_service.list_assets(db)
    return {
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "url": a.url,
                "tags_json": a.tags_json,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ]
    }


@router.post("/assets")
def content_assets_create(
    body: AssetCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_content),
):
    a = admin_content_service.create_asset(
        db, name=body.name, type_=body.type, url=body.url, tags=body.tags, created_by=admin.id
    )
    admin_service._audit(db, admin_id=admin.id, action="content.asset.create", payload={"id": a.id}, ip=_ip(request))
    return {"id": a.id}


@router.get("/messages")
def content_messages_list(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_content)):
    rows = admin_content_service.list_messages(db)
    return {
        "items": [
            {
                "id": m.id,
                "title": m.title,
                "audience": m.audience,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]
    }


@router.post("/messages")
def content_messages_create(
    body: SiteMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_content),
    x_admin_confirm: Optional[str] = Header(None, alias="X-Admin-Confirm"),
):
    if body.status == "published":
        if not admin_confirm_service.consume_token(db, admin.id, x_admin_confirm):
            raise HTTPException(status_code=412, detail="全站/角色发送需二次确认（X-Admin-Confirm）。")
    m = admin_content_service.create_message(
        db, title=body.title, body=body.body, audience=body.audience, status=body.status, created_by=admin.id
    )
    admin_service._audit(db, admin_id=admin.id, action="content.message.create", payload={"id": m.id}, ip=_ip(request))
    return {"id": m.id}


@router.get("/appearance")
def content_appearance_get(db: Session = Depends(get_db), _: UserDB = Depends(_require_admin_content)):
    return admin_content_service.get_appearance(db)


@router.patch("/appearance")
def content_appearance_patch(
    body: AppearancePatch,
    request: Request,
    db: Session = Depends(get_db),
    admin: UserDB = Depends(_require_admin_content),
):
    out = admin_content_service.patch_appearance(db, body.values, updated_by=admin.id)
    admin_service._audit(db, admin_id=admin.id, action="content.appearance.patch", payload={"keys": list(body.values.keys())}, ip=_ip(request))
    return out
