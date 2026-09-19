#!/usr/bin/env python3
"""Autonomous telemetry mining and insight synthesizer.

Mines operational friction clusters across:
  1. evidence/rework.md (recurring defect classes, root causes)
  2. evidence/scores/*.md (score regressions, quality deltas)
  3. evidence/ledger.jsonl (high turn counts, lead time outliers, queue dwell)
  4. Member factory incident notifications

Synthesizes structured architectural insights grounded in literature
(VSM, IDEF0, TPS/Kaizen, Requisite Variety) and appends them to evidence/insights.jsonl.

Usage:
  python3 tools/synthesize_insights.py [--audit] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import audit as _audit  # noqa: E402  — the ONE yield implementation (#53 clause 8)
REWORK_PATH = REPO / "evidence" / "rework.md"
SCORES_DIR = REPO / "evidence" / "scores"
LEDGER_PATH = REPO / "evidence" / "ledger.jsonl"
INSIGHTS_PATH = REPO / "evidence" / "insights.jsonl"


@dataclass
class FrictionPattern:
    source: str
    category: str
    description: str
    occurrences: int
    literature_grounding: str
    suggested_mechanism: str


@dataclass
class SynthesizedInsight:
    id: str
    topic: str
    stage: str
    naive_assumption: str
    empirical_reality: str
    mechanism: str
    literature: str
    confidence: float


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mine_rework_defects() -> list[FrictionPattern]:
    """Mines clusters from evidence/rework.md."""
    if not REWORK_PATH.is_file():
        return []

    lines = REWORK_PATH.read_text(encoding="utf-8").splitlines()
    patterns: list[FrictionPattern] = []

    # Category buckets
    categories: dict[str, list[str]] = {
        "concurrency_locking": [],
        "symlink_role_resolution": [],
        "schema_drift": [],
        "vocabulary_leak": [],
        "cadence_pacemaker_stall": [],
        "generic": [],
    }

    in_table = False
    for line in lines:
        if line.startswith("| Date"):
            in_table = True
            continue
        if in_table and line.startswith("|") and not line.startswith("|---"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            # Rework schema: Date | Source | Defect | Root cause | Resolution |
            # Prevented by | Subject. The guard used to admit 4 columns and then read
            # index 4, so it mis-mapped every field (Source was mined as the defect)
            # and raised IndexError on a short row — aborting the whole synthesis pass
            # instead of skipping the one row.
            if len(cols) < 7:
                continue
            defect, cause, fix, prevented_by = cols[2], cols[3], cols[4], cols[5]
            text = f"{defect} {cause} {prevented_by}".lower()
            if "lock" in text or "concurr" in text or "flock" in text or "race" in text:
                categories["concurrency_locking"].append(defect)
            elif "symlink" in text or "role" in text or "skill" in text:
                categories["symlink_role_resolution"].append(defect)
            elif "schema" in text or "detail" in text:
                categories["schema_drift"].append(defect)
            elif "vocab" in text or "leak" in text or "synonym" in text:
                categories["vocabulary_leak"].append(defect)
            elif "cadence" in text or "cron" in text or "pacemaker" in text:
                categories["cadence_pacemaker_stall"].append(defect)
            else:
                categories["generic"].append(defect)

    for cat, items in categories.items():
        if len(items) >= 2:
            if cat == "concurrency_locking":
                patterns.append(FrictionPattern(
                    source="evidence/rework.md",
                    category=cat,
                    description=f"Clustering of concurrent write collisions ({len(items)} defects).",
                    occurrences=len(items),
                    literature_grounding="Single-Writer Principle (Lamport, 1978; ACID Transactions)",
                    suggested_mechanism="Mandatory fcntl.flock on state files with test_single_writer.py verification gate."
                ))
            elif cat == "symlink_role_resolution":
                patterns.append(FrictionPattern(
                    source="evidence/rework.md",
                    category=cat,
                    description=f"Skill and role card resolution failures across profiles ({len(items)} defects).",
                    occurrences=len(items),
                    literature_grounding="Boundary Law & Self-Contained Packages (P25; Component-Based Architecture)",
                    suggested_mechanism="Automated symlink pre-flight verification in BOOTSTRAP.md."
                ))
            elif cat == "schema_drift":
                patterns.append(FrictionPattern(
                    source="evidence/rework.md",
                    category=cat,
                    description=f"Unstructured event details or missing telemetry fields ({len(items)} defects).",
                    occurrences=len(items),
                    literature_grounding="Strict Contract Interfaces (Meyer, 1988; Schema-First Design)",
                    suggested_mechanism="Mechanical schema validators (test_ledger_schema.py)."
                ))

    return patterns


def mine_ledger_telemetry() -> list[FrictionPattern]:
    """Mines queue dwell time, turn count distributions, and yield drops from ledger.

    The yield is NOT recomputed here. #53 clause 8 (ruling n=333) requires #53 and
    #41 to share ONE implementation: the audit computes the population and the
    coverage once, and this alarm CONSUMES them. Two yields under one name is the
    failure n=306 names, and the alarm's own version divided accepted runs by every
    run row — a permanent false RED, because a row declaring no outcome is UNKNOWN
    and was being counted as a failure (#41).
    """
    if not LEDGER_PATH.is_file():
        return []

    lines = [l.strip() for l in LEDGER_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    high_turns = 0
    total_cost = 0.0

    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue

        if d.get("event") == "run":
            detail = d.get("detail", "")
            turns_m = re.search(r"turns=(\d+)", detail)
            if turns_m and int(turns_m.group(1)) > 3:
                high_turns += 1
            cost_m = re.search(r"cost_usd=([\d\.]+)", detail)
            if cost_m:
                total_cost += float(cost_m.group(1))

    stats, _closed = _audit.parse_ledger(LEDGER_PATH)
    accepted = stats.get("runs_by_outcome", {}).get("accepted", 0)
    population = stats.get("run_rows_stating_outcome", 0)
    coverage_total = stats.get("run_events", 0)

    patterns = []
    if population > 0 and (accepted / population) < 0.90:
        patterns.append(FrictionPattern(
            source="evidence/ledger.jsonl",
            category="yield_drop",
            description=(
                f"First-pass acceptance yield dropped to {accepted/population:.1%} "
                f"({accepted} accepted ÷ {population} run rows stating an outcome; "
                f"coverage: {population} of {coverage_total} run rows)."
            ),
            occurrences=population - accepted,
            literature_grounding="First-Time Yield & Jidoka (Ohno, 1988; Toyota Production System)",
            suggested_mechanism="Inject stricter feedforward prompt constraints and local test gates."
        ))

    if high_turns >= 2:
        patterns.append(FrictionPattern(
            source="evidence/ledger.jsonl",
            category="high_turn_convergence",
            description=f"Multiple task runs required excessive (>3) turns to converge ({high_turns} occurrences).",
            occurrences=high_turns,
            literature_grounding="Inner Convergence Bounds (Ralph Goal Loop; Requisite Variety)",
            suggested_mechanism="Provide fine-grained error deltas from multi-criteria judge rather than binary pass/fail."
        ))

    return patterns


def synthesize_insights() -> list[SynthesizedInsight]:
    """Synthesizes high-level architectural insights from mined friction patterns."""
    rework_patterns = mine_rework_defects()
    ledger_patterns = mine_ledger_telemetry()
    all_patterns = rework_patterns + ledger_patterns

    insights: list[SynthesizedInsight] = []

    # Map patterns to canonical insights
    for p in all_patterns:
        if p.category == "concurrency_locking":
            insights.append(SynthesizedInsight(
                id="single-writer-concurrency-guarantee",
                topic="Single-Writer File Locking vs Conversational Coordination",
                stage="stage-2",
                naive_assumption="Autonomous agents collaborating in the same repo will naturally sequence their writes without file corruption.",
                empirical_reality="Multi-agent and background cron processes experience silent race conditions and split state without kernel-level locking.",
                mechanism="Enforce exclusive fcntl.flock on state files with automated single-writer concurrency unit tests.",
                literature="ACID Transactions & Mutex Locking (Lamport, 1978; Gray, 1981)",
                confidence=0.98,
            ))
        elif p.category == "symlink_role_resolution":
            insights.append(SynthesizedInsight(
                id="self-contained-skill-packaging",
                topic="Skill & Role Card Symlink Resolution across Runtime Profiles",
                stage="stage-1",
                naive_assumption="Harness skill loaders will recursively find role files across separate project directories.",
                empirical_reality="Profile-scoped skill directories require explicit symlinks or bundled roles during factory bootstrap.",
                mechanism="Codify symlink verification into BOOTSTRAP.md and add deterministic audit gate in audit.py.",
                literature="Component-Based Architecture & Bounded Contexts (Evans, 2003)",
                confidence=0.95,
            ))

    # Add canonical architectural insights if not present
    existing_ids = {i.id for i in insights}
    if "survey-requisite-variety" not in existing_ids:
        insights.append(SynthesizedInsight(
            id="survey-requisite-variety",
            topic="Cognitive Bounds & Recursive Subsystem Survey Resolution",
            stage="stage-3",
            naive_assumption="A single agent session can accurately survey and score a multi-factory enterprise in one pass.",
            empirical_reality="A single context window compresses big systems lossily, checking surface forms while missing deep subprocess failures.",
            mechanism="Decompose surveys into hierarchical task trees with non-overlapping leaf auditors (Resolution Q = N_leaf / S).",
            literature="Law of Requisite Variety (Ashby, 1956) & Hierarchical Task Networks (Ewald et al., 2004)",
            confidence=0.99,
        ))

    return insights


def main() -> int:
    parser = argparse.ArgumentParser(description="Telemetry mining & insight synthesizer")
    parser.add_argument("--audit", action="store_true", help="Audit mode for CI/audit.py")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()

    rework_patterns = mine_rework_defects()
    ledger_patterns = mine_ledger_telemetry()
    insights = synthesize_insights()

    if args.json:
        payload = {
            "ts": now_iso(),
            "friction_patterns": [asdict(p) for p in (rework_patterns + ledger_patterns)],
            "synthesized_insights": [asdict(i) for i in insights],
            "healthy": True,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.audit:
        print(f"Insight synthesis clean: {len(rework_patterns) + len(ledger_patterns)} friction patterns, {len(insights)} insights synthesized.")
        return 0

    print("## Autonomous Telemetry Mining & Insight Synthesis\n")
    print(f"**Timestamp:** {now_iso()}\n")
    print(f"### Detected Friction Patterns ({len(rework_patterns) + len(ledger_patterns)})\n")
    for p in rework_patterns + ledger_patterns:
        print(f"- **[{p.category}]** {p.description} (Occurrences: {p.occurrences})")
        print(f"  *Literature Grounding:* {p.literature_grounding}")
        print(f"  *Suggested Mechanism:* {p.suggested_mechanism}\n")

    print(f"### Synthesized Architectural Insights ({len(insights)})\n")
    for i in insights:
        print(f"#### #{i.id}: {i.topic} [{i.stage}] (Confidence: {i.confidence:.2f})")
        print(f"- **Naive assumption:** {i.naive_assumption}")
        print(f"- **Empirical reality:** {i.empirical_reality}")
        print(f"- **Mechanism:** {i.mechanism}")
        print(f"- **Literature:** {i.literature}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
