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
REFS_KINDS_REL = "docs/ledger-refs-kinds.json"
REFS_KINDS_EXAMPLE_REL = "docs/ledger-refs-kinds.example.json"


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


def load_refs_kinds(repo: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(declared_kinds, declared_events)` — the vocabulary this factory carries BEYOND the core.

    WHY THIS IS A FILE AND NOT A CONSTANT, for the same reason as `load_authorizations`: this
    module is copied into every factory, so a kind or an event that only ONE factory carries
    cannot sit in a constant that must match everywhere. Without the seam a member's own
    vocabulary had no lawful home: `tools/ledger.py` would refuse `ack`, and the only way to
    carry it was to fork the writer.

    A declaration ADDS; it never removes or redefines a core entry. The core tuple stays the
    floor, so a factory that declares nothing gets exactly the vocabulary it has today.

    ABSENT MEANS NONE, and MALFORMED IS A PROBLEM — the convention every sibling surface states.
    Absent or empty is the shipped state of a new factory; a file that exists and cannot be read
    must never pass quietly, because a declaration that fails to load is indistinguishable from
    no declaration at all.

    THIS IS THE READER THE GATE MUST USE. The schema gate used to parse this file itself, inside
    a bare `except (OSError, json.JSONDecodeError): return ()` — so a malformed declaration read
    as an EMPTY vocabulary, and an empty vocabulary is exactly what the vacuity pin cannot see.
    One reading, one home.
    """
    # The override is the isolation seam, the same shape `OC_AUTHORIZATIONS_PATH` uses: a probe
    # that read the LIVE declaration would pass or fail on this factory's own vocabulary instead
    # of on the code.
    path = Path(os.environ.get("OC_REFS_KINDS_PATH", repo / REFS_KINDS_REL))
    if not path.is_file():
        return (), ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclarationUnreadable([f"{REFS_KINDS_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise DeclarationUnreadable([f"{REFS_KINDS_REL} is not valid JSON: {exc}"]) from exc
    if not isinstance(payload, dict):
        raise DeclarationUnreadable([
            f"{REFS_KINDS_REL} must be a JSON object carrying `kinds` and `events`"
        ])
    out: list[tuple[str, ...]] = []
    for key in ("kinds", "events"):
        names = payload.get(key, [])
        if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
            raise DeclarationUnreadable([
                f"{REFS_KINDS_REL} `{key}` must be a list of names — "
                f"see {REFS_KINDS_EXAMPLE_REL}"
            ])
        out.append(tuple(str(n) for n in names))
    return out[0], out[1]


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

def load_dispatch_batches(repo: Path) -> dict:
    """The declared `dispatch_batches` map, or `DeclarationUnavailable`/`DeclarationUnreadable`.

    THE FOURTH DECLARATION in the same file, on the same ground as the three above: it is
    FACTORY DATA, so it does not ship and the skeleton does. It exists because a dispatch
    can be a BATCH ACT rather than a per-item row (#519, ruling n=3864): a review cycle's
    findings are fanned out by one `run` receipt and a partition of per-lane route files,
    and the per-item `dispatch` rows are then owed to Triage and may never be written. NO
    BACKFILL (`n=1596`) bars writing them after the fact, so the only lawful record of that
    routing is a DECLARATION that the batch act happened — which is true, and dated.

    It is NOT an inference surface, and the difference is the whole reason it is a file of
    its own rather than a lookup. The finding→issue linkage in such a batch is prose-only:
    `reviews/20260927-c1/state.json`'s `codification_plan` carries no issue field, and the
    route files name findings by lens and F-number. A leg that resolved units by matching a
    finding string against an issue title would be guessing with a join's clothes on, and a
    wrong resolution there silently excuses a real debt. So the units are DECLARED, by the
    lane that can see the batch, and a reader only ever reads them.

    Shape: `{"<batch-slug>": {"row": <ledger n of the batch act>, "units": [<issue>, ...],
    "recorded_at": "<ISO-8601 UTC instant the declaration was made>", "basis": "<prose>"}}`.
    A `units` entry that is not a positive integer is a FAILURE, not a skip: an empty or
    malformed declaration is the absent one wearing a key, and excusing a population is
    exactly the act this declaration must not be able to do by accident.
    """
    path = repo / DECLARATION_REL
    if not path.is_file():
        raise DeclarationUnavailable(
            f"no {DECLARATION_REL} — a batch dispatch is DECLARED factory data, and this "
            f"tree has declared none; the skeleton is {DECLARATION_EXAMPLE_REL}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} is not valid JSON: {exc}"]) from exc

    if not isinstance(payload, dict):
        raise DeclarationUnreadable([f"{DECLARATION_REL} must be a JSON object"])
    declared = payload.get("dispatch_batches")
    if declared is None:
        raise DeclarationUnavailable(
            f"{DECLARATION_REL} declares no `dispatch_batches` map — no batch dispatch has "
            f"been recorded in this factory, so there is nothing to resolve against; the "
            f"skeleton is {DECLARATION_EXAMPLE_REL}"
        )
    if not isinstance(declared, dict):
        raise DeclarationUnreadable([
            f"{DECLARATION_REL}: `dispatch_batches` must be an object keyed by batch slug"
        ])
    if not declared:
        raise DeclarationUnreadable([
            f"{DECLARATION_REL}: `dispatch_batches` is an EMPTY map — an empty declaration "
            f"is the absent one wearing a key, and it would excuse a population on no evidence"
        ])

    problems: list[str] = []
    batches: dict[str, dict] = {}
    for slug, entry in declared.items():
        if not isinstance(entry, dict):
            problems.append(f"{DECLARATION_REL}: `dispatch_batches.{slug}` must be an object")
            continue
        row = entry.get("row")
        if not isinstance(row, int) or isinstance(row, bool) or row < 1:
            problems.append(
                f"{DECLARATION_REL}: `dispatch_batches.{slug}.row` must be the positive "
                f"ledger row number of the batch act, found {row!r}"
            )
            continue
        units = entry.get("units")
        if not isinstance(units, list) or not units:
            problems.append(
                f"{DECLARATION_REL}: `dispatch_batches.{slug}.units` must be a NON-EMPTY "
                f"list of issue numbers — a batch that dispatched nothing is not a batch"
            )
            continue
        bad = [u for u in units if not isinstance(u, int) or isinstance(u, bool) or u < 1]
        if bad:
            problems.append(
                f"{DECLARATION_REL}: `dispatch_batches.{slug}.units` carries non-positive "
                f"or non-integer entries: {bad[:5]}"
            )
            continue
        batches[slug] = {
            "row": row,
            "units": [int(u) for u in units],
            "recorded_at": str(entry.get("recorded_at") or ""),
            "basis": str(entry.get("basis") or ""),
        }
    if problems:
        raise DeclarationUnreadable(problems)
    return batches


def load_standing_items(repo: Path) -> dict[int, dict]:
    """The declared `standing_items` list, keyed by issue, or its refusal (#586).

    THE FIFTH DECLARATION in the same file, on the same ground as the four above: it is
    FACTORY DATA, so it does not ship and the skeleton does. It exists because a class of
    board item is PERMANENT STATE rather than work — `#581` is the standing routing item
    that `conversion_routing_problems` requires a conversion row to cite, so every one of
    `undispatched-ruling`'s four exits is a FALSE record for it: a `claim` asserts work
    nobody started, a `close` breaks the conversion leg (which tests the item's state at
    the row's own `ts`, so closing it makes every future conversion row citing it read
    UNANSWERED, including the one at `n=4456` that already cites it), a subject-`dispatch`
    claims work owed to a lane when the ruling at `n=4472` states none is, and a declared
    batch asserts a dispatch act that never happened. Ruling `n=4478`.

    Shape: a LIST of `{"issue": <board number>, "ruling_row": <ledger n of the ruling that
    makes it standing>, "reason": "<prose>"}`.

    This reader validates the SHAPE ONLY, deliberately. Whether `ruling_row` really names a
    `ruling` row and whether that row's resolution lands on `issue` is a question about the
    LEDGER, and the leg that holds the rows answers it — so a stale or mistyped entry is
    REFUSED there, printed with its reason, and the item stays OWED. Splitting it that way
    keeps this reader free of the ledger and keeps the refusal beside the population it
    affects.

    ABSENT is a legitimate state — a factory with no permanent-state item has declared none
    — and resolves nothing while saying so. MALFORMED is a DEFECT in a declaration that
    exists: an empty list, a non-integer issue, a non-positive `ruling_row` or an empty
    `reason` is a FAILURE, not a skip, because an empty declaration is the absent one
    wearing a key and it would excuse a whole population on no evidence at all.
    """
    path = repo / DECLARATION_REL
    if not path.is_file():
        raise DeclarationUnavailable(
            f"no {DECLARATION_REL} — a standing item is DECLARED factory data, and this "
            f"tree has declared none; the skeleton is {DECLARATION_EXAMPLE_REL}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} exists but cannot be read: {exc}"]) from exc
    except json.JSONDecodeError as exc:
        raise DeclarationUnreadable([f"{DECLARATION_REL} is not valid JSON: {exc}"]) from exc

    if not isinstance(payload, dict):
        raise DeclarationUnreadable([f"{DECLARATION_REL} must be a JSON object"])
    declared = payload.get("standing_items")
    if declared is None:
        raise DeclarationUnavailable(
            f"{DECLARATION_REL} declares no `standing_items` list — no permanent-state item "
            f"has been recorded in this factory, so there is nothing to resolve against; the "
            f"skeleton is {DECLARATION_EXAMPLE_REL}"
        )
    if not isinstance(declared, list):
        raise DeclarationUnreadable([
            f"{DECLARATION_REL}: `standing_items` must be a LIST of "
            f"{{issue, ruling_row, reason}} objects"
        ])
    if not declared:
        raise DeclarationUnreadable([
            f"{DECLARATION_REL}: `standing_items` is an EMPTY list — an empty declaration is "
            f"the absent one wearing a key, and it would excuse a population on no evidence"
        ])

    problems: list[str] = []
    items: dict[int, dict] = {}
    for index, entry in enumerate(declared):
        where = f"{DECLARATION_REL}: `standing_items[{index}]`"
        if not isinstance(entry, dict):
            problems.append(f"{where} must be an object")
            continue
        issue = entry.get("issue")
        if not isinstance(issue, int) or isinstance(issue, bool) or issue < 1:
            problems.append(f"{where}.issue must be a positive board issue number, found {issue!r}")
            continue
        ruling_row = entry.get("ruling_row")
        if not isinstance(ruling_row, int) or isinstance(ruling_row, bool) or ruling_row < 1:
            problems.append(
                f"{where}.ruling_row must be the positive ledger row number of the ruling "
                f"that makes #{issue} standing, found {ruling_row!r}"
            )
            continue
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(
                f"{where}.reason must be non-empty prose — an entry that cannot say why the "
                f"item is permanent state is not a declaration, it is a hole"
            )
            continue
        if issue in items:
            problems.append(
                f"{where}: #{issue} is declared twice — one item, one entry, so a reader can "
                f"tell which ruling makes it standing"
            )
            continue
        items[int(issue)] = {
            "issue": int(issue),
            "ruling_row": int(ruling_row),
            "reason": reason.strip(),
        }
    if problems:
        raise DeclarationUnreadable(problems)
    return items
