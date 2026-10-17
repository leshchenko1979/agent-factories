#!/usr/bin/env python3
"""Gate: a `\u00a7N` written into a ledger row NAMES the document it cites.

Origin (issue #262), ruled at ledger `n=2246`, dispatched at `n=2247`. The citation
clause (meta-factory SKILL, "Verdicts and claims" -- *"a reference to another document
NAMES that document; a bare section number resolves only inside the file that holds
it"*) had NO POPULATION for this factory's ledger: `tests/test_citation_clause_titles.py`
scans `tools/`, `tests/` and their TEMPLATE twins, and `evidence/ledger.jsonl` is outside
all four. Measured when the item was filed (1863 rows): 96 rows carried a `\u00a7N`, 219 such
citations existed, and **149 of them (68%) named no document** -- with the class not
dying (bare share 62-77% by band).

WHY THE LEDGER GETS ITS OWN LEG RATHER THAN AN ENTRY IN THE SHIPPED GATE'S SCOPE_DIRS.
The shipped gate excludes prose for a PROPERTY -- *"docs are prose that may number their
own sections"* -- and a ledger row numbers no sections of its own: every `\u00a7N` it carries
is a citation INTO another document. So the ledger sits outside that gate by a DIRECTORY
BOUNDARY, not by the argument that justifies excluding docs. The shipped gate keeps ONE
population and ONE predicate; this leg is separate, and lives with the ledger's own gate
set (`docs/instruments/ledger.md` section 5). The owner's own words (register `q22`,
option 0): *"add a SEPARATE check for ledger rows, living with the ledger own checks.
Leave the check that ships to every factory exactly as it is, but correct its comment."*

THE PREDICATE, and the half that is load-bearing.

* **BARE** -- a `\u00a7N` is bare when no document token appears in the `DOC_WINDOW`
  characters BEFORE it. A row numbers no sections of its own, so a bare `\u00a7N` in a row can
  only point at ANOTHER document: it cannot resolve inside the ledger, and a reader who
  meets it out of tree has nothing to resolve it against. The harm is measured, not
  theoretical (#184): a brief carrying a bare `\u00a711` reached Miidas HQ asserting *"your law
  \u00a711 prescribes a remedy"* against a document whose section 11 is its Verification law
  and which contains no occurrence of "repair". The window's DIRECTION is the shipped
  gate's: a document name PRECEDES its section (`DOC_ON_LINE.search(line[: m.start()])`
  there), so the house convention is that a citation names its document first. A document
  named only AFTER the number therefore does not satisfy this predicate, and that is
  stated rather than implied.
* **WHAT NAMES A DOCUMENT is the SHIPPED GATE'S OWN CONVENTION**, so the two legs agree
  about what naming means: a markdown token (`([A-Za-z0-9_./-]+\\.md)`), which is exactly
  `DOC_ON_LINE` in `tests/test_citation_clause_titles.py`. The house writes its citations
  that way -- `SKILL.md \u00a7State`, `docs/measurement-procedure.md \u00a75`, `insights.md \u00a76` --
  and a bare `SKILL \u00a74` does NOT name a document, because "SKILL" is the basename of a
  file every factory carries its OWN copy of and the numbering differs per tree (#184's
  class). A row reference (`n=950`) is not a document either: `n=950 \u00a74` is the dominant
  bare shape in this ledger and stays bare.
* **QUOTING-AWARE**, and this is the load-bearing half. A row's `detail` is free prose
  that QUOTES other documents, so a naive scan flags a QUOTATION as a citation -- the
  class `docs/instruments/ledger.md` section 9.8 ("one field, one predicate") was written
  to prevent, and repeating it in a second reader would be the very defect that clause
  names. The scope is the row's OWN VOICE, and the predicate for that is the SHARED one:
  `field_predicate.own_voice_text`, IMPORTED and never re-implemented. A `\u00a7N` inside a
  parenthetical aside is a quotation -- the aside is where a row reports what another
  document or row SAYS -- and a `\u00a7N` at parenthetical depth 0 is the row's own citation.
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
      a bare `\u00a7N`, on a probe failure, or on a declaration this tree cannot honour.
"""
from __future__ import annotations

