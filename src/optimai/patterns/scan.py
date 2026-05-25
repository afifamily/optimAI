"""Pattern E — Scan/Audit: read-only pattern hunt with pass/fail verdict.

Born from the Phase 3 collection (DEC-025): three projects independently needed
"grep for these patterns in these targets, give me a verdict". A is read-only
too but its report shape is root_cause/fix and its prompt forbids scanning large
trees — E is its own pattern because the report shape (matches + verdict) is
genuinely different (PATTERN_CANDIDATES.md).

Sémantique (figée Desktop #13, brief CLI #10) :

- **Cortex-sourced** — the Cortex provides patterns (``required`` /
  ``forbidden`` / ``secret_patterns``) and targets. The worker does not invent
  patterns; it runs ``grep`` / ``curl -s`` and reports occurrences + verdict.
- **Read-only** — no mutation, no snapshot. Timeout policy ``recover``
  (DEC-022, same reasoning as Diagnose).
- **Two source kinds** — ``fs`` (sub-paths under the sandbox) and ``http``
  (``GET`` body, bénin per DEC-008/DEC-025).
- **DEC-026** — ``secret_patterns`` carries values whose literal occurrences
  must be stripped from outgoing fields. The redaction is a generic engine
  step in ``dispatcher.py`` (consulted via ``getattr(spec, "secret_patterns")``),
  not a pattern-specific concern — A/D/B/C inherit it for free if they ever
  grow a ``secret_patterns`` attribute (YAGNI today; ready when needed).

DEC-021 — this pattern adds itself by ``@register("scan")`` and no other file
changes (server.py, dispatcher.py untouched on the pattern axis). The
redaction step is generic so it does not count as pattern-specific glue.
"""

from typing import Literal

from optimai.patterns.base import Step, TimeoutPolicy, register
from optimai.schemas.report import ScanMatch, ScanReport
from optimai.schemas.task_spec import ScanSpec

SYSTEM_PROMPT = """\
You audit one or more targets for the presence or absence of Cortex-supplied
patterns. You issue read-only shell commands (`grep`, `curl -s`) to collect
occurrences, then report a pass/fail verdict.

Scope — read carefully:
- The PATTERNS and TARGETS in the first user message come from the operator.
  You do NOT invent new patterns or new targets.
- For `fs` targets, the ref is a path under the sandbox — use `grep -rn` (or
  `grep -nF` for literal values) against it.
- For `http` targets, the ref is an HTTP(S) URL — use `curl -s <url>` and pipe
  to `grep` to inspect the body. A GET is informational; do NOT chain through
  `sh`, `bash`, eval, redirect to file, or any other side effect.
- Output is truncated and you are told the exit code. `grep` exit 1 means
  "pattern not found in input" — that is information, not an error.

Hard constraints:
- Informational commands ONLY. No sudo. No file modifications. No installs.
- Each command is a SINGLE line for /bin/sh -c. Keep commands fast and targeted.
- You have a small, bounded number of turns. Converge as soon as every pattern
  has been checked against every target.

Verdict rules:
- A pattern in `REQUIRED` that is NOT found in any target → verdict fail
  (and list it under MISSING_REQUIRED).
- A pattern in `FORBIDDEN` that IS found in any target → verdict fail
  (and list every occurrence under MATCHES).
- A pattern in `SECRET` is a forbidden value whose presence is a leak — list
  occurrences under MATCHES exactly as for FORBIDDEN. The value will be
  redacted from your output before it leaves the dispatcher.
- Otherwise → verdict pass.

At EVERY turn reply in EXACTLY ONE of these two formats, nothing else.

To run a command:
THINK: <one-line reasoning>
ACTION: shell
CMD: <single shell command on one line>

To deliver the final verdict:
THINK: <one-line reasoning>
ACTION: report
VERDICT: pass
MATCHES:
- <target> | <line_or_-> | <pattern> | <matched_text>
- <target> | <line_or_-> | <pattern> | <matched_text>
MISSING_REQUIRED:
- <pattern_name>
PATTERNS_CHECKED: <int>

Rules:
- Output ONLY the block. No markdown fences, no extra prose.
- If MATCHES is empty, leave the section header on its own line with no
  entries underneath. Same for MISSING_REQUIRED.
- A `MATCHES` line must use `|` as the field separator. Use `-` for line when
  unknown (HTTP body without a line counter).
- Report as soon as every pattern has been checked — do not run redundant
  commands.
"""


