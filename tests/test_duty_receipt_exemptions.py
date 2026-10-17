#!/usr/bin/env python3
"""Gate: the duty-receipt exemption table is READ, and every entry in it is explained.

Origin (#506). `docs/duty-receipt-exemptions.json` was introduced as the declared escape
hatch for the ONE lawful silence in the duty-receipt leg: a cron job whose prompt carries
no `receipt_subject:` and which nobody has declared a reason for is a PROBLEM since #506,
so a box that must carry such a job needs a surface to say so in writing. The table is
factory DATA — it ships empty and each factory fills its own — which puts it in the class
`tests/gate_registry.py` calls an exemption table and holds to two directions:

  * a table that RESOLVES but which no gate declares is an ORPHAN — an exit whose reader
    is unregistered, which is the shape this gate exists to close;
  * a gate that DECLARES a table must name that table's basename in its own source, so the
    declaration and the reader cannot drift apart.

This gate is that reader's registration. It does not re-implement the parser: `one field,
one reader` (the skill's one-reader rule) means the tool's own `receipt_declaration_exemptions()` decides
what the file MEANS, and this gate asks it. What the gate adds is the strictness the reader
deliberately does not carry — the reader tolerates a reason-less entry (it has to: a
partially-written store must still excuse nothing rather than red the whole box), while an
exemption with no stated reason is an unexplained silence and belongs to nobody.

Population is PRINTED on every run, in both states, so `0` reads as "this box excuses
nothing" and never as "the check did not look": a gate whose clean output is
indistinguishable from its unrun output is the #506 false-clean one surface over.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TABLE = REPO / "docs" / "duty-receipt-exemptions.json"
RUNNER_PATH = REPO / "tools" / "patrol_host_state.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("patrol_host_state_gate", RUNNER_PATH)
    assert spec and spec.loader, f"cannot load {RUNNER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(module) -> list[str]:
    """Every arm, in one list. Empty means the table is honest and its reader is named."""
    problems: list[str] = []

    # --- the LIVE arm: this factory's own table, read through the tool's reader --------
    live_absent = not TABLE.is_file()
    if not live_absent:
        entries, problem = module.receipt_declaration_exemptions(TABLE)
        if problem:
            problems.append(f"live table: {problem}")
        else:
            raw = json.loads(TABLE.read_text(encoding="utf-8")).get("exempt") or []
            for index, entry in enumerate(raw):
                reason = entry.get("reason") if isinstance(entry, dict) else None
                if not isinstance(reason, str) or not reason.strip():
                    job = entry.get("job") if isinstance(entry, dict) else entry
                    problems.append(
                        f"live table: entry {index} excuses {job!r} with no stated reason — "
                        f"an exemption nobody explained is an unexplained silence, and the "
                        f"reason is the only thing that makes it reviewable"
                    )
    else:
        entries = {}

    # --- PROBE arms: the reader's four refusals and its one tolerance, each on its own
    # throwaway store, so a clean live run cannot stand in for an unproven parser.
    def probe(payload: str) -> tuple[dict, str | None]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duty-receipt-exemptions.json"
            path.write_text(payload, encoding="utf-8")
            return module.receipt_declaration_exemptions(path)

    # (1) ABSENT is the empty state, never a problem: every bootstrapped factory is here.
    with tempfile.TemporaryDirectory() as tmp:
        got, problem = module.receipt_declaration_exemptions(
            Path(tmp) / "duty-receipt-exemptions.json"
        )
        if (got, problem) != ({}, None):
            problems.append(
                f"probe 1: an ABSENT table returned {(got, problem)!r}, but absence is the "
                f"empty state and must not be reported as a defect"
            )

    # (2) unparseable -> a problem. A silent empty set here would hide every excuse and
    # turn a typo into a box-wide red with no cause named.
    _, problem = probe("{not json")
    if not problem:
        problems.append(
            "probe 2: an UNPARSEABLE table returned no problem — a store that cannot be "
            "read must say so, or its exemptions vanish silently"
        )

    # (3) no `exempt` list -> a problem.
    _, problem = probe('{"_note": "x"}')
    if not problem:
        problems.append(
            "probe 3: a table with no `exempt` list returned no problem — the shape is "
            "declared and a file that does not carry it is not an empty table"
        )

    # (4) an entry naming no job -> a problem.
    _, problem = probe('{"exempt": [{"reason": "because"}]}')
    if not problem:
        problems.append(
            "probe 4: an entry naming NO job returned no problem — an exemption that names "
            "nothing excuses nothing and hides its own uselessness"
        )

    # (5) the discriminating arm: a well-formed entry IS honoured, so a predicate that
    # reds everything cannot pass this gate.
    got, problem = probe('{"exempt": [{"job": "factory-x", "reason": "clock-driven"}]}')
    if problem or got != {"factory-x": "clock-driven"}:
        problems.append(
            f"probe 5: a WELL-FORMED entry returned {(got, problem)!r}, but it must be "
            f"honoured — otherwise this gate would pass by refusing every store"
        )

    # (6) the strictness this gate adds: the reader accepts a reason-less entry, and the
    # gate must not. Pinned as a probe so the tolerance cannot silently become policy.
    got, problem = probe('{"exempt": [{"job": "factory-y"}]}')
    if problem or got != {"factory-y": ""}:
        problems.append(
            f"probe 6: a reason-less entry returned {(got, problem)!r}, but the READER is "
            f"meant to tolerate it (got, then this gate refuses it) — if the reader has "
            f"tightened, delete this probe deliberately rather than leaving it to rot"
        )

    return problems


def main() -> int:
    if not RUNNER_PATH.is_file():
        print(f"NOT RUN — the reader is absent: {RUNNER_PATH}", file=sys.stderr)
        return 1

    module = load_runner()
    problems = check(module)

    state = "absent (empty state)" if not TABLE.is_file() else "present"
    entries, _ = (
        ({}, None)
        if not TABLE.is_file()
        else module.receipt_declaration_exemptions(TABLE)
    )
    population = (
        f"table {state}: {len(entries)} declared exemption(s) over "
        f"{len(entries)} job(s), {len(problems)} problem(s); probe: 6 case(s) examined"
    )

    if problems:
        print(f"FAIL — {population}", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nAn exemption is a DECLARED silence: name the job, state the reason. Fix the "
            "table, or remove it — do not leave a job excused by an entry nobody can read.",
            file=sys.stderr,
        )
        return 1

    print(f"PASS — {population}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
