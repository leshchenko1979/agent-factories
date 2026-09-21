#!/usr/bin/env python3
"""Gate registry: which files declare themselves gates, and are they actually run?

This module is a PURE predicate over a tree, so a synthetic tree can probe it: a rule
that has only ever seen good input has not been shown to reject bad input.

Five directions, because any one alone leaves a hole
----------------------------------------------------
**declared -> registered.** A file that declares itself a gate must actually be run. An
earlier probe protected only the gate that carried it — a file asserting its own name
appears in `tools/audit.py`. That closes one instance and not the class: a new gate file
is unregistered by default, and `tests/test_gate_fixtures_closure.py` was born
unregistered *during* the very window that probe was written (issue #59).

**registered -> declared.** The reverse. A file the audit RUNS as a gate but which never
says so is invisible to the first direction, which only ever consults files that declare
themselves. Measured live, that cell is not empty: `tests/test_session_bindings.py` is
registered in both audit copies and its opening docstring contains no word "gate" at all,
so a declared->registered-only predicate stays GREEN if it is unregistered tomorrow —
#62's family one level deeper (HQ ruling n=376).

**required -> present.** The two directions above ask whether the gates a tree HAS are
wired up. Neither asks whether the gates it SHOULD have are there at all, and that is the
hole issue #68 measured: `tools/audit.py` registers every gate behind an `is_file()` guard,
so a factory that never adopted a gate file runs a shorter suite and still prints HEALTHY.
A gate that is absent is not a gate that passes, and nothing asserted the difference — the
printed count was the only signal and no gate read it. So a DECLARED manifest names the
gates every bootstrapped factory must carry, and each absent one FAILS naming it. The
manifest is DERIVED from what the template ships (HQ ruling n=432, Part 1): the template is
the artifact every factory inherits, so what it ships every factory must carry. The
coupling leg asserts manifest and template cannot drift — a leg only the meta-factory can
carry, because a bootstrapped factory has no `TEMPLATE/` to compare against.

**law -> registered.** The three directions above read the TREE: what it declares, what the
audit runs, what the template ships. None reads a RECORDED LAW, and a law that names a
mechanism which is not wired up is the same dead text P29 forbids, one step further out.
The sources are the two this factory already keeps: the rework log's `Prevented by` column
(section 11 makes that log a law surface, and its `Prevented by` is the load-bearing column)
and the skill's own sentences. A `tests/test_*.py` either source names must be REGISTERED.
SCOPE BOUND, carried in the predicate: this covers mechanisms a RECORDED LAW names; the
GENERAL case — a test file that should be a gate and is named nowhere — is issue #48,
already open, and this direction must NOT swallow it.

**registered -> CAN RUN.** Every direction above asks WHAT is registered and never HOW.
`registration_entries` reads the append's argv, which carries two facts — the target and
the runner — and the first reader kept only the target and DISCARDED the runner, so a
registration that cannot run its target read exactly like one that runs it (HQ ruling
n=639 Part 2(d)). The consequence is a gate that reports PASS while testing nothing: a
pytest-style target (`def test_*` at module level, no `__main__`) invoked as
`[sys.executable, "tests/X.py"]` runs no test at all and exits 0. Measured live during
#107(a), which is how the class was found:

    python3 tests/test_registry_render.py        → rc=0, 0 bytes of output
    python3 -m pytest tests/test_registry_render.py -q → 29 passed in 0.63s

ONE-WAY BY DESIGN: only a pytest-style target under a script runner is reported. A
script-style target under the pytest runner is collectible, so it is NOT a defect, and
this direction answers one question — can this registration run its target — rather than
classifying shapes, which is direction 1's job and stays declaration-only.

Why LOOSE-then-STRICT rather than a strict match alone
------------------------------------------------------
The obvious predicate — "a file whose docstring opens with Gate" — under-covers, because
a predicate that only recognises the convention cannot see a departure from it. Three live
gates declared themselves differently and were invisible to it:

  tests/test_law_coverage.py   `Tests for Best Practice Law-to-Gate Coverage (P29).`
  tests/test_law_structure.py  `Law structure gate: numbered sections in a law file`
  tests/test_ontology.py       `Vocabulary gate for the agent-factories repo.`

So the predicate runs in two passes, the #62 shape:

  1. LOOSE  — every `tests/test_*.py` whose opening docstring's FIRST line contains the
              word "gate" (case-insensitive). A gate that describes itself in words is
              found whatever form it uses.
  2. STRICT — each of those must ALSO open with the canonical `Gate` form.

Loose finds the file; strict makes a departure LOUD rather than silent.

Registration is an APPEND, not a mention
----------------------------------------
A path sitting only in the surrounding `is_file()` guard is NOT a registration: a guard
whose body appends nothing would otherwise read as registered, and the bite proof found
exactly that hole by un-registering a live gate and watching this gate stay green. So the
predicate reads the argv of each `gates_to_run.append(...)`.

Two scope statements the predicate carries, because it is wrong without them
----------------------------------------------------------------------------
(i)  **A `tests/`-scoped parse does not cover the whole run list.** Three entries are TOOL
     invocations (`tools/ledger.py verify`, `tools/hygiene.py --audit`,
     `tools/roadmap.py --audit`) that no test-file predicate can see. They are counted and
     named in the report so the coverage gap is stated, never implied away.

(ii) **The OPENER is matched, never the whole file.** A whole-file search for "gate" picks
     up `tests/test_review.py` (a comment) and `tests/test_telemetry.py` (a data field) —
     two false positives, neither a gate. Matching the opening docstring's first line is
     what keeps the predicate about declarations.

Shape is deliberately NOT the discriminator. This tree runs both script-style gates
(`def main() -> int` + `__main__`) and pytest-style gates (`def test_*()`), and three
canonical gates have no `def main()`. A shape predicate would under-cover differently.
Only the declaration discriminates.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The rework log's entries table is parsed by ONE module, shared with tests/test_rework.py:
# a second parser is the defect this repo names as "one field, one predicate", and it fails
# SILENTLY — two parsers agree until a cell count or a column order changes, and then one
# returns another column's values under the name it asked for. Imported, never re-derived.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rework_table as rt  # noqa: E402 — the path above is set deliberately before this line

# The canonical declaration: the opening docstring's first line begins with this.
CANONICAL_OPENER = "Gate"

# The loose declaration: the opening docstring's first line contains this word.
DECLARATION_WORD = "gate"

# A test file's opening docstring first line, allowing a shebang, a leading space, and any
# legal string prefix. The prefix is not cosmetic: `r"""` is required whenever the docstring
# quotes a regex, and a parser demanding a bare `"""` reads such a file as having NO
# docstring at all — which is exactly how tests/test_law_coverage.py stopped declaring
# itself the moment #62 gave it an r-prefixed opener. A missed declaration is not a
# near-miss: the file is neither declared nor non-canonical, it is INVISIBLE, and the
# reverse direction then reports it as a registered gate that stays silent.
_OPENING = re.compile(r'^\s*(?:#!.*\n)?\s*(?:[rR][bB]?|[bB][rR]?|[uU])?"""(?P<first>[^\n]*)')

