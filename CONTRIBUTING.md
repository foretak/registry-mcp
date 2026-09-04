# Contributing

Thanks for looking. The single most valuable contribution to this project is
**a new country module** — read [Add your country](#add-your-country) first.

- [Ground rules](#ground-rules)
- [Development setup](#development-setup)
- [Add your country](#add-your-country)
- [Other contributions](#other-contributions)
- [Pull requests](#pull-requests)
- [Where decisions live](#where-decisions-live)

## Ground rules

Three rules carry most of the design (`DECISIONS.md` has the rest):

1. **`core/` stays country-neutral.** No Norwegian vocabulary, no
   country-specific prose, no `if country == "NO"` anywhere in `core/`, `api/`
   or `mcp/`. A country's terms, caveats and quirks live in that country's
   folder (D-001, D-004).
2. **One shape per operation, both surfaces.** REST and MCP return the *same*
   `core.models` document for the same operation — `CompanyReport`,
   `SearchResult`, `DeadlineReport`, `ValidationResult` — built by the
   `Registry` base class, never assembled by a surface (D-004, D-010). There is
   a test that asserts REST ≡ MCP; if you change one, change the model.
3. **Rules are pure and `today` is the only clock.** Deadline logic takes
   `today` as a parameter and never calls `date.today()` itself, so every
   computed date is reproducible in a test.

Two things we will ask you to change in review, every time: a docstring written
as a keyword dump rather than as prose an agent reads (`KEYWORDS.md` §3), and
an invented value where the register publishes none — a field the register does
not answer is `null`, meaning "we do not know", never a guess and never `false`.

## Development setup

```bash
git clone https://github.com/foretak/registry-mcp
cd registry-mcp
uv sync --all-extras

uv run pytest -m "not live"   # the default suite: no network
uv run pytest                 # includes the tests that hit the real register
uv run mypy .
uv run ruff check . && uv run ruff format --check .
```

`pre-commit install` wires ruff and mypy into your commits. CI runs the same
three commands, so a green local run is a green PR.

Run the server the way a client will:

```bash
uv run registry-mcp                      # stdio
uv run uvicorn registry_mcp.api.main:app --port 8080   # REST + /mcp
```

## Add your country

**Norway is one folder.** So is yours. Nothing in `core/`, `api/` or `mcp/`
changes — both surfaces, `list_countries`, the OpenAPI document and the rules
resource all light up for your country automatically once the module registers
itself.

**Before you start: [open a "new country" issue](https://github.com/foretak/registry-mcp/issues/new?template=new_country.yml)**
so two people don't build the same module. Say which register you are wrapping
and paste one real API response — that response is the thing that decides
whether the mapping is honest.

Then copy the template and work through the six steps in its module docstring
(`src/registry_mcp/registries/xx/__init__.py`):

```bash
cp -r src/registry_mcp/registries/xx src/registry_mcp/registries/dk
```

1. **Identity.** Set `country` to the ISO-3166-1 alpha-2 code and `registry` to
   the register's slug. Set `is_stub = False`. Fill in `id_scheme`,
   `id_example`, `id_description`, `source_url` and `license` — these are what
   the `registry://rules/{country}` resource shows an agent.
2. **`validate_id`.** Normalise the input, then check the national checksum.
   Raise `RegistryError(ErrorCode.INVALID_ID, ..., hint=...)` on failure — the
   hint must tell the agent its *next call*, not just what went wrong. If your
   country formats identifiers a particular way (Norway groups nine digits in
   threes), override `format_id` too; leave it alone if it does not.
3. **`lookup` and `search`** in a `client.py` next to the module. Reuse the
   contract in `NORBIZ_SPEC.md` §6 — 5 s timeout, one retry, a descriptive
   `User-Agent` carrying a contact address — and the 24 h SQLite cache (D-006).
4. **`deadlines`** in a `rules.py`, importing the date helpers from
   `core.rules.common`. Pure function of `(report, today)`. Weekend and public
   holiday roll-forward belongs here, not in `core`.
5. **Register it**: add `from registry_mcp.registries import dk as dk` to
   `registries/__init__.py`. That is the one line outside your folder.
6. **Tests.** Write your country's own numbered rules list in the style of
   `NORBIZ_SPEC.md` §5 and a test per entry, plus fixture-backed client tests.
   Record at least one real upstream response as a fixture under
   `tests/fixtures/` — no hand-written JSON standing in for the register.

Checklist for the PR:

- [ ] `uv run pytest`, `uv run mypy .`, `uv run ruff check .` all pass
- [ ] Nothing outside `registries/<cc>/` changed except the one import line
- [ ] Every caveat the user should hear is on `CompanyReport.notes` (it is
      copied into `DeadlineReport.notes` for free) — not synthesised in a surface
- [ ] Fields the register does not publish are `null`, not invented
- [ ] `source`, `source_url` and `license` are set, and the licence's
      attribution condition is actually satisfiable from the response
- [ ] The data source permits programmatic access at the rate we will use

If the abstraction fights you, **say so in the PR** rather than working around
it. A country that does not fit is a bug in `core/`, and fixing it is worth
more than the module.

## Other contributions

Good first issues are labelled [`good first issue`](https://github.com/foretak/registry-mcp/labels/good%20first%20issue).
Beyond that, the things that help most:

- **A missing field or a wrong mapping** for a country already supported —
  file it with the org number and the upstream JSON.
- **A deadline rule that is wrong**, with the statute reference. Deadline
  computation is the part most likely to be subtly wrong, and the part where
  being wrong matters most.
- **Docs**: `static/llms.txt` and `static/llms-full.txt` are read by agents, not
  people. If a model misread something, that is a doc bug worth fixing.

Please do not open PRs that only reformat, only bump a dependency without a
reason, or add a dependency to do something the standard library does.

## Pull requests

- One logical change per PR; a new country is one PR.
- Write the commit message for someone reading `git log` in a year.
- If your change alters a response shape, it needs a `DECISIONS.md` entry
  first — open an issue and we will agree the shape before you write the code.
- By contributing you agree your work is released under the repository's
  [MIT licence](LICENSE).

## Where decisions live

| Document | What it settles |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | Interface and schema decisions, numbered D-001… Read before changing any model. |
| [`NORBIZ_SPEC.md`](NORBIZ_SPEC.md) | The Norwegian module in detail, incl. the numbered rules test list |
| [`KEYWORDS.md`](KEYWORDS.md) | The canonical alias vocabulary and where each term must appear |
| [`legal/terms.md`](legal/terms.md) | Data licensing and attribution obligations |

Be decent to each other. Behaviour that makes this a worse place to work gets
you removed from it.