def _none_if_blank(value: str) -> str | None:
    cleaned = value.strip()
    return None if cleaned == "" or cleaned.lower() == "none" else cleaned


def _parse_match_line(line: str) -> ScanMatch | None:
    """Best-effort parse of a single ``MATCHES`` entry.

    Format expected (worker contract): ``- <target> | <line_or_-> | <pattern> | <text>``.
    Tolerant of extra whitespace around `|`; returns None on a malformed line so
    one bad line does not kill the whole report.
    """
    body = line.lstrip("- ").strip()
    if not body:
        return None
    parts = [p.strip() for p in body.split("|")]
    if len(parts) < 4:
        return None
    target, line_field, pattern, *text_parts = parts
    text = " | ".join(text_parts).strip()  # preserve any pipe in matched text
    line_no: int | None
    if line_field in ("-", "", "none", "None"):
        line_no = None
    else:
        try:
            line_no = int(line_field)
        except ValueError:
            line_no = None
    if not target or not pattern:
        return None
    return ScanMatch(target=target, line=line_no, text=text, pattern=pattern)


def _format_patterns(spec: ScanSpec) -> str:
    """Render the pattern registers in the initial user message.

    Secret values flow through as ``context``-equivalent — DEC-026 allows them
    to enter; the dispatcher strips them from outputs.
    """
    lines: list[str] = []
    if spec.required:
        lines.append("REQUIRED (must be present):")
        for p in spec.required:
            lines.append(f"- {p}")
    if spec.forbidden:
        lines.append("FORBIDDEN (must be absent):")
        for p in spec.forbidden:
            lines.append(f"- {p}")
    if spec.secret_patterns:
        lines.append(
            "SECRET (must be absent — values redacted in the outgoing report):"
        )
        for p in spec.secret_patterns:
            lines.append(f"- {p}")
    return "\n".join(lines)


def _format_targets(spec: ScanSpec) -> str:
    lines = ["TARGETS:"]
    for t in spec.targets:
        lines.append(f"- [{t.kind}] {t.ref}")
    return "\n".join(lines)


