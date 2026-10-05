# Review Cycle 20260927-c1 — Master Verdict

**Status:** COMPLETED

**Opened:** 2026-09-27T21:26:02Z · **Closed:** 2026-10-04T22:17:29Z · **Frozen:** 2026-10-04T22:17:29Z

**Subject:** the meta-factory's own tree — its written law, its tool surface, its ledger. The lens briefs were written for a generic factory; a corpus manifest remapped each lens's scope onto the surfaces that actually exist here.

**Lenses:** 14/14 COMPLETED — the catalogue's first full run since it was authored.

## 1. Census

| Lens | Name / Focus | Status | Report | Bytes |
|---|---|---|---|---|
| **A** | Redundancy, Ontology & Provenance Sediment | `COMPLETED` | `reviews/20260927-c1/reports/lens-A.md` | 25,869 |
| **B** | LLM Efficiency, No-Op Pruning & Responsibility Creep | `COMPLETED` | `reviews/20260927-c1/reports/lens-B.md` | 16,499 |
| **G** | Role File Structure & Checkable Completion | `COMPLETED` | `reviews/20260927-c1/reports/lens-G.md` | 25,613 |
| **J** | Law-to-Tool Migration (The Pure Function Test) | `COMPLETED` | `reviews/20260927-c1/reports/lens-J.md` | 23,848 |
| **P** | Pacemaker & Autonomous Convergence | `COMPLETED` | `reviews/20260927-c1/reports/lens-P.md` | 22,882 |
| **C** | CLI Automation Gaps & Usage Analysis | `COMPLETED` | `reviews/20260927-c1/reports/lens-C.md` | 18,491 |
| **E** | Interface Topology & Command Merging | `COMPLETED` | `reviews/20260927-c1/reports/lens-E.md` | 21,802 |
| **F** | Tool Implementation Quality & Exit Contracts | `COMPLETED` | `reviews/20260927-c1/reports/lens-F.md` | 17,304 |
| **D** | Deletion Safety & YAGNI Pruning | `COMPLETED` | `reviews/20260927-c1/reports/lens-D.md` | 24,186 |
| **H** | Ledger Invariants & Monotonicity | `COMPLETED` | `reviews/20260927-c1/reports/lens-H.md` | 16,386 |
| **M** | Value Stream, Flow & WIP Stagnation | `COMPLETED` | `reviews/20260927-c1/reports/lens-M.md` | 18,046 |
| **T** | Token Economics & Cost-Per-Success | `COMPLETED` | `reviews/20260927-c1/reports/lens-T.md` | 22,672 |
| **I** | Meta-Review & Catalog Brief Integrity | `COMPLETED` | `reviews/20260927-c1/reports/lens-I.md` | 28,791 |
| **S** | Brain Scrub & Cross-Profile Cleanliness | `COMPLETED` | `reviews/20260927-c1/reports/lens-S.md` | 29,935 |

`verify 20260927-c1` → rc=0: census clean across all 14 lenses, 132 accepted finding(s), all accounted for.

## 2. Accepted findings

**132 entries** in `codification_plan` — the 125 findings the 14 lens reports produced, the 6 self-findings this cycle's own apparatus produced while it was being built, and 1 orchestrator observation.

| Disposition | Count | Owes |
|---|---|---|
| `landed` | 4 | home (the file+section it landed in) |
| `routed` | 116 | home (the destination) |
| `rejected` | 12 | reason (the recorded non-fix) |

**Severity, over the 125 lens findings:**

| Severity | Count |
|---|---|
| CRITICAL | 2 |
| SEVERE | 4 |
| HIGH | 26 |
| MEDIUM-HIGH | 3 |
| MAJOR | 2 |
| MEDIUM | 31 |
| LOW-MEDIUM | 2 |
| LOW/MEDIUM | 1 |
| LOW | 15 |
| MINOR | 1 |
| INFO | 2 |
| UNSPECIFIED | 36 |

`UNSPECIFIED` = the three reports that carry no severity at all (lenses A, D, G); they order their findings most-severe-first instead. The brief never required one — codified below as a routed finding against the brief's own format.

