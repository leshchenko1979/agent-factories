#!/usr/bin/env python3
"""Gate: the register's two homes differ ONLY in the declared parameter layer.

`TEMPLATE/tools/questions` is the kit's source of truth for the Open Questions register
(#547, adopted 2026-09-26). The copy that actually answers an owner's tap is a SECOND home,
in a SECOND repository (`leshchenko1979/opencrabs-skill`), resolved at call time by
`/opt/questions/backend.py`'s `CLI_ROOT` glob. The two were adopted apart, and nothing owned
the return leg -- so a fix landed on the template alone while the executing copy kept the
pre-fix refusal for two days (#183 -> #188). `tools/kit_census.py` NAMES the executing copy
but compares no bytes; this gate is that comparison.

What is allowed to differ is DECLARED here, and it is exactly two things:

  (1) THE PARAMETER LAYER. Each home names itself -- `PROG` (the program's own name),
      the `RENDER_SRC` built from it, `USAGE` (the usage string, which embeds `PROG`),
      and `FORK_REPO` (the tracker that copy points at). Those lines differ BY DESIGN.
      MEASURED 2026-10-03: only PROG/RENDER_SRC/USAGE actually differ (8 lines, 4 hunks);
      FORK_REPO is identical in both homes at line 50 and the header comments are
      identical too -- both are declared here as per-home PARAMETERS, not as observed
      differences, so a legitimate divergence there does not read as drift.

  (2) ONE NAMED LOCAL FIX, kept deliberately: the executing copy resolves its ledger actor
      through `OC_ACTOR` before `OPENCRABS_SESSION_ID`. It is NAMED here rather than waved
      through, because a kept divergence nobody names is the #183 shape this gate catches.

The predicate is a SUBSET: the symmetric difference of the two files' LINES must be a subset
of the declared layer. An EMPTY difference is a subset, so the gate stays GREEN once the
Toolsmith finishes the adoption and the two become byte-identical (#188's own requirement).

The executing copy is resolved the way the BACKEND resolves it -- through the census's own
`answering_path` -- so this gate and the census can never disagree about which copy is live.
When it cannot be resolved (a member factory, which has no such tree) the gate prints NOT RUN
with its reason and exits 0: it never reports the verdict of a leg that examined nothing. The
predicate's own ability to bite is proven on EVERY run by a mutation control, so a clean
verdict is never the verdict of a predicate that cannot fail.

Run:  python3 tests/test_kit_questions_homes.py
Exit: 0 pass (or NOT RUN), 1 a declared-layer violation or a failed control.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

TEMPLATE_HOME = REPO / "TEMPLATE" / "tools" / "questions"

# ---------------------------------------------------------------------------
# THE DECLARED PARAMETER LAYER -- lines each home is ENTITLED to spell its own way.
# Every entry is (regex, label); a differing line matching NONE of these is DRIFT.
# ---------------------------------------------------------------------------
PARAMETER_LAYER: tuple[tuple[str, str], ...] = (
    (r"^PROG\s*=", "PROG -- the program's own name"),
    (
        r'^\s*(?:PROG \+ )?"[A-Za-z0-9_.-]*render\.mjs"\)$',
        "RENDER_SRC continuation -- the renderer beside the CLI",
    ),
    (r"^USAGE\s*=", "USAGE -- the usage string, which embeds PROG"),
    (r"^FORK_REPO\s*=", "FORK_REPO -- the tracker this copy points at"),
)

# ---------------------------------------------------------------------------
# THE NAMED LOCAL FIXES -- deliberate divergences, NAMED rather than waved through.
# ---------------------------------------------------------------------------
LOCAL_FIXES: tuple[tuple[str, str], ...] = (
    (
        r'^\s*"actor":\s*\(?os\.environ\.get\("(?:OC_ACTOR|OPENCRABS_SESSION_ID)"',
        "actor resolution -- the executing copy honours OC_ACTOR (deliberate local fix)",
    ),
    (
        r"^#\s*Unified tools log",
        "the tools-log header comment -- the shipped copy de-names the donor's own log lib, "
        "which resolves on no host (#85)",
    ),
    (
        r"^#\s*(?:`oc-questions`|the instrument's home in the)",
        "the instrument's-home comment -- the shipped copy de-names the donor tool, whose "
        "home this factory does not carry (#85)",
    ),
)

DECLARED: tuple[tuple[str, str], ...] = PARAMETER_LAYER + LOCAL_FIXES


def declared_class(line: str) -> str | None:
    """The declared class a line belongs to, or None when the line is UNDECLARED."""
    for pattern, label in DECLARED:
        if re.search(pattern, line):
            return label
    return None


def residual(template_text: str, executing_text: str) -> Counter:
    """Lines present on one side and not the other (the symmetric difference)."""
    ct = Counter(template_text.splitlines())
    ce = Counter(executing_text.splitlines())
    return (ct - ce) + (ce - ct)


def undeclared(template_text: str, executing_text: str) -> list[str]:
    """The differing lines that are NOT in the declared layer -- the drift, if any."""
    return sorted(
        line for line in residual(template_text, executing_text) if declared_class(line) is None
    )


def controls(template_text: str) -> list[str]:
    """Non-vacuity. The predicate must BITE on an undeclared line and PASS on identity."""
    problems: list[str] = []

    base = template_text if template_text.endswith("\n") else template_text + "\n"
    synthetic = base + "SOMETHING_UNDECLARED = 1\n"
    bites = undeclared(template_text, synthetic)
    if bites != ["SOMETHING_UNDECLARED = 1"]:
        problems.append(
            "mutation control: an undeclared synthetic line was NOT flagged "
            f"(got {bites!r}) -- the predicate cannot bite, so its clean verdict means nothing"
        )

    if undeclared(template_text, template_text):
        problems.append(
            "identity control: byte-identical texts were flagged -- an empty difference "
            "is a subset and MUST pass (#188: the gate stays green once adoption completes)"
        )
    return problems


def main() -> int:
    if not TEMPLATE_HOME.is_file():
        print(f"questions-homes gate ERROR: {TEMPLATE_HOME.relative_to(REPO)} is missing")
        return 1
    template_text = TEMPLATE_HOME.read_text(encoding="utf-8")

    problems = controls(template_text)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print("controls: bites on an undeclared line; passes on identity (empty difference)")

    try:
        import kit_census  # the census owns HOW the executing copy is resolved
    except Exception as exc:  # a broken import is a hard error, never a silent pass
        print(f"questions-homes gate ERROR: cannot import tools/kit_census.py: {exc!r}")
        return 1

    info = kit_census.answering_path()
    if not info.get("measured") or not info.get("resolved"):
        print("NOT RUN -- the executing copy is not resolvable on this host, so this leg")
        print(f"  examined NOTHING: {info.get('why') or 'no candidate matched the backend glob'}")
        print("  (a member factory has no executing tree; this is not a clean verdict)")
        return 0

    executing = Path(info["resolved"])
    executing_text = executing.read_text(encoding="utf-8")
    diff = residual(template_text, executing_text)
    bad = undeclared(template_text, executing_text)

    print(f"template home : {TEMPLATE_HOME.relative_to(REPO)} ({len(template_text)} B)")
    print(f"executing home: {executing} ({len(executing_text)} B)")
    print(f"population    : {len(diff)} differing line(s) examined")

    if bad:
        print(f"\nFAIL: {len(bad)} line(s) diverge OUTSIDE the declared parameter layer:")
        for line in bad:
            print(f"  {line!r}")
        print("\nEither the fix belongs on BOTH homes, or the divergence must be DECLARED")
        print("in this gate (PARAMETER_LAYER / LOCAL_FIXES) and named in #188.")
        return 1

    print(
        "OK: the difference is confined to the declared parameter layer "
        f"({len(PARAMETER_LAYER)} parameter entries + {len(LOCAL_FIXES)} named local fix)"
    )
    if not diff:
        print("     (the homes are byte-identical -- an empty difference is a subset)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
