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


# --------------------------------------------------------------------------
# DEC-024 amended — status-of-failure cascade in the engine
# --------------------------------------------------------------------------


def _install_validation_aware_pattern(
    name: str,
    *,
    is_validation,
    worker_declares=None,
    mutate_fn=None,
):
    """Register an ad-hoc pattern that opts into the new DEC-024 hooks.

    Mirrors `_install_mutating_pattern` but exposes the two new hooks the
    engine consults via getattr. Mutation is optional so the cascade can be
    tested on a read-only-shaped pattern too.
    """

    class _V:
        def __init__(self):
            self.name = name
            self.spec_model = DiagnoseSpec
            self.tool_description = "ad-hoc validation-aware pattern"

        def system_prompt(self, spec):
            return "dummy system"

        def initial_user_message(self, spec):
            return f"GOAL:\n{spec.goal}"

        def operator_text(self, spec):
            return spec.goal

        def parse(self, worker_text):
            if "ACTION: report" in worker_text:
                return Step(
                    kind="final",
                    think="worker says ok",
                    payload={
                        "root_cause": "ok",
                        "evidence": [],
                        "temporary_fix": None,
                        "permanent_fix": None,
                        # Surface a flag so worker_declares_failure can see it.
                        "fail_flag": "TESTFLAG" in worker_text,
                    },
                )
            # Each shell block emits its CMD verbatim.
            for line in worker_text.splitlines():
                if line.startswith("CMD:"):
                    return Step(kind="command", think="try", cmd=line[4:].strip())
            return Step(kind="invalid", reason="no CMD")

        def build_report(self, **kwargs):
            return DiagnoseReport(
                status=kwargs["status"],
                stop_reason=kwargs["stop_reason"],
                iterations_used=kwargs["iterations_used"],
                commands_executed=kwargs["commands_executed"],
                notes=kwargs["notes"][:1024],
            )

        def on_command_timeout(self, cmd, step):
            return "abort"

    _V.is_validation_command = lambda self, cmd, spec: is_validation(cmd, spec)
    if worker_declares is not None:
        _V.worker_declares_failure = lambda self, payload: worker_declares(payload)
    if mutate_fn is not None:
        _V.mutate = lambda self, spec, snap: mutate_fn(spec, snap)

    instance = _V()
    patterns_base._REGISTRY[name] = instance
    return instance


# A simple commenting trick: `false # VAL` and `false # DIAG` both produce a
# real shell exit (1) but carry an inline marker the lambdas can match on.
_VAL_MARK = "# VAL"
_DIAG_MARK = "# DIAG"


def _is_validation_by_marker(cmd, spec):
    return _VAL_MARK in cmd


async def test_validation_exit_nonzero_forces_error(_registry_isolation, tmp_path):
    """Layer 1 — a designated validation cmd exiting non-zero overrides
    the worker's converged 'complete' report (the very bug DEC-024 amended fixes)."""
    _install_validation_aware_pattern("val_aware", is_validation=_is_validation_by_marker)

    # Worker runs the validation cmd (`false` exits 1, the comment is just
    # a marker the lambda matches on), then converges. Pre-fix, status would be "complete".
    responses = [
        f"THINK: validate\nACTION: shell\nCMD: false {_VAL_MARK}\n",
        _report_block("worker thinks all good"),
    ]
    async with _scripted_worker(responses) as client:
        report = await dispatch(
            "val_aware",
            DiagnoseSpec(goal="run the validation against a failing cmd", workdir=tmp_path),
            settings=_settings(),
            client=client,
        )

    assert report.status == "error", (
        "deterministic guard did not override worker convergence"
    )
    assert report.stop_reason == "converged"  # worker DID converge — only status was downgraded
    assert "validation command failed" in report.notes
    assert "deterministic guard" in report.notes


async def test_non_validation_exit_nonzero_stays_complete(_registry_isolation, tmp_path):
    """Layer 1 must NOT fire on diagnostic read-only commands the worker
    interleaves (`grep` finding nothing → exit 1 → don't rollback)."""
    _install_validation_aware_pattern("val_aware_diag", is_validation=_is_validation_by_marker)

    # Worker runs a diagnostic (`false # DIAG` exits 1 but is NOT marked as
    # validation), then converges. status must stay "complete".
    responses = [
        f"THINK: peek\nACTION: shell\nCMD: false {_DIAG_MARK}\n",
        _report_block("nothing wrong with the actual artifact"),
    ]
    async with _scripted_worker(responses) as client:
        report = await dispatch(
            "val_aware_diag",
            DiagnoseSpec(goal="diagnose without firing the guard", workdir=tmp_path),
            settings=_settings(),
            client=client,
        )

    assert report.status == "complete"
    assert report.stop_reason == "converged"


