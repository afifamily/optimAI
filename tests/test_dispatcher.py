"""Tests for optimai.dispatcher — the single bounded loop (DEC-007, DEC-021).

Worker is mocked via httpx.MockTransport (a sequence of pre-canned replies),
shell is sometimes real (`echo` / a real blacklist hit) and sometimes
monkeypatched (per-command timeout, shell error). Combining both keeps the
loop semantics under test without relying on a live mlx_lm.server.
"""

import asyncio
from pathlib import Path

import httpx
import pytest

from optimai import dispatcher as dispatcher_mod
from optimai.config import Settings
from optimai.dispatcher import PatternRejected, dispatch
from optimai.patterns import base as patterns_base
from optimai.schemas.report import DiagnoseReport
from optimai.schemas.task_spec import DiagnoseSpec
from optimai.shell import CommandResult, CommandTimeout, ShellError

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLACKLIST = REPO_ROOT / "config" / "blacklist.txt"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _make_settings(*, max_iter: int = 5, timeout: int = 300) -> Settings:
    """A Settings instance with a known blacklist path, overridable budgets."""
    return Settings(
        OPTIMAI_MAX_ITERATIONS=max_iter,
        OPTIMAI_TIMEOUT_SECONDS=timeout,
        OPTIMAI_MAX_OUTPUT_BYTES=10240,
        OPTIMAI_BLACKLIST_FILE=DEFAULT_BLACKLIST,
    )


def _spec(workdir: Path, *, goal: str = "investigate something benign for the test") -> DiagnoseSpec:
    return DiagnoseSpec(goal=goal, context="(test)", workdir=workdir)


def _scripted_worker(responses: list[str]) -> httpx.AsyncClient:
    """An AsyncClient whose POSTs return `responses` in order, then 500."""
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
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _report_block(root_cause: str = "ok") -> str:
    return (
        "THINK: done\n"
        "ACTION: report\n"
        f"ROOT_CAUSE: {root_cause}\n"
        "EVIDENCE:\n"
        "- saw the expected output\n"
        "TEMPORARY_FIX: none\n"
        "PERMANENT_FIX: none\n"
    )


def _shell_block(cmd: str) -> str:
    return f"THINK: try\nACTION: shell\nCMD: {cmd}\n"


# --------------------------------------------------------------------------
# convergence — happy path
# --------------------------------------------------------------------------


async def test_dispatch_converges(tmp_path):
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [_shell_block("echo hello"), _report_block("toolchain ok")]

    async with _scripted_worker(responses) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    assert isinstance(report, DiagnoseReport)
    assert report.status == "complete"
    assert report.stop_reason == "converged"
    assert report.iterations_used == 2
    assert report.root_cause == "toolchain ok"
    assert len(report.commands_executed) == 1
    assert report.commands_executed[0]["cmd"] == "echo hello"
    assert report.commands_executed[0]["exit"] == 0


# --------------------------------------------------------------------------
# max_iterations
# --------------------------------------------------------------------------


async def test_dispatch_hits_max_iterations(tmp_path):
    settings = _make_settings(max_iter=3, timeout=30)
    spec = _spec(tmp_path)
    # The worker never reports — always asks for another echo.
    responses = [_shell_block("echo a"), _shell_block("echo b"), _shell_block("echo c")]

    async with _scripted_worker(responses) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    assert report.status == "incomplete"
    assert report.stop_reason == "max_iterations"
    assert report.iterations_used == 3
    assert len(report.commands_executed) == 3


# --------------------------------------------------------------------------
# global timeout — wait_for fires around the loop
# --------------------------------------------------------------------------


async def test_dispatch_global_timeout(tmp_path):
    """The dispatch wraps the loop in asyncio.wait_for(timeout_seconds)."""
    settings = _make_settings(max_iter=5, timeout=1)
    spec = _spec(tmp_path)

    async def slow_handler(_request):
        await asyncio.sleep(3)
        return httpx.Response(200, json={"choices": [], "usage": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow_handler)) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    assert report.status == "incomplete"
    assert report.stop_reason == "timeout"
    assert "global timeout" in report.notes


# --------------------------------------------------------------------------
# per-command timeout is RECOVERABLE (DEC-007 annotation)
# --------------------------------------------------------------------------


