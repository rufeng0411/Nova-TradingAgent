"""Admin time-series metrics: overview, credits, traffic (+ optional daily rollup)."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from api.database import (
    DATABASE_URL,
    AccessLogDB,
    AdminMetricsDailyDB,
    CreditTransactionDB,
    ReportOutcomeDB,
    SubscriptionDB,
    UserDB,
)

logger = logging.getLogger(__name__)

Granularity = Literal["day", "hour"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_range(
    from_ts: datetime, to_ts: datetime, granularity: Granularity
) -> Tuple[datetime, datetime]:
    if to_ts <= from_ts:
        to_ts = from_ts + timedelta(hours=1)
    max_days = int(os.getenv("TA_ADMIN_METRICS_MAX_DAYS", "30") or "30")
    if granularity == "hour":
        max_span = timedelta(days=min(7, max_days))
    else:
        max_span = timedelta(days=max(1, min(max_days, 90)))
    if to_ts - from_ts > max_span:
        from_ts = to_ts - max_span
    return from_ts, to_ts


def _bucket_sqlite(col_sql: str, granularity: Granularity) -> str:
    if granularity == "day":
        return f"strftime('%Y-%m-%d 00:00:00', {col_sql})"
    return f"strftime('%Y-%m-%d %H:00:00', {col_sql})"


def _bucket_mysql(col_sql: str, granularity: Granularity) -> str:
    if granularity == "day":
        return f"DATE_FORMAT({col_sql}, '%Y-%m-%d 00:00:00')"
    return f"DATE_FORMAT({col_sql}, '%Y-%m-%d %H:00:00')"


def _bucket_pg(col_sql: str, granularity: Granularity) -> str:
    u = "day" if granularity == "day" else "hour"
    return f"date_trunc('{u}', {col_sql} AT TIME ZONE 'UTC')::text"


def _series_from_daily_table(
    db: Session, from_ts: datetime, to_ts: datetime, granularity: Granularity
) -> Optional[List[Dict[str, Any]]]:
    """If rollup rows exist for every UTC day in [from_ts, to_ts], return merged points; else None."""
    if granularity != "day":
        return None
    d0 = from_ts.date()
    d1 = to_ts.date()
    days: List[date] = []
    cur = d0
    while cur <= d1:
        days.append(cur)
        cur += timedelta(days=1)
    if not days:
        return None
    keys = ("overview.day",)
    rows = (
        db.query(AdminMetricsDailyDB)
        .filter(
            AdminMetricsDailyDB.bucket_date.in_([d.isoformat() for d in days]),
            AdminMetricsDailyDB.metric_key.in_(keys),
        )
        .all()
    )
    by_day = {r.bucket_date: json.loads(r.value_json) for r in rows}
    if len(by_day) < len(days) * 0.8:
        return None
    points: List[Dict[str, Any]] = []
    for d in days:
        ds = d.isoformat()
        blob = by_day.get(ds)
        if not blob:
            continue
        ts = f"{ds}T00:00:00+00:00"
        for k, v in blob.items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            points.append({"ts": ts, "key": k, "value": fv})
    return points


def _agg_users(db: Session, from_ts: datetime, to_ts: datetime, granularity: Granularity) -> List[Tuple[str, int]]:
    if DATABASE_URL.startswith("sqlite"):
        b = _bucket_sqlite("created_at", granularity)
        q = text(f"SELECT {b} AS ts, COUNT(*) FROM users WHERE created_at >= :f AND created_at < :t GROUP BY ts")
    elif DATABASE_URL.startswith("mysql"):
        b = _bucket_mysql("created_at", granularity)
        q = text(f"SELECT {b} AS ts, COUNT(*) FROM users WHERE created_at >= :f AND created_at < :t GROUP BY ts")
    else:
        b = _bucket_pg("created_at", granularity)
        q = text(f"SELECT {b} AS ts, COUNT(*)::int FROM users WHERE created_at >= :f AND created_at < :t GROUP BY 1")
    rows = db.execute(q, {"f": from_ts, "t": to_ts}).fetchall()
    return [(str(r[0]), int(r[1] or 0)) for r in rows]


def _agg_access(db: Session, from_ts: datetime, to_ts: datetime, granularity: Granularity) -> List[Tuple[str, int]]:
    if DATABASE_URL.startswith("sqlite"):
        b = _bucket_sqlite("created_at", granularity)
        q = text(f"SELECT {b} AS ts, COUNT(*) FROM access_logs WHERE created_at >= :f AND created_at < :t GROUP BY ts")
    elif DATABASE_URL.startswith("mysql"):
        b = _bucket_mysql("created_at", granularity)
        q = text(f"SELECT {b} AS ts, COUNT(*) FROM access_logs WHERE created_at >= :f AND created_at < :t GROUP BY ts")
    else:
        b = _bucket_pg("created_at", granularity)
        q = text(f"SELECT {b} AS ts, COUNT(*)::int FROM access_logs WHERE created_at >= :f AND created_at < :t GROUP BY 1")
    rows = db.execute(q, {"f": from_ts, "t": to_ts}).fetchall()
    return [(str(r[0]), int(r[1] or 0)) for r in rows]


def _agg_credit_type(
    db: Session, from_ts: datetime, to_ts: datetime, granularity: Granularity, tx_type: str
) -> List[Tuple[str, float]]:
    if DATABASE_URL.startswith("sqlite"):
        b = _bucket_sqlite("created_at", granularity)
        q = text(
            f"SELECT {b} AS ts, SUM(ABS(delta)) FROM credit_transactions "
            "WHERE created_at >= :f AND created_at < :t AND type = :tp GROUP BY ts"
        )
    elif DATABASE_URL.startswith("mysql"):
        b = _bucket_mysql("created_at", granularity)
        q = text(
            f"SELECT {b} AS ts, COALESCE(SUM(ABS(delta)),0) FROM credit_transactions "
            "WHERE created_at >= :f AND created_at < :t AND type = :tp GROUP BY ts"
        )
    else:
        b = _bucket_pg("created_at", granularity)
        q = text(
            f"SELECT {b} AS ts, COALESCE(SUM(ABS(delta)),0)::float FROM credit_transactions "
            "WHERE created_at >= :f AND created_at < :t AND type = :tp GROUP BY 1"
        )
    rows = db.execute(q, {"f": from_ts, "t": to_ts, "tp": tx_type}).fetchall()
    return [(str(r[0]), float(r[1] or 0)) for r in rows]


def _agg_subscriptions_new(
    db: Session, from_ts: datetime, to_ts: datetime, granularity: Granularity
) -> List[Tuple[str, int]]:
    if DATABASE_URL.startswith("sqlite"):
        b = _bucket_sqlite("created_at", granularity)
        q = text(
            f"SELECT {b} AS ts, COUNT(*) FROM subscriptions WHERE created_at >= :f AND created_at < :t GROUP BY ts"
        )
    elif DATABASE_URL.startswith("mysql"):
        b = _bucket_mysql("created_at", granularity)
        q = text(
            f"SELECT {b} AS ts, COUNT(*) FROM subscriptions WHERE created_at >= :f AND created_at < :t GROUP BY ts"
        )
    else:
        b = _bucket_pg("created_at", granularity)
        q = text(
            f"SELECT {b} AS ts, COUNT(*)::int FROM subscriptions WHERE created_at >= :f AND created_at < :t GROUP BY 1"
        )
    rows = db.execute(q, {"f": from_ts, "t": to_ts}).fetchall()
    return [(str(r[0]), int(r[1] or 0)) for r in rows]


def _normalize_ts(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    if "+" not in s and "Z" not in s and "T" in s:
        return s + "+00:00"
    if " " in s and "T" not in s:
        return s.replace(" ", "T") + "+00:00"
    return s


def metrics_overview(
    db: Session,
    *,
    from_ts: datetime,
    to_ts: datetime,
    granularity: Granularity,
) -> List[Dict[str, Any]]:
    from_ts, to_ts = _clamp_range(from_ts, to_ts, granularity)
    if granularity == "day":
        cached = _series_from_daily_table(db, from_ts, to_ts, granularity)
        if cached is not None and len(cached) > 0:
            return sorted(cached, key=lambda x: x["ts"])
    points: List[Dict[str, Any]] = []
    for ts, v in _agg_users(db, from_ts, to_ts, granularity):
        points.append({"ts": _normalize_ts(ts), "key": "users.new_registrations", "value": float(v)})
    for ts, v in _agg_access(db, from_ts, to_ts, granularity):
        points.append({"ts": _normalize_ts(ts), "key": "access.requests", "value": float(v)})
    for label, tp in (
        ("credits.reserve_volume", "reserve"),
        ("credits.commit_volume", "commit"),
        ("credits.refund_volume", "refund"),
    ):
        for ts, v in _agg_credit_type(db, from_ts, to_ts, granularity, tp):
            points.append({"ts": _normalize_ts(ts), "key": label, "value": float(v)})
    for ts, v in _agg_subscriptions_new(db, from_ts, to_ts, granularity):
        points.append({"ts": _normalize_ts(ts), "key": "subscriptions.new", "value": float(v)})
    return sorted(points, key=lambda x: (x["ts"], x["key"]))


def metrics_credits(
    db: Session,
    *,
    from_ts: datetime,
    to_ts: datetime,
    granularity: Granularity,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    from_ts, to_ts = _clamp_range(from_ts, to_ts, granularity)
    points: List[Dict[str, Any]] = []
    for label, tp in (
        ("credits.reserve_volume", "reserve"),
        ("credits.commit_volume", "commit"),
        ("credits.refund_volume", "refund"),
    ):
        if DATABASE_URL.startswith("sqlite"):
            b = _bucket_sqlite("created_at", granularity)
            base = (
                f"SELECT {b} AS ts, SUM(ABS(delta)) FROM credit_transactions "
                "WHERE created_at >= :f AND created_at < :t AND type = :tp"
            )
            if user_id:
                base += " AND user_id = :uid"
            base += " GROUP BY ts"
            q = text(base)
        elif DATABASE_URL.startswith("mysql"):
            b = _bucket_mysql("created_at", granularity)
            base = (
                f"SELECT {b} AS ts, COALESCE(SUM(ABS(delta)),0) FROM credit_transactions "
                "WHERE created_at >= :f AND created_at < :t AND type = :tp"
            )
            if user_id:
                base += " AND user_id = :uid"
            base += " GROUP BY ts"
            q = text(base)
        else:
            b = _bucket_pg("created_at", granularity)
            base = (
                f"SELECT {b} AS ts, COALESCE(SUM(ABS(delta)),0)::float FROM credit_transactions "
                "WHERE created_at >= :f AND created_at < :t AND type = :tp"
            )
            if user_id:
                base += " AND user_id = :uid"
            base += " GROUP BY 1"
            q = text(base)
        params: Dict[str, Any] = {"f": from_ts, "t": to_ts, "tp": tp}
        if user_id:
            params["uid"] = user_id
        for ts, v in db.execute(q, params).fetchall():
            points.append({"ts": _normalize_ts(str(ts)), "key": label, "value": float(v or 0)})
    return sorted(points, key=lambda x: (x["ts"], x["key"]))


def metrics_traffic(
    db: Session,
    *,
    from_ts: datetime,
    to_ts: datetime,
    granularity: Granularity,
    path_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Path/status aggregates + approximate P95 latency per bucket (SQLite percentile via raw query)."""
    from_ts, to_ts = _clamp_range(from_ts, to_ts, granularity)
    if DATABASE_URL.startswith("sqlite"):
        b = _bucket_sqlite("created_at", granularity)
        filt = "created_at >= :f AND created_at < :t AND latency_ms IS NOT NULL"
        params: Dict[str, Any] = {"f": from_ts, "t": to_ts}
        if path_prefix:
            filt += " AND path LIKE :pf"
            params["pf"] = f"{path_prefix}%"
        q_counts = text(
            f"SELECT {b} AS ts, path, status_code, COUNT(*) AS c FROM access_logs WHERE {filt} "
            "GROUP BY ts, path, status_code ORDER BY ts ASC"
        )
        q_p95 = text(
            f"""
            SELECT bucket_ts, latency_ms FROM (
              SELECT {b} AS bucket_ts, latency_ms,
                ROW_NUMBER() OVER (PARTITION BY {b} ORDER BY latency_ms ASC) AS rn,
                COUNT(*) OVER (PARTITION BY {b}) AS cnt
              FROM access_logs
              WHERE {filt}
            ) x
            WHERE rn = CASE WHEN (x.cnt * 95 + 99) / 100 < 1 THEN 1 ELSE (x.cnt * 95 + 99) / 100 END
            """
        )
    elif DATABASE_URL.startswith("mysql"):
        b = _bucket_mysql("created_at", granularity)
        filt = "created_at >= :f AND created_at < :t AND latency_ms IS NOT NULL"
        params: Dict[str, Any] = {"f": from_ts, "t": to_ts}
        if path_prefix:
            filt += " AND path LIKE :pf"
            params["pf"] = f"{path_prefix}%"
        q_counts = text(
            f"SELECT {b} AS ts, path, status_code, COUNT(*) AS c FROM access_logs WHERE {filt} "
            "GROUP BY ts, path, status_code ORDER BY ts ASC"
        )
        q_p95 = text(
            f"""
            SELECT bucket_ts, latency_ms FROM (
              SELECT {b} AS bucket_ts, latency_ms,
                ROW_NUMBER() OVER (PARTITION BY {b} ORDER BY latency_ms ASC) AS rn,
                COUNT(*) OVER (PARTITION BY {b}) AS cnt
              FROM access_logs
              WHERE {filt}
            ) x
            WHERE rn = CASE WHEN (x.cnt * 95 + 99) / 100 < 1 THEN 1 ELSE (x.cnt * 95 + 99) / 100 END
            """
        )
    else:
        b = _bucket_pg("created_at", granularity)
        filt = "created_at >= :f AND created_at < :t AND latency_ms IS NOT NULL"
        params = {"f": from_ts, "t": to_ts}
        if path_prefix:
            filt += " AND path LIKE :pf"
            params["pf"] = f"{path_prefix}%"
        q_counts = text(
            f"SELECT {b} AS ts, path, status_code, COUNT(*)::int AS c FROM access_logs WHERE {filt} "
            "GROUP BY 1, path, status_code ORDER BY 1 ASC"
        )
        q_p95 = text(
            f"""
            SELECT bucket_ts, PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)
            FROM (
              SELECT {b} AS bucket_ts, latency_ms FROM access_logs WHERE {filt}
            ) s
            GROUP BY bucket_ts
            """
        )
    series_points: List[Dict[str, Any]] = []
    for row in db.execute(q_counts, params).fetchall():
        ts, path, sc, c = row[0], row[1], row[2], int(row[3] or 0)
        series_points.append(
            {
                "ts": _normalize_ts(str(ts)),
                "key": f"traffic.{path or ''}.{sc}",
                "value": float(c),
            }
        )
    p95_points: List[Dict[str, Any]] = []
    try:
        for row in db.execute(q_p95, params).fetchall():
            p95_points.append(
                {"ts": _normalize_ts(str(row[0])), "key": "traffic.latency_p95_ms", "value": float(row[1] or 0)}
            )
    except Exception as e:
        logger.debug("p95 query skipped: %s", e)
    return {"counts": sorted(series_points, key=lambda x: (x["ts"], x["key"])), "p95": sorted(p95_points, key=lambda x: x["ts"])}


