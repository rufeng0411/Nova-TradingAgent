"""Checkpoint status API for upgrade UI."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.database import UserDB, get_db
from api.deps import _require_api_user

router = APIRouter(prefix="/v1/jobs", tags=["jobs-checkpoint"])


class CheckpointStatus(BaseModel):
    step: Optional[int] = None
    resumable: bool = False
    last_node: Optional[str] = None
    thread_id: Optional[str] = None


def _checkpoint_ui_enabled() -> bool:
    return os.getenv("TA_UPGRADE_CHECKPOINT_UI", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@router.get("/{job_id}/checkpoint", response_model=CheckpointStatus)
async def get_job_checkpoint(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(_require_api_user),
):
    if not _checkpoint_ui_enabled():
        return CheckpointStatus(resumable=False, thread_id=job_id)
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        checkpointer = TradingAgentsGraph._shared_checkpointer
        if checkpointer is None:
            return CheckpointStatus(resumable=False, thread_id=job_id)
        config = {"configurable": {"thread_id": job_id}}
        tup = await checkpointer.aget_tuple(config)
        if tup is None:
            return CheckpointStatus(resumable=False, thread_id=job_id)
        meta = getattr(tup, "metadata", None) or {}
        step = meta.get("step")
        last_node = meta.get("source") or meta.get("writes", {}).get("node")
        return CheckpointStatus(
            step=step,
            resumable=True,
            last_node=str(last_node) if last_node else None,
            thread_id=job_id,
        )
    except Exception:
        return CheckpointStatus(resumable=False, thread_id=job_id)


@router.delete("/{job_id}/checkpoint")
async def delete_job_checkpoint(
    job_id: str,
    current_user: UserDB = Depends(_require_api_user),
):
    if not _checkpoint_ui_enabled():
        return {"ok": True, "skipped": True}
    try:
        from scripts.cleanup_stale_checkpoints import delete_checkpoint_for_thread

        delete_checkpoint_for_thread(job_id)
    except Exception:
        pass
    return {"ok": True}
