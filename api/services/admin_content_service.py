"""Admin content: home blocks, assets, site messages, appearance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from api.database import AdminContentBlockDB, AppearanceSettingDB, AssetLibraryItemDB, SiteMessageDB


def _now() -> datetime:
    return datetime.now(timezone.utc)


def list_blocks(db: Session) -> List[AdminContentBlockDB]:
    return db.query(AdminContentBlockDB).order_by(AdminContentBlockDB.key.asc()).all()


def upsert_block(db: Session, key: str, title: str, content: Any, status: str, updated_by: Optional[str]) -> AdminContentBlockDB:
    row = db.query(AdminContentBlockDB).filter(AdminContentBlockDB.key == key).first()
    body = json.dumps(content, ensure_ascii=False) if not isinstance(content, str) else content
    if row:
        row.title = title
        row.content_json = body
        row.status = status
        row.updated_by = updated_by
        row.updated_at = _now()
        if status == "published":
            row.published_at = _now()
    else:
        row = AdminContentBlockDB(
            key=key,
            title=title,
            content_json=body,
            status=status,
            published_at=_now() if status == "published" else None,
            updated_by=updated_by,
            updated_at=_now(),
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_assets(db: Session) -> List[AssetLibraryItemDB]:
    return db.query(AssetLibraryItemDB).order_by(AssetLibraryItemDB.created_at.desc()).limit(200).all()


def create_asset(db: Session, *, name: str, type_: str, url: str, tags: Optional[list], created_by: Optional[str]) -> AssetLibraryItemDB:
    a = AssetLibraryItemDB(
        id=str(uuid4()),
        name=name,
        type=type_,
        url=url,
        storage_path=None,
        tags_json=json.dumps(tags or [], ensure_ascii=False),
        created_by=created_by,
        created_at=_now(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def list_messages(db: Session) -> List[SiteMessageDB]:
    return db.query(SiteMessageDB).order_by(SiteMessageDB.created_at.desc()).limit(100).all()


def create_message(db: Session, *, title: str, body: str, audience: str, status: str, created_by: Optional[str]) -> SiteMessageDB:
    m = SiteMessageDB(
        id=str(uuid4()),
        title=title,
        body=body,
        audience=audience,
        status=status,
        scheduled_at=None,
        created_by=created_by,
        created_at=_now(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def get_appearance(db: Session) -> Dict[str, Any]:
    rows = db.query(AppearanceSettingDB).all()
    out: Dict[str, Any] = {}
    for r in rows:
        try:
            out[r.key] = json.loads(r.value_json)
        except json.JSONDecodeError:
            out[r.key] = r.value_json
    return out


def patch_appearance(db: Session, items: Dict[str, Any], updated_by: Optional[str]) -> Dict[str, Any]:
    now = _now()
    for k, v in items.items():
        row = db.query(AppearanceSettingDB).filter(AppearanceSettingDB.key == k).first()
        val = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        if row:
            row.value_json = val
            row.updated_by = updated_by
            row.updated_at = now
        else:
            db.add(AppearanceSettingDB(key=k, value_json=val, updated_by=updated_by, updated_at=now))
    db.commit()
    return get_appearance(db)
