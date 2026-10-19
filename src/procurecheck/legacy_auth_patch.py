"""Protect the legacy routes that predate role-based tool authentication.

Install this middleware in procurecheck/api.py after app = FastAPI(...).
"""
from fastapi import Request
from fastapi.responses import JSONResponse

from .tools.authorization import (
    ApiKeyError,
    PERMISSION_ANALYSE,
    load_api_keys,
    principal_for_key,
)

LEGACY_PROTECTED = frozenset({
    ("POST", "/check"),
    ("POST", "/checklist/parse"),
})


def install_legacy_auth(app):
    @app.middleware("http")
    async def legacy_authentication(request: Request, call_next):
        if (request.method, request.url.path) not in LEGACY_PROTECTED:
            return await call_next(request)
        try:
            keys = load_api_keys()
        except ApiKeyError:
            return JSONResponse(status_code=500, content={
                "status": "error",
                "error_code": "CONFIGURATION_ERROR",
                "message": "Authentication configuration error.",
            })
        principal = principal_for_key(request.headers.get("X-API-Key"), keys)
        if principal is None:
            return JSONResponse(status_code=401, content={
                "status": "error",
                "error_code": "UNAUTHORIZED",
                "message": "Valid X-API-Key required.",
            })
        if not principal.may(PERMISSION_ANALYSE):
            return JSONResponse(status_code=403, content={
                "status": "error",
                "error_code": "UNAUTHORIZED",
                "message": "Permission document:analyse required.",
            })
        return await call_next(request)
