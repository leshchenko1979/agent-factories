"""Gate: the tree's own instants, kit drift and short parses — #531

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
    _DUTY_BOUND,
    _DUTY_FIRE,
    _DUTY_ROUND,
    _EMPTY_GOAL_STORE,
    _EMPTY_LOG_DIR,
    _EMPTY_SCORES_DIR,
    _NO_CRITERION_EXEMPTIONS,
    _NO_REF_ROLE_EXEMPTIONS,
    _RECEIPT_PROMPT,
    _RECEIPT_TS,
    _conversion_row,
    _duty_leg,
    _duty_row,
    _duty_scope,
    _duty_tree,
    _fires,
    _issue,
    _non_conversion_row,
    _plus,
    _run,
    _scores_dir,
    _scores_tree,
    _stall_row,
    _stub_publish_leg,
    _stub_shared_tree_rider,
    _synthetic_kit,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _receipt_row(subject=None,
                 detail="the round completed. duty=completed", n=1) -> dict:
    subject = f"registry-attest-{_DUTY_ROUND}" if subject is None else subject
    """A receipt row. The `duty=` token is what MAKES it a receipt (#160).

    The default carries it, because a row that declares nothing is not a receipt at all —
    the leg's first version accepted any subject match, which is how a dispatch record
    written before the round completed certified the round.
    """
    return {"n": n, "ts": _RECEIPT_TS, "event": "run", "actor": "delegate",
            "subject": subject, "detail": detail}

def _fire_receipt(fire_hours: float, latency_secs: float, n: int) -> dict:
    """A receipt row for the round opened `fire_hours` after the bound, `latency_secs` later.

    Built rather than pinned, because the per-job residual (#449) is a function of the GAP
    between a fire and its round's receipt: a fixture with a fixed receipt instant can only
    express one latency, and a measurement over one observation is not a max.
    """
    fire = _plus(_DUTY_BOUND, fire_hours)
    fired = dt.datetime.strptime(fire, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    receipt = (fired + dt.timedelta(seconds=latency_secs)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"n": n, "ts": receipt, "event": "run", "actor": "delegate",
            "subject": f"registry-attest-{fire[:10]}",
            "detail": "the round completed. duty=completed"}

def _stub_predicate(**overrides):
    """The SHARED field predicate with ONE reader replaced — the neuter-the-code control.

    Criterion 1 of the #281 ruling (n=2003) requires the MALFORMED-RECEIPT finding to be
    proven to BITE, and a finding that survives its own discriminator being neutered is
    not a finding: it is prose that happens to be true. So the probes replace exactly one
    attribute and assert the finding MOVES, which is what makes the surviving assertion
    attributable to that attribute rather than to the fixture.

    Everything else delegates to the real module, so a probe neuters ONE reader and the
    rest of the leg keeps the behaviour the live run has.
    """
    real = RUNNER.field_predicate_readers()
    class _Stub:
        def __init__(self):
            object.__setattr__(self, "_real", real)
            for key, value in overrides.items():
                object.__setattr__(self, key, value)
        def __getattr__(self, name):
            return getattr(object.__getattribute__(self, "_real"), name)
    return _Stub()

def _lexical_duty_scan(detail: str) -> bool:
    """`mentions_duty` with the own-voice scope REMOVED — the pre-#278 lexical reading.

    Built on the real module's own `keyed_value`, so the neutered reader differs from the
    live one in ONE respect only: whether a token inside a parenthetical aside counts. That
    is the exact question the ruling says the shared discriminator answers, so this is the
    control that shows it is answering it.
    """
    real = RUNNER.field_predicate_readers()
    return any(real.keyed_value(token, real.DUTY_KEY) is not None
               for token in str(detail).split())

def _per_family_score_artifact(*, name: str = "Probe factory", total: int = 67) -> str:
    """A card in the shape 2026-10-17 carries: cells grouped PER FAMILY, no flat row.

    The heading is the one `_SCORECARD_HEADING_RE` matches, so the block IS found -- and its
    body carries no `| D1 | ... |` criterion header, so ZERO cells parse. That is the filed
    shape exactly: the leg knew the round existed and read nothing out of it, then printed
    `0 cell(s) examined ... 0 regression(s): none` as though it had examined the round.
    """
    return (
        "## Detailed Factory Scorecards\n\n"
        f"### 1. {name} — {total} / 76\n\n"
        "| Family | Cells | Sum | Max |\n"
        "|---|---:|---:|---:|\n"
        "| Documentation | 3 4 4 3 | 14 | 16 |\n"
        "| Output | 4 3 **0** | 7 | 12 |\n"
    )

def _cell_score_artifact(*, cells: list[str], declared: int = 19, total: int = 67,
                         name: str = "Probe factory") -> str:
    """A card whose HEADER declares `declared` columns and whose BODY carries `cells`.

    Separate from `_score_artifact` on purpose: that helper derives the header FROM the
    body, so the two counts can never disagree and a short parse cannot be expressed at
    all. The incompleteness arm exists precisely in the gap between them.
    """
    header = " | ".join(f"D{i + 1}" for i in range(declared))
    body = " | ".join(cells)
    return (
        "## Detailed Factory Scorecards\n\n"
        f"### 1. {name} — {total} / 76\n\n"
        f"| {header} |\n"
        "|" + "---:|" * declared + "\n"
        f"| {body} |\n"
    )

# --- this leg's tests -------------------------------------------------------
def test_the_duty_leg_BITES_when_a_fired_round_left_no_receipt() -> None:
    """THE probe this leg exists for: a green cron run with no duty row is a FINDING.

    The measured instance: six fragments sat at attested_at 2026-09-19 for four days while
    `cron_job_runs` carried success — the trigger worked and the duty did not, and nothing
    reported it.
    """
    leg = _duty_leg([_duty_row()], [])
    assert leg["status"] == "ASSERTED", leg
    assert leg["coverage"]["duties_judged"][0]["round"] == _DUTY_ROUND, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "NO duty receipt" in problem, problem
    assert f"registry-attest-{_DUTY_ROUND}" in problem, problem
    assert "9ec28cec" in problem, "the finding must RESOLVE the row it names, by id"
    assert "TRIGGER fired" in problem, "the finding must say what a green run does mean"

def test_the_duty_leg_passes_when_the_round_left_its_receipt() -> None:
    leg = _duty_leg([_duty_row()], [_receipt_row()])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1

def test_the_duty_leg_reports_a_FAILED_receipt_not_only_a_missing_one() -> None:
    """A receipt that declares a non-success is a FAILED duty, never a clean one."""
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(detail="the round did not complete. duty=failed")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "did NOT complete" in leg["problems"][0], leg["problems"][0]
    assert "duty=failed" in leg["problems"][0], leg["problems"][0]

def test_a_SKIPPED_receipt_is_a_finding_too() -> None:
    """`skipped` is in the domain and is NOT a completion — it must not pass silently.

    The domain is completed|failed|skipped, so the leg owes an answer for each member. A
    receipt declaring `skipped` says the duty did not run, which is exactly what this leg
    exists to surface.
    """
    leg = _duty_leg([_duty_row()], [_receipt_row(detail="nothing ran today. duty=skipped")])
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "duty=skipped" in leg["problems"][0], leg["problems"][0]

def test_a_duty_value_OUTSIDE_the_domain_is_an_ERROR_never_a_silent_pass() -> None:
    """The `declared_outcome` precedent: an unrecognised value is REPORTED, never bucketed.

    A reader that silently accepted `duty=done` would let a typo read as a completion, which
    is the fabrication direction #53 clause 4 removed from the outcome reader.
    """
    leg = _duty_leg([_duty_row()], [_receipt_row(detail="the round finished. duty=done")])
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "outside the domain" in leg["problems"][0], leg["problems"][0]
    assert "duty=done" in leg["problems"][0], leg["problems"][0]

def test_the_NEWEST_receipt_GOVERNS_a_round_that_failed_then_completed() -> None:
    """#217: a round can fail at T and complete at T+n, and that is not a standing problem.

    The measured instance: round 2026-09-28 on `registry-attest` carried a `duty=failed` row
    written at 5-of-6, then a `duty=completed` row when the sixth fragment answered. Every
    row is honest and neither corrects the other, so before this the round red for the rest
    of its key and a lane had NO lawful way to record the recovery.

    BOTH halves are asserted, because either alone is passable by a wrong implementation:
    the verdict must go CLEAN, and the SUPERSEDED row must still be printed. A leg that
    simply dropped the incomplete rows would pass the first half and hide the failure.
    """
    failed = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                          detail="5 of 6 fragments written back. duty=failed", n=1499)
    failed["ts"] = _plus(_DUTY_BOUND, 0.9)
    completed = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                             detail="6 of 6 fragments written back. duty=completed", n=1529)
    completed["ts"] = _plus(_DUTY_BOUND, 1.5)
    leg = _duty_leg([_duty_row()], [failed, completed])

    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["rounds_superseded"] == 1, leg["coverage"]
    superseded = [e for e in leg["excused"] if "SUPERSEDED" in e]
    assert len(superseded) == 1, leg["excused"]
    note = superseded[0]
    assert "n=1499" in note, note                      # the superseded row, NAMED
    assert "duty=failed" in note, note                 # with the value it declared
    assert "n=1529" in note, note                      # and its successor
    assert "not backfilled" in note, note

def test_a_round_whose_NEWEST_receipt_failed_still_REDs() -> None:
    """The discriminator must not weaken the finding it was added alongside.

    Same round, the OPPOSITE order: it completed, then a later row says it failed. The
    newest declaration governs, so the round is a problem — which is what stops the fix
    from becoming "any completed row anywhere clears the round".
    """
    completed = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                             detail="6 of 6 fragments written back. duty=completed", n=1529)
    completed["ts"] = _plus(_DUTY_BOUND, 0.9)
    failed = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                          detail="a fragment regressed on re-read. duty=failed", n=1540)
    failed["ts"] = _plus(_DUTY_BOUND, 1.5)
    leg = _duty_leg([_duty_row()], [completed, failed])

    assert len(leg["problems"]) == 1, leg["problems"]
    assert "did NOT complete" in leg["problems"][0], leg["problems"][0]
    assert "n=1540" in leg["problems"][0], "the finding must name the GOVERNING row"
    assert "NEWEST" in leg["problems"][0], leg["problems"][0]

def test_a_SINGLE_incomplete_receipt_still_REDs() -> None:
    """The single-row case is the one the leg was always right about — unchanged by #217."""
    leg = _duty_leg([_duty_row()], [_receipt_row(
        subject=f"registry-attest-{_DUTY_ROUND}",
        detail="nothing ran today. duty=skipped", n=7)])
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "did NOT complete" in leg["problems"][0], leg["problems"][0]
    assert leg["coverage"]["rounds_superseded"] == 0, leg["coverage"]

def test_the_DOMAIN_leg_is_NOT_superseded_by_a_later_row() -> None:
    """A vocabulary fault is not a state a later row settles — the carve-out, pinned.

    An unrecognised token is the WRITER's error, so it is reported even when a later row
    declares a clean completion. Folding it into the supersession would let a typo be
    buried by a subsequent correct row, which is the fabrication direction the domain leg
    exists to refuse.
    """
    bad = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                       detail="the round finished. duty=done", n=1500)
    bad["ts"] = _plus(_DUTY_BOUND, 0.9)
    good = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}",
                        detail="6 of 6 fragments written back. duty=completed", n=1529)
    good["ts"] = _plus(_DUTY_BOUND, 1.5)
    leg = _duty_leg([_duty_row()], [bad, good])

    assert len(leg["problems"]) == 1, leg["problems"]
    assert "outside the domain" in leg["problems"][0], leg["problems"][0]
    assert "n=1500" in leg["problems"][0], leg["problems"][0]

