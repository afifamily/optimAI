"""Pattern C — Create: deterministic file creation, then worker-driven syntax check.

DEC-024 §corollary : la création est **Cortex-sourced et déterministe** — le
Cortex fournit chemin + contenu complet. Le pattern écrit le fichier
mécaniquement sous snapshot, puis le worker pilote la validation syntaxique
(``python -m py_compile`` / ``swiftc -parse`` / ``gofmt -e``…).

Refus explicite si un ``path`` existe déjà : Create ne fait pas d'écrasement
(DEC-008 §4 — échec explicite, pas de silent overwrite).

Dégradation propre des validateurs : un outil absent (ex. ``swiftc`` non
installé) n'invalide pas la création — le worker rapporte « validation sautée :
outil absent », pas un faux négatif (DEC-024 §validation).

DEC-022 : Create mute → politique timeout per-cmd = ``abort``.
"""

import shlex
from pathlib import Path
from typing import Literal

from optimai.patterns.base import MutationResult, Step, TimeoutPolicy, register
from optimai.schemas.report import CreateReport
from optimai.schemas.task_spec import CreateSpec, NewFile, ValidationLanguage
from optimai.snapshot import Snapshot

SYSTEM_PROMPT = """\
You validate files that have ALREADY been created on a developer workstation by
deterministic code, then report the outcome. You do NOT create or modify any
file yourself.

Scope — read carefully:
- The new files are listed in the MUTATION APPLIED block. Their content was
  written verbatim from the operator specification.
- For each file, a language-aware syntax check command is provided. RUN each
  validation command, observe its result, then report a single verdict.
- If a validation tool is unavailable (exit code likely 127 or "command not
  found"), say so in the SUMMARY but do NOT mark the file as failed — that is
  graceful degradation, not a regression.
- You MAY run ONE short read-only diagnostic command (`which <tool>`,
  `cat <file>`) to clarify a result. No mutations of any kind.

Hard constraints:
- No sudo. No file modifications. Each command is a single line for /bin/sh -c.
- Output is truncated and you are told the exit code.
- You have a small, bounded number of turns. Converge fast.

Domain knowledge:
- The CONTEXT block carries any special expectations (e.g. "this file ships in
  a Swift package — `swiftc -parse` must succeed"). USE IT to interpret results.

At EVERY turn reply in EXACTLY ONE of these two formats, nothing else.

To run a command:
THINK: <one-line reasoning>
ACTION: shell
CMD: <single shell command on one line>

To deliver the final verdict:
THINK: <one-line reasoning>
ACTION: report
SUMMARY: <one line — files validated, validation skipped (tool absent), or what broke>
FAILED_FILE: <"none", or "<path>: <reason>">

Rules:
- Output ONLY the block. No markdown fences, no extra prose.
- Report as soon as you have a verdict — do not run redundant commands.
"""


# --------------------------------------------------------------------------
# Language-aware syntax check
# --------------------------------------------------------------------------

# tool name → command-template. ``{path}`` is replaced (shell-quoted) at call
# time. ``None`` for ``python`` because we always know ``python3`` is around
# in a uv-managed venv — the template is hard-coded below.
_VALIDATION_COMMANDS: dict[ValidationLanguage, str] = {
    "python": "python -m py_compile {path}",
    "swift": "swiftc -parse {path}",
    "go": "gofmt -e {path}",
    "none": "",
}

_TOOL_NAMES: dict[ValidationLanguage, str] = {
    "python": "python",
    "swift": "swiftc",
    "go": "gofmt",
    "none": "",
}


def validation_command_for(language: ValidationLanguage, path: Path) -> str | None:
    """Return the validation shell command for ``language`` / ``path``, or None.

    ``None`` means "no validation" (``language="none"``). The tool-presence
    check is delegated to the worker (the system prompt explains how to read a
    "command not found" result) — the engine stays generic.
    """
    template = _VALIDATION_COMMANDS.get(language, "")
    if not template:
        return None
    return template.format(path=shlex.quote(str(path)))


def _none_if_blank(value: str) -> str | None:
    cleaned = value.strip()
    return None if cleaned == "" or cleaned.lower() == "none" else cleaned


def _resolve_file_path(item: NewFile, workdir: Path) -> Path:
    p = item.path
    if not p.is_absolute():
        p = workdir / p
    return p


