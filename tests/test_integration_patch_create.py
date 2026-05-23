"""Cross-pattern integration: A+B (Diagnose then Patch) and D+C (Create then Execute).

These tests prove that the patterns COMPOSE through the public dispatch API
(each call independent, statelessness preserved) and that the mutation phase
of B/C integrates correctly with the loop. Worker is mocked via httpx; shell
is real (the validation step runs ``python -m py_compile`` on a real file).
"""

from pathlib import Path

import httpx

from optimai.config import Settings
from optimai.dispatcher import dispatch
from optimai.schemas.report import CreateReport, DiagnoseReport, ExecuteReport, PatchReport
from optimai.schemas.task_spec import (
    CreateSpec,
    DiagnoseSpec,
    ExecuteSpec,
    FileEdit,
    NewFile,
    PatchSpec,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLACKLIST = REPO_ROOT / "config" / "blacklist.txt"


def _settings() -> Settings:
    return Settings(
        OPTIMAI_MAX_ITERATIONS=5,
        OPTIMAI_TIMEOUT_SECONDS=30,
        OPTIMAI_MAX_OUTPUT_BYTES=10240,
        OPTIMAI_BLACKLIST_FILE=DEFAULT_BLACKLIST,
    )


def _client(responses: list[str]) -> httpx.AsyncClient:
    cursor = {"i": 0}

    def handler(_request):
        i = cursor["i"]
        cursor["i"] += 1
        if i >= len(responses):
            return httpx.Response(500, text="exhausted")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": responses[i]}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _diagnose_report_text() -> str:
    return (
        "THINK: done\nACTION: report\nROOT_CAUSE: identified\n"
        "EVIDENCE:\n- saw expected\nTEMPORARY_FIX: none\nPERMANENT_FIX: none\n"
    )


def _patch_report_text() -> str:
    return "THINK: validated\nACTION: report\nSUMMARY: file compiles\nFAILED_EDIT: none\n"


def _create_report_text() -> str:
    return "THINK: validated\nACTION: report\nSUMMARY: created and compiles\nFAILED_FILE: none\n"


def _execute_report_text(failed: str = "none") -> str:
    return f"THINK: pack done\nACTION: report\nSUMMARY: ran the pack\nFAILED_COMMAND: {failed}\n"


# --------------------------------------------------------------------------
# A + B — diagnose first (read-only), then patch (mutating) on the same workdir
# --------------------------------------------------------------------------


async def test_diagnose_then_patch_compose(tmp_path):
    """Diagnose leaves the workdir untouched; Patch then mutates + validates."""
    src = tmp_path / "hello.py"
    src.write_text("print('hello')\n", encoding="utf-8")
    src_bytes_before = src.read_bytes()

    # Step 1 — Diagnose. We mock a 1-shot report; no shell side effects.
    async with _client([_diagnose_report_text()]) as client:
        diag = await dispatch(
            "diagnose",
            DiagnoseSpec(goal="check that hello.py is well-formed Python", workdir=tmp_path),
            settings=_settings(),
            client=client,
        )
    assert isinstance(diag, DiagnoseReport)
    assert diag.status == "complete"
    # File unchanged by the diagnose call (statelessness + read-only).
    assert src.read_bytes() == src_bytes_before

    # Step 2 — Patch with a real validation command.
    cmd_text = "THINK: validate\nACTION: shell\nCMD: python -m py_compile " + str(src) + "\n"
    async with _client([cmd_text, _patch_report_text()]) as client:
        patch_report = await dispatch(
            "patch",
            PatchSpec(
                goal="rename hello to world",
                workdir=tmp_path,
                edits=[FileEdit(path=src, old="hello", new="world")],
                validation_command="python -m py_compile " + str(src),
            ),
            settings=_settings(),
            client=client,
        )
    assert isinstance(patch_report, PatchReport)
    assert patch_report.status == "complete"
    assert patch_report.diff and "world" in patch_report.diff
    assert patch_report.files_changed == [str(src)]
    # The mutation stayed applied on success.
    assert src.read_text(encoding="utf-8") == "print('world')\n"


async def test_patch_validation_failure_rolls_back(tmp_path):
    """If the worker decides the patched state is broken (one bad turn, then
    one more bad turn → status=error), the snapshot must restore the file."""
    src = tmp_path / "hello.py"
    original = "print('hello')\n"
    src.write_text(original, encoding="utf-8")

    # Two consecutive invalid worker replies → status=error.
    async with _client(["garbage one", "garbage two"]) as client:
        report = await dispatch(
            "patch",
            PatchSpec(
                goal="rename hello to world",
                workdir=tmp_path,
                edits=[FileEdit(path=src, old="hello", new="world")],
            ),
            settings=_settings(),
            client=client,
        )

    assert report.status == "error"
    # Atomicity: file restored byte-for-byte (DEC-024).
    assert src.read_text(encoding="utf-8") == original


# --------------------------------------------------------------------------
# D + C — create a file, then execute a pack against it
# --------------------------------------------------------------------------


async def test_create_then_execute_compose(tmp_path):
    target = tmp_path / "sub" / "made.py"

    create_cmd = (
        "THINK: validate\nACTION: shell\nCMD: python -m py_compile " + str(target) + "\n"
    )
    async with _client([create_cmd, _create_report_text()]) as client:
        c_report = await dispatch(
            "create",
            CreateSpec(
                goal="create made.py with a valid python expression",
                workdir=tmp_path,
                files=[NewFile(path=target, content="x = 1\n", language="python")],
            ),
            settings=_settings(),
            client=client,
        )

    assert isinstance(c_report, CreateReport)
    assert c_report.status == "complete"
    assert c_report.files_created == [str(target)]
    assert target.exists()

    # Now Execute a pack that reads the file (read-only `cat` from the workdir).
    async with _client([_execute_report_text("none")]) as client:
        e_report = await dispatch(
            "execute",
            ExecuteSpec(
                goal="cat the file we just created",
                workdir=tmp_path,
                commands=["cat " + str(target)],
            ),
            settings=_settings(),
            client=client,
        )
    assert isinstance(e_report, ExecuteReport)
    # The worker delivered a verdict directly without running the pack — that's
    # fine, the integration point we're asserting is "two separate dispatches
    # over the same workdir keep working". Both calls succeeded.
    assert e_report.status in ("complete", "incomplete")
    # And the file from Create is still present (no cross-call rollback).
    assert target.exists()


async def test_create_rollback_when_validation_fails(tmp_path):
    """Same atomicity story for Create: error in the loop → file is gone."""
    target = tmp_path / "new.py"
    async with _client(["garbage one", "garbage two"]) as client:
        report = await dispatch(
            "create",
            CreateSpec(
                goal="create new.py",
                workdir=tmp_path,
                files=[NewFile(path=target, content="x = 1\n", language="python")],
            ),
            settings=_settings(),
            client=client,
        )
    assert report.status == "error"
    assert not target.exists()


# --------------------------------------------------------------------------
# Statelessness: two consecutive Patches on the same workdir keep working
# --------------------------------------------------------------------------


async def test_two_patches_in_sequence(tmp_path):
    src = tmp_path / "code.py"
    src.write_text("a = 1\n", encoding="utf-8")

    async with _client([_patch_report_text()]) as client:
        await dispatch(
            "patch",
            PatchSpec(
                goal="rename a to b",
                workdir=tmp_path,
                edits=[FileEdit(path=src, old="a = 1", new="b = 2")],
            ),
            settings=_settings(),
            client=client,
        )
    assert src.read_text(encoding="utf-8") == "b = 2\n"

    async with _client([_patch_report_text()]) as client:
        await dispatch(
            "patch",
            PatchSpec(
                goal="rename b to c",
                workdir=tmp_path,
                edits=[FileEdit(path=src, old="b = 2", new="c = 3")],
            ),
            settings=_settings(),
            client=client,
        )
    assert src.read_text(encoding="utf-8") == "c = 3\n"
