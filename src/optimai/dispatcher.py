"""Single bounded worker<->shell loop, pattern-agnostic (DEC-001, DEC-007, DEC-021).

The Dispatcher is the *only* place the loop mechanics live: iteration counter,
global `asyncio.wait_for` budget, per-command timeout recovery, blacklist
enforcement, and the worker correction protocol. Every task-specific concern
(system prompt, parser, report shape) is delegated to a `Pattern` strategy
resolved from the registry.

This module must stay free of any pattern-specific import (Diagnose, Execute,
Patch, Create, ...). The Phase-2 mutation phase (DEC-024) is wired by
consulting OPTIONAL hooks via ``getattr`` — never by importing a pattern —
so the "axis 1 absorbed by the registry" claim of DEC-021 keeps holding.
"""

import asyncio
import logging

import httpx
from pydantic import BaseModel

from optimai.config import Settings, get_settings
from optimai.patterns.base import MutationResult, Pattern, Step, get_pattern
from optimai.shell import (
    BlacklistViolation,
    CommandTimeout,
    ShellError,
    is_blacklisted,
    load_blacklist,
)
from optimai.shell import run as shell_run
from optimai.snapshot import Snapshot
from optimai.worker import WorkerError, chat as worker_chat

logger = logging.getLogger(__name__)


class PatternRejected(Exception):
    """Raised when the operator-supplied text matches a blacklist pattern."""


def _per_command_timeout(global_timeout: int) -> int:
    """A single command is capped at 30 s OR the global budget, whichever is smaller.

    Matches the PoC formula. Whether a per-command timeout is recoverable is
    decided per-pattern via `Pattern.on_command_timeout` (DEC-022); the global
    budget is the real DEC-007 guard, applied by `asyncio.wait_for` around the
    loop.
    """
    return min(30, global_timeout)


def _resolve_timeout_policy(pattern: Pattern, cmd: str, step: Step) -> str:
    """Consult the pattern's per-command timeout policy. Default = abort (DEC-022).

    The safe default is enforced HERE (not in the Protocol) so a pattern that
    omits `on_command_timeout` cannot silently inherit recovery — it gets the
    prudent behavior. Anything other than the explicit string ``"recover"`` is
    treated as abort, again on the safe-default principle.
    """
    hook = getattr(pattern, "on_command_timeout", None)
    if hook is None:
        return "abort"
    try:
        decision = hook(cmd, step)
    except Exception as exc:  # noqa: BLE001 — a buggy pattern must not silently recover
        logger.warning("dispatch: on_command_timeout raised %s — defaulting to abort", exc)
        return "abort"
    return "recover" if decision == "recover" else "abort"


def _mutation_user_message(mut_result: MutationResult) -> str:
    """Engine-generic preamble that hands the diff to the worker (DEC-024).

    The pattern's ``system_prompt`` already sets the cadrage ("you validate, you
    don't re-mutate"). We only inject the diff body here so the engine stays
    agnostic of what was mutated.
    """
    files = ", ".join(str(p) for p in mut_result.files_changed) or "(none recorded)"
    diff_body = mut_result.diff.strip() or "(no textual diff)"
    return (
        "MUTATION APPLIED — the files below have been modified by deterministic "
        "code BEFORE this conversation. Your task is to VALIDATE the result, not "
        "to propose further mutations.\n\n"
        f"Files changed: {files}\n\n"
        f"DIFF:\n{diff_body}"
    )


