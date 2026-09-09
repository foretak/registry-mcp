"""Tests for `registries/no/peppol.py` and the `include=["peppol"]` attachment
it serves (`DECISIONS.md` D-029(b), amended in full by D-046).

Like `tests/test_gleif.py`, this attachment's tests mostly call
`Registry.peppol(id)` directly rather than going through `Registry.lookup_with`
— it proves the resolver/HTTP/mapping machinery in isolation. The handful of
tests that must exercise `lookup_with` (the default-lookup-costs-nothing
test, the failed-whole-attachment test, and the `bad_request` tests) do so
explicitly and say why in their own docstrings.

**The DNS seam.** `respx` mocks `httpx` and cannot see `dnspython` at all, so
every test monkeypatches `registry_mcp.registries.no.peppol._resolve_smp_base`
directly — the one module-level function `tasks/T43.md` requires for exactly
this reason — via the `_stub_resolve` helper below. The HTTPS steps (the SMP
GET and the Peppol Directory GET) are respx-mocked as usual, against the
seven fixtures recorded in `tests/fixtures/` (see `tests/fixtures/README.md`
for how each was obtained).

Numbered comments below (`# T1`, `# T2`, ...) tie each test back to
`tasks/T43.md` §F's eighteen-item list, in order, so a reviewer can check
the list off directly.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx
import pytest
import respx

from registry_mcp.core import cache
from registry_mcp.core.models import CompanyReport, ErrorCode, PeppolParticipant, RegistryError
from registry_mcp.core.registry import get_registry
from registry_mcp.registries.no import BrregRegistry, peppol
from registry_mcp.registries.no import client as no_client_module
from registry_mcp.registries.no import rules as no_rules_module

FIXTURES = Path(__file__).parent / "fixtures"


def _no_registry() -> BrregRegistry:
    """`peppol()` is concrete on `BrregRegistry`, not on the abstract
    `Registry` `get_registry()` is typed to return -- the same `cast`
    `tests/test_client_gb.py`'s `charges()` tests use for the identical
    reason."""
    return cast(BrregRegistry, get_registry("NO"))


def _nxdomain() -> dns.resolver.NXDOMAIN:
    return dns.resolver.NXDOMAIN()  # type: ignore[no-untyped-call]


def _dns_timeout() -> dns.exception.Timeout:
    return dns.exception.Timeout()  # type: ignore[no-untyped-call]


def _load_json(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


def _load_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


EQUINOR_ENTITY = _load_json("brreg_923609016.json")
EQUINOR_SERVICE_GROUP = _load_bytes("peppol_smp_923609016.xml")
CONTA_SERVICE_GROUP = _load_bytes("peppol_smp_837056942.xml")
SMP_404_BODY = _load_bytes("peppol_smp_404.xml")
DIRECTORY_EQUINOR_MATCH = _load_json("peppol_directory_923609016.json")
DIRECTORY_EMPTY = _load_json("peppol_directory_empty.json")

_INVOICE_ID = (
    "busdox-docid-qns::urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice"
    "##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1"
)


def _stub_resolve(
    *, returns: str | None = None, raises: BaseException | None = None
) -> Callable[[str], Awaitable[str | None]]:
    """A drop-in replacement for `peppol._resolve_smp_base`, monkeypatched
    onto the module-level seam `tasks/T43.md` requires. Exactly one of
    `returns`/`raises` is meaningful per call."""

    async def _inner(fqdn: str) -> str | None:
        if raises is not None:
            raise raises
        return returns

    return _inner


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    monkeypatch.delenv("REGISTRY_MCP_CACHE_TTL_SECONDS", raising=False)
    yield


@pytest.fixture(autouse=True)
async def _reset_peppol_client() -> AsyncIterator[None]:
    peppol._client = None
    yield
    await peppol.aclose()


# ---------------------------------------------------------------------------
# T1 -- the two hash vectors, offline, plus the qualified-id trap
# ---------------------------------------------------------------------------


def test_hash_label_matches_the_two_worked_examples_and_the_scheme_is_a_separate_label() -> (
    None
):
    """Peppol SML v1.3.0's own worked example, and Equinor's, reproduced
    byte for byte (DECISIONS.md D-046(c)) -- offline, no network, no
    dependency beyond stdlib hashing/encoding inside `_hash_label` itself."""
    assert (
        peppol._hash_label("0010:5798000000001")
        == "XUKHFQABQZIKI3YKVR2FHR4SNFA3PF5VPQ6K4TONV3LMVSY5ARVQ"
    )
    assert (
        peppol._hash_label("0192:923609016")
        == "XQK4T3FMTEZDUY5BOVJMTNAQ45N7E4TIBYHWFPGOT75BSP7UYG2A"
    )
    # The hash is over the identifier *value* only -- the qualified form
    # (with the "iso6523-actorid-upis::" scheme prefixed) must hash to a
    # different label, or a caller who queried the wrong string would get a
    # plausible-looking wrong answer instead of a loud failure.
    assert peppol._hash_label("iso6523-actorid-upis::0192:923609016") != peppol._hash_label(
        "0192:923609016"
    )


def test_naptr_fqdn_uses_the_hash_label_the_scheme_and_the_zone() -> None:
    assert peppol._naptr_fqdn("0192:923609016") == (
        "XQK4T3FMTEZDUY5BOVJMTNAQ45N7E4TIBYHWFPGOT75BSP7UYG2A."
        "iso6523-actorid-upis.participant.sml.prod.tech.peppol.org"
    )


# ---------------------------------------------------------------------------
# T17 -- the zone constant and the query type, pinned statically
# ---------------------------------------------------------------------------


def test_sml_zone_and_scheme_constants_are_pinned() -> None:
    """One static test, so a later edit to either is deliberate (`tasks/T43.md`
    test 17). The query *type* (NAPTR) is exercised, not merely asserted, by
    `test_resolve_smp_base_queries_naptr_records` below -- both are pinned so
    a later edit to either the zone string or the rdtype argument is caught
    somewhere."""
    assert peppol._SML_ZONE == "participant.sml.prod.tech.peppol.org"
    assert peppol._SCHEME == "iso6523-actorid-upis"


async def test_resolve_smp_base_queries_naptr_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_resolve_smp_base` is the one seam allowed to call `dnspython` at
    all -- assert it asks for NAPTR records, via `dns.asyncresolver`, never
    the synchronous `dns.resolver` module's blocking equivalent."""
    calls: list[tuple[str, str]] = []

    async def _fake_resolve(qname: str, rdtype: str, **kwargs: Any) -> dns.resolver.Answer:
        calls.append((qname, rdtype))
        raise _nxdomain()

    monkeypatch.setattr(dns.asyncresolver, "resolve", _fake_resolve)
    with pytest.raises(dns.resolver.NXDOMAIN):
        await peppol._resolve_smp_base("example.participant.sml.prod.tech.peppol.org")
    assert calls == [("example.participant.sml.prod.tech.peppol.org", "NAPTR")]


