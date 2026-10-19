#!/usr/bin/env python3
"""Gate: the repo prose uses no banned synonym from ONTOLOGY.md.

Parses the banned-synonyms table out of ONTOLOGY.md and fails when the repo's
own prose uses a banned word. The table is the source of truth, so the ban list
and the gate cannot drift apart: add a row to ONTOLOGY.md and the next run
enforces it.

THE SUBJECT, AND WHY IT HAS A DECLARED CLASS (#512). The gate judges the
factory's LIVING vocabulary. Two kinds of line are outside that subject rather
than forgiven by it, and both are declared as FACTORY DATA in
`docs/ontology-exemptions.json` -- never inline here, because this file is a
declared byte pair with its TEMPLATE twin and a factory's own paths must not
live in a file that ships to every new factory:

  * `dated_artifacts` -- directory roots holding DATED RECORDS (a measurement
    run's evidence, a review cycle's reports). A dated record states what was
    said at the time; rewriting it to satisfy a vocabulary gate would falsify
    the record. Correcting a population is a MECHANISM, so a class never needs
    a second exemption row. Every file excluded this way is PRINTED with its hit
    count on every run, so the class is visible and never silently empty.
  * `exemptions` -- a single line whose banned word is the historical mention
    itself, justified at the point of use by a `substring`, a `reason` and a
    `proof` a reader can check. An entry must match at least one live hit: an
    exemption that excuses nothing is an ERROR rather than a leftover, so the
    store can never rot into a standing waiver list.

Absent or empty declaration means no class and no exemptions -- the shipped
state of a new factory. A malformed or unreadable declaration is an ERROR,
never a silent pass.

Run:  python3 tests/test_ontology.py
Exit: 0 clean, 1 drift found or the declaration is broken.

Why a gate and not a review checklist: the rubric's Vocabulary conformance
criterion (L2) counts an ontology that a test enforces as law, and one nobody
can violate as documentation. This is the difference.
"""

from __future__ import annotations

import json
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
# A document shipped in both trees is one document -- see `mirrored`.
TEMPLATE_PREFIX = "TEMPLATE/"

# The declared class and exemption surface (#512). FACTORY DATA, read here and
# never listed inline: the gate is a declared byte pair with its TEMPLATE twin,
# so a factory's own paths must not live in a file that ships to every factory.
EXEMPTIONS_PATH = "docs/ontology-exemptions.json"
DATED_KEY = "dated_artifacts"
EXEMPT_KEY = "exemptions"
# Every field is REQUIRED: a path and a substring without a reason and a proof
# is forgiveness, not a declaration -- nobody can check it.
ENTRY_FIELDS = ("path", "substring", "reason", "proof")


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


def mirrored(rel: str) -> str:
    """A file shipped in BOTH trees is one document.

    `TEMPLATE/docs/best-practices.md` is the copy of `docs/best-practices.md`,
    and `tests/test_docs_sync.py` already requires the two to be byte-identical.
    So a justification that holds for one holds for the other, and keying the
    declaration on the exact path would force a duplicate entry per mirrored
    path — a duplicate that can drift from its pair while both read as
    justified. The `TEMPLATE/` prefix is therefore stripped before BOTH lookups
    (the exemption match and the dated class), which covers every current and
    future mirror without weakening either: an exemption still needs its own
    file, its own substring, its own reason and its own proof.
    """
    if rel.startswith(TEMPLATE_PREFIX):
        return rel[len(TEMPLATE_PREFIX) :]
    return rel


def load_declaration(repo: Path) -> tuple[list[str], list[dict], list[str]]:
    """`(dated_roots, entries, problems)` read from the factory's own data file.

    Absent or empty data means NO class and NO exemptions -- the shipped state of
    a new factory, where `docs/` carries only the `.example.json` skeleton.
    Anything malformed is a problem, never a silent pass: a declaration that
    quietly fails to load is indistinguishable from no declaration at all, which
    is the vacuous-pass shape this gate exists to forbid.

    The stale check (an entry that matches no live hit) is not made here but in
    `main`, where the population is known: an entry that excuses nothing is an
    ERROR, and that is what keeps the store from becoming a standing waiver
    list -- it can only ever hold lines that are actually red.
    """
    problems: list[str] = []
    path = repo / EXEMPTIONS_PATH
    if not path.is_file():
        return [], [], problems
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], [], [f"{EXEMPTIONS_PATH} is not readable JSON: {exc}"]
    if not isinstance(data, dict):
        return [], [], [
            f"{EXEMPTIONS_PATH}: expected a JSON object with `{DATED_KEY}` and `{EXEMPT_KEY}`"
        ]

    raw_dated = data.get(DATED_KEY, [])
    if not isinstance(raw_dated, list):
        problems.append(f"{EXEMPTIONS_PATH}: `{DATED_KEY}` must be a list of directory roots")
        raw_dated = []
    dated: list[str] = []
    for i, root in enumerate(raw_dated, 1):
        if not isinstance(root, str) or not root.strip():
            problems.append(
                f"{EXEMPTIONS_PATH}: `{DATED_KEY}` entry {i} is not a non-empty string: {root!r}"
            )
            continue
        norm = root.strip().replace("\\", "/")
        while norm.startswith("./"):
            norm = norm[2:]
        if not norm.endswith("/"):
            norm += "/"
        if norm.startswith("/") or ".." in norm.split("/"):
            problems.append(
                f"{EXEMPTIONS_PATH}: `{DATED_KEY}` entry {i} ({root!r}) is not a path "
                f"inside this tree — a root that escapes the tree can never name a record"
            )
            continue
        if not (repo / norm).is_dir():
            problems.append(
                f"{EXEMPTIONS_PATH}: `{DATED_KEY}` entry {i} ({root!r}) is not an existing "
                f"directory in this tree — a class whose root is absent excludes nothing "
                f"and must not pass silently"
            )
            continue
        if norm in dated:
            problems.append(f"{EXEMPTIONS_PATH}: `{DATED_KEY}` entry {i} repeats {norm!r}")
            continue
        dated.append(norm)

    raw_entries = data.get(EXEMPT_KEY, [])
    if not isinstance(raw_entries, list):
        problems.append(f"{EXEMPTIONS_PATH}: `{EXEMPT_KEY}` must be a list of objects")
        raw_entries = []
    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for i, item in enumerate(raw_entries, 1):
        if not isinstance(item, dict):
            problems.append(f"{EXEMPTIONS_PATH}: `{EXEMPT_KEY}` entry {i} is not an object")
            continue
        fields: dict[str, str] = {}
        missing = False
        for field in ENTRY_FIELDS:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(
                    f"{EXEMPTIONS_PATH}: `{EXEMPT_KEY}` entry {i} carries no {field} — an "
                    f"exemption nobody can check is forgiveness, not a declaration"
                )
                missing = True
            else:
                fields[field] = value.strip()
        if missing:
            continue
        key = (fields["path"], fields["substring"])
        if key in seen:
            problems.append(
                f"{EXEMPTIONS_PATH}: `{EXEMPT_KEY}` entry {i} repeats path "
                f"{key[0]!r} + substring {key[1]!r}"
            )
            continue
        seen.add(key)
        entries.append(fields)
    return dated, entries, problems


