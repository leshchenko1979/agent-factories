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
import ast
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

# ---- THE DECLARED CONSUMER MAP (#273, ruled at ledger n=1969) ---------------------------
#
# Three of the classifier's six categories reached no insight branch. The pattern->insight
# wiring was a chain of `if`/`elif` over TWO of them, so `schema_drift`, `vocabulary_leak`
# and `cadence_pacemaker_stall` were mined, counted and silently dropped. `schema_drift` is
# the dispositive case: `mine_rework_defects()` authors a full FrictionPattern for it --
# description, literature grounding and suggested mechanism included -- so a category whose
# mechanism was WRITTEN and never read is a stopped port, not a deliberate
# classification-only key. The same test catches two more the ruling did not have to name,
# because they are not classifier keys at all: the ledger-telemetry miner emits `yield_drop`
# and `high_turn_convergence`, and NEITHER reached a branch either.
#
# The wiring is a DECLARATION now, not a chain. Every category this tool can emit names, in
# ONE place, either the insight id it feeds or the explicit marker `classification-only`.
# `synthesize_insights()` reads the map, so a category cannot be added without someone
# deciding IN WRITING what consumes it -- and `consumer_map_problems()` is the invariant,
# read by the gate and printed by the run, so a forgotten declaration is a RED rather than a
# bucket that quietly reaches nothing (#143/#194: a bucket examined and dropped reads
# exactly like a clean run).
CLASSIFICATION_ONLY = "classification-only"

# The categories the LEDGER-TELEMETRY miner can emit. They come from the ledger's own
# telemetry, never from a rework entry's text, so they are NOT classifier keys and cannot
# appear in CATEGORY_KEYS -- but they reach the consumer map like any other pattern
# category, and an undeclared one is the same stopped port one level over.
LEDGER_TELEMETRY_CATEGORIES: tuple[str, ...] = ("yield_drop", "high_turn_convergence")

# The classifier's no-key-fired bucket. `classify_defect()` returns it and
# `classify_rework_entries()` reports it, but no miner builds a pattern from it -- it is the
# ABSENCE of a classification, so there is nothing for a consumer to read.
GENERIC_CATEGORY = "generic"

