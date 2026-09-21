#!/usr/bin/env python3
"""Gate: every close row declares WHICH writer produced its telemetry.

`tools/ledger.py`'s close guard fills five measurement keys — `cost_usd`, `tokens_in`,
`tokens_out`, `turns`, `duration` — from a window it MEASURED, and it skips any key the
author has already declared. So the numbers in a close row have two possible writers: the
tool, and the author. Until #130 nothing in the row said which, and no structural read of
a row can settle it: HQ measured all three candidate predicates — position, completeness
and value equality — and each FAILED. A `duration=` the author typed read exactly like one
the tool took.

The repair is that the WRITER states it. The close guard appends `telemetry=measured` when
it contributed the values, `telemetry=typed` when it contributed nothing, and
`telemetry=unavailable` when it had no window basis at all (#129's spelling). The field is
deliberately NOT one of `field_predicate.TELEMETRY_KEYS`: it declares no measurement, so it
must not enter an aggregate that sums or counts them — `rework`'s reason, and the writer's
own comment says so.

THE INVARIANT: every `close` row in the main ledger at or after the declared boundary
declares EXACTLY ONE `telemetry=` value, in its CANONICAL TRAILER, and that value is one of
the three the writer can produce. Exactly one, because two tokens for one field have no
canonical reading (`skills/meta-factory/SKILL.md` section 8). In the trailer, because that
is where a DECLARATION lives and a token quoted mid-sentence is prose — the positional rule
`declared_rework` uses, and the reason both sides of this gate's question are read from ONE
surface through `declared_telemetry_provenance`.

WHY THE POPULATION IS EVERY CLOSE ROW, NOT ONLY THOSE DECLARING A MEASUREMENT
--------------------------------------------------------------------------------
The narrower predicate — *a close row that declares a measurement must declare its
provenance too* — is the shape the harm took, and it is strictly WEAKER. The guard appends
its token on all three branches, so every close row it writes carries one, and a predicate
that reads only rows which already declare a measurement cannot see the case where the
guard never ran at all. This gate asserts the WRITER'S OWN GUARANTEE instead: one token,
one of three values, on every close row. It needs no key list to state, and it is
satisfiable by construction rather than by convention.

The boundary is DECLARED, and this file SHIPS (issue #78, ruled n=515 clause 4)
-------------------------------------------------------------------------------
The invariant date is not a module constant. The LOGIC is universal — *a close row states
which writer produced its telemetry* — while the PARAMETERS are factory-specific: the
boundary date, and the ledger read. `TEMPLATE/` does not carry `evidence/ledger.jsonl` (the
ledger is BOOTSTRAP-created), so a copy of this file with a hardcoded date RED in the tree
it ships to — #76's class, P35. So the boundary is DECLARED in the factory's own
`docs/ledger-invariants.json` and read through `tests/ledger_boundary.py`, shared with
`test_close_row_revision.py` and `test_score_gate_recorded.py` so the class has ONE
implementation. The skeleton ships (`TEMPLATE/docs/ledger-invariants.example.json`), the
filled file does not, and the gate asserts the CORRESPONDENCE rather than a fixed state.

Three outcomes, and the difference between them is the point:

* **skip** — this tree legitimately has nothing to judge: no ledger, an empty ledger, no
  declaration, no declared boundary, or no `close` row at or after it. Printed as
  `SKIP: <reason>`, exit 0, the reason stated.
* **fail** — a post-boundary `close` row that declares no provenance, more than one, or a
  value outside the writer's vocabulary; or a declaration this tree cannot honour
  (malformed JSON, an unreadable date, a corrupt ledger line). A declared parameter that
  cannot be read is a defect, not an absence, so it never skips.
* **pass** — a non-empty population, every row carrying exactly one legal provenance.

The population is PRINTED on every run (P29): a clean verdict over a population that was
never named is indistinguishable from one that examined nothing, and this gate's live
population is a small tail of the ledger, so the count is the reader's only signal that it
examined anything at all.

The invariant is factored into `close_telemetry_provenance_problems()` so synthetic rows
can probe it: a rule that has only ever seen good input has not been shown to reject bad
input.

Run:  python3 -m pytest tests/test_close_telemetry_provenance.py -q
Exit: 0 clean, fully excused, or skipped-with-reason; non-zero on any post-boundary close
      row without exactly one legal `telemetry=` declaration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    boundary_and_rows,
    parse_ts,
    population_skip_reason,
    post_boundary_rows,
    synthetic_tree,
)

REPO = Path(__file__).resolve().parent.parent

# `ledger_boundary` has already put `tools/` on the path — the same bare-neighbour import
# every gate and tool here uses, because a bootstrapped factory has `tools/` and `tests/`
# as siblings with no `__init__.py` in either.
from field_predicate import (  # noqa: E402
    TELEMETRY_PROVENANCE_VALUES,
    declared_telemetry_provenance,
)

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name, so the declaration says
# which invariant each date belongs to.
INVARIANT_KEY = "close_telemetry_provenance"

PROVENANCE_KEY = "telemetry="


def close_telemetry_provenance_problems(
    rows: list[dict], boundary_text: str
) -> tuple[list[str], list[str]]:
    """`(problems, excused)` over `rows` — the invariant, pure, so it can be probed.

    `rows` is every row of a ledger, not a filtered population: the event filter and the
    boundary are part of the rule, so a probe cannot satisfy it by pre-filtering. A row
    before the boundary is EXCUSED by name and never called clean — the distinction
    `tools/ledger.py` already draws for its own legacy closes, so that "clean" and
    "excused" are never the same output.
    """
    problems: list[str] = []
    excused: list[str] = []
    boundary = parse_ts(boundary_text)

    for row in rows:
        if row.get("event") != "close":
            continue
        n = row.get("n")
        ts = row.get("ts", "")
        try:
            when = parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"n={n}: unparseable ts {ts!r}")
            continue
        if when < boundary:
            excused.append(
                f"n={n} ({ts}) predates the declared boundary ({boundary_text})"
            )
            continue
        detail = str(row.get("detail") or "")
        declared = declared_telemetry_provenance(detail)
        if not declared:
            problems.append(
                f"n={n} ({ts}) declares no telemetry= provenance in its canonical "
                f"trailer — a reader cannot tell a value the tool TOOK from one the "
                f"author TYPED (#130)"
            )
        elif len(declared) > 1:
            problems.append(
                f"n={n} ({ts}) declares {len(declared)} telemetry= values "
                f"({', '.join(declared)}) — two tokens for one field have no canonical "
                f"reading (SKILL.md section 8)"
            )
        elif declared[0] not in TELEMETRY_PROVENANCE_VALUES:
            problems.append(
                f"n={n} ({ts}) declares telemetry={declared[0]}, which is not one of "
                f"the writer's values {list(TELEMETRY_PROVENANCE_VALUES)}"
            )

    return problems, excused


def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], int]:
    """`(status, reason, problems, excused, checked)` over `repo` — the probe-able core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip:
    the population guard runs only on an otherwise-clean ledger, so a defect is never
    hidden behind "there was nothing to judge".
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], 0
    except GateError as exc:
        return "fail", "", list(exc.problems), [], 0

    problems, excused = close_telemetry_provenance_problems(rows, boundary_text)
    if problems:
        return "fail", "", problems, excused, 0

    population = post_boundary_rows(rows, boundary, "close")
    reason = population_skip_reason(population, boundary_text, "close")
    if reason:
        return "skip", reason, [], excused, 0
    return "pass", "", [], excused, len(population)


