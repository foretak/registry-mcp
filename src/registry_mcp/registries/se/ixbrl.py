"""Bolagsverket's filed annual report — the inline-XBRL extractor.

**Read `ix:nonFraction`. Never read `ix:nonNumeric`.** That is the whole of
this module's privacy story, and it is written here as the module's first
rule rather than as a per-concept blocklist, because Sweden **renamed its
own signature concepts** between the two taxonomy generations this module
is measured against — `se-gen-base:UnderskriftArsredovisningForetradareTilltalsnamn`
/ `…Efternamn` (2017-09-30) became `se-gen-base:UnderskriftHandlingTilltalsnamn`
/ `…Efternamn` (2021-10-31), with a third pair,
`se-comp-base:UnderskriftFaststallelseintygForetradare{Tilltalsnamn,Efternamn,Foretradarroll}`,
present under both generations (`tasks/T52-recon.md` Fact 5,
`tasks/T55-recon.md`). A blocklist keyed on those names would have gone
stale the day the taxonomy renamed them and nobody would have noticed,
because the failure is silent — a name reaching a field that was never
supposed to carry one. **This module's element filter — every function
below that reads a fact's numeric value only ever iterates `ix:nonFraction`
elements — makes that failure structurally unreachable regardless of what a
concept happens to be called**, in either language, in either country's
taxonomy, this year or after the next rename nobody has scheduled yet.
`ix:nonNumeric` elements are used only to read `link:schemaRef`'s href (not
a fact at all) and are otherwise never inspected — not their names, not
their presence, and never their text content.

**`currency` comes from the unit, never from a concept.** Every
`ix:nonFraction` fact's `@unitRef` resolves to an `xbrli:unit/xbrli:measure`
whose text is `iso4217:<CODE>` — verified against a namespace declaration,
never against the literal prefix string, so a filer who binds a different
prefix to the ISO 4217 namespace (nothing in XML forbids it) still resolves
correctly. **`se-cd-base:Redovisningsvaluta` is never read anywhere in this
module** — Sweden renamed it to `se-cd-base:RedovisningsvalutaHandlingList`
*and* re-typed its value from the string `"SEK"` (2020, 2022) to the enum
member `se-mem-base:ValutaSvenskaKronorMember` (2025) between the same two
taxonomy generations, so a parser keyed on it builds nothing at all on the
current taxonomy (`tasks/T52-recon.md` Fact 1, D-043(d)). `grep -rn
"Redovisningsvaluta" src/` must return nothing outside this comment.

**Concept identity is by local name, never by the qualified prefix.**
`tasks/T52-recon.md` Fact 1 found the *British* FRC taxonomy's core-schema
prefix changes between taxonomy versions (`uk-core` vs bare `core` for the
same namespace) and warned to "match on the local name (or the namespace
URI), never on the prefix" — a lesson this module applies here even though
it was learned on the other register: every wanted Swedish concept is
matched on the text after the last `:` in `@name`, never on the `se-gen-base`
prefix string, which is measured stable (`tasks/T55-recon.md`) but is a
filer's own choice under XML's namespace rules and not a guarantee.

**Contexts, periods and the "latest period" rule.** A context is read into
its period bounds (`instant`, or `startDate`/`endDate`) and a boolean for
whether `xbrldi:explicitMember` or `xbrldi:typedMember` appears anywhere
inside it (segment or scenario). **Only dimension-free contexts are ever
candidates for "the latest period"** — zero dimensions was Part 0's premise
for K2 and holds on every K3 taxonomy specimen checked (`tasks/T55-recon.md`);
this module does not merely assume it, it structurally cannot select a
dimensioned context as the reporting period, so a note-level breakdown
(committed here or added later by a taxonomy this module has not seen) is
excluded rather than mistaken for the whole-entity total. The *latest*
period end is the maximum date among every dimension-free context's instant
or duration end; income-statement facts come from the duration context
whose own end equals it, balance-sheet facts from the instant context whose
own instant equals it — one rule, both statement types, and it is exactly as
robust to a five-year `Flerårsöversikt` overview table (period0..period4 on
this session's K3 specimen, tagging the same concepts five times over) as it
is to the two-year case K2's own recon measured: the maximum simply picks
the newest one, however many older ones exist beside it.

**`@sign="-"` and `@scale` are both applied; `@format` is read to parse the
digit string.** Every wanted-concept fact measured across five real K2
filings (`tasks/T52-recon.md`, `tasks/T55-recon.md`) and two K3 taxonomy
specimens carries `@format="ixt:numcomma"` or `@format="ixt:numspacecomma"`
— a **comma** decimal point, a **space** (or no) thousands separator, the
opposite convention from the `ixt2:numdotdecimal` the British recon met —
and `@scale="0"` on every one of them, with `@sign="-"` genuinely present on
loss and negative-equity figures. **No other `@format` has ever been
measured on a wanted concept**, so this module recognises exactly those two
and nothing else: a fact tagged with an unrecognised format is not guessed
at, it is simply not extracted, which degrades that one field to absent
rather than to a wrong number (D-009, D-043(f)). `@scale` is exercised on a
hand-built fixture (`tests/fixtures/se_ixbrl_scale_handbuilt.xhtml`) because
no real or specimen document measured carries a non-zero one — recorded here
so nobody mistakes the hand-built fixture for a filing.

**On the K3 taxonomy specifically: validated against Bolagsverket's own K3
taxonomy specimens and against zero live K3 filings.** `tasks/T55-recon.md`
records why: this task's entire four-call `POST /dokumentlista` budget was
spent on four companies legally too large to file under K2 at all, and
every one of them has an empty digital-filing history, so no live K3
document was ever read. The two `taxonomier.se` specimens measured show 16
of 17 D-043(c) concepts identical to K2's under `se-gen-base`, zero
dimensioned contexts, and `unitRef` resolving to `iso4217:SEK` exactly as
K2 does — which is why this module is shipped for K3 at all — but a
specimen is the taxonomy publisher's own demonstration of a conformant
document, not a real filer's software producing one, and it cannot stand in
for the sign, completeness or presentation surprises only a real filing can
contain (`tasks/T52-recon.md` Fact 6 is the whole reason that distinction
matters). `registries/se/financials.py` carries the caller-facing half of
this caveat as a `notes` sentence on every K3 block; this paragraph is its
one required appearance in this module's own docstring
(`tasks/T55.md`'s continuation brief, rule 1).

**Nothing here reads or names `se-gen-base:Soliditet` or any other ratio
concept.** There is no code path in this module that could relay one: the
wanted-concept lookup is keyed by an explicit, closed list of local names
`registries/se/financials.py` owns, and a concept absent from that list is
simply never looked up, `Soliditet` included. `grep -rn "Soliditet" src/`
must return nothing outside a comment explaining why.
"""

