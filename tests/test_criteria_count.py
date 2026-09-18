#!/usr/bin/env python3
"""Gate: every stated quality-criteria count matches the rubric's live count.

Origin (issue #43). Eight lines across seven surfaces stated a criteria count that
did not match the rubric — and one file contradicted itself: `ONTOLOGY.md:37` read
"19 quality criteria across 6 families" while `ONTOLOGY.md:355` read "the 16
criteria across 5 families". The count was stated in twelve places and checked in
none, which is why it survived every audit run. That is prose no mechanism upholds
(P29): the number drifted silently because nothing read it.

**The predicate, stated because a count taken by a pattern is not a count of
items.** This gate does two different things, and both are named here.

  How the count is *taken.* `docs/quality-criteria.md` is parsed for its criteria
  rows (`| **Name** (X#) |`), each sitting under a `## <Family> — …` heading. The
  criteria total is the number of such rows. The family total is the number of
  *distinct families that own at least one row* — not the number of `##` headings,
  because a heading with no criteria under it is not a family.

  Which lines are *scanned.* `*.md` and `*.tmpl` at the repo root, plus `docs/`,
  `skills/`, `roles/` and `TEMPLATE/` recursively, minus `evidence/` — a dated
  historical record is not a claim about the live rubric. Every line matching
  `\\b(\\d{1,2})\\s+(criteria|families|family)\\b` is a claim, and its number must
  equal the parsed count. A `.tmpl` file is a shipped law surface, so it is
  scanned: an earlier sweep of this defect held only `*.md` and missed
  `TEMPLATE/SKILL.md.tmpl` entirely.

**The one allowance, and it is printed.** A line naming a rubric version other
than the live one *and* saying so (`superseded`, `historical`, `frozen`, …) is a
deliberate historical reference, not a stale claim: `docs/growth-stages.md` carries
a dated calibration run whose fleet scores are all out of v0.4's 68 points, so
rewriting its rubric line to the live version would falsify the table beneath it.
Such a line is reported as `excused:` — the shape `tools/ledger.py` uses for its
sequence exemptions, so "clean" and "excused" are never the same output.

**The pin.** Where `docs/quality-criteria.md` exists the count is read from it and
the shipped pin is asserted against it, so the pin cannot drift silently. A
bootstrapped factory carries no local rubric — its law says the criteria live in
the template project — so there the pin is the source of truth, and the gate says
which of the two it used.

It resolves its own tree, so one file serves both: run from this repo it checks the
root surfaces and `TEMPLATE/…`; run from `TEMPLATE/`, or from a bootstrapped
factory where the copies sit at the root, it checks the same law in place. The two
copies are byte-identical and paired by `tests/test_template_sync.py`.

Run:  python3 tests/test_criteria_count.py
Exit: 0 every stated count matches the rubric, 1 one does not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- the source of truth ------------------------------------------------------

RUBRIC = ("docs/quality-criteria.md",)

# What this gate ships believing the rubric says. Asserted against the rubric file
# whenever one is present, so it cannot drift silently where both exist; used as
# the source of truth where none is.
PIN = {"criteria": 19, "families": 6, "version": "v0.5"}

# --- the predicate ------------------------------------------------------------

CLAIM = re.compile(r"\b(\d{1,2})\s+(criteria|families|family)\b")
NOUN = {"criteria": "criteria", "families": "families", "family": "families"}

CRITERION_ROW = re.compile(r"^\| \*\*.+?\*\* \(([A-Z])\d+\) \|")
FAMILY_HEADING = re.compile(r"^## (.+?) — ")

VERSION = re.compile(r"\bv(\d+)\.(\d+)\b")
STATUS_VERSION = re.compile(r"Status:\s*v(\d+)\.(\d+)")
SUPERSEDED = re.compile(r"supersed|histor|frozen|no longer|at the time", re.IGNORECASE)

SCAN_GLOBS = (
    "*.md",
    "*.tmpl",
    "docs/**/*.md",
    "skills/**/*.md",
    "roles/**/*.md",
    "TEMPLATE/**/*.md",
    "TEMPLATE/**/*.tmpl",
)
EXCLUDE_DIRS = {"evidence", "__pycache__", ".git"}


def parse_rubric(text: str) -> tuple[int, int]:
    """Return `(criteria, families)` as the rubric states them."""
    heading: str | None = None
    owners: list[str] = []
    for line in text.splitlines():
        m = FAMILY_HEADING.match(line)
        if m:
            heading = m.group(1).strip()
            continue
        if heading and CRITERION_ROW.match(line):
            owners.append(heading)
    return len(owners), len(set(owners))


def rubric_version(text: str) -> str | None:
    """The live rubric's own version, read from its Status line."""
    m = STATUS_VERSION.search(text)
    return f"v{m.group(1)}.{m.group(2)}" if m else None


