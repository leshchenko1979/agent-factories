#!/usr/bin/env python3
r"""Gate: a reconstructed claim DECLARES itself and the basis it rests on.

Origin: #112, ruled at ledger `n=657`, amended under **#115 (ruling `n=687`)**. The law at
SKILL.md §State — every surface has one writer requires a reconstructed claim — an event `claim` row
stamped AFTER the work it accepts — to carry the token `claim=reconstructed` and to name the
basis it rests on under the canonical marker `BASIS:`.

WHAT THIS GATE USED TO CHECK, AND WHY THAT IS WITHDRAWN
-------------------------------------------------------
It used to require the row to DECLARE the interval between its own `ts` and its close row's
`ts` as the token `claim_gap`, and it compared that declaration against the interval it
recomputed. That requirement is **WITHDRAWN** (`n=687` clause 1), for the reason the file
already carried one paragraph down: **a gate must test a property its author controls.**

The author controls the ACT of declaring, never the interval. The claim's `ts` is its own
write instant — one of the five `ROW_IDENTITY` fields — while the close row's `ts` belongs
to whoever appends the close, and `tools/ledger.py` assigns it under the append lock after
`extract_task_telemetry` has run (~17–19 s measured on this host). So the declared value was
never the author's to compute, and a gate over it would have compared the tool's own
arithmetic against the rows that arithmetic was computed from — a check that cannot fail.

Two alternatives were ruled out with it (`n=687` clause 3): having the TOOL write the token
on the close row (same cannot-fail shape), and an atomic claim+close append (structurally
zero interval, at the cost of a second append path).

So the interval moves from DECLARED to **RECOMPUTED-AND-PRINTED**: this gate recomputes it
from the two rows' own `ts` values and PRINTS it beside each row it examines. It is
REPORTED, never judged — and the law text says so, which is why `tools/ledger.py verify`
prints it too: a law asserting that something is printed, with no mechanism printing it, is
the dead-text class P29 forbids.

WHAT FIRES AND WHAT DOES NOT
----------------------------
A row in the population — an event `claim` row at or after the declared boundary carrying
`claim=reconstructed` — FIRES when:

  * it names no basis under the canonical marker `BASIS:`.

That is the whole predicate, and it is deliberately narrow: it is the author-controlled
half, which is the only half a gate may judge. Everything else the gate knows about the row
is PRINTED:

  * the recomputed interval, close_row.ts − claim.ts, tool-sourced on BOTH sides with no
    typed expectation;
  * `no close row yet` where the work unit has not closed — which is NOT a defect, because a
    lane reconstructing its claim mid-work has no close row yet, and the gate must not fail
    an honest row for a state it has not reached.

THE POPULATION IS DOUBLY SCOPED, and that is the `n=602` measured need
------------------------------------------------------------------------
The population is `event == "claim"` AND `declares_token(detail, "claim", "reconstructed")`.
The scan is LEXICAL and the CALLER scopes it by the row's own event, because `n=602` is a
RULING row whose detail states the token it defines — and a ruling that quotes a token is
not a row that carries one (`tools/field_predicate.py::declares_token` records that need).

WHY THE BASIS IS A MARKER AND NOT A TRAILER TOKEN
--------------------------------------------------
`BASIS:` carries descriptive prose — which ruling, which dispatch, what it answers — and a
canonical trailer token is whitespace-delimited, so a `basis=` token could carry no more
than one word. The marker is prose-shaped and always lands in the detail's HEAD by
construction: `tools/field_predicate.py::trailer_tokens` collects only tokens carrying `=`,
so a colon-bearing marker can never be part of the canonical run. The marker is therefore
read over the whole detail, and the head/trailer question cannot arise for it.

THE MARKER IS MANDATED FORWARD ONLY
-----------------------------------
Measured before this gate was written: ONE of the pre-boundary reconstructions is an honest
row that names its basis in prose WITHOUT the marker, while the rest carry it. So a
retroactive marker gate would have fired on an honest row — the same defect class this
factory recorded in rework entry 157. The boundary is declared at the instant the rule
lands, so **every existing reconstruction is OUTSIDE the population** and prints as
`excused:`. NOTHING IS BACKFILLED.

WHICH rows those are, and which one is the decisive prose-only case, is FACTORY DATA: it is
declared under `reconstructions` in `docs/ledger-invariants.json`, never written as a
literal here. This file is paired byte-identically with its TEMPLATE copy, so a row number
typed here ships to every member and is judged against a ledger that does not carry it
(#239) — the declaration is what lets a member read its OWN history, or read none and skip
with the reason stated.

THE CLOSE ROW IS RESOLVED BY SUBJECT, NEVER BY ADJACENCY
--------------------------------------------------------
The close row of THAT WORK UNIT, not of the neighbouring row: a row's counterpart is read
from the row's OWN identity fields, and inferring one from the row beside it is the
attribution trap this workspace forbids. The close row is the event `close` row carrying the
SAME SUBJECT at or after the claim row, and where a subject carries several, the EARLIEST
such row is the one that answered it.

THE BOUNDARY IS DECLARED, AND THIS FILE SHIPS
---------------------------------------------
The boundary lives in the factory's own `docs/ledger-invariants.json`, read through
`tests/ledger_boundary.py`. This file is paired byte-identically with its TEMPLATE copy, so
it may not carry one factory's history: a key that is absent SKIPS with its reason stated,
and the value is that factory's own instant.

⚠️ THIS GATE MUST NOT COPY THE LOUD-FAIL-ON-ZERO GUARD. Its live population is legitimately
EMPTY until the next reconstruction, so an empty read is the EXPECTED state rather than a
broken parse. It takes the PROPORTIONAL guard (`population_skip_reason`), which SKIPS with a
stated reason and never passes silently — and it is proven to BITE by a synthetic probe,
because the two are separate properties: population visibility is the property of the RUN,
non-vacuity is the property of the PROBE (`n=657` PART 8).

Exit: 0 clean or stated skip, 1 on any hit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    boundary_and_rows,
    declared_reconstructions,
    parse_ts,
    synthetic_tree,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
# The reconstruction predicate — which rows are reconstructed claims, whether a row
# names its basis, which close row answered a claim, and the interval recomputed from
# the two rows' own `ts` values — lives in `tools/reconstruction.py` and is SHARED with
# `tools/ledger.py verify`, which prints the same interval beside its `excused:` lines
# (`n=687` clause 1). One field predicate, one home (`n=405` clause 5, `n=599`): a
# private copy here would drift from the printer's in silence, and the drift would land
# on exactly the rows both exist to describe.
from reconstruction import (  # noqa: E402
    BASIS_MARKER,
    RECONSTRUCTION_KEY,
    RECONSTRUCTION_VALUE,
    close_row_for,
    interval_line,
    names_basis,
    reconstructed_claims,
)
REPO = Path(__file__).resolve().parent.parent

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name with the `test_` prefix and
# `.py` suffix dropped, matching `close_row_revision`, `score_gate_recorded` and
# `subject_form`.
INVARIANT_KEY = "reconstructed_claim_declared"

# The token pair, the basis marker and the four helpers above are IMPORTED from
# `tools/reconstruction.py`, never redefined here — see the import block.

def row_problems(row: dict) -> list[str]:
    """Every way this reconstructed claim's self-declaration fails, naming the row.

    One leg, and it is the author-controlled one: a reconstruction must say what it rests
    on. The interval is not here — it is recomputed and printed, never judged.
    """
    number = row.get("n")
    subject = row.get("subject")
    where = f"n={number} (subject {subject})"

    problems: list[str] = []
    if not names_basis(row.get("detail", "")):
        problems.append(
            f"{where} carries `{RECONSTRUCTION_KEY}={RECONSTRUCTION_VALUE}` and names no "
            f"basis under the canonical marker `{BASIS_MARKER}` — a reconstructed claim "
            f"must state what it rests on (#115, ruling n=687)"
        )
    return problems


def population_reason(population: list[dict], boundary_text: str) -> str | None:
    """The reason to SKIP when no reconstruction is governed, else None.

    Shaped after `tests/ledger_boundary.py::population_skip_reason` and carrying its exact
    closing clause, because this population is DOUBLY scoped — an event `claim` row that
    also carries the reconstruction token — and that helper's `event` parameter names a
    single row EVENT. Passing `claim` there would print "no `claim` row at or after the
    declared boundary", which is FALSE of a ledger whose claims simply are not
    reconstructions; passing a phrase would put a scope where the helper documents an event
    name. So the sentence is stated here, with the scope it actually describes.
    """
    if population:
        return None
    return (
        f"no reconstructed claim (an event `{RECONSTRUCTION_KEY}` row carrying the token "
        f"`{RECONSTRUCTION_KEY}={RECONSTRUCTION_VALUE}`) at or after the declared boundary "
        f"{boundary_text} — the population is empty, so this is a stated skip and not a "
        f"silent pass"
    )


def reconstruction_problems(
    rows: list[dict], boundary, boundary_text: str
) -> tuple[list[str], list[str], list[dict], list[str]]:
    """`(problems, excused, population, intervals)` over every reconstructed claim in `rows`.

    The three-way split is the boundary's whole job: a reconstruction at or after it is
    GOVERNED and judged, one before it is EXCUSED and printed, and one that cannot be dated
    is a PROBLEM — a row that cannot be dated cannot be excused by its date either, and a
    defect must never be laundered into a stated skip.

    `intervals` is the RECOMPUTED-AND-PRINTED leg (`n=687` clause 1): one line per governed
    row, computed from the two rows' own `ts` values. It is returned rather than judged, so
    no caller can turn the report into a verdict by accident.
    """
    problems: list[str] = []
    excused: list[str] = []
    population: list[dict] = []
    intervals: list[str] = []

    for row in reconstructed_claims(rows):
        number, ts = row.get("n"), row.get("ts", "")
        try:
            when = parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(
                f"n={number} carries `{RECONSTRUCTION_KEY}={RECONSTRUCTION_VALUE}` with an "
                f"unparseable ts {ts!r} — it cannot be dated, so it cannot be excused"
            )
            continue
        if when < boundary:
            excused.append(
                f"n={number} ({ts}) predates the declared boundary ({boundary_text}) — the "
                f"reconstruction is never backfilled"
            )
            continue
        population.append(row)
        problems.extend(row_problems(row))
        intervals.append(interval_line(row, rows))

    return problems, excused, population, intervals


def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], int, list[str]]:
    """`(status, reason, problems, excused, checked, intervals)` over `repo`.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip: the
    population guard runs only on an otherwise-clean ledger, so a defect is never hidden
    behind "there was nothing to judge".
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], 0, []
    except GateError as exc:
        return "fail", "", list(exc.problems), [], 0, []

    problems, excused, population, intervals = reconstruction_problems(
        rows, boundary, boundary_text
    )
    if problems:
        return "fail", "", problems, excused, len(population), intervals

    reason = population_reason(population, boundary_text)
    if reason:
        return "skip", reason, [], excused, 0, intervals
    return "pass", "", [], excused, len(population), intervals