from __future__ import annotations

import contextlib
import zipfile
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

__all__ = [
    "IXBRLDocument",
    "MultiEntryZipError",
    "NumericFact",
    "parse",
    "schema_ref_says",
    "unzip_single_xhtml",
]


class MultiEntryZipError(Exception):
    """A Bolagsverket `/dokument` zip did not contain exactly one entry.

    A2/A1's "report, not guess": every zip measured across every document
    this project has read (six K2 filings, this task's two K3 specimens)
    holds exactly one entry, so this is reported rather than resolved by
    picking one arbitrarily.
    """

    def __init__(self, entry_count: int) -> None:
        self.entry_count = entry_count
        super().__init__(f"expected exactly one entry in the zip, found {entry_count}")


def unzip_single_xhtml(zip_bytes: bytes) -> bytes:
    """The bytes of the zip's single entry. Raises :class:`MultiEntryZipError`
    for anything but exactly one entry — never picks the first and moves on."""
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise MultiEntryZipError(len(names))
        return zf.read(names[0])


#: `@format` values measured on a wanted concept across every K2 filing and
#: K3 specimen this project has read (module docstring). Both use a comma
#: decimal point; the only difference is whether digit groups are separated
#: by a space. Anything else is not guessed at (D-009).
_COMMA_DECIMAL_FORMATS = frozenset({"ixt:numcomma", "ixt:numspacecomma"})


