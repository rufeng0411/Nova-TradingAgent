from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from api.database import FastAnalysisDB, ReportDB


def evaluate_daily_fast_analyses(db: Session, trade_date: str) -> dict[str, Any]:
    rows = (
        db.query(FastAnalysisDB)
        .filter(FastAnalysisDB.trade_date == trade_date, FastAnalysisDB.status.in_(("succeeded", "degraded")))
        .all()
    )
    stats = defaultdict(lambda: {"total": 0, "hit": 0})
    for row in rows:
        verdict = dict(row.verdict_json or {})
        direction = str((verdict.get("verdict") or {}).get("direction") or verdict.get("direction") or "neutral")
        if direction not in ("bullish", "bearish"):
            continue
        report = (
            db.query(ReportDB)
            .filter(ReportDB.symbol == row.symbol, ReportDB.trade_date >= trade_date, ReportDB.direction.isnot(None))
            .order_by(ReportDB.trade_date.asc())
            .first()
        )
        stats[direction]["total"] += 1
        if report and ((direction == "bullish" and "多" in str(report.direction)) or (direction == "bearish" and "空" in str(report.direction))):
            stats[direction]["hit"] += 1
    out = {k: {"total": v["total"], "hit_rate": (v["hit"] / v["total"] if v["total"] else 0.0)} for k, v in stats.items()}
    return {
        "trade_date": trade_date,
        "evaluated_at": datetime.utcnow().isoformat(),
        "rows": len(rows),
        "stats": out,
    }

