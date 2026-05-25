"""Tests for optimai.patterns.scan — strategy E (DEC-025, DEC-026, DEC-021)."""

from pathlib import Path

import pytest

from optimai.patterns import base as patterns_base
from optimai.patterns.base import Step
from optimai.patterns.scan import SYSTEM_PROMPT, ScanPattern
from optimai.schemas.report import ScanMatch, ScanReport
from optimai.schemas.task_spec import ScanSpec, ScanTarget


@pytest.fixture
def pattern():
    return ScanPattern()


@pytest.fixture
def spec(tmp_path):
    return ScanSpec(
        goal="prove the admin path is not leaked in served output",
        context="audit of bassmati robots.txt + sitemap",
        workdir=tmp_path,
        required=["og:title"],
        forbidden=["/admin/"],
        secret_patterns=["xyz-very-secret-value"],
        targets=[
            ScanTarget(kind="fs", ref="public/robots.txt"),
            ScanTarget(kind="http", ref="http://localhost/robots.txt"),
        ],
    )


# --------------------------------------------------------------------------
# Registration — E is plugged via the registry (no server.py changes)
# --------------------------------------------------------------------------


def test_scan_pattern_registered():
    """The package import side-effect must have registered Pattern E."""
    assert "scan" in patterns_base.available_patterns()
    p = patterns_base.get_pattern("scan")
    assert p.name == "scan"
    assert p.spec_model is ScanSpec


def test_scan_pattern_spec_model(pattern):
    assert pattern.spec_model is ScanSpec


# --------------------------------------------------------------------------
# parse — shell / report / invalid
# --------------------------------------------------------------------------


def test_parse_well_formed_shell_command(pattern):
    text = "THINK: hunt the admin path\nACTION: shell\nCMD: grep -rn /admin/ ."
    step = pattern.parse(text)
    assert step.kind == "command"
    assert step.cmd == "grep -rn /admin/ ."
    assert step.think == "hunt the admin path"


def test_parse_shell_without_cmd_is_invalid(pattern):
    step = pattern.parse("THINK: t\nACTION: shell")
    assert step.kind == "invalid"
    assert "CMD" in step.reason


def test_parse_shell_with_empty_cmd_is_invalid(pattern):
    step = pattern.parse("THINK: t\nACTION: shell\nCMD:    ")
    assert step.kind == "invalid"
    assert "empty" in step.reason.lower()


def test_parse_report_pass(pattern):
    text = (
        "THINK: all required present, no forbidden / secret found\n"
        "ACTION: report\n"
        "VERDICT: pass\n"
        "MATCHES:\n"
        "MISSING_REQUIRED:\n"
        "PATTERNS_CHECKED: 3\n"
    )
    step = pattern.parse(text)
    assert step.kind == "final"
    assert step.payload["verdict"] == "pass"
    assert step.payload["matches"] == []
    assert step.payload["missing_required"] == []
    assert step.payload["patterns_checked"] == 3


def test_parse_report_fail_with_match_and_missing(pattern):
    text = (
        "THINK: forbidden found, required missing\n"
        "ACTION: report\n"
        "VERDICT: fail\n"
        "MATCHES:\n"
        "- public/robots.txt | 7 | /admin/ | Disallow: /admin/\n"
        "MISSING_REQUIRED:\n"
        "- og:title\n"
        "PATTERNS_CHECKED: 2\n"
    )
    step = pattern.parse(text)
    assert step.kind == "final"
    assert step.payload["verdict"] == "fail"
    assert len(step.payload["matches"]) == 1
    m = step.payload["matches"][0]
    assert m["target"] == "public/robots.txt"
    assert m["line"] == 7
    assert m["pattern"] == "/admin/"
    assert m["text"] == "Disallow: /admin/"
    assert step.payload["missing_required"] == ["og:title"]
    assert step.payload["patterns_checked"] == 2


