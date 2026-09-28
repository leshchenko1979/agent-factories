#!/usr/bin/env python3
"""Gate: a measurement run records its closing workspace-gate verdict.

Origin (issue #32). The measurement run could end with an uncommitted score file:
step 7 committed the report, later re-read corrections landed after that commit, and
no step re-checked the tree. The workspace gate already existed (`tools/hygiene.py
--audit`, repaired by #28) but the run never invoked it — a gate that exists and does
not run is dead text (P29). Step 7 now requires it, and this gate makes that
requirement *checkable* instead of asserted: the difference between a procedure that
says it and a rule that is upheld.

The rule, in two parts:

1. **Every `score` row written on or after the invariant landed carries the closing
   verdict** — `workspace_gate=rc=0` — and the HEAD sha the run committed at
   (`head=<sha>`). A run that skipped the gate leaves no verdict, so the absence is
   the signal; the sha makes the row checkable against the repository rather than a
   claim about a tree that has since moved.
2. **Rows written before the invariant are excused, and said so.** They are reported
   as `excused:` with their count, never folded into a bare "clean" — the convention
   `tools/ledger.py` already uses for its own legacy closes, so that "clean" and
   "excused" are never the same output. Nothing is backfilled: a verdict written today
   for a run that predates the rule would be a falsified record, not a repair.

The boundary is DECLARED, and this file SHIPS (issue #78, ruled n=515 clause 4)
-------------------------------------------------------------------------------
This file used to carry the invariant date as a module constant —
`INVARIANT_LANDED = "2026-09-18T10:04:05Z"  # commit 9552947`. That is the meta-factory's
own history, and a bootstrapped factory has a different one; worse, the file reads
`evidence/ledger.jsonl`, which `TEMPLATE/` does not carry at all (the ledger is
BOOTSTRAP-created). So a copy of this file RED in the tree it ships to — #76's class, and
#78 is its second instance: **a byte-paired gate asserting a live-tree fact its own tree
cannot satisfy** (P35).

The ruled form splits the two halves. The LOGIC is universal — *a run records the gate it
ran and the revision it committed at* — while the PARAMETERS are factory-specific: the
boundary date, and the ledger read. So the boundary is DECLARED in the factory's own
`docs/ledger-invariants.json` and read through `tests/ledger_boundary.py`, shared with
`test_close_row_revision.py` so the class has ONE implementation. The shape mirrors #69
(`docs/products.json` + `docs/products.example.json`): the skeleton ships, the filled file
does not, and the gate asserts the CORRESPONDENCE rather than a fixed state.

Three outcomes, and the difference between them is the point:

* **skip** — this tree legitimately has nothing to judge: no ledger, an empty ledger, no
  declaration, no declared boundary, or no `score` row at or after it. Printed as
  `SKIP: <reason>`, exit 0, the reason stated.
* **fail** — a post-boundary `score` row missing part of the verdict, or a declaration
  this tree cannot honour (malformed JSON, an unreadable date, a corrupt ledger line). A
  declared parameter that cannot be read is a defect, not an absence, so it never skips.
* **pass** — a non-empty population, every row carrying both halves of the verdict.

The invariant is factored into `score_gate_problems()` so synthetic rows can probe it:
a rule that has only ever seen good input has not been shown to reject bad input.

Run:  python3 -m pytest tests/test_score_gate_recorded.py -q
Exit: 0 clean, fully excused, or skipped-with-reason; non-zero on any post-boundary row
      without a verdict.
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

# THE SHARED PREDICATE, not a private scan (#215). Both legs of this gate read a field
# that `tools/field_predicate.py` already owns, and this file had its own answer for each:
# a substring test for the verdict and `_has_head_sha` for the revision. Two readers for
# one field is the class section 11 codifies against, and here it was worse than
# duplication — the private forms asked whether a token APPEARS IN THE TEXT while the law
# asks whether the row DECLARES it, so a row that merely MENTIONED the verdict satisfied
# the leg that exists to require it.
sys.path.insert(0, str(REPO / "tools"))
from field_predicate import (  # noqa: E402
    declared_revision,
    keyed_value,
    trailer_tokens,
)

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name, so the declaration says
# which invariant each date belongs to.
INVARIANT_KEY = "score_gate_recorded"

VERDICT_KEY = "workspace_gate=rc=0"
# The verdict's two halves, named so the check reads the FIELD and VALUE separately: the
# canonical run must declare `workspace_gate` WITH the value `rc=0`. Declaring the key with
# a different value is a FAILING gate, which is a finding rather than a pass.
VERDICT_FIELD = "workspace_gate"
VERDICT_VALUE = "rc=0"

# THE SECOND LAWFUL VERDICT (#201, ruled 2026-09-28). The closing-invariant clause admits
# two verdicts, because on a shared tree a run's OWN artifacts can be committed and clean
# while an unrelated lane holds a tracked file past the grace window: `hygiene.py --audit`
# then returns rc=1 correctly for the whole tree, and the law says that is NOT this run's
# defect. The run records that state instead of forging a clean.
#
# The token is DELIBERATELY NOT `rc=0-blocked-by-unowned`: embedding `rc=0` lets a reader
# scan past it as a clean run, and the whole point of the second verdict is that it must
# never be readable as one.
#
# AND IT IS LAWFUL ONLY WHEN THE ROW NAMES THE BLOCKING PATHS (#201 ruling point 3). A
# token without the paths is an unexaminable excuse — nothing can re-read it, so the
# blocked verdict would become the back door the ruling refused as shape (a). Naming the
# paths is what gives the standing patrol something to cross-read against the live tree.
VERDICT_BLOCKED_VALUE = "blocked-by-unowned"
BLOCKED_PATHS_KEY = "blocked_paths"

def _verdict_declared(detail: str) -> bool:
    """True when `detail`'s CANONICAL RUN declares a LAWFUL workspace-gate verdict.

    Read through the shared predicate rather than over the whole text, because the law's
    definition of a declaration is positional: the canonical run is the row's trailer, and
    a token outside it is a QUOTATION. A row that says "no `workspace_gate=rc=0` was
    written here" satisfies a substring test while carrying no verdict at all — so the
    more lawfully a run REFUSES the token, the blinder a lexical leg becomes (#215).

    Two verdicts are lawful, and the second carries a condition (#201):

      * `workspace_gate=rc=0` — the run's own closing gate was clean;
      * `workspace_gate=blocked-by-unowned` — the gate was blocked by paths this run does
        not own, AND the row names them. The token without the paths is refused here, so
        an excuse that cannot be re-read never reads as a verdict.

    A third value (a failing gate, say `rc=1`) is NOT lawful and is reported as a missing
    verdict: a run whose gate genuinely failed must record that as a defect, not as a pass
    and not as a foreign block.
    """
    tokens = trailer_tokens(detail)
    for token in tokens:
        value = keyed_value(token, VERDICT_FIELD)
        if value == VERDICT_VALUE:
            return True
        if value == VERDICT_BLOCKED_VALUE:
            return any(
                (keyed_value(t, BLOCKED_PATHS_KEY) or "").strip(" ,")
                for t in tokens
            )
    return False

def score_gate_problems(
    rows: list[dict], boundary_text: str
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the `score` rows of a ledger.

    `problems` names every post-boundary score row missing part of the verdict;
    `excused` names every pre-boundary row, so the two are never conflated.
    `boundary_text` is the DECLARED boundary verbatim, so an excused line quotes the date
    the factory declared rather than one this file carries.
    """
    boundary = parse_ts(boundary_text)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        if row.get("event") != "score":
            continue
        n, ts = row.get("n"), row.get("ts", "")
        try:
            when = parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"n={n}: unparseable ts {ts!r}")
            continue
        if when < boundary:
            excused.append(f"n={n} ({ts}) predates the declared boundary ({boundary_text})")
            continue
        detail = str(row.get("detail") or "")
        missing = []
        if not _verdict_declared(detail):
            missing.append(VERDICT_KEY)
        if declared_revision(detail) is None:
            missing.append("head=<sha>")
        if missing:
            problems.append(f"n={n} ({ts}) missing {' and '.join(missing)}")

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

    problems, excused = score_gate_problems(rows, boundary_text)
    if problems:
        return "fail", "", problems, excused, 0

    population = post_boundary_rows(rows, boundary, "score")
    reason = population_skip_reason(population, boundary_text, "score")
    if reason:
        return "skip", reason, [], excused, 0
    return "pass", "", [], excused, len(population)

# --- live gate -------------------------------------------------------------------

def test_live_ledger_records_the_closing_verdict() -> None:
    status, reason, problems, excused, checked = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "score rows written after the declared boundary must carry the "
            "workspace-gate verdict and the committed HEAD sha:\n  "
            + "\n  ".join(problems)
        )
    print(
        f"score-gate verdict gate: {checked} post-boundary score row(s) verified, "
        f"{len(excused)} excused (pre-boundary)"
    )

