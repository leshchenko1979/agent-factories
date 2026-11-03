"""Gate: the workspace-blocked leg — #201

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
    RUNNER,
    _PROBE_TARGET,
    _delivery,
    _issue,
    _run,
    _stall_row,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _gate_row(n, subject, paths, *, event="score", gate="blocked-by-unowned"):
    """One governed-run row whose canonical trailer declares a workspace gate.

    `paths=None` omits `blocked_paths=` entirely; `paths=[]` writes it EMPTY. Both are the
    unexaminable shape the ruling refuses, and both must bite.
    """
    detail = "a governed run closed its workspace gate"
    detail += f" workspace_gate={gate}"
    if paths is not None:
        detail += f" blocked_paths={','.join(paths)}"
    return {"n": n, "event": event, "subject": subject, "detail": detail}

def _questions_homes_repo(root: Path, kind: str) -> Path:
    """A hermetic tree whose `tests/test_kit_questions_homes.py` answers with `kind`'s shape.

    THE STUB IS THE POINT, not a shortcut (#530). The leg under test is a RUNNER of the real
    gate, so the behaviour it adds is the CLASSIFICATION of that gate's answer -- and a probe
    that pointed at the real gate would have its verdict decided by whichever adoption this
    box's executing home happens to carry, which is precisely the live surface the leg exists
    to watch. A stub lets both arms be BUILT, so the STALE arm is proved to fire rather than
    assumed to.
    """
    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    bodies = {
        "in-step": (
            'print("template home : TEMPLATE/tools/questions (100 B)")\n'
            'print("executing home: /tmp/probe-exec-questions (120 B)")\n'
            'print("population    : 7 differing line(s) examined")\n'
            'print("OK: the difference is confined to the declared layer "\n'
            '      "(2 parameter entries + 1 named local fix + 3 declared block(s))")\n'
            'raise SystemExit(0)\n'
        ),
        "stale": (
            'print("template home : TEMPLATE/tools/questions (100 B)")\n'
            'print("executing home: /tmp/probe-exec-questions (120 B)")\n'
            'print("population    : 9 differing line(s) examined")\n'
            'print("")\n'
            'print("FAIL: 2 line(s) diverge OUTSIDE the declared parameter layer:")\n'
            'print("  \'the template-only landing\'")\n'
            'raise SystemExit(1)\n'
        ),
        "not-run": (
            'print("NOT RUN -- the executing copy is not resolvable on this host, so this leg")\n'
            'print("  examined NOTHING: no candidate matched the backend glob")\n'
            'print("  (a member factory has no executing tree; this is not a clean verdict)")\n'
            'raise SystemExit(0)\n'
        ),
        "shape-changed": (
            'print("something else entirely")\n'
            'raise SystemExit(0)\n'
        ),
    }
    (tests / "test_kit_questions_homes.py").write_text(bodies[kind], encoding="utf-8")
    return root

def _late_stamp_row(n: int, *, now: dt.datetime, subject: str = "#77",
                    declared: dt.datetime | None = None, days_ago: float = 1 / 24.0) -> dict:
    """A dispatch row whose `ts` is a WRITE instant LATER than the instant it declares (#432).

    The live specimen this shape is taken from: row `n=2787` (`#428`) carries
    `ts 2026-10-07T12:26:04Z` -- a batched ledger write -- while its own detail declares
    `resolved_at 2026-10-07T12:11:46Z`, and the notify it records landed at `12:11:28Z`. One
    fixture, because a window built from `ts` alone misses that delivery by 11m36s while a
    window built from the declaration contains it.
    """
    detail = "DISPATCH to the probe lane, resolved LIVE this turn"
    if declared is not None:
        detail += f" (resolved_at {declared.strftime('%Y-%m-%dT%H:%M:%SZ')})"
    return _stall_row(n, "dispatch", subject, days_ago, now=now, actor="triage",
                      detail=detail, refs=[{"session": _PROBE_TARGET}])

def _row_with_lag(n: int, *, ts: dt.datetime, lag_secs: float, subject: str = "#90") -> dict:
    """A dispatch row whose detail QUOTES `resolved_at` an exact LAG behind its write stamp.

    `ts` is written to the second and `days_ago=0`, so the lag is exact and the boundary pair
    below is a statement about the bound rather than about rounding.
    """
    declared = ts - dt.timedelta(seconds=lag_secs)
    return _stall_row(
        n, "dispatch", subject, 0, now=ts, actor="triage",
        detail="DISPATCH to the probe lane, resolved LIVE this turn "
               f"(resolved_at {declared.strftime('%Y-%m-%dT%H:%M:%SZ')})",
        refs=[{"session": _PROBE_TARGET}],
    )

def _messages_db(path: Path, *messages: tuple[str, str]) -> None:
    """A throwaway OpenCrabs home holding real `messages` rows — the landed-notify read path.

    `box_deliveries` consumes the header form in its SQL `like` clause, so a probe that
    injected delivery DICTS would pass whichever header it was handed and prove nothing about
    the predicate. This builds the SHAPE the live box has and reads it through the runner's
    own function (#426).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "create table messages "
        "(session_id text, role text, content text, created_at integer)"
    )
    conn.execute(
        "create table notify_queue "
        "(session_id text, display_text text, context_text text, created_at integer)"
    )
    stamp = int(dt.datetime.now(dt.timezone.utc).timestamp())
    conn.executemany(
        "insert into messages (session_id, role, content, created_at) values (?,?,?,?)",
        [(session, "user", text, stamp) for session, text in messages],
    )
    conn.commit()
    conn.close()

# --- this leg's tests -------------------------------------------------------
def test_the_workspace_blocked_leg_BITES_on_a_declaration_that_names_no_paths() -> None:
    """The unexaminable excuse is a PROBLEM, not a silent pass (the ruling's refusal)."""
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(1, "survey-x", None)], read_at="2026-10-05T00:00:00Z",
        dirty_paths_fn=lambda: set(),
    )
    assert leg["status"] == "ASSERTED", leg
    assert leg["coverage"]["blocked_declarations"] == 1, leg["coverage"]
    assert any("names NO blocking paths" in p for p in leg["problems"]), leg["problems"]

def test_the_workspace_blocked_leg_BITES_on_an_EMPTY_paths_value() -> None:
    """`blocked_paths=` with no value is a MENTION, not a declaration — it must bite too."""
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(2, "survey-y", [])], read_at="2026-10-05T00:00:00Z",
        dirty_paths_fn=lambda: set(),
    )
    assert any("names NO blocking paths" in p for p in leg["problems"]), leg["problems"]

def test_the_workspace_blocked_leg_REPORTS_a_path_no_longer_dirty() -> None:
    """The cross-read separates the still-stranded from the settled, and never reds on the
    settled half — a declaration true at its instant is history, not a permanent defect."""
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(3, "survey-z", ["evidence/a.md", "evidence/b.md"])],
        read_at="2026-10-05T00:00:00Z",
        dirty_paths_fn=lambda: {"evidence/a.md"},
    )
    assert leg["problems"] == [], leg["problems"]
    entry = leg["coverage"]["blocked_rows"][0]
    assert entry["still_dirty"] == ["evidence/a.md"], entry
    assert entry["no_longer_dirty"] == ["evidence/b.md"], entry

def test_the_workspace_blocked_leg_is_LOUD_on_a_zero_population() -> None:
    """Zero blocked declarations is NOT RUN with its reason, never a clean HOLD (#242)."""
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(4, "survey-clean", None, gate="rc=0")],
        read_at="2026-10-05T00:00:00Z", dirty_paths_fn=lambda: set(),
    )
    assert leg["status"] == "NOT RUN", leg
    assert "zero is LOUD" in leg["coverage"]["reason"], leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

def test_the_workspace_blocked_leg_goes_NOT_RUN_when_the_tree_is_UNREADABLE() -> None:
    """A cross-reader that cannot read the tree has corroborated nothing — never "all cleared"."""
    def boom():
        raise RUNNER.BoardReadError("git status exited 128: not a git repository")
    leg = RUNNER.workspace_blocked_leg(
        [_gate_row(5, "survey-w", ["evidence/a.md"])],
        read_at="2026-10-05T00:00:00Z", dirty_paths_fn=boom,
    )
    assert leg["status"] == "NOT RUN", leg
    assert "unreadable" in leg["coverage"]["reason"], leg["coverage"]

