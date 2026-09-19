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

import datetime as dt
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
        declared = json.loads(
            (REPO / "docs" / "ledger-invariants.json").read_text(encoding="utf-8")
        )["invariants"]["close_row_revision"]
        boundary_dt = dt.datetime.fromisoformat(declared.replace("Z", "+00:00"))
        post_ts = (boundary_dt + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        probe_sha = "a" * 40

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
        r = run(ledger, "repair", "--n", "3", "--append-detail", f"head={probe_sha}",
                "--note", "probe")
        err = r.stderr.strip()
        check("a pre-boundary row refuses repair", r.returncode != 0, err[:90])
        check("the refusal names the boundary it refuses on", declared in err, err[:170])
        check("the refused repair wrote nothing", len(rows(ledger)) == 3,
              f"{len(rows(ledger))} row(s)")

        # A repair with no stated reason is refused. Run against a POST-boundary
        # row, so the only thing the refusal can be about is the missing note.
        write_repair_ledger(ledger, post_ts)
        r = run(ledger, "repair", "--n", "3", "--append-detail", f"head={probe_sha}")
        err = r.stderr.strip()
        check("a repair with no --note is refused", r.returncode != 0, err[:90])
        check("the refusal names --note as what is missing", "--note" in err, err[:140])
        check("the refused repair wrote nothing", len(rows(ledger)) == 3,
              f"{len(rows(ledger))} row(s)")

        # A lawful repair lands, changes only `detail`, appends exactly one `run`
        # row naming the row and the note, and `verify` accepts the result.
        identity = ("n", "ts", "event", "actor", "subject")
        before = rows(ledger)[2]
        r = run(ledger, "repair", "--n", "3", "--append-detail", f"head={probe_sha}",
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

        # The single-writer property has to survive a repair running CONCURRENTLY
        # with appends: a repair rewrites the file, so a repair holding a different
        # lock than `append` would interleave with it and re-issue an n.
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
                [sys.executable, str(TOOL), "repair", "--n", "3",
                 "--append-detail", f"head={probe_sha}", "--note", f"race repair {i}"],
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
        r = subprocess.run(
            [sys.executable, str(bare / "tools" / "ledger.py"), "repair", "--n", "3",
             "--append-detail", f"head={probe_sha}", "--note", "probe"],
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