def _live_rows() -> list[dict]:
    """The live ledger's rows, or a pytest SKIP when this tree has none.

    The TEMPLATE copy resolves `REPO` to `TEMPLATE/`, whose ledger is BOOTSTRAP-created and
    therefore absent. That is the P35 class — a byte-paired gate asserting a live-tree fact
    its own tree cannot satisfy — so the live probes below STATE that reason instead of
    asserting a fact their tree cannot produce.
    """
    try:
        _, _, rows = boundary_and_rows(REPO, INVARIANT_KEY)
    except (SkipGate, GateError) as exc:
        pytest.skip(f"this tree carries no live ledger to judge: {exc}")
    return rows


def _declared() -> tuple[list[int], dict[int, int]]:
    """`(rows, gaps)` as THIS factory declared them, or a stated SKIP.

    The skip is the point of the whole change (#239): a tree that declares no reconstructed
    rows has none to calibrate against, and it says so with the reason rather than judging
    another factory's rows against its own ledger. `pytest.skip` is the gate's own idiom for
    it, and the reason travels, so the output reads "nothing to judge, and here is why"
    rather than passing silently.
    """
    try:
        rows, gaps, text = declared_reconstructions(REPO, INVARIANT_KEY)
    except SkipGate as exc:
        pytest.skip(f"no declared reconstruction history in this tree: {exc}")
    except GateError as exc:
        raise AssertionError(f"the declaration is unreadable: {exc}") from exc
    return rows, gaps