# ---------------------------------------------------------------------------
# T2 -- the happy path (Equinor, via ELMA)
# ---------------------------------------------------------------------------


@respx.mock
async def test_happy_path_equinor_via_elma(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(returns="https://smp.elma-smp.no/")
    )
    respx.get(
        "https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016"
    ).mock(return_value=httpx.Response(200, content=EQUINOR_SERVICE_GROUP))

    block = await _no_registry().peppol("923609016")

    assert block.registered is True
    assert len(block.document_types) == 17
    assert block.can_receive_invoice is True
    assert block.smp_url == "https://smp.elma-smp.no/"
    assert block.provenance.source is not None
    assert "smp.elma-smp.no" in block.provenance.source
    assert block.provenance.license == peppol._LICENSE
    assert block.participant_id == "0192:923609016"
    assert block.provenance.cached is False


# ---------------------------------------------------------------------------
# T3 -- include=["peppol"] on lookup_company; default lookup asks nothing
# ---------------------------------------------------------------------------


@respx.mock
async def test_include_peppol_returns_the_block_through_lookup_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(returns="https://smp.elma-smp.no/")
    )
    respx.get(f"{no_client_module.BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR_ENTITY)
    )
    respx.get("https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016").mock(
        return_value=httpx.Response(200, content=EQUINOR_SERVICE_GROUP)
    )

    report = await get_registry("NO").lookup_with("923609016", ["peppol"])

    assert isinstance(report, CompanyReport)
    assert report.peppol is not None
    assert report.peppol.registered is True
    assert len(report.peppol.document_types) == 17


