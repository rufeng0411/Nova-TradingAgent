from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from api.database import AnalysisJobDB, JobEventDB, get_db_ctx
from tests.helpers_auth import register_user_via_api


def _auth_headers(client):
    token, user_id = register_user_via_api(client, prefix="taskdel")
    return {"Authorization": f"Bearer {token}"}, user_id


def test_delete_task_record_removes_job_and_events(client):
    headers, user_id = _auth_headers(client)
    job_id = uuid4().hex
    now = datetime.now(timezone.utc)
    with get_db_ctx() as db:
        db.add(
            AnalysisJobDB(
                id=job_id,
                user_id=user_id,
                status="failed",
                symbol="603002.SH",
                trade_date="2026-05-13",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            JobEventDB(
                job_id=job_id,
                seq=1,
                event="job.failed",
                payload={"job_id": job_id, "error": "mock"},
                created_at=now,
            )
        )
        db.commit()

    resp = client.delete(f"/v1/me/tasks/{job_id}/record", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "deleted"

    with get_db_ctx() as db:
        row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
        events = db.query(JobEventDB).filter(JobEventDB.job_id == job_id).all()
    assert row is None
    assert events == []


def test_delete_task_record_rejects_running_job(client):
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
                trade_date="2026-05-13",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    resp = client.delete(f"/v1/me/tasks/{job_id}/record", headers=headers)
    assert resp.status_code == 409
    assert "stop first" in str(resp.json().get("detail", "")).lower()
