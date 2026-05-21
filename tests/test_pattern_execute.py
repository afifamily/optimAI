"""Tests for optimai.patterns.execute — strategy D (DEC-006, DEC-021, DEC-022)."""

import pytest

from optimai.patterns.base import Step
from optimai.patterns.execute import SYSTEM_PROMPT, ExecutePattern
from optimai.schemas.report import ExecuteReport
from optimai.schemas.task_spec import ExecuteSpec


@pytest.fixture
def pattern():
    return ExecutePattern()


@pytest.fixture
def spec(tmp_path):
    return ExecuteSpec(
        goal="run the smoke pack and report",
        context="(no preconditions to worry about)",
        workdir=tmp_path,
        commands=["echo a", "echo b", "true"],
    )


# --------------------------------------------------------------------------
# parse: command / final / invalid
# --------------------------------------------------------------------------


def test_parse_well_formed_shell_command(pattern):
    text = "THINK: run step 1\nACTION: shell\nCMD: echo a"
    step = pattern.parse(text)
    assert step.kind == "command"
    assert step.cmd == "echo a"
    assert step.think == "run step 1"


def test_parse_shell_without_cmd_is_invalid(pattern):
    step = pattern.parse("THINK: ?\nACTION: shell")
    assert step.kind == "invalid"
    assert "CMD" in step.reason


def test_parse_well_formed_report_success(pattern):
    text = (
        "THINK: pack done\n"
        "ACTION: report\n"
        "SUMMARY: pack executed; all 3 commands succeeded\n"
        "FAILED_COMMAND: none\n"
    )
    step = pattern.parse(text)
    assert step.kind == "final"
    assert step.payload["summary"] == "pack executed; all 3 commands succeeded"
    assert step.payload["failed_command"] is None  # "none" -> None


def test_parse_well_formed_report_failure(pattern):
    text = (
        "THINK: step 2 broke\n"
        "ACTION: report\n"
        "SUMMARY: brew install failed at step 2; stopped here\n"
        "FAILED_COMMAND: brew install foo\n"
    )
    step = pattern.parse(text)
    assert step.kind == "final"
    assert "brew install" in step.payload["summary"]
    assert step.payload["failed_command"] == "brew install foo"


def test_parse_unknown_action_is_invalid(pattern):
    step = pattern.parse("THINK: ?\nACTION: dance")
    assert step.kind == "invalid"


def test_parse_garbage_is_invalid(pattern):
    step = pattern.parse("the model forgot the protocol entirely")
    assert step.kind == "invalid"


# --------------------------------------------------------------------------
# build_report: complete / incomplete / error
# --------------------------------------------------------------------------


def test_build_report_complete(pattern):
    payload = {"summary": "all good", "failed_command": None}
    report = pattern.build_report(
        final_payload=payload,
        commands_executed=[
            {"cmd": "echo a", "exit": 0, "stdout_truncated": False},
            {"cmd": "echo b", "exit": 0, "stdout_truncated": False},
        ],
        stop_reason="converged",
        iterations_used=3,
        status="complete",
        notes="ok",
    )
    assert isinstance(report, ExecuteReport)
    assert report.status == "complete"
    assert report.summary == "all good"
    assert report.failed_command is None
    assert report.iterations_used == 3


def test_build_report_complete_with_failed_command(pattern):
    payload = {"summary": "step 2 broke", "failed_command": "brew install foo"}
    report = pattern.build_report(
        final_payload=payload,
        commands_executed=[
            {"cmd": "echo a", "exit": 0, "stdout_truncated": False},
            {"cmd": "brew install foo", "exit": 1, "stdout_truncated": False},
        ],
        stop_reason="converged",
        iterations_used=2,
        status="complete",
        notes="failure surfaced",
    )
    assert report.status == "complete"
    assert report.failed_command == "brew install foo"


