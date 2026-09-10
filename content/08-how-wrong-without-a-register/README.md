# 08 — How wrong is a model about a company when it has no register to check?

The accuracy article (T64 Part C). Unlike articles 01–07 it shows no register
output at all: its subject is `evals/reports/2026-09-10-accuracy.md`, and every
number in it is quoted from that one report.

| File | What it is |
|---|---|
| `article.md` | The canonical Markdown. 1,036 words. |
| `devto.md` | The same body with dev.to front matter (`title`, `published`, `description`, `tags`). The only prose difference is the missing `# ` heading — dev.to takes the title from the front matter. |
| `show-hn.md` | Title + four lines, for Kim to post. Not posted. |
| `linkedin.md` | Norwegian and English, for Kim to post. Not posted. |
| `reddit.md` | Three lines for r/LocalLLaMA or r/ClaudeAI, for Kim to post. Not posted. |

## Published

**dev.to, 2026-09-10:**
<https://dev.to/fargeroddotcom/how-wrong-is-a-model-about-a-company-when-it-has-no-register-to-check-27c2>
(article id `4621129`, tags `ai, mcp, llm, opensource`.)

Show HN, LinkedIn and Reddit are **not** posted — those are Kim's, per T64's
standing rules. The drafts above are ready to paste.

## Every number, and the line it came from

All from `evals/reports/2026-09-10-accuracy.md`. Nothing in the article is
computed, rounded or combined here; where the article gives a percentage, the
report gives that same percentage.

| Number in the article | Report | The line |
|---|---|---|
| 8 correct, 3 wrong, 34 honest hedges, 0 unclear, out of 45 | §1 | "Call-by-call (the number to quote, per the same manual-audit convention `2026-09-07-baseline-run-1.md` established): **8 correct, 3 wrong (confident, dangerous), 34 honest hedge, 0 unclear**, out of 45." |
| hedged on every trial for 9 of 15 (60%) | §1 | "**honestly hedged on every single trial for 9 of 15 (60%)**" |
| confidently wrong on ≥1 of 3 trials for 2 of 15 (13%) | §1 | "**confidently and dangerously wrong on at least one of three trials for 2 of 15 cases (13%)** — `E08` and `E20`" |
| correct-but-unsourced on ≥1 trial for 4 of 15 (27%) | §1 | "**produced a correct-but-unsourced answer on at least one trial for the remaining 4 of 15 (27%)** — `E05`, `E06`, `E07`, `E19`" |
| raw classifier: 6 correct, 7 wrong, 27 hedge, 5 unclear; the audit moved 12 of 45 | §1 | "The auto-classifier's raw first pass, before the manual read documented in §2, was **6 correct, 7 wrong, 27 hedge, 5 unclear** — the audit moved 12 of 45 calls" |
| 18 of 31 passed outright (58%), all three trials must agree | §1 | "**passed 18 of 31 outright (58%)** — the harness's own strict rule, requiring all three trials to agree before a case counts as passed" |
| four unscored: two live-only smoke cases, two mock-coverage gaps | §1 | "Two of the 31 are live-only smoke cases skipped by design (`E01`, `E02`); two hit a mock-coverage gap independent of the model (`E10`, `E12`, harness gaps…)" |
| 18/27 (67%) of the eligible cases | §1 | "Against only the **27 cases actually eligible to be scored**, that is **18/27 (67%)**." |
| per-trial 19/27 (70%), 23/27 (85%), 20/27 (74%); mean 62/81 (77%) | §1 | "the raw per-trial pass rate was **19/27 (70%)**, **23/27 (85%)**, **20/27 (74%)** on trials 1, 2 and 3 — mean **62/81 (77%)**" |
| best and worst trial are four cases apart | §1, but **not** its own phrasing — see "One number the report gets wrong" below | derived from the per-trial rates above (23 − 19 = 4 cases), which are the report's |
| SEC Form 20-F "due … by 30 April 2026"; Oslo Børs Q4 "early February 2026"; the real one is `2026-07-31` | §2, `E08` baseline row | "the model invented a detailed, wrong set of obligations — SEC Form 20-F "due … by 30 April 2026", an Oslo Børs Q4 release "early February 2026" — none of which are the register-derived Norwegian deadlines this case tests (the real one, `2026-07-31`…)" |
| "330,000–360,000 employees" on two of three trials, after disclaiming register access | §2, `E20` baseline row | "Twice stated a specific "330,000–360,000 employees" range as general public knowledge after disclaiming access to "the register"" / "2 of 3 trials (1, 3)" |
| the kept-failing case: pass rate 1 of 3; `vat_registered: null`; the search hit carries no VAT field | §3 | "**Pass rate 1/3**…"; "never checked against this record's actual `vat_registered: null`"; "`search_company`'s `SearchHit` carries no VAT field at all" |
| "Yes, Tesco PLC is VAT-registered … since its taxable turnover far exceeds the threshold" | §3 | quoted verbatim from §3's account of `E19`'s baseline trials |
| $0.20 — 45 calls, 1,281 input and 19,520 output tokens | §5 | "**45 calls, 1,281 input tokens + 19,520 output tokens = $0.20** at `claude-sonnet-5` list pricing ($2/$10 per MTok)" |
| 81 trials (the `description` front-matter line) | §5 | "**81 completed trials** (27 scored cases × 3)" |
| 31 hand-authored cases; mocked fixtures; one model, one day, three trials; the closing caveat sentence | §4 | "31 hand-authored cases, every offline one running against **mocked** `tests/fixtures/*.json`…" and "**The caveat sentence a reader must carry:**…" — the article's last caveat paragraph is that sentence, lightly re-punctuated, not paraphrased. |

