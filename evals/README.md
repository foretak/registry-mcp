# registry-mcp agent eval harness (T19)

This is the harness backlog item 6 of `research/07-product-improvements.md` asked
for: a small, deterministic, version-controlled eval of the five MCP tools
(`lookup_company`, `search_company`, `company_deadlines`, `validate_company_id`,
`list_countries`), built from the 26-case set in
`research/07-product-improvements/08-eval-set-registry-mcp.md` and the
methodology in `07-measuring-tool-quality-for-agents.md` in the same folder.

## What this measures, and what it does not

registry-mcp's `tests/` suite (417 tests) proves the **server** is correct:
given a request, does it return the right `CompanyReport`/`DeadlineReport`/etc.?
It says nothing about whether an **agent** calling the server through natural
language picks the right tool, with the right arguments, and reports the
answer honestly. That is what this harness adds, in two modes:

| Mode | Drives | Needs | Answers |
|---|---|---|---|
| `--golden` | The case's own *reference* tool calls, direct | nothing (no LLM, no network for offline cases) | "Does the server still produce the right facts for a well-behaved trajectory?" A regression suite. |
| `--agent` | A real model, through a manual Anthropic tool-use loop | `ANTHROPIC_API_KEY` (+ `anthropic` package) | "Does an agent actually choose the right tool, with the right arguments, and avoid fabricating?" |

Both drive the `FastMCP` server object in `registry_mcp.mcp.server` **in
process** — no server is ever started in the foreground, no port is bound, in
either mode.

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

## Adding a case

Cases live in `evals/cases.json` as one object per id. Fields:

- `id`, `group` (`A`–`F`, matching the research file's categories), `prompt`
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
  `"445790"` or `"00445790"`), `answer_must_include` / `answer_must_not_include`
  (substrings, case-insensitive, checked against the model's final text —
  the latter is the agent-mode fabrication gate), `gate: true` on the whole
  block to mark a restraint violation (a forbidden tool call) as a hard
  gate rather than an ordinary failure (used on `E23`, the "cheap tool
  should win" case).

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
- `E17`'s "first-try `today` format" telemetry (the actual metric that case
  exists to produce, per the research file) is computed and printed in
  `--agent`'s notes but does not gate pass/fail on its own.
- `--trials` repeats a case serially and requires **every** trial to pass for
  the case to be reported `PASS` (a conservative choice, not the research
  file's "report pass rate, not pass/fail"). The per-trial pass rate (e.g.
  `pass rate 2/3`) is always the first line of `notes` regardless of the
  final verdict, so the underlying rate is never hidden even though the
  headline status is stricter than a bare rate.
