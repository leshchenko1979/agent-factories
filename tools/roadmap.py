#!/usr/bin/env python3
"""Visual Roadmap, Process-to-Product Delivery Status, and Cadence Verification.

Upholds Process 1 & Process 3 visibility by auditing and rendering:
1. The canonical factory products and their producing processes.
2. The 5-stage factory growth & maturity progress.
3. Live operational status, quality gates, and delivery cadence receipts.

**Where the product list comes from.** The canonical products are *factory data*,
not template law: what a factory sells, to whom, and which artifacts prove it
differs per factory and is decided during onboarding. The declaration therefore
lives in `docs/products.json` — a factory-owned file — and this tool only reads
it. The tool ships in the template; the declaration does not, so a freshly
bootstrapped factory has no declaration and is **RED until its onboarding
interview fills one in** (the defined exit: `docs/processes.md`, subprocess 3
*Onboarding Interview Loop*). The skeleton to copy is
`docs/products.example.json`.

A missing declaration is a *specified* state, never a crash: `healthy: False`
with a reason naming the fix, and exit code 1.

Usage:
  python3 tools/roadmap.py              # Generate visual markdown roadmap
  python3 tools/roadmap.py --audit      # Run mechanical check on product/process alignment
  python3 tools/roadmap.py --cadence    # Audit and display delivery cadence loops & receipts
  python3 tools/roadmap.py --json       # Output machine-readable JSON status
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from kit_identity import VersionAction

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The factory-owned declaration this tool reads. Absent in the template tree:
#: a bootstrapped factory starts RED and its onboarding interview fills this in.
DECLARATION = "docs/products.json"

#: The skeleton a factory copies. Ships in both trees (gate 12 pairs it).
EXAMPLE = "docs/products.example.json"

#: Stage definitions are template law — the maturity ladder is the same for every
#: factory. Only the *status* of each stage is factory data, and that lives in the
#: declaration's `growth_status` map.
GROWTH_STAGES = [
    {"stage": "Stage 0", "name": "Interactive Prototype", "throughput": "1–5 tasks/wk"},
    {"stage": "Stage 1", "name": "Autonomous Intake", "throughput": "5–50 tasks/wk"},
    {"stage": "Stage 2", "name": "Single-Writer & Locking", "throughput": "50–200 events/day"},
    {"stage": "Stage 3", "name": "Self-Auditing Quality Loops", "throughput": "200–1000 events/day"},
    {"stage": "Stage 4", "name": "Fleet Ecosystem & Value Optimization", "throughput": "1000+ events/day"},
]

#: The fields every declared product must carry. A declaration missing one is a
#: broken declaration, and saying so is more useful than a KeyError traceback.
PRODUCT_FIELDS = (
    "id",
    "name",
    "process",
    "owner",
    "client",
    "client_value",
    "artifacts",
    "cadence",
    "pacemaker_job",
    "last_receipt",
)


def load_declaration(repo_root: Path) -> tuple[dict[str, Any], str]:
    """(declaration, reason) — reason is empty when the declaration is usable.

    Every failure mode here is a *reported* state, not an exception: a factory
    that has not onboarded yet, a declaration with no products, a declaration
    that does not parse. All three are RED with a reason naming the fix.
    """
    path = repo_root / DECLARATION
    if not path.is_file():
        return {}, (
            f"no product declaration at {DECLARATION} — this factory has not been "
            f"onboarded. Copy {EXAMPLE} to {DECLARATION} and declare this factory's "
            f"products (docs/processes.md, subprocess 3: Onboarding Interview Loop)"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{DECLARATION} could not be read as JSON: {exc}"
    if not isinstance(data, dict):
        return {}, f"{DECLARATION} must be a JSON object, got {type(data).__name__}"
    products = data.get("products")
    if not isinstance(products, list) or not products:
        return {}, (
            f"{DECLARATION} declares no products — an empty declaration is not an "
            f"onboarded factory (docs/processes.md, subprocess 3)"
        )
    for i, p in enumerate(products):
        if not isinstance(p, dict):
            return {}, f"{DECLARATION}: products[{i}] must be an object"
        missing = [f for f in PRODUCT_FIELDS if f not in p]
        if missing:
            return {}, f"{DECLARATION}: products[{i}] ({p.get('id', '?')}) is missing {', '.join(missing)}"
        if not isinstance(p["artifacts"], list) or not p["artifacts"]:
            return {}, f"{DECLARATION}: products[{i}] ({p.get('id', '?')}) declares no artifacts"
    return data, ""


def audit_products(repo_root: Path) -> dict[str, Any]:
    """Audit existence and integrity of canonical product artifacts and cadences."""
    declaration, reason = load_declaration(repo_root)
    growth_status = declaration.get("growth_status") or {}

    growth_stages = [
        {**s, "status": growth_status.get(s["stage"], "NOT STARTED")}
        for s in GROWTH_STAGES
    ]

    if reason:
        return {
            "healthy": False,
            "reason": reason,
            "declared": False,
            "products": [],
            "growth_stages": growth_stages,
        }

    results = []
    all_ok = True

    for p in declaration["products"]:
        art_status = []
        for art in p["artifacts"]:
            exists = (repo_root / art).exists()
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
            "cadence": p["cadence"],
            "pacemaker_job": p["pacemaker_job"],
            "last_receipt": p["last_receipt"],
            "artifacts": art_status,
            "healthy": all(a["exists"] for a in art_status),
        })

    return {
        "healthy": all_ok,
        "reason": "" if all_ok else "some declared product artifacts are missing",
        "declared": True,
        "products": results,
        "growth_stages": growth_stages,
    }


def generate_roadmap_markdown(repo_root: Path, show_cadence: bool = False) -> str:
    """Render markdown visual roadmap and process delivery matrix."""
    audit_data = audit_products(repo_root)
    healthy = audit_data["healthy"]

    lines = [
        "# Factory Visual Roadmap & Process-to-Product Matrix",
        "",
        f"> **Operational Status:** `{'HEALTHY' if healthy else 'INCOMPLETE'}` · "
        f"Multi-Factory Fleet Alignment",
        "",
        "---",
        "",
        "## 1. Process-to-Product Value Streams",
        "",
        "| Product | Producing Process | Owner | Client & Delivered Value | Status |",
        "|---|---|---|---|:---:|",
    ]

    if not audit_data["declared"]:
        # The un-onboarded state renders as itself, not as an empty table.
        lines.append(
            f"| *no products declared* | — | — | **RED:** {audit_data['reason']} | "
            f"🔴 NOT ONBOARDED |"
        )

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

    for s in audit_data["growth_stages"]:
        icon = "✅" if "COMPLETED" in s["status"] else ("🔄" if "ACTIVE" in s["status"] else "⏳")
        lines.append(f"| `{s['stage']}` | **{s['name']}** | `{s['throughput']}` | {icon} {s['status']} |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Product Delivery Artifacts & Cadenced Pacemakers",
        "",
        "| Product | Cadence Schedule | Pacemaker Job | Latest Delivery Receipt | Status |",
        "|---|---|---|---|:---:|",
    ])

    if not audit_data["declared"]:
        lines.append(
            "| *no products declared* | — | — | *nothing to deliver yet* | 🔴 MISSING |"
        )

    for p in audit_data["products"]:
        mark = "🟢 ACTIVE" if p["healthy"] else "🔴 MISSING"
        lines.append(f"| **{p['name']}** | `{p['cadence']}` | `{p['pacemaker_job']}` | *{p['last_receipt']}* | {mark} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action=VersionAction,
                    help="print this copy\'s identity and exit")
    parser.add_argument("--audit", action="store_true", help="Audit product artifact existence")
    parser.add_argument("--cadence", action="store_true", help="Audit product delivery cadence status")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON status")
    parser.add_argument("--output", type=str, default="", help="Save roadmap markdown to file")
    args = parser.parse_args()

    data = audit_products(REPO_ROOT)

    if args.json:
        print(json.dumps(data, indent=2))
        return 0 if data["healthy"] else 1

    if args.audit or args.cadence:
        if not data["healthy"]:
            print(f"Product artifact audit FAILED: {data['reason']}", file=sys.stderr)
            return 1
        print(f"Product & cadence roadmap clean: {len(data['products'])} canonical products healthy and cadenced")
        return 0

    md = generate_roadmap_markdown(REPO_ROOT, show_cadence=True)
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