def _declared_rows() -> list[int]:
    return _declared()[0]


def _declared_gaps() -> dict[int, int]:
    return _declared()[1]


def _live_verdict() -> tuple[str, str, list[str], list[str], int, list[str]]:
    return evaluate(REPO)


# --- probes: the predicate must reject bad input, not only accept good ----------------

_PROBE_BOUNDARY = "2026-09-19T13:07:51Z"

# The SIX reconstructions the ledger carried when this gate was amended under #115. Named
# here as the LIVE calibration: the population is empty today, so a gate proven only on
# synthetic rows has never been pointed at the shape it was written for. One of the DECLARED
# rows is the decisive one — it names its basis in prose WITHOUT the marker, which is why the
# marker is mandated forward only and why every row here is excused rather than judged. WHICH
# row that is lives in the declaration, not here (#239).
# THE ROWS AND THEIR INTERVALS ARE **NOT HERE** (#239). They are THIS factory's history —
# six row numbers and five measured intervals that describe this ledger and no other — and
# this file is PAIRED byte-identically with its TEMPLATE copy, so a constant written here
# ships to every member. Measured before the fix: the live leg below asserts each row is
# present in the TREE'S OWN ledger, so every member tree went HARD RED naming a row that is
# not theirs. The harm was a red in a tree the constant does not describe, not a false
# clean.
#
# They now live in `docs/ledger-invariants.json` under `reconstructions`, beside the
# boundary, read through `ledger_boundary.declared_reconstructions` — the same seam, the
# same two arms: an ABSENT declaration SKIPS with its reason (the state every bootstrapped
# factory is in, and the state this factory would be in for any other gate's history), and a
# MALFORMED one FAILS, because a factory that declared rows and cannot have them read must
# not be hidden behind the same output as no declaration at all.


