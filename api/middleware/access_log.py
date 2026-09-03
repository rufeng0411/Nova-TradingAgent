"""HTTP access logging middleware."""

from __future__ import annotations

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.services import access_log_service, auth_service


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        try:
            latency_ms = int((time.perf_counter() - start) * 1000)
            path = request.url.path
            if path in ("/healthz", "/favicon.ico") or path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/redoc"):
                return response
            user_id = None
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
                try:
                    payload = auth_service.decode_access_token(token)
                    user_id = str(payload.get("sub") or "") or None
                except Exception:
                    user_id = None
            client = request.client
            ip = client.host if client else None
            access_log_service.enqueue(
                user_id=user_id,
                ip=ip,
                method=request.method,
                path=path,
                status_code=response.status_code,
                latency_ms=latency_ms,
                user_agent=request.headers.get("user-agent"),
            )
        except Exception:
            pass
        return response
