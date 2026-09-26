#!/usr/bin/env python3
"""Gate: the day's score artifact carries every section the procedure requires.

Origin (issue #69). The measurement run's step 7 named the artifact's PATH, the
`score` row, the commit and the closing workspace invariant — but not the
artifact's SECTIONS, and no gate asserted them. A restructure therefore dropped
the per-family criterion scorecards and every gate still read rc=0: the run's own
output was the one surface nothing covered, which is P29 dead text at the
procedure's most load-bearing step.

Three parts, the shape `tests/test_score_gate_recorded.py` already uses.

1. **A pure predicate.** `missing_sections(text)` is factored out so a synthetic
   artifact can probe it: a rule that has only ever seen good input has not been
   shown to reject bad input.
2. **A forward-only requirement with a boundary.** An artifact dated strictly
   AFTER `INVARIANT_LANDED` must carry every required section. The boundary is
   EXCLUSIVE because the artifact for the day the invariant lands is already
   written, and a section reconstructed after the fact is fabricated provenance —
   the same no-backfill law as the close trailer's. Pre-boundary artifacts are
   reported as `excused:`, with their count, so "clean" and "excused" are never
   the same output.
3. **A coupling to the procedure.** The gate holds the canonical list; step 7 must
   NAME it. A gate whose requirement is not stated where the run reads it enforces
   a rule nobody was told — the coupling probe asserts each anchor appears in
   `docs/measurement-procedure.md`.

THE REQUIRED SET, and where each entry comes from
-------------------------------------------------
Seven entries are DERIVED: they are present in BOTH committed artifacts
(`evidence/scores/2026-09-17.md` and `2026-09-18.md`), which is what makes them the
artifact's actual shape rather than a preference. Two are MANDATED by the ruling at
ledger n=199, which requires the artifact to state the run's own self-audit verdict
and the pacemaker-thinness result — neither committed artifact carries them as a
section, so they cannot be derived and their authority is the ruling.

Two entries are matched by FAMILY rather than by an exact string, and the reason is
in the artifacts: the method-note heading is not identical across the two runs
(`## Method notes and limits of this run` vs `## Method Notes & Survey Limits`), and
the per-family scorecards are numbered. Requiring either as a fixed string would
invent a form the artifacts do not have. So the predicate is loose-then-strict, the
#62 shape: the loose form finds the section whatever it is called, and the procedure
names the canonical heading.

Run:  python3 -m pytest tests/test_score_artifact_sections.py -q
Exit: 0 clean or fully excused, non-zero on any post-boundary artifact missing a section.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "evidence" / "scores"
PROCEDURE = REPO / "docs" / "measurement-procedure.md"
CRITERIA = REPO / "docs" / "quality-criteria.md"

# The day this requirement lands. The boundary is EXCLUSIVE: an artifact dated
# strictly after this day must comply; this day's artifact and earlier are excused,
# because the landing day's artifact is already written and is never backfilled.
INVARIANT_LANDED = dt.date(2026, 9, 19)

# The day the maturity-band requirement lands, for the leg added by issue #154.
# EXCLUSIVE on the same terms, and placed a day earlier than the section boundary
# for a measured reason: the artifacts at 2026-09-22, -23 and -24 carry real band
# mismatches (Miidas 60/76 and InferHub Watch 58/76 both labelled "Scalable"),
# they predate the law, and a band rewritten into a dated artifact would be a
# falsified record rather than a repair -- so they are EXCUSED AND PRINTED, never
# repaired. 2026-09-25 is the first artifact written under the law and is the
# brief's own acceptance case, so it is CHECKED rather than excused.
BAND_LANDED = dt.date(2026, 9, 24)

_ARTIFACT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")

# kind "exact"     — a heading line equal to `pattern`
# kind "prefix"    — a heading line starting with `pattern`
# kind "scorecard" — at least one numbered per-factory scorecard heading
# kind "selfaudit" — a heading naming the run's own self-audit verdict
# kind "pacemaker" — a heading carrying the pacemaker-thinness result (P7)
#
# Each tuple is (label, kind, pattern, procedure_anchor). The anchor is the exact
# text step 7 must carry, which is what couples the requirement to the procedure.
REQUIRED: list[tuple[str, str, str, str]] = [
    (
        "executive summary",
        "exact",
        "## Executive Summary & Movements",
        "## Executive Summary & Movements",
    ),
    (
        "fleet family view",
        "prefix",
        "### Family-level fleet view",
        "### Family-level fleet view",
    ),
    (
        "subject-matter consulting gate status",
        "exact",
        "## Subject Matter Consulting Gate Status",
        "## Subject Matter Consulting Gate Status",
    ),
    (
        "detailed factory scorecards",
        "exact",
        "## Detailed Factory Scorecards",
        "## Detailed Factory Scorecards",
    ),
    (
        "per-family criterion scorecards",
        "scorecard",
        "### <n>. <factory> — <score> / 76",
        "### <n>. <factory> — <score> / 76",
    ),
    (
        "consulting advisories",
        "exact",
        "## Consulting Advisories (prioritised)",
        "## Consulting Advisories (prioritised)",
    ),
    (
        "method notes",
        "prefix",
        "## Method",
        "## Method",
    ),
    (
        "self-audit verdict",
        "selfaudit",
        "## Run Self-Audit Verdict",
        "## Run Self-Audit Verdict",
    ),
    (
        "pacemaker thinness result",
        "pacemaker",
        "## Pacemaker Verification",
        "## Pacemaker Verification",
    ),
]

_SCORECARD = re.compile(r"^### \d+\.\s+\S")
_SELFAUDIT = re.compile(r"^## .*[Ss]elf-[Aa]udit")
_PACEMAKER = re.compile(r"^## .*[Pp]acemaker")


def headings(text: str) -> list[str]:
    """Every level-2 or level-3 heading line, stripped. Level-3 is not level-2."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.startswith("## ") or line.startswith("### ")
    ]