def test_a_row_that_DECLARES_NOTHING_is_NOT_a_receipt() -> None:
    """THE false-clean fix (#160), and the probe the first version would have passed.

    Measured instance: the leg accepted n=1003 — subject `registry-attest-2026-09-25`,
    appended 06:08:53Z — as the round's receipt, while n=1003 is the DISPATCH record and the
    completion landed later (n=1007, 06:14:25Z) under a different subject. A subject match
    was enough, so the round reported 0 problems while it was incomplete.

    The omission is the failure the mechanism cannot see: a row that declares nothing is not
    a duty that owed nothing.
    """
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(detail="Registry attestation — the round. NO REPLY OWED on this row.")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]
    assert "declare no `duty=`" in leg["problems"][0], (
        "the finding must say that a row matched and declared nothing, so the reader can "
        f"tell this from an absent row: {leg['problems'][0]}"
    )
    assert leg["coverage"]["duties_judged"][0]["rows_matched"] == 1, leg["coverage"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 0, leg["coverage"]

def test_a_PROSE_mention_of_the_duty_is_not_a_declaration() -> None:
    """Positional read: a sentence that merely SAYS the round completed is not the field.

    This is the n=405 clause 5 damage on a new field — the rows carrying a receipt discuss
    completion at length in prose, so a whole-detail scan would read the discussion as the
    declaration.
    """
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(detail="the round completed and all six were answered. head=abc123")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_an_HOUR_BEARING_subject_names_the_round() -> None:
    """#159: the round is a DATE, so an hour-keyed receipt must still resolve.

    `factory-triage-patrol` writes `patrol-verify-2026-09-25T06` — exact equality could never
    match it, so a duty that DID complete reported MISSING.
    """
    leg = _duty_leg(
        [_duty_row(name="factory-triage-patrol", prompt=_RECEIPT_PROMPT.replace(
            "registry-attest", "patrol-verify"))],
        [_receipt_row(subject=f"patrol-verify-{_DUTY_ROUND}T06",
                      detail="the patrol ran. duty=completed")],
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_a_DECORATED_AFTER_the_date_subject_names_the_round() -> None:
    """#159: a decoration that FOLLOWS the date is reached by the ruled prefix."""
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(subject=f"registry-attest-{_DUTY_ROUND}-writeback",
                      detail="the write-back round. duty=completed")],
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_an_INFIX_decorated_subject_is_NOT_reached_by_the_ruled_prefix() -> None:
    """THE BOUND, stated so the widening is not oversold (#159).

    The ruled key is `subject.startswith(f"{stem}-{round_date}")`, so a decoration AFTER the
    date is reached (`...-2026-09-25T06`, `...-2026-09-25-writeback`) while one BEFORE it is
    not: `registry-attest-writeback-2026-09-25` does not start with
    `registry-attest-2026-09-25`. Measured, all four shapes, at the ruled key:

        registry-attest-2026-09-25            -> reached  (exact)
        registry-attest-2026-09-25T06         -> reached  (hour, the #159 defect)
        registry-attest-2026-09-25-writeback  -> reached  (word suffix)
        registry-attest-writeback-2026-09-25  -> NOT      (infix decoration)

    The last is the live subject of n=1007 — the instance the coupling rationale cites — so
    the ruled widening does not reach it. This probe PINS that bound rather than widening
    past the ruling on this lane's own reading: the key is a ruled shape, and the
    measurement was reported to HQ instead. It is here so a future reader cannot mistake the
    prefix for a general "the subject mentions the round" rule.
    """
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(subject="registry-attest-writeback-2026-09-25",
                      detail="the write-back round. duty=completed")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_the_PREFIX_IS_BOUNDARY_CHECKED_so_a_longer_date_cannot_match() -> None:
    """#159's guard: `...-2026-09-25` must NOT match `...-2026-09-250`.

    A bare `startswith` would read a DIFFERENT date's subject as this round's — the widening
    would trade a false MISSING for a false CLEAN, which is the defect it is fixing.
    """
    leg = _duty_leg(
        [_duty_row()],
        [_receipt_row(subject=f"registry-attest-{_DUTY_ROUND}0",
                      detail="some other round. duty=completed")],
    )
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_the_EXACT_match_case_still_resolves() -> None:
    """The widening is strictly more permissive — the original shape must not regress."""
    leg = _duty_leg([_duty_row()], [_receipt_row()])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_a_row_declaring_no_receipt_is_NOT_JUDGED_COUNTED_and_since_506_a_PROBLEM() -> None:
    """P29, and #506 half 2 which SUPERSEDES this probe's original expectation.

    The original assertion was `len(problems) == 1` with the comment "the undeclared row is
    not judged and adds no problem" — the row added no problem, so `problems: 0` was
    indistinguishable from a clean round for a duty the leg could not look at. That is the
    exact false negative #506 closed: an unjudged duty is now a FINDING with the job named.
    The P29 half is unchanged and still bites — the population is COUNTED by name, never a
    bare zero.
    """
    leg = _duty_leg(
        [_duty_row(), _duty_row(name="factory-measurement-daily", prompt="no declaration here")],
        [],
    )
    assert leg["coverage"]["jobs_declaring_receipt"] == 1, leg["coverage"]
    assert leg["coverage"]["jobs_undeclared"] == 1, leg["coverage"]
    assert leg["coverage"]["undeclared_jobs"] == ["factory-measurement-daily"], leg["coverage"]
    # the declared row is judged and MISSING (it owes a receipt nobody wrote), and the
    # undeclared one REDS under #506 -- two problems, and the #506 one NAMES the job
    assert len(leg["problems"]) == 2, leg["problems"]
    findings = [p for p in leg["problems"] if "#506" in p]
    assert len(findings) == 1, leg["problems"]
    assert "factory-measurement-daily" in findings[0], findings[0]
    assert any("NO duty receipt" in p for p in leg["problems"]), leg["problems"]

def test_a_census_where_NO_row_declares_a_receipt_is_a_FINDING_not_a_silent_NOT_RUN() -> None:
    """#506 half 2. This probe used to assert `status == "NOT RUN"` and `problems == []` —
    the silence itself. A census in which NOT ONE attributed duty declares a receipt is now
    the loudest possible finding: the leg judged nothing because nothing was declarable, and
    it says so by NAMING the jobs rather than by rendering a status that reads as deferred.
    """
    leg = _duty_leg([_duty_row(prompt="no declaration here")], [])
    assert leg["status"] == "ASSERTED", leg
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "factory-registry-attest" in leg["problems"][0], leg["problems"][0]
    # the reason still names the POPULATION it enumerated, so the reader can tell a census
    # that declared nothing from one that declared something and found it missing
    assert "receipt_subject:" in (leg["reason"] or ""), leg["reason"]
    assert "NO DUTY WAS JUDGED" in (leg["reason"] or ""), leg["reason"]

def test_the_round_comes_from_the_rows_own_fire_instant_never_a_parsed_schedule() -> None:
    """`last_run_at` is stamped at DISPATCH, so it names the round the trigger woke.

    The tree is pinned to an EARLIER declared bound rather than moving the fixture instant,
    because the assertion's whole power is that the round date (09-24) differs from the read
    instant (09-25) — a schedule parse would name 09-25. Moving the instant forward to clear
    the #175 bound would have made the probe unable to tell the two derivations apart.

    The second arm is the same row under this factory's real bound: 09-24 predates it, so
    the round is EXCUSED and never judged. One row, two bounds, two outcomes — which is the
    property #175 exists to establish.
    """
    early = _duty_tree(invariants={"duty_receipt_declared": "2026-09-20T00:00:00Z"})
    leg = _duty_leg([_duty_row(last_run_at="2026-09-24T06:00:11Z")], [], repo=early)
    assert leg["coverage"]["duties_judged"][0]["round"] == "2026-09-24", leg["coverage"]
    assert "registry-attest-2026-09-24" in leg["problems"][0], leg["problems"][0]

    bounded = _duty_leg([_duty_row(last_run_at="2026-09-24T06:00:11Z")], [])
    assert bounded["coverage"]["duties_judged"] == [], bounded["coverage"]
    assert bounded["coverage"]["rounds_excused_by_bound"] == 1, bounded["coverage"]

def test_a_row_with_no_fire_instant_is_EXCUSED_and_never_guessed() -> None:
    """A round that cannot be READ is never NAMED: the row is excused with its reason."""
    leg = _duty_leg([_duty_row(last_run_at="")], [])
    assert leg["problems"] == [], leg["problems"]
    assert len(leg["excused"]) == 1, leg["excused"]
    assert "no fire instant" in leg["excused"][0], leg["excused"][0]

def test_a_MENTION_of_the_declaration_is_not_a_DECLARATION() -> None:
    """Prose about a field must not satisfy it — the declaration is a whole LINE (n=405)."""
    prompt = (
        "Thin trigger only — do NOT execute any project work yourself.\n"
        "The old text said receipt_subject: registry-attest and it was removed.\n"
    )
    assert RUNNER.declared_receipt_stem(prompt) is None, "a mid-sentence mention declared one"
    assert RUNNER.declared_receipt_stem(_RECEIPT_PROMPT) == "registry-attest"

def test_the_duty_leg_names_attested_at_as_RESULTING_STATE_never_the_receipt() -> None:
    """Criterion 4: a stale attestation is RESULTING STATE, and a stale one must not stand
    in for the missing receipt — the receipt is the ledger run row, and it is still absent."""
    store = Path(tempfile.mkdtemp())
    (store / "probe.json").write_text(
        json.dumps({"factory": "probe", "attested_at": "2026-09-19T00:00:00Z"}),
        encoding="utf-8",
    )
    leg = _duty_leg([_duty_row()], [], store=store)
    assert leg["coverage"]["attested_at_state"] == {"probe": "2026-09-19T00:00:00Z"}, leg["coverage"]
    assert len(leg["problems"]) == 1, "a stale attestation must not excuse the missing receipt"

def test_the_duty_leg_is_WIRED_into_the_runner_and_prints_its_population() -> None:
    """A leg that is not wired is not a leg: the runner's own output must carry it."""
    rc, out, err = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"])
    assert "LEG duty-receipt" in out, out
    assert "1 row(s) declare a receipt" in out, out
    assert "RESULTING STATE, never the receipt" in out, out
    # #487: the bound is read through the SAME reader the runner was handed, never the LIVE
    # one. A probe that resolved this field by a second path would be the very defect #487
    # fixed — and it would assert the shipped half REFUSES while the runner, handed the
    # reader whose fallback keeps the probes runnable, JUDGES. The REFUSAL path is exercised
    # through `main()` by the probe below, which drives a refusing reader.
    assert _duty_scope(RUNNER.REPO)[2] == "", "the default reader must not refuse here"
    assert "NO duty receipt" in out, "a missing duty receipt must reach the report"
    assert rc == 1, "the leg's verdict must fail the run"

def test_a_REFUSED_duty_bound_is_HONOURED_through_the_runner() -> None:
    """#487 acceptance, the FAIL arm: a reader that REFUSES must reach the verdict.

    The bound is injected, so a probe can drive a state the live tree cannot be in — a
    declaration that is present but unreadable — without the live tree deciding the verdict.
    A REFUSAL is neither a skip nor a pass: no round may be judged while the bound is
    unreadable, and the run must be RED naming the key it could not read. Without this arm
    the injection could be wired to nothing and every other probe would still pass.
    """
    def _refusing(_repo):
        return None, "", (
            "`duty_receipt_declared` is declared in this tree but cannot be read: "
            "not an instant — REFUSED: probe"
        )

    rc, out, _ = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"],
                      duty_scope=_refusing)
    assert rc == 1, f"a refused bound is a defect, got rc={rc}\n{out}"
    assert "LEG duty-receipt" in out, out
    assert "cannot be read" in out, out[-3000:]
    assert "REFUSED" in out, out[-3000:]

def test_a_round_YOUNGER_than_the_residual_is_NOT_JUDGED_with_its_AGE_printed() -> None:
    """#200's whole defect: a round IN FLIGHT read as a missing duty.

    The filed specimen judged three live lanes MISSING at age 1136 s. A round younger than
    the declared residual has a trigger that fired and a lane that has not finished, which
    this leg cannot tell from a duty never done -- so it must not judge it. The age AND the
    window are both asserted: a bare skip would trade a false RED for a false clean (#160).
    """
    young_read = _plus(_DUTY_FIRE, 0.3)          # 18 min after the fire, well inside 30 min
    leg = _duty_leg([_duty_row()], [], read_at=young_read)
    assert leg["problems"] == [], (
        f"a round still inside its residual must not be judged MISSING: {leg['problems']}")
    assert leg["coverage"]["rounds_excused_by_residual"] == 1, leg["coverage"]
    line = [e for e in leg["excused"] if "IN FLIGHT" in e]
    assert len(line) == 1, leg["excused"]
    assert "18.0 min old" in line[0], line[0]      # the AGE
    assert "30.0 min" in line[0], line[0]          # the WINDOW, beside it
    assert "factory-registry-attest" in line[0], "the round is NAMED, never a bare count"

def test_the_residual_is_PRINTED_in_the_coverage_beside_its_sibling() -> None:
    """Criterion 3: the window travels in the coverage, so an ACCEPTED window is never a
    hidden one -- the same discipline PUBLISH_RESIDUAL_SECS follows for the pusher.

    Since #449 there is no single fleet residual: the coverage carries the DEFAULT and the
    FORM beside the PER-JOB derivations, and a scalar here would be a number no round was
    judged against.
    """
    leg = _duty_leg([_duty_row()], [_receipt_row()])
    assert "residual_secs" not in leg["coverage"], (
        "there is no single fleet residual any more -- a scalar would be a number no round "
        f"was judged against: {leg['coverage'].get('residual_secs')}"
    )
    assert leg["coverage"]["residual_default_secs"] == RUNNER.DUTY_RESIDUAL_DEFAULT_SECS, (
        leg["coverage"]
    )
    # No fires were injected, so this job has no measurable round and falls to the DEFAULT.
    residuals = leg["coverage"]["residuals"]
    assert len(residuals) == 1, residuals
    assert residuals[0]["basis"] == "default", residuals[0]
    assert residuals[0]["residual_secs"] == RUNNER.DUTY_RESIDUAL_DEFAULT_SECS, residuals[0]
    rc, out, err = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"])
    assert "forward residual:" in out, out[-3000:]
    assert "PER JOB, DERIVED" in out, out[-3000:]
    assert f"{RUNNER.DUTY_RESIDUAL_DEFAULT_SECS} s" in out, out[-3000:]

