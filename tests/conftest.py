"""Shared pytest fixtures."""

from __future__ import annotations

import os

# Documented development admin (same as .env.example). Required because
# ensure_default_admin refuses to boot without TA_ADMIN_PASSWORD.
os.environ.setdefault("TA_ADMIN_PASSWORD", "ChangeMe_Admin1!")
os.environ.setdefault("TA_APP_SECRET_KEY", "please-change-this-to-a-32byte-or-longer-secret")
os.environ.setdefault("TA_ALLOW_REGISTRATION", "1")

import pytest
from fastapi.testclient import TestClient

from api.database import init_db


@pytest.fixture(scope="session", autouse=True)
def _disable_llm_final_decision_summary_for_tests() -> None:
    """避免 create_report 在单测中触发真实 LLM 摘要调用。"""
    os.environ["TA_FINAL_DECISION_SUMMARY_ENABLED"] = "0"


@pytest.fixture(autouse=True)
def _init_database(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("no_init_db"):
        return
    init_db()


@pytest.fixture(scope="session")
def fastapi_app():
    from api.main import app

    return app


@pytest.fixture
def client(fastapi_app) -> TestClient:
    return TestClient(fastapi_app, raise_server_exceptions=False)
