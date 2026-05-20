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
# Architectural sanity (DEC-021): dispatcher.py imports nothing Diagnose-specific
# --------------------------------------------------------------------------


def test_dispatcher_module_has_no_diagnose_imports():
    """The single-engine abstraction must not leak."""
    source = Path(dispatcher_mod.__file__).read_text(encoding="utf-8")
    # Substring scan is enough — these would only appear if we imported them.
    forbidden = ("DiagnoseReport", "DiagnoseSpec", "patterns.diagnose", "patterns import diagnose")
    for token in forbidden:
        assert token not in source, f"dispatcher.py leaks Diagnose specificity: {token!r}"
