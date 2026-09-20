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
    ("tests/rework_table.py", "TEMPLATE/tests/rework_table.py"),
    ("tests/test_rework_declared_landed.py", "TEMPLATE/tests/test_rework_declared_landed.py"),
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
    ("tests/test_rework_relative_revision.py", "TEMPLATE/tests/test_rework_relative_revision.py"),
    ("tests/test_claim_gap_declared.py", "TEMPLATE/tests/test_claim_gap_declared.py"),
    ("tools/hooks/commit-msg", "TEMPLATE/tools/hooks/commit-msg"),
    # The commit-time index check (#92). The hook refuses a staged set that names
    # one side of a declared pair without its twin, and its table is THIS one — it
    # loads `PAIRS` from this file rather than keeping a copy, so a pair added here
    # is enforced at commit time with no second edit.
    ("tools/hooks/pre-commit", "TEMPLATE/tools/hooks/pre-commit"),
    # The factory registry. Its three tools and two gates ship whole: a
    # bootstrapped factory declares its own fleet in `registry/fleet.json` and
    # gets the same renderer, the same drift gate and the same attest pacemaker.
    # `registry/fleet.example.json` ships because the loader's own error message
    # names it — an error that points at a file nobody ships is a dead end.
    ("registry/fleet.example.json", "TEMPLATE/registry/fleet.example.json"),
    ("tools/registry.py", "TEMPLATE/tools/registry.py"),
    ("tools/registry_render.py", "TEMPLATE/tools/registry_render.py"),
    ("tools/registry_attest.py", "TEMPLATE/tools/registry_attest.py"),
    ("tests/test_registry.py", "TEMPLATE/tests/test_registry.py"),
    ("tests/test_registry_render.py", "TEMPLATE/tests/test_registry_render.py"),
    ("tests/test_ledger_close_preflight.py", "TEMPLATE/tests/test_ledger_close_preflight.py"),
    # The telemetry-reader registry gate (#99). It classifies the tools the template
    # SHIPS, so its allow-list is structural and must travel byte-identically with the
    # code it describes — a factory that adds its own writer edits its own copy.
    ("tests/test_telemetry_reader_registry.py", "TEMPLATE/tests/test_telemetry_reader_registry.py"),
    # The commit-time pair check's own gate, and the shared installation predicate it
    # reads. The predicate is a library, not a gate — it declares nothing — but it is
    # paired because both hook gates import it and a factory must inherit the same
    # implementation rather than a drifting second copy.
    ("tests/hook_installation.py", "TEMPLATE/tests/hook_installation.py"),
    ("tests/test_commit_pair_hook.py", "TEMPLATE/tests/test_commit_pair_hook.py"),
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