def missing_sections(text: str) -> list[str]:
    """Labels of every required section absent from an artifact's text.

    Pure: no file system, no clock. A synthetic artifact probes it directly.
    """
    found = headings(text)
    missing: list[str] = []
    for label, kind, pattern, _anchor in REQUIRED:
        if kind == "exact":
            present = pattern in found
        elif kind == "prefix":
            present = any(h.startswith(pattern) for h in found)
        elif kind == "scorecard":
            present = any(_SCORECARD.match(h) for h in found)
        elif kind == "selfaudit":
            present = any(_SELFAUDIT.match(h) for h in found)
        elif kind == "pacemaker":
            present = any(_PACEMAKER.match(h) for h in found)
        else:  # pragma: no cover - a bad kind is a programming error, not input
            raise AssertionError(f"unknown section kind: {kind!r}")
        if not present:
            missing.append(label)
    return missing


def artifacts() -> list[tuple[dt.date, Path]]:
    """Every dated score artifact, oldest first. `*-self-audit.md` is not one."""
    out: list[tuple[dt.date, Path]] = []
    for path in sorted(SCORES.glob("*.md")):
        match = _ARTIFACT_RE.match(path.name)
        if match is None:
            continue
        year, month, day = (int(g) for g in match.groups())
        out.append((dt.date(year, month, day), path))
    return out


# --- the maturity band, computed from the rubric rather than typed -----------
#
# Filed as issue #154. Each scorecard states a maturity band beside its score, and
# until this leg the band was TYPED -- nothing computed it, so nothing could catch
# it drifting. One table in one run labelled Miidas (60/76 = 78.9%) and InferHub
# Watch (58/76 = 76.3%) "Scalable" while OpenCrabs dev (62/76 = 81.6%) read
# "Optimizing": the same band, three factories, two labels, and the score column
# correct in every case. The defect is in the label, never the measurement, and no
# score moves -- the fleet total is unchanged.
#
# The thresholds are READ from `docs/quality-criteria.md`, never restated here. A
# hardcoded copy would pass a rubric change silently, which is the class this leg
# exists to close -- and a probe drives a MUTATED rubric to prove the read.

