"""DEC-026 — generic secret-value redaction in the Dispatcher.

The redaction is the most security-sensitive new piece of CLI #10. These tests
target the three vectors named in DEC-026 (matches/text, commands_executed.cmd,
free-form notes) and the persistence-on-disk leg (log file). The architectural
guard ``no_scan_imports`` lives at the bottom — DEC-021 sentinel for the new
pattern.
"""

import asyncio
import logging
from pathlib import Path

import httpx
import pytest

from optimai import dispatcher as dispatcher_mod
from optimai.config import Settings
from optimai.dispatcher import (
    _collect_secret_values,
    _redact_report,
    _redact_string,
    dispatch,
)
from optimai.patterns import base as patterns_base
from optimai.schemas.report import (
    CreateReport,
    DiagnoseReport,
    ExecuteReport,
    PatchReport,
    ScanMatch,
    ScanReport,
)
from optimai.schemas.task_spec import ScanSpec, ScanTarget

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLACKLIST = REPO_ROOT / "config" / "blacklist.txt"

# Chosen long and unique so we can grep the log file without false positives.
SECRET = "xyz-very-secret-token-abc123"


def _settings(*, max_iter: int = 4, timeout: int = 30, log_file: Path | None = None) -> Settings:
    extra = {"OPTIMAI_LOG_FILE": log_file} if log_file is not None else {}
    return Settings(
        OPTIMAI_MAX_ITERATIONS=max_iter,
        OPTIMAI_TIMEOUT_SECONDS=timeout,
        OPTIMAI_MAX_OUTPUT_BYTES=10240,
        OPTIMAI_BLACKLIST_FILE=DEFAULT_BLACKLIST,
        **extra,
    )


def _scripted_worker(responses: list[str]) -> httpx.AsyncClient:
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
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------------
# Unit-level: _collect_secret_values + _redact_report + _redact_string
# --------------------------------------------------------------------------


def test_collect_secret_values_dedupes_and_skips_empty():
    class _Spec:
        secret_patterns = ["a", "a", "b", "", "c"]

    assert _collect_secret_values(_Spec()) == ["a", "b", "c"]


def test_collect_secret_values_inert_when_attr_missing():
    class _Spec:
        pass

    assert _collect_secret_values(_Spec()) == []


def test_redact_string_replaces_all_occurrences_with_indexed_placeholder():
    placeholders = [("alpha", "<secret:1>"), ("beta", "<secret:2>")]
    out = _redact_string("alpha and beta and alpha", placeholders)
    assert out == "<secret:1> and <secret:2> and <secret:1>"


def test_redact_string_handles_overlapping_secrets():
    """Longer secret first prevents the shorter one stranding a fragment."""
    placeholders = [("supersecret", "<secret:1>"), ("super", "<secret:2>")]
    # Sorted longest-first by the helper that builds this list (mirror that order).
    out = _redact_string("the supersecret stays whole", placeholders)
    assert "supersecret" not in out
    assert out == "the <secret:1> stays whole"


def test_redact_report_is_inert_with_no_secrets():
    report = DiagnoseReport(
        status="complete",
        root_cause="xyz-very-secret-token-abc123",
        evidence=["nothing was redacted"],
        stop_reason="converged",
    )
    out = _redact_report(report, secrets=[])
    assert out == report  # identity preserved when there's nothing to do
    assert "xyz-very-secret" in out.model_dump_json()


def test_redact_report_strips_secret_from_simple_string_field():
    report = DiagnoseReport(
        status="complete",
        root_cause=f"leak: {SECRET} found in env",
        evidence=[f"saw {SECRET}"],
        stop_reason="converged",
    )
    out = _redact_report(report, secrets=[SECRET])
    assert SECRET not in out.root_cause
    assert all(SECRET not in line for line in out.evidence)
    assert "<secret:1>" in out.root_cause


# --------------------------------------------------------------------------
# Vector 1 — matches[].text and matches[].pattern
# --------------------------------------------------------------------------


def test_vector_1_redaction_strips_secret_from_scan_match_text_and_pattern():
    report = ScanReport(
        status="complete",
        verdict="fail",
        matches=[
            ScanMatch(
                target="some.txt",
                line=10,
                text=f"line contains {SECRET} here",
                pattern=SECRET,
            )
        ],
        missing_required=[],
        patterns_checked=1,
        iterations_used=2,
        stop_reason="converged",
    )
    out = _redact_report(report, secrets=[SECRET])
    serialized = out.model_dump_json()
    assert SECRET not in serialized
    assert out.matches[0].text == "line contains <secret:1> here"
    assert out.matches[0].pattern == "<secret:1>"


