#!/usr/bin/env python3
"""Gate: a board issue and its ledger `intake` row are two records of one act.

Origin (issue #56). Nothing read the board against the ledger, so an issue could
sit open on the board with no `intake` row — and the other way round: an `intake`
row could name a number the board has never heard of. Each surface was internally
consistent, which is why neither gate saw it. The coverage leg had no upholding
mechanism (P29).

**The predicate is pure and offline.** A repo gate cannot call `gh`: the mechanical
suite must run against a tree, not a live board (`tests/test_close_board_recorded.py`
says the same for the same reason). So the shape is two-part, and this file is part
(a) only: `board_intake_problems(issues, rows)` takes the board issue list and the
ledger rows and returns `(problems, excused)` in the `close_board_problems()` shape.
Part (b) — a host-side runner on the patrol cadence that fetches the board and calls
this — is a later step and is not this file's acceptance.

**Three legs, each with its own list.**

1. **Forward — an OPEN issue with no `intake` row.** Sound over `--state open`,
   because the claim is only about issues the board still calls unfiled. A CLOSED
   issue with no intake row is not reported here: the closed set is not evidence
   about intake, and reporting it would fail every historical issue the factory
   closed by hand.
2. **Reverse — a numeric `intake` row whose issue is not on the board.** Sound
   **only over the full board**, so the caller must say so: with
   `complete_board=False` this leg is skipped rather than guessing, because a
   filtered list would report every issue outside the filter as missing.
3. **Judged — a numeric subject carrying a `claim` or a `close` with no `intake`
   row of its own.** Reported as `excused:` when that activity predates this gate,
   and as a problem otherwise — never folded into a bare clean, so "clean" and
   "excused" are never the same output. The predicate is deliberately NARROWER
   than "carrying ledger activity", and the difference is BY DESIGN: under the
   filing-time intake ordering the ruling and the dispatches are stamped BEFORE
   the intake row, so a subject whose only rows are a ruling or a dispatch is a
   normal window and not a defect — widening this leg to every event would fire
   RED during that window. A board item with no intake row is the BOARD leg's
   concern, owned by the host runner (`tools/patrol_host_state.py`), which reads
   the board whole. Nothing is backfilled: an intake row written today for work
   filed before the gate is a falsified record, not a repair.

**The namespace is why this gate does not fire on every ledger subject.** Ledger
subjects are not all issue references — `methodology-agent-failure-taxonomy` is a
law change, not a board issue. Every leg that asserts about issue references
therefore asserts ONLY over subjects matching `^#\\d+$`, so a descriptive subject
can never be read as a missing or orphaned issue.

Run:  python3 tests/test_board_intake_recorded.py   (or `-m pytest` — same checks)
Exit: 0 all checks pass, 1 a check failed.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from ledger_boundary import evidence_skip_reason as _evidence_skip_reason  # noqa: E402
from ledger_boundary import module_skip as _module_skip  # noqa: E402

import datetime as dt
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# BOTH INVOCATION MODES MUST REACH THE GUARD (#199). The audit invokes this gate in pytest
# mode and pytest never calls `main()`, so a guard there protects only the script-mode run —
# #195's split exactly. `pytestmark` COLLECTS the tests and skips them (exit 0); a module-level
# `pytest.skip` would exit 5, which the audit reads as a failure.
# STATED SKIP: evidence/ledger.jsonl (BOOTSTRAP-created, step 4b)
_SKIP_REASON = _module_skip(REPO)
if _SKIP_REASON:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(True, reason=_SKIP_REASON)

LEDGER = REPO / "evidence" / "ledger.jsonl"

# The day the intake requirement became mechanically gated — the day this gate
# landed. Subjects whose ledger activity predates it are excused, because their
# intake row cannot be written now without backfilling a record that never was.
INVARIANT_LANDED = "2026-09-19T00:00:00Z"

# An issue reference, and nothing else. `#12a` and `# 12` are not references.
ISSUE_SUBJECT = re.compile(r"^#(\d+)$")

def _parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))

def issue_reference(value: object) -> int | None:
    """The issue number a ledger subject names, or None when it names no issue."""
    match = ISSUE_SUBJECT.match(str(value))
    return int(match.group(1)) if match else None

def open_issue_numbers(issues: list[dict]) -> set[int]:
    """The numbers the board still calls open. `state` is compared case-insensitively."""
    numbers: set[int] = set()
    for issue in issues:
        if str(issue.get("state", "")).strip().lower() != "open":
            continue
        number = issue.get("number")
        if isinstance(number, int):
            numbers.add(number)
    return numbers

def intaken_numbers(rows: list[dict]) -> dict[int, object]:
    """Issue number -> the `n` of the intake row that records it.

    Numeric subjects only: a descriptive subject is not an issue reference, so it
    is not evidence about intake in either direction.
    """
    intaken: dict[int, object] = {}
    for row in rows:
        if row.get("event") != "intake":
            continue
        number = issue_reference(row.get("subject"))
        if number is not None and number not in intaken:
            intaken[number] = row.get("n")
    return intaken

def subjects_acted_without_intake(rows: list[dict]) -> list[str]:
    """The OFFLINE leg's population: numeric subjects carrying a `claim` or a
    `close` with no `intake` row of their own.

    This is the leg that produced this gate's verdict, so its count is the
    denominator the verdict travels with (#116). The predicate is deliberately
    NARROWER than "carrying ledger activity": under the filing-time intake ordering
    the ruling and the dispatches are stamped BEFORE the intake row, so a subject
    whose only rows are a ruling or a dispatch is a normal window and is OUTSIDE
    this population by design. A board item with no intake row is the BOARD leg's
    concern, owned by the host runner (`tools/patrol_host_state.py`), which reads
    the board whole.
    """
    intaken = intaken_numbers(rows)
    acted: set[str] = set()
    for row in rows:
        subject = row.get("subject")
        if not isinstance(subject, str) or issue_reference(subject) is None:
            continue
        if row.get("event") in ("claim", "close"):
            acted.add(subject)
    return sorted(s for s in acted if issue_reference(s) not in intaken)

def board_intake_coverage(
    issues: list[dict],
    rows: list[dict],
    complete_board: bool = True,
) -> dict[str, object]:
    """What each leg actually examined, so neither can be read as the other.

    Bullet 4 of #56's acceptance: the forward count and the reverse count are
    reported separately. A single "clean" over a predicate that silently covers one
    direction is the same hole in a new place, so the coverage is a value the caller
    can print, and the direction that was NOT asserted says so in words rather than
    being counted as zero.

    The OFFLINE leg — the one that produced this gate's verdict — reports its own
    population too (`offline_subjects_examined`). A green verdict without its
    denominator is unreadable: "examined 1, 0 problems" and "examined nothing"
    print the same word, which is the hole #116 names. The count is taken through
    `subjects_acted_without_intake`, the same predicate the verdict is reached
    with, so the two cannot drift.
    """
    return {
        "forward_issues_examined": len(open_issue_numbers(issues)),
        "reverse_intake_rows_examined": len(intaken_numbers(rows)),
        "reverse_leg": "asserted over the FULL board" if complete_board
        else "SKIPPED — partial board list, so the reverse direction is not sound",
        "offline_subjects_examined": len(subjects_acted_without_intake(rows)),
        "excused_boundary": INVARIANT_LANDED,
    }

def board_intake_problems(
    issues: list[dict],
    rows: list[dict],
    exempt_before: str = INVARIANT_LANDED,
    complete_board: bool = True,
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for a board issue list against a ledger.

    `issues` is the board as `gh issue list --json number,state` returns it; `rows`
    is the ledger. The two are never merged — the whole point is that they are two
    records and can disagree.
    """
    boundary = _parse_ts(exempt_before)
    problems: list[str] = []
    excused: list[str] = []

    intaken = intaken_numbers(rows)

    # 1. Forward: an open issue the ledger never recorded as filed.
    for number in sorted(open_issue_numbers(issues)):
        if number not in intaken:
            problems.append(
                f"issue #{number} is OPEN on the board with no intake row — the board "
                f"says it is filed and the ledger does not"
            )

    # 2. Reverse: an intake row for a number the board does not carry. Sound only
    #    over the full board, so a partial list skips it instead of guessing.
    if complete_board:
        on_board = {
            issue.get("number") for issue in issues if isinstance(issue.get("number"), int)
        }
        for number, n in sorted(intaken.items()):
            if number not in on_board:
                problems.append(
                    f"intake row n={n} records #{number}, which is not on the board — "
                    f"this leg is only sound over the FULL board"
                )

    # 3. Judged: a numeric subject carrying a `claim` or a `close` with no intake
    #    row of its own — the SAME population the coverage denominator counts, read
    #    through the one predicate below rather than re-derived here.
    first_row: dict[object, tuple[object, str]] = {}
    for row in rows:
        subject = row.get("subject")
        if not isinstance(subject, str) or issue_reference(subject) is None:
            continue
        first_row.setdefault(subject, (row.get("n"), str(row.get("ts") or "")))

    for subject in subjects_acted_without_intake(rows):
        n, ts = first_row.get(subject, (None, ""))
        try:
            when = _parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"subject {subject} (n={n}): unparseable ts {ts!r}")
            continue
        line = (
            f"subject {subject} (first row n={n} at {ts}) carries a claim or a "
            f"close but no intake row of its own"
        )
        if when < boundary:
            excused.append(f"{line} — predates the gate ({exempt_before})")
        else:
            problems.append(line)

    return problems, excused

