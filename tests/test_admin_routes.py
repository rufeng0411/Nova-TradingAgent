"""Admin routes: normal user 403, admin JWT 200, API token rejected for admin."""

from api.database import UserDB, get_db_ctx
from api.services import auth_service, token_service

from tests.helpers_auth import register_user_via_api


def test_non_admin_forbidden_on_dashboard(client):
    token, _ = register_user_via_api(client, prefix="adm")
    r = client.get("/v1/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_dashboard_ok(client):
    token, uid = register_user_via_api(client, prefix="adm")
    with get_db_ctx() as db:
        user = db.query(UserDB).filter(UserDB.id == uid).first()
        user.role = "admin"
        db.commit()
        db.refresh(user)
        admin_token = auth_service.create_access_token(user)

    r = client.get("/v1/admin/dashboard", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert "total_users" in r.json()


def test_api_token_rejected_for_admin(client):
    _, uid = register_user_via_api(client, prefix="adm")
    with get_db_ctx() as db:
        user = db.query(UserDB).filter(UserDB.id == uid).first()
        user.role = "admin"
        db.commit()
        tok = token_service.create_token(db, uid, "pytest-admin")

    r = client.get("/v1/admin/dashboard", headers={"Authorization": f"Bearer {tok['token']}"})
    assert r.status_code == 401
