# review-lenses.md — The Generic 14-Lens Factory Review Catalog

> **Owns:** Canonical catalog of the 14 review lenses for periodic factory quality reviews (Duty 4+6 review rotation / **P32**).
> **Methodology Reference:** `docs/methodology/02-quality-management.md` §4.

Periodic multi-lens reviews prevent process decay, law bloat, tool rot, ledger drift, and token waste.

**The Adversarial Isolation Requirement:** Review lenses must be executed by **dedicated adversarial sub-agents** spawned with clean, unpolluted context windows and explicit adversarial briefs (`tools/review.py brief <LENS>`). The primary authoring lane naturally suffers from conversational self-confirmation bias; an isolated sub-agent enters without authorial baggage and is primed specifically to detect flaws, prompt bloat, and un-gated rules.

---

## 🏛️ Family 1: DOCS & LANGUAGE (Role Cards, Directives, Procedures)

### Lens A — Redundancy, Ontology & Provenance Sediment
- **Scope:** All role cards (`roles/*.md`), process registers (`processes.md`), and process law (`SKILL.md`).
- **Core Checks:**
  1. **Rule Duplication:** Find the same requirement or constraint stated twice across different files.
  2. **One Concept = One Name:** Enforce single canonical terms (from `ONTOLOGY.md`). Flag synonyms, colloquial aliases, and undefined coinages.
  3. **Provenance Sediment:** Live rule text must carry the **current rule only**, never its historical biography. Incident dates, post-mortem anecdotes, owner quotes, and "first pass shipped" notes belong in `CHANGELOG.md` or `evidence/rework.md`.
  4. **Post-Migration Path Sweep:** Verify old paths, moved files, or retired CLI flags do not linger as dead references in instructions.
  5. **Enumeration Consistency:** Counts of steps, tools, gates, or phases stated in prose must match their actual definitions.
- **Evidence Format:** File path + line locator + verbatim quote of duplicate or sedimental text.

### Lens B — LLM Efficiency, No-Op Pruning & Responsibility Creep
- **Scope:** Token weight, role focus, and cognitive load across role instructions.
- **Core Checks:**
  1. **Responsibility Creep:** Role files must contain only what the executing role needs. (A worker should not load HQ dispatch procedures).
  2. **The No-Op Test:** Test sentences against pre-trained model defaults. If a line instructs the model to do what it already does naturally, it is paying token load for zero behavioral change.
  3. **The Cache Test:** Environment state (config files, scripts, CLI `--help`) is already truth. A markdown document restating CLI flags or directory listings is a cache that drifts. Document what cannot be found by inspection.
  4. **The Negation Test:** Avoid steering solely by prohibition (which drags forbidden concepts into active context). State positive targets and actionable boundaries.
  5. **Subsumed Procedure Pruning:** When a composite tool or script ships (e.g. `audit.py`), prune the lower-level manual plumbing rituals from role instructions. Document only the milestone command.
  6. **Progressive Disclosure:** Lengthy references belong behind linked pointers or separate docs, not in the primary execution loop.
- **Evidence Format:** File locator + verbatim quote + estimated token savings / structural critique.

### Lens G — Role File Structure & Checkable Completion
- **Scope:** Cohesion, work sequence, and exit criteria within each role file.
- **Core Checks:**
  1. **Section Cohesion:** One section = one operational concern.
  2. **Checkable Completion Criteria:** Every step in a role procedure must terminate on a deterministic, checkable condition (e.g. `DONE = exit 0 from test_x.py + row stamped in ledger`). Vague completion criteria invite premature termination.
  3. **Load Path Integrity:** Verify that moved or split sections remain reachable across context compactions. Confirm that recovery anchors in `AGENTS.md` point to the correct files.
- **Evidence Format:** File locator + section header + critique of work sequence or exit ambiguity.

---

## ⚙️ Family 2: MECHANICAL & PROTOCOL (Law Migration & Dispatch)

### Lens J — Law-to-Tool Migration (The Pure Function Test)
- **Scope:** The entire corpus of written factory law and directives.
- **Core Checks:**
  - Read every directive as a specification of **who decides**, asking: **Is this decision a pure function of state on disk?**
  - **The Three-Part Test:**
    * **T1:** The decision depends purely on git tree, files, environment, or ledger state (no human judgment or client taste).
    * **T2:** A CLI script or mechanical test already exists or is the natural host.
    * **T3:** The rule currently instructs an **agent** to remember, derive, or manually check that state.
  - **Verdict:** If T1–T3 hold, the rule is an **unwritten tool specification**. Prose instructions must be migrated into a deterministic tool, hook, or unit test.
