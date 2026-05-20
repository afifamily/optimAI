#!/usr/bin/env python3
"""Live smoke run — Pattern A end-to-end against a real `mlx_lm.server` (DEC-017).

Thin CLI wrapper around `optimai.dispatcher.dispatch("diagnose", spec)`. The
loop mechanics live in `optimai.dispatcher`, the strategy in
`optimai.patterns.diagnose`; this script only builds the spec for the TBS
XCTest case and prints the resulting report.

The same scenario also runs as `tests/test_diagnose_live.py` under
`uv run pytest -m live`. Keeping the script form makes it easy to eyeball the
output during dev:

    uv run python scripts/poc_diagnose_xctest.py

Exit code: 0 if the DiagnoseReport status is "complete", 1 otherwise.
"""

import asyncio
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from optimai.config import get_settings  # noqa: E402
from optimai.dispatcher import dispatch  # noqa: E402
from optimai.schemas.task_spec import DiagnoseSpec  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


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
            r"\bxcode-select\s+-s\b",
            r"\bxcodebuild\s+-license\b",
        ],
    )


async def _main() -> int:
    settings = get_settings()
    spec = _build_spec()

    print("=" * 64)
    print("optimAI — PoC Pattern A — TBS XCTest diagnosis (via dispatch)")
    print(f"workdir          : {spec.workdir}")
    print(f"blacklist file   : {settings.blacklist_file}")
    print(f"max_iterations   : {settings.max_iterations}")
    print(f"timeout_seconds  : {settings.timeout_seconds}")
    print("=" * 64)

    report = await dispatch("diagnose", spec, settings=settings)

    print()
    print("=== DiagnoseReport ===")
    print(report.model_dump_json(indent=2))
    return 0 if report.status == "complete" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
