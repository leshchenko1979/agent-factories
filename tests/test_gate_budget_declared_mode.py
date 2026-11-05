#!/usr/bin/env python3
"""Gate: #615 — a declared-mode entry can NEVER be re-derived from a single sample.

The defect this gate holds shut (ruled `n=4745`): `tools/gate_budget_rederive.py` never read
`basis_note`, so an entry whose own note declared its measurement BIMODAL was re-derived from
whichever half the audit happened to sample. On 2026-11-04 that was the WARM half, and it
collapsed `tests/test_ledger_no_shrink.py` from 550.91 s to 9.19 s — 59.95x — arming the exact
failure the margin exists to prevent: the COLD path would have died with NO VERDICT. The note
said so in its own words and no instrument could read it.

THE INVARIANT, stated so it can be tested rather than agreed with: an entry whose declaration
names more than one measurement mode can never be re-derived from one sample, because a single
duration cannot say which mode it came from.

Both directions, because a rule that only ever refuses is indistinguishable from a leg that
refuses everything:

* a BIMODAL entry is HELD, its wall is UNCHANGED, and the reason NAMES it;
* a UNIMODAL entry beside it in the same manifest still derives, so the hold is scoped;
* an entry naming NO modes is derived as before, and COUNTED on the census line, so the gap
  is observable rather than a silent default;
* an UNPARSEABLE declaration is HELD (fail-closed: an entry whose mode nobody can read is an
  entry whose mode nobody knows).

The mutation arm is the one that makes the rest a mechanism: it neuters the honouring write
and requires the gate to go RED. Without it, a future edit could delete the hold and every
probe above would still pass, because the fixture's bimodal entry would simply derive.

Run: python3 tests/test_gate_budget_declared_mode.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

failures: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)

def _entry(measured_sec: float, modes: object = "__absent__", note: str = "") -> dict:
    """A declared entry. `budget_sec` IS `margin_x x measured_sec`, so the manifest's own
    loader accepts it and the only thing these probes vary is the DECLARATION."""
    margin = 4.0 + 0.75 / measured_sec
    entry = {
        "budget_sec": round(margin * measured_sec, 2),
        "measured_sec": measured_sec,
        "margin_x": round(margin, 3),
        "measured_at": "0" * 40,
    }
    if note:
        entry["basis_note"] = note
    if modes != "__absent__":
        entry["basis_modes"] = modes
    return entry

def _git(root: Path, *args: str):
    import subprocess

    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "probe", "GIT_AUTHOR_EMAIL": "p@e",
             "GIT_COMMITTER_NAME": "probe", "GIT_COMMITTER_EMAIL": "p@e",
             "HOME": str(root), "PATH": "/usr/bin:/bin"},
    )

def _fixture(root: Path, gates: dict, name: str = "gates.json") -> tuple[Path, str]:
    """A throwaway manifest IN A THROWAWAY GIT REPO, returning (manifest, base_sha).

    The repo is not decoration. The leg resolves each entry's `measured_at` against the
    tree, so a fixture with no resolvable HEAD leaves every entry UNEXAMINED and nothing
    derives at all -- which made four of these probes pass or fail for a reason that had
    nothing to do with the hold. The base commit carries one file per declared gate, so a
    basis recorded at that revision is neither stale nor unreached, and the hold is the only
    thing that can stop a derivation.

    A bare `default` is the shape a factory inherits; it loads without stating a derivation,
    so no probe here rests on the live store.
    """
    (root / "tests").mkdir(parents=True, exist_ok=True)
    for key in gates:
        (root / key).write_text("# the gate's bytes\n", encoding="utf-8")
    if _git(root, "init", "-q").returncode != 0:
        raise RuntimeError(f"could not init a git repo under {root}")
    _git(root, "add", "-A")
    if _git(root, "commit", "-qm", "base").returncode != 0:
        raise RuntimeError(f"could not commit the fixture under {root}")
    base = _git(root, "rev-parse", "HEAD").stdout.strip()
    # THE BASIS MOVES, so every entry takes the ORDINARY (stale) arm -- which is the arm
    # the #615 collapse actually came through: a moved basis derives from ONE sample,
    # whatever the sample's size, while the growth arm needs two consecutive breaches.
    # A fixture left un-moved would test the report-first rule instead of the hold.
    for key in gates:
        (root / key).write_text("# the gate's bytes, v2 -- the basis moved\n", encoding="utf-8")
    _git(root, "add", "-A")
    if _git(root, "commit", "-qm", "head").returncode != 0:
        raise RuntimeError(f"could not commit the fixture's second revision under {root}")
    sha = _git(root, "rev-parse", "HEAD").stdout.strip()
    for entry in gates.values():
        entry["measured_at"] = base
    path = root / name
    path.write_text(
        json.dumps({"default": {"budget_sec": 120.0}, "gates": gates}, indent=2),
        encoding="utf-8",
    )
    return path, sha

def _audit(root: Path, samples: dict, *, head: str = "1" * 40) -> Path:
    """An audit report carrying one COMPLETED PASSING sample per gate, so every entry in the
    fixture is derivable on the ordinary path — the hold must be the only thing stopping it."""
    path = root / "audit.json"
    path.write_text(
        json.dumps(
            {
                "date": "2026-11-05",
                "tree": {"head_sha": head},
                "gates": [
                    {"gate_key": key, "duration_sec": sec, "passed": True}
                    for key, sec in samples.items()
                ],
            }
        ),
        encoding="utf-8",
    )
    return path

def _run(manifest: Path, audit: Path, root: Path):
    """The leg, end to end, on a fixture. Imported here so the module is the SAME one the
    tree ships — a gate that re-implemented the rule would prove nothing about the leg."""
    import gate_budget_rederive as leg

    pop = leg.containment_population(manifest, root, audit)
    return leg, pop, leg.apply_rederivation(pop, manifest, root, "2" * 40)

def probe_a_bimodal_entry_is_HELD_and_its_wall_does_not_move() -> None:
    """The harm case, reproduced: a bimodal entry whose audit sample is the FAST half."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest, sha = _fixture(root, {"tests/demo.py": _entry(100.0, ["cold", "warm"])})
        before = json.loads(manifest.read_text())["gates"]["tests/demo.py"]
        leg, pop, after_pop = _run(manifest, _audit(root, {"tests/demo.py": 2.11}, head=sha), root)
        after = json.loads(manifest.read_text())["gates"]["tests/demo.py"]

        held = dict(after_pop.held)
        check(
            "a BIMODAL entry is HELD and never re-derived",
            "tests/demo.py" in held,
            f"held={sorted(held)}",
        )
        check(
            "the HELD reason NAMES the entry's own declaration",
            "tests/demo.py" in held and "BIMODAL" in held["tests/demo.py"]
            and "cold" in held["tests/demo.py"] and "warm" in held["tests/demo.py"],
            held.get("tests/demo.py", "no reason")[:110],
        )
        check(
            "the wall is UNCHANGED — 550.91 s does not collapse to 9.19 s",
            after == before,
            f"before={before['budget_sec']} after={after['budget_sec']}",
        )
        check(
            "and it is NOT in the applied set",
            "tests/demo.py" not in after_pop.applied,
            f"applied={list(after_pop.applied)}",
        )
        check(
            "the population does not claim it either — a hold is not a containment",
            "tests/demo.py" not in pop.keys,
            f"keys={list(pop.keys)}",
        )

