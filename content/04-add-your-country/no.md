# Legg til ditt eget lands foretaksregister i registry-mcp på en ettermiddag

`registry-mcp` er en MCP-server for foretaksdata. I dag svarer den for ett land — Brønnøysundregistrene / Enhetsregisteret (brreg), på organisasjonsnummer (orgnr, org.nr). Hele arkitekturens veddemål er at land nummer to skal være **én mappe pluss én import-linje**. Her er beviset, og invitasjonen.

## Malen ligger allerede i repoet

`src/registry_mcp/registries/xx/` er et oppdiktet land som er fullt koblet opp. Kopier mappa til `registries/<cc>/` og fyll ut seks steg — oppskriften står i docstringen til modulen.

## Grensesnittet er fire metoder

```python
class Registry(ABC):
    country = "SE"; registry = "bolagsverket"
    id_scheme = "organisationsnummer"; id_example = "5560212524"
    # + name, id_description, source_url, license, is_stub

    def validate_id(self, id: str) -> str: ...          # synkron, ren
    async def lookup(self, id: str) -> CompanyReport: ...
    async def search(self, name: str, limit: int = 10) -> SearchResult: ...
    def deadlines(self, report, today: date) -> list[Deadline]: ...
```

Det er alt du implementerer. `lookup` og `search` er asynkrone fordi de gjør nettverkskall; `validate_id` og `deadlines` er synkrone og rene — `deadlines` tar `today` som parameter nettopp for å være testbar uten klokke.

Du skriver **ikke** svardokumentene selv. `Registry.validate()` og `Registry.deadline_report()` er konkrete metoder i basisklassen som pakker de fire primitivene dine inn i den samme `ValidationResult`-en og `DeadlineReport`-en som alle andre land returnerer. Nytt land, identisk JSON, begge flater, gratis.

Så `register(SeRegistry())` nederst i modulen din, og én linje i `registries/__init__.py`:

```python
from registry_mcp.registries import se as se
```

Den import-linja er den eneste delte fila du rører, og den ligger utenfor `core/`.

## Stubber er skjult, ikke fraværende

Sett `is_stub = True` mens du bygger. `list_countries()` hopper over deg:

<!-- standard server; uv run python content/call.py list_countries '{}' (utdrag) -->
```json
{"countries": [{"country": "NO", "registry": "brreg", "is_stub": false}]}
```

Sett `REGISTRY_MCP_INCLUDE_STUBS=1`, og det samme verktøyet viser arbeidet ditt:

<!-- REGISTRY_MCP_INCLUDE_STUBS=1 på serveren; uv run python content/call.py list_countries '{}' (utdrag) -->
```json
{"countries": [
  {"country": "NO", "registry": "brreg", "is_stub": false},
  {"country": "XX", "registry": "example", "id_scheme": "example_number",
   "id_example": "12345678", "is_stub": true}
]}
```

Dermed reklamerer aldri `/v1/countries` med et land som ikke kan svare, samtidig som abstraksjonen forblir testbar. Og den lever fra dag én — `validate_id` for `XX` virker med det samme du har skrevet den:

<!-- uv run python content/call.py validate_company_id '{"id": "12345678", "country": "XX"}' (utdrag) -->
```json
{"country": "XX", "id_scheme": "example_number", "input": "12345678",
 "valid": true, "normalized": "12345678", "formatted": null}
```

mens delene du ennå ikke har bygget, feiler ærlig — med et hint:

<!-- uv run python content/call.py lookup_company '{"id": "12345678", "country": "XX"}' -->
```json
{"error": {"code": "not_implemented",
  "message": "lookup is not implemented: XX is the example template, not a real registry.",
  "hint": "Call list_countries to see the countries that are actually supported.",
  "country": "XX", "registry": "example"}}
```

## Hva en PR må inneholde

1. **Fixtures hentet fra det live API-et** — to–tre reelle enheter, lagret som JSON, slik at testene slipper nettverket.
2. **Tester**, inkludert en nummerert regelliste for landets frister, i samme stil som den norske.
3. **`rules_markdown()`** — prosaen en agent leser én gang, i stedet for å oppdage organisasjonsformene dine ett kall om gangen.
4. `is_stub = False`, og import-linja di.

## Gode førstevalg

**Danmark, CVR** — åpent og godt dokumentert API; trolig det enkleste. **Sverige, Bolagsverket**. Begge ligger nært nok Norge til at modellene passer, og langt nok unna til at de tester abstraksjonen på ordentlig.

MIT: <https://github.com/foretak/registry-mcp> — åpne et issue med landkoden din og ta den.
