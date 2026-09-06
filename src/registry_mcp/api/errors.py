"""Turn every exception a route can raise into the `{"error": {...}}` envelope.

Per ``DECISIONS.md`` D-007, every expected failure is a raised
:class:`~registry_mcp.core.models.RegistryError`; this module is the *only*
place that serialises it (and everything else that can escape a route) to
JSON, so REST and MCP stay byte-identical as they drift (D-004).

HTTP status always comes from ``RegistryError.HTTP_STATUS`` (or an explicit
``http_status`` the raiser set) — never hard-coded here.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Route as StarletteRoute

from registry_mcp.core.models import ErrorCode, RegistryError

__all__ = ["install_error_handlers"]

logger = logging.getLogger(__name__)

#: Named so a crawler that guesses a wrong path is told where the real map is
#: (`NORBIZ_SPEC.md` §15's closing rule).
_UNKNOWN_ROUTE_HINT = (
    "There is no such route. GET /llms.txt for the discovery document, or "
    "GET /v1/countries for the endpoints and countries this service supports."
)


def _error_response(err: RegistryError) -> JSONResponse:
    headers: dict[str, str] = {}
    if err.code is ErrorCode.RATE_LIMITED:
        retry_after = err.details.get("retry_after")
        if retry_after is not None:
            headers["Retry-After"] = str(int(retry_after))
    return JSONResponse(status_code=err.http_status, content=err.to_dict(), headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    """Register every exception -> ``{"error": {...}}`` translation on ``app``."""

    @app.exception_handler(RegistryError)
    async def _registry_error_handler(request: Request, exc: RegistryError) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # A malformed query/path parameter FastAPI itself rejected (e.g. a
        # missing required `q`). Re-cast into our own shape rather than
        # Starlette's `{"detail": [...]}` so every failure looks the same.
        first: dict[str, Any] | None = next(iter(exc.errors()), None)
        detail = first.get("msg", "invalid request") if first else "invalid request"
        err = RegistryError(
            ErrorCode.BAD_REQUEST,
            f"Invalid request parameters: {detail}.",
            hint="Check the parameter against /openapi.json and retry with a corrected value.",
        )
        return _error_response(err)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if exc.status_code == 404:
            err = RegistryError(ErrorCode.NOT_FOUND, "No such route.", hint=_UNKNOWN_ROUTE_HINT)
        else:
            err = RegistryError(
                ErrorCode.BAD_REQUEST,
                str(exc.detail) if exc.detail else "Request error.",
                hint="Check the request method and path and retry.",
                http_status=exc.status_code,
            )
        return _error_response(err)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak a traceback into the body — log it server-side instead.
        # Review fix 3(a) (T30): D-040(e) closed the concrete path out of the
        # access log because an identifier — e.g. a Swedish personnummer —
        # can be the path itself (`GET /v1/SE/company/194009272719`); this
        # handler must not write the same thing to the same stream at ERROR.
        # Log the route *template* (e.g. `/v1/{country}/company/{id}`)
        # instead, never `request.url.path`; fall back to the method alone
        # when no route matched (a raw ASGI failure, or middleware raising
        # before routing ran) rather than substituting the concrete path.
        route = request.scope.get("route")
        if isinstance(route, StarletteRoute):
            logger.exception("Unhandled exception in %s %s", request.method, route.path)
        else:
            logger.exception("Unhandled exception in %s", request.method)
        err = RegistryError(
            ErrorCode.INTERNAL_ERROR,
            "An unexpected error occurred while handling this request.",
            hint=(
                "This is a bug on our side, not a problem with your request. Retry once; if "
                "it persists, open an issue at https://github.com/foretak/registry-mcp/issues "
                "naming the endpoint and time."
            ),
        )
        return _error_response(err)
