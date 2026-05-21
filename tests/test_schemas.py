"""Tests for the pattern schemas — Diagnose (A) and Execute (D)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from optimai.schemas.report import DiagnoseReport, ExecuteReport
from optimai.schemas.task_spec import DiagnoseSpec, ExecuteSpec


def test_diagnose_spec_rejects_missing_workdir(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(ValidationError):
        DiagnoseSpec(goal="diagnose something", workdir=missing)


def test_diagnose_spec_rejects_short_goal(tmp_path):
    with pytest.raises(ValidationError):
        DiagnoseSpec(goal="hi", workdir=tmp_path)


def test_diagnose_spec_resolves_workdir(tmp_path):
    spec = DiagnoseSpec(goal="diagnose the build", workdir=tmp_path)
    # Symlinks normalized: the stored workdir is the resolved path.
    assert spec.workdir == tmp_path.resolve()
    assert spec.context == ""
    assert spec.allowed_read_paths == []
    assert spec.extra_blacklist == []


def test_diagnose_report_incomplete_allows_none_root_cause():
    report = DiagnoseReport(status="incomplete", stop_reason="max_iterations")
    assert report.root_cause is None
    assert report.iterations_used == 0
    assert report.evidence == []


def test_diagnose_report_json_round_trip():
    original = DiagnoseReport(
        status="complete",
        root_cause="xcode-select points to CommandLineTools",
        evidence=["xcode-select -p -> /Library/Developer/CommandLineTools"],
        temporary_fix="DEVELOPER_DIR=... swift test",
        permanent_fix="sudo xcode-select -s /Applications/Xcode.app/Contents/Developer",
        iterations_used=3,
        stop_reason="converged",
        commands_executed=[{"cmd": "xcode-select -p", "exit": 0, "stdout_truncated": False}],
        notes="env diagnosed",
    )
    restored = DiagnoseReport.model_validate_json(original.model_dump_json())
    assert restored == original


def test_diagnose_report_rejects_bad_stop_reason():
    with pytest.raises(ValidationError):
        DiagnoseReport(status="complete", stop_reason="exploded")


def test_diagnose_spec_keeps_allowed_read_paths():
    spec = DiagnoseSpec(
        goal="diagnose XCTest failure",
        workdir=Path.home(),
        allowed_read_paths=[Path("/Applications")],
    )
    assert Path("/Applications") in spec.allowed_read_paths


# --------------------------------------------------------------------------
# Pattern D — ExecuteSpec / ExecuteReport (CLI #5)
# --------------------------------------------------------------------------


def test_execute_spec_rejects_missing_workdir(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(ValidationError):
        ExecuteSpec(goal="run the smoke pack", workdir=missing, commands=["echo hi"])


def test_execute_spec_rejects_empty_commands(tmp_path):
    with pytest.raises(ValidationError):
        ExecuteSpec(goal="run the smoke pack", workdir=tmp_path, commands=[])


def test_execute_spec_rejects_blank_command(tmp_path):
    with pytest.raises(ValidationError):
        ExecuteSpec(goal="run the smoke pack", workdir=tmp_path, commands=["echo ok", "   "])


def test_execute_spec_keeps_pack_order(tmp_path):
    spec = ExecuteSpec(
        goal="run the smoke pack",
        workdir=tmp_path,
        commands=["echo a", "echo b", "true"],
    )
    assert spec.commands == ["echo a", "echo b", "true"]
    assert spec.context == ""
    assert spec.extra_blacklist == []


def test_execute_report_incomplete_allows_none_summary():
    report = ExecuteReport(status="incomplete", stop_reason="max_iterations")
    assert report.summary is None
    assert report.failed_command is None
    assert report.iterations_used == 0


def test_execute_report_accepts_command_timeout_stop_reason():
    # DEC-022 added "command_timeout" to the StopReason vocabulary.
    report = ExecuteReport(
        status="error",
        stop_reason="command_timeout",
        failed_command="brew install foo",
        notes="state may be inconsistent",
    )
    assert report.stop_reason == "command_timeout"
    assert report.failed_command == "brew install foo"


def test_execute_report_json_round_trip():
    original = ExecuteReport(
        status="complete",
        summary="pack executed; all 3 commands succeeded",
        failed_command=None,
        iterations_used=4,
        stop_reason="converged",
        commands_executed=[
            {"cmd": "echo a", "exit": 0, "stdout_truncated": False},
            {"cmd": "echo b", "exit": 0, "stdout_truncated": False},
            {"cmd": "true", "exit": 0, "stdout_truncated": False},
        ],
        notes="ok",
    )
    restored = ExecuteReport.model_validate_json(original.model_dump_json())
    assert restored == original


def test_execute_report_rejects_bad_stop_reason():
    with pytest.raises(ValidationError):
        ExecuteReport(status="error", stop_reason="exploded")


def test_diagnose_report_accepts_command_timeout_stop_reason():
    """DEC-022 shared vocabulary — even though Diagnose never abort-on-timeout,
    the Literal is shared so the type stays consistent across reports."""
    report = DiagnoseReport(status="error", stop_reason="command_timeout")
    assert report.stop_reason == "command_timeout"
