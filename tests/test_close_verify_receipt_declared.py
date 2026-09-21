#!/usr/bin/env python3
"""Gate: a close row that cites a verify receipt declares the row count it measured.

Origin: issue #96, ruled at ledger `n=745`, whose first half is HQ's procedure law
(`docs/processes.md`, section Settlement & Release). The order: the settlement step runs
`tools/ledger.py verify` AFTER the close row is appended, so the receipt covers the row
it certifies. This gate is the half that makes the order MECHANICALLY CHECKABLE, and it
is a sharper predicate than the finding that prompted it.

WHY A CITATION ALONE CANNOT CARRY THE CLAIM. `verify` reads a subject's rows as a
SEQUENCE, so a run made while the close row does not yet exist has not seen the row it is
cited for — the receipt is structurally incapable of covering the artifact it certifies.
The finding asked only that a cited receipt STATE the row count it measured, and that is
checkable but WEAK: a count that is merely present can still be smaller than the row it
certifies. So the predicate is the statement itself:

    a close row that cites a verify receipt must DECLARE the row count that verify
    measured, and that count must be AT LEAST the row's own number.

A declared count of `n-1` is not a MALFORMED row. It is a row that has TOLD you its
verify predated the append, which is the whole point: the gate's finding names an ORDER
defect, and it accuses nobody of dishonesty. A citation taken early is not a false
citation — the rows that carry one stand as written.

THE PRECEDENT IS NOT AN INVENTION. `tools/ledger.py`'s close guard already refuses to
suppress a measurement it genuinely took unless the row DECLARES the field
(`declares_field(detail, "cost_usd" | "tokens_in" | ...)`). This gate is the sibling of a
mechanism that already exists, one step out: the guard reads what the AUTHOR declared,
this reads what the ROW declares about a receipt it cites.

THE FIELD IS READ THROUGH `tools/field_predicate.py` AND NOTHING ELSE. Section 11's
one-field-one-predicate law binds a NEW field exactly as it binds an old one: the key
`verify_rows` is declared in that module beside `declared_verify_rows`, and this gate
imports it rather than parsing the detail itself. The read is POSITIONAL — the canonical
trailer — so a `verify_rows=` token quoted mid-sentence is PROSE and never a
declaration. Prose can TRIGGER this gate's question (a citation IS prose) and can never
SATISFY it, which is the direction §8's prose-as-data law forbids (#88, `n=405` clause 5).

THE POPULATION IS THE WHOLE CLOSE HISTORY, SO ZERO IS LOUD. This is the one place this
gate refuses the family's proportional skip. A gate whose population is an event may
legitimately be empty in a young tree and must SKIP with a stated reason; `n=745` rules
that form out here — "its population is the whole close history, so the loud-fail-on-zero
form IS correct". A ledger carrying rows but no `close` row at all is a read that judged
nothing, and a clean verdict over a population that was never judged is exactly what P29
forbids. (Contrast #112, whose population is a shape a factory may legitimately never
produce and which is therefore proven by its probe instead.)

FORWARD-ONLY, AND NOTHING IS BACKFILLED. The boundary is a DECLARED FACTORY PARAMETER
(`docs/ledger-invariants.json`, keyed by this gate's own name) and never a module constant
(#78, ruled `n=515` clause 4): the LOGIC is universal and the DATE is this factory's. Rows
before the boundary are EXCUSED AND PRINTED, never repaired — a count written into a row
today for a receipt taken days ago would be a falsified record, not a repair. The gate
SHIPS (issue #130's precedent), so a bootstrapped factory reads its own declaration; a
tree with no ledger, no declaration or no key SKIPS with the reason printed, which is how
the same file runs in `TEMPLATE/`, where `evidence/` does not exist.

SEVERITY IS LATENT, STATED SO THE GATE IS NOT OVERSOLD: `verify` exits 0 on the live
ledger, and `n=596`'s write-path refusal already blocks the `n=588` shape. This gate
closes the RECORDING hole, not a live outage. Its first five known instances — `n=746`
(#121), `n=749` (#119), `n=752` (#120), `n=763` (#66), `n=783` (#124) — each cite verify
in prose with no declared count and are EXCUSED by the declared boundary.

WHAT THIS GATE DOES NOT REACH, STATED RATHER THAN IMPLIED. The citation trigger is the
receipt's FORM (`verify` followed, in one sentence, by a result: an `rc=` exit code, the
word `clean`, or `exits 0`). Measured over the 113 close rows in this factory's ledger,
35 match and every one of them is a genuine receipt statement; a row that words its
receipt some other way is NOT seen as citing, and is therefore not governed. That bound is
deliberate and stated: the alternative — triggering on any mention of `verify` — fires on
rows that DISCUSS the mechanism rather than cite a run (measured: three such rows), and a
trigger that demands a declaration from a row which cites nothing is worse than one that
misses a shape nobody has yet written.

Run:  python3 -m pytest tests/test_close_verify_receipt_declared.py -q
Exit: 0 clean or skipped-with-reason; non-zero on a post-boundary close row that cites a
      verify receipt without declaring a count covering its own number, and non-zero on a
      ledger that carries no close row at all.
"""

