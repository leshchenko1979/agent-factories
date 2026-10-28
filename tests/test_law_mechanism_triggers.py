#!/usr/bin/env python3
r"""Gate: every containment source the re-derivation tool declares is named in its law.

Origin (board #576, filed by the Surveys lane, intake n=4413). `docs/measurement-procedure.md`
docs/measurement-procedure.md §5.2 said a basis is re-derived "when, and only when" and then listed exactly THREE triggers,
while `tools/gate_budget_rederive.py` applies FOUR. A lane auditing its work against the
procedure was therefore right to refuse a growth-applied basis, and could not audit either of
the two rules that existed only in the tool's docstring - the precedence order and the
report-first streak rule.

WHY NO GATE SAW IT, and why the obvious home could not hold it. `tests/test_shipped_mechanism_law.py`
is this factory's law-vs-mechanism pairing gate and it is the right instrument, but it resolves
its mechanism under `TEMPLATE/` (`repo / "TEMPLATE" / mechanism`), and
`TEMPLATE/tools/gate_budget_rederive.py` does not exist - the tool ships in the live tree only.
No entry in `docs/shipped-mechanism-law.json` can name it without reading NAMED ABSENT, so the
whole class of LIVE-ONLY tools with a documented procedure sits outside that gate's reach.
`tests/test_law_conversion_join.py` reads the same procedure but its two legs are pure over law
TEXT and never open a tool.

THE PREDICATE. The source set is DERIVED from the mechanism, never declared here:

  1. DECLARED SET - the `Population` class docstring names its sources in one paragraph
     ("The three sources are a PARTITION ... `stale` ... `exhausted` ... `growth`"). The
     backticked tokens of that paragraph ARE the set. A list hardcoded in this gate would be
     the gate's own memory and would pass a fifth source in silence, which is the failure
     #576 is an instance of.
  2. THE NUMERAL MUST AGREE - the word before "sources are a PARTITION" is a count, and it is
     asserted against the set's size. #576 was a count mismatch in prose; a gate that only
     read the token list would let the count drift on its own.
  3. THE LAW MUST NAME EACH ONE - inside docs/measurement-procedure.md §5.2's own bounds, never the whole file, so a token
     appearing in docs/measurement-procedure.md §5.1 cannot satisfy a §5.2 obligation.

A subject the gate cannot FIND is a failure, never a pass: an absent section, an unreadable
tool, or a reworded declaration paragraph all red with the reason stated.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "gate_budget_rederive.py"
LAW = REPO / "docs" / "measurement-procedure.md"

SECTION_OPEN = re.compile(r"^###\s+5\.2\b", re.MULTILINE)
SECTION_CLOSE = re.compile(r"^#{2,4}\s+5\.3\b", re.MULTILINE)
ANCHOR = "sources are a PARTITION"
NUMERALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def declared_sources(tool_text: str) -> tuple[list[str], list[str]]:
    """Return (sources, problems) derived from the tool's own declaration."""
    try:
        tree = ast.parse(tool_text)
    except SyntaxError as exc:
        return [], [f"{TOOL.name} could not be parsed: {exc} - the source set is unreadable"]

    body = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Population":
            body = ast.get_docstring(node) or ""
            break
    if body is None:
        return [], [f"{TOOL.name} declares no `Population` class - the source set cannot be derived"]

    paragraph = next((p for p in body.split("\n\n") if ANCHOR in p), None)
    if paragraph is None:
        return [], [
            f"`Population`'s docstring carries no paragraph stating that its {ANCHOR!r} - "
            f"the declaration this gate joins to the law is absent, and an unstated "
            f"partition is not a partition with no sources"
        ]

    sources = re.findall(r"`([a-z_]+)`", paragraph)
    if not sources:
        return [], [f"the paragraph naming the partition declares NO backticked source - nothing to join"]

    problems: list[str] = []
    match = re.search(r"\b(" + "|".join(NUMERALS) + r")\s+sources\b", paragraph, re.IGNORECASE)
    if match is None:
        problems.append(
            f"the partition paragraph states no count word before 'sources' - the size claim "
            f"cannot be checked against the {len(sources)} declared source(s)"
        )
    else:
        word = match.group(1).lower()
        if NUMERALS[word] != len(sources):
            problems.append(
                f"the partition paragraph says {word!r} ({NUMERALS[word]}) but declares "
                f"{len(sources)} source(s): {', '.join(sources)} - the count and the list disagree"
            )
    return sources, problems


def law_section(law_text: str) -> tuple[str | None, str | None]:
    """Return (section body, problem) for docs/measurement-procedure.md §5.2, bounded rather than whole-file."""
    opening = SECTION_OPEN.search(law_text)
    if opening is None:
        return None, "the law carries no docs/measurement-procedure.md §5.2 heading - the section this gate reads is absent"
    closing = SECTION_CLOSE.search(law_text, opening.end())
    body = law_text[opening.end(): closing.start() if closing else len(law_text)]
    if not body.strip():
        return None, "docs/measurement-procedure.md §5.2 is EMPTY - every source would read as unnamed"
    return body, None


def evaluate(tool_text: str, law_text: str) -> tuple[list[str], dict]:
    """Return (problems, population). Each problem NAMES its subject."""
    population = {"sources": [], "named": 0, "unnamed": 0, "section_chars": 0}
    sources, problems = declared_sources(tool_text)
    population["sources"] = sources
    if problems:
        return problems, population

    body, problem = law_section(law_text)
    if problem:
        return [problem], population
    population["section_chars"] = len(body)

    for source in sources:
        if re.search(rf"\b{re.escape(source)}\b", body, re.IGNORECASE):
            population["named"] += 1
        else:
            population["unnamed"] += 1
            problems.append(
                f"the law's docs/measurement-procedure.md §5.2 does NOT name the containment source {source!r}, which "
                f"{TOOL.name} applies - a lane auditing its work against the procedure "
                f"cannot know the source exists, and is right to refuse a basis it produced"
            )
    return problems, population


