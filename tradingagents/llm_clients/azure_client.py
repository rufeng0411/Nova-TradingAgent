import os
from typing import Optional

from .openai_client import OpenAIClient
from .validators import validate_model


class AzureOpenAIClient(OpenAIClient):
    """Azure OpenAI — deployment name is passed as model."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        endpoint = (
            base_url
            or os.getenv("AZURE_OPENAI_ENDPOINT")
            or os.getenv("TA_BASE_URL")
        )
        if endpoint and not endpoint.rstrip("/").endswith("/v1"):
            endpoint = endpoint.rstrip("/") + "/openai/v1"
        super().__init__(model, endpoint, provider="azure", **kwargs)

    def get_llm(self):
        api_key = (
            self.kwargs.get("api_key")
            or os.getenv("AZURE_OPENAI_API_KEY")
            or os.getenv("TA_API_KEY")
        )
        if api_key:
            self.kwargs["api_key"] = api_key
        return super().get_llm()

    def validate_model(self) -> bool:
        return validate_model("azure", self.model)
