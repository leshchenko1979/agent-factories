"""Multi-Lens Review Engine (Review Rotation / P32).

Manages periodic quality reviews of factory laws, tools, and artifacts.
Enforces:
  1. Complete census: all catalog lenses must run or be explicitly waived.
  2. State durability and STEP-0 RECOVERY: state.json carries the cycle
     lifecycle, an explicit terminal state and both durations.  That file IS
     the step-0 recovery point — after a compaction or restart, RUN
     `step0 <cycle>` before re-querying input, re-briefing reviewers or
     re-drafting a plan.  It is a COMMAND rather than this paragraph because a
     compacted session cannot execute prose, and it reads state.json and
     nothing else, so it answers the same on a resumed run as on the first.
     `step0 --record` appends the reading to `step0_log`, which is what makes
     the recovery durable EVIDENCE instead of an assertion.
  3. Receipt verification: reports verified with sha256 checksums, and a report
     with no index line is UNRECEIPTED — a named state, never a silent pass.
  4. Adversarial sub-agent dispatch: generates isolated, adversarial auditor
     prompts.  Lenses are executed by READ-ONLY SUB-AGENTS, never by the
     authoring session inline (docs/review-lenses.md, Adversarial Isolation
     Requirement).
  5. An OBSERVABLE cadence: `cadence` derives the boundary stamp from the
     ledger's own ANCHORED notes, so a member's cadence state is re-derivable
     by anyone holding the ledger instead of asserted in prose.
  6. A DECLARED intake: `intake` reads the cycle's input channels and reports a
     NAMED state.  Nothing declared, nothing submitted and a malformed
     submission are three different states, and none of them is a pass.
  7. NO SILENT LIVE READ: a cycle is FROZEN once its lifecycle is terminal.
     Closing snapshots the declared channels (`inputs_snapshot`), and a later
     `intake` or `cadence --write` against a frozen cycle is REFUSED, because
     the bytes on disk now answer a different question than the one the cycle
     closed on.  `--live` is the explicit way to say the reader means today's
     bytes, and the read then says so.
  8. A DECLARED extension surface: the core catalogue IS the instrument's shape
     and is centralised -- a member cannot fork it.  A member's OWN lenses are
     DECLARED in `docs/review-lenses.json` (shipped as an empty
     `docs/review-lenses.example.json`), which ONE reader folds into the
     catalogue.  A declaration ADDS; it never removes or redefines a core lens.

Usage:
  python3 tools/review.py init <cycle_id>
  python3 tools/review.py brief <lens> [--json]
  python3 tools/review.py record <cycle_id> <lens> <report_path_or_text>
  python3 tools/review.py waive <cycle_id> <lens> --reason "..." [--by WHO]
  python3 tools/review.py status <cycle_id>
  python3 tools/review.py lenses [--json]
  python3 tools/review.py verify <cycle_id>
  python3 tools/review.py compile <cycle_id>
  python3 tools/review.py close <cycle_id> [--status COMPLETED|ABANDONED] [--stamp --ledger F]
  python3 tools/review.py cadence --ledger <ledger.jsonl> [--every N] [--write <cycle_id>] [--json]
  python3 tools/review.py intake <cycle_id> [--record] [--live]
  python3 tools/review.py step0 <cycle_id> [--record]
  python3 tools/review.py schema
  python3 tools/review.py migrate <cycle_id> [--dry-run]
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


# ---------------------------------------------------------------------------
# THE PROMOTED STATE CONTRACT — schema v1
# ---------------------------------------------------------------------------
# The schema is AUTHORED HERE and emitted to the shipped artifact by
# `review.py schema`.  The pair `docs/review-cycle.schema.json` /
# `TEMPLATE/docs/review-cycle.schema.json` is generated from that command, and
# `tests/test_review.py` asserts the shipped pair is byte-identical to what it
# prints — one authoring home, no drift.  (Same shape as
# `tools/kit_manifest.py`, which generates `registry/kit.json`.)
#
# WHY A CLOSED SCHEMA AND NOT PROSE.  Measured over the donor's own cycle dirs
# (predicate: each dir's state.json; scope: the donor state root; instant
# 2026-09-27): the donor's "FROZEN SCHEMA — these five field names are law" is
# honoured by 4 of 17 state files; `status` carries SIX distinct values where
# the law says exactly two; `cycle_id` is absent in 1 of 17; and the key union
# is 35 keys against the 10 the law names.  A declared schema nothing reads is
# a comment.  This one is emitted, shipped and asserted.

SCHEMA_VERSION = 1

# Terminal ENUM.  `COMPLETED` is the donor's DOMINANT terminal token, not its
# only one, and the distinction is measured rather than assumed: over the
# donor's own cycle state files (predicate: each dir's state.json; scope: the
# donor state root, 17 files; instant 2026-09-27) cycle `status` carries SIX
# distinct values — COMPLETED 9, IN_PROGRESS 4, reports_persisted 1,
# intake_complete 1, VALIDATED 1, COMPLETE 1 — and lens entries carry FOUR:
# COMPLETED 66, COMPLETE 11, PENDING 7, PERSISTED 4.  So the enum keeps the
# dominant token and `migrate` MAPS the plain synonym `COMPLETE`; anything
# outside both is REPORTED as UNMAPPED rather than carried in as if valid.
# `ABANDONED` is ADDED, and the reason is measured rather than speculative:
# four donor cycles sit at IN_PROGRESS (20260915-c18, 20260916-c20,
# 20260919-c21 and the live 20260927-c25), three of them days old and dead in
# fact — an abandoned cycle is otherwise indistinguishable from a live one,
# the same defect the donor fixed for `ended_at`.
LIFECYCLE_STATES = ["IN_PROGRESS", "COMPLETED", "ABANDONED"]
LENS_STATES = ["PENDING", "COMPLETED", "WAIVED"]

# THE DECLARED EXTENSION SURFACE (frame template-instruments.md §6.5; the live
# specimen is ledger's `docs/ledger-refs-kinds.json`).  The core catalogue above
# is the instrument's SHAPE and is CENTRALISED (template-instruments.md §6.4): a member cannot fork
# it.  What a member MAY do is DECLARE its own lenses -- subject matter the core
# catalogue carries no lens for -- in `docs/review-lenses.json`, which ships as an
# EMPTY `docs/review-lenses.example.json` and which the manifest does NOT track.
# ONE reader (`known_lenses` / `lens_metadata`) serves every path, so the writer
# and the verifier cannot disagree.  A declaration ADDS; it never removes or
# redefines a core lens -- a declared id that collides with a core letter is
# dropped, so the core entry keeps the law that letter carries.  The path is
# relocatable for the same reason every declared surface in this fleet is: a
# member whose layout differs points the instrument at its own declaration
# without editing the instrument, and the same seam makes a fixture lawful.
REVIEW_LENSES_FILE = Path(
    os.environ.get("OC_REVIEW_LENSES_PATH", REPO_ROOT / "docs" / "review-lenses.json")
)

def _read_declared_lenses() -> list[dict]:
    """The factory's declared lens additions.  Absent or unreadable is NOT an error.

    The core catalogue stands alone without it, which is what lets the field ship
    before any factory has declared a lens.
    """
    try:
        data = json.loads(REVIEW_LENSES_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return []
    out: list[dict] = []
    for item in (data.get("lenses") or []) if isinstance(data, dict) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
            out.append(item)
    return out

def declared_lenses() -> list[dict]:
    """Declared lenses whose id does NOT shadow a core lens -- a declaration ADDS.

    A colliding id is dropped here rather than merged, so a factory cannot shadow
    a core letter and escape the law that letter carries.
    """
    return [
        d for d in _read_declared_lenses()
        if d["id"].strip().upper() not in CATALOG_LENSES
    ]

def known_lenses() -> list[str]:
    """The core catalogue PLUS this factory's declared additions -- ONE reader.

    Every path that enumerates lenses (init, step0, status, verify, close, compile,
    migrate, census_gaps) reads THIS, so a declared lens is materialised, counted and
    verified exactly as a core lens is, and the write path and the gate cannot disagree.
    """
    return CATALOG_LENSES + [d["id"].strip().upper() for d in declared_lenses()]

def lens_metadata(lens: str) -> dict | None:
    """The metadata for a lens -- core first, then the member's declaration.

    Core takes precedence, so a declared id that collides with a core letter never
    redefines it.  `None` is the single refusal predicate for brief/record/waive.
    """
    if lens in LENS_METADATA:
        return LENS_METADATA[lens]
    for d in declared_lenses():
        if d["id"].strip().upper() == lens:
            return {
                "name": str(d.get("name") or d["id"].strip().upper()),
                "family": str(d.get("family") or "member-declared"),
                "scope": str(d.get("scope") or ""),
                "instructions": str(d.get("instructions") or ""),
            }
    return None

# The donor's terminal SYNONYM, and only the synonym.  `PERSISTED` is
# deliberately NOT mapped: it says a report was written, not that a lens
# reached a verdict, and collapsing it to COMPLETED would over-claim evidence
# the donor did not assert.  An unmapped value is named by the caller.
TERMINAL_SYNONYMS = {"COMPLETE": "COMPLETED"}

# A LENS ENTRY drifts by KEY as well as by VALUE, and the rename is measured rather than
# assumed: over the donor's 88 lens entries the shapes are `(report_path, status, verdict)`
# 73, `(path, status)` 11, `(findings_count, report_path, status)` 4 — so eleven entries name
# the report with `path` where the other seventy-three use `report_path`.  A null-check on
# `report_path` does NOT survive that: the render prints None for a lens that has a report,
# which is a wrong value rather than a crash, and the migration's own key filter DROPPED it,
# because `path` is not a key of the template.
LENS_KEY_SYNONYMS = {"path": "report_path"}

# The cadence boundary is the NEWEST row whose text ANCHORS on this pattern —
# the last cycle-close stamp.  ANCHORED, never a substring: a loose search
# harvests an END from a row whose whole point is that none was written — the
# donor's `WITHHELD:` convention exists for exactly that row, and a WITHHELD
# row begins with the literal token, so it can never match an anchored pattern.
CADENCE_PATTERN = r"^v[0-9]+\.[0-9]+\.[0-9]+ ACCEPTED"
CADENCE_DEFAULT_EVERY = 5

# ... and the COUNT is a SECOND predicate, not the same one.  Read from the
# donor's own implementation rather than inferred from its prose: in
# the donor's `cmd_cadence` the boundary is the newest ANCHORED row, while
# the bumps are counted over rows of a DIFFERENT kind — `kind == "skill-bump"`.
# Re-measured against the donor's live ledger (predicate: rows per kind; scope:
# workers-ledger.json, 11 562 rows; instant 2026-09-27T15:2xZ): boundary
# n=12391 (`v0.4.266 ACCEPTED — Duty-6 cycle 20260927-c25 closed`), and
# exactly 2 `skill-bump` rows after it -> 2/5 WAIT.
#
# Counting anchored rows instead — the obvious reading, and the one this file
# first shipped — gives the SAME ledger a different answer, because the close
# stamp is itself anchored and would be counted as a bump.  The two predicates
# are one row apart here and diverge without bound over time.
CADENCE_BUMP_EVENT = "skill-bump"

STATE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "review-cycle.schema.json",
    "title": "Review Rotation - cycle state",
    "description": (
        "One review cycle's state, at reviews/<cycle-id>/state.json in the "
        "adopting tree. Emitted by `python3 tools/review.py schema`."
    ),
    "schema_version": SCHEMA_VERSION,
    "type": "object",
    "required": [
        "schema_version",
        "cycle_id",
        "status",
        "started_at",
        "ended_at",
        "duration_review_min",
        "duration_cycle_min",
        "cadence",
        "corpus",
        "lenses",
        "waivers",
        "proposals",
        "codification_plan",
        "frozen_at",
        "inputs_snapshot",
        "step0_log",
        "updated_at",
    ],
    "properties": {
        "schema_version": {
            "type": "integer",
            "const": SCHEMA_VERSION,
            "description": "The schema's own version. A reader REFUSES an unknown value rather than guessing.",
        },
        "cycle_id": {
            "type": "string",
            "minLength": 1,
            "description": "Minted ONCE at init and written to BOTH stores: state.json and the ledger row that opens the cycle.",
        },
        "status": {
            "type": "string",
            "enum": LIFECYCLE_STATES,
            "description": "A CLOSED enum. Free text here is the measured defect: six distinct values against a two-value law.",
        },
        "started_at": {"type": "string", "format": "date-time"},
        "ended_at": {
            "type": ["string", "null"],
            "format": "date-time",
            "description": "Null while IN_PROGRESS, and NEVER absent: absence and null are different claims. updated_at is not a substitute.",
        },
        "duration_review_min": {
            "type": ["number", "null"],
            "minimum": 0,
            "description": "Review start to last report persisted.",
        },
        "duration_cycle_min": {
            "type": ["number", "null"],
            "minimum": 0,
            "description": "Cycle start to cadence close stamp. A SECOND number; the two are never conflated.",
        },
        "cadence": {
            "type": "object",
            "description": "The cadence boundary as an OBSERVABLE artifact, never prose. Computed by `review.py cadence`.",
            "required": ["trigger", "boundary", "fires", "evaluated_at"],
            "properties": {
                "trigger": {
                    "type": "object",
                    "required": ["kind"],
                    "properties": {
                        "kind": {"type": "string", "enum": ["version_bumps", "manual", "interval"]},
                        "every": {"type": ["integer", "null"], "minimum": 1},
                        "note": {"type": "string"},
                        "counts": {"type": "string", "description": "The row kind counted as a version bump since the boundary. The count and the boundary are TWO predicates: the close stamp is itself anchored, so counting anchored rows would count it as a bump."},
                    },
                },
                "boundary": {
                    "type": "object",
                    "required": ["ref", "at", "pattern", "accepted_since"],
                    "description": "The newest row matching the ANCHORED pattern — the cycle-close stamp — and how many BUMP rows landed after it. TWO predicates, never one: counting anchored rows would count the close stamp itself as a bump.",
                    "properties": {
                        "ref": {"type": ["string", "null"]},
                        "at": {"type": ["string", "null"], "format": "date-time"},
                        "pattern": {"type": "string"},
                        "accepted_since": {"type": "integer", "minimum": 0},
                    },
                },
                "fires": {"type": "boolean"},
                "evaluated_at": {"type": "string", "format": "date-time"},
            },
        },
        "corpus": {
            "type": "object",
            "description": "The FROZEN inputs the cycle reviewed. A report is valid only for this hash.",
            "required": ["hash", "pack", "pack_status"],
            "properties": {
                "hash": {"type": ["string", "null"]},
                "pack": {
                    "type": ["string", "null"],
                    "description": "Optional mechanical corpus pack. NOT promoted: it is a project-dir trial called by absolute path.",
                },
                "pack_status": {
                    "type": "string",
                    "enum": ["present", "absent", "failed"],
                    "description": "A missing or failing pack is REPORTED, never silently skipped: the record says which.",
                },
            },
        },
        "lenses": {
            "type": "object",
            "description": "One entry per catalog lens, INCLUDING lenses that never ran. A sparse map is normalized on read, because coverage is complete-or-waived and an absent lens is PENDING, not absent.",
            "additionalProperties": {
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["PENDING", "COMPLETED", "WAIVED", "HOLLOW", "FAILED"],
                    },
                    "report_path": {"type": ["string", "null"]},
                    "sha256": {"type": ["string", "null"]},
                    "verdict": {"type": ["string", "null"]},
                    "receipt": {
                        "type": ["string", "null"],
                        "enum": ["verified", "UNRECEIPTED", None],
                        "description": "A report with no index line is UNRECEIPTED, which is a distinct state from missing.",
                    },
                    "fallback": {
                        "type": ["string", "null"],
                        "enum": ["inline", None],
                        "description": "Set when the inline fallback ran after a second hollow report. The fallback MUST be flagged in the record.",
                    },
                    "recorded_at": {"type": ["string", "null"], "format": "date-time"},
                    "reason": {"type": ["string", "null"]},
                },
            },
        },
        "waivers": {
            "type": "array",
            "description": "The waiver LOG, one record per waived lens. A waiver with no reason is refused. This array is the SINGLE home; the donor's separate waivers.log is not carried.",
            "items": {
                "type": "object",
                "required": ["lens", "reason", "waived_at"],
                "properties": {
                    "lens": {"type": "string"},
                    "reason": {"type": "string", "minLength": 1},
                    "by": {"type": ["string", "null"]},
                    "waived_at": {"type": "string", "format": "date-time"},
                },
            },
        },
        "proposals": {
            "type": "array",
            "description": "Intake receipts: what the cycle took in and from which channel. The proposals/ DIRECTORY is the member-owned data surface; this array is the instrument's receipt index.",
            "items": {
                "type": "object",
                "required": ["id", "source", "recorded_at"],
                "properties": {
                    "id": {"type": "string"},
                    "source": {"type": "string", "enum": ["dir", "ledger", "declared"]},
                    "path": {"type": ["string", "null"]},
                    "recorded_at": {"type": "string", "format": "date-time"},
                    "op": {"type": "string", "enum": ["ADD", "CHANGE"],
                           "description": "The proposal's operation, from the strict intake format."},
                    "target": {"type": "string",
                               "description": "The file+section the proposal names, from the strict intake format."},
                    "dated": {"type": "boolean",
                              "description": "Whether the evidence carried a date. An undated proposal is RECEIVED and WARNED, never silently accepted as evidenced."},
                },
            },
        },
        "codification_plan": {
            "type": "array",
            "description": "Accepted findings and the home each lands in. An accepted finding with no landed home is a cycle-completion FAILURE, never a scheduling choice.",
            "items": {
                "type": "object",
                "required": ["finding", "disposition"],
                "properties": {
                    "finding": {"type": "string"},
                    "disposition": {"type": "string", "enum": ["landed", "routed", "rejected"]},
                    "home": {"type": ["string", "null"]},
                    "reason": {"type": ["string", "null"]},
                },
            },
        },
        "frozen_at": {
            "type": ["string", "null"],
            "description": "Set when the cycle closes. A FROZEN cycle's inputs are historical: a live channel read against it is REFUSED, because the bytes on disk now answer a different question than the one the cycle closed on.",
        },
        "inputs_snapshot": {
            "type": ["object", "null"],
            "description": "WHAT the cycle read and WHEN, one digest per declared channel, taken at freeze time. A resumed reader compares this against today's channel to tell the cycle's own bytes from the current ones. Digests are computed in constant memory: the ledger may be large and a whole-file read is banned on this box.",
            "properties": {
                "taken_at": {"type": "string", "format": "date-time"},
                "channels": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["kind", "ref", "exists"],
                        "properties": {
                            "kind": {"type": "string", "enum": ["dir", "ledger"]},
                            "ref": {"type": "string"},
                            "exists": {"type": "boolean"},
                            "sha256": {"type": ["string", "null"]},
                            "bytes": {"type": ["integer", "null"]},
                            "files": {"type": ["integer", "null"]},
                        },
                    },
                },
            },
        },
        "step0_log": {
            "type": "array",
            "description": "One entry per `step0 --record`: where the cycle stood, read from state ALONE. This is the durable half of the step-0 recovery claim — a resumed session can show where it recovered from rather than assert it.",
            "items": {
                "type": "object",
                "required": ["at", "status", "frozen", "completed", "waived", "pending", "next_action"],
                "properties": {
                    "at": {"type": "string", "format": "date-time"},
                    "status": {"type": "string"},
                    "frozen": {"type": "boolean"},
                    "completed": {"type": "integer"},
                    "waived": {"type": "integer"},
                    "pending": {"type": "integer"},
                    "pending_lenses": {"type": "array", "items": {"type": "string"}},
                    "next_action": {"type": "string"},
                },
            },
        },
        "updated_at": {
            "type": "string",
            "format": "date-time",
            "description": "Written by the engine on every save. Not a claim that the cycle is current.",
        },
    },
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_state(cycle_id: str) -> dict[str, Any]:
    """The v1 shape, complete. Every required key is present from init."""
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "cycle_id": cycle_id,
        "status": "IN_PROGRESS",
        "started_at": now,
        "ended_at": None,
        "duration_review_min": None,
        "duration_cycle_min": None,
        "cadence": {
            "trigger": {"kind": "version_bumps", "every": CADENCE_DEFAULT_EVERY, "note": ""},
            "boundary": {"ref": None, "at": None, "pattern": CADENCE_PATTERN, "accepted_since": 0},
            "fires": False,
            "evaluated_at": now,
        },
        "corpus": {"hash": None, "pack": None, "pack_status": "absent"},
        "lenses": {
            lens: {"status": "PENDING", "report_path": None, "sha256": None, "verdict": None,
                   "receipt": None, "fallback": None, "recorded_at": None, "reason": None}
            for lens in known_lenses()
        },
        "waivers": [],
        "proposals": [],
        "codification_plan": [],
        # A cycle is FROZEN once its lifecycle is terminal: its inputs were read
        # at a known instant and a later read of a LIVE mutable channel (a
        # ledger, a proposals dir) would answer a different question than the
        # one the cycle closed on. `inputs_snapshot` records the digests taken
        # at freeze time, so a resumed reader can say WHAT it read and WHEN
        # instead of silently re-reading whatever is on disk now.
        "frozen_at": None,
        "inputs_snapshot": None,
        # The step-0 recovery log: each `step0 --record` appends where the cycle
        # stood at that instant. It is EVIDENCE rather than a convenience —
        # a resumed session can prove it recovered from state alone, instead of
        # asserting it did.
        "step0_log": [],
        "updated_at": now,
    }


def normalize_state(state: dict[str, Any], cycle_id: str) -> dict[str, Any]:
    """Read ANY state file into the v1 shape.

    This is the frozen legacy reader.  It NEVER rewrites history on disk: a
    donor cycle is migrated by a caller that decides to save, and a cycle read
    only for its status is left byte-for-byte alone.

    Three donor shapes are reconciled here, all measured on the donor's own
    tree: a sparse `lenses` map (12 of 17 files carry the key at all, and the
    live cycle carries `{}`); `waivers` as a dict rather than a log; and free
    text in `status`.
    """
    if not state:
        return {}
    out = _empty_state(state.get("cycle_id") or cycle_id)
    for key, value in state.items():
        if key in ("schema_version", "lenses", "waivers", "cadence", "corpus"):
            continue
        out[key] = value

    # status: the donor's terminal SYNONYM is mapped, so a cycle it closed as
    # `COMPLETE` reads as closed here instead of as an unknown state.  Only the
    # named synonym is mapped; anything else is carried in as-is and REPORTED by
    # `migrate` as unmapped, because inventing a mapping for a value whose
    # meaning was never measured is how a schema stops describing its data.
    if out.get("status") in TERMINAL_SYNONYMS:
        out["status"] = TERMINAL_SYNONYMS[out["status"]]

    # lenses: normalize each entry, and materialize every KNOWN lens.
    raw_lenses = state.get("lenses") or {}
    if isinstance(raw_lenses, dict):
        for lens in known_lenses():
            entry = dict(out["lenses"][lens])
            incoming = raw_lenses.get(lens)
            if isinstance(incoming, dict):
                # The KEY RENAME is applied BEFORE the filter, because the filter keeps only
                # keys the template has and `path` is not one of them — so an un-renamed entry
                # loses its report path silently, which is how eleven donor lenses arrived
                # with no report at all.
                incoming = {LENS_KEY_SYNONYMS.get(k, k): v for k, v in incoming.items()}
                entry.update({k: v for k, v in incoming.items() if k in entry})
                if entry.get("status") is None:
                    entry["status"] = "PENDING"
                elif entry["status"] in TERMINAL_SYNONYMS:
                    entry["status"] = TERMINAL_SYNONYMS[entry["status"]]
            out["lenses"][lens] = entry

    # waivers: a DICT (engine shape) becomes a LOG (v1 shape).
    raw_waivers = state.get("waivers")
    if isinstance(raw_waivers, dict):
        for lens, rec in raw_waivers.items():
            if isinstance(rec, dict):
                out["waivers"].append({
                    "lens": lens,
                    "reason": rec.get("reason", ""),
                    "by": rec.get("by"),
                    "waived_at": rec.get("waived_at", out["started_at"]),
                })
    elif isinstance(raw_waivers, list):
        out["waivers"] = raw_waivers

    # cadence: prose (donor) is NOT parsed into fields; it is preserved as the
    # trigger note and the boundary is left unevaluated until `cadence` runs.
    raw_cadence = state.get("cadence")
    if isinstance(raw_cadence, dict):
        out["cadence"].update(raw_cadence)
    elif isinstance(raw_cadence, str) and raw_cadence:
        out["cadence"]["trigger"]["note"] = raw_cadence

    # corpus: the donor's flat `corpus_hash` folds into the corpus object.
    if state.get("corpus_hash") and not isinstance(state.get("corpus"), dict):
        out["corpus"]["hash"] = state["corpus_hash"]
        out["corpus"]["pack_status"] = "present" if state.get("corpus_hash") else "absent"
        out.pop("corpus_hash", None)
    return out


def _ledger_text(row: dict[str, Any]) -> str:
    for key in ("note", "detail", "text", "message", "subject", "what"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _row_kind(row: dict[str, Any]) -> str:
    """The row's kind, under either ledger vocabulary.

    The template's ledger column is `event` (`n/ts/event/actor/subject/detail`);
    the donor's is `kind`.  ONE predicate serves both, so a cadence read does
    not depend on which vocabulary an adopter's ledger happens to carry.
    """
    for key in ("event", "kind"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _row_ts(row: dict[str, Any]) -> Any:
    """The row's timestamp, under either ledger vocabulary.

    The template's column is `ts`; the donor's is `t`.  Reading only one makes
    the other's boundary `at` silently None — a field loss that looks like an
    absent timestamp rather than a vocabulary mismatch.
    """
    for key in ("ts", "t"):
        value = row.get(key)
        if value:
            return value
    return None


def _ledger_rows(ledger_path: str) -> list[dict[str, Any]]:
    """Read a ledger's rows, in file order, from either shipped format.

    TWO formats are in service, and a reader that silently returns [] for the
    one it does not recognise reports a boundary of `None` and a count of 0 —
    which is indistinguishable from a genuine `0/5 WAIT`.  So:

    - JSONL, one object per line — the template's `evidence/ledger.jsonl`;
    - a single JSON OBJECT carrying an `events` array — the donor's
      `workers-ledger.json`.

    File order IS append order in both, which is what makes "the newest row"
    and "the rows after it" well defined without reading a clock.
    """
    path = Path(ledger_path)
    if not path.is_file():
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        # Could be a single JSON object (donor) or JSONL whose first line is one.
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            events = obj.get("events")
            if isinstance(events, list):
                return [r for r in events if isinstance(r, dict)]

    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def cadence_stamp(ledger_path: str, every: int = CADENCE_DEFAULT_EVERY,
                  pattern: str = CADENCE_PATTERN,
                  bump_event: str = CADENCE_BUMP_EVENT) -> dict[str, Any]:
    """Compute the cadence boundary from a ledger JSONL.

    TWO predicates, and they are not the same one:

    - the BOUNDARY is the NEWEST row whose text ANCHORS on `pattern` — the last
      cycle-close stamp;
    - the COUNT is the number of `bump_event` rows AFTER that boundary — the
      version bumps that have landed since the last cycle closed.

    `fires` is `count >= every`.  Counting anchored rows instead is the
    plausible misreading this docstring exists to prevent: the close stamp is
    itself anchored, so it would be counted as a bump.

    A row's kind is read from `event` (the template ledger's column), then
    `kind` (the donor's), so one predicate serves both vocabularies.

    An unreadable or absent ledger is a NAMED state, never a silent zero:
    `fires` stays False and `ref` stays None, and the caller reports which.
    """
    rows = _ledger_rows(ledger_path)

    anchored = [(i, r) for i, r in enumerate(rows) if re.match(pattern, _ledger_text(r))]
    if anchored:
        index, row = anchored[-1]
        boundary_ref = f"n={row.get('n')}" if row.get("n") is not None else f"line={index + 1}"
        boundary_at = _row_ts(row)
        # The COUNT is over bump rows, not over anchored rows — see the note on
        # CADENCE_BUMP_EVENT.  Rows BEFORE the boundary are excluded by index.
        accepted_since = sum(
            1 for r in rows[index + 1:] if _row_kind(r) == bump_event
        )
    else:
        boundary_ref, boundary_at, accepted_since = None, None, 0

    return {
        "trigger": {"kind": "version_bumps", "every": every, "note": "", "counts": bump_event},
        "boundary": {
            "ref": boundary_ref,
            "at": boundary_at,
            "pattern": pattern,
            "accepted_since": accepted_since,
        },
        "fires": accepted_since >= every,
        "evaluated_at": _now(),
    }


def get_cycle_dir(cycle_id: str) -> Path:
    return REPO_ROOT / "reviews" / cycle_id


def load_state(cycle_id: str) -> dict[str, Any]:
    state_file = get_cycle_dir(cycle_id) / "state.json"
    if not state_file.is_file():
        return {}
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)


def read_state(cycle_id: str) -> dict[str, Any]:
    """The state AS THE v1 CONTRACT: normalized in memory, never on disk."""
    return normalize_state(load_state(cycle_id), cycle_id)


def save_state(cycle_id: str, state: dict[str, Any], migrate: bool = False) -> int:
    """Write the v1 shape.

    Refuses (rc=3) to overwrite a state file that predates the schema unless
    the caller passes `migrate=True`, because historical evidence is migrated
    by an explicit act that leaves a pre-image, never as a side effect of a
    routine write.
    """
    cycle_dir = get_cycle_dir(cycle_id)
    cycle_dir.mkdir(parents=True, exist_ok=True)
    state_file = cycle_dir / "state.json"

    existing = load_state(cycle_id)
    if existing and "schema_version" not in existing and not migrate:
        print(
            f"REFUSED: '{state_file}' predates schema v{SCHEMA_VERSION}. "
            f"Run `review.py migrate {cycle_id}` - it writes a pre-image first.",
            file=sys.stderr,
        )
        return 3

    state["schema_version"] = SCHEMA_VERSION
    state["updated_at"] = _now()
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    return 0


def _stream_sha256(path: Path) -> str:
    """Digest a file in CONSTANT memory. A whole-file read() is banned here.

    The memory law on this box is a cgroup decision, not a host one, and every
    tool child adds to that cgroup: a 1 GB read to compute a digest is exactly
    the fat child the rule exists to prevent.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def is_frozen(state: dict[str, Any]) -> bool:
    """A cycle is FROZEN when its lifecycle is terminal, or when frozen_at is set.

    Terminal status IS the freeze, not a separate switch: a closed cycle's
    inputs became historical the moment it closed, so a design that required a
    second command to freeze it would leave open exactly the window this guard
    exists to shut.
    """
    if not state:
        return False
    return bool(state.get("frozen_at")) or state.get("status") in ("COMPLETED", "ABANDONED")

def snapshot_inputs(cycle_dir: Path) -> dict[str, Any]:
    """Record WHAT the cycle read and WHEN: one digest per declared channel.

    Two channels are named because they are the two the engine can read: the
    `proposals/` directory, which is authoritative and always current, and an
    OPTIONAL ledger, which must be declared before it is read at all.
    """
    declaration = _intake_declaration(cycle_dir)
    candidates: list[tuple[str, str, Path]] = [("dir", "proposals", cycle_dir / "proposals")]
    declared_ledger = declaration.get("ledger")
    if declared_ledger:
        candidates.append(("ledger", str(declared_ledger), Path(str(declared_ledger))))

    channels: list[dict[str, Any]] = []
    for kind, ref, path in candidates:
        entry: dict[str, Any] = {"kind": kind, "ref": ref, "exists": path.exists()}
        if path.is_file():
            entry["sha256"] = _stream_sha256(path)
            entry["bytes"] = path.stat().st_size
        elif path.is_dir():
            files = sorted(p for p in path.rglob("*") if p.is_file())
            hasher = hashlib.sha256()
            for item in files:
                hasher.update(item.relative_to(path).as_posix().encode())
                hasher.update(_stream_sha256(item).encode())
            entry["files"] = len(files)
            entry["sha256"] = hasher.hexdigest()
        channels.append(entry)
    return {"taken_at": _now(), "channels": channels}

def refuse_live_read(state: dict[str, Any], cycle_id: str, channel: str,
                     live: bool) -> int | None:
    """Gate a LIVE-sourced read against a FROZEN cycle.

    Returns None when the read may proceed, else the exit code and the refusal.
    Not a lock — a named state: `--live` is the explicit way to say "I know this
    cycle is closed and I want today's bytes anyway", and the read then says so
    on stdout so the answer can never be mistaken for the frozen one.
    """
    if not is_frozen(state):
        return None
    frozen_at = state.get("frozen_at") or state.get("ended_at") or state.get("status")
    if live:
        print(
            f"WARNING: cycle '{cycle_id}' is FROZEN at {frozen_at} and {channel} was "
            f"read with --live. These bytes are TODAY's, not the cycle's: the frozen "
            f"snapshot is inputs_snapshot in state.json.",
            file=sys.stderr,
        )
        return None
    print(
        f"REFUSED: cycle '{cycle_id}' is FROZEN at {frozen_at}; {channel} would read live "
        f"mutable input the cycle did not close on. Re-run with --live to read today's bytes "
        f"deliberately, or read the frozen snapshot in state.json.",
        file=sys.stderr,
    )
    return 2

def cmd_step0(cycle_id: str, record: bool = False) -> int:
    """The step-0 recovery point: where a resumed reader stands, from state ALONE.

    The module docstring has claimed since promotion that state.json IS the
    step-0 recovery point. A claim in a docstring is not a mechanism: a
    compacted session cannot run a paragraph. This is the claim as a COMMAND,
    and it reads state.json and nothing else — no ledger, no proposals dir, no
    live channel — so it answers the same way on a resumed run as on the first.

    `--record` appends the reading to step0_log, which is what makes the
    recovery DURABLE rather than merely printed.
    """
    state = read_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2

    lenses = state.get("lenses", {})
    completed = [l for l in known_lenses() if (lenses.get(l) or {}).get("status") == "COMPLETED"]
    waived = [l for l in known_lenses() if (lenses.get(l) or {}).get("status") == "WAIVED"]
    pending = [l for l in known_lenses()
               if (lenses.get(l) or {}).get("status", "PENDING") not in ("COMPLETED", "WAIVED")]
    frozen = is_frozen(state)

    if frozen:
        next_action = (
            "cycle is FROZEN (terminal): report the frozen snapshot. Do NOT re-read a live "
            "ledger or proposals dir — pass --live only to say you mean today's bytes."
        )
    elif pending:
        next_action = f"brief and record lens {pending[0]} (pending: {','.join(pending)})"
    elif not state.get("ended_at"):
        next_action = f"verify, then close (status={state.get('status')})"
    else:
        next_action = "nothing owed"

    print(f"=== Step 0 recovery: {cycle_id} ===")
    frozen_note = f" (frozen_at {state.get('frozen_at')})" if state.get("frozen_at") else ""
    print(f"status      : {state.get('status')}  frozen={'yes' if frozen else 'no'}{frozen_note}")
    print(f"started_at  : {state.get('started_at')}   ended_at: {state.get('ended_at')}")
    print(f"census      : {len(completed)} completed | {len(waived)} waived | "
          f"{len(pending)} pending (of {len(known_lenses())})")
    print(f"proposals   : {len(state.get('proposals') or [])} receipt(s)")
    snapshot = state.get("inputs_snapshot") or {}
    if snapshot:
        print(f"inputs      : frozen snapshot taken {snapshot.get('taken_at')}")
        for channel in snapshot.get("channels") or []:
            print(f"  [{channel.get('kind')}] {channel.get('ref')} "
                  f"exists={channel.get('exists')} sha256={str(channel.get('sha256'))[:16]}")
    print(f"next action : {next_action}")

    if record:
        state.setdefault("step0_log", []).append({
            "at": _now(),
            "status": state.get("status"),
            "frozen": frozen,
            "completed": len(completed),
            "waived": len(waived),
            "pending": len(pending),
            "pending_lenses": pending,
            "next_action": next_action,
        })
        rc = save_state(cycle_id, state)
        if rc != 0:
            return rc
        print(f"recorded step-0 reading #{len(state['step0_log'])} in {cycle_id}/state.json")
    return 0

def cmd_init(cycle_id: str) -> int:
    cycle_dir = get_cycle_dir(cycle_id)
    reports_dir = cycle_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(cycle_id)
    if state and state.get("status") == "IN_PROGRESS":
        print(f"Cycle '{cycle_id}' already initialized and IN_PROGRESS.")
        return 0

    rc = save_state(cycle_id, _empty_state(cycle_id))
    if rc != 0:
        return rc
    print(
        f"Initialized review cycle '{cycle_id}' with {len(known_lenses())} "
        f"lenses, core + declared (schema v{SCHEMA_VERSION})."
    )
    return 0


def cmd_brief(lens: str, json_out: bool = False) -> int:
    lens = lens.upper()
    if lens_metadata(lens) is None:
        print(f"Error: Lens '{lens}' not in catalog {known_lenses()}", file=sys.stderr)
        return 2

    meta = lens_metadata(lens)
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
    if lens_metadata(lens) is None:
        print(f"Error: Lens '{lens}' not in catalog {known_lenses()}", file=sys.stderr)
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

    # Append to index log — the receipt.  The FULL path is written, never a
    # bare filename: a receipt that cannot be re-resolved from the line is not
    # a receipt.  The line format is the donor's, `ts|lens|path|sha256|bytes`.
    now = _now()
    index_file = reports_dir / "review-index.log"
    with open(index_file, "a", encoding="utf-8") as f:
        f.write(
            f"{now}|{lens}|{report_file.relative_to(REPO_ROOT)}|{digest}|{len(body)}\n"
        )

    # Update state
    state = read_state(cycle_id)
    if not state:
        state = _empty_state(cycle_id)
    entry = dict(state["lenses"].get(lens) or {})
    entry.update({
        "status": "COMPLETED",
        "report_path": str(report_file.relative_to(REPO_ROOT)),
        "sha256": digest,
        "receipt": "verified",
        "recorded_at": now,
    })
    state["lenses"][lens] = entry
    rc = save_state(cycle_id, state)
    if rc != 0:
        return rc
    print(f"Persisted report for Lens {lens}: {digest[:16]}... ({len(body)} bytes)")
    return 0


def cmd_waive(cycle_id: str, lens: str, reason: str, by: str | None = None) -> int:
    lens = lens.upper()
    if lens_metadata(lens) is None:
        print(f"Error: Lens '{lens}' not in catalog {known_lenses()}", file=sys.stderr)
        return 2
    if not reason.strip():
        print("Error: Waiver reason cannot be empty.", file=sys.stderr)
        return 2

    state = read_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2

    now = _now()
    # ONE home: the log array in state.json.  The donor's separate
    # `waivers.log` is not carried — two homes for one thing is the defect
    # promotion exists to collapse, and the donor's own live cycle
    # (20260927-c25) carries no such file at all.
    state.setdefault("waivers", []).append({
        "lens": lens,
        "reason": reason,
        "by": by,
        "waived_at": now,
    })
    entry = dict(state["lenses"].get(lens) or {})
    entry.update({"status": "WAIVED", "reason": reason, "recorded_at": now})
    state["lenses"][lens] = entry
    rc = save_state(cycle_id, state)
    if rc != 0:
        return rc

    print(f"Waived Lens {lens}: {reason}")
    return 0


def cmd_codify(cycle_id: str, finding: str, disposition: str, home: str | None,
               reason: str | None) -> int:
    """Record an ACCEPTED finding with the carrier its disposition owes.

    This is the producer the enforcement needs.  Without it `codification_plan`
    had a reader (verify, close) and no writer at all — so the field stayed at
    the empty list `_empty_state` seeds, `codification_gaps` saw no entries, and
    a gate over a permanently-empty population would have read green forever.
    That is the same defect class one level up: the contract was unenforced, and
    this command is what makes it enforced rather than merely declarable.

    The carrier is validated HERE as well as in verify, and for a different
    reason: a refusal at write time names the mistake while the operator still
    has the finding in hand, where a refusal at close time is a puzzle.
    """
    if disposition not in CODIFICATION_DISPOSITIONS:
        print(f"Error: disposition must be one of {CODIFICATION_DISPOSITIONS}", file=sys.stderr)
        return 2
    if not finding.strip():
        print("Error: --finding cannot be empty.", file=sys.stderr)
        return 2
    owed = CODIFICATION_OBLIGATIONS[disposition]
    supplied = home if owed == "home" else reason
    if not (supplied or "").strip():
        print(
            f"Error: disposition {disposition!r} owes a {owed}; pass --{owed}.",
            file=sys.stderr,
        )
        return 2

    state = read_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2
    if is_frozen(state):
        print(
            f"Error: Cycle '{cycle_id}' is FROZEN ({state.get('frozen_at')}). "
            f"A closed cycle's inputs are historical; record the finding in a new cycle.",
            file=sys.stderr,
        )
        return 2

    # ONE home for accepted findings: the plan array. A second log would be the
    # two-homes defect the waivers leg already collapsed.
    entry: dict[str, Any] = {
        "finding": finding.strip(),
        "disposition": disposition,
        "home": (home.strip() if isinstance(home, str) and home.strip() else None),
        "reason": (reason.strip() if isinstance(reason, str) and reason.strip() else None),
        "recorded_at": _now(),
    }
    state.setdefault("codification_plan", []).append(entry)
    rc = save_state(cycle_id, state)
    if rc != 0:
        return rc

    where = entry["home"] or entry["reason"]
    print(
        f"Recorded finding as {disposition} ({owed}={where!r}) — "
        f"plan now carries {len(state['codification_plan'])} accepted finding(s)."
    )
    return 0

def cmd_status(cycle_id: str) -> int:
    state = read_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2

    print(f"=== Review Cycle: {cycle_id} ({state.get('status', 'UNKNOWN')}) ===")
    lenses = state.get("lenses", {})
    completed = 0
    waived = 0
    pending = 0

    for lens in known_lenses():
        info = lenses.get(lens, {})
        status = info.get("status", "PENDING")
        if status == "COMPLETED":
            completed += 1
            # A MIGRATED record carries the report PATH and no digest: the donor
            # never recorded one, and a migration that invented a digest would be
            # asserting a verification nobody performed.  Rendered as `unrecorded`
            # rather than crashed on, so a donor cycle reads end-to-end.
            digest = info.get("sha256")
            shown = digest[:8] if isinstance(digest, str) and digest else "unrecorded"
            # The report path is resolved across BOTH key names, because the donor renamed
            # it in eleven of its own entries and a record read without migration must not
            # report a launched lens as having no report.
            path = info.get("report_path") or info.get("path")
            print(f"  [{status}] Lens {lens} -> {path} ({shown})")
        elif status == "WAIVED":
            waived += 1
            print(f"  [{status}] Lens {lens} -> {info.get('reason')}")
        else:
            pending += 1
            print(f"  [{status}] Lens {lens}")

    cadence = state.get("cadence") or {}
    boundary = cadence.get("boundary") or {}
    every = (cadence.get("trigger") or {}).get("every", CADENCE_DEFAULT_EVERY)
    print(
        f"\nCadence: {boundary.get('accepted_since', 0)}/{every} "
        f"{'FIRE' if cadence.get('fires') else 'WAIT'} "
        f"(boundary {boundary.get('ref')}, evaluated {cadence.get('evaluated_at')})"
    )
    print(f"\nSummary: {completed} Completed | {waived} Waived | {pending} Pending (Total: {len(known_lenses())})")
    return 0 if pending == 0 else 1


# --- codification plan enforcement -------------------------------------------------
# The schema declares this contract at "codification_plan": an accepted finding with
# no landed home "is a cycle-completion FAILURE, never a scheduling choice".  A
# declaration nothing reads is the defect this block exists to close — the same class
# as a claim in a docstring, which is why the enforcement sits in both verify and
# close rather than in prose.
CODIFICATION_DISPOSITIONS = ["landed", "routed", "rejected"]
CODIFICATION_OBLIGATIONS = {
    # the file+section the finding landed in
    "landed": "home",
    # where it was routed TO: a route with no destination is indistinguishable
    # from a drop, so a routed finding owes the same carrier as a landed one
    "routed": "home",
    # the recorded non-fix, which stays legal (F5's narrower reading) but only
    # with its reason on the surface
    "rejected": "reason",
}


def codification_gaps(plan: Any) -> list[str]:
    """Name every plan entry that owes a carrier and does not carry one.

    An EMPTY plan is not a gap: a cycle that accepted no findings owes no landing.
    The gap is an accepted finding whose disposition names no home and no reason,
    which is a finding that goes nowhere while the cycle reads COMPLETED.
    """
    if not plan:
        return []
    if not isinstance(plan, list):
        return [f"codification_plan is {type(plan).__name__}, not a list"]
    gaps: list[str] = []
    for i, entry in enumerate(plan, 1):
        if not isinstance(entry, dict):
            gaps.append(f"#{i}: not an object ({type(entry).__name__})")
            continue
        finding = (entry.get("finding") or "").strip() if isinstance(entry.get("finding"), str) else f"#{i}"
        finding = finding or f"#{i}"
        disp = entry.get("disposition")
        disp = disp.strip() if isinstance(disp, str) else ""
        if disp not in CODIFICATION_DISPOSITIONS:
            gaps.append(
                f"{finding}: disposition {disp!r} is not one of {CODIFICATION_DISPOSITIONS}"
            )
            continue
        owed = CODIFICATION_OBLIGATIONS[disp]
        val = entry.get(owed)
        if not (isinstance(val, str) and val.strip()):
            gaps.append(f"{finding}: disposition {disp!r} owes a {owed} and carries none")
    return gaps


def census_gaps(state: dict[str, Any]) -> list[str]:
    """Lenses that are neither run nor explicitly waived.

    The mirror of `codification_gaps`, and a SEPARATE obligation: the plan check
    asks what happened to what the review FOUND, this one asks whether the review
    HAPPENED. Measured before this function existed: `verify` failed over 14
    PENDING lenses while `close --status COMPLETED` returned 0 and froze the
    cycle — so the census apparatus was advisory and a cycle could read COMPLETED
    with no lens ever run. That is the silent pass the lifecycle exists to
    forbid, and it is the worse of the two gaps because it needs no mistake:
    a lane that simply never ran the review reached the same state as one that
    ran it clean.
    """
    gaps: list[str] = []
    lenses = state.get("lenses") or {}
    for lens in known_lenses():
        info = lenses.get(lens) or {}
        status = info.get("status", "PENDING")
        if status == "WAIVED":
            if not (info.get("reason") or "").strip():
                gaps.append(f"{lens} (waived with no reason)")
            continue
        if status != "COMPLETED":
            gaps.append(f"{lens} ({status})")
    return gaps


def cmd_lenses(json_out: bool = False) -> int:
    """The lawful lens set: the core catalogue plus this factory's declarations.

    The one place a member can SEE which lenses its own declaration made lawful,
    so the extension surface is observable rather than inferred from a refusal.
    """
    declared = declared_lenses()
    if json_out:
        print(json.dumps({
            "core": CATALOG_LENSES,
            "declared": [d["id"].strip().upper() for d in declared],
            "known": known_lenses(),
            "declaration_file": str(REVIEW_LENSES_FILE),
            "declaration_read": REVIEW_LENSES_FILE.is_file(),
        }, indent=2))
        return 0
    print(f"Core catalogue ({len(CATALOG_LENSES)}): {', '.join(CATALOG_LENSES)}")
    if declared:
        names = ", ".join(d["id"].strip().upper() for d in declared)
        print(f"Declared here ({len(declared)}): {names}")
    else:
        print(f"Declared here (0): none -- {REVIEW_LENSES_FILE} is absent or declares nothing")
    print(f"Known ({len(known_lenses())}): {', '.join(known_lenses())}")
    return 0

def cmd_verify(cycle_id: str) -> int:
    state = read_state(cycle_id)
    if not state:
        print(f"FAIL: Cycle '{cycle_id}' state.json missing.", file=sys.stderr)
        return 1

    lenses = state.get("lenses", {})
    missing: list[str] = []
    corrupted: list[str] = []
    unverified: list[str] = []

    for lens in known_lenses():
        info = lenses.get(lens, {})
        status = info.get("status", "PENDING")
        if status == "WAIVED":
            # A waiver without a reason is refused at write time; one that
            # slipped in without a reason is a finding here, never a pass.
            if not (info.get("reason") or "").strip():
                missing.append(f"{lens} (waived with no reason)")
            continue
        if status != "COMPLETED":
            missing.append(f"{lens} ({status})")
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
        # A report whose index line is absent is UNRECEIPTED: a distinct state
        # from missing, and never a silent pass.
        if info.get("receipt") != "verified":
            unverified.append(lens)

    unlanded = codification_gaps(state.get("codification_plan"))

    if missing or corrupted or unverified or unlanded:
        print(f"FAIL: Cycle '{cycle_id}' census check failed.")
        if missing:
            print(f"  Missing or incomplete lenses: {', '.join(missing)}")
        if corrupted:
            print(f"  Checksum corrupted lenses: {', '.join(corrupted)}")
        if unverified:
            print(f"  UNRECEIPTED lenses (no index line): {', '.join(unverified)}")
        if unlanded:
            print(f"  UNLANDED codification entries (accepted finding, no carrier): {', '.join(unlanded)}")
        return 1

    plan = state.get("codification_plan") or []
    print(
        f"PASS: Cycle '{cycle_id}' census verified clean across all {len(known_lenses())} lenses "
        f"(codification plan: {len(plan)} accepted finding(s), all accounted for)."
    )
    return 0


def cmd_compile(cycle_id: str) -> int:
    state = read_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2

    cycle_dir = get_cycle_dir(cycle_id)
    verdict_file = cycle_dir / "verdict.md"

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

    lens_names = {k: (lens_metadata(k) or {}).get("name", "") for k in known_lenses()}

    lenses = state.get("lenses", {})
    for lens in known_lenses():
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


def _parse_ts(value: Any) -> datetime.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def cmd_schema() -> int:
    """Emit the state schema.

    The shipped artifact `docs/review-cycle.schema.json` (and its
    `TEMPLATE/docs/` twin) is generated from THIS command, so the contract has
    one authoring home.  Regenerate with:
        python3 tools/review.py schema > docs/review-cycle.schema.json
        cp docs/review-cycle.schema.json TEMPLATE/docs/review-cycle.schema.json
    """
    sys.stdout.write(json.dumps(STATE_SCHEMA, indent=2) + "\n")
    return 0


def cmd_cadence(ledger_path: str, every: int, cycle_id: str | None,
                json_out: bool, live: bool = False) -> int:
    """Compute the cadence boundary stamp, and optionally record it.

    The boundary is an OBSERVABLE artifact, not prose: a member's cadence state
    is the ledger's own anchored notes, re-derivable by anyone holding the
    ledger.  Recording it into a cycle is `--write <cycle_id>` — and a ledger is
    LIVE mutable input, so writing one into a FROZEN cycle is refused unless
    `--live` says the reader means today's ledger.
    """
    stamp = cadence_stamp(ledger_path, every)
    if cycle_id:
        state = read_state(cycle_id)
        if not state:
            print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
            return 2
        refused = refuse_live_read(state, cycle_id, "cadence --write", live)
        if refused is not None:
            return refused
        state["cadence"] = stamp
        rc = save_state(cycle_id, state)
        if rc != 0:
            return rc

    if json_out:
        sys.stdout.write(json.dumps(stamp, indent=2) + "\n")
        return 0
    boundary = stamp["boundary"]
    print(
        f"cadence: {boundary['accepted_since']}/{stamp['trigger']['every']} "
        f"{'FIRE' if stamp['fires'] else 'WAIT'} "
        f"(boundary {boundary['ref']} at {boundary['at']}, "
        f"pattern {boundary['pattern']}, ledger {ledger_path})"
    )
    return 0


def cmd_close(cycle_id: str, status: str, stamp: bool,
              ledger_path: str | None) -> int:
    """Close the cycle: an EXPLICIT terminal state carrying both durations.

    `ended_at` is set here and never inferred from `updated_at`, because a
    reader that cannot tell "finished" from "untouched" is the defect the
    donor's own schema table records.
    """
    if status not in LIFECYCLE_STATES:
        print(f"Error: status must be one of {LIFECYCLE_STATES}", file=sys.stderr)
        return 2
    state = read_state(cycle_id)
    if not state:
        print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
        return 2
    if state.get("status") != "IN_PROGRESS":
        print(f"Error: Cycle '{cycle_id}' is already {state.get('status')}.", file=sys.stderr)
        return 2

    # A COMPLETED close is refused over an unlanded accepted finding — that is the
    # schema's own words.  ABANDONED is NOT refused: a cycle that cannot complete must
    # still be closable, or the enforcement traps it in IN_PROGRESS forever, which is
    # worse than the silent pass it prevents.
    if status == "COMPLETED":
        # TWO obligations, checked separately so a refusal says WHICH one failed.
        # A COMPLETED close means the review happened AND what it found is
        # accounted for; either alone is a cycle that reads finished without
        # being finished.
        ran = census_gaps(state)
        if ran:
            print(
                f"Error: Cycle '{cycle_id}' cannot close COMPLETED — "
                f"{len(ran)} lens(es) neither run nor explicitly waived:",
                file=sys.stderr,
            )
            for g in ran:
                print(f"  - {g}", file=sys.stderr)
            return 1
        gaps = codification_gaps(state.get("codification_plan"))
        if gaps:
            print(
                f"Error: Cycle '{cycle_id}' cannot close COMPLETED — "
                f"{len(gaps)} accepted finding(s) with no carrier:",
                file=sys.stderr,
            )
            for g in gaps:
                print(f"  - {g}", file=sys.stderr)
            return 1

    started = _parse_ts(state.get("started_at"))
    state["status"] = status
    state["ended_at"] = _now()
    if started:
        span = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds() / 60.0
        state["duration_cycle_min"] = round(span, 1)

    # duration_review_min is review start to the LAST report persisted — a
    # different number from the cycle span, never conflated with it.
    recorded = [
        _parse_ts((state["lenses"].get(lens) or {}).get("recorded_at"))
        for lens in known_lenses()
    ]
    recorded = [t for t in recorded if t is not None]
    if recorded and started:
        review_span = (max(recorded) - started).total_seconds() / 60.0
        state["duration_review_min"] = round(review_span, 1)

    if stamp and ledger_path:
        every = (state["cadence"].get("trigger") or {}).get("every", CADENCE_DEFAULT_EVERY)
        state["cadence"] = cadence_stamp(ledger_path, every)

    # Closing FREEZES: the inputs become historical at this instant, and the
    # snapshot records what they were so a later reader can tell the cycle's
    # own bytes from today's. Taken here rather than in a separate command
    # because the window between close and freeze is the window that matters.
    state["frozen_at"] = _now()
    state["inputs_snapshot"] = snapshot_inputs(get_cycle_dir(cycle_id))

    rc = save_state(cycle_id, state)
    if rc != 0:
        return rc
    print(
        f"Closed cycle '{cycle_id}' as {status}; "
        f"duration_cycle_min={state['duration_cycle_min']}, "
        f"duration_review_min={state['duration_review_min']}, "
        f"frozen_at={state['frozen_at']}, "
        f"inputs snapshotted={len((state['inputs_snapshot'] or {}).get('channels') or [])} channel(s)"
    )
    return 0


def cmd_migrate(cycle_id: str, dry_run: bool) -> int:
    """Migrate a pre-v1 state file to v1, leaving a pre-image behind.

    This is the documented adapter, and it is an EXPLICIT act: a routine write
    refuses a legacy file (rc=3) rather than migrating it by accident, because
    historical evidence is never rewritten in place as a side effect.
    """
    raw = load_state(cycle_id)
    if not raw:
        print(f"Error: Cycle '{cycle_id}' has no state.json to migrate.", file=sys.stderr)
        return 2
    if "schema_version" in raw:
        print(f"Cycle '{cycle_id}' is already schema v{raw['schema_version']}; nothing to migrate.")
        return 0

    migrated = normalize_state(raw, cycle_id)
    dropped = sorted(set(raw) - set(migrated))
    print(
        f"Migrate '{cycle_id}': {len(raw)} keys read -> {len(migrated)} written, "
        f"schema v{SCHEMA_VERSION}"
    )
    for key in sorted(raw):
        print(f"  {key:24} {'kept' if key in migrated else 'DROPPED'}")
    if dropped:
        print(f"  dropped: {', '.join(dropped)}")

    # TERMINAL VOCABULARY, reported rather than silently absorbed.  The donor's
    # `status` carries six distinct values and its lens entries four, so a
    # migration that maps the known synonym and says nothing about the rest
    # leaves a reader unable to tell "mapped" from "carried in unvalidated".
    raw_status = raw.get("status")
    if raw_status is not None and raw_status != migrated.get("status"):
        print(f"  status mapped: {raw_status!r} -> {migrated['status']!r}")
    unmapped: list[str] = []
    if migrated.get("status") not in LIFECYCLE_STATES:
        unmapped.append(f"status={migrated.get('status')!r}")
    seen_lens_values: dict[str, str] = {}
    for lens, entry in ((raw.get("lenses") or {}) if isinstance(raw.get("lenses"), dict) else {}).items():
        if isinstance(entry, dict) and entry.get("status") is not None:
            seen_lens_values[str(entry["status"])] = lens
    for value in sorted(seen_lens_values):
        if value not in LENS_STATES and value not in TERMINAL_SYNONYMS:
            unmapped.append(f"lens status={value!r} (e.g. lens {seen_lens_values[value]})")
    if unmapped:
        print(f"  UNMAPPED (carried in, not valid here): {'; '.join(unmapped)}")

    # LENS ENTRY KEYS, reported for the same reason the values are: the donor renames a key in
    # some entries and carries keys the schema has no home for, and a migration that absorbed
    # either in silence would leave a reader unable to tell what was kept from what was lost.
    template_keys: set[str] = set()
    for lens in known_lenses():
        e = (migrated.get("lenses") or {}).get(lens)
        if isinstance(e, dict):
            template_keys = set(e)
            break
    raw_lenses = raw.get("lenses") if isinstance(raw.get("lenses"), dict) else {}
    renamed: dict[str, str] = {}
    dropped_keys: dict[str, str] = {}
    for lens, entry in raw_lenses.items():
        if not isinstance(entry, dict):
            continue
        for k in entry:
            if k in LENS_KEY_SYNONYMS:
                renamed.setdefault(k, lens)
            elif template_keys and k not in template_keys:
                dropped_keys.setdefault(k, lens)
    if renamed:
        print("  lens keys mapped: " + "; ".join(
            f"{k!r} -> {LENS_KEY_SYNONYMS[k]!r} (e.g. lens {v})" for k, v in sorted(renamed.items())))
    if dropped_keys:
        print("  lens keys DROPPED (no home in the schema): " + "; ".join(
            f"{k!r} (e.g. lens {v})" for k, v in sorted(dropped_keys.items())))
    if dry_run:
        print("dry run: nothing written")
        return 0

    state_file = get_cycle_dir(cycle_id) / "state.json"
    pre_image = state_file.with_name("state.json.pre-v1.bak")
    if not pre_image.exists():
        pre_image.write_bytes(state_file.read_bytes())
        print(f"pre-image written: {pre_image}")
    rc = save_state(cycle_id, migrated, migrate=True)
    if rc != 0:
        return rc
    print(f"migrated: {state_file}")
    return 0


# ---------------------------------------------------------------------------
# Duty-4 intake — the member-facing input leg
# ---------------------------------------------------------------------------

PROPOSAL_FORMAT = re.compile(
    r"^(?P<op>ADD|CHANGE)\s+(?P<rule>.+?)\s+in\s+(?P<target>[^\s]+)\s+BECAUSE\s+(?P<evidence>.+)$",
    re.DOTALL,
)
# The trailing guard is `(?!\d)`, never `\b`. A published reading carries its instant in
# the ISO-8601 `T` form — the form used throughout
# docs/instruments/template-instruments.md §7.4 — and `\b` cannot match between the
# final digit and that `T` (both are word characters), so the mandated form read UNDATED
# while a bare date read DATED, flagging every adopter who followed the dating
# discipline. The lookahead still refuses a partial digit run (`2026-09-271`), the one
# thing that boundary covered.
DATE_TOKEN = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})(?!\d)")
INTAKE_DECL_NAME = "intake.json"
PROPOSAL_KIND_DEFAULT = "proposal"

