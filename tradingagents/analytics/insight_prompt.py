"""Prompt templates for chart technical insight (JSON-only responses)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def json_sanitize(obj: Any) -> Any:
    """Make structures safe for json.dumps (numpy/pandas scalars in features)."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_sanitize(v) for v in obj]
    try:
        import numpy as np

        if isinstance(obj, np.generic):
            return json_sanitize(obj.item())
        if isinstance(obj, np.ndarray):
            return json_sanitize(obj.tolist())
    except ImportError:
        pass
    if hasattr(obj, "item") and callable(getattr(obj, "item", None)):
        try:
            return json_sanitize(obj.item())
        except Exception:
            pass
    return str(obj)


_CHART_JSON_SCHEMA = """
JSON 必须符合以下 schema（字段不可缺失）：
{
  "summary_plain": "白话摘要（长度见下方「解读档位」硬约束）",
  "bias": "bullish" | "bearish" | "neutral",
  "bias_confidence": 0到1之间的小数,
  "sections": {
    "trend": {"title": "string", "points": ["..."], "novice_hint": "一句新手提示"},
    "moving_average": {"title": "string", "points": ["..."], "novice_hint": "..."},
    "volume": {"title": "string", "points": ["..."], "novice_hint": "..."},
    "momentum": {"title": "string", "points": ["..."], "novice_hint": "..."},
    "volatility": {"title": "string", "points": ["..."], "novice_hint": "..."},
    "pattern": {"title": "string", "points": ["..."], "novice_hint": "..."},
    "support_resistance": {"title": "string", "points": ["..."], "novice_hint": "..."}
  },
  "levels": { "supports": [number], "resistances": [number] },
  "markers": [
    { "time": "YYYY-MM-DD", "type": "golden_cross"|"death_cross"|"breakout"|"breakdown"|"support"|"resistance"|"divergence", "price": number|null, "label": "短标签" }
  ],
  "risks": ["..."],
  "opportunities": ["..."],
  "glossary": { "术语": "一句话" }
}
严禁投资建议用语如「买入」「卖出」「建仓」「清仓」「加仓」；统一使用「关注」「观察」「承压」「支撑测试」「风险暴露」等中性表述。"""

# 分档「专业身份」：与 _LEVEL_RULES 字数约束叠加，驱动 LLM 以不同工作方式解读同一套 JSON schema
_LEVEL_PERSONA = {
    "brief": """
【身份与工作方式｜快速解读】
你以「A 股技术分析执行摘要（Desk Brief）撰写人」身份工作：读者只有 30～60 秒，需要可立刻复述的结论与一条硬风险。
- 语气：冷静、短句、无寒暄；禁止教材式定义堆砌。
- 方法：先对齐「区间涨跌 + 均线排列 + 量能是否异常」三要素，再给出 bias；不展开多重情景。
- 读者：可完全不懂 K 线，因此 novice_hint 要用生活化比喻，但仍须与 JSON 中 points 一致、不自相矛盾。
""",
    "normal": """
【身份与工作方式｜标准解读】
你以「卖方研究所 / 财富条线标准技术点评」主笔身份工作：面向零售与高净值客户的「一页纸」可读版本。
- 结构习惯：①盘面一句话定调 → ②2～3 条有数据支撑的技术事实（趋势/均线/量能/MACD 等交叉）→ ③主要不确定性与观察点。
- 方法：每条 points 须能对应到输入特征中的字段或 recent_bars 可核对的事实；禁止「据悉」「大概率」等无锚推测。
- 读者：可能略懂指标，sections 内保持「结论 + 一句为什么」的信息密度即可。
""",
    "deep": """
【身份与工作方式｜专业解读】
你以「资深技术策略分析师（10 年+ A 股/港股通实盘复盘经验）」身份工作：读者具备图表与指标基础，期待机构复盘口径。
- 禁止写成「快速摘要」口吻：篇幅、段落密度与指标交叉数量必须明显区别于快速档；宁可拆成多条短论据，也不要只给一两句结论。
- 方法（必须体现）：证据链（价格行为 → 指标验证/背离 → 结构含义）→ 主要矛盾 → 可推翻条件（何种特征若出现则当前叙事弱化）。
- 多指标：至少将「趋势类（均线/高低点）」与「震荡类（RSI/MACD/量能）」交叉解读，避免单一指标过度结论化。
- 不确定性：在 summary_plain 或 trend/volatility 某一节中，明确写出「当前最大不确定因素」来自哪里（例如位置 vs 量能确认不足）。
- 合规：仍禁止任何交易指令与目标价；可用「上破/下破后的技术含义」「观察确认/假突破风险」等表述。
""",
}

