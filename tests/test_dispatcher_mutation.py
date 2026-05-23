"""Pre-loop mutation phase in the dispatcher (DEC-024, DEC-021 verdict).

These tests use *ad-hoc* patterns wired into the registry so they exercise the
engine's mutation orchestration without depending on the Patch/Create patterns
themselves — that is the DEC-021 proof: the engine consults ``mutate`` via
``getattr`` and stays unaware of which pattern uses it.
"""

from pathlib import Path

import httpx
import pytest

from optimai import dispatcher as dispatcher_mod
from optimai.config import Settings
from optimai.dispatcher import dispatch
from optimai.patterns import base as patterns_base
from optimai.patterns.base import MutationResult, Step
from optimai.schemas.report import DiagnoseReport
from optimai.schemas.task_spec import DiagnoseSpec
from optimai.snapshot import Snapshot

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLACKLIST = REPO_ROOT / "config" / "blacklist.txt"


def _settings(*, max_iter: int = 5, timeout: int = 30) -> Settings:
    return Settings(
        OPTIMAI_MAX_ITERATIONS=max_iter,
        OPTIMAI_TIMEOUT_SECONDS=timeout,
        OPTIMAI_MAX_OUTPUT_BYTES=10240,
        OPTIMAI_BLACKLIST_FILE=DEFAULT_BLACKLIST,
    )


def _scripted_worker(responses: list[str]) -> httpx.AsyncClient:
    cursor = {"i": 0}

    def handler(_request):
        i = cursor["i"]
        cursor["i"] += 1
        if i >= len(responses):
            return httpx.Response(500, text=f"only {len(responses)} responses prepared")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": responses[i]}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _report_block(root_cause: str = "ok") -> str:
    return (
        "THINK: done\n"
        "ACTION: report\n"
        f"ROOT_CAUSE: {root_cause}\n"
        "EVIDENCE:\n- saw expected\n"
        "TEMPORARY_FIX: none\nPERMANENT_FIX: none\n"
    )


@pytest.fixture
def _registry_isolation():
    snapshot = dict(patterns_base._REGISTRY)
    yield
    patterns_base._REGISTRY.clear()
    patterns_base._REGISTRY.update(snapshot)


# --------------------------------------------------------------------------
# Ad-hoc mutating pattern — a thin echo of B/C but registered only for tests
# --------------------------------------------------------------------------


def _install_mutating_pattern(
    name: str,
    *,
    mutate_fn,
    enrich_fn=None,
    parse_fn=None,
):
    captured = {"messages_in_loop": []}

    class _M:
        def __init__(self):
            self.name = name
            self.spec_model = DiagnoseSpec
            self.tool_description = "ad-hoc mutating pattern"

        def system_prompt(self, spec):
            return "dummy system"

        def initial_user_message(self, spec):
            return f"GOAL:\n{spec.goal}"

        def operator_text(self, spec):
            return spec.goal

        def parse(self, worker_text):
            if parse_fn is not None:
                return parse_fn(worker_text)
            return Step(
                kind="final",
                think="done",
                payload={"root_cause": "ok", "evidence": [], "temporary_fix": None, "permanent_fix": None},
            )

        def build_report(self, **kwargs):
            captured["build_report_kwargs"] = kwargs
            return DiagnoseReport(
                status=kwargs["status"],
                stop_reason=kwargs["stop_reason"],
                iterations_used=kwargs["iterations_used"],
                commands_executed=kwargs["commands_executed"],
                notes=kwargs["notes"][:1024],
            )

        def on_command_timeout(self, cmd, step):
            return "abort"

        def mutate(self, spec, snap):
            return mutate_fn(spec, snap)

    if enrich_fn is not None:
        # attach as method only when defined to mirror the optional-hook contract
        def _enrich(self, report, outcome):
            return enrich_fn(report, outcome)
        _M.enrich_report = _enrich  # type: ignore[attr-defined]

    instance = _M()
    patterns_base._REGISTRY[name] = instance
    return instance, captured


