"""symbol_utils / symbol_service 展示与解析单测（不依赖 AkShare 网络）。"""

import pytest
import time
import json

pytestmark = pytest.mark.no_init_db

from api.symbol_utils import format_stock_display_label, normalize_name_key
from api.services import symbol_service


def test_format_stock_display_label_basic() -> None:
    assert format_stock_display_label("贵州茅台", "600519.SH") == "贵州茅台 600519.SH"
    assert format_stock_display_label(None, "600519.SH") == "600519.SH"
    assert format_stock_display_label("", "AAPL") == "AAPL"


def test_format_stock_display_label_dedupes_name_equals_symbol() -> None:
    assert format_stock_display_label("600519.SH", "600519.SH") == "600519.SH"


def test_format_stock_display_label_collapses_double_exchange_suffix() -> None:
    assert format_stock_display_label("鼎胜新材", "603876.SH.SH") == "鼎胜新材 603876.SH"


def test_normalize_name_key() -> None:
    assert normalize_name_key("  茅台  ") == "茅台"


def test_attach_stock_names_adds_display_label() -> None:
    items = [{"symbol": "600519.SH", "id": "1"}]
    code_to_name = {"600519.SH": "贵州茅台"}
    symbol_service.attach_stock_names(items, code_to_name)
    assert items[0]["name"] == "贵州茅台"
    assert items[0]["display_label"] == "贵州茅台 600519.SH"


def test_resolve_cn_display_name_index_fallback() -> None:
    assert symbol_service.resolve_cn_display_name("000001.SH") == "上证指数"


def test_display_name_for_builtin_symbol_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        symbol_service,
        "get_reverse_stock_map",
        lambda: (_ for _ in ()).throw(AssertionError("network load should not run for builtin")),
    )

    assert symbol_service.display_name_for_symbol("300750.SZ", code_to_name={}) == "宁德时代"
    assert symbol_service.search_cn_stock_by_name("宁德时代") == "300750.SZ"


def test_search_cn_stock_by_common_alias_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        symbol_service,
        "load_cn_stock_map",
        lambda: (_ for _ in ()).throw(AssertionError("network load should not run for builtin alias")),
    )

    assert symbol_service.search_cn_stock_by_name("鼎盛新材") == "603876.SH"


def test_enrich_dict_with_display() -> None:
    d = {"symbol": "600519.SH"}
    symbol_service.enrich_dict_with_display(d, code_to_name={"600519.SH": "贵州茅台"})
    assert d["display_label"] == "贵州茅台 600519.SH"


def test_resolve_watchlist_identifier_accepts_mixed_name_and_code_without_map() -> None:
    symbol, name, error = symbol_service.resolve_watchlist_identifier("天通股份600330", {}, {})

    assert error is None
    assert symbol == "600330.SH"
    assert name == "天通股份"


def test_resolve_watchlist_identifier_accepts_stock_name_alias_without_map() -> None:
    symbol, name, error = symbol_service.resolve_watchlist_identifier("鼎盛新材", {}, {})

    assert error is None
    assert symbol == "603876.SH"
    assert name == "鼎胜新材"


