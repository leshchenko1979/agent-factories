# Lens I — Meta-Review & Catalog Brief Integrity

**Revision audited:** `af6d92776c1dce0159256ad100c6c0abf889e480` (`git -C /root/agent-factories rev-parse HEAD`).
All four of this lens's target files are byte-identical to that commit (`git diff --quiet HEAD -- <path>` returns clean for `tools/review.py`, `tests/test_review.py`, `docs/review-lenses.md`, `docs/instruments/review-rotation.md`), so every quote below is a HEAD byte.

> **Revision note (drift during the audit).** HEAD advanced to `8ed685cb2208dc9ab459ac0686b916433db32047` mid-audit — a concurrent review lane committed `review(rr-c1): record lenses T, S (13/14)`. That commit touches only `reviews/20260927-c1/{state.json,reports/lens-S.md,reports/lens-T.md}`; `git diff --quiet af6d927… HEAD -- <each of the four target files>` is clean, so **every quote below holds identically at both revisions**. No file under `/root/agent-factories` was written by this audit.

## Method

Read-only audit. Commands actually run this session (no estimates):

- `git -C /root/agent-factories rev-parse HEAD` and `git diff --quiet HEAD -- <file>` for the four targets.
- `sed -n` / `nl -ba` reads of `tools/review.py` (2144 lines), `docs/review-lenses.md` (181 lines), `docs/instruments/review-rotation.md` (535 lines), `tests/test_review.py` (1425 lines).
- **Executed behaviour** of the engine on a throwaway copy outside the factory (`cp tools/review.py /tmp/revtest/tools/`, then `init/record/close/verify/waive`), never writing into `/root/agent-factories`.
- `python3 -m pytest tests/test_review.py --collect-only -q` on a `/tmp` copy → **31 tests collected**.
- `python3 tools/review.py brief <LENS>` for all 14 lenses → captured each brief's `## SCOPE` line.
- AST count of `REQUIRED_GATES` from `git show HEAD:tests/gate_registry.py` → **64**; `registry/gates.json` → `gates: 54`, `modes: 85`.
- `diff` of root vs `TEMPLATE/` halves of the two law docs → **byte-identical**.

The audit found **9 findings**. The flagship is F1: the adversarial briefs the engine emits are generated from a second, drifted copy of the lens definitions, not from the catalogue the factory declares canonical — and the meta-review lens (I) is itself briefed with a scope that contradicts its own catalogue entry.

---

## F1 — HIGH — The lens briefs are generated from a SECOND, drifted copy of the lens definitions; `docs/review-lenses.md` (the declared "canonical catalogue") and `LENS_METADATA` in `tools/review.py` disagree on names, families, scopes and checks, and nothing pins them together

**File locators & verbatim quotes (each is a HEAD byte):**

