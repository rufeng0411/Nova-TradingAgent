"""Export feature/label panels for Qlib sandbox experiments."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from api.database import ReportDB
from tradingagents.qlib_eval.adapters.derived_bridge import from_result_data
from tradingagents.qlib_eval.adapters.marketdata_loader import load_daily_bars, load_marketdata_row
from tradingagents.qlib_eval.config import qlib_data_dir
from tradingagents.qlib_eval.schema import (
    FULL_LABEL_HORIZONS,
    compute_forward_return_labels,
    merge_feature_label_rows,
)


def _report_trade_date(report: ReportDB) -> str:
    td = str(getattr(report, "trade_date", "") or "").strip()
    if td:
        return td[:10]
    ca = getattr(report, "created_at", None)
    if ca:
        return ca.strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_panel_from_reports(
    db: Session,
    mdb: Session,
    *,
    user_id: str | None = None,
    since_days: int = 90,
    limit: int = 500,
) -> pd.DataFrame:
    q = db.query(ReportDB).filter(ReportDB.status == "completed")
    if user_id:
        q = q.filter(ReportDB.user_id == str(user_id))
    if since_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(since_days))
        q = q.filter(ReportDB.created_at >= cutoff)
    reports = q.order_by(ReportDB.created_at.desc()).limit(max(1, int(limit))).all()

    rows: list[dict[str, Any]] = []
    for r in reports:
        sym = str(r.symbol or "").strip()
        td = _report_trade_date(r)
        if not sym:
            continue
        result_data = dict(r.result_data or {}) if isinstance(r.result_data, dict) else {}
        md_row = load_marketdata_row(mdb, symbol=sym, trade_date=td)
        feature = from_result_data(symbol=sym, trade_date=td, result_data=result_data, marketdata_row=md_row)

        start = (datetime.strptime(td, "%Y-%m-%d") - timedelta(days=120)).strftime("%Y-%m-%d")
        end = (datetime.strptime(td, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
        bar_list = load_daily_bars(mdb, symbol=sym, start_date=start, end_date=end)
        bars = pd.DataFrame(bar_list)
        label = compute_forward_return_labels(bars, symbol=sym, trade_date=td, horizons=FULL_LABEL_HORIZONS)
        row = merge_feature_label_rows(feature, label)
        row["report_id"] = str(r.id)
        row["release_version"] = str(getattr(r, "release_version", "") or "dev")
        row["direction"] = str(getattr(r, "direction", "") or "")
        rows.append(row)
    return pd.DataFrame(rows)


def export_panel(
    panel: pd.DataFrame,
    *,
    out_dir: Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    base = out_dir or qlib_data_dir()
    base.mkdir(parents=True, exist_ok=True)
    rid = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_path = base / rid
    run_path.mkdir(parents=True, exist_ok=True)

    csv_path = run_path / "feature_label_panel.csv"
    parquet_path = run_path / "feature_label_panel.parquet"
    meta_path = run_path / "manifest.json"

    panel.to_csv(csv_path, index=False, encoding="utf-8-sig")
    try:
        panel.to_parquet(parquet_path, index=False)
        parquet_ok = True
    except Exception:
        parquet_ok = False

    manifest = {
        "run_id": rid,
        "rows": int(len(panel)),
        "columns": list(panel.columns),
        "csv": str(csv_path),
        "parquet": str(parquet_path) if parquet_ok else None,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
