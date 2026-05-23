"""Pattern B — Patch: deterministic search-and-replace on existing files (DEC-024).

Sémantique arbitrée DEC-024 §corollary : la mutation est **Cortex-sourced et
déterministe**. Le worker n'invente aucun édit ; il valide l'état muté et
formule le verdict (compile/test OK ou non).

Atomicité intra-appel : chaque édit doit matcher ``old`` exactement une fois.
No-match / multi-match / validation KO → la snapshot remet les fichiers à
l'identique avant le retour (DEC-024 §atomicité).

DEC-022 : le pattern mute → politique timeout per-cmd = ``abort``.
"""

import difflib
from collections import OrderedDict
from pathlib import Path
from typing import Literal

from optimai.patterns.base import MutationResult, Step, TimeoutPolicy, register
from optimai.schemas.report import PatchReport
from optimai.schemas.task_spec import FileEdit, PatchSpec
from optimai.snapshot import Snapshot

SYSTEM_PROMPT = """\
You validate a deterministic patch that has ALREADY been applied to files on a
developer workstation, then report the outcome. You do NOT propose or apply
any further mutations.

Scope — read carefully:
- The patch has been applied by code BEFORE this conversation. You will see a
  MUTATION APPLIED block listing the changed files and a unified diff.
- Your job is to RUN the validation step provided by the operator (a compile,
  parse, or test command), observe its result, and report.
- You MAY run ONE short read-only diagnostic command (e.g. `head`, `cat`,
  `which`) if interpreting an error needs context. You may NOT modify any file
  and you may NOT propose new edits.
- If validation fails, name the failure cause in the SUMMARY — do not improvise
  a fix.

Hard constraints:
- No sudo. No file modifications. Each command is a single line for /bin/sh -c.
- Output is truncated and you are told the exit code.
- You have a small, bounded number of turns. Converge fast — usually 1 command
  (the validation) and 1 report.

Domain knowledge:
- The CONTEXT block carries domain-specific guidance (what "passing" looks like,
  expected validation output, what a regression here would mean). USE IT.

At EVERY turn reply in EXACTLY ONE of these two formats, nothing else.

To run a command:
THINK: <one-line reasoning>
ACTION: shell
CMD: <single shell command on one line>

To deliver the final verdict:
THINK: <one-line reasoning>
ACTION: report
SUMMARY: <one line — patch validated or what broke>
FAILED_EDIT: <"none", or a short description of which edit caused trouble>

Rules:
- Output ONLY the block. No markdown fences, no extra prose.
- Report as soon as you have a verdict — do not run redundant commands.
"""


def _none_if_blank(value: str) -> str | None:
    cleaned = value.strip()
    return None if cleaned == "" or cleaned.lower() == "none" else cleaned


def _resolve_edit_path(edit: FileEdit, workdir: Path) -> Path:
    """Resolve ``edit.path`` against the workdir if it's relative."""
    p = edit.path
    if not p.is_absolute():
        p = workdir / p
    return p


def _apply_edits(edits: list[FileEdit], workdir: Path, snap: Snapshot) -> tuple[list[Path], str]:
    """Apply the search-and-replace pack under ``snap``; raise on any miss.

    Edits sharing the same target file are applied in-memory in declaration
    order before a single write — so a no-match later in the pack still rolls
    back the whole call (the snapshot wraps the dispatcher).
    """
    by_path: OrderedDict[Path, list[FileEdit]] = OrderedDict()
    for e in edits:
        target = _resolve_edit_path(e, workdir)
        by_path.setdefault(target, []).append(e)

    files_changed: list[Path] = []
    diff_chunks: list[str] = []

    for target, file_edits in by_path.items():
        # Sandbox check + temp backup happen here. Snapshot raises on escape.
        snap.protect(target)
        if not target.exists():
            raise FileNotFoundError(f"patch target does not exist: {target}")
        original = target.read_text(encoding="utf-8")
        current = original
        for e in file_edits:
            count = current.count(e.old)
            if count == 0:
                raise ValueError(f"{target}: 'old' string not found")
            if count > 1:
                raise ValueError(f"{target}: 'old' matched {count} times — must be unique")
            current = current.replace(e.old, e.new, 1)
        if current == original:
            # All edits were no-ops; protect was called but nothing changed.
            continue
        target.write_text(current, encoding="utf-8")
        files_changed.append(target)
        diff_chunks.append(
            "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    current.splitlines(keepends=True),
                    fromfile=f"a/{target.name}",
                    tofile=f"b/{target.name}",
                    n=3,
                )
            )
        )

    return files_changed, "\n".join(c for c in diff_chunks if c)