async def test_worker_declares_failure_on_exit_zero(_registry_isolation, tmp_path):
    """Layer 2 — the worker can downgrade complete to error on exit 0 by
    setting a semantic-failure flag in the payload."""
    _install_validation_aware_pattern(
        "val_aware_layer2",
        is_validation=_is_validation_by_marker,
        worker_declares=lambda payload: bool(payload.get("fail_flag")),
    )

    # Validation cmd succeeds (exit 0), but the worker's report carries
    # the TESTFLAG marker — parse() puts fail_flag=True in payload.
    responses = [
        f"THINK: validate\nACTION: shell\nCMD: true {_VAL_MARK}\n",
        "THINK: TESTFLAG\nACTION: report\nROOT_CAUSE: tests passed by skipping\n"
        "EVIDENCE:\n- 0 tests collected\nTEMPORARY_FIX: none\nPERMANENT_FIX: none\n",
    ]
    async with _scripted_worker(responses) as client:
        report = await dispatch(
            "val_aware_layer2",
            DiagnoseSpec(goal="exercise layer 2", workdir=tmp_path),
            settings=_settings(),
            client=client,
        )

    assert report.status == "error"
    assert "worker declared semantic failure" in report.notes


async def test_layer1_prime_over_layer2_invariant(_registry_isolation, tmp_path):
    """The cascade order MUST enforce 'deterministic guard prime' — even
    when the worker payload would also have triggered Layer 2, the engine
    reports Layer 1's reason (the validation exit, not the worker flag)."""
    _install_validation_aware_pattern(
        "val_aware_both",
        is_validation=_is_validation_by_marker,
        worker_declares=lambda payload: bool(payload.get("fail_flag")),
    )

    responses = [
        f"THINK: validate\nACTION: shell\nCMD: false {_VAL_MARK}\n",
        "THINK: TESTFLAG\nACTION: report\nROOT_CAUSE: also bad\n"
        "EVIDENCE:\n- both\nTEMPORARY_FIX: none\nPERMANENT_FIX: none\n",
    ]
    async with _scripted_worker(responses) as client:
        report = await dispatch(
            "val_aware_both",
            DiagnoseSpec(goal="both layers say fail", workdir=tmp_path),
            settings=_settings(),
            client=client,
        )

    assert report.status == "error"
    # Layer 1 message wins — proves the cascade order.
    assert "deterministic guard" in report.notes
    assert "worker declared semantic failure" not in report.notes


async def test_layer1_triggers_snapshot_restore_on_mutating_pattern(
    _registry_isolation, tmp_path
):
    """End-to-end: mutation succeeds → loop runs the validation cmd (exit≠0)
    → engine downgrades to error → snapshot restores the file. This is the
    exact path the live B-rollback bug walks, exercised here with a mocked
    worker so the unit suite can guard the regression."""
    f = tmp_path / "broken.py"
    original = "def greet():\n    return 'hi'\n"
    f.write_text(original, encoding="utf-8")

    def mut(spec, snap: Snapshot):
        snap.protect(f)
        # Simulate a deterministic mutation that breaks the file.
        f.write_text("def greet()\n    return 'hi'\n", encoding="utf-8")
        return MutationResult(files_changed=[f], diff="--- a/broken.py\n+++ b/broken.py\n")

    _install_validation_aware_pattern(
        "val_aware_mut",
        is_validation=_is_validation_by_marker,
        mutate_fn=mut,
    )

    responses = [
        f"THINK: validate the mutation\nACTION: shell\nCMD: false {_VAL_MARK}\n",
        _report_block("compile failed, naming the cause"),
    ]
    async with _scripted_worker(responses) as client:
        report = await dispatch(
            "val_aware_mut",
            DiagnoseSpec(goal="mutate then watch the guard fire", workdir=tmp_path),
            settings=_settings(),
            client=client,
        )

    assert report.status == "error"
    # Atomicity intra-appel: file restored to its pre-mutation bytes (DEC-024).
    assert f.read_text(encoding="utf-8") == original


async def test_buggy_is_validation_hook_keeps_dispatch_alive(_registry_isolation, tmp_path):
    """A hook that raises must not crash the dispatch — engine logs and
    treats the entry as non-validation (preserves the worker's verdict)."""

    def boom(cmd, spec):
        raise RuntimeError("buggy pattern")

    _install_validation_aware_pattern("val_aware_buggy", is_validation=boom)

    responses = [
        f"THINK: try\nACTION: shell\nCMD: false {_DIAG_MARK}\n",
        _report_block("ok"),
    ]
    async with _scripted_worker(responses) as client:
        report = await dispatch(
            "val_aware_buggy",
            DiagnoseSpec(goal="exercise the buggy hook path", workdir=tmp_path),
            settings=_settings(),
            client=client,
        )

    # Hook raised on every entry → treated as no-validation → worker's
    # converged "complete" stands.
    assert report.status == "complete"


