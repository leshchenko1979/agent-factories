#!/usr/bin/env python3
r"""Gate: a pacemaker cron is a thin WAKE, never the worker (P7 / P28).

WHAT THIS GATE UPHOLDS. `docs/best-practices.md` P7 — *"Cron is a thin pacemaker
trigger, not the worker"* — and P28, *"Every periodic process is driven by a thin
nudging cron"*. Both describe the same object: a scheduled job exists to WAKE the
persistent session that owns a periodic process, and the substantive work runs there.

Until #54 neither practice had a mechanism. P7 was mapped to `tools/hygiene.py`, which
declares its own scope as P20 and never reads a cron row; P28's second target
`tools/audit.py` carried no cron reference either. Both mappings passed, because
`tests/test_law_coverage.py` asserts only that the target PATH EXISTS — a file that
exists and implements nothing satisfies it completely. A rule without an upholding
mechanism is dead text (P29), and #50 is what that cost: a live, unbounded P7 violation
was found by a lane reading a cron row by hand, because no gate could see it.

WHY THE UPHOLDER IS A PURE PREDICATE OVER A LIST. The pacemaker rows live in the live
`cron_jobs` table, and the mechanical suite runs offline against a tree. A gate that read
that table would RED in every bootstrapped factory that has no such table — the failure
#68 measured. So the predicate is HERE, pure over a list of rows and probeable with
synthetic ones, and the host-side invocation that feeds it live rows is a separate item
(#54 part b, not dispatched). `test_probe_is_offline` asserts the purity structurally.

THE THREE LIVE SHAPES — and why BOTH fields must be read. Issue #54 measured them
against the live table (`cron_jobs`, `enabled=1`, 23 rows, 2026-09-18):

  1. session target      `deliver_to = session:<uuid>`, tiny prompt — the delivery IS the wake.
  2. prompt-carried wake `deliver_to = NULL`, the prompt invokes `session notify <uuid>`.
  3. self-executing      a channel or NULL target, and no wake in the prompt — the work
                         runs in the cron's own session. This is the #50 shape.

A predicate reading only `deliver_to` flags every shape-2 row; one reading only the prompt
flags every shape-1 row. Both legs are required, and "thin" is NOT a byte count: the
meta-factory's own correctly-thin pacemaker `factory-triage-patrol` (id
`3673ffec-07af-433c-9aa7-16f47903466c`) has `deliver_to = NULL` and a 1326-byte prompt
whose single command is a wake — measured 2026-09-20, and the width is stated with its
instant because the row is mutable — while a shorter prompt carrying a work order is a
defect. The probes pin exactly that pair, so a future edit that "simplifies" this to a
length test fails loudly.

WHAT THE PREDICATE DOES NOT CLAIM. It reads the WAKE ROUTE, never the work content: a row
that delivers to a session is thin BY ROUTE whether or not its prompt also carries a work
order, which is the shape HQ ruled in #50. It cannot execute a prompt, so a row that merely
DESCRIBES a wake in prose satisfies the prompt leg — the bound is that the leg is a
textual one, and the live population that would catch that belongs to #54 part (b). The
population judged is the caller's: this file never decides which rows are pacemakers, and a
row it cannot classify at all (neither prompt nor `deliver_to`) is EXCUSED and PRINTED,
never silently clean.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SESSION_TARGET_PREFIX = "session:"
WAKE_RE = re.compile(r"\bsession[\s_]+notify\b", re.IGNORECASE)

def _text(value: object) -> str:
    """The value as text, or '' — a non-string cell is absent, never a crash."""
    return value if isinstance(value, str) else ""

def row_wake(row: dict) -> str:
    """Which wake this row carries: 'session-target', 'prompt-notify', or 'none'."""
    if _text(row.get("deliver_to")).strip().lower().startswith(SESSION_TARGET_PREFIX):
        return "session-target"
    if WAKE_RE.search(_text(row.get("prompt"))):
        return "prompt-notify"
    return "none"

def pacemaker_problems(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for a list of cron rows."""
    problems: list[str] = []
    excused: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            excused.append(
                f"row {index}: not a mapping ({type(row).__name__}) — not a cron row"
            )
            continue
        name = _text(row.get("name")) or f"<row {index}>"
        prompt = _text(row.get("prompt"))
        deliver_to = _text(row.get("deliver_to")).strip()
        if not prompt.strip() and not deliver_to:
            excused.append(
                f"{name}: carries neither a prompt nor a deliver_to — unclassifiable, "
                f"and an unclassifiable row is not a clean one"
            )
            continue
        if row_wake(row) == "none":
            problems.append(
                f"{name}: no wake — deliver_to is {deliver_to or 'NULL'} and the prompt "
                f"invokes no session notify, so this job's own session is the only "
                f"executor (P7: cron is a thin pacemaker trigger, not the worker)"
            )
    return problems, excused

# --- probes ---

