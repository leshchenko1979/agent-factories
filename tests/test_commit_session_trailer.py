#!/usr/bin/env python3
"""Gate: the commit-msg hook writes a `Session-Id:` trailer, mechanically.

Origin: issue #138, ruled at ledger `n=928`, plan 2646d31a step 6.

THE GAP THIS CLOSES, measured rather than argued. Before this hook wrote the
trailer, a commit in this repository could not be attributed to a lane at all:
**0 of the last 200 commits carried a `Session-Id` trailer**, every commit
carried one shared author identity, and the board's author field returns the
same name for the owner, for HQ and for Triage alike because every lane files
through one CLI. So the ONLY attribution available was prose a lane chose to
write -- and on 2026-09-21 two lanes chased the wrong culprit because a commit
named nobody. The remedy is not a rule asking lanes to remember a flag: the
daemon already exports `OPENCRABS_SESSION_ID` into every tool subprocess, so the
identity is mechanical and the hook is the cheapest place to record it.

WHAT THIS GATE CAN AND CANNOT PROVE, stated because the difference is the whole
point. It CAN prove the mechanism works -- driven directly, with a synthetic
message and a synthetic session, both directions plus the refusal case. It
CANNOT prove that a given historical commit carries a trailer, because the hook
was installed late and history is not rewritten. So the gate probes the
MECHANISM and does not judge the population; the population is reported by the
patrol, which is where a live-state fact belongs.

The probe drives the hook DIRECTLY with a temporary message file rather than
making a real commit. A real commit would need a throwaway repository, and the
hook resolves its predicate through `git rev-parse --show-toplevel`, so the
throwaway would have to carry this repo's whole gate file -- a fixture that
tests the fixture. Direct invocation tests exactly the code git runs.

Run:  python3 tests/test_commit_session_trailer.py
Exit: 0 the mechanism is present and bites; 1 a check failed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "tools/hooks/commit-msg"
SESSION_ENV = "OPENCRABS_SESSION_ID"
TRAILER_KEY = "Session-Id"
PROBE_SESSION = "11111111-2222-3333-4444-555555555555"
SUBJECT = "fix(probe): a lawful subject names the concern"

_failures: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)

def drive(message: str, env: dict[str, str]) -> tuple[int, str]:
    """Run the hook on a temporary message file; return (rc, resulting body).

    The session variable is REMOVED from the inherited environment first, so a
    probe asking for its absence gets absence rather than this shell's own value.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write(message)
        path = Path(fh.name)
    base = {k: v for k, v in os.environ.items() if k != SESSION_ENV}
    try:
        proc = subprocess.run(
            [sys.executable, str(HOOK), str(path)],
            capture_output=True, text=True, env={**base, **env}, cwd=str(REPO),
        )
        return proc.returncode, path.read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)

def main() -> int:
    print("commit session trailer — the identity the environment already knows (#138)")

    if not HOOK.is_file():
        check("the hook exists", False, f"{HOOK} is absent — nothing to probe")
        return 1

    body = f"{SUBJECT}\n\nThe body explains the change.\n"

    rc, out = drive(body, {SESSION_ENV: PROBE_SESSION})
    check("a commit with the session set succeeds", rc == 0, f"rc={rc}")
    check("and the trailer carries that exact session",
          f"{TRAILER_KEY}: {PROBE_SESSION}" in out, repr(out[-90:]))
    check("the trailer is the LAST paragraph (a git trailer, not prose)",
          out.rstrip().splitlines()[-1] == f"{TRAILER_KEY}: {PROBE_SESSION}",
          repr(out.rstrip().splitlines()[-1]))
    check("the author's own text is byte-identical above the trailer",
          out.startswith(body), repr(out[:60]))

    rc, out = drive(body, {})
    check("a commit with the session ABSENT still succeeds", rc == 0, f"rc={rc}")
    check("and carries NO trailer — a fabricated actor is worse than none",
          TRAILER_KEY not in out, repr(out[-60:]))

    already = f"{body}\n{TRAILER_KEY}: {PROBE_SESSION}\n"
    rc, out = drive(already, {SESSION_ENV: PROBE_SESSION})
    check("an existing trailer is never duplicated", out.count(f"{TRAILER_KEY}:") == 1,
          f"{out.count(f'{TRAILER_KEY}:')} occurrence(s)")

    # The refusal case, and it is the one that keeps the trailer honest: a refused
    # commit must NOT be stamped, because that would attribute a commit that never
    # happened.
    rc, out = drive("fix(x): cites row n=1234 in its subject\n", {SESSION_ENV: PROBE_SESSION})
    check("a REFUSED subject still fails", rc == 1, f"rc={rc}")
    check("and a refused commit is NOT stamped", TRAILER_KEY not in out, repr(out[-60:]))

    if _failures:
        print(f"commit session trailer FAILED: {len(_failures)} check(s)")
        return 1
    print("commit session trailer passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
