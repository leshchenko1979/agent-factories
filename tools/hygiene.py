#!/usr/bin/env python3
"""Workspace hygiene tool — upholds the Cleanliness & Garbage Collection Law (P20).

Prevents host resource exhaustion and recovery failures by auditing and reaping
stale scratch scripts, temporary run artifacts, untracked repository clutter,
and modified tracked working-tree files.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

SCRATCH_PATTERNS = [
    "/tmp/oc-*",
    "/tmp/test-*",
    "/tmp/vds-*",
]

MAX_AGE_HOURS = 24


def reap_stale_scratch(dry_run: bool = False) -> tuple[int, list[str]]:
    """Audit and optionally reap scratch artifacts older than MAX_AGE_HOURS."""
    now = time.time()
    cutoff = now - (MAX_AGE_HOURS * 3600)
    found: list[str] = []
    reaped = 0

    for pattern in SCRATCH_PATTERNS:
        for path in glob.glob(pattern):
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


def inspect_git_working_tree() -> tuple[list[str], list[str], list[str]]:
    """Inspect repository working tree for modified tracked files, untracked clutter, and untracked files.

    Returns:
        (modified_tracked, untracked_clutter, untracked_other)
    """
    try:
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

    modified_tracked: list[str] = []
    untracked_clutter: list[str] = []
    untracked_other: list[str] = []

    for line in res.stdout.splitlines():
        if not line:
            continue
        status_code = line[:2]
        path = line[3:].strip()
        if status_code == "??":
            if path.endswith((".bak", ".tmp", ".log", ".orig")):
                untracked_clutter.append(path)
            else:
                untracked_other.append(path)
        else:
            # Any non-?? status code represents staged, modified, or deleted tracked files
            modified_tracked.append(f"[{status_code}] {path}")

    return modified_tracked, untracked_clutter, untracked_other


def main() -> int:
    parser = argparse.ArgumentParser(description="Workspace hygiene and GC audit tool.")
    parser.add_argument("--audit", action="store_true", help="Audit without removing")
    parser.add_argument("--clean", action="store_true", help="Reap stale scratch items")
    args = parser.parse_args()

    if not args.audit and not args.clean:
        args.audit = True

    dry_run = args.audit and not args.clean
    count, items = reap_stale_scratch(dry_run=dry_run)
    modified_tracked, untracked_clutter, untracked_other = inspect_git_working_tree()

    if dry_run:
        # Audit mode: any stale scratch items, modified tracked files, or untracked clutter fail the gate
        total_violations = len(items) + len(modified_tracked) + len(untracked_clutter) + len(untracked_other)
        if total_violations > 0:
            print(f"hygiene audit found {total_violations} issue(s):", file=sys.stderr)
            for item in items:
                print(f"  - stale scratch file: {os.path.basename(item)}", file=sys.stderr)
            for m in modified_tracked:
                print(f"  - modified tracked file: {m}", file=sys.stderr)
            for c in untracked_clutter:
                print(f"  - untracked git clutter: {c}", file=sys.stderr)
            for u in untracked_other:
                print(f"  - untracked file: {u}", file=sys.stderr)
            return 1
        print("hygiene audit clean: 0 stale scratch items, 0 untracked clutter, working tree clean (0 modified tracked files)")
        return 0

    print(f"hygiene cleanup complete: {count} scratch item(s) reaped")
    if untracked_clutter:
        print(f"warning: {len(untracked_clutter)} untracked git clutter item(s) remain:", file=sys.stderr)
        for c in untracked_clutter:
            print(f"  - {c}", file=sys.stderr)
    if modified_tracked:
        print(f"warning: {len(modified_tracked)} modified tracked file(s) in working tree:", file=sys.stderr)
        for m in modified_tracked:
            print(f"  - {m}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
