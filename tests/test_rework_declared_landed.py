#!/usr/bin/env python3
r"""Gate: a close row's `rework=#N` declaration RESOLVES to a rework entry that LANDED.

Origin (issue #110). Section 11 gives the close row a canonical trailer, and `rework=#N`
is the token in it that names the rework entry THIS CLOSE PRODUCED. `evidence/rework.md`
is the log those entries live in. Nothing joined the two: a close row could name an entry
that was never written, and every reader would keep reporting the declaration as a
declaration — a claim with no landing. The rework log's own gate cannot see it either,
because that gate reads the log alone, and a declaration that never landed leaves no trace
in the file it was supposed to land in.

The property is EXISTENCE, never TRUTH
--------------------------------------
This gate asserts that the entry a close row NAMES exists. It does not assert that the
close truly produced it, and the difference is not academic — this ledger has a live
instance. Close row `n=633` declares `rework=#102`. That token is FALSE as a production
claim: the close RESOLVED entry #102 and produced no entry of its own, which its own
detail states in terms ("No NEW rework entry was produced by this close"), and which a
later row retired by naming at `n=642`. `#102` nonetheless EXISTS as an entry Subject, so
this gate passes `n=633` — CORRECTLY, on its own narrow property. Stated here rather than
left to be discovered, because the first reader who expects more of this gate will read
that pass as a miss.

The truth of a production claim is not readable offline. Establishing it would mean
reconstructing which defect a given close introduced, and no artifact records that; it is
a judgement, and it was made for `n=633` by the ruling at `n=642`. This gate reads a file
and asserts a membership, which is what a gate can do.

Two sides, two shared predicates — neither re-implemented
---------------------------------------------------------
Side 1, the declaration, is read through ONE predicate,
`tools/field_predicate.py::declared_rework`, which this gate CALLS rather than
re-deriving. `rework` is not a telemetry KEY, so `declared_telemetry` returns nothing for
it; the predicate is the positional read of the canonical trailing run. The trailer and
not the whole detail, because `detail`
is free prose that QUOTES trailers as evidence — the retirement rows quote the very token
they retire — and a scan over the whole detail reads a quotation as a declaration.

Side 2, the landing, is read through `tests/rework_table.py`, the ONE shared parse of the
entries table, and the `Subject` column is found BY NAME via `column_index`. Reading it by
position is the defect that module exists to prevent: a hardcoded index keeps returning
the cell at that position after the table is reordered, and hands back another column's
values under the name it asked for.

The subject VOCABULARY is bound, not re-spelled: `tools/audit.py::rework_bucket` is the
ONE classifier of a declared value, and it reads `SUBJECT_WORK_UNIT_RE`/`SUBJECT_NONE`
from the module that also reads that column to derive the change fail rate numerator.
Two hand-written patterns is how two readers come to disagree about which values name a
work unit at all — so the audit's declaration count and this gate share the classifier.

The population guard, and why this gate is the loud-fail kind
-------------------------------------------------------------
This gate PRINTS the population it examined — close rows read, declarations carried,
in scope, resolved, unresolved, out of scope — and FAILS LOUDLY when the in-scope count is
zero. Its population is the whole history rather than a forward-only slice, so an empty
one is never legitimate here: it means either the ledger lost its close rows or the
trailer predicate stopped reading them, and both are defects that a clean verdict over an
empty read would hide.

The out-of-scope values are PRINTED WITH THEIR COUNTS. Section 11 defines the grammar as
exactly three values — `#N` names the entry, `none` states the close produced none, and an
absent token stays `unstated` — so a fourth value is not a reference at all and would
silently leave the population. Printing it is what keeps it from leaving silently; no
verdict is asserted against it, because the ruling that ordered this gate scoped its
assertion to `#N`.

No retirement surface
---------------------
None is owed and none is built. Every declaration in this ledger's history resolves, so
the gate governs the whole of it and there is nothing to excuse. The declared retirement
surface that does exist, `docs/ledger-retirements.json`, admits only unresolvable SHAPE
tokens and its population is `head=` values — `rework=#102` is not one and could not enter
it, so an entry there would match no unresolvable token and be an error by that gate's own
terms (ruled at `n=642`).

Bootstrap
---------
`evidence/ledger.jsonl` and `evidence/rework.md` are BOOTSTRAP-created, so a tree that has
not bootstrapped — `TEMPLATE/` carries no `evidence/` — has neither a declaration to
resolve nor an entry to resolve it against, and this gate SKIPS with that reason rather
than passing over nothing.

Run:  python3 tests/test_rework_declared_landed.py
Exit: 0 every in-scope declaration resolves, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "evidence" / "ledger.jsonl"
REWORK = REPO / "evidence" / "rework.md"

# Side 2's parse, shared with `tests/test_rework.py` and `tests/gate_registry.py` — see
# that module's own docstring for why a second parser of one table is the defect rather
# than a convenience.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rework_table as rt  # noqa: E402

# The subject vocabulary, bound rather than retyped.
sys.path.insert(0, str(REPO / "tools"))
import audit  # noqa: E402

# Side 1's predicate, imported as a NAME so a private re-implementation cannot satisfy this
# gate's own import while reading the field some other way. The value's VOCABULARY is bound
# the same way, from `audit.rework_bucket` — one field, one read, one classification.
from field_predicate import declared_rework  # noqa: E402


def close_rows(ledger_text: str) -> list[dict]:
    """Every `close` row of a ledger text, in file order."""
    rows: list[dict] = []
    for line in ledger_text.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("event") == "close":
            rows.append(row)
    return rows


def declarations(ledger_text: str) -> list[dict]:
    """Every `rework=` token a close row's CANONICAL TRAILER declares.

    One dict per declaration: the row number, the close's own subject, and the value the
    token carries. The read is `field_predicate.declared_rework`, SHARED with the audit's
    declaration count rather than re-implemented here, and it bounds the read to the
    trailing run — so a token quoted inside a sentence is prose, never a declaration.
    """
    found: list[dict] = []
    for row in close_rows(ledger_text):
        for value in declared_rework(str(row.get("detail", ""))):
            found.append(
                    {
                        "n": row.get("n"),
                        "subject": str(row.get("subject", "")),
                        "value": value,
                    }
                )
    return found


def landed_subjects(rework_text: str) -> tuple[set[str], int, str | None]:
    """(subjects, entry count, reason) — the `Subject` cell of every entry, read BY NAME.

    `reason` is not None when the table could not be read at all, and the caller reports
    it as a failure: an unparsed region returns an empty set, which is indistinguishable
    from a log with nothing in it.
    """
    rows, reason = rt.column_cells(rework_text, "Entries", "Subject")
    if reason is not None:
        return set(), 0, reason
    return {cell for _, cell in rows if cell}, len(rows), None


def classify(decls: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(in_scope, keyword, other) — the declarations split by the FORM of their value.

    `audit.rework_bucket` is the ONE classifier, so this gate and the audit's declaration
    count agree on what a work-unit reference is by construction rather than by review.
    A keyword value is out of scope, not a failure: `none` states the close produced no
    entry, and `unstated` is the absence token (#53 clause 2).
    """
    in_scope: list[dict] = []
    keyword: list[dict] = []
    other: list[dict] = []
    for decl in decls:
        bucket = audit.rework_bucket(decl["value"])
        if bucket == "work_unit":
            in_scope.append(decl)
        elif bucket in ("none", "unstated"):
            keyword.append(decl)
        else:
            other.append(decl)
    return in_scope, keyword, other


