"""Sandboxed shell execution with blacklist enforcement (DEC-008).

The most security-sensitive module of the project. Four layers of protection
(DEC-008):

  1. Blacklist — regex patterns refused before execution.
  2. Path sandbox — the subprocess `cwd` is pinned to the task workdir.
  3. Explicit env — no parent secrets propagate to the subprocess.
  4. Output truncation — capped at `max_output_bytes` (DEC-007).

Phase 1 applies the sandbox to the subprocess working directory only; static
analysis of `/bin/sh -c` argument paths is explicitly Phase 4 (DEC-008
"Évolution prévue").
"""

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class ShellError(Exception):
    """Base class for shell execution failures."""


class BlacklistViolation(ShellError):
    """Raised when a command matches a blacklist pattern (DEC-008 §1)."""


class SandboxViolation(ShellError):
    """Raised when a path resolves outside the sandbox (DEC-008 §2)."""


class CommandTimeout(ShellError):
    """Raised when a command exceeds its time budget (DEC-007)."""


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a single sandboxed command execution."""

    cmd: str
    exit_code: int
    stdout: str  # Truncated to max_output_bytes.
    stderr: str  # Truncated to max_output_bytes.
    stdout_truncated: bool
    stderr_truncated: bool
    duration_seconds: float


def load_blacklist(
    path: Path, extra_patterns: list[str] | None = None
) -> list[re.Pattern]:
    """Compile blacklist regex patterns from `path` plus any `extra_patterns`.

    File format: one regex per line; blank lines and `#`-comments are ignored.
    An invalid regex raises `ShellError` at load time, not at runtime.
    """
    compiled: list[re.Pattern] = []
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            compiled.append(re.compile(stripped))
        except re.error as exc:
            raise ShellError(
                f"Invalid blacklist regex at {path}:{lineno}: {stripped!r} ({exc})"
            ) from exc

    for extra in extra_patterns or []:
        try:
            compiled.append(re.compile(extra))
        except re.error as exc:
            raise ShellError(f"Invalid extra blacklist regex: {extra!r} ({exc})") from exc

    logger.info("Loaded %d blacklist patterns from %s", len(compiled), path)
    return compiled


def is_blacklisted(cmd: str, patterns: list[re.Pattern]) -> tuple[bool, str]:
    """Return (True, matching_pattern) if `cmd` is blacklisted, else (False, '').

    Uses `pattern.search` so a forbidden token is caught anywhere in the command.
    """
    for pattern in patterns:
        if pattern.search(cmd):
            return True, pattern.pattern
    return False, ""


def validate_path_in_sandbox(
    target: Path, workdir: Path, allowed_read_paths: list[Path]
) -> None:
    """Raise `SandboxViolation` if `target` resolves outside the sandbox.

    The sandbox is the workdir plus any explicitly allowed read paths. Symlinks
    are followed via `resolve(strict=False)` so a symlink escape is caught.
    """
    resolved = target.resolve(strict=False)
    roots = [workdir.resolve(strict=False)] + [
        p.resolve(strict=False) for p in allowed_read_paths
    ]
    if any(resolved.is_relative_to(root) for root in roots):
        return
    raise SandboxViolation(
        f"Path {resolved} is outside the sandbox (workdir={workdir}, "
        f"allowed={allowed_read_paths})"
    )


def _truncate(data: bytes, max_bytes: int) -> tuple[str, bool]:
    """Decode `data` to str, truncating to `max_bytes` with a visible marker."""
    if len(data) <= max_bytes:
        return data.decode("utf-8", errors="replace"), False
    overflow = len(data) - max_bytes
    head = data[:max_bytes].decode("utf-8", errors="replace")
    return f"{head}\n... [TRUNCATED: {overflow} more bytes]", True


def _build_env(workdir: Path, env: dict[str, str] | None) -> dict[str, str]:
    """Build a minimal subprocess environment — no parent secrets (DEC-008 §3).

    Only PATH/HOME/LANG are carried over from the parent. Any variable holding
    a TOKEN/KEY/SECRET/PASSWORD therefore never reaches the subprocess.
    """
    base_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": os.environ.get("HOME", str(workdir)),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }
    if env:
        # WARNING: caller-supplied env is trusted (resolved by the Dispatcher).
        # The parent process environment is never inherited.
        base_env.update(env)
    return base_env


async def run(
    cmd: str,
    workdir: Path,
    *,
    patterns: list[re.Pattern],
    timeout_seconds: int,
    max_output_bytes: int,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Execute `cmd` via `/bin/sh -c` with strict sandboxing (DEC-008, DEC-007).

    Raises `BlacklistViolation` *before* execution if the command is forbidden,
    `CommandTimeout` if it exceeds `timeout_seconds`.
    """
    # WARNING: blacklist check happens before any subprocess is spawned.
    blocked, matched = is_blacklisted(cmd, patterns)
    if blocked:
        raise BlacklistViolation(f"Command blocked by pattern {matched!r}: {cmd}")

    workdir = workdir.resolve(strict=True)
    logger.info("shell.run start: cmd=%r workdir=%s", cmd[:200], workdir)

    proc_env = _build_env(workdir, env)
    started = time.monotonic()
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=str(workdir),
        env=proc_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        duration = time.monotonic() - started
        logger.info("shell.run timeout: cmd=%r after %.2fs", cmd[:200], duration)
        raise CommandTimeout(f"Command exceeded {timeout_seconds}s: {cmd}") from exc

    duration = time.monotonic() - started
    stdout, stdout_truncated = _truncate(stdout_b, max_output_bytes)
    stderr, stderr_truncated = _truncate(stderr_b, max_output_bytes)
    exit_code = proc.returncode if proc.returncode is not None else -1

    logger.info(
        "shell.run done: exit=%d duration=%.2fs stdout_truncated=%s stderr_truncated=%s",
        exit_code,
        duration,
        stdout_truncated,
        stderr_truncated,
    )
    # DEBUG only, first 200 chars — full output may contain user secrets.
    logger.debug("shell.run stdout[:200]=%r", stdout[:200])

    return CommandResult(
        cmd=cmd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        duration_seconds=duration,
    )
