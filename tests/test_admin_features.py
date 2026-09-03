"""Admin feature flags."""

from __future__ import annotations

from api.database import UserDB, get_db_ctx
from api.services import auth_service, features_service
from tests.helpers_auth import register_user_via_api


def test_features_patch_admin_only(client):
    r = client.get("/v1/features")
    assert r.status_code == 200
    token, uid = register_user_via_api(client, prefix="feat")
    r2 = client.patch(
        "/v1/admin/features",
        headers={"Authorization": f"Bearer {token}"},
        json={"key": "allow_registration", "value": False},
    )
    assert r2.status_code == 403

    with get_db_ctx() as db:
        u = db.query(UserDB).filter(UserDB.id == uid).first()
        u.role = "admin"
        db.commit()
        admin_tok = auth_service.create_access_token(u)

    r3 = client.patch(
        "/v1/admin/features",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"key": "allow_registration", "value": False},
    )
    assert r3.status_code == 200
    pub = client.get("/v1/features").json()
    assert pub["allow_registration"] is False
    with get_db_ctx() as db:
        features_service.patch(db, "allow_registration", True, admin_id=uid)
