**Where and when to post:** a UK developer sub (r/devsuk first choice), day 11 of the run, the day article 05 goes to dev.to; text post, link in the first comment.

## Title

Companies House behind one MCP tool, with the filing dates the register publishes per company

## Body

I wanted UK filing dates in Claude Code without writing another Companies House client, so I put the register behind an MCP server. One line:

    claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp

Deloitte LLP, asked on 2026-09-05:

```json
{
  "company_name": "DELOITTE LLP",
  "today": "2026-09-05",
  "deadlines": [
    {"kind": "confirmation_statement", "due_date": "2026-08-14", "days_until": -22},
    {"kind": "annual_accounts", "due_date": "2027-02-28", "days_until": 176}
  ]
}
```

`days_until: -22` is not a bug. Companies House leaves a passed confirmation-statement date in the past, and this passes it through rather than rolling it forward to an invented one. Negative means overdue as far as the register is concerned. Each deadline carries `applies_because`, which for the UK says the date is the register's own figure, not a calculation.

You bring your own Companies House API key. It is free from developer.company-information.service.gov.uk/get-started, and the limit is 600 requests per five minutes per key.

Two things it will not do. A UK company number has no check digit, so a typo that is still eight characters looks valid; only the lookup tells you. And Companies House publishes no VAT status, so that field is `null`, never `false`.

## First comment (post it right after)

Longer write-up: https://dev.to/fargeroddotcom/check-a-uk-supplier-at-companies-house-from-claude-code-and-the-same-tool-works-for-norway-4mk8

Source, MIT: https://github.com/foretak/registry-mcp
