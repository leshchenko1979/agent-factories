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
import shutil
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


def _ignored(rel: str, repo: Path = REPO) -> tuple[bool, str, str]:
    """Is `rel` ignored, and by WHICH source? Returns (ok, source, detail).

    `check-ignore -v` names the FILE AND LINE carrying the pattern, so the gate reports
    the mechanism rather than a bare yes: "ignored by a member's own .gitignore" and
    "ignored by the local exclude the tool wrote" are different facts, and only the
    second is this instrument's own doing.

    The failure text names the REMEDY, because a red that does not say what to run is
    the class this fleet files against itself.
    """
    gi = subprocess.run(["git", "check-ignore", "-v", rel],
                        capture_output=True, text=True, cwd=repo)
    if gi.returncode == 0 and gi.stdout.strip():
        return True, gi.stdout.split(":", 1)[0], f"ignored by {gi.stdout.split(':', 1)[0]}"
    return False, "", (f"NOT ignored, so a binary blob at {rel} is committable — "
                       f"run: python3 tools/ledger-index.py build (it ensures the line), "
                       f"or add {rel!r} to .gitignore")

def _index_arm(tool_index: Path | None, repo: Path) -> tuple[str, str, str]:
    """The ignore requirement's verdict in ONE tree: (verdict, subject, detail).

    KEYED ON THE INDEX'S EXISTENCE, and extracted into a function so the KEYING ITSELF
    can be driven. What the requirement protects is "no COMMITTABLE binary blob", and a
    tree that has never built the index has no blob — so an unconditional arm FAILS a
    clean tree, and a red that is not a defect teaches lanes to ignore red gates.
    Measured 2026-10-01 on the three real adopters (ai-antispam, inferhub-watch, miidas):
    index ABSENT and `git check-ignore` rc=1 in all three, i.e. the unconditional form
    red all three on a state where nothing was committable.

    It is a function rather than inline branches because an arm that can only ever SKIP
    protects nothing while passing forever, and the three states below are driven on the
    fixture trees rather than trusted to be reachable.
    """
    if tool_index is None:
        return "FAIL", "?", "the tool did not name an index path"
    try:
        rel = tool_index.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return "SKIP", str(tool_index), (
            f"the index ({tool_index}) lives outside the repository — nothing to ignore, "
            f"so nothing can be committed")
    if not tool_index.is_file():
        return "SKIP", rel, (
            f"no index at {rel} yet — nothing is committable, so there is nothing to "
            f"ignore; run: python3 tools/ledger-index.py build")
    ok, source, detail = _ignored(rel, repo)
    return ("PASS" if ok else "FAIL"), rel, detail


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
    # Ask the TOOL for its path rather than re-deriving the literal: a path hardcoded
    # here would keep testing the old location after the tool's default moved, and pass
    # vacuously while the real artifact sat committable.
    r = run("path", env_extra={})
    tool_index = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    check("the tool names its index path", tool_index is not None,
          r.stderr.strip()[:120] or r.stdout.strip()[:120])
    verdict, subject, detail = _index_arm(tool_index, REPO)
    if verdict == "SKIP":
        print(f"  SKIP  {detail}")
    else:
        check(f"git ignores the index path ({subject})", verdict == "PASS", detail)
    # THE ARM THAT KEEPS ITS TEETH: the same predicate, aimed at a path nothing ignores,
    # must FAIL. It runs whether or not the index exists, because it tests the PREDICATE
    # rather than the artifact — a check that cannot fail is indistinguishable from one
    # that works, and this is the arm that proves the difference.
    probe = f"evidence/.not-ignored-{os.getpid()}.sqlite"
    ok2, _s2, detail2 = _ignored(probe)
    check("the same check FAILS on a path nothing ignores", not ok2, detail2)

    print("the carrier the tool writes — driven, not asserted")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        member = tmp / "member"
        (member / "tools").mkdir(parents=True)
        (member / "evidence").mkdir()
        shutil.copy(TOOL, member / "tools" / "ledger-index.py")
        mledger = member / "evidence" / "ledger.jsonl"
        mledger.write_text("\n".join(json.dumps(r) for r in fixture_rows("member", 1, 4)) + "\n")
        subprocess.run(["git", "init", "-q", "."], cwd=member, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=member, capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "init"], cwd=member, capture_output=True)
        menv = {"OC_LEDGER_SOURCES": f"member={mledger}"}
        mtool = member / "tools" / "ledger-index.py"

        def mrun(tool, *args, env_extra):
            return subprocess.run([sys.executable, str(tool), *args], capture_output=True,
                                  text=True, env={**os.environ, **env_extra}, cwd=member)

        def mig(*args):
            return subprocess.run(["git", *args], capture_output=True, text=True, cwd=member)

        check("(a) fixture starts with the path NOT ignored",
              mig("check-ignore", "-q", "evidence/.ledger-index.sqlite").returncode != 0)
        r = mrun(mtool, "build", env_extra=menv)
        check("(a) build ADDS the line and says so",
              r.returncode == 0 and "was NOT ignored" in r.stdout and "added it to" in r.stdout,
              [l for l in r.stdout.splitlines() if "ignore:" in l][:1])
        check("(a) and git now ignores it", mig("check-ignore", "-q",
              "evidence/.ledger-index.sqlite").returncode == 0)

        r = mrun(mtool, "build", env_extra=menv)
        common = mig("rev-parse", "--git-common-dir").stdout.strip()
        exclude = (member / common / "info" / "exclude") if not Path(common).is_absolute() \
            else Path(common) / "info" / "exclude"
        check("(b) a second build is IDEMPOTENT — one line, still ignored",
              "already ignored" in r.stdout and exclude.read_text().count("ledger-index") == 1,
              f"count={exclude.read_text().count('ledger-index')}")

        # (d) THE MUTATION ARM: neuter the call and the assertion above must fail. Without
        # this, a green here cannot be told from a check that never bites.
        mutant = tmp / "mutant-tool.py"
        mutant.write_text(mtool.read_text(encoding="utf-8").replace(
            "    ensure_ignored(INDEX)\n", "", 1), encoding="utf-8")
        repo2 = tmp / "member2"
        shutil.copytree(member, repo2)
        (repo2 / ".git" / "info" / "exclude").write_text("")
        m2 = repo2 / "tools" / "ledger-index.py"
        m2.write_text(mutant.read_text(encoding="utf-8"), encoding="utf-8")
        m2ledger = repo2 / "evidence" / "ledger.jsonl"
        r = subprocess.run([sys.executable, str(m2), "build"],
                           capture_output=True, text=True, cwd=repo2,
                           env={**os.environ, "OC_LEDGER_SOURCES": f"member={m2ledger}"})
        added = "added it to" in r.stdout
        gi2 = subprocess.run(["git", "check-ignore", "-q", "evidence/.ledger-index.sqlite"],
                             capture_output=True, cwd=repo2)
        check("(d) neutering ensure_ignored makes the arm FAIL — the check is load-bearing",
              not added and gi2.returncode != 0,
              "mutant added the line" if added else "mutant did not, as required")

        # (e) an index outside the repository has nothing to ignore, and says so
        r = mrun(mtool, "build", env_extra={**menv, "OC_LEDGER_INDEX": str(tmp / "out" / "i.sqlite")})
        check("(e) an index OUTSIDE the repo SKIPs with its reason",
              r.returncode == 0 and "outside the repository" in r.stdout,
              [l for l in r.stdout.splitlines() if "ignore:" in l][:1])

        # (f) a member's own tracked .gitignore line is respected, not duplicated
        repo3 = tmp / "member3"
        shutil.copytree(member, repo3)
        (repo3 / ".gitignore").write_text("evidence/.ledger-index.sqlite\n")
        (repo3 / ".git" / "info" / "exclude").write_text("")
        m3 = repo3 / "tools" / "ledger-index.py"
        r = subprocess.run([sys.executable, str(m3), "build"], capture_output=True, text=True,
                           cwd=repo3, env={**os.environ,
                                           "OC_LEDGER_SOURCES": f"member={repo3 / 'evidence' / 'ledger.jsonl'}"})
        check("(f) a member's own .gitignore line is respected, not duplicated",
              "already ignored" in r.stdout and (repo3 / ".git" / "info" / "exclude").read_text().strip() == "",
              (repo3 / ".git" / "info" / "exclude").read_text().strip()[:60])

        # (g) THE KEYING ITSELF IS DRIVEN, not trusted. The arm in the live tree can only
        # protect a tree whose index EXISTS, so if the existence test were wrong in the
        # SKIP direction the gate would pass forever while protecting nothing — the
        # vacuity class this factory files against itself. All three states, on the
        # fixture trees already built above, because a branch that cannot be reached is
        # indistinguishable from a branch that always fires.
        print("(g) the ignore arm's three states — the keying is driven, not assumed")
        v, _s, d = _index_arm(member / "evidence" / ".ledger-index.sqlite", member)
        check("(g) index PRESENT and ignored → PASS", v == "PASS", d)
        v, _s, d = _index_arm(repo2 / "evidence" / ".ledger-index.sqlite", repo2)
        check("(g) index PRESENT and NOT ignored → FAIL", v == "FAIL", d)
        v, _s, d = _index_arm(member / "evidence" / ".never-built.sqlite", member)
        check("(g) index ABSENT → SKIP, naming the remedy",
              v == "SKIP" and "ledger-index.py build" in d, d)

    if failures:
        print(f"ledger index gate FAILED: {len(failures)} check(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ledger index gate clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