| # | `docs/review-lenses.md` (declared canonical) | `tools/review.py` (what `brief` actually emits) |
|---|---|---|
| F4 family | `:111` `## 📦 Family 4: ARTIFACTS, STATE & FLOW (Files, Ledgers, WIP)` | `:181` `"family": "4. STATE, DELIVERY & FLOW",` |
| F6 family | `:145` `## 🔍 Family 6: META & GOVERNANCE (Review Mechanics, Scope Cleanliness)` | `:201` `"family": "6. META-GOVERNANCE",` |
| Lens H name | `:113` `### Lens H — Ledger Health & Lifecycle Invariants` | `:170` `"name": "Ledger Invariants & Monotonicity",` |
| Lens M name | `:122` `### Lens M — Value Stream, WIP Stagnation & Lead Time` | `:180` `"name": "Value Stream, Flow & WIP Stagnation",` |
| Lens I name | `:147` `### Lens I — Meta-Review of the Lens Catalog` | `:200` `"name": "Meta-Review & Catalog Brief Integrity",` |
| Lens S name | `:155` `### Lens S — Brain Scrub & Profile Scope Cleanliness` | `:210` `"name": "Brain Scrub & Cross-Profile Cleanliness",` |
| Lens A scope | `:20` `- **Scope:** All role cards (\`roles/*.md\`), process registers (\`processes.md\`), process law (\`SKILL.md\`), and instrument law docs (\`docs/instruments/*.md\`).` | `:78` `"scope": "All role cards (roles/*.md), process registers (processes.md), and process law (SKILL.md).",` (drops `and instrument law docs (docs/instruments/*.md)`) |
| Lens H scope | `:114` `- **Scope:** \`evidence/ledger.jsonl\` (or factory work state store).` | `:172` `"scope": "State journals, ledger.jsonl, and subprocess event streams.",` |
| Lens I scope | `:148` `- **Scope:** This catalog (\`review-lenses.md\`) and historical review cycle outputs.` | `:202` `"scope": "The 14 review lenses and review machinery.",` |
| Lens S scope | `:156` `- **Scope:** External agent profile brain files (\`AGENTS.md\`, \`SOUL.md\`, \`TOOLS.md\`) vs. factory repos.` | `:212` `"scope": "Shared AGENTS.md vs factory-specific skills.",` |
| Lens B checks | `:37` `  6. **Progressive Disclosure:** Lengthy references belong behind linked pointers or separate docs, not in the primary execution loop.` | B instructions `:91–97` carry only 5 items — **Progressive Disclosure is absent** |
| Lens H checks | `:118` `  3. **Contradiction Pairs:** …` / `:119` `  4. **Lesson Extraction Parity:** …` | H instructions `:173–177` drop both, and **add** `"3. Audit actor attribution and verify single-writer locking compliance."` — a check the catalogue never states |
| Lens T checks | `:140` `  4. **Context Inflation Guard:** Audit turn context growth; …` | T instructions `:193–197` drop Context Inflation Guard |

The generator reads the drifted copy, not the catalogue:

```
tools/review.py:1084	    meta = lens_metadata(lens)
tools/review.py:1097	{meta['scope']}
tools/review.py:1100	{meta['instructions']}
```

`lens_metadata` (`tools/review.py:312–328`) resolves core lenses from the in-file constant `LENS_METADATA` (`:74–219`), never from `docs/review-lenses.md`.

**Defect analysis.** The catalogue's own first paragraph is the law this violates — `docs/review-lenses.md:3` `> **Owns:** Canonical catalog of the 14 review lenses …` and `:8` `**This catalogue is the instrument's CORE, and it is centralised: a member does not fork it.**`. But the file that is *actually read to brief every reviewer* is `LENS_METADATA`, a second home for the same definitions. This is the factory's own named defect class — `tools/review.py:1210` states it as law: *"two homes for one thing is the defect promotion exists to collapse"* — reproduced inside the instrument that claims to enforce it. `docs/instruments/review-rotation.md:312–315` compounds the false claim: `3. **ONE reader serves every path.** \`known_lenses()\` and \`lens_metadata()\` are read by \`init\`, … so a declared lens is materialised, counted and verified exactly as a core lens is`. There *is* one reader, but there are **two copies of the content**, and the copy the reader serves (`LENS_METADATA`) is not the canonical file. Consequence: **Lens I's own Core Check 1 is defeated by the machinery Lens I audits** — `docs/review-lenses.md:150` `1. **Scope Drift:** Verify lens briefs match what reviewers actually evaluate.` A reviewer briefed with `brief I` is told `The 14 review lenses and review machinery` while the catalogue says the scope is `This catalog (review-lenses.md) and historical review cycle outputs` — the brief does not match the law. No gate pins the two: `tests/test_review.py` contains zero references to `docs/review-lenses.md` (grep for `review-lenses.md` in the test file returns only the JSON extension surface), so the drift is silent.

**Remediation.** Make the catalogue the single authoring home for lens definitions and have `LENS_METADATA` be *generated from it* (or have `cmd_brief` parse the catalogue). Concretely: (a) add a test `test_brief_matches_the_catalogue` that, for every core lens, extracts the catalogue's `### Lens X — <name>` heading and its `**Scope:**`/`**Core Checks:**` block and asserts equality with `brief <X> --json`; (b) until then, correct `LENS_METADATA` to the catalogue's names/families/scopes/checks for A, B, H, I, M, S, T. Either fix turns F1 from a silent two-home into a gate.

---

