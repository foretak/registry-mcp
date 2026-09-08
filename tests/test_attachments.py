"""Tests for R-5's attachment machinery: `SourceRef`, `Registry.supported_includes`
and `Registry.lookup_with` (`DECISIONS.md` D-026(c), D-041(b),(c), D-042(b),(d)).

No country ships an attachment yet (D-042(g) — this task ships the machinery, not
a payload; the LEI, GB filing history/charges (T37) and everything after it are
separate tasks). Every test below either exercises the real `XX` example
registry — which correctly declares no attachments, since `Registry.
supported_includes` defaults to an empty set — or a small test-local fake
registry that declares one or two, standing in for a country module that does
not exist yet. Each fake subclasses the real `ExampleRegistry` (`type(
example_registry)`) so it inherits a working `validate_id`/`search`/
`deadlines` for free, exactly as `test_interface.py`'s `CaveatRegistry` does;
none of these fakes are ever `register()`-ed, so they cannot leak into
`list_countries()` or any other test.

The fake attachment blocks and the fake report type (`_Widget`,
`_ReportWithAttachments`) stand in for a real attachment model and the field a
real attachment task adds to `CompanyReport` (e.g. the future
`filings: FilingHistory | None`). `_ReportWithAttachments` is a genuine
`CompanyReport` *subclass* — `isinstance` and `model_copy` both treat it as a
`CompanyReport` — so `lookup_with`'s generic "attach the block to the field of
the same name" mechanism is exercised exactly as it will be once a real
attachment lands, without `core/models.py` gaining a field for one it does not
ship today.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ConfigDict, Field

from registry_mcp.core.models import (
    CompanyReport,
    CountryInfo,
    ErrorCode,
    RegistryError,
    SourceRef,
)
from registry_mcp.core.registry import Registry

# ---------------------------------------------------------------------------
# Test doubles — core/models.py gains no field for these (D-042(g))
# ---------------------------------------------------------------------------


class _Widget(BaseModel):
    """Stand-in for a real attachment block, e.g. the future `LeiRecord`."""

    model_config = ConfigDict(extra="forbid")

    items: list[str] = Field(default_factory=list)


class _ReportWithAttachments(CompanyReport):
    """A `CompanyReport` *subclass* carrying two attachment-shaped fields, so
    `lookup_with` has somewhere real to attach to. A genuine `isinstance`
    match for `CompanyReport`; `core/models.py` itself is unchanged."""

    widget: _Widget | None = None
    gadget: _Widget | None = None


def _report(country: str, registry: str, id: str) -> _ReportWithAttachments:
    return _ReportWithAttachments(country=country, registry=registry, id=id, name="Attach Co")


@pytest.fixture
def attach_registry(example_registry: Registry) -> Registry:
    """A fake registry declaring two attachments: `widget` (succeeds, empty
    only when `id == "empty"`) and `gadget` (always fails). Never registered
    globally — instantiated and used directly, like `test_interface.py`'s
    `CaveatRegistry`.
    """

    class _AttachRegistry(type(example_registry)):  # type: ignore[misc]
        country = "XW"
        registry = "example-attach"
        is_stub = True
        supported_includes = frozenset({"widget", "gadget"})

        async def lookup(self, id: str) -> CompanyReport:
            return _report(self.country, self.registry, id)

        async def widget(self, id: str) -> _Widget:
            return _Widget(items=[]) if id == "empty" else _Widget(items=["a", "b"])

        async def gadget(self, id: str) -> _Widget:
            raise RegistryError(
                ErrorCode.UPSTREAM_ERROR,
                "The gadget upstream is unreachable in this test.",
                hint="Retry later.",
                country=self.country,
                registry=self.registry,
            )

    return _AttachRegistry()


# ---------------------------------------------------------------------------
# `SourceRef` — the shape (D-026(c), sharpened by D-041(c))
# ---------------------------------------------------------------------------


def test_source_ref_carries_the_five_provenance_names() -> None:
    """No new vocabulary: the same five names `CompanyReport` already has."""
    ref = SourceRef(
        source="GLEIF Level 1 (gleif.org)",
        source_url="https://api.gleif.org/api/v1/lei-records/X",
        license="CC0 1.0",
        cached=True,
    )
    assert ref.source == "GLEIF Level 1 (gleif.org)"
    assert ref.source_url == "https://api.gleif.org/api/v1/lei-records/X"
    assert ref.license == "CC0 1.0"
    assert ref.cached is True


def test_source_ref_defaults_to_all_none_and_uncached() -> None:
    ref = SourceRef()
    assert ref.source is None
    assert ref.source_url is None
    assert ref.license is None
    assert ref.fetched_at is None
    assert ref.cached is False


def test_source_ref_forbids_unknown_fields() -> None:
    """`extra='forbid'`, the same discipline as every other model (D-004) —
    a typo in a future attachment's provenance fails loudly at construction."""
    with pytest.raises(Exception, match="organisation"):
        SourceRef.model_validate({"organisation": "not a real field"})


