# Privacy policy — registry-mcp hosted service (api.foretak.dev)

*Draft written 2026-09-05 for Kim's review; effective once published at a public URL. Plain facts, no legal boilerplate. Everything below describes what the software actually does today; change the software, change this page.*

## Who runs it

The hosted endpoint at `https://api.foretak.dev` (REST and MCP) is operated by EL ANSARI KONSULT, organisasjonsnummer 833285602, Oslo, Norway. Contact: hello@foretak.dev. The hosting provider is Railway (region EU West / Amsterdam). The same software can be run by anyone locally (`uvx registry-mcp`); a local copy sends nothing to us.

## What the service does

It looks up publicly registered companies in national business registers on your behalf and returns the register's data in one JSON shape. Today: Norway (Brønnøysundregistrene / Enhetsregisteret, `data.brreg.no`) and the United Kingdom (Companies House, `api.company-information.service.gov.uk`). It does not perform sanctions, PEP or adverse-media screening and does not verify bank accounts.

## What we receive and keep

- **Your request.** The country, the identifier or search text you send, the tool or route used, the time, the outcome (success or error code), and your client's `User-Agent` string. These are written to a usage log so we can see whether the service is used and whether it fails. For a country where the identifier can be a natural person's number — today, Sweden — the identifier itself is not written to that log; the country, route, time, outcome and `User-Agent` still are. The log is kept on the server's storage volume and is not shared. We do not log IP addresses in that log; the hosting provider's own access logs (which do include IP addresses) are retained by Railway for a short period under Railway's terms.
- **Register responses.** Answers from the registers are cached for up to 24 hours so repeated lookups do not hit the registers again. The cache is on the same volume and expires automatically.
- **Nothing else.** No accounts, no cookies, no analytics scripts, no advertising, no payment data. The homepage playground calls the same API only when you press the button.

## Personal data in register records

National registers publish data about natural persons: the name and address of a sole proprietor (enkeltpersonforetak), and, in the UK, officers' names in the public record (which this service does not currently return). When a record concerns a sole proprietorship, the response carries a note saying so. We return what the register publishes, cache it for up to 24 hours, and do not enrich, profile or resell it. If you are a sole proprietor and object to your register record being served through this service, write to hello@foretak.dev; the authoritative way to change the record itself is through the register that publishes it.

## What we send to third parties

Your lookup is forwarded to the relevant register (Brønnøysundregistrene or Companies House) as an API request identifying our service and a contact address in the `User-Agent`, as the registers ask of API clients. For the UK we send our own Companies House API key with the request; your identity is not part of it. Nothing is sent anywhere else.

## Legal basis and licences

Register data is redistributed under the registers' own terms: Norway under the Norwegian Licence for Open Government Data (NLOD 2.0), the UK under Crown copyright terms permitting reuse. Every response carries `source`, `source_url` and `license` so you can cite the origin. Our processing of your request data rests on our legitimate interest in operating and improving a public service; the data is minimal and never used for marketing.

## Retention

Cache entries: up to 24 hours. Usage log: kept for the life of the service for aggregate statistics; entries older than 12 months may be deleted without notice. Provider access logs: per Railway's retention.

## Your rights

Under the GDPR you may ask what we hold about a request you made (which is little, and not linked to you by name), and ask for its deletion. Write to hello@foretak.dev with the approximate time and the identifier you looked up. The supervisory authority in Norway is Datatilsynet.

## Changes

This page is versioned in the public repository at https://github.com/foretak/registry-mcp/blob/main/legal/privacy.md; the commit history is the change log.