_BAND_ROW = re.compile(
    r"^\|\s*\*\*(?P<name>[^*]+)\*\*\s*\|\s*"
    r"(?P<lo>\d+)[–-](?P<hi>\d+)%\s*\((?P<raw_lo>\d+)[–-](?P<raw_hi>\d+)\)\s*\|"
)
_RUBRIC_MAX = re.compile(r"maximum is \*\*(\d+)\*\*")

# `### 1. Meta-factory (`/root/agent-factories`) — 70 / 76 (92.1%), Optimizing`
# and the movement form `... (71%), Scalable ⬇`. The trailing arrow is REAL in two
# committed artifacts (2026-09-17 and -18, two headings each), so an end-anchored
# pattern would silently skip those headings and a band could leave the population
# with no error -- the failure this leg cannot see. The band group therefore takes
# whatever trails the comma and the arrow is stripped from it.
_SCORECARD_BAND = re.compile(
    r"^### \d+\.\s+(?P<name>.+?)\s+—\s+(?P<score>\d+)\s*/\s*(?P<den>\d+)\s*"
    r"\((?P<pct>\d+(?:\.\d+)?)%\)\s*(?:,\s*(?P<band>.*))?$"
)
_MOVEMENT = re.compile(r"[⬆⬇↑↓]")

def _shown(path: Path) -> str:
    """A path as it reads in a message: relative when it is inside the repo.

    Probes drive `read_bands` from a temporary directory, so a bare
    `relative_to(REPO)` would raise `ValueError` in exactly the case the message
    exists to report.
    """
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)

def read_bands(path: Path) -> tuple[list[tuple[str, int, int]], int | None, list[str]]:
    """`(bands, max_score, problems)`, READ from the criteria document.

    An ABSENT document is not a problem: a factory that ships no rubric has
    declared no bands, which is the undeclared path `declared()` already takes. A
    PRESENT document whose table will not parse IS a problem -- the two are
    different facts and must never render the same way (the #164 split).
    """
    if not path.is_file():
        return [], None, []
    text = path.read_text(encoding="utf-8")
    bands: list[tuple[str, int, int]] = []
    for line in text.splitlines():
        match = _BAND_ROW.match(line.strip())
        if match is not None:
            bands.append(
                (match.group("name").strip(), int(match.group("lo")), int(match.group("hi")))
            )
    max_match = _RUBRIC_MAX.search(text)
    problems: list[str] = []
    if not bands:
        problems.append(
            f"{_shown(path)}: the maturity band table did not parse "
            f"-- no band row matched"
        )
    if max_match is None:
        problems.append(f"{_shown(path)}: the rubric maximum did not parse")
    return bands, (int(max_match.group(1)) if max_match else None), problems

def band_for(pct: float, bands: list[tuple[str, int, int]]) -> str | None:
    """The band the rubric assigns to `pct`, or None if it falls in no band."""
    for name, low, high in bands:
        if low <= pct <= high:
            return name
    return None

def band_problems(
    text: str, bands: list[tuple[str, int, int]], max_score: int | None
) -> list[str]:
    """Problems in one artifact's scorecard bands. Pure: no file system, no clock.

    Three ways a heading is wrong, and each names the heading and both values:
      - its denominator is not the rubric's maximum. The band table is calibrated
        to that maximum, so a different denominator bands on the wrong scale;
      - it states no band at all -- silence is not compliance;
      - it states a band the rubric does not compute from its own score.
    """
    problems: list[str] = []
    for line in text.splitlines():
        match = _SCORECARD_BAND.match(line.strip())
        if match is None:
            continue
        name = match.group("name").strip()
        denominator = int(match.group("den"))
        pct = float(match.group("pct"))
        band = _MOVEMENT.sub("", match.group("band") or "").strip()
        if max_score is not None and denominator != max_score:
            problems.append(
                f"{name}: scored out of {denominator}, but the rubric's maximum is "
                f"{max_score} -- the band table is calibrated to {max_score}, so this "
                f"heading bands on the wrong scale"
            )
            continue
        if not band:
            problems.append(f"{name}: states no maturity band beside its {pct}%")
            continue
        expected = band_for(pct, bands)
        if expected is None:
            problems.append(f"{name}: {pct}% falls in no band the rubric declares")
        elif band != expected:
            problems.append(f"{name}: labelled {band}, but {pct}% is {expected}")
    return problems

