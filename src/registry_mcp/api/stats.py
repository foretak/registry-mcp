"""`GET /v1/stats` — usage stats behind an admin key (`NORBIZ_SPEC.md` §11, T08).

Mounted on the real app via `app.include_router(stats_router)` in
`api/main.py`. `include_in_schema=False`: this is an admin/debugging
endpoint, not part of the versioned public data API `/openapi.json`
describes (the same reasoning `api/main.py`'s four static discovery routes
already use).

Auth: `?key=` must equal the `REGISTRY_MCP_ADMIN_KEY` env var. Missing key,
wrong key, or the env var being unset at all -> 403. There is deliberately no
"is a key configured" leak in the response — the same 403 covers every case
so a caller cannot distinguish "wrong key" from "no key configured".

Error body: `DECISIONS.md` D-007's `{"error": {...}}` envelope, built from
`core.models.RegistryError` exactly like `api/errors.py` does for `main.py`'s
routes. `core.models.ErrorCode` has **no `forbidden` member** (checked: only
`invalid_id`, `not_found`, `unsupported_country`, `upstream_error`,
`upstream_timeout`, `rate_limited`, `bad_request`, `not_implemented`,
`internal_error` exist) — per this task's instructions, the closest existing
code is used instead: `ErrorCode.BAD_REQUEST`, with the HTTP status forced to
403 via `RegistryError(..., http_status=403)`. The response is built directly
in this route (not via `install_error_handlers`) because this router may be
mounted on an app that hasn't installed those handlers — e.g. the throwaway
`FastAPI()` test apps `tests/test_stats.py` uses.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from registry_mcp.core import stats as stats_module
from registry_mcp.core.models import ErrorCode, RegistryError

__all__ = ["stats_router"]

_ADMIN_KEY_ENV = "REGISTRY_MCP_ADMIN_KEY"

stats_router = APIRouter()


@stats_router.get("/v1/stats", include_in_schema=False)
def get_stats(key: str | None = None) -> JSONResponse:
    """Return `core/stats.py::summary()` when `key` matches; else a 403 envelope."""
    admin_key = os.environ.get(_ADMIN_KEY_ENV, "")
    if not admin_key or key != admin_key:
        err = RegistryError(
            ErrorCode.BAD_REQUEST,
            "Missing or incorrect stats key.",
            hint=(
                f"Pass the correct value as ?key= (see the {_ADMIN_KEY_ENV} env var on "
                "the server). This endpoint is not publicly readable."
            ),
            http_status=403,
        )
        return JSONResponse(status_code=err.http_status, content=err.to_dict())
    return JSONResponse(content=stats_module.summary())
