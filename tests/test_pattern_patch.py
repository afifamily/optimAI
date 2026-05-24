"""Tests for optimai.patterns.patch — strategy B (DEC-006, DEC-024)."""

from pathlib import Path

import pytest

from optimai.patterns.base import MutationResult, Step
from optimai.patterns.patch import SYSTEM_PROMPT, PatchPattern
from optimai.schemas.report import PatchReport
from optimai.schemas.task_spec import FileEdit, PatchSpec
from optimai.snapshot import Snapshot


@pytest.fixture
def pattern():
    return PatchPattern()


@pytest.fixture
def workdir(tmp_path):
    return tmp_path


@pytest.fixture
def target(workdir):
    f = workdir / "hello.py"
    f.write_text("print('hello')\n", encoding="utf-8")
    return f


# --------------------------------------------------------------------------
# mutate: success, no-match, multi-match, multi-edit on same file
# --------------------------------------------------------------------------


def test_mutate_applies_exact_one_match(pattern, workdir, target):
    spec = PatchSpec(
        goal="rename hello to world",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
    )
    snap = Snapshot(workdir)
    try:
        result = pattern.mutate(spec, snap)
        assert isinstance(result, MutationResult)
        assert target.read_text(encoding="utf-8") == "print('world')\n"
        assert target in result.files_changed
        assert "world" in result.diff
        assert "hello" in result.diff
    finally:
        snap.cleanup()


def test_mutate_no_match_raises_and_rolls_back(pattern, workdir, target):
    spec = PatchSpec(
        goal="rename absent string",
        workdir=workdir,
        edits=[FileEdit(path=target, old="not-in-file", new="x")],
    )
    snap = Snapshot(workdir)
    try:
        with pytest.raises(ValueError, match="not found"):
            pattern.mutate(spec, snap)
        snap.restore()
    finally:
        # Either restore (above) or cleanup — both safe.
        pass
    # The file is untouched (we never wrote anything before raising).
    assert target.read_text(encoding="utf-8") == "print('hello')\n"


def test_mutate_multi_match_raises(pattern, workdir):
    f = workdir / "repeat.txt"
    f.write_text("foo\nfoo\n", encoding="utf-8")
    spec = PatchSpec(
        goal="rename foo",
        workdir=workdir,
        edits=[FileEdit(path=f, old="foo", new="bar")],
    )
    snap = Snapshot(workdir)
    try:
        with pytest.raises(ValueError, match="matched 2 times"):
            pattern.mutate(spec, snap)
        snap.restore()
    finally:
        pass
    assert f.read_text(encoding="utf-8") == "foo\nfoo\n"


def test_mutate_multiple_edits_same_file_apply_in_order(pattern, workdir):
    f = workdir / "code.py"
    f.write_text("alpha beta gamma\n", encoding="utf-8")
    spec = PatchSpec(
        goal="rename alpha and beta",
        workdir=workdir,
        edits=[
            FileEdit(path=f, old="alpha", new="ALPHA"),
            FileEdit(path=f, old="beta", new="BETA"),
        ],
    )
    snap = Snapshot(workdir)
    try:
        result = pattern.mutate(spec, snap)
        assert f.read_text(encoding="utf-8") == "ALPHA BETA gamma\n"
        # One file changed, even with two edits.
        assert result.files_changed == [f]
    finally:
        snap.cleanup()


def test_mutate_missing_file_raises(pattern, workdir):
    spec = PatchSpec(
        goal="patch ghost",
        workdir=workdir,
        edits=[FileEdit(path=workdir / "ghost.py", old="x", new="y")],
    )
    snap = Snapshot(workdir)
    try:
        with pytest.raises(FileNotFoundError):
            pattern.mutate(spec, snap)
        snap.restore()
    finally:
        pass


# --------------------------------------------------------------------------
# parse: command / final / invalid
# --------------------------------------------------------------------------


def test_parse_shell_command(pattern):
    step = pattern.parse("THINK: validate\nACTION: shell\nCMD: pytest")
    assert step.kind == "command"
    assert step.cmd == "pytest"