def band_leg() -> tuple[list[str], list[str], list[str], bool]:
    """`(excused, checked, problems, declared)` over the live tree.

    `declared` is False when the factory ships no rubric: nothing is asserted, and
    the caller says so rather than printing a clean verdict over a population that
    was never named.
    """
    bands, max_score, problems = read_bands(CRITERIA)
    if not bands and max_score is None and not problems:
        return [], [], [], False
    excused: list[str] = []
    checked: list[str] = []
    found: list[str] = list(problems)
    for day, path in artifacts():
        if day <= BAND_LANDED:
            excused.append(path.name)
            continue
        checked.append(path.name)
        found.extend(
            f"{path.name}: {problem}"
            for problem in band_problems(path.read_text(encoding="utf-8"), bands, max_score)
        )
    return excused, checked, found, True

# The synthetic artifact the probes build from. One entry per required section, so
# omitting an entry is exactly how a probe makes one section absent. The key set is
# asserted EQUAL to the required labels: the fixture cannot drift from the rule.
SECTIONS: dict[str, list[str]] = {
    "executive summary": ["## Executive Summary & Movements"],
    "fleet family view": [
        "### Family-level fleet view (mean score per family, out of 4 per criterion)"
    ],
    "subject-matter consulting gate status": ["## Subject Matter Consulting Gate Status"],
    "detailed factory scorecards": ["## Detailed Factory Scorecards"],
    "per-family criterion scorecards": [
        "### 1. Meta-factory (`/root/agent-factories`) — 71 / 76",
        "### 2. OpenCrabs dev (`/root/opencrabs`) — 63 / 76",
    ],
    "consulting advisories": ["## Consulting Advisories (prioritised)"],
    "method notes": ["## Method notes and limits of this run"],
    "self-audit verdict": ["## Run Self-Audit Verdict"],
    "pacemaker thinness result": ["## Pacemaker Verification"],
}


def synthetic_artifact(omit: str | None = None) -> str:
    """A well-formed artifact, optionally with one required section removed."""
    lines = ["# Factory scores — 2026-09-20 (Quality Criteria v0.5)", ""]
    for label, section in SECTIONS.items():
        if label == omit:
            continue
        lines.extend(section)
        lines.append("")
    return "\n".join(lines)


# --- probes -----------------------------------------------------------------


def test_fixture_matches_the_required_set() -> None:
    """The fixture and the rule cannot drift: same labels, both directions."""
    labels = [label for label, _kind, _pattern, _anchor in REQUIRED]
    assert set(SECTIONS) == set(labels)
    assert len(labels) == len(set(labels))


def test_well_formed_artifact_reports_nothing_missing() -> None:
    assert missing_sections(synthetic_artifact()) == []


def test_every_required_section_bites() -> None:
    """Removing any one section must be reported — the bite proof, per entry."""
    for label in SECTIONS:
        reported = missing_sections(synthetic_artifact(omit=label))
        assert reported == [label], f"omitting {label!r} reported {reported!r}"


def test_a_section_free_artifact_reports_every_label() -> None:
    assert missing_sections("") == [label for label, _k, _p, _a in REQUIRED]


def test_an_unnumbered_scorecard_does_not_count() -> None:
    """The per-family scorecards are numbered; a bare `### Meta-factory` is not one."""
    text = synthetic_artifact(omit="per-family criterion scorecards")
    text += "\n### Meta-factory (`/root/agent-factories`) — 71 / 76\n"
    assert "per-family criterion scorecards" in missing_sections(text)


def test_a_related_but_unnamed_heading_does_not_count() -> None:
    """A self-audit heading that never says self-audit is not the verdict section."""
    text = synthetic_artifact(omit="self-audit verdict")
    text += "\n## Gate Status\n"
    assert "self-audit verdict" in missing_sections(text)


# --- probes: the maturity band leg (issue #154) -----------------------------

_GOOD_HEADING = "### 1. Meta-factory (`/root/agent-factories`) — 70 / 76 (92.1%), Optimizing"

