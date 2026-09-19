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

**The sanctioned exit, and why the marker is not it (ruled at n=328).** A violation
inside the window has an EMPTY REPAIR SPACE, so without a lawful exit one violation reds
the suite forever and the next lane learns to ignore a red gate — which destroys every
other gate's signal. The repairs are all barred: the commit is pushed (rewriting it is
barred by the identity law), a revert does not clear the gate (it reads subjects across
MARKER..HEAD, so the offending subject stays in range), and re-anchoring the marker past
the violation would make the marker's own definition — "the first commit touching the
ledger whose subject obeys the clause", whose predecessors "predate the rule" — false,
silently converting a live violation into an excused one. So the marker is re-anchored
ONLY at a factory's birth or when a history rewrite invalidates it, and the gate carries
a second, VISIBLE exit: an exemption list.

**The list is factory data read by the gate, never source inside it.** This file is
copied byte-identically into `TEMPLATE/` (guarded by `tests/test_template_sync.py`), so
an inline table naming one factory's sha would either break that gate or ship a foreign
sha into the template. The entries therefore live in
`docs/ledger-commit-exemptions.json`, whose skeleton is
`TEMPLATE/docs/ledger-commit-exemptions.example.json` — the same move that took the
product declaration out of `tools/roadmap.py` and into `docs/products.json`.

**An exemption is a visible debt, not forgiveness.** Every entry that matched is printed
as an `excused:` line on EVERY run, and the closing line distinguishes clean from
excused, so "clean" and "excused" are never the same output. Entries are keyed by the
FULL 40-character sha: a short sha or a tag would match nothing while looking like it
should. Absent or empty data means no exemptions — the shipped state of a new factory. A
malformed entry (not a full sha, no reason, malformed JSON) is a gate ERROR, never a
silent pass, because an exemption list that quietly fails to load is indistinguishable
from no exemptions — the same vacuous-pass shape the marker rule exists to prevent. An
entry that matches no violation in the range is an ERROR too: a stale exemption inflates
the count of visible debt while excusing nothing. And a SECOND exemption of the same
shape is a process defect, not an exemption — one is a debt; two mean the mechanism
(running `tools/audit.py` before a commit that touches the ledger) is not biting.

**The repo root is resolved, not assumed.** The gate's own file sits at `tests/` in a
bootstrapped factory but under `TEMPLATE/tests/` in the template repo, so resolving the
tree from `__file__` alone made the template copy run `git log` with a pathspec relative
to `TEMPLATE/` — matching no commits and reporting "examined 0" as clean. That is the
vacuous pass this gate exists to prevent, so it asks git for the real top level and
passes the ledger and the exemption data as absolute paths.

**It reports the count it examined.** "0 examined" must never read as "clean".

Run:  python3 tests/test_ledger_commit_cites_no_rows.py
Exit: 0 clean, or every violation excused; 1 a post-marker commit cites row numbers
      without an exemption, or the marker is gone, or the exemption data is malformed.
**The mechanism, and why this gate asserts it.** The clause's remedy for a SECOND
exemption of the same shape is a mechanism, not a third row (ruled at n=405): a
versioned `commit-msg` hook that refuses a citing subject before it is recorded. An
uninstalled hook is SILENT — the vacuous-pass shape this repo forbids — so this gate
also asserts the hook is present, executable, and reachable through `core.hooksPath`.
Install it with `git config core.hooksPath tools/hooks`; the config is local, so a
fresh clone runs it once.

"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER_PATH = "evidence/ledger.jsonl"
EXEMPTIONS_PATH = "docs/ledger-commit-exemptions.json"

# The mechanism the clause makes its remedy (issue #47, ruled at n=405): a versioned
# commit-msg hook, at the only point where the pending subject exists to be refused.
HOOK_PATH = "tools/hooks/commit-msg"
HOOKS_PATH_CONFIG = "tools/hooks"

# The first commit touching the ledger whose subject obeys the clause. Commits at or
# before it predate the rule and are not examined. See the docstring: a missing marker
# fails loudly, so a history rewrite cannot turn this gate into a silent pass.
MARKER = "743b543"

# A row citation. The word boundary is load-bearing: without it, `version=3` and
# `conversion=2` both contain the substring `n=` and would be reported as citations.
ROW_CITE = re.compile(r"\bn=\d+\b", re.IGNORECASE)

# An exemption is keyed by a full git sha. Asserted rather than assumed: a short sha or a
# tag would match nothing while looking like it should.
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

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

