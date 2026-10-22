#!/usr/bin/env python3
"""Gate: the register's two homes differ ONLY in the declared parameter layer.

`TEMPLATE/tools/questions` is the kit's source of truth for the Open Questions register
(#547, adopted 2026-09-26). The copy that actually answers an owner's tap is a SECOND home,
in a SECOND repository (`leshchenko1979/opencrabs-skill`), resolved at call time by
`/opt/questions/backend.py`'s `CLI_ROOT` glob. The two were adopted apart, and nothing owned
the return leg -- so a fix landed on the template alone while the executing copy kept the
pre-fix refusal for two days (#183 -> #188). `tools/kit_census.py` NAMES the executing copy
but compares no bytes; this gate is that comparison.

What is allowed to differ is DECLARED here, in TWO shapes -- per-LINE patterns and, for a
REPLACEMENT hunk a line pattern cannot honestly bound, per-BLOCK anchor pairs (`LOCAL_BLOCKS`,
whose every entry registers an adoption OWED and prints its debt with the verdict).

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
        "the tools-log header comment -- each home names its own entry schema, and the shipped "
        "copy de-names the donor's own log lib, which resolves on no host (#85, #484)",
    ),
    (
        r"^#\s*rc vocabulary",
        "the rc-vocabulary comment -- the shipped copy de-names the donor's `tools/docs/` "
        "path, which the shipped tree does not carry (#484; #188 adoption)",
    ),
    (
        r"^#\s*(?:`oc-questions`|the instrument's home in the)",
        "the instrument's-home comment -- the shipped copy de-names the donor tool, whose "
        "home this factory does not carry (#85)",
    ),
)

DECLARED: tuple[tuple[str, str], ...] = PARAMETER_LAYER + LOCAL_FIXES

# ---------------------------------------------------------------------------
# THE DECLARED BLOCKS -- an adoption OWED, expressed as a REPLACEMENT hunk.
#
# A per-line regex CANNOT declare this honestly, and saying so is the point: a
# replacement hunk carries generic lines (`try:`, `return None, reason`, the
# `with open(target, ...)` pair) whose text also appears elsewhere in BOTH homes, so
# a regex matching them would wave through real drift anywhere in a 6,500-line file.
# MEASURED 2026-10-22: the #520 closure's residual lines need one declaration each,
# and a third of them are generic -- the declaration would have been wider than the
# defect it was meant to bound.
#
# A block is named by TWO anchors that must BOTH be present, one pair per SIDE,
# because a replacement REMOVES lines from one home while ADDING lines to the other
# and both halves are residual. Only residual lines INSIDE a resolved region are
# declared: a line outside every region is still drift, and a block whose anchors
# have moved resolves to nothing -- so the declaration stops applying and the gate
# reds rather than silently widening. `controls()` proves the outside-the-block case
# on every run.
#
# A block is a REGISTER OF A GAP, never a licence to keep it: each entry states what
# is owed and where. The label is printed with the verdict so the debt is readable
# from the gate's own output, not only from this source.
# ---------------------------------------------------------------------------
LOCAL_BLOCKS: tuple[dict, ...] = (
    {
        "label": (
            "#520's dependency-manifest closure, landed on the TEMPLATE home only -- the "
            "executing copy (opencrabs-skill) does not carry it yet, so a member running "
            "THAT copy still gets no package.json and the pre-#520 bare "
            "ERR_MODULE_NOT_FOUND. ADOPTION OWED on #188; this entry registers the gap, "
            "it does not excuse it."
        ),
        # The constant and its rationale: ADDED on the template side, absent entirely on
        # the executing side, so that half declares no region.
        "template": (
            r"^# The renderer's DEPENDENCY MANIFEST, shipped BESIDE it",
            r'^\s+"questions-render\.package\.json"\)$',
        ),
        "executing": None,
    },
    {
        "label": (
            "#520's render_page() closure -- the renderer copy became a two-source loop so "
            "the manifest lands beside it. REPLACEMENT: the executing copy still carries the "
            "single-source block. ADOPTION OWED on #188."
        ),
        "template": (
            r"^\s+# The renderer AND its dependency manifest land beside each other",
            r'^\s+return None, "%s \(%s\)" % \(failed, exc\.__class__\.__name__\)$',
        ),
        "executing": (
            r'^\s+target = os\.path\.join\(directory, "render\.mjs"\)$',
            r'^\s+return None, "renderer copy failed \(%s\)" % exc\.__class__\.__name__$',
        ),
    },
    {
        "label": (
            "#520's discoverable remedy -- a renderer fault caused by ERR_MODULE_NOT_FOUND "
            "now names the directory to run `npm install` in. REPLACEMENT: the executing copy "
            "returns the bare rc string. ADOPTION OWED on #188."
        ),
        "template": (
            r'^\s+reason = "renderer rc=%d%s" % \(proc\.returncode,$',
            r"^\s+return None, reason$",
        ),
        "executing": (
            r'^\s+return None, "renderer rc=%d%s" % \(proc\.returncode,$',
            r'^\s+\(": " \+ cause\.strip\(\)\) if cause else ""\)$',
        ),
    },
)


def declared_class(line: str) -> str | None:
    """The declared class a line belongs to, or None when the line is UNDECLARED."""
    for pattern, label in DECLARED:
        if re.search(pattern, line):
            return label
    return None


def block_region(text: str, anchors: "tuple[str, str] | None") -> "set[str] | None":
    """The lines between two anchors, INCLUSIVE -- or None when either anchor is absent.

    None means "this side declares no region" for an addition, and "the declaration has
    gone stale" for a replacement. The caller distinguishes the two by whether anchors
    were supplied at all, so a moved hunk is reported instead of passing silently.
    """
    if anchors is None:
        return None
    start_re, end_re = anchors
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.search(start_re, line)), None)
    if start is None:
        return None
    end = next((i for i in range(start, len(lines)) if re.search(end_re, lines[i])), None)
    if end is None:
        return None
    return set(lines[start : end + 1])


def declared_blocks(
    template_text: str, executing_text: str
) -> "tuple[set[str], set[str], list[str]]":
    """(template lines declared by a block, executing lines, problems).

    A block that names anchors for a side and does NOT resolve there is reported: the
    region it was written to bound has moved, so the declaration no longer describes
    the tree and a clean verdict would be a verdict about nothing.
    """
    template_lines: set[str] = set()
    executing_lines: set[str] = set()
    problems: list[str] = []
    for entry in LOCAL_BLOCKS:
        for side, text, bucket in (
            ("template", template_text, template_lines),
            ("executing", executing_text, executing_lines),
        ):
            anchors = entry.get(side)
            if anchors is None:
                continue
            region = block_region(text, anchors)
            if region is None:
                problems.append(
                    f"declared block on the {side} side did NOT resolve: {entry['label']} "
                    f"-- one of its anchors ({anchors[0]!r} .. {anchors[1]!r}) is absent, so "
                    "the region it was written to bound has moved and this declaration now "
                    "bounds nothing"
                )
                continue
            bucket |= region
    return template_lines, executing_lines, problems


def residual(template_text: str, executing_text: str) -> Counter:
    """Lines present on one side and not the other (the symmetric difference)."""
    ct = Counter(template_text.splitlines())
    ce = Counter(executing_text.splitlines())
    return (ct - ce) + (ce - ct)


def undeclared(
    template_text: str, executing_text: str, problems: "list[str] | None" = None
) -> list[str]:
    """The differing lines that are NOT in the declared layer -- the drift, if any.

    A line is declared when a `DECLARED` regex matches it OR it falls inside a resolved
    block ON THE SIDE IT CAME FROM. The sides are filtered separately because a
    replacement's two halves live in different texts: matching a template-side block
    against an executing-only line would declare a line the block never contained.
    """
    tpl_blocks, exe_blocks, block_problems = declared_blocks(template_text, executing_text)
    if problems is not None:
        problems.extend(block_problems)
    ct = Counter(template_text.splitlines())
    ce = Counter(executing_text.splitlines())
    drift: list[str] = []
    for line in ct - ce:
        if declared_class(line) is not None or line in tpl_blocks:
            continue
        drift.append(line)
    for line in ce - ct:
        if declared_class(line) is not None or line in exe_blocks:
            continue
        drift.append(line)
    return sorted(drift)


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

    # BLOCK CONTROL -- a declared block must NOT become a hole in the predicate. Two
    # arms, because a block can fail in two directions: it can swallow a line OUTSIDE
    # itself (the declaration wider than the defect), and it can silently stop
    # applying when its anchors move (a declaration that bounds nothing while the
    # verdict reads clean).
    tpl_blocks, exe_blocks, block_problems = declared_blocks(template_text, template_text)
    if not tpl_blocks:
        problems.append(
            "block control: no template-side block resolved against the live home -- the "
            "declaration bounds nothing, so the gate cannot say what it is excusing"
        )
    # A line OUTSIDE every resolved region must still bite. Placed at the TOP, not the
    # end: a block whose end anchor is near EOF would otherwise contain the synthetic
    # line and the arm would pass for the wrong reason.
    outside = "SOMETHING_OUTSIDE_A_BLOCK = 1\n" + (
        template_text if template_text.endswith("\n") else template_text + "\n"
    )
    if undeclared(template_text, outside) != ["SOMETHING_OUTSIDE_A_BLOCK = 1"]:
        problems.append(
            "block control: a line OUTSIDE every declared block was NOT flagged "
            f"(got {undeclared(template_text, outside)!r}) -- the block has widened the "
            "predicate into a hole, so a clean verdict proves nothing about the rest of "
            "the file"
        )
    # And a block whose anchors have gone must REPORT, not pass.
    moved = template_text.replace("RENDER_MANIFEST_SRC", "SOMETHING_ELSE", 1)
    _, _, moved_problems = declared_blocks(moved, moved)
    if not moved_problems:
        problems.append(
            "block control: a block with a REMOVED anchor reported no problem -- a "
            "declaration whose region has moved would silently bound nothing"
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
    block_problems: list[str] = []
    bad = undeclared(template_text, executing_text, block_problems)
    if block_problems:
        for problem in block_problems:
            print(f"FAIL: {problem}")
        return 1

    # UTF-8 BYTE counts, not character counts: the homes carry em-dashes, and a
    # character count understates the file a ` B` label claims to report.  Hoisted
    # into locals because nesting same-type quotes in an f-string is PEP 701
    # (Python 3.12+) and this gate ships to member factories of unknown interpreter.
    template_bytes = len(template_text.encode("utf-8"))
    executing_bytes = len(executing_text.encode("utf-8"))
    print(f"template home : {TEMPLATE_HOME.relative_to(REPO)} ({template_bytes} B)")
    print(f"executing home: {executing} ({executing_bytes} B)")
    print(f"population    : {len(diff)} differing line(s) examined")

    if bad:
        print(f"\nFAIL: {len(bad)} line(s) diverge OUTSIDE the declared parameter layer:")
        for line in bad:
            print(f"  {line!r}")
        print("\nEither the fix belongs on BOTH homes, or the divergence must be DECLARED")
        print("in this gate (PARAMETER_LAYER / LOCAL_FIXES) and named in #188.")
        return 1

    print(
        "OK: the difference is confined to the declared layer "
        f"({len(PARAMETER_LAYER)} parameter entries + {len(LOCAL_FIXES)} named local fix"
        f" + {len(LOCAL_BLOCKS)} declared block(s))"
    )
    # The debt is printed, not merely excused: a block that reads clean and says
    # nothing is how an owed adoption becomes invisible.
    for entry in LOCAL_BLOCKS:
        print(f"     DECLARED BLOCK, adoption owed: {entry['label']}")
    if not diff:
        print("     (the homes are byte-identical -- an empty difference is a subset)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
