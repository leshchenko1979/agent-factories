#!/usr/bin/env python3
"""Gate: every close row declares the row count `verify` measured, and it covers the row.

Origin: issue #96, ruled at ledger `n=745`, whose first half is HQ's procedure law
(`docs/processes.md`, section Settlement & Release). The order: the settlement step runs
`tools/ledger.py verify` AFTER the close row is appended, so the receipt covers the row it
certifies. This gate is the half that makes the order MECHANICALLY CHECKABLE.

WHY A CITATION ALONE CANNOT CARRY THE CLAIM. `verify` reads a subject's rows as a
SEQUENCE, so a run made while the close row does not yet exist has not seen the row it is
cited for — the receipt is structurally incapable of covering the artifact it certifies.
The finding asked only that a cited receipt STATE the row count it measured, and that is
checkable but WEAK: a count that is merely present can still be smaller than the row it
certifies. So the predicate is the statement itself, verbatim from `n=745`:

    a close row declares the row count that verify measured, and that count must be AT
    LEAST the row's own number.

A declared count of `n-1` is not a MALFORMED row. It is a row that has TOLD you its verify
predated the append, which is the whole point: the gate's finding names an ORDER defect,
and it accuses nobody of dishonesty. A citation taken early is not a false citation — the
rows that carry one stand as written.

WHY THE POPULATION IS EVERY CLOSE ROW, NOT ONLY THE ONES THAT MENTION VERIFY
-----------------------------------------------------------------------------------
This is the shape the sibling gate (`tests/test_close_telemetry_provenance.py`) settled for
its own field, and the deciding fact is the same one. The narrower predicate — *a close row
that cites a verify receipt must declare the count* — is strictly WEAKER, and its weakness
is not hypothetical: `verify` is part of settlement for every close (that is what the order
in `docs/processes.md` says), so the case worth catching is the close where settlement did
not run it at all — a row that cites nothing to hang a count on, which a citation-filtered
population cannot see by construction. The condition states what settlement DOES, not a
filter over prose; satisfiable by construction beats satisfiable by convention.

The prose filter is also the class this factory has already measured and ruled against: a
loose `verify` pattern read 30 of 54 close rows of which 4 were real (#63), and a count
taken by a pattern is a claim about the pattern rather than about the rows. So the
population is every post-boundary `close` row, and the predicate is the WRITER'S OWN
GUARANTEE — one declaration, on every close.

THE FIELD IS `rows`, AND ITS READER IS SHARED. `tools/field_predicate.py` owns the read
(section 11's one-field-one-predicate law binds a NEW field exactly as it binds an old
one), imported here rather than parsed locally. The token is NOT this gate's to pick: the
ledger already carries `rows=` — `n=761`, the close of #89, declares `rows=761`, and
`n=762` is the repair row that put it there, stating in terms that the row "now DECLARES
the row count verify measured (SKILL.md section 11, #96 ruling n=745)". A second spelling
would split the very field the invariant is about. The read is POSITIONAL — the canonical
trailer — so a `rows=` token quoted mid-sentence is PROSE and never a declaration.

THE POPULATION IS THE WHOLE CLOSE HISTORY, SO ZERO HISTORY IS LOUD. `n=745` rules this the
one place this family refuses its proportional skip: a ledger carrying rows and NOT ONE
`close` row is a read that judged nothing, and a clean verdict over a population that was
never judged is what P29 forbids. (Contrast #112, whose population a factory may
legitimately never produce and which is therefore proven by its probe instead.) The other
zero — a ledger whose closes all PREDATE the declared boundary — is the legitimate state of
a factory on the day it adopts this gate, so it PASSES with the governed count printed as
0 rather than failing: forward-only means the boundary, not the count, is what separates
adopted rows from excused ones, and a gate that reds every young factory is a tax rather
than a gate (#68).

FORWARD-ONLY, AND NOTHING IS BACKFILLED. The boundary is a DECLARED FACTORY PARAMETER
(`docs/ledger-invariants.json`, keyed by this gate's own name) and never a module constant
(#78, ruled `n=515` clause 4): the LOGIC is universal and the DATE is this factory's. Rows
before the boundary are EXCUSED AND PRINTED, never repaired — a count written into a row
today for a receipt taken days ago would be a falsified record, not a repair. The gate
SHIPS (#130's precedent), so a bootstrapped factory reads its own declaration; a tree with
no ledger, no declaration or no key SKIPS with the reason printed, which is how the same
file runs in `TEMPLATE/`, where `evidence/` does not exist.

SEVERITY IS LATENT, STATED SO THE GATE IS NOT OVERSOLD: `verify` exits 0 on the live
ledger, and `n=596`'s write-path refusal already blocks the `n=588` shape. This gate closes
the RECORDING hole, not a live outage. The close rows that predate the boundary — the five
known instances `n=746` (#121), `n=749` (#119), `n=752` (#120), `n=763` (#66), `n=783`
(#124), each citing verify in prose with no declared count — print as `excused:` on every
run and are never backfilled.

WHAT THIS GATE DOES NOT CLAIM, STATED RATHER THAN IMPLIED. It asserts that the row STATES a
count and that the statement covers the row; it cannot falsify the count itself, because a
row that declared a number it never measured would read exactly like one that measured it.
That bound is the same one the provenance gate carries: the token records what the writer
says it did, and no structural read of a row can settle whether the writer was truthful.

Run:  python3 -m pytest tests/test_close_verify_count_declared.py -q
Exit: 0 clean or skipped-with-reason; non-zero on a post-boundary close row whose declared
      count is missing, malformed, doubled, or smaller than the row's own number, and on a
      ledger that carries no close row at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    LEDGER_REL,
    GateError,
    SkipGate,
    boundary_and_rows,
    parse_ts,
    post_boundary_rows,
    synthetic_tree,
)

REPO = Path(__file__).resolve().parent.parent

# `ledger_boundary` has already put `tools/` on the path — the bare-neighbour import every
# gate and tool here uses, because a bootstrapped factory carries `tools/` and `tests/` as
# siblings with no `__init__.py` in either.
from field_predicate import declared_verify_rows  # noqa: E402

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name, so the declaration says
# which invariant each date belongs to.
INVARIANT_KEY = "close_verify_count_declared"

# The exemption surface, and why this gate must carry one. The invariant's repair space is
# EMPTY once a row exists: a ledger row is append-only, `tools/ledger.py repair` refuses to
# re-declare a key the row's canonical run already carries (#104, ruled n=620 PART 4) and
# inserts its text BEFORE that run, and a row's `n` is identity and immutable — so a close
# row that shipped a count short of its own number can never be corrected. A gate whose only
# exits are barred is a stop with no andon cord (SKILL.md section 11), so the exit is a table
# of FACTORY DATA in its own file: absent or empty means none, every matching row is printed
# as an `excused:` line on EVERY run, and an entry that matches nothing is a gate ERROR
# rather than a silent pass. The skeleton ships as
# `TEMPLATE/docs/close-verify-count-exemptions.example.json`.
EXEMPTIONS_PATH = "docs/close-verify-count-exemptions.json"

def load_exemptions(repo: Path) -> tuple[list[dict], list[str]]:
    """The factory's declared exemptions, or `([], [])` when it has declared none.

    A list that cannot be READ is a problem, never a silent pass: an exemption list that
    quietly fails to load is indistinguishable from no exemptions, the vacuous-pass shape
    this repo forbids.
    """
    path = repo / EXEMPTIONS_PATH
    if not path.is_file():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"{EXEMPTIONS_PATH}: not valid JSON — {exc}"]
    if not isinstance(data, dict) or not isinstance(data.get("exemptions"), list):
        return [], [f"{EXEMPTIONS_PATH}: expected a JSON object with an 'exemptions' list"]
    exemptions: list[dict] = []
    problems: list[str] = []
    for index, raw in enumerate(data["exemptions"], 1):
        if not isinstance(raw, dict):
            problems.append(f"{EXEMPTIONS_PATH}: exemption {index} is not an object")
            continue
        missing = [field for field in ("n", "reason") if not raw.get(field)]
        if missing:
            problems.append(
                f"{EXEMPTIONS_PATH}: exemption {index} is missing {', '.join(missing)}"
            )
            continue
        if not isinstance(raw["n"], int):
            problems.append(f"{EXEMPTIONS_PATH}: exemption {index} 'n' is not an integer")
            continue
        exemptions.append(raw)
    return exemptions, problems

def close_verify_count_declared_problems(
    rows: list[dict], boundary_text: str, exemptions: list[dict] | None = None
) -> tuple[list[str], list[str], int, int]:
    """`(problems, excused, governed, covered)` over `rows` — the invariant, pure.

    `rows` is EVERY row of a ledger, not a filtered population: the event filter and the
    boundary are part of the rule, so a probe cannot satisfy it by pre-filtering. `governed`
    counts the post-boundary close rows the predicate APPLIED to and `covered` those whose
    declared count reaches their own number; the live run prints both, so a verdict over a
    population is never mistaken for one over nothing (P29).

    A row before the boundary is EXCUSED by name and never called clean — the distinction
    `tools/ledger.py` draws for its own legacy closes, so "clean" and "excused" are never the
    same output.

    `exemptions` are the factory's declared entries for rows whose repair space is empty.
    An exempted row is EXCUSED BY NAME and printed on every run, and it leaves `governed`
    because the predicate did not apply to it — a debt that is visible, never forgiveness
    and never a silent subtraction.
    """
    problems: list[str] = []
    excused: list[str] = []
    governed = 0
    covered = 0
    boundary = parse_ts(boundary_text)

    for row in rows:
        if row.get("event") != "close":
            continue
        n = row.get("n")
        ts = row.get("ts", "")
        try:
            when = parse_ts(ts)
        except (ValueError, TypeError):
            problems.append(f"n={n}: unparseable ts {ts!r} — an undatable row is judged")
            continue
        if when < boundary:
            excused.append(
                f"n={n} ({ts}) predates the declared boundary ({boundary_text})"
            )
            continue
        exempt = next((entry for entry in (exemptions or []) if entry["n"] == n), None)
        if exempt is not None:
            excused.append(f"n={n} ({ts}) EXEMPTED — {exempt['reason']}")
            continue
        governed += 1
        detail = str(row.get("detail") or "")
        if not isinstance(n, int):
            problems.append(
                f"n={n!r} ({ts}) carries no integer row number, so no declared count can "
                f"be shown to cover it"
            )
            continue
        declared = declared_verify_rows(detail)
        if not declared:
            problems.append(
                f"n={n} ({ts}) declares no rows= count in its canonical trailer — the "
                f"settlement order makes verify part of every close, and a receipt whose "
                f"row count is unstated cannot be told from one taken before this row "
                f"existed (#96, ruling n=745)"
            )
            continue
        if len(declared) > 1:
            problems.append(
                f"n={n} ({ts}) declares {len(declared)} rows= values "
                f"({', '.join(declared)}) — two tokens for one field have no canonical "
                f"reading (SKILL.md section 8)"
            )
            continue
        value = declared[0]
        if not value.isdigit():
            problems.append(
                f"n={n} ({ts}) declares rows={value}, which is not a row count verify "
                f"could have reported"
            )
            continue
        if int(value) < n:
            problems.append(
                f"n={n} ({ts}) declares rows={value} and is itself row {n}: the receipt "
                f"it cites covered {value} row(s), so that verify ran BEFORE this row was "
                f"appended — the ORDER defect the #96 order exists to prevent"
            )
            continue
        covered += 1

    return problems, excused, governed, covered

def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], dict]:
    """`(status, reason, problems, excused, counts)` over `repo` — the probe-able core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip, and
    both outrank a verdict over nothing: the zero-close-history check runs only on an
    otherwise-clean ledger, so a defect is never hidden behind "there was nothing to judge".

    `counts` is `{"history", "governed", "covered"}` — close rows in the ledger, close rows
    at or after the boundary, and those declaring a count that covers their own number.
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], {}
    except GateError as exc:
        return "fail", "", list(exc.problems), [], {}

    exemptions, exemption_problems = load_exemptions(repo)
    problems, excused, governed, covered = close_verify_count_declared_problems(
        rows, boundary_text, exemptions
    )
    problems = list(exemption_problems) + problems
    # A STALE exemption is a FAILURE, never silence: it inflates the visible debt while
    # excusing nothing, and the record and its exemption must not drift apart. An entry is
    # USED only where it excused a governed row — an entry for a row that does not exist, is
    # not a close, predates the boundary, or already covers its own number excuses nothing.
    for entry in exemptions:
        row = next((r for r in rows if r.get("n") == entry["n"]), None)
        if row is None or row.get("event") != "close":
            problems.append(
                f"{EXEMPTIONS_PATH}: exemption n={entry['n']} matches no close row — a "
                f"stale exemption excuses nothing; remove it"
            )
            continue
        try:
            when = parse_ts(row.get("ts", ""))
        except (ValueError, TypeError):
            continue
        if when < boundary:
            problems.append(
                f"{EXEMPTIONS_PATH}: exemption n={entry['n']} predates the declared "
                f"boundary ({boundary_text}) — a pre-boundary row is already excused by "
                f"the boundary, so this entry excuses nothing; remove it"
            )
            continue
        declared = declared_verify_rows(str(row.get("detail") or ""))
        if len(declared) == 1 and declared[0].isdigit() and int(declared[0]) >= entry["n"]:
            problems.append(
                f"{EXEMPTIONS_PATH}: exemption n={entry['n']} excuses nothing — the row "
                f"declares rows={declared[0]} and covers its own number; remove it"
            )
    counts = {
        "history": sum(1 for row in rows if row.get("event") == "close"),
        "governed": governed,
        "covered": covered,
    }
    if problems:
        return "fail", "", problems, excused, counts

    # THE LOUD ZERO (#96, ruling n=745). This gate's population is the whole close history,
    # so an empty one is NOT a young factory: the ledger carries rows and not one of them is
    # a close, which means the reader judged nothing. The family's proportional skip would
    # report that in the same shape as a clean run.
    if counts["history"] == 0:
        return "fail", "", [
            f"{LEDGER_REL} carries {len(rows)} row(s) and not one of them is a close — "
            f"this gate's population is the whole close history, so a zero count is a "
            f"read that judged nothing, never a clean run (n=745, contrast #112)"
        ], excused, counts
    return "pass", "", [], excused, counts

