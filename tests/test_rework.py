#!/usr/bin/env python3
"""Gate: every rework entry is complete, and the table is still one table.

`evidence/rework.md` is only worth having if an entry can be read by someone who
was not there. A row with an empty root cause, or "Prevented by: TBD", is a
placeholder that looks like a record — and the improvement-loop criterion (S3)
turns on that last column actually naming something.

The second property is the one this gate originally missed: the entries are a
*single* table, so a blank line inside it splits the log into fragments and the
rows after the break render with no header above them. The gate reported a clean
pass over exactly that shape, because it parsed the rows it expected to find and
never asked whether they were still contiguous. A check that only looks for what
its author expected is not a check.

The third property is about the Rates section above the table, and it is the
same defect shape again. The section's own rule is that the rates are recomputed
rather than remembered — and that rule had no mechanism behind it. The headline
figures were published once as a live reading, undated, went stale, and were
wrong for a day before anyone noticed. A rate claim is only reproducible if it
carries the date it was taken *and* names which of the two forms it is: the
share of work, or rework per close. Two different numbers travel under one name
otherwise, which is exactly how the wrong one gets quoted.

The fourth property is the coverage figure, and it is the one figure in that
section whose inputs no other lane can move. The rate reads the ledger's
closed-subject set, so any lane that closes a work unit moves it — asserting it
live would fail on someone else's commit, which is the false-RED shape this
repo has already paid for. The coverage counts `Subject` cells against entry
rows, and both are properties of this file alone, so the gate can assert it
against the live measurement and mean it. It is measured through the audit's own
predicate rather than re-derived here, so one number cannot have two
implementations free to disagree.

The fifth property is the one question this file cannot answer about itself:
whether the work unit a `Subject` names actually EXISTS. Coverage counts
determinate cells, and a `#N` pointing at something that never closed is still
determinate — so coverage can read 100% while the change fail rate silently drops
the case: the entry looks linked and no failure is counted for it. That is why
the resolution leg takes the ledger's closed-subject set as an INPUT, and it is
the deliberate exception to the invariance above. The *coverage assertion* is
invariant to the closed set — probed at the end of `main`, and the property that
makes its live assertion safe — while the resolution leg is only meaningful
against it. The two run side by side on purpose: one assertion no other lane can
move, one that reads exactly what another lane moves, and neither softens the
other.

Run:  python3 tests/test_rework.py
Exit: 0 all entries complete and contiguous, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REWORK = REPO / "evidence" / "rework.md"
# Read by the resolution leg only. Everything else in this gate is a property of
# the rework file alone; the closed set is the one input that arrives from
# outside, and the leg that takes it says so where it is used.
LEDGER = REPO / "evidence" / "ledger.jsonl"

# The coverage predicate lives in `tools/audit.py`, which reads the same file this
# gate reads. It is imported rather than re-implemented so that one number cannot
# have two implementations free to drift apart.
sys.path.insert(0, str(REPO / "tools"))
import audit  # noqa: E402 — the path above is set deliberately before this line

# The entries-table PARSE is shared — `tests/rework_table.py` — because
# `tests/gate_registry.py` reads one COLUMN of this same table (the `Prevented by` cell,
# the column section 11 makes a law surface) to find the mechanisms a recorded law names
# and assert each one is registered (issue #107, ruling n=639, direction 4). Two parsers
# of one table is the defect this repo names as one-field-one-predicate, and its failure
# is silent: they agree until a cell count or a column order changes, and then one of
# them returns another column's values under the name it asked for. What stays HERE is
# the gate's own subject — completeness, contiguity, vocabulary, rates — and the column
# list it asserts against.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rework_table as rt  # noqa: E402

COLUMNS = ["Date", "Source", "Defect", "Root cause", "Resolution", "Prevented by", "Subject"]
PLACEHOLDERS = {"tbd", "todo", "n/a", "-", "?", "unknown", "none"}

# `Subject` is the one column where `none` is a *defined answer* rather than a
# dodge: it means the defect was caught before any change landed. So the column
# is exempt from PLACEHOLDERS and carries its own vocabulary instead — and that
# vocabulary is BOUND from `tools/audit.py` rather than retyped here, because
# that module reads the same column to derive the change fail rate numerator: two
# hand-written patterns is how the gate and the reader come to disagree about
# which cells name a work unit at all.
SUBJECT_NONE = audit.SUBJECT_NONE
SUBJECT_LEGACY = audit.SUBJECT_PRE_COLUMN
SUBJECT_RE = audit.SUBJECT_WORK_UNIT_RE

HEADER = "| Date | Source | Defect | Root cause | Resolution | Prevented by | Subject |"
SEPARATOR = "|---|---|---|---|---|---|---|"

def section_body(text: str) -> str | None:
    """The body of the `## Entries` section, or None when it is absent."""
    return rt.section_body(text, "Entries")

def rates_body(text: str) -> str | None:
    """The body of the `## Rates` section, or None when it is absent."""
    return rt.section_body(text, "Rates")

# A numeric rate claim: a percentage, or a count stated per close. Prose that
# merely *names* the forms (the formula table, the explanation of why two forms
# are reported) carries no digits and is deliberately not matched — requiring a
# date beside it would be noise, and a gate that cries wolf gets deleted.
RATE_CLAIM = re.compile(r"\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s+(?:entries\s+)?per\s+close")
RATE_PREDICATES = ("share of", "per close")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

def rate_claim_problems(text: str) -> list[str]:
    """Every rate claim in `## Rates` must carry its own date and its predicate."""
    body = rates_body(text)
    if body is None:
        return ["no '## Rates' section — a rate with no stated formula cannot be checked"]

    problems: list[str] = []
    for paragraph in re.split(r"\n\s*\n", body):
        claim = " ".join(paragraph.split())
        if not claim or not RATE_CLAIM.search(claim):
            continue
        missing: list[str] = []
        if not ISO_DATE.search(claim):
            missing.append("its date")
        if not any(predicate in claim for predicate in RATE_PREDICATES):
            missing.append("its predicate ('share of …' or '… per close')")
        if missing:
            problems.append(
                "the Rates section states a rate without " + " and ".join(missing)
                + f": {claim[:90]!r}"
            )
    return problems

# The coverage claim — `N of M entries carry a subject` — is the one figure in the
# Rates section whose inputs no other lane can move: N counts the `Subject` cells
# that are determinate (`#<n>` or `none`) and M counts entry rows, so both are
# properties of THIS FILE. The rate and the closed-work-unit denominator are the
# opposite case: they read the ledger's closed-subject set, which every lane moves
# when it closes a work unit, so asserting them live would fail on another lane's
# commit — the false-RED class #41 names. That asymmetry is why only the coverage
# is gated HERE, and why this measurement passes an EMPTY closed set: the value is
# invariant to it, which is the property that makes a live assertion safe. The
# closed set is not ignored — `subject_resolution_problems` below reads it
# deliberately, and asserts a different property against it.
COVERAGE_CLAIM = re.compile(r"(\d+)\s+of\s+(\d+)\s+entr", re.I)

def measure_coverage() -> tuple[int, int]:
    """(determinate, entries) for evidence/rework.md — the audit's own predicate.

    Imported from `tools/audit.py` rather than re-derived, so the two surfaces
    cannot drift apart about one number.
    """
    stats = audit.parse_rework(REWORK, set())
    return stats["subject_coverage_numerator"], stats["subject_coverage_denominator"]

def coverage_claim_problems(text: str) -> list[str]:
    """The Rates section's coverage claim must equal the coverage measured live."""
    body = rates_body(text)
    if body is None:
        return ["no '## Rates' section — a coverage claim with no section cannot be checked"]
    # Emphasis is stripped before matching: the live sentence reads
    # `**8 of 27** entries carry`, and a pattern requiring whitespace right after
    # the number silently matches nothing there — which would read as "no claim
    # stated" and pass a document whose figure is wrong. Markup must not be able
    # to hide a claim from the gate.
    claims = COVERAGE_CLAIM.findall(body.replace("*", ""))
    if not claims:
        return [
            "the Rates section states no coverage claim — a figure that can be "
            "deleted to dodge the gate is not gated"
        ]
    measured = measure_coverage()
    problems: list[str] = []
    for n_str, m_str in claims:
        if (int(n_str), int(m_str)) != measured:
            problems.append(
                f"the Rates section claims {n_str} of {m_str} entries carry a "
                f"subject; measured from evidence/rework.md it is "
                f"{measured[0]} of {measured[1]}"
            )
    return problems

