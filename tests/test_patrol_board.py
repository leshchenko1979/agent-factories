"""Gate: the board-close leg — #117

Split from tests/test_patrol_host_state.py by #602: one gate per leg, each
carrying its own measured budget, so one slow leg can no longer withhold a
verdict from the whole fleet.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import importlib.util
import io
import json
import os
import sqlite3
import shutil
import subprocess
import tempfile
import datetime as dt
from pathlib import Path
from unittest import mock
import pytest

from patrol_fixtures import (  # noqa: F401
    REPO,
    RUNNER,
    _CLOSE_TS,
    _CLOSE_TS2,
    _PRE_CLOSE_TS,
    _close_anchor,
    _issue,
    _plus,
    _rows,
    _run,
    _scratch,
    _swept,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _close_row(n: int, subject: str, ts: str, detail: str) -> dict:
    return {"n": n, "ts": ts, "event": "close", "actor": "worker",
            "subject": subject, "detail": detail}

# --- this leg's tests -------------------------------------------------------
def test_the_leg_binds_to_the_gate_own_constant_not_a_private_copy() -> None:
    """One field, one predicate: the leg reads the GATE's token and its DECLARED bound key.

    A private copy would be self-consistent on both sides and the drift would be
    invisible — the class this factory has already ruled (n=405 clause 5, n=599). The
    instant itself is FACTORY DATA (#428), so what the leg binds to is the gate's
    `INVARIANT_KEY`; the value is read from this tree's declaration through the one
    reader, and a tree that declares none is a NOT RUN rather than a red.
    """
    assert RUNNER.CLOSE_BOARD_GATE == REPO / "tests" / "test_close_board_recorded.py", (
        f"the leg must bind to the close-board gate, not {RUNNER.CLOSE_BOARD_GATE}"
    )
    gate = RUNNER.load_close_board_gate()
    assert gate.BOARD_TOKEN == "board=closed", gate.BOARD_TOKEN
    assert gate.INVARIANT_KEY == "close_board_recorded", gate.INVARIANT_KEY
    # The leg reaches the DECLARATION through the reader, and the reader's answer is
    # either a well-formed instant or a stated absence — never a third, silent state.
    text, refusal, skip_reason = RUNNER.declared_leg_boundary(REPO, gate.INVARIANT_KEY)
    if refusal:
        raise AssertionError(f"the bound is declared but unreadable: {refusal}")
    if not skip_reason:
        assert text.endswith("Z") and len(text) == 20, text

def test_a_tree_with_NO_declared_bound_does_not_judge_the_bound_dependent_legs() -> None:
    """#428 acceptance, the SKIP arm: absent factory data is a stated NOT RUN, never a red.

    A boundary is factory data, and the shipped half of this byte-identical pair declares
    none — the state every bootstrapped factory is in until it adopts the invariant. So an
    absent bound must not redden the run, and it must not silently pass either: both legs
    say which they are and why, and the intake leg still judges the two arms that ask no
    question about when a rule landed.
    """
    # The `ruling` row is not decoration: since #332 the patrol also asserts the ROUND's
    # own predicate, so a fixture that models a clean board must be a board it has SWEPT.
    # The `claim` for #7 is the OFFLINE arm's population — a subject acted on with no
    # intake row of its own — so the arm that needs the bound is actually exercised.
    issues = [_issue(1, "OPEN")]
    rows = _swept(("intake", "#1", 1), ("ruling", "#1", 2), ("claim", "#7", 3))

    def _undeclared(_repo, key):
        return "", "", f"`{key}` is UNDECLARED in this tree — NOT JUDGED: probe"

    rc, out, _ = _run(issues, rows, board_scope=_undeclared)
    assert rc == 0, f"an absent bound is factory data, not a defect, got rc={rc}\n{out}"
    assert "LEG board-close — NOT RUN" in out, out
    assert "LEG board-closed — NOT RUN" in out, out
    assert "`close_board_recorded` is UNDECLARED in this tree" in out, out
    # The intake leg's bound-independent arms are STILL judged: what was not judged must
    # never read as what was not there (#242).
    assert "LEG board-intake — ASSERTED" in out, out
    assert "1 examined" in out, out
    # ... and the bound-dependent arm says it was not judged, rather than reporting zero.
    assert "declares no boundary for the gate" in out, out

def test_a_MALFORMED_declared_bound_REFUSES_the_board_legs() -> None:
    """#428 acceptance, the FAIL arm: a declared-but-unreadable bound is a DEFECT.

    The reader's policy is absent SKIPS / malformed FAILS, and the leg maps that onto
    NOT RUN versus REFUSED. A malformed declaration hiding behind the same output as none
    at all is the failure this arm exists to catch, so the run must be RED and must name
    the key it could not read.
    """
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 2))

    def _malformed(_repo, key):
        return "", f"`{key}` is declared but cannot be read: not an instant — REFUSED: probe", ""

    rc, out, _ = _run(issues, rows, board_scope=_malformed)
    assert rc == 1, f"a malformed bound is a defect, got rc={rc}\n{out}"
    assert "LEG board-close — REFUSED" in out, out
    assert "LEG board-closed — REFUSED" in out, out
    assert "LEG board-intake — REFUSED" in out, out
    assert "`close_board_recorded` is declared but cannot be read" in out, out

def test_declared_leg_boundary_MAPS_the_readers_three_outcomes() -> None:
    """#428 acceptance: the leg's own reader is DRIVEN, not assumed.

    The two probes above hand the leg a `board_scope`, so they exercise the leg's handling
    of a scope's ANSWER and never `declared_leg_boundary`'s own mapping. Measured while
    writing this: a mutant that re-typed the instant in the SKIP arm, and a mutant that
    downgraded a malformed declaration to a skip, both left those two probes GREEN — the
    mapping between the reader's two exceptions and the leg's NOT RUN / REFUSED was the
    one path in the change with no probe behind it. This drives the reader itself against
    the three trees `ledger_boundary.synthetic_tree` builds, so each outcome has a probe
    that fails on the shape it forbids.
    """
    reader = RUNNER.load_module("ledger_boundary", RUNNER.LEDGER_BOUNDARY)
    key = "close_board_recorded"

    # (1) Nothing declared: the state every bootstrapped factory is in. NOT a defect.
    undeclared = reader.synthetic_tree(_scratch(), rows=[])
    text, refusal, skip_reason = RUNNER.declared_leg_boundary(undeclared, key)
    assert (text, refusal) == ("", ""), (text, refusal)
    assert "UNDECLARED" in skip_reason and key in skip_reason, skip_reason
    assert "NOT JUDGED" in skip_reason, skip_reason

    # (2) Declared and unreadable: a DEFECT, and it must never render as (1).
    malformed = reader.synthetic_tree(_scratch(), rows=[],
                                      invariants={key: "not an instant"})
    text, refusal, skip_reason = RUNNER.declared_leg_boundary(malformed, key)
    assert (text, skip_reason) == ("", ""), (text, skip_reason)
    assert "REFUSED" in refusal and key in refusal, refusal
    assert "cannot be read" in refusal, refusal

    # (3) Declared and readable: the text is the FACTORY's, not one this file carries.
    declared = reader.synthetic_tree(_scratch(), rows=[],
                                     invariants={key: "2026-01-02T03:04:05Z"})
    text, refusal, skip_reason = RUNNER.declared_leg_boundary(declared, key)
    assert (refusal, skip_reason) == ("", ""), (refusal, skip_reason)
    assert text == "2026-01-02T03:04:05Z", text

def test_a_false_board_declaration_is_reported_and_fails_the_run() -> None:
    """#117 acceptance: a close row declaring board=closed for an OPEN issue is a problem.

    This is the NON-VACUITY probe. The live board is clean as this lands, so a leg that
    only ever saw a clean board would have shown nothing — the probe supplies the false
    declaration and asserts the leg bites.
    """
    issues = [_issue(1, "OPEN"), _issue(2, "CLOSED")]
    rows = _rows(("intake", "#1", 1), ("intake", "#2", 2)) + [
        _close_row(3, "#1", _CLOSE_TS, "settled board=closed"),
        _close_row(4, "#2", _CLOSE_TS2, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a false board declaration must fail the run, got rc={rc}\n{out}"
    assert "declares board=closed for #1" in out, out
    assert "still OPEN on the board" in out, out
    assert "2 close row(s) checked" in out, (
        f"the leg must PRINT the population it examined\n{out}"
    )
    assert "close rows (declaring board=closed" in out, (
        f"the leg's own line must state the token it read\n{out}"
    )
    leg_line = out.split("LEG board-close")[1].split("\n")[1]
    assert "2 examined" in leg_line, (
        f"the leg's OWN line must carry the count, not only the verdict's: {leg_line!r}"
    )
    assert "board read at" in out, (
        f"freshness is a property of the INSTANT and must be reported\n{out}"
    )
    assert "#2" not in out.split("LEG board-close")[1].split("LEG ")[0], (
        f"a TRUE declaration must not be reported as a problem\n{out}"
    )

def test_a_true_board_declaration_reads_clean_and_states_its_population() -> None:
    """The complement: a green must be green over a NON-ZERO examined count."""
    issues = [_issue(1, "CLOSED")]
    rows = _rows(("intake", "#1", 1)) + [
        _close_row(2, "#1", _CLOSE_TS, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 0, out
    assert "1 close row(s) checked" in out, out
    assert "0 problem(s) — board read at" in out, out

def test_a_mid_detail_token_is_judged_not_only_a_canonical_trailer() -> None:
    """THE BINDING PROBE. A row carrying the token outside the trailing `=`-run counts.

    Measured on the live ledger: 12 of the 52 post-invariant close rows carry
    `board=closed` outside the canonical trailer (`n=303`, `315`, `327`, `341`, `368`,
    `370`, `372`, `374`, `554`, `565`, `584`, `589`). A leg that re-derived the read via
    `trailer_tokens` would judge 40 and go FALSE-GREEN over those 12.
    """
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1)) + [
        _close_row(2, "#1", _CLOSE_TS,
                   "settled board=closed and then prose trails after it"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"a mid-detail token must still be judged, got rc={rc}\n{out}"
    assert "1 close row(s) checked" in out, out
    assert "declares board=closed for #1" in out, out

def test_a_subject_absent_from_the_board_is_a_problem_not_a_silent_pass() -> None:
    """`absent` and `closed` are different facts; only one is what the row declares."""
    issues = [_issue(1, "CLOSED")]
    rows = _rows(("intake", "#1", 1)) + [
        _close_row(2, "#99", _CLOSE_TS, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 1, out
    assert "no issue #99 exists on the board" in out, out

def test_a_pre_invariant_close_row_is_outside_the_population() -> None:
    """The GATE's own boundary is honoured: a pre-invariant row is not judged here."""
    issues = [_issue(1, "OPEN")]
    # The `ruling` row keeps the fixture inside the round's own population (#332): an OPEN
    # intaken item with no ruling row is a miss, and this probe is about the close board.
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 5)) + [
        _close_row(2, "#1", _PRE_CLOSE_TS, "settled board=closed"),
    ]
    rc, out, _ = _run(issues, rows)
    assert rc == 0, out
    assert "0 close row(s) checked" in out, (
        f"a pre-invariant close row must not enter the population\n{out}"
    )