def is_excused(line: str, live_version: str) -> bool:
    """True when `line` marks itself as a reference to a superseded rubric."""
    m = VERSION.search(line)
    if not m:
        return False
    if f"v{m.group(1)}.{m.group(2)}" == live_version:
        return False
    return bool(SUPERSEDED.search(line))


def scanned_files() -> list[Path]:
    """Every shipped law/doc surface this gate reads, deduplicated and sorted."""
    found: set[Path] = set()
    for pattern in SCAN_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            if EXCLUDE_DIRS & set(path.relative_to(REPO_ROOT).parts):
                continue
            found.add(path)
    return sorted(found)


def probe() -> list[str]:
    """Probe the predicates against both shapes, and report anything wrong.

    A predicate that has only ever seen good input has not been shown to reject
    bad input.
    """
    failures: list[str] = []

    sample = (
        "## Documentation — what it is\n"
        "| **A** (D1) | x |\n"
        "| **B** (D2) | x |\n"
        "## Output — what it does\n"
        "| **C** (O1) | x |\n"
    )
    got = parse_rubric(sample)
    if got != (3, 2):
        failures.append(f"probe: rubric parse returned {got}, expected (3, 2)")

    empty_heading = "## Empty — nothing here\n\n## Real — something\n| **A** (R1) | x |\n"
    if parse_rubric(empty_heading) != (1, 1):
        failures.append("probe: a heading owning no criteria was counted as a family")

    for text in ("16 criteria across 5 families", "The 13 criteria are the floor", "across all 6 families"):
        if not CLAIM.search(text):
            failures.append(f"probe: the claim pattern missed a stated count: {text!r}")

    if CLAIM.search("the maximum is 76, scored 0-4 per criterion"):
        failures.append("probe: the claim pattern fired on a line stating no count")

    # The allowance must fire on a labelled historical reference, and must NOT fire
    # on a stale line that reads as current, nor on a line naming the live version.
    if not is_excused("Quality Criteria v0.4 (17 criteria) — superseded by v0.5", "v0.5"):
        failures.append("probe: a labelled historical reference was not excused")
    if is_excused("Quality Criteria v0.4 (17 criteria across 5 families)", "v0.5"):
        failures.append("probe: an unlabelled superseded version was excused as historical")
    if is_excused("Quality Criteria v0.5 (19 criteria across 6 families)", "v0.5"):
        failures.append("probe: a line naming the live version was excused")

    return failures


def main() -> int:
    problems = probe()
    excused: list[str] = []

    rubric_path = next((REPO_ROOT / r for r in RUBRIC if (REPO_ROOT / r).is_file()), None)
    if rubric_path is not None:
        text = rubric_path.read_text(encoding="utf-8")
        criteria, families = parse_rubric(text)
        if (criteria, families) != (PIN["criteria"], PIN["families"]):
            problems.append(
                f"pin drift: {rubric_path.relative_to(REPO_ROOT)} states {criteria} criteria "
                f"/ {families} families, this gate ships {PIN['criteria']} / {PIN['families']} "
                "— update PIN to the rubric it guards"
            )
        live_version = rubric_version(text) or PIN["version"]
        source = f"{rubric_path.relative_to(REPO_ROOT)} (parsed)"
    else:
        criteria, families = PIN["criteria"], PIN["families"]
        live_version = PIN["version"]
        source = f"the shipped pin {PIN['version']} — no local rubric in this tree"

    files = scanned_files()
    claims = 0
    for path in files:
        rel = path.relative_to(REPO_ROOT)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in CLAIM.finditer(line):
                claims += 1
                noun = NOUN[m.group(2)]
                expected = criteria if noun == "criteria" else families
                if int(m.group(1)) == expected:
                    continue
                if is_excused(line, live_version):
                    excused.append(f"{rel}:{lineno} — {m.group(0)!r} (a superseded rubric, labelled)")
                    continue
                problems.append(
                    f"{rel}:{lineno} states {m.group(1)} {noun}, the rubric has {expected} "
                    f"— {line.strip()[:110]!r}"
                )

    for line in excused:
        print(f"  excused: {line}")
    if problems:
        for line in problems:
            print(f"  FAIL {line}")
        return 1

    tail = f", {len(excused)} excused" if excused else ""
    print(
        f"criteria count: clean — {claims} claim(s) over {len(files)} file(s) all read "
        f"{criteria} criteria / {families} families{tail} (source: {source})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
