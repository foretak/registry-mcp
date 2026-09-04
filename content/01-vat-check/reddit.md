**Title:** Stop your agent paying VAT to a supplier that isn't VAT-registered (Norway, brreg MCP)

`registry-mcp` puts Brønnøysundregistrene / Enhetsregisteret behind an MCP tool. Give it an organisasjonsnummer (orgnr), get the company back.

<!-- uv run python content/call.py lookup_company '{"id": "833285602"}' (excerpt) -->
```json
{
  "name": "EL ANSARI KONSULT",
  "status": "active",
  "vat_registered": true,
  "vat_registered_at": "2024-04-15",
  "vat_number": "NO833285602MVA",
  "registers": {"mvaregisteret": true}
}
```

`vat_number` is what must appear on the invoice; `vat_registered_at` catches invoices dated before the supplier could legally charge MVA.

Two failure modes worth knowing: `validate_company_id` returns `valid: false` with a `hint` (never throws) for a bad check digit, and a well-formed-but-unissued number like `999999999` raises `not_found`. Different problems, different fixes.

`claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp` — or `uvx registry-mcp`.

Source: NLOD 2.0. MIT: github.com/foretak/registry-mcp