def main() -> int:
# STATED SKIP: ONTOLOGY.md (BOOTSTRAP-created, step 3)
    # THE SHIPPED TREE CARRIES `ONTOLOGY.md.tmpl`, NOT `ONTOLOGY.md` (#199). The ontology is
    # BOOTSTRAP-created (BOOTSTRAP.md step 3) because it is the factory's own vocabulary, so
    # the tree the kit ships has none — and this gate's entire subject is a table parsed out of
    # it. Without this arm the gate died with FileNotFoundError in the tree it ships from: a
    # CRASH, not a verdict. The reason is printed and names the artifact.
    if not ONTOLOGY.is_file():
        shipped = ONTOLOGY.with_suffix(".md.tmpl")
        print(
            f"ontology gate: SKIPPED — no {ONTOLOGY.name} in this tree, so there is no banned-"
            f"synonym table to judge against. It is BOOTSTRAP-created (BOOTSTRAP.md step 3)"
            + (f"; this tree carries the shipped {shipped.name} instead." if shipped.is_file() else ".")
        )
        return 0
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

    dated, entries, problems = load_declaration(REPO)

    findings: list[str] = []
    excused: list[str] = []
    dated_lines: list[str] = []
    matched: set[int] = set()
    dated_files = 0
    scanned = 0
    for path in tracked_files():
        if path.suffix not in SCAN_SUFFIXES or not path.is_file():
            continue
        if path.resolve() == ONTOLOGY.resolve():
            continue
        scanned += 1
        rel = str(path.relative_to(REPO))
        judged = mirrored(rel)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        hits = [
            (n, line, word, canonical)
            for n, line in enumerate(lines, 1)
            for pattern, word, canonical in patterns
            if pattern.search(line)
        ]
        if not hits:
            continue
        # A DATED RECORD is outside the gate's subject: printed with its count on
        # every run, never judged, never silently dropped.
        if any(judged.startswith(root) for root in dated):
            dated_lines.append(f"dated: {rel} ({len(hits)} hit(s) not judged)")
            dated_files += 1
            continue
        for n, line, word, canonical in hits:
            entry = next(
                (
                    i
                    for i, e in enumerate(entries)
                    if e["path"] == judged and e["substring"] in line
                ),
                None,
            )
            if entry is None:
                findings.append(f"{rel}:{n}: '{word}' -> use '{canonical}'")
            else:
                matched.add(entry)
                excused.append(f"excused: {rel}:{n} '{word}' — {entries[entry]['reason']}")

    for line in excused:
        print(line)
    for line in dated_lines:
        print(line)

    for i, entry in enumerate(entries):
        if i not in matched:
            problems.append(
                f"{EXEMPTIONS_PATH}: the exemption for {entry['path']} (substring "
                f"{entry['substring']!r}) matches 0 hit(s) — a stale exemption excuses "
                f"nothing; remove it or correct its path/substring"
            )

    if findings:
        print(f"vocabulary drift: {len(findings)} hit(s)\n")
        for f in findings:
            print(f"  {f}")
        print(
            "\nFix the prose, or — when the line is a dated record or a justified "
            "historical mention — declare it in "
            f"{EXEMPTIONS_PATH}: a dated record belongs under `{DATED_KEY}`, and a "
            f"single justified line is an `{EXEMPT_KEY}` entry carrying "
            + ", ".join(ENTRY_FIELDS)
            + "."
        )

    if problems:
        print(f"\nvocabulary gate: ERROR — {len(problems)} declaration problem(s)\n")
        for p in problems:
            print(f"  {p}")
        return 1
    if findings:
        return 1

    state = ""
    if excused and dated_files:
        state = f" ({len(excused)} excused, {dated_files} dated file(s) excluded)"
    elif excused:
        state = f" ({len(excused)} excused)"
    elif dated_files:
        state = f" ({dated_files} dated file(s) excluded)"
    print(
        f"vocabulary clean: {len(terms)} canonical term(s), "
        f"{len(banned)} banned term(s), {scanned} file(s) scanned{state}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