def _local(tag: str) -> str:
    """The element/attribute local name, stripping a `{namespace}` prefix
    `xml.etree.ElementTree` adds to every tag it resolves."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _qname_local(raw: str) -> str:
    """The text after the last `:` in a QName-shaped attribute *value* such
    as `@name="se-gen-base:Nettoomsattning"` or `@unitRef`'s measure text
    `"iso4217:SEK"`. Attribute and text **values** are not XML names, so
    `ElementTree` never expands them the way it expands element/attribute
    tags — this function does the equivalent lookup by hand, and, per the
    module docstring, deliberately never checks the prefix half against
    anything but a resolved namespace URI where that matters (currency)."""
    return raw.rsplit(":", 1)[-1] if ":" in raw else raw


def _collect_namespaces(xhtml_bytes: bytes) -> dict[str, str]:
    nsmap: dict[str, str] = {}
    for _event, (prefix, uri) in ET.iterparse(BytesIO(xhtml_bytes), events=("start-ns",)):
        nsmap[prefix] = uri
    return nsmap


def _parse_number(
    raw_text: str, fmt: str | None, scale: str | None, sign: str | None
) -> float | None:
    """Apply `@format`, `@scale` and `@sign` to a fact's text content.
    `None` when `@format` is not one of the two comma-decimal forms this
    module has ever measured (module docstring) — an unparseable figure is
    dropped, never guessed."""
    if fmt not in _COMMA_DECIMAL_FORMATS:
        return None
    cleaned = raw_text.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if scale is not None:
        with contextlib.suppress(ValueError):
            value *= 10 ** int(scale)
    if sign == "-":
        value = -value
    return value


@dataclass(frozen=True)
class _Context:
    is_instant: bool
    instant: date | None
    start: date | None
    end: date | None
    has_dimension: bool

    @property
    def period_end(self) -> date | None:
        return self.instant if self.is_instant else self.end


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        # `YYYY-MM-DD` is every date this endpoint and this document format
        # have ever produced; a `T…` suffix (seen on `registreringstidpunkt`
        # elsewhere in this registry, never inside a context here) still
        # parses via the first 10 characters rather than raising.
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_contexts(root: ET.Element) -> dict[str, _Context]:
    contexts: dict[str, _Context] = {}
    for el in root.iter():
        if _local(el.tag) != "context":
            continue
        context_id = el.attrib.get("id")
        if context_id is None:
            continue
        has_dimension = any(
            _local(sub.tag) in ("explicitMember", "typedMember") for sub in el.iter()
        )
        period_el = next((sub for sub in el.iter() if _local(sub.tag) == "period"), None)
        instant = start = end = None
        if period_el is not None:
            for sub in period_el:
                name = _local(sub.tag)
                if name == "instant":
                    instant = _parse_date(sub.text)
                elif name == "startDate":
                    start = _parse_date(sub.text)
                elif name == "endDate":
                    end = _parse_date(sub.text)
        contexts[context_id] = _Context(
            is_instant=instant is not None,
            instant=instant,
            start=start,
            end=end,
            has_dimension=has_dimension,
        )
    return contexts


def _parse_units(root: ET.Element, nsmap: dict[str, str]) -> dict[str, str | None]:
    """unit id -> ISO 4217 currency code, or `None` when the unit's measure
    does not resolve to the ISO 4217 namespace (a non-monetary unit such as
    `procent`/`xbrli:pure` or a headcount unit — both measured on real
    filings, module docstring)."""
    iso4217_uri = "http://www.xbrl.org/2003/iso4217"
    units: dict[str, str | None] = {}
    for el in root.iter():
        if _local(el.tag) != "unit":
            continue
        unit_id = el.attrib.get("id")
        if unit_id is None:
            continue
        measure_el = next((sub for sub in el.iter() if _local(sub.tag) == "measure"), None)
        code: str | None = None
        if measure_el is not None and measure_el.text:
            text = measure_el.text.strip()
            if ":" in text:
                prefix, _, local_part = text.partition(":")
                if nsmap.get(prefix) == iso4217_uri:
                    code = local_part
            units[unit_id] = code
        else:
            units[unit_id] = None
    return units


@dataclass(frozen=True)
class NumericFact:
    """One `ix:nonFraction` fact, fully resolved: `@format`/`@scale`/`@sign`
    already applied to `value`, and `currency` already resolved through the
    unit (`None` if the unit did not resolve to ISO 4217 — e.g. a percentage
    or a headcount, which this dataclass can represent but
    `financials.py` never asks for by name)."""

    value: float
    currency: str | None
    context_id: str


@dataclass(frozen=True)
class IXBRLDocument:
    """The parsed result of one Bolagsverket annual-report XHTML. Carries no
    `ix:nonNumeric` content of any kind — not a name, not a count, not a tag
    — per the module docstring's one-line rule."""

    schema_refs: tuple[str, ...]
    latest_period_end: date | None
    latest_period_start: date | None
    _facts_by_concept: dict[str, list[NumericFact]] = field(repr=False)
    _contexts: dict[str, _Context] = field(repr=False)

    def latest(self, concept_local_name: str) -> NumericFact | None:
        """The fact for `concept_local_name` at :attr:`latest_period_end`, or
        `None` when this document does not tag that concept at that period
        (D-043(f): absent, never a guessed zero). When more than one fact
        matches (a figure retagged in a summary note, measured on real
        filings), the first one found is returned; every instance measured
        agrees in value, and this module does not additionally verify that,
        which would be arithmetic D-043(e) does not ask for."""
        if self.latest_period_end is None:
            return None
        # A duration context is matched on its *end* only (the module
        # docstring's "latest period" rule) — `latest_period_start` is
        # derived from this same context in `parse()` and is never used to
        # filter it a second time here, which would just be checking a
        # value against itself.
        for fact in self._facts_by_concept.get(concept_local_name, ()):
            context = self._contexts.get(fact.context_id)
            if context is None or context.has_dimension:
                continue
            if context.period_end == self.latest_period_end:
                return fact
        return None