def rollup_utc_day(db: Session, day: date) -> None:
    """Recompute daily rollup JSON for `day` (UTC) into admin_metrics_daily."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    blob: Dict[str, float] = {}
    u = _agg_users(db, start, end, "day")
    blob["users.new_registrations"] = float(u[0][1]) if u else 0.0
    a = _agg_access(db, start, end, "day")
    blob["access.requests"] = float(a[0][1]) if a else 0.0
    for tp, key in (("reserve", "credits.reserve_volume"), ("commit", "credits.commit_volume"), ("refund", "credits.refund_volume")):
        rows = _agg_credit_type(db, start, end, "day", tp)
        blob[key] = float(rows[0][1]) if rows else 0.0
    s = _agg_subscriptions_new(db, start, end, "day")
    blob["subscriptions.new"] = float(s[0][1]) if s else 0.0
    active = (
        db.query(func.count(SubscriptionDB.id))
        .filter(SubscriptionDB.status == "active", SubscriptionDB.created_at < end)
        .scalar()
        or 0
    )
    blob["subscriptions.active_snapshot"] = float(active)
    ds = day.isoformat()
    metric_key = "overview.day"
    payload = json.dumps(blob, ensure_ascii=False)
    existing = (
        db.query(AdminMetricsDailyDB)
        .filter(AdminMetricsDailyDB.bucket_date == ds, AdminMetricsDailyDB.metric_key == metric_key)
        .first()
    )
    now = _utcnow()
    if existing:
        existing.value_json = payload
        existing.updated_at = now
    else:
        from uuid import uuid4

        db.add(
            AdminMetricsDailyDB(
                id=str(uuid4()),
                bucket_date=ds,
                metric_key=metric_key,
                value_json=payload,
                updated_at=now,
            )
        )
    db.commit()


def rollup_recent_days(db: Session, days: int = 32) -> None:
    today = _utcnow().date()
    for i in range(days):
        rollup_utc_day(db, today - timedelta(days=i))


def get_outcome_trend(db: Session, days: int = 90, group_by: str = "release_version") -> dict[str, Any]:
    """按月聚合报告兑现度，支持按版本分组。"""
    days = max(7, min(int(days or 90), 365))
    since = _utcnow() - timedelta(days=days)
    grp_col = "release_version" if group_by == "release_version" else "all"

    if DATABASE_URL.startswith("sqlite"):
        month_expr = "strftime('%Y-%m', created_at)"
    elif DATABASE_URL.startswith("mysql"):
        month_expr = "DATE_FORMAT(created_at, '%Y-%m')"
    else:
        month_expr = "to_char(created_at, 'YYYY-MM')"

    if grp_col == "release_version":
        sql = text(
            f"""
            SELECT COALESCE(release_version, 'dev') AS grp,
                   {month_expr} AS month,
                   AVG(CASE WHEN weighted_score IS NULL THEN 0 ELSE weighted_score END) AS avg_score,
                   COUNT(*) AS cnt
            FROM report_outcomes
            WHERE created_at >= :since
            GROUP BY grp, month
            ORDER BY month ASC, grp ASC
            """
        )
    else:
        sql = text(
            f"""
            SELECT 'all' AS grp,
                   {month_expr} AS month,
                   AVG(CASE WHEN weighted_score IS NULL THEN 0 ELSE weighted_score END) AS avg_score,
                   COUNT(*) AS cnt
            FROM report_outcomes
            WHERE created_at >= :since
            GROUP BY month
            ORDER BY month ASC
            """
        )

    rows = db.execute(sql, {"since": since}).fetchall()
    items: list[dict[str, Any]] = []
    for grp, month, avg_score, cnt in rows:
        score = float(avg_score or 0.0)
        # weighted_score 既可能是 0~1，也可能是 0~100，做兼容归一。
        if score > 1.0:
            score = score / 100.0
        items.append(
            {
                "release_version": str(grp or "dev"),
                "month": str(month or ""),
                "weighted_hit_rate": round(max(0.0, min(score, 1.0)), 4),
                "count": int(cnt or 0),
            }
        )

    total = (
        db.query(func.count(ReportOutcomeDB.id))
        .filter(ReportOutcomeDB.created_at >= since)
        .scalar()
        or 0
    )
    return {"days": days, "group_by": grp_col, "items": items, "total_reports": int(total)}