- **Exclusions:** Irreversible human gates (P14), approval checkpoints, and client subjective decisions belong in prose/gates.
- **Evidence Format:** Verbatim rule quote + state read on disk + proposed tool command/test.

### Lens P — Pacemaker & Autonomous Convergence
- **Scope:** Cron configuration, outer heartbeat loops, and autonomous task convergence.
- **Core Checks:**
  1. **0-Token Quiescence (P28):** Pacemaker crons on quiescent/idle queues must use `trigger_cmd` short-circuits (`trigger_on=non_empty` or `exit_zero`) to wake sessions only when work is pending. Zero LLM tokens may be billed for empty checks.
  2. **Goal State Convergence:** Sessions waking under automated crons must run against explicit deterministic goal conditions (`set_goal: true`), converging to terminal exit without human nudges.
  3. **Dead Session Detection:** Verify crons target live session UUIDs and do not push into dead subagent queues or unbound topics.
- **Evidence Format:** Cron identifier + trigger command exit analysis + token billing log confirmation.

---

## 🔧 Family 3: TOOLS & INTERFACES (Scripts, Commands, Gates)

### Lens C — CLI Automation Gaps & Usage Analysis
- **Scope:** Manual procedures and actual tool invocation telemetry (`tools.log`, ledger records).
- **Core Checks:**
  1. **Automation Gaps:** Detect recurring multi-step manual commands in role workflows that should be unified into a single CLI utility.
  2. **Usage Telemetry:** Analyze command frequency, error code distributions (tools clustering on error exits indicate broken interfaces), and uninvoked legacy tools (YAGNI deletion candidates).
- **Evidence Format:** Proposed CLI utility signature + replaced manual steps + supporting ledger/log citations.

### Lens E — Interface Topology & Command Merging
- **Scope:** The CLI tool surface across `tools/`.
- **Core Checks:**
  1. **Chained Invocations:** Pairs or triads of tools that are always executed in immediate succession without intermediate judgment gates (candidates for merging).
  2. **Duplicate Interfaces:** Overlapping flags or verbs performing similar lookups across different scripts.
- **Evidence Format:** Tool names + duplicate/chained interfaces + suggested consolidated command syntax.

### Lens F — Tool Implementation Quality & Exit Contracts
- **Scope:** Source code of scripts in `tools/` and test runners in `tests/`.
- **Core Checks:**
  1. **Exit Code Determinism:** Success must exit `0`. Failures must exit distinct non-zero codes. No soft errors masked by exit `0`.
  2. **Shell Hygiene:** Shell scripts must enforce strict error trapping (`set -euo pipefail`), quote variable expansions, and avoid non-portable constructs.
  3. **Atomic Journaling:** Tools performing state changes must write their journal or ledger entry atomically before or alongside the mutation.
- **Evidence Format:** Script file:line locator + defect analysis + proposed patch.

### Lens D — Deletion Safety & YAGNI Pruning
- **Scope:** File tree, state directories, scratch files, and legacy configurations.
- **Core Checks:**
  1. **Orphan Detection:** Enumerate stale, retired, or unreferenced files, mock fixtures, and temporary artifacts.
  2. **Reference Counting:** Search codebase, scripts, crons, and docs for references. Classify each candidate:
     - `DELETE-SAFE`: Zero references found; verified safe to remove.
     - `ARCHIVE`: Historical value; move to archive/rework record.
     - `KEEP`: Active reference found.
  3. **Guard:** "Looks stale" is a hypothesis, never a verdict. Removal requires verified zero references.
- **Evidence Format:** Target file path + search query used + reference verification proof.

---

## 📦 Family 4: ARTIFACTS, STATE & FLOW (Files, Ledgers, WIP)

