"""Unit tests for api.services.credits_service (reserve / commit / refund / insufficient)."""

from uuid import uuid4

import pytest

from api.database import UserDB, get_db_ctx
from api.services import auth_service, credits_service


def _register_user(username: str) -> UserDB:
    with get_db_ctx() as db:
        return auth_service.register_user(
            db,
            username=username,
            email=auth_service.normalize_email(f"{username}-{uuid4().hex[:6]}@credits.test"),
            password="Testpass12",
        )


def test_reserve_commit_consumes_counter():
    u = _register_user(f"u{uuid4().hex[:8]}")
    job_id = uuid4().hex
    cost = credits_service.analysis_cost()
    if cost <= 0:
        pytest.skip("TA_COST_ANALYSIS is 0; nothing to reserve")

    with get_db_ctx() as db:
        credits_service.grant(db, u.id, cost + 50, "top_up", ref_type="test", ref_id="t1")

    with get_db_ctx() as db:
        credits_service.reserve_for_analysis(db, u.id, job_id, cost)
        bal_after_reserve = credits_service.get_balance(db, u.id)

    with get_db_ctx() as db:
        credits_service.commit_analysis(db, u.id, job_id, cost)
        u2 = db.query(UserDB).filter(UserDB.id == u.id).first()
        assert int(u2.total_credits_consumed or 0) >= cost
        assert credits_service.get_balance(db, u.id) == bal_after_reserve


def test_reserve_idempotent_then_refund_restores_balance():
    u = _register_user(f"r{uuid4().hex[:8]}")
    job_id = uuid4().hex
    cost = credits_service.analysis_cost()
    if cost <= 0:
        pytest.skip("TA_COST_ANALYSIS is 0")

    with get_db_ctx() as db:
        credits_service.grant(db, u.id, cost + 10, "top_up", ref_type="test", ref_id="t2")

    with get_db_ctx() as db:
        credits_service.reserve_for_analysis(db, u.id, job_id, cost)
        credits_service.reserve_for_analysis(db, u.id, job_id, cost)  # idempotent
        mid = credits_service.get_balance(db, u.id)

    with get_db_ctx() as db:
        credits_service.refund_analysis(db, u.id, job_id, cost)
        assert credits_service.get_balance(db, u.id) == mid + cost


def test_insufficient_raises():
    u = _register_user(f"i{uuid4().hex[:8]}")
    job_id = uuid4().hex
    cost = credits_service.analysis_cost()
    if cost <= 0:
        pytest.skip("TA_COST_ANALYSIS is 0")

    with get_db_ctx() as db:
        db.query(UserDB).filter(UserDB.id == u.id).update({"credits": max(0, cost - 1)})
        db.commit()

    with get_db_ctx() as db:
        with pytest.raises(credits_service.InsufficientCreditsError):
            credits_service.reserve_for_analysis(db, u.id, job_id, cost)
