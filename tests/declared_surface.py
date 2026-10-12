#!/usr/bin/env python3
"""Shared helper: a factory's DECLARED surface, read the ONE way every gate reads it.

Origin (issue #79, ruled at ledger `n=531`). Two gates now read a factory declaration
that ships as a skeleton and is filled per factory: `tests/ledger_boundary.py` (the
close-row boundary parameter, issue #78) and `tests/test_harness_bindings.py` (the
harness-binding manifest, issue #79). Both need the SAME policy -- an ABSENT declaration
SKIPS with a stated reason, a MALFORMED one FAILS -- and a second copy of that policy
would drift on exactly the inputs that matter: a missing file, an empty object, a corrupt
value. The factory would then hold a gate that excuses what another refuses.

So the MECHANISM is factored once here: the two outcome types, the raw-json reader, and
the mapping from a store-specific reader's two outcomes onto them. The NOUNS stay
separate -- `docs/ledger-invariants.json` and `docs/harness-bindings.json` each name
their own concern -- because merging two unrelated concerns into one generic parameters
file is LESS modular, not more (n=531, the DRY ruling).

Three outcomes, and the difference between them is the point
------------------------------------------------------------
* **`SkipGate`** -- this tree legitimately declares nothing to judge. Reported as
  `SKIP: <reason>`; the caller exits 0 and STATES the reason. Never a silent pass.
* **`GateError`** -- this tree declares something it cannot honour. Reported as a FAILURE
  naming the problem. A declared parameter that cannot be read is a DEFECT, not an
  absence (#69 clause (e)), so it must never be downgraded onto the skip path.
* **the caller's own value** -- the declaration was read and the predicate found nothing.

This module holds no tests (the name has no `test_` prefix, so pytest does not collect
it) and no state of its own: it is the reader, shared, so the class has ONE
implementation instead of one per gate.

Run:  imported by the gates, never run directly.
"""

from __future__ import annotations

import json
from pathlib import Path

class SkipGate(Exception):
    """Nothing to judge in THIS tree, and that is legitimate: skip with this reason."""

class GateError(Exception):
    """The tree declares something it cannot honour: fail with these problems."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)

def load_declared_json(repo: Path, rel: str, example_rel: str, concern: str) -> dict:
    """Read `docs/<concern>.json` -> dict, or `SkipGate`/`GateError`. Never anything else.

    ABSENT is a skip: the declaration is factory DATA and does not ship, so a tree that has
    not declared it is a legitimate state -- the shipped `example_rel` skeleton is what
    travels instead. An EMPTY object is NOT a skip: the file exists and says nothing, which
    no skeleton produces, so it is left to the caller's own predicate to judge.

    MALFORMED is a failure: a factory that declared something and cannot have it read must
    never hide behind the same output as no declaration at all (#69 clause (e)).
    """
    path = repo / rel
    if not path.is_file():
        raise SkipGate(
            f"no {rel} in this tree — the {concern} declaration is factory DATA, so it "
            f"does not ship; the skeleton is {example_rel}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateError([f"{rel} exists but cannot be read: {exc}"]) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GateError([f"{rel} is not JSON: {exc}"]) from exc
    if not isinstance(data, dict):
        raise GateError([f"{rel} is not a JSON object"])
    return data

def map_outcome(fn, *args, unavailable, unreadable, **kwargs):
    """Call `fn`; map ITS two declaration outcomes onto THIS module's policy.

    The one place "absent -> `SkipGate`, malformed -> `GateError`" is written for a reader
    that owns its own exception types, so every declared-surface consumer agrees about which
    outcome is a skip and which is a defect. `unavailable` / `unreadable` are the reader's
    own exception types, passed in so this helper stays decoupled from any single store.

    A reader that returns a value did read a declaration, and its value is passed through
    untouched -- this helper rules on the two FAILURE shapes only, never on the predicate.
    """
    try:
        return fn(*args, **kwargs)
    except unavailable as exc:
        raise SkipGate(str(exc)) from exc
    except unreadable as exc:
        problems = list(getattr(exc, "problems", None) or [str(exc)])
        raise GateError(problems) from exc
