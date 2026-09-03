"""503 maintenance mode (DB-driven), with allowlist for health/admin/auth."""

from __future__ import annotations

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.database import SessionLocal
from api.services import features_service

logger = logging.getLogger(__name__)


class MaintenanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path == "/healthz" or path.startswith("/health"):
            return await call_next(request)
        if path.startswith("/v1/admin") or path.startswith("/v1/features"):
            return await call_next(request)
        if path.startswith("/v1/auth/login") or path.startswith("/v1/auth/register"):
            return await call_next(request)
        if path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/redoc"):
            return await call_next(request)
        try:
            db = SessionLocal()
            try:
                if bool(features_service.get_merged(db).get("maintenance")):
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "MAINTENANCE_MODE", "message": "系统维护中，请稍后再试。"},
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning("maintenance check failed: %s", e)
        return await call_next(request)