def band_declared() -> bool:
    """Whether this factory declares a maturity band rubric at all.

    The bands and the rubric maximum are declared by docs/quality-criteria.md,
    which the template does not ship. A factory without it has declared no band
    law, so the band probes assert nothing and say so -- the same undeclared path
    `declared()` takes for the section law, and the reason the TEMPLATE twin does
    not RED where it is copied (the #78 class).
    """
    return CRITERIA.is_file()

def _artifact_with(heading: str) -> str:
    return f"# Factory scores — 2026-09-20\n\n{heading}\n"

def _bands_from_the_rubric() -> tuple[list[tuple[str, int, int]], int | None]:
    """The live rubric's bands and maximum, for probes that need a real set."""
    bands, max_score, problems = read_bands(CRITERIA)
    assert problems == [], problems
    assert bands, "the live rubric must declare bands"
    return bands, max_score

def test_the_live_rubric_declares_four_bands_covering_every_percent() -> None:
    """The read is a property of the document, so it is asserted as one.

    Contiguous and exhaustive over 0-100: a gap would silently admit a score with
    no band, and `band_for` would return None for a legitimate score.
    """
    if not band_declared():
        return
    bands, max_score = _bands_from_the_rubric()
    assert len(bands) == 4, bands
    assert max_score == 76, max_score
    assert bands[0][1] == 0, bands
    assert bands[-1][2] == 100, bands
    for (_n1, _lo1, hi1), (_n2, lo2, _hi2) in zip(bands, bands[1:]):
        assert lo2 == hi1 + 1, bands

def test_a_correct_band_reports_nothing() -> None:
    if not band_declared():
        return
    bands, max_score = _bands_from_the_rubric()
    assert band_problems(_artifact_with(_GOOD_HEADING), bands, max_score) == []

def test_a_wrong_band_bites() -> None:
    """The filed instance: Miidas 60/76 = 78.9% labelled `Scalable`."""
    if not band_declared():
        return
    bands, max_score = _bands_from_the_rubric()
    text = _artifact_with("### 4. Miidas (`/root/miidas`) — 60 / 76 (78.9%), Scalable")
    problems = band_problems(text, bands, max_score)
    assert len(problems) == 1, problems
    assert "Scalable" in problems[0] and "Optimizing" in problems[0], problems[0]
    assert "78.9" in problems[0], problems[0]

def test_the_band_is_computed_from_the_score_not_the_neighbours() -> None:
    """The 09-25 case: 58/76 = 76.3% is Optimizing even beside a 65.8% Scalable."""
    if not band_declared():
        return
    bands, max_score = _bands_from_the_rubric()
    text = _artifact_with(
        "### 3. InferHub Watch (`/root/inferhub-watch`) — 58 / 76 (76.3%), Optimizing"
    ) + "\n### 6. AI AntiSpam (`/root/ai-antispam`) — 50 / 76 (65.8%), Scalable\n"
    assert band_problems(text, bands, max_score) == []

def test_a_missing_band_bites() -> None:
    """Silence is not compliance: a scorecard that states no band is a problem."""
    if not band_declared():
        return
    bands, max_score = _bands_from_the_rubric()
    text = _artifact_with("### 1. Meta-factory — 70 / 76 (92.1%)")
    problems = band_problems(text, bands, max_score)
    assert len(problems) == 1 and "states no maturity band" in problems[0], problems

def test_a_wrong_denominator_bites() -> None:
    """The 09-16 shape: a 68-max rubric bands on a scale this table is not."""
    if not band_declared():
        return
    bands, max_score = _bands_from_the_rubric()
    text = _artifact_with("### 1. Meta-factory — 62 / 68 (91.2%), Optimizing")
    problems = band_problems(text, bands, max_score)
    assert len(problems) == 1 and "maximum is 76" in problems[0], problems

def test_a_trailing_movement_arrow_still_parses() -> None:
    """Two committed artifacts carry `⬇`, so an end-anchored pattern would skip them.

    Without this the heading leaves the population silently: the band could then
    drift with nothing to catch it, which is the failure this leg cannot see.
    """
    if not band_declared():
        return
    bands, max_score = _bands_from_the_rubric()
    assert band_problems(_artifact_with(_GOOD_HEADING + " ⬇"), bands, max_score) == []
    wrong = _artifact_with("### 1. Meta-factory — 70 / 76 (92.1%), Scalable ⬇")
    problems = band_problems(wrong, bands, max_score)
    assert len(problems) == 1 and "Optimizing" in problems[0], problems

