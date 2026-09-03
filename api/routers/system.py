"""System metadata endpoints."""

from __future__ import annotations

import subprocess

from fastapi import APIRouter

import tradingagents

router = APIRouter(prefix="/v1/system", tags=["system"])


@router.get("/version")
def system_version():
    commit = None
    try:
        commit = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        commit = None
    parts = (tradingagents.__version__ or "").split("+")
    fork = parts[1] if len(parts) > 1 else "ta-cn.1"
    return {
        "upstream": getattr(tradingagents, "__upstream_version__", "0.2.5"),
        "fork": fork,
        "version": tradingagents.__version__,
        "commit": commit,
    }
