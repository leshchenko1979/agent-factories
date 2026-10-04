#!/usr/bin/env python3
r"""Gate: a `§N` written into a ledger row NAMES the document it cites.

Origin (issue #262), ruled at ledger `n=2246`, dispatched at `n=2247`. The citation
clause (meta-factory SKILL, "Verdicts and claims" -- *"a reference to another document
NAMES that document; a bare section number resolves only inside the file that holds
it"*) had NO POPULATION for this factory's ledger: `tests/test_citation_clause_titles.py`
scans `tools/`, `tests/` and their TEMPLATE twins, and `evidence/ledger.jsonl` is outside
all four. Measured when the item was filed (1863 rows): 96 rows carried a `§N`, 219 such
citations existed, and **149 of them (68%) named no document** -- with the class not
dying (bare share 62-77% by band).

WHY THE LEDGER GETS ITS OWN LEG RATHER THAN AN ENTRY IN THE SHIPPED GATE'S SCOPE_DIRS.
The shipped gate excludes prose for a PROPERTY -- *"docs are prose that may number their
own sections"* -- and a ledger row numbers no sections of its own: every `§N` it carries
is a citation INTO another document. So the ledger sits outside that gate by a DIRECTORY
BOUNDARY, not by the argument that justifies excluding docs. The shipped gate keeps ONE
population and ONE predicate; this leg is separate, and lives with the ledger's own gate
set (`docs/instruments/ledger.md` section 5). The owner's own words (register `q22`,
option 0): *"add a SEPARATE check for ledger rows, living with the ledger own checks.
Leave the check that ships to every factory exactly as it is, but correct its comment."*

THE PREDICATE, and the half that is load-bearing.

* **BARE** -- a `§N` is bare when no document token appears in the `DOC_WINDOW`
  characters BEFORE it. A row numbers no sections of its own, so a bare `§N` in a row can
  only point at ANOTHER document: it cannot resolve inside the ledger, and a reader who
  meets it out of tree has nothing to resolve it against. The harm is measured, not
  theoretical (#184): a brief carrying a bare `§11` reached Miidas HQ asserting *"your law
  §11 prescribes a remedy"* against a document whose section 11 is its Verification law
  and which contains no occurrence of "repair". The window's DIRECTION is the shipped
  gate's: a document name PRECEDES its section (`DOC_ON_LINE.search(line[: m.start()])`
  there), so the house convention is that a citation names its document first. A document
  named only AFTER the number therefore does not satisfy this predicate, and that is
  stated rather than implied.
* **WHAT NAMES A DOCUMENT is the SHIPPED GATE'S OWN CONVENTION**, so the two legs agree
  about what naming means: a markdown token (`([A-Za-z0-9_./-]+\.md)`), which is exactly
  `DOC_ON_LINE` in `tests/test_citation_clause_titles.py`. The house writes its citations
  that way -- `SKILL.md §State`, `docs/measurement-procedure.md §5`, `insights.md §6` --
  and a bare `SKILL §4` does NOT name a document, because "SKILL" is the basename of a
  file every factory carries its OWN copy of and the numbering differs per tree (#184's
  class). A row reference (`n=950`) is not a document either: `n=950 §4` is the dominant
  bare shape in this ledger and stays bare.
* **QUOTING-AWARE**, and this is the load-bearing half. A row's `detail` is free prose
  that QUOTES other documents, so a naive scan flags a QUOTATION as a citation -- the
  class `docs/instruments/ledger.md` section 9.8 ("one field, one predicate") was written
  to prevent, and repeating it in a second reader would be the very defect that clause
  names. The scope is the row's OWN VOICE, and the predicate for that is the SHARED one:
  `field_predicate.own_voice_text`, IMPORTED and never re-implemented. A `§N` inside a
  parenthetical aside is a quotation -- the aside is where a row reports what another
  document or row SAYS -- and a `§N` at parenthetical depth 0 is the row's own citation.
  `own_voice_text` FAILS OPEN on unbalanced parentheses (it returns the detail unchanged),
  so such a row is judged by the unscoped text: the worst outcome is the pre-existing
  over-inclusion, which is visible, rather than a silently dropped citation.

FORWARD-ONLY, from a boundary THIS FACTORY declares. The ledger is append-only and its
rows are immutable once published, so a historical bare citation is a RECORD and not a
repairable defect -- nothing is backfilled. The boundary lives in
`docs/ledger-invariants.json` under this gate's own name and is read through
`tests/ledger_boundary.py`; rows BEFORE it print as `excused:` on every run and are never
folded into a bare "clean", and rows AT OR AFTER it are governed. A tree that has not
declared the boundary SKIPS with a stated reason -- never a silent pass, and never another
factory's date.

WHAT THIS LEG CANNOT DO, stated rather than implied. It cannot catch a WRONG section
number. A row that cites a NAMED document for the wrong section satisfies this predicate
completely -- measured on HQ's own rows `n=1858`/`n=1860`, which cite
`docs/measurement-procedure.md` section 8 for what is that document's section 5 STEP 8.
That variant is a READ DISCIPLINE, not a gate: no gate can know which number was meant.

Run:  python3 -m pytest tests/test_ledger_citation_declared.py -q
      (the script form also works: python3 tests/test_ledger_citation_declared.py)
Exit: 0 clean, fully excused, or skipped-with-reason; non-zero on a governed row carrying
      a bare `§N`, on a probe failure, or on a declaration this tree cannot honour.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    boundary_and_rows,
    module_skip,
    parse_ts,
    population_skip_reason,
    synthetic_tree,
)

REPO = Path(__file__).resolve().parent.parent

# BOTH INVOCATION MODES MUST REACH THE GUARD. The audit invokes this gate in pytest mode
# and pytest never calls `main()`, so a guard there protects only the script-mode run.
# `pytestmark` COLLECTS the tests and skips them (exit 0); a module-level `pytest.skip`
# would exit 5, which the audit reads as a failure (#199, #195).
# STATED SKIP: evidence/ledger.jsonl (BOOTSTRAP-created, step 4b)
_SKIP_REASON = module_skip(REPO)
if _SKIP_REASON:
    pytestmark = pytest.mark.skipif(True, reason=_SKIP_REASON)

# The ONE own-voice predicate, shared with `reconstruction` and every other reader of a
# row's prose (`docs/instruments/ledger.md` section 9.8). Imported by module name so a
# staged throwaway `tools/` resolves it the same way.
sys.path.insert(0, str(REPO / "tools"))
from field_predicate import own_voice_text  # noqa: E402

# The key this gate's boundary is declared under, in the factory's own
# `docs/ledger-invariants.json`. The key is the gate's own name, so the declaration says
# which invariant each date belongs to (#248).
INVARIANT_KEY = "ledger_citation_declared"

# A section NUMBER citation. A `§` followed by a TITLE is a different leg -- the shipped
# gate resolves titles against the law corpus, and the ledger's clause is about numbers.
SECTION_NUMBER = re.compile(r"§\s*\d")

# What NAMES a document: a markdown token, which is `DOC_ON_LINE` in the shipped gate
# (`tests/test_citation_clause_titles.py`) -- ONE convention, both legs, so the two cannot
# disagree about what naming means. A bare `SKILL` is NOT here (a file every factory
# carries its own copy of, with its own numbering), and neither is a row reference
# (`n=950`), which is not a document at all.
DOCUMENT_TOKEN = re.compile(r"([A-Za-z0-9_./-]+\.md)")

# How far before the marker a document name may sit. The measurement that opened #262 used
# this window, so the leg and the finding that ordered it read the same population.
DOC_WINDOW = 70


class Verdict(NamedTuple):
    """One run's outcome. `examined` is the SCAN's population (every own-voice `§N` in the
    ledger), which is what makes a clean verdict non-vacuous; `governed` is the
    sub-population the boundary actually judges."""

    status: str
    reason: str
    problems: list[str]
    excused: list[str]
    governed: int
    examined: int
    boundary_text: str


def own_voice_citations(detail: object) -> int:
    """How many `§N` citations `detail` carries IN THE ROW'S OWN VOICE.

    The scan's population, and the reason a clean run is not a vacuous one: a `§N` inside
    a quotation is excluded here exactly as it is in the predicate below, so the count and
    the verdict are taken over ONE scope.
    """
    return len(SECTION_NUMBER.findall(own_voice_text(str(detail or ""))))


def bare_citations(detail: object) -> list[str]:
    """Every BARE `§N` in one row's own voice, as a label plus a readable snippet.

    The scan runs over the own-voice TEXT itself, never by indexing the raw `detail` with
    own-voice offsets: `own_voice_text` DELETES aside content, so the two strings are not
    the same length and an offset carried between them points at the wrong character.
    """
    own = own_voice_text(str(detail or ""))
    out: list[str] = []
    for m in SECTION_NUMBER.finditer(own):
        before = own[max(0, m.start() - DOC_WINDOW): m.start()]
        if DOCUMENT_TOKEN.search(before):
            continue
        snippet = " ".join(own[max(0, m.start() - 45): m.end() + 35].split())
        out.append(f"`{m.group(0).strip()}` -- ...{snippet}...")
    return out


def evaluate(repo: Path) -> Verdict:
    """The core: judge `repo`'s ledger against `repo`'s declared boundary.

    A row that cannot be DATED cannot be excused by its date either, so it is a problem
    rather than a silent exemption. A real problem always outranks a skip: the population
    guard runs only on an otherwise-clean ledger, so a defect is never hidden behind
    "there was nothing to judge".
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return Verdict("skip", str(exc), [], [], 0, 0, "")
    except GateError as exc:
        return Verdict("fail", "", list(exc.problems), [], 0, 0, "")

    problems: list[str] = []
    excused: list[str] = []
    governed = 0
    examined = 0
    for row in rows:
        detail = row.get("detail")
        examined += own_voice_citations(detail)
        bare = bare_citations(detail)
        number = row.get("n")
        try:
            when = parse_ts(str(row.get("ts", "")))
        except (ValueError, TypeError):
            problems.append(
                f"n={number}: unreadable timestamp {row.get('ts')!r} -- a row that cannot "
                f"be dated cannot be excused by its date either"
            )
            continue
        if when >= boundary:
            governed += 1
            problems.extend(
                f"n={number} ({row.get('event')}): {b} -- a ledger row numbers no "
                f"sections of its own, so this citation names no document and resolves in "
                f"no tree" for b in bare
            )
        elif bare:
            excused.append(
                f"n={number} ({row.get('ts')}): {len(bare)} bare citation(s) -- predates "
                f"the declared boundary ({boundary_text})"
            )

    if problems:
        return Verdict("fail", "", problems, excused, governed, examined, boundary_text)
    if not governed:
        return Verdict(
            "skip",
            population_skip_reason([], boundary_text),
            [],
            excused,
            0,
            examined,
            boundary_text,
        )
    return Verdict("pass", "", [], excused, governed, examined, boundary_text)