## F2 — HIGH — The "Quote-or-No-Finding" evidence rule is unenforced: `record` accepts any non-empty bytes and stamps COMPLETED, and `verify` never inspects report content — the census is bypassable with content-free reports

**File locator & verbatim quote** — `tools/review.py:1147–1157`:

```
    body = body.strip()
    if not body:
        print("Error: Report content is empty.", file=sys.stderr)
        return 2
    …
    report_file.write_text(body + "\n", encoding="utf-8")
```

**Measured bypass** (throwaway copy, `/tmp/revtest`):

```
$ for L in A B G J P C E F D H M T I S; do printf 'x' > r.txt; \
    python3 tools/review.py record 20260101-c1 $L r.txt >/dev/null; done
$ python3 tools/review.py verify 20260101-c1
PASS: Cycle '20260101-c1' census verified clean across all 14 lenses (codification plan: 0 accepted finding(s), all accounted for).
verify rc=0
```

Fourteen **1-byte** reports (`x`) produce a green census. `cmd_verify` (`tools/review.py:1443–1506`) checks only: status, `report_path` existence, and `sha256` equality — never the body.

**Defect analysis.** The catalogue states this as a Core Check of Lens I itself — `docs/review-lenses.md:152` `3. **Evidence Discipline:** Enforce the "Quote-or-No-Finding" rule. Reject vague impressions lacking specific locators and quotes.` The brief the engine emits even prints the required format (`tools/review.py:1102–1107`, `1. File Locator … 2. Verbatim Quote …`). Yet no code path reads the body: the "Enforce" and "Reject" verbs have **no mechanism**, which is exactly the class the instrument's own law names at `docs/instruments/review-rotation.md:55` — *"**A claim in a docstring is not a mechanism.**"* A lens report containing no locator and no quote is recorded `COMPLETED` and the census reads clean. The un-bypassability the brief charges Lens I to guarantee (`## INSPECTION TARGETS … 3. Ensure the review census mechanism (tools/review.py) remains un-bypassable`) is therefore not met: "the review happened" is decoupled from "the review produced evidence".

**Remediation.** Enforce a minimal structural predicate at write time in `cmd_record`: reject a body with no `path:line` locator token (regex `[\w./-]+:\d+`) or no quoted span; and record the predicate result in the state entry (e.g. `"evidence_format": "ok"|"missing-locator"`). Make `census_gaps` treat `COMPLETED` with `evidence_format != "ok"` as a gap, so `close --status COMPLETED` is refused. Add a test asserting a quote-less report is refused (or at least flagged), mirroring `test_a_missing_closure_cannot_pass_verify`.

---

## F3 — HIGH — The freeze is bypassable: `record` and `waive` carry no `is_frozen` check (unlike `codify`, `intake`, `cadence`), so a closed cycle's `state.json` can be mutated after `close`

**File locators & verbatim quotes.**

`cmd_record` (`tools/review.py:1127–1191`) and `cmd_waive` (`tools/review.py:1194–1227`) contain **no** `is_frozen`/`refuse_live_read` call. The guard exists elsewhere — `grep -n "refuse_live_read\|is_frozen" tools/review.py` returns only: `920` (def), `971`, `1012`, `1264` (`cmd_codify`), `1597` (`cmd_cadence`), `1919` (`cmd_intake`). The law it contradicts, `tools/review.py:27–32`:

```
  7. NO SILENT LIVE READ: a cycle is FROZEN once its lifecycle is terminal.
     Closing snapshots the declared channels (`inputs_snapshot`), and a later
     `intake` or `cadence --write` against a frozen cycle is REFUSED, because
     the bytes on disk now answer a different question than the one the cycle
     closed on.
```

**Measured bypass** (throwaway copy, `/tmp/revtest2`): after `close --status COMPLETED`,

```
state.json sha BEFORE post-close record: f91edfa862cadfe980c3b762a93dfa84fe7bfdf91374f08e25654808cbe1b60d
state.json sha AFTER  post-close record: 8f78a02b0485ebdfdfde74d196b769330e5ef9bf737dc5e91509ca85a52f5b0b
>>> FROZEN state.json WAS MUTATED post-close
Persisted report for Lens A: 8880f92927b7a5d7... (19 bytes)      # record rc=0
Waived Lens B: post-close waiver                                  # waive  rc=0
```

