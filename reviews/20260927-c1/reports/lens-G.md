# LENS G — Role File Structure & Checkable Completion

**Cycle:** 20260927-c1 · **Auditor:** isolated adversarial lane (zero shared context with the authoring lane)
**Repo under review:** `/root/agent-factories` (READ-ONLY throughout — no file under the repo was modified, created or deleted by this audit)
**Surfaces audited (per `CORPUS.md` per-lens mapping for G):** `skills/meta-factory/SKILL.md`, `skills/meta-factory/state.md`, `skills/meta-factory/verdicts-and-claims.md`, `docs/instruments/*.md` (8 docs) — **plus** `TEMPLATE/roles/*.md` (see Scope Note).
**Lens targets:** (1) section cohesion — one section = one concern; (2) checkable completion — every procedure terminates deterministically; (3) load-path integrity — role paths and recovery anchors survive compaction.

---

## Scope Note — the manifest's mapping is narrower than the lens, and its premise is factually wrong

`CORPUS.md` states the lens briefs "name `roles/*.md` … **Those paths do not exist in this repo**" and maps Lens G onto four law surfaces. That premise is false: the repo carries four role cards, `TEMPLATE/roles/{hq,triage,worker,carrier}.md` (measured: `ls TEMPLATE/roles/` → 4 files; `wc -l` → 314 lines total). They are the repo's literal "role files", they ship to every bootstrapped factory, and the ledger's core actor set is defined as "the template's four cards plus `owner`" (`skills/meta-factory/SKILL.md:123`). I therefore audited them as a **secondary surface**, flagged as such. Findings **F1, F2 and F5** below are on role cards. The manifest-mapping gap is itself a coverage defect: a review lens mapped away from the surface it exists to inspect. **Remediation:** add `TEMPLATE/roles/*.md` to Lens G's read set and correct the "do not exist here" premise.

---

## Findings (most severe first)

### F1 — A shipped role card names an 11-lens review while citing the 14-lens catalogue; the count is un-gated and the mismatch is a known live defect

**File Locator:** `TEMPLATE/roles/hq.md:19-20`
**Verbatim Quote:**
```
- Governs periodic process evolution: orchestrates periodic multi-lens reviews
  (the 11-lens review, **P32** / `docs/review-lenses.md`), triple-checks findings,
```
**Defect Analysis.** The cited document, `docs/review-lenses.md`, defines **14** lenses (`grep -c '^### Lens ' docs/review-lenses.md` → 14: A,B,G,J,P,C,E,F,D,H,M,T,I,S). `tools/review.py:72` agrees (`CATALOG_LENSES = ["A","B","G","J","P","C","E","F","D","H","M","T","I","S"]`, 14 entries), and `docs/instruments/review-rotation.md:100,300` both say "14". The card's "11" is the count of the *methodology core's* superseded catalogue (`docs/methodology/02-quality-management.md:90` "Periodic **11-Lens** Factory Review"; `:104` "The 11 Review Lenses" — missing M, P, T). So a shipped role card instructs HQ to run an 11-lens review while naming the 14-lens file as its authority: the name contradicts its own citation. This is a live, previously-filed defect left unfixed in the card — `evidence/reviews/2026-09-27-review-rotation-vocabulary.md:43` (finding V1) already measured "**Two incompatible lens catalogues are live in the same corpus.** The shipped catalogue is **14 lenses / 6 families**; the methodology core describes an **11-lens** review over **5 families**." No gate reads the number (`grep -rn "11-lens"` finds it only in `hq.md:20` and two evidence records; `tests/test_law_structure.py` checks only heading contiguity; `tests/test_law_coverage.py` checks only that P32's target *exists*), so the stale count survives compaction and ships to every new factory.
**Actionable Remediation.** Change `TEMPLATE/roles/hq.md:20` to "the **14-lens** review"; and either delete the methodology core's duplicate catalogue (`docs/methodology/02-quality-management.md:90-109`) in favour of a pointer to `docs/review-lenses.md`, or add a gate asserting one catalogue count across the corpus (V1's routed owner is HQ).

---

### F2 — A shipped role card orders an ACK that the factory's own law names as forbidden — an un-gated directive contradicting the notification law