def _row(number: int, ts: str, detail: str) -> dict:
    return {
        "n": number,
        "ts": ts,
        "event": "run",
        "actor": "worker",
        "subject": "#1",
        "detail": detail,
    }


# --- the live leg -----------------------------------------------------------------

def test_live_ledger_rows_name_the_document_they_cite() -> None:
    """The population is PRINTED, never asserted: it is a property of the INSTANT.

    A run that examined nothing is visible as `0` citations scanned rather than reading as
    a clean one, and a governed population of zero is a stated skip rather than a pass.
    """
    verdict = evaluate(REPO)
    print(
        f"ledger citation gate: {verdict.examined} own-voice `§N` citation(s) examined in "
        f"the ledger's rows"
    )
    if verdict.boundary_text:
        print(f"  boundary: {INVARIANT_KEY} = {verdict.boundary_text}")
    for line in verdict.excused:
        print(f"  excused: {line}")
    if verdict.status == "skip":
        print(f"  SKIP: {verdict.reason}")
        pytest.skip(verdict.reason)
    if verdict.status == "fail":
        raise AssertionError(
            "ledger rows written at or after the declared boundary must NAME the document "
            "they cite, and a bare `§N` names none:\n  " + "\n  ".join(verdict.problems)
        )
    print(
        f"ledger citation gate: clean -- {verdict.governed} governed row(s) at or after "
        f"the boundary, {verdict.examined} own-voice citation(s) scanned, "
        f"{len(verdict.excused)} pre-boundary row(s) excused, 0 problem(s)"
    )


