#!/usr/bin/env python3
"""Gate: a `claim` whose subject has no `intake` ANYWHERE is a defect, at the moment it is made.

The ledger's sequence predicate used to run on `close` rows only. A `claim`
whose subject had no `intake` was therefore invisible: `verify` read GREEN while
the ledger was already defective, and the defect surfaced hours later, when
somebody tried to close. Measured on the live instrument: at ledger `4c46bc0`
(257 rows) `verify` returned 0 problems while this leg named
`line 256: claim for #120 has no intake anywhere in the ledger` — about nine
minutes before the close that turned the gate red, and one append-only repair
(`intake -> re-claim -> close`) later it was clean again.

A claim is work being taken, and work cannot be taken on a subject the ledger
never admitted. So the predicate is asked of the claim itself, at both call
sites, and the message is phrased for the event that triggered it.

'ANYWHERE', NOT 'BEFORE IT'
---------------------------
A late-reconstruction intake lands AFTER the original claim by design, so a
positional claim predicate would re-flag the very repair it exists to prompt.
The claim leg therefore looks for an intake anywhere in the subject's history.
The `close` legs keep their positional form — a close could not have been lawful
on the row it occupies unless its subject was already admitted by then — and the
order leg depends on that positional reading. One test below pins each half.

WHY NOT A `dispatch` LEG
------------------------
Three legacy subjects carry a `dispatch` and no `intake` (`#87` `#88` `#89`;
`SKILL.md@1.0.11`; `#108` dispatched to worker lane `1122b15e`) and none has a
claim or a close. A dispatch-keyed leg would fire three false positives on rows
that are not defective, which is why the leg is keyed on `claim`.

WHAT THIS GATE ASSERTS, AND WHAT IT DOES NOT
--------------------------------------------
It asserts the REFUSAL at the write path (nothing is written), the DETECTION at
`verify` (the line and the subject are named), the PHRASING (a claim-triggered
problem never says "close"), the ANYWHERE semantics, and the CLOSE regression
guard. It does NOT assert that a ledger can no longer CONTAIN such a row: a
writer that never calls `tools/ledger.py` takes no lock, and that residue stays
`verify`'s.

Every probe runs against a THROWAWAY ledger through the `OC_LEDGER_PATH` seam
`tests/test_ledger_ack.py` already uses; one test asserts the live state surface
is untouched.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ledger.py"
LIVE_LEDGER = REPO / "evidence" / "ledger.jsonl"

CLEAN = "#121clean"
BAD = "#121bad"

def _empty_telemetry_db(path: Path) -> Path:
    """A throwaway telemetry source: the schema, and NO rows.

    `tools/telemetry.py` is absent here, so a close append appends no trailer
    today — but pinning this is what keeps that true if a sibling ever lands.
    (A missing `OPENCRABS_DB_PATH` file is NOT isolation: the template's
    `find_database_path()` falls back to the live database in that case.)
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
    _empty_telemetry_db(Path(tmp) / "no-telemetry.db")
    return Path(tmp) / "ledger.jsonl"

def _env(ledger: Path) -> dict:
    return {
        **os.environ,
        "OC_LEDGER_PATH": str(ledger),
        "OC_ACTORS_PATH": str(ledger.parent / "no-actors.txt"),
        "OPENCRABS_DB_PATH": str(ledger.parent / "no-telemetry.db"),
    }

def run(ledger: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True, env=_env(ledger), cwd=REPO,
    )

def append(ledger: Path, subject: str, event: str, actor: str) -> subprocess.CompletedProcess:
    return run(ledger, "append", "--event", event, "--actor", actor,
               "--subject", subject, "--detail", f"{event} probe")

def write_around(ledger: Path, rows: list[tuple[str, str, str]]) -> None:
    """Write rows AROUND the append path, the way no lawful writer can.

    This is how the pre-gate history is reproduced: the rows were written before
    the leg existed, so no pre-flight could have seen them.
    """
    lines = [
        json.dumps({"n": i, "ts": "2026-09-21T00:00:00Z", "event": event,
                    "actor": actor, "subject": subject, "detail": f"{event} raw"})
        for i, (subject, event, actor) in enumerate(rows, 1)
    ]
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

def rows_of(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]

# --------------------------------------------------------------------------
# Criterion 2 — the pre-write leg refuses the row before it is written.
# --------------------------------------------------------------------------

def test_a_claim_with_no_intake_anywhere_is_refused_pre_write(tmp_path: Path) -> None:
    ledger = _throwaway(str(tmp_path))

    refused = append(ledger, BAD, "claim", "worker")

    assert refused.returncode != 0, "a claim whose subject was never admitted must be refused"
    message = refused.stdout + refused.stderr
    assert "refused" in message, f"the refusal form must carry it: {message!r}"
    assert BAD in message, f"the refusal must name the SUBJECT: {message!r}"
    assert "intake" in message, f"the refusal must name the MISSING LEG: {message!r}"