# --------------------------------------------------------------------------
# Success path: mutate runs, snapshot cleaned up, loop sees diff, enrich runs
# --------------------------------------------------------------------------


async def test_mutate_then_loop_sees_diff(_registry_isolation, tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("before\n", encoding="utf-8")

    def mut(spec, snap: Snapshot):
        snap.protect(f)
        f.write_text("after\n", encoding="utf-8")
        return MutationResult(files_changed=[f], diff="--- a/f.txt\n+++ b/f.txt\n-before\n+after\n")

    captured_diff = {"seen": False}

    def parse_fn(text):
        if "MUTATION APPLIED" in text:
            # never directly invoked — the engine puts the diff into a user
            # message, not into the worker's reply; parse only sees the reply.
            captured_diff["seen"] = True
        return Step(
            kind="final",
            think="done",
            payload={"root_cause": "ok", "evidence": [], "temporary_fix": None, "permanent_fix": None},
        )

    _install_mutating_pattern("mut_ok", mutate_fn=mut, parse_fn=parse_fn)

    async with _scripted_worker([_report_block("validated")]) as client:
        report = await dispatch("mut_ok", DiagnoseSpec(goal="run the mutation", workdir=tmp_path), settings=_settings(), client=client)

    assert report.status == "complete"
    assert report.stop_reason == "converged"
    # The file stays MUTATED — success path does cleanup, not restore.
    assert f.read_text(encoding="utf-8") == "after\n"


async def test_mutate_diff_appears_in_worker_user_turn(_registry_isolation, tmp_path):
    """The engine injects a MUTATION APPLIED user turn after initial_user_message."""
    f = tmp_path / "f.txt"
    f.write_text("before", encoding="utf-8")

    sentinel_diff = "DIFF_SENTINEL_XYZ"

    def mut(spec, snap):
        snap.protect(f)
        f.write_text("after", encoding="utf-8")
        return MutationResult(files_changed=[f], diff=sentinel_diff)

    _install_mutating_pattern("mut_sentinel", mutate_fn=mut)

    captured = {"posts": []}

    def handler(request):
        captured["posts"].append(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": _report_block()}, "finish_reason": "stop"}], "usage": {}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await dispatch("mut_sentinel", DiagnoseSpec(goal="run the mutation", workdir=tmp_path), settings=_settings(), client=client)

    assert any(sentinel_diff in body for body in captured["posts"]), "diff not relayed to worker"
    assert any("MUTATION APPLIED" in body for body in captured["posts"])


async def test_mutate_failure_restores_and_skips_loop(_registry_isolation, tmp_path):
    """An exception in mutate → snapshot restored, no worker call, mutation_error report."""
    f = tmp_path / "f.txt"
    f.write_text("original\n", encoding="utf-8")

    def mut(spec, snap: Snapshot):
        snap.protect(f)
        f.write_text("damaged\n", encoding="utf-8")  # done, then we explode
        raise ValueError("simulated mutation failure")

    _install_mutating_pattern("mut_boom", mutate_fn=mut)

    worker_called = {"n": 0}

    def handler(_request):
        worker_called["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": _report_block()}, "finish_reason": "stop"}], "usage": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await dispatch("mut_boom", DiagnoseSpec(goal="run the mutation", workdir=tmp_path), settings=_settings(), client=client)

    assert report.status == "error"
    assert report.stop_reason == "mutation_error"
    assert "simulated mutation failure" in report.notes
    # The file was restored byte-for-byte.
    assert f.read_text(encoding="utf-8") == "original\n"
    # The worker was never consulted — the loop did not run.
    assert worker_called["n"] == 0


