"""Peppol / ELMA participant status — the ``include=["peppol"]`` attachment.

DECISIONS.md D-029(b), amended in full by D-046 after ``tasks/T48-recon.md``
read the wire. Norway-only (``registries/no/__init__.py``'s own
``supported_includes``, not ``Registry.universal_includes`` — D-046(h)).

**The shape: two network reads, one answer.**

1. **The SML — and it is DNS, not HTTP.** Build
   ``<base32(sha256(lower(participant id value)))>.iso6523-actorid-upis.
   participant.sml.prod.tech.peppol.org`` and read its NAPTR record. The
   record whose service is ``Meta:SMP`` and flag is ``U`` carries the base
   URL of the SMP that answers for this participant, as the substring
   between the second and third ``!`` of its ``!.*!<url>!`` regexp.
2. **The SMP.** ``GET <base>/iso6523-actorid-upis%3A%3A0192%3A<orgnr>``
   returns the ServiceGroup XML: every ``ServiceMetadataReference/@href``,
   split on ``/services/`` and percent-decoded, is one document type this
   participant can *receive*.
3. **The Peppol Directory — positive answers only, and only as a repair.**
   Consulted solely when step 1/2 produced no answer at all (never after an
   NXDOMAIN, which is already the answer, and never after a ServiceGroup,
   which is a better one): ``GET https://directory.peppol.eu/search/1.0/
   json?participant=iso6523-actorid-upis::0192:<orgnr>``. It can raise a
   ``null`` to a ``true`` — a Directory list is a subset of the SMP's, so
   presence there is sound — but it can **never** produce ``false``: both
   Peppol operators say in writing that an absence in the Directory means
   nothing, because publication to it is voluntary (D-046(a)).

**The one trap this module exists to avoid, and it has two mouths that
close on the same mistake.** (1) Hardcoding ``smp.elma-smp.no`` — it
answers for 42 of 43 Norwegian participants tested, which is exactly why an
implementer would do it and exactly why the tests would still pass; Digdir
(ELMA's own operator) says in writing that "a lookup only in ELMA is no
longer a valid way to lookup norwegian organizations in PEPPOL", and the
1-in-43 (``0192:837056942`` -> ``smp.conta.no``) proves it live. A
hardcoded ELMA host reports ``registered: false`` for a company that *is*
registered — the worst available answer to a statutory question. (2)
Hardcoding the old EC zone ``edelivery.tech.ec.europa.eu`` or its
``B-<md5>`` CNAME form, as every pre-2025 tutorial does — the CNAME form is
already NXDOMAIN everywhere, and the EC zone is being decommissioned this
month at the Commission's discretion. **The rule that closes both: the SML
*zone* below is a module constant, because it is the network's own root and
nothing derives it; the SMP *host* is data, read fresh from the NAPTR on
every uncached lookup, and is never assumed, inferred from the country, or
remembered across lookups.**

**The TTL below (``core/cache.py``'s ``peppol`` row, 24h ok / 1h empty) is
registry-mcp's own policy, not either upstream's.** Both the SMP and the
Directory send ``no-store`` (the SMP: ``cache-control: no-cache, no-store,
max-age=0, must-revalidate``; the Directory: ``no-cache, no-store,
must-revalidate, proxy-revalidate``), and the NAPTR's own TTL is 60
seconds. Only the *composed* :class:`~registry_mcp.core.models.
PeppolParticipant` is ever cached (D-046(d)) — never the NAPTR-to-SMP-host
binding, whose own TTL is a minute and which (per the trap above) must be
read fresh regardless.

**Not done here, by name, so the next reader knows it was considered and
declined rather than missed (D-046(e), C2):** process identifiers and
``ServiceActivationDate``/``ServiceExpirationDate`` (one HTTP call *per
document type*, deeper than this block reads); the AS4 endpoint address; and
**XMLDSig verification of the SMP's signature over each ServiceMetadata**.
A bare, keyless GET already returns 200 with no client certificate and no
token — the Peppol certificate appears only *inside* the answer, as an
optional integrity check for a reader who wants to *prove* which access
point signed it, never as an entry requirement. This module reads the
ServiceGroup body and never touches the signature.

**The Peppol Directory's ``contact`` block is never requested, read, mapped
or logged, anywhere in this module** — the Directory's own Privacy Policy
restricts personal data in it to "persons who are contractually authorised
... to use the Peppol Network", which registry-mcp is not, and `contact` is
the only place personal data lives in any of these three payloads
(D-046(f)). This paragraph is the one place the word appears.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx

from registry_mcp import __version__
from registry_mcp.core import cache
from registry_mcp.core.models import ErrorCode, PeppolParticipant, RegistryError, SourceRef

__all__ = ["aclose", "fetch_peppol"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The Peppol SML production zone. *Peppol Service Metadata Locator (SML)
#: v1.3.0*, valid from 2025-11-01 — the successor to the EC-operated
#: ``edelivery.tech.ec.europa.eu`` (see the module docstring's trap). This is
#: the network's own root and a genuine constant: nothing in this module
#: derives it, unlike the SMP host below, which is always data.
_SML_ZONE = "participant.sml.prod.tech.peppol.org"

#: The ISO 6523 scheme identifier for a national-registry-issued participant
#: id, used both as the DNS label between the hash and the zone, and as the
#: scheme half of the qualified ``<scheme>::<value>`` identifier sent to the
#: SMP and to the Directory.
_SCHEME = "iso6523-actorid-upis"

#: Norway's ISO 6523 ICD (International Code Designator) inside the Peppol
#: network (DECISIONS.md D-029(c)). Country-specific by design: D-046(h) is
#: why this module is not shared with any other country.
_ICD = "0192"

#: The one NAPTR service name Peppol SML v1.3.0 permits for this walk:
#: "Other service names MUST NOT be used in relation to this specification."
_META_SMP_SERVICE = "Meta:SMP"
#: The NAPTR "terminal URI" flag — the regexp field carries the final answer,
#: no further NAPTR indirection.
_NAPTR_URI_FLAG = "U"

#: Short and explicit, per DECISIONS.md D-046(c): `lookup_with` runs every
#: attachment concurrently, and a hung DNS read must not hold the whole
#: lookup open.
_DNS_LIFETIME_SECONDS = 5.0

_DIRECTORY_URL = "https://directory.peppol.eu/search/1.0/json"

_TIMEOUT = httpx.Timeout(5.0)
_RETRY_BACKOFF_SECONDS = 0.25
_MAX_ATTEMPTS = 2  # one try + one retry, on a timeout or a 5xx only — never a 4xx

#: DECISIONS.md D-046(g), quoted exactly. Not "NLOD", not "CC BY", not
#: `None` (which `SourceRef.license` reserves for "not recorded" — this is a
#: *stated* absence): nobody — not OpenPeppol, not Digitaliseringsdirektoratet
#: — publishes a licence for any of the three routes this module reads.
_LICENSE = (
    "Not stated — neither OpenPeppol nor Digitaliseringsdirektoratet publishes a "
    "licence for the Peppol SML, for any SMP or for the Peppol Directory; "
    "data.norge.no records the ELMA dataset's licence as 'Ikke oppgitt' (not stated)"
)

#: The committed table (DECISIONS.md D-046(e), C4): exact string membership
#: only, on the full ``<scheme>::<value>`` form — never a substring, never a
#: version range. DFØ's own equation: "Peppol BIS billing v3.0 er det samme
#: som EHF-faktura." The CreditNote id is deliberately absent: this flag is
#: named for the invoice, and the credit note is in `document_types` for
#: anyone who needs it.
_INVOICE_DOCUMENT_TYPE_IDS: frozenset[str] = frozenset(
    {
        # BIS Billing 3.0 Invoice = EHF-faktura. 384,834 of 385,268 Norwegian
        # Peppol Directory participants advertise it (99.89%, T48-recon.md).
        "busdox-docid-qns::urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::"
        "Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:"
        "billing:3.0::2.1",
        # Its PINT successor, 3.4% of the same population.
        "peppol-doctype-wildcard::urn:oasis:names:specification:ubl:schema:xsd:"
        "Invoice-2::Invoice##urn:peppol:pint:billing-1::2.1",
    }
)

_RECEIVING_ONLY_NOTE = (
    "Only receiving capabilities are registered anywhere in the Peppol network "
    "(OpenPeppol's administrative policy): this block says what this participant "
    "is set up to receive, never what it can send, which is the right question "
    "for the 1 January 2027 duty to send this counterparty an e-invoice."
)
_ACTIVATION_DATES_NOTE = (
    "The SMP publishes a ServiceActivationDate/ServiceExpirationDate for each "
    "document type; this block does not read them (one extra HTTP call per "
    "document type), so an advertised type may be future-dated or already expired."
)
_DIRECTORY_LAG_NOTE = (
    "This answer came from the Peppol Directory, a voluntary index of the network "
    "that can lag the authoritative SMP (measured: Equinor's own SMP advertises 17 "
    "document types where the Directory lists 12) -- consulted only because the "
    "Peppol SML/SMP route itself did not answer."
)
_DIRECTORY_MISS_NOTE = (
    "The Peppol Directory does not list this participant. Both Peppol operators "
    "state in writing that this does not mean the entity is not in the Peppol "
    "Network: publication to the Directory is voluntary, so an absence there is "
    "not authoritative the way an SML/SMP answer is."
)

_client: httpx.AsyncClient | None = None


# ---------------------------------------------------------------------------
# HTTP plumbing (mirrors core/gleif.py's shape for a second cross-cutting
# upstream family that happens to live under registries/no/ rather than
# core/ -- DECISIONS.md D-046(h): the ICD, the per-participant SMP and the
# licence sentence are all specifically Norwegian, so this is a country
# declaration, not a base-class attachment)
# ---------------------------------------------------------------------------


def _user_agent() -> str:
    # Named `email`, not the operator-contact-email module's usual `contact`
    # local, so this file's one `contact` grep hit (D-046(f), tested below)
    # stays the docstring paragraph explaining why the Directory's `contact`
    # field is never read -- not an unrelated local variable.
    email = os.environ.get("REGISTRY_MCP_CONTACT_EMAIL", "").strip()
    if not email:
        email = "unknown@example.invalid"
        logger.warning("REGISTRY_MCP_CONTACT_EMAIL is not set; using %s", email)
    return f"registry-mcp/{__version__} (+https://github.com/foretak/registry-mcp; {email})"


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": _user_agent()})
    return _client


async def aclose() -> None:
    """Close the shared client. Call on application shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _validate_orgnr(id: str) -> str:
    """Lazy hand-off to ``registries/no/rules.py::validate_orgnr`` — the same
    lazy-import convention ``registries/no/client.py`` uses, so importing
    this module never depends on import order with ``rules.py``."""
    from registry_mcp.registries.no import rules

    result: str = rules.validate_orgnr(id)
    return result