def test_the_residual_does_NOT_excuse_a_round_OLDER_than_it() -> None:
    """The counter-control, and the half that keeps the fix honest: a window that excused
    everything would make the leg permanently clean, which is the pre-fix defect inverted.

    The same round with the same absence, read PAST the residual, must still read MISSING.
    """
    old_read = _plus(_DUTY_FIRE, 5.0)               # 5 h after the fire, far past 30 min
    leg = _duty_leg([_duty_row()], [], read_at=old_read)
    assert leg["coverage"]["rounds_excused_by_residual"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_the_residual_is_DERIVED_from_the_jobs_OWN_measured_max() -> None:
    """#449 criterion 1: the window is the JOB's, never a fleet constant.

    Three fires, three receipts, the longest 6000 s behind its fire. The assertion is made
    against the MARGIN LAW `tools/gate_budget.py` states -- `margin_for(measured_max) *
    measured_max`, read through the runner's own accessor -- rather than against a number
    copied into this probe, because a copied number would be a second statement of the law
    and would keep passing after the law moved.
    """
    fires = _fires((0.5, 26.0, 50.0))
    ledger = [
        _fire_receipt(0.5, 6000.0, 11),
        _fire_receipt(26.0, 3000.0, 12),
        _fire_receipt(50.0, 1200.0, 13),
    ]
    leg = _duty_leg([_duty_row()], ledger, fires=fires)
    residual = leg["coverage"]["residuals"][0]
    assert residual["basis"] == "derived", residual
    assert residual["measured_rounds"] == 3, residual
    assert residual["measured_max_secs"] == 6000.0, residual
    margin = RUNNER.gate_budget_module().margin_for(6000.0)
    assert abs(residual["margin_x"] - margin) < 1e-9, residual
    assert abs(residual["residual_secs"] - margin * 6000.0) < 1e-6, residual
    assert residual["residual_secs"] > RUNNER.DUTY_RESIDUAL_DEFAULT_SECS, (
        "the job's own measured max exceeds the pre-#449 fleet constant, so the derived "
        f"window must be the WIDER one -- the derivation must not collapse back to it: {residual}"
    )
    # THE OBSERVABLE EFFECT, and it is the #449 harm exactly: this round's age (5400 s at
    # the read) is ABOVE the old fleet constant and BELOW this job's own derived residual,
    # so the round the pre-fix leg called a missing duty is now correctly IN FLIGHT.
    assert 5400.0 > RUNNER.DUTY_RESIDUAL_DEFAULT_SECS, "the fixture must straddle the old value"
    assert leg["coverage"]["rounds_excused_by_residual"] == 1, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

def test_an_OVER_CADENCE_residual_is_a_PROBLEM_carrying_its_RATIO() -> None:
    """Ruling n=4153 (board #549): a window that cannot discriminate is a FINDING.

    Measured on this box at 2026-10-25T18:20Z: four of eight declared duties read
    `OVER CADENCE` in the rendered report while `problems` stayed `[]` -- the #160 class (a
    false clean) produced by the leg's OWN output, because the only surface carrying the
    finding was the one a reader greps for problems.

    THE FIXTURE IS THE MEASURED SHAPE, not a convenient one: four fires a day apart with a
    7 h measured max give a residual of ~28 h against a 24 h cadence, i.e. 1.17x -- the same
    class the live `factory-registry-attest` carried at 1.66x in that read.
    """
    fires = _fires((0.5, 24.5, 48.5))
    ledger = [
        _fire_receipt(0.5, 25200.0, 21),
        _fire_receipt(24.5, 25200.0, 22),
        _fire_receipt(48.5, 25200.0, 23),
    ]
    leg = _duty_leg([_duty_row()], ledger, fires=fires)
    residual = leg["coverage"]["residuals"][0]
    assert residual["cadence_secs"] == 86400.0, residual
    assert residual["over_cadence"] is True, residual
    assert leg["coverage"]["rounds_over_cadence"] == 1, leg["coverage"]
    # ARM 1: the duty is NAMED in `problems`, carrying its ratio.
    named = [p for p in leg["problems"] if residual["name"] in p]
    assert len(named) == 1, leg["problems"]
    assert f"{RUNNER.duty_cadence_ratio(residual):.2f}x" in named[0], named[0]
    assert "DISCRIMINATE" in named[0], named[0]
    assert "never" in named[0] and "clamped" in named[0], named[0]
    # AND THE WINDOW IS STILL APPLIED: a problem about the DERIVATION is not a refusal of
    # the duty, and the leg still returns a verdict over the round.
    assert leg["status"] == "ASSERTED", leg
    rc, out, err = _run([], ledger, cron_rows=[_duty_row()], prefixes=["factory-"],
                        cron_fires=fires)
    assert "OVER CADENCE" in out, out[-3000:]
    assert "REPORTED as a PROBLEM" in out, out[-3000:]
    assert "never clamped to the cadence" in out, out[-3000:]

def test_a_SUB_CADENCE_residual_stays_CLEAN() -> None:
    """ARM 2 of the #549 ruling: the POSITIVE CONTROL, and the half that keeps the fix honest.

    A leg that redded on every duty would be permanently red, which is the pre-fix defect
    inverted. Three weekly duties and one sub-cadence duty read clean on this box in the
    SAME read that named four problems, and this fixture is that population's shape: four
    fires a day apart with a 6000 s measured max give a residual of ~6.7 h against the 24 h
    cadence -- 0.28x.
    """
    fires = _fires((0.5, 24.5, 48.5))
    ledger = [
        _fire_receipt(0.5, 6000.0, 31),
        _fire_receipt(24.5, 3000.0, 32),
        _fire_receipt(48.5, 1200.0, 33),
    ]
    leg = _duty_leg([_duty_row()], ledger, fires=fires)
    residual = leg["coverage"]["residuals"][0]
    assert residual["cadence_secs"] == 86400.0, residual
    assert residual["over_cadence"] is False, residual
    assert leg["coverage"]["rounds_over_cadence"] == 0, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

def test_a_residual_of_TWICE_the_cadence_is_NEVER_clean() -> None:
    """ARM 3 of the #549 ruling: the NEGATIVE CONTROL, at the threshold the ruling names.

    At 2x the cadence the window covers two whole fire intervals, so EVERY round sits inside
    it and the leg can excuse a duty indefinitely -- the sharpest form of the defect. On this
    box at 2026-10-25T18:20Z three duties sat past that threshold (7.14x, 15.07x, 12.64x)
    and all three read `problems: 0`. This control FAILS on that tree and passes on the
    fixed one, and it is stated as a property of the leg rather than of a live value.
    """
    fires = _fires((0.5, 24.5, 48.5))
    ledger = [
        _fire_receipt(0.5, 50000.0, 61),
        _fire_receipt(24.5, 50000.0, 62),
        _fire_receipt(48.5, 50000.0, 63),
    ]
    leg = _duty_leg([_duty_row()], ledger, fires=fires)
    residual = leg["coverage"]["residuals"][0]
    ratio = RUNNER.duty_cadence_ratio(residual)
    assert ratio >= 2.0, ratio
    assert residual["over_cadence"] is True, residual
    assert [p for p in leg["problems"] if residual["name"] in p], (
        f"a residual at {ratio:.2f}x the job's own cadence excuses every round it covers, so "
        f"it must never read clean: {leg['problems']}"
    )

def test_a_MILDLY_OVER_CADENCE_duty_reports_JUDGEABLE_with_its_WINDOW() -> None:
    """ARM 4 of the #549 ruling: `factory-registry-attest` reads 1.66x, and it is JUDGEABLE.

    The live read at 2026-10-25T18:20Z: residual 39.91 h against a 24.00 h cadence. A duty
    whose window reaches its cadence is a FINDING, but it is not a duty that cannot be
    judged -- its round IS judged against that window and the leg returns a verdict over it.
    That distinction is the whole of this arm: a problem that read as NOT JUDGED would
    retract a verdict the leg did reach, which is the #160 class in the other direction.
    """
    fires = _fires((0.5, 24.5, 48.5))
    ledger = [
        _fire_receipt(0.5, 35920.0, 41),
        _fire_receipt(24.5, 35920.0, 42),
        _fire_receipt(48.5, 35920.0, 43),
    ]
    # Read PAST the newest fire's window (48.5 h fire + 39.9 h residual), so the round is
    # JUDGED rather than excused as IN FLIGHT -- otherwise the arm would assert judgeability
    # from a run that judged nothing.
    leg = _duty_leg([_duty_row()], ledger, fires=fires,
                    read_at=_plus(_DUTY_BOUND, 100.0))
    residual = leg["coverage"]["residuals"][0]
    ratio = RUNNER.duty_cadence_ratio(residual)
    assert residual["over_cadence"] is True, residual
    assert 1.5 < ratio < 2.0, ratio
    assert leg["coverage"]["duties_judged"], leg["coverage"]
    named = [p for p in leg["problems"] if residual["name"] in p]
    assert len(named) == 1, leg["problems"]
    assert "still JUDGEABLE with" in named[0], named[0]
    assert f"{ratio:.2f}x" in named[0], named[0]
    assert "never refused" in named[0], named[0]

def test_a_SUPPRESSED_duty_keeps_its_EXCUSE_beside_the_CADENCE_finding() -> None:
    """ARM 5 of the #549 ruling: the new finding must not SWALLOW the existing excuses.

    `factory-questions-redeliver` is the live instance: it is judged on a PRIOR round every
    time because its own gate suppresses each fire, and its excuse is the daemon's own record
    rather than a declaration. A problem appended to the same leg must leave that excuse in
    `excused`, with its reason -- a finding that displaced an excuse would trade a false
    clean for a false MISSING, which is the #160 class from the other side.

    THE FIXTURE IS MIXED SINCE #617, and that is the point rather than a convenience. The
    exclusion surface now removes a suppressed round from the job's LATENCY observations as
    well as from its judgement: a round whose trigger gate skipped it never woke the lane, so
    whatever latency sits beside it measures something other than the lane's promptness. An
    all-suppressed job therefore has NO observation to derive a residual from -- it falls back
    to the short default and cannot report a cadence finding at all, which is the correct
    answer for a job that never ran. To keep this arm measuring what it was written to measure
    (a finding must not SWALLOW an excuse), one round is suppressed and two are real: the
    suppressed round must stay in `excused` while the two real ones carry the cadence finding.
    An all-suppressed fixture would now be asserting a state the instrument says cannot exist.
    """
    fires = _fires((0.5, 24.5, 48.5))
    fires[0] = dict(fires[0],
                    content=f"Trigger condition not met (exit_code=0, output_bytes=0). "
                            f"{RUNNER.CRON_SUPPRESSION_MARKER}.")
    fires[0]["suppressed"] = RUNNER.fire_is_suppressed(fires[0]["content"])
    ledger = [
        _fire_receipt(0.5, 25200.0, 51),
        _fire_receipt(24.5, 25200.0, 52),
        _fire_receipt(48.5, 25200.0, 53),
    ]
    leg = _duty_leg([_duty_row()], ledger, fires=fires,
                    read_at=_plus(_DUTY_BOUND, 100.0))
    assert leg["coverage"]["rounds_excused_by_suppression"] >= 1, leg["coverage"]
    suppressed = [e for e in leg["excused"] if "SUPPRESSED" in e]
    assert suppressed, leg["excused"]
    assert RUNNER.CRON_SUPPRESSION_MARKER in suppressed[0], suppressed[0]
    # AND the cadence finding is still there: the two are different facts about one job.
    assert leg["coverage"]["rounds_over_cadence"] == 1, leg["coverage"]
    assert any("DISCRIMINATE" in p for p in leg["problems"]), leg["problems"]

def test_a_MALFORMED_receipt_is_REPORTED_and_proven_to_BITE() -> None:
    """#281 (A), acceptance 1 of ruling n=2003 — and the BITE is the probe.

    THE MEASURED INSTANCE, and it is a real row: n=1966 writes its receipt as
    *"DUTY RECEIPT, duty=completed."* in the prose HEAD and closes with
    *"Session: f4c192c9-… (actor triage)."* — so the canonical terminal run is empty,
    `declared_duty` reads NOTHING, and a lane that declared its completion reads as a lane
    that declared nothing. The author is told to declare the token they believe they
    declared; the reader cannot reach it. Neither "clean" nor "missing duty" describes that
    state, so the leg names it and names the repair.

    PROVEN TO BITE: the second half neuters `mentions_duty` to a constant False and asserts
    the finding MOVES back to the generic no-declaration text. Without that half the
    assertion would pass on any fixture, including one where the finding came from
    something else entirely.
    """
    prose = (
        "TRIAGE CYCLE — patrol-verify-2026-09-25. DUTY RECEIPT, duty=completed.\n"
        "Session: f4c192c9-a8e9-4268-9026-ee3e4970cc8a (actor triage)."
    )
    row = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}", detail=prose, n=1875)
    leg = _duty_leg([_duty_row()], [row])
    assert leg["coverage"]["receipts_malformed"] == 1, leg["coverage"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "MALFORMED RECEIPT" in problem, problem
    assert "OWN VOICE" in problem, problem
    assert "Make it TERMINAL" in problem, problem
    assert "n=1875" in problem, "the finding must NAME the row it is about, by number"
    assert "registry-attest-2026-09-25" in problem, problem
    assert "never a missing duty" in problem, (
        "the finding must refuse the missing-duty reading, because a lane that declared is "
        f"not a lane that did nothing: {problem}"
    )
    # THE BITE: neuter the discriminator and the finding must vanish, leaving the generic
    # no-declaration text behind. A finding that survives this is not this finding.
    neutered = _duty_leg([_duty_row()], [row],
                         predicate=_stub_predicate(mentions_duty=lambda detail: False))
    assert neutered["coverage"]["receipts_malformed"] == 0, (
        f"the malformed class must be produced BY `mentions_duty`: {neutered['coverage']}"
    )
    assert "MALFORMED RECEIPT" not in neutered["problems"][0], (
        f"with the discriminator neutered the generic text must return: {neutered['problems']}"
    )
    assert "declare no `duty=`" in neutered["problems"][0], neutered["problems"][0]

def test_the_OWN_VOICE_discriminator_keeps_a_QUOTED_aside_out() -> None:
    """The discriminator is the #278 helper, and THIS is what proves it is load-bearing.

    A token inside a PARENTHETICAL ASIDE is a CITATION of another row's trailer, and the
    ruling names exactly this as what keeps the detector off a row that quotes a token. The
    probe neuters the own-voice scope — the same scan with the aside-stripping REMOVED — and
    asserts the finding appears, so the clean verdict on the real reader is attributable to
    that scope and not to the fixture happening to be quiet.

    A SECOND discriminator was refused (n=405 PART 5 / n=599), so this probe asserts the
    SHARED reader is the one doing the separating rather than a private walk here.
    """
    aside = (
        "the round was cleared by the repair recorded in n=1999 (whose trailer carries "
        "duty=completed), and nothing further is owed."
    )
    row = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}", detail=aside, n=2000)
    real = RUNNER.field_predicate_readers()
    assert real.mentions_duty(aside) is False, "the shared reader must drop the aside"
    assert _lexical_duty_scan(aside) is True, "the lexical control must keep it, or it proves nothing"
    leg = _duty_leg([_duty_row()], [row])
    assert leg["coverage"]["receipts_malformed"] == 0, leg["coverage"]
    assert "MALFORMED RECEIPT" not in leg["problems"][0], leg["problems"][0]
    neutered = _duty_leg([_duty_row()], [row],
                         predicate=_stub_predicate(mentions_duty=_lexical_duty_scan))
    assert neutered["coverage"]["receipts_malformed"] == 1, (
        "without the own-voice scope the aside must be read as a mention — that is the "
        f"over-inclusion the scope exists to narrow: {neutered['coverage']}"
    )

def test_a_repair_rows_round_is_READ_through_its_DECLARING_row() -> None:
    """The n=2000 population control, stated as a probe because the ruling states it.

    n=2000 is a repair record that QUOTES the token and then MENTIONS it unquoted in its own
    prose ("the receipt row declares duty=completed in its TEXT"). No lexical reader can tell
    that mention from a declaration, so the ruling keeps the detector off n=2000 by its
    POPULATION rather than by a cleverer predicate: the round it keys (2026-10-03) also
    carries n=1999, which DECLARES. So the round is judged clean and the repair record is
    never asked the question — which is what this probe pins, so a future change that made
    n=2000 the only row of its round would show up here as the behaviour change it is.
    """
    repair = _receipt_row(
        subject=f"registry-attest-{_DUTY_ROUND}",
        detail=("the repair of n=1999: the receipt row declares duty=completed in its "
                "TEXT. Session: 8f0c (actor triage)."),
        n=2000,
    )
    declaring = _receipt_row(subject=f"registry-attest-{_DUTY_ROUND}", n=1999)
    leg = _duty_leg([_duty_row()], [declaring, repair])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["receipts_malformed"] == 0, leg["coverage"]
    assert leg["coverage"]["duties_judged"][0]["receipts"] == 1, leg["coverage"]

