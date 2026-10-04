# Lens C — CLI Automation Gaps & Usage Analysis

**Repo audited:** `/root/agent-factories` (READ-ONLY; no writes made)
**Revision pinned:** `6bd9690d578c5bbc911537b95abe0ab0bc884c8c` (`git rev-parse HEAD`, read at 2026-10-04 ~21:10Z)
**Bound — the shared tree advanced under the audit (not by me):** while this lens ran, the orchestrator committed peer reports, moving HEAD `6bd9690` → `9ffe211` → `33ca8d8` ("review(rr-c1): record batch 2 lens E…"). I wrote nothing under `/root/agent-factories`. All findings were read at `6bd9690`; `git diff --name-only 6bd9690 33ca8d8` shows **none of the files I cite changed**, so every locator and quote below still holds at the current tip.
**Lens definition read from the corpus itself:** `tools/review.py:133-138` — lens C, family "3. TOOLS & INTERFACES", scope *"Manual procedures and tool invocation telemetry"*, instructions: (1) detect recurring multi-step manual commands, (2) propose unified CLI signatures, (3) analyze tool error distributions and uninvoked legacy tools. `docs/review-lenses.md:77` names the telemetry surface: *"(`tools.log`, ledger records)"*.
**Method (every number below is from a command run this session):** `git rev-parse`, `grep -rc/-rl/-rn` over `skills/ docs/ tools/ tests/ registry/`, `sed -n` on every cited line, `wc -l`, `find`, `ls`, and a `python3` pass over the live `tools.log`. Locators were re-read with `sed` before shipping.

---

## Finding 1 — HIGH — The live law asserts a tool does not exist that is shipped in the tree; the ruling path bypasses it

**(a) LOCATOR:** `skills/meta-factory/state.md:58`

**(b) VERBATIM QUOTE:**
> `The canonical head is **DECLARED, never enforced** — the writer is an agent typing `gh issue comment` and there is no tool on that path, so a rule the writer cannot reach would be dead text (P29).`

**(c) DEFECT ANALYSIS:**
`tools/rule.py` **is** that tool, and it says so in its own docstring:
- `tools/rule.py:32` — `THE HEAD IS NOW ENFORCED, NOT MERELY DECLARED.`RULING_CANONICAL_HEADING` in`
- `tools/rule.py:35` — `typing `gh issue comment` and there was no tool on that path. This is the tool on that`

The shipped twin agrees the premise is dead: `TEMPLATE/tools/patrol_host_state.py:810` — `removes. That premise is measured FALSE as of #270: `tools/rule.py` sits on that path, so`. The tool is not a stub: `tools/rule.py` validates the canonical head, POSTs the board comment, and appends the paired `ruling` row with `comment=<id>`, rolling the comment back if the append fails (atomic two-leg design, `tools/rule.py:56-77`, `:200-260`).

Measured reference count of the law's own pointer to it:
- `grep -rc "rule\.py" skills/ docs/ ONTOLOGY.md README.md` → **0 files** (rule.py appears in no law surface; the only repo references are `evidence/rework.md:320`, `TEMPLATE/tests/test_ruling_row_recorded.py`, `TEMPLATE/tools/patrol_host_state.py`, and the kit manifest).

The cost is not theoretical. `evidence/rework.md:320` records the exact failure this stale sentence licenses: `n=2032` — a ruling row *"written by a path that bypassed `tools/rule.py`, which exists precisely to write the ruling row and its board-comment pairing in ONE invocation"* — left `main` RED on `tests/test_ruling_row_recorded.py` (`1 failed, 20 passed`). The law that a lane reads when it writes a ruling tells it no such tool exists; so it hand-types `gh issue comment` and reproduces the recorded defect. This is the lens's target #1 (a recurring manual multi-step command, `gh issue comment` + `tools/ledger.py append`, that a shipped tool already unifies) compounded by target #3 (a tool with zero law-invocations).

