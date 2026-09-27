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

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
LEDGER_REL = Path("evidence") / "ledger.jsonl"
LEDGER_PATH = Path(os.environ.get("OC_LEDGER_PATH", REPO / LEDGER_REL))
ACTORS_FILE = Path(os.environ.get("OC_ACTORS_PATH", REPO / "tools" / "actors.txt"))


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
from ledger_declaration import AUTHORIZED_ACTORS_BY_EVENT  # noqa: E402

ISO_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def get_known_actors() -> set[str]:
    actors = set(CORE_ACTORS)
    if ACTORS_FILE.exists():
        for line in ACTORS_FILE.read_text(encoding="utf-8").splitlines():
            role = line.split("#", 1)[0].strip()
            if role:
                actors.add(role)
    return actors


def validate_row_schema(row: dict[str, Any], line_num: int, known_actors: set[str]) -> list[str]:
    """Validate raw row structure, types, and schema boundaries."""
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
    if event_val not in EVENT_TYPES:
        errors.append(f"line {line_num}: unknown event type {event_val!r}, must be one of {EVENT_TYPES}")

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


def validate_domain_invariants(row: dict[str, Any], line_num: int) -> list[str]:
    """Validate domain entity class and role-to-event authorization invariants."""
    errors: list[str] = []
    event = row.get("event")
    actor = row.get("actor")
    subject = row.get("subject", "")

    # Role-to-event authorization check
    allowed_actors = AUTHORIZED_ACTORS_BY_EVENT.get(event, ())
    if actor and event and allowed_actors and actor not in allowed_actors:
        errors.append(
            f"line {line_num}: unauthorized actor '{actor}' for event '{event}' "
            f"(authorized: {', '.join(allowed_actors)})"
        )

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


def validate_ledger_file(ledger_path: Path) -> tuple[int, list[str]]:
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
        return 0, [f"ledger file not found: {ledger_path}"]

    known_actors = get_known_actors()
    errors: list[str] = []
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
        errors.extend(validate_domain_invariants(row, idx))

    return len(lines), errors


def evaluate(repo: Path) -> tuple[str, str, list[str]]:
    """`(status, reason, problems)` over `repo` — the core, so probes can drive it.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip: the
    skip is raised from the LOADER, so it can only fire where there is no ledger to judge,
    and never suppresses a defect the audit would have found.
    """
    try:
        row_count, errors = validate_ledger_file(repo / LEDGER_REL)
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
    # Probe 5: Unauthorized actor for ruling (e.g. worker issuing a ruling)
    assert_probe(
        "unauthorized ruling actor",
        {"n": 1, "ts": "2026-09-12T10:00:00Z", "event": "ruling", "actor": "worker", "subject": "#1", "detail": "d"},
        "unauthorized actor 'worker' for event 'ruling'",
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
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        # (i) A tree that ships no `evidence/` BY DESIGN -> SKIP, with the reason STATED.
        #     THIS IS ALSO THE MUTATION CONTROL: revert the loader's by-design branch to
        #     `return 0, [f"ledger file not found: …"]` and this probe REDs, because the
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

    return probes_passed


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
        row_count, errors = validate_ledger_file(LEDGER_PATH)
    except SkipGate as exc:
        print(f"ledger schema gate SKIPPED: {exc}")
        return 0

    if errors:
        print(f"ledger schema violations ({len(errors)} problem(s) in {LEDGER_PATH}):")
        for err in errors:
            print(f"  {err}")
        return 1

    print(f"ledger schema clean: {row_count} row(s) audited, all domain invariants & schemas verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
