"""Gate: the claim-standing leg — a CLAIM is not a receipt (#625).

THE CLASS THIS GATE GUARDS. A unit can carry a `claim` row, still be OPEN on the board, and
never receive a `close` row. No leg measured it, and the reason is structural: every
adjacent leg excludes a claimed unit BY ITS OWN DEFINITION (`stall-census` = dispatched and
NEVER claimed; `driverless-lane` = an UNCLAIMED backlog; `board-closed` = CLOSED items), so
their union is not a coverage of the class (#116 shape). Measured at 2026-11-07T06:09:08Z
over 4,849 rows: 11 units stood in it, oldest 37.29 d, median 16.10 d — NET OF the two
claims their owner withdrew by release, which is the #626 half of the predicate.

WHAT THE ARMS PROVE, one per acceptance criterion:

* past the threshold -> a PROBLEM naming the unit, the claimer, the row and the age;
* a `close` row -> silent, and the unit leaves the population entirely;
* a `release` naming the claim row -> silent, and the unit is COUNTED in the printed
  `units_released_off` bucket rather than silently subtracted (#626 criterion 1);
* `claim -> release -> claim` -> STANDING again on the second claim (#626 criterion 2);
* `claim -> claim -> release(first)` -> still standing on the second, because a release
  terminates exactly the row it names and nothing else (#626 criterion 3);
* inside the threshold -> silent, but STILL NAMED in the printed population, because a leg
  that prints only its problems cannot distinguish "nothing stands" from "nothing looked";
* a claimed unit CLOSED on the board -> outside this population, COUNTED not dropped (the
  missing close row there is `board-closed`'s direction, not this leg's);
* an unreadable claim instant -> NOT JUDGED with its reason, never read as a short standing
  (#271);
* an EMPTY population still reports its population, so a green is never indistinguishable
  from a leg that examined nothing (#116);
* the threshold is DECLARED and its basis carries the measurement it rests on (criterion 4);
* a re-claim restarts the clock, so a unit re-claimed yesterday is not reported as standing
  for a fortnight;
* the MUTANT ARM: the same fixture with the age comparison disarmed stops reddening while
  the population is unchanged, which is what proves the comparison is what bites rather
  than the unit's mere presence in the population;
* the RELEASE MUTANT ARM (#626 criterion 4): the same fixture with the release reader
  neutered REGAINS the released unit and reddens again at the same age, which is what
  proves the release read — not a fixture artefact — is what removed it.
"""

from __future__ import annotations

import re

import pytest

from patrol_fixtures import RUNNER

READ_AT = "2026-11-07T00:00:00Z"

# Chosen relative to READ_AT so every age in this file is exact arithmetic, not a
# remembered number.
PAST = "2026-10-28T00:00:00Z"    # 10.00 d before READ_AT
INSIDE = "2026-11-05T00:00:00Z"  #  2.00 d before READ_AT


def _issue(number, state="open"):
    """One board item, in the only two fields this leg reads."""
    return {"number": number, "state": state}


def _claim(number, ts, *, actor="worker", n=100):
    return {"n": n, "ts": ts, "event": "claim", "actor": actor, "subject": f"#{number}"}


def _close(number, ts="2026-11-06T00:00:00Z", *, n=101):
    return {"n": n, "ts": ts, "event": "close", "actor": "worker", "subject": f"#{number}"}


def _release(number, claim_row, *, ts="2026-11-06T12:00:00Z", n=102, actor="triage"):
    """A `release` row withdrawing the claim at `claim_row` (#626).

    The terminated claim travels as a ref of kind `row` — the instrument's own vehicle
    (`docs/instruments/ledger.md:264`) — never as prose, because prose is not a predicate.
    """
    return {
        "n": n,
        "ts": ts,
        "event": "release",
        "actor": actor,
        "subject": f"#{number}",
        "refs": [{"row": str(claim_row)}],
    }

def _run(issues, rows, **kw):
    return RUNNER.claim_standing_leg(issues, rows, read_at=READ_AT, **kw)


