# Fleet-wide name census

Read at **2026-09-25T23:39:39Z** by `tools/kit_names.py` over **10** tree(s).

Names examined: the `.py` basenames `registry/kit.json` ships, plus the Phase D.1
promotion candidates. A name is reported only where at least one tree carries it.

## 1. Trees read

| tree | root |
|---|---|
| `ai-antispam` | `/root/ai-antispam` |
| `inferhub-watch` | `/root/inferhub-watch` |
| `inferhub-watch-skill` | `/root/inferhub-watch/skills/inferhub` |
| `infra-factory` | `/root/vds-servers` |
| `infra-factory-skill` | `/root/vds-servers/skills/infra-factory` |
| `meta-factory` | `/root/agent-factories` |
| `meta-factory-skill` | `/root/agent-factories/skills/meta-factory` |
| `miidas` | `/root/miidas` |
| `opencrabs-dev` | `/root/opencrabs` |
| `opencrabs-dev-skill` | `/root/.opencrabs/profiles/ops/skills/opencrabs-dev` |

## 2. Conflicts — one name, different declared purposes

### `test_ontology.py` — 5 trees, 4 purposes

Token overlap across those purposes: **0.0** (below 0.5 reads as different instruments).

| tree | path | sha256[:12] | declared purpose |
|---|---|---|---|
| `ai-antispam` | `tests/test_ontology.py` | `f1bd79251116` | Vocabulary gate for the agent-factories repo. |
| `inferhub-watch` | `tests/test_ontology.py` | `297bac1a0eec` | Ontology enforcement: site copy uses ontology terms, no banned synonyms. |
| `infra-factory` | `tests/test_ontology.py` | `f1bd79251116` | Vocabulary gate for the agent-factories repo. |
| `meta-factory` | `TEMPLATE/tests/test_ontology.py` | `9a5314c8ebae` | Gate: the repo prose uses no banned synonym from ONTOLOGY.md. |
| `meta-factory` | `tests/test_ontology.py` | `9a5314c8ebae` | Gate: the repo prose uses no banned synonym from ONTOLOGY.md. |
| `miidas` | `tests/test_ontology.py` | `f87c25f7e7b1` | Ontology enforcement for MIIDAS platform. |

## 3. Stdlib shadowing

**None.** No examined name matches a `sys.stdlib_module_names` entry.

## 4. Per-name population