def test_a_refused_claim_append_writes_nothing(tmp_path: Path) -> None:
    """Not merely 'no claim row': the file is byte-for-byte what it was."""
    ledger = _throwaway(str(tmp_path))
    before_bytes = ledger.read_bytes() if ledger.exists() else b""

    assert append(ledger, BAD, "claim", "worker").returncode != 0

    after_bytes = ledger.read_bytes() if ledger.exists() else b""
    assert after_bytes == before_bytes, "the refusal wrote to the ledger"
    assert rows_of(ledger) == [], "the refusal added a row"

def test_a_lawful_claim_and_non_lifecycle_events_still_land(tmp_path: Path) -> None:
    """The positive half: the refusal must not be a blanket refusal to claim."""
    ledger = _throwaway(str(tmp_path))

    assert append(ledger, CLEAN, "intake", "hq").returncode == 0
    landed = append(ledger, CLEAN, "claim", "worker")
    assert landed.returncode == 0, f"a lawful claim must land: {landed.stdout}{landed.stderr}"
    # An event with no sequence precondition is untouched by the claim leg. `ack` is a
    # PER-FACTORY event (the reporting factory's own #92) and this template's core EVENTS
    # does not carry it, so `score` stands in: the property under test is the ABSENCE of a
    # sequence precondition, not the name of the event that lacks one.
    assert append(ledger, "SKILL.md@1.0.99", "score", "worker").returncode == 0
    assert append(ledger, "probe-subject", "run", "hq").returncode == 0

def test_a_lone_intake_is_still_accepted(tmp_path: Path) -> None:
    """Filing a subject is not work being taken; the claim leg must not reach it."""
    ledger = _throwaway(str(tmp_path))

    assert append(ledger, BAD, "intake", "hq").returncode == 0

# --------------------------------------------------------------------------
# Criterion 1 — verify goes non-zero and names the line and the subject.
# --------------------------------------------------------------------------

def test_verify_goes_red_on_a_claim_with_no_intake(tmp_path: Path) -> None:
    ledger = _throwaway(str(tmp_path))
    write_around(ledger, [(BAD, "claim", "worker")])

    verified = run(ledger, "verify")

    assert verified.returncode != 0, "verify must exit non-zero on a claim with no intake"
    assert "line 1" in verified.stdout, f"the problem must name the LINE: {verified.stdout}"
    assert BAD in verified.stdout, f"the problem must name the SUBJECT: {verified.stdout}"

# --------------------------------------------------------------------------
# Criterion 5 — the message is phrased for the event that triggered it.
# --------------------------------------------------------------------------

def test_the_message_is_phrased_for_the_event_that_triggered_it(tmp_path: Path) -> None:
    """A claim-triggered problem says `claim` — never `close`."""
    ledger = _throwaway(str(tmp_path))
    write_around(ledger, [(BAD, "claim", "worker")])

    verified = run(ledger, "verify")

    assert "claim for" in verified.stdout, verified.stdout
    assert "close for" not in verified.stdout, (
        f"a claim-triggered problem must not be phrased as a close problem: {verified.stdout}"
    )

def test_the_refusal_is_phrased_for_the_claim_too(tmp_path: Path) -> None:
    ledger = _throwaway(str(tmp_path))
    refused = append(ledger, BAD, "claim", "worker")
    message = refused.stdout + refused.stderr
    assert "claim for" in message and "close for" not in message, message

# --------------------------------------------------------------------------
# 'Anywhere', not 'before it' — the repair semantics.
# --------------------------------------------------------------------------

def test_the_predicate_is_anywhere_in_the_ledger_not_before_the_claim(tmp_path: Path) -> None:
    """A late intake lands AFTER the claim by design, so it must NOT re-flag it."""
    ledger = _throwaway(str(tmp_path))
    write_around(ledger, [(BAD, "claim", "worker"), (BAD, "intake", "hq")])

    verified = run(ledger, "verify")

    assert verified.returncode == 0, (
        f"an intake anywhere in the subject's history clears the claim leg: {verified.stdout}"
    )

def test_the_end_to_end_repair_sequence_verifies_clean(tmp_path: Path) -> None:
    """The #120 shape: a bare claim is RED, and a late intake repairs it — append-only."""
    ledger = _throwaway(str(tmp_path))
    write_around(ledger, [(BAD, "claim", "worker")])
    assert run(ledger, "verify").returncode != 0, "the bare claim is the defect"

    repaired = append(ledger, BAD, "intake", "hq")
    assert repaired.returncode == 0, repaired.stderr
    assert run(ledger, "verify").returncode == 0, "the late intake must repair it"

    # ...and a re-claim after the repair still stands clean (the #120 n=259 row).
    reclaim = append(ledger, BAD, "claim", "worker")
    assert reclaim.returncode == 0, reclaim.stderr
    assert run(ledger, "verify").returncode == 0

# --------------------------------------------------------------------------
# Criterion 4 — the invariant is PINNED by a fixture holding both shapes.
# --------------------------------------------------------------------------

