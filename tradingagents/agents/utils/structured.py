"""Structured output helpers with provider capability routing."""

from __future__ import annotations

import os
from typing import Any, Type

from pydantic import BaseModel, ValidationError

from tradingagents.llm_clients.base_client import BaseLLMClient
from tradingagents.llm_clients.capabilities import get_capabilities


def upgrade_structured_output_enabled(config: dict | None = None) -> bool:
    if config and config.get("upgrade_structured_output"):
        return True
    return os.getenv("TA_UPGRADE_STRUCTURED_OUTPUT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def resolve_structured_method(model_id: str, provider: str) -> str:
    caps = get_capabilities(model_id)
    provider_lower = (provider or "").lower()
    if provider_lower == "anthropic":
        return "json_schema" if caps.supports_json_schema else "function_calling"
    if provider_lower == "google":
        return "json_schema" if caps.supports_json_schema else "function_calling"
    return caps.preferred_structured_method


async def ainvoke_structured(
    client: BaseLLMClient,
    schema: Type[BaseModel],
    prompt: str,
    *,
    provider: str,
    model_id: str,
) -> BaseModel | None:
    method = resolve_structured_method(model_id, provider)
    try:
        llm = client.with_structured_output(schema, method=method)
        if hasattr(llm, "ainvoke"):
            return await llm.ainvoke(prompt)
        return llm.invoke(prompt)
    except (ValidationError, TypeError, ValueError, AttributeError):
        return None
    except Exception:
        return None
