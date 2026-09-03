from __future__ import annotations

import json
from typing import Any


FAST_ANALYSIS_JSON_SCHEMA = {
    "verdict": {
        "direction": "bullish|bearish|neutral",
        "confidence": "1-5",
        "horizon": "next_2h|half_day|same_day|next_day",
        "reason": "string",
        "key_drivers": ["string"],
        "risks": ["string"],
    },
    "time_phased_strategy": {
        "morning_10_to_11_30": {
            "action": "wait_observe|enter_partial|enter_full|reduce_partial|exit_all|hold",
            "trigger_condition": "string",
            "key_levels": {"support": 0, "resistance": 0},
            "size_pct": 0.0,
        },
        "afternoon_13_to_14_30": {},
        "closing_14_30_to_15_00": {},
    },
    "position_recommendation": {
        # wait_observe：明确表达「本次不入场，等待企稳/破位等信号」；选用此枚举时
        # entry_zone / exit_zone / stop_loss / take_profit_tiers 可统一返回空数组或 0，
        # 不要用伪造价位塞入区间，避免前端把 [0, 0] 当成有效价位渲染。
        "scenario": "new_entry|add_to_existing|reduce_existing|exit_existing|hold_existing|wait_observe",
        "target_position_pct": 0.0,
        "entry_zone": [0, 0],
        "exit_zone": [0, 0],
        "stop_loss": 0.0,
        "take_profit_tiers": [{"price": 0.0, "size_pct": 0.0}],
        "sizing_rationale": "string",
    },
    "executability_assessment": {
        "liquidity_score": 1,
        "estimated_slippage_pct": 0.0,
        "max_advisable_position_pct": 0.0,
        "split_orders_recommended": True,
        "execution_window_minutes": 0,
        "warnings": ["string"],
    },
    "kline_insight": {},
    "alignment": {
        "with_overnight": "aligned|divergent|n/a",
        "with_user_position": "consistent|conflicting|n/a",
        "with_kline_bias": "aligned|divergent",
    },
    "data_completeness": 0.0,
    "disclaimer": "仅供研究参考，不构成投资建议",
}


def build_fast_system_prompt() -> str:
    return (
        "你是资深A股短线量化研究员。任务是给出2小时到1个交易日的研究级决策辅助。\n"
        "必须严格遵守：\n"
        "1) 仅输出一个 JSON 对象，不要 markdown。\n"
        "2) 禁止给出明确交易指令措辞（例如 立刻买入/全仓/加杠杆）。\n"
        "3) 必须在 verdict.reason 与 morning_10_to_11_30 中引用 auction_* 特征（若 unavailable 则明确说明无开盘锚点）。\n"
        "4) 识别并点名开盘模式：高开高走/高开低走/低开高走/低开低走/平开震荡。\n"
        "5) 输出包含免责声明：仅供研究参考，不构成投资建议。\n"
        "6) position_recommendation：若判断为「本次不入场 / 等待企稳或破位」，必须用 scenario=\"wait_observe\"，"
        "并把 entry_zone/exit_zone/take_profit_tiers 留空（或 0）、target_position_pct=0；"
        "禁止用 new_entry + 全 0 的价位假装给了建议。\n"
        "7) kline_insight.supports / resistances 必须使用「当日 + 近 5 日」盘中坐标系（不要直接照搬 60 日历史聚类价位）；"
        "如需引用 60 日中长期密集区，请放入 supports_60d / resistances_60d。\n"
    )


def build_fast_user_prompt(payload: dict[str, Any]) -> str:
    schema = json.dumps(FAST_ANALYSIS_JSON_SCHEMA, ensure_ascii=False, indent=2)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "请根据以下输入生成 JSON：\n"
        f"{body}\n\n"
        "输出 JSON schema（字段必须齐全）：\n"
        f"{schema}\n"
    )