# --- live gate -------------------------------------------------------------------


def test_live_ledger_records_the_telemetry_provenance() -> None:
    status, reason, problems, excused, checked = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "close rows written after the declared boundary must declare exactly one "
            "legal telemetry= provenance:\n  " + "\n  ".join(problems)
        )
    print(
        f"close-telemetry provenance gate: {checked} post-boundary close row(s) "
        f"verified, {len(excused)} excused (pre-boundary)"
    )


# --- probes: the tree the gate runs in, then the predicate it applies --------------


def _close(n: int, ts: str, detail: str) -> dict:
    return {
        "n": n,
        "ts": ts,
        "event": "close",
        "actor": "worker",
        "subject": "#1",
        "detail": detail,
    }


_OK = {
    "n": 900,
    "ts": "2026-09-21T06:00:00Z",
    "event": "close",
    "actor": "worker",
    "subject": "#1",
    "detail": "CLOSE -- #1, the thing is done. board=closed head=deadbeef985b "
    "cost_usd=1.0000 tokens_in=10 tokens_out=20 turns=2 duration=5s telemetry=measured",
}
_PROBE_BOUNDARY = "2026-09-21T05:00:00Z"


def test_probe_a_tree_with_no_ledger_skips_with_a_stated_reason(tmp_path: Path) -> None:
    """`TEMPLATE/evidence/` does not exist — the ledger is BOOTSTRAP-created. A gate
    that RAISED here was RED on the very tree it ships to (#78, #76's class)."""
    status, reason, problems, _, _ = evaluate(synthetic_tree(tmp_path / "bare"))
    assert status == "skip", (status, reason, problems)
    assert "evidence/ledger.jsonl" in reason and "BOOTSTRAP" in reason, reason