# ---------------------------------------------------------------------------
# `Registry.supported_includes` / `CountryInfo.supported_includes` (D-042(d))
# ---------------------------------------------------------------------------


def test_supported_includes_defaults_to_empty(example_registry: Registry) -> None:
    """A country that declares no attachments costs nothing and edits
    nothing — the same default pattern as `requires_api_key` (D-017)."""
    assert example_registry.supported_includes == frozenset()


def test_country_info_carries_empty_supported_includes(example_registry: Registry) -> None:
    info = example_registry.country_info()
    assert isinstance(info, CountryInfo)
    assert info.supported_includes == []


def test_country_info_carries_supported_includes_sorted(attach_registry: Registry) -> None:
    """Sorted, for a stable wire (D-042(d)(1)) — declared as
    `{"gadget", "widget"}`, a set with no guaranteed iteration order."""
    info = attach_registry.country_info()
    assert info.supported_includes == ["gadget", "widget"]


# ---------------------------------------------------------------------------
# `include=[]` default behaviour (D-026(c) done-check: "exactly one upstream
# request")
# ---------------------------------------------------------------------------


async def test_lookup_with_default_include_costs_exactly_one_lookup_call(
    example_registry: Registry,
) -> None:
    calls = 0

    class _CountedRegistry(type(example_registry)):  # type: ignore[misc]
        country = "XS"
        registry = "example-counted"
        is_stub = True
        supported_includes = frozenset({"widget"})

        async def lookup(self, id: str) -> CompanyReport:
            nonlocal calls
            calls += 1
            return _report(self.country, self.registry, id)

        async def widget(self, id: str) -> _Widget:
            return _Widget(items=["a"])

    result = await _CountedRegistry().lookup_with("123")
    assert calls == 1
    assert isinstance(result, _ReportWithAttachments)
    assert result.widget is None
    assert result.notes == []


async def test_lookup_with_empty_include_list_is_equivalent_to_default(
    attach_registry: Registry,
) -> None:
    result = await attach_registry.lookup_with("123", [])
    assert isinstance(result, _ReportWithAttachments)
    assert result.widget is None
    assert result.gadget is None
    assert result.notes == []


# ---------------------------------------------------------------------------
# Unknown include value → `bad_request` (D-026(c), D-042(d)(3)) — never
# silently ignored, never an empty block
# ---------------------------------------------------------------------------


async def test_unknown_include_value_raises_bad_request_naming_allowed_set(
    attach_registry: Registry,
) -> None:
    with pytest.raises(RegistryError) as excinfo:
        await attach_registry.lookup_with("123", ["bogus"])
    err = excinfo.value
    assert err.code is ErrorCode.BAD_REQUEST
    assert err.http_status == 400
    assert "bogus" in err.message
    assert "gadget" in err.hint and "widget" in err.hint
    assert err.details["allowed"] == ["gadget", "widget"]
    assert err.details["unknown"] == ["bogus"]
    assert err.country == "XW"
    assert err.registry == "example-attach"


