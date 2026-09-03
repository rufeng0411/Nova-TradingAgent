"""Admin reports API smoke tests."""

from api.database import UserDB, get_db_ctx
from api.services import auth_service
from tests.helpers_auth import register_user_via_api


def _admin_token(client):
    token, uid = register_user_via_api(client, prefix="rep")
    with get_db_ctx() as db:
        u = db.query(UserDB).filter(UserDB.id == uid).first()
        u.role = "admin"
        db.commit()
        tok = auth_service.create_access_token(u)
    return tok


def test_reports_overview_ok(client):
    tok = _admin_token(client)
    r = client.get("/v1/admin/reports/overview", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    j = r.json()
    assert "new_users" in j


def test_reports_export_csv_ok(client):
    tok = _admin_token(client)
    r = client.get(
        "/v1/admin/reports/export.csv?report=overview&grain=day",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert "metric" in (r.text or "")


def test_bootstrap_has_enabled_modules(client):
    tok = _admin_token(client)
    r = client.get("/v1/admin/bootstrap", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json().get("enabled_modules", {}).get("reports") is True
