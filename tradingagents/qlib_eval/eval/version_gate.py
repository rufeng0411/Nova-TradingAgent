"""Enablement gates: quant metrics must pass before entering default chain."""

from __future__ import annotations

from typing import Any

from tradingagents.qlib_eval.config import gate_min_coverage_pct, gate_min_hit_rate_pct, gate_min_ic


def evaluate_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    hit = metrics.get("hit_rate_pct")
    ic = metrics.get("ic") or metrics.get("rank_ic")
    coverage = metrics.get("coverage_pct")

    checks = {
        "hit_rate": hit is not None and float(hit) >= gate_min_hit_rate_pct(),
        "ic": ic is not None and float(ic) >= gate_min_ic(),
        "coverage": coverage is not None and float(coverage) >= gate_min_coverage_pct(),
    }
    passed = all(checks.values())
    reasons = []
    if not checks["hit_rate"]:
        reasons.append(f"hit_rate<{gate_min_hit_rate_pct():.1f}%")
    if not checks["ic"]:
        reasons.append(f"ic<{gate_min_ic():.3f}")
    if not checks["coverage"]:
        reasons.append(f"coverage<{gate_min_coverage_pct():.1f}%")

    return {
        "passed": passed,
        "checks": checks,
        "thresholds": {
            "min_hit_rate_pct": gate_min_hit_rate_pct(),
            "min_ic": gate_min_ic(),
            "min_coverage_pct": gate_min_coverage_pct(),
        },
        "reasons": reasons,
        "metrics": metrics,
    }


def aggregate_version_gates(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_version: dict[str, list[dict[str, Any]]] = {}
    for row in items:
        ver = str(row.get("release_version") or "dev")
        by_version.setdefault(ver, []).append(row)

    out = []
    for ver, rows in sorted(by_version.items()):
        avg_hit = _mean([r.get("hit_rate_pct") for r in rows])
        avg_ic = _mean([r.get("ic") for r in rows if r.get("ic") is not None] or [r.get("rank_ic") for r in rows])
        avg_cov = _mean([r.get("coverage_pct") for r in rows])
        gate = evaluate_gate({"hit_rate_pct": avg_hit, "ic": avg_ic, "coverage_pct": avg_cov})
        out.append({"release_version": ver, "runs": len(rows), "gate": gate})
    return {"items": out, "any_passed": any(x["gate"]["passed"] for x in out)}


def _mean(values: list[Any]) -> float | None:
    nums = []
    for v in values:
        if v is None:
            continue
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return None
    return sum(nums) / len(nums)
