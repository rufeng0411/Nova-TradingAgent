"""Build quant_signal context for multi-agent comparison."""

from __future__ import annotations

from typing import Any


def build_quant_signal_context(
    *,
    metrics: dict[str, Any] | None,
    model_card: dict[str, Any] | None,
    summary_md: str | None,
    report_direction: str | None = None,
) -> dict[str, Any]:
    """Structured payload for agent injection (no raw tables)."""
    m = dict(metrics or {})
    card = dict(model_card or {})

    score = m.get("mean_prediction") or m.get("score")
    ic = m.get("ic") or m.get("rank_ic")
    hit = m.get("hit_rate_pct")
    cov = m.get("coverage_pct")

    direction = _score_to_direction(score)
    if report_direction:
        llm_dir = _normalize_direction(report_direction)
    else:
        llm_dir = None

    warnings: list[str] = []
    if cov is not None and float(cov) < 30:
        warnings.append("特征覆盖率偏低，量化信号仅供参考")
    if m.get("test_samples") is not None and int(m.get("test_samples") or 0) < 20:
        warnings.append("验证样本不足，模型稳定性未确认")
    if ic is not None and abs(float(ic)) < 0.02:
        warnings.append("IC 较弱，因子预测力有限")

    top_features = []
    imp = card.get("feature_importance") or card.get("linear_weights") or {}
    if isinstance(imp, dict):
        top_features = [
            {"name": k, "weight": v}
            for k, v in sorted(imp.items(), key=lambda x: abs(float(x[1] or 0)), reverse=True)[:5]
        ]

    ctx = {
        "quant_signal": {
            "direction": direction,
            "score": score,
            "evidence": {
                "ic": ic,
                "rank_ic": m.get("rank_ic"),
                "hit_rate_pct": hit,
                "coverage_pct": cov,
                "top_features": top_features,
                "model_backend": card.get("backend"),
                "label_horizon": card.get("label_horizon"),
            },
            "warnings": warnings,
            "summary_short": _first_paragraph(summary_md),
        },
        "comparison": {
            "llm_direction": llm_dir,
            "quant_direction": direction,
            "aligned": llm_dir is not None and direction is not None and llm_dir == direction,
        },
    }
    return ctx


def format_agent_prompt_block(context: dict[str, Any]) -> str:
    """Human-readable block for prompt injection."""
    qs = dict(context.get("quant_signal") or {})
    cmp = dict(context.get("comparison") or {})
    ev = dict(qs.get("evidence") or {})
    lines = [
        "## 量化引擎摘要（Qlib/LightGBM 沙盒，非 LLM 推导）",
        f"- 量化方向：{_dir_label(qs.get('direction'))}",
        f"- 模型分数：{qs.get('score') if qs.get('score') is not None else '—'}",
        f"- IC / RankIC：{ev.get('ic')} / {ev.get('rank_ic')}",
        f"- 回测命中率：{ev.get('hit_rate_pct')}%（覆盖率 {ev.get('coverage_pct')}%）",
    ]
    if ev.get("top_features"):
        feats = ", ".join(f"{x['name']}({x['weight']:.3f})" for x in ev["top_features"][:3] if x.get("name"))
        lines.append(f"- 主要特征：{feats}")
    if qs.get("warnings"):
        lines.append(f"- 风险提示：{'；'.join(qs['warnings'])}")
    if cmp.get("llm_direction"):
        lines.append(
            f"- 与当前 LLM 方向对照：LLM={_dir_label(cmp.get('llm_direction'))}，"
            f"量化={_dir_label(cmp.get('quant_direction'))}，"
            f"{'一致' if cmp.get('aligned') else '不一致'}"
        )
    if qs.get("summary_short"):
        lines.append(f"- 摘要：{qs['summary_short']}")
    return "\n".join(lines)


def _score_to_direction(score: Any) -> str | None:
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s > 0.002:
        return "bull"
    if s < -0.002:
        return "bear"
    return "neutral"


def _normalize_direction(raw: str | None) -> str | None:
    s = str(raw or "").strip().lower()
    if any(k in s for k in ("看多", "偏多", "bull", "buy")):
        return "bull"
    if any(k in s for k in ("看空", "偏空", "bear", "sell")):
        return "bear"
    return "neutral"


def _dir_label(d: str | None) -> str:
    return {"bull": "偏多", "bear": "偏空", "neutral": "中性"}.get(str(d or ""), "未知")


def _first_paragraph(md: str | None) -> str:
    if not md:
        return ""
    for line in md.splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            return t[:400]
    return md.strip()[:400]