# --- probes: the predicate, then the tree the gate runs in ------------------------

def test_probe_a_bare_section_number_is_bare() -> None:
    assert len(bare_citations("the clause is §11")) == 1


def test_probe_a_quoted_section_number_is_not_bare() -> None:
    assert bare_citations("the ruling reads (see the note at §11 of the law) and stops") == []


def test_probe_a_named_document_satisfies_the_predicate() -> None:
    assert bare_citations("see docs/instruments/ledger.md §5 for the gate set") == []


def test_probe_a_markdown_basename_names_a_document() -> None:
    assert bare_citations("per SKILL.md §State the writer decides the content") == []


def test_probe_a_bare_law_name_does_not_name_a_document() -> None:
    """`SKILL §4` names no document: every factory carries its OWN `SKILL.md` and its
    numbering differs per tree -- #184's class, which is why the shipped gate's own
    convention is a markdown token."""
    assert len(bare_citations("per SKILL §4 the filer dispatches the intake role")) == 1


def test_probe_a_row_reference_is_not_a_document() -> None:
    """`n=950 §4` is the dominant bare shape in this ledger: a row is not a document."""
    assert len(bare_citations("the duplicate bar in n=950 §4 binds a CLAIMED item")) == 1


def test_probe_a_document_named_only_after_the_number_does_not_satisfy_it() -> None:
    assert len(bare_citations("§11 of skills/meta-factory/SKILL.md is the State section")) == 1


