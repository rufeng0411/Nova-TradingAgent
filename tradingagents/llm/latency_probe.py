from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage

from tradingagents.llm_clients.factory import create_llm_client


def probe_model_latency(
    *,
    provider: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    started = time.perf_counter()
    ok = False
    error = None
    try:
        client = create_llm_client(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
            max_tokens=64,
        )
        llm = client.get_llm()
        llm.invoke([HumanMessage(content="ping")])
        ok = True
    except Exception as exc:
        error = str(exc)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "provider": provider,
        "model": model,
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }

