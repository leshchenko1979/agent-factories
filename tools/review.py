#!/usr/bin/env python3
"""Multi-Lens Review Engine (Duty 4+6 Review Rotation / P32).

Manages periodic quality reviews of factory laws, tools, and artifacts.
Enforces:
  1. Complete census: all catalog lenses must run or be explicitly waived.
  2. State durability: state.json tracks cycle lifecycle and step-0 recovery.
  3. Receipt verification: reports verified with sha256 checksums on disk.

Usage:
  python3 tools/review.py init <cycle_id>
  python3 tools/review.py record <cycle_id> <lens> <report_path_or_text>
  python3 tools/review.py waive <cycle_id> <lens> --reason "..."
  python3 tools/review.py status <cycle_id>
  python3 tools/review.py verify <cycle_id>
  python3 tools/review.py compile <cycle_id>
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# Standard 14 Lenses across 6 families:
# Docs: A, B, G; Mechanical: J, P; Tools: C, E, F, D; State/Flow: H, M; Economics: T; Meta: I, S
CATALOG_LENSES = ["A", "B", "G", "J", "P", "C", "E", "F", "D", "H", "M", "T", "I", "S"]


def get_cycle_dir(cycle_id: str) -> Path:
    return REPO_ROOT / "reviews" / cycle_id


def load_state(cycle_id: str) -> dict[str, Any]:
    state_file = get_cycle_dir(cycle_id) / "state.json"
    if not state_file.is_file():
        return {}
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(cycle_id: str, state: dict[str, Any]) -> None:
    cycle_dir = get_cycle_dir(cycle_id)
    cycle_dir.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state_file = cycle_dir / "state.json"
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def cmd_init(cycle_id: str) -> int:
    cycle_dir = get_cycle_dir(cycle_id)
    reports_dir = cycle_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(cycle_id)
    if state and state.get("status") == "IN_PROGRESS":
        print(f"Cycle '{cycle_id}' already initialized and IN_PROGRESS.")
        return 0

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state = {
        "cycle_id": cycle_id,
        "started_at": now,
        "status": "IN_PROGRESS",
        "lenses": {lens: {"status": "PENDING", "report_path": None, "sha256": None} for lens in CATALOG_LENSES},
        "waivers": {},
        "codification_plan": [],
        "updated_at": now,
    }
    save_state(cycle_id, state)
    print(f"Initialized review cycle '{cycle_id}' with {len(CATALOG_LENSES)} catalog lenses.")
    return 0


def cmd_record(cycle_id: str, lens: str, content_or_path: str) -> int:
    lens = lens.upper()
    if lens not in CATALOG_LENSES:
        print(f"Error: Lens '{lens}' not in catalog {CATALOG_LENSES}", file=sys.stderr)
        return 2

    cycle_dir = get_cycle_dir(cycle_id)
    if not cycle_dir.is_dir():
        print(f"Error: Cycle '{cycle_id}' not found. Run init first.", file=sys.stderr)
        return 2

    # Read content
    input_path = Path(content_or_path)
    if input_path.is_file():
        body = input_path.read_text(encoding="utf-8")
    elif content_or_path == "-":
        body = sys.stdin.read()
    else:
        body = content_or_path

    body = body.strip()
    if not body:
        print("Error: Report content is empty.", file=sys.stderr)
        return 2

    reports_dir = cycle_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / f"lens-{lens}.md"

    # Write report
    report_file.write_text(body + "\n", encoding="utf-8")

    # Verify sha256 round-trip
    hasher = hashlib.sha256()
    hasher.update(report_file.read_bytes())
    digest = hasher.hexdigest()

    # Append to index log
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    index_file = cycle_dir / "review-index.log"
    with open(index_file, "a", encoding="utf-8") as f:
        f.write(f"{now}|{lens}|{report_file.name}|{digest}|{len(body)}\n")

    # Update state
    state = load_state(cycle_id)
    if not state:
        state = {"cycle_id": cycle_id, "lenses": {}, "waivers": {}}
    if "lenses" not in state:
        state["lenses"] = {}
    state["lenses"][lens] = {
        "status": "COMPLETED",
        "report_path": str(report_file.relative_to(REPO_ROOT)),
        "sha256": digest,
        "recorded_at": now,
    }
    save_state(cycle_id, state)
    print(f"Persisted report for Lens {lens}: {digest[:16]}... ({len(body)} bytes)")
    return 0


def cmd_waive(cycle_id: str, lens: str, reason: str) -> int:
    lens = lens.upper()
    if lens not in CATALOG_LENSES:
        print(f"Error: Lens '{lens}' not in catalog {CATALOG_LENSES}", file=sys.stderr)
        return 2
    if not reason.strip():
        print("Error: Waiver reason cannot be empty.", file=sys.stderr)
        return 2

    state = load_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state.setdefault("waivers", {})[lens] = {"reason": reason, "waived_at": now}
    state.setdefault("lenses", {})[lens] = {"status": "WAIVED", "reason": reason}
    save_state(cycle_id, state)

    waivers_file = get_cycle_dir(cycle_id) / "waivers.log"
    with open(waivers_file, "a", encoding="utf-8") as f:
        f.write(f"{now}|{lens}|{reason}\n")

    print(f"Waived Lens {lens}: {reason}")
    return 0


def cmd_status(cycle_id: str) -> int:
    state = load_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2

    print(f"=== Review Cycle: {cycle_id} ({state.get('status', 'UNKNOWN')}) ===")
    lenses = state.get("lenses", {})
    completed = 0
    waived = 0
    pending = 0

    for lens in CATALOG_LENSES:
        info = lenses.get(lens, {})
        status = info.get("status", "PENDING")
        if status == "COMPLETED":
            completed += 1
            print(f"  [{status}] Lens {lens} -> {info.get('report_path')} ({info.get('sha256', '')[:8]})")
        elif status == "WAIVED":
            waived += 1
            print(f"  [{status}] Lens {lens} -> {info.get('reason')}")
        else:
            pending += 1
            print(f"  [{status}] Lens {lens}")

    print(f"\nSummary: {completed} Completed | {waived} Waived | {pending} Pending (Total: {len(CATALOG_LENSES)})")
    return 0 if pending == 0 else 1


def cmd_verify(cycle_id: str) -> int:
    state = load_state(cycle_id)
    if not state:
        print(f"FAIL: Cycle '{cycle_id}' state.json missing.", file=sys.stderr)
        return 1

    lenses = state.get("lenses", {})
    missing: list[str] = []
    corrupted: list[str] = []

    for lens in CATALOG_LENSES:
        info = lenses.get(lens, {})
        status = info.get("status", "PENDING")
        if status == "WAIVED":
            continue
        if status != "COMPLETED":
            missing.append(lens)
            continue

        # Verify physical file existence and checksum
        rel_path = info.get("report_path")
        if not rel_path:
            missing.append(lens)
            continue
        abs_path = REPO_ROOT / rel_path
        if not abs_path.is_file():
            missing.append(f"{lens} (file missing: {rel_path})")
            continue

        hasher = hashlib.sha256()
        hasher.update(abs_path.read_bytes())
        actual_sha = hasher.hexdigest()
        if actual_sha != info.get("sha256"):
            corrupted.append(f"{lens} (checksum mismatch)")

    if missing or corrupted:
        print(f"FAIL: Cycle '{cycle_id}' census check failed.")
        if missing:
            print(f"  Missing or incomplete lenses: {', '.join(missing)}")
        if corrupted:
            print(f"  Checksum corrupted lenses: {', '.join(corrupted)}")
        return 1

    print(f"PASS: Cycle '{cycle_id}' census verified clean across all {len(CATALOG_LENSES)} lenses.")
    return 0


def cmd_compile(cycle_id: str) -> int:
    state = load_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2

    cycle_dir = get_cycle_dir(cycle_id)
    verdict_file = cycle_dir / "verdict.md"
    reports_dir = cycle_dir / "reports"

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Review Cycle {cycle_id} — Master Verdict ({now})",
        "",
        f"Status: {state.get('status', 'IN_PROGRESS')}",
        "",
        "## Census & Lenses Executed",
        "",
        "| Lens | Name / Focus | Status | Report |",
        "|---|---|---|---|",
    ]

    lens_names = {
        "A": "Redundancy & Ontology",
        "B": "LLM Efficiency & No-Op",
        "G": "Role File Structure",
        "J": "Law-to-Tool Migration",
        "C": "CLI Automation Gaps",
        "E": "Interface Topology",
        "F": "Tool Implementation Quality",
        "D": "Deletion Safety & YAGNI",
        "H": "Ledger Health & Invariants",
        "I": "Meta-Review of Catalog",
        "S": "Brain Scrub & Scope",
    }

    lenses = state.get("lenses", {})
    for lens in CATALOG_LENSES:
        info = lenses.get(lens, {})
        status = info.get("status", "PENDING")
        path = info.get("report_path", "—")
        lines.append(f"| **{lens}** | {lens_names.get(lens, '')} | `{status}` | `{path}` |")

    lines.extend([
        "",
        "## Consolidated Accepted Findings",
        "",
        "*(HQ populates accepted findings from triple-checked lens reports)*",
        "",
        "## Codification Batch Plan",
        "",
        "*(File edits and mechanical migrations applied in single version batch)*",
        "",
    ])

    verdict_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Compiled master verdict skeleton: {verdict_file.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-Lens Review Engine")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    p_init = subparsers.add_parser("init", help="Initialize a new review cycle")
    p_init.add_argument("cycle_id", help="Review cycle identifier (e.g. 20260917-c1)")

    p_record = subparsers.add_parser("record", help="Persist a lens report")
    p_record.add_argument("cycle_id", help="Cycle identifier")
    p_record.add_argument("lens", help="Lens letter (A-J, S)")
    p_record.add_argument("content", help="File path, '-' for stdin, or literal text")

    p_waive = subparsers.add_parser("waive", help="Explicitly waive a lens")
    p_waive.add_argument("cycle_id", help="Cycle identifier")
    p_waive.add_argument("lens", help="Lens letter")
    p_waive.add_argument("--reason", required=True, help="Reason for waiver")

    p_status = subparsers.add_parser("status", help="Show cycle progress")
    p_status.add_argument("cycle_id", help="Cycle identifier")

    p_verify = subparsers.add_parser("verify", help="Census verification gate")
    p_verify.add_argument("cycle_id", help="Cycle identifier")

    p_compile = subparsers.add_parser("compile", help="Generate verdict template")
    p_compile.add_argument("cycle_id", help="Cycle identifier")

    args = parser.parse_args()

    if args.subcommand == "init":
        return cmd_init(args.cycle_id)
    elif args.subcommand == "record":
        return cmd_record(args.cycle_id, args.lens, args.content)
    elif args.subcommand == "waive":
        return cmd_waive(args.cycle_id, args.lens, args.reason)
    elif args.subcommand == "status":
        return cmd_status(args.cycle_id)
    elif args.subcommand == "verify":
        return cmd_verify(args.cycle_id)
    elif args.subcommand == "compile":
        return cmd_compile(args.cycle_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
