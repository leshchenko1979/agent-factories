#!/usr/bin/env python3
"""Shared helper: the ledger boundary a gate reads, DECLARED in the factory's own tree.

Origin (issue #78, ruled at ledger `n=515` clause 4). `tests/test_close_row_revision.py`
and `tests/test_score_gate_recorded.py` both assert an invariant over the live
`evidence/ledger.jsonl`, and both hardcoded the moment that invariant landed *in this
factory*. That made them unusable in `TEMPLATE/`: `TEMPLATE/evidence/` does not exist —
the ledger is BOOTSTRAP-created (`TEMPLATE/BOOTSTRAP.md`) — so a copy of either file
raised `FileNotFoundError`. RED on the very tree it ships to. That is #76's class, and
this is its second instance: **a byte-paired gate asserting a live-tree fact its own tree
cannot satisfy** (P35). #328 clause 4 makes a second instance a PROCESS defect whose
remedy is a MECHANISM, which is why the reader below is shared rather than repeated.

The ruled form splits the two halves:

* the gate's LOGIC is universal — *a row written after the boundary must declare what the
  boundary requires*;
* its PARAMETERS are factory-specific — the boundary date, and the ledger it reads.

So the parameters are DECLARED, in the factory's own tree, and this module is the one
reader of that declaration. The shape mirrors #69 (`docs/products.json` +
`docs/products.example.json`): the skeleton ships, the filled file does not, and the gate
asserts the CORRESPONDENCE rather than a fixed state. A tree that has not declared a
boundary takes the SKIP path with a stated reason — never a silent pass, and never
another factory's date.

Three outcomes, and the difference between them is the point
------------------------------------------------------------
* **`SkipGate`** — this tree legitimately has nothing to judge: no ledger, an empty
  ledger, no declaration, no declared boundary, or an empty population. Reported as
  `SKIP: <reason>`; the caller exits 0 and STATES the reason.
* **`GateError`** — this tree declares something it cannot honour: an unreadable or
  malformed declaration, an unparseable boundary, a corrupt ledger line. Reported as a
  FAILURE naming the problem. A declared parameter that cannot be read is a defect, not
  an absence, so it must never be silently skipped — the `#69` clause (e) shape.
* **clean** — the caller's own predicate found nothing.

The population guard (#78 clause (c)) lives here rather than in each gate, because it is
the same statement twice. The fixed `>= 50` floor is DROPPED: it fails a factory whose
history is younger than it, and a population floor cannot be both universal and true.
What replaces it is PROPORTIONAL — an empty post-boundary population SKIPS with its
reason instead of passing vacuously, so the gate either verifies a non-empty population
or says why it examined nothing.

This module holds no tests (the name carries no `test_` prefix, so pytest does not
collect it) and no state of its own: it is the reader, shared, so that the class this
issue measured has ONE implementation instead of one per gate.

Run:  imported by the gates, never run directly.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

LEDGER_REL = "evidence/ledger.jsonl"
DECLARATION_REL = "docs/ledger-invariants.json"
DECLARATION_EXAMPLE_REL = "docs/ledger-invariants.example.json"

class SkipGate(Exception):
    """Nothing to judge in THIS tree, and that is legitimate: skip with this reason."""

class GateError(Exception):
    """The tree declares something it cannot honour: fail with these problems."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)

def parse_ts(value: str) -> dt.datetime:
    """An ISO-8601 UTC timestamp, as `tools/ledger.py` writes it."""
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))

def read_rows(repo: Path) -> list[dict]:
    """The ledger's rows, or `SkipGate`/`GateError`. Never raises anything else.

    An ABSENT ledger is a skip: the ledger is bootstrap-created, so a tree that has not
    bootstrapped yet is a legitimate state, not a defect. An EMPTY one is a skip for the
    same reason — there is no population to judge. A CORRUPT one is a failure: the
    ledger exists and cannot be read, which no bootstrap step produces.
    """
    ledger = repo / LEDGER_REL
    if not ledger.is_file():
        raise SkipGate(
            f"no {LEDGER_REL} in this tree — the ledger is BOOTSTRAP-created "
            f"({DECLARATION_EXAMPLE_REL} names the declaration this gate reads instead)"
        )
    try:
        text = ledger.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateError([f"{LEDGER_REL} exists but cannot be read: {exc}"]) from exc

    rows: list[dict] = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GateError([f"{LEDGER_REL}:{number} is not a JSON row: {exc}"]) from exc
        if not isinstance(row, dict):
            raise GateError([f"{LEDGER_REL}:{number} is not a JSON object"])
        rows.append(row)

    if not rows:
        raise SkipGate(f"{LEDGER_REL} exists but carries no rows — nothing to judge")
    return rows

