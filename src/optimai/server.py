"""FastMCP stdio server — one MCP tool per registered pattern (DEC-005, DEC-021).

The server does NOT know about Diagnose or Execute by name. It iterates
`available_patterns()` and builds one `optimai_<name>` tool per registry entry,
deriving each tool's input schema from the pattern's `spec_model` (flattened
fields), its description from the pattern's `tool_description`, and its handler
from a closure over `dispatch(name, spec)`. Adding a Phase-2 pattern therefore
adds a tool without touching this file — the architectural dividend DEC-021
paid for and that `test_server_tools_match_registry` guards.

Hygiene (stdio transport):
- stdout is the JSON-RPC channel; we route logging to a file handler with an
  ERROR-only mirror on stderr. No print, no banner on stdout — that would
  corrupt the protocol stream.
"""

import inspect
import logging
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools.tool import Tool
from pydantic import BaseModel
from pydantic.fields import FieldInfo

import optimai.patterns  # noqa: F401 — side-effect: populates the pattern registry
from optimai.config import Settings, get_settings
from optimai.dispatcher import PatternRejected, dispatch
from optimai.patterns.base import Pattern, available_patterns, get_pattern

logger = logging.getLogger(__name__)


def _configure_logging(settings: Settings) -> None:
    """Wire `optimai.*` logs to a file; mirror ERROR on stderr; never touch stdout.

    Targets the `optimai` namespace logger (not root) so a host that pipes
    arbitrary libraries through `logging` cannot accidentally spam our file
    sink. Idempotent: re-running `main()` in the same process replaces the
    handlers instead of stacking them.
    """
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level = logging.getLevelName(settings.log_level)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    pkg_logger = logging.getLogger("optimai")
    pkg_logger.setLevel(level)
    # Drop previously attached handlers so this function is safe to call twice.
    for h in list(pkg_logger.handlers):
        pkg_logger.removeHandler(h)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    pkg_logger.addHandler(file_handler)

    # WARNING: stderr only — anything on stdout would corrupt the JSON-RPC
    # channel under MCP stdio transport.
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(fmt)
    pkg_logger.addHandler(stderr_handler)

    pkg_logger.propagate = False


def _field_default(info: FieldInfo) -> Any:
    """Translate a pydantic FieldInfo into an `inspect.Parameter`-compatible default.

    Required fields → `Parameter.empty` (no default). Optional fields with a
    `default_factory` → an invocation of that factory (so e.g. `list` becomes
    `[]` and FastMCP advertises a real default in the JSON schema rather than
    the pydantic `PydanticUndefined` sentinel).
    """
    if info.is_required():
        return inspect.Parameter.empty
    if info.default_factory is not None:
        return info.default_factory()
    return info.default


def _make_tool_handler(pattern_name: str, spec_model: type[BaseModel]):
    """Build the async handler exposed as `optimai_<pattern_name>`.

    The signature is constructed from `spec_model.model_fields` so the MCP tool
    advertises flattened keyword arguments (e.g. `goal`, `context`, `workdir`)
    instead of a nested `spec` object — that is the ergonomic input shape for
    the Cortex side.

    Late-binding guard: `pattern_name` and `spec_model` are captured as default
    args of the inner function via this factory closure, never by free-name
    lookup in a loop — so each pattern's handler keeps its own identity.
    """

    async def _handler(**kwargs: Any) -> BaseModel:
        spec = spec_model(**kwargs)
        try:
            report = await dispatch(pattern_name, spec)
        except PatternRejected as exc:
            # Frontier mapping: an operator-text blacklist hit becomes a clean
            # MCP-level error rather than a stack trace propagating to the Cortex.
            raise ToolError(str(exc)) from exc
        return report

    params = [
        inspect.Parameter(
            fname,
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=_field_default(finfo),
            annotation=finfo.annotation,
        )
        for fname, finfo in spec_model.model_fields.items()
    ]
    _handler.__signature__ = inspect.Signature(parameters=params)  # type: ignore[attr-defined]
    _handler.__annotations__ = {
        fname: finfo.annotation for fname, finfo in spec_model.model_fields.items()
    }
    _handler.__name__ = f"optimai_{pattern_name}"
    _handler.__doc__ = None  # description is supplied explicitly via Tool.from_function
    return _handler


def _register_patterns(mcp: FastMCP) -> None:
    """Iterate the registry and attach one tool per pattern. No hardcoded list."""
    for name in available_patterns():
        pattern: Pattern = get_pattern(name)
        handler = _make_tool_handler(name, pattern.spec_model)
        tool = Tool.from_function(
            handler,
            name=f"optimai_{name}",
            description=pattern.tool_description,
        )
        mcp.add_tool(tool)
        logger.info("registered tool optimai_%s (spec=%s)", name, pattern.spec_model.__name__)


def build_server(settings: Settings | None = None) -> FastMCP:
    """Construct the FastMCP server with all registered patterns attached.

    Split out from `main()` so tests can instantiate the server in-process via
    `fastmcp.Client(build_server())` without touching stdio or logging.
    """
    settings = settings or get_settings()
    mcp = FastMCP("optimai")
    _register_patterns(mcp)
    return mcp


def main() -> None:
    """Entry point for `uv run python -m optimai.server` / `optimai` console script."""
    settings = get_settings()
    _configure_logging(settings)
    logger.info("optimai MCP server starting (patterns=%s)", available_patterns())
    mcp = build_server(settings)
    # FastMCP defaults to stdio when invoked through `.run()` without a transport
    # argument; stay on the default so the host (Claude Desktop / CLI) drives it.
    mcp.run()


if __name__ == "__main__":
    main()