def test_a_MENTION_of_the_blocked_token_is_not_a_declaration() -> None:
    """The read is the POSITIONAL trailer, never a substring: a row that cites the token in
    prose — a dispatch, a ruling, the ledger repair that appended it — is not a run, and
    counting it would be this reader's own echo mistaken for evidence (AGENTS.md rule 7)."""
    rows = [
        {"n": 6, "event": "dispatch", "subject": "#201",
         "detail": "GOAL: the verdict workspace_gate=blocked-by-unowned is lawful"},
        {"n": 7, "event": "score", "subject": "survey-v",
         "detail": "this run cites workspace_gate=blocked-by-unowned in prose, not as a "
                   "trailer, so it declares nothing"},
    ]
    leg = RUNNER.workspace_blocked_leg(
        rows, read_at="2026-10-05T00:00:00Z", dirty_paths_fn=lambda: set(),
    )
    assert leg["coverage"]["blocked_declarations"] == 0, leg["coverage"]
    assert leg["status"] == "NOT RUN", leg

def test_the_workspace_blocked_leg_is_WIRED_and_bites_through_main() -> None:
    """End to end: a no-paths declaration in the ledger REDs the run and the leg is printed."""
    rc, out, _ = _run(
        [], [_gate_row(8, "survey-u", None)],
        dirty_paths_fn=lambda: set(),
    )
    assert rc == 1, f"an unexaminable declaration must fail the run\n{out}"
    assert "LEG workspace-blocked" in out, out
    assert "NO paths named" in out, out

def test_the_workspace_blocked_leg_is_INJECTABLE_and_wired_by_default() -> None:
    """`dirty_paths_fn` is a real parameter, and the live tree read is the default."""
    import inspect
    params = inspect.signature(RUNNER.main).parameters
    assert "dirty_paths_fn" in params, sorted(params)
    assert hasattr(RUNNER, "live_dirty_paths"), "the live tree read must exist"

def test_the_board_unruled_leg_BITES_and_discriminates_on_every_neighbour() -> None:
    """#332 acceptance (a): the round's own predicate -- an OPEN item carrying an `intake`
    row and NO `ruling` row -- is DETECTED past the threshold, and the five neighbours that
    look like it stay quiet.

    The neighbours are the whole point, because each is a live false positive a naive
    reading ("any open item without a ruling row") would report: a fresh item is IN FLIGHT,
    a ruled item is out of the population, a CLOSED item owes the round nothing, an item
    with no intake row belongs to `board_intake_leg`, and a ruling stamped under a
    DESCRIPTIVE subject governs its item through the resolver's `declared` arm. A probe
    that supplied only the true positive would pass a leg that reported all six.

    The defect this reproduces, measured 2026-10-05 (#332): #327 carried intake n=2380 at
    12:07:20Z, was OPEN, and had no `ruling` row when the round swept at 12:50Z -- and
    nothing went red, because no leg had this population.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(921, "OPEN"),    # intaken 2 d ago, NO ruling row -> OWED
        _issue(922, "OPEN"),    # intaken 1 h ago, no ruling row -> in flight
        _issue(923, "OPEN"),    # intaken, and RULED (strict `#923`)
        _issue(924, "CLOSED"),  # intaken and unruled, but the board closed it
        _issue(925, "OPEN"),    # unruled and open, but carries NO intake row
        _issue(926, "OPEN"),    # ruled under a DESCRIPTIVE subject, via `governs=`
    ]
    rows = [
        _stall_row(21, "intake", "#921", 2, now=now),
        _stall_row(22, "intake", "#922", 1 / 24, now=now),
        _stall_row(23, "intake", "#923", 3, now=now),
        _stall_row(24, "ruling", "#923", 2.9, now=now),
        _stall_row(25, "intake", "#924", 3, now=now),
        _stall_row(26, "close", "#924", 2.5, now=now),
        _stall_row(27, "intake", "#926", 3, now=now),
        _stall_row(28, "ruling", "concern-probe", 2.9, now=now,
                   detail="governs=926"),
    ]

    leg = RUNNER.board_unruled_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "#921" in named, f"the unruled intaken item must be NAMED\n{named}"
    for quiet in ("#922", "#923", "#924", "#925", "#926"):
        assert quiet not in named, (
            f"{quiet} must NOT be reported: a fresh item is in flight, a ruled one is out "
            f"of the population, a closed one owes the round nothing, an item with no "
            f"intake row belongs to the intake leg, and a `governs=` ruling IS a ruling"
            f"\n{named}"
        )
    assert leg["coverage"]["items_owed_ruling"] == 1, leg["coverage"]
    assert leg["coverage"]["population_unruled"] == 2, leg["coverage"]

    # ... and the same fixture through the REAL `main()`: the report must carry the leg,
    # the OWED line AND the population it was read from. A leg returning a correct dict
    # while the render drops it is the half-fix this half exists to catch. (#925 also REDs
    # `board-intake` here, deliberately: it is the boundary between the two legs -- an open
    # item with NO intake row is that leg's population, not this one's.)
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "LEG board-unruled — ASSERTED" in out, out
    assert "#921 is OPEN on the board" in out, out
    assert "population (OPEN, intake row, NO ruling row): 2 item(s) -- 1 past" in out, out
    assert "board read at " in out, out

def test_the_board_unruled_leg_PRINTS_an_EMPTY_population_rather_than_silence() -> None:
    """#332 acceptance (b): a clean sweep over an EMPTY population is distinguishable from
    a leg that examined nothing -- the population count and the board read instant are
    PRINTED, and the run is GREEN.

    This is the criterion the defect itself turns on: #327 was skipped by the round and
    NOTHING went red, so a leg that stayed silent on an empty population would reproduce
    the very failure it exists to detect. The discriminating control is the fixture with
    the `ruling` row REMOVED, which fires -- driven in the arm above -- so this one proves
    the leg's own empty read is PRINTED, not merely that it is quiet.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(931, "OPEN")]
    rows = [
        _stall_row(31, "intake", "#931", 5, now=now),
        _stall_row(32, "ruling", "#931", 4.9, now=now),
        # The ruling is DISPATCHED and CLAIMED (#519): a ruled item with no dispatch row
        # naming it is a defect in its own right, so the clean fixture must carry the act.
        _stall_row(33, "dispatch", "#931", 4.8, now=now),
        _stall_row(34, "claim", "#931", 4.7, actor="worker", now=now),
    ]

    leg = RUNNER.board_unruled_leg(issues, rows, read_at=read_at)
    assert leg["problems"] == [], leg
    assert leg["coverage"]["population_unruled"] == 0, leg["coverage"]
    assert leg["coverage"]["board_read_at"] == read_at, leg["coverage"]
    assert leg["coverage"]["open_items_examined"] == 1, leg["coverage"]

    rc, out, _ = _run(issues, rows)
    assert rc == 0, f"a ruled item is not a defect, got rc={rc}\n{out}"
    assert "LEG board-unruled — ASSERTED" in out, out
    assert "population (OPEN, intake row, NO ruling row): 0 item(s) -- 0 past" in out, out
    assert f"board read at {read_at}" in out, out

def test_the_board_unruled_leg_PRINTS_its_threshold_with_its_basis() -> None:
    """#332: the threshold and the basis it rests on are PRINTED on every run, never
    carried in a reader's memory -- and the basis must NAME the round's own cadence it is
    derived from, or the value reads as a chosen number.

    Asserted on the RENDER, not on the constant: a basis declared in a module constant and
    dropped from the report is the same failure as one never written.
    """
    rc, out, _ = _run([_issue(931, "OPEN")], [])
    assert "LEG board-unruled — ASSERTED" in out, out
    assert "past the declared threshold of 6.0 h" in out, out
    assert "threshold basis: 6.0 h" in out, out
    assert "HQ round cadence" in out, (
        f"the basis must name the round's own cadence it is taken from\n{out}"
    )

