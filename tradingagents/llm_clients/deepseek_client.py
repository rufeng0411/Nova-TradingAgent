import os
from typing import Optional

from .openai_client import OpenAIClient
from .validators import validate_model

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekClient(OpenAIClient):
    """DeepSeek via OpenAI-compatible API."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(
            model,
            base_url or os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL,
            provider="deepseek",
            **kwargs,
        )

    def get_llm(self):
        llm_kwargs = {}
        api_key = self.kwargs.get("api_key") or os.getenv("DEEPSEEK_API_KEY")
        if api_key:
            llm_kwargs["api_key"] = api_key
        self.kwargs.update(llm_kwargs)
        return super().get_llm()

    def validate_model(self) -> bool:
        return validate_model("deepseek", self.model)
