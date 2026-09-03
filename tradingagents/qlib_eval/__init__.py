"""Qlib evaluation sandbox — feature/label schema, baseline experiments, and enablement gates.

Not wired into the default analysis chain. Enable via TA_QLIB_EVAL_ENABLED=1.
"""

from tradingagents.qlib_eval.config import qlib_eval_enabled, qlib_sandbox_enabled, qlib_sweeps_enabled, qlib_bridge_enabled

__all__ = [
    "qlib_eval_enabled",
    "qlib_sandbox_enabled",
    "qlib_sweeps_enabled",
    "qlib_bridge_enabled",
]