| Lens | Findings |
|---|---|
| **A** | 12 |
| **B** | 9 |
| **G** | 13 |
| **J** | 7 |
| **P** | 8 |
| **C** | 9 |
| **E** | 9 |
| **F** | 9 |
| **D** | 7 |
| **H** | 4 |
| **M** | 6 |
| **T** | 8 |
| **I** | 9 |
| **S** | 15 |

## 3. The findings that matter (CRITICAL → MEDIUM-HIGH)

37 of the 125. Each is in its report verbatim, with locator and quote.

- **[CRITICAL] Lens J F1** — The gate that upholds P29 is satisfied by a .md file; nine of 37 practices map only to prose
  - locator: `tests/test_law_coverage.py:146 (map :40, comment :57)`
- **[CRITICAL] Lens T T-1** — Task telemetry is not session-scoped; the 'unit cost per task' is whole-factory spend over an unbounded claim window
  - locator: `tools/ledger.py:1514; tools/telemetry.py:243,286; tools/audit.py:591`
- **[SEVERE] Lens H Finding 1** — Timestamp ordering is non-monotonic, and no mechanism detects it (13 rows out of order; verify prints unqualified 'monotonic')
  - locator: `evidence/ledger.jsonl:1624-1625,:1851-1852,:2147-2148; tools/ledger.py:2230`
- **[SEVERE] Lens M F1** — The factory's own flow acceptance criterion is violated ~46x and is upheld by nothing
  - locator: `docs/processes.md:136`
- **[SEVERE] Lens M F2** — The queue-dwell law is unmeasured, and the one tool whose docstring claims to measure it does not
  - locator: `tools/synthesize_insights.py:255; docs/methodology/02-quality-management.md:37`
- **[SEVERE] Lens M F3** — WIP stagnation is a live livelock: 27 open items past 24h, 20 re-dispatched >=2x, oldest 16.2 days
  - locator: `evidence/ledger.jsonl:237,:2167; tools/patrol_host_state.py:2161`
- **[HIGH] Lens B F1** — state.md is a wall of unbroken 1000-2257-char paragraphs (cognitive load / token weight)
  - locator: `skills/meta-factory/state.md:144 (also :54,:26,:150,:79,:186,:58,:24,:56)`
- **[HIGH] Lens B F2** — Cache Test: ONTOLOGY.md embeds a self-census that is unreproducible and already contradicted
  - locator: `ONTOLOGY.md:530`
- **[HIGH] Lens B F3** — Cache Test: README.md carries 8 raw session UUIDs, one of them measured dead by the factory itself
  - locator: `README.md:94-97, :121-124`
- **[HIGH] Lens C Finding 1** — The live law asserts a tool does not exist that is shipped in the tree; the ruling path bypasses it
  - locator: `skills/meta-factory/state.md:58`
- **[HIGH] Lens C Finding 2** — A documented reproduce command that no longer reproduces, and the file contradicts itself
  - locator: `docs/instruments/kit.md:180-181 (also :113, :523)`
- **[HIGH] Lens E Finding 1** — A law file names a registry.py verb that does not exist (show); ships to every member
  - locator: `skills/meta-factory/SKILL.md:378 (+ TEMPLATE/SKILL.md.tmpl:325)`
- **[HIGH] Lens E Finding 2** — --stdout means 'also write' in one census and 'do not write' in two others
  - locator: `tools/instrument_census.py:358; tools/kit_census.py:559; tools/kit_names.py:394`
- **[HIGH] Lens F Finding 1** — Shell hygiene: neither shell script sets -e; the lens law requires set -euo pipefail
  - locator: `tools/box/oc_questions_push.sh:56; tools/sigpipe_threshold.sh:39`
- **[HIGH] Lens F Finding 2** — audit.py masks a failed ledger stamp with exit 0
  - locator: `tools/audit.py:2922 (return :2924)`
- **[HIGH] Lens F Finding 3** — Atomic journaling: review.py writes its cycle state, report and receipt with no lock, no temp file and no fsync
  - locator: `tools/review.py:901, :1157, :1169`
