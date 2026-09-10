# How wrong is a model about a company when it has no register to check?

`registry-mcp` puts three national company registers behind one MCP tool — Brønnøysundregistrene / Enhetsregisteret (**brreg**) by **organisasjonsnummer** (orgnr, org.nr), Companies House by company number, and Bolagsverket by organisationsnummer. The pitch has always rested on a counterfactual: without a register, an agent answers company questions confidently and wrongly. That is an easy thing to assert in a README. On 2026-09-10 we measured it, and the answer is not the one the pitch would have picked.

## The setup

Two arms, one model — `claude-sonnet-5` — on the same day, over the same hand-written prompts.

- **With the tools:** 31 authored cases, three trials each.
- **Without them:** the 15 of those 31 that are fair to ask with no tools at all — a case about *which tool to pick* is meaningless when there are none — asked verbatim, with `tools` and `system` omitted from the API call entirely. Three trials each, so 45 calls.

## Without a register: 45 answers

Call by call, manually audited: **8 correct, 3 wrong (confident, dangerous), 34 honest hedges, 0 unclear.**

The hedges are the part nobody would have put on a slide. Per case, the model **hedged on every single trial for 9 of the 15 (60%)** — "I can't check a live register", and nothing more. It was **confidently and dangerously wrong on at least one of three trials for 2 of 15 (13%)**, and produced a **correct-but-unsourced answer on at least one trial for 4 of 15 (27%)**.

So the honest version of our own pitch is: a current model mostly refuses. It does not mostly lie. That refusal is good behaviour, and we do not score it as a win for the product — beating a model that already said "I don't know" is not beating anything.

Two caveats belong on those numbers rather than in a footnote. First, that is the **audited** count, not the harness's. The automatic classifier's raw first pass was **6 correct, 7 wrong, 27 hedge, 5 unclear**; the manual read moved **12 of the 45 calls**, every one of them a failure mode this project had already named once — the classifier cannot tell an assertion about *this* company from the same words used generically, as in "status (active, dissolved, etc.)". Second, three trials smooths sampling noise. It does not remove it.

## The three that were wrong

"3 of 45" is abstract. These are not.

On one trial, asked what a Norwegian company owed next, the model invented a detailed obligation set with no hedge anywhere in it: an SEC Form 20-F "due ... by 30 April 2026", an Oslo Børs Q4 release "early February 2026". Neither is the register-derived Norwegian deadline the case is about. The real one is `2026-07-31`.

On two of three trials, asked for a headcount, the model disclaimed access to the register and then gave "330,000–360,000 employees" anyway, as general knowledge. A caveat followed by a specific number is exactly the shape an agent pipeline strips the caveat off.

## With the register: two answers in three

Same model, same day, tools attached. **18 of the 31 cases passed outright (58%)** under the harness's strict rule, which requires all three trials to agree before a case counts as passed at all. Four of the 31 never get scored — two are live-only smoke cases skipped by design, two hit a gap in the mock coverage that has nothing to do with the model — so against the **27 cases actually eligible, that is 18/27 (67%)**.

Before the strict rule is applied, the raw per-trial rates were **19/27 (70%), 23/27 (85%) and 20/27 (74%)**, a mean of **62/81 (77%)**. Best trial and worst trial are four cases apart, on identical cases with nothing else changed. That is why the strict rule exists, and why one trial of anything is not evidence.

## The failure we keep on purpose

One case is kept failing deliberately, and it is the most useful line in the report. Asked whether a UK company is VAT-registered, the model called `search_company` to confirm the company's identity, then answered "Companies House ... doesn't publish VAT registration data" — correct, and never checked against that record's actual `vat_registered: null`. The search result carries no VAT field at all, so the only way to answer it *from the tool* is to look the company up and read the null. Pass rate: 1 of 3.

The no-tools arm found the same behaviour from the other side the same day. On that same case it answered "Yes, Tesco PLC is VAT-registered ... since its taxable turnover far exceeds the threshold" — confident, reasoned, unsourced. Same answer shape; one of them merely had a tool available to skip.

Which is the thing a register actually buys, and it is not accuracy. It is provenance: the difference between an answer that happens to be right and an answer with a record behind it.

## What this does not claim

- **31 hand-authored cases.** We wrote them. Not a public benchmark, not a random sample of what anyone actually asks.
- **Mocked registers.** Every offline case runs against `tests/fixtures/*.json`, not the live registers. This measures whether a model uses the tool surface correctly — not brreg's, Companies House's or Bolagsverket's own data quality, coverage or uptime.
- **One model, one day, three trials.** Not a cross-model comparison.

The caveat sentence to carry away is the report's own: this measures whether one named model, on one day, answering 31 questions someone wrote by hand against mocked data, uses this tool correctly and knows the difference between "the register says no" and "the register doesn't say". It says nothing about a harder question, a different model, or the real registers' own accuracy.

The no-tools half cost $0.20 to produce — **45 calls, 1,281 input and 19,520 output tokens** at list pricing. The harness, the cases and both reports are in the repo, so the disagreement can be with the data rather than with us.

```bash
claude mcp add registry-mcp --transport http "https://api.foretak.dev/mcp?src=devto"
# or locally, over stdio: uvx registry-mcp
```

Harness, cases and reports (`evals/`), MIT: <https://github.com/foretak/registry-mcp>
