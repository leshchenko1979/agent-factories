#!/usr/bin/env python3
"""Blast-radius gate selection — the gate set a change REQUIRES (issue #294).

The audit's pre-commit remedy ("run `tools/audit.py` before a commit that touches
the surface") was unexecutable: `registry/gates.json` declares 1387.9 s of measured
runtime against a 600 s inline ceiling, so the author fell back to a hand-picked
subset — and the author is structurally the least likely to pick the gate that reads
their own edit (#197's close landed RED on `main` for ~4 min that way).

This module removes the author from the SELECTION. The gate set is derived from the
CHANGED PATHS alone, through the declared map `registry/gate_triggers.json`.

**DEFAULT-DENY is the safety property, and it is not the map's completeness.** Any
changed path matching no declared glob forces the FULL gate set. An incomplete map
degrades to SLOW, never to SILENT — a subset that misses is the defect this module
exists to remove.

One predicate, several call sites: the pre-commit leg, the manual run, and
`tests/test_gate_triggers.py` all import `select()` rather than re-deriving the set.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

MAP_RELATIVE = "registry/gate_triggers.json"
MAP_EXAMPLE_RELATIVE = "TEMPLATE/registry/gate_triggers.example.json"
AUDIT_RELATIVE = "tools/audit.py"
GATE_REGISTRY_RELATIVE = "tests/gate_registry.py"
DEFAULT = "full"


def glob_matches(glob: str, path: str) -> bool:
    """Whether a changed path is covered by one declared glob.

    fnmatch semantics, so `*` also crosses `/` — over-inclusion is deliberate. A
    gate listed on a path it does not read costs only time; a gate MISSING from a
    path it reads is the silent miss this map exists to remove.
    """
    return fnmatch.fnmatchcase(path, glob)


def load_map(root: Path) -> dict | None:
    """The declared map, or None when it is absent (which the caller reads as full).

    The LIVE map is preferred; the shipped example is the fallback so a factory that
    has not yet copied it still resolves a map rather than silently selecting nothing.
    `None` is not "empty": it is an instrument that cannot read its declaration, and
    the caller turns it into the FULL set with a stated reason.
    """
    for relative in (MAP_RELATIVE, MAP_EXAMPLE_RELATIVE):
        candidate = root / relative
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            if isinstance(data, dict) and isinstance(data.get("gates"), dict):
                return data
    return None


def select(mapping: dict, paths: list[str]) -> dict:
    """The selection for a set of changed paths — PURE, so a probe can drive it.

    Returns `{mode, gates, uncovered, default_deny}`:
      * `mode == "subset"` — every path was covered; `gates` is floor ∪ matches.
      * `mode == "full"`   — some path matched no declared glob (or the map could not
        be read); `gates` is the FULL set and `uncovered` names the offending paths,
        so the verdict says WHY it went full rather than only that it did.
    """
    gates = mapping.get("gates", {}) if isinstance(mapping, dict) else {}
    floor = set(mapping.get("floor", [])) if isinstance(mapping, dict) else set()
    selected = set(floor)
    uncovered: list[str] = []
    for path in paths:
        hit = [
            gate
            for gate, globs in gates.items()
            if any(glob_matches(str(glob), path) for glob in globs)
        ]
        if hit:
            selected.update(hit)
        else:
            uncovered.append(path)
    if uncovered:
        return {
            "mode": "full",
            "gates": sorted(floor | set(gates)),
            "uncovered": sorted(set(uncovered)),
            "default_deny": True,
        }
    return {"mode": "subset", "gates": sorted(selected), "uncovered": [], "default_deny": False}


def changed_paths_staged(root: Path) -> list[str] | None:
    """The index's pending paths, or None when the index cannot be read."""
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--name-only", "-z"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.split("\0") if p]


def changed_paths_range(root: Path, rev_range: str) -> list[str] | None:
    """The paths a revision range touched, or None when git cannot read it."""
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "-z", rev_range],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.split("\0") if p]