# The catalogue: insight id -> the insight it builds. Keyed by id and declared ONCE, so the
# map's entries can be CHECKED against it -- an id resolving to nothing is a dead pointer,
# which is the same defect one level up.
INSIGHT_CATALOGUE: dict[str, SynthesizedInsight] = {
    "single-writer-concurrency-guarantee": SynthesizedInsight(
        id="single-writer-concurrency-guarantee",
        topic="Single-Writer File Locking vs Conversational Coordination",
        stage="stage-2",
        naive_assumption="Autonomous agents collaborating in the same repo will naturally sequence their writes without file corruption.",
        empirical_reality="Multi-agent and background cron processes experience silent race conditions and split state without kernel-level locking.",
        mechanism="Enforce exclusive fcntl.flock on state files with automated single-writer concurrency unit tests.",
        literature="ACID Transactions & Mutex Locking (Lamport, 1978; Gray, 1981)",
        confidence=0.98,
    ),
    "self-contained-skill-packaging": SynthesizedInsight(
        id="self-contained-skill-packaging",
        topic="Skill & Role Card Symlink Resolution across Runtime Profiles",
        stage="stage-1",
        naive_assumption="Harness skill loaders will recursively find role files across separate project directories.",
        empirical_reality="Profile-scoped skill directories require explicit symlinks or bundled roles during factory bootstrap.",
        mechanism="Codify symlink verification into BOOTSTRAP.md and add deterministic audit gate in audit.py.",
        literature="Component-Based Architecture & Bounded Contexts (Evans, 2003)",
        confidence=0.95,
    ),
    "ledger-event-schema-contract": SynthesizedInsight(
        id="ledger-event-schema-contract",
        topic="Strict Event Contracts for a Row's Declared Fields",
        stage="stage-2",
        naive_assumption="Free prose in a row's detail cell carries the same information as a declared, machine-checkable shape.",
        empirical_reality="Unstructured details drift: a field appears in one lane's rows and not another's, and every reader that must parse the prose re-derives the schema for itself.",
        mechanism="Mechanical schema validators over the event detail, with a declared field set per event kind.",
        literature="Strict Contract Interfaces (Meyer, 1988; Schema-First Design)",
        confidence=0.93,
    ),
    "controlled-vocabulary-alignment": SynthesizedInsight(
        id="controlled-vocabulary-alignment",
        topic="Controlled Vocabulary & Synonym Leakage across Agent-authored Records",
        stage="stage-1",
        naive_assumption="Independent lanes describing the same mechanism will converge on the same term for it.",
        empirical_reality="They do not: one concept acquires several names, and a reader keyed on one of them reports the others as absent -- a predicate artefact, not a finding.",
        mechanism="One term table per concept, checked by a gate, so a synonym is a RED rather than a silent second name.",
        literature="Controlled Vocabularies & Ontology Alignment (Gruber, 1993; SKOS)",
        confidence=0.90,
    ),
    "cadence-watchdog-deadman": SynthesizedInsight(
        id="cadence-watchdog-deadman",
        topic="Cadence Watchdogs & Pacemaker Stall Detection",
        stage="stage-2",
        naive_assumption="A scheduled job that stops running announces itself, because its outputs simply stop appearing.",
        empirical_reality="An absent output is indistinguishable from a quiet period: a stalled pacemaker and a healthy one both write nothing, and the silence is only visible against a declared expected cadence.",
        mechanism="A declared expected cadence per job plus a watchdog that REDs on a missing run past its own interval.",
        literature="Watchdog Timers & Fail-Stop Systems (Kopetz, 1997)",
        confidence=0.92,
    ),
    "first-pass-yield-jidoka": SynthesizedInsight(
        id="first-pass-yield-jidoka",
        topic="First-Pass Yield as the Factory's Stop-the-Line Signal",
        stage="stage-2",
        naive_assumption="Rework is absorbed invisibly, so a falling first-pass yield is only a throughput question.",
        empirical_reality="A yield drop is the earliest mechanical evidence that the feedforward constraint is wrong, and it arrives before any individual failure is filed.",
        mechanism="Compute one yield from one implementation and stop the line on it, rather than inspecting defects one at a time.",
        literature="First-Time Yield & Jidoka (Ohno, 1988; Toyota Production System)",
        confidence=0.94,
    ),
    "inner-convergence-bounds": SynthesizedInsight(
        id="inner-convergence-bounds",
        topic="Inner Convergence Bounds for a Task Loop",
        stage="stage-3",
        naive_assumption="A task loop converges as soon as the work is correct, so turn count measures nothing.",
        empirical_reality="Runs needing more than three turns are reading a binary verdict and re-deriving the same failure, which is a feedback-bandwidth problem rather than a task-size one.",
        mechanism="Feed fine-grained error deltas from a multi-criteria judge instead of a binary pass/fail.",
        literature="Inner Convergence Bounds (Ralph Goal Loop; Requisite Variety)",
        confidence=0.88,
    ),
}

# THE MAP. One entry per category the tool can emit; the value is the insight id it feeds,
# or `classification-only` where the category is deliberately not converted -- and that
# marker is a DECISION a reader can audit, which a missing branch never was.
CONSUMER_MAP: dict[str, str] = {
    "concurrency_locking": "single-writer-concurrency-guarantee",
    "symlink_role_resolution": "self-contained-skill-packaging",
    "schema_drift": "ledger-event-schema-contract",
    "vocabulary_leak": "controlled-vocabulary-alignment",
    "cadence_pacemaker_stall": "cadence-watchdog-deadman",
    "yield_drop": "first-pass-yield-jidoka",
    "high_turn_convergence": "inner-convergence-bounds",
    GENERIC_CATEGORY: CLASSIFICATION_ONLY,
}


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


