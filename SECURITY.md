# Security Policy

## Reporting a vulnerability

Email **hello@foretak.dev** with what you found, the affected endpoint or
tool, and steps to reproduce. Please do not open a public GitHub issue for a
security report until we've had a chance to look at it.

This is a small project with one maintainer, so there is no bug bounty and
no guaranteed SLA, but we treat every report seriously: expect an
acknowledgement within a few business days. We will credit reporters in the
fix's `CHANGELOG.md` entry, by name or anonymously — your choice — unless
you'd rather not be mentioned at all.

## Supported versions

| Version | Supported |
|---|---|
| 0.2.x | Yes |
| 0.1.x | No — upgrade to 0.2.x |

Only the latest published minor version of the `registry-mcp` / `brreg-mcp`
packages (PyPI and npm) and the hosted instance at `https://api.foretak.dev`
receive security fixes. There is no long-term-support branch. If you
self-host, track releases in [`CHANGELOG.md`](CHANGELOG.md).

## What this service does and does not do

- **Read-only.** Every tool and REST route reads a national business
  register and returns what it says. Nothing here writes to a register, and
  the service has no concept of a write operation to begin with —
  `readOnlyHint: true` on all five MCP tools is a description of the code,
  not a promise layered on top of it.
- **No inbound credentials.** Calling the hosted API or MCP server requires
  no API key, token or account. There is nothing to leak because there is
  nothing issued.
- **Outbound credentials, held by the operator, never by a caller.**
  Self-hosting a country whose upstream needs a key (today, only Companies
  House / `COMPANIES_HOUSE_API_KEY`) means setting that variable in your own
  environment. It is read at call time, sent only to that register's own API
  over HTTPS, and never logged, cached, returned in a response, or included
  in an error's `details` (`DECISIONS.md` D-017).
- **What is logged.** Every REST and MCP call may be recorded to a local
  SQLite file (`core/log.py`) for the `/v1/stats` dashboard: timestamp,
  surface, operation, country, the identifier or search string you passed
  (`query`) — the same data already visible in the request itself — latency,
  success/error code, and whether the answer was cached. Never a full
  request body, never headers, never an IP address, never a credential.
  Logging failures are swallowed rather than allowed to break a request.
- **No accounts, no profiles, no data beyond what the register publishes.**
  This service does not authenticate callers, does not build profiles of
  who is looking up which company, and does not combine register data with
  any other source. Business register data can be about a person — a sole
  proprietorship registered under someone's own name, for instance — and
  that is the national register's own disclosure, not something this
  project adds. See [`legal/terms.md`](legal/terms.md) §"Personal data" for
  what that means for anyone building on top of this service.
- **Two upstreams, and only two.** `data.brreg.no` (Norway) and
  `api.company-information.service.gov.uk` (United Kingdom) are the only
  external services this project's own code calls. Nothing else is
  contacted on your behalf.
- **Dependencies.** `uv.lock` pins every dependency; CI runs on every push.
  If a dependency vulnerability is reported against this project, it will be
  patched and released as a point release, noted in `CHANGELOG.md`.

For what this service does **not** promise about the data itself — accuracy,
freshness beyond the stated 24-hour cache, fitness for a KYC/AML/legal
decision — see [`legal/terms.md`](legal/terms.md), which is the terms of
use, not a security document, but answers the question "can I trust this
number" that usually comes up alongside "is this safe to call."