**(d) REMEDIATION:**
Rewrite `state.md:58` to name the write path: *"the canonical head is ENFORCED at the write path — a ruling is stamped with `python3 tools/rule.py --issue N --body-file …`, which posts the comment and stamps the paired `ruling` row or leaves neither surface touched; the patrol's printed spellings cover only comments written around that path."* Add a row for `tools/rule.py` to the §11 surface table in `SKILL.md` (beside `tools/ledger.py append`). Add a law-coverage gate that fails any law clause containing the phrase `no tool on that path` while the named tool exists.

---

## Finding 2 — HIGH — A documented reproduce command that no longer reproduces, and the file contradicts itself

**(a) LOCATOR:** `docs/instruments/kit.md:180-181` (repeated at `:523`; opening claim at `:113`)

**(b) VERBATIM QUOTE:**
> `- Predicate: `grep -c kit_surfaces TEMPLATE/tests/gate_registry.py` → **0** (rc=1).`
> `- Scope: both trees. No `tests/test_kit_surfaces.py` exists in either.`

**(c) DEFECT ANALYSIS:**
Both halves are falsified by the current tree, and the same file states the opposite 110 lines later.
- `grep -c kit_surfaces TEMPLATE/tests/gate_registry.py` → **2** (rc=0), not 0.
- `tests/test_kit_surfaces.py` **exists** — `-rw-r--r-- 1 root root 5598 Sep 28 14:24 tests/test_kit_surfaces.py`.
- The same file, `docs/instruments/kit.md:291`: `This is the remedy for §4.1. The gate is **`tests/test_kit_surfaces.py`**, meta-factory-only at the`.

So `kit.md` simultaneously declares (F1/§4.1/§7.1) that the gate does not exist and (§7.2) that the gate *is* `tests/test_kit_surfaces.py`. The reproduce command is a runnable CLI invocation printed for a reader to check — and it is a stale assertion, the exact "figure that drifts" class the instrument exists to eliminate. The same `:523` F1 row instructs a remedy *"built by the code owner"* that was already built.

**(d) REMEDIATION:**
Close F1: delete the F1 row from §9.2 and the §4.1 block (or retitle it `RESOLVED — gate landed at tests/test_kit_surfaces.py`), and correct `:113`. Replace the free-text reproduce line with the registered gate name so it cannot drift: `tests/test_kit_surfaces.py` (present in `registry/gates.json:26` and `tools/audit.py`).

---

## Finding 3 — MEDIUM-HIGH — The law declares a standing duty but never names its runner; the runner is invisible to every law surface

**(a) LOCATOR:** `docs/measurement-procedure.md:547` (within §5.2, heading at `:506`)

**(b) VERBATIM QUOTE:**
> ``tools/gate_budget.py` **REFUSES** a stated derivation its own numbers contradict. The **DEFAULT's``

**(c) DEFECT ANALYSIS:**
§5.2 (`### 5.2 The Gate-Budget Re-Derivation Leg — the standing duty that clears the staleness class`) orders a periodic re-derivation leg, but the only tool it names is `tools/gate_budget.py` — the **value reader**, which the clause uses as a refusal oracle. The leg's actual executable, `tools/gate_budget_rederive.py`, is named in **zero** law surfaces:
- `grep -rn "gate_budget_rederive" docs/ skills/` → **0 hits**.
- `grep -rl "gate_budget_rederive.py" skills/ docs/ ONTOLOGY.md README.md` → **0 files**.

The only place that names the runner is the cron prompt embedded in `registry/state.json:3455` (`run python3 tools/gate_budget_rederive.py against the round's own audit payload`). A lane woken by §5.2 — whose whole duty is *"run the leg"* — is told the mechanism but not the command; the runner is reachable only by reading a cron row, not the law the cron row points at. This is the lens's target #3 (an uninvoked-by-law tool) and target #2 (no unified signature stated).