async def _run_loop(
    pattern: Pattern,
    spec: BaseModel,
    settings: Settings,
    client: httpx.AsyncClient,
    blacklist_patterns: list,
    commands_executed: list[dict],
    iterations_used: list[int],
    mut_result: MutationResult | None = None,
) -> BaseModel:
    """Inner bounded loop. Mutates `commands_executed` / `iterations_used` in place.

    The list-wrapped `iterations_used` is so the outer wrapper can recover the
    counter on global timeout (the loop coroutine is cancelled mid-flight).

    If ``mut_result`` is provided (a mutating pattern ran ``mutate`` pre-loop),
    a generic user turn carrying the diff is appended before the loop starts so
    the worker sees the new state without the pattern having to change
    ``initial_user_message``'s signature (DEC-021).
    """
    messages: list[dict] = [
        {"role": "system", "content": pattern.system_prompt(spec)},
        {"role": "user", "content": pattern.initial_user_message(spec)},
    ]
    if mut_result is not None:
        messages.append({"role": "user", "content": _mutation_user_message(mut_result)})
    correction_used = False
    per_cmd_timeout = _per_command_timeout(settings.timeout_seconds)

    for iteration in range(1, settings.max_iterations + 1):
        iterations_used[0] = iteration
        try:
            response = await worker_chat(messages, max_tokens=768, client=client)
        except WorkerError as exc:
            logger.warning("dispatch: worker error at iter=%d: %s", iteration, exc)
            return pattern.build_report(
                final_payload=None,
                commands_executed=commands_executed,
                stop_reason="worker_error",
                iterations_used=iteration,
                status="error",
                notes=f"worker error: {exc}",
            )

        messages.append({"role": "assistant", "content": response.content})
        step = pattern.parse(response.content)
        logger.info("dispatch: iter=%d kind=%s think=%r", iteration, step.kind, step.think[:120])

        if step.kind == "command":
            cmd = step.cmd
            try:
                result = await shell_run(
                    cmd,
                    spec.workdir,  # every spec_model exposes a `workdir` field
                    patterns=blacklist_patterns,
                    timeout_seconds=per_cmd_timeout,
                    max_output_bytes=settings.max_output_bytes,
                )
            except BlacklistViolation as exc:
                logger.warning("dispatch: blacklist hit at iter=%d cmd=%r", iteration, cmd[:120])
                commands_executed.append({"cmd": cmd, "exit": -1, "stdout_truncated": False})
                return pattern.build_report(
                    final_payload=None,
                    commands_executed=commands_executed,
                    stop_reason="blacklist_violation",
                    iterations_used=iteration,
                    status="error",
                    notes=f"blacklist violation: {exc}",
                )
            except CommandTimeout as exc:
                # DEC-022: per-pattern recovery policy. Default = abort (safe).
                logger.info("dispatch: per-cmd timeout at iter=%d cmd=%r", iteration, cmd[:120])
                commands_executed.append({"cmd": cmd, "exit": -1, "stdout_truncated": False})
                policy = _resolve_timeout_policy(pattern, cmd, step)
                if policy == "recover":
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Command: {cmd}\n"
                                f"Result: TIMED OUT and was killed (per-command limit, {exc}). "
                                "Pick a faster, more targeted command — avoid scanning "
                                "large directory trees."
                            ),
                        }
                    )
                    continue
                # policy == "abort": surface the inconsistency, don't improvise.
                return pattern.build_report(
                    final_payload=None,
                    commands_executed=commands_executed,
                    stop_reason="command_timeout",
                    iterations_used=iteration,
                    status="error",
                    notes=(
                        f"command timeout (abort policy): {exc}. "
                        "State after the killed command may be inconsistent."
                    ),
                )
            except ShellError as exc:
                logger.warning("dispatch: shell error at iter=%d: %s", iteration, exc)
                commands_executed.append({"cmd": cmd, "exit": -1, "stdout_truncated": False})
                return pattern.build_report(
                    final_payload=None,
                    commands_executed=commands_executed,
                    stop_reason="shell_error",
                    iterations_used=iteration,
                    status="error",
                    notes=f"shell error: {exc}",
                )

            commands_executed.append(
                {
                    "cmd": cmd,
                    "exit": result.exit_code,
                    "stdout_truncated": result.stdout_truncated,
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Command: {cmd}\n"
                        f"Exit: {result.exit_code}\n"
                        f"STDOUT (truncated={result.stdout_truncated}):\n"
                        f"{result.stdout}\n"
                        f"STDERR:\n{result.stderr}"
                    ),
                }
            )
            continue

        if step.kind == "final":
            return pattern.build_report(
                final_payload=step.payload,
                commands_executed=commands_executed,
                stop_reason="converged",
                iterations_used=iteration,
                status="complete",
                notes=step.think,
            )

        # step.kind == "invalid" — one correction allowed, then bail.
        logger.info("dispatch: invalid worker output at iter=%d: %s", iteration, step.reason)
        if correction_used:
            return pattern.build_report(
                final_payload=None,
                commands_executed=commands_executed,
                stop_reason="worker_error",
                iterations_used=iteration,
                status="error",
                notes=f"worker produced invalid output twice: {step.reason}",
            )
        correction_used = True
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Your previous reply was not parseable ({step.reason}). "
                    "Reply again using EXACTLY the required THINK/ACTION format. "
                    "No markdown fences, no extra prose."
                ),
            }
        )

    # Loop exhausted with no final report.
    return pattern.build_report(
        final_payload=None,
        commands_executed=commands_executed,
        stop_reason="max_iterations",
        iterations_used=iterations_used[0],
        status="incomplete",
        notes="reached max_iterations without a final report",
    )


