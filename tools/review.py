"""Multi-Lens Review Engine (Duty 4+6 Review Rotation / P32).

Manages periodic quality reviews of factory laws, tools, and artifacts.
Enforces:
  1. Complete census: all catalog lenses must run or be explicitly waived.
  2. State durability: state.json tracks cycle lifecycle and step-0 recovery.
  3. Receipt verification: reports verified with sha256 checksums on disk.
  4. Adversarial sub-agent dispatch: generates isolated, adversarial auditor prompts.

Usage:
  python3 tools/review.py init <cycle_id>
  python3 tools/review.py brief <lens> [--json]
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
from kit_identity import VersionAction

REPO_ROOT = Path(__file__).resolve().parent.parent

# Standard 14 Lenses across 6 families:
# Docs: A, B, G; Mechanical: J, P; Tools: C, E, F, D; State/Flow: H, M; Economics: T; Meta: I, S
CATALOG_LENSES = ["A", "B", "G", "J", "P", "C", "E", "F", "D", "H", "M", "T", "I", "S"]

LENS_METADATA: dict[str, dict[str, str]] = {
    "A": {
        "name": "Redundancy, Ontology & Provenance Sediment",
        "family": "1. DOCS & LANGUAGE",
        "scope": "All role cards (roles/*.md), process registers (processes.md), and process law (SKILL.md).",
        "instructions": (
            "1. Find rule duplication: identical constraints stated across different files.\n"
            "2. Enforce canonical ontology from ONTOLOGY.md; flag uncodified synonyms and aliases.\n"
            "3. Strip provenance sediment: dates, post-mortem anecdotes, and history belong in changelogs.\n"
            "4. Verify post-migration path sweeps: old file paths or retired CLI flags lingering in instructions.\n"
            "5. Check numeric enumeration consistency (claimed counts vs actual definitions)."
        ),
    },
    "B": {
        "name": "LLM Efficiency, No-Op Pruning & Responsibility Creep",
        "family": "1. DOCS & LANGUAGE",
        "scope": "Token weight, role focus, and cognitive load across role instructions.",
        "instructions": (
            "1. Check responsibility creep: role files must contain only what the executing role needs.\n"
            "2. Apply the No-Op Test: prune sentences instructing the model to do what it does naturally.\n"
            "3. Apply the Cache Test: document only what cannot be derived by CLI inspection.\n"
            "4. Apply the Negation Test: replace negative prohibitions with positive boundaries.\n"
            "5. Prune subsumed manual procedures when composite CLI tools exist."
        ),
    },
    "G": {
        "name": "Role File Structure & Checkable Completion",
        "family": "1. DOCS & LANGUAGE",
        "scope": "Cohesion, work sequence, and exit criteria within each role file.",
        "instructions": (
            "1. Section cohesion: verify one section equals one operational concern.\n"
            "2. Checkable completion criteria: every procedure must terminate on deterministic conditions.\n"
            "3. Load path integrity: verify role paths and recovery anchors survive compactions."
        ),
    },
    "J": {
        "name": "Law-to-Tool Migration (The Pure Function Test)",
        "family": "2. MECHANICAL & PROTOCOL",
        "scope": "The entire corpus of written factory law and directives.",
        "instructions": (
            "1. Apply the Pure Function Test: Is this decision a pure function of disk state?\n"
            "2. Identify unwritten tool specs: rules telling agents to manually derive state.\n"
            "3. Propose deterministic CLI scripts, hooks, or unit tests to replace prose."
        ),
    },
    "P": {
        "name": "Pacemaker & Autonomous Convergence",
        "family": "2. MECHANICAL & PROTOCOL",
        "scope": "Cron configuration, outer heartbeat loops, and autonomous task convergence.",
        "instructions": (
            "1. 0-Token Quiescence (P28): verify idle cron pacemakers use trigger_cmd short-circuits.\n"
            "2. Goal State Convergence: verify crons run against deterministic set_goal conditions.\n"
            "3. Dead Session Detection: verify crons target live session UUIDs and bound topics."
        ),
    },
    "C": {
        "name": "CLI Automation Gaps & Usage Analysis",
        "family": "3. TOOLS & INTERFACES",
        "scope": "Manual procedures and tool invocation telemetry.",
        "instructions": (
            "1. Detect recurring multi-step manual commands in role workflows.\n"
            "2. Propose unified CLI signatures in tools/ to automate plumbing.\n"
            "3. Analyze tool error distributions and uninvoked legacy tools."
        ),
    },
    "E": {
        "name": "Interface Topology & Command Merging",
        "family": "3. TOOLS & INTERFACES",
        "scope": "The CLI tool surface across tools/.",
        "instructions": (
            "1. Identify chained invocations: tool pairs always run in immediate succession.\n"
            "2. Find duplicate interfaces: overlapping flags or verbs across different scripts.\n"
            "3. Propose consolidated command syntax."
        ),
    },
    "F": {
        "name": "Tool Implementation Quality & Exit Contracts",
        "family": "3. TOOLS & INTERFACES",
        "scope": "Source code of scripts in tools/ and test runners in tests/.",
        "instructions": (
            "1. Exit code determinism: success exits 0, failures exit distinct non-zero codes.\n"
            "2. Shell hygiene: verify strict error trapping (set -euo pipefail) and variable quoting.\n"
            "3. Atomic journaling: ensure state mutations write ledger entries atomically."
        ),
    },
    "D": {
        "name": "Deletion Safety & YAGNI Pruning",
        "family": "3. TOOLS & INTERFACES",
        "scope": "File tree, state directories, scratch files, and legacy configurations.",
        "instructions": (
            "1. Enumerate stale, retired, or orphaned files and test fixtures.\n"
            "2. Perform reference counting across codebase, scripts, and docs.\n"
            "3. Classify candidates: DELETE-SAFE (0 references), ARCHIVE, or KEEP."
        ),
    },
    "H": {
        "name": "Ledger Invariants & Monotonicity",
        "family": "4. STATE, DELIVERY & FLOW",
        "scope": "State journals, ledger.jsonl, and subprocess event streams.",
        "instructions": (
            "1. Verify strict monotonic row numbering and timestamp ordering.\n"
            "2. Verify lifecycle sequence: every close has a prior claim, and every claim an intake.\n"
            "3. Audit actor attribution and verify single-writer locking compliance."
        ),
    },
    "M": {
        "name": "Value Stream, Flow & WIP Stagnation",
        "family": "4. STATE, DELIVERY & FLOW",
        "scope": "Task throughput, dwell times, and batch size constraints.",
        "instructions": (
            "1. Detect WIP stagnation: identify tasks parked in intake/claim for >24 hours.\n"
            "2. Measure lead time (T_intake -> T_close) across recent work units.\n"
            "3. Enforce single-piece flow and batch size limits (P11)."
        ),
    },
    "T": {
        "name": "Token Economics & Cost-Per-Success",
        "family": "5. ECONOMICS & TELEMETRY",
        "scope": "Token consumption, model tier routing, and billing logs.",
        "instructions": (
            "1. Compute unit cost-per-successful-task (USD/task) across workflows.\n"
            "2. Audit model right-sizing: ensure expensive reasoning models are not used for mechanical tasks.\n"
            "3. Analyze prompt caching hit rates and context inflation."
        ),
    },
    "I": {
        "name": "Meta-Review & Catalog Brief Integrity",
        "family": "6. META-GOVERNANCE",
        "scope": "The 14 review lenses and review machinery.",
        "instructions": (
            "1. Audit review lenses for scope drift, overlapping coverage, or missing families.\n"
            "2. Verify that review reports cite exact locators and verbatim quotes.\n"
            "3. Ensure the review census mechanism (tools/review.py) remains un-bypassable."
        ),
    },
    "S": {
        "name": "Brain Scrub & Cross-Profile Cleanliness",
        "family": "6. META-GOVERNANCE",
        "scope": "Shared AGENTS.md vs factory-specific skills.",
        "instructions": (
            "1. Verify that AGENTS.md carries only a minimal one-line recovery anchor.\n"
            "2. Verify zero factory-specific rules leaked into shared profile brain files.\n"
            "3. Check that member-specific domain rules live only in their dedicated repo skills."
        ),
    },
}


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


def cmd_brief(lens: str, json_out: bool = False) -> int:
    lens = lens.upper()
    if lens not in CATALOG_LENSES or lens not in LENS_METADATA:
        print(f"Error: Lens '{lens}' not found in catalog {CATALOG_LENSES}", file=sys.stderr)
        return 2

    meta = LENS_METADATA[lens]
    prompt_text = f"""# ADVERSARIAL AUDITOR BRIEF — LENS {lens}: {meta['name']}
