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


def _carries_verbatim_session(row: object, sid: str) -> bool:
    """Whether a row carries docs/instruments/ledger.md §2's `session` key, byte-equal to the writing lane's id.

    A named predicate so arm 11 can exercise it directly, including on the rows that
    must FAIL it -- a check whose only evidence is that it passed over one good row has
    not been shown to bite.
    """
    return isinstance(row, dict) and row.get("session") == sid


class ResolverBroken(Exception):
    """The tree carries a lane resolver, and it will not load. A BROKEN INPUT.

    Distinct from an ABSENT one on purpose (HQ's criterion-3 sharpening): a
    destination tree that ships `tools/registry.py` and a manifest that will not
    parse must NOT take the same branch as a tree that carries no resolver at all.
    One is a defect in the tree, the other is a factory that has not declared a
    fleet yet, and a gate that renders them identically reports a clean skip over a
    broken input.
    """

RESOLVER = REPO / "tools" / "registry.py"

def _is_this_trees_fragment(data: object) -> bool:
    """Whether a live fragment describes THIS tree. It always does.

    The predecessor compared `data.get("factory")` against the ORIGIN factory's
    slug, hardcoded -- so in any destination factory
    the comparison never matched, the loop ran through every fragment, `resolve_role`
    returned None, and the gate took its skip branch while its message blamed the
    tree for a slug the kit had hardcoded. Outcome-correct, mechanism-wrong.

    Every path in `registry.live_fragment_paths([])` is the TREE'S OWN -- that is
    what `live` means -- so each fragment's `factory` IS this tree's slug and no
    comparison against a remembered name is owed. The tree's slug is therefore
    available from two independent sources (this fragment's own field, and the
    tree's `registry/fleet.json`, which `registry.FACTORY_CHATS` is built from); the
    fragment is used here because it is already in hand and cannot disagree with
    itself. Kept as a named predicate so a probe can exercise it directly.
    """
    return isinstance(data, dict)

def _report_broken(exc: BaseException) -> None:
    """Print the BROKEN-input verdict. Shared by both sites that can raise it.

    One printer, so the two cannot drift apart and render one state as a skip and the
    other as a failure. It prints and does NOT return: the caller keeps its own
    `return 1`, so the exit code is visible at the call site rather than hidden in a
    helper's return value.
    """
    print(f"ledger identity: FAILED — the lane resolver is present and BROKEN: {exc}")
    print("  A broken input is not an absent one: this tree ships a resolver, so this is a "
          "defect HERE rather than a factory that has not declared a fleet yet. Refusing to "
          "render it as a skip.")

def load_resolver() -> tuple[object | None, str | None]:
    """`(registry module, absent_reason)`; `absent_reason` is set only when it is ABSENT.

    Raises `ResolverBroken` when the resolver exists and cannot be read -- the third
    state, and the one that must never render as a skip. The two skips are both
    ABSENCE: no `tools/registry.py` at all (a tree that carries no lane resolver),
    and no fleet manifest (a factory that has not declared one, which `BOOTSTRAP.md`
    creates). A manifest that EXISTS and will not parse is neither.
    """
    if not RESOLVER.is_file():
        return None, f"this tree carries no {RESOLVER.relative_to(REPO)}"
    override = os.environ.get("OC_FLEET_MANIFEST")
    manifest = Path(override) if override else REPO / "registry" / "fleet.json"
    if not manifest.is_file():
        return None, f"this tree declares no fleet manifest ({manifest.name})"
    sys.path.insert(0, str(REPO / "tools"))
    try:
        import registry  # noqa: PLC0415
    except Exception as exc:
        raise ResolverBroken(
            f"{RESOLVER.relative_to(REPO)} is present and its manifest exists, but the "
            f"resolver will not load: {exc}"
        ) from exc
    # `import registry` TOLERATES a manifest that will not parse. registry.py:233 binds
    # `MANIFEST, MANIFEST_ERROR = _manifest_or_empty()`, so a broken file yields an empty
    # record set plus an error string rather than an exception — which is why the `except`
    # above cannot be the whole of this discrimination. Re-validating through the
    # resolver's OWN loader is the authoritative read: it raises on a file that will not
    # parse AND on one that parses but is incomplete, where the import-time cache would
    # silently yield no declared factories. Reading only the import would send a BROKEN
    # input into the emptiness below, and the emptiness renders as a skip: the false clean
    # this branch exists to prevent.
    try:
        registry.load_fleet_manifest(manifest)
    except Exception as exc:
        raise ResolverBroken(
            f"{manifest} is present but the resolver's own loader refuses it, so no "
            f"factory is declared: {exc}"
        ) from exc
    return registry, None