**File Locator:** `TEMPLATE/roles/worker.md:14`
**Verbatim Quote:**
```
4. Report & Stamp           what changed, evidence, stamp ledger close (Rail 2) + ack back (Rail 1)
```
**Defect Analysis.** `skills/meta-factory/SKILL.md:156-157` states "**A NOTIFICATION MUST CARRY A STATE CHANGE OR AN ASK — a bare acknowledgment is neither, and is NOT SENT (owner order 2026-10-03: …**", and `SKILL.md:169-170` says "The receipt for a dispatch, a wave, a freeze or a law-change is the **ledger row**, never a reply: the sender reads …". The shipped role card therefore instructs every Worker in every bootstrapped factory to send a bare "ack back" — the exact defect class the meta-factory's own law was ordered against. The upholder is only prose living in a *different* file the Worker is not told to load: `worker.md:4` declares "**Loads:** this card + the process law. Not the other role cards." So the contradiction is real on the Worker's own load path and un-gated (`grep -rn "ack back"` finds it only in the card; no test reads role cards for ack directives).
**Actionable Remediation.** Change step 4 to `Report & Stamp — what changed, evidence, stamp the ledger close (Rail 2). No reply is sent: the close row is the receipt.` Optionally add `tests/test_role_cards_no_ack.py` asserting no role card instructs an acknowledgement.

---

### F3 — Two law files cite another factory's tree by a repo-relative path that resolves to nothing here

**File Locator:** `skills/meta-factory/state.md:188` (and the same shape at `docs/instruments/open-questions.md:7`, `:118`)
**Verbatim Quote (state.md:188):**
```
Canonical clause (full contract, verbs, store path): `docs/instruments/open-questions.md` — the instrument's own law; `skills/opencrabs-dev/fleet-directives.md` keeps a `[LANE]` pointer only.
```
**Verbatim Quote (open-questions.md:118):** `Tool: `skills/opencrabs-dev/tools/state/oc-questions` — verbs …`
**Defect Analysis.** Both paths are written bare, with no document/owner qualifier, and neither resolves from this repo. Measured: `ls skills/opencrabs-dev` → *No such file or directory*; `ls tools/questions` → *No such file or directory*; the real files live in a **different profile tree** — `/root/.opencrabs/profiles/ops/skills/opencrabs-dev/fleet-directives.md` and `…/opencrabs-dev/tools/state/oc-questions` (both verified present). This is the load-path hazard the lens exists to catch: `state.md` is reloaded across compaction as the operative home of the State law, and the clause names a `[LANE]` pointer a compacted reader is told to rely on — but the printed path resolves only if the reader silently substitutes a foreign profile root. The law's own citation rule (`skills/meta-factory/verdicts-and-claims.md:51`: "A citation is resolvable by a reader who holds ONLY this document") is violated by its own sibling.
**Actionable Remediation.** Replace the bare paths with the profile-qualified form (or a resolved-at-call-time lookup), e.g. `state.md:188` → "`~/.opencrabs/profiles/ops/skills/opencrabs-dev/fleet-directives.md` keeps a `[LANE]` pointer only (outside this repo)"; and `open-questions.md:118` likewise. Optionally add a gate that scans law files for `skills/<other-factory>/…` paths that do not resolve.

---

### F4 — The questions-register instrument's declared set is half-absent in the source tree, and its named writer lives in another factory's tree

**File Locator:** `docs/instruments/open-questions.md:34-35`
**Verbatim Quote:**
```
| 1 | `tools/questions` ↔ `TEMPLATE/tools/questions` | `standalone` | **the executable** — every verb: `ask` · `answer` · `amend` · `notify` · `list` · `publish` · `lint` · `gc` · `selftest` |
| 2 | `tools/questions-render.mjs` ↔ `TEMPLATE/tools/questions-render.mjs` | `standalone` | **the render asset**, resolved beside the binary …
```
**Defect Analysis.** §2 declares these as the *root halves* of the pair, and §2's stated purpose is that "a reader holding this file and a tree can answer *'is this instrument complete here?'*". In **this** tree the answer is NO for two of the four declared paths: `tools/questions` and `tools/questions-render.mjs` do not exist (measured: `ls tools/questions*` → *No such file or directory*; only the `TEMPLATE/` halves exist). The repo's own census agrees — `evidence/instrument-census-open-questions-2026-09-29.md` reads `meta-factory … 2/4 … SOURCE`. Meanwhile the meta-factory's law names `oc-questions` as the authoritative writer of the register surface (`SKILL.md` §11 surface table; `state.md` open-questions clause), and that tool resolves only at `…/profiles/ops/skills/opencrabs-dev/tools/state/oc-questions` — a path this repo neither owns nor gates. §5.4 does permit "reaching a shared copy" as an adoption shape, but §2's table does not encode that decision, so §2 and §5 disagree about whether the root half is owed.
**Actionable Remediation.** Make §2 state the adoption explicitly: mark rows 1–2 as `shared-copy` (naming the resolved `…/opencrabs-dev/tools/state/oc-questions` path), or add a line "the meta-factory reaches a shared copy; the root halves are absent-by-design", so the declared set and the census `2/4` reading tell one story.