def probe_a_UNIMODAL_entry_beside_it_STILL_derives() -> None:
    """The hold is SCOPED. A gate that refused every entry would pass the probe above and
    would also stop every wall in the factory from ever being re-derived."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest, sha = _fixture(root, {
            "tests/bimodal.py": _entry(100.0, ["cold", "warm"]),
            "tests/unimodal.py": _entry(10.0, ["cold"]),
            "tests/undeclared.py": _entry(20.0),
        })
        before = json.loads(manifest.read_text())["gates"]
        leg, pop, after_pop = _run(manifest, _audit(root, {
            "tests/bimodal.py": 2.11, "tests/unimodal.py": 50.0, "tests/undeclared.py": 90.0,
        }, head=sha), root)
        after = json.loads(manifest.read_text())["gates"]

        check(
            "the bimodal entry stays held",
            after["tests/bimodal.py"] == before["tests/bimodal.py"],
            f"{before['tests/bimodal.py']['budget_sec']} -> {after['tests/bimodal.py']['budget_sec']}",
        )
        check(
            "a UNIMODAL entry's wall DOES move",
            after["tests/unimodal.py"]["budget_sec"] != before["tests/unimodal.py"]["budget_sec"],
            f"{before['tests/unimodal.py']['budget_sec']} -> {after['tests/unimodal.py']['budget_sec']}",
        )
        check(
            "an entry naming NO modes is derived as before — absence is not bimodality",
            after["tests/undeclared.py"]["budget_sec"] != before["tests/undeclared.py"]["budget_sec"],
            f"{before['tests/undeclared.py']['budget_sec']} -> {after['tests/undeclared.py']['budget_sec']}",
        )
        check(
            "the UNDECLARED population is counted and printed, never a silent default",
            "declared-mode hold: 1 entr" in after_pop.note
            and "1 of 3 declared entr" in after_pop.note,
            after_pop.note[-190:],
        )

def probe_an_UNPARSEABLE_declaration_is_HELD() -> None:
    """Fail-closed where it can be: a field that is PRESENT but unreadable says nothing about
    the mode, so it may not seed a derivation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest, sha = _fixture(root, {
            "tests/bad_type.py": _entry(10.0, 7),
            "tests/bad_member.py": _entry(10.0, ["cold", ""]),
            "tests/empty.py": _entry(10.0, []),
        })
        before = json.loads(manifest.read_text())["gates"]
        leg, pop, after_pop = _run(manifest, _audit(root, {
            "tests/bad_type.py": 90.0, "tests/bad_member.py": 90.0, "tests/empty.py": 90.0,
        }, head=sha), root)
        after = json.loads(manifest.read_text())["gates"]
        held = dict(after_pop.held)
        for key in ("tests/bad_type.py", "tests/bad_member.py"):
            check(
                f"an unparseable declaration is HELD — {key}",
                key in held and after[key] == before[key],
                held.get(key, "NOT HELD")[:100],
            )
        check(
            "an EMPTY mode list is a declaration of none, so it derives",
            "tests/empty.py" not in held and after["tests/empty.py"] != before["tests/empty.py"],
            f"held={sorted(held)}",
        )