def resolve_role(role: str) -> str | None:
    """A live session id whose declared lane role is `role`, or None.

    Read through the registry's OWN resolver -- the same code the tool calls -- so
    the gate cannot disagree with the mechanism it pins about which session is which
    lane. Never assembled from a prefix: a hand-built session id is the defect this
    whole change exists to remove.

    The DESTINATION's lane is what resolves: the fragments iterated are this tree's
    own, and each is filtered by `_is_this_trees_fragment`, never by a remembered
    factory name.
    """
    registry, absent = load_resolver()
    if registry is None:
        return None
    bindings, errors = registry.all_bindings()
    if errors:
        # The same discrimination one level down: an unreadable binding store is a BROKEN
        # input, not an ABSENT lane. Rendering it as the skip below would certify a tree
        # whose daemon DB cannot be opened as a tree with nothing bound.
        raise ResolverBroken(
            "the resolver and its manifest loaded, but no binding row could be read: "
            + "; ".join(str(e) for e in errors)
        )
    for path in registry.live_fragment_paths([]):
        data, err = registry.load_fragment(path)
        if err or not _is_this_trees_fragment(data):
            continue
        chat_id = registry.FACTORY_CHATS.get(data.get("factory"))
        for lane in data.get("lanes") or []:
            if lane.get("role") != role:
                continue
            resolved = registry.resolve_lane(lane, bindings, {}, chat_id)
            if resolved.get("session_id"):
                return str(resolved["session_id"])
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

# --- The DESTINATION-factory tree, for ARMs 9 and 10 (issue #186) -----------------
#
# Built from the registry's own manifest idiom — the key set `_manifest_record`
# declares in tests/test_registry.py — and NOT from a copy of this repo's registry
# data, because a member tree that could still resolve a meta-factory lane would make
# ARM 9 pass for the wrong reason. The slug below is one no factory in this fleet
# declares, so the ONLY way the gate resolves a Worker there is by reading that tree's
# own fragment, which is exactly the property #186 is about.
MEMBER_SLUG = "probe-member"
MEMBER_CHAT = -1009990000001
MEMBER_THREAD = 90001
# A fixture session id, minted for the throwaway DB below and bound to nothing real.
# It never appears in a report and names no live lane: the rule against hand-assembling
# identifiers governs a REAL session's identity, and a member tree's session has to be
# synthesized rather than borrowed precisely so this gate cannot reach a live lane.
MEMBER_SESSION = "00000000-0000-4000-8000-00000000e186"
# The recursion sentinel. ARM 9 runs THIS gate inside a member tree, and that nested run
# would otherwise build its own member tree and recurse — three more gate processes per
# level, each with a 300 s timeout. A nested probe reports arms 1-8 and stops.
MEMBER_PROBE_ENV = "OC_IDENTITY_MEMBER_PROBE"


