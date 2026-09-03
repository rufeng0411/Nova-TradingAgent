from __future__ import annotations

from tests.helpers_auth import register_user_via_api


def _auth_headers(client) -> dict[str, str]:
    token, _ = register_user_via_api(client, prefix="adv")
    return {"Authorization": f"Bearer {token}"}


def test_market_intraday_requires_login(client):
    r = client.get("/v1/market/intraday?symbol=600519.SH")
    assert r.status_code == 401


def test_market_intraday_forbidden_without_entitlement(client, monkeypatch):
    headers = _auth_headers(client)
    monkeypatch.setattr(
        "api.services.entitlements_service.user_has_advanced_market",
        lambda _db, _user: False,
    )
    r = client.get("/v1/market/intraday?symbol=600519.SH", headers=headers)
    assert r.status_code == 403


def test_market_intraday_ok_with_entitlement_mock(client, monkeypatch):
    headers = _auth_headers(client)
    monkeypatch.setattr(
        "api.services.entitlements_service.user_has_advanced_market",
        lambda _db, _user: True,
    )
    monkeypatch.setattr(
        "api.services.market_advanced_service.fetch_intraday",
        lambda symbol: {"symbol": symbol.upper(), "bars": [], "summary": None},
    )
    r = client.get("/v1/market/intraday?symbol=600519.SH", headers=headers)
    assert r.status_code == 200
    assert r.json()["bars"] == []
