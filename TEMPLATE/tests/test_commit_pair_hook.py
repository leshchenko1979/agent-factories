#!/usr/bin/env python3
"""Gate: a commit must not stage one side of a declared byte pair without its twin.

Origin: #92, ruled at n=630. `tests/test_template_sync.py` has always caught a
one-sided pair — but only AFTER the commit landed, leaving a red on `main` for
the hours until the next audit ran. The class recurred (#80, then c3b60d5)
because nothing refused it at the only moment it is refusable: the commit.

This gate is the OFFLINE half. `tools/hooks/pre-commit` is the refusal point, and
this gate exists because an uninstalled hook is SILENT — the vacuous-pass shape
this repo forbids — so absence is a RED gate rather than an advisory.

Why the naive hook would be worse than none
-------------------------------------------
Running `tests/test_template_sync.py` in a `pre-commit` hook would read the
WORKING TREE, not the INDEX: a lane that staged one side and fixed the other
side on disk without staging it would get a PASS on a one-sided commit. That is
a green light on the exact defect the hook exists to catch, and it is worse than
no hook. The hook therefore reads `git diff --cached --name-only`, and the
probes below drive the predicate that consumes it.

What this gate asserts
----------------------
1. **The predicate, against synthetic state.** `one_sided` is exercised on
   synthetic pair lists and synthetic index contents, because a rule that has
   only ever seen good input has not been shown to reject bad input. Four cases:
   one side staged (reported, naming the staged path AND its twin), both sides
   (clean), neither (clean — no false fire on an unrelated commit), and an
   unrelated file staged (clean).
2. **One pair table, two call sites.** The hook must load the SAME `PAIRS` the
   gate reads. Asserted BEHAVIOURALLY — the hook's own loader is called and its
   result compared to this gate's table — not by grepping for a path string,
   because a lookalike table under the same name would satisfy a textual probe.
3. **The hook is itself paired and shippable.** `tools/hooks/pre-commit` and
   `TEMPLATE/tools/hooks/pre-commit` must both be declared in `PAIRS` (so a
   future edit that drops the entry fails here rather than silently unshipping
   the mechanism) and the twin must carry the EXECUTABLE bit. `test_template_sync.py`
   compares BYTES and is blind to the mode, so a non-executable twin would ship a
   hook git refuses to run — silent in every factory bootstrapped from it.
4. **The installation facts, LIVE.** Present, executable, reachable through
   `core.hooksPath`. The predicate is shared with `tests/test_ledger_commit_cites_no_rows.py`
   (issue #47's hook) via `tests/hook_installation.py` — one predicate, two call
   sites, because two implementations of one predicate drift and the drift is
   silent.

Scope statement: a factory bootstrapped from the template has no `TEMPLATE/` and
therefore no declared pairs. Its `PAIRS` is absent and the hook correctly fails
open. This gate states that condition and passes the table-dependent legs rather
than reporting a defect that is not one — the same reasoning `tests/test_close_row_revision.py`
applies to the BOOTSTRAP-created ledger. The installation legs still bite there,
because a hook is a mechanism everywhere.

Run:  python3 tests/test_commit_pair_hook.py
Exit: 0 the refusal point is shipped, wired, and rejects a one-sided staged set.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

HOOK_PATH = "tools/hooks/pre-commit"
HOOK_TWIN = "TEMPLATE/tools/hooks/pre-commit"
PAIR_TABLE_RELATIVE = "tests/test_template_sync.py"
TABLE_NAME = "PAIRS"
HOOKS_PATH_CONFIG = "tools/hooks"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_installation import (  # noqa: E402
    hook_installation_problems,
    hook_state_problems,
)

def repo_toplevel() -> Path | None:
    """The git top level containing this gate, so a copy in a subdirectory works.

    Resolved from git rather than from `__file__` so the ORIGINAL and the
    TEMPLATE twin judge the same repository — in this factory, both live in one
    work tree, and a twin that judged `TEMPLATE/` as its own repo would compare
    the pair table against a tree that does not have one.
    """
    proc = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    return Path(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else None

def load_module(path: Path, name: str):
    """Import a module by path, or None — neither `tools/hooks/` nor `tests/` is a package.

    The loader is named EXPLICITLY rather than inferred: `spec_from_file_location`
    picks a loader from the file's extension, and the hook this gate loads carries
    no extension at all (git requires `tools/hooks/pre-commit` to be named exactly
    that). Inference returns a spec with no loader for it, which would read as "the
    refusal point is not shipped" over a hook that is sitting right there — a false
    RED is cheaper than a false GREEN, but it is still a lie about the tree.
    """
    if not path.is_file():
        return None
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    if spec is None:
        return None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

def gate_pairs(top: Path) -> list[tuple[str, str]] | None:
    """`PAIRS` as this gate's own table defines it, or None when the table is absent."""
    module = load_module(top / PAIR_TABLE_RELATIVE, "oc_pair_table_expected")
    pairs = getattr(module, TABLE_NAME, None) if module else None
    return [(str(a), str(b)) for a, b in pairs] if pairs else None