| name | trees | sha agreement | purposes | overlap | conflict | shadows |
|---|---|---|---|---|---|---|
| `audit.py` | 5 | 5 digests | 2 | 0.667 | no | no |
| `brain_metrics.py` | 1 | same | 1 | 1.0 | no | no |
| `field_predicate.py` | 2 | 2 digests | 1 | 1.0 | no | no |
| `gate_budget.py` | 1 | same | 1 | 1.0 | no | no |
| `gate_fixtures.py` | 1 | same | 1 | 1.0 | no | no |
| `gate_registry.py` | 1 | same | 1 | 1.0 | no | no |
| `hook_installation.py` | 1 | same | 1 | 1.0 | no | no |
| `hygiene.py` | 4 | 3 digests | 1 | 1.0 | no | no |
| `kit_pin.py` | 1 | same | 1 | 1.0 | no | no |
| `ledger.py` | 5 | 5 digests | 1 | 1.0 | no | no |
| `ledger_boundary.py` | 2 | same | 1 | 1.0 | no | no |
| `ledger_declaration.py` | 2 | 2 digests | 2 | 0.733 | no | no |
| `patrol_host_state.py` | 1 | same | 1 | 1.0 | no | no |
| `reconstruction.py` | 2 | same | 1 | 1.0 | no | no |
| `registry.py` | 2 | 2 digests | 1 | 1.0 | no | no |
| `registry_attest.py` | 1 | same | 1 | 1.0 | no | no |
| `registry_render.py` | 1 | same | 1 | 1.0 | no | no |
| `review.py` | 1 | same | 1 | 1.0 | no | no |
| `rework_entries.py` | 1 | same | 1 | 1.0 | no | no |
| `rework_table.py` | 2 | same | 1 | 1.0 | no | no |
| `roadmap.py` | 1 | same | 1 | 1.0 | no | no |
| `subject_law.py` | 1 | same | 1 | 1.0 | no | no |
| `telemetry.py` | 1 | same | 1 | 1.0 | no | no |
| `test_audit_inflight_guard.py` | 1 | same | 1 | 1.0 | no | no |
| `test_audit_rates.py` | 1 | same | 1 | 1.0 | no | no |
| `test_binding_mechanism_exists.py` | 1 | same | 1 | 1.0 | no | no |
| `test_board_intake_recorded.py` | 1 | same | 1 | 1.0 | no | no |
| `test_brain_metrics.py` | 1 | same | 1 | 1.0 | no | no |
| `test_close_board_recorded.py` | 1 | same | 1 | 1.0 | no | no |
| `test_close_row_revision.py` | 1 | same | 1 | 1.0 | no | no |
| `test_close_telemetry_provenance.py` | 1 | same | 1 | 1.0 | no | no |
| `test_commit_pair_hook.py` | 1 | same | 1 | 1.0 | no | no |
| `test_commit_pathspec_law.py` | 1 | same | 1 | 1.0 | no | no |
| `test_commit_session_trailer.py` | 1 | same | 1 | 1.0 | no | no |
| `test_criteria_count.py` | 1 | same | 1 | 1.0 | no | no |
| `test_cron_thinness.py` | 1 | same | 1 | 1.0 | no | no |
| `test_docs_sync.py` | 1 | same | 1 | 1.0 | no | no |
| `test_duplicate_prose.py` | 1 | same | 1 | 1.0 | no | no |
| `test_gate_fixtures_closure.py` | 1 | same | 1 | 1.0 | no | no |
| `test_gate_registration.py` | 1 | same | 1 | 1.0 | no | no |
| `test_hq_delegation.py` | 1 | same | 1 | 1.0 | no | no |
| `test_hygiene_inflight.py` | 2 | same | 1 | 1.0 | no | no |
| `test_hygiene_namespace.py` | 2 | 2 digests | 1 | 1.0 | no | no |
| `test_insights_gate_recorded.py` | 1 | same | 1 | 1.0 | no | no |
| `test_kit_pin.py` | 1 | same | 1 | 1.0 | no | no |
| `test_law_structure.py` | 1 | same | 1 | 1.0 | no | no |
| `test_ledger.py` | 4 | 4 digests | 1 | 1.0 | no | no |
| `test_ledger_close_preflight.py` | 1 | same | 1 | 1.0 | no | no |
| `test_ledger_commit_cites_no_rows.py` | 1 | same | 1 | 1.0 | no | no |
| `test_ledger_identity.py` | 1 | same | 1 | 1.0 | no | no |
| `test_ledger_no_shrink.py` | 1 | same | 1 | 1.0 | no | no |
| `test_ledger_schema.py` | 3 | 3 digests | 1 | 1.0 | no | no |
| `test_ontology.py` | 5 | 4 digests | 4 | 0.0 | **YES** | no |
| `test_patrol_host_state.py` | 1 | same | 1 | 1.0 | no | no |
| `test_reconstructed_claim_declared.py` | 1 | same | 1 | 1.0 | no | no |
| `test_registry.py` | 1 | same | 1 | 1.0 | no | no |
| `test_registry_attest.py` | 1 | same | 1 | 1.0 | no | no |
| `test_registry_render.py` | 1 | same | 1 | 1.0 | no | no |
| `test_review.py` | 1 | same | 1 | 1.0 | no | no |
| `test_rework.py` | 5 | 4 digests | 1 | 1.0 | no | no |
| `test_rework_declared_landed.py` | 1 | same | 1 | 1.0 | no | no |
| `test_rework_relative_revision.py` | 1 | same | 1 | 1.0 | no | no |
| `test_roadmap_transition.py` | 1 | same | 1 | 1.0 | no | no |
| `test_score_artifact_sections.py` | 1 | same | 1 | 1.0 | no | no |
| `test_score_gate_recorded.py` | 1 | same | 1 | 1.0 | no | no |
| `test_single_writer.py` | 4 | 3 digests | 1 | 1.0 | no | no |
| `test_skill_version_contract.py` | 1 | same | 1 | 1.0 | no | no |
| `test_subject_form.py` | 1 | same | 1 | 1.0 | no | no |
| `test_telemetry_reader_registry.py` | 1 | same | 1 | 1.0 | no | no |
| `test_template_integrity.py` | 1 | same | 1 | 1.0 | no | no |

## 5. Bounds — what this census does not say

- **A conflict is not a verdict.** It names a name carried by two trees under
  two declared purposes. Which tree owns the name is the naming criteria's call,
  not this tool's.
- **Purpose is read from the MODULE docstring** (via `ast`), so a module with
  none contributes no purpose and two undocumented files sharing a name read as
  ONE purpose. That limit was measured rather than assumed: over **656** `.py`
  files in five trees, **0** carry a docstring placed after another statement,
  so the misplaced case is theoretical and the convention holds fleet-wide.
- **Reworded purposes are NOT conflicts** (token overlap at or above
  0.5). The threshold is a judgement and is printed per name so it
  can be argued with: a false conflict costs a look, a missed one costs the
  defect this census exists for.
- **Depth is bounded at 6** and the noisy directories are skipped, so a name
  carried only deeper than that is not seen.

