import os
from typing import Optional

from .openai_client import OpenAIClient
from .validators import validate_model

_GLM_BASE_URLS = {
    "cn": "https://open.bigmodel.cn/api/paas/v4",
    "intl": "https://api.z.ai/api/paas/v4",
}


class GLMClient(OpenAIClient):
    """GLM via Z.AI / BigModel OpenAI-compatible endpoints."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        region: str = "cn",
        **kwargs,
    ):
        region_norm = (region or "cn").lower()
        resolved = base_url or _GLM_BASE_URLS.get(region_norm, _GLM_BASE_URLS["cn"])
        provider = "glm-cn" if region_norm == "cn" else "glm"
        super().__init__(model, resolved, provider=provider, **kwargs)
        self.region = region_norm

    def get_llm(self):
        if self.region == "cn":
            api_key = (
                self.kwargs.get("api_key")
                or os.getenv("ZHIPU_CN_API_KEY")
                or os.getenv("ZHIPU_API_KEY")
            )
        else:
            api_key = self.kwargs.get("api_key") or os.getenv("ZHIPU_API_KEY")
        if api_key:
            self.kwargs["api_key"] = api_key
        return super().get_llm()

    def validate_model(self) -> bool:
        return validate_model("glm", self.model)
