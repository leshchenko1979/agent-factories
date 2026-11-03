"""Gate: census, standing items and the driverless lane — #133/#532/#607

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
    _GOAL_CREATED,
    _NOW,
    _activity_store,
    _goal_store,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _census_with(*lanes, status="ASSERTED"):
    """A census leg carrying ONLY the grouping the driverless leg reads.

    Deliberately minimal: this leg's population is the census's `owed_by_lane`, so a fixture
    that rebuilt the census's own routing would be asserting a second implementation of it.
    """
    return {
        "name": "stall-census",
        "status": status,
        "problems": [],
        "excused": [],
        "coverage": {
            "owed_by_lane": list(lanes),
            "lanes_with_backlog": len(lanes),
            "read_at": "2026-10-18T00:00:00Z",
        },
    }

def _lane_slot(session_ref, units, *, lane=None, age=2.0):
    return {"session_ref": session_ref, "lane": lane, "units": list(units),
            "oldest_age_days": age}

def _goal_row(session_id, state, *, turns=1, updated=_GOAL_CREATED):
    """One `goal_state` row. `updated` defaults to `created`, i.e. an arm never evaluated.

    The default is deliberate: the card's ARMED-INERT row is defined by `updated_at =
    created_at`, so the motionless shape is the one a fixture should get by NOT asking for
    motion. A fixture that had to remember to suppress the timestamp would be encoding the
    predicate a second time.
    """
    return {"session_id": session_id, "state": state, "turns_used": turns,
            "max_turns": 20, "created_at": _GOAL_CREATED,
            "updated_at": updated}

def _driverless_probe(activity, *, goal_state="paused", turn_open=False):
    """One lane, one paused row, one injected activity source -- the (a)/(b) pair's shared half."""
    census = _census_with(_lane_slot("sess-x", ["#9"], lane="Probe Lane"))
    return RUNNER.driverless_leg(
        census,
        goals=_goal_store(_goal_row("sess-x", goal_state, turns=20,
                                    updated="2026-10-17T00:00:00+00:00")),
        read_at="2026-10-21T12:00:00Z",
        lane_names_fn=lambda: {},
        lane_turn_open_fn=lambda: {"sess-x": turn_open},
        lane_activity_fn=lambda: activity,
        now=_NOW,
    )

# --- this leg's tests -------------------------------------------------------
def test_the_readings_are_DISTINCT_and_counted_separately() -> None:
    """#133's acceptance: DRIVEN, ARMED-INERT and DRIVERLESS are different findings.

    Non-vacuity rides THIS fixture rather than a loud-fail-on-zero: the live population of
    driverless lanes is legitimately empty on a healthy day, so an empty reading is a normal
    reading. What must never be empty is the leg's ability to tell the three apart, which is
    exactly what a fixture carrying one of each proves -- a leg that collapsed ARMED-INERT into
    DRIVEN would report two DRIVEN and one DRIVERLESS here and pass a count-only assertion.

    THE FOURTH LANE IS THE CARD'S OWN COLLISION (#460 criterion 2). Read literally, the card's
    DRIVEN row (motion) and DRIVERLESS row (no active row, no turn in flight) both matched a
    `paused` row that advanced before it stopped, so a reader could report either. It reads
    DRIVERLESS, because a stopped loop is not a driver and calling it one refuses the only act
    that restarts it -- and that is asserted here so the two halves cannot drift apart again.
    """
    census = _census_with(
        _lane_slot("sess-driven", ["#1", "#2"], lane="Driven Lane"),
        _lane_slot("sess-inert", ["#3"], lane="Inert Lane"),
        _lane_slot("sess-none", ["#4", "#5", "#6"], lane="Driverless Lane"),
        _lane_slot("sess-stopped", ["#7"], lane="Stopped Lane"),
    )
    goals = _goal_store(
        # ADVANCING: active, evaluated, touched after creation.
        _goal_row("sess-driven", "active", turns=4, updated="2026-10-17T00:00:00+00:00"),
        # ARMED AND NEVER EVALUATED: active, zero turns, updated == created.
        _goal_row("sess-inert", "active", turns=0),
        # STOPPED AFTER RUNNING: motion in its history, but nothing will evaluate it again.
        _goal_row("sess-stopped", "paused", turns=20, updated="2026-10-17T00:00:00+00:00"),
    )
    leg = RUNNER.driverless_leg(census, goals=goals, read_at="2026-10-18T00:00:00Z",
                                lane_names_fn=lambda: {},
                                lane_activity_fn=lambda: _activity_store(),
                                now=dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc))

    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert (cov["driven"], cov["armed_inert"], cov["driverless"]) == (1, 1, 2), cov
    assert cov["lanes_judged"] == 4, cov
    assert cov["backlog_units"] == 7, cov
    assert cov["lanes_with_a_turn_in_flight"] == 0, cov

    readings = {entry["lane"]: entry["reading"] for entry in cov["lanes"]}
    assert readings == {
        "Driven Lane": "DRIVEN",
        "Inert Lane": "ARMED-INERT",
        "Driverless Lane": "DRIVERLESS",
        "Stopped Lane": "DRIVERLESS",
    }, readings

    # THE BITE: only the three non-DRIVEN lanes are problems, and each names its OWN cause --
    # a never-evaluated arm, a stopped loop and an absent one are three remedies, so one
    # sentence for all of them would be the collapse this probe exists to forbid.
    assert len(leg["problems"]) == 3, leg["problems"]
    by_lane = {p.split("LANE ", 1)[1].split(":", 1)[0]: p for p in leg["problems"]}
    assert set(by_lane) == {"Inert Lane", "Driverless Lane", "Stopped Lane"}, by_lane
    assert "`active`" in by_lane["Inert Lane"], by_lane["Inert Lane"]
    assert "never" in by_lane["Inert Lane"] and "evaluated" in by_lane["Inert Lane"], by_lane["Inert Lane"]
    assert "NO goal row" in by_lane["Driverless Lane"], by_lane["Driverless Lane"]
    assert "`paused`" in by_lane["Stopped Lane"], by_lane["Stopped Lane"]
    # ... and the stopped lane must NOT be described as never armed: it carries a row, and
    # printing an absence beside a row that exists is the misreport this split prevents.
    assert "NO goal row" not in by_lane["Stopped Lane"], by_lane["Stopped Lane"]
    assert "`active`" not in by_lane["Stopped Lane"], by_lane["Stopped Lane"]
    # ... and ALL of them say the leg will not act, so no reader thinks a re-arm happened.
    for problem in leg["problems"]:
        assert "MUST NOT re-arm another lane's goal" in problem, problem

def test_a_TURN_IN_FLIGHT_drives_a_lane_whose_arm_is_INERT() -> None:
    """The card's DRIVEN row admits a turn in flight EVEN WHEN THE ARM IS INERT.

    This is the reading the goal store alone cannot produce: an armed-but-never-evaluated lane
    is ARMED-INERT by its rows, and yet it is being driven right now by the turn that is
    running. A reader that consulted only `goal_state` would call it inert and refuse a re-arm
    that the card permits only because nothing is in the room -- so the binding fact decides.
    """
    census = _census_with(_lane_slot("sess-busy", ["#1"], lane="Busy Lane"))
    goals = _goal_store(_goal_row("sess-busy", "active", turns=0))
    leg = RUNNER.driverless_leg(
        census, goals=goals, read_at="2026-10-18T00:00:00Z",
        lane_names_fn=lambda: {},
        lane_turn_open_fn=lambda: {"sess-busy": True},
        lane_activity_fn=lambda: _activity_store(),
        now=dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc),
    )

    cov = leg["coverage"]
    assert cov["driven"] == 1 and cov["armed_inert"] == 0, cov
    assert cov["lanes_with_a_turn_in_flight"] == 1, cov
    assert cov["lanes"][0]["reading"] == "DRIVEN", cov["lanes"]
    assert leg["problems"] == [], leg["problems"]

    # THE CONTROL, same fixture, turn closed: without the binding fact the very same rows read
    # ARMED-INERT and the lane IS a problem. Both halves in one probe, so the assertion cannot
    # pass by the binding fact being ignored in both directions.
    idle = RUNNER.driverless_leg(
        census, goals=goals, read_at="2026-10-18T00:00:00Z",
        lane_names_fn=lambda: {},
        lane_turn_open_fn=lambda: {"sess-busy": False},
        lane_activity_fn=lambda: _activity_store(),
        now=dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc),
    )
    assert idle["coverage"]["armed_inert"] == 1, idle["coverage"]
    assert len(idle["problems"]) == 1, idle["problems"]

def test_a_census_with_NO_grouping_renders_NOT_RUN_never_a_clean_lane() -> None:
    """An unasked question must not render like a lane with nothing on it (#133).

    The failure this forbids is the one every zero-shaped leg is one refactor away from: the
    census ran NOT RUN, its grouping is absent, and a leg that iterated `coverage.get(...) or
    []` would print `0 DRIVERLESS` — a clean bill of health for a question nobody asked.
    """
    leg = RUNNER.driverless_leg({"name": "stall-census", "status": "NOT RUN",
                                 "problems": [], "excused": [],
                                 "coverage": {"reason": "the ledger could not be read"}},
                                goals=_goal_store(), read_at="2026-10-18T00:00:00Z",
                                lane_activity_fn=lambda: _activity_store())
    assert leg["status"] == "NOT RUN", leg
    assert leg["problems"] == [], leg
    assert "owed_by_lane" in leg["coverage"]["reason"], leg["coverage"]
    assert leg["coverage"]["census_status"] == "NOT RUN", leg["coverage"]

    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-18T00:00:00Z",
                        issues=[])
    assert "LEG driverless-lane — NOT RUN" in out, out
    assert "NOT RUN: " in out, out
    assert "census status this round: NOT RUN" in out, out
    # THE DISCRIMINATING HALF: no reading counts at all, so nothing can be read as clean.
    assert "DRIVEN" not in out, out
    assert "DRIVERLESS" not in out, out
    assert "readings:" not in out, out

def test_an_UNREACHED_goal_store_prints_as_UNREACHED_not_as_a_driverless_lane() -> None:
    """A lane on an unopened home reads DRIVERLESS for want of a READ (#133).

    That is a true statement about this reader and a false one about the lane, so the render
    must name the unreached home beside the reading — otherwise the leg manufactures exactly
    the finding it is meant to report, and a reader has no way to tell the two apart.
    """
    census = _census_with(_lane_slot("sess-x", ["#9"], lane="Unread Lane"))
    leg = RUNNER.driverless_leg(
        census,
        goals=_goal_store(unreached=["ops: unable to open database file"]),
        read_at="2026-10-18T00:00:00Z",
        lane_names_fn=lambda: {},
        lane_activity_fn=lambda: _activity_store(),
        now=dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc),
    )
    # The reading itself is honest: no row was found, so nothing was armed AS FAR AS THIS READ.
    assert leg["coverage"]["driverless"] == 1, leg["coverage"]
    assert leg["coverage"]["goal_homes_unreached"] == ["ops: unable to open database file"]

    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-18T00:00:00Z",
                        issues=[])
    assert "1 UNREACHED" in out, out
    assert "ops: unable to open database file" in out, out
    assert "for want of a read, not for want of a driver" in out, out
    # DISCRIMINATING CONTROL: the same leg with a store that WAS read carries no UNREACHED
    # line, so the sentence is attributable to the unread home and not to the leg's shape.
    clean = RUNNER.driverless_leg(census, goals=_goal_store(_goal_row("sess-x", "active")),
                                  read_at="2026-10-18T00:00:00Z", lane_names_fn=lambda: {},
                                  lane_activity_fn=lambda: _activity_store(),
                                  now=dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc))
    assert clean["coverage"]["driverless"] == 0, clean["coverage"]
    clean_out = RUNNER.render([clean], [], slug="owner/repo",
                              read_at="2026-10-18T00:00:00Z", issues=[])
    assert "UNREACHED" not in clean_out, clean_out

def test_a_PAUSED_row_with_measured_WORK_inside_the_window_is_UNARMED_ACTIVE() -> None:
    """(a) The filed defect, in one assertion: work inside the window is NOT driverless.

    The lane below is exactly the shape the ledger carried -- a goal row that stopped four days
    before the read, and work landing inside the census's own window. The pre-#532 leg called
    that DRIVERLESS and refused a re-arm on the strength of a claim about the future it could
    not support. It is UNARMED-ACTIVE, and the re-arm is refused for the OPPOSITE reason: the
    lane is working, so it does not need a driver installed.
    """
    leg = _driverless_probe(_activity_store(work={"sess-x": "2026-10-21T06:00:00+00:00"}))

    cov = leg["coverage"]
    assert cov["unarmed_active"] == 1, cov
    assert cov["driverless"] == 0, cov
    assert cov["lanes"][0]["reading"] == "UNARMED-ACTIVE", cov["lanes"]
    # THE INSTANT IT RESTS ON IS ON THE RECORD AND IN THE RENDER (#532, criterion 3): a reading
    # that says "working" without saying WHEN is unfalsifiable by the reader.
    assert cov["lanes"][0]["activity_instant"] == "2026-10-21T06:00:00+00:00", cov["lanes"]
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T12:00:00Z",
                        issues=[])
    assert "1 UNARMED-ACTIVE" in out, out
    assert "2026-10-21T06:00:00+00:00" in out, out
    # ... and it is still a PROBLEM, because a backlog behind a lane this leg cannot see driving
    # is still owed an owner's look -- the reading changes the REMEDY, not the attention.
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "UNARMED-ACTIVE LANE Probe Lane" in leg["problems"][0], leg["problems"][0]
    # THE BITE, and it is the whole ruling: no re-arm, and the reason cites the measurement.
    assert "The ACT is NOT a re-arm" in leg["problems"][0], leg["problems"][0]
    assert "installing a driver on a running lane" in leg["problems"][0], leg["problems"][0]

def test_the_SAME_paused_row_with_NO_work_in_the_window_still_reads_DRIVERLESS() -> None:
    """(b) The control for (a), same fixture, one fact changed.

    Without this half, (a) could pass on a leg that had stopped distinguishing the two readings
    at all -- and the census's whole point is that a genuinely stopped lane must still red. The
    work here is OLD (outside the 1.0 d window), which is the discriminating fact: a reader that
    keyed on "has ever run" rather than "ran inside the window" would call this UNARMED-ACTIVE.
    """
    leg = _driverless_probe(_activity_store(work={"sess-x": "2026-10-15T06:00:00+00:00"}))

    cov = leg["coverage"]
    assert cov["driverless"] == 1, cov
    assert cov["unarmed_active"] == 0, cov
    assert cov["lanes"][0]["reading"] == "DRIVERLESS", cov["lanes"]
    # The instant still prints, so "no work since T" is distinguishable from "not read".
    assert cov["lanes"][0]["activity_instant"] == "2026-10-15T06:00:00+00:00", cov["lanes"]
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T12:00:00Z",
                        issues=[])
    assert "1 DRIVERLESS" in out, out
    # ... and the DRIVERLESS line must NOT assert the future: the pre-#532 text said "nothing
    # will evaluate this session's goal", which two facts cannot support.
    assert "nothing will evaluate" not in out, out
    assert "no measured work since" in out, out

def test_an_UNREADABLE_activity_source_reads_UNREADABLE_and_never_counts_as_ZERO() -> None:
    """(c) #271 on the new source: "could not look" is not "nothing happened".

    The pre-#532 shape is one refactor away from every lane on an unopened home reading
    DRIVERLESS -- a true statement about this reader and a false one about the lane. The
    discriminator is the third reading, and the render must name the REASON so a reader can
    tell the two apart.
    """
    leg = _driverless_probe(
        _activity_store(readable=False, reason="no home carried tool_executions")
    )

    cov = leg["coverage"]
    assert cov["unreadable"] == 1, cov
    assert cov["driverless"] == 0, cov
    assert cov["unarmed_active"] == 0, cov
    assert cov["lanes"][0]["reading"] == "UNREADABLE", cov["lanes"]
    assert cov["activity_readable"] is False, cov
    assert "no home carried tool_executions" in cov["activity_reason"], cov
    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T12:00:00Z",
                        issues=[])
    assert "1 UNREADABLE" in out, out
    assert "no home carried tool_executions" in out, out
    # THE DISCRIMINATING HALF: no DRIVERLESS count at all, so the unread source cannot be read
    # as "these lanes have no work".
    assert "1 DRIVERLESS" not in out, out

def test_the_activity_WINDOW_and_its_BASIS_print_on_every_run() -> None:
    """The window is the CENSUS's constant, not this leg's -- so it prints with its basis.

    A reading that says "inside the window" while leaving the window unnamed is a claim the
    reader cannot check, and the number is not even this leg's own: it is
    `STALL_CENSUS_THRESHOLD_DAYS`, whose meaning is "the shortest interval in which a lane that
    intends to take a dispatched item would have claimed it". Asserted through the RENDER, since
    a coverage key nobody prints is a fact the report does not carry.
    """
    leg = _driverless_probe(_activity_store(work={"sess-x": "2026-10-21T06:00:00+00:00"}))
    cov = leg["coverage"]
    assert cov["activity_window_days"] == float(RUNNER.STALL_CENSUS_THRESHOLD_DAYS), cov
    assert cov["activity_window_basis"] == RUNNER.STALL_CENSUS_THRESHOLD_BASIS, cov

    out = RUNNER.render([leg], [], slug="owner/repo", read_at="2026-10-21T12:00:00Z",
                        issues=[])
    assert "activity window: 1 day(s)" in out, out
    assert RUNNER.STALL_CENSUS_THRESHOLD_BASIS in out, out
    # ... and the store's own outcome prints too, so "READ" is never assumed silently.
    assert "activity store: READ" in out, out

def test_the_window_BOUNDARY_is_INCLUSIVE_and_the_probe_CAN_cross_it() -> None:
    """The boundary is asserted from BOTH sides, one second apart.

    A predicate tested only on the comfortable side of its threshold is a predicate whose
    threshold was never exercised, so the same fixture is read at exactly the window's edge and
    one second past it -- and the two verdicts must differ. That difference IS the probe: a leg
    that ignored the window would return the same reading twice.
    """
    window_secs = float(RUNNER.STALL_CENSUS_THRESHOLD_DAYS) * 86400.0
    edge = _NOW - dt.timedelta(seconds=window_secs)
    just_past = edge - dt.timedelta(seconds=1)

    inside = _driverless_probe(_activity_store(work={"sess-x": edge.isoformat()}))
    outside = _driverless_probe(_activity_store(work={"sess-x": just_past.isoformat()}))

    assert inside["coverage"]["lanes"][0]["reading"] == "UNARMED-ACTIVE", inside["coverage"]
    assert outside["coverage"]["lanes"][0]["reading"] == "DRIVERLESS", outside["coverage"]

def test_an_ACTIVE_row_still_outranks_the_activity_fact() -> None:
    """The fourth reading must not steal a lane that HAS a driver.

    UNARMED-ACTIVE means "no active row". A lane with a live, advancing goal row reads DRIVEN
    even while it is also measurably working -- the reading is about what is ARMED, and a leg
    that preferred the activity fact would report every busy lane as unarmed. Asserted as a pair
    so neither half can pass alone.
    """
    driven = _driverless_probe(
        _activity_store(work={"sess-x": "2026-10-21T06:00:00+00:00"}), goal_state="active"
    )
    # the fixture's active row also carries motion (`turns_used > 0`, touched after creation), so
    # the card's DRIVEN row owns it -- what matters here is that NEITHER active-row reading is
    # UNARMED-ACTIVE: the activity fact decides only where NO row is armed.
    assert driven["coverage"]["lanes"][0]["reading"] == "DRIVEN", driven["coverage"]
    assert driven["coverage"]["unarmed_active"] == 0, driven["coverage"]

def test_an_UNRESOLVABLE_activity_root_is_UNREADABLE_and_never_RAISES() -> None:
    """Clause 4, at the SHIPPED depth: no locatable home is an UNREAD reason, not a crash.

    The shipped tree carries `registry/fleet.example.json` and no manifest, so
    `opencrabs_home_dbs` raises `FleetManifestError` -- and an unguarded reader took the whole
    patrol down from `TEMPLATE/` (35 red arms in `test_template_gate_pairing.py`, every one a
    traceback out of `main()`). A guard that let the error through would honour "never a zero"
    and miss the point: the ruling says an unreadable source yields UNREADABLE WITH ITS REASON.

    Driven through the REAL reader rather than an injected one, because the defect was in the
    reader's own failure path -- an injected fixture would have replaced exactly the code under
    test.
    """
    with mock.patch.object(RUNNER, "load_module") as loader:
        registry = mock.Mock()
        registry.FleetManifestError = RuntimeError
        registry.opencrabs_home_dbs.side_effect = RuntimeError(
            "the fleet manifest declares no `profile_root`"
        )
        loader.return_value = registry
        store = RUNNER.box_lane_activity()

    assert store["readable"] is False, store
    assert store["epochs"] == {}, store
    assert store["newest"] == {}, store
    assert "could not be located" in store["reason"], store
    assert "profile_root" in store["reason"], store

    # AND THE READING IT PRODUCES IS UNREADABLE, never DRIVERLESS -- the discriminating half.
    leg = _driverless_probe(store)
    assert leg["coverage"]["lanes"][0]["reading"] == "UNREADABLE", leg["coverage"]
    assert leg["coverage"]["driverless"] == 0, leg["coverage"]

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
