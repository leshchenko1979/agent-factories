#!/usr/bin/env python3
"""Gate: every family figure in the fleet view prints its measurable count.

Origin: board #430 (ruling at ledger n=2777), filed on the #421 return leg's own ASK.
`docs/measurement-procedure.md` §5.3 — ruled 2026-10-07 (board #421, ruling n=2747) —
declares the UNMEASURABLE mechanics: a cell whose input does not exist for the round
leaves the FAMILY MEAN and nothing else, every denominator stays unchanged (76 per
factory, 456 fleet), the measurable count prints BESIDE every family figure so an
exclusion is never silent, and the mechanics bind forward-only.

`docs/measurement-procedure.md` §5.3 landed with NO gate reading it. Its sibling `tests/test_score_artifact_sections.py`
(same origin) asserts the family view's PRESENCE and cannot read its arithmetic, and
`tests/test_docs_sync.py` keeps the two procedure twins identical without asserting the
clause is there at all. So the disclosure requirement was prose a later edit could drop
silently — the class this gate closes.

THE MECHANICS THE GATE ASSERTS
------------------------------
1. A post-boundary artifact's `### Family-level fleet view` table carries, on every row
   that prints a family mean, a measurable count. `docs/measurement-procedure.md` §5.3 names the canonical wording
   *"3.167 over 12 of 18 cells"*; the predicate is loose-then-strict (the #62 shape), so
   it finds `<n> of <m>` — or the `<n>/<m>` spelling — wherever the count sits, and the
   procedure names the canonical form.
2. A count exceeding its own population is NOT a disclosure: `20 of 18 cells` says
   nothing about a reduced population, so it reds exactly like an absent one.
3. Denominators stay UNCHANGED (`docs/measurement-procedure.md` §5.3 point 2): a scorecard heading's denominator must
   equal the rubric's own declared maximum, and the fleet row's must equal that maximum
   times the fleet manifest's factory count — both READ from the declarations, never
   restated — so a round that dropped the excluded cell from its denominator reds rather
   than silently re-basing every published percentage.
4. Forward-only, with an EXCLUSIVE boundary. An artifact dated at or before
   the declared boundary is EXCUSED AND PRINTED, never repaired — the landing round's own
   artifact is already written, and a disclosure reconstructed after the fact would be
   fabricated provenance rather than a measurement.
5. The requirement is COUPLED to the procedure: the gate asserts `docs/measurement-procedure.md` §5.3's own clause
   markers appear in `docs/measurement-procedure.md`, so the rule lives where the run
   reads it. A gate whose requirement is stated nowhere enforces a rule nobody was told.

The predicates are factored out as `missing_disclosure` and `denominator_problems` and
driven by synthetic text, because a rule that has only ever seen good input has not been
shown to reject bad input.

Run:  python3 -m pytest tests/test_score_artifact_measurable.py -q
Exit: 0 clean or fully excused, non-zero on any post-boundary artifact whose family view
      prints a mean with no measurable count.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    declared_boundary,
)

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "evidence" / "scores"
PROCEDURE = REPO / "docs" / "measurement-procedure.md"

# The boundary is FACTORY DATA (#428), declared in `docs/ledger-invariants.json` under this
# key and read through `tests/ledger_boundary.py` — never a literal here. This file is paired
# byte-identically with TEMPLATE/tests/test_score_artifact_measurable.py, so a date written
# inside it would ship to every member and be read against the MEMBER's scores directory,
# where the day this law landed means nothing. An ABSENT declaration skips with its reason;
# a MALFORMED one FAILS.
#
# The declared value is EXCLUSIVE, and its provenance is the ruling recorded at
# `docs/measurement-procedure.md §5.3` (board #421): the landing round's own artifact is
# already written and is never backfilled — `evidence/scores/2026-10-07.md` still prints Output's family mean over
# all 18 cells, so requiring it there would demand a rewritten record rather than a repair.
INVARIANT_KEY = "score_artifact_measurable"

# The PROBES' own boundary — a fixture, never the factory's declaration.
_PROBE_BOUNDARY = dt.date(2026, 10, 7)

# `docs/measurement-procedure.md` §5.3's own clause markers, which is what couples the requirement to the procedure. Read
# from `docs/measurement-procedure.md`, never restated in a second home: a gate whose
# requirement is stated nowhere enforces a rule nobody was told.
PROCEDURE_ANCHORS: list[str] = [
    "## 5.3 The UNMEASURABLE mechanics",
    "**1. The cell leaves the FAMILY MEAN, and nothing else.**",
    "**2. Every denominator is UNCHANGED.**",
    "**3. The disclosure is MANDATORY, and the exclusion is never silent.**",
    "**4. Forward-only.**",
    "**5. Every family figure is RE-DERIVABLE from the round's own scorecards.**",
]

_ARTIFACT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
_FAMILY_VIEW_HEADING = "### Family-level fleet view"
_SEPARATOR_RE = re.compile(r"^:?-{2,}:?$")
_MEAN_RE = re.compile(r"\d+\.\d+")
# A family row's CURRENT figure is its bolded numeric CELL, and the FORM is read from the
# value itself: an integer is the family SUM, a decimal is the MEAN over the row's measurable
# cells. The 2026-10-10 round printed sums where the rounds before it printed means, and the
# two are the same number in two presentations (71 == 2.958 x 24) — so every reading keys on
# the form the row carries rather than demanding one of them (#458).
_BOLD_NUM_CELL_RE = re.compile(r"^\*\*(\d+(?:\.\d+)?)\*\*$")
# A SCORECARD cell carries the same emphasis for the same reason: a round bolds the cell that
# moved (`| ... | **3** |`) so a reader can see it at a glance. The emphasis is presentation and
# the value is the number, so the leading `**` is stripped before the value is read — dropping a
# bolded cell instead would silently lose its points from every family aggregate, which is how
# the 2026-10-09 round's Autonomy figure read 38 against its own cells' 41 (#458).
_SCORECARD_CELL_RE = re.compile(r"^\*{0,2}\s*(\d+)")
# The disclosure: `<n> of <m>` in `docs/measurement-procedure.md` §5.3's canonical wording, or the `<n>/<m>` spelling.
# The row's other columns carry no `of` and no `/`, so the predicate cannot be satisfied
# by a bare total — `| Output | 18 | **2.611** | 0.000 |` carries no disclosure.
_DISCLOSURE_RE = re.compile(r"\b(\d+)\s*(?:of|/)\s*(\d+)\b")

# `docs/measurement-procedure.md` §5.3 point 2's declarations, both READ rather than restated: the per-factory
# denominator is the rubric's own stated maximum, and the fleet total is that maximum
# times the fleet's declared factory count. A hardcoded copy would pass a rubric change
# silently — the class the sibling sections gate exists to close.
CRITERIA = REPO / "docs" / "quality-criteria.md"
FLEET = REPO / "registry" / "fleet.json"
_RUBRIC_MAX = re.compile(r"maximum is \*\*(\d+)\*\*")
# The heading's trailing percentage is OPTIONAL. It was printed through the 2026-10-08 round
# and absent from 2026-10-09 onward, so requiring the `(` made this arm match ZERO scorecards
# in the two most recent artifacts — the gate still reported that denominators were checked
# while examining none of them (#458). The denominator is the `/<n>` and nothing else.
_SCORECARD_DEN = re.compile(r"^### \d+\.\s+.+?\s+—\s+\d+\s*/\s*(?P<den>\d+)")
_FLEET_ROW = re.compile(r"^\|\s*\*\*Fleet\*\*\s*\|")
_RATIO = re.compile(r"(\d+)\s*/\s*(\d+)")


def family_view_block(text: str) -> str:
    """The lines under the fleet view's heading, up to the next heading of any level."""
    out: list[str] = []
    on = False
    for line in text.splitlines():
        if line.strip().startswith(_FAMILY_VIEW_HEADING):
            on = True
            continue
        if on and line.startswith("#"):
            break
        if on:
            out.append(line)
    return "\n".join(out)