async def test_unknown_include_value_is_never_silently_dropped_from_a_mixed_list(
    attach_registry: Registry,
) -> None:
    """A mix of one valid and one unknown value still raises (D-011,
    D-042(d)): it must never partially succeed on the good one."""
    with pytest.raises(RegistryError) as excinfo:
        await attach_registry.lookup_with("123", ["widget", "bogus"])
    assert excinfo.value.details["unknown"] == ["bogus"]


async def test_a_country_that_declares_none_rejects_every_include_value(
    example_registry: Registry,
) -> None:
    """The real `XX` stub: `supported_includes` is the default empty set, so
    any `include` value is unknown, and the caller is told so rather than
    silently getting an empty block back."""
    with pytest.raises(RegistryError) as excinfo:
        await example_registry.lookup_with("12345678", ["lei"])
    err = excinfo.value
    assert err.code is ErrorCode.BAD_REQUEST
    assert err.details["allowed"] == []
    assert "lei" in err.message
    assert "lei" in err.hint or "none" in err.hint.lower()


async def test_bad_include_value_raises_before_any_upstream_request(
    example_registry: Registry,
) -> None:
    """Validated before `lookup` runs: cheap to fail, and it must not cost
    the upstream a wasted request."""
    calls = 0

    class _CountedRegistry2(type(example_registry)):  # type: ignore[misc]
        country = "XR"
        registry = "example-counted2"
        is_stub = True
        supported_includes = frozenset({"widget"})

        async def lookup(self, id: str) -> CompanyReport:
            nonlocal calls
            calls += 1
            return _report(self.country, self.registry, id)

        async def widget(self, id: str) -> _Widget:
            return _Widget(items=[])

    with pytest.raises(RegistryError):
        await _CountedRegistry2().lookup_with("123", ["bogus"])
    assert calls == 0


# ---------------------------------------------------------------------------
# Two-level nullability (D-026(c), restated for every attachment by D-041(c))
# ---------------------------------------------------------------------------


async def test_absent_block_means_not_requested(attach_registry: Registry) -> None:
    result = await attach_registry.lookup_with("123", [])
    assert isinstance(result, _ReportWithAttachments)
    assert result.widget is None


async def test_present_block_with_empty_content_is_a_real_answer_not_an_absence(
    attach_registry: Registry,
) -> None:
    """`id == "empty"` makes the fake `widget` fetch succeed with no items:
    a **present** block, not an absent one. "The register has none of
    these" is a real, useful answer, distinct from "you did not ask"."""
    result = await attach_registry.lookup_with("empty", ["widget"])
    assert isinstance(result, _ReportWithAttachments)
    assert result.widget is not None
    assert result.widget.items == []
    assert result.notes == []  # a genuinely empty result is not a failure


async def test_present_block_with_content(attach_registry: Registry) -> None:
    result = await attach_registry.lookup_with("123", ["widget"])
    assert isinstance(result, _ReportWithAttachments)
    assert result.widget is not None
    assert result.widget.items == ["a", "b"]


# ---------------------------------------------------------------------------
# A failed attachment never fails the lookup (D-042(b),(j))
# ---------------------------------------------------------------------------


async def test_a_failing_attachment_leaves_its_block_absent_with_a_note(
    attach_registry: Registry,
) -> None:
    result = await attach_registry.lookup_with("123", ["gadget"])
    assert isinstance(result, _ReportWithAttachments)
    assert result.gadget is None
    assert len(result.notes) == 1
    assert "gadget" in result.notes[0]
    assert "unreachable" in result.notes[0]


