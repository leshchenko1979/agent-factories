#!/usr/bin/env python3
"""Gate registry: which files declare themselves gates, and are they actually run?

This module is a PURE predicate over a tree, so a synthetic tree can probe it: a rule
that has only ever seen good input has not been shown to reject bad input.

Two directions, because either one alone leaves a hole
-----------------------------------------------------
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
from pathlib import Path

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

def registered_entries(audit_text: str) -> tuple[list[str], list[str]]:
    """Return (tests/ file names, tool invocation argv) read from the audit's run list."""
    tests_entries: list[str] = []
    tool_entries: list[str] = []
    for match in _APPEND.finditer(audit_text):
        quoted = _QUOTED.findall(match.group("argv"))
        target = next((q for q in quoted if q.startswith(("tests/", "tools/"))), None)
        if target is None:
            continue
        if target.startswith("tests/"):
            tests_entries.append(Path(target).name)
        else:
            tool_entries.append(" ".join(quoted))
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
