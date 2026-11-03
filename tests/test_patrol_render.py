"""Gate: the render and the ref-role surface — #330

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
    _ROUTING_TS,
    _issue,
    _run,
    _score_artifact,
    _scores_dir,
    _scratch,
    _stall_row,
    _tier_row,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _routing_item(number: int, *, title: str = "scores(2026-10-29)",
                  created: str = "2026-10-28T00:00:00Z", state: str = "OPEN",
                  closed: str | None = None) -> dict:
    """A board item shaped like the `gh` read the leg consumes."""
    return {"number": number, "title": title, "state": state,
            "createdAt": created, "closedAt": closed}

def _probe_routed_row(n: int = 4449, *, board: str | None = "#600",
                ts: str = _ROUTING_TS) -> dict:
    """A conversion row at or after the routing epoch, carrying `board` as its only ref."""
    return {
        "n": n, "ts": ts, "event": "conversion", "actor": "worker", "subject": "#67",
        "detail": "converted_from=evidence/scores/2026-10-29.md",
        "refs": [{"board": board}] if board is not None else [],
    }

# --- this leg's tests -------------------------------------------------------
def test_the_ref_role_leg_reaches_the_RENDER_and_reds_the_run() -> None:
    """End to end: a receipt asserting the WRONG role for a row must red the round.

    The instance is #330's own, shrunk to two rows: a receipt says `intake row n=2` and
    n=2 is a close. Existence is satisfied — n=2 IS a row — which is exactly why the write
    path passed it; the ROLE is what the reader needs and what the leg judges.
    """
    rows = [
        _tier_row(1, "#900", "settled run=7 tier=T1", event="intake"),
        _tier_row(2, "#900", "CLOSE #900. Intake row n=2.", event="close"),
    ]
    rc, out, _ = _run([], rows)
    assert "LEG ledger-ref-roles" in out, out
    assert "UNRESOLVED" in out, out
    assert rc == 1, f"a wrong role assertion must red the run, got rc={rc}\n{out}"

def test_the_ref_role_leg_PRINTS_its_population_even_when_clean() -> None:
    """A leg that examined nothing and one that examined the corpus must never render alike.

    The negative half: a correct assertion reads clean, and the render still carries the
    counts — assertions examined, roles judged, mismatches, declared-exempt, unresolved.
    """
    rows = [
        _tier_row(1, "#900", "settled run=7 tier=T1", event="intake"),
        _tier_row(2, "#900", "CLOSE #900. Intake row n=1.", event="close"),
    ]
    rc, out, _ = _run([], rows)
    assert "LEG ledger-ref-roles" in out, out
    assert "1 examined over 2 ledger row(s)" in out, out
    assert "0 mismatch(es), 0 declared-exempt, 0 unresolved" in out, out
    # The rc is NOT asserted here: this fixture's board is empty while its rows name #900,
    # so the board-intake leg reds for a reason this probe is not about. What this probe
    # owns is that the ref-role leg contributes NO unresolved line of its own.
    assert "UNRESOLVED" not in out, out

def test_an_ABSENT_batch_declaration_RESOLVES_NOTHING_and_SAYS_SO() -> None:
    """#519 acceptance (2) and #271: a tree that has declared no batch act must report its
    population as OWED, and the absence must be VISIBLE — an absent declaration and a
    population with nothing owed must never render the same.

    This is the arm that makes the declaration safe to be absent: absence SKIPS the excuse,
    it never grants one. A leg that read an absent declaration as "no batches exist, so
    everything is resolved" would clear the whole population on no evidence at all.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(941, "OPEN")]
    rows = [_stall_row(41, "ruling", "#941", 2, now=now)]

    absent = RUNNER.undispatched_ruling_leg(
        issues, rows, read_at=read_at, batches={}, standing={},
        batch_refusal="ABSENT: no docs/ledger-invariants.json in this tree",
    )
    assert absent["coverage"]["items_owed_dispatch"] == 1, absent["coverage"]
    assert absent["coverage"]["batch_refusal"].startswith("ABSENT:"), absent["coverage"]

    # ... and the discriminating control: the SAME population, resolved by a declaration.
    # If both arms read the same, the assertion above proves nothing about the declaration.
    resolved = RUNNER.undispatched_ruling_leg(
        issues, rows, read_at=read_at,
        batches={"probe-batch": {"row": 41, "units": [941],
                                 "recorded_at": "2026-10-21T00:00:00Z", "basis": "probe"}},
        standing={},
    )
    assert resolved["coverage"]["items_owed_dispatch"] == 0, resolved["coverage"]
    assert resolved["coverage"]["items_resolved_by_batch"] == 1, resolved["coverage"]

