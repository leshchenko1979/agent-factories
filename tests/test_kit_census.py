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
     directory gains nothing;
  6. the ANSWERING PATH renders as its own section, and an UNMEASURED path renders as
     NOT MEASURED rather than as a clean row — an absent section and a clean section read
     the same, and that is the one confusion the section exists to prevent;
  7. an AMBIGUOUS root renders as every tap REFUSED, not as a degraded reading;
  8. the two LEGS are reported on their own rows and are allowed to DISAGREE — one marker
     summarised as one verdict clears the leg it cannot see;
  9. a member's own copy reads LIVE / inert / ABSENT / undetermined FROM the answering
     path, and INERT is never claimed when that path was not measured.

The leg AND the answering-path result are both injected, so these arms run with no live
fleet, no live board and no live answering path: a probe that could only run against five
real repositories would be measuring those trees rather than this tool.

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


def answering_dict(**kw) -> dict:
    """A synthetic answering-path result, in the shape `answering_path()` returns.

    Both legs carry DIFFERENT verdicts on purpose: the arm that pins per-leg reporting needs
    two legs that disagree, or it would pass on a renderer that collapsed them into one.
    """
    out = {
        "cli_root": "/tmp/synthetic/tools",
        "authority": "/opt/questions/backend.py (CLI_ROOT default + the CLI_RESOLVE glob)",
        "candidates": ["/tmp/synthetic/tools/state/oc-questions"],
        "resolved": "/tmp/synthetic/tools/state/oc-questions",
        "bytes": 174035,
        "mtime": "2026-01-01T00:00:00Z",
        "measured": True,
        "ambiguous": False,
        "legs": [
            {"leg": "clarify — what an owner's empty tap does", "reads": "synthetic",
             "control": 1, "fixed": 4, "old": 0, "state": "fixed"},
            {"leg": "publisher fault — what a caller learns when a page fails to build",
             "reads": "synthetic", "control": 1, "fixed": 0, "old": 1, "state": "PRE-FIX"},
        ],
        "why": "",
    }
    out.update(kw)
    return out

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
        saved_ans = KC.answering_path
        KC.DECISIONS = decls
        # The answering path is injected for the same reason the leg is: `main` calls it,
        # and a real call would make every arm below depend on which copy happens to be
        # live on this box — a probe that measures the box rather than this tool.
        KC.answering_path = lambda *a, **k: answering_dict()
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
            # ARM 8 — THE ANSWERING PATH RENDERS AS ITS OWN SECTION, WITH ITS RESOLVED COPY.
            TS = "2026-01-01T00:00:00Z"
            t8 = KC.render(leg_with([member("alpha", str(root_a))]), TS, answering=answering_dict())
            check("ARM 8: the answering path renders with its resolved copy",
                  "/tmp/synthetic/tools/state/oc-questions" in t8,
                  "the copy an owner's tap reaches, named")
            check("ARM 8: both legs render on their own rows with their OWN verdicts",
                  "| clarify" in t8 and "| publisher fault" in t8
                  and "**fixed**" in t8 and "**PRE-FIX**" in t8,
                  "two legs that disagree must not collapse into one verdict")

            # ARM 9 — AN UNMEASURED PATH IS STATED, NOT OMITTED.
            t9 = KC.render(leg_with([member("alpha", str(root_a))]), TS, answering=None)
            check("ARM 9: answering=None renders NOT MEASURED rather than a clean section",
                  "**NOT MEASURED**" in t9,
                  "an absent section and a clean section read the same")
            check("ARM 9: answering=None names no resolved copy",
                  "**executing copy**" not in t9,
                  "no measurement means no copy claimed")

            # ARM 10 — AN AMBIGUOUS ROOT IS EVERY TAP REFUSED, NOT A DEGRADED READING.
            t10 = KC.render(leg_with([member("alpha", str(root_a))]), TS,
                            answering=answering_dict(measured=False, ambiguous=True,
                                                     resolved="", candidates=[],
                                                     why="wants exactly 1 and finds 0"))
            check("ARM 10: an ambiguous root renders as REFUSED",
                  "AMBIGUOUS" in t10 and "exits 127" in t10,
                  "the backend exits 127 on any count but one")
            check("ARM 10: an ambiguous root does NOT render a resolved copy",
                  "**executing copy**" not in t10,
                  "an ambiguous root resolves nothing")

            # ARM 11 — EACH LEG IS READ ON ITS OWN MARKERS, INCLUDING THE CONTROL.
            check("ARM 11: a copy with NO control reads UNPROBED, not clean",
                  KC._leg_state({"control": 0, "fixed": 4, "old": 0}).startswith("UNPROBED"),
                  "a zero without a working control is not evidence of absence")
            check("ARM 11: a leg carrying only the OLD form reads PRE-FIX",
                  KC._leg_state({"control": 1, "fixed": 0, "old": 1}) == "PRE-FIX",
                  "the leg the fix has not reached")
            check("ARM 11: a leg carrying BOTH forms reads BOTH, not a verdict",
                  KC._leg_state({"control": 1, "fixed": 1, "old": 1}).startswith("BOTH"),
                  "a half-applied fix must not read as fixed")
            check("ARM 11: a leg carrying NEITHER marker is named as such",
                  "neither marker" in KC._leg_state({"control": 1, "fixed": 0, "old": 0}),
                  "distinct from a clean leg")

            # ARM 12 — THE PER-MEMBER COLUMN DERIVES FROM THE ANSWERING PATH, NOT THE TREE.
            live_mem = tmp / "live_mem"
            (live_mem / "tools").mkdir(parents=True)
            (live_mem / "tools" / "questions").write_text("# synthetic copy\n")
            inert_mem = tmp / "inert_mem"
            (inert_mem / "tools").mkdir(parents=True)
            (inert_mem / "tools" / "questions").write_text("# synthetic copy\n")
            absent_mem = tmp / "absent_mem"
            absent_mem.mkdir()
            m_live = member("live", str(live_mem))
            m_inert = member("inert", str(inert_mem))
            m_absent = member("absent", str(absent_mem))
            ans_at_live = answering_dict(resolved=str(live_mem / "tools" / "questions"))
            check("ARM 12: a member whose copy IS the answering path reads LIVE",
                  KC.member_copy_state(m_live, ans_at_live)["state"] == "LIVE")
            check("ARM 12: a member holding a copy OFF that path reads inert",
                  KC.member_copy_state(m_inert, ans_at_live)["state"] == "inert",
                  "a real copy that reaches no owner tap")
            check("ARM 12: a member holding NO copy reads ABSENT, not inert",
                  KC.member_copy_state(m_absent, ans_at_live)["state"] == "ABSENT",
                  "installed-nothing and installed-but-dead are different states")
            check("ARM 12: INERT is NEVER claimed when the path was not measured",
                  KC.member_copy_state(
                      m_inert, answering_dict(measured=False, resolved="", why="none")
                  )["state"] == "undetermined",
                  "off-path is a claim about the path, so it needs the path")
            t12 = KC.render(leg_with([m_live, m_inert, m_absent]), TS, answering=ans_at_live)
            check("ARM 12: the rendered table carries the column for every member",
                  "| own copy |" in t12 and "| LIVE |" in t12
                  and "| inert |" in t12 and "| ABSENT |" in t12)

            # ARM 13 — THE FLEET LINE NAMES THE TREE, OR SAYS NONE.
            t13 = KC.render(leg_with([member("host", str(live_mem))]), TS, answering=ans_at_live)
            check("ARM 13: when a member's tree holds the executing copy, it is NAMED",
                  "**The tree holding that copy**: `host`" in t13,
                  "the one case where a row can read LIVE")
            t13b = KC.render(leg_with([member("alpha", str(root_a))]), TS, answering=ans_at_live)
            check("ARM 13: when no member tree holds it, the line says NONE",
                  "NONE of the declared members" in t13b,
                  "the case that ended the install round")

        finally:
            KC.DECISIONS, KC.P.kit_drift_leg, KC.answering_path = saved_decl, saved_leg, saved_ans

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