@respx.mock
async def test_default_lookup_makes_no_peppol_requests_and_peppol_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_route = respx.get(f"{no_client_module.BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR_ENTITY)
    )
    directory_route = respx.get(peppol._DIRECTORY_URL).mock(
        return_value=httpx.Response(200, json=DIRECTORY_EQUINOR_MATCH)
    )

    def _fail_if_called(fqdn: str) -> Any:
        raise AssertionError("the SML must not be resolved on a default lookup")

    monkeypatch.setattr(peppol, "_resolve_smp_base", _fail_if_called)

    report = await get_registry("NO").lookup_with("923609016")

    assert entity_route.call_count == 1
    assert directory_route.call_count == 0
    assert report.peppol is None


# ---------------------------------------------------------------------------
# T4 -- the non-ELMA host: the SMP base URL is data, never a constant
# ---------------------------------------------------------------------------


@respx.mock
async def test_non_elma_host_is_read_from_the_naptr_not_hardcoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The trap `tasks/T43.md` exists to catch: an implementation that
    hardcodes `smp.elma-smp.no` would either fail to match this respx route
    at all, or (worse) silently call the wrong host. Asserting the *exact
    request URL respx saw* is what makes a hardcoded-host implementation
    fail here rather than in production against the 1-in-43 case
    (`0192:837056942`, `tests/fixtures/peppol_naptr_837056942.json`)."""
    monkeypatch.setattr(peppol, "_resolve_smp_base", _stub_resolve(returns="https://smp.conta.no"))
    route = respx.get("https://smp.conta.no/iso6523-actorid-upis%3A%3A0192%3A837056942").mock(
        return_value=httpx.Response(200, content=CONTA_SERVICE_GROUP)
    )

    block = await _no_registry().peppol("837056942")

    assert route.call_count == 1
    assert str(route.calls.last.request.url) == (
        "https://smp.conta.no/iso6523-actorid-upis%3A%3A0192%3A837056942"
    )
    assert block.smp_url == "https://smp.conta.no"
    assert block.provenance.source is not None
    assert "smp.conta.no" in block.provenance.source
    assert "smp.elma-smp.no" not in (block.provenance.source or "")
    assert block.registered is True
    assert len(block.document_types) == 2


def test_service_group_url_joins_both_trailing_slash_forms_correctly() -> None:
    """ELMA's NAPTR URI ends in `/`; Conta's does not. Both must produce
    exactly one `/` before the encoded participant id."""
    trailing = peppol._service_group_url("https://smp.elma-smp.no/", "0192:923609016")
    bare = peppol._service_group_url("https://smp.conta.no", "0192:837056942")
    assert trailing == "https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016"
    assert bare == "https://smp.conta.no/iso6523-actorid-upis%3A%3A0192%3A837056942"
    assert "//iso6523" not in trailing
    assert "no/iso6523" in bare


# ---------------------------------------------------------------------------
# T5 -- NXDOMAIN -> False, and no Directory request at all
# ---------------------------------------------------------------------------


@respx.mock
async def test_nxdomain_is_false_and_no_directory_request_is_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_nxdomain())
    )
    directory_route = respx.get(peppol._DIRECTORY_URL).mock(
        return_value=httpx.Response(200, json=DIRECTORY_EQUINOR_MATCH)
    )

    block = await _no_registry().peppol("999999999")

    assert block.registered is False
    assert block.can_receive_invoice is False
    assert block.smp_url is None
    assert block.document_types == []
    assert directory_route.call_count == 0


# ---------------------------------------------------------------------------
# T6 -- SMP 404 -> False, with smp_url still populated
# ---------------------------------------------------------------------------


@respx.mock
async def test_smp_404_is_false_with_smp_url_populated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(returns="https://smp.elma-smp.no/")
    )
    directory_route = respx.get(peppol._DIRECTORY_URL).mock(
        return_value=httpx.Response(200, json=DIRECTORY_EQUINOR_MATCH)
    )
    respx.get("https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A999999999").mock(
        return_value=httpx.Response(404, content=SMP_404_BODY)
    )

    block = await _no_registry().peppol("999999999")

    assert block.registered is False
    assert block.can_receive_invoice is False
    assert block.smp_url == "https://smp.elma-smp.no/"
    # A 404 from the SMP the SML named is already the authoritative answer
    # (DECISIONS.md D-046(a)) -- the Directory is a repair for *our* failure
    # to reach that route, and there is nothing to repair here.
    assert directory_route.call_count == 0


# ---------------------------------------------------------------------------
# T7/T8 -- resolver timeout, then the Directory fallback (hit, then miss)
# ---------------------------------------------------------------------------


@respx.mock
async def test_resolver_timeout_then_directory_hit_is_true_with_the_lag_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_dns_timeout())
    )
    respx.get(peppol._DIRECTORY_URL).mock(return_value=httpx.Response(200, json=DIRECTORY_EQUINOR_MATCH))

    block = await _no_registry().peppol("923609016")

    assert block.registered is True
    assert block.smp_url is None
    assert len(block.document_types) == 12
    assert block.can_receive_invoice is True
    joined_notes = " ".join(block.notes)
    assert "lag" in joined_notes.lower() or "may lag" in joined_notes.lower()
    assert block.provenance.source is not None and "Directory" in block.provenance.source


@respx.mock
async def test_resolver_timeout_then_directory_empty_is_null_but_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_dns_timeout())
    )
    respx.get(peppol._DIRECTORY_URL).mock(return_value=httpx.Response(200, json=DIRECTORY_EMPTY))

    block = await _no_registry().peppol("999999999")

    assert block.registered is None
    assert block.can_receive_invoice is None
    assert block.participant_id == "0192:999999999"
    assert block.smp_url is None
    # Present and successful: this is a *value*, proving the caller got a
    # real PeppolParticipant rather than an exception.
    assert isinstance(block, PeppolParticipant)


# ---------------------------------------------------------------------------
# T9 -- NOERROR with no Meta:SMP record -> null, never False
# ---------------------------------------------------------------------------


@respx.mock
async def test_noerror_no_meta_smp_record_is_null_not_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The middlebox case: `_resolve_smp_base` returns `None` (a NOERROR
    answer with nothing usable), which must never be conflated with the
    definitive NXDOMAIN `False` above."""
    monkeypatch.setattr(peppol, "_resolve_smp_base", _stub_resolve(returns=None))
    respx.get(peppol._DIRECTORY_URL).mock(return_value=httpx.Response(200, json=DIRECTORY_EMPTY))

    block = await _no_registry().peppol("999999999")

    assert block.registered is None
    assert block.registered is not False
    assert block.can_receive_invoice is None


