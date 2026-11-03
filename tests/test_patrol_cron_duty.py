"""Gate: cron thinness and duty receipts — #121/#147

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
    _SESSION_UUID,
    _WAKE_PROMPT,
    _cron,
    _run,
    _thin,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _ledger_with(*subjects) -> Path:
    """A synthetic ledger in a temp dir — the guard is checked against DATA, not the live log."""
    path = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    path.write_text(
        "".join(
            json.dumps({"n": i + 1, "ts": _CLOSE_TS, "event": "close",
                        "actor": "worker", "subject": s, "detail": "probe"}) + "\n"
            for i, s in enumerate(subjects)
        ),
        encoding="utf-8",
    )
    return path

# --- this leg's tests -------------------------------------------------------
def test_the_cron_leg_RUNS_and_states_the_population_it_examined() -> None:
    """#121: the leg is wired, and every count it reports travels with its scope.

    Ownership is the manifest's DECLARATION, never the home a row sits in — all twelve
    ai-antispam rows sit in the OPS home, so a home-scoped read answers a narrower
    question than the one it names (#102).
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-measurement-daily", home="other-home"),
        _thin("sibling-triage-hourly-patrol", home="other-home"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      unreached=["gone-home: no opencrabs.db"], prefixes=["factory-"])
    assert rc == 0, out
    assert "LEG cron-thinness — ASSERTED" in out, (
        f"the leg is WIRED: it must render ASSERTED, never a deferred NOT RUN\n{out}"
    )
    assert "3 enabled read across 2 home(s)" in out, out
    assert "2 attributed to this factory (factory-)" in out, out
    assert "1 unattributed" in out, (
        f"a row nobody declares is COUNTED, and the count must be printed\n{out}"
    )
    assert "homes unreached: 1" in out, out
    assert "gone-home" in out, (
        f"an unreached home is REPORTED, never dropped — an unreachable home is not an "
        f"empty one\n{out}"
    )
    assert "read at " in out, f"the read instant must travel with the count\n{out}"

def test_the_cron_leg_fails_LOUDLY_when_nothing_is_attributed() -> None:
    """A clean verdict over an examined-nothing read is not a verdict (skill section 8).

    The declared prefix set is non-empty and NOTHING matches it, so the population the
    leg claims to judge came back empty — reported, never read as clean.
    """
    rows = [_thin("sibling-triage-hourly-patrol")]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 1, f"an empty attributed population must FAIL LOUDLY, got rc={rc}\n{out}"
    assert "population came back EMPTY" in out, out
    assert "0 cron row(s) attributed to this factory" in out, out

def test_an_unattributable_row_is_COUNTED_NAMED_and_never_judged() -> None:
    """A row this factory cannot attribute is COUNTED, NAMED, never judged.

    The second row carries a WORK ORDER on a waking session target — a real defect under
    the shared predicate — but nobody here declares it, so judging it would be this
    factory enforcing another factory's law.

    NAMED is the half that used to be forbidden here. A bare count is not a report: the
    name and the home it was read from are what let a reader resolve it, so the population
    read carries them (#126). The property this probe tests is the one it always claimed —
    the row is never JUDGED — and it still bites, because a row that reached the problems
    list would fail the second assertion.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _cron("sibling-some-other-factory-job", deliver_to=f"session:{_SESSION_UUID}",
              prompt="Execute the hourly cycle and write the report.", home="other-home"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      prefixes=["factory-"])
    assert rc == 0, f"an unattributable row must not fail this factory's run\n{out}"
    assert "1 unattributed" in out, out
    assert "    unattributed: sibling-some-other-factory-job (home other-home)" in out, (
        f"the population read must NAME every row it could not attribute, with the home "
        f"it was read from — a count alone resolves to no object and cannot be checked "
        f"by the reader it is reported to (#126)\n{out}"
    )
    judged = [line for line in out.splitlines() if line.startswith("    - ")]
    assert not any("sibling-some-other-factory-job" in line for line in judged), (
        f"the leg judges its OWN rows only — an unattributable row belongs in the "
        f"population read, never in this factory's problems\n{judged}\n{out}"
    )

def test_the_cron_leg_BITES_on_a_defect_in_a_row_this_factory_declares() -> None:
    """Non-vacuity: the wired leg must report a defect, not merely render a green line."""
    rows = [
        _thin("factory-triage-patrol"),
        _cron("factory-broken-pacemaker", deliver_to=f"session:{_SESSION_UUID}",
              prompt="Execute the 6-hourly cycle and write the report."),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 1, f"a work order on a waking row must fail the run, got rc={rc}\n{out}"
    assert "factory-broken-pacemaker" in out, out
    assert "work order" in out, out
    assert "2 cron row(s) attributed to this factory and judged" in out, (
        f"the verdict must state the judged population\n{out}"
    )

def test_the_law_content_class_NAMES_every_row_and_states_its_population() -> None:
    """#178: the class NAMES each row, never a bare count, and prints the population read.

    A count cannot be dispatched, claimed or closed; a named row can be all three (#148).
    The row below belongs to ANOTHER factory, and the leg still names it — because a
    per-factory scan would see none of the class's live instances and would report a clean
    verdict over the class it exists to catch (the #170/#177 family).
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("sibling-other-factory-window",
              prompt=_WAKE_PROMPT + " The window from the deploy (2026-09-24T11:33:19Z) "
                                   "has passed.", home="other-home"),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home", "other-home"],
                      prefixes=["factory-"])
    assert rc == 0, (
        f"another factory's row must not fail THIS factory's run — the class is reported "
        f"for rows this factory does not declare (#101)\n{out}"
    )
    assert "law-content scan: 2 row(s) examined" in out, (
        f"the population examined must be printed, so a clean verdict is distinguishable "
        f"from one that examined nothing\n{out}"
    )
    assert "law content: sibling-other-factory-window" in out, (
        f"the row must be NAMED, with the instant it embeds\n{out}"
    )
    assert "2026-09-24T11:33" in out, out

def test_the_law_content_class_BITES_on_a_row_this_factory_declares() -> None:
    """Non-vacuity: the class must FAIL the run when the row carrying it is ours."""
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-boundary-holder",
              prompt=_WAKE_PROMPT + " Pool-swap boundary: 2026-09-25T16:17:46Z. The pool is "
                                   "now model-a:free + model-b:free."),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 1, f"an embedded boundary on our own row must fail the run, got rc={rc}\n{out}"
    assert "factory-boundary-holder" in out, out
    assert "2026-09-25T16:17" in out, out
    assert "P7/P28" in out, (
        f"the finding must name the rule that would have prevented it, per #148 — the "
        f"repairer is named, not counted\n{out}"
    )

def test_a_bare_date_is_REPORTED_and_never_judged_so_the_exclusion_is_visible() -> None:
    """A bare date is a CITATION of the past, not state — printed, never judged.

    This is the half that keeps the exclusion checkable: a reader can see WHICH rows were
    set aside and why, instead of trusting a silent predicate.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-thin-exemplar",
              prompt=_WAKE_PROMPT + " This prompt is thin: it was 5,289 chars of pasted law "
                                   "on 2026-09-26, every word of which already lived in "
                                   "triage.md."),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 0, (
        f"a historical rationale carrying a bare date is not embedded state\n{out}"
    )
    assert "dated, not a boundary: factory-thin-exemplar" in out, (
        f"the row must be REPORTED with its date — an exclusion that prints nothing is "
        f"indistinguishable from a predicate that never looked\n{out}"
    )
    judged = [line for line in out.splitlines() if line.startswith("    - ")]
    assert not any("factory-thin-exemplar" in line for line in judged), (
        f"a bare date must never reach the problems list\n{judged}\n{out}"
    )

def test_the_negative_control_BITES_a_date_only_predicate_would_fire_on_the_exemplar() -> None:
    """The control is not vacuous, and this is the measurement that chose the predicate.

    Widening the class to a BARE DATE makes the box's best-shaped row a defect: the
    exemplar explains its own thinness using a date. A predicate that fires on the exemplar
    is one a reader learns to ignore, so the instant (date WITH a time) is the predicate and
    this probe is the evidence for it — it fails if the control cannot fire at all.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-thin-exemplar",
              prompt=_WAKE_PROMPT + " It was 5,289 chars of pasted law on 2026-09-26, every "
                                   "word of which already lived in triage.md."),
    ]
    saved = RUNNER.EMBEDDED_INSTANT_RE
    try:
        RUNNER.EMBEDDED_INSTANT_RE = RUNNER.BARE_DATE_RE
        rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
        assert rc == 1, (
            f"the control must BITE: a date-only predicate fires on the exemplar, which is "
            f"exactly why the shipped predicate is an INSTANT\n{out}"
        )
    finally:
        RUNNER.EMBEDDED_INSTANT_RE = saved
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 0, f"the shipped predicate must not fire on the exemplar\n{out}"