# --------------------------------------------------------------------------
# Vector 2 — commands_executed[].cmd (the easy one to forget)
# --------------------------------------------------------------------------


def test_vector_2_redaction_strips_secret_from_commands_cmd():
    """Same secret may have been searched for via `grep "<value>"` — that
    command literally contains the value. A scrub of only the matches.text
    field would leave this leak open: this is the regression guard."""
    report = ScanReport(
        status="complete",
        verdict="pass",
        matches=[],
        missing_required=[],
        patterns_checked=1,
        iterations_used=2,
        stop_reason="converged",
        commands_executed=[
            {"cmd": f"grep -nF '{SECRET}' robots.txt", "exit": 1, "stdout_truncated": False}
        ],
    )
    out = _redact_report(report, secrets=[SECRET])
    serialized = out.model_dump_json()
    assert SECRET not in serialized, "secret survives in commands_executed.cmd"
    assert "<secret:1>" in out.commands_executed[0]["cmd"]


# --------------------------------------------------------------------------
# Vector 3 — free-form fields (notes here; same principle for any str field)
# --------------------------------------------------------------------------


def test_vector_3_redaction_strips_secret_from_notes():
    report = ScanReport(
        status="complete",
        verdict="fail",
        matches=[],
        missing_required=[],
        patterns_checked=1,
        iterations_used=2,
        stop_reason="converged",
        notes=f"observed {SECRET} in the served output",
    )
    out = _redact_report(report, secrets=[SECRET])
    assert SECRET not in out.notes
    assert SECRET not in out.model_dump_json()


# --------------------------------------------------------------------------
# Cross-vector guard — all three vectors at once survive the same scrub
# --------------------------------------------------------------------------


def test_redaction_covers_all_three_vectors_simultaneously():
    """The brief's spirit: a single test that proves text+cmd+notes all clean."""
    report = ScanReport(
        status="complete",
        verdict="fail",
        matches=[ScanMatch(target="x", line=1, text=f"hit {SECRET}", pattern=SECRET)],
        missing_required=[],
        patterns_checked=1,
        iterations_used=3,
        stop_reason="converged",
        commands_executed=[
            {"cmd": f"grep -nF {SECRET} x", "exit": 0, "stdout_truncated": False}
        ],
        notes=f"the value {SECRET} surfaced",
    )
    out = _redact_report(report, secrets=[SECRET])
    serialized = out.model_dump_json()
    assert SECRET not in serialized, "secret survives in serialized report (some vector unscrubbed)"


# --------------------------------------------------------------------------
# Architectural assertion: failure to redact must be explicit (DEC-008 §4)
# --------------------------------------------------------------------------


def test_redact_report_assertion_fires_if_redaction_misses(monkeypatch):
    """If the walk somehow leaves a literal secret, an AssertionError fires
    rather than the value silently leaving the dispatcher."""
    report = ScanReport(
        status="complete",
        verdict="fail",
        matches=[ScanMatch(target="x", line=1, text=f"hit {SECRET}", pattern=SECRET)],
        missing_required=[],
        patterns_checked=1,
        iterations_used=1,
        stop_reason="converged",
    )

    # Sabotage the walker so the secret is not actually scrubbed.
    monkeypatch.setattr(dispatcher_mod, "_redact_walk", lambda node, _ph: node)
    with pytest.raises(AssertionError) as exc:
        _redact_report(report, secrets=[SECRET])
    assert "redaction failed" in str(exc.value).lower()


# --------------------------------------------------------------------------
# Inertia — A/D/B/C reports traverse the redaction unchanged
# --------------------------------------------------------------------------


def test_inertia_a_diagnose_report_unchanged_with_no_secrets():
    report = DiagnoseReport(
        status="complete",
        root_cause="ok",
        evidence=["x"],
        stop_reason="converged",
        commands_executed=[{"cmd": "grep -rn ADMIN .", "exit": 1, "stdout_truncated": False}],
    )
    assert _redact_report(report, secrets=[]) == report


def test_inertia_d_execute_report_unchanged_with_no_secrets():
    report = ExecuteReport(
        status="complete",
        summary="all green",
        failed_command=None,
        stop_reason="converged",
        commands_executed=[{"cmd": "go build ./...", "exit": 0, "stdout_truncated": False}],
    )
    assert _redact_report(report, secrets=[]) == report


def test_inertia_b_patch_report_unchanged_with_no_secrets():
    report = PatchReport(
        status="complete",
        summary="validated",
        diff="--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n",
        files_changed=["/tmp/x.py"],
        stop_reason="converged",
    )
    assert _redact_report(report, secrets=[]) == report


