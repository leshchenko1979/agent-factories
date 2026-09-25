#!/usr/bin/env python3
"""Gate: the kit-drift census publisher (`tools/kit_census.py`).

WHY THIS GATE EXISTS. The census is the report a plan is corrected against, so its two
load-bearing properties are that it RENDERS THE DECLARED HALF and that it REFUSES to publish
when the leg examined nothing. Both are silent failures otherwise: a census that dropped the
declarations still renders a full-looking table, and a census over an empty fleet renders a
clean one.

WHAT IT PINS, and why each arm is here:
  1. the figure AND the declared decisions both reach the artifact — the criterion the
     census exists for, and the one a "figure-only" regression would silently drop;
  2. a leg that reached NO member is a REFUSAL (rc=1, nothing written) — an empty artifact
     reads as a clean fleet, which is the examined-nothing class;
  3. a member with no declaration on record is rendered AS SUCH rather than left blank —
     a blank cell and an undeclared member look the same to a reader;
  4. an unreachable member is RENDERED, not dropped — a member missing from the table is
     indistinguishable from a member that is fine;
  5. HERMETICITY — every arm writes to a TemporaryDirectory, so the live evidence
     directory gains nothing.

The leg itself is injected, so these arms run with no live fleet and no live board: a probe
that could only run against five real repositories would be measuring those trees rather
than this tool.

Run:  python3 tests/test_kit_census.py
Exit: 0 all arms hold; 1 a failure, printed.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import kit_census as KC  # noqa: E402

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def leg_with(members: list[dict], kit_version: str = "testkit000001") -> dict:
    """A synthetic leg result, in the shape `patrol_host_state.kit_drift_leg` returns."""
    tot = {"same": 0, "DIFF": 0, "ABSENT": 0}
    for m in members:
        for k in tot:
            tot[k] += m.get(k, 0)
    return {
        "name": "kit-drift",
        "status": "ASSERTED",
        "problems": [],
        "coverage": {
            "manifest_files": 109,
            "kit_version": kit_version,
            "members_declared": len(members),
            "members_reachable": sum(1 for m in members if m.get("reachable")),
            "members_unreachable": [m["slug"] for m in members if not m.get("reachable")],
            "manifest_cells": dict(tot),
            "manifest_cells_total": sum(tot.values()),
            "bootstrap_cells": {"same": 1, "DIFF": 20, "ABSENT": 29},
            "bootstrap_cells_total": 50,
            "bootstrap_named": ["a.py"],
            "members": members,
            "read_at": "2026-01-01T00:00:00Z",
        },
    }


def member(slug: str, root: str, reachable: bool = True) -> dict:
    return {
        "slug": slug, "root": root, "reachable": reachable,
        "same": 3 if reachable else 0, "DIFF": 5 if reachable else 0,
        "ABSENT": 99 if reachable else 0,
        "diff_files": ["tools/ledger.py"] if reachable else [],
        "absent_files": ["tools/hooks/commit-msg"] if reachable else [],
    }


def main() -> int:
    live_evidence_before = sorted(p.name for p in (REPO / "evidence").glob("kit-drift-census-*"))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # A declaration record the arms control, so the live one cannot change a verdict.
        decls = tmp / "kit-decisions.json"
        decls.write_text(json.dumps({"members": {
            "alpha": {"declared_at": "2026-01-01T00:00:00Z",
                      "figure_at_declaration": "same=0 DIFF=5 ABSENT=5 of 10",
                      "forks_declared": ["tools/ledger.py"],
                      "decisions": ["DO NOT PORT: its own gates for its own code"]},
        }}))
        saved_decl, saved_leg = KC.DECISIONS, KC.P.kit_drift_leg
        KC.DECISIONS = decls
        try:
            # ARM 1 — THE FIGURE AND THE DECLARED HALF BOTH REACH THE ARTIFACT.
            root_a = tmp / "alpha"
            root_a.mkdir()
            leg = leg_with([member("alpha", str(root_a))])
            text = KC.render(leg, "2026-01-01T00:00:00Z")
            check("ARM 1: the figure is rendered",
                  "DIFF 5" in text and "testkit000001" in text,
                  "kit_version and cell totals present")
            check("ARM 1: the DECLARED decisions are rendered, not only the figure",
                  "DO NOT PORT" in text and "forks declared" in text,
                  "a figure-only regression would drop exactly this")

            # ARM 2 — A LEG THAT REACHED NO MEMBER IS A REFUSAL, NOT A CLEAN FLEET.
            KC.P.kit_drift_leg = lambda **kw: leg_with([member("alpha", str(root_a), reachable=False)])
            out2 = tmp / "refused.md"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc2 = KC.main(["--out", str(out2)])
            check("ARM 2: no reachable member REFUSES (rc=1)", rc2 == 1, f"rc={rc2}")
            check("ARM 2: the refusal writes NOTHING",
                  not out2.exists(), "an empty artifact would read as a clean fleet")
            check("ARM 2: the refusal names why",
                  "reached no member" in buf.getvalue(), buf.getvalue().strip()[:90])

            # ARM 3 — REACHABLE MEMBERS PUBLISH, AND THE ARTIFACT LANDS WHERE ASKED.
            KC.P.kit_drift_leg = lambda **kw: leg_with([member("alpha", str(root_a))])
            out3 = tmp / "published.md"
            with contextlib.redirect_stdout(io.StringIO()):
                rc3 = KC.main(["--out", str(out3)])
            check("ARM 3: reachable members publish (rc=0)", rc3 == 0, f"rc={rc3}")
            check("ARM 3: the artifact lands at --out and is non-trivial",
                  out3.is_file() and out3.stat().st_size > 1000,
                  f"{out3.stat().st_size if out3.is_file() else 0} B")

            # ARM 4 — AN UNDECLARED MEMBER IS NAMED, NOT LEFT BLANK.
            KC.P.kit_drift_leg = lambda **kw: leg_with([
                member("alpha", str(root_a)), member("beta", str(root_a)),
            ])
            out4 = tmp / "undeclared.md"
            with contextlib.redirect_stdout(io.StringIO()):
                KC.main(["--out", str(out4)])
            t4 = out4.read_text()
            check("ARM 4: a member with NO declaration is rendered as such",
                  "no declaration recorded" in t4,
                  "a blank cell and an undeclared member look the same to a reader")
            check("ARM 4: the declared member's decisions still render beside it",
                  "DO NOT PORT" in t4, "both members in one table")

            # ARM 5 — AN UNREACHABLE MEMBER IS RENDERED, NOT DROPPED.
            KC.P.kit_drift_leg = lambda **kw: leg_with([
                member("alpha", str(root_a)),
                member("gone", str(tmp / "nope"), reachable=False),
            ])
            out5 = tmp / "unreachable.md"
            with contextlib.redirect_stdout(io.StringIO()):
                KC.main(["--out", str(out5)])
            t5 = out5.read_text()
            check("ARM 5: an unreachable member is RENDERED, not dropped",
                  "`gone`" in t5 and "unreachable" in t5,
                  "a member missing from the table is indistinguishable from a healthy one")

            # ARM 6 — THE PIN COLUMN REFLECTS THE MEMBER'S OWN TREE, NOT A CONSTANT.
            vendored = tmp / "vendored"
            (vendored / "registry").mkdir(parents=True)
            (vendored / "registry" / "kit.json").write_text("{}")
            (vendored / "registry" / "kit-exemptions.json").write_text(
                json.dumps({"exempt": [{"path": "tools/ledger.py"}]}))
            KC.P.kit_drift_leg = lambda **kw: leg_with([
                member("alpha", str(root_a)), member("pinned", str(vendored)),
            ])
            out6 = tmp / "pins.md"
            with contextlib.redirect_stdout(io.StringIO()):
                KC.main(["--out", str(out6)])
            t6 = out6.read_text()
            check("ARM 6: a member with a vendored pin reads 'vendored', with its count",
                  "vendored · 1 exempt" in t6, "the member-actionable half")
            check("ARM 6: a member without one reads 'none'",
                  "**none**" in t6, "no pin means the fleet figure is not theirs to act on")
        finally:
            KC.DECISIONS, KC.P.kit_drift_leg = saved_decl, saved_leg

    # ARM 7 — HERMETICITY: every arm wrote to a TemporaryDirectory.
    live_evidence_after = sorted(p.name for p in (REPO / "evidence").glob("kit-drift-census-*"))
    check("ARM 7: the live evidence directory gained nothing",
          live_evidence_before == live_evidence_after,
          f"{len(live_evidence_after)} census artifact(s), unchanged")

    if _failures:
        print(f"kit census FAILED: {len(_failures)} check(s)")
        return 1
    print("kit census passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