def test_the_board_unruled_leg_resolves_the_RULING_namespace_and_PRINTS_an_unplaced_row() -> None:
    """#332 + #243 clause 2: the RULING namespace is resolved through the ruling leg's own
    three arms -- so a ruling written under a SLUG and bridged by a later row that
    references its `n` still clears its item -- and a ruling row that resolves to NO issue
    is LISTED, never silently dropped.

    Dropping an unplaced row would report a smaller ruled set than was read, and the leg
    would then fire on an item that is in fact ruled -- a false red no reader could
    re-litigate. So the row is printed, and the item it fails to clear stays OWED.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(941, "OPEN"), _issue(942, "OPEN")]
    rows = [
        _stall_row(41, "intake", "#941", 3, now=now),
        _stall_row(42, "ruling", "slug-probe", 2.9, now=now),
        # the DISPATCH BRIDGE: a later row POINTS AT the ruling (`ref row:42`) and names the
        # issue — the typed pointer is what makes it ownership rather than a quotation
        _stall_row(43, "dispatch", "#941", 2.8, now=now,
                   detail="Ruling n=42 ref row:42"),
        _stall_row(44, "intake", "#942", 3, now=now),
        _stall_row(45, "ruling", "another-slug-probe", 2.9, now=now),
    ]

    leg = RUNNER.board_unruled_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "#941" not in named, (
        f"a bridged ruling IS a ruling, and its item must not be reported\n{named}"
    )
    assert "#942" in named, f"an unplaced ruling clears nothing\n{named}"
    assert leg["coverage"]["resolution_arms"]["bridged"] == 1, leg["coverage"]
    assert leg["coverage"]["rulings_unbridgeable"] == 1, leg["coverage"]
    assert leg["coverage"]["unbridgeable_rows"][0]["n"] == 45, leg["coverage"]

    rc, out, _ = _run(issues, rows)
    assert "unbridgeable" in out, out
    assert "bridged 1" in out, out

def test_the_questions_homes_leg_REPORTS_a_stale_home_and_NEVER_reads_rc_alone() -> None:
    """#530: the executing home is watched, and `rc == 0` is never the verdict by itself.

    THE ZERO THAT IS NOT A PASS IS THE ARM THAT MATTERS. The gate exits 0 both when the
    difference is confined to the declared layer AND when the executing copy is not
    resolvable -- and its own words say the second is "not a clean verdict". A leg that read
    `rc == 0` as "in step" would print a clean sweep over no population, which is the defect
    class this leg was ordered to catch, one surface over.

    AND A STALE HOME IS A REPORT, NOT THIS FACTORY'S EXIT CODE (HQ's ruling: patrol, not
    floor). The executing copy is a BOX surface another lane adopts; a leg that reddened this
    factory for it would make our verdict a function of that lane's backlog -- and, worse, a
    FLOOR gate reading another home could not be repaired by the lane it refuses, which is
    exactly the lockout the ruling withdrew.
    """
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="probe-530-"))

    # ARM 1 -- a real comparison reads IN STEP, and its population is CARRIED, not dropped.
    in_step = RUNNER.questions_homes_leg(repo=_questions_homes_repo(tmp / "a", "in-step"),
                                         read_at="2026-10-24T12:00:00Z")
    assert in_step["status"] == "ASSERTED", f"arm1 status {in_step['status']!r}"
    assert in_step["coverage"]["in_step"] is True, f"arm1 in_step {in_step['coverage']}"
    assert in_step["coverage"]["stale"] is False, "arm1 stale"
    assert in_step["problems"] == [], f"arm1 problems {in_step['problems']}"
    assert in_step["coverage"]["population"] == 7, f"arm1 population {in_step['coverage']}"
    assert in_step["coverage"]["declared_blocks"] == 3, f"arm1 declared_blocks {in_step['coverage']}"

    # ARM 2 -- a STALE home is ASSERTED (it examined a population) and carries the gate's own
    # diagnosis, and it raises NO problem: report, not enforce.
    stale = RUNNER.questions_homes_leg(repo=_questions_homes_repo(tmp / "b", "stale"),
                                       read_at="2026-10-24T12:00:00Z")
    assert stale["status"] == "ASSERTED", f"arm2 status {stale['status']!r}"
    assert stale["coverage"]["stale"] is True, f"arm2 stale {stale['coverage']}"
    assert stale["coverage"]["in_step"] is False, "arm2 in_step must be False"
    assert stale["problems"] == [], f"arm2 a stale executing home must NOT move this factory's exit code: {stale['problems']}"
    assert any("OUTSIDE the declared parameter layer" in line
              for line in stale["coverage"].get("diagnosis") or []), f"arm2 diagnosis lost the gate's own word: {stale['coverage'].get('diagnosis')}"

    # ARM 3 -- THE ZERO THAT IS NOT A PASS: rc 0 with the gate's own NOT RUN marker must be
    # examined-nothing, never "in step". This is the arm a naive `rc == 0` reading fails.
    not_run = RUNNER.questions_homes_leg(repo=_questions_homes_repo(tmp / "c", "not-run"),
                                         read_at="2026-10-24T12:00:00Z")
    assert not_run["status"] == "NOT RUN", f"arm3 status {not_run['status']!r}"
    assert not_run["coverage"]["in_step"] is False, f"arm3 rc=0 was read as in-step: {not_run['coverage']}"
    assert not_run["problems"], "arm3 an unresolvable executing copy examined NOTHING and must say so"
    assert "not resolvable" in not_run["problems"][0], f"arm3 problem {not_run['problems'][0]!r}"
    assert "no candidate matched the backend glob" in (not_run["coverage"].get("reason") or ""), f"arm3 the gate's own reason was lost: {not_run['coverage'].get('reason')!r}"

    # ARM 4 -- a gate whose OUTPUT SHAPE changed must red as UNREADABLE, never pass as clean.
    changed = RUNNER.questions_homes_leg(repo=_questions_homes_repo(tmp / "d", "shape-changed"),
                                         read_at="2026-10-24T12:00:00Z")
    assert changed["status"] == "FAILED", f"arm4 status {changed['status']!r}"
    assert changed["problems"], "arm4 an unreadable verdict must be UNKNOWN, not in step"
    assert "without printing either" in changed["problems"][0], f"arm4 problem {changed['problems'][0]!r}"

    # ARM 5 -- a home that CARRIES the gate's subject but not the gate is this factory's own
    # defect: something exists to watch and nothing is watching it.
    subject_only = tmp / "subject-only"
    (subject_only / "TEMPLATE" / "tools" / "questions").mkdir(parents=True, exist_ok=True)
    absent = RUNNER.questions_homes_leg(repo=subject_only, read_at="2026-10-24T12:00:00Z")
    assert absent["status"] == "FAILED", f"arm5 status {absent['status']!r}"
    assert absent["problems"] and "missing" in absent["problems"][0], f"arm5 problem {absent['problems']}"

    # ARM 5b -- THE LOCKOUT ARM. A home with NO template home carries no subject, and this leg
    # SHIPS into such homes through the twin law, so a missing gate there must read NOT
    # APPLICABLE with its reason and raise NO problem -- otherwise every bootstrapped factory
    # inherits a RED it cannot repair. Measured 2026-10-24: the TEMPLATE copy of this very suite
    # redded on exactly this, the leg refusing the tree the twin law ships it into.
    no_subject = RUNNER.questions_homes_leg(repo=tmp / "nope", read_at="2026-10-24T12:00:00Z")
    assert no_subject["status"] == "NOT RUN", f"arm5b status {no_subject['status']!r}"
    assert no_subject["problems"] == [], (
        f"arm5b a home with no subject must raise NO problem: {no_subject['problems']}")
    assert no_subject["coverage"]["not_applicable"] is True, f"arm5b coverage {no_subject['coverage']}"
    assert "no subject here" in (no_subject["coverage"].get("reason") or ""), (
        f"arm5b reason {no_subject['coverage'].get('reason')!r}")

    # ARM 6 -- the round RENDERS the finding and its exit code is UNCHANGED by it: the leg
    # reports a stale home while the round stays green on everything else.
    rc, out, _err = _run([], [], questions_homes={
        "repo": _questions_homes_repo(tmp / "e", "stale"),
    })
    assert "STALE EXECUTING HOME" in out, f"arm6 the stale home was not printed:\n{out[-2000:]}"
    assert "probe-exec-questions" in out, "arm6 the stale home's path was not named"
    assert "reported, not enforced" in out, "arm6 the print must say it is a report"
    assert rc == 0, f"arm6 a stale executing home moved the round's exit code: rc={rc}"

    # ... and the IN-STEP arm renders as a measurement, so the two never share a phrasing.
    rc2, out2, _err2 = _run([], [], questions_homes={
        "repo": _questions_homes_repo(tmp / "f", "in-step"),
    })
    assert "in step:" in out2, f"arm6b the in-step reading was not printed:\n{out2[-2000:]}"
    assert "STALE EXECUTING HOME" not in out2, "arm6b an in-step round printed STALE"
    assert rc2 == 0, f"arm6b rc={rc2}"

    # ARM 7 -- the NOT-APPLICABLE round RENDERS its reason and stays GREEN: the exact shape that
    # redded the TEMPLATE twin's own suite.
    rc3, out3, _err3 = _run([], [], questions_homes={"repo": tmp / "nope"})
    assert "NOT RUN:" in out3, f"arm7 the N/A leg did not render a NOT RUN:\n{out3[-2000:]}"
    assert "no subject here" in out3, "arm7 the N/A reason was lost in the render"
    assert rc3 == 0, f"arm7 rc={rc3}"

    print("questions-homes leg: 8 arms bit (in-step, stale, rc-0-not-run, shape-changed, "
          "absent-with-subject, absent-without-subject, render, render-not-applicable)")

def test_the_intake_partition_is_NAMED_and_CLOSES_and_NAMES_every_orphan() -> None:
    """#548 (ruling n=4146): the intake side must name ALL THREE buckets and assert its own
    sum, because the shape it replaced -- `549 rows (540 naming an issue)` -- invited the
    reader to infer "9 intake rows name no issue" and that inference was wrong twice over.

    Measured on this ledger 2026-10-24: 559 intake rows, 550 DISTINCT issues, 5 REPEATED
    rows, 4 genuinely orphaned. The old printout collapsed three buckets into one number
    and the four orphans were invisible on the intake side while the ruling side printed
    its own unbridgeable list -- one leg, two halves, one of them silent.

    The fixture is hermetic and the live ledger is CORROBORATION only: a control that reads
    live state stops being a control the moment the population moves, and a clean
    `unbridgeable == 0` is exactly the reading the ruling forbids trusting (#548 binding 3).
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(941, "OPEN"), _issue(942, "OPEN")]
    # n=46 is the ORPHAN: an intake row whose subject names no issue and which carries no
    # typed `ref row:` pointer, so no arm can resolve it.
    rows = [
        _stall_row(41, "intake", "#941", 3, now=now),
        _stall_row(42, "ruling", "#941", 2.9, now=now),
        _stall_row(43, "intake", "#942", 3, now=now),
        # the REPEAT: a second intake row for an issue already intaken. The ledger keeps
        # both, the predicate keeps the first, so the extra row must be NAMED as a repeat
        # rather than left to look like an orphan.
        _stall_row(44, "intake", "#942", 2.95, now=now),
        _stall_row(45, "ruling", "#942", 2.9, now=now),
        _stall_row(46, "intake", "orphan-slug-probe", 3, now=now,
                   detail="no pointer to any row here"),
    ]

    leg = RUNNER.board_unruled_leg(issues, rows, read_at=read_at)
    cov = leg["coverage"]
    # THE PARTITION CLOSES: every intake row lands in exactly one bucket.
    assert cov["intake_rows_read"] == 4, cov
    assert cov["intake_rows_resolved"] == 2, cov           # DISTINCT issues
    assert cov["intake_rows_resolved_rows"] == 3, cov      # ROWS that resolved
    assert cov["intake_repeated"] == 1, cov
    assert cov["intake_unbridgeable_rows"] == 1, cov
    assert cov["intake_partition_closes"] is True, cov
    assert cov["intake_numbers_agree"] is True, cov
    assert 2 + 1 + 1 == cov["intake_rows_read"], cov
    # The orphan is NAMED with its row number and its own subject, not merely counted.
    assert [e["n"] for e in cov["intake_unbridgeable"]] == [46], cov
    assert cov["intake_unbridgeable"][0]["subject"] == "orphan-slug-probe", cov
    # ... and a partition that closes raises NO problem: the sum is a gate, not decoration.
    assert not leg["problems"], leg["problems"]

    rc, out, _ = _run(issues, rows)
    assert "REPEATED" in out, out
    # the fixture carries ONE orphan, and the count must be the fixture's own -- not the
    # live ledger's 4, which is corroboration and never the control.
    assert "1 unbridgeable" in out, out
    assert "UNBRIDGEABLE intake row n=46 ('orphan-slug-probe')" in out, out
    # The ruling half must still print: repairing the intake half by orphaning the ruling
    # half would swap one silent bucket for another.
    assert "ruling rows read:" in out, out

    # NO-ORPHAN CONTROL: the same fixture minus the orphan still closes, and prints no
    # UNBRIDGEABLE line. Without this arm a leg that printed an orphan unconditionally
    # would pass the positive probe.
    clean = [r for r in rows if r["n"] != 46]
    leg_clean = RUNNER.board_unruled_leg(issues, clean, read_at=read_at)
    cov_clean = leg_clean["coverage"]
    assert cov_clean["intake_rows_read"] == 3, cov_clean
    assert cov_clean["intake_repeated"] == 1, cov_clean
    assert cov_clean["intake_unbridgeable_rows"] == 0, cov_clean
    assert cov_clean["intake_partition_closes"] is True, cov_clean
    assert not leg_clean["problems"], leg_clean["problems"]
    _rc, out_clean, _ = _run(issues, clean)
    assert "UNBRIDGEABLE intake row" not in out_clean, out_clean
    assert "0 unbridgeable" in out_clean, out_clean

