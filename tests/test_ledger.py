#!/usr/bin/env python3
"""Gate for the ledger — the single-writer claim, tested rather than asserted.

The claim in SKILL.md is that `tools/ledger.py` is the *sole* writer for
`evidence/ledger.jsonl`, so concurrent lanes cannot collide on a row number.
That is a property of the code, and a property nobody tests is a hope.

It holds a second property too: a subject that reaches `close` must have been
filed (`intake`) and taken (`claim`) before it. Both are tested here.

A third is a READ path rather than a write one: `verify` must PRINT the rows that
declare themselves reconstructions (`claim=reconstructed`), beside its `excused:`
lines, so clean, excused and reconstructed are never the same output (#98, ruling
n=602 PART 5) — and since #115 (ruling n=687 clause 1) that line also carries the
interval RECOMPUTED from the two rows' own `ts` values, because the author controls
the act of declaring and never the interval the tool stamps under the append lock.

And a fourth closes the exemption's own boundary: an entry that would excuse a
POST-gate omission is ADMITTED only by its PROOF, so an entry carrying none is
refused at the point it would excuse something and the omission stays a problem
(#52 clause 3, ruling n=318).

This runs the probes against throwaway ledgers (`OC_LEDGER_PATH`) and throwaway
actor declarations (`OC_ACTORS_PATH`), never the live ones: a test that writes
the real state surface is how a probe becomes permanent corruption.

Run:  python3 tests/test_ledger.py
Exit: 0 all checks pass, 1 a check failed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ledger.py"
LOCAL_TOOLS = REPO / "tools"

# A throwaway tree must model the tree the tool actually runs in. Copying the tool
# alone reds the probe the moment it gains a neighbour import, and this gate's
# append-guard probe needs a real repository, so that failure would read as a
# ledger defect rather than a fixture one.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_fixtures import stage_tool  # noqa: E402
import ledger_boundary  # noqa: E402 — the SHARED boundary reader, so this
# gate and `tools/ledger.py repair` cannot disagree about what was declared

failures: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)

def run(
    ledger: Path,
    *args: str,
    actors: Path | None = None,
    auth: Path | None = None,
    extra_env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run the tool against a throwaway ledger.

    `OC_ACTORS_PATH` is pinned to a throwaway path as well unless a probe brings
    its own. Without that pin a probe would read the live `tools/actors.txt` and
    pass or fail on this factory's own declared lanes instead of on the code.

    `extra_env` exists for the same reason one layer down: the append guard's
    telemetry comes from the runtime substrate, so a probe that did not pin the
    database would read the LIVE one and its verdict would depend on the box.
    """
    env = {**os.environ, "OC_LEDGER_PATH": str(ledger)}
    env["OC_ACTORS_PATH"] = str(actors if actors is not None else ledger.parent / "no-actors.txt")
    env["OC_AUTHORIZATIONS_PATH"] = str(
        auth if auth is not None else ledger.parent / "no-authorizations.json"
    )
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )

def seed_telemetry_db(path: Path, *, cost: float = 1.25, tokens_in: int = 111,
                      tokens_out: int = 222, turns: int = 3) -> Path:
    """A throwaway telemetry source: `turns` assistant messages, inside any live window.

    `tools/telemetry.py` reads the OpenCrabs database through `OPENCRABS_DB_PATH` and
    takes `cost`/`input_tokens`/`token_count` as SUMs over `role = 'assistant'` rows
    while `turns` is that query's COUNT(*) — so the three totals and the turn count come
    from DIFFERENT aggregates and cannot be set by one row. The seed therefore writes one
    row carrying the totals and `turns - 1` further assistant rows worth zero, which move
    the count without moving the sums. A seed that got this wrong would make a probe
    assert a number the tool never produces, which is how the first version of the
    prose-as-data probe failed.
    """
    import sqlite3

    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE messages (created_at INTEGER, cost REAL, input_tokens INTEGER, "
        "token_count INTEGER, role TEXT, session_id TEXT)"
    )
    conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, 'assistant', 'probe')",
        (now, cost, tokens_in, tokens_out),
    )
    for _ in range(max(0, turns - 1)):
        conn.execute(
            "INSERT INTO messages VALUES (?, 0.0, 0, 0, 'assistant', 'probe')",
            (now,),
        )
    conn.commit()
    conn.close()
    return path

def rows(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]

def close_row(ledger: Path) -> dict:
    """The CLOSE row a probe just appended — never simply the last row.

    `append --event close` writes TWO rows: the close itself, then the SETTLEMENT RECEIPT
    that records the verified population the sequence check covered. The receipt follows
    the row it receipts by construction, so `[-1]` is the receipt and a probe asking about
    the close row's own detail must NAME the row it means. This helper is that name.
    """
    closes = [r for r in rows(ledger) if r.get("event") == "close"]
    return closes[-1] if closes else {}

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

def check_registered_in_the_audit() -> None:
    """An unregistered gate never runs — assert this one is wired (P29, issue #59)."""
    audit = (REPO / "tools" / "audit.py").read_text(encoding="utf-8")
    check(
        "this gate is registered in tools/audit.py",
        "tests/test_ledger.py" in audit,
        "an unregistered gate never runs (P29)",
    )