- **[HIGH] Lens H Finding 2** — Duplicate close/claim rows leave the ledger unable to answer 'closed once or twice?'
  - locator: `evidence/ledger.jsonl:930-931,:1361/:1363,:1502/:1504,:1509/:1511`
- **[HIGH] Lens I F1** — The lens briefs are generated from a SECOND, drifted copy of the lens definitions; review-lenses.md and LENS_METADATA disagree
  - locator: `docs/review-lenses.md (canonical) vs tools/review.py:74-219`
- **[HIGH] Lens I F2** — The 'Quote-or-No-Finding' evidence rule is unenforced: record accepts any non-empty bytes and stamps COMPLETED
  - locator: `tools/review.py:1147-1157`
- **[HIGH] Lens I F3** — The freeze is bypassable: record and waive carry no is_frozen check, so a closed cycle's state.json can be mutated after close
  - locator: `tools/review.py:1127-1191, :1194-1227`
- **[HIGH] Lens J F2** — P26's operator-act count is law with no tool, and the gate it maps to does not implement it
  - locator: `docs/best-practices.md:416,:453; tests/test_law_coverage.py:112`
- **[HIGH] Lens J F3** — Section 5.2's gate-budget re-derivation names no tool, though the tool exists and the cron already calls it
  - locator: `docs/measurement-procedure.md:186-188, :545`
- **[HIGH] Lens J F4** — Section 4.1's 'own-elapsed-slot' cadence predicate is a pure function of cron state, stated as a surveyor computation with no host
  - locator: `docs/measurement-procedure.md:99, :91`
- **[HIGH] Lens P P-1** — The instrument's declared concept has four columns; its gates read two, so 0-token quiescence and goal convergence are ungated
  - locator: `docs/instruments/pacemaker.md:37-42,:211-214; tests/test_cron_thinness.py:277-293; tools/patrol_host_state.py:1188-1191`
- **[HIGH] Lens P P-2** — Live state violates the instrument's own concept and the factory's own patrol is green over it
  - locator: `docs/instruments/pacemaker.md:80-81; live cron_jobs`
- **[HIGH] Lens S S-1** — Dangling cross-reference: the core law points at section 17 for a clause that is section 18
  - locator: `skills/meta-factory/SKILL.md:33`
- **[HIGH] Lens S S-2** — The meta-factory's own section 5 routing table hardcodes three member factories into core law (leak-test class, unenforced)
  - locator: `skills/meta-factory/SKILL.md:253-256`
- **[HIGH] Lens S S-3** — The 'leak test' is a declared mandatory gate with NO mechanism, and two authoritative files define it inconsistently
  - locator: `TEMPLATE/README.md:37-45; docs/addons.md:54-62`
- **[HIGH] Lens S S-4** — Stale member count in law: 'four member factories' vs six enrolled
  - locator: `skills/meta-factory/SKILL.md:493`
- **[HIGH] Lens T T-2** — tokens_out is not output tokens; the schema exposes no output-token column
  - locator: `tools/telemetry.py:181,191`
- **[HIGH] Lens T T-3** — Model right-sizing (lens check 2) has no instrument; 'model' is never read
  - locator: `docs/review-lenses.md:138; docs/processes.md:77`
- **[HIGH] Lens T T-4** — Prompt-cache efficiency (lens check 3) has no instrument; the substrate already records the columns
  - locator: `docs/review-lenses.md:139; tools/telemetry.py:176-192`
- **[MAJOR] Lens M F4** — The census excludes claimed units, and no leg covers 'claimed-but-silent' — Triage's >30 m duty is unmechanized
  - locator: `tools/patrol_host_state.py:2208 vs TEMPLATE/roles/triage.md:23`
- **[MAJOR] Lens M F5** — 'Batch Size Control (P11)' cites a clause that says the opposite, and the check is unmeasurable
  - locator: `docs/review-lenses.md:127 + tools/review.py:186 (vs docs/best-practices.md:177)`
- **[MEDIUM-HIGH] Lens B F4** — Duplication-driven drift: the required_tools set differs between two law surfaces
  - locator: `docs/best-practices.md:643 vs skills/meta-factory/SKILL.md:325`