# --- probes: the tree the gate runs in, then the predicate it applies --------------

def _score(n: int, ts: str, detail: str) -> dict:
    return {"n": n, "ts": ts, "event": "score", "actor": "surveys", "subject": "survey", "detail": detail}

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
        rows=[_score(1, "2026-09-19T06:00:00Z", "survey-2026-09-19")],
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "ledger-invariants.json" in reason and "DECLARED factory parameter" in reason, reason

def test_probe_a_synthetic_tree_fails_a_row_without_the_verdict(tmp_path: Path) -> None:
    """THE PROPERTY SURVIVES THE DECLARED FORM. Making the boundary a parameter must not
    cost the gate its teeth: a post-boundary score row with no verdict still FAILS."""
    tree = synthetic_tree(
        tmp_path / "offending",
        rows=[_score(1, "2026-09-19T06:00:00Z", "survey-2026-09-19 — head=deadbeef985b")],
        invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert problems and VERDICT_KEY in problems[0], problems

def test_probe_a_compliant_synthetic_tree_passes(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "compliant",
        rows=[_score(1, "2026-09-19T06:00:00Z", _OK["detail"])],
        invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"},
    )
    status, reason, problems, _, checked = evaluate(tree)
    assert (status, problems) == ("pass", []), (status, reason, problems)
    assert checked == 1, checked

def test_probe_the_boundary_comes_from_the_declaration_not_this_file(
    tmp_path: Path,
) -> None:
    """(b): the date is READ. The same row is post-boundary under one declaration and
    pre-boundary under another, and this file carries neither."""
    row = _score(1, "2026-09-19T06:00:00Z", "survey-2026-09-19")
    early = synthetic_tree(
        tmp_path / "early", rows=[row], invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"}
    )
    late = synthetic_tree(
        tmp_path / "late", rows=[row], invariants={INVARIANT_KEY: "2026-09-19T07:00:00Z"}
    )
    assert evaluate(early)[0] == "fail", "the declared boundary was not applied"
    status, _, problems, excused, _ = evaluate(late)
    assert (status, problems) == ("skip", []), (status, problems)
    assert excused and "2026-09-19T07:00:00Z" in excused[0], excused

def test_probe_an_empty_population_skips_rather_than_passing(tmp_path: Path) -> None:
    """(c), PROPORTIONAL: a young factory whose history predates the boundary — or holds
    no score at all — skips with its reason instead of passing vacuously."""
    tree = synthetic_tree(
        tmp_path / "young",
        rows=[_score(1, "2026-09-19T04:00:00Z", "survey-2026-09-19")],
        invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"},
    )
    status, reason, problems, excused, checked = evaluate(tree)
    assert (status, problems, checked) == ("skip", [], 0), (status, reason, problems)
    assert "population is empty" in reason, reason
    assert len(excused) == 1, excused

def test_probe_an_empty_ledger_skips(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "empty-ledger", rows=[], invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"}
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip" and "carries no rows" in reason, (status, reason)

def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    """A declared parameter that cannot be read is a DEFECT, not an absence: skipping it
    would hide a broken declaration behind the same output as no declaration."""
    tree = synthetic_tree(
        tmp_path / "malformed",
        rows=[_score(1, "2026-09-19T06:00:00Z", _OK["detail"])],
        declaration="{ this is not json",
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail" and problems, (status, problems)
    assert "not valid JSON" in problems[0], problems

def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "bad-date",
        rows=[_score(1, "2026-09-19T06:00:00Z", _OK["detail"])],
        invariants={INVARIANT_KEY: "yesterday"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "not a readable ISO-8601 timestamp" in problems[0], problems

def test_probe_a_corrupt_ledger_line_fails_rather_than_raising(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "corrupt", invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"}
    )
    (tree / "evidence/ledger.jsonl").write_text('{"n": 1}\nnot a row\n', encoding="utf-8")
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert "is not a JSON row" in problems[0], problems

# --- probes: the invariant must reject bad input, not only accept good ------------

_OK = {
    "n": 900,
    "ts": "2026-09-19T06:00:00Z",
    "event": "score",
    "detail": "survey-2026-09-19 — workspace_gate=rc=0 head=deadbeef985b0f1a6c8919c362a0a56ec7d0d42e",
}

_PROBE_BOUNDARY = "2026-09-19T05:00:00Z"

def test_probe_accepts_a_compliant_row() -> None:
    problems, excused = score_gate_problems([_OK], _PROBE_BOUNDARY)
    assert problems == [] and excused == []

def test_probe_rejects_a_row_without_the_verdict() -> None:
    row = {**_OK, "detail": "survey-2026-09-19 — head=deadbeef985b0f1a6c8919c362a0a56ec7d0d42e"}
    problems, _ = score_gate_problems([row], _PROBE_BOUNDARY)
    assert problems and VERDICT_KEY in problems[0], problems

def test_probe_rejects_a_failing_verdict() -> None:
    row = {**_OK, "detail": "survey-2026-09-19 — workspace_gate=rc=1 head=deadbeef985b0"}
    problems, _ = score_gate_problems([row], _PROBE_BOUNDARY)
    assert problems, "a failing workspace gate must not read as a recorded pass"

def test_probe_rejects_a_row_without_the_head_sha() -> None:
    row = {**_OK, "detail": "survey-2026-09-19 — workspace_gate=rc=0"}
    problems, _ = score_gate_problems([row], _PROBE_BOUNDARY)
    assert problems and "head=<sha>" in problems[0], problems

def test_probe_excuses_pre_boundary_rows_without_calling_them_clean() -> None:
    legacy = {
        "n": 179,
        "ts": "2026-09-18T07:04:29Z",
        "event": "score",
        "detail": "survey-2026-09-18-third-read",
    }
    problems, excused = score_gate_problems([legacy], _PROBE_BOUNDARY)
    assert problems == [], problems
    assert len(excused) == 1 and "predates the declared boundary" in excused[0], excused

def test_probe_ignores_non_score_events() -> None:
    other = {"n": 901, "ts": "2026-09-19T06:00:00Z", "event": "dispatch", "detail": "x"}
    problems, excused = score_gate_problems([other], _PROBE_BOUNDARY)
    assert problems == [] and excused == []

# --- the legs' POSITIONAL reads (#215) ------------------------------------------
#
# Every specimen below ends in a VALID `head=<sha>`, deliberately. The row must be judged
# on the leg under test, so the OTHER leg is satisfied by construction — a probe that let
# both legs fail could not tell which predicate caught the row, and the whole defect is
# that the verdict leg went blind while the head leg kept working (the real `n=1458` is
# exactly that shape: it fails on `head=<sha>` ALONE today).
_STAMP = "head=deadbeef985b0f1a6c8919c362a0a56ec7d0d42e"

def _specimen(detail: str) -> list[dict]:
    return [{**_OK, "detail": detail}]

def test_probe_AC1_a_row_mentioning_nothing_fails() -> None:
    """Specimen A — the positive control: nothing is mentioned, so the leg bites."""
    problems, _ = score_gate_problems(_specimen(f"survey-2026-09-19 — {_STAMP}"), _PROBE_BOUNDARY)
    assert problems and VERDICT_KEY in problems[0], problems

def test_probe_AC1_a_row_QUOTING_the_token_in_prose_fails() -> None:
    """Specimen B — the law's own honest refusal. It must NOT satisfy the leg.

    The canonical run here is `[head=<sha>]` alone: the token appears mid-sentence, so it
    is a quotation. A lexical leg accepts it (that was the defect); the positional leg must
    not, or the more lawfully a row explains its refusal, the blinder the gate becomes.
    """
    problems, _ = score_gate_problems(
        _specimen(
            "survey-2026-09-19 — writing workspace_gate=rc=0 would forge a verdict the "
            f"tool did not return, so none was written {_STAMP}"
        ),
        _PROBE_BOUNDARY,
    )
    assert problems and VERDICT_KEY in problems[0], problems

def test_probe_AC1_a_row_mentioning_the_token_in_prose_fails() -> None:
    """Specimen D — a bare mention, same shape as B with plainer wording."""
    problems, _ = score_gate_problems(
        _specimen(f"survey-2026-09-19 — we did not record workspace_gate=rc=0 today {_STAMP}"),
        _PROBE_BOUNDARY,
    )
    assert problems and VERDICT_KEY in problems[0], problems

def test_probe_AC1_a_row_DECLARING_the_token_in_the_run_passes() -> None:
    """Specimen E — the real declaration at the end. This is the leg that must keep passing."""
    problems, excused = score_gate_problems(
        _specimen(f"survey-2026-09-19 — workspace_gate=rc=0 {_STAMP}"), _PROBE_BOUNDARY
    )
    assert problems == [] and excused == [], (problems, excused)

def test_probe_AC1_a_row_QUOTING_a_foreign_sha_fails() -> None:
    """Specimen G — the sha is quoted from elsewhere, so neither leg reads a declaration."""
    problems, _ = score_gate_problems(
        _specimen(
            "survey-2026-09-19 — n=565 quotes head=4ae1ffdb0987654321ff in prose workspace_gate=rc=0"
        ),
        _PROBE_BOUNDARY,
    )
    assert problems and "head=<sha>" in problems[0], problems

def test_probe_AC2_the_REAL_row_1458_is_caught_by_the_VERDICT_leg() -> None:
    """AC2 (reverse leg) — driven over the live ledger, asserted on the LEG.

    `n=1458` fails on `head=<sha>` ALONE under the old predicate, so a probe counting FAIL
    passes while the defect is fully present: the specimen must name WHICH leg caught it.
    This asserts the VERDICT leg, which is the half the fix moves.
    """
    try:
        _, _, rows = boundary_and_rows(REPO, INVARIANT_KEY)
    except SkipGate as exc:
        # A tree with no ledger has no row to drive. That is a STATED inability, not a
        # failure and not a silent pass: this probe's population is a real row, and the
        # shipped tree carries none (the ledger is bootstrap-created). The reason NAMES
        # what is absent, so this skip is never indistinguishable from a clean run.
        pytest.skip("the AC2 specimen is a live ledger row and this tree carries none: %s" % exc)
    target = next((r for r in rows if r.get("n") == 1458), None)
    if target is None:
        pytest.skip(
            "n=1458 is not in this ledger — the probe could not reach its population "
            "(a ledger that has not grown to that row is not a defect)"
        )
    problems, _ = score_gate_problems([target], "2020-01-01T00:00:00Z")
    assert problems, "n=1458 must fail"
    assert VERDICT_KEY in problems[0], (
        "n=1458 must be caught by the VERDICT leg, not only by head= — got: %r" % problems
    )

def test_probe_AC4_a_nameABLE_row_missing_the_paths_fails() -> None:
    """#201 — the blocked verdict is lawful only when the row NAMES the blocking paths.

    A token without the paths is an unexaminable excuse: nothing can re-read it, so it
    would become the back door the ruling refused. The same row WITH paths passes, which
    is what shows the refusal discriminates rather than rejecting the token outright.
    """
    unnamed, _ = score_gate_problems(
        _specimen(f"survey-2026-09-19 — workspace_gate=blocked-by-unowned {_STAMP}"),
        _PROBE_BOUNDARY,
    )
    assert unnamed and VERDICT_KEY in unnamed[0], unnamed

    named, excused = score_gate_problems(
        _specimen(
            "survey-2026-09-19 — workspace_gate=blocked-by-unowned "
            "blocked_paths=evidence/census-2026-09-28.md,evidence/other.md "
            f"{_STAMP}"
        ),
        _PROBE_BOUNDARY,
    )
    assert named == [] and excused == [], (named, excused)

def test_probe_AC4_the_two_verdicts_are_NOT_confusable() -> None:
    """The blocked token must never read as a clean run, and a failing gate never passes."""
    clean, _ = score_gate_problems(
        _specimen(f"survey-2026-09-19 — workspace_gate=rc=0 {_STAMP}"), _PROBE_BOUNDARY
    )
    blocked, _ = score_gate_problems(
        _specimen(
            "survey-2026-09-19 — workspace_gate=blocked-by-unowned blocked_paths=a.md " + _STAMP
        ),
        _PROBE_BOUNDARY,
    )
    assert clean == [] and blocked == [], (clean, blocked)
    # and the FAILING gate is neither: `rc=1` is not in the lawful set.
    failing, _ = score_gate_problems(
        _specimen(f"survey-2026-09-19 — workspace_gate=rc=1 {_STAMP}"), _PROBE_BOUNDARY
    )
    assert failing and VERDICT_KEY in failing[0], failing