import json
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

# THE POST-BOUNDARY EXIT (#317). Forward-only means a bare `\u00a7N` written after the boundary
# has an EMPTY REPAIR SPACE: the row is immutable once published, and `ledger.py repair
# --append-detail` inserts BEFORE the canonical trailer, i.e. after the citation, so the
# bare number survives every lawful repair. `docs/instruments/ledger.md` section 9.6 names
# the remedy for exactly this shape -- *excusing is what the exemption surfaces do for a
# violation whose repair space is empty* -- and this gate shipped without one while eight
# sibling ledger gates declared theirs. The surface is FACTORY DATA read by the gate, never
# a list inside it: this file is paired byte-identically with its TEMPLATE twin, and a
# factory's own rows must not live in a file that ships to every new factory. Ruling
# n=2310 parked the shape; ledger rows n=3355 released it as SHAPE A, an allow-list naming
# its exact rows.
EXEMPTIONS_PATH = "docs/ledger-citation-exemptions.json"

# A section NUMBER citation. The section sign followed by a TITLE is a different leg --
# the shipped gate resolves titles against the law corpus, and the ledger's clause is
# about numbers.
SECTION_NUMBER = re.compile("\u00a7" + r"\s*\d")

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
    """One run's outcome. `examined` is the SCAN's population (every own-voice `\u00a7N` in the
    ledger), which is what makes a clean verdict non-vacuous; `governed` is the
    sub-population the boundary actually judges."""

    status: str
    reason: str
    problems: list[str]
    excused: list[str]
    governed: int
    examined: int
    boundary_text: str
    # `declared` is the count of POST-BOUNDARY rows the exemption store actually excused, so
    # the population line can never read "clean" over an excused row: 0 and 3 are different
    # outputs, printed every run.
    declared: int = 0

def load_exemptions(repo: Path) -> tuple[dict[int, dict], list[str]]:
    """`({row_number: entry}, problems)` read from the factory's own data file.

    Absent or empty data means NO exemptions -- the shipped state of a new factory, where
    `docs/` carries only the `.example.json` skeleton. Anything malformed is a problem,
    never a silent pass: an exemption list that quietly fails to load is indistinguishable
    from no exemptions at all, which is the same vacuous-pass shape the boundary guard
    exists to forbid.

    Each entry must name a row and carry a reason. The PROOF obligation is not checked
    here but in `evaluate`: an entry that names a row carrying no bare citation excuses
    nothing, so it is a STALE exemption and a gate ERROR. That is what keeps the store
    from becoming a standing waiver list -- it can only ever hold rows that are actually
    red.
    """
    problems: list[str] = []
    path = repo / EXEMPTIONS_PATH
    if not path.is_file():
        return {}, problems
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"{path.name} is not JSON: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{path.name}: expected a JSON object with an 'exemptions' list"]
    raw = data.get("exemptions", [])
    if not isinstance(raw, list):
        return {}, [f"{path.name}: 'exemptions' must be a list"]

    entries: dict[int, dict] = {}
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            problems.append(f"{path.name}: entry {i} is not an object")
            continue
        row = item.get("row")
        if not isinstance(row, int) or isinstance(row, bool) or row < 1:
            problems.append(
                f"{path.name}: entry {i} names a row that is not a positive integer: {row!r}"
            )
            continue
        if not str(item.get("reason") or "").strip():
            problems.append(f"{path.name}: entry {i} (n={row}) carries no reason")
            continue
        if row in entries:
            problems.append(f"{path.name}: entry {i} repeats n={row}")
            continue
        entries[row] = item
    return entries, problems


def own_voice_citations(detail: object) -> int:
    """How many `\u00a7N` citations `detail` carries IN THE ROW'S OWN VOICE.

    The scan's population, and the reason a clean run is not a vacuous one: a `\u00a7N` inside
    a quotation is excluded here exactly as it is in the predicate below, so the count and
    the verdict are taken over ONE scope.
    """
    return len(SECTION_NUMBER.findall(own_voice_text(str(detail or ""))))