PROBE_COUNT = 7  # P1..P7, asserted below so the constant cannot drift from the arms

def run_self_probes() -> list[str]:
    """Every arm driven from a synthetic fixture, never from prose that happens to be present."""
    failed: list[str] = []
    ran = [0]

    def check(name: str, ok: bool, detail: str = "") -> None:
        ran[0] += 1
        if not ok:
            failed.append(f"{name}{(' - ' + detail) if detail else ''}")

    def tool(count_word: str, names: str) -> str:
        return (
            "class Population:\n"
            f'    """The containment population.\n\n'
            f"    The {count_word} sources are a PARTITION: {names} claim distinct entries.\n"
            f'    """\n'
            "    stale: tuple = ()\n"
        )

    def law(body: str) -> str:
        return f"## 5.1 previous\n\n### 5.2 The leg\n\n{body}\n\n### 5.3 next\n\nunrelated\n"

    three = tool("three", "`stale` and `exhausted`, and `growth`")

    # P1 - the population is COUNTED, so a clean verdict is distinguishable from an empty one.
    problems, population = evaluate(three, law("stale, exhausted and growth all apply."))
    check(
        "P1 a law naming every source passes and is counted",
        not problems and population["named"] == 3 and population["unnamed"] == 0,
        f"problems={problems} population={population}",
    )

    # P2 - THE BITE: the exact #576 shape - growth applied, growth absent from the law.
    problems, _ = evaluate(three, law("stale and exhausted re-derive the basis."))
    check(
        "P2 a source the law omits reds and NAMES it",
        len(problems) == 1 and "'growth'" in problems[0],
        f"problems={problems}",
    )

    # P3 - a FIFTH source added to the tool with the law unchanged must red without the gate
    # being edited: this is the arm a hardcoded list could never carry.
    four = tool("four", "`stale`, `exhausted`, `growth`, and `superseded`")
    problems, population = evaluate(four, law("stale, exhausted and growth all apply."))
    check(
        "P3 a NEWLY DECLARED source reds on the law alone",
        population["sources"] == ["stale", "exhausted", "growth", "superseded"]
        and len(problems) == 1 and "'superseded'" in problems[0],
        f"problems={problems} population={population}",
    )

    # P4 - the count word and the list disagree.
    problems, _ = evaluate(tool("three", "`stale` and `exhausted`"), law("stale and exhausted."))
    check(
        "P4 a count that disagrees with its own list reds",
        any("says 'three'" in p and "declares 2 source(s)" in p for p in problems),
        f"problems={problems}",
    )

    # P5 - SECTION BOUNDS: the token in docs/measurement-procedure.md §5.1 must not satisfy a §5.2 obligation.
    leaky = "## 5.1 previous\n\ngrowth\n\n### 5.2 The leg\n\nstale and exhausted.\n\n### 5.3 next\n"
    problems, _ = evaluate(three, leaky)
    check(
        "P5 a source named only OUTSIDE docs/measurement-procedure.md §5.2 still reds",
        len(problems) == 1 and "'growth'" in problems[0],
        f"problems={problems}",
    )

    # P6 - an absent section is a failure, never a pass.
    problems, _ = evaluate(three, "## 5.1 only\n\nstale exhausted growth\n")
    check(
        "P6 an absent docs/measurement-procedure.md §5.2 reds",
        len(problems) == 1 and "no docs/measurement-procedure.md §5.2 heading" in problems[0],
        f"problems={problems}",
    )

    # P7 - a reworded declaration paragraph cannot pass silently.
    problems, _ = evaluate(
        "class Population:\n    \"\"\"Population.\n\n    Sources exist.\n    \"\"\"\n",
        law("stale, exhausted and growth."),
    )
    check(
        "P7 an unstated partition reds rather than passing on an empty set",
        len(problems) == 1 and "no paragraph stating" in problems[0],
        f"problems={problems}",
    )

    if ran[0] != PROBE_COUNT:
        failed.append(
            f"the gate DECLARES {PROBE_COUNT} arm(s) but {ran[0]} actually ran - the count "
            f"is a claim about the arms and must move with them"
        )
    return failed


def main() -> int:
    failed = run_self_probes()

    if not TOOL.is_file():
        print(f"  FAIL - the mechanism {TOOL} is absent from this tree")
        return 1
    if not LAW.is_file():
        print(f"  FAIL - the law {LAW} is absent from this tree")
        return 1

    problems, population = evaluate(
        TOOL.read_text(encoding="utf-8"), LAW.read_text(encoding="utf-8")
    )
    print(
        f"  population: {len(population['sources'])} declared source(s) "
        f"({', '.join(population['sources']) or 'none'}) judged against docs/measurement-procedure.md §5.2 "
        f"({population['section_chars']} chars) - {population['named']} named, "
        f"{population['unnamed']} unnamed"
    )
    for problem in problems:
        print(f"  UNNAMED  {problem}")

    if failed or problems:
        print(
            f"law-mechanism-triggers gate FAILED: {len(failed)} probe failure(s), "
            f"{len(problems)} source problem(s)"
        )
        for failure in failed:
            print(f"  PROBE  {failure}")
        return 1
    print(
        f"  self-probes: {PROBE_COUNT} arm(s) ran, 0 failed - a clean verdict is "
        f"distinguishable from an empty run"
    )
    print(
        "law-mechanism-triggers gate ok: every containment source the tool declares is "
        "named inside the law's own docs/measurement-procedure.md §5.2"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