def test_the_rubric_is_read_and_not_restated() -> None:
    """A mutated rubric moves the band, which a hardcoded copy could not do.

    This is the criterion's own proof: the thresholds live in the document, so
    changing the document changes the verdict. A literal table in this file would
    pass the mutation and fail here.
    """
    if not band_declared():
        return
    bands, max_score = _bands_from_the_rubric()
    assert band_for(78.9, bands) == "Optimizing"
    with tempfile.TemporaryDirectory() as tmp:
        moved = Path(tmp) / "quality-criteria.md"
        moved.write_text(
            "| Band | Score | Reading |\n|---|---|---|\n"
            "| **Provisional** | 0–50% (0–38) | moved |\n"
            "| **Operational** | 51–75% (39–57) | moved |\n"
            "| **Scalable** | 76–90% (58–68) | moved |\n"
            "| **Optimizing** | 91–100% (69–76) | moved |\n"
            "\nThe maximum is **76**.\n",
            encoding="utf-8",
        )
        moved_bands, moved_max, moved_problems = read_bands(moved)
        assert moved_problems == [], moved_problems
        assert moved_max == 76
        assert band_for(78.9, moved_bands) == "Scalable", moved_bands
        # 78.9% is Optimizing under the live rubric and Scalable under the mutated
        # one, so the same heading flips: proof the thresholds came from the FILE
        # rather than from a literal in this one. A score in a band both rubrics
        # agree on (92.1% is Optimizing under either) would prove nothing.
        miidas = _artifact_with("### 4. Miidas — 60 / 76 (78.9%), Optimizing")
        assert band_problems(miidas, bands, max_score) == []
        moved_found = band_problems(miidas, moved_bands, moved_max)
        assert len(moved_found) == 1, moved_found
        assert "Scalable" in moved_found[0], moved_found[0]

def test_a_present_but_unparseable_rubric_is_a_problem_not_a_skip() -> None:
    """The #164 split: by-design absence passes, a lost table is a real problem."""
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "quality-criteria.md"
        assert read_bands(missing) == ([], None, [])
        broken = Path(tmp) / "broken.md"
        broken.write_text("# Quality criteria\n\nno table here\n", encoding="utf-8")
        bands, max_score, problems = read_bands(broken)
        assert bands == [] and max_score is None
        assert len(problems) == 2, problems
        assert any("band table did not parse" in p for p in problems), problems
        assert any("maximum did not parse" in p for p in problems), problems

def test_the_band_boundary_excuses_the_pre_law_artifacts() -> None:
    """Forward-only: the artifacts that predate the law are excused, never repaired.

    Asserted over whatever the tree holds, with this factory's own instances named
    as the concrete case: 09-22/-23/-24 carry real mismatches and are excused,
    while 09-25 -- the first written under the law -- is CHECKED.
    """
    excused, checked, _problems, declared_here = band_leg()
    if not declared_here:
        return
    assert set(excused) | set(checked) == {p.name for _d, p in artifacts()}
    assert not (set(excused) & set(checked))
    present = {p.name for _d, p in artifacts()}
    for name in ("2026-09-22.md", "2026-09-23.md", "2026-09-24.md"):
        if name in present:
            assert name in excused, f"{name} predates the band law and must be excused"
    for name in ("2026-09-25.md", "2026-09-26.md"):
        if name in present:
            assert name in checked, f"{name} is written under the band law and is checked"

def test_the_live_band_population_is_clean() -> None:
    """The live check is non-vacuous and green -- the brief's own acceptance case."""
    _excused, checked, problems, declared_here = band_leg()
    if not declared_here:
        return
    assert checked, "the band leg must examine a population, not report a clean zero"
    assert problems == [], "\n".join(problems)

