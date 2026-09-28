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

A FIFTH surface rides this file without being a fifth direction (HQ ruling n=786, #125). A
per-gate budget is a cap on a COMMAND, and every declared entry names the revision its basis
was taken at — `measured_at`. Nothing resolved it, so an entry whose basis was taken on a
command that has since changed read exactly like one whose command is unchanged, and the
audit kept printing the stale entry as sound. The probes at the end of this file resolve it
and compare the gate file's BLOB and the argv its REGISTRATION declares, both read from the
object database against a throwaway repository — because leg B is precisely the half that
moves while a blob does not, which is how six registrations changed runner form in one commit
and no file-identity check could see it. It REPORTS and never gates: the budget values are the
process owner's and never the implementing lane's (n=574 PART 5), and a stale basis whose gate
still runs inside its cap is a fact about the manifest rather than a failing gate.

Run:  python3 tests/test_gate_registration.py
Exit: 0 clean, non-zero on any gate that is unregistered, non-canonical, or silent.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_registry import (  # noqa: E402
    LAW_COVERAGE_PREDICATE,
    OPENER_ONLY_NOTE,
    OPTIONAL_GATES,
    PREDICATE,
    PYTEST_RUNNER,
    REQUIRED_GATES,
    REQUIRED_PREDICATE,
    RUNNER_FORM_PREDICATE,
    SCRIPT_RUNNER,
    TOOL_INVOCATION_NOTE,
    declared_gates,
    first_docstring_line,
    gate_registration_problems,
    law_coverage_problems,
    manifest_drift_problems,
    optional_gate_lines,
    reads_a_docstring,
    registration_entries,
    required_gate_problems,
    runner_form_problems,
    target_form,
)

TESTS_DIR = REPO / "tests"
AUDIT = REPO / "tools" / "audit.py"
# Direction 4's two law sources. Both are meta-factory surfaces: a bootstrapped factory
# has its own skill at a different path and no rework log until it writes one, and the
# leg reports an unread source rather than treating it as an empty one.
REWORK_LOG = REPO / "evidence" / "rework.md"
SKILL = REPO / "skills" / "meta-factory" / "SKILL.md"
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

# --- synthetic probes: direction 4, law -> registered -----------------------------

REWORK_HEADER = (
    "## Entries\n\n"
    "| Date | Source | Defect | Root cause | Resolution | Prevented by | Subject |\n"
    "|---|---|---|---|---|---|---|\n"
)

def _rework(*prevented_by: str) -> str:
    """A synthetic rework log with one Entries row per `Prevented by` cell."""
    return REWORK_HEADER + "".join(
        f"| 2026-01-01 | #1 | defect {n} | cause {n} | a fix | {cell} | subject-{n} |\n"
        for n, cell in enumerate(prevented_by, 1)
    )

def _law_tree(
    root: Path, files: dict[str, str], audit: str, rework: str, skill: str
) -> tuple[Path, Path, Path, Path]:
    """A throwaway tree carrying BOTH law sources; return (tests, audit, rework, skill)."""
    tests, audit_path = _synthetic_tree(root, files, audit)
    rework_path = root / "rework.md"
    rework_path.write_text(rework, encoding="utf-8")
    skill_path = root / "SKILL.md"
    skill_path.write_text(skill, encoding="utf-8")
    return tests, audit_path, rework_path, skill_path

def probe_a_law_named_unregistered_mechanism_is_named() -> None:
    """Direction 4 (a): a law names a mechanism that exists but never runs."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit, rework, skill = _law_tree(
            Path(tmp),
            {"test_orphan.py": CANONICAL_GATE},
            "# an audit that registers nothing\n",
            _rework("tests/test_orphan.py"),
            "no mechanism named here\n",
        )
        problems, report = law_coverage_problems(tests, audit, rework, skill)
        check("direction 4 — a law-named unregistered mechanism is NAMED",
              any("test_orphan.py" in p for p in problems),
              problems[0][:80] if problems else "no problem reported")
        check("direction 4 — the report says WHERE the law named it",
              report["unregistered"] == [
                  "test_orphan.py — named by rework log, Entries row 4"
              ],
              str(report["unregistered"]))
        check("direction 4 — the report states the sources it read",
              report["rework_rows"] == 1 and report["skill_read"] is True,
              str(report["law_sources"]))

def probe_a_registered_law_named_mechanism_is_clean() -> None:
    """Direction 4: the same tree with the mechanism registered reports nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit, rework, skill = _law_tree(
            Path(tmp),
            {"test_orphan.py": CANONICAL_GATE},
            _register("test_orphan.py"),
            _rework("tests/test_orphan.py"),
            "no mechanism named here\n",
        )
        problems, report = law_coverage_problems(tests, audit, rework, skill)
        check("direction 4 — a registered law-named mechanism is clean",
              problems == [] and report["named"] == 1,
              f"problems={problems} named={report['named']}")

def probe_the_skill_arm_alone_names_an_unregistered_mechanism() -> None:
    """Both sources are read: the skill arm fires with the rework log silent."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit, rework, skill = _law_tree(
            Path(tmp),
            {"test_skillgate.py": CANONICAL_GATE},
            "# an audit that registers nothing\n",
            _rework("nothing yet"),
            "the gate must run, naming tests/test_skillgate.py\n",
        )
        problems, report = law_coverage_problems(tests, audit, rework, skill)
        check("direction 4 — the skill arm names an unregistered mechanism",
              report["unregistered"] == ["test_skillgate.py — named by skill line 1"],
              str(report["unregistered"]))
        check("direction 4 — the rework arm stays silent on a 'nothing yet' entry",
              "test_orphan.py" not in str(report["unregistered"]),
              str(report["unregistered"]))

def probe_a_prose_mention_is_not_a_mechanism() -> None:
    """The scan is for a NAMED FILE, never the word "gate" — the false-positive guard.

    A whole-file search for the word "gate" is the predicate this direction must NOT be:
    it fires on prose, and this repo has already measured two files it would pick up
    (`tests/test_review.py`, `tests/test_telemetry.py`) neither of which is a gate.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit, rework, skill = _law_tree(
            Path(tmp), {},
            "# an audit that registers nothing\n",
            _rework("nothing yet"),
            "every gate must run; the gate registry reads the gates; a gate is required\n",
        )
        problems, report = law_coverage_problems(tests, audit, rework, skill)
        check("direction 4 — the word 'gate' in prose names no mechanism",
              report["named"] == 0 and problems == [],
              f"named={report['named']} problems={problems}")

def probe_only_the_prevented_by_column_is_read() -> None:
    """The law source is ONE column: a file named in another column is not a claim."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit, rework, skill = _law_tree(
            Path(tmp),
            {"test_other.py": CANONICAL_GATE},
            "# an audit that registers nothing\n",
            REWORK_HEADER
            + "| 2026-01-01 | #1 | defect | cause | tests/test_other.py | nothing yet | s |\n",
            "no mechanism named here\n",
        )
        problems, report = law_coverage_problems(tests, audit, rework, skill)
        check("direction 4 — a file named outside `Prevented by` is not a mechanism",
              report["named"] == 0 and problems == [],
              f"named={report['named']} problems={problems}")

def probe_a_dead_reference_is_reported() -> None:
    """Direction 4 (b): the law cites a mechanism this tree does not carry at all."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit, rework, skill = _law_tree(
            Path(tmp), {},
            "# an audit that registers nothing\n",
            _rework("tests/test_missing.py"),
            "no mechanism named here\n",
        )
        problems, report = law_coverage_problems(tests, audit, rework, skill)
        check("direction 4 — a law-named file that does not exist is reported",
              any("test_missing.py" in p and "dead reference" in p for p in problems),
              problems[0][:80] if problems else "no problem reported")
        check("direction 4 — a dead reference is not counted as merely unregistered",
              report["unregistered"] == [] and len(report["dead_reference"]) == 1,
              str(report["dead_reference"]))

