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
  8. a REFUSAL IS PUBLISHED, naming the refused input by path (template-instruments.md §1.5) —
     an exit code reaches a caller and a reader meets artifacts, so a refusal that wrote nothing
     would make a short list and a wrong list indistinguishable;
  9. the `held` figures are published WITH THEIR AXIS (template-instruments.md §7.5): `held`
     reads a WORKING TREE, so a declared path may be present and untracked, and the figure may
     never be quoted as a fact about the member's repository;
 10. ONE `run` row per run, subject `instrument-census-<instant>`, carrying the instant, the
     declared-set size and the per-member split (#660). The artifact path carries the DATE, so
     four runs in one morning overwrite one file and leave no trace of the three that were
     replaced: the row is what makes a reading addressable by its INSTANT (HQ n=5197 — an
     instant must RESOLVE on a surface a reader can open, and per-instant artifact paths were
     declined). A second run the same day is a second ROW, not a second artifact;
 11. a REFUSAL is a run too — it consumed the duty, and a refusal that rows nothing leaves a
     refused census indistinguishable from no census at all;
 12. a tree that is not a factory records NOTHING and says why: the duty may never be
     discharged by a silent no-op, and a tree records into a ledger INSIDE itself, never one
     outside it (asserted by the HERMETICITY arm over the LIVE ledger).

THE PREDICATE IS REUSED, NOT RESTATED. These arms run against the REPO'S OWN
`tools/registry.py`, so the refusal wording asserted below is the registry's real one: if the
schema changes, this gate fails loudly instead of measuring a stale copy of it.

Run:  python3 tests/test_instrument_census.py
Exit: 0 all arms hold; 1 a failure, printed.
"""

from __future__ import annotations

import json
import os
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


# The ledger writer and its import chain, copied WHOLE so the row arms exercise the real
# `tools/ledger.py` rather than a stub of it. A stubbed writer would assert the shape this gate
# already believes; the real one is the only thing that can prove the row is ADMISSIBLE — that
# `run` accepts a declared fixture actor and `board` is a declared ref kind in this factory.
LEDGER_CHAIN = (
    "tools/ledger.py",
    "tools/ledger_declaration.py",
    "tools/field_predicate.py",
    "tools/reconstruction.py",
    "tools/registry.py",
    "tools/actors.txt",
    "docs/ledger-refs-kinds.json",
)


def build_ledger_tree(root: Path, fragments: dict[str, dict],
                      held: dict[str, list[str]]) -> Path:
    """A census tree that is ALSO a factory: the ledger writer, its chain, and an empty store.

    The store is the tree's OWN `evidence/ledger.jsonl`, and the run below names it through
    `OC_LEDGER_PATH` — the fixture mode `tools/ledger.py` documents. That is what keeps a
    synthetic run's row out of the live ledger: a tree records into a ledger INSIDE itself, and
    the HERMETICITY arm at the foot of this file asserts the live store gained nothing.
    """
    build_tree(root, fragments, held)
    for rel in LEDGER_CHAIN:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((REPO / rel).read_text(encoding="utf-8"), encoding="utf-8")
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "ledger.jsonl").write_text("", encoding="utf-8")
    return root


# The actor the FIXTURE declares. A synthetic tree carries no lane fragments, so the ledger
# cannot derive a role there; a declared actor is the fixture's own declaration and is lawful
# only because `OC_LEDGER_PATH` marks the target as a fixture. A LIVE run declares none.
FIXTURE_ROW_ACTOR = "worker"

def run_with_ledger(root: Path, out: Path) -> tuple[int, str]:
    """`run`, with the tree's own ledger named explicitly (fixture mode)."""
    env = dict(os.environ, OC_LEDGER_PATH=str(root / "evidence" / "ledger.jsonl"))
    proc = subprocess.run(
        [sys.executable, "tools/instrument_census.py", "review-rotation",
         "--row-actor", FIXTURE_ROW_ACTOR,
         "--out", str(out), "--stdout"],
        cwd=root, capture_output=True, text=True, env=env,
    )
    return proc.returncode, proc.stdout + proc.stderr


def ledger_rows(root: Path) -> list[dict]:
    store = root / "evidence" / "ledger.jsonl"
    if not store.is_file():
        return []
    return [json.loads(line) for line in store.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def artifact_instant(body: str) -> str:
    """The instant the artifact itself stamps, read back from the artifact."""
    for line in body.splitlines():
        if "**Instant:**" in line:
            return line.split("**Instant:**", 1)[1].strip().rstrip(".")
    return ""

def row(body: str, member: str) -> str:
    """The member's row, so an arm asserts on ITS cell rather than on the whole document."""
    for line in body.splitlines():
        if line.startswith(f"| `{member}`"):
            return line
    return ""

def main() -> int:
    live_before = sorted(p.name for p in (REPO / "evidence").glob("instrument-census-*"))
    # The LIVE ledger's size, so the row arms below cannot pass by writing into the store the
    # patrol reads. A fixture that reached the live ledger would be the same defect one surface
    # over: a gate whose verdict depends on — and now MUTATES — the state it is meant to observe.
    live_ledger = REPO / "evidence" / "ledger.jsonl"
    live_ledger_before = len(live_ledger.read_text(encoding="utf-8").splitlines()) \
        if live_ledger.is_file() else 0

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
        # ARM 2b — the AXIS the `held` column owes (template-instruments.md §7.5). `held` reads a
        # WORKING TREE, so a declared path can be present and untracked, and a member can read
        # held-complete over a commit that cannot run the instrument from a clone. The figure is
        # legitimate; quoting it as a repository fact is not. Stated in the artifact that carries
        # the figure, because a requirement that reaches no assertion is the class the arm above
        # cannot catch.
        body_a = (tmp / "b.md").read_text(encoding="utf-8")
        check("the published artifact states the WORKING-TREE axis and the prohibition",
              "WORKING TREE" in body_a and "untracked" in body_a
              and "never a" in body_a and "template-instruments.md §7.5" in body_a,
              "the `held` figures are published without their axis")

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

        # ARM 9 — #660: ONE `run` row per run, addressable by its INSTANT. The artifact path
        # carries the DATE, so four runs in one morning overwrite one file and leave no trace of
        # the three that were replaced (measured 2026-11-20: 08:26:52Z / 08:30:06Z / 08:31:39Z /
        # 09:31:01Z landed on one path, and only the last survived in the tree). HQ ruled
        # (n=5197) that an instant must RESOLVE on a surface a reader can open — the commit that
        # carried the bytes, or an append-only row — and declined per-instant artifact paths. So
        # the row is what makes a reading citable, and its subject must name the SAME instant the
        # artifact stamps, or the two would be two readings.
        root = build_ledger_tree(tmp / "i",
                                 {"m1": {"instruments": {"review-rotation":
                                                         {"state": "adopted", "green": True}}}},
                                 {"m1": ALL_PATHS})
        rc, out = run_with_ledger(root, tmp / "i.md")
        rows_i = ledger_rows(root)
        body_i = (tmp / "i.md").read_text(encoding="utf-8")
        instant_i = artifact_instant(body_i)
        check("a census run appends EXACTLY ONE `run` row",
              rc == 0 and len(rows_i) == 1, f"rc={rc}, rows={len(rows_i)}, {out.strip()[-120:]}")
        check("  ... whose subject names the INSTANT the artifact itself stamps",
              bool(instant_i) and len(rows_i) == 1
              and rows_i[0].get("subject") == f"instrument-census-{instant_i}",
              f"artifact instant={instant_i!r}, "
              f"subject={rows_i[0].get('subject') if rows_i else None!r}")
        detail_i = rows_i[0].get("detail", "") if rows_i else ""
        check("  ... carrying the instant, the declared-set size and the per-member split",
              f"instant={instant_i}" in detail_i and "declared_set=2 path(s)" in detail_i
              and "members=1" in detail_i and "split=m1=2/2/ADOPTED" in detail_i, detail_i)
        check("  ... written by the actor the FIXTURE declared, and citing the board item",
              len(rows_i) == 1 and rows_i[0].get("actor") == FIXTURE_ROW_ACTOR
              and rows_i[0].get("event") == "run"
              and any("660" in str(r.get("board", "")) for r in (rows_i[0].get("refs") or [])),
              f"actor={rows_i[0].get('actor') if rows_i else None}, "
              f"refs={rows_i[0].get('refs') if rows_i else None}")

        # ARM 9c — THE LIVE SHAPE. No subprocess arm can reach the live ledger, so the argv a
        # live run builds is pinned here: `--actor` must be ABSENT, because a declared actor is
        # refused on the live path (identity is derived from the writing session). This is the
        # regression that started it — a hardcoded constant made the row unwritable from every
        # lane but the one it named.
        sys.path.insert(0, str(REPO / "tools"))
        import instrument_census as _ic
        live_cmd = _ic._census_row_cmd(Path("ledger.py"), "s", "d", None)
        declared_cmd = _ic._census_row_cmd(Path("ledger.py"), "s", "d", "worker")
        check("a LIVE run declares NO actor, so the ledger derives the lane that ran it",
              "--actor" not in live_cmd,
              f"argv={live_cmd}")
        check("  ... while a FIXTURE may declare one, and only then does `--actor` appear",
              declared_cmd[declared_cmd.index("--actor") + 1] == "worker",
              f"argv={declared_cmd}")

        # ARM 9b — a SECOND run on the same day is a second row. This is the whole point: the
        # artifact path is overwritten, so a day that ran twice must still be readable as two
        # runs. Two rows, each addressable, on one path.
        rc2, _ = run_with_ledger(root, tmp / "i2.md")
        rows_i2 = ledger_rows(root)
        check("a second run on the SAME day appends a second row, not a second artifact",
              rc2 == 0 and len(rows_i2) == 2
              and all(str(r.get("subject", "")).startswith("instrument-census-")
                      for r in rows_i2),
              f"rc={rc2}, rows={len(rows_i2)}")

        # ARM 10 — a REFUSAL is a run too. It consumed the duty and it is the reading a later
        # reader most needs to find ("did the census run that morning, and what did it say"), so
        # a refusal that rows nothing makes a refused census indistinguishable from no census.
        root = build_ledger_tree(tmp / "j", {"m1": {}}, {"m1": ALL_PATHS})
        (root / "docs" / "instruments" / "review-rotation.md").write_text(
            "# no table here\n", encoding="utf-8")
        rc, out = run_with_ledger(root, tmp / "j.md")
        rows_j = ledger_rows(root)
        check("a REFUSED census still appends its run row",
              rc == 1 and len(rows_j) == 1, f"rc={rc}, rows={len(rows_j)}")
        check("  ... and the row reports the set it REFUSED, not a clean one",
              len(rows_j) == 1 and "declared_set=0 path(s)" in rows_j[0].get("detail", ""),
              rows_j[0].get("detail", "") if rows_j else "")

        # ARM 11 — a tree that is not a factory records NOTHING and SAYS SO. The duty may not be
        # discharged by a silent no-op: a run that cannot record has to say why, or the next
        # reader meets an empty ledger and cannot tell it from a lane that skipped the duty.
        root = build_tree(tmp / "k",
                          {"m1": {"instruments": {"review-rotation":
                                                  {"state": "adopted", "green": True}}}},
                          {"m1": ALL_PATHS})
        rc, out = run(root, tmp / "k.md")
        check("a tree with no ledger writer records nothing and says WHY",
              rc == 0 and "run row SKIPPED" in out and not (root / "evidence").exists(),
              f"rc={rc}, said_skipped={'run row SKIPPED' in out}")

    live_after = sorted(p.name for p in (REPO / "evidence").glob("instrument-census-*"))
    check("HERMETICITY: the live evidence directory gained nothing",
          live_before == live_after, f"{len(live_before)} -> {len(live_after)}")
    live_ledger_after = len(live_ledger.read_text(encoding="utf-8").splitlines()) \
        if live_ledger.is_file() else 0
    check("HERMETICITY: the LIVE ledger gained no row — every row above is a tree's own",
          live_ledger_before == live_ledger_after,
          f"{live_ledger_before} -> {live_ledger_after}")

    print()
    if _failures:
        print(f"instrument census gate: FAILED — {len(_failures)} arm(s): {', '.join(_failures)}")
        return 1
    print("instrument census gate: passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