def _load_module(root: Path, relative: str, name: str):
    """Import a module by path — the pattern the pre-commit hook already uses."""
    source = root / relative
    if not source.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def registered_commands(root: Path) -> dict[str, list[str]]:
    """`{gate target: argv}` read from the audit's own registration.

    The argv comes from `tests/gate_registry.registration_entries` — the SAME scan
    `tests/test_gate_registration.py` and `tests/test_gate_invocation_mode.py` read —
    so the selector cannot disagree with the audit about how a gate is invoked.
    """
    registry = _load_module(root, GATE_REGISTRY_RELATIVE, "oc_gate_registry")
    audit = root / AUDIT_RELATIVE
    if registry is None or not audit.is_file():
        return {}
    commands: dict[str, list[str]] = {}
    for entry in registry.registration_entries(audit.read_text(encoding="utf-8")):
        commands.setdefault(entry["target"], entry["argv"].split())
    return commands


def run_gates(root: Path, gates: list[str]) -> list[str]:
    """Run each gate's registered argv; return the failures, each naming the gate.

    The registered argv is interpreter-RELATIVE: `registered_commands` scans the audit's
    call sites and keeps only the TARGET-shaped tokens, dropping the `sys.executable` the
    audit prefixes every append with. The interpreter is put back HERE (#416) -- without it
    a script gate (`tests/x.py`, mode 100644) dies with PermissionError and a pytest gate
    (`-m pytest`) with FileNotFoundError, so the remedy the pre-commit hook prints could
    run no gate at all.

    A gate with no registered argv is reported as a FAILURE rather than skipped: a
    gate the selector names but cannot run is an instrument that lies, and skipping it
    silently is the very class this module removes. An argv that cannot be EXECUTED is
    the same class, so it is reported rather than raised.
    """
    commands = registered_commands(root)
    failures: list[str] = []
    for gate in gates:
        argv = commands.get(gate)
        if argv is None:
            failures.append(f"{gate} — no registered argv in {AUDIT_RELATIVE}")
            continue
        try:
            proc = subprocess.run(
                [sys.executable, *argv], cwd=str(root), capture_output=True, text=True
            )
        except OSError as exc:
            failures.append(f"{gate} — could not execute: {exc}")
            continue
        if proc.returncode != 0:
            failures.append(f"{gate} — rc={proc.returncode}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select the gates a change requires.")
    parser.add_argument("--repo-root", default=None)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true")
    group.add_argument("--range", dest="rev_range")
    group.add_argument("--paths", nargs="+")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--run", action="store_true", help="run the selected gates")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()

    if args.paths:
        paths = args.paths
    elif args.staged:
        paths = changed_paths_staged(root)
        if paths is None:
            print("gate-select: the index could not be read; defaulting to FULL.", file=sys.stderr)
            paths = []
    else:
        paths = changed_paths_range(root, args.rev_range)
        if paths is None:
            print("gate-select: the range could not be read; defaulting to FULL.", file=sys.stderr)
            paths = []

    mapping = load_map(root)
    if mapping is None:
        # An unreadable declaration is not an empty map: state the reason and go full.
        full = sorted(set((mapping or {}).get("gates", {})))
        print("gate-select: %s could not be read; defaulting to FULL." % MAP_RELATIVE,
              file=sys.stderr)
        if args.json:
            print(json.dumps({"mode": "full", "gates": full, "uncovered": [],
                              "default_deny": True, "reason": "map unreadable"}))
        return 0

    result = select(mapping, paths)

    if args.json:
        print(json.dumps(result))
    else:
        header = (
            f"gate-select: {len(result['gates'])} gate(s), mode={result['mode']}"
            + (f", default-deny on {len(result['uncovered'])} uncovered path(s)"
               if result["default_deny"] else "")
        )
        print(header)
        if result["default_deny"]:
            print("  DEFAULT-DENY — these paths match no declared trigger:")
            for path in result["uncovered"]:
                print(f"    {path}")
            print("  The FULL gate set is selected; run the whole audit (it exceeds the")
            print("  600 s inline ceiling, so it runs DETACHED):  python3 tools/audit.py")
        for gate in result["gates"]:
            print(gate)

    if args.run:
        failures = run_gates(root, result["gates"])
        for failure in failures:
            print(f"gate-select: FAILED {failure}", file=sys.stderr)
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