# Every append in the audit is a single line with no nested parenthesis, so the argv is
# taken to the first `)`.
_APPEND = re.compile(r"gates_to_run\.append\((?P<argv>[^)]*)\)")
_QUOTED = re.compile(r'"([^"]+)"')

PREDICATE = (
    "a tests/test_*.py whose opening docstring's FIRST line contains 'gate' "
    "(case-insensitive) is a declared gate; each must be REGISTERED (its path appears "
    "quoted in a gates_to_run.append(...) in tools/audit.py) and CANONICAL (that first "
    "line starts with 'Gate'). The REVERSE also holds: every tests/ path in the run list "
    "must DECLARE itself, so a gate the audit runs is never silent about being one."
)

TOOL_INVOCATION_NOTE = (
    "a tests/-scoped parse covers the tests/ entries of the run list only; tool "
    "invocations (tools/*.py) are outside any test-file predicate and are named in the "
    "report so the gap is stated"
)

OPENER_ONLY_NOTE = (
    "the OPENER is matched, never the whole file — a whole-file search for 'gate' picks "
    "up a comment and a data field, neither of them a gate"
)

LAW_COVERAGE_PREDICATE = (
    "a tests/test_*.py that a RECORDED LAW names as an upholding mechanism must be "
    "REGISTERED. The law sources are the rework log's `Prevented by` column — section 11 "
    "makes that log a law surface — and the skill's own sentences. A mechanism named and "
    "not registered FAILS, NAMING it. SCOPE BOUND: this covers mechanisms a recorded law "
    "names; the GENERAL case (a test file that should be a gate and is named nowhere) is "
    "#48, already open, and this direction must NOT swallow it. The report PRINTS the "
    "entries parsed, the mechanisms named and the files it read on every run — an "
    "unprinted population is the exempt-by-silence surface ruled at n=571."
)

# A `tests/test_*.py` NAMED as a token. The token form is what makes the scan safe on
# prose: a naive whole-file search for the word "gate" picks up test_review.py and
# test_telemetry.py, but neither file is NAMED as a `test_*.py` in either law source
# (measured 2026-09-19: 11 named in the skill, 29 in the rework log, 0 false positives),
# so no exemption is needed and none is granted.
_FILE_TOKEN = re.compile(r"\btest_[A-Za-z0-9_]+\.py\b")

# The rework log's `Prevented by` column, by the header cell that names it. The exact
# header text: matching is case-insensitive, but the column reader builds its failure
# reason from this string, so the casing is what a reader of that reason sees.
_PREVENTED_BY_HEADER = "Prevented by"