- **[MEDIUM-HIGH] Lens C Finding 3** — The law declares a standing duty but never names its runner; the runner is invisible to every law surface
  - locator: `docs/measurement-procedure.md:547 (section 5.2)`
- **[MEDIUM-HIGH] Lens I F4** — The 'UNRECEIPTED (no index line)' state is unreachable: verify reads a self-stamped boolean, never the index log
  - locator: `tools/review.py:1168-1172, :1482-1485`

## 4. Codification plan

### landed (4) — the fix is in the tree

- DATE_TOKEN rejects the ISO-8601 instant form (fleet law's mandated dating form)
  - home: tools/review.py DATE_TOKEN (commit 348f758)
- codification_plan was read and initialised but written by nothing, so the schema's own close condition could never be met
  - home: tools/review.py cmd_codify (commit 6c4f42f)
- close --status COMPLETED returned rc=0 over 14 PENDING lenses and over an accepted finding carrying no carrier, so the cycle reached a terminal state on unrun w
  - home: tools/review.py cmd_close (commit 5b2fe9f)
- Lens E Finding 1 (HIGH): the read column named a `registry.py` verb that does not exist (`show`), and the string ships in TEMPLATE/SKILL.md.tmpl so every bootst
  - home: skills/meta-factory/SKILL.md:378 + TEMPLATE/SKILL.md.tmpl:325 (commit a862d47, the dead pointer replaced by the existing verb `resolve`)

### rejected (12) — the recorded non-fix, with its reason

- no gate reads a promotion's close-row declarations (promotion=/naming=/review=/vocabulary= -> 0 files)
  - reason: Owner order 2026-10-04 (MSK 17:37): DROP, superseding the 2026-09-28T19:02:21Z routed entry above. Basis, measured 2026-10-04T14:38:24Z over evidence/ledger.jsonl (2223 rows): the population ruling n=1375 declares — prom
- Lens C SCOPE-NOTE (UNSPECIFIED): Scope note: the brief's generic premises (roles/*.md, processes.md, AGENTS.md) do not exist in this repo
  - reason: scope note, not a fix — the corpus manifest already remapped lens C
- Lens D D-7 (UNSPECIFIED): 494 KB of regenerable derived JSON is committed (YAGNI/bloat; KEEP, but recorded)
  - reason: observation with no action — the report recommends NO action (gates compare against them); KEEP
- Lens E Finding 6 (MEDIUM): A documented trigger command uses a flag hygiene.py does not define (--check)
  - reason: duplicate of C Finding 6 (same locator and defect)
- Lens E SCOPE-NOTE (UNSPECIFIED): Scope/coverage note: no mapped path was absent; Finding 4's telemetry numbers come from a log outside the repo
  - reason: scope note, not a fix — methodological caveat on Finding 4's log source
- Lens F SCOPE-NOTE (UNSPECIFIED): Scope notes: corpus says tests/ holds '89 pytest gate files' (measured 84, 40 pytest-style); shell-hygiene population
  - reason: scope notes, not fixes — premise drift that does not change the findings
- Lens G F1 (UNSPECIFIED): A shipped role card names an 11-lens review while citing the 14-lens catalogue; the count is un-gated
  - reason: duplicate of A F6 (same locator and defect)
- Lens G F10 (UNSPECIFIED): SKILL.md section 11 states every instrument ships as a doc pair, contradicted by insights
  - reason: duplicate of A F10 (same locator and defect)
- Lens G SCOPE-FINDING (UNSPECIFIED): Scope/coverage finding: the CORPUS manifest omits TEMPLATE/roles/*.md while asserting those paths are absent
  - reason: scope note, not a fix — add TEMPLATE/roles/*.md to Lens G's read set
- Lens J F7 (INFO): Section 5.2 declared a third trigger that was unreachable until 007d959; a law stating a mechanism that could not fire (resolved)
  - reason: INFO, resolved — verified fixed at 007d959; no outstanding code action
- Lens P COVERAGE-NOTE (UNSPECIFIED): Coverage note: no cron/pacemaker section exists in SKILL.md; lens P audited docs/instruments/pacemaker.md instead
  - reason: scope note, not a fix — the operative pacemaker law lives in docs/instruments/pacemaker.md
- Lens S S-14 (LOW): state.md:51 opens with a stray '_ ' token (malformed markdown / unclosed emphasis)
  - reason: duplicate of G F12 (same locator and defect)

### routed (116) — destination named

| Destination owner | Findings routed |
|---|---|
| Meta-Factory HQ (its own law surfaces) | 51 |
| this lane's own surface (review instrument) | 13 |
| other tool lanes (census / shell scripts / insights synth) | 9 |
| the Hygiene instrument lane | 7 |
| the Ledger instrument lane | 5 |
| the Pacemaker instrument lane | 5 |
| the telemetry / brain_metrics lane | 5 |
| the Audit tool lane | 4 |
| the Patrol / Triage lanes | 3 |
| a proposal's owner | 2 |
| the Open Questions instrument lane | 2 |
| the Insights instrument lane | 2 |
| the Review-Rotation instrument lane | 2 |
| the Ledger instrument lane (this cycle's close row) | 1 |
| the promotion close-row gate (dropped — see rejected) | 1 |
| the Kit instrument lane | 1 |
| the Roadmap tool lane | 1 |
| the Registry tool lane | 1 |
| the ledger/telemetry lane (shared) | 1 |

The full 132 entries, each with its carrier, are the machine-readable record in `reviews/20260927-c1/state.json` → `codification_plan`.

## 5. What this run already changed in shipped law

- **Lens E Finding 1 (HIGH)** — the read column named a `registry.py` verb that does not exist (`show`). Routed to HQ, verified, and landed in both halves at **`a862d47`** (`skills/meta-factory/SKILL.md:378` + `TEMPLATE/SKILL.md.tmpl:325`; the intended verb was `resolve`). Before the fix every factory bootstrapped from this repo inherited a command that cannot run.

## 6. Method notes and open items

- **The brief never requires a severity.** 3 of 14 reports (A, D, G) therefore carry none, and 36 of 125 findings have no common ordering key for cross-lens triage. Codified and routed to `tools/review.py:1102` (the brief's REQUIRED FINDINGS FORMAT).
- **The corpus manifest is ephemeral.** The per-lens remapping that made this run possible lived at `/tmp/rr-c1/CORPUS.md` and is not committed; the cycle's own `corpus` field reads `pack_status: absent`. Lens G's read set omitted `TEMPLATE/roles/*.md` while asserting those paths absent — the lens read them anyway. A method note for the next run, not a shipped surface.
- **Close basis.** The register question `meta-factory q29` was answered "close `--status ABANDONED`" at 2026-10-04T20:44:33Z, twelve minutes after the owner's typed instruction "Run the 14 lenses" (20:32:48Z). The register answer's stated basis was cost — *"cheaper, lawful today"* — which is void once the run is done; writing `ABANDONED` over a completed census would make the record lie, the exact class this instrument exists to prevent. Closed **COMPLETED** on the typed order and the clean census. Recorded here so the basis is auditable.
- **12 findings target this lane's own instrument** (`tools/review.py`, `docs/review-lenses.md`): atomic journaling (no lock/temp/fsync), the freeze bypass in `record`/`waive`, the unenforced quote-or-no-finding rule, `verify` reading a self-stamped receipt instead of the index log, and the `LENS_METADATA` drift from the catalogue. They are recorded `routed`, not `landed`: none is applied yet, and `CODIFICATION_OBLIGATIONS` defines `landed` as the file+section a finding **landed** in. They are the immediate follow-on work.
- **Already open, not this cycle's:** `#263` (census second reader), HQ's `kit`/`instruments` vocabulary collision, the 11/5-vs-14/6 catalogue divergence between `docs/methodology/02-quality-management.md` §4 and the shipped `CATALOG_LENSES`, and `test_review.py` still executing nowhere in the aggregate audit.

## 7. Evidence

The 14 reports are the evidence and the source of every finding above: `reviews/20260927-c1/reports/lens-{A,B,C,D,E,F,G,H,I,J,M,P,S,T}.md`. Each finding's locator, verbatim quote and remediation are in its report; each finding's disposition and carrier are in `state.json`.
