"""Pattern D — Execute: run a bounded operator-supplied pack of commands (DEC-006).

Sémantique option (1), arbitrée Desktop #8 / brief CLI #5 : `ExecuteSpec.commands`
est un *pack ordonné* fourni par le Cortex. Le worker l'exécute via la boucle du
moteur, peut intercaler une commande **read-only** de diagnostic en cas d'échec,
mais ne propose **jamais** de commande mutante hors pack.

DEC-022 : les commandes mutent l'état → politique timeout = ``abort``. Une
commande tuée en cours peut avoir laissé des effets de bord ; surface l'incohérence
plutôt que d'enchaîner sur un état inconnu.
"""

from typing import Literal

from optimai.patterns.base import Step, TimeoutPolicy, register
from optimai.schemas.report import ExecuteReport
from optimai.schemas.task_spec import ExecuteSpec

SYSTEM_PROMPT = """\
You execute a pre-validated PACK of shell commands on a developer workstation,
proceeding through the pack in order and reporting the outcome.

Scope — read carefully:
- The PACK in the first user message is the ONLY mutating work you may do.
- Execute the pack commands ONE AT A TIME, in order, observing each result.
- Between two pack commands you MAY run ONE short read-only diagnostic
  command (e.g. `ls`, `cat`, `which`, `--version`) if interpreting a result
  needs context. You may NOT run any mutating command outside the pack.
- If a pack command fails and the subsequent steps clearly depend on it,
  report the failure (FAILED_COMMAND named) — do NOT improvise alternatives.

Hard constraints:
- No sudo. No commands outside the pack except short read-only diagnostics.
- Each command is a SINGLE line for /bin/sh -c.
- Command output is truncated and you are told the exit code.
- You have a small, bounded number of turns. Converge: as soon as the pack
  is done (or has clearly failed), deliver the report.

Domain knowledge:
- The CONTEXT block in the first user message carries domain-specific guidance
  from the Cortex (preconditions, expected outputs, what failure means). Use
  it to interpret each command's result.

At EVERY turn reply in EXACTLY ONE of these two formats, nothing else.

To run a command:
THINK: <one-line reasoning>
ACTION: shell
CMD: <single shell command on one line>

To deliver the final verdict:
THINK: <one-line reasoning>
ACTION: report
SUMMARY: <one line — what was accomplished or what broke>
FAILED_COMMAND: <the pack command that failed, or "none">

Rules:
- Output ONLY the block. No markdown fences, no extra prose.
- Report as soon as the pack is done (success or failure). Do not run extra commands.
"""


def _none_if_blank(value: str) -> str | None:
    cleaned = value.strip()
    return None if cleaned == "" or cleaned.lower() == "none" else cleaned


@register("execute")
class ExecutePattern:
    """Strategy D — bounded pack execution with worker-driven sequencing."""

    name: str = "execute"
    spec_model: type = ExecuteSpec
    tool_description: str = (
        "Run an ordered, pre-validated pack of shell commands (mutating). The "
        "worker proceeds through `commands` one at a time, may interleave short "
        "read-only diagnostics, and reports a compact verdict (summary + which "
        "command failed if any). Aborts on per-command timeout — partial mutations "
        "are surfaced, never improvised around."
    )

    def system_prompt(self, spec: ExecuteSpec) -> str:
        return SYSTEM_PROMPT

    def initial_user_message(self, spec: ExecuteSpec) -> str:
        pack_lines = "\n".join(f"{i + 1}. {cmd}" for i, cmd in enumerate(spec.commands))
        return (
            f"GOAL:\n{spec.goal}\n\n"
            f"CONTEXT:\n{spec.context}\n\n"
            f"PACK (execute in order, one at a time):\n{pack_lines}"
        )

    def operator_text(self, spec: ExecuteSpec) -> str:
        # WARNING: pack commands are operator-supplied vectors — vet them too,
        # not just the goal. Concatenated for a single blacklist scan.
        return spec.goal + "\n" + "\n".join(spec.commands)

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
            summary = ""
            failed_command = ""
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("SUMMARY:"):
                    summary = stripped[len("SUMMARY:"):].strip()
                elif stripped.startswith("FAILED_COMMAND:"):
                    failed_command = stripped[len("FAILED_COMMAND:"):].strip()
            payload = {
                "summary": _none_if_blank(summary),
                "failed_command": _none_if_blank(failed_command),
            }
            return Step(kind="final", think=think, payload=payload)

        return Step(kind="invalid", reason=f"unrecognized ACTION {action!r}")

    def build_report(
        self,
        *,
        final_payload: dict | None,
        commands_executed: list[dict],
        stop_reason: str,
        iterations_used: int,
        status: Literal["complete", "incomplete", "error"],
        notes: str,
    ) -> ExecuteReport:
        if status == "complete" and final_payload is not None:
            return ExecuteReport(
                status="complete",
                summary=final_payload.get("summary"),
                failed_command=final_payload.get("failed_command"),
                iterations_used=iterations_used,
                stop_reason=stop_reason,
                commands_executed=commands_executed,
                notes=notes[:1024],
            )
        # incomplete / error (including DEC-022 command_timeout abort):
        # surface the last attempted command as failed_command so the Cortex
        # sees where the chain stopped without having to walk the trace.
        last_cmd = commands_executed[-1]["cmd"] if commands_executed else None
        return ExecuteReport(
            status=status,
            summary=None,
            failed_command=last_cmd if status == "error" else None,
            iterations_used=iterations_used,
            stop_reason=stop_reason,
            commands_executed=commands_executed,
            notes=notes[:1024],
        )

    def on_command_timeout(self, cmd: str, step: Step) -> TimeoutPolicy:
        # WARNING: Execute pack commands MUTATE state. A timed-out mutating
        # command may have left a partial side effect (file half-written,
        # build in intermediate state, package partially installed). DEC-022:
        # abort with stop_reason="command_timeout"; the Cortex decides whether
        # to roll forward or back, with full knowledge of the inconsistency.
        return "abort"
