from __future__ import annotations

from types import SimpleNamespace

import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.data_source_catalog import enrich_data_source_item


class _FakeRegistry:
    def __init__(self, providers: dict[str, object]):
        self._providers = providers

    def get(self, name: str):
        return self._providers.get(name)

    def list_names(self):
        return list(self._providers.keys())


def test_route_to_vendor_with_meta_hit(monkeypatch):
    provider = SimpleNamespace(get_stock_data=lambda *args, **kwargs: "ok")
    registry = _FakeRegistry({"cn_akshare": provider})
    monkeypatch.setattr(interface, "_registry", registry)
    monkeypatch.setattr(interface, "_log_vendor_call", lambda **kwargs: None)
    monkeypatch.setattr(interface, "get_vendor", lambda *args, **kwargs: "cn_akshare")
    monkeypatch.setattr(interface, "_infer_market", lambda *args, **kwargs: "cn")

    value, meta = interface.route_to_vendor_with_meta("get_stock_data", symbol="000001.SH", start_date="2026-01-01", end_date="2026-01-02")

    assert value == "ok"
    assert meta["status"] == "hit"
    assert meta["vendor"] == "cn_akshare"
    assert meta["category"] == "core_stock_apis"
    assert isinstance(meta.get("fallback_chain"), list)
    assert "fetched_at" in meta


def test_route_to_vendor_with_meta_fallback(monkeypatch):
    bad_provider = SimpleNamespace(get_stock_data=lambda *args, **kwargs: (_ for _ in ()).throw(NotImplementedError("skip")))
    good_provider = SimpleNamespace(get_stock_data=lambda *args, **kwargs: "from-fallback")
    registry = _FakeRegistry({"cn_tushare": bad_provider, "cn_akshare": good_provider})
    monkeypatch.setattr(interface, "_registry", registry)
    monkeypatch.setattr(interface, "_log_vendor_call", lambda **kwargs: None)
    monkeypatch.setattr(interface, "get_vendor", lambda *args, **kwargs: "cn_tushare,cn_akshare")
    monkeypatch.setattr(interface, "_infer_market", lambda *args, **kwargs: "cn")

    value, meta = interface.route_to_vendor_with_meta("get_stock_data", symbol="000001.SH", start_date="2026-01-01", end_date="2026-01-02")

    assert value == "from-fallback"
    assert meta["status"] == "fallback"
    assert meta["vendor"] == "cn_akshare"
    assert meta["fallback_chain"][:2] == ["cn_tushare", "cn_akshare"]


def test_route_to_vendor_with_meta_all_failed(monkeypatch):
    p1 = SimpleNamespace(get_stock_data=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad1")))
    p2 = SimpleNamespace(get_stock_data=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad2")))
    registry = _FakeRegistry({"v1": p1, "v2": p2})
    monkeypatch.setattr(interface, "_registry", registry)
    monkeypatch.setattr(interface, "_log_vendor_call", lambda **kwargs: None)
    monkeypatch.setattr(interface, "get_vendor", lambda *args, **kwargs: "v1,v2")
    monkeypatch.setattr(interface, "_infer_market", lambda *args, **kwargs: "global")

    value, meta = interface.route_to_vendor_with_meta("get_stock_data", symbol="MSFT", start_date="2026-01-01", end_date="2026-01-02")

    assert value is None
    assert meta["status"] == "error"
    assert meta["vendor"] is None
    assert "RuntimeError" in str(meta.get("error"))
    assert meta["fallback_chain"][:2] == ["v1", "v2"]


def test_route_to_vendor_raises_on_error(monkeypatch):
    monkeypatch.setattr(
        interface,
        "route_to_vendor_with_meta",
        lambda *args, **kwargs: (None, {"status": "error", "fallback_chain": ["a", "b"], "error": "bad"}),
    )
    with pytest.raises(RuntimeError, match="No available vendor"):
        interface.route_to_vendor("get_stock_data", symbol="MSFT", start_date="2026-01-01", end_date="2026-01-02")


def test_route_to_vendor_with_meta_fields_complete(monkeypatch):
    provider = SimpleNamespace(get_stock_data=lambda *args, **kwargs: "ok")
    registry = _FakeRegistry({"single": provider})
    monkeypatch.setattr(interface, "_registry", registry)
    monkeypatch.setattr(interface, "_log_vendor_call", lambda **kwargs: None)
    monkeypatch.setattr(interface, "get_vendor", lambda *args, **kwargs: "single")
    monkeypatch.setattr(interface, "_infer_market", lambda *args, **kwargs: "us")

    _, meta = interface.route_to_vendor_with_meta("get_stock_data", symbol="AAPL", start_date="2026-01-01", end_date="2026-01-02")
    for field in ("method", "category", "market", "vendor", "status", "fetched_at", "latency_ms", "total_latency_ms", "fallback_chain"):
        assert field in meta


def test_enrich_data_source_item_for_internal():
    item = enrich_data_source_item(
        "indicators",
        {
            "vendor": "internal",
            "status": "internal",
            "fetched_at": "2026-05-07T00:00:00Z",
            "latency_ms": None,
            "fallback_chain": [],
        },
    )
    assert item["key"] == "indicators"
    assert item["category"] == "internal"
    assert item["vendor"] == "internal"
    assert item["vendor_display"]