def probe_an_unreadable_law_source_fails_rather_than_passing() -> None:
    """A present-but-unparseable law source is not an absent one (the n=571 class)."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit, rework, skill = _law_tree(
            Path(tmp), {},
            "# an audit that registers nothing\n",
            "## Entries\n\n| Date | Source |\n|---|---|\n| 2026-01-01 | #1 |\n",
            "no mechanism named here\n",
        )
        problems, report = law_coverage_problems(tests, audit, rework, skill)
        check("direction 4 — an unreadable law source FAILS and states why",
              any("law source unreadable" in p for p in problems),
              problems[0][:90] if problems else "no problem reported")
        check("direction 4 — the stated reason is the column reader's own",
              report["rework_reason"]
              == "the 'Entries' table has no 'Prevented by' column",
              str(report["rework_reason"]))

    # The contrast: an ABSENT source is a SKIP — reported as not-read, never as a clean
    # read, and not a failure. A bootstrapped factory has no rework log until it writes one.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tests, audit = _synthetic_tree(root, {}, "# an audit that registers nothing\n")
        problems, report = law_coverage_problems(
            tests, audit, root / "no-such-rework.md", root / "no-such-skill.md"
        )
        check("direction 4 — an ABSENT law source is a reported skip, not a failure",
              problems == [] and report["rework_read"] is False
              and report["skill_read"] is False
              and report["law_sources"][1] == "skill: NOT READ",
              f"problems={problems} sources={report['law_sources']}")

def probe_the_law_coverage_predicate_states_its_scope() -> None:
    """The scope bound travels with the predicate, or the direction swallows #48."""
    check("the law-coverage predicate is a module constant",
          bool(LAW_COVERAGE_PREDICATE.strip()), LAW_COVERAGE_PREDICATE[:60])
    check("it carries the SCOPE BOUND that keeps #48 out of its population",
          "SCOPE BOUND" in LAW_COVERAGE_PREDICATE and "#48" in LAW_COVERAGE_PREDICATE,
          LAW_COVERAGE_PREDICATE[-90:])
    check("it states that a failure NAMES the mechanism",
          "NAMING it" in LAW_COVERAGE_PREDICATE, LAW_COVERAGE_PREDICATE[:80])

def probe_the_live_law_coverage_is_clean() -> None:
    """The meta-factory carries both law sources; a bootstrapped factory carries neither.

    This gate is REQUIRED, so its copy runs in every factory — and a factory has its own
    skill at a different path and no rework log until it writes one. So each source is
    asserted only when it EXISTS, and the vacuity leg needs BOTH, which keeps a shipped
    copy reporting a SKIP instead of REDing on an absent law surface. Same shape as the
    coupling leg above, reached without special-casing.
    """
    problems, report = law_coverage_problems(TESTS_DIR, AUDIT, REWORK_LOG, SKILL)
    for problem in problems:
        print(f"    {problem}")
    print(
        f"  predicate: {LAW_COVERAGE_PREDICATE}\n"
        f"  sources: {'; '.join(report['law_sources'])}\n"
        f"  {report['named']} mechanism(s) named by law, against "
        f"{report['registered']} registered tests/ path(s) — "
        f"unregistered: {len(report['unregistered'])}, "
        f"dead references: {len(report['dead_reference'])}, "
        f"{len(problems)} problem(s)"
    )
    check("every mechanism a recorded law names is registered", problems == [],
          "; ".join(problems)[:90])

    if REWORK_LOG.is_file():
        check("the rework log is present and was READ, not silently skipped",
              report["rework_read"] is True and report["rework_reason"] is None,
              str(report["law_sources"][0]))
    if SKILL.is_file():
        check("the skill is present and was READ, not silently skipped",
              report["skill_read"] is True, str(report["law_sources"][1]))

    if report["rework_read"] and report["skill_read"]:
        check("the scan is not vacuous — both law sources read and mechanisms named",
              report["named"] > 0,
              f"named={report['named']} rework_rows={report['rework_rows']} "
              f"skill_lines={report['skill_lines']}")
    else:
        print("  (vacuity leg skipped — this tree does not carry BOTH law sources; "
              "the meta-factory does, a bootstrapped factory need not)")

