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
