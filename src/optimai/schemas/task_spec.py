"""Task spec schemas — input contracts for the patterns (DEC-002, DEC-006).

Phase 1 / CLI #3 scope: `DiagnoseSpec` only (Pattern A). `ExecuteSpec` (Pattern D)
is deferred to ROADMAP Phase 1 step 7.
"""

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


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
        """Resolve symlinks and require the workdir to exist (fail explicit).

        A missing path raises ValueError so Pydantic wraps it into a
        ValidationError (it does not catch raw OSError / FileNotFoundError).
        """
        try:
            return value.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(f"workdir does not exist: {value}") from exc