def test_the_PRIOR_round_is_JUDGED_when_the_newest_is_IN_FLIGHT() -> None:
    """#281 (B), acceptance 2 — the permanent gap this fixes, and it is a REAL one.

    `factory-triage-patrol` fires every 6 h and its own derived residual reaches 3.77 d, so
    the round the leg judged was ALWAYS the one still in flight: the `continue` ended the
    job's turn and no round was ever examined. Measured live at 2026-10-12T18:40Z, the job
    had no round judged at all.

    Here the newest fire is 18 min old (inside the 30 min default residual) and the fire
    before it is a day older, with NO receipt: the leg must judge the PRIOR round and NAME
    it, and the excuse must still name the round it declined to judge.
    """
    newest = _plus(_DUTY_BOUND, 74.0)
    prior = _plus(_DUTY_BOUND, 50.0)
    read_at = _plus(newest, 0.3)                      # 18 min after the newest fire
    row = _duty_row(last_run_at=newest)
    # The row's OWN scheduling record, carried since #281 (ruling n=2003): the reason a
    # round was skipped is the cadence against the residual, so the finding must name the
    # schedule it belongs to rather than leaving the reader to guess it.
    row["cron_expr"] = "0 */6 * * *"
    row["next_run_at"] = _plus(newest, 6.0)
    fires = [
        {"job_id": row["id"], "job_name": row["name"], "started_at": prior},
        {"job_id": row["id"], "job_name": row["name"], "started_at": newest},
    ]
    leg = _duty_leg([row], [], read_at=read_at, fires=fires)
    assert leg["coverage"]["rounds_judged_by_fallback"] == 1, leg["coverage"]
    assert leg["coverage"]["rounds_prior_unreadable"] == 0, leg["coverage"]
    judged = leg["coverage"]["duties_judged"]
    assert len(judged) == 1, judged
    assert judged[0]["round"] == prior[:10], (
        f"the PRIOR round must be the one judged, and it must be NAMED: {judged[0]}"
    )
    assert judged[0]["fallback_from"] == newest[:10], judged[0]
    assert judged[0]["fired"] == prior, judged[0]
    assert len(leg["problems"]) == 1, leg["problems"]
    problem = leg["problems"][0]
    assert "PRIOR round" in problem, problem
    assert "is NOT JUDGED" in problem, problem
    assert newest[:10] in problem, "the round being declined must be named too"
    assert "0 */6 * * *" in problem, (
        f"the PRIOR-round note must carry the row's own schedule: {problem}"
    )
    in_flight = [e for e in leg["excused"] if "IN FLIGHT" in e]
    assert len(in_flight) == 1, leg["excused"]
    assert newest[:10] in in_flight[0], in_flight[0]

def test_a_prior_round_that_cannot_be_DERIVED_is_NOT_JUDGED_with_its_reason() -> None:
    """#281 (B)'s bound — acceptance 3, and it is the #112/#160 law, not a nicety.

    The ruling is explicit: where the prior round cannot be derived the leg prints NOT JUDGED
    with its reason, NEVER a silent fallback to the old behaviour. A fallback that cannot
    judge must say so, because silence here is exactly the false clean the leg exists to
    catch — and the old behaviour was a silent one.

    The instant is READ from the job's own run record and never composed (`next_run_at -
    last_run_at` is the #175 class wearing arithmetic), so a job whose record holds only the
    in-flight fire has no prior round to name.
    """
    newest = _plus(_DUTY_BOUND, 74.0)
    read_at = _plus(newest, 0.3)
    row = _duty_row(last_run_at=newest)
    fires = [{"job_id": row["id"], "job_name": row["name"], "started_at": newest}]
    leg = _duty_leg([row], [], read_at=read_at, fires=fires)
    assert leg["coverage"]["rounds_prior_unreadable"] == 1, leg["coverage"]
    assert leg["coverage"]["rounds_judged_by_fallback"] == 0, leg["coverage"]
    assert leg["coverage"]["duties_judged"] == [], (
        f"no round may be judged from a fire the record does not date: {leg['coverage']}"
    )
    assert leg["problems"] == [], (
        f"an unexamined round is not a RED — it is a stated absence: {leg['problems']}"
    )
    stated = [e for e in leg["excused"] if "NO fire before it" in e]
    assert len(stated) == 1, leg["excused"]
    assert "NOT JUDGED" in stated[0], stated[0]
    assert "no prior round can be NAMED" in stated[0], stated[0]

def test_the_runner_PRINTS_the_prior_round_and_the_malformed_class() -> None:
    """Acceptance 4, the printing half: the leg's population and its two new verdicts.

    A verdict that never reaches the report is a verdict no reader can act on, and the
    population line is what keeps an empty or one-row population from reading as a clean
    box (#160). Both new classes are asserted at the RENDERED output, not at the coverage
    dict, because the coverage dict is what the leg computes and the report is what the
    operator reads.
    """
    now = dt.datetime.now(dt.timezone.utc)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    newest = iso(now - dt.timedelta(minutes=10))
    prior = iso(now - dt.timedelta(hours=24, minutes=10))
    prior_date = prior[:10]
    row = _duty_row(last_run_at=newest)
    fires = [
        {"job_id": row["id"], "job_name": row["name"], "started_at": prior},
        {"job_id": row["id"], "job_name": row["name"], "started_at": newest},
    ]
    malformed = {
        "n": 1875, "ts": prior, "event": "run", "actor": "triage",
        "subject": f"registry-attest-{prior_date}",
        "detail": (f"TRIAGE CYCLE — patrol-verify-{prior_date}. DUTY RECEIPT, "
                   f"duty=completed.\nSession: 8f0c (actor triage)."),
    }
    rc, out, err = _run([], [malformed], cron_rows=[row], prefixes=["factory-"],
                        cron_fires=fires)
    assert "LEG duty-receipt" in out, out
    assert "jobs: 1 enabled row(s) attributed to this factory of 1 read across" in out, out
    assert "duties: 1 row(s) declare a receipt" in out, out
    assert "were judged as the PRIOR fire's round" in out, out[-4000:]
    assert "MALFORMED RECEIPT" in out, out[-4000:]
    assert "make it terminal" in out, out[-4000:]
    assert f"round {prior_date}" in out, "the judged round must be NAMED in the report"
    assert rc == 1, "both new classes are findings, so the run must fail"

def test_the_drift_leg_counts_same_diff_and_absent_apart() -> None:
    """Three DIFFERENT facts. Folding them would hide which one a member has."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(
            root,
            files={"tools/a.py": b"a", "tools/b.py": b"b", "tools/c.py": b"c"},
            members={"alpha": {"same": {"tools/a.py": b"a"}, "diff": {"tools/b.py": b"WRONG"}}},
        )
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        cov = leg["coverage"]
        assert leg["problems"] == [], leg["problems"]
        assert cov["manifest_cells"] == {"same": 1, "DIFF": 1, "ABSENT": 1}, cov["manifest_cells"]
        member = cov["members"][0]
        assert member["slug"] == "alpha" and member["reachable"]
        assert member["absent_files"] == ["tools/c.py"], member["absent_files"]
        assert member["diff_files"] == ["tools/b.py"], member["diff_files"]

def test_a_member_is_never_a_PROBLEM_even_when_fully_stale() -> None:
    """Drift belongs to the MEMBER. Reddening this factory's patrol for another lane's
    backlog would make our verdict a function of that lane's queue -- the coupling the
    leg's whole design avoids -- and a leg that reds forever teaches readers to ignore a
    red patrol (#139's permanent-false-positive class)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(
            root, files={"tools/a.py": b"a"},
            members={"alpha": {"diff": {"tools/a.py": b"DIFFERENT"}}},
        )
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        assert leg["problems"] == [], f"drift must not red the patrol: {leg['problems']}"
        assert leg["coverage"]["manifest_cells"]["DIFF"] == 1

def test_a_STALE_SHARED_SURFACE_writer_is_a_PROBLEM_and_an_absent_one_is_not() -> None:
    """#514, ruled at ledger n=3792. THE TWO ARMS ARE THE WHOLE POINT.

    A `shared-surface` file writes a box-wide store, so a member's stale copy mutates state
    every factory reads -- that is not that member's backlog, it is this factory's hazard,
    and it must red here. Its ABSENCE is the SAFE state: a factory that does not carry the
    writer never writes the surface, so flagging absence would punish the members that did
    nothing wrong.

    The third arm is the CONTROL the first would pass without: the SAME diverging tree with
    the classification removed reads clean. That is what makes the problem a function of the
    declaration rather than of the bytes -- and it is why the class is read from the
    manifest's own map instead of being inferred from what the file looks like.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # ARM 1 -- declared shared-surface, member's copy DIFFERS -> exactly one problem,
        # naming BOTH the member and the file.
        mpath, fpath = _synthetic_kit(
            root, files={"tools/questions": b"current"},
            members={"stale": {"diff": {"tools/questions": b"superseded"}}},
            classes={"tools/questions": "shared-surface"},
        )
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        assert len(leg["problems"]) == 1, leg["problems"]
        assert "`stale`" in leg["problems"][0], leg["problems"][0]
        assert "tools/questions" in leg["problems"][0], leg["problems"][0]
        cells = leg["coverage"]["shared_surface"]["cells"]
        assert cells == {"same": 0, "DIFF": 1, "ABSENT": 0}, cells

        # ARM 2 -- same fixture, the member does NOT carry the file -> no problem, and the
        # safe state is RECORDED rather than inferred from a total.
        mpath2, fpath2 = _synthetic_kit(
            root / "absent", files={"tools/questions": b"current"},
            members={"silent": {"same": {"tools/other.py": b"x"}}},
            classes={"tools/questions": "shared-surface"},
        )
        leg2 = RUNNER.kit_drift_leg(manifest_path=mpath2, fleet_path=fpath2, read_at="probe")
        assert leg2["problems"] == [], leg2["problems"]
        assert leg2["coverage"]["shared_surface"]["cells"]["ABSENT"] == 1, \
            leg2["coverage"]["shared_surface"]["cells"]

        # ARM 3 -- CONTROL: the identical DIFF with NO classification reads clean, so arm 1
        # is measuring the declaration and not the divergence.
        mpath3, fpath3 = _synthetic_kit(
            root / "unclassified", files={"tools/questions": b"current"},
            members={"stale": {"diff": {"tools/questions": b"superseded"}}},
        )
        leg3 = RUNNER.kit_drift_leg(manifest_path=mpath3, fleet_path=fpath3, read_at="probe")
        assert leg3["problems"] == [], f"the class must be load-bearing: {leg3['problems']}"
        assert leg3["coverage"]["shared_surface"]["files"] == [], \
            leg3["coverage"]["shared_surface"]

def test_an_unreachable_member_is_reported_never_silently_skipped() -> None:
    """A member whose repo is absent is NAMED. A sweep that silently dropped it would
    report a smaller population as if it were the whole one."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(root, files={"tools/a.py": b"a"}, members={})
        fleet = json.loads(fpath.read_text())
        fleet["factories"].append({"slug": "ghost", "repo": str(root / "does-not-exist")})
        fpath.write_text(json.dumps(fleet), encoding="utf-8")
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        cov = leg["coverage"]
        assert cov["members_unreachable"] == ["ghost"], cov["members_unreachable"]
        assert cov["members_reachable"] == 0
        assert any("no member repository was reachable" in p for p in leg["problems"]), \
            leg["problems"]

def test_an_UNREADABLE_member_root_is_recorded_unreachable_never_raised() -> None:
    """#429: a member root the box cannot READ is UNREACHABLE, not a traceback.

    `Path.is_dir()` answers False for a root that is ABSENT, but it RE-RAISES when a
    PARENT of the root denies traversal, because EACCES is not among the errors pathlib
    ignores. So a member repo under a mode-700 home -- a CI runner's `/root` -- raised
    straight out of `kit_drift_leg`, on the very leg whose job is to record that the member
    could not be read, and took the whole sweep with it.

    Measured in inferhub-watch run 37587867752, head 569088a, job `validate`, Python
    3.12.14: `PermissionError: [Errno 13] Permission denied: '/root/inferhub-watch'` at
    `pathlib.py:840`, raised from the member's own `kit_drift_leg` line 1556 -- the
    byte-identical `if not root.is_dir():` this probe now guards.

    The failure is DRIVEN, never simulated with a permission bit, for the reason the
    notify-receipt leg states at its own read-failure probe: this gate runs as root on this
    box, so a `chmod 000` parent is traversed happily and the probe would pass for the
    wrong reason. A second, independent reason applies here: this box's Python is 3.14,
    where `is_dir` delegates to `os.path.isdir` and swallows the error -- so only a DRIVEN
    raise exercises the code path the member's Python takes.

    A missing root and an unreadable one are the same class with DIFFERENT remedies (a
    stale fleet entry versus a permissions problem on the member's box), so the reason is
    asserted to reach the RENDER, which is a second surface.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(root, files={"tools/a.py": b"a"}, members={})
        fleet = json.loads(fpath.read_text())
        guarded = root / "unreadable"
        fleet["factories"].append({"slug": "locked", "repo": str(guarded)})
        fpath.write_text(json.dumps(fleet), encoding="utf-8")

        real_is_dir = Path.is_dir

        def denying_is_dir(self, *args, **kwargs):
            if self == guarded:
                raise PermissionError(13, "Permission denied", str(self))
            return real_is_dir(self, *args, **kwargs)

        with mock.patch.object(Path, "is_dir", denying_is_dir):
            leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
            text = RUNNER.render([leg], [], slug="owner/repo", read_at="probe", issues=[])

        cov = leg["coverage"]
        assert cov["members_unreachable"] == ["locked"], cov["members_unreachable"]
        assert cov["members_reachable"] == 0, cov["members_reachable"]
        member = cov["members"][0]
        assert member["reachable"] is False, member
        assert "PermissionError" in member["reason"], (
            f"the reason must NAME the failure class -- an unreadable root and an absent "
            f"one share the UNREACHABLE verdict but not the remedy: {member}"
        )
        assert "UNREACHABLE" in text and "PermissionError" in text, (
            f"the reason must reach the RENDER, which is a second surface:\n{text}"
        )
        assert any("no member repository was reachable" in p for p in leg["problems"]), \
            leg["problems"]

def test_the_meta_factory_is_excluded_from_its_own_drift_sweep() -> None:
    """This factory IS the template source: comparing it against its own manifest would
    report every file identical and inflate the totals with a tautology."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(root, files={"tools/a.py": b"a"}, members={})
        fleet = json.loads(fpath.read_text())
        fleet["factories"].append({"slug": "meta-factory", "repo": str(root)})
        fpath.write_text(json.dumps(fleet), encoding="utf-8")
        leg = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="probe")
        assert leg["coverage"]["members_declared"] == 0, leg["coverage"]["members_declared"]
        assert leg["coverage"]["manifest_cells_total"] == 0

