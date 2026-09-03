"""Authentication routes: register, login, captcha, me, forgot/reset password."""

from __future__ import annotations

import os
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from api.database import UserDB, get_db
from api.deps import _require_web_user
from api.schemas.auth import (
    AuthTokenResponse,
    CaptchaResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
)
from api.services import auth_service, captcha_service, password_reset_service
from api.services import password_service

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_CAPTCHA_RL: dict[str, list[float]] = {}
_LOGIN_RL: dict[str, list[float]] = {}

_REGISTER_ERR_ZH: dict[str, str] = {
    "registration_disabled": "本站已关闭新用户注册。",
    "invalid_username": "用户名格式不正确（3–50 位小写字母、数字、下划线）。",
    "invalid_email": "邮箱格式不正确。",
    "username_taken": "该用户名已被注册。",
    "email_taken": "该邮箱已被注册。",
}


def _captcha_rl_params() -> tuple[float, int, bool]:
    """(window_seconds, max_hits_per_window, disabled). Env: TA_CAPTCHA_RL_* ."""
    if os.getenv("TA_CAPTCHA_RL_DISABLED", "").strip().lower() in ("1", "true", "yes", "on"):
        return (30.0, 10**9, True)
    window = float(os.getenv("TA_CAPTCHA_RL_WINDOW_SECONDS", "30") or "30")
    mx = int(os.getenv("TA_CAPTCHA_RL_MAX", "60") or "60")
    if window <= 0:
        window = 30.0
    if mx < 1:
        mx = 60
    return (window, mx, False)


def _client_ip(request: Request) -> str:
    return (request.client.host if request.client else "") or "unknown"


def _rl_check(store: dict[str, list[float]], ip: str, window: float, max_hits: int) -> bool:
    now = time.time()
    w = store.setdefault(ip, [])
    w[:] = [t for t in w if now - t < window]
    if len(w) >= max_hits:
        return False
    w.append(now)
    return True


def _mask_phone(plain: str) -> str:
    p = re.sub(r"\D", "", plain)
    if len(p) < 7:
        return "***"
    return f"{p[:3]}****{p[-4:]}"


def _build_user_out(db: Session, user: UserDB) -> UserOut:
    from api.services import billing_service

    code, exp, st = billing_service.user_plan_snapshot(db, user)
    phone_masked = None
    if getattr(user, "phone_encrypted", None):
        dec = auth_service.decrypt_secret(user.phone_encrypted)
        if dec:
            phone_masked = _mask_phone(dec)
    role = getattr(user, "role", None) or "user"
    status_v = getattr(user, "status", None) or "active"
    perms = getattr(user, "admin_permissions", None)
    perm_list = list(perms) if isinstance(perms, list) else None
    return UserOut(
        id=user.id,
        email=user.email,
        username=getattr(user, "username", None),
        display_name=getattr(user, "display_name", None),
        role=role,
        status=status_v,
        credits=int(getattr(user, "credits", 0) or 0),
        plan_code=code,
        subscription_expires_at=exp,
        phone_masked=phone_masked,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        email_report_enabled=bool(getattr(user, "email_report_enabled", True)),
        wecom_report_enabled=bool(getattr(user, "wecom_report_enabled", True)),
        admin_permissions=perm_list,
    )


@router.get("/captcha", response_model=CaptchaResponse)
def get_captcha(request: Request, db: Session = Depends(get_db)):
    from api.services import features_service

    if not bool(features_service.get_merged(db).get("captcha_enabled", False)):
        return CaptchaResponse(captcha_id="", image="", enabled=False)
    if not captcha_service.is_enabled():
        return CaptchaResponse(captcha_id="", image="", enabled=False)
    ip = _client_ip(request)
    window, max_hits, rl_off = _captcha_rl_params()
    if not rl_off and not _rl_check(_CAPTCHA_RL, ip, window, max_hits):
        raise HTTPException(
            status_code=429,
            detail=(
                "验证码刷新过于频繁，请稍后再试。"
                "本地开发可在 .env 设置 TA_CAPTCHA_RL_DISABLED=1 关闭限流，"
                "或调大 TA_CAPTCHA_RL_MAX / TA_CAPTCHA_RL_WINDOW_SECONDS。"
            ),
        )
    try:
        cid, img = captcha_service.generate_captcha()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return CaptchaResponse(captcha_id=cid, image=img, enabled=True)


@router.get("/check-username")
def check_username(username: str, db: Session = Depends(get_db)):
    u = auth_service.normalize_username(username)
    if len(u) < 3:
        return {"available": False}
    taken = auth_service.get_user_by_username(db, u) is not None
    return {"available": not taken}


@router.post("/register", response_model=AuthTokenResponse)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    # 注册不校验图形验证码
    try:
        user = auth_service.register_user(
            db,
            username=body.username,
            email=body.email,
            password=body.password,
            phone=body.phone,
            display_name=body.display_name,
        )
    except ValueError as e:
        msg = str(e)
        code = 400
        if msg == "registration_disabled":
            code = 403
        detail = _REGISTER_ERR_ZH.get(msg, msg)
        raise HTTPException(status_code=code, detail=detail) from e
    user.last_login_at = auth_service._utcnow()
    user.last_login_ip = _client_ip(request)
    db.commit()
    db.refresh(user)
    token = auth_service.create_access_token(user)
    from api.services import admin_signals_service

    admin_signals_service.insert_signal(
        db,
        type="auth.user_registered",
        severity="info",
        payload={"username": user.username, "email": user.email},
        user_id=user.id,
    )
    return AuthTokenResponse(access_token=token, user=_build_user_out(db, user))


@router.post("/login", response_model=AuthTokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    if not _rl_check(_LOGIN_RL, ip, 60.0, 30):
        from api.services import admin_signals_service

        admin_signals_service.insert_signal_safe(
            type="auth.login_rate_limited",
            severity="warning",
            payload={"ip": ip},
        )
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试。")
    # 登录不校验图形验证码（避免与 invalid_credentials 混淆、降低本地/内网使用门槛）
    user = auth_service.authenticate(db, body.identifier, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码不正确，或该账号尚未设置密码。")
    user.last_login_at = auth_service._utcnow()
    user.last_login_ip = ip
    db.commit()
    db.refresh(user)
    token = auth_service.create_access_token(user)
    return AuthTokenResponse(access_token=token, user=_build_user_out(db, user))


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    # 忘记密码不校验图形验证码
    email = auth_service.normalize_email(body.email)
    user = auth_service.get_user_by_email(db, email)
    if not user:
        return {"message": "如果邮箱已注册，将收到重置链接"}
    raw = password_reset_service.create_reset_token(db, user, client_ip=_client_ip(request))
    link_or_none = password_reset_service.send_reset_email(email, raw)
    out: dict = {"message": "如果邮箱已注册，将收到重置链接"}
    if link_or_none and os.getenv("APP_ENV", "development") != "production":
        out["dev_reset_link"] = link_or_none
    return out


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = password_reset_service.verify_and_consume_token(db, body.token)
    if not user:
        raise HTTPException(status_code=400, detail="重置链接无效或已过期，请重新申请找回密码。")
    ok, msg = password_service.validate_strength(body.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    user.password_hash = password_service.hash_password(body.new_password)
    user.updated_at = auth_service._utcnow()
    db.commit()
    return {"message": "密码已重置，请登录"}


@router.get("/me", response_model=UserOut)
def get_me(db: Session = Depends(get_db), current_user: UserDB = Depends(_require_web_user)):
    u = db.query(UserDB).filter(UserDB.id == current_user.id).first() or current_user
    return _build_user_out(db, u)
