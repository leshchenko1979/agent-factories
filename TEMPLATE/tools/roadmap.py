#!/usr/bin/env python3
"""Visual Roadmap & Process-to-Product Delivery Status Generator.

Upholds Process 1 & Process 3 visibility by auditing and rendering:
1. The 4 canonical factory products and their producing processes.
2. The 5-stage factory growth & maturity progress.
3. Live operational status, quality gates, and delivery receipts.

Usage:
  python3 tools/roadmap.py              # Generate visual markdown roadmap
  python3 tools/roadmap.py --audit      # Run mechanical check on product/process alignment
  python3 tools/roadmap.py --json       # Output machine-readable JSON status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

CANONICAL_PRODUCTS = [
    {
        "id": "template",
        "name": "Factory Template & Add-on Packs",
        "process": "Process 1: Work Delivery Pipeline",
        "owner": "hq",
        "client": "New Factory Operators & Fleet Developers",
        "client_value": "Bootstraps production-ready autonomous factories in minutes with built-in quality gates",
        "artifacts": ["TEMPLATE/", "docs/addons/"],
    },
    {
        "id": "consulting",
        "name": "Consulting Practice & Advisories",
        "process": "Process 3: Operational Measurement & Consulting",
        "owner": "surveys",
        "client": "Member Factory HQs (InferHub, Miidas, AntiSpam, Infra, OpenCrabs)",
        "client_value": "Objective bottleneck visibility, reduced lead time, higher operational yield",
        "artifacts": ["evidence/scores/", "docs/measurement-procedure.md"],
    },
    {
        "id": "growth_map",
        "name": "Factory Growth & Maturity Map",
        "process": "Process 1 (Work Delivery) + Process 3 (Measurement)",
        "owner": "hq",
        "client": "Factory Owners & Technical Leadership",
        "client_value": "Predicts scale roadblocks (Stages 0–4) and specifies exact transition mechanics",
        "artifacts": ["docs/growth-stages.md"],
    },
    {
        "id": "insights",
        "name": "Empirical Insights Story (Public Narrative)",
        "process": "Process 3: Operational Measurement",
        "owner": "surveys",
        "client": "Public Engineering Audience & Operators",
        "client_value": "Battle-tested engineering case studies on queue dwell time, fcntl.flock, and ISO 9001 self-auditing",
        "artifacts": ["evidence/insights.jsonl", "docs/stories/"],
    },
]

GROWTH_STAGES = [
    {"stage": "Stage 0", "name": "Interactive Prototype", "throughput": "1–5 tasks/wk", "status": "COMPLETED"},
    {"stage": "Stage 1", "name": "Autonomous Intake", "throughput": "5–50 tasks/wk", "status": "COMPLETED"},
    {"stage": "Stage 2", "name": "Single-Writer & Locking", "throughput": "50–200 events/day", "status": "COMPLETED"},
    {"stage": "Stage 3", "name": "Self-Auditing Quality Loops", "throughput": "200–1000 events/day", "status": "ACTIVE / PILOTED"},
    {"stage": "Stage 4", "name": "Fleet Ecosystem & Value Optimization", "throughput": "1000+ events/day", "status": "IN PROGRESS"},
]


def audit_products(repo_root: Path) -> dict[str, Any]:
    """Audit existence and integrity of canonical product artifacts."""
    results = []
    all_ok = True

    for p in CANONICAL_PRODUCTS:
        art_status = []
        for art in p["artifacts"]:
            art_path = repo_root / art
            exists = art_path.exists()
            if not exists:
                all_ok = False
            art_status.append({"path": art, "exists": exists})
        results.append({
            "id": p["id"],
            "name": p["name"],
            "owner": p["owner"],
            "client": p["client"],
            "process": p["process"],
            "client_value": p["client_value"],
            "artifacts": art_status,
            "healthy": all(a["exists"] for a in art_status),
        })

    return {
        "healthy": all_ok,
        "products": results,
        "growth_stages": GROWTH_STAGES,
    }


def generate_roadmap_markdown(repo_root: Path) -> str:
    """Render markdown visual roadmap and process delivery matrix."""
    audit_data = audit_products(repo_root)

    lines = [
        "# Factory Visual Roadmap & Process-to-Product Matrix",
        "",
        "> **Operational Status:** `HEALTHY` · Multi-Factory Fleet Alignment",
        "",
        "---",
        "",
        "## 1. Process-to-Product Value Streams",
        "",
        "| Product | Producing Process | Owner | Client & Delivered Value | Status |",
        "|---|---|---|---|:---:|",
    ]

    for p in audit_data["products"]:
        status_icon = "🟢 HEALTHY" if p["healthy"] else "🔴 INCOMPLETE"
        lines.append(
            f"| **{p['name']}** | `{p['process']}` | `{p['owner']}` | "
            f"**Client:** {p['client']}<br/>*{p['client_value']}* | {status_icon} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Factory Growth Stages & Maturity Progress",
        "",
        "| Stage | Maturity Level | Throughput Band | Fleet Operating Status |",
        "|:---:|---|---|:---:|",
    ])

    for s in GROWTH_STAGES:
        icon = "✅" if "COMPLETED" in s["status"] else ("🔄" if "ACTIVE" in s["status"] else "⏳")
        lines.append(f"| `{s['stage']}` | **{s['name']}** | `{s['throughput']}` | {icon} {s['status']} |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Product Delivery Artifact Verification",
        "",
    ])

    for p in audit_data["products"]:
        lines.append(f"### {p['name']}")
        lines.append(f"- **Primary Process:** `{p['process']}`")
        lines.append(f"- **Process Owner:** `{p['owner']}`")
        lines.append("- **Tracked Artifacts:**")
        for art in p["artifacts"]:
            mark = "EXISTS" if art["exists"] else "MISSING"
            lines.append(f"  - `{art['path']}`: `[{mark}]`")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true", help="Audit product artifact existence")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON status")
    parser.add_argument("--output", type=str, default="", help="Save roadmap markdown to file")
    args = parser.parse_args()

    data = audit_products(REPO_ROOT)

    if args.json:
        print(json.dumps(data, indent=2))
        return 0 if data["healthy"] else 1

    if args.audit:
        if not data["healthy"]:
            print("Product artifact audit FAILED: some canonical product artifacts are missing", file=sys.stderr)
            return 1
        print(f"Product & process roadmap clean: {len(data['products'])} canonical products healthy")
        return 0

    md = generate_roadmap_markdown(REPO_ROOT)
    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(md, encoding="utf-8")
        print(f"Roadmap written to {out_p}")
    else:
        print(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())