#!/usr/bin/env python3
"""Gate: a law file that names the conversion leg must name the row that leg reads.

WHY THIS GATE EXISTS. `docs/measurement-procedure.md` §5.4 point 5 states, from a
measurement taken 2026-10-10, that **the declaration is NOT the score row** — the
`score-conversion` leg reads `conversion` rows only, and a `score` row answers nothing.
`skills/meta-factory/SKILL.md` nonetheless said, at two places, that "the run DECLARES
the regression on its own score row": the procedure's own vocabulary for a join the
instrument does not perform. The procedure's correction landed and the skill's
restatement was never swept, because **no gate compares the two artifacts** — the
suite reads the procedure (`tests/test_law_coverage.py`, `tests/test_template_sync.py`)
and reads the law table (`tests/test_declaration_drift.py`), and nothing compares a
law SENTENCE to the document that owns it.

WHY IT MATTERED MORE THAN A TYPO. The skill is the always-loaded law, so the stale
sentence was reproduced by every lane that briefed or acted from it — measured
2026-10-21: Triage's 18:00Z brief to Surveys repeated the skill's wording and Surveys
corrected the brief. The defect survived eleven rounds because the round that would
have exercised the join — a round with a below-floor cell — was answered each time by
the lane's own memory of the rule rather than by reading it.

THE PREDICATE, two legs, both pure over TEXT so a synthetic string can probe them:

  1. FORBIDDEN WORDING — no law line may assert the declaration happens on a score
     row (`\\bown\\s+score\\s+row\\b`). This is the exact phrasing that propagated.
  2. REQUIRED VOCABULARY — every law LINE naming `score-conversion` must also name
     `conversion` as a distinct token. Leg 2 is the durable half: a re-wording that
     evades leg 1 ("declares it in the score row") still fails leg 2, because the line
     names the leg and never the row type.

THE UNIT IS THE LINE, and that bound is stated rather than implied: a claim wrapped
across two lines evades leg 2. Markdown law here is one paragraph per line, so the
bound costs nothing today, and the alternative — sentence splitting — misfires on
`docs/measurement-procedure.md` §5.4-style citations, which carry dots inside a
sentence. A gate that reds on correct text teaches its reader to ignore red (#507).

THE PREMISE IS CHECKED, NOT ASSUMED. Leg 1's authority is the owning document. If that
document stops carrying the refutation, this gate must NOT keep passing on a premise
that moved — it FAILS naming the owning doc, so a reader is sent to the source rather
than to a green tick that means nothing. The hermetic fixture is the CONTROL (below);
the live doc is corroboration, per the rule that a check's independent declaration must
be stable rather than read from whatever a live artifact currently says.

SCOPE. This gate guards one declared pair — the conversion join — and does not claim to
compare law prose to owning docs in general. Prose equivalence is not mechanically
derivable; a declared pair with a pure predicate is the shape that is gateable, and
adding a second pair means adding a second declared predicate, never widening this one.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The owning document, and the sentence that gives this gate its authority.
OWNING_DOC = "docs/measurement-procedure.md"
OWNING_PREMISE = "The declaration is NOT the score row"

#: The leg's own name, as it appears in law prose.
LEG_TOKEN = "score-conversion"

#: The exact stale wording that propagated from the skill into a lane brief.
FORBIDDEN_PHRASE = re.compile(r"\bown\s+score\s+row\b", re.IGNORECASE)

#: The token leg 2 requires: `conversion` as a row type, not the leg's own name.
CONVERSION_ROW = re.compile(r"\bconversion\b", re.IGNORECASE)

#: Law surfaces scanned. `skills/meta-factory/*.md` is the meta-factory's own law
#: (instrument docs reload into it through symlinks); the two root names are what a
#: bootstrapped member carries instead, so the same predicate reads a member tree.
LAW_GLOBS = ("skills/meta-factory/*.md", "SKILL.md", "SKILL.md.tmpl")


def law_files(root: Path) -> list[Path]:
    """Every law file present in this tree, sorted, deduplicated."""
    found: list[Path] = []
    for pattern in LAW_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path not in found:
                found.append(path)
    return found


def _names_conversion_row(line: str) -> bool:
    """True when the line names `conversion` as a row type, not only the leg's name."""
    stripped = line.replace("`score-conversion`", " ").replace(LEG_TOKEN, " ")
    return CONVERSION_ROW.search(stripped) is not None


def drift_problems(text: str) -> list[str]:
    """The predicate. Pure over text, so a fixture can probe it in both directions."""
    problems: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if FORBIDDEN_PHRASE.search(line):
            problems.append(
                f"line {lineno}: asserts the declaration on 'its own score row' — the "
                f"leg reads `conversion` rows only "
                f"(docs/measurement-procedure.md §5.4 point 5)"
            )
        if LEG_TOKEN in line and not _names_conversion_row(line):
            problems.append(
                f"line {lineno}: names `{LEG_TOKEN}` but never names the `conversion` "
                f"row that leg reads"
            )
    return problems


# --- hermetic controls: the predicate must fire on bad text and clear good text ------

CONTROL_VIOLATING = (
    "the run DECLARES the regression on its own score row, the patrol's "
    "`score-conversion` leg READS it."
)
CONTROL_LEG_ONLY = "the patrol's `score-conversion` leg reads it."
CONTROL_CORRECTED = (
    "the run DECLARES the regression on a `conversion` row naming its artifact, the "
    "patrol's `score-conversion` leg READS it."
)


def test_predicate_bites_in_both_directions() -> None:
    """A passing live read must not be a predicate that can never fire."""
    both = drift_problems(CONTROL_VIOLATING)
    assert len(both) == 2, f"expected both legs to fire, got {both}"

    leg_two_only = drift_problems(CONTROL_LEG_ONLY)
    assert len(leg_two_only) == 1, f"expected leg 2 alone to fire, got {leg_two_only}"

    assert drift_problems(CONTROL_CORRECTED) == [], (
        "the corrected wording must clear both legs"
    )


def test_law_names_the_row_the_conversion_leg_reads() -> None:
    """Live read over this tree's law surfaces, with its population printed."""
    owning = REPO_ROOT / OWNING_DOC
    assert owning.is_file(), f"{OWNING_DOC} is missing, so this gate has no authority"
    owning_text = owning.read_text(encoding="utf-8")
    assert OWNING_PREMISE in owning_text, (
        f"PREMISE MOVED: {OWNING_DOC} no longer states {OWNING_PREMISE!r}. This gate's "
        f"leg 1 is derived from that sentence; re-derive it before re-arming the gate, "
        f"or delete the gate. Do not silence it."
    )

    files = law_files(REPO_ROOT)
    assert files, "no law files found — the discovery globs no longer match this tree"

    failures: list[str] = []
    leg_lines = 0
    for path in files:
        rel = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8", errors="replace")
        leg_lines += sum(1 for line in text.splitlines() if LEG_TOKEN in line)
        for problem in drift_problems(text):
            failures.append(f"{rel}: {problem}")

    print(
        f"examined {len(files)} law file(s), {leg_lines} line(s) naming "
        f"`{LEG_TOKEN}`, {len(failures)} problem(s)"
    )
    for rel in files:
        print(f"  read {rel.relative_to(REPO_ROOT)}")

    assert not failures, (
        "a law file contradicts the document that owns the conversion join:\n  "
        + "\n  ".join(failures)
    )


if __name__ == "__main__":
    test_predicate_bites_in_both_directions()
    test_law_names_the_row_the_conversion_leg_reads()
