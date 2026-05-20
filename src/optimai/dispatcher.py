"""Single bounded worker<->shell loop, pattern-agnostic (DEC-001, DEC-007, DEC-021).

The Dispatcher is the *only* place the loop mechanics live: iteration counter,
global `asyncio.wait_for` budget, per-command timeout recovery, blacklist
enforcement, and the worker correction protocol. Every task-specific concern
(system prompt, parser, report shape) is delegated to a `Pattern` strategy
resolved from the registry.

This module must stay free of any Diagnose/Execute-specific import — that
invariant is what makes DEC-021's "axis 1 absorbed by the registry" claim hold.
"""

import asyncio
import logging

import httpx
from pydantic import BaseModel

from optimai.config import Settings, get_settings
from optimai.patterns.base import Pattern, get_pattern
from optimai.shell import (
    BlacklistViolation,
    CommandTimeout,
    ShellError,
    is_blacklisted,
    load_blacklist,
)
from optimai.shell import run as shell_run
from optimai.worker import WorkerError, chat as worker_chat

logger = logging.getLogger(__name__)


class PatternRejected(Exception):
    """Raised when the operator-supplied text matches a blacklist pattern."""


def _per_command_timeout(global_timeout: int) -> int:
    """A single command is capped at 30 s OR the global budget, whichever is smaller.

    Matches the PoC formula. The per-command cap is *recoverable* (the loop
    reinjects the timeout into context and continues); the global budget is
    the real DEC-007 guard, applied by `asyncio.wait_for` around the loop.
    """
    return min(30, global_timeout)


async def _run_loop(
    pattern: Pattern,
    spec: BaseModel,
    settings: Settings,
    client: httpx.AsyncClient,
    blacklist_patterns: list,
    commands_executed: list[dict],
    iterations_used: list[int],
) -> BaseModel:
    """Inner bounded loop. Mutates `commands_executed` / `iterations_used` in place.

    The list-wrapped `iterations_used` is so the outer wrapper can recover the
    counter on global timeout (the loop coroutine is cancelled mid-flight).
    """
    messages: list[dict] = [
        {"role": "system", "content": pattern.system_prompt(spec)},
        {"role": "user", "content": pattern.initial_user_message(spec)},
    ]
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
                # Per-command cap is recoverable (DEC-007): tell the worker, loop on.
                logger.info("dispatch: per-cmd timeout at iter=%d cmd=%r", iteration, cmd[:120])
                commands_executed.append({"cmd": cmd, "exit": -1, "stdout_truncated": False})
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

    return report


__all__ = ["dispatch", "PatternRejected"]
