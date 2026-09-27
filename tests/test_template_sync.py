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
Exit: 0 in sync and portable; 1 on drift or on a non-portable literal.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# A hex token of at least 12 characters — a git object name, full or abbreviated.
# Matched inside a paired file it is a literal that travels into every factory that
# copies this tree, where it resolves to nothing.
#
# The FLOOR is MEASURED, not chosen. Over the 58 paired files, every hex token that
# resolves in THIS repository is 7 or 8 characters (13 at length 7, 4 at length 8), and
# every one of them is a PROSE CITATION of this repository's history inside a comment or
# a docstring — a fact about this tree, not a value the file carries. Nothing at length 9
# to 39 resolves at all, while the widths a fixture literal actually used here are 12
# (`9552947a985b`) and 40. A floor of 12 therefore catches both observed widths and
# touches none of the citations, where a {40} form provably MISSES the 12-character case
# that existed.
#
# THE BOUND, stated rather than left implied: a RESOLVING literal of 7 to 11 characters
# would pass this leg. The floor cannot go lower without firing on the citations above,
# so what it buys is the class at the widths a fixture literal has actually used, and not
# below them. A predicate that states its population and hides its floor is the defect
# this comment exists to avoid.
SHA = re.compile(r"\b[0-9a-f]{12,40}\b")


