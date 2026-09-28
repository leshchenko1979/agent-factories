#!/usr/bin/env python3
"""Gate: the S1 leg of `tools/kit_surfaces.py` matches a gate's name in EITHER spelling.

WHY THIS GATE EXISTS (#214). S1 asks "does some gate exercise this tool?", and it answered
with a hand-rolled normalisation that stripped `_` and not `-`. A hyphenated tool could
therefore never match its own gate: `ledger-index` normalised to `ledger-index` and was
compared against `testledgerindex.py`, never a substring. Measured, that false negative WAS
the instrument's only headline red -- `ledger-index` read S1=false with
`tests/test_ledger_index.py` present and invoking it.

It is the shape a green suite cannot catch. The defect reads as a GAP, not as corruption,
and every other row of the report was correct, so nothing looked wrong; a suite asserting
only the happy path passes straight over it. Hence a probe that BITES.

WHAT IT PINS:
  1. the live specimen END TO END -- `ledger-index`'s row, read out of the instrument's own
     `build()`, reads S1 = True, and the gate it is judged against is asserted to EXIST so
     the arm is not matching against nothing;
  2. both directions of the leg, so the insensitivity is a property rather than the one
     direction that happened to be exercised (2b is synthetic: no real gate name carries a
     hyphen, which is itself why the one-way mapping survived);
  3. NON-VACUITY -- the leg returns FALSE for a stem no gate carries, and TRUE for a real
     stem over the SAME population, so the False is a judgement about the stem rather than a
     leg stuck at False.

POPULATION, stated in this gate's own output: the live tool stems x the live gate names,
plus the report's own row count.

WHY IT IS A GATE AND NOT A SELF-PROBE (#214 ruling). `tools/kit_surfaces.py` was run by
NOTHING -- `grep -c kit_surfaces tools/audit.py` -> 0 -- so its verdict, including this red,
reached no consumer. A self-probe that nothing runs is a comment, and the instrument that
defines the census was the one instrument with no gate at all.

Run:  python3 tests/test_kit_surfaces.py
Exit: 0 every arm holds; 1 an arm failed (each is named in the output).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "kit_surfaces.py"

def load_tool():
    """The instrument under test, loaded by path.

    `tools/` goes on sys.path first because the tool imports its own sibling
    (`kit_manifest`) by bare name, the same way every kit tool does.
    """
    sys.path.insert(0, str(TOOL.parent))
    spec = importlib.util.spec_from_file_location("kit_surfaces_under_test", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", label,
                              ("  -- " + detail) if detail else ""))
        if not ok:
            failures.append(label)

    ks = load_tool()
    gate_names = sorted(p.name for p in (REPO / "tests").glob("*.py"))
    stems = sorted(q.stem for q in (REPO / "tools").glob("*")
                   if q.is_file() and q.suffix in (".py", ""))
    specimen_gate = REPO / "tests" / "test_ledger_index.py"

    print("kit_surfaces S1 leg -- spelling insensitivity (#214)")
    print("  population: %d live tool stem(s) x %d live gate name(s)"
          % (len(stems), len(gate_names)))
    print()

    # 1. the live specimen, end to end through the instrument's own build()
    data = ks.build()
    row = next((r for r in data["rows"] if r["tool"] == "ledger-index"), None)
    check("arm 1  the instrument's report carries a `ledger-index` row",
          row is not None, "population: %d row(s)" % len(data["rows"]))
    if row is not None:
        check("arm 1  ledger-index reads S1 = True (was False before #214)",
              row["surfaces"]["S1"] is True,
              "gaps now: %s" % (", ".join(row["gaps"]) or "none"))
    check("arm 1  its gate EXISTS, so S1 is not matching against nothing",
          specimen_gate.is_file(), str(specimen_gate.relative_to(REPO)))

    # 2. the leg itself, both directions
    check("arm 2a hyphen stem vs underscore gate -- exercised_by_gate('ledger-index', ...)",
          ks.exercised_by_gate("ledger-index", ["test_ledger_index.py"]) is True)
    check("arm 2b underscore stem vs hyphen gate (SYNTHETIC name -- no real gate carries "
          "a hyphen, which is why the one-way mapping survived)",
          ks.exercised_by_gate("ledger_index", ["test_ledger-index.py"]) is True)

    # 3. non-vacuity: a leg that cannot say no is not a check
    check("arm 3  a stem NO gate carries reads False",
          ks.exercised_by_gate("no-such-tool-xyzzy", gate_names) is False,
          "over all %d live gate name(s)" % len(gate_names))
    check("arm 3b the SAME population reads True for a real stem, so arm 3 is a judgement "
          "about the stem and not a leg stuck at False",
          ks.exercised_by_gate("ledger-index", gate_names) is True)

    print()
    if failures:
        print("kit_surfaces S1 leg FAILED -- %d arm(s):" % len(failures))
        for f in failures:
            print("  %s" % f)
        return 1
    print("kit_surfaces S1 leg passed -- spelling-insensitive in both directions, and "
          "able to say no.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
