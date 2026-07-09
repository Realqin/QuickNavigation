"""API 鉴权与操作审计中间件。"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.auth import resolve_user_from_request
from app.database import SessionLocal
from app.operation_log_service import record_api_operation

_PUBLIC_API_PREFIXES = (
    "/api/public/",
    "/api/auth/login",
)


def is_public_api_path(path: str) -> bool:
    if path in {"/health"}:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_API_PREFIXES)


class AuthAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if request.method == "OPTIONS":
            return await call_next(request)
        if not path.startswith("/api") or is_public_api_path(path):
            return await call_next(request)

        db = SessionLocal()
        try:
            user = resolve_user_from_request(request, db)
            if not user:
                return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})
            request.state.current_user = user
            response = await call_next(request)
            if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                record_api_operation(
                    db,
                    user=user,
                    method=request.method.upper(),
                    path=path,
                    status_code=response.status_code,
                    ip_address=request.client.host if request.client else None,
                )
            return response
        finally:
            db.close()