# The resolution leg — the one assertion here that is NOT invariant to another
# lane's work, and deliberately so. Coverage answers "does this entry name a work
# unit?" from this file alone; resolution answers "does that work unit exist?",
# which only the ledger knows. A dangling `#N` is the failure this leg exists to
# catch: the entry reads as linked, coverage counts it as determinate, and the
# change fail rate quietly counts no failure for it — the linkage looks complete
# while a case has fallen out of the numerator.
#
# It counts DISTINCT SUBJECTS, never cells: two entries against one work unit
# (`#42` carries two in this log) are lawful, and the question is how many work
# units are referenced, not how many rows mention one. The count is returned
# beside the problems rather than derived by the caller, so the printed figure
# and the thing that was checked cannot describe different populations.
def subject_resolution_problems(
    rows: list[tuple[int, list[str]]], closed_subjects: set[str]
) -> tuple[list[str], int]:
    """(problems, distinct determinate subjects) for an entries table.

    A problem names the subject and the row it was first seen on: an unresolvable
    reference reported as a bare count is a finding nobody can act on.
    """
    named: dict[str, int] = {}
    for n, cells in rows:
        if len(cells) != len(COLUMNS):
            continue
        subject = cells[-1]
        if not SUBJECT_RE.fullmatch(subject):
            continue
        named.setdefault(subject, n)

    problems = [
        f"Subject {subject} (first seen at row {named[subject]}) names a work "
        "unit that never closed — a dangling reference: the entry reads as "
        "linked, coverage counts it as determinate, and the change fail rate "
        "counts no failure for it"
        for subject in sorted(named, key=lambda s: int(s[1:]))
        if subject not in closed_subjects
    ]
    return problems, len(named)