def test_parse_report(pattern):
    text = (
        "THINK: done\n"
        "ACTION: report\n"
        "SUMMARY: tests pass, patch validated\n"
        "FAILED_EDIT: none\n"
    )
    step = pattern.parse(text)
    assert step.kind == "final"
    assert step.payload["summary"] == "tests pass, patch validated"
    assert step.payload["failed_edit"] is None


def test_parse_report_with_failed_edit(pattern):
    text = (
        "THINK: build broke\n"
        "ACTION: report\n"
        "SUMMARY: swiftc -parse failed at line 42\n"
        "FAILED_EDIT: Sources/Foo.swift: introduced a syntax error\n"
    )
    step = pattern.parse(text)
    assert step.kind == "final"
    assert "Foo.swift" in step.payload["failed_edit"]


def test_parse_garbage_is_invalid(pattern):
    assert pattern.parse("nope").kind == "invalid"


# --------------------------------------------------------------------------
# build_report and enrich_report
# --------------------------------------------------------------------------


def test_build_report_complete(pattern, workdir, target):
    payload = {"summary": "validated", "failed_edit": None}
    report = pattern.build_report(
        final_payload=payload,
        commands_executed=[{"cmd": "pytest", "exit": 0, "stdout_truncated": False}],
        stop_reason="converged",
        iterations_used=2,
        status="complete",
        notes="ok",
    )
    assert isinstance(report, PatchReport)
    assert report.status == "complete"
    assert report.summary == "validated"
    # diff / files_changed are populated by enrich_report, not build_report.
    assert report.diff is None
    assert report.files_changed == []

    # Now enrich with a fake MutationResult and verify it's stamped.
    enriched = pattern.enrich_report(
        report, MutationResult(files_changed=[target], diff="DIFF_BODY")
    )
    assert enriched.diff == "DIFF_BODY"
    assert enriched.files_changed == [str(target)]


def test_build_report_mutation_error_then_enrich_with_exception(pattern):
    """The dispatcher's mutation-error path: build error report, then enrich
    with the original exception so ``failed_edit`` is populated."""
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="mutation_error",
        iterations_used=0,
        status="error",
        notes="mutation error: oh no",
    )
    enriched = pattern.enrich_report(report, ValueError("hello.py: 'old' not found"))
    assert enriched.status == "error"
    assert enriched.stop_reason == "mutation_error"
    assert "not found" in enriched.failed_edit


# --------------------------------------------------------------------------
# Contract surface: protocol pieces + DEC-021 (no domain) + DEC-022 (abort)
# --------------------------------------------------------------------------


def test_on_command_timeout_is_abort(pattern):
    decision = pattern.on_command_timeout("pytest", Step(kind="command", cmd="pytest"))
    assert decision == "abort"


def test_system_prompt_carries_no_domain_knowledge(pattern, workdir, target):
    prompt = pattern.system_prompt(PatchSpec(goal="rename", workdir=workdir, edits=[FileEdit(path=target, old="hello", new="world")]))
    assert prompt == SYSTEM_PROMPT
    forbidden = ("xcode-select", "XCTest", "homebrew", "brew install", "Xcode.app")
    for token in forbidden:
        assert token not in prompt


def test_operator_text_covers_goal_paths_and_new_strings(pattern, workdir, target):
    spec = PatchSpec(
        goal="rename hello to world",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="WORLD_NEW_TOKEN")],
        validation_command="echo VALIDATE_TOKEN",
    )
    text = pattern.operator_text(spec)
    assert spec.goal in text
    assert str(target) in text
    assert "WORLD_NEW_TOKEN" in text
    assert "VALIDATE_TOKEN" in text


def test_patch_pattern_registered():
    from optimai.patterns.base import available_patterns, get_pattern
    assert "patch" in available_patterns()
    inst = get_pattern("patch")
    assert isinstance(inst, PatchPattern)


def test_patch_pattern_spec_model(pattern):
    assert pattern.spec_model is PatchSpec


