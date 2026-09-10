**Where and when to post:** Hacker News, Show HN, a weekday morning US Eastern; Kim posts, not an agent. Show HN wants a thing people can try, so the tool is the submission and the article is the evidence — link the repo as the URL and put the dev.to write-up in the text. Answer every comment; the harness is in the repo, so expect the argument to be about the eval design, and that is the argument worth having.

## Title

Show HN: Company registers for AI agents (Norway, UK, Sweden), and the eval

## Text (four lines)

registry-mcp puts three national company registers behind one MCP tool and one REST API — Norway's brreg, the UK's Companies House, Sweden's Bolagsverket — free, no key, no account: `claude mcp add registry-mcp --transport http "https://api.foretak.dev/mcp?src=hn"`.

The pitch for anything like this is a counterfactual — an agent without a register answers confidently and wrongly — so I measured it instead of asserting it: the same Sonnet 5 model over 31 hand-written cases with the tools, and over the 15 of them that are fair to ask without, three trials each. With no register, 45 answers came back 8 correct, 3 confidently wrong, 34 honest hedges. The model mostly refuses. It does not mostly lie, and that is not the result I set out to publish.

With the tools, 18 of the 27 scorable cases passed under a rule that requires all three trials to agree; the case I keep failing on purpose is the useful one, where the model answers "Companies House doesn't publish VAT status" correctly without ever looking the company up. So what a register buys an agent is not accuracy — it is provenance, the difference between an answer that happens to be right and an answer with a record behind it.

Limits, up front: 31 cases I wrote myself, offline cases running against mocked fixtures rather than the live registers, one model, one day, three trials — it says nothing about a harder question, a different model, or the registers' own data quality. Harness, cases and both reports are in the repo (MIT): https://github.com/foretak/registry-mcp — write-up: https://dev.to/fargeroddotcom/how-wrong-is-a-model-about-a-company-when-it-has-no-register-to-check-27c2
