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
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "evidence" / "scores"
PROCEDURE = REPO / "docs" / "measurement-procedure.md"

# The day this requirement lands. The boundary is EXCLUSIVE: an artifact dated
# strictly after this day must comply; this day's artifact and earlier are excused,
# because the landing day's artifact is already written and is never backfilled.
INVARIANT_LANDED = dt.date(2026, 9, 19)

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

    if problems:
        print("required sections absent from a post-boundary artifact:", file=sys.stderr)
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
