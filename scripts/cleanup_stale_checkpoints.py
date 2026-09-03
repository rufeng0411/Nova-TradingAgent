"""Clean stale LangGraph checkpoint rows."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _sqlite_path() -> Path:
    p = os.getenv("LANGGRAPH_CHECKPOINT_SQLITE")
    if p:
        return Path(p)
    return Path("tradingagents/data/langgraph_checkpoints.sqlite")


def delete_checkpoint_for_thread(thread_id: str) -> None:
    path = _sqlite_path()
    if not path.exists():
        return
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        conn.commit()
    finally:
        conn.close()


def cleanup_stale(days: int = 7) -> int:
    path = _sqlite_path()
    if not path.exists():
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints WHERE checkpoint_id < ?",
            (cutoff,),
        )
        ids = [r[0] for r in cur.fetchall()]
        for tid in ids:
            delete_checkpoint_for_thread(tid)
        return len(ids)
    except Exception:
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    n = cleanup_stale()
    print(f"cleaned {n} stale checkpoint threads")
