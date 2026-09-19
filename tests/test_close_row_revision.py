#!/usr/bin/env python3
"""Gate: a close row's receipt names the revision it measured.

Origin (issue #63). A close row is the ledger's completion claim: it says a work unit is
finished. Its detail carries receipts — gate counts, row counts, verify exit codes — and
those receipts were TRUE of the working tree the author measured. Nothing required them
to name WHICH revision that was, and no gate read the receipt at all. So the row is not
false; it is UNCHECKABLE: a reader cannot tell whether "27 gates, 0 FAIL" describes the
tree that shipped or a tree that has since moved four commits.

The sharpening. SKILL.md §8 already says verdict verbs need a receipt. This adds the
missing half — the receipt must name the revision it measured. Without it a receipt
degrades into testimony: an assertion about a tree nobody can identify.

The rule, in two parts — the shape `tests/test_score_gate_recorded.py` already uses for
`score` rows, REUSED rather than reinvented:

1. **Every `close` row written on or after the invariant lands carries `head=<sha>`**,
   the revision its receipts describe. The sha makes the row checkable against the
   repository instead of a claim about a tree that has since moved.
2. **Rows written before the invariant are excused, and said so.** Reported as
   `excused:` with their count, never folded into a bare "clean" — so "clean" and
   "excused" are never the same output. Nothing is backfilled: a revision written today
   for a close that predates the rule would be a falsified record, not a repair
   (#52 clause 2(a), #53 clause 7).

The predicate reads the FIELD, never the prose
----------------------------------------------
Measured when this landed: a loose hex-shaped pattern matches 30 of 54 close rows, but
only 4 carry `head=`. A predicate that accepted any hex token would pass 30 rows whose
revision is not actually declared — and a hex-shaped token is not even necessarily a
revision. Two of the 30 (n=349, n=353) match only inside the append tool's own telemetry
trailer (`tokens_out=`), which is machine-written and names no revision at all; seven
more cite a 10-digit GitHub comment id that `git cat-file -t` does not resolve as an
object (n=10, 303, 341, 368, 370, 372, 374). So the value is validated as a FIELD: a
`head=` token whose value is hex and at least 7 chars. This is #53 clause 4's discipline,
whose three live instances there were prose misread as fields.

The boundary is DECLARED, and this file SHIPS (issue #78, ruled n=515 clause 4)
-------------------------------------------------------------------------------
This file used to carry a section titled *"Why this is NOT paired into TEMPLATE"*. Its
argument was that the predicate reads `evidence/ledger.jsonl`, which is FACTORY DATA — a
bootstrapped factory has its own ledger, its own history and its own invariant date, so
shipping this file would assert another factory's boundary against it. The argument was
RIGHT about the hardcoded shape and WRONG only in concluding the gate cannot ship at all:
it is SUPERSEDED by the declared-parameter form, not discarded. The logic is universal;
the boundary is a factory parameter, and a parameter can be declared.

So the boundary moves out of this file and into `docs/ledger-invariants.json`, the
factory's own declaration, read through `tests/ledger_boundary.py` (shared with
`test_score_gate_recorded.py`, so the class has one implementation). A tree that has not
declared a boundary SKIPS with a stated reason — never a silent pass, and never a foreign
boundary. A tree with no ledger at all skips for the same reason: `TEMPLATE/evidence/`
does not exist, because the ledger is BOOTSTRAP-created.

The population guard is PROPORTIONAL (#78 clause c). The `>= 50` floor is dropped: it
fails a factory whose history is younger than 50 closes, and a floor cannot be both
universal and true. An empty post-boundary population skips with its reason instead, so
this gate either verifies a non-empty population or says why it examined nothing.

Run:  python3 -m pytest tests/test_close_row_revision.py -q
Exit: 0 clean, fully excused, or skipped-with-reason; non-zero on any post-boundary close
      without a revision, or on a declaration this tree cannot honour.
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
    parse_ts,
    population_skip_reason,
    post_boundary_rows,
    synthetic_tree,
)

REPO = Path(__file__).resolve().parent.parent

# The ONE field predicate, shared with `tests/test_ledger_schema.py` and
# `tools/ledger.py`. Imported by module name so a staged throwaway `tools/` resolves it
# the same way — see tools/field_predicate.py.
sys.path.insert(0, str(REPO / "tools"))
from field_predicate import keyed_value  # noqa: E402

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name, so the declaration says
# which invariant each date belongs to.
INVARIANT_KEY = "close_row_revision"

REVISION_FIELD = "head"
REVISION_KEY = f"{REVISION_FIELD}="
_HEX = set("0123456789abcdef")
_MIN_SHA = 7

def _declared_revision(detail: str) -> str | None:
    """The `head=<sha>` value, or None when no readable field is present.

    A FIELD, not a prose mention: the token must DECLARE `head` — the shared
    `keyed_value` predicate in `tools/field_predicate.py`, which requires the key, then
    `=`, then a NON-EMPTY value — and that value must be hex of at least `_MIN_SHA`
    chars. Both halves are probed, because a predicate that only checked "is a sha
    present somewhere" would pass a row whose revision is merely cited in a sentence —
    the pattern-inflated shape #63 measured at 30 of 54. The shape half is the same
    predicate the telemetry gates use; only the type half is this gate's own, which is
    what makes it one class with one remedy rather than three readers (#88, n=405
    clause 5).

    The scan CONTINUES past an unreadable `head=` token rather than stopping at it, the
    shape `tests/test_score_gate_recorded.py::_has_head_sha` uses. Stopping at the first
    one is a false-RED generator: a row that DESCRIBES the field in prose before naming
    the revision ("the `head=` field is carried by only 4 rows ... head=02e9597...") does
    declare a revision, and an early return rejects it. Not hypothetical — it fired on
    this gate's own author's close row on the day it landed, and it is #53 clause 4's
    shape one layer up, prose mistaken for a field. The distinction that matters is
    readable-vs-not, so a row whose only `head=` token is unreadable is still reported,
    which `test_probe_rejects_an_unreadable_revision` pins.
    """
    for token in str(detail).replace(",", " ").replace(";", " ").split():
        value = keyed_value(token, REVISION_FIELD)
        if value is None:
            continue
        sha = value.strip(").`")
        if len(sha) >= _MIN_SHA and all(c in _HEX for c in sha):
            return sha
    return None

def close_row_revision_problems(
    rows: list[dict], boundary_text: str
) -> tuple[list[str], list[str]]:
    """Return (problems, excused) for the `close` rows of a ledger.

    `problems` names every post-boundary close row that does not declare a readable
    revision; `excused` names every pre-boundary row, so the two are never conflated.
    `boundary_text` is the DECLARED boundary verbatim, so an excused line quotes the date
    the factory declared rather than one this file carries.
    """
    boundary = parse_ts(boundary_text)
    problems: list[str] = []
    excused: list[str] = []

    for row in rows:
        if row.get("event") != "close":
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
        if _declared_revision(str(row.get("detail") or "")) is None:
            problems.append(
                f"n={n} ({ts}) does not declare the revision its receipts describe "
                f"(expected a readable {REVISION_KEY}<sha> field)"
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

    problems, excused = close_row_revision_problems(rows, boundary_text)
    if problems:
        return "fail", "", problems, excused, 0

    population = post_boundary_rows(rows, boundary, "close")
    reason = population_skip_reason(population, boundary_text, "close")
    if reason:
        return "skip", reason, [], excused, 0
    return "pass", "", [], excused, len(population)

def _live_verdict() -> tuple[str, list[str], list[str], int]:
    """The verdict for the tree this file is running in, skipping with its reason."""
    status, reason, problems, excused, checked = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "close rows written after the declared boundary must name the revision "
            "their receipts describe:\n  " + "\n  ".join(problems)
        )
    return status, problems, excused, checked

# --- live gate -------------------------------------------------------------------

def test_live_close_rows_declare_the_revision_they_measured() -> None:
    _, _, excused, checked = _live_verdict()
    print(
        f"close-row revision gate: {checked} post-boundary close row(s) verified, "
        f"{len(excused)} excused (pre-boundary)"
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
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. audit -> HEALTHY (PASS).")],
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert "ledger-invariants.json" in reason and "DECLARED factory parameter" in reason, reason

def test_probe_a_declaration_missing_this_key_skips(tmp_path: Path) -> None:
    """One declaration file serves every ledger invariant; a key a factory has not
    declared skips for that gate alone."""
    tree = synthetic_tree(
        tmp_path / "other-key",
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. audit -> HEALTHY (PASS).")],
        invariants={"score_gate_recorded": "2026-09-18T10:04:05Z"},
    )
    status, reason, _, _, _ = evaluate(tree)
    assert status == "skip", (status, reason)
    assert INVARIANT_KEY in reason, reason

def test_probe_a_synthetic_tree_fails_a_close_row_with_no_revision(tmp_path: Path) -> None:
    """THE PROPERTY SURVIVES THE DECLARED FORM. Making the boundary a parameter must not
    cost the gate its teeth: a post-boundary close row with no revision still FAILS."""
    tree = synthetic_tree(
        tmp_path / "offending",
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. audit -> HEALTHY (PASS).")],
        invariants={INVARIANT_KEY: "2026-09-19T05:00:00Z"},
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, problems)
    assert problems and "does not declare the revision" in problems[0], problems

def test_probe_a_compliant_synthetic_tree_passes(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "compliant",
        rows=[
            _close(
                1,
                "2026-09-19T06:00:00Z",
                "Closed. Receipts taken at head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e.",
            )
        ],
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
    row = _close(1, "2026-09-19T06:00:00Z", "Closed. audit -> HEALTHY (PASS).")
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
    no close at all — skips with its reason instead of passing vacuously."""
    tree = synthetic_tree(
        tmp_path / "young",
        rows=[_close(1, "2026-09-19T04:00:00Z", "Closed. no revision field.")],
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
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e")],
        declaration="{ this is not json",
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail" and problems, (status, problems)
    assert "not valid JSON" in problems[0], problems

def test_probe_an_unreadable_declared_boundary_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "bad-date",
        rows=[_close(1, "2026-09-19T06:00:00Z", "Closed. head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e")],
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

def test_probe_the_population_guard_is_proportional() -> None:
    """(c): the guard scales with the tree. An empty population is a REASON; a non-empty
    one is None, whatever its size — there is no floor left to fail a young factory."""
    assert population_skip_reason([], "2026-09-19T05:00:00Z", "close") is not None
    assert population_skip_reason([{"n": 1}], "2026-09-19T05:00:00Z", "close") is None

# --- probes: the predicate must reject bad input, not only accept good ------------

_PROBE_BOUNDARY = "2026-09-19T05:00:00Z"

_OK = {
    "n": 900,
    "ts": "2026-09-19T06:00:00Z",
    "event": "close",
    "detail": "Closed. Receipts taken at head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e.",
}

def test_probe_accepts_a_compliant_close_row() -> None:
    problems, excused = close_row_revision_problems([_OK], _PROBE_BOUNDARY)
    assert problems == [] and excused == [], (problems, excused)

def test_probe_rejects_a_close_row_with_no_revision() -> None:
    row = {**_OK, "detail": "Closed. audit -> HEALTHY (PASS), 28 gates, 0 FAIL."}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems and "does not declare the revision" in problems[0], problems

def test_probe_rejects_an_unreadable_revision() -> None:
    """A `head=` field whose value is not a sha is present-but-unreadable, not absent."""
    for bad in ("head=not-a-sha", "head=abc", "head=zzzzzzzz"):
        row = {**_OK, "detail": f"Closed. Receipts taken at {bad}."}
        problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
        assert problems, f"{bad!r} must not read as a declared revision"

def test_probe_rejects_a_prose_mention_without_the_field() -> None:
    """The pattern-inflation trap: a sha cited in a sentence is not a declared revision.

    Measured at landing: 30 of 54 close rows carry a sha-shaped token, only 4 carry the
    field. Accepting the prose form would pass rows whose revision is never declared.
    """
    row = {**_OK, "detail": "Closed. The fix landed at 9c2ed02 as clause 8 of the stream."}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems, "a sha-shaped prose token must not satisfy the field"

def test_probe_accepts_a_row_that_describes_the_field_before_naming_it() -> None:
    """The live shape that made this gate reject its own author's close row.

    n=399 read "the head= FIELD is carried by only 4 (n=283, ...)" and only later
    "head=02e9597...". An early return on the first `head=` token rejected a row that does
    declare its revision — a false RED, and #53 clause 4's shape (prose read as a field).
    """
    row = {**_OK, "detail": (
        "Closed. The head= FIELD is carried by only 4 rows; the scan must continue past "
        "this prose to the field that follows. Receipts taken at "
        "head=9552947a985b0f1a6c8919c362a0a56ec7d0d42e."
    )}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems == [], f"a row naming its revision after describing the field must pass: {problems}"

def test_probe_rejects_a_pure_digit_comment_id() -> None:
    """n=303 cites 5737030289 — a GitHub comment id, which `git cat-file -t` does not
    resolve as an object. Ten such rows are in the live population."""
    row = {**_OK, "detail": "Closed. Receipt comment 5739522839 posted to the board."}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems, "a comment id must not satisfy the revision field"

def test_probe_rejects_a_telemetry_trailer_match() -> None:
    """The append tool writes `tokens_out=<n>` into every close row — a 7+ digit run that
    a loose hex-shaped pattern matches. It names no revision: n=349 and n=353 match ONLY
    there, which is why the loose pattern would pass rows that declare nothing."""
    row = {**_OK, "detail": "Closed. gate=all-pass outcome=accepted cost_usd=4.7343 "
                            "tokens_out=16830682 turns=5 duration=308s"}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems, "the telemetry trailer must not satisfy the revision field"

def test_probe_the_field_predicate_is_shared_not_reimplemented() -> None:
    """The scan's SHAPE half is the shared predicate, not a private copy (#88).

    Ledger `n=405` clause 5 ruled the class as ONE field predicate at three call sites,
    because three readings is how the class recurs: this file's own first version read
    `token.startswith("head=")` while the schema gate read every `k=v` token and the
    append guard read a substring. So the binding the scan calls must BE the shared
    function — a lookalike defined here would satisfy every behavioural probe above and
    still leave the class unfixed.
    """
    import field_predicate

    assert keyed_value is field_predicate.keyed_value, (
        "the scan must call the shared predicate, not a local re-implementation"
    )
    # And the shape the shared predicate changes at this site: a bare `head=` is a
    # MENTION. It names the field and states no value, so it declares no revision.
    row = {**_OK, "detail": "Closed. The head= field is read from the trailer; it is absent here."}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems, "a bare head= mention must not satisfy the revision field"

def test_probe_rejects_an_unparseable_timestamp() -> None:
    row = {**_OK, "ts": "not-a-timestamp"}
    problems, _ = close_row_revision_problems([row], _PROBE_BOUNDARY)
    assert problems and "unparseable ts" in problems[0], problems

def test_probe_excuses_pre_boundary_rows_without_calling_them_clean() -> None:
    legacy = {
        "n": 368,
        "ts": "2026-09-19T04:01:30Z",
        "event": "close",
        "detail": "Closed. python3 tools/audit.py -> HEALTHY (PASS), 27 gates, 0 FAIL.",
    }
    problems, excused = close_row_revision_problems([legacy], _PROBE_BOUNDARY)
    assert problems == [], problems
    assert len(excused) == 1 and "predates the declared boundary" in excused[0], excused

def test_probe_ignores_non_close_events() -> None:
    other = {"n": 901, "ts": "2026-09-19T06:00:00Z", "event": "claim", "detail": "x"}
    problems, excused = close_row_revision_problems([other], _PROBE_BOUNDARY)
    assert problems == [] and excused == []

def main() -> int:
    """Script form: the same verdict, with the skip reason on STDOUT rather than in a
    pytest short summary — so a reader of the run sees WHY nothing was judged."""
    status, reason, problems, _, checked = evaluate(REPO)
    if status == "skip":
        print(f"close-row revision gate: SKIP — {reason}")
        return 0
    if status == "fail":
        print("close-row revision gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"close-row revision gate: clean — {checked} post-boundary close row(s) verified")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
