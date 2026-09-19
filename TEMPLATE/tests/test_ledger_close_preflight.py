#!/usr/bin/env python3
"""Gate: a close row is refused at the write path when its subject has no preceding intake and claim.

Origin (issue #98, ruling n=596). `tools/ledger.py verify` has always required a
subject's rows to read `intake -> claim -> close`. Nothing in the APPEND path required
it, so a lane could close a board item, post the receipt, and stamp the close row with
no claim row ever written — and the omission surfaced only on a later `verify` run,
after the board was already closed and the row was already in a SHARED file. Measured
twice: `#50` at `n=304` and `#86` at `n=589`, the second time with the invalid row
sitting uncommitted in the shared tree, where the next lane to stage the ledger would
have carried it into history with no act of its own.

A detector that fires only after the shared file is poisoned is not upholding at the
moment that matters, so the predicate moves to the WRITE PATH — ONE predicate, TWO call
sites. `verify` asks it about every close row in history; `append` asks it about the row
it is about to write, with `index = len(rows)`, the line that row will occupy.

What this gate asserts, and what it does NOT
--------------------------------------------
It asserts the REFUSAL: both legs (missing intake AND missing claim) are refused, the
refusal names the subject and the missing leg, and it writes NOTHING — byte-for-byte
nothing, not merely "no close row". It asserts the ACCEPTANCE: a close whose subject
carries both legs preceding it lands, and `verify` then reads that ledger clean.

It does NOT assert that a ledger can no longer CONTAIN a bad sequence. SKILL.md §11's
guarantee is one append path, not tamper-proof: a writer that never calls
`tools/ledger.py` takes no lock and this pre-flight never sees it. That residue stays
`verify`'s, and the last two probes pin it — a raw row written AROUND the append path is
still reported, both as a missing leg and as the order leg the pre-flight also refuses
at the write path.

The probes run against THROWAWAY ledgers through the `OC_LEDGER_PATH` seam
`tests/test_ledger.py` already uses. No probe reads `evidence/ledger.jsonl`.

Run:  python3 -m pytest tests/test_ledger_close_preflight.py -q
Exit: 0 clean; non-zero on any direction that fails.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ledger.py"
GATE_REL = "tests/test_ledger_close_preflight.py"
SUBJECT = "#probe-close"


def _empty_telemetry_db(path: Path) -> Path:
    """A throwaway telemetry source: the schema, and NO rows.

    `tools/telemetry.py:find_database_path()` FALLS BACK to the live OpenCrabs
    database when `OPENCRABS_DB_PATH` is set but does not resolve to a file, so
    pinning that variable to a missing path is not isolation at all — it is the
    live database by another route. The probe therefore seeds a real, empty
    database: the append reads it, finds no telemetry, and appends no trailer.
    """
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE messages (created_at INTEGER, cost REAL, input_tokens INTEGER, "
        "token_count INTEGER, role TEXT, session_id TEXT)"
    )
    conn.commit()
    conn.close()
    return path


def _throwaway(tmp: str) -> Path:
    """A throwaway ledger, with its throwaway telemetry source beside it."""
    _empty_telemetry_db(Path(tmp) / "no-telemetry.db")
    return Path(tmp) / "ledger.jsonl"


def run(ledger: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the tool against a throwaway ledger, with every substrate pinned.

    `OC_ACTORS_PATH` is pinned so the verdict cannot depend on which lanes this
    factory happens to have declared; `OPENCRABS_DB_PATH` is pinned to the seeded
    empty database so the append reads no live telemetry.
    """
    env = {**os.environ, "OC_LEDGER_PATH": str(ledger)}
    env["OC_ACTORS_PATH"] = str(ledger.parent / "no-actors.txt")
    env["OPENCRABS_DB_PATH"] = str(ledger.parent / "no-telemetry.db")
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def append(ledger: Path, event: str, actor: str, detail: str) -> subprocess.CompletedProcess:
    return run(ledger, "append", "--event", event, "--actor", actor,
               "--subject", SUBJECT, "--detail", detail)


