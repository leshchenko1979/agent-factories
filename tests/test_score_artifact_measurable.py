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
   `INVARIANT_LANDED` is EXCUSED AND PRINTED, never repaired — the landing round's own
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

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "evidence" / "scores"
PROCEDURE = REPO / "docs" / "measurement-procedure.md"

# The day this requirement lands, read from `docs/measurement-procedure.md` §5.3's own ruling (board #421, 2026-10-07).
# EXCLUSIVE: an artifact dated strictly after this day must comply. The landing round's
# own artifact is already written and is never backfilled — and the #430 dispatch names
# it: `evidence/scores/2026-10-07.md` still prints Output's family mean over all 18
# cells, so requiring it there would demand a rewritten record rather than a repair.
INVARIANT_LANDED = dt.date(2026, 10, 7)

# `docs/measurement-procedure.md` §5.3's own clause markers, which is what couples the requirement to the procedure. Read
# from `docs/measurement-procedure.md`, never restated in a second home: a gate whose
# requirement is stated nowhere enforces a rule nobody was told.
PROCEDURE_ANCHORS: list[str] = [
    "## 5.3 The UNMEASURABLE mechanics",
    "**1. The cell leaves the FAMILY MEAN, and nothing else.**",
    "**2. Every denominator is UNCHANGED.**",
    "**3. The disclosure is MANDATORY, and the exclusion is never silent.**",
    "**4. Forward-only.**",
]

_ARTIFACT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
_FAMILY_VIEW_HEADING = "### Family-level fleet view"
_SEPARATOR_RE = re.compile(r"^:?-{2,}:?$")
_MEAN_RE = re.compile(r"\d+\.\d+")
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
_SCORECARD_DEN = re.compile(r"^### \d+\.\s+.+?\s+—\s+\d+\s*/\s*(?P<den>\d+)\s*\(")
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
    """Data rows of the fleet view's table: a `|`-row with a label and a decimal mean.

    The header row and the `|---|` separator carry no decimal, so they are excluded by
    construction rather than by position — a table whose column order moves stays read.
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
        if not _MEAN_RE.search(row):
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


def test_predicate_rejects_a_mean_with_no_measurable_count() -> None:
    assert probe() == [], "\n".join(probe())


def test_predicate_rejects_a_re_based_denominator() -> None:
    assert probe_denominators() == [], "\n".join(probe_denominators())


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
    found = artifacts()
    present = {path.name for _day, path in found}
    excused = {path.name for day, path in found if day <= INVARIANT_LANDED}
    checked = {path.name for day, path in found if day > INVARIANT_LANDED}
    assert excused | checked == present
    assert not (excused & checked)
    if "2026-10-07.md" in present:
        assert "2026-10-07.md" in excused


def test_post_boundary_artifacts_disclose_their_measurable_count() -> None:
    if not declared():
        return
    problems: list[str] = []
    for day, path in artifacts():
        if day <= INVARIANT_LANDED:
            continue
        missing = missing_disclosure(path.read_text(encoding="utf-8"))
        if missing:
            problems.append(f"{path.name}: no measurable count on {', '.join(missing)}")
    assert problems == [], "\n".join(problems)


def test_post_boundary_artifacts_keep_the_declared_denominators() -> None:
    if not declared():
        return
    factory_max = declared_maximum()
    factories = factory_count()
    problems: list[str] = []
    for day, path in artifacts():
        if day <= INVARIANT_LANDED:
            continue
        for problem in denominator_problems(
            path.read_text(encoding="utf-8"), factory_max, factories
        ):
            problems.append(f"{path.name}: {problem}")
    assert problems == [], "\n".join(problems)


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
            day = INVARIANT_LANDED + dt.timedelta(days=1)
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

    excused: list[str] = []
    checked: list[str] = []
    problems: list[str] = []

    for day, path in artifacts():
        if day <= INVARIANT_LANDED:
            excused.append(path.name)
            continue
        checked.append(path.name)
        text = path.read_text(encoding="utf-8")
        rows = len(family_rows(text))
        # The population is PRINTED, always: a clean verdict over a population that was
        # never named is indistinguishable from one that examined nothing (P29).
        print(f"checked: {path.name} — {rows} family row(s) in the fleet view")
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

    for name in excused:
        print(f"excused: {name} — predates the measurable-count invariant")

    absent = [anchor for anchor in PROCEDURE_ANCHORS if anchor not in PROCEDURE.read_text(encoding="utf-8")]
    if absent:
        problems.append(f"{PROCEDURE.relative_to(REPO)} does not name: {', '.join(absent)}")

    problems.extend(probe())
    problems.extend(probe_denominators())

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
