from typing import Optional

from .base_client import BaseLLMClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .google_client import GoogleClient
from .deepseek_client import DeepSeekClient
from .qwen_client import QwenClient
from .glm_client import GLMClient
from .minimax_client import MiniMaxClient
from .azure_client import AzureOpenAIClient


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider."""
    provider_lower = provider.lower()
    region = kwargs.pop("region", None)

    # Legacy bridge: openai + custom base_url stays on OpenAIClient (no host sniffing)
    if provider_lower in ("openai", "ollama", "openrouter"):
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "xai":
        return OpenAIClient(model, base_url, provider="xai", **kwargs)

    if provider_lower == "anthropic":
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "deepseek":
        return DeepSeekClient(model, base_url, **kwargs)

    if provider_lower in ("qwen", "qwen-cn"):
        reg = region or ("cn" if provider_lower == "qwen-cn" else "intl")
        return QwenClient(model, base_url, region=reg, **kwargs)

    if provider_lower in ("glm", "glm-cn"):
        reg = region or ("cn" if provider_lower == "glm-cn" else "intl")
        return GLMClient(model, base_url, region=reg, **kwargs)

    if provider_lower in ("minimax", "minimax-cn"):
        reg = region or ("cn" if provider_lower == "minimax-cn" else "intl")
        return MiniMaxClient(model, base_url, region=reg, **kwargs)

    if provider_lower == "azure":
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
