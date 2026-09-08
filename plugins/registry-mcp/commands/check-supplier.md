---
description: Check a supplier or counterparty in the UK, Norwegian or Swedish business register — existence, current status and filing health, with what it does not establish
argument-hint: <company-number> [GB|NO|SE] [expected name]
---

# Check a supplier

The user asked to check: **$ARGUMENTS**

Read the arguments as: an identifier, an optional country code, and an optional name they
expect it to be. If no country was given, infer it from the identifier's shape — 9 digits is
Norway (`NO`), 10 digits is Sweden (`SE`), 8 characters with letters or leading zeros is the
United Kingdom (`GB`) — and **say which you inferred and why** before you report anything, so
a wrong guess is visible rather than silent. If the shape is ambiguous, ask.

Then run the counterparty check from the `company-check` skill, in this order:

1. `validate_company_id(id, country)` — free, no network call. If `valid` is false, stop and
   report `reason` and `hint` in plain English. Do not guess at a corrected identifier.
2. `lookup_company(id, country, include=["insolvency"])` for `GB`, or
   `lookup_company(id, country)` for `NO` and `SE`. The insolvency attachment is a second
   fetch and is worth it here: "are they being wound up" is exactly the question a supplier
   check is asking, and the base report's `registers` flag is not the same thing as the
   proceedings themselves. If `include` returns `bad_request`, read the hint — it names what
   that country does support — and retry without it.
3. `company_deadlines(id, country, today=<today's date>)`.

Report, in this order and no other:

- **Existence** — the registered name, and whether it matches the expected name if one was
  given. A near-match is not a match.
- **Status** — active or not, right now. If not active, lead with it and quote `status_detail`
  verbatim.
- **Filing health** — any deadline with a negative `days_until`, named, with how many days.
- **Every `notes` entry from every call, quoted verbatim and in full.**
- **Where it came from** — `source`, `source_url`, and `fetched_at` / `cached`.
- A closing section titled exactly **"What this does not establish"**, written as the
  `company-check` skill specifies. Do not shorten it and do not soften it: a clean register
  result is consistent with invoice fraud, not evidence against it.

Keep it short. This is a decision aid, not a report — the user is about to pay someone.