def _row(n: int, ts: str, subject: str, event: str = "dispatch", detail: str = "x") -> dict:
    return {
        "n": n,
        "ts": ts,
        "event": event,
        "actor": "worker",
        "subject": subject,
        "detail": detail,
    }


def _claim_detail(basis: str | None = f"{BASIS_MARKER} HQ ruling n=687") -> str:
    """A detail whose HEAD optionally names the basis, and whose canonical TRAILER carries
    the reconstruction token.

    The split is deliberate: the token is read LEXICALLY and the marker lives in prose, so a
    fixture that put both in the same place would not exercise the two scopes separately —
    and the trailer is what makes `claim=reconstructed` a canonical declaration rather than
    a quotation.
    """
    head = "Written now because the edits preceded this row."
    if basis is not None:
        head += f" {basis}"
    return f"{head} claim=reconstructed board=closed"


def _claim(n: int, ts: str, subject: str, basis: str | None = f"{BASIS_MARKER} ledger n=687") -> dict:
    return _row(n, ts, subject, event="claim", detail=_claim_detail(basis))


def _close(n: int, ts: str, subject: str) -> dict:
    return _row(n, ts, subject, event="close", detail="the work is done. board=closed")


def _probe_tree(root: Path, rows: list[dict]) -> Path:
    return synthetic_tree(root, rows=rows, invariants={INVARIANT_KEY: _PROBE_BOUNDARY})


# --- the live legs ---------------------------------------------------------------------


def test_live_the_ledger_carries_no_unbackfilled_reconstruction() -> None:
    """The live verdict, and it is the acceptance criterion: rc=0 on the live ledger."""
    status, reason, problems, _, _, _ = _live_verdict()
    assert status in ("pass", "skip"), (status, reason, problems)
    assert problems == [], problems