# ---------------------------------------------------------------------------
# T10 -- can_receive_invoice via the Directory: True if present, else None
# (never False)
# ---------------------------------------------------------------------------


@respx.mock
async def test_directory_route_with_invoice_id_present_can_receive_is_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_dns_timeout())
    )
    respx.get(peppol._DIRECTORY_URL).mock(return_value=httpx.Response(200, json=DIRECTORY_EQUINOR_MATCH))

    block = await _no_registry().peppol("923609016")

    assert _INVOICE_ID in block.document_types
    assert block.can_receive_invoice is True


@respx.mock
async def test_directory_route_without_invoice_id_is_none_never_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "version": "1.0",
        "total-result-count": 1,
        "matches": [
            {
                "participantID": {"scheme": "iso6523-actorid-upis", "value": "0192:910000004"},
                "docTypes": [
                    {
                        "scheme": "busdox-docid-qns",
                        "value": (
                            "urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2"
                            "::DespatchAdvice##urn:fdc:peppol.eu:poacc:trns:"
                            "despatch_advice:3::2.1"
                        ),
                    }
                ],
                "entities": [{"name": [{"name": "SYNTHETIC TEST AS"}], "countryCode": "NO"}],
            }
        ],
    }
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_dns_timeout())
    )
    respx.get(peppol._DIRECTORY_URL).mock(return_value=httpx.Response(200, json=payload))

    block = await _no_registry().peppol("910000004")

    assert block.registered is True  # the Directory listed *something*
    assert _INVOICE_ID not in block.document_types
    assert block.can_receive_invoice is None
    assert block.can_receive_invoice is not False


