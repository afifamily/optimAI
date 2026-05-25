"""Report schemas — compressed structured output returned to the Cortex (DEC-002)."""

from typing import Literal

from pydantic import BaseModel, Field

StopReason = Literal[
    "converged",
    "max_iterations",
    "timeout",
    "command_timeout",  # DEC-022: per-command timeout under an "abort" policy
    "blacklist_violation",
    "sandbox_violation",
    "worker_error",
    "shell_error",
    "mutation_error",  # DEC-024: pre-loop mutation refused / failed → snapshot restored
]


class DiagnoseReport(BaseModel):
    """Structured verdict of a Pattern A investigation (DEC-006).

    Field order: most important first. `root_cause` and the fixes are None
    whenever the loop did not converge to a firm conclusion.
    """

    status: Literal["complete", "incomplete", "error"] = Field(
        description="complete = firm conclusion; incomplete = limit hit (DEC-007); "
        "error = crash / guardrail violation.",
    )
    root_cause: str | None = Field(
        default=None,
        description="Identified root cause. None when status is incomplete/error.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Observations proving the root cause (command + output excerpt).",
    )
    temporary_fix: str | None = Field(
        default=None,
        description="Short-term command or action to unblock.",
    )
    permanent_fix: str | None = Field(
        default=None,
        description="Long-term recommendation.",
    )
    iterations_used: int = Field(
        default=0,
        ge=0,
        description="Number of loop iterations consumed.",
    )
    stop_reason: StopReason = Field(
        description="Why the orchestration loop stopped.",
    )
    commands_executed: list[dict] = Field(
        default_factory=list,
        description='Trace of every command: {"cmd", "exit", "stdout_truncated"}.',
    )
    notes: str = Field(
        default="",
        max_length=1024,
        description="Free-form worker notes (<= 1 KB).",
    )


class PatchReport(BaseModel):
    """Structured outcome of a Pattern B deterministic patch (DEC-006, DEC-024).

    Compact like ExecuteReport: ``diff`` carries the applied edit (or ``None``
    when the mutation failed pre-validation), ``failed_edit`` names the offender
    on rollback (no-match / multi-match / validation error).
    """

    status: Literal["complete", "incomplete", "error"] = Field(
        description="complete = patch applied AND validated; incomplete = limit "
        "hit (DEC-007); error = mutation refused, validation failed, or guardrail tripped.",
    )
    summary: str | None = Field(
        default=None,
        max_length=1024,
        description="One-line worker verdict (validation outcome, what broke if any).",
    )
    diff: str | None = Field(
        default=None,
        description="Unified diff of the applied edits (None when mutation was rejected).",
    )
    files_changed: list[str] = Field(
        default_factory=list,
        description="Paths that were patched. Empty on mutation_error.",
    )
    failed_edit: str | None = Field(
        default=None,
        description='Description of the offending edit, e.g. "<path>: old not found" / '
        '"<path>: matched 3 times".',
    )
    iterations_used: int = Field(
        default=0,
        ge=0,
        description="Number of loop iterations consumed by the validation phase.",
    )
    stop_reason: StopReason = Field(
        description="Why the orchestration loop stopped.",
    )
    commands_executed: list[dict] = Field(
        default_factory=list,
        description='Trace of every validation command: {"cmd", "exit", "stdout_truncated"}.',
    )
    notes: str = Field(
        default="",
        max_length=1024,
        description="Free-form worker notes (<= 1 KB).",
    )


class CreateReport(BaseModel):
    """Structured outcome of a Pattern C deterministic creation (DEC-006, DEC-024).

    Mirrors PatchReport but speaks the create vocabulary: ``files_created`` lists
    what was written, ``failed_file`` names a refused/invalid one on rollback.
    """

    status: Literal["complete", "incomplete", "error"] = Field(
        description="complete = files created AND syntax-validated; incomplete = limit "
        "hit; error = path collision, validation failed, or guardrail tripped.",
    )
    summary: str | None = Field(
        default=None,
        max_length=1024,
        description="One-line worker verdict.",
    )
    files_created: list[str] = Field(
        default_factory=list,
        description="Paths actually written. Empty on mutation_error.",
    )
    failed_file: str | None = Field(
        default=None,
        description='Description of the offender, e.g. "<path>: already exists" / '
        '"<path>: syntax check failed".',
    )
    iterations_used: int = Field(
        default=0,
        ge=0,
        description="Number of loop iterations consumed.",
    )
    stop_reason: StopReason = Field(
        description="Why the orchestration loop stopped.",
    )
    commands_executed: list[dict] = Field(
        default_factory=list,
        description='Trace of every validation command: {"cmd", "exit", "stdout_truncated"}.',
    )
    notes: str = Field(
        default="",
        max_length=1024,
        description="Free-form worker notes (<= 1 KB).",
    )