def test_a_claim_past_the_threshold_is_a_problem():
    """Criterion 1, first half: claimed, open, unclosed, past the threshold -> red."""
    leg = _run([_issue(600)], [_claim(600, PAST, actor="worker", n=4719)])
    assert leg["status"] == "ASSERTED", leg["status"]
    assert len(leg["problems"]) == 1, leg["problems"]
    line = leg["problems"][0]
    assert "#600" in line and "STANDING" in line, line
    # The line must carry what a reader needs to act: the claimer, the row, the age.
    assert "worker" in line and "n=4719" in line and "10.00 d" in line, line
    # And it must say it does not re-arm, because a standing claim may be legitimate work.
    assert "re-arms" in line, line
    assert leg["coverage"]["units_past_threshold"] == 1


def test_a_close_row_clears_it_and_removes_it_from_the_population():
    """Criterion 1, second half: the same unit with a close row reads clean."""
    leg = _run([_issue(600)], [_claim(600, PAST), _close(600)])
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["units_in_population"] == 0, cov
    assert cov["units_with_close_row"] == 1, cov
    assert cov["population"] == [], cov["population"]


def test_inside_the_threshold_is_clean_but_still_named():
    """The population prints EVERY member, not only the problems (#116, criterion 6)."""
    leg = _run([_issue(600)], [_claim(600, INSIDE)])
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["units_in_population"] == 1, cov
    assert cov["units_past_threshold"] == 0, cov
    assert len(cov["population"]) == 1, cov["population"]
    assert "#600" in cov["population"][0] and "WITHIN" in cov["population"][0], cov["population"]


def test_a_closed_board_item_is_outside_the_population():
    """A claimed unit closed on the board is `board-closed`'s direction, not this leg's.

    Counted, never dropped: an exclusion that is not counted is indistinguishable from a
    miss, and judging it here would be a second predicate for one question.
    """
    leg = _run([_issue(600, state="closed")], [_claim(600, PAST)])
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["units_off_board"] == 1, cov
    assert cov["units_in_population"] == 0, cov
    assert cov["population"] == [], cov["population"]


def test_an_unreadable_claim_instant_is_not_judged():
    """#271: an unread clock must never read as a SHORT standing."""
    leg = _run([_issue(600)], [_claim(600, "not-an-instant")])
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["instants_unparsed"] == 1, cov
    assert cov["units_in_population"] == 0, cov
    assert len(leg["excused"]) == 1 and "#600" in leg["excused"][0], leg["excused"]
    assert "NOT JUDGED" in leg["excused"][0], leg["excused"][0]


def test_an_empty_population_reports_its_population():
    """A green over an examined-nothing read is not a verdict (#116).

    The zero must be VISIBLE as a zero: `units_in_population: 0` beside `population: []`
    says the leg read the ledger and found nothing standing, which is a different statement
    from a leg that never ran.
    """
    leg = _run([], [])
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["units_in_population"] == 0, cov
    assert cov["units_claimed"] == 0, cov
    assert cov["population"] == [], cov["population"]
    assert cov["claim_rows_examined"] == 0, cov


def test_the_threshold_is_declared_with_its_basis():
    """Criterion 4: DECLARED, and the declaration prints on every run.

    A threshold without its basis is a number a reader must take on trust, and the basis is
    what says whether it is a policy or a measurement. The value is read from the module's
    own declaration, so a leg that silently hardcoded a different number inside its
    comparison would fail this arm.
    """
    leg = _run([_issue(600)], [_claim(600, PAST)])
    cov = leg["coverage"]
    assert cov["threshold_days"] == RUNNER.CLAIM_STANDING_THRESHOLD_DAYS, cov
    assert cov["threshold_days"] == 7.0, cov
    basis = cov["threshold_basis"]
    assert isinstance(basis, str) and len(basis) > 40, basis
    # The basis must carry the MEASUREMENT it rests on, not merely an opinion: the
    # population it was measured over, the statistic, and the figure itself. Deliberately
    # NOT pinned to a literal day count -- that figure is re-measured every time the live
    # population moves, and an arm pinned to it would red on a correct re-measure.
    assert "measured population" in basis, basis
    assert "median" in basis, basis
    assert re.search(r"median standing is \d+\.\d+ d", basis), basis