# The two runner forms an append can use, and the two shapes a target can have. The RUNNER
# is read from the append's argv; the SHAPE is read from the target's own text.
PYTEST_RUNNER = "pytest"
SCRIPT_RUNNER = "script"

# A pytest-style target: module-level `def test_*` and NO `__main__` guard.
#
# Shape is read ONLY to answer whether a given registration CAN run its target. It never
# becomes a general shape classifier — the declaration question keeps its own
# declaration-only predicate (direction 1, and the "Shape is deliberately NOT the
# discriminator" note above), and this direction answers one narrower question.
_TEST_FUNC = re.compile(r"^def test_[A-Za-z0-9_]*\(", re.M)
_MAIN_GUARD = re.compile(r"^if __name__ == ['\"]__main__['\"]:", re.M)

RUNNER_FORM_PREDICATE = (
    "a registered gate whose target is pytest-style (module-level `def test_*`, no "
    "`__main__` guard) must be registered under the pytest runner. The runner is read "
    "from the append's argv and the shape from the target's own text; a pytest-style "
    "target invoked as a script runs NOTHING and exits 0, so every `def test_*` in it is "
    "dead. A file carrying BOTH a `def test_*` and a `__main__` guard is therefore "
    "PYTEST-form: runs under either runner is true of the FILE and false of each "
    "RUNNER, and this direction answers the latter. Measured 2026-09-20 (#124): six "
    "registered files carried 99 dead legs between them while the audit printed PASS "
    "for every one. ONE-WAY BY DESIGN: a target carrying NO module-level `def test_*` "
    "under the pytest runner is NOT reported — pytest collects nothing and exits 5, so "
    "that direction is LOUD rather than silent, and this direction answers only whether "
    "a given registration CAN run its target."
)

def first_docstring_line(text: str) -> str | None:
    """The opening docstring's first line, or None when the file has no docstring."""
    match = _OPENING.match(text)
    return match.group("first").strip() if match else None

def reads_a_docstring(text: str) -> bool:
    """True when the file's opening docstring is RECOGNISED at all.

    This is the distinction a prefix bug erases. A file the parser cannot open is not a
    near-miss and not a malformed declaration — it is invisible, so every downstream
    direction is silent about it. #62 put an r-prefix on a live gate and this is what
    went quiet.
    """
    return _OPENING.match(text) is not None

def declared_gates(tests_dir: Path) -> list[tuple[Path, str]]:
    """Every `test_*.py` under `tests_dir` that declares itself a gate (loose pass)."""
    found: list[tuple[Path, str]] = []
    for path in sorted(tests_dir.glob("test_*.py")):
        first = first_docstring_line(path.read_text(encoding="utf-8"))
        if first is not None and DECLARATION_WORD in first.lower():
            found.append((path, first))
    return found

def registration_entries(audit_text: str) -> list[dict]:
    """Every `gates_to_run.append(...)`, with BOTH projections read from ONE scan.

    An append's argv carries two facts: the TARGET it registers and the RUNNER it
    registers it under. `registered_entries` kept only the first and DISCARDED the
    second, so a registration that cannot run its target read exactly like one that runs
    it — the reason direction 4 exists (#107(d), HQ ruling n=639 Part 2). Both
    projections come from this single scan: a second `_APPEND` scan would be the same
    defect one level down.
    """
    entries: list[dict] = []
    for match in _APPEND.finditer(audit_text):
        argv = match.group("argv")
        quoted = _QUOTED.findall(argv)
        target = next((q for q in quoted if q.startswith(("tests/", "tools/"))), None)
        if target is None:
            continue
        entries.append(
            {
                "target": target,
                "name": Path(target).name,
                "kind": "tests" if target.startswith("tests/") else "tool",
                "runner": _runner_of(quoted),
                "argv": " ".join(quoted),
            }
        )
    return entries

def _runner_of(quoted: list[str]) -> str:
    """The runner an append's argv invokes, read from its ARGUMENT STRUCTURE.

    NOT a substring test over the whole argv: a target named `tests/test_pytest_form.py`
    contains the word "pytest" and would be misread as a pytest invocation, hiding a real
    mismatch behind its own filename. Measured — this predicate's own probe caught exactly
    that on its first run. The runner is recognised only by a token that can BE the runner:
    the `-m pytest` pair (the module form this audit uses) or `pytest` as the argv's own
    executable.
    """
    for i, token in enumerate(quoted):
        if token == "pytest" and (i == 0 or quoted[i - 1] == "-m"):
            return PYTEST_RUNNER
    return SCRIPT_RUNNER