# --- synthetic probes: direction 5, registered -> CAN RUN -------------------------

def _register_pytest(*names: str) -> str:
    """The SAME registrations as `_register`, under the pytest runner."""
    return "".join(
        f'gates_to_run.append([sys.executable, "-m", "pytest", "tests/{n}"])\n' for n in names
    )

# pytest-style: module-level `def test_*`, NO `__main__` guard. Invoked as a script this
# file defines its functions and calls none of them — it exits 0 having run nothing.
PYTEST_STYLE = (
    '#!/usr/bin/env python3\n"""Gate: a pytest-style synthetic gate.\n"""\n'
    "\n\ndef test_one() -> None:\n    assert True\n"
    "\n\ndef test_two() -> None:\n    assert True\n"
)

# script-style: a `main()` under a `__main__` guard, so a script invocation really runs it.
SCRIPT_STYLE = (
    '#!/usr/bin/env python3\n"""Gate: a script-style synthetic gate.\n"""\n'
    "\n\ndef main() -> int:\n    return 0\n"
    "\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n"
)

def probe_a_pytest_style_target_under_a_script_runner_is_named() -> None:
    """The defect: a registration that cannot run its target."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp), {"test_pytestish.py": PYTEST_STYLE}, _register("test_pytestish.py")
        )
        problems, report = runner_form_problems(tests, audit)
        check("direction 5 — a pytest-style target under a script runner is NAMED",
              any("test_pytestish.py" in p for p in problems),
              problems[0][:80] if problems else "no problem reported")
        check("direction 5 — the report carries the mismatch, naming file and runner read",
              len(report["mismatches"]) == 1
              and "test_pytestish.py" in report["mismatches"][0]
              and "registered as a script" in report["mismatches"][0],
              str(report["mismatches"])[:90])

def probe_the_same_target_under_the_pytest_runner_is_clean() -> None:
    """The same file, registered correctly, must be clean — else the rule is a blanket."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp), {"test_pytestish.py": PYTEST_STYLE}, _register_pytest("test_pytestish.py")
        )
        problems, report = runner_form_problems(tests, audit)
        check("direction 5 — the same target under the pytest runner is CLEAN",
              problems == [] and report["mismatches"] == [],
              str(problems)[:80] or "clean")

def probe_a_script_style_target_under_the_pytest_runner_is_not_reported() -> None:
    """ONE-WAY BY DESIGN: pytest can collect a script-style file, so it is not a defect."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp), {"test_scripty.py": SCRIPT_STYLE}, _register_pytest("test_scripty.py")
        )
        problems, report = runner_form_problems(tests, audit)
        check("direction 5 — a script-style target under the pytest runner is NOT reported",
              problems == [],
              str(problems)[:80] or "clean")
        check("direction 5 — and the report still states the runner it read",
              any("runner=pytest" in f and "target form=script" in f for f in report["forms"]),
              str(report["forms"])[:90])

def probe_a_file_with_a_main_guard_is_still_pytest_form() -> None:
    """A file carrying BOTH is PYTEST-form (#124).

    The earlier rule read it as script-form on the reasoning that it "runs under either
    runner, so flagging it would be a false red". Measured FALSE 2026-09-20: under the
    script runner pytest never collects the file, so its module-level legs never run —
    SIX registered files carried 99 such legs, all dead, and the audit printed PASS for
    each. The premise was true of the FILE and false of each RUNNER.
    """
    both = PYTEST_STYLE + '\n\nif __name__ == "__main__":\n    raise SystemExit(0)\n'
    check("direction 5 — a `__main__` guard does NOT make a test-carrying file script-form",
          target_form(both) == PYTEST_RUNNER, f"got {target_form(both)}")
    check("direction 5 — without the guard it is pytest-form too",
          target_form(PYTEST_STYLE) == PYTEST_RUNNER, f"got {target_form(PYTEST_STYLE)}")
    check("direction 5 — a file with NO test function stays script-form",
          target_form('def main() -> int:\n    return 0\n') == SCRIPT_RUNNER,
          f"got {target_form('def main() -> int:\n    return 0\n')}")

def probe_the_runner_is_read_from_argv_not_guessed_from_the_target() -> None:
    """The runner comes from the APPEND; the shape from the TARGET. Neither implies the other."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp), {"test_pytestish.py": PYTEST_STYLE, "test_scripty.py": SCRIPT_STYLE},
            _register("test_pytestish.py") + _register_pytest("test_scripty.py"),
        )
        entries = registration_entries(audit.read_text(encoding="utf-8"))
        by_name = {e["name"]: e["runner"] for e in entries}
        check("direction 5 — the runner is read from each append's own argv",
              by_name == {"test_pytestish.py": SCRIPT_RUNNER, "test_scripty.py": PYTEST_RUNNER},
              str(by_name))

