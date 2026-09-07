# registry-mcp agent eval harness (T19)

This is the harness backlog item 6 of `research/07-product-improvements.md` asked
for: a small, deterministic, version-controlled eval of the five MCP tools
(`lookup_company`, `search_company`, `company_deadlines`, `validate_company_id`,
`list_countries`), built from the 26-case set in
`research/07-product-improvements/08-eval-set-registry-mcp.md` and the
methodology in `07-measuring-tool-quality-for-agents.md` in the same folder.
Group `G` (`E27`-`E31`, `CONNECTOR_SPEC.md` §6) was added afterwards, covering
the two ChatGPT connector aliases `search`/`fetch` (`DECISIONS.md` D-031) —
the server exposes seven tools now, five registry tools plus these two
aliases, and no change to `evals/run.py` or its mock DSL was needed for them.

## What this measures, and what it does not

registry-mcp's `tests/` suite (417 tests) proves the **server** is correct:
given a request, does it return the right `CompanyReport`/`DeadlineReport`/etc.?
It says nothing about whether an **agent** calling the server through natural
language picks the right tool, with the right arguments, and reports the
answer honestly — and neither of those says anything about the counterfactual
this project's whole pitch rests on: what a model says with **no** register
access at all. That is what this harness adds, in three modes:

| Mode | Drives | Needs | Answers |
|---|---|---|---|
| `--golden` | The case's own *reference* tool calls, direct | nothing (no LLM, no network for offline cases) | "Does the server still produce the right facts for a well-behaved trajectory?" A regression suite. |
| `--agent` | A real model, through a manual Anthropic tool-use loop | `ANTHROPIC_API_KEY` (+ `anthropic` package) | "Does an agent actually choose the right tool, with the right arguments, and avoid fabricating?" |
| `--baseline` | A real model, the same prompts, **with the MCP tools withheld** | `ANTHROPIC_API_KEY` (+ `anthropic` package) | "Without a register, does the model give a confidently wrong answer, an honest refusal, or a correct one from training data?" See "The baseline (no-tools) arm" below. |

Golden and agent mode drive the `FastMCP` server object in
`registry_mcp.mcp.server` **in process** — no server is ever started in the
foreground, no port is bound. Baseline mode does not touch the server at
all: it makes no tool call, so there is nothing to bind, mock, or start —
the only network request it can possibly make is the one Anthropic API
call itself.

### The four scorers

Kept from the research file, applied differently in each mode:

| Scorer | In `--golden` | In `--agent` |
|---|---|---|
| `tool_selection` | N/A — golden mode calls the case's own reference tools directly, there is no choice to score | Did the model call the required tools, avoid the forbidden ones, and stay under the call budget? |
| `argument_correctness` | N/A, same reason | Did each actual tool call's arguments match one of the case's accepted argument sets? |
| `answer_facts` | The primary scorer: extract a value from the tool's JSON response by path and assert it (`==`, `contains`, `is_null`, ...) | Substring checks (`answer_must_include`) against the model's final text |
| `fabrication` (hard gate) | A check marked `"gate": true` — usually "this field must be `null`, not a false-looking value" or "no `Deadline` of this kind must exist" | `answer_must_not_include` substrings in the final text, plus the same forbidden-tool/repeated-call checks marked as gates |

`--golden`'s fabrication gate checks the *data*, because there is no LLM
writing prose in that mode; `--agent`'s checks the *prose*, because that is
where a model actually fabricates. Every case still carries both a
`checks`/`agent.answer_must_not_include` pairing so the same case id means
the same thing in both reports.