def test_load_cn_stock_map_retries_empty_cache(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(symbol_service, "_STOCK_MAP_CACHE_PATH", tmp_path / "missing_cache.json")
    monkeypatch.setattr(symbol_service, "_cn_stock_map", {})
    monkeypatch.setattr(symbol_service, "_cn_stock_reverse_map", {})
    monkeypatch.setattr(symbol_service, "_cn_stock_map_loaded_at", time.time())
    monkeypatch.setattr(
        symbol_service,
        "_download_cn_stock_map_body",
        lambda: {"宁德时代": "300750.SZ"},
    )

    loaded = symbol_service.load_cn_stock_map()

    assert loaded == {"宁德时代": "300750.SZ"}
    assert symbol_service.get_reverse_stock_map_cached_only()["300750.SZ"] == "宁德时代"


def test_load_cn_stock_map_keeps_stale_non_empty_cache_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    stale = {"贵州茅台": "600519.SH"}
    monkeypatch.setattr(symbol_service, "_STOCK_MAP_CACHE_PATH", tmp_path / "missing_cache.json")
    monkeypatch.setattr(symbol_service, "_cn_stock_map", stale.copy())
    monkeypatch.setattr(symbol_service, "_cn_stock_reverse_map", {"600519.SH": "贵州茅台"})
    monkeypatch.setattr(
        symbol_service,
        "_cn_stock_map_loaded_at",
        time.time() - symbol_service._STOCK_MAP_TTL - 1,
    )

    def fail_download() -> dict[str, str]:
        raise TimeoutError("simulated download failure")

    monkeypatch.setattr(symbol_service, "_download_cn_stock_map_body", fail_download)

    loaded = symbol_service.load_cn_stock_map()

    assert loaded == stale
    assert symbol_service.get_reverse_stock_map_cached_only()["600519.SH"] == "贵州茅台"


def test_load_cn_stock_map_uses_fresh_persistent_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    cache_path = tmp_path / "stock_map_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "date": symbol_service._today_cache_date(),
                "name_to_code": {"宁德时代": "300750.SZ"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(symbol_service, "_STOCK_MAP_CACHE_PATH", cache_path)
    monkeypatch.setattr(symbol_service, "_cn_stock_map", None)
    monkeypatch.setattr(symbol_service, "_cn_stock_reverse_map", None)
    monkeypatch.setattr(symbol_service, "_download_cn_stock_map_body", lambda: pytest.fail("fresh disk cache should be used"))

    loaded = symbol_service.load_cn_stock_map()

    assert loaded == {"宁德时代": "300750.SZ"}
    assert symbol_service.get_reverse_stock_map_cached_only()["300750.SZ"] == "宁德时代"


def test_load_cn_stock_map_refreshes_stale_persistent_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    cache_path = tmp_path / "stock_map_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "date": "2000-01-01",
                "name_to_code": {"旧名称": "000001.SZ"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(symbol_service, "_STOCK_MAP_CACHE_PATH", cache_path)
    monkeypatch.setattr(symbol_service, "_cn_stock_map", None)
    monkeypatch.setattr(symbol_service, "_cn_stock_reverse_map", None)
    monkeypatch.setattr(
        symbol_service,
        "_download_cn_stock_map_body",
        lambda: {"贵州茅台": "600519.SH"},
    )

    loaded = symbol_service.load_cn_stock_map()
    saved = json.loads(cache_path.read_text(encoding="utf-8"))

    assert loaded == {"贵州茅台": "600519.SH"}
    assert saved["date"] == symbol_service._today_cache_date()
    assert saved["name_to_code"] == {"贵州茅台": "600519.SH"}


def test_load_cn_stock_map_uses_stale_persistent_cache_when_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    cache_path = tmp_path / "stock_map_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "date": "2000-01-01",
                "name_to_code": {"贵州茅台": "600519.SH"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(symbol_service, "_STOCK_MAP_CACHE_PATH", cache_path)
    monkeypatch.setattr(symbol_service, "_cn_stock_map", None)
    monkeypatch.setattr(symbol_service, "_cn_stock_reverse_map", None)

    def fail_download() -> dict[str, str]:
        raise TimeoutError("simulated download failure")

    monkeypatch.setattr(symbol_service, "_download_cn_stock_map_body", fail_download)

    loaded = symbol_service.load_cn_stock_map()

    assert loaded == {"贵州茅台": "600519.SH"}
    assert symbol_service.get_reverse_stock_map_cached_only()["600519.SH"] == "贵州茅台"


def test_load_cn_stock_map_refreshes_memory_cache_on_next_day(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(symbol_service, "_STOCK_MAP_CACHE_PATH", tmp_path / "missing_cache.json")
    monkeypatch.setattr(symbol_service, "_cn_stock_map", {"旧名称": "000001.SZ"})
    monkeypatch.setattr(symbol_service, "_cn_stock_reverse_map", {"000001.SZ": "旧名称"})
    monkeypatch.setattr(symbol_service, "_cn_stock_map_loaded_at", time.time())
    monkeypatch.setattr(symbol_service, "_cn_stock_map_cache_date", "2000-01-01")
    monkeypatch.setattr(
        symbol_service,
        "_download_cn_stock_map_body",
        lambda: {"宁德时代": "300750.SZ"},
    )

    loaded = symbol_service.load_cn_stock_map()

    assert loaded == {"宁德时代": "300750.SZ"}
    assert symbol_service.get_reverse_stock_map_cached_only()["300750.SZ"] == "宁德时代"
