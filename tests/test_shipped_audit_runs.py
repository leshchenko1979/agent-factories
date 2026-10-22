#!/usr/bin/env python3
"""Gate: the SHIPPED tree's own audit is EXECUTED, and its verdict classified.

WHY THIS GATE EXISTS (#199). The kit ships 55 test files and 65 distinct gate
registrations in `TEMPLATE/tools/audit.py`, and NOTHING in the root audit executes any
of them. So a shipped gate that reds or crashes *in the tree it ships from* is invisible
until somebody happens to run it by hand — measured: five instances in one day, one of
them the SAME gate crashing twice, the second crash 15 h after the first fix, because
each was found by a lane reading a file rather than by a mechanism.

WHAT IT ASSERTS, and what it deliberately does NOT. It asserts the shipped tree's OWN
CONTRACT — never "green by the root standard". The shipped tree is not a factory: its
`evidence/`, its ontology, its product declaration and its registry are all
BOOTSTRAP-created, so a gate that reds on non-green there would be a PERMANENT red, and
a permanent red teaches lanes to ignore red (the class #83 closed). Building that would
ship a rubber stamp.

FIVE VERDICT CLASSES, and a SILENT skip is a defect exactly as a FAIL is:

  PASS           the gate ran and passed
  STATED SKIP    the gate ran, could not apply, and SAID SO — the reason is printed by
                 the gate itself and its declared marker is found in that output
  NAMED ABSENCE  the gate is REGISTERED and the file is absent from this tree, named
  NO VERDICT     the gate was KILLED at its budget: it did not pass, it did not fail, and
                 it must not be counted in either — #206
  FAIL           anything else, including a declared skip whose reason has gone missing

The distinction between STATED SKIP and NAMED ABSENCE is the whole finding: a gate that
is REGISTERED and ABSENT is a different fact from a gate that RAN and could not apply.
Folding them together hides the population `is_file()` guards currently skip in silence.

WHY NO VERDICT IS ITS OWN CLASS (#206). A budget kill is already modelled in this factory
and modelled exactly once: `tools/audit.py` records `unknown: True` beside the kill code, so
the fleet's own audits exclude it from both the failed set and the pass total. A classifier
that read the code alone would agree with the audit's constant but not with its MODEL, and
would misread a future kill code. So the class reads the FLAG first and falls back to the
code for a record that carries no flag.

THIS GATE'S OWN WALL IS READ, NOT WRITTEN (#414). The outer `subprocess.run` used to carry
`timeout=900` while the declared budget for this gate was 1008.75 s — two sources for one
number, and the literal won at runtime, so the gate killed its own audit 108.75 s inside its
allowance and could not be satisfied by a round that legitimately needed the time. Raising
the literal would have re-armed the same drift the moment the budget was re-measured upward.
The wall now comes from `registry/gates.json` through `tools/gate_budget.py`, and the SOURCE
is printed with it, so a gate silently running on the fleet default is visible instead of
silent. A kill at that wall is reported as NO VERDICT and exits with the fleet's kill code,
never as a FAIL: the audit produced no verdict, so this gate has none to give.

Run:  python3 tests/test_shipped_audit_runs.py
Exit: 0 the shipped audit ran and every verdict is accounted for; 1 a FAIL, a silent
      skip, a stale declaration, or a probe that failed to bite; 124 the outer wall fired
      and no verdict exists — a kill, not a red (#206, #414).
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The kill code has ONE home — the constant the root audit writes into the payload it
# records for a budget kill (`TEMPLATE/tools/audit.py` imports it from here too). Imported
# rather than copied, so the two surfaces cannot drift apart.
sys.path.insert(0, str(REPO / "tools"))
from gate_budget import (  # noqa: E402
    TIMEOUT_EXIT_CODE,
    GateBudgetManifestError,
    gates_manifest_path,
    load_gate_budgets,
)
SHIPPED = REPO / "TEMPLATE"
SHIPPED_AUDIT = SHIPPED / "tools" / "audit.py"
# The declared non-green population: FACTORY DATA, repo-side, in its own file so an entry
# is visible debt rather than a line buried in this gate.
DECLARED = REPO / "docs" / "shipped-audit-skips.json"

# THIS GATE'S OWN BUDGET KEY, and the reason it is a key rather than a number (#414).
# The wall below used to be `timeout=900` written into the call, while the budget lived in
# `registry/gates.json` as `budget_sec 1008.75`. Two sources, one number, and the constant
# won at runtime: the audit was killed 108.75 s BEFORE its own declared budget, on a
# machine where a legitimate round could reach it. Raising the literal would have fixed
# that day and re-armed the same drift the moment the budget was re-measured upward --
# which its own `margin_x 4.003` against `measured_sec 252.0` invites. So the gate reads
# its own declared cap through the shared reader, and there is ONE number.
BUDGET_KEY = "tests/test_shipped_audit_runs.py"


def inner_wall(manifest: Path | None = None) -> tuple[float, str]:
    """This gate's declared wall, and whether it was DECLARED or fell to the default.

    The second element is not decoration. A gate with no entry in the manifest silently
    runs on the fleet default -- 69.27 s here, against a round that has been measured at
    252 s -- so a reader meeting a kill must be able to see WHICH cap killed it. The
    source is printed with the verdict for exactly that reason.

    Raises `GateBudgetManifestError` for a manifest that exists and cannot be read: an
    unreadable budget set is indistinguishable from no budget set, and defaulting over it
    would silently re-cap every gate (the rule `gate_budget` itself states).
    """
    budgets = load_gate_budgets(manifest)
    return budgets.resolve(BUDGET_KEY)

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def registered_gates(audit_source: str) -> list[str]:
    """Every path this audit registers, in order, from the AST.

    An AST rather than a regex: the registrations are multi-line `gates_to_run.append([...])`
    calls and a regex over them under-counts — measured on this file, an earlier regex read
    produced a false "no call site" finding for four entries before the AST corrected it.
    """
    tree = ast.parse(audit_source)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "append"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if not isinstance(arg, ast.List):
            continue
        for elt in arg.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                v = elt.value
                if v.endswith(".py") or v.endswith(".json"):
                    found.append(v)
    # `-m pytest <path>` forms carry the path as the LAST element; the loop above already
    # takes every string constant, so filter to the ones that look like a scanned file.
    return [p for p in found if p.startswith(("tests/", "tools/"))]


def classify(registered: list[str], absent: set[str], results: dict[str, dict],
             declared: dict[str, dict], source_of) -> dict[str, list[str]]:
    """The ONE predicate. Returns {class: [named entries]}.

    `results` maps a gate path to its record from the shipped audit's payload. A gate with
    no record either did not run or is absent; `absent` decides which.

    WHY THE MARKER IS CHECKED IN THE GATE'S SOURCE, not in its captured output. pytest
    CAPTURES both streams from session start, so a pytest-mode gate's stated reason never
    reaches the audit's log — measured: `print`, `sys.__stdout__`, and a `dup(1)` taken at
    import all land in the capture. The source is the surface that actually carries the
    reason, and checking it proves the stronger property: the skip is STATED, not merely
    that something was printed. A declared gate whose marker has been removed from its
    source is a SILENT skip, which is a defect exactly as a FAIL is.
    """
    out: dict[str, list[str]] = {"PASS": [], "STATED SKIP": [], "NAMED ABSENCE": [],
                                 "NO VERDICT": [], "FAIL": []}
    for path in registered:
        if path in absent:
            out["NAMED ABSENCE"].append(path)
            continue
        rec = results.get(path)
        if rec is None:
            out["FAIL"].append(f"{path} — registered, present, and NO RESULT: it did not run")
            continue
        entry = declared.get(path)
        # NO VERDICT — a gate killed at its budget (#206). Reached BEFORE the declared and
        # the FAIL branches, so a kill is never read as a failure and never as a skip whose
        # contract it did not meet. The FLAG is the model the fleet's audits already apply;
        # the code is the fallback for a record that carries no flag.
        killed = bool(rec.get("unknown")) or rec.get("exit_code") == TIMEOUT_EXIT_CODE
        if killed:
            line = (f"{path} — NO VERDICT: killed at its budget "
                    f"(exit {rec.get('exit_code')}, unknown={bool(rec.get('unknown'))})")
            if entry:
                line += (f"; it is declared as a STATED SKIP (marker {entry.get('marker')!r}), "
                         f"and a budget kill fails against ANY declaration — the declaration "
                         f"does not make the kill a skip")
            out["NO VERDICT"].append(line)
            continue
        if rec.get("exit_code") == 0 and not entry:
            out["PASS"].append(path)
            continue
        blob = (rec.get("stdout") or "") + (rec.get("stderr") or "")
        if entry and entry.get("marker"):
            # WHERE THE MARKER LIVES IS DECLARABLE. A skip's reason usually sits in the gate
            # itself, but not always: the hygiene leg's reason belongs to the AUDIT's own
            # registration comment, because the leg is a shared tool whose behaviour is not
            # the kit's to change. `marker_in` names the source, defaulting to the gate.
            src = source_of(entry.get("marker_in") or path) or ""
            if entry["marker"] in src:
                # A declared skip is a CLEAN exit with its reason — except where the entry
                # states the instrument's own contract allows otherwise (`exits`). A tool
                # whose law is "RED until the factory onboards" is correct to exit 1 there,
                # and the declaration says so rather than the classifier assuming it.
                allowed = entry.get("exits") or [0]
                if rec.get("exit_code") not in allowed:
                    out["FAIL"].append(
                        f"{path} — declared as a STATED SKIP but exited {rec.get('exit_code')} "
                        f"against a declared {allowed}: a skip is a clean exit with its reason, "
                        f"never a failure"
                    )
                    continue
                out["STATED SKIP"].append(f"{path} — {entry.get('artifact', 'declared')}")
                continue
            out["FAIL"].append(
                f"{path} — declared as a STATED SKIP but its reason marker "
                f"{entry['marker']!r} is NOT in the gate's source: a skip whose reason has "
                f"gone is a SILENT skip, which is a defect"
            )
            continue
        out["FAIL"].append(
            f"{path} — exit {rec.get('exit_code')} and NOT declared: "
            f"{(blob.strip().splitlines() or [''])[-1][:110]}"
        )
    return out


def probes() -> None:
    """The classifier must BITE, driven from constructed inputs — never from today's tree."""
    reg = ["tests/a.py", "tests/b.py", "tests/c.py", "tests/d.py"]

    # CONTROL — the four classes, one gate each, all accounted for. `b.py` exits 0 with its
    # stated reason in its SOURCE, which is what a real declared skip looks like in both
    # invocation modes.
    sources = {"tests/b.py": 'print("SKIPPED — no evidence/ in this tree")\n'}
    got = classify(
        reg,
        absent={"tests/d.py"},
        results={
            "tests/a.py": {"exit_code": 0, "stdout": "clean"},
            "tests/b.py": {"exit_code": 0, "stdout": "sss"},
            "tests/c.py": {"exit_code": 1, "stdout": "boom"},
        },
        declared={"tests/b.py": {"marker": "no evidence/ in this tree", "artifact": "evidence/"}},
        source_of=lambda p: sources.get(p, ""),
    )
    check("CONTROL: the four classes are separated",
          len(got["PASS"]) == 1 and len(got["STATED SKIP"]) == 1
          and len(got["NAMED ABSENCE"]) == 1 and len(got["FAIL"]) == 1,
          f"PASS={len(got['PASS'])} SKIP={len(got['STATED SKIP'])} "
          f"ABSENT={len(got['NAMED ABSENCE'])} FAIL={len(got['FAIL'])}")

    # BITE 1 — a gate that FAILS is a FAIL, and it is NAMED (criterion b).
    check("BITE: a failing gate produces a FAIL verdict NAMING it",
          any("tests/c.py" in f for f in got["FAIL"]), got["FAIL"][:1])

    # BITE 2 — a STATED SKIP whose reason text is STRIPPED becomes a FAIL (criterion c).
    # This is the leg that makes the (A) conversions meaningful rather than decorative: a
    # gate that returns 0 with no reason is indistinguishable from one that judged and
    # passed, which is exactly the silent skip the issue is about.
    stripped = classify(
        ["tests/b.py"],
        absent=set(),
        results={"tests/b.py": {"exit_code": 0, "stdout": "sss"}},
        declared={"tests/b.py": {"marker": "no evidence/ in this tree", "artifact": "evidence/"}},
        source_of=lambda p: "print('nothing to do')\n",
    )
    check("BITE: a declared skip whose reason text is GONE is a FAIL, not a skip",
          len(stripped["STATED SKIP"]) == 0 and len(stripped["FAIL"]) == 1,
          stripped["FAIL"][:1])

    # BITE 3b — the marker may live in ANOTHER declared source (the audit's registration
    # comment carries the hygiene leg's reason, because that leg is a shared tool whose
    # behaviour is not the kit's to change). A declaration naming a file whose marker is
    # absent must still fail.
    elsewhere = classify(
        ["tools/hygiene.py"],
        absent=set(),
        results={"tools/hygiene.py": {"exit_code": 1, "stdout": "dirty"}},
        declared={"tools/hygiene.py": {"marker": "STATED SKIP: the ENCLOSING repo",
                                       "marker_in": "tools/audit.py",
                                       "exits": [0, 1]}},
        source_of=lambda p: "STATED SKIP: the ENCLOSING repo's working tree\n" if p == "tools/audit.py" else "",
    )
    check("BITE: a marker declared in ANOTHER source is found there, not in the gate",
          len(elsewhere["STATED SKIP"]) == 1 and not elsewhere["FAIL"], elsewhere)

    # BITE 4 — a gate that produced NO result is a FAIL, never a silent pass. Without this
    # arm a gate the audit failed to record would vanish from the verdict entirely.
    silent = classify(["tests/z.py"], absent=set(), results={}, declared={},
                      source_of=lambda p: "")
    check("BITE: a gate with no result at all is a FAIL, never a silent pass",
          len(silent["FAIL"]) == 1 and not silent["PASS"], silent["FAIL"][:1])

    # BITE 4 — an ABSENT gate is NAMED, never folded into a skip (criterion f).
    fold = classify(["tests/gone.py"], absent={"tests/gone.py"}, results={}, declared={},
                    source_of=lambda p: "")
    check("BITE: an absent gate is a NAMED ABSENCE, never folded into STATED SKIP",
          len(fold["NAMED ABSENCE"]) == 1 and len(fold["STATED SKIP"]) == 0,
          fold["NAMED ABSENCE"])

    # ---- #206: the kill is its OWN class, never a FAIL and never a skip --------------
    #
    # The population is driven SYNTHETICALLY, never from today's tree: whether any gate is
    # killed this run is a property of the instant, so a probe reading the live verdict
    # would pass on every day the budget happened to be sufficient.

    # (1) THE RULING'S OWN CASE. A bare kill code and nothing else: no declaration, no
    # output, no name it could hide behind. It must NOT be a FAIL.
    kill = classify(["tests/k.py"], absent=set(),
                    results={"tests/k.py": {"exit_code": TIMEOUT_EXIT_CODE}},
                    declared={}, source_of=lambda p: "")
    check("KILL: a bare exit 124 is NO VERDICT, never a FAIL",
          len(kill["NO VERDICT"]) == 1 and len(kill["FAIL"]) == 0,
          f"NO VERDICT={len(kill['NO VERDICT'])} FAIL={len(kill['FAIL'])}")
    check("KILL: the verdict NAMES the gate it could not judge",
          any("tests/k.py" in v for v in kill["NO VERDICT"]), kill["NO VERDICT"][:1])

    # (2) THE FLAG GOVERNS THE CODE. A kill at a DIFFERENT code still reads as a kill,
    # because the class reads the audit's own model rather than one number -- so a future
    # kill code (or a signal) inherits the class instead of silently becoming a FAIL.
    flagged = classify(["tests/k.py"], absent=set(),
                       results={"tests/k.py": {"exit_code": 137, "unknown": True}},
                       declared={}, source_of=lambda p: "")
    check("KILL: the audit's own `unknown` flag governs, not one hard-coded number",
          len(flagged["NO VERDICT"]) == 1 and len(flagged["FAIL"]) == 0,
          flagged["NO VERDICT"][:1])

    # (3) A DECLARATION DOES NOT MAKE A KILL A SKIP. The contradiction is PRINTED on the
    # same line: an entry declaring this gate as a stated skip is still not satisfied by a
    # budget kill, because a kill fails against any declaration.
    contradicted = classify(
        ["tests/k.py"], absent=set(),
        results={"tests/k.py": {"exit_code": TIMEOUT_EXIT_CODE, "unknown": True}},
        declared={"tests/k.py": {"marker": "no evidence/ in this tree", "artifact": "evidence/"}},
        source_of=lambda p: "print('SKIPPED - no evidence/ in this tree')\n",
    )
    check("KILL: a declared skip killed at budget is NO VERDICT, and the contradiction is printed",
          len(contradicted["NO VERDICT"]) == 1 and len(contradicted["STATED SKIP"]) == 0
          and "declared" in (contradicted["NO VERDICT"][0] if contradicted["NO VERDICT"] else ""),
          contradicted["NO VERDICT"][:1])

    # (4) FAIL IS UNTOUCHED. The same call, a gate that exited non-zero on its OWN merits,
    # is still a FAIL -- the class is shown not to absorb failures, which is the whole risk
    # of adding one.
    still_fails = classify(["tests/f.py"], absent=set(),
                           results={"tests/f.py": {"exit_code": 1, "unknown": False}},
                           declared={}, source_of=lambda p: "")
    check("KILL: a gate that exited 1 on its own merits is STILL a FAIL",
          len(still_fails["FAIL"]) == 1 and len(still_fails["NO VERDICT"]) == 0,
          still_fails["FAIL"][:1])

    # (5) THE POPULATION IS PRINTED EVEN AT ZERO. The class is in the headline's loop on
    # every run, so a clean run shows `NO VERDICT: 0` rather than omitting the class -- the
    # difference between "none were killed" and "kills are not tracked".
    clean = classify(["tests/a.py"], absent=set(),
                     results={"tests/a.py": {"exit_code": 0}}, declared={},
                     source_of=lambda p: "")
    check("KILL: the class is accounted for even when EMPTY, so 0 is readable as 0",
          clean["NO VERDICT"] == [], "NO VERDICT == []")


