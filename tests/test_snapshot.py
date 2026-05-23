"""Tests for optimai.snapshot — intra-call atomicity helper (DEC-024)."""

import pytest

from optimai.shell import SandboxViolation
from optimai.snapshot import Snapshot, snapshot


def test_snapshot_restores_existing_file_to_the_byte(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("before\n", encoding="utf-8")

    snap = Snapshot(tmp_path)
    snap.protect(target)
    target.write_text("MUTATED\n", encoding="utf-8")
    snap.restore()

    assert target.read_text(encoding="utf-8") == "before\n"


def test_snapshot_restore_removes_created_file(tmp_path):
    target = tmp_path / "new.txt"
    assert not target.exists()

    snap = Snapshot(tmp_path)
    snap.protect(target)
    target.write_text("freshly written\n", encoding="utf-8")
    snap.restore()

    assert not target.exists()


def test_snapshot_restore_removes_created_directories(tmp_path):
    """Ancestor dirs the snapshot caller had to create must be cleaned up too."""
    target = tmp_path / "deep" / "nest" / "file.txt"

    snap = Snapshot(tmp_path)
    snap.protect(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("body\n", encoding="utf-8")
    snap.restore()

    assert not target.exists()
    assert not (tmp_path / "deep" / "nest").exists()
    assert not (tmp_path / "deep").exists()


def test_snapshot_cleanup_drops_temp_backups(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("hi\n", encoding="utf-8")

    snap = Snapshot(tmp_path)
    snap.protect(target)
    tmp_root = snap.tmp_root
    assert tmp_root.exists()
    snap.cleanup()
    assert not tmp_root.exists()


def test_snapshot_double_protect_raises(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("x", encoding="utf-8")

    snap = Snapshot(tmp_path)
    snap.protect(target)
    with pytest.raises(ValueError):
        snap.protect(target)
    snap.cleanup()


def test_snapshot_refuses_path_outside_sandbox(tmp_path):
    outside = tmp_path.parent / "escape.txt"

    snap = Snapshot(tmp_path)
    try:
        with pytest.raises(SandboxViolation):
            snap.protect(outside)
    finally:
        snap.cleanup()


def test_snapshot_refuses_symlink(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("hi\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    snap = Snapshot(tmp_path)
    try:
        with pytest.raises(SandboxViolation):
            snap.protect(link)
    finally:
        snap.cleanup()


def test_snapshot_context_manager_restores_on_exception(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("before\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        with snapshot(tmp_path) as snap:
            snap.protect(target)
            target.write_text("MUTATED\n", encoding="utf-8")
            raise RuntimeError("boom")

    assert target.read_text(encoding="utf-8") == "before\n"


def test_snapshot_context_manager_cleans_on_success(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("before\n", encoding="utf-8")

    with snapshot(tmp_path) as snap:
        snap.protect(target)
        target.write_text("kept\n", encoding="utf-8")
        tmp_root = snap.tmp_root

    assert target.read_text(encoding="utf-8") == "kept\n"
    assert not tmp_root.exists()


def test_snapshot_restore_is_idempotent(tmp_path):
    """Calling restore twice (or restore then cleanup) must not raise."""
    target = tmp_path / "f.txt"
    target.write_text("x", encoding="utf-8")
    snap = Snapshot(tmp_path)
    snap.protect(target)
    snap.restore()
    snap.restore()
    snap.cleanup()


def test_snapshot_allowed_read_path_widens_sandbox(tmp_path):
    extra = tmp_path.parent / f"{tmp_path.name}-extra"
    extra.mkdir(parents=True, exist_ok=True)
    target = extra / "f.txt"
    target.write_text("ok\n", encoding="utf-8")
    try:
        snap = Snapshot(tmp_path, allowed_read_paths=[extra])
        snap.protect(target)
        target.write_text("MUTATED\n", encoding="utf-8")
        snap.restore()
        assert target.read_text(encoding="utf-8") == "ok\n"
    finally:
        for f in extra.iterdir():
            f.unlink()
        extra.rmdir()


def test_snapshot_protected_paths_listing(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("a", encoding="utf-8")
    b = tmp_path / "b.txt"  # will-create

    snap = Snapshot(tmp_path)
    snap.protect(a)
    snap.protect(b)
    paths = snap.protected_paths
    assert {p.name for p in paths} == {"a.txt", "b.txt"}
    snap.cleanup()
