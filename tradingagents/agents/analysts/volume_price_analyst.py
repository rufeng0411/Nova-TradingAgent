from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.dataflows.config import get_config
from tradingagents.prompts import get_prompt
from tradingagents.graph.intent_parser import build_horizon_context
from tradingagents.agents.utils.agent_states import current_tracker_var, extract_verdict
from tradingagents.agents.utils.context_utils import summarize_silent_data


def create_volume_price_analyst(llm, data_collector=None):
    def _trim_table(text: object, max_lines: int = 200) -> str:
        raw = str(text or "无数据")
        lines = raw.splitlines()
        if len(lines) <= max_lines:
            return raw
        return "\n".join(lines[:max_lines]) + "\n...（附录已截断）"

    async def volume_price_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        horizon = "short"
        user_intent = state.get("user_intent") or {}
        focus_areas = user_intent.get("focus_areas", [])
        specific_questions = user_intent.get("specific_questions", [])

        config = get_config()
        horizon_ctx = build_horizon_context(horizon, focus_areas, specific_questions, agent_type="volume_price")
        system_message = get_prompt("volume_price_system_message", config=config)

        if data_collector is not None:
            pool = data_collector.get(ticker, current_date)
            if pool is not None:
                windowed = data_collector.get_window(pool, horizon, current_date)
                vpa_data = windowed.get("vpa_indicators", "无数据")
                stock_data = windowed.get("stock_data", "无数据")
                data_window = windowed.get("_data_window", "14天")
                chips_data = windowed.get("cyq_chips_recent", "无数据")
                factor_data = windowed.get("stk_factor_pro_window", "无数据")
                opening_auction = windowed.get("opening_auction", "无数据")
                opening_auction_signal = windowed.get("opening_auction_signal", "无数据")
                intraday_features = (windowed.get("intraday_features") or {}).get("summary", "无数据")
                orderbook_pressure_signal = windowed.get("orderbook_pressure_signal", "无数据")
                active_buy_proxy = windowed.get("active_buy_proxy", "无数据")
            else:
                vpa_data, stock_data, data_window = "无数据", "无数据", "14天"
                chips_data, factor_data, opening_auction, opening_auction_signal = "无数据", "无数据", "无数据", "无数据"
                intraday_features, orderbook_pressure_signal, active_buy_proxy = "无数据", "无数据", "无数据"
        else:
            vpa_data, stock_data, data_window = "无数据", "无数据", "14天"
            chips_data, factor_data, opening_auction, opening_auction_signal = "无数据", "无数据", "无数据", "无数据"
            intraday_features, orderbook_pressure_signal, active_buy_proxy = "无数据", "无数据", "无数据"
        silent_summary = summarize_silent_data({"cyq_chips": chips_data})

        messages = [
            SystemMessage(content=horizon_ctx + system_message + "\n\n请全程使用中文。"),
            HumanMessage(content=(
                f"以下是 {ticker} 在 {current_date} 的量价分析预计算数据（数据窗口：{data_window}）。\n\n"
                f"{vpa_data}\n\n"
                f"【原始 K 线数据参考】\n{stock_data}\n\n"
                f"【开盘集合竞价】\n{opening_auction}\n\n"
                f"【竞价强弱信号】\n{opening_auction_signal}\n\n"
                f"【盘中派生特征】\n{intraday_features}\n\n"
                f"【盘口压力代理】\n{orderbook_pressure_signal}\n\n"
                f"【主动买入近似】\n{active_buy_proxy}\n\n"
                f"【沉默数据摘要（筹码分布）】\n{silent_summary or '无数据'}\n\n"
                f"【专业因子（stk_factor_pro，附录）】\n{_trim_table(factor_data)}"
            )),
        ]

        tracker = current_tracker_var.get()
        full_content = ""
        async for chunk in llm.astream(messages):
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_content += content
            if tracker:
                tracker._emit_token("Volume Price Analyst", "volume_price_report", content)

        verdict, confidence = extract_verdict(full_content)

        return {
            "volume_price_report": full_content,
            "analyst_traces": [{
                "agent": "volume_price_analyst",
                "horizon": horizon,
                "data_window": data_window,
                "key_finding": f"量价分析结论：{verdict}",
                "verdict": verdict,
                "confidence": confidence,
            }],
        }

    return volume_price_analyst_node
