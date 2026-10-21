#!/usr/bin/env python3
"""Gate: a DECLARED event authorizes the WHOLE claim population, not a slice of it.

WHY THIS GATE EXISTS (#526, ruling at ledger n=3908)
----------------------------------------------------
A DECLARED event is one this factory adds through `docs/ledger-refs-kinds.json`. It has
no row in the core authorization matrix, so its `by_event` entry in
`docs/ledger-authorizations.json` is its ENTIRE population — nothing falls back on the
core tuple. The vacuity pin in `tests/test_ledger_schema.py` asks whether such an event
authorizes ANYBODY; it cannot ask whether it authorizes EVERYBODY it should. An event that
names eight of fourteen lanes passes that pin, and the eight lanes it does name can write
rows while the six it omits are refused BY NAME at the append.

That is not hypothetical, and it is not one defect. It happened TWICE, and both instances
were found by MEASUREMENT, never by a gate:

  * `conversion` (#462) — declared with the eight instrument lanes only; `surveys`, the
    lane the ruling names as the declarer, was refused at the append, and zero conversion
    rows existed twelve days after the ruling that created the event.
  * `release` (#461) — the same shape one event over; 373 claim rows against 0 release
    rows in 3085, because no lane that could TAKE a claim could WITHDRAW one.

The population is correct today BY HAND. A hand-correct population is a fact about the
current file, not a property of the tree, so it decays the moment the next event is
declared or the core matrix grows a lane. This gate turns that hand-maintenance into a
check.

THE PREDICATE
-------------
For every event named in this factory's DECLARED vocabulary, the set of roles
`authorized_for_event(repo, event)` returns must be a SUPERSET of
`authorized_for_event(repo, "claim")`.

`claim` is the referent because it carries a CORE matrix row and therefore cannot itself
be narrow, and because it is the population the mirror principle is defined against: a
lane may withdraw the claim it may make, and a lane may declare the conversion of the
regression it may claim and close. Both instances above are that one sentence, violated.

THE POPULATION IS ASKED OF THE TOOL, NEVER RE-DERIVED HERE
----------------------------------------------------------
`load_refs_kinds(REPO)[1]` is the declared vocabulary, and `authorized_for_event` is the
one reader of the authorization surface — the same two functions the write path and the
schema gate call. A second parse of either JSON would be a second answer to a question
that has one home, which is the defect `#487` had just removed from `tools/ledger.py`
one file over.

WHAT AN EMPTY DECLARATION MEANS, AND WHY IT IS NOT A PASS
---------------------------------------------------------
The shipped `docs/ledger-refs-kinds.example.json` declares no events, so a member tree
that has not bootstrapped has NOTHING TO JUDGE. That is a STATE, not an error — the same
distinction `c0a8f61` drew for the release probe arms — so this gate SKIPS, and prints its
reason WITH the population it examined. `examined N declared event(s)` appears on EVERY
outcome, because an empty population and a clean population are indistinguishable in a
silent green (#116).

WHAT THIS GATE IS NOT, AND THE BOUND IS STATED SO IT IS NOT REOPENED
--------------------------------------------------------------------
It is a DETECTOR, not a prevention. Nothing offline can require the vocabulary half and
the authorization half to land in ONE unit: they are two files, in two offices, and that
is #210's own recorded bound. A lane that declares an event today and widens the
authorization tomorrow is RED in between, which is the correct direction — the gate reads
the tree as it stands, and the tree as it stands would refuse the lanes the event is for.

A DECLARATION THAT CANNOT BE READ is a DEFECT, not an absence (#69 clause (e)): the shared
reader raises `DeclarationUnreadable` and this gate fails on it rather than reading it as
an empty vocabulary. That is the whole reason the reader exists, and the arm below pins it.

THE BITE ARMS, AND WHY THEY RUN ON EVERY INVOCATION
---------------------------------------------------
A coverage check whose live population happens to be right is green whether or not its
predicate works. So this gate carries its own hermetic fixture pair, and runs it every
time: a fixture factory declares an event whose `by_event` names only the eight instrument
lanes, and the gate must EXIT 1 naming the event and the missing lanes; the same fixture
must clear once the six core claim lanes join. The arms are run as a SUBPROCESS of this
file with the declaration seams pointed at the fixture, so what is proven is the exit path
a CI actually reads, never an in-process helper's return value. `OC_POPULATION_ARM=1`
marks the child, which skips the arms in turn rather than recursing.

RUNNER: script, declared in `registry/gates.json` under `modes`. The `__main__` block owns
the verdict, and the fixture arms are subprocess probes of that block — the same shape as
`tests/test_ledger_identity.py` and `tests/test_ledger_no_shrink.py`.

Run:  python3 tests/test_declared_event_population.py
Exit: 0 clean, or nothing to judge (printed with its reason and its population);
      1 on a declared event narrower than `claim`, or on a declaration that cannot be read.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from ledger_declaration import (  # noqa: E402  (the import seam needs sys.path first)
    AUTHORIZATIONS_REL,
    AUTHORIZED_ACTORS_BY_EVENT,
    REFS_KINDS_REL,
    DeclarationUnreadable,
    authorized_for_event,
    load_refs_kinds,
)

REFERENT = "claim"

# The eight instrument lanes the two measured instances declared, spelled out rather than
# read from the live file: a bite arm that borrowed its population from the tree it is
# checking would move with the defect it exists to catch.
INSTRUMENT_LANES = (
    "ledger",
    "questions",
    "pacemakers",
    "methodology",
    "fleet-instruments",
    "review-rotation",
    "insights",
    "hygiene",
)

def coverage(repo: Path) -> tuple[tuple[str, ...], list[str]]:
    """`(declared_events, problems)` — every declared event measured against `claim`."""
    _, declared = load_refs_kinds(repo)
    referent = authorized_for_event(repo, REFERENT)
    problems: list[str] = []
    if not referent:
        problems.append(
            f"`{REFERENT}` authorizes NOBODY in this tree — the referent is empty, so no "
            f"declared event's population can be judged against it"
        )
        return declared, problems
    for event in declared:
        population = authorized_for_event(repo, event)
        missing = [lane for lane in referent if lane not in population]
        if missing:
            problems.append(
                f"`{event}` is DECLARED in {REFS_KINDS_REL} but its population is narrower "
                f"than `{REFERENT}`: missing {', '.join(missing)}. A declared event has no "
                f"core row to fall back on, so its by_event entry in "
                f"{AUTHORIZATIONS_REL} is its ENTIRE population"
            )
    return declared, problems

def _bite_arms() -> int:
    """Run the fixture pair through THIS file's exit path; return the arms' verdict."""
    event = "probe"
    core_claim = list(AUTHORIZED_ACTORS_BY_EVENT[REFERENT])
    assert core_claim, "the core matrix must authorize `claim`, or the referent is unjudgeable"
    here = str(Path(__file__).resolve())

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        refs = root / "ledger-refs-kinds.json"
        authz = root / "ledger-authorizations.json"
        refs.write_text(json.dumps({"kinds": [], "events": [event]}), encoding="utf-8")
        env = {
            **os.environ,
            "OC_REFS_KINDS_PATH": str(refs),
            "OC_AUTHORIZATIONS_PATH": str(authz),
            "OC_POPULATION_ARM": "1",
        }

        def invoke() -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, here], capture_output=True, text=True, env=env, cwd=REPO
            )

        # ARM 1 — the measured defect: an event naming only the instrument lanes must RED,
        # naming the event and every missing claim lane. This is the arm that proves the
        # predicate bites rather than agreeing with a population that happens to be right.
        authz.write_text(
            json.dumps({"actors": list(INSTRUMENT_LANES), "by_event": {event: list(INSTRUMENT_LANES)}}),
            encoding="utf-8",
        )
        red = invoke()
        out = red.stdout + red.stderr
        if red.returncode != 1:
            print(f"FAIL  bite arm 1: a narrow declaration must exit 1, got {red.returncode}\n{out}")
            return 1
        if event not in out:
            print(f"FAIL  bite arm 1: the refusal must name the event `{event}`\n{out}")
            return 1
        for lane in core_claim:
            if lane not in out:
                print(f"FAIL  bite arm 1: the refusal must name the missing lane `{lane}`\n{out}")
                return 1
        if "examined 1 declared event(s)" not in out:
            print(f"FAIL  bite arm 1: every outcome must print its population\n{out}")
            return 1

        # ARM 2 — the same fixture, widened: the six core claim lanes join and it CLEARS.
        # Without this half, arm 1 would be satisfied by a gate that reds on everything.
        authz.write_text(
            json.dumps({
                "actors": list(INSTRUMENT_LANES) + core_claim,
                "by_event": {event: list(INSTRUMENT_LANES) + core_claim},
            }),
            encoding="utf-8",
        )
        green = invoke()
        out = green.stdout + green.stderr
        if green.returncode != 0:
            print(f"FAIL  bite arm 2: the widened fixture must clear, got {green.returncode}\n{out}")
            return 1

        # ARM 3 — an empty declaration SKIPS with its reason and its population, rc 0. The
        # shipped example is exactly this tree, so a silent pass here would be invisible in
        # every member factory that has not bootstrapped.
        refs.write_text(json.dumps({"kinds": [], "events": []}), encoding="utf-8")
        empty = invoke()
        out = empty.stdout + empty.stderr
        if empty.returncode != 0:
            print(f"FAIL  bite arm 3: an empty declaration must skip, not fail, got {empty.returncode}\n{out}")
            return 1
        if "examined 0 declared event(s)" not in out or "SKIPPED" not in out:
            print(f"FAIL  bite arm 3: a skip must print its reason and its population\n{out}")
            return 1

    print(
        "PASS  bite arms: a narrow declaration exits 1 naming the event and the missing lanes; "
        "the same fixture clears once the core claim lanes join; an empty declaration skips "
        "with its reason printed"
    )
    return 0

def main() -> int:
    try:
        declared, problems = coverage(REPO)
    except DeclarationUnreadable as exc:
        print(f"FAIL  {exc}")
        return 1

    population = ", ".join(declared) if declared else "none"
    print(f"examined {len(declared)} declared event(s): {population}")

    if not declared:
        print(
            f"SKIPPED  no event is DECLARED in {REFS_KINDS_REL} — a factory that has not "
            f"declared its own vocabulary has nothing to judge. This is a STATE, not a pass."
        )
        return 0 if os.environ.get("OC_POPULATION_ARM") == "1" else _bite_arms()

    if problems:
        for problem in problems:
            print(f"FAIL  {problem}")
        return 1

    referent = authorized_for_event(REPO, REFERENT)
    print(
        f"PASS  every declared event authorizes at least the {len(referent)} lane(s) "
        f"`{REFERENT}` does"
    )
    if os.environ.get("OC_POPULATION_ARM") == "1":
        return 0
    return _bite_arms()

if __name__ == "__main__":
    sys.exit(main())
