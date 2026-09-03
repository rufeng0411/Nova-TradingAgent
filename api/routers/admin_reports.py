"""Admin reporting API (/v1/admin/reports/*)."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from api.database import UserDB, get_db
from api.deps import _require_admin
from api.services import admin_metrics_service, admin_reports_service

router = APIRouter(prefix="/v1/admin/reports", tags=["admin-reports"])
Grain = Literal["day", "hour"]


@router.get("/overview")
def reports_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    grain: Grain = Query("day", pattern="^(day|hour)$"),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    return admin_reports_service.overview(db, start_date=start_date, end_date=end_date, grain=grain)


@router.get("/users-trend")
def reports_users_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    grain: Grain = Query("day", pattern="^(day|hour)$"),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    return {"items": admin_reports_service.users_trend(db, start_date=start_date, end_date=end_date, grain=grain)}


@router.get("/projects-trend")
def reports_projects_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    grain: Grain = Query("day", pattern="^(day|hour)$"),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    return {"items": admin_reports_service.projects_trend(db, start_date=start_date, end_date=end_date, grain=grain)}


@router.get("/revenue-trend")
def reports_revenue_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    grain: Grain = Query("day", pattern="^(day|hour)$"),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    return {"items": admin_reports_service.revenue_trend(db, start_date=start_date, end_date=end_date, grain=grain)}


@router.get("/usage-trend")
def reports_usage_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    grain: Grain = Query("day", pattern="^(day|hour)$"),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    return {"items": admin_reports_service.usage_trend(db, start_date=start_date, end_date=end_date, grain=grain)}


@router.get("/ops-stats")
def reports_ops_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    return admin_reports_service.ops_stats(db, start_date=start_date, end_date=end_date)


@router.get("/feature-token")
def reports_feature_token(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    return admin_reports_service.feature_token(db, start_date=start_date, end_date=end_date)


@router.get("/outcome-trend")
def reports_outcome_trend(
    days: int = Query(90, ge=7, le=365),
    group_by: str = Query("release_version", pattern="^(release_version|all)$"),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    return admin_metrics_service.get_outcome_trend(db, days=days, group_by=group_by)


@router.get("/export.csv", response_class=PlainTextResponse)
def reports_export_csv(
    report: str = Query(
        ...,
        description="overview|users-trend|projects-trend|revenue-trend|usage-trend|ops-stats|feature-token",
    ),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    grain: Grain = Query("day", pattern="^(day|hour)$"),
    db: Session = Depends(get_db),
    _: UserDB = Depends(_require_admin),
):
    body = admin_reports_service.export_csv(db, report=report, start_date=start_date, end_date=end_date, grain=grain)
    return PlainTextResponse(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="admin-report-{report}.csv"'},
    )
