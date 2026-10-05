#!/usr/bin/env python3
"""Gate: the trigger map covers every gate, and an uncovered path NEVER buys a subset.

#294. The audit's pre-commit remedy was unexecutable: 54 gates / 1387.9 s measured against
5592.1 s of caps and a 600 s inline ceiling. HQ ruled the fix is to select by BLAST RADIUS
with DEFAULT-DENY -- a change names the paths it touches, the map turns those into the gates
that read them, and ANY path the map cannot cover buys the full suite rather than a guess.

Two properties are load-bearing and each is a probe here:

  * COVERAGE -- every gate the audit registers is reachable from the map (as a key, or on the
    floor). A gate missing from the map is a gate no change can ever select, which is a gate
    that has silently stopped running.
  * DEFAULT-DENY -- an uncovered path returns the FULL set. This is the one that must go RED
    the instant someone guts the branch, so the probe drives `select` with a synthetic
    mapping and compares the result against BOTH the full set and the union of matches: a
    gutted branch returns the union, and the two differ by exactly the gates the uncovered
    path could have needed.

Run: python3 tests/test_gate_triggers.py   (rc=0 clean)
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE_SELECT = REPO / "tools" / "gate_select.py"
LIVE_MAP = REPO / "registry" / "gate_triggers.json"
EXAMPLE_MAP = REPO / "TEMPLATE" / "registry" / "gate_triggers.example.json"
AUDIT = REPO / "tools" / "audit.py"
GATE_REGISTRY = REPO / "tests" / "gate_registry.py"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"PASS -- {label}")
    else:
        print(f"FAIL -- {label}{': ' + detail if detail else ''}")
        FAILURES.append(label)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _selector():
    return _load("oc_gate_select_map", GATE_SELECT)


# --- the absence contract (#199 / #322) --------------------------------------------
# STATED SKIP: registry/gate_triggers.json (factory data)
# THE MAP IS FACTORY DATA. The kit ships `registry/gate_triggers.example.json`, and a
# factory copies it to the live name (TEMPLATE/BOOTSTRAP.md) — so at the SHIPPED depth
# there is no map to resolve: `load_map` looks for the example under a nested `TEMPLATE/`,
# which only the ROOT tree has, and the five probes below that read the map have no
# subject. That is the #199 class — a gate that cannot pass in the tree it ships from —
# and its remedy is the #229 shape: the absence is DECLARED, never silent. The reason is
# stated here, and `tests/test_shipped_audit_runs.py` asserts this marker line is present.
#
# BOTH INVOCATION MODES MUST REACH THE GUARD (#195). The audit invokes this gate in
# PYTEST mode, and pytest never calls `main()`, so a guard there would protect only the
# script-mode run. `pytestmark` COLLECTS the tests and skips them (exit 0); a module-level
# `pytest.skip` would exit 5, which the audit reads as a failure.
def _map_skip_reason(root: Path) -> str:
    """A stated reason when no trigger map resolves in this tree, else "".

    The predicate is the SELECTOR's OWN `load_map`, never a second parse of the same
    absence (`docs/instruments/ledger.md` §9.8 "One field, one predicate"): if the
    instrument cannot read a map, the gate that judges the map has no subject — and the two
    can never disagree about which map is in force. A MISSING SELECTOR is not a skip: that
    is a defect, and it must FAIL.
    """
    if not GATE_SELECT.is_file():
        return ""
    try:
        mapping = _selector().load_map(root)
    except Exception:  # noqa: BLE001 — an unreadable selector is a FAIL, never a skip
        return ""
    if mapping is not None:
        return ""
    return (
        "no gate trigger map resolves in this tree: neither "
        f"{root / 'registry' / 'gate_triggers.json'} nor "
        f"{root / 'TEMPLATE' / 'registry' / 'gate_triggers.example.json'} is readable. "
        "The map is FACTORY DATA — the kit ships registry/gate_triggers.example.json and a "
        "factory copies it to the live name — so the shipped tree has no map to judge"
    )


_SKIP_REASON = _map_skip_reason(REPO)
if _SKIP_REASON:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(True, reason=_SKIP_REASON)


def _live_map() -> dict:
    """The map this tree resolves, through the SELECTOR's own loader.

    Not a direct read of `registry/gate_triggers.json`: a factory copies the shipped
    example to that path (TEMPLATE/BOOTSTRAP.md), and reading the path directly would make
    this gate fail in every tree that has not renamed the file yet — a gate that cannot
    pass where it is copied is the P36 defect. The selector resolves live-then-example, so
    the gate and the instrument cannot disagree about which map is in force.
    """
    mapping = _selector().load_map(REPO)
    if mapping is None:
        raise SystemExit(
            "FAIL -- no gate trigger map resolves in this tree: neither "
            f"{LIVE_MAP} nor {EXAMPLE_MAP} is readable. Copy the shipped map:\n"
            f"    cp {EXAMPLE_MAP} {LIVE_MAP}"
        )
    return mapping


def probe_every_registered_gate_is_covered() -> None:
    """Every gate the audit registers is a map key or sits on the floor."""
    module = _load("oc_gate_select_cover", GATE_SELECT)
    commands = module.registered_commands(REPO)
    mapping = _live_map()
    keys, floor = set(mapping.get("gates", {})), set(mapping.get("floor", []))
    missing = sorted(set(commands) - keys - floor)
    print(
        f"population: {len(commands)} registered gate(s), {len(keys)} map key(s), "
        f"{len(floor)} floor entr(y/ies)"
    )
    check(
        "the instrument can see the registration it judges",
        len(commands) > 0,
        f"registered_commands() returned {len(commands)} -- a clean verdict over an empty "
        f"population is not a verdict",
    )
    check(
        "every registered gate is reachable from the map",
        not missing,
        f"{len(missing)} gate(s) no change can select: {missing[:3]}",
    )


def probe_every_map_key_is_registered() -> None:
    """No key names a gate the audit does not register -- a stale key selects nothing."""
    module = _load("oc_gate_select_stale", GATE_SELECT)
    commands = set(module.registered_commands(REPO))
    keys = set(_live_map().get("gates", {}))
    stale = sorted(keys - commands)
    check(
        "no map key names a gate that is not registered",
        not stale,
        f"{len(stale)} stale key(s): {stale[:3]}",
    )


def probe_the_map_is_well_formed() -> None:
    """Shape: a stated default, a list floor, and non-empty string globs per gate."""
    mapping = _live_map()
    gates = mapping.get("gates", {})
    problems = [
        f"{gate}: empty or non-list globs"
        for gate, globs in gates.items()
        if not isinstance(globs, list) or not globs
    ]
    problems += [
        f"{gate}: non-string glob {glob!r}"
        for gate, globs in gates.items()
        if isinstance(globs, list)
        for glob in globs
        if not isinstance(glob, str) or not glob
    ]
    check("every gate carries at least one string glob", not problems, str(problems[:3])[:160])
    check(
        "the map DECLARES its default as `full` -- default-deny is stated, not inferred",
        mapping.get("default") == "full",
        f"default={mapping.get('default')!r}",
    )
    check(
        "the floor is a list",
        isinstance(mapping.get("floor"), list),
        f"floor={type(mapping.get('floor')).__name__}",
    )


def probe_the_example_carries_the_same_shape() -> None:
    """The shipped example is what a factory inherits -- it must name the same gates."""
    if not EXAMPLE_MAP.is_file():
        print(f"STATED SKIP -- {EXAMPLE_MAP} is absent from this tree, so the shipped shape "
              "cannot be compared; the resolved map was judged above")
        return
    example = json.loads(EXAMPLE_MAP.read_text(encoding="utf-8"))
    live = _live_map()
    check(
        "the example map names exactly the gates the live map names",
        set(example.get("gates", {})) == set(live.get("gates", {})),
        f"example={len(example.get('gates', {}))} live={len(live.get('gates', {}))}",
    )
    check(
        "the example states the same default and floor",
        example.get("default") == live.get("default")
        and set(example.get("floor", [])) == set(live.get("floor", [])),
        f"default={example.get('default')!r} floor={example.get('floor')!r}",
    )


def probe_globs_over_include_deliberately() -> None:
    """`*` crosses `/`: over-inclusion costs time, a silent miss costs correctness."""
    module = _load("oc_gate_select_glob", GATE_SELECT)
    check(
        "a `*` glob reaches a nested path",
        module.glob_matches("tools/*", "tools/nested/deep.py") is True,
        "fnmatch `*` no longer crosses `/` -- the map's coverage claim would weaken",
    )
    check(
        "and it still refuses a path outside the prefix",
        module.glob_matches("tools/*", "tests/x.py") is False,
    )


def probe_a_covered_change_selects_a_subset() -> None:
    """The money shot, direction one: a covered path yields the gates that read it."""
    module = _load("oc_gate_select_subset", GATE_SELECT)
    mapping = _live_map()
    result = module.select(mapping, ["evidence/rework.md"])
    check(
        "a covered change selects a subset",
        result["mode"] == "subset" and result["default_deny"] is False,
        f"mode={result['mode']} default_deny={result['default_deny']}",
    )
    check(
        "and the floor is always in it",
        set(mapping.get("floor", [])) <= set(result["gates"]),
        f"floor absent from {result['gates'][:4]}",
    )
    full = set(mapping.get("gates", {})) | set(mapping.get("floor", []))
    check(
        "and it is a strict subset of the full set",
        len(result["gates"]) < len(full),
        f"selected {len(result['gates'])} of {len(full)}",
    )


def probe_the_default_deny_cannot_be_neutered() -> None:
    """THE NEUTER PROBE. Gut the branch and this goes RED.

    The synthetic mapping is deliberately tiny so the two sets are computable by hand:
    `full` is floor | every key, `union` is floor | the keys that actually matched. A
    `select` that has lost its default-deny branch returns the union -- and the assertion
    below is written as `== full` AND `!= union`, so neither a shortened full set nor a
    widened union can satisfy it.
    """
    module = _load("oc_gate_select_neuter", GATE_SELECT)
    mapping = {
        "default": "full",
        "floor": ["tests/test_floor.py"],
        "gates": {"tests/test_a.py": ["a/*"], "tests/test_b.py": ["b/*"]},
    }
    full = {"tests/test_floor.py", "tests/test_a.py", "tests/test_b.py"}
    union = {"tests/test_floor.py", "tests/test_a.py"}
    result = module.select(mapping, ["a/one.py", "z/nowhere.py"])
    check(
        "an uncovered path returns the FULL set",
        set(result["gates"]) == full,
        f"got {sorted(result['gates'])}",
    )
    check(
        "which is STRICTLY larger than the union of matches -- a gutted branch returns the union",
        set(result["gates"]) != union,
        "the default-deny branch is gone: an uncovered path bought a subset",
    )
    check(
        "and the verdict declares itself default-deny",
        result["default_deny"] is True,
        f"default_deny={result['default_deny']!r}",
    )
    check(
        "and names the path it could not cover",
        result["uncovered"] == ["z/nowhere.py"],
        f"uncovered={result['uncovered']!r}",
    )
    check("and the mode says WHY it went full", result["mode"] == "full", result["mode"])
    covered = module.select(mapping, ["a/one.py"])
    check(
        "the other direction still holds: a fully covered change stays a subset",
        covered["mode"] == "subset" and covered["default_deny"] is False,
        f"mode={covered['mode']}",
    )


def probe_an_unreadable_map_is_none_not_empty() -> None:
    """`None` is an instrument that cannot read its declaration -- not an empty map."""
    module = _load("oc_gate_select_load", GATE_SELECT)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        check(
            "a root with no map resolves to None",
            module.load_map(root) is None,
            repr(module.load_map(root))[:80],
        )
        (root / "registry").mkdir()
        (root / "registry" / "gate_triggers.json").write_text("{ not json", encoding="utf-8")
        check(
            "a corrupt map resolves to None rather than to a silent empty one",
            module.load_map(root) is None,
            repr(module.load_map(root))[:80],
        )


def probe_the_cli_reports_the_mode() -> None:
    """End to end: the CLI's own verdict, on the two directions, as JSON."""
    covered = subprocess.run(
        [sys.executable, "tools/gate_select.py", "--paths", "evidence/rework.md", "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    uncovered = subprocess.run(
        [sys.executable, "tools/gate_select.py", "--paths", ".github/workflows/ci.yml", "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    try:
        covered_data = json.loads(covered.stdout)
        uncovered_data = json.loads(uncovered.stdout)
    except json.JSONDecodeError as exc:
        check("the CLI emits parseable JSON on both directions", False, f"{exc}: {covered.stderr[:120]}")
        return
    check(
        "a covered path exits 0 and reports a subset",
        covered.returncode == 0 and covered_data.get("mode") == "subset",
        f"rc={covered.returncode} mode={covered_data.get('mode')}",
    )
    check(
        "an uncovered path reports full and says why",
        uncovered_data.get("mode") == "full"
        and uncovered_data.get("default_deny") is True
        and uncovered_data.get("uncovered"),
        f"mode={uncovered_data.get('mode')} uncovered={uncovered_data.get('uncovered')}",
    )
    full = set(_live_map().get("gates", {})) | set(_live_map().get("floor", []))
    check(
        "and it hands over the whole suite, not a guess",
        set(uncovered_data.get("gates", [])) == full,
        f"{len(uncovered_data.get('gates', []))} of {len(full)}",
    )


PROBES = (
    probe_every_registered_gate_is_covered,
    probe_every_map_key_is_registered,
    probe_the_map_is_well_formed,
    probe_the_example_carries_the_same_shape,
    probe_globs_over_include_deliberately,
    probe_a_covered_change_selects_a_subset,
    probe_the_default_deny_cannot_be_neutered,
    probe_an_unreadable_map_is_none_not_empty,
    probe_the_cli_reports_the_mode,
)


def main() -> int:
    for relative in (GATE_SELECT, AUDIT, GATE_REGISTRY):
        if not relative.is_file():
            print(f"FAIL -- required artifact missing: {relative}")
            return 1
    if _SKIP_REASON:
        # The stated skip, for the SCRIPT face: a clean exit carrying its reason, exactly
        # as the pytest face does through `pytestmark`. A silent 0 would be a skip whose
        # reason has gone, which this factory counts as a defect (#199).
        print(f"gate triggers: SKIPPED — {_SKIP_REASON}")
        return 0
    for probe in PROBES:
        print(f"\n{probe.__name__}")
        probe()
    print(f"\n{len(PROBES) - len(FAILURES)} of {len(PROBES)} probe(s) clean")
    if FAILURES:
        print("failed: " + "; ".join(FAILURES))
        return 1
    print("gate triggers: the map covers every registered gate, and an uncovered path buys the full suite")
    return 0


# --- the pytest face ---------------------------------------------------------------
# `main()` owns the SCRIPT verdict, which is how `tools/audit.py` invokes this file. The
# wrappers below make each probe reachable as its own pytest node as well, so a factory
# that wires the kit into a PYTEST-based CI collects this gate instead of reading a green
# run over a file it never imported -- the hazard `tests/test_gate_invocation_mode.py`
# exists to name. The invocation MODE stays `script`: it is derived from this file's CALL
# SITE in `tools/audit.py`, and a dual-shaped file is judged by its call site, never by
# its shape. The assertion is on the FRESH failure delta, so a node fails only for the
# probe it names and never inherits a sibling's verdict.

def _assert_probe(probe) -> None:
    before = len(FAILURES)
    probe()
    fresh = FAILURES[before:]
    assert not fresh, "; ".join(fresh)

def test_probe_every_registered_gate_is_covered() -> None:
    _assert_probe(probe_every_registered_gate_is_covered)

def test_probe_every_map_key_is_registered() -> None:
    _assert_probe(probe_every_map_key_is_registered)

def test_probe_the_map_is_well_formed() -> None:
    _assert_probe(probe_the_map_is_well_formed)

def test_probe_the_example_carries_the_same_shape() -> None:
    _assert_probe(probe_the_example_carries_the_same_shape)

def test_probe_globs_over_include_deliberately() -> None:
    _assert_probe(probe_globs_over_include_deliberately)

def test_probe_a_covered_change_selects_a_subset() -> None:
    _assert_probe(probe_a_covered_change_selects_a_subset)

def test_probe_the_default_deny_cannot_be_neutered() -> None:
    _assert_probe(probe_the_default_deny_cannot_be_neutered)

def test_probe_an_unreadable_map_is_none_not_empty() -> None:
    _assert_probe(probe_an_unreadable_map_is_none_not_empty)

def test_probe_the_cli_reports_the_mode() -> None:
    _assert_probe(probe_the_cli_reports_the_mode)

if __name__ == "__main__":
    sys.exit(main())
