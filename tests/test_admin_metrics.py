"""Admin metrics overview buckets (SQLite)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from api.database import CreditTransactionDB, UserDB, get_db_ctx
from api.services import admin_metrics_service
from tests.helpers_auth import register_user_via_api


def test_metrics_overview_day_bucket(client):
    token, uid = register_user_via_api(client, prefix="mtr")
    with get_db_ctx() as db:
        user = db.query(UserDB).filter(UserDB.id == uid).first()
        user.role = "admin"
        db.commit()
        from api.services import auth_service

        admin_token = auth_service.create_access_token(user)
        day = datetime.now(timezone.utc) - timedelta(days=2)
        tx_id = f"tx-test-{uid[:8]}"
        db.add(
            CreditTransactionDB(
                id=tx_id,
                user_id=uid,
                delta=-5,
                type="reserve",
                reason="t",
                ref_type="analysis_job",
                ref_id=f"job-{uid[:8]}",
                balance_after=0,
                operator_id=None,
                created_at=day,
            )
        )
        db.commit()

    to = datetime.now(timezone.utc)
    frm = to - timedelta(days=7)
    r = client.get(
        f"/v1/admin/metrics/overview?from={quote(frm.isoformat())}&to={quote(to.isoformat())}&granularity=day",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    data = r.json()["items"]
    assert isinstance(data, list)
    keys = {x["key"] for x in data}
    assert "credits.reserve_volume" in keys


def test_public_features(client):
    r = client.get("/v1/features")
    assert r.status_code == 200
    body = r.json()
    assert "maintenance" in body
    assert "allow_registration" in body
