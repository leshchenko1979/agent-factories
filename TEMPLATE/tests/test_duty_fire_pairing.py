"""Gate: a fire is paired with the receipt that ANSWERS it, never its round's newest (#621).

The defect this gate guards, measured at HEAD on `factory-triage-patrol`: `duty_residual_for`
iterated FIRES but matched receipts at ROUND (YYYY-MM-DD) granularity, then took the round's
NEWEST row as the answer to every fire that date. A stem+date subject is shared by every fire
of the day, so the day's earliest fire was charged with the day's latest receipt:

  * fire `2026-09-26T00:00:35Z` -> charged `n=1225` at `22:36:23Z` = **22.60 h**
  * its own answer `n=1143` at `00:10:35Z`                        =  **0.17 h**

The measured max over the job fell from 22.60 h to 12.17 h once pairing was honest (144
observations either way), which is a 1.86x magnitude error and NOT a manufactured alarm: the
job's residual stays at 48.67 h against a 6 h cadence. The counterpart control is
`factory-questions-gc`, measured 12.08 h / 3 observations under BOTH pairings -- its lateness
is genuine, so an arm here asserts the fix leaves it alone.

THE TWO QUESTIONS ARE NOT COLLAPSED, and this is the half a naive fix gets wrong:

  * "was this round receipted, and does the duty stand?" -> `duty_receipt_leg`, where #217's
    NEWEST-GOVERNS rule decides the verdict (a round may fail at T and complete at T+n)
  * "how prompt is this lane?"                           -> `duty_residual_for`, where the
    FIRST receipt at or after the fire is the answer, because a supersession cannot move an
    instant that has already happened

Every arm drives the leg's own injections (`fires`, `ledger_rows`), so no verdict here is
decided by this box's files. The pair that matters is `test_the_fire_is_charged_its_own_...`
against `test_MUTANT_...`: the mutant restores the round-newest rule and the incident's own
22.60 h must reappear, so the green is attributable to the pairing and nothing else.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import pytest

from patrol_fixtures import RUNNER  # noqa: F401  (import side effect: loads the runner)

P = RUNNER

# --- the incident's own numbers, as fixture constants ----------------------
_STEM = "patrol-verify"
_ROUND = "2026-09-26"
_JOB_ID = "0b6f4f7e-6210-4c11-9a3e-621062106210"

# The two fires of the measured day. `_FIRE_EARLY` is the one the defect mis-charged.
_FIRE_EARLY = "2026-09-26T00:00:35Z"
_FIRE_LATE = "2026-09-26T12:00:00Z"

# Its OWN answer, ten minutes later -- the true latency is 0.1667 h.
_OWN_ANSWER_TS = "2026-09-26T00:10:35Z"
# The round's newest receipt, 22.6 h after the early fire and the answer to NOTHING here.
_ROUND_NEWEST_TS = "2026-09-26T22:36:23Z"
# The late fire's own answer.
_LATE_ANSWER_TS = "2026-09-26T12:10:00Z"

_OWN_ANSWER_SECS = 600.0        # 00:00:35 -> 00:10:35 = exactly 10 min
_ROUND_NEWEST_SECS = 22.6 * 3600.0

_JOB = {"name": "factory-triage-patrol", "id": _JOB_ID, "stem": _STEM,
        "last_run_at": _FIRE_EARLY,
        "prompt": f"Run the patrol.\nreceipt_subject: {_STEM}\n"}

_FIRES = [
    {"job_id": _JOB_ID, "started_at": _FIRE_EARLY, "status": "success"},
    {"job_id": _JOB_ID, "started_at": _FIRE_LATE, "status": "success"},
]


def _row(n, ts, hour_token, *, duty="completed", extra=""):
    """One receipt of the round: subject carries the round AND the hour token."""
    return {
        "n": n, "ts": ts, "event": "run", "actor": "triage",
        "subject": f"{_STEM}-{_ROUND}{hour_token}",
        "detail": f"Patrol round receipt. duty={duty}{extra}",
    }


def _receipts():
    """The three rows of the measured day, in ledger order."""
    return [
        _row(1143, _OWN_ANSWER_TS, "T00"),
        _row(1200, _LATE_ANSWER_TS, "T12"),
        _row(1225, _ROUND_NEWEST_TS, "T22"),
    ]


def _residual(rows, *, fires=None, job=None):
    return P.duty_residual_for(
        job or _JOB, _STEM,
        fires=fires if fires is not None else _FIRES,
        ledger_rows=rows,
    )


# --- the incident ----------------------------------------------------------

def test_the_fire_is_charged_its_own_answer_not_the_rounds_newest():
    """The early fire is answered in ten minutes and must be charged ten minutes.

    Under the defect this read 22.60 h: the round's newest row was taken as the answer to
    a fire it never answered.
    """
    rec = _residual(_receipts())
    assert rec["measured_max_secs"] == pytest.approx(_OWN_ANSWER_SECS, rel=1e-6), rec
    assert rec["measured_max_secs"] < _ROUND_NEWEST_SECS / 10.0, rec


def test_every_fire_of_the_round_keeps_its_own_observation():
    """Both fires of the day are measured, and neither is answered by the other's receipt.

    A fix that collapsed the round to one observation would pass the arm above by accident,
    so the population is asserted beside the value.
    """
    rec = _residual(_receipts())
    assert rec["measured_rounds"] == 2, rec
    assert rec["fires_read"] == 2, rec


def test_the_control_job_is_unchanged_by_the_pairing():
    """`factory-questions-gc` measured 12.08 h / 3 obs under BOTH pairings: 1.00x.

    Its lateness is genuine, so a fix that made it read clean would be wrong. This fixture
    is the same shape at a different scale: one fire, one receipt 12 h later, and no other
    row of the round that could answer it first.
    """
    job = {"name": "factory-questions-gc", "id": "gc-621", "stem": "questions-gc",
           "last_run_at": "2026-09-26T00:00:00Z",
           "prompt": "Run the gc.\nreceipt_subject: questions-gc\n"}
    rows = [{"n": 7, "ts": "2026-09-26T12:04:48Z", "event": "run", "actor": "triage",
             "subject": "questions-gc-2026-09-26", "detail": "gc round. duty=completed"}]
    rec = P.duty_residual_for(
        job, "questions-gc",
        fires=[{"job_id": "gc-621", "started_at": "2026-09-26T00:00:00Z", "status": "success"}],
        ledger_rows=rows,
    )
    assert rec["measured_max_secs"] == pytest.approx(12.08 * 3600.0, rel=0.002), rec
    assert rec["measured_rounds"] == 1, rec


# --- the invariant ---------------------------------------------------------

def test_a_receipt_may_not_answer_a_fire_it_follows():
    """The pinned invariant: a receipt answers a fire it FOLLOWS, never one that precedes it.

    One fire at noon, and the round's only receipt is the ten-past-midnight row written
    BEFORE it. That row cannot answer this fire, so the job has no observation at all --
    and takes the stated default rather than a negative latency or a borrowed receipt.
    """
    rows = [_row(1143, _OWN_ANSWER_TS, "T00")]
    rec = P.duty_residual_for(
        _JOB, _STEM,
        fires=[{"job_id": _JOB_ID, "started_at": _FIRE_LATE, "status": "success"}],
        ledger_rows=rows,
    )
    assert rec["measured_rounds"] == 0, rec
    assert rec["measured_max_secs"] is None, rec
    assert rec["basis"] == "default", rec


def test_a_supersession_inside_the_pairing_does_not_move_the_instant():
    """Two rows share ONE subject: the first instant is when the duty was answered.

    This is where a naive reading of #217 would go wrong. Newest-governs decides whether
    the duty STANDS (in `duty_receipt_leg`); it cannot retroactively move the moment the
    first answer was written. A fix that grouped by subject and took the group's newest
    would read 0.67 h here instead of 0.17 h.
    """
    rows = [
        _row(1143, _OWN_ANSWER_TS, "T00"),
        _row(1150, "2026-09-26T00:40:35Z", "T00", duty="failed", extra=" superseded"),
    ]
    rec = _residual(rows, fires=[{"job_id": _JOB_ID, "started_at": _FIRE_EARLY,
                                  "status": "success"}])
    assert rec["measured_max_secs"] == pytest.approx(_OWN_ANSWER_SECS, rel=1e-6), rec


def test_the_verdict_path_still_takes_the_newest_declaration():
    """#217 is NOT weakened: the leg still counts a failed-then-completed round as superseded.

    The two questions live in different functions, and this arm exists so that a future
    change to the LATENCY pairing cannot quietly delete the VERDICT rule.
    """
    rows = [
        _row(1143, _OWN_ANSWER_TS, "T00", duty="failed"),
        _row(1150, "2026-09-26T00:40:35Z", "T00", duty="completed"),
    ]
    leg = P.duty_receipt_leg(
        [_JOB], ["ops"], [], ["factory-"], rows,
        read_at="2026-09-26T23:00:00Z", fires=_FIRES,
        scope_fn=lambda repo: (P.reader_parse_ts("2026-09-25T07:01:07Z"),
                               "2026-09-25T07:01:07Z", ""),
        exemptions_fn=lambda: ({}, None),
        round_exemptions_fn=lambda: ({}, None),
    )
    cov = leg["coverage"]
    assert cov.get("rounds_superseded", 0) >= 1, cov


# --- the mutant: without the pairing the incident must reappear -------------

def test_MUTANT_without_the_pairing_the_incident_reappears(monkeypatch):
    """Restore the round-newest rule and the 22.60 h charge must come back.

    A gate that cannot fail is decoration. This arm swaps the pairing for the exact pre-#621
    shape -- newest row of the round, for every fire of the round -- and asserts the defect's
    own figure on the SAME fixture, so the greens above are attributable to the pairing.
    """
    def _round_newest(candidates, instant, parse):
        if not candidates:
            return None
        return max(candidates, key=lambda r: str(r.get("ts") or ""))

    monkeypatch.setattr(P, "receipt_answering_fire", _round_newest)
    rec = _residual(_receipts())
    assert rec["measured_max_secs"] == pytest.approx(_ROUND_NEWEST_SECS, rel=0.002), rec
    assert rec["measured_max_secs"] > _OWN_ANSWER_SECS * 100.0, rec


if __name__ == "__main__":
    # PYTEST form: these are module-level arms, so a bare run would exit 0 having asserted
    # NOTHING -- a gate whose only exits are barred (entry-point equivalence, #612 review).
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
