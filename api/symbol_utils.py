"""A 股 / 美股标的字符串规范化（供任务调度与单测使用，避免 import api.main 拉起全量依赖）。"""

from __future__ import annotations

import re
from typing import Mapping, Optional


def cn_symbol_supports_extended_kline(symbol: str) -> bool:
    s = symbol.upper().strip()
    if "." in s:
        return s.endswith((".SH", ".SZ", ".BJ"))
    return len(s) == 6 and s.isdigit()


def looks_like_us_style_equity_ticker(sym: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{1,6}(?:\.[A-Z]{1,4})?", (sym or "").strip().upper()))


def normalize_exchange_symbol(raw: str, name_to_code: Optional[Mapping[str, str]] = None) -> str:
    """从「名称+代码」等混输中提取交易所代码；可选中文名→代码映射（与 AkShare 全市场表一致）。"""
    s = raw.strip().upper()
    m = re.search(r"(\d{6})(?:\.(SH|SZ|SS|BJ))?", s)
    if m:
        code = m.group(1)
        suffix = m.group(2)
        if suffix:
            if suffix == "SS":
                return f"{code}.SH"
            return f"{code}.{suffix}"
        if code.startswith(("4", "8")) or code.startswith("92"):
            return f"{code}.BJ"
        market = "SH" if code.startswith(("5", "6", "9")) else "SZ"
        return f"{code}.{market}"
    if re.fullmatch(r"[A-Z]{1,6}(?:\.[A-Z]{1,3})?", s):
        return s
    if name_to_code is not None and s in name_to_code:
        return name_to_code[s]
    return s


def effective_data_ticker(
    normalized_request_symbol: str,
    intent_ticker: object,
    *,
    name_to_code: Optional[Mapping[str, str]] = None,
) -> str:
    """数据采集用 ticker：禁止已规范化的 A 股代码被 LLM 填的中文简称覆盖。"""
    base = normalize_exchange_symbol(normalized_request_symbol or "", name_to_code).strip().upper()
    if intent_ticker is None:
        return base
    raw_it = intent_ticker if isinstance(intent_ticker, str) else str(intent_ticker)
    it = raw_it.strip()
    if not it:
        return base
    cand = normalize_exchange_symbol(it, name_to_code).strip().upper()
    if cn_symbol_supports_extended_kline(base):
        return base
    if cn_symbol_supports_extended_kline(cand):
        return cand
    if looks_like_us_style_equity_ticker(base):
        return base
    if looks_like_us_style_equity_ticker(cand):
        return cand
    return cand or base


def normalize_name_key(raw: str) -> str:
    """证券简称用于映射查找前的规范化：去首尾空白（不改变大小写；A 股简称多为中文）。"""
    return (raw or "").strip()


def _collapse_duplicate_cn_listing_suffix(sym: str) -> str:
    """将 603876.SH.SH 等误拼接规范为单个交易所后缀。"""
    s = (sym or "").strip()
    m = re.fullmatch(r"(\d{6}\.(?:SH|SZ|BJ))(?:\.(?:SH|SZ|BJ))+", s, flags=re.I)
    if m:
        return m.group(1).upper()
    return s


def format_stock_display_label(name: Optional[str], symbol: str) -> str:
    """用户界面展示：「名称 代码」，例如：贵州茅台 600519.SH。

    - 有名称为名称 + 空格 + 规范代码
    - 仅有代码则只展示代码
    - 美股等仅展示 ticker
    - 对明显非行情代码的字符串保留原始大小写（避免异常输入被 .upper() 扭曲）
    """
    sym_raw = _collapse_duplicate_cn_listing_suffix((symbol or "").strip())
    if cn_symbol_supports_extended_kline(sym_raw) or looks_like_us_style_equity_ticker(sym_raw):
        sym = sym_raw.upper()
    elif re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", sym_raw, re.I):
        sym = sym_raw.upper()
    else:
        sym = sym_raw
    n = normalize_name_key(name or "")
    if n.upper() == sym.upper():
        return sym
    if n and sym:
        return f"{n} {sym}".strip()
    if sym:
        return sym
    return n or ""
