#!/usr/bin/env python3
"""Gate: the instrument adoption census (`tools/instrument_census.py`).

WHY THIS GATE EXISTS. The census is the artifact a member's adoption is read off, and its
DECLARED leg is the half a reader is most likely to over-read: a complete set of files with no
decision behind it is not an adoption (template-instruments.md §1.3), and a declaration that no longer satisfies
the registry's predicate is not a disposition either. A census that absorbed either would render
a full-looking table and manufacture an adoption nobody decided — silent, and in the flattering
direction.

WHAT IT PINS, and why each arm is here:
  1. the DECLARED leg is read from `instruments.<slug>`, and the `kit` key beside it — the KIT's
     own state — is never rendered as this instrument's. One surface read as the other is the
     defect the two-leg rule exists to prevent;
  2. an ABSENT key is LEGAL and renders as the member's silence (rc=0), never as a refusal: the
     schema makes absence valid, and a member that considered the instrument has to stay
     distinguishable from one that never did;
  3. a PRESENT key the registry REFUSES renders `DECLARED-INVALID` carrying the registry's OWN
     error — a deferral with no reason, and an `adopted` that leaves its `green` axis unspoken;
  4. NON-VACUITY — a complete set declared `adopted` with `green: true` reads ADOPTED, so the
     arms above fail for the reason they name rather than because the gate is stuck;
  5. a declaration cannot MANUFACTURE a set: `adopted` over an incomplete set does not read
     ADOPTED;
  6. a zero parsed declared set is a REFUSAL (rc=1), not a clean census — the
     examined-nothing class;
  7. HERMETICITY — every arm runs in a TemporaryDirectory, so the live `evidence/` gains
     nothing;
  8. a REFUSAL IS PUBLISHED, naming the refused input by path (template-instruments.md §1.5) — an exit code
     reaches a caller and a reader meets artifacts, so a refusal that wrote nothing would make
     a short list and a wrong list indistinguishable.

THE PREDICATE IS REUSED, NOT RESTATED. These arms run against the REPO'S OWN
`tools/registry.py`, so the refusal wording asserted below is the registry's real one: if the
schema changes, this gate fails loudly instead of measuring a stale copy of it.

Run:  python3 tests/test_instrument_census.py
Exit: 0 all arms hold; 1 a failure, printed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_failures: list[str] = []

# Two declared paths, so "complete" and "incomplete" are both expressible without a third file.
LAW = """# review-rotation (fixture)

## 2. The declared file set

| # | path (root half ↔ TEMPLATE half) | class | what it is |
|---|---|---|---|
| 1 | `tools/review.py` ↔ `TEMPLATE/tools/review.py` | `standalone` | the executable |
| 2 | `tests/test_review.py` ↔ `TEMPLATE/tests/test_review.py` | `standalone` | the gate |
"""

ALL_PATHS = ["tools/review.py", "tests/test_review.py"]

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)

def build_tree(root: Path, fragments: dict[str, dict], held: dict[str, list[str]]) -> Path:
    """A minimal census tree: the REPO'S REAL tool and registry predicate, synthetic members."""
    (root / "tools").mkdir(parents=True)
    (root / "docs" / "instruments").mkdir(parents=True)
    (root / "registry" / "factories").mkdir(parents=True)
    for rel in ("tools/instrument_census.py", "tools/registry.py"):
        (root / rel).write_text((REPO / rel).read_text(encoding="utf-8"), encoding="utf-8")
    (root / "docs" / "instruments" / "review-rotation.md").write_text(LAW, encoding="utf-8")
    for slug, frag in fragments.items():
        member_root = root / "members" / slug
        for rel in held.get(slug, []):
            path = member_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")
        body = dict(frag)
        body["repo"] = str(member_root)
        body.setdefault("factory", slug)
        (root / "registry" / "factories" / f"{slug}.json").write_text(
            json.dumps(body, indent=2), encoding="utf-8")
    return root

def run(root: Path, out: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "tools/instrument_census.py", "review-rotation",
         "--out", str(out), "--stdout"],
        cwd=root, capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr

def row(body: str, member: str) -> str:
    """The member's row, so an arm asserts on ITS cell rather than on the whole document."""
    for line in body.splitlines():
        if line.startswith(f"| `{member}`"):
            return line
    return ""