def _load_rows() -> list[dict]:
    rows: list[dict] = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows

def _row(event: str, subject: str, n: int, ts: str) -> dict:
    return {"n": n, "ts": ts, "event": event, "actor": "hq", "subject": subject,
            "detail": "probe"}

# --- live gate: the ledger's own leg, which needs no board -----------------------

def test_live_ledger_records_its_subjects_as_intakes() -> None:
    """The board directions need a board; this leg needs only the ledger.

    Run with no board list and `complete_board=False` so the two board legs stay
    out of it — the forward leg has nothing to check and the reverse leg is not
    sound over an empty list. What remains is the leg the suite can settle offline.
    """
    rows = _load_rows()
    problems, excused = board_intake_problems([], rows, complete_board=False)
    for line in excused:
        print(f"  excused: {line}")
    if problems:
        raise AssertionError(
            "a subject carrying a claim or a close with no intake row of its own:\n  "
            + "\n  ".join(problems)
        )
    coverage = board_intake_coverage([], rows, complete_board=False)
    print(
        f"board-intake gate (ledger leg): "
        f"offline leg examined {coverage['offline_subjects_examined']} subject(s) "
        f"carrying a claim or a close with no intake row; "
        f"forward examined {coverage['forward_issues_examined']} open issue(s) "
        f"(no board in this offline run); "
        f"reverse examined {coverage['reverse_intake_rows_examined']} intake row(s), "
        f"and {coverage['reverse_leg']}; "
        f"{len(excused)} excused (pre-gate, boundary {coverage['excused_boundary']}) — "
        f"the board legs are probed synthetically here and run for real by the "
        f"host-side runner"
    )

