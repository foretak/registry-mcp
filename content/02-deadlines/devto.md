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
      "applies_because": "This entity has reported employees and must file the monthly payroll report (a-melding) with NAV/Skatteetaten."
    },
    { "kind": "vat_return", "due_date": "2026-10-12", "statutory_date": "2026-10-10", "rolled_forward": true, "period_label": "2026 term 4 (Jul–Aug)", "days_until": 11 },
    { "kind": "shareholder_register_statement", "due_date": "2027-02-01", "statutory_date": "2027-01-31", "rolled_forward": true, "days_until": 123 },
    { "kind": "tax_return", "due_date": "2027-05-31", "days_until": 242 },
    { "kind": "general_meeting", "due_date": "2027-06-30", "days_until": 272 },
    { "kind": "annual_accounts", "due_date": "2027-08-02", "statutory_date": "2027-07-31", "rolled_forward": true, "days_until": 305 }
  ],
  "notes": [
    "Filing deadlines are computed assuming a calendar-year accounting period. A company with a deviating accounting year (avvikende regnskapsår) will have different actual dates, and Enhetsregisteret does not publish which companies those are."
  ]
}
```

Two deadlines fall inside Q4: the a-melding on 5 October and the VAT return on 12 October.

**Quote `due_date`, not `statutory_date`.** The VAT return's statutory date is 10 October — a Saturday. `due_date` is 12 October and `rolled_forward: true` says why. Same for the annual accounts: 31 July 2027 is a Saturday, so the real date is 2 August.

**`applies_because` is the citation.** Nothing here is a legal-form guess: the a-melding appears because the entity reports employees, the VAT return because it's in Merverdiavgiftsregisteret. The docstring's rule is to quote that sentence rather than presenting a date as unconditional fact.

**Read `notes` before you send it to anyone.** The list assumes a calendar-year accounting period, because Enhetsregisteret does not publish who has a deviating one. Every annual date above inherits that assumption.

An empty `deadlines` list is a real answer too — a bankrupt, deleted or compulsorily-liquidated entity, a sub-unit, or a legal form the module has not classified. `notes` says which, and the service would rather omit an obligation than invent one.

Source: Enhetsregisteret, NLOD 2.0. Same JSON over MCP and REST.
Repo: <https://github.com/foretak/registry-mcp>