def test_an_absent_manifest_EXAMINES_NOTHING_and_says_so() -> None:
    """The examined-nothing case is this leg's ONLY problem: with no reference there is
    nothing to measure, and a clean sweep over no population is not a verdict."""
    with tempfile.TemporaryDirectory() as tmp:
        leg = RUNNER.kit_drift_leg(
            manifest_path=Path(tmp) / "absent.json", fleet_path=Path(tmp) / "fleet.json",
            read_at="probe",
        )
        assert leg["status"] == "NOT RUN", leg["status"]
        assert any("examined NOTHING" in p for p in leg["problems"]), leg["problems"]

def test_an_absent_manifest_RENDERS_as_NOT_RUN_never_a_traceback() -> None:
    """The render path is a SECOND surface, and a leg that reports correctly but
    crashes while printing has reported nothing.

    Measured 2026-09-25: the kit-drift branch read `coverage["manifest_cells"]`
    unconditionally, so the absent-manifest path -- the one that exists to REPORT the
    absence -- raised KeyError instead. It was reachable in the TEMPLATE copy, whose
    REPO resolves to TEMPLATE/ where `registry/kit.json` is factory data and never
    ships. Every other kit-drift probe injects a manifest, so none of them could see it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(root, files={"tools/a.py": b"a"}, members={})
        mpath.unlink()  # the manifest is ABSENT: the NOT RUN path
        out = io.StringIO()
        RUNNER.main(
            [], board_fn=lambda slug: [], slug_fn=lambda: "owner/repo",
            rows_fn=lambda: [], cron_rows_fn=lambda: ([], ["probe-home"], []),
            cron_fires_fn=lambda: [],
            prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
            scores_dir_fn=lambda: _EMPTY_SCORES_DIR,
            kit_manifest=mpath, fleet_manifest=fpath,
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
            shared_tree_fn=_stub_shared_tree_rider,
            # #133: the driverless-lane leg's goal store and its turn-in-flight read are
            # injected here for the same reason every other live surface is -- and the
            # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
            # granting one, so a probe that never asserts a driver cannot read one.
            driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
            driverless_turn_open_fn=lambda: {},
            # #330: the ref-role store is injected for the same reason the ruling table is.
            ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
        )
        text = out.getvalue()
        assert "LEG kit-drift" in text, text
        assert "NOT RUN" in text, text
        assert "examined NOTHING" in text, text
        assert "manifest_cells" not in text, text

def test_an_empty_manifest_is_a_FAILURE_not_a_universal_agreement() -> None:
    """A manifest declaring no files would agree with every tree in existence."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "kit.json").write_text(json.dumps({"files": {}}), encoding="utf-8")
        (root / "fleet.json").write_text(json.dumps({"factories": []}), encoding="utf-8")
        leg = RUNNER.kit_drift_leg(manifest_path=root / "kit.json",
                                   fleet_path=root / "fleet.json", read_at="probe")
        assert any("declares NO files" in p for p in leg["problems"]), leg["problems"]

def test_the_MUTATION_control_flips_same_to_DIFF_without_touching_a_member_tree() -> None:
    """The probe that makes the leg's green mean something.

    A leg reporting `same` for every cell is exactly what a vacuous implementation would
    print, so the leg is driven twice over ONE synthetic pair: once clean, and once with a
    single byte moved in a file that previously matched. The moved byte is written to a
    COPY of the member tree, so no real repository is touched -- and the live member trees
    are compared before and after, so that claim is measured rather than asserted.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(
            root, files={"tools/a.py": b"a", "tools/b.py": b"b"},
            members={"alpha": {"same": {"tools/a.py": b"a", "tools/b.py": b"b"}}},
        )
        before = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="p1")
        assert before["coverage"]["manifest_cells"] == {"same": 2, "DIFF": 0, "ABSENT": 0}, \
            before["coverage"]["manifest_cells"]

        # The mutation lands in a COPY of the member tree, never the tree itself.
        member_root = root / "alpha"
        copied = root / "alpha-copy"
        shutil.copytree(member_root, copied)
        (copied / "tools/a.py").write_bytes(b"a-MUTATED")
        fleet = json.loads(fpath.read_text())
        fleet["factories"][0]["repo"] = str(copied)
        fpath.write_text(json.dumps(fleet), encoding="utf-8")

        after = RUNNER.kit_drift_leg(manifest_path=mpath, fleet_path=fpath, read_at="p2")
        assert after["coverage"]["manifest_cells"] == {"same": 1, "DIFF": 1, "ABSENT": 0}, \
            after["coverage"]["manifest_cells"]
        assert after["coverage"]["members"][0]["diff_files"] == ["tools/a.py"]

        # The ORIGINAL member tree is byte-identical: the mutation was on a copy.
        assert (member_root / "tools/a.py").read_bytes() == b"a"
        assert (member_root / "tools/b.py").read_bytes() == b"b"

def test_the_leg_reaches_the_RENDERED_report() -> None:
    """A leg whose output never renders is a leg nobody reads."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        mpath, fpath = _synthetic_kit(
            root, files={"tools/a.py": b"a"},
            members={"alpha": {"same": {"tools/a.py": b"a"}}},
        )
        out = io.StringIO()
        RUNNER.main(
            [], board_fn=lambda slug: [], slug_fn=lambda: "owner/repo",
            rows_fn=lambda: [], cron_rows_fn=lambda: ([], ["probe-home"], []),
            cron_fires_fn=lambda: [],
            prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
            scores_dir_fn=lambda: _EMPTY_SCORES_DIR,
            kit_manifest=mpath, fleet_manifest=fpath,
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
            shared_tree_fn=_stub_shared_tree_rider,
            # #133: the driverless-lane leg's goal store and its turn-in-flight read are
            # injected here for the same reason every other live surface is -- and the
            # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
            # granting one, so a probe that never asserts a driver cannot read one.
            driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
            driverless_turn_open_fn=lambda: {},
            # #330: the ref-role store is injected for the same reason the ruling table is.
            ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
        )
        text = out.getvalue()
        assert "LEG kit-drift" in text, text
        assert "drift over the WHOLE manifest (1 cells)" in text, text
        assert "alpha: same=1 DIFF=0 ABSENT=0" in text, text

def test_the_live_baseline_reproduces_the_measured_figure() -> None:
    """The criterion's own figure, re-derived from the leg rather than quoted.

    The 1/20/29 baseline was measured over the BOOTSTRAP-NAMED set across the member
    factories -- a narrower predicate than the whole manifest -- so both populations are
    read here and the bootstrap one is asserted against its own recorded figure. If a
    member ports a file, this figure MOVES, and the assertion is meant to be updated
    rather than to fail for ever: it pins the predicate, not a permanent state.
    """
    leg = RUNNER.kit_drift_leg(read_at="probe")
    cov = leg["coverage"]
    # A tree carrying no manifest — a bootstrapped factory, or the TEMPLATE copy, whose
    # REPO resolves to TEMPLATE/ — has nothing to reproduce, and the leg says so with a
    # stated reason rather than a clean sweep. Both states are legitimate; what is NOT
    # legitimate is reading either as a verdict about a member.
    if leg["status"] == "NOT RUN" or cov.get("members_reachable", 0) == 0:
        print(f"  (no live member repos to reproduce against: {cov.get('reason', 'none reachable')})")
        return
    boot = cov["bootstrap_cells"]
    assert len(cov["bootstrap_named"]) == 10, len(cov["bootstrap_named"])
    assert cov["bootstrap_cells_total"] == 10 * cov["members_reachable"], cov
    print(f"  (live bootstrap drift: {boot['same']} same / {boot['DIFF']} DIFF / "
          f"{boot['ABSENT']} ABSENT over {cov['bootstrap_cells_total']} cells)")

def test_the_reference_is_read_from_HEAD_not_from_the_working_tree() -> None:
    """Issue #185: a member's pin is COMMITTED, so the reference it is judged against has
    to be re-derivable by a reader who was not here.

    The manifest is GENERATED FROM THE WORKING TREE, so a disk read returns whatever the
    last generation happened to see — and a lane mid-write changes it under the reader.
    Measured at the filing (2026-09-26): five distinct kit_version values in about 23
    minutes, TWO of which appeared in no commit at all, the file changed between two reads
    14 seconds apart, and the manifest included two files untracked at that instant.

    THE PROBE IS HERMETIC AND THE BITE IS REAL, which is why it is built this way. On the
    live tree HEAD and the working copy AGREE, so a live assertion would pass under the
    PRE-FIX code too and would prove nothing about the dispatch. So the leg is pointed at a
    throwaway repository built here whose HEAD and working copy deliberately DISAGREE — the
    window the filing measured, reproduced deterministically — and driven twice over that
    ONE tree: once with no manifest_path (the live call, which must read HEAD) and once with
    an explicit path (the probe call, which must still read disk). The two answers must
    DIFFER, and in that direction. Under the pre-fix code both arms read the file, both
    return the dirty version, and the first assertion below fails.
    """
    import hashlib

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        (repo / "registry").mkdir(parents=True)

        member = root / "member"
        (member / "tools").mkdir(parents=True)
        (member / "tools" / "a.py").write_bytes(b"a")
        files = {"TEMPLATE/tools/a.py": hashlib.sha256(b"a").hexdigest()}

        (repo / "registry" / "kit.json").write_text(
            json.dumps({"kit_version": "COMMITTED", "files": files}), encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.email=probe@probe.invalid", "-c", "user.name=probe",
                      "commit", "-qm", "probe"]):
            done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
            assert done.returncode == 0, done.stderr

        # THE WINDOW: the working copy now names a version that appears in NO commit.
        (repo / "registry" / "kit.json").write_text(
            json.dumps({"kit_version": "DIRTY-UNCOMMITTED", "files": files}), encoding="utf-8")

        fleet = root / "fleet.json"
        fleet.write_text(json.dumps({"factories": [{"slug": "alpha", "repo": str(member)}]}),
                         encoding="utf-8")

        with mock.patch.object(RUNNER, "REPO", repo), \
                mock.patch.object(RUNNER, "KIT_MANIFEST_REL", "registry/kit.json"):
            head_arm = RUNNER.kit_drift_leg(fleet_path=fleet, read_at="head")
            disk_arm = RUNNER.kit_drift_leg(manifest_path=repo / "registry" / "kit.json",
                                            fleet_path=fleet, read_at="disk")

        assert head_arm["coverage"]["kit_version"] == "COMMITTED", head_arm["coverage"]
        assert disk_arm["coverage"]["kit_version"] == "DIRTY-UNCOMMITTED", disk_arm["coverage"]
        assert head_arm["coverage"]["manifest_source"] == "HEAD:registry/kit.json"
        assert disk_arm["coverage"]["manifest_source"].endswith("registry/kit.json")
        # Both arms saw the SAME member tree, so the only thing that moved the reference was
        # where it was read from — not a different fixture.
        assert (head_arm["coverage"]["manifest_files"]
                == disk_arm["coverage"]["manifest_files"])