def probe_an_absent_target_is_skipped_and_named_not_double_reported() -> None:
    """Presence is direction 3's leg; a second report of one defect is noise."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(Path(tmp), {}, _register("test_ghost.py"))
        problems, report = runner_form_problems(tests, audit)
        check("direction 5 — an absent target is NOT a runner-form problem",
              problems == [], str(problems)[:80] or "clean")
        check("direction 5 — but it is NAMED in the report as skipped",
              any("target absent" in f for f in report["forms"]),
              str(report["forms"])[:90])

def probe_a_tool_invocation_carries_no_target_shape() -> None:
    """A `tools/*.py` invocation has no test shape to read, and must not be classified."""
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp), {},
            'gates_to_run.append([sys.executable, "tools/ledger.py", "verify"])\n',
        )
        problems, report = runner_form_problems(tests, audit)
        check("direction 5 — a tool invocation is reported as carrying no target shape",
              problems == [] and any("tool invocation" in f for f in report["forms"]),
              str(report["forms"])[:90])

def probe_registered_entries_is_a_projection_of_one_scan() -> None:
    """DRY, mechanically: a second `_APPEND` scan is the same defect one level down."""
    import inspect

    from gate_registry import registered_entries as _re

    source = inspect.getsource(_re)
    check("direction 5 — registered_entries does NOT re-scan for appends",
          "_APPEND" not in source,
          "registered_entries still scans _APPEND itself")
    check("direction 5 — registered_entries delegates to registration_entries",
          "registration_entries(" in source, source.strip().splitlines()[0][:60])

def probe_a_target_whose_name_contains_pytest_is_not_misread_as_the_runner() -> None:
    """The runner is read from ARGUMENT STRUCTURE, never from a substring of the argv.

    A script-form registration of `tests/test_pytest_form.py` carries the word "pytest"
    inside the target's own name. A `"pytest" in argv` test reads it as a pytest
    invocation and silently HIDES the mismatch — the predicate's own first run did exactly
    that, on the probe above.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tests, audit = _synthetic_tree(
            Path(tmp), {"test_pytest_form.py": PYTEST_STYLE}, _register("test_pytest_form.py")
        )
        entries = registration_entries(audit.read_text(encoding="utf-8"))
        check("direction 5 — a target named test_pytest_form.py in script form reads as script",
              entries[0]["runner"] == SCRIPT_RUNNER, str(entries[0]["runner"]))
        problems, _ = runner_form_problems(tests, audit)
        check("direction 5 — and the mismatch is still reported, not hidden by the name",
              any("test_pytest_form.py" in p for p in problems),
              problems[0][:80] if problems else "no problem reported — hidden by the name")

def probe_the_runner_form_predicate_states_its_one_way_bound() -> None:
    """Every direction carries its SCOPE BOUND in the predicate text itself."""
    check("direction 5 — the predicate states the one-way bound",
          "ONE-WAY BY DESIGN" in RUNNER_FORM_PREDICATE
          and "NO module-level `def test_*`" in RUNNER_FORM_PREDICATE
          and "exits 5" in RUNNER_FORM_PREDICATE,
          RUNNER_FORM_PREDICATE[-60:])

def probe_the_live_runner_forms_are_clean() -> None:
    """The live tree: every registration can run its target, and the population is printed."""
    problems, report = runner_form_problems(TESTS_DIR, AUDIT)
    check("the audit was READ, not silently skipped", report["audit_read"] is True,
          f"audit_read={report['audit_read']}")
    check("the live tree has no registration that cannot run its target",
          problems == [], str(problems[:1])[:90] or "clean")
    print(f"  live tree — direction 5: {report['registrations']} registration(s) read, "
          f"{len(report['mismatches'])} runner-form mismatch(es)")
    for form in report["forms"]:
        print(f"    {form}")

# --- synthetic probes: a declared basis is RESOLVED, never trusted (#125) ---------
#
# HQ ruling n=786: `measured_at` was a declared revision that NOTHING resolved, so an entry
# whose basis was taken on a command that has since changed read like one whose command is
# unchanged. `gate_budget.budget_staleness` resolves it and compares two things — the gate
# file's BLOB at that revision against its blob at HEAD (leg A), and the argv its
# REGISTRATION declares at the two revisions (leg B).
#
# Leg B is the load-bearing half, and it is the reason a blob-only check is not enough: the
# runner form lives in `tools/audit.py`, so six registrations moved from the script form to
# `-m pytest` in one commit while every one of those gate files stayed byte-identical. The
# two gates that exhausted their budget on 2026-09-20 and had NOT changed bytes are exactly
# the two a file-identity check reads CLEAN.
#
# These probes run against a THROWAWAY REPOSITORY, because a leg that reads the object
# database cannot be exercised any other way: a lookalike that stubs the git calls would
# pass while the real reads stayed wrong, which is the bound stated in that module's own
# probe note. `budget_staleness(..., repo_root=...)` exists for exactly this and says so.

STALE_BASE_AUDIT = (
    "import sys\n"
    "gates_to_run = []\n"
    'gates_to_run.append([sys.executable, "tests/test_moved.py"])\n'
    'gates_to_run.append([sys.executable, "tests/test_same.py"])\n'
    'gates_to_run.append([sys.executable, "tests/test_runner_moved.py"])\n'
)
STALE_HEAD_AUDIT = (
    "import sys\n"
    "gates_to_run = []\n"
    'gates_to_run.append([sys.executable, "tests/test_moved.py"])\n'
    'gates_to_run.append([sys.executable, "tests/test_same.py"])\n'
    'gates_to_run.append([sys.executable, "-m", "pytest", "tests/test_runner_moved.py"])\n'
)

def _gate_budget_module():
    """`tools/gate_budget.py` ITSELF — the mechanism under probe, never a lookalike.

    Imported lazily, and by the module's own NAME rather than through a file loader, so the
    module under probe is the one the audit runs and not a second copy that could satisfy
    every assertion below while the real reader stayed wrong. `tools/` is APPENDED, never
    inserted, so the repo's own `registry/` directory keeps its precedence over the
    same-named module beside it.
    """
    tools = str(REPO / "tools")
    if tools not in sys.path:
        sys.path.append(tools)
    import gate_budget  # noqa: PLC0415

    return gate_budget

def _git(root: Path, *args: str):
    """One git call inside `root`, both streams captured, never through a pipe."""
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60
    )

def _commit(root: Path, message: str) -> str | None:
    """Stage the synthetic tree and commit it; the new sha, or None when git refuses."""
    if _git(root, "add", "tests", "tools").returncode != 0:
        return None
    done = _git(
        root,
        "-c", "user.email=probe@example.invalid",
        "-c", "user.name=probe",
        "-c", "commit.gpgsign=false",
        "commit", "-q", "-m", message,
    )
    if done.returncode != 0:
        return None
    got = _git(root, "rev-parse", "HEAD")
    return got.stdout.strip() if got.returncode == 0 else None

