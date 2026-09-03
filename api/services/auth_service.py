from __future__ import annotations

import base64
import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional
from uuid import uuid4

import re
import jwt
from cryptography.fernet import Fernet, InvalidToken
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy.orm import Session

from api.database import EmailVerificationCodeDB, UserDB, UserLLMConfigDB
from api.services import password_service


ALGORITHM = "HS256"

# 未配置 TA_ADMIN_EMAIL / TA_ADMIN_USERNAME 时与 .env.example、重置脚本共用
DEFAULT_ADMIN_EMAIL = "admin@localhost"
DEFAULT_ADMIN_USERNAME = "admin"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


_DEFAULT_SECRET = "tradingagents-ashare-dev-secret"


def _secret_key() -> str:
    return os.getenv("TA_APP_SECRET_KEY") or _DEFAULT_SECRET


def _fernet_from_key(key: str) -> Fernet:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet() -> Fernet:
    return _fernet_from_key(_secret_key())


def is_custom_secret_configured() -> bool:
    return bool(os.getenv("TA_APP_SECRET_KEY"))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def decrypt_secret_with_fallback(value: Optional[str]) -> Optional[str]:
    """Decrypt trying current key first, then default key as fallback."""
    if not value:
        return None
    # Try current key
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        pass
    # Try default key (first-time migration: no key → custom key)
    if is_custom_secret_configured():
        try:
            return _fernet_from_key(_DEFAULT_SECRET).decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            pass
    return None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def relocate_conflicting_email_holders(db: Session, email: str, *, keep_user_id: Optional[str]) -> int:
    """将 `email` 的占用者（可选排除 keep_user_id）迁到内部占位地址，便于管理员统一邮箱。返回迁移人数。"""
    em = normalize_email(email)
    q = db.query(UserDB).filter(UserDB.email == em)
    if keep_user_id:
        q = q.filter(UserDB.id != keep_user_id)
    n = 0
    for row in q.all():
        row.email = f"released-{uuid4().hex}@reassigned.internal"
        n += 1
    return n


def generate_login_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def hash_code(email: str, code: str) -> str:
    return hashlib.sha256(f"{normalize_email(email)}:{code}:{_secret_key()}".encode("utf-8")).hexdigest()


def create_access_token(user: UserDB, expires_days: int = 30) -> str:
    now = _utcnow()
    role = getattr(user, "role", None) or "user"
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": role,
        "exp": now + timedelta(days=expires_days),
        "iat": now,
    }
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])


def get_user_by_email(db: Session, email: str) -> Optional[UserDB]:
    return db.query(UserDB).filter(UserDB.email == normalize_email(email)).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[UserDB]:
    return db.query(UserDB).filter(UserDB.id == user_id).first()


def upsert_login_code(db: Session, email: str, purpose: str = "login") -> str:
    email = normalize_email(email)
    code = generate_login_code()
    now = _utcnow()

    db.query(EmailVerificationCodeDB).filter(
        EmailVerificationCodeDB.email == email,
        EmailVerificationCodeDB.purpose == purpose,
        EmailVerificationCodeDB.consumed_at.is_(None),
    ).update({"consumed_at": now})

    row = EmailVerificationCodeDB(
        id=str(uuid4()),
        email=email,
        code_hash=hash_code(email, code),
        purpose=purpose,
        expires_at=now + timedelta(minutes=10),
        created_at=now,
    )
    db.add(row)
    db.commit()
    return code


def ensure_user_from_email(db: Session, email: str, client_ip: Optional[str] = None) -> UserDB:
    """Create or update user by email without verification code.

    Only call when TA_PASSWORDLESS_LOGIN is enabled (see api.main login-direct).
    """
    email = normalize_email(email)
    now = _utcnow()
    user = get_user_by_email(db, email)
    if not user:
        user = UserDB(
            id=str(uuid4()),
            email=email,
            is_active=True,
            created_at=now,
            updated_at=now,
            last_login_at=now,
            last_login_ip=client_ip,
        )
        db.add(user)
    else:
        user.last_login_at = now
        user.last_login_ip = client_ip
        user.updated_at = now
    db.commit()
    db.refresh(user)
    return user


