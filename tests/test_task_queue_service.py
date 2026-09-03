from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import AnalysisJobDB, Base
from api.services import task_queue_service

pytestmark = pytest.mark.no_init_db


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def _add_job(db, *, job_id: str, user_id: str, status: str = "queued") -> None:
    now = datetime.now(timezone.utc)
    db.add(
        AnalysisJobDB(
            id=job_id,
            user_id=user_id,
            status=status,
            symbol="600519.SH",
            trade_date="2026-05-12",
            request_payload={"symbol": "600519.SH", "trade_date": "2026-05-12"},
            request_source="api",
            dry_run=False,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def test_dequeue_not_blocked_by_stale_pending_job():
    """Expired-lease + old pending rows must not freeze the per-user queue (reclaim-eligible)."""
    db = _session()
    try:
        now = datetime.now(timezone.utc)
        old = now - timedelta(seconds=900)
        db.add(
            AnalysisJobDB(
                id="zombie-pending",
                user_id="u1",
                status="pending",
                symbol="000001.SZ",
                trade_date="2026-05-12",
                request_payload={"symbol": "000001.SZ", "trade_date": "2026-05-12"},
                request_source="api",
                dry_run=False,
                lease_until=now - timedelta(minutes=5),
                created_at=old,
                updated_at=old,
            )
        )
        db.commit()
        _add_job(db, job_id="job-1", user_id="u1")
        task_queue_service.enqueue_job(
            db,
            user_id="u1",
            job_id="job-1",
            task_kind="full_analysis",
            title="A",
            description=None,
            symbol="600519.SH",
            trade_date="2026-05-12",
        )
        dequeued = task_queue_service.dequeue_next_job(db, "u1")
        assert dequeued is not None and dequeued["job_id"] == "job-1"
    finally:
        db.close()


def test_dequeue_blocked_by_live_pending_job():
    db = _session()
    try:
        now = datetime.now(timezone.utc)
        db.add(
            AnalysisJobDB(
                id="live-pending",
                user_id="u1",
                status="pending",
                symbol="000001.SZ",
                trade_date="2026-05-12",
                request_payload={"symbol": "000001.SZ", "trade_date": "2026-05-12"},
                request_source="api",
                dry_run=False,
                lease_until=now + timedelta(hours=1),
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        _add_job(db, job_id="job-1", user_id="u1")
        task_queue_service.enqueue_job(
            db,
            user_id="u1",
            job_id="job-1",
            task_kind="full_analysis",
            title="A",
            description=None,
            symbol="600519.SH",
            trade_date="2026-05-12",
        )
        assert task_queue_service.dequeue_next_job(db, "u1") is None
    finally:
        db.close()


def test_dequeue_respects_sort_order():
    db = _session()
    try:
        _add_job(db, job_id="job-1", user_id="u1")
        _add_job(db, job_id="job-2", user_id="u1")
        task_queue_service.enqueue_job(
            db,
            user_id="u1",
            job_id="job-1",
            task_kind="full_analysis",
            title="A",
            description=None,
            symbol="600519.SH",
            trade_date="2026-05-12",
        )
        task_queue_service.enqueue_job(
            db,
            user_id="u1",
            job_id="job-2",
            task_kind="full_analysis",
            title="B",
            description=None,
            symbol="300750.SZ",
            trade_date="2026-05-12",
        )

        first = task_queue_service.dequeue_next_job(db, "u1")
        second = task_queue_service.dequeue_next_job(db, "u1")
        assert first is not None and first["job_id"] == "job-1"
        assert second is not None and second["job_id"] == "job-2"
    finally:
        db.close()


def test_pause_resume_controls_dequeue():
    db = _session()
    try:
        _add_job(db, job_id="job-3", user_id="u1")
        task_queue_service.enqueue_job(
            db,
            user_id="u1",
            job_id="job-3",
            task_kind="full_analysis",
            title="C",
            description=None,
            symbol="600519.SH",
            trade_date="2026-05-12",
        )
        task_queue_service.set_queue_status(
            db,
            "u1",
            "job-3",
            queue_status=task_queue_service.QUEUE_STATUS_PAUSED,
        )
        assert task_queue_service.dequeue_next_job(db, "u1") is None

        task_queue_service.set_queue_status(
            db,
            "u1",
            "job-3",
            queue_status=task_queue_service.QUEUE_STATUS_QUEUED,
        )
        dequeued = task_queue_service.dequeue_next_job(db, "u1")
        assert dequeued is not None and dequeued["job_id"] == "job-3"
    finally:
        db.close()


def test_remove_queued_job_marks_analysis_failed():
    db = _session()
    try:
        _add_job(db, job_id="job-4", user_id="u1")
        task_queue_service.enqueue_job(
            db,
            user_id="u1",
            job_id="job-4",
            task_kind="full_analysis",
            title="D",
            description=None,
            symbol="600519.SH",
            trade_date="2026-05-12",
        )
        assert task_queue_service.remove_queued_job(db, user_id="u1", job_id="job-4") is True
        row = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == "job-4").first()
        assert row is not None
        assert row.status == "failed"
        assert "取消" in str(row.error or "")
    finally:
        db.close()