async def test_legacy_pattern_without_hooks_keeps_complete(tmp_path):
    """A/D regression — diagnose has neither hook → the cascade is silently
    inert and the legacy converged-⇒-complete behavior is preserved."""
    spec = DiagnoseSpec(goal="legacy converge path stays complete", workdir=tmp_path)
    async with _scripted_worker([_report_block("legacy ok")]) as client:
        report = await dispatch("diagnose", spec, settings=_settings(), client=client)
    assert report.status == "complete"
    assert report.stop_reason == "converged"


# --------------------------------------------------------------------------
# DEC-024 piste B — end-to-end: absent validation tool degrades cleanly
# --------------------------------------------------------------------------


def _create_report_block(summary: str = "files written", failed_file: str = "none") -> str:
    return (
        "THINK: validated\n"
        "ACTION: report\n"
        f"SUMMARY: {summary}\n"
        f"FAILED_FILE: {failed_file}\n"
    )


async def test_absent_validation_tool_does_not_trigger_rollback(tmp_path, monkeypatch):
    """End-to-end: Create with a missing toolchain (mocked shutil.which→None)
    must finish 'complete', the file must survive, and the report must mention
    the skip — exactly the bug from DEC-024 §Précision."""
    from optimai.schemas.task_spec import CreateSpec, NewFile

    monkeypatch.setattr("optimai.patterns.create.shutil.which", lambda name: None)

    target = tmp_path / "Foo.swift"
    spec = CreateSpec(
        goal="create a swift source on a machine without swiftc",
        workdir=tmp_path,
        files=[NewFile(path=target, content="struct Foo {}\n", language="swift")],
    )

    async with _scripted_worker([_create_report_block("file written; validation skipped")]) as client:
        report = await dispatch("create", spec, settings=_settings(), client=client)

    assert report.status == "complete"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "struct Foo {}\n"
    assert "Skipped validations" in report.notes
    assert "swiftc" in report.notes


async def test_present_tool_with_invalid_file_still_rolls_back(tmp_path, monkeypatch):
    """Invariant #8 / DEC-024 amendment must not regress: when the tool IS
    present and the validation cmd really exits non-zero, Layer 1 fires →
    status=error → snapshot restores the file."""
    from optimai.schemas.task_spec import CreateSpec, NewFile

    # Force shutil.which to claim swiftc is present so validation_command_for
    # returns a real command. The worker's mocked transcript will then 'run'
    # it via a scripted shell turn.
    monkeypatch.setattr("optimai.patterns.create.shutil.which", lambda name: "/usr/bin/" + name)

    target = tmp_path / "Bar.swift"
    spec = CreateSpec(
        goal="create a swift source that won't compile, tool present",
        workdir=tmp_path,
        files=[NewFile(path=target, content="garbage // not real swift\n", language="swift")],
    )

    # Worker runs the canonical 'swiftc -parse <path>' (we replay it via 'false'
    # in the test shell to get a real exit≠0 — Layer 1 needs the EXACT cmd
    # string matched by is_validation_command, so we use the same canonical
    # form the engine would expose).
    from optimai.patterns.create import validation_command_for
    val_cmd = validation_command_for("swift", target.resolve())
    assert val_cmd is not None  # mock made it visible

    # The shell will actually run `swiftc -parse …` — but swiftc may not be
    # installed on this machine. So we fake the worker by submitting a CMD
    # the shell can execute and which returns non-zero. We use `bash -c
    # "exit 1"` and tell the engine that THAT is the validation by wrapping
    # is_validation_command. Simpler: register an ad-hoc create-like pattern.
    #
    # The cleanest route: trust the real CreatePattern but stub the shell
    # exit via monkeypatching shell.run to fake the swiftc call.
    from optimai import shell as shell_mod
    real_run = shell_mod.run

    async def fake_run(cmd, *args, **kwargs):
        # Pretend swiftc parsed and failed.
        if cmd.strip() == val_cmd.strip():
            from optimai.shell import CommandResult
            return CommandResult(
                cmd=cmd,
                exit_code=1,
                stdout="error: garbage",
                stderr="",
                stdout_truncated=False,
                stderr_truncated=False,
                duration_seconds=0.0,
            )
        return await real_run(cmd, *args, **kwargs)

    monkeypatch.setattr("optimai.dispatcher.shell_run", fake_run)

    responses = [
        f"THINK: validate\nACTION: shell\nCMD: {val_cmd}\n",
        _create_report_block("would say all good but the file is broken", "Bar.swift: parse error"),
    ]
    async with _scripted_worker(responses) as client:
        report = await dispatch("create", spec, settings=_settings(), client=client)

    assert report.status == "error", (
        f"Layer 1 must still fire when tool is present and validation fails — got status={report.status}"
    )
    # Atomicity: file restored (i.e., does not exist anymore — it was created
    # by mutate, then the snapshot deleted it on rollback).
    assert not target.exists()
