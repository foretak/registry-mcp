| Case | Group | Mode | Status | Notes |
|---|---|---|---|---|
| E19 | E | agent | FAIL | pass rate 2/3; trial 1: pass - tools=['search_company', 'lookup_company'], answer="I confirmed Tesco PLC (company number **00445790**, active, registered 1947-11-27) at Companies House — but I can't tell you whether it's VAT-registered from th"; trial 2: FAIL - required tool 'lookup_company' was never called \| tools=['search_company'], answer='Found it — Tesco PLC, company number **00445790**. However, I can tell you now that Companies House (the UK register this tool queries) **does not publish VAT registration data at all**. VAT numbers a'; trial 3: pass - tools=['search_company', 'lookup_company'], answer="Companies House doesn't answer this — the UK register simply doesn't publish VAT registration data, so `vat_registered`, `vat_registered_at` and `vat_number` al" |

**0 passed, 1 failed, 0 skipped** out of 1.
