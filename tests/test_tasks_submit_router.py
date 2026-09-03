from __future__ import annotations

from unittest.mock import patch

from tests.helpers_auth import register_user_via_api


def _auth_headers(client):
    token, _ = register_user_via_api(client, prefix="tasksubmit")
    return {"Authorization": f"Bearer {token}"}


def test_submit_task_pending(client):
    headers = _auth_headers(client)
    def _close_coro(coro, *args, **kwargs):
        coro.close()
        return None

    with patch("api.main._build_runtime_config", return_value={}), \
         patch("api.main._ai_extract_symbol_and_date", return_value=("603002.SH", "2026-05-13", ["short"], [], [], {})), \
         patch("api.main._enqueue_or_start_job", return_value=("pending", 0)), \
         patch("api.main._create_tracked_task", side_effect=_close_coro) as create_task:
        resp = client.post(
            "/v1/me/tasks/submit",
            headers=headers,
            json={"text": "分析宏昌电子 603002.SH 今日走势"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["symbol"] == "603002.SH"
    assert body["waiting_ahead_count"] == 0
    assert create_task.call_count == 1


def test_submit_task_queued(client):
    headers = _auth_headers(client)
    with patch("api.main._build_runtime_config", return_value={}), \
         patch("api.main._ai_extract_symbol_and_date", return_value=("600519.SH", "2026-05-13", ["short"], [], [], {})), \
         patch("api.main._enqueue_or_start_job", return_value=("queued", 2)), \
         patch("api.main._create_tracked_task") as create_task:
        resp = client.post(
            "/v1/me/tasks/submit",
            headers=headers,
            json={"text": "分析贵州茅台"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["waiting_ahead_count"] == 2
    assert "入" in (body.get("message") or "")
    assert create_task.call_count == 0


def test_submit_task_queue_full_returns_failed(client):
    headers = _auth_headers(client)
    with patch("api.main._build_runtime_config", return_value={}), \
         patch("api.main._ai_extract_symbol_and_date", return_value=("600330.SH", "2026-05-13", ["short"], [], [], {})), \
         patch("api.main._enqueue_or_start_job", return_value=("rejected", 5)), \
         patch("api.main._create_tracked_task") as create_task:
        resp = client.post(
            "/v1/me/tasks/submit",
            headers=headers,
            json={"text": "分析600330"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "排队已满" in (body.get("message") or "")
    assert create_task.call_count == 0


def test_submit_task_symbol_not_found_returns_failed(client):
    headers = _auth_headers(client)
    with patch("api.main._build_runtime_config", return_value={}), \
         patch("api.main._ai_extract_symbol_and_date", return_value=(None, None, ["short"], [], [], {})), \
         patch("api.main._enqueue_or_start_job") as enqueue_job:
        resp = client.post(
            "/v1/me/tasks/submit",
            headers=headers,
            json={"text": "帮我看一下今天市场"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert "识别出股票标的" in (body.get("message") or "")
    enqueue_job.assert_not_called()