def _two_commit_repo(root: Path) -> tuple[str | None, str | None]:
    """A history in which one gate's BYTES move and another's RUNNER FORM does.

    `tests/test_moved.py` changes content between the two commits; `tests/test_same.py`
    changes nothing; `tests/test_runner_moved.py` keeps its bytes while its registration
    moves from the script form to `-m pytest` — the live shape of #124's commit, in
    miniature. Returns (base_sha, head_sha), or (None, None) when git is unavailable or
    refuses, so the caller STATES that instead of reading it as a clean sweep.
    """
    tests, tools = root / "tests", root / "tools"
    tests.mkdir(parents=True, exist_ok=True)
    tools.mkdir(parents=True, exist_ok=True)
    (tests / "test_same.py").write_text("# identical at both revisions\n", encoding="utf-8")
    (tests / "test_moved.py").write_text("# v1\n", encoding="utf-8")
    (tests / "test_runner_moved.py").write_text(
        "# bytes held; the runner form moved\n", encoding="utf-8"
    )
    (tools / "audit.py").write_text(STALE_BASE_AUDIT, encoding="utf-8")
    if _git(root, "init", "-q").returncode != 0:
        return None, None
    base = _commit(root, "base")
    if base is None:
        return None, None
    (tests / "test_moved.py").write_text("# v2 — the bytes moved\n", encoding="utf-8")
    (tools / "audit.py").write_text(STALE_HEAD_AUDIT, encoding="utf-8")
    return base, _commit(root, "head")

def _basis(measured_at: str) -> dict:
    """A well-formed declared entry: `budget_sec` IS `margin_x x measured_sec`, so the only
    thing these probes vary is the revision the basis was taken at."""
    return {"budget_sec": 4.0, "measured_sec": 1.0, "margin_x": 4.0, "measured_at": measured_at}

def _manifest(root: Path, gates: dict) -> Path:
    """Write a throwaway manifest and return its path — never the live store."""
    path = root / "gates.json"
    path.write_text(
        json.dumps({"default": {"budget_sec": 120.0}, "gates": gates}), encoding="utf-8"
    )
    return path

def probe_the_declared_basis_legs_are_resolved() -> None:
    """Both legs, and the clean cell between them, over one synthetic history."""
    module = _gate_budget_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base, head = _two_commit_repo(root)
        if base is None or head is None:
            check("the probe repository could be built and committed", False,
                  f"base={base} head={head} — this leg could not judge")
            return
        entries = {
            "tests/test_moved.py": _basis(base),
            "tests/test_same.py": _basis(base),
            "tests/test_runner_moved.py": _basis(base),
        }
        stale, note = module.budget_staleness(entries, root)
        found = {s.key: s for s in stale}
        check("a MOVED BLOB is stale on leg A",
              found.get("tests/test_moved.py") is not None
              and found["tests/test_moved.py"].legs == ("bytes",),
              str(found.get("tests/test_moved.py")))
        check("a MOVED REGISTRATION is stale on leg B with its bytes held",
              found.get("tests/test_runner_moved.py") is not None
              and found["tests/test_runner_moved.py"].legs == ("runner",),
              str(found.get("tests/test_runner_moved.py")))
        check("an entry whose bytes AND registration both held is not reported",
              "tests/test_same.py" not in found,
              str(found.get("tests/test_same.py")))
        check("the sweep reported exactly the two entries that moved", len(stale) == 2,
              f"{len(stale)} stale: {sorted(found)}")
        check("the account states its count, its population AND the revision it compared "
              "against",
              note.startswith(f"{len(stale)} of {len(entries)} declared entries")
              and head[:12] in note,
              note[:120])

def probe_an_unresolvable_revision_is_reported_never_clean() -> None:
    """A basis this clone cannot resolve is UNKNOWN: named, counted, and never read clean."""
    module = _gate_budget_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base, _head = _two_commit_repo(root)
        if base is None:
            check("the probe repository could be built and committed", False,
                  "no base commit — this leg could not judge")
            return
        missing = "0" * 40
        entries = {
            "tests/test_same.py": _basis(base),
            "tests/test_moved.py": _basis(missing),
        }
        stale, note = module.budget_staleness(entries, root)
        check("an unresolvable measured_at is named WITH the count it covers",
              "NOT EXAMINED" in note and missing in note and "1 entry" in note,
              note.split("|")[-1].strip()[:120])
        check("the entry that could not be reached is not reported as stale",
              all(s.key != "tests/test_moved.py" for s in stale),
              str([s.key for s in stale]))
        check("the entry that COULD be reached was still examined, and the account says so",
              note.startswith(f"{len(stale)} of 2 declared entries"),
              note[:90])

def probe_a_tree_without_a_resolvable_head_is_not_read_as_clean() -> None:
    """No object database at all: the sweep states it could not run, rather than passing."""
    module = _gate_budget_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)  # deliberately NOT a repository
        stale, note = module.budget_staleness({"tests/test_same.py": _basis("HEAD")}, root)
        check("a directory with no resolvable HEAD reports NOT RUN, not clean",
              stale == () and note.startswith("NOT RUN"), note[:120])
        check("and it names how many declared entries it left UNEXAMINED",
              "1 declared entry left UNEXAMINED" in note, note[-100:])

def probe_a_malformed_entry_still_raises() -> None:
    """The sweep is ADDITIVE: an entry with no stated basis is still refused, before any read."""
    module = _gate_budget_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _manifest(
            root,
            {"tests/test_no_basis.py": {"budget_sec": 4.0, "measured_sec": 1.0, "margin_x": 4.0}},
        )
        raised = ""
        try:
            module.load_gate_budgets(path=path, repo_root=root)
        except module.GateBudgetManifestError as exc:
            raised = str(exc)
        check("an entry with no measured_at still raises, naming the key",
              "measured_at" in raised, raised[:120] or "nothing was raised")

def probe_the_margin_law_still_raises() -> None:
    """And a budget its own stated basis does not follow is still refused."""
    module = _gate_budget_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _manifest(
            root,
            {"tests/test_same.py": {"budget_sec": 9.0, "measured_sec": 1.0,
                                    "margin_x": 4.0, "measured_at": "HEAD"}},
        )
        raised = ""
        try:
            module.load_gate_budgets(path=path, repo_root=root)
        except module.GateBudgetManifestError as exc:
            raised = str(exc)
        check("a budget that is not margin_x x measured_sec still raises",
              "is not margin_x x measured_sec" in raised, raised[:120] or "nothing was raised")

