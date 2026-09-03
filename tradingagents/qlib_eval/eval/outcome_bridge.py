"""Bridge quant metrics to report outcome semantics."""

from __future__ import annotations

from typing import Any

from api.services import report_outcome_service


def release_version() -> str:
    return report_outcome_service.release_version()


def compare_outcome_hit_rate(summary: dict[str, Any]) -> float | None:
    s = dict(summary.get("summary") or {})
    hr = s.get("hit_rate")
    try:
        return float(hr) if hr is not None else None
    except (TypeError, ValueError):
        return None