def family_rows(text: str) -> list[str]:
    """Data rows of the fleet view's table: a `|`-row with a label and a numeric figure.

    The header row and the `|---|` separator are excluded by construction rather than by
    position — a table whose column order moves stays read. The FIGURE may be either form
    the rounds use: a decimal mean (`2.958`) or a bolded integer sum (`**71**`). Requiring a
    decimal made this selector return ONE row on the 2026-10-10 artifact — the fleet row,
    whose percentage carries the only decimal — so six of seven rows went unexamined while
    the gate reported a clean verdict (#458).
    """
    rows: list[str] = []
    for line in family_view_block(text).splitlines():
        row = line.strip()
        if not row.startswith("|"):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) < 3 or not cells[0]:
            continue
        if all(_SEPARATOR_RE.match(c) for c in cells if c):
            continue
        if not (_MEAN_RE.search(row) or any(_BOLD_NUM_CELL_RE.match(c) for c in cells)):
            continue
        rows.append(row)
    return rows


def missing_disclosure(text: str) -> list[str]:
    """Labels of every fleet-view row printing a mean with no usable measurable count.

    Pure: no file system, no clock. A synthetic artifact drives it directly, so the
    predicate is proven to REJECT bad input rather than merely to accept good input.
    """
    missing: list[str] = []
    for row in family_rows(text):
        label = row.strip("|").split("|")[0].strip().strip("*")
        match = _DISCLOSURE_RE.search(row)
        if match is None:
            missing.append(label)
            continue
        measured, population = int(match.group(1)), int(match.group(2))
        if population <= 0 or measured > population:
            missing.append(label)
    return missing