def test_inertia_c_create_report_unchanged_with_no_secrets():
    report = CreateReport(
        status="complete",
        summary="created",
        files_created=["/tmp/y.py"],
        stop_reason="converged",
    )
    assert _redact_report(report, secrets=[]) == report


# --------------------------------------------------------------------------
# Pass-without-leak: a verdict=pass scan that never sees the secret is still
# checked to confirm no field carries it.
# --------------------------------------------------------------------------


def test_pass_verdict_never_carries_secret(tmp_path):
    """A scan that finds nothing has nothing to redact — and the resulting
    report still leaves the dispatcher with no field touched by the secret."""
    target = tmp_path / "clean.txt"
    target.write_text("nothing sensitive in here\n", encoding="utf-8")

    spec = ScanSpec(
        goal="prove the secret is absent from the served clean output",
        workdir=tmp_path,
        secret_patterns=[SECRET],
        targets=[ScanTarget(kind="fs", ref="clean.txt")],
    )

    cursor = {"i": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        i = cursor["i"]
        cursor["i"] += 1
        replies = [
            # Worker uses literal grep — its command will *contain* the secret.
            f"THINK: scan\nACTION: shell\nCMD: grep -nF {SECRET} clean.txt\n",
            "THINK: clean\nACTION: report\n"
            "VERDICT: pass\nMATCHES:\nMISSING_REQUIRED:\nPATTERNS_CHECKED: 1\n",
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": replies[i]},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await dispatch("scan", spec, settings=_settings(), client=client)

    report = asyncio.run(go())
    assert report.verdict == "pass"
    # The `cmd` contained the secret pre-redaction — make sure it's clean now.
    assert SECRET not in report.model_dump_json()
    assert "<secret:1>" in report.commands_executed[0]["cmd"]


# --------------------------------------------------------------------------
# Log persistence — the file handler attached to optimai must not contain the
# secret after a full dispatch with secret_patterns.
# --------------------------------------------------------------------------


def _wire_file_logger(log_path: Path) -> tuple[logging.Logger, logging.FileHandler]:
    """Attach a file handler to the optimai package logger and return both."""
    pkg = logging.getLogger("optimai")
    pkg.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    pkg.addHandler(handler)
    pkg.propagate = False
    return pkg, handler


def test_log_persistence_no_secret_after_full_dispatch(tmp_path):
    """End-to-end: a successful scan that grep's for a secret must not leave
    the literal value anywhere in the file handler's output."""
    log_path = tmp_path / "optimai.log"
    pkg_logger, handler = _wire_file_logger(log_path)

    target = tmp_path / "robots.txt"
    target.write_text("nothing sensitive\n", encoding="utf-8")

    spec = ScanSpec(
        goal="prove the secret is absent from the served output",
        workdir=tmp_path,
        secret_patterns=[SECRET],
        targets=[ScanTarget(kind="fs", ref="robots.txt")],
    )

    cursor = {"i": 0}

    def handler_fn(_request: httpx.Request) -> httpx.Response:
        i = cursor["i"]
        cursor["i"] += 1
        replies = [
            f"THINK: scan\nACTION: shell\nCMD: grep -nF {SECRET} robots.txt\n",
            "THINK: clean\nACTION: report\n"
            "VERDICT: pass\nMATCHES:\nMISSING_REQUIRED:\nPATTERNS_CHECKED: 1\n",
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": replies[i]},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler_fn)) as client:
            return await dispatch("scan", spec, settings=_settings(), client=client)

    try:
        report = asyncio.run(go())
    finally:
        handler.flush()
        pkg_logger.removeHandler(handler)
        handler.close()
        # Reset propagate so other tests inherit the default.
        pkg_logger.propagate = True

    assert report.verdict == "pass"
    log_contents = log_path.read_text(encoding="utf-8")
    assert log_contents, "log file should have captured at least one record"
    assert SECRET not in log_contents, (
        "DEC-026 leg 2 failed: the secret value survives on disk in the log"
    )


# --------------------------------------------------------------------------
# DEC-021 architectural guard — dispatcher has no Scan-specific import
# --------------------------------------------------------------------------


def test_dispatcher_has_no_scan_imports():
    """E must plug in via the registry, just like A/D/B/C — the engine must
    not reference Scan by name in any form."""
    source = Path(dispatcher_mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        "ScanReport",
        "ScanSpec",
        "ScanMatch",
        "ScanTarget",
        "patterns.scan",
        "patterns import scan",
    )
    for token in forbidden:
        assert token not in source, f"dispatcher.py leaks Scan specificity: {token!r}"


# --------------------------------------------------------------------------
# Sanity: the registry sentinel must now see optimai_scan
# --------------------------------------------------------------------------


def test_registry_contains_scan_for_server_propagation():
    assert "scan" in patterns_base.available_patterns()