def _intake_declaration(cycle_dir: Path) -> dict[str, Any]:
    """The member's declaration of where its input lands.

    Absent is a STATE, not an error: a member with no ledger says so by not
    declaring one, and the leg NAMES the absent channel rather than reading
    nothing from it and calling that a clean zero.

    A DECLARED channel the tree cannot honour is a REFUSAL, not an empty read.
    That distinction is the whole point — the false-negative this leg exists to
    prevent is a declared channel that silently yields nothing, which is
    indistinguishable from a genuine "nobody submitted".
    """
    decl_file = cycle_dir / INTAKE_DECL_NAME
    if not decl_file.is_file():
        return {"declared": False, "ledger": None, "ledger_kind": PROPOSAL_KIND_DEFAULT,
                "decl_file": None, "error": None}
    try:
        raw = json.loads(decl_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"declared": True, "ledger": None, "ledger_kind": PROPOSAL_KIND_DEFAULT,
                "decl_file": str(decl_file), "error": str(exc)}
    if not isinstance(raw, dict):
        return {"declared": True, "ledger": None, "ledger_kind": PROPOSAL_KIND_DEFAULT,
                "decl_file": str(decl_file), "error": "top level is not an object"}
    ledger = raw.get("ledger")
    kind = raw.get("ledger_kind")
    return {
        "declared": True,
        "ledger": ledger if isinstance(ledger, str) and ledger.strip() else None,
        "ledger_kind": kind if isinstance(kind, str) and kind.strip() else PROPOSAL_KIND_DEFAULT,
        "decl_file": str(decl_file),
        "error": None,
    }

