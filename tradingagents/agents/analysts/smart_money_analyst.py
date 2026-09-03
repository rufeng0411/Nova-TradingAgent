import asyncio

from langchain_core.messages import HumanMessage, SystemMessage
from tradingagents.dataflows.config import get_config
from tradingagents.prompts import get_prompt
from tradingagents.graph.intent_parser import build_horizon_context
from tradingagents.agents.utils.agent_states import current_tracker_var, extract_verdict


def create_smart_money_analyst(llm, data_collector=None):
    def _trim_table(text: object, max_lines: int = 200) -> str:
        raw = str(text or "无数据")
        lines = raw.splitlines()
        if len(lines) <= max_lines:
            return raw
        return "\n".join(lines[:max_lines]) + "\n...（附录已截断）"

    async def _safe(tool, payload):
        try:
            return await asyncio.to_thread(tool.invoke, payload)
        except Exception as exc:
            return f"调用失败：{exc}"

    async def smart_money_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        print(f"[Smart Money Analyst] START {ticker} {current_date}")
        horizon = "short"  # 资金面固定短期视角
        user_intent = state.get("user_intent") or {}
        focus_areas = user_intent.get("focus_areas", [])
        specific_questions = user_intent.get("specific_questions", [])

        config = get_config()
        system_message = get_prompt("smart_money_system_message", config=config) or ""
        horizon_ctx = build_horizon_context(horizon, focus_areas, specific_questions, agent_type="smart_money")

        pool = data_collector.get(ticker, current_date) if data_collector else None

        if pool is not None:
            fund_flow = pool.get("fund_flow_individual", "无数据")
            lhb = pool.get("lhb", "无数据")
            volume = pool.get("indicators", {}).get("vwma", "无数据")
            moneyflow_detail = pool.get("individual_money_flow_detail", "无数据")
            margin_detail = pool.get("margin_detail_window", "无数据")
            hsgt_top10 = pool.get("hsgt_top10_window", "无数据")
            opening_auction = pool.get("opening_auction", "无数据")
            opening_auction_signal = pool.get("opening_auction_signal", "无数据")
            top_list_history = pool.get("top_list_history", "无数据")
            orderbook_pressure_signal = pool.get("orderbook_pressure_signal", "无数据")
            active_buy_proxy = pool.get("active_buy_proxy", "无数据")
            moneyflow_structure = pool.get("moneyflow_structure", "无数据")
        else:
            from tradingagents.agents.utils.agent_utils import (
                get_individual_fund_flow, get_lhb_detail, get_indicators, get_opening_auction,
            )
            
            # Parallelize fallback fetches
            results = await asyncio.gather(
                _safe(get_individual_fund_flow, {"symbol": ticker}),
                _safe(get_lhb_detail, {"symbol": ticker, "date": current_date}),
                _safe(get_indicators, {
                    "symbol": ticker, "indicator": "volume",
                    "curr_date": current_date, "look_back_days": 20,
                }),
                _safe(get_opening_auction, {"symbol": ticker, "date": current_date}),
            )
            fund_flow, lhb, volume, opening_auction = results
            opening_auction_signal = "无数据"
            moneyflow_detail = "无数据"
            margin_detail = "无数据"
            hsgt_top10 = "无数据"
            top_list_history = "无数据"
            orderbook_pressure_signal = "无数据"
            active_buy_proxy = "无数据"
            moneyflow_structure = "无数据"

        messages = [
            SystemMessage(content=(
                system_message
                + "\n\n请严格基于提供的量化数据输出分析，全程使用中文。"
            )),
            HumanMessage(content=(
                horizon_ctx + "\n"
                f"请分析 {ticker} 在 {current_date} 的主力资金行为。\n\n"
                f"【近5日主力资金净流向】\n{fund_flow}\n\n"
                f"【龙虎榜数据】\n{lhb}\n\n"
                f"【成交量指标(vwma)】\n{volume}\n\n"
                f"【开盘集合竞价】\n{opening_auction}\n\n"
                f"【竞价强弱信号】\n{opening_auction_signal}\n\n"
                f"【盘口压力代理】\n{orderbook_pressure_signal}\n\n"
                f"【主动买入近似】\n{active_buy_proxy}\n\n"
                f"【资金流结构化结论】\n{moneyflow_structure}\n\n"
                f"【主力资金流明细（附录）】\n{_trim_table(moneyflow_detail)}\n\n"
                f"【融资融券变化（附录）】\n{_trim_table(margin_detail)}\n\n"
                f"【北向Top10变化（附录）】\n{_trim_table(hsgt_top10)}\n\n"
                f"【龙虎榜历史（附录）】\n{_trim_table(top_list_history)}"
            )),
        ]

        # ── 实现 Token 级流式输出 ──────────────────
        tracker = current_tracker_var.get()
        full_content = ""
        async for chunk in llm.astream(messages):
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_content += content
            if tracker:
                tracker._emit_token("Smart Money Analyst", "smart_money_report", content)

        print(f"[Smart Money Analyst] DONE {ticker}, report length={len(full_content)}")
        verdict, confidence = extract_verdict(full_content)
        return {
            "smart_money_report": full_content,
            "analyst_traces": [{
                "agent": "smart_money_analyst",
                "horizon": horizon,
                "data_window": "近期可用",
                "key_finding": f"主力资金分析结论：{verdict}",
                "verdict": verdict,
                "confidence": confidence,
            }],
        }

    return smart_money_analyst_node
