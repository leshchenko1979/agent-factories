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

import ast
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / "tools" / "audit.py"
MANIFEST = REPO / "registry" / "gates.json"

# The two conventions, and ONLY these two: a third would be a new call-site form nobody
# declared, which is the class this gate exists to make loud rather than silently unjudged.
MODES = ("script", "pytest")

class ManifestUnreadable(Exception):
    """`registry/gates.json` exists and cannot be read -- a failure, never a skip."""

def invoked_gates(audit_path: Path = AUDIT) -> dict[str, str]:
    """Every gate the audit invokes, mapped to the convention its CALL SITE uses.

    Parsed with `ast`, never a regex: the appends span several lines, and a regex over them
    under-counts (a pattern-based read of this file produced a false "no call site" finding
    for four entries before an AST corrected it). The population is the call sites and not a
    glob, because a gate that ships but is never invoked owes no mode.
    """
    tree = ast.parse(audit_path.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "append"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "gates_to_run"):
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.List):
            continue
        argv = [
            e.value for e in node.args[0].elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        paths = [a for a in argv if a.endswith(".py")]
        if not paths:
            continue
        mode = "pytest" if ("-m" in argv and "pytest" in argv) else "script"
        path = paths[-1]
        if path in found:
            # A path invoked twice is reported by the both-forms probe below; keeping the
            # FIRST form here would silently pick a winner, so the map holds the pair.
            found[path] = f"{found[path]}+{mode}"
        else:
            found[path] = mode
    return found

def declared_modes(manifest_path: Path = MANIFEST) -> tuple[dict[str, str], str]:
    """`(modes, note)` from the manifest, or raises `ManifestUnreadable`."""
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestUnreadable(f"{manifest_path}: cannot be read as JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestUnreadable(f"{manifest_path}: the manifest must be a JSON object")
    modes = data.get("modes")
    if not isinstance(modes, dict):
        raise ManifestUnreadable(
            f"{manifest_path}: no `modes` object — the invocation convention is undeclared, "
            f"which is the state #195 exists to end (a consumer cannot compute their CI's "
            f"population from it)"
        )
    for key, value in modes.items():
        if value not in MODES:
            raise ManifestUnreadable(
                f"{manifest_path}: modes[{key!r}] = {value!r} is not one of {'/'.join(MODES)}"
            )
    return modes, f"{manifest_path.name}: {len(modes)} declared mode(s)"

def problems(invoked: dict[str, str], declared: dict[str, str]) -> list[str]:
    """Every mismatch between the call sites and the declaration, as named findings."""
    out: list[str] = []
    for path in sorted(invoked):
        form = invoked[path]
        if "+" in form:
            forms = sorted(set(form.split("+")))
            out.append(
                f"{path}: invoked under BOTH forms ({', '.join(forms)}) — the call site's form "
                f"is ambiguous, so no single declared mode can be right"
            )
            continue
        want = declared.get(path)
        if want is None:
            out.append(
                f"{path}: invoked as `{form}` by the audit and carries NO declared mode — a "
                f"consumer cannot tell whether a pytest-based CI reaches it"
            )
        elif want != form:
            out.append(
                f"{path}: declared `{want}` but the audit invokes it as `{form}` — a "
                f"declaration that can drift from its call site is one field read two ways"
            )
    for path in sorted(set(declared) - set(invoked)):
        out.append(
            f"{path}: declared `{declared[path]}` and NOT invoked by the audit — a declaration "
            f"about a gate that does not run is a claim nobody can check"
        )
    return out

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
    # THE DECLARATION IS FACTORY DATA (#199). The shipped tree carries no
    # `registry/gates.json` — the kit ships the SHAPE, `registry/gates.example.json`, because a
    # bootstrapped factory must measure its own runtimes and cannot inherit this box's. Without
    # this guard the probe raised FileNotFoundError inside the tree the kit ships from, which is
    # a crash rather than a verdict; the mode declaration simply does not exist to compare
    # against there, and `main` states that skip separately.
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
