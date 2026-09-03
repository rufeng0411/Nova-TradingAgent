"""Admin step-up confirmation tokens (DB-backed, multi-worker safe)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from api.database import AdminConfirmTokenDB
from api.services.auth_service import _secret_key

_TTL_SEC = 300


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hash_token(raw: str) -> str:
    key = _secret_key().encode("utf-8")
    return hmac.new(key, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_token(db: Session, admin_id: str, created_ip: Optional[str] = None) -> Tuple[str, float]:
    raw = secrets.token_urlsafe(32)
    th = _hash_token(raw)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=_TTL_SEC)
    row = AdminConfirmTokenDB(
        id=str(uuid4()),
        token_hash=th,
        admin_id=admin_id,
        scope=None,
        expires_at=exp,
        consumed_at=None,
        created_ip=created_ip,
        created_at=now,
    )
    db.add(row)
    db.commit()
    return raw, exp.timestamp()


def verify_token(db: Session, admin_id: str, token: Optional[str]) -> bool:
    if not token:
        return False
    th = _hash_token(token)
    row = db.query(AdminConfirmTokenDB).filter(AdminConfirmTokenDB.token_hash == th).first()
    if not row:
        return False
    now = datetime.now(timezone.utc)
    if row.consumed_at is not None or _as_utc_aware(row.expires_at) < now or row.admin_id != admin_id:
        return False
    return True


def consume_token(db: Session, admin_id: str, token: Optional[str]) -> bool:
    if not token:
        return False
    th = _hash_token(token)
    row = db.query(AdminConfirmTokenDB).filter(AdminConfirmTokenDB.token_hash == th).first()
    if not row:
        return False
    now = datetime.now(timezone.utc)
    if row.consumed_at is not None or _as_utc_aware(row.expires_at) < now or row.admin_id != admin_id:
        return False
    row.consumed_at = now
    db.add(row)
    db.commit()
    return True