def test_patch_module_does_not_import_create():
    """Cross-pattern hygiene: patterns are independent strategies."""
    src = (Path(__file__).resolve().parents[1] / "src" / "optimai" / "patterns" / "patch.py").read_text()
    assert "patterns.create" not in src
    assert "from optimai.patterns import create" not in src


# --------------------------------------------------------------------------
# DEC-024 amended — status-of-failure hooks
# --------------------------------------------------------------------------


def test_is_validation_command_matches_designated_cmd(pattern, workdir, target):
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="python -m py_compile hello.py",
    )
    assert pattern.is_validation_command("python -m py_compile hello.py", spec) is True
    # Whitespace tolerant.
    assert pattern.is_validation_command("  python -m py_compile hello.py  ", spec) is True


def test_is_validation_command_rejects_diagnostics(pattern, workdir, target):
    """A read-only diagnostic the worker may run between the patch and the
    report is NOT the validation cmd — protects the worker's right to peek."""
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="python -m py_compile hello.py",
    )
    for diagnostic in ("cat hello.py", "head -n 5 hello.py", "which python", "grep hello hello.py"):
        assert pattern.is_validation_command(diagnostic, spec) is False


def test_is_validation_command_returns_false_when_no_validation_declared(pattern, workdir, target):
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command=None,
    )
    assert pattern.is_validation_command("anything at all", spec) is False


def test_worker_declares_failure_flags_named_edit(pattern):
    assert pattern.worker_declares_failure({"summary": "broke", "failed_edit": "x: syntax"}) is True
    assert pattern.worker_declares_failure({"summary": "ok", "failed_edit": None}) is False
    assert pattern.worker_declares_failure({}) is False


def test_build_report_preserves_worker_verdict_on_error_status(pattern):
    """DEC-024 amended: when the engine downgrades a converged report to
    status='error', build_report must still surface SUMMARY + FAILED_EDIT so
    the Cortex sees the worker's verdict."""
    payload = {"summary": "py_compile failed at line 3", "failed_edit": "hello.py: syntax break"}
    report = pattern.build_report(
        final_payload=payload,
        commands_executed=[
            {"cmd": "python -m py_compile hello.py", "exit": 1, "stdout_truncated": False}
        ],
        stop_reason="converged",
        iterations_used=2,
        status="error",
        notes="validation command failed (deterministic guard)",
    )
    assert report.status == "error"
    assert report.summary == "py_compile failed at line 3"
    assert report.failed_edit == "hello.py: syntax break"


# --------------------------------------------------------------------------
# DEC-024 piste B — absent validation tool: skipped deterministically
# --------------------------------------------------------------------------


def test_is_validation_command_false_when_tool_absent(pattern, workdir, target, monkeypatch):
    """Layer 1 must NOT fire on the canonical validation command when the
    tool itself is missing from PATH — even on an exact-string match (defense
    in depth, in case the worker runs it despite the user-message skip)."""
    monkeypatch.setattr("optimai.patterns.patch.shutil.which", lambda name: None)
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="pytest tests/",
    )
    assert pattern.is_validation_command("pytest tests/", spec) is False


def test_is_validation_command_true_when_tool_on_path(pattern, workdir, target, monkeypatch):
    monkeypatch.setattr("optimai.patterns.patch.shutil.which", lambda name: "/usr/bin/" + name)
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="pytest tests/",
    )
    assert pattern.is_validation_command("pytest tests/", spec) is True


def test_initial_user_message_marks_skipped_when_tool_absent(pattern, workdir, target, monkeypatch):
    monkeypatch.setattr("optimai.patterns.patch.shutil.which", lambda name: None)
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="pytest tests/",
    )
    msg = pattern.initial_user_message(spec)
    assert "(skipped — pytest not on PATH" in msg
    assert "pytest tests/" not in msg


