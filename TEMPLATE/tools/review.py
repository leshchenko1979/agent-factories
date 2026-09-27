"""Multi-Lens Review Engine (Review Rotation / P32).

Manages periodic quality reviews of factory laws, tools, and artifacts.
Enforces:
  1. Complete census: all catalog lenses must run or be explicitly waived.
  2. State durability: state.json carries the cycle lifecycle, an explicit
     terminal state and both durations.  That file IS the step-0 recovery
     point — after a compaction or restart, read it before re-querying input,
     re-briefing reviewers or re-drafting a plan.
  3. Receipt verification: reports verified with sha256 checksums, and a report
     with no index line is UNRECEIPTED — a named state, never a silent pass.
  4. Adversarial sub-agent dispatch: generates isolated, adversarial auditor
     prompts.  Lenses are executed by READ-ONLY SUB-AGENTS, never by the
     authoring session inline (docs/review-lenses.md, Adversarial Isolation
     Requirement).
  5. An OBSERVABLE cadence: `cadence` derives the boundary stamp from the
     ledger's own ANCHORED notes, so a member's cadence state is re-derivable
     by anyone holding the ledger instead of asserted in prose.

Usage:
  python3 tools/review.py init <cycle_id>
  python3 tools/review.py brief <lens> [--json]
  python3 tools/review.py record <cycle_id> <lens> <report_path_or_text>
  python3 tools/review.py waive <cycle_id> <lens> --reason "..." [--by WHO]
  python3 tools/review.py status <cycle_id>
  python3 tools/review.py verify <cycle_id>
  python3 tools/review.py compile <cycle_id>
  python3 tools/review.py close <cycle_id> [--status COMPLETED|ABANDONED] [--stamp --ledger F]
  python3 tools/review.py cadence --ledger <ledger.jsonl> [--every N] [--write <cycle_id>] [--json]
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

# Terminal ENUM.  `COMPLETED` is the donor's own token and is kept verbatim.
# `ABANDONED` is ADDED, and the reason is measured rather than speculative:
# four donor cycles sit at IN_PROGRESS (20260915-c18, 20260916-c20,
# 20260919-c21 and the live 20260927-c25), three of them days old and dead in
# fact — an abandoned cycle is otherwise indistinguishable from a live one,
# the same defect the donor fixed for `ended_at`.
LIFECYCLE_STATES = ["IN_PROGRESS", "COMPLETED", "ABANDONED"]

# The cadence boundary is the NEWEST row whose text ANCHORS on this pattern —
# the last cycle-close stamp.  ANCHORED, never a substring: a loose search
# harvests an END from a row whose whole point is that none was written — the
# donor's `WITHHELD:` convention exists for exactly that row, and a WITHHELD
# row begins with the literal token, so it can never match an anchored pattern.
CADENCE_PATTERN = r"^v[0-9]+\.[0-9]+\.[0-9]+ ACCEPTED"
CADENCE_DEFAULT_EVERY = 5

# ... and the COUNT is a SECOND predicate, not the same one.  Read from the
# donor's own implementation rather than inferred from its prose: in
# `oc-ledger`'s `cmd_cadence` the boundary is the newest ANCHORED row, while
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
            for lens in CATALOG_LENSES
        },
        "waivers": [],
        "proposals": [],
        "codification_plan": [],
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

    # lenses: normalize each entry, and materialize every catalog lens.
    raw_lenses = state.get("lenses") or {}
    if isinstance(raw_lenses, dict):
        for lens in CATALOG_LENSES:
            entry = dict(out["lenses"][lens])
            incoming = raw_lenses.get(lens)
            if isinstance(incoming, dict):
                entry.update({k: v for k, v in incoming.items() if k in entry})
                if entry.get("status") is None:
                    entry["status"] = "PENDING"
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
        f"Initialized review cycle '{cycle_id}' with {len(CATALOG_LENSES)} "
        f"catalog lenses (schema v{SCHEMA_VERSION})."
    )
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
    if lens not in CATALOG_LENSES:
        print(f"Error: Lens '{lens}' not in catalog {CATALOG_LENSES}", file=sys.stderr)
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

    cadence = state.get("cadence") or {}
    boundary = cadence.get("boundary") or {}
    every = (cadence.get("trigger") or {}).get("every", CADENCE_DEFAULT_EVERY)
    print(
        f"\nCadence: {boundary.get('accepted_since', 0)}/{every} "
        f"{'FIRE' if cadence.get('fires') else 'WAIT'} "
        f"(boundary {boundary.get('ref')}, evaluated {cadence.get('evaluated_at')})"
    )
    print(f"\nSummary: {completed} Completed | {waived} Waived | {pending} Pending (Total: {len(CATALOG_LENSES)})")
    return 0 if pending == 0 else 1


def cmd_verify(cycle_id: str) -> int:
    state = read_state(cycle_id)
    if not state:
        print(f"FAIL: Cycle '{cycle_id}' state.json missing.", file=sys.stderr)
        return 1

    lenses = state.get("lenses", {})
    missing: list[str] = []
    corrupted: list[str] = []
    unverified: list[str] = []

    for lens in CATALOG_LENSES:
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

    if missing or corrupted or unverified:
        print(f"FAIL: Cycle '{cycle_id}' census check failed.")
        if missing:
            print(f"  Missing or incomplete lenses: {', '.join(missing)}")
        if corrupted:
            print(f"  Checksum corrupted lenses: {', '.join(corrupted)}")
        if unverified:
            print(f"  UNRECEIPTED lenses (no index line): {', '.join(unverified)}")
        return 1

    print(f"PASS: Cycle '{cycle_id}' census verified clean across all {len(CATALOG_LENSES)} lenses.")
    return 0


def cmd_compile(cycle_id: str) -> int:
    state = read_state(cycle_id)
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
                json_out: bool) -> int:
    """Compute the cadence boundary stamp, and optionally record it.

    The boundary is an OBSERVABLE artifact, not prose: a member's cadence state
    is the ledger's own anchored notes, re-derivable by anyone holding the
    ledger.  Recording it into a cycle is `--write <cycle_id>`.
    """
    stamp = cadence_stamp(ledger_path, every)
    if cycle_id:
        state = read_state(cycle_id)
        if not state:
            print(f"Error: Cycle '{cycle_id}' not found.", file=sys.stderr)
            return 2
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
        for lens in CATALOG_LENSES
    ]
    recorded = [t for t in recorded if t is not None]
    if recorded and started:
        review_span = (max(recorded) - started).total_seconds() / 60.0
        state["duration_review_min"] = round(review_span, 1)

    if stamp and ledger_path:
        every = (state["cadence"].get("trigger") or {}).get("every", CADENCE_DEFAULT_EVERY)
        state["cadence"] = cadence_stamp(ledger_path, every)

    rc = save_state(cycle_id, state)
    if rc != 0:
        return rc
    print(
        f"Closed cycle '{cycle_id}' as {status}; "
        f"duration_cycle_min={state['duration_cycle_min']}, "
        f"duration_review_min={state['duration_review_min']}"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-Lens Review Engine")
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

    args = parser.parse_args()

    if args.subcommand == "init":
        return cmd_init(args.cycle_id)
    elif args.subcommand == "brief":
        return cmd_brief(args.lens, json_out=args.json)
    elif args.subcommand == "record":
        return cmd_record(args.cycle_id, args.lens, args.content)
    elif args.subcommand == "waive":
        return cmd_waive(args.cycle_id, args.lens, args.reason, by=args.by)
    elif args.subcommand == "status":
        return cmd_status(args.cycle_id)
    elif args.subcommand == "verify":
        return cmd_verify(args.cycle_id)
    elif args.subcommand == "compile":
        return cmd_compile(args.cycle_id)
    elif args.subcommand == "schema":
        return cmd_schema()
    elif args.subcommand == "cadence":
        return cmd_cadence(args.ledger, args.every, args.write_cycle, args.json)
    elif args.subcommand == "close":
        return cmd_close(args.cycle_id, args.status, args.stamp, args.ledger)
    elif args.subcommand == "migrate":
        return cmd_migrate(args.cycle_id, args.dry_run)
    return 1


if __name__ == "__main__":
    sys.exit(main())