from __future__ import annotations

import re
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
INVARIANT_KEY = "close_verify_receipt_declared"

# The receipt's FORM, and the only thing this gate reads as a CITATION. The command and a
# result, in one sentence: `tools/ledger.py verify rc=0` (n=746, n=749, n=752, n=763),
# `py verify rc=0` (n=783), `ledger verify: clean` (n=353), `verify clean 616 row(s)`
# (n=618), `verify reports clean and exits 0` (n=491-502). A sentence boundary ends the
# window, so a row that NAMES verify and then reports something else is not a citation.
_CITATION_RESULT = (
    r"\brc\s*=\s*\d"      # the exit code, the form the settlement order itself uses
    r"|\bclean\b"         # the prose result
    r"|\bexits?\s+0\b"    # the spelled-out form
)
VERIFY_CITE = re.compile(
    rf"\bverify\b[^.\n]{{0,80}}?(?:{_CITATION_RESULT})", re.IGNORECASE
)

def detail_cites_verify(detail: str) -> str | None:
    """The citation `detail` carries, verbatim, or None when it carries none.

    Returns the MATCHED TEXT rather than a bool so the gate's finding can quote the shape
    that made the row governed: a trigger that over-fires then names itself in the output
    instead of demanding a declaration for a reason the author cannot see. The bound is
    the `VERIFY_CITE` window above, stated there rather than implied here.
    """
    match = VERIFY_CITE.search(str(detail))
    return match.group(0) if match else None

def close_verify_receipt_declared_problems(
    rows: list[dict], boundary_text: str
) -> tuple[list[str], list[str], int, int]:
    """`(problems, excused, cited, covered)` over `rows` — the invariant, pure.

    `rows` is EVERY row of a ledger, not a filtered population: the event filter and the
    boundary are part of the rule, so a probe cannot satisfy it by pre-filtering. `cited`
    counts the governed rows the predicate actually APPLIED to, which the live run prints:
    a rule conditional on a citation can otherwise read clean over a population it judged
    none of, and that is indistinguishable from a clean one.

    A row before the boundary is EXCUSED by name and never called clean — the distinction
    `tools/ledger.py` draws for its own legacy closes, so "clean" and "excused" are never
    the same output.
    """
    problems: list[str] = []
    excused: list[str] = []
    cited = 0
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
        detail = str(row.get("detail") or "")
        citation = detail_cites_verify(detail)
        if citation is None:
            # The invariant is CONDITIONAL: a row that cites no receipt owes no count, and
            # that is a scope statement rather than an excuse.
            continue
        cited += 1
        if not isinstance(n, int):
            problems.append(
                f"n={n!r} ({ts}) cites a verify receipt ({citation!r}) but carries no "
                f"integer row number, so no declared count can be shown to cover it"
            )
            continue
        declared = declared_verify_rows(detail)
        if not declared:
            problems.append(
                f"n={n} ({ts}) cites a verify receipt ({citation!r}) and declares no "
                f"verify_rows= count in its canonical trailer — a receipt whose row count "
                f"is unstated cannot be told from one taken before this row existed (#96)"
            )
            continue
        if len(declared) > 1:
            problems.append(
                f"n={n} ({ts}) declares {len(declared)} verify_rows= values "
                f"({', '.join(declared)}) — two tokens for one field have no canonical "
                f"reading (SKILL.md section 8)"
            )
            continue
        value = declared[0]
        if not value.isdigit():
            problems.append(
                f"n={n} ({ts}) declares verify_rows={value}, which is not a row count "
                f"verify could have reported"
            )
            continue
        if int(value) < n:
            problems.append(
                f"n={n} ({ts}) declares verify_rows={value} and is itself row {n}: the "
                f"receipt it cites covered {value} row(s), so that verify ran BEFORE this "
                f"row was appended — the ORDER defect the #96 order exists to prevent"
            )
            continue
        covered += 1

    return problems, excused, cited, covered