def test_live_the_historical_reconstructions_are_outside_the_population() -> None:
    """The boundary is REAL, not decorative: the rows THIS FACTORY DECLARED are
    reconstructions — the token scan finds them on live rows — and every one of them is
    excused rather than judged. A gate whose boundary excluded nothing would pass this file
    while governing the very rows the ruling put out of scope.

    The population is the DECLARATION's, never a constant in this file (#239): a member tree
    declares its own rows or declares none, and this leg reads whatever it declared.
    """
    historical = _declared_rows()
    rows = _live_rows()
    found = {row["n"] for row in reconstructed_claims(rows)}
    for n in historical:
        assert n in found, f"n={n} is a reconstructed claim and the scan missed it"
    _, _, problems, excused, checked, intervals = _live_verdict()
    # #124 DEFECT B. This leg asserted `checked == 0` — a COUNT of a MUTABLE population —
    # and it rotted the moment a lawful post-boundary reconstruction landed (n=716 #54,
    # n=760 #89): #121's class, inside the very file #121 produced. A count of a growing
    # population is a claim about the tree, so it must rot; the INVARIANT is what this leg
    # actually cares about, and it does not move when a lawful row arrives. The count is
    # still PRINTED, never asserted — a leg that examined nothing must never be mistaken
    # for one that examined the population and found it clean.
    assert problems == [], problems
    for n in historical:
        assert any(f"n={n} " in line for line in excused), (n, excused)
        assert not any(f"n={n} " in line for line in intervals), (
            f"n={n} is a PRE-BOUNDARY reconstruction and must not be governed"
        )
    print(f"  live — {checked} reconstruction(s) governed, {len(excused)} excused "
          f"(pre-boundary), {len(intervals)} interval(s) printed")


def test_live_the_historical_gaps_recompute_to_the_measured_intervals() -> None:
    """LIVE CALIBRATION of the resolution logic, against real rows.

    The population is empty today, so the only way this gate meets the shape it was written
    for is to point it at the rows #112 measured. Each pair is resolved the way the gate
    resolves it — close row by SUBJECT, earliest at or after the claim — and the interval is
    recomputed from the two rows' own `ts` values with the gate's own `parse_ts`. Those five
    recomputed intervals ARE the ruling's numbers, and three of the five are non-zero, which
    is the measurement that withdrew the equality requirement: a gate over "the close row's
    own ts" would have fired on three honest rows. A gate whose resolution drifted would
    still pass every synthetic probe, because the probes encode the same drift.
    """
    gaps = _declared_gaps()
    rows = _live_rows()
    by_n = {row["n"]: row for row in rows if isinstance(row.get("n"), int)}
    for claim_n, measured in gaps.items():
        claim = by_n.get(claim_n)
        assert claim is not None, f"n={claim_n} is not in the live ledger"
        assert claim.get("event") == "claim", (claim_n, claim.get("event"))
        close = close_row_for(claim, rows)
        assert close is not None, f"n={claim_n} (subject {claim.get('subject')}) has no close row"
        recomputed = int((parse_ts(close["ts"]) - parse_ts(claim["ts"])).total_seconds())
        assert recomputed == measured, (
            f"n={claim_n} -> n={close['n']} recomputes to {recomputed}s, "
            f"but #112 measured {measured}s"
        )


def test_live_the_recomputed_interval_is_printed_beside_the_row() -> None:
    """The PRINT leg, exercised against live rows (`n=687` clause 1).

    The interval is recomputed from the two rows' own `ts` values and PRINTED — never
    declared and never judged. The governed population is empty today, so this points the
    printer at the live rows directly: the printed line must carry the recomputed value AND
    the pair of rows it came from, so a reader can re-check it without the gate.
    """
    rows = _live_rows()
    by_n = {row["n"]: row for row in rows if isinstance(row.get("n"), int)}
    for claim_n, measured in _declared_gaps().items():
        line = interval_line(by_n[claim_n], rows)
        assert f"n={claim_n} " in line, (claim_n, line)
        assert f"interval={measured}s" in line, (claim_n, line)
        assert "recomputed" not in line, line
        close = close_row_for(by_n[claim_n], rows)
        assert f"close n={close['n']}" in line, (claim_n, line)


# --- THE BITE --------------------------------------------------------------------------