# --- live gate -------------------------------------------------------------------

def test_live_close_rows_declare_the_verify_row_count() -> None:
    status, reason, problems, excused, counts = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "every close row at or after the declared boundary must declare a rows= "
            "count covering its own number:\n  " + "\n  ".join(problems)
        )
    print(
        f"close verify-count gate: {counts['history']} close row(s) in history, "
        f"{counts['governed']} governed by the declared boundary, {counts['covered']} "
        f"declaring a count covering the row; {len(excused)} excused (pre-boundary)"
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

# A row in the shape the shipping lane writes: the citation in prose, the count in the
# canonical trailer beside the other close fields. `n=761` is the live precedent.
_CITING_DETAIL = (
    "CLOSE -- #1, the gate lands. VERIFY RECEIPT, TAKEN AFTER THIS ROW EXISTS, per the "
    "#96 settlement order: tools/ledger.py verify rc=0, reporting ledger clean over 900 "
    "row(s). rows=900 board=closed head=deadbeef985b outcome=accepted "
    "gate=all-pass cost_usd=1.0000 telemetry=measured"
)
_OK = _close(900, "2026-09-21T06:00:00Z", _CITING_DETAIL)
_PROBE_BOUNDARY = "2026-09-21T05:00:00Z"

def test_probe_a_tree_with_no_ledger_skips_with_a_stated_reason(tmp_path: Path) -> None:
    """`TEMPLATE/evidence/` does not exist — the ledger is BOOTSTRAP-created. A gate that
    RAISED here was RED on the very tree it ships to (#78, #76's class)."""
    status, reason, problems, _, _ = evaluate(synthetic_tree(tmp_path / "bare"))
    assert status == "skip", (status, reason, problems)
    assert "evidence/ledger.jsonl" in reason and "BOOTSTRAP" in reason, reason

def test_probe_a_tree_with_no_declared_boundary_skips_with_a_stated_reason(
    tmp_path: Path,
) -> None:
    """A factory that has not adopted the invariant has no boundary to judge against —
    and that is a STATED skip, never a silent pass and never a foreign boundary."""
    tree = synthetic_tree(tmp_path / "undeclared", rows=[_OK])
    status, reason, problems, _, _ = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert "ledger-invariants.json" in reason, reason
    assert "DECLARED factory parameter" in reason, reason

def test_probe_an_empty_ledger_skips(tmp_path: Path) -> None:
    """`rows=[]` writes an EMPTY ledger: the bootstrap state of a factory that has created
    the file and appended nothing. Nothing to judge, stated as such."""
    tree = synthetic_tree(
        tmp_path / "empty", rows=[], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, reason, problems, _, _ = evaluate(tree)
    assert status == "skip", (status, reason, problems)
    assert "carries no rows" in reason, reason

def test_probe_a_ledger_with_no_close_row_fails_loudly(tmp_path: Path) -> None:
    """THE LOUD ZERO, and the difference from #112. This gate's population is the whole
    close history, so a ledger carrying rows and no close is a READ that judged nothing —
    a skip here would report that in the same shape as a clean run."""
    intake = {
        "n": 1,
        "ts": "2026-09-21T06:00:00Z",
        "event": "intake",
        "actor": "triage",
        "subject": "#1",
        "detail": "filed.",
    }
    tree = synthetic_tree(
        tmp_path / "noclose", rows=[intake], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, reason, problems, _, counts = evaluate(tree)
    assert status == "fail", (status, reason, problems)
    assert counts["history"] == 0, counts
    assert "not one of them is a close" in problems[0], problems

def test_probe_a_compliant_row_passes_and_the_population_is_counted(
    tmp_path: Path,
) -> None:
    """The positive direction, with the population PRINTED: one governed row declaring a
    count that covers it. A verdict over a population that was never named is what this
    count exists to prevent (P29)."""
    tree = synthetic_tree(
        tmp_path / "ok", rows=[_OK], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, reason, problems, excused, counts = evaluate(tree)
    assert status == "pass", (status, reason, problems)
    assert counts == {"history": 1, "governed": 1, "covered": 1}, counts
    assert excused == [], excused

def test_probe_a_count_below_the_rows_own_number_bites(tmp_path: Path) -> None:
    """THE BITE the ruling asks for, and it is an ORDER finding rather than a schema
    finding: `n=900` declaring `rows=899` has told the reader its verify covered 899 rows
    while this row is number 900, i.e. the receipt predated the append."""
    short = _close(
        900, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("rows=900", "rows=899")
    )
    tree = synthetic_tree(
        tmp_path / "short", rows=[short], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, reason, problems, _, counts = evaluate(tree)
    assert status == "fail", (status, reason, problems)
    assert "rows=899" in problems[0] and "900" in problems[0], problems[0]
    assert "BEFORE this row was appended" in problems[0], problems[0]
    assert counts["governed"] == 1 and counts["covered"] == 0, counts

def test_probe_the_boundary_comes_from_the_declaration(tmp_path: Path) -> None:
    """The same offending row FAILS under one declaration and is EXCUSED under a later
    one, which is what makes the date a factory parameter rather than a module constant."""
    short = _close(
        900, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("rows=900", "rows=899")
    )
    governed = synthetic_tree(
        tmp_path / "governed", rows=[short], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, _, problems, _, _ = evaluate(governed)
    assert status == "fail", problems

    later = synthetic_tree(
        tmp_path / "later", rows=[short], invariants={INVARIANT_KEY: "2026-09-21T07:00:00Z"}
    )
    status, _, problems, excused, counts = evaluate(later)
    assert status == "pass", (status, problems)
    assert excused and "2026-09-21T07:00:00Z" in excused[0], excused
    assert counts["governed"] == 0 and counts["history"] == 1, counts

def test_probe_a_malformed_declaration_fails(tmp_path: Path) -> None:
    """A factory that declared a boundary and cannot be read is a DEFECT, never a skip
    hiding behind the same output as no declaration at all."""
    tree = synthetic_tree(tmp_path / "malformed", rows=[_OK], declaration="{not json")
    status, reason, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, reason, problems)
    assert "not valid JSON" in problems[0], problems

def test_probe_an_unreadable_boundary_date_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "baddate", rows=[_OK], invariants={INVARIANT_KEY: "not-a-date"}
    )
    status, reason, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, reason, problems)
    assert "not a readable ISO-8601 timestamp" in problems[0], problems

def test_probe_a_corrupt_ledger_line_fails(tmp_path: Path) -> None:
    tree = synthetic_tree(
        tmp_path / "corrupt", invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    (tree / "evidence" / "ledger.jsonl").write_text("{not a row\n", encoding="utf-8")
    status, reason, problems, _, _ = evaluate(tree)
    assert status == "fail", (status, reason, problems)
    assert "is not a JSON row" in problems[0], problems

def test_probe_accepts_a_count_equal_to_the_rows_own_number() -> None:
    """The predicate is `>=`, not `>`. A receipt taken after the append reports at least
    the row it certifies, and equality is the common case — `n=761` is the live precedent:
    the close row is the last row verify read."""
    exact = _close(901, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("900", "901"))
    problems, excused, governed, covered = close_verify_count_declared_problems(
        [exact], _PROBE_BOUNDARY
    )
    assert problems == [] and excused == [], (problems, excused)
    assert (governed, covered) == (1, 1), (governed, covered)

def test_probe_accepts_a_count_above_the_rows_own_number() -> None:
    """Rows appended after the receipt do not invalidate it: a count above the row's own
    number is what a receipt taken later in the same settlement pass looks like."""
    later = _close(902, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("900", "910"))
    problems, _, governed, covered = close_verify_count_declared_problems(
        [later], _PROBE_BOUNDARY
    )
    assert problems == [], problems
    assert (governed, covered) == (1, 1), (governed, covered)

def test_probe_rejects_a_row_with_no_declared_count() -> None:
    """What the five known instances look like: the citation is there, the count is not —
    `n=746`/`n=749`/`n=752`/`n=763`/`n=783` each cite verify in prose and none declares
    the number. Prose does not satisfy a field, and the population is every close row, so
    a row that cites NOTHING owes the count too."""
    bare = _close(
        903,
        "2026-09-21T06:00:00Z",
        "CLOSE -- #1, the tree moved. tools/ledger.py verify rc=0, reporting ledger clean "
        "over 903 row(s). board=closed head=deadbeef985b telemetry=measured",
    )
    silent = _close(
        904,
        "2026-09-21T06:00:00Z",
        "CLOSE -- #1, no receipt is mentioned anywhere in this row. board=closed "
        "head=deadbeef985b telemetry=measured",
    )
    problems, _, governed, covered = close_verify_count_declared_problems(
        [bare, silent], _PROBE_BOUNDARY
    )
    assert len(problems) == 2, problems
    assert all("declares no rows= count" in p for p in problems), problems
    assert (governed, covered) == (2, 0), (governed, covered)

def test_probe_rejects_two_tokens_for_one_field() -> None:
    """SKILL.md section 8: two tokens for one field have no canonical reading, so the gate
    reports the multiplicity rather than silently reading the first."""
    twice = _close(
        905,
        "2026-09-21T06:00:00Z",
        _CITING_DETAIL.replace("rows=900", "rows=904 rows=905"),
    )
    problems, _, _, _ = close_verify_count_declared_problems([twice], _PROBE_BOUNDARY)
    assert problems and "2 rows= values" in problems[0], problems

def test_probe_rejects_a_count_that_is_not_a_number() -> None:
    """The field carries a COUNT. A word in its place states nothing a reader can compare
    against the row's number, so it is not a declaration the gate can accept."""
    wordy = _close(
        906,
        "2026-09-21T06:00:00Z",
        _CITING_DETAIL.replace("rows=900", "rows=clean"),
    )
    problems, _, _, _ = close_verify_count_declared_problems([wordy], _PROBE_BOUNDARY)
    assert problems and "is not a row count" in problems[0], problems

def test_probe_a_mid_sentence_mention_is_not_a_declaration() -> None:
    """The read is POSITIONAL. A `rows=` token quoted mid-sentence is prose — the reason a
    lane must state the count in the canonical trailer and cannot satisfy the field by
    mentioning it (#88, `n=405` clause 5: prose must not SATISFY a field, and here it must
    not SUPPRESS it either). `n=762` is the live shape: a repair row that QUOTES
    `rows=761` while its own trailer carries nothing."""
    mid = _close(
        907,
        "2026-09-21T06:00:00Z",
        "CLOSE -- #1, a reader might write rows=9 right here and mean a count. "
        "tools/ledger.py verify rc=0 over 907 rows. board=closed head=deadbeef985b "
        "telemetry=measured",
    )
    problems, _, governed, covered = close_verify_count_declared_problems(
        [mid], _PROBE_BOUNDARY
    )
    assert problems and "declares no rows= count" in problems[0], problems
    assert (governed, covered) == (1, 0), (governed, covered)

def test_probe_a_quoted_token_in_a_non_close_row_is_out_of_scope() -> None:
    """The population is `close` rows only. A `run` row that quotes a trailer — the shape
    the repair path writes when it extends another row — is outside it, and its trailer
    is never read. (`n=762` is exactly that row for `n=761`.)"""
    repair = {
        "n": 908,
        "ts": "2026-09-21T06:00:00Z",
        "event": "run",
        "actor": "worker",
        "subject": "#1",
        "detail": "repair n=907: the row now declares rows=907 cost_usd=1.0",
    }
    problems, excused, governed, covered = close_verify_count_declared_problems(
        [repair], _PROBE_BOUNDARY
    )
    assert (problems, excused) == ([], []), (problems, excused)
    assert (governed, covered) == (0, 0), (governed, covered)

def test_probe_an_undatable_row_is_a_problem() -> None:
    """A close row whose `ts` will not parse cannot be excused BY its date either, so it
    is reported rather than silently dropped from the population."""
    broken = _close(909, "not-a-date", _CITING_DETAIL)
    problems, excused, governed, covered = close_verify_count_declared_problems(
        [broken], _PROBE_BOUNDARY
    )
    assert problems and "unparseable ts" in problems[0], problems
    assert (excused, governed, covered) == ([], 0, 0), (excused, governed, covered)

def test_probe_the_ledger_rows_field_is_the_one_it_reads() -> None:
    """The field's identity is `rows`, the spelling the ledger already carries (`n=761`,
    its repair at `n=762`) — never a second spelling for the same datum. The read takes the
    last `=`-carrying run only, so a key that merely ENDS in it does not match."""
    assert declared_verify_rows(f"{_CITING_DETAIL}") == ["900"]
    assert declared_verify_rows("ledger_rows=11 rows=12") == ["12"]
    assert declared_verify_rows("ledger_rows=11") == []

def _with_exemptions(tree: Path, exemptions: list[dict]) -> Path:
    """Write the factory's exemption table into a synthetic tree."""
    docs = tree / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "close-verify-count-exemptions.json").write_text(
        json.dumps({"_note": "probe fixture", "exemptions": exemptions}),
        encoding="utf-8",
    )
    return tree

def test_probe_an_exempted_row_is_excused_and_printed(tmp_path: Path) -> None:
    """A row whose repair space is empty is EXCUSED BY NAME and leaves the governed
    population — a visible debt, never a clean verdict and never a silent subtraction."""
    short = _close(
        900, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("rows=900", "rows=899")
    )
    tree = _with_exemptions(
        synthetic_tree(
            tmp_path / "exempt", rows=[short], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
        ),
        [{"n": 900, "reason": "repair space is empty — measured"}],
    )
    status, reason, problems, excused, counts = evaluate(tree)
    assert status == "pass", (status, reason, problems)
    assert not problems, problems
    assert excused and "EXEMPTED" in excused[0] and "n=900" in excused[0], excused
    assert counts["history"] == 1 and counts["governed"] == 0, counts

def test_probe_a_stale_exemption_fails(tmp_path: Path) -> None:
    """An exemption that matches no row is a FAILURE, never silence: it inflates the
    visible debt while excusing nothing."""
    tree = _with_exemptions(
        synthetic_tree(
            tmp_path / "stale",
            rows=[_close(900, "2026-09-21T06:00:00Z", _CITING_DETAIL)],
            invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
        ),
        [{"n": 999, "reason": "nothing"}],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", problems
    assert "stale exemption" in problems[0], problems[0]

def test_probe_an_exemption_that_excuses_nothing_fails(tmp_path: Path) -> None:
    """An entry for a row that COVERS its own number excuses nothing and is an ERROR."""
    tree = _with_exemptions(
        synthetic_tree(
            tmp_path / "covering",
            rows=[_close(900, "2026-09-21T06:00:00Z", _CITING_DETAIL)],
            invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
        ),
        [{"n": 900, "reason": "nothing"}],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", problems
    assert "excuses nothing" in problems[0], problems[0]

def test_probe_a_malformed_exemption_list_fails(tmp_path: Path) -> None:
    """A list that cannot be read is a problem, never a silent pass."""
    tree = synthetic_tree(
        tmp_path / "malformed",
        rows=[_close(900, "2026-09-21T06:00:00Z", _CITING_DETAIL)],
        invariants={INVARIANT_KEY: _PROBE_BOUNDARY},
    )
    docs = tree / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "close-verify-count-exemptions.json").write_text("{not json", encoding="utf-8")
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", problems
    assert "not valid JSON" in problems[0], problems[0]

def test_probe_an_exemption_does_not_blunt_the_bite(tmp_path: Path) -> None:
    """THE CONTROL for the exemption surface: an entry for a DIFFERENT row leaves the
    below-n finding biting, so the exit cannot widen into a blanket excuse."""
    short = _close(
        900, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("rows=900", "rows=899")
    )
    tree = _with_exemptions(
        synthetic_tree(
            tmp_path / "control", rows=[short], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
        ),
        [{"n": 901, "reason": "another row"}],
    )
    status, _, problems, _, _ = evaluate(tree)
    assert status == "fail", problems
    assert any("rows=899" in problem for problem in problems), problems