def test_parse_match_line_with_dash_line_number(pattern):
    """HTTP responses do not have a meaningful line number — '-' yields None."""
    text = (
        "THINK: scan http\n"
        "ACTION: report\n"
        "VERDICT: fail\n"
        "MATCHES:\n"
        "- http://example.com/r.txt | - | /admin/ | href=/admin/foo\n"
        "MISSING_REQUIRED:\n"
        "PATTERNS_CHECKED: 1\n"
    )
    step = pattern.parse(text)
    m = step.payload["matches"][0]
    assert m["line"] is None
    assert m["target"] == "http://example.com/r.txt"


def test_parse_unknown_action_is_invalid(pattern):
    step = pattern.parse("THINK: ?\nACTION: dance")
    assert step.kind == "invalid"
    assert "dance" in step.reason or "unrecognized" in step.reason.lower()


def test_parse_garbage_is_invalid(pattern):
    step = pattern.parse("the model forgot the protocol entirely")
    assert step.kind == "invalid"


def test_parse_drops_malformed_match_lines(pattern):
    """A single malformed entry must not poison the whole report."""
    text = (
        "THINK: t\n"
        "ACTION: report\n"
        "VERDICT: fail\n"
        "MATCHES:\n"
        "- bogus line without enough fields\n"
        "- public/x.html | 12 | /admin/ | href=/admin/\n"
        "MISSING_REQUIRED:\n"
        "PATTERNS_CHECKED: 1\n"
    )
    step = pattern.parse(text)
    assert len(step.payload["matches"]) == 1
    assert step.payload["matches"][0]["target"] == "public/x.html"


# --------------------------------------------------------------------------
# build_report — complete / incomplete / error
# --------------------------------------------------------------------------


def test_build_report_complete_pass(pattern):
    payload = {
        "verdict": "pass",
        "matches": [],
        "missing_required": [],
        "patterns_checked": 2,
    }
    report = pattern.build_report(
        final_payload=payload,
        commands_executed=[{"cmd": "grep -rn /admin .", "exit": 1, "stdout_truncated": False}],
        stop_reason="converged",
        iterations_used=2,
        status="complete",
        notes="no leak",
    )
    assert isinstance(report, ScanReport)
    assert report.verdict == "pass"
    assert report.matches == []
    assert report.missing_required == []
    assert report.patterns_checked == 2


def test_build_report_complete_fail(pattern):
    payload = {
        "verdict": "fail",
        "matches": [
            {"target": "f.txt", "line": 1, "text": "/admin/", "pattern": "/admin/"}
        ],
        "missing_required": ["og:title"],
        "patterns_checked": 2,
    }
    report = pattern.build_report(
        final_payload=payload,
        commands_executed=[{"cmd": "grep /admin/ f.txt", "exit": 0, "stdout_truncated": False}],
        stop_reason="converged",
        iterations_used=3,
        status="complete",
        notes="leak found",
    )
    assert report.verdict == "fail"
    assert len(report.matches) == 1
    assert report.missing_required == ["og:title"]


def test_build_report_incomplete_leaves_verdict_none(pattern):
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="max_iterations",
        iterations_used=10,
        status="incomplete",
        notes="hit max iterations",
    )
    assert report.verdict is None
    assert report.matches == []


def test_build_report_error_keeps_verdict_none(pattern):
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="blacklist_violation",
        iterations_used=1,
        status="error",
        notes="blocked",
    )
    assert report.status == "error"
    assert report.verdict is None
    assert report.stop_reason == "blacklist_violation"


def test_build_report_truncates_notes(pattern):
    report = pattern.build_report(
        final_payload=None,
        commands_executed=[],
        stop_reason="worker_error",
        iterations_used=1,
        status="error",
        notes="x" * 2000,
    )
    assert len(report.notes) <= 1024


# --------------------------------------------------------------------------
# Cortex<->Hands contract (DEC-021)
# --------------------------------------------------------------------------