# --- probes: the predicate must reject bad input, not only accept good -----------

def test_an_open_issue_with_no_intake_row_is_reported() -> None:
    problems, excused = board_intake_problems(
        [{"number": 57, "state": "OPEN"}], [], complete_board=False
    )
    assert problems and not excused, (problems, excused)
    assert "#57" in problems[0]

def test_a_closed_issue_with_no_intake_row_is_not_forward_fired() -> None:
    """The forward direction is sound over `--state open` and nowhere else."""
    problems, excused = board_intake_problems(
        [{"number": 9, "state": "CLOSED"}], [], complete_board=False
    )
    assert not problems and not excused, (problems, excused)

def test_an_intake_row_with_no_issue_is_reported_over_the_full_board() -> None:
    rows = [_row("intake", "#1", 1, "2026-09-19T00:00:01Z"),
            _row("intake", "#99", 2, "2026-09-19T00:00:02Z")]
    problems, _excused = board_intake_problems(
        [{"number": 1, "state": "open"}], rows, complete_board=True
    )
    assert len(problems) == 1 and "#99" in problems[0], problems

def test_a_partial_board_skips_the_reverse_direction() -> None:
    """A filtered list would report every issue outside the filter as missing."""
    rows = [_row("intake", "#1", 1, "2026-09-19T00:00:01Z"),
            _row("intake", "#99", 2, "2026-09-19T00:00:02Z")]
    problems, excused = board_intake_problems(
        [{"number": 1, "state": "open"}], rows, complete_board=False
    )
    assert not problems and not excused, (problems, excused)