**Defect analysis.** `docs/instruments/review-rotation.md:59–62` makes the freeze the third design commitment — *"**A closed cycle's inputs are historical.** … A terminal lifecycle FREEZES the cycle and snapshots its declared channels"* — and §9 (`:500–508`) rests the instrument's published census artifact on the frozen bytes being the bytes. `record` overwrites `reviews/<cycle_id>/reports/lens-<X>.md` and rewrites the lens entry in `state.json`; `waive` flips a lens status. Both run against a terminal cycle with rc=0, so the "frozen" historical record is silently rewritable. The docstring enumerates the guard as covering `intake` and `cadence --write` and simply never mentions `record`/`waive` — an omission that leaves the two write paths that *carry lens evidence* unguarded.

**Remediation.** Add the same guard used by `cmd_codify` (`tools/review.py:1264–1270`) to the top of `cmd_record` and `cmd_waive`: refuse (rc=2) when `is_frozen(state)`. Add a test `test_a_frozen_cycle_refuses_a_new_report_or_waiver` asserting rc=2 and that the `state.json` sha is unchanged, paralleling `test_codify_records_a_finding_and_refuses_a_carrier_less_one`'s frozen arm.

---

## F4 — MEDIUM-HIGH — The "UNRECEIPTED (no index line)" state is unreachable: `verify` reads a self-stamped boolean in `state.json`, never the `review-index.log` it calls the receipt; the index log is write-only decoration

**File locators & verbatim quotes.**

Written (never read back) — `tools/review.py:1168–1172`:

```
    index_file = reports_dir / "review-index.log"
    with open(index_file, "a", encoding="utf-8") as f:
        f.write(
            f"{now}|{lens}|{report_file.relative_to(REPO_ROOT)}|{digest}|{len(body)}\n"
        )
```

The self-stamp — `tools/review.py:1183` `        "receipt": "verified",`. The "verification" — `tools/review.py:1482–1485`:

```
        # A report whose index line is absent is UNRECEIPTED: a distinct state
        # from missing, and never a silent pass.
        if info.get("receipt") != "verified":
            unverified.append(lens)
```

`grep -n "review-index\|index_file" tools/review.py` shows `index_file` is written at `:1168–1169` and **read nowhere**. The claim it is meant to back, `tools/review.py:15–16`: `3. Receipt verification: reports verified with sha256 checksums, and a report with no index line is UNRECEIPTED — a named state, never a silent pass.`

**Measured bypass** (throwaway copy, `/tmp/revtest2`): after recording 14 lenses and deleting the index log,

```
$ rm -f reviews/20260101-c2/reports/review-index.log
$ python3 tools/review.py verify 20260101-c2
PASS: Cycle '20260101-c2' census verified clean across all 14 lenses (codification plan: 0 accepted finding(s), all accounted for).
verify rc=0 (with index log DELETED)
```

**Defect analysis.** The docstring promises a mechanism ("a report with no index line is UNRECEIPTED"); the code checks a field `cmd_record` itself stamps `"verified"` on the same write, so the UNRECEIPTED state is reachable **only by hand-editing `state.json`** — which is precisely how the only test of it works. `tests/test_review.py:388–415` `test_verify_reports_unreceipted_lenses` carries the docstring `"""A COMPLETED lens with no index line is UNRECEIPTED, not clean."""` but its body nulls `state["lenses"]["A"]["receipt"]` (`:400`) and never touches an index line — the test reproduces the fiction rather than testing the claim. Same class as F2: a claim in a docstring that is not a mechanism (`docs/instruments/review-rotation.md:55`). The real receipt log can be deleted, corrupted, or never written and the census is unchanged.

**Remediation.** Either (a) make `verify` actually parse `reviews/<cycle_id>/reports/review-index.log` and require a line whose `sha256`/`path` match the state entry (then a deleted index line genuinely reds), or (b) delete the index log and the `receipt` field entirely and drop the docstring claim, since the sha256-in-state already provides the receipt. Option (a) is preferred because the docstring and `review-rotation.md §1`'s lifecycle diagram (`:44` `receipt`) both advertise an index-line receipt. Fix the test either way so its docstring matches its body.