def test_initial_user_message_keeps_validation_when_tool_present(pattern, workdir, target, monkeypatch):
    monkeypatch.setattr("optimai.patterns.patch.shutil.which", lambda name: "/usr/bin/" + name)
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="pytest tests/",
    )
    msg = pattern.initial_user_message(spec)
    assert "VALIDATION COMMAND:\npytest tests/" in msg


def test_mutate_records_skip_when_tool_absent(pattern, workdir, target, monkeypatch):
    monkeypatch.setattr("optimai.patterns.patch.shutil.which", lambda name: None)
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="pytest tests/",
    )
    snap = Snapshot(workdir)
    try:
        result = pattern.mutate(spec, snap)
        # File mutated normally — the missing tool only affects validation.
        assert target.read_text(encoding="utf-8") == "print('world')\n"
        assert any("pytest" in note and "not on PATH" in note for note in result.skipped_validations)
    finally:
        snap.cleanup()


def test_mutate_no_skip_when_validation_command_absent(pattern, workdir, target):
    """When there is no validation_command, we don't probe — and there's
    nothing to skip either."""
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command=None,
    )
    snap = Snapshot(workdir)
    try:
        result = pattern.mutate(spec, snap)
        assert result.skipped_validations == []
    finally:
        snap.cleanup()


def test_mutate_no_skip_when_tool_present(pattern, workdir, target, monkeypatch):
    monkeypatch.setattr("optimai.patterns.patch.shutil.which", lambda name: "/usr/bin/" + name)
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="pytest tests/",
    )
    snap = Snapshot(workdir)
    try:
        result = pattern.mutate(spec, snap)
        assert result.skipped_validations == []
    finally:
        snap.cleanup()


def test_enrich_report_surfaces_skip_notes(pattern, workdir, target):
    report = pattern.build_report(
        final_payload={"summary": "patched", "failed_edit": None},
        commands_executed=[],
        stop_reason="converged",
        iterations_used=1,
        status="complete",
        notes="worker note",
    )
    enriched = pattern.enrich_report(
        report,
        MutationResult(
            files_changed=[target],
            diff="DIFF",
            skipped_validations=["pytest: not on PATH (validation skipped)"],
        ),
    )
    assert "worker note" in enriched.notes
    assert "Skipped validations:" in enriched.notes
    assert "pytest" in enriched.notes


def test_invariant_layer1_still_fires_when_tool_present(pattern, workdir, target, monkeypatch):
    """Invariant #8 (CLI #8 / amendment): when the tool IS present and the
    validation cmd really exits non-zero (real failure), Layer 1 must still
    flag it as a validation command — we did not weaken the guard, only
    excluded the missing-tool case."""
    monkeypatch.setattr("optimai.patterns.patch.shutil.which", lambda name: "/usr/bin/" + name)
    spec = PatchSpec(
        goal="rename hello",
        workdir=workdir,
        edits=[FileEdit(path=target, old="hello", new="world")],
        validation_command="python -m py_compile broken.py",
    )
    assert pattern.is_validation_command("python -m py_compile broken.py", spec) is True


# --------------------------------------------------------------------------
# _validation_tool helper — first-token extraction, env-var prefix off
# --------------------------------------------------------------------------


def test_validation_tool_extracts_first_token():
    from optimai.patterns.patch import _validation_tool

    assert _validation_tool("pytest tests/") == "pytest"
    assert _validation_tool("python -m py_compile x.py") == "python"
    assert _validation_tool("swiftc -parse Foo.swift") == "swiftc"


def test_validation_tool_skips_env_var_assignment():
    """`VAR=val pytest ...` — first token is an assignment, we can't reliably
    probe → return None so degradation stays OFF (Layer 1 stays active)."""
    from optimai.patterns.patch import _validation_tool

    assert _validation_tool("DEBUG=1 pytest tests/") is None


def test_validation_tool_returns_none_on_unparsable_or_empty():
    from optimai.patterns.patch import _validation_tool

    assert _validation_tool(None) is None
    assert _validation_tool("") is None
    # Unbalanced quote: shlex.split raises, we swallow → None.
    assert _validation_tool("pytest 'unterminated") is None