async def _get(
    url: str, *, headers: dict[str, str], params: dict[str, str] | None = None
) -> httpx.Response:
    """One GET, retrying exactly once on a timeout or a 5xx. Never on a 4xx —
    a 404 is a legitimate, definitive answer on the SMP route (D-046(a)) and
    a 4xx from the Directory means our own request was malformed."""
    client = _get_client()
    attempt = 0
    while True:
        attempt += 1
        try:
            response = await client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_ATTEMPTS:
                raise RegistryError(
                    ErrorCode.UPSTREAM_TIMEOUT,
                    f"{url} did not respond within the timeout.",
                    hint=(
                        "This is a problem with third-party Peppol infrastructure, not "
                        "a bad request. Retry the call in a moment, or omit 'peppol' "
                        "from include."
                    ),
                    country="NO",
                    registry="brreg",
                ) from exc
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code >= 500:
            if attempt >= _MAX_ATTEMPTS:
                raise RegistryError(
                    ErrorCode.UPSTREAM_ERROR,
                    f"{url} returned {response.status_code}.",
                    hint=(
                        "This is a problem with third-party Peppol infrastructure, not "
                        "a bad request. Retry the call in a moment, or omit 'peppol' "
                        "from include."
                    ),
                    country="NO",
                    registry="brreg",
                )
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        return response


