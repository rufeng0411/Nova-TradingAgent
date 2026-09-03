"""Trading memory log — DB primary + markdown export."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from tradingagents.dataflows.config import get_config


class TradingMemoryLog:
    """Markdown export snapshot."""

    def __init__(self, path: str | None = None):
        cfg = get_config()
        self.path = Path(path or cfg.get("memory_log_path") or "~/.tradingagents/memory/trading_memory.md")
        self.path = self.path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_entry(self, entry: dict[str, Any]) -> None:
        line = (
            f"\n## {entry.get('trade_date')} {entry.get('ticker')} "
            f"[{entry.get('rating_5tier') or 'Hold'}]\n"
            f"{entry.get('decision_md') or ''}\n"
        )
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)


class DBTradingMemoryLog:
    """SQLAlchemy-backed memory log."""

    def __init__(self, db_session_factory):
        self._session_factory = db_session_factory

    def append_entry(self, user_id: str, entry: dict[str, Any]) -> str:
        from api.database import TradingMemoryLogDB

        row_id = str(uuid.uuid4())
        with self._session_factory() as db:
            row = TradingMemoryLogDB(
                id=row_id,
                user_id=str(user_id),
                ticker=entry.get("ticker", ""),
                trade_date=entry.get("trade_date", ""),
                rating_5tier=entry.get("rating_5tier"),
                decision_md=(entry.get("decision_md") or "")[:1500],
                reflection_md=entry.get("reflection_md"),
                outcome_raw_pct=entry.get("outcome_raw_pct"),
                outcome_alpha_pct=entry.get("outcome_alpha_pct"),
                holding_days=entry.get("holding_days"),
                status=entry.get("status", "pending"),
                benchmark_ticker=entry.get("benchmark_ticker"),
            )
            db.add(row)
            db.commit()
        return row_id

    def list_for_ticker(self, user_id: str, ticker: str, limit: int = 5) -> list[dict]:
        from api.database import TradingMemoryLogDB

        with self._session_factory() as db:
            ids = (
                db.query(TradingMemoryLogDB.id)
                .filter(
                    TradingMemoryLogDB.user_id == str(user_id),
                    TradingMemoryLogDB.ticker == ticker,
                )
                .order_by(TradingMemoryLogDB.trade_date.desc())
                .limit(limit)
                .all()
            )
            if not ids:
                return []
            id_list = [i[0] for i in ids]
            rows = db.query(TradingMemoryLogDB).filter(TradingMemoryLogDB.id.in_(id_list)).all()
            return [
                {
                    "rating_5tier": r.rating_5tier,
                    "decision_md": r.decision_md,
                    "outcome_raw_pct": r.outcome_raw_pct,
                    "outcome_alpha_pct": r.outcome_alpha_pct,
                    "holding_days": r.holding_days,
                    "reflection_md": r.reflection_md,
                    "trade_date": r.trade_date,
                }
                for r in rows
            ]


def memory_log_enabled(config: dict | None = None) -> bool:
    if config and config.get("upgrade_persistent_memory"):
        return True
    return os.getenv("TA_UPGRADE_PERSISTENT_MEMORY", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