async def test_dispatch_recovers_from_per_command_timeout(monkeypatch, tmp_path):
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [_shell_block("sleep 99"), _report_block("recovered")]

    calls = {"n": 0}

    async def fake_run(cmd, workdir, *, patterns, timeout_seconds, max_output_bytes, env=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise CommandTimeout(f"fake per-command timeout for: {cmd}")
        return CommandResult(
            cmd=cmd,
            exit_code=0,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_seconds=0.0,
        )

    monkeypatch.setattr(dispatcher_mod, "shell_run", fake_run)

    async with _scripted_worker(responses) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    # The first command timed out, the loop continued, and the worker delivered
    # a report on the SECOND turn — the report itself doesn't need a 2nd command.
    assert report.status == "complete"
    assert report.stop_reason == "converged"
    assert report.iterations_used == 2
    # Only one command was attempted (the second turn was a report, not a CMD).
    assert len(report.commands_executed) == 1
    assert report.commands_executed[0]["exit"] == -1  # timeout marker


# --------------------------------------------------------------------------
# blacklist violation — defense in depth via shell.run
# --------------------------------------------------------------------------


async def test_dispatch_blacklist_violation(tmp_path):
    """A worker that proposes `sudo ls` triggers the real blacklist."""
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [_shell_block("sudo ls /"), _report_block("ignored")]

    async with _scripted_worker(responses) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    assert report.status == "error"
    assert report.stop_reason == "blacklist_violation"
    assert report.iterations_used == 1
    assert len(report.commands_executed) == 1
    assert report.commands_executed[0]["exit"] == -1


# --------------------------------------------------------------------------
# shell error (non-timeout) — fatal
# --------------------------------------------------------------------------


async def test_dispatch_shell_error_is_fatal(monkeypatch, tmp_path):
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [_shell_block("echo hello"), _report_block("ignored")]

    async def fake_run(*_a, **_k):
        raise ShellError("kaboom")

    monkeypatch.setattr(dispatcher_mod, "shell_run", fake_run)

    async with _scripted_worker(responses) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    assert report.status == "error"
    assert report.stop_reason == "shell_error"
    assert "kaboom" in report.notes


# --------------------------------------------------------------------------
# worker invalid output — 1 correction allowed, then fail
# --------------------------------------------------------------------------


async def test_dispatch_invalid_then_valid_recovers(tmp_path):
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [
        "the model forgot the protocol entirely",  # invalid -> trigger correction
        _shell_block("echo hi"),
        _report_block("converged after correction"),
    ]

    async with _scripted_worker(responses) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    assert report.status == "complete"
    assert report.stop_reason == "converged"
    assert report.root_cause == "converged after correction"


async def test_dispatch_two_invalid_outputs_is_fatal(tmp_path):
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = ["garbage one", "garbage two", _report_block("never reached")]

    async with _scripted_worker(responses) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    assert report.status == "error"
    assert report.stop_reason == "worker_error"
    assert "invalid output twice" in report.notes


# --------------------------------------------------------------------------
# worker HTTP error -> stop_reason=worker_error
# --------------------------------------------------------------------------


async def test_dispatch_worker_http_error(tmp_path):
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)

    def handler(_request):
        return httpx.Response(500, text="boom")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await dispatch("diagnose", spec, settings=settings, client=client)

    assert report.status == "error"
    assert report.stop_reason == "worker_error"


# --------------------------------------------------------------------------
# unknown pattern name -> explicit failure (DEC-008 §4, no fallback)
# --------------------------------------------------------------------------


async def test_dispatch_unknown_pattern_raises(tmp_path):
    settings = _make_settings()
    spec = _spec(tmp_path)
    with pytest.raises(KeyError):
        await dispatch("definitely-not-a-pattern", spec, settings=settings)


# --------------------------------------------------------------------------
# operator text blacklist scrub (defense in depth)
# --------------------------------------------------------------------------


async def test_dispatch_rejects_blacklisted_operator_text(tmp_path):
    settings = _make_settings()
    # The goal text itself contains a fake GitHub token shape (matches \bghp_…).
    bad_goal = "diagnose ghp_" + "A1b2C3d4E5" * 4
    spec = DiagnoseSpec(goal=bad_goal, context="", workdir=tmp_path)
    with pytest.raises(PatternRejected):
        await dispatch("diagnose", spec, settings=settings)


# --------------------------------------------------------------------------
# DEC-022 — per-command timeout policy is consulted per-pattern by the engine
# --------------------------------------------------------------------------


def _install_dummy_pattern(name: str, *, on_timeout):
    """Register an ad-hoc pattern that returns scripted Steps and a chosen policy."""

    class _Dummy:
        def __init__(self):
            self.name = name
            self.spec_model = DiagnoseSpec
            self.build_calls: list[dict] = []

        def system_prompt(self, spec):
            return "dummy system"

        def initial_user_message(self, spec):
            return "dummy intro"

        def operator_text(self, spec):
            return spec.goal

        def parse(self, worker_text):
            # First reply -> a CMD; second reply -> a report.
            if "ACTION: report" in worker_text:
                return patterns_base.Step(
                    kind="final",
                    think="done",
                    payload={
                        "root_cause": "ok",
                        "evidence": [],
                        "temporary_fix": None,
                        "permanent_fix": None,
                    },
                )
            return patterns_base.Step(kind="command", think="try", cmd="sleep 99")

        def build_report(self, **kwargs):
            self.build_calls.append(kwargs)
            return DiagnoseReport(
                status=kwargs["status"],
                stop_reason=kwargs["stop_reason"],
                iterations_used=kwargs["iterations_used"],
                commands_executed=kwargs["commands_executed"],
                notes=kwargs["notes"][:1024],
            )

    instance = _Dummy()
    if on_timeout is not None:
        instance.on_command_timeout = on_timeout  # type: ignore[attr-defined]
    patterns_base._REGISTRY[name] = instance
    return instance


