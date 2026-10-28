#!/usr/bin/env python3
r"""Gate: every source partition a LIVE-ONLY tool declares is named in the law that owns it.

Origin (board #576, intake n=4413; generalised under #577, intake n=4423). The
`docs/measurement-procedure.md` §5.2 section of that law said a basis is re-derived "when, and
only when" and then listed exactly THREE triggers, while `tools/gate_budget_rederive.py` applies
FOUR. A lane auditing its work against the procedure was therefore right to refuse a
growth-applied basis, and could not audit either of the two rules that existed only in the
tool's docstring - the precedence order and the report-first streak rule.

WHY NO OTHER GATE SAW IT. `tests/test_shipped_mechanism_law.py` is this factory's
law-vs-mechanism pairing gate, but it resolves its mechanism under `TEMPLATE/`
(`repo / "TEMPLATE" / mechanism`), and `TEMPLATE/tools/gate_budget_rederive.py` does not exist -
the tool ships in the live tree only. No entry in `docs/shipped-mechanism-law.json` can name it
without reading NAMED ABSENT, so the whole class of LIVE-ONLY tools with a documented procedure
sits outside that gate's reach. `tests/test_law_conversion_join.py` reads the same procedure but
its legs are pure over law TEXT and never open a tool.

THE PREDICATE, per declared pair. The source set is DERIVED from the mechanism, never declared
here:

  1. DECLARED SET - the mechanism's own docstring carries one paragraph stating a PARTITION and
     naming its sources in backticks. The backticked tokens of that paragraph ARE the set. A list
     hardcoded in this gate would be the gate's own memory and would pass a fifth source in
     silence, which is the failure #576 is an instance of.
  2. THE NUMERAL MUST AGREE - the word before "a PARTITION" is a count, and it is asserted
     against the set's size. #576 was a count mismatch in prose; a gate that only read the token
     list would let the count drift on its own.
  3. THE LAW MUST NAME EACH ONE - inside the declared section's own bounds, never the whole
     file, so a token appearing in the `docs/measurement-procedure.md` §5.1 section cannot
     satisfy an obligation of its `docs/measurement-procedure.md` §5.2 section.

THE POPULATION (#577, and the reason this gate is not one hardcoded pair). Which DOCUMENT owns a
mechanism cannot be derived from code - that is a declaration - so the pairs live in PAIRS below.
The POPULATION is derived instead: every tool under `tools/` that ships NO `TEMPLATE` twin and
declares a source partition must be named in PAIRS, and every PAIRS entry must still declare one.
Measured 2026-10-28 at intake: 11 live-only tools, exactly ONE of them declaring a partition, so
a name-grep over `docs/` would have been noise (9 of the 11 are mentioned somewhere in `docs/`,
mostly incidentally) while the declaration itself is mechanical. A second live-only mechanism
that declares a partition now REDS this gate until its law pair is declared, instead of sitting
silently outside every law join - which is what #576 did for as long as it existed.

DIRECTION 2 IS DECLARED, NOT FAKED. The inverse defect - the law asserting a mechanism no tool
implements - is NOT mechanically derivable here: the law enumerates its triggers in bolded prose
rather than a token list, so an arm claiming to read it would pass on its own blindness. It
remains a REVIEW obligation, and the declaration it would need is a law-side enumeration nobody
has written yet. Saying so is cheaper than a leg that cannot see the thing it names.

A subject the gate cannot FIND is a failure, never a pass: an absent section, an unreadable tool,
an undeclared mechanism or a reworded declaration paragraph all red with the reason stated.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ANCHOR = "PARTITION"
NUMERALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# WHICH LAW OWNS WHICH LIVE-ONLY MECHANISM. A declaration, not a derivation: the code says what
# the sources ARE, never which document promises them. The population leg below keeps this table
# honest in both directions - an undeclared partition-declaring tool reds, and so does an entry
# whose tool has stopped declaring one.
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("tools/gate_budget_rederive.py", "docs/measurement-procedure.md", "5.2"),
)


def partition_declaration(tool_text: str, name: str) -> tuple[list[str] | None, list[str]]:
    """Return (sources, problems). `sources` is None when the tool declares NO partition at all."""
    try:
        tree = ast.parse(tool_text)
    except SyntaxError as exc:
        return None, [f"{name} could not be parsed: {exc} - its declaration is unreadable"]

    body = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ""
            if ANCHOR in doc:
                body = doc
                break
    if body is None:
        return None, []

    paragraph = next((p for p in body.split("\n\n") if ANCHOR in p), None)
    if paragraph is None:
        return None, [
            f"{name} states a {ANCHOR!r} in prose but no single paragraph carries it - the "
            f"declaration this gate joins to the law cannot be isolated, and an unstated "
            f"partition is not a partition with no sources"
        ]

    sources = re.findall(r"`([a-z_]+)`", paragraph)
    if not sources:
        return [], [
            f"{name}'s partition paragraph declares NO backticked source - nothing to join"
        ]

    problems: list[str] = []
    match = re.search(
        r"\b(" + "|".join(NUMERALS) + r")\s+\w+\s+(?:are|is)\s+a\s+" + ANCHOR,
        paragraph,
        re.IGNORECASE,
    )
    if match is None:
        problems.append(
            f"{name}'s partition paragraph states no count word before 'a {ANCHOR}' - the size "
            f"claim cannot be checked against the {len(sources)} declared source(s)"
        )
    else:
        word = match.group(1).lower()
        if NUMERALS[word] != len(sources):
            problems.append(
                f"{name}'s partition paragraph says {word!r} ({NUMERALS[word]}) but declares "
                f"{len(sources)} source(s): {', '.join(sources)} - the count and the list disagree"
            )
    return sources, problems


def section_bounds(law_text: str, section: str) -> tuple[str | None, str | None]:
    """Return (section body, problem), bounded by heading rank rather than by a fixed neighbour."""
    opening = re.search(rf"^(#{{2,4}})\s+{re.escape(section)}\b", law_text, re.MULTILINE)
    if opening is None:
        return None, f"the law carries no {section} heading - the section this gate reads is absent"
    rank = len(opening.group(1))
    closing = re.search(rf"^#{{1,{rank}}}\s", law_text[opening.end():], re.MULTILINE)
    body = (
        law_text[opening.end(): opening.end() + closing.start()]
        if closing
        else law_text[opening.end():]
    )
    if not body.strip():
        return None, f"the law's {section} section is EMPTY - every source would read as unnamed"
    return body, None


def evaluate(
    sources: list[str], law_text: str, section: str, law_name: str, tool_name: str
) -> tuple[list[str], dict]:
    """Return (problems, population). Each problem NAMES its subject."""
    population = {"sources": sources, "named": 0, "unnamed": 0, "section_chars": 0}
    body, problem = section_bounds(law_text, section)
    if problem:
        return [f"{law_name}: {problem}"], population
    population["section_chars"] = len(body)

    problems: list[str] = []
    for source in sources:
        if re.search(rf"\b{re.escape(source)}\b", body, re.IGNORECASE):
            population["named"] += 1
        else:
            population["unnamed"] += 1
            problems.append(
                f"the {law_name} {section} section does NOT name the source {source!r}, which "
                f"{tool_name} applies - a lane auditing its work against that law cannot know "
                f"the source exists, and is right to refuse a basis it produced"
            )
    return problems, population


def population_problems(declarations: dict[str, list[str]], declared: set[str]) -> list[str]:
    """Both directions of the #577 population leg, pure so the self-probes can drive it."""
    problems: list[str] = []
    for tool in sorted(declarations):
        if tool not in declared:
            problems.append(
                f"the live-only mechanism {tool} declares a source partition "
                f"({', '.join(declarations[tool])}) but NO law pair is declared for it in this "
                f"gate's PAIRS - its sources are joined to no law at all, which is the hole "
                f"#577 exists to close"
            )
    for tool in sorted(declared - set(declarations)):
        problems.append(
            f"PAIRS declares {tool} as a source-partition mechanism, but that tool declares no "
            f"partition today - a stale declaration reads as coverage and is not"
        )
    return problems