def verify_login_code(db: Session, email: str, code: str, purpose: str = "login", client_ip: Optional[str] = None) -> Optional[UserDB]:
    email = normalize_email(email)
    now = _utcnow()
    code_row = (
        db.query(EmailVerificationCodeDB)
        .filter(
            EmailVerificationCodeDB.email == email,
            EmailVerificationCodeDB.purpose == purpose,
            EmailVerificationCodeDB.consumed_at.is_(None),
        )
        .order_by(EmailVerificationCodeDB.created_at.desc())
        .first()
    )
    expires_at = _as_utc(code_row.expires_at) if code_row else None
    if not code_row or not expires_at or expires_at < now:
        return None
    if code_row.code_hash != hash_code(email, code):
        return None

    code_row.consumed_at = now
    user = get_user_by_email(db, email)
    if not user:
        user = UserDB(
            id=str(uuid4()),
            email=email,
            is_active=True,
            created_at=now,
            updated_at=now,
            last_login_at=now,
            last_login_ip=client_ip,
        )
        db.add(user)
    else:
        user.last_login_at = now
        user.last_login_ip = client_ip
        user.updated_at = now
    db.commit()
    db.refresh(user)
    return user


def get_env_alias(keys: list[str], default: str = "") -> str:
    for k in keys:
        v = os.getenv(k)
        if v is not None:
            return v
    return default


def send_login_code(email: str, code: str) -> Optional[str]:
    smtp_host = get_env_alias(["MAIL_HOST", "MAIL_SERVER", "SMTP_HOST"]).strip()
    if not smtp_host:
        print(f"[auth] login code for {email}: {code}")
        if os.getenv("APP_ENV", "development") != "production":
            return code
        return None

    smtp_port = int(get_env_alias(["MAIL_PORT", "SMTP_PORT"]) or "587")
    smtp_user = get_env_alias(["MAIL_USER", "MAIL_USERNAME", "SMTP_USER"]).strip()
    smtp_password = get_env_alias(["MAIL_PASS", "MAIL_PASSWORD", "SMTP_PASSWORD"]).strip()
    smtp_from = get_env_alias(["MAIL_FROM", "SMTP_FROM"], smtp_user or "noreply@example.com").strip()
    
    # 兼容旧版的逻辑
    smtp_starttls_str = get_env_alias(["MAIL_STARTTLS", "SMTP_TLS"], "1").strip().lower()
    smtp_starttls = smtp_starttls_str not in ("0", "false", "off", "no")
    
    smtp_ssl_tls_str = get_env_alias(["MAIL_SSL", "MAIL_SSL_TLS"], "0").strip().lower()
    smtp_ssl_tls = smtp_ssl_tls_str in ("1", "true", "on", "yes")

    msg = EmailMessage()
    msg["Subject"] = "Nova-TradingAgent 登录验证码"
    msg["From"] = smtp_from
    msg["To"] = email
    msg.set_content(f"你的 Nova-TradingAgent 登录验证码是：{code}\n\n10 分钟内有效。")

    try:
        print(f"[auth] connecting to {smtp_host}:{smtp_port} (SSL: {smtp_ssl_tls}, STARTTLS: {smtp_starttls})")
        smtp_cls = smtplib.SMTP_SSL if smtp_ssl_tls else smtplib.SMTP
        with smtp_cls(smtp_host, smtp_port, timeout=20) as server:
            if smtp_starttls and not smtp_ssl_tls:
                server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return None
    except Exception as e:
        print(f"[auth] failed to send email via {smtp_host}: {e}")
        print(f"[auth] falling back to console log. code for {email}: {code}")
        if os.getenv("APP_ENV", "development") != "production":
            return code
        return None


def normalize_username(username: str) -> str:
    return username.strip().lower()


def get_user_by_username(db: Session, username: str) -> Optional[UserDB]:
    u = normalize_username(username)
    return db.query(UserDB).filter(UserDB.username == u).first()