def evaluate(repo: Path) -> tuple[str, str, list[str], list[str], dict]:
    """`(status, reason, problems, excused, counts)` over `repo` — the probe-able core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip, and
    both outrank a verdict over nothing: the zero-close-history check runs only on an
    otherwise-clean ledger, so a defect is never hidden behind "there was nothing to
    judge".

    `counts` is `{"history", "governed", "cited", "covered"}` — close rows in the ledger,
    close rows at or after the boundary, the governed rows that cite a verify receipt, and
    those whose declared count covers their own number. The live run prints all four: this
    gate's question is conditional on a citation, so the number of rows it APPLIED to is
    the reader's only signal that it examined anything at all (P29).
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return "skip", str(exc), [], [], {}
    except GateError as exc:
        return "fail", "", list(exc.problems), [], {}

    problems, excused, cited, covered = close_verify_receipt_declared_problems(
        rows, boundary_text
    )
    counts = {
        "history": sum(1 for row in rows if row.get("event") == "close"),
        "governed": len(post_boundary_rows(rows, boundary, "close")),
        "cited": cited,
        "covered": covered,
    }
    if problems:
        return "fail", "", problems, excused, counts

    # THE LOUD ZERO (#96, ruling n=745). This gate's population is the whole close
    # history, so an empty one is NOT a young factory: the ledger carries rows and not one
    # of them is a close, which means the reader judged nothing. The family's proportional
    # skip would report that in the same shape as a clean run.
    if counts["history"] == 0:
        return "fail", "", [
            f"{LEDGER_REL} carries {len(rows)} row(s) and not one of them is a close — "
            f"this gate's population is the whole close history, so a zero count is a "
            f"read that judged nothing, never a clean run (n=745, contrast #112)"
        ], excused, counts
    return "pass", "", [], excused, counts

# --- live gate -------------------------------------------------------------------

def test_live_close_rows_that_cite_verify_declare_the_count() -> None:
    status, reason, problems, excused, counts = evaluate(REPO)
    for line in excused:
        print(f"  excused: {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "every close row at or after the declared boundary that cites a verify "
            "receipt must declare a verify_rows= count covering its own number:\n  "
            + "\n  ".join(problems)
        )
    print(
        f"close verify-count gate: {counts['history']} close row(s) in history, "
        f"{counts['governed']} governed by the declared boundary — of those, "
        f"{counts['cited']} cite a verify receipt and {counts['covered']} declare a count "
        f"covering the row; {len(excused)} excused (pre-boundary)"
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
# canonical trailer beside the other close fields.
_CITING_DETAIL = (
    "CLOSE -- #1, the gate lands. VERIFY RECEIPT, TAKEN AFTER THIS ROW EXISTS, per the "
    "#96 settlement order: tools/ledger.py verify rc=0, reporting ledger clean over 900 "
    "row(s). verify_rows=900 board=closed head=deadbeef985b outcome=accepted "
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
    """`rows=[]` writes an EMPTY ledger: the bootstrap state of a factory that has
    created the file and appended nothing. Nothing to judge, stated as such."""
    tree = synthetic_tree(tmp_path / "empty", rows=[], invariants={INVARIANT_KEY: _PROBE_BOUNDARY})
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
    """The positive direction, with the population PRINTED: one governed row, one citing
    row, one covered count. A verdict over a population that was never named is what this
    count exists to prevent (P29)."""
    tree = synthetic_tree(
        tmp_path / "ok", rows=[_OK], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, reason, problems, excused, counts = evaluate(tree)
    assert status == "pass", (status, reason, problems)
    assert counts == {"history": 1, "governed": 1, "cited": 1, "covered": 1}, counts
    assert excused == [], excused

def test_probe_a_count_below_the_rows_own_number_bites(tmp_path: Path) -> None:
    """THE BITE the ruling asks for, and it is an ORDER finding rather than a schema
    finding: `n=900` declaring `verify_rows=899` has told the reader its verify covered
    899 rows while this row is number 900, i.e. the receipt predated the append."""
    short = _close(900, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("verify_rows=900", "verify_rows=899"))
    tree = synthetic_tree(
        tmp_path / "short", rows=[short], invariants={INVARIANT_KEY: _PROBE_BOUNDARY}
    )
    status, reason, problems, _, counts = evaluate(tree)
    assert status == "fail", (status, reason, problems)
    assert "verify_rows=899" in problems[0] and "900" in problems[0], problems[0]
    assert "BEFORE this row was appended" in problems[0], problems[0]
    assert counts["cited"] == 1 and counts["covered"] == 0, counts

def test_probe_the_boundary_comes_from_the_declaration(tmp_path: Path) -> None:
    """The same offending row FAILS under one declaration and is EXCUSED under a later
    one, which is what makes the date a factory parameter rather than a module constant."""
    short = _close(900, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("verify_rows=900", "verify_rows=899"))
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
    the row it certifies, and equality is the common case: the close row is the last row
    verify read."""
    exact = _close(901, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("900", "901"))
    problems, excused, cited, covered = close_verify_receipt_declared_problems(
        [exact], _PROBE_BOUNDARY
    )
    assert problems == [] and excused == [], (problems, excused)
    assert (cited, covered) == (1, 1), (cited, covered)