def registered_entries(audit_text: str) -> tuple[list[str], list[str]]:
    """Return (tests/ file names, tool invocation argv) read from the audit's run list.

    A PROJECTION of `registration_entries`, never a second parse — one append scan, two
    readers, so the target set and the runner set can never disagree about what the audit
    contains.
    """
    tests_entries: list[str] = []
    tool_entries: list[str] = []
    for entry in registration_entries(audit_text):
        if entry["kind"] == "tests":
            tests_entries.append(entry["name"])
        else:
            tool_entries.append(entry["argv"])
    return tests_entries, tool_entries

def gate_registration_problems(tests_dir: Path, audit_path: Path) -> tuple[list[str], dict]:
    """Return (problems, report) for one tree.

    `report` carries the scan's coverage — modules scanned, both directions' findings, and
    the tool invocations outside the predicate's reach — so a caller states the scan's
    extent rather than only its verdict. A count travels with its predicate, never alone.
    """
    problems: list[str] = []
    audit_text = audit_path.read_text(encoding="utf-8") if audit_path.is_file() else ""
    tests_entries, tool_entries = registered_entries(audit_text)
    registered = set(tests_entries)

    declared = declared_gates(tests_dir)
    declared_names = [p.name for p, _ in declared]

    declared_unregistered: list[str] = []
    registered_undeclared: list[str] = []
    non_canonical: list[str] = []

    # direction 1: declared -> registered, and declared -> canonical
    for path, first in declared:
        if path.name not in registered:
            declared_unregistered.append(path.name)
            problems.append(
                f"tests/{path.name} declares itself a gate but is never registered in "
                f"{audit_path.name} — an unregistered gate never runs (P29)"
            )
        if not first.startswith(CANONICAL_OPENER):
            non_canonical.append(path.name)
            problems.append(
                f"tests/{path.name} declares a gate without the canonical "
                f"'{CANONICAL_OPENER}' opener: {first[:60]!r}"
            )

    # direction 2: registered -> declared
    for name in sorted(registered):
        if name in declared_names or not (tests_dir / name).is_file():
            continue
        registered_undeclared.append(name)
        problems.append(
            f"tests/{name} is run as a gate by {audit_path.name} but does not declare "
            f"itself one — a registered gate that stays silent is invisible to the "
            f"declared->registered direction (P29)"
        )

    report = {
        "modules_scanned": len(list(tests_dir.glob("test_*.py"))),
        "declared": declared_names,
        "registered_tests": sorted(registered),
        "tool_invocations": tool_entries,
        "declared_unregistered": declared_unregistered,
        "registered_undeclared": registered_undeclared,
        "non_canonical": non_canonical,
    }
    return problems, report

# --- direction 3: required -> present ------------------------------------------------