def probe_the_live_sweep_states_its_own_account() -> None:
    """On the live manifest: a count that travels with the population it was taken over.

    This asserts the ACCOUNT, never a verdict, and it is deliberately indifferent to how
    many entries are stale — the check REPORTS (the values are the process owner's), so a
    probe that demanded a clean sweep would turn a report into a gate. The template copy of
    this file has no manifest of its own (it ships `gates.example.json`), and it states that
    rather than reading the absence as a clean sweep.
    """
    module = _gate_budget_module()
    budgets = module.load_gate_budgets()
    if not budgets.gates:
        print(f"  live manifest — declared fallback in use, nothing declared to sweep "
              f"({budgets.default_source[-70:]})")
        return
    check("the live manifest was READ, not skipped",
          budgets.default_source.endswith(":default"), budgets.default_source[-70:])
    check("every key the sweep names is a key the manifest declares",
          all(s.key in budgets.gates for s in budgets.stale),
          str([s.key for s in budgets.stale if s.key not in budgets.gates])[:100]
          or "all declared")
    check("the account leads with the count of the population it examined",
          budgets.stale_note.startswith(
              f"{len(budgets.stale)} of {len(budgets.gates)} declared entries"
          ),
          budgets.stale_note[:110])
    print(f"  live manifest — {len(budgets.gates)} declared entr"
          f"{'y' if len(budgets.gates) == 1 else 'ies'}, {len(budgets.stale)} stale")

# ---------------------------------------------------------------------------
# #93 — THE THREE-STATE VERDICT, and the cause on the line (P29).
#
# The class this leg closes, as Triage measured it at pristine 2fbd097: `run_gate`
# returned `exit_code: 99` with `duration_sec: 0.0` HARDCODED on a timeout, so a gate
# that timed out and a gate that crashed on import were the SAME ROW -- and the 0.0 was
# a literal occupying a field whose name asserts it was measured. The default report
# carried no stderr at all, so the cause was invisible to the reader who must decide
# whether to re-run.
#
# A probe over a COPY would satisfy every assertion below while the runner the audit
# actually uses stayed wrong, so `_audit_module()` imports `tools/audit.py` by its own
# name -- the same convention as `_gate_budget_module()` above, and for the same reason.
# ---------------------------------------------------------------------------

# The probe's budget is deliberately TINY, and that is a design choice rather than a
# detail: this gate carries a DECLARED 4.35s budget, and a probe that really sleeps for
# seconds would turn the gate that GUARDS the timeout law into a flake generator -- the
# exact defect #93 exists to close. At 0.05s the forced timeout costs two attempts of
# 0.05s each.
PROBE_TIMEOUT_BUDGET_SEC = 0.05


def _audit_module():
    """`tools/audit.py` ITSELF -- the mechanism under probe, never a lookalike.

    Imported lazily and by the module's own NAME rather than through a file loader, so
    the runner under probe is the one the audit runs. `tools/` is APPENDED, never
    inserted, so the repo's own `registry/` keeps its precedence over the same-named
    module beside it. Pair of `_gate_budget_module` above.
    """
    tools = str(REPO / "tools")
    if tools not in sys.path:
        sys.path.append(tools)
    import audit  # noqa: PLC0415

    return audit


def _synthetic_gate(passed: bool, unknown: bool) -> dict:
    """One gate result shaped exactly as `run_gate` returns them."""
    return {"cmd": "synthetic", "passed": passed, "unknown": unknown, "duration_sec": 1.0}


def probe_a_timeout_carries_true_elapsed_and_a_distinct_exit_code() -> dict:
    """PART 1: a killed gate reports WHEN it died, and is never read as a crash.

    Returns the result so the retry probe asserts on the SAME run rather than sleeping
    a second time.
    """
    audit = _audit_module()
    gate_budget = _gate_budget_module()
    res = audit.run_gate(["/bin/sleep", "5"], REPO, PROBE_TIMEOUT_BUDGET_SEC)
    check(
        "a timed-out gate carries the DISTINCT timeout exit code, never the generic 99",
        res["exit_code"] == gate_budget.TIMEOUT_EXIT_CODE,
        f"exit_code={res['exit_code']}, TIMEOUT_EXIT_CODE={gate_budget.TIMEOUT_EXIT_CODE}",
    )
    check(
        "a timed-out gate is UNKNOWN, never a plain failure",
        res["unknown"] is True and res["passed"] is False,
        f"unknown={res['unknown']}, passed={res['passed']}",
    )
    check(
        "the recorded duration is the MEASURED elapsed time, not the 0.0 literal",
        res["duration_sec"] > 0.0,
        f"{res['duration_sec']}s against a {PROBE_TIMEOUT_BUDGET_SEC}s budget",
    )
    check(
        "the cause is in stderr, where the FAIL line reads it",
        "budget exhausted" in res["stderr"],
        res["stderr"][:90],
    )
    return res


def probe_the_retry_is_bounded_and_recorded(timed_out: dict) -> None:
    """PART 4: ONE retry, recorded -- an unrecorded retry hides a genuinely slow gate."""
    check(
        "a timeout is retried exactly ONCE",
        timed_out["attempts"] == 2,
        f"attempts={timed_out['attempts']}",
    )
    check(
        "the retry is RECORDED, with the first attempt's own elapsed time",
        timed_out["retried"] is True
        and isinstance(timed_out.get("first_attempt_sec"), float),
        f"retried={timed_out['retried']}, "
        f"first_attempt_sec={timed_out.get('first_attempt_sec')}",
    )


