from typing import Any, Mapping

from tradingagents.dataflows.config import get_config

from .en import PROMPTS as EN_PROMPTS
from .zh import PROMPTS as ZH_PROMPTS


def _resolve_language(config: Mapping[str, Any] | None = None) -> str:
    cfg = dict(config or get_config())
    language = str(cfg.get("prompt_language", "auto")).lower()
    if language in ("zh", "en"):
        return language

    provider = str(cfg.get("llm_provider", "")).lower()
    provider_map = cfg.get("prompt_language_by_provider", {}) or {}
    mapped = str(provider_map.get(provider, "")).lower()
    if mapped in ("zh", "en"):
        return mapped

    return "en"


def get_prompt(key: str, config: Mapping[str, Any] | None = None) -> str:
    lang = _resolve_language(config)
    if lang == "zh":
        if key in ZH_PROMPTS:
            return ZH_PROMPTS[key]
        return EN_PROMPTS[key]
    return EN_PROMPTS[key]