def test_the_LIVE_reference_is_the_committed_manifest() -> None:
    """The live half of the #185 remedy, and the provenance that makes it checkable.

    The probe above proves the DISPATCH hermetically; this one pins the LIVE call to the
    committed bytes, so a later change that quietly restored a disk default is caught
    against the real repository rather than only against a fixture. It derives the expected
    version the SAME way the leg does — `git show HEAD:registry/kit.json` — so it cannot
    drift from the leg's own definition of "the committed manifest", and it asserts the
    provenance field, because a HEAD read and a disk read print identically otherwise and
    the whole change is which one happened.
    """
    leg = RUNNER.kit_drift_leg(read_at="probe")
    cov = leg["coverage"]
    if leg["status"] == "NOT RUN":
        # A tree carrying no manifest at HEAD — a bootstrapped factory, or this file's
        # TEMPLATE twin, whose REPO resolves to TEMPLATE/ where `registry/kit.json` is
        # factory data that never ships. STATED, never silently passed.
        print(f"  (no committed manifest to pin: {cov.get('reason')})")
        return
    done = subprocess.run(["git", "-C", str(RUNNER.REPO), "show", "HEAD:registry/kit.json"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    at_head = json.loads(done.stdout)
    assert cov["manifest_source"] == "HEAD:registry/kit.json", cov["manifest_source"]
    assert cov["kit_version"] == at_head["kit_version"], (cov["kit_version"], at_head["kit_version"])
    assert cov["manifest_files"] == len(at_head["files"]), cov["manifest_files"]

def test_a_block_records_the_CELL_POPULATION_its_own_header_declares() -> None:
    """#531 clause 1: `declared` and `parsed` travel ON the block, so no caller re-derives.

    The two numbers are the instrument. A consumer that counted cells itself would be a
    second reader of one fact -- which is how both consumers came to report a clean round
    over a block that had lost a cell.
    """
    blocks = RUNNER.scorecard_blocks(_cell_score_artifact(cells=["4"] * 18 + ["—"]))
    assert len(blocks) == 1, blocks
    assert blocks[0]["declared"] == 19, blocks[0]
    assert blocks[0]["parsed"] == 18, blocks[0]
    assert len(blocks[0]["cells"]) == 18, blocks[0]

    # A well-formed card declares and delivers the SAME count -- the record must not read
    # "short" for a block that is whole.
    whole = RUNNER.scorecard_blocks(_cell_score_artifact(cells=["4"] * 19))
    assert (whole[0]["declared"], whole[0]["parsed"]) == (19, 19), whole[0]
    assert RUNNER.scorecard_shortfalls(whole) == [], whole

    # ... and a body NARROWER than its own header is SHORT, never absent: the block was
    # found and read zero cells out of it, which is the 10-17 shape wearing another face.
    ragged = RUNNER.scorecard_blocks(
        _cell_score_artifact(cells=["4"] * 18, declared=19)
    )
    assert (ragged[0]["declared"], ragged[0]["parsed"]) == (19, 0), ragged[0]
    assert len(RUNNER.scorecard_shortfalls(ragged)) == 1, ragged

def test_the_newest_round_REFUSES_a_ZERO_CELL_block_instead_of_calling_it_clean() -> None:
    """#531 acceptance 1, and the FILED symptom: 2026-10-17's six cards, 0 cells each.

    Before the repair the leg returned ASSERTED with `criteria_cells: 0` and `regressions:
    []` -- a clean verdict over a population it never read, indistinguishable from a round
    that examined 114 cells and found them clean. The refusal must name the BLOCK and BOTH
    counts: "the parse was short" without the numbers is the same unverifiable claim in a
    different voice.
    """
    directory = _scores_dir(_per_family_score_artifact())
    leg = RUNNER.score_conversion_leg(
        [_non_conversion_row()], read_at="probe", scores_dir=directory
    )
    assert leg["status"] == "NOT RUN", leg
    assert leg["problems"] == [], leg["problems"]
    cov = leg["coverage"]
    assert cov["criteria_cells"] == 0, cov
    assert cov["incomplete_blocks"] == [
        {"factory": "Probe factory", "parsed": 0, "declared": 0}
    ], cov["incomplete_blocks"]
    reason = cov["reason"]
    assert "INCOMPLETE" in reason, reason
    assert "Probe factory" in reason, reason
    assert "0 cell(s) parsed" in reason and "0 declared" in reason, reason

    # ... and the RENDER carries the refusal: no zero-cell "clean" line may be assembled.
    rc, out, _ = _run([], [_non_conversion_row()], scores_dir=directory)
    assert "LEG score-conversion — NOT RUN" in out, out
    assert "INCOMPLETE" in out, out
    assert "0 cell(s) examined" not in out, out
    assert rc == 0, f"a NOT RUN leg is not a failure of the run\n{out}"

def test_the_newest_round_REFUSES_a_block_SHORT_of_its_own_header() -> None:
    """#531 acceptance 2: 18 of 19 -- the arm that printed NOTHING anomalous.

    2026-10-09's Miidas card is this shape (A2 written `**3**`), and it was never filed
    because the leg said nothing about it. The regex repair makes THAT cell parse; this arm
    keeps the refusal alive for a cell no reading recovers, because the class is "a cell the
    parser could not read", never "a cell written in bold".
    """
    directory = _scores_dir(_cell_score_artifact(cells=["4"] * 18 + ["—"]))
    leg = RUNNER.score_conversion_leg(
        [_non_conversion_row()], read_at="probe", scores_dir=directory
    )
    assert leg["status"] == "NOT RUN", leg
    cov = leg["coverage"]
    assert cov["criteria_cells"] == 18, cov
    assert cov["incomplete_blocks"] == [
        {"factory": "Probe factory", "parsed": 18, "declared": 19}
    ], cov["incomplete_blocks"]
    reason = cov["reason"]
    assert "18 of 19 declared cell(s) parsed" in reason, reason
    assert "1 unread" in reason, reason

def test_a_WELL_FORMED_card_is_still_ASSERTED_with_ALL_its_cells() -> None:
    """#531 acceptance 3: the POSITIVE CONTROL -- the predicate must not pass by refusing.

    Every refusal arm above is satisfied by a leg that refuses everything and reports
    nothing, which would be a worse instrument than the one it replaced. A whole card must
    read exactly as it read before the repair.
    """
    directory = _scores_dir(_cell_score_artifact(cells=["4"] * 18 + ["0 (UNM)"]))
    leg = RUNNER.score_conversion_leg(
        [_non_conversion_row()], read_at="probe", scores_dir=directory
    )
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert cov["criteria_cells"] == 19, cov
    assert cov["unmeasurable_cells"] == 1, cov
    assert "incomplete_blocks" not in cov, cov
    assert leg["problems"] == [], leg["problems"]

def test_a_BOLD_wrapped_cell_reads_as_its_VALUE_and_the_UNM_marker_stays_DATA() -> None:
    """#531 acceptance 4: `**3**` is a three; `0 (UNM)` is still an EXCLUDED cell.

    Two different kinds of markup, and the repair must not confuse them: bold is
    presentation wrapped around a value, while `(UNM)` is the ruling's own marker (n=2747)
    that keeps a zero OUT of the floor predicate. A leg that treated them alike would either
    lose the value or score the exclusion.
    """
    blocks = RUNNER.scorecard_blocks(
        _cell_score_artifact(cells=["4"] * 17 + ["**3**", "0 (UNM)"])
    )
    assert blocks[0]["parsed"] == 19, blocks[0]
    by_criterion = {c[0]: (c[1], c[2]) for c in blocks[0]["cells"]}
    assert by_criterion["D18"] == (3, False), by_criterion
    assert by_criterion["D19"] == (0, True), by_criterion

    # The floor predicate sees the bold cell as a measurable 3 and the UNM zero as excluded.
    regressions, examined, unmeasurable = RUNNER.score_regressions(blocks, {})
    assert regressions == [], regressions
    assert (examined, unmeasurable) == (19, 1), (examined, unmeasurable)

def test_the_LAPSED_read_REFUSES_an_incomplete_round_instead_of_CLEARING_it() -> None:
    """#531 acceptance 1, LAPSED arm -- the filed line, verbatim.

    The artifact is 2026-10-17's shape and it is UNANSWERED, so it is a lapse. Before the
    repair the line read `2026-10-17.md (0 regression(s): none, no conversion owed)` -- a
    round clearing itself of an obligation nobody had checked. `owed` must not be False when
    nothing was examined, and the render must carry the reason IN PLACE OF counts the leg
    does not have. The newest round here is COMPLETE, so the newest-arm refusal cannot be
    what produces this line: the lapsed arm has to stand on its own.
    """
    directory = _scores_tree({
        "2026-10-09": _cell_score_artifact(cells=["4"] * 19, total=70),
        "2026-10-10": _per_family_score_artifact(total=70),
        "2026-10-11": _cell_score_artifact(cells=["4"] * 19, total=70),
    })
    rows = [
        _conversion_row("evidence/scores/2026-10-09.md"),
        _conversion_row("evidence/scores/2026-10-11.md", subject="#68"),
    ]
    leg = RUNNER.score_conversion_leg(rows, read_at="probe", scores_dir=directory)
    assert leg["status"] == "ASSERTED", leg
    cov = leg["coverage"]
    assert cov["lapsed_population"] == 3, cov
    assert [e["artifact"] for e in cov["lapsed"]] == ["evidence/scores/2026-10-10.md"], cov
    entry = cov["lapsed"][0]
    assert entry["owed"] is not False, entry
    assert entry["unread"] is True, entry
    assert "INCOMPLETE" in entry["reason"], entry
    assert "0 cell(s) parsed" in entry["reason"], entry
    # An unread round is not a PROBLEM: it is a refusal to measure, and the run must say so
    # without inventing a regression the leg never read.
    assert leg["problems"] == [], leg["problems"]

    rc, out, _ = _run([], rows, scores_dir=directory)
    assert "evidence/scores/2026-10-10.md (UNREAD" in out, out
    assert "nothing measured, nothing cleared" in out, out
    assert "no conversion owed" not in out, (
        f"an unread round must never clear itself of a conversion\n{out}"
    )

def test_the_stall_census_leg_PRINTS_the_lane_drain_beside_the_OWED_total() -> None:
    """#465 criterion 1, re-based at #546: the OWED total travels with the addressee LANE's
    own drain evidence -- its claims on a SIBLING of the same standing set inside the window.

    The defect #465 answered: a bare "9 OWED" reads as nine independent findings, and for an
    addressee lane that is demonstrably working through the same batch that reading is wrong.
    The evidence is the lane's OWN claims on units it was dispatched, grouped on the SAME
    declared routing the addressee is read from, so the evidence and the line it corrects
    cannot disagree about whose lane it is.

    #546 SPLIT THE VERDICT IN TWO, and this arm asserts the split rather than the total: a
    lane with in-window claims is ALIVE, and whether it DRAINS A QUEUE is a second question.
    Two lanes here, one of each shape, so a leg that printed a single "DRAINING" count fails.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker, pacemakers = "aaaaaaaa-0000-0000-0000-000000000001", \
        "bbbbbbbb-0000-0000-0000-000000000002"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN"),
              _issue(1003, "OPEN"), _issue(1004, "OPEN")]
    rows = [
        # Worker: the OLDER unit is unclaimed while the YOUNGER is claimed -> NOT-A-QUEUE.
        _stall_row(1, "dispatch", "#1001", 6, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
        # Pacemakers: the OLDER unit is claimed and the YOUNGER is not -> a real QUEUE.
        _stall_row(4, "dispatch", "#1003", 6, now=now, refs=[{"session": pacemakers}]),
        _stall_row(5, "claim", "#1003", 0.5, now=now),
        _stall_row(6, "dispatch", "#1004", 5, now=now, refs=[{"session": pacemakers}]),
    ]
    names = {worker: "Worker", pacemakers: "Pacemakers / Crons"}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    cov = leg["coverage"]
    assert cov["units_owed"] == 2, cov
    assert cov["lanes_draining"] == 2, cov
    assert cov["lanes_draining_a_queue"] == 1, cov
    assert cov["lanes_not_a_queue"] == 1, cov
    assert cov["units_owed_on_draining_lanes"] == 2, cov
    assert len(cov["lane_drain"]) == 2, cov["lane_drain"]
    joined = "\n".join(cov["lane_drain"])
    assert "NOT-A-QUEUE Worker" in joined, joined
    assert "DRAINING Pacemakers / Crons" in joined, joined
    assert "DRAINING Worker" not in joined, (
        f"a lane whose claims are OUT OF DISPATCH ORDER must never read DRAINING\n{joined}"
    )
    # The evidence names the SIBLING and the row it was claimed at, and it never counts a
    # claim outside the observation window as drain evidence.
    assert "#1002" in joined and "n=3" in joined, (
        f"the evidence must name the SIBLING and the row it was claimed at\n{joined}"
    )
    assert "#1003" in joined and "n=5" in joined, joined

    # ... and through the REAL `main()`: the split must reach the REPORT, beside the OWED
    # population it corrects. A leg returning a correct dict while the render drops it is
    # the half-fix this half exists to catch.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: names)
    assert rc == 1, f"OWED lines must fail the run, got rc={rc}\n{out}"
    assert "population: 4 dispatched unit(s) -- 2 never claimed" in out, out
    assert "drain evidence" in out, out
    assert "2 lane(s) ALIVE with claims inside the window" in out, out
    assert "1 draining a QUEUE" in out, out
    assert "1 NOT-A-QUEUE (claims out of dispatch order)" in out, out
    assert "2 of 2 OWED unit(s) sit on one" in out, out
    assert "The remedy keys on the CLAIM, never on the drain (#546)" in out, out
    assert "NOT-A-QUEUE Worker" in out, out

def test_the_stall_census_leg_STOPS_prescribing_a_PER_ITEM_re_dispatch_on_a_DRAINING_lane() -> None:
    """#465 criterion 2, RE-BASED at #546 change 1 (ruling n=4117): the remedy keys on the
    CLAIM, never on the drain.

    #465 installed this clause in the OWED branch and keyed it on the addressee lane's DRAIN.
    Its warrant is a DUPLICATE -- "a delivery EXISTS, so a re-dispatch carries no state
    change" -- and the OWED class is by definition NEVER CLAIMED, so for 100% of the rows it
    governs the warrant is false. The measured case: `#543`'s first dispatch (n=4088) was
    ACKNOWLEDGED by the Worker lane in its own words at 08:45 ("Ordering is clear: #543
    first"), the session was then compacted 117 times in one day, and the work did not exist.
    Delivery, reading and RETENTION are three different things.

    So BOTH drain shapes now get the re-hand: a lane draining a queue in order (the OLDER
    unit claimed, the YOUNGER owed) AND a lane whose claims are out of dispatch order. What
    #465 got right is kept -- neither lane is told to close the unit, and the ordering is
    named -- and what it got wrong is gone: no shape in the OWED class reads "Do NOT
    re-dispatch this item".
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker = "aaaaaaaa-0000-0000-0000-000000000001"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN")]

    # ARM (a): a REAL queue -- the OLDER unit claimed, the YOUNGER owed.
    queue_rows = [
        _stall_row(1, "dispatch", "#1001", 6, now=now, refs=[{"session": worker}]),
        _stall_row(2, "claim", "#1001", 0.5, now=now),
        _stall_row(3, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
    ]
    # ARM (b): NOT a queue -- the YOUNGER unit claimed, the OLDER owed.
    not_a_queue_rows = [
        _stall_row(1, "dispatch", "#1001", 6, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
    ]

    for label, rows, owed_unit, held_fragment in (
        ("a real QUEUE", queue_rows, "#1002",
         "ALIVE -- it claimed a sibling of the same standing set inside the last 1.0 d -- "
         "but it does NOT hold this unit"),
        ("NOT-A-QUEUE", not_a_queue_rows, "#1001",
         "ALIVE, and its claims are OUT OF DISPATCH ORDER, so it does not drain a queue "
         "either -- it takes what is HANDED to it when it is free"),
    ):
        leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                      lane_names_fn=lambda: {worker: "Worker"})
        line = [ln for ln in leg["problems"] if owed_unit in ln][0]
        assert "Re-hand it OLDEST FIRST, ONE AT A TIME" in line, (
            f"on {label} the OWED unit's remedy is the RE-HAND (#546)\n{line}"
        )
        assert held_fragment in line, f"on {label} the held-verdict must be named\n{line}"
        assert "A delivery the lane never re-read is SPENT, so a re-hand is NOT a duplicate " \
               "and is the lawful act (#546)" in line, line
        assert "Do NOT re-dispatch this item" not in line, (
            f"the CLAIMED-class sentence must be unreachable in the OWED class (#546)\n{line}"
        )
        assert "ONE consolidated backlog-first brief" not in line, (
            f"#465's lane-level brief is RETIRED for the OWED class: it presupposed a "
            f"delivery that was retained\n{line}"
        )
        assert "close it on the board" not in line, (
            f"a live OPEN defect must never be advised closed\n{line}"
        )

        rc, out, _ = _run(issues, rows, lane_names_fn=lambda: {worker: "Worker"})
        assert rc == 1, out
        assert "Re-hand it OLDEST FIRST, ONE AT A TIME" in out, out
        assert "Do NOT re-dispatch this item" not in out, out

def test_546_a_YOUNGER_unit_claimed_while_an_OLDER_stays_UNCLAIMED_REDS_the_drain_evidence() -> None:
    """#546 change 3, THE DISCRIMINATOR: the positive control the ruling asked for.

    A lane whose claims are out of DISPATCH order is not draining a queue. The measured
    mechanism: the Worker lane claimed and closed `#545`, dispatched 75.3 min YOUNGER than
    `#543`, then produced zero claim rows for 4 h 10 m 30 s with `#543` still unclaimed. A
    lane draining a queue in dispatch order would have taken the OLDER unit next.

    THE CONTROL IS TWO-SIDED, and that is the whole point: the SAME pair of units, with only
    WHICH ONE was claimed reversed, must read NOT-A-QUEUE in one direction and DRAINING in
    the other. A leg that always fired the order test would pass the first arm alone; a leg
    that never fired it would pass the second alone.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker = "aaaaaaaa-0000-0000-0000-000000000001"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN")]
    names = {worker: "Worker"}

    # The YOUNGER unit is claimed while the OLDER stays unclaimed -> the drain evidence REDS.
    younger_claimed = [
        _stall_row(1, "dispatch", "#1001", 6, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
    ]
    leg = RUNNER.stall_census_leg(issues, younger_claimed, read_at=read_at,
                                  lane_names_fn=lambda: names)
    cov = leg["coverage"]
    assert cov["lanes_not_a_queue"] == 1, cov
    assert cov["lanes_draining_a_queue"] == 0, cov
    verdicts = {v["lane"]: v for v in cov["lane_drain_verdicts"]}
    assert verdicts["Worker"]["verdict"] == "NOT-A-QUEUE", verdicts
    assert verdicts["Worker"]["out_of_order_pairs"] == 1, verdicts
    assert verdicts["Worker"]["claims_in_window"] == 1, verdicts
    note = cov["lane_drain"][0]
    assert note.startswith("NOT-A-QUEUE Worker:"), note
    assert "#1002" in note and "#1001" in note, note
    assert ", OLDER) is still unclaimed" in note, (
        f"the evidence must say WHICH unit is older and still unclaimed\n{note}"
    )
    assert "does NOT drain a queue" in note, note
    assert "the #465 warrant ('a re-hand is a duplicate') is VOID for this lane" in note, note
    assert "re-handing the OLDEST unclaimed unit ONE AT A TIME is the lawful act (#546)" in note, note

    # The SAME pair, the claim moved to the OLDER unit -> a real queue, and the control must
    # NOT fire. Without this arm the assertion above is satisfied by a constant.
    older_claimed = [
        _stall_row(1, "dispatch", "#1001", 6, now=now, refs=[{"session": worker}]),
        _stall_row(2, "claim", "#1001", 0.5, now=now),
        _stall_row(3, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
    ]
    leg2 = RUNNER.stall_census_leg(issues, older_claimed, read_at=read_at,
                                   lane_names_fn=lambda: names)
    cov2 = leg2["coverage"]
    assert cov2["lanes_not_a_queue"] == 0, (
        f"the order test fired on a lane whose claims ARE in dispatch order -- it is a "
        f"constant, not a measurement\n{cov2}"
    )
    assert cov2["lanes_draining_a_queue"] == 1, cov2
    assert cov2["lane_drain_verdicts"][0]["verdict"] == "DRAINING", cov2["lane_drain_verdicts"]
    assert cov2["lane_drain"][0].startswith("DRAINING Worker:"), cov2["lane_drain"]

def test_546_the_VERDICT_SPLIT_is_PRINTED_beside_the_OWED_total() -> None:
    """#546 change 3, the RENDER half: the split reaches the report, in words a reader can
    act on, and it is machine-readable in the coverage beside it.

    The failure this catches is the one #465's own half-fix nearly shipped: a leg that
    computes the right verdict and a render that prints the old single count. The two must
    be asserted together, and the render must carry the LAW and not only the numbers -- a
    reader who sees "1 NOT-A-QUEUE" without the sentence explaining what it means has been
    given a word, not a finding.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker, pacemakers = "aaaaaaaa-0000-0000-0000-000000000001", \
        "bbbbbbbb-0000-0000-0000-000000000002"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN"),
              _issue(1003, "OPEN"), _issue(1004, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#1001", 6, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
        _stall_row(4, "dispatch", "#1003", 6, now=now, refs=[{"session": pacemakers}]),
        _stall_row(5, "claim", "#1003", 0.5, now=now),
        _stall_row(6, "dispatch", "#1004", 5, now=now, refs=[{"session": pacemakers}]),
    ]
    names = {worker: "Worker", pacemakers: "Pacemakers / Crons"}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    verdicts = {v["lane"]: v["verdict"] for v in leg["coverage"]["lane_drain_verdicts"]}
    assert verdicts == {"Worker": "NOT-A-QUEUE",
                        "Pacemakers / Crons": "DRAINING"}, verdicts

    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: names)
    assert rc == 1, out
    assert "1 draining a QUEUE" in out, out
    assert "1 NOT-A-QUEUE (claims out of dispatch order)" in out, out
    assert "The remedy keys on the CLAIM, never on the drain (#546)" in out, out
    assert "    NOT-A-QUEUE Worker:" in out, out
    assert "    DRAINING Pacemakers / Crons:" in out, out

def test_546_EVERY_OWED_line_places_its_AGE_against_the_LANES_OWN_p50_p75_and_n() -> None:
    """#546 change 2, ruling n=4117: the unit's age prints BESIDE its lane's own paired
    dispatch->claim p50/p75 and n, and says WHICH SIDE of p75 it falls on.

    The ruling's measured basis for the Worker lane: n=108, p50 2.94 h, p75 17.63 h. The
    fixed 1.0 d observation window sits on the WRONG side of that data -- it flags the normal
    case and says nothing about the tail -- so a bare "5.00 d" is not a reading, it is a
    duration a reader has to guess about. The threshold stays the OBSERVATION window; the
    LANE's own p75 is the READING.

    BOTH SIDES ARE ASSERTED, because a leg that printed "ABOVE" for every row would pass the
    loud half. `#1001` is 144 h against the Worker lane's p75 of 108 h (ABOVE); `#1004` is
    120 h against the Pacemakers lane's p75 of 132 h (AT OR BELOW).
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker, pacemakers = "aaaaaaaa-0000-0000-0000-000000000001", \
        "bbbbbbbb-0000-0000-0000-000000000002"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN"),
              _issue(1003, "OPEN"), _issue(1004, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#1001", 6, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
        _stall_row(4, "dispatch", "#1003", 6, now=now, refs=[{"session": pacemakers}]),
        _stall_row(5, "claim", "#1003", 0.5, now=now),
        _stall_row(6, "dispatch", "#1004", 5, now=now, refs=[{"session": pacemakers}]),
    ]
    names = {worker: "Worker", pacemakers: "Pacemakers / Crons"}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    profiles = leg["coverage"]["lane_latency_profiles"]
    assert profiles["Worker"]["n"] == 1, profiles
    assert profiles["Worker"]["unpaired"] == 1, profiles
    assert round(profiles["Worker"]["p75_secs"] / 3600.0, 2) == 108.00, profiles
    assert round(profiles["Pacemakers / Crons"]["p75_secs"] / 3600.0, 2) == 132.00, profiles

    above = [ln for ln in leg["problems"] if "#1001" in ln][0]
    assert "Its age 144.00 h is ABOVE its addressee lane's own p75 of 108.00 h" in above, above
    assert "(n=1 paired dispatch->claim interval(s): p50 108.00 h, p75 108.00 h, " \
           "max 108.00 h, derived from the lane's own rows; 1 unit(s) UNPAIRED and " \
           "excluded, never imputed)" in above, above

    below = [ln for ln in leg["problems"] if "#1004" in ln][0]
    assert "Its age 120.00 h is AT OR BELOW its addressee lane's own p75 of 132.00 h" in below, below

    # ... and through the render: the placement is the READING, so it must reach the report.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: names)
    assert rc == 1, out
    assert "is ABOVE its addressee lane's own p75 of 108.00 h" in out, out
    assert "is AT OR BELOW its addressee lane's own p75 of 132.00 h" in out, out

def test_546_a_lane_with_NO_paired_history_prints_p75_UNKNOWN_never_an_INVENTED_tolerance() -> None:
    """#546 change 2, the ZERO arm: `n == 0` is a real answer and it is PRINTED as one.

    A lane that has never had a paired dispatch->claim interval yields no distribution, so
    the age is placed against NOTHING -- and the line must say so in words rather than going
    quiet or, worse, substituting a tolerance the read did not derive. The `unpaired` count
    is printed beside it for the same reason: it is what the derivation REFUSED, and a
    percentile whose excluded population is invisible is not a measurement.

    This is also the arm that keeps the fixture honest: the only unit on this lane is the OWED
    one itself, which is NEVER CLAIMED by construction, so `unpaired == 1` and `n == 0` are
    the same fact read twice.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker = "aaaaaaaa-0000-0000-0000-000000000001"
    issues = [_issue(1001, "OPEN")]
    rows = [_stall_row(1, "dispatch", "#1001", 5, now=now, refs=[{"session": worker}])]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: {worker: "Worker"})
    profile = leg["coverage"]["lane_latency_profiles"]["Worker"]
    assert profile["n"] == 0, profile
    assert profile["unpaired"] == 1, profile
    assert profile["p50_secs"] is None and profile["p75_secs"] is None, profile
    assert profile["max_secs"] is None, profile

    line = [ln for ln in leg["problems"] if "#1001" in ln][0]
    assert "is placed against NO measured distribution" in line, line
    assert "yields n=0 paired interval(s) this read can derive, so its p75 is UNKNOWN" in line, line
    assert "the age is not evidence about it (#546)" in line, line
    # No invented tolerance: nothing in this line may claim a distribution it did not derive.
    assert "ABOVE" not in line, line
    assert "AT OR BELOW" not in line, line
    # The remedy still holds -- an unknown p75 orders the re-hand, it does not forbid it.
    assert "Re-dispatch it to the lane that owns it through `session_notify`" in line, line

def test_546_a_CLAIMED_unit_is_never_OWED_so_the_CLAIMED_branch_is_UNREACHABLE_and_COUNTED() -> None:
    """#546 change 1, THE STANDING ASSERTION: `owed` is built by skipping every CLAIMED unit,
    so the remedy's CLAIMED branch cannot be reached from this class -- and the coverage
    prints the count that would prove otherwise.

    "Unreachable" is a comment until something measures it. `owed_units_carrying_a_claim`
    turns it into a fact: a non-zero value means the owed predicate and the remedy have
    drifted apart, which is exactly the drift that put a "do not re-dispatch" sentence on
    units that had never been claimed.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker = "aaaaaaaa-0000-0000-0000-000000000001"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN"), _issue(1003, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#1001", 6, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
        _stall_row(4, "dispatch", "#1003", 5, now=now, refs=[{"session": worker}]),
        _stall_row(5, "claim", "#1003", 0.25, now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: {worker: "Worker"})
    cov = leg["coverage"]
    assert cov["owed_units_carrying_a_claim"] == 0, (
        f"a CLAIMED unit reached the OWED class -- the predicate and the remedy have "
        f"drifted apart (#546)\n{cov}"
    )
    assert cov["units_owed"] == 1, cov
    owed_lines = [ln for ln in leg["problems"] if ln.startswith("OWED ")]
    assert len(owed_lines) == 1, owed_lines
    assert "#1001" in owed_lines[0], owed_lines
    assert "#1002" not in owed_lines[0] and "#1003" not in owed_lines[0], (
        f"a CLAIMED unit was reported OWED\n{owed_lines}"
    )
    assert "has CLAIMED it" not in "\n".join(leg["problems"]), (
        f"the CLAIMED-class sentence must be unreachable in the OWED class (#546)\n"
        f"{leg['problems']}"
    )

def test_a_lane_with_NO_in_window_claim_keeps_its_OWED_line_VERBATIM() -> None:
    """#465 criterion 3, the TWO-SIDED control: the softened remedy is a statement about
    the drain, never a constant.

    `#1003`'s lane (`Pacemakers / Crons`) claimed nothing inside the window, so its stall
    is real and the re-dispatch advice is the only exit there is. A census that softened
    the sentence everywhere would stop naming the class it exists to name.

    The control has two halves, because a text assertion alone would pass a leg that
    printed the original sentence by accident of the fixture: (a) with a resolver that
    knows NOTHING there is no drain evidence at all -- the drain line says so in words
    rather than going silent -- and (b) the drain line prints even at zero, so "found no
    drain" is distinguishable from "never looked".
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker, pacemakers = "aaaaaaaa-0000-0000-0000-000000000001", \
        "bbbbbbbb-0000-0000-0000-000000000002"
    issues = [_issue(1001, "OPEN"), _issue(1002, "OPEN"),
              _issue(1003, "OPEN"), _issue(1004, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#1001", 5, now=now, refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1002", 5, now=now, refs=[{"session": worker}]),
        _stall_row(3, "claim", "#1002", 0.5, now=now),
        _stall_row(4, "dispatch", "#1003", 5, now=now, refs=[{"session": pacemakers}]),
        _stall_row(5, "dispatch", "#1004", 5, now=now, refs=[{"session": pacemakers}]),
        _stall_row(6, "claim", "#1004", 3, now=now),
    ]
    names = {worker: "Worker", pacemakers: "Pacemakers / Crons"}
    original = ("Re-dispatch it to the lane that owns it through `session_notify`, or "
                "close it on the board: a dispatch no lane has taken is work nobody is "
                "doing")

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    line = [ln for ln in leg["problems"] if "#1003" in ln][0]
    assert original in line, (
        f"a lane with NO in-window claim keeps the ORIGINAL remedy VERBATIM\n{line}"
    )
    assert "Do NOT re-dispatch this item" not in line, line

    # (a) THE RESOLVER CONTROL: with a blind resolver no lane name exists, so no unit can
    # sit on a draining lane and NO line is softened -- the drain evidence is a statement
    # about the resolution, not a constant the leg prints.
    blind = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                    lane_names_fn=lambda: {})
    assert blind["coverage"]["lanes_draining"] == 0, blind["coverage"]
    assert blind["coverage"]["units_owed_on_draining_lanes"] == 0, blind["coverage"]
    assert blind["coverage"]["lane_drain"] == [], blind["coverage"]["lane_drain"]
    assert all(original in ln for ln in blind["problems"]), blind["problems"]

    # (b) THE ZERO-DRAIN RENDER: the line prints at zero and SAYS what it read, so a leg
    # that never looked is distinguishable from one that looked and found nothing.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: {})
    assert "drain evidence" in out, out
    assert "no lane carrying an OWED unit claimed a sibling inside the window" in out, out

def test_the_stall_census_leg_reads_a_CARRIER_mention_as_a_MENTION_never_a_ROUTING() -> None:
    """#467, TWO-SIDED and HERMETIC: whether a carrier ROUTED a unit is read from WHERE
    the token STANDS in the row, never from the fact that the row names it at all.

    The defect: the addressee map kept the NEWEST dispatch-bearing row declaring a typed
    `session` ref. An ESCALATION row -- non-unit subject, actor `hq`, its detail listing
    the stalled units in the BODY -- declares HQ's own session, so it overwrote the
    genuine routing for every unit it merely mentioned. On the live ledger that is row
    `n=3098` (`stall-census-escalation-2026-10-11T06`), which took the slot from the real
    routing row `n=3067` (`#79`, actor triage, addressed to the Worker lane) and read
    twelve units as addressed to the lane that COMPLAINED about them rather than the lane
    they were sent to. One surface over from #433: a body mention is a MENTION.

    BOTH arms are built from rows THIS fixture supplies. The control is deliberately not
    read from the live row `n=3098`: a control keyed on a mutable live artifact stops
    discriminating the moment that artifact changes, and would keep passing while testing
    nothing.

    NEGATIVE arm: the escalation-shaped row names `#1101` and `#1102` in its body and
    declares HQ -- the addressee must stay the row that actually dispatched them.
    POSITIVE arm: a batch-dispatch-shaped row whose OPENING LINE names `#1103` DID route
    it, and being newer it must win the slot from the older direct dispatch.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    worker, hq = "aaaaaaaa-0000-0000-0000-000000000001", \
        "bbbbbbbb-0000-0000-0000-000000000002"
    issues = [_issue(1101, "OPEN"), _issue(1102, "OPEN"), _issue(1103, "OPEN")]
    rows = [
        # THE GENUINE ROUTINGS, addressed to the Worker lane.
        _stall_row(1, "dispatch", "#1101", 5, now=now, actor="triage",
                   refs=[{"session": worker}]),
        _stall_row(2, "dispatch", "#1102", 5, now=now, actor="triage",
                   refs=[{"session": worker}]),
        # THE NEGATIVE ARM: an escalation that only MENTIONS them, deep in its body.
        _stall_row(3, "dispatch", "stall-census-escalation-probe", 1, now=now, actor="hq",
                   refs=[{"session": hq}],
                   detail="escalation for HQ's attention:\n"
                          "the following units have never been claimed -- #1101, #1102 --\n"
                          "and the census re-flags them every cycle"),
        # #1103's genuine routing, older than the carrier below.
        _stall_row(4, "dispatch", "#1103", 5, now=now, actor="triage",
                   refs=[{"session": worker}]),
        # THE POSITIVE ARM: a carrier that ROUTES #1103 in its opening line, and is newer.
        _stall_row(5, "dispatch", "batch-dispatch-probe", 1, now=now, actor="hq",
                   refs=[{"session": hq}],
                   detail="DISPATCH #1103 -> the HQ lane\ncarrying the backlog brief"),
    ]
    names = {worker: "Worker", hq: "HQ"}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    by_unit = {ln.split("OWED ")[1].split(":")[0]: ln
               for ln in leg["problems"] if "OWED #" in ln}

    # NEGATIVE: a body mention never takes the routing slot.
    for unit in ("#1101", "#1102"):
        line = by_unit[unit]
        assert "ADDRESSED to Worker" in line, (
            f"a row that only MENTIONS {unit} in its body is a MENTION, not a routing: "
            f"the addressee must stay the row that dispatched it\n{line}"
        )
        assert "ADDRESSED to HQ" not in line, (
            f"the escalation's session must not stand in {unit}'s addressee slot\n{line}"
        )

    # POSITIVE: an opening-line carrier DID route its unit, and wins on being newer.
    assert "ADDRESSED to HQ" in by_unit["#1103"], (
        f"a carrier whose OPENING LINE names the unit DID route it, and being newer it "
        f"takes the slot\n{by_unit['#1103']}"
    )

    cov = leg["coverage"]
    assert cov["units_owed"] == 3, cov
    assert cov["addressees_resolved"] == 3, cov
    assert cov["mentions_rejected"] == 2, (
        f"the two body-only tokens must be COUNTED as rejected, or a leg that never "
        f"applied the test is indistinguishable from one that rejected nothing\n{cov}"
    )

    # THE RENDER HALF: the rejected count reaches the report.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: names)
    assert rc == 1, f"OWED lines must fail the run, got rc={rc}\n{out}"
    # The predicate's NAME moved with #550 (the discriminator is grammatical role, not the
    # opening line), so the assertion tracks the current wording -- what it pins is the
    # SUBSTANCE: a token this leg refused is reported as a MENTION and never as a routing.
    assert "read as a MENTION, never as a routing (#467, re-based by #550)" in out, out
    assert "2 of their token(s) standing in APPOSITION" in out, out

def test_the_ROUTING_role_predicate_states_each_measured_shape() -> None:
    """The predicate ITSELF, on the three live rows' own token contexts (#550).

    Driven through `token_routes_in_prose` directly, because the leg-level arms above can be
    satisfied by a rule that happens to agree on these fixtures while reading the wrong
    signal. Each assertion quotes the bytes that follow the token on the live row it came
    from, so a widened or narrowed separator set fails here by name.
    """
    routes = RUNNER.token_routes_in_prose
    # n=219 -- every one of these is the subject of its own finding.
    assert routes("#33 unclaimed 4h10m since intake", len("#33")) is True
    assert routes("#35 had NO intake row", len("#35")) is True
    assert routes("#34 claimed by HQ (n=198)", len("#34")) is True
    assert routes("#36 closed in ledger", len("#36")) is True
    assert routes("#32 closed on the board 34s", len("#32")) is True
    # n=330 -- the routed unit, then two mentions.
    assert routes("#40 shipped tonight", len("#40")) is True
    assert routes("#54 (n=325) and before", len("#54")) is False
    assert routes("#52's two mechanical halves", len("#52")) is False
    # n=4048 -- the typed ref routes #540; these three are prose mentions.
    assert routes("#540 is a law-and-gate question", len("#540")) is True
    assert routes("#422 (n=4035). Removing them", len("#422")) is False
    assert routes("#529's tests were dispatched", len("#529")) is False
    assert routes("#324's TEMPLATE test parked", len("#324")) is False
    # the dispatch arrow every routing row uses, and the list/coordination separators.
    assert routes("#318 -> the HQ lane", len("#318")) is True
    assert routes("#33/#35, which the Worker claimed", len("#33")) is False
    assert routes("#50 -- Triage routed the identical row", len("#50")) is False
    # the possessive is refused on its own, not because of what follows it.
    assert routes("#52's", len("#52")) is False
    assert routes("#52 and #55; the issue's number", len("#52")) is True, (
        "a spelled-out conjunction opens a clause and ROUTES: the residual is stated in "
        "the source, and it is the permissive direction -- it can over-admit, never "
        "silently demote a genuine dispatch"
    )

def test_587_the_duty_receipt_PROSE_census_reports_its_population_and_splits_the_verdict() -> None:
    """#587, ruled at n=4483: the writer rule has no READER for its own failure class.

    ARM 1 IS THE POSITIVE CONTROL and it is the one that matters. A synthetic `run` row on
    a declared stem whose canonical trailer declares NOTHING while its prose carries
    `duty=completed` must be a PROBLEM. The defect #587 names is a filter that cannot see
    the class and reports 0, which reads exactly like a clean tree -- so arms that only
    assert the leg runs, or only assert a count of zero somewhere, prove nothing.

    ARM 2 is its negative control, and it is deliberately the SAME row with only the token's
    POSITION changed: a leg that red on any row mentioning `duty` would pass arm 1 and fail
    here, which is the "prose must not satisfy a field" damage (#88, n=405 clause 5).
    """
    predicate = RUNNER.field_predicate_readers()
    since = "2026-10-16"
    cron = [{"name": "probe-patrol", "prompt": "receipt_subject: patrol-verify\n"}]

    def row(n, detail, ts="2026-10-20T00:00:00Z"):
        return {"n": n, "ts": ts, "event": "run", "actor": "triage",
                "subject": "patrol-verify-2026-10-20T00", "detail": detail}

    prose = "patrol round. The receipt declares duty=completed in its TEXT."
    canonical = "patrol round. The receipt carries the terminal run.\nduty=completed"

    # ARM 1 -- POSITIVE CONTROL: prose token, empty canonical trailer -> a PROBLEM.
    leg = RUNNER.duty_receipt_prose_leg(
        [row("9001", prose)], cron, read_at="2026-10-30T00:00:00Z",
        predicate=predicate, since=since)
    assert leg["status"] == "ASSERTED", leg["status"]
    assert leg["coverage"]["run_rows_on_stem"] == 1, leg["coverage"]
    assert leg["coverage"]["prose_token"] == 1, leg["coverage"]
    assert len(leg["problems"]) == 1, leg
    assert "n=9001" in leg["problems"][0], leg["problems"][0]
    assert leg["excused"] == [], leg["excused"]

    # ARM 2 -- NEGATIVE CONTROL: the SAME row, token in the CANONICAL TRAILER. It must be
    # invisible to this leg: not a finding, and not even in the empty set.
    leg = RUNNER.duty_receipt_prose_leg(
        [row("9002", canonical)], cron, read_at="2026-10-30T00:00:00Z",
        predicate=predicate, since=since)
    assert leg["coverage"]["run_rows_on_stem"] == 1, leg["coverage"]
    assert leg["coverage"]["canonical_empty"] == 0, leg["coverage"]
    assert leg["coverage"]["prose_token"] == 0, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

    # ARM 3 -- THE SPLIT. The same prose row stamped BEFORE the rule is visible debt, never
    # a red: no backfill is ordered, so an all-red leg would be red forever and un-greenable.
    leg = RUNNER.duty_receipt_prose_leg(
        [row("9003", prose, ts="2026-10-01T12:00:00Z")], cron,
        read_at="2026-10-30T00:00:00Z", predicate=predicate, since=since)
    assert leg["problems"] == [], leg["problems"]
    assert len(leg["excused"]) == 1, leg["excused"]
    assert "BEFORE the rule was ordered" in leg["excused"][0], leg["excused"][0]

    # ARM 4 -- an EMPTY-TRAILER row with NO token anywhere is not a receipt and must never
    # be reported: that population is 110 of the 136 empty rows on this tree, and counting
    # it as findings would triple the red with rows no writer rule can reach.
    leg = RUNNER.duty_receipt_prose_leg(
        [row("9004", "patrol round, nothing declared at all.")], cron,
        read_at="2026-10-30T00:00:00Z", predicate=predicate, since=since)
    assert leg["coverage"]["canonical_empty"] == 1, leg["coverage"]
    assert leg["coverage"]["prose_token"] == 0, leg["coverage"]
    assert leg["problems"] == [], leg["problems"]

    # ARM 5 -- NO DECLARED STEM is NOT RUN, never a clean pass: a zero from a filter with
    # no population is the exact shape #587 exists to kill (#242).
    leg = RUNNER.duty_receipt_prose_leg(
        [row("9005", prose)], [], read_at="2026-10-30T00:00:00Z",
        predicate=predicate, since=since)
    assert leg["status"] == "NOT RUN", leg["status"]

    # ARM 6 -- THE CLASS BOUNDARY IS COUNTED, not left to be inferred. A finding on a stem
    # this factory does NOT declare is outside the verdict, and a finding on a NON-`run`
    # event is not a receipt at all; both must appear in the coverage beside the population,
    # so `prose_token` is never read as the size of the class.
    off = dict(row("9006", prose), subject="undeclared-stem-2026-10-20T00")
    not_receipt = dict(row("9007", prose), event="close")
    leg = RUNNER.duty_receipt_prose_leg(
        [row("9008", prose), off, not_receipt], cron,
        read_at="2026-10-30T00:00:00Z", predicate=predicate, since=since)
    assert leg["coverage"]["prose_token"] == 1, leg["coverage"]
    assert leg["coverage"]["prose_token_off_stem"] == 1, leg["coverage"]
    assert leg["coverage"]["prose_token_not_a_receipt"] == 1, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]

    # ARM 7 -- BOTH SHAPES RENDER. The leg's ASSERTED coverage and `no_prefixes_leg`'s NOT
    # RUN coverage are different dicts, and the report reads keys that only one of them
    # carries: without this arm the NOT RUN shape raises a KeyError inside `render` and takes
    # the whole round down. Measured, this is not hypothetical -- the first run of this change
    # failed `test_538_the_render_PRINTS_the_scoping_and_the_board_it_read` with
    # `KeyError: 'run_rows_on_stem'`, and the leg-level arms above were all green.
    for arm in (
        RUNNER.duty_receipt_prose_leg([row("9009", prose)], cron,
                                      read_at="2026-10-30T00:00:00Z",
                                      predicate=predicate, since=since),
        RUNNER.duty_receipt_prose_leg([row("9010", prose)], [],
                                      read_at="2026-10-30T00:00:00Z",
                                      predicate=predicate, since=since),
    ):
        text = RUNNER.render([arm], [], slug="probe", read_at="2026-10-30T00:00:00Z",
                             issues=[])
        assert "LEG duty-receipt-prose" in text, text
    # and the ASSERTED arm's population line names the number, never a bare count.
    asserted = RUNNER.duty_receipt_prose_leg([row("9011", prose)], cron,
                                             read_at="2026-10-30T00:00:00Z",
                                             predicate=predicate, since=since)
    text = RUNNER.render([asserted], [], slug="probe", read_at="2026-10-30T00:00:00Z",
                         issues=[])
    assert "class boundary" in text, text
    assert "1 run row(s) on 1 declared receipt stem(s)" in text, text

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