### Lens H — Ledger Health & Lifecycle Invariants
- **Scope:** `evidence/ledger.jsonl` (or factory work state store).
- **Core Checks:**
  1. **Lifecycle Sequence:** Verify tasks follow the complete lifecycle (`intake` → `claim` → `close`). Flag orphan claims or closes lacking intake.
  2. **Sequence Monotonicity:** Confirm integer sequence numbers ($n=1, 2, \dots$) and monotonically advancing timestamps.
  3. **Contradiction Pairs:** Detect conflicting event records or duplicate task identifiers.
  4. **Lesson Extraction Parity:** Confirm that major incidents noted in ledger rows have corresponding codified entries in `evidence/rework.md`.
- **Evidence Format:** Ledger row number $n$ + violated invariant + verifying command output.

### Lens M — Value Stream, WIP Stagnation & Lead Time
- **Scope:** Active work items, backlog turnover, and work-in-progress (WIP) age.
- **Core Checks:**
  1. **WIP Stagnation:** Detect tasks parked in `intake` or `claim` without closing for >24 hours.
  2. **Lead Time Drift:** Track mean lead time ($T_{\text{intake}} \to T_{\text{close}}$) over successive cycles; flag upward trends indicating pipeline bottlenecks.
  3. **Batch Size Control (P11):** Enforce small task batching. Flag tasks touching >3 files or >200 lines without explicit architectural decomposition.
- **Evidence Format:** Task identifier + timestamp delta ($T_{\text{dwell}}$) + bottleneck diagnosis.

---

## 💰 Family 5: ECONOMICS & TELEMETRY (Cost, Context, Models)

### Lens T — Token Economics & Cost-Per-Success
- **Scope:** Model usage, token consumption logs, prompt caching efficiency, and operational expenditure.
- **Core Checks:**
  1. **Unit Cost Analysis:** Compute and track unit cost-per-successful-task ($\text{USD}/\text{task}$) across workflows.
  2. **Model Tier Right-Sizing:** Verify that heavy reasoning models (high cost) are not assigned to mechanical triage or deterministic formatting tasks where lightweight models suffice.
  3. **Prompt Cache Efficiency:** Audit static instruction prefixes to ensure high prompt cache hit rates (>80%) and eliminate cache-busting dynamic timestamps in primary system prompts.
  4. **Context Inflation Guard:** Audit turn context growth; trigger compaction or subagent delegation before context sizes exceed cost-effective thresholds.
- **Evidence Format:** Workflow name + token breakdown (input/output/cache) + unit cost vs. budget target.

---

## 🔍 Family 6: META & GOVERNANCE (Review Mechanics, Scope Cleanliness)

### Lens I — Meta-Review of the Lens Catalog
- **Scope:** This catalog (`review-lenses.md`) and historical review cycle outputs.
- **Core Checks:**
  1. **Scope Drift:** Verify lens briefs match what reviewers actually evaluate.
  2. **Overlap Detection:** Identify findings redundantly claimed by multiple lenses.
  3. **Evidence Discipline:** Enforce the "Quote-or-No-Finding" rule. Reject vague impressions lacking specific locators and quotes.
- **Evidence Format:** Catalog section + observed drift/overlap pattern.

### Lens S — Brain Scrub & Profile Scope Cleanliness
- **Scope:** External agent profile brain files (`AGENTS.md`, `SOUL.md`, `TOOLS.md`) vs. factory repos.
- **Core Checks:**
  1. **P25 Isolation Enforcement:** Ensure factory-specific process rules do NOT leak into shared agent profile brain files.
  2. **Pointer Discipline:** Shared profile files may carry only one-line pointers and recovery anchors back to the factory skill.
  3. **Provenance Sweep:** Verify that directives found in passive memory (`MEMORY.md`) are properly re-homed into versioned factory process files.
- **Evidence Format:** Profile file locator + leaked factory directive + suggested clean pointer.

---

## 🔄 Review Cycle Execution Workflow

```
[Trigger Cadence] → [HQ Inits reviews/<cycle-id>/state.json]
       ↓
[Spawn Independent Read-Only Reviewers across 14 Lenses]
       ↓
[Persist Reports to reviews/<cycle-id>/reports/lens-<X>.md]
       ↓
[HQ Triple-Checks Findings: Disk Truth + Evidence + Coherence]
       ↓
[HQ Compiles Master Verdict: reviews/<cycle-id>/verdict.md]
       ↓
[HQ Codifies Mechanical & Doc Fixes in Single Version Batch]
       ↓
[HQ Resets Cadence Stamp in Ledger]
```