---

## F5 — MEDIUM — Every emitted brief scopes the reviewer onto paths that do not exist in this repo, while dropping the one path that does

**File locator & verbatim quote** — `python3 tools/review.py brief A` (scope line, from `tools/review.py:78`):

```
## SCOPE
All role cards (roles/*.md), process registers (processes.md), and process law (SKILL.md).
```

**Measured** (`ls`/`find` in the repo root):

```
roles/ dir:        ls: cannot access 'roles': No such file or directory
processes.md:      ls: cannot access 'processes.md': No such file or directory
SKILL.md (root):   ls: cannot access 'SKILL.md': No such file or directory
```
(`docs/processes.md` and `skills/meta-factory/SKILL.md` exist, but the brief names neither path.)

**Defect analysis.** The shipped brief for Lens A points the isolated auditor at three paths that are absent from the very tree that ships the brief, so the brief is un-runnable as written. This is why the corpus manifest (`/tmp/rr-c1/CORPUS.md`) had to be hand-authored to remap the briefs' generic paths — i.e. the defect is real enough that the review harness built a shim for it. Worse, the catalogue's Lens A scope (`docs/review-lenses.md:20`) *does* name a real path — `and instrument law docs (docs/instruments/*.md)` — and F1 shows the brief drops exactly that clause. So the brief points at nothing real and omits the one real target. Violates `docs/review-lenses.md:150` (`Verify lens briefs match what reviewers actually evaluate`) and the generic-template premise: the catalogue is shipped "centralised … a member does not fork it" (`:8`), but it was never localised to the meta-factory's own layout.

**Remediation.** Localise `LENS_METADATA` scopes to the paths that exist here (`skills/meta-factory/SKILL.md`, `docs/*.md`, `docs/methodology/*`, `docs/instruments/*.md`, `ONTOLOGY.md`), or make the scope strings reference the catalogue which carries the mapped surface. At minimum, restore the `docs/instruments/*.md` clause the brief dropped (F1).

---

## F6 — MEDIUM — `docs/instruments/review-rotation.md` ships stale and self-contradictory numeric readings, including three different counts of its own declared gate file

**File locators & verbatim quotes** (all HEAD bytes):

- `:124` `… | **the gate** — one test per pinned behaviour; **29 collected** (\`pytest --collect-only -q\`) at **2026-10-03T22:35:40Z**, in the tree this doc ships in |`
- `:188` `| \`tests/test_review.py\` | the instrument's own behaviour — the 27 named tests of §7 |`
- `:340` `instrument's probes are named, not implied — all **27** are in \`tests/test_review.py\`, and each is`
- `:176` `- \`tests/gate_registry.py\`'s \`REQUIRED_GATES\` carries **56** entries and **\`test_review.py\` is not`
- `:196` `entries and **none** names \`tests/test_review.py\`, and the \`REQUIRED_GATES\` tuple above (54) does`

**Measured:**

```
python3 -m pytest tests/test_review.py --collect-only -q   → 31 tests collected
AST REQUIRED_GATES (from HEAD:tests/gate_registry.py)       → 64
registry/gates.json                                          → gates: 54, modes: 85
```

**Defect analysis.** The file carries **three** different counts of its own gate file — 29 (`:124`), 27 (`:188`), 27 (`:340`) — against a measured **31**; §7 claims "all 27 … each is named" yet enumerates 27 and silently omits four that exist (`test_a_declared_lens_extends_the_catalogue_without_forking_it`, `test_the_shipped_seed_declares_nothing`, `test_the_janitor_repairs_a_killed_runs_leak`, `test_the_next_run_repairs_a_killed_runs_leak`). And `:176` and `:196` state **56** and **54** for the *same* `REQUIRED_GATES` tuple in the same section (measured 64), a flat internal contradiction, not a dated-instant difference — no distinct instants are given for the two figures. `:195/:209` say `gates.json` carries **48** (measured 54) and `:210` says modes **74** (measured 85). This is the defect the catalogue's Lens A check 5 names — `docs/review-lenses.md` `5. **Enumeration Consistency:** Counts of steps, tools, gates, or phases stated in prose must match their actual definitions` — reproduced in the instrument's own law doc. A member reproducing the doc's declared gate count gets a number that is wrong three different ways.