def main() -> int:
    print("registration — an unregistered gate never runs (P29)")
    check_registered_in_the_audit()

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.jsonl"

        # --- refs: a typed pointer, and the existence check at the write path -----
        # W2 of the ledger-instrument plan. The append-time check is the half only the
        # lock can do; the verify leg is the half only a read can do.
        print("refs — a typed pointer, and the existence check at the write path")
        # A SEPARATE ledger: the concurrent-append fixture below asserts an exact
        # row count, so a probe appending to `ledger` breaks a NEIGHBOUR test
        # rather than its own (measured 2026-09-27: 20 -> 22 rows).
        refs_ledger = Path(tmp) / "refs.jsonl"
        run(refs_ledger, "append", "--event", "claim", "--actor", "triage",
            "--subject", "#1", "--detail", "first")
        r2 = run(refs_ledger, "append", "--event", "dispatch", "--actor", "triage",
                 "--subject", "#2", "--detail", "points at row 1",
                 "--ref", "row:1", "--ref", "subject:#1")
        check("a row carrying refs appends", r2.returncode == 0,
              r2.stderr.strip()[:140])
        got = rows(refs_ledger)
        check("refs are stored as typed pointers",
              len(got) == 2 and got[1].get("refs") == [{"row": "1"}, {"subject": "#1"}],
              json.dumps(got[1].get("refs")) if len(got) > 1 else "no second row")
        check("a six-key row stays valid (the field is additive)",
              "refs" not in got[0],
              json.dumps(sorted(got[0].keys())) if got else "")

        bad = run(refs_ledger, "append", "--event", "dispatch", "--actor", "triage",
                  "--subject", "#3", "--detail", "dangling", "--ref", "row:999")
        check("a dangling row ref is REFUSED at append",
              bad.returncode != 0 and "does not exist" in bad.stderr,
              bad.stderr.strip()[:160])
        check("the refused append wrote nothing", len(rows(refs_ledger)) == 2,
              f"{len(rows(refs_ledger))} row(s)")

        malformed = run(refs_ledger, "append", "--event", "dispatch", "--actor", "triage",
                        "--subject", "#4", "--detail", "malformed", "--ref", "nope")
        check("a malformed ref is refused with the kinds named",
              malformed.returncode != 0 and "KIND:VALUE" in malformed.stderr,
              malformed.stderr.strip()[:140])

        # A ref that was VALID AT APPEND and broken afterwards is visible only to the
        # verify leg -- built by hand, because no lawful write path can produce it.
        broken = Path(tmp) / "broken.jsonl"
        broken.write_text(
            "\n".join(json.dumps(x) for x in [
                {"n": 1, "ts": "2026-09-27T00:00:00Z", "event": "claim",
                 "actor": "triage", "subject": "#1", "detail": "a"},
                {"n": 2, "ts": "2026-09-27T00:00:01Z", "event": "dispatch",
                 "actor": "triage", "subject": "#2", "detail": "b",
                 "refs": [{"row": "99"}]},
            ]) + "\n"
        )
        v = run(broken, "verify")
        check("verify reports a ref that no longer resolves",
              v.returncode != 0 and "dangling ref row:99" in v.stdout,
              v.stdout.strip()[-200:])
        check("verify prints the ref population it examined",
              "refs examined: 1" in v.stdout,
              [ln for ln in v.stdout.splitlines() if "refs examined" in ln])

        undecl = Path(tmp) / "undecl.jsonl"
        undecl.write_text(
            "\n".join(json.dumps(x) for x in [
                {"n": 1, "ts": "2026-09-27T00:00:00Z", "event": "claim",
                 "actor": "triage", "subject": "#1", "detail": "a",
                 "refs": [{"nonsense": "x"}]},
            ]) + "\n"
        )
        v2 = run(undecl, "verify")
        check("verify reports an undeclared ref kind",
              v2.returncode != 0 and "is not declared" in v2.stdout,
              v2.stdout.strip()[-160:])

        # --- declared vocabulary: a member's event, without a fork ------------------
        # W3. The point is not that `ack` is special; it is that a member's vocabulary
        # is DECLARED rather than forked into this file.
        print("declared vocabulary \u2014 a member event a law for, not a fork")
        # THE DECLARATION IS POINTED AT BY ENV, not by staging a copy of the tool: the
        # `run` helper invokes TOOL, so a staged tree would never be executed and the
        # probe would silently test the wrong file (measured 2026-09-27, and the first
        # cut of this check did exactly that). OC_REFS_KINDS_PATH is the module's own
        # seam, the same shape OC_ACTORS_PATH and OC_LEDGER_PATH already use.
        decl_tree = Path(tmp) / "decl-tree"
        decl_tree.mkdir(parents=True, exist_ok=True)
        decl_ledger = decl_tree / "ledger.jsonl"
        decl_file = decl_tree / "refs-kinds.json"
        DECL = {"OC_REFS_KINDS_PATH": str(decl_file)}

        r = run(decl_ledger, "append", "--event", "ack", "--actor", "triage",
                "--subject", "#1", "--detail", "declared event",
                extra_env=DECL)
        check("an event NOT declared is refused, by name, naming the route",
              r.returncode != 0 and "unknown event 'ack'" in r.stderr
              and "ledger-refs-kinds.json" in r.stderr,
              r.stderr.strip()[:170])

        decl_file.write_text(json.dumps({"events": ["ack"], "kinds": ["contour"]}))
        r = run(decl_ledger, "append", "--event", "ack", "--actor", "triage",
                "--subject", "#1", "--detail", "declared event",
                extra_env=DECL)
        check("the SAME event is lawful once declared",
              r.returncode == 0, r.stderr.strip()[:150])

        r = run(decl_ledger, "append", "--event", "ack", "--actor", "triage",
                "--subject", "#2", "--detail", "a declared member kind",
                "--ref", "contour:zamer/01", extra_env=DECL)
        check("a declared member kind travels as an opaque ref",
              r.returncode == 0, r.stderr.strip()[:150])

        v = run(decl_ledger, "verify", extra_env=DECL)
        check("verify accepts a ledger already holding the declared event's rows",
              v.returncode == 0 and "refs examined: 1" in v.stdout,
              v.stdout.strip()[-150:])

        decl_file.unlink()
        r = run(decl_ledger, "append", "--event", "score", "--actor", "triage",
                "--subject", "#3", "--detail", "core event, no declaration present",
                extra_env=DECL)
        check("core events stand alone when no declaration exists",
              r.returncode == 0, r.stderr.strip()[:150])

        # A declaration ADDS; it never removes or redefines a core entry. Without this
        # leg a member could shadow `close` and the sequence law would silently stop
        # applying to a factory's own lifecycle.
        decl_file.write_text(json.dumps({"events": [], "kinds": []}))
        r = run(decl_ledger, "append", "--event", "close", "--actor", "triage",
                "--subject", "#9", "--detail", "core event against an empty declaration",
                extra_env=DECL)
        check("a core event is still refused by its own law, not shadowed by a declaration",
              r.returncode != 0, r.stderr.strip()[:120] or r.stdout.strip()[-120:])


        # --- the authorization declaration: a factory's OWN lane, without a fork ---------
        # #193. The matrix was a hard constant while membership had `tools/actors.txt`, so a
        # factory's own lane could be DECLARED as a lane and still be refused at append. This
        # gives authorization the same seam. THE BOUND, stated rather than papered over: the
        # matrix binds a DERIVED actor, and a fixture's actor is `declared` by construction
        # (reaching the live ledger requires both overrides absent), so no fixture can drive a
        # real lane's derived append. What is proven here is the PREDICATE the write path now
        # calls and the composition rule it obeys; the derived leg is exercised by the first
        # real lane to write, which is why the seam's absence was invisible for so long.
        # --- the authorization declaration: a factory's OWN lane, without a fork ---------
        # #193. The matrix was a hard constant while membership had `tools/actors.txt`, so a
        # factory's own lane could be DECLARED as a lane and still be refused at append. This
        # gives authorization the same seam.
        #
        # THE BOUND, stated rather than papered over: the matrix binds a DERIVED actor, and a
        # fixture's actor is `declared` by construction — reaching the live ledger requires both
        # overrides absent — so no fixture can drive a real lane's refusal. What is proven here
        # is the PREDICATE the write path calls and the composition rule it obeys; the derived
        # leg is exercised by the first real lane to write, which is why the seam's absence was
        # invisible for so long.
        print("authorization declaration \u2014 a factory's own lane, declared not forked")
        auth_tree = Path(tmp) / "auth-tree"
        auth_tree.mkdir(parents=True, exist_ok=True)
        auth_file = auth_tree / "authorizations.json"
        auth_actors = auth_tree / "actors.txt"
        auth_actors.write_text("surveys\ninstrument\n")
        AUTH = {"OC_AUTHORIZATIONS_PATH": str(auth_file)}
        auth_kw = {"actors": auth_actors}

        def predicate(event, repo=None):
            """Read the composed predicate the WRITE PATH calls, from its one home."""
            code = (
                "import sys, pathlib; sys.path.insert(0, 'tools');"
                "import ledger_declaration as ld;"
                "print('|'.join(ld.authorized_for_event(pathlib.Path(sys.argv[1]), sys.argv[2])))"
            )
            return subprocess.run(
                [sys.executable, "-c", code, str(repo or auth_tree), event],
                capture_output=True, text=True,
                env={**os.environ, **AUTH}, cwd=str(REPO),
            )

        # ARM 1: a lane DECLARED here is a MEMBER, without touching tools/actors.txt's role
        # list — the membership half the declaration now carries.
        auth_file.write_text(json.dumps({"actors": ["instrument"], "by_event": {}}))
        got = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'tools'); import ledger;"
             "print('instrument' in ledger.known_actors())"],
            capture_output=True, text=True,
            env={**os.environ, **AUTH, "OC_ACTORS_PATH": str(auth_tree / "no-actors.txt")},
            cwd=str(REPO),
        )
        check("a lane declared in the authorizations file is a MEMBER",
              got.returncode == 0 and got.stdout.strip() == "True",
              got.stdout.strip() or got.stderr.strip()[-150:])

        # ARM 2: with NO declaration the predicate is EXACTLY the core floor — the shipped
        # state of a new factory, unchanged by this seam.
        auth_file.unlink()
        got = predicate("ruling")
        check("with no declaration the predicate is exactly the core floor",
              got.returncode == 0 and set(got.stdout.strip().split("|")) == {"hq", "owner"},
              got.stdout.strip() or got.stderr.strip()[-150:])

        # ARM 3: a declaration ADDS. It must never evict a core role, or a factory could
        # shadow its own law by declaring one lane for an event.
        auth_file.write_text(json.dumps(
            {"actors": ["instrument"], "by_event": {"ruling": ["instrument"]}}))
        got = predicate("ruling")
        roles = set(got.stdout.strip().split("|"))
        check("a declaration ADDS the lane and never removes a core entry",
              got.returncode == 0 and {"hq", "owner", "instrument"} <= roles,
              got.stdout.strip() or got.stderr.strip()[-150:])

        # ARM 4: a MALFORMED declaration FAILS LOUDLY, never reads as none. A factory whose own
        # lanes silently vanished on a typo would get a membership error naming no file.
        auth_file.write_text("{ this is not json")
        r = run(auth_tree / "ledger.jsonl", "append", "--event", "claim", "--actor", "triage",
                "--subject", "#2", "--detail", "malformed declaration",
                extra_env=AUTH, **auth_kw)
        check("a malformed declaration fails loudly rather than reading as none",
              r.returncode != 0 and "not valid JSON" in (r.stderr or ""),
              (r.stderr or r.stdout).strip()[-160:])

        # ARM 5: the tool still RUNS with the declaration absent — absent means none, and a
        # factory that declares nothing keeps exactly the behaviour it had.
        auth_file.unlink()
        r = run(auth_tree / "ledger.jsonl", "append", "--event", "intake", "--actor", "triage",
                "--subject", "#3", "--detail", "no declaration present",
                extra_env=AUTH, **auth_kw)
        check("absent declaration means none, and the tool still runs",
              r.returncode == 0, (r.stderr or r.stdout).strip()[-140:])

        print("concurrent append \u2014 the single-writer property")
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
        # P4 IS THE DELIBERATE REVERSAL, not an omission (2026-09-25, plan 2646d31a
        # step 5). This shape WAS refused: `claim` before `intake` was read as a
        # defect. It is not one, because the two rows belong to two lanes with
        # independent wake latencies -- intake is Triage's and the claim is the
        # implementer's -- so the inversion is the designed outcome of a latency gap.
        # The case is kept and its expectation INVERTED rather than deleted, so a
        # change that reintroduces the clause REDs here and must argue with this.
        seq_case("P4 a claim before its intake is ACCEPTED (the deliberate reversal)",
                 (("claim", "#4"), ("intake", "#4"), ("close", "#4")), 0, ())
        seq_case("P4b a claim AFTER its close is still refused (presence, positional)",
                 (("intake", "#4b"), ("close", "#4b"), ("claim", "#4b")), 1, ("#4b", "claim"))

        # THE DISPATCH LEG (#45, ruling n=255, refined n=524). `verify` modelled intake ->
        # claim -> close and `dispatch` was no leg of that model, so the ledger could say
        # "this was routed" for a subject it could not say "was this taken in?" for. The
        # leg is FORWARD-ONLY from a DECLARED BOUNDARY, so a probe must control the row's
        # `ts`: `write_ledger`'s fixed 2026-09-12 is pre-boundary and would be excused,
        # which is exactly the trap a probe that used it would fall into.
        print("\nthe dispatch leg — ordering, observations, malformed subjects (#45)")
        POST = "2027-01-01T00:00:00Z"   # after any plausible landing boundary
        PRE = "2026-09-12T00:00:00Z"    # the boundary's own pre-image

        def write_ledger_ts(path: Path, *rows: tuple[str, str, str]) -> None:
            """(event, subject, ts) rows, numbered 1..N — the sequence leg's own fixture."""
            path.write_text(
                "\n".join(
                    json.dumps({"n": i, "ts": ts, "event": event, "actor": "hq",
                                "subject": subject, "detail": "probe"})
                    for i, (event, subject, ts) in enumerate(rows, 1)
                ) + "\n",
                encoding="utf-8",
            )

        def dispatch_case(name: str, rows: tuple[tuple[str, str, str], ...],
                          want_rc: int, want: tuple[str, ...]) -> None:
            write_ledger_ts(seq, *rows)
            r = run(seq, "verify")
            ok = r.returncode == want_rc and all(s in r.stdout for s in want)
            lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
            check(name, ok, lines[1].strip() if len(lines) > 1 else (lines[0] if lines else ""))

        dispatch_case("P5 a work-unit dispatch with no intake before it is REFUSED",
                      (("dispatch", "#5", POST),), 1, ("#5", "dispatch of #5"))
        dispatch_case("P6 the same ledger with the dispatch row REMOVED passes",
                      (("intake", "#6", PRE),), 0, ())
        dispatch_case("P7 an OBSERVATION dispatch is legal and never swept in",
                      (("dispatch", "advisory-sweep-2026-09-18", POST),), 0,
                      ("1 observation", "dispatch rows examined"))
        dispatch_case("P8 a MALFORMED subject is REPORTED, and the ledger stays clean",
                      (("dispatch", "77", POST),), 0,
                      ("malformed subject", "77", "immutable once pushed"))
        dispatch_case("P8b a HASH-LED non-strict subject is reported too",
                      (("dispatch", "#332-D5", POST),), 0, ("malformed subject", "#332-D5"))
        dispatch_case("P9 a PRE-boundary instance is EXCUSED and printed, never refused",
                      (("dispatch", "#9", PRE),), 0, ("excused: dispatch of #9", "pre-boundary"))
        dispatch_case("P10 the population is printed beside the verdict",
                      (("dispatch", "advisory-x", POST),), 0,
                      ("dispatch rows examined:", "forward-only from"))
        print("\nthe close-row revision — declared at the WRITE PATH (#187)")
        # The invariant `close_row_revision` was enforced by the gate and by NOTHING at the
        # write path, so four instances in one session were each repaired by a SECOND append
        # (`n=1065`->`n=1079`, `n=1126`->`n=1135`, `n=1258`->`n=1262`, `n=1260`->`n=1263`)
        # and the rate was not falling. These probes drive the REAL command, and the pair of
        # arms is the ruling's own discriminator: the refusal reads the CANONICAL RUN, so a
        # revision merely MENTIONED in prose is refused while one the run DECLARES is
        # accepted. Both arms are required — a permissive refusal, satisfiable by quoting any
        # hex-shaped token, would pass a one-sided probe here and accept a row whose revision
        # the existence leg never resolves. Three live rows are exactly that shape.
        from field_predicate import declared_revision  # the shared predicate, one field one read
        rev_actors = Path(tmp) / "rev-actors.txt"
        rev_actors.write_text("worker\n", encoding="utf-8")
        # A throwaway telemetry source, for the reason the #88 block states: a probe that
        # read the LIVE database would pass or fail on this box's traffic rather than on the
        # code. My first cut of this block omitted the pin and the row it inspected carried
        # `tokens_in=22017218` — the live daemon's own totals.
        rev_db = seed_telemetry_db(Path(tmp) / "rev-telemetry.db")
        rev_env = {"OPENCRABS_DB_PATH": str(rev_db)}
        rev = Path(tmp) / "revision.jsonl"
        write_ledger(rev, ("intake", "#187"), ("claim", "#187"))
        before_rev = hashlib.md5(rev.read_bytes()).hexdigest()

        r = run(rev, "append", "--event", "close", "--actor", "worker", "--subject", "#187",
                "--detail", "Closed, and the revision is not stated anywhere.",
                actors=rev_actors, extra_env=rev_env)
        check("a close declaring no revision is REFUSED",
              r.returncode != 0, (r.stderr or r.stdout).strip()[:90])
        check("and the refusal names the token it wants",
              "head=<sha>" in (r.stderr + r.stdout), (r.stderr or r.stdout).strip()[:160])
        check("and it wrote NOTHING — the ledger is byte-identical by md5",
              hashlib.md5(rev.read_bytes()).hexdigest() == before_rev,
              f"{len(rows(rev))} row(s)")

        r = run(rev, "append", "--event", "close", "--actor", "worker", "--subject", "#187",
                "--detail", "Closed. The receipts describe revision "
                            "0123456789abcdef0123456789abcdef01234567 which resolves.",
                actors=rev_actors, extra_env=rev_env)
        check("a revision only MENTIONED in prose is REFUSED (the discriminator)",
              r.returncode != 0, (r.stderr or r.stdout).strip()[:90])
        check("and that refusal wrote nothing either",
              hashlib.md5(rev.read_bytes()).hexdigest() == before_rev,
              f"{len(rows(rev))} row(s)")

        # The accepting arm. Without it the probe would pass on a refusal that rejected
        # every close row — the one-sided shape that proves nothing about the predicate.
        r = run(rev, "append", "--event", "close", "--actor", "worker", "--subject", "#187",
                "--detail", "Closed with its receipts. "
                            "head=0123456789abcdef0123456789abcdef01234567",
                actors=rev_actors, extra_env=rev_env)
        check("a revision the CANONICAL RUN declares is ACCEPTED",
              r.returncode == 0, (r.stderr or r.stdout).strip()[:90])
        _rev_detail = close_row(rev).get("detail", "")
        # Asserted through the SHARED reader, not `declares_field`: that predicate answers
        # "has the author stated this TELEMETRY measurement" and parses the value for the
        # key's type, so it is False for every key outside the telemetry set — a mistake
        # this probe made first, and the reason the check reads the field's own predicate.
        check("and the row carries it in the run, beside the telemetry the tool appended",
              declared_revision(_rev_detail) == "0123456789abcdef0123456789abcdef01234567",
              _rev_detail[-90:])

        print("\nreconstructed claims — declared by token, printed, never collapsed")
        # A claim stamped after the work declares itself with the token
        # `claim=reconstructed` (#98, ruling n=602 PART 5), and `verify` prints those
        # rows beside its `excused:` lines. The declaration is MECHANICAL because a
        # declaration living only in prose can be counted only by reading prose — this
        # factory's own ruled class (#88 / n=405 clause 5). Three directions, and the
        # third is the one a one-sided probe misses: the line must APPEAR for a
        # token-bearing claim row, must be ABSENT without the token, and the verdict
        # outputs must not collapse into one.
        def set_detail(path: Path, index: int, detail: str) -> None:
            got = rows(path)
            got[index]["detail"] = detail
            path.write_text(
                "\n".join(json.dumps(row) for row in got) + "\n", encoding="utf-8")

        rec = Path(tmp) / "reconstructed.jsonl"
        write_ledger(rec, ("intake", "#98"), ("claim", "#98"), ("close", "#98"))
        r = run(rec, "verify")
        check("a ledger with no reconstruction prints no reconstructed line",
              r.returncode == 0 and "reconstructed claim:" not in r.stdout,
              r.stdout.strip().splitlines()[-1] if r.stdout else "")

        set_detail(rec, 1, "Taken on acceptance of the dispatch. claim=reconstructed")
        r = run(rec, "verify")
        # The printed form carries the RECOMPUTED INTERVAL since #115 (ruling n=687
        # clause 1): the interval moved from DECLARED to RECOMPUTED-AND-PRINTED, so the
        # line now names the row AND the interval the reader computed from the two rows'
        # own `ts` values. Asserting the row's own identity plus the `interval=` field is
        # the property; pinning the NUMBER would pin the fixture's clock, not the tool.
        check("a claim row carrying the token prints its reconstructed line",
              r.returncode == 0
              and "reconstructed claim: n=2 (subject #98) interval=" in r.stdout,
              r.stdout.strip().splitlines()[-1] if r.stdout else "")

        # The SCOPE: the token describes a CLAIM row, so a row of another event that
        # merely QUOTES it is not a reconstruction. Without this leg the predicate
        # would fire on the ruling row that defines the token (measured: n=602).
        quote = Path(tmp) / "rec-quoted.jsonl"
        write_ledger(quote, ("intake", "#98"), ("claim", "#98"), ("close", "#98"))
        set_detail(quote, 0, "States the token claim=reconstructed that n=602 defines.")
        r = run(quote, "verify")
        check("a non-claim row that quotes the token is not a reconstruction",
              r.returncode == 0 and "reconstructed claim:" not in r.stdout,
              r.stdout.strip().splitlines()[-1] if r.stdout else "")

        # Not collapsed: one ledger exercising BOTH a pre-gate exemption and a
        # reconstruction must print both, distinctly, on the clean path.
        both = Path(tmp) / "rec-both.jsonl"
        write_ledger(both, ("intake", "#6"), ("close", "#6"),
                     ("intake", "#98"), ("claim", "#98"), ("close", "#98"))
        set_detail(both, 3, "Taken on acceptance of the dispatch. claim=reconstructed")
        r = run(both, "verify")
        lines = r.stdout.strip().splitlines()
        check("clean, excused and reconstructed are three distinct outputs",
              r.returncode == 0
              and "ledger clean:" in r.stdout
              and "excused: #6 missing claim" in r.stdout
              and "reconstructed claim: n=4 (subject #98) interval=" in r.stdout
              and next((i for i, l in enumerate(lines) if "excused:" in l), 99)
                  < next((i for i, l in enumerate(lines) if "reconstructed claim:" in l), -1),
              " | ".join(l.strip() for l in lines))

        print("\nthe exemption's PROOF — an entry with none is not admittable")
        # #52 clause 3: EXEMPTIONS admits a POST-gate entry, and what ADMITS it is the
        # PROOF — an external receipt, never a restatement of the omission it excuses.
        # The rule is mechanical, so a proofless entry must excuse nothing: the omission
        # stays a problem and the refusal names the entry that failed to excuse it. Both
        # directions are probed, because a one-sided probe passes on a list that refuses
        # everything exactly as happily as on one that excuses everything.
        #
        # The seam is a staged COPY of the tree, and since 2026-09-25 the exemptions are a
        # DATA FILE (`docs/ledger-exemptions.json`) rather than a module constant -- so this
        # probe now varies exactly the surface a factory varies, and the declaration it
        # writes is the one production reads. The live surface is still never touched.
        def stage_with_exemptions(name: str, entries: list[dict]) -> Path:
            tree = Path(tmp) / name
            (tree / "tools").mkdir(parents=True)
            (tree / "evidence").mkdir()
            (tree / "docs").mkdir()
            stage_tool(TOOL, tree / "tools", LOCAL_TOOLS)
            (tree / "docs" / "ledger-exemptions.json").write_text(
                json.dumps({"exempt": entries}), encoding="utf-8")
            return tree / "tools" / "ledger.py"

        def exempt_run(tool: Path) -> subprocess.CompletedProcess:
            """Verify a ledger whose ONLY defect is a missing claim leg on #7."""
            tree = tool.parent.parent
            ledger = tree / "evidence" / "ledger.jsonl"
            write_ledger(ledger, ("intake", "#7"), ("close", "#7"))
            return subprocess.run(
                [sys.executable, str(tool), "verify"],
                capture_output=True, text=True, cwd=tree,
                env={**os.environ, "OC_LEDGER_PATH": str(ledger),
                     "OC_ACTORS_PATH": str(tree / "no-actors.txt")},
            )

        # The subject is this probe's own, so the entry it exercises can never be a
        # live one; the omission is the #6 shape — a close with no claim before it.
        proofless = stage_with_exemptions("exempt-proofless", [
            {"subject": "#7", "leg": "claim", "granted": "2026-09-19",
             "reason": "post-gate omission; the leg was never written", "proof": ""},
        ])
        r = exempt_run(proofless)
        check("a proofless entry excuses nothing",
              r.returncode != 0 and "excused:" not in r.stdout,
              (r.stdout + r.stderr).strip().splitlines()[-1][:100])
        check("and the refusal names the entry that failed to excuse it",
              "not admittable" in r.stdout and "#7/claim" in r.stdout,
              next((l.strip() for l in r.stdout.splitlines() if "admittable" in l), "")[:110])

        proven = stage_with_exemptions("exempt-proven", [
            {"subject": "#7", "leg": "claim", "granted": "2026-09-19",
             "reason": "post-gate omission; the leg was never written",
             "proof": "the ruling that granted it: ledger n=318"},
        ])
        r = exempt_run(proven)
        check("a proof-bearing entry excuses the omission and still prints it",
              r.returncode == 0 and "excused: #7 missing claim" in r.stdout,
              (r.stdout + r.stderr).strip().splitlines()[-1][:100])

        print("\nverify --against — the identity check is a command, not a discipline")
        # Clause 1 of the #52 ruling: a row's identity is immutable once pushed, because
        # `n` is what an external citation MEANS. The defence for that was a sentence a
        # reader had to reconstruct from git log; `--against` reads it. The probe needs a
        # real repository, because the command reads the committed blob through git —
        # and it uses a THROWAWAY one, so the live ledger is never the subject.
        cmp_repo = Path(tmp) / "cmprepo"
        (cmp_repo / "tools").mkdir(parents=True)
        (cmp_repo / "evidence").mkdir()
        stage_tool(TOOL, cmp_repo / "tools", LOCAL_TOOLS)
        cmp_tool = cmp_repo / "tools" / "ledger.py"
        cmp_ledger = cmp_repo / "evidence" / "ledger.jsonl"

        def cmp_git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-c", "user.email=probe@factory", "-c", "user.name=probe",
                 "-c", "commit.gpgsign=false", *args],
                cwd=cmp_repo, capture_output=True, text=True,
            )

        def cmp_run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, str(cmp_tool), *args],
                capture_output=True, text=True, cwd=cmp_repo,
                env={**os.environ, "OC_LEDGER_PATH": str(cmp_ledger),
                     "OC_ACTORS_PATH": str(cmp_repo / "no-actors.txt")},
            )

        def commit(text: str, message: str) -> None:
            cmp_ledger.write_text(text, encoding="utf-8")
            cmp_git("add", "-A")
            cmp_git("commit", "-q", "-m", message)

        def render(ledger_rows: list[dict]) -> str:
            return "".join(json.dumps(r) + "\n" for r in ledger_rows)

        def row(n: int, event: str, subject: str, ts: str = "2026-09-12T00:00:00Z",
                actor: str = "hq", detail: str = "probe") -> dict:
            return {"n": n, "ts": ts, "event": event, "actor": actor,
                    "subject": subject, "detail": detail}

        base = render([row(1, "intake", "#1"), row(2, "claim", "#1"), row(3, "close", "#1")])
        cmp_git("init", "-q")
        commit(base, "three rows")

        # (1) The #52 shape: a row KEEPS its number and becomes a different row. Plain
        # verify cannot see it — every structural property it checks still holds, and the
        # sequence is intact — which is the whole reason the clause needed a command.
        cmp_ledger.write_text(render([
            row(1, "intake", "#1"),
            row(2, "claim", "#1", ts="2026-09-12T00:00:02Z"),
            row(3, "close", "#1", ts="2026-09-12T00:00:01Z"),
        ]), encoding="utf-8")
        r = cmp_run("verify")
        check("a row that changed in place is invisible to plain verify",
              r.returncode == 0, r.stdout.strip().splitlines()[0][:90])
        r = cmp_run("verify", "--against", "HEAD")
        check("--against reports the identity change plain verify cannot see",
              r.returncode != 0 and "IDENTITY" in r.stdout and "n=2" in r.stdout,
              next((l.strip() for l in r.stdout.splitlines() if "IDENTITY" in l), "")[:110])

        # (2) A PERMUTATION — the shape a renumber actually takes in a ledger that stays
        # contiguous. Every number still exists, so nothing is added and nothing removed,
        # and plain verify is clean: two rows have swapped places and each number now
        # describes the other's work. Reporting that as two ordinary identity changes
        # would be true and useless; the reader needs to be told the rows MOVED.
        ordered = render([
            row(1, "intake", "#1"), row(2, "claim", "#1"),
            row(3, "intake", "#2"), row(4, "claim", "#2"),
        ])
        commit(ordered, "four rows")
        cmp_ledger.write_text(render([
            row(1, "intake", "#1"), row(2, "claim", "#1"),
            row(3, "claim", "#2"), row(4, "intake", "#2"),
        ]), encoding="utf-8")
        r = cmp_run("verify")
        check("a permuted ledger is invisible to plain verify",
              r.returncode == 0, r.stdout.strip().splitlines()[0][:90])
        r = cmp_run("verify", "--against", "HEAD")
        check("--against names permuted rows as RENUMBERED, not as identity changes",
              r.returncode != 0 and r.stdout.count("RENUMBERED") == 2
              and "IDENTITY" not in r.stdout,
              " | ".join(l.strip() for l in r.stdout.splitlines() if "RENUMBERED" in l)[:110])

        # (2b) The other move shape: a number VACATED. The row survives, its old number
        # does not exist any more, and the report says so instead of describing one fact
        # as a deletion beside an insertion. (A contiguous ledger cannot produce this —
        # the tail shifts but every number survives — which is why the branch needs a
        # probe of its own; plain verify also flags the gap, and the point here is the
        # SHAPE of the report, not that the file is otherwise clean.)
        commit(base, "back to the three-row ledger")
        cmp_ledger.write_text(render([
            row(1, "intake", "#1"), row(2, "claim", "#1"), row(4, "close", "#1"),
        ]), encoding="utf-8")
        r = cmp_run("verify", "--against", "HEAD")
        check("a vacated number is reported as a move, not as a delete beside an insert",
              r.returncode != 0 and "RENUMBERED  n=3 -> n=4" in r.stdout
              and "REMOVED" not in r.stdout,
              next((l.strip() for l in r.stdout.splitlines() if "RENUMBERED" in l), "")[:110])

        # (3) Content is the OTHER question. Clause 2 admits a correction to a detail,
        # and the row discloses it with its own REPAIR NOTE — so the command reports the
        # change and distinguishes a disclosed one from a silent edit.
        disclosed = base.replace('"detail": "probe"',
                                 '"detail": "probe. REPAIR NOTE: the token was appended, '
                                 'identity untouched"', 1)
        cmp_ledger.write_text(disclosed, encoding="utf-8")
        r = cmp_run("verify", "--against", "HEAD")
        check("a disclosed content change is reported and is not fatal",
              r.returncode == 0 and "CONTENT" in r.stdout and "disclosed by a REPAIR NOTE" in r.stdout,
              next((l.strip() for l in r.stdout.splitlines() if "CONTENT" in l), "")[:110])

        cmp_ledger.write_text(base.replace('"detail": "probe"', '"detail": "quietly edited"', 1),
                              encoding="utf-8")
        r = cmp_run("verify", "--against", "HEAD")
        check("an undisclosed content change is fatal",
              r.returncode != 0 and "NO DISCLOSURE" in r.stdout,
              next((l.strip() for l in r.stdout.splitlines() if "CONTENT" in l), "")[:110])

        # (4) Growth is the ledger's normal state, so an addition is reported, never fatal.
        cmp_ledger.write_text(base + json.dumps(
            {"n": 4, "ts": "2026-09-12T00:00:00Z", "event": "run", "actor": "hq",
             "subject": "#1", "detail": "probe"}) + "\n", encoding="utf-8")
        r = cmp_run("verify", "--against", "HEAD")
        check("an added row is reported and is not fatal",
              r.returncode == 0 and "ADDED" in r.stdout and "n=4" in r.stdout,
              next((l.strip() for l in r.stdout.splitlines() if "ADDED" in l), "")[:110])

        # (5) Fail LOUD, never open. A revision that cannot be read is not an empty
        # comparison: reporting "no change" over a population of zero is the shape this
        # repo has already ruled against (a truncated log window is not an empty one).
        r = cmp_run("verify", "--against", "no-such-revision")
        check("an unreadable revision fails loudly instead of comparing nothing",
              r.returncode != 0 and "no change" not in r.stdout
              and "cannot read" in (r.stdout + r.stderr),
              (r.stdout + r.stderr).strip().splitlines()[-1][:110])

        # (6) The clean path still reports its own comparison, so "compared and equal" is
        # an output rather than a silence.
        cmp_ledger.write_text(base, encoding="utf-8")
        r = cmp_run("verify", "--against", "HEAD")
        check("an unchanged ledger says so, rather than saying nothing",
              r.returncode == 0 and "no change" in r.stdout,
              r.stdout.strip().splitlines()[-1][:110])

        print("\nthe append-time guard — a revert is loud, not silent")
        # The lock serialises the appenders, not the file they append to. A
        # revert lowers the working file OUTSIDE the lock and the next lawful
        # append re-issues a committed `n`. The guard reads the COMMITTED
        # lineage, so this probe needs a real repository: a copy of the tool
        # inside a throwaway git repo, where the tool's REPO resolves to that
        # repo's root and the live surface is never touched.
        guard_repo = Path(tmp) / "guardrepo"
        (guard_repo / "tools").mkdir(parents=True)
        (guard_repo / "evidence").mkdir()
        stage_tool(TOOL, guard_repo / "tools", LOCAL_TOOLS)
        guard_tool = guard_repo / "tools" / "ledger.py"
        guard_ledger = guard_repo / "evidence" / "ledger.jsonl"

        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-c", "user.email=probe@factory", "-c", "user.name=probe",
                 "-c", "commit.gpgsign=false", *args],
                cwd=guard_repo, capture_output=True, text=True,
            )

        def guard_run(*args: str) -> subprocess.CompletedProcess:
            env = {**os.environ, "OC_LEDGER_PATH": str(guard_ledger)}
            env["OC_ACTORS_PATH"] = str(guard_repo / "no-actors.txt")
            return subprocess.run(
                [sys.executable, str(guard_tool), *args],
                capture_output=True, text=True, env=env, cwd=guard_repo,
            )

        write_ledger(guard_ledger, ("intake", "#1"), ("claim", "#1"), ("close", "#1"))
        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "three rows")

        # The revert, in the #57 shape exactly: three rows committed, two in the
        # working file, so the next append would re-issue n=3.
        lines = guard_ledger.read_text(encoding="utf-8").splitlines(keepends=True)
        guard_ledger.write_text("".join(lines[:2]), encoding="utf-8")
        r = guard_run("append", "--event", "run", "--actor", "hq",
                      "--subject", "after-revert", "--detail", "probe")
        err = r.stderr.strip()
        check("a reverted working file refuses the append", r.returncode != 0, err[:90])
        check("the refusal names the first divergent row",
              "row 3" in err and "'#1'" in err, err[:140])
        check("the refused append wrote nothing",
              len(rows(guard_ledger)) == 2, f"{len(rows(guard_ledger))} row(s)")

        # Editing already-committed history is the other fatal shape.
        guard_ledger.write_text("".join(lines), encoding="utf-8")
        mutated = rows(guard_ledger)
        mutated[1]["subject"] = "#tampered"
        guard_ledger.write_text(
            "\n".join(json.dumps(row) for row in mutated) + "\n", encoding="utf-8")
        r = guard_run("append", "--event", "run", "--actor", "hq",
                      "--subject", "after-edit", "--detail", "probe")
        err = r.stderr.strip()
        check("an edited committed row refuses the append", r.returncode != 0, err[:90])
        check("the refusal names the edited row",
              "row 2" in err and "#tampered" in err, err[:140])

        # Fail-open: no committed lineage to read must never block a factory.
        fresh = Path(tmp) / "freshfactory"
        (fresh / "tools").mkdir(parents=True)
        (fresh / "evidence").mkdir()
        stage_tool(TOOL, fresh / "tools", LOCAL_TOOLS)
        fresh_ledger = fresh / "evidence" / "ledger.jsonl"
        r = subprocess.run(
            [sys.executable, str(fresh / "tools" / "ledger.py"), "append",
             "--event", "genesis", "--actor", "owner",
             "--subject", "genesis", "--detail", "the surface came into existence"],
            capture_output=True, text=True, cwd=fresh,
            env={**os.environ, "OC_LEDGER_PATH": str(fresh_ledger),
                 "OC_ACTORS_PATH": str(fresh / "no-actors.txt")},
        )
        check("no committed lineage: the append proceeds (fail-open)",
              r.returncode == 0, r.stderr.strip()[:90])
        check("no committed lineage: the guard warns",
              "fail-open" in r.stderr, r.stderr.strip()[:90])
        check("the fail-open append landed",
              len(rows(fresh_ledger)) == 1, f"{len(rows(fresh_ledger))} row(s)")

        print("\nthe repair path — one lawful correction, and the refusals that carry it")
        # The declaration is FACTORY DATA, so read it rather than restating the
        # timestamp: a probe that hardcodes the boundary reds the day the factory
        # moves its own declaration, and that red would name this gate instead of
        # the decision it is describing (#87).
        #
        # AND READ IT THROUGH THE SHARED READER, which is the part this probe got
        # wrong: indexing the declaration directly raised `KeyError: 'close_row_revision'`
        # on a bootstrapped factory, which has adopted no invariant yet. Measured
        # 2026-09-25 on a clean fixture built from BOOTSTRAP step 4b — so a factory
        # following the step exactly could not run its own ledger gate, and the failure
        # named this gate rather than the absence it was describing. The shipped example
        # PROMISES the skip ("the gate SKIPS with a stated reason when a key is absent"),
        # and `tests/ledger_boundary.py` implements it; this call site bypassed it.
        # `SkipGate` carries the stated reason, and the caller prints it and exits 0 —
        # an absence, never a silent pass.
        try:
            declared_dt, declared = ledger_boundary.declared_boundary(REPO, "close_row_revision")
        except ledger_boundary.SkipGate as exc:
            print(f"  SKIP  the repair-path probes — {exc}")
            declared_dt = None
        boundary_dt = declared_dt
        if boundary_dt is not None:
            post_ts = (boundary_dt + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        probe_sha = "a" * 40

        if boundary_dt is None:
            # No declared boundary, so the repair path cannot be exercised: the
            # declaration is factory data and its absence is a legitimate state.
            # Stated, never silent — the same contract the shipped example promises.
            pass
        else:
            def write_repair_ledger(path: Path, ts: str) -> None:
                """intake/claim/close for one subject, every row at `ts`."""
                path.write_text(
                    "\n".join(
                        json.dumps({
                            "n": i, "ts": ts, "event": event, "actor": "worker",
                            "subject": "#80", "detail": "probe",
                        })
                        for i, event in enumerate(("intake", "claim", "close"), 1)
                    ) + "\n",
                    encoding="utf-8",
                )

            # A row that PREDATES the declared boundary is refused, and the refusal
            # names the boundary it refuses on. `write_ledger` stamps 2026-09-12, which
            # is before every boundary this factory has declared.
            write_ledger(ledger, ("intake", "#1"), ("claim", "#1"), ("close", "#1"))
            r = run(ledger, "repair", "--actor", "worker", "--n", "3", "--append-detail", f"head={probe_sha}",
                    "--note", "probe")
            err = r.stderr.strip()
            check("a pre-boundary row refuses repair", r.returncode != 0, err[:90])
            check("the refusal names the boundary it refuses on", declared in err, err[:170])
            check("the refused repair wrote nothing", len(rows(ledger)) == 3,
                  f"{len(rows(ledger))} row(s)")

            # A repair with no stated reason is refused. Run against a POST-boundary
            # row, so the only thing the refusal can be about is the missing note.
            write_repair_ledger(ledger, post_ts)
            r = run(ledger, "repair", "--actor", "worker", "--n", "3", "--append-detail", f"head={probe_sha}")
            err = r.stderr.strip()
            check("a repair with no --note is refused", r.returncode != 0, err[:90])
            check("the refusal names --note as what is missing", "--note" in err, err[:140])
            check("the refused repair wrote nothing", len(rows(ledger)) == 3,
                  f"{len(rows(ledger))} row(s)")

            # A lawful repair lands, changes only `detail`, appends exactly one `run`
            # row naming the row and the note, and `verify` accepts the result.
            identity = ("n", "ts", "event", "actor", "subject")
            before = rows(ledger)[2]
            r = run(ledger, "repair", "--actor", "worker", "--n", "3", "--append-detail", f"head={probe_sha}",
                    "--note", "the row omitted the revision its receipts describe")
            err = r.stderr.strip()
            check("a post-boundary repair succeeds", r.returncode == 0, err[:140])
            after_rows = rows(ledger)
            after = after_rows[2]
            moved = [f for f in identity if before[f] != after[f]]
            check("the repaired row's identity is untouched", not moved,
                  f"{[(f, before[f], after[f]) for f in moved]}")
            check("the detail gained the appended field",
                  after["detail"].endswith(f"head={probe_sha}"), after["detail"][-60:])
            check("the field is a separate token, not welded to the previous one",
                  f" head={probe_sha}" in after["detail"], after["detail"][-70:])
            run_rows = [row for row in after_rows if row["event"] == "run"]
            check("exactly one run row was appended", len(run_rows) == 1, f"{len(run_rows)} run row(s)")
            check("the run row names the repaired row", "n=3" in run_rows[0]["detail"],
                  run_rows[0]["detail"][:90])
            check("the run row carries the note",
                  "the row omitted the revision its receipts describe" in run_rows[0]["detail"],
                  run_rows[0]["detail"][:90])
            check("the ledger gained exactly one row", len(after_rows) == 4,
                  f"{len(after_rows)} row(s)")
            v = run(ledger, "verify")
            check("verify accepts the repaired ledger", v.returncode == 0, v.stderr.strip()[:90])

            # A repair must not DISPLACE the row's canonical trailer (#91, ruled at ledger
            # n=572 PART 3). The trailer is POSITIONAL, so text appended AFTER it terminates
            # the run and the row's declared telemetry leaves the trailing run that every
            # trailer-scoped reader stops at — measured on the live n=303, whose telemetry
            # was canonical until a repair note was appended after it. Both append shapes are
            # probed, because the tool cannot know which it was handed and must be correct
            # for both: a PROSE note (the shape that broke n=303) and a `key=value` field
            # (the shape that has always been safe, so a fix that only handled prose would
            # regress it silently).
            sys.path.insert(0, str(REPO / "tools"))
            from field_predicate import declared_telemetry, trailer_tokens  # noqa: E402

            trailer = "cost_usd=1.2500 tokens_out=111 turns=3"
            for label, append_detail in (
                ("a PROSE append", "REPAIR NOTE (probe): the row omitted its revision."),
                ("a key=value append", f"head={probe_sha}"),
            ):
                displace = Path(tmp) / f"displace-{label.split()[1]}.jsonl"
                write_repair_ledger(displace, post_ts)
                written = rows(displace)
                written[2]["detail"] = f"Closed. {trailer}"
                displace.write_text(
                    "\n".join(json.dumps(row) for row in written) + "\n", encoding="utf-8"
                )
                r = run(displace, "repair", "--actor", "worker", "--n", "3", "--append-detail", append_detail,
                        "--note", "probe: the trailer must survive the repair")
                err = r.stderr.strip()
                check(f"{label} is accepted", r.returncode == 0, err[:140])
                detail = rows(displace)[2]["detail"]
                keys = dict(declared_telemetry(detail))
                check(f"{label} keeps the telemetry inside the trailing run",
                      keys == {"cost_usd": "1.2500", "tokens_out": "111", "turns": "3"},
                      f"declared={keys}")
                check(f"{label} leaves the run as the detail's tail",
                      detail.endswith(trailer), detail[-70:])
                check(f"{label} still lands its text (the probe is not vacuous)",
                      append_detail in detail, detail[:90])
                check(f"{label} keeps the original telemetry as a contiguous tail of the run",
                      " ".join(trailer_tokens(detail)).endswith(trailer),
                      " ".join(trailer_tokens(detail)))

            # The complementary half: a detail with NO canonical run has nothing to displace,
            # so the historic append-at-the-end behaviour stands and the field still lands as
            # its own token. Without this the fix could "protect" an absent trailer by
            # inserting into the middle of prose.
            norun = Path(tmp) / "displace-norun.jsonl"
            write_repair_ledger(norun, post_ts)
            plain = rows(norun)
            plain[2]["detail"] = "Closed with no trailer at all"
            norun.write_text("\n".join(json.dumps(row) for row in plain) + "\n", encoding="utf-8")
            r = run(norun, "repair", "--actor", "worker", "--n", "3", "--append-detail", f"head={probe_sha}",
                    "--note", "probe: no run to protect")
            check("a runless detail still repairs", r.returncode == 0, r.stderr.strip()[:140])
            check("a runless detail appends at the end, as a separate token",
                  rows(norun)[2]["detail"] == f"Closed with no trailer at all head={probe_sha}",
                  rows(norun)[2]["detail"])

            # The RE-DECLARATION refusal (#104, ruled at ledger n=620 PART 4). A `key=value`
            # append extends the canonical run only when the key is NEW. An append that
            # re-declares a key the row's run already carries leaves one field with two values
            # and no canonical reading: a consumer taking the last occurrence reads the
            # appended one while the row's own declaration still stands beside it. The refusal
            # happens BEFORE any write, so the ledger is byte-identical afterwards — proved by
            # CHECKSUM, because "the file looks unchanged" is an eye, not a receipt.
            redeclare = Path(tmp) / "redeclare.jsonl"
            write_repair_ledger(redeclare, post_ts)
            seeded = rows(redeclare)
            seeded[2]["detail"] = (
                f"Closed. Receipts taken at head={'b' * 40} cost_usd=1.2500 turns=3"
            )
            redeclare.write_text(
                "\n".join(json.dumps(row) for row in seeded) + "\n", encoding="utf-8"
            )
            digest_before = hashlib.md5(redeclare.read_bytes()).hexdigest()
            r = run(redeclare, "repair", "--actor", "worker", "--n", "3", "--append-detail", f"head={'c' * 40}",
                    "--note", "probe: a re-declaring append must be refused")
            err = r.stderr.strip()
            check("a re-declaring --append-detail is refused", r.returncode != 0, err[:90])
            check("the refusal names the key it would re-declare", "'head'" in err, err[:220])
            check("the refusal names the row", "n=3" in err, err[:220])
            check("the refused repair left the ledger BYTE-IDENTICAL",
                  hashlib.md5(redeclare.read_bytes()).hexdigest() == digest_before,
                  f"{digest_before} -> {hashlib.md5(redeclare.read_bytes()).hexdigest()}")
            check("the refused repair appended no run row", len(rows(redeclare)) == 3,
                  f"{len(rows(redeclare))} row(s)")

            # (c) THE GUARD IS NOT A FALSE-REFUSAL GENERATOR. A NEW key still repairs, and it
            # still lands BEFORE the run, so the row's declared telemetry survives the repair.
            newkey = Path(tmp) / "newkey.jsonl"
            newkey.write_text(redeclare.read_text(encoding="utf-8"), encoding="utf-8")
            r = run(newkey, "repair", "--actor", "worker", "--n", "3", "--append-detail", "board=closed",
                    "--note", "probe: a NEW key must still repair")
            check("an append introducing a NEW key still repairs",
                  r.returncode == 0, r.stderr.strip()[:140])
            newkey_detail = rows(newkey)[2]["detail"]
            check("the new key landed and the original telemetry is still the run's tail",
                  dict(declared_telemetry(newkey_detail)).get("turns") == "3"
                  and newkey_detail.endswith("cost_usd=1.2500 turns=3"), newkey_detail[-70:])

            # (d) THE GUARD BITES, and an exit 0 over an unchanged file shows nothing — so the
            # probe contrasts the SAME append against a row that does NOT declare the key.
            # Identical text, opposite verdicts: that is the only thing showing the refusal is
            # caused by the ROW's declaration rather than by the text alone.
            nohead = Path(tmp) / "nohead.jsonl"
            write_repair_ledger(nohead, post_ts)
            plain = rows(nohead)
            plain[2]["detail"] = "Closed with no revision field at all"
            nohead.write_text("\n".join(json.dumps(row) for row in plain) + "\n", encoding="utf-8")
            r = run(nohead, "repair", "--actor", "worker", "--n", "3", "--append-detail", f"head={'c' * 40}",
                    "--note", "probe: the same append, on a row that does not declare head")
            check("the SAME append repairs a row that does NOT declare the key",
                  r.returncode == 0, r.stderr.strip()[:140])
            check("...and the key it introduced is now in that row's run",
                  rows(nohead)[2]["detail"].endswith(f"head={'c' * 40}"),
                  rows(nohead)[2]["detail"][-70:])

            # The other side of the shared predicate: a prose append that merely NAMES a field
            # declares nothing (`head=` is a MENTION — `keyed_value` returns no value for it,
            # and `token_key` returns no key), so it must not be refused. Without this the
            # guard could be "fixed" by scanning the whole detail for the key as a substring,
            # which is #88's class one layer up.
            prose_note = Path(tmp) / "prosenote.jsonl"
            prose_note.write_text(redeclare.read_text(encoding="utf-8"), encoding="utf-8")
            r = run(prose_note, "repair", "--actor", "worker", "--n", "3",
                    "--append-detail", "REPAIR NOTE: the row omitted the head field.",
                    "--note", "probe: a prose append declares no key")
            check("a prose append that declares no key is not refused",
                  r.returncode == 0, r.stderr.strip()[:140])

            # The single-writer property has to survive a repair running CONCURRENTLY
            # with appends: a repair rewrites the file, so a repair holding a different
            # lock than `append` would interleave with it and re-issue an n.
            #
            # Each repair appends a key of its OWN, and that is load-bearing rather than
            # cosmetic: ten repairs of the SAME row each appending `head=` would now be
            # refused from the second onwards — the first lands the key, and the re-declaration
            # refusal above then refuses the rest, because one field with two values has no
            # canonical reading. Racing distinct keys exercises the lock, which is what this
            # block is for, without tripping the guard whose own probe sits above.
            race = Path(tmp) / "race.jsonl"
            write_repair_ledger(race, post_ts)
            race_env = {**os.environ, "OC_LEDGER_PATH": str(race),
                        "OC_ACTORS_PATH": str(Path(tmp) / "no-actors.txt")}
            procs = []
            for i in range(10):
                procs.append(subprocess.Popen(
                    [sys.executable, str(TOOL), "append", "--event", "run", "--actor", "worker",
                     "--subject", "#race", "--detail", f"race append {i}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=race_env))
                procs.append(subprocess.Popen(
                    [sys.executable, str(TOOL), "repair", "--actor", "worker", "--n", "3",
                     "--append-detail", f"race{i}=ok", "--note", f"race repair {i}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=race_env))
            for p in procs:
                p.wait()
            raced = rows(race)
            check("20 concurrent append+repair invocations all landed", len(raced) == 23,
                  f"{len(raced)} row(s)")
            check("no two writers claimed the same n (append racing repair)",
                  [row["n"] for row in raced] == list(range(1, 24)),
                  f"n={[row['n'] for row in raced]}")

            # The other half of the policy split: a GATE skips when the tree declares
            # nothing, but a REPAIR must refuse — it cannot certify a correction as
            # lawful under a boundary it cannot read, and proceeding anyway is exactly
            # the silent edit this command exists to make impossible. A staged tool in
            # a tree with no declaration is that case, and this also proves the new
            # neighbour import is staged rather than resolved from the live tree.
            bare = Path(tmp) / "barefactory"
            (bare / "tools").mkdir(parents=True)
            (bare / "evidence").mkdir()
            stage_tool(TOOL, bare / "tools", LOCAL_TOOLS)
            bare_ledger = bare / "evidence" / "ledger.jsonl"
            write_repair_ledger(bare_ledger, post_ts)
            # The probe declares an actor so that it reaches the code under test.
            # Identity is now derived from the session BEFORE the boundary is read, so
            # in a staged tree (which carries no lane resolver) the actor guard fires
            # first and the boundary refusal below would be unreachable — the probe
            # would then pass on a refusal it never exercised. A REDIRECTED ledger is
            # a fixture, so a declared actor there is the fixture's own declaration.
            r = subprocess.run(
                [sys.executable, str(bare / "tools" / "ledger.py"), "repair", "--n", "3",
                 "--append-detail", f"head={probe_sha}", "--note", "probe", "--actor", "hq"],
                capture_output=True, text=True, cwd=bare,
                env={**os.environ, "OC_LEDGER_PATH": str(bare_ledger),
                     "OC_ACTORS_PATH": str(bare / "no-actors.txt")},
            )
            err = r.stderr.strip()
            check("an undeclared boundary refuses the repair (it does not skip)",
                  r.returncode != 0, err[:90])
            check("the refusal names the invariant it could not read",
                  "close_row_revision" in err, err[:170])
            check("the staged tool carries its declaration reader",
                  (bare / "tools" / "ledger_declaration.py").is_file(),
                  "stage_tool must copy the new neighbour import")

    print("\nprose-as-data — a mention must not suppress a field (#88, ledger n=405 clause 5)")
    # Each probe below writes its close row through the REAL append path, which since
    # #98 refuses a close whose subject has no preceding intake and claim. The legs are
    # seeded directly with `write_ledger` — the fixture helper, which does not go
    # through the path under test — so each probe fails for its own reason and never
    # for a missing leg.
    # The class's third direction. `cmd_append` used to test `"tokens_out=" not in
    # detail` — a SUBSTRING test — so a close row whose PROSE mentioned the key
    # suppressed the measurement the tool had genuinely taken, and the row shipped with
    # no telemetry while nothing said so. The probe runs the REAL command against a
    # throwaway ledger AND a throwaway telemetry source: a probe that read the live
    # database would pass or fail on this box's traffic rather than on the code.
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        actors = tdir / "actors.txt"
        actors.write_text("worker\n", encoding="utf-8")
        db = seed_telemetry_db(tdir / "telemetry.db")

        prose = tdir / "prose.jsonl"
        write_ledger(prose, ("intake", "#88"), ("claim", "#88"))
        r = run(
            prose, "append", "--event", "close", "--actor", "worker", "--subject", "#88",
            "--detail",
            "Closed. The writer tested whether tokens_out= was absent before appending, "
            "and cost_usd= was read from the same sentence. "
            "head=0123456789abcdef0123456789abcdef01234567",
            actors=actors, extra_env={"OPENCRABS_DB_PATH": str(db)},
        )
        check("a close row whose prose mentions the keys is accepted",
              r.returncode == 0, (r.stderr or r.stdout).strip()[:90])
        detail = close_row(prose).get("detail", "")
        for key, want in (("cost_usd", "1.2500"), ("tokens_in", "111"),
                          ("tokens_out", "222"), ("turns", "3")):
            check(f"a prose mention did not suppress {key}",
                  f"{key}={want}" in detail, detail[-100:])

        # The control: the guard still exists, it just reads a field now instead of a
        # substring. A measurement the author DID state is not duplicated, and one they
        # did not state is still appended beside it. Both stated tokens stand alone, so
        # both parse — the punctuation case is the boundary pinned below.
        stated = tdir / "stated.jsonl"
        write_ledger(stated, ("intake", "#88"), ("claim", "#88"))
        run(stated, "append", "--event", "close", "--actor", "worker", "--subject", "#88",
            "--detail", "Closed. The author stated turns=7 and cost_usd=9.99 before the "
                        "append. head=0123456789abcdef0123456789abcdef01234567",
            actors=actors, extra_env={"OPENCRABS_DB_PATH": str(db)})
        detail = close_row(stated).get("detail", "")
        check("a DECLARED measurement is not duplicated",
              detail.count("cost_usd=") == 1 and "cost_usd=9.99" in detail, detail[-100:])
        check("a declared count is not replaced by the tool's own",
              "turns=7" in detail and "turns=3" not in detail, detail[-100:])
        check("a key the author did not state is still appended",
              "tokens_out=222" in detail, detail[-100:])

        # The measured BOUNDARY of the suppression leg, pinned rather than assumed. The
        # law requires the value to PARSE for the key's type, so a stated measurement
        # carrying trailing sentence punctuation is not a declaration and the tool appends
        # its own beside it. That is reachable, and the probe takes its receipt from the
        # schema gate rather than describing the outcome: the row then carries both
        # tokens, and the punctuated one fails that gate's trailer check. The boundary is
        # pinned instead of narrowed because stripping sentence punctuation from the value
        # would re-open the quotation hole (`turns=36'`) this class exists to close.
        punctuated = tdir / "punctuated.jsonl"
        write_ledger(punctuated, ("intake", "#88"), ("claim", "#88"))
        run(punctuated, "append", "--event", "close", "--actor", "worker", "--subject", "#88",
            "--detail", "Closed. The author stated turns=7. "
                        "head=0123456789abcdef0123456789abcdef01234567",
            actors=actors, extra_env={"OPENCRABS_DB_PATH": str(db)})
        detail = close_row(punctuated).get("detail", "")
        check("a punctuated stated value does not suppress the append (pinned boundary)",
              "turns=7." in detail and "turns=3" in detail, detail[-100:])
        gate = subprocess.run(
            [sys.executable, str(REPO / "tests" / "test_ledger_schema.py")],
            capture_output=True, text=True,
            env={**os.environ, "OC_LEDGER_PATH": str(punctuated),
                 "OC_ACTORS_PATH": str(actors)},
        )
        check("and the punctuated token is refused by the schema gate",
              gate.returncode != 0 and "invalid integer format for turns" in gate.stdout + gate.stderr,
              (gate.stdout + gate.stderr).strip().splitlines()[-1][:90])

        # The under-scope this probe closes: a value that does NOT parse is not a
        # measurement, so a quotation of another row's trailer (`turns=36'`) must not
        # suppress the count the tool took. Reading only "is the key named with
        # something after the `=`" would leave this half of the class live.
        quoted = tdir / "quoted.jsonl"
        write_ledger(quoted, ("intake", "#88"), ("claim", "#88"))
        run(quoted, "append", "--event", "close", "--actor", "worker", "--subject", "#88",
            "--detail", "Closed. The quoted trailer read turns=36' before the repair. "
                        "head=0123456789abcdef0123456789abcdef01234567",
            actors=actors, extra_env={"OPENCRABS_DB_PATH": str(db)})
        detail = close_row(quoted).get("detail", "")
        check("a quoted unparseable value does not suppress the measurement",
              "turns=3" in detail, detail[-100:])

        # The COMPLEMENT of the suppression leg above, and the half that was MISSING.
        # Every telemetry token is appended only when its value is `> 0`, so a close row
        # whose window yielded NOTHING shipped SILENCE — and the case is SYSTEMATIC, not
        # incidental: a lane that claims and closes together at the end of a work item
        # writes both rows after the work has landed, so the window holds no turns and
        # every cost and yield figure computed from that row silently degrades. The boundary
        # is the `> 0` test, and the two branches have DIFFERENT populations: a window
        # LONGER than a second belongs to the guard above, and a ZERO-second window belongs
        # to the branch under test here. The receipted instance is n=607 (#98), whose claim
        # (n=606) and close both carry ts 2026-09-19T17:57:10Z -- a zero-second window, and
        # no telemetry token in the row (n=405 clause 6: absence must be STATED, never
        # silent). The probe points the telemetry source at an EMPTY database AND dates the
        # claim row in the FUTURE, so `max(0, now - start_epoch)` is exactly 0 and the
        # `> 0` guard above cannot answer this leg. BOTH halves are load-bearing: pointing at
        # an empty database alone leaves a ~780000s window (write_ledger stamps every row
        # 2026-09-12T00:00:00Z), which the pre-existing guard satisfies -- a probe in that
        # shape passes with this branch deleted ENTIRELY, which is exactly what happened
        # here and is why the future stamp is not decoration. The companion assertions keep
        # the probe non-vacuous: the row must carry NO cost/tokens/turns token, which proves
        # the window really was empty and the statement came from this branch.
        import sqlite3
        from field_predicate import declares_field  # the shared predicate, one field one read

        silent = tdir / "silent.jsonl"
        empty_db = tdir / "empty.db"
        conn = sqlite3.connect(empty_db)
        conn.execute(
            "CREATE TABLE messages (created_at INTEGER, cost REAL, input_tokens INTEGER, "
            "token_count INTEGER, role TEXT, session_id TEXT)"
        )
        conn.commit()
        conn.close()
        # The claim row is written BY HAND rather than through write_ledger, which stamps
        # every row `2026-09-12T00:00:00Z`: a date ~9 days in the past makes the window
        # ~780000s, the guard above fires, and the branch under test is never reached. A
        # FUTURE stamp makes `duration_sec` exactly 0 -- the shape of the real instance
        # n=607, and the only shape this branch exists for. Do NOT use `ts == now`: the
        # close lands a second later, `duration_sec` becomes 1, and the vacuity returns.
        silent.write_text(
            "\n".join(
                json.dumps({
                    "n": i, "ts": "2030-01-01T00:00:00Z", "event": event, "actor": "hq",
                    "subject": "#89", "detail": "probe",
                })
                for i, event in enumerate(("intake", "claim"), 1)
            ) + "\n",
            encoding="utf-8",
        )
        r = run(
            silent, "append", "--event", "close", "--actor", "worker", "--subject", "#89",
            "--detail", "Closed with no telemetry inside the window. "
                        "head=0123456789abcdef0123456789abcdef01234567",
            actors=actors, extra_env={"OPENCRABS_DB_PATH": str(empty_db)},
        )
        check("a close row whose window yielded nothing is accepted",
              r.returncode == 0, (r.stderr or r.stdout).strip()[:90])
        detail = close_row(silent).get("detail", "")
        check("an empty window states the window it used",
              declares_field(detail, "duration"), detail[-100:])
        for key in ("cost_usd", "tokens_in", "tokens_out", "turns"):
            check(f"and the empty window declared no {key} (the probe is not vacuous)",
                  not declares_field(detail, key), detail[-100:])

        # The other direction, pinned: an author who STATED the window is not given a
        # second one. One field, one value — the guard reads the DECLARED field, never a
        # substring, because a substring test is what made this the third site of the
        # prose-as-data class in the first place.
        stated = tdir / "stated_window.jsonl"
        write_ledger(stated, ("intake", "#90"), ("claim", "#90"))
        run(
            stated, "append", "--event", "close", "--actor", "worker", "--subject", "#90",
            "--detail", "Closed. The author stated duration=42s before the append. "
                        "head=0123456789abcdef0123456789abcdef01234567",
            actors=actors, extra_env={"OPENCRABS_DB_PATH": str(empty_db)},
        )
        detail = close_row(stated).get("detail", "")
        check("a stated window is not duplicated",
              detail.count("duration=") == 1 and "duration=42s" in detail, detail[-100:])

        # PROVENANCE, CARRIED (#130). Every leg above judges WHAT the guard wrote; these
        # judge that the row SAYS WHO WROTE IT. HQ measured all three candidate structural
        # predicates -- position, completeness, value equality -- and each FAILED, so no
        # reader can settle this from the row's own shape: the writer states it instead.
        #
        # The row just written is the sharpest case in the whole gate. The author stated
        # `duration=42s` THEMSELVES, so the extractor contributed NOTHING -- `missing` was
        # empty and the field was already declared -- which means the values in that row are
        # the AUTHOR's, not a measurement. That is #130's class exactly, and it is the branch
        # (`provenance = "typed"`) that did not exist before this issue.
        check("a row the tool contributed nothing to says the author typed it",
              "telemetry=typed" in detail, detail[-100:])
        check("and it carries exactly one provenance token",
              detail.count("telemetry=") == 1, detail[-100:])

        print("\nthe guard's own availability — an unimportable extractor is stated, not silent")
        # The two legs above judge a window that WAS measured. This one judges the case
        # where nothing could be measured at all: the extractor could not be imported, and
        # the row used to be appended in complete silence — rc 0, no telemetry, and not a
        # word in the row saying so. Same defect one level up (n=405 clause 6: absence must
        # be STATED, never silent), and it is receipted on EIGHT post-guard close rows
        # (n=169, 173, 210, 341, 370, 399, 607, 686) that shipped with no telemetry at all.
        #
        # The probe stages the tool the way every throwaway tree in this gate does, then
        # DELETES `telemetry.py` from the staged directory. That deletion is the only way
        # the import can still fail, and it is deliberate rather than convenient: the
        # module's own bare sibling imports (`ledger_declaration`, `field_predicate`,
        # `reconstruction`) put `tools/` on `sys.path` as a side effect, so a writer whose
        # `sys.path[0]` was neither the repo root nor `tools/` now kills the module OUTRIGHT
        # at load — loudly, before any row exists — instead of silently skipping the block.
        # The failure mode left to guard is "the neighbour is not there", which is exactly
        # what the unlink models. Both arms run the SAME staged tree, so the extractor's
        # presence is the only difference between them. The database is pinned to an EMPTY
        # one, and NOT to a path that does not exist: `find_database_path` accepts the env
        # path only `if p.is_file()` and otherwise falls through to the profile database on
        # the live box, so a bogus path would silently read the running daemon's totals --
        # the exact box-dependence `run()`'s docstring warns against. An empty database
        # yields a zero measurement while the window itself still comes from the ledger.
        absent = Path(tmp) / "noextractor"
        (absent / "tools").mkdir(parents=True)
        (absent / "evidence").mkdir()
        stage_tool(TOOL, absent / "tools", LOCAL_TOOLS)
        absent_tool = absent / "tools" / "ledger.py"
        absent_ledger = absent / "evidence" / "ledger.jsonl"
        absent_db = absent / "empty.db"
        conn = sqlite3.connect(absent_db)
        conn.execute(
            "CREATE TABLE messages (created_at INTEGER, cost REAL, input_tokens INTEGER, "
            "token_count INTEGER, role TEXT, session_id TEXT)"
        )
        conn.commit()
        conn.close()
        write_ledger(absent_ledger, ("intake", "#91"), ("claim", "#91"))

        def absent_run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, str(absent_tool), *args],
                capture_output=True, text=True, cwd=absent,
                env={**os.environ, "OC_LEDGER_PATH": str(absent_ledger),
                     "OC_ACTORS_PATH": str(absent / "no-actors.txt"),
                     "OPENCRABS_DB_PATH": str(absent_db)},
            )

        # ARM GREEN — the extractor is present, so this leg must not fire at all, and the
        # extractor must actually have RUN. Both halves are asserted: without the second,
        # the arm would pass on a tree where the module was never staged, and the RED arm
        # below would then be proving the wrong thing.
        r = absent_run("append", "--event", "close", "--actor", "worker",
                       "--subject", "#91", "--detail", "Closed with the extractor present. "
                       "head=0123456789abcdef0123456789abcdef01234567")
        detail = close_row(absent_ledger).get("detail", "")
        check("extractor present: the row does not claim it was unavailable",
              r.returncode == 0 and "telemetry=unavailable" not in detail, detail[-90:])
        check("extractor present: the window was measured and stated",
              declares_field(detail, "duration"), detail[-90:])
        # #130: measured, and SAID to be measured -- one token, from the one writer.
        check("extractor present: the row says the tool took the values",
              "telemetry=measured" in detail, detail[-90:])
        check("extractor present: exactly one provenance token",
              detail.count("telemetry=") == 1, detail[-90:])

        # ARM RED — the neighbour is gone, and the SAME command must now say so.
        (absent / "tools" / "telemetry.py").unlink()
        absent_ledger.write_text(
            "\n".join(json.dumps(row) for row in rows(absent_ledger)[:2]) + "\n",
            encoding="utf-8",
        )
        r = absent_run("append", "--event", "close", "--actor", "worker",
                       "--subject", "#91", "--detail", "Closed with no extractor at all. "
                       "head=0123456789abcdef0123456789abcdef01234567")
        detail = close_row(absent_ledger).get("detail", "")
        check("an unimportable extractor is stated, never silent",
              r.returncode == 0 and "telemetry=unavailable" in detail, detail[-90:])
        # #130: the third provenance value, and the same one-token invariant. Without this
        # the third branch would be the only writer nobody pinned to exactly one token.
        check("and it carries exactly one provenance token",
              detail.count("telemetry=") == 1, detail[-90:])
        # Non-vacuity: the row carries NO measurement, which is precisely why the statement
        # has to exist. Without this the leg would pass on a row that had the numbers.
        for key in ("cost_usd", "tokens_in", "tokens_out", "turns", "duration"):
            check(f"and it declared no {key} (the probe is not vacuous)",
                  not declares_field(detail, key), detail[-90:])

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
