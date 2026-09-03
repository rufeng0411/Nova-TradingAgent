import os
from typing import Optional

from .openai_client import OpenAIClient
from .capabilities import get_capabilities
from .validators import validate_model

_MINIMAX_BASE_URLS = {
    "cn": "https://api.minimaxi.com/v1",
    "intl": "https://api.minimax.io/v1",
}


class MiniMaxClient(OpenAIClient):
    """MiniMax via OpenAI-compatible endpoints."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        region: str = "intl",
        **kwargs,
    ):
        region_norm = (region or "intl").lower()
        resolved = base_url or _MINIMAX_BASE_URLS.get(region_norm, _MINIMAX_BASE_URLS["intl"])
        provider = "minimax-cn" if region_norm == "cn" else "minimax"
        super().__init__(model, resolved, provider=provider, **kwargs)
        self.region = region_norm

    def get_llm(self):
        if self.region == "cn":
            api_key = (
                self.kwargs.get("api_key")
                or os.getenv("MINIMAX_CN_API_KEY")
                or os.getenv("MINIMAX_API_KEY")
            )
        else:
            api_key = self.kwargs.get("api_key") or os.getenv("MINIMAX_API_KEY")
        if api_key:
            self.kwargs["api_key"] = api_key
        caps = get_capabilities(self.model)
        if caps.reasoning_split:
            self.kwargs.setdefault("model_kwargs", {})["reasoning_split"] = True
        return super().get_llm()

    def validate_model(self) -> bool:
        return validate_model("minimax", self.model)
