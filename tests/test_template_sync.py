#!/usr/bin/env python3
"""Gate: the template's copies of the gates must match the originals.

`TEMPLATE/tools/ledger.py` and `TEMPLATE/tests/*.py` are copies — a factory
bootstraps by copying the template, so the template has to carry them. But a
copy that drifts is the same defect the ledger exists to prevent: two versions
of one thing, and the one nobody reads is the one that is wrong.

So the copies are checked byte-for-byte against their originals.

This file is deliberately NOT copied into the template: it guards the pair, and
a copy of a pair-guard would need its own pair-guard.

Run:  python3 tests/test_template_sync.py
Exit: 0 in sync, 1 drifted.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PAIRS = [
    ("tools/ledger.py", "TEMPLATE/tools/ledger.py"),
    ("tests/test_ontology.py", "TEMPLATE/tests/test_ontology.py"),
    ("tests/test_ledger.py", "TEMPLATE/tests/test_ledger.py"),
]


def main() -> int:
    drifted: list[str] = []
    for original, copy in PAIRS:
        a, b = REPO / original, REPO / copy
        if not a.is_file():
            drifted.append(f"{original}: missing")
            continue
        if not b.is_file():
            drifted.append(f"{copy}: missing — the template does not ship it")
            continue
        if a.read_bytes() != b.read_bytes():
            drifted.append(f"{copy} differs from {original}")

    if drifted:
        print("template drift:\n")
        for d in drifted:
            print(f"  {d}")
        print("\nRe-copy: cp <original> <copy> — then re-run this gate.")
        return 1

    print(f"template in sync: {len(PAIRS)} pair(s) byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
