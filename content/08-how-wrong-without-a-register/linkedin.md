**Where and when to post:** LinkedIn, Kim's own profile, a weekday morning CET, the same day as the dev.to post or the day after. One post, not two — pick the language for the audience you want (Norwegian reaches the Norwegian finance-and-dev crowd; English reaches the MCP one). If you want both, post the Norwegian one and put the English text in the first comment, never as a second post. No hashtag block: two at most, at the end. Kim posts, not an agent.

---

## Norwegian

Vi har solgt registry-mcp på en kontrafaktisk påstand: en agent uten register svarer selvsikkert og feil. Det er lett å skrive i en README. I dag målte vi det.

Samme modell (Sonnet 5), samme håndskrevne spørsmål, to armer: 31 saker med verktøyene på, og de 15 av dem det er rimelig å stille helt uten verktøy — tre forsøk hver.

**Uten register: 45 svar, manuelt gjennomgått. 8 riktige, 3 selvsikkert feil, 34 ærlige «dette kan jeg ikke slå opp», 0 uavklarte.**

Altså: en moderne modell nekter stort sett. Den lyver ikke stort sett. Det er god oppførsel, og vi teller det ikke som en seier for produktet — å slå en modell som allerede sa «vet ikke» er ikke å slå noe som helst.

Med verktøyene på: 18 av de 27 tellende sakene bestått, etter en regel som krever at alle tre forsøk er enige.

Den mest nyttige linjen i rapporten er saken vi lar stryke med vilje. Modellen svarer «Companies House publiserer ikke MVA-status» — helt riktig — uten å slå opp selskapet i det hele tatt. Samme uunderbygde svar som armen uten verktøy ga; forskjellen er bare at denne hadde et verktøy den kunne la være å bruke.

Det er det et register faktisk kjøper deg. Ikke treffsikkerhet. Sporbarhet: forskjellen på et svar som tilfeldigvis stemmer, og et svar med et oppslag bak seg.

Forbehold, sagt først og ikke i en fotnote: 31 saker vi skrev selv, offline-sakene kjørt mot mockede registre og ikke de ekte, én modell, én dag, tre forsøk. Det sier ingenting om et vanskeligere spørsmål, en annen modell, eller registrenes egen datakvalitet.

Harness, alle 31 sakene og begge rapportene ligger i repoet, MIT. Krangle gjerne med dataene.

Skrivet: https://dev.to/fargeroddotcom/how-wrong-is-a-model-about-a-company-when-it-has-no-register-to-check-27c2
Kode: https://github.com/foretak/registry-mcp

---

## English

We have been selling registry-mcp on a counterfactual: an agent without a company register answers confidently and wrongly. That is an easy thing to assert in a README. Today we measured it.

Same model (Sonnet 5), same hand-written prompts, two arms: 31 cases with the tools attached, and the 15 of them that are fair to ask with no tools at all — three trials each.

**With no register: 45 answers, manually audited. 8 correct, 3 confidently wrong, 34 honest hedges, 0 unclear.**

So a current model mostly refuses. It does not mostly lie. That is good behaviour, and we do not score it as a win for the product — beating a model that already said "I don't know" is not beating anything.

With the tools: 18 of the 27 scorable cases passed, under a rule that requires all three trials to agree before a case counts at all.

The most useful line in the report is the case we keep failing on purpose. The model answers "Companies House doesn't publish VAT status" — correct — without ever looking the company up. It is the same unsourced answer the no-tools arm gave; this one just had a tool available to skip.

Which is what a register actually buys you. Not accuracy. Provenance: the difference between an answer that happens to be right and an answer with a lookup behind it.

Limits, stated up front rather than in a footnote: 31 cases we wrote ourselves, offline cases running against mocked fixtures rather than the live registers, one model, one day, three trials. It says nothing about a harder question, a different model, or the registers' own data quality.

The harness, all 31 cases and both raw reports are in the repo, MIT. Please argue with the data.

Write-up: https://dev.to/fargeroddotcom/how-wrong-is-a-model-about-a-company-when-it-has-no-register-to-check-27c2
Code: https://github.com/foretak/registry-mcp

---

## If you want the install line in the post

    claude mcp add registry-mcp --transport http "https://api.foretak.dev/mcp?src=linkedin"

Leave it out of the body if the post is already long — it reads as a pitch where the rest of the post is a result. The first comment is the better place for it.
