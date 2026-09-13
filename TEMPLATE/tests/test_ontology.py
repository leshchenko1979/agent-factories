#!/usr/bin/env python3
"""Vocabulary gate for the agent-factories repo.

Parses the banned-synonyms table out of ONTOLOGY.md and fails when the repo's
own prose uses a banned word. The table is the source of truth, so the ban list
and the gate cannot drift apart: add a row to ONTOLOGY.md and the next run
enforces it.

Run:  python3 tests/test_ontology.py
Exit: 0 clean, 1 drift found.

Why a gate and not a review checklist: the rubric's Vocabulary conformance
criterion (L2) counts an ontology that a test enforces as law, and one nobody
can violate as documentation. This is the difference.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ONTOLOGY = REPO / "ONTOLOGY.md"

# Files scanned. Markdown and template prose is where vocabulary drift lives;
# the ontology itself is excluded because it must name every banned word.
SCAN_SUFFIXES = {".md", ".tmpl"}
SKIP_DIRS = {".git", "node_modules", "__pycache__"}

# Lines that may use a banned word, each with the substring that justifies it.
# An entry exempts a line only when the line ALSO contains `substring`, so a
# historical mention stays visible and is justified at the point of use rather
# than silently tolerated everywhere the word appears.
EXEMPTIONS: list[tuple[str, str, str]] = [
    (
        "docs/best-practices.md",
        "SUPERVISOR / TRIAGE / TOOLSMITH",
        "P5 names the original role set as the evidence for the pattern; "
        "the roles were real under those names.",
    ),
    (
        "docs/best-practices.md",
        "was renamed **HQ**",
        "the rename record itself — rewriting it would delete the provenance",
    ),
    (
        "evidence/factories.md",
        "renamed",
        "dated survey evidence of the pre-rename state",
    ),
    (
        "evidence/rework.md",
        "`meta-layer`",
        "the rework log records defects that WERE vocabulary drift; the banned "
        "term appears backticked as the quoted term of art, and rewriting it "
        "would delete the evidence that the defect happened.",
    ),
]


def parse_banned(ontology: Path) -> list[tuple[str, str]]:
    """Return [(banned_word, canonical_term)] from the Banned synonyms table."""
    text = ontology.read_text(encoding="utf-8")
    match = re.search(
        r"^## Banned synonyms\s*$(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        sys.exit("ONTOLOGY.md has no '## Banned synonyms' section — cannot gate")

    rows: list[tuple[str, str]] = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        dont_say, say = cells[0], cells[1]
        if dont_say.startswith("---") or dont_say.lower().startswith("don't say"):
            continue
        banned = dont_say.strip("`").strip()
        canonical = say.strip("`").strip()
        if banned and canonical:
            rows.append((banned, canonical))

    if not rows:
        sys.exit("parsed zero banned terms — the table shape changed")
    return rows


def parse_terms(ontology: Path) -> list[str]:
    """Return the canonical terms, counted by SECTION, not by row shape.

    Three tables in ONTOLOGY.md begin a row with a backticked term — the terms,
    the objects, and the banned synonyms — so a pattern over the whole file
    counts seven rows that are not terms as terms. A count without its predicate
    cannot be checked, and this one was published 7 too high before it was.
    """
    text = ontology.read_text(encoding="utf-8")
    match = re.search(
        r"^## Canonical terms\s*$(.*?)(?=^## |^### )",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        sys.exit("ONTOLOGY.md has no '## Canonical terms' section — cannot count")

    terms: list[str] = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        first = cells[0].strip("`").strip()
        if not first or first.startswith("---") or first.lower() == "term":
            continue
        terms.append(first)

    if not terms:
        sys.exit("parsed zero canonical terms — the table shape changed")
    return terms


def tracked_files() -> list[Path]:
    """Files to scan: git-tracked plus untracked-not-ignored, else a walk.

    `--cached --others --exclude-standard` matters: plain `ls-files` sees only
    tracked files, so a brand-new file carrying drift would pass the gate right
    up until the commit that lands it — which is the moment it is too late to
    be useful.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return [REPO / p for p in out.splitlines() if p.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [
            p
            for p in REPO.rglob("*")
            if p.is_file() and not any(part in SKIP_DIRS for part in p.parts)
        ]


def is_exempt(rel: str, line: str) -> bool:
    return any(
        rel == path and substring in line for path, substring, _ in EXEMPTIONS
    )


def main() -> int:
    banned = parse_banned(ONTOLOGY)
    terms = parse_terms(ONTOLOGY)
    patterns = [
        (
            re.compile(
                rf"(?<![A-Za-z0-9_-]){re.escape(word)}(?![A-Za-z0-9_-])", re.I
            ),
            word,
            canonical,
        )
        for word, canonical in sorted(banned, key=lambda p: -len(p[0]))
    ]

    findings: list[str] = []
    scanned = 0
    for path in tracked_files():
        if path.suffix not in SCAN_SUFFIXES or not path.is_file():
            continue
        if path.resolve() == ONTOLOGY.resolve():
            continue
        scanned += 1
        rel = str(path.relative_to(REPO))
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            for pattern, word, canonical in patterns:
                if pattern.search(line) and not is_exempt(rel, line):
                    findings.append(f"{rel}:{n}: '{word}' -> use '{canonical}'")

    if findings:
        print(f"vocabulary drift: {len(findings)} hit(s)\n")
        for f in findings:
            print(f"  {f}")
        print(
            "\nFix the prose, or add a justified exemption to "
            "tests/test_ontology.py EXEMPTIONS."
        )
        return 1

    print(
        f"vocabulary clean: {len(terms)} canonical term(s), "
        f"{len(banned)} banned term(s), {scanned} file(s) scanned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
