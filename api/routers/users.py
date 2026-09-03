"""Current-user profile routes."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.database import UserDB, get_db
from api.deps import _require_web_user
from api.schemas.auth import ChangePasswordRequest
from api.services import auth_service
from api.services.entitlements_service import user_entitlements_payload

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/entitlements")
def get_my_entitlements(db: Session = Depends(get_db), current_user: UserDB = Depends(_require_web_user)):
    """当前账号的功能权益（高级行情等），用于前端展示锁定态与路由。"""
    return user_entitlements_payload(db, current_user)


class MePatchRequest(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None


@router.patch("/me")
def patch_me(
    body: MePatchRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    u = db.query(UserDB).filter(UserDB.id == current_user.id).first()
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    if body.email:
        em = auth_service.normalize_email(body.email)
        if not re.match(r"^[^@\s]+@[^@\s.]+\.[^@\s.]+$", em):
            raise HTTPException(status_code=400, detail="invalid_email")
        other = db.query(UserDB).filter(UserDB.email == em, UserDB.id != u.id).first()
        if other:
            raise HTTPException(status_code=400, detail="email_taken")
        u.email = em
    if body.display_name is not None:
        u.display_name = body.display_name.strip() or None
    if body.phone is not None:
        u.phone_encrypted = auth_service.encrypt_secret(body.phone.strip()) if body.phone.strip() else None
    u.updated_at = auth_service._utcnow()
    db.commit()
    return {"message": "ok"}


@router.post("/me/change-password")
def change_me_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_web_user),
):
    try:
        auth_service.change_password(db, current_user.id, body.old_password, body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"message": "ok"}
