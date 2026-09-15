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
LEDGER_PATH = Path(os.environ.get("OC_LEDGER_PATH", REPO / "evidence" / "ledger.jsonl"))
ACTORS_FILE = Path(os.environ.get("OC_ACTORS_PATH", REPO / "tools" / "actors.txt"))

CORE_ACTORS = ("hq", "triage", "worker", "carrier", "owner")
EVENT_TYPES = ("genesis", "intake", "claim", "dispatch", "close", "score", "ruling", "run")
REQUIRED_FIELDS = {"n", "ts", "event", "actor", "subject", "detail"}

# Role-to-Event Authorization Matrix
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
    extra = row_keys - REQUIRED_FIELDS
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
        # Validate structured telemetry formats if present in detail
        for part in detail_val.split():
            if "=" in part:
                k, v = part.split("=", 1)
                if k in ("cost_usd", "cost"):
                    try:
                        val = float(v.rstrip("$"))
                        if val < 0:
                            errors.append(f"line {line_num}: cost cannot be negative: {v!r}")
                    except ValueError:
                        errors.append(f"line {line_num}: invalid numeric format for cost: {v!r}")
                elif k in ("tokens_in", "tokens_out", "in_tokens", "out_tokens", "turns"):
                    try:
                        val = int(v)
                        if val < 0:
                            errors.append(f"line {line_num}: count {k} cannot be negative: {v!r}")
                    except ValueError:
                        errors.append(f"line {line_num}: invalid integer format for {k}: {v!r}")

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
    """Audit the complete ledger file."""
    if not ledger_path.exists():
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

    return probes_passed


def main() -> int:
    # 1. Run internal self-probes
    if not run_self_probes():
        print("ledger schema gate self-probes FAILED", file=sys.stderr)
        return 1

    # 2. Audit live ledger
    row_count, errors = validate_ledger_file(LEDGER_PATH)
    if errors:
        print(f"ledger schema violations ({len(errors)} problem(s) in {LEDGER_PATH}):")
        for err in errors:
            print(f"  {err}")
        return 1

    print(f"ledger schema clean: {row_count} row(s) audited, all domain invariants & schemas verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
