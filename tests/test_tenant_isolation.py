"""Cross-tenant isolation: jobs, backtest store, reports, feedback, job owner edge cases."""

from unittest.mock import patch
from uuid import uuid4

from api.database import get_db_ctx
from api.services import auth_service, feedback_service, report_service
from api.services.backtest_service import _set as bt_set

from tests.helpers_auth import register_user_via_api


def test_analyze_job_not_readable_by_other_user(client):
    ta, _ = register_user_via_api(client, prefix="iso")
    tb, _ = register_user_via_api(client, prefix="iso")
    ha = {"Authorization": f"Bearer {ta}"}
    hb = {"Authorization": f"Bearer {tb}"}

    r = client.post(
        "/v1/analyze",
        headers=ha,
        json={"symbol": "600519.SH", "trade_date": "2024-01-15", "dry_run": True},
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    r2 = client.get(f"/v1/jobs/{job_id}", headers=hb)
    assert r2.status_code == 404


def test_job_missing_user_id_returns_403(client):
    """Legacy/inconsistent job store entries without user_id must not be world-readable."""
    token, _ = register_user_via_api(client, prefix="job")
    fake_job = {
        "job_id": "orphan-job",
        "status": "completed",
        "created_at": "2024-01-01T00:00:00+00:00",
        "symbol": "600519.SH",
        "trade_date": "2024-01-15",
        "user_id": None,
    }
    with patch("api.main._get_job", return_value=fake_job):
        r = client.get("/v1/jobs/orphan-job", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_backtest_job_isolation(client):
    ta, _ = register_user_via_api(client, prefix="iso")
    tb, _ = register_user_via_api(client, prefix="iso")
    uid_a = auth_service.decode_access_token(ta)["sub"]

    jid = f"btiso-{uuid4().hex[:10]}"
    bt_set(
        jid,
        user_id=uid_a,
        symbol="600519.SH",
        start_date="2024-01-01",
        end_date="2024-01-10",
        selected_analysts=["market"],
        hold_days=5,
        sample_interval=7,
        status="pending",
        created_at="2024-01-01T00:00:00+00:00",
        total_dates=0,
        completed_dates=0,
        records=[],
        stats=None,
        error=None,
    )

    r = client.get(f"/v1/backtest/{jid}", headers={"Authorization": f"Bearer {tb}"})
    assert r.status_code == 404


def test_report_get_isolation(client):
    ta, _ = register_user_via_api(client, prefix="iso")
    tb, _ = register_user_via_api(client, prefix="iso")
    uid_a = auth_service.decode_access_token(ta)["sub"]

    with get_db_ctx() as db:
        rep = report_service.create_report(
            db=db,
            symbol="000001.SZ",
            trade_date="2024-02-01",
            decision="HOLD",
            user_id=uid_a,
            result_data={"final_trade_decision": "持有"},
        )
        rid = rep.id

    r = client.get(f"/v1/reports/{rid}", headers={"Authorization": f"Bearer {tb}"})
    assert r.status_code == 404


def test_feedback_get_isolation(client):
    with get_db_ctx() as db:
        u1 = auth_service.register_user(
            db,
            username=f"f1{uuid4().hex[:6]}",
            email=auth_service.normalize_email(f"f1-{uuid4().hex[:6]}@fb.test"),
            password="Testpass12",
        )
        u2 = auth_service.register_user(
            db,
            username=f"f2{uuid4().hex[:6]}",
            email=auth_service.normalize_email(f"f2-{uuid4().hex[:6]}@fb.test"),
            password="Testpass12",
        )
        fb = feedback_service.create_feedback(db, u1, "t", "body")
        fid = fb.id
        u2_id = u2.id

    with get_db_ctx() as db:
        u2_db = auth_service.get_user_by_id(db, u2_id)
        assert u2_db is not None
        t2 = auth_service.create_access_token(u2_db)
    r = client.get(f"/v1/feedbacks/{fid}", headers={"Authorization": f"Bearer {t2}"})
    assert r.status_code == 404