def test_the_dispatch_delivery_leg_BITES_and_clears_on_a_delivery() -> None:
    """#49 acceptance (1) and (2): the leg NAMES a dispatch row with no delivery inside its
    window, and the SAME fixture with a delivery produces no problem.

    Both halves are asserted, because a leg that reported every row would pass the first
    alone and a leg that reported none would pass the second.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(51, "dispatch", "#77", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])

    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    named = "\n".join(leg["problems"])
    assert leg["status"] == "ASSERTED", leg
    assert "n=51" in named and "#77" in named, f"the phantom must be NAMED\n{named}"
    assert leg["coverage"]["dispatch_rows_examined"] == 1, leg["coverage"]

    delivered = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched + dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nDISPATCH #77 to the Worker")],
            ["probe-home"], [],
        ),
    )
    assert delivered["problems"] == [], delivered["problems"]

def test_the_dispatch_delivery_leg_anchors_on_the_ROWS_OWN_ts_not_the_newest_row() -> None:
    """#49 acceptance (3): the `#77` shape, asserted directly.

    A LATER row exists on the same subject, so a leg that anchored on the subject's NEWEST
    row would open its window after the delivery it is testing for and report a confident
    miss -- the exact error the first census made (ledger n=1893). The delivery here lands
    60 s after the DISPATCH row and two hours BEFORE the later row, so only a
    row-own-`ts` anchor can see it.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=3)
    dispatch = _stall_row(61, "dispatch", "#77", 0, now=dispatched, actor="triage",
                          refs=[{"session": _PROBE_TARGET}])
    later = _stall_row(62, "claim", "#77", 0, now=dispatched + dt.timedelta(hours=2))
    delivered_at = dispatched + dt.timedelta(seconds=60)

    leg = RUNNER.dispatch_delivery_leg(
        [dispatch, later], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(delivered_at, "[session-notify from=abc]\nDISPATCH #77")],
            ["probe-home"], [],
        ),
    )
    assert leg["problems"] == [], (
        f"a newest-row anchor would miss a delivery that is inside the ROW's own window\n"
        f"{leg['problems']}"
    )

def test_the_dispatch_delivery_token_is_no_narrower_than_the_artifact() -> None:
    """#49 acceptance (4): a delivery carrying the BARE subject number clears a dispatch
    written `#77`, and a WIDER token (a longer number containing 77) does not count.

    The first census searched `#77` where the artifact carried `77` and returned a zero
    that read as good news. The mirror error -- a substring test that lets `77` match
    inside `177` -- is just as silent, so both directions are asserted.
    """
    assert RUNNER.delivery_subject_matches("DISPATCH 77 to the Worker", "#77")
    assert RUNNER.delivery_subject_matches("DISPATCH #77", "#77")
    assert RUNNER.delivery_subject_matches("wave-2026-10-05 begins", "wave-2026-10-05")
    assert not RUNNER.delivery_subject_matches("row 177 of the table", "#77")
    assert not RUNNER.delivery_subject_matches("row 770 of the table", "#77")
    assert not RUNNER.delivery_subject_matches("#177 was closed", "#77")

    # #425: a hex continuation is the SAME class of silent over-match. The digits of a
    # commit sha (`423f233`) or of an identifier that continues in hex letters (`x423y`)
    # are not a `#423` subject, and a digit-only boundary matched BOTH -- so a delivery
    # naming an unrelated artifact cleared the leg. A longer NUMBER (`41423f5`) and a
    # longer ALPHANUMERIC token (`B4239.log`) already failed on the digit boundary and must
    # keep failing; a legitimate mention (`FILED as #423`) must keep passing.
    assert not RUNNER.delivery_subject_matches("version 0.1.25 (commit 423f233)", "#423")
    assert not RUNNER.delivery_subject_matches("the sha x423y here", "#423")
    assert not RUNNER.delivery_subject_matches("release 41423f5 shipped", "#423")
    assert not RUNNER.delivery_subject_matches("see B4239.log for detail", "#423")
    assert RUNNER.delivery_subject_matches("FILED as #423", "#423")