def probe_a_genuine_failure_is_never_retried() -> None:
    """PART 4's bound: a non-zero exit is a VERDICT, and a verdict is not re-rolled."""
    audit = _audit_module()
    failed = audit.run_gate(["/bin/sh", "-c", "exit 3"], REPO, 30.0)
    check(
        "a genuine FAIL keeps its own exit code and is NEVER retried",
        failed["exit_code"] == 3
        and failed["attempts"] == 1
        and failed["retried"] is False
        and failed["unknown"] is False,
        f"exit_code={failed['exit_code']}, attempts={failed['attempts']}, "
        f"retried={failed['retried']}",
    )


def probe_a_real_timeout_lands_in_unknown_end_to_end(timed_out: dict) -> None:
    """PART 2, end to end: a REAL timed-out result, judged by the REAL verdict.

    This is the leg the acceptance criteria name -- a probe proving a timed-out gate
    lands in UNKNOWN -- driven from the runner's own output rather than from a fixture.
    """
    audit = _audit_module()
    verdict = audit.judge_gates([_synthetic_gate(True, False), timed_out])
    check(
        "a real timed-out gate forces UNKNOWN, never DEGRADED",
        verdict.status == "UNKNOWN",
        verdict.status,
    )
    check(
        "the timed-out gate is counted in NO pass total",
        verdict.all_known_pass is True and verdict.examined == 1,
        f"all_known_pass={verdict.all_known_pass}, examined={verdict.examined}",
    )
    check(
        "the timed-out gate is not filed as a failure either",
        verdict.failed == [] and len(verdict.unknown) == 1,
        f"failed={len(verdict.failed)}, unknown={len(verdict.unknown)}",
    )
    check(
        "a timed-out gate is NOT healthy -- no verdict is not a green",
        not verdict.healthy,
        repr(verdict.healthy),
    )
    line = audit.render_status_line(verdict)
    check(
        "the headline renders UNKNOWN as loudly as FAIL",
        "UNKNOWN" in line and "NOT a green" in line and "HEALTHY" not in line,
        line[:130],
    )
    check(
        "the headline states the population it reports over",
        f"1 of {verdict.total}" in line,
        line[:130],
    )


def probe_the_three_states_are_distinct_and_a_failure_outranks_unknown() -> None:
    """PART 2: three states, three DISTINCT renderings -- and a measured FAIL wins."""
    audit = _audit_module()
    green = audit.judge_gates([_synthetic_gate(True, False)])
    degraded = audit.judge_gates(
        [_synthetic_gate(True, False), _synthetic_gate(False, False)]
    )
    unknown = audit.judge_gates(
        [_synthetic_gate(True, False), _synthetic_gate(False, True)]
    )
    check(
        "every gate that ran to a verdict passed -> GREEN",
        green.status == "GREEN",
        green.status,
    )
    check("a gate that FAILED -> DEGRADED", degraded.status == "DEGRADED", degraded.status)
    check(
        "a gate that returned NO verdict -> UNKNOWN",
        unknown.status == "UNKNOWN",
        unknown.status,
    )
    check(
        "the three states render as three DISTINCT headlines",
        len({audit.render_status_line(v) for v in (green, degraded, unknown)}) == 3,
        " / ".join(audit.render_status_line(v)[:34] for v in (green, degraded, unknown)),
    )
    check(
        "GREEN is the only state that is healthy",
        green.healthy is True and degraded.healthy is False and not unknown.healthy,
    )
    both = audit.judge_gates(
        [
            _synthetic_gate(True, False),
            _synthetic_gate(False, False),
            _synthetic_gate(False, True),
        ]
    )
    check(
        "a measured FAIL outranks an UNKNOWN -- a statement beats its absence",
        both.status == "DEGRADED" and len(both.unknown) == 1,
        both.status,
    )
    check(
        "the UNKNOWN gates are still NAMED beside the failure, never dropped",
        f"{len(both.unknown)} more" in audit.render_status_line(both),
        audit.render_status_line(both)[:130],
    )


def probe_a_skipped_suite_is_still_no_verdict() -> None:
    """The #28 law survives the third state: no gates run means NO verdict, not a green."""
    audit = _audit_module()
    verdict = audit.judge_gates([], gates_ran=False)
    check(
        "a skipped suite reports no status at all", verdict.status is None, repr(verdict.status)
    )
    check("a skipped suite is not healthy", verdict.healthy is None, repr(verdict.healthy))
    check(
        "a skipped suite keeps its own headline",
        "GATES SKIPPED" in audit.render_status_line(verdict),
        audit.render_status_line(verdict),
    )


def probe_the_fail_line_cause_is_read_by_one_predicate() -> None:
    """PART 1(c): the cause is read by ONE helper, so the stdout and markdown surfaces
    cannot disagree about which line states it (one field, one predicate)."""
    audit = _audit_module()
    check(
        "the cause is the LAST non-blank line, not the first",
        audit.last_reported_line("first line\n\n  the cause  \n") == "the cause",
        repr(audit.last_reported_line("first line\n\n  the cause  \n")),
    )
    check(
        "the cause is collapsed onto one line",
        audit.last_reported_line("x\n  a   b  \n") == "a b",
        repr(audit.last_reported_line("x\n  a   b  \n")),
    )
    check(
        "an output-less gate yields NO cause rather than a blank one",
        audit.last_reported_line("") == "" and audit.last_reported_line("\n \n") == "",
    )
    check(
        "the cause is BOUNDED, so a chatty gate cannot flood the line",
        len(audit.last_reported_line("z" * 900)) == 200,
        str(len(audit.last_reported_line("z" * 900))),
    )

