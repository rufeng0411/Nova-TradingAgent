"""Model name validators — catalog-driven for new providers."""

from tradingagents.llm_clients.model_catalog import get_known_models

VALID_MODELS = {
    **get_known_models(),
    "openai": sorted(
        set(get_known_models().get("openai", []))
        | {
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-5.2",
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
        }
    ),
    "anthropic": sorted(
        set(get_known_models().get("anthropic", []))
        | {"claude-3-5-sonnet-20241022", "claude-opus-4-7", "claude-sonnet-4-6"}
    ),
    "google": sorted(
        set(get_known_models().get("google", []))
        | {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.1-flash-lite"}
    ),
    "xai": sorted(
        set(get_known_models().get("xai", []))
        | {"grok-4-0709", "grok-4.20-reasoning", "grok-4.20-non-reasoning"}
    ),
    "deepseek": sorted(
        set(get_known_models().get("deepseek", []))
        | {"deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro"}
    ),
    "qwen": sorted(set(get_known_models().get("qwen", []))),
    "glm": sorted(set(get_known_models().get("glm", []))),
    "minimax": sorted(set(get_known_models().get("minimax", []))),
}


def validate_model(provider: str, model: str) -> bool:
    provider_lower = provider.lower()
    if provider_lower in ("ollama", "openrouter", "azure", "custom"):
        return True
    if model == "custom":
        return True
    if provider_lower not in VALID_MODELS:
        return True
    return model in VALID_MODELS[provider_lower]
