**Title:** Three company registers, three completely different meanings of "active" — brreg, Companies House and Bolagsverket behind one MCP tool

`registry-mcp` now answers for Sweden as well as Norway (brreg, organisasjonsnummer/orgnr) and the UK. All three return `"status": "active"`. None of them means the same thing by it.

**Norway** publishes four flags (`konkurs`, `underAvvikling`, `underTvangsavviklingEllerTvangsopplosning`, `slettedato`); `active` is the absence of all four — and all four *missing* rather than false maps to `unknown`, because absence is not a negative.

**The UK** publishes a status, mapped one-to-one. It can read `active` while `company_status_detail` says a strike-off has already been proposed; that arrives as a `notes` sentence, because the enum cannot hold it.

**Sweden** publishes no status field at all — three signals get combined: a strike-off date, ongoing winding-up/restructuring procedures, and Statistics Sweden's "economically active" flag.

<!-- curl https://api.foretak.dev/v1/SE/company/5560160680 (excerpt) -->
```json
{"name": "Telefonaktiebolaget LM Ericsson", "status": "active",
 "status_detail": "Registered with Bolagsverket and not marked as struck off or in any winding-up or restructuring procedure."}
```

So for `SE`, `is_active` means *on the register and not winding down* — **not** trading. A dormant Swedish company is `active` here, with a note saying SCB does not mark it economically active.

Shared enum, per-country derivation, no `core/` change. `uvx registry-mcp`, or the hosted `https://api.foretak.dev/mcp?src=article`. MIT: github.com/foretak/registry-mcp
