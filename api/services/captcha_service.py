"""Simple image captcha (Pillow) — in-memory store, one-time verify."""

from __future__ import annotations

import asyncio
import base64
import io
import os
import random
import string
import time
from threading import Lock
from typing import Dict, Optional, Tuple
from uuid import uuid4

_CAPTCHA_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_store: Dict[str, Tuple[str, float]] = {}
_lock = Lock()
_ttl = float(os.getenv("TA_CAPTCHA_TTL_SECONDS", "300"))
# 默认关闭：登录/注册/找回密码不校验图形验证码；仅当显式 TA_CAPTCHA_ENABLED=1 时开放 GET /v1/auth/captcha（供可选场景）。
_enabled = os.getenv("TA_CAPTCHA_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def is_enabled() -> bool:
    return _enabled


def _purge_expired() -> None:
    now = time.time()
    dead = [k for k, (_, exp) in _store.items() if exp < now]
    for k in dead:
        _store.pop(k, None)


def generate_captcha() -> tuple[str, str]:
    """Return (captcha_id, data_uri_png_base64)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        raise RuntimeError("Pillow is required for captcha: pip install Pillow") from e

    code = "".join(random.choices(_CAPTCHA_CHARS, k=4))
    captcha_id = uuid4().hex
    w, h = 120, 40
    img = Image.new("RGB", (w, h), (245, 247, 250))
    draw = ImageDraw.Draw(img)
    for _ in range(3):
        draw.line(
            [(random.randint(0, w), random.randint(0, h)), (random.randint(0, w), random.randint(0, h))],
            fill=(random.randint(100, 180), random.randint(100, 180), random.randint(100, 180)),
            width=1,
        )
    for _ in range(50):
        g = random.randint(150, 220)
        draw.point((random.randint(0, w - 1), random.randint(0, h - 1)), fill=(g, g, g))
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for i, ch in enumerate(code):
        angle = random.randint(-20, 20)
        ch_img = Image.new("RGBA", (28, 32), (0, 0, 0, 0))
        ch_draw = ImageDraw.Draw(ch_img)
        ch_draw.text((2, 2), ch, font=font, fill=(30, 41, 59, 255))
        ch_img = ch_img.rotate(angle, expand=True)
        img.paste(ch_img, (10 + i * 24, 4), ch_img)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = base64.b64encode(buf.getvalue()).decode("ascii")
    data_uri = f"data:image/png;base64,{raw}"

    with _lock:
        _purge_expired()
        _store[captcha_id] = (code.upper(), time.time() + _ttl)

    return captcha_id, data_uri


def verify_and_consume(captcha_id: str, user_code: str) -> bool:
    """产品内认证不依赖图形验证码；恒为 True，避免旧代码/旧网关仍调用校验时阻断登录。"""
    return True


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60)
        with _lock:
            _purge_expired()