def _member_tree(tmp: Path, *, break_manifest: bool = False) -> Path:
    """A destination factory carrying the gate AND its full closure (P35).

    Two shapes from one builder, so the states cannot drift apart: the default —
    resolver + a parseable manifest, the tree #186's criterion 2 runs in — and
    `break_manifest=True`, a resolver present whose manifest will not parse, which is a
    BROKEN INPUT and must never render as the skip an ABSENT resolver earns (HQ's
    criterion-3 sharpening: "the skip must not become a false clean").

    There is deliberately NO `with_resolver=False` parameter here. `ledger.py` imports
    the resolver for its own actor derivation, so staging the tool's closure always
    brings `registry.py` along: a parameter of that name would silently not do what it
    says. Absence is constructed by removal in ARM 10, where the fact is stated.
    """
    root = tmp / "member"
    tests_dir = root / "tests"
    tools_dir = root / "tools"
    # The gate's OWN closure: it imports `gate_fixtures`, so copying the file alone
    # stages a tree that cannot start. That is P35, and it is the hole my first probe
    # of this arm fell into when it copied `ledger.py` without its import closure.
    stage_tool(Path(__file__).resolve(), tests_dir, REPO / "tests")
    stage_tool(TOOL, tools_dir, REPO / "tools")
    stage_tool(RESOLVER, tools_dir, REPO / "tools")
    (root / "registry" / "factories").mkdir(parents=True, exist_ok=True)
    profile_root = root / "profiles"
    manifest = {
        "profile_root": str(profile_root),
        "profile": "probe",
        "factories": [{
            "slug": MEMBER_SLUG,
            "display_name": "Probe Member",
            "chat_id": MEMBER_CHAT,
            "repo": f"owner/{MEMBER_SLUG}",
            "skill": f"skills/{MEMBER_SLUG}/SKILL.md",
            "job_prefixes": [f"{MEMBER_SLUG}-"],
            "aliases": [],
        }],
    }
    body = json.dumps(manifest)
    # A trailing `}` replaced by `",` is invalid JSON that still reads as text up to
    # the fault, so the resolver's own loader is the thing that rejects it.
    (root / "registry" / "fleet.json").write_text(
        body[:-1] + '",' if break_manifest else body, encoding="utf-8")
    (root / "registry" / "factories" / f"{MEMBER_SLUG}.json").write_text(json.dumps({
        "factory": MEMBER_SLUG,
        "status": "live",
        "lanes": [{"role": "worker", "topic": "Worker", "thread_id": MEMBER_THREAD}],
    }), encoding="utf-8")
    (profile_root / "probe").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(profile_root / "probe" / "opencrabs.db")
    conn.execute("CREATE TABLE session_bindings (session_id text, channel text, "
                 "chat_id integer, thread_id integer, updated_at integer)")
    conn.execute("CREATE TABLE sessions (id text, title text, updated_at integer)")
    conn.execute("INSERT INTO session_bindings VALUES (?, ?, ?, ?, ?)",
                 (MEMBER_SESSION, "telegram", MEMBER_CHAT, MEMBER_THREAD, 1))
    conn.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                 (MEMBER_SESSION, f"member {MEMBER_SLUG} worker", 1))
    conn.commit()
    conn.close()
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "ledger.jsonl").write_text("", encoding="utf-8")
    return root


def _run_gate_in(root: Path) -> subprocess.CompletedProcess:
    """Run the staged copy of THIS gate in `root`, with this shell's session stripped."""
    env = {k: v for k, v in os.environ.items()
           if k not in (SESSION_ENV, "OC_FLEET_MANIFEST", "OC_LEDGER_PATH")}
    # The sentinel that keeps ARMs 9-10 from recursing: it is set HERE and honoured by
    # `_arms_member_tree`, so the tree this arm builds reports the arms it exists to
    # prove and stops instead of spawning three more gate runs of its own. SESSION_ENV is
    # stripped for the same reason `run()` strips it: a nested tree that inherited this
    # shell's live session could resolve a REAL lane, and the arm exists to prove the
    # member's OWN lane is what resolves.
    env[MEMBER_PROBE_ENV] = "1"
    return subprocess.run(
        [sys.executable, str(root / "tests" / Path(__file__).name)],
        capture_output=True, text=True, env=env, cwd=str(root), timeout=300,
    )