def live_only_declarations() -> tuple[dict[str, list[str]], list[str]]:
    """Every live-only tool that declares a source partition, derived from the tree."""
    declarations: dict[str, list[str]] = {}
    problems: list[str] = []
    for path in sorted((REPO / "tools").glob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if (REPO / "TEMPLATE" / rel).exists():
            continue  # twinned mechanisms belong to test_shipped_mechanism_law.py's population
        sources, probs = partition_declaration(path.read_text(encoding="utf-8"), path.name)
        problems.extend(probs)
        if sources:
            declarations[rel] = sources
    return declarations, problems


PROBE_COUNT = 9  # P1..P9, asserted below so the constant cannot drift from the arms


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
    src, probs = partition_declaration(three, "synthetic")

    # P1 - the population is COUNTED, so a clean verdict is distinguishable from an empty one.
    problems, population = evaluate(
        src, law("stale, exhausted and growth all apply."), "5.2", "law", "tool"
    )
    check(
        "P1 a law naming every source passes and is counted",
        not probs and not problems and population["named"] == 3 and population["unnamed"] == 0,
        f"probs={probs} problems={problems} population={population}",
    )

    # P2 - THE BITE: the exact #576 shape - growth applied, growth absent from the law.
    problems, _ = evaluate(src, law("stale and exhausted re-derive the basis."), "5.2", "law", "tool")
    check(
        "P2 a source the law omits reds and NAMES it",
        len(problems) == 1 and "'growth'" in problems[0],
        f"problems={problems}",
    )

    # P3 - a FIFTH source added to the tool with the law unchanged must red without the gate
    # being edited: this is the arm a hardcoded list could never carry.
    four, _ = partition_declaration(
        tool("four", "`stale`, `exhausted`, `growth`, and `superseded`"), "synthetic"
    )
    problems, population = evaluate(
        four, law("stale, exhausted and growth all apply."), "5.2", "law", "tool"
    )
    check(
        "P3 a NEWLY DECLARED source reds on the law alone",
        four == ["stale", "exhausted", "growth", "superseded"]
        and len(problems) == 1 and "'superseded'" in problems[0],
        f"problems={problems} population={population}",
    )

    # P4 - the count word and the list disagree.
    _, probs = partition_declaration(tool("three", "`stale` and `exhausted`"), "synthetic")
    check(
        "P4 a count that disagrees with its own list reds",
        any("says 'three'" in p and "declares 2 source(s)" in p for p in probs),
        f"probs={probs}",
    )

    # P5 - SECTION BOUNDS: the token in the law's own 5.1 must not satisfy a 5.2 obligation.
    leaky = "## 5.1 previous\n\ngrowth\n\n### 5.2 The leg\n\nstale and exhausted.\n\n### 5.3 next\n"
    problems, _ = evaluate(src, leaky, "5.2", "law", "tool")
    check(
        "P5 a source named only OUTSIDE the declared section still reds",
        len(problems) == 1 and "'growth'" in problems[0],
        f"problems={problems}",
    )

    # P6 - an absent section is a failure, never a pass.
    problems, _ = evaluate(src, "## 5.1 only\n\nstale exhausted growth\n", "5.2", "law", "tool")
    check(
        "P6 an absent declared section reds",
        len(problems) == 1 and "no 5.2 heading" in problems[0],
        f"problems={problems}",
    )

    # P7 - a reworded declaration paragraph cannot pass silently: no partition is NOT a
    # partition with no sources, and the declared-pair leg says so in its own words.
    absent, probs = partition_declaration(
        "class Population:\n    \"\"\"Population.\n\n    Sources exist.\n    \"\"\"\n", "synthetic"
    )
    check(
        "P7 a tool that declares no partition is distinguishable from one with no sources",
        absent is None and not probs,
        f"absent={absent} probs={probs}",
    )

    # P8 - THE #577 ARM: a live-only tool declaring a partition that no pair declares must red.
    problems = population_problems({"tools/x.py": ["a", "b"]}, {"tools/y.py"})
    check(
        "P8 an UNDECLARED partition-declaring mechanism reds and NAMES it",
        len(problems) == 2 and any("tools/x.py" in p and "#577" in p for p in problems),
        f"problems={problems}",
    )

    # P9 - the inverse of P8: a declaration whose mechanism no longer declares a partition.
    problems = population_problems({}, {"tools/y.py"})
    check(
        "P9 a STALE pair declaration reds rather than reading as coverage",
        len(problems) == 1 and "stale declaration" in problems[0],
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

    declarations, problems = live_only_declarations()
    declared = {tool for tool, _, _ in PAIRS}
    problems.extend(population_problems(declarations, declared))
    print(
        f"  population: {len(declarations)} live-only mechanism(s) declaring a source partition "
        f"({', '.join(sorted(declarations)) or 'none'}), {len(PAIRS)} declared law pair(s)"
    )

    for tool, law, section in PAIRS:
        tool_path, law_path = REPO / tool, REPO / law
        if not tool_path.is_file():
            problems.append(f"the declared mechanism {tool} is absent from this tree")
            continue
        if not law_path.is_file():
            problems.append(f"the declared law {law} is absent from this tree")
            continue
        sources, probs = partition_declaration(
            tool_path.read_text(encoding="utf-8"), tool_path.name
        )
        problems.extend(f"{tool}: {p}" for p in probs)
        if not sources:
            problems.append(
                f"the declared mechanism {tool} declares no source partition - the declaration "
                f"this gate joins to {law} is absent, so the pair reads as coverage and is not"
            )
            continue
        found, population = evaluate(
            sources, law_path.read_text(encoding="utf-8"), section, law, tool_path.name
        )
        problems.extend(found)
        print(
            f"  {tool} -> {law} {section} ({population['section_chars']} chars): "
            f"{len(sources)} declared source(s) ({', '.join(sources)}) - "
            f"{population['named']} named, {population['unnamed']} unnamed"
        )

    for problem in problems:
        print(f"  PROBLEM  {problem}")

    if failed or problems:
        print(
            f"law-mechanism-triggers gate FAILED: {len(failed)} probe failure(s), "
            f"{len(problems)} problem(s)"
        )
        for failure in failed:
            print(f"  PROBE  {failure}")
        return 1
    print(
        f"  self-probes: {PROBE_COUNT} arm(s) ran, 0 failed - a clean verdict is "
        f"distinguishable from an empty run"
    )
    print(
        "law-mechanism-triggers gate ok: every live-only mechanism's declared source partition "
        "is named inside the law section that owns it, and no partition-declaring mechanism is "
        "left without a declared pair"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