def test_probe_a_tree_with_no_declared_boundary_skips_with_a_stated_reason(
    tmp_path: Path,
) -> None:
    """A factory that has not adopted the invariant has no boundary to judge against —
    and that is a STATED skip, never a silent pass and never a foreign boundary."""
    tree = synthetic_tree(
        tmp_path / "undeclared",
        rows=[_close(1, "2026-09-21T06:00:00Z", _OK["detail"])],
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "ledger-invariants.json" in reason and "DECLARED factory parameter" in reason, reason


def test_probe_a_synthetic_tree_fails_a_row_without_the_provenance(
    tmp_path: Path,
) -> None:
    """THE PROPERTY SURVIVES THE DECLARED FORM. Making the boundary a parameter must not
    cost the gate its teeth: a post-boundary close row declaring a measurement and no
    provenance still FAILS — this is #130's own class."""
    tree = synthetic_tree(
        tmp_path / "offending",
        rows=[
            _close(
                1,
                "2026-09-21T06:00:00Z",
                "CLOSE -- #1 done. head=deadbeef985b cost_usd=1.0000 duration=5s",
            )
        ],
        invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert problems and "telemetry=" in problems[0], problems


def test_probe_a_compliant_synthetic_tree_passes(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "compliant",
        rows=[_close(_OK["n"], _OK["ts"], _OK["detail"])],
        invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
    )
    status, reason, problems, _, checked = evaluate(tree)
    assert (status, problems) == ("pass", []), (status, reason, problems)
    assert checked == 1, checked


def test_probe_the_boundary_comes_from_the_declaration_not_this_file(
    tmp_path: Path,
) -> None:
    """(b): the date is READ. The same row is post-boundary under one declaration and
    pre-boundary under another, and this file carries neither."""
    row = _close(1, "2026-09-21T06:00:00Z", "CLOSE -- #1 done. head=deadbeef985b")
    early = synthetic_tree(
        tmp_path / "early", rows=[row], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    late = synthetic_tree(
        tmp_path / "late",
        rows=[row],
        invariants={INVARIANT_KEY: "2026-09-21T07:00:00Z"},
    )
    assert evaluate(early)[0] == "fail", "the declared boundary was not applied"
    status, _, problems, excused, _ = evaluate(late)
    assert (status, problems) == ("skip", []), (status, problems)
    assert excused and "2026-09-21T07:00:00Z" in excused[0], excused


def test_probe_an_empty_population_skips_rather_than_passing(tmp_path: Path) -> None:
    """(c), PROPORTIONAL: a young factory whose history predates the boundary — or holds
    no close at all — skips with its reason instead of passing vacuously."""
    tree = synthetic_tree(
        tmp_path / "young",
        rows=[_close(1, "2026-09-21T04:00:00Z", "CLOSE -- #1 done. head=deadbeef985b")],
        invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
    )
    status, reason, problems, excused, checked = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert "population is empty" in reason, reason
    assert len(excused) == 1, excused


def test_probe_an_empty_ledger_skips(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "empty-ledger", rows=[], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip" and "carries no rows" in reason, (status, reason)


def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    """A declared parameter that cannot be read is a DEFECT, not an absence: skipping it
    would hide a broken declaration behind the same output as no declaration."""
    tree = synthetic_tree(
        tmp_path / "malformed",
        rows=[_close(_OK["n"], _OK["ts"], _OK["detail"])],
        declaration="{ this is not json",
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail" and problems, (status, problems)
    assert "not valid JSON" in problems[0], problems


def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "bad-date",
        rows=[_close(_OK["n"], _OK["ts"], _OK["detail"])],
        invariants={INVARIANT_KEY: "yesterday"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "not a readable ISO-8601 timestamp" in problems[0], problems


def test_probe_a_corrupt_ledger_line_fails_rather_than_raising(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "corrupt", invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    (tree / "evidence/ledger.jsonl").write_text('{"n": 1}\nnot a row\n', encoding="utf-8")
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "is not a JSON row" in problems[0], problems


# --- probes: the invariant must reject bad input, not only accept good -------------


def test_probe_accepts_a_compliant_row() -> None:
    problems, excused = close_telemetry_provenance_problems([_OK], _PROBE_BOUNDARY)
    assert problems == [] and excused == [], (problems, excused)


def test_probe_rejects_a_row_without_the_provenance() -> None:
    """#130's own class: a close row declaring a measurement and no provenance."""
    row = {
        **_OK,
        "detail": "CLOSE -- #1 done. board=closed head=deadbeef985b duration=5s turns=2",
    }
    problems, _ = close_telemetry_provenance_problems([row], _PROBE_BOUNDARY)
    assert problems and "telemetry=" in problems[0], problems


def test_probe_rejects_a_row_carrying_two_provenances() -> None:
    """Two tokens for one field have no canonical reading (SKILL.md section 8)."""
    row = {
        **_OK,
        "detail": "CLOSE -- #1 done. head=deadbeef985b telemetry=measured telemetry=typed",
    }
    problems, _ = close_telemetry_provenance_problems([row], _PROBE_BOUNDARY)
    assert problems and "2 telemetry= values" in problems[0], problems


def test_probe_rejects_a_value_outside_the_writers_vocabulary() -> None:
    row = {**_OK, "detail": "CLOSE -- #1 done. head=deadbeef985b telemetry=handwritten"}
    problems, _ = close_telemetry_provenance_problems([row], _PROBE_BOUNDARY)
    assert problems and "not one of the writer's values" in problems[0], problems


def test_probe_a_prose_mention_is_not_a_declaration() -> None:
    """The read is POSITIONAL, matching `declared_rework`: a token quoted mid-sentence is
    prose and cannot satisfy the invariant. This is the case that made the two historical
    `telemetry=` mentions (`n=828`, `n=830`) read as absent — correctly."""
    row = {
        **_OK,
        "detail": (
            "CLOSE -- #1, the guard now adds an else: that states telemetry=unavailable "
            "instead of inventing a window. head=deadbeef985b"
        ),
    }
    problems, _ = close_telemetry_provenance_problems([row], _PROBE_BOUNDARY)
    assert problems and "telemetry=" in problems[0], problems


def test_probe_excuses_pre_boundary_rows_without_calling_them_clean() -> None:
    """`n=828`'s shape: a close row carrying `duration=1935s` and no provenance, written
    before the guard landed. It is EXCUSED by name, never repaired and never called clean
    — a value reconstructed after the fact is a falsified record, not a repair."""
    legacy = {
        "n": 828,
        "ts": "2026-09-21T02:38:26Z",
        "event": "close",
        "subject": "#129",
        "detail": "CLOSE -- #129, the import chain is collapsed. cost_usd=5.7272 duration=1935s",
    }
    problems, excused = close_telemetry_provenance_problems([legacy], _PROBE_BOUNDARY)
    assert problems == [], problems
    assert len(excused) == 1 and "predates the declared boundary" in excused[0], excused


def test_probe_ignores_non_close_events() -> None:
    """A `claim` row is outside the population entirely — `n=830` is one, and its
    mid-sentence `telemetry=` mention must not be read as a declaration either way."""
    other = {
        "n": 901,
        "ts": "2026-09-21T06:00:00Z",
        "event": "claim",
        "detail": "Claimed by the Worker lane. IMPLEMENTING HQ's ruling: states telemetry=unavailable.",
    }
    problems, excused = close_telemetry_provenance_problems([other], _PROBE_BOUNDARY)
    assert problems == [] and excused == [], (problems, excused)
