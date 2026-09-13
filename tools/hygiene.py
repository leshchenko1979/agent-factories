#!/usr/bin/env python3
"""Workspace hygiene tool — upholds the Cleanliness & Garbage Collection Law (P20).

Prevents host resource exhaustion by auditing and reaping stale scratch
scripts, temporary run artifacts, and untracked repository clutter.
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
    "/tmp/tmp.*",
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


def audit_git_clutter() -> list[str]:
    """Check if repository working tree has untracked clutter or temp files."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except Exception as e:
        return [f"git status failed: {e}"]

    clutter = []
    for line in res.stdout.splitlines():
        if line.startswith("??"):
            path = line[3:].strip()
            if path.endswith((".bak", ".tmp", ".log", ".orig")):
                clutter.append(path)
    return clutter


def main() -> int:
    parser = argparse.ArgumentParser(description="Workspace hygiene and GC audit tool.")
    parser.add_argument("--audit", action="store_true", help="Audit without removing")
    parser.add_argument("--clean", action="store_true", help="Reap stale scratch items")
    args = parser.parse_args()

    if not args.audit and not args.clean:
        args.audit = True

    dry_run = args.audit and not args.clean
    count, items = reap_stale_scratch(dry_run=dry_run)
    clutter = audit_git_clutter()

    if dry_run:
        if items or clutter:
            print(f"hygiene audit found {len(items) + len(clutter)} item(s):", file=sys.stderr)
            for item in items:
                print(f"  - stale scratch file: {os.path.basename(item)}", file=sys.stderr)
            for c in clutter:
                print(f"  - untracked git clutter: {c}", file=sys.stderr)
            return 1
        print("hygiene audit clean: 0 stale scratch items, clean git tree")
        return 0

    print(f"hygiene cleanup complete: {count} item(s) reaped")
    if clutter:
        print(f"warning: {len(clutter)} untracked git clutter item(s) remain:", file=sys.stderr)
        for c in clutter:
            print(f"  - {c}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
