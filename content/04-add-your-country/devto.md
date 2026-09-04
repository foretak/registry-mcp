# Add your country's company registry to registry-mcp in an afternoon

`registry-mcp` is a company registry MCP server. Today it answers for one country — Norway's Brønnøysundregistrene / Enhetsregisteret (brreg), by organisasjonsnummer (orgnr, org.nr). The architecture's whole bet is that the second country is **one folder plus one import line**. Here's the proof, and the invitation.

## The template already ships

`src/registry_mcp/registries/xx/` is a fake country that is fully wired up. Copy it to `registries/<cc>/` and fill in six steps — its module docstring is the recipe.

## The interface is four methods

```python
class Registry(ABC):
    country = "SE"; registry = "bolagsverket"
    id_scheme = "organisationsnummer"; id_example = "5560212524"
    # + name, id_description, source_url, license, is_stub

    def validate_id(self, id: str) -> str: ...          # sync, pure
    async def lookup(self, id: str) -> CompanyReport: ...
    async def search(self, name: str, limit: int = 10) -> SearchResult: ...
    def deadlines(self, report, today: date) -> list[Deadline]: ...
```

That's all you implement. `lookup`/`search` are async because they do network I/O; `validate_id` and `deadlines` are sync and pure — `deadlines` takes `today` as a parameter precisely so it's testable with no clock.

You **don't** write the response documents. `Registry.validate()` and `Registry.deadline_report()` are concrete base-class methods that wrap your four primitives into the same `ValidationResult` and `DeadlineReport` every other country emits. New country, identical JSON, both surfaces, for free.

Then `register(SeRegistry())` at the bottom of your module, and one line in `registries/__init__.py`:

```python
from registry_mcp.registries import se as se
```

That import is the only shared file you touch, and it's outside `core/`.

## Stubs are hidden, not absent

Set `is_stub = True` while you build. `list_countries()` skips you:

<!-- default server; uv run python content/call.py list_countries '{}' (excerpt) -->
```json
{"countries": [{"country": "NO", "registry": "brreg", "is_stub": false}]}
```

Set `REGISTRY_MCP_INCLUDE_STUBS=1` and the same tool shows your work in progress:

<!-- REGISTRY_MCP_INCLUDE_STUBS=1 on the server; uv run python content/call.py list_countries '{}' (excerpt) -->
```json
{"countries": [
  {"country": "NO", "registry": "brreg", "is_stub": false},
  {"country": "XX", "registry": "example", "id_scheme": "example_number",
   "id_example": "12345678", "is_stub": true}
]}
```

So `/v1/countries` never advertises a country that can't answer, while the abstraction stays testable. And it really is live — `XX`'s `validate_id` works the day you write it:

<!-- uv run python content/call.py validate_company_id '{"id": "12345678", "country": "XX"}' (excerpt) -->
```json
{"country": "XX", "id_scheme": "example_number", "input": "12345678",
 "valid": true, "normalized": "12345678", "formatted": null}
```

while the parts you haven't built yet fail honestly, with a hint:

<!-- uv run python content/call.py lookup_company '{"id": "12345678", "country": "XX"}' -->
```json
{"error": {"code": "not_implemented",
  "message": "lookup is not implemented: XX is the example template, not a real registry.",
  "hint": "Call list_countries to see the countries that are actually supported.",
  "country": "XX", "registry": "example"}}
```

## What a PR needs

1. **Fixtures captured from the live API** — two or three real entities, saved as JSON, so tests don't hit the network.
2. **Tests**, including a numbered rules list for your country's deadlines in the style of Norway's.
3. **`rules_markdown()`** — the prose an agent reads once instead of rediscovering your legal forms one call at a time.
4. `is_stub = False`, and your import line.

## Good first targets

**Denmark, CVR** — open, well-documented API; probably the easiest. **Sweden, Bolagsverket**. Both are close enough to Norway that the models fit, far enough that they'll test the abstraction honestly.

MIT: <https://github.com/foretak/registry-mcp> — open an issue with your country code and claim it.
