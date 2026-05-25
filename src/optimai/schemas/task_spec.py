"""Task spec schemas — input contracts for the patterns (DEC-002, DEC-006)."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


# --------------------------------------------------------------------------
# Phase 3 — Pattern E (Scan/Audit) — DEC-025, DEC-026
# --------------------------------------------------------------------------

ScanTargetKind = Literal["fs", "http"]


class ScanTarget(BaseModel):
    """One target the worker must scan (DEC-025).

    Two kinds: ``fs`` (a sub-path under the sandbox, grep'd locally) or
    ``http`` (a URL whose GET response body is grep'd). HTTP is read-only —
    a ``GET`` is bénin and explicitly allowed by DEC-008/DEC-025; the
    blacklist still catches télécharge-puis-exécute shapes.
    """

    kind: ScanTargetKind = Field(description="Source family — fs or http.")
    ref: str = Field(min_length=1, description="Filesystem ref or URL, depending on kind.")

    @model_validator(mode="after")
    def _ref_shape(self):
        if not self.ref.strip():
            raise ValueError("target ref must not be blank")
        if self.kind == "http":
            lower = self.ref.lower()
            if not (lower.startswith("http://") or lower.startswith("https://")):
                raise ValueError(
                    f"http target ref must start with http:// or https://: {self.ref!r}"
                )
        return self


class ScanSpec(BaseModel):
    """Input contract for Pattern E — Cortex-supplied scan/audit (DEC-025, DEC-026).

    Cortex-sourced: the patterns and targets come from the Cortex. The worker
    runs ``grep``/``curl`` to collect occurrences, then formulates a pass/fail
    verdict. Read-only by design (DEC-022 → ``recover`` timeout policy).

    Secret invariant (DEC-026): ``secret_patterns`` declares values whose
    *literal occurrences* must be stripped from every outgoing field — report
    and log alike. The dispatcher consults this field via ``getattr`` as a
    generic engine step; patterns A/D/B/C do not declare it and are unaffected.
    """

    goal: str = Field(
        min_length=5,
        description="Scan objective formulated by the Cortex.",
    )
    context: str = Field(
        default="",
        description="Free-form context — what 'pass' means, what a leak would look like.",
    )
    workdir: Path = Field(
        description="Sandbox root for fs scans. Must exist.",
    )
    required: list[str] = Field(
        default_factory=list,
        description="Patterns that MUST be present in the targets. Missing → fail.",
    )
    forbidden: list[str] = Field(
        default_factory=list,
        description="Patterns that MUST be absent. Any occurrence → fail.",
    )
    secret_patterns: list[str] = Field(
        default_factory=list,
        description="Subset of patterns whose literal value is a secret. "
        "Their values are redacted from every outgoing report field and from "
        "logs (DEC-026). Pass the value verbatim — the dispatcher handles the "
        "redaction generically.",
    )
    targets: list[ScanTarget] = Field(
        min_length=1,
        description="Sources to scan — at least one fs or http target.",
    )
    allowed_read_paths: list[Path] = Field(
        default_factory=list,
        description="Extra read-only paths beyond workdir. fs targets must live "
        "inside workdir or one of these.",
    )
    extra_blacklist: list[str] = Field(
        default_factory=list,
        description="Task-specific blacklist regex patterns, added to the base list.",
    )

    @field_validator("workdir")
    @classmethod
    def _workdir_must_exist(cls, value: Path) -> Path:
        return _resolve_existing_workdir(value)

    @model_validator(mode="after")
    def _at_least_one_pattern_register(self):
        if not (self.required or self.forbidden or self.secret_patterns):
            raise ValueError(
                "at least one of required / forbidden / secret_patterns must be non-empty"
            )
        return self