def test_the_dispatch_delivery_leg_COUNTS_pre_boundary_rows_and_never_judges_them() -> None:
    """#49: the historical population is legitimately large -- 430 live dispatch rows
    carry no verdict, and the ruling forbids backfilling them. A leg that judged them all
    is the permanent red #334 exists to stop, so a pre-boundary row is COUNTED and
    PRINTED, and the examined count is printed beside the verdict so a clean read over
    zero rows is never mistaken for a verified one.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    old = _stall_row(71, "dispatch", "#70", 5, now=now, actor="triage")

    leg = RUNNER.dispatch_delivery_leg(
        [old], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["dispatch_rows_pre_boundary"] == 1, leg["coverage"]
    assert leg["coverage"]["dispatch_rows_examined"] == 0, leg["coverage"]

def test_the_dispatch_delivery_leg_FAILS_OPEN_on_a_refused_bound_and_a_blind_store() -> None:
    """#49 acceptance (1): the leg fails open -- an absent bound and an unreachable store
    each render NOT RUN with the reason, never a clean zero.

    A clean verdict over a store the leg could not read is the "confident zero that reads
    as good news" the ruling names as worse than no leg at all.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    row = _stall_row(81, "dispatch", "#80", 0, now=now, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])

    refused = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=(None, "", "probe refusal"),
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert refused["status"] == "NOT RUN", refused
    assert refused["problems"] == [], refused["problems"]
    assert "probe refusal" in (refused["reason"] or ""), refused

    blind = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=(now - dt.timedelta(days=1), "b", ""),
        deliveries_fn=lambda: ([], [], ["probe-home: could not be read"]),
    )
    assert blind["status"] == "NOT RUN", blind
    assert blind["problems"] == [], blind["problems"]
    assert "could not be read" in (blind["reason"] or ""), blind