**(d) REMEDIATION:**
Add the command to §5.2, e.g. *"Run: `python3 tools/gate_budget_rederive.py --audit-report <round audit.json> [--apply]`; a leg with no payload is REPORT-ONLY."* Add `tools/gate_budget_rederive.py` to the instrument/surface table that §5.2's writer (`Surveys`) reads, so the duty and its runner are stated in one place.

---

## Finding 4 — MEDIUM — No tool-invocation telemetry exists for this factory's own CLI surface; the lens's error-distribution analysis is unimplementable

**(a) LOCATOR:** `docs/review-lenses.md:77` (scope) against `TEMPLATE/tools/questions:586`

**(b) VERBATIM QUOTE:**
> `- **Scope:** Manual procedures and actual tool invocation telemetry (`tools.log`, ledger records).`
> `# Unified tools log (parity with tools/lib/oc-log.sh, schema per RC-CONTRACT)`

**(c) DEFECT ANALYSIS:**
Lens C is scoped to `tools.log`, so I measured it. The log exists and is rich — `/root/.opencrabs/profiles/ops/opencrabs-dev/tools.log` holds **75,011** entries across **53** distinct tools (e.g. `oc-ledger` 33,870 with 4,365 non-zero exits; `oc-prchecks` 4,734 / 3,718). But **none** of this factory's own `tools/*.py` write to it:
- `grep -rl "OC_TOOLS_LOG\|oc_log_finish\|oc_log_init\|tools.log" tools/*.py` → **0 files**.
- The python pass over `tools.log` finds **none** of `ledger, audit, hygiene, review, rule, patrol_host_state, kit_manifest, brain_metrics, registry, roadmap, insights, telemetry, subject_anchor, compaction_rate, gate_budget` (only the shipped `questions` instrument appears, 407 entries).

So the error distribution the lens asks to analyze cannot be computed for the meta-factory's own tool surface: the factory runs `tools/ledger.py`, `tools/audit.py`, `tools/hygiene.py` etc. thousands of times and no surface records their exit codes. The one tool that does emit (`questions`) references two files that do not exist in this repo: `tools/lib/oc-log.sh` (`TEMPLATE/tools/questions:586`) and `tools/docs/RC-CONTRACT.md` (`TEMPLATE/tools/questions:17`) — `find . -iname "*oc-log*" -o -iname "*RC-CONTRACT*"` → **nothing** (they resolve only in the ops profile at `skills/opencrabs-dev/tools/`). This is the P29 "a field written but never read" shape inverted: a telemetry surface that exists but has no writers on this factory's own path.

**(d) REMEDIATION:**
Either (i) add a shared `oc_log_finish` shim to `tools/*.py` so each tool records `{tool, args, exit, secs}` to `tools.log`, giving lens C a real population; or (ii) state in `docs/review-lenses.md` (lens C scope) that this factory's own tool surface is deliberately un-telemetred, and name the population the lens *can* read. Do not leave the scope line pointing at a log that carries none of this factory's tools.

---

## Finding 5 — MEDIUM — The settlement/release leg is a 3–4 step manual sequence with no unified runner, while the analogous ruling act has one

**(a) LOCATOR:** `skills/meta-factory/SKILL.md:424`

**(b) VERBATIM QUOTE:**
> `   - Stamp `evidence/ledger.jsonl`, run `tools/ledger.py verify`, and commit/push to `origin/main`.`

**(c) DEFECT ANALYSIS:**
This is a recurring, multi-leg manual command sequence. `docs/processes.md:148` states the same leg with four legs:
> `| **6. Settlement & Release** | HQ / Carrier | All gates green | Fast-forward commit on main + `close` row (Rail 2) + Rail 1 ack + the board issue closed with its receipt | Stale sha / broken remote push / false open (`close` row written, board issue still open) | …`

