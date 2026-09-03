"""FastAPI auth dependencies (shared by main and routers)."""

from __future__ import annotations

from typing import Optional, Set

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.database import UserDB, get_db, get_db_ctx
from api.services import admin_confirm_service, auth_service, token_service
from api.services.entitlements_service import user_has_advanced_market, user_has_fast_analysis

_auth_scheme = HTTPBearer(auto_error=False)


class RequireUser:
    def __init__(self, allow_api_token: bool = True):
        self.allow_api_token = allow_api_token

    def __call__(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_auth_scheme),
    ) -> UserDB:
        if not credentials:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

        token = credentials.credentials

        with get_db_ctx() as db:
            try:
                payload = auth_service.decode_access_token(token)
                user_id = str(payload.get("sub") or "")
                user = auth_service.get_user_by_id(db, user_id)
                if user and user.is_active:
                    if getattr(user, "status", "active") != "active":
                        raise HTTPException(status_code=403, detail="账户已停用")
                    db.expunge(user)
                    return user
            except HTTPException:
                raise
            except Exception:
                pass

            if self.allow_api_token and token.startswith(token_service.TOKEN_PREFIX):
                user = token_service.verify_token(db, token)
                if user and user.is_active:
                    if getattr(user, "status", "active") != "active":
                        raise HTTPException(status_code=403, detail="账户已停用")
                    db.expunge(user)
                    return user

        detail = "身份验证失败或该接口不支持 API Token 访问" if self.allow_api_token else "该接口仅限网页端登录访问"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


_require_api_user = RequireUser(allow_api_token=True)
_require_web_user = RequireUser(allow_api_token=False)


class RequireAdmin(RequireUser):
    def __init__(self) -> None:
        super().__init__(allow_api_token=False)

    def __call__(self, credentials: Optional[HTTPAuthorizationCredentials] = Depends(_auth_scheme)) -> UserDB:
        user = super().__call__(credentials)
        if getattr(user, "role", "user") != "admin":
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return user


_require_admin = RequireAdmin()


def admin_effective_scopes(user: UserDB) -> Set[str]:
    """admin_permissions JSON null/empty => full scopes (backward compatible)."""
    if getattr(user, "role", "user") != "admin":
        return set()
    raw = getattr(user, "admin_permissions", None)
    if raw is None or raw == []:
        return {"superadmin", "ops", "finance", "content", "support"}
    if isinstance(raw, list):
        return {str(x) for x in raw}
    return set()


def admin_has_scope(user: UserDB, scope: str) -> bool:
    scopes = admin_effective_scopes(user)
    return "superadmin" in scopes or scope in scopes


class RequireAdminScope:
    def __init__(self, scope: str) -> None:
        self.scope = scope

    def __call__(self, admin: UserDB = Depends(_require_admin)) -> UserDB:
        if admin_has_scope(admin, self.scope):
            return admin
        raise HTTPException(status_code=403, detail="当前管理员账号没有执行此操作的权限。")


_require_admin_finance = RequireAdminScope("finance")
_require_admin_ops = RequireAdminScope("ops")
_require_admin_content = RequireAdminScope("content")


def require_advanced_market(
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_web_user),
) -> UserDB:
    """高级行情（分时/盘口/成交/企业资料等）：管理员或含 advanced_market 权益的订阅用户。"""
    if not user_has_advanced_market(db, user):
        raise HTTPException(status_code=403, detail="需要高级 VIP 行情权益（管理员默认可用）")
    return user


def require_fast_analysis(
    db: Session = Depends(get_db),
    user: UserDB = Depends(_require_web_user),
) -> UserDB:
    if not user_has_fast_analysis(db, user):
        raise HTTPException(status_code=403, detail="需要快速分析权益（管理员默认可用）")
    return user


def require_finance_step_up(
    admin: UserDB = Depends(_require_admin_finance),
    x_admin_confirm: Optional[str] = Header(None, alias="X-Admin-Confirm"),
    db: Session = Depends(get_db),
) -> UserDB:
    if not admin_confirm_service.consume_token(db, admin.id, x_admin_confirm):
        raise HTTPException(
            status_code=412,
            detail="敏感操作需二次确认：请先输入管理员登录密码获取确认令牌（X-Admin-Confirm），令牌约 5 分钟内有效。",
        )
    return admin


def require_ops_step_up(
    admin: UserDB = Depends(_require_admin_ops),
    x_admin_confirm: Optional[str] = Header(None, alias="X-Admin-Confirm"),
    db: Session = Depends(get_db),
) -> UserDB:
    if not admin_confirm_service.consume_token(db, admin.id, x_admin_confirm):
        raise HTTPException(
            status_code=412,
            detail="敏感操作需二次确认：请先输入管理员登录密码获取确认令牌（X-Admin-Confirm），令牌约 5 分钟内有效。",
        )
    return admin



def optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_auth_scheme),
) -> Optional[UserDB]:
    if not credentials:
        return None
    try:
        payload = auth_service.decode_access_token(credentials.credentials)
    except Exception:
        return None
    user_id = str(payload.get("sub") or "")
    if not user_id:
        return None
    with get_db_ctx() as db:
        user = auth_service.get_user_by_id(db, user_id)
        if user:
            db.expunge(user)
        return user
