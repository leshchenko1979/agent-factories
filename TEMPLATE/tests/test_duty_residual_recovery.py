"""Gate: a RECOVERY receipt is a valid PAIRING, never a latency OBSERVATION (#617).

The defect this gate guards, measured 2026-11-05 on `factory-hq-pacemaker`: `n=4781` was
written to make a round that HAD been completed visible to the duty-receipt leg, because its
true completion (`n=4652`) went out under subject `#253` and the stem predicate cannot pair
that. The row did its job and paid for it: `duty_residual_for` takes the MAXIMUM fire-to-
receipt latency over every round, so the row's own timestamp entered as an 80.33 h
observation, lifting the job's measured max from 18.97 h to 80.33 h, its derived residual
from 75.87 h to 321.31 h, and — because 321.31 h then excused BOTH of the job's rounds as
inside its own window — left the job with no round to judge at all.

The two questions are different and only one of them is answered here:

  * "was this round receipted?"   -> the PAIRING, and a recovery row must still satisfy it
  * "how prompt is this lane?"    -> the OBSERVATIONS, and a recovery row must never enter it

Every arm below drives the leg's own injections (`fires`, `ledger_rows`, `predicate`,
`margin_for`, `exclude_round`), so no verdict here is decided by this box's files. The pair
that matters is `test_a_declared_recovery_...` against `test_the_same_row_undeclared_...`:
they differ in ONE substring of ONE detail, so the window is a function of the declaration
rather than of the fixture.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import pytest

from patrol_fixtures import RUNNER  # noqa: F401  (import side effect: loads the runner)

P = RUNNER

# --- the incident's own numbers, as fixture constants ----------------------
# The fire that opened the round, and the true completion's instant. The gap between them
# (3.65 h) is the real latency and is NOT what the recovery row carries.
_FIRE = "2026-11-02T09:50:35Z"
_TRUE_COMPLETION = "2026-11-02T13:29:21Z"
_RECOVERY_TS = "2026-11-05T18:10:17Z"      # n=4781's own stamp -- the 80.33 h artefact
_JOB_ID = "8e6522bb-1fa1-4eed-a2e5-de705f8ffa10"
_STEM = "hq-cycle"

# A prior, ordinary round so the job has a real observation to measure against. Its latency
# (2 h) is the control's measured max, and it must survive BOTH arms unchanged.
_PRIOR_FIRE = "2026-10-26T09:50:00Z"
_PRIOR_RECEIPT = "2026-10-26T11:50:00Z"

# The declaration lives in the job's PROMPT, read by `declared_receipt_disposition` -- a
# `receipt_subject` KEY on the row is read by nothing, which is the shape of #618.
_JOB = {"name": "factory-hq-pacemaker", "id": _JOB_ID, "stem": _STEM,
        "last_run_at": _FIRE,
        "prompt": f"Run the weekly HQ cycle.\nreceipt_subject: {_STEM}\n"}

_FIRES = [
    {"job_id": _JOB_ID, "started_at": _PRIOR_FIRE, "status": "success"},
    {"job_id": _JOB_ID, "started_at": _FIRE, "status": "success"},
]

# The recovery declaration, verbatim from `n=4781`'s own detail tail: the canonical trailer
# the leg reads is `observation=recovery`, and the sentence beside it is the pre-convention
# form. Both are here because the row carries both.
_RECOVERY_CLAUSE = "RECOVERY record, not a latency observation."
_TRAILER = "observation=recovery"

_PRIOR_ROW = {
    "n": 1, "ts": _PRIOR_RECEIPT, "event": "run", "actor": "hq",
    "subject": "hq-cycle-2026-10-26",
    "detail": f"HQ cycle 2026-10-26: the round's own completion record. duty=completed",
}


def _recovery_row(*, declared: bool) -> dict:
    """`n=4781` in miniature: the SAME row, with or without its recovery declaration."""
    tail = f" {_TRAILER}" if declared else ""
    return {
        "n": 2, "ts": _RECOVERY_TS, "event": "run", "actor": "hq",
        "subject": "hq-cycle-2026-11-02T09",
        "detail": (
            "Receipt for the 2026-11-02 cycle: RECOVERED, not re-earned. The round's true "
            f"completion is dated {_TRUE_COMPLETION}. This row exists only to make that "
            f"completion visible to the leg. {_RECOVERY_CLAUSE if declared else ''} "
            f"duty=completed{tail}"
        ),
    }


def _residual(rows, *, exclude_round=None, fires=None, job=None):
    return P.duty_residual_for(
        job or _JOB, _STEM,
        fires=fires if fires is not None else _FIRES,
        ledger_rows=rows,
        exclude_round=exclude_round,
    )


# --- the arms --------------------------------------------------------------

def test_a_declared_recovery_is_excluded_from_the_observations():
    """The fix: the row pairs its round and never enters the latency list."""
    rec = _residual([_PRIOR_ROW, _recovery_row(declared=True)])
    assert rec["observations_excluded_recovery"] == 1, rec
    # The window rests on the ONE ordinary round, so its max is that round's 2 h -- NOT the
    # 80.33 h the recovery row's own stamp would have contributed.
    assert rec["measured_max_secs"] == pytest.approx(7200.0, abs=1.0), rec
    assert rec["measured_rounds"] == 1, rec


def test_the_same_row_undeclared_lifts_the_window_the_incident_measured():
    """The control's negative half: strip ONE substring and the defect reproduces.

    This is the live shape HQ measured -- the recovery row entering as an observation and
    taking the window from 75.87 h to 321.31 h. The arm exists so the fix cannot be satisfied
    by a fixture that simply never carried the row.
    """
    rec = _residual([_PRIOR_ROW, _recovery_row(declared=False)])
    assert rec["observations_excluded_recovery"] == 0, rec
    expected = 80.33 * 3600.0  # 2026-11-02T09:50:35Z -> 2026-11-05T18:10:17Z
    assert rec["measured_max_secs"] == pytest.approx(expected, rel=0.002), rec
    assert rec["measured_max_secs"] > 70000.0, rec


def test_the_exclusion_ratio_matches_the_incident():
    """Both arms on the SAME fixture: the exclusion is the only difference in the window."""
    with_decl = _residual([_PRIOR_ROW, _recovery_row(declared=True)])
    without = _residual([_PRIOR_ROW, _recovery_row(declared=False)])
    ratio = without["residual_secs"] / with_decl["residual_secs"]
    # 321.31 h / 75.87 h = 4.235x on the live box; the margin cancels in the ratio, so the
    # fixture's ratio is the latency ratio itself.
    assert ratio == pytest.approx(without["measured_max_secs"] / 7200.0, rel=0.01), ratio
    assert ratio > 4.0, ratio


def test_the_recovery_row_still_pairs_its_round():
    """The constraint HQ stated: REMAIN a valid pairing. The leg must still see the round.

    `duty_residual_for` is not the pairing reader -- `duty_receipt_leg` is -- so this arm
    proves the exclusion did not move the pairing predicate: the same row that is dropped
    from the latencies is still a candidate when the leg asks "was this round receipted?".
    """
    rows = [_PRIOR_ROW, _recovery_row(declared=True)]
    leg = P.duty_receipt_leg(
        [_JOB], ["ops"], [], ["factory-"], rows,
        read_at="2026-11-05T20:00:00Z", fires=_FIRES,
    )
    cov = leg["coverage"]
    judged = [j for j in cov.get("duties_judged", []) if j.get("name") == "factory-hq-pacemaker"]
    assert judged, cov.get("duties_judged")
    round_ = judged[0]
    assert round_["round"] == "2026-11-02", round_
    # The pairing found the recovery row, and it is not an unanswered fire.
    assert round_["receipts"] >= 1, round_
    assert round_["fires_unanswered"] == 0, round_


def test_a_round_scoped_exemption_is_excused_counted_and_excluded():
    """The second exclusion surface: a factory may declare ONE round owed nothing.

    Distinct from a job exemption (which removes the job) and from a recovery receipt
    (which removes one observation): this removes the round from BOTH the judgement and the
    residual, and it must be COUNTED so a short window is never read as a prompt lane.
    """
    seen = []

    def exclude(job, round_date, instant):
        seen.append(round_date)
        return "declared owed nothing in the fixture" if round_date == "2026-11-02" else None

    rec = _residual([_PRIOR_ROW, _recovery_row(declared=False)], exclude_round=exclude)
    assert seen, "the exclusion was never consulted"
    assert rec["rounds_excluded_excuse"] == 1, rec
    assert rec["excluded_rounds"] and rec["excluded_rounds"][0]["round"] == "2026-11-02", rec
    # Excluded BEFORE the candidate scan, so the 80.33 h never became a candidate at all.
    assert rec["measured_max_secs"] == pytest.approx(7200.0, abs=1.0), rec


def test_the_round_exemption_reader_returns_the_declared_reason(tmp_path):
    """The store reader: a round-scoped entry yields `{(job, round): reason}`."""
    import json
    store = tmp_path / "docs"
    store.mkdir()
    (store / "duty-receipt-exemptions.json").write_text(json.dumps({
        "exempt": [
            {"job": "factory-hq-pacemaker", "round": "2026-11-02",
             "reason": "the lane was mid-repair and declared it"},
        ]
    }), encoding="utf-8")
    mapping, problem = P.receipt_round_exemptions(store / "duty-receipt-exemptions.json")
    assert problem is None, problem
    assert mapping == {("factory-hq-pacemaker", "2026-11-02"):
                       "the lane was mid-repair and declared it"}, mapping


def test_a_job_scoped_entry_never_leaks_into_the_round_map(tmp_path):
    """The two halves are separate surfaces: a job exemption must not excuse a round."""
    import json
    store = tmp_path / "docs"
    store.mkdir()
    (store / "duty-receipt-exemptions.json").write_text(json.dumps({
        "exempt": [
            {"job": "factory-hq-pacemaker", "reason": "job-level, no round named"},
        ]
    }), encoding="utf-8")
    mapping, problem = P.receipt_round_exemptions(store / "duty-receipt-exemptions.json")
    assert problem is None, problem
    assert mapping == {}, mapping


def test_the_census_prints_zeros_on_a_clean_job():
    """An exclusion counter reads an explicit 0, never an absent key."""
    rec = _residual([_PRIOR_ROW])
    for key in ("rounds_excluded_excuse", "observations_excluded_recovery", "excluded_rounds"):
        assert key in rec, (key, sorted(rec))
    assert rec["rounds_excluded_excuse"] == 0, rec
    assert rec["observations_excluded_recovery"] == 0, rec
    assert rec["excluded_rounds"] == [], rec


def test_the_leg_reports_the_exclusions_in_its_coverage():
    """The leg-level census: a reader of `--json` sees what was dropped, not just a window."""
    rows = [_PRIOR_ROW, _recovery_row(declared=True)]
    leg = P.duty_receipt_leg(
        [_JOB], ["ops"], [], ["factory-"], rows,
        read_at="2026-11-05T20:00:00Z", fires=_FIRES,
    )
    cov = leg["coverage"]
    assert cov.get("observations_excluded_recovery") == 1, cov.get("observations_excluded_recovery")
    assert cov.get("round_exemptions_declared") == 0, cov.get("round_exemptions_declared")


# --- the mutant: without the exclusion the gate must bite -------------------

def test_MUTANT_without_the_exclusion_the_incident_reads_CLEAN(monkeypatch):
    """Neuter the exclusion and the incident's own figure must reappear.

    A gate that cannot fail is decoration. This arm removes the recovery filter and asserts
    the defect reproduces on the SAME fixture, so the green above is attributable to the
    exclusion and to nothing else.
    """
    monkeypatch.setattr(P, "declares_recovery_observation", lambda detail, predicate=None: False)
    rec = _residual([_PRIOR_ROW, _recovery_row(declared=True)])
    assert rec["observations_excluded_recovery"] == 0, rec
    assert rec["measured_max_secs"] > 70000.0, rec
    assert rec["measured_max_secs"] == pytest.approx(80.33 * 3600.0, rel=0.002), rec


if __name__ == "__main__":
    # PYTEST form: these are module-level arms, so a bare run would exit 0 having asserted
    # NOTHING — a gate whose only exits are barred (entry-point equivalence, #612 review).
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
