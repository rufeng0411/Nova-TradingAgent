"""A 股名称 ↔ 代码缓存、展示标签与自选解析（独立于 api.main，避免循环导入）。"""

from __future__ import annotations

import logging
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from api.symbol_utils import (
    cn_symbol_supports_extended_kline,
    format_stock_display_label,
    normalize_exchange_symbol,
    looks_like_us_style_equity_ticker,
)

logger = logging.getLogger(__name__)

# ── Module cache ─────────────────────────────────────────────────────────────
_cn_stock_map: Optional[Dict[str, str]] = None  # name -> "XXXXXX.SH/SZ"
_cn_stock_reverse_map: Optional[Dict[str, str]] = None  # code -> name
_cn_stock_map_lock = Lock()
_cn_stock_fetch_lock = Lock()

_cn_stock_map_loaded_at: float = 0
_cn_stock_map_cache_date: Optional[str] = None
_STOCK_MAP_TTL = 24 * 86400  # hard safety cap; daily freshness is controlled by cache date
_STOCK_MAP_FETCH_TIMEOUT = float(os.getenv("TA_STOCK_MAP_FETCH_TIMEOUT", "90"))
_STOCK_MAP_CACHE_PATH = Path(os.getenv("TA_STOCK_MAP_CACHE_PATH", "data_cache/stock_map_cache.json"))

CN_INDEX_SYMBOL_MAP = {
    "000001.SH": "sh000001",
    "399001.SZ": "sz399001",
    "399006.SZ": "sz399006",
    "000300.SH": "sh000300",
    "000688.SH": "sh000688",
    "000905.SH": "sh000905",
    "000852.SH": "sh000852",
    "899050.BJ": "bj899050",
}

CN_INDEX_DISPLAY_NAMES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000300.SH": "沪深300",
    "000688.SH": "科创50",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "899050.BJ": "北证50",
}

BUILTIN_CN_DISPLAY_NAMES = {
    **CN_INDEX_DISPLAY_NAMES,
    "000001.SZ": "平安银行",
    "300750.SZ": "宁德时代",
    "600036.SH": "招商银行",
    "600120.SH": "浙江东方",
    "600330.SH": "天通股份",
    "600406.SH": "国电南瑞",
    "600519.SH": "贵州茅台",
    "600879.SH": "航天电子",
    "603876.SH": "鼎胜新材",
    "510300.SH": "沪深300ETF",
}

BUILTIN_CN_NAME_TO_SYMBOL = {name: code for code, name in BUILTIN_CN_DISPLAY_NAMES.items()}
BUILTIN_CN_NAME_ALIASES = {
    "鼎盛新材": "603876.SH",
}


def _log(msg: str) -> None:
    logger.info(msg)


def _today_cache_date() -> str:
    return date.today().isoformat()


