"""Admin reporting aggregates: overview, trends, ops stats (operational口径)."""

from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from api.database import (
    DATABASE_URL,
    AccessLogDB,
    CreditTransactionDB,
    PlanDB,
    ReportDB,
    SubscriptionDB,
    UserDB,
    UserTokenDB,
)

Grain = Literal["day", "hour"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def clamp_date_range(
    start_date: Optional[str], end_date: Optional[str], *, default_days: int = 14
) -> Tuple[datetime, datetime]:
    """Inclusive date range in UTC: start 00:00, end next-day 00:00 exclusive upper."""
    ed = _parse_date(end_date) or _utcnow().date()
    sd = _parse_date(start_date) or (ed - timedelta(days=default_days - 1))
    if sd > ed:
        sd, ed = ed, sd
    max_days = int(os.getenv("TA_ADMIN_REPORTS_MAX_DAYS", "90") or "90")
    if (ed - sd).days + 1 > max_days:
        sd = ed - timedelta(days=max_days - 1)
    start_ts = datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc)
    end_ts = datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc) + timedelta(days=1)
    return start_ts, end_ts


def _bucket_sqlite(col_sql: str, grain: Grain) -> str:
    if grain == "day":
        return f"strftime('%Y-%m-%d 00:00:00', {col_sql})"
    return f"strftime('%Y-%m-%d %H:00:00', {col_sql})"


def _bucket_mysql(col_sql: str, grain: Grain) -> str:
    if grain == "day":
        return f"DATE_FORMAT({col_sql}, '%Y-%m-%d 00:00:00')"
    return f"DATE_FORMAT({col_sql}, '%Y-%m-%d %H:00:00')"


def _bucket_pg(col_sql: str, grain: Grain) -> str:
    u = "day" if grain == "day" else "hour"
    return f"date_trunc('{u}', {col_sql} AT TIME ZONE 'UTC')::text"


