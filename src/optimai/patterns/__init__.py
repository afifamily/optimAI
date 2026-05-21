"""Task patterns — priority A (Diagnose) and D (Execute) for Phase 1 (DEC-006, DEC-021).

Importing this package also imports each pattern module so that their
`@register(...)` decorators populate the registry. Any code that goes through
`optimai.patterns.base` (e.g. the dispatcher) therefore sees the built-in
patterns without an explicit import.
"""

from optimai.patterns import diagnose  # noqa: F401  # side-effect: register("diagnose")
from optimai.patterns import execute  # noqa: F401  # side-effect: register("execute")
