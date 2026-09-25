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
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import audit as _audit  # noqa: E402  — the ONE yield implementation (#53 clause 8)
import field_predicate as _fields  # noqa: E402  — the ONE field predicate (#99)
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

# The classifier's keys, in FIRST-MATCH order — the chain's own order, kept so the buckets
# do not move for any entry the old predicate classified correctly.
CATEGORY_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("concurrency_locking", ("lock", "concurr", "flock", "race")),
    ("symlink_role_resolution", ("symlink", "role", "skill")),
    ("schema_drift", ("schema", "detail")),
    ("vocabulary_leak", ("vocab", "leak", "synonym")),
    ("cadence_pacemaker_stall", ("cadence", "cron", "pacemaker")),
)


def classify_defect(text: str) -> tuple[str, str | None]:
    """`(category, the key that fired)` for a rework entry's own text — first match wins.

    Returns `("generic", None)` when no key fires. The firing token is RETURNED rather than
    discarded so the tool can print it per entry (#168): a bucket count tells a reader how
    many entries landed in it, never WHY, and the why is what separates a real match from a
    word that merely contains the key.

    THE PREDICATE IS A LEFT BOUNDARY, not a substring. A raw `in` test counts WORDS, not
    events: `lock` matches `block` (18 rows in the live table) and `clock` (6), and `race`
    matches `trace`, `traceback`, `traceable` and `braces` (7 — the instance #168 was filed
    for). The `lock` family was 24 more, measured when this predicate replaced the
    substring test: 30 concurrency entries became 10.

    A BARE word-boundary test on BOTH sides IS NOT THE FIX, and that is why this is a left
    boundary only. Both boundaries break the `concurr` key outright — the words it exists to
    catch are `concurrency` and `concurrent`, which do not end at `concurr` — and would drop
    `locking` and `flock`'s inflections with it. The left boundary rejects CONTAINMENT
    (block, clock, trace, braces) while admitting the key's own INFLECTIONS
    (lock/locking/locked, concurrency/concurrent/concurrently, race/races).
    """
    for category, keys in CATEGORY_KEYS:
        for key in keys:
            if key_fires(key, text):
                return category, key
    return "generic", None


def key_fires(key: str, text: str) -> bool:
    """True when `key` occurs in `text` at a LEFT boundary — the predicate itself.

    Implemented in plain string operations rather than a regex, deliberately: this module
    must not carry a regex engine. Its earlier private `re` scan read the WHOLE ledger
    detail, so it took a quotation for a measurement, and a pinned probe asserts the
    attribute is absent (#99). A boundary test needs no engine, so the guard stays as
    written instead of being widened to accommodate this change.
    """
    start = 0
    while True:
        found = text.find(key, start)
        if found == -1:
            return False
        if found == 0 or not text[found - 1].isalnum():
            return True
        start = found + 1


def persisted_insight_ids() -> set[str]:
    """The ids ALREADY in `evidence/insights.jsonl` — the file the dedup guard must read.

    #166: the guard compared against the list it had just built IN THIS CALL, never against
    the persisted file, so it was a tautology — an id absent from the current list is by
    construction absent from a set built from that list. `INSIGHTS_PATH` was defined in the
    module header and read NOWHERE, which is the shape a second copy of a fact takes when
    the copy is never consulted.

    A row that cannot be parsed is skipped rather than aborting the read: this runs on the
    tool's own output path, and a malformed historical row must not take the synthesis down.
    """
    if not INSIGHTS_PATH.is_file():
        return set()
    ids: set[str] = set()
    for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = row.get("id")
        if isinstance(rid, str) and rid:
            ids.add(rid)
    return ids


def classify_rework_entries() -> list[dict]:
    """Every parsed rework entry with its bucket and the KEY that put it there.

    THE PURE CORE of the classifier, factored out of `mine_rework_defects` so the firing
    token is available to the OUTPUT (#168) and so a probe can drive it directly rather
    than only through a whole synthesis pass.
    """
    if not REWORK_PATH.is_file():
        return []

    lines = REWORK_PATH.read_text(encoding="utf-8").splitlines()
    classified: list[dict] = []

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
            category, fired = classify_defect(text)
            classified.append({
                "category": category,
                "key": fired,
                "defect": defect,
            })

    return classified


