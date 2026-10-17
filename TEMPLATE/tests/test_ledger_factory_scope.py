#!/usr/bin/env python3
"""Gate: the ledger's lane resolver is SCOPED to this factory's own fragment.

Origin: issue #312, ruled and dispatched 2026-10-17 (dispatch n=3493).

THE DEFECT THIS PINS, demonstrated rather than argued. `session_to_role` read
EVERY factory fragment and returned the first lane whose resolved session matched,
as a bare role string. Neither the derivation nor the membership check scoped the
session to THIS factory, so any lane in ANY factory whose role name collided with a
meta role inherited that role's powers here. Measured on the live fleet before the
fix: of 33 resolvable sessions, **20 belonged to other factories** and every one of
them resolved to a meta role. The issue's own reproduction, re-run after the fix:

    OPENCRABS_SESSION_ID=cb06a94a-... python3 tools/ledger.py append --event intake ...
    -> refused, naming 'ai-antispam', ZERO rows written

`hq` is declared by all six factories, `triage` by four, `worker` by three, so the
collision is the normal case and not an edge.

WHY THE DISCRIMINATING PAIR IS THE FLEET-WIDE FALLBACK. `decide_role(None, ...)`
grants the role, and `decide_role('meta-factory', [('ai-antispam', 'hq')])` refuses
it. Same session, same matches, ONE input changed -- so the arm proves the SCOPING
is what refuses, not something incidental to the fixture. Without it, a resolver
that refused everything would pass every refusal arm here.

WHY THE UNPLACEABLE-TREE ARM ASSERTS A GRANT RATHER THAN A REFUSAL. A bootstrapped
factory whose manifest row is not written yet must still be able to stamp its own
genesis row; refusing every write in that state would name no remedy. The residual
is therefore stated in the tool's docstring and asserted here, rather than left for
a reader to discover as a surprise.

Run:  python3 tests/test_ledger_factory_scope.py
Exit: 0 every arm behaved; 1 an arm failed; 0 with a stated SKIP when the fleet
      manifest cannot be read (a bootstrapped factory has no manifest yet).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
LEDGER_TOOL = TOOLS / "ledger.py"
OWN_FACTORY = "meta-factory"

# The session the issue demonstrated with: the ai-antispam HQ lane, a FOREIGN
# factory, whose role name `hq` collides with this factory's own.
FOREIGN_SESSION = "cb06a94a-be02-4e8c-b6c6-c8c9f09922f4"
FOREIGN_FACTORY = "ai-antispam"
UNKNOWN_SESSION = "deadbeef-0000-0000-0000-000000000000"

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

_failures: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)

def skip(reason: str) -> None:
    print(f"  SKIP  {reason}")
    sys.exit(0)

try:
    import ledger
except Exception as exc:  # a tool that will not import is a broken INPUT, not a pass
    print(f"FAIL  the ledger tool does not import: {exc}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Arm 1 — the PURE predicate, in both directions.
# ---------------------------------------------------------------------------

def arm_pure_predicate() -> None:
    print("\n[1] decide_role is pure, and grants ONLY this factory's lanes")
    decide = ledger.decide_role

    role, why = decide(OWN_FACTORY, [(OWN_FACTORY, "worker")])
    check("an own-factory match GRANTS its role", role == "worker" and why == "", f"{role!r}")

    role, why = decide(OWN_FACTORY, [(FOREIGN_FACTORY, "hq")])
    check("a foreign match is REFUSED", role is None, f"{role!r}")
    check("the refusal NAMES the foreign factory", FOREIGN_FACTORY in why, why[:90])
    check("the refusal NAMES the colliding role", "'hq'" in why, why[:90])
    check("the refusal NAMES this factory", OWN_FACTORY in why, why[:90])

    # Own wins regardless of fragment ORDER: the fleet store is sorted by filename,
    # so `ai-antispam.json` precedes `meta-factory.json` and a first-match resolver
    # would hand the row to the foreign lane on an accident of the alphabet.
    for label, matches in (
        ("own first", [(OWN_FACTORY, "worker"), (FOREIGN_FACTORY, "hq")]),
        ("foreign first", [(FOREIGN_FACTORY, "hq"), (OWN_FACTORY, "worker")]),
    ):
        role, why = decide(OWN_FACTORY, matches)
        check(f"own match wins with the {label}", role == "worker", f"{role!r}")

    role, why = decide(OWN_FACTORY, [])
    check("no match at all returns no role and no foreign refusal", role is None and why == "", f"{role!r}/{why!r}")

    # The DISCRIMINATING PAIR: one input changes and the verdict must flip. This is
    # what proves the refusal above is the SCOPING and not the fixture.
    matches = [(FOREIGN_FACTORY, "hq")]
    granted, _ = decide(None, matches)
    refused, _ = decide(OWN_FACTORY, matches)
    check(
        "DISCRIMINATING PAIR: same matches, own_slug None grants and the real slug refuses",
        granted == "hq" and refused is None,
        f"unplaced={granted!r} scoped={refused!r}",
    )

    # An UNPLACEABLE tree keeps the fleet-wide reading — asserted, not assumed.
    role, why = decide(None, [(FOREIGN_FACTORY, "hq")])
    check("an unplaceable tree keeps the fleet-wide reading (stated residual)", role == "hq", f"{role!r}")

# ---------------------------------------------------------------------------
# Arm 2 — the tree places itself, and it does so from a WORKTREE too.
# ---------------------------------------------------------------------------

def arm_tree_identity() -> None:
    print("\n[2] the tree knows which factory it is, from the manifest's own declaration")
    slug, why = ledger.factory_slug_for_tree()
    if slug is None and "no factory in the fleet manifest declares" in why:
        skip(f"this tree is not a declared factory — {why}")
    check("this tree resolves to exactly one factory", slug == OWN_FACTORY, f"{slug!r} {why}")

    root = ledger.tree_repo_root()
    check("tree_repo_root is an ABSOLUTE resolved path", root.is_absolute() and root == root.resolve(), str(root))

    # The worktree leg: this gate runs from whatever checkout the lane works in, and
    # a linked worktree answers a DIFFERENT directory for `REPO`. Identity must not
    # depend on which checkout the writer happens to be in (#312, and the af-487
    # incident where two trees shared one branch).
    proc = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        common = Path(proc.stdout.strip())
        if common.name == ".git":
            check(
                "the identity anchor is the REPOSITORY, not the checkout",
                root == common.parent.resolve(),
                f"root={root} common_parent={common.parent.resolve()}",
            )
        else:
            check("a non-.git common dir falls back to the checkout", root == REPO.resolve(), str(root))

# ---------------------------------------------------------------------------
# Arm 3 — the live resolver, on the demonstrated session.
# ---------------------------------------------------------------------------

def arm_live_resolver() -> None:
    print("\n[3] the live resolver grants this factory's lanes and refuses foreign ones")
    own_lanes = []
    for sid, expected in (
        ("dcd8f7a9-c1e7-48c3-b184-d901dc08eac7", "worker"),
        ("f4c192c9-a8e9-4268-9026-ee3e4970cc8a", "triage"),
    ):
        role, why = ledger.session_to_role(sid)
        own_lanes.append((sid, role))
        check(f"own lane {expected} still resolves", role == expected, f"{role!r} {why[:60]}")

    role, why = ledger.session_to_role(FOREIGN_SESSION)
    check(f"the issue's foreign session ({FOREIGN_FACTORY} hq) is REFUSED", role is None, f"{role!r}")
    check("its refusal names the foreign factory", FOREIGN_FACTORY in why, why[:100])

    role, why = ledger.session_to_role(UNKNOWN_SESSION)
    check("an unknown session is still refused as unmatched", role is None and "matches no lane" in why, why[:80])

# ---------------------------------------------------------------------------
# Arm 4 — end to end: the append path writes NOTHING for a foreign session.
# ---------------------------------------------------------------------------

def arm_append_refuses() -> None:
    print("\n[4] END TO END — the issue's own reproduction writes no row")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "probe.jsonl"
        env = dict(os.environ)
        env["OPENCRABS_SESSION_ID"] = FOREIGN_SESSION
        env["OC_LEDGER_PATH"] = str(target)
        env.pop("OC_ACTOR", None)
        proc = subprocess.run(
            [
                sys.executable, str(LEDGER_TOOL), "append",
                "--event", "intake",
                "--subject", "probe-foreign-session-actor",
                "--detail", "PROBE #312 — re-run of the issue's reproduction",
            ],
            cwd=REPO, capture_output=True, text=True, timeout=120, env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        check("the append is REFUSED", "refused" in out.lower(), out.strip()[:120])
        check("the refusal names the foreign factory", FOREIGN_FACTORY in out, out.strip()[:120])
        written = target.read_text().strip() if target.exists() else ""
        check("ZERO rows were written", written == "", f"{len(written)} bytes")

    # The positive control for arm 4: an OWN lane on the same seam DOES write. Without
    # it, a tool that refused every append would pass this arm.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "probe.jsonl"
        env = dict(os.environ)
        env["OPENCRABS_SESSION_ID"] = "dcd8f7a9-c1e7-48c3-b184-d901dc08eac7"
        env["OC_LEDGER_PATH"] = str(target)
        proc = subprocess.run(
            [
                sys.executable, str(LEDGER_TOOL), "append",
                "--event", "run",
                "--subject", "probe-own-lane-writes",
                "--detail", "POSITIVE CONTROL for #312 — an own-factory lane must still write",
            ],
            cwd=REPO, capture_output=True, text=True, timeout=120, env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        wrote = target.exists() and bool(target.read_text().strip())
        check("POSITIVE CONTROL: an own lane on the same seam still writes", wrote, out.strip()[:120])

# ---------------------------------------------------------------------------
# Arm 5 — the scope is not a comment: the resolver must CALL the predicate.
# ---------------------------------------------------------------------------

def arm_resolver_calls_the_scope() -> None:
    print("\n[5] the resolver routes through the scoped predicate, so a revert reds here")
    source = LEDGER_TOOL.read_text()
    check("session_to_role calls decide_role", "decide_role(own_slug, matches)" in source)
    check("session_to_role resolves the tree's factory", "factory_slug_for_tree()" in source)
    check(
        "no bare first-match return survives in the resolver",
        'return str(role), ""' not in source,
    )

def main() -> int:
    print("gate: the ledger's lane resolver is scoped to its own factory (#312)")
    arm_pure_predicate()
    arm_tree_identity()
    arm_live_resolver()
    arm_append_refuses()
    arm_resolver_calls_the_scope()
    print()
    if _failures:
        print(f"FAIL — {len(_failures)} arm(s) failed: {', '.join(_failures)}")
        return 1
    print("PASS — every arm behaved")
    return 0

if __name__ == "__main__":
    sys.exit(main())
