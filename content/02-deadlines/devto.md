# Every filing deadline a Norwegian AS faces this quarter, in one tool call

"What do we owe Skatteetaten and Regnskapsregisteret next?" is a question your agent should not answer from memory. `registry-mcp` computes it from Brønnøysundregistrene / Enhetsregisteret (brreg) facts, by organisasjonsnummer (orgnr, org.nr).

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# or locally, over stdio: uvx registry-mcp
```

## The prompt

> Today is 1 October 2026. For org.nr 923 609 016, list every statutory filing deadline coming up, with the date and why it applies.

## The call

`company_deadlines(id="923609016", today="2026-10-01")`

Pass `today` explicitly. Deadlines are **computed, never fetched**, so the same entity and the same `today` always give the same list — which is what makes the answer testable instead of "whatever the server clock said".

<!-- uv run python content/call.py company_deadlines '{"id": "923609016", "today": "2026-10-01"}' (first deadline in full, rest trimmed) -->
```json
{
  "company_name": "EQUINOR ASA",
  "today": "2026-10-01",
  "deadlines": [
    {
      "kind": "payroll_report",
      "name": "Monthly payroll report (A-melding)",
      "local_name": "A-melding",
      "authority": "NAV / Skatteetaten (A-ordningen)",
      "statutory_date": "2026-10-05",
      "due_date": "2026-10-05",
      "rolled_forward": false,
      "period_label": "2026-09",
      "recurrence": "monthly",
      "days_until": 4,
      "applies_because": "This entity has reported employees and must file the monthly payroll report (a-melding) with NAV/Skatteetaten (a-opplysningsforskriften § 2-1)."
    },
    { "kind": "vat_return", "due_date": "2026-10-12", "statutory_date": "2026-10-10", "rolled_forward": true, "period_label": "2026 term 4 (Jul–Aug)", "days_until": 11 },
    { "kind": "shareholder_register_statement", "due_date": "2027-02-01", "statutory_date": "2027-01-31", "rolled_forward": true, "days_until": 123 },
    { "kind": "tax_return", "due_date": "2027-05-31", "days_until": 242 },
    { "kind": "general_meeting", "due_date": "2027-06-30", "days_until": 272 },
    { "kind": "annual_accounts", "due_date": "2027-07-31", "statutory_date": "2027-07-31", "rolled_forward": false, "days_until": 303 }
  ],
  "notes": [
    "Filing deadlines are computed assuming a calendar-year accounting period. Enhetsregisteret does not publish a company's accounting year. For a financial year ending between 1 January and 30 June, regnskapsloven § 8-3(1) sets a different deadline — 1 February, not 31 July — so a deviating year changes which rule applies, not just the date. The Ministry may also postpone the accounts deadline by up to one month by regulation (§ 8-3(1)). Verify against Regnskapsregisteret before relying on an annual date."
  ]
}
```

Two deadlines fall inside Q4: the a-melding on 5 October and the VAT return on 12 October.

**Quote `due_date`, not `statutory_date`.** The VAT return's statutory date is 10 October — a Saturday. `due_date` is 12 October and `rolled_forward: true` says why. The annual accounts deadline does **not** get the same treatment: 31 July 2027 is also a Saturday, but `rolled_forward` stays `false` and `due_date` stays 31 July, because regnskapsloven § 8-3(1) only waives the late fee if the accounts are dispatched *before* 1 August — rolling onto Monday would return a date the fee is already running. Roll-forward is decided per deadline, from that deadline's own source, not as a blanket rule.

**`applies_because` is the citation.** Nothing here is a legal-form guess: the a-melding appears because the entity reports employees, the VAT return because it's in Merverdiavgiftsregisteret. Each sentence also names the provision the date comes from. The docstring's rule is to quote that sentence rather than presenting a date as unconditional fact.

**Read `notes` before you send it to anyone.** `annual_accounts` and `general_meeting` assume a calendar-year accounting period, because Enhetsregisteret does not publish the real one — a financial year ending in the first half of the year has a **1 February** deadline instead of 31 July, not just a shifted date. `tax_return` and `shareholder_register_statement` don't carry that caveat: they run from the tax period, not the accounting year.

An empty `deadlines` list is a real answer too — a bankrupt, deleted or compulsorily-liquidated entity, a sub-unit, or a legal form the module has not classified. `notes` says which, and the service would rather omit an obligation than invent one.

Source: Enhetsregisteret, NLOD 2.0. Same JSON over MCP and REST.
Repo: <https://github.com/foretak/registry-mcp>
