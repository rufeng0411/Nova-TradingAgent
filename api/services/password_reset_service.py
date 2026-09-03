"""Password reset tokens and email."""

from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from api.database import PasswordResetTokenDB, UserDB
from api.services import auth_service


def _token_hash(raw: str) -> str:
    return hashlib.sha256(f"{raw}:{auth_service._secret_key()}".encode()).hexdigest()


def create_reset_token(db: Session, user: UserDB, client_ip: Optional[str] = None) -> str:
    """Return plaintext token (for URL); store hash in DB."""
    ttl_min = int(os.getenv("TA_RESET_TOKEN_TTL_MINUTES", "30"))
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    row = PasswordResetTokenDB(
        id=str(uuid4()),
        user_id=user.id,
        token_hash=_token_hash(raw),
        expires_at=now + timedelta(minutes=ttl_min),
        created_at=now,
        ip=client_ip,
    )
    db.add(row)
    db.commit()
    return raw


def verify_and_consume_token(db: Session, raw_token: str) -> Optional[UserDB]:
    if not raw_token:
        return None
    h = _token_hash(raw_token.strip())
    now = datetime.now(timezone.utc)
    row = (
        db.query(PasswordResetTokenDB)
        .filter(
            PasswordResetTokenDB.token_hash == h,
            PasswordResetTokenDB.used_at.is_(None),
        )
        .first()
    )
    if not row:
        return None
    exp = auth_service._as_utc(row.expires_at)
    if not exp or exp < now:
        return None
    row.used_at = now
    user = db.query(UserDB).filter(UserDB.id == row.user_id).first()
    db.commit()
    return user


def send_reset_email(email: str, raw_token: str) -> Optional[str]:
    base = os.getenv("TA_FRONTEND_URL", "").strip() or os.getenv("FRONTEND_URL", "").strip()
    if not base:
        base = "http://localhost:5173"
    link = f"{base.rstrip('/')}/reset-password?token={raw_token}"

    host = auth_service.get_env_alias(["MAIL_HOST", "MAIL_SERVER", "SMTP_HOST"]).strip()
    if not host:
        print(f"[auth] password reset link for {email}: {link}")
        if os.getenv("APP_ENV", "development") != "production":
            return link
        return None

    port = int(auth_service.get_env_alias(["MAIL_PORT", "SMTP_PORT"]) or "587")
    user = auth_service.get_env_alias(["MAIL_USER", "MAIL_USERNAME", "SMTP_USER"]).strip()
    password = auth_service.get_env_alias(["MAIL_PASS", "MAIL_PASSWORD", "SMTP_PASSWORD"]).strip()
    from_addr = auth_service.get_env_alias(["MAIL_FROM", "SMTP_FROM"], user or "noreply@example.com").strip()
    starttls = auth_service.get_env_alias(["MAIL_STARTTLS", "SMTP_TLS"], "1").strip().lower() not in ("0", "false", "off", "no")
    ssl_tls = auth_service.get_env_alias(["MAIL_SSL", "MAIL_SSL_TLS"], "0").strip().lower() in ("1", "true", "on", "yes")

    msg = EmailMessage()
    msg["Subject"] = "Nova-TradingAgent 重置密码"
    msg["From"] = from_addr
    msg["To"] = email
    msg.set_content(f"请点击以下链接重置密码（{os.getenv('TA_RESET_TOKEN_TTL_MINUTES', '30')} 分钟内有效）：\n\n{link}\n\n如非本人操作请忽略。")

    try:
        smtp_cls = smtplib.SMTP_SSL if ssl_tls else smtplib.SMTP
        with smtp_cls(host, port, timeout=20) as server:
            if starttls and not ssl_tls:
                server.starttls()
            if user:
                server.login(user, password)
            server.send_message(msg)
        return None
    except Exception as e:
        print(f"[auth] reset email failed: {e}")
        if os.getenv("APP_ENV", "development") != "production":
            return link
        return None
