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


# --- the foreign-toolchain leg (#85, ruled n=2144) --------------------------
#
# `portability_problems` above judges literals that RESOLVE in this repository and nowhere
# else. This leg judges the mirror hazard: a file shipped in `TEMPLATE/` that names a
# toolchain resolving NOWHERE -- not here, and not in the factory that copies the tree. A
# member inheriting such a reference is handed an instruction it cannot execute, and the
# failure is silent: the binary is absent, the law offers no fallback, and the lane either
# improvises an equivalent by hand or stalls -- neither distinguishable from a correct
# attempt by anyone reading the result.
#
# THE POPULATION IS EVERY FILE UNDER `TEMPLATE/`, not the declared pairs. A paired file is
# where drift is *visible*; an unpaired shipped file is where it is *unread*.
#
# MEASURED at the ruling (HQ, first-hand): `shutil.which` returns None for all nine names
# below -- the 40-file family lives in ONE member factory's private skill repo.
FOREIGN_TOOLCHAIN_NAMES = (
    "oc-ledger", "oc-prchecks", "oc-order-validate", "oc-deploy", "oc-attrib",
    "oc-snap", "oc-drift-check", "oc-notify-fanout", "oc-wt",
)

# The PREFIX is what this leg matches. The nine names above are the MEASUREMENT, not the
# scope: a gate keyed to a fixed list admits the next member of the family, which is how
# the questions instrument's former prefixed name and the donor's cron job names stayed in
# the shipped tree while the list read clean.
FOREIGN_PREFIX = re.compile(r"\boc-[a-z][a-z0-9-]*")

# DECLARED survivors: a token that LOOKS foreign and is not, with the reason it stays.
# Every entry must be a token this repository's own code EMITS or CONSUMES, so it resolves
# on every host by construction -- never a name that merely happens to be convenient.
DECLARED_FOREIGN_TOKENS = {
    "oc-cause-count": (
        "the template's OWN stderr token: defined at tools/field_predicate.py "
        "(CAUSE_COUNT_TOKEN), emitted by tools/hygiene.py, and asserted by "
        "tests/test_gate_registration.py. It names no binary and resolves on every host by "
        "construction, because the factory itself writes it."
    ),
    "oc-notify-fanout": (
        "a DENY-LIST literal in tests/test_review.py, whose gate asserts donor tokens are "
        "ABSENT from the shipped tools/review.py. A deny-list entry is the inverse of a "
        "dependency, so removing it would weaken that gate by one token."
    ),
}

def foreign_toolchain_problems(root: "Path | None" = None) -> "tuple[list[str], int]":
    """`(problems, files_scanned)` over every file under `root`.

    `root` is a parameter rather than a constant so the leg is PROBEABLE: the neuter probe
    below points it at a synthetic tree, which is the only way to show the detector bites.
    A rule that has only ever seen good input has not been shown to bite.
    """
    base = root if root is not None else REPO / "TEMPLATE"
    problems: list[str] = []
    scanned = 0
    if not base.is_dir():
        return problems, 0
    for path in sorted(q for q in base.rglob("*") if q.is_file()):
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue  # a binary shipped file carries no reference to read
        try:
            label = str(path.relative_to(REPO))
        except ValueError:
            label = str(path)
        for token in sorted(set(FOREIGN_PREFIX.findall(text))):
            if token in DECLARED_FOREIGN_TOKENS:
                continue
            problems.append(
                f"{label} names `{token}` -- a toolchain that resolves on no host: it is "
                f"not on PATH here and will not be in the factory this file ships to. "
                f"Remove the reference, or declare it in DECLARED_FOREIGN_TOKENS with the "
                f"reason it is not a dependency."
            )
    return problems, scanned