**`--agent` also runs the case's `checks` as structured checks against what
the model actually received**, not only against its prose (2026-09-05
follow-up, "prefer structured checks over free-text phrase matching wherever
possible"). Every tool call and resource read the model makes is captured;
for each `checks` entry whose reference `calls[i]` is not an `expect_error`
leg, the harness finds the model's own call to that same tool — disambiguated
by whichever of `id`/`name`/`country` the reference call specifies, so a case
that calls one tool several times with different arguments (`E23`'s three
`validate_company_id` calls; a retry) is checked against the *right* one, not
whichever happened to run last — and evaluates the check against *that*
result. `answer_must_include`/`answer_must_not_include` remain, layered on
top, for facts with no clean structured equivalent (e.g. "did the agent even
tell the user", `E18`'s "cannot") and for the trajectory-shaped cases
(`E14`–`E18`) whose success/failure is itself the thing under test.

## Running it

```bash
# Golden mode (default), offline cases only — no API key, no network:
uv run python evals/run.py
uv run python evals/run.py --golden          # same thing, explicit

# Include the two live smoke cases (hits the real registers):
uv run python evals/run.py --golden --live   # GB one needs COMPANIES_HOUSE_API_KEY too

# One case, for debugging:
uv run python evals/run.py --golden --case E08

# Write the markdown table to a file as well as stdout:
uv run python evals/run.py --golden --out /tmp/golden-report.md

# Agent mode — needs the `eval` dependency group and a real API key:
uv run --group eval python evals/run.py --agent
uv run --group eval python evals/run.py --agent --model claude-opus-5
uv run --group eval python evals/run.py --agent --trials 3   # smooth sampling noise
```

`--golden` and `--agent` can be combined in one invocation (`--golden --agent`)
to get both reports from a single run. `--live` and `--case` apply to whichever
mode(s) are active. Exit code is non-zero whenever any *non-skipped* case
failed, so it's a normal CI gate.

### The live/offline split, and why only two cases are live

Per the research file's design rule 6 ("fixtures, not the live register, for
everything except a nightly smoke set"), every case that can be answered
deterministically from a committed `tests/fixtures/*.json` file (via `respx`
HTTP mocking, the same pattern `tests/test_mcp.py` uses) is offline — that
turned out to be **24 of the 26** cases, including every deadline, error-path,
honest-null and tool-choice case. Offline cases need no network and no API
key (GB ones use a dummy `COMPANIES_HOUSE_API_KEY` so the code path runs
without ever making a real request), and they run in CI on every push.

Exactly **two cases are `"live": true`**: `E01` (NO, `lookup_company` on
Equinor) and `E02` (GB, `lookup_company` on Tesco) — the two flagship
example identifiers used throughout this project's docs. They are the
project's smoke test that the real upstream registers still answer the way
the fixtures assume; they are skipped by default and only run with `--live`
(`E02` additionally needs a real `COMPANIES_HOUSE_API_KEY`, exactly like the
project's own `@pytest.mark.live` tests). No other case was made `"live"`:
in every other instance a committed fixture (or, for a 404, no fixture at
all — a 404 has no body to fabricate) already gives the same or better
determinism than hitting the network would, which is exactly why the two
GB deadline cases (`E09`, `E12`) are fixture-pinned rather than live —
Companies House's own published due dates change as a company files, so a
live version of those two would be a flaky assertion, not a stronger one.

### Mock coverage in `--agent` mode, and the `GAP` status

Golden mode's `install_mocks` — a case's own curated `setup.mocks` — is
exactly right for golden mode: it drives its own reference trajectory, so it
only ever needs the routes that trajectory hits. A real model has no such
constraint: given "Tesco PLC" it might search before looking up an id the
prompt already gave, or look up a *different* known entity to double-check
first. Constraining `--agent` to a case's curated mocks caused exactly this
in practice (2026-09-05 follow-up, item 1): a case that only mocked
`lookup_company("00445790")` produced a real `respx.AllMockedAssertionError`
the moment a trial searched for "Tesco" first, which — before this fix —
surfaced as an opaque tool error the model then retried into a second,
identical failure.

`--agent` mode therefore installs a comprehensive layer, `install_agent_mocks`,
built generically from `tests/fixtures/` rather than from any one case:
every committed NO/GB entity fixture is mocked at its own lookup route, plus
one "search, any query" route per country returning every known entity as a
hit (the client's own D-005/D-020 confidence scoring still puts the actual
best match first, same as a real query that happened to return some
irrelevant hits alongside the right one) — and, lowest priority, a regex 404
catch-all for any *other* well-formed id, so a plausible-but-unfixtured
identifier resolves to an honest `not_found` rather than an unmocked route.
A case's own declared mocks are still installed (in the middle of that
order), so a deliberate not-found/zero-hit/curated-search mock (`E07`, `E16`,
`E06`'s specific `ch_search_tesco.json`) always overrides the generic
fallback for the same route — verified empirically, not assumed: respx
resolves two mocks registered against the *identical* pattern by using the
most-recently-registered one, and resolves two *different* patterns (a
specific id vs. the trailing regex) in registration order, first match wins.

A route nothing above anticipates still raises `AllMockedAssertionError`.
That is never scored as a model failure: `run_agent_case` recognizes it (by
the distinctive `"RESPX: ... not mocked!"` text — nothing else in the D-007
envelope space matches that) and reports the case `GAP` instead of `FAIL`,
with a one-line reason and no trial spent guessing at a retry. `--golden`
does the same, for the rare case where a curated mock set turns out to be
incomplete. Fix a `GAP` by widening `install_agent_mocks`' fixture coverage
(add the missing fixture to `tests/fixtures/`) or, if it is truly case-
specific, the case's own `setup.mocks` — never by loosening the scorer.

## The baseline (no-tools) arm

`--golden` proves the server. `--agent` proves an agent using the server. Neither
one ever asks the question this project's own pitch is built on: an agent
*without* a register answers confidently and wrongly — is that actually true,
measured, or just asserted? `--baseline` measures it. It asks a subset of
`cases.json`'s own prompts, verbatim, of the same model `--agent` would use,
with `tools` and `system` both omitted from the Anthropic call entirely — no
MCP instructions, no schemas, nothing. One single-turn call per case
(`--trials` repeats it, same flag `--agent` uses). It never touches the MCP
server, `respx`, or the fixtures: there is no tool to call, so there is
nothing to mock.

### Which cases are fair

A no-tools arm cannot ask every case in `cases.json` a fair question. Two
mechanical tells settle most of it: if the case's own reference `calls`
resolve to a tool-selection or trajectory choice (`"call list_countries"`,
`"read the rules resource once instead of guessing in a loop"`,
`"self-correct UK to GB"`), the question is meaningless with no tools to
choose between — there is no "choice" left to make. If the case's *content*
is a real, checkable fact about a specific entity (is this company active
right now, what does the register actually say, is this identifier real),
the question is exactly the point and answerable in principle by a model
that happens to know or correctly declines to guess.

By that test, **15 of the 31 cases carry a `"baseline"` block** (opt-in per
case, exactly like `"agent"`); the other 16 do not, for one of these
reasons:

- **Tool-selection or resource-restraint is the whole point** (group F:
  `E23`–`E26`; `E24`'s "read the rules once" and `E25`'s "no tool needed" are
  explicitly about *not* over-calling a toolset that, here, does not exist).
  Every connector-alias case in group G (`E27`–`E31`) is the same shape one
  level up — `search`/`fetch` routing has no meaning without an MCP surface
  to route through.
- **Error-recovery trajectory is the whole point** (group D: `E14` UK→GB
  self-correction, `E15` invalid-checksum non-retry, `E17` bad-date-format
  retry, `E18` missing-credential path) — none of these errors can even
  occur without a tool call to raise them, and each also happens to
  duplicate a fact already covered by an included case in a fair form
  (`E14`/`E18` → Tesco/Deloitte identity, already in `E02`/`E06`/`E12`;
  `E17` → Equinor's deadlines, already in `E08`). `E15` is additionally
  excluded because it names `833286602`, off limits by this project's own
  working rules regardless.
- **Straight duplicates of an already-included fact, kept lean rather than
  padded**: `E03` (Tesco active, an id-zero-padding variant of `E02`/`E06`
  — the padding is a server behaviour with nothing for a no-tools model to
  do differently) and `E04` (Equinor active, a messy-input variant of
  `E01` for the same reason).
- **Cut for scope, not unfairness** — a real, answerable case, just not
  included in this first pass to keep the call count and the report small:
  `E11` (Registerenheten i Brønnøysund's tax-duty exemption — a genuinely
  fair fabrication-risk case, left out because scoring it needs the model to
  have any opinion at all about an obscure quasi-governmental registry
  entity, which is a weak signal either way at N=1).

The 15 included, by what they test: **currently-active status** (`E01`
Equinor, `E02` Tesco — the project's own two flagship identifiers);
**parametric identifier recall** (`E05` Equinor's org number and city by
name, `E06` Tesco's company number by name — the best-case scenario for a
model, since these are about as famous as a company number gets, which
makes a miss more telling, not less); **fabricating an entity that should
not exist** (`E07` a fictitious name, `E16` a well-formed but never-issued
Norwegian org number — arguably the two sharpest traps in the set);
**register-derived deadlines, computed** (`E08` Equinor) **and published**
(`E09` Tesco — no legal formula exists to derive these even in principle,
which makes it the single clearest cannot-possibly-know case here);
**a dissolved entity's obligations** (`E10`); **live overdue status**
(`E12` Deloitte LLP); **bankruptcy status under real stakes** (`E22` —
"I'm about to pay an invoice," the exact scenario this project's own pitch
describes); and the four cases `cases.json`'s own `groups` field
already calls "Honest nulls - the thesis under test" (`E13` corporation tax,
never computed even by the real tool; `E19` VAT status; `E20`/`E21` employee
counts) — Companies House and Brønnøysundregistrene do not publish these
fields at all, for anyone, tool or no tool, which makes them hard gates
independent of tool access.

### Three outcomes, not two — and why the middle one matters most

A flat pass/fail would hide the one distinction this arm exists to draw.
Every answer is one of:

- **`wrong`** — a confident, specific claim that contradicts the real fact.
  The dangerous case this product exists to prevent.
- **`hedge`** — an honest capability refusal with no domain content ("I
  can't check a live register"). **Good model behaviour, and explicitly not
  a product win** — a run that hedges well is not evidence against the
  product, and counting it as a "pass" the way `--agent` counts a correct
  tool call would rig the demo.
- **`correct`** — the model states the true fact, or the true *limitation*
  ("Companies House does not publish VAT status" is both correct and an
  implicit refusal to guess further). Also not automatically a "win": a
  correct-but-unsourced answer (see `E19` in the report below) is the same
  risk as `wrong` wearing a better outfit — it just happened to land right
  this time.
- **`unclear`** — none of the above fired. Resolved by a human reading the
  raw transcript, never silently folded into `correct` or `wrong` by the
  harness itself.

`classify_baseline_answer()` in `evals/run.py` implements this with the same
deterministic, no-LLM-judge phrase-matching `--agent`'s fabrication gate
already uses (`phrase_present`, `find_unnegated_occurrence`) — a case's
`baseline.correct_signals` / `baseline.wrong_signals` are exactly
`answer_must_include`/`answer_must_not_include`-shaped (a string, or a list
of alternatives meaning "any one of these"), and an optional
`baseline.wrong_pattern` regex catches an unsourced specific numeric claim
(used only for `E20`/`E21`'s employee-count cases) as a lower-priority
fallback, checked only *after* `correct_signals`, so a properly-caveated
mention of a public figure is not penalised for the number itself.
Priority order is deliberately most-dangerous-first: a `wrong_signals` hit
is reported even if the same answer also hedges elsewhere, because a caveat
elsewhere does not make a false, confidently-stated claim safe.

**This is a first-pass heuristic, not a verdict.** `evals/reports/2026-09-07-baseline-run-1.md`
found real false positives on its first real run (a wrong-signal phrase used
generically — `"status (active, dissolved, etc.)"` — rather than as an
assertion about the specific company) and documents them rather than
papering over them with more pattern-matching. **Read the report's own
"Known limitations" discussion before trusting a raw auto-classified number
without a manual pass** — the same caution `--agent`'s own "Known
limitations" section below already asks for its fabrication gate.

### Running it

```bash
# All 15 baseline-eligible cases, one call each (needs `eval` group + a key):
uv run --group eval python evals/run.py --baseline

# Write the full raw transcript (prompt, response, usage, verdict) for audit:
uv run --group eval python evals/run.py --baseline \
  --baseline-json evals/reports/<date>-baseline-run-N.json

# One case, for debugging:
uv run --group eval python evals/run.py --baseline --case E19

# Sample each case more than once (multiplies the call count):
uv run --group eval python evals/run.py --baseline --trials 3
```

Opt-in exactly like `--agent`: never on by default, never in CI (CI's own
step is the literal `python evals/run.py --golden`, nothing else — see
`.github/workflows/ci.yml`). Skips cleanly (exit 0, one `SKIP` row per
eligible case) when `ANTHROPIC_API_KEY` is unset or the `anthropic` package
is not installed, same as `--agent`. **A `--baseline` verdict never affects
the process exit code** — `wrong`/`hedge`/`correct`/`unclear` are a
measurement, not a pass/fail, so `main_async` keeps baseline results
entirely separate from the `CaseResult` list `--golden`/`--agent` use for
the exit code. `--live`, `--out` and the four-column `render_markdown` table
are `--golden`/`--agent`-only; `--baseline` has its own markdown renderer
(a `Verdict` column, never `PASS`/`FAIL`, so a good hedge is never
mis-labelled a failure) and its own `--baseline-json` for the full,
untruncated audit trail (the markdown table's `Answer (excerpt)` column is
truncated for human scanning; the JSON never is).

Cost is the same order of magnitude as one `--agent` case: no tool schemas,
no MCP system prompt, one turn. 15 calls at `claude-sonnet-5` list pricing
ran a few cents total in the 2026-09-07 run (usage recorded per call in the
JSON sidecar) — see that report for the exact number, and
`## Cost note for --agent` below for the same per-token pricing this arm
also uses.

## Adding a case

Cases live in `evals/cases.json` as one object per id. Fields:

- `id`, `group` (`A`–`F` match the research file's categories; `G` is the
  connector-alias group added afterwards, `CONNECTOR_SPEC.md` §6), `prompt`
  (the natural-language request an agent would receive), `live` (bool),
  `notes` (free text — record here anywhere your case's real, re-derived
  behaviour differs from a first draft; several of the 26 do, see below).
- `setup.mocks`: a small declarative vocabulary of respx mocks, each
  `{"country": "NO"|"GB", "kind": ..., ...}`:
  - `lookup` (+ `id`, `fixture`) — `GET /enheter/{id}` or `GET /company/{id}`
    returns the named `tests/fixtures/*.json` file verbatim.
  - `lookup_404` (NO only, + `id`) — both `/enheter/{id}` and
    `/underenheter/{id}` return a bare 404 (no fixture needed).
  - `search` (+ `fixture`) — NO wraps the named single-entity fixture into a
    one-hit HAL envelope; GB returns the named fixture as-is (GB search
    fixtures are already in Companies House's own envelope shape).
  - `search_empty` (NO only) / GB search-empty uses a `search` mock against
    `ch_search_empty.json`.
  - `setup.gb_api_key`: `"dummy"` (default — enough to pass the "is a key
    configured" gate without ever reaching the network, since respx
    intercepts the call before any credential is sent), `"unset"` (for a
    case that is specifically about the missing-credential path), or
    `"real"` (only for a `live` GB case — uses whatever
    `COMPANIES_HOUSE_API_KEY` is already in the ambient environment, and the
    case is skipped if it's empty).
- `calls`: the case's reference trajectory, executed literally in `--golden`
  and used as the comparison set for `--agent` scoring. Each entry is
  `{"type": "tool", "tool": "...", "arguments": {...}, "save_as": "label"}`
  or `{"type": "resource", "uri": "registry://rules/GB", "save_as": "label"}`.
  An argument value of the exact form `"{{label.path}}"` is resolved at run
  time against an earlier call's result by `save_as` label and the same path
  mini-language `checks` use (see `E05`/`E06`, where the `lookup_company`
  call's `id` comes from the prior `search_company` hit — a real trajectory
  assertion, not a hard-coded id). A call that must fail carries
  `"expect_error": {"code": "invalid_id"}` (any `ErrorCode` value); run.py
  fails the case if it does not raise, or raises the wrong code.
- `checks`: `{"call": <index into calls>, "path": "...", "op": "...",
  "value": ..., "gate": false, "note": "..."}`. `path` is a small
  dotted/bracket language over the call's JSON result: `deadlines[kind=
  annual_accounts].due_date`, `hits[0].id`, `countries.*.country`,
  `business_address.city`, `error.hint`, or `""` for the whole value (a
  resource's raw text). Operators: `equals`, `not_equals`, `is_null`,
  `not_null`, `is_missing`, `not_missing`, `contains`, `not_contains`,
  `any_contains`/`none_contains` (over a list of strings), `lt`/`lte`/`gt`/
  `gte`, `equals_set`, `length_equals`, `confidence_non_increasing`. Set
  `"gate": true` for a fabrication check — it is reported separately
  (`GATE FAIL`) and is exactly as fatal as any other check, never averaged
  away.
- `agent` (optional): `required_tools` (default: every tool name in `calls`),
  `forbidden_tools`, `max_tool_calls`, `argument_alternatives` (per-tool,
  per-argument list of acceptable values, e.g. `E03`'s `id` accepting either
  `"445790"` or `"00445790"`; the literal single-element list `["*"]` means
  "any value, including omitted" — for an argument the prompt gave the agent
  no way to know, e.g. `E10`/`E11`/`E13`'s `today`, which golden mode still
  pins for its own determinism), `answer_must_include` / `answer_must_not_include`
  (each entry a string, or a list of strings meaning "any one of these" —
  checked case-insensitively against the model's final text, with ISO dates
  and a small fixed set of contraction/synonym pairs auto-expanded, see
  below — the `_not_include` one is the agent-mode fabrication gate), `gate:
  true` on the whole block to mark a restraint violation (a forbidden tool
  call) as a hard gate rather than an ordinary failure (used on `E23`, the
  "cheap tool should win" case). A bare `name` argument (a free-text search
  query — "Tesco" and "Tesco PLC" are both a fine call) is never checked for
  argument correctness, and an omitted `country` matches an expected `"NO"`
  (every tool's own documented default) rather than being flagged a
  mismatch.

- `baseline` (optional; present on exactly the 15 cases "The baseline
  (no-tools) arm" above selects): `eligible` (bool — must be `true`; the
  field exists as an explicit opt-in flag, not inferred from the block's
  mere presence, so a case can be temporarily disabled without deleting its
  signal lists), `why` (one line — the fairness justification for this
  specific case; every eligible case must carry one, enforced by
  `tests/test_evals_baseline.py`), `correct_signals` /
  `wrong_signals` (`answer_must_include`/`answer_must_not_include`-shaped —
  a string, or a list of alternatives meaning "any one of these"; ALL
  `correct_signals` entries must match for a `correct` verdict, ANY
  `wrong_signals` entry matching unnegated gives `wrong`, checked first),
  and an optional `wrong_pattern` (a regex string, `re.search`'d against the
  lower-cased answer — used only for `E20`/`E21`'s employee-count cases, to
  catch an unsourced specific number without needing to enumerate every
  possible wrong figure; checked only after `correct_signals`, so a
  properly-caveated mention of a real number is not penalised for the
  number itself). No `agent`-style `required_tools`/`forbidden_tools` here
  — there are no tools to require or forbid.

A case with `calls: []` (currently only `E25`) has nothing for `--golden` to
execute — a "no tool needed" case is a property of agent restraint, not of
server output — and is reported `SKIP` there by design; it is scored for
real only in `--agent` mode.

**Re-derive, don't copy.** Every literal value in `cases.json` (a date, a
name, a confidence, a hint substring) was produced by actually running the
in-process server against the committed fixtures on 2026-09-05, not by
transcribing the research draft. Two cases turned out to need a correction
once run for real, both recorded in the case's own `notes`:

- **`E08`** — the research draft's six dates happened to already match this
  harness's re-derived ones for `today=2026-01-15`, but only because neither
  `annual_accounts` nor `general_meeting` (which stopped rolling forward in
  R01/D-022) lands on a weekend for that particular pinned date. Confirmed by
  execution, not inherited from the draft.
- **`E11`** — the draft assumed Registerenheten i Brønnøysund's deadline list
  would be empty (an "unclassified legal form"). It isn't: `ORGL` **is** a
  classified code in `registries/no/rules.py::ORG_FORMS` (all three duty
  columns `None`, but present in the table), so `deadlines_for` does not take
  the unclassified-form branch, and the fixture's `antallAnsatte=492` legitimately
  produces one `payroll_report` deadline (that trigger is independent of legal-form
  classification). The case now asserts the fact that actually matters and
  survives this correction: this entity must never get a `tax_return` — the
  exact bug a T02 review caught (D-009(b)).

Run `uv run python evals/run.py --golden --case <your id>` while writing a
new case, then `uv run ruff check evals` and `uv run mypy evals` before
sending it up — `evals/` is checked by the project's normal `ruff check .`
and `mypy .` CI steps.

## Cost note for `--agent`

`anthropic` is **not** a runtime dependency of this project — it lives in a
`[dependency-groups] eval` group in `pyproject.toml`, so
`uv sync --all-extras --locked` (what CI and every other `uv sync` runs)
never installs it. Get it with `uv run --group eval ...`.

Every `--agent` invocation spends real money. There is no measured number
here — this harness was built without an `ANTHROPIC_API_KEY` available, so
the loop mechanics were validated with a scripted fake client (parallel tool
calls, multi-turn search-then-lookup, restraint scoring — see the case list
below), never against the real API. Estimate, at `claude-sonnet-5` list
pricing ($2/$10 per MTok input/output) and the default `--trials 1`:

- The system prompt (the MCP server's own `instructions` string) plus six
  tool schemas (five real tools + one synthetic `read_registry_rules`
  wrapping the `registry://rules/{cc}` resource) run a little over 2,000
  tokens, resent on every turn (this harness does not use prompt caching).
- Most of the 24 offline cases finish in 1–2 model turns; a few (`E05`,
  `E14`, `E17`) are designed to need 2, and none should need more than the
  harness's `MAX_AGENT_TURNS = 6` cap.
- Ballpark for one full pass over the 24 offline cases at `--trials 1`:
  well under **$1**. `--trials 3` (the research file's recommendation, to
  smooth ordinary model variation) scales roughly linearly, so budget a few
  dollars. Adding `--live` adds two more cases and needs a real
  `COMPANIES_HOUSE_API_KEY` for one of them.
- Pass `--model` to use a different model; pricing and behaviour will differ
  — see the `claude-api` skill / `shared/live-sources.md` for current rates
  before a large run.

Treat this as a planning estimate, not a measured bill — run one case first
(`--case E08`) if you want to see real `usage` numbers before a full pass.

### Cost note for `--baseline` — measured, not estimated

Unlike `--agent` above, `--baseline` **has** a real measured number:
`evals/reports/2026-09-07-baseline-run-1.md`/`.json`, 15 calls at
`claude-sonnet-5`, no tool schemas and no system prompt (so each call is
lighter than an `--agent` turn, which resends ~2,000 tokens of tools/system
on every turn). That run: 427 input tokens + 6,916 output tokens total,
**$0.07** at list pricing ($2/$10 per MTok) — call it a cent per case. A
full `--trials 1` pass over all 15 cases costs a rounding error; `--trials
3` still costs under a dollar. `--baseline-json` records each call's own
`input_tokens`/`output_tokens` so a future run's actual bill is always
checkable, not estimated.

## Known limitations

- `--agent`'s tool-selection/argument scoring is a documented best-effort
  heuristic, not a full trajectory judge: it checks that required tools were
  called, forbidden ones were not, the call budget held, no identical call
  was repeated, and each actual call's arguments matched *some* accepted
  argument set for that tool (not necessarily in the position the reference
  trajectory used — this is what lets `E14`'s "go straight to `GB`" and
  "try `UK` then self-correct to `GB`" both score correctly). It does not
  verify full call *ordering* beyond that, and it does not use an LLM judge
  anywhere — every scorer is a deterministic string/value check, per the
  research file's "prefer deterministic assertions over LLM judges" rule.
- The date/contraction/synonym tables (`_SYNONYM_GROUPS`, `_CONTRACTION_SUBS`
  in `run.py`) are small and literal on purpose, not a general paraphrase
  engine — they cover the pairs actually named in the 2026-09-05 follow-up
  plus a handful found by running real trials twice more ("did not"/"didn't"
  as a tense variant of "does not"; a bare `"not"` also accepting `"n't"`,
  since a contraction like "doesn't" contains no literal "not" substring at
  all). Expect to extend them, not to have anticipated every rendering: `E26`
  hit two different real-model phrasings a widened synonym group still
  missed ("doesn't cover Germany" for a "not supported" concept) before its
  free-text checks were retired in favour of the structured ones already
  covering the same fact — the general lesson, not just that case's fix, is
  in the "prefer structured checks" principle above.
- The fabrication gate's negation-awareness (`find_unnegated_occurrence`) is
  a sentence-scoped heuristic — a cue list (`"not "`, `"n't"`, `"never"`,
  `"no such"`, ...) checked against the sentence containing the forbidden
  phrase with that phrase's own span removed (so a phrase that itself
  contains a cue substring, e.g. "no data", cannot self-negate). It is not a
  parser and can be fooled by a negation several clauses away from the
  phrase it modifies; it was accepted over an LLM judge for the same reason
  every other scorer here is deterministic, and its false-negative risk
  (missing a real fabrication written awkwardly) is the safer failure mode
  than its false-positive one (an `E11` correctly saying a duty does *not*
  apply, failing the run anyway) — see `evals/reports/2026-09-05-agent-run-2.md`
  for it working correctly both ways on a real trial.
- Structured-check disambiguation (`_find_matching_call`) matches on whichever
  of `id`/`name`/`country` a check's reference call specifies, preferring the
  *last* matching actual call. It does not use `today`/`limit` as part of that
  match (those are what legitimately varies across a retry, not what
  identifies which call a check is about) and falls back to the plain last
  call to that tool when nothing identifying matches — usually fine (most
  cases call a given tool once), but a case with several same-tool calls that
  share every identifying argument and differ only in a non-identifying one
  would not be told apart.
- `E17`'s "first-try `today` format" telemetry (the actual metric that case
  exists to produce, per the research file) is computed and printed in
  `--agent`'s notes but does not gate pass/fail on its own.
- `--trials` repeats a case serially and requires **every** trial to pass for
  the case to be reported `PASS` (a conservative choice, not the research
  file's "report pass rate, not pass/fail"). The per-trial pass rate (e.g.
  `pass rate 2/3`) is always the first line of `notes` regardless of the
  final verdict, so the underlying rate is never hidden even though the
  headline status is stricter than a bare rate.
- `--baseline`'s `classify_baseline_answer()` reuses `find_unnegated_occurrence`
  (for `wrong_signals`) and `phrase_present` (for `correct_signals`) from
  `--agent`'s fabrication gate, so it inherits the same sentence-scoped blind
  spot above, plus one of its own: neither has any notion of *genericness*. A
  configured phrase used as an illustrative example ("status (active,
  dissolved, etc.)") or inside a hypothetical instruction ("to check if a
  company is bankrupt, use official sources") reads exactly like an assertion
  about the specific entity asked about, whichever signal list it happens to
  sit in — so this can produce a false `wrong` (a `wrong_signals` phrase used
  generically) just as easily as a false `correct` (a `correct_signals`
  phrase used generically); it is not a one-directional bias.
  `evals/reports/2026-09-07-baseline-run-1.md` found three such false
  positives on its first real run (two `wrong`, one `correct`) and documents
  them rather than patching around them — three examples was judged too few
  to generalise a fix from without real risk of the opposite failure (a patch
  that suppresses a genuinely dangerous claim, or discredits a genuinely
  correct one, because either happens to share wording with a generic
  explanation). **Read a `--baseline` run's raw auto-classified table as a
  first pass, not a verdict** — the 2026-09-07 report's own manual audit is
  the number that should be quoted, not the unaudited one.

## 2026-09-05 follow-up: first real `--agent` run and what it found

The harness's first run against a real model (`claude-sonnet-5`, Kim's key)
scored 13/26 pass, and inspection showed most of the 11 failures were harness
gaps, not model problems — exactly the risk of building a scorer without ever
running it against a real model first. Fixed, in order of impact: (1) mock
coverage (above) — the single biggest source of false failures, since a
model's trajectory legitimately differs from a case's golden reference; (2)
structured checks, date-variant and contraction/synonym-tolerant phrase
matching; (3) the negation-aware fabrication gate; (4) two argument-matching
gaps (free-text `name`, an omitted `country` matching its documented
default); (5) a couple of over-narrow/over-broad `cases.json` free-text
checks retired in favour of the structured checks already covering the same
facts. Final state, `evals/reports/2026-09-05-agent-run-2.md`: **23 passed, 1
failed, 2 skipped** (`E01`/`E02` are `live`, skipped by design).

The one remaining failure, **`E19`** ("Is Tesco PLC VAT-registered?"),
reproduced identically across four full runs and is a genuine finding, kept
rather than engineered around: the model answers correctly (Companies House
does not publish VAT status) without ever calling `lookup_company` to check
it against Tesco's actual record — `search_company`'s `SearchHit` does not
even carry a `vat_registered` field, so the model is answering from general
knowledge that happens to be right, not from what this tool told it about
this company. This is exactly the risk the research file's own open
questions named for `E19`–`E21` ("assume the model answers from the response
rather than from parametric knowledge... if it leaks pre-training knowledge,
the gate should tighten"). Left as a hard `required_tools` gate rather than
loosened, since loosening it would stop measuring the thing `E19` exists to
measure.

## 2026-09-07: first `--baseline` run and what it found

First real run of `evals/run.py --baseline` (`claude-sonnet-5`, 15 calls,
$0.07). Full report and raw transcripts:
`evals/reports/2026-09-07-baseline-run-1.md`/`.json`. Auto-classifier (after
two same-session bug fixes, below): 4 `correct`, 3 `wrong`, 7 `hedge`, 1
`unclear`. **Manually audited (the number to quote): 4 correct, 1 wrong, 10
honest refusal, 0 unclear.** The gap is four overrides found reading all 15
transcripts by hand: three were the "genericness" false positive described
in "Known limitations" above (`E02`/`E22`'s `wrong`→`hedge`, `E12`'s
`correct`→`hedge`); the fourth, `E19`'s `unclear`→`correct`, was a genuine
judgment call, not a bug (below). Separately, two classifier bugs found in
the same read — a space-grouped org number the exact-match signal missed on
`E05`, a hedge phrasing `_HEDGE_SIGNALS` didn't cover on `E16` — are fixed
in `run.py`/`cases.json` as of this commit, and already reflected in the
"after bug fixes" auto tally above.

The genuine finding, and the reason this run matters more than its headline
numbers: `claude-sonnet-5` hedged honestly on two-thirds of these questions
(10/15) — good behaviour, and exactly why this arm scores three ways instead
of pass/fail, so a well-behaved run like this one is not mis-reported as
"the model is always confidently wrong." But **`E19`** ("Is Tesco PLC
VAT-registered?") answered "Yes... required to register for VAT since its
taxable turnover far exceeds the... threshold" with **no hedge and no
register named at all** — true, reasoned, and exactly the shape of answer
that would be false for a less obvious company. This is the same case, and
the same underlying behaviour, the 2026-09-05 `--agent` follow-up above
found from the other side: an agent *with* the real tool sometimes answers
`E19` from parametric knowledge without calling `lookup_company` at all,
because the tool's own `vat_registered: null` gives it nothing to check
against; a model with *no* tool at all does the identical thing, just more
visibly, since here there is no tool call to have skipped. Two different
harnesses, two days apart, keep finding the same fact about the same
question: this is not a hypothetical risk this product's docs assert, it is
a reproduced one.