# The DECLARED manifest: the gates every bootstrapped factory must carry.
#
# DERIVED from the template (HQ ruling n=432 Part 1), never hand-invented — the template is
# the artifact every factory inherits, so what it ships every factory must carry, and what
# it does not ship is that factory's own. `manifest_drift_problems` asserts the two cannot
# drift apart, so this list is a transcription that is CHECKED rather than trusted.
#
# Scoped to DECLARED GATES, never raw files. Triage's reconciliation of #68 measured why:
# `TEMPLATE/tests/test_review.py` is a raw file that is NOT a gate — this module's own scope
# statement names it as a false positive, and neither audit copy registers it. A manifest
# defined by file-shipping would demand it, and could then never equal the registered set.
# Part 1's derivation and Part 3's equality leg meet only at the declared-gate grain.
REQUIRED_GATES: tuple[str, ...] = (
    "test_audit_rates.py",
    # Added with its registration (issue #74, ruling n=485). REQUIRED is the correct grain and
    # OPTIONAL is not: the gate is PURE over two paired artifacts — the harness binding's own
    # variable table and the tool that must honour each name in it — so it passes in a
    # bootstrapped factory exactly as it does here, with no box-local fixture and no TEMPLATE
    # comparison to make it red. A factory that dropped the runner while keeping the file would
    # keep a binding that promises an isolation seam nothing proves exists, and the harm that
    # promise prevents is UNRECOVERABLE rather than merely unrecorded: a probe that ignores the
    # seam appends to LIVE state, so the rows it leaves are indistinguishable from real
    # transitions and no later gate can separate them. It is byte-paired with a TEMPLATE twin,
    # so the manifest grain is what keeps a factory from dropping the runner and keeping the file.
    "test_binding_mechanism_exists.py",
    "test_board_intake_recorded.py",
    "test_close_board_recorded.py",
    "test_close_row_revision.py",
    # Added with its registration (issue #130). REQUIRED is the correct grain and OPTIONAL
    # is not, for the same deciding fact as the gate below: its boundary is FORWARD-ONLY.
    # The rule governs close rows written at or after the instant a factory declares, and
    # nothing is ever backfilled, so a factory that ships the gate OPTIONAL and omits it
    # writes its first close row with no provenance and can never repair that — the
    # evidence a later gate would need is the evidence it did not take. The
    # counter-argument, that a factory whose close rows all predate its declaration
    # carries a gate that only ever skips, describes every gate whose population is an
    # event: it skips with a STATED reason, and no boundary key means no declaration
    # rather than a silent pass. It is byte-paired with a TEMPLATE twin, so the manifest
    # grain is what keeps a factory from dropping the runner and keeping the file.
    "test_close_telemetry_provenance.py",
    # Added with its registration (issue #112, ruling n=657; amended under issue #115, ruling
    # n=687). REQUIRED is the correct grain and OPTIONAL is not, and the deciding fact is
    # that its boundary is FORWARD-ONLY: the rule governs rows written at or after the
    # instant a factory declares, and nothing is ever backfilled, so a factory that ships the
    # gate OPTIONAL and omits it writes its first reconstruction ungoverned and can never
    # repair that — the record a later gate would need is the one it did not take. The
    # counter-argument, that a factory which never reconstructs carries a gate that always
    # skips, describes every gate whose population is an event: it skips with a STATED reason
    # and no boundary key means no declaration rather than a silent pass, which is the same
    # shape `test_subject_form.py` and `test_close_row_revision.py` already carry in this
    # tuple. It is also byte-paired with a TEMPLATE twin, so the manifest grain is what keeps
    # a factory from dropping the runner and keeping the file (the `test_registry_render.py`
    # reasoning above). RENAMED from `test_claim_gap_declared.py` by #115: the gate no longer
    # judges the `claim_gap` token, so the old name described a predicate it no longer
    # implements — a name that lies about its predicate is worse than a rename.
    "test_reconstructed_claim_declared.py",
    "test_commit_pair_hook.py",
    "test_commit_pathspec_law.py",
    "test_criteria_count.py",
    # Added with its registration (issue #54, P7 + P28). REQUIRED is the correct grain and
    # OPTIONAL is not: the predicate is PURE over a LIST of cron rows and reads no live
    # table, so it passes in a bootstrapped factory exactly as it does here — there is no
    # `TEMPLATE` comparison or box-local fixture that would make it red. It is byte-paired
    # with a TEMPLATE twin, so the manifest grain is what keeps a factory from dropping the
    # runner and keeping the file.
    "test_cron_thinness.py",
    "test_docs_sync.py",
    "test_duplicate_prose.py",
    "test_gate_fixtures_closure.py",
    "test_gate_registration.py",
    "test_hq_delegation.py",
    "test_hygiene_inflight.py",
    "test_hygiene_namespace.py",
    # Added with its registration (issue #46). REQUIRED is the correct grain and OPTIONAL
    # is not, and the deciding fact is the same one that put the score-run twin
    # (`test_score_gate_recorded.py`) in this tuple: its boundary is FORWARD-ONLY. The rule
    # governs rows written at or after the instant a factory declares, nothing is ever
    # backfilled, and a ledger row is immutable — so a factory that ships the gate OPTIONAL
    # and omits it writes its next synthesis run ungoverned and can never repair that,
    # because the record it did not take is the one thing that cannot be reconstructed.
    # It is byte-paired with a TEMPLATE twin, so the manifest grain is what keeps a factory
    # from dropping the runner and keeping the file.
    "test_insights_gate_recorded.py",
    "test_law_structure.py",
    "test_ledger.py",
    "test_ledger_close_preflight.py",
    "test_ledger_commit_cites_no_rows.py",
    "test_ledger_no_shrink.py",
    "test_ledger_schema.py",
    "test_ontology.py",
    "test_patrol_host_state.py",
    "test_rework.py",
    # Added with its registration (issue #110, ruling n=642). REQUIRED is the correct
    # grain and OPTIONAL is not: the declaration it checks rides on the SAME close row
    # the sibling rework gates already govern, so a factory carrying the log and the
    # entry gate but not this one can still declare an entry that never landed — the leg
    # is a property of the close row, never an optional extra. Its population is the
    # whole history, so it loud-fails on an empty read rather than skipping.
    "test_rework_declared_landed.py",
    "test_rework_relative_revision.py",
    "test_registry.py",
    # Added with its registration (issue #107, ruling n=639). It was ALREADY shipped by
    # the template — byte-paired at `tests/test_template_sync.py` — while no runner ran it
    # and no manifest named it, so every factory carried the file and none executed it.
    # REQUIRED is the correct grain and OPTIONAL is not: a manifest that omitted a paired
    # gate would let a factory drop the runner and keep the file.
    "test_registry_render.py",
    "test_roadmap_transition.py",
    "test_score_artifact_sections.py",
    "test_score_gate_recorded.py",
    "test_single_writer.py",
    # Added with its registration (issue #71, ruling n=455 clause 3). REQUIRED is the correct
    # grain and OPTIONAL is not, and the deciding fact is the same one that put
    # `test_reconstructed_claim_declared.py` in this tuple: its boundary is FORWARD-ONLY. The rule
    # governs commits at or after the instant a factory declares, nothing is ever backfilled,
    # and a commit is immutable — so a factory that ships the gate OPTIONAL and omits it
    # writes its next law change ungoverned and can never repair that, because the record a
    # later gate would need is the commit it did not check. The counter-argument, that a
    # factory which keeps its version line honest carries a gate that always skips, describes
    # every gate whose population is an event: it skips with a STATED reason, and a missing
    # boundary key means no declaration rather than a silent pass. It is byte-paired with a
    # TEMPLATE twin, so the manifest grain is what keeps a factory from dropping the runner
    # and keeping the file.
    "test_skill_version_contract.py",
    "test_subject_form.py",
    "test_telemetry_reader_registry.py",
    "test_template_integrity.py",
)

