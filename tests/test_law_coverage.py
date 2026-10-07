#!/usr/bin/env python3
r"""Gate: every declared best practice has an upholding gate (P29).

Principle P29 states:
  "Every law needs an active process or mechanical gate upholding it.
   A rule without an upholding mechanism is dead text."

This test parses docs/best-practices.md, extracts all declared best practices (P1..PN),
and asserts that each practice is mapped to at least one mechanical test file, tool gate,
or active process validator.

PREDICATE, stated with its count (measured 2026-09-19 at 9c2ed02: 35 loose = 35 strict,
0 malformed): a practice is DECLARED by a line matching `^##\s+(P\d+)\b` (loose extract),
and a declared practice is WELL-FORMED only when that same heading continues `\s+—` (the
em-dash U+2014 separator). Extraction is LOOSE and the separator is ASSERTED, never the
reverse: a heading written with a hyphen (`## P34 - title`) is not extracted AT ALL by the
strict pattern, so its PRACTICE_GATES entry is never consulted and the law silently stops
being checked while this gate still reports clean. That was #62 — the same fail-open family
as #58.

The predicate is BIDIRECTIONAL, and that is what makes the former
`assert len(declared_practices) >= 32` floor unnecessary. Forward: every declared practice
must be mapped in PRACTICE_GATES. Reverse: every key in PRACTICE_GATES must be a declared
practice. The floor was the only vacuity guard, and a floor is the wrong FORM — it goes
stale and carries slack (>= 32 against 34 declared is exactly what let #62's drift pass
unnoticed). The reverse direction carries no number: if the extraction returns nothing,
every key reads as undeclared and the gate REDs naming all of them; if a single heading
vanishes, it REDs naming that one. The two sets were measured EQUAL (35 == 35) when this
landed, so the reverse check introduces zero false reds.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Explicit mapping of Best Practice ID -> upholding mechanism (test file, tool, or mechanical check)
PRACTICE_GATES: dict[str, list[str]] = {
    "P1": ["tests/test_ontology.py", "skills/meta-factory/SKILL.md"],  # Process law is a versioned file
    "P2": ["TEMPLATE/roles/hq.md", "TEMPLATE/roles/triage.md", "TEMPLATE/roles/worker.md"],  # One file per role
    "P3": ["tools/audit.py", "tools/ledger.py", "tests/test_board_intake_recorded.py"],  # Issue board / ledger is task list
    "P4": ["tests/test_session_bindings.py", "skills/meta-factory/SKILL.md"],  # Direct message to session UUID
    "P5": ["evidence/ledger.jsonl"],  # Named place carries state
    "P6": ["TEMPLATE/roles/hq.md", "skills/meta-factory/SKILL.md", "tests/test_hq_delegation.py"],  # HQ works on process, not in it
    # P7's upholding mechanism is TWO-PART, and both halves are needed (issue #54). The
    # PREDICATE (`tests/test_cron_thinness.py`) is the mechanical half: a pure function
    # over a LIST of cron rows that flags a row whose wake route is neither a `session:`
    # target nor a notify in its prompt. It is pure because cron state lives in the
    # harness database, not in the tree, so a gate reading that table would red in every
    # bootstrapped factory that has no such table (#68's failure). The PROCESS half is the
    # measurement run: it verifies the pacemaker crons are thin and the RESULT is a
    # required artifact section, which tests/test_score_artifact_sections.py asserts. It
    # mapped to tools/hygiene.py before — a file that declares its own scope as Process 4 and
    # never reads a cron row, which passed because the only check here is that the target
    # EXISTS. A file that exists and implements nothing satisfied it completely (#69, #54).
    "P7": ["tests/test_cron_thinness.py", "tests/test_score_artifact_sections.py", "docs/measurement-procedure.md"],
    "P8": ["tests/test_ontology.py"],  # Codify vocabulary with a test
    "P9": ["tools/audit.py"],  # Mechanical gates beat prose judgment
    "P10": ["tests/test_template_sync.py", "tests/test_ledger_schema.py"],  # Verification in repo instruction
    "P11": ["tools/ledger.py", "tests/test_single_writer.py", "tests/test_ledger_no_shrink.py"],  # Single writer per surface (flock)
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
    # P28 describes the SAME OBJECT as P7 — a periodic process driven by a thin nudging
    # cron — and carried the same defect one level worse: BOTH of its mapped targets were
    # files that never read a cron row. tools/hygiene.py declares its own scope as Process 4, and
    # `grep -c 'cron\|deliver_to\|set_goal' tools/audit.py` returned 0. It now shares P7's
    # pair: the pure predicate for the wake route, and the measurement run for the live
    # check. A mapping to a file that implements nothing is dead text (P29, #54).
    "P28": ["tests/test_cron_thinness.py", "tests/test_score_artifact_sections.py", "docs/measurement-procedure.md"],
    "P29": ["tests/test_law_coverage.py"],  # Every law needs active process or gate (this test)
    "P30": ["evidence/rework.md", "tests/test_rework.py"],  # Autonomous incident remediation
    "P31": ["docs/processes.md", "TEMPLATE/roles/hq.md"],  # Every process has exactly one named owner
    "P32": ["tools/review.py", "tests/test_review.py", "docs/review-lenses.md"],  # Multi-lens review rotation
    "P33": ["docs/methodology/04-harness-binding.md", "TEMPLATE/SKILL.md.tmpl", "skills/meta-factory/SKILL.md"],  # Context manifest curation
    "P34": ["docs/methodology/01-llm-weakness-counters.md", "TEMPLATE/AGENTS.md.tmpl"],  # Mirror test: diagnose mechanism before counter
    "P35": ["tests/test_gate_fixtures_closure.py", "tests/gate_fixtures.py"],  # A fixture must model the tree its tool runs in
    "P36": ["registry/fleet.json", "tests/test_registry.py", "tests/gate_registry.py"],  # A box-describing surface is declared, and its gate must pass where it is copied
    # P37's three clauses each name their own mechanism rather than a shared one: the
    # commit arm is the index-reading hook and the gate whose synthetic probes prove it
    # reads the index (a working-tree read would pass the one-sided case), the live-state
    # arm is the patrol runner plus the offline gate over its logic, and the render arm is
    # the generator paired with the gate that compares its output. All five ship in
    # TEMPLATE/, so the mapping holds in a bootstrapped factory.
    "P37": ["tests/test_commit_pair_hook.py", "tools/hooks/pre-commit", "tools/patrol_host_state.py", "tests/test_patrol_host_state.py", "tools/registry_render.py"],  # A commit check reads the index; a live-state check says so
    # P38's three targets are the DETECTORS and the shared read, not a single shared
    # gate: `tests/test_gate_registration.py` compares the argv a selector rebuilds
    # against the argv the audit actually runs (#436), `tests/test_rework_declared_landed.py`
    # resolves a close row's declaration against the Subject its entry landed (#438), and
    # `tools/field_predicate.py` is the ONE positional read of a trailer field, so a
    # consumer reads the artifact rather than re-deriving it per reader. All three ship in
    # TEMPLATE/, so the mapping holds in a bootstrapped factory (P36).
    "P38": ["tools/field_predicate.py", "tests/test_rework_declared_landed.py", "tests/test_gate_registration.py"],  # Read the artifact, never a stand-in that resembles it
}


def test_all_declared_best_practices_have_upholding_gates() -> None:
    best_practices_file = REPO_ROOT / "docs" / "best-practices.md"
    assert best_practices_file.is_file(), f"Missing {best_practices_file}"

    content = best_practices_file.read_text(encoding="utf-8")
    # Loose extract, then assert the separator. A malformed heading is REPORTED by
    # name rather than skipped, because a skipped heading is a law this gate cannot see.
    declared_practices = re.findall(r"^##\s+(P\d+)\b", content, re.MULTILINE)
    malformed = [
        p
        for p in declared_practices
        if not re.search(rf"^##\s+{p}\s+—", content, re.MULTILINE)
    ]
    assert not malformed, f"law heading lacks the em-dash separator: {malformed}"

    # REVERSE DIRECTION. Every mapping key must be a DECLARED practice. This is what makes
    # the dropped floor unnecessary, and it is a stronger guard than the floor ever was:
    # if the extraction returns nothing, every key is undeclared and the gate REDs naming
    # all of them, where the floor would have passed it. If one heading vanishes, the gate
    # REDs naming that one. Neither case needs a magic number that can go stale.
    declared_set = set(declared_practices)
    dead_entries = sorted(p for p in PRACTICE_GATES if p not in declared_set)
    assert not dead_entries, (
        "PRACTICE_GATES maps practices that docs/best-practices.md does not declare "
        f"(a heading that vanished, or an extraction that failed): {dead_entries}"
    )

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
    print(
        f"ALL BEST PRACTICE LAWS (P1..PN) HAVE VERIFIED UPHOLDING GATES "
        f"({len(PRACTICE_GATES)} mapped)."
    )
