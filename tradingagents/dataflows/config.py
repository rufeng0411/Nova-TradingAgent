import copy
from typing import Any, Dict

import tradingagents.default_config as default_config
from typing import Dict as TypingDict, Optional

# Use default config but allow it to be overridden
_config: Optional[TypingDict] = None

_NESTED_DICT_KEYS = frozenset(
    {"data_vendors", "tool_vendors", "benchmark_map", "prompt_language_by_provider"}
)


def _deep_merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge patch into base; sibling keys in nested dicts are preserved."""
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if key in _NESTED_DICT_KEYS and isinstance(value, dict) and isinstance(result.get(key), dict):
            merged = copy.deepcopy(result[key])
            merged.update(value)
            result[key] = merged
        else:
            result[key] = copy.deepcopy(value)
    return result


def initialize_config():
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = copy.deepcopy(default_config.DEFAULT_CONFIG)


def set_config(config: Dict):
    """Update the configuration with custom values (deep-merge nested dicts)."""
    global _config
    if _config is None:
        _config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    _config = _deep_merge_dict(_config, config)


def get_config() -> Dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return copy.deepcopy(_config)


# Initialize with default config
initialize_config()