# ---------------------------------------------------------------------------
# C1 -- the SML: DNS, not HTTP
# ---------------------------------------------------------------------------


def _hash_label(participant_value: str) -> str:
    """``base32(sha256(lower(value)))``, trailing ``=`` stripped — over the
    identifier **value only** (``"0192:923609016"``), never the qualified
    ``"iso6523-actorid-upis::0192:923609016"``: the scheme is a separate DNS
    label. Six lines of stdlib, no network, no dependency (DECISIONS.md
    D-046(c)); reproduces the SML spec's own worked example and Equinor's
    label byte for byte (``tests/test_no_peppol.py``)."""
    digest = hashlib.sha256(participant_value.lower().encode("ascii")).digest()
    label: str = base64.b32encode(digest).decode("ascii").rstrip("=")
    return label


def _naptr_fqdn(participant_value: str) -> str:
    return f"{_hash_label(participant_value)}.{_SCHEME}.{_SML_ZONE}"


def _decode(value: bytes) -> str:
    return value.decode("ascii", errors="replace")


def _base_url_from_regexp(regexp: str) -> str | None:
    """The base URL is the substring between the second and third ``!`` of
    the ``!.*!<base URL>!`` regexp. Returns ``None`` if the value is not
    shaped that way -- treated identically to "no matching record", never
    guessed at."""
    parts = regexp.split("!")
    if len(parts) < 4 or not parts[2]:
        return None
    return parts[2]


