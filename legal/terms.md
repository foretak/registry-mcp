# Terms of use

_Last updated: 2026-09-04. Applies to the hosted API and MCP server at
`api.foretak.dev` and to the `registry-mcp` / `brreg-mcp` packages._

These terms are short on purpose. If something here is unclear, ask before you
build on it.

## What this service is

`registry-mcp` reads **public national business registers** and returns what
they say, in one shape, over a REST API and an MCP server. It adds no facts of
its own. Filing deadlines are the one thing it *computes* rather than reads —
see [Computed deadlines](#computed-deadlines) below.

## Where the data comes from

Norwegian data comes from **Enhetsregisteret**, published as open data by
**Brønnøysundregistrene**, under the
**[Norsk lisens for offentlige data (NLOD) 2.0](https://data.norge.no/nlod/no/2.0)**.

Every response we return carries `source`, `source_url` and `license` so the
attribution travels with the data.

**NLOD requires attribution, and that obligation passes to you.** If you
republish, display or redistribute this data, credit Brønnøysundregistrene as
the source — for example:

> Contains data from Enhetsregisteret, Brønnøysundregistrene, under NLOD 2.0.

We are **not affiliated with, endorsed by, or acting on behalf of
Brønnøysundregistrene**, Skatteetaten, or any other authority named in a
response.

## No warranty

The service is provided **as is, with no warranty of any kind**, express or
implied — including accuracy, completeness, timeliness, or fitness for a
particular purpose.

Concretely:

- Responses may be **stale**. We cache upstream responses for up to 24 hours, and
  the register itself lags real-world events.
- A field the register does not publish comes back as `null`, meaning **"we do
  not know"** — never "no".
- Field mappings, English labels and derived flags are our interpretation of the
  register's data and may be wrong.
- The register itself can be wrong or out of date. We reproduce it; we do not
  correct it.

**For anything that carries legal or financial consequence — paying an invoice,
signing a contract, a KYC or AML decision, a filing — verify against the
official register before you act.** The authoritative source is
[data.brreg.no](https://data.brreg.no), and every response gives you the
`source_url` to check.

To the fullest extent permitted by law, we accept no liability for any loss
arising from use of this service or reliance on its output.

## Computed deadlines

`company_deadlines` and `/v1/{country}/company/{id}/deadlines` **compute** dates
from statutory rules and the entity's registered attributes. They are an
estimate, not a notice from an authority.

They assume a **calendar-year accounting period** — the register does not
publish which companies have a deviating one (*avvikende regnskapsår*), so a
company that does will have different real dates. Each deadline states its
assumption in `applies_because`, and each report repeats the caveat in `notes`.
Every computed Norwegian deadline also names its own statutory basis in
`applies_because`; two of the six — the annual accounts filing and the
ordinary general meeting — deliberately never move off a weekend or public
holiday, because the law behind them has no rule that would allow it.
Read them before quoting a date to anyone.

Deadlines are not tax, accounting or legal advice.

## Rate limits and fair use

- **60 requests per minute per IP** on the hosted API. Exceeding it returns
  `429 rate_limited`; back off and retry rather than retrying immediately.
- Cache on your side. A response is good for a day for almost every purpose, and
  we already cache upstream for 24 hours.
- **Do not bulk-download the register through this service.** Brønnøysundregistrene
  publishes complete datasets for that, and using them is faster for you and
  kinder to everyone: <https://data.brreg.no/enhetsregisteret/oppslag/enheter>
- Set `REGISTRY_MCP_CONTACT_EMAIL` when self-hosting. It goes into the
  `User-Agent` we send upstream, which is what the register asks of API clients;
  anonymous clients may be throttled or blocked at their end.
- We may throttle, block or withdraw access to protect the service or to comply
  with the upstream register's terms. The hosted endpoint is a convenience, not
  a commitment — it may change or go away. Self-host if you need a guarantee;
  the code is MIT licensed.

## Personal data

Business register data is public, but some of it is about **people** — for
example a sole proprietorship (*enkeltpersonforetak*) whose registered name is a
person's name, or contact details registered by the entity.

We do not create profiles, enrich, or combine this data with any other source,
and we log only what is needed to run and monitor the service. **If you process
this data further, you are the controller for that processing** and the GDPR
obligations are yours, not ours.

For a request concerning personal data in a register record, contact the
register directly — we cannot change what Enhetsregisteret publishes. For
anything concerning this service's own logs or cache, write to us.

## Your code, our code

This project's source code is **MIT licensed** (see [`LICENSE`](../LICENSE)).
The MIT licence covers the software. It does not cover the register data, which
is governed by NLOD 2.0 as described above.

## Changes

These terms may change; the date at the top says when they last did. Material
changes will be noted in the repository's release notes.

## Contact

**hello@foretak.dev**

Bugs and corrections are better as issues:
<https://github.com/foretak/registry-mcp/issues>