def _parse_proposal(text: str) -> dict[str, Any]:
    """Validate one proposal against the strict format, or say why it is INVALID.

    `ADD|CHANGE <rule> in <file+section> BECAUSE <gap actually hit>` with a date
    in the evidence. A malformed proposal is INVALID and REPORTED — never
    skipped. A file quietly passed over reads exactly like one that was never
    written, which is the same false-negative shape as an unread channel.
    """
    m = PROPOSAL_FORMAT.match(text.strip())
    if not m:
        return {"valid": False, "reason": "format"}
    evidence = m.group("evidence").strip()
    if not evidence:
        return {"valid": False, "reason": "empty-evidence"}
    return {
        "valid": True,
        "op": m.group("op"),
        "rule": m.group("rule").strip(),
        "target": m.group("target"),
        "evidence": evidence,
        "dated": bool(DATE_TOKEN.search(evidence)),
    }

def _proposal_rows_from_ledger(ledger_path: Path, kind: str) -> list[tuple[str, str]]:
    """The ledger channel's proposal rows, as (id, text).

    The KIND is declared, never assumed: the template's ledger vocabulary is
    `event`, the donor's is `kind`, and a member may name its own. `_row_kind`
    reads both, so one predicate serves every adopter.
    """
    out: list[tuple[str, str]] = []
    for row in _ledger_rows(str(ledger_path)):
        if _row_kind(row) != kind:
            continue
        text = _ledger_text(row)
        if not text:
            continue
        ref = row.get("n") or row.get("id") or row.get("ts") or row.get("t") or "?"
        out.append((str(ref), text))
    return out

