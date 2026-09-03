"""把 .env 里的 TA_ADMIN_PASSWORD 写入管理员账号（用户名优先于邮箱，与 ensure_default_admin 一致）。

仓库根执行:
  uv run python scripts/reset_admin_password.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from api.database import UserDB, get_db_ctx, init_db
from api.services import auth_service, password_service


def main() -> int:
    raw = os.getenv("TA_ADMIN_PASSWORD")
    pwd = raw.strip() if raw else ""
    if not pwd:
        print("错误: 请在 .env 设置 TA_ADMIN_PASSWORD", file=sys.stderr)
        return 1
    email = auth_service.normalize_email((os.getenv("TA_ADMIN_EMAIL") or auth_service.DEFAULT_ADMIN_EMAIL).strip())
    uname = auth_service.normalize_username(os.getenv("TA_ADMIN_USERNAME") or auth_service.DEFAULT_ADMIN_USERNAME)
    init_db()
    with get_db_ctx() as db:
        user = auth_service.get_user_by_username(db, uname) or auth_service.get_user_by_email(db, email)
        if not user:
            print(f"错误: 未找到 username={uname} 或 email={email}", file=sys.stderr)
            return 1
        user.password_hash = password_service.hash_password(pwd)
        user.role = "admin"
        user.status = "active"
        user.is_active = True
        auth_service.relocate_conflicting_email_holders(db, email, keep_user_id=user.id)
        if auth_service.normalize_email(user.email) != email:
            user.email = email
        db.commit()
        print(f"已写入密码: username={user.username!r} email={user.email!r} id={user.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
