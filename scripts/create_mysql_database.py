"""在本地 MySQL 上创建 utf8mb4 库（默认名 tradingagents）。

从仓库根目录执行。凭据优先读 .env（与 reset_admin_password 一致），也可用命令行覆盖。

环境变量（.env）:
  TA_MYSQL_HOST   默认 127.0.0.1
  TA_MYSQL_PORT   默认 3306
  TA_MYSQL_USER   默认 root
  TA_MYSQL_PASSWORD  必填其一：或与 MYSQL_ROOT_PASSWORD 二选一
  TA_MYSQL_DATABASE  默认 tradingagents

示例:
  uv run python scripts/create_mysql_database.py
  uv run python scripts/create_mysql_database.py --database mydb
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None, help="若未设 .env，可临时传入（勿写入脚本）")
    parser.add_argument("--no-password", action="store_true", help="MySQL 用户无密码时使用")
    parser.add_argument("--database", default=None)
    args = parser.parse_args()

    host = (args.host or os.getenv("TA_MYSQL_HOST") or "127.0.0.1").strip()
    port = args.port if args.port is not None else int(os.getenv("TA_MYSQL_PORT", "3306") or "3306")
    user = (args.user or os.getenv("TA_MYSQL_USER") or "root").strip()
    password = args.password
    if args.no_password:
        password = ""
    elif password is None:
        password = (os.getenv("TA_MYSQL_PASSWORD") or os.getenv("MYSQL_ROOT_PASSWORD") or "").strip()
    else:
        password = password.strip()

    db_name = (args.database or os.getenv("TA_MYSQL_DATABASE") or "tradingagents").strip()

    if not re.fullmatch(r"[A-Za-z0-9_]+", db_name):
        print(f"错误: 非法库名 {db_name!r}（仅允许字母数字下划线）", file=sys.stderr)
        return 1

    if not args.no_password and not password:
        print(
            "错误: 未配置 MySQL 密码。请在 .env 中设置 TA_MYSQL_PASSWORD=你的密码\n"
            "（或 MYSQL_ROOT_PASSWORD），再执行本脚本；若确无密码可加参数 --no-password。",
            file=sys.stderr,
        )
        return 1

    try:
        import pymysql
    except ImportError:
        print("错误: 请先安装 pymysql: pip install pymysql", file=sys.stderr)
        return 1

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset="utf8mb4",
        )
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.close()
    except Exception as e:
        print(f"错误: 无法连接或建库: {e}", file=sys.stderr)
        return 1

    print(f"已创建（或已存在）数据库: {db_name}")
    safe_url = (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/"
        f"{db_name}?charset=utf8mb4"
    )
    print("请将下行写入 .env 并重启 API（勿泄露给他人）:")
    print(f"DATABASE_URL={safe_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
