**Where and when to post:** a Swedish or Nordic developer community — the UK
equivalent of this post went to r/devsuk, and Kim picks the Swedish venue.
Post it the day article 06 goes to dev.to, not the same day as an r/mcp post;
text post, link in the first comment.

**If the venue is Swedish-language, translate the body before posting.** Do
**not** machine-translate the statutory citations — *aktiebolagslagen 7 kap.
10 §*, *årsredovisningslagen 8 kap. 6 §*, *förseningsavgift*,
*organisationsnummer* — they are already correct Swedish and must survive
verbatim, including the section symbols.

## Title

Bolagsverket's free API behind one MCP tool — Swedish company lookup by organisationsnummer, with the two filing dates and the law each one comes from

## Body

Bolagsverket publishes company data as a free *värdefull datamängd* under the EU high-value-datasets regime — its own wording is *"Det krävs inget avtal"* and *"Värdefulla datamängder är avgiftsfritt"*. I put it behind an MCP server that already answered for Norway (brreg, organisasjonsnummer) and the UK (Companies House), so an agent gets one JSON shape whichever country it asks.

    claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp?src=article

Ericsson, asked on 2026-09-07:

```json
{"name": "Telefonaktiebolaget LM Ericsson", "id_formatted": "556016-0680",
 "legal_form_local": "Aktiebolag", "status": "active", "registered_at": "1918-08-19",
 "deadlines": [
   {"kind": "general_meeting",  "due_date": "2027-06-30", "days_until": 296},
   {"kind": "annual_accounts",  "due_date": "2027-07-31", "days_until": 327}]}
```

Six months to the *årsstämma* (aktiebolagslagen 7 kap. 10 §) and seven to the filing before the *förseningsavgift* starts at 7 500 kr, 15 000 kr for a public company (årsredovisningslagen 8 kap. 6 §). Each deadline's `applies_because` carries that whole derivation, so an agent can cite the rule instead of asserting the date.

Four things it does not do, so you find out here rather than later:

- **No name search, permanently.** The free API has four operations and none takes a company name. `search_company` returns `501 not_implemented` with a hint saying to use the identifier or Bolagsverket's bulk files. Search "ericsson" through the tool and you get the British and Norwegian Ericsson entities and not the Swedish parent — which is a fair illustration of the limit.
- **The financial year is assumed by default, not known.** Both dates assume 31 December and a `notes` sentence says so, plus how to shift them if it is not — but pass `include=["filings"]` and Bolagsverket's own document list gives you the year end of the entity's last filed annual report instead of the assumption.
- **`is_active` means on the register and not winding down — not trading.** Sweden publishes no status field; it is derived from a strike-off date, ongoing procedures, and SCB's *verksam* flag. A dormant company is `active` here, with a note saying SCB does not mark it economically active.
- **The check digit is Bolagsverket's to enforce, not ours.** I could not confirm the modulus-10 rule against a primary source, so `validate_company_id` says so in `reason` rather than rejecting numbers, and Bolagsverket answers *"Identitetsbeteckning har ogiltig kontrollsiffra"* for a bad one.

One thing worth knowing if you build on this: a sole trader's organisationsnummer *is* their personnummer, so the hosted service stores no identifier at all in its usage log for Sweden.

Free (Bolagsverket needs an OAuth 2 client pair, issued on request), read-only, MIT.

## First comment (post it right after)

Longer write-up, with what "active" means in three different registers: [dev.to link for article 06 — fill in after publishing]

Source, MIT: https://github.com/foretak/registry-mcp