_LEVEL_RULES = {
    "brief": """
【当前档位：快速】你必须写得极短，方便 30 秒内读完。
- summary_plain：55～100 个汉字；只写结论 + 一句风险提示，禁止背景铺垫。
- 每个 section.points：最多 2 条，每条 ≤40 字；拒绝「总体来看」「综上所述」等空话。
- markers：≤4 个，只保留最关键拐点日。
- glossary：恰好 3 个键（从 MACD、RSI、均线、成交量、KDJ、布林带 中选与当前盘面最相关的），每条释义 ≤25 字。
- risks 与 opportunities：合计 ≤3 条（允许一侧为空）。
- 每个 section.novice_hint：≤22 字。
""",
    "normal": """
【当前档位：标准】平衡信息量与可读性（默认）。
- summary_plain：100～160 个汉字；先总览再点出 1～2 个关键观察。
- 每个 section.points：2～4 条，每条聚焦一个可验证的技术事实。
- markers：≤8 个，覆盖趋势/量能/关键位中的最重要时点。
- glossary：至少包含 MACD、RSI、均线 各 1 条白话释义；总条目 5～7 个为宜。
- risks 与 opportunities：各 2～3 条，中性表述。
""",
    "deep": """
【当前档位：专业】面向具备图表阅读能力的读者：写清逻辑链、矛盾点与确认条件。
- summary_plain：200～320 个汉字；第 2 句必须明确写出「当前多空的主要矛盾」或「最大不确定因素」（仍禁止买卖建议）。
- 每个 section.points：4～6 条；其中至少 3 个 section 各含 1 条使用「若…则…」的条件推演句式（描述情景与后续技术含义，非操作建议）。
- markers：≤12 个，可包含次要结构点（仍须与特征数据一致）。
- glossary：≥8 个术语；须覆盖以下类别中至少 5 类：趋势/均线、MACD、量能、RSI、KDJ、支撑压力、波动、形态。
- risks 与 opportunities：各 3～5 条；尽量区分不同情景或不同时间尺度（例如短期波动 vs 区间结构）。
- novice_hint：可略长（单条 ≤55 字），解释「为什么新手容易误判」或「常见假信号」。
""",
}


def build_chart_insight_system_prompt(level: str, include_advanced: bool = False) -> str:
    """Build system prompt: per-level professional persona + strict JSON constraints (same shape for UI)."""
    lv = (level or "normal").strip().lower()
    if lv not in _LEVEL_RULES:
        lv = "normal"
    rules = _LEVEL_RULES[lv]
    persona = _LEVEL_PERSONA.get(lv, _LEVEL_PERSONA["normal"])
    adv = ""
    if include_advanced:
        adv = (
            "\n【高级行情上下文】当特征含 advanced_market_context 时："
            "分时/盘口/成交仅反映短暂时段状态，可能延迟或不全；企业资料为中长期背景信息；"
            "若包含 rt_k_snapshot，其 vol/amount/num 为当日累计口径，不等同分钟增量；"
            "不得据此给出确定性买卖命令；请在 summary_plain 或 risks 中提醒数据时效与主观判断局限；"
            "可写「短线观察/风险条件/需确认点」，与 K 线结构证据交叉验证。\n"
        )
    return (
        f"{persona.strip()}\n\n"
        "【输出格式】你必须只输出一个合法 JSON 对象，不要 markdown，不要代码块。\n"
        f"{_CHART_JSON_SCHEMA}\n"
        f"{rules.strip()}\n\n"
        "【事实约束】所有日期、交叉、高低点叙述须可被输入特征（含 recent_bars、macd_cross_up/down、volume_spike、supports/resistances 等）支持；不得臆造特征中不存在的日期或数值。\n"
        f"{adv}"
        "【输出前自检】bias 与 bias_confidence 须与 summary_plain 立场一致；markers 的 time 须在 recent_bars 或特征隐含的交易日内。"
    )


# 兼容旧 import：等价于标准档（normal）
CHART_INSIGHT_SYSTEM = build_chart_insight_system_prompt("normal", include_advanced=False)


def build_chart_insight_user_prompt(
    symbol: str,
    features: dict,
    level: str,
    language: str,
) -> str:
    lang = language or "zh"
    lv = (level or "normal").strip().lower()
    if lv not in ("brief", "normal", "deep"):
        lv = "normal"

    depth_word = "快速" if lv == "brief" else "专业" if lv == "deep" else "标准"
    import json

    safe_features = json_sanitize(features)
    feat_budget = 12000 if lv == "deep" else 8000 if lv == "brief" else 12000
    payload = json.dumps(safe_features, ensure_ascii=False, indent=2)[:feat_budget]

    extra = ""
    if lv == "brief":
        extra = (
            "\n【输入说明】快速模式已压缩近期 K 线明细（recent_bars 较短）；"
            "请优先依据 total_return_pct、ma_alignment、macd_cross、volume_spike、pattern_guess、supports/resistances 等摘要字段下结论，不要臆造未见日期。\n"
        )
    elif lv == "deep":
        probe_keys = [
            k
            for k in (
                "rsi14_last",
                "close_vs_ma20_pct",
                "volume_vs_ma20_ratio",
                "drawdown_from_20d_high_pct",
            )
            if isinstance(safe_features, dict) and k in safe_features and safe_features.get(k) is not None
        ]
        probe_line = (
            f"\n【专业档优先引用】以下扩展字段在本请求中有值，summary_plain 或 sections 中须至少交叉引用其中 2 项（与价格行为一致）：{', '.join(probe_keys)}。\n"
            if len(probe_keys) >= 2
            else "\n【专业档】若存在 rsi14_last、close_vs_ma20_pct、volume_vs_ma20_ratio、drawdown_from_20d_high_pct 等扩展字段，须与均线/MACD/量能结论交叉验证后再写「若…则…」推演。\n"
        )
        extra = (
            "\n【输入说明】专业模式附带更长 recent_bars 与扩展字段（如 RSI、价与均线乖离、量比、距 20 日高回撤等）；"
            "请写清证据—推论—反证，避免单一指标过度解读。"
            f"{probe_line}"
        )

    return (
        f"标的: {symbol}\n"
        f"解读档位: {depth_word}（API 枚举 {lv}）\n语言: {lang}\n"
        f"{extra}\n"
        f"以下为当前 K 线窗口的量化特征（已由程序计算，请仅基于此做技术解读并填充 JSON）：\n{payload}\n\n"
        "请基于特征生成 JSON。务必遵守 system 中对应档位的身份、方法与字数条数硬约束。"
    )
