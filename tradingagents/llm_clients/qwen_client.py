import os
from typing import Optional

from .openai_client import OpenAIClient
from .validators import validate_model

_QWEN_BASE_URLS = {
    "cn": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "intl": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
}


class QwenClient(OpenAIClient):
    """Qwen via DashScope OpenAI-compatible endpoints."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        region: str = "cn",
        **kwargs,
    ):
        region_norm = (region or "cn").lower()
        resolved = base_url or _QWEN_BASE_URLS.get(region_norm, _QWEN_BASE_URLS["cn"])
        provider = "qwen-cn" if region_norm == "cn" else "qwen"
        super().__init__(model, resolved, provider=provider, **kwargs)
        self.region = region_norm

    def get_llm(self):
        if self.region == "cn":
            api_key = (
                self.kwargs.get("api_key")
                or os.getenv("DASHSCOPE_CN_API_KEY")
                or os.getenv("DASHSCOPE_API_KEY")
            )
        else:
            api_key = self.kwargs.get("api_key") or os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            self.kwargs["api_key"] = api_key
        return super().get_llm()

    def validate_model(self) -> bool:
        return validate_model("qwen", self.model)