def test_probe_a_reconstruction_naming_no_basis_fires(tmp_path: Path) -> None:
    """THE BITE. An exit 0 over an empty population shows nothing, so the gate is proven to
    fail: the row declares itself reconstructed and names no basis, and the report names the
    row and the marker it is missing."""
    tree = _probe_tree(
        tmp_path / "nobasis",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7", basis=None),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, _, problems, _, checked, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert checked == 1, checked
    assert len(problems) == 1, problems
    assert "n=900" in problems[0] and BASIS_MARKER in problems[0], problems


def test_probe_the_same_tree_with_the_basis_stated_is_clean(tmp_path: Path) -> None:
    """The same tree with the BASIS stated passes — so the bite above is the missing basis
    and not the fixture."""
    tree = _probe_tree(
        tmp_path / "basis",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7"),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, reason, problems, _, checked, intervals = evaluate(tree)
    assert status == "pass", (status, reason, problems)
    assert problems == [], problems
    assert checked == 1, checked
    assert len(intervals) == 1, intervals


def test_probe_a_prose_basis_without_the_marker_still_fires(tmp_path: Path) -> None:
    """The decisive DECLARED row's exact shape: the row says it rests on something, in words,
    WITHOUT the canonical marker.

    This probe is the reason the marker is mandated FORWARD ONLY. The live row of that shape
    is excused by the boundary rather than judged; a row written after the rule must carry
    the marker, and this probe fixes what the rule actually asks for — the marker, not the
    word "basis" appearing anywhere in the prose.
    """
    tree = _probe_tree(
        tmp_path / "prose",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7", basis="It carries the token on that basis."),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, _, problems, _, checked, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert checked == 1, checked
    assert len(problems) == 1, problems


# --- the printed legs, which never judge ----------------------------------------------


def test_probe_a_reconstruction_with_no_close_row_yet_does_not_fire(tmp_path: Path) -> None:
    """A reconstruction mid-work is NORMAL: the work unit has not closed, so there is no
    interval to recompute — and the gate PRINTS that state instead of failing the row.

    This is the leg that would have made the old gate unusable for its own purpose: a lane
    reconstructing its claim cannot wait for its close row to exist before writing it.
    """
    tree = _probe_tree(tmp_path / "open", [_claim(900, "2026-09-19T14:00:00Z", "#7")])
    status, reason, problems, _, checked, intervals = evaluate(tree)
    assert status == "pass", (status, reason, problems)
    assert problems == [], problems
    assert checked == 1, checked
    assert len(intervals) == 1, intervals
    assert "interval=no close row yet" in intervals[0], intervals


def test_probe_the_interval_is_printed_and_never_judged(tmp_path: Path) -> None:
    """The declared-then-rejected shape, now merely REPORTED.

    The old gate FAILED this tree: a row that declared `claim_gap=65` against a recomputed
    300s was a hit. Under `n=687` clause 1 the token is withdrawn and the interval is
    recomputed and printed — so the same tree now PASSES, and the printed line carries the
    recomputed 300s. If this ever fails, the withdrawn token has crept back in as a
    requirement.
    """
    tree = _probe_tree(
        tmp_path / "reported",
        [
            _row(
                900,
                "2026-09-19T14:00:00Z",
                "#7",
                event="claim",
                detail=_claim_detail() + " claim_gap=65",
            ),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, reason, problems, _, checked, intervals = evaluate(tree)
    assert status == "pass", (status, reason, problems)
    assert problems == [], problems
    assert checked == 1, checked
    assert len(intervals) == 1, intervals
    assert "interval=300s" in intervals[0], intervals


def test_probe_the_close_row_is_resolved_by_subject_not_by_adjacency(tmp_path: Path) -> None:
    """The attribution trap, at row granularity: a close row of ANOTHER subject sitting
    between the claim and its own close must not answer it.

    A reader that took the neighbouring row would recompute 60s here; the row's own subject
    resolves to 300s. The subject is the row's own identity field — inferring a counterpart
    from the row beside it is the failure this workspace names and forbids.
    """
    tree = _probe_tree(
        tmp_path / "adjacency",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7"),
            _close(901, "2026-09-19T14:01:00Z", "#8"),
            _close(902, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, reason, problems, _, _, intervals = evaluate(tree)
    assert status == "pass", (status, reason, problems)
    assert "interval=300s" in intervals[0], intervals
    assert "n=902" in intervals[0], intervals


def test_probe_a_close_row_before_the_claim_does_not_answer_it(tmp_path: Path) -> None:
    """A close that PRECEDES the claim is not the close of this work unit — the claim was
    reconstructed after work that a LATER close settles. So the interval prints as
    `no close row yet`, and no row is failed for a state the work has not reached."""
    tree = _probe_tree(
        tmp_path / "earlier",
        [
            _close(899, "2026-09-19T13:00:00Z", "#7"),
            _claim(900, "2026-09-19T14:00:00Z", "#7"),
        ],
    )
    status, reason, problems, _, checked, intervals = evaluate(tree)
    assert status == "pass", (status, reason, problems)
    assert problems == [], problems
    assert checked == 1, checked
    assert "interval=no close row yet" in intervals[0], intervals


def test_probe_the_earliest_close_of_the_subject_answers_the_claim(tmp_path: Path) -> None:
    """Where a subject carries several close rows, the EARLIEST at or after the claim is the
    one that answered it — the row number is the tie-break, and it is the row's own
    identity field rather than a fact about its neighbour."""
    tree = _probe_tree(
        tmp_path / "earliest",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7"),
            _close(901, "2026-09-19T14:02:00Z", "#7"),
            _close(902, "2026-09-19T14:20:00Z", "#7"),
        ],
    )
    _, _, _, _, _, intervals = evaluate(tree)
    assert "n=901" in intervals[0], intervals
    assert "interval=120s" in intervals[0], intervals


# --- scope, boundary, and the stated skips --------------------------------------------


def test_probe_a_quoted_token_outside_event_claim_is_out_of_the_population(tmp_path: Path) -> None:
    """`n=602`'s measured need: a RULING row whose detail states the token it defines is not
    a row that carries one. The token is read lexically, so the EVENT is what keeps the
    quotation out of the population — and with it out, the population is empty and the gate
    SKIPS with its reason instead of judging a ruling."""
    tree = _probe_tree(
        tmp_path / "quoted",
        [
            _row(
                900,
                "2026-09-19T14:00:00Z",
                "#7",
                event="ruling",
                detail="a claim is reconstructed when it carries claim=reconstructed.",
            ),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, reason, problems, _, checked, _ = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert checked == 0, checked
    assert "reconstructed claim" in reason, reason


def test_probe_a_pre_boundary_reconstruction_is_excused_not_judged(tmp_path: Path) -> None:
    """Forward-only: a reconstruction written before the boundary prints as `excused:` and
    is never judged — even one that names no basis, which is exactly the declared
    prose-only shape."""
    tree = _probe_tree(
        tmp_path / "early",
        [
            _claim(900, "2026-09-19T13:00:00Z", "#7", basis=None),
            _close(901, "2026-09-19T13:05:00Z", "#7"),
        ],
    )
    status, reason, problems, excused, checked, intervals = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert problems == [], problems
    assert checked == 0, checked
    assert len(excused) == 1 and "n=900" in excused[0], excused
    assert intervals == [], intervals


def test_probe_the_boundary_comes_from_the_declaration_not_this_file(tmp_path: Path) -> None:
    """The boundary is READ, not baked in: the same row is excused under a late boundary and
    governed under an early one. A gate whose boundary was a constant in this file would
    pass both, which is the difference between a declared boundary and a decorative one."""
    rows = [
        _claim(900, "2026-09-19T14:00:00Z", "#7", basis=None),
        _close(901, "2026-09-19T14:05:00Z", "#7"),
    ]
    early = synthetic_tree(
        tmp_path / "early-boundary",
        rows=rows,
        invariants={INVARIANT_KEY: "2026-09-19T13:00:00Z"},
    )
    late = synthetic_tree(
        tmp_path / "late-boundary",
        rows=rows,
        invariants={INVARIANT_KEY: "2026-09-19T15:00:00Z"},
    )
    assert evaluate(early)[0] == "fail", "the declared boundary was not applied"
    assert evaluate(late)[0] == "skip", "the declared boundary was not applied"


def test_probe_a_tree_with_no_ledger_skips_with_its_reason(tmp_path: Path) -> None:
    """The TEMPLATE copy's own state: no ledger, so no verdict. Stated, never silent."""
    tree = _probe_tree(tmp_path / "empty", [])
    (tree / "evidence" / "ledger.jsonl").unlink()
    status, reason, problems, _, checked, _ = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert "ledger" in reason, reason
    assert checked == 0, checked


def test_probe_a_tree_with_no_declaration_skips_with_its_reason(tmp_path: Path) -> None:
    """An undeclared boundary is a STATED skip naming the key, not a silent pass."""
    tree = synthetic_tree(
        tmp_path / "bare", rows=[_row(900, "2026-09-19T14:00:00Z", "#7")], invariants={}
    )
    status, reason, problems, _, checked, _ = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert INVARIANT_KEY in reason, reason
    assert checked == 0, checked


def test_probe_a_declaration_missing_this_key_skips_with_its_reason(tmp_path: Path) -> None:
    """A declaration that exists but does not carry THIS key is still a stated skip: a key
    another gate owns must not be read as this gate's boundary.

    The row below is a DISPATCH, not a reconstruction — deliberately: the boundary reader
    validates the ledger before it reads the declaration, so a probe for an undeclared key
    must still ship a ledger with rows in it, or it would be measuring the empty-ledger leg
    instead of the one it names.
    """
    tree = synthetic_tree(
        tmp_path / "other-key",
        rows=[_row(900, "2026-09-19T14:00:00Z", "#7")],
        invariants={"close_row_revision": _PROBE_BOUNDARY},
    )
    status, reason, problems, _, checked, _ = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert INVARIANT_KEY in reason, reason
    assert checked == 0, checked


def test_probe_an_unparseable_ts_is_a_problem_and_not_a_skip(tmp_path: Path) -> None:
    """A row that cannot be DATED cannot be excused by its date either: it is a problem, so
    a defect is never laundered into a stated skip."""
    tree = _probe_tree(
        tmp_path / "undated",
        [_claim(900, "not-a-timestamp", "#7")],
    )
    status, _, problems, _, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert len(problems) == 1 and "cannot be dated" in problems[0], problems


# --- the printed form ------------------------------------------------------------------


def test_probe_the_printed_form_names_the_population_and_prints_the_interval(
    tmp_path: Path, capsys
) -> None:
    """The script form's contract: the governed population is NAMED and the recomputed
    interval is PRINTED. Population visibility is the property of the RUN — a gate that
    prints neither cannot be told from one that examined nothing."""
    tree = _probe_tree(
        tmp_path / "printed",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7"),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    assert main(tree) == 0
    out = capsys.readouterr().out
    assert "1 reconstructed claim(s) examined" in out, out
    assert "0 hit(s)" in out, out
    assert "interval=300s" in out, out


def test_probe_the_printed_form_fails_loudly_with_the_row_named(
    tmp_path: Path, capsys
) -> None:
    """A hit is rc=1 and the row is named on stderr, so a failing gate says WHICH row."""
    tree = _probe_tree(
        tmp_path / "printed-fail",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7", basis=None),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    assert main(tree) == 1
    err = capsys.readouterr().err
    assert "reconstructed-claim gate FAILED:" in err, err
    assert "n=900" in err, err


def main(repo: Path = REPO) -> int:
    """Script form: the same verdict, with the excused set and the recomputed intervals on
    STDOUT.

    `repo` is a parameter so a probe can exercise the printed form against a synthetic tree
    — the TEMPLATE copy has no ledger of its own to print.
    """
    status, reason, problems, excused, checked, intervals = evaluate(repo)
    for line in excused:
        print(f"  excused: {line}")
    for line in intervals:
        print(f"  {line}")
    if status == "skip":
        print(f"reconstructed-claim gate: SKIP — {reason}")
        return 0
    if status == "fail":
        print("reconstructed-claim gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"reconstructed-claim gate: clean — {checked} reconstructed claim(s) examined, "
        f"{len(problems)} hit(s), {len(excused)} excused (pre-boundary)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
