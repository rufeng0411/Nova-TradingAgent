from __future__ import annotations

import pandas as pd

from api.services import rt_quote_service
from tests.helpers_auth import register_user_via_api


def _sample_rt_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "600519.SH",
                "name": "贵州茅台",
                "pre_close": 1600.0,
                "open": 1601.0,
                "high": 1610.0,
                "low": 1598.0,
                "close": 1608.0,
                "vol": 1200000,
                "amount": 1880000000,
                "num": 10342,
                "trade_time": "14:25:02",
            }
        ]
    )


def test_rt_daily_bulk_maps_fields_and_missing(monkeypatch):
    monkeypatch.setattr(rt_quote_service, "_cache", {})
    monkeypatch.setattr(rt_quote_service, "_inflight", {})
    monkeypatch.setattr(rt_quote_service, "_RT_TTL_SECONDS", 8.0)

    def fake_route(_method, _symbols):
        return _sample_rt_df()

    monkeypatch.setattr(rt_quote_service, "route_to_vendor", fake_route)

    quotes, missing, ttl = rt_quote_service.get_rt_daily_bulk(["600519.SH", "000001.SZ"])
    assert ttl == 8
    assert "600519.SH" in quotes
    item = quotes["600519.SH"]
    assert item["name"] == "贵州茅台"
    assert item["close"] == 1608.0
    assert item["change"] == 8.0
    assert item["change_pct"] == 0.5
    assert "000001.SZ" in missing


def test_rt_daily_bulk_cache_hit(monkeypatch):
    monkeypatch.setattr(rt_quote_service, "_cache", {})
    monkeypatch.setattr(rt_quote_service, "_inflight", {})
    monkeypatch.setattr(rt_quote_service, "_RT_TTL_SECONDS", 8.0)
    calls = {"n": 0}

    def fake_route(_method, _symbols):
        calls["n"] += 1
        return _sample_rt_df()

    monkeypatch.setattr(rt_quote_service, "route_to_vendor", fake_route)
    rt_quote_service.get_rt_daily_bulk(["600519.SH"])
    rt_quote_service.get_rt_daily_bulk(["600519.SH"])
    assert calls["n"] == 1


def test_rt_board_sort(monkeypatch):
    monkeypatch.setattr(rt_quote_service, "_cache", {})
    monkeypatch.setattr(rt_quote_service, "_inflight", {})

    def fake_route(_method, _symbols):
        return pd.DataFrame(
            [
                {"ts_code": "600519.SH", "name": "贵州茅台", "pre_close": 100.0, "close": 103.0},
                {"ts_code": "000001.SZ", "name": "平安银行", "pre_close": 10.0, "close": 10.2},
            ]
        )

    monkeypatch.setattr(rt_quote_service, "route_to_vendor", fake_route)
    items = rt_quote_service.get_rt_board("6*.SH,0*.SZ", sort_by="change_pct", limit=2)
    assert len(items) == 2
    assert items[0].symbol == "600519.SH"


def test_rt_daily_api(client, monkeypatch):
    token, _uid = register_user_via_api(client, "rt")
    monkeypatch.setattr("api.deps.user_has_advanced_market", lambda db, user: True)

    def fake_bulk(symbols):
        return (
            {
                "600519.SH": {
                    "name": "贵州茅台",
                    "close": 1608.0,
                    "pre_close": 1600.0,
                    "change": 8.0,
                    "change_pct": 0.5,
                    "source": "tushare_rt",
                }
            },
            [],
            8,
        )

    monkeypatch.setattr("api.services.rt_quote_service.get_rt_daily_bulk", fake_bulk)
    r = client.get(
        "/v1/market/rt-daily",
        params={"symbols": "600519.SH"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cache_ttl_seconds"] == 8
    assert body["quotes"]["600519.SH"]["source"] == "tushare_rt"
