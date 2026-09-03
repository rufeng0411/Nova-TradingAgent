from __future__ import annotations

import pandas as pd

from api.services import market_chart_service
from tests.helpers_auth import register_user_via_api


def test_get_auction_snapshot_parses_gap_and_cache(monkeypatch):
    monkeypatch.setenv("TA_TS_AUCTION_ENABLED", "1")
    monkeypatch.setattr(market_chart_service, "_cache", {})
    monkeypatch.setattr(market_chart_service, "_inflight", {})
    monkeypatch.setattr(market_chart_service, "cn_today_str", lambda: "2026-05-14")
    calls = {"n": 0}

    def _fake_route(method, symbol, trade_date):
        calls["n"] += 1
        assert method == "fetch_stk_auction"
        assert symbol == "600519.SH"
        assert trade_date == "2026-05-14"
        return pd.DataFrame(
            [
                {
                    "price": 1608.0,
                    "pre_close": 1600.0,
                    "volume_ratio": 1.7,
                    "turnover_rate": 0.35,
                    "amount": 88880000,
                    "vol": 1200000,
                }
            ]
        )

    monkeypatch.setattr(market_chart_service, "route_to_vendor", _fake_route)
    p1 = market_chart_service.get_auction_snapshot("600519.SH")
    p2 = market_chart_service.get_auction_snapshot("600519.SH")
    assert calls["n"] == 1
    assert p1["enabled"] is True
    assert p2["snapshot"]["bull_bear_ratio"] == 1.7
    assert round(float(p1["snapshot"]["gap_pct"]), 2) == 0.50


def test_get_corp_event_markers_disabled(monkeypatch):
    monkeypatch.setenv("TA_TS_FIN_EVENT_ENABLED", "0")
    payload = market_chart_service.get_corp_event_markers("600519.SH", "2026-01-01", "2026-05-14")
    assert payload["enabled"] is False
    assert payload["items"] == []


def test_chart_auction_api(client, monkeypatch):
    token, _uid = register_user_via_api(client, "chart")
    monkeypatch.setattr("api.deps.user_has_advanced_market", lambda db, user: True)
    monkeypatch.setattr(
        "api.services.market_chart_service.get_auction_snapshot",
        lambda symbol: {
            "enabled": True,
            "symbol": symbol,
            "snapshot": {"gap_pct": 1.23, "bull_bear_ratio": 1.7},
        },
    )
    resp = client.get(
        "/v1/market/chart/auction",
        params={"symbol": "600519.SH"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is True
    assert body["snapshot"]["gap_pct"] == 1.23
