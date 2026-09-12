#!/usr/bin/env python3
"""Gate: every rework entry is complete, and the table is still one table.

`evidence/rework.md` is only worth having if an entry can be read by someone who
was not there. A row with an empty root cause, or "Prevented by: TBD", is a
placeholder that looks like a record — and the improvement-loop criterion (S3)
turns on that last column actually naming something.

The second property is the one this gate originally missed: the entries are a
*single* table, so a blank line inside it splits the log into fragments and the
rows after the break render with no header above them. The gate reported a clean
pass over exactly that shape, because it parsed the rows it expected to find and
never asked whether they were still contiguous. A check that only looks for what
its author expected is not a check.

Run:  python3 tests/test_rework.py
Exit: 0 all entries complete and contiguous, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REWORK = REPO / "evidence" / "rework.md"

COLUMNS = ["Date", "Source", "Defect", "Root cause", "Resolution", "Prevented by"]
PLACEHOLDERS = {"tbd", "todo", "n/a", "-", "?", "unknown", "none"}

HEADER = "| Date | Source | Defect | Root cause | Resolution | Prevented by |"
SEPARATOR = "|---|---|---|---|---|---|"

def section_body(text: str) -> str | None:
    """The body of the `## Entries` section, or None when it is absent."""
    match = re.search(r"^## Entries\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else None

def is_header(line: str) -> bool:
    return line.startswith("|") and line.strip("|").split("|")[0].strip().lower().startswith("date")

def is_separator(line: str) -> bool:
    return line.startswith("|") and set(line) <= set("|-: ")

def entry_rows(body: str) -> list[tuple[int, list[str]]]:
    """Rows of the Entries table: (line number within the section, cells)."""
    out = []
    for n, line in enumerate(body.splitlines(), 1):
        line = line.strip()
        if not line.startswith("|") or is_separator(line) or is_header(line):
            continue
        out.append((n, [c.strip() for c in line.strip("|").split("|")]))
    return out

def contiguity_problems(body: str, parsed: int) -> list[str]:
    """The entries must be one table under one header — not fragments."""
    lines = [line.strip() for line in body.splitlines()]
    headers = [i for i, line in enumerate(lines) if is_header(line)]
    if len(headers) != 1:
        return [f"the Entries section has {len(headers)} header row(s), expected exactly 1"]
    head = headers[0]
    if head + 1 >= len(lines) or not is_separator(lines[head + 1]):
        return ["the line after the Entries header is not a separator row"]
    # The block is the header plus every *consecutive* following `|` line: a
    # blank line ends it, which is precisely what makes the rows after the gap
    # render headerless.
    block = 0
    i = head + 2
    while i < len(lines) and lines[i].startswith("|"):
        block += 1
        i += 1
    if block != parsed:
        return [
            f"the Entries table is fragmented: {parsed} entry row(s) parsed, "
            f"{block} sit under one contiguous header"
        ]
    return []

def check_text(text: str) -> tuple[list[str], int]:
    """(problems, entry count) for a rework document — pure, so it can be probed."""
    body = section_body(text)
    if body is None:
        return ["no '## Entries' section — cannot gate"], 0

    rows = entry_rows(body)
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

    problems.extend(contiguity_problems(body, len(rows)))
    return problems, len(rows)

def probe(name: str, text: str, want_problems: bool, failures: list[str]) -> None:
    problems, _ = check_text(text)
    ok = bool(problems) == want_problems
    detail = problems[0] if problems else "no problems"
    print(f"  {'PASS' if ok else 'FAIL'}  {name} — {detail}")
    if not ok:
        failures.append(name)

def good_row(n: int) -> str:
    return f"| 2026-09-12 | probe {n} | defect {n} | cause {n} | fix {n} | gate {n} |"

def main() -> int:
    if not REWORK.is_file():
        sys.exit("evidence/rework.md is missing")

    problems, count = check_text(REWORK.read_text(encoding="utf-8"))
    if problems:
        print(f"rework log incomplete: {len(problems)} problem(s)\n")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"rework log clean: {count} complete entry(s)")

    # The gate is probed on synthetic documents, in-process: it never writes a
    # temp file and never re-invokes itself, so a probe cannot become the
    # defect it is testing for.
    print("\nthe gate's own probes")
    failures: list[str] = []
    two_rows = f"## Entries\n\n{HEADER}\n{SEPARATOR}\n{good_row(1)}\n{good_row(2)}\n"
    probe("a well-formed two-row table passes", two_rows, False, failures)
    probe(
        "a blank line after the header is caught",
        f"## Entries\n\n{HEADER}\n{SEPARATOR}\n\n{good_row(1)}\n",
        True, failures,
    )
    probe(
        "a blank line between two rows is caught",
        f"## Entries\n\n{HEADER}\n{SEPARATOR}\n{good_row(1)}\n\n{good_row(2)}\n",
        True, failures,
    )
    probe(
        "a duplicated header is caught",
        f"## Entries\n\n{HEADER}\n{SEPARATOR}\n{good_row(1)}\n{HEADER}\n{SEPARATOR}\n{good_row(2)}\n",
        True, failures,
    )

    print()
    if failures:
        print(f"rework gate FAILED: {len(failures)} probe(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("rework gate passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