def _probe_foreign_toolchain() -> list[str]:
    """The two-sided neuter probe: the leg BITES on a foreign name, stays SILENT on a
    declared one, and bites through the PREFIX rather than only the measured list."""
    import tempfile

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "clean.md").write_text("nothing foreign here\n")
        (root / "declared.md").write_text("oc-cause-count: 7\n")
        got, scanned = foreign_toolchain_problems(root)
        if scanned != 2:
            problems.append(f"probe: expected 2 file(s) scanned, got {scanned}")
        if got:
            problems.append(f"probe: expected SILENCE on a declared token, got {got}")

        (root / "dirty.md").write_text("run `oc-ledger sync`\n")
        got, _ = foreign_toolchain_problems(root)
        if len(got) != 1 or "oc-ledger" not in got[0]:
            problems.append(f"probe: expected ONE problem naming oc-ledger, got {got}")

        # The PREFIX bites, not only the nine measured names: a synthetic member of the
        # family that is on no list must still be caught. The token is ASSEMBLED, never
        # written whole -- this file ships in `TEMPLATE/` and is scanned by its own leg, so
        # a literal unlisted member here would be a real finding, not a probe.
        unlisted = "oc-" + "never-measured-thing"
        (root / "dirty.md").write_text(f"run `{unlisted}`\n")
        got, _ = foreign_toolchain_problems(root)
        if len(got) != 1 or unlisted not in got[0]:
            problems.append(
                f"probe: the PREFIX did not bite on an unlisted member, got {got}"
            )

        # A declared token must NOT be what the prefix matched -- i.e. the declared set is a
        # real allowlist, not a blanket mute.
        (root / "dirty.md").write_text("oc-cause-count: 1\nand `oc-deploy ship`\n")
        got, _ = foreign_toolchain_problems(root)
        if len(got) != 1 or "oc-deploy" not in got[0]:
            problems.append(
                f"probe: a declared token muted a real one on the same file, got {got}"
            )
    return problems


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
    ("tests/test_gate_invocation_mode.py", "TEMPLATE/tests/test_gate_invocation_mode.py"),
    ("tests/test_gate_fixtures_closure.py", "TEMPLATE/tests/test_gate_fixtures_closure.py"),
    # The blast-radius gate selector, its gate, and its map's example (#294, ruling n=2106).
    # The selector is a TOOL, so it pairs like every other tool. The map's SHAPE ships as an
    # example at BOTH paths on the same reasoning as `gates.example.json` below: a factory
    # copies it to `registry/gate_triggers.json` (TEMPLATE/BOOTSTRAP.md) and then extends it
    # with its own surfaces, so the live file is FACTORY DATA and is deliberately not paired.
    ("tools/gate_select.py", "TEMPLATE/tools/gate_select.py"),
    ("tests/test_gate_triggers.py", "TEMPLATE/tests/test_gate_triggers.py"),
    ("registry/gate_triggers.example.json", "TEMPLATE/registry/gate_triggers.example.json"),
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
    # Added with its registration (board #254, ruling n=1810). It pairs for the same reason
    # the exemption-carrying gates beside it do: the gate's LOGIC is universal law, and its
    # PARAMETERS are factory data (`docs/law-uuid-exemptions.json`), so a member that took
    # the file without its table would red on its own law's declared debt, and one that took
    # the table without the runner would carry a declaration nothing reads. The TEMPLATE
    # half ships the `.example.json` skeleton and no live table, so a bootstrapped factory
    # starts with zero exemptions -- a clean file, not an excused one.
    ("tests/test_law_no_raw_session_uuid.py", "TEMPLATE/tests/test_law_no_raw_session_uuid.py"),
    ("tests/test_hygiene_namespace.py", "TEMPLATE/tests/test_hygiene_namespace.py"),
    ("tests/test_docs_sync.py", "TEMPLATE/tests/test_docs_sync.py"),
    # Added with its registration (board #48, ruling 2026-09-26). The gate drives SYNTHETIC
    # repositories and reads no live board, so it passes in a bootstrapped factory exactly as
    # it does here; its `wiring_problems` leg reads `tools/audit.py` and `tools/hooks/pre-commit`,
    # both paired files, so it is only meaningful where all three ship together — a factory
    # that took the law without the hook leg would carry a clause whose mechanism is absent.
    ("tests/test_law_mechanism_same_commit.py", "TEMPLATE/tests/test_law_mechanism_same_commit.py"),
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
    # Added with its registration (G3, q15): the gate drives `tools/hygiene.py`, which is a
    # paired file, so it is only meaningful where BOTH ship — a factory that took the report
    # leg without the gate proving it holds no removal path would carry a leg nothing checks,
    # and one that took the gate without the leg would run probes that cannot pass.
    ("tests/test_hygiene_build_residue.py", "TEMPLATE/tests/test_hygiene_build_residue.py"),
    # Added with its registration (G2, q13): same reason as the G3 pair above -- the gate
    # reads the declaration surfaces that `tools/hygiene.py` sweeps, so a factory carrying
    # one half without the other would ship a sweep nothing checks, or probes that cannot run.
    ("tests/test_hygiene_declaration_sweep.py", "TEMPLATE/tests/test_hygiene_declaration_sweep.py"),
    # Added with its registration (G5, q13): the gate checks the placement map that
    # `tools/hygiene.py` declares, so a factory carrying the leg without the gate would
    # have a map nothing holds to the tree, and one carrying the gate without the leg
    # would run probes against a map that does not exist.
    ("tests/test_hygiene_placement.py", "TEMPLATE/tests/test_hygiene_placement.py"),
    # Added with its registration (G6, q13): the gate plants worktree-census fixtures that
    # `tools/hygiene.py`'s stale-directory leg reads, so a factory carrying the leg without
    # the gate would ship a population nothing holds to git's own list, and one carrying the
    # gate without the leg would probe a function that does not exist.
    ("tests/test_hygiene_stale_dirs.py", "TEMPLATE/tests/test_hygiene_stale_dirs.py"),
    # Added with its registration (G7, q13): the gate plants evidence fixtures that
    # `tools/hygiene.py`'s supersession leg reads, so a factory carrying the leg without the
    # gate would ship a debt census nothing holds to the naming convention, and one carrying
    # the gate without the leg would probe a function that does not exist.
    ("tests/test_hygiene_evidence_supersession.py", "TEMPLATE/tests/test_hygiene_evidence_supersession.py"),
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
    ("tests/test_score_artifact_measurable.py", "TEMPLATE/tests/test_score_artifact_measurable.py"),
    ("tests/test_duplicate_prose.py", "TEMPLATE/tests/test_duplicate_prose.py"),
    ("tests/test_ledger_no_shrink.py", "TEMPLATE/tests/test_ledger_no_shrink.py"),
    ("tests/ledger_boundary.py", "TEMPLATE/tests/ledger_boundary.py"),
    ("tests/test_close_row_revision.py", "TEMPLATE/tests/test_close_row_revision.py"),
    ("tests/test_score_gate_recorded.py", "TEMPLATE/tests/test_score_gate_recorded.py"),
    ("tests/test_subject_form.py", "TEMPLATE/tests/test_subject_form.py"),
    ("tests/test_rework_relative_revision.py", "TEMPLATE/tests/test_rework_relative_revision.py"),
    ("tests/test_reconstructed_claim_declared.py", "TEMPLATE/tests/test_reconstructed_claim_declared.py"),
    # The commit-session-trailer gate (issue #138, ruling n=928). Paired for the same
    # reason every other gate is: the hook it pins ships from TEMPLATE, so a factory
    # that takes the hook must take its pin too.
    ("tests/test_commit_session_trailer.py", "TEMPLATE/tests/test_commit_session_trailer.py"),
    # The audit tree-condition gate (board #150, ruling n=919). Paired for the same reason
    # every other gate is: the audit ships from TEMPLATE, so a factory that takes the audit
    # must take the gate that pins its verdict's provenance.
    ("tests/test_audit_tree_condition.py", "TEMPLATE/tests/test_audit_tree_condition.py"),
    # The undefined-name gate (board #235). Paired for the same reason every other gate is:
    # the audit ships from TEMPLATE, so a factory that takes the audit must take the gate
    # that pins the audit's own tools to the names they bind. It scans `tools/` in whatever
    # tree it runs in, so it is clean in a bootstrapped factory rather than skipping there.
    ("tests/test_audit_undefined_names.py", "TEMPLATE/tests/test_audit_undefined_names.py"),
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
    # The ledger header's declared closure (#137 half 1). It ships because the claim it
    # guards — "this file is copied byte-identically" — is the thing a factory READS before
    # copying, and a header that drifts from the code it describes misleads every member.
    ("tests/test_ledger_header_closure.py", "TEMPLATE/tests/test_ledger_header_closure.py"),
    # The claim half of the pre-flight (#137 half 2). It ships for the same reason the close
    # half does: a factory that ports the ledger must be able to check the sequence rule it
    # was given, and the leg's own law lives in the file it pins.
    ("tests/test_ledger_claim_preflight.py", "TEMPLATE/tests/test_ledger_claim_preflight.py"),
    # The ref-kind half of the pre-flight (#232). It ships for the same reason its two
    # siblings do: a factory that ports the ledger must be able to check the ref-kind rule
    # it was given, and the declaration file the refusal names is the member's OWN — so the
    # gate that proves the seam works has to travel with the tool that reads it.
    ("tests/test_ledger_refs_preflight.py", "TEMPLATE/tests/test_ledger_refs_preflight.py"),
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
    # Added with its registration (board #454, ruling n=3024). The gate reads the factory's
    # OWN routing surfaces -- `skills/meta-factory/SKILL.md`, `docs/factory-registry.md`,
    # `registry/**`, `evidence/factories.md` -- and both ship whole for the reason the
    # entries around it state: a factory that took the gate without the surfaces, or the
    # surfaces without the gate, would carry the 2026-10-09 order's restatement drift with
    # nothing comparing them (the #305 bound: no gate compared these prose surfaces).
    ("tests/test_issue_routing_surfaces.py", "TEMPLATE/tests/test_issue_routing_surfaces.py"),
    # Added with its registration (issue #270, the atomic ruling act). The pairing gate
    # drives the writer `tools/rule.py`, and both ship whole for the same reason the ledger
    # and its gates do: a factory that took the writer without the gate proving every
    # `ruling` row carries its `comment=<id>` token would carry the #270 defect unnoticed,
    # and one that took the gate without the writer would run probes that cannot pass.
    ("tools/rule.py", "TEMPLATE/tools/rule.py"),
    ("tests/test_ruling_row_recorded.py", "TEMPLATE/tests/test_ruling_row_recorded.py"),
    # Added with its registration (issue #441, ruled n=2907, dispatched n=2909). Paired for
    # the reason every gate is, plus this one's own: the gate drives the publication
    # predicate in `tools/publish.py` AND the writer `tools/rule.py`, and all three ship
    # whole. A factory that took the writer without the predicate would cite rows it cannot
    # check, and one that took the gate without either would run probes that cannot pass --
    # the #107 class, which is exactly why the copies are held here.
    ("tests/test_citation_published.py", "TEMPLATE/tests/test_citation_published.py"),
    # Added with its registration (board #262, ruled n=2246, dispatched n=2247). Paired for
    # the same reason every other gate is, plus one of its own: this leg reads the LEDGER's
    # rows and the boundary declaration, so a factory that took the runner without the file
    # would invoke nothing, while one that took the file without the runner would carry a
    # gate no audit ever reaches. The shipped citation gate's `SCOPE_DIRS` is UNCHANGED by
    # this landing -- the two legs judge different populations and neither stands in for
    # the other.
    ("tests/test_ledger_citation_declared.py", "TEMPLATE/tests/test_ledger_citation_declared.py"),
    # Added with its registration (board #431, ruling n=2799, dispatched n=2793). Paired for
    # the reason that makes a CENSUS portable rather than for the manifest grain alone: it
    # reads SOURCE and never `evidence/`, so a bootstrapped factory runs the same predicate
    # over its OWN modules, and two factories' censuses stay comparable only while the
    # predicate is one file. That property is also why the entry is load-bearing in the
    # direction a `twin.exists()` check cannot cover: this gate's own population rule asks
    # whether a module has a TEMPLATE twin, so a copy that drifted would judge a population
    # the other tree never saw — the pairing test is what keeps the two halves answering the
    # same question. Without this entry the gate would exist in both trees with nothing
    # enforcing that they stay identical.
    ("tests/test_declared_boundary_census.py", "TEMPLATE/tests/test_declared_boundary_census.py"),
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

    probe = _probe_foreign_toolchain()
    if probe:
        print("template foreign-toolchain leg: NEUTER PROBE FAILED\n")
        for p in probe:
            print(f"  {p}")
        return 1

    if not (REPO / "TEMPLATE").is_dir():
        print("foreign toolchain: no TEMPLATE/ tree -- nothing to scan")
    else:
        ft_problems, ft_scanned = foreign_toolchain_problems()
        if ft_scanned == 0:
            print(
                "template foreign-toolchain leg ERROR: zero file(s) read, so this leg "
                "examined nothing and cannot report a clean verdict"
            )
            return 1
        if ft_problems:
            print("template ships a foreign toolchain:\n")
            for p in ft_problems:
                print(f"  {p}")
            return 1
        print(
            f"foreign toolchain: {ft_scanned} file(s) under TEMPLATE/ scanned, "
            f"0 undeclared oc-* reference(s); "
            f"{len(DECLARED_FOREIGN_TOKENS)} declared survivor token(s)"
        )

    print(f"template in sync: {len(PAIRS)} pair(s) byte-identical")
    print(
        f"portability: {scanned} pair(s) scanned, {examined} hex literal(s) examined, "
        f"0 resolving"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