def declared() -> bool:
    """Whether this factory declares required sections at all.

    The list is DERIVED from a factory's own committed artifacts and stated in
    `docs/measurement-procedure.md`. The score file itself is template-level —
    `SKILL.md.tmpl`, `ONTOLOGY.md.tmpl` and `processes.md.tmpl` all name it — but
    WHAT it must contain is declared by that document, which the template does
    not ship. A factory without it has declared no required sections, so there is
    nothing for this gate to assert; it says so and passes, the way
    `tests/test_docs_sync.py` passes on a tree with no `TEMPLATE/` to pair.
    """
    return PROCEDURE.is_file()


def test_procedure_names_every_anchor() -> None:
    """The rule is stated where the run reads it, not only where it is enforced."""
    if not declared():
        return
    text = PROCEDURE.read_text(encoding="utf-8")
    absent = [anchor for _l, _k, _p, anchor in REQUIRED if anchor not in text]
    assert absent == [], f"docs/measurement-procedure.md does not name: {absent}"


def test_pre_boundary_artifacts_are_excused_not_required() -> None:
    """The boundary is exclusive: at or before the landing day is excused, never checked.

    Asserted as a property over whatever artifacts the tree holds — a bootstrapped
    factory has none of this factory's — with this factory's own landing-day pair
    named as the concrete case where they are present.
    """
    found = artifacts()
    present = {path.name for _day, path in found}
    excused = {path.name for day, path in found if day <= INVARIANT_LANDED}
    checked = {path.name for day, path in found if day > INVARIANT_LANDED}
    assert excused | checked == present
    assert not (excused & checked)
    for name in ("2026-09-19.md", "2026-09-18.md"):
        if name in present:
            assert name in excused


def test_post_boundary_artifacts_carry_every_required_section() -> None:
    if not declared():
        return
    problems: list[str] = []
    for day, path in artifacts():
        if day <= INVARIANT_LANDED:
            continue
        missing = missing_sections(path.read_text(encoding="utf-8"))
        if missing:
            problems.append(f"{path.name}: missing {', '.join(missing)}")
    assert problems == [], "\n".join(problems)


def test_a_factory_without_the_procedure_declares_nothing() -> None:
    """The undeclared path passes and says why — this is the template's own case.

    The score file is template-level, but the required-section list is declared by
    `docs/measurement-procedure.md`, which the template does not ship. A factory
    without it must NOT red: it has declared no sections to assert. The guard is
    asserted here so it is proven rather than merely written.
    """
    global PROCEDURE
    saved = PROCEDURE
    try:
        PROCEDURE = REPO / "docs" / "no-such-procedure.md"
        assert declared() is False
        assert main() == 0
        assert test_procedure_names_every_anchor() is None
        assert test_post_boundary_artifacts_carry_every_required_section() is None
    finally:
        PROCEDURE = saved
    assert declared() is True


def main() -> int:
    if not declared():
        print(
            f"no {PROCEDURE.relative_to(REPO)} — no required-section law is declared; "
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
        missing = missing_sections(path.read_text(encoding="utf-8"))
        if missing:
            problems.append(f"{path.name}: missing {', '.join(missing)}")

    for name in excused:
        print(f"excused: {name} — predates the required-section invariant")

    # The maturity band leg (issue #154). It reports its OWN population, because a
    # clean verdict over a population that was never named is indistinguishable
    # from one that examined nothing (P29).
    band_excused, band_checked, band_found, band_declared = band_leg()
    if not band_declared:
        print(
            f"no {CRITERIA.relative_to(REPO)} — no maturity band law is declared; "
            f"nothing to assert about bands"
        )
    else:
        for name in band_excused:
            print(f"excused (band): {name} — predates the maturity-band invariant")
        if band_checked:
            print(
                f"maturity band leg: {len(band_checked)} artifact(s) checked "
                f"({', '.join(band_checked)}), {len(band_excused)} excused"
            )
        else:
            print(
                "maturity band leg: 0 artifact(s) checked — the post-boundary "
                "population is EMPTY, so no band was verified"
            )
        problems.extend(f"band: {problem}" for problem in band_found)

    if problems:
        print("score artifact problems:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(
        f"score artifact sections ok: {len(checked)} artifact(s) checked, "
        f"{len(excused)} excused, {len(REQUIRED)} required section(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
