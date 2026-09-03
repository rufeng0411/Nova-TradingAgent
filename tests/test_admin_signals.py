"""Admin signals."""

from __future__ import annotations

from api.database import UserDB, get_db_ctx
from api.services import admin_signals_service, auth_service
from tests.helpers_auth import register_user_via_api


def test_list_signals(client):
    token, uid = register_user_via_api(client, prefix="sig")
    with get_db_ctx() as db:
        u = db.query(UserDB).filter(UserDB.id == uid).first()
        u.role = "admin"
        db.commit()
        admin_tok = auth_service.create_access_token(u)
        admin_signals_service.insert_signal(
            db,
            type="pytest.signal",
            severity="info",
            payload={"hello": True},
            user_id=uid,
        )

    r = client.get("/v1/admin/signals", headers={"Authorization": f"Bearer {admin_tok}"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(x["type"] == "pytest.signal" for x in items)
