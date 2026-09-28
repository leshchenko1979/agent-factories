#!/usr/bin/env python3
"""Gate: the insights synthesizer's advertised interface is its real interface.

Origin (issue #42). Two defects in `tools/synthesize_insights.py`, both latent
rather than firing, which is why neither had been noticed.

1. **The module advertised a capability it does not have.** The usage block
   named `--file-issue`; `argparse` defines two flags, not three, and the file
   contains no `gh` call, no HTTP client and no board client anywhere. The
   weekly pacemaker cron was instructed to "file GitHub issues on board" on the
   strength of that docstring, so the step was either skipped silently or done
   by hand in the agent turn. A documented interface must be a real interface.
   The fix drops the flag and the claim; this gate keeps them from returning.

2. **The rework parser guard admitted a row it then indexed past.** The guard
   tested `len(cols) >= 4` and the body read `cols[4]` — the fifth — so a
   four-cell row raised `IndexError` and aborted the whole synthesis pass rather
   than skipping one row. The same off-by-one also mis-mapped *every* row it
   did parse: the schema is `Date | Source | Defect | Root cause | Resolution |
   Prevented by | Subject`, so the defect text is index **2**, while the code
   read index 1 — mining the *Source* column as if it were the defect. That
   second half was not in the issue and was found while fixing the first.

**Why the probe rows look the way they do.** The classifier tests the *union* of
`defect + cause + prevented_by` against an ordered `elif` chain, so a probe row
only discriminates if the mis-mapped union lands in a *different* branch. An
earlier version of this gate put a concurrency word in Defect and a role word in
Source: under the old index-1 mapping the defect text simply slid into `cause`,
the concurrency word still matched, and — because concurrency is the first
branch — the same category came out either way. The gate was vacuous and passed
against a mutated mapping.

These rows are built to separate the two mappings instead: Source carries a
**concurrency** word (`race`, first branch) and Defect carries a **schema** word
(`schema`, third branch). Correct mapping reads only Defect/Root cause/Prevented
by and yields `schema_drift`; the index-1 mapping pulls Source into the union and
yields `concurrency_locking`. Two rows, so the `>= 2` pattern threshold is met.

The discrimination was established by running the tool against a scratch
mutation, not by reasoning: indices shifted only (width guard intact) yields
`concurrency_locking` and fails this gate; the full original defect exits 1 on
the four-cell row.

Run:  python3 tests/test_synthesize_interface.py
Exit: 0 the advertised interface is real and the parser is width-safe, 1 otherwise.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "synthesize_insights.py"
LOCAL_TOOLS = REPO / "tools"

# The fixture that builds the throwaway tree, shared with the other gates that
# copy a tool into one: three sites cannot drift apart if there is one helper.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_fixtures import stage_tool  # noqa: E402
# `[--flag]` in the usage block, and `add_argument("--flag"` in the parser.
DOCSTRING_FLAG = re.compile(r"\[(--[a-z][a-z-]*)\]")
PARSER_FLAG = re.compile(r'add_argument\(\s*"(--[a-z][a-z-]*)"')

HEADER = "| Date | Source | Defect | Root cause | Resolution | Prevented by | Subject |"
SEPARATOR = "|---|---|---|---|---|---|---|"

# Two well-formed rows whose Source and Defect classify into different branches,
# plus one four-cell row — the width the old guard admitted and then indexed past.
PROBE_ROWS = (
    "| 2026-01-01 | a race in the runner | Schema drift in the log | no guard | added a guard | nothing yet | none |",
    "| 2026-01-02 | a race in the runner | Schema drift in the audit | no guard | added a guard | nothing yet | none |",
    "| 2026-01-03 | short | a four-cell row | cause |",
)


def flag_problems() -> tuple[list[str], set[str], set[str]]:
    """(problems, advertised, defined) for the module's own interface claim."""
    src = TOOL.read_text(encoding="utf-8")
    advertised = set(DOCSTRING_FLAG.findall(src))
    defined = set(PARSER_FLAG.findall(src))
    problems = [
        f"the usage block advertises {flag}, which argparse never defines"
        for flag in sorted(advertised - defined)
    ]
    problems += [
        f"argparse defines {flag}, which the usage block never names"
        for flag in sorted(defined - advertised)
    ]
    return problems, advertised, defined


def mining_problems() -> tuple[list[str], list[str]]:
    """(problems, notes) from running the tool against a throwaway tree."""
    notes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="synthesize-gate-") as tmp:
        root = Path(tmp)
        (root / "tools").mkdir()
        (root / "evidence").mkdir()
        stage_tool(TOOL, root / "tools", LOCAL_TOOLS)
        (root / "evidence" / "rework.md").write_text(
            "\n".join((HEADER, SEPARATOR, *PROBE_ROWS)) + "\n", encoding="utf-8"
        )
        proc = subprocess.run(
            [sys.executable, str(root / "tools" / TOOL.name), "--json"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            if "ModuleNotFoundError" in stderr or "ImportError" in stderr:
                # The tool never ran, so nothing about its parsing is under test:
                # the FIXTURE's tree is incomplete. Saying so plainly keeps the next
                # reader out of the wrong file — the message below blamed the
                # four-cell row while the cause was a missing neighbour import.
                return (
                    [
                        f"the tool could not be imported in the throwaway tree — the "
                        f"fixture does not model its import closure "
                        f"(stderr: {stderr[:200]!r})"
                    ],
                    notes,
                )
            return (
                [
                    f"the tool exited {proc.returncode} on a rework log holding a "
                    f"four-cell row — a short row must be skipped, not abort the pass"
                    f" (stderr: {stderr[:200]!r})"
                ],
                notes,
            )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            return ([f"the tool's --json output did not parse: {exc}"], notes)

    patterns = payload.get("friction_patterns", [])
    by_category = {p.get("category"): p for p in patterns}
    notes.append(f"throwaway tree mined {len(patterns)} pattern(s) from 3 rows")

    problems: list[str] = []
    if "schema_drift" not in by_category:
        problems.append(
            "a row carrying 'schema' in its Defect column did not reach "
            "schema_drift — the defect text is not being read from the Defect "
            "column (index 2)"
        )
    else:
        occurrences = by_category["schema_drift"].get("occurrences")
        if occurrences != 2:
            problems.append(
                f"schema_drift counted {occurrences} defect(s), expected 2 — "
                "the four-cell row was not skipped cleanly"
            )
    if "concurrency_locking" in by_category:
        problems.append(
            "a row whose Defect says 'Schema drift' was classified by its Source "
            "column ('a race in the runner') instead — the defect index is off by one"
        )
    return problems, notes


def main() -> int:
    flag_issues, advertised, defined = flag_problems()
    mining_issues, notes = mining_problems()
    problems = flag_issues + mining_issues

    for note in notes:
        print(f"  note: {note}")
    if problems:
        for line in problems:
            print(f"  FAIL {line}")
        return 1
    print(
        f"synthesize interface: clean — usage block and argparse agree on "
        f"{len(advertised)} flag(s) ({', '.join(sorted(defined))}); a four-cell rework "
        f"row is skipped and the Defect column is the one mined"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