@pytest.fixture
def _registry_isolation():
    snapshot = dict(patterns_base._REGISTRY)
    yield
    patterns_base._REGISTRY.clear()
    patterns_base._REGISTRY.update(snapshot)


async def test_dispatch_timeout_recover_continues_loop(monkeypatch, tmp_path, _registry_isolation):
    """A pattern declaring `recover` keeps the loop going on per-cmd timeout."""
    _install_dummy_pattern("dummy_recover", on_timeout=lambda cmd, step: "recover")
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [_shell_block("sleep 99"), _report_block("recovered")]

    calls = {"n": 0}

    async def fake_run(cmd, workdir, *, patterns, timeout_seconds, max_output_bytes, env=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise CommandTimeout(f"fake timeout for: {cmd}")
        return CommandResult(
            cmd=cmd, exit_code=0, stdout="", stderr="",
            stdout_truncated=False, stderr_truncated=False, duration_seconds=0.0,
        )

    monkeypatch.setattr(dispatcher_mod, "shell_run", fake_run)
    async with _scripted_worker(responses) as client:
        report = await dispatch("dummy_recover", spec, settings=settings, client=client)

    assert report.status == "complete"
    assert report.stop_reason == "converged"
    assert report.iterations_used == 2


async def test_dispatch_timeout_abort_returns_error(monkeypatch, tmp_path, _registry_isolation):
    """A pattern declaring `abort` short-circuits with stop_reason=command_timeout."""
    _install_dummy_pattern("dummy_abort", on_timeout=lambda cmd, step: "abort")
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [_shell_block("sleep 99"), _report_block("never reached")]

    async def fake_run(*_a, **_k):
        raise CommandTimeout("fake per-cmd timeout")

    monkeypatch.setattr(dispatcher_mod, "shell_run", fake_run)
    async with _scripted_worker(responses) as client:
        report = await dispatch("dummy_abort", spec, settings=settings, client=client)

    assert report.status == "error"
    assert report.stop_reason == "command_timeout"
    assert report.iterations_used == 1
    assert len(report.commands_executed) == 1
    assert report.commands_executed[0]["exit"] == -1
    assert "inconsistent" in report.notes.lower() or "abort" in report.notes.lower()


async def test_dispatch_timeout_default_is_abort(monkeypatch, tmp_path, _registry_isolation):
    """A pattern that does NOT declare on_command_timeout gets the safe default = abort.

    This is the DEC-022 invariant: silent recovery is impossible for a pattern
    that didn't think about it.
    """
    _install_dummy_pattern("dummy_silent", on_timeout=None)
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [_shell_block("sleep 99")]

    async def fake_run(*_a, **_k):
        raise CommandTimeout("fake per-cmd timeout")

    monkeypatch.setattr(dispatcher_mod, "shell_run", fake_run)
    async with _scripted_worker(responses) as client:
        report = await dispatch("dummy_silent", spec, settings=settings, client=client)

    assert report.status == "error"
    assert report.stop_reason == "command_timeout"


async def test_dispatch_timeout_buggy_hook_defaults_to_abort(monkeypatch, tmp_path, _registry_isolation):
    """If on_command_timeout raises, the engine falls back to abort (safe default)."""

    def boom(cmd, step):
        raise RuntimeError("buggy pattern")

    _install_dummy_pattern("dummy_buggy", on_timeout=boom)
    settings = _make_settings(max_iter=5, timeout=30)
    spec = _spec(tmp_path)
    responses = [_shell_block("sleep 99")]

    async def fake_run(*_a, **_k):
        raise CommandTimeout("fake per-cmd timeout")

    monkeypatch.setattr(dispatcher_mod, "shell_run", fake_run)
    async with _scripted_worker(responses) as client:
        report = await dispatch("dummy_buggy", spec, settings=settings, client=client)

    assert report.status == "error"
    assert report.stop_reason == "command_timeout"


# --------------------------------------------------------------------------
# Architectural sanity (DEC-021): dispatcher.py imports nothing pattern-specific
# --------------------------------------------------------------------------


def test_dispatcher_module_has_no_diagnose_imports():
    """The single-engine abstraction must not leak."""
    source = Path(dispatcher_mod.__file__).read_text(encoding="utf-8")
    # Substring scan is enough — these would only appear if we imported them.
    forbidden = ("DiagnoseReport", "DiagnoseSpec", "patterns.diagnose", "patterns import diagnose")
    for token in forbidden:
        assert token not in source, f"dispatcher.py leaks Diagnose specificity: {token!r}"


def test_dispatcher_module_has_no_execute_imports():
    """Same invariant for Execute (DEC-021 acceptance criterion)."""
    source = Path(dispatcher_mod.__file__).read_text(encoding="utf-8")
    forbidden = ("ExecuteReport", "ExecuteSpec", "patterns.execute", "patterns import execute")
    for token in forbidden:
        assert token not in source, f"dispatcher.py leaks Execute specificity: {token!r}"