def test_mutant_arm_the_age_comparison_is_what_bites():
    """THE MUTANT ARM (criterion 2): neuter the comparison, the fixture stops reddening.

    This is the arm that makes the others mean something. The fixture is IDENTICAL in both
    halves — same board item, same claim row, same read instant — and the only thing that
    changes is whether the age comparison can bite. If the reddening in the armed half came
    from the unit merely being in the population (or from any other fact of the fixture),
    the disarmed half would redden too; it does not, and the population stays populated in
    both, which isolates the comparison as the cause.
    """
    issues = [_issue(600)]
    rows = [_claim(600, PAST)]

    armed = _run(issues, rows)
    assert len(armed["problems"]) == 1, armed["problems"]
    assert armed["coverage"]["units_in_population"] == 1, armed["coverage"]

    # Disarmed: a threshold no age can reach, so the comparison cannot fire. The unit is
    # still IN the population, so what changed is the comparison and nothing else.
    disarmed = _run(issues, rows, threshold_days=1e9)
    assert disarmed["problems"] == [], disarmed["problems"]
    assert disarmed["coverage"]["units_in_population"] == 1, disarmed["coverage"]
    assert disarmed["coverage"]["units_past_threshold"] == 0, disarmed["coverage"]


def test_the_newest_claim_dates_the_standing_not_the_earliest():
    """A re-claim restarts the clock: the age runs from the CURRENT taking.

    An age measured from the earliest claim would report a unit re-claimed yesterday as
    standing for a fortnight — the exact false finding that teaches lanes to ignore red.
    """
    leg = _run(
        [_issue(600)],
        [_claim(600, PAST, n=100), _claim(600, INSIDE, n=200)],
    )
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["units_in_population"] == 1, cov
    # The population line names the NEWEST claim row, which is the one that dates it.
    assert "n=200" in cov["population"][0], cov["population"]
    assert "WITHIN" in cov["population"][0], cov["population"]


def test_a_claim_row_naming_no_work_unit_is_counted_not_judged():
    """A descriptive-stem claim is legal (a wave, a sweep): not a unit, never a finding.

    Counted, so a leg that silently ignored the whole ledger could not pass this gate.
    """
    leg = _run(
        [_issue(600)],
        [
            {"n": 5, "ts": PAST, "event": "claim", "actor": "worker", "subject": "wave-7"},
            _claim(600, PAST),
        ],
    )
    cov = leg["coverage"]
    assert cov["claim_rows_not_naming_a_unit"] == 1, cov
    assert cov["claim_rows_examined"] == 1, cov
    assert len(leg["problems"]) == 1, leg["problems"]


def test_a_released_claim_is_not_standing():
    """Criterion 1 (#626): a claim withdrawn by a release is terminal, not standing.

    Before #626 this leg read only `claim`/`close`, so every release a lane wrote added a
    PERMANENT false positive — and the remedy that produced the release was the act the leg
    punished. The unit must leave the population AND be COUNTED in its own bucket: an
    exclusion that is not printed is indistinguishable from a miss (#116).
    """
    leg = _run([_issue(600)], [_claim(600, PAST, n=100), _release(600, 100)])
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["units_released_off"] == 1, cov
    assert cov["release_rows_examined"] == 1, cov
    assert cov["units_in_population"] == 0, cov
    assert cov["population"] == [], cov["population"]

def test_claim_release_claim_stands_again():
    """Criterion 2 (#626): `claim -> release -> claim` is STANDING on the second claim.

    A lane that withdrew a claim and later re-took the unit is standing on the CURRENT
    taking, so the clock restarts at the second claim. A unit-level filter (rather than a
    per-row one) would read this as withdrawn and hide live work.
    """
    rows = [
        _claim(600, PAST, n=100),
        _release(600, 100),
        _claim(600, INSIDE, n=200),
    ]
    leg = _run([_issue(600)], rows)
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["units_released_off"] == 0, cov
    assert cov["units_in_population"] == 1, cov
    assert "n=200" in cov["population"][0], cov["population"]
    assert "WITHIN" in cov["population"][0], cov["population"]