def test_the_undispatched_ruling_leg_REFUSES_a_call_that_omits_the_declaration() -> None:
    """#557 acceptance (1) / ruling n=4197: omitting `batches` is a TypeError at the call
    site, never a silent "no batches exist".

    The `= None` default this replaces was indistinguishable from a readable declaration
    that declares no batches, so a caller who forgot the argument had the excuse dropped in
    SILENCE and the entire declared population reported as OWED -- an absence that cannot be
    told from a clean read, which is the exact class this leg exists to police (#271). It is
    also why the fix is the signature: the docstring already promised `batch_refusal` made
    such a population visible, and the defaulted path emitted an empty reason anyway.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(951, "OPEN")]
    rows = [_stall_row(51, "ruling", "#951", 2, now=now)]

    with pytest.raises(TypeError) as excinfo:
        RUNNER.undispatched_ruling_leg(issues, rows, read_at=read_at)  # type: ignore[call-arg]
    assert "batches" in str(excinfo.value), (
        f"the refusal must NAME the omitted argument, or the reader cannot tell which "
        f"declaration to inject\n{excinfo.value}"
    )

    # ... and the discriminating control: the SAME call, one keyword supplied, returns a
    # leg. If this arm read the same as the one above, the TypeError would prove nothing
    # about the argument -- it would only prove the call is broken.
    control = RUNNER.undispatched_ruling_leg(issues, rows, read_at=read_at, batches={}, standing={})
    assert control["status"] == "ASSERTED", control
    assert control["coverage"]["items_owed_dispatch"] == 1, (
        f"an absent declaration resolves NOTHING, so the one ruled unit is OWED\n"
        f"{control['coverage']}"
    )

def test_the_undispatched_ruling_leg_is_WIRED_and_PRINTS_every_bucket() -> None:
    """#519 acceptance (3) and #163 half 2 (b): the leg reaches the report through the REAL
    `main()`, REDs on an owed unit, and prints each bucket WITH its predicate — so `0 owed`
    and "a bucket that cannot see one" never render the same line.
    """
    now = dt.datetime.now(dt.timezone.utc)
    issues = [_issue(951, "OPEN")]
    rows = [_stall_row(51, "ruling", "#951", 2, now=now)]

    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED dispatch must fail the run\n{out}"
    assert "LEG undispatched-ruling — ASSERTED" in out, out
    assert "OWED #951" in out, out
    assert "a mention is not a dispatch" in out, out
    assert "resolved by a DECLARED batch act" in out, out
    assert "batch declaration: ABSENT:" in out, (
        f"an absent declaration must be PRINTED with its reason, not implied by silence\n{out}"
    )
    assert "board read at " in out, out

def test_the_undispatched_ruling_leg_is_INJECTABLE_and_wired_by_default() -> None:
    """`dispatch_batches_fn` is a real parameter of `main()`, and the LIVE default reads the
    declaration through the ONE shared reader — never a second parse of the file."""
    import inspect
    params = inspect.signature(RUNNER.main).parameters
    assert "dispatch_batches_fn" in params, sorted(params)
    assert hasattr(RUNNER, "undispatched_batches_fn"), (
        "the live declaration read must exist as the default"
    )
    # The one reader, reached through the same accessor every other cross-tool read uses.
    reader = RUNNER.declaration_reader()
    assert hasattr(reader, "load_dispatch_batches"), (
        "the batch record must be read through tools/ledger_declaration.py, not re-parsed"
    )

def test_the_routing_arm_COUNTS_historical_rows_OUTSIDE_and_judges_none() -> None:
    """The epoch boundary: rows below it are COUNTED, never silently judged clean.

    The fifteen historical conversion rows name no item at all, and they are not defects --
    the requirement did not exist when they were written. Counting them as `outside` is what
    lets a reader see the boundary do work instead of assuming it.
    """
    problems, cov = RUNNER.conversion_routing_problems(
        [_probe_routed_row(3000, board=None)], [_routing_item(600)]
    )
    assert problems == [], problems
    assert cov["outside"] == 1, cov
    assert cov["judged"] == 0, cov
    assert cov["resolved"] == [] and cov["unanswered"] == [], cov

def test_the_routing_arm_RESOLVES_a_row_naming_an_OPEN_routing_item() -> None:
    """THE CONTROL. Without it, every arm below could pass on a leg that resolves nothing."""
    problems, cov = RUNNER.conversion_routing_problems(
        [_probe_routed_row(4449)], [_routing_item(600)]
    )
    assert problems == [], problems
    assert cov["judged"] == 1, cov
    assert cov["resolved"] == [4449], cov
    assert cov["unanswered"] == [], cov

def test_the_routing_arm_NAMES_each_unresolvable_case_by_its_OWN_reason() -> None:
    """FIVE failure modes, five DISTINCT reasons, on one fixture.

    The distinctness is the assertion: a leg that emitted one generic "unresolved" would
    satisfy every `in problems` check here and still leave a reader unable to tell a row
    naming no item from a row naming the wrong one. So the reasons are compared to each
    other, not only to their own phrases.
    """
    cases = [
        ("no ref at all", _probe_routed_row(4450, board=None), [_routing_item(600)],
         "carries no well-formed `board:#<n>` ref"),
        ("an item the board does not carry", _probe_routed_row(4451, board="#999"),
         [_routing_item(600)], "which this board does not carry"),
        ("an item that is not a routing item", _probe_routed_row(4452),
         [_routing_item(600, title="a defect that routed nothing")],
         "does not open `scores(` or `scores:`"),
        ("an item CREATED after the row", _probe_routed_row(4453),
         [_routing_item(600, created="2026-10-30T00:00:00Z")],
         "AFTER this row's ts"),
        ("an item CLOSED before the row", _probe_routed_row(4454),
         [_routing_item(600, state="CLOSED", closed="2026-10-27T00:00:00Z")],
         "not later than this row's ts"),
    ]
    reasons: list[str] = []
    for label, row, issues, phrase in cases:
        problems, cov = RUNNER.conversion_routing_problems([row], issues)
        assert len(problems) == 1, f"{label}: {problems}"
        assert phrase in problems[0], f"{label} — the reason must name its own failure\n" \
                                     f"{problems[0]}"
        assert cov["unanswered"] == [row["n"]], f"{label}: {cov}"
        assert cov["resolved"] == [], f"{label}: {cov}"
        reasons.append(problems[0])
    assert len(set(reasons)) == len(reasons), (
        "every unresolvable case must read DIFFERENTLY; a generic reason is a count, and a "
        f"count cannot be dispatched\n{reasons}"
    )

def test_the_routing_arm_discriminates_on_the_STATE_of_one_item() -> None:
    """The SAME item, one field apart: closed after the row resolves, before it does not.

    The row is identical in both arms, so a leg keyed on anything but the item's own window
    returns the same verdict twice and this pair fails. That is the property a "was it open
    when the routing was declared" clause has to have.
    """
    row = _probe_routed_row(4455)
    after, cov_after = RUNNER.conversion_routing_problems(
        [row], [_routing_item(600, state="CLOSED", closed="2026-10-29T06:00:00Z")]
    )
    assert after == [] and cov_after["resolved"] == [4455], (after, cov_after)
    before, cov_before = RUNNER.conversion_routing_problems(
        [row], [_routing_item(600, state="CLOSED", closed="2026-10-28T06:00:00Z")]
    )
    assert len(before) == 1 and cov_before["unanswered"] == [4455], (before, cov_before)

def test_the_routing_arm_fails_OPEN_when_no_board_was_injected() -> None:
    """"No unresolved routing" and "no board was read" must never render the same line."""
    problems, cov = RUNNER.conversion_routing_problems([_probe_routed_row(4449)], None)
    assert problems == [], problems
    assert cov["reason"] and "board was not injected" in cov["reason"], cov
    assert cov["judged"] == 0, cov

def test_the_routing_arm_is_WIRED_and_PRINTS_its_population_beside_its_epoch() -> None:
    """Driven through the REAL `main()`: a leg the report drops is a verdict nobody reads."""
    directory = _scores_dir(_score_artifact(total=70, cells=["2", "4"]))
    rows = [_probe_routed_row(4449)]
    rc, out, _ = _run([_routing_item(600)], rows, scores_dir=directory)
    assert "routing (epoch n=4448): 1 conversion row(s) judged" in out, out
    assert "0 historical row(s) OUTSIDE the population" in out, out
    assert "resolved: n=4449" in out, out
    assert "UNANSWERED: none" in out, out

    # ... and the UNANSWERED half renders as loudly as the resolved one.
    rc, out, _ = _run([_routing_item(600)], [_probe_routed_row(4449, board="#999")],
                      scores_dir=directory)
    assert rc == 1, out
    assert "UNANSWERED: n=4449" in out, out

def test_586_a_DECLARED_standing_item_is_EXCUSED_and_a_REFUSED_one_stays_OWED() -> None:
    """#586, ruled at n=4478: a PERMANENT-STATE item has no honest exit from this leg.

    `undispatched-ruling` reports items that are ruled, open, unclaimed and undispatched.
    For a standing item every one of those four exits is a FALSE RECORD: a `claim` asserts
    work nobody started, a `close` breaks the leg that tests the item's state at a row's own
    `ts`, a subject `dispatch` claims work owed to a lane, and a batch asserts an act that
    never happened. So the item was OWED forever and the only ways to clear it were lies.

    ARM 1 IS THE POSITIVE CONTROL and ARM 2 is its discriminating twin: the SAME board item
    and the SAME ruling row, one declaration apart. A leg that excused without a declaration
    would pass arm 1 and fail arm 2, which is the "an excuse must be DECLARED" property.
    ARM 3 and ARM 4 are the refusal pair, and they are the reason the entry is validated
    against the LEDGER rather than trusted: a stale or mistyped declaration must never
    silently clear a real debt.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # #581's real shape: a `ruling` row that resolves to it, and nothing else at all.
    rows = [_stall_row(4472, "ruling", "#581", 1, now=now)]
    issues = [_issue(581, "OPEN")]
    declared = {581: {"issue": 581, "ruling_row": 4472, "reason": "permanent state, probe"}}

    # ARM 1 -- POSITIVE CONTROL: a VALID declaration excuses, and says which ruling did it.
    leg = RUNNER.undispatched_ruling_leg(
        issues, rows, read_at=read_at, batches={},
        standing=declared)
    cov = leg["coverage"]
    assert leg["status"] == "ASSERTED", leg["status"]
    assert leg["problems"] == [], leg["problems"]
    assert cov["population_undispatched"] == 1, cov
    assert cov["items_owed_dispatch"] == 0, cov
    assert cov["items_excused_standing"] == 1, cov
    assert [e["issue"] for e in cov["excused_standing"]] == [581], cov["excused_standing"]
    assert cov["excused_standing"][0]["ruling_row"] == 4472, cov["excused_standing"]
    assert len(leg["excused"]) == 1, leg["excused"]
    assert "DECLARED standing item" in leg["excused"][0], leg["excused"][0]
    assert "ruling n=4472" in leg["excused"][0], leg["excused"][0]

    # ARM 2 -- NEGATIVE CONTROL: the SAME item, the SAME rows, NO declaration. It must be
    # OWED. Without this arm a leg that excused everything would pass arm 1.
    leg = RUNNER.undispatched_ruling_leg(
        issues, rows, read_at=read_at, batches={}, standing={})
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "#581 is OPEN" in leg["problems"][0], leg["problems"][0]
    assert leg["coverage"]["items_excused_standing"] == 0, leg["coverage"]

    # ARM 3 -- REFUSAL, wrong EVENT: `ruling_row` names a row that is not a `ruling` row.
    # The item is in the population (n=4472 really does rule it) and the declaration points
    # at the INTAKE row instead. It stays OWED and the refusal prints BESIDE it, so a broken
    # declaration is never indistinguishable from no declaration.
    with_intake = rows + [_stall_row(4480, "intake", "#581", 1, now=now)]
    wrong_event = {581: {"issue": 581, "ruling_row": 4480, "reason": "permanent state, probe"}}
    leg = RUNNER.undispatched_ruling_leg(
        issues, with_intake, read_at=read_at, batches={},
        standing=wrong_event)
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "#581 is OPEN" in leg["problems"][0], leg["problems"][0]
    assert "REFUSED" in leg["problems"][0], leg["problems"][0]
    assert "not a `ruling` row" in leg["problems"][0], leg["problems"][0]
    assert leg["coverage"]["items_refused_standing"] == 1, leg["coverage"]
    assert leg["coverage"]["items_excused_standing"] == 0, leg["coverage"]

    # ARM 4 -- REFUSAL, wrong ISSUE: a real `ruling` row, but it resolves to a DIFFERENT
    # unit. An entry that names another unit's ruling excuses nothing.
    other_ruling = rows + [_stall_row(4473, "ruling", "#999", 1, now=now)]
    wrong_issue = {581: {"issue": 581, "ruling_row": 4473, "reason": "permanent state, probe"}}
    leg = RUNNER.undispatched_ruling_leg(
        issues, other_ruling, read_at=read_at, batches={},
        standing=wrong_issue)
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "resolves to #999" in leg["problems"][0], leg["problems"][0]
    assert leg["coverage"]["items_refused_standing"] == 1, leg["coverage"]

    # ARM 5 -- ABSENT is a legitimate state and is NOT the same output as a refusal: the
    # population is still owed, and the reason rides in `standing_refusal` so a reader sees
    # "nothing declared" rather than an inference.
    leg = RUNNER.undispatched_ruling_leg(
        issues, rows, read_at=read_at, batches={},
        standing={}, standing_refusal="ABSENT: probe: none declared")
    assert leg["coverage"]["standing_refusal"].startswith("ABSENT"), leg["coverage"]
    assert leg["coverage"]["items_refused_standing"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]

    # ARM 6 -- THE RENDER, through the REAL `main()`: a leg whose numbers are right and
    # whose report still reads `0 owed` with no standing line would have fixed nothing a
    # lane can see. The declaration is INJECTED, so no probe reads the live one.
    _rc, out, _err = _run(issues, rows, standing_items=declared)
    assert "excused as DECLARED standing items: 1 item(s)" in out, out
    assert "STANDING #581 — ruling n=4472" in out, out
    assert "standing declaration: READ" in out, out

    # ... and a REFUSED entry renders as loudly as an excused one, with its reason.
    _rc, out, _err = _run(issues, with_intake, standing_items=wrong_event)
    assert "standing declarations REFUSED: 1 entry(ies)" in out, out
    assert "REFUSED #581 (ruling_row n=4480)" in out, out
    assert "OWED #581" in out, out

    # ARM 7 -- the LIVE default is a real parameter of `main()`, and the reader exists on
    # the module the runner reaches: a wiring that dropped either would leave production
    # reading the absent declaration forever while every probe above stayed green.
    import inspect
    params = set(inspect.signature(RUNNER.main).parameters)
    assert "standing_items_fn" in params, sorted(params)
    reader = RUNNER.declaration_reader()
    assert hasattr(reader, "load_standing_items"), dir(reader)