def declared_boundary(repo: Path, key: str) -> tuple[dt.datetime, str]:
    """The boundary `key` names, as `(datetime, declared-text)`, or Skip/GateError.

    The declaration is FACTORY DATA and never ships, so its absence is a skip — the
    state every bootstrapped factory is in until it adopts the invariant. Its
    MALFORMED presence is a failure: the factory declared a boundary and the gate cannot
    read it, and silently skipping that would hide a broken declaration behind the same
    output as no declaration at all.
    """
    path = repo / DECLARATION_REL
    if not path.is_file():
        raise SkipGate(
            f"no {DECLARATION_REL} — the boundary is a DECLARED factory parameter "
            f"(#78 clause b), and this tree has not declared one; the skeleton is "
            f"{DECLARATION_EXAMPLE_REL}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GateError([f"{DECLARATION_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise GateError([f"{DECLARATION_REL} is not valid JSON: {exc}"]) from exc

    if not isinstance(payload, dict):
        raise GateError([f"{DECLARATION_REL} must be a JSON object carrying `invariants`"])
    declared = payload.get("invariants")
    if not isinstance(declared, dict):
        raise GateError([
            f"{DECLARATION_REL} carries no `invariants` map — see {DECLARATION_EXAMPLE_REL}"
        ])

    value = declared.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise SkipGate(
            f"{DECLARATION_REL} declares no `{key}` boundary — this factory has not "
            f"adopted that invariant, so there is no boundary to judge against"
        )
    if not isinstance(value, str):
        raise GateError([
            f"{DECLARATION_REL}: `{key}` must be an ISO-8601 UTC string, found "
            f"{type(value).__name__}"
        ])
    try:
        boundary = parse_ts(value)
    except (ValueError, TypeError) as exc:
        raise GateError([
            f"{DECLARATION_REL}: `{key}` is not a readable ISO-8601 timestamp: "
            f"{value!r} ({exc})"
        ]) from exc
    return boundary, value

def boundary_and_rows(repo: Path, key: str) -> tuple[dt.datetime, str, list[dict]]:
    """`(boundary, declared-text, rows)` for one gate, or `SkipGate`/`GateError`.

    The ledger is read FIRST, so a tree that has neither a ledger nor a declaration
    reports the more fundamental absence.
    """
    rows = read_rows(repo)
    boundary, text = declared_boundary(repo, key)
    return boundary, text, rows

def post_boundary_rows(
    rows: list[dict], boundary: dt.datetime, event: str | None = None
) -> list[dict]:
    """The rows at or after `boundary` whose timestamp is readable.

    This is the gate's POPULATION: the rows the invariant actually governs. Rows with an
    unparseable timestamp are excluded here and reported by the predicate as problems —
    a row that cannot be dated cannot be excused by its date either.

    `event` scopes the population to one kind of row, which is what the close-row and
    score invariants need. `event=None` governs EVERY row, which is what an invariant
    over the ledger as a whole needs — the subject form constrains any row that names an
    issue, whatever its event. The unscoped form is the default so a caller that names no
    event gets the whole ledger rather than an empty population.
    """
    population: list[dict] = []
    for row in rows:
        if event is not None and row.get("event") != event:
            continue
        try:
            when = parse_ts(row.get("ts", ""))
        except (ValueError, TypeError):
            continue
        if when >= boundary:
            population.append(row)
    return population

def population_skip_reason(
    population: list[dict], boundary_text: str, event: str | None = None
) -> str | None:
    """The reason to SKIP when the population is empty, else None (#78 clause c).

    PROPORTIONAL, not a floor. A gate whose population is empty passes vacuously, and
    `>= 50` was the meta-factory's answer to that — but it fails a factory whose history
    is younger than 50 closes, so it is not a law a template can ship. The proportional
    form states the same fact about the tree under test: this gate either verifies a
    non-empty population or says, in the output, why it examined nothing.

    `event=None` describes the unscoped population as "row" rather than as an event name,
    so the reason never claims a scope the caller did not ask for.
    """
    if population:
        return None
    scope = f"`{event}` row" if event is not None else "row"
    return (
        f"no {scope} at or after the declared boundary {boundary_text} — the "
        f"population is empty, so this is a stated skip and not a silent pass"
    )

def synthetic_tree(
    root: Path,
    rows: list[dict] | None = None,
    invariants: dict | None = None,
    declaration: object = None,
) -> Path:
    """A factory tree carrying exactly what the caller names — the P35 fixture.

    `rows=None` writes NO ledger (the bootstrap case); `rows=[]` writes an EMPTY one.
    `invariants=None` writes NO declaration; a mapping writes one under `invariants`.
    `declaration` writes raw text instead, for the malformed case.
    """
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)

    if rows is not None:
        body = "".join(json.dumps(row) + "\n" for row in rows)
        (root / LEDGER_REL).write_text(body, encoding="utf-8")

    if declaration is not None:
        text = declaration if isinstance(declaration, str) else json.dumps(declaration)
        (root / DECLARATION_REL).write_text(text + "\n", encoding="utf-8")
    elif invariants is not None:
        (root / DECLARATION_REL).write_text(
            json.dumps({"invariants": invariants}) + "\n", encoding="utf-8"
        )

    return root