class ScanMatch(BaseModel):
    """One occurrence found during a Pattern E scan (DEC-025).

    ``text`` and ``pattern`` are subject to DEC-026 redaction when ``pattern``
    is declared as a secret in the spec; the dispatcher walks the whole report
    generically before it leaves, so this model carries no redaction logic of
    its own.
    """

    target: str = Field(description="The fs path or URL the match was found in.")
    line: int | None = Field(
        default=None,
        description="Line number for fs targets (None for http, or when unknown).",
    )
    text: str = Field(description="Matched line / excerpt.")
    pattern: str = Field(description="The input pattern that matched.")


class ScanReport(BaseModel):
    """Structured outcome of a Pattern E scan/audit (DEC-025, DEC-026).

    Distinct report shape: ``matches`` + ``verdict`` is the Cortex-actionable
    information (cf. PATTERN_CANDIDATES.md — what makes E a pattern in its own
    right rather than an A/D usage). DEC-026 redaction acts on the existing
    ``text``/``pattern`` / ``commands_executed[].cmd`` / ``notes`` fields; no
    new field is needed for it.
    """

    status: Literal["complete", "incomplete", "error"] = Field(
        description="complete = scan ran to convergence; incomplete = limit hit; "
        "error = guardrail / shell / worker failure.",
    )
    verdict: Literal["pass", "fail"] | None = Field(
        default=None,
        description="pass = all required present AND no forbidden found. "
        "None when status is not 'complete'.",
    )
    matches: list[ScanMatch] = Field(
        default_factory=list,
        description="Occurrences the worker reported (post-redaction for secret patterns).",
    )
    missing_required: list[str] = Field(
        default_factory=list,
        description="Required patterns that were not found in any target.",
    )
    patterns_checked: int = Field(
        default=0,
        ge=0,
        description="Number of input patterns the worker confirms it scanned for.",
    )
    iterations_used: int = Field(
        default=0,
        ge=0,
        description="Number of loop iterations consumed.",
    )
    stop_reason: StopReason = Field(
        description="Why the orchestration loop stopped.",
    )
    commands_executed: list[dict] = Field(
        default_factory=list,
        description='Trace of every command: {"cmd", "exit", "stdout_truncated"}.',
    )
    notes: str = Field(
        default="",
        max_length=1024,
        description="Free-form worker notes (<= 1 KB).",
    )


class ExecuteReport(BaseModel):
    """Structured outcome of a Pattern D bounded-pack execution (DEC-006).

    Intentionally compact: the Cortex consumes the summary + failed_command +
    the per-command exit trace; full stdout/stderr never travel up.
    """

    status: Literal["complete", "incomplete", "error"] = Field(
        description="complete = worker delivered a verdict; incomplete = limit "
        "hit (DEC-007); error = abort (blacklist, shell, command_timeout, etc.).",
    )
    summary: str | None = Field(
        default=None,
        max_length=1024,
        description="One-line worker verdict (what was accomplished or what broke).",
    )
    failed_command: str | None = Field(
        default=None,
        description="The pack command that failed or was aborted, if any.",
    )
    iterations_used: int = Field(
        default=0,
        ge=0,
        description="Number of loop iterations consumed.",
    )
    stop_reason: StopReason = Field(
        description="Why the orchestration loop stopped.",
    )
    commands_executed: list[dict] = Field(
        default_factory=list,
        description='Trace of every command: {"cmd", "exit", "stdout_truncated"}.',
    )
    notes: str = Field(
        default="",
        max_length=1024,
        description="Free-form worker notes (<= 1 KB).",
    )
