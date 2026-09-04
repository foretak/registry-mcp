**Title:** registry-mcp: company registry MCP server, one country done, your country is a folder and an import line

Norway (Brønnøysundregistrene / Enhetsregisteret, brreg, organisasjonsnummer) works today. A second country is a subclass of `Registry` with four methods — `validate_id`, `lookup`, `search`, `deadlines` — plus `register(YourRegistry())` and one import line in `registries/__init__.py`. Nothing in `core/` changes.

You don't build the response documents: `Registry.validate()` and `deadline_report()` are concrete base-class methods, so your country emits byte-identical JSON to every other, on both MCP and REST, for free.

`registries/xx/` is a working template with the six-step recipe in its docstring. `is_stub = True` hides you from `list_countries()` while you build; `REGISTRY_MCP_INCLUDE_STUBS=1` shows you. Unfinished methods raise `not_implemented` with a hint rather than lying.

A PR needs: fixtures captured from the live API, tests, `rules_markdown()`.

Best first targets: Denmark CVR, Sweden Bolagsverket. MIT: github.com/foretak/registry-mcp
