"""Tests for optimai.patterns.create — strategy C (DEC-006, DEC-024)."""

import shlex
import subprocess
from pathlib import Path

import pytest

from optimai.patterns.base import MutationResult, Step
from optimai.patterns.create import (
    SYSTEM_PROMPT,
    CreatePattern,
    validation_command_for,
)
from optimai.schemas.report import CreateReport
from optimai.schemas.task_spec import CreateSpec, NewFile
from optimai.snapshot import Snapshot


@pytest.fixture
def pattern():
    return CreatePattern()


@pytest.fixture
def workdir(tmp_path):
    return tmp_path


# --------------------------------------------------------------------------
# mutate: success, existing-path refusal, rollback removes files + dirs
# --------------------------------------------------------------------------


def test_mutate_creates_simple_file(pattern, workdir):
    spec = CreateSpec(
        goal="create a sample python module",
        workdir=workdir,
        files=[NewFile(path=workdir / "sample.py", content="print('hi')\n", language="python")],
    )
    snap = Snapshot(workdir)
    try:
        result = pattern.mutate(spec, snap)
        assert (workdir / "sample.py").exists()
        assert (workdir / "sample.py").read_text(encoding="utf-8") == "print('hi')\n"
        assert isinstance(result, MutationResult)
        assert (workdir / "sample.py") in result.files_changed
    finally:
        snap.cleanup()


def test_mutate_creates_nested_directories(pattern, workdir):
    target = workdir / "deep" / "nest" / "file.py"
    spec = CreateSpec(
        goal="create nested file",
        workdir=workdir,
        files=[NewFile(path=target, content="x = 1\n", language="python")],
    )
    snap = Snapshot(workdir)
    try:
        pattern.mutate(spec, snap)
        assert target.exists()
    finally:
        snap.cleanup()


def test_mutate_refuses_existing_file_and_rolls_back(pattern, workdir):
    existing = workdir / "already.py"
    existing.write_text("old content\n", encoding="utf-8")

    other = workdir / "new.py"
    spec = CreateSpec(
        goal="create files including one that exists",
        workdir=workdir,
        files=[
            NewFile(path=other, content="new\n", language="python"),
            NewFile(path=existing, content="should-not-overwrite\n", language="python"),
        ],
    )
    snap = Snapshot(workdir)
    try:
        with pytest.raises(FileExistsError):
            pattern.mutate(spec, snap)
        snap.restore()
    finally:
        pass

    # The pre-existing file is untouched, AND the first file (created before
    # the second raised) was deleted by restore.
    assert existing.read_text(encoding="utf-8") == "old content\n"
    assert not other.exists()


def test_mutate_rollback_removes_created_directories(pattern, workdir):
    """Two nested creates, second one fails → both new files and any
    intermediate dirs we created are gone after restore."""
    a = workdir / "newdir" / "a.py"
    b = workdir / "already" / "b.py"
    (workdir / "already").mkdir()
    (workdir / "already" / "b.py").write_text("preexisting\n", encoding="utf-8")

    spec = CreateSpec(
        goal="create a then conflict on b",
        workdir=workdir,
        files=[
            NewFile(path=a, content="x = 1\n", language="python"),
            NewFile(path=b, content="bogus\n", language="python"),
        ],
    )
    snap = Snapshot(workdir)
    try:
        with pytest.raises(FileExistsError):
            pattern.mutate(spec, snap)
        snap.restore()
    finally:
        pass

    assert not a.exists()
    assert not (workdir / "newdir").exists()  # ancestor we created
    assert (workdir / "already" / "b.py").read_text(encoding="utf-8") == "preexisting\n"


# --------------------------------------------------------------------------
# validation_command_for — language dispatch + shell-quoting
# --------------------------------------------------------------------------


def test_validation_command_python():
    cmd = validation_command_for("python", Path("/tmp/x.py"))
    assert cmd == "python -m py_compile /tmp/x.py"


def test_validation_command_swift_quotes_paths_with_spaces():
    cmd = validation_command_for("swift", Path("/tmp/a b/c.swift"))
    assert "swiftc -parse " in cmd
    # shlex.quote wraps a path with a space in single quotes.
    assert shlex.quote("/tmp/a b/c.swift") in cmd


def test_validation_command_go():
    cmd = validation_command_for("go", Path("/tmp/x.go"))
    assert cmd == "gofmt -e /tmp/x.go"