# Gates the template does NOT ship, each with the reason it is not required. Stated rather
# than merely omitted — the discipline `TOOL_INVOCATION_NOTE` already applies, so the
# optional set is PRINTED WITH ITS REASON and an omission is never implied away (Part 4).
#
# `test_close_row_revision.py` and `test_score_gate_recorded.py` were the first two entries
# here, held against n=432 Part 5's propagation order. That order is now EXECUTED: ruled at
# n=515 clause 4 in its DECLARED-factory-parameter form, both files moved into
# REQUIRED_GATES and gained their TEMPLATE twins in one change (issue #78). Nothing is
# held here any more, so every entry below is a settled classification.
#
# `test_registry.py` was held here for the same reason and has now moved the same way: the
# fleet it hardcoded is a DECLARED manifest (`registry/fleet.json`) rather than six dicts in
# the tool, so it passes in a bootstrapped factory that has declared its own fleet and
# enrolled its own fragment. It moved into REQUIRED_GATES in the change that shipped
# `TEMPLATE/registry/`, which is the condition its own entry named.
OPTIONAL_GATES: dict[str, str] = {
    "test_law_coverage.py": (
        "PARAMETERIZE FIRST (n=432 Part 5) — hardcodes skills/meta-factory/SKILL.md and "
        "would RED in a bootstrapped factory."
    ),
    "test_session_bindings.py": (
        "PARAMETERIZE FIRST (n=432 Part 5) — hardcodes skills/meta-factory/SKILL.md, and "
        "additionally requires >=4 lane rows the template's SKILL.md.tmpl does not carry."
    ),
    "test_synthesize_interface.py": (
        "meta-factory-only (n=432 Part 5) — its subject tool tools/synthesize_insights.py "
        "is live-only and does not ship."
    ),
    "test_template_sync.py": (
        "meta-factory-only (n=432 Part 5), self-documented — a copy of a pair-guard would "
        "need its own pair-guard."
    ),
}

REQUIRED_PREDICATE = (
    "every gate in REQUIRED_GATES — the manifest derived from what the template ships as a "
    "declared gate — must be PRESENT as a file in the tree, and each absent one FAILS naming "
    "it. The manifest must also EQUAL the template's declared-gate inventory, so the two "
    "cannot drift; that leg is meta-factory-only and skips where no TEMPLATE/ tree exists."
)

def required_gate_problems(
    tests_dir: Path, required: tuple[str, ...] = REQUIRED_GATES
) -> tuple[list[str], dict]:
    """Direction 3: every gate in the manifest must be PRESENT in this tree.

    The audit is fail-soft by construction — it registers a gate only when its file exists,
    so an absent gate is invisible to it and the run reads HEALTHY over a shrunken suite
    (issue #68; measured at /root/inferhub-watch, where 2 gates ran and the verdict was
    still `rc=0 HEALTHY`). This predicate makes the absence LOUD, and it fails NAMING the
    file so the reader does not have to diff two inventories to find it.
    """
    problems: list[str] = []
    present: list[str] = []
    absent: list[str] = []
    for name in required:
        if (tests_dir / name).is_file():
            present.append(name)
        else:
            absent.append(name)
            problems.append(
                f"required gate tests/{name} is ABSENT — the template ships it, so every "
                f"bootstrapped factory must carry it, and an absent gate is not a passing "
                f"gate (P29, issue #68)"
            )
    report = {"required": list(required), "present": present, "absent": absent}
    return problems, report

