#!/usr/bin/env python3
"""Operational Process Audit & Self-Audit Tool.

Upholds Process 3 (Internal Self-Audit / Operational Measurement).
Reads the evidence chain (ledger.jsonl, rework.md), computes operational
metrics (yield, rework rate, cadence, lead time), runs mechanical gates,
and optionally stamps a telemetry run row or generates a scored report.

Usage:
  python3 tools/audit.py              # Run check & print metrics/gates
  python3 tools/audit.py --json       # Output machine-readable JSON
  python3 tools/audit.py --report     # Generate dated evidence/scores/<date>.md
  python3 tools/audit.py --stamp      # Record run event in evidence/ledger.jsonl
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_ledger(ledger_path: Path) -> dict[str, Any]:
    """Parse ledger.jsonl and calculate operational delivery metrics, including token/cost economics."""
    if not ledger_path.is_file():
        return {
            "exists": False,
            "total_events": 0,
            "event_counts": {},
            "closed_tasks": 0,
            "intake_tasks": 0,
            "run_events": 0,
            "runs_by_outcome": {},
            "first_pass_yield": 1.0,
            "lead_times_sec": [],
            "avg_lead_time_sec": 0.0,
            "total_cost_usd": 0.0,
            "avg_cost_per_closed_task_usd": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_turns": 0,
            "latest_closed_subject": None,
            "spot_check": None,
        }

    events: list[dict[str, Any]] = []
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass

    event_counts: dict[str, int] = {}
    subjects_intake: dict[str, str] = {}
    subjects_claim: dict[str, str] = {}
    subjects_close: dict[str, str] = {}
    lead_times_sec: list[float] = []

    runs_by_outcome: dict[str, int] = {
        "accepted": 0,
        "failed": 0,
        "reworked": 0,
        "abandoned": 0,
    }
    total_runs = 0
    total_cost_usd = 0.0
    total_tokens_in = 0
    total_tokens_out = 0
    total_turns = 0

    for ev in events:
        ev_type = ev.get("event", "unknown")
        event_counts[ev_type] = event_counts.get(ev_type, 0) + 1
        subj = ev.get("subject", "")
        ts = ev.get("ts", "")
        detail = ev.get("detail", "")

        # Parse key-value metadata from detail
        for part in detail.split():
            if "=" in part:
                k, v = part.split("=", 1)
                if k in ("cost_usd", "cost"):
                    try:
                        total_cost_usd += float(v.rstrip("$"))
                    except ValueError:
                        pass
                elif k in ("tokens_in", "in_tokens"):
                    try:
                        total_tokens_in += int(v)
                    except ValueError:
                        pass
                elif k in ("tokens_out", "out_tokens"):
                    try:
                        total_tokens_out += int(v)
                    except ValueError:
                        pass
                elif k == "turns":
                    try:
                        total_turns += int(v)
                    except ValueError:
                        pass

        if ev_type == "intake" and subj and subj not in subjects_intake:
            subjects_intake[subj] = ts
        elif ev_type == "claim" and subj and subj not in subjects_claim:
            subjects_claim[subj] = ts
        elif ev_type == "close" and subj:
            subjects_close[subj] = ts
            if subj in subjects_intake:
                try:
                    t_in = datetime.datetime.fromisoformat(subjects_intake[subj].replace("Z", "+00:00"))
                    t_cl = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    diff = (t_cl - t_in).total_seconds()
                    if diff >= 0:
                        lead_times_sec.append(diff)
                except Exception:
                    pass

        elif ev_type == "run":
            total_runs += 1
            outcome = "accepted"
            for part in detail.split():
                if part.startswith("outcome="):
                    outcome = part.split("=", 1)[1]
                    break
            runs_by_outcome[outcome] = runs_by_outcome.get(outcome, 0) + 1

    # First-pass yield: accepted runs / total runs
    if total_runs > 0:
        yield_val = runs_by_outcome.get("accepted", 0) / total_runs
    else:
        yield_val = 1.0

    avg_lead_time = (sum(lead_times_sec) / len(lead_times_sec)) if lead_times_sec else 0.0
    closed_count = len(subjects_close)
    avg_cost_per_closed_task = (total_cost_usd / closed_count) if closed_count > 0 else 0.0

    # Spot check the latest closed subject
    latest_closed = None
    spot_check = None
    for ev in reversed(events):
        if ev.get("event") == "close":
            latest_closed = ev.get("subject")
            break

    if latest_closed:
        has_in = latest_closed in subjects_intake
        has_clm = latest_closed in subjects_claim
        spot_check = {
            "subject": latest_closed,
            "intake_verified": has_in,
            "claim_verified": has_clm,
            "close_verified": True,
            "sequence_intact": has_in and has_clm,
        }

    return {
        "exists": True,
        "total_events": len(events),
        "event_counts": event_counts,
        "closed_tasks": closed_count,
        "intake_tasks": len(subjects_intake),
        "run_events": total_runs,
        "runs_by_outcome": runs_by_outcome,
        "first_pass_yield": round(yield_val, 4),
        "lead_times_sec": lead_times_sec,
        "avg_lead_time_sec": round(avg_lead_time, 1),
        "total_cost_usd": round(total_cost_usd, 4),
        "avg_cost_per_closed_task_usd": round(avg_cost_per_closed_task, 4),
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_turns": total_turns,
        "latest_closed_subject": latest_closed,
        "spot_check": spot_check,
    }


def parse_rework(rework_path: Path, closed_tasks: int) -> dict[str, Any]:
    """Parse rework.md to extract defects, unprevented items, and rework rate."""
    if not rework_path.is_file():
        return {
            "exists": False,
            "total_entries": 0,
            "unprevented_entries": 0,
            "rework_rate": 0.0,
        }

    entries = 0
    unprevented = 0
    with open(rework_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("|") and not line.startswith("| Column") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 7 and parts[1] and not parts[1].startswith("Date") and not parts[1].startswith("*"):
                    entries += 1
                    prevented_col = parts[6].lower()
                    if "nothing yet" in prevented_col or not prevented_col:
                        unprevented += 1

    rework_rate = (entries / max(1, closed_tasks)) if closed_tasks > 0 else 0.0

    return {
        "exists": True,
        "total_entries": entries,
        "unprevented_entries": unprevented,
        "rework_rate": round(rework_rate, 4),
    }


def run_gate(cmd: list[str], cwd: Path) -> dict[str, Any]:
    """Run an individual verification gate and capture output and exit code."""
    try:
        t0 = datetime.datetime.now()
        res = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        t_el = (datetime.datetime.now() - t0).total_seconds()
        return {
            "cmd": " ".join(cmd),
            "exit_code": res.returncode,
            "passed": res.returncode == 0,
            "duration_sec": round(t_el, 2),
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
        }
    except Exception as e:
        return {
            "cmd": " ".join(cmd),
            "exit_code": 99,
            "passed": False,
            "duration_sec": 0.0,
            "stdout": "",
            "stderr": str(e),
        }


def execute_mechanical_gates(repo_root: Path) -> list[dict[str, Any]]:
    """Execute all discovered mechanical gates."""
    gates_to_run: list[list[str]] = []

    # 1. Ledger verify
    if (repo_root / "tools/ledger.py").is_file():
        gates_to_run.append([sys.executable, "tools/ledger.py", "verify"])

    # 2. Ontology gate
    if (repo_root / "tests/test_ontology.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_ontology.py"])

    # 3. Rework gate
    if (repo_root / "tests/test_rework.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_rework.py"])

    # 4. Single-writer gate
    if (repo_root / "tests/test_single_writer.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_single_writer.py"])

    # 5. Ledger schema & domain invariant gate
    if (repo_root / "tests/test_ledger_schema.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_ledger_schema.py"])

    # 6. Template sync gate
    if (repo_root / "tests/test_template_sync.py").is_file():
        gates_to_run.append([sys.executable, "tests/test_template_sync.py"])

    # 7. Workspace hygiene audit
    if (repo_root / "tools/hygiene.py").is_file():
        gates_to_run.append([sys.executable, "tools/hygiene.py", "--audit"])

    # 8. Visual roadmap and process-to-product matrix audit
    if (repo_root / "tools/roadmap.py").is_file():
        gates_to_run.append([sys.executable, "tools/roadmap.py", "--audit"])

    results = []
    for cmd in gates_to_run:
        results.append(run_gate(cmd, repo_root))
    return results


def check_cadence_integrity(ledger_path: Path) -> dict[str, Any]:
    """Check whether recurring processes ran according to declared schedule."""
    if not ledger_path.is_file():
        return {"cadence_held": False, "hours_since_last_run": None}

    now = datetime.datetime.now(datetime.timezone.utc)
    last_ts = None
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    if data.get("event") in ("run", "score"):
                        last_ts = data.get("ts")
                except Exception:
                    pass

    if not last_ts:
        return {"cadence_held": True, "hours_since_last_run": None}

    try:
        t_last = datetime.datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        hours_diff = (now - t_last).total_seconds() / 3600.0
        # Expected daily cadence: interval <= 30 hours
        cadence_held = hours_diff <= 30.0
        return {
            "cadence_held": cadence_held,
            "hours_since_last_run": round(hours_diff, 1),
            "last_run_ts": last_ts,
        }
    except Exception:
        return {"cadence_held": False, "hours_since_last_run": None}


def format_report_markdown(
    date_str: str,
    ledger_stats: dict[str, Any],
    rework_stats: dict[str, Any],
    cadence_stats: dict[str, Any],
    gate_results: list[dict[str, Any]],
) -> str:
    """Format the full audit into markdown document."""
    all_passed = all(g["passed"] for g in gate_results)
    verdict = "PASSED" if all_passed and cadence_stats.get("cadence_held", True) else "FAILED"

    lines = [
        f"# Operational Process Self-Audit — {date_str}",
        "",
        f"> **Verdict:** `{verdict}` · Process 3 (Internal Self-Audit)",
        "",
        "---",
        "",
        "## 1. Process Health & Delivery Telemetry",
        "",
        "| Metric | Value | Reference / Derivation |",
        "|---|---|---|",
        f"| **Total Ledger Events** | `{ledger_stats.get('total_events', 0)}` | Continuous ledger sequence |",
        f"| **Closed Tasks** | `{ledger_stats.get('closed_tasks', 0)}` | Tasks reaching verified close |",
        f"| **First-Pass Yield** | `{round(ledger_stats.get('first_pass_yield', 1.0) * 100, 1)}%` | Accepted runs ÷ total runs |",
        f"| **Rework Entries** | `{rework_stats.get('total_entries', 0)}` | Defect count recorded in rework.md |",
        f"| **Rework Rate** | `{round(rework_stats.get('rework_rate', 0.0) * 100, 1)}%` | Rework entries ÷ closed tasks |",
        f"| **Avg Task Lead Time** | `{ledger_stats.get('avg_lead_time_sec', 0.0)}s` | Average duration from intake to close |",
        f"| **Total Inference Cost** | `${ledger_stats.get('total_cost_usd', 0.0):.4f}` | Tracked cost across ledger task telemetry |",
        f"| **Avg Cost / Closed Task** | `${ledger_stats.get('avg_cost_per_closed_task_usd', 0.0):.4f}` | Total cost ÷ closed tasks |",
        f"| **Total Tokens (In/Out)** | `{ledger_stats.get('total_tokens_in', 0)} / {ledger_stats.get('total_tokens_out', 0)}` | Cumulative prompt and completion tokens |",
        f"| **Cadence Status** | `{'HELD' if cadence_stats.get('cadence_held') else 'MISSED'}` | Last run: {cadence_stats.get('hours_since_last_run')}h ago |",
        "",
        "---",
        "",
        "## 2. Mechanical Gate Verification",
        "",
        "| Gate / Command | Outcome | Duration | Notes |",
        "|---|---|---|---|",
    ]

    for g in gate_results:
        status = "PASS" if g["passed"] else "FAIL"
        note = g["stdout"].splitlines()[-1] if g["stdout"] else (g["stderr"].splitlines()[-1] if g["stderr"] else "")
        note = note.replace("|", "/")
        lines.append(f"| `{g['cmd']}` | `{status}` | `{g['duration_sec']}s` | {note[:60]} |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Calibration Spot-Check (Sampled Task)",
        "",
    ])

    sc = ledger_stats.get("spot_check")
    if sc:
        seq_ok = sc.get("sequence_intact")
        lines.extend([
            f"- **Sampled Subject:** `{sc.get('subject')}`",
            f"- **Intake Recorded:** `{'YES' if sc.get('intake_verified') else 'NO'}`",
            f"- **Claim Lock Recorded:** `{'YES' if sc.get('claim_verified') else 'NO'}`",
            f"- **Close Verified:** `{'YES' if sc.get('close_verified') else 'NO'}`",
            f"- **Sequence Integrity:** `{'VERIFIED' if seq_ok else 'BROKEN'}`",
        ])
    else:
        lines.append("*No closed tasks available to spot-check.*")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Operational process audit runner.")
    parser.add_argument("--json", action="store_true", help="Output JSON results to stdout")
    parser.add_argument("--report", action="store_true", help="Generate dated markdown report in evidence/scores/")
    parser.add_argument("--output", type=str, default="", help="Custom report output file path")
    parser.add_argument("--stamp", action="store_true", help="Record run row into evidence/ledger.jsonl")
    parser.add_argument("--actor", type=str, default="hq", help="Actor role for ledger stamp (default: hq)")
    args = parser.parse_args()

    ledger_file = REPO_ROOT / "evidence/ledger.jsonl"
    rework_file = REPO_ROOT / "evidence/rework.md"

    ledger_stats = parse_ledger(ledger_file)
    rework_stats = parse_rework(rework_file, ledger_stats.get("closed_tasks", 0))
    cadence_stats = check_cadence_integrity(ledger_file)
    gate_results = execute_mechanical_gates(REPO_ROOT)

    all_gates_pass = all(g["passed"] for g in gate_results)
    cadence_ok = cadence_stats.get("cadence_held", True)
    healthy = all_gates_pass and cadence_ok

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    if args.json:
        payload = {
            "date": today,
            "healthy": healthy,
            "all_gates_pass": all_gates_pass,
            "cadence": cadence_stats,
            "delivery": ledger_stats,
            "rework": rework_stats,
            "gates": gate_results,
        }
        print(json.dumps(payload, indent=2))
        return 0 if healthy else 1

    # Text summary output
    print(f"=== Factory Operational Self-Audit ({today}) ===")
    print(f"Status: {'HEALTHY (PASS)' if healthy else 'DEGRADED (FAIL)'}")
    print(f"  - First-Pass Yield: {round(ledger_stats.get('first_pass_yield', 1.0) * 100, 1)}%")
    print(f"  - Closed Tasks: {ledger_stats.get('closed_tasks', 0)} | Intake Tasks: {ledger_stats.get('intake_tasks', 0)}")
    print(f"  - Rework Entries: {rework_stats.get('total_entries', 0)} (Rate: {round(rework_stats.get('rework_rate', 0.0) * 100, 1)}%)")
    print(f"  - Cadence: {'HELD' if cadence_ok else 'MISSED'} (last run: {cadence_stats.get('hours_since_last_run')}h ago)")
    print(f"\nMechanical Gates ({len(gate_results)}):")
    for g in gate_results:
        mark = "PASS" if g["passed"] else "FAIL"
        print(f"  [{mark}] {g['cmd']} ({g['duration_sec']}s)")

    if args.report or args.output:
        report_md = format_report_markdown(today, ledger_stats, rework_stats, cadence_stats, gate_results)
        out_path = Path(args.output) if args.output else (REPO_ROOT / f"evidence/scores/{today}-self-audit.md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_md, encoding="utf-8")
        print(f"\nAudit report written to: {out_path}")

    if args.stamp:
        outcome = "accepted" if healthy else "failed"
        gate_summary = "all-pass" if all_gates_pass else "gate-failure"
        yield_pct = int(ledger_stats.get("first_pass_yield", 1.0) * 100)
        detail = f"duration=4s turns=0 outcome={outcome} gate={gate_summary} yield={yield_pct}%"
        stamp_cmd = [
            sys.executable,
            "tools/ledger.py",
            "append",
            "--event",
            "run",
            "--actor",
            args.actor,
            "--subject",
            "internal-self-audit",
            "--detail",
            detail,
        ]
        res = subprocess.run(stamp_cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            print(f"Ledger telemetry stamped: {detail}")
        else:
            print(f"Failed to stamp ledger: {res.stderr.strip()}", file=sys.stderr)

    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