**Remediation.** Re-measure and update all four counts; better, stop restating derived counts in prose — have `test_review.py`'s collection count and `REQUIRED_GATES` length asserted by a gate and cite the gate, so the number cannot drift from the tree. Resolve the 56/54 contradiction to the measured value.

---

## F7 — MEDIUM — Overlapping lens coverage: C and D claim the same "uninvoked/legacy tool" finding wholesale, and C's error-code clause overlaps F — the very duplication Lens I check 2 exists to catch

**File locators & verbatim quotes** — `docs/review-lenses.md`:

- `:80` `  2. **Usage Telemetry:** Analyze command frequency, error code distributions (tools clustering on error exits indicate broken interfaces), and uninvoked legacy tools (YAGNI deletion candidates).` (Lens C)
- `:98` `### Lens D — Deletion Safety & YAGNI Pruning`
- `:101` `  1. **Orphan Detection:** Enumerate stale, retired, or unreferenced files, mock fixtures, and temporary artifacts.` (Lens D)
- `:93` `  1. **Exit Code Determinism:** Success must exit \`0\`. Failures must exit distinct non-zero codes. No soft errors masked by exit \`0\`.` (Lens F)

**Defect analysis.** Lens C's check 2 names "uninvoked legacy tools (YAGNI deletion candidates)" — a finding Lens D is *entirely* about (`:98`–`:107`), so the same deletion candidate can be filed under C or D with no discriminator. C's "error code distributions (tools clustering on error exits …)" is a usage-telemetry reading of the same exit-code surface Lens F owns as a contract (`:93`). The catalogue defines the anti-duplication duty as a Core Check of Lens I — `:151` `2. **Overlap Detection:** Identify findings redundantly claimed by multiple lenses.` — so the catalogue ships the overlap its own meta-lens is instructed to flag. Without a boundary rule, HQ's triple-check (`docs/review-lenses.md:170`, "HQ Triple-Checks Findings") cannot dedupe mechanically.

**Remediation.** Add an explicit ownership boundary: give D exclusive title to deletion/YAGNI findings and delete the clause from C's check 2 (leaving C purely "automation gaps + command frequency"); split the exit-code surface by giving C "error *frequency*" (telemetry) and F "exit *contract*" (determinism), stating the split in both entries.

---

## F8 — MEDIUM — The Adversarial Isolation Requirement is unenforceable: nothing records who produced a report or that it came from an isolated sub-agent, so a self-authored report and an isolated one are indistinguishable and the census is green either way

**File locators & verbatim quotes.**

The requirement — `docs/review-lenses.md:13`:

```
**The Adversarial Isolation Requirement:** Review lenses must be executed by **dedicated adversarial sub-agents** spawned with clean, unpolluted context windows and explicit adversarial briefs (`tools/review.py brief <LENS>`).
```

`docs/instruments/review-rotation.md:73–78`:

```
   consequence for THIS instrument is a boundary a lane can check: **the lane that authored the
   work under review may not be the lane that supplies that cycle's lens reports.** … `brief <LENS>`
   is what makes the isolation executable rather than advisory
```

What `cmd_record` actually stores — `tools/review.py:1178–1185`:

```
    entry = dict(state["lenses"].get(lens) or {})
    entry.update({
        "status": "COMPLETED",
        "report_path": str(report_file.relative_to(REPO_ROOT)),
        "sha256": digest,
        "receipt": "verified",
        "recorded_at": now,
    })
```

No field records the recording actor, the sub-agent identity, or a brief hash.

**Defect analysis.** The law calls the boundary "a lane can check" and says `brief <LENS>` makes isolation "executable rather than advisory" — but `brief` only *prints a prompt*; it neither records that the prompt was dispatched to an isolated sub-agent nor ties the resulting report to that dispatch. `cmd_record` will happily persist a report supplied as literal text (`tools/review.py:1145` `else: body = content_or_path`) by the authoring lane itself, and `verify`/`census_gaps` cannot tell the difference. The isolation requirement is thus prose, not mechanism — the same docstring-vs-mechanism defect (`review-rotation.md:55`) applied to the instrument's headline obligation. (The module docstring even over-claims the enforcement at `:17–19`: *"Lenses are executed by READ-ONLY SUB-AGENTS, never by the authoring session inline"* — nothing enforces "read-only" or "never inline".)

