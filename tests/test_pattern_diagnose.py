"""Tests for optimai.patterns.diagnose — strategy A (DEC-006, DEC-021)."""

from pathlib import Path

import pytest

from optimai.patterns.diagnose import SYSTEM_PROMPT, DiagnosePattern
from optimai.schemas.report import DiagnoseReport
from optimai.schemas.task_spec import DiagnoseSpec


@pytest.fixture
def pattern():
    return DiagnosePattern()


@pytest.fixture
def spec(tmp_path):
    return DiagnoseSpec(
        goal="diagnose a test failure please",
        context="some domain knowledge from the cortex",
        workdir=tmp_path,
    )


# --------------------------------------------------------------------------
# parse: command / final / invalid
# --------------------------------------------------------------------------


def test_parse_well_formed_shell_command(pattern):
    text = "THINK: check the toolchain\nACTION: shell\nCMD: xcode-select -p"
    step = pattern.parse(text)
    assert step.kind == "command"
    assert step.cmd == "xcode-select -p"
    assert step.think == "check the toolchain"


def test_parse_shell_without_cmd_is_invalid(pattern):
    text = "THINK: missing cmd line\nACTION: shell"
    step = pattern.parse(text)
    assert step.kind == "invalid"
    assert "CMD" in step.reason


def test_parse_shell_with_empty_cmd_is_invalid(pattern):
    text = "THINK: empty\nACTION: shell\nCMD:   "
    step = pattern.parse(text)
    assert step.kind == "invalid"
    assert "empty" in step.reason.lower()


def test_parse_well_formed_report(pattern):
    text = (
        "THINK: toolchain healthy\n"
        "ACTION: report\n"
        "ROOT_CAUSE: developer dir points to Xcode.app\n"
        "EVIDENCE:\n"
        "- xcode-select -p prints /Applications/Xcode.app/Contents/Developer\n"
        "- XCTest.framework is present\n"
        "TEMPORARY_FIX: none\n"
        "PERMANENT_FIX: none\n"
    )
    step = pattern.parse(text)
    assert step.kind == "final"
    assert step.payload["root_cause"] == "developer dir points to Xcode.app"
    assert len(step.payload["evidence"]) == 2
    assert step.payload["temporary_fix"] is None  # "none" -> None
    assert step.payload["permanent_fix"] is None


def test_parse_report_keeps_real_fixes(pattern):
    text = (
        "THINK: cmdline tools selected\n"
        "ACTION: report\n"
        "ROOT_CAUSE: CommandLineTools missing XCTest\n"
        "EVIDENCE:\n"
        "- xcode-select -p prints /Library/Developer/CommandLineTools\n"
        "TEMPORARY_FIX: DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test\n"
        "PERMANENT_FIX: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer\n"
    )
    step = pattern.parse(text)
    assert step.kind == "final"
    assert "DEVELOPER_DIR" in step.payload["temporary_fix"]
    assert "xcode-select -s" in step.payload["permanent_fix"]


def test_parse_unknown_action_is_invalid(pattern):
    text = "THINK: ?\nACTION: dance"
    step = pattern.parse(text)
    assert step.kind == "invalid"
    assert "unrecognized" in step.reason.lower() or "dance" in step.reason


def test_parse_garbage_is_invalid(pattern):
    step = pattern.parse("the model forgot the protocol entirely")
    assert step.kind == "invalid"


# --------------------------------------------------------------------------
# build_report: complete / incomplete / error
# --------------------------------------------------------------------------


def test_build_report_complete(pattern):
    payload = {
        "root_cause": "toolchain ok",
        "evidence": ["xcode-select -p shows Xcode.app"],
        "temporary_fix": None,
        "permanent_fix": None,
    }
    report = pattern.build_report(
        final_payload=payload,
        commands_executed=[{"cmd": "xcode-select -p", "exit": 0, "stdout_truncated": False}],
        stop_reason="converged",
        iterations_used=2,
        status="complete",
        notes="ok",
    )
    assert isinstance(report, DiagnoseReport)
    assert report.status == "complete"
    assert report.root_cause == "toolchain ok"
    assert report.iterations_used == 2
    assert report.stop_reason == "converged"
    assert report.commands_executed[0]["cmd"] == "xcode-select -p"


def test_build_report_error_has_none_root_cause(pattern):
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="blacklist_violation",
        iterations_used=1,
        status="error",
        notes="blocked: sudo something",
    )
    assert report.status == "error"
    assert report.root_cause is None
    assert report.temporary_fix is None
    assert report.permanent_fix is None
    assert report.stop_reason == "blacklist_violation"
    assert "blocked" in report.notes


def test_build_report_incomplete_max_iterations(pattern):
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="max_iterations",
        iterations_used=10,
        status="incomplete",
        notes="reached max_iterations",
    )
    assert report.status == "incomplete"
    assert report.stop_reason == "max_iterations"
    assert report.iterations_used == 10
    assert report.root_cause is None


def test_build_report_truncates_notes(pattern):
    long_notes = "x" * 2000
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="worker_error",
        iterations_used=1,
        status="error",
        notes=long_notes,
    )
    assert len(report.notes) <= 1024


# --------------------------------------------------------------------------
# Cortex<->Hands contract (DEC-021): XCTest knowledge lives in spec.context
# --------------------------------------------------------------------------


def test_system_prompt_carries_no_xctest_hard_knowledge(pattern, spec):
    """Anti-regression for DEC-021: domain knowledge must NOT be hard-coded.

    The PoC system prompt named `xcode-select` and the XCTest fixes explicitly.
    After CLI #4 promotion, the prompt only references CONTEXT generically.
    """
    prompt = pattern.system_prompt(spec)
    assert "xcode-select" not in prompt
    assert "XCTest" not in prompt
    assert "CommandLineTools" not in prompt
    assert "Xcode.app" not in prompt
    # The protocol scaffolding must still be there.
    assert "THINK:" in prompt
    assert "ACTION:" in prompt
    assert "ROOT_CAUSE:" in prompt
    # And the generic "use the CONTEXT" instruction must be present.
    assert "CONTEXT" in prompt


def test_initial_user_message_wraps_goal_and_context(pattern, spec):
    msg = pattern.initial_user_message(spec)
    assert spec.goal in msg
    assert spec.context in msg
    assert "GOAL:" in msg and "CONTEXT:" in msg


def test_operator_text_is_just_the_goal(pattern, spec):
    """The blacklist scrub targets the high-level instruction, not context."""
    assert pattern.operator_text(spec) == spec.goal


def test_diagnose_pattern_spec_model(pattern):
    assert pattern.spec_model is DiagnoseSpec


def test_system_prompt_is_constant_string(pattern, spec):
    # `system_prompt` is currently spec-independent; future refactors that vary it
    # should reconsider DEC-021's contract.
    assert pattern.system_prompt(spec) == SYSTEM_PROMPT


def test_spec_workdir_path(tmp_path):
    # Sanity guard: spec.workdir resolves to a real Path for the dispatcher.
    spec = DiagnoseSpec(goal="x" * 10, workdir=tmp_path)
    assert isinstance(spec.workdir, Path)
    assert spec.workdir.exists()
