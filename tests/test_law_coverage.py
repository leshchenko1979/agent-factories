#!/usr/bin/env python3
"""Tests for Best Practice Law-to-Gate Coverage (P29).

Principle P29 states:
  "Every law needs an active process or mechanical gate upholding it.
   A rule without an upholding mechanism is dead text."

This test parses docs/best-practices.md, extracts all declared best practices (P1..PN),
and asserts that each practice is mapped to at least one mechanical test file, tool gate,
or active process validator.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Explicit mapping of Best Practice ID -> upholding mechanism (test file, tool, or mechanical check)
PRACTICE_GATES: dict[str, list[str]] = {
    "P1": ["tests/test_ontology.py", "skills/meta-factory/SKILL.md"],  # Process law is a versioned file
    "P2": ["TEMPLATE/roles/hq.md", "TEMPLATE/roles/triage.md", "TEMPLATE/roles/worker.md"],  # One file per role
    "P3": ["tools/audit.py", "tools/ledger.py"],  # Issue board / ledger is task list
    "P4": ["tests/test_session_bindings.py", "skills/meta-factory/SKILL.md"],  # Direct message to session UUID
    "P5": ["evidence/ledger.jsonl"],  # Named place carries state
    "P6": ["TEMPLATE/roles/hq.md", "skills/meta-factory/SKILL.md", "tests/test_hq_delegation.py"],  # HQ works on process, not in it
    "P7": ["tools/hygiene.py"],  # Cron is thin pacemaker trigger
    "P8": ["tests/test_ontology.py"],  # Codify vocabulary with a test
    "P9": ["tools/audit.py"],  # Mechanical gates beat prose judgment
    "P10": ["tests/test_template_sync.py", "tests/test_ledger_schema.py"],  # Verification in repo instruction
    "P11": ["tools/ledger.py", "tests/test_single_writer.py"],  # Single writer per surface (flock)
    "P12": ["tools/ledger.py", "evidence/ledger.jsonl"],  # Every task leaves a trace
    "P13": ["evidence/ledger.jsonl"],  # Durable state off working box
    "P14": ["TEMPLATE/roles/hq.md"],  # Approval gates for irreversible acts
    "P15": ["tests/test_rework.py"],  # Never loosen the gate
    "P16": ["skills/meta-factory/SKILL.md"],  # Dispatch directly, no relay hops
    "P17": ["tests/test_ledger_schema.py"],  # Claims about state need same-turn receipt
    "P18": ["skills/meta-factory/SKILL.md"],  # Surface change does not move delivery paths
    "P19": ["skills/meta-factory/SKILL.md"],  # Boundaries named; meta-factory advises
    "P20": ["tools/audit.py"],  # Measure the machine, not only output
    "P21": ["TEMPLATE/README.md"],  # Separate requirements from mechanics (add-ons)
    "P22": ["tools/audit.py", "tools/ledger.py"],  # Measure factory on cadence
    "P23": ["ONTOLOGY.md", "tests/test_ontology.py"],  # Plain language for operator
    "P24": ["skills/meta-factory/SKILL.md"],  # Substrate defect goes to substrate owner
    "P25": ["skills/meta-factory/SKILL.md"],  # Factory rules live in own skill
    "P26": ["tools/audit.py"],  # Count acts that still need operator
    "P27": ["tools/audit.py", "TEMPLATE/roles/triage.md"],  # Automated task assignment & monitoring
    "P28": ["tools/hygiene.py", "tools/audit.py"],  # Periodic processes driven by thin cron
    "P29": ["tests/test_law_coverage.py"],  # Every law needs active process or gate (this test)
    "P30": ["evidence/rework.md", "tests/test_rework.py"],  # Autonomous incident remediation
    "P31": ["docs/processes.md", "TEMPLATE/roles/hq.md"],  # Every process has exactly one named owner
    "P32": ["tools/review.py", "tests/test_review.py", "docs/review-lenses.md"],  # Multi-lens review rotation
    "P33": ["docs/methodology/04-harness-binding.md", "TEMPLATE/SKILL.md.tmpl", "skills/meta-factory/SKILL.md"],  # Context manifest curation
    "P34": ["docs/methodology/01-llm-weakness-counters.md", "TEMPLATE/AGENTS.md.tmpl"],  # Mirror test: diagnose mechanism before counter
}


def test_all_declared_best_practices_have_upholding_gates() -> None:
    best_practices_file = REPO_ROOT / "docs" / "best-practices.md"
    assert best_practices_file.is_file(), f"Missing {best_practices_file}"

    content = best_practices_file.read_text(encoding="utf-8")
    declared_practices = re.findall(r"^##\s+(P\d+)\s+—", content, re.MULTILINE)
    assert len(declared_practices) >= 32, f"Expected at least 32 practices, found {len(declared_practices)}"

    missing_gates: list[str] = []
    unverified_targets: list[str] = []

    for p_id in declared_practices:
        if p_id not in PRACTICE_GATES:
            missing_gates.append(p_id)
            continue

        gates = PRACTICE_GATES[p_id]
        if not gates:
            missing_gates.append(f"{p_id} (empty gate list)")
            continue

        for target in gates:
            target_path = REPO_ROOT / target
            if not target_path.exists():
                unverified_targets.append(f"{p_id} -> {target} does not exist on disk")

    assert not missing_gates, f"Best practices missing mechanical gate mapping: {missing_gates}"
    assert not unverified_targets, f"Mapped gate targets do not exist on disk: {unverified_targets}"


if __name__ == "__main__":
    test_all_declared_best_practices_have_upholding_gates()
    print("ALL BEST PRACTICE LAWS (P1..PN) HAVE VERIFIED UPHOLDING GATES.")


if __name__ == "__main__":
    test_all_declared_best_practices_have_upholding_gates()
    print("ALL BEST PRACTICE LAWS (P1..PN) HAVE VERIFIED UPHOLDING GATES.")
