#!/usr/bin/env python3
"""Gate: every gate in this tree is REGISTERED in the audit, and every one of them DECLARES itself.

Predicate, stated with its count in this gate's own output (see `gate_registry.PREDICATE`):
a `tests/test_*.py` whose opening docstring's FIRST line contains the word "gate"
(case-insensitive) is a declared gate; each must be REGISTERED — its path appears quoted
inside a `gates_to_run.append(...)` in `tools/audit.py` — and CANONICAL — that first line
starts with `Gate`. The REVERSE also holds: every `tests/` path in the run list must
DECLARE itself.

Why the law exists (issue #59). `tests/test_ledger.py` is a gate by its own declaration,
is paired byte-identically into TEMPLATE, and is cited by law as the PROOF of the
single-writer property — yet nothing registered it, so its probes, including the
append-guard probes, ran nowhere while the audit printed HEALTHY over them. A gate that
never runs is indistinguishable from a gate that passes.

The window that produced this file is the argument for it. A local probe asserting the
carrier's own name appears in the audit landed first, and it closes exactly one file:
`tests/test_gate_fixtures_closure.py` was born unregistered *during* that same window.
A new gate file is unregistered by default, so the class needs a scan, not a self-check.

Why BOTH directions (HQ ruling n=376). The declared->registered direction only ever
consults files that declare themselves, so a file the audit RUNS but which never says so
is invisible to it — and that cell is not empty: `tests/test_session_bindings.py` is
registered in both audit copies with no word "gate" anywhere in its opening docstring.
Either direction alone leaves a hole.

Two scope statements this gate carries, because its report is wrong without them:

  (i)  A `tests/`-scoped parse does not cover the whole run list. Three entries are TOOL
       invocations that no test-file predicate can see; they are counted and named, so the
       gap is stated rather than implied away.
  (ii) The OPENER is matched, never the whole file. A whole-file search for "gate" picks
       up a comment in `tests/test_review.py` and a data field in `tests/test_telemetry.py`
       — two false positives, neither a gate.

Run:  python3 tests/test_gate_registration.py
Exit: 0 clean, non-zero on any gate that is unregistered, non-canonical, or silent.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_registry import (  # noqa: E402
    OPENER_ONLY_NOTE,
    PREDICATE,
    TOOL_INVOCATION_NOTE,
    declared_gates,
    first_docstring_line,
    gate_registration_problems,
    reads_a_docstring,
)

TESTS_DIR = REPO / "tests"
AUDIT = REPO / "tools" / "audit.py"

failures: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)

def _synthetic_tree(root: Path, files: dict[str, str], audit: str) -> tuple[Path, Path]:
    """Build a throwaway tests/ tree plus an audit file; return (tests_dir, audit_path)."""
    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (tests / name).write_text(body, encoding="utf-8")
    audit_path = root / "audit.py"
    audit_path.write_text(audit, encoding="utf-8")
    return tests, audit_path

def _register(*names: str) -> str:
    return "".join(f'gates_to_run.append([sys.executable, "tests/{n}"])\n' for n in names)

CANONICAL_GATE = '#!/usr/bin/env python3\n"""Gate: a synthetic gate.\n\nBody.\n"""\n'

# --- synthetic probes: the predicate must reject bad input ------------------------

def probe_an_unregistered_gate_is_named() -> None:
    """Direction 1: declared but never run."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(Path(tmp), {"test_orphan.py": CANONICAL_GATE},
                                       "# an audit that registers nothing\n")
        problems, report = gate_registration_problems(tests, audit)
        check("direction 1 — an unregistered gate is NAMED",
              any("test_orphan.py" in p for p in problems),
              problems[0][:70] if problems else "no problem reported")
        check("direction 1 — the report names it too",
              report["declared_unregistered"] == ["test_orphan.py"],
              str(report["declared_unregistered"]))

