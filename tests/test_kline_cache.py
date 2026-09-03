from __future__ import annotations


def test_kline_endpoint_reuses_cached_candles_for_same_request(client, monkeypatch):
    from api import main

    calls: list[tuple[str, str, str, str, str]] = []

    def fake_load(symbol: str, start: str, end: str, period: str = "1d", adjust: str = "none"):
        calls.append((symbol, start, end, period, adjust))
        return [
            {
                "date": "2026-05-06",
                "open": 10.0,
                "high": 11.0,
                "low": 9.8,
                "close": 10.5,
                "volume": 1000,
                "amount": 10500,
                "change": 0.5,
                "change_percent": 5.0,
            }
        ]

    monkeypatch.setattr(main, "_load_kline_candles_unsafe", fake_load)
    monkeypatch.setattr(main, "_get_reverse_stock_map_cached_only", lambda: {})

    params = {
        "symbol": "600519.SH",
        "start_date": "2026-05-01",
        "end_date": "2026-05-06",
        "period": "1d",
        "adjust": "none",
    }

    first = client.get("/v1/market/kline", params=params)
    second = client.get("/v1/market/kline", params=params)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(calls) == 1
    assert second.json()["candles"] == first.json()["candles"]