async def _resolve_smp_base(fqdn: str) -> str | None:
    """The DNS step, isolated behind this one seam so tests can monkeypatch
    it directly -- respx mocks ``httpx`` and cannot see ``dnspython`` at all
    (DECISIONS.md D-046(c)).

    Uses ``dns.asyncresolver``'s async ``resolve()`` — never the
    *synchronous* resolver a blocking call would stall the event loop with —
    against the operator's own configured resolver (``/etc/resolv.conf``),
    the same one every other program on the host uses and the same trust
    model a real Peppol access point uses to perform this exact walk in
    production. DNS-over-HTTPS was considered and declined by name
    (DECISIONS.md D-046(c)): it would substitute a resolver *we* chose,
    belonging to a company with no relationship to the Peppol network, into
    the trust path of an answer acted on under bokføringsloven § 10.

    Returns:
        The SMP base URL from the winning ``Meta:SMP``/``U`` NAPTR record, or
        ``None`` when the SML answered NOERROR with nothing usable — either
        no NAPTR record at all (``dns.resolver.NoAnswer``) or a NAPTR RRset
        with no matching ``Meta:SMP``/``U`` record. Both collapse to the same
        ``None`` here because they are the same fact for a caller: "the SML
        had nothing to say" — the shape D-046(c) says a filtering or
        NXDOMAIN-rewriting middlebox produces, and which must read as
        ``null``, never ``False``.

    Raises:
        dns.resolver.NXDOMAIN: the participant is in no SMP at all — the
            only DNS outcome (besides an SMP 404) that earns
            ``registered: False`` (DECISIONS.md D-046(a)). **Not caught
            here, and never inferred from any other exception**: a resolver
            exception is not an NXDOMAIN.
        dns.exception.DNSException: any other resolver failure — a timeout,
            SERVFAIL, no nameservers reachable, or anything else dnspython
            can raise. Mapped explicitly by the caller as one bucket
            (DECISIONS.md D-046(c) groups them as one outcome); never
            inferred from a bare ``Exception``.
    """
    try:
        answer = await dns.asyncresolver.resolve(fqdn, "NAPTR", lifetime=_DNS_LIFETIME_SECONDS)
    except dns.resolver.NoAnswer:
        return None
    for rdata in answer:
        service = _decode(rdata.service)
        flags = _decode(rdata.flags)
        if service == _META_SMP_SERVICE and flags.upper() == _NAPTR_URI_FLAG:
            base_url = _base_url_from_regexp(_decode(rdata.regexp))
            if base_url is not None:
                return base_url
    return None


