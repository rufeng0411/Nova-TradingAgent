"""Intent ticker 与 fallback 合并（无 langgraph/langchain 依赖，供单测与 intent_parser 使用）。"""

from __future__ import annotations

import re
from typing import Any, Optional


def merge_llm_ticker_with_fallback(parsed_ticker: Any, fallback_ticker: Optional[str]) -> str:
    """LLM 常把 ticker 填成中文简称；若 fallback 已含 6 位交易所代码而解析结果不含数字，以 fallback 为准。"""
    fb = (fallback_ticker or "").strip()
    raw = parsed_ticker if isinstance(parsed_ticker, str) else ""
    raw = raw.strip()
    if fb and re.search(r"\d{6}", fb) and not re.search(r"\d{6}", raw):
        return fb.upper().replace(".SS", ".SH")
    return (raw or fb).strip()
