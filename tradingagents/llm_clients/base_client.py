from abc import ABC, abstractmethod
from typing import Any, Optional, Type

from pydantic import BaseModel

from .capabilities import get_capabilities


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    @abstractmethod
    def get_llm(self) -> Any:
        """Return the configured LLM instance."""
        pass

    @abstractmethod
    def validate_model(self) -> bool:
        """Validate that the model is supported by this client."""
        pass

    def get_structured_method(self, model_id: str | None = None) -> str:
        """Return preferred structured output method for model."""
        mid = model_id or self.model
        return get_capabilities(mid).preferred_structured_method

    def with_structured_output(self, schema: Type[BaseModel], *, method: str | None = None) -> Any:
        """Wrap underlying LLM with structured output."""
        llm = self.get_llm()
        resolved = method or self.get_structured_method()
        if resolved == "none":
            return llm
        return llm.with_structured_output(schema, method=resolved)
