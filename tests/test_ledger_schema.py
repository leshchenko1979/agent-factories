#!/usr/bin/env python3
"""Gate: Domain Object Class Schema & Lifecycle Invariant Validator.

Upholds the Domain Entity Model and Ledger Integrity Law.
Validates that every event in `evidence/ledger.jsonl`:
1. Adheres to the strict 6-field schema (no extra or missing keys).
2. Has valid primitive types, monotonic n, and ISO-8601 UTC timestamps.
3. Maps to a valid Domain Object Class (WorkUnit, ProcessRun, MeasurementScore, Ruling, Dispatch, Genesis).
4. Respects Role-to-Event authorization invariants (e.g., rulings only by hq/owner).
5. Carries structured detail appropriate to the event kind.

Run:  python3 tests/test_ledger_schema.py
Exit: 0 clean, 1 schema or domain invariant violation.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
LEDGER_REL = Path("evidence") / "ledger.jsonl"
LEDGER_PATH = Path(os.environ.get("OC_LEDGER_PATH", REPO / LEDGER_REL))

# FACTORY DATA, never inline in this gate (#156). This file is a declared PAIR, so a
# factory's own row numbers must not ship to every new factory; the skeleton that
# ships is the `.example.json` beside it. Absent means "this factory declared none".
EXEMPTIONS_REL = Path("docs") / "ledger-schema-exemptions.json"
ACTORS_FILE = Path(os.environ.get("OC_ACTORS_PATH", REPO / "tools" / "actors.txt"))
AUTHORIZATIONS_FILE = Path(
    os.environ.get("OC_AUTHORIZATIONS_PATH", REPO / "docs" / "ledger-authorizations.json")
)


class SkipGate(Exception):
    """This tree ships no `evidence/` BY DESIGN — a STATED skip, never a silent pass.

    The ledger is BOOTSTRAP-created (`TEMPLATE/BOOTSTRAP.md` step 4b), so the tree the kit
    SHIPS has no `evidence/` at all, and a gate that reds there is red on the very tree it
    ships to (#78, #76's class). `n=515` clause 4(a) already ruled the contract: *"the
    reader must tolerate an absent or empty ledger by SKIPPING WITH A STATED REASON, never
    raising"*. `tests/test_close_row_revision.py` implements it for this class, and this
    gate was the outlier — it reported the absence as a VIOLATION, so `TEMPLATE/` carried
    a RED that no bootstrap step can clear.

    THE GUARD THAT MAKES IT SAFE, and the reason it is raised from the LOADER rather than
    returned early: the skip is for a tree that ships no `evidence/` BY DESIGN. A live
    tree that HAS the directory and has LOST its ledger is a real problem and still REDs —
    otherwise a missing live ledger hides behind "nothing to judge", which is the vacuity
    this clause exists to prevent. Raising from the loader also keeps the checks in front
    of it: a defect the audit would have found is never suppressed by a skip.
    """


# The ONE field predicate, shared with the other two call sites of this class
# (`tests/test_close_row_revision.py`, `tools/ledger.py`). Imported by module name, not
# by package path, so a tree that stages the tool into a throwaway `tools/` resolves it
# the same way — the shape `tools/ledger.py` already uses for `telemetry`.
sys.path.insert(0, str(REPO / "tools"))
from field_predicate import telemetry_problems  # noqa: E402
import ledger  # noqa: E402  # the WRITE PATH, for the convergence cases (#50/#53)

CORE_ACTORS = ("hq", "triage", "worker", "carrier", "owner")
# The CORE events. A factory's OWN events are declared, and they are read from the SAME
# declaration file the write path reads, through the SAME env seam -- because a gate that
# refuses what the tool lawfully wrote is worse than no gate: the member learns that its
# declared vocabulary is unlawful at the exact moment the tool told it otherwise.
# Measured 2026-09-27 on inferhub-watch: `tools/ledger.py verify` accepted its 8
# `ack` rows once they were declared, while this tuple still red them.
_CORE_EVENT_TYPES = ("genesis", "intake", "claim", "dispatch", "close", "score", "ruling", "run")
_REFS_KINDS_FILE = Path(os.environ.get("OC_REFS_KINDS_PATH", REPO / "docs" / "ledger-refs-kinds.json"))


def _declared_events() -> tuple[str, ...]:
    try:
        _d = json.loads(_REFS_KINDS_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple(e for e in (_d.get("events") or []) if isinstance(e, str))


EVENT_TYPES = _CORE_EVENT_TYPES + tuple(
    e for e in _declared_events() if e not in _CORE_EVENT_TYPES)
REQUIRED_FIELDS = {"n", "ts", "event", "actor", "subject", "detail"}
# THE DECLARED EXTENSION SURFACE, widened in the SAME change as the write path that
# emits it, so the gate never refuses what the tool lawfully writes. Additive and
# OPTIONAL: a six-key row stays valid, so the forked copies are not broken on day one.
#   refs    -- typed pointers from this row to another object
#   session -- the writing lane's session id: attribution beside the actor's capacity
OPTIONAL_FIELDS = {"refs", "session"}

# Role-to-Event Authorization Matrix — imported from its ONE home
# (`tools/ledger_declaration.py`), which the write path reads too. While this gate held the
# only copy, `append` could not consult it, so an unauthorized row was written silently and
# reported here a day later: the blind spot was exactly one audit wide by construction.
import ledger_declaration  # noqa: E402  # the matrix's ONE home (identity pin)
from ledger_declaration import authorized_for_event, load_authorizations  # noqa: E402

ISO_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def get_known_actors() -> set[str]:
    """The core roles, plus any this factory DECLARES -- both declaration surfaces.

    `tools/actors.txt` names the lanes this factory has; `docs/ledger-authorizations.json`
    names what each may write, and its `actors` list is membership's second half. While this
    gate read the txt alone, `tools/ledger.py::known_actors()` unioned BOTH, so a lane the
    declaration admits was accepted by `append` and refused HERE -- a gate refusing what the
    instrument lawfully wrote, which is a red no lane can clear by doing the right thing.
    Measured when it landed: this factory's four commissioned lanes (#193) wrote lawful rows
    that the write path took and this gate rejected with `unknown actor 'ledger'`.

    Read through the SAME loader the write path uses, so the two cannot drift: one predicate,
    one home. A malformed declaration RAISES rather than reading as none.
    """
    actors = set(CORE_ACTORS)
    if ACTORS_FILE.exists():
        for line in ACTORS_FILE.read_text(encoding="utf-8").splitlines():
            role = line.split("#", 1)[0].strip()
            if role:
                actors.add(role)
    declared, _ = load_authorizations(REPO)
    actors.update(declared)
    return actors


def validate_row_schema(
    row: dict[str, Any],
    line_num: int,
    known_actors: set[str],
    event_types: tuple[str, ...] | None = None,
) -> list[str]:
    """Validate raw row structure, types, and schema boundaries.

    `event_types` is the SEAM that makes the one-home property PROVABLE (#53,
    promoted from miidas 2026-09-28). It defaults to the declaration this gate
    consumes, so the live audit is byte-for-byte unchanged; a caller may pass the
    OLD private copy to demonstrate that the shape #53 removed really does reject a
    row the shipped writer accepts. Without the parameter the divergence is
    describable but not demonstrable -- which is how it survived unnoticed.
    """
    vocabulary = EVENT_TYPES if event_types is None else event_types
    errors: list[str] = []

    # 1. Field completeness & strictness
    row_keys = set(row.keys())
    missing = REQUIRED_FIELDS - row_keys
    if missing:
        errors.append(f"line {line_num}: missing required field(s): {', '.join(sorted(missing))}")
    extra = row_keys - REQUIRED_FIELDS - OPTIONAL_FIELDS
    if extra:
        errors.append(f"line {line_num}: unknown field(s) in schema: {', '.join(sorted(extra))}")

    # 2. Field types and primitive invariants
    n_val = row.get("n")
    if not isinstance(n_val, int) or n_val < 1:
        errors.append(f"line {line_num}: 'n' must be a positive integer >= 1, got {n_val!r}")
    elif n_val != line_num:
        errors.append(f"line {line_num}: non-monotonic sequence: n={n_val}, expected {line_num}")

    ts_val = row.get("ts")
    if not isinstance(ts_val, str) or not ISO_TIMESTAMP_RE.match(ts_val):
        errors.append(f"line {line_num}: 'ts' must be ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ), got {ts_val!r}")
    else:
        try:
            datetime.strptime(ts_val, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            errors.append(f"line {line_num}: invalid calendar timestamp in 'ts': {exc}")

    event_val = row.get("event")
    if event_val not in vocabulary:
        errors.append(f"line {line_num}: unknown event type {event_val!r}, must be one of {vocabulary}")

    actor_val = row.get("actor")
    if actor_val not in known_actors:
        errors.append(f"line {line_num}: unknown actor {actor_val!r}, must be one of {sorted(known_actors)}")

    subject_val = row.get("subject")
    if not isinstance(subject_val, str) or not subject_val.strip():
        errors.append(f"line {line_num}: 'subject' must be a non-empty string, got {subject_val!r}")

    detail_val = row.get("detail")
    if not isinstance(detail_val, str) or not detail_val.strip():
        errors.append(f"line {line_num}: 'detail' must be a non-empty string, got {detail_val!r}")
    else:
        # Validate the telemetry this row DECLARES, never what it merely MENTIONS. A
        # row that QUOTES a trailer as evidence is prose about a field, not a statement
        # of one, and the old reader parsed the whole detail so a quotation could red
        # the audit (n=561). Scoped to the canonical trailer by the shared predicate
        # (#88; ledger n=405 clause 5) — see tools/field_predicate.py.
        errors.extend(
            f"line {line_num}: {problem}" for problem in telemetry_problems(detail_val)
        )

    return errors


def unauthorized_actor_error(row: dict[str, Any], line_num: int) -> str | None:
    """The GOVERNED class, as ONE predicate — the exemption surface keys on this.

    A second copy of this test would let the exemption and the violation drift apart,
    which is the one-field-one-predicate defect: an exemption that matched a string the
    gate no longer emits would excuse nothing while reading as coverage.
    """
    event = row.get("event")
    actor = row.get("actor")
    allowed_actors = authorized_for_event(REPO, event)
    if actor and event and allowed_actors and actor not in allowed_actors:
        return (
            f"line {line_num}: unauthorized actor '{actor}' for event '{event}' "
            f"(authorized: {', '.join(allowed_actors)})"
        )
    return None


def validate_domain_invariants(row: dict[str, Any], line_num: int) -> list[str]:
    """Validate domain entity class and role-to-event authorization invariants."""
    errors: list[str] = []
    event = row.get("event")
    subject = row.get("subject", "")

    # Role-to-event authorization check — read through the shared predicate above.
    unauthorized = unauthorized_actor_error(row, line_num)
    if unauthorized:
        errors.append(unauthorized)

    # Domain Entity Class Invariants
    if event == "genesis":
        if not (subject.endswith(".jsonl") or subject.endswith(".md") or "ledger" in subject):
            errors.append(f"line {line_num}: genesis subject must name a state surface, got {subject!r}")

    elif event in ("intake", "claim", "close"):
        # For issue/task work units, subjects typically begin with '#' or name a clear task identifier
        if not subject:
            errors.append(f"line {line_num}: {event} requires a valid subject entity identifier")

    elif event == "score":
        if not (subject.startswith("survey-") or subject.startswith("fleet-measurement-") or "score" in subject or "audit" in subject):
            errors.append(f"line {line_num}: score event subject must name a measurement run, got {subject!r}")

    return errors


def load_exemptions(repo: Path) -> tuple[list[dict], list[str]]:
    """`(entries, load_errors)` for this factory's schema exemptions.

    Three readings, and they are NOT the same (#156, following the five precedents):
      * ABSENT file -> none declared, which is the shipped state of a new factory;
      * a file that exists and cannot be READ -> a reported problem, because only the
        silent failure is the hazard;
      * a file whose shape is wrong -> a reported problem, never a silent pass.
    """
    path = repo / EXEMPTIONS_REL
    if not path.is_file():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [
            f"{EXEMPTIONS_REL}: cannot be read ({exc}) — an exemption file that cannot be "
            f"read is a reported problem, never a silent pass"
        ]
    if not isinstance(data, dict):
        return [], [f"{EXEMPTIONS_REL}: must be a JSON object carrying an `exempt` array"]
    entries = data.get("exempt")
    if entries is None:
        return [], []
    if not isinstance(entries, list):
        return [], [f"{EXEMPTIONS_REL}: `exempt` must be an array of entries"]
    return entries, []


def validate_ledger_file(ledger_path: Path) -> tuple[int, list[str], list[str]]:
    """Audit the complete ledger file, or `SkipGate` when the tree ships none BY DESIGN.

    The absence has two shapes and they are NOT the same reading:
      * the `evidence/` directory ITSELF is absent — the kit's own tree, where the ledger
        is bootstrap-created and there is legitimately nothing to audit yet -> SKIP, with
        the reason stated;
      * the directory is PRESENT and the ledger is gone — a live factory that lost it,
        which is a real problem -> a violation, exactly as before.

    Collapsing the two is the vacuity this split exists to prevent: a live tree that has
    lost its ledger must never read as "nothing to judge".
    """
    if not ledger_path.is_file():
        if not ledger_path.parent.is_dir():
            raise SkipGate(
                f"no {LEDGER_REL} in this tree — the ledger is BOOTSTRAP-created, so there "
                f"is nothing to audit yet (BOOTSTRAP.md step 4b creates it)"
            )
        return 0, [f"ledger file not found: {ledger_path}"], []

    known_actors = get_known_actors()
    entries, load_errors = load_exemptions(ledger_path.parent.parent)
    errors: list[str] = list(load_errors)
    excused: list[str] = []
    matched: set[int] = set()
    lines = ledger_path.read_text(encoding="utf-8").splitlines()

    for idx, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            errors.append(f"line {idx}: empty line in ledger (ledger must be contiguous newline-delimited JSON)")
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {idx}: malformed JSON: {exc}")
            continue

        if not isinstance(row, dict):
            errors.append(f"line {idx}: row must be a JSON object, got {type(row).__name__}")
            continue

        errors.extend(validate_row_schema(row, idx, known_actors))
        row_errors = validate_domain_invariants(row, idx)

        # The exemption governs EXACTLY the unauthorized-actor class, keyed by the row's
        # own `n` — `n` is row identity and immutable, which is what makes the key stable
        # across a re-read. It is applied only to that one class: an entry must never
        # excuse a malformed row, because the repair space for a schema error is not empty.
        governed = unauthorized_actor_error(row, idx)
        n = row.get("n")
        if governed is not None and isinstance(n, int):
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("n") != n:
                    continue
                if not entry.get("proof"):
                    errors.append(
                        f"{EXEMPTIONS_REL}: entry n={n} is not admittable — `proof` is blank, "
                        f"so it excuses nothing (name the external receipt that admits it)"
                    )
                    break
                excused.append(
                    f"n={n} unauthorized actor — {entry.get('reason', 'no reason stated')} "
                    f"[{entry.get('proof')}]"
                )
                matched.add(n)
                row_errors = [e for e in row_errors if e != governed]
                break

        errors.extend(row_errors)

    # An entry that matched no governed row is a gate ERROR: an exemption list that
    # quietly excuses nothing is indistinguishable from no exemptions at all, and a
    # stale entry inflates the visible debt while admitting no defect.
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{EXEMPTIONS_REL}: entry {i} is not a JSON object")
            continue
        n = entry.get("n")
        if not isinstance(n, int):
            errors.append(f"{EXEMPTIONS_REL}: entry {i} has no integer `n` — the key is the row's own number")
            continue
        if n not in matched:
            errors.append(
                f"{EXEMPTIONS_REL}: entry n={n} matches no governed row in this ledger — an "
                f"exemption that excuses nothing is a stale entry, not a pass"
            )

    return len(lines), errors, excused


def evaluate(repo: Path) -> tuple[str, str, list[str]]:
    """`(status, reason, problems)` over `repo` — the core, so probes can drive it.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip: the
    skip is raised from the LOADER, so it can only fire where there is no ledger to judge,
    and never suppresses a defect the audit would have found.
    """
    try:
        row_count, errors, _excused = validate_ledger_file(repo / LEDGER_REL)
    except SkipGate as exc:
        return "skip", str(exc), []
    if errors:
        return "fail", "", errors
    return "pass", f"{row_count} row(s) audited", []


def run_self_probes() -> bool:
    """Run internal test probes on synthetic invalid rows to ensure the gate catches violations."""
    known_actors = {"hq", "triage", "worker", "carrier", "owner", "surveys", "delegate"}
    probes_passed = True

    def assert_probe(name: str, row: dict, expected_err_substr: str, line_no: int = 1):
        nonlocal probes_passed
        errs = validate_row_schema(row, line_no, known_actors) + validate_domain_invariants(row, line_no)
        matched = any(expected_err_substr in e for e in errs)
        if not matched:
            print(f"  FAIL self-probe '{name}': expected error containing {expected_err_substr!r}, got: {errs}")
            probes_passed = False

    class _DeclarationPin:
        """Pin the authorization seam for a block, then restore it exactly.

        `load_authorizations` reads `OC_AUTHORIZATIONS_PATH` at CALL time, so the pin
        governs whatever runs inside the block and nothing outside it -- the isolation
        shape `OC_ACTORS_PATH` already provides for membership.
        """

        def __init__(self, path):
            self._path = path
            self._prev = None

        def __enter__(self):
            self._prev = os.environ.get("OC_AUTHORIZATIONS_PATH")
            if self._path is None:
                os.environ.pop("OC_AUTHORIZATIONS_PATH", None)
            else:
                os.environ["OC_AUTHORIZATIONS_PATH"] = str(self._path)
            return self

        def __exit__(self, *exc):
            if self._prev is None:
                os.environ.pop("OC_AUTHORIZATIONS_PATH", None)
            else:
                os.environ["OC_AUTHORIZATIONS_PATH"] = self._prev
            return False

    def assert_clean(name: str, row: dict, line_no: int = 1):
        """The inverse probe: a row declaring nothing malformed must produce NO error.

        The class's first direction needs this shape. Its measured defect was a FALSE
        RED — a row quoting a trailer was read as declaring it — and a probe that can
        only assert an error cannot catch a false red (#88, ledger n=405 clause 5).
        """
        nonlocal probes_passed
        errs = validate_row_schema(row, line_no, known_actors) + validate_domain_invariants(row, line_no)
        if errs:
            print(f"  FAIL self-probe '{name}': expected no error, got: {errs}")
            probes_passed = False

    # Probe 0: the DECLARED-ACTOR arm, both ways, against the REAL actor set.
    #
    # The fixture set below is a literal, so a probe using it cannot tell a declaration READ
    # from a hardcoded tuple -- which is exactly how the defect survived: the gate's own
    # vocabulary was consistent with itself and disagreed with the write path. This arm reads
    # `get_known_actors()` and asserts BOTH directions, so neither a constant nor an empty
    # declaration can pass it. Where a tree declares nothing beyond the core (the TEMPLATE
    # half does not), it SKIPS with that reason rather than passing vacuously.
    real_actors = get_known_actors()
    beyond_core = sorted(real_actors - set(CORE_ACTORS))
    if not beyond_core:
        print("  note self-probe 'declared actor admitted': this tree declares no actor beyond "
              "the core, so the declaration-read arm SKIPS rather than passing vacuously")
    else:
        role = beyond_core[0]
        declared_row = {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "run", "actor": role,
                        "subject": "#1", "detail": "d"}
        errs = validate_row_schema(declared_row, 1, real_actors)
        if errs:
            print(f"  FAIL self-probe 'declared actor admitted': {role!r} is DECLARED but the "
                  f"gate refuses it: {errs}")
            probes_passed = False
        errs_without = validate_row_schema(declared_row, 1, real_actors - {role})
        if not any("unknown actor" in e for e in errs_without):
            print(f"  FAIL self-probe 'declared actor refused when undeclared': dropping "
                  f"{role!r} from the set did NOT refuse it, so the arm above proves nothing: "
                  f"{errs_without}")
            probes_passed = False

    # Probe 1: Missing required field
    assert_probe(
        "missing field",
        {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "intake", "actor": "triage", "subject": "#1"},
        "missing required field(s): detail",
    )
    # Probe 2: Extra unknown field
    assert_probe(
        "extra field",
        {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "intake", "actor": "triage", "subject": "#1", "detail": "d", "extra_col": 123},
        "unknown field(s) in schema: extra_col",
    )
    # Probe 3: Invalid timestamp format
    assert_probe(
        "bad ts",
        {"n": 1, "ts": "2026-09-12 10:00:00", "event": "intake", "actor": "triage", "subject": "#1", "detail": "d"},
        "'ts' must be ISO-8601 UTC",
    )
    # Probe 4: Non-monotonic n
    assert_probe(
        "non-monotonic n",
        {"n": 5, "ts": "2026-09-12T10:00:00Z", "event": "intake", "actor": "triage", "subject": "#1", "detail": "d"},
        "non-monotonic sequence",
        line_no=1,
    )
    # Probe 5: Unauthorized actor for ruling (e.g. worker issuing a ruling).
    #
    # THIS PROBE PINS THE CORE MATRIX, and it must, because the pair it asserts is one a
    # declaration may LAWFULLY grant. `docs/ledger-authorizations.json` exists so a factory
    # can ADD to the core matrix (additive; the constant stays the floor), so in a tree that
    # declared `ruling` for `worker` this probe asserted a default the declaration is designed
    # to change and red the gate -- refusing what the tool lawfully wrote, at the exact moment
    # the tool told the factory to make the declaration. Measured 2026-09-27 on inferhub-watch:
    # it declared that pair (self-corrections of its own prior rows) and this gate returned
    # rc=1 with this probe's message. Same discipline as Probe 0, which states it reads the
    # REAL actor set: a probe must say which world it asserts in.
    _absent = REPO / "docs" / ".probe-no-authorizations.json"
    with _DeclarationPin(_absent):
        assert_probe(
            "unauthorized ruling actor",
            {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "ruling", "actor": "worker", "subject": "#1", "detail": "d"},
            "unauthorized actor 'worker' for event 'ruling'",
        )

    # Probe 5b: THE DECLARED ARM -- the extension surface itself, proven rather than assumed.
    # A probe that can only assert the default cannot tell "no declaration" from "a declaration
    # that extends the default", which is precisely the failure measured above. Declaring the
    # pair must make the SAME row clean, and the seam is the only thing that changed.
    with tempfile.TemporaryDirectory() as _td:
        _decl = Path(_td) / "authorizations.json"
        _decl.write_text(json.dumps({"actors": [], "by_event": {"ruling": ["worker"]}}), encoding="utf-8")
        with _DeclarationPin(_decl):
            assert_clean(
                "declared ruling actor",
                {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "ruling", "actor": "worker", "subject": "#1", "detail": "d"},
            )
    # Probe 6: Invalid cost format
    assert_probe(
        "bad cost format",
        {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "intake", "actor": "triage", "subject": "#1", "detail": "cost_usd=invalid"},
        "invalid numeric format for cost",
    )
    # Probes 7-9: the prose-as-data class (#88, ledger n=405 clause 5). A row's
    # telemetry is what it DECLARES in its canonical trailer — the run of `key=value`
    # tokens at the END of the detail (SKILL.md section 11) — never what it MENTIONS
    # elsewhere. The old reader parsed the whole detail, so prose could satisfy a field.
    #
    # Probe 7: the live FALSE RED. n=561 is an intake row that QUOTES n=554's trailer as
    # evidence; the old reader validated the quotation and reddened the audit on a row
    # that declares nothing malformed. Prose must not SATISFY a field.
    assert_clean(
        "a quoted trailer is prose, not a declaration",
        {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "intake", "actor": "triage",
         "subject": "#88",
         "detail": "the row's trailer ends '...board=closed; rework=unstated cost_usd=1.9225 "
                   "tokens_in=... turns=36' with NO head= field, and the gate names the row"},
    )
    # Probe 8: the gate must still BITE. The same malformed value in TRAILER position is
    # a declaration, and a declaration that does not parse is reported.
    assert_probe(
        "a malformed value in the trailer is still reported",
        {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "close", "actor": "worker",
         "subject": "#88",
         "detail": "Closed. Receipts taken at head=deadbeef985b0f1a6c8919c362a0a56ec7d0d42e "
                   "outcome=accepted turns=abc"},
        "invalid integer format for turns",
    )
    # Probe 9: a bare key in TRAILER position is still a MENTION, not a declaration. This
    # is the shape that reddened the audit before the shared predicate existed —
    # `'line 399: invalid integer format for tokens_out: ""'` — because an empty value was
    # read as a malformed one rather than as no value at all.
    assert_clean(
        "an empty value is a mention, not a malformed declaration",
        {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "close", "actor": "worker",
         "subject": "#88", "detail": "Closed. gate=all-pass outcome=accepted tokens_out="},
    )

    # ── The absence contract (n=515 clause 4(a); #83's class) ──────────────────────────
    # A gate that RAISED on an absent ledger was RED on the very tree it ships to, because
    # the ledger is BOOTSTRAP-created and `TEMPLATE/` carries no `evidence/` at all. BOTH
    # directions are pinned below: a skip that swallowed a REAL absence would be the vacuity
    # this clause exists to prevent, so the guard is probed as hard as the skip.

    with tempfile.TemporaryDirectory() as tmp:
        # (i) A tree that ships no `evidence/` BY DESIGN -> SKIP, with the reason STATED.
        #     THIS IS ALSO THE MUTATION CONTROL: revert the loader's by-design branch to
        #     `return 0, [f"ledger file not found: …"], []` and this probe REDs, because the
        #     status becomes "fail" where a skip is owed.
        bare = Path(tmp) / "ships-no-evidence"
        bare.mkdir()
        status, reason, problems = evaluate(bare)
        if status != "skip" or problems:
            print(f"  FAIL self-probe 'a tree shipping no evidence/ skips': "
                  f"got status={status!r} problems={problems}")
            probes_passed = False
        elif not (str(LEDGER_REL) in reason and "BOOTSTRAP" in reason):
            print(f"  FAIL self-probe 'the skip STATES its reason': reason={reason!r} does "
                  f"not name {str(LEDGER_REL)!r} and BOOTSTRAP")
            probes_passed = False

        # (i-b) The MECHANISM, not merely the status: the loader must RAISE. A control that
        #       only read `evaluate`'s status could pass under a loader that returned a
        #       violation and an evaluator that mapped it to "skip" — this pins the loader.
        try:
            validate_ledger_file(bare / LEDGER_REL)
        except SkipGate:
            pass
        else:
            print("  FAIL self-probe 'the loader RAISES SkipGate for a by-design tree': it "
                  "returned instead, so the skip is not raised from the loader")
            probes_passed = False

        # (ii) THE VACUITY GUARD. A live tree that HAS `evidence/` and lost its ledger is a
        #      real problem: it must still RED, never read as "nothing to judge".
        lost = Path(tmp) / "lost-its-ledger"
        (lost / "evidence").mkdir(parents=True)
        status, reason, problems = evaluate(lost)
        if status != "fail" or not problems:
            print(f"  FAIL self-probe 'a live tree that LOST its ledger still reds': "
                  f"got status={status!r} problems={problems}")
            probes_passed = False

        # EVERY PROBE BELOW VALIDATES A SYNTHETIC TREE, so every one must pin the authorization
        # seam. The pin is ONE wrap around the block, not five, because the leak is the block's
        # shared premise rather than any single arm.
        #
        # `member_tree()` builds a 2-row fixture whose row 2 is an UNAUTHORIZED intake (`worker`
        # filing `intake`). That unauthorized-ness is the fixture's premise, and every arm below
        # tests the exemption surface AGAINST IT: a proven entry excuses it, a malformed one
        # errors, a stale one is named, a proofless one refuses by name. But the authorization
        # set does not come from the tree under test: `validate_ledger_file()` calls
        # `load_authorizations(REPO)` on the MODULE-level `REPO`, while `load_exemptions()` two
        # lines later reads the tree under test — so one function holds two authorities
        # and they disagree by construction. A factory that LAWFULLY declared `intake` for
        # `worker` — which is exactly what the seam ships to allow — therefore
        # authorized the fixture's row: it stopped being governed, the exemption keyed to it
        # matched nothing, and three probes red on `matches no governed row`.
        #
        # Measured 2026-09-27 on inferhub-watch, which declared both `ruling` and `intake` for
        # `worker` (13 of its rows file their own issues) and got rc=1 WITH the declaration and
        # rc=1 WITHOUT it: the gate could not be green in that tree either way. Same class as the
        # probe-5 defect fixed an hour earlier, one probe deeper, and invisible here for the same
        # reason — this factory's declaration grants `claim`/`close`/`run` and never
        # `intake`, so the fixture's row stayed unauthorized in the tree that authored the gate.
        #
        # The pin is `_absent`, NOT `None`: `_DeclarationPin(None)` POPS the variable and
        # `load_authorizations` then falls back to the real `REPO/docs/...json`, which IS the
        # leak. An absent path is what means NONE. Corrected against the fix shape the reporting
        # lane proposed; its parenthetical alternative was the right one.
        #
        # The MEMBERSHIP seam needs no pin and must not be given one, which is a structural fact
        # rather than an omission: `ACTORS_FILE` is bound at IMPORT (line 35), so a per-block pin
        # could not reach it. It does not need to. `known_actors()` is core UNION declared and
        # `load_authorizations` is additive-only, so membership can grow but never shrink, and a
        # fixture whose actors are all CORE (`triage`, `worker`) is unaffected by whatever a
        # factory adds. Additive-only is what makes this safe; a declaration that could REMOVE a
        # core actor would break it, which is why the floor is a constant and not a default.

        with _DeclarationPin(_absent):
            # (iii) THE EXEMPTION SURFACE (#156). The governed class is the unauthorized-actor
            #       violation, keyed by the row's own `n`. Every arm is driven from a
            #       CONSTRUCTED fixture, never from prose that happens to be in this ledger —
            #       this factory's own ledger carries no such row, so a probe reading it would
            #       pass vacuously.
            def member_tree(name: str, exempt: object) -> Path:
                """A member-shaped tree: a 2-row ledger whose row 2 is an unauthorized intake."""
                tree = Path(tmp) / name
                (tree / "evidence").mkdir(parents=True)
                (tree / "docs").mkdir()
                rows = [
                    {"n": 1, "ts": "2026-09-24T10:00:00Z", "event": "intake", "actor": "triage",
                     "subject": "#41", "detail": "clean row"},
                    {"n": 2, "ts": "2026-09-24T10:01:00Z", "event": "intake", "actor": "worker",
                     "subject": "#42", "detail": "the member's unauthorized row"},
                ]
                (tree / "evidence" / "ledger.jsonl").write_text(
                    "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
                if exempt is not None:
                    (tree / "docs" / "ledger-schema-exemptions.json").write_text(
                        json.dumps(exempt), encoding="utf-8")
                return tree

            # (b) A PROVEN entry excuses the violation, the run passes, and the excused line
            #     is PRINTED — a clean verdict and an excused one must not be the same output.
            proven = member_tree("exempt-proven", {"exempt": [{
                "n": 2, "subject": "#42", "granted": "2026-09-26",
                "reason": "row written before the actor matrix existed",
                "proof": "the ruling that granted it: ledger n=1026"}]})
            count, errs, exc = validate_ledger_file(proven / LEDGER_REL)
            if errs or len(exc) != 1 or "n=2" not in exc[0]:
                print(f"  FAIL self-probe 'a PROVEN entry excuses the governed row and prints it': "
                      f"errors={errs} excused={exc}")
                probes_passed = False

            # (c) A MALFORMED entry is a gate ERROR, never a silent pass.
            for label, bad in (("no integer n", {"exempt": [{"subject": "#42"}]}),
                               ("not an object", {"exempt": ["n=2"]})):
                count, errs, exc = validate_ledger_file(
                    member_tree("exempt-bad-%s" % label.split()[0], bad) / LEDGER_REL)
                if not errs:
                    print(f"  FAIL self-probe 'a malformed entry ({label}) is a gate ERROR': "
                          f"got no errors")
                    probes_passed = False

            # (d) An entry matching NO governed row is a gate ERROR — a stale exemption
            #     inflates the visible debt while admitting no defect.
            stale = member_tree("exempt-stale", {"exempt": [{
                "n": 99, "subject": "#99", "granted": "2026-09-26", "reason": "gone",
                "proof": "ledger n=1026"}]})
            count, errs, exc = validate_ledger_file(stale / LEDGER_REL)
            if not any("matches no governed row" in e for e in errs):
                print(f"  FAIL self-probe 'an entry matching no governed row is a gate ERROR': "
                      f"errors={errs}")
                probes_passed = False

            # (e) A BLANK proof is refused BY NAME and excuses nothing — the violation stands.
            #     Both directions are probed: a proofless entry must not pass, and the refusal
            #     must name the entry that failed to excuse it.
            proofless = member_tree("exempt-proofless", {"exempt": [{
                "n": 2, "subject": "#42", "granted": "2026-09-26",
                "reason": "no receipt", "proof": ""}]})
            count, errs, exc = validate_ledger_file(proofless / LEDGER_REL)
            if exc or not any("not admittable" in e for e in errs):
                print(f"  FAIL self-probe 'a proofless entry excuses nothing and is named': "
                      f"errors={errs} excused={exc}")
                probes_passed = False
            if not any("unauthorized actor" in e for e in errs):
                print(f"  FAIL self-probe 'and the violation itself still stands': errors={errs}")
                probes_passed = False

            # (f) The exemption governs ONE class only. A malformed row that is ALSO
            #     unauthorized must not have its schema error excused by an entry keyed to it.
            mixed = member_tree("exempt-mixed", {"exempt": [{
                "n": 2, "subject": "#42", "granted": "2026-09-26", "reason": "actor",
                "proof": "ledger n=1026"}]})
            (mixed / "evidence" / "ledger.jsonl").write_text(
                json.dumps({"n": 1, "ts": "2026-09-24T10:00:00Z", "event": "intake",
                            "actor": "triage", "subject": "#41", "detail": "d"}) + "\n"
                + json.dumps({"n": 2, "ts": "2026-09-24T10:01:00Z", "event": "intake",
                              "actor": "worker", "subject": "", "detail": "d"}) + "\n",
                encoding="utf-8")
            count, errs, exc = validate_ledger_file(mixed / LEDGER_REL)
            if not any("subject" in e for e in errs):
                print(f"  FAIL self-probe 'the exemption does not excuse a schema error on the "
                      f"same row': errors={errs}")
                probes_passed = False

        # THE PIN IS LOAD-BEARING, and this arm proves it rather than assuming it. Under a
        # declaration granting the fixture's own pair, the synthetic row stops being governed,
        # the exemption keyed to it matches nothing, and the stale-entry error surfaces on
        # demand. Without this arm the block would pass on a pin that pinned nothing — the
        # vacuous-green failure mode a fix inherits from the defect it repairs. Probe (b) above
        # is the converse arm under the pin; this is the mutation.
        with tempfile.TemporaryDirectory() as _td:
            _grant = Path(_td) / "authorizations.json"
            _grant.write_text(json.dumps({"actors": [], "by_event": {"intake": ["worker"]}}),
                                   encoding="utf-8")
            with _DeclarationPin(_grant):
                _c, _e, _x = validate_ledger_file(
                    member_tree("exempt-under-grant", {"exempt": [{
                        "n": 2, "subject": "#42", "granted": "2026-09-26",
                        "reason": "excused under a lawful grant",
                        "proof": "ledger n=1026"}]}) / LEDGER_REL)
            if not any("matches no governed row" in e for e in _e):
                print("  FAIL self-probe 'the authorization pin is load-bearing': errors=%s"
                        % (_e,))
                probes_passed = False
    return probes_passed


class TestVocabularyConvergence(unittest.TestCase):
    """The event vocabulary has ONE home: the tool declares it, the gate consumes it (#53).

    PROMOTED from miidas (2026-09-28), whose gate was 496 lines ahead of this one on the
    enforcement path. This class is the part of that lead which TRANSFERS; the exhaustive
    writer-vs-gate sweep is the part that does not, and the bound is recorded below it.

    The old shape gave the gate a private copy of the same eight names. They were
    identical, so nothing failed -- and the divergence would have surfaced silently on the
    first edit of either, in both directions. These cases DRIVE that shape rather than
    describing it: a real write through `cmd_append`, the row read back off disk, then this
    gate's own row validator run over it under each vocabulary.

    ADAPTED FOR THIS TREE, and the adaptation is the point: the writer here resolves a
    DERIVED actor on the live path and refuses every event but `genesis` when no lane
    binds, so these cases drive it through the FIXTURE seam (`OC_LEDGER_PATH`) -- the
    documented route by which a throwaway ledger names its own actors. Without it the
    probe cannot write at all and every case would be vacuously green.
    """

    PROBE_SUBJECT = "#42"

    def _undeclared_event(self) -> str:
        """An event the vocabulary does not carry -- DERIVED, never assumed.

        Hardcoding the name couples these cases to live state: admitting it to the
        declaration later breaks them for a reason unrelated to the defect. Ask the
        vocabulary for a free name instead.
        """
        name, i = "probe-event", 0
        while name in EVENT_TYPES:
            i += 1
            name = f"probe-event-{i}"
        return name

    @contextlib.contextmanager
    def _tool_declaring(self, events, table):
        """Temporarily widen the TOOL's declarations, then restore them.

        A coherent ninth event needs both: the writer refuses a declared event that has
        no table entry, so widening `EVENTS` alone is refused by the coupling #50 built.
        That is the realistic edit and the one a private gate copy was blind to.
        """
        real_events = ledger.EVENTS
        real_table = ledger.AUTHORIZED_ACTORS_BY_EVENT
        ledger.EVENTS, ledger.AUTHORIZED_ACTORS_BY_EVENT = events, table
        try:
            yield
        finally:
            ledger.EVENTS, ledger.AUTHORIZED_ACTORS_BY_EVENT = real_events, real_table

    def _writer_accepts(self, ledger_path: Path, event: str, actor: str) -> bool:
        ns = argparse.Namespace(
            event=event, actor=actor, subject=self.PROBE_SUBJECT, detail="vocabulary probe"
        )
        real_ledger, real_lock = ledger.LEDGER, ledger.LOCK
        prior = os.environ.get("OC_LEDGER_PATH")
        os.environ["OC_LEDGER_PATH"] = str(ledger_path)  # THE FIXTURE SEAM
        ledger.LEDGER = ledger_path
        ledger.LOCK = ledger_path.parent / ".ledger.lock"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                ledger.cmd_append(ns)
            return True
        except SystemExit:
            return False
        finally:
            ledger.LEDGER, ledger.LOCK = real_ledger, real_lock
            if prior is None:
                os.environ.pop("OC_LEDGER_PATH", None)
            else:
                os.environ["OC_LEDGER_PATH"] = prior

    def test_the_private_copy_reported_a_row_the_writer_had_written(self):
        """Direction 1: the tool's vocabulary gains an event; the gate's private copy does not."""
        with tempfile.TemporaryDirectory() as td:
            led = Path(td) / "ledger.jsonl"
            led.write_text("", encoding="utf-8")
            probe = self._undeclared_event()
            widened = EVENT_TYPES + (probe,)
            widened_table = dict(ledger.AUTHORIZED_ACTORS_BY_EVENT, **{probe: ("hq",)})

            with self._tool_declaring(widened, widened_table):
                self.assertTrue(
                    self._writer_accepts(led, probe, "hq"),
                    "premise: the widened tool must actually write the row",
                )

            # Read the row back off disk; do not construct one.
            rows = [
                json.loads(ln)
                for ln in led.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            self.assertEqual(len(rows), 1, "exactly one row should have been written")
            row = rows[0]
            self.assertEqual(row["event"], probe)
            known = set(ledger.known_actors())

            # The shape #53 removed: a private copy, equal to the tool's on the day it was
            # written. It rejects the row the writer just wrote.
            errs = validate_row_schema(row, 1, known, event_types=tuple(_CORE_EVENT_TYPES))
            self.assertTrue(
                any("unknown event type" in e for e in errs),
                f"the private copy must reject the row the writer accepted; got {errs}",
            )

            # Consuming the one declaration, the same row passes: no divergence is possible.
            self.assertEqual(
                validate_row_schema(row, 1, known, event_types=widened),
                [],
                "the gate consuming the tool's declaration must accept the row the tool wrote",
            )

    def test_a_gate_ahead_of_the_tool_is_refused_by_both(self):
        """Direction 2: a gate whose vocabulary ran AHEAD of the tool's.

        A row cannot reach the ledger by the shipped path while holding an event the
        writer refuses, so such a gate validated against a vocabulary the tool does not
        implement. Measured both ways: the unedited writer refuses the event, and the
        private copy passes a row carrying it.
        """
        with tempfile.TemporaryDirectory() as td:
            led = Path(td) / "ledger.jsonl"
            led.write_text("", encoding="utf-8")
            probe = self._undeclared_event()

            self.assertFalse(
                self._writer_accepts(led, probe, "hq"),
                "the unedited writer must refuse an undeclared event",
            )
            row = {
                "n": 1, "ts": "2026-09-01T00:00:00Z", "event": probe, "actor": "hq",
                "subject": self.PROBE_SUBJECT, "detail": "vocabulary probe",
            }
            errs = validate_row_schema(
                row, 1, set(ledger.known_actors()), event_types=tuple(_CORE_EVENT_TYPES)
            )
            self.assertTrue(
                any("unknown event type" in e for e in errs),
                f"a gate ahead of the tool must refuse the row the writer refuses; got {errs}",
            )

    # ------------------------------------------------------------------------------
    # THE BOUND, stated so a later reader does not graft the rest of miidas's lead and
    # then mute the reds. `TestWriterGateConvergence` asserts that the writer and the
    # gate return the SAME verdict for every (event, actor) pair. MEASURED 2026-09-28
    # against this write path, 8 events x 11 actors = 88 pairs: 21 agree, 67 disagree,
    # decomposing into three BY-DESIGN differences --
    #   45 pairs writer ACCEPT / gate REFUSE: the matrix binds a DERIVED actor only, so a
    #        fixture (which declares its actor) is authorized for everything membership
    #        permits, while the gate has no fixture concept;
    #   21 pairs writer REFUSE / gate ACCEPT: the writer enforces PREDECESSOR LEGS
    #        (claim needs an intake) and the gate validates a single row in isolation;
    #    1 pair  both refuse (claim/owner).
    # The premise holds in miidas's tree because its fork carries none of those three
    # predicates -- verified there: rc=0, 33 tests. It cannot hold here without deleting
    # the write path's identity law. The properties this tree CAN promise are asserted
    # above; the rest is a design difference, not a defect, and grafting it verbatim
    # would red 67 of 88 on a false premise.
    # ------------------------------------------------------------------------------


class TestDeclarations(unittest.TestCase):
    """The declaration's OWN properties -- the half of miidas's lead this tree lacked.

    Grafted from miidas's `tests/test_ledger_schema.py` (`TestDeclarations`), which guards
    a class the write-path cases above cannot reach: they exercise the WRITER, these
    exercise the OBJECTS it consults. None of the convergence cases above notices if the
    gate and the writer stop sharing ONE object, if the tool's core constants drift, or if
    the live vocabulary grows an event no authorized set covers.

    THAT LAST ONE IS SILENT BY CONSTRUCTION, and it is why this class exists: an event with
    no matrix entry authorizes NOBODY, so every row carrying it is refused by the writer --
    or, on an older write path that only checks membership, accepted while the reviewer
    checks nothing. Either way the declaration reads as coverage and is not. miidas named
    this shape in #50/#53.

    TWO RULES came with the graft, both miidas's, both now measured here:
      * a test's POPULATION comes from the POLICY, never from the universe under test --
        the pins below iterate `EVENT_TYPES` (the live vocabulary), so an event is covered
        the moment it is declared; iterating the TABLE would test only what the table
        already covers and pass on the day an event arrives without one.
      * a pin that cannot FAIL reads exactly like a pin that holds -- so the vacuity pin is
        paired with the mutation that must break it.
    """

    def test_the_matrix_has_one_home(self) -> None:
        """One OBJECT, not two equal copies: `is`, never `==`.

        Equality is satisfied the day two copies are written and drifts on the first edit
        of either. While this gate held its own copy, a declared authorization passed the
        tool and red the gate, so a member learned its lawful row was unlawful at the exact
        moment the tool told it otherwise.
        """
        self.assertIs(ledger.AUTHORIZED_ACTORS_BY_EVENT,
                      ledger_declaration.AUTHORIZED_ACTORS_BY_EVENT)

    def test_the_tool_declares_the_core_vocabulary(self) -> None:
        """The tool's core events are the eight this gate also hardcodes.

        The two constants are still two copies (`ledger.EVENTS` and `_CORE_EVENT_TYPES`),
        so this is the change-notice: it names WHICH direction a silent edit moved. It is
        the honest form of an `EXPECTED_EVENTS` delta -- the tool's OWN declaration is read
        rather than a third literal typed here.
        """
        self.assertEqual(tuple(ledger.EVENTS), tuple(_CORE_EVENT_TYPES),
                         "the tool's core event vocabulary moved away from this gate's")

    def test_the_tool_declares_the_core_actors(self) -> None:
        """The tool's core roles are the five this gate also assumes."""
        self.assertEqual(tuple(ledger.ACTORS), tuple(CORE_ACTORS),
                         "the tool's core actor vocabulary moved away from this gate's")

    def test_every_vocabulary_event_has_an_authorized_set(self) -> None:
        """THE VACUITY PIN: a vocabulary event that authorizes nobody is UNCHECKED.

        Population from the POLICY (`EVENT_TYPES`), never from the table under test. A
        factory declaring an event without authorizing anyone for it has declared a dead
        event: the writer refuses every actor, and no reviewer is looking.
        """
        unchecked = [e for e in EVENT_TYPES if not authorized_for_event(REPO, e)]
        self.assertEqual(
            unchecked, [],
            f"vocabulary event(s) with no authorized set, so no writer may emit them "
            f"and no reviewer checks them: {unchecked}",
        )

    def test_a_dropped_table_entry_is_visible(self) -> None:
        """The mutation that proves the pin above can FAIL.

        Without this arm, a pin that passes because the predicate is a no-op is
        indistinguishable from one that passes because the property holds.
        """
        # THE OBJECT MUTATED IS THE ONE `authorized_for_event` READS, and getting that
        # wrong is the whole trap: `ledger.AUTHORIZED_ACTORS_BY_EVENT` is a module-level
        # REBINDING of the same object, so assigning to it changes ledger's name only,
        # while the predicate does its own global lookup in `ledger_declaration`. The
        # first version of this arm rebound `ledger`'s name and reported the pin holding
        # -- a mutation that tested nothing, which is exactly what an arm like this is for.
        real = ledger_declaration.AUTHORIZED_ACTORS_BY_EVENT
        try:
            ledger_declaration.AUTHORIZED_ACTORS_BY_EVENT = {
                k: v for k, v in real.items() if k != "score"}
            unchecked = [e for e in EVENT_TYPES if not authorized_for_event(REPO, e)]
        finally:
            ledger_declaration.AUTHORIZED_ACTORS_BY_EVENT = real
        self.assertEqual(
            unchecked, ["score"],
            "the vacuity pin did not bite on a table entry dropped under it",
        )

    def test_the_writer_admits_every_role_this_gate_assumes(self) -> None:
        """Direction B, in the form that holds in EVERY tree.

        NOT asserted: "every authorized actor is known to the writer". The core table
        authorizes `delegate` and `surveys`, neither is in the core `ACTORS` tuple, and
        `TEMPLATE/tools/actors.txt` does not exist -- so that form would RED every factory
        on the day it is created, for a matrix that ships as core. What IS asserted is the
        direction that must never break: the writer admits every role this gate hardcodes,
        so the gate cannot be assuming a role the write path has never heard of.
        """
        known = set(ledger.known_actors())
        missing = [a for a in CORE_ACTORS if a not in known]
        self.assertEqual(
            missing, [],
            f"this gate assumes role(s) the writer cannot admit: {missing}",
        )


def run_case_suite() -> bool:
    """Run this file's `unittest` cases and report whether they all held.

    The gate is invoked as a SCRIPT (`python3 tests/test_ledger_schema.py`), so any
    `unittest.main()` in the `__main__` block never fires -- without this call every
    `TestCase` in this file is DEAD CODE THAT READS AS COVERAGE. That was the state of
    miidas's `TestLedgerSubjectLaw` (#28) until #30 wired it in, and it is why the
    promotion carries the runner and not only the cases.
    """
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main() -> int:
    # 1. Run internal self-probes — ALWAYS, and BEFORE the ledger read. The skip below is
    #    raised from the LOADER, so it can never stand in front of a defect these catch.
    if not run_self_probes():
        print("ledger schema gate self-probes FAILED", file=sys.stderr)
        return 1

    # 2. Audit live ledger. An absent `evidence/` is a STATED SKIP, never a violation: the
    #    ledger is bootstrap-created, and the tree the kit SHIPS has none (#78's class).
    #    A tree that HAS the directory and lost the ledger still reds — see SkipGate.
    try:
        row_count, errors, excused = validate_ledger_file(LEDGER_PATH)
    except SkipGate as exc:
        print(f"ledger schema gate SKIPPED: {exc}")
        if not run_case_suite():
            print("ledger schema gate case suite FAILED", file=sys.stderr)
            return 1
        return 0

    # Every MATCHING entry prints as an `excused:` line on EVERY run, and the closing
    # line distinguishes clean from excused, so the two are never the same output. An
    # exemption is a VISIBLE DEBT, not forgiveness.
    for line in excused:
        print(f"  excused: {line}")

    if errors:
        print(f"ledger schema violations ({len(errors)} problem(s) in {LEDGER_PATH}):")
        for err in errors:
            print(f"  {err}")
        return 1

    if excused:
        print(f"ledger schema clean, {len(excused)} excused: {row_count} row(s) audited, "
              f"all domain invariants & schemas verified")
    else:
        print(f"ledger schema clean: {row_count} row(s) audited, all domain invariants & schemas verified")
    if not run_case_suite():
        print("ledger schema gate case suite FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