def _resolves(sha: str) -> bool:
    """True when `sha` names a commit object in THIS repository."""
    return (
        subprocess.run(
            ["git", "-C", str(REPO), "cat-file", "-e", f"{sha}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def portability_problems() -> tuple[list[str], int, int]:
    """`(problems, pairs_scanned, literals_examined)` over every declared pair.

    Byte-identity is necessary but NOT sufficient, and this leg is the half the byte
    comparison cannot reach. The twins are the same file in two trees that differ BY
    DESIGN — this factory's object database and a bootstrapped factory's — so a literal
    in a paired file that resolves HERE and nowhere THERE makes the file's behaviour a
    property of the tree rather than of the file. The failure is silent and inverted: a
    probe asserting a token resolves passes here and fails on the day the factory is
    born, while a probe asserting it does NOT resolve fails here and passes there.

    The predicate is therefore RESOLUTION in this repository, and the remedy is a value
    that resolves in neither tree. The counts are returned rather than kept so the
    population examined is PRINTED — a clean verdict over an unstated population is
    indistinguishable from one that examined nothing.
    """
    problems: list[str] = []
    scanned = 0
    examined = 0
    for original, _ in PAIRS:
        a = REPO / original
        if not a.is_file():
            continue  # already reported as drift; this leg does not duplicate it
        scanned += 1
        try:
            text = a.read_text()
        except UnicodeDecodeError:
            continue  # a binary pair carries no literals to read
        for sha in sorted(set(SHA.findall(text))):
            examined += 1
            if _resolves(sha):
                problems.append(
                    f"{original} carries {sha}, which RESOLVES in this repository — in "
                    f"the factory this file ships to it will not, so the pair is not "
                    f"portable; use a value that resolves in neither tree"
                )
    return problems, scanned, examined

PAIRS = [
    ("tools/ledger.py", "TEMPLATE/tools/ledger.py"),
    ("tools/ledger_declaration.py", "TEMPLATE/tools/ledger_declaration.py"),
    # The DERIVED index (owner order 2026-09-27). It pairs because it is the same kind of
    # instrument as the ledger itself: a member that took the tool without its gate would
    # carry a derived view nothing proves agrees with the text, and one that took the gate
    # without the tool would run probes that cannot pass.
    ("tools/ledger-index.py", "TEMPLATE/tools/ledger-index.py"),
    ("tests/test_ledger_index.py", "TEMPLATE/tests/test_ledger_index.py"),
    ("tools/field_predicate.py", "TEMPLATE/tools/field_predicate.py"),
    # Added with plan 2646d31a task 6. The pin reader is loaded BY PATH from
    # tools/patrol_host_state.py (KIT_PIN), so an unpaired copy is the #171 shape again: the
    # runner resolves tools/ beside itself, and a tree carrying only the TEMPLATE half would
    # fail at load rather than at import.
    ("tools/kit_pin.py", "TEMPLATE/tools/kit_pin.py"),
    ("tools/reconstruction.py", "TEMPLATE/tools/reconstruction.py"),
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
    # Added with its registration (issue #94): audit.py imports this module, so it
    # pairs like every other tool. A factory that has taken no measurements ships
    # `registry/gates.example.json` and no `gates.json`, so the reader takes the
    # declared fallback rather than REDing where it is copied.
    ("tools/gate_budget.py", "TEMPLATE/tools/gate_budget.py"),
    ("tools/roadmap.py", "TEMPLATE/tools/roadmap.py"),
    ("tools/telemetry.py", "TEMPLATE/tools/telemetry.py"),
    ("tools/review.py", "TEMPLATE/tools/review.py"),
    ("tests/test_review.py", "TEMPLATE/tests/test_review.py"),
    ("tests/test_law_structure.py", "TEMPLATE/tests/test_law_structure.py"),
    ("tests/test_hygiene_namespace.py", "TEMPLATE/tests/test_hygiene_namespace.py"),
    ("tests/test_docs_sync.py", "TEMPLATE/tests/test_docs_sync.py"),
    ("tests/test_audit_rates.py", "TEMPLATE/tests/test_audit_rates.py"),
    # Added with its registration (issue #145): the gate drives `tools/audit.py`, which is a
    # paired file, so it is only meaningful where BOTH ship — a factory that took the tool's
    # in-flight guard without the gate proving it would carry a guard nothing checks, and one
    # that took the gate without the tool would run probes that cannot pass.
    ("tests/test_audit_inflight_guard.py", "TEMPLATE/tests/test_audit_inflight_guard.py"),
    # Added with its registration (issue #74): the gate reads the harness binding's own
    # variable table and probes the tool for each name it finds, so it is only meaningful
    # where BOTH artifacts ship — and both do, byte-paired (`docs/**` by
    # `tests/test_docs_sync.py`, `tools/ledger.py` by the entry above). A factory that took
    # the binding without the gate would carry a law naming an isolation seam nothing proves.
    ("tests/test_binding_mechanism_exists.py", "TEMPLATE/tests/test_binding_mechanism_exists.py"),
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
    ("tools/publish.py", "TEMPLATE/tools/publish.py"),
    ("tests/test_publish.py", "TEMPLATE/tests/test_publish.py"),
    ("tests/test_patrol_host_state.py", "TEMPLATE/tests/test_patrol_host_state.py"),
    ("tests/test_score_artifact_sections.py", "TEMPLATE/tests/test_score_artifact_sections.py"),
    ("tests/test_duplicate_prose.py", "TEMPLATE/tests/test_duplicate_prose.py"),
    ("tests/test_ledger_no_shrink.py", "TEMPLATE/tests/test_ledger_no_shrink.py"),
    ("tests/ledger_boundary.py", "TEMPLATE/tests/ledger_boundary.py"),
    ("tests/test_close_row_revision.py", "TEMPLATE/tests/test_close_row_revision.py"),
    ("tests/test_score_gate_recorded.py", "TEMPLATE/tests/test_score_gate_recorded.py"),
    ("tests/test_insights_gate_recorded.py", "TEMPLATE/tests/test_insights_gate_recorded.py"),
    ("tests/test_subject_form.py", "TEMPLATE/tests/test_subject_form.py"),
    ("tests/test_rework_relative_revision.py", "TEMPLATE/tests/test_rework_relative_revision.py"),
    ("tests/test_reconstructed_claim_declared.py", "TEMPLATE/tests/test_reconstructed_claim_declared.py"),
    # The commit-session-trailer gate (issue #138, ruling n=928). Paired for the same
    # reason every other gate is: the hook it pins ships from TEMPLATE, so a factory
    # that takes the hook must take its pin too.
    ("tests/test_commit_session_trailer.py", "TEMPLATE/tests/test_commit_session_trailer.py"),
    ("tests/test_ledger_identity.py", "TEMPLATE/tests/test_ledger_identity.py"),
    ("tools/hooks/commit-msg", "TEMPLATE/tools/hooks/commit-msg"),
    # The commit-time index check (#92). The hook refuses a staged set that names
    # one side of a declared pair without its copy, and its table is THIS one — it
    # loads `PAIRS` from this file rather than keeping a copy, so a pair added here
    # is enforced at commit time with no second edit.
    ("tools/hooks/pre-commit", "TEMPLATE/tools/hooks/pre-commit"),
    # The factory registry. Its three tools and two gates ship whole: a
    # bootstrapped factory declares its own fleet in `registry/fleet.json` and
    # gets the same renderer, the same drift gate and the same attest pacemaker.
    # `registry/fleet.example.json` ships because the loader's own error message
    # names it — an error that points at a file nobody ships is a dead end.
    ("registry/fleet.example.json", "TEMPLATE/registry/fleet.example.json"),
    # The gate-budget manifest's own example (#94, ruling n=744). Same reason as the
    # fleet example above and the same shape of pair: a bootstrapped factory reads the
    # SHAPE from here and writes its own `registry/gates.json` from measurements of its
    # own box, so the example ships whole and byte-identically at both paths.
    ("registry/gates.example.json", "TEMPLATE/registry/gates.example.json"),
    # Added with plan 2646d31a task 6. The kit PIN -- the manifest a factory vendors at
    # the version it ported, so its own gate judges its own declaration instead of the
    # template's working tree. Same shape as the two examples above: the SHAPE ships whole
    # and byte-identically at both paths, and a factory writes its own `registry/kit.json`
    # by running the generator against its tree.
    ("registry/kit.example.json", "TEMPLATE/registry/kit.example.json"),
    ("tools/registry.py", "TEMPLATE/tools/registry.py"),
    ("tools/registry_render.py", "TEMPLATE/tools/registry_render.py"),
    ("tools/registry_attest.py", "TEMPLATE/tools/registry_attest.py"),
    ("tests/test_registry.py", "TEMPLATE/tests/test_registry.py"),
    # Added with plan 2646d31a task 5. The gate ships byte-paired into TEMPLATE alongside the
    # tool it exercises, so an unpaired copy is the #107 class: a factory could keep the file
    # and lose the copy, and nothing would say so.
    ("tests/test_registry_attest.py", "TEMPLATE/tests/test_registry_attest.py"),
    ("tests/test_registry_render.py", "TEMPLATE/tests/test_registry_render.py"),
    # Added with plan 2646d31a task 8 (2026-09-25). The member-side pin gate: a factory
    # judges ITSELF against the pin IT vendored, so its verdict moves only when its own tree
    # diverges from its own declaration. It ships, so the copy is held here.
    ("tests/test_kit_pin.py", "TEMPLATE/tests/test_kit_pin.py"),
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
    # The skill-version contract gate (#71, ruling n=455). It DISCOVERS the law file rather
    # than hardcoding the slug, so it ships in the template and every bootstrapped factory
    # inherits it — the discovery leg is what makes a byte-identical copy meaningful here:
    # a factory's own `skills/<slug>/SKILL.md` is judged by the same file.
    ("tests/test_skill_version_contract.py", "TEMPLATE/tests/test_skill_version_contract.py"),
    # The cron-thinness predicate (#54, P7 + P28). It is PURE over a LIST of cron rows
    # and probeable with synthetic ones, which is what makes it portable: a bootstrapped
    # factory has its own `cron_jobs` table, not this one, and the file never reads it.
    # Paired so every factory inherits the same predicate rather than a drifting copy,
    # and REQUIRED in `gate_registry.REQUIRED_GATES` for the same reason.
    ("tests/test_cron_thinness.py", "TEMPLATE/tests/test_cron_thinness.py"),
    # The close-telemetry provenance gate (#130). Paired for the same reason as the
    # cron-thinness predicate above, and with one property of its own that makes the copy
    # load-bearing: it carries NO date. Its boundary is a DECLARED FACTORY PARAMETER read
    # from `docs/ledger-invariants.json`, so a bootstrapped factory inherits a gate that
    # judges ITS OWN ledger from ITS OWN declaration — a hardcoded boundary here would RED
    # in the tree it ships to (#76's class, P35). REQUIRED in
    # `gate_registry.REQUIRED_GATES`, because its boundary is FORWARD-ONLY: a factory that
    # ships the file but drops the runner writes its first close row with no provenance
    # and can never repair that.
    ("tests/test_close_telemetry_provenance.py", "TEMPLATE/tests/test_close_telemetry_provenance.py"),
    # The brain-metrics standing reading (P29 — no board issue: it ships under the standing
    # obligation `docs/measurement-procedure.md` §5 already declares). Paired because the
    # WHOLE value of a standing reading is that two factories compute the SAME predicate the
    # same way: a drifting second copy would make two factories' "24.4 % of a 200k window"
    # figures incomparable while both still looked correct. Unlike `insights.py` /
    # `synthesize_insights.py`, which read THIS factory's own `evidence/insights.jsonl`, this
    # file reads only artifacts every bootstrapped factory already has — its own Tier 0 brain
    # files, its own `skills/*/SKILL.md`, its own daemon logs — and imports nothing from this
    # repository, so (unlike `gate_budget.py`) the rationale cannot rest on an import edge.
    # A reader can reject the pairing on the two limits it actually carries: the `--home`
    # default names the profile THIS box serves (overridable by flag — the same shape
    # `tools/telemetry.py` already ships), and the oracle block CITES
    # `evidence/brain-metrics-2026-09-19.md` without ever reading it, so a factory that lacks
    # that file still runs and compares against a foreign, dated baseline.
    # The nearest analogue argues AGAINST pairing: `tools/compaction_rate.py`, the other
    # measurement tool, is one of the four deliberately unpaired tools, so "the idiom donor is
    # paired, therefore pair it" is not an available argument here.
    ("tools/brain_metrics.py", "TEMPLATE/tools/brain_metrics.py"),
    # The gate for the pair above, and paired for the reason that makes it a gate rather than
    # a convenience: a bootstrapped factory inherits the INSTRUMENT, and an instrument whose
    # arithmetic nothing checks is the shape this factory has already paid for — a gate that
    # ran nowhere while the audit printed HEALTHY over it (issue #59). Its probes are fixtures
    # and offline by construction, so the copy passes in a factory tree for the same reason it
    # does here: the live figures are properties of an INSTANT and are REPORTED by the
    # instrument, never asserted by this gate. That is also why no criterion in this change
    # pins a live figure — the fixture leg is the only pass/fail available (see the rationale
    # on the instrument's own pair above).
    ("tests/test_brain_metrics.py", "TEMPLATE/tests/test_brain_metrics.py"),
    # The subject-anchor instrument and its gate (board #149, ruling n=1158). Paired for the
    # reason that makes the instrument portable: it reads only artifacts a bootstrapped
    # factory already has -- its own `registry/fleet.json` (or the shipped example) and the
    # files its own factories declare -- and imports nothing from this repository, so two
    # factories compute the SAME predicate and their D1 resolutions stay comparable. The
    # rubric itself does NOT ship (a bootstrapped factory keeps its criteria in the template
    # project, as `tests/test_criteria_count.py` states), so where it is absent the instrument
    # takes the STATED-SKIP path rather than falling back to a copy of the accepted set that
    # could drift from the declaration -- which is why no default member list ships at all.
    # A reader can reject the pairing on the two limits it actually carries: the live reading
    # is a property of THIS box's fleet at THIS instant and is therefore REPORTED by the
    # instrument rather than asserted by the gate, and a factory that never adopts the rubric
    # runs an instrument that always skips with its reason.
    ("tools/subject_anchor.py", "TEMPLATE/tools/subject_anchor.py"),
    ("tests/test_subject_anchor.py", "TEMPLATE/tests/test_subject_anchor.py"),
    # Added with its registration (board #182 item 2, gate 58). The questions selftest gate
    # is byte-paired for the same reason as every entry above it: the manifest grain is what
    # keeps a factory from dropping the runner and keeping the file. Without this entry the
    # gate exists in both trees but NOTHING enforces that they stay identical.
    ("tests/test_questions.py", "TEMPLATE/tests/test_questions.py"),
    ("tests/test_self_audit_instant.py", "TEMPLATE/tests/test_self_audit_instant.py"),
    # Added with its registration (board #184, ruling n=1231). The gate reads
    # `TEMPLATE/**` AND `tools/**` in THIS tree, so without the entry the two copies
    # could drift and the shipped half would keep citing by number in every member.
    ("tests/test_citation_clause_titles.py", "TEMPLATE/tests/test_citation_clause_titles.py"),
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
        print("portability: NOT RUN — the pair list is already drifted.")
        return 1

    problems, scanned, examined = portability_problems()
    if scanned == 0:
        print(
            "template sync gate ERROR: zero pairs were read, so this gate examined "
            "nothing and cannot report a clean verdict"
        )
        return 1
    if problems:
        print("template non-portable:\n")
        for p in problems:
            print(f"  {p}")
        print(
            f"\n{scanned} pair(s) scanned, {examined} hex literal(s) examined. A literal "
            f"above resolves in THIS repository and will not in the factory this file "
            f"ships to — use a value that resolves in neither tree."
        )
        return 1

    print(f"template in sync: {len(PAIRS)} pair(s) byte-identical")
    print(
        f"portability: {scanned} pair(s) scanned, {examined} hex literal(s) examined, "
        f"0 resolving"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
