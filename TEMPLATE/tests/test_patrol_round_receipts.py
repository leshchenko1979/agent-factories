"""Gate: a round's fires against its receipts — #499/#500/#501/#585

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
    _499_FIRE_HOURS,
    _499_READ_AT,
    _499_ROUND,
    _500_FIRE_HOURS,
    _500_READ_AT,
    _CLOSE_TS,
    _DUTY_BOUND,
    _EMPTY_GOAL_STORE,
    _NO_RULING_EXEMPTIONS,
    _activity_store,
    _comment_numeric,
    _duty_leg,
    _duty_row,
    _fires,
    _goal_store,
    _issue,
    _issue_with_comments,
    _plus,
    _run,
    _stall_row,
    _stub_publish_leg,
    _stub_shared_tree_rider,
    _swept,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _499_row(**kw) -> dict:
    """The duty row whose newest fire is the LAST of the four — the round is their date."""
    kw.setdefault("last_run_at", _plus(_DUTY_BOUND, _499_FIRE_HOURS[-1]))
    return _duty_row(**kw)

def _499_receipt(hour: float, n: int, *, token_hour: str | None = None) -> dict:
    """A receipt for the fire at `hour`, or — when `token_hour` is given — one that keys a
    DIFFERENT hour, which is a row that declares a duty and answers no fire."""
    fire = _plus(_DUTY_BOUND, hour)
    token = token_hour if token_hour is not None else fire[11:13]
    return {"n": n, "ts": _plus(_DUTY_BOUND, hour + 0.25), "event": "run",
            "actor": "delegate", "subject": f"registry-attest-{_499_ROUND}T{token}",
            "detail": "the round completed. duty=completed"}

def _499_leg(receipt_hours, *, fires=None, read_at=_499_READ_AT, **kw) -> dict:
    return _duty_leg(
        [_499_row()], list(receipt_hours),
        fires=_fires(fires if fires is not None else _499_FIRE_HOURS),
        read_at=read_at, **kw)

def _500_rows() -> list[dict]:
    """ONE receipt, ts-EQUAL to the FIRST of the four fires.

    It answers the first fire exactly and every later fire with a negative gap, so the
    measured max is 0.0 -- NOT None, which is the whole defect: the `is None` guard passed
    it straight through to the division.
    """
    first = _plus(_DUTY_BOUND, _500_FIRE_HOURS[0])
    return [{"n": 1, "ts": first, "event": "run", "actor": "delegate",
             "subject": f"registry-attest-{first[:10]}",
             "detail": "the round completed. duty=completed"}]

def _500_row(**kw) -> dict:
    kw.setdefault("last_run_at", _plus(_DUTY_BOUND, _500_FIRE_HOURS[-1]))
    return _duty_row(**kw)

def _500_residual(rows) -> dict:
    return RUNNER.duty_residual_for(
        _500_row(), "registry-attest", fires=_fires(_500_FIRE_HOURS), ledger_rows=rows)

def _501_clean():
    """A board the round can sweep clean, so the ONLY variable is the raising leg."""
    issues = [_issue(1, "OPEN")]
    rows = _swept(("intake", "#1", 1), ("ruling", "#1", 5))
    return issues, rows

def _raising_publish_leg(*, read_at: str) -> dict:
    """A MIDDLE leg that raises, so legs on BOTH sides of it are asserted to survive.

    `publish-freshness` is leg 16 of 18: `kit-drift` precedes it and `worktree` and
    `pacemaker-presence` follow it. Under the old shape those last two were exactly the
    legs that vanished.
    """
    raise RuntimeError("probe: the publish leg could not read the remote")

def _leg_names(text: str) -> list[str]:
    return [line.split()[1] for line in text.splitlines() if line.startswith("LEG ")]

def _leg_status(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("LEG ") and " \u2014 " in line:
            name, status = line[4:].split(" \u2014 ", 1)
            out[name] = status
    return out

# --- this leg's tests -------------------------------------------------------
def test_the_fires_arm_REDs_a_round_that_fired_more_often_than_it_reported() -> None:
    """Acceptance 1: four fires, three receipts — the day is UNDER-RECEIPTED and the fire
    that answered nothing is NAMED by its own instant.

    This is the exact state that read CLEAN before the arm existed: one receipt satisfied
    `if not receipts`, and `last_run_at` records only the newest fire, so the three earlier
    ones left no trace in any field the leg read.
    """
    leg = _499_leg([_499_receipt(h, i + 1) for i, h in enumerate(_499_FIRE_HOURS[:3])])
    assert leg["status"] == "ASSERTED", leg["reason"]
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 1, cov
    assert cov["rounds_under_receipted"] == 1, cov
    named = "\n".join(leg["problems"])
    assert "UNDER-RECEIPTED" in named, named
    assert _plus(_DUTY_BOUND, _499_FIRE_HOURS[-1]) in named, (
        f"the finding must NAME the fire that found no receipt: {named}")
    assert cov["duties_judged"][0]["fires"] == 4, cov["duties_judged"]
    assert cov["duties_judged"][0]["fires_unanswered"] == 1, cov["duties_judged"]

def test_the_fires_arm_is_CLEAN_when_every_fire_answered() -> None:
    """The CONTROL for the probe above: the SAME fixture with the fourth receipt present.

    Without it the RED above is attributable to the fixture rather than to the missing
    receipt — a finding that survives its own input being fixed is not a finding.
    """
    leg = _499_leg([_499_receipt(h, i + 1) for i, h in enumerate(_499_FIRE_HOURS)])
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 0, (cov, leg["problems"])
    assert cov["rounds_under_receipted"] == 0, cov
    # SCOPED TO THE RECEIPT ARMS, because `problems` also carries the cadence class
    # (ruling n=4153) and this arm's subject is the FIRES arm.
    assert not [p for p in leg["problems"] if "UNDER-RECEIPTED" in p], leg["problems"]
    # #621 PINNED HERE, and it is the whole point of the fix. All four receipts key ONE
    # round date, so while the round was the PAIRING key "newest candidate wins" charged
    # the FIRST fire a 12.25 h latency (44100 s measured max over 4 rounds) and the derived
    # residual reached 12.25x the 4 h cadence. Each fire is now answered by its own
    # receipt, which the fixture writes at fire + 0.25 h -- so the measured max must be
    # exactly 900 s over 4 rounds, and the cadence finding must be GONE because nothing
    # was actually late. Asserting only `rounds_over_cadence == 0` would leave the
    # latency unmeasured and pass equally if the arm had simply stopped observing.
    residual = cov["residuals"][0]
    assert residual["measured_rounds"] == 4, residual
    assert residual["measured_max_secs"] == 900.0, residual
    assert cov["rounds_over_cadence"] == 0, cov
    # The cadence class's own positive controls live in tests/test_patrol_tree_instants.py
    # (arms asserting rounds_over_cadence == 1 on a genuinely over-cadence fixture), so
    # reading 0 here cannot silently retire the class.

def test_the_fires_arm_REDs_a_receipt_that_keys_its_COMPLETION_hour() -> None:
    """The 10-06 miss, reproduced: the fire is at 06:50 and the lane wrote a `T09` row.

    ONE fire, ONE receipt, and the round matched — so every predicate this leg had before
    the arm read CLEAN. The token answers no fire, so the day is unreported and the arm
    says so. This is the clause that makes the predicate a CONTENT comparison rather than
    a count: a row existing is not a row answering.
    """
    leg = _499_leg([_499_receipt(0.5, 1, token_hour="09")], fires=(0.5,))
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 1, (cov, leg["problems"])
    assert "UNDER-RECEIPTED" in "\n".join(leg["problems"]), leg["problems"]
    assert cov["duties_missing"] == 0, (
        "the round DID declare a duty — this is the under-receipted class, not a missing "
        f"duty, and folding them together would misreport the repair: {cov}")

def test_the_fires_arm_does_not_charge_a_ROUND_LEVEL_receipt() -> None:
    """The LIVE false RED of 2026-10-16, reproduced: a DATE-ONLY receipt on a 4-fire day.

    `factory-insights-weekly` fired four times and wrote `insights-2026-10-16` — no `T<HH>`
    anywhere, because a round-level job writes ONE receipt for its round. An earlier form of
    this predicate demanded an hour token from every receipt and charged all four fires, so
    three correctly-receipted jobs on the live box read UNDER-RECEIPTED (#146's false-RED
    class, found only by driving the real ledger). The hour is the WRITER's convention to
    choose (#159): where a round's receipts carry no hour at all, the round IS the unit and
    its receipt answers every fire in it.
    """
    date_only = {"n": 1, "ts": _plus(_DUTY_BOUND, 0.75), "event": "run", "actor": "delegate",
                 "subject": f"registry-attest-{_499_ROUND}",
                 "detail": "the round completed. duty=completed"}
    leg = _499_leg([date_only])
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 0, (cov, leg["problems"])
    assert cov["rounds_under_receipted"] == 0, cov
    assert not leg["problems"], (
        "a round-level receipt declares the round; charging it per-fire is the false RED: "
        f"{leg['problems']}")

def test_the_fires_arm_still_REDs_when_an_HOUR_keyed_round_skips_one() -> None:
    """The CONTROL for the probe above — and the guard against over-correcting into a false
    CLEAN.

    The exemption must key on the ROUND's convention, not on a receipt merely lacking an
    hour: here the round writes hours for 3 of its 4 fires, so the convention IS hour-keyed
    and the fourth fire is genuinely unanswered. A predicate that accepted any date-only
    token would read this CLEAN — and would then also read the 10-06 `T09` miss clean the
    moment one receipt dropped its hour.
    """
    receipts = [_499_receipt(h, i + 1) for i, h in enumerate(_499_FIRE_HOURS[:3])]
    receipts.append({"n": 9, "ts": _plus(_DUTY_BOUND, 1.0), "event": "run",
                     "actor": "delegate", "subject": f"registry-attest-{_499_ROUND}",
                     "detail": "the round completed. duty=completed"})
    leg = _499_leg(receipts)
    cov = leg["coverage"]
    assert cov["fires_unanswered"] == 1, (
        "an hour-keyed round that also carries a bare date token still owes its fourth "
        f"fire a receipt: {cov}")
    assert _plus(_DUTY_BOUND, _499_FIRE_HOURS[-1]) in "\n".join(leg["problems"])

def test_the_fires_arm_counts_only_the_round_it_judges() -> None:
    """A fire on ANOTHER date contributes no round to this one.

    `round_fire_instants` filters by the round's own date, so a job that fired yesterday
    and today is judged per day. Without the filter the older fires would be charged to
    today's receipts and every round would read under-receipted.
    """
    fires = (_499_FIRE_HOURS[0], _499_FIRE_HOURS[0] - 24.0)  # one today, one yesterday
    leg = _499_leg([_499_receipt(_499_FIRE_HOURS[0], 1)], fires=fires)
    cov = leg["coverage"]
    assert cov["duties_judged"][0]["fires"] == 1, (
        f"only the round's OWN date may be counted: {cov['duties_judged']}")
    assert cov["fires_unanswered"] == 0, (cov, leg["problems"])

def test_the_fires_arm_does_not_charge_a_fire_still_inside_its_residual() -> None:
    """The false-RED guard (#146, #200/#449): a fire younger than the job's residual has a
    lane still working on it, and charging it a receipt would trade a false CLEAN for a
    false RED.

    Driven at the helper, where the window is stated rather than derived, so the guard is
    tested as a predicate and not as a side effect of the fixture's timing.
    """
    fire = _plus(_DUTY_BOUND, 0.5)
    read = RUNNER.reader_parse_ts(_plus(_DUTY_BOUND, 0.6))  # 6 minutes after the fire
    assert RUNNER.unanswered_fires(
        [fire], "registry-attest", _499_ROUND, [], residual_secs=3600.0,
        read_instant=read, parse=RUNNER.reader_parse_ts) == [], (
        "a fire inside its residual is IN FLIGHT and owes no receipt yet")
    assert RUNNER.unanswered_fires(
        [fire], "registry-attest", _499_ROUND, [], residual_secs=60.0,
        read_instant=read, parse=RUNNER.reader_parse_ts) == [fire], (
        "past the residual the same fire IS owed a receipt")

def test_the_fires_arm_token_is_BOUNDARY_checked() -> None:
    """`T06` is not satisfied by `T060` — the same boundary guard the round prefix keeps.

    A bare `startswith` would let a receipt for a DIFFERENT hour certify this fire, which
    is a false CLEAN wearing a match.
    """
    fire = _plus(_DUTY_BOUND, 0.5)  # 07:31, token T07
    exact = {"subject": f"registry-attest-{_499_ROUND}T07"}
    wider = {"subject": f"registry-attest-{_499_ROUND}T070"}
    assert RUNNER.unanswered_fires([fire], "registry-attest", _499_ROUND, [exact]) == []
    assert RUNNER.unanswered_fires([fire], "registry-attest", _499_ROUND, [wider]) == [fire], (
        "a token that merely extends the hour's digits answers a DIFFERENT fire")

def test_the_fires_arm_prints_its_population_on_a_CLEAN_round() -> None:
    """#242: a clean round states what it counted. A reader who sees no line cannot tell
    `0 fires unanswered` from `the leg never counted fires` — and a leg that silently
    examines nothing renders exactly like one that examined everything and found nothing.
    """
    rc, out, err = _run(
        [], [_499_receipt(0.5, 1)], cron_rows=[_duty_row()], prefixes=["factory-"],
        cron_fires=_fires((0.5,)))
    assert "LEG duty-receipt" in out, out[-3000:]
    assert "fires vs receipts:" in out, out[-4000:]
    assert "0 fire(s) left unanswered" in out, out[-4000:]
    assert "UNDER-RECEIPTED" not in out, out[-4000:]

def test_the_fires_arm_renders_the_UNDER_RECEIPTED_round_it_found() -> None:
    """The other render branch, driven through `main()`: the fires/receipts line must reach
    the report rather than being computed and dropped (#242's swallow).
    """
    rc, out, err = _run(
        [], [_499_receipt(h, i + 1) for i, h in enumerate(_499_FIRE_HOURS[:3])],
        cron_rows=[_499_row()], prefixes=["factory-"],
        cron_fires=_fires(_499_FIRE_HOURS))
    assert "fires vs receipts:" in out or "UNDER-RECEIPTED" in out, out[-4000:]

def test_the_zero_max_guard_keeps_margin_for_RAISING() -> None:
    """Acceptance 1: the guard is at the CALLER, so the SHARED law is unchanged.

    A fix that caught the zero INSIDE `margin_for` would silence the predicate for every
    caller in the fleet, including the gate-budget manifest's own derivation. This asserts
    the raise still happens, at the bytes.
    """
    margin_for = RUNNER.gate_budget_module().margin_for
    try:
        margin_for(0.0)
    except ZeroDivisionError:
        return
    raise AssertionError(
        "margin_for(0.0) no longer raises — the #500 guard leaked into shared law "
        "(tools/gate_budget.py), whose own probes pin the division")

def test_the_zero_max_guard_returns_the_DEFAULT_instead_of_raising() -> None:
    """Acceptance 2: the exact fixture that crashed the derivation returns the default.

    `measured_rounds` is asserted beside the basis, because the requirement is that the
    reading is STATED rather than silent: a default that also hid the one round it measured
    would render identically to a job that never fired at all.
    """
    residual = _500_residual(_500_rows())
    assert residual["basis"] == "default", residual
    assert residual["measured_max_secs"] == 0.0, residual
    assert residual["measured_rounds"] == 1, residual
    assert residual["margin_x"] is None, residual
    assert residual["residual_secs"] == float(RUNNER.DUTY_RESIDUAL_DEFAULT_SECS), residual

def test_the_zero_max_guard_CONTROL_derives_a_POSITIVE_max_normally() -> None:
    """The CONTROL for the probe above: a positive max still DERIVES.

    Without it the default could be the guard firing on EVERY fixture rather than on the
    zero — a change that replaced the whole derivation with the constant would pass the
    probe above and destroy the measurement (#449).
    """
    rows = [{**_500_rows()[0], "ts": _plus(_500_rows()[0]["ts"], 1.0)}]
    residual = _500_residual(rows)
    assert residual["basis"] == "derived", residual
    assert residual["measured_max_secs"] == 3600.0, residual
    assert residual["margin_x"] is not None, residual

def test_the_zero_max_guard_reaches_the_LEG_and_it_keeps_its_shape() -> None:
    """Acceptance 3: the fixture driven through `duty_receipt_leg`, the path a round runs.

    A guard that only satisfied the helper would leave the crash on the real path, and the
    leg is what the patrol actually calls. The assertion is that the leg RETURNS and that
    the record is the leg's normal shape — before the guard the exception propagated out of
    the derivation and, with no try/except around the leg list, took the round down.
    """
    leg = _duty_leg([_500_row()], _500_rows(), fires=_fires(_500_FIRE_HOURS),
                    read_at=_500_READ_AT)
    assert set(leg) >= {"name", "status", "problems", "excused", "coverage"}, sorted(leg)
    assert leg["status"] in ("ASSERTED", "NOT RUN"), leg["status"]
    assert leg["name"] == "duty-receipt", leg["name"]

def test_the_zero_max_guard_STATES_the_reading_in_the_render() -> None:
    """The render distinguishes a measured ZERO from an absent measurement.

    "no measurable round" and "measured, and the number is zero" are different facts, and a
    render printing one sentence for both would report a silent job and a clock-artefact job
    identically. The second half is the control: the absent case must not borrow the
    non-positive wording.
    """
    zero_text = RUNNER.duty_residual_basis_text(
        {"basis": "default", "measured_max_secs": 0.0, "measured_rounds": 1})
    absent_text = RUNNER.duty_residual_basis_text(
        {"basis": "default", "measured_max_secs": None, "measured_rounds": 0})
    assert "NON-POSITIVE" in zero_text, zero_text
    assert "NON-POSITIVE" not in absent_text, absent_text

def test_a_contained_round_still_carries_EVERY_leg_the_clean_round_carries() -> None:
    """The crux: a raise used to DELETE every leg after it, with no trace of its own.

    This is asserted as SET AND ORDER equality against a clean round's own leg list, so the
    probe fails both when a leg vanishes AND when the containment guard's name table drifts
    away from the legs it names -- a contained leg is only useful if the name is right.
    """
    issues, rows = _501_clean()
    _, clean_out, _ = _run(issues, rows)
    _, out, _ = _run(issues, rows, publish_fn=_raising_publish_leg)

    clean, got = _leg_names(clean_out), _leg_names(out)
    assert got == clean, (
        "a contained round must carry the SAME legs as a clean one, in the same order -- a "
        f"missing leg IS the silent failure #501 is about\nclean: {clean}\ngot:   {got}"
    )
    # EXACTLY ONE status may differ from the clean round's: the raiser's. Comparing against
    # the clean run's OWN statuses rather than against "ASSERTED" is the point -- several
    # legs are legitimately NOT RUN under `_run`'s inert defaults, and a probe that demanded
    # ASSERTED of them would be asserting the fixture, not the containment.
    clean_statuses = _leg_status(clean_out)
    statuses = _leg_status(out)
    assert statuses == {**clean_statuses, "publish-freshness": "FAILED"}, (
        "containment must change EXACTLY the raising leg's status and nothing else\n"
        f"clean: {clean_statuses}\ngot:   {statuses}"
    )

def test_a_raising_leg_is_NAMED_with_its_reason_and_moves_the_exit_code() -> None:
    """Criterion (a)+(d): a FAILED leg named for ITSELF, with the reason, and rc reflects it.

    A containment that swallowed the problem would be worse than the abort: the round would
    read CLEAN over a leg that never ran. So the problem is asserted to be COUNTED and the
    exit code asserted to move.
    """
    issues, rows = _501_clean()
    rc, out, _ = _run(issues, rows, publish_fn=_raising_publish_leg)

    assert rc == 1, f"a contained leg's problem must still move the exit code\n{out}"
    block = out.split("LEG publish-freshness")[1].split("LEG ")[0]
    assert "FAILED" in block.split("\n")[0], block
    assert "RuntimeError" in block, block
    assert "could not read the remote" in block, block
    assert "problems: 1" in block, block
    assert "UNKNOWN" in block, (
        f"the containment must state that the leg's verdict is UNKNOWN, not clean: {block}"
    )
    assert "verdict:" in out, f"the round must STILL print a verdict\n{out}"

def test_the_containment_guard_changes_NOTHING_on_a_clean_round() -> None:
    """CONTROL: with no leg raising, the guard is invisible -- rc, verdict and legs alike.

    A guard that perturbed the clean path would move every other probe in this file, and
    the honest way to say it does not is to assert the clean round is unchanged.
    """
    issues, rows = _501_clean()
    rc, out, _ = _run(issues, rows)

    assert rc == 0, f"a clean round must stay clean\n{out}"
    assert "FAILED" not in out, out
    assert "0 problem(s)" in out, out
    assert len(_leg_names(out)) == len(set(_leg_names(out))), "no leg may be named twice"

def test_the_board_read_abort_path_is_UNCHANGED_by_the_containment_guard() -> None:
    """Criterion (c): the abort BEFORE the legs is by design, and it is the leg-free case.

    The board read happens before any leg exists, so containment cannot apply there: the run
    must still abort with rc=2, name every leg NOT RUN, and print NO verdict. A guard that
    caught this too would replace a loud abort with a quiet round over zero issues.
    """
    def _boom(slug):
        raise RUNNER.BoardReadError("probe: the board could not be read")

    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [], board_fn=_boom, slug_fn=lambda: "owner/repo", rows_fn=lambda: [],
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        publish_fn=_stub_publish_leg, shared_tree_fn=_stub_shared_tree_rider,
        # #133: the driverless-lane leg's goal store and its turn-in-flight read are
        # injected here for the same reason every other live surface is -- and the
        # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
        # granting one, so a probe that never asserts a driver cannot read one.
        driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
        driverless_turn_open_fn=lambda: {},
    )
    assert rc == 2, f"the board-read abort must be unchanged, got rc={rc}"
    assert "NOT RUN: every leg" in err.getvalue(), err.getvalue()
    assert "verdict" not in out.getvalue(), out.getvalue()

def test_a_raise_in_the_FIRST_leg_still_prints_a_verdict() -> None:
    """Criterion (b), on the leg whose OWN render branch reads coverage keys it lacks.

    The probes above raise in `publish-freshness`, which is leg 16 of 18 AND whose render
    branch is status-guarded -- so they prove the BUILD half (the leg is named, its problem
    counts, its neighbours survive) but they cannot exercise the REPORT half, because that
    leg's branch tolerates a leg that never built. `board-intake` is leg 1 of 18 and its
    branch reads `forward_issues_examined` and `reverse_intake_rows_examined` with NO status
    guard, and a leg that never built has neither key.

    So without the FAILED branch the round raises `KeyError` while printing its own report:
    the same silent-failure class one layer down, and the reason the branch is load-bearing
    rather than decorative. Disable it and this probe errors with the KeyError; that is its
    bite, and it is the only probe here that bites on the report half at all.
    """
    real = RUNNER.board_intake_leg

    def _boom(*a, **k):
        raise RuntimeError("probe: board-intake could not read the board")

    issues, rows = _501_clean()
    _, clean_out, _ = _run(issues, rows)

    RUNNER.board_intake_leg = _boom
    try:
        rc, out, err = _run(issues, rows)
    finally:
        RUNNER.board_intake_leg = real

    assert "verdict:" in out, f"the round must STILL print a verdict\n{out}\n{err}"
    assert rc == 1, f"a contained leg's problem must still move the exit code\n{out}"
    block = out.split("LEG board-intake")[1].split("LEG ")[0]
    assert "FAILED" in block.split("\n")[0], block
    assert "RuntimeError" in block, block
    # Leg 1 raising must not delete the other seventeen: the report is built from the SAME
    # leg list the clean round produced, in the same order.
    assert _leg_names(out) == _leg_names(clean_out), (
        "a raise in the FIRST leg must not vanish the ones after it\n"
        f"clean: {_leg_names(clean_out)}\ngot:   {_leg_names(out)}"
    )

def test_probe_the_NAMED_arm_returns_every_board_ref_in_row_order() -> None:
    """The arm itself, on the shape the defect was filed for.

    `#579` is the ruling's own subject, so `strict` answers for it — and the two mechanisms
    it ORDERS are ADDED, not substituted. That additivity is the ruling's own constraint: if
    the named refs only answered when no other arm did, the ordering ruling would still
    resolve to `#579` alone and the defect would survive its own fix.
    """
    pred = RUNNER.load_predicate()
    ruling = {"n": 4460, "event": "ruling", "subject": "#579",
              "detail": "orders the mechanisms #582 and #583",
              "refs": [{"board": "#583"}, {"board": "#582"}]}

    issues, arm, bridge = RUNNER.resolve_ruling_issues(ruling, [ruling], pred)
    # ROW ORDER, not sorted order: the row is the record, and re-ordering it here would
    # print a sequence the ledger does not carry.
    assert issues == [579, 583, 582], issues
    assert (arm, bridge) == ("strict", None), (arm, bridge)

    # The SINGULAR adapter still answers the primary, so the two callers that ask about one
    # unit are not handed a list they would have to guess the first element of.
    assert RUNNER.resolve_ruling_issue(ruling, [ruling], pred) == (579, "strict", None)

def test_probe_PROSE_mentions_confer_NOTHING_on_the_named_arm() -> None:
    """The line the ruling drew, and the reason the edge is TYPED.

    The issue's own premise was that "the creating ruling already names #582 and #583 in its
    refs". Measured, it does not: `n=4460` mentions each three times in PROSE, carries
    `refs=None` and zero `governs=`. This probe holds that measurement as a fixture — a
    row identical to the one above but with the prose and WITHOUT the refs resolves to its
    subject alone. Without this leg the named arm could be implemented as a text scan and
    every other probe here would still pass.
    """
    pred = RUNNER.load_predicate()
    prose_only = {"n": 4460, "event": "ruling", "subject": "#579",
                  "detail": "#582 and #583 are ordered here; #582 again, and #583 again."}

    issues, arm, _bridge = RUNNER.resolve_ruling_issues(prose_only, [prose_only], pred)
    assert issues == [579], issues
    assert arm == "strict", arm

    # ...and a row whose ONLY placement is prose resolves to NOTHING, so the arm cannot be
    # reached through a mention even when no other arm answers.
    slug_with_prose = {"n": 4461, "event": "ruling", "subject": "a-concern",
                       "detail": "orders #582 and #583"}
    issues, arm, _bridge = RUNNER.resolve_ruling_issues(slug_with_prose, [slug_with_prose], pred)
    assert (issues, arm) == ([], "unbridgeable"), (issues, arm)

def test_probe_a_NAMED_only_row_reports_the_arm_it_was_reached_by() -> None:
    """Arm 4 is NAMED in the report, never implied.

    A resolution that does not say how it was reached cannot be re-litigated when the
    vocabulary moves — the same discipline the canonicality ladder uses. So a row placed by
    its board refs alone reports `"named"`, and a row placed by any other arm reports THAT
    arm even when it also names items.

    The malformed values are the point of the second half: `board:463` (no hash) and a bare
    `board:` OCCUPY the kind while naming no tracker item, so the shared predicate drops
    them and the row names nothing. Reading them as names would resolve to `463` and `""`.
    """
    pred = RUNNER.load_predicate()
    named_only = {"n": 1, "event": "ruling", "subject": "a-concern",
                  "detail": "no issue number anywhere in this detail",
                  "refs": [{"board": "#7"}, {"board": "#7"}, {"board": "463"}, {"board": ""}]}
    issues, arm, _bridge = RUNNER.resolve_ruling_issues(named_only, [named_only], pred)
    assert (issues, arm) == ([7], "named"), (issues, arm)
    # The duplicate `#7` is collapsed ONCE, in first-seen order.
    assert RUNNER.resolve_ruling_issue(named_only, [named_only], pred)[:2] == (7, "named")

def test_probe_board_unruled_STOPS_firing_on_a_mechanism_its_ruling_ORDERS() -> None:
    """THE DEFECT ITSELF, driven through the leg that reported it.

    `board_unruled_leg`'s question is "is this item RULED", so a ruling that ORDERS a
    mechanism settles it. Before the fix this fixture reds on `#582`/`#583`: both carry an
    intake row, both are OPEN, and neither had a `ruling` row of its own. That is the
    self-demonstration the issue is — the leg firing on items a published ruling created.

    NON-VACUITY: the same fixture WITHOUT the `board` refs still reds on both, so the green
    above is attributable to the typed edge and not to a leg that stopped judging.
    """
    pred = RUNNER.load_predicate()
    issues = [
        _issue_with_comments(579, "OPEN", "## RULED — orders two mechanisms.\n"),
        _issue_with_comments(582, "OPEN", "## A mechanism item.\n"),
        _issue_with_comments(583, "OPEN", "## A mechanism item.\n"),
    ]
    ruling = {"n": 4460, "event": "ruling", "subject": "#579",
              "detail": "orders the mechanisms #582 and #583",
              "refs": [{"board": "#582"}, {"board": "#583"}]}
    # THE INTAKE ROWS CARRY A DATED `ts`, and the probe would be VACUOUS without one: the
    # leg excuses an intake row it cannot date ("NOT JUDGED") instead of calling it owed, so
    # an undated fixture reads `owed == []` for the refs case AND for the control alike and
    # the non-vacuity arm below proves nothing. Seven hours back is past the 6.0 h threshold
    # at `read_at`, which is what makes the stripped-refs arm red.
    stamp = _plus(_CLOSE_TS, -7.0)
    rows = [ruling,
            {"n": 4472, "event": "intake", "subject": "#579", "detail": "intake", "ts": stamp},
            {"n": 4473, "event": "intake", "subject": "#582", "detail": "intake", "ts": stamp},
            {"n": 4474, "event": "intake", "subject": "#583", "detail": "intake", "ts": stamp}]

    leg = RUNNER.board_unruled_leg(issues, rows, read_at=_plus(_CLOSE_TS, 1.0), predicate=pred)
    assert leg["coverage"]["items_owed_ruling"] == 0, leg["coverage"]["owed"]
    assert leg["coverage"]["population_unruled"] == 0, leg["coverage"]["population"]
    # NON-VACUITY OF THE GREEN ITSELF: nothing was excused, so the zero above is the typed
    # edge doing the work and not the leg declining to judge an undated row.
    assert leg["excused"] == [], leg["excused"]
    cov = leg["coverage"]
    assert cov["resolution_arms"]["named"] == 0, cov["resolution_arms"]
    assert cov["rulings_named"] == 1, cov
    assert cov["named_via"] == [
        {"ruling_n": 4460, "primary": 579, "named": [582, 583], "arm": "strict"}
    ], cov["named_via"]

    # THE PARTITION STILL CLOSES, over ISSUE-RESOLVES rather than rows: one row added three
    # issues, so `resolved_rows - len(ruled)` would read 1 - 3 = -2. A negative repeat count
    # is the arithmetic telling the reader the partition does not close.
    assert cov["rulings_resolved_rows"] == 1, cov
    assert cov["rulings_issue_resolves"] == 3, cov
    assert cov["rulings_resolved"] == 3, cov
    assert cov["rulings_repeated"] == 0, cov
    assert cov["rulings_repeated"] >= 0, cov

    # NON-VACUITY: strip ONLY the refs and both mechanisms go back to owing a ruling.
    bare = dict(ruling)
    bare.pop("refs")
    without = RUNNER.board_unruled_leg(issues, [bare] + rows[1:],
                                       read_at=_plus(_CLOSE_TS, 1.0), predicate=pred)
    assert without["coverage"]["items_owed_ruling"] == 2, without["coverage"]["owed"]
    assert sorted(without["coverage"]["owed"]) == [582, 583], without["coverage"]["owed"]
    assert without["coverage"]["rulings_named"] == 0, without["coverage"]
    assert without["excused"] == [], without["excused"]

def test_probe_board_ruling_is_not_disturbed_by_the_widened_arity() -> None:
    """THE CONTROL THE RULING OWES (#585 clause 4).

    `board_ruling_leg` consumes the same resolver, so the landing owes a probe that the
    widened arity turns neither a ruled item into an unruled one nor the reverse on THAT
    leg. The leg's population is "every board issue carrying a ruling COMMENT", so a named
    ref must add to its `rulings_resolved` count and change nothing else: no problem, no
    unbridgeable row, the paired act still paired.
    """
    pred = RUNNER.load_predicate()
    issues = [
        _issue_with_comments(579, "OPEN", "## RULED — orders two mechanisms.\n"),
        _issue_with_comments(582, "OPEN", "## A mechanism item.\n"),
    ]
    ruling = {"n": 4460, "event": "ruling", "subject": "#579",
              "detail": f"orders #582; comment={_comment_numeric(579)}",
              "refs": [{"board": "#582"}]}
    leg = RUNNER.board_ruling_leg(issues, [ruling], read_at="probe", predicate=pred,
                                  scope=RUNNER.UNBOUNDED_SCOPE,
                                  exemptions_path=_NO_RULING_EXEMPTIONS)
    cov = leg["coverage"]
    assert leg["problems"] == [], leg["problems"]
    assert cov["rulings_unbridgeable"] == 0, cov
    assert cov["unbridgeable_rows"] == [], cov["unbridgeable_rows"]
    assert cov["rulings_paired"] == 1, cov
    assert cov["rulings_resolved_rows"] == 1, cov
    assert cov["rulings_issue_resolves"] == 2, cov
    assert cov["rulings_resolved"] == 2, cov
    assert cov["rulings_repeated"] == 0, cov
    assert cov["rulings_named"] == 1, cov
    assert cov["named_via"] == [
        {"ruling_n": 4460, "primary": 579, "named": [582], "arm": "strict"}
    ], cov["named_via"]

    # CONTROL: the SAME row without its refs reads ONE issue and one fewer resolve, and the
    # rest of the leg's verdict is untouched — so the delta is the ref and nothing else.
    bare = dict(ruling)
    bare.pop("refs")
    plain = RUNNER.board_ruling_leg(issues, [bare], read_at="probe", predicate=pred,
                                    scope=RUNNER.UNBOUNDED_SCOPE,
                                    exemptions_path=_NO_RULING_EXEMPTIONS)
    pcov = plain["coverage"]
    assert plain["problems"] == [], plain["problems"]
    assert pcov["rulings_resolved"] == 1, pcov
    assert pcov["rulings_issue_resolves"] == 1, pcov
    assert pcov["rulings_named"] == 0, pcov
    assert pcov["rulings_paired"] == 1, pcov

def test_probe_the_plural_never_LOSES_an_issue_the_singular_found() -> None:
    """REACHABILITY, as the ruling defines it (#585 clause 3).

    `set(issues_before) - set(issues_after)` must be EMPTY: widening may ADD items and must
    cost no existing one, the discipline `n=4157` used. Asserted here over every arm's
    fixture — strict, declared, bridged and unbridgeable — because the whole-ledger proof is
    a one-off measurement and a fixture-level invariant is what keeps it true afterwards.
    """
    pred = RUNNER.load_predicate()
    cases = [
        # strict, with and without refs
        {"n": 1, "event": "ruling", "subject": "#42", "detail": "ruled"},
        {"n": 1, "event": "ruling", "subject": "#42", "detail": "ruled",
         "refs": [{"board": "#9"}, {"board": "#10"}]},
        # declared
        {"n": 900, "event": "ruling", "subject": "a-concern", "detail": "governs=1234"},
        # bridged
        {"n": 545, "event": "ruling", "subject": "a-slug", "detail": "ruled"},
        # unbridgeable
        {"n": 901, "event": "ruling", "subject": "no-issue-anywhere", "detail": "nothing"},
    ]
    bridge_row = {"n": 546, "event": "dispatch", "subject": "#85",
                  "detail": "Ruling n=545 ref row:545"}
    rows = cases + [bridge_row]
    for row in cases:
        before = RUNNER.resolve_ruling_issue(row, rows, pred)[0]
        after_issues = RUNNER.resolve_ruling_issues(row, rows, pred)[0]
        if before is not None:
            assert before in after_issues, (row.get("n"), before, after_issues)
        else:
            assert after_issues == [] or row.get("refs"), (row.get("n"), after_issues)

def test_probe_a_FOREIGN_ruling_does_not_rule_this_board() -> None:
    """THE DEFECT ITSELF, driven through the leg that reported it (#592, ruling n=4551).

    `subject` is a bare `#NNN` with NO repo qualifier, so `n=433` -- a ruling whose own
    detail reads `gh issue view 366 --repo leshchenko1979/opencrabs` -- satisfied
    `agent-factories#366` for 26 DAYS while that item had never been ruled in this repo's
    life, and the leg printed `problems: 0` over it.

    THE DISCRIMINATOR IS THE WRITER'S TYPED `repo` REF, never a read over the detail:
    `n=433` and `n=4279` are structurally identical prose and one is foreign while the
    other is ours. Case 4 is the probe that proves it -- it is this factory's own ruling on
    #561 that merely QUOTES a command against `inferhub-watch#550`, and it must stay GREEN
    because a detail is evidence and never a declaration.

    THE FOUR CASES THE RULING REQUIRES, in ONE fixture so they cannot drift apart:
      1. a ruling declaring a FOREIGN repo does NOT rule a same-numbered local item;
      2. a ruling declaring NO repo still rules -- all 702 historical rows must not move;
      3. a ruling declaring THIS factory's repo still rules;
      4. `n=4279` still rules, and the SAME detail carrying a foreign ref stops ruling.

    `own_repo` is injected rather than read: a probe must not depend on this checkout's
    remote, and the leg's own docstring says so.
    """
    pred = RUNNER.load_predicate()
    own = "leshchenko1979/agent-factories"
    # The intake row is DATED, or the leg excuses it as NOT JUDGED and every case below
    # reads `owed == []` for the same reason -- the vacuity trap the #585 probe names.
    stamp = _plus(_CLOSE_TS, -7.0)

    def read(ruling: dict, issue_no: int = 366):
        issues = [_issue_with_comments(issue_no, "OPEN", "## An item.\n")]
        rows = [ruling,
                {"n": 9001, "event": "intake", "subject": f"#{issue_no}",
                 "detail": "intake", "ts": stamp}]
        leg = RUNNER.board_unruled_leg(
            issues, rows, read_at=_plus(_CLOSE_TS, 1.0), predicate=pred, own_repo=own
        )
        return leg, issues

    # CASE 1 -- THE DEFECT. A foreign ruling, structurally identical to a local one.
    foreign = {"n": 433, "event": "ruling", "subject": "#366",
               "detail": "ruled; measured with `gh issue view 366 --repo "
                         "leshchenko1979/opencrabs`",
               "refs": [{"repo": "leshchenko1979/opencrabs"}]}
    leg, issues = read(foreign)
    cov = leg["coverage"]
    assert cov["items_owed_ruling"] == 1, cov["owed"]
    assert cov["owed"] == [366], cov["owed"]
    # AND THE EXCLUSION IS NAMED, not merely counted: an instrument that removes a row from
    # a population must say which row and which repo, or the silent drop is the same defect
    # turned around.
    assert cov["rulings_foreign"] == 1, cov
    assert cov["foreign_rows"] == [
        {"ruling_n": 433, "repo": "leshchenko1979/opencrabs",
         "repos": ["leshchenko1979/opencrabs"], "subject": "#366", "own_repo": own}
    ], cov["foreign_rows"]
    # PRINTED, in the report, with the row number and the repo.
    text = RUNNER.render([leg], [], slug=own, read_at="probe", issues=issues)
    assert "FOREIGN ruling row n=433" in text, text
    assert "leshchenko1979/opencrabs" in text, text
    assert "1 FOREIGN repo row(s) EXCLUDED" in text, text

    # CASE 2 -- ABSENT MEANS THIS FACTORY. The same row with no `repo` ref rules, which is
    # what keeps all 702 historical ruling rows meaning what they meant with no backfill.
    bare = dict(foreign)
    bare.pop("refs")
    leg, _ = read(bare)
    assert leg["coverage"]["items_owed_ruling"] == 0, leg["coverage"]["owed"]
    assert leg["coverage"]["rulings_foreign"] == 0, leg["coverage"]

    # CASE 3 -- THIS FACTORY'S OWN REPO still resolves.
    ours = dict(foreign)
    ours["refs"] = [{"repo": own}]
    leg, _ = read(ours)
    assert leg["coverage"]["items_owed_ruling"] == 0, leg["coverage"]["owed"]
    assert leg["coverage"]["rulings_foreign"] == 0, leg["coverage"]

    # CASE 4 -- n=4279, the case a text heuristic breaks. This factory's own ruling on #561
    # QUOTES a command against inferhub-watch#550; the quote is evidence, not a declaration.
    quoting = {"n": 4279, "event": "ruling", "subject": "#561",
               "detail": "ruled here; the measurement used `gh issue view 550 --repo "
                         "leshchenko1979/inferhub-watch`"}
    leg, _ = read(quoting, issue_no=561)
    assert leg["coverage"]["items_owed_ruling"] == 0, leg["coverage"]["owed"]
    assert leg["coverage"]["rulings_foreign"] == 0, leg["coverage"]
    # NON-VACUITY OF CASE 4: the SAME detail with a foreign `repo` ref stops ruling, so the
    # green above is the ref's doing and not a leg that stopped judging prose.
    quoting_foreign = dict(quoting)
    quoting_foreign["refs"] = [{"repo": "leshchenko1979/inferhub-watch"}]
    leg, _ = read(quoting_foreign, issue_no=561)
    assert leg["coverage"]["items_owed_ruling"] == 1, leg["coverage"]["owed"]
    assert leg["coverage"]["owed"] == [561], leg["coverage"]["owed"]
    assert leg["coverage"]["foreign_rows"][0]["repo"] == "leshchenko1979/inferhub-watch"

def test_the_census_EXCLUDES_a_declared_standing_item_and_NEVER_a_REFUSED_one() -> None:
    """#607 shape 2, ruling n=4674: the standing exclusion lives in the POPULATION BUILDER.

    THE DEFECT THIS CLOSES. `#586` taught ONE leg (`undispatched-ruling`) to excuse a
    permanent-state item and closed on that leg, so the item it excused stayed OWED in the two
    legs that build their population elsewhere -- `stall-census` and, through the census's own
    grouping, `driverless-lane`. The fix travelled exactly as far as the report did. A lane
    reading "1 owed" every morning for an item that will never be worked is being told to
    re-dispatch finished work, which is the failure the excuse existed to stop.

    THE SHAPE (2a/2b/2c) IS ASSERTED AS THREE SEPARATE PROPERTIES, because each one can fail
    alone and each one fails silently:

    * 2a -- a VALID declaration is an EXCLUSION applied in the population builder, so every
      leg that reads the census inherits it. Asserted directly, and then asserted AGAIN
      through `driverless_leg`, which is the leg that would otherwise still red.
    * 2b -- a REFUSED declaration is NEVER an exclusion. The unit stays OWED and the refusal
      prints ON its line. Half of the pair is worse than neither: an exclusion without the
      refusal turns a visible red into an invisible false excuse.
    * 2c -- every round prints `judged + excluded = before`, so "0 problems" stays
      distinguishable from "empty population" and a receipt taken before this change is
      comparable to one taken after it by ARITHMETIC rather than by eye.

    THE FIXTURE IS #581's REAL SHAPE: a `ruling` row that resolves to it, a dispatch row that
    was never claimed, and nothing else. #931 is the neighbour that must stay OWED in every
    arm -- without it, a leg that excluded the whole population would satisfy every
    exclusion assertion here.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(581, "OPEN"), _issue(931, "OPEN")]
    rows = [
        _stall_row(4472, "ruling", "#581", 1, now=now),      # the ruling that declares it
        _stall_row(1, "dispatch", "#581", 5, now=now),       # dispatched, never claimed
        _stall_row(2, "dispatch", "#931", 5, now=now),       # the neighbour, never declared
    ]
    declared = {581: {"issue": 581, "ruling_row": 4472, "reason": "permanent state, probe"}}

    # ARM 1 -- 2a, the POSITIVE half: a valid declaration EXCLUDES #581 and leaves #931 OWED.
    leg = RUNNER.stall_census_leg(
        issues, rows, read_at=read_at,
        predicate=RUNNER.load_predicate(), standing=declared)
    cov = leg["coverage"]
    named = "\n".join(leg["problems"])
    assert "OWED #581" not in named, (
        f"a VALID standing declaration must exclude the unit -- it is permanent state, not "
        f"work, so no dispatch is owed and none will ever be\n{named}"
    )
    assert "OWED #931" in named, (
        f"the undeclared neighbour must STILL be owed, or a leg that excluded the whole "
        f"population would satisfy the assertion above\n{named}"
    )
    assert cov["standing_declared"] == 1, cov
    assert cov["units_standing"] == 1, cov
    assert cov["standing_refused"] == 0, cov
    standing_notes = "\n".join(cov["standing"])
    assert "STANDING #581" in standing_notes, cov["standing"]
    assert "EXCLUDED" in standing_notes and "#607" in standing_notes, cov["standing"]

    # ARM 1b -- 2c, the IDENTITY: judged + excluded == before, on THIS arm.
    assert (cov["population_before"], cov["population_judged"], cov["excluded"]) == (2, 1, 1), cov
    assert cov["population_judged"] + cov["excluded"] == cov["population_before"], cov

    # ARM 2 -- THE NEGATIVE CONTROL: the SAME rows with NO declaration read #581 OWED. Without
    # this arm, a leg that excused everything unconditionally would pass ARM 1.
    bare = RUNNER.stall_census_leg(
        issues, rows, read_at=read_at,
        predicate=RUNNER.load_predicate(), standing={})
    bare_cov = bare["coverage"]
    assert "OWED #581" in "\n".join(bare["problems"]), bare["problems"]
    assert bare_cov["units_standing"] == 0, bare_cov
    assert bare_cov["standing_declared"] == 0, bare_cov
    assert (bare_cov["population_before"], bare_cov["population_judged"],
            bare_cov["excluded"]) == (2, 2, 0), bare_cov
    assert bare_cov["population_judged"] + bare_cov["excluded"] == bare_cov["population_before"]

    # ARM 3 -- 2b, REFUSED because the row does not exist: the entry is stale or mistyped. The
    # unit stays OWED and the refusal prints ON its line, so a broken declaration is never
    # indistinguishable from no declaration.
    stale = {581: {"issue": 581, "ruling_row": 9999, "reason": "permanent state, probe"}}
    leg = RUNNER.stall_census_leg(
        issues, rows, read_at=read_at,
        predicate=RUNNER.load_predicate(), standing=stale)
    cov = leg["coverage"]
    named = "\n".join(leg["problems"])
    assert "OWED #581" in named, (
        f"a REFUSED entry excuses NOTHING -- the unit it names stays in the population\n{named}"
    )
    assert "REFUSED" in named and "does not exist" in named, named
    assert "a refused entry excuses nothing (#607)" in named, named
    assert cov["units_standing"] == 0, cov
    assert cov["standing_refused"] == 1, cov
    assert cov["population_judged"] + cov["excluded"] == cov["population_before"], cov

    # ARM 4 -- 2b, REFUSED because the row names ANOTHER unit's ruling. An entry that names
    # another unit's ruling excuses nothing, and the refusal says which unit it resolves to.
    other = {581: {"issue": 581, "ruling_row": 4473, "reason": "permanent state, probe"}}
    rows_other = rows + [_stall_row(4473, "ruling", "#999", 1, now=now)]
    leg = RUNNER.stall_census_leg(
        issues, rows_other, read_at=read_at,
        predicate=RUNNER.load_predicate(), standing=other)
    named = "\n".join(leg["problems"])
    assert "OWED #581" in named, named
    assert "resolves to #999" in named, named
    assert leg["coverage"]["standing_refused"] == 1, leg["coverage"]

    # ARM 5 -- 2a THROUGH THE LEG THAT WOULD OTHERWISE STILL RED: `driverless_leg` reads the
    # census's OWN grouping, so the exclusion is inherited rather than re-taught. This is the
    # assertion the whole shape exists for -- before #607 this leg red on the same item.
    driven_census = RUNNER.stall_census_leg(
        issues, rows, read_at=read_at,
        predicate=RUNNER.load_predicate(), standing=declared)
    dl = RUNNER.driverless_leg(
        driven_census, goals=_goal_store(), read_at=read_at,
        lane_names_fn=lambda: {}, lane_activity_fn=lambda: _activity_store())
    dl_cov = dl["coverage"]
    assert dl_cov["units_standing"] == driven_census["coverage"]["units_standing"], dl_cov
    assert dl_cov["population_before"] == driven_census["coverage"]["population_before"], dl_cov
    assert dl_cov["population_judged"] == driven_census["coverage"]["population_judged"], dl_cov
    assert dl_cov["excluded"] == driven_census["coverage"]["excluded"], dl_cov
    slots = driven_census["coverage"]["owed_by_lane"]
    assert all("#581" not in slot["units"] for slot in slots), (
        f"the excluded unit must not reach the grouping `driverless_leg` reads, or the "
        f"exclusion was applied after the population was already handed on\n{slots}"
    )

    # ARM 6 -- THE RENDER, through the REAL `main()`: a leg whose numbers are right and whose
    # report still reads `1 owed` with no identity line would have fixed nothing a lane can
    # see. The declaration is INJECTED, so no probe reads the live one.
    rc, out, _err = _run(issues, rows, standing_items=declared)
    assert "population identity: judged 1 + excluded 1 = 2" in out, out
    assert "1 declared, 1 OWED unit(s) excused and EXCLUDED from the owed total" in out, out
    assert "STANDING #581" in out, out
    assert "declaration READ" in out, out
    assert rc == 1, f"the undeclared neighbour is still OWED, got rc={rc}\n{out}"

    # ARM 6b -- 2c THROUGH THE INHERITING LEG'S OWN RENDER. (c) says EVERY inheriting leg
    # PRINTS the identity, and carrying the numbers in a coverage dict is not printing them:
    # `driverless-lane` is the leg that red on this item before the fix, so a reader comparing
    # its block to the census's must find the same arithmetic there or see two populations with
    # no way to reconcile them. The `(inherited from the census; #607)` suffix is what makes
    # this assertion about THIS leg and not the census line ARM 6 already matched.
    assert "population identity: judged 1 + excluded 1 = 2 (inherited from the census; #607)" in out, (
        f"every INHERITING leg must print the identity, not only carry it\n{out}"
    )

    # ... and a REFUSED entry renders as loudly as an excused one, with its reason ON the owed
    # line -- the pair is what stops a broken declaration from reading as a clean one.
    _rc, out, _err = _run(issues, rows, standing_items=stale)
    assert "0 OWED unit(s) excused and EXCLUDED" in out, out
    assert "1 REFUSED (each still OWED)" in out, out
    assert "OWED #581" in out, out
    assert "does not exist" in out, out

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
