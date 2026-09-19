#!/usr/bin/env python3
"""Shared gate fixtures — the tree a tool actually runs in.

Several gates build a throwaway tree by copying ONE file into it and running that
copy, so the probe cannot touch the live surface. That models a tree which stops
existing the moment the tool gains a neighbour import: `sys.path.insert(0,
REPO/"tools")` then points at a `tools/` holding no such module, and the tool dies
on `ModuleNotFoundError` before doing any work.

That is not hypothetical. When #53 clause 8 gave `tools/synthesize_insights.py` a
neighbour import — `import audit`, the one yield implementation, so two readers
could not drift apart — gate 23's fixture copied the tool alone and the tool could
not start. Worse, the gate's message blamed the row it was parsing ("a short row
must be skipped, not abort the pass"), sending the next reader to the wrong file.
The fix is to copy the tool's import CLOSURE, read from its source, so the fixture
follows the tool instead of a list somebody must remember to update.

This module holds no tests (the name has no `test_` prefix, so pytest does not
collect it) and no state: it is the fixture, shared, so three sites cannot drift.

Run:  imported by the gates, never run directly.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

def stage_tool(entry: Path, dest_dir: Path, search_dir: Path) -> list[Path]:
    """Copy `entry` AND its local import closure into `dest_dir`; return what was staged.

    This is the one way to build a throwaway tree. Copying the tool alone encodes an
    unstated assumption of self-containment that nothing checks, so it holds silently
    until the tool gains a lawful intra-repo import — and then the fixture breaks while
    the tool is correct (P35, meta-factory #60).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(entry, dest_dir / entry.name)
    staged = [entry]
    for module in local_import_closure(entry, search_dir):
        shutil.copy2(module, dest_dir / module.name)
        staged.append(module)
    return staged

def local_import_closure(entry: Path, search_dir: Path) -> list[Path]:
    """Every module in `search_dir` that `entry` imports, directly or transitively.

    Only modules that exist in `search_dir` are returned: a stdlib or third-party
    import resolves from the interpreter, and copying it would be wrong. The entry
    itself is excluded — the caller copies it separately, and on its own terms.

    The walk is transitive, so a neighbour that itself gains a neighbour is still
    copied. It reads the AST rather than importing, so it cannot execute the tool
    under test as a side effect of preparing a fixture for it.
    """
    found: set[Path] = set()
    queue: list[Path] = [entry]
    while queue:
        current = queue.pop()
        if current in found:
            continue
        found.add(current)
        tree = ast.parse(current.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                candidate = search_dir / f"{name}.py"
                if candidate.exists() and candidate not in found:
                    queue.append(candidate)
    found.discard(entry)
    return sorted(found)
