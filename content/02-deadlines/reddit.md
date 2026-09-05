**Title:** MCP tool that computes Norwegian filing deadlines (brreg / Skatteetaten) instead of guessing them

`company_deadlines(id, today)` takes an organisasjonsnummer and a date and returns the next occurrence of every statutory deadline. Computed, never fetched — same inputs, same output, so you can test it.

<!-- uv run python content/call.py company_deadlines '{"id": "923609016", "today": "2026-10-01"}' (trimmed) -->
```json
{
  "company_name": "EQUINOR ASA",
  "today": "2026-10-01",
  "deadlines": [
    {"kind": "payroll_report", "due_date": "2026-10-05", "days_until": 4},
    {"kind": "vat_return", "statutory_date": "2026-10-10", "due_date": "2026-10-12", "rolled_forward": true},
    {"kind": "annual_accounts", "statutory_date": "2027-07-31", "due_date": "2027-07-31", "rolled_forward": false}
  ],
  "notes": ["Filing deadlines are computed assuming a calendar-year accounting period. ..."]
}
```

`due_date` rolls off weekends/holidays only where the deadline's own source allows it — two of six (annual accounts, general meeting) never do. `rolled_forward` says which. Each deadline carries `applies_because` — an unclassified legal form gets no deadline rather than an invented one.

`uvx registry-mcp` · MIT: github.com/foretak/registry-mcp
