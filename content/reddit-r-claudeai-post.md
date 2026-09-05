**Where and when to post:** r/ClaudeAI, day 3 of the content run, morning CET, never the same day as an r/mcp post; text post, links in the first comment only.

## Title

I asked Claude Code to check a supplier before paying an invoice

## Body

An invoice arrived from a Norwegian supplier I had not used before: NOK 4,000 plus 25% MVA. Two things I wanted to know before paying. Is the company still trading, and is it actually VAT-registered, since only registered businesses may charge MVA.

Install is one line:

    claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp

Then I pasted the org number off the invoice and asked. What came back:

```json
{
  "name": "EL ANSARI KONSULT",
  "status": "active",
  "vat_registered": true,
  "vat_registered_at": "2024-04-15",
  "vat_number": "NO833285602MVA",
  "fetched_at": "2026-09-05T14:44:24.836394Z"
}
```

The VAT number matched the invoice, the registration date was well before the invoice date, so I paid it.

`vat_registered_at` is the field I did not expect to need. A supplier can enter or leave the VAT register mid-relationship, and an invoice dated before that date charged VAT it could not collect.

What it did not tell me is whether the bank account on the invoice belongs to that company. That is the fraud that actually happens, and this does not catch it.

Has anyone found something that does?

## First comment (post it right after)

Write-up, with the two Norwegian tax cases that price skipping the check: https://dev.to/fargeroddotcom/check-a-norwegian-supplier-is-vat-registered-before-you-pay-the-invoice-pb9

MIT, and it runs locally over stdio: https://github.com/foretak/registry-mcp
