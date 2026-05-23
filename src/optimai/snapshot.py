"""Intra-call atomicity helper (DEC-024) — copy-based snapshot/restore, no git.

A `Snapshot` records the pre-mutation state of files inside the sandbox so a
failed mutation can be reverted to the byte. Used by patterns B/C: the engine
opens a snapshot before calling `Pattern.mutate`, and either:

- restores it (any exception in mutate; or final report.status == "error"), or
- cleans it up (success path, freeing the temp copies).

The helper is generic: callers register paths via ``protect()`` before touching
them. ``protect()`` works for files that already exist (restored by copying the
backup back) and for files about to be created (restored by deletion + cleanup
of any ancestor directories that did not exist pre-call).

Sandbox enforcement (DEC-008 §2): every protected path must resolve inside the
workdir or one of the allowed read paths; symlinks are rejected outright to
avoid surprises across sandbox boundaries.
"""

import logging
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from optimai.shell import SandboxViolation, validate_path_in_sandbox

logger = logging.getLogger(__name__)


@dataclass
class _Record:
    """One snapshotted path + its restore plan."""

    backup: Path | None  # None ⇒ path didn't exist pre-call (creation)
    missing_ancestors: list[Path] = field(default_factory=list)


class Snapshot:
    """Sandbox-checked file snapshot. Methods are intentionally synchronous —
    snapshot work is local I/O on a few small files, not worth an event loop hop.
    """

    def __init__(self, workdir: Path, allowed_read_paths: list[Path] | None = None) -> None:
        self._workdir = workdir.resolve(strict=False)
        self._allowed = [p.resolve(strict=False) for p in allowed_read_paths or []]
        self._tmp_root = Path(tempfile.mkdtemp(prefix="optimai-snap-"))
        self._records: dict[Path, _Record] = {}
        self._closed = False

    @property
    def tmp_root(self) -> Path:
        return self._tmp_root

    def protect(self, path: Path) -> None:
        """Snapshot ``path`` before it is mutated. Idempotent only within the call:
        registering the same path twice raises (the caller likely meant to apply
        all edits in-memory and write once).
        """
        if self._closed:
            raise RuntimeError("Snapshot is closed (already restored or cleaned).")

        # WARNING: snapshotting through a symlink would let a mutation reach
        # a target the sandbox doesn't expect (the link target). Refuse the
        # input *before* resolution — ``Path.resolve`` would follow the link
        # silently. Spirit of DEC-008 §2.
        if path.is_symlink():
            raise SandboxViolation(f"Snapshot refuses symlink: {path}")

        # Sandbox check second — never copy a file from outside the sandbox.
        validate_path_in_sandbox(path, self._workdir, self._allowed)
        resolved = path.resolve(strict=False)

        if resolved in self._records:
            raise ValueError(f"Path already protected by this snapshot: {resolved}")

        if resolved.exists():
            backup = self._tmp_root / f"{len(self._records):04d}.bak"
            shutil.copy2(resolved, backup)
            self._records[resolved] = _Record(backup=backup)
            logger.debug("snapshot.protect(existing): %s -> %s", resolved, backup)
        else:
            # Record creation. Walk ancestors and remember those still missing —
            # restore will rmdir them (innermost first) so the workdir is left
            # exactly as we found it.
            missing: list[Path] = []
            for parent in resolved.parents:
                if parent == self._workdir or parent in self._allowed:
                    break
                if parent.exists():
                    break
                missing.append(parent)
            self._records[resolved] = _Record(backup=None, missing_ancestors=missing)
            logger.debug("snapshot.protect(creating): %s (missing dirs=%d)", resolved, len(missing))

    def restore(self) -> None:
        """Revert every protected path; then cleanup. Best-effort, never raises."""
        if self._closed:
            return
        # Existing files first: copy the backup back. Created files second:
        # delete them and rmdir empty ancestors.
        for path, rec in self._records.items():
            try:
                if rec.backup is not None:
                    shutil.copy2(rec.backup, path)
                else:
                    if path.exists():
                        try:
                            path.unlink()
                        except IsADirectoryError:
                            shutil.rmtree(path, ignore_errors=True)
                    for d in rec.missing_ancestors:
                        try:
                            d.rmdir()
                        except OSError:
                            # Not empty (something else dropped a file in here)
                            # or already removed — non-fatal.
                            pass
            except Exception as exc:  # noqa: BLE001 — best-effort restore
                logger.error("snapshot.restore failed for %s: %s", path, exc)
        self.cleanup()

    def cleanup(self) -> None:
        """Drop the temp backups; safe to call multiple times."""
        if self._closed:
            return
        shutil.rmtree(self._tmp_root, ignore_errors=True)
        self._closed = True

    @property
    def protected_paths(self) -> list[Path]:
        return list(self._records)


@contextmanager
def snapshot(workdir: Path, allowed_read_paths: list[Path] | None = None) -> Iterator[Snapshot]:
    """Convenience context manager — restores on any exception, cleans on success.

    The dispatcher does NOT use this form (it needs the snapshot to live past
    the mutate call so it can also revert on a post-loop validation error).
    Tests and ad-hoc callers should prefer this entry point.
    """
    snap = Snapshot(workdir, allowed_read_paths)
    try:
        yield snap
    except BaseException:
        snap.restore()
        raise
    else:
        snap.cleanup()


__all__ = ["Snapshot", "snapshot"]