def probe_a_silent_registered_gate_is_named() -> None:
    """Direction 2: run by the audit but never declaring itself."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp),
            {"test_silent.py": '#!/usr/bin/env python3\n"""Tests for arithmetic.\n\nBody.\n"""\n'},
            _register("test_silent.py"),
        )
        problems, report = gate_registration_problems(tests, audit)
        check("direction 2 — a registered gate that stays silent is NAMED",
              any("test_silent.py" in p for p in problems),
              problems[0][:70] if problems else "no problem reported")
        check("direction 2 — the report names it too",
              report["registered_undeclared"] == ["test_silent.py"],
              str(report["registered_undeclared"]))

def probe_the_body_is_not_searched() -> None:
    """Scope (ii): a 'gate' in the BODY is not a declaration — the opener is what counts."""
    with tempfile.TemporaryDirectory() as tmp:
        body_only = (
            '#!/usr/bin/env python3\n"""Tests for arithmetic.\n\n'
            '# this file is a gate for the arithmetic law\n"""\n'
        )
        tests, audit = _synthetic_tree(Path(tmp), {"test_bodyonly.py": body_only},
                                       _register("test_bodyonly.py"))
        problems, report = gate_registration_problems(tests, audit)
        check("scope (ii) — a body-only 'gate' does not count as a declaration",
              report["registered_undeclared"] == ["test_bodyonly.py"],
              str(report["registered_undeclared"]))
        check("scope (ii) — and it is reported as a problem",
              any("test_bodyonly.py" in p for p in problems), str(problems[:1]))

def probe_a_non_canonical_declaration_is_named() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp),
            {"test_loose.py": '#!/usr/bin/env python3\n"""Vocabulary gate for a repo.\n\n"""\n'},
            _register("test_loose.py"),
        )
        problems, report = gate_registration_problems(tests, audit)
        check("a non-canonical opener is NAMED, not silently skipped",
              any("canonical" in p for p in problems),
              problems[0][:70] if problems else "no problem reported")
        check("the non-canonical gate is reported as such",
              report["non_canonical"] == ["test_loose.py"], str(report["non_canonical"]))

def probe_a_registered_canonical_gate_is_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(Path(tmp), {"test_ok.py": CANONICAL_GATE},
                                       _register("test_ok.py"))
        problems, report = gate_registration_problems(tests, audit)
        check("a registered, canonical gate raises no problem", problems == [],
              "; ".join(problems)[:70])
        check("and the report shows both directions satisfied",
              report["declared"] == ["test_ok.py"] and report["registered_undeclared"] == [],
              f"declared={report['declared']} undeclared={report['registered_undeclared']}")

def probe_a_non_gate_file_is_not_inspected() -> None:
    """The loose pass must not swallow every test file — only the declared gates."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp),
            {"test_plain.py": '#!/usr/bin/env python3\n"""Tests for arithmetic.\n\n"""\n'},
            "# an audit that registers nothing\n",
        )
        problems, report = gate_registration_problems(tests, audit)
        check("a file that declares no gate and is not run raises nothing",
              problems == [] and report["declared"] == [] and report["registered_tests"] == [],
              f"problems={problems} declared={report['declared']}")

def probe_a_quoted_registration_is_required() -> None:
    """A bare mention is not a registration — the path must appear in an APPEND."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp), {"test_mentioned.py": CANONICAL_GATE},
            '# see tests/test_mentioned.py for the discussion\n'
            'if (repo_root / "tests/test_mentioned.py").is_file():\n    pass\n',
        )
        problems, _ = gate_registration_problems(tests, audit)
        check("a guard that appends nothing is not a registration",
              any("test_mentioned.py" in p for p in problems),
              "; ".join(problems)[:70])

# --- live probes ------------------------------------------------------------------

def probe_the_live_tree_is_clean() -> None:
    problems, report = gate_registration_problems(TESTS_DIR, AUDIT)
    for problem in problems:
        print(f"    {problem}")
    print(
        f"  predicate: {PREDICATE}\n"
        f"  scope (i): {TOOL_INVOCATION_NOTE}\n"
        f"  scope (ii): {OPENER_ONLY_NOTE}\n"
        f"  examined {report['modules_scanned']} module(s); "
        f"{len(report['declared'])} declared a gate, "
        f"{len(report['registered_tests'])} tests/ paths are in the run list, "
        f"{len(report['tool_invocations'])} run-list entr(ies) are tool invocations "
        f"({', '.join(report['tool_invocations'])}) — "
        f"declared-but-unregistered: {len(report['declared_unregistered'])}, "
        f"registered-but-undeclared: {len(report['registered_undeclared'])}, "
        f"non-canonical: {len(report['non_canonical'])}, "
        f"{len(problems)} problem(s)"
    )
    check("every declared gate is registered, and every registered gate declares itself",
          not problems, "; ".join(problems)[:90])