def test_a_release_of_the_first_claim_leaves_the_second_standing():
    """Criterion 3 (#626): a release terminates the row it NAMES, and nothing else.

    `ledger.md:286`: a claim is the only row a release can terminate. So releasing the
    FIRST of two claims leaves the second standing — the leg must date the unit from the
    newest claim that is still LIVE, never from the newest claim full stop (which would be
    the released one) and never from the earliest.
    """
    rows = [
        _claim(600, PAST, n=100),
        _claim(600, INSIDE, n=200),
        _release(600, 100),
    ]
    leg = _run([_issue(600)], rows)
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["units_released_off"] == 0, cov
    assert cov["units_in_population"] == 1, cov
    assert "n=200" in cov["population"][0], cov["population"]
    assert "WITHIN" in cov["population"][0], cov["population"]

def test_mutant_arm_the_release_read_is_what_removes_the_unit():
    """THE MUTANT ARM (criterion 4, #626): neuter the release read, the unit comes back.

    This is what makes the other three arms mean something. The fixture is IDENTICAL in
    both halves — same board item, same claim row, same release row, same read instant — and
    the only thing that changes is whether `_released_claim_rows` is allowed to read. If the
    unit left the population for any reason other than the release read (a fixture artefact,
    a close row, the age comparison), the neutered half would still exclude it; it does not,
    and it reddens again at the same age, which isolates the read as the cause.
    """
    from unittest import mock

    issues = [_issue(600)]
    rows = [_claim(600, PAST, n=100), _release(600, 100)]

    armed = _run(issues, rows)
    assert armed["problems"] == [], armed["problems"]
    assert armed["coverage"]["units_released_off"] == 1, armed["coverage"]
    assert armed["coverage"]["units_in_population"] == 0, armed["coverage"]

    # Neutered: the reader returns nothing, so no claim is ever seen as withdrawn.
    with mock.patch.object(RUNNER, "_released_claim_rows", lambda _rows: {}):
        neutered = _run(issues, rows)

    assert neutered["coverage"]["units_released_off"] == 0, neutered["coverage"]
    assert neutered["coverage"]["units_in_population"] == 1, neutered["coverage"]
    assert len(neutered["problems"]) == 1, neutered["problems"]
    assert "#600" in neutered["problems"][0], neutered["problems"]


# --- #626: the PAIR, and the drain evidence ---------------------------------
#
# The two halves of #626 are ONE predicate, and proving them apart is how the defect got
# in: excluding a released unit from claim-standing alone turns a false RED into a false
# CLEAN, because `stall-census` built its `claimed` set from ANY claim row and so dropped
# the very units a release freed. Measured on the live board at 2026-11-07T06:28Z:
# #561/#563 carry a LIVE never-claimed WORKER dispatch (n=4280/n=4314, 12.21 d) that
# Triage's intake-and-routing release had made invisible to every leg.

WORKER = "U-WORKER"
_DISPATCH_TS = "2026-10-26T00:00:00Z"   # 12.00 d before READ_AT — past the census's 1.0 d

def _dispatch(number, ts=_DISPATCH_TS, *, n=1, session=WORKER):
    return {"n": n, "ts": ts, "event": "dispatch", "actor": "hq",
            "subject": f"#{number}", "detail": "probe", "refs": [{"session": session}]}

def _census(issues, rows):
    return RUNNER.stall_census_leg(
        issues, rows, read_at=READ_AT, lane_names_fn=lambda: {WORKER: "Worker"}
    )