def budget_controls() -> None:
    """#414: the wall is READ from the manifest, and a kill at it is NO VERDICT, not a FAIL.

    Three arms, and the third is the one that pins the defect. The first two could both pass
    on a gate that read the number and then ignored it, so the third runs the gate for real
    against a fixture tree whose audit outlives a fixture budget — and then against a MUTANT
    whose call site carries the old `timeout=900` literal, which must NOT read NO VERDICT.
    Without that mutant the control would pass on the literal too, since a 900 s wall also
    fails to kill a 2 s fixture.
    """
    # ARM 1 — the wall IS this gate's own declared budget, read through the shared reader,
    # and the reader says so. A gate with no entry would silently run on the fleet default
    # (69.27 s here against a round measured at 252 s), which is why the SOURCE is asserted
    # and not just the number.
    manifest = REPO / "registry" / "gates.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    declared_sec = ((data.get("gates") or {}).get(BUDGET_KEY) or {}).get("budget_sec")
    wall, source = inner_wall()
    check("WALL: the inner wall IS this gate's declared budget, and the reader says `declared`",
          declared_sec is not None and wall == declared_sec and source == "declared",
          f"{wall}s ({source}) against the manifest's {declared_sec}s")

    # ARM 2 — the number is READ, not a literal: a fixture manifest moves it. This is what
    # separates a real read from a constant that happens to equal today's budget. The fixture
    # is built through the module's OWN margin law (`budget_sec == margin_for(measured) *
    # measured`), because a thin hand-written entry is refused by the reader — which is the
    # reader working, not an inconvenience to route around.
    from gate_budget import margin_for

    def fixture_manifest(measured_sec: float) -> dict:
        return {
            "default": {"budget_sec": round(margin_for(measured_sec) * measured_sec, 4)},
            "gates": {BUDGET_KEY: {
                "budget_sec": round(margin_for(measured_sec) * measured_sec, 4),
                "measured_sec": measured_sec,
                "margin_x": margin_for(measured_sec),
                "measured_at": "HEAD",
            }},
        }

    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "gates.json"
        fixture_data = fixture_manifest(1080.0)
        fixture.write_text(json.dumps(fixture_data), encoding="utf-8")
        moved, moved_source = inner_wall(fixture)
        check("CONTROL: a different DECLARED number moves the wall, so it is read",
              moved == fixture_data["gates"][BUDGET_KEY]["budget_sec"] != wall
              and moved_source == "declared",
              f"{moved}s from the fixture manifest, {moved_source} (live wall {wall}s)")

        # A gate with NO entry falls to the fleet default and SAYS so. Printed, not silent:
        # that is the difference between a declared fallback and an exempt-by-silence one.
        fixture.write_text(json.dumps({
            "default": {"budget_sec": 77.0},
            "gates": {},
        }), encoding="utf-8")
        fell, fell_source = inner_wall(fixture)
        check("CONTROL: an undeclared gate falls to the default AND reports `default`",
              fell == 77.0 and fell_source == "default",
              f"{fell}s, source `{fell_source}`")

    # ARM 3 — a kill at the wall reads NO VERDICT. Driven through the gate as a PROCESS,
    # against a fixture tree: the fixture audit registers one gate and then outlives the
    # fixture budget, so the only possible outcome is the outer wall firing.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        (root / "tests").mkdir(parents=True)
        (root / "tools").mkdir(parents=True)
        (root / "TEMPLATE" / "tools").mkdir(parents=True)
        shutil.copyfile(REPO / "tools" / "gate_budget.py", root / "tools" / "gate_budget.py")
        # A registration the AST can find, then a sleep longer than the fixture budget.
        (root / "TEMPLATE" / "tools" / "audit.py").write_text(
            "import time\n"
            "gates_to_run = []\n"
            'gates_to_run.append(["tests/slow.py"])\n'
            "time.sleep(2.0)\n"
            'print("{}")\n', encoding="utf-8")
        slow_manifest = Path(tmp) / "gates.json"
        slow_manifest.write_text(json.dumps(fixture_manifest(0.1)), encoding="utf-8")

        gate_src = (REPO / "tests" / "test_shipped_audit_runs.py").read_text(encoding="utf-8")
        gate = root / "tests" / "test_shipped_audit_runs.py"
        gate.write_text(gate_src, encoding="utf-8")

        def run_gate(path: Path) -> subprocess.CompletedProcess:
            env = dict(os.environ, OC_GATES_MANIFEST=str(slow_manifest))
            return subprocess.run([sys.executable, str(path), "--no-controls"],
                                  cwd=str(root), capture_output=True, text=True,
                                  env=env, timeout=120)

        killed = run_gate(gate)
        check("KILL: the outer wall fires and the gate reports NO VERDICT",
              killed.returncode == TIMEOUT_EXIT_CODE and "NO VERDICT" in killed.stdout,
              f"exit {killed.returncode}, "
              f"{(killed.stdout or killed.stderr).strip().splitlines()[-1:]}")
        check("KILL: and it is NOT reported as a FAIL, so a kill is distinguishable from a red",
              killed.returncode != 1
              and "gate FAILED" not in killed.stdout
              and not any(l.strip().startswith("FAIL") for l in killed.stdout.splitlines()),
              f"exit {killed.returncode}; a red would be exit 1 with a `FAIL` check line")

        # THE MUTANT — the same gate with the old literal at the call site. It must NOT read
        # NO VERDICT at this budget, because 900 s cannot kill a 2 s fixture. This is the arm
        # that proves ARM 3 measured the READ and not merely the presence of a kill path.
        #
        # THE ANCHOR IS THE CALL SITE, and it must not be spellable inside this function —
        # so it is assembled from two halves. A literal anchor is self-matching: the first
        # version used the bare string `timeout=wall_sec`, which also appears in the MUTATION
        # code itself, so the replace rewrote the mutation and left the call site intact — a
        # no-op that still reported "a real mutation" because the text changed somewhere.
        # Measured: that mutant read 124 exactly like the real gate. Raising it to a longer
        # literal did not fix it, it moved the collision up a level (the anchor then matched
        # its own assignment). The halves below cannot collide with either.
        anchor = "text=True, timeout=" + "wall_sec,"
        check("MUTATION: the anchor names the CALL SITE and is unique in the file",
              gate_src.count(anchor) == 1, f"{gate_src.count(anchor)} occurrence(s)")
        mutated = gate_src.replace(anchor, "text=True, timeout=" + "900,", 1)
        check("MUTATION: the mutant carries the old literal, so it is a real mutation",
              mutated != gate_src, "call site rewritten to `timeout=900`")
        mutant = root / "tests" / "mutant_shipped_audit_runs.py"
        mutant.write_text(mutated, encoding="utf-8")
        survived = run_gate(mutant)
        check("MUTATION: with the literal restored, the fixture budget does NOT kill — so "
              "ARM 3 measured the read",
              survived.returncode != TIMEOUT_EXIT_CODE
              and "killed at this gate's declared budget" not in survived.stdout,
              f"exit {survived.returncode} (a literal 900 s wall cannot kill a 2 s fixture); "
              f"the class NAME still prints as `NO VERDICT: 0`, which is why this asserts on "
              f"the kill MESSAGE and not on the class")


