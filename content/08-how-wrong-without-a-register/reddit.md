**Where and when to post:** r/LocalLLaMA (first choice — the eval design is the draw there) or r/ClaudeAI, not both the same day, and not the same day as any r/mcp post. Text post, three lines, links in the first comment only. Kim posts, not an agent.

## Title

I measured what a model says about a company when it has no register to check: 45 answers, 3 confidently wrong, 34 honest hedges

## Body (three lines)

Same model (Sonnet 5), same hand-written prompts, two arms: 31 cases with company-register tools attached, and the 15 of them that are fair to ask with `tools` and `system` stripped out of the API call entirely, three trials each.

With no register, the 45 no-tools answers audited out at 8 correct, 3 confidently wrong, 34 honest hedges, 0 unclear — so a current model mostly refuses rather than fabricates, which is the opposite of the result the product would have wanted; with the tools, 18 of 27 scorable cases passed under a rule requiring all three trials to agree.

Limits are the whole story here: 31 cases I wrote myself, offline cases against mocked fixtures rather than the live registers, one model, one day, three trials — and the case I keep failing on purpose is the model answering "Companies House doesn't publish VAT status" correctly *without ever looking the company up*, which is the same unsourced answer the no-tools arm gave, just with a tool available to skip.

## First comment (post it right after)

Write-up, with every number and its caveat: https://dev.to/fargeroddotcom/how-wrong-is-a-model-about-a-company-when-it-has-no-register-to-check-27c2

Harness, the 31 cases and both raw reports are in `evals/`, MIT — argue with the data: https://github.com/foretak/registry-mcp
