"""In-process per-client-IP token-bucket rate limiter for the REST surface.

60 requests/minute per client IP (`NORBIZ_SPEC.md` §7, `tasks/T06.md`). Honours
the first value of ``X-Forwarded-For`` since we run behind Caddy (a reverse
proxy) — the socket peer would otherwise always be the proxy.

The four static discovery routes (``/``, ``/llms.txt``, ``/llms-full.txt``,
``/server.json``) are exempt: `NORBIZ_SPEC.md` §15 is explicit that a crawler
must never get a 429 on the one request we most want to succeed.

This is intentionally a single in-process bucket dict, not a shared store —
fine for one worker process; a multi-worker deployment would need a shared
backend (Redis, etc.), which is out of scope here.
"""

from __future__ import annotations

import math
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from registry_mcp.core.models import ErrorCode, RegistryError

__all__ = ["EXEMPT_PATHS", "RateLimitMiddleware"]

#: Never rate-limited — see `NORBIZ_SPEC.md` §15.
EXEMPT_PATHS = frozenset({"/", "/llms.txt", "/llms-full.txt", "/server.json"})

_CAPACITY = 60.0
_REFILL_PER_SECOND = _CAPACITY / 60.0


class _Bucket:
    __slots__ = ("tokens", "updated_at")

    def __init__(self, tokens: float, updated_at: float) -> None:
        self.tokens = tokens
        self.updated_at = updated_at


def client_ip(request: Request) -> str:
    """The caller's IP: first hop of ``X-Forwarded-For``, else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client is not None else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """60 requests/minute per client IP, in-process token bucket."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        capacity: float = _CAPACITY,
        refill_per_second: float = _REFILL_PER_SECOND,
    ) -> None:
        super().__init__(app)
        self._capacity = capacity
        self._refill = refill_per_second
        self._buckets: dict[str, _Bucket] = {}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        ip = client_ip(request)
        now = time.monotonic()
        bucket = self._buckets.get(ip)
        if bucket is None:
            bucket = _Bucket(self._capacity, now)
            self._buckets[ip] = bucket
        else:
            elapsed = now - bucket.updated_at
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill)
            bucket.updated_at = now

        if bucket.tokens < 1.0:
            deficit = 1.0 - bucket.tokens
            retry_after = max(1, math.ceil(deficit / self._refill))
            err = RegistryError(
                ErrorCode.RATE_LIMITED,
                "You exceeded 60 requests/minute for this service.",
                hint=(
                    f"Back off for {retry_after} seconds, then batch your calls instead of "
                    "retrying immediately or in parallel."
                ),
                details={"retry_after": retry_after},
            )
            return JSONResponse(
                status_code=err.http_status,
                content=err.to_dict(),
                headers={"Retry-After": str(retry_after)},
            )

        bucket.tokens -= 1.0
        return await call_next(request)