def test_a_descriptive_subject_never_fires_the_reverse_direction() -> None:
    """A law change is not an issue reference, in either direction."""
    rows = [_row("intake", "methodology-agent-failure-taxonomy", 1, "2026-09-19T00:00:01Z")]
    problems, excused = board_intake_problems([], rows, complete_board=True)
    assert not problems and not excused, (problems, excused)

def test_a_pre_gate_subject_with_no_intake_row_is_excused_not_failed() -> None:
    rows = [_row("close", "#8", 7, "2026-09-12T11:09:57Z")]
    problems, excused = board_intake_problems([], rows, complete_board=False)
    assert not problems and len(excused) == 1, (problems, excused)
    assert "#8" in excused[0]

def test_a_post_gate_subject_with_no_intake_row_is_reported() -> None:
    rows = [_row("close", "#77", 9, "2026-09-19T10:00:00Z")]
    problems, excused = board_intake_problems([], rows, complete_board=False)
    assert problems and not excused, (problems, excused)
    assert "#77" in problems[0]

def test_the_forward_and_reverse_counts_are_printed_separately() -> None:
    """No bare clean: each leg reports what it examined, under its own predicate.

    The two legs must be counted by different predicates over the same input, so
    this probe pins both counts AND the one problem: the forward leg sees a single
    open issue, the reverse leg sees both intake rows, and only the orphaned row
    fires. A leg counted by the other leg's predicate shows up here as 2 where 1
    is required.
    """
    rows = [_row("intake", "#1", 1, "2026-09-19T00:00:01Z"),
            _row("intake", "#99", 2, "2026-09-19T00:00:02Z")]
    issues = [{"number": 1, "state": "open"}, {"number": 2, "state": "CLOSED"}]
    problems, _excused = board_intake_problems(issues, rows, complete_board=True)
    assert len(problems) == 1 and "#99" in problems[0], problems
    assert len(open_issue_numbers(issues)) == 1, "forward leg examined the closed issue"
    assert len(intaken_numbers(rows)) == 2, "reverse leg examined the intake rows"

def test_the_coverage_reports_each_direction_under_its_own_predicate() -> None:
    """Bullet 4: each direction reports its own count, and the skipped one says so."""
    rows = [_row("intake", "#1", 1, "2026-09-19T00:00:01Z"),
            _row("intake", "#99", 2, "2026-09-19T00:00:02Z")]
    issues = [{"number": 1, "state": "open"}, {"number": 2, "state": "CLOSED"},
              {"number": 3, "state": "closed"}]
    full = board_intake_coverage(issues, rows, complete_board=True)
    partial = board_intake_coverage(issues, rows, complete_board=False)
    assert full["forward_issues_examined"] == 1, full
    assert full["reverse_intake_rows_examined"] == 2, full
    assert "asserted" in str(full["reverse_leg"]), full
    assert "SKIPPED" in str(partial["reverse_leg"]), partial
    assert partial["forward_issues_examined"] == full["forward_issues_examined"], (
        "the skipped reverse leg changed what the forward leg examined"
    )

