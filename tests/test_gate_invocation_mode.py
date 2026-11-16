#!/usr/bin/env python3
r"""Gate: the audit's invocation mode is DECLARED per gate, and matches its call site.

WHAT THIS GATE IS FOR. The audit invokes its gates under TWO conventions -- some as
`python3 tests/x.py` (the file's `__main__` block owns the verdict) and some as
`python3 -m pytest tests/x.py` (the test functions own it) -- and the split is INTENDED
(#144: a gate's form is a property of what it tests, not a uniform). What was missing is
the DECLARATION. A member wiring the kit's gates into a pytest-based CI enforces only the
pytest-invoked population, and a green CI then reads as "the gates passed" when a
script-invoked gate was never collected. Measured on one member (2026-09-27): `pytest` over
two gate files collected 8 items from one and NOTHING from the other, which was rc=1 with
4 violations under its own script form -- "the gate is red" and "shipping is blocked" were
different facts there, and nothing on any surface distinguished them.

WHAT IT ASSERTS. For every gate the audit invokes: a mode is declared, the declared mode
matches the CALL SITE's own form, and no path is invoked under both forms. The population
is the call sites, not a file glob and not the budget manifest -- 18 invoked gates carry no
budget entry, so a gate keyed on that manifest would have declared a mode for 46 of 64 and
gone green over the other 28 percent.

WHY THE CALL SITE AND NOT THE FILE'S SHAPE. A file can be dual-shaped: it may carry
module-level `def test_` AND a `__main__` block, and then the file's own shape does not
answer which convention the audit uses. `test_questions.py` is exactly that shape and is
invoked as a SCRIPT, so its `__main__` owns the verdict and pytest never sees it.

WHERE THE MAP IS ABSENT, THE GATE SKIPS WITH ITS REASON -- a bootstrapped factory has not
adopted the declaration yet, and that is a legitimate state, not a defect. A map that
exists and cannot be read is a FAILURE, never a skip: the two are the same output to a
caller that only sees a verdict, and one of them hides a broken declaration.

Run:  python3 tests/test_gate_invocation_mode.py
      python3 tests/test_gate_invocation_mode.py --emit-modes
Exit: 0 every invoked gate's declared mode matches its call site, 1 a problem, 2 the
      declaration could not be read at all. Under `--emit-modes` it exits 2 when the
      call sites cannot be parsed, because an emitted empty map is not a map.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_registry  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / "tools" / "audit.py"
MANIFEST = REPO / "registry" / "gates.json"

# The two conventions, and ONLY these two: a third would be a new call-site form nobody
# declared, which is the class this gate exists to make loud rather than silently unjudged.
# READ FROM THE SHARED MODULE (#296): a private copy of the pair would be the same
# "one field, two predicates" defect the ruling retires, one constant at a time.
MODES = gate_registry.GATE_MODES

# The failure class is the shared one too, so a caller catching it here catches exactly what
# `gate_registry.declared_gate_modes` raises.
ManifestUnreadable = gate_registry.GateModesUnreadable

def invoked_gates(audit_path: Path = AUDIT) -> dict[str, str]:
    """Every gate the audit invokes, mapped to the convention its CALL SITE uses.

    The map comes from the SHARED predicate (#296, HQ ruling n=2123), never from a parse of
    this gate's own: `gate_registry.invoked_gate_modes` reads the mode out of the same append
    scan that already carries the runner, so this gate and
    `tests/test_gate_registration.py` cannot disagree about what the audit invokes or under
    which convention. One field, one predicate -- a private mode-map walk beside it is the
    same defect one level down, which is what the ruling retired.

    The population is the call SITES and not a glob: a gate that ships but is never invoked
    owes no mode.

    The AST walk this replaces was written because a NAIVE regex over the appends
    under-counted them. The shared scan is not that regex -- it is the append scan three
    other directions already read -- and it was measured against the AST reader on this tree
    before the switch: 133 paths, 0 population difference, 0 mode disagreement.
    """
    return gate_registry.invoked_gate_modes(audit_path)

def declared_modes(manifest_path: Path = MANIFEST) -> tuple[dict[str, str], str]:
    """`(modes, note)` from the manifest, or raises -- the SHARED reader (#296).

    Delegation, not a copy: `gate_registry.declared_gate_modes` is the one place a `modes`
    object is read, so this gate and `tests/test_gate_registration.py` cannot disagree about
    what a malformed declaration is either.
    """
    return gate_registry.declared_gate_modes(manifest_path)

def problems(invoked: dict[str, str], declared: dict[str, str]) -> list[str]:
    """Every mismatch between the call sites and the declaration -- the SHARED predicate."""
    return gate_registry.gate_mode_problems(invoked, declared)

def probe_the_population_is_the_call_sites_and_is_non_empty() -> None:
    """The population is the CALL SITES, and a predicate that examined nothing says so."""
    invoked = invoked_gates()
    assert invoked, "no gate call sites parsed — the population is empty and nothing is judged"
    assert len(invoked) > 1, invoked
    forms = {m for m in invoked.values()}
    assert forms & set(MODES), f"no recognised call-site form among {forms}"

def probe_every_invoked_gate_declares_the_mode_its_call_site_uses() -> None:
    """The core assertion: declared mode == call-site form, for every invoked gate."""
    invoked = invoked_gates()
    declared, note = declared_modes()
    found = problems(invoked, declared)
    assert not found, f"{note}: " + "; ".join(found)

def probe_a_DISAGREEING_declaration_is_reported_not_accepted() -> None:
    """The bite, driven from a CONSTRUCTED pair rather than from live data (#195 c).

    A check that has only ever seen agreeing input has not been shown to reject
    disagreeing input, and this gate's whole subject is a declaration drifting from the
    call site it describes.
    """
    invoked = {"tests/test_a.py": "script", "tests/test_b.py": "pytest"}
    declared = {"tests/test_a.py": "pytest", "tests/test_b.py": "pytest"}  # test_a flipped
    found = problems(invoked, declared)
    assert len(found) == 1, found
    assert "test_a.py" in found[0] and "declared `pytest`" in found[0], found[0]

    missing = problems({"tests/test_c.py": "script"}, {})
    assert len(missing) == 1 and "NO declared mode" in missing[0], missing

    both = problems({"tests/test_d.py": "script+pytest"}, {"tests/test_d.py": "script"})
    assert len(both) == 1 and "BOTH forms" in both[0], both

    orphan = problems({}, {"tests/test_e.py": "script"})
    assert len(orphan) == 1 and "NOT invoked" in orphan[0], orphan

def probe_a_dual_SHAPED_file_is_judged_by_its_CALL_SITE() -> None:
    """The constraint that makes the call site the only honest source (#195).

    `tests/test_questions.py` carries module-level `def test_` AND a `__main__` block, and
    the audit invokes it as a SCRIPT. Judging by the file's shape would declare it
    `pytest` and be wrong; the declaration must come from the call site.
    """
    invoked = invoked_gates()
    declared, _ = declared_modes()
    dual = [
        p for p in invoked
        if (REPO / p).is_file()
        and "def test_" in (REPO / p).read_text(encoding="utf-8")
        and '__main__' in (REPO / p).read_text(encoding="utf-8")
    ]
    assert dual, (
        "no dual-shaped gate found — the fixture this probe exists for has changed shape, so "
        "the probe would pass vacuously; re-point it rather than deleting it"
    )
    for path in dual:
        assert declared.get(path) == invoked[path], (
            f"{path} is dual-shaped and declared `{declared.get(path)}` against a call site of "
            f"`{invoked[path]}` — the declaration must follow the call site, not the shape"
        )

def emit_modes(audit_path: Path = AUDIT) -> int:
    """Print the mode map this tree's call sites IMPLY, as JSON, and exit 0.

    `modes` is a property of `tools/audit.py`, which ships byte-identical into every tree,
    so hand-transcribing 73 mechanical facts is transcription for no gain -- and it is the
    class that produces stale counts, because nothing re-derives them when a call site moves.
    Budgets stay DECLARED (a runtime is box-specific); modes are DERIVED (a call site is not).

    This bypasses nothing. The map below is produced by the same `invoked_gates()` the gate
    asserts the declaration against, so an emitted map cannot disagree with the judged one;
    merging it into `registry/gates.json` is how the two stay in step. A tree whose call
    sites cannot be parsed, or where one path is invoked under BOTH forms, is REFUSED --
    an emitted empty map declares nothing and would read as agreement.
    """
    invoked = invoked_gates(audit_path)
    if not invoked:
        print(
            "no gate call sites parsed — refusing to emit an empty map, which would "
            "declare nothing and read as agreement",
            file=sys.stderr,
        )
        return 2
    ambiguous = sorted(p for p, form in invoked.items() if "+" in form)
    if ambiguous:
        for path in ambiguous:
            print(
                f"  AMBIGUOUS  {path}: invoked under BOTH forms, so no single mode can be "
                f"right — that is a call-site defect, not a declaration gap",
                file=sys.stderr,
            )
        return 2
    print(json.dumps(dict(sorted(invoked.items())), indent=2, ensure_ascii=False))
    return 0

def probe_the_EMITTER_prints_the_map_the_gate_judges() -> None:
    """`--emit-modes` is the member's path, so its output is asserted, not assumed.

    A derivation that printed a different map would be a second, silent declaration of the
    same fact. This probe runs the emit path and holds it to the call sites AND to the
    declaration, so the three can only ever be one map.
    """
    invoked = invoked_gates()
    assert invoked, (
        "no call sites parsed — the emitter REFUSES on that, so this probe would pass "
        "vacuously; it is asserted non-vacuous here"
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = emit_modes()
    assert rc == 0, f"emit_modes returned {rc} on a tree whose call sites DO parse"
    emitted = json.loads(buf.getvalue())
    declared, _note = declared_modes()
    assert emitted == invoked == declared, (
        "the emitted map, the call sites and the declaration must be ONE map — "
        f"emitted={len(emitted)}, invoked={len(invoked)}, declared={len(declared)}"
    )

def probe_the_EMITTER_refuses_an_empty_map() -> None:
    """Zero call sites must be a REFUSAL, never an empty map that reads as agreement."""
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "audit_with_no_call_sites.py"
        empty.write_text("x = 1\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = emit_modes(empty)
        assert rc == 2, (
            f"the emitter returned {rc} for zero call sites; an empty map declares nothing "
            f"and would read as agreement"
        )
        assert buf.getvalue() == "", (
            "the refusal printed to STDOUT — a caller capturing stdout would receive an "
            "empty map, which is the failure this refusal exists to prevent"
        )

def probe_the_ABSENT_manifest_is_a_stated_skip_and_never_a_PASS() -> None:
    """#219 -- the two shapes of the defect, both driven.

    The skip was written and UNREACHABLE: `declared_modes()` was hand-checked at each call
    site, applied twice and missed once, so the third instance raised `FileNotFoundError` out
    of a probe and the tree the kit ships from got a CRASH instead of the verdict the module
    docstring already specified. And the two guards that did exist paid a FALSE PASS: the loop
    labels a probe `PASS` after it has printed its own SKIP, so a green recorded no judgement.

    Arm 1 (reachability) drives the gate in a tree with no `registry/gates.json` and requires
    rc=0 with the skip PRINTED. Arm 2 (non-vacuity) requires that tree to carry NO `PASS` line
    at all -- an exit-0-only probe would satisfy arm 1 and miss the whole second defect.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "member"
        (tree / "tests").mkdir(parents=True)
        (tree / "tools").mkdir()
        # the gate AS IT SHIPS, beside a tree that has not adopted the declaration
        (tree / "tests" / "test_gate_invocation_mode.py").write_text(
            Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
        # ...and the tree's HELPER MODULES, because the gate's mode map now comes from the
        # shared predicate (#296) and that module carries its own helper import chain
        # (`rework_table`). A synthetic tree carrying the gate WITHOUT the helper set is not a
        # tree the kit ships -- it is a broken install, and driving it would test the import
        # graph rather than the absent manifest this arm is about. The helpers are exactly the
        # non-gate `.py` files beside this one.
        for helper in Path(__file__).parent.glob("*.py"):
            if helper.name.startswith("test_"):
                continue
            (tree / "tests" / helper.name).write_text(
                helper.read_text(encoding="utf-8"), encoding="utf-8")
        (tree / "tools" / "audit.py").write_text(
            AUDIT.read_text(encoding="utf-8"), encoding="utf-8")
        assert not (tree / "registry" / "gates.json").exists(), (
            "the fixture is not a no-manifest tree -- the arm would prove nothing")
        proc = subprocess.run(
            [sys.executable, "tests/test_gate_invocation_mode.py"],
            cwd=tree, capture_output=True, text=True, timeout=120,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            f"(219a) the absent-manifest tree must EXIT 0, not crash: rc={proc.returncode}; "
            f"{out.strip()[:300]}"
        )
        assert "SKIP" in out and "no registry/gates.json" in out, (
            f"(219a) the skip must be PRINTED with its reason: {out.strip()[:300]}"
        )
        assert "  PASS  " not in out, (
            "(219b) a probe was labelled PASS in a tree where nothing could be asserted -- "
            "the loop labels a probe PASS after it prints its own SKIP, so a green there "
            f"records no judgement: {out.strip()[:300]}"
        )
        assert "Traceback" not in out, (
            f"(219a) a traceback reached the caller instead of a verdict: {out.strip()[:300]}"
        )

def main() -> int:
# STATED SKIP: registry/gates.json (factory data)
    if "--emit-modes" in sys.argv[1:]:
        return emit_modes()
    # The manifest-state discrimination happens ONCE, here, ABOVE the probe loop.
    # The precondition belongs to the GATE, not to each call site: restated per probe it was
    # hand-applied twice and missed once (#219), which made the k-th instance a coin flip.
    # Above the loop it is also what makes the skip REACHABLE — and it removes the false-pass
    # path, where a probe that printed its own SKIP and returned was then labelled PASS by the
    # loop below, a pass for a probe that asserted nothing.
    try:
        declared, note = declared_modes()
    except FileNotFoundError:
        print(
            "  SKIP  no registry/gates.json in this tree — the invocation-mode declaration "
            "has not been adopted here, so there is nothing to assert against. This is a "
            "stated skip, never a silent pass."
        )
        return 0
    except ManifestUnreadable as exc:
        print(f"  FAIL  the declaration exists and cannot be read: {exc}")
        return 1
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("probe_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
            print(f"  PASS  {check.__name__}")
        except AssertionError as exc:
            failures.append(f"{check.__name__}: {exc}")
            print(f"  FAIL  {check.__name__} — {exc}")
    invoked = invoked_gates()
    print(
        f"  population: {len(invoked)} invoked gate(s) — "
        f"{sum(1 for m in invoked.values() if m == 'script')} script / "
        f"{sum(1 for m in invoked.values() if m == 'pytest')} pytest; {note}"
    )
    if failures:
        print(f"\ngate-invocation-mode gate FAILED: {len(failures)} probe(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\ngate-invocation-mode gate passed: {len(checks)} probe(s)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
