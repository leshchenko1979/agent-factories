#!/usr/bin/env python3
"""The factory's DECLARED ledger policy — ONE home, shared by the tool and the gates.

Two declarations live here, and for the same reason: two consumers must agree about each,
and a second copy would drift on exactly the inputs that matter.

* the INVARIANT BOUNDARIES a factory has adopted, read from `docs/ledger-invariants.json`
  (the rest of this module), and
* the ROLE-TO-EVENT AUTHORIZATION MATRIX (`AUTHORIZED_ACTORS_BY_EVENT`), which the write
  path enforces at append time and the schema gate reports against.

`docs/ledger-invariants.json` maps an invariant's name to the ISO-8601 UTC instant at
which it took effect IN THIS FACTORY. It is factory DATA, so it does not ship; the
skeleton `docs/ledger-invariants.example.json` does — the shape #69 gave
`docs/products.json`.

Two consumers read it, and they must agree about what it says:

* `tests/ledger_boundary.py` — the gates. A row at or after its boundary is GOVERNED, and
  a row before it is EXCUSED and printed as such.
* `tools/ledger.py repair` — the write path. A row before its boundary must be REFUSED,
  because writing a value into a pre-boundary row is the BACKFILL the no-backfill law
  forbids.

The POLICIES differ deliberately: a gate with nothing to judge SKIPS, and a repair with
no boundary to stand on REFUSES. The READING must not differ. Two implementations would
drift on exactly the inputs that matter — a missing key, a malformed value, an
unparseable date — and the factory would then hold a gate that excuses a row the repair
path refuses to correct, or one that governs a row the repair path would happily rewrite.
So the reading lives here, once, and each consumer maps this module's two outcomes onto
its own policy:

* `DeclarationUnavailable` — nothing declared for this key, or no declaration at all.
  The caller decides: SKIP (a gate) or REFUSE (the repair path). Never a silent pass, and
  never another factory's date.
* `DeclarationUnreadable` — the factory declared something it cannot honour. A declared
  parameter that cannot be read is a DEFECT, not an absence (#69 clause (e)), so both
  callers FAIL. It must never be quietly downgraded onto the skip path, which is why the
  two outcomes are separate types rather than one exception carrying a flag.

This module holds no tests and no state of its own: it is the reader, and it is the only
one. `tools/ledger.py` reaches it through a plain import (so the fixture helper
`tests/gate_fixtures.stage_tool` copies it into a throwaway tree by following that
import), and `tests/ledger_boundary.py` adds the tool directory to `sys.path`.

Run:  imported by `tools/ledger.py`, `tests/ledger_boundary.py` and
      `tests/test_ledger_schema.py`, never run directly.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

DECLARATION_REL = "docs/ledger-invariants.json"
DECLARATION_EXAMPLE_REL = "docs/ledger-invariants.example.json"

# Role-to-Event authorization, in ONE home.
#
# Two consumers must agree about it and neither may hold its own copy: the write path
# (`tools/ledger.py append`) refuses a row the matrix does not authorize, and
# `tests/test_ledger_schema.py` reports one written before that refusal existed. While the
# matrix lived only in the gate, the write path could not consult it, so an unauthorized
# row was written SILENTLY and surfaced a day later — the gate was the only guard, and its
# blind spot was exactly one audit wide by construction.
#
# Membership is not authorization: `known_actors()` answers whether a name is an actor at
# all, and this answers which actor may write which event. `append` checks both, and a
# refusal names the event and the actor it refused.
AUTHORIZED_ACTORS_BY_EVENT: dict[str, tuple[str, ...]] = {
    "genesis": ("hq", "owner"),
    "ruling": ("hq", "owner"),
    "score": ("surveys", "hq", "owner"),
    "intake": ("triage", "hq", "owner", "delegate"),
    "claim": ("hq", "worker", "carrier", "triage", "delegate", "surveys"),
    "dispatch": ("triage", "hq", "owner", "delegate"),
    "close": ("hq", "worker", "carrier", "triage", "delegate", "surveys", "owner"),
    "run": ("hq", "surveys", "worker", "carrier", "triage", "delegate", "owner"),
}

class DeclarationUnavailable(Exception):
    """This factory has declared nothing for this key — the CALLER decides what that means.

    A gate skips on it (there is nothing to judge); the repair path refuses on it (a row's
    boundary cannot be established, so its correction cannot be shown to be a correction
    rather than a backfill). One reading, two policies.
    """

class DeclarationUnreadable(Exception):
    """The factory declared something it cannot honour: FAIL, never skip."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)

def parse_ts(value: str) -> dt.datetime:
    """An ISO-8601 UTC timestamp, as `tools/ledger.py` writes it."""
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))

def load_invariants(repo: Path) -> dict:
    """The declared `invariants` map, or `DeclarationUnavailable`/`DeclarationUnreadable`."""
    path = repo / DECLARATION_REL
    if not path.is_file():
        raise DeclarationUnavailable(
            f"no {DECLARATION_REL} — the boundary is a DECLARED factory parameter "
            f"(#78 clause b), and this tree has not declared one; the skeleton is "
            f"{DECLARATION_EXAMPLE_REL}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} is not valid JSON: {exc}"]) from exc

    if not isinstance(payload, dict):
        raise DeclarationUnreadable([f"{DECLARATION_REL} must be a JSON object carrying `invariants`"])
    declared = payload.get("invariants")
    if not isinstance(declared, dict):
        raise DeclarationUnreadable([
            f"{DECLARATION_REL} carries no `invariants` map — see {DECLARATION_EXAMPLE_REL}"
        ])
    return declared

def boundary_for(repo: Path, key: str) -> tuple[dt.datetime, str]:
    """The boundary `key` names, as `(datetime, declared-text)`.

    The declared TEXT is returned beside the parsed value because the refusal and the
    `excused:` lines both quote the date the factory itself declared, rather than one
    this repository carries.
    """
    declared = load_invariants(repo)
    value = declared.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise DeclarationUnavailable(
            f"{DECLARATION_REL} declares no `{key}` boundary — this factory has not "
            f"adopted that invariant, so there is no boundary to judge against"
        )
    if not isinstance(value, str):
        raise DeclarationUnreadable([
            f"{DECLARATION_REL}: `{key}` must be an ISO-8601 UTC string, found "
            f"{type(value).__name__}"
        ])
    try:
        when = parse_ts(value)
    except (ValueError, TypeError) as exc:
        raise DeclarationUnreadable([
            f"{DECLARATION_REL}: `{key}` is not a readable ISO-8601 timestamp: "
            f"{value!r} ({exc})"
        ]) from exc
    return when, value