def manifest_drift_problems(
    template_tests_dir: Path, required: tuple[str, ...] = REQUIRED_GATES
) -> tuple[list[str], dict]:
    """The coupling leg: the manifest must EQUAL the template's declared-gate inventory.

    META-FACTORY ONLY, and SKIPPED rather than failed when there is no template tree to
    compare against — a bootstrapped factory has no `TEMPLATE/`, which is exactly why
    n=432 Part 3 makes this leg the meta-factory's. The TEMPLATE copy of this module
    resolves its own repo root to `TEMPLATE/`, so the path it would look for does not exist
    there and the leg skips itself without special-casing.
    """
    if not template_tests_dir.is_dir():
        return [], {
            "skipped": True,
            "reason": "no TEMPLATE tree — this leg is meta-factory-only (n=432 Part 3)",
            "manifest": sorted(required),
        }
    shipped = sorted(path.name for path, _ in declared_gates(template_tests_dir))
    manifest = sorted(required)
    problems: list[str] = []
    for name in sorted(set(shipped) - set(manifest)):
        problems.append(
            f"the template ships tests/{name} as a declared gate but the manifest omits it "
            f"— every factory inherits it, so derivation makes it required (n=432 Part 1)"
        )
    for name in sorted(set(manifest) - set(shipped)):
        problems.append(
            f"the manifest requires tests/{name} but the template does not ship it as a "
            f"declared gate — a required gate the template omits is unadoptable (P29)"
        )
    report = {
        "skipped": False,
        "manifest": manifest,
        "template_shipped": shipped,
    }
    return problems, report

def optional_gate_lines() -> list[str]:
    """The optional set with its reasons, ready to print (n=432 Part 4)."""
    return [
        f"not required: tests/{name} — {reason}"
        for name, reason in sorted(OPTIONAL_GATES.items())
    ]

def law_named_mechanisms(
    rework_path: Path, skill_path: Path | None
) -> tuple[dict[str, list[str]], dict]:
    """(mechanisms, report) — every `test_*.py` a RECORDED LAW names, with provenance.

    `mechanisms` maps a file NAME to the provenance strings that named it, so a failure
    says WHERE the law named it rather than only that something did. The report states
    what was read and what was skipped: a source silently absent would shrink the
    population without saying so, and an unprinted population is the exempt-by-silence
    surface ruled at n=571.

    The two sources are the rework log's `Prevented by` column — section 11 makes that
    log a law surface, and `Prevented by` is its load-bearing column — and the skill's
    own sentences. The column is read through `rt.column_cells`, so a reordered table
    yields a REPORTED reason rather than another column's values.
    """
    mechanisms: dict[str, list[str]] = {}
    report: dict = {
        "rework_read": False,
        "rework_rows": 0,
        "rework_reason": None,
        "skill_read": False,
        "skill_lines": 0,
    }

    if rework_path.is_file():
        report["rework_read"] = True
        rows, reason = rt.column_cells(
            rework_path.read_text(encoding="utf-8"), "Entries", _PREVENTED_BY_HEADER
        )
        report["rework_rows"] = len(rows)
        report["rework_reason"] = reason
        for n, cell in rows:
            for name in _FILE_TOKEN.findall(cell):
                mechanisms.setdefault(name, []).append(f"rework log, Entries row {n}")

    if skill_path is not None and skill_path.is_file():
        text = skill_path.read_text(encoding="utf-8")
        report["skill_read"] = True
        report["skill_lines"] = len(text.splitlines())
        for n, line in enumerate(text.splitlines(), 1):
            for name in _FILE_TOKEN.findall(line):
                mechanisms.setdefault(name, []).append(f"skill line {n}")

    return mechanisms, report

def law_coverage_problems(
    tests_dir: Path,
    audit_path: Path,
    rework_path: Path,
    skill_path: Path | None = None,
) -> tuple[list[str], dict]:
    """Direction 4: a mechanism a RECORDED LAW names must be REGISTERED.

    The three directions above read the TREE — what it declares, what the audit runs,
    what the template ships. This one reads the LAW, because a law naming a mechanism
    that is not wired up is the dead text P29 forbids, one step further out.

    Two failure legs, reported DISTINCTLY so a reader can tell them apart:

      (a) named, the file exists, and it is not registered in `tools/audit.py` — the
          mechanism the law relies on does not run.
      (b) named and no such file exists under `tests/` — a DEAD REFERENCE: the law cites
          a mechanism this tree does not carry at all.

    SCOPE BOUND, carried in `LAW_COVERAGE_PREDICATE`: this covers mechanisms a recorded
    law NAMES. The GENERAL case — a test file that should be a gate and is named nowhere
    — is #48, already open, and this direction must not swallow it.
    """
    audit_text = audit_path.read_text(encoding="utf-8") if audit_path.is_file() else ""
    tests_entries, _ = registered_entries(audit_text)
    registered = set(tests_entries)

    mechanisms, report = law_named_mechanisms(rework_path, skill_path)

    problems: list[str] = []

    # A law source that EXISTS and cannot be read is not an absent one. Passing here would
    # be the vacuous-green class this repo names: an empty result from an unparsed region
    # is indistinguishable from a region with nothing in it, and only the reason
    # distinguishes them. An ABSENT source is a skip (a bootstrapped factory has no rework
    # log until it writes one) and is reported as "not read", never as a clean read.
    if report["rework_read"] and report["rework_reason"] is not None:
        problems.append(
            "law source unreadable — the rework log is present but its "
            f"`Prevented by` column could not be read: {report['rework_reason']}"
        )

    unregistered: list[str] = []
    dead_reference: list[str] = []
    for name in sorted(mechanisms):
        if name in registered:
            continue
        where = "; ".join(mechanisms[name])
        if (tests_dir / name).is_file():
            unregistered.append(f"{name} — named by {where}")
        else:
            dead_reference.append(f"{name} — named by {where}, no such file under tests/")

    problems += [
        f"law-named mechanism not registered in tools/audit.py: {item}"
        for item in unregistered
    ] + [
        f"law-named mechanism is a dead reference: {item}" for item in dead_reference
    ]

    report.update(
        {
            "audit_read": audit_path.is_file(),
            "registered": len(registered),
            "named": len(mechanisms),
            "unregistered": unregistered,
            "dead_reference": dead_reference,
            "law_sources": [
                f"rework log: {report['rework_rows']} row(s) read, reason={report['rework_reason']}",
                (
                    f"skill: {report['skill_lines']} line(s) read"
                    if report["skill_read"]
                    else "skill: NOT READ"
                ),
            ],
        }
    )
    return problems, report