def probe_the_scan_is_not_vacuous() -> None:
    _, report = gate_registration_problems(TESTS_DIR, AUDIT)
    check("the live scan finds gates to check", len(report["declared"]) >= 20,
          f"{len(report['declared'])} declared gate(s)")
    check("the reverse direction finds registered gates to check",
          len(report["registered_tests"]) >= 20,
          f"{len(report['registered_tests'])} registered tests/ path(s)")

def probe_the_report_states_the_tool_gap() -> None:
    """Scope (i): the run list's tool invocations are named, so the gap is not implied."""
    _, report = gate_registration_problems(TESTS_DIR, AUDIT)
    tools = report["tool_invocations"]
    check("scope (i) — the tool invocations are counted and named",
          len(tools) == 3, f"{len(tools)}: {tools}")
    check("scope (i) — the scope note says a tests/-scoped parse cannot see them",
          "tool" in TOOL_INVOCATION_NOTE and "tests/" in TOOL_INVOCATION_NOTE,
          TOOL_INVOCATION_NOTE[:70])

def probe_the_resolver_reads_the_live_declaration() -> None:
    """`declared_gates` must find a gate by its words, not by a hardcoded list."""
    names = {p.name for p, _ in declared_gates(TESTS_DIR)}
    check("this gate finds itself", "test_gate_registration.py" in names,
          f"{len(names)} declared gate(s)")
    check("it finds the gates that declare themselves in words",
          {"test_law_coverage.py", "test_law_structure.py", "test_ontology.py",
           "test_session_bindings.py"} <= names,
          str(sorted(names & {"test_law_coverage.py", "test_law_structure.py",
                              "test_ontology.py", "test_session_bindings.py"})))

def probe_a_string_prefixed_opener_is_read() -> None:
    """A legal string prefix must not hide the declaration — the #62 regression.

    An r-prefix is REQUIRED whenever the docstring quotes a regex, and it is what #62's
    own patch put on tests/test_law_coverage.py. A parser demanding a bare triple quote
    reads that file as having no docstring, so it is neither declared nor non-canonical:
    it vanishes from the scan, and the reverse direction then reports a live registered
    gate as silent. This probe is that exact input, at unit level rather than at audit
    time.
    """
    raw_gate = '#!/usr/bin/env python3\nr"""Gate: a raw-prefixed gate.\n\nBody.\n"""\n'
    check("an r-prefixed opener IS recognised as a docstring",
          reads_a_docstring(raw_gate), raw_gate.splitlines()[1][:40])
    check("and its first line is read with the prefix stripped",
          first_docstring_line(raw_gate) == "Gate: a raw-prefixed gate.",
          repr(first_docstring_line(raw_gate)))
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(Path(tmp), {"test_raw.py": raw_gate},
                                       _register("test_raw.py"))
        problems, report = gate_registration_problems(tests, audit)
        check("a raw-prefixed gate is DECLARED, so no silent-gate problem is raised",
              problems == [] and report["declared"] == ["test_raw.py"],
              f"problems={problems} declared={report['declared']}")
    plain_gate = '"""Gate: a plain gate.\n\nBody.\n"""\n'
    check("a bare-quote opener still reads (no regression)",
          reads_a_docstring(plain_gate), plain_gate.splitlines()[0][:40])

def probe_the_predicate_is_stated_with_its_count() -> None:
    """A number must travel with its predicate — the predicate lives in the module."""
    check("the predicate is a module constant", bool(PREDICATE.strip()), PREDICATE[:70])
    check("the predicate names both directions",
          "REGISTERED" in PREDICATE and "REVERSE" in PREDICATE, PREDICATE[-70:])
    check("the predicate names the scan's file set", "tests/test_*.py" in PREDICATE,
          PREDICATE[:60])

def main() -> int:
    print("gate registry — an unregistered gate never runs (P29, issue #59)")
    print("  synthetic probes")
    probe_an_unregistered_gate_is_named()
    probe_a_silent_registered_gate_is_named()
    probe_the_body_is_not_searched()
    probe_a_non_canonical_declaration_is_named()
    probe_a_registered_canonical_gate_is_clean()
    probe_a_non_gate_file_is_not_inspected()
    probe_a_quoted_registration_is_required()
    print("  live tree")
    probe_the_scan_is_not_vacuous()
    probe_the_resolver_reads_the_live_declaration()
    probe_the_report_states_the_tool_gap()
    probe_a_string_prefixed_opener_is_read()
    probe_the_predicate_is_stated_with_its_count()
    probe_the_live_tree_is_clean()

    print()
    if failures:
        print(f"gate registry FAILED: {len(failures)} check(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("gate registry passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
