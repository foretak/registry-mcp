# The company number that is also a person's national ID — and what it cost our logs

Adding Sweden to `registry-mcp` — a company registry MCP server that already answered for Brønnøysundregistrene / Enhetsregisteret (**brreg**) by **organisasjonsnummer** (orgnr, org.nr) and for Companies House by company number — broke an assumption every one of those two countries had let us keep.

**A Swedish sole trader's company number is their personnummer.** Not derived from it. Not linked to it. It *is* it: the same twelve digits that identify a living human being to the Swedish state are that person's identifier in the company register. `validate_company_id` has to accept twelve digits alongside the usual ten for exactly this reason.

So the identifier we take as a routine argument, log as a routine parameter, and put in a URL and a cache key as an implementation detail is, for some fraction of Swedish calls, a national identity number.

## What Bolagsverket does about it, and what it told us

Bolagsverket's free API takes the identifier in a **POST body**, not a path segment. For a read-only lookup that is a strange design — until you notice that a URL is the most-copied string in computing. It lands in the access log, the proxy log, the browser history, the `curl` in the bug report and the screenshot in the ticket. A body does not. We took that as a specification rather than an inconvenience.

## What changed on our side

A country now declares one thing about itself:

```python
id_may_be_personal: ClassVar[bool] = False
"""True when an identifier this registry accepts can be a natural person's
national identity number (Sweden: a sole trader's organisationsnummer is
their personnummer). The surfaces consult it before logging; the module
does not.
"""
```

and one function is the only place that reads it:

```python
def loggable_query(country: str | None, query: str | None) -> str | None:
    ...
    return None if registry.id_may_be_personal else query
```

Both surfaces — the REST route and the MCP tool — call that one function before writing anything. Adding a country that sets the flag changes no route and no tool. The usage log still records the country, the route, the time, the outcome and the `User-Agent`; for such a country it records **no identifier at all**.

Three smaller things went with it, because a chokepoint is worthless if the value leaks around it: the web server's access log is off, the unhandled-exception log records the route *template* rather than the request path, and a cache failure logs a key prefix rather than the key. `legal/privacy.md` states all of it.

Verifiable rather than asserted: on the first day in production the Swedish rows in the usage log carried a null query, while Norwegian rows still carried `923609016`.

## The other thing a Swedish identifier taught us

`valid: true` does not mean what you think, and it means something different in each country:

<!-- curl https://api.foretak.dev/v1/SE/validate/5560212524 -->
```json
{
  "input": "5560212524", "valid": true, "formatted": "556021-2524",
  "reason": "Well-formed organisationsnummer for SE. … this number does not satisfy the modulus-10 check digit that Swedish identifiers are generally described as carrying. registry-mcp has not been able to confirm that rule against a primary source, as of 2026-09, so the number is not rejected here — but Bolagsverket validates a check digit server-side and may answer 'Identitetsbeteckning har ogiltig kontrollsiffra'."
}
```

And it does:

<!-- curl https://api.foretak.dev/v1/SE/company/5560212524 -->
```json
{"error": {"code": "invalid_id",
  "message": "Bolagsverket rejected 5560212524 as a malformed identitetsbeteckning.",
  "hint": "Bolagsverket validates a check digit that this module does not: it answers 'Identitetsbeteckning har ogiltig kontrollsiffra' for a number of the right length whose check digit is wrong. …"}}
```

Norway's MOD11 is enforced, so a bad orgnr never reaches brreg. A UK company number has no check digit to enforce. Sweden has one we could not confirm against a primary source — so rather than implement a checksum from memory and reject real companies, we say so in `reason` and let Bolagsverket be the authority on its own numbers.

Writing "we could not source this rule" into a user-visible field is uncomfortable. It still beats a false rejection.

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# or locally, over stdio: uvx registry-mcp
```

MIT: <https://github.com/foretak/registry-mcp>
