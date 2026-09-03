from __future__ import annotations

from tradingagents.dataflows import local_first


def test_route_with_local_first_hit(monkeypatch):
    monkeypatch.setenv("TA_DATASOURCE_TIER3_ENABLED", "1")
    monkeypatch.setenv("TA_DATASOURCE_LOCAL_FIRST", "1")
    monkeypatch.setitem(local_first.LOCAL_FIRST_HANDLERS, "x", lambda *a, **k: "local-hit")
    monkeypatch.setattr(local_first, "route_to_vendor", lambda *a, **k: "vendor-hit")
    assert local_first.route_with_local_first("x", "a") == "local-hit"


def test_route_with_local_first_miss_fallback(monkeypatch):
    monkeypatch.setenv("TA_DATASOURCE_TIER3_ENABLED", "1")
    monkeypatch.setenv("TA_DATASOURCE_LOCAL_FIRST", "1")
    monkeypatch.setitem(local_first.LOCAL_FIRST_HANDLERS, "x", lambda *a, **k: None)
    monkeypatch.setattr(local_first, "route_to_vendor", lambda *a, **k: "vendor-hit")
    assert local_first.route_with_local_first("x", "a") == "vendor-hit"


def test_route_with_local_first_disabled(monkeypatch):
    monkeypatch.setenv("TA_DATASOURCE_TIER3_ENABLED", "1")
    monkeypatch.setenv("TA_DATASOURCE_LOCAL_FIRST", "0")
    monkeypatch.setitem(local_first.LOCAL_FIRST_HANDLERS, "x", lambda *a, **k: "local-hit")
    monkeypatch.setattr(local_first, "route_to_vendor", lambda *a, **k: "vendor-hit")
    assert local_first.route_with_local_first("x", "a") == "vendor-hit"


def test_route_with_local_first_handler_error(monkeypatch):
    monkeypatch.setenv("TA_DATASOURCE_TIER3_ENABLED", "1")
    monkeypatch.setenv("TA_DATASOURCE_LOCAL_FIRST", "1")

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(local_first.LOCAL_FIRST_HANDLERS, "x", _boom)
    monkeypatch.setattr(local_first, "route_to_vendor", lambda *a, **k: "vendor-hit")
    assert local_first.route_with_local_first("x", "a") == "vendor-hit"