**Remediation.** Give `brief` a stable id (hash of the emitted prompt) and require `record --brief-id <hash>` so a report names the brief it answers; store `recorded_by` (lane/session) and refuse a `record` whose lane equals the cycle's authoring lane recorded at `init`. If true isolation cannot be verified by the tool, downgrade the law's wording from "makes the isolation executable rather than advisory" to an explicit process-only requirement, and add a state field `isolation: "declared"` so the claim at least leaves a surface.

---

## F9 — LOW — Documentation drift within `tools/review.py`: the Usage block and the enforcement list omit the `codify` subcommand, and two `--help` strings disagree on the lens set

**File locators & verbatim quotes.**

Usage block `tools/review.py:39–53` lists 14 commands and omits `codify` (dispatch at `:2138`, parser at `:2091`). The enforcement list `:4–37` (items 1–8) likewise never mentions the `codify` writer that `docs/instruments/review-rotation.md:85` calls load-bearing (`**The writer is \`codify\`**`). Help strings disagree — `:2029` `p_brief.add_argument("lens", help="Lens letter (A-J, P, M, T, S)")` versus `:2034` `p_record.add_argument("lens", help="Lens letter (A-J, S)")`.

**Defect analysis.** `codify` is a first-class subcommand and the sole writer for `codification_plan`, yet the file's own map of itself omits it, so a reader trusting the docstring's Usage never learns the command exists. The two help strings describe the same lens set differently. Low severity (help text, not logic), but it is the same "docs drifted from the tool" class Lens I audits, and it is cheap to close.

**Remediation.** Add `python3 tools/review.py codify <cycle_id> --finding … --disposition …` to the Usage block and an item to the enforcement list; make both help strings read the same (`(A-J, P, M, T, S)` or `(the lawful lens set; see \`lenses\`)`).

---

## Summary

**9 findings.** The single most severe is **F1**: the adversarial briefs the engine emits are generated from `LENS_METADATA` — a second, drifted copy of the lens definitions — rather than from `docs/review-lenses.md`, the file the factory declares canonical; the two disagree on 4 lens names, 2 family names, several scopes, and 3 check-sets, and no gate pins them, so Lens I's own Core Check 1 ("Verify lens briefs match what reviewers actually evaluate") is defeated by the machinery Lens I audits. The next tier is the census's un-bypassability: **F2** (content-free 1-byte reports pass `verify` clean — measured), **F3** (a frozen/closed cycle is still mutable by `record` and `waive` — measured, `state.json` sha changed post-close), and **F4** (the "UNRECEIPTED (no index line)" state is unreachable because `verify` reads a self-stamped boolean, not `review-index.log` — measured, index log deleted and `verify` still PASS).

**Measurements that produced the findings:** `git rev-parse HEAD` → `af6d92776c1dce0159256ad100c6c0abf889e480`; `git diff --quiet HEAD -- <4 targets>` → all clean; behaviour of `init/record/close/verify/waive` on `/tmp/revtest` and `/tmp/revtest2` (14×1-byte reports → `census verified clean`, rc=0; post-close `record`/`waive` → rc=0 and `state.json` sha `f91edf…`→`8f78a0…`; deleted `review-index.log` → `verify` rc=0); `pytest --collect-only -q` → **31** tests (doc says 29 and 27); AST `REQUIRED_GATES` → **64** (doc says 56 and 54); `registry/gates.json` → gates **54**, modes **85** (doc says 48 and 74); `diff` root vs `TEMPLATE/` halves of both law docs → byte-identical; `ls` of `roles/`, `processes.md`, `SKILL.md` → all absent, so brief A's scope names three nonexistent paths. Every finding carries a `path:line` locator and a verbatim HEAD byte; nothing was estimated. No file under `/root/agent-factories` was modified.
