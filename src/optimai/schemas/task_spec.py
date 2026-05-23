"""Task spec schemas — input contracts for the patterns (DEC-002, DEC-006)."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _resolve_existing_workdir(value: Path) -> Path:
    """Shared workdir validator: resolve symlinks, require it to exist.

    A missing path raises ValueError so Pydantic wraps it into a
    ValidationError (it does not catch raw OSError / FileNotFoundError).
    """
    try:
        return value.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"workdir does not exist: {value}") from exc


class DiagnoseSpec(BaseModel):
    """Input contract for Pattern A — an investigation request from the Cortex."""

    goal: str = Field(
        min_length=5,
        description="Investigation objective formulated by the Cortex.",
    )
    context: str = Field(
        default="",
        description="Free-form additional context (log excerpt, environment, etc.).",
    )
    workdir: Path = Field(
        description="Working directory / sandbox root. Must exist.",
    )
    allowed_read_paths: list[Path] = Field(
        default_factory=list,
        description="Extra read-only paths. The workdir is implicitly included.",
    )
    extra_blacklist: list[str] = Field(
        default_factory=list,
        description="Task-specific blacklist regex patterns, added to the base list.",
    )

    @field_validator("workdir")
    @classmethod
    def _workdir_must_exist(cls, value: Path) -> Path:
        return _resolve_existing_workdir(value)


class ExecuteSpec(BaseModel):
    """Input contract for Pattern D — a bounded pack of shell commands (DEC-006).

    Per DEC-022 the commands MUTATE state, so the dispatcher's per-pattern
    timeout policy is `abort`: a half-killed mutating command leaves the
    machine in an unknown state, no improvisation.

    Per DEC-021 (Cortex<->Hands contract) the operator-supplied pack +
    domain context come from the Cortex; the pattern stays generic.
    """

    goal: str = Field(
        min_length=5,
        description="Execution objective formulated by the Cortex.",
    )
    context: str = Field(
        default="",
        description="Free-form context: preconditions, expected outputs, what failure means.",
    )
    workdir: Path = Field(
        description="Working directory / sandbox root. Must exist.",
    )
    commands: list[str] = Field(
        min_length=1,
        description="Ordered pack of shell commands the worker must run, one at a time.",
    )
    allowed_read_paths: list[Path] = Field(
        default_factory=list,
        description="Extra read-only paths. The workdir is implicitly included.",
    )
    extra_blacklist: list[str] = Field(
        default_factory=list,
        description="Task-specific blacklist regex patterns, added to the base list.",
    )

    @field_validator("workdir")
    @classmethod
    def _workdir_must_exist(cls, value: Path) -> Path:
        return _resolve_existing_workdir(value)

    @field_validator("commands")
    @classmethod
    def _commands_non_empty_strings(cls, value: list[str]) -> list[str]:
        # Cheap shape check — heavy validation (blacklist) happens at dispatch
        # time so the engine can reject with a single uniform exception path.
        for i, cmd in enumerate(value):
            if not cmd or not cmd.strip():
                raise ValueError(f"commands[{i}] is empty or blank")
        return value


# --------------------------------------------------------------------------
# Phase 2 — mutating patterns (DEC-006, DEC-024)
# --------------------------------------------------------------------------

# Validation languages supported by Pattern C — kept short on purpose
# (Swift / Python / Go from the user's three flagship projects, plus an
# explicit ``none`` escape hatch). DEC-024 §corollary: the mutation itself
# is deterministic; the worker only reads validation output and reports.
ValidationLanguage = Literal["swift", "python", "go", "none"]


class FileEdit(BaseModel):
    """One search-and-replace edit on a file inside the sandbox (DEC-024).

    ``old`` MUST match exactly once in the target file (no-match / multi-match
    fail the whole call — atomicity intra-appel). The pattern is deterministic
    Python, not the worker — so a malformed ``old`` is a refusal, not a guess.
    """

    path: Path = Field(description="Target file, relative or absolute; must live in the sandbox.")
    old: str = Field(min_length=1, description="Exact substring to replace; must match exactly once.")
    new: str = Field(description="Replacement text — empty string is allowed (deletion).")


class NewFile(BaseModel):
    """One file to create inside the sandbox (DEC-024).

    Refused at mutate-time if the path already exists — Create is creation, not
    overwrite. ``language`` drives the optional syntax check; ``none`` skips it.
    """

    path: Path = Field(description="New file path; must live in the sandbox; must NOT exist.")
    content: str = Field(description="Full file body — written verbatim, no template expansion.")
    language: ValidationLanguage = Field(
        default="none",
        description="Drives the post-create syntax check. ``none`` disables it.",
    )


class PatchSpec(BaseModel):
    """Input contract for Pattern B — Cortex-supplied search-and-replace edits.

    Per DEC-024 the mutation is Cortex-sourced and deterministic: every edit's
    ``old`` must match exactly once. The worker then runs the validation step
    (typically a build/compile command) and reports a verdict — it never
    proposes further mutations (cadrage in `patterns/patch.py`).
    """

    goal: str = Field(
        min_length=5,
        description="Patch objective formulated by the Cortex (1-line summary).",
    )
    context: str = Field(
        default="",
        description="Free-form context — preconditions, expected validation outcome, fallback.",
    )
    workdir: Path = Field(
        description="Sandbox root for the edits. Must exist.",
    )
    edits: list[FileEdit] = Field(
        min_length=1,
        description="Ordered edits — each ``old`` must match exactly once at apply time.",
    )
    validation_command: str | None = Field(
        default=None,
        description="Optional shell command the worker runs to validate the patched files.",
    )
    allowed_read_paths: list[Path] = Field(
        default_factory=list,
        description="Extra read-only paths. The workdir is implicitly included.",
    )
    extra_blacklist: list[str] = Field(
        default_factory=list,
        description="Task-specific blacklist regex patterns, added to the base list.",
    )

    @field_validator("workdir")
    @classmethod
    def _workdir_must_exist(cls, value: Path) -> Path:
        return _resolve_existing_workdir(value)


class CreateSpec(BaseModel):
    """Input contract for Pattern C — Cortex-supplied new file(s).

    The pattern refuses to overwrite anything; existing paths fail the call
    explicitly (DEC-008 §4). Per-file ``language`` drives the post-create
    syntax check (DEC-024 §validation).
    """

    goal: str = Field(
        min_length=5,
        description="Creation objective formulated by the Cortex.",
    )
    context: str = Field(
        default="",
        description="Free-form context — what these files are for, what failure means.",
    )
    workdir: Path = Field(
        description="Sandbox root. Must exist.",
    )
    files: list[NewFile] = Field(
        min_length=1,
        description="Ordered list of new files to create — all paths must be free.",
    )
    allowed_read_paths: list[Path] = Field(
        default_factory=list,
        description="Extra read-only paths. The workdir is implicitly included.",
    )
    extra_blacklist: list[str] = Field(
        default_factory=list,
        description="Task-specific blacklist regex patterns, added to the base list.",
    )

    @field_validator("workdir")
    @classmethod
    def _workdir_must_exist(cls, value: Path) -> Path:
        return _resolve_existing_workdir(value)
