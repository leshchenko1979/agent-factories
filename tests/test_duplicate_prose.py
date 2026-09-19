#!/usr/bin/env python3
"""Gate: a law file must not state the same prose claim twice.

Origin: #73. Two live instances of the class were found in shipped law, and
NO gate read prose structure — `tests/test_law_structure.py` reads heading
numbers, never the text, and the profile and template copies are not paired
because they differ by design. So `tools/audit.py` sat at rc=0 HEALTHY with
the duplication in place.

The two instances are DIFFERENT SHAPES, and that is the whole design:

  instance 1 — two CONSECUTIVE identical lines (the template State opening,
               fixed at d7bcd54).
  instance 2 — an identical 2-line PARAGRAPH BLOCK separated by a blank line
               (the profile section 6 closing paragraph).

A line-granular detector misses instance 2: an adjacent identical non-empty
line scan over that file returns NONE. A block-only detector misses instance 1
just as badly, and for a reason that is not obvious — two consecutive identical
lines are not two blocks, they are ONE block whose text repeats inside itself,
so the block is unique and never reports. Both arms are therefore required, and
each is probed against the shape it exists for. A detector carrying only one of
them is half a gate that passes.

Scope is deliberately narrow so legitimate repetition cannot fire it: table
rows, headings, list items, blockquotes, fenced-code content and separator-only
lines are excluded, and a normalised block shorter than the floor is ignored.
The floor and the exclusions are what keep the predicate calibrated against the
live tree rather than argued down on its first run.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The law surfaces. Globs, not fixed paths: a bootstrapped factory carries
# `skills/<name>/SKILL.md` and the role cards but may carry no TEMPLATE/ at
# all, and a missing surface must yield no hits rather than an error.
SURFACE_GLOBS = (
    "skills/*/SKILL.md",
    "TEMPLATE/SKILL.md.tmpl",
    "TEMPLATE/roles/*.md",
    # The template's own layout, so the gate is correct from either root. In
    # this repo these add nothing — root carries no `roles/` and no
    # `SKILL.md.tmpl`, and `TEMPLATE/skills/` does not exist — but in a
    # bootstrapped factory the gate is run from the tree it shipped into, and
    # there the law surfaces sit at the root. Without these it would scan
    # nothing and pass, which is the vacuous green this whole issue is about.
    "roles/*.md",
    "SKILL.md.tmpl",
    "TEMPLATE/skills/*/SKILL.md",
)

# Measured starting point: at this floor the predicate returns exactly one hit
# over the six surfaces at HEAD af8984c — the section 6 duplicate — and zero
# false positives. Lowering it would admit short structural prose; raising it
# would let a genuine duplicate hide behind brevity.
MIN_CHARS = 60

_FENCE = re.compile(r"^\s*(```|~~~)")
_ORDERED_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
_SEPARATOR_ONLY = re.compile(r"^[-*_=|\s]+$")
_EXCLUDED_PREFIX = ("|", "#", ">", "```", "~~~")


def law_surfaces(repo: Path = REPO) -> list[Path]:
    """Every law surface present in the tree, sorted, de-duplicated."""
    found: list[Path] = []
    for pattern in SURFACE_GLOBS:
        found.extend(sorted(repo.glob(pattern)))
    seen: list[Path] = []
    for path in found:
        if path not in seen:
            seen.append(path)
    return seen


def paragraph_blocks(text: str) -> list[tuple[int, list[tuple[int, str]]]]:
    """(first line number, [(line number, whitespace-normalised line), ...]).

    A block is a run of consecutive non-blank prose lines. An excluded line
    ENDS the run rather than joining it, so a table or a bullet list interrupts
    prose instead of being folded into it. Fenced code is skipped entirely.
    """
    blocks: list[tuple[int, list[tuple[int, str]]]] = []
    buffer: list[tuple[int, str]] = []
    start = 0
    in_fence = False

    def flush() -> None:
        nonlocal buffer
        if buffer:
            blocks.append((start, buffer))
            buffer = []

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if _FENCE.match(raw):
            in_fence = not in_fence
            flush()
            continue
        if in_fence:
            continue
        if not line:
            flush()
            continue
        if line.startswith(_EXCLUDED_PREFIX) or _SEPARATOR_ONLY.match(line) or _ORDERED_ITEM.match(line):
            flush()
            continue
        if not buffer:
            start = number
        buffer.append((number, " ".join(line.split())))
    flush()
    return blocks


def duplicate_blocks(text: str, min_chars: int = MIN_CHARS) -> list[tuple[str, str, list[int]]]:
    """Repeated prose, as (shape, block text, line numbers).

    Two arms, because the class took two shapes and neither arm covers the
    other. `repeat` is the same block appearing at two or more starts;
    `inline` is a line repeating immediately inside one block. Within a single
    file only — the profile law and the template law differ by design, one
    condensed and one full, so comparing them would report the template's whole
    purpose as a defect.
    """
    found: list[tuple[str, str, list[int]]] = []
    starts: dict[str, list[int]] = {}
    for start, lines in paragraph_blocks(text):
        block = " ".join(part for _n, part in lines)
        if len(block) >= min_chars:
            starts.setdefault(block, []).append(start)
        for (n1, t1), (n2, t2) in zip(lines, lines[1:]):
            if t1 == t2 and len(t1) >= min_chars:
                found.append(("inline", t1, [n1, n2]))
    for block, where in starts.items():
        if len(where) > 1:
            found.append(("repeat", block, where))
    return sorted(found, key=lambda item: item[2][0])


def duplicate_prose_problems(repo: Path = REPO, min_chars: int = MIN_CHARS) -> tuple[list[str], int, int]:
    """(problems, surfaces scanned, blocks examined) over the law surfaces."""
    problems: list[str] = []
    surfaces = 0
    examined = 0
    for path in law_surfaces(repo):
        surfaces += 1
        text = path.read_text(encoding="utf-8")
        examined += sum(1 for _n, lines in paragraph_blocks(text)
                        if len(" ".join(part for _i, part in lines)) >= min_chars)
        for shape, block, numbers in duplicate_blocks(text, min_chars):
            where = ", ".join(f"line {n}" for n in numbers)
            preview = block[:64] + ("..." if len(block) > 64 else "")
            problems.append(f"{path.relative_to(repo)}: {shape} at {where} — {preview}")
    return problems, surfaces, examined


def probe(name: str, text: str, want: bool, failures: list[str], repo: Path | None = None) -> None:
    """Run the predicate against a document or a tree and assert the verdict."""
    found = bool(duplicate_prose_problems(repo)[0]) if repo is not None else bool(duplicate_blocks(text))
    ok = found == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name} — {'reported' if found else 'reported nothing'}")
    if not ok:
        failures.append(name)


def run_probes() -> list[str]:
    failures: list[str] = []
    long_a = "The law states a claim about the factory and its process that is long enough to count."
    other = "A different claim, worded differently, so it cannot be confused with the first one."

    # One probe per shape. The inline arm exists because the repeat arm cannot
    # see instance 1 at all: consecutive identical lines form a single unique
    # block, so dropping either arm leaves half the class uncovered.
    probe("instance 1 shape — consecutive identical lines — is caught", f"{long_a}\n{long_a}\n", True, failures)
    probe("instance 2 shape — a repeated paragraph block — is caught", f"{long_a}\n\n{long_a}\n", True, failures)
    probe("the inline arm catches what the repeat arm cannot",
          f"{long_a}\n{long_a}\n", "inline" in [s for s, _b, _n in duplicate_blocks(f"{long_a}\n{long_a}\n")], failures)

    # Whitespace must not be able to hide a duplicate from the gate.
    probe("a block differing only in whitespace is still a duplicate",
          f"{long_a}\n\n" + long_a.replace(" and ", "\nand ", 1) + "\n", True, failures)

    # Legitimate repetition must not fire it.
    probe("two different paragraphs are not a duplicate", f"{long_a}\n\n{other}\n", False, failures)
    probe("a single occurrence is not a duplicate", f"{long_a}\n", False, failures)
    probe("a short block is below the floor and ignored", "Same.\n\nSame.\n", False, failures)
    probe("a repeated table row is excluded", f"| a | b |\n\n| a | b |\n\n{long_a}\n", False, failures)
    probe("a repeated heading is excluded", f"# A heading\n\n# A heading\n\n{long_a}\n", False, failures)
    probe("a repeated list item is excluded", f"- {long_a}\n\n- {long_a}\n", False, failures)
    probe("a repeated blockquote is excluded", f"> {long_a}\n\n> {long_a}\n", False, failures)
    probe("a repeated fenced-code body is excluded", f"```\n{long_a}\n```\n\n```\n{long_a}\n```\n", False, failures)
    probe("separator-only lines are excluded", f"---\n\n---\n\n{long_a}\n", False, failures)
    probe("prose either side of a table is two blocks, not one", f"{long_a}\n| a | b |\n{long_a}\n", True, failures)

    # And the tree itself, which is the verdict that actually matters.
    probe("the live tree carries no duplicated prose", "", False, failures, repo=REPO)
    return failures


def main() -> int:
    problems, surfaces, examined = duplicate_prose_problems()
    failures = run_probes()
    if failures:
        print(f"duplicate-prose gate: {len(failures)} probe(s) failed: {', '.join(failures)}")
        return 1
    for problem in problems:
        print(f"duplicate prose: {problem}")
    if problems:
        print(f"duplicate-prose gate: {len(problems)} duplicated block(s) over {surfaces} law surface(s)")
        return 1
    print(f"duplicate-prose gate ok: {surfaces} law surface(s), {examined} prose block(s), no duplicates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
