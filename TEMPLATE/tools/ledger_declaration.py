#!/usr/bin/env python3
"""The factory's DECLARED ledger policy — ONE home, shared by the tool and the gates.

Two declarations live here, and for the same reason: two consumers must agree about each,
and a second copy would drift on exactly the inputs that matter.

* the FACTORY DECLARATIONS read from `docs/ledger-invariants.json` — the invariant
  BOUNDARIES a factory has adopted, the RECONSTRUCTED-CLAIM rows it holds, and the live
  CALIBRATION rows its gates judge against (the rest of this module), and
* the ROLE-TO-EVENT AUTHORIZATION MATRIX (`AUTHORIZED_ACTORS_BY_EVENT`), which the write
  path enforces at append time and the schema gate reports against.

`docs/ledger-invariants.json` maps an invariant's name to the ISO-8601 UTC instant at
which it took effect IN THIS FACTORY. It is factory DATA, so it does not ship; the
skeleton `docs/ledger-invariants.example.json` does — the shape #69 gave
`docs/products.json`.

TWO FURTHER MAPS sit beside the boundaries, keyed by the same gate name, and they are
factory data for the same reason: `reconstructions` holds a factory's own pre-boundary
reconstructed-claim rows, and `calibrations` holds the live rows its gates judge against.
Both exist because a gate PAIRED byte-identically with its TEMPLATE copy ships to every
member, so a row number written inside one is read against the member's ledger — and the
member does not have that row (#239, #248).

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
import os
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


AUTHORIZATIONS_REL = "docs/ledger-authorizations.json"
AUTHORIZATIONS_EXAMPLE_REL = "docs/ledger-authorizations.example.json"

def load_authorizations(repo: Path) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """`(declared_actors, declared_by_event)` — the factory's OWN lanes and what they may write.

    WHY THIS IS A FILE AND NOT A CONSTANT IN THE TOOL, and the reason is the SAME one that put
    `tools/actors.txt` beside the `ACTORS` tuple: `tools/ledger_declaration.py` is copied into
    every factory, so a lane that only ONE factory has cannot sit in a constant that must match
    everywhere. The matrix had no such seam, which meant a factory's own lane could be DECLARED
    as a lane (the fragment names it, `actors.txt` grants membership) and still be refused at
    append, because the matrix had no row for it and there was no lawful way to give it one.
    Membership and authorization were the two halves of the same declaration, and only one had a
    home (#193).

    A declaration ADDS; it never removes or redefines a core entry. The constant stays the floor,
    so every factory keeps the core matrix whether or not it declares anything.

    ABSENT MEANS NONE, and MALFORMED IS A PROBLEM — the convention every sibling surface states:
    absent or empty means the factory has declared nothing (the shipped state of a new factory),
    while a file that exists and cannot be read must never pass quietly, because a declaration
    that fails to load is indistinguishable from no declaration at all.
    """
    # The override is the isolation seam, the same shape `OC_ACTORS_PATH` uses for
    # membership: a probe that read the LIVE declaration would pass or fail on this
    # factory's own declared lanes instead of on the code.
    path = Path(os.environ.get("OC_AUTHORIZATIONS_PATH", repo / AUTHORIZATIONS_REL))
    if not path.is_file():
        return (), {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclarationUnreadable([f"{AUTHORIZATIONS_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise DeclarationUnreadable([f"{AUTHORIZATIONS_REL} is not valid JSON: {exc}"]) from exc
    if not isinstance(payload, dict):
        raise DeclarationUnreadable([
            f"{AUTHORIZATIONS_REL} must be a JSON object carrying `actors` and `by_event`"
        ])
    actors = payload.get("actors")
    if not isinstance(actors, list) or not all(isinstance(a, str) and a.strip() for a in actors):
        raise DeclarationUnreadable([
            f"{AUTHORIZATIONS_REL} carries no `actors` list of role names — "
            f"see {AUTHORIZATIONS_EXAMPLE_REL}"
        ])
    by_event = payload.get("by_event", {})
    if not isinstance(by_event, dict):
        raise DeclarationUnreadable([
            f"{AUTHORIZATIONS_REL} `by_event` must be an object mapping event -> [role, ...]"
        ])
    out: dict[str, tuple[str, ...]] = {}
    for event, names in by_event.items():
        if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
            raise DeclarationUnreadable([
                f"{AUTHORIZATIONS_REL} by_event[{event!r}] must be a list of role names"
            ])
        out[str(event)] = tuple(str(n) for n in names)
    return tuple(str(a) for a in actors), out



def authorized_for_event(repo: Path, event: str) -> tuple[str, ...]:
    """The roles authorized for `event` — the core matrix UNION this factory's declaration.

    ONE HOME, because the write path and the schema gate must agree about it: while they
    held separate copies, a declared authorization would pass the tool and red the gate,
    which is the same defect that made `test_ledger_schema.py` carry its own event tuple
    and refuse an event the tool lawfully wrote.

    A declaration ADDS; it never removes or redefines a core entry. So the constant is the
    floor and the declaration extends it, and a factory that declares nothing gets exactly
    the core matrix it has today.
    """
    core = AUTHORIZED_ACTORS_BY_EVENT.get(event, ())
    _, declared = load_authorizations(repo)
    return core + tuple(a for a in declared.get(event, ()) if a not in core)


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

EXEMPTIONS_REL = "docs/ledger-exemptions.json"
EXEMPTIONS_EXAMPLE_REL = "docs/ledger-exemptions.example.json"


def load_exemptions(repo: Path) -> list[tuple[str, str, str, str, str]]:
    """The declared sequence exemptions, or a typed failure naming the skeleton.

    WHY THIS IS A FILE AND NOT A CONSTANT IN THE TOOL, and the reason is law rather than
    taste. `SKILL.md` section 11: *"an exemption table holding the entries as FACTORY DATA
    in its own file and never inline in the gate, because the gate is paired byte-identically
    with its template copy and a factory sha must not ship to every new factory."* The
    ledger's `EXEMPTIONS` was the LAST surface still inline -- its three entries name
    meta-factory's own `#6`/`#8` closes of 2026-09-12 and their granting rulings -- while
    `docs/ledger-commit-exemptions.json`, `docs/ledger-no-shrink-exemptions.json` and
    `docs/ledger-retirements.json` already follow the rule. So a factory that happened to
    work on `#6` or `#8` would have had its OWN sequence defects excused by another
    factory's history, and the two entries say so in terms: *"close written before the gate
    existed"* is true of the template's ledger and of no other.

    ABSENT MEANS NONE, and MALFORMED IS A PROBLEM -- the convention the sibling surface
    states in its own words: *"Absent or empty data means no exemptions — the shipped state
    of a new factory. Anything malformed is a problem, never a silent pass: an exemption
    list that quietly fails to load is indistinguishable from no exemptions."* The law's
    concern is the SILENT failure, and a missing file is a factory that has nothing to
    excuse; a file that exists and cannot be read is the one that must never pass quietly.

    `proof` is NOT required here, deliberately. The doctrine in `tools/ledger.py` refuses a
    proofless entry at the point it would EXCUSE an omission -- *"refusing on the USED path
    rather than at load keeps a fresh factory's dead entries invisible"* -- so a dead entry
    is named where a reader is already looking, rather than failing the whole declaration.
    """
    path = repo / EXEMPTIONS_REL
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclarationUnreadable([f"{EXEMPTIONS_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise DeclarationUnreadable([f"{EXEMPTIONS_REL} is not valid JSON: {exc}"]) from exc
    if not isinstance(payload, dict):
        raise DeclarationUnreadable([f"{EXEMPTIONS_REL} must be a JSON object carrying `exempt`"])
    rows = payload.get("exempt")
    if not isinstance(rows, list):
        raise DeclarationUnreadable([
            f"{EXEMPTIONS_REL} carries no `exempt` list — see {EXEMPTIONS_EXAMPLE_REL}"
        ])
    out: list[tuple[str, str, str, str, str]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DeclarationUnreadable([f"{EXEMPTIONS_REL} exempt[{i}] is not an object"])
        # `proof` is carried through even when blank: the USE site refuses a proofless
        # entry by naming it, which is a better error than a whole-file rejection.
        missing = [k for k in ("subject", "leg", "granted", "reason") if not row.get(k)]
        if missing:
            raise DeclarationUnreadable([
                f"{EXEMPTIONS_REL} exempt[{i}] is missing {', '.join(missing)} — an "
                f"exemption names what it excuses and when it was granted"
            ])
        out.append((str(row["subject"]), str(row["leg"]), str(row["granted"]),
                    str(row["reason"]), str(row.get("proof") or "")))
    return out


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

def load_reconstructions(repo: Path) -> dict:
    """The declared `reconstructions` map, or `DeclarationUnavailable`/`DeclarationUnreadable`.

    THE SECOND DECLARATION in the same file, and it is read here rather than in the gate for
    the reason `load_invariants` is (#239): a gate paired byte-identically with its TEMPLATE
    copy ships to every member, so a row number written INSIDE it is judged against the
    member's ledger — and the member does not have this factory's rows. The map is keyed by
    the same gate name as `invariants`, so the two halves of one factory fact travel
    together.

    An ABSENT key raises `DeclarationUnavailable` — the state a bootstrapped factory is in,
    and a legitimate one. A PRESENT but unreadable map raises `DeclarationUnreadable`,
    because a factory that declared rows and cannot have them read must not be hidden behind
    the same output as no declaration at all. The two arms are `load_invariants`' own, so a
    caller reads both declarations the same way.
    """
    path = repo / DECLARATION_REL
    if not path.is_file():
        raise DeclarationUnavailable(
            f"no {DECLARATION_REL} — this factory's own reconstructed-claim rows are "
            f"DECLARED factory data, and this tree has not declared any; the skeleton is "
            f"{DECLARATION_EXAMPLE_REL}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} is not valid JSON: {exc}"]) from exc

    if not isinstance(payload, dict):
        raise DeclarationUnreadable([f"{DECLARATION_REL} must be a JSON object"])
    declared = payload.get("reconstructions")
    if declared is None:
        raise DeclarationUnavailable(
            f"{DECLARATION_REL} declares no `reconstructions` map — this factory has not "
            f"declared its own pre-boundary reconstructed-claim rows, so there is nothing "
            f"to calibrate against; the skeleton is {DECLARATION_EXAMPLE_REL}"
        )
    if not isinstance(declared, dict):
        raise DeclarationUnreadable([
            f"{DECLARATION_REL}: `reconstructions` must be an object keyed by gate name"
        ])
    return declared

def load_calibrations(repo: Path) -> dict:
    """The declared `calibrations` map, or `DeclarationUnavailable`/`DeclarationUnreadable`.

    THE THIRD DECLARATION in the same file, and it is read here rather than in the gate for
    the reason `load_invariants` and `load_reconstructions` are (#239, #248): a gate paired
    byte-identically with its TEMPLATE copy ships to every member, so a row number written
    INSIDE it is judged against the MEMBER's ledger — and the member does not have this
    factory's rows. A gate whose LIVE calibration rows are literals therefore goes RED on
    every member tree, naming a history that is not the reader's. The map is keyed by the
    same gate name as `invariants` and `reconstructions`, so the three halves of one factory
    fact travel together.

    An ABSENT key raises `DeclarationUnavailable` — the state a bootstrapped factory is in,
    and a legitimate one. A PRESENT but unreadable map raises `DeclarationUnreadable`,
    because a factory that declared calibrations and cannot have them read must not be
    hidden behind the same output as no declaration at all. The two arms are
    `load_invariants`' own, so a caller reads all three declarations the same way.
    """
    path = repo / DECLARATION_REL
    if not path.is_file():
        raise DeclarationUnavailable(
            f"no {DECLARATION_REL} — this factory's own live calibration rows are "
            f"DECLARED factory data, and this tree has not declared any; the skeleton is "
            f"{DECLARATION_EXAMPLE_REL}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} is not valid JSON: {exc}"]) from exc

    if not isinstance(payload, dict):
        raise DeclarationUnreadable([f"{DECLARATION_REL} must be a JSON object"])
    declared = payload.get("calibrations")
    if declared is None:
        raise DeclarationUnavailable(
            f"{DECLARATION_REL} declares no `calibrations` map — this factory has not "
            f"declared the live rows its gates calibrate against, so there is nothing to "
            f"calibrate with; the skeleton is {DECLARATION_EXAMPLE_REL}"
        )
    if not isinstance(declared, dict):
        raise DeclarationUnreadable([
            f"{DECLARATION_REL}: `calibrations` must be an object keyed by gate name"
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