# ---------------------------------------------------------------------------
# T11 -- `contact` never surfaces
# ---------------------------------------------------------------------------


@respx.mock
async def test_directory_contact_field_never_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "version": "1.0",
        "total-result-count": 1,
        "matches": [
            {
                "participantID": {"scheme": "iso6523-actorid-upis", "value": "0192:923609016"},
                "docTypes": [{"scheme": "busdox-docid-qns", "value": "urn:test:doctype::1.0"}],
                "entities": [
                    {
                        "name": [{"name": "EQUINOR ASA"}],
                        "countryCode": "NO",
                        "contacts": [
                            {
                                "type": "technical",
                                "name": "PRIVATE PERSON NAME",
                                "phone": "+47 99 99 99 99",
                                "email": "private.person@example.com",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_dns_timeout())
    )
    respx.get(peppol._DIRECTORY_URL).mock(return_value=httpx.Response(200, json=payload))

    block = await _no_registry().peppol("923609016")

    dumped = json.dumps(block.model_dump(mode="json"))
    assert "PRIVATE PERSON NAME" not in dumped
    assert "private.person@example.com" not in dumped
    assert "+47 99 99 99 99" not in dumped
    assert all("PRIVATE PERSON NAME" not in note for note in block.notes)


def test_no_source_file_reads_or_sends_the_directory_contact_field() -> None:
    """D-046(f) declines the Directory's `contact` block by name: the word
    appears in this file only inside the explanatory comments/docstrings
    saying so (`peppol.py`'s module docstring and two function docstrings) --
    never in code that reads or sends it. Mirrors `tests/test_gleif.py`'s
    `test_no_source_file_reads_gleifs_entity_status_field` for an analogous
    never-touch-this-field invariant."""
    source = Path(peppol.__file__).read_text(encoding="utf-8")
    forbidden = (
        '.get("contact"',
        "['contact']",
        '["contact"]',
        "get('contact'",
        '"contact":',
        "'contact':",
        "contact=",
    )
    hits = [pattern for pattern in forbidden if pattern in source]
    assert hits == []


# ---------------------------------------------------------------------------
# T12 -- cache: true at 24h, false at 1h, null never written; the exact key
# ---------------------------------------------------------------------------


@respx.mock
async def test_true_is_cached_at_the_ok_ttl_under_the_exact_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(returns="https://smp.elma-smp.no/")
    )
    respx.get("https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016").mock(
        return_value=httpx.Response(200, content=EQUINOR_SERVICE_GROUP)
    )

    await _no_registry().peppol("923609016")

    entry = cache.get("NO:brreg:peppol:923609016")
    assert entry is not None
    assert entry.status == "ok"
    assert cache._TTL_BY_KIND["peppol"][0] == 24 * 60 * 60


@respx.mock
async def test_false_is_cached_at_the_empty_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_nxdomain())
    )

    await _no_registry().peppol("999999999")

    entry = cache.get("NO:brreg:peppol:999999999")
    assert entry is not None
    assert entry.status == "not_found"
    assert cache._TTL_BY_KIND["peppol"][1] == 60 * 60


@respx.mock
async def test_null_is_never_written_to_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_dns_timeout())
    )
    respx.get(peppol._DIRECTORY_URL).mock(return_value=httpx.Response(200, json=DIRECTORY_EMPTY))

    block = await _no_registry().peppol("999999999")

    assert block.registered is None
    assert cache.get("NO:brreg:peppol:999999999") is None


