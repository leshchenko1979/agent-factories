#!/usr/bin/env python3
"""Gate: a commit carrying the ledger names the concern, not row numbers.

Origin (issue #47, the ledger clause). A ledger row's number is assigned *inside* the
append lock, so it cannot be known before the append — and by the time the commit runs
another lane may have appended further rows. Measured in a single day, three commits
carried the same shape: one named `n=211` and added 211/212/213; another named 212/213
and added 214/215; a third named `n=259` and added `n=261`. That is structural, not
carelessness, which is why the clause removes the claim rather than policing it: the
message names the concern, and where a row must be cited it is cited in the ledger's
own `detail` text — written after the append, where the real number can be read.

**Forward-only, and why.** A history-wide form would be permanently red: 55 of 146
historical commits touching the ledger cite row numbers in their subject. The gate is
therefore bounded by a MARKER commit — the first ledger commit obeying the clause — and
examines only commits after it. Nothing is backfilled: those historical violations are
history, not a backlog.

**The marker is a hardcoded sha.** A history rewrite invalidates it, and that is stated
rather than left implicit. If the marker no longer resolves, this gate FAILS LOUDLY
instead of passing vacuously: a gate that silently examines zero commits is
indistinguishable from a gate that examines zero commits and passes. A factory
bootstrapped from the template re-anchors MARKER at birth — the shipped sha belongs to
the history of the repo the template was written in, not to the new factory's.

**The repo root is resolved, not assumed.** The gate's own file sits at `tests/` in a
bootstrapped factory but under `TEMPLATE/tests/` in the template repo, so resolving the
tree from `__file__` alone made the template copy run `git log` with a pathspec relative
to `TEMPLATE/` — matching no commits and reporting "examined 0" as clean. That is the
vacuous pass this gate exists to prevent, so it asks git for the real top level and
passes the ledger as an absolute path.

**It reports the count it examined.** "0 examined" must never read as "clean".

Run:  python3 tests/test_ledger_commit_cites_no_rows.py
Exit: 0 clean, 1 a post-marker ledger commit cites row numbers, or the marker is gone.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER_PATH = "evidence/ledger.jsonl"

# The first commit touching the ledger whose subject obeys the clause. Commits at or
# before it predate the rule and are not examined. See the docstring: a missing marker
# fails loudly, so a history rewrite cannot turn this gate into a silent pass.
MARKER = "743b543"

# A row citation. The word boundary is load-bearing: without it, `version=3` and
# `conversion=2` both contain the substring `n=` and would be reported as citations.
ROW_CITE = re.compile(r"\bn=\d+\b", re.IGNORECASE)


def subject_cites_rows(subject: str) -> bool:
    """True when a commit subject cites a ledger row number.

    Factored so synthetic subjects can probe it: a rule that has only ever seen good
    input has not been shown to reject bad input.
    """
    return bool(ROW_CITE.search(subject or ""))


def _git(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True
    )
    return proc.returncode, proc.stdout, proc.stderr


def repo_toplevel() -> Path | None:
    """The git top level containing this gate, so a copy in a subdirectory still works."""
    rc, out, _ = _git("rev-parse", "--show-toplevel")
    return Path(out.strip()) if rc == 0 and out.strip() else None


def marker_resolves(marker: str = MARKER) -> bool:
    rc, _, _ = _git("rev-parse", "--verify", "--quiet", f"{marker}^{{commit}}")
    return rc == 0


def ledger_commits_after(marker: str = MARKER) -> list[tuple[str, str]]:
    """`[(sha, subject)]` for commits after `marker` touching the ledger, newest first.

    The ledger is passed as an absolute path, so the pathspec resolves against the git
    top level rather than against this file's own directory.
    """
    top = repo_toplevel()
    if top is None:
        raise RuntimeError(f"{REPO} is not inside a git work tree")
    rc, out, err = _git(
        "log", "--format=%h\x1f%s", f"{marker}..HEAD", "--", str(top / LEDGER_PATH)
    )
    if rc != 0:
        raise RuntimeError(f"git log failed: {err.strip()}")
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, _, subject = line.partition("\x1f")
        rows.append((sha, subject))
    return rows


def offenders(commits: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(sha, s) for sha, s in commits if subject_cites_rows(s)]


def probe() -> list[str]:
    """Probe the predicate against both shapes, and report anything that is wrong."""
    failures: list[str] = []
    must_catch = [
        "chore(ledger): stamp the claim and carry HQ's ruling rows (n=265)",
        "chore(ledger): n=123",
        "chore(ledger): closes n=9 and n=10",
    ]
    must_pass = [
        "chore(ledger): stamp the claim and carry HQ's ruling rows",
        "chore(ledger): close the board-close-on-settlement subject with its board token",
        # The word-boundary guard: a word merely ending in `n=` is not a citation.
        "fix: bump version=3 of the schema",
        "docs: conversion=2 notes",
    ]
    for subject in must_catch:
        if not subject_cites_rows(subject):
            failures.append(f"probe: predicate missed a row citation in {subject!r}")
    for subject in must_pass:
        if subject_cites_rows(subject):
            failures.append(f"probe: predicate false-positived on {subject!r}")
    return failures


def main() -> int:
    problems = probe()

    if not marker_resolves():
        problems.append(
            f"the marker commit {MARKER} does not resolve — a history rewrite "
            "invalidates it. Re-anchor MARKER to the first ledger commit obeying the "
            "clause; do not delete the gate."
        )
    else:
        commits = ledger_commits_after()
        bad = offenders(commits)
        print(f"ledger clause: examined {len(commits)} commit(s) after {MARKER}")
        for sha, subject in bad:
            problems.append(f"{sha} cites a row number: {subject}")

    if problems:
        for line in problems:
            print(f"  FAIL {line}")
        return 1

    print("ledger clause: clean — no commit after the marker cites row numbers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
