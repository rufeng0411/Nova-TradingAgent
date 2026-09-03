"""Async CSV export jobs for admin (sanitized)."""

from __future__ import annotations

import csv
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from api.database import (
    SYSTEM_LEGACY_USER_ID,
    AccessLogDB,
    AdminExportJobDB,
    CreditTransactionDB,
    UserDB,
    get_db_ctx,
)

logger = logging.getLogger(__name__)

_EXPORT_ROOT = Path(os.getenv("TA_ADMIN_EXPORT_DIR", "data/admin_exports"))


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"**@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def create_job(db: Session, *, export_type: str, admin_id: str) -> AdminExportJobDB:
    _EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    jid = str(uuid4())
    row = AdminExportJobDB(
        id=jid,
        export_type=export_type,
        status="pending",
        created_by=admin_id,
        created_at=datetime.now(timezone.utc),
        download_token=secrets.token_urlsafe(24),
        download_consumed=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _write_users_csv(db: Session, path: Path) -> None:
    rows = (
        db.query(UserDB)
        .filter(UserDB.id != SYSTEM_LEGACY_USER_ID, UserDB.role != "system")
        .order_by(UserDB.created_at.desc())
        .limit(50_000)
        .all()
    )
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "email_masked", "username", "role", "status", "credits", "created_at"])
        for u in rows:
            w.writerow(
                [
                    u.id,
                    _mask_email(u.email or ""),
                    (u.username or "")[:20],
                    getattr(u, "role", "user"),
                    getattr(u, "status", "active"),
                    int(getattr(u, "credits", 0) or 0),
                    u.created_at.isoformat() if u.created_at else "",
                ]
            )


def _write_access_csv(db: Session, path: Path) -> None:
    rows = db.query(AccessLogDB).order_by(AccessLogDB.created_at.desc()).limit(100_000).all()
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "user_id", "ip_masked", "method", "path", "status_code", "latency_ms", "created_at"])
        for r in rows:
            ip = r.ip or ""
            ip_m = re.sub(r"(\d+\.\d+)\.\d+\.\d+", r"\1.*.*", ip) if "." in ip else ip[:8]
            w.writerow(
                [
                    r.id,
                    r.user_id or "",
                    ip_m,
                    r.method or "",
                    (r.path or "")[:200],
                    r.status_code or "",
                    r.latency_ms or "",
                    r.created_at.isoformat() if r.created_at else "",
                ]
            )


def _write_credits_csv(db: Session, path: Path) -> None:
    rows = db.query(CreditTransactionDB).order_by(CreditTransactionDB.created_at.desc()).limit(100_000).all()
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "user_id", "delta", "type", "reason", "ref_type", "ref_id", "created_at"])
        for r in rows:
            w.writerow(
                [
                    r.id,
                    r.user_id,
                    r.delta,
                    r.type,
                    (r.reason or "")[:80],
                    r.ref_type or "",
                    r.ref_id or "",
                    r.created_at.isoformat() if r.created_at else "",
                ]
            )


def run_export_job(job_id: str) -> None:
    try:
        with get_db_ctx() as db:
            job = db.query(AdminExportJobDB).filter(AdminExportJobDB.id == job_id).first()
            if not job or job.status != "pending":
                return
            job.status = "running"
            db.commit()
            et = job.export_type
            path = _EXPORT_ROOT / f"{job_id}.csv"
            if et == "users":
                _write_users_csv(db, path)
            elif et == "access_logs":
                _write_access_csv(db, path)
            elif et == "credits":
                _write_credits_csv(db, path)
            else:
                job.status = "failed"
                job.error_message = "unknown_export_type"
                db.commit()
                return
            job.status = "completed"
            job.file_path = str(path.resolve())
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as e:
        logger.exception("export job failed")
        try:
            with get_db_ctx() as db:
                job = db.query(AdminExportJobDB).filter(AdminExportJobDB.id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error_message = str(e)[:500]
                    db.commit()
        except Exception:
            pass


def get_job(db: Session, job_id: str) -> Optional[AdminExportJobDB]:
    return db.query(AdminExportJobDB).filter(AdminExportJobDB.id == job_id).first()