def main() -> int:
    live_before = sorted(p.name for p in (REPO / "evidence").glob("instrument-census-*"))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ARM 1 — the KIT's state is not this instrument's declaration. The member declares its
        # kit adopted and says NOTHING about the instrument: a census that read the two
        # surfaces as one would print ADOPTED over a decision nobody made.
        root = build_tree(tmp / "a", {"m1": {"kit": {"state": "adopted"}}}, {"m1": ALL_PATHS})
        rc, _ = run(root, tmp / "a.md")
        body = (tmp / "a.md").read_text(encoding="utf-8")
        line = row(body, "m1")
        check("a `kit` declaration is NOT read as this instrument's",
              "HELD-UNDECLARED" in line and "ADOPTED" not in line, line.strip())
        check("  ... and the absent key is not a refusal", rc == 0, f"rc={rc}")

        # ARM 2 — a lawful declaration over a complete set DOES read ADOPTED. Without this the
        # arms below would pass on a gate that never accepts anything.
        root = build_tree(tmp / "b",
                          {"m1": {"instruments": {"review-rotation":
                                                  {"state": "adopted", "green": True}}}},
                          {"m1": ALL_PATHS})
        rc, _ = run(root, tmp / "b.md")
        line = row((tmp / "b.md").read_text(encoding="utf-8"), "m1")
        check("NON-VACUITY: adopted + green over a complete set reads ADOPTED",
              rc == 0 and "**ADOPTED**" in line, line.strip())

        # ARM 3 — a declaration cannot MANUFACTURE a set. Same lawful declaration, incomplete set.
        root = build_tree(tmp / "c",
                          {"m1": {"instruments": {"review-rotation":
                                                  {"state": "adopted", "green": True}}}},
                          {"m1": ALL_PATHS[:1]})
        run(root, tmp / "c.md")
        line = row((tmp / "c.md").read_text(encoding="utf-8"), "m1")
        check("a declaration over an INCOMPLETE set does not read ADOPTED",
              "**ADOPTED**" not in line and "DECLARED-ADOPTED" in line, line.strip())

        # ARM 4 — a REASONLESS DEFERRAL is refused, carrying the registry's own wording.
        root = build_tree(tmp / "d",
                          {"m1": {"instruments": {"review-rotation": {"state": "deferred"}}}},
                          {"m1": ALL_PATHS})
        rc, _ = run(root, tmp / "d.md")
        body = (tmp / "d.md").read_text(encoding="utf-8")
        check("a reasonless deferral reads DECLARED-INVALID",
              "DECLARED-INVALID" in row(body, "m1"), row(body, "m1").strip())
        check("  ... and the registry's OWN reason reaches the artifact",
              "requires a non-empty `reason`" in body,
              "the refusal text did not reach the artifact")

        # ARM 5 — the second axis: `adopted` that leaves `green` unspoken is refused too.
        root = build_tree(tmp / "e",
                          {"m1": {"instruments": {"review-rotation": {"state": "adopted"}}}},
                          {"m1": ALL_PATHS})
        run(root, tmp / "e.md")
        body = (tmp / "e.md").read_text(encoding="utf-8")
        check("an `adopted` with no `green` axis is refused, naming the axis",
              "DECLARED-INVALID" in row(body, "m1")
              and "requires `green: true`" in body, row(body, "m1").strip())

        # ARM 6 — a lawful DEFERRAL (with its reason) is a state, not a failure: the refusal in
        # arm 4 must be about the missing reason, not about deferring.
        root = build_tree(tmp / "f",
                          {"m1": {"instruments": {"review-rotation":
                                                  {"state": "deferred",
                                                   "reason": "waiting on Q3"}}}},
                          {"m1": ALL_PATHS})
        rc, _ = run(root, tmp / "f.md")
        line = row((tmp / "f.md").read_text(encoding="utf-8"), "m1")
        check("a deferral WITH its reason reads DECLARED-DEFERRED (rc=0)",
              rc == 0 and "DECLARED-DEFERRED" in line, line.strip())

        # ARM 7 — a law doc whose declared-set table does not parse is a REFUSAL, not an empty census,
        # AND the refusal is PUBLISHED. template-instruments.md §1.5: an aggregate reports the inputs it refused,
        # BY PATH, in the artifact a reader meets. An exit code reaches a caller; a reader who
        # lists the artifact directory meets files -- so a refusal that wrote nothing would make
        # a short list and a wrong list indistinguishable, which is the defect this arm pins.
        root = build_tree(tmp / "g", {"m1": {}}, {"m1": ALL_PATHS})
        (root / "docs" / "instruments" / "review-rotation.md").write_text(
            "# no table here\n", encoding="utf-8")
        rc, out = run(root, tmp / "g.md")
        body = (tmp / "g.md").read_text(encoding="utf-8") if (tmp / "g.md").is_file() else ""
        check("a zero parsed declared set is a REFUSAL (rc=1)",
              rc == 1 and "REFUSED" in out, f"rc={rc}")
        check("  ... and the refusal IS published, naming the REFUSED INPUT BY PATH",
              (tmp / "g.md").is_file() and "docs/instruments/review-rotation.md" in body,
              f"wrote={(tmp / 'g.md').exists()}, names_path="
              f"{'docs/instruments/review-rotation.md' in body}")
        check("  ... the artifact says the instrument was NOT censused, so no table is read",
              "NOT censused" in body and "| member |" not in body,
              "the refusal artifact rendered a reading table")
        check("  ... and it carries NO absolute worktree path",
              str(root) not in body, "an absolute path leaked into a published artifact")

        # ARM 8 — the refusal must reach the DEFAULT artifact location too. The arms above pass
        # --out; a reader meets the path the tool CHOSE, so that leg is pinned separately.
        root = build_tree(tmp / "h", {"m1": {}}, {"m1": ALL_PATHS})
        (root / "docs" / "instruments" / "review-rotation.md").write_text(
            "# no table here\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "tools/instrument_census.py", "review-rotation"],
            cwd=root, capture_output=True, text=True)
        default = sorted(p.name for p in (root / "evidence").glob("instrument-census-*"))
        check("a refusal with no --out still lands under evidence/ (template-instruments.md §1.5)",
              proc.returncode == 1 and len(default) == 1, f"rc={proc.returncode}, {default}")

    live_after = sorted(p.name for p in (REPO / "evidence").glob("instrument-census-*"))
    check("HERMETICITY: the live evidence directory gained nothing",
          live_before == live_after, f"{len(live_before)} -> {len(live_after)}")

    print()
    if _failures:
        print(f"instrument census gate: FAILED — {len(_failures)} arm(s): {', '.join(_failures)}")
        return 1
    print("instrument census gate: passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