def test_the_fixture_holds_both_a_clean_subject_and_a_claim_without_intake(
    tmp_path: Path,
) -> None:
    """One ledger, both subjects. The clean one must stay silent.

    Without the silent half this test would pass on a predicate that simply
    reported every claim in the ledger, which is why both shapes share a file.
    """
    ledger = _throwaway(str(tmp_path))
    write_around(ledger, [
        (CLEAN, "intake", "hq"), (CLEAN, "claim", "worker"), (CLEAN, "close", "worker"),
        (BAD, "claim", "worker"),
    ])

    verified = run(ledger, "verify")

    assert verified.returncode != 0, "the bad subject must turn the gate red"
    assert BAD in verified.stdout, f"the bad subject must be named: {verified.stdout}"
    assert CLEAN not in verified.stdout, (
        f"the clean subject must stay silent — the leg is not merely 'any claim': {verified.stdout}"
    )
    # The count line, by the label this repo's `verify` prints it under. Asserting on line 0
    # would read the refs header here, which carries no problem count at all.
    counts = [ln for ln in verified.stdout.splitlines() if ln.startswith("ledger problems:")]
    assert counts and counts[0].strip().endswith("1"), (
        f"exactly one problem must be counted, and the clean subject contributes none: "
        f"{verified.stdout}"
    )

def test_the_same_fixture_goes_green_once_the_bad_subject_has_an_intake(tmp_path: Path) -> None:
    """The tooth cuts both ways: the leg is not vacuous, and it is not a wall."""
    ledger = _throwaway(str(tmp_path))
    write_around(ledger, [
        (CLEAN, "intake", "hq"), (CLEAN, "claim", "worker"), (CLEAN, "close", "worker"),
        (BAD, "intake", "hq"), (BAD, "claim", "worker"),
    ])

    assert run(ledger, "verify").returncode == 0

# --------------------------------------------------------------------------
# Regression guard — the close legs keep their positional form.
# --------------------------------------------------------------------------

def test_the_close_legs_still_behave_positionally(tmp_path: Path) -> None:
    """Widening the claim leg must not widen the close legs."""
    ledger = _throwaway(str(tmp_path))
    write_around(ledger, [(CLEAN, "intake", "hq"), (CLEAN, "close", "worker")])

    verified = run(ledger, "verify")

    assert verified.returncode != 0, verified.stdout
    assert "close for" in verified.stdout and "no claim before it" in verified.stdout, (
        f"the close legs must keep their positional phrasing: {verified.stdout}"
    )

def test_the_order_leg_is_RETIRED_and_the_inversion_is_clean(tmp_path: Path) -> None:
    """The ORDER leg is retired HERE (2026-09-25, plan 2646d31a step 5), unlike the tree this
    test came from: intake is Triage's row and the claim is the implementer's, so a claim
    landing before its intake is the designed outcome of a wake-latency race rather than an
    error by either lane. What SURVIVES is PRESENCE -- a close must have both legs before it --
    and that is pinned by the test above. Porting the ordering clause back would re-accuse
    every occurrence of the race, so this test pins the ABSENCE of the clause instead.
    """
    ledger = _throwaway(str(tmp_path))
    write_around(ledger, [
        (CLEAN, "claim", "worker"), (CLEAN, "intake", "hq"), (CLEAN, "close", "worker"),
    ])

    verified = run(ledger, "verify")

    assert verified.returncode == 0, (
        f"a claim before its intake is the designed race outcome here, not a defect: "
        f"{verified.stdout}"
    )
    assert "precedes its intake" not in verified.stdout, verified.stdout

# --------------------------------------------------------------------------
# Isolation — a probe must never become corruption.
# --------------------------------------------------------------------------

def test_the_tests_never_write_the_live_ledger(tmp_path: Path) -> None:
    # THE SHIPPED TREE CARRIES NO `evidence/` (#199). The ledger is BOOTSTRAP-created, so
    # there is no live file here to compare against — and reading one unconditionally made
    # this probe fail in the tree the kit ships from, which is a crash rather than a verdict.
    # The property it protects is that NO probe reaches the live surface, and that holds
    # vacuously where no live surface exists; the skip is stated so the vacuity is visible.
    if not LIVE_LEDGER.is_file():
        print(f"  SKIPPED  no {LIVE_LEDGER.relative_to(REPO)} in this tree — nothing live to "
              f"reach, so the isolation property holds vacuously here")
        return
    before = LIVE_LEDGER.read_bytes()
    ledger = _throwaway(str(tmp_path))

    assert append(ledger, CLEAN, "intake", "hq").returncode == 0
    assert append(ledger, CLEAN, "claim", "worker").returncode == 0
    assert append(ledger, BAD, "claim", "worker").returncode != 0
    assert run(ledger, "verify").returncode == 0

    assert LIVE_LEDGER.read_bytes() == before, "a probe wrote the live state surface"