# ---------------------------------------------------------------------------
# C2 -- the SMP
# ---------------------------------------------------------------------------


def _service_group_url(smp_base: str, participant_value: str) -> str:
    """Join with care: ELMA's NAPTR URI ends in ``/`` and Conta's does not
    (live-confirmed, both fixtures) — strip one trailing slash before
    joining rather than assume either shape."""
    base = smp_base[:-1] if smp_base.endswith("/") else smp_base
    encoded = quote(f"{_SCHEME}::{participant_value}", safe="")
    return f"{base}/{encoded}"


def _local_name(tag: str) -> str:
    """Strip a Clark-notation namespace prefix (``'{uri}Name'`` -> ``'Name'``).
    Needed because ELMA's ServiceGroup uses the ``ns2:`` ElementTree default
    prefix and Conta's uses ``smp:`` for the identical element — matching by
    local name is the only form that is not a hardcoded guess about a
    specific SMP's own XML serialisation choices."""
    return tag.rsplit("}", 1)[-1]


def _document_types_from_service_group(body: bytes) -> list[str]:
    """Every ``ServiceMetadataReference/@href``, split on ``/services/``,
    percent-decoded to a full ``"<scheme>::<value>"`` string. No cap, no
    truncation (DECISIONS.md D-046(e)) — Equinor returns 17, the modal
    Norwegian participant 2, one observed participant 26.

    Raises:
        xml.etree.ElementTree.ParseError: on a body that is not well-formed
            XML. Not caught here — the caller treats it the same as any
            other "the SMP did not give us a usable answer" outcome.
    """
    root = ET.fromstring(body)
    document_types: list[str] = []
    for elem in root.iter():
        if _local_name(elem.tag) != "ServiceMetadataReference":
            continue
        href = elem.get("href")
        if not href:
            continue
        _prefix, separator, tail = href.partition("/services/")
        if separator:
            document_types.append(unquote(tail))
    return document_types


async def _get_service_group(url: str) -> httpx.Response:
    """The SMP GET. **HTTPS only** — SMPs became HTTPS-only on 2026-02-01 and
    a bare ``http://`` GET now returns 503 (T48-recon.md, live). No client
    certificate, no token: this is a keyless, anonymous read, confirmed live
    against two different SMPs. **``Accept: text/xml``, not
    ``application/xml``** — the ELMA SMP answers the latter with 406
    (live-confirmed, this session)."""
    return await _get(url, headers={"Accept": "text/xml"})


# ---------------------------------------------------------------------------
# C3 -- the Peppol Directory fallback, positive answers only
# ---------------------------------------------------------------------------


