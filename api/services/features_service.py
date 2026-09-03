"""Runtime feature flags: DB overrides merged with environment defaults."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from api.database import SystemFeatureDB

_DEFAULT_KEYS = (
    "allow_registration",
    "maintenance",
    "captcha_enabled",
    "ta_cost_analysis",
)


def _env_allow_registration() -> bool:
    return os.getenv("TA_ALLOW_REGISTRATION", "1").strip().lower() not in ("0", "false", "no", "off")


def _env_maintenance() -> bool:
    return os.getenv("TA_MAINTENANCE_MODE", "0").strip().lower() in ("1", "true", "yes", "on")


def _env_captcha_enabled() -> bool:
    from api.services import captcha_service

    return captcha_service.is_enabled()


def _env_cost_analysis() -> int:
    return int(os.getenv("TA_COST_ANALYSIS", "10") or "10")


def defaults() -> Dict[str, Any]:
    return {
        "allow_registration": _env_allow_registration(),
        "maintenance": _env_maintenance(),
        "captcha_enabled": _env_captcha_enabled(),
        "ta_cost_analysis": _env_cost_analysis(),
    }


def _parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def get_merged(db: Session) -> Dict[str, Any]:
    out = defaults()
    rows = db.query(SystemFeatureDB).all()
    for r in rows:
        if r.key in out:
            out[r.key] = _parse_value(r.value_json)
    return out


def get_public(db: Session) -> Dict[str, Any]:
    """Subset safe for unauthenticated clients."""
    full = get_merged(db)
    queue_enabled = os.getenv("TA_USER_TASK_QUEUE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
    chat_task_submit_v2_enabled = os.getenv("TA_CHAT_TASK_SUBMIT_V2_ENABLED", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    fast_analysis_enabled = os.getenv("TA_FAST_ANALYSIS_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    return {
        "allow_registration": bool(full.get("allow_registration", True)),
        "maintenance": bool(full.get("maintenance", False)),
        "captcha_enabled": bool(full.get("captcha_enabled", False)),
        "ta_cost_analysis": int(full.get("ta_cost_analysis", 10) or 10),
        "task_queue_enabled": queue_enabled,
        "chat_task_submit_v2_enabled": chat_task_submit_v2_enabled,
        "fast_analysis_enabled": fast_analysis_enabled,
    }


def patch(
    db: Session,
    key: str,
    value: Any,
    *,
    admin_id: str,
) -> Dict[str, Any]:
    if key not in _DEFAULT_KEYS and not key.startswith("feature."):
        raise ValueError("unknown_feature_key")
    row = db.query(SystemFeatureDB).filter(SystemFeatureDB.key == key).first()
    payload = json.dumps(value, ensure_ascii=False)
    now = datetime.now(timezone.utc)
    if row:
        row.value_json = payload
        row.updated_at = now
        row.updated_by = admin_id
    else:
        db.add(
            SystemFeatureDB(
                key=key,
                value_json=payload,
                updated_at=now,
                updated_by=admin_id,
            )
        )
    db.commit()
    return get_merged(db)