def test_the_dispatch_delivery_leg_PRINTS_its_examined_population() -> None:
    """#49 acceptance (3): `examined 1, 1 problem` must never render the same as
    `examined 0`. Asserted on the RENDER, because a count computed and dropped from the
    report is the same failure as one never computed.
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    row = _stall_row(91, "dispatch", "#90", 0, now=now - dt.timedelta(minutes=5),
                     actor="triage", refs=[{"session": _PROBE_TARGET}])
    rc, out, _ = _run(
        [], [row], delivery_scope=bound,
        deliveries=[],
    )
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "examined: 1" in out, out
    assert "read at " in out, out
    assert rc == 1, f"a phantom dispatch is a problem, got rc={rc}\n{out}"

def test_the_dispatch_delivery_leg_DEFERS_the_store_read_until_there_is_a_row_to_judge() -> None:
    """#49: the store read is DEFERRED, and the not-read state is DISTINGUISHABLE from an
    empty one.

    TWO FACTS, and the second is the one that matters.

    (a) A leg with no post-boundary dispatch row must not touch the store AT ALL. The read
    is O(the whole box's message history) -- expensive enough that a leg scanning it before
    knowing whether it had anything to corroborate pays that cost to judge zero rows -- so
    every probe driving `main()` paid it again. That is
    what turned this file's own gate from well inside its budget into a TIMEOUT the moment
    the leg's boundary was declared. `deliveries_fn` here RAISES, so a leg that read the
    store anyway fails by exception rather than by a number nobody thought to assert.

    (b) `deliveries_read` is then None and NOT 0, because `0` would stand for both "the
    store held no delivery" and "the store was never opened" -- the confident zero this leg
    exists to refuse.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    old = _stall_row(72, "dispatch", "#70", 5, now=now, actor="triage")

    def _explode():
        raise AssertionError("the store must not be read when there is nothing to judge")

    deferred = RUNNER.dispatch_delivery_leg(
        [old], read_at=read_at, bound=bound, deliveries_fn=_explode,
    )
    assert deferred["status"] == "ASSERTED", deferred
    assert deferred["problems"] == [], deferred["problems"]
    assert deferred["coverage"]["store_read"] is False, deferred["coverage"]
    assert deferred["coverage"]["deliveries_read"] is None, deferred["coverage"]

    # ... and the SAME leg WITH a row to judge DOES read it, so the deferral is a deferral
    # and not a leg that has stopped reading at all. Without this arm, a leg that never read
    # the store would satisfy the first half just as well.
    fresh = _stall_row(73, "dispatch", "#71", 0, now=now - dt.timedelta(minutes=5),
                       actor="triage", refs=[{"session": _PROBE_TARGET}])
    read = RUNNER.dispatch_delivery_leg(
        [fresh], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert read["coverage"]["store_read"] is True, read["coverage"]
    assert read["coverage"]["deliveries_read"] == 0, read["coverage"]

def test_the_leg_RENDERS_a_store_it_never_opened_distinctly_from_one_that_held_nothing() -> None:
    """#49 acceptance (3): `deliveries read: 0` must not be the render of BOTH "the store
    held no delivery" and "the store was never opened".

    Asserted on the RENDER for the same reason the examined-population probe is: a state the
    leg records but never prints is a state no reader can act on.
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    old = _stall_row(74, "dispatch", "#72", 5, now=now, actor="triage")
    rc, out, _ = _run([], [old], delivery_scope=bound, deliveries=[])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "deliveries: NOT READ" in out, out
    assert "deliveries read:" not in out, out
    assert "examined: 0" in out, out

def test_the_dispatch_delivery_leg_corroborates_ONLY_the_rows_OWN_target() -> None:
    """#425 clause 1: a delivery carrying the subject but addressed to a DIFFERENT lane is
    NOT corroboration of this dispatch row.

    The same subject is broadcast to several lanes, so a subject-only match clears a row
    whose actual target was never told -- the false-clean class. Both arms are asserted,
    because a leg that reported every row would pass the first alone and a leg that reported
    none would pass the second.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(52, "dispatch", "#78", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    delivered_at = dispatched + dt.timedelta(seconds=60)
    notify = "[session-notify from=abc]\nDISPATCH #78 to the lane"

    # arm 1 — the notify names the SUBJECT but is addressed to a DIFFERENT target: the row
    # is a phantom, and the problem must NAME the target it actually routed to.
    other = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(delivered_at, notify, session="a-different-lane")],
            ["probe-home"], [],
        ),
    )
    named = "\n".join(other["problems"])
    assert other["status"] == "ASSERTED", other
    assert "n=52" in named and _PROBE_TARGET in named, (
        f"a subject match to the WRONG target must stay RED and name the real target\n{named}"
    )

    # arm 2 — the SAME delivery addressed to the ROW'S OWN target clears it. Without this
    # arm the first would pass a leg that matched nothing at all.
    same = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(delivered_at, notify, session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert same["problems"] == [], same["problems"]

def test_the_dispatch_delivery_leg_counts_a_ref_less_row_as_NOT_JUDGED() -> None:
    """#425 clause 1: a post-boundary dispatch row carrying no typed `session` ref is NOT
    JUDGED -- counted and printed, never CLEAN and never RED, nothing backfilled.

    The 19 rows that carry a target are the shape the write path now enforces; every row
    written before that refusal is immutable history, so judging it would be the permanent
    red #334 exists to stop. The bucket is asserted on BOTH the leg's coverage AND the
    render, because a count computed and dropped from the report is the same failure as one
    never computed -- and the zero it would otherwise show is the confident one.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    ref_less = _stall_row(101, "dispatch", "#100", 0, now=now - dt.timedelta(minutes=5),
                          actor="triage")

    leg = RUNNER.dispatch_delivery_leg(
        [ref_less], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"] == [], (
        f"a ref-less row is NOT JUDGED, never RED\n{leg['problems']}"
    )
    assert leg["coverage"]["dispatch_rows_not_judged"] == 1, leg["coverage"]
    assert leg["coverage"]["dispatch_rows_examined"] == 0, leg["coverage"]
    # the store is not read, and the reason names the BUCKET rather than an empty window.
    assert leg["coverage"]["store_read"] is False, leg["coverage"]
    assert "NOT JUDGED" in (leg["coverage"]["store_not_read_reason"] or ""), leg["coverage"]

    rc, out, _ = _run([], [ref_less], delivery_scope=bound, deliveries=[])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "1 carry no target, NOT JUDGED" in out, out
    assert "examined: 0" in out, out
    assert rc == 0, f"a ref-less row is not a problem, got rc={rc}\n{out}"

def test_the_dispatch_delivery_leg_reads_a_LATE_STAMP_by_the_instant_the_row_DECLARES() -> None:
    """#432, the specimen. A row's `ts` is a WRITE instant, so a batched ledger write stamps it
    AFTER the dispatch it records and a window built from it opens after a genuine delivery.

    BOTH ARMS, because either alone proves nothing: the row WITH its declared instant clears
    the delivery, and the SAME row with the declaration stripped reports a window mismatch --
    so the declaration is measured to be the thing that clears it, not a leg that stopped
    judging. The declared instant is 1 h before the write stamp and the notify lands on it.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    declared = now - dt.timedelta(hours=2)
    # `ts` = now - 1 h; the delivery sits on the DECLARED instant, 1 h before the write stamp
    # and 57 min before the window a `ts`-only anchor would open.
    declared_row = _late_stamp_row(111, now=now, declared=declared)
    deliveries = lambda: (
        [_delivery(declared, "[session-notify from=abc]\nDISPATCH #77 to the lane",
                   session=_PROBE_TARGET)],
        ["probe-home"], [],
    )

    cleared = RUNNER.dispatch_delivery_leg(
        [declared_row], read_at=read_at, bound=bound, deliveries_fn=deliveries,
    )
    assert cleared["problems"] == [], (
        f"the row's own declared instant must anchor the window (#432)\n{cleared['problems']}"
    )
    assert cleared["coverage"]["dispatch_rows_declared_anchor"] == 1, cleared["coverage"]
    assert cleared["coverage"]["dispatch_rows_examined"] == 1, cleared["coverage"]

    # ... AND THE DECLARATION IS WHAT CLEARS IT. The same fixture with the declaration removed
    # keeps the same `ts`, the same delivery and the same target, so a leg that cleared the
    # first arm by matching nothing at all would fail here.
    stripped = _late_stamp_row(112, now=now, declared=None)
    mismatch = RUNNER.dispatch_delivery_leg(
        [stripped], read_at=read_at, bound=bound, deliveries_fn=deliveries,
    )
    assert mismatch["coverage"]["dispatch_rows_declared_anchor"] == 0, mismatch["coverage"]
    assert mismatch["problems"] == [], (
        "without the declaration the delivery falls outside the window — which is an "
        f"EXCUSAL, not a problem (#538)\n{mismatch['problems']}"
    )
    assert "WINDOW MISMATCH" in mismatch["excused"][0], mismatch["excused"]

def test_the_declared_instant_is_BOUNDED_so_a_QUOTED_token_declares_NOTHING() -> None:
    """#476: the declared-instant form is a PHRASE MATCH, so a row that QUOTES the token as
    evidence about a DIFFERENT artifact declares it as its own dispatch instant.

    The live specimen is row `n=3215` (#474's dispatch): its detail quotes the stale
    `registry/state.json` snapshot's `resolved_at 2026-10-05T13:01:19Z` as a MEASUREMENT, 8
    days before the row's own write stamp, and the #432 anchor rule built the judged window
    from that quote -- printing "records no delivery" for a dispatch that had landed one
    second BEFORE the row's stamp. `n=3226` repeated it within the hour, on the ruling lane's
    own next dispatch.

    BOTH ARMS, because either alone proves nothing: a mid-line declaration INSIDE the bound is
    still used as the anchor, and the SAME shape with a quoted instant BEYOND the bound falls
    back to `ts` -- where the delivery IS found. A bound that rejected every declaration would
    pass the second arm while silently disabling the #432 repair the first arm pins.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    ts = now - dt.timedelta(hours=1)

    # ARM 1 -- a DESIGNED declaration: 7200 s of lag, well inside the bound. It anchors the
    # window on the declared instant and clears a delivery that sits there.
    designed_at = ts - dt.timedelta(seconds=7200)
    used = RUNNER.dispatch_delivery_leg(
        [_row_with_lag(161, ts=ts, lag_secs=7200)], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(designed_at, "[session-notify from=abc]\nDISPATCH #90 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert used["coverage"]["dispatch_rows_declared_anchor"] == 1, used["coverage"]
    assert used["problems"] == [], (
        f"a declaration inside the bound must still anchor the window (#432)\n{used['problems']}"
    )

    # ARM 2 -- the `n=3215` shape: the same row carrying a quoted instant 8 days back. It must
    # NOT become the anchor, and a delivery inside the `ts` window must be found.
    fell_back = RUNNER.dispatch_delivery_leg(
        [_row_with_lag(162, ts=ts, lag_secs=8 * 86400)], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(ts - dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nDISPATCH #90 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert fell_back["coverage"]["dispatch_rows_declared_anchor"] == 0, (
        f"a quote beyond the bound must fall back to the write stamp\n{fell_back['coverage']}"
    )
    assert fell_back["problems"] == [], (
        f"anchored on `ts`, the delivery lands inside the window\n{fell_back['problems']}"
    )

    # ... AND THE BOUND IS EXACT, not merely present: a lag 1 s inside it anchors on the
    # declaration, 1 s outside it falls back to `ts`. The arms above would pass under ANY
    # bound; this pair pins WHICH one.
    limit = RUNNER.DECLARED_INSTANT_MAX_LAG_SECS
    for n, lag, expected in ((163, limit - 1, 1), (164, limit + 1, 0)):
        leg = RUNNER.dispatch_delivery_leg(
            [_row_with_lag(n, ts=ts, lag_secs=lag)], read_at=read_at, bound=bound,
            deliveries_fn=lambda: ([], ["probe-home"], []),
        )
        assert leg["coverage"]["dispatch_rows_declared_anchor"] == expected, (
            f"a {lag} s lag must anchor={expected} against a {limit} s bound\n"
            f"{leg['coverage']}"
        )

def test_the_dispatch_delivery_leg_reports_a_WINDOW_MISMATCH_as_an_EXCUSAL() -> None:
    """#432's class, re-homed by #538. The leg carried ONE verdict for TWO conditions, so a
    delivery that exists but falls outside the window the leg chose read as "records no
    delivery" -- a FALSE ABSENCE that sends a reader off to re-dispatch an item the target
    already holds.

    A match is taken WITHOUT the window first, so the two conditions are distinguishable. The
    mismatch must NAME the delivery's own instant and the window that judged it, and must NOT
    carry the absence's words -- a reader who greps for the absence text must not find it on a
    row whose delivery is sitting in the store.

    AND IT IS AN EXCUSAL, NOT A PROBLEM (#538, ruled at ledger n=4029): the leg's own line
    said "a DELIVERY EXISTS ... do not re-dispatch" while counting it as a debt, and 57 of its
    96 problems on the 2026-10-21 read were this shape -- units delivered and finished. The
    verdict keeps every instant and every window; what it loses is the problem count.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(121, "dispatch", "#79", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    # 2 h after the write stamp: past the 5400 s forward bound, so the window cannot hold it.
    landed_at = dispatched + dt.timedelta(hours=2)

    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(landed_at, "[session-notify from=abc]\nDISPATCH #79 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert leg["status"] == "ASSERTED", leg
    assert leg["problems"] == [], (
        f"a delivery outside the window is an EXCUSAL, not a finding (#538)\n{leg['problems']}"
    )
    assert leg["coverage"]["delivered_outside_window"] == 1, leg["coverage"]
    problem = leg["excused"][0]
    assert "WINDOW MISMATCH" in problem, problem
    assert "records no delivery" not in problem, (
        f"a delivery that EXISTS must never read as an absence\n{problem}"
    )
    assert landed_at.strftime("%Y-%m-%dT%H:%M:%SZ") in problem, (
        f"the mismatch must name the delivery's own instant\n{problem}"
    )
    assert "do not re-dispatch" in problem, problem

    # ... AND A TRUE ABSENCE STILL READS AS ONE, or the fix would have bought the mismatch
    # verdict by never reporting the absence it exists to catch.
    absent = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert absent["problems"], absent
    assert "records no delivery" in absent["problems"][0], absent["problems"]
    assert "WINDOW MISMATCH" not in absent["problems"][0], absent["problems"]

    # ... AND A DELIVERY ADDRESSED TO ANOTHER LANE IS STILL AN ABSENCE, not a mismatch: the
    # match is on the ROW'S OWN target (#425 clause 1), so a broadcast that never reached this
    # row's target must not be read as "it exists, just elsewhere".
    elsewhere = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(landed_at, "[session-notify from=abc]\nDISPATCH #79 to the lane",
                       session="a-different-lane")],
            ["probe-home"], [],
        ),
    )
    assert "records no delivery" in elsewhere["problems"][0], elsewhere["problems"]
    assert "WINDOW MISMATCH" not in elsewhere["problems"][0], elsewhere["problems"]

def test_declared_dispatch_instant_reads_only_a_NAMED_form() -> None:
    """#432: the row's `detail` is FREE PROSE, so a bare ISO instant is not a declaration.

    Measured on this ledger: 146 of 458 dispatch rows carry SOME ISO instant in their detail --
    a window, a neighbour's row stamp, a read instant. A reader that took any ISO string would
    anchor windows on whatever instant a row happened to quote, which is the `#425` class of
    predicate-wider-than-the-artifact. So each form pairs a TOKEN with its value, a value that
    does not parse declares nothing (and raises nothing: a malformed declaration is no
    declaration, never a licence to judge unbounded), and the EARLIER of the two wins.
    """
    now = dt.datetime.now(dt.timezone.utc)
    declared = (now - dt.timedelta(hours=2)).replace(microsecond=0)
    iso = declared.strftime("%Y-%m-%dT%H:%M:%SZ")

    # A named form declares ...
    instant, form = RUNNER.declared_dispatch_instant(
        {"detail": f"routed LIVE this turn (resolved_at {iso})."}
    )
    assert instant == declared and form == "resolved_at", (instant, form)

    # ... a bare ISO instant does NOT ...
    assert RUNNER.declared_dispatch_instant(
        {"detail": f"the window was [{iso}, later]"}
    ) == (None, "")
    # ... nor does a mention of the token with no value, nor a value that cannot be parsed ...
    assert RUNNER.declared_dispatch_instant(
        {"detail": "resolved_at was not recorded"}
    ) == (None, "")
    assert RUNNER.declared_dispatch_instant(
        {"detail": "resolved_at 2026-13-45T99:99:99Z"}
    ) == (None, "")
    # ... nor an empty or absent detail.
    assert RUNNER.declared_dispatch_instant({"detail": ""}) == (None, "")
    assert RUNNER.declared_dispatch_instant({}) == (None, "")

    # EARLIER WINS: a declaration AFTER the write stamp cannot pull the window forward, so the
    # leg keeps the write stamp as the anchor and the later instant is simply not used.
    now2 = dt.datetime.now(dt.timezone.utc)
    read_at = now2.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now2 - dt.timedelta(days=1), "probe-bound", "")
    forward = _stall_row(
        131, "dispatch", "#81", 1 / 24.0, now=now2, actor="triage",
        detail=f"resolved_at {(now2 + dt.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        refs=[{"session": _PROBE_TARGET}],
    )
    leg = RUNNER.dispatch_delivery_leg(
        [forward], read_at=read_at, bound=bound,
        deliveries_fn=lambda: ([], ["probe-home"], []),
    )
    assert leg["coverage"]["dispatch_rows_declared_anchor"] == 0, (
        f"a declaration AFTER the write stamp must not become the anchor\n{leg['coverage']}"
    )