def _directory_document_types(body: dict[str, Any]) -> list[str] | None:
    """``None`` on a miss (``matches`` empty — the Directory's own empty
    answer is HTTP 200 with ``"total-result-count": 0``, never a 404); the
    first match's ``docTypes``, joined ``"<scheme>::<value>"``, otherwise.

    The Directory's ``contact`` field, when present on a match's `entities`,
    is never read here or anywhere in this module (DECISIONS.md D-046(f));
    only ``docTypes`` is. Likewise ``name``, ``websites``, ``regDate`` and
    ``countryCode`` are never carried onto the block (D-046(e)): a second
    register's opinion of a company already described from Enhetsregisteret.
    """
    matches = body.get("matches") or []
    if not matches:
        return None
    first = matches[0] if isinstance(matches[0], dict) else {}
    raw_doc_types = first.get("docTypes") or []
    document_types: list[str] = []
    for entry in raw_doc_types:
        if not isinstance(entry, dict):
            continue
        scheme = entry.get("scheme")
        value = entry.get("value")
        if scheme and value:
            document_types.append(f"{scheme}::{value}")
    return document_types


async def _get_directory(participant_value: str) -> httpx.Response:
    """The Directory GET. The scheme is part of the ``participant`` value —
    a bare identifier the Directory cannot parse is silently ignored and
    400s if it was the only term. ``contact`` is never sent as a query
    parameter (DECISIONS.md D-046(f))."""
    return await _get(
        _DIRECTORY_URL,
        headers={"Accept": "application/json"},
        params={"participant": f"{_SCHEME}::{participant_value}"},
    )


# ---------------------------------------------------------------------------
# C4 -- can_receive_invoice
# ---------------------------------------------------------------------------


def _can_receive_invoice(
    registered: bool | None, document_types: list[str], *, via_directory: bool
) -> bool | None:
    """DECISIONS.md D-046(e)'s table, verbatim:

    ``true`` via the SMP: ``True`` if a table id is in ``document_types``,
    else ``False``. ``true`` via the Directory: ``True`` if present, **else
    ``None`` — never ``False``** (a Directory list is a subset of the SMP's,
    so presence is sound and absence is not). ``false``: ``False``. ``null``:
    ``None``.
    """
    if registered is None:
        return None
    if registered is False:
        return False
    present = any(candidate in _INVOICE_DOCUMENT_TYPE_IDS for candidate in document_types)
    if present:
        return True
    return None if via_directory else False


# ---------------------------------------------------------------------------
# Assembly, cache and the public entry point
# ---------------------------------------------------------------------------


def _finish(
    *,
    participant_value: str,
    registered: bool | None,
    document_types: list[str],
    smp_url: str | None,
    source: str | None,
    source_url: str | None,
    fetched_at: datetime,
    via_directory: bool,
    notes: list[str],
) -> PeppolParticipant:
    return PeppolParticipant(
        participant_id=participant_value,
        registered=registered,
        can_receive_invoice=_can_receive_invoice(
            registered, document_types, via_directory=via_directory
        ),
        document_types=document_types,
        smp_url=smp_url,
        provenance=SourceRef(
            source=source,
            source_url=source_url,
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=False,
        ),
        notes=notes,
    )


