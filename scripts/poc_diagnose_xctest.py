#!/usr/bin/env python3
"""PoC — Pattern A end-to-end on the TBS XCTest failure case (CLI #3, step 5).

A *scripted* Cortex-light loop that proves the full chain holds end-to-end:
worker reasons -> proposes a shell command -> shell.run executes it -> the
result is injected back into context -> ... -> final DiagnoseReport.

This is NOT the clean Pattern A module (that is patterns/diagnose.py, CLI #4).
The system prompt and the parser live here on purpose; they get factored out
once the mechanics are proven.

Run from the repo root:

    uv run python scripts/poc_diagnose_xctest.py

Exit code: 0 if the DiagnoseReport status is "complete", 1 otherwise.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Make `optimai` importable when run as a plain script (no install needed).
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from optimai.config import get_settings  # noqa: E402
from optimai.schemas.report import DiagnoseReport  # noqa: E402
from optimai.schemas.task_spec import DiagnoseSpec  # noqa: E402
from optimai.shell import (  # noqa: E402
    BlacklistViolation,
    CommandTimeout,
    ShellError,
    is_blacklisted,
    load_blacklist,
)
from optimai.shell import run as shell_run  # noqa: E402
from optimai.worker import WorkerError, chat  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

# --------------------------------------------------------------------------
# Worker protocol — THINK / ACTION / (shell | report)
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an environment diagnostic assistant. You diagnose why a build/test
tool fails on a developer workstation by inspecting the TOOLCHAIN state with
informational shell commands, then reasoning over the results.

Scope — read carefully:
- You diagnose the ENVIRONMENT / TOOLCHAIN, not a specific project checkout.
- The project source tree is NOT necessarily present on this machine. Do NOT
  search the filesystem for it: no broad `find`, no hunting for Package.swift
  or source files.
- Focus on tool state: which toolchain is selected, which frameworks/SDKs it
  ships, version output.

Hard constraints:
- Informational commands ONLY. No sudo. No file modifications. No installs.
- Each command is a SINGLE line for /bin/sh -c. Keep commands fast and
  targeted; never scan large directory trees.
- Command output is truncated to 10 KB and you are told the exit code.
- You have a small, bounded number of turns. Converge fast: as soon as the
  toolchain state is clear, deliver the report. 2-4 commands should suffice.

At EVERY turn reply in EXACTLY ONE of these two formats, nothing else.

To run a command:
THINK: <one-line reasoning>
ACTION: shell
CMD: <single shell command on one line>

To deliver the final verdict:
THINK: <one-line reasoning>
ACTION: report
ROOT_CAUSE: <one line>
EVIDENCE:
- <evidence line 1>
- <evidence line 2>
TEMPORARY_FIX: <one line, or "none">
PERMANENT_FIX: <one line, or "none">

Domain knowledge for "no such module 'XCTest'":
- XCTest.framework ships inside Xcode.app, NOT inside the CommandLineTools.
- `xcode-select -p` prints the active developer directory.
- If it points to an Xcode.app developer dir, XCTest is available and the
  toolchain is HEALTHY — report that as the root cause (no environment fault).
- If it points to /Library/Developer/CommandLineTools, THAT is the root cause:
  CommandLineTools does not ship XCTest. Temporary fix:
  `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test`.
  Permanent fix: `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`
  — NAME it in PERMANENT_FIX, never emit it as a CMD.

Rules:
- Output ONLY the block. No markdown fences, no extra prose.
- If a fix needs sudo or a blocked command, still NAME it in TEMPORARY_FIX /
  PERMANENT_FIX, but never emit it as a CMD.
- Report as soon as you have firm evidence; do not run redundant commands.
"""

# Field markers used by the report parser.
_REPORT_FIELDS = ("ROOT_CAUSE:", "EVIDENCE:", "TEMPORARY_FIX:", "PERMANENT_FIX:")


def _none_if_blank(value: str) -> str | None:
    """Map an empty / 'none' worker field to a real None."""
    cleaned = value.strip()
    return None if cleaned == "" or cleaned.lower() == "none" else cleaned


