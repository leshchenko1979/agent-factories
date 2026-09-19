# Operational Process Self-Audit — 2026-09-19

> **Verdict:** `PASSED` · Process 3 (Internal Self-Audit)

---

## 1. Process Health & Delivery Telemetry

| Metric | Value | Reference / Derivation |
|---|---|---|
| **Total Ledger Events** | `419` | Continuous ledger sequence |
| **Closed Tasks** | `53` | Distinct closed subjects; `55` close rows (2 re-close of a re-opened subject) |
| **First-Pass Yield** | `100.0%` | 24 accepted runs ÷ 24 runs stating an outcome (coverage: 24 of 63 run rows) |
| **Rework Entries** | `38` | Defect count recorded in rework.md |
| **Rework Share** | `41.8%` | 38 rework entries ÷ (53 closed subjects + 38 rework entries) |
| **Rework per Close** | `71.7%` | 38 rework entries ÷ 53 closed subjects |
| **Change Fail Rate** | `32.1%` | 17 closes that produced a rework entry ÷ 53 closed work units — **linkage coverage `19/38`** entries carry a determinate Subject (50.0%); read the rate only against this coverage |
| **Avg Task Lead Time** | `5832.2s` | Mean intake→close duration over 54 sampled subjects |
| **Total Inference Cost** | `$118.2620` | Tracked cost across ledger task telemetry |
| **Avg Cost / Closed Task** | `$2.2314` | $118.2620 total cost ÷ 53 distinct closed subjects |
| **Cost / Successful Task** | `$3.4783` | $118.2620 total cost ÷ 34 accepted closed subjects (coverage: 34 of 55 close rows state an outcome) |
| **Total Tokens (In/Out)** | `15643667 / 429268098` | Cumulative prompt and completion tokens |
| **Cadence Status** | `HELD` | Last run: 0.0h ago |

---

## 2. Mechanical Gate Verification

| Gate / Command | Outcome | Duration | Notes |
|---|---|---|---|
| `/usr/bin/python3 tools/ledger.py verify` | `PASS` | `0.34s` |   excused: #8 missing claim (granted 2026-09-12) — close wri |
| `/usr/bin/python3 tests/test_ontology.py` | `PASS` | `0.73s` | vocabulary clean: 55 canonical term(s), 3 banned term(s), 90 |
| `/usr/bin/python3 tests/test_rework.py` | `PASS` | `0.31s` | rework gate passed |
| `/usr/bin/python3 tests/test_single_writer.py` | `PASS` | `0.17s` | single-writer state clean: 9 declared surface(s) audited, lo |
| `/usr/bin/python3 tests/test_ledger_schema.py` | `PASS` | `0.37s` | ledger schema clean: 419 row(s) audited, all domain invarian |
| `/usr/bin/python3 tests/test_template_sync.py` | `PASS` | `0.23s` | template in sync: 30 pair(s) byte-identical |
| `/usr/bin/python3 tools/hygiene.py --audit` | `PASS` | `0.29s` | hygiene audit clean: 0 stale scratch items in /tmp/agent-fac |
| `/usr/bin/python3 tools/roadmap.py --audit` | `PASS` | `0.26s` | Product & cadence roadmap clean: 4 canonical products health |
| `/usr/bin/python3 -m pytest tests/test_law_coverage.py` | `PASS` | `5.63s` | ============================== 1 passed in 0.07s =========== |
| `/usr/bin/python3 -m pytest tests/test_session_bindings.py` | `PASS` | `4.88s` | ============================== 1 passed in 0.12s =========== |
| `/usr/bin/python3 -m pytest tests/test_law_structure.py` | `PASS` | `4.9s` | ============================== 1 passed in 0.13s =========== |
| `/usr/bin/python3 tests/test_docs_sync.py` | `PASS` | `0.21s` | docs in sync: 20 shared document(s) byte-identical |
| `/usr/bin/python3 -m pytest tests/test_hygiene_namespace.py` | `PASS` | `7.07s` | ============================== 4 passed in 0.52s =========== |
| `/usr/bin/python3 -m pytest tests/test_audit_rates.py` | `PASS` | `6.57s` | ============================== 9 passed in 2.70s =========== |
| `/usr/bin/python3 -m pytest tests/test_score_gate_recorded.py` | `PASS` | `5.8s` | ============================== 7 passed in 0.16s =========== |
| `/usr/bin/python3 -m pytest tests/test_hq_delegation.py` | `PASS` | `7.34s` | ============================== 1 passed in 0.37s =========== |
| `/usr/bin/python3 -m pytest tests/test_template_integrity.py` | `PASS` | `4.4s` | ============================== 4 passed in 0.26s =========== |
| `/usr/bin/python3 -m pytest tests/test_hygiene_inflight.py` | `PASS` | `9.11s` | ============================== 7 passed in 3.80s =========== |
| `/usr/bin/python3 -m pytest tests/test_close_board_recorded.py` | `PASS` | `6.51s` | ============================== 8 passed in 0.34s =========== |
| `/usr/bin/python3 tests/test_ledger_commit_cites_no_rows.py` | `PASS` | `0.9s` | ledger clause: excused — 2 exempted violation(s) in 743b543. |
| `/usr/bin/python3 tests/test_commit_pathspec_law.py` | `PASS` | `0.28s` | commit pathspec law: clean — the repo law and every committi |
| `/usr/bin/python3 tests/test_criteria_count.py` | `PASS` | `0.52s` | criteria count: clean — 20 claim(s) over 60 file(s) all read |
| `/usr/bin/python3 tests/test_synthesize_interface.py` | `PASS` | `0.78s` | synthesize interface: clean — usage block and argparse agree |
| `/usr/bin/python3 tests/test_roadmap_transition.py` | `PASS` | `2.96s` | roadmap transition: clean — fresh/empty/malformed/incomplete |
| `/usr/bin/python3 tests/test_board_intake_recorded.py` | `PASS` | `0.3s` | board-intake gate passed: 10 check(s) |
| `/usr/bin/python3 tests/test_gate_fixtures_closure.py` | `PASS` | `3.06s` | gate-fixture closure gate passed |
| `/usr/bin/python3 tests/test_ledger.py` | `PASS` | `8.5s` | ledger gate passed |
| `/usr/bin/python3 tests/test_gate_registration.py` | `PASS` | `0.5s` | gate registry passed |
| `/usr/bin/python3 -m pytest tests/test_close_row_revision.py` | `PASS` | `5.67s` | ============================== 13 passed in 0.21s ========== |

---

## 3. Calibration Spot-Check (Sampled Task)

- **Sampled Subject:** `#63`
- **Intake Recorded:** `YES`
- **Claim Lock Recorded:** `YES`
- **Close Verified:** `YES`
- **Sequence Integrity:** `VERIFIED`