@register("patch")
class PatchPattern:
    """Strategy B — deterministic patch + worker-driven validation."""

    name: str = "patch"
    spec_model: type = PatchSpec
    tool_description: str = (
        "Apply Cortex-supplied search-and-replace edits to existing files "
        "(deterministic, atomic). Each edit must match exactly once; the worker "
        "then validates the result and reports a unified diff. Any failure rolls "
        "back the whole call — files are never left half-patched."
    )

    # ---- mutation phase (DEC-024) -------------------------------------------------

    def mutate(self, spec: PatchSpec, snap: Snapshot) -> MutationResult:
        files_changed, diff = _apply_edits(spec.edits, spec.workdir, snap)
        return MutationResult(files_changed=files_changed, diff=diff)

    # ---- loop phase --------------------------------------------------------------

    def system_prompt(self, spec: PatchSpec) -> str:
        return SYSTEM_PROMPT

    def initial_user_message(self, spec: PatchSpec) -> str:
        validation = spec.validation_command or "(none — report based on the diff alone)"
        return (
            f"GOAL:\n{spec.goal}\n\n"
            f"CONTEXT:\n{spec.context}\n\n"
            f"VALIDATION COMMAND:\n{validation}"
        )

    def operator_text(self, spec: PatchSpec) -> str:
        # WARNING: every operator-supplied vector is vetted — goal, the edit
        # targets, the replacement texts, and the validation command. The
        # context (domain knowledge) stays exempt (DEC-021).
        parts: list[str] = [spec.goal]
        for e in spec.edits:
            parts.append(str(e.path))
            parts.append(e.new)
        if spec.validation_command:
            parts.append(spec.validation_command)
        return "\n".join(parts)

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
            failed_edit = ""
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("SUMMARY:"):
                    summary = stripped[len("SUMMARY:"):].strip()
                elif stripped.startswith("FAILED_EDIT:"):
                    failed_edit = stripped[len("FAILED_EDIT:"):].strip()
            payload = {
                "summary": _none_if_blank(summary),
                "failed_edit": _none_if_blank(failed_edit),
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
    ) -> PatchReport:
        # Mutation-side fields (diff / files_changed) are stamped by
        # enrich_report after the dispatcher has the MutationResult — leave
        # them at defaults here.
        if status == "complete" and final_payload is not None:
            return PatchReport(
                status="complete",
                summary=final_payload.get("summary"),
                failed_edit=final_payload.get("failed_edit"),
                iterations_used=iterations_used,
                stop_reason=stop_reason,
                commands_executed=commands_executed,
                notes=notes[:1024],
            )
        return PatchReport(
            status=status,
            iterations_used=iterations_used,
            stop_reason=stop_reason,
            commands_executed=commands_executed,
            notes=notes[:1024],
        )

    def enrich_report(self, report: PatchReport, outcome: object) -> PatchReport:
        """Stamp diff / files_changed / failed_edit from the mutation outcome.

        ``outcome`` is either the ``MutationResult`` (success) or the Exception
        that crashed ``mutate`` (rollback). Called by the dispatcher AFTER
        build_report so this pattern keeps its standard 6-kwarg signature.
        """
        if isinstance(outcome, MutationResult):
            return report.model_copy(
                update={
                    "diff": outcome.diff or None,
                    "files_changed": [str(p) for p in outcome.files_changed],
                }
            )
        # outcome is the exception from mutate — populate failed_edit only if
        # build_report didn't already set it (worker may have named it).
        update = {"failed_edit": report.failed_edit or str(outcome)}
        return report.model_copy(update=update)

    def on_command_timeout(self, cmd: str, step: Step) -> TimeoutPolicy:
        # WARNING: Patch mutates files. A validation command timing out leaves
        # the workstation in a state where we don't know whether the build
        # half-ran. DEC-022: abort, let the Cortex decide (snapshot will revert
        # since report.status will be "error").
        return "abort"