async def test_validation_error_restores_snapshot(_registry_isolation, tmp_path):
    """A successful mutation followed by an error in the loop must roll the
    files back (atomicity intra-appel, DEC-024)."""
    f = tmp_path / "f.txt"
    f.write_text("original\n", encoding="utf-8")

    def mut(spec, snap):
        snap.protect(f)
        f.write_text("mutated\n", encoding="utf-8")
        return MutationResult(files_changed=[f], diff="diff body")

    def parse_fn(_text):
        return Step(kind="invalid", reason="forced error")

    _install_mutating_pattern("mut_then_err", mutate_fn=mut, parse_fn=parse_fn)

    # Two invalid replies → status=error (worker_error stop_reason)
    async with _scripted_worker(["garbage 1", "garbage 2", _report_block()]) as client:
        report = await dispatch("mut_then_err", DiagnoseSpec(goal="run the mutation", workdir=tmp_path), settings=_settings(), client=client)

    assert report.status == "error"
    # Files restored even though mutation itself succeeded.
    assert f.read_text(encoding="utf-8") == "original\n"


async def test_enrich_report_called_on_success(_registry_isolation, tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")

    def mut(spec, snap):
        snap.protect(f)
        f.write_text("y", encoding="utf-8")
        return MutationResult(files_changed=[f], diff="some diff")

    captured = {"outcome": None}

    def enrich(report, outcome):
        captured["outcome"] = outcome
        # Tag the notes so we can prove enrichment happened.
        return report.model_copy(update={"notes": "ENRICHED"})

    _install_mutating_pattern("mut_enrich", mutate_fn=mut, enrich_fn=enrich)

    async with _scripted_worker([_report_block()]) as client:
        report = await dispatch("mut_enrich", DiagnoseSpec(goal="run the mutation", workdir=tmp_path), settings=_settings(), client=client)

    assert isinstance(captured["outcome"], MutationResult)
    assert report.notes == "ENRICHED"


async def test_enrich_report_called_on_mutation_error(_registry_isolation, tmp_path):
    """When mutate raises, enrich_report still runs — with the exception."""
    f = tmp_path / "f.txt"
    f.write_text("orig", encoding="utf-8")

    def mut(spec, snap):
        snap.protect(f)
        raise RuntimeError("rejected by mutator")

    captured = {"outcome": None}

    def enrich(report, outcome):
        captured["outcome"] = outcome
        return report.model_copy(update={"notes": "ENRICHED_AFTER_ERROR"})

    _install_mutating_pattern("mut_err_enrich", mutate_fn=mut, enrich_fn=enrich)

    async with _scripted_worker([_report_block()]) as client:
        report = await dispatch("mut_err_enrich", DiagnoseSpec(goal="run the mutation", workdir=tmp_path), settings=_settings(), client=client)

    assert isinstance(captured["outcome"], Exception)
    assert "rejected by mutator" in str(captured["outcome"])
    assert report.notes == "ENRICHED_AFTER_ERROR"


# --------------------------------------------------------------------------
# Backward compatibility: A/D (no mutate hook) must behave exactly as before
# --------------------------------------------------------------------------


async def test_non_mutating_pattern_skips_mutation_phase(tmp_path):
    """Diagnose has no ``mutate`` method → the engine takes the legacy path."""
    spec = DiagnoseSpec(goal="investigate something benign", workdir=tmp_path)
    async with _scripted_worker([_report_block("toolchain ok")]) as client:
        report = await dispatch("diagnose", spec, settings=_settings(), client=client)
    assert report.status == "complete"
    assert report.stop_reason == "converged"


def test_dispatcher_has_no_patch_imports():
    """DEC-021 guard: the engine must not import Patch by name."""
    source = Path(dispatcher_mod.__file__).read_text(encoding="utf-8")
    forbidden = ("PatchReport", "PatchSpec", "patterns.patch", "patterns import patch", "FileEdit")
    for token in forbidden:
        assert token not in source, f"dispatcher.py leaks Patch specificity: {token!r}"


def test_dispatcher_has_no_create_imports():
    """DEC-021 guard: the engine must not import Create by name."""
    source = Path(dispatcher_mod.__file__).read_text(encoding="utf-8")
    forbidden = ("CreateReport", "CreateSpec", "patterns.create", "patterns import create", "NewFile")
    for token in forbidden:
        assert token not in source, f"dispatcher.py leaks Create specificity: {token!r}"
