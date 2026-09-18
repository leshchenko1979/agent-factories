#!/usr/bin/env python3
"""Gate: a doc shipped in both the factory and the template must not drift.

`TEMPLATE/` is what a new factory bootstraps from. Some documents are carried in
both trees — the methodology core, the review lenses, the subject-matter
skeletons, the add-on packs — and `tests/test_template_sync.py` only guards the
*tool* copies. The documents were therefore unguarded, and they drifted: the
section shipped for issue #30 landed in `docs/methodology/04-harness-binding.md`
and never reached the template, so every factory bootstrapped afterwards would
have been born without it.

The rule this gate enforces: **a path present in both trees is byte-identical.**
A file that genuinely needs to differ is not a pair — it carries a `.tmpl`
suffix and lives outside the shared path (see `TEMPLATE/processes.md.tmpl`),
which is also what makes the difference visible instead of silent.

Run:  python3 tests/test_docs_sync.py
Exit: 0 in sync (or no template tree), 1 on drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED_ROOT = "docs"
TEMPLATE_ROOT = "TEMPLATE/docs"


def main() -> int:
    ours = REPO / SHARED_ROOT
    theirs = REPO / TEMPLATE_ROOT

    if not theirs.is_dir():
        # A bootstrapped factory has no TEMPLATE/ tree: there is nothing to pair.
        print(f"no {TEMPLATE_ROOT} tree — nothing to pair")
        return 0
    if not ours.is_dir():
        print(f"missing {SHARED_ROOT} tree", file=sys.stderr)
        return 1

    pairs = 0
    drifted: list[str] = []
    missing_in_root: list[str] = []

    for template_file in sorted(p for p in theirs.rglob("*") if p.is_file()):
        rel = template_file.relative_to(theirs)
        root_file = ours / rel
        if not root_file.is_file():
            missing_in_root.append(str(rel))
            continue
        pairs += 1
        if root_file.read_bytes() != template_file.read_bytes():
            drifted.append(str(rel))

    if drifted or missing_in_root:
        print("documentation drift:\n", file=sys.stderr)
        for d in drifted:
            print(
                f"  {TEMPLATE_ROOT}/{d} differs from {SHARED_ROOT}/{d}",
                file=sys.stderr,
            )
        for m in missing_in_root:
            print(
                f"  {SHARED_ROOT}/{m}: missing — the template ships it, the "
                f"factory does not",
                file=sys.stderr,
            )
        print(
            f"\nRe-copy: cp {SHARED_ROOT}/<path> {TEMPLATE_ROOT}/<path> — then "
            f"re-run this gate. If the two genuinely must differ, rename the "
            f"template copy to <name>.tmpl and move it out of the shared path.",
            file=sys.stderr,
        )
        return 1

    print(f"docs in sync: {pairs} shared document(s) byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
