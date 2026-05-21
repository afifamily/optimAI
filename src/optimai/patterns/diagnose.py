"""Pattern A — Diagnose: iterative toolchain investigation (DEC-006, DEC-021).

The strategy that turns a `DiagnoseSpec` into a `DiagnoseReport`. Everything
loop-related lives in `dispatcher.py`; this module only describes *what* a
diagnose turn looks like (prompt + protocol + parser + report shape).

DEC-021 (Cortex<->Hands contract) drives the system prompt: the cadrage and
the THINK/ACTION protocol are hard-coded here, but the *domain knowledge* for
each instance (e.g. "for 'no such module XCTest', check `xcode-select -p`...")
travels via `spec.context` from the Cortex. That keeps the pattern reusable
across diagnostic families without forking the prompt.
"""

from typing import Literal

from optimai.patterns.base import Step, TimeoutPolicy, register
from optimai.schemas.report import DiagnoseReport
from optimai.schemas.task_spec import DiagnoseSpec

SYSTEM_PROMPT = """\
You are an environment diagnostic assistant. You diagnose why a build/test
tool fails on a developer workstation by inspecting the TOOLCHAIN state with
informational shell commands, then reasoning over the results.

Scope — read carefully:
- You diagnose the ENVIRONMENT / TOOLCHAIN, not a specific project checkout.
- The project source tree is NOT necessarily present on this machine. Do NOT
  search the filesystem for it: no broad `find`, no hunting for source files.
- Focus on tool state: which toolchain is selected, which frameworks/SDKs it
  ships, version output.

Hard constraints:
- Informational commands ONLY. No sudo. No file modifications. No installs.
- Each command is a SINGLE line for /bin/sh -c. Keep commands fast and
  targeted; never scan large directory trees.
- Command output is truncated and you are told the exit code.
- You have a small, bounded number of turns. Converge fast: as soon as the
  toolchain state is clear, deliver the report. 2-4 commands should suffice.

Domain knowledge:
- The CONTEXT block in the first user message carries domain-specific guidance
  from the Cortex: typical root causes for this family of failure, which
  commands to run, which fixes to name. USE IT to orient your investigation.
- If the CONTEXT names a fix that requires sudo or a blocked command, NAME it
  in TEMPORARY_FIX / PERMANENT_FIX — never emit it as a CMD.

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

Rules:
- Output ONLY the block. No markdown fences, no extra prose.
- Report as soon as you have firm evidence; do not run redundant commands.
"""


def _none_if_blank(value: str) -> str | None:
    """Map an empty / 'none' worker field to a real None."""
    cleaned = value.strip()
    return None if cleaned == "" or cleaned.lower() == "none" else cleaned


@register("diagnose")
class DiagnosePattern:
    """Strategy A — informational diagnosis loop."""

    name: str = "diagnose"
    spec_model: type = DiagnoseSpec

    def system_prompt(self, spec: DiagnoseSpec) -> str:
        return SYSTEM_PROMPT

    def initial_user_message(self, spec: DiagnoseSpec) -> str:
        return f"GOAL:\n{spec.goal}\n\nCONTEXT:\n{spec.context}"

    def operator_text(self, spec: DiagnoseSpec) -> str:
        # `goal` is the high-level Cortex instruction — the prompt-injection-shaped
        # vector worth scrubbing pre-flight. `context` (domain knowledge) is
        # intentionally allowed to mention sensitive tokens or named fixes.
        return spec.goal

    def parse(self, worker_text: str) -> Step:
        lines = worker_text.strip().splitlines()
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
                        return Step(kind="invalid", reason="empty CMD")
                    return Step(kind="command", think=think, cmd=cmd)
            return Step(kind="invalid", reason="ACTION shell without CMD line")

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
            payload = {
                "root_cause": _none_if_blank(root_cause),
                "evidence": evidence,
                "temporary_fix": _none_if_blank(temporary_fix),
                "permanent_fix": _none_if_blank(permanent_fix),
            }
            return Step(kind="final", think=think, payload=payload)

        return Step(kind="invalid", reason=f"unrecognized ACTION {action!r}")

    def on_command_timeout(self, cmd: str, step: Step) -> TimeoutPolicy:
        # Diagnose commands are informational (xcode-select -p, --version, …) and
        # leave no side effect, so a single slow command is safely retryable —
        # the worker reacts to "TIMED OUT" by picking a tighter command (DEC-022).
        return "recover"

    def build_report(
        self,
        *,
        final_payload: dict | None,
        commands_executed: list[dict],
        stop_reason: str,
        iterations_used: int,
        status: Literal["complete", "incomplete", "error"],
        notes: str,
    ) -> DiagnoseReport:
        if status == "complete" and final_payload is not None:
            return DiagnoseReport(
                status="complete",
                root_cause=final_payload["root_cause"],
                evidence=final_payload["evidence"],
                temporary_fix=final_payload["temporary_fix"],
                permanent_fix=final_payload["permanent_fix"],
                iterations_used=iterations_used,
                stop_reason=stop_reason,
                commands_executed=commands_executed,
                notes=notes[:1024],
            )
        # incomplete / error: root_cause + fixes stay None (schema allows it).
        return DiagnoseReport(
            status=status,
            iterations_used=iterations_used,
            stop_reason=stop_reason,
            commands_executed=commands_executed,
            notes=notes[:1024],
        )