def hook_state_problems(*, exists: bool, executable: bool, configured: str) -> list[str]:
    """The refusal point's three facts, as a PURE predicate.

    Factored so synthetic state can drive every rejection path: an uninstalled hook
    is SILENT, which is the vacuous-pass shape this repo forbids — the same reason a
    missing marker fails loudly rather than examining zero commits. So absence is a
    gate failure, never an advisory.
    """
    problems: list[str] = []
    if not exists:
        problems.append(
            f"{HOOK_PATH} is missing — the commit-msg refusal point the ledger clause "
            "makes its remedy (issue #47, ruled at n=405) is not shipped"
        )
    elif not executable:
        problems.append(f"{HOOK_PATH} is not executable — git will not run it")
    shown = configured or "unset"
    if configured != HOOKS_PATH_CONFIG:
        problems.append(
            f"core.hooksPath is {shown!r} — the hook is versioned but not wired, so "
            "it never runs. Install it: "
            f"git config core.hooksPath {HOOKS_PATH_CONFIG}"
        )
    return problems

def hook_installation_problems(top: Path) -> list[str]:
    """Read the installation state off the tree and git config, then judge it."""
    hook = top / HOOK_PATH
    rc, out, _ = _git("config", "--get", "core.hooksPath")
    return hook_state_problems(
        exists=hook.is_file(),
        executable=os.access(hook, os.X_OK),
        configured=out.strip() if rc == 0 else "",
    )

def exemptions_file() -> Path:
    """The factory's exemption data, resolved against the git top level.

    Resolved the same way as the ledger, and for the same reason: this file's own
    location moves between `tests/` and `TEMPLATE/tests/`.
    """
    return (repo_toplevel() or REPO) / EXEMPTIONS_PATH

def marker_resolves(marker: str = MARKER) -> bool:
    rc, _, _ = _git("rev-parse", "--verify", "--quiet", f"{marker}^{{commit}}")
    return rc == 0

def ledger_commits_after(marker: str = MARKER) -> list[tuple[str, str, str]]:
    """`[(full_sha, short_sha, subject)]` for commits after `marker`, newest first.

    The full sha is carried because exemptions are keyed by it; the short one is carried
    because it is what a human reads. The ledger is passed as an absolute path, so the
    pathspec resolves against the git top level rather than against this file's own
    directory.
    """
    top = repo_toplevel()
    if top is None:
        raise RuntimeError(f"{REPO} is not inside a git work tree")
    rc, out, err = _git(
        "log", "--format=%H\x1f%h\x1f%s", f"{marker}..HEAD", "--", str(top / LEDGER_PATH)
    )
    if rc != 0:
        raise RuntimeError(f"git log failed: {err.strip()}")
    rows: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        rows.append((parts[0], parts[1], parts[2]))
    return rows

def offenders(commits: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    return [(full, short, s) for full, short, s in commits if subject_cites_rows(s)]

def load_exemptions(path: Path) -> tuple[dict[str, dict], list[str]]:
    """`({full_sha: entry}, problems)` read from the factory data file.

    Absent or empty data means no exemptions. Anything malformed is a problem, never a
    silent pass — see the docstring for why that distinction is load-bearing.
    """
    problems: list[str] = []
    if not path.is_file():
        return {}, problems
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"{path.name} is not JSON: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{path.name}: expected a JSON object with an 'exemptions' list"]
    raw = data.get("exemptions", [])
    if not isinstance(raw, list):
        return {}, [f"{path.name}: 'exemptions' must be a list"]

    entries: dict[str, dict] = {}
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            problems.append(f"{path.name}: entry {i} is not an object")
            continue
        sha = item.get("sha")
        if not isinstance(sha, str) or not FULL_SHA.match(sha):
            problems.append(
                f"{path.name}: entry {i} names a sha that is not a full 40-character "
                f"lowercase hex sha: {sha!r}"
            )
            continue
        if not item.get("reason"):
            problems.append(f"{path.name}: entry {i} ({sha[:12]}) carries no reason")
            continue
        if sha in entries:
            problems.append(f"{path.name}: entry {i} repeats {sha}")
            continue
        entries[sha] = item
    return entries, problems