def cmd_intake(cycle_id: str, record: bool = False, live: bool = False) -> int:
    """Read the cycle's input channels and report a NAMED intake state.

    TWO channels, and the difference between them is load-bearing:

    - the `proposals/` DIRECTORY is authoritative and always current;
    - a LEDGER is OPTIONAL and must be DECLARED. A member with no ledger is not
      a member with no input, so an undeclared ledger is named ABSENT rather
      than read as empty.

    READ-ONLY over every factory-owned byte. The proposal files and the ledger
    are the member's data, and this leg never writes them; the receipt index it
    produces goes into the cycle STATE, which is the instrument's own.

    FROZEN cycles are REFUSED here: both channels are LIVE and MUTABLE, so
    re-reading one against a closed cycle answers a different question than the
    one the cycle closed on. `--live` is the deliberate way to ask for today's
    bytes, and it says so on stdout.

    Exit: 0 COMPLETE · 1 EMPTY or INCOMPLETE (a named state, never a pass) ·
          2 REFUSED (nothing declared, a channel the tree lacks, or a frozen cycle).
    """
    cycle_dir = get_cycle_dir(cycle_id)
    if not cycle_dir.is_dir():
        print(f"INTAKE REFUSED: cycle '{cycle_id}' has no directory at {cycle_dir}.",
              file=sys.stderr)
        return 2

    refused = refuse_live_read(read_state(cycle_id), cycle_id, "intake", live)
    if refused is not None:
        return refused

    decl = _intake_declaration(cycle_dir)
    proposals_dir = cycle_dir / "proposals"

    if decl["error"]:
        print(f"INTAKE REFUSED: {INTAKE_DECL_NAME} is unreadable — {decl['error']}",
              file=sys.stderr)
        return 2
    if not decl["declared"] and not proposals_dir.is_dir():
        print(
            "INTAKE REFUSED: no intake declarations — neither "
            f"{proposals_dir} nor {cycle_dir / INTAKE_DECL_NAME} exists. "
            "A member declares where its input lands; nothing declared is nothing to read.",
            file=sys.stderr,
        )
        return 2

    receipts: list[dict[str, Any]] = []
    invalid: list[tuple[str, str]] = []
    channels: list[str] = []

    if proposals_dir.is_dir():
        channels.append(f"dir:{proposals_dir} ({len(list(proposals_dir.glob('*.md')))} file(s))")
        for path in sorted(proposals_dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                invalid.append((path.name, f"unreadable: {exc}"))
                continue
            parsed = _parse_proposal(text)
            if parsed["valid"]:
                receipts.append({
                    "id": path.stem, "source": "dir", "path": str(path),
                    "recorded_at": _now(),
                    "op": parsed["op"], "target": parsed["target"],
                    "dated": parsed["dated"],
                })
            else:
                invalid.append((path.name, parsed["reason"]))
    else:
        channels.append(f"dir:{proposals_dir} ABSENT (not present)")

    if decl["ledger"]:
        ledger_path = Path(decl["ledger"])
        if not ledger_path.is_absolute():
            ledger_path = REPO_ROOT / ledger_path
        if not ledger_path.is_file():
            print(
                f"INTAKE REFUSED: {INTAKE_DECL_NAME} declares ledger "
                f"'{decl['ledger']}' but no such file exists. A declared channel "
                "the tree cannot honour is a refusal, not an empty read.",
                file=sys.stderr,
            )
            return 2
        rows = _proposal_rows_from_ledger(ledger_path, decl["ledger_kind"])
        channels.append(f"ledger:{ledger_path} (kind={decl['ledger_kind']}, {len(rows)} row(s))")
        for ref, text in rows:
            parsed = _parse_proposal(text)
            if parsed["valid"]:
                receipts.append({
                    "id": ref, "source": "ledger", "path": str(ledger_path),
                    "recorded_at": _now(),
                    "op": parsed["op"], "target": parsed["target"],
                    "dated": parsed["dated"],
                })
            else:
                invalid.append((f"ledger row {ref}", parsed["reason"]))
    else:
        channels.append("ledger ABSENT (not declared)")

    for line in channels:
        print(f"  channel {line}")
    undated = [r["id"] for r in receipts if not r["dated"]]

    if invalid:
        for name, reason in invalid:
            print(f"  INVALID {name}: {reason}", file=sys.stderr)
        print(f"INTAKE INCOMPLETE: {len(receipts)} valid, {len(invalid)} invalid.")
        rc = 1
    elif not receipts:
        print("INTAKE EMPTY: channels read, 0 proposals. Nothing submitted is a state, not a pass.")
        rc = 1
    else:
        print(f"INTAKE COMPLETE: {len(receipts)} proposal(s).")
        if undated:
            print(f"  WARNING undated evidence: {', '.join(undated)}")
        rc = 0

    if record:
        state = read_state(cycle_id)
        state["proposals"] = receipts
        state["status"] = state.get("status") or "IN_PROGRESS"
        save_state(cycle_id, state)
        print(f"  recorded {len(receipts)} receipt(s) in the cycle state")
    return rc

# ---------------------------------------------------------------- the brain leg (G4)

# The mechanical half of gap G4: four deterministic invariants over the ops profile's brain
# files. Those files are injected into EVERY lane's session and live in NO repository, so no
# repo gate can read them — their only defences were a semantic lens (by eye) and a size
# reading that printed and gated nothing. The owner re-homed the check here (q19,
# 2026-10-05T06:43:37Z); the spec is infra's §4
# (`vds-servers/docs/rulings/2026-10-02-shared-brain-gate-design.md`).
#
# STDLIB ONLY — this verb adds NO local import, so the instrument's declared closure stays
# EMPTY (instrument law §3) and a member that adopts the declared file set still gets a
# runnable executable. Every file is read STREAMED, line by line: the box runs a small cgroup
# cap and MEMORY.md is ~3.3k lines, so a whole-file `read()` is the one thing this must not do.

BRAIN_SIZE_LIMIT = 500      # the always-loaded file's line budget, from the profile's own canon
BRAIN_OWNS_WINDOW = 20      # lines the tolerant `Owns:` search reads
BRAIN_DUP_MIN_LEN = 20      # normalised chars below which a line is furniture, not a rule
BRAIN_REQUIRED = ("AGENTS.md", "SOUL.md", "USER.md")  # the always-injected triple

# A pointer is a bare `X.md` name after an arrow. A PATH (`skills/x/y.md`) is a repo citation,
# not a brain pointer, so it is out of scope by construction — the class carries no `/`.
_BRAIN_POINTER_RE = re.compile(r"→\s*\**`?([A-Za-z0-9_.\-]+\.md)`?\**")
# Tolerant `Owns:`: the blockquote markers are stripped before this is tried, the bold markers
# are optional, and it must sit at line start (SOUL.md carries its own inside a blockquote).
_BRAIN_OWNS_RE = re.compile(r"^\**\s*Owns:")
# A line made ENTIRELY of markdown furniture (`---`, `|---|`, a fence, `>`) is not a rule —
# and every file's table separators would otherwise read as duplicates of every other file's.
_BRAIN_STRUCTURE_RE = re.compile(r"^[\s|*_=`>:~\-]+$")


def _brain_lines(path: Path):
    """Yield `(lineno, text)` for a file, STREAMED — never a whole-file `read()`."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            yield lineno, raw.rstrip("\n")


def _brain_skill_names(home: Path) -> set:
    """The `*.md` names sitting directly inside a skill directory under `<home>/skills/`.

    A brain pointer names a sibling brain file OR a skill file — a routing table in the brain
    sends a reader to a skill's own law file (`SKILL.md`), which lives in `skills/<skill>/`. Both
    domains are real, so both resolve, and the rule is MECHANICAL rather than an allow-list (an
    allow-list is what silently grows). Scope limit, stated rather than implied: one level deep
    (`skills/*/*.md`); a pointer into a skill's own subdirectory is out of scope and reads as
    dangling rather than being quietly excused.
    """
    names = set()
    skills = home / "skills"
    if not skills.is_dir():
        return names
    for entry in sorted(skills.iterdir()):
        if not entry.is_dir():
            continue
        try:
            for candidate in entry.glob("*.md"):
                if candidate.is_file():
                    names.add(candidate.name)
        except OSError:
            continue
    return names


def cmd_brain(home_path: str, json_out: bool = False) -> int:
    """G4 — the four mechanical invariants over a profile's brain files.

    Read-only and deterministic. `--home` is the PROFILE HOME (`~/.opencrabs/profiles/ops`),
    never a repository: the brain lives in no repo, which is exactly why no repo gate could
    read it. The gate therefore runs on the box, and each member runs it against its own home.

    rc=0 all four hold; rc=1 one line per violation; rc=2 the home itself is unreadable.
    """
    home = Path(home_path).expanduser()
    if not home.is_dir():
        print(f"brain: home not found: {home}", file=sys.stderr)
        return 2

    files = sorted(p for p in home.glob("*.md") if p.is_file())
    names = {p.name for p in files}
    skill_names = _brain_skill_names(home)
    violations = []

    def flag(invariant: str, filename: str, detail: str) -> None:
        violations.append({"invariant": invariant, "file": filename, "detail": detail})

    # --- invariant 2a: the always-injected triple is PRESENT (absence reported by name) ----
    for required in BRAIN_REQUIRED:
        if required not in names:
            flag("missing", required, "required brain file absent from the profile home")

    line_counts = {}
    duplicated = {}

    for path in files:
        count = 0
        owns_seen = False
        for lineno, line in _brain_lines(path):
            count = lineno
            # invariant 2b — the ownership declaration, tolerant over the first N lines
            if not owns_seen and lineno <= BRAIN_OWNS_WINDOW:
                if _BRAIN_OWNS_RE.match(re.sub(r"^\s*>+\s*", "", line)):
                    owns_seen = True
            # invariant 3 — every arrow pointer must resolve
            for match in _BRAIN_POINTER_RE.finditer(line):
                target = match.group(1)
                if target == path.name or target in names or target in skill_names:
                    continue
                flag("dangling", path.name,
                     f"line {lineno}: → {target} resolves to no brain or skill file")
            # invariant 4 — collect the normalised rule lines for the cross-file pass
            normalised = line.strip().lower()
            if (
                len(normalised) >= BRAIN_DUP_MIN_LEN
                and not normalised.startswith("#")
                and not normalised.startswith("<!--")
                and not _BRAIN_STRUCTURE_RE.match(normalised)
            ):
                duplicated.setdefault(normalised, []).append((path.name, lineno))
        line_counts[path.name] = count
        if not owns_seen:
            flag("owns", path.name,
                 f"no `Owns:` header in the first {BRAIN_OWNS_WINDOW} lines")

    # --- invariant 1 — the size budget on the always-loaded file --------------------------
    agents_lines = line_counts.get("AGENTS.md")
    if agents_lines is not None and agents_lines > BRAIN_SIZE_LIMIT:
        flag("size", "AGENTS.md", f"{agents_lines} lines > {BRAIN_SIZE_LIMIT} budget")

    # --- invariant 4 — the cross-file pass: one concept, one home -------------------------
    # The VIOLATION is the cross-file repeat, so it is reported per FILE PAIR — a per-line
    # report would print sixty rows for one copied block and bury the signal in its own echo.
    pair_hits = {}
    for normalised, hits in duplicated.items():
        owners = sorted({name for name, _ in hits})
        if len(owners) < 2:
            continue
        pair = tuple(owners)
        entry = pair_hits.setdefault(pair, {"count": 0, "sample": normalised, "where": []})
        entry["count"] += 1
        entry["where"].extend(f"{name}:{lineno}" for name, lineno in hits)

    for pair, entry in sorted(pair_hits.items()):
        sample = entry["sample"]
        preview = sample if len(sample) <= 60 else sample[:57] + "…"
        first = entry["where"][0] if entry["where"] else ""
        flag("duplicate", " + ".join(pair),
             f"{entry['count']} normalised line(s) shared across files "
             f"(first {first}: {preview})")

    if json_out:
        print(json.dumps({
            "home": str(home),
            "files": len(files),
            "violations": violations,
            "ok": not violations,
        }, indent=2))
    elif violations:
        for violation in violations:
            print(f"  {violation['invariant'].upper():9s} {violation['file']}: {violation['detail']}")
        print(f"brain FAIL: {len(violations)} violation(s) over {len(files)} file(s) in {home}.")
    else:
        print(f"brain OK: size, owns, pointers and duplicates all hold "
              f"over {len(files)} file(s) in {home}.")
    return 1 if violations else 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-Lens Review Engine")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    p_init = subparsers.add_parser("init", help="Initialize a new review cycle")
    p_init.add_argument("cycle_id", help="Review cycle identifier (e.g. 20260917-c1)")

    p_lenses = subparsers.add_parser("lenses", help="List the lawful lens set (core + declared)")
    p_lenses.add_argument("--json", action="store_true", help="Output as JSON object")

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
    p_waive.add_argument("--by", default=None, help="Who took the waiver decision")

    p_status = subparsers.add_parser("status", help="Show cycle progress")
    p_status.add_argument("cycle_id", help="Cycle identifier")

    p_verify = subparsers.add_parser("verify", help="Census verification gate")
    p_verify.add_argument("cycle_id", help="Cycle identifier")

    p_compile = subparsers.add_parser("compile", help="Generate verdict template")
    p_compile.add_argument("cycle_id", help="Cycle identifier")

    subparsers.add_parser(
        "schema", help="Emit the state schema — the source of the shipped artifact"
    )

    p_cadence = subparsers.add_parser("cadence", help="Compute the cadence boundary stamp from a ledger")
    p_cadence.add_argument("--ledger", required=True, help="Path to the ledger JSONL")
    p_cadence.add_argument(
        "--every", type=int, default=CADENCE_DEFAULT_EVERY,
        help=f"Accepted version bumps required to fire (default {CADENCE_DEFAULT_EVERY})",
    )
    p_cadence.add_argument(
        "--write", dest="write_cycle", default=None,
        help="Record the stamp into this cycle's state",
    )
    p_cadence.add_argument("--json", action="store_true", help="Output the stamp as JSON")
    p_cadence.add_argument("--live", action="store_true",
                           help="Write today's ledger boundary into a FROZEN cycle, and say so")

    p_close = subparsers.add_parser("close", help="Close a cycle with an explicit terminal state")
    p_close.add_argument("cycle_id", help="Cycle identifier")
    p_close.add_argument("--status", default="COMPLETED", choices=LIFECYCLE_STATES)
    p_close.add_argument("--stamp", action="store_true", help="Recompute the cadence stamp at close")
    p_close.add_argument("--ledger", default=None, help="Ledger JSONL; required with --stamp")

    p_migrate = subparsers.add_parser(
        "migrate", help="Migrate a pre-v1 state file, leaving a pre-image behind"
    )
    p_migrate.add_argument("cycle_id", help="Cycle identifier")
    p_migrate.add_argument("--dry-run", action="store_true", help="Print the mapping, write nothing")

    p_intake = subparsers.add_parser(
        "intake", help="Read the cycle's input channels and report a named intake state"
    )
    p_intake.add_argument("cycle_id", help="Cycle identifier")
    p_intake.add_argument("--record", action="store_true",
                          help="Write the receipt index into the cycle state (read-only over member data)")
    p_intake.add_argument("--live", action="store_true",
                          help="Read today's bytes even on a FROZEN cycle, and say so")

    p_codify = subparsers.add_parser(
        "codify", help="Record an accepted finding with the carrier its disposition owes"
    )
    p_codify.add_argument("cycle_id", help="Cycle identifier")
    p_codify.add_argument("--finding", required=True, help="The accepted finding, in one line")
    p_codify.add_argument("--disposition", required=True, choices=CODIFICATION_DISPOSITIONS,
                          help="landed (owes --home) | routed (owes --home) | rejected (owes --reason)")
    p_codify.add_argument("--home", default=None, help="The file+section it landed in, or where it was routed")
    p_codify.add_argument("--reason", default=None, help="Why it was not fixed (required for `rejected`)")

    p_step0 = subparsers.add_parser(
        "step0", help="Recovery point: where a resumed reader stands, read from state alone"
    )
    p_step0.add_argument("cycle_id", help="Cycle identifier")
    p_step0.add_argument("--record", action="store_true",
                         help="Append the reading to step0_log (durable evidence)")

    p_brain = subparsers.add_parser(
        "brain", help="Mechanical brain leg (G4): four invariants over a profile's brain files"
    )
    p_brain.add_argument(
        "--home", required=True,
        help="Profile home holding the brain *.md files (e.g. ~/.opencrabs/profiles/ops)",
    )
    p_brain.add_argument("--json", action="store_true", help="Output as a JSON object")

    args = parser.parse_args()

    if args.subcommand == "init":
        return cmd_init(args.cycle_id)
    elif args.subcommand == "brief":
        return cmd_brief(args.lens, json_out=args.json)
    elif args.subcommand == "record":
        return cmd_record(args.cycle_id, args.lens, args.content)
    elif args.subcommand == "waive":
        return cmd_waive(args.cycle_id, args.lens, args.reason, by=args.by)
    elif args.subcommand == "lenses":
        return cmd_lenses(json_out=args.json)
    elif args.subcommand == "status":
        return cmd_status(args.cycle_id)
    elif args.subcommand == "verify":
        return cmd_verify(args.cycle_id)
    elif args.subcommand == "compile":
        return cmd_compile(args.cycle_id)
    elif args.subcommand == "schema":
        return cmd_schema()
    elif args.subcommand == "cadence":
        return cmd_cadence(args.ledger, args.every, args.write_cycle, args.json, args.live)
    elif args.subcommand == "close":
        return cmd_close(args.cycle_id, args.status, args.stamp, args.ledger)
    elif args.subcommand == "migrate":
        return cmd_migrate(args.cycle_id, args.dry_run)
    elif args.subcommand == "intake":
        return cmd_intake(args.cycle_id, args.record, args.live)
    elif args.subcommand == "step0":
        return cmd_step0(args.cycle_id, args.record)
    elif args.subcommand == "codify":
        return cmd_codify(args.cycle_id, args.finding, args.disposition, args.home, args.reason)
    elif args.subcommand == "brain":
        return cmd_brain(args.home, json_out=args.json)
    return 1


if __name__ == "__main__":
    sys.exit(main())