is_header = rt.is_header
is_separator = rt.is_separator
entry_rows = rt.entry_rows

def contiguity_problems(body: str, parsed: int) -> list[str]:
    """The entries must be one table under one header — not fragments."""
    lines = [line.strip() for line in body.splitlines()]
    headers = [i for i, line in enumerate(lines) if is_header(line)]
    if len(headers) != 1:
        return [f"the Entries section has {len(headers)} header row(s), expected exactly 1"]
    head = headers[0]
    if head + 1 >= len(lines) or not is_separator(lines[head + 1]):
        return ["the line after the Entries header is not a separator row"]
    # The block is the header plus every *consecutive* following `|` line: a
    # blank line ends it, which is precisely what makes the rows after the gap
    # render headerless.
    block = 0
    i = head + 2
    while i < len(lines) and lines[i].startswith("|"):
        block += 1
        i += 1
    if block != parsed:
        return [
            f"the Entries table is fragmented: {parsed} entry row(s) parsed, "
            f"{block} sit under one contiguous header"
        ]
    return []

def check_text(text: str) -> tuple[list[str], int]:
    """(problems, entry count) for a rework document — pure, so it can be probed."""
    body = section_body(text)
    if body is None:
        return ["no '## Entries' section — cannot gate"], 0

    rows = entry_rows(body)
    problems: list[str] = []
    if not rows:
        problems.append("no entries — an empty log cannot report a rework rate")

    for n, cells in rows:
        if len(cells) != len(COLUMNS):
            problems.append(f"row {n}: {len(cells)} cells, expected {len(COLUMNS)}")
            continue
        date = cells[0]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            problems.append(f"row {n}: date {date!r} is not YYYY-MM-DD")
        for label, value in zip(COLUMNS[1:], cells[1:]):
            if not value:
                problems.append(f"row {n} ({date}): '{label}' is empty")
            elif label == "Subject":
                # The Subject column's own vocabulary — see SUBJECT_LEGACY.
                if value not in (SUBJECT_NONE, SUBJECT_LEGACY) and not SUBJECT_RE.fullmatch(value):
                    problems.append(
                        f"row {n} ({date}): 'Subject' is {value!r} — expected "
                        "'#<n>' (the work unit whose change failed), 'none' "
                        "(caught before any change landed), or "
                        f"{SUBJECT_LEGACY!r}"
                    )
            elif value.strip("`").strip().lower() in PLACEHOLDERS:
                problems.append(
                    f"row {n} ({date}): '{label}' is a placeholder ({value!r}) — "
                    "say what is true, or 'nothing yet'"
                )

    problems.extend(contiguity_problems(body, len(rows)))
    problems.extend(rate_claim_problems(text))
    problems.extend(coverage_claim_problems(text))
    return problems, len(rows)

def probe(name: str, text: str, want_problems: bool, failures: list[str]) -> None:
    problems, _ = check_text(text)
    ok = bool(problems) == want_problems
    detail = problems[0] if problems else "no problems"
    print(f"  {'PASS' if ok else 'FAIL'}  {name} — {detail}")
    if not ok:
        failures.append(name)