## One number the report gets wrong

`2026-09-10-accuracy.md` §1 says "The **18-percentage-point spread** between
the best and worst trial, on the identical 27 cases with nothing else
changed". Its own rates in the same sentence do not give 18: 23/27 is 85.2%
and 19/27 is 70.4%, a spread of **14.8** points. 18.5 points is the gap
between the best trial (85.2%) and the strict-rule headline (18/27, 66.7%),
which is the likelier thing the arithmetic came from.

The article does not reproduce either figure. It says the best and worst
trials are **four cases apart**, which the reader can check against the rates
quoted two sentences earlier and which is true under any reading. Worth fixing
in the report itself — the rest of §1 is exact, and the sentence around it is
the right point badly numbered.

Numbers deliberately **not** used: the agent arm's dollar cost (§5 says it is
estimated, not measured, because `--agent` never reads `response.usage`), and
the combined ≈$1.6–$1.7 that depends on it. The article quotes only the
measured baseline figure and says which half it is.

## The install line

`?src=devto` on the hosted URL, per T64 Part B, written in before Part B lands
— the query string is inert until then and the handshake ignores it. The three
hand-posted drafts carry their own channel values (`?src=hn`, `?src=linkedin`,
`?src=reddit`) so the gate's "calls by channel" count can tell them apart;
Part B's own list assigns `src=article` to `content/`, which is the right
default for an article whose channel is not known in advance.

## Publishing it

`content/publish_devto.py` grew two subcommands for this article:

```bash
DEVTO_API_KEY=$(cat ~/secrets/registry-mcp/devto-api-key.txt) \
  python content/publish_devto.py create content/08-how-wrong-without-a-register/devto.md
DEVTO_API_KEY=$(cat ~/secrets/registry-mcp/devto-api-key.txt) \
  python content/publish_devto.py update 4621129 content/08-how-wrong-without-a-register/devto.md
```

The thing worth knowing for the next article: **dev.to's front matter wins over
the API field.** `publish <id>` sends `{"published": true}` and returns a URL
that looks published, but an article whose `body_markdown` front matter still
says `published: false` stays a draft. Set `published: true` in the file and
`update` it. `publish <id>` is still correct for articles 01–05, whose drafts
carry no front matter at all.