def test_probe_accepts_a_count_above_the_rows_own_number() -> None:
    """Rows appended after the receipt do not invalidate it: a count above the row's own
    number is what a receipt taken later in the same settlement pass looks like."""
    later = _close(902, "2026-09-21T06:00:00Z", _CITING_DETAIL.replace("900", "910"))
    problems, _, cited, covered = close_verify_receipt_declared_problems(
        [later], _PROBE_BOUNDARY
    )
    assert problems == [], problems
    assert (cited, covered) == (1, 1), (cited, covered)

def test_probe_rejects_a_citing_row_with_no_declared_count() -> None:
    """What the five known instances look like: the citation is there, the count is not.
    Committing a count into prose is the shape `n=746`/`n=749`/`n=752`/`n=763`/`n=783`
    carry, and prose does not satisfy a field."""
    bare = _close(
        903,
        "2026-09-21T06:00:00Z",
        "CLOSE -- #1, the tree moved. tools/ledger.py verify rc=0, reporting ledger clean "
        "over 903 row(s). board=closed head=deadbeef985b telemetry=measured",
    )
    problems, _, cited, covered = close_verify_receipt_declared_problems(
        [bare], _PROBE_BOUNDARY
    )
    assert problems and "declares no verify_rows= count" in problems[0], problems
    assert "rc=0" in problems[0], problems
    assert (cited, covered) == (1, 0), (cited, covered)

