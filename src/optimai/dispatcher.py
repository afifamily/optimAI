"""Single bounded worker<->shell loop, pattern-agnostic (DEC-001, DEC-007, DEC-021).

The Dispatcher is the *only* place the loop mechanics live: iteration counter,
global `asyncio.wait_for` budget, per-command timeout recovery, blacklist
enforcement, and the worker correction protocol. Every task-specific concern
(system prompt, parser, report shape) is delegated to a `Pattern` strategy
resolved from the registry.

This module must stay free of any pattern-specific import (Diagnose, Execute,
Patch, Create, Scan, ...). The Phase-2 mutation phase (DEC-024) is wired by
consulting OPTIONAL hooks via ``getattr`` — never by importing a pattern —
so the "axis 1 absorbed by the registry" claim of DEC-021 keeps holding.

DEC-026 (Phase 3): a generic redaction step strips literal occurrences of every
``spec.secret_patterns`` value from the outgoing report AND from log records,
covering the three leak vectors (matches/text fields, ``commands_executed[].cmd``,
free-form notes). The engine reads ``secret_patterns`` via ``getattr`` so patterns
without that field (A/D/B/C today) are entirely unaffected.
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


# --------------------------------------------------------------------------
# DEC-026 — secret-value redaction (generic engine step)
# --------------------------------------------------------------------------


def _collect_secret_values(spec: BaseModel) -> list[str]:
    """Return the deduplicated, non-empty ``secret_patterns`` from ``spec``.

    Reads via ``getattr`` so any pattern's spec that lacks the field (A/D/B/C
    today) yields an empty list and turns the redaction step inert — the
    Open/Closed extension principle of DEC-021.
    """
    raw = getattr(spec, "secret_patterns", []) or []
    seen: list[str] = []
    for value in raw:
        if isinstance(value, str) and value and value not in seen:
            seen.append(value)
    return seen


def _redact_string(value: str, placeholders: list[tuple[str, str]]) -> str:
    """Replace every literal secret in ``value`` with its stable placeholder.

    Order matters when one secret is a substring of another — we apply the
    longer values first so partial replacements never strand a fragment of a
    longer secret in the output.
    """
    out = value
    for secret, placeholder in placeholders:
        if secret in out:
            out = out.replace(secret, placeholder)
    return out


def _redact_walk(node, placeholders: list[tuple[str, str]]):
    """Walk ``node`` recursively, redacting every str leaf.

    Built for the shape produced by ``BaseModel.model_dump()``: strings, ints,
    None, lists, dicts. Non-string leaves are returned unchanged.
    """
    if isinstance(node, str):
        return _redact_string(node, placeholders)
    if isinstance(node, list):
        return [_redact_walk(v, placeholders) for v in node]
    if isinstance(node, dict):
        return {k: _redact_walk(v, placeholders) for k, v in node.items()}
    return node


def _redact_report(report: BaseModel, secrets: list[str]) -> BaseModel:
    """Strip every literal secret value from every string field of ``report``.

    Single engine-generic pass — does not know the report's shape, so it covers
    A/D/B/C/E uniformly and any future report's text fields without a code
    change here. Returns a freshly validated instance so callers (and FastMCP
    serialization downstream) see the redacted bytes.

    Defensive assertion: after redaction, the serialized form must not contain
    any literal secret (DEC-026 §4 — explicit failure beats silent leak).
    """
    if not secrets:
        return report
    placeholders = [
        (s, f"<secret:{i + 1}>")
        # Sort the (secret, placeholder) pairs so longer secrets are applied
        # first while keeping the index assignment stable.
        for i, s in enumerate(secrets)
    ]
    placeholders.sort(key=lambda pair: len(pair[0]), reverse=True)

    redacted = _redact_walk(report.model_dump(), placeholders)
    rebuilt = type(report).model_validate(redacted)

    serialized = rebuilt.model_dump_json()
    for secret in secrets:
        if secret and secret in serialized:
            raise AssertionError(
                "DEC-026 redaction failed: a declared secret value survives in the report"
            )
    return rebuilt


class _SecretLogFilter(logging.Filter):
    """Logging filter that scrubs declared secret values from records in flight.

    Attached to every handler on the ``optimai`` package logger for the
    lifetime of a single ``dispatch()`` call. We mutate ``record.msg`` and
    drop ``record.args`` after rendering the final message so propagation
    cannot re-expose the value via lazy formatting.
    """

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        sorted_secrets = sorted(secrets, key=len, reverse=True)
        self._placeholders = [
            (s, f"<secret:{secrets.index(s) + 1}>") for s in sorted_secrets
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:  # noqa: BLE001 — never let a logging quirk kill dispatch
            return True
        if not any(s in rendered for s, _ in self._placeholders):
            return True
        record.msg = _redact_string(rendered, self._placeholders)
        record.args = ()
        return True


def _attach_log_redaction(secrets: list[str]) -> _SecretLogFilter | None:
    """Install a log filter on every handler of the ``optimai`` package logger.

    Handler-level (not logger-level) so records propagated up from child
    loggers like ``optimai.shell`` / ``optimai.worker`` are scrubbed too —
    the optimai package logger is where ``_configure_logging`` wires the
    file + stderr handlers (server.py).
    """
    if not secrets:
        return None
    filter_obj = _SecretLogFilter(secrets)
    pkg_logger = logging.getLogger("optimai")
    for handler in pkg_logger.handlers:
        handler.addFilter(filter_obj)
    return filter_obj


def _detach_log_redaction(filter_obj: _SecretLogFilter | None) -> None:
    if filter_obj is None:
        return
    pkg_logger = logging.getLogger("optimai")
    for handler in pkg_logger.handlers:
        handler.removeFilter(filter_obj)


def _per_command_timeout(global_timeout: int) -> int:
    """A single command is capped at 30 s OR the global budget, whichever is smaller.

    Matches the PoC formula. Whether a per-command timeout is recoverable is
    decided per-pattern via `Pattern.on_command_timeout` (DEC-022); the global
    budget is the real DEC-007 guard, applied by `asyncio.wait_for` around the
    loop.
    """
    return min(30, global_timeout)


def _failed_validation_entry(
    pattern: Pattern, spec: BaseModel, commands_executed: list[dict]
) -> dict | None:
    """Layer 1 — deterministic guard (DEC-024 amended).

    Scan the executed commands; return the first one that the pattern
    designates as a validation command AND that exited non-zero. The pattern's
    ``is_validation_command`` hook is OPTIONAL — when absent (A/D, or any
    pattern without a notion of validation), the guard is silently inert and
    the loop keeps the legacy "converged ⇒ complete" behavior.

    A buggy hook (raising) is treated as "not a validation command" for that
    entry — better to keep the worker's verdict than to crash the dispatch on
    a faulty pattern. The hook MUST NOT have side effects (engine calls it
    once per entry).
    """
    hook = getattr(pattern, "is_validation_command", None)
    if hook is None:
        return None
    for entry in commands_executed:
        if entry["exit"] == 0:
            continue
        try:
            if hook(entry["cmd"], spec):
                return entry
        except Exception as exc:  # noqa: BLE001 — never let a buggy hook crash dispatch
            logger.warning(
                "dispatch: is_validation_command raised %s on cmd=%r — treating as non-validation",
                exc,
                entry["cmd"][:120],
            )
    return None


def _worker_declared_failure(pattern: Pattern, payload: dict | None) -> bool:
    """Layer 2 — worker additive (DEC-024 amended).

    Optional hook lets a pattern downgrade a converged report to ``"error"``
    when the worker's payload semantically indicates failure even on exit 0
    (e.g. ``failed_edit`` populated, a ``result=fail`` marker). Only consulted
    when Layer 1 did not fire — the invariant "deterministic guard prime" is
    enforced by the call order in ``_run_loop``, not by the hook itself.
    """
    hook = getattr(pattern, "worker_declares_failure", None)
    if hook is None or payload is None:
        return False
    try:
        return bool(hook(payload))
    except Exception as exc:  # noqa: BLE001 — buggy hook must not flip a complete to error
        logger.warning("dispatch: worker_declares_failure raised %s — keeping complete", exc)
        return False


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
            # DEC-024 amended — status-of-failure cascade:
            #   Layer 1 (deterministic guard, non-overridable): if the pattern
            #     designates a validation command and it exited non-zero, force
            #     status="error" regardless of what the worker reports.
            #   Layer 2 (worker additive, optional): on exit 0 the worker may
            #     declare a semantic failure (e.g. test "passes" by skipping).
            # The cascade order enforces the invariant by construction — the
            # worker can only ADD a failure, never subtract a deterministic one.
            failed_val = _failed_validation_entry(pattern, spec, commands_executed)
            if failed_val is not None:
                return pattern.build_report(
                    final_payload=step.payload,
                    commands_executed=commands_executed,
                    stop_reason="converged",
                    iterations_used=iteration,
                    status="error",
                    notes=(
                        f"validation command failed (deterministic guard): "
                        f"{failed_val['cmd']!r} exited {failed_val['exit']}. "
                        f"Worker said: {step.think}"
                    ),
                )
            status = "error" if _worker_declared_failure(pattern, step.payload) else "complete"
            notes = step.think if status == "complete" else (
                f"worker declared semantic failure on exit 0. {step.think}"
            )
            return pattern.build_report(
                final_payload=step.payload,
                commands_executed=commands_executed,
                stop_reason="converged",
                iterations_used=iteration,
                status=status,
                notes=notes,
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

    # DEC-026: declare secret values BEFORE the loop runs so log records emitted
    # by shell / worker / dispatcher get scrubbed in flight on their way to the
    # file handler. The redaction step on the report itself runs at the end,
    # after enrich_report — see _redact_report.
    secret_values = _collect_secret_values(spec)
    log_filter = _attach_log_redaction(secret_values)

    commands_executed: list[dict] = []
    iterations_used: list[int] = [0]

    try:
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
                enriched = _maybe_enrich(pattern, report, exc)
                return _redact_report(enriched, secret_values)

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

        enriched = _maybe_enrich(pattern, report, mut_result)
        # DEC-026: redact BEFORE returning. The log filter has already scrubbed
        # whatever the loop emitted in flight; redacting the report is the
        # second leg covering the Cortex-side return.
        return _redact_report(enriched, secret_values)
    finally:
        _detach_log_redaction(log_filter)


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
