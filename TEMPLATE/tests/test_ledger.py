#!/usr/bin/env python3
"""Gate for the ledger — the single-writer claim, tested rather than asserted.

The claim in SKILL.md is that `tools/ledger.py` is the *sole* writer for
`evidence/ledger.jsonl`, so concurrent lanes cannot collide on a row number.
That is a property of the code, and a property nobody tests is a hope.

It holds a second property too: a subject that reaches `close` must have been
filed (`intake`) and taken (`claim`) before it. Both are tested here.

This runs the probes against throwaway ledgers (`OC_LEDGER_PATH`) and throwaway
actor declarations (`OC_ACTORS_PATH`), never the live ones: a test that writes
the real state surface is how a probe becomes permanent corruption.

Run:  python3 tests/test_ledger.py
Exit: 0 all checks pass, 1 a check failed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ledger.py"

failures: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)

def run(ledger: Path, *args: str, actors: Path | None = None) -> subprocess.CompletedProcess:
    """Run the tool against a throwaway ledger.

    `OC_ACTORS_PATH` is pinned to a throwaway path as well unless a probe brings
    its own. Without that pin a probe would read the live `tools/actors.txt` and
    pass or fail on this factory's own declared lanes instead of on the code.
    """
    env = {**os.environ, "OC_LEDGER_PATH": str(ledger)}
    env["OC_ACTORS_PATH"] = str(actors if actors is not None else ledger.parent / "no-actors.txt")
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        env=env,
    )

def rows(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]

def write_ledger(path: Path, *events: tuple[str, str]) -> None:
    """Write an explicit ledger from (event, subject) pairs, numbered 1..N.

    Every row carries a known event and actor and a contiguous `n`, so the only
    thing a probe can trip is the sequence leg — a probe that could fail for two
    reasons proves neither.
    """
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "n": i,
                    "ts": "2026-09-12T00:00:00Z",
                    "event": event,
                    "actor": "hq",
                    "subject": subject,
                    "detail": "probe",
                }
            )
            for i, (event, subject) in enumerate(events, 1)
        )
        + "\n",
        encoding="utf-8",
    )

def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"

        print("concurrent append — the single-writer property")
        procs = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(TOOL),
                    "append",
                    "--event", "claim",
                    "--actor", "triage",
                    "--subject", f"probe-{i}",
                    "--detail", f"parallel append {i}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "OC_LEDGER_PATH": str(ledger)},
            )
            for i in range(20)
        ]
        for p in procs:
            p.wait()

        got = rows(ledger)
        numbers = [r["n"] for r in got]
        check("20 parallel appends all landed", len(got) == 20, f"{len(got)} rows")
        check(
            "no two writers claimed the same n",
            len(set(numbers)) == len(numbers),
            f"{len(set(numbers))} unique of {len(numbers)}",
        )
        check(
            "row numbers are 1..N with no gaps",
            numbers == list(range(1, len(got) + 1)),
            f"got {numbers[:5]}…",
        )

        print("\nverify — the integrity check itself")
        r = run(ledger, "verify")
        check("verify exits 0 on a good ledger", r.returncode == 0, r.stdout.strip())

        r = run(ledger, "append", "--event", "run", "--actor", "hq",
                "--subject", "four-gates", "--detail", "duration=3s outcome=accepted")
        check("run event type is accepted", r.returncode == 0, r.stdout.strip() if r.stdout else r.stderr.strip()[:60])

        print("\nrejection — the schema is closed")
        r = run(ledger, "append", "--event", "nonsense", "--actor", "hq",
                "--subject", "x", "--detail", "y")
        check("unknown event type is refused", r.returncode != 0, r.stderr.strip()[:60])
        r = run(ledger, "append", "--event", "ruling", "--actor", "nobody",
                "--subject", "x", "--detail", "y")
        check("unknown actor is refused", r.returncode != 0, r.stderr.strip()[:60])

        print("\nthe actor set — the core roles, plus what the factory declares")
        # The template ships four role cards; a factory whose law names a lane
        # beyond them declares it in tools/actors.txt. A lane that cannot be
        # declared cannot record its rows, so a shipped role the gate rejects —
        # or an undeclared lane it accepts — is a defect in the gate.
        act = Path(tmp) / "actors.jsonl"
        declared = Path(tmp) / "actors.txt"

        r = run(act, "append", "--event", "claim", "--actor", "worker",
                "--subject", "x", "--detail", "a shipped role")
        check("a role the template ships is accepted", r.returncode == 0,
              r.stderr.strip()[:60])

        r = run(act, "append", "--event", "claim", "--actor", "delegate",
                "--subject", "x", "--detail", "not declared here")
        check("a lane this factory has not declared is refused",
              r.returncode != 0, r.stderr.strip()[:60])

        declared.write_text("delegate\n", encoding="utf-8")
        r = run(act, "append", "--event", "claim", "--actor", "delegate",
                "--subject", "x", "--detail", "declared", actors=declared)
        check("a declared lane is accepted", r.returncode == 0, r.stderr.strip()[:60])

        r = run(act, "verify", actors=declared)
        check("verify accepts a row written by a declared lane",
              r.returncode == 0, r.stdout.strip().splitlines()[0] if r.stdout else "")

        print("\ncorruption is detected, not tolerated")
        with open(ledger, "a") as fh:
            fh.write(json.dumps({"n": 999, "ts": "2026-01-01T00:00:00Z",
                                 "event": "ruling", "actor": "hq",
                                 "subject": "x", "detail": "gap"}) + "\n")
        r = run(ledger, "verify")
        check("verify exits 1 on a gap in row numbers", r.returncode == 1,
              r.stdout.strip().splitlines()[0] if r.stdout else "")

        print("\nthe transition sequence — a close needs its legs")
        # A ledger can be perfectly numbered and still say that something was
        # closed without ever saying who took it. That is the shape this
        # catches, and it is why a row count is not an integrity check.
        seq = Path(tmp) / "seq.jsonl"

        def seq_case(name: str, events: tuple[tuple[str, str], ...],
                     want_rc: int, want: tuple[str, ...]) -> None:
            write_ledger(seq, *events)
            r = run(seq, "verify")
            ok = r.returncode == want_rc and all(s in r.stdout for s in want)
            lines = r.stdout.strip().splitlines()
            check(name, ok, lines[1].strip() if len(lines) > 1 else (lines[0] if lines else ""))

        seq_case("P1 close with no intake is refused",
                 (("close", "#1"),), 1, ("#1", "intake"))
        seq_case("P2 close with no claim is refused",
                 (("intake", "#2"), ("close", "#2")), 1, ("#2", "claim"))
        seq_case("P3 a full sequence passes",
                 (("intake", "#3"), ("claim", "#3"), ("close", "#3")), 0, ())
        seq_case("P4 a claim before its intake is refused",
                 (("claim", "#4"), ("intake", "#4"), ("close", "#4")), 1, ("#4", "precedes"))

    print()
    if failures:
        print(f"ledger gate FAILED: {len(failures)} check(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ledger gate passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
