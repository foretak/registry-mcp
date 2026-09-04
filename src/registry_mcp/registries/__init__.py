"""National registry modules.

One folder per country. Importing this package imports every bundled module,
and each module registers itself with ``core.registry.register()``.

**Adding a country is: create the folder, add one import line below.** That
line is the only shared file a new country touches, and it is outside ``core/``
(``DECISIONS.md`` D-008).
"""

# Each import registers its country with core.registry.register() as a side effect.
from registry_mcp.registries import gb as gb
from registry_mcp.registries import no as no
from registry_mcp.registries import xx as xx

__all__: list[str] = []
