#!/usr/bin/env python3
"""Gate: every rework entry is complete.

`evidence/rework.md` is only worth having if an entry can be read by someone who
was not there. A row with an empty root cause, or "Prevented by: TBD", is a
placeholder that looks like a record — and the improvement-loop criterion (S3)
turns on that last column actually naming something.

Run:  python3 tests/test_rework.py
Exit: 0 all entries complete, 1 an entry is incomplete or malformed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REWORK = REPO / "evidence" / "rework.md"

COLUMNS = ["Date", "Source", "Defect", "Root cause", "Resolution", "Prevented by"]
PLACEHOLDERS = {"tbd", "todo", "n/a", "-", "?", "unknown", "none"}


def entry_rows(text: str) -> list[tuple[int, list[str]]]:
    """Rows of the Entries table: (line number, cells)."""
    section = re.search(r"^## Entries\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not section:
        sys.exit("rework.md has no '## Entries' section — cannot gate")
    out = []
    for n, line in enumerate(section.group(1).splitlines(), 1):
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0].lower().startswith("date"):
            continue
        out.append((n, cells))
    return out


def main() -> int:
    if not REWORK.is_file():
        sys.exit("evidence/rework.md is missing")
    rows = entry_rows(REWORK.read_text(encoding="utf-8"))

    problems: list[str] = []
    if not rows:
        problems.append("no entries — an empty log cannot report a rework rate")

    for n, cells in rows:
        if len(cells) != len(COLUMNS):
            problems.append(f"row {n}: {len(cells)} cells, expected {len(COLUMNS)}")
            continue
        date = cells[0]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            problems.append(f"row {n}: date {date!r} is not YYYY-MM-DD")
        for label, value in zip(COLUMNS[1:], cells[1:]):
            if not value:
                problems.append(f"row {n} ({date}): '{label}' is empty")
            elif value.strip("`").strip().lower() in PLACEHOLDERS:
                problems.append(
                    f"row {n} ({date}): '{label}' is a placeholder ({value!r}) — "
                    "say what is true, or 'nothing yet'"
                )

    if problems:
        print(f"rework log incomplete: {len(problems)} problem(s)\n")
        for p in problems:
            print(f"  {p}")
        return 1

    print(f"rework log clean: {len(rows)} complete entry(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
