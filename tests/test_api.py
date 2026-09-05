"""Tests for `api/main.py`, `api/errors.py` and `api/ratelimit.py` (T06).

The Norwegian registry's HTTP is mocked with `respx` against
`tests/fixtures/brreg_923609016.json`, the same pattern `tests/test_client_no.py`
(T03) uses — these tests exercise the REST surface end to end, not the client
directly.

Deadlines and validate return `core.models.DeadlineReport` / `ValidationResult`
built by `Registry.deadline_report` / `Registry.validate` (`DECISIONS.md`
D-010) — an invalid identifier is HTTP 200 with `valid: false`, not an error.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from registry_mcp import __version__
from registry_mcp.api import ratelimit as ratelimit_module
from registry_mcp.api.main import app
from registry_mcp.registries.no import client as client_module

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = client_module.BASE_URL


def _load_fixture(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


EQUINOR = _load_fixture("brreg_923609016.json")

_ip_counter = iter(range(2, 250))


@pytest.fixture
def ip() -> str:
    """A fresh fake client IP per test, so the shared rate-limit bucket never
    lets one test's traffic starve another's (the app, and its middleware
    instance, are module-level singletons shared across the whole file)."""
    return f"203.0.113.{next(_ip_counter)}"


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    monkeypatch.delenv("REGISTRY_MCP_CACHE_TTL_SECONDS", raising=False)
    yield


@pytest.fixture(autouse=True)
async def _reset_http_client() -> AsyncIterator[None]:
    client_module._client = None
    yield
    await client_module.aclose()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@respx.mock
def test_company_lookup_valid(client: TestClient, ip: str) -> None:
    respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    resp = client.get("/v1/NO/company/923609016", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "EQUINOR ASA"
    assert body["id"] == "923609016"
    assert body["country"] == "NO"
    assert body["registry"] == "brreg"
    assert body["cached"] is False


def test_company_lookup_invalid_id(client: TestClient, ip: str) -> None:
    resp = client.get("/v1/NO/company/923609017", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == "invalid_id"
    assert err["hint"]
    assert "search_company" in err["hint"]


@respx.mock
def test_company_lookup_not_found(client: TestClient, ip: str) -> None:
    respx.get(f"{BASE_URL}/enheter/999999999").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE_URL}/underenheter/999999999").mock(return_value=httpx.Response(404))
    resp = client.get("/v1/NO/company/999999999", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "not_found"
    assert "search_company" in err["hint"]


def test_unsupported_country(client: TestClient, ip: str) -> None:
    resp = client.get("/v1/ZZ/company/1", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "unsupported_country"
    assert "/v1/countries" in err["hint"] or "list_countries" in err["hint"]


def test_validate_valid(client: TestClient, ip: str) -> None:
    resp = client.get("/v1/NO/validate/923609016", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["normalized"] == "923609016"
    assert body["formatted"] == "923 609 016"
    assert body["id_scheme"] == "organisasjonsnummer"
    assert body["hint"] is None


def test_validate_invalid_is_200_not_error(client: TestClient, ip: str) -> None:
    # D-010: an invalid identifier is a normal 200 answering "is it valid?",
    # not a raised RegistryError — the one deliberate exception to D-007.
    resp = client.get("/v1/NO/validate/923609017", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["normalized"] is None
    assert body["formatted"] is None
    assert body["reason"]
    assert body["hint"]
    assert "search_company" in body["hint"]


@respx.mock
def test_search(client: TestClient, ip: str) -> None:
    envelope = {
        "_embedded": {"enheter": [EQUINOR]},
        "page": {"size": 1, "totalElements": 1, "totalPages": 1, "number": 0},
    }
    respx.get(f"{BASE_URL}/enheter").mock(return_value=httpx.Response(200, json=envelope))
    resp = client.get(
        "/v1/NO/search", params={"q": "equinor", "limit": 1}, headers={"X-Forwarded-For": ip}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["hits"][0]["id"] == "923609016"
    assert body["hint"]


def test_search_missing_q_is_bad_request(client: TestClient, ip: str) -> None:
    resp = client.get("/v1/NO/search", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


def test_search_limit_out_of_range_is_bad_request(client: TestClient, ip: str) -> None:
    resp = client.get(
        "/v1/NO/search", params={"q": "equinor", "limit": 0}, headers={"X-Forwarded-For": ip}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


@respx.mock
def test_deadlines(client: TestClient, ip: str) -> None:
    respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    resp = client.get(
        "/v1/NO/company/923609016/deadlines",
        params={"today": "2026-01-15"},
        headers={"X-Forwarded-For": ip},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["today"] == "2026-01-15"
    assert body["company_id"] == "923609016"
    assert body["company_name"] == "EQUINOR ASA"
    assert len(body["deadlines"]) > 0
    assert body["deadlines"][0]["kind"] == "shareholder_register_statement"
    assert any("calendar-year" in n for n in body["notes"])


@respx.mock
def test_deadlines_default_today(client: TestClient, ip: str) -> None:
    respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    resp = client.get("/v1/NO/company/923609016/deadlines", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 200
    assert "today" in resp.json()


def test_deadlines_bad_today_is_bad_request(client: TestClient, ip: str) -> None:
    resp = client.get(
        "/v1/NO/company/923609016/deadlines",
        params={"today": "not-a-date"},
        headers={"X-Forwarded-For": ip},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


def test_countries(client: TestClient, ip: str) -> None:
    resp = client.get("/v1/countries", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 200
    codes = {row["country"] for row in resp.json()["countries"]}
    assert codes == {"GB", "NO"}  # XX is a stub, hidden by default (D-008)


def test_health(client: TestClient, ip: str) -> None:
    resp = client.get("/health", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "version": __version__, "countries": ["GB", "NO"]}


# ---------------------------------------------------------------------------
# Static routes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "content_type_prefix"),
    [
        ("/", "text/html"),
        ("/llms.txt", "text/plain"),
        ("/llms-full.txt", "text/plain"),
        ("/server.json", "application/json"),
        ("/robots.txt", "text/plain"),
        ("/.well-known/mcp/server-card.json", "application/json"),
    ],
)
def test_static_routes_200(
    client: TestClient, ip: str, path: str, content_type_prefix: str
) -> None:
    resp = client.get(path, headers={"X-Forwarded-For": ip})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(content_type_prefix)
    assert "charset=utf-8" in resp.headers["content-type"].lower()
    assert len(resp.text) > 0


def test_robots_txt_allows_everything(client: TestClient, ip: str) -> None:
    resp = client.get("/robots.txt", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 200
    assert resp.text == "User-agent: *\nAllow: /\n"


def test_well_known_server_card_version_matches_package(client: TestClient, ip: str) -> None:
    """Backlog item 6(a): the Smithery-style server card is regenerated from
    the real server, not hand-maintained — its `serverInfo.version` must
    never drift from the package version being served."""
    resp = client.get(
        "/.well-known/mcp/server-card.json", headers={"X-Forwarded-For": ip}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["serverInfo"]["version"] == __version__
    assert {t["name"] for t in body["tools"]} == {
        "lookup_company",
        "search_company",
        "company_deadlines",
        "validate_company_id",
        "list_countries",
    }


def test_static_routes_never_rate_limited(client: TestClient) -> None:
    # All from the *same* IP, well past the 60/minute budget any real route
    # would enforce (`NORBIZ_SPEC.md` §15).
    for _ in range(70):
        resp = client.get("/llms.txt", headers={"X-Forwarded-For": "203.0.113.250"})
        assert resp.status_code == 200


def test_unknown_route_is_404_naming_llms_txt(client: TestClient, ip: str) -> None:
    resp = client.get("/this-is-not-a-route", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert "llms.txt" in err["hint"]


# ---------------------------------------------------------------------------
# X-Request-ID
# ---------------------------------------------------------------------------


def test_request_id_header_present_when_absent(client: TestClient, ip: str) -> None:
    resp = client.get("/health", headers={"X-Forwarded-For": ip})
    request_id = resp.headers.get("x-request-id")
    assert request_id
    uuid.UUID(request_id)  # a generated id is a real UUID4, not an echo of nothing


def test_request_id_header_echoes_incoming(client: TestClient, ip: str) -> None:
    resp = client.get(
        "/health", headers={"X-Forwarded-For": ip, "X-Request-ID": "caller-chosen-id-123"}
    )
    assert resp.headers["x-request-id"] == "caller-chosen-id-123"


def test_request_id_header_present_on_error(client: TestClient, ip: str) -> None:
    # Outermost middleware (added after RateLimitMiddleware) must still see
    # a 400/404/etc — the header is not a happy-path-only feature.
    resp = client.get("/v1/ZZ/company/1", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 404
    assert resp.headers.get("x-request-id")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class _FrozenClock:
    """A stand-in for the `time` module exposing only `monotonic()`, pinned to
    a constant. Assigning this over `ratelimit`'s module-level `time` name
    (not the real stdlib `time` module — see the test below) makes the
    limiter's refill exactly zero for every request, so its 60-capacity
    bucket depletes on pure request count with no dependence on how long the
    61 real HTTP round trips (each one now also a `core/log.py::log_call`
    SQLite write, D-006/T08) happen to take on the machine running the test.
    """

    def monotonic(self) -> float:
        return 0.0


def test_rate_limit_429_shape(client: TestClient, ip: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # This test was flaky (`PROGRESS.md`'s T13 note, reproduced independently
    # of T13's own changes): `RateLimitMiddleware` refills its per-IP bucket
    # by elapsed *wall-clock* time (`api/ratelimit.py`'s `time.monotonic()`),
    # so 61 real, sequential requests occasionally took just long enough
    # (disk I/O, scheduler jitter, a slow CI host) for the bucket to refill a
    # sliver of a token — enough, once in a while, for the 61st request to
    # come back 200 instead of the expected 429. Freezing the clock removes
    # time from the equation entirely: with refill pinned at zero, exactly 60
    # of 60.0 capacity are consumable before the 61st is always the first
    # rejection, deterministically. `ip` (this file's per-test IP fixture,
    # never reused) also rules out a shared bucket carrying over state from
    # another test — `RateLimitMiddleware`'s bucket dict lives on the single
    # instance attached to the `app` singleton for the whole test session.
    monkeypatch.setattr(ratelimit_module, "time", _FrozenClock())

    responses = [client.get("/v1/countries", headers={"X-Forwarded-For": ip}) for _ in range(61)]
    last = responses[-1]
    assert last.status_code == 429
    assert "Retry-After" in last.headers
    err = last.json()["error"]
    assert err["code"] == "rate_limited"
    assert err["hint"]


def test_request_id_header_present_on_rate_limit(
    client: TestClient, ip: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `RequestIDMiddleware` is added after `RateLimitMiddleware`, making it
    # the outermost of the two (Starlette's `add_middleware` prepends) — it
    # must see a 429 response too, not only ones that reach a route handler.
    # Same frozen-clock technique as `test_rate_limit_429_shape` above, for
    # the same reason: a real-time refill makes this flaky.
    monkeypatch.setattr(ratelimit_module, "time", _FrozenClock())
    responses = [client.get("/v1/countries", headers={"X-Forwarded-For": ip}) for _ in range(61)]
    last = responses[-1]
    assert last.status_code == 429
    assert last.headers.get("x-request-id")


# ---------------------------------------------------------------------------
# Unhandled exceptions never leak a traceback
# ---------------------------------------------------------------------------


def test_internal_error_has_no_traceback_in_body(ip: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(country: str, *, include_stubs: bool | None = None) -> Any:
        raise ValueError("boom")

    monkeypatch.setattr("registry_mcp.api.main.get_registry", _boom)
    # `TestClient`'s default `raise_server_exceptions=True` re-raises whatever
    # escaped the ASGI app to the test itself, bypassing our own `Exception`
    # handler's response entirely — this test is specifically about what a
    # real client over the wire receives, so it needs that off.
    with TestClient(app, raise_server_exceptions=False) as unsafe_client:
        resp = unsafe_client.get("/v1/NO/company/923609016", headers={"X-Forwarded-For": ip})
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["hint"]
    assert "Traceback" not in resp.text
    assert "boom" not in resp.text


# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------


def test_openapi_has_descriptions_on_every_path() -> None:
    schema = app.openapi()
    assert schema["info"]["title"] == "registry-mcp"
    assert schema["info"]["version"] == __version__
    found_any = False
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            found_any = True
            assert operation.get("summary"), f"{method.upper()} {path} has no summary"
            description = operation.get("description", "")
            assert len(description) > 20, f"{method.upper()} {path} has no real description"
            assert operation.get("tags"), f"{method.upper()} {path} has no tag"
            responses = operation.get("responses", {})
            ok_response = responses.get("200", {})
            content = ok_response.get("content", {}).get("application/json", {})
            assert "example" in content or "examples" in content, (
                f"{method.upper()} {path} has no example"
            )
    assert found_any
    # The static discovery routes are deliberately excluded from the schema
    # (`include_in_schema=False`) — they are not part of the versioned data
    # API these docs describe.
    for hidden in (
        "/",
        "/llms.txt",
        "/llms-full.txt",
        "/server.json",
        "/robots.txt",
        "/.well-known/mcp/server-card.json",
    ):
        assert hidden not in schema["paths"]
