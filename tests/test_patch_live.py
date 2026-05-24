"""Live smoke test — Pattern B failure path against a real `mlx_lm.server` (DEC-024 amended).

Reproduces the bug captured at Desktop #12 smoke live: a deterministic patch
breaks the syntax of a target file; the validation command (`python -m
py_compile`) exits non-zero; the worker correctly names the failure but the
report used to come back with `status="complete"` → snapshot was *cleaned*
instead of *restored* → file was left broken on disk.

After the DEC-024 amendment, the dispatcher's deterministic guard (Layer 1)
must force `status="error"` on a validation command's non-zero exit, regardless
of what the worker reports. Atomicity intra-appel then restores the file to
its pre-call bytes.

Excluded from the default `pytest` run (see `pyproject.toml`,
`addopts = "-m 'not live'"`), opt-in via:

    uv run pytest -m live -s
"""

import pytest

from optimai.dispatcher import dispatch
from optimai.schemas.task_spec import CreateSpec, FileEdit, NewFile, PatchSpec

pytestmark = pytest.mark.live


async def test_patch_validation_failure_rolls_back_live(tmp_path):
    """Broken patch → validation exit≠0 → status=error → file byte-restored."""
    target = tmp_path / "hello.py"
    original = "def greet():\n    return 'hello'\n"
    target.write_text(original, encoding="utf-8")
    original_bytes = target.read_bytes()

    # Drop the ':' from the signature — py_compile will fail at parse time.
    spec = PatchSpec(
        goal="introduce a deliberate syntax break to validate rollback",
        context=(
            "This patch is expected to break the file. The validation command will "
            "exit non-zero. The engine's deterministic guard must force "
            "status=error so the snapshot restores the original bytes."
        ),
        workdir=tmp_path,
        edits=[FileEdit(path=target, old="def greet():", new="def greet()")],
        validation_command=f"python -m py_compile {target}",
    )

    report = await dispatch("patch", spec)

    print("\n=== Live PatchReport (B-rollback) ===")
    print(report.model_dump_json(indent=2))

    assert report.status == "error", (
        f"deterministic guard did not fire: status={report.status}, "
        f"stop_reason={report.stop_reason}, notes={report.notes!r}"
    )
    # Atomicity intra-appel (DEC-024): file restored to the byte.
    assert target.read_bytes() == original_bytes, (
        "snapshot did not restore the file — it is still broken on disk"
    )


async def test_patch_validation_success_keeps_complete_live(tmp_path):
    """Border the invariant: exit 0 + no worker failure → status stays complete."""
    target = tmp_path / "ok.py"
    target.write_text("x = 1\n", encoding="utf-8")

    spec = PatchSpec(
        goal="rename variable x to y — must keep the file valid",
        context="Validation command should exit 0; the report must be complete.",
        workdir=tmp_path,
        edits=[FileEdit(path=target, old="x = 1", new="y = 1")],
        validation_command=f"python -m py_compile {target}",
    )

    report = await dispatch("patch", spec)

    print("\n=== Live PatchReport (B-success) ===")
    print(report.model_dump_json(indent=2))

    assert report.status == "complete", (
        f"expected complete on clean patch: status={report.status}, "
        f"stop_reason={report.stop_reason}, notes={report.notes!r}"
    )
    # Mutation kept (no rollback on success).
    assert target.read_text(encoding="utf-8") == "y = 1\n"


async def test_create_validation_failure_rolls_back_live(tmp_path):
    """Mirror for Pattern C: invalid-Python content → syntax check exit≠0 →
    status=error → file removed (atomicity intra-appel)."""
    target = tmp_path / "broken.py"

    spec = CreateSpec(
        goal="create a deliberately invalid python file to validate rollback",
        context=(
            "The content is syntactically invalid. py_compile will exit non-zero "
            "and the engine's deterministic guard must force status=error so the "
            "snapshot removes the freshly-created file."
        ),
        workdir=tmp_path,
        files=[NewFile(path=target, content="def (\n", language="python")],
    )

    report = await dispatch("create", spec)

    print("\n=== Live CreateReport (C-rollback) ===")
    print(report.model_dump_json(indent=2))

    assert report.status == "error", (
        f"deterministic guard did not fire: status={report.status}, "
        f"stop_reason={report.stop_reason}, notes={report.notes!r}"
    )
    assert not target.exists(), (
        "snapshot did not remove the freshly-created broken file"
    )