def probe(hook_mod, pairs: list[tuple[str, str]]) -> list[str]:
    """Every rejection path, driven by SYNTHETIC state. Returns failure strings."""
    failures: list[str] = []

    # --- 1. the staged-set predicate -----------------------------------------
    synthetic = [("a/one", "b/one"), ("a/two", "b/two")]
    for staged, expected, why in (
        (["a/one"], [("a/one", "b/one")], "one side staged must be reported"),
        (["b/one"], [("b/one", "a/one")], "the twin side staged must be reported too"),
        (["a/one", "b/one"], [], "both sides staged must be clean"),
        ([], [], "an empty index must be clean"),
        (["unrelated.txt"], [], "an unrelated staged file must not false-fire"),
        (["a/one", "a/two"], [("a/one", "b/one"), ("a/two", "b/two")],
         "two split pairs must both be reported"),
    ):
        got = hook_mod.one_sided(synthetic, staged)
        if got != expected:
            failures.append(f"probe: {why} — got {got!r}, expected {expected!r}")

    # --- 2. one pair table, two call sites -----------------------------------
    top = repo_toplevel() or REPO
    loaded = hook_mod.load_pairs(top)
    if loaded is None:
        failures.append(
            f"probe: the hook could not load {TABLE_NAME} from {PAIR_TABLE_RELATIVE} — "
            "a second copy of the table is the drift this leg exists to prevent"
        )
    elif loaded != pairs:
        only_hook = [p for p in loaded if p not in pairs]
        only_gate = [p for p in pairs if p not in loaded]
        failures.append(
            "probe: the hook's pair table is NOT the gate's — "
            f"hook-only {only_hook[:3]}, gate-only {only_gate[:3]}"
        )

    # --- 3. the hook is itself paired, and the twin is executable ------------
    if (HOOK_PATH, HOOK_TWIN) not in pairs:
        failures.append(
            f"probe: ({HOOK_PATH}, {HOOK_TWIN}) is not declared in {TABLE_NAME} — "
            "the refusal point would not ship to a bootstrapped factory"
        )
    twin = top / HOOK_TWIN
    if not twin.is_file():
        failures.append(f"probe: {HOOK_TWIN} is absent — the mechanism does not ship")
    elif not os.access(twin, os.X_OK):
        failures.append(
            f"probe: {HOOK_TWIN} is not executable — byte-identity is satisfied but a "
            "bootstrapped factory inherits a hook git will not run"
        )

    # --- 4. the shared installation predicate --------------------------------
    ok = dict(
        hook_path=HOOK_PATH,
        hooks_path_config=HOOKS_PATH_CONFIG,
        exists=True,
        executable=True,
        configured=HOOKS_PATH_CONFIG,
    )
    if hook_state_problems(**ok):
        failures.append("probe: a present, executable, wired hook must report clean")
    for override, why in (
        ({"exists": False, "executable": False}, "a missing hook"),
        ({"exists": True, "executable": False}, "a hook git cannot execute"),
        ({"exists": True, "executable": True, "configured": ""}, "an unwired hook"),
        (
            {"exists": True, "executable": True, "configured": ".git/hooks"},
            "a hook reachable only through a foreign hooksPath",
        ),
    ):
        if not hook_state_problems(**{**ok, **override}):
            failures.append(f"probe: {why} must be reported, not passed")

    return failures

def main() -> int:
    top = repo_toplevel() or REPO
    problems: list[str] = []

    hook_mod = load_module(top / HOOK_PATH, "oc_pre_commit_hook")
    if hook_mod is None:
        print(f"{HOOK_PATH} could not be loaded — the refusal point is not shipped.")
        return 1

    pairs = gate_pairs(top)
    if pairs is None:
        print(
            f"note: no {PAIR_TABLE_RELATIVE} in this tree — a bootstrapped factory has no "
            "TEMPLATE/ and therefore no declared pairs, so the staged-set legs are not "
            "applicable here. The hook fails open by design; the installation legs below "
            "still bind."
        )
    else:
        problems.extend(probe(hook_mod, pairs))

    problems.extend(hook_installation_problems(top, HOOK_PATH, HOOKS_PATH_CONFIG))

    if problems:
        print("commit pair hook problems:\n")
        for p in problems:
            print(f"  {p}")
        return 1

    print(f"commit pair hook ok: {HOOK_PATH} shipped, executable, wired via core.hooksPath")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