def register_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    phone: Optional[str] = None,
    display_name: Optional[str] = None,
) -> UserDB:
    if os.getenv("TA_ALLOW_REGISTRATION", "1").strip().lower() in ("0", "false", "no", "off"):
        raise ValueError("registration_disabled")
    from api.services import features_service

    if not bool(features_service.get_merged(db).get("allow_registration", True)):
        raise ValueError("registration_disabled")
    u = normalize_username(username)
    if len(u) < 3 or len(u) > 50 or not re.match(r"^[a-z0-9_]+$", u):
        raise ValueError("invalid_username")
    ok, msg = password_service.validate_strength(password)
    if not ok:
        raise ValueError(msg)
    email_n = normalize_email(email)
    if not re.match(r"^[^@\s]+@[^@\s.]+\.[^@\s.]+$", email_n):
        raise ValueError("invalid_email")
    if get_user_by_username(db, u):
        raise ValueError("username_taken")
    if get_user_by_email(db, email_n):
        raise ValueError("email_taken")
    now = _utcnow()
    initial = int(os.getenv("TA_REGISTRATION_DEFAULT_CREDITS", "50"))
    phone_enc = encrypt_secret(phone.strip()) if phone and phone.strip() else None
    user = UserDB(
        id=str(uuid4()),
        email=email_n,
        username=u,
        password_hash=password_service.hash_password(password),
        phone_encrypted=phone_enc,
        display_name=(display_name or "").strip() or None,
        is_active=True,
        role="user",
        status="active",
        credits=0,
        total_credits_consumed=0,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if initial > 0:
        from api.services import credits_service

        credits_service.grant(db, user.id, initial, "signup_bonus", ref_type="signup", ref_id=user.id)
    return user


def authenticate(db: Session, identifier: str, password: str) -> Optional[UserDB]:
    ident = (identifier or "").strip()
    plain = (password or "").strip()
    if not ident or not plain:
        return None

    candidates: list[UserDB] = []
    if "@" in ident:
        em = normalize_email(ident)
        local = ident.split("@", 1)[0].strip().lower()
        # 先按 @ 左侧用户名匹配，再按整段邮箱；避免「目标管理员邮箱」被他人注册占用时登错账号
        if re.match(r"^[a-z0-9_]{3,50}$", local):
            by_local = get_user_by_username(db, local)
            if by_local:
                candidates.append(by_local)
        by_email = get_user_by_email(db, em)
        if by_email and all(by_email.id != u.id for u in candidates):
            candidates.append(by_email)
    else:
        u = get_user_by_username(db, ident)
        if u:
            candidates.append(u)

    for user in candidates:
        if not getattr(user, "password_hash", None):
            continue
        if not user.is_active:
            continue
        if getattr(user, "status", "active") != "active":
            continue
        if password_service.verify_password(plain, user.password_hash):
            return user
    return None


def change_password(db: Session, user_id: str, old_password: str, new_password: str) -> None:
    user = get_user_by_id(db, user_id)
    if not user or not user.password_hash:
        raise ValueError("no_password_set")
    if not password_service.verify_password(old_password, user.password_hash):
        raise ValueError("wrong_password")
    ok, msg = password_service.validate_strength(new_password)
    if not ok:
        raise ValueError(msg)
    user.password_hash = password_service.hash_password(new_password)
    user.updated_at = _utcnow()
    db.commit()


def admin_set_password(db: Session, user_id: str, new_password: str) -> None:
    ok, msg = password_service.validate_strength(new_password)
    if not ok:
        raise ValueError(msg)
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("user_not_found")
    user.password_hash = password_service.hash_password(new_password)
    user.updated_at = _utcnow()
    db.commit()


def ensure_default_admin(db: Session) -> None:
    """Create or promote default admin from env (called at startup)."""
    email = normalize_email((os.getenv("TA_ADMIN_EMAIL") or DEFAULT_ADMIN_EMAIL).strip())
    raw_pwd = os.getenv("TA_ADMIN_PASSWORD")
    explicit_admin_pwd = raw_pwd.strip() if raw_pwd else None
    if not explicit_admin_pwd:
        raise RuntimeError(
            "TA_ADMIN_PASSWORD must be set (letters+digits, min 8). See .env.example Quick start."
        )
    pwd = explicit_admin_pwd
    uname = normalize_username(os.getenv("TA_ADMIN_USERNAME") or DEFAULT_ADMIN_USERNAME)
    user = get_user_by_username(db, uname) or get_user_by_email(db, email)
    now = _utcnow()
    if not user:
        relocate_conflicting_email_holders(db, email, keep_user_id=None)
        user = UserDB(
            id=str(uuid4()),
            email=email,
            username=uname,
            password_hash=password_service.hash_password(pwd),
            is_active=True,
            role="admin",
            status="active",
            credits=int(os.getenv("TA_REGISTRATION_DEFAULT_CREDITS", "10000")),
            total_credits_consumed=0,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.commit()
        if not os.getenv("TA_APP_SECRET_KEY"):
            print("[auth] WARNING: default admin created; set TA_APP_SECRET_KEY in production.")
        return
    changed = False
    if getattr(user, "role", "user") != "admin":
        user.role = "admin"
        changed = True
    if relocate_conflicting_email_holders(db, email, keep_user_id=user.id) > 0:
        changed = True
    if normalize_email(user.email) != email:
        user.email = email
        changed = True
    if not user.password_hash:
        user.password_hash = password_service.hash_password(pwd)
        changed = True
    elif explicit_admin_pwd and not password_service.verify_password(explicit_admin_pwd, user.password_hash):
        user.password_hash = password_service.hash_password(explicit_admin_pwd)
        changed = True
    if changed:
        user.updated_at = now
        db.commit()


def ensure_default_plans(db: Session) -> None:
    from api.database import PlanDB

    if db.query(PlanDB).count() > 0:
        return
    now = _utcnow()
    seed = [
        ("free", "Free", 0, 30, 50),
        ("pro", "Pro", 9900, 30, 500),
        ("team", "Team", 49900, 30, 5000),
    ]
    for code, name, price, days, mc in seed:
        db.add(
            PlanDB(
                id=str(uuid4()),
                code=code,
                name=name,
                price_cents=price,
                currency="CNY",
                period_days=days,
                monthly_credits=mc,
                features_json="[]",
                is_active=True,
                sort_order=0 if code == "free" else 1 if code == "pro" else 2,
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()


def get_user_llm_config(db: Session, user_id: str) -> Optional[UserLLMConfigDB]:
    return db.query(UserLLMConfigDB).filter(UserLLMConfigDB.user_id == user_id).first()


def upsert_user_llm_config(
    db: Session,
    user_id: str,
    *,
    llm_provider: Optional[str] = None,
    backend_url: Optional[str] = None,
    quick_think_llm: Optional[str] = None,
    deep_think_llm: Optional[str] = None,
    max_debate_rounds: Optional[int] = None,
    max_risk_discuss_rounds: Optional[int] = None,
    api_key: Optional[str] = None,
    wecom_webhook_url: Optional[str] = None,
    clear_api_key: bool = False,
    clear_wecom_webhook: bool = False,
    default_analysts: Optional[list] = None,
) -> UserLLMConfigDB:
    row = get_user_llm_config(db, user_id)
    now = _utcnow()
    if not row:
        row = UserLLMConfigDB(user_id=user_id, created_at=now, updated_at=now)
        db.add(row)

    if llm_provider is not None:
        row.llm_provider = llm_provider
    if backend_url is not None:
        row.backend_url = backend_url
    if quick_think_llm is not None:
        row.quick_think_llm = quick_think_llm
    if deep_think_llm is not None:
        row.deep_think_llm = deep_think_llm
    if max_debate_rounds is not None:
        row.max_debate_rounds = max_debate_rounds
    if max_risk_discuss_rounds is not None:
        row.max_risk_discuss_rounds = max_risk_discuss_rounds

    if clear_api_key:
        row.api_key_encrypted = None
    elif api_key:
        row.api_key_encrypted = encrypt_secret(api_key)

    if clear_wecom_webhook:
        row.wecom_webhook_encrypted = None
    elif wecom_webhook_url:
        row.wecom_webhook_encrypted = encrypt_secret(wecom_webhook_url)

    if default_analysts is not None:
        import json
        row.default_analysts = json.dumps(default_analysts)

    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row