---

### F5 — A watchdog procedure terminates on an undefined variable (`*N* cycles`), and its two mentions disagree in shape

**File Locator:** `TEMPLATE/roles/triage.md:23-24` (repeat at `:67`)
**Verbatim Quote:**
```
  - **CLAIMED-BUT-SILENT** — a worker holding a claim with no progress/update after
    *N* cycles or > 30 m. Notify that worker through `session_notify`, or escalate to `HQ`.
```
```
   If CLAIMED-BUT-SILENT (> 30m)  → notify the worker via `session_notify` / escalate to HQ.
```
**Defect Analysis.** The same bullet names one deterministic bound (`> 30 m`) and one symbolic placeholder (`*N* cycles`) that is **defined nowhere in the card, in `skills/meta-factory/SKILL.md`, or in `state.md`** (`grep -rn "N\* cycles\|N cycles"` → only this line). Lens target (2) requires every procedure to terminate on deterministic conditions; a predicate with a free variable cannot be executed or falsified, so the watchdog leg is advisory. The two mentions also disagree in shape: `:23-24` says "*N* cycles or > 30 m" while `:67` says only "> 30m" — a reader cannot tell whether the cycle bound is load-bearing or vestigial.
**Actionable Remediation.** Delete `*N* cycles` and keep the measured `> 30 m`, or replace it with a declared constant (`> 2 sweep cycles of the factory-triage-patrol cadence, `0 */6 * * *` UTC`). Make `:67` match.

---

### F6 — Section cohesion: `SKILL.md` §4 "Briefing and dispatch" also carries git-commit and worktree discipline

**File Locator:** `skills/meta-factory/SKILL.md:151` (heading), `:219`, `:227`
**Verbatim Quote (heading + the two misplaced clauses):**
```
## 4. Briefing and dispatch
… **Name your paths at the commit, not only at the stage.** This tree is shared, and a bare
… **The shared tree is a READ surface; work happens in a worktree.** The tree every lane can
```
**Defect Analysis.** §4 is titled for one concern — how work is briefed and dispatched — but its body carries at least four: (a) the notification-content law (`:155-188`), (b) board-intake ordering and the claim/intake race ruling (`:183-217`), (c) **git commit-pathspec discipline** (`:219`), and (d) **shared-tree vs worktree discipline** (`:227`). Clauses (c) and (d) are repository/git hygiene, not briefing: a lane looking for the commit-pathspec rule will not look under "Briefing and dispatch", and a lane reading §4 for how to brief a lane is handed a worktree rule it did not ask for. Lens target (1) — "one section equals one operational concern" — is not met. (The same shape recurs at §11, which mixes the surface table, instrument-reload mechanics, the authorship/transcription split, the derived-figure rule and a whole paragraph on the hygiene instrument, `SKILL.md:353-407`.)
**Actionable Remediation.** Extract clauses (c) and (d) into a new section, e.g. "## N. Commit and shared-tree discipline", leaving §4 to briefing/dispatch only. If section numbers must stay contiguous (guarded by `tests/test_law_structure.py`), renumber downstream and bump the file `version:` in the same commit.

---

### F7 — `pacemaker.md` §10 claims a law home it has not taken, and the pending extraction has no exit criterion