def test_the_pair_a_released_claim_is_EXCLUDED_here_and_OWED_there():
    """Criterion 5 (#626): the two halves must be proven TOGETHER.

    One fixture, both legs. A released claim must leave the claim-standing population AND
    leave the unit in the census's OWED population with its addressee intact. A gate that
    asserts only the first half is the false-CLEAN gate #626 describes: the unit would be
    named by no leg at all, which is strictly worse than the false RED it replaced.
    """
    issues = [_issue(561)]
    rows = [
        _dispatch(561, n=1),
        _claim(561, PAST, n=2),                      # 10.00 d — Triage's routing claim
        _release(561, 2, ts="2026-11-02T18:46:56Z", n=3),   # ... withdrawn
    ]
    standing = _run(issues, rows)
    assert standing["problems"] == [], (
        f"the released claim must not be counted as standing (#626 criterion 1)\n"
        f"{standing['problems']}"
    )
    assert standing["coverage"]["units_released_off"] == 1, standing["coverage"]
    assert standing["coverage"]["units_in_population"] == 0, standing["coverage"]

    census = _census(issues, rows)
    named = "\n".join(census["problems"])
    assert "OWED #561" in named, (
        f"the released claim must NOT drop #561 from the OWED population — a live "
        f"never-claimed dispatch stands on it (#626 criterion 4)\n{named}"
    )
    assert "ADDRESSED to Worker" in named, (
        f"the OWED line must keep the addressee the release did not touch\n{named}"
    )
    cov = census["coverage"]
    assert cov["released_claim_units"] == ["#561"], cov
    assert cov["released_claim_units_count"] == 1, cov

def test_mutant_arm_the_census_half_is_what_keeps_the_unit_owed():
    """Criterion 5's MUTANT ARM (#626): disarm the census half and the pair must fail.

    Neuter the one predicate both halves read, and the released claim becomes a claim
    again: `claimed` takes the unit back, the census drops it from OWED, and the unit
    disappears from the patrol entirely — the exact false CLEAN #626 was filed against.
    Without this arm the pair test would pass on a tree where the census half was never
    wired, because a green that never triggers the comparison proves nothing.
    """
    issues = [_issue(561)]
    rows = [
        _dispatch(561, n=1),
        _claim(561, PAST, n=2),
        _release(561, 2, ts="2026-11-02T18:46:56Z", n=3),
    ]
    assert "OWED #561" in "\n".join(_census(issues, rows)["problems"])

    # Patched by hand rather than by a pytest fixture: this gate carries BOTH `def test_*`
    # and a `__main__` harness, and `main()` calls every check with no arguments -- so a
    # fixture-taking arm would be silently unrunnable from the form the audit invokes.
    real = RUNNER._released_claim_rows
    RUNNER._released_claim_rows = lambda _rows: {}
    try:
        neutered = _census(issues, rows)
    finally:
        RUNNER._released_claim_rows = real
    assert "OWED #561" not in "\n".join(neutered["problems"]), (
        "the mutant must reproduce the defect: with the release read disarmed the unit "
        "returns to `claimed` and the census goes silent"
    )
    assert neutered["coverage"]["released_claim_units"] == [], neutered["coverage"]

def test_a_released_claim_is_not_drain_evidence_for_a_sibling():
    """Criterion 6 (#626): the same rows feed the drain evidence, so the same filter binds.

    `claims_by_unit` is a SECOND reading of the claim rows (#465), used to decide whether a
    lane is DRAINING a queue. A released claim read there would say the lane took work it
    had already handed back — the release act becoming evidence of activity it never did.
    """
    issues = [_issue(561), _issue(562)]
    rows = [
        _dispatch(561, n=1),                       # OWED, 12.00 d
        _dispatch(562, n=2),                       # the sibling ...
        _claim(562, "2026-11-06T12:00:00Z", n=3),  # ... claimed 0.50 d ago ...
        _release(562, 3, ts="2026-11-06T18:00:00Z", n=4),   # ... and withdrawn again
    ]
    leg = _census(issues, rows)
    named = "\n".join(leg["problems"])
    assert "OWED #561" in named, named
    assert "claimed a sibling of the same standing set" not in named, (
        f"a WITHDRAWN claim is not drain evidence: the lane did not keep that work\n{named}"
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
        print(f"claim-standing gate FAILED: {len(failures)} check(s)")
        return 1
    print(f"claim-standing gate passed: {len(checks)} check(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
