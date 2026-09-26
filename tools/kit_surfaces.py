#!/usr/bin/env python3
"""The A.0 surface census — what a shipped tool declares, and what it may exempt.

WHY THIS IS A TOOL AND NOT A NOTE. Plan 2646d31a step 5 asks that "a re-run of the A.0
census reports every tool at 4 of 4 or carrying a declared exemption". A re-run has to be
a COMMAND. The figure was previously a table in a session plan, and two lanes produced
different numbers from it (2/15 and 3/15) because the PREDICATE lived in prose that each
reader completed differently. This file is the predicate, so the figure is derived.

THE FOUR SURFACES, with the predicate stated in the output rather than beside it:

  S1  a gate exercises the tool
  S2  TEMPLATE/BOOTSTRAP.md installs it
  S3  the law corpus names it
  S4  registry/kit.json carries it

THE TWO PREDICATE CORRECTIONS this instrument makes over the prose it replaces:

  S1  was "a file exactly named test_<stem>.py". The PROPERTY is "some gate exercises
      this tool". Six of fifteen tools have gates named for a FACET rather than the stem
      (audit -> test_audit_rates.py + test_audit_inflight_guard.py), so the old predicate
      scored a well-gated tool as having no gate at all. Corrected, 6 of 10 executables
      reached 4/4 where the old form scored 4 — and the difference is the predicate, not
      the tree.

  POPULATION  was "every TEMPLATE/tools/*.py" -- widened TWICE, for two different
      reasons. (i) by KIND: a closure module has no CLI, so it cannot
      carry an entry-point gate or be named in the law as an instrument. Splitting the
      population by KIND (executable | closure) is what makes the remaining gaps legible
      instead of alarming: 0 of 5 closure modules can reach 4/4 under an executable's
      predicate, and that is a shape error in the predicate, not 5 defects.
      (ii) by EXTENSION: `TEMPLATE/tools/questions` is extensionless, so a `*.py`
      glob could not see it and this census reported a clean population while an
      ungated instrument sat inside it (#180 criterion 2).

DECLARED EXEMPTIONS are in EXEMPTIONS below, each with the measurement that grounds it.
An exemption is a statement that a surface DOES NOT APPLY, and it must name why; a gap
with no exemption is a real gap and this tool exits 1 on it. The temptation this exists to
resist is declaring an exemption to close a gap that is genuinely uninstalled — which is
the silent-exclusion class, and the reason every exemption here cites a read.

Run:  python3 tools/kit_surfaces.py            # the census, with its verdict
      python3 tools/kit_surfaces.py --json     # machine-readable
Exit: 0 every tool 4/4 or exempt; 1 an undeclared gap exists.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

import kit_manifest

REPO = Path(__file__).resolve().parent.parent
T = REPO / "TEMPLATE"

SURFACES = ("S1", "S2", "S3", "S4")

# Historical records are EXCLUDED from the law corpus: a defect note that names a tool is
# not a declaration that the tool is mandated, and counting them would let a mention in a
# closed issue stand in for a law clause. Measured exclusion, stated so a reader can
# disagree with the boundary rather than with the number.
LAW_DIRS = ("skills", "docs")
LAW_HIST = re.compile(r"evidence/|proposals/|/history|rework|/plans/")

# A tool may be named in law under a hyphen variant (registry_attest <->
# factory-registry-attest), so both spellings count for S2/S3.
#
# DECLARED EXEMPTIONS. Key is (kind, surface); the value is WHY that surface cannot apply,
# with the measurement that grounds it. An entry here is a statement about the PREDICATE'S
# SHAPE, not a waiver for a missing file.
EXEMPTIONS: dict[tuple[str, str], str] = {
    ("closure", "S1"): (
        "a closure module has no CLI, so no gate can be named for it; the property is "
        "exercised-by-an-importing-gate instead, and the IMPORTS column prints the measured "
        "count per module. A zero there would be a real gap and this exemption would be a "
        "lie, which is why the column is printed rather than the claim asserted"
    ),
    ("closure", "S3"): (
        "the law names the INSTRUMENT, not each file of its full set; a closure module's "
        "declaration home is the entry path's closure row instead, so this exemption holds "
        "only while S2 does — a closure neither named in law nor installed by the entry "
        "path is a file nothing declares"
    ),
}

# Per-tool exemptions, for a surface that cannot apply to THIS tool and no other.
TOOL_EXEMPTIONS: dict[tuple[str, str], str] = {
    ("roadmap", "S2"): (
        "installed by the `roadmap` Domain add-on pack, not by bootstrap — "
        "docs/addons/domain/roadmap.md carries the install row (`shipped by the template`, "
        "a paired copy, with CANONICAL_PRODUCTS named as the factory's own to replace). "
        "A factory takes roadmap.py when it takes the pack."
    ),
}


def law_corpus() -> list[Path]:
    out: list[Path] = []
    for d in LAW_DIRS:
        base = REPO / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            if not LAW_HIST.search(str(p.relative_to(REPO))):
                out.append(p)
    tmpl = T / "skills"
    if tmpl.is_dir():
        out += [p for p in tmpl.rglob("*.md") if not LAW_HIST.search(str(p.relative_to(REPO)))]
    return sorted(set(out))


def is_executable(src: str) -> bool:
    """An instrument a factory runs, rather than a module it imports.

    DELEGATES to `kit_manifest.is_runnable` -- one predicate, two call sites. This body
    used to hold its own copy of the entry-point regex, and that is how this census and
    the manifest's `class_gaps` came to give DIFFERENT answers about `tools/kit_pin.py`:
    a duplicated predicate is a second opinion, not a second check.
    """
    return kit_manifest.is_runnable(src)


def local_imports(src: str, local: set[str]) -> set[str]:
    out: set[str] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in local:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name in local:
                    out.add(a.name)
    return out


def named(stem: str, text: str) -> bool:
    alts = (stem, stem.replace("_", "-"))
    return any(a in text or (a + ".py") in text for a in alts)


def build() -> dict:
    # The population is PYTHON MODULES AND EXTENSIONLESS EXECUTABLES, not `*.py`.
    # `TEMPLATE/tools/questions` is extensionless (shebang + chmod +x), and a `*.py`
    # glob cannot see it, so the census that exists to find an ungated instrument
    # reported a clean population while that instrument sat inside it unexamined
    # (#180 criterion 2). A companion asset (e.g. `questions-render.mjs`) is
    # deliberately out: it is not an instrument and carries no gate of its own -- it
    # travels with the instrument it serves. Stated here because a predicate that is
    # not written down is re-derived wrongly by the next reader.
    tools = sorted(
        q for q in T.glob("tools/*")
        if q.is_file() and q.suffix in (".py", "")
    )
    local = {p.stem for p in tools}
    tests = sorted(p.name for p in T.glob("tests/*.py"))
    kit = json.loads((REPO / "registry" / "kit.json").read_text())
    kit_paths = set(kit["files"].keys())
    boot = (T / "BOOTSTRAP.md").read_text()
    lfiles = law_corpus()
    law_text = "\n".join(p.read_text() for p in lfiles)

    # two different relations a gate can have to a tool, and they are not
    # interchangeable: a gate IMPORTS a closure module (that is how a module with no CLI is
    # exercised), and a gate INVOKES an executable as a subprocess (so an executable is
    # almost never imported by its own gate). Counting only importers would report most
    # executables as unexercised, which is a false alarm of the same shape as the false
    # exemption it replaces.
    importers: dict[str, set[str]] = {s: set() for s in local}
    invokers: dict[str, set[str]] = {s: set() for s in local}
    for tp in sorted(set(T.glob("tests/*.py")) | set(REPO.glob("tests/*.py"))):
        text = tp.read_text()
        try:
            imps = local_imports(text, local)
        except Exception:
            imps = set()
        for m in imps:
            importers[m].add(tp.name)
        for stem in local:
            if stem in imps:
                continue
            if named(stem, text):
                invokers[stem].add(tp.name)

    rows = []
    for p in tools:
        stem = p.stem
        src = p.read_text()
        kind = "executable" if is_executable(src) else "closure"
        norm = stem.replace("_", "")
        s1 = any(norm in t.replace("_", "") for t in tests)
        s2 = named(stem, boot)
        s3 = named(stem, law_text)
        s4 = "TEMPLATE/tools/%s" % p.name in kit_paths
        s = {"S1": s1, "S2": s2, "S3": s3, "S4": s4}
        gaps = [k for k in SURFACES if not s[k]]
        declared = {}
        for k in list(gaps):
            why = TOOL_EXEMPTIONS.get((stem, k)) or EXEMPTIONS.get((kind, k))
            if not why:
                continue
            # An exemption is a statement that the surface CANNOT APPLY, and it is only
            # honest if it fails when its own ground is absent. A closure module imported
            # by NO gate has no substitute for S1 — it is unexercised, and waiving it would
            # hide the gap the census exists to find.
            if (kind, k) == ("closure", "S1") and not importers[stem]:
                continue
            # the S3 waiver for a closure rests on S2 holding, so it cannot survive the
            # fact it cites
            if (kind, k) == ("closure", "S3") and not s["S2"]:
                continue
            declared[k] = why
            gaps.remove(k)
        rows.append({
            "tool": stem, "kind": kind, "surfaces": s, "gaps": gaps,
            "declared": declared,
            "imported_by_gates": sorted(importers[stem]),
            "invoked_by_gates": sorted(invokers[stem]),
        })
    return {
        "population": len(rows),
        "law_corpus_files": len(lfiles),
        "kit_file_count": len(kit_paths),
        "kit_version": kit.get("kit_version"),
        "rows": rows,
    }


def print_report(data: dict) -> int:
    rows = data["rows"]
    print("A.0 surface census — TEMPLATE/tools/ (modules and extensionless executables)")
    print()
    print("POPULATION PREDICATE")
    print("  a shipped tool is a Python module or an extensionless executable under")
    print("  TEMPLATE/tools/; its KIND decides which surfaces can apply:")
    for k in ("executable", "closure"):
        sub = [r for r in rows if r["kind"] == k]
        print("    %-11s %2d  %s" % (k, len(sub), ", ".join(r["tool"] for r in sub)))
    print("  executable: carries an entry point or an ArgumentParser (it is RUN).")
    print("  closure:    neither — it exists to be imported, so S1 and S3 are exempt")
    print("              by shape, not by waiver.")
    print()
    print("SURFACE PREDICATES")
    print("  S1  some gate's name carries the stem (normalised), i.e. the tool is exercised")
    print("  S2  TEMPLATE/BOOTSTRAP.md installs it (stem, hyphen variant, or filename)")
    print("  S3  the law corpus names it: %d .md files under skills/ + docs/ + TEMPLATE/skills/,"
          % data["law_corpus_files"])
    print("      with historical records EXCLUDED (evidence/ proposals/ rework plans/)")
    print("  S4  registry/kit.json carries it (%d files, kit_version %s)"
          % (data["kit_file_count"], data["kit_version"]))
    print()
    print("%-20s %-11s %-3s %-3s %-3s %-3s %-4s %-6s %-7s %s" % ("tool", "kind", *SURFACES, "n/4", "imp", "invoke", "status"))
    print("-" * 100)
    for r in rows:
        marks = [("Y" if r["surfaces"][k] else ".") for k in SURFACES]
        if not r["gaps"] and not r["declared"]:
            state = "complete"
        elif not r["gaps"]:
            state = "exempt %s" % ",".join(sorted(r["declared"]))
        else:
            state = "GAP %s" % ",".join(r["gaps"])
        # Two exercise relations, printed separately because they are not
        # interchangeable: a closure is exercised by being IMPORTED, an executable by being
        # INVOKED. Collapsing them into one column is what made the first version of this
        # table report most executables as unexercised.
        nimp = len(r["imported_by_gates"])
        ninv = len(r["invoked_by_gates"])
        print("%-20s %-11s %-3s %-3s %-3s %-3s %-4d %-6s %-7s %s" % (
            r["tool"], r["kind"], *marks, sum(r["surfaces"].values()),
            (str(nimp) if nimp else "-"), (str(ninv) if ninv else "-"), state))
    print()
    print("FIGURE, by kind")
    for k in ("executable", "closure"):
        sub = [r for r in rows if r["kind"] == k]
        comp = [r["tool"] for r in sub if not r["gaps"] and not r["declared"]]
        ex = [r["tool"] for r in sub if not r["gaps"] and r["declared"]]
        bad = [r["tool"] for r in sub if r["gaps"]]
        print("  %-11s %d of %d complete, %d exempt, %d undeclared" % (k, len(comp), len(sub), len(ex), len(bad)))
        if comp:
            print("      complete : %s" % ", ".join(sorted(comp)))
        if ex:
            print("      exempt   : %s" % ", ".join(sorted(ex)))
        if bad:
            print("      UNDECLARED: %s" % ", ".join(sorted(bad)))
    print()
    print("DECLARED EXEMPTIONS, with the measurement that grounds each")
    seen = set()
    for r in rows:
        for k, why in sorted(r["declared"].items()):
            if (k, why) in seen:
                continue
            seen.add((k, why))
            print("  %s of %-11s %s" % (k, r["kind"], why))
    print()
    undeclared = [r for r in rows if r["gaps"]]
    if undeclared:
        print("VERDICT: FAIL — %d tool(s) carry an undeclared gap" % len(undeclared))
        for r in undeclared:
            print("  %-20s missing %s" % (r["tool"], ", ".join(r["gaps"])))
        return 1
    print("VERDICT: PASS — every shipped tool is 4/4 or carries a declared exemption")
    print("         stating why the surface cannot apply.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the census as JSON")
    args = ap.parse_args()
    data = build()
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 1 if any(r["gaps"] for r in data["rows"]) else 0
    return print_report(data)


if __name__ == "__main__":
    sys.exit(main())
