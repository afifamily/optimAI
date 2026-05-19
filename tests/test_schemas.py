"""Tests for the Pattern A schemas — DiagnoseSpec / DiagnoseReport."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from optimai.schemas.report import DiagnoseReport
from optimai.schemas.task_spec import DiagnoseSpec


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