def schema_ref_says(schema_refs: Any, framework: str) -> bool:
    """`True` when `"/{framework}/"` (lowercased `"k2"`/`"k3"`) appears in
    any of `schema_refs`'s href paths. A K3 koncernredovisning imports the
    entity schema alongside its own (`tasks/T55-recon.md`: both `/k3/...`
    and `/k3k/...` appear in that specimen's `schemaRef`s), so checking for
    `/k3/` alone correctly classifies both K3 profiles; it is never used to
    tell them apart (see :func:`registries.se.financials`'s ``scope``
    handling, which does not attempt that distinction on this evidence)."""
    needle = f"/{framework.lower()}/"
    return any(needle in (href or "").lower() for href in schema_refs)


def parse(xhtml_bytes: bytes) -> IXBRLDocument:
    """Parse one Bolagsverket annual-report XHTML. Pure, synchronous, no I/O.

    Reads `link:schemaRef` hrefs, every `xbrli:context`, every `xbrli:unit`,
    and every `ix:nonFraction` fact's `@name`/`@contextRef`/`@unitRef`/
    `@format`/`@scale`/`@sign` and text content. **Never reads an
    `ix:nonNumeric` element for any purpose** (module docstring).
    """
    nsmap = _collect_namespaces(xhtml_bytes)
    root = ET.fromstring(xhtml_bytes)

    schema_refs: list[str] = []
    for el in root.iter():
        if _local(el.tag) != "schemaRef":
            continue
        href = next((v for k, v in el.attrib.items() if _local(k) == "href"), None)
        if href is not None:
            schema_refs.append(href)

    contexts = _parse_contexts(root)
    units = _parse_units(root, nsmap)

    facts_by_concept: dict[str, list[NumericFact]] = {}
    for el in root.iter():
        if _local(el.tag) != "nonFraction":
            continue
        name = el.attrib.get("name")
        context_id = el.attrib.get("contextRef")
        if not name or not context_id:
            continue
        value = _parse_number(
            "".join(el.itertext()),
            el.attrib.get("format"),
            el.attrib.get("scale"),
            el.attrib.get("sign"),
        )
        if value is None:
            continue
        unit_ref = el.attrib.get("unitRef")
        currency = units.get(unit_ref) if unit_ref is not None else None
        local_name = _qname_local(name)
        facts_by_concept.setdefault(local_name, []).append(
            NumericFact(value=value, currency=currency, context_id=context_id)
        )

    latest_period_end: date | None = None
    for context in contexts.values():
        if context.has_dimension or context.period_end is None:
            continue
        if latest_period_end is None or context.period_end > latest_period_end:
            latest_period_end = context.period_end

    latest_period_start: date | None = None
    if latest_period_end is not None:
        for context in contexts.values():
            if (
                not context.is_instant
                and not context.has_dimension
                and context.end == latest_period_end
                and context.start is not None
            ):
                latest_period_start = context.start
                break

    return IXBRLDocument(
        schema_refs=tuple(schema_refs),
        latest_period_end=latest_period_end,
        latest_period_start=latest_period_start,
        _facts_by_concept=facts_by_concept,
        _contexts=contexts,
    )
