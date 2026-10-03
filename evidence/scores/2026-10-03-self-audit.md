# Operational Process Self-Audit — 2026-10-03

> **Verdict:** `FAILED` · Process 3 (Internal Self-Audit)

> **Ledger read at:** `2026-10-03T02:11:01Z` (2020 events) — this artifact describes the ledger AS OF THAT INSTANT, before this run's own row was appended. It is a START-OF-RUN SNAPSHOT, not the ledger's state when you read it: the run row this audit writes lands after the read, and concurrent lanes append throughout the gate window (#142, ruling n=919).

---

## 1. Process Health & Delivery Telemetry

| Metric | Value | Reference / Derivation |
|---|---|---|
| **Total Ledger Events** | `2020` | Continuous ledger sequence |
| **Closed Tasks** | `240` | Distinct closed subjects; `246` close rows (6 re-close of a re-opened subject) |
| **First-Pass Yield** | `96.2%` | 25 accepted runs ÷ 26 runs stating an outcome (coverage: 26 of 635 run rows) |
| **Rework Entries** | `201` | Defect count recorded in rework.md |
| **Rework Declarations** | `153/246` (62.2%) | Close rows declaring a `rework=#N` or `rework=none` disposition — canonical trailer read by position: rework=#N 117; rework=none 36; undeclared 93; of which state rework=unstated 9 (printed, never gated — n=386 clause 5) |
| **Rework Share** | `45.6%` | 201 rework entries ÷ (240 closed subjects + 201 rework entries) |
| **Rework per Close** | `83.8%` | 201 rework entries ÷ 240 closed subjects |
| **Change Fail Rate** | `68.3%` | 164 closes that produced a rework entry ÷ 240 closed work units — **linkage coverage `182/201`** entries carry a determinate Subject (90.5%); read the rate only against this coverage |
| **Avg Task Lead Time** | `76985.8s` | Mean intake→close duration over 245 sampled subjects |
| **Total Inference Cost** | `$12051.6041` | Tracked cost across ledger task telemetry — summed from each row's canonical TRAILER only, by position and across every event (issue #90) |
| **Telemetry Outside the Trailer** | `18` row(s) | excluded from the totals above BY DESIGN: these rows carry a telemetry-shaped token outside the canonical trailer — n=135 (close), n=136 (close), n=146 (close), n=303 (close), n=382 (intake), n=561 (intake), n=572 (ruling), n=576 (intake), n=577 (intake), n=584 (close), n=586 (run), n=594 (close), n=598 (intake), n=867 (run), n=933 (intake), n=1067 (run), n=1889 (ruling), n=1985 (dispatch). Read each as prose, not as spend |
| **Avg Cost / Closed Task** | `$50.2150` | $12051.6041 total cost ÷ 240 distinct closed subjects |
| **Cost / Successful Task** | `$165.0905` | $12051.6041 total cost ÷ 73 accepted closed subjects (coverage: 74 of 246 close rows state an outcome) |
| **Total Tokens (In/Out)** | `1575621484 / 44812746321` | Cumulative prompt and completion tokens |
| **Cadence Status** | `HELD` | Last run: 0.1h ago |

---

## 2. Mechanical Gate Verification

| Gate / Command | Outcome | Duration | Notes |
|---|---|---|---|
| `/usr/bin/python3 tools/ledger.py verify` | `FAIL` | `2.04s` | open claim: n=2017 #278 claimed by worker — no close after it and no release naming it, so the ledger cannot tell in-flight work from withdr [STALE:bytes] blob 8743536cb6d6c716b14473ec51f1dbe006ee93b9 -> b560bc9142c37aca7b02db2312074ca03b86bd03 |
| `/usr/bin/python3 tests/test_ontology.py` | `PASS` | `1.92s` |  |
| `/usr/bin/python3 tests/test_rework.py` | `PASS` | `3.38s` | [STALE:bytes] blob 16949c1cf3d50ba41219a7cf00bdfd7815740947 -> 650b45de5dc0145692e6cf1928904581bc85c77b |
| `/usr/bin/python3 tests/test_single_writer.py` | `PASS` | `0.14s` |  |
| `/usr/bin/python3 tests/test_ledger_schema.py` | `PASS` | `1.89s` |  |
| `/usr/bin/python3 tests/test_ledger_index.py` | `PASS` | `3.7s` |  |
| `/usr/bin/python3 tests/test_template_sync.py` | `PASS` | `1.24s` | [STALE:bytes] blob 43272aa2e370480d7bd53cd31d6b878cd9e49521 -> 283eca7bcf5f6cd8b5e496bd398d306220f57e75 |
| `/usr/bin/python3 tools/hygiene.py --audit --namespace agent-factories` | `PASS` | `0.99s` | [STALE:bytes] blob a19a14356075d3c2f5d93e0961b83b2b5ecad7a2 -> 794c281cb6950c64d3d8f899eb7ca38821327aee |
| `/usr/bin/python3 tools/roadmap.py --audit` | `PASS` | `0.35s` |  |
| `/usr/bin/python3 -m pytest tests/test_law_coverage.py` | `PASS` | `4.53s` | [STALE:bytes] blob 3d7b428afcefdd4cd1df58ea9d7d1f6ad32c5e38 -> d92bfe957e365ee330be1c0dfc934640bcee46b2 |
| `/usr/bin/python3 -m pytest tests/test_session_bindings.py` | `PASS` | `3.39s` |  |
| `/usr/bin/python3 -m pytest tests/test_law_structure.py` | `PASS` | `3.35s` |  |
| `/usr/bin/python3 tests/test_docs_sync.py` | `PASS` | `0.2s` |  |
| `/usr/bin/python3 -m pytest tests/test_hygiene_namespace.py` | `PASS` | `9.72s` |  |
| `/usr/bin/python3 -m pytest tests/test_audit_rates.py` | `PASS` | `37.16s` | [STALE:bytes] blob db49f99865c9260b84f075561dad402aafa00918 -> 73a526ff71ba84813386b0363561504fd756dc3b |
| `/usr/bin/python3 -m pytest tests/test_score_gate_recorded.py` | `PASS` | `7.06s` | [STALE:bytes] blob 20547ec4e3ed6fadd16cf4adabb4bb8545fd3d0d -> 43daf072fad2632f01f31deffc252aaaf7402641 |
| `/usr/bin/python3 -m pytest tests/test_hq_delegation.py` | `PASS` | `4.54s` |  |
| `/usr/bin/python3 -m pytest tests/test_template_integrity.py` | `PASS` | `4.96s` |  |
| `/usr/bin/python3 -m pytest tests/test_hygiene_inflight.py` | `PASS` | `9.39s` |  |
| `/usr/bin/python3 -m pytest tests/test_close_board_recorded.py` | `PASS` | `4.52s` |  |
| `/usr/bin/python3 tests/test_ledger_commit_cites_no_rows.py` | `PASS` | `1.94s` | [STALE:bytes] blob 2178c393f43a145b08df201397c947ce629b9145 -> 1610d2aa5867446b0fe8d8435751e14cacd4f313 |
| `/usr/bin/python3 tests/test_commit_pathspec_law.py` | `PASS` | `0.21s` |  |
| `/usr/bin/python3 tests/test_criteria_count.py` | `PASS` | `0.82s` |  |
| `/usr/bin/python3 tests/test_synthesize_interface.py` | `PASS` | `0.76s` |  |
| `/usr/bin/python3 tests/test_roadmap_transition.py` | `PASS` | `2.51s` |  |
| `/usr/bin/python3 -m pytest tests/test_board_intake_recorded.py` | `PASS` | `3.52s` |  |
| `/usr/bin/python3 -m pytest tests/test_gate_fixtures_closure.py` | `PASS` | `17.05s` |  |
| `/usr/bin/python3 tests/test_ledger.py` | `PASS` | `251.07s` |  |
| `/usr/bin/python3 tests/test_gate_registration.py` | `PASS` | `8.76s` | [STALE:bytes] blob 557f7f63ed342fcd5b12136f5b612266a99383a0 -> 558262e960c16163a2f5517a7178d30029f6be45 |
| `/usr/bin/python3 -m pytest tests/test_close_row_revision.py` | `PASS` | `7.85s` | [STALE:bytes] blob 801306a217ff458e7cade7c8f4f2bceeadb1a493 -> 7328c2756f9480305757a989cd2f5a7fa8ab366a |
| `/usr/bin/python3 -m pytest tests/test_score_artifact_sections.py` | `PASS` | `3.57s` |  |
| `/usr/bin/python3 tests/test_duplicate_prose.py` | `PASS` | `0.17s` |  |
| `/usr/bin/python3 tests/test_ledger_no_shrink.py` | `PASS` | `53.7s` | [STALE:bytes] blob 0742623eb3626fbb0f54cf3b1e9cedd47d22d9f3 -> e48dc5ea2750dfd56c5746b955a2fb2a89e9f893 |
| `/usr/bin/python3 -m pytest tests/test_subject_form.py` | `PASS` | `6.94s` | [STALE:bytes] blob 05a0d4be32c079039eaa330ecf461d771dfdafb9 -> b1f74bbb1a0eadb478d53c21b10565805a4af767 |
| `/usr/bin/python3 tests/test_registry.py` | `PASS` | `1.68s` | [STALE:bytes] blob afc6a6b97689e8c72ca8bf93950ff951727f85ff -> 376570ca114b471458525e08ac393911fb4c9c27 |
| `/usr/bin/python3 -m pytest tests/test_patrol_host_state.py` | `PASS` | `41.8s` | [STALE:bytes] blob 4deb80c13bff81f89e1909a2e03620121b93ac35 -> e9976252403f0ac503c2bbc2ebde975cf22c7d54 |
| `/usr/bin/python3 tests/test_rework_relative_revision.py` | `PASS` | `0.66s` |  |
| `/usr/bin/python3 -m pytest tests/test_ledger_close_preflight.py` | `PASS` | `8.65s` |  |
| `/usr/bin/python3 -m pytest tests/test_ledger_claim_preflight.py` | `PASS` | `57.64s` |  |
| `/usr/bin/python3 -m pytest tests/test_ledger_refs_preflight.py` | `PASS` | `6.58s` |  |
| `/usr/bin/python3 tests/test_shipped_audit_runs.py` | `PASS` | `762.44s` |  |
| `/usr/bin/python3 tests/test_shipped_mechanism_law.py` | `PASS` | `0.4s` |  |
| `/usr/bin/python3 tests/test_audit_undefined_names.py` | `PASS` | `4.33s` |  |
| `/usr/bin/python3 -m pytest tests/test_telemetry_reader_registry.py` | `PASS` | `16.32s` |  |
| `/usr/bin/python3 tests/test_commit_pair_hook.py` | `PASS` | `1.67s` |  |
| `/usr/bin/python3 -m pytest tests/test_registry_render.py` | `PASS` | `4.77s` |  |
| `/usr/bin/python3 tests/test_rework_declared_landed.py` | `FAIL` | `1.04s` | rework declared-to-landed gate FAILED: 1 unresolved declaration(s), 0 probe failure(s) |
| `/usr/bin/python3 -m pytest tests/test_reconstructed_claim_declared.py` | `PASS` | `8.87s` | [STALE:bytes] blob 53555222dbc1f8277a31042fa401189216b0e0d3 -> 7592b9eb1050a72ad9cbd4757cbe9bd89687a776 |
| `/usr/bin/python3 -m pytest tests/test_skill_version_contract.py` | `PASS` | `10.81s` |  |
| `/usr/bin/python3 -m pytest tests/test_cron_thinness.py` | `PASS` | `6.24s` |  |
| `/usr/bin/python3 -m pytest tests/test_close_telemetry_provenance.py` | `PASS` | `5.45s` |  |
| `/usr/bin/python3 -m pytest tests/test_insights_gate_recorded.py` | `PASS` | `5.15s` | [STALE:bytes] blob 061c7ebe82e8d9e48742ac851b1301d423936d17 -> c6928af0357ef958158b2e6da373ffb94c957739 |
| `/usr/bin/python3 -m pytest tests/test_binding_mechanism_exists.py` | `PASS` | `12.18s` |  |
| `/usr/bin/python3 tests/test_brain_metrics.py` | `PASS` | `0.83s` |  |
| `/usr/bin/python3 tests/test_audit_inflight_guard.py` | `PASS` | `11.53s` |  |
| `/usr/bin/python3 tests/test_commit_session_trailer.py` | `PASS` | `1.62s` |  |
| `/usr/bin/python3 tests/test_ledger_identity.py` | `PASS` | `13.91s` |  |
| `/usr/bin/python3 tests/test_kit_manifest.py` | `PASS` | `5.57s` |  |
| `/usr/bin/python3 -m pytest tests/test_synthesize_insights.py` | `PASS` | `33.36s` |  |
| `/usr/bin/python3 -m pytest tests/test_registry_attest.py` | `PASS` | `3.0s` |  |
| `/usr/bin/python3 tests/test_kit_deliver.py` | `PASS` | `1.31s` |  |
| `/usr/bin/python3 tests/test_kit_pin.py` | `PASS` | `2.82s` |  |
| `/usr/bin/python3 tests/test_kit_census.py` | `PASS` | `0.66s` |  |
| `/usr/bin/python3 tests/test_kit_names.py` | `PASS` | `0.63s` |  |
| `/usr/bin/python3 tests/test_kit_surfaces.py` | `PASS` | `5.64s` |  |
| `/usr/bin/python3 tests/test_publish.py` | `PASS` | `4.08s` |  |
| `/usr/bin/python3 tests/test_subject_anchor.py` | `PASS` | `0.43s` |  |
| `/usr/bin/python3 tests/test_questions.py` | `PASS` | `966.07s` |  |
| `/usr/bin/python3 tests/test_citation_clause_titles.py` | `PASS` | `1.18s` |  |
| `/usr/bin/python3 tests/test_self_audit_instant.py` | `PASS` | `0.16s` |  |
| `/usr/bin/python3 tests/test_gate_invocation_mode.py` | `PASS` | `1.2s` |  |
| `/usr/bin/python3 tests/test_audit_tree_condition.py` | `PASS` | `4.04s` |  |
| `/usr/bin/python3 tests/test_instrument_census.py` | `PASS` | `2.83s` |  |
| `/usr/bin/python3 tests/test_ledger_header_closure.py` | `PASS` | `1.06s` |  |
| `/usr/bin/python3 -m pytest tests/test_insights_author.py` | `PASS` | `7.13s` |  |
| `/usr/bin/python3 -m pytest tests/test_insights_audience.py` | `PASS` | `4.25s` |  |
| `/usr/bin/python3 -m pytest tests/test_insights_status.py` | `PASS` | `6.33s` |  |
| `/usr/bin/python3 tests/test_law_no_raw_session_uuid.py` | `PASS` | `0.31s` |  |
| `/usr/bin/python3 -m pytest tests/test_hygiene_build_residue.py` | `PASS` | `7.23s` |  |
| `/usr/bin/python3 -m pytest tests/test_hygiene_declaration_sweep.py` | `PASS` | `4.59s` | [STALE:bytes] blob 9fae3f382baabef47f9a6b06fa0729d8b5e4a07e -> fcc6629b039508ab3c9a22861df78cffba96252c |
| `/usr/bin/python3 -m pytest tests/test_ruling_row_recorded.py` | `PASS` | `4.57s` |  |
| `/usr/bin/python3 -m pytest tests/test_hygiene_placement.py` | `PASS` | `6.15s` | [STALE:bytes] blob 3782c1e7f9c956c1c07a25bf6249d34a4c762194 -> e7b97f6eaf05430a7ff4033b29d2efe61111395b |
| `/usr/bin/python3 -m pytest tests/test_hygiene_stale_dirs.py` | `PASS` | `5.48s` | [STALE:bytes] blob 583c9753a981b99fae10dc74cd1328c400249c17 -> cbb345db6def3309be238c8ac8b2703efa413f7a |
| `/usr/bin/python3 -m pytest tests/test_hygiene_evidence_supersession.py` | `PASS` | `4.77s` | [STALE:bytes] blob fa6be5fd62add9095cb5b875b03b5ea082ba90ac -> 3d681a525163570f5b0541c8c136506d81f07e4c |

---

## 3. Calibration Spot-Check (Sampled Task)

- **Sampled Subject:** `#283`
- **Intake Recorded:** `YES`
- **Claim Lock Recorded:** `YES`
- **Close Verified:** `YES`
- **Sequence Integrity:** `VERIFIED`
