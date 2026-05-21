"""Task spec schemas — input contracts for the patterns (DEC-002, DEC-006)."""

from pathlib import Path

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