def _read_persistent_stock_map() -> Tuple[Dict[str, str], Optional[str]]:
    try:
        raw = json.loads(_STOCK_MAP_CACHE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, None
    except Exception as exc:
        _log(f"[StockMap] Persistent cache ignored: {exc}")
        return {}, None

    payload = raw.get("name_to_code") if isinstance(raw, dict) else None
    cache_date = raw.get("date") if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        return {}, cache_date if isinstance(cache_date, str) else None

    result: Dict[str, str] = {}
    for name, code in payload.items():
        n = str(name or "").strip()
        c = str(code or "").strip().upper()
        if n and c:
            result[n] = c
    return result, cache_date if isinstance(cache_date, str) else None


def _write_persistent_stock_map(name_to_code: Dict[str, str]) -> None:
    if not name_to_code:
        return
    payload = {
        "date": _today_cache_date(),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "name_to_code": name_to_code,
    }
    try:
        _STOCK_MAP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = _STOCK_MAP_CACHE_PATH.with_suffix(_STOCK_MAP_CACHE_PATH.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        tmp_path.replace(_STOCK_MAP_CACHE_PATH)
    except Exception as exc:
        _log(f"[StockMap] Failed to write persistent cache: {exc}")


def _set_memory_stock_map(
    name_to_code: Dict[str, str],
    *,
    loaded_at: Optional[float] = None,
    cache_date: Optional[str] = None,
) -> Dict[str, str]:
    global _cn_stock_map, _cn_stock_reverse_map, _cn_stock_map_loaded_at, _cn_stock_map_cache_date
    with _cn_stock_map_lock:
        _cn_stock_map = dict(name_to_code)
        _cn_stock_reverse_map = {code: name for name, code in _cn_stock_map.items()}
        _cn_stock_map_loaded_at = loaded_at if loaded_at is not None else time.time()
        _cn_stock_map_cache_date = cache_date or _today_cache_date()
    return _cn_stock_map


def _call_ak_with_timeout(label: str, fn, timeout_sec: float):
    def _runner():
        return fn()

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_runner)
        try:
            return fut.result(timeout=timeout_sec)
        except FuturesTimeoutError as exc:
            raise TimeoutError(f"{label} exceeded {timeout_sec:.0f}s") from exc


def _normalize_bare_listed_code(code: str) -> str:
    """构建 name→code 映射时使用，避免在加载缓存过程中递归调用 load_cn_stock_map。"""
    return normalize_exchange_symbol((code or "").strip(), None).strip().upper()


def _download_cn_stock_map_body() -> Dict[str, str]:
    import akshare as ak

    result: Dict[str, str] = {}
    df = _call_ak_with_timeout(
        "ak.stock_info_a_code_name",
        ak.stock_info_a_code_name,
        _STOCK_MAP_FETCH_TIMEOUT,
    )
    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        code = str(row.get("code", "")).strip()
        if name and code:
            result[name] = _normalize_bare_listed_code(code)
    stock_count = len(result)
    fund_count = 0
    try:
        fund_df = _call_ak_with_timeout(
            "ak.fund_name_em",
            ak.fund_name_em,
            min(_STOCK_MAP_FETCH_TIMEOUT, 120.0),
        )
        existing_codes = set(result.values())
        for _, row in fund_df.iterrows():
            code = str(row.get("基金代码", "")).strip()
            name = str(row.get("基金简称", "")).strip()
            if name and code and len(code) == 6 and code.isdigit():
                normalized = _normalize_bare_listed_code(code)
                if normalized not in existing_codes:
                    result[name] = normalized
                    existing_codes.add(normalized)
        fund_count = len(result) - stock_count
    except Exception as fe:
        _log(f"[StockMap] ETF/fund load skipped: {fe}")
    _log(f"[StockMap] Loaded {stock_count} stocks + {fund_count} ETFs/funds = {len(result)} total.")
    return result


def load_cn_stock_map() -> Dict[str, str]:
    """Lazy-load A-share + ETF name→code（内存驻留，磁盘持久化，每日刷新）。"""
    global _cn_stock_map, _cn_stock_reverse_map, _cn_stock_map_loaded_at, _cn_stock_map_cache_date
    now = time.time()
    today = _today_cache_date()
    if _cn_stock_map:
        if _cn_stock_map_cache_date == today and (now - _cn_stock_map_loaded_at) <= _STOCK_MAP_TTL:
            return _cn_stock_map
    elif _cn_stock_map is not None:
        _cn_stock_map = None
        _cn_stock_reverse_map = None
        _cn_stock_map_cache_date = None

    stale_map = dict(_cn_stock_map or {})

    with _cn_stock_fetch_lock:
        now = time.time()
        today = _today_cache_date()
        if _cn_stock_map and _cn_stock_map_cache_date == today and (now - _cn_stock_map_loaded_at) <= _STOCK_MAP_TTL:
            return _cn_stock_map
        stale_map = dict(_cn_stock_map or stale_map)
        disk_map, disk_date = _read_persistent_stock_map()
        if disk_map:
            if disk_date == today:
                return _set_memory_stock_map(disk_map, cache_date=disk_date)
            if not stale_map:
                stale_map = disk_map

        result: Dict[str, str] = {}
        try:
            result = _download_cn_stock_map_body()
        except Exception as e:
            _log(f"[StockMap] Failed to load: {e}")
            if stale_map:
                return _set_memory_stock_map(stale_map)
            return {}

        if not result:
            _log("[StockMap] Empty stock map load ignored; will retry on next request.")
            if stale_map:
                return _set_memory_stock_map(stale_map)
            return {}

        _write_persistent_stock_map(result)
        return _set_memory_stock_map(result)


def get_reverse_stock_map() -> Dict[str, str]:
    load_cn_stock_map()
    return dict(_cn_stock_reverse_map or {})


def get_reverse_stock_map_cached_only() -> Dict[str, str]:
    if _cn_stock_map is None or _cn_stock_reverse_map is None:
        return {}
    return dict(_cn_stock_reverse_map)


def normalize_symbol(raw: str) -> str:
    return normalize_exchange_symbol(raw or "", load_cn_stock_map()).strip().upper()


def resolve_cn_display_name(symbol_key: str) -> Optional[str]:
    sk = (symbol_key or "").strip().upper()
    if not sk:
        return None
    if sk in BUILTIN_CN_DISPLAY_NAMES:
        return BUILTIN_CN_DISPLAY_NAMES[sk]
    rev = get_reverse_stock_map()
    if sk in rev:
        return rev[sk]
    return None


def is_cn_index_symbol(symbol: str) -> bool:
    return symbol.upper() in CN_INDEX_SYMBOL_MAP


def _search_cn_stock_by_name_in_map(query: str, stock_map: Dict[str, str]) -> Optional[str]:
    if not query:
        return None
    if query in BUILTIN_CN_NAME_ALIASES:
        return BUILTIN_CN_NAME_ALIASES[query]
    if query in stock_map:
        return stock_map[query]
    candidates = [(name, code) for name, code in stock_map.items() if query in name or name in query]
    if len(candidates) == 1:
        return candidates[0][1]
    if candidates:
        candidates.sort(key=lambda x: len(x[0]))
        return candidates[0][1]
    if len(query) >= 4:
        fuzzy_candidates = [
            (SequenceMatcher(None, query, name).ratio(), name, code)
            for name, code in stock_map.items()
            if abs(len(name) - len(query)) <= 2
        ]
        fuzzy_candidates = [item for item in fuzzy_candidates if item[0] >= 0.75]
        fuzzy_candidates.sort(key=lambda item: (item[0], -len(item[1])), reverse=True)
        if fuzzy_candidates and (
            len(fuzzy_candidates) == 1 or fuzzy_candidates[0][0] - fuzzy_candidates[1][0] >= 0.08
        ):
            return fuzzy_candidates[0][2]
    return None


def search_cn_stock_by_name(query: str) -> Optional[str]:
    query = query.strip()
    if not query:
        return None
    if query in BUILTIN_CN_NAME_ALIASES:
        return BUILTIN_CN_NAME_ALIASES[query]
    if query in BUILTIN_CN_NAME_TO_SYMBOL:
        return BUILTIN_CN_NAME_TO_SYMBOL[query]
    stock_map = {**BUILTIN_CN_NAME_TO_SYMBOL, **load_cn_stock_map()}
    return _search_cn_stock_by_name_in_map(query, stock_map)


def display_name_for_symbol(symbol: str, *, code_to_name: Optional[Dict[str, str]] = None) -> str:
    """返回简称；未知则退回代码本身。"""
    sk = (symbol or "").strip().upper()
    if not sk:
        return ""
    cmap = code_to_name if code_to_name is not None else get_reverse_stock_map()
    return cmap.get(sk) or BUILTIN_CN_DISPLAY_NAMES.get(sk) or resolve_cn_display_name(sk) or sk


def format_display_label(name: Optional[str], symbol: str) -> str:
    return format_stock_display_label(name, symbol)


def attach_stock_names(items: List[dict], code_to_name: Dict[str, str]) -> List[dict]:
    for item in items:
        symbol = str(item.get("symbol") or "").strip().upper()
        name = code_to_name.get(symbol) or resolve_cn_display_name(symbol)
        if not name:
            name = str(item.get("name") or "").strip()
        if not name:
            name = symbol
        item["name"] = name
        item["display_label"] = format_display_label(name, symbol)
    return items


def enrich_dict_with_display(item: dict, *, code_to_name: Optional[Dict[str, str]] = None) -> dict:
    """为已有 symbol / name 的字典补充 display_label。"""
    sym = str(item.get("symbol") or "").strip().upper()
    if not sym:
        item["display_label"] = item.get("display_label") or ""
        return item
    nm = item.get("name")
    if isinstance(nm, str) and nm.strip():
        pass
    else:
        nm = display_name_for_symbol(sym, code_to_name=code_to_name)
        item["name"] = nm
    item["display_label"] = format_display_label(nm, sym)
    return item


def apply_display_label_to_report_row(row: Any, *, code_to_name: Optional[Dict[str, str]] = None) -> None:
    """为 ReportORM 等对象设置 name（若缺）与 display_label。"""
    sym = str(getattr(row, "symbol", "") or "").strip().upper()
    if not sym:
        setattr(row, "display_label", "")
        return
    nm_attr = getattr(row, "name", None)
    nm = nm_attr.strip() if isinstance(nm_attr, str) else ""
    if not nm and code_to_name is not None:
        nm = str(code_to_name.get(sym, "") or "")
    if not nm:
        nm = display_name_for_symbol(sym, code_to_name=code_to_name)
    nm_out = nm or sym
    try:
        setattr(row, "name", nm_out)
    except Exception:
        pass
    setattr(row, "display_label", format_display_label(nm_out if nm_out != sym else None, sym))


def resolve_watchlist_identifier(
    raw: str,
    name_to_code: Dict[str, str],
    code_to_name: Dict[str, str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    token = raw.strip()
    if not token:
        return None, None, "输入为空"
    if token in name_to_code:
        symbol = name_to_code[token]
        return symbol, code_to_name.get(symbol, token), None
    name_symbol = _search_cn_stock_by_name_in_map(token, {**BUILTIN_CN_NAME_TO_SYMBOL, **name_to_code})
    if name_symbol:
        return name_symbol, code_to_name.get(name_symbol) or resolve_cn_display_name(name_symbol) or token, None
    symbol = normalize_symbol(token)
    if symbol in code_to_name:
        return symbol, code_to_name.get(symbol, symbol), None
    if cn_symbol_supports_extended_kline(symbol):
        name_hint = re.sub(r"\d{6}(?:\.(?:SH|SZ|SS|BJ))?", "", token, flags=re.I).strip()
        return symbol, code_to_name.get(symbol) or name_hint or symbol, None
    return None, None, f"未识别的股票代码或名称: {token}"


def resolve_stock(raw: str) -> Dict[str, Any]:
    """将用户输入解析为规范 symbol、名称与展示标签（尽力而为）。"""
    token = (raw or "").strip()
    if not token:
        return {"symbol": "", "name": "", "display_label": "", "error": "empty"}
    name_to_code = load_cn_stock_map()
    code_to_name = get_reverse_stock_map()
    sym: Optional[str] = None
    nm = ""
    err: Optional[str] = None

    if token in name_to_code:
        sym = name_to_code[token]
        nm = code_to_name.get(sym, token)
    else:
        cand = normalize_symbol(token)
        if cand in code_to_name:
            sym, nm = cand, code_to_name[cand]
        elif re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", cand, re.I) or looks_like_us_style_equity_ticker(cand):
            sym = cand
            nm = resolve_cn_display_name(sym) or ""

    if sym:
        nm_filled = nm or display_name_for_symbol(sym)
        lbl = format_display_label(nm_filled or None, sym)
        return {"symbol": sym, "name": nm_filled, "display_label": lbl, "error": None}

    err = "unresolved"
    return {"symbol": token.strip().upper(), "name": "", "display_label": token.strip().upper(), "error": err}


def split_watchlist_batch_text(text: str) -> List[str]:
    return [t.strip() for t in re.split(r"[\s,，、；;]+", text.strip()) if t.strip()]