def test_the_render_PRINTS_the_anchor_each_window_was_built_from() -> None:
    """#432: a window built from a row's WRITE stamp and one built from an instant the row
    DECLARES are different judgements. A reader who cannot tell which was used cannot tell a
    clean sweep from a narrow window, so the anchor counts are printed beside the verdict --
    the same discipline as the examined population (acceptance criterion 3, #116).
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    declared = now - dt.timedelta(hours=2)
    row = _late_stamp_row(141, now=now, declared=declared)
    rc, out, _ = _run([], [row], delivery_scope=bound, deliveries=[])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "window anchors: 1 of 1 examined row(s) anchored on an instant the row itself DECLARES" in out, out
    # ... and the window line states which anchor was used, not just the count.
    assert "anchored on the row's declared `resolved_at`" in out, out

def test_the_match_HORIZON_keeps_an_OLD_mention_from_reading_as_a_DELIVERY() -> None:
    """#432: the horizon separates a DELIVERY from a subject MENTION, and both arms are needed.

    Measured on this ledger at the 2026-10-07T15:36Z read: the `#432` target held **47**
    messages carrying the subject, the oldest `2026-09-19T08:29:00Z` -- 18 days before the
    read -- and only **3** within 24 h. Without a horizon, the first of those 47 reads as "a
    delivery EXISTS, just outside the window", which is the false-CLEAN twin of the false
    absence this item is about: a leg that answered "it was delivered, only not then" for
    every stale mention would clear a row whose notify was never sent. So a match outside the
    horizon is NOT a delivery, and a true absence is still reported as one.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(151, "dispatch", "#83", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])

    # ARM 1 -- an 18-day-old mention to the SAME target carrying the SAME subject is not a
    # delivery: it is a stale broadcast, and the row still records no delivery of THIS brief.
    stale_at = dispatched - dt.timedelta(days=18)
    stale = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(stale_at, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert stale["coverage"]["subject_matches_anywhere"] == 1, stale["coverage"]
    assert stale["coverage"]["subject_matches_within_horizon"] == 0, stale["coverage"]
    assert stale["problems"], "a mention outside the horizon is not a delivery"
    assert "records no delivery" in stale["problems"][0], stale["problems"]
    assert "WINDOW MISMATCH" not in stale["problems"][0], (
        f"an 18-day-old mention must never read as a delivery\n{stale['problems']}"
    )

    # ARM 2 -- the SAME row with the mention 2 h after the write stamp is INSIDE the horizon
    # and outside the 5400 s window, so it is a WINDOW MISMATCH. Same subject, same target,
    # same fixture: only the age moved, so the horizon is measured to be the discriminator.
    near_at = dispatched + dt.timedelta(hours=2)
    near = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(near_at, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert near["coverage"]["subject_matches_anywhere"] == 1, near["coverage"]
    assert near["coverage"]["subject_matches_within_horizon"] == 1, near["coverage"]
    # A WINDOW MISMATCH IS AN EXCUSAL, NOT A PROBLEM (#538, ruled at ledger n=4029): the
    # delivery EXISTS, and the leg's own text said "do not re-dispatch on this line" while
    # counting it as a debt. The instance still names its instant and its window.
    assert near["problems"] == [], near["problems"]
    assert near["coverage"]["delivered_outside_window"] == 1, near["coverage"]
    assert "WINDOW MISMATCH" in near["excused"][0], near["excused"]
    assert "does not contain it" in near["excused"][0], near["excused"]

    # ... AND THE HORIZON IS BOUNDED, not merely present: a mention 1 s inside it is a
    # delivery and one 1 s outside it is not, so a leg that ignored the bound entirely would
    # fail the pair above while a leg that used ANY bound would still have to pass this one.
    horizon = RUNNER.DELIVERY_MATCH_HORIZON_SECS
    just_in = dispatched + dt.timedelta(seconds=horizon - 1)
    just_out = dispatched + dt.timedelta(seconds=horizon + 1)
    inside = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(just_in, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    outside = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(just_out, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert inside["coverage"]["subject_matches_within_horizon"] == 1, inside["coverage"]
    # ... and the WINDOW MISMATCH it produces is an EXCUSAL, not a problem (#538).
    assert inside["problems"] == [], inside["problems"]
    assert "WINDOW MISMATCH" in inside["excused"][0], inside["excused"]
    assert outside["coverage"]["subject_matches_within_horizon"] == 0, outside["coverage"]
    assert "records no delivery" in outside["problems"][0], outside["problems"]

def test_the_render_PRINTS_the_match_counts_the_horizon_judged() -> None:
    """#432: the horizon decides silently whether a mention is a delivery, so its effect is
    PRINTED -- `N within the horizon of M anywhere` -- and the reader can see how many
    mentions were set aside. A count that appears only when the horizon clears everything is a
    number a reader cannot distinguish from a store that held nothing (#116, criterion 3).
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(161, "dispatch", "#85", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    stale = _delivery(dispatched - dt.timedelta(days=18),
                      "[session-notify from=abc]\nDISPATCH #85 to the lane",
                      session=_PROBE_TARGET)
    near = _delivery(dispatched + dt.timedelta(hours=2),
                     "[session-notify from=abc]\nDISPATCH #85 to the lane",
                     session=_PROBE_TARGET)
    rc, out, _ = _run([], [row], delivery_scope=bound, deliveries=[stale, near])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert (
        f"subject matches: 1 within the {RUNNER.DELIVERY_MATCH_HORIZON_SECS} s horizon of 2 "
        f"anywhere in the store(s)"
    ) in out, out

def test_a_BODY_only_mention_is_a_MENTION_and_NEVER_corroboration() -> None:
    """#433: a message that DISCUSSES the subject does not clear a dispatch row.

    The false-CLEAN twin of #432's false absence. A lane's store is full of messages carrying
    the unit's token -- compaction summaries quoting the task list, rulings quoting the row
    under discussion -- and a whole-text match lets any one of them clear a row whose brief was
    never routed. The token belongs in the delivery's HEADER, because that is where a delivery
    NAMES what it routes.

    THREE assertions, because a fix that overshot would pass two of them: the row is NAMED, it
    reads as a MENTION, and it does NOT read as an absence -- the text IS there, and calling it
    "records no delivery" would be a lie in the opposite direction.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(181, "dispatch", "#91", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched + dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nTriage cycle report\n\n"
                       "queued for this lane: #91, #92",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    named = "\n".join(leg["problems"])
    assert leg["coverage"]["dispatch_rows_corroborated"] == 0, leg["coverage"]
    assert leg["coverage"]["subject_matches_anywhere"] == 1, leg["coverage"]
    assert leg["coverage"]["subject_matches_within_horizon"] == 0, leg["coverage"]
    assert leg["coverage"]["subject_mentions_body_only"] == 1, leg["coverage"]
    assert "n=181" in named and "#91" in named, f"the row must be NAMED\n{named}"
    assert "MENTION" in named, f"a body-only match reads as a MENTION\n{named}"
    assert "corroborated by NO delivery" in named, named
    assert "records no delivery" not in named, (
        f"a body mention is not an absence -- the text IS there\n{named}"
    )

def test_a_HEADER_match_still_clears_the_row_when_the_body_mentions_it_too() -> None:
    """#433, the specimen's own shape: `#428`'s dispatch row carried its subject at offset 78
    (the header) and again at offset 868 (a queue list in the body).

    A fix that scoped the match to "the first occurrence" or to "not the body" would redden
    this row -- the one whose delivery genuinely woke the lane. The discriminator is WHERE the
    token sits, never WHICH occurrence is found first.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(182, "dispatch", "#93", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched + dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nTRIAGE DISPATCH — #93\n\n"
                       "queued for this lane: #93, #94",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["dispatch_rows_corroborated"] == 1, leg["coverage"]
    assert leg["coverage"]["subject_mentions_body_only"] == 0, leg["coverage"]

def test_a_body_mention_addressed_to_a_DIFFERENT_target_is_still_an_ABSENCE() -> None:
    """#425 clause 1, re-asserted under the #433 split: a mention on ANOTHER lane is neither
    corroboration nor a mention OF THIS DISPATCH.

    The subject is broadcast to several lanes, so a body match on a different target must stay
    an absence -- otherwise the header fix would have widened the predicate it was meant to
    narrow.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(183, "dispatch", "#95", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched + dt.timedelta(seconds=60),
                       "[session-notify from=abc]\nTriage cycle report\n\nqueued: #95",
                       session="another-lane")],
            ["probe-home"], [],
        ),
    )
    named = "\n".join(leg["problems"])
    assert "records no delivery" in named, named
    assert "MENTION" not in named, f"another lane's mention is not this dispatch's\n{named}"
    assert leg["coverage"]["subject_mentions_body_only"] == 0, leg["coverage"]

def test_a_body_mention_beyond_the_horizon_is_counted_but_not_a_MENTION() -> None:
    """#433 horizon arm: the MENTION verdict is bounded exactly as a delivery match is.

    An 18-day-old compaction summary quoting the unit is not evidence that a briefing reached
    the target, so it must not become a second route to a confident near-verdict. It is still
    COUNTED (`..._anywhere`), because a count that vanished would be indistinguishable from a
    store that held nothing (#116).
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(184, "dispatch", "#96", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    leg = RUNNER.dispatch_delivery_leg(
        [row], read_at=read_at, bound=bound,
        deliveries_fn=lambda: (
            [_delivery(dispatched - dt.timedelta(days=18),
                       "[session-notify from=abc]\nTriage cycle report\n\nqueued: #96",
                       session=_PROBE_TARGET)],
            ["probe-home"], [],
        ),
    )
    named = "\n".join(leg["problems"])
    assert leg["coverage"]["subject_mentions_body_only"] == 1, leg["coverage"]
    assert leg["coverage"]["subject_mentions_body_only_within_horizon"] == 0, leg["coverage"]
    assert "records no delivery" in named, named
    assert "MENTION" not in named, f"an 18-day-old mention is not a near-mention\n{named}"

def test_delivery_header_skips_the_envelope_and_reads_the_line_the_SENDER_wrote() -> None:
    """#433: the header is the sender's first NON-BLANK line, with the harness's envelope
    skipped.

    The envelope (`[session-notify from=<uuid>]`, `📨 notify from <short-id>:`) is added by the
    transport, not written by the lane that routed the brief, so counting it as the header line
    would scope the match to a line no sender controls. Both declared forms are exercised, and
    the blank line between envelope and body is what the skip exists for.
    """
    assert RUNNER.delivery_header(
        "[session-notify from=abc]\n\nTRIAGE DISPATCH — #94\nqueued: #94"
    ) == "TRIAGE DISPATCH — #94"
    assert RUNNER.delivery_header(
        "📨 notify from abc123:\nDISPATCH #94 to the Worker\nbody: #94"
    ) == "DISPATCH #94 to the Worker"

def test_the_render_PRINTS_the_header_and_body_split() -> None:
    """#433: the split is PRINTED, because it IS the verdict.

    "subject matches: 1 within the horizon of 1 anywhere" was true of the #433 specimen and
    said nothing about whether the match corroborated -- the reader needs "of the rows
    examined, how many a HEADER match cleared" beside "how many body-only mentions were set
    aside", or a green line cannot be told from a row cleared by a mention.
    """
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(185, "dispatch", "#97", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    mention = _delivery(dispatched + dt.timedelta(seconds=60),
                        "[session-notify from=abc]\nTriage cycle report\n\nqueued: #97",
                        session=_PROBE_TARGET)
    rc, out, _ = _run([], [row], delivery_scope=bound, deliveries=[mention])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "subject matches in a delivery HEADER:" in out, out
    assert "body-only mention(s)" in out, out

def test_box_deliveries_reads_BOTH_harness_header_forms() -> None:
    """#426: the harness writes TWO landed-notify header forms, and the leg matched only one.

    Measured live before the fix: four dispatch rows (n=2749-2752) read RED because their
    notifies landed in the emoji form and the read saw none. Both forms are asserted here, so
    the probe fails if the predicate narrows back to a single header — and a QUOTED header is
    asserted NOT to count, so the fix cannot be a bare `notify from` substring (rule 7).
    """
    root = Path(tempfile.mkdtemp()) / "profiles"
    # The live box's SHAPE: a default home beside a profile root, both read.
    _messages_db(root.parent / "opencrabs.db")
    _messages_db(
        root / "ops" / "opencrabs.db",
        ("probe-session", "📨 notify from abc12345:\nDISPATCH #77 to the Worker"),
        ("probe-session", "[session-notify from=abc]\nDISPATCH #78 to the Worker"),
        ("probe-session", "a report QUOTING `notify from abc` must not read as landed"),
    )
    deliveries, _homes_read, unreached = RUNNER.box_deliveries(root)
    assert unreached == [], unreached
    texts = [d["text"] for d in deliveries if d["state"] == "landed"]
    assert any(t.startswith("📨 notify from ") for t in texts), (
        f"the EMOJI form must read as landed\n{texts}"
    )
    assert any(t.startswith("[session-notify from=") for t in texts), (
        f"the BRACKETED form must still read as landed\n{texts}"
    )
    assert not any("QUOTING" in t for t in texts), (
        f"a QUOTED header is not a delivery (reader-echo class, rule 7)\n{texts}"
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