def test_probe_rejects_two_tokens_for_one_field() -> None:
    """SKILL.md section 8: two tokens for one field have no canonical reading, so the gate
    reports the multiplicity rather than silently reading the first."""
    twice = _close(
        904,
        "2026-09-21T06:00:00Z",
        _CITING_DETAIL.replace("verify_rows=900", "verify_rows=904 verify_rows=905"),
    )
    problems, _, _, _ = close_verify_receipt_declared_problems([twice], _PROBE_BOUNDARY)
    assert problems and "2 verify_rows= values" in problems[0], problems

def test_probe_rejects_a_count_that_is_not_a_number() -> None:
    """The field carries a COUNT. A word in its place states nothing a reader can compare
    against the row's number, so it is not a declaration the gate can accept."""
    wordy = _close(
        905,
        "2026-09-21T06:00:00Z",
        _CITING_DETAIL.replace("verify_rows=900", "verify_rows=clean"),
    )
    problems, _, _, _ = close_verify_receipt_declared_problems([wordy], _PROBE_BOUNDARY)
    assert problems and "is not a row count" in problems[0], problems

def test_probe_a_mid_sentence_mention_is_not_a_declaration() -> None:
    """The read is POSITIONAL. A `verify_rows=` token quoted mid-sentence is prose — the
    reason a future reader must state the count in the canonical trailer and cannot
    satisfy the field by mentioning it (#88, `n=405` clause 5: prose must not SATISFY a
    field, and here it must not SUPPRESS it either)."""
    mid = _close(
        906,
        "2026-09-21T06:00:00Z",
        "CLOSE -- #1, a reader might write verify_rows=9 right here and mean a count. "
        "tools/ledger.py verify rc=0 over 906 rows. board=closed head=deadbeef985b "
        "telemetry=measured",
    )
    problems, _, cited, covered = close_verify_receipt_declared_problems(
        [mid], _PROBE_BOUNDARY
    )
    assert problems and "declares no verify_rows= count" in problems[0], problems
    assert (cited, covered) == (1, 0), (cited, covered)

def test_probe_a_row_that_cites_nothing_is_out_of_scope() -> None:
    """The invariant is CONDITIONAL: no citation, nothing owed. Neither excused nor
    clean — the predicate never applied to it, and `cited` is what says so."""
    silent = _close(
        907,
        "2026-09-21T06:00:00Z",
        "CLOSE -- #1, no receipt is cited here. board=closed head=deadbeef985b "
        "telemetry=measured",
    )
    problems, excused, cited, covered = close_verify_receipt_declared_problems(
        [silent], _PROBE_BOUNDARY
    )
    assert (problems, excused) == ([], []), (problems, excused)
    assert (cited, covered) == (0, 0), (cited, covered)

def test_probe_ignores_non_close_events() -> None:
    """A `claim` row citing verify is outside the population entirely: the order this gate
    upholds governs the SETTLEMENT row, and a claim leg owes no receipt."""
    claim = {
        "n": 908,
        "ts": "2026-09-21T06:00:00Z",
        "event": "claim",
        "actor": "worker",
        "subject": "#1",
        "detail": "Claimed. tools/ledger.py verify rc=0 was clean before this row.",
    }
    problems, excused, cited, covered = close_verify_receipt_declared_problems(
        [claim], _PROBE_BOUNDARY
    )
    assert (problems, excused) == ([], []), (problems, excused)
    assert (cited, covered) == (0, 0), (cited, covered)

def test_probe_an_undatable_row_is_a_problem() -> None:
    """A close row whose `ts` will not parse cannot be excused BY its date either, so it
    is reported rather than silently dropped from the population."""
    broken = _close(909, "not-a-date", _CITING_DETAIL)
    problems, excused, cited, covered = close_verify_receipt_declared_problems(
        [broken], _PROBE_BOUNDARY
    )
    assert problems and "unparseable ts" in problems[0], problems
    assert (excused, cited, covered) == ([], 0, 0), (excused, cited, covered)
