---
description: Resolve a list or spreadsheet of UK, Norwegian and Swedish company numbers to registered name, status, address, industry code and VAT registration, one row each with a source URL
argument-hint: <file path, or paste the identifiers> [--include filings]
---

# Enrich a company list

The user gave: **$ARGUMENTS**

If that is a file path, read it. If it is a pasted list, use it directly. If it is neither,
ask for the identifiers.

## Before you spend a single lookup

1. Pull out the identifiers. Note which column they came from, and keep every other column —
   the output must join back to the user's own rows.
2. Determine each row's country. Use an explicit country column if there is one; otherwise
   infer from shape (9 digits → `NO`, 10 digits → `SE`, 8 characters → `GB`) and **mark every
   inferred row as inferred** in the output.
3. Run `validate_company_id` on every row first. It costs no network call. Rows that fail
   validation never reach a lookup: report them as a separate "could not be checked" group
   with each `reason`, so the user can fix their data instead of wondering.
4. **Tell the user how many lookups this will be and ask before starting** if it is more than
   about 25 rows. Each row is at least one upstream request against a national register, and
   an attachment doubles it.

## Then

For each valid row, call `lookup_company(id, country)`. Add
`include=["filings"]` only if the user asked for filing behaviour and only for the countries
`list_countries` says support it — check `supported_includes` once at the start rather than
discovering it row by row.

Build a table with one row per input row:

| identifier | country | registered name | status | registered address | industry code | VAT registered | source_url | notes |

Rules for the table, all of which matter more than the table looking tidy:

- An empty cell must be `null` or `—`, **never** "no", "0", "none" or a blank that reads as an
  answer. Companies House publishes no VAT status, no employee count and no share capital for
  any company; Sweden publishes no status field at all and derives it. A blank there is the
  register being silent, not the company having nothing.
- Keep `notes` — do not truncate it to fit a column. If a note will not fit, put a marker in
  the cell and list the notes in full beneath the table. Sole-proprietorship and
  advertising-protection notes carry obligations that travel with the data.
- Keep `source_url` on every row. That is what makes any single cell checkable.
- A row that errored gets its `error.code` and `error.hint` in the table, not a blank.

Finish with: how many rows resolved, how many failed validation, how many errored upstream,
and the licence line for each register that answered (`license` from the response). If the
user wants the result written back to a file, write it — CSV if they gave CSV, otherwise
Markdown — and never overwrite their input file without being asked.
