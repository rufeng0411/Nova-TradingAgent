"""Feature flags and paths for Qlib evaluation sandbox."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def _flag(name: str, default: str = "0") -> bool:
    raw = (os.getenv(name) or default).strip().lower()
    return raw in ("1", "true", "yes", "on")


def qlib_eval_enabled() -> bool:
    """Master gate for quant evaluation APIs and persistence."""
    return _flag("TA_QLIB_EVAL_ENABLED", "0")


def qlib_sandbox_enabled() -> bool:
    """Allow Qlib dataset export and LightGBM baseline runs."""
    return qlib_eval_enabled() and _flag("TA_QLIB_SANDBOX_ENABLED", "0")


def qlib_sweeps_enabled() -> bool:
    """Allow short-horizon rule parameter sweeps."""
    return qlib_eval_enabled() and _flag("TA_QLIB_SWEEPS_ENABLED", "0")


def qlib_data_dir() -> Path:
    raw = (os.getenv("TA_QLIB_DATA_DIR") or "data/qlib_sandbox").strip()
    return Path(raw)


def bridge_root() -> Path:
    raw = (os.getenv("TA_QLIB_BRIDGE_DIR") or "data/qlib_bridge").strip()
    return Path(raw)


def qlib_bridge_enabled() -> bool:
    """Async file-queue bridge to QLIB/ worker (no in-process qlib import)."""
    return qlib_eval_enabled() and _flag("TA_QLIB_BRIDGE_ENABLED", "0")


def release_version() -> str:
    return str(os.getenv("TA_RELEASE_VERSION") or "dev").strip() or "dev"


def gate_min_hit_rate_pct() -> float:
    try:
        return float(os.getenv("TA_QLIB_GATE_MIN_HIT_RATE", "55") or "55")
    except ValueError:
        return 55.0


def gate_min_ic() -> float:
    try:
        return float(os.getenv("TA_QLIB_GATE_MIN_IC", "0.02") or "0.02")
    except ValueError:
        return 0.02


def gate_min_coverage_pct() -> float:
    try:
        return float(os.getenv("TA_QLIB_GATE_MIN_COVERAGE", "30") or "30")
    except ValueError:
        return 30.0


def qlib_data_uri() -> Path:
    raw = (os.getenv("TA_QLIB_DATA_URI") or "data/qlib_cn_data").strip()
    return Path(raw)


def qlib_validation_start() -> str:
    return (os.getenv("TA_QLIB_VALIDATION_START") or "2023-01-01").strip()


def qlib_validation_test_start() -> str:
    return (os.getenv("TA_QLIB_VALIDATION_TEST_START") or "2025-01-01").strip()


def qlib_universe() -> str:
    return (os.getenv("TA_QLIB_UNIVERSE") or "sample").strip().lower()


def qlib_exports_universe_dir() -> Path:
    return Path(os.getenv("TA_QLIB_EXPORTS_UNIVERSE_DIR") or "data/qlib_exports/universe")


def csi300_index_code() -> str:
    return (os.getenv("TA_QLIB_CSI300_INDEX") or "000300.SH").strip().upper()


def backfill_checkpoint_path() -> Path:
    return qlib_validation_log_dir() / "backfill_checkpoint.json"


def qlib_validation_end() -> str:
    return (os.getenv("TA_QLIB_VALIDATION_END") or datetime.now().strftime("%Y-%m-%d")).strip()


def qlib_validation_recent_start() -> str:
    return (os.getenv("TA_QLIB_VALIDATION_RECENT_START") or "2026-01-01").strip()


def qlib_exports_csv_dir() -> Path:
    return Path(os.getenv("TA_QLIB_EXPORTS_CSV_DIR") or "data/qlib_exports/csv")


def qlib_validation_log_dir() -> Path:
    return Path(os.getenv("TA_QLIB_VALIDATION_LOG_DIR") or "logs/qlib_validation")
