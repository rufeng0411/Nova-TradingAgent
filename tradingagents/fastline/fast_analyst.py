from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from tradingagents.analytics.ta_features import build_fallback_insight
from tradingagents.fastline.json_safe import json_safe
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.prompts.zh_fast import build_fast_system_prompt, build_fast_user_prompt

logger = logging.getLogger(__name__)


class FastVerdict(BaseModel):
    direction: str = "neutral"
    confidence: int = 3
    horizon: str = "same_day"
    reason: str = ""
    key_drivers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class FastAnalysisResult(BaseModel):
    verdict: FastVerdict
    time_phased_strategy: dict[str, Any] = Field(default_factory=dict)
    position_recommendation: dict[str, Any] = Field(default_factory=dict)
    executability_assessment: dict[str, Any] = Field(default_factory=dict)
    kline_insight: dict[str, Any] = Field(default_factory=dict)
    alignment: dict[str, Any] = Field(default_factory=dict)
    data_completeness: float = 0.0
    disclaimer: str = "仅供研究参考，不构成投资建议"


def _extract_json(raw: str) -> dict[str, Any]:
    m = re.search(r"\{[\s\S]*\}\s*$", raw.strip())
    if not m:
        raise ValueError("llm_output_not_json")
    return json.loads(m.group(0))


def run_fast_analyst(
    *,
    llm_provider: str,
    model_name: str,
    base_url: str | None,
    api_key: str | None,
    payload: dict[str, Any],
    kline_features: dict[str, Any],
    timeout_sec: float = 55.0,
) -> dict[str, Any]:
    fallback = {
        "verdict": {
            "direction": "neutral",
            "confidence": 2,
            "horizon": "same_day",
            "reason": "数据不足或模型超时，建议以观望为主并等待更多确认信号。",
            "key_drivers": [],
            "risks": ["数据完整性不足"],
        },
        "time_phased_strategy": {},
        "position_recommendation": {},
        "executability_assessment": {},
        "kline_insight": build_fallback_insight(kline_features, str(payload.get("symbol") or ""), level="brief"),
        "alignment": {"with_overnight": "n/a", "with_user_position": "n/a", "with_kline_bias": "aligned"},
        "data_completeness": float(payload.get("data_completeness") or 0.0),
        "disclaimer": "仅供研究参考，不构成投资建议",
    }

    system_prompt = build_fast_system_prompt()
    user_prompt = build_fast_user_prompt(json_safe(payload))

    last_error: str | None = None
    for retry in range(2):
        try:
            client = create_llm_client(
                provider=llm_provider,
                model=model_name,
                base_url=base_url,
                api_key=api_key,
                timeout=timeout_sec,
                max_retries=0,
                max_tokens=3072,
            )
            llm = client.get_llm()
            output = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
            text = output if isinstance(output, str) else getattr(output, "content", str(output))
            parsed = _extract_json(text)
            if "kline_insight" not in parsed or not isinstance(parsed.get("kline_insight"), dict):
                parsed["kline_insight"] = build_fallback_insight(kline_features, str(payload.get("symbol") or ""), level="brief")
            return FastAnalysisResult.model_validate(parsed).model_dump(mode="json")
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("[fast_analyst] LLM output validation failed (retry=%s): %s", retry, last_error)
            if retry == 0:
                user_prompt = user_prompt + "\n请严格输出合法JSON对象，并完整包含所有schema字段。"
                continue
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "[fast_analyst] LLM invoke failed provider=%s model=%s base_url=%s: %s",
                llm_provider,
                model_name,
                base_url,
                last_error,
            )
            break
    if last_error:
        fallback["llm_error"] = last_error
        fallback["verdict"]["reason"] = (
            f"LLM 调用未成功（{last_error}），已返回基于本地特征的中性参考结论。"
        )
    return fallback