The failure column itself names the divergence (*"`close` row written, board issue still open"*) — a board/ledger pairing that no tool binds. `ls tools/ | grep -iE "close|settle|file|intake|dispatch|board"` → **empty**; `grep -rn "gh issue close\|gh issue create" tools/` → **empty**. Yet the exact analogue — board comment ↔ ledger row — **is** automated by `tools/rule.py` (Finding 1). The asymmetry is the gap: rulings get an atomic two-surface tool; closes (and filings: board issue + intake row + claim + dispatch, `SKILL.md:184-190`) do not, so the settlement leg stays hand-typed and the patrol can only *report* the divergence after the fact.

**(d) REMEDIATION:**
Propose `tools/settle.py --issue <N> --subject <#N> [--sha <sha>] [--dry-run]`, mirroring `rule.py`'s single-entry/single-exit contract: append the `close` row (which already runs the sequence predicate at the write path, `ledger.py:2089`), then close the board issue, rolling back neither-or-both on failure. The `verify` leg stays a separate read. Name it in `SKILL.md` §12 step 2 so P30's sequence becomes one invocation.

---

## Finding 6 — LOW-MEDIUM — A documented cron trigger names a flag the tool does not define

**(a) LOCATOR:** `docs/proposals/01-cron-gated-goal-pipeline.md:113`

**(b) VERBATIM QUOTE:**
> `| **Meta-Factory** | `python3 tools/hygiene.py --check` | `exit_non_zero` | Dispatches workspace cleanup goal if stale scratch files exceed threshold. |`

**(c) DEFECT ANALYSIS:**
`tools/hygiene.py`'s argparse defines `--audit`, `--clean`, `--scratch-glob`, `--namespace`, `--grace-minutes`, `--require-committed` (`tools/hygiene.py:1466-1500`) — **no `--check`** (`grep -n '"--check"' tools/hygiene.py` → rc=1). The proposal offers this as the `trigger_cmd` for a cron row with `trigger_on = exit_non_zero`. argparse exits **2** on an unknown flag, and 2 is non-zero, so a cron copied from this table would fire the full agent turn on **every** scheduled run — the precise inversion of the P28 "0-token quiescence" the trigger exists to provide. The live cron uses the correct verb (`registry/state.json` contains only `hygiene.py --clean`), so the defect is confined to the proposal — but the proposal is a copy-ready table.

**(d) REMEDIATION:**
Change the trigger to `python3 tools/hygiene.py --audit` (the documented audit verb, `docs/measurement-procedure.md:407`). More generally, add the proposal's command column to the same "reproduce command" gate that should cover Finding 2.

---

## Finding 7 — LOW — Two tools in `tools/` are invoked by nothing: no law, no gate, no cron, no kit

**(a) LOCATOR:** `tools/render-trap-runbook.py:2`; `tools/sigpipe_threshold.sh:2`

**(b) VERBATIM QUOTE:**
> `"""Render the Trap Runbook as a standalone document for a human reader.`
> `# Reproduction of the SIGPIPE assertion class (#537, fixed by #660) -- and the threshold that`