def target_form(text: str) -> str:
    """'pytest' when the file is pytest-style, else 'script'.

    pytest-style is a module-level `def test_*` with NO `__main__` guard. A file carrying
    NEITHER is script-form by the same rule, and that is deliberate: this predicate
    answers what the registration MUST use, not what the file is, and it does not invent
    a third answer it cannot act on.

    A file carrying BOTH is PYTEST-form (#124). The earlier reading — that a both-file
    "runs under either runner", so flagging it would be a false red — was measured FALSE.
    Under the script runner pytest never collects the file, so its module-level
    `def test_*` legs never execute: six registered files carried 99 such legs, every one
    of them dead, and a script runner exits 0 having run nothing, which is
    indistinguishable from passing.
    """
    if _TEST_FUNC.search(text):
        return PYTEST_RUNNER
    return SCRIPT_RUNNER

def runner_form_problems(tests_dir: Path, audit_path: Path) -> tuple[list[str], dict]:
    """Direction 5: a registration must be able to RUN its target.

    A registration the audit cannot actually run is not a gate. The runner comes from the
    append's argv; the target's shape comes from its own text. When the target is
    pytest-style and the registration is script form, the append invokes the file as a
    script, pytest never collects it, and every `def test_*` inside is DEAD — the file
    exits 0 having run nothing, which is indistinguishable from passing.

    ONE-WAY BY DESIGN, and the reason is the COST ASYMMETRY rather than taste: a both-file
    registered under pytest loses only its `main()` — pytest runs the module-level legs
    and never executes the `__main__` guard — and `main()` in these files is a GENERIC
    runner that calls every `test_*` and prints, which is exactly what pytest does. So
    that direction loses no assertion and is deliberately NOT reported. Script
    registration loses EVERY leg; pytest registration loses a printer.

    The bound is stated so it is not mistaken for coverage: this direction reports the
    SCRIPT-registration direction only. A target carrying NO module-level `def test_*`
    under the pytest runner is not silent either — pytest collects nothing and exits 5.

    A target that is ABSENT is skipped here and named in the report: presence is direction
    3's leg, and a second direction reporting absence would double-report one defect.
    """
    audit_text = audit_path.read_text(encoding="utf-8") if audit_path.is_file() else ""
    entries = registration_entries(audit_text)

    forms: list[str] = []
    mismatches: list[str] = []
    for entry in entries:
        if entry["kind"] != "tests":
            forms.append(f"{entry['argv']} — tool invocation, no target shape to read")
            continue
        path = tests_dir / entry["name"]
        if not path.is_file():
            forms.append(
                f"{entry['argv']} — runner={entry['runner']}, target absent "
                f"(presence is direction 3's leg)"
            )
            continue
        text = path.read_text(encoding="utf-8")
        form = target_form(text)
        forms.append(f"{entry['argv']} — runner={entry['runner']}, target form={form}")
        if form == PYTEST_RUNNER and entry["runner"] == SCRIPT_RUNNER:
            mismatches.append(
                f"{entry['name']} carries module-level `def test_*` but is registered "
                f"as a script ({entry['argv']}) — invoked as a script pytest never "
                f"collects it, so every test leg is DEAD"
            )

    problems = [
        f"runner form cannot run its target: {item}" for item in mismatches
    ]
    report = {
        "audit_read": audit_path.is_file(),
        "registrations": len(entries),
        "forms": forms,
        "mismatches": mismatches,
    }
    return problems, report