@respx.mock
async def test_a_cached_true_is_served_without_a_second_smp_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(returns="https://smp.elma-smp.no/")
    )
    route = respx.get("https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016").mock(
        return_value=httpx.Response(200, content=EQUINOR_SERVICE_GROUP)
    )

    registry = _no_registry()
    first = await registry.peppol("923609016")
    second = await registry.peppol("923609016")

    assert route.call_count == 1
    assert first.provenance.cached is False
    assert second.provenance.cached is True
    assert second.registered == first.registered


def test_naptr_to_smp_binding_is_never_cached_under_any_key() -> None:
    """The composed answer is cached (once for `registered is True`, once
    for `registered is False` -- the two branches in `fetch_peppol`); the
    NAPTR->SMP binding itself is never cached, under any key -- its own TTL
    is 60 seconds and D-046(b)/(d) rule the host must be read fresh on every
    uncached lookup. There is exactly one key-building function
    (`_cache_key`, `NO:brreg:peppol:{orgnr}`) and both `cache.set(` call
    sites use its `cache_key` local, which this test pins by reading the
    source rather than trying to enumerate every non-call."""
    source = Path(peppol.__file__).read_text(encoding="utf-8")
    assert source.count("cache.set(") == 2
    assert source.count("def _cache_key(") == 1
    assert source.count("cache_key = _cache_key(orgnr)") == 1


# ---------------------------------------------------------------------------
# T13 -- GB/SE reject peppol as bad_request; list_countries shows it for NO
# only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("country", ["GB", "SE"])
async def test_gb_and_se_reject_peppol_include_as_bad_request(country: str) -> None:
    registry = get_registry(country)
    assert "peppol" not in registry.effective_includes

    with pytest.raises(RegistryError) as excinfo:
        await registry.lookup_with("x", ["peppol"])
    assert excinfo.value.code is ErrorCode.BAD_REQUEST
    assert "peppol" in excinfo.value.details["unknown"]
    assert "peppol" not in excinfo.value.details["allowed"]


def test_list_countries_shows_peppol_for_no_only() -> None:
    assert "peppol" in get_registry("NO").country_info().supported_includes
    assert "peppol" not in get_registry("GB").country_info().supported_includes
    assert "peppol" not in get_registry("SE").country_info().supported_includes


# ---------------------------------------------------------------------------
# T14 -- a whole-attachment failure leaves the block absent, with a note, and
# the lookup still succeeds
# ---------------------------------------------------------------------------


