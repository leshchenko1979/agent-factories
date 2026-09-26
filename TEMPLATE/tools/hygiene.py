#!/usr/bin/env python3
"""Workspace hygiene tool — upholds the Cleanliness & Garbage Collection Law (P20).

Prevents host resource exhaustion and recovery failures by auditing and reaping
stale scratch scripts, temporary run artifacts, untracked repository clutter,
and modified tracked working-tree files.

## In-flight is not stranded (issue #38)

This factory's working tree is SHARED. Several lanes edit it at once, so "a path is
dirty" and "a path was abandoned" are different facts, and an audit that cannot tell
them apart is a race, not a health signal: it goes RED whenever a peer lane is
mid-task, and the daily pacemaker then reports DEGRADED on a healthy factory.

The discriminator git actually offers is **age**. A file written two minutes ago
belongs to a lane that is still working; the same file a day later is stranded. So
the audit now classifies every finding as one of:

  * **violation** — fails the gate;
  * **advisory** — printed, does not fail, because it may be a lane's live work.

| Finding | Class |
|---|---|
| stale owned scratch (`/tmp/<this-factory>-*`, older than `MAX_AGE_HOURS`) | violation — already age-based |
| untracked litter (`*.bak` `*.tmp` `*.log` `*.orig`) | violation, no grace — litter is litter |
| untracked other (a new file) | advisory while younger than the grace window, then violation |
| modified tracked file | advisory while younger than the grace window, then violation |
| a path named by `--require-committed` | violation regardless of age |

The grace window is declared by the caller (`--grace-minutes`, default 60) rather
than hidden in this file, because how long a lane may hold a file is a property of
the factory's process, not of this tool.

**Why age and not an allowlist.** #38 warned against a fix that exempts
`evidence/ledger.jsonl` by path: it removes that one case and leaves the general one
(a peer's in-flight gate file). The general form is the same for every path, so the
rule is the same for every path.

**Why #28 stays fixed.** #28 was a *false green*: the audit reported clean without
examining modified tracked files at all. It still examines them, and a stranded one
still fails — it now has to be older than the window to be judged stranded, which is
what "stranded" means. The measurement run's own-artifact invariant gets the sharper
form: `--require-committed <path>` fails on a fresh dirty path with no grace at all,
because the run knows which artifacts are its own. A whole-tree check and a
run-scoped check coincide in a single-lane repo and diverge here; the run-scoped one
is the blocking one.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# A gate may only glob a namespace this factory OWNS.
#
# `/tmp` is shared. Another factory's tooling writes its own prefix there — the
# OpenCrabs dev tools leave `oc-snap-*` behind by the thousand. Globbing a
# foreign prefix makes this gate measure someone else's litter: it goes RED for
# work this factory did not do, the mirror of a false green and just as
# corrosive, because a gate that cries wolf gets ignored and then reverted.
#
# The owned namespace is the repository directory name, so a factory
# bootstrapped from this template owns its own prefix automatically. Extra owned
# namespaces are declared with --scratch-glob, never by widening this list to a
# prefix somebody else already uses.
NAMESPACE = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def scratch_patterns_for(namespace: str) -> list[str]:
    """The scratch globs a factory owning `namespace` may inspect.

    Factored out of the module constant so `--namespace` moves the population
    through the SAME expression the default uses. A second copy of the glob
    shape would let the flag and the default drift apart, which is the class
    this factory files against.
    """
    return [f"/tmp/{namespace}-*"]

SCRATCH_PATTERNS = scratch_patterns_for(NAMESPACE)

# The declaration the reaper consults before it unlinks. AGE ALONE cannot tell a
# stale scratch file from LIVE STATE: a lock created once and held long-term has
# an mtime nothing refreshes, so it is indistinguishable from litter by the only
# discriminator this tool has. The file is FACTORY DATA and never ships; the
# skeleton beside it (`docs/hygiene-protected.example.json`) is what a factory
# copies. An ABSENT file means this factory has declared no live paths, which is
# the shipped state of a new factory; a file that EXISTS and cannot be read is a
# reported problem, because only the silent failure is the hazard.
PROTECTED_REL = "docs/hygiene-protected.json"

def repo_root() -> Path:
    """The tree this copy of the tool belongs to."""
    return Path(__file__).resolve().parent.parent

def load_declaration(root: Path | None = None) -> tuple[list[dict], list[dict], list[str]]:
    """(protected, scratch, problems) read from the factory's declaration.

    `protected` entries name paths the reaper must SKIP; `scratch` entries name
    paths that are genuinely reapable, classified so the classifier gate can tell
    a declared literal from a new one. Both are lists of dicts with `path` and
    `why`; `why` is REQUIRED, because an entry nobody could defend in the output
    is one that should be fixed instead.

    An entry that matches nothing is PRINTED but is NOT a problem: this is a
    PREVENTION surface, and the point is to declare a path BEFORE the code that
    creates it lands. That is the one deliberate difference from the exemption
    surfaces, where an unmatched entry is a stale debt.
    """
    root = root or repo_root()
    path = root / PROTECTED_REL
    if not path.is_file():
        return [], [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [], [f"{PROTECTED_REL} exists but cannot be read: {exc}"]

    problems: list[str] = []
    out: dict[str, list[dict]] = {"protected": [], "scratch": []}
    for kind in ("protected", "scratch"):
        entries = data.get(kind, [])
        if not isinstance(entries, list):
            problems.append(f"{PROTECTED_REL}: `{kind}` must be a list")
            continue
        for i, entry in enumerate(entries):
            where = f"{PROTECTED_REL}: {kind}[{i}]"
            if not isinstance(entry, dict):
                problems.append(f"{where} must be an object")
                continue
            p, why = entry.get("path"), entry.get("why")
            if not isinstance(p, str) or not p.startswith("/tmp/"):
                problems.append(f"{where}: `path` must be an absolute /tmp path")
                continue
            if not isinstance(why, str) or not why.strip():
                problems.append(f"{where} ({p}): `why` is required and blank")
                continue
            out[kind].append(entry)
    return out["protected"], out["scratch"], problems

MAX_AGE_HOURS = 24

# How long a dirty path may be explained as a lane still working on it. The
# default is a floor, not a recommendation: a factory whose lanes routinely hold
# work longer raises it with --grace-minutes, in its own process law.
DEFAULT_GRACE_MINUTES = 60

LITTER_SUFFIXES = (".bak", ".tmp", ".log", ".orig")

def reap_stale_scratch(
    dry_run: bool = False,
    patterns: list[str] | None = None,
    protected: set[str] | None = None,
) -> tuple[int, list[str]]:
    """Audit and optionally reap scratch artifacts older than MAX_AGE_HOURS.

    Only the namespaces passed in (default: the ones this factory owns) are
    inspected; a foreign prefix is never globbed. `protected` is the set of paths
    DECLARED LIVE (`docs/hygiene-protected.json`): a protected path is skipped
    entirely — never reported as stale, never unlinked — because age alone cannot
    tell it from litter (#153).
    """
    now = time.time()
    cutoff = now - (MAX_AGE_HOURS * 3600)
    protected = protected or set()
    found: list[str] = []
    reaped = 0

    for pattern in (patterns or SCRATCH_PATTERNS):
        for path in glob.glob(pattern):
            if path in protected:
                continue
            try:
                mtime = os.path.getmtime(path)
                if mtime < cutoff:
                    age_h = int((now - mtime) / 3600)
                    found.append(f"{path} (age: {age_h}h)")
                    if not dry_run:
                        if os.path.isdir(path):
                            shutil.rmtree(path, ignore_errors=True)
                            reaped += 1
                        else:
                            os.remove(path)
                            reaped += 1
            except Exception:
                pass

    return (len(found) if dry_run else reaped), found

def _split_status_line(line: str) -> tuple[str, str]:
    """Return (status code, path) from one `git status --porcelain` line.

    A rename is reported as `R  old -> new`; the path that exists on disk — the
    one whose age is meaningful — is the new one.
    """
    status_code = line[:2]
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1].strip()
    if len(path) > 1 and path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    return status_code, path

def inspect_git_working_tree(
    repo_dir: str | None = None, now: float | None = None
) -> tuple[list[str], list[str], list[str]]:
    """Classify the working tree into (violations, advisories, explanations).

    A dirty path younger than the grace window is an advisory: it may be a lane's
    live work. The same path older than the window is a violation: nothing is
    working on it any more. Untracked litter is always a violation — age does not
    make a `.bak` legitimate.
    """
    now = time.time() if now is None else now
    try:
        repo_dir = repo_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except Exception as e:
        return ([f"git status failed: {e}"], [], [])

    violations: list[str] = []
    advisories: list[str] = []
    explanations: list[str] = []

    for line in res.stdout.splitlines():
        if not line:
            continue
        status_code, path = _split_status_line(line)
        full = os.path.join(repo_dir, path)
        try:
            age_min = int((now - os.path.getmtime(full)) / 60)
        except OSError:
            # Deleted from the working tree: nothing can be in flight about a file
            # that is gone, and a deleted tracked file left uncommitted is stranded.
            violations.append(f"[{status_code}] {path} (missing from the working tree)")
            continue

        if status_code == "??":
            if path.endswith(LITTER_SUFFIXES):
                violations.append(f"untracked git clutter: {path}")
            elif age_min >= GRACE_MINUTES:
                violations.append(f"untracked file: {path} (untouched for {age_min}m)")
            else:
                advisories.append(f"untracked file: {path} (age {age_min}m — possibly a lane's work in flight)")
        else:
            if age_min >= GRACE_MINUTES:
                violations.append(f"modified tracked file: [{status_code}] {path} (untouched for {age_min}m)")
            else:
                advisories.append(
                    f"modified tracked file: [{status_code}] {path} (age {age_min}m — possibly a lane's work in flight)"
                )

    for path in REQUIRED_COMMITTED:
        full = os.path.join(repo_dir, path)
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", path],
            cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()
        if status:
            violations.append(f"required committed, but dirty: {path} ({status})")
        elif not os.path.exists(full):
            violations.append(f"required committed, but absent: {path}")
        else:
            explanations.append(f"required committed: {path} clean")

    return (violations, advisories, explanations)

# Set by main() from --grace-minutes / --require-committed, so the classifier stays
# callable as a pure function from tests with an explicit window.
GRACE_MINUTES = DEFAULT_GRACE_MINUTES
REQUIRED_COMMITTED: list[str] = []

def main() -> int:
    global GRACE_MINUTES, REQUIRED_COMMITTED

    parser = argparse.ArgumentParser(description="Workspace hygiene and GC audit tool.")
    parser.add_argument("--audit", action="store_true", help="Audit without removing")
    parser.add_argument("--clean", action="store_true", help="Reap stale scratch items")
    parser.add_argument(
        "--scratch-glob",
        action="append",
        metavar="GLOB",
        help="Additional scratch namespace this factory owns (repeatable). "
        "Never pass a prefix another tool already writes to.",
    )
    parser.add_argument(
        "--namespace",
        default=NAMESPACE,
        metavar="NAME",
        help=f"The scratch namespace this factory OWNS (default: the repository "
        f"directory name, {NAMESPACE!r}). Pass it explicitly when running from a "
        f"worktree: the default follows the directory the TOOL sits in, so a "
        f"worktree measures a namespace belonging to nobody.",
    )
    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=DEFAULT_GRACE_MINUTES,
        metavar="N",
        help=f"How long a dirty path may be explained as a lane's work in flight "
        f"(default {DEFAULT_GRACE_MINUTES}). A path older than this is stranded.",
    )
    parser.add_argument(
        "--require-committed",
        action="append",
        default=[],
        metavar="PATH",
        help="A path this run owns and must find committed. Fails with NO grace, "
        "regardless of age (repeatable). This is the measurement run's closing "
        "invariant — the run-scoped form of the #28 catch.",
    )
    args = parser.parse_args()

    if not args.audit and not args.clean:
        args.audit = True

    GRACE_MINUTES = args.grace_minutes
    REQUIRED_COMMITTED = list(args.require_committed)

    dry_run = args.audit and not args.clean
    # The namespace is PRINTED on every run, with its provenance: a verdict over
    # a namespace the reader cannot see is unreproducible, and a worktree's run
    # site is exactly how the wrong one got measured in silence (#174).
    origin = (
        "default, the repository directory name"
        if args.namespace == NAMESPACE
        else "declared"
    )
    print(f"hygiene namespace: {args.namespace} ({origin})")
    protected_entries, scratch_entries, decl_problems = load_declaration()
    if decl_problems:
        for problem in decl_problems:
            print(f"hygiene declaration problem: {problem}", file=sys.stderr)
        return 1
    protected = {e["path"] for e in protected_entries}
    # The declaration's population is PRINTED on every run, with the counts a
    # reader needs to tell "nothing is declared live" from "the file was never
    # found": a reaper that silently protects nothing is the defect itself.
    print(
        f"hygiene declaration: {len(protected)} path(s) declared live, "
        f"{len(scratch_entries)} declared scratch ({PROTECTED_REL})"
    )
    patterns = scratch_patterns_for(args.namespace) + list(args.scratch_glob or [])
    count, items = reap_stale_scratch(
        dry_run=dry_run, patterns=patterns, protected=protected
    )
    violations, advisories, explanations = inspect_git_working_tree()

    if dry_run:
        # Audit mode: stale scratch, litter, stranded dirty paths and any path this
        # run declared as its own all fail the gate. Advisories are printed so the
        # signal is not lost — an audit that hides what it saw is how #28 happened —
        # but they do not fail, because a peer lane mid-task is not a defect.
        total_violations = len(items) + len(violations)
        for item in items:
            violations.insert(0, f"stale scratch file: {os.path.basename(item)}")
        if advisories:
            print(f"hygiene audit: {len(advisories)} advisory item(s) — not failures:", file=sys.stderr)
            for a in advisories:
                print(f"  ~ {a}", file=sys.stderr)
        if total_violations > 0:
            # The header states the window it judged on: a verdict that does not
            # carry its own predicate cannot be reproduced by its reader.
            print(
                f"hygiene audit found {total_violations} issue(s) "
                f"(stranded = untouched for {GRACE_MINUTES}m or more):",
                file=sys.stderr,
            )
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            return 1
        print(
            f"hygiene audit clean: 0 stale scratch items in "
            f"{', '.join(patterns)}, 0 stranded dirty paths (grace "
            f"{GRACE_MINUTES}m), {len(advisories)} advisory item(s), "
            f"working tree clean of violations"
        )
        return 0

    print(f"hygiene cleanup complete: {count} scratch item(s) reaped")
    if advisories:
        print(f"warning: {len(advisories)} dirty path(s) within the {GRACE_MINUTES}m grace window:", file=sys.stderr)
        for a in advisories:
            print(f"  ~ {a}", file=sys.stderr)
    if violations:
        print(f"warning: {len(violations)} stranded item(s) in the working tree:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