def parse_worker_output(text: str) -> dict:
    """Parse a worker turn into a structured dict.

    Returns one of:
      {"action": "shell", "think": str, "cmd": str}
      {"action": "report", "think": str, "root_cause": str|None, "evidence": list,
       "temporary_fix": str|None, "permanent_fix": str|None}
      {"action": "invalid", "reason": str}
    """
    lines = text.strip().splitlines()
    think = ""
    action = ""
    for line in lines:
        if line.startswith("THINK:"):
            think = line[len("THINK:"):].strip()
        elif line.startswith("ACTION:"):
            action = line[len("ACTION:"):].strip().lower()

    if action == "shell":
        for line in lines:
            if line.startswith("CMD:"):
                cmd = line[len("CMD:"):].strip()
                if not cmd:
                    return {"action": "invalid", "reason": "empty CMD"}
                return {"action": "shell", "think": think, "cmd": cmd}
        return {"action": "invalid", "reason": "ACTION shell without CMD line"}

    if action == "report":
        root_cause = ""
        temporary_fix = ""
        permanent_fix = ""
        evidence: list[str] = []
        in_evidence = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("ROOT_CAUSE:"):
                root_cause = stripped[len("ROOT_CAUSE:"):].strip()
                in_evidence = False
            elif stripped.startswith("EVIDENCE:"):
                in_evidence = True
            elif stripped.startswith("TEMPORARY_FIX:"):
                temporary_fix = stripped[len("TEMPORARY_FIX:"):].strip()
                in_evidence = False
            elif stripped.startswith("PERMANENT_FIX:"):
                permanent_fix = stripped[len("PERMANENT_FIX:"):].strip()
                in_evidence = False
            elif in_evidence and stripped.startswith("-"):
                evidence.append(stripped.lstrip("- ").strip())
        return {
            "action": "report",
            "think": think,
            "root_cause": _none_if_blank(root_cause),
            "evidence": evidence,
            "temporary_fix": _none_if_blank(temporary_fix),
            "permanent_fix": _none_if_blank(permanent_fix),
        }

    return {"action": "invalid", "reason": f"unrecognized ACTION {action!r}"}


# --------------------------------------------------------------------------
# Orchestration loop (Cortex-light)
# --------------------------------------------------------------------------


def _build_spec(fixture_text: str) -> DiagnoseSpec:
    """Build the DiagnoseSpec for the TBS XCTest case."""
    return DiagnoseSpec(
        goal=(
            "`swift test` fails with 'no such module XCTest'. "
            "Find the root cause and propose a fix. "
            "Use only informational shell commands (no sudo, no modifications)."
        ),
        context=fixture_text,
        workdir=Path.home(),  # neutral workdir — diagnosis modifies nothing
        allowed_read_paths=[
            Path("/Applications"),
            Path("/Library/Developer"),
        ],
        extra_blacklist=[
            r"\bxcode-select\s+-s\b",  # block the invasive fix during the PoC
            r"\bxcodebuild\s+-license\b",
        ],
    )