def test_system_prompt_carries_no_domain_knowledge(pattern, spec):
    """Anti-regression for DEC-021: no project-specific patterns in the prompt."""
    prompt = pattern.system_prompt(spec)
    # The fixture's domain-specific patterns must NOT leak into the prompt.
    assert "/admin/" not in prompt
    assert "og:title" not in prompt
    assert "xyz-very-secret-value" not in prompt
    assert "bassmati" not in prompt
    # The protocol scaffolding must still be there.
    assert "THINK:" in prompt
    assert "ACTION:" in prompt
    assert "VERDICT:" in prompt
    assert "MATCHES:" in prompt
    assert "MISSING_REQUIRED:" in prompt
    # Generic guidance about secret values must be present.
    assert "redacted" in prompt.lower()


def test_initial_user_message_carries_patterns_and_targets(pattern, spec):
    msg = pattern.initial_user_message(spec)
    assert spec.goal in msg
    assert spec.context in msg
    assert "REQUIRED" in msg
    assert "FORBIDDEN" in msg
    assert "SECRET" in msg
    assert "TARGETS" in msg
    # Every pattern + target ref is rendered.
    assert "og:title" in msg
    assert "/admin/" in msg
    assert "xyz-very-secret-value" in msg
    assert "public/robots.txt" in msg
    assert "http://localhost/robots.txt" in msg


def test_operator_text_covers_goal_and_refs_but_not_patterns(pattern, spec):
    """DEC-008/DEC-026: refs are operator vectors; patterns flow through like CONTEXT."""
    text = pattern.operator_text(spec)
    assert spec.goal in text
    # Both target refs must be vetted.
    assert "public/robots.txt" in text
    assert "http://localhost/robots.txt" in text
    # The patterns themselves must NOT be in the operator_text — they may
    # carry token-shaped values that the blacklist would (wrongly) reject.
    assert "/admin/" not in text
    assert "og:title" not in text
    assert "xyz-very-secret-value" not in text


def test_scan_on_command_timeout_is_recover(pattern):
    """DEC-022: scan commands are read-only — recovery is safe."""
    decision = pattern.on_command_timeout(
        "grep -rn /admin/ .", Step(kind="command", cmd="grep -rn /admin/ .")
    )
    assert decision == "recover"


def test_system_prompt_is_constant_string(pattern, spec):
    assert pattern.system_prompt(spec) == SYSTEM_PROMPT


def test_spec_workdir_path(tmp_path):
    spec = ScanSpec(
        goal="scan that workdir resolves cleanly",
        workdir=tmp_path,
        required=["foo"],
        targets=[ScanTarget(kind="fs", ref="x")],
    )
    assert isinstance(spec.workdir, Path)
    assert spec.workdir.exists()


