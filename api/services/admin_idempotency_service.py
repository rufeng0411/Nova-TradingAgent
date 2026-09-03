"""Idempotent admin POST responses (credits / subscription)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.database import AdminIdempotencyDB


def get_cached_response(db: Session, *, route: str, idempotency_key: str) -> Optional[Any]:
    row = (
        db.query(AdminIdempotencyDB)
        .filter(AdminIdempotencyDB.idempotency_key == idempotency_key, AdminIdempotencyDB.route == route)
        .first()
    )
    if not row:
        return None
    try:
        return json.loads(row.response_json)
    except json.JSONDecodeError:
        return {"raw": row.response_json}


def store_response(db: Session, *, route: str, idempotency_key: str, response_body: Any) -> None:
    row = AdminIdempotencyDB(
        idempotency_key=idempotency_key,
        route=route,
        response_json=json.dumps(response_body, ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
