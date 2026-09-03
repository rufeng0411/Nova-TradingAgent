from __future__ import annotations

from tests.helpers_auth import register_user_via_api


def _auth_headers(client) -> dict[str, str]:
    token, _ = register_user_via_api(client, prefix="quotes")
    return {"Authorization": f"Bearer {token}"}


def test_market_quotes_requires_login(client):
    response = client.post("/v1/market/quotes", json={"symbols": ["600519.SH"]})

    assert response.status_code == 401


def test_market_quotes_dedupes_symbols_and_reports_missing(client, monkeypatch):
    headers = _auth_headers(client)
    captured: list[str] = []

    def fake_fetch(symbols: list[str]):
        captured.extend(symbols)
        return {
            "600519.SH": {
                "price": 1800.0,
                "open": 1790.0,
                "high": 1810.0,
                "low": 1788.0,
                "previous_close": 1795.0,
                "change": 5.0,
                "change_pct": 0.2786,
                "volume": 50000,
                "amount": 90000000,
                "quote_time": "2026-05-06 10:30:00",
                "source": "test",
            }
        }

    monkeypatch.setattr("api.services.tracking_board_service._fetch_live_quotes", fake_fetch)

    response = client.post(
        "/v1/market/quotes",
        headers=headers,
        json={"symbols": ["600519.SH", "600519", "", "000001.SZ"]},
    )

    assert response.status_code == 200
    assert captured == ["600519.SH", "000001.SZ"]
    body = response.json()
    assert body["quotes"]["600519.SH"]["price"] == 1800.0
    assert body["quotes"]["600519.SH"]["change_pct"] == 0.2786
    assert body["missing"] == ["000001.SZ"]
    assert body["cache_ttl_seconds"] >= 1


def test_market_quotes_rejects_too_many_symbols(client):
    headers = _auth_headers(client)
    symbols = [f"{i:06d}.SZ" for i in range(51)]

    response = client.post("/v1/market/quotes", headers=headers, json={"symbols": symbols})

    assert response.status_code == 400
    assert "最多" in response.json()["detail"]