Family: {meta['family']}

## ADVERSARIAL MISSION
You are an ISOLATED ADVERSARIAL AUDITOR. You have zero shared context with the factory author.
Your goal is NOT to validate or confirm compliance. Your goal is to find DEFECTS, CONTRADICTIONS,
PROMPT BLOAT, UN-GATED DIRECTIVES, AND SILENT OMISSIONS.

Assume the rules are decaying, tools are leaky, and documentation has drifted.
Praising without concrete findings is considered a failed audit.

## SCOPE
{meta['scope']}

## INSPECTION TARGETS
{meta['instructions']}

## REQUIRED FINDINGS FORMAT
Every finding MUST include:
1. File Locator: `path/to/file.md:line_number`
2. Verbatim Quote: Exact code or text snippet
3. Defect Analysis: Why this violates law, wastes tokens, or risks execution
4. Actionable Remediation: Concrete patch or deletion proposal

Record your findings via:
  python3 tools/review.py record <cycle_id> {lens} <report_file_or_text>
"""
    if json_out:
        out = {
            "lens": lens,
            "name": meta["name"],
            "family": meta["family"],
            "scope": meta["scope"],
            "instructions": meta["instructions"],
            "adversarial_prompt": prompt_text,
        }
        print(json.dumps(out, indent=2))
    else:
        print(prompt_text.strip())
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

    lens_names = {k: v["name"] for k, v in LENS_METADATA.items()}

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
    parser.add_argument("--version", action=VersionAction,
                    help="print this copy\'s identity and exit")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    p_init = subparsers.add_parser("init", help="Initialize a new review cycle")
    p_init.add_argument("cycle_id", help="Review cycle identifier (e.g. 20260917-c1)")

    p_brief = subparsers.add_parser("brief", help="Generate adversarial subagent prompt for a lens")
    p_brief.add_argument("lens", help="Lens letter (A-J, P, M, T, S)")
    p_brief.add_argument("--json", action="store_true", help="Output as JSON object")

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
    elif args.subcommand == "brief":
        return cmd_brief(args.lens, json_out=args.json)
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
    return 1


if __name__ == "__main__":
    sys.exit(main())
