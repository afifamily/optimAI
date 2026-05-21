"""Pattern contract + registry — the extensibility seam of the Dispatcher (DEC-021).

A `Pattern` is a thin strategy: it owns the system prompt, the user-facing
intro, the worker-output parser, and the report builder for one kind of task
(Diagnose, Execute, ...). The Dispatcher's loop is pattern-agnostic — it
consumes `Step` values produced by `Pattern.parse` and hands the trace back to
`Pattern.build_report` to fabricate the typed report.

Adding a new pattern = new file under `patterns/` + `@register("name")`. The
Dispatcher and the future MCP server iterate the registry; no central list.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

StepKind = Literal["command", "final", "invalid"]
TimeoutPolicy = Literal["recover", "abort"]


@dataclass(frozen=True)
class Step:
    """One decision made by the worker at a single turn.

    Kept opaque to the Dispatcher beyond `kind` and `cmd`:
      - `kind="command"` — execute `cmd`; `think` is informational.
      - `kind="final"`   — the worker has converged; `payload` carries the
        pattern-specific fields that `build_report` will consume.
      - `kind="invalid"` — the worker reply could not be parsed; `reason`
        explains why so the Dispatcher can request a correction.
    """

    kind: StepKind
    think: str = ""
    cmd: str = ""
    payload: dict | None = None
    reason: str = ""


@runtime_checkable
class Pattern(Protocol):
    """The contract every pattern strategy must satisfy."""

    name: str
    spec_model: type[BaseModel]

    def system_prompt(self, spec: BaseModel) -> str:
        """Cadrage + protocole — must NOT contain task-specific domain knowledge.

        Per DEC-021 (Cortex<->Hands contract), domain knowledge for the specific
        instance lives in `spec.context`, not in the prompt itself.
        """
        ...

    def initial_user_message(self, spec: BaseModel) -> str:
        """The first user turn — typically wraps `spec.goal` + `spec.context`."""
        ...

    def operator_text(self, spec: BaseModel) -> str:
        """Text vetted against the blacklist before reaching the worker.

        Defense in depth (DEC-008): the high-level operator instruction is the
        prompt-injection-style vector worth scrubbing pre-flight. `spec.context`
        is intentionally allowed to mention sensitive tokens (domain knowledge).
        """
        ...

    def parse(self, worker_text: str) -> Step:
        """Turn a raw worker reply into a `Step` the Dispatcher can act on."""
        ...

    def build_report(
        self,
        *,
        final_payload: dict | None,
        commands_executed: list[dict],
        stop_reason: str,
        iterations_used: int,
        status: Literal["complete", "incomplete", "error"],
        notes: str,
    ) -> BaseModel:
        """Fabricate the typed report. `final_payload` is set iff status=complete."""
        ...

    def on_command_timeout(self, cmd: str, step: Step) -> TimeoutPolicy:
        """Recovery policy when one shell command exceeds its per-cmd budget (DEC-022).

        Returning ``"recover"`` lets the dispatcher reinject "TIMED OUT" and
        continue the loop (Diagnose-style: read-only commands, no side effects
        to worry about). Returning ``"abort"`` makes the dispatcher stop and
        produce an error report (Execute-style: mutating commands may have
        left partial side effects — surfacing the inconsistency beats
        improvising on an unknown state).

        DEC-022 invariant: a pattern that does NOT implement this hook gets
        ``"abort"`` from the dispatcher, never silent recovery.
        """
        ...


_REGISTRY: dict[str, Pattern] = {}


def register(name: str):
    """Class decorator: instantiate and register the pattern under `name`.

    The decorator stores an instance (patterns are stateless strategies), so
    `get_pattern("diagnose")` returns the same object each call.
    """

    def deco(cls):
        instance = cls()
        # The instance's `name` attr must match the registration key — a guard
        # against typos like @register("diagnose") on a class with name="diagonse".
        declared = getattr(instance, "name", None)
        if declared != name:
            raise ValueError(
                f"Pattern class {cls.__name__} declares name={declared!r} "
                f"but is registered as {name!r}"
            )
        _REGISTRY[name] = instance
        return cls

    return deco


def get_pattern(name: str) -> Pattern:
    """Return the registered pattern or raise `KeyError` (DEC-008 §4, no fallback)."""
    if name not in _REGISTRY:
        available = sorted(_REGISTRY)
        raise KeyError(f"Unknown pattern {name!r}. Available: {available}")
    return _REGISTRY[name]


def available_patterns() -> list[str]:
    """Sorted list of registered pattern names — source of truth for MCP tools."""
    return sorted(_REGISTRY)
