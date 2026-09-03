"""Admin RBAC scopes + step-up + idempotency."""

from __future__ import annotations

import uuid

from api.database import UserDB, get_db_ctx
from api.services import auth_service, password_service
from tests.helpers_auth import register_user_via_api


def _make_admin(client, prefix: str = "rbac", *, perms: list | None = None):
    token, uid = register_user_via_api(client, prefix=prefix)
    with get_db_ctx() as db:
        u = db.query(UserDB).filter(UserDB.id == uid).first()
        u.role = "admin"
        u.password_hash = password_service.hash_password("Adminpass12")
        if perms is not None:
            u.admin_permissions = perms
        db.commit()
        tok = auth_service.create_access_token(u)
    return tok, uid


def test_finance_scope_denied(client):
    admin_tok, _ = _make_admin(client, perms=["ops"])
    _, target = register_user_via_api(client, prefix="t")
    r = client.post(
        f"/v1/admin/users/{target}/credits",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"delta": 1, "reason": "t"},
    )
    assert r.status_code == 403


def test_step_up_required(client):
    admin_tok, _ = _make_admin(client, perms=["finance", "ops"])
    _, target = register_user_via_api(client, prefix="t2")
    r = client.post(
        f"/v1/admin/users/{target}/credits",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"delta": 1, "reason": "t"},
    )
    assert r.status_code == 412


def test_idempotency_credits(client):
    admin_tok, admin_id = _make_admin(client, perms=["finance"])
    _, target = register_user_via_api(client, prefix="t3")
    c = client.post(
        "/v1/admin/confirm",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"password": "Adminpass12"},
    )
    assert c.status_code == 200
    confirm = c.json()["confirm_token"]
    key = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {admin_tok}",
        "X-Admin-Confirm": confirm,
        "Idempotency-Key": key,
    }
    r1 = client.post(f"/v1/admin/users/{target}/credits", headers=headers, json={"delta": 2, "reason": "idem"})
    assert r1.status_code == 200
    r2 = client.post(f"/v1/admin/users/{target}/credits", headers=headers, json={"delta": 2, "reason": "idem"})
    assert r2.status_code == 200
    assert r1.json() == r2.json()
