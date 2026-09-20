#!/usr/bin/env python3
"""The rework log's entries table — ONE parse, shared by every reader of it.

**Owns:** the SHAPE of `evidence/rework.md`'s entries table — which section holds the
entries, which line is the header, which is the separator, and how a row becomes cells.

Why this module exists rather than two parses
---------------------------------------------
Two call sites read this table. `tests/test_rework.py` gates its completeness, its
contiguity and its vocabulary. `tests/gate_registry.py` reads ONE COLUMN of it — the
`Prevented by` cell, the column section 11 makes a law surface — to find the mechanisms a
recorded law names, so it can assert that each one is actually REGISTERED (issue #107,
ruling n=639, direction 4).

A second parser is the defect this repo already names: one field, one predicate. The
failure it produces is SILENT, which is why it is worth a module. Two parsers agree until
the day a cell count or a column order changes, and then one of them returns another
column's values under the name it asked for — a reader that reads the wrong field and
reports it as the field it named. `column_index` below is derived from the table's own
header for exactly that reason: a hardcoded index keeps reading that index after a
reorder, while a header read fails loudly with `None`.

A shared module under `tests/` is the established pattern here, not a new idea:
`tests/ledger_boundary.py`, `tests/hook_installation.py` and `tests/gate_fixtures.py` are
the same shape — a pure predicate with two call sites, paired into `TEMPLATE/` so every
bootstrapped factory carries it.
"""

from __future__ import annotations

import re

# The header row is recognised by its FIRST CELL rather than by an exact string, so a
# reordered or re-worded table is still parsed as a table. `test_rework.py` asserts the
# header's exact cells; this module only needs to find the row.
def is_header(line: str) -> bool:
    """True when the line is a table's header row (its first cell starts with 'date')."""
    return line.startswith("|") and (
        line.strip("|").split("|")[0].strip().lower().startswith("date")
    )

def is_separator(line: str) -> bool:
    """True when the line is a markdown separator row (`|---|---|`)."""
    return line.startswith("|") and set(line) <= set("|-: ")

def section_body(text: str, heading: str) -> str | None:
    """The body of a `## <heading>` section, or None when the section is absent.

    None rather than "" for an absent section, because an empty body is a section that
    exists and says nothing — a different fact, and one a caller must not confuse with a
    section it failed to find.
    """
    pattern = rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.M | re.S)
    return match.group(1) if match else None

def entry_rows(body: str) -> list[tuple[int, list[str]]]:
    """Rows of an entries table: (line number within the section, cells).

    Header and separator rows are skipped, and every other `|` line becomes a row — a
    blank line does NOT end the table here, deliberately: contiguity is a property the
    rework gate asserts, and a parser that silently stopped at a gap would hide the very
    fragmentation that gate exists to report.
    """
    out: list[tuple[int, list[str]]] = []
    for n, line in enumerate(body.splitlines(), 1):
        line = line.strip()
        if not line.startswith("|") or is_separator(line) or is_header(line):
            continue
        out.append((n, [c.strip() for c in line.strip("|").split("|")]))
    return out

def column_index(body: str, column: str) -> int | None:
    """The index of a named column, read from the table's OWN header row.

    `None` when there is no header row or no such column. Derived rather than hardcoded:
    a reader that assumes a column's position keeps reading that position after the table
    is reordered, and returns another column's values under the name it asked for.
    """
    for line in body.splitlines():
        line = line.strip()
        if not is_header(line):
            continue
        for index, cell in enumerate(line.strip("|").split("|")):
            if cell.strip().lower() == column.lower():
                return index
        return None
    return None

def column_cells(
    text: str, heading: str, column: str
) -> tuple[list[tuple[int, str]], str | None]:
    """(rows, reason) — the named column's cell per entry row, or why it could not be read.

    `reason` is None on success. A missing section, a missing header row and a missing
    column are each REPORTED rather than returned as an empty list: an empty result from
    an unparsed region is indistinguishable from a table with nothing in it, and this
    repo has already produced that exact false pass once.

    A row too short to carry the column yields "" for that row. That is not silence — a
    short row is a malformed row, and `tests/test_rework.py` fails it on its own terms;
    this function's job is to hand back what the column holds, not to re-gate the table.
    """
    body = section_body(text, heading)
    if body is None:
        return [], f"no '## {heading}' section"
    index = column_index(body, column)
    if index is None:
        return [], f"the '{heading}' table has no '{column}' column"
    rows: list[tuple[int, str]] = []
    for n, cells in entry_rows(body):
        rows.append((n, cells[index] if index < len(cells) else ""))
    return rows, None