async def _fetch_peppol_uncached(orgnr: str) -> PeppolParticipant:
    participant_value = f"{_ICD}:{orgnr}"
    fqdn = _naptr_fqdn(participant_value)

    notes: list[str] = []
    smp_url: str | None = None
    smp_base: str | None

    try:
        smp_base = await _resolve_smp_base(fqdn)
    except dns.resolver.NXDOMAIN:
        return _finish(
            participant_value=participant_value,
            registered=False,
            document_types=[],
            smp_url=None,
            source=f"Peppol SML ({_SML_ZONE})",
            source_url=None,
            fetched_at=datetime.now(UTC),
            via_directory=False,
            notes=[
                f"The Peppol SML has no record for {participant_value} (NXDOMAIN "
                f"resolving {fqdn}): not registered anywhere in the Peppol network."
            ],
        )
    except dns.exception.DNSException as exc:
        notes.append(
            f"Could not resolve the Peppol SML record for {participant_value}: "
            f"{type(exc).__name__}: {exc}."
        )
        smp_base = None
    else:
        if smp_base is None:
            notes.append(
                f"The Peppol SML answered {fqdn} with no usable Meta:SMP record -- the "
                "shape a filtering or NXDOMAIN-rewriting middlebox produces, not a "
                "confirmed non-registration."
            )

    if smp_base is not None:
        smp_url = smp_base
        service_group_url = _service_group_url(smp_base, participant_value)
        host = urlsplit(smp_base).hostname or smp_base
        source = f"{host} (Peppol SMP, via the Peppol SML)"
        try:
            response = await _get_service_group(service_group_url)
        except RegistryError as exc:
            notes.append(f"The SMP at {smp_base} did not answer: {exc.message}")
        else:
            if response.status_code == 200:
                try:
                    document_types = _document_types_from_service_group(response.content)
                except ET.ParseError:
                    notes.append(
                        f"The SMP at {smp_base} returned a ServiceGroup that could not "
                        "be parsed."
                    )
                else:
                    notes.append(
                        f"Resolved via the Peppol SML to {smp_base}, then queried its "
                        "ServiceGroup."
                    )
                    notes.append(_RECEIVING_ONLY_NOTE)
                    notes.append(_ACTIVATION_DATES_NOTE)
                    return _finish(
                        participant_value=participant_value,
                        registered=True,
                        document_types=document_types,
                        smp_url=smp_url,
                        source=source,
                        source_url=service_group_url,
                        fetched_at=datetime.now(UTC),
                        via_directory=False,
                        notes=notes,
                    )
            elif response.status_code == 404:
                return _finish(
                    participant_value=participant_value,
                    registered=False,
                    document_types=[],
                    smp_url=smp_url,
                    source=source,
                    source_url=service_group_url,
                    fetched_at=datetime.now(UTC),
                    via_directory=False,
                    notes=[
                        f"The SMP at {smp_base} (named by the Peppol SML for this "
                        f"participant) returned 404 for {participant_value}: not "
                        "registered."
                    ],
                )
            else:
                notes.append(
                    f"The SMP at {smp_base} returned an unexpected status "
                    f"{response.status_code}."
                )

    # Reached only when the SML/SMP route produced no answer at all -- never
    # after an NXDOMAIN or a ServiceGroup (both already returned above), and
    # never after an SMP 404 (also already returned). DECISIONS.md D-046(a).
    try:
        directory_response = await _get_directory(participant_value)
    except RegistryError as exc:
        if smp_url is None:
            # Nothing at all: the SML gave us no host, and the one repair
            # attempt failed too. D-042(b): this is the whole-attachment
            # failure `lookup_with` turns into an absent block plus a note,
            # not a present block with `registered: null` -- there is no
            # fetch left to describe a `SourceRef` from.
            raise RegistryError(
                ErrorCode.UPSTREAM_ERROR,
                "Neither the Peppol SML/SMP route nor the Peppol Directory answered "
                f"for {participant_value}.",
                hint=(
                    "This is a problem with third-party Peppol infrastructure, not a "
                    "bad request. Retry the call in a moment, or omit 'peppol' from "
                    "include."
                ),
                country="NO",
                registry="brreg",
            ) from exc
        notes.append(f"The Peppol Directory did not answer either: {exc.message}")
        return _finish(
            participant_value=participant_value,
            registered=None,
            document_types=[],
            smp_url=smp_url,
            source=None,
            source_url=None,
            fetched_at=datetime.now(UTC),
            via_directory=True,
            notes=notes,
        )

    fetched_at = datetime.now(UTC)
    directory_source = "Peppol Directory (directory.peppol.eu) -- an index that may lag"
    directory_source_url = str(directory_response.request.url)

    if directory_response.status_code != 200:
        notes.append(
            f"The Peppol Directory returned an unexpected status "
            f"{directory_response.status_code}."
        )
        return _finish(
            participant_value=participant_value,
            registered=None,
            document_types=[],
            smp_url=smp_url,
            source=None,
            source_url=None,
            fetched_at=fetched_at,
            via_directory=True,
            notes=notes,
        )

    body: dict[str, Any] = directory_response.json()
    directory_document_types = _directory_document_types(body)
    if directory_document_types is None:
        notes.append(_DIRECTORY_MISS_NOTE)
        return _finish(
            participant_value=participant_value,
            registered=None,
            document_types=[],
            smp_url=smp_url,
            source=directory_source,
            source_url=directory_source_url,
            fetched_at=fetched_at,
            via_directory=True,
            notes=notes,
        )

    notes.append(
        "The Peppol Directory lists this participant (the SML/SMP route above did "
        "not answer)."
    )
    notes.append(_RECEIVING_ONLY_NOTE)
    notes.append(_DIRECTORY_LAG_NOTE)
    return _finish(
        participant_value=participant_value,
        registered=True,
        document_types=directory_document_types,
        smp_url=smp_url,
        source=directory_source,
        source_url=directory_source_url,
        fetched_at=fetched_at,
        via_directory=True,
        notes=notes,
    )


