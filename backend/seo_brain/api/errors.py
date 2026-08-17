"""Uniform error envelope for the v1 API (part of the frontend contract).

Every non-2xx response has the shape:
    {"error": {"code": "<machine_code>", "message": "<human text>", "details": <any|null>, "request_id": "<id>"}}
codes: bad_request | unauthorized | not_found | conflict | validation_error | internal_error | <custom>
Every response (success or error) carries an `X-Request-ID` header (echoed if the client sent one).
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("api.errors")

_STATUS_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
                 409: "conflict", 422: "validation_error", 429: "rate_limited", 500: "internal_error", 501: "not_implemented"}


class ApiError(HTTPException):
    """HTTPException with an explicit machine-readable code and optional details."""

    def __init__(self, status_code: int, message: str, code: str | None = None, details=None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code or _STATUS_CODES.get(status_code, "error")
        self.details = details


def _envelope(request: Request, status: int, message: str, code: str | None = None, details=None) -> JSONResponse:
    rid = getattr(request.state, "request_id", None) or "-"
    body = {"error": {"code": code or _STATUS_CODES.get(status, "error"), "message": message, "details": details, "request_id": rid}}
    return JSONResponse(body, status_code=status, headers={"X-Request-ID": rid})


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def install_error_handlers(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return _envelope(request, exc.status_code, str(exc.detail), exc.code, exc.details)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        msg = exc.detail if isinstance(exc.detail, str) else "request failed"
        details = None if isinstance(exc.detail, str) else exc.detail
        return _envelope(request, exc.status_code, msg, None, details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return _envelope(request, 422, "request validation failed", "validation_error", details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception(f"unhandled error on {request.method} {request.url.path}: {exc}")
        return _envelope(request, 500, "internal server error", "internal_error", {"type": exc.__class__.__name__})