def test_586_the_standing_declaration_REFUSES_a_malformed_entry() -> None:
    """MALFORMED is a DEFECT, never a skip — an empty declaration would excuse a population.

    Every arm below is a shape that would resolve to `{}` if the reader were lenient, and an
    empty map is exactly what excuses nothing while looking like a declaration that checked
    out. So each one must RAISE, and the message must name the entry so the fix is obvious.
    """
    root = _scratch()
    reader = RUNNER.declaration_reader()
    doc = root / "docs"
    doc.mkdir()
    path = doc / "ledger-invariants.json"

    def raises(payload, needle):
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            reader.load_standing_items(root)
        except reader.DeclarationUnreadable as exc:
            joined = " ".join(str(p) for p in exc.args)
            assert needle in joined, joined
            return
        raise AssertionError(f"a declaration {needle!r} must be UNREADABLE, not resolved")

    # ABSENT is NOT a failure: a factory with no permanent-state item has declared none.
    try:
        reader.load_standing_items(root)
    except reader.DeclarationUnavailable as exc:
        assert "DECLARED factory data" in str(exc), str(exc)
    else:
        raise AssertionError("no declaration file must be UNAVAILABLE, not an empty map")

    raises({"standing_items": []}, "EMPTY list")
    raises({"standing_items": [{"issue": "581", "ruling_row": 1, "reason": "x"}]},
           "positive board issue number")
    raises({"standing_items": [{"issue": 581, "ruling_row": 0, "reason": "x"}]},
           "positive ledger row number")
    raises({"standing_items": [{"issue": 581, "ruling_row": 4472, "reason": "   "}]},
           "non-empty prose")
    raises({"standing_items": [
        {"issue": 581, "ruling_row": 4472, "reason": "a"},
        {"issue": 581, "ruling_row": 4473, "reason": "b"},
    ]}, "declared twice")

    # ... and the shape that DOES check out resolves to a map keyed by issue.
    path.write_text(json.dumps({"standing_items": [
        {"issue": 581, "ruling_row": 4472, "reason": "permanent state"}]}), encoding="utf-8")
    assert reader.load_standing_items(root) == {
        581: {"issue": 581, "ruling_row": 4472, "reason": "permanent state"}
    }

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
