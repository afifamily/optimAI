"""Tests for optimai.server — FastMCP stdio surface, registry-driven (DEC-005, DEC-021).

The decisive guard here is `test_server_tools_match_registry`: it would fail
the moment someone hardcodes an extra tool or omits a pattern. The other tests
shore up the surface (flattened input schema, error mapping, end-to-end via
the in-memory FastMCP client) but the registry-match guard is the architectural
canary for DEC-021.
"""

from pathlib import Path

import httpx
import pytest
from fastmcp import Client

import optimai.server as server_mod
from optimai.patterns import base as patterns_base
from optimai.patterns.base import available_patterns
from optimai.schemas.task_spec import DiagnoseSpec
from optimai.server import build_server

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLACKLIST = REPO_ROOT / "config" / "blacklist.txt"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _scripted_worker(responses: list[str]) -> httpx.AsyncClient:
    """Mock OpenAI-compatible chat endpoint returning canned worker replies."""
    cursor = {"i": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        i = cursor["i"]
        cursor["i"] += 1
        if i >= len(responses):
            return httpx.Response(500, text=f"only {len(responses)} responses prepared")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": responses[i]},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _report_block() -> str:
    return (
        "THINK: done\n"
        "ACTION: report\n"
        "ROOT_CAUSE: ok\n"
        "EVIDENCE:\n"
        "- saw expected output\n"
        "TEMPORARY_FIX: none\n"
        "PERMANENT_FIX: none\n"
    )


@pytest.fixture
def _registry_isolation():
    """Snapshot/restore the registry so ad-hoc pattern registrations don't leak."""
    snapshot = dict(patterns_base._REGISTRY)
    yield
    patterns_base._REGISTRY.clear()
    patterns_base._REGISTRY.update(snapshot)


# --------------------------------------------------------------------------
# DEC-021 sentinel: tools must mirror the registry, no hardcoded list.
# --------------------------------------------------------------------------


async def test_server_tools_match_registry():
    """Every registered pattern → exactly one `optimai_<name>` tool, no more."""
    mcp = build_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool_names = {t.name for t in tools}
    expected = {f"optimai_{n}" for n in available_patterns()}
    assert tool_names == expected


async def test_server_picks_up_new_pattern_without_touching_server(_registry_isolation):
    """The dividend: register a pattern *after* import → it shows up as a tool.

    This is the test the brief asks for explicitly. It registers a fake pattern
    on the live registry, rebuilds the server, and asserts the new tool appears
    — without `server.py` having any awareness of the pattern.
    """
    from optimai.patterns.base import Step  # local import — registry test only

    class _GhostPattern:
        name = "ghost"
        spec_model = DiagnoseSpec
        tool_description = "Ghost pattern used to prove DEC-021 dynamism."

        def system_prompt(self, spec):
            return ""

        def initial_user_message(self, spec):
            return ""

        def operator_text(self, spec):
            return spec.goal

        def parse(self, worker_text):
            return Step(kind="invalid", reason="ghost")

        def build_report(self, **_kw):
            return None

        def on_command_timeout(self, cmd, step):
            return "abort"

    patterns_base._REGISTRY["ghost"] = _GhostPattern()
    mcp = build_server()
    async with Client(mcp) as client:
        tool_names = {t.name for t in await client.list_tools()}
    assert "optimai_ghost" in tool_names


# --------------------------------------------------------------------------
# Input schema: flattened spec fields (no nested `spec` object)
# --------------------------------------------------------------------------


async def test_diagnose_tool_flattens_spec_fields():
    mcp = build_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    schema = by_name["optimai_diagnose"].inputSchema
    props = schema["properties"]
    assert {"goal", "context", "workdir", "allowed_read_paths", "extra_blacklist"} <= set(props)
    # `goal` and `workdir` are required; the rest carry defaults.
    assert set(schema["required"]) == {"goal", "workdir"}
    # No nested `spec` object — the failure mode this test catches.
    assert "spec" not in props


async def test_execute_tool_flattens_spec_fields():
    mcp = build_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    schema = by_name["optimai_execute"].inputSchema
    props = schema["properties"]
    assert {"goal", "context", "workdir", "commands"} <= set(props)
    assert "commands" in schema["required"]
    assert "spec" not in props


# --------------------------------------------------------------------------
# Phase 2 — Patch (B) + Create (C) appear automatically via the registry
# --------------------------------------------------------------------------


async def test_patch_and_create_tools_appear_with_no_server_changes():
    """DEC-021 dividend: server.py is untouched but the new patterns show up."""
    mcp = build_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "optimai_patch" in names
    assert "optimai_create" in names


async def test_patch_tool_flattens_spec_fields():
    mcp = build_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    schema = {t.name: t for t in tools}["optimai_patch"].inputSchema
    props = schema["properties"]
    assert {"goal", "workdir", "edits"} <= set(props)
    assert "edits" in schema["required"]
    assert "spec" not in props


async def test_create_tool_flattens_spec_fields():
    mcp = build_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    schema = {t.name: t for t in tools}["optimai_create"].inputSchema
    props = schema["properties"]
    assert {"goal", "workdir", "files"} <= set(props)
    assert "files" in schema["required"]
    assert "spec" not in props


# --------------------------------------------------------------------------
# tool_description carried through
# --------------------------------------------------------------------------


async def test_tool_descriptions_non_empty():
    mcp = build_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    for t in tools:
        assert t.description and t.description.strip(), f"{t.name} has empty description"


# --------------------------------------------------------------------------
# Error mapping: PatternRejected -> ToolError
# --------------------------------------------------------------------------


async def test_pattern_rejected_maps_to_tool_error(monkeypatch, tmp_path):
    """A blacklist hit in dispatch surfaces as a clean MCP ToolError to the client."""
    from optimai.dispatcher import PatternRejected

    async def fake_dispatch(name, spec, **_kwargs):
        raise PatternRejected("blacklist match: 'sudo'")

    monkeypatch.setattr(server_mod, "dispatch", fake_dispatch)

    mcp = build_server()
    async with Client(mcp) as client:
        with pytest.raises(Exception) as exc_info:  # noqa: BLE001 — surfaced as ToolError
            await client.call_tool(
                "optimai_diagnose",
                {"goal": "investigate something benign", "workdir": str(tmp_path)},
            )
    # The FastMCP client raises ToolError mirroring the server-side mapping.
    assert "blacklist" in str(exc_info.value).lower()


# --------------------------------------------------------------------------
# Input validation: missing workdir, blank goal -> client-side validation
# --------------------------------------------------------------------------


async def test_missing_workdir_rejected_by_schema(tmp_path):
    mcp = build_server()
    async with Client(mcp) as client:
        with pytest.raises(Exception):  # noqa: BLE001 — validation error from FastMCP
            await client.call_tool(
                "optimai_diagnose",
                {"goal": "investigate something benign"},  # no workdir
            )


async def test_nonexistent_workdir_rejected_by_validator(tmp_path):
    """`DiagnoseSpec._workdir_must_exist` rejects ghost paths before dispatch runs."""
    mcp = build_server()
    bogus = tmp_path / "does-not-exist"
    async with Client(mcp) as client:
        with pytest.raises(Exception) as exc_info:  # noqa: BLE001
            await client.call_tool(
                "optimai_diagnose",
                {"goal": "investigate something benign", "workdir": str(bogus)},
            )
    assert "workdir" in str(exc_info.value).lower() or "exist" in str(exc_info.value).lower()


# --------------------------------------------------------------------------
# Mocked end-to-end: tool call -> dispatch -> DiagnoseReport (via in-memory MCP)
# --------------------------------------------------------------------------


async def test_optimai_diagnose_end_to_end_mocked(monkeypatch, tmp_path):
    """Run the full chain Cortex (client) -> MCP tool -> dispatch -> report.

    The dispatcher's `dispatch` is monkeypatched at the server module to inject
    a mock httpx client whose responses converge in one report turn. That keeps
    the assertion focused on the MCP boundary rather than re-testing dispatcher
    semantics already covered in test_dispatcher.
    """
    from optimai.dispatcher import dispatch as real_dispatch

    async def patched_dispatch(name, spec, **_kwargs):
        async with _scripted_worker([_report_block()]) as worker:
            from optimai.config import Settings

            settings = Settings(
                OPTIMAI_MAX_ITERATIONS=3,
                OPTIMAI_TIMEOUT_SECONDS=30,
                OPTIMAI_MAX_OUTPUT_BYTES=10240,
                OPTIMAI_BLACKLIST_FILE=DEFAULT_BLACKLIST,
            )
            return await real_dispatch(name, spec, settings=settings, client=worker)

    monkeypatch.setattr(server_mod, "dispatch", patched_dispatch)

    mcp = build_server()
    async with Client(mcp) as client:
        result = await client.call_tool(
            "optimai_diagnose",
            {
                "goal": "investigate something benign for the MCP test",
                "context": "(test)",
                "workdir": str(tmp_path),
            },
        )
    # `result.data` is the structured form; FastMCP rebuilds it from the
    # serialized pydantic report. Assert on the shape, not the precise model.
    data = result.data
    assert data is not None
    # Either a dict (when FastMCP serializes the pydantic model) or an object
    # with attributes — both shapes are acceptable contract-wise.
    if isinstance(data, dict):
        assert data["status"] == "complete"
        assert data["stop_reason"] == "converged"
        assert data["root_cause"] == "ok"
    else:
        assert getattr(data, "status") == "complete"
        assert getattr(data, "stop_reason") == "converged"
        assert getattr(data, "root_cause") == "ok"


# --------------------------------------------------------------------------
# Logging hygiene: stdout stays untouched, file handler is wired.
# --------------------------------------------------------------------------


def test_configure_logging_routes_to_file_and_stderr_only(tmp_path, monkeypatch):
    """`_configure_logging` must not attach any handler to stdout (DEC-005 stdio)."""
    from optimai.config import Settings

    log_path = tmp_path / "logs" / "optimai.log"
    settings = Settings(
        OPTIMAI_LOG_LEVEL="INFO",
        OPTIMAI_LOG_FILE=log_path,
        OPTIMAI_BLACKLIST_FILE=DEFAULT_BLACKLIST,
    )

    import logging
    import sys

    server_mod._configure_logging(settings)
    pkg_logger = logging.getLogger("optimai")
    streams = [
        h.stream for h in pkg_logger.handlers if isinstance(h, logging.StreamHandler)
    ]
    # WARNING: a stdout handler would corrupt the JSON-RPC stream under stdio.
    assert sys.stdout not in streams
    # stderr is the allowed mirror, ERROR-only.
    stderr_handlers = [
        h
        for h in pkg_logger.handlers
        if isinstance(h, logging.StreamHandler) and h.stream is sys.stderr
    ]
    assert len(stderr_handlers) == 1
    assert stderr_handlers[0].level == logging.ERROR
    # File handler exists and points at the configured path.
    file_handlers = [h for h in pkg_logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert Path(file_handlers[0].baseFilename) == log_path.resolve()
    # Idempotent: a second call replaces handlers instead of stacking them.
    server_mod._configure_logging(settings)
    pkg_logger = logging.getLogger("optimai")
    assert len(pkg_logger.handlers) == 2  # file + stderr