def bare_citations(detail: object) -> list[str]:
    """Every BARE `\u00a7N` in one row's own voice, as a label plus a readable snippet.

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

    A governed row carrying a bare citation is excused ONLY by a declared entry naming its
    exact row number, and every such excuse is PRINTED with its reason on every run -- the
    gate reports what it let through, never a bare "clean". An entry that matches no
    governed row carrying a bare citation is a STALE exemption and a problem: it inflates
    visible debt while excusing nothing, and it would let the store rot into a standing
    waiver list.
    """
    try:
        boundary, boundary_text, rows = boundary_and_rows(repo, INVARIANT_KEY)
    except SkipGate as exc:
        return Verdict("skip", str(exc), [], [], 0, 0, "")
    except GateError as exc:
        return Verdict("fail", "", list(exc.problems), [], 0, 0, "")

    exemptions, problems = load_exemptions(repo)
    excused: list[str] = []
    matched: set[int] = set()
    governed = 0
    examined = 0
    declared = 0
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
            if not bare:
                continue
            entry = exemptions.get(number) if isinstance(number, int) else None
            if entry is None:
                problems.extend(
                    f"n={number} ({row.get('event')}): {b} -- a ledger row numbers no "
                    f"sections of its own, so this citation names no document and resolves "
                    f"in no tree" for b in bare
                )
                continue
            matched.add(number)
            declared += 1
            excused.append(
                f"n={number} ({row.get('ts')}): {len(bare)} bare citation(s) EXCUSED by "
                f"{EXEMPTIONS_PATH} -- {entry.get('reason')}"
            )
        elif bare:
            excused.append(
                f"n={number} ({row.get('ts')}): {len(bare)} bare citation(s) -- predates "
                f"the declared boundary ({boundary_text})"
            )

    for stale in sorted(set(exemptions) - matched):
        problems.append(
            f"{EXEMPTIONS_PATH}: the exemption for n={stale} matches no governed row "
            f"carrying a bare citation -- a stale exemption excuses nothing and must be "
            f"removed (the row was repaired, or was never red)"
        )

    if problems:
        return Verdict(
            "fail", "", problems, excused, governed, examined, boundary_text, declared
        )
    if not governed:
        return Verdict(
            "skip",
            population_skip_reason([], boundary_text),
            [],
            excused,
            0,
            examined,
            boundary_text,
            declared,
        )
    return Verdict(
        "pass", "", [], excused, governed, examined, boundary_text, declared
    )


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
        f"ledger citation gate: {verdict.examined} own-voice `\u00a7N` citation(s) examined in "
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
            "they cite, and a bare `\u00a7N` names none:\n  " + "\n  ".join(verdict.problems)
        )
    print(
        f"ledger citation gate: clean -- {verdict.governed} governed row(s) at or after "
        f"the boundary, {verdict.examined} own-voice citation(s) scanned, "
        f"{verdict.declared} declared-exempt row(s), 0 problem(s)"
    )


# --- probes: the predicate, then the tree the gate runs in ------------------------

def test_probe_a_bare_section_number_is_bare() -> None:
    assert len(bare_citations("the clause is \u00a711")) == 1


def test_probe_a_quoted_section_number_is_not_bare() -> None:
    assert bare_citations("the ruling reads (see the note at \u00a711 of the law) and stops") == []


def test_probe_a_named_document_satisfies_the_predicate() -> None:
    assert bare_citations("see docs/instruments/ledger.md \u00a75 for the gate set") == []


def test_probe_a_markdown_basename_names_a_document() -> None:
    assert bare_citations("per SKILL.md \u00a7State the writer decides the content") == []


def test_probe_a_bare_law_name_does_not_name_a_document() -> None:
    """`SKILL \u00a74` names no document: every factory carries its OWN `SKILL.md` and its
    numbering differs per tree -- #184's class, which is why the shipped gate's own
    convention is a markdown token."""
    assert len(bare_citations("per SKILL \u00a74 the filer dispatches the intake role")) == 1


