"""Shared model catalog for UI selections and validation."""

from __future__ import annotations

from typing import Dict, List, Tuple

ModelOption = Tuple[str, str]
ProviderModeOptions = Dict[str, Dict[str, List[ModelOption]]]

# Legacy IDs retained for existing user configs
_LEGACY_OPENAI: List[ModelOption] = [
    ("GPT-4o (legacy)", "gpt-4o"),
    ("GPT-4o Mini (legacy)", "gpt-4o-mini"),
]

_GLM_MODELS: Dict[str, List[ModelOption]] = {
    "quick": [
        ("GLM-5-Turbo - Fast", "glm-5-turbo"),
        ("GLM-4.7 - Previous-gen flagship", "glm-4.7"),
        ("Custom model ID", "custom"),
    ],
    "deep": [
        ("GLM-5.1 - Latest flagship", "glm-5.1"),
        ("GLM-5 - Flagship", "glm-5"),
        ("Custom model ID", "custom"),
    ],
}

_QWEN_MODELS: Dict[str, List[ModelOption]] = {
    "quick": [
        ("Qwen 3.6 Flash", "qwen3.6-flash"),
        ("Qwen 3.5 Flash", "qwen3.5-flash"),
        ("Custom model ID", "custom"),
    ],
    "deep": [
        ("Qwen 3.6 Plus", "qwen3.6-plus"),
        ("Qwen 3.5 Plus", "qwen3.5-plus"),
        ("Qwen 3 Max", "qwen3-max"),
        ("Custom model ID", "custom"),
    ],
}

_MINIMAX_MODELS: Dict[str, List[ModelOption]] = {
    "quick": [
        ("MiniMax-M2.7-highspeed", "MiniMax-M2.7-highspeed"),
        ("Custom model ID", "custom"),
    ],
    "deep": [
        ("MiniMax-M2.7", "MiniMax-M2.7"),
        ("MiniMax-M2.7-highspeed", "MiniMax-M2.7-highspeed"),
        ("Custom model ID", "custom"),
    ],
}

MODEL_OPTIONS: ProviderModeOptions = {
    "openai": {
        "quick": _LEGACY_OPENAI + [
            ("GPT-5.4 Mini", "gpt-5.4-mini"),
            ("GPT-5.5", "gpt-5.5"),
            ("GPT-4.1", "gpt-4.1"),
        ],
        "deep": _LEGACY_OPENAI + [
            ("GPT-5.5", "gpt-5.5"),
            ("GPT-5.4", "gpt-5.4"),
            ("GPT-5.2", "gpt-5.2"),
        ],
    },
    "anthropic": {
        "quick": [
            ("Claude Sonnet 4.6", "claude-sonnet-4-6"),
            ("Claude Haiku 4.5", "claude-haiku-4-5"),
            ("Claude 3.5 Sonnet (legacy)", "claude-3-5-sonnet-20241022"),
        ],
        "deep": [
            ("Claude Opus 4.7", "claude-opus-4-7"),
            ("Claude Opus 4.5", "claude-opus-4-5"),
            ("Claude Sonnet 4.6", "claude-sonnet-4-6"),
        ],
    },
    "google": {
        "quick": [
            ("Gemini 3 Flash (preview)", "gemini-3-flash-preview"),
            ("Gemini 2.5 Flash", "gemini-2.5-flash"),
            ("Gemini 3.1 Flash Lite (GA)", "gemini-3.1-flash-lite"),
        ],
        "deep": [
            ("Gemini 3.1 Pro (preview)", "gemini-3.1-pro-preview"),
            ("Gemini 2.5 Pro", "gemini-2.5-pro"),
        ],
    },
    "xai": {
        "quick": [
            ("Grok 4.20 Non-Reasoning", "grok-4.20-non-reasoning"),
            ("Grok 4 Fast Non-Reasoning", "grok-4-fast-non-reasoning"),
        ],
        "deep": [
            ("Grok 4.20 Reasoning", "grok-4.20-reasoning"),
            ("Grok 4", "grok-4-0709"),
        ],
    },
    "deepseek": {
        "quick": [
            ("DeepSeek V4 Flash", "deepseek-v4-flash"),
            ("DeepSeek Chat", "deepseek-chat"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("DeepSeek V4 Pro", "deepseek-v4-pro"),
            ("DeepSeek Reasoner", "deepseek-reasoner"),
            ("DeepSeek Chat", "deepseek-chat"),
            ("Custom model ID", "custom"),
        ],
    },
    "qwen": _QWEN_MODELS,
    "qwen-cn": _QWEN_MODELS,
    "glm": _GLM_MODELS,
    "glm-cn": _GLM_MODELS,
    "minimax": _MINIMAX_MODELS,
    "minimax-cn": _MINIMAX_MODELS,
    "openrouter": {
        "quick": [("Custom model ID", "custom")],
        "deep": [("Custom model ID", "custom")],
    },
    "azure": {
        "quick": [("Deployment name", "custom")],
        "deep": [("Deployment name", "custom")],
    },
    "ollama": {
        "quick": [
            ("Qwen3:latest", "qwen3:latest"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("GLM-4.7-Flash:latest", "glm-4.7-flash:latest"),
            ("Custom model ID", "custom"),
        ],
    },
}

REGIONS = [
    {"id": "intl", "label": "海外"},
    {"id": "cn", "label": "国内"},
]


def get_model_options(provider: str, mode: str) -> List[ModelOption]:
    provider_key = provider.lower()
    if provider_key not in MODEL_OPTIONS:
        return [("Custom model ID", "custom")]
    return MODEL_OPTIONS[provider_key][mode]


def get_known_models() -> Dict[str, List[str]]:
    return {
        provider: sorted({value for options in mode_options.values() for _, value in options})
        for provider, mode_options in MODEL_OPTIONS.items()
    }


def build_catalog_response() -> dict:
    """API payload for GET /v1/llm/catalog."""
    providers = {}
    for provider, modes in MODEL_OPTIONS.items():
        providers[provider] = {
            "quick": [{"label": label, "id": mid} for label, mid in modes.get("quick", [])],
            "deep": [{"label": label, "id": mid} for label, mid in modes.get("deep", [])],
        }
    return {"providers": providers, "regions": REGIONS}
