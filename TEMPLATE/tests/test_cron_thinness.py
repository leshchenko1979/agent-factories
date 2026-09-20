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

THINNESS IS TWO LEGS, AND BOTH MUST HOLD (#120, ruling n=729). A pacemaker row is thin
only when it carries (a) a WAKE — `deliver_to` begins with `session:`, or the prompt
invokes a session notify — AND (b) NO WORK ORDER — an empty prompt carries no work and is
judged on leg (a) alone, while a non-empty prompt must DECLARE itself wake-only by
carrying the canonical marker `do NOT execute any project work yourself`.

Leg (a) alone is NOT sufficient, and this is the correction #120 made. #50 ruled on
exactly this shape: a row carrying a full work order as its prompt AND `deliver_to =
session:<lane>` produces TWO WRITERS ON ONE ACTOR — the work executes inside the cron's
own session, which then wakes the lane — the shape `SKILL.md` section 11 forbids, applied
to an actor rather than to the append path. #50's ruling (n=287, corrected by n=289)
rewrote all five rows to the thin wake-only form and cleared `deliver_to` as well. A
predicate reading only the route therefore passes the very shape P7 exists to prevent,
and #120 measured it: the `#50` shape probed CLEAN, because a problem was appended only
when the wake was `none` and a session target was never examined for work content at all.
The docstring's earlier claim — that a session target is thin BY ROUTE "which is the shape
HQ ruled in #50" — did not survive a read of #50 and is withdrawn.

THE FOUR LIVE SHAPES — and why BOTH fields must be read. Issue #54 measured the first
three against the live table (`cron_jobs`, `enabled=1`, 23 rows, 2026-09-18):

  1. session target      `deliver_to = session:<uuid>`, tiny prompt — the delivery IS the
                         wake. Thin ONLY IF the prompt carries no work order (leg b).
  2. prompt-carried wake `deliver_to = NULL`, the prompt invokes `session notify <uuid>`.
  3. self-executing      a channel or NULL target, and no wake in the prompt — the work
                         runs in the cron's own session. This is the #50 shape.
  4. unbaked target      `deliver_to` is a raw create-time `oc://` URL (#119). The harness
                         refuses it at FIRE time, so the route cannot be read at all.

A predicate reading only `deliver_to` flags every shape-2 row; one reading only the prompt
flags every shape-1 row. Both legs are required, and "thin" is NOT a byte count: the
meta-factory's own correctly-thin pacemaker `factory-triage-patrol` (id
`3673ffec-07af-433c-9aa7-16f47903466c`) has `deliver_to = NULL` and a 1326-byte prompt
whose single command is a wake — measured 2026-09-20, and the width is stated with its
instant because the row is mutable — while a shorter prompt carrying a work order is a
defect. The probes pin exactly that pair, so a future edit that "simplifies" this to a
length test fails loudly.

WHAT THE PREDICATE DOES NOT CLAIM. Both legs are TEXTUAL: the predicate cannot execute a
prompt, so a row that merely DESCRIBES a wake in prose satisfies leg (a), and a row whose
prompt carries the wake-only marker FOLLOWED BY A HIDDEN WORK ORDER satisfies leg (b).
That bound is stated rather than oversold, and the LIVE behavioural check is the
measurement run — its result recorded in the artifact's `## Pacemaker Verification`
section, which `tests/test_law_coverage.py` maps to P7/P28 beside this predicate. The
population judged is the caller's: this file never decides which rows are pacemakers, and
a row it cannot classify at all (neither prompt nor `deliver_to`) is EXCUSED and PRINTED,
never silently clean.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SESSION_TARGET_PREFIX = "session:"
WAKE_ONLY_MARKER = "do NOT execute any project work yourself"
WAKE_RE = re.compile(r"\bsession[\s_]+notify\b", re.IGNORECASE)


def _text(value: object) -> str:
    """The value as text, or '' — a non-string cell is absent, never a crash."""
    return value if isinstance(value, str) else ""


def row_wake(row: dict) -> str:
    """Which wake this row carries: 'session-target', 'prompt-notify', or 'none'."""
    target = _text(row.get("deliver_to")).strip().lower()
    if target.startswith(SESSION_TARGET_PREFIX):
        return "session-target"
    if WAKE_RE.search(_text(row.get("prompt"))):
        return "prompt-notify"
    return "none"


def is_wake_only(prompt: str) -> bool:
    """Leg (b): does this prompt carry no work order?

    An EMPTY or whitespace prompt carries nothing to execute, so it is judged on leg (a)
    alone and returns True. A non-empty prompt must carry the canonical wake-only marker;
    one that does not is a work order by default, and is REPORTED rather than assumed thin.
    The leg is textual and casing-insensitive — the marker is a declaration, and its casing
    is not part of it.
    """
    if not prompt.strip():
        return True
    return WAKE_ONLY_MARKER.lower() in prompt.lower()


def pacemaker_problems(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for a list of cron rows.

    ONE problem per row: the first leg that fails is the row's defect, and a row reported
    for carrying no wake at all is not also reported for its content.
    """
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
        wake = row_wake(row)
        if wake == "none":
            problems.append(
                f"{name}: no wake — deliver_to is {deliver_to or 'NULL'} and the prompt "
                f"invokes no session notify, so this job's own session is the only "
                f"executor (P7: cron is a thin pacemaker trigger, not the worker)"
            )
            continue
        if not is_wake_only(prompt):
            problems.append(
                f"{name}: work order on a waking row — the prompt carries substantive "
                f"work and does not declare itself wake-only with the canonical marker "
                f"'{WAKE_ONLY_MARKER}', so this job's own session executes the work AND "
                f"wakes the target: two writers on one actor (P7: the work belongs in "
                f"the lane, not in the cron)"
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

_SESSION_UUID = "359fe71b-c7a1-420b-b856-acfb49939a7b"

def _row(name: str, prompt: str = "", deliver_to: object = None, **extra: object) -> dict:
    row: dict = {"name": name, "prompt": prompt, "deliver_to": deliver_to}
    row.update(extra)
    return row

def test_a_session_target_with_a_work_order_is_the_50_shape() -> None:
    """The regression pin for #120: the shape #50 ruled on must NOT be clean.

    This probe asserted the OPPOSITE before #120 — that the row was thin BY ROUTE. It is
    the row the ruling was written about: a real 6-hourly pacemaker that delivers to its
    lane's session AND carries a work order in its prompt, so the cron's own session
    executes the cycle and then wakes the lane. Two writers on one actor (#50). The route
    leg passes and the content leg is the one that fails.
    """
    rows = [
        _row(
            "inferhub-hq-pacemaker",
            "Execute the 6-hourly HQ cycle per skills/inferhub/SKILL.md.",
            f"session:{_SESSION_UUID}",
        )
    ]
    assert row_wake(rows[0]) == "session-target", row_wake(rows[0])
    problems, excused = pacemaker_problems(rows)
    assert len(problems) == 1, problems
    assert "inferhub-hq-pacemaker" in problems[0], problems
    assert "work order" in problems[0], problems
    assert "no wake" not in problems[0], problems
    assert excused == [], excused

def test_a_session_target_with_an_empty_prompt_is_clean() -> None:
    """Leg (a) alone: nothing to execute is not a work order, so the delivery IS the wake.

    Both rows carry the same route and differ only in the prompt — empty, and the canonical
    wake-only marker — so this probe pins that the content leg keys on the DECLARATION and
    not on the row having a prompt at all.
    """
    rows = [
        _row("tmp-empty-prompt-wake", "", f"session:{_SESSION_UUID}"),
        _row("tmp-marker-wake", _WAKE_PROMPT, f"session:{_SESSION_UUID}"),
    ]
    assert [row_wake(r) for r in rows] == ["session-target", "session-target"]
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
    """The #54 census shape, recomputed under BOTH legs (#120).

    13 rows fail leg (a): 10 channel workers and 3 null workers, each carrying a work order
    with no wake at all. 5 more fail leg (b): the session targets whose prompt is "Execute
    the cycle per the skill." — a work order on a waking row. The 5 prompt-notify rows carry
    the wake-only marker and stay clean, so the count is 18 and NOT 31, because one problem
    is reported per row: the first leg that fails is the row's defect.
    """
    rows = (
        [_row(f"session-{i}", "Execute the cycle per the skill.", f"session:uuid-{i}") for i in range(5)]
        + [_row(f"null-notify-{i}", _WAKE_PROMPT, None) for i in range(5)]
        + [_row(f"channel-worker-{i}", _WORK_ORDER_PROMPT, f"telegram:-100{i}:{i}") for i in range(10)]
        + [_row(f"null-worker-{i}", _WORK_ORDER_PROMPT, None) for i in range(3)]
    )
    problems, excused = pacemaker_problems(rows)
    assert len(problems) == 18, problems
    assert excused == [], excused
    no_wake = [p for p in problems if "no wake" in p]
    work_order = [p for p in problems if "work order" in p]
    assert len(no_wake) == 13, no_wake
    assert len(work_order) == 5, work_order
    assert all("worker-" in p for p in no_wake), no_wake
    assert all("session-" in p for p in work_order), work_order

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