def probe_a_script_shaped_failure_records_its_count() -> None:
    """Issue #158: the kit ships TWO output shapes and they summarise in DIFFERENT places.

    A SCRIPT-shaped gate prints `N problem(s)` FIRST and its violations after, so keeping
    only the LAST line discards the count and keeps one arbitrary specimen -- measured on
    `tests/test_ledger_schema.py`, where SIX problems were recorded as a single truncated
    tail violation. A PYTEST-shaped gate writes its reason LAST and must be UNCHANGED.
    """
    audit = _audit_module()
    script = (
        "ledger schema: 6 problem(s) in /repo/evidence/ledger.jsonl\n"
        "  line 15: n=15 (#41) — actor 'worker' is not authorized\n"
        "  line 95: n=95 (#101) — malformed telemetry\n"
    )
    cause = audit.reported_cause(script)
    check(
        "a script-shaped failure records its COUNT, not only a tail specimen",
        "6 problem(s)" in cause,
        repr(cause),
    )
    check(
        "the count is kept AND a specimen follows it",
        cause.startswith("ledger schema: 6 problem(s)") and "n=95" in cause,
        repr(cause),
    )
    check(
        "the OLD predicate loses the count on this shape — the defect, reproduced",
        "6 problem(s)" not in audit.last_reported_line(script),
        repr(audit.last_reported_line(script)),
    )
    pytest_shaped = (
        "=================== FAILURES ===================\n"
        "E   assert 1 == 2\n"
        "=========== 1 failed, 31 passed in 1.42s ===========\n"
    )
    check(
        "a pytest-shaped failure is UNCHANGED — its reason is already last",
        audit.reported_cause(pytest_shaped) == audit.last_reported_line(pytest_shaped),
        repr(audit.reported_cause(pytest_shaped)),
    )
    check(
        "the cause is BOUNDED on both shapes",
        len(audit.reported_cause(script)) <= audit.GATE_CAUSE_LIMIT,
        str(len(audit.reported_cause(script))),
    )
    check(
        "an output-less gate yields NO cause rather than a blank one",
        audit.reported_cause("") == "",
        repr(audit.reported_cause("")),
    )
    check(
        "a count line that IS the last line is not duplicated",
        audit.reported_cause("only 2 problem(s) here\n") == "only 2 problem(s) here",
        repr(audit.reported_cause("only 2 problem(s) here\n")),
    )

def probe_the_note_is_attached_once_for_every_surface() -> None:
    """The cause is computed ONCE and read by all three surfaces (#158).

    A cause visible only via `--json` is a cause the reader does not have; a cause derived
    SEPARATELY per surface is two answers to one question. `attach_gate_causes` is the one
    call, and the JSON therefore carries the COUNT a script-shaped gate prints first.
    """
    audit = _audit_module()
    roster = [
        {"cmd": "passing", "passed": True, "unknown": False, "duration_sec": 1.0,
         "stdout": "all good"},
        {"cmd": "script-shaped", "passed": False, "unknown": False, "duration_sec": 1.0,
         "stdout": "ledger schema: 6 problem(s) in /repo/x\n  line 15: n=15 (#41)\n"},
        {"cmd": "empty-fail", "passed": False, "unknown": False, "duration_sec": 1.0,
         "stdout": ""},
    ]
    audit.attach_gate_causes(roster)
    check(
        "a PASSING gate carries no note",
        "note" not in roster[0],
        repr(roster[0].get("note")),
    )
    check(
        "a failing gate carries the note, with its COUNT",
        "6 problem(s)" in roster[1].get("note", ""),
        repr(roster[1].get("note")),
    )
    check(
        "the note is BOUNDED, so it cannot grow the table cell",
        len(roster[1]["note"]) <= audit.GATE_CAUSE_LIMIT,
        str(len(roster[1]["note"])),
    )
    check(
        "a silent failing gate carries an EMPTY note, never an absent key",
        roster[2].get("note") == "",
        repr(roster[2].get("note")),
    )

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
    print("  synthetic probes — direction 4, law -> registered")
    probe_a_law_named_unregistered_mechanism_is_named()
    probe_a_registered_law_named_mechanism_is_clean()
    probe_the_skill_arm_alone_names_an_unregistered_mechanism()
    probe_a_prose_mention_is_not_a_mechanism()
    probe_only_the_prevented_by_column_is_read()
    probe_a_dead_reference_is_reported()
    probe_an_unreadable_law_source_fails_rather_than_passing()
    probe_the_law_coverage_predicate_states_its_scope()
    print("  synthetic probes — direction 5, registered -> CAN RUN")
    probe_a_pytest_style_target_under_a_script_runner_is_named()
    probe_the_same_target_under_the_pytest_runner_is_clean()
    probe_a_script_style_target_under_the_pytest_runner_is_not_reported()
    probe_a_file_with_a_main_guard_is_still_pytest_form()
    probe_the_runner_is_read_from_argv_not_guessed_from_the_target()
    probe_an_absent_target_is_skipped_and_named_not_double_reported()
    probe_a_tool_invocation_carries_no_target_shape()
    probe_registered_entries_is_a_projection_of_one_scan()
    probe_a_target_whose_name_contains_pytest_is_not_misread_as_the_runner()
    probe_the_runner_form_predicate_states_its_one_way_bound()
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
    print("  live tree — direction 4")
    probe_the_live_law_coverage_is_clean()
    print("  live tree — direction 5")
    probe_the_live_runner_forms_are_clean()
    print("  synthetic probes — the declared basis is RESOLVED (#125)")
    probe_the_declared_basis_legs_are_resolved()
    probe_an_unresolvable_revision_is_reported_never_clean()
    probe_a_tree_without_a_resolvable_head_is_not_read_as_clean()
    probe_a_malformed_entry_still_raises()
    probe_the_margin_law_still_raises()
    print("  synthetic probes — #93: a timeout is UNKNOWN, never a 0.0s FAIL")
    timed_out = probe_a_timeout_carries_true_elapsed_and_a_distinct_exit_code()
    probe_the_retry_is_bounded_and_recorded(timed_out)
    probe_a_genuine_failure_is_never_retried()
    probe_a_real_timeout_lands_in_unknown_end_to_end(timed_out)
    probe_the_three_states_are_distinct_and_a_failure_outranks_unknown()
    probe_a_skipped_suite_is_still_no_verdict()
    probe_the_fail_line_cause_is_read_by_one_predicate()
    probe_a_script_shaped_failure_records_its_count()
    probe_the_note_is_attached_once_for_every_surface()

    print("  live manifest — the declared revisions, swept")
    probe_the_live_sweep_states_its_own_account()

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