@register("scan")
class ScanPattern:
    """Strategy E — Cortex-sourced pattern hunt over fs + http sources."""

    name: str = "scan"
    spec_model: type = ScanSpec
    tool_description: str = (
        "Read-only scan/audit. Given Cortex-supplied patterns (required-present "
        "and/or forbidden-absent) and one or more targets (files under the "
        "sandbox, or HTTP GET responses), the worker greps each target and "
        "returns matches plus a pass/fail verdict. Use it to prove presence of "
        "expected markers or absence of a leak. Never mutates; secret pattern "
        "values are redacted from the report."
    )

    def system_prompt(self, spec: ScanSpec) -> str:
        # DEC-021: no domain knowledge in the prompt — patterns + targets flow
        # in through `initial_user_message`, the prompt only describes the
        # protocol and the verdict rules.
        return SYSTEM_PROMPT

    def initial_user_message(self, spec: ScanSpec) -> str:
        parts = [f"GOAL:\n{spec.goal}", "", f"CONTEXT:\n{spec.context}", ""]
        patterns_block = _format_patterns(spec)
        if patterns_block:
            parts.append(patterns_block)
            parts.append("")
        parts.append(_format_targets(spec))
        return "\n".join(parts)

    def operator_text(self, spec: ScanSpec) -> str:
        # DEC-008 defense in depth: scan the high-level operator instructions —
        # goal plus the target refs (a URL or a path is itself an operator
        # vector). The patterns themselves (incl. `secret_patterns`) are NOT
        # vetted: they may legitimately carry token-shaped values to be
        # searched for — same rationale as `context` (DEC-021, DEC-026).
        parts: list[str] = [spec.goal]
        for t in spec.targets:
            parts.append(t.ref)
        return "\n".join(parts)

    def parse(self, worker_text: str) -> Step:
        lines = worker_text.strip().splitlines()
        think = ""
        action = ""
        for line in lines:
            if line.startswith("THINK:"):
                think = line[len("THINK:"):].strip()
            elif line.startswith("ACTION:"):
                action = line[len("ACTION:"):].strip().lower()

        if action == "shell":
            for line in lines:
                if line.startswith("CMD:"):
                    cmd = line[len("CMD:"):].strip()
                    if not cmd:
                        return Step(kind="invalid", reason="empty CMD")
                    return Step(kind="command", think=think, cmd=cmd)
            return Step(kind="invalid", reason="ACTION shell without CMD line")

        if action == "report":
            verdict_raw = ""
            patterns_checked = 0
            matches: list[ScanMatch] = []
            missing_required: list[str] = []
            section = ""  # "matches" | "missing" | ""
            for raw in lines:
                stripped = raw.strip()
                if stripped.startswith("VERDICT:"):
                    verdict_raw = stripped[len("VERDICT:"):].strip().lower()
                    section = ""
                elif stripped.startswith("MATCHES:"):
                    section = "matches"
                elif stripped.startswith("MISSING_REQUIRED:"):
                    section = "missing"
                elif stripped.startswith("PATTERNS_CHECKED:"):
                    try:
                        patterns_checked = int(
                            stripped[len("PATTERNS_CHECKED:"):].strip()
                        )
                    except ValueError:
                        patterns_checked = 0
                    section = ""
                elif section == "matches" and stripped.startswith("-"):
                    m = _parse_match_line(stripped)
                    if m is not None:
                        matches.append(m)
                elif section == "missing" and stripped.startswith("-"):
                    p = stripped.lstrip("- ").strip()
                    if p:
                        missing_required.append(p)
            verdict: Literal["pass", "fail"] | None
            if verdict_raw == "pass":
                verdict = "pass"
            elif verdict_raw == "fail":
                verdict = "fail"
            else:
                verdict = None
            payload = {
                "verdict": verdict,
                "matches": [m.model_dump() for m in matches],
                "missing_required": missing_required,
                "patterns_checked": patterns_checked,
            }
            return Step(kind="final", think=think, payload=payload)

        return Step(kind="invalid", reason=f"unrecognized ACTION {action!r}")

    def on_command_timeout(self, cmd: str, step: Step) -> TimeoutPolicy:
        # Scan commands are read-only (`grep`, `curl -s`) — a slow command
        # killed and replaced by a more targeted one leaves no side effect, so
        # recovery is the safe choice (DEC-022, same as Diagnose).
        return "recover"

    def build_report(
        self,
        *,
        final_payload: dict | None,
        commands_executed: list[dict],
        stop_reason: str,
        iterations_used: int,
        status: Literal["complete", "incomplete", "error"],
        notes: str,
    ) -> ScanReport:
        if status == "complete" and final_payload is not None:
            return ScanReport(
                status="complete",
                verdict=final_payload.get("verdict"),
                matches=[ScanMatch(**m) for m in final_payload.get("matches", [])],
                missing_required=list(final_payload.get("missing_required", [])),
                patterns_checked=int(final_payload.get("patterns_checked", 0)),
                iterations_used=iterations_used,
                stop_reason=stop_reason,
                commands_executed=commands_executed,
                notes=notes[:1024],
            )
        # incomplete / error: keep verdict / matches / missing_required at
        # their defaults — the Cortex distinguishes "no verdict" from "pass".
        return ScanReport(
            status=status,
            iterations_used=iterations_used,
            stop_reason=stop_reason,
            commands_executed=commands_executed,
            notes=notes[:1024],
        )