async def dispatch(
    pattern_name: str,
    spec: BaseModel,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> BaseModel:
    """Run the bounded worker<->shell loop for `pattern_name`, return its report.

    Resolves the pattern from the registry, loads the blacklist (base file +
    `spec.extra_blacklist`), vets the operator text up front (DEC-008 defense
    in depth), then runs the loop under `settings.timeout_seconds` global budget.

    If `client` is None, a single `httpx.AsyncClient` is created and shared
    across every `worker.chat` call so the KV cache and the HTTP connection
    are reused.
    """
    settings = settings or get_settings()
    pattern = get_pattern(pattern_name)

    blacklist_patterns = load_blacklist(
        settings.blacklist_file, extra_patterns=spec.extra_blacklist
    )

    operator_text = pattern.operator_text(spec)
    blocked, matched = is_blacklisted(operator_text, blacklist_patterns)
    if blocked:
        raise PatternRejected(
            f"Operator text matches blacklist pattern {matched!r}; refusing to dispatch."
        )

    commands_executed: list[dict] = []
    iterations_used: list[int] = [0]

    # DEC-024 pre-loop mutation phase. Consulted via getattr so non-mutating
    # patterns (A/D) keep the previous code path untouched — extension, not
    # refactor (DEC-021).
    snap: Snapshot | None = None
    mut_result: MutationResult | None = None
    mutate_hook = getattr(pattern, "mutate", None)
    if mutate_hook is not None:
        snap = Snapshot(spec.workdir, getattr(spec, "allowed_read_paths", []))
        try:
            mut_result = mutate_hook(spec, snap)
        except Exception as exc:  # noqa: BLE001 — any failure means atomic restore
            logger.warning("dispatch: mutate raised %s — restoring snapshot", exc)
            snap.restore()
            snap = None
            report = pattern.build_report(
                final_payload=None,
                commands_executed=[],
                stop_reason="mutation_error",
                iterations_used=0,
                status="error",
                notes=f"mutation error: {exc}",
            )
            return _maybe_enrich(pattern, report, exc)

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    try:
        try:
            report = await asyncio.wait_for(
                _run_loop(
                    pattern,
                    spec,
                    settings,
                    client,
                    blacklist_patterns,
                    commands_executed,
                    iterations_used,
                    mut_result=mut_result,
                ),
                timeout=settings.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "dispatch: global timeout after %ds (iter=%d)",
                settings.timeout_seconds,
                iterations_used[0],
            )
            report = pattern.build_report(
                final_payload=None,
                commands_executed=commands_executed,
                stop_reason="timeout",
                iterations_used=iterations_used[0],
                status="incomplete",
                notes=f"global timeout after {settings.timeout_seconds}s",
            )
    finally:
        if owns_client:
            await client.aclose()

    # DEC-024 atomicity: any error after mutation means the loop did not
    # validate the mutated state — revert files to their pre-call bytes.
    if snap is not None:
        if report.status == "error":
            logger.info("dispatch: report.status=error — restoring snapshot")
            snap.restore()
        else:
            snap.cleanup()

    return _maybe_enrich(pattern, report, mut_result)


def _maybe_enrich(pattern: Pattern, report: BaseModel, outcome) -> BaseModel:
    """Optional pattern hook: stamp mutation fields onto the typed report.

    ``outcome`` is either a ``MutationResult`` (success), an ``Exception``
    (mutate raised), or ``None`` (non-mutating pattern). Consulted via
    ``getattr`` — A/D stay untouched (DEC-021 extension principle).
    """
    if outcome is None:
        return report
    hook = getattr(pattern, "enrich_report", None)
    if hook is None:
        return report
    try:
        return hook(report, outcome)
    except Exception as exc:  # noqa: BLE001 — never let enrichment crash the dispatch
        logger.error("dispatch: enrich_report raised %s — returning bare report", exc)
        return report


__all__ = ["dispatch", "PatternRejected"]