def consumer_insight(category: str) -> SynthesizedInsight | None:
    """The insight `category` feeds, or None where it is DECLARED classification-only.

    Raises KeyError, naming the missing declaration, for a category the map does not carry
    and for a declared id that resolves to no catalogue entry. A default of "skip" is
    exactly how three categories stayed invisible: an unread bucket and a bucket read and
    dropped produce the same silence, and neither leaves a trace in the output.
    """
    try:
        consumer = CONSUMER_MAP[category]
    except KeyError:
        raise KeyError(
            f"category {category!r} has NO declared consumer in CONSUMER_MAP (#273) -- every "
            f"category this tool can emit must name the insight it feeds or the explicit "
            f"marker {CLASSIFICATION_ONLY!r}"
        ) from None
    if consumer == CLASSIFICATION_ONLY:
        return None
    try:
        return INSIGHT_CATALOGUE[consumer]
    except KeyError:
        raise KeyError(
            f"category {category!r} declares consumer {consumer!r}, which is NOT in "
            f"INSIGHT_CATALOGUE -- a declared consumer must resolve to a real insight (#273)"
        ) from None


def emitted_category_literals(source: Path | None = None) -> set[str]:
    """Every string LITERAL this tool passes as `category=` when it builds a pattern.

    Parsed from the AST rather than scanned as text. The classifier's own categories reach
    the miner through a VARIABLE, so the literals are exactly the ones a hand-kept list
    forgets -- the ledger-telemetry miner's two -- and a text scan would additionally match
    this function's own source and this module's prose. Paired with CATEGORY_KEYS in
    `consumer_map_problems()`, the union is every category the tool can emit, so a NEW
    literal category in a miner is a RED until it is declared.
    """
    path = Path(source) if source else Path(__file__).resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "category":
                continue
            value = keyword.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.add(value.value)
    return found


def consumer_map_problems(source: Path | None = None) -> list[str]:
    """Every way the declared consumer map can be wrong, as PROBLEM strings (#273).

    ONE home for the invariant: the gate (`tests/test_synthesize_insights.py`) asserts this
    is empty, the probe beside it adds a consumer-less category and asserts it is NOT, and
    `main()` prints it -- so a category reaching no consumer is loud on all three surfaces.
    Empty list = the map is sound.
    """
    problems: list[str] = []
    emittable = (
        {category for category, _ in CATEGORY_KEYS}
        | set(LEDGER_TELEMETRY_CATEGORIES)
        | emitted_category_literals(source)
        | {GENERIC_CATEGORY}
    )
    for category in sorted(emittable):
        if category not in CONSUMER_MAP:
            problems.append(
                f"category {category!r} can be emitted and declares NO consumer in "
                f"CONSUMER_MAP -- name the insight it feeds or the explicit marker "
                f"{CLASSIFICATION_ONLY!r} (#273)"
            )
    for category, consumer in CONSUMER_MAP.items():
        if consumer == CLASSIFICATION_ONLY:
            continue
        if consumer not in INSIGHT_CATALOGUE:
            problems.append(
                f"category {category!r} declares consumer {consumer!r}, which is NOT in "
                f"INSIGHT_CATALOGUE -- a declared consumer must resolve to a real insight "
                f"(#273)"
            )
    return problems


