# Three company registers, one word: what "active" actually means in Norway, the UK and Sweden

An agent about to pay an invoice asks one question first: is this company still active? `registry-mcp` answers from three national registers — Brønnøysundregistrene / Enhetsregisteret (**brreg**) by **organisasjonsnummer** (orgnr, org.nr), **Companies House** by company number, and **Bolagsverket** by **organisationsnummer** — and returns the same field from all three:

```json
{"status": "active", "is_active": true}
```

The three registers do not mean the same thing by it. Only one of them even publishes it.

## Norway: four flags, and `active` is the absence of all four

brreg has no status field. It publishes `konkurs`, `underAvvikling`, `underTvangsavviklingEllerTvangsopplosning` and `slettedato`; `active` is what is left when none of them fires. The branch worth copying is the one *before* `active`:

```python
if bankrupt is None and under_liquidation is None and under_compulsory_liquidation is None:
    return StatusResult(CompanyStatus.UNKNOWN, "The registry record does not carry status flags.", False, [note])

return StatusResult(CompanyStatus.ACTIVE, "Registered and active in Enhetsregisteret.", True, [])
```

`None` is not `False`. A payload carrying no flags at all is `unknown`, never `active` — "the register did not say" and "the register said no" are different answers, and only one of them is safe to pay an invoice on.

## The UK: one status, which can say `active` while the company is on its way out

Companies House does publish a status, and it is mapped one to one — no derivation at all. It also publishes `company_status_detail`, separately, and the pair `active` + `active-proposal-to-strike-off` is both legal and common. That detail arrives as a `notes` sentence:

```
Companies House has published a proposal to strike this company off the register.
It is still active today, but it may be dissolved within about two months unless
the proposal is suspended. Do not treat it as a stable counterparty without
checking the filing history.
```

A UK `active` with a note is a different fact from a UK `active` without one. The enum cannot carry that difference, so the sentence does.

## Sweden: no status field, and three independent signals instead

Bolagsverket publishes nothing called a status. It publishes a strike-off date; a *list* of ongoing procedures (`KK` konkurs, `LI` likvidation, `FR` företagsrekonstruktion and more, which can arrive two at a time); and — from Statistics Sweden, in the same payload — a flag saying whether the entity is *economically active*. Live, today:

<!-- curl https://api.foretak.dev/v1/SE/company/5560160680 (excerpt) -->
```json
{
  "name": "Telefonaktiebolaget LM Ericsson",
  "status": "active",
  "status_detail": "Registered with Bolagsverket and not marked as struck off or in any winding-up or restructuring procedure.",
  "is_active": true
}
```

Read `status_detail`, not `status`. And read this twice: for Sweden, `is_active: true` means **on the register and not winding down**. It does not mean trading. Statistics Sweden's flag can say NEJ on a company in perfect standing — newly formed, dormant, a holding company with no operations — and that company is still `active` here, with a note saying so in plain English, and saying that SCB's question is a different one from being on the register.

We could have invented a `dormant` status. We didn't. That would change a shared enum for one country's convenience, and an agent would read it as a lifecycle claim about Norwegian and British companies that we have no data to make.

## What Sweden cost the design: nothing in `core/`

The enum is shared; the derivation is not. Each country folder derives its own status and writes the sentence naming the signal that decided it. Three registers, three unrelated derivations, one shape at the tool boundary.

Which is the argument for putting a register behind an MCP tool rather than a scraper. A scraper hands your agent the word. A tool can hand it the sentence.

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# or locally, over stdio: uvx registry-mcp
```

Data: Enhetsregisteret (NLOD 2.0), Companies House (Crown copyright), Bolagsverket and SCB (free under the EU high-value-datasets regulation — and Bolagsverket names no licence, so neither do we).

MIT: <https://github.com/foretak/registry-mcp>