async def test_one_failing_attachment_does_not_affect_a_succeeding_one(
    attach_registry: Registry,
) -> None:
    """`include=["widget", "gadget"]` in one call: `widget` present,
    `gadget` absent with a note, and the call as a whole still succeeds —
    a partial failure is a note, not a raise."""
    result = await attach_registry.lookup_with("123", ["widget", "gadget"])
    assert isinstance(result, _ReportWithAttachments)
    assert result.widget is not None
    assert result.widget.items == ["a", "b"]
    assert result.gadget is None
    assert len(result.notes) == 1
    assert "gadget" in result.notes[0]
    assert "widget" not in result.notes[0]


async def test_pre_existing_notes_are_preserved_ahead_of_a_failure_note(
    example_registry: Registry,
) -> None:
    """A country module's own `notes` (e.g. an ENK caveat) survive
    unchanged, in order, alongside a `lookup_with` failure note."""

    class _NotedRegistry(type(example_registry)):  # type: ignore[misc]
        country = "XN"
        registry = "example-noted"
        is_stub = True
        supported_includes = frozenset({"gadget"})

        async def lookup(self, id: str) -> CompanyReport:
            return _report(self.country, self.registry, id).model_copy(
                update={"notes": ["Pre-existing caveat."]}
            )

        async def gadget(self, id: str) -> _Widget:
            raise RegistryError(
                ErrorCode.UPSTREAM_ERROR,
                "down",
                hint="retry",
                country=self.country,
                registry=self.registry,
            )

    result = await _NotedRegistry().lookup_with("1", ["gadget"])
    assert result.notes[0] == "Pre-existing caveat."
    assert len(result.notes) == 2
    assert "gadget" in result.notes[1]


async def test_a_failing_base_lookup_raises_and_attempts_no_attachment(
    attach_registry: Registry,
) -> None:
    """Contrast with an attachment failure: `lookup` itself failing is a
    real error, not a note — there is no report to attach anything to."""

    class _FailingLookup(type(attach_registry)):  # type: ignore[misc]
        async def lookup(self, id: str) -> CompanyReport:
            raise RegistryError(
                ErrorCode.NOT_FOUND,
                "no such company",
                hint="check the id",
                country=self.country,
                registry=self.registry,
            )

    with pytest.raises(RegistryError) as excinfo:
        await _FailingLookup().lookup_with("1", ["widget"])
    assert excinfo.value.code is ErrorCode.NOT_FOUND


async def test_only_registry_error_is_treated_as_a_failed_fetch(
    example_registry: Registry,
) -> None:
    """A bug in a country module (a bare `ValueError`, say) is not an
    upstream failure and must not be swallowed into a plausible-looking
    `notes` sentence — it propagates and the caller sees it crash."""

    class _BuggyRegistry(type(example_registry)):  # type: ignore[misc]
        country = "XB"
        registry = "example-buggy"
        is_stub = True
        supported_includes = frozenset({"widget"})

        async def lookup(self, id: str) -> CompanyReport:
            return _report(self.country, self.registry, id)

        async def widget(self, id: str) -> _Widget:
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await _BuggyRegistry().lookup_with("1", ["widget"])


# ---------------------------------------------------------------------------
# Duplicates and bounded concurrency (D-024(g): at most `max_concurrency`
# attachment fetches in flight)
# ---------------------------------------------------------------------------


async def test_duplicate_include_values_are_fetched_once(
    example_registry: Registry,
) -> None:
    calls: list[str] = []

    class _CountingRegistry(type(example_registry)):  # type: ignore[misc]
        country = "XT"
        registry = "example-counting"
        is_stub = True
        supported_includes = frozenset({"widget"})

        async def lookup(self, id: str) -> CompanyReport:
            return _report(self.country, self.registry, id)

        async def widget(self, id: str) -> _Widget:
            calls.append(id)
            return _Widget(items=["once"])

    result = await _CountingRegistry().lookup_with("1", ["widget", "widget"])
    assert calls == ["1"]
    assert isinstance(result, _ReportWithAttachments)
    assert result.widget is not None and result.widget.items == ["once"]