def resolution_probe(
    name: str,
    doc: str,
    closed: set[str],
    want_problems: bool,
    want_examined: int,
    failures: list[str],
    want_named: str | None = None,
) -> None:
    """Probe the resolution leg, which takes rows and a closed set — not a document.

    `want_named` asserts the report names the offending subject rather than
    merely counting it, which is the half of the discipline a boolean cannot check.
    """
    problems, examined = subject_resolution_problems(
        entry_rows(section_body(doc) or ""), closed
    )
    ok = bool(problems) == want_problems and examined == want_examined
    if want_named is not None:
        ok = ok and any(want_named in p for p in problems)
    detail = problems[0] if problems else f"{examined} distinct subject(s), none dangling"
    print(f"  {'PASS' if ok else 'FAIL'}  {name} — {detail}")
    if not ok:
        failures.append(name)

def good_row(n: int, subject: str | None = None) -> str:
    subj = f"#{n}" if subject is None else subject
    return (
        f"| 2026-09-12 | probe {n} | defect {n} | cause {n} | fix {n} | gate {n} "
        f"| {subj} |"
    )

def coverage_line(claim: str | None = None) -> str:
    """A coverage sentence that matches the live measurement unless told otherwise.

    Generated rather than typed: a hardcoded probe figure would itself go stale as
    the log grows, and the probe would then fail the gate it exists to test.
    """
    if claim is None:
        n, m = measure_coverage()
        claim = f"**{n} of {m}** entries carry a determinate Subject"
    return claim + "\n\n"

def dated_rates(claim: str | None = None) -> str:
    """A Rates section that satisfies every Rates rule — the probes' base document."""
    return (
        "## Rates\n\n"
        "At 2026-09-12 this factory had 4 closes against 11 rework entries — "
        "a share of 73%, or 2.75 entries per close.\n\n" + coverage_line(claim)
    )

