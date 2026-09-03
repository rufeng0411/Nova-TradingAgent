"""Tests for durable analysis jobs + event log."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.services import analysis_job_service

pytestmark = pytest.mark.no_init_db


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_append_event_increments_seq_and_is_replayable():
    db = _session()
    try:
        jid = "abc123job"
        analysis_job_service.upsert_job_row(
            db,
            jid,
            user_id="user-1",
            symbol="600519.SH",
            trade_date="2026-05-06",
            status="running",
            request_payload={"symbol": "600519.SH", "trade_date": "2026-05-06", "dry_run": True},
            request_source="api",
            dry_run=True,
        )
        s1 = analysis_job_service.append_event(db, jid, "job.running", {"x": 1})
        s2 = analysis_job_service.append_event(db, jid, "agent.snapshot", {"agents": []})
        assert s1 == 1
        assert s2 == 2

        replay = analysis_job_service.fetch_events_after(jid, 0, db=db)
        assert len(replay) == 2
        assert replay[0][0] == 1 and replay[0][1] == "job.running"
        assert replay[1][0] == 2

        tail = analysis_job_service.fetch_events_after(jid, 1, db=db)
        assert len(tail) == 1
        assert tail[0][0] == 2
    finally:
        db.close()


def test_list_jobs_to_reclaim_expired_lease():
    db = _session()
    try:
        jid = "stale1"
        analysis_job_service.upsert_job_row(
            db,
            jid,
            user_id="u1",
            symbol="600519.SH",
            trade_date="2026-05-06",
            status="running",
            request_payload={"dry_run": True},
            request_source="api",
            dry_run=True,
        )
        row = analysis_job_service.get_job_row(db, jid)
        assert row is not None
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        row.lease_until = past
        row.updated_at = past
        db.commit()

        reclaim = analysis_job_service.list_jobs_to_reclaim(db)
        assert jid in reclaim
    finally:
        db.close()


def test_try_claim_for_resume_sets_resuming():
    db = _session()
    try:
        jid = "claim1"
        analysis_job_service.upsert_job_row(
            db,
            jid,
            user_id="u1",
            symbol="600519.SH",
            trade_date="2026-05-06",
            status="running",
            request_payload={"dry_run": True},
            request_source="api",
            dry_run=True,
        )
        row = analysis_job_service.get_job_row(db, jid)
        assert row is not None
        row.lease_until = datetime.now(timezone.utc) - timedelta(seconds=30)
        db.commit()

        ok = analysis_job_service.try_claim_for_resume(db, jid, "worker-test")
        assert ok is True
        row2 = analysis_job_service.get_job_row(db, jid)
        assert row2 is not None
        assert row2.status == "resuming"
        assert row2.lease_owner == "worker-test"
    finally:
        db.close()