def _arms_member_tree() -> None:
    """ARMs 9 and 10 — the tree-level verdicts for issue #186.

    Skipped inside a member probe: this process may BE the tree ARM 9 builds, and
    re-entering the arm there would recurse with three more gate runs per level.
    """
    if os.environ.get(MEMBER_PROBE_ENV):
        print("  (member probe: ARMs 9-10 belong to the top level — this tree exists to "
              "prove they bite, and reports arms 1-8 which are the ones that must RUN "
              "here rather than skip)")
        return

    # ARM 9 — THE MEMBER-SHAPED TREE, end to end (#186 criterion 2). ARM 8 is a unit
    # probe: it shows the filter accepts the tree's own slugs and nothing more. The
    # property that decides whether this defect is real is that a DESTINATION factory
    # RUNS this gate instead of skipping it, and that is only reachable by running the
    # gate in a tree shaped like a member's. Under the hardcoded origin comparison the
    # fragment below matched nothing, `resolve_role` returned None, and the gate skipped
    # while blaming the tree — so the assertion is not "rc==0" alone but that the
    # session it resolved is THIS tree's own bound lane.
    with tempfile.TemporaryDirectory() as mt:
        mr = _run_gate_in(_member_tree(Path(mt)))
        mout = mr.stdout + mr.stderr
        check("arm9 a member-shaped tree RUNS the gate rather than skipping it",
              "SKIPPED" not in mout, mout.strip()[:200])
        # The resolved id is read out of the gate's own line, which prints the first 8
        # chars of whatever `resolve_role` returned — so this proves the member's lane
        # resolved, and not merely that some lane did.
        check("arm9 it resolved THIS member's own Worker session",
              MEMBER_SESSION[:8] in mout,
              f"expected {MEMBER_SESSION[:8]}… in the gate's resolved-lane line")
        check("arm9 and arms 1-8 RAN and held inside it",
              mr.returncode == 0 and "identity passed" in mout,
              f"rc={mr.returncode} tail={mout.strip()[-260:]}")

        # ARM 10 — THE THREE STATES ARE THREE BRANCHES, not one (#186 criterion 3).
        # An ABSENT resolver is a factory that has not been given one: a legitimate
        # skip, whose reason must name the MISSING CLOSURE and never the origin
        # factory. A manifest that EXISTS and will not parse is a BROKEN input in a
        # tree that ships a resolver, and it must refuse instead — rendering it as the
        # same skip is the false clean HQ's sharpening exists to prevent.
        #
        # ABSENCE IS CONSTRUCTED BY REMOVAL, NOT BY DECLINING TO STAGE, and the reason
        # is a fact worth recording: `ledger.py` imports the resolver for its own
        # actor derivation, so `stage_tool(TOOL, …)` already carried `registry.py` into
        # this tree as part of the closure. A tree that ships the ledger tool ships the
        # resolver, so this skip branch is reachable in a live factory only where the
        # resolver was removed or never installed — which is why the more realistic
        # bootstrapped shape (the leg below it) is a resolver present and NO manifest.
        ar = _member_tree(Path(mt) / "a")
        (ar / "tools" / "registry.py").unlink()
        a = _run_gate_in(ar)
        aout = a.stdout + a.stderr
        check("arm10 NO resolver -> SKIP, and it is a clean exit",
              a.returncode == 0 and "SKIPPED" in aout, aout.strip()[:200])
        check("arm10 the skip reason names the MISSING CLOSURE",
              "carries no" in aout, aout.strip()[:200])

        # The bootstrapped shape: a resolver that ships, and a fleet manifest that
        # BOOTSTRAP.md has not written yet. Also a legitimate skip, also naming absence
        # rather than a factory — and it must not be confused with the leg below.
        nr = _member_tree(Path(mt) / "n")
        (nr / "registry" / "fleet.json").unlink()
        nm = _run_gate_in(nr)
        nmout = nm.stdout + nm.stderr
        check("arm10 resolver but NO manifest -> SKIP, naming the missing manifest",
              nm.returncode == 0 and "SKIPPED" in nmout and "manifest" in nmout,
              nmout.strip()[:200])

        # No factory slug appears in either reason. The population is READ from this
        # tree's own fleet manifest rather than typed here, because typing one is the
        # defect this change exists to remove — and a probe that names the literal it
        # checks absent is the same hardcoding wearing a test's clothes.
        _declared = [f["slug"] for f in json.loads(
            (REPO / "registry" / "fleet.json").read_text(encoding="utf-8"))["factories"]]
        check("arm10 and neither reason names any factory of this fleet",
              bool(_declared)
              and not any(s in aout for s in _declared)
              and not any(s in nmout for s in _declared),
              f"{len(_declared)} declared slug(s) checked against both reasons")

        b = _run_gate_in(_member_tree(Path(mt) / "b", break_manifest=True))
        bout = b.stdout + b.stderr
        check("arm10 a BROKEN manifest -> FAIL, never the skip branch",
              b.returncode == 1 and "SKIPPED" not in bout,
              f"rc={b.returncode} tail={bout.strip()[-200:]}")
        check("arm10 and it says so in terms — a broken input, not an absent one",
              "BROKEN" in bout and "not an absent one" in bout, bout.strip()[:220])