def test_validation_command_none_returns_none():
    assert validation_command_for("none", Path("/tmp/x")) is None


def test_python_validation_actually_compiles_a_valid_file(workdir):
    """Sanity check: py_compile passes on a valid file and fails on invalid one."""
    good = workdir / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")
    cmd = validation_command_for("python", good)
    assert cmd is not None
    result = subprocess.run(cmd, shell=True, capture_output=True)
    assert result.returncode == 0


def test_python_validation_fails_on_syntax_error(workdir):
    bad = workdir / "bad.py"
    bad.write_text("def (\n", encoding="utf-8")
    cmd = validation_command_for("python", bad)
    assert cmd is not None
    result = subprocess.run(cmd, shell=True, capture_output=True)
    assert result.returncode != 0


# --------------------------------------------------------------------------
# parse / build_report / enrich_report
# --------------------------------------------------------------------------


def test_parse_shell_and_report(pattern):
    s = pattern.parse("THINK: validate\nACTION: shell\nCMD: python -m py_compile x.py")
    assert s.kind == "command"
    assert "py_compile" in s.cmd

    r = pattern.parse(
        "THINK: done\nACTION: report\nSUMMARY: files compiled\nFAILED_FILE: none\n"
    )
    assert r.kind == "final"
    assert r.payload["summary"] == "files compiled"
    assert r.payload["failed_file"] is None


def test_build_report_complete_then_enrich(pattern, workdir):
    f = workdir / "x.py"
    f.write_text("x", encoding="utf-8")
    report = pattern.build_report(
        final_payload={"summary": "compiled", "failed_file": None},
        commands_executed=[],
        stop_reason="converged",
        iterations_used=1,
        status="complete",
        notes="ok",
    )
    assert isinstance(report, CreateReport)
    assert report.summary == "compiled"
    assert report.files_created == []
    enriched = pattern.enrich_report(report, MutationResult(files_changed=[f], diff=""))
    assert enriched.files_created == [str(f)]


def test_build_report_mutation_error_enriches_with_exception(pattern):
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="mutation_error",
        iterations_used=0,
        status="error",
        notes="mutation error",
    )
    enriched = pattern.enrich_report(report, FileExistsError("workdir/already.py: exists"))
    assert "exists" in enriched.failed_file


# --------------------------------------------------------------------------
# Contract surface: DEC-021 (no domain) + DEC-022 (abort) + operator_text
# --------------------------------------------------------------------------


def test_on_command_timeout_is_abort(pattern):
    assert pattern.on_command_timeout("python -m py_compile x.py", Step(kind="command", cmd="x")) == "abort"


def test_system_prompt_no_domain(pattern, workdir):
    spec = CreateSpec(
        goal="create a file",
        workdir=workdir,
        files=[NewFile(path=workdir / "x.py", content="x = 1\n", language="python")],
    )
    prompt = pattern.system_prompt(spec)
    assert prompt == SYSTEM_PROMPT
    for token in ("xcode-select", "homebrew", "brew install", "XCTest", "DEVELOPER_DIR"):
        assert token not in prompt


def test_operator_text_covers_paths_and_content(pattern, workdir):
    spec = CreateSpec(
        goal="create with markers",
        workdir=workdir,
        files=[NewFile(path=workdir / "x.py", content="CONTENT_MARKER_42", language="python")],
    )
    text = pattern.operator_text(spec)
    assert spec.goal in text
    assert "x.py" in text
    assert "CONTENT_MARKER_42" in text


def test_create_pattern_registered():
    from optimai.patterns.base import available_patterns, get_pattern
    assert "create" in available_patterns()
    assert isinstance(get_pattern("create"), CreatePattern)


def test_create_pattern_spec_model(pattern):
    assert pattern.spec_model is CreateSpec


def test_initial_user_message_includes_validation_commands(pattern, workdir):
    spec = CreateSpec(
        goal="create two files",
        workdir=workdir,
        files=[
            NewFile(path=workdir / "ok.py", content="x = 1\n", language="python"),
            NewFile(path=workdir / "skip.txt", content="hi\n", language="none"),
        ],
    )
    msg = pattern.initial_user_message(spec)
    assert "python -m py_compile" in msg
    assert "no check" in msg.lower() or "none" in msg.lower()