def test_an_instant_inside_a_CITATION_is_REPORTED_and_never_judged() -> None:
    """#478 ARM A — an instant that CITES a source record is a citation, not state.

    The box's own `factory-publish` prompt cites a ruling by its timestamp. The leg judged
    that instant as an embedded boundary and red the row, so the class fired on a prompt
    whose only sin is saying WHEN something was decided. The carve-out is the citation
    itself: a clause naming a source record and asserting no state word is REPORTED.

    Reported, not silently dropped — an exclusion that prints nothing is indistinguishable
    from a predicate that never looked, which is the defect one bucket over.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-publish",
              prompt="The pusher is fetched from origin/main and run with --repo, per "
                     "ruling n=3263 (issue #469, 2026-10-11T12:59:43Z)."),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 0, (
        f"an instant inside a citation is not embedded state\n{out}"
    )
    assert "instant in a citation: factory-publish" in out, (
        f"the row must be REPORTED with its instant — a carve-out that prints nothing is "
        f"a false clean one layer down\n{out}"
    )
    judged = [line for line in out.splitlines() if line.startswith("    - ")]
    assert not any("factory-publish" in line for line in judged), (
        f"a citation must never reach the problems list\n{judged}\n{out}"
    )

def test_the_citation_carve_out_CANNOT_swallow_a_real_boundary() -> None:
    """#478 ARM B — the carve-out is strictly NARROWER than the class it excuses.

    A clause can name a source record AND assert state: "per ruling n=3263 the boundary
    opens 2026-10-11T12:59:43Z" cites a ruling and states a window. If the carve-out keyed
    on the citation alone it would swallow that boundary, and the leg would stop seeing the
    one shape it exists to catch. The state word wins, so the instant stays JUDGED.

    This is the arm that makes ARM A safe: without it, ARM A proves only that the leg can
    stop looking.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-boundary-citer",
              prompt="Per ruling n=3263 the window opens 2026-10-11T12:59:43Z and every "
                     "row after it must declare its receipt."),
    ]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 1, (
        f"a citation that ALSO asserts a boundary must stay judged — the carve-out is a "
        f"citation predicate, not a licence\n{out}"
    )
    assert "factory-boundary-citer" in out, out
    assert "instant in a citation: factory-boundary-citer" not in out, (
        f"the row asserts state, so it must not be excused as a citation\n{out}"
    )

