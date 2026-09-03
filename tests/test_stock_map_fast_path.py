from unittest.mock import patch

from api.services import symbol_service


def test_reverse_stock_map_cached_only_does_not_trigger_cold_load():
    original_map = symbol_service._cn_stock_map
    original_rev = symbol_service._cn_stock_reverse_map
    try:
        symbol_service._cn_stock_map = None
        symbol_service._cn_stock_reverse_map = None
        with patch.object(symbol_service, "load_cn_stock_map", side_effect=AssertionError("slow load should not run")):
            assert symbol_service.get_reverse_stock_map_cached_only() == {}
    finally:
        symbol_service._cn_stock_map = original_map
        symbol_service._cn_stock_reverse_map = original_rev


def test_reverse_stock_map_cached_only_uses_existing_cache():
    original_map = symbol_service._cn_stock_map
    original_rev = symbol_service._cn_stock_reverse_map
    try:
        symbol_service._cn_stock_map = {
            "贵州茅台": "600519.SH",
            "宁德时代": "300750.SZ",
        }
        symbol_service._cn_stock_reverse_map = {
            "600519.SH": "贵州茅台",
            "300750.SZ": "宁德时代",
        }
        assert symbol_service.get_reverse_stock_map_cached_only() == {
            "600519.SH": "贵州茅台",
            "300750.SZ": "宁德时代",
        }
    finally:
        symbol_service._cn_stock_map = original_map
        symbol_service._cn_stock_reverse_map = original_rev
