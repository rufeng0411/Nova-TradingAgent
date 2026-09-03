"""Grounded sentiment analyst — pre-fetch + single LLM call."""

from __future__ import annotations

import warnings

from langchain_core.messages import HumanMessage, SystemMessage
from tradingagents.dataflows.config import get_config
from tradingagents.prompts import get_prompt
from tradingagents.agents.utils.agent_states import current_tracker_var, extract_verdict


def create_sentiment_analyst(llm, data_collector=None):
    async def sentiment_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        config = get_config()

        pool = data_collector.get(ticker, current_date) if data_collector else None
        sentiment_block = "无 grounded 情绪数据"
        if pool is not None:
            sd = pool.get("sentiment_data") or {}
            parts = []
            for key in ("xueqiu_hot", "guba_posts", "tushare_news"):
                item = sd.get(key)
                if item:
                    parts.append(f"### {key}\n{item}")
            if parts:
                sentiment_block = "\n\n".join(parts)

        system_message = get_prompt("social_system_message", config=config)
        user_content = (
            f"标的：{ticker}\n日期：{current_date}\n\n"
            f"以下为已采集的 grounded 情绪数据（勿重复拉取）：\n{sentiment_block}"
        )
        messages = [SystemMessage(content=system_message), HumanMessage(content=user_content)]

        tracker = current_tracker_var.get()
        full_content = ""
        async for chunk in llm.astream(messages):
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_content += content
            if tracker:
                tracker._emit_token("Sentiment Analyst", "sentiment_report", content)

        verdict = extract_verdict(full_content)
        return {
            "sentiment_report": full_content,
            "messages": messages + [HumanMessage(content=full_content)],
            **({"sentiment_verdict": verdict} if verdict else {}),
        }

    return sentiment_analyst_node


def create_social_media_analyst_shim(llm, data_collector=None):
    warnings.warn(
        "create_social_media_analyst is deprecated; use create_sentiment_analyst",
        DeprecationWarning,
        stacklevel=2,
    )
    from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst

    return create_social_media_analyst(llm, data_collector=data_collector)