def test_probe_a_row_reference_is_not_a_document() -> None:
    """`n=950 \u00a74` is the dominant bare shape in this ledger: a row is not a document."""
    assert len(bare_citations("the duplicate bar in n=950 \u00a74 binds a CLAIMED item")) == 1


def test_probe_a_document_named_only_after_the_number_does_not_satisfy_it() -> None:
    assert len(bare_citations("\u00a711 of skills/meta-factory/SKILL.md is the State section")) == 1


def test_probe_unbalanced_parentheses_fail_open() -> None:
    assert len(bare_citations("the ruling (see \u00a711")) == 1


def test_probe_the_scan_counts_only_the_rows_own_voice() -> None:
    assert own_voice_citations("quoted (at \u00a73) but own \u00a75 here") == 1


def test_probe_the_own_voice_predicate_is_the_shared_one() -> None:
    """\u00a79.8: one field, one predicate. The leg IMPORTS it; it must not re-implement it."""
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
        rows=[_row(1, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.reason)
    assert len(verdict.problems) == 1, verdict.problems


def test_probe_a_governed_row_whose_only_number_is_quoted_passes(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-03T00:00:00Z", "the ruling (which reads \u00a75 of the law) holds")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    assert evaluate(root).status == "pass"


def test_probe_a_pre_boundary_bare_citation_is_excused(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-01T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "skip", (verdict.status, verdict.reason)
    assert verdict.problems == []
    assert len(verdict.excused) == 1


def test_probe_an_undeclared_boundary_skips_with_a_stated_reason(tmp_path: Path) -> None:
    root = synthetic_tree(tmp_path / "t", rows=[_row(1, "2026-01-03T00:00:00Z", "cites \u00a75 bare")])
    verdict = evaluate(root)
    assert verdict.status == "skip", (verdict.status, verdict.reason)
    assert verdict.reason


def test_probe_an_unreadable_timestamp_is_a_problem_not_an_excuse(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "not-a-date", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.reason)
    assert len(verdict.problems) == 1, verdict.problems


def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        declaration="{ not json",
    )
    assert evaluate(root).status == "fail"


def test_probe_a_clean_governed_population_passes_and_counts_it(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[
            _row(1, "2026-01-03T00:00:00Z", "see docs/instruments/ledger.md \u00a75 for the set"),
            _row(2, "2026-01-04T00:00:00Z", "the ruling (quoting \u00a79 of the law) holds"),
        ],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "pass", (verdict.status, verdict.reason, verdict.problems)
    assert verdict.governed == 2, verdict.governed
    # `examined` counts OWN-VOICE citations only, so row 2's parenthetical number is
    # a quotation and is not counted -- the scan and the verdict read one scope.
    assert verdict.examined == 1, verdict.examined


def _write_exemptions(root: Path, payload: object) -> None:
    """Write this gate's exemption store into a synthetic tree, verbatim."""
    (root / "docs").mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (root / "docs" / "ledger-citation-exemptions.json").write_text(text, encoding="utf-8")

def test_probe_a_declared_exemption_excuses_a_governed_row_and_prints_its_reason(
    tmp_path: Path,
) -> None:
    """The surface exists so a post-boundary bare citation stops being a permanent red.

    The row must NOT be silent: `clean` and `excused` are different outputs, and the reason
    is printed on every run, so an exemption can never hide behind a green verdict.
    """
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(7, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    _write_exemptions(root, {"exemptions": [{"row": 7, "reason": "pushed before the gate had a surface"}]})
    verdict = evaluate(root)
    assert verdict.status == "pass", (verdict.status, verdict.problems)
    assert verdict.problems == [], verdict.problems
    assert verdict.declared == 1, verdict.declared
    assert len(verdict.excused) == 1, verdict.excused
    assert "pushed before the gate had a surface" in verdict.excused[0], verdict.excused

def test_probe_the_exemption_does_not_swallow_an_undeclared_governed_row(
    tmp_path: Path,
) -> None:
    """THE CONTROL THAT BITES: with the store in place, a row it does NOT name still fails.

    An exemption surface that excused everything would pass every other probe in this file
    while testing nothing -- the failure class `docs/instruments/ledger.md` section 9.6
    names when it says an exemption is a visible debt, not forgiveness.
    """
    root = synthetic_tree(
        tmp_path / "t",
        rows=[
            _row(7, "2026-01-03T00:00:00Z", "cites \u00a75 bare"),
            _row(8, "2026-01-04T00:00:00Z", "cites \u00a76 bare"),
        ],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    _write_exemptions(root, {"exemptions": [{"row": 7, "reason": "declared debt"}]})
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.excused)
    assert len(verdict.problems) == 1, verdict.problems
    assert "n=8" in verdict.problems[0], verdict.problems
    assert verdict.declared == 1, verdict.declared

def test_probe_a_stale_exemption_is_an_error(tmp_path: Path) -> None:
    """An entry naming a row that carries NO bare citation excuses nothing.

    Without this arm the store rots into a standing waiver list: an entry outlives the
    defect it named and still reads as admitted debt.
    """
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(7, "2026-01-03T00:00:00Z", "see docs/instruments/ledger.md \u00a75")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    _write_exemptions(root, {"exemptions": [{"row": 7, "reason": "no longer red"}]})
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.problems)
    assert any("stale exemption" in p for p in verdict.problems), verdict.problems
    assert verdict.declared == 0, verdict.declared

def test_probe_an_exemption_for_a_row_that_does_not_exist_is_stale(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(7, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    _write_exemptions(
        root,
        {"exemptions": [{"row": 7, "reason": "real"}, {"row": 999, "reason": "a typo"}]},
    )
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.problems)
    assert any("n=999" in p and "stale exemption" in p for p in verdict.problems), verdict.problems

def test_probe_an_absent_store_is_the_shipped_state_not_a_failure(tmp_path: Path) -> None:
    """A new factory ships only the `.example.json` skeleton, so absence must be clean."""
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    verdict = evaluate(root)
    assert verdict.status == "fail", verdict.status
    assert verdict.declared == 0
    assert all("stale exemption" not in p for p in verdict.problems), verdict.problems

def test_probe_a_malformed_store_fails_closed(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(1, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    _write_exemptions(root, "{ not json")
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.problems)
    assert any("not JSON" in p for p in verdict.problems), verdict.problems

def test_probe_a_store_entry_without_a_reason_is_an_error(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(7, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    _write_exemptions(root, {"exemptions": [{"row": 7}]})
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.problems)
    assert any("carries no reason" in p for p in verdict.problems), verdict.problems

def test_probe_a_duplicated_store_entry_is_an_error(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(7, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    _write_exemptions(
        root, {"exemptions": [{"row": 7, "reason": "a"}, {"row": 7, "reason": "b"}]}
    )
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.problems)
    assert any("repeats n=7" in p for p in verdict.problems), verdict.problems

def test_probe_a_non_integer_row_is_an_error(tmp_path: Path) -> None:
    root = synthetic_tree(
        tmp_path / "t",
        rows=[_row(7, "2026-01-03T00:00:00Z", "cites \u00a75 bare")],
        invariants={INVARIANT_KEY: "2026-01-02T00:00:00Z"},
    )
    _write_exemptions(root, {"exemptions": [{"row": "7", "reason": "a string is not a row"}]})
    verdict = evaluate(root)
    assert verdict.status == "fail", (verdict.status, verdict.problems)
    assert any("not a positive integer" in p for p in verdict.problems), verdict.problems

def main() -> int:
    """Script form: the same verdict, with the skip reason on STDOUT rather than in a
    pytest short summary -- so a reader of the run sees WHY nothing was judged."""
    verdict = evaluate(REPO)
    print(
        f"ledger citation gate: {verdict.examined} own-voice `\u00a7N` citation(s) examined in "
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
        f"{verdict.declared} declared-exempt row(s), 0 problem(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
