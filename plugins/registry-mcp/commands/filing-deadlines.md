---
description: What a UK, Norwegian or Swedish company must file next, when, and under which statutory provision
argument-hint: <company-number> [GB|NO|SE] [YYYY-MM-DD]
---

# Filing deadlines

The user asked about: **$ARGUMENTS**

Read the arguments as: an identifier, an optional country code, and an optional date to
compute from. Infer the country from the identifier's shape if it was not given (9 digits →
`NO`, 10 digits → `SE`, 8 characters → `GB`) and say which you inferred.

**Always pass `today` explicitly** — the date the user gave, or today's date if they gave
none — so `days_until` is reproducible and the answer can be written down.

1. `company_deadlines(id, country, today=...)`.
2. If the user asks *whether they file on time* — as opposed to *what is due next* — also
   call `lookup_company(id, country, include=["filings"])` and compare what was actually
   filed, and when, against the deadlines. That is the second question and it needs the
   second fetch; do not answer it from the deadline dates alone.

For every deadline, report:

- the `kind` and `local_name` (the register's own name for the form — "Confirmation statement
  (CS01)", not "the annual return");
- the `due_date` and `days_until`;
- **`applies_because`, quoted.** This is the point of the tool: it names the statutory
  provision the date came from, or states that Companies House publishes the date itself and
  it is the register's own figure rather than a calculation. Never replace it with "it's due
  then".

Then:

- A negative `days_until` means the register still shows the filing overdue. **Lead with it.**
- `rolled_forward` says whether the date moved off a weekend or a holiday. Norway rolls;
  Sweden does not. Do not invent a roll for a country that does not do it.
- Quote every `notes` entry verbatim. For Sweden in particular, both dates assume a financial
  year ending 31 December — the free dataset does not publish the year end — and the note says
  how to shift them. Presenting a Swedish date as certain without that caveat is wrong.
- An empty `deadlines` list is an answer: this legal form carries no filing duty this tool
  computes. Say so plainly; do not substitute a duty from another country.

Close with `source`, `source_url` and how fresh the answer is.
