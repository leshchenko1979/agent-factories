#!/usr/bin/env python3
"""Gate: the ledger's actor is DERIVED from the session, and the matrix binds it.

Origin: issue #138 (attribution) and plan 2646d31a steps 1-3, landed 2026-09-25.

THE TWO DEFECTS THIS PINS, both measured rather than argued.

1. IDENTITY WAS DECLARED. A row's `actor` was whatever a lane typed into
   `--actor`, and `cmd_append` checked only that the name was in the known-actor
   LIST. Measured: three `intake` rows in one member factory carried
   `actor=worker`, and `intake` is Triage's row -- the write path accepted every
   one and the schema gate reported them a day later.

2. `repair` DEFAULTED ITS ACTOR. Omitting the flag stamped the repair as the
   Worker regardless of who ran it, which is misattribution by omission.

So the tool now DERIVES the actor from `OPENCRABS_SESSION_ID` -- which the daemon
exports into every tool subprocess, so the identity was always available and the
kit simply never asked -- resolves it through the registry's own lane resolver,
refuses a lane it cannot place BY NAME, accepts a `--actor` only when it AGREES
with the derivation, and enforces the per-event authorization matrix at the write
path.

WHY EVERY ARM RUNS IN A STAGED TREE, which is the load-bearing design decision
here. The STRICT branch -- derivation, agreement, matrix -- is reachable ONLY when
`OC_LEDGER_PATH` is absent, and with that variable absent the tool's target is its
own `REPO/evidence/ledger.jsonl`. So the strict path cannot be exercised against a
redirected ledger by construction: either the redirect is set and the fixture
branch runs, or it is absent and the write goes to the live ledger. A staged copy
of the tool (and its import closure, and the fleet manifest the resolver reads) is
therefore the only way to test it, and `gate_fixtures.stage_tool` is the one
sanctioned way to build that tree. This was found by writing the arms the wrong
way first: an arm asserting the contradiction refusal through `OC_LEDGER_PATH`
returned rc=0, and the cause was the PROBE, not the tool -- a fixture legitimately
wins its own declaration because it has no lane to bind to.

THE FIXTURE SEAM, and why it is not a hole. A redirected ledger or a `--subprocess`
sub-ledger is a FIXTURE: a declared actor there is the fixture's own declaration
and the matrix does not apply, because a fixture-declared actor has no row in a
matrix about lanes. Reaching the LIVE ledger requires BOTH overrides to be absent,
so nothing can smuggle a role into it by declaring one -- and this gate asserts
that seam in BOTH directions, because a seam nobody tests is one that gets widened
by accident.

Run:  python3 tests/test_ledger_identity.py
Exit: 0 every arm behaved; 1 an arm failed; 0 with a stated SKIP when the lane
      resolver cannot be read (a bootstrapped factory has no fleet manifest).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools/ledger.py"
LIVE_LEDGER = REPO / "evidence/ledger.jsonl"
SESSION_ENV = "OPENCRABS_SESSION_ID"
MARKER = "probe-identity-arm"
UNRESOLVABLE = "deadbeef-0000-0000-0000-000000000000"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_fixtures import stage_tool  # noqa: E402

_failures: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)

def resolve_role(role: str) -> str | None:
    """A live session id whose declared lane role is `role`, or None.

    Read through the registry's OWN resolver -- the same code the tool calls -- so
    the gate cannot disagree with the mechanism it pins about which session is which
    lane. Never assembled from a prefix: a hand-built session id is the defect this
    whole change exists to remove.
    """
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import registry  # noqa: PLC0415
        bindings, _errors = registry.all_bindings()
        for path in registry.live_fragment_paths([]):
            data, err = registry.load_fragment(path)
            if err or not isinstance(data, dict) or data.get("factory") != "meta-factory":
                continue
            chat_id = registry.FACTORY_CHATS.get(data.get("factory"))
            for lane in data.get("lanes") or []:
                if lane.get("role") != role:
                    continue
                resolved = registry.resolve_lane(lane, bindings, {}, chat_id)
                if resolved.get("session_id"):
                    return str(resolved["session_id"])
    except Exception as exc:  # an unreadable registry is a STATED skip, never a pass
        print(f"  (the lane resolver could not be read: {exc})")
    return None

def stage(tmp: Path) -> Path:
    """A throwaway repo root holding a runnable copy of the tool AND its resolver data.

    The manifest is staged because the resolver reads it relative to the TOOL's own
    tree: without it the staged tree cannot resolve any session, and every arm below
    would pass for the wrong reason (each append refused as unresolvable rather than
    for the property under test).
    """
    root = tmp / "staged"
    stage_tool(TOOL, root / "tools", REPO / "tools")
    (root / "registry" / "factories").mkdir(parents=True, exist_ok=True)
    (root / "registry" / "fleet.json").write_bytes((REPO / "registry/fleet.json").read_bytes())
    for frag in (REPO / "registry/factories").glob("*.json"):
        shutil.copy2(frag, root / "registry" / "factories" / frag.name)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    db = root / "evidence" / "no-telemetry.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE messages (created_at INTEGER, cost REAL, input_tokens INTEGER, "
        "token_count INTEGER, role TEXT, session_id TEXT)"
    )
    conn.commit()
    conn.close()
    return root

def run(root: Path, *args: str, session: str | None) -> subprocess.CompletedProcess:
    """Drive the staged tool on its own default ledger (the STRICT path).

    The session variable is set from the caller rather than inherited, so an arm
    asking for its ABSENCE gets absence rather than this shell's own value.
    """
    env = {k: v for k, v in os.environ.items() if k != SESSION_ENV}
    env["OPENCRABS_DB_PATH"] = str(root / "evidence" / "no-telemetry.db")
    if session is not None:
        env[SESSION_ENV] = session
    return subprocess.run(
        [sys.executable, str(root / "tools" / "ledger.py"), *args],
        capture_output=True, text=True, env=env, cwd=str(root),
    )

def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def main() -> int:
    print("ledger identity — the actor is DERIVED, and the matrix binds it (#138, plan 2646d31a)")

    if not TOOL.is_file():
        check("the tool exists", False, f"{TOOL} is absent")
        return 1

    worker = resolve_role("worker")
    if worker is None:
        print(
            "ledger identity: SKIPPED — the meta-factory's Worker lane does not resolve in "
            "this tree, so no session can be bound to a role and every arm below would "
            "pass vacuously. A bootstrapped factory with no fleet manifest lands here."
        )
        return 0
    print(f"  (worker session resolved: {worker[:8]}… — read from the registry, never assembled)")

    before = LIVE_LEDGER.read_bytes()

    with tempfile.TemporaryDirectory() as tmp:
        root = stage(Path(tmp))
        led = root / "evidence" / "ledger.jsonl"

        # ARM 1 — no session at all: REFUSED, and not defaulted to any role.
        r = run(root, "append", "--event", "run", "--subject", "#A1", "--detail", MARKER,
                session=None)
        check("arm1 no session -> refused, not defaulted",
              r.returncode != 0 and not rows(led), f"rc={r.returncode} rows={len(rows(led))}")
        check("arm1 the refusal names the missing variable",
              SESSION_ENV in r.stderr, r.stderr.strip()[:110])

        # ARM 2 — a session that resolves to no lane: REFUSED, and it NAMES that session.
        r = run(root, "append", "--event", "run", "--subject", "#A2", "--detail", MARKER,
                session=UNRESOLVABLE)
        check("arm2 an unresolvable session -> refused",
              r.returncode != 0 and not rows(led), f"rc={r.returncode}")
        check("arm2 the refusal names THAT session, so it is diagnosable",
              UNRESOLVABLE in r.stderr, r.stderr.strip()[:110])

        # ARM 3 — derived `worker`, event `intake`: REFUSED by the MATRIX.
        # `intake` is Triage's row; this is the exact shape of the three unauthorized
        # rows the write path used to accept silently.
        r = run(root, "append", "--event", "intake", "--subject", "#A3", "--detail", MARKER,
                session=worker)
        check("arm3 derived worker + intake -> refused by the matrix",
              r.returncode != 0 and not rows(led), f"rc={r.returncode}")
        check("arm3 the refusal names the event, the actor and the accepted set",
              all(s in r.stderr for s in ("intake", "worker", "triage")), r.stderr.strip()[:130])

        # ARM 4 — CONTROL. The same session on an event it IS authorized for must land.
        # Without this the refusals above are indistinguishable from a tool that refuses
        # everything.
        r = run(root, "append", "--event", "claim", "--subject", "#A4", "--detail", MARKER,
                session=worker)
        check("arm4 CONTROL derived worker + claim -> ACCEPTED",
              r.returncode == 0 and len(rows(led)) == 1, f"rc={r.returncode} rows={len(rows(led))}")
        check("arm4 the row records the DERIVED role, not a default",
              bool(rows(led)) and rows(led)[0].get("actor") == "worker",
              str(rows(led)[0].get("actor") if rows(led) else None))

        # ARM 5 — a declaration that CONTRADICTS the derivation is refused, naming both.
        r = run(root, "append", "--event", "claim", "--actor", "hq", "--subject", "#A5",
                "--detail", MARKER, session=worker)
        check("arm5 a contradicting --actor -> refused",
              r.returncode != 0 and len(rows(led)) == 1, f"rc={r.returncode} rows={len(rows(led))}")
        check("arm5 the refusal names BOTH the declared and the derived role",
              "hq" in r.stderr and "worker" in r.stderr, r.stderr.strip()[:130])

        # ARM 6 — the FIXTURE SEAM, asserted in the direction that matters: with the
        # redirect set, a declared actor is accepted because there is no lane to bind to.
        # This is the seam that makes every other gate's fixtures possible, so it is
        # pinned deliberately rather than left implicit.
        fixture_led = root / "fixture" / "ledger.jsonl"
        fixture_led.parent.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k != SESSION_ENV}
        env.update({
            "OC_LEDGER_PATH": str(fixture_led),
            "OPENCRABS_DB_PATH": str(root / "evidence" / "no-telemetry.db"),
            SESSION_ENV: worker,
        })
        r = subprocess.run(
            [sys.executable, str(root / "tools" / "ledger.py"),
             "append", "--event", "intake", "--actor", "triage", "--subject", "#A6",
             "--detail", MARKER],
            capture_output=True, text=True, env=env, cwd=str(root),
        )
        check("arm6 a redirected ledger may declare its own actor (the seam is intended)",
              r.returncode == 0 and len(rows(fixture_led)) == 1,
              f"rc={r.returncode} rows={len(rows(fixture_led))}")

    # ARM 7 — HERMETICITY: nothing above reached the live ledger. The staged tree's own
    # default ledger is inside the temp dir, so the live ledger was never even the
    # target; the content check is the belt to that braces, and it is by CONTENT rather
    # than by row count because a peer lane appending lawfully during this run must not
    # turn this gate RED.
    marker_hits = LIVE_LEDGER.read_text(encoding="utf-8").count(MARKER)
    check("arm7 no probe row reached the live ledger", marker_hits == 0, f"{marker_hits} hit(s)")
    if LIVE_LEDGER.read_bytes() != before:
        print("  (the live ledger moved during this run — a concurrent lawful append is "
              "consistent with this gate; the marker check above is the verdict)")

    if _failures:
        print(f"ledger identity FAILED: {len(_failures)} check(s)")
        return 1
    print("ledger identity passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