def rows(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_around(ledger: Path, events: list[tuple[str, str]]) -> None:
    """Write rows AROUND the append path, the way no lawful writer can.

    This is the residue §11 names: one append path is a guarantee about the
    WRITERS, not about the file. A raw write takes no lock, so the pre-flight
    cannot see it — and `verify` is what catches it afterwards.
    """
    lines = [
        json.dumps({
            "n": i,
            "ts": "2026-09-19T00:00:00Z",
            "event": event,
            "actor": actor,
            "subject": SUBJECT,
            "detail": f"{event} written around the append path",
        })
        for i, (event, actor) in enumerate(events, 1)
    ]
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_the_gate_is_registered_in_the_audit() -> None:
    """An unregistered gate never runs (P29, issue #59)."""
    audit = (REPO / "tools" / "audit.py").read_text(encoding="utf-8")
    assert GATE_REL in audit, f"{GATE_REL} is not registered in tools/audit.py"


def test_a_close_with_no_claim_leg_is_refused() -> None:
    """The exact defect #98 exists to prevent: an intake, then a close, no claim."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _throwaway(tmp)
        assert append(ledger, "intake", "triage", "intake probe").returncode == 0

        refused = append(ledger, "close", "worker", "close probe")
        assert refused.returncode != 0, "a close with no claim leg must be refused"
        message = refused.stdout + refused.stderr
        assert "refused" in message, f"the existing refusal form must carry it: {message!r}"
        assert SUBJECT in message, f"the refusal must name the SUBJECT: {message!r}"
        assert "claim" in message, f"the refusal must name the MISSING LEG: {message!r}"


def test_a_close_with_no_intake_leg_is_refused() -> None:
    """Both legs, not only the claim leg: a claim alone does not license a close."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _throwaway(tmp)
        assert append(ledger, "claim", "worker", "claim probe").returncode == 0

        refused = append(ledger, "close", "worker", "close probe")
        assert refused.returncode != 0, "a close with no intake leg must be refused"
        message = refused.stdout + refused.stderr
        assert SUBJECT in message, f"the refusal must name the SUBJECT: {message!r}"
        assert "intake" in message, f"the refusal must name the MISSING LEG: {message!r}"


def test_a_refused_append_writes_nothing() -> None:
    """Not merely "no close row": the file is byte-for-byte what it was."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _throwaway(tmp)
        assert append(ledger, "intake", "triage", "intake probe").returncode == 0
        before_bytes = ledger.read_bytes()
        before_rows = len(rows(ledger))

        assert append(ledger, "close", "worker", "close probe").returncode != 0

        assert ledger.read_bytes() == before_bytes, "the refusal wrote to the ledger"
        assert len(rows(ledger)) == before_rows, "the refusal added a row"
        assert not [r for r in rows(ledger) if r["event"] == "close"], "a close row landed"


def test_a_close_with_both_legs_preceding_is_accepted() -> None:
    """The positive half: the refusal must not be a blanket refusal to close."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _throwaway(tmp)
        for event, actor in (("intake", "triage"), ("claim", "worker")):
            landed = append(ledger, event, actor, f"{event} probe")
            assert landed.returncode == 0, f"{event} did not land: {landed.stdout}{landed.stderr}"

        closed = append(ledger, "close", "worker", "close probe")
        assert closed.returncode == 0, f"a lawful close must land: {closed.stdout}{closed.stderr}"
        assert len(rows(ledger)) == 3, f"expected 3 rows, got {len(rows(ledger))}"

        verified = run(ledger, "verify")
        assert verified.returncode == 0, verified.stdout


def test_a_row_written_around_the_append_path_is_still_caught() -> None:
    """A claim sitting AFTER its close takes no lock, so only `verify` can see it."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _throwaway(tmp)
        write_around(ledger, [("intake", "triage"), ("close", "worker"), ("claim", "worker")])

        verified = run(ledger, "verify")
        assert verified.returncode != 0, "verify must still report a close with no claim before it"
        assert "claim" in verified.stdout, verified.stdout


def test_the_order_leg_survives_on_verify() -> None:
    """The pre-flight refuses this shape at the write path; verify still owns history."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _throwaway(tmp)
        write_around(ledger, [("claim", "worker"), ("intake", "triage"), ("close", "worker")])

        verified = run(ledger, "verify")
        assert verified.returncode != 0, "verify must report a claim that precedes its intake"
        assert "precedes its intake" in verified.stdout, verified.stdout