# --------------------------------------------------------------------------
# Mocked fs / http "scans" — convergence via dispatcher with a scripted worker
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_fs_via_dispatcher_pass(tmp_path):
    """End-to-end: scan against a tmp file, worker scripted, fs-only grep."""
    import httpx

    from optimai.config import Settings
    from optimai.dispatcher import dispatch

    REPO_ROOT = Path(__file__).resolve().parents[1]
    DEFAULT_BLACKLIST = REPO_ROOT / "config" / "blacklist.txt"

    # Real file the worker can grep — it doesn't actually contain /admin/.
    (tmp_path / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    spec = ScanSpec(
        goal="prove the admin path is absent from the served robots",
        workdir=tmp_path,
        forbidden=["/admin/"],
        targets=[ScanTarget(kind="fs", ref="robots.txt")],
    )

    cursor = {"i": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        idx = cursor["i"]
        cursor["i"] += 1
        replies = [
            "THINK: scan fs target\nACTION: shell\nCMD: grep -nF /admin/ robots.txt\n",
            (
                "THINK: forbidden absent\n"
                "ACTION: report\n"
                "VERDICT: pass\n"
                "MATCHES:\n"
                "MISSING_REQUIRED:\n"
                "PATTERNS_CHECKED: 1\n"
            ),
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": replies[idx]},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    settings = Settings(
        OPTIMAI_MAX_ITERATIONS=4,
        OPTIMAI_TIMEOUT_SECONDS=30,
        OPTIMAI_MAX_OUTPUT_BYTES=10240,
        OPTIMAI_BLACKLIST_FILE=DEFAULT_BLACKLIST,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await dispatch("scan", spec, settings=settings, client=client)

    assert isinstance(report, ScanReport)
    assert report.status == "complete"
    assert report.verdict == "pass"
    assert report.patterns_checked == 1
    # grep with no match returns exit 1 — that is "info, not error" per the prompt.
    assert len(report.commands_executed) == 1
    assert report.commands_executed[0]["exit"] == 1


@pytest.mark.asyncio
async def test_scan_http_via_dispatcher_fail(tmp_path, monkeypatch):
    """End-to-end: scan against an HTTP target — `curl` is faked via shell.run."""
    import httpx

    from optimai import dispatcher as dispatcher_mod
    from optimai.config import Settings
    from optimai.dispatcher import dispatch
    from optimai.shell import CommandResult

    REPO_ROOT = Path(__file__).resolve().parents[1]
    DEFAULT_BLACKLIST = REPO_ROOT / "config" / "blacklist.txt"

    async def fake_run(cmd, workdir, *, patterns, timeout_seconds, max_output_bytes, env=None):
        # Pretend the curl|grep pipeline found a leak.
        return CommandResult(
            cmd=cmd,
            exit_code=0,
            stdout="Disallow: /admin/\n",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_seconds=0.0,
        )

    monkeypatch.setattr(dispatcher_mod, "shell_run", fake_run)

    spec = ScanSpec(
        goal="audit the served robots for an admin-path leak",
        workdir=tmp_path,
        forbidden=["/admin/"],
        targets=[ScanTarget(kind="http", ref="http://localhost/robots.txt")],
    )

    cursor = {"i": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        idx = cursor["i"]
        cursor["i"] += 1
        replies = [
            "THINK: fetch and grep\nACTION: shell\nCMD: curl -s http://localhost/robots.txt | grep -nF /admin/\n",
            (
                "THINK: leak found in served output\n"
                "ACTION: report\n"
                "VERDICT: fail\n"
                "MATCHES:\n"
                "- http://localhost/robots.txt | - | /admin/ | Disallow: /admin/\n"
                "MISSING_REQUIRED:\n"
                "PATTERNS_CHECKED: 1\n"
            ),
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": replies[idx]},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    settings = Settings(
        OPTIMAI_MAX_ITERATIONS=4,
        OPTIMAI_TIMEOUT_SECONDS=30,
        OPTIMAI_MAX_OUTPUT_BYTES=10240,
        OPTIMAI_BLACKLIST_FILE=DEFAULT_BLACKLIST,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await dispatch("scan", spec, settings=settings, client=client)

    assert report.status == "complete"
    assert report.verdict == "fail"
    assert len(report.matches) == 1
    assert report.matches[0].pattern == "/admin/"
    assert report.matches[0].target == "http://localhost/robots.txt"
    # HTTP body has no line number — None survived the round-trip.
    assert report.matches[0].line is None


# --------------------------------------------------------------------------
# pytest-asyncio bridge for async tests above
# --------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=False)
def _asyncio_marker():  # pragma: no cover — only here to flag intent
    """The two async tests rely on pytest-asyncio's `asyncio_mode = auto` config."""
    return None


def test_scan_match_dump_round_trip():
    """The Step.payload uses dicts; build_report rehydrates ScanMatch from them."""
    m = ScanMatch(target="x", line=1, text="t", pattern="p")
    rehydrated = ScanMatch(**m.model_dump())
    assert rehydrated == m