def test_the_citation_carve_out_MUTATION_control_reverting_it_reddens_ARM_A() -> None:
    """The control is not decorative: neuter the carve-out and ARM A's row must go RED.

    A probe that passes whether or not the mechanism exists proves nothing about the
    mechanism. Neuter `is_citation_instant` to the pre-#478 behaviour (no instant is ever a
    citation) and the same fixture that was green must fail — that is what makes ARM A
    evidence rather than decoration.
    """
    rows = [
        _thin("factory-triage-patrol"),
        _thin("factory-publish",
              prompt="The pusher is fetched from origin/main and run with --repo, per "
                     "ruling n=3263 (issue #469, 2026-10-11T12:59:43Z)."),
    ]
    saved = RUNNER.is_citation_instant
    try:
        RUNNER.is_citation_instant = lambda text, start: False
        rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
        assert rc == 1, (
            f"the control must BITE: with the carve-out neutered, the citation is judged "
            f"as an embedded boundary and the row goes red\n{out}"
        )
        assert "factory-publish" in out, out
    finally:
        RUNNER.is_citation_instant = saved
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"])
    assert rc == 0, f"the shipped predicate must excuse the citation again\n{out}"

def test_the_leg_binds_to_the_SHARED_predicate_and_the_shared_registry() -> None:
    """One predicate, one home — imported, never re-derived.

    A private copy would be self-consistent on both sides and the drift invisible: the
    class this factory has already ruled (n=405 clause 5, n=599).
    """
    assert RUNNER.CRON_THINNESS_PREDICATE == REPO / "tests" / "test_cron_thinness.py", (
        f"the leg must bind to the shared predicate, not {RUNNER.CRON_THINNESS_PREDICATE}"
    )
    predicate = RUNNER.load_module("cron_thinness_predicate", RUNNER.CRON_THINNESS_PREDICATE)
    assert callable(predicate.pacemaker_problems), "the shared entry point must exist"
    assert RUNNER.REGISTRY == REPO / "tools" / "registry.py", (
        f"the box read must use the registry the 6h-floor law already uses, "
        f"not {RUNNER.REGISTRY}"
    )
    assert hasattr(RUNNER, "DEFERRED_LEG_REASON") is False, (
        "the cron-thinness reason must be DELETED, not corrected — a corrected reason is "
        "still a hand-written claim about the tree that nothing re-checks"
    )