def main() -> int:
    print("ledger identity — the actor is DERIVED, and the matrix binds it (#138, plan 2646d31a)")

    if not TOOL.is_file():
        check("the tool exists", False, f"{TOOL} is absent")
        return 1

    try:
        registry, absent = load_resolver()
    except ResolverBroken as exc:
        _report_broken(exc)
        return 1
    if registry is None:
        print(
            f"ledger identity: SKIPPED — no lane resolver: {absent}. With no resolver there "
            f"are no lanes to bind, so every arm below would pass vacuously. A bootstrapped "
            f"factory lands here until BOOTSTRAP.md writes its fleet manifest."
        )
        return 0

    try:
        worker = resolve_role("worker")
    except ResolverBroken as exc:
        _report_broken(exc)
        return 1
    if worker is None:
        print(
            "ledger identity: SKIPPED — this tree carries a lane resolver and a manifest, but "
            "its Worker lane does not resolve to a live session, so no session can be bound "
            "to a role and every arm below would pass vacuously."
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
        # `run`, not `claim`: this arm tests the ACTOR MATRIX, and `claim` now carries a
        # sequence precondition (#137 half 2) that would refuse the row for an unrelated
        # reason. The carrier must be an event with no sequence leg.
        r = run(root, "append", "--event", "run", "--subject", "#A4", "--detail", MARKER,
                session=worker)
        check("arm4 CONTROL derived worker + run -> ACCEPTED",
              r.returncode == 0 and len(rows(led)) == 1, f"rc={r.returncode} rows={len(rows(led))}")
        check("arm4 the row records the DERIVED role, not a default",
              bool(rows(led)) and rows(led)[0].get("actor") == "worker",
              str(rows(led)[0].get("actor") if rows(led) else None))

        # ARM 5 — a declaration that CONTRADICTS the derivation is refused, naming both.
        r = run(root, "append", "--event", "run", "--actor", "hq", "--subject", "#A5",
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

        # ARM 11 — docs/instruments/ledger.md §2's SECOND IDENTITY KEY, which the write path never wrote (#256).
        #
        # The law declared it and nothing emitted it: `actor` is the CAPACITY a write was
        # made in, two lanes can share a capacity, and docs/instruments/ledger.md §2's own motivation is that 246 of
        # 1322 meta rows pasted a session uuid into free-text `detail` because no field
        # held it. The key sat in the schema's OPTIONAL_FIELDS -- and its own comment said
        # the widening landed "in the SAME change as the write path that emits it", which
        # is the half that never happened -- so every gate stayed green over a law key
        # that 0 of 1828 rows carried. These arms pin the WRITE.
        #
        # The live row is the one ARM 4's accepted append left on `led`; it is read back
        # off the BYTES rather than trusted as an object, because a key this reader could
        # add is not evidence that the tool wrote it.
        _raw_lines = [ln for ln in led.read_text(encoding="utf-8").splitlines() if ln.strip()]
        live_row = rows(led)[0] if rows(led) else {}
        check("arm11 the accepted live row carries the docs/instruments/ledger.md §2 `session` key",
              live_row.get("session") == worker,
              f"session={live_row.get('session')!r}; expected the resolved lane {worker[:8]}…")
        check("arm11 the key is the session, not the resolved role echoed back",
              live_row.get("session") not in (None, live_row.get("actor")),
              f"session={live_row.get('session')!r} actor={live_row.get('actor')!r}")
        check("arm11 the key is present in the bytes the tool wrote",
              bool(_raw_lines) and json.loads(_raw_lines[0]).get("session") == worker,
              f"{len(_raw_lines)} line(s) parsed from {led.name}")

        # A FIXTURE is not a lane, so a redirected write carries none: a fixture's bytes
        # must not depend on WHO RAN THE SUITE.
        _fixture_row = rows(fixture_led)[0] if rows(fixture_led) else {}
        check("arm11 a fixture write carries NO session key",
              "session" not in _fixture_row, f"keys={sorted(_fixture_row)}")

        # The predicate in BOTH directions. The CLI cannot reach the unset case on the
        # live path -- an unset variable refuses the append before a row exists -- so the
        # omission is pinned where it is decided, on the staged tool's own function.
        def _session_id_probe():
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location("_probe_ledger_sid", root / "tools" / "ledger.py")
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            return _mod.writing_session_id()

        _saved_sid = os.environ.get(SESSION_ENV)
        try:
            os.environ[SESSION_ENV] = "probe-verbatim-9f3a"
            check("arm11 writing_session_id() returns the variable VERBATIM",
                  _session_id_probe() == "probe-verbatim-9f3a",
                  f"got {_session_id_probe()!r}")
            os.environ.pop(SESSION_ENV, None)
            check("arm11 writing_session_id() returns None when the variable is unset",
                  _session_id_probe() is None, f"got {_session_id_probe()!r}")
        finally:
            if _saved_sid is None:
                os.environ.pop(SESSION_ENV, None)
            else:
                os.environ[SESSION_ENV] = _saved_sid

        # NON-VACUITY: the check must BITE. A row with the key absent, and a row whose key
        # names a different session, must BOTH fail the predicate -- otherwise the arms
        # above would pass over any row at all and prove nothing about the write.
        check("arm11 NON-VACUITY: the predicate rejects a row with no `session` key",
              not _carries_verbatim_session(
                  {k: v for k, v in live_row.items() if k != "session"}, worker),
              "an absent key must not read as a present one")
        check("arm11 NON-VACUITY: the predicate rejects a row naming another session",
              not _carries_verbatim_session(dict(live_row, session=UNRESOLVABLE), worker),
              "a different session must not read as verbatim")

    # ARM 8 — THE FRAGMENT FILTER (issue #186). The predecessor accepted a fragment only
    # when its `factory` equalled the ORIGIN slug, so a destination factory's own fragment
    # was skipped, `resolve_role` returned None, and the gate took its skip branch while
    # blaming the tree. The predicate must accept ANY live fragment, because
    # `live_fragment_paths` has ALREADY scoped the population to this tree -- that is what
    # `live` means -- so the fragment's own `factory` is this tree's slug by construction.
    check("arm8 a fragment naming ANOTHER factory is accepted (the #186 defect)",
          _is_this_trees_fragment({"factory": "miidas", "lanes": []}),
          "a destination factory's fragment was skipped by the hardcoded comparison")
    # And EVERY slug the tree's own manifest declares is accepted. No remembered name
    # is typed here, because typing one is the defect this arm exists to remove; the
    # population is read from the tree's own fleet manifest instead. The count is
    # asserted non-zero so a tree declaring no factory cannot report this as clean.
    _slugs = [f["slug"] for f in json.loads(
        (REPO / "registry" / "fleet.json").read_text(encoding="utf-8"))["factories"]]
    check("arm8 every slug the tree's own manifest declares is accepted",
          bool(_slugs)
          and all(_is_this_trees_fragment({"factory": s, "lanes": []}) for s in _slugs),
          f"{len(_slugs)} declared slug(s) read from the manifest; the hardcoded"
          " comparison accepted none of them")
    check("arm8 a malformed fragment is still refused",
          not _is_this_trees_fragment(None) and not _is_this_trees_fragment("not-a-dict"),
          "the predicate must still refuse a non-object")

    _arms_member_tree()

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
