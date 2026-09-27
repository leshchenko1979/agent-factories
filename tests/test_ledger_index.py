#!/usr/bin/env python3
"""Gate: the derived ledger index — a rebuild agrees with a plain scan.

P29: a rule needs an active process or a deterministic gate. The index's rule is
"derived, disposable, never a source of truth", and the property that makes it safe to
treat that way is that a REBUILD AGREES WITH A PLAIN SCAN OF THE JSONL. That is what
this gate asserts, on a FIXTURE, so it does not depend on the box's live ledgers.

What it deliberately does NOT assert: that the index is fresh. A stale derived index is
not a defect, it is a stale cache — the tool states its own instant, and the patrol
rebuilds it. A gate over freshness would red for a reason no one can act on.

Run:  python3 tests/test_ledger_index.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "ledger-index.py"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def run(*args: str, env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True,
        env={**os.environ, **env_extra},
    )


def fixture_rows(ledger: str, base: int, count: int) -> list[dict]:
    events = ["intake", "claim", "close", "ruling", "run"]
    out = []
    for i in range(count):
        row = {
            "n": base + i,
            "ts": f"2026-09-27T0{i % 10}:00:00Z",
            "event": events[i % len(events)],
            "actor": "triage",
            "subject": f"#{base + i}",
            "detail": f"fixture row {ledger} {base + i} alpha",
        }
        if i % 4 == 0:
            row["refs"] = [{"row": str(base + i - 1 if i else 1)}]
        out.append(row)
    return out


def main() -> int:
    print("registration — an unregistered gate never runs (P29)")
    audit = (REPO / "tools" / "audit.py").read_text(encoding="utf-8")
    check("this gate is registered in tools/audit.py",
          "tests/test_ledger_index.py" in audit,
          "an unregistered gate never runs")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        index = tmp / "index.sqlite"
        sources = []
        for name, base, count in (("alpha", 1, 12), ("beta", 1, 5)):
            p = tmp / f"{name}.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in fixture_rows(name, base, count)) + "\n")
            sources.append(f"{name}={p}")
        env = {"OC_LEDGER_INDEX": str(index), "OC_LEDGER_SOURCES": ":".join(sources)}

        print("build — the index is produced from the declared population")
        r = run("build", env_extra=env)
        check("build exits 0", r.returncode == 0, r.stderr.strip()[:120])
        check("build names every ledger it read", "alpha" in r.stdout and "beta" in r.stdout)
        check("the index file exists", index.is_file())

        print("the property that makes it disposable — a rebuild agrees with a scan")
        r = run("check", env_extra=env)
        check("check exits 0", r.returncode == 0, r.stdout.strip()[-140:])
        check("check compares EVERY ledger in the population",
              "alpha: 12 rows in both" in r.stdout and "beta: 5 rows in both" in r.stdout,
              r.stdout.strip()[-160:])

        print("the queries it exists for")
        r = run("find", "alpha", env_extra=env)
        check("full-text finds the fixture rows", r.returncode == 0 and "hit(s)" in r.stdout,
              r.stdout.strip()[-120:])
        r = run("subject", "#3", env_extra=env)
        check("a subject query crosses ledgers", r.returncode == 0 and "2 row(s)" in r.stdout,
              r.stdout.strip()[-120:])
        r = run("touching", "4", env_extra=env)
        check("a ref query follows the refs table",
              r.returncode == 0 and "0 ref(s)" not in r.stdout,
              r.stdout.strip()[-120:])

        print("disposability — the index is deletable and rebuildable")
        index.unlink()
        r = run("check", env_extra=env)
        check("a query against a deleted index FAILS rather than inventing an answer",
              r.returncode != 0 and "run:" in r.stderr, r.stderr.strip()[:120])
        r = run("build", env_extra=env)
        check("and it rebuilds from the ledgers alone", r.returncode == 0)

        print("an absent ledger is named, never treated as empty")
        env2 = dict(env)
        env2["OC_LEDGER_SOURCES"] = f"alpha={tmp / 'alpha.jsonl'}:ghost={tmp / 'nope.jsonl'}"
        r = run("build", env_extra=env2)
        check("the absent ledger is SKIPPED and named",
              r.returncode == 0 and "absent" in r.stdout and "ghost" in r.stdout,
              r.stdout.strip()[-140:])

    print("the index is gitignored — a tracked binary blob is the one thing it must not be")
    gi = subprocess.run(["git", "check-ignore", "-v", "evidence/.ledger-index.sqlite"],
                        capture_output=True, text=True, cwd=REPO)
    check("git ignores the index path", gi.returncode == 0 and "ledger-index" in gi.stdout,
          gi.stdout.strip() or gi.stderr.strip()[:100])

    if failures:
        print(f"ledger index gate FAILED: {len(failures)} check(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ledger index gate clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
