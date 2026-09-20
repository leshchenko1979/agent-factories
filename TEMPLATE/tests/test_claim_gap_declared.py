#!/usr/bin/env python3
r"""Gate: a reconstructed claim DECLARES the interval it cannot control.

Origin: #112, ruled at ledger `n=657` PART 6 and PART 7. The law at
`skills/meta-factory/SKILL.md` requires a reconstructed claim — an event `claim` row
stamped AFTER the work it accepts — to carry the token `claim=reconstructed` and to
DECLARE the interval between its own `ts` and its close row's `ts` as the token
`claim_gap`, in seconds, with a zero value where both appends landed in one second.

WHAT IT REPLACED, AND WHY THAT MATTERS TO THIS FILE
---------------------------------------------------
It replaced a requirement that the reconstruction TAKE the close row's own `ts`, on the
stated rationale that both rows are written in one instant. Measured over the five
reconstructions the ledger then carried, the gaps were 0s, 2s, 0s, 347s and 65s — THREE OF
FIVE miss that equality, so a gate over it would have fired on honest rows. `n=657` PART 5
states the rule this file is built on: **a gate must test a property its author controls.**
The claim's `ts` is its own write instant, one of the five `ROW_IDENTITY` fields, while the
close row's `ts` belongs to whoever appends the close and is nobody's to control. The
controllable property is the DECLARATION, so this gate checks the declaration against the
rows it describes.

WHAT FIRES AND WHAT DOES NOT
----------------------------
A row in the population — an event `claim` row at or after the declared boundary carrying
`claim=reconstructed` — FIRES when:

  * it declares no `claim_gap` token in its canonical trailer, or declares the key twice,
    or declares a value that is not a whole number of seconds;
  * its work unit has no close row to measure against, or none at or after it;
  * the value it declares disagrees with the interval recomputed from the two rows' own
    `ts` values.

Both sides of that comparison are TOOL-SOURCED and neither is typed in this file: the
declared side is read out of the row through `tools/field_predicate.py`, and the recomputed
side is arithmetic over the two rows' own timestamps. A gate carrying its own expected
number would be asserting a fact about a row it never read.

THE POPULATION IS DOUBLY SCOPED, and that is the `n=602` measured need
------------------------------------------------------------------------
The population is `event == "claim"` AND `declares_token(detail, "claim", "reconstructed")`.
The scan is LEXICAL and the CALLER scopes it by the row's own event, because `n=602` is a
RULING row whose detail states the token it defines — and a ruling that quotes a token is
not a row that carries one. `declares_token`'s own docstring records that need, so the two
scoping questions are kept apart here: WHICH ROWS ARE RECONSTRUCTIONS is lexical and
event-scoped; WHICH TOKEN DECLARES THE INTERVAL is positional and trailer-scoped.

THE CLOSE ROW IS RESOLVED BY SUBJECT, NEVER BY ADJACENCY
--------------------------------------------------------
The law's words are "its close row's `ts`" — the close row of THAT WORK UNIT. The five
historical pairs happen to be adjacent rows, but adjacency is not the relation: a row's
actor and a row's counterpart are read from the row's OWN identity fields, and inferring
one from the row beside it is the attribution trap this workspace forbids. So the close row
is the event `close` row carrying the SAME SUBJECT at or after the claim row, and where a
subject carries several, the EARLIEST such row is the close that answered this claim — a
later close is a later close of the same work unit, not the boundary this row declared.

THE BOUNDARY IS DECLARED, AND THIS FILE SHIPS
---------------------------------------------
The boundary lives in the factory's own `docs/ledger-invariants.json`, read through
`tests/ledger_boundary.py`. This file is paired byte-identically with its TEMPLATE twin, so
it may not carry one factory's history: a key that is absent SKIPS with its reason stated,
and the five historical reconstructions are OUTSIDE the population. NOTHING IS BACKFILLED —
a reconstruction written before the sentence existed is not retrofitted, and the `excused:`
lines this gate prints are how that is visible rather than assumed.

THE VACUITY GUARD IS PROPORTIONAL, NOT A FLOOR
----------------------------------------------
The live population is legitimately EMPTY until the next reconstruction, so the
loud-fail-on-zero form — correct for a gate whose population is the whole history, as
`tests/test_ledger_no_shrink.py`'s is — would be wrong here. Non-vacuity is a property of
the PROBE; population visibility is the property of the RUN. So this file PRINTS the
population it examined and proves it BITES with a synthetic probe.

Run: python3 tests/test_claim_gap_declared.py
Exit: 0 clean or stated skip, 1 on any hit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    boundary_and_rows,
    parse_ts,
    synthetic_tree,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from field_predicate import declares_token, keyed_value, trailer_tokens  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name with the `test_` prefix and
# `.py` suffix dropped, matching `close_row_revision`, `score_gate_recorded` and
# `subject_form`.
INVARIANT_KEY = "claim_gap_declared"

# The two tokens this invariant is built on, named once. `claim=reconstructed` declares
# THAT a row is a reconstruction — read LEXICALLY, anywhere in the detail, scoped by the
# caller to event `claim`. `claim_gap` declares the interval — read from the CANONICAL
# TRAILER, because that run is the row's own declaration of its fields.
RECONSTRUCTION_KEY = "claim"
RECONSTRUCTION_VALUE = "reconstructed"
INTERVAL_KEY = "claim_gap"


def reconstructed_claims(rows: list[dict]) -> list[dict]:
    """Every event `claim` row that declares ITSELF reconstructed.

    Lexical and event-scoped, deliberately: `n=602` is a ruling row that QUOTES the token
    it defines, and a row that quotes a token is not a row that carries one. Scoping by
    position in the trailer was the alternative and is rejected — a declaration written
    mid-detail would then be silently invisible, and a declaration no reader can see is
    worse than one a reader can check (`tools/field_predicate.py::declares_token`).
    """
    return [
        row
        for row in rows
        if row.get("event") == "claim"
        and declares_token(row.get("detail", ""), RECONSTRUCTION_KEY, RECONSTRUCTION_VALUE)
    ]


def declared_gap(detail: str) -> tuple[int | None, str | None]:
    """`(seconds, None)` for the interval this detail declares, else `(None, why)`.

    Read through the canonical trailer, per token, mirroring the sibling reader of `rework`
    in `tests/test_rework_declared_landed.py`: `claim_gap` is not a telemetry key, so it has
    no entry in `tools/field_predicate.py`'s `TELEMETRY_KEYS`, and the trailer is where a
    row declares its own fields.

    A SECOND declaration is reported rather than resolved. One field has one predicate, and
    a reader that takes the last occurrence as canonical is exactly the failure the masking
    rule names: `tools/ledger.py repair` once prepended a duplicate token so a row declared
    the field twice with the FALSE value last (`n=620` PART 2, `n=642`).
    """
    values = [
        value
        for value in (keyed_value(token, INTERVAL_KEY) for token in trailer_tokens(detail))
        if value is not None
    ]
    if not values:
        return None, f"declares no `{INTERVAL_KEY}` token in its canonical trailer"
    if len(values) > 1:
        return None, (
            f"declares `{INTERVAL_KEY}` {len(values)} times in its canonical trailer "
            f"({', '.join(values)}) — one field, one declaration"
        )
    try:
        return int(values[0]), None
    except ValueError:
        return None, (
            f"declares `{INTERVAL_KEY}={values[0]}`, which is not a whole number of seconds"
        )


def close_row_for(claim_row: dict, rows: list[dict]) -> dict | None:
    """The close row of this claim's WORK UNIT, or None when there is none.

    Resolved by SUBJECT, never by adjacency — see the module docstring. The row number is
    the tie-break, and it is a row's OWN identity field rather than a fact about its
    neighbour: among the close rows of this subject, the earliest at or after the claim row
    is the one that answered it.
    """
    subject = claim_row.get("subject")
    number = claim_row.get("n")
    if not isinstance(number, int):
        return None
    candidates = [
        row
        for row in rows
        if row.get("event") == "close"
        and row.get("subject") == subject
        and isinstance(row.get("n"), int)
        and row["n"] >= number
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: row["n"])


def row_problems(row: dict, rows: list[dict]) -> list[str]:
    """Every way this reconstructed claim's declaration fails, naming the row."""
    number = row.get("n")
    subject = row.get("subject")
    where = f"n={number} (subject {subject})"

    problems: list[str] = []
    declared, why = declared_gap(row.get("detail", ""))
    if why is not None:
        problems.append(
            f"{where} carries `{RECONSTRUCTION_KEY}={RECONSTRUCTION_VALUE}` but {why}"
        )

    close = close_row_for(row, rows)
    if close is None:
        problems.append(
            f"{where} declares an interval against its close row, and no event `close` row "
            f"carries subject {subject} at or after n={number} — the interval cannot be "
            f"recomputed from the rows it describes"
        )
        return problems

    recomputed = int((parse_ts(close["ts"]) - parse_ts(row["ts"])).total_seconds())
    if recomputed < 0:
        problems.append(
            f"{where} ts {row.get('ts')} is LATER than its close row n={close.get('n')} "
            f"ts {close.get('ts')} — the rows recompute to {recomputed}s, and a close cannot "
            f"precede the claim that accepted the work"
        )
        return problems
    if declared is not None and declared != recomputed:
        problems.append(
            f"{where} declares `{INTERVAL_KEY}={declared}` and the rows recompute it to "
            f"{recomputed}s — its own ts {row.get('ts')} to its close row n={close.get('n')} "
            f"ts {close.get('ts')}"
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


def claim_gap_problems(
    rows: list[dict], boundary, boundary_text: str
) -> tuple[list[str], list[str], list[dict]]:
    """`(problems, excused, population)` over every reconstructed claim in `rows`.

    The three-way split is the boundary's whole job: a reconstruction at or after it is
    GOVERNED and judged, one before it is EXCUSED and printed, and one that cannot be dated
    is a PROBLEM — a row that cannot be dated cannot be excused by its date either, and a
    defect must never be laundered into a stated skip.
    """
    problems: list[str] = []
    excused: list[str] = []
    population: list[dict] = []

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
        problems.extend(row_problems(row, rows))

    return problems, excused, population


def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], int]:
    """`(status, reason, problems, excused, checked)` over `repo` — the probe-able core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip: the
    population guard runs only on an otherwise-clean ledger, so a defect is never hidden
    behind "there was nothing to judge".
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], 0
    except GateError as exc:
        return "fail", "", list(exc.problems), [], 0

    problems, excused, population = claim_gap_problems(rows, boundary, boundary_text)
    if problems:
        return "fail", "", problems, excused, len(population)

    reason = population_reason(population, boundary_text)
    if reason:
        return "skip", reason, [], excused, 0
    return "pass", "", [], excused, len(population)


def _live_rows() -> list[dict]:
    """The live ledger's rows, or a pytest SKIP when this tree has none.

    The TEMPLATE twin resolves `REPO` to `TEMPLATE/`, whose ledger is BOOTSTRAP-created and
    therefore absent. That is the P35 class — a byte-paired gate asserting a live-tree fact
    its own tree cannot satisfy — so the live probes below STATE that reason instead of
    asserting a fact their tree cannot produce.
    """
    try:
        _, _, rows = boundary_and_rows(REPO, INVARIANT_KEY)
    except (SkipGate, GateError) as exc:
        pytest.skip(f"this tree carries no live ledger to judge: {exc}")
    return rows


def _live_verdict() -> tuple[str, str, list[str], list[str], int]:
    return evaluate(REPO)


# --- probes: the predicate must reject bad input, not only accept good ----------------

_PROBE_BOUNDARY = "2026-09-19T13:07:51Z"

# The five reconstructions the ledger carried when #112 was ruled (n=657 PART 1). Named
# here as the LIVE calibration: the population is empty today, so a gate proven only on
# synthetic rows has never been pointed at the shape it was written for. These are the rows
# the boundary exists to exclude.
_HISTORICAL_RECONSTRUCTIONS = (606, 617, 626, 647, 654)

# The intervals those five DECLARE, as #112's ruling measured them, keyed by claim row.
_HISTORICAL_GAPS = {606: 0, 617: 2, 626: 0, 647: 347, 654: 65}


def _row(n: int, ts: str, subject: str, event: str = "dispatch", detail: str = "x") -> dict:
    return {
        "n": n,
        "ts": ts,
        "event": event,
        "actor": "worker",
        "subject": subject,
        "detail": detail,
    }


def _claim_detail(*extra: str) -> str:
    """A detail whose CANONICAL TRAILER carries the reconstruction token and `extra`.

    The prose head is deliberate: `claim=reconstructed` is read lexically and `claim_gap` is
    read from the trailer, so a fixture that put both in the same run would not exercise the
    two scopes separately.
    """
    tokens = ["claim=reconstructed", *extra, "board=closed"]
    return "Written now because the edits preceded this row. " + " ".join(tokens)


def _claim(n: int, ts: str, subject: str, *extra: str) -> dict:
    return _row(n, ts, subject, event="claim", detail=_claim_detail(*extra))


def _close(n: int, ts: str, subject: str) -> dict:
    return _row(n, ts, subject, event="close", detail="the work is done. board=closed")


def _probe_tree(root: Path, rows: list[dict]) -> Path:
    return synthetic_tree(root, rows=rows, invariants={INVARIANT_KEY: _PROBE_BOUNDARY})


def test_live_the_ledger_carries_no_unbackfilled_reconstruction() -> None:
    """The live verdict, and it is the acceptance criterion: rc=0 on the live ledger."""
    status, reason, problems, _, _ = _live_verdict()
    assert status in ("pass", "skip"), (status, reason, problems)
    assert problems == [], problems


def test_live_the_historical_reconstructions_are_outside_the_population() -> None:
    """The boundary is REAL, not decorative: the five rows the ruling measured ARE
    reconstructions — the token scan finds them on live rows — and every one of them is
    excused rather than judged. A gate whose boundary excluded nothing would pass this file
    while governing the very rows the ruling put out of scope."""
    rows = _live_rows()
    found = {row["n"] for row in reconstructed_claims(rows)}
    for n in _HISTORICAL_RECONSTRUCTIONS:
        assert n in found, f"n={n} is a reconstructed claim and the scan missed it"
    _, _, problems, excused, checked = _live_verdict()
    assert problems == [], problems
    assert checked == 0, f"{checked} reconstruction(s) are governed; none should be yet"
    for n in _HISTORICAL_RECONSTRUCTIONS:
        assert any(f"n={n} " in line for line in excused), (n, excused)


def test_live_the_historical_gaps_recompute_to_the_measured_intervals() -> None:
    """LIVE CALIBRATION of the resolution logic, against real rows.

    The population is empty today, so the only way this gate meets the shape it was written
    for is to point it at the five rows #112 measured. Each pair is resolved the way the gate
    resolves it — close row by SUBJECT, earliest at or after the claim — and the interval is
    recomputed from the two rows' own `ts` values with the gate's own `parse_ts`. Those five
    recomputed intervals ARE the ruling's numbers, and three of the five are non-zero, which
    is the measurement that withdrew the equality requirement: a gate over "the close row's
    own ts" would have fired on three honest rows. A gate whose resolution drifted would
    still pass every synthetic probe, because the probes encode the same drift.
    """
    rows = _live_rows()
    by_n = {row["n"]: row for row in rows if isinstance(row.get("n"), int)}
    for claim_n, measured in _HISTORICAL_GAPS.items():
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


def test_probe_a_declared_gap_that_disagrees_with_the_rows_fires(tmp_path: Path) -> None:
    """THE BITE. An exit 0 over an empty population shows nothing, so the gate is proven to
    fail: the declared interval is 65s and the two rows' own `ts` values recompute it to
    300s, and the report names the row, the declaration and the recomputation."""
    tree = _probe_tree(
        tmp_path / "disagree",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7", "claim_gap=65"),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, _, problems, _, checked = evaluate(tree)
    assert status == "fail", (status, problems)
    assert checked == 1, checked
    assert len(problems) == 1, problems
    assert "n=900" in problems[0] and "claim_gap=65" in problems[0], problems
    assert "recompute it to 300s" in problems[0], problems


def test_probe_an_agreeing_declaration_is_clean(tmp_path: Path) -> None:
    """The same tree with the DECLARATION corrected passes — so the bite above is the
    disagreement and not the fixture."""
    tree = _probe_tree(
        tmp_path / "agree",
        [
            _claim(900, "2026-09-19T14:00:00Z", "#7", "claim_gap=300"),
            _close(901, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, reason, problems, _, checked = evaluate(tree)
    assert (status, problems, checked) == ("pass", [], 1), (status, reason, problems)


def test_probe_a_missing_interval_token_fires(tmp_path: Path) -> None:
    tree = _probe_tree(
        tmp_path / "missing",
        [
            _claim(902, "2026-09-19T14:00:00Z", "#7"),
            _close(903, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "declares no `claim_gap` token" in problems[0], problems


def test_probe_a_duplicate_declaration_fires(tmp_path: Path) -> None:
    """The MASKING shape, and the reason a second declaration is a defect rather than a
    tie-break: `tools/ledger.py repair` prepended a token so a row declared the field twice
    with the FALSE value last (n=620 PART 2). A reader taking the last occurrence as
    canonical would read this row's 300 and miss the 65 it also declares."""
    tree = _probe_tree(
        tmp_path / "duplicate",
        [
            _claim(904, "2026-09-19T14:00:00Z", "#7", "claim_gap=65", "claim_gap=300"),
            _close(905, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "declares `claim_gap` 2 times" in problems[0], problems


def test_probe_a_non_numeric_declaration_fires(tmp_path: Path) -> None:
    tree = _probe_tree(
        tmp_path / "prose-value",
        [
            _claim(906, "2026-09-19T14:00:00Z", "#7", "claim_gap=soon"),
            _close(907, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "not a whole number of seconds" in problems[0], problems


def test_probe_a_claim_whose_work_unit_has_no_close_row_fires(tmp_path: Path) -> None:
    """The interval cannot be recomputed from rows that are not there, and that is a defect
    in the declaration rather than a skip: the row asserts a boundary it cannot point at."""
    tree = _probe_tree(
        tmp_path / "orphan",
        [_claim(908, "2026-09-19T14:00:00Z", "#7", "claim_gap=0")],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "no event `close` row carries subject #7" in problems[0], problems


def test_probe_a_close_row_before_the_claim_does_not_answer_it(tmp_path: Path) -> None:
    """A close row of the same subject that PRECEDES the claim is not this claim's close
    row — it closed an earlier taking of the work unit — so the claim is judged orphaned."""
    tree = _probe_tree(
        tmp_path / "earlier-close",
        [
            _close(909, "2026-09-19T13:00:00Z", "#7"),
            _claim(910, "2026-09-19T14:00:00Z", "#7", "claim_gap=0"),
        ],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "at or after n=910" in problems[0], problems


def test_probe_the_close_row_is_resolved_by_subject_not_by_adjacency(tmp_path: Path) -> None:
    """The relation is the WORK UNIT, not the next line. Here the adjacent row is a close of
    a DIFFERENT subject at 60s and the real close of this subject sits nine rows later at
    180s: the declaration is measured against the subject's close. An adjacency reader would
    report a 60s disagreement here, so a clean verdict is the proof."""
    tree = _probe_tree(
        tmp_path / "adjacency",
        [
            _claim(920, "2026-09-19T14:00:00Z", "#7", "claim_gap=180"),
            _close(921, "2026-09-19T14:01:00Z", "#8"),
            _row(922, "2026-09-19T14:01:30Z", "#7", event="dispatch"),
            _close(930, "2026-09-19T14:03:00Z", "#7"),
        ],
    )
    status, reason, problems, _, checked = evaluate(tree)
    assert (status, problems, checked) == ("pass", [], 1), (status, reason, problems)

    wrong = _probe_tree(
        tmp_path / "adjacency-flipped",
        [
            _claim(920, "2026-09-19T14:00:00Z", "#7", "claim_gap=60"),
            _close(921, "2026-09-19T14:01:00Z", "#8"),
            _row(922, "2026-09-19T14:01:30Z", "#7", event="dispatch"),
            _close(930, "2026-09-19T14:03:00Z", "#7"),
        ],
    )
    status, _, problems, _, _ = evaluate(wrong)
    assert status == "fail", (status, problems)
    assert "its close row n=930" in problems[0], problems


def test_probe_a_close_that_precedes_its_claim_in_time_fires(tmp_path: Path) -> None:
    """Row order and wall-clock order can disagree, and the recomputed interval is then
    NEGATIVE. No non-negative declaration can agree with it, so the disagreement arm would
    catch it — but only by accident, and with a message that reports a negative interval as
    though it were an ordinary disagreement. It is named for what it is."""
    tree = _probe_tree(
        tmp_path / "negative",
        [
            _claim(931, "2026-09-19T14:10:00Z", "#7", "claim_gap=0"),
            _close(932, "2026-09-19T14:00:00Z", "#7"),
        ],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "is LATER than its close row n=932" in problems[0], problems


def test_probe_the_earliest_close_of_the_subject_is_the_boundary(tmp_path: Path) -> None:
    """A subject closed twice: the FIRST close at or after the claim answered it, and a
    later close of the same work unit is not the boundary this row declared."""
    tree = _probe_tree(
        tmp_path / "two-closes",
        [
            _claim(940, "2026-09-19T14:00:00Z", "#7", "claim_gap=120"),
            _close(941, "2026-09-19T14:02:00Z", "#7"),
            _close(950, "2026-09-19T15:00:00Z", "#7"),
        ],
    )
    status, reason, problems, _, _ = evaluate(tree)
    assert (status, problems) == ("pass", []), (status, reason, problems)


def test_probe_a_quoted_token_outside_event_claim_is_out_of_the_population(tmp_path: Path) -> None:
    """The n=602 measured need, reproduced: a RULING row whose detail states the token it
    defines is not a row that carries one. Its `claim_gap` is nonsense on purpose — the
    population must never reach it."""
    tree = _probe_tree(
        tmp_path / "quoted",
        [
            _row(
                960,
                "2026-09-19T14:00:00Z",
                "#7",
                event="ruling",
                detail=_claim_detail("claim_gap=99999"),
            ),
            _close(961, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "population is empty" in reason, reason


def test_probe_the_interval_is_read_from_the_trailer_and_not_from_the_prose(tmp_path: Path) -> None:
    """Two scopes, two answers. A `claim_gap` written mid-detail is NOT this row's
    declaration of the field — the canonical run is where a row declares its own fields — so
    a row whose only token sits in its prose declares nothing and FIRES. A private
    whole-detail scan would read the prose value and pass it, which is the direction the
    masking rule forbids."""
    prose = "claim=reconstructed written in one instant; claim_gap=0 in words board=closed"
    assert declared_gap(prose) == (None, "declares no `claim_gap` token in its canonical trailer")
    tree = _probe_tree(
        tmp_path / "prose-only",
        [
            _row(970, "2026-09-19T14:00:00Z", "#7", event="claim", detail=prose),
            _close(971, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "declares no `claim_gap` token" in problems[0], problems


def test_probe_a_pre_boundary_reconstruction_is_excused_not_a_hit(tmp_path: Path) -> None:
    tree = _probe_tree(
        tmp_path / "pre",
        [
            _claim(980, "2026-09-19T12:00:00Z", "#7", "claim_gap=99999"),
            _close(981, "2026-09-19T12:00:01Z", "#7"),
        ],
    )
    status, reason, problems, excused, checked = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert len(excused) == 1, excused
    assert "predates the declared boundary" in excused[0], excused
    assert _PROBE_BOUNDARY in excused[0], excused


def test_probe_the_boundary_comes_from_the_declaration_not_this_file(tmp_path: Path) -> None:
    """The date is READ. The same row is post-boundary under one declaration and
    pre-boundary under another, and this file carries neither."""
    rows = [
        _claim(981, "2026-09-19T14:00:00Z", "#7", "claim_gap=0"),
        _close(982, "2026-09-19T14:00:00Z", "#7"),
    ]
    early = synthetic_tree(
        tmp_path / "early", rows=rows, invariants={INVARIANT_KEY: "2026-09-19T15:00:00Z"}
    )
    late = synthetic_tree(
        tmp_path / "late", rows=rows, invariants={INVARIANT_KEY: "2026-09-19T13:00:00Z"}
    )
    assert evaluate(early)[0] == "skip", "the declared boundary was not applied"
    assert evaluate(late)[0] == "pass", "the declared boundary was not applied"


def test_probe_a_zero_gap_between_two_appends_in_one_second_is_clean(tmp_path: Path) -> None:
    """The law names the zero case explicitly — both appends landing in one second — so a
    gate that treated 0 as a missing value would fire on the shape the law blesses."""
    tree = _probe_tree(
        tmp_path / "zero",
        [
            _claim(990, "2026-09-19T14:00:00Z", "#7", "claim_gap=0"),
            _close(991, "2026-09-19T14:00:00Z", "#7"),
        ],
    )
    status, reason, problems, _, checked = evaluate(tree)
    assert (status, problems, checked) == ("pass", [], 1), (status, reason, problems)


def test_probe_a_tree_with_no_ledger_skips_with_a_stated_reason(tmp_path: Path) -> None:
    status, reason, _, _, _ = evaluate(synthetic_tree(tmp_path / "bare"))
    assert status == "skip" and "no evidence/ledger.jsonl" in reason, (status, reason)


def test_probe_a_tree_with_no_declaration_skips_with_a_stated_reason(tmp_path: Path) -> None:
    """The TEMPLATE's own case: a bootstrapped tree declares no boundary, so the gate SKIPS
    with its reason rather than borrowing this factory's date."""
    tree = synthetic_tree(tmp_path / "undeclared", rows=[_claim(992, "2026-09-19T14:00:00Z", "#7")])
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "ledger-invariants.json" in reason, reason
    assert "DECLARED factory parameter" in reason, reason


def test_probe_a_declaration_missing_this_key_skips(tmp_path: Path) -> None:
    """One declaration file serves every ledger invariant; a key a factory has not declared
    skips for that gate alone."""
    tree = synthetic_tree(
        tmp_path / "other-key",
        rows=[_claim(993, "2026-09-19T14:00:00Z", "#7", "claim_gap=0")],
        invariants={"close_row_revision": "2026-09-19T05:05:49Z"},
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip" and INVARIANT_KEY in reason, (status, reason)


def test_probe_an_empty_ledger_skips(tmp_path: Path) -> None:
    tree = synthetic_tree(tmp_path / "empty", rows=[], invariants={INVARIANT_KEY: _PROBE_BOUNDARY})
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip" and "carries no rows" in reason, (status, reason)


def test_probe_an_empty_population_skips_rather_than_passing(tmp_path: Path) -> None:
    """The population guard is PROPORTIONAL. This is the gate's LIVE state — no
    reconstruction is governed yet — and it must read as a stated skip, never as a clean run
    over nothing."""
    tree = _probe_tree(
        tmp_path / "young",
        [
            _claim(994, "2026-09-19T12:00:00Z", "#7", "claim_gap=99999"),
            _close(995, "2026-09-19T12:00:01Z", "#7"),
        ],
    )
    status, reason, problems, excused, checked = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert "population is empty" in reason, reason
    assert len(excused) == 1, excused


def test_probe_a_defect_is_never_hidden_behind_a_skip(tmp_path: Path) -> None:
    """A row that cannot be DATED is a problem, and it must not be laundered into a stated
    skip: the population guard runs only on an otherwise-clean ledger."""
    tree = _probe_tree(
        tmp_path / "undated",
        [{"n": 996, "ts": "not-a-timestamp", "event": "claim", "subject": "#7",
          "detail": _claim_detail("claim_gap=0")}],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "unparseable ts" in problems[0], problems


def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    """A declared parameter that cannot be read is a DEFECT, not an absence: skipping it
    would hide a broken declaration behind the same output as no declaration at all."""
    tree = synthetic_tree(
        tmp_path / "malformed",
        rows=[_claim(997, "2026-09-19T14:00:00Z", "#7", "claim_gap=0")],
        declaration="{ this is not json",
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail" and problems, (status, problems)
    assert "not valid JSON" in problems[0], problems


def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "bad-date",
        rows=[_claim(998, "2026-09-19T14:00:00Z", "#7", "claim_gap=0")],
        invariants={INVARIANT_KEY: "yesterday"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "not a readable ISO-8601 timestamp" in problems[0], problems


def test_probe_a_corrupt_ledger_line_fails_rather_than_raising(tmp_path: Path) -> None:
    tree = synthetic_tree(tmp_path / "corrupt", invariants={INVARIANT_KEY: _PROBE_BOUNDARY})
    (tree / "evidence/ledger.jsonl").write_text('{"n": 1}\nnot a row\n', encoding="utf-8")
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "is not a JSON row" in problems[0], problems


def test_probe_the_population_guard_is_proportional_and_names_its_own_scope() -> None:
    assert population_reason([], _PROBE_BOUNDARY) is not None
    assert population_reason([{"n": 1}], _PROBE_BOUNDARY) is None
    reason = population_reason([], _PROBE_BOUNDARY) or ""
    assert "claim=reconstructed" in reason, reason
    assert "population is empty" in reason, reason


def test_probe_the_predicate_is_pure_and_offline() -> None:
    """No `gh`, no network, no board list. Asserted on the IMPORTS rather than on prose, so
    a later 'improvement' that adds a board lookup fails here."""
    imports = set(
        re.findall(
            r"^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)",
            Path(__file__).read_text(encoding="utf-8"),
            re.M,
        )
    )
    banned = {"subprocess", "socket", "urllib", "urllib.request", "http", "requests"}
    assert not (imports & banned), sorted(imports & banned)
    assert declared_gap(_claim_detail("claim_gap=7")) == declared_gap(_claim_detail("claim_gap=7"))


def test_probe_the_script_form_prints_its_population(tmp_path: Path, capsys) -> None:
    """Non-vacuity is a property of the PROBE, population visibility of the RUN: the script
    states the rows EXAMINED, the HITS and the EXCUSED set separately, so a clean run and a
    run that examined nothing are never the same output."""
    tree = _probe_tree(
        tmp_path / "printed",
        [
            _claim(980, "2026-09-19T12:00:00Z", "#7", "claim_gap=99999"),
            _claim(999, "2026-09-19T14:00:00Z", "#7", "claim_gap=300"),
            _close(1000, "2026-09-19T14:05:00Z", "#7"),
        ],
    )
    assert main(tree) == 0
    out = capsys.readouterr().out
    assert "excused: n=980" in out, out
    assert "1 reconstructed claim(s) examined" in out, out
    assert "0 hit(s)" in out, out


def main(repo: Path = REPO) -> int:
    """Script form: the same verdict, with the population and the excused set on STDOUT.

    `repo` is a parameter so a probe can exercise the printed form against a synthetic tree
    — the TEMPLATE twin has no ledger of its own to print.
    """
    status, reason, problems, excused, checked = evaluate(repo)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"claim-gap gate: SKIP — {reason}")
        return 0
    if status == "fail":
        print("claim-gap gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"claim-gap gate: clean — {checked} reconstructed claim(s) examined, "
        f"{len(problems)} hit(s), {len(excused)} excused (pre-boundary)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