def test_nothing_is_deferred_now_that_the_cron_leg_is_wired() -> None:
    """Wiring the leg retires the REASON, and an empty list is the honest state."""
    assert RUNNER.deferred_legs() == [], (
        f"the cron-thinness leg is WIRED, so nothing may still be deferred: "
        f"{RUNNER.deferred_legs()}"
    )

def test_a_deferred_entry_with_a_CLOSED_tracker_is_reported() -> None:
    """THE BITE. A reader following a closed tracker lands on a settled item.

    This is the exact shape #121 found: the reason pointed at #54, and #54 had closed
    under it while every gate stayed green. The guard's live population is legitimately
    EMPTY, so THIS probe is the evidence that it bites (skill section 8).
    """
    entries = [{"name": "some-future-leg", "tracker": 54,
                "claims": [{"path": "tools/registry.py", "present": True}]}]
    problems = RUNNER.deferred_entry_problems(entries, ledger=_ledger_with("#54"))
    assert problems, "a CLOSED tracker must be reported"
    assert any("CLOSED" in p for p in problems), problems
    assert any("#54" in p for p in problems), problems

def test_a_deferred_entry_with_a_FALSE_claim_is_reported() -> None:
    """THE BITE, second arm: a stated reason must not outlive the tree it describes."""
    entries = [{"name": "some-future-leg", "tracker": 121,
                "claims": [{"path": "tools/registry.py", "present": True},
                           {"path": "tools/does-not-exist.py", "present": True}]}]
    problems = RUNNER.deferred_entry_problems(entries, ledger=_ledger_with())
    assert problems, "a claim the tree contradicts must be reported"
    assert any("tools/does-not-exist.py" in p for p in problems), problems

def test_a_truthful_deferral_reads_clean() -> None:
    """The complement: the guard is not a wall — a truthful entry is not a problem."""
    entries = [{"name": "some-future-leg", "tracker": 121,
                "claims": [{"path": "tools/registry.py", "present": True},
                           {"path": "tools/nope.py", "present": False}]}]
    assert RUNNER.deferred_entry_problems(entries, ledger=_ledger_with()) == [], (
        "a truthful deferral must read clean"
    )

def test_a_deferral_declaring_nothing_checkable_is_reported() -> None:
    """The CLOSED vocabulary is the point: free prose cannot be re-checked."""
    problems = RUNNER.deferred_entry_problems([{"name": "vague-leg", "reason": "later"}],
                                             ledger=_ledger_with())
    assert len(problems) >= 2, problems
    assert any("tracker" in p for p in problems), problems
    assert any("claims" in p for p in problems), problems

def test_the_guard_PRINTS_the_population_it_examined() -> None:
    """A guard that examined nothing must never print the verdict of one that did."""
    rc, out, _ = _run([], [])
    assert rc == 0, out
    assert "deferred entries examined: 0" in out, (
        f"the empty population must be PRINTED, so a clean read is never mistaken for a "
        f"checked one\n{out}"
    )

def test_the_runner_reads_the_repo_own_ledger_by_default() -> None:
    """The default path is this repo's own ledger, and every row it reads carries its `n`.

    A bootstrapped factory begins with an empty ledger, so the row assertions are made
    over whatever is there and the coverage is PRINTED — "0 rows read" and "584 rows
    read" must never render the same, and an absent ledger is stated rather than
    silently passing as a clean one.
    """
    ledger = RUNNER.LEDGER
    assert ledger == REPO / "evidence" / "ledger.jsonl", (
        f"the runner must default to this repo's ledger, not {ledger}"
    )
    if not ledger.is_file():
        print(f"  note: no ledger at {ledger} — this tree carries none to read")
        return
    rows = RUNNER.load_rows()
    assert all(isinstance(r.get("n"), int) for r in rows), "every row carries its n"
    print(f"  ledger read: {len(rows)} row(s) from {ledger}")

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
