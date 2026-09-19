#!/usr/bin/env python3
"""Gate: the template's copies of the gates must match the originals.

`TEMPLATE/tools/ledger.py` and `TEMPLATE/tests/*.py` are copies — a factory
bootstraps by copying the template, so the template has to carry them. But a
copy that drifts is the same defect the ledger exists to prevent: two versions
of one thing, and the one nobody reads is the one that is wrong.

So the copies are checked byte-for-byte against their originals.

This file is deliberately NOT copied into the template: it guards the pair, and
a copy of a pair-guard would need its own pair-guard.

Run:  python3 tests/test_template_sync.py
Exit: 0 in sync, 1 drifted.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PAIRS = [
    ("tools/ledger.py", "TEMPLATE/tools/ledger.py"),
    ("tools/ledger_declaration.py", "TEMPLATE/tools/ledger_declaration.py"),
    ("tools/field_predicate.py", "TEMPLATE/tools/field_predicate.py"),
    ("tests/gate_fixtures.py", "TEMPLATE/tests/gate_fixtures.py"),
    ("tests/gate_registry.py", "TEMPLATE/tests/gate_registry.py"),
    ("tests/test_gate_registration.py", "TEMPLATE/tests/test_gate_registration.py"),
    ("tests/test_gate_fixtures_closure.py", "TEMPLATE/tests/test_gate_fixtures_closure.py"),
    ("tests/test_ontology.py", "TEMPLATE/tests/test_ontology.py"),
    ("tests/test_ledger.py", "TEMPLATE/tests/test_ledger.py"),
    ("tests/test_rework.py", "TEMPLATE/tests/test_rework.py"),
    ("tests/test_single_writer.py", "TEMPLATE/tests/test_single_writer.py"),
    ("tests/test_ledger_schema.py", "TEMPLATE/tests/test_ledger_schema.py"),
    ("tools/hygiene.py", "TEMPLATE/tools/hygiene.py"),
    ("tools/audit.py", "TEMPLATE/tools/audit.py"),
    ("tools/roadmap.py", "TEMPLATE/tools/roadmap.py"),
    ("tools/telemetry.py", "TEMPLATE/tools/telemetry.py"),
    ("tools/review.py", "TEMPLATE/tools/review.py"),
    ("tests/test_review.py", "TEMPLATE/tests/test_review.py"),
    ("tests/test_law_structure.py", "TEMPLATE/tests/test_law_structure.py"),
    ("tests/test_hygiene_namespace.py", "TEMPLATE/tests/test_hygiene_namespace.py"),
    ("tests/test_docs_sync.py", "TEMPLATE/tests/test_docs_sync.py"),
    ("tests/test_audit_rates.py", "TEMPLATE/tests/test_audit_rates.py"),
    ("tests/test_hq_delegation.py", "TEMPLATE/tests/test_hq_delegation.py"),
    ("tests/test_template_integrity.py", "TEMPLATE/tests/test_template_integrity.py"),
    ("tests/test_hygiene_inflight.py", "TEMPLATE/tests/test_hygiene_inflight.py"),
    ("tests/test_close_board_recorded.py", "TEMPLATE/tests/test_close_board_recorded.py"),
    ("tests/test_ledger_commit_cites_no_rows.py", "TEMPLATE/tests/test_ledger_commit_cites_no_rows.py"),
    ("tests/test_commit_pathspec_law.py", "TEMPLATE/tests/test_commit_pathspec_law.py"),
    ("tests/test_criteria_count.py", "TEMPLATE/tests/test_criteria_count.py"),
    ("tests/test_roadmap_transition.py", "TEMPLATE/tests/test_roadmap_transition.py"),
    ("tests/test_board_intake_recorded.py", "TEMPLATE/tests/test_board_intake_recorded.py"),
    ("tools/patrol_host_state.py", "TEMPLATE/tools/patrol_host_state.py"),
    ("tests/test_patrol_host_state.py", "TEMPLATE/tests/test_patrol_host_state.py"),
    ("tests/test_score_artifact_sections.py", "TEMPLATE/tests/test_score_artifact_sections.py"),
    ("tests/test_duplicate_prose.py", "TEMPLATE/tests/test_duplicate_prose.py"),
    ("tests/test_ledger_no_shrink.py", "TEMPLATE/tests/test_ledger_no_shrink.py"),
    ("tests/ledger_boundary.py", "TEMPLATE/tests/ledger_boundary.py"),
    ("tests/test_close_row_revision.py", "TEMPLATE/tests/test_close_row_revision.py"),
    ("tests/test_score_gate_recorded.py", "TEMPLATE/tests/test_score_gate_recorded.py"),
    ("tests/test_subject_form.py", "TEMPLATE/tests/test_subject_form.py"),
    (
        "tests/test_rework_relative_revision.py",
        "TEMPLATE/tests/test_rework_relative_revision.py",
    ),
    ("tools/hooks/commit-msg", "TEMPLATE/tools/hooks/commit-msg"),
]


def main() -> int:
    drifted: list[str] = []
    for original, copy in PAIRS:
        a, b = REPO / original, REPO / copy
        if not a.is_file():
            drifted.append(f"{original}: missing")
            continue
        if not b.is_file():
            drifted.append(f"{copy}: missing — the template does not ship it")
            continue
        if a.read_bytes() != b.read_bytes():
            drifted.append(f"{copy} differs from {original}")

    if drifted:
        print("template drift:\n")
        for d in drifted:
            print(f"  {d}")
        print("\nRe-copy: cp <original> <copy> — then re-run this gate.")
        return 1

    print(f"template in sync: {len(PAIRS)} pair(s) byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
