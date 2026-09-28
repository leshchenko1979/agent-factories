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

FOUR VERDICT CLASSES, and a SILENT skip is a defect exactly as a FAIL is:

  PASS           the gate ran and passed
  STATED SKIP    the gate ran, could not apply, and SAID SO — the reason is printed by
                 the gate itself and its declared marker is found in that output
  NAMED ABSENCE  the gate is REGISTERED and the file is absent from this tree, named
  FAIL           anything else, including a declared skip whose reason has gone missing

The distinction between STATED SKIP and NAMED ABSENCE is the whole finding: a gate that
is REGISTERED and ABSENT is a different fact from a gate that RAN and could not apply.
Folding them together hides the population `is_file()` guards currently skip in silence.

Run:  python3 tests/test_shipped_audit_runs.py
Exit: 0 the shipped audit ran and every verdict is accounted for; 1 a FAIL, a silent
      skip, a stale declaration, or a probe that failed to bite.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHIPPED = REPO / "TEMPLATE"
SHIPPED_AUDIT = SHIPPED / "tools" / "audit.py"
# The declared non-green population: FACTORY DATA, repo-side, in its own file so an entry
# is visible debt rather than a line buried in this gate.
DECLARED = REPO / "docs" / "shipped-audit-skips.json"

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
    out: dict[str, list[str]] = {"PASS": [], "STATED SKIP": [], "NAMED ABSENCE": [], "FAIL": []}
    for path in registered:
        if path in absent:
            out["NAMED ABSENCE"].append(path)
            continue
        rec = results.get(path)
        if rec is None:
            out["FAIL"].append(f"{path} — registered, present, and NO RESULT: it did not run")
            continue
        entry = declared.get(path)
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
    proc = subprocess.run(
        [sys.executable, "tools/audit.py", "--json"],
        cwd=str(SHIPPED), capture_output=True, text=True, timeout=900,
    )
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
    for cls in ("PASS", "STATED SKIP", "NAMED ABSENCE", "FAIL"):
        print(f"  {cls}: {len(got[cls])}")
    if got["NAMED ABSENCE"]:
        print("  — NAMED ABSENCE, registered and not carried by this tree:")
        for p in got["NAMED ABSENCE"]:
            print(f"      {p}")
    if got["STATED SKIP"]:
        print("  — STATED SKIP, ran and said why:")
        for p in got["STATED SKIP"]:
            print(f"      {p}")
    if got["FAIL"]:
        print("  — FAIL:")
        for p in got["FAIL"]:
            print(f"      {p}")

    probes()

    if _failures or got["FAIL"]:
        print(f"shipped audit gate FAILED: {len(_failures)} probe failure(s), "
              f"{len(got['FAIL'])} unaccounted verdict(s)")
        return 1
    print(f"shipped audit gate passed — {len(registered)} gate(s): {len(got['PASS'])} pass, "
          f"{len(got['STATED SKIP'])} stated skip, {len(got['NAMED ABSENCE'])} named absence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