**File Locator:** `docs/instruments/pacemaker.md:588-610`
**Verbatim Quote:**
```
## 10. Where this instrument's law lives
This file is the instrument's law home. The law it **takes over** is currently stated elsewhere, and
the move is deliberately not in this commit:
…
to HQ, and **until it lands, SKILL.md remains the operative home and this file is its declaration and
its citation target.** This file does not claim a move it did not make.
```
**Defect Analysis.** The instrument's own law for the **duty receipt** and the **redirect log** still lives in `skills/meta-factory/state.md` (verified: `state.md:18-26` carries the `receipt_subject` / `duty=` / `DUTY_DOMAIN` contract), while `pacemaker.md:590` opens by calling itself "the instrument's law home". The move is declared "deliberately not in this commit" with no owner, no date and no completion test — a procedure that does not terminate on a deterministic condition, which is exactly lens target (2). The consequence is a split law home: a lane writing a duty receipt must read `state.md` for the contract and `pacemaker.md` for its surfaces, and the "law home" claim at `:590` is contradicted by `:610` in the same section. Compaction makes this worse: the reader re-loads whichever doc the reload link surfaces and finds a half-law.
**Actionable Remediation.** Either land the extraction (move the `state.md:18-26` clauses into `pacemaker.md` §9/§10 and leave a pointer row naming the enforcing line), or rewrite §10 to state the pending move as a declared obligation with an owner and a checkable exit criterion, and drop the "This file is the instrument's law home" sentence until it is true.

---

### F8 — Dangling in-file anchor: "(Section 10 Standard)" resolves to the wrong section of its own file

**File Locator:** `skills/meta-factory/SKILL.md:323`
**Verbatim Quote:**
```
> **Context-Manifest Curation (Section 10 Standard):** In the compaction prompt manifest, explicitly
```
**Defect Analysis.** The clause sits in `SKILL.md` §9 ("After a context compaction", `:312`) and cites "Section 10" as its standard. In **this** file §10 is `## 10. Add-ons in force` (`:335`) — a reader who follows the anchor lands on add-ons, not on manifest curation. The phrase was carried over from the template, where §10 genuinely *is* the manifest section (`TEMPLATE/SKILL.md.tmpl:256` "## 10. Context compaction, manifest curation & recovery"); the meta-factory file starts at §0, so its §10 is a different clause. `tests/test_law_structure.py` guarantees section numbers are contiguous but never checks that a reference *resolves*, and `tests/test_citation_clause_titles.py` scans only `tools/`, `tests/` and their TEMPLATE twins — **not** `skills/` — so a law file's own bare section reference is un-gated. This is the load-path/anchor class: a compaction-recovery instruction whose anchor is wrong is worse than absent, because it reads as resolved.
**Actionable Remediation.** Replace "(Section 10 Standard)" with a resolvable citation — e.g. "the Section-10 context-manifest standard (`docs/methodology/04-harness-binding.md` §9)" — per the citation law the file itself states.

---

### F9 — The role cards' `Rail 1/2/3` jargon is undefined on the load path the cards declare

**File Locator:** `TEMPLATE/roles/worker.md:11,14` and `TEMPLATE/roles/triage.md:51,67`
**Verbatim Quote:**
```
1. Receive push brief       dispatched via Rail 1 push goal (session_notify): issue number, goal, done-criteria
4. Report & Stamp           what changed, evidence, stamp ledger close (Rail 2) + ack back (Rail 1)
## The claim and dispatch loop (Dual-Rail Push Handoff)
   If CLAIMED-BUT-SILENT (> 30m)  → notify the worker via `session_notify` / escalate to HQ.
```
**Defect Analysis.** `grep -rn "Rail" skills/meta-factory/` returns **zero** hits — the meta-factory's own law (the "process law" a lane in THIS factory loads) never defines Rail 1/2/3. The definitions live in `TEMPLATE/processes.md.tmpl:45-48` (Rail 1 = `session_notify` goal push; Rail 2 = `evidence/ledger.jsonl` under `fcntl.flock`; Rail 3 = the watchdog sweep) and `docs/methodology/04-harness-binding.md`. A Worker bootstrapped from this template is told to load "this card + the process law" (`worker.md:4`); three of its steps name an undefined transport, and the card conflates the rails with the ledger close (`stamp ledger close (Rail 2)`) without saying which file owns Rail 2.
**Actionable Remediation.** Add a one-line gloss in each card (`Rail 1 = session_notify push goal; Rail 2 = evidence/ledger.jsonl under fcntl.flock; Rail 3 = the watchdog sweep; defined in docs/methodology/04-harness-binding.md`), or replace the Rail names with the mechanisms themselves.

