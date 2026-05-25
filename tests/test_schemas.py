"""Tests for the pattern schemas — Diagnose (A), Execute (D), Patch (B), Create (C)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from optimai.schemas.report import (
    CreateReport,
    DiagnoseReport,
    ExecuteReport,
    PatchReport,
    ScanMatch,
    ScanReport,
)
from optimai.schemas.task_spec import (
    CreateSpec,
    DiagnoseSpec,
    ExecuteSpec,
    FileEdit,
    NewFile,
    PatchSpec,
    ScanSpec,
    ScanTarget,
)


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


# --------------------------------------------------------------------------
# Phase 2 — Patch (B) + Create (C) schemas (DEC-024)
# --------------------------------------------------------------------------


def test_patch_spec_requires_workdir(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(ValidationError):
        PatchSpec(
            goal="patch a file",
            workdir=missing,
            edits=[FileEdit(path=tmp_path / "x.py", old="a", new="b")],
        )


def test_patch_spec_rejects_empty_edits(tmp_path):
    with pytest.raises(ValidationError):
        PatchSpec(goal="patch a file", workdir=tmp_path, edits=[])


def test_file_edit_rejects_empty_old():
    with pytest.raises(ValidationError):
        FileEdit(path=Path("/tmp/x"), old="", new="b")


def test_file_edit_allows_empty_new():
    """Empty ``new`` is deletion — valid."""
    e = FileEdit(path=Path("/tmp/x"), old="DELETE_ME\n", new="")
    assert e.new == ""


def test_patch_spec_optional_validation_command(tmp_path):
    spec = PatchSpec(
        goal="patch a file",
        workdir=tmp_path,
        edits=[FileEdit(path=tmp_path / "x.py", old="a", new="b")],
    )
    assert spec.validation_command is None


def test_patch_report_mutation_error_round_trip():
    report = PatchReport(
        status="error",
        stop_reason="mutation_error",
        failed_edit="x.py: 'old' not found",
        files_changed=[],
        diff=None,
        notes="mutation refused",
    )
    restored = PatchReport.model_validate_json(report.model_dump_json())
    assert restored == report


def test_create_spec_requires_workdir(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(ValidationError):
        CreateSpec(
            goal="create a file",
            workdir=missing,
            files=[NewFile(path=tmp_path / "x.py", content="x", language="python")],
        )


def test_create_spec_rejects_empty_files(tmp_path):
    with pytest.raises(ValidationError):
        CreateSpec(goal="create", workdir=tmp_path, files=[])


def test_new_file_default_language_is_none():
    f = NewFile(path=Path("/tmp/x"), content="hi")
    assert f.language == "none"


def test_create_report_json_round_trip():
    report = CreateReport(
        status="complete",
        summary="all files compile",
        files_created=["/tmp/x.py"],
        iterations_used=1,
        stop_reason="converged",
        notes="ok",
    )
    restored = CreateReport.model_validate_json(report.model_dump_json())
    assert restored == report


def test_patch_and_create_reports_accept_mutation_error_stop_reason():
    p = PatchReport(status="error", stop_reason="mutation_error")
    c = CreateReport(status="error", stop_reason="mutation_error")
    assert p.stop_reason == "mutation_error"
    assert c.stop_reason == "mutation_error"


# --------------------------------------------------------------------------
# Phase 3 — Pattern E (Scan/Audit) schemas (DEC-025, DEC-026)
# --------------------------------------------------------------------------


def test_scan_target_http_requires_url_scheme():
    with pytest.raises(ValidationError):
        ScanTarget(kind="http", ref="not-a-url")
    ok = ScanTarget(kind="http", ref="http://example.com/robots.txt")
    assert ok.ref.startswith("http://")


def test_scan_target_fs_accepts_relative_path():
    t = ScanTarget(kind="fs", ref="src/foo.go")
    assert t.kind == "fs"
    assert t.ref == "src/foo.go"


def test_scan_target_rejects_blank_ref():
    with pytest.raises(ValidationError):
        ScanTarget(kind="fs", ref="   ")


def test_scan_spec_requires_at_least_one_pattern_register(tmp_path):
    """Validation: required ∪ forbidden ∪ secret_patterns must be non-empty."""
    with pytest.raises(ValidationError):
        ScanSpec(
            goal="audit the robots.txt",
            workdir=tmp_path,
            targets=[ScanTarget(kind="fs", ref="robots.txt")],
        )


def test_scan_spec_accepts_secret_patterns_alone(tmp_path):
    """A scan that only proves the absence of a secret is valid."""
    spec = ScanSpec(
        goal="prove ADMIN_PREFIX value never appears in served output",
        workdir=tmp_path,
        secret_patterns=["xyz-very-secret-value"],
        targets=[ScanTarget(kind="http", ref="https://example.com/robots.txt")],
    )
    assert spec.secret_patterns == ["xyz-very-secret-value"]
    assert spec.required == []
    assert spec.forbidden == []


def test_scan_spec_rejects_missing_workdir(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(ValidationError):
        ScanSpec(
            goal="scan something",
            workdir=missing,
            required=["foo"],
            targets=[ScanTarget(kind="fs", ref="x")],
        )


def test_scan_spec_rejects_short_goal(tmp_path):
    with pytest.raises(ValidationError):
        ScanSpec(
            goal="hi",
            workdir=tmp_path,
            required=["foo"],
            targets=[ScanTarget(kind="fs", ref="x")],
        )


def test_scan_spec_rejects_empty_targets(tmp_path):
    with pytest.raises(ValidationError):
        ScanSpec(
            goal="scan something",
            workdir=tmp_path,
            required=["foo"],
            targets=[],
        )


def test_scan_spec_rejects_bad_http_url(tmp_path):
    with pytest.raises(ValidationError):
        ScanSpec(
            goal="scan something served",
            workdir=tmp_path,
            required=["og:title"],
            targets=[ScanTarget(kind="http", ref="ftp://example.com/")],
        )


def test_scan_match_round_trip():
    m = ScanMatch(target="robots.txt", line=2, text="Disallow: /admin", pattern="/admin")
    restored = ScanMatch.model_validate_json(m.model_dump_json())
    assert restored == m


def test_scan_report_json_round_trip():
    report = ScanReport(
        status="complete",
        verdict="pass",
        matches=[],
        missing_required=[],
        patterns_checked=3,
        iterations_used=2,
        stop_reason="converged",
        commands_executed=[{"cmd": "grep -rn ADMIN .", "exit": 1, "stdout_truncated": False}],
        notes="no leak found",
    )
    restored = ScanReport.model_validate_json(report.model_dump_json())
    assert restored == report


def test_scan_report_fail_with_matches_and_missing():
    report = ScanReport(
        status="complete",
        verdict="fail",
        matches=[ScanMatch(target="index.html", line=42, text="<a href=/admin>", pattern="/admin")],
        missing_required=["og:title"],
        patterns_checked=2,
        iterations_used=3,
        stop_reason="converged",
    )
    assert report.verdict == "fail"
    assert len(report.matches) == 1
    assert report.missing_required == ["og:title"]


def test_scan_report_incomplete_has_none_verdict():
    """A non-converged scan reports no verdict."""
    report = ScanReport(status="incomplete", stop_reason="max_iterations")
    assert report.verdict is None
    assert report.matches == []
    assert report.missing_required == []


def test_scan_report_rejects_bad_stop_reason():
    with pytest.raises(ValidationError):
        ScanReport(status="complete", verdict="pass", stop_reason="exploded")