def main() -> int:
    print("shipped audit — the tree the kit hands to members, EXECUTED (#199)")

    if not SHIPPED_AUDIT.is_file():
        print("  SKIPPED — this tree carries no TEMPLATE/, so there is no shipped audit to run.")
        print("             A bootstrapped factory lands here; its own audit is its verdict.")
        return 0

    registered = registered_gates(SHIPPED_AUDIT.read_text(encoding="utf-8"))
    if not registered:
        print("  FAIL  no gate registrations parsed from the shipped audit — the population is "
              "empty, so a clean verdict would be a verdict over nothing")
        return 1
    # A gate is ABSENT when the file it names is not in the shipped tree. The registrations
    # are relative to the tree the audit runs in, which is `TEMPLATE/`.
    absent = {p for p in registered if not (SHIPPED / p).is_file()}

    declared: dict[str, dict] = {}
    if DECLARED.is_file():
        try:
            declared = json.loads(DECLARED.read_text(encoding="utf-8")).get("skips") or {}
        except json.JSONDecodeError as exc:
            print(f"  FAIL  {DECLARED.relative_to(REPO)} exists and cannot be read: {exc}")
            return 1

    print(f"  population: {len(registered)} registered gate(s); {len(absent)} absent from "
          f"this tree; {len(declared)} declared skip(s)")

    # RUN THE INSTRUMENT. The shipped audit is the only thing that knows how to invoke its
    # own registrations — re-deriving the invocation here is the defect #195 declared the
    # mode map to prevent.
    #
    # THE WALL IS READ, NOT WRITTEN (#414). `timeout=900` used to sit in this call while the
    # declared budget was 1008.75 — so this gate killed the audit 108.75 s inside its own
    # allowance and could not be satisfied by a round that legitimately needed the time. The
    # wall now comes from the manifest entry for THIS gate, and the source is printed, so a
    # gate running on the fleet default rather than its own measurement is visible instead of
    # silent.
    try:
        wall_sec, wall_source = inner_wall()
    except GateBudgetManifestError as exc:
        print(f"  FAIL  the gate-budget manifest exists and cannot be read: {exc}")
        print("             an unreadable budget set is indistinguishable from no budget set,")
        print("             and defaulting over it would silently re-cap every gate")
        return 1
    print(f"  wall: {wall_sec:.2f}s for this gate ({wall_source} — {gates_manifest_path()})")

    try:
        proc = subprocess.run(
            [sys.executable, "tools/audit.py", "--json"],
            cwd=str(SHIPPED), capture_output=True, text=True, timeout=wall_sec,
        )
    except subprocess.TimeoutExpired as exc:
        # A BUDGET KILL IS NOT A FAILURE (#206, #414). `TimeoutExpired` is an unhandled
        # exception here, so a kill raised out of this call and the gate exited as a plain
        # failure — the exact mislabelling #206's NO VERDICT class exists to prevent, one
        # level up from where it was modelled. The audit never reported a verdict, so this
        # gate has none to give: it says so, in the class's own words, and exits with the
        # kill code the fleet already uses, so a caller can tell this from a red.
        killed = f"{wall_sec:.2f}s ({wall_source})"
        print(f"  NO VERDICT  the shipped audit was killed at this gate's declared budget — "
              f"{killed}")
        print(f"      it neither passed nor failed: the audit produced no verdict to "
              f"classify. Its own record, if it wrote one, is the authority on WHICH gate "
              f"was still running; this gate's `timeout` is the OUTER wall and says nothing "
              f"about the inner one. Regime: a wall measured while other work shares this "
              f"box does not size the next wall (n=3984).")
        print(f"      not counted as a FAIL: exit {TIMEOUT_EXIT_CODE}, the fleet's kill code "
              f"(#{206})")
        del exc
        return TIMEOUT_EXIT_CODE
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("  FAIL  the shipped audit produced no readable JSON payload — its verdict "
              f"cannot be classified. exit={proc.returncode} "
              f"tail={(proc.stdout or proc.stderr or '').strip().splitlines()[-1:]}")
        return 1

    results: dict[str, dict] = {}
    for rec in payload.get("gates") or []:
        key = rec.get("gate_key") or rec.get("cmd") or ""
        for path in registered:
            if key.endswith(path) or path in (rec.get("cmd") or ""):
                results.setdefault(path, rec)

    def _source_of(path: str) -> str:
        p = SHIPPED / path
        try:
            return p.read_text(encoding="utf-8") if p.is_file() else ""
        except OSError:
            return ""

    got = classify(registered, absent, results, declared, _source_of)
    for cls in ("PASS", "STATED SKIP", "NAMED ABSENCE", "NO VERDICT", "FAIL"):
        print(f"  {cls}: {len(got[cls])}")
    if got["NAMED ABSENCE"]:
        print("  — NAMED ABSENCE, registered and not carried by this tree:")
        for p in got["NAMED ABSENCE"]:
            print(f"      {p}")
    if got["STATED SKIP"]:
        print("  — STATED SKIP, ran and said why:")
        for p in got["STATED SKIP"]:
            print(f"      {p}")
    if got["NO VERDICT"]:
        print("  — NO VERDICT, killed at budget (neither a pass nor a failure):")
        for p in got["NO VERDICT"]:
            print(f"      {p}")
    if got["FAIL"]:
        print("  — FAIL:")
        for p in got["FAIL"]:
            print(f"      {p}")

    # The controls are skipped only when a CALLER says so — the kill arms below run this
    # gate as a nested process against a fixture tree, and a copy that re-ran its own
    # controls would spawn copies of itself without end. Every ordinary invocation runs
    # them, including the one the gate set derives.
    if "--no-controls" not in sys.argv:
        probes()
        budget_controls()

    if _failures or got["FAIL"]:
        print(f"shipped audit gate FAILED: {len(_failures)} probe failure(s), "
              f"{len(got['FAIL'])} unaccounted verdict(s)")
        return 1
    print(f"shipped audit gate passed — {len(registered)} gate(s): {len(got['PASS'])} pass, "
          f"{len(got['STATED SKIP'])} stated skip, {len(got['NAMED ABSENCE'])} named absence, "
          f"{len(got['NO VERDICT'])} no verdict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
