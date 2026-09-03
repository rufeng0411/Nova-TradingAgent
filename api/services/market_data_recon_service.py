from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session

from api.database import MarketDataReconAnomalyDB


def _now():
    return datetime.now(timezone.utc)


def recon_daily_bar_frames(
    db: Session,
    trade_date: date,
    primary_df: pd.DataFrame,
    secondary_df: pd.DataFrame,
    *,
    source_primary: str,
    source_secondary: str,
    threshold: float = 0.005,
) -> dict[str, int]:
    """Compare daily close/open/high/low/volume between two vendor frames."""
    if primary_df is None:
        primary_df = pd.DataFrame()
    if secondary_df is None:
        secondary_df = pd.DataFrame()

    def _normalize(df: pd.DataFrame, source: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["symbol", "open", "high", "low", "close", "volume", "_source"])
        out = df.copy()
        rename_map = {
            "ts_code": "symbol",
            "code": "symbol",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Date": "trade_date",
        }
        out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
        if "symbol" not in out.columns:
            return pd.DataFrame(columns=["symbol", "open", "high", "low", "close", "volume", "_source"])
        out["symbol"] = out["symbol"].astype(str).str.upper()
        out["_source"] = source
        keep = [c for c in ("symbol", "open", "high", "low", "close", "volume", "_source") if c in out.columns]
        return out[keep]

    left = _normalize(primary_df, source_primary)
    right = _normalize(secondary_df, source_secondary)
    if left.empty or right.empty:
        return {"compared": 0, "anomalies": 0}

    merged = left.merge(right, on="symbol", suffixes=("_p", "_s"))
    if merged.empty:
        return {"compared": 0, "anomalies": 0}

    anomalies = 0
    for _, row in merged.iterrows():
        symbol = row["symbol"]
        for field in ("open", "high", "low", "close", "volume"):
            v1 = pd.to_numeric(row.get(f"{field}_p"), errors="coerce")
            v2 = pd.to_numeric(row.get(f"{field}_s"), errors="coerce")
            if pd.isna(v1) or pd.isna(v2):
                continue
            base = abs(float(v1)) if float(v1) != 0 else 1.0
            diff_ratio = abs(float(v1) - float(v2)) / base
            if diff_ratio <= threshold:
                continue
            severity = "high" if diff_ratio > threshold * 3 else "medium"
            db.add(
                MarketDataReconAnomalyDB(
                    id=uuid4().hex,
                    trade_date=trade_date,
                    symbol=symbol,
                    field=field,
                    value_primary=Decimal(str(float(v1))),
                    value_secondary=Decimal(str(float(v2))),
                    diff_ratio=Decimal(str(diff_ratio)),
                    severity=severity,
                    source_primary=source_primary,
                    source_secondary=source_secondary,
                    details={
                        "threshold": threshold,
                        "checked_at": _now().isoformat(),
                    },
                )
            )
            anomalies += 1
    if anomalies:
        db.commit()
    return {"compared": int(len(merged)), "anomalies": anomalies}