def probe() -> list[str]:
    """Probe the predicate and the exemption loader against both shapes.

    A rule that has only ever seen good input has not been shown to reject bad input, so
    every rejection path is exercised here — including the ones that would otherwise
    only ever run in a factory that had already made the mistake.
    """
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

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        full = "0" * 40

        absent = tmpdir / "absent.json"
        entries, problems = load_exemptions(absent)
        if entries or problems:
            failures.append(
                "probe: absent exemption data must mean no exemptions and no error"
            )

        empty = tmpdir / "empty.json"
        empty.write_text('{"exemptions": []}', encoding="utf-8")
        entries, problems = load_exemptions(empty)
        if entries or problems:
            failures.append(
                "probe: an empty exemption list must mean no exemptions and no error"
            )

        good = tmpdir / "good.json"
        good.write_text(
            json.dumps(
                {"exemptions": [{"sha": full, "date": "2026-01-01", "reason": "r"}]}
            ),
            encoding="utf-8",
        )
        entries, problems = load_exemptions(good)
        if problems or set(entries) != {full}:
            failures.append("probe: a well-formed exemption entry must load cleanly")

        short = tmpdir / "short.json"
        short.write_text(
            '{"exemptions": [{"sha": "697b660", "date": "2026-01-01", "reason": "r"}]}',
            encoding="utf-8",
        )
        entries, problems = load_exemptions(short)
        if entries or not problems:
            failures.append(
                "probe: a sha that is not a full sha must be an ERROR, not a silent pass"
            )

        no_reason = tmpdir / "no_reason.json"
        no_reason.write_text(
            json.dumps({"exemptions": [{"sha": full, "date": "2026-01-01"}]}),
            encoding="utf-8",
        )
        entries, problems = load_exemptions(no_reason)
        if entries or not problems:
            failures.append("probe: an entry carrying no reason must be an ERROR")

        broken = tmpdir / "broken.json"
        broken.write_text('{"exemptions": [', encoding="utf-8")
        entries, problems = load_exemptions(broken)
        if entries or not problems:
            failures.append("probe: malformed JSON must be an ERROR, not a silent pass")

    # The hook's installation facts — the mechanism the clause's second exemption is
    # admitted WITH. An uninstalled hook is silent, so every way it can be absent is
    # exercised here rather than discovered in a factory that had lost the mechanism.
    if hook_state_problems(exists=True, executable=True, configured=HOOKS_PATH_CONFIG):
        failures.append("probe: a present, executable, wired hook must report clean")
    for kwargs, why in (
        (
            {"exists": False, "executable": False, "configured": HOOKS_PATH_CONFIG},
            "a missing hook",
        ),
        (
            {"exists": True, "executable": False, "configured": HOOKS_PATH_CONFIG},
            "a hook git cannot execute",
        ),
        ({"exists": True, "executable": True, "configured": ""}, "an unwired hook"),
        (
            {"exists": True, "executable": True, "configured": ".git/hooks"},
            "a hook reachable only through a foreign hooksPath",
        ),
    ):
        if not hook_state_problems(**kwargs):
            failures.append(f"probe: {why} must be reported, not passed")

    return failures

def main() -> int:
    problems = probe()

    top = repo_toplevel()
    if top is None:
        problems.append(
            f"{REPO} is not inside a git work tree — the hook's installation, and "
            "the ledger's history, cannot be read"
        )
    else:
        problems.extend(hook_installation_problems(top))
    excused: list[tuple[str, dict]] = []

    if not marker_resolves():
        problems.append(
            f"the marker commit {MARKER} does not resolve — a history rewrite "
            "invalidates it. Re-anchor MARKER to the first ledger commit obeying the "
            "clause; do not delete the gate."
        )
    else:
        exemptions, data_problems = load_exemptions(exemptions_file())
        problems.extend(data_problems)

        commits = ledger_commits_after()
        bad = offenders(commits)
        print(f"ledger clause: examined {len(commits)} commit(s) after {MARKER}")

        for full, short, subject in bad:
            entry = exemptions.get(full)
            if entry is None:
                problems.append(f"{short} cites a row number: {subject}")
            else:
                excused.append((full, entry))

        # A stale exemption matches nothing, so it inflates the count of visible debt
        # while excusing nothing. Reported rather than ignored: an exemption list that
        # silently does nothing is a gate lying about its own coverage.
        for full in sorted(set(exemptions) - {f for f, _, _ in bad}):
            problems.append(
                f"exemption {full} matches no violation in {MARKER}..HEAD — a stale "
                "exemption excuses nothing; remove it or correct the sha"
            )

        for full, entry in excused:
            print(f"  excused: {full} — {entry.get('reason', '')}")

    if problems:
        for line in problems:
            print(f"  FAIL {line}")
        return 1

    if excused:
        print(
            f"ledger clause: excused — {len(excused)} exempted violation(s) in "
            f"{MARKER}..HEAD; this is a visible debt, not a clean run"
        )
    else:
        print("ledger clause: clean — no commit after the marker cites row numbers")
    return 0

if __name__ == "__main__":
    sys.exit(main())