def consumer_population(patterns: list[FrictionPattern]) -> list[dict]:
    """The per-category population this run EXAMINED, each with its declared consumer.

    #143/#194 class: a bucket examined and silently dropped reads exactly like a clean run.
    Every category the run saw is listed with its count and its consumer, in declaration
    order, and a category the run saw that the map does not name is printed as UNDECLARED
    rather than omitted -- the print is the population, not a summary of it.
    """
    counts: dict[str, int] = {}
    occurrences: dict[str, int] = {}
    for pattern in patterns:
        counts[pattern.category] = counts.get(pattern.category, 0) + 1
        occurrences[pattern.category] = occurrences.get(pattern.category, 0) + pattern.occurrences
    rows = [
        {
            "category": category,
            "patterns": counts.get(category, 0),
            "occurrences": occurrences.get(category, 0),
            "consumer": consumer,
        }
        for category, consumer in CONSUMER_MAP.items()
    ]
    for category in sorted(counts):
        if category not in CONSUMER_MAP:
            rows.append(
                {
                    "category": category,
                    "patterns": counts[category],
                    "occurrences": occurrences[category],
                    "consumer": "UNDECLARED",
                }
            )
    return rows


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
    """Every parsed rework entry with its bucket, the KEY that put it there, and the text.

    THE PURE CORE of the classifier, factored out of `mine_rework_defects` so the firing
    token is available to the OUTPUT (#168) and so a probe can drive it directly rather
    than only through a whole synthesis pass.

    THE MINED POPULATION, chosen deliberately and recorded per entry (#194). The text the
    classifier reads is the **Defect, Root cause and Prevented-by** cells concatenated —
    cells 3, 4 and 7 of the row — because a defect's CLASS is carried as much by what
    caused it and by what now prevents it as by the sentence describing the symptom. What
    was not defensible was mining three cells and RECORDING one: the entry kept only the
    defect cell, so a reader could see the class and not the words that produced it, and a
    probe validating the key against the defect cell alone red on entries whose key fired
    in a cell the entry never carried (measured on the live table, 32 of 130 entries have
    a key that fires ONLY outside the defect cell). The entry therefore records `mined`,
    and the key is validated against THAT.
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
            defect, cause, prevented_by = cols[2], cols[3], cols[5]
            text = f"{defect} {cause} {prevented_by}".lower()
            category, fired = classify_defect(text)
            classified.append({
                "category": category,
                "key": fired,
                "defect": defect,
                # The text the classification actually read, recorded so the class is
                # auditable from the row rather than only from the code that made it.
                "mined": text,
            })

    return classified


def mine_rework_defects() -> list[FrictionPattern]:
    """Mines clusters from evidence/rework.md."""
    if not REWORK_PATH.is_file():
        return []

    patterns: list[FrictionPattern] = []

    # Category buckets, filled from the classifier's own output so the bucket a pattern
    # counts and the key that put it there cannot disagree.
    #
    # DERIVED from the key list, never hand-kept (#273). A second hard-coded list is the
    # same defect one level down: it drifts from `CATEGORY_KEYS`, and a new key then dies
    # at the dict lookup with a bare `KeyError('new_bucket')` -- an error that says nothing
    # about the real question, which is whether a pattern is authored for it.
    categories: dict[str, list[str]] = {
        category: [] for category, _ in CATEGORY_KEYS
    }
    categories[GENERIC_CATEGORY] = []
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
            elif cat == "vocabulary_leak":
                patterns.append(FrictionPattern(
                    source="evidence/rework.md",
                    category=cat,
                    description=f"Terms leaking between role vocabularies, or off-register synonyms ({len(items)} defects).",
                    occurrences=len(items),
                    literature_grounding="Controlled Vocabulary & Ontology Discipline (ISO 25964; Domain-Driven Design ubiquitous language)",
                    suggested_mechanism="A declared term register with a lint leg that fails on an undeclared synonym (test_vocabulary_register.py)."
                ))
            elif cat == "cadence_pacemaker_stall":
                patterns.append(FrictionPattern(
                    source="evidence/rework.md",
                    category=cat,
                    description=f"Pacemakers or crons that stopped firing without anyone noticing ({len(items)} defects).",
                    occurrences=len(items),
                    literature_grounding="Deadman Switch & Watchdog Timers (heartbeat liveness detection)",
                    suggested_mechanism="A last-fired timestamp per cron with a staleness leg that reports a silent cadence (test_cadence_liveness.py)."
                ))
            elif CONSUMER_MAP.get(cat) == CLASSIFICATION_ONLY:
                # Declared classification-only: counted, and deliberately not consumed. The
                # declaration IS the trace, so this is not a stopped port (#273).
                continue
            else:
                # A category that fires often enough to be a pattern but has no authored
                # description here is a STOPPED PORT, not a bucket to skip: `schema_drift`
                # was counted, was in this dict, and reached no branch for exactly this
                # reason (#273). Say so loudly instead of returning a shorter list.
                raise KeyError(
                    f"category {cat!r} cleared the {len(items)}-defect threshold in "
                    f"mine_rework_defects() but NO FrictionPattern is authored for it -- "
                    f"author one, or the cluster is counted and then silently dropped (#273)"
                )

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

    # Map patterns to their DECLARED consumer (#273). The map is READ, never re-derived as a
    # chain of `if`/`elif`: the chain is what silently dropped three of six categories, and
    # `consumer_insight()` REFUSES an undeclared category rather than skipping it.
    for p in all_patterns:
        insight = consumer_insight(p.category)
        if insight is not None:
            insights.append(insight)

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

    # THE POPULATION AND THE INVARIANT (#273). Both are computed on EVERY run, so a bucket
    # that reached no consumer and a category declared with no consumer are visible whether
    # or not anyone remembers to look -- the class the ruling names (#143/#194).
    population = consumer_population(rework_patterns + ledger_patterns)
    map_problems = consumer_map_problems()
    dropped = [row for row in population if row["consumer"] == CLASSIFICATION_ONLY]

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
            # The declared consumer map, its per-category population, and the invariant's
            # own verdict (#273) -- a JSON reader must be able to tell a category that fed
            # nothing BY DECLARATION from one that fed nothing by omission.
            "consumer_map": population,
            "consumer_map_problems": map_problems,
            "classification_only": {"declared": len(dropped), "of": len(population)},
            "healthy": not map_problems,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.audit:
        print(
            f"Insight synthesis clean: {len(rework_patterns) + len(ledger_patterns)} friction "
            f"patterns, {len(insights)} insights synthesized, "
            f"classification-only: {len(dropped)} of {len(population)} declared categor(ies)."
        )
        for problem in map_problems:
            print(f"PROBLEM: {problem}")
        return 0

    print("## Autonomous Telemetry Mining & Insight Synthesis\n")
    print(f"**Timestamp:** {now_iso()}\n")
    print(f"### Rework Classification - the key that fired, per entry ({len(classification)})\n")
    print(
        "Mined population: the Defect, Root cause and Prevented-by cells concatenated, "
        "because cause and prevention carry class information; each entry records that "
        "text, so the class is auditable from the row.\n"
    )
    for entry in classification:
        key = entry["key"] or "none"
        print(f"- **[{entry['category']}]** key={key} - {entry['defect'][:120]}")
        if entry["key"] and not key_fires(entry["key"], entry["defect"].lower()):
            print(
                "    the key fired OUTSIDE the defect cell, in the mined text: "
                f"{entry['mined'][:160]}"
            )
    print()

    print(f"### Detected Friction Patterns ({len(rework_patterns) + len(ledger_patterns)})\n")
    for p in rework_patterns + ledger_patterns:
        print(f"- **[{p.category}]** {p.description} (Occurrences: {p.occurrences})")
        print(f"  *Literature Grounding:* {p.literature_grounding}")
        print(f"  *Suggested Mechanism:* {p.suggested_mechanism}\n")

    print("### Declared Consumer Map - what each category feeds (#273)\n")
    print(
        "Every category this run can emit declares, in ONE place, the insight it feeds or "
        "the explicit marker `classification-only`. A bucket examined and dropped reads "
        "exactly like a clean run, so the map is PRINTED with its own counts.\n"
    )
    for row in population:
        print(
            f"- **{row['category']}**: {row['patterns']} pattern(s), "
            f"{row['occurrences']} occurrence(s) -> {row['consumer']}"
        )
    print(
        f"\nclassification-only: {len(dropped)} of {len(population)} entries "
        f"({', '.join(row['category'] for row in dropped) or 'none'})\n"
    )
    for problem in map_problems:
        print(f"**PROBLEM:** {problem}\n")

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