def _apply_creates(files: list[NewFile], workdir: Path, snap: Snapshot) -> tuple[list[Path], str]:
    """Create the files under ``snap``; raise if any path already exists.

    ``protect`` runs first per file — that records the missing ancestors so
    rollback can clean up directories we made.
    """
    files_changed: list[Path] = []
    diff_chunks: list[str] = []

    for item in files:
        target = _resolve_file_path(item, workdir)
        snap.protect(target)  # raises SandboxViolation on escape; refuses symlinks
        if target.exists():
            raise FileExistsError(f"refuse to overwrite existing path: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
        files_changed.append(target)
        diff_chunks.append(f"+++ b/{target.name}\n" + _indent_for_diff(item.content))

    return files_changed, "\n".join(diff_chunks)


def _indent_for_diff(content: str) -> str:
    """Render file content as a ``+``-prefixed diff body (lightweight, readable)."""
    return "\n".join(f"+{line}" for line in content.splitlines()) or "+(empty file)"


@register("create")
class CreatePattern:
    """Strategy C — deterministic create + worker-driven syntax check."""

    name: str = "create"
    spec_model: type = CreateSpec
    tool_description: str = (
        "Create new files from Cortex-supplied content (deterministic, atomic). "
        "Refuses to overwrite existing paths; the worker runs a language-aware "
        "syntax check and reports the verdict. Any failure rolls back the whole "
        "call — no half-created files."
    )

    # ---- mutation phase ----------------------------------------------------------

    def mutate(self, spec: CreateSpec, snap: Snapshot) -> MutationResult:
        files_changed, diff = _apply_creates(spec.files, spec.workdir, snap)
        return MutationResult(files_changed=files_changed, diff=diff)

    # ---- loop phase --------------------------------------------------------------

    def system_prompt(self, spec: CreateSpec) -> str:
        return SYSTEM_PROMPT

    def initial_user_message(self, spec: CreateSpec) -> str:
        lines: list[str] = [f"GOAL:\n{spec.goal}", "", f"CONTEXT:\n{spec.context}"]
        lines.append("")
        lines.append("VALIDATION COMMANDS:")
        for f in spec.files:
            resolved = _resolve_file_path(f, spec.workdir)
            cmd = validation_command_for(f.language, resolved)
            label = f.language if f.language != "none" else "(none)"
            lines.append(f"- {resolved} [{label}]: {cmd or '(no check)'}")
        return "\n".join(lines)

    def operator_text(self, spec: CreateSpec) -> str:
        # WARNING: file paths AND file contents are operator-supplied vectors;
        # both must be vetted by the blacklist. Context (domain) is exempt.
        parts: list[str] = [spec.goal]
        for f in spec.files:
            parts.append(str(f.path))
            parts.append(f.content)
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
            failed_file = ""
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("SUMMARY:"):
                    summary = stripped[len("SUMMARY:"):].strip()
                elif stripped.startswith("FAILED_FILE:"):
                    failed_file = stripped[len("FAILED_FILE:"):].strip()
            payload = {
                "summary": _none_if_blank(summary),
                "failed_file": _none_if_blank(failed_file),
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
    ) -> CreateReport:
        if status == "complete" and final_payload is not None:
            return CreateReport(
                status="complete",
                summary=final_payload.get("summary"),
                failed_file=final_payload.get("failed_file"),
                iterations_used=iterations_used,
                stop_reason=stop_reason,
                commands_executed=commands_executed,
                notes=notes[:1024],
            )
        return CreateReport(
            status=status,
            iterations_used=iterations_used,
            stop_reason=stop_reason,
            commands_executed=commands_executed,
            notes=notes[:1024],
        )

    def enrich_report(self, report: CreateReport, outcome: object) -> CreateReport:
        if isinstance(outcome, MutationResult):
            return report.model_copy(
                update={
                    "files_created": [str(p) for p in outcome.files_changed],
                }
            )
        update = {"failed_file": report.failed_file or str(outcome)}
        return report.model_copy(update=update)

    def on_command_timeout(self, cmd: str, step: Step) -> TimeoutPolicy:
        # Validation command timed out → state of the validator unknown, files
        # were just written → abort and let the snapshot restore (DEC-022).
        return "abort"
