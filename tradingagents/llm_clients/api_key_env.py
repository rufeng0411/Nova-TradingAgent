"""Persist missing API keys to .env for CLI interactive flows only."""

from __future__ import annotations

import os
from pathlib import Path


def persist_api_key_to_env(env_var: str, value: str, env_path: str | None = None) -> None:
    """Append or update a single key in project .env (CLI use only)."""
    if not value or not env_var:
        return
    path = Path(env_path or ".env")
    lines: list[str] = []
    found = False
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{env_var}="):
                lines[i] = f"{env_var}={value}"
                found = True
                break
    if not found:
        lines.append(f"{env_var}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def require_env_key(env_var: str, provider: str, *, region: str | None = None) -> str:
    value = (os.getenv(env_var) or "").strip()
    if value:
        return value
    region_hint = f" (region='{region}')" if region else ""
    raise ValueError(
        f"{env_var} is required for provider '{provider}'{region_hint}. Set it in .env."
    )