def test_build_report_command_timeout_abort(pattern):
    """DEC-022 path: failed_command is auto-filled from the last attempted command."""
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[
            {"cmd": "echo a", "exit": 0, "stdout_truncated": False},
            {"cmd": "brew install foo", "exit": -1, "stdout_truncated": False},
        ],
        stop_reason="command_timeout",
        iterations_used=2,
        status="error",
        notes="command timeout (abort policy). State may be inconsistent.",
    )
    assert report.status == "error"
    assert report.stop_reason == "command_timeout"
    assert report.failed_command == "brew install foo"
    assert report.summary is None


def test_build_report_incomplete_max_iterations(pattern):
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="max_iterations",
        iterations_used=5,
        status="incomplete",
        notes="ran out of turns",
    )
    assert report.status == "incomplete"
    assert report.summary is None
    assert report.failed_command is None  # incomplete != error


def test_build_report_error_blacklist(pattern):
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[{"cmd": "sudo rm -rf /", "exit": -1, "stdout_truncated": False}],
        stop_reason="blacklist_violation",
        iterations_used=1,
        status="error",
        notes="blacklist",
    )
    assert report.status == "error"
    assert report.failed_command == "sudo rm -rf /"


# --------------------------------------------------------------------------
# DEC-022 — Execute aborts on per-command timeout
# --------------------------------------------------------------------------


def test_execute_on_command_timeout_is_abort(pattern):
    """DEC-022 invariant for Execute: mutating commands → abort on timeout."""
    decision = pattern.on_command_timeout("brew install foo", Step(kind="command", cmd="brew install foo"))
    assert decision == "abort"


# --------------------------------------------------------------------------
# Cortex<->Hands contract (DEC-021): no domain knowledge in the prompt
# --------------------------------------------------------------------------


def test_system_prompt_carries_no_domain_knowledge(pattern, spec):
    """Anti-regression for DEC-021: the prompt cadre + protocol only.

    No hard-coded tool names, no project-specific fixes — domain knowledge
    is meant to come through `spec.context`.
    """
    prompt = pattern.system_prompt(spec)
    # Cadrage + protocole present.
    assert "PACK" in prompt
    assert "THINK:" in prompt
    assert "ACTION:" in prompt
    assert "SUMMARY:" in prompt
    assert "FAILED_COMMAND:" in prompt
    assert "CONTEXT" in prompt
    # No tool-specific knowledge baked in.
    forbidden = ("xcode-select", "XCTest", "CommandLineTools", "Xcode.app", "brew install", "homebrew")
    for token in forbidden:
        assert token not in prompt, f"system prompt leaks domain knowledge: {token!r}"


def test_initial_user_message_includes_goal_context_and_pack(pattern, spec):
    msg = pattern.initial_user_message(spec)
    assert "GOAL:" in msg and spec.goal in msg
    assert "CONTEXT:" in msg and spec.context in msg
    assert "PACK" in msg
    # Pack rendered in order with 1-based numbering.
    assert "1. echo a" in msg
    assert "2. echo b" in msg
    assert "3. true" in msg


def test_operator_text_covers_goal_and_pack_commands(pattern, spec):
    """Pack commands are operator-supplied vectors — they MUST be vetted."""
    text = pattern.operator_text(spec)
    assert spec.goal in text
    for cmd in spec.commands:
        assert cmd in text


def test_execute_pattern_spec_model(pattern):
    assert pattern.spec_model is ExecuteSpec


def test_system_prompt_is_constant_string(pattern, spec):
    assert pattern.system_prompt(spec) == SYSTEM_PROMPT


# --------------------------------------------------------------------------
# Registry sanity — patterns/__init__.py imports execute, so it's registered
# --------------------------------------------------------------------------


def test_execute_pattern_registered():
    from optimai.patterns.base import available_patterns, get_pattern

    assert "execute" in available_patterns()
    inst = get_pattern("execute")
    assert inst.name == "execute"
    assert isinstance(inst, ExecutePattern)
