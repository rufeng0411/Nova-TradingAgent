"""Password hashing and strength validation (bcrypt, no passlib)."""

from __future__ import annotations

import os
import re

import bcrypt

_MIN_LEN = int(os.getenv("TA_PASSWORD_MIN_LENGTH", "8"))


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    if not plain or not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def validate_strength(plain: str) -> tuple[bool, str]:
    if len(plain) < _MIN_LEN:
        return False, f"密码至少 {_MIN_LEN} 位"
    if not re.search(r"[A-Za-z]", plain):
        return False, "密码需包含至少一个字母"
    if not re.search(r"\d", plain):
        return False, "密码需包含至少一个数字"
    return True, ""