def probe_the_LIVE_manifest_declares_the_bimodal_entry() -> None:
    """The one entry this defect was measured on, in the manifest the tree actually ships.
    A fix that left the live store undeclared would hold nothing in production."""
    live = json.loads((REPO / "registry" / "gates.json").read_text(encoding="utf-8"))
    entry = (live.get("gates") or {}).get("tests/test_ledger_no_shrink.py") or {}
    modes = entry.get("basis_modes")
    check(
        "tests/test_ledger_no_shrink.py declares its TWO modes in the live manifest",
        isinstance(modes, list) and len(set(modes)) > 1,
        f"basis_modes={modes!r}",
    )
    import gate_budget_rederive as leg

    check(
        "and the leg's own predicate HOLDS it",
        leg.declared_basis_hold(entry) is not None,
        (leg.declared_basis_hold(entry) or "NOT HELD")[:110],
    )

def probe_the_MUTANT_that_drops_the_hold_goes_RED() -> None:
    """The arm that makes every probe above a MECHANISM rather than a description.

    It neuters `declared_basis_hold` in the module under test and requires the harm to
    reappear: the bimodal entry must then DERIVE from the warm sample. If this arm ever
    passes while the hold is removed, the gate above is decoration.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        manifest, sha = _fixture(root, {"tests/demo.py": _entry(100.0, ["cold", "warm"])})
        before = json.loads(manifest.read_text())["gates"]["tests/demo.py"]
        audit = _audit(root, {"tests/demo.py": 2.11}, head=sha)
        import gate_budget_rederive as leg

        original = leg.declared_basis_hold
        try:
            leg.declared_basis_hold = lambda entry: None  # the hold is GONE
            pop = leg.containment_population(manifest, root, audit)
            after_pop = leg.apply_rederivation(pop, manifest, root, "2" * 40)
        finally:
            leg.declared_basis_hold = original
        after = json.loads(manifest.read_text())["gates"]["tests/demo.py"]
        check(
            "MUTANT: without the hold the bimodal wall COLLAPSES (so the hold is what stops it)",
            after["budget_sec"] < before["budget_sec"] / 2,
            f"{before['budget_sec']} -> {after['budget_sec']}",
        )
        check(
            "MUTANT: and it is no longer named as held",
            "tests/demo.py" not in dict(after_pop.held),
            f"held={sorted(dict(after_pop.held))}",
        )

def main() -> int:
    print("#615 — a declared-mode entry is never re-derived from a single sample")
    probe_a_bimodal_entry_is_HELD_and_its_wall_does_not_move()
    probe_a_UNIMODAL_entry_beside_it_STILL_derives()
    probe_an_UNPARSEABLE_declaration_is_HELD()
    probe_the_LIVE_manifest_declares_the_bimodal_entry()
    probe_the_MUTANT_that_drops_the_hold_goes_RED()
    print()
    if failures:
        print(f"declared-mode gate FAILED: {len(failures)} check(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("declared-mode gate passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