def _norm_ts(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    if "+" not in s and "Z" not in s and "T" in s:
        return s + "+00:00"
    if " " in s and "T" not in s:
        return s.replace(" ", "T") + "+00:00"
    return s


def overview(
    db: Session, *, start_date: Optional[str], end_date: Optional[str], grain: Grain = "day"
) -> Dict[str, Any]:
    f, t = clamp_date_range(start_date, end_date)
    new_users = int(db.query(func.count(UserDB.id)).filter(UserDB.created_at >= f, UserDB.created_at < t).scalar() or 0)
    active_users_q = (
        db.query(func.count(func.distinct(AccessLogDB.user_id)))
        .filter(
            AccessLogDB.created_at >= f,
            AccessLogDB.created_at < t,
            AccessLogDB.user_id.isnot(None),
            AccessLogDB.status_code.isnot(None),
            AccessLogDB.status_code < 400,
        )
        .scalar()
    )
    active_users = int(active_users_q or 0)
    reports_n = int(
        db.query(func.count(ReportDB.id)).filter(ReportDB.created_at >= f, ReportDB.created_at < t).scalar() or 0
    )
    credits_consumed = int(
        db.query(func.coalesce(func.sum(CreditTransactionDB.delta), 0))
        .filter(
            CreditTransactionDB.created_at >= f,
            CreditTransactionDB.created_at < t,
            CreditTransactionDB.delta < 0,
        )
        .scalar()
        or 0
    )
    credits_consumed = abs(credits_consumed)
    subs_active = int(
        db.query(func.count(SubscriptionDB.id))
        .filter(SubscriptionDB.status == "active", SubscriptionDB.started_at.isnot(None), SubscriptionDB.expires_at > f)
        .scalar()
        or 0
    )
    # 运营口径收入：订阅关联套餐价（非真实支付 GMV）
    rev_rows = (
        db.query(func.coalesce(func.sum(PlanDB.price_cents), 0))
        .select_from(SubscriptionDB)
        .join(PlanDB, PlanDB.id == SubscriptionDB.plan_id)
        .filter(SubscriptionDB.created_at >= f, SubscriptionDB.created_at < t)
        .scalar()
    )
    revenue_cents_operational = int(rev_rows or 0)
    return {
        "period": {"start": f.date().isoformat(), "end": (t - timedelta(days=1)).date().isoformat()},
        "grain": grain,
        "new_users": new_users,
        "active_users_distinct": active_users,
        "reports_created": reports_n,
        "credits_consumed_sum": credits_consumed,
        "active_subscriptions_snapshot": subs_active,
        "revenue_cents_operational": revenue_cents_operational,
        "disclaimer": "收入为运营口径（新建订阅对应套餐标价之和），非实收 GMV；精确对账见商业化模块。",
    }


def users_trend(db: Session, *, start_date: Optional[str], end_date: Optional[str], grain: Grain) -> List[Dict[str, Any]]:
    f, t = clamp_date_range(start_date, end_date)
    if DATABASE_URL.startswith("sqlite"):
        b1 = _bucket_sqlite("created_at", grain)
        q_new = text(f"SELECT {b1} AS ts, COUNT(*) FROM users WHERE created_at >= :f AND created_at < :t GROUP BY ts")
        b2 = _bucket_sqlite("created_at", grain)
        q_act = text(
            f"SELECT {b2} AS ts, COUNT(DISTINCT user_id) FROM access_logs WHERE created_at >= :f AND created_at < :t "
            "AND user_id IS NOT NULL AND status_code IS NOT NULL AND status_code < 400 GROUP BY ts"
        )
    elif DATABASE_URL.startswith("mysql"):
        b1 = _bucket_mysql("created_at", grain)
        q_new = text(f"SELECT {b1} AS ts, COUNT(*) FROM users WHERE created_at >= :f AND created_at < :t GROUP BY ts")
        b2 = _bucket_mysql("created_at", grain)
        q_act = text(
            f"SELECT {b2} AS ts, COUNT(DISTINCT user_id) FROM access_logs WHERE created_at >= :f AND created_at < :t "
            "AND user_id IS NOT NULL AND status_code IS NOT NULL AND status_code < 400 GROUP BY ts"
        )
    else:
        b1 = _bucket_pg("created_at", grain)
        q_new = text(f"SELECT {b1} AS ts, COUNT(*)::int FROM users WHERE created_at >= :f AND created_at < :t GROUP BY 1")
        b2 = _bucket_pg("created_at", grain)
        q_act = text(
            f"SELECT {b2} AS ts, COUNT(DISTINCT user_id)::int FROM access_logs WHERE created_at >= :f AND created_at < :t "
            "AND user_id IS NOT NULL AND status_code IS NOT NULL AND status_code < 400 GROUP BY 1"
        )
    by_ts: Dict[str, Dict[str, Any]] = {}
    for ts, c in db.execute(q_new, {"f": f, "t": t}).fetchall():
        k = _norm_ts(str(ts))
        by_ts.setdefault(k, {"ts": k, "new_users": 0, "active_users": 0})
        by_ts[k]["new_users"] = int(c or 0)
    for ts, c in db.execute(q_act, {"f": f, "t": t}).fetchall():
        k = _norm_ts(str(ts))
        by_ts.setdefault(k, {"ts": k, "new_users": 0, "active_users": 0})
        by_ts[k]["active_users"] = int(c or 0)
    return sorted(by_ts.values(), key=lambda x: x["ts"])


def projects_trend(db: Session, *, start_date: Optional[str], end_date: Optional[str], grain: Grain) -> List[Dict[str, Any]]:
    f, t = clamp_date_range(start_date, end_date)
    if DATABASE_URL.startswith("sqlite"):
        b = _bucket_sqlite("created_at", grain)
        q = text(
            f"SELECT {b} AS ts, COUNT(*) FROM reports WHERE created_at >= :f AND created_at < :t GROUP BY ts"
        )
    elif DATABASE_URL.startswith("mysql"):
        b = _bucket_mysql("created_at", grain)
        q = text(
            f"SELECT {b} AS ts, COUNT(*) FROM reports WHERE created_at >= :f AND created_at < :t GROUP BY ts"
        )
    else:
        b = _bucket_pg("created_at", grain)
        q = text(
            f"SELECT {b} AS ts, COUNT(*)::int FROM reports WHERE created_at >= :f AND created_at < :t GROUP BY 1"
        )
    out: List[Dict[str, Any]] = []
    for ts, c in db.execute(q, {"f": f, "t": t}).fetchall():
        out.append({"ts": _norm_ts(str(ts)), "reports": int(c or 0)})
    return sorted(out, key=lambda x: x["ts"])


def revenue_trend(db: Session, *, start_date: Optional[str], end_date: Optional[str], grain: Grain) -> List[Dict[str, Any]]:
    f, t = clamp_date_range(start_date, end_date)
    if DATABASE_URL.startswith("sqlite"):
        b = _bucket_sqlite("subscriptions.created_at", grain)
        q = text(
            f"SELECT {b} AS ts, COALESCE(SUM(plans.price_cents),0) "
            "FROM subscriptions JOIN plans ON plans.id = subscriptions.plan_id "
            "WHERE subscriptions.created_at >= :f AND subscriptions.created_at < :t GROUP BY ts"
        )
    elif DATABASE_URL.startswith("mysql"):
        b = _bucket_mysql("subscriptions.created_at", grain)
        q = text(
            f"SELECT {b} AS ts, COALESCE(SUM(plans.price_cents),0) "
            "FROM subscriptions JOIN plans ON plans.id = subscriptions.plan_id "
            "WHERE subscriptions.created_at >= :f AND subscriptions.created_at < :t GROUP BY ts"
        )
    else:
        b = _bucket_pg("subscriptions.created_at", grain)
        q = text(
            f"SELECT {b} AS ts, COALESCE(SUM(plans.price_cents),0)::bigint "
            "FROM subscriptions JOIN plans ON plans.id = subscriptions.plan_id "
            "WHERE subscriptions.created_at >= :f AND subscriptions.created_at < :t GROUP BY 1"
        )
    out: List[Dict[str, Any]] = []
    for ts, cents in db.execute(q, {"f": f, "t": t}).fetchall():
        out.append(
            {
                "ts": _norm_ts(str(ts)),
                "revenue_cents_operational": int(cents or 0),
            }
        )
    return sorted(out, key=lambda x: x["ts"])


def usage_trend(db: Session, *, start_date: Optional[str], end_date: Optional[str], grain: Grain) -> List[Dict[str, Any]]:
    f, t = clamp_date_range(start_date, end_date)
    if DATABASE_URL.startswith("sqlite"):
        b = _bucket_sqlite("created_at", grain)
        q = text(
            f"SELECT {b} AS ts, type, SUM(ABS(delta)) FROM credit_transactions "
            "WHERE created_at >= :f AND created_at < :t GROUP BY ts, type"
        )
    elif DATABASE_URL.startswith("mysql"):
        b = _bucket_mysql("created_at", grain)
        q = text(
            f"SELECT {b} AS ts, type, SUM(ABS(delta)) FROM credit_transactions "
            "WHERE created_at >= :f AND created_at < :t GROUP BY ts, type"
        )
    else:
        b = _bucket_pg("created_at", grain)
        q = text(
            f"SELECT {b} AS ts, type, COALESCE(SUM(ABS(delta)),0)::bigint FROM credit_transactions "
            "WHERE created_at >= :f AND created_at < :t GROUP BY 1, type"
        )
    by_ts: Dict[str, Dict[str, Any]] = {}
    for ts, typ, vol in db.execute(q, {"f": f, "t": t}).fetchall():
        k = _norm_ts(str(ts))
        row = by_ts.setdefault(k, {"ts": k, "reserve": 0, "commit": 0, "refund": 0, "other": 0})
        tstr = str(typ or "")
        if tstr == "reserve":
            row["reserve"] = int(vol or 0)
        elif tstr == "commit":
            row["commit"] = int(vol or 0)
        elif tstr == "refund":
            row["refund"] = int(vol or 0)
        else:
            row["other"] += int(vol or 0)
    return sorted(by_ts.values(), key=lambda x: x["ts"])


def ops_stats(db: Session, *, start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    f, t = clamp_date_range(start_date, end_date)
    total_users = int(db.query(func.count(UserDB.id)).scalar() or 0)
    paid_users = int(db.query(func.count(func.distinct(SubscriptionDB.user_id))).filter(SubscriptionDB.status == "active").scalar() or 0)
    reports_ok = int(
        db.query(func.count(ReportDB.id))
        .filter(ReportDB.created_at >= f, ReportDB.created_at < t, ReportDB.status == "completed")
        .scalar()
        or 0
    )
    reports_fail = int(
        db.query(func.count(ReportDB.id))
        .filter(ReportDB.created_at >= f, ReportDB.created_at < t, ReportDB.status == "failed")
        .scalar()
        or 0
    )
    rev = int(
        db.query(func.coalesce(func.sum(PlanDB.price_cents), 0))
        .select_from(SubscriptionDB)
        .join(PlanDB, PlanDB.id == SubscriptionDB.plan_id)
        .filter(SubscriptionDB.created_at >= f, SubscriptionDB.created_at < t)
        .scalar()
        or 0
    )
    denom = max(paid_users, 1)
    arpu_cents = rev // denom
    vol_sum = func.coalesce(func.sum(func.abs(CreditTransactionDB.delta)), 0).label("vol")
    top_users_rows = (
        db.query(CreditTransactionDB.user_id, vol_sum)
        .filter(CreditTransactionDB.created_at >= f, CreditTransactionDB.created_at < t, CreditTransactionDB.delta < 0)
        .group_by(CreditTransactionDB.user_id)
        .order_by(vol_sum.desc())
        .limit(10)
        .all()
    )
    top_users = [{"user_id": r[0], "credits_used": int(r[1] or 0)} for r in top_users_rows]
    return {
        "period": {"start": f.date().isoformat(), "end": (t - timedelta(days=1)).date().isoformat()},
        "total_users": total_users,
        "active_subscription_users": paid_users,
        "reports_completed": reports_ok,
        "reports_failed": reports_fail,
        "arpu_cents_operational": arpu_cents,
        "top_credit_users": top_users,
    }


def feature_token(db: Session, *, start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    f, t = clamp_date_range(start_date, end_date)
    active_tokens = int(
        db.query(func.count(UserTokenDB.id)).filter(UserTokenDB.is_active.is_(True)).scalar() or 0
    )
    token_used_period = int(
        db.query(func.count(UserTokenDB.id))
        .filter(UserTokenDB.last_used_at.isnot(None), UserTokenDB.last_used_at >= f, UserTokenDB.last_used_at < t)
        .scalar()
        or 0
    )
    return {
        "period": {"start": f.date().isoformat(), "end": (t - timedelta(days=1)).date().isoformat()},
        "api_tokens_active": active_tokens,
        "api_tokens_used_in_period": token_used_period,
        "note": "模型与功能开关详见 /v1/features 与系统配置；此处为 Token 使用概况。",
    }


def export_csv(
    db: Session, *, report: str, start_date: Optional[str], end_date: Optional[str], grain: Grain
) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    if report == "overview":
        row = overview(db, start_date=start_date, end_date=end_date, grain=grain)
        w.writerow(["metric", "value"])
        for k, v in row.items():
            if isinstance(v, (dict, list)):
                continue
            w.writerow([k, v])
    elif report == "users-trend":
        w.writerow(["ts", "new_users", "active_users"])
        for r in users_trend(db, start_date=start_date, end_date=end_date, grain=grain):
            w.writerow([r["ts"], r.get("new_users"), r.get("active_users")])
    elif report == "projects-trend":
        w.writerow(["ts", "reports"])
        for r in projects_trend(db, start_date=start_date, end_date=end_date, grain=grain):
            w.writerow([r["ts"], r.get("reports")])
    elif report == "revenue-trend":
        w.writerow(["ts", "revenue_cents_operational"])
        for r in revenue_trend(db, start_date=start_date, end_date=end_date, grain=grain):
            w.writerow([r["ts"], r.get("revenue_cents_operational")])
    elif report == "usage-trend":
        w.writerow(["ts", "reserve", "commit", "refund", "other"])
        for r in usage_trend(db, start_date=start_date, end_date=end_date, grain=grain):
            w.writerow([r["ts"], r.get("reserve"), r.get("commit"), r.get("refund"), r.get("other")])
    elif report == "ops-stats":
        o = ops_stats(db, start_date=start_date, end_date=end_date)
        w.writerow(["metric", "value"])
        for k, v in o.items():
            if k == "top_credit_users":
                continue
            w.writerow([k, v])
        w.writerow([])
        w.writerow(["top_user_id", "credits_used"])
        for u in o.get("top_credit_users") or []:
            w.writerow([u.get("user_id"), u.get("credits_used")])
    elif report == "feature-token":
        ft = feature_token(db, start_date=start_date, end_date=end_date)
        w.writerow(["metric", "value"])
        for k, v in ft.items():
            w.writerow([k, v])
    else:
        w.writerow(["error", "unknown_report"])
    return buf.getvalue()