---

### F10 — `SKILL.md` §11 states every instrument "ships as a doc pair", contradicted by `insights`

**File Locator:** `skills/meta-factory/SKILL.md:360`
**Verbatim Quote:**
```
… The contract for an instrument — its verbs, store path, gates and closure — ships as a doc pair (`docs/instruments/<instrument>.md` + `TEMPLATE/docs/instruments/<instrument>.md`) …
```
**Defect Analysis.** The statement is absolute ("ships as a doc pair"), but the corpus has an exception: `docs/instruments/insights.md` has **no** `TEMPLATE/` half (`ls TEMPLATE/docs/instruments/` → 7 files, no `insights.md`; `ls docs/instruments/` → 8), and `insights.md` §2 declares "**No path in this instrument ships — the declared set is empty.**" The frame carves this out explicitly (`docs/instruments/template-instruments.md` §6.3 "A law doc may be home-factory-only — and the reload leg is NOT waived with the pair"). So the authority file (`SKILL.md`, which §11 says is "the authority") states a rule its own instance violates, without the §6.3 exception — a cohesion defect where a general law and its exception live in different files and the reader of the authority is not told.
**Actionable Remediation.** Add the exception to `SKILL.md:360`: "… ships as a doc pair — **except a home-factory-only instrument (frame §6.3), whose doc is root-only and reloads from `docs/instruments/`**".

---

### F11 — Cross-reference off by one: `insights.md` cites `test_instrument_census.py` "arm 6" for a check that is ARM 7