@respx.mock
async def test_whole_attachment_failure_leaves_the_block_absent_with_a_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both routes fail outright -- the SML with a non-NXDOMAIN exception,
    then the Directory fallback with an exhausted-retry 5xx -- so there is
    nothing at all to build even a `null` block from. `Registry.peppol`
    raises `RegistryError(UPSTREAM_ERROR)`, and `lookup_with` turns that
    into an absent block plus a `notes` sentence, never a failed lookup
    (DECISIONS.md D-042(b))."""
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(raises=_dns_timeout())
    )
    respx.get(f"{no_client_module.BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR_ENTITY)
    )
    respx.get(peppol._DIRECTORY_URL).mock(side_effect=[httpx.Response(500), httpx.Response(500)])

    report = await get_registry("NO").lookup_with("923609016", ["peppol"])

    assert report.name == "EQUINOR ASA"
    assert report.peppol is None
    assert any("peppol" in note for note in report.notes)


# ---------------------------------------------------------------------------
# T15 -- no cap, no truncation
# ---------------------------------------------------------------------------


def _synthetic_service_group(count: int) -> bytes:
    """Not a live recording -- built by hand, the way `tests/test_gleif.py`'s
    `_synthetic_record` is, for a scenario `tasks/T48-recon.md` measured the
    *count* of (one 26-doctype participant in a 500-participant sample) but
    did not capture the raw XML for."""
    hrefs = "".join(
        '<ns2:ServiceMetadataReference href="https://smp.example.test/'
        f'{quote("iso6523-actorid-upis::0192:910000004", safe="")}/services/'
        f'{quote(f"busdox-docid-qns::urn:test:synthetic:{i}::1.0", safe="")}"/>'
        for i in range(count)
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ns2:ServiceGroup xmlns:ns2="http://busdox.org/serviceMetadata/publishing/1.0/">'
        f"<ns2:ServiceMetadataReferenceCollection>{hrefs}</ns2:ServiceMetadataReferenceCollection>"
        "</ns2:ServiceGroup>"
    )
    return xml.encode("utf-8")


def test_26_document_types_no_cap_no_truncation() -> None:
    document_types = peppol._document_types_from_service_group(_synthetic_service_group(26))
    assert len(document_types) == 26
    assert document_types[0] == "busdox-docid-qns::urn:test:synthetic:0::1.0"
    assert document_types[25] == "busdox-docid-qns::urn:test:synthetic:25::1.0"


@respx.mock
async def test_26_document_types_survive_the_full_fetch_uncapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peppol, "_resolve_smp_base", _stub_resolve(returns="https://smp.example.test/")
    )
    respx.get(
        "https://smp.example.test/iso6523-actorid-upis%3A%3A0192%3A910000004"
    ).mock(return_value=httpx.Response(200, content=_synthetic_service_group(26)))

    block = await _no_registry().peppol("910000004")

    assert len(block.document_types) == 26


# ---------------------------------------------------------------------------
# T16 -- rules_markdown() and company_deadlines
# ---------------------------------------------------------------------------


def test_rules_markdown_carries_the_2027_2030_prose() -> None:
    markdown = no_rules_module.rules_markdown()
    assert "1 January 2027" in markdown
    assert "1 January 2030" in markdown
    assert "50,000" in markdown
    assert "finansvirksomhet" in markdown
    assert "Prop. 44 L" in markdown
    assert "oppdatert informasjonen" not in markdown


async def test_company_deadlines_for_a_norwegian_entity_emits_no_e_invoicing_deadline(
    sample_report: CompanyReport, today: date
) -> None:
    registry = get_registry("NO")
    deadlines = registry.deadlines(sample_report, today)
    kinds = {d.kind for d in deadlines}
    assert "peppol" not in kinds
    assert not any("e-invoic" in d.kind.lower() or "peppol" in d.kind.lower() for d in deadlines)


def test_peppol_is_not_a_deadline_include() -> None:
    """D-043(j)/D-046(h): `peppol` can never appear in `DEADLINE_INCLUDES`,
    regardless of what any country declares -- checked directly against the
    committed set, the same assertion `tests/test_attachments.py::
    test_deadline_includes_is_filings_only_and_never_peppol` already makes
    generically. Not a duplicate: that test guards the constant in
    `core/registry.py`; this one guards this task's own footprint against
    ever adding to it."""
    from registry_mcp.core.registry import DEADLINE_INCLUDES

    assert "peppol" not in DEADLINE_INCLUDES


# ---------------------------------------------------------------------------
# T18 -- REST <-> MCP parity: covered by the existing whole-document parity
# tests, not duplicated here.
# ---------------------------------------------------------------------------

# `tests/test_mcp.py::test_rest_and_mcp_lookup_company_are_identical` diffs
# every field of a plain (no-include) NO `CompanyReport` between the REST and
# MCP surfaces, `peppol` included -- it compares the two surfaces' dumps key
# for key without naming any one field, so a new field on `CompanyReport`
# (this task's `peppol`) is covered by construction, not by an edit to that
# test. Confirmed by inspection, not duplicated here per `tasks/T43.md`
# test 18's own instruction.


# ---------------------------------------------------------------------------
# CompanyReport.peppol default (D-004: always present as a field, None on
# every report that did not request it)
# ---------------------------------------------------------------------------


def test_company_report_peppol_field_defaults_to_none() -> None:
    report = CompanyReport(country="NO", registry="brreg", id="923609016", name="X")
    assert report.peppol is None
    assert "peppol" in CompanyReport.model_fields


# ---------------------------------------------------------------------------
# can_receive_invoice table -- membership, not substring (DECISIONS.md
# D-046(e))
# ---------------------------------------------------------------------------


def test_can_receive_invoice_table_is_exact_membership_not_a_substring() -> None:
    close_but_not_exact = _INVOICE_ID + "-EXTRA-SUFFIX-NOT-IN-THE-TABLE"
    assert peppol._can_receive_invoice(True, [close_but_not_exact], via_directory=False) is False
    assert peppol._can_receive_invoice(True, [_INVOICE_ID], via_directory=False) is True


def test_credit_note_id_alone_does_not_satisfy_can_receive_invoice() -> None:
    """The CreditNote id is deliberately absent from the committed table
    (DECISIONS.md D-046(e)): the flag is named for the invoice."""
    credit_note_id = _INVOICE_ID.replace("Invoice", "CreditNote")
    assert credit_note_id not in peppol._INVOICE_DOCUMENT_TYPE_IDS
    assert (
        peppol._can_receive_invoice(True, [credit_note_id], via_directory=False) is False
    )


# ---------------------------------------------------------------------------
# Live done-check (network; excluded from CI) -- formalises the three
# end-to-end fetch_peppol() calls made by hand while building this task,
# each recorded in the T43 C commit message.
# ---------------------------------------------------------------------------


@pytest.mark.live
async def test_98_live_equinor_via_elma_end_to_end() -> None:
    """Real DNS (this machine's own resolver), then a real HTTPS GET
    against whatever host the SML actually names -- no respx, no DNS stub."""
    block = await _no_registry().peppol("923609016")
    assert block.registered is True
    assert len(block.document_types) == 17
    assert block.can_receive_invoice is True
    assert block.smp_url == "https://smp.elma-smp.no/"


@pytest.mark.live
async def test_99_live_non_elma_participant_end_to_end() -> None:
    """The 1-in-43 case, live: the SML must name `smp.conta.no`, not ELMA,
    and the join (no trailing slash on this host) must produce a real,
    fetchable URL. This is the test that would fail first against a
    hardcoded-ELMA implementation -- not in a mock, against the network."""
    block = await _no_registry().peppol("837056942")
    assert block.registered is True
    assert block.smp_url == "https://smp.conta.no"
    assert block.provenance.source is not None
    assert "smp.conta.no" in block.provenance.source
    assert "smp.elma-smp.no" not in (block.provenance.source or "")


@pytest.mark.live
async def test_99_live_synthetic_negative_nxdomains() -> None:
    """`999999999` (synthetic, MOD11-valid, never a real company) NXDOMAINs
    at the SML live -- the negative path, on the real network."""
    block = await _no_registry().peppol("999999999")
    assert block.registered is False
    assert block.can_receive_invoice is False
    assert block.smp_url is None