async def _run_loop(spec: DiagnoseSpec, settings, patterns) -> DiagnoseReport:
    """Run the bounded worker<->shell loop and return a DiagnoseReport."""
    user_intro = f"GOAL:\n{spec.goal}\n\nCONTEXT:\n{spec.context}"
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_intro},
    ]
    commands_executed: list[dict] = []
    correction_used = False
    iterations = 0

    for iterations in range(1, settings.max_iterations + 1):
        try:
            response = await chat(messages, max_tokens=768)
        except WorkerError as exc:
            print(f"[iter {iterations}] worker error: {exc}")
            return DiagnoseReport(
                status="error",
                stop_reason="worker_error",
                iterations_used=iterations,
                commands_executed=commands_executed,
                notes=f"worker error: {exc}"[:1024],
            )

        messages.append({"role": "assistant", "content": response.content})
        parsed = parse_worker_output(response.content)

        if parsed["action"] == "shell":
            cmd = parsed["cmd"]
            print(f"[iter {iterations}] THINK: {parsed['think']}")
            print(f"[iter {iterations}] CMD: {cmd}")
            try:
                result = await shell_run(
                    cmd,
                    spec.workdir,
                    patterns=patterns,
                    timeout_seconds=min(30, settings.timeout_seconds),
                    max_output_bytes=settings.max_output_bytes,
                )
            except BlacklistViolation as exc:
                print(f"[iter {iterations}] BLOCKED: {exc}")
                commands_executed.append(
                    {"cmd": cmd, "exit": -1, "stdout_truncated": False}
                )
                return DiagnoseReport(
                    status="error",
                    stop_reason="blacklist_violation",
                    iterations_used=iterations,
                    commands_executed=commands_executed,
                    notes=f"blacklist violation: {exc}"[:1024],
                )
            except CommandTimeout as exc:
                # A single slow command is not a chain failure — report it
                # back to the worker so it can pick a faster command. The
                # loop's global timeout (DEC-007) stays the real budget guard.
                print(f"[iter {iterations}] TIMEOUT: {exc}")
                print()
                commands_executed.append(
                    {"cmd": cmd, "exit": -1, "stdout_truncated": False}
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Command: {cmd}\n"
                            "Result: TIMED OUT and was killed (per-command limit). "
                            "Pick a faster, more targeted command — avoid scanning "
                            "large directory trees."
                        ),
                    }
                )
                continue
            except ShellError as exc:
                print(f"[iter {iterations}] SHELL ERROR: {exc}")
                commands_executed.append(
                    {"cmd": cmd, "exit": -1, "stdout_truncated": False}
                )
                return DiagnoseReport(
                    status="error",
                    stop_reason="shell_error",
                    iterations_used=iterations,
                    commands_executed=commands_executed,
                    notes=f"shell error: {exc}"[:1024],
                )

            stdout_preview = result.stdout.strip() or "(empty)"
            print(
                f"[iter {iterations}] EXIT: {result.exit_code}  "
                f"STDOUT: {stdout_preview[:300]}"
            )
            print()
            commands_executed.append(
                {
                    "cmd": cmd,
                    "exit": result.exit_code,
                    "stdout_truncated": result.stdout_truncated,
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Command: {cmd}\n"
                        f"Exit: {result.exit_code}\n"
                        f"STDOUT (truncated={result.stdout_truncated}):\n"
                        f"{result.stdout}\n"
                        f"STDERR:\n{result.stderr}"
                    ),
                }
            )
            continue

        if parsed["action"] == "report":
            print(f"[iter {iterations}] THINK: {parsed['think']}")
            print(f"[iter {iterations}] ACTION: report")
            print()
            return DiagnoseReport(
                status="complete",
                root_cause=parsed["root_cause"],
                evidence=parsed["evidence"],
                temporary_fix=parsed["temporary_fix"],
                permanent_fix=parsed["permanent_fix"],
                iterations_used=iterations,
                stop_reason="converged",
                commands_executed=commands_executed,
                notes=parsed["think"][:1024],
            )

        # parsed["action"] == "invalid"
        print(f"[iter {iterations}] INVALID worker output: {parsed['reason']}")
        if correction_used:
            return DiagnoseReport(
                status="error",
                stop_reason="worker_error",
                iterations_used=iterations,
                commands_executed=commands_executed,
                notes=f"worker produced invalid output twice: {parsed['reason']}"[:1024],
            )
        correction_used = True
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Your previous reply was not parseable ({parsed['reason']}). "
                    "Reply again using EXACTLY the THINK/ACTION format. "
                    "No markdown fences, no extra prose."
                ),
            }
        )

    # Loop exhausted without a report.
    return DiagnoseReport(
        status="incomplete",
        stop_reason="max_iterations",
        iterations_used=iterations,
        commands_executed=commands_executed,
        notes="reached max_iterations without a final report",
    )


async def _main() -> int:
    settings = get_settings()

    # config/blacklist.txt is relative to the repo root, not the cwd.
    blacklist_path = settings.blacklist_file
    if not blacklist_path.is_absolute():
        blacklist_path = REPO_ROOT / blacklist_path

    fixture_text = (REPO_ROOT / "tests/fixtures/xctest_failure.txt").read_text(
        encoding="utf-8"
    )
    spec = _build_spec(fixture_text)
    patterns = load_blacklist(blacklist_path, extra_patterns=spec.extra_blacklist)

    # Defense in depth: the goal itself is operator-supplied text — make sure it
    # carries nothing blacklisted before we feed it to the worker.
    blocked, matched = is_blacklisted(spec.goal, patterns)
    if blocked:
        print(f"Refusing: goal text matches blacklist pattern {matched!r}")
        return 1

    print("=" * 64)
    print("optimAI — PoC Pattern A — TBS XCTest diagnosis")
    print(f"workdir          : {spec.workdir}")
    print(f"blacklist        : {blacklist_path} ({len(patterns)} patterns)")
    print(f"max_iterations   : {settings.max_iterations}")
    print(f"timeout_seconds  : {settings.timeout_seconds}")
    print("=" * 64)
    print()

    try:
        report = await asyncio.wait_for(
            _run_loop(spec, settings, patterns),
            timeout=settings.timeout_seconds,
        )
    except asyncio.TimeoutError:
        print(f"\n[timeout] loop exceeded {settings.timeout_seconds}s")
        report = DiagnoseReport(
            status="incomplete",
            stop_reason="timeout",
            iterations_used=settings.max_iterations,
            notes=f"global timeout after {settings.timeout_seconds}s",
        )

    print("=== DiagnoseReport ===")
    print(report.model_dump_json(indent=2))
    return 0 if report.status == "complete" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
