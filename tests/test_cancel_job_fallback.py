from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from api.database import AnalysisJobDB, get_db_ctx
from tests.helpers_auth import register_user_via_api


def _auth_headers(client):
    token, user_id = register_user_via_api(client, prefix="canceljob")
    return {"Authorization": f"Bearer {token}"}, user_id


def test_cancel_running_job_without_inner_task_falls_back_to_failed(client):
    headers, user_id = _auth_headers(client)
    job_id = uuid4().hex
    now = datetime.now(timezone.utc)
    with get_db_ctx() as db:
        db.add(
            AnalysisJobDB(
                id=job_id,
                user_id=user_id,
                status="running",
                symbol="603002.SH",
                trade_date="2026-05-14",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    resp = client.post(f"/v1/jobs/{job_id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] in ("cancelled", "cancel_requested")

    with get_db_ctx() as db:
        row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
    assert row is not None
    assert str(row.status) == "failed"
    assert "取消" in str(row.error or "")