async def test_lookup_with_fetches_attachments_concurrently_by_default(
    example_registry: Registry,
) -> None:
    order: list[str] = []
    gadget_started = asyncio.Event()

    class _SlowRegistry(type(example_registry)):  # type: ignore[misc]
        country = "XV"
        registry = "example-slow"
        is_stub = True
        supported_includes = frozenset({"widget", "gadget"})

        async def lookup(self, id: str) -> CompanyReport:
            return _report(self.country, self.registry, id)

        async def widget(self, id: str) -> _Widget:
            order.append("widget-start")
            # Block until gadget signals it has started. If the two were fetched
            # sequentially this wait would never be satisfied, so the timeout is
            # the failure — deterministic, unlike racing two sleep lengths.
            await asyncio.wait_for(gadget_started.wait(), timeout=5)
            order.append("widget-end")
            return _Widget(items=["w"])

        async def gadget(self, id: str) -> _Widget:
            order.append("gadget-start")
            gadget_started.set()
            order.append("gadget-end")
            return _Widget(items=["g"])

    result = await _SlowRegistry().lookup_with("1", ["widget", "gadget"])
    assert isinstance(result, _ReportWithAttachments)
    assert result.widget is not None and result.widget.items == ["w"]
    assert result.gadget is not None and result.gadget.items == ["g"]
    # Overlap proven by rendezvous: widget cannot finish until gadget has started,
    # so this exact order is only reachable if both were in flight at once. The
    # earlier version raced a 0.03s sleep against a 0.01s one and flaked under load
    # — the same fault `test_105_token_bucket_does_not_serialise_concurrent_lookups`
    # documents in tests/test_client_gb.py.
    assert order == ["widget-start", "gadget-start", "gadget-end", "widget-end"]


async def test_max_concurrency_bounds_in_flight_attachment_fetches(
    example_registry: Registry,
) -> None:
    order: list[str] = []

    class _SlowRegistry2(type(example_registry)):  # type: ignore[misc]
        country = "XU"
        registry = "example-slow2"
        is_stub = True
        supported_includes = frozenset({"widget", "gadget"})

        async def lookup(self, id: str) -> CompanyReport:
            return _report(self.country, self.registry, id)

        async def widget(self, id: str) -> _Widget:
            order.append("widget-start")
            await asyncio.sleep(0)
            order.append("widget-end")
            return _Widget(items=[])

        async def gadget(self, id: str) -> _Widget:
            order.append("gadget-start")
            await asyncio.sleep(0.01)
            order.append("gadget-end")
            return _Widget(items=[])

    await _SlowRegistry2().lookup_with("1", ["widget", "gadget"], max_concurrency=1)
    # max_concurrency=1 forces strictly sequential fetches, in `include`
    # order: gadget cannot acquire the one semaphore slot until widget frees it.
    assert order == ["widget-start", "widget-end", "gadget-start", "gadget-end"]


# ---------------------------------------------------------------------------
# A misconfigured country module fails loudly, not silently (defensive:
# `model_copy(update=...)` alone would drop an unknown key without error —
# see `core/registry.py`'s `lookup_with`)
# ---------------------------------------------------------------------------


async def test_an_include_with_no_matching_report_field_fails_loudly(
    example_registry: Registry,
) -> None:
    """A country-module bug — `supported_includes` names something with no
    matching `CompanyReport` field — must never silently vanish. It surfaces
    as a clear `RuntimeError`, not a quietly incomplete report."""

    class _GhostRegistry(type(example_registry)):  # type: ignore[misc]
        country = "XG"
        registry = "example-ghost"
        is_stub = True
        supported_includes = frozenset({"ghost"})

        async def lookup(self, id: str) -> CompanyReport:
            # A plain `CompanyReport` — no `ghost` field exists anywhere.
            return CompanyReport(country=self.country, registry=self.registry, id=id, name="Ghost Co")

        async def ghost(self, id: str) -> _Widget:
            return _Widget(items=["boo"])

    with pytest.raises(RuntimeError, match="ghost"):
        await _GhostRegistry().lookup_with("1", ["ghost"])