**File Locator:** `docs/instruments/insights.md:45`
**Verbatim Quote:**
```
… the census refuses by design (`test_instrument_census.py` arm 6 — a zero parsed declared set is a refusal, never a clean census).
```
**Defect Analysis.** In `tests/test_instrument_census.py` the arms are labelled in comments: ARM 6 is "a lawful DEFERRAL (with its reason) is a state, not a failure"; the zero-parsed-set refusal is **ARM 7** ("a law doc whose declared-set table does not parse is a REFUSAL, not an empty census"). The doc's own tool-facing claim is therefore checkable and wrong: a reader validating the claim against the test's arm 6 finds the opposite behaviour. The doc states the correct count for its sibling elsewhere (`review-rotation.md` cites "15 checks", matching the test's 15 `check(...)` calls), so the arm-number drift is local to this citation.
**Actionable Remediation.** Change "arm 6" → "arm 7" in `insights.md:45`, or cite the arm by its name ("the zero-parsed-set refusal arm") so it survives reordering.

---

### F12 — `state.md:51` is a malformed markdown list item (leading `_` instead of `-`)

**File Locator:** `skills/meta-factory/state.md:51`
**Verbatim Quote:**
```
_ **The ledger's write discipline is the instrument's own law: `docs/instruments/ledger.md` §9 — the single-writer lock and fsync, the settlement receipt the TOOL writes, the close refusal, the reconstructed claim's basis, the subject form and the one-board `#N` namespace, retirement as naming-not-deleting, the irreducible append→push residual after a fork and the re-mint protocol that answers it, and the ad-hoc probe seam.**
```
**Defect Analysis.** The line begins `_ ` where the surrounding block uses `- **…**`. It renders as literal prose starting with an underscore, not as a list item, so the clause loses its list membership and its visual parity with its siblings — a section-cohesion defect in the clause file that carries the State law. The defect is small but in a law file, where structure is the reader's only map.
**Actionable Remediation.** Change the leading `_ ` to `- `.

---

## Surfaces checked and found clean (with method)

- **`skills/meta-factory/verdicts-and-claims.md`** — read in full (246 lines). Cohesive: one concern (how a claim about the factory's state is made and checked); every clause carries a locator, a measured instance, and a stated upholding mechanism or an explicit "no gate upholds this and that is stated". No un-terminating procedure found.
- **`TEMPLATE/roles/carrier.md`** — read in full. One concern; explicit terminal state (step 6 "Record"); no dangling internal anchor, no un-gated directive.
- **`docs/instruments/review-rotation.md` §1-2, §9-10** — the lifecycle has an explicit terminal state and a checkable completion formula ("A COMPLETED close now requires both, and refuses with the count and the names", `:101-104`); §10's reload-path table matches the actual symlink target (verified: `readlink -f skills/meta-factory/review-rotation.md` → `…/TEMPLATE/docs/instruments/review-rotation.md`, as §10 declares).
- **Reload-path integrity of the 8 instrument symlinks** — verified `readlink -f` for all eight: 7 resolve into `TEMPLATE/docs/instruments/` (as `template-instruments.md` §6 mandates), and `insights.md` resolves to `docs/instruments/insights.md` (its root-only exception). All eight resolve; none is broken.
- **Doc-pair byte identity** — verified `cmp` for the 7 pairs: all IDENTICAL (held by `tests/test_docs_sync.py`, read and confirmed to cover `docs/instruments/*`).
- **`skills/meta-factory/SKILL.md` section numbering** — `grep -n '^## '` → contiguous `## 0.` … `## 14.`; the structural gate `tests/test_law_structure.py` is satisfied (it checks contiguity only — see F6/F8 for what it does *not* check).

---

## Summary

**12 findings** (F1–F12) plus one scope/coverage finding (the manifest mapping omits `TEMPLATE/roles/*.md` while asserting those paths are absent). The single most severe is **F1**: the shipped role card `TEMPLATE/roles/hq.md:20` orders "the **11-lens** review … / `docs/review-lenses.md`" while that cited catalogue defines **14** lenses (`grep -c '^### Lens ' docs/review-lenses.md` → 14; `tools/review.py:72` → 14 entries) — a name that contradicts its own citation, un-gated, shipped to every bootstrapped factory, and a re-appearance of the already-filed V1 defect (`evidence/reviews/2026-09-27-review-rotation-vocabulary.md:43`, "Two incompatible lens catalogues are live in the same corpus"). The severity theme is the lens's own third target: four findings (F2, F3, F5, F8) are recovery anchors or load paths that do not survive the reader they were written for — a Worker told to ack against its law, a `[LANE]` pointer to another repo, a watchdog bound with a free variable, and a compaction-recovery clause pointing at the wrong section.

**Measurements (exact commands/reads):** `ls -la skills/meta-factory/ docs/instruments/ TEMPLATE/docs/instruments/ TEMPLATE/roles/ tools/`; `wc -l` on all law docs; `readlink -f` on the 8 skill symlinks; `cmp -s` over the 7 `docs/` ↔ `TEMPLATE/docs/` instrument pairs; `grep -c '^### Lens ' docs/review-lenses.md` (→14); `sed -n '72p' tools/review.py` (`CATALOG_LENSES`, 14 entries); `grep -rn "11-lens"` (→ only `TEMPLATE/roles/hq.md:20` + two evidence records); `grep -rn "Rail" skills/meta-factory/` (→ 0 hits); `grep -rn "N\* cycles\|N cycles"` (→ only `triage.md:24`); `ls tools/questions*` and `ls skills/opencrabs-dev` (→ absent) vs `ls /root/.opencrabs/profiles/ops/skills/opencrabs-dev/…` (→ present); `grep -n '^## ' skills/meta-factory/SKILL.md` (→ contiguous 0-14); `read_file` of `tests/test_instrument_census.py` (ARM 6 = deferral, ARM 7 = zero-parsed-set refusal), `tests/test_law_structure.py`, `tests/test_law_coverage.py`, `tests/test_citation_clause_titles.py`, `tests/test_docs_sync.py`; `read_file` of `evidence/instrument-census-open-questions-2026-09-29.md` (→ `meta-factory … 2/4 … SOURCE`); `sed -n` reads of every quoted line.

**Not done (deliberately):** the brief's `python3 tools/review.py record <cycle_id> G <report>` step was **not** run — `tools/review.py record` writes into the repo's `reviews/` tree, and this audit is READ-ONLY on `/root/agent-factories` per the corpus rule ("Your only permitted write is your own report file"). This report at `/tmp/rr-c1/reports/lens-G.md` is the deliverable.

**Observation (not this audit's doing):** `git status --porcelain` at the end of the audit showed ` M evidence/insights.jsonl` — an uncommitted modification present in the working tree. This audit made no write to the repo, so the change is not mine; flagged only so the orchestrator knows the tree was not clean when the report was taken.