def unresolved(in_scope: list[dict], landed: set[str]) -> list[dict]:
    """The in-scope declarations whose named entry is not in the log."""
    return [decl for decl in in_scope if decl["value"] not in landed]


# --- probes: a rule that has only seen good input has not been shown to reject bad input

SYNTHETIC_REWORK = (
    "## Entries\n\n"
    "| Date | Source | Defect | Root cause | Resolution | Prevented by | Subject |\n"
    "|---|---|---|---|---|---|---|\n"
    "| 2026-09-19 | a gate | a defect | a cause | a fix | a mechanism | #7 |\n"
)


def synthetic_ledger(*details: str) -> str:
    """A ledger TEXT of close rows carrying the given details, numbered from 1."""
    return "".join(
        json.dumps(
            {
                "n": index,
                "ts": "2026-01-01T00:00:00Z",
                "event": "close",
                "actor": "worker",
                "subject": f"#{index}",
                "detail": detail,
            }
        )
        + "\n"
        for index, detail in enumerate(details, 1)
    )


def check(name: str, condition: bool, detail: str, failures: list[str]) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(f"{name} — {detail}")


def main() -> int:
    for path in (LEDGER, REWORK):
        if not path.is_file():
            print(
                f"SKIP: no {path.relative_to(REPO)} in this tree — the ledger and the "
                f"rework log are BOOTSTRAP-created, so a tree that has not bootstrapped "
                f"has no declaration to resolve and no entry to resolve it against"
            )
            return 0

    print("rework declared-to-landed gate — a declaration resolves to a landed entry (#110)")

    ledger_text = LEDGER.read_text(encoding="utf-8")
    rework_text = REWORK.read_text(encoding="utf-8")

    closes = close_rows(ledger_text)
    decls = declarations(ledger_text)
    landed, entries, reason = landed_subjects(rework_text)

    if reason is not None:
        print(f"FAIL  the entries table could not be read: {reason}")
        return 1

    in_scope, keyword, other = classify(decls)
    missing = unresolved(in_scope, landed)

    print(f"  population: {len(closes)} close row(s) read, {len(decls)} rework token(s) carried")
    print(f"    in scope (rework=#N): {len(in_scope)}")
    print(f"    resolved: {len(in_scope) - len(missing)}")
    print(f"    unresolved: {len(missing)}")
    print(
        f"    out of scope: {len(keyword) + len(other)}"
        f" (rework=none {sum(1 for d in keyword if d['value'] == 'none')},"
        f" rework=unstated {sum(1 for d in keyword if d['value'] == 'unstated')},"
        f" other form {len(other)})"
    )
    print(f"  rework log: {entries} entry row(s), {len(landed)} distinct Subject cell(s)")
    for decl in other:
        print(
            f"  out of scope, not a reference and not a keyword: n={decl['n']} "
            f"({decl['subject']}) declares rework={decl['value']}"
        )

    failures: list[str] = []

    print("\n  the gate's own probes")
    synthetic_landed, synthetic_entries, _ = landed_subjects(SYNTHETIC_REWORK)

    landed_probe = classify(declarations(synthetic_ledger("a close. rework=#7 duration=1s")))
    missing_probe = classify(declarations(synthetic_ledger("a close. rework=#99 duration=1s")))
    keyword_probe = classify(declarations(synthetic_ledger("a close. rework=none duration=1s")))
    other_probe = classify(declarations(synthetic_ledger("a close. rework=seven duration=1s")))
    quoted_probe = declarations(
        synthetic_ledger("n=633 carries a false rework=#102 token, retired. duration=1s")
    )

    check(
        "a declaration naming a LANDED entry resolves",
        unresolved(landed_probe[0], synthetic_landed) == [],
        f"in_scope={[d['value'] for d in landed_probe[0]]}",
        failures,
    )
    check(
        "a declaration naming an entry that did NOT land is caught",
        len(unresolved(missing_probe[0], synthetic_landed)) == 1,
        f"unresolved={[d['value'] for d in unresolved(missing_probe[0], synthetic_landed)]}",
        failures,
    )
    check(
        "rework=none is out of scope — not a reference, and not a failure",
        keyword_probe[0] == [] and keyword_probe[1] != [],
        f"in_scope={keyword_probe[0]} keyword={keyword_probe[1]}",
        failures,
    )
    check(
        "a value that is neither a reference nor a keyword is REPORTED, never dropped",
        other_probe[2] != [] and other_probe[0] == [],
        f"other={other_probe[2]}",
        failures,
    )
    check(
        "a token QUOTED inside a sentence is prose, not a declaration",
        quoted_probe == [],
        f"declarations={quoted_probe}",
        failures,
    )
    check(
        "the Subject column is read by NAME — the synthetic table yields its own cell",
        synthetic_landed == {"#7"} and synthetic_entries == 1,
        f"landed={synthetic_landed} entries={synthetic_entries}",
        failures,
    )
    absent_subjects, absent_entries, absent_reason = landed_subjects("## Entries\n\n| a | b |\n")
    check(
        "a table with no Subject column reports WHY, never an empty set",
        absent_reason is not None and absent_entries == 0 and absent_subjects == set(),
        f"reason={absent_reason}",
        failures,
    )

    print()
    if not in_scope:
        print(
            f"FAIL  the gate examined nothing: {len(closes)} close row(s) carry no "
            f"rework=#N declaration. This gate's population is the whole history, so an "
            f"empty one is a defect in the ledger or in the trailer predicate — never a "
            f"clean verdict"
        )
        return 1

    for decl in missing:
        print(
            f"  - n={decl['n']} ({decl['subject']}) declares rework={decl['value']} — no "
            f"entry in evidence/rework.md carries Subject {decl['value']}"
        )

    if missing or failures:
        print(
            f"rework declared-to-landed gate FAILED: {len(missing)} unresolved "
            f"declaration(s), {len(failures)} probe failure(s)"
        )
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"rework declared-to-landed gate passed — {len(in_scope)} declaration(s) in scope, "
        f"all resolved to a landed entry"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