**(c) DEFECT ANALYSIS:**
Reference counts (lens target #3, "uninvoked legacy tools"), measured with `grep -rl` over `skills/ docs/ ONTOLOGY.md README.md`:
- `render-trap-runbook.py` → **0** law references; `tests/` has no matching gate; `grep -c render-trap-runbook registry/kit.json registry/gates.json tools/audit.py` → `0 0 0`. The only repo mention is a one-off deliverable, `evidence/deliverables/2026-09-18-trap-runbook.md:5`.
- `sigpipe_threshold.sh` → **0** law references; `0 0 0` across kit.json / gates.json / audit.py; the only mention is `evidence/deliverables/2026-09-27-review-rotation-donor-migration.md:163`.

Neither ships in the kit (`ls TEMPLATE/tools/` contains neither). They are build/repro scratch that never entered a cadence or a gate — no run row, no registration, no reader. That is the "uninvoked legacy tool" class the lens names, and neither is declared as a deliberate exception anywhere I could find.

**(d) REMEDIATION:**
Either wire `render-trap-runbook.py` into the cadence that regenerates its deliverable (and register the deliverable in the kit/render set), or move both to `evidence/` as one-shot artifacts and drop them from `tools/` — the deletion-safety call belongs to lens D; what lens C owes is the declaration that they have no invocation.

---

## Finding 8 — LOW — An instrument's declared file set names a repo-side half that is absent from this repo

**(a) LOCATOR:** `docs/instruments/open-questions.md:34`

**(b) VERBATIM QUOTE:**
> `| 1 | `tools/questions` ↔ `TEMPLATE/tools/questions` | `standalone` | **the executable** — every verb: `ask` · `answer` · `amend` · `notify` · `list` · `publish` · `lint` · `gc` · `selftest` |`

**(c) DEFECT ANALYSIS:**
`find . -name questions` → `./TEMPLATE/tools/questions` only (plus the `.git/refs` branch name). The left half of the declared pair, `tools/questions`, does **not** exist in this repo. The doc's own §5.1 says the path is resolved by a glob and *"no clause in this file may pin it"* (`open-questions.md:221`), and §5.4 says *"'Absent from its own tree' is NOT 'unusable'"* — so the absence may be a deliberate "reach a shared copy" adoption. But the §2 table presents both halves as *the pair*, with no marker that the repo half is absent here, so a reader grepping for `tools/questions` meets a missing file and cannot tell a decision from a defect. (The re-homed body at `open-questions.md:118` further names yet a third location, `skills/opencrabs-dev/tools/state/oc-questions`.)

**(d) REMEDIATION:**
Annotate the §2 row to state the adoption shape (e.g. *"this factory resolves the CLI under the skill's tools root; no `tools/questions` copy is vendored here — declared, not missing"*), or drop the pinned `tools/questions` path from the table per §5.1's own no-pin rule.

---

## Scope / coverage note

The brief's generic premises (`roles/*.md`, `processes.md`, `AGENTS.md`) do not exist in this repo — the CORPUS manifest already maps lens C onto `skills/meta-factory/SKILL.md` + `docs/*.md` against `tools/*.py`, and I followed that mapping. No mapped path was absent. One methodological caveat, stated rather than hidden: Finding 4's telemetry numbers come from the ops-profile log at `/root/.opencrabs/profiles/ops/opencrabs-dev/tools.log`, which is outside `/root/agent-factories`; I read it read-only, and the *finding* (this factory's own tools emit nothing) is established by the in-repo grep returning 0 files.

## Summary

**Eight findings** (2 HIGH, 1 MEDIUM-HIGH, 3 MEDIUM/LOW-MEDIUM, 2 LOW). The single most severe is **Finding 1**: the live process law at `skills/meta-factory/state.md:58` asserts *"there is no tool on that path"* for the ruling write path while `tools/rule.py` — shipped, gate-tested, and documented in its own docstring as *"the tool on that path"* — sits unused by any law clause (`grep -rc "rule\.py" skills/ docs/ ONTOLOGY.md README.md` → 0), a staleness whose downstream cost is already recorded at `evidence/rework.md:320` (row `n=2032` bypassed the tool; `main` RED on `tests/test_ruling_row_recorded.py`).

Measurements were produced by: `git rev-parse HEAD`; `grep -rc/-rl/-rn` over `skills/ docs/ tools/ tests/ registry/ ONTOLOGY.md README.md`; `sed -n` on every cited line (`state.md:58`, `SKILL.md:424`, `kit.md:180-181,291,523`, `measurement-procedure.md:547`, `review-lenses.md:77`, `proposals/01-cron-gated-goal-pipeline.md:113`, `open-questions.md:34`, `processes.md:148`, `TEMPLATE/tools/questions:17,586`, `rule.py:32,35`, `TEMPLATE/tools/patrol_host_state.py:800,810`); `grep -n '"--check"' tools/hygiene.py` (rc=1); `find . -name questions`; `ls TEMPLATE/tools/`; and a `python3` pass over the 75,011-row `tools.log` counting per-tool entries and non-zero exits.
