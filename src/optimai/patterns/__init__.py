"""Task patterns — A (Diagnose) + D (Execute) + B (Patch) + C (Create) + E (Scan).

Importing this package also imports each pattern module so that their
`@register(...)` decorators populate the registry. Any code that goes through
`optimai.patterns.base` (e.g. the dispatcher, the MCP server) therefore sees
every built-in pattern without an explicit import.

DEC-006 phasing: A/D are Phase 1; B/C are Phase 2 (DEC-024); E is Phase 3
(DEC-025, DEC-026).
"""

from optimai.patterns import create  # noqa: F401  # side-effect: register("create")
from optimai.patterns import diagnose  # noqa: F401  # side-effect: register("diagnose")
from optimai.patterns import execute  # noqa: F401  # side-effect: register("execute")
from optimai.patterns import patch  # noqa: F401  # side-effect: register("patch")
from optimai.patterns import scan  # noqa: F401  # side-effect: register("scan")