_WAKE_PROMPT = (
    'Thin trigger only — do NOT execute any project work yourself, do NOT investigate, '
    'do NOT write a report. Run exactly ONE bash command, then stop:\n\n'
    'nohup /usr/local/bin/opencrabs -p ops session notify f4c192c9-a8e9-4268-9026-ee3e4970cc8a '
    '--text "Triage cycle — run your patrol." --title "triage" --mode turn-end >/dev/null 2>&1 &'
)

_LONG_WAKE_PROMPT = (
    "Thin trigger only — do NOT execute any project work yourself, do NOT investigate, do "
    "NOT re-derive state, do NOT write project files, do NOT second-guess the runner's "
    "logic, and do NOT re-send anything already sent.\n"
    + ("Padding that a real thin prompt carries: state the do-not list, name the owner. " * 12)
    + "\n" + _WAKE_PROMPT
)

_WORK_ORDER_PROMPT = (
    "Sync the inferhub usage_logs Postgres cache. Execute exactly:\n\n"
    "1. ssh -N -L 15432:127.0.0.1:5432 apps -f -o ExitOnForwardFailure=yes || true\n"
    "2. cd /root/inferhub-watch && git pull --ff-only\n"
    "3. cd /root/inferhub-watch && python3 tools/sync_usage_logs.py --window 24h"
)

def _row(name: str, prompt: str = "", deliver_to: object = None, **extra: object) -> dict:
    row: dict = {"name": name, "prompt": prompt, "deliver_to": deliver_to}
    row.update(extra)
    return row

def test_shape_one_is_thin_by_route() -> None:
    rows = [
        _row(
            "inferhub-hq-pacemaker",
            "Execute the 6-hourly HQ cycle per skills/inferhub/SKILL.md.",
            "session:359fe71b-c7a1-420b-b856-acfb49939a7b",
        )
    ]
    problems, excused = pacemaker_problems(rows)
    assert problems == [], problems
    assert excused == [], excused

def test_shape_two_is_thin_by_prompt_with_a_null_target() -> None:
    rows = [_row("factory-triage-patrol", _WAKE_PROMPT, None)]
    problems, excused = pacemaker_problems(rows)
    assert problems == [], problems
    assert excused == [], excused

def test_thinness_is_not_a_byte_count() -> None:
    long_wake = _row("factory-triage-patrol", _LONG_WAKE_PROMPT, None)
    short_work = _row("tmp-short-worker", "Rebuild the index, then report.", None)
    assert len(_LONG_WAKE_PROMPT) > len(short_work["prompt"])

    problems, _ = pacemaker_problems([long_wake])
    assert problems == [], problems
    problems, _ = pacemaker_problems([short_work])
    assert len(problems) == 1, problems

def test_a_work_order_with_no_wake_is_a_problem_on_either_target() -> None:
    rows = [
        _row("inferhub-usage-logs-sync", _WORK_ORDER_PROMPT, None),
        _row("ai-antispam-outreach-db-sync", _WORK_ORDER_PROMPT, "telegram:-1003993000918:10780"),
    ]
    problems, excused = pacemaker_problems(rows)
    assert len(problems) == 2, problems
    assert excused == [], excused
    assert "inferhub-usage-logs-sync" in problems[0]
    assert "ai-antispam-outreach-db-sync" in problems[1]

def test_an_unclassifiable_row_is_excused_and_printed() -> None:
    rows = [_row("tmp-empty", "", None), "not-a-row"]
    problems, excused = pacemaker_problems(rows)
    assert problems == [], problems
    assert len(excused) == 2, excused
    assert "tmp-empty" in excused[0]
    assert "row 1" in excused[1]

def test_the_census_shape_classifies_as_the_issue_describes() -> None:
    rows = (
        [_row(f"session-{i}", "Execute the cycle per the skill.", f"session:uuid-{i}") for i in range(5)]
        + [_row(f"null-notify-{i}", _WAKE_PROMPT, None) for i in range(5)]
        + [_row(f"channel-worker-{i}", _WORK_ORDER_PROMPT, f"telegram:-100{i}:{i}") for i in range(10)]
        + [_row(f"null-worker-{i}", _WORK_ORDER_PROMPT, None) for i in range(3)]
    )
    problems, excused = pacemaker_problems(rows)
    assert len(problems) == 13, problems
    assert excused == [], excused
    assert all("worker-" in p for p in problems), problems

def test_probe_is_offline() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = imported & {"sqlite3", "subprocess", "socket", "urllib", "http"}
    assert not forbidden, f"the predicate must stay pure and offline, imports: {sorted(forbidden)}"

def test_gate_is_registered_in_the_audit() -> None:
    audit = (REPO_ROOT / "tools" / "audit.py").read_text(encoding="utf-8")
    assert "test_cron_thinness.py" in audit, (
        "gate not registered in tools/audit.py — an unregistered gate never runs (P29)"
    )
