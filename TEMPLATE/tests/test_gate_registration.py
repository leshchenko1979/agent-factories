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

A THIRD direction (HQ ruling n=432, issue #68): required -> present. Both directions above
ask whether the gates a tree HAS are wired up; neither asks whether the gates it SHOULD
have are there at all. `tools/audit.py` registers every gate behind an `is_file()` guard, so
a factory that never adopted a gate file runs a shorter suite and still prints HEALTHY —
measured live at /root/inferhub-watch, where 2 gates ran and the verdict was still
`rc=0 HEALTHY`. A DECLARED manifest (`gate_registry.REQUIRED_GATES`, derived from what the
template ships as a declared gate) names the gates every bootstrapped factory must carry,
and each absent one FAILS NAMING it. The coupling leg asserts the manifest EQUALS the
template's declared-gate inventory so the two cannot drift; it is meta-factory-only, because
a bootstrapped factory has no `TEMPLATE/` to compare against and skips it. The optional set
is PRINTED WITH ITS REASON, so an omission is stated and never implied away.

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
    OPTIONAL_GATES,
    PREDICATE,
    REQUIRED_GATES,
    REQUIRED_PREDICATE,
    TOOL_INVOCATION_NOTE,
    declared_gates,
    first_docstring_line,
    gate_registration_problems,
    manifest_drift_problems,
    optional_gate_lines,
    reads_a_docstring,
    required_gate_problems,
)

TESTS_DIR = REPO / "tests"
AUDIT = REPO / "tools" / "audit.py"
# The coupling leg's comparison tree. In the TEMPLATE copy of this file `REPO` resolves to
# `TEMPLATE/`, so this path does not exist there and the leg skips itself — which is the
# behaviour n=432 Part 3 asks for, reached without special-casing.
TEMPLATE_TESTS_DIR = REPO / "TEMPLATE" / "tests"

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

# --- synthetic probes: direction 3, required -> present ---------------------------

def probe_an_absent_required_gate_is_named() -> None:
    """Direction 3: a gate the manifest requires but the tree lacks must FAIL, NAMING it."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, _ = _synthetic_tree(Path(tmp), {"test_present.py": CANONICAL_GATE}, "")
        problems, report = required_gate_problems(tests, ("test_present.py", "test_absent.py"))
        check("direction 3 — an absent required gate is NAMED",
              any("test_absent.py" in p for p in problems),
              problems[0][:80] if problems else "no problem reported")
        check("direction 3 — the report separates present from absent",
              report["absent"] == ["test_absent.py"] and report["present"] == ["test_present.py"],
              f"absent={report['absent']} present={report['present']}")
        check("direction 3 — the message says the gate is ABSENT, not merely missing from a list",
              any("ABSENT" in p for p in problems), str(problems[:1])[:80])

def probe_a_complete_required_set_is_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tests, _ = _synthetic_tree(
            Path(tmp), {"test_a.py": CANONICAL_GATE, "test_b.py": CANONICAL_GATE}, "")
        problems, report = required_gate_problems(tests, ("test_a.py", "test_b.py"))
        check("direction 3 — a tree carrying every required gate raises nothing",
              problems == [] and report["absent"] == [] and report["present"] == ["test_a.py", "test_b.py"],
              "; ".join(problems)[:70])

def probe_the_coupling_leg_skips_without_a_template() -> None:
    """Part 3: the coupling leg is meta-factory-only — no TEMPLATE tree means SKIP, not FAIL.

    A bootstrapped factory has no `TEMPLATE/`, and a leg that FAILED there would RED every
    factory the template is copied to. So the absence of the comparison tree is reported as
    a skip with its reason, never as a violation.
    """
    with tempfile.TemporaryDirectory() as tmp:
        problems, report = manifest_drift_problems(Path(tmp) / "TEMPLATE" / "tests")
        check("the coupling leg SKIPS when no TEMPLATE tree exists",
              problems == [] and report["skipped"] is True,
              f"problems={problems} skipped={report.get('skipped')}")
        check("and the skip states WHY, naming the leg as meta-factory-only",
              "meta-factory" in report.get("reason", ""), report.get("reason", "")[:80])

def probe_a_manifest_template_mismatch_fails_both_ways() -> None:
    """Part 3: the manifest must EQUAL the template's declared-gate inventory, both ways."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, _ = _synthetic_tree(Path(tmp), {"test_shipped.py": CANONICAL_GATE}, "")
        drift, _ = manifest_drift_problems(tests, ("test_other.py",))
        check("a gate the template ships but the manifest omits FAILS",
              any("test_shipped.py" in p and "omits" in p for p in drift),
              "; ".join(drift)[:80])
        drift2, _ = manifest_drift_problems(tests, ("test_shipped.py", "test_ghost.py"))
        check("a gate the manifest requires but the template does not ship FAILS",
              any("test_ghost.py" in p and "does not ship" in p for p in drift2),
              "; ".join(drift2)[:80])
        drift3, report3 = manifest_drift_problems(tests, ("test_shipped.py",))
        check("an exact manifest/template match raises nothing",
              drift3 == [] and report3["skipped"] is False, "; ".join(drift3)[:70])

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

