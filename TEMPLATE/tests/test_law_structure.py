#!/usr/bin/env python3
"""Law structure gate: numbered sections in a law file must be contiguous.

A law file (`skills/<name>/SKILL.md`, or the template's `SKILL.md.tmpl`) numbers its
sections so that prose can reference them — "see §7", "per §11". That reference scheme
breaks silently:

- a **duplicate** number means two sections claim the same slot, or a heading was
  clobbered by an edit that anchored on the wrong line;
- a **gap** means a section was deleted or lost, and every later reference now points
  at the wrong section.

Neither defect is visible to a reader. The file still renders, the table of contents
still looks plausible, and the cross-references quietly resolve to the wrong text.

Origin: a `hashline_edit` replace anchored on a hash read from an earlier read of a
different region replaced the `## 10. Add-ons in force` heading, leaving the meta-factory
law file with two `## 12` sections and no section 10. Nothing caught it — the file parsed,
rendered, and passed every existing gate. The defect was found by reading a diff.

The numbering may start at 0 or 1: this factory starts at 0, the template's law starts
at 1. What is asserted is the property, not the convention — each number exactly one
greater than the one before it, in file order.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SECTION_RE = re.compile(r"^##\s+(\d+)\.", re.MULTILINE)


def law_files() -> list[Path]:
    """Every law file in this repo: factory laws, plus the template's law."""
    found = sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))
    template_law = REPO_ROOT / "TEMPLATE" / "SKILL.md.tmpl"
    if template_law.is_file():
        found.append(template_law)
    return found


def section_numbers(text: str) -> list[int]:
    return [int(m) for m in SECTION_RE.findall(text)]


def is_contiguous(numbers: list[int]) -> bool:
    if not numbers:
        return False
    return all(b - a == 1 for a, b in zip(numbers, numbers[1:]))


def check() -> list[str]:
    problems: list[str] = []

    files = law_files()
    if not files:
        problems.append(
            "no law file found — expected skills/*/SKILL.md or TEMPLATE/SKILL.md.tmpl"
        )
        return problems

    for law_file in files:
        rel = law_file.relative_to(REPO_ROOT)
        numbers = section_numbers(law_file.read_text(encoding="utf-8"))

        if not numbers:
            problems.append(f"{rel}: no numbered sections found")
            continue

        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if duplicates:
            problems.append(f"{rel}: duplicate section number(s) {duplicates} in {numbers}")
            continue

        if not is_contiguous(numbers):
            gaps = [b for a, b in zip(numbers, numbers[1:]) if b - a != 1]
            problems.append(
                f"{rel}: section numbers are not contiguous — {numbers}; "
                f"breaks at {gaps}"
            )

    return problems


def main() -> int:
    problems = check()
    if problems:
        print("law structure problems:\n")
        for p in problems:
            print(f"  {p}")
        print("\nA duplicate means a heading was clobbered or two sections claim one slot;")
        print("a gap means a section was lost. Fix the numbering before committing.")
        return 1

    checked = ", ".join(str(f.relative_to(REPO_ROOT)) for f in law_files())
    print(f"law structure clean: contiguous numbered sections in {checked}")
    return 0


def test_law_sections_are_numbered_contiguously() -> None:
    problems = check()
    assert not problems, "law files with broken section numbering: " + "; ".join(problems)


if __name__ == "__main__":
    raise SystemExit(main())