def _cache_key(orgnr: str) -> str:
    """``NO:brreg:peppol:{orgnr}`` (DECISIONS.md D-046(d)) — four segments on
    D-006's convention, kind third so ``core/cache.py``'s per-kind TTL table
    finds it, beside the ``NO:brreg:entity:{orgnr}`` and
    ``NO:brreg:filings:{orgnr}`` keys ``registries/no/client.py`` already
    builds. The second segment names the module that owns the key
    (``brreg``, per D-006/D-041(c)'s convention for this package) — the
    upstream answering underneath is Peppol infrastructure, not
    Brønnøysundregistrene, and that distinction is carried by `SourceRef`,
    not by the cache key."""
    return f"NO:brreg:peppol:{orgnr}"


async def fetch_peppol(id: str) -> PeppolParticipant:
    """Fetch (or serve from cache) the Peppol participant status for one
    entity.

    Caches only the **composed** answer, never the NAPTR-to-SMP-host
    binding (whose own TTL is 60 seconds and which must be read fresh on
    every uncached lookup regardless — see the module docstring's trap).
    ``registered: true`` is cached at the per-kind table's ok TTL (24h);
    ``registered: false`` at its empty TTL (1h), through the existing
    ``status="not_found"`` label purely for that TTL, never raised as an
    error; **``registered: null`` is never written to the cache at all**
    (DECISIONS.md D-046(d)) — caching "we could not ask" would turn a
    thirty-second outage into an hour of nulls.

    Raises:
        RegistryError: ``invalid_id`` from the orgnr check; ``upstream_error``
            only when *both* the SML/SMP route and the Directory fallback
            failed outright, leaving nothing to build even a ``null`` block
            from (D-042(b)) -- ``lookup_with`` turns that into an absent
            block plus a ``notes`` sentence, never failing the whole lookup.
            An *unanswered* Peppol question that nonetheless completed both
            attempts is not this: it is a **present** block with
            ``registered: null``, because ``participant_id`` is always worth
            returning (D-029(c)).
    """
    orgnr = _validate_orgnr(id)
    cache_key = _cache_key(orgnr)

    entry = cache.get(cache_key)
    if entry is not None:
        cached_block = PeppolParticipant.model_validate(entry.payload)
        return cached_block.model_copy(
            update={
                "provenance": cached_block.provenance.model_copy(
                    update={"cached": True, "fetched_at": entry.fetched_at}
                )
            }
        )

    block = await _fetch_peppol_uncached(orgnr)

    if block.registered is True:
        cache.set(
            cache_key,
            block.model_dump(mode="json"),
            status="ok",
            fetched_at=block.provenance.fetched_at,
        )
    elif block.registered is False:
        cache.set(
            cache_key,
            block.model_dump(mode="json"),
            status="not_found",
            fetched_at=block.provenance.fetched_at,
        )
    # registered is None: never cached (DECISIONS.md D-046(d)).

    return block