def _naive_declared_names(tests_dir: Path) -> set[str]:
    """A deliberately INDEPENDENT re-scan, used to cross-check the resolver's own reader.

    It shares none of the resolver's regex: it finds the first triple quote in the file and
    reads to the next one. Two independent readers agreeing is evidence; one reader compared
    against a hardcoded name list is not evidence at all — and that is what this probe used
    to do, which made the gate RED on the very tree it ships to. This file is paired
    byte-identically into `TEMPLATE/tests/`, and the template declares only two of the four
    names that list hardcoded (issue #68's follow-on).
    """
    names: set[str] = set()
    for path in sorted(tests_dir.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        start = text.find('"""')
        if start == -1:
            continue
        end = text.find('"""', start + 3)
        if end == -1:
            continue
        first = text[start + 3:end].split("\n", 1)[0].strip()
        if "gate" in first.lower():
            names.add(path.name)
    return names

def probe_the_resolver_reads_the_live_declaration() -> None:
    """`declared_gates` must find a gate by its WORDS — verified against an independent scan.

    This probe used to assert the scan contained a hardcoded four-name list. That is exactly
    what the probe exists to disprove — a resolver must find a gate by its words, not by a
    list — and it made the gate RED on the tree it ships to, because this file is paired
    byte-identically into `TEMPLATE/tests/` and the template declares only two of those four
    names (`test_law_coverage.py` and `test_session_bindings.py` are profile-only; issue #68's
    follow-on, pre-existing and not introduced here). A fixture must model the tree its tool
    runs in (P35), so the expectation is DERIVED from the tree and cross-checked by a second,
    independent reader. A tree whose gates are all canonical passes; a resolver that misses a
    declared gate still fails.
    """
    resolved = {p.name for p, _ in declared_gates(TESTS_DIR)}
    expected = _naive_declared_names(TESTS_DIR)
    check("the resolver finds every gate that declares itself in words",
          resolved == expected,
          f"missed={sorted(expected - resolved)} extra={sorted(resolved - expected)}")
    check("this gate finds itself", "test_gate_registration.py" in resolved,
          f"{len(resolved)} declared gate(s)")
    check("the scan is not vacuous — it found gates to check", len(resolved) >= 2,
          f"{len(resolved)} declared gate(s)")
    non_canonical: list[str] = []
    for name in sorted(resolved):
        first = first_docstring_line((TESTS_DIR / name).read_text(encoding="utf-8")) or ""
        if not first.startswith("Gate"):
            non_canonical.append(name)
    print(f"  (this tree carries {len(non_canonical)} non-canonical declaration(s) found by "
          f"the loose pass: {non_canonical or 'none — the synthetic probes cover that form'})")

def probe_the_live_required_set_is_present() -> None:
    """Direction 3 on the live tree, plus the coupling leg where a TEMPLATE tree exists."""
    problems, report = required_gate_problems(TESTS_DIR)
    for problem in problems:
        print(f"    {problem}")
    check("every required gate is PRESENT in the live tree",
          not problems, "; ".join(problems)[:90])
    check("the manifest is non-vacuous", len(report["required"]) >= 20,
          f"{len(report['required'])} required gate(s)")
    drift, drift_report = manifest_drift_problems(TEMPLATE_TESTS_DIR)
    for problem in drift:
        print(f"    {problem}")
    if drift_report.get("skipped"):
        print(f"  coupling leg SKIPPED: {drift_report['reason']}")
    check("the manifest EQUALS the template's declared-gate inventory",
          not drift, "; ".join(drift)[:90])

def probe_the_optional_set_is_printed_with_its_reason() -> None:
    """Part 4: the optional set is printed WITH its reason, never silently omitted."""
    lines = optional_gate_lines()
    check("every optional gate is printed WITH a reason",
          len(lines) == len(OPTIONAL_GATES) and all(" — " in line for line in lines),
          f"{len(lines)} line(s)")
    check("the optional set is disjoint from the required manifest",
          not (set(OPTIONAL_GATES) & set(REQUIRED_GATES)),
          str(sorted(set(OPTIONAL_GATES) & set(REQUIRED_GATES))))
    check("the required predicate is a module constant naming the manifest",
          bool(REQUIRED_PREDICATE.strip()) and "REQUIRED_GATES" in REQUIRED_PREDICATE,
          REQUIRED_PREDICATE[:70])
    for line in lines:
        print(f"    {line}")

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
    print("gate registry — an unregistered gate never runs (P29, issues #59, #68)")
    print("  synthetic probes")
    probe_an_unregistered_gate_is_named()
    probe_a_silent_registered_gate_is_named()
    probe_the_body_is_not_searched()
    probe_a_non_canonical_declaration_is_named()
    probe_a_registered_canonical_gate_is_clean()
    probe_a_non_gate_file_is_not_inspected()
    probe_a_quoted_registration_is_required()
    print("  synthetic probes — direction 3, required -> present")
    probe_an_absent_required_gate_is_named()
    probe_a_complete_required_set_is_clean()
    probe_the_coupling_leg_skips_without_a_template()
    probe_a_manifest_template_mismatch_fails_both_ways()
    print("  live tree")
    probe_the_scan_is_not_vacuous()
    probe_the_resolver_reads_the_live_declaration()
    probe_the_report_states_the_tool_gap()
    probe_a_string_prefixed_opener_is_read()
    probe_the_predicate_is_stated_with_its_count()
    probe_the_live_tree_is_clean()
    print("  live tree — direction 3")
    probe_the_live_required_set_is_present()
    probe_the_optional_set_is_printed_with_its_reason()

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
