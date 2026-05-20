"""Live smoke test — Pattern A end-to-end against a real `mlx_lm.server` (DEC-017).

Exercises the full chain post-DEC-021: `dispatch("diagnose", spec)` → real worker
loop → real shell. Excluded from the default `pytest` run (see `pyproject.toml`,
`addopts = "-m 'not live'"`), opt-in via:

    uv run pytest -m live -s

The XCTest domain knowledge that used to live in the PoC's system prompt is now
injected through `spec.context`. That's the Cortex↔Hands contract from DEC-021:
the pattern is generic, the Cortex supplies the situational know-how.
"""

from pathlib import Path

import pytest

from optimai.dispatcher import dispatch
from optimai.schemas.task_spec import DiagnoseSpec

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[1]


# Domain knowledge for the XCTest failure family — previously hard-coded in the
# PoC system prompt, now supplied as CONTEXT by the (simulated) Cortex.
XCTEST_DOMAIN_KNOWLEDGE = """\
Domain knowledge for "no such module 'XCTest'":
- XCTest.framework ships inside Xcode.app, NOT inside the CommandLineTools.
- `xcode-select -p` prints the active developer directory.
- If it points to an Xcode.app developer dir (e.g.
  /Applications/Xcode.app/Contents/Developer), XCTest is available and the
  toolchain is HEALTHY — report that as the root cause (no environment fault).
- If it points to /Library/Developer/CommandLineTools, THAT is the root cause:
  CommandLineTools does not ship XCTest. Temporary fix:
  `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test`.
  Permanent fix: `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`
  — NAME it in PERMANENT_FIX, never emit it as a CMD.
"""


def _build_spec() -> DiagnoseSpec:
    failure_text = (REPO_ROOT / "tests/fixtures/xctest_failure.txt").read_text(encoding="utf-8")
    context = f"{failure_text}\n\n{XCTEST_DOMAIN_KNOWLEDGE}"
    return DiagnoseSpec(
        goal=(
            "`swift test` fails with 'no such module XCTest'. "
            "Find the root cause and propose a fix. "
            "Use only informational shell commands (no sudo, no modifications)."
        ),
        context=context,
        workdir=Path.home(),
        allowed_read_paths=[Path("/Applications"), Path("/Library/Developer")],
        extra_blacklist=[
            r"\bxcode-select\s+-s\b",  # the invasive fix stays out of CMDs
            r"\bxcodebuild\s+-license\b",
        ],
    )


async def test_diagnose_xctest_converges_live():
    spec = _build_spec()
    report = await dispatch("diagnose", spec)
    print("\n=== Live DiagnoseReport ===")
    print(report.model_dump_json(indent=2))

    assert report.status == "complete", (
        f"expected complete, got status={report.status} stop_reason={report.stop_reason}"
    )
    assert report.iterations_used <= 6, (
        f"diagnostic should converge fast; took {report.iterations_used} iterations"
    )
    assert report.root_cause is not None
    assert len(report.evidence) >= 1
