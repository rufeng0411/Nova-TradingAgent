"""Auth helpers for HTTP API tests (captcha bypass via patch)."""

from __future__ import annotations

from typing import Tuple
from uuid import uuid4

from fastapi.testclient import TestClient

from api.services import auth_service


def register_user_via_api(test_client: TestClient, prefix: str = "u") -> Tuple[str, str]:
    """POST /v1/auth/register；返回 (access_token, user_id)。"""
    email = auth_service.normalize_email(f"{prefix}-{uuid4().hex[:8]}@test.com")
    username = f"{prefix[0]}{uuid4().hex[:10]}"
    body = {
        "username": username,
        "email": email,
        "password": "Testpass12",
    }
    r = test_client.post("/v1/auth/register", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    return data["access_token"], data["user"]["id"]