def declared_maximum() -> int | None:
    """The per-factory denominator, READ from the rubric's own declared maximum."""
    if not CRITERIA.is_file():
        return None
    match = _RUBRIC_MAX.search(CRITERIA.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def factory_count() -> int:
    """The fleet's factory count, READ from the declared fleet manifest."""
    if not FLEET.is_file():
        return 0
    try:
        data = json.loads(FLEET.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    factories = data.get("factories", [])
    return len(factories) if isinstance(factories, list) else 0


def denominator_problems(text: str, factory_max: int | None, factories: int) -> list[str]:
    """Scorecard and fleet denominators that disagree with the declared maximum.

    `docs/measurement-procedure.md` §5.3 point 2: an UNMEASURABLE cell is neither scored nor removed, so every denominator
    is UNCHANGED — 76 per factory, 456 fleet. A round that dropped the excluded cell from
    its denominator would re-base every published percentage, which is the reading the
    NARROW option was chosen to refuse. The expected values are READ from the declarations
    (`docs/quality-criteria.md`, `registry/fleet.json`), never restated here, so a rubric
    change moves them and a re-based artifact reds.

    Pure: the caller passes both declarations, so a synthetic artifact drives it directly.
    """
    problems: list[str] = []
    if factory_max:
        for line in text.splitlines():
            match = _SCORECARD_DEN.match(line)
            if match is None:
                continue
            den = int(match.group("den"))
            if den != factory_max:
                name = line.split("—")[0].strip().lstrip("#").strip()
                problems.append(
                    f"scorecard {name}: /{den}, declared /{factory_max}"
                )
    if factory_max and factories:
        expected = factory_max * factories
        for line in text.splitlines():
            if not _FLEET_ROW.match(line):
                continue
            for _score, den in _RATIO.findall(line):
                if int(den) != expected:
                    problems.append(
                        f"fleet row: /{den}, declared /{expected} "
                        f"({factories} x {factory_max})"
                    )
    return problems


# --- the aggregate: the family view re-derived from the artifact's own scorecards (#458) ---

# The artifact's declared criteria order. BOTH the codes and the family names are read from
# this one line, so a round that reorders or renames a family moves the reading with it: a
# hardcoded family->code map would sum the wrong cells the day the order moved, and the
# result would still look plausible.
_ORDER_LINE_RE = re.compile(
    r"\*\*Order of criteria throughout:\*\*\s*`(?P<codes>[^`]+)`\s*—\s*(?P<names>[A-Za-z ,]+)"
)
# A scorecard heading: `### <n>. <factory> — <total> / <denominator>`.
_SCORECARD_TOTAL_RE = re.compile(
    r"^### \d+\.\s+(?P<name>.+?)\s+—\s+(?P<total>\d+)\s*/\s*(?P<den>\d+)"
)

def _table_cells(line: str) -> list[str]:
    """The trimmed cells of a markdown table row, or `[]` when the line is not one."""
    row = line.strip()
    if not row.startswith("|"):
        return []
    return [cell.strip() for cell in row.strip("|").split("|")]

def criteria_order(text: str) -> dict[str, list[str]]:
    """The artifact's declared family -> criterion-code map, or `{}` when it declares none.

    An artifact carrying no order line is not judged by the aggregate arms: the declaration
    is the artifact's own, and a round that predates the form carries none.
    """
    for line in text.splitlines():
        match = _ORDER_LINE_RE.search(line)
        if match is None:
            continue
        groups = [group.strip() for group in match.group("codes").split("·")]
        names = [name.strip() for name in match.group("names").split(",") if name.strip()]
        if len(groups) != len(names):
            return {}
        return {
            name: [code for code in group.split() if code]
            for name, group in zip(names, groups)
        }
    return {}

def scorecard_blocks(text: str) -> list[tuple[str, list[str]]]:
    """`(heading, body lines)` for every scorecard, in the artifact's own order."""
    blocks: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if _SCORECARD_TOTAL_RE.match(stripped):
            if current is not None:
                blocks.append(current)
            current = (stripped, [])
            continue
        if current is None:
            continue
        if stripped.startswith("#"):
            blocks.append(current)
            current = None
            continue
        current[1].append(line)
    if current is not None:
        blocks.append(current)
    return blocks

def scorecard_values(body: list[str], codes: list[str]) -> dict[str, int]:
    """One scorecard's per-criterion values keyed by code, or `{}` when unreadable.

    The criterion row is found by CONTENT — a `|`-row whose every cell is a declared code —
    and the values are the first following row of the same width that is neither the `|---|`
    separator nor a second code row. An UNMEASURABLE cell (`0 (UNM)`) reads as the 0 it
    contributes, which is what ruling `n=2747` says it contributes to the totals, and a cell
    bolded as the round's movement marker (`**3**`) reads as the 3 it is.
    """
    header: list[str] | None = None
    start = 0
    for index, line in enumerate(body):
        cells = _table_cells(line)
        if cells and all(cell in codes for cell in cells):
            header = cells
            start = index + 1
            break
    if header is None:
        return {}
    for line in body[start:]:
        cells = _table_cells(line)
        if len(cells) != len(header):
            continue
        if all(_SEPARATOR_RE.match(cell) for cell in cells if cell):
            continue
        if all(cell in codes for cell in cells):
            continue
        values: dict[str, int] = {}
        for code, cell in zip(header, cells):
            match = _SCORECARD_CELL_RE.match(cell)
            if match is not None:
                values[code] = int(match.group(1))
        return values
    return {}

def family_totals(text: str) -> dict[str, int]:
    """Family -> summed cell value, re-derived from the artifact's own scorecards."""
    order = criteria_order(text)
    if not order:
        return {}
    codes = [code for group in order.values() for code in group]
    values = [scorecard_values(body, codes) for _heading, body in scorecard_blocks(text)]
    return {
        family: sum(row.get(code, 0) for row in values for code in family_codes)
        for family, family_codes in order.items()
    }

def aggregate_problems(text: str) -> list[str]:
    """Family-view figures that disagree with the artifact's own scorecards (#458).

    Three readings, all over the artifact's own declarations and none over a second copy of
    them:
      * every family row's figure equals the sum of that family's cells across the
        scorecards, compared in the FORM the row carries (an integer is the sum; a decimal
        is the mean over the row's own measurable count);
      * the fleet row's numerator equals the sum of the scorecards' own printed totals;
      * every scorecard yields a readable criterion row at all.

    The third reading is why the first two are trustworthy: a sum that silently omitted an
    unreadable scorecard would agree with a table that omitted it too.
    """
    problems: list[str] = []
    order = criteria_order(text)
    if not order:
        return problems
    codes = [code for group in order.values() for code in group]
    blocks = scorecard_blocks(text)
    if not blocks:
        return problems

    rows: list[dict[str, int]] = []
    printed: list[int] = []
    for heading, body in blocks:
        match = _SCORECARD_TOTAL_RE.match(heading)
        if match is not None:
            printed.append(int(match.group("total")))
        values = scorecard_values(body, codes)
        if not values:
            problems.append(
                f"scorecard {heading.lstrip('#').strip()}: no readable criterion row"
            )
            continue
        rows.append(values)

    totals = {
        family: sum(row.get(code, 0) for row in rows for code in family_codes)
        for family, family_codes in order.items()
    }

    for line in family_rows(text):
        if _FLEET_ROW.match(line):
            continue
        cells = _table_cells(line)
        label = cells[0].strip().strip("*")
        if label not in totals:
            continue
        figure = next(
            (cell for cell in cells if _BOLD_NUM_CELL_RE.match(cell)), None
        )
        if figure is None:
            continue
        declared = _BOLD_NUM_CELL_RE.match(figure).group(1)
        expected = totals[label]
        if "." not in declared:
            if int(declared) != expected:
                problems.append(
                    f"{label}: total {declared}, its scorecard cells sum to {expected}"
                )
            continue
        disclosure = _DISCLOSURE_RE.search(line)
        measurable = int(disclosure.group(1)) if disclosure else 0
        if measurable <= 0:
            problems.append(f"{label}: mean {declared} with no measurable count to divide by")
            continue
        mean = expected / measurable
        if abs(float(declared) - mean) > 0.0005:
            problems.append(
                f"{label}: mean {declared}, its scorecard cells sum to {expected} over "
                f"{measurable} measurable cell(s) = {mean:.3f}"
            )

    fleet = next((line for line in family_rows(text) if _FLEET_ROW.match(line)), None)
    if fleet is not None and printed:
        ratios = _RATIO.findall(fleet)
        if ratios:
            numerator = int(ratios[0][0])
            expected = sum(printed)
            if numerator != expected:
                problems.append(
                    f"Fleet: numerator {numerator}, the {len(printed)} scorecard totals "
                    f"sum to {expected}"
                )
    return problems

def artifacts() -> list[tuple[dt.date, Path]]:
    """Every dated score artifact, oldest first. `*-self-audit.md` is not one."""
    out: list[tuple[dt.date, Path]] = []
    if not SCORES.is_dir():
        return out
    for path in sorted(SCORES.glob("*.md")):
        match = _ARTIFACT_RE.match(path.name)
        if match is None:
            continue
        year, month, day = (int(g) for g in match.groups())
        out.append((dt.date(year, month, day), path))
    return out


def declared_day(repo: Path, key: str) -> dt.date:
    """The declared boundary `key` names, as a DATE, or `SkipGate`/`GateError`.

    The declaration is FACTORY DATA and never ships, so its ABSENCE is a stated skip — the
    state every bootstrapped factory is in until it adopts the invariant. A MALFORMED
    declaration is a `GateError`: a broken declaration must not hide behind the same output
    as none at all. The artifact names are dated (`YYYY-MM-DD.md`), so the boundary is
    compared as a DATE — the declaration's time of day carries no meaning here.
    """
    return declared_boundary(repo, key)[0].date()

def _declared_day_or_skip(repo: Path, key: str) -> dt.date:
    """`declared_day`, with the two declaration outcomes mapped onto pytest."""
    try:
        return declared_day(repo, key)
    except SkipGate as exc:
        pytest.skip(str(exc))
    except GateError as exc:
        raise AssertionError("; ".join(exc.problems)) from exc

def declared() -> bool:
    """The requirement is declared by the procedure; without it there is nothing to assert."""
    return PROCEDURE.is_file()


def probe() -> list[str]:
    """The predicate's discriminating arms. Returns a problem per arm that misbehaved."""
    problems: list[str] = []
    red = (
        "### Family-level fleet view\n\n"
        "| Family | Cells | Mean (10-07) | Movement |\n"
        "|---|---:|---:|---:|\n"
        "| Output | 18 | **2.611** | 0.000 |\n"
    )
    cases: list[tuple[str, str, list[str]]] = [
        ("RED (mean, no count)", red, ["Output"]),
        ("GREEN (canonical form)", red.replace("**2.611**", "**3.167** over 12 of 18 cells"), []),
        ("SLASH (alternate spelling)", red.replace("**2.611**", "**3.167** (12/18 cells)"), []),
        ("BOUND (count exceeds population)", red.replace("**2.611**", "**3.167** over 20 of 18 cells"), ["Output"]),
        ("SCOPE (table outside the family view)", red.replace(_FAMILY_VIEW_HEADING, "## Detailed Factory Scorecards"), []),
    ]
    for label, text, expected in cases:
        got = missing_disclosure(text)
        if got != expected:
            problems.append(f"{label}: expected {expected!r}, got {got!r}")
    return problems


def probe_denominators() -> list[str]:
    """The denominators predicate's discriminating arms, over synthetic text."""
    problems: list[str] = []
    good = (
        "### 1. Alpha — 70 / 76 (92.1%), Optimizing\n"
        "### 2. Beta — 59 / 76 (77.6%), Scalable\n\n"
        "| **Fleet** | **357 / 456 (78.3 %)** | **358 / 456 (78.5 %)** | **+1** | — |\n"
    )
    cases: list[tuple[str, str, int | None, int, int]] = [
        ("GREEN (declared denominators)", good, 76, 6, 0),
        ("RED (scorecard re-based)", good.replace("70 / 76", "70 / 70"), 76, 6, 1),
        ("RED (fleet re-based)", good.replace("/ 456", "/ 420"), 76, 6, 2),
        ("SCOPE (no declared maximum)", good.replace("70 / 76", "70 / 70"), None, 6, 0),
        ("SCOPE (no declared fleet)", good.replace("/ 456", "/ 420"), 76, 0, 0),
    ]
    for label, text, factory_max, factories, expected in cases:
        got = denominator_problems(text, factory_max, factories)
        if len(got) != expected:
            problems.append(f"{label}: expected {expected} problem(s), got {len(got)}: {got!r}")
    return problems


_AGGREGATE_FIXTURE = (
    "**Order of criteria throughout:** `D1 D2 · O1 O2` — Documentation, Output.\n"
    "\n"
    "### 1. Alpha — 7 / 8\n"
    "\n"
    "| D1 | D2 | O1 | O2 |\n"
    "|---:|---:|---:|---:|\n"
    "| 2 | 3 | 1 | 1 |\n"
    "\n"
    "### 2. Beta — 6 / 8\n"
    "\n"
    "| D1 | D2 | O1 | O2 |\n"
    "|---:|---:|---:|---:|\n"
    "| 2 | 1 | 2 | 1 |\n"
    "\n"
    "### Family-level fleet view\n"
    "\n"
    "| Family | Criteria | Max | Measurable | Now | Before | Note |\n"
    "|---|---|---:|---:|---:|---:|---|\n"
    "| Documentation | D1 D2 | 16 | 4 of 4 | **8** | 8 | — |\n"
    "| Output | O1 O2 | 16 | 4 of 4 | **5** | 5 | — |\n"
    "| **Fleet** | | **16** | **8 of 8** | **13 / 16 (81.25 %)** | **13** | — |\n"
)

def _aggregate_labels(problems: list[str]) -> list[str]:
    """The row label each aggregate problem names, so an arm asserts WHICH row it caught."""
    return [problem.split(":", 1)[0] for problem in problems]

def probe_aggregates() -> list[str]:
    """The aggregate predicate's discriminating arms, over synthetic text.

    The mean-form arms are not decoration: the two rounds before 2026-10-10 printed means and
    that round printed sums, so a predicate reading only one form would have left the other
    round's table unexamined — the shape the round's own 25-gate set passed.
    """
    problems: list[str] = []
    mean_form = (
        _AGGREGATE_FIXTURE.replace("| **8** |", "| **2.000** |").replace(
            "| **5** |", "| **1.250** |"
        )
    )
    no_order = _AGGREGATE_FIXTURE.replace(
        "**Order of criteria throughout:** `D1 D2 · O1 O2` — Documentation, Output.\n", ""
    )
    cases: list[tuple[str, str, list[str]]] = [
        ("GREEN (sum form re-adds)", _AGGREGATE_FIXTURE, []),
        (
            "RED (a family row off by one)",
            _AGGREGATE_FIXTURE.replace("| **8** |", "| **9** |"),
            ["Documentation"],
        ),
        (
            "RED (the fleet numerator disagrees with the scorecard totals)",
            _AGGREGATE_FIXTURE.replace("**13 / 16", "**12 / 16"),
            ["Fleet"],
        ),
        ("GREEN (mean form over the row's measurable count)", mean_form, []),
        (
            "GREEN (a bolded cell — the round's movement marker — still re-adds)",
            _AGGREGATE_FIXTURE.replace("| 2 | 1 | 2 | 1 |", "| 2 | **1** | 2 | 1 |"),
            [],
        ),
        (
            "RED (a mean that disagrees with the cells it summarises)",
            mean_form.replace("**2.000**", "**2.250**"),
            ["Documentation"],
        ),
        ("SCOPE (no declared order line)", no_order, []),
    ]
    for label, text, expected in cases:
        got = _aggregate_labels(aggregate_problems(text))
        if got != expected:
            problems.append(f"{label}: expected {expected!r}, got {got!r}")
    return problems

def test_predicate_rejects_a_mean_with_no_measurable_count() -> None:
    assert probe() == [], "\n".join(probe())


def test_predicate_rejects_a_re_based_denominator() -> None:
    assert probe_denominators() == [], "\n".join(probe_denominators())


def test_predicate_rejects_a_family_row_that_disagrees_with_the_scorecards() -> None:
    assert probe_aggregates() == [], "\n".join(probe_aggregates())


def test_procedure_names_every_anchor() -> None:
    if not declared():
        return
    text = PROCEDURE.read_text(encoding="utf-8")
    absent = [anchor for anchor in PROCEDURE_ANCHORS if anchor not in text]
    assert absent == [], f"docs/measurement-procedure.md does not name: {absent}"


def test_pre_boundary_artifacts_are_excused_not_required() -> None:
    """The boundary is exclusive: at or before the landing day is excused, never checked.

    Asserted as a property over whatever artifacts the tree holds — a bootstrapped factory
    has none of this factory's — with this factory's own landing-day artifact named as the
    concrete case where it is present.
    """
    landed = _declared_day_or_skip(REPO, INVARIANT_KEY)
    found = artifacts()
    present = {path.name for _day, path in found}
    excused = {path.name for day, path in found if day <= landed}
    checked = {path.name for day, path in found if day > landed}
    assert excused | checked == present
    assert not (excused & checked)
    if "2026-10-07.md" in present:
        assert "2026-10-07.md" in excused


def test_post_boundary_artifacts_disclose_their_measurable_count() -> None:
    if not declared():
        return
    landed = _declared_day_or_skip(REPO, INVARIANT_KEY)
    problems: list[str] = []
    for day, path in artifacts():
        if day <= landed:
            continue
        missing = missing_disclosure(path.read_text(encoding="utf-8"))
        if missing:
            problems.append(f"{path.name}: no measurable count on {', '.join(missing)}")
    assert problems == [], "\n".join(problems)


def test_post_boundary_artifacts_re_add_their_own_family_view() -> None:
    """Every family figure is re-derived from the artifact's own scorecards (#458).

    The 2026-10-10 round shipped four of six family totals wrong while BOTH revisions summed
    to the fleet total, and the round's own 25-gate set read the table clean. A total that
    agrees with the fleet figure while disagreeing with the scorecards is exactly the shape a
    reader cannot catch by adding up, which is why the per-family reading is the load-bearing
    one — and why the form the row carries is read rather than demanded.
    """
    if not declared():
        return
    landed = _declared_day_or_skip(REPO, INVARIANT_KEY)
    problems: list[str] = []
    for day, path in artifacts():
        if day <= landed:
            continue
        for problem in aggregate_problems(path.read_text(encoding="utf-8")):
            problems.append(f"{path.name}: {problem}")
    assert problems == [], "\n".join(problems)


def test_post_boundary_artifacts_keep_the_declared_denominators() -> None:
    if not declared():
        return
    landed = _declared_day_or_skip(REPO, INVARIANT_KEY)
    factory_max = declared_maximum()
    factories = factory_count()
    problems: list[str] = []
    for day, path in artifacts():
        if day <= landed:
            continue
        for problem in denominator_problems(
            path.read_text(encoding="utf-8"), factory_max, factories
        ):
            problems.append(f"{path.name}: {problem}")
    assert problems == [], "\n".join(problems)


# --- probes: the DECLARATION the boundary is read from (#428) ------------------

def test_probe_a_tree_with_no_declared_boundary_skips_with_a_stated_reason() -> None:
    """The declaration is FACTORY DATA and does not ship, so its absence is the state every
    bootstrapped factory is in — a STATED skip, never a red and never a silent pass. This is
    the arm that keeps the shipped `TEMPLATE/` tree green (#78, #76's class)."""
    with tempfile.TemporaryDirectory() as tmp:
        bare = Path(tmp)
        with pytest.raises(SkipGate) as excinfo:
            declared_day(bare, INVARIANT_KEY)
    assert "ledger-invariants" in str(excinfo.value), excinfo.value

def test_probe_a_declaration_without_this_key_skips_and_names_it() -> None:
    """A factory that adopted SOME invariant but not this one is the same state, and the
    skip names the KEY so a reader can tell which invariant is unadopted."""
    with tempfile.TemporaryDirectory() as tmp:
        bare = Path(tmp)
        (bare / "docs").mkdir()
        (bare / "docs" / "ledger-invariants.json").write_text(
            json.dumps({"invariants": {"some_other_gate": "2026-01-01T00:00:00Z"}}),
            encoding="utf-8",
        )
        with pytest.raises(SkipGate) as excinfo:
            declared_day(bare, INVARIANT_KEY)
    assert INVARIANT_KEY in str(excinfo.value), excinfo.value

def test_probe_an_unreadable_declared_boundary_fails() -> None:
    """A factory that DECLARED a boundary and cannot read it is a FAILURE, not a skip:
    skipping would hide a broken declaration behind the same output as none at all."""
    with tempfile.TemporaryDirectory() as tmp:
        bare = Path(tmp)
        (bare / "docs").mkdir()
        (bare / "docs" / "ledger-invariants.json").write_text(
            json.dumps({"invariants": {INVARIANT_KEY: "yesterday"}}), encoding="utf-8"
        )
        with pytest.raises(GateError) as excinfo:
            declared_day(bare, INVARIANT_KEY)
    assert excinfo.value.problems, excinfo.value

def test_a_factory_without_the_procedure_declares_nothing() -> None:
    """The undeclared path passes and says why — a bootstrapped factory's own case.

    The requirement is declared by `docs/measurement-procedure.md`. A factory without it
    must NOT red: it has declared no disclosure law to assert. The guard is asserted here
    so it is proven rather than merely written.
    """
    global PROCEDURE
    saved = PROCEDURE
    try:
        PROCEDURE = REPO / "docs" / "no-such-procedure.md"
        assert declared() is False
        assert main() == 0
        assert test_procedure_names_every_anchor() is None
        assert test_post_boundary_artifacts_disclose_their_measurable_count() is None
    finally:
        PROCEDURE = saved
    assert PROCEDURE == saved, f"the probe must restore PROCEDURE, not leak it: {PROCEDURE}"


def test_main_reds_on_a_post_boundary_artifact_with_no_count() -> None:
    """The wiring arm: the predicate is proven above; this proves `main()` READS it.

    A predicate proven in isolation and never wired to the artifact it governs is the
    decorative-instrument hole this project exists to close — so the gate drives `main()`
    itself over a synthetic scores directory holding one post-boundary artifact, both ways.
    """
    global SCORES
    saved = SCORES
    try:
        with tempfile.TemporaryDirectory() as tmp:
            scores = Path(tmp) / "scores"
            scores.mkdir()
            day = _declared_day_or_skip(REPO, INVARIANT_KEY) + dt.timedelta(days=1)
            artifact = scores / f"{day.isoformat()}.md"
            artifact.write_text(
                "### Family-level fleet view\n\n"
                "| Family | Cells | Mean | Movement |\n"
                "|---|---:|---:|---:|\n"
                "| Output | 18 | **2.611** | 0.000 |\n",
                encoding="utf-8",
            )
            SCORES = scores
            assert main() == 1, "main() must RED on a post-boundary artifact with no count"
            artifact.write_text(
                "### Family-level fleet view\n\n"
                "| Family | Cells | Mean | Movement |\n"
                "|---|---:|---:|---:|\n"
                "| Output | 18 | **3.167** over 12 of 18 cells | 0.000 |\n",
                encoding="utf-8",
            )
            assert main() == 0, "main() must GREEN once the measurable count prints"
    finally:
        SCORES = saved
    assert SCORES == saved, f"the probe must restore SCORES, not leak it: {SCORES}"


def main() -> int:
    if not declared():
        print(
            f"no {PROCEDURE.relative_to(REPO)} — no measurable-count law is declared; "
            f"nothing to assert"
        )
        return 0

    try:
        landed = declared_day(REPO, INVARIANT_KEY)
    except SkipGate as exc:
        print(f"score-artifact measurable gate: SKIPPED — {exc}")
        return 0
    except GateError as exc:
        print("score-artifact measurable gate failed:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    excused: list[str] = []
    checked: list[str] = []
    problems: list[str] = []

    for day, path in artifacts():
        if day <= landed:
            excused.append(path.name)
            continue
        checked.append(path.name)
        text = path.read_text(encoding="utf-8")
        rows = len(family_rows(text))
        # The population is PRINTED, always: a clean verdict over a population that was
        # never named is indistinguishable from one that examined nothing (P29).
        print(
            f"checked: {path.name} — {rows} family row(s) in the fleet view, "
            f"{len(scorecard_blocks(text))} scorecard(s) re-added"
        )
        if rows == 0:
            print(
                f"  {path.name}: 0 family rows — the post-boundary population is EMPTY, "
                f"so no disclosure was verified (its section is the sections gate's leg)"
            )
        missing = missing_disclosure(text)
        if missing:
            problems.append(f"{path.name}: no measurable count on {', '.join(missing)}")
        for problem in denominator_problems(text, declared_maximum(), factory_count()):
            problems.append(f"{path.name}: {problem}")
        for problem in aggregate_problems(text):
            problems.append(f"{path.name}: {problem}")

    for name in excused:
        print(f"excused: {name} — predates the measurable-count invariant")

    absent = [anchor for anchor in PROCEDURE_ANCHORS if anchor not in PROCEDURE.read_text(encoding="utf-8")]
    if absent:
        problems.append(f"{PROCEDURE.relative_to(REPO)} does not name: {', '.join(absent)}")

    problems.extend(probe())
    problems.extend(probe_denominators())
    problems.extend(probe_aggregates())

    if problems:
        print("score artifact measurable-count problems:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(
        f"score artifact measurable counts ok: {len(checked)} artifact(s) checked, "
        f"{len(excused)} excused, {len(PROCEDURE_ANCHORS)} procedure anchor(s), "
        f"denominators /{declared_maximum()} per factory and "
        f"/{(declared_maximum() or 0) * factory_count()} fleet"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