def test_probe_unbalanced_parentheses_fail_open() -> None:
    assert len(bare_citations("the ruling (see §11")) == 1


def test_probe_the_scan_counts_only_the_rows_own_voice() -> None:
    assert own_voice_citations("quoted (at §3) but own §5 here") == 1


def test_probe_the_own_voice_predicate_is_the_shared_one() -> None:
    """§9.8: one field, one predicate. The leg IMPORTS it; it must not re-implement it."""
    import field_predicate

    assert own_voice_text is field_predicate.own_voice_text


def test_probe_a_tree_with_no_ledger_skips_with_a_stated_reason(tmp_path: Path) -> None:
    """`TEMPLATE/evidence/` does not exist -- the ledger is BOOTSTRAP-created."""
    verdict = evaluate(synthetic_tree(tmp_path / "bare"))
    assert verdict.status == "skip", (verdict.status, verdict.reason)
    assert verdict.reason


def test_probe_a_governed_row_carrying_a_bare_number_fails(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-03T00:00:00Z", "cites §5 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.reason)
    assert len(verdict.problems) == 1, verdict.problems


def test_probe_a_governed_row_whose_only_number_is_quoted_passes(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-03T00:00:00Z", "the ruling (which reads §5 of the law) holds")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    assert evaluate(root).status == "pass"


def test_probe_a_pre_boundary_bare_citation_is_excused(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-01T00:00:00Z", "cites §5 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "skip", (verdict.status, verdict.reason)
    assert verdict.problems == []
    assert len(verdict.excused) == 1


def test_probe_an_undeclared_boundary_skips_with_a_stated_reason(tmp_path: Path) -> None:
    root = synthetic_tree(tmp_path / "t", rows=[_row(1, "2026-01-03T00:00:00Z", "cites §5 bare")])
    verdict = evaluate(root)
    assert verdict.status == "skip", (verdict.status, verdict.reason)
    assert verdict.reason


def test_probe_an_unreadable_timestamp_is_a_problem_not_an_excuse(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "not-a-date", "cites §5 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.reason)
    assert len(verdict.problems) == 1, verdict.problems


def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-03T00:00:00Z", "cites §5 bare")],
        declaration="{ not json",
    )
    assert evaluate(root).status == "fail"


def test_probe_a_clean_governed_population_passes_and_counts_it(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[
            _row(1, "2026-01-03T00:00:00Z", "see docs/instruments/ledger.md §5 for the set"),
            _row(2, "2026-01-04T00:00:00Z", "the ruling (quoting §9 of the law) holds"),
        ],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "pass", (verdict.status, verdict.reason, verdict.problems)
    assert verdict.governed == 2, verdict.governed
    # `examined` counts OWN-VOICE citations only, so row 2's parenthetical `§9` is a
    # quotation and is not counted -- the scan and the verdict read one scope.
    assert verdict.examined == 1, verdict.examined


def main() -> int:
    """Script form: the same verdict, with the skip reason on STDOUT rather than in a
    pytest short summary -- so a reader of the run sees WHY nothing was judged."""
    verdict = evaluate(REPO)
    print(
        f"ledger citation gate: {verdict.examined} own-voice `§N` citation(s) examined in "
        f"the ledger's rows"
    )
    if verdict.boundary_text:
        print(f"  boundary: {INVARIANT_KEY} = {verdict.boundary_text}")
    for line in verdict.excused:
        print(f"  excused: {line}")
    if verdict.status == "skip":
        print(f"ledger citation gate: SKIP -- {verdict.reason}")
        return 0
    if verdict.status == "fail":
        print("ledger citation gate FAILED:", file=sys.stderr)
        for line in verdict.problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"ledger citation gate: clean -- {verdict.governed} governed row(s) at or after "
        f"the boundary, {verdict.examined} own-voice citation(s) scanned, "
        f"{len(verdict.excused)} pre-boundary row(s) excused, 0 problem(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
