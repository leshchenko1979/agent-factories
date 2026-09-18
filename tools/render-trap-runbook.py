#!/usr/bin/env python3
"""Render the Trap Runbook as a standalone document for a human reader.

The canonical text lives in `docs/methodology/01-llm-weakness-counters.md`
(sections 4-7): the mirror test, the management analogy, the ten traps, and the
limits of the analogy. That file is written for an agent that will act on it,
inside a methodology core with the taxonomy above it.

A reader who has not seen the taxonomy needs the same text without the rest of
the core around it. Copying it into a second file would create a second source
of truth that drifts the moment either copy is edited, so the standalone
document is *derived*: this script extracts the four sections and prepends a
provenance line naming the file they came from.

    python3 tools/render-trap-runbook.py                 # -> evidence/deliverables/<date>-trap-runbook.md
    python3 tools/render-trap-runbook.py --out /tmp/x.md

The output is a build product. Edit the methodology, re-run this, and the
deliverable follows; never edit the deliverable.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "docs" / "methodology" / "01-llm-weakness-counters.md"

# The runbook starts at the mirror test and runs to the end of the file.
FIRST_SECTION = "## 4. The Mirror Test"

PROVENANCE = """\
# The Trap Runbook — agent failures, and what to do about them

> Extracted from `docs/methodology/01-llm-weakness-counters.md` sections 4-7 —
> that file is the source of truth, this is a rendering of it. Regenerate with
> `python3 tools/render-trap-runbook.py`.

The extract opens by referring to "the taxonomy above", which is section 1 of the
source and is not repeated here. It splits agent failures by *generative
mechanism*, because each mechanism takes a different remedy:

| Family | Mechanism | Remedy that works |
|---|---|---|
| **Epistemic** | A fact that was never in context | Grounding — deterministic exit codes, same-turn receipts |
| **Context-capacity** | A fact that *was* in context and is gone | Flush to durable state before the summary |
| **Behavioral bias** | Training rewards politeness over convergence | An external driver — a goal, a pacemaker, a gate |
| **Operational friction** | Unbounded search, cascading errors | Stop on first defect, atomic work units, single accountability |

Getting the family wrong is what produces the useless counter: more rules for a
capacity failure, or a plea to "be careful" for a bias. Section 4 is the test
that tells them apart.

"""


def extract(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    start = text.find(FIRST_SECTION)
    if start < 0:
        raise SystemExit(f"{source}: could not find '{FIRST_SECTION}'")
    body = text[start:].rstrip() + "\n"
    return PROVENANCE + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if not SOURCE.is_file():
        raise SystemExit(f"missing source: {SOURCE}")

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    out = args.out or (REPO_ROOT / "evidence" / "deliverables" / f"{today}-trap-runbook.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(extract(SOURCE), encoding="utf-8")

    lines = out.read_text(encoding="utf-8").count("\n")
    print(f"wrote {out} ({lines} lines) from {SOURCE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