def main() -> int:
    if not REWORK.is_file():
        sys.exit("evidence/rework.md is missing")

    text = REWORK.read_text(encoding="utf-8")
    problems, count = check_text(text)
    if problems:
        print(f"rework log incomplete: {len(problems)} problem(s)\n")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"rework log clean: {count} complete entry(s)")

    # The gate is probed on synthetic documents, in-process: it never writes a
    # temp file and never re-invokes itself, so a probe cannot become the
    # defect it is testing for.
    print("\nthe gate's own probes")
    failures: list[str] = []
    # A Rates section has to be present for the probes to be about the entries
    # table, so each document carries one that passes.
    entries = f"## Entries\n\n{HEADER}\n{SEPARATOR}\n"
    two_rows = dated_rates() + entries + f"{good_row(1)}\n{good_row(2)}\n"
    probe("a well-formed two-row table passes", two_rows, False, failures)
    probe(
        "a blank line after the header is caught",
        dated_rates() + entries + f"\n{good_row(1)}\n",
        True, failures,
    )
    probe(
        "a blank line between two rows is caught",
        dated_rates() + entries + f"{good_row(1)}\n\n{good_row(2)}\n",
        True, failures,
    )
    probe(
        "a duplicated header is caught",
        dated_rates() + entries + f"{good_row(1)}\n{HEADER}\n{SEPARATOR}\n{good_row(2)}\n",
        True, failures,
    )
    probe(
        "an undated rate claim is caught",
        "## Rates\n\nThis factory has 17 rework entries against 29 closes — "
        "a share of 37%.\n\n" + coverage_line() + entries + f"{good_row(1)}\n",
        True, failures,
    )
    probe(
        "a dated rate claim that names no form is caught",
        "## Rates\n\nAt 2026-09-18 the rework rate was 59%.\n\n"
        + coverage_line() + entries + f"{good_row(1)}\n",
        True, failures,
    )
    probe(
        "prose naming the forms without a number is not a claim",
        "## Rates\n\nThe share of work and rework per close are reported "
        "separately.\n\n" + coverage_line() + entries + f"{good_row(1)}\n",
        False, failures,
    )
    probe(
        "a Subject naming a work unit passes",
        dated_rates() + entries + f"{good_row(1, '#31')}\n",
        False, failures,
    )
    probe(
        "a Subject of 'none' passes — caught before a change landed",
        dated_rates() + entries + f"{good_row(1, 'none')}\n",
        False, failures,
    )
    probe(
        "the pre-column marker passes",
        dated_rates() + entries + f"{good_row(1, SUBJECT_LEGACY)}\n",
        False, failures,
    )
    probe(
        "a Subject that is a placeholder is caught",
        dated_rates() + entries + f"{good_row(1, 'n/a')}\n",
        True, failures,
    )
    probe(
        "an empty Subject cell is caught",
        dated_rates() + entries + f"{good_row(1, '')}\n",
        True, failures,
    )

    # The coverage predicate. A predicate that has only ever seen good input has
    # not been shown to reject bad input, so each way the claim can be wrong is
    # probed against the live measurement.
    live_n, live_m = measure_coverage()
    probe(
        "a coverage claim matching the live measurement passes",
        dated_rates() + entries + f"{good_row(1)}\n",
        False, failures,
    )
    probe(
        "a coverage claim with the wrong numerator is caught",
        dated_rates(f"**{live_n + 1} of {live_m}** entries carry a determinate Subject")
        + entries + f"{good_row(1)}\n",
        True, failures,
    )
    probe(
        "a coverage claim with the wrong denominator is caught",
        dated_rates(f"**{live_n} of {live_m + 1}** entries carry a determinate Subject")
        + entries + f"{good_row(1)}\n",
        True, failures,
    )
    probe(
        "a Rates section with no coverage claim at all is caught",
        dated_rates("The coverage is reported in the daily score file.")
        + entries + f"{good_row(1)}\n",
        True, failures,
    )

    # The resolution leg. Its input arrives from the ledger, so its probes supply
    # the closed set themselves: a predicate only ever run against a correct set
    # has not been shown to reject a wrong one.
    resolution_probe(
        "a determinate Subject that closed passes",
        entries + f"{good_row(1, '#31')}\n", {"#31"}, False, 1, failures,
    )
    resolution_probe(
        "a determinate Subject that never closed is caught, and named",
        entries + f"{good_row(1, '#31')}\n", set(), True, 1, failures,
        want_named="#31",
    )
    resolution_probe(
        "a duplicated Subject is one work unit, not two",
        entries + f"{good_row(1, '#42')}\n{good_row(2, '#42')}\n",
        {"#42"}, False, 1, failures,
    )
    resolution_probe(
        "a duplicated dangling Subject is reported once",
        entries + f"{good_row(1, '#42')}\n{good_row(2, '#42')}\n",
        set(), True, 1, failures,
    )
    resolution_probe(
        "a Subject of 'none' and the pre-column marker are not work units",
        entries + f"{good_row(1, SUBJECT_NONE)}\n{good_row(2, SUBJECT_LEGACY)}\n",
        set(), False, 0, failures,
    )
    resolution_probe(
        "a prose cell that mentions a number is not a work-unit reference",
        entries + f"{good_row(1, 'see #42 for the detail')}\n",
        {"#42"}, False, 0, failures,
    )

    # The property that makes a live assertion safe at all: the coverage figure is
    # invariant to the ledger's closed-subject set, which every lane moves when it
    # closes a work unit. If it were not, this gate would go RED on another lane's
    # commit — the false-RED class #41 names, and the reason the *rate* is
    # deliberately NOT gated here.
    empty = audit.parse_rework(REWORK, set())
    populated = audit.parse_rework(REWORK, {"#40", "#50"})
    invariant = (
        empty["subject_coverage_numerator"] == populated["subject_coverage_numerator"]
        and empty["subject_coverage_denominator"]
        == populated["subject_coverage_denominator"]
    )
    print(
        f"  {'PASS' if invariant else 'FAIL'}  the coverage figure does not move "
        f"with the closed-subject set — {live_n} of {live_m}"
    )
    if not invariant:
        failures.append("the coverage figure moves with the closed-subject set")

    # The resolution leg against the LIVE document. This is the one assertion in
    # the gate that reads the ledger, and it reads it through the audit's own
    # parser so the closed set checked here is the same population the change fail
    # rate is computed against — a second reading of the ledger is how the gate
    # and the rate come to disagree about which work units exist.
    if not LEDGER.is_file():
        print(f"  FAIL  the ledger is missing at {LEDGER} — nothing can be resolved")
        failures.append("the ledger is missing, so no determinate Subject can resolve")
    else:
        _, closed_subjects = audit.parse_ledger(LEDGER)
        resolution_problems, examined = subject_resolution_problems(
            entry_rows(section_body(text) or ""), closed_subjects
        )
        print(
            f"  {'PASS' if not resolution_problems else 'FAIL'}  every determinate "
            f"Subject resolves to a closed work unit — {examined} distinct "
            f"subject(s) examined against {len(closed_subjects)} closed"
        )
        for problem in resolution_problems:
            print(f"    - {problem}")
        failures.extend(resolution_problems)

    print()
    if failures:
        print(f"rework gate FAILED: {len(failures)} probe(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("rework gate passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
