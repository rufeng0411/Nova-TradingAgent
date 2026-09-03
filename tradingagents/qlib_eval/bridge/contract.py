"""Inbox/outbox file contract for QLIB async bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

BRIDGE_SCHEMA_VERSION = "qlib_bridge_v1"

BridgeStatus = Literal["pending", "processing", "completed", "failed", "imported"]

INBOX_FILES = (
    "manifest.json",
    "feature_label_panel.csv",
    "provenance.json",
    "status.json",
)

OUTBOX_FILES = (
    "metrics.json",
    "model_card.json",
    "summary.md",
    "status.json",
)

OUTBOX_OPTIONAL = ("predictions.csv", "predictions.parquet")


@dataclass
class BridgePaths:
    root: Path
    inbox: Path
    outbox: Path
    processing: Path

    @classmethod
    def from_root(cls, root: Path) -> "BridgePaths":
        return cls(
            root=root,
            inbox=root / "inbox",
            outbox=root / "outbox",
            processing=root / "processing",
        )

    def ensure(self) -> None:
        for p in (self.inbox, self.outbox, self.processing):
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class InboxManifest:
    run_id: str
    schema_version: str = BRIDGE_SCHEMA_VERSION
    release_version: str = "dev"
    label_horizon: str = "t2"
    rows: int = 0
    symbol_count: int = 0
    date_range: dict[str, str | None] = field(default_factory=dict)
    feature_panel_csv: str = "feature_label_panel.csv"
    feature_panel_parquet: str | None = None
    provenance_file: str = "provenance.json"
    created_at: str = ""
    sources: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "release_version": self.release_version,
            "label_horizon": self.label_horizon,
            "rows": self.rows,
            "symbol_count": self.symbol_count,
            "date_range": self.date_range,
            "feature_panel_csv": self.feature_panel_csv,
            "feature_panel_parquet": self.feature_panel_parquet,
            "provenance_file": self.provenance_file,
            "created_at": self.created_at or datetime.now(timezone.utc).isoformat(),
            "sources": self.sources,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InboxManifest":
        return cls(
            run_id=str(data.get("run_id") or ""),
            schema_version=str(data.get("schema_version") or BRIDGE_SCHEMA_VERSION),
            release_version=str(data.get("release_version") or "dev"),
            label_horizon=str(data.get("label_horizon") or "t2"),
            rows=int(data.get("rows") or 0),
            symbol_count=int(data.get("symbol_count") or 0),
            date_range=dict(data.get("date_range") or {}),
            feature_panel_csv=str(data.get("feature_panel_csv") or "feature_label_panel.csv"),
            feature_panel_parquet=data.get("feature_panel_parquet"),
            provenance_file=str(data.get("provenance_file") or "provenance.json"),
            created_at=str(data.get("created_at") or ""),
            sources=dict(data.get("sources") or {}),
        )


def inbox_dir(paths: BridgePaths, run_id: str) -> Path:
    return paths.inbox / run_id


def outbox_dir(paths: BridgePaths, run_id: str) -> Path:
    return paths.outbox / run_id


def processing_dir(paths: BridgePaths, run_id: str) -> Path:
    return paths.processing / run_id


def write_status(path: Path, status: BridgeStatus, **extra: Any) -> None:
    import json

    payload = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat(), **extra}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_status(path: Path) -> dict[str, Any]:
    import json

    if not path.exists():
        return {"status": "pending"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "pending"}
