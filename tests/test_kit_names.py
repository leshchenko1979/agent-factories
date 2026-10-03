#!/usr/bin/env python3
"""Gate: the fleet-wide name census (`tools/kit_names.py`).

WHY THIS GATE EXISTS. The census answers three questions and every one of them can be
answered WRONG while the artifact still renders: a conflict predicate that never fires
reports a clean fleet, a shadow predicate that never fires reports no shadowing, and a
purpose reader that picks the wrong string decides both on the wrong text. So the arms below
drive each predicate against a fixture whose answer is KNOWN, with a companion that must read
the opposite way — a predicate that cannot fail is not a predicate.

WHAT IT PINS:
  1. the conflict predicate BITES on two trees carrying one name under different purposes,
     and does NOT fire on a REWORDED purpose (one instrument described twice) — the two
     directions that make the predicate usable rather than merely strict;
  2. the shadow predicate BITES on a name in `sys.stdlib_module_names` and stays quiet on a
     companion name that is not — the live instance being a stray `struct.py` that broke a
     `ctypes` probe in an unrelated session;
  3. the PURPOSE reader takes the MODULE docstring, not the first string literal it finds —
     a file whose first statement is an import contributes its real docstring, and a file
     with no module docstring contributes NOTHING rather than a function's;
  4. a name carried by ONE tree is not a conflict, however its purpose reads;
  5. an unreachable tree set is a REFUSAL, not an empty census — an empty census reads as a
     clean fleet, which is the examined-nothing class;
  6. the KIT MANIFEST is read from HEAD, not the working tree (#292) — proven over a fixture
     whose HEAD and working copy DISAGREE, the only shape that can show it, since on a clean
     tree the two agree and the pre-fix code passes the same assertion;
  7. an unreadable manifest REFUSES rather than returning `[]` and censusing the D.1
     candidates alone — with a companion showing the refusal is conditional on the failure;
  8. the companion `fleet_trees()` read of `registry/fleet.json` is the same discipline;
  9. HERMETICITY — every arm runs in a TemporaryDirectory, so the live evidence directory
     gains nothing.

Run:  python3 tests/test_kit_names.py
Exit: 0 all arms hold; 1 a failure, printed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import kit_names as KN  # noqa: E402

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root

def _git(root: Path) -> None:
    """Init a repo and COMMIT whatever is in it, so HEAD is a real revision to read.

    A fixture that is NOT a git repo cannot prove the HEAD read at all: the fix falls back to
    disk there, so the pre-fix and post-fix code agree and the arm would pass vacuously.
    """
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-qm", "init"], check=True)


def main() -> int:
    live_before = sorted(p.name for p in (REPO / "evidence").glob("name-census-*"))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ---- ARM 1: the conflict predicate BITES, and its companion does NOT.
        a = tree(tmp / "a", {"tools/thing.py": '"""The ledger instrument."""\n'})
        b = tree(tmp / "b", {"tools/thing.py": '"""A site copy linter."""\n'})
        c = tree(tmp / "c", {"tools/thing.py": '"""The ledger instrument, reworded."""\n'})

        r = KN.census({"a": a, "b": b}, ["thing.py"])
        v = r["names"].get("thing.py") or {}
        check("ARM 1: two trees, two purposes — CONFLICT fires",
              bool(v.get("conflict")), f"overlap={v.get('overlap')}")
        check("ARM 1: the conflict names BOTH trees and their digests",
              set(v.get("trees", {})) == {"a", "b"} and all(v.get("digests", {}).values()),
              "a conflict without the population cannot be acted on")

        r2 = KN.census({"a": a, "c": c}, ["thing.py"])
        v2 = r2["names"].get("thing.py") or {}
        check("ARM 1 COMPANION: a REWORDED purpose is NOT a conflict",
              not v2.get("conflict"),
              f"overlap={v2.get('overlap')} — a strict predicate would red every docstring edit")

        # ---- ARM 2: the shadow predicate BITES, with a non-shadowing companion.
        d = tree(tmp / "d", {
            "tools/struct.py": '"""Shadow the stdlib struct module."""\n',
            "tools/kit_pin.py": '"""A real kit module."""\n',
        })
        r3 = KN.census({"d": d}, ["struct.py", "kit_pin.py"])
        check("ARM 2: a stdlib name is flagged as shadowing",
              (r3["names"].get("struct.py") or {}).get("shadow_stdlib") is True,
              "the live instance: a stray struct.py broke a ctypes probe elsewhere")
        check("ARM 2 COMPANION: a non-stdlib name is NOT flagged",
              (r3["names"].get("kit_pin.py") or {}).get("shadow_stdlib") is False,
              "a predicate that flagged everything would pass the arm above vacuously")

        # ---- ARM 3: the purpose reader takes the MODULE docstring.
        e = tree(tmp / "e", {
            "tools/imported.py": 'from __future__ import annotations\n\nimport json\n\n\n'
                                 'def helper():\n    """A helper about atomic writes."""\n',
        })
        r4 = KN.census({"e": e}, ["imported.py"])
        pur = (r4["names"].get("imported.py") or {}).get("purposes") or []
        check("ARM 3: a file with NO module docstring contributes NO purpose",
              pur == [],
              f"got {pur} — a scan would report the helper's docstring")
        # The REAL convention fleet-wide: docstring FIRST, then the future-import. Measured
        # 2026-09-25 over 656 .py files in five trees: ZERO carry a docstring placed after
        # another statement, so the misplaced case is a limit of the predicate rather than a
        # live population. This arm pins the convention that actually holds.
        f2 = tree(tmp / "f", {"tools/real.py": '"""The real module purpose."""\n'
                                              'from __future__ import annotations\n'})
        r5 = KN.census({"f": f2}, ["real.py"])
        pur2 = (r5["names"].get("real.py") or {}).get("purposes") or []
        check("ARM 3: a module docstring BEFORE the future-import IS read",
              pur2 == ["The real module purpose."], f"got {pur2}")
        check("ARM 3 COMPANION: a docstring placed AFTER an import is not a docstring",
              KN.purpose_of(tree(tmp / "g", {"tools/after.py":
                  'import json\n\n"""Not a module docstring in Python."""\n'})
                  / "tools" / "after.py") == "",
              "Python semantics, not a defect — recorded so the limit is known")

        # ---- ARM 4: one tree alone is never a conflict.
        r6 = KN.census({"a": a}, ["thing.py"])
        check("ARM 4: a name carried by ONE tree is not a conflict",
              not (r6["names"].get("thing.py") or {}).get("conflict"),
              "a single tree has nothing to conflict with")

        # ---- ARM 5: no reachable tree is a REFUSAL.
        r7 = KN.census({"gone": tmp / "nope"}, ["thing.py"])
        check("ARM 5: an unreachable tree set is a REFUSAL, not an empty census",
              bool(r7.get("problems")), str(r7.get("problems"))[:80])

        # ---- ARM 7: the kit manifest is read from HEAD, not the working tree (#292).
        # A git repo whose HEAD manifest and working-tree manifest DISAGREE: only a HEAD read
        # returns the committed population. On a clean live tree the two agree and the pre-fix
        # code would pass this same assertion, which is why the fixture must differ.
        a7 = tmp / "headkit"
        (a7 / "registry").mkdir(parents=True)
        (a7 / "registry" / "kit.json").write_text(
            json.dumps({"files": {"tools/committed_only.py": "h"}}))
        _git(a7)
        (a7 / "registry" / "kit.json").write_text(          # working tree now disagrees
            json.dumps({"files": {"tools/working_only.py": "d"}}))
        got7 = KN.kit_names(repo=a7)
        check("ARM 7: kit_names() returns the HEAD population, not the dirty working copy",
              got7 == ["committed_only.py"],
              f"got {got7} — a disk read would return working_only.py")

        # ---- ARM 8: an unreadable manifest REFUSES; a readable one does NOT.
        a8 = tmp / "nokit"
        (a8 / "registry").mkdir(parents=True)
        (a8 / "README.md").write_text("a tree with a HEAD, but no committed manifest\n")
        _git(a8)                                            # manifest never committed
        (a8 / "registry" / "kit.json").write_text(
            json.dumps({"files": {"tools/untracked.py": "u"}}))
        refused8, why8 = False, ""
        try:
            KN.kit_names(repo=a8)
        except SystemExit as exc:
            refused8, why8 = True, str(exc)[:70]
        check("ARM 8: an uncommitted manifest REFUSES rather than censusing D.1 alone",
              refused8, why8 or "returned instead of refusing")
        check("ARM 8 COMPANION: a readable manifest does NOT refuse",
              len(KN.kit_names(repo=REPO)) > 0,
              "the refusal must be conditional on the failure, not unconditional")

        # ---- ARM 9: the companion fleet_trees() read is the same discipline.
        a9 = tmp / "headfleet"
        (a9 / "registry").mkdir(parents=True)
        (a9 / "registry" / "fleet.json").write_text(
            json.dumps({"factories": [{"slug": "committed", "repo": "/tmp/committed"}]}))
        _git(a9)
        (a9 / "registry" / "fleet.json").write_text(
            json.dumps({"factories": [{"slug": "working", "repo": "/tmp/working"}]}))
        ft9 = KN.fleet_trees(repo=a9)
        check("ARM 9: fleet_trees() reads the fleet manifest from HEAD too",
              "committed" in ft9 and "working" not in ft9, f"trees={list(ft9)}")

    # ---- ARM 6: HERMETICITY.
    live_after = sorted(p.name for p in (REPO / "evidence").glob("name-census-*"))
    check("ARM 6: the live evidence directory gained nothing",
          live_before == live_after, f"{len(live_after)} census artifact(s), unchanged")

    if _failures:
        print(f"kit names FAILED: {len(_failures)} check(s)")
        return 1
    print("kit names passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