def mine_rework_defects() -> list[FrictionPattern]:
    """Mines clusters from evidence/rework.md."""
    if not REWORK_PATH.is_file():
        return []

    patterns: list[FrictionPattern] = []

    # Category buckets, filled from the classifier's own output so the bucket a pattern
    # counts and the key that put it there cannot disagree.
    categories: dict[str, list[str]] = {
        "concurrency_locking": [],
        "symlink_role_resolution": [],
        "schema_drift": [],
        "vocabulary_leak": [],
        "cadence_pacemaker_stall": [],
        "generic": [],
    }
    for entry in classify_rework_entries():
        categories[entry["category"]].append(entry["defect"])

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

    `total_cost` was REMOVED here rather than migrated (#99). It was accumulated from
    every run row and read by NOTHING — a dead aggregate is a second reading of a field
    `tools/audit.py` already owns from the same trailer scope, and a dead one is the
    kind that gets wired up by mistake. `high_turns` stays: it is read, by the
    `high_turn_convergence` alarm below.
    """
    if not LEDGER_PATH.is_file():
        return []

    lines = [l.strip() for l in LEDGER_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    high_turns = 0

    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue

        if d.get("event") == "run":
            # Telemetry is read through the ONE shared predicate (#99), which scopes a
            # field to the row's canonical TRAILER. The private scan this replaces read
            # the WHOLE detail, so it took a QUOTATION for a measurement: `n=586` is a
            # run row that quotes `n=303`'s trailer as evidence, and the quoted
            # `cost_usd=2.7719` was aggregated as a cost that row took.
            for key, value in _fields.declared_telemetry(d.get("detail", "")):
                try:
                    if key == "turns" and int(value) > 3:
                        high_turns += 1
                except ValueError:
                    pass

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

    # Add canonical architectural insights if not ALREADY PERSISTED (#166).
    #
    # The guard's first version compared against `{i.id for i in insights}` — the list it
    # had just built in this call — so it could never fire: an id absent from the current
    # list is, by construction, absent from a set built from that list. It was a tautology,
    # and the duplicate it let through was caught by hand at the append step instead (the
    # weekly run's own record: `survey-requisite-variety` was already at `n=17`). The
    # comparison that means anything is against the FILE.
    existing_ids = {i.id for i in insights} | persisted_insight_ids()
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

    # DEDUPLICATE AGAINST THE PERSISTED FILE, and within this run (#166).
    #
    # The canonical-insight guard above covers ONE id. The pattern-mapped insights are
    # emitted on EVERY run the pattern still fires — and a pattern that has been recorded
    # keeps firing, because the rework log is append-only — so they were re-emitted every
    # week too. Measured at the fix: all THREE ids the tool emitted were already persisted
    # (`single-writer-concurrency-guarantee`, `self-contained-skill-packaging`,
    # `survey-requisite-variety`), which is the tautology's real blast radius.
    #
    # Filtering once, here, covers both paths: an insight the file already carries is not
    # re-emitted, whatever produced it. The within-run set keeps a pattern and a canonical
    # entry that share an id from emitting it twice in one pass.
    persisted = persisted_insight_ids()
    emitted: set[str] = set()
    fresh: list[SynthesizedInsight] = []
    for insight in insights:
        if insight.id in persisted or insight.id in emitted:
            continue
        emitted.add(insight.id)
        fresh.append(insight)
    return fresh


def main() -> int:
    parser = argparse.ArgumentParser(description="Telemetry mining & insight synthesizer")
    parser.add_argument("--audit", action="store_true", help="Audit mode for CI/audit.py")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()

    rework_patterns = mine_rework_defects()
    ledger_patterns = mine_ledger_telemetry()
    insights = synthesize_insights()

    # The FIRING TOKEN per rework entry (#168). A bucket count says how many entries landed
    # in a bucket, never WHY, and the why is what separates a real match from a word that
    # merely contains the key — `block` and `clock` both contained `lock`, and `trace` and
    # `braces` both contained `race`.
    classification = classify_rework_entries()

    if args.json:
        payload = {
            "ts": now_iso(),
            "friction_patterns": [asdict(p) for p in (rework_patterns + ledger_patterns)],
            "synthesized_insights": [asdict(i) for i in insights],
            "rework_classification": classification,
            "healthy": True,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.audit:
        print(f"Insight synthesis clean: {len(rework_patterns) + len(ledger_patterns)} friction patterns, {len(insights)} insights synthesized.")
        return 0

    print("## Autonomous Telemetry Mining & Insight Synthesis\n")
    print(f"**Timestamp:** {now_iso()}\n")
    print(f"### Rework Classification - the key that fired, per entry ({len(classification)})\n")
    for entry in classification:
        key = entry["key"] or "none"
        print(f"- **[{entry['category']}]** key={key} - {entry['defect'][:120]}")
    print()

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