def test_the_bound_is_DECLARED_DATA_and_moves_the_population() -> None:
    """#428 acceptance: the same fixture, two bounds, two populations.

    This is the arm that catches a hardcoded boundary. A row at `_CLOSE_TS` is judged
    against the declared bound and excluded against a later one — so if the leg ever went
    back to carrying its own literal, ONE of these two runs would disagree with the bound
    it was handed, and the probe would say so.
    """
    issues = [_issue(1, "OPEN")]
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 5)) + [
        _close_row(2, "#1", _CLOSE_TS, "settled board=closed"),
    ]
    declared = _close_anchor()

    def _later(_repo, key):
        return _plus(declared, 24.0), "", ""

    rc_early, out_early, _ = _run(issues, rows)
    assert rc_early == 1, out_early
    assert "1 close row(s) checked" in out_early, out_early
    assert "declares board=closed for #1" in out_early, out_early

    # The SAME row, one day past a later bound: outside the population, so not judged.
    rc_late, out_late, _ = _run(issues, rows, board_scope=_later)
    assert rc_late == 0, out_late
    assert "0 close row(s) checked" in out_late, (
        f"the bound the leg was HANDED must decide the population\n{out_late}"
    )

def main() -> int:
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except pytest.skip.Exception:
            continue
        except AssertionError as exc:
            failures.append(f"{check.__name__}: {exc}")
            print(f"  FAIL  {check.__name__} — {exc}")
        else:
            print(f"  PASS  {check.__name__}")
    print()
    if failures:
        print(f"patrol-runner gate FAILED: {len(failures)} check(s)")
        return 1
    ran = len(checks) - len(_SKIPS)
    skipped = f", {len(_SKIPS)} SKIPPED (nothing to judge)" if _SKIPS else ""
    print(f"patrol-runner gate passed: {ran} check(s){skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