def test_the_offline_denominator_counts_what_the_verdict_judged() -> None:
    """The printed denominator is the population the verdict was reached over.

    A count that drifts from the verdict is worse than no count, so this pins the
    two together on a fixture where one subject is judged and one is not: `#8`
    carries a close and no intake row, `#77` carries both, so the leg examines ONE
    subject and reports ONE line. A denominator counted over every subject would
    read 2 here; one counted over every row would read 3.
    """
    rows = [_row("close", "#8", 7, "2026-09-12T11:09:57Z"),
            _row("intake", "#77", 8, "2026-09-19T09:00:00Z"),
            _row("close", "#77", 9, "2026-09-19T10:00:00Z")]
    problems, excused = board_intake_problems([], rows, complete_board=False)
    coverage = board_intake_coverage([], rows, complete_board=False)
    assert len(problems) + len(excused) == 1, (problems, excused)
    assert coverage["offline_subjects_examined"] == 1, coverage

def test_the_offline_denominator_is_non_zero_on_the_live_ledger() -> None:
    """Acceptance 2 of #116: an emptied population fails loudly, not vacuously.

    The live ledger carries subjects that closed before the intake requirement
    existed, so this population is non-empty by construction. If it is ever zero,
    either the ledger was replaced or the predicate was narrowed to nothing — and a
    clean verdict over an empty population is indistinguishable from a verified
    one, which is the failure this assertion exists to make impossible.
    CORRECTED 2026-09-27. The paragraph above names two cases -- the ledger replaced, or the
    predicate narrowed to nothing -- and misses a third: a REPAIRED ledger. Once every acted
    subject has been backfilled an intake row, `subjects_acted_without_intake` returns []
    legitimately, so requiring it non-empty reds a ledger in its best state. Measured on
    inferhub-watch: 608 rows, predicate returned 0, gate rc=1 with the message below. The
    anchor is therefore the population the leg WALKS, which survives repair, and not the
    defect it counts, which repair erases.
    """
    rows = _load_rows()
    walked = [
        row for row in rows
        if row.get("event") in ("claim", "close")
        and isinstance(row.get("subject"), str)
        and issue_reference(row["subject"]) is not None
    ]
    assert walked, (
        "the offline leg walked NOTHING — a clean verdict over an empty population "
        "is indistinguishable from a verified one (acceptance 2 of #116)"
    )
    examined = subjects_acted_without_intake(rows)
    coverage = board_intake_coverage([], rows, complete_board=False)
    assert coverage["offline_subjects_examined"] == len(examined), coverage

def main() -> int:
    # THE SHIPPED TREE IS NOT A FACTORY (#199). Its `evidence/` is BOOTSTRAP-created, so both
    # the live-ledger and the offline-denominator legs have nothing to read here; without this
    # arm the gate died with FileNotFoundError in the tree it ships from, which is a CRASH
    # rather than a verdict. The reason is printed and names the artifact.
    _skip = _evidence_skip_reason(_Path(__file__).resolve().parent.parent)
    if _skip:
        print(f"board-intake gate: SKIPPED — {_skip}")
        return 0
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        name = check.__name__
        try:
            check()
        except AssertionError as exc:
            failures.append(f"{name}: {exc}")
            print(f"  FAIL  {name} — {exc}")
        else:
            print(f"  PASS  {name}")
    print()
    if failures:
        print(f"board-intake gate FAILED: {len(failures)} check(s)")
        return 1
    print(f"board-intake gate passed: {len(checks)} check(s)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
