# Donor contract inventory — the Review Rotation promotion (step 2)

**Owns:** the clause-by-clause inventory of opencrabs-dev's Duty 4/6 donor contract, each row carrying
its mechanism, the promoted artifact it becomes, its class, its member-facing behaviour and its
**disposition**.
**Written:** 2026-09-27 by the Review Rotation lane. **Method:** every path and line number below was
confirmed by `grep -n` / `ls` **in the same turn it is cited** — none is taken from memory.

**Dispositions (the vocabulary this inventory uses, and nothing else):**
`KERNEL` — reusable mechanics that move into the promoted instrument · `ACCEPT` — already shipped in
the template, nothing to move · `DONOR-LAW` — stays the donor's own law, cited never shipped ·
`ROUTED` — belongs to another owner, dispatched with a receipt · `REJECT` — not promoted, **reason
recorded, never silently dropped**.

## 0. The donor's own root, and why its two `reviews/` roots matter here

| path | receipt | fact |
|---|---|---|
| `skills/opencrabs-dev/hq.md` | `wc -l` = **334**; Duty 4 at `:137`, Duty 6 at `:184` | the donor contract, in a **role card** |
| `~/.opencrabs/profiles/ops/opencrabs-dev/reviews/` | `ls -lt` = **11 cycle dirs**, newest `20260927-c25` | the CANONICAL state root (`$OC_DEV_STATE`) |
| `skills/opencrabs-dev/reviews/` | donor law §Duty 6.0 | FROZEN EVIDENCE — never swept, never written |

`hq.md:192-200` states the two-root rule and names the defect it caused (`hq.md:199`): `oc-review-persist`'s own
`DEFAULT_DIR` is the **skill** root, so a run without `--dir` writes evidence into the frozen tree.
That is a donor-internal hazard the promoted instrument must not inherit (row **D-14**).

## 1. The catalogue — FOUR derivations of one fact, and they disagree

This is the single largest finding of the inventory, and it is measured, not inferred.

| # | derivation | where | what it yields |
|---|---|---|---|
| C1 | **briefs catalogue** | `skills/opencrabs-dev/review-lenses.md` — 300 lines, 22 545 B, sha256[:16] `e2b9931005f92aef` | **11** lenses: `- **Reviewer A — …` … `- **Reviewer J — …` plus a standing `brain-scrub` |
| C2 | **lens catalogue** | `TEMPLATE/docs/review-lenses.md` — 176 lines, 12 926 B, sha256[:16] `e4f1f26b2cbe4d2b` | **14** lenses: `### Lens A — …` … `### Lens S — …`, including **M, P, T** (`:117`, `:59`, `:129`) |
| C3 | **engine constant** | `TEMPLATE/tools/review.py` `CATALOG_LENSES` | **14**: `A B G J P C E F D H M T I S` (read by `import`, not counted from prose) |
| C4 | **persist whitelist + dispatch globs** | `skills/opencrabs-dev/tools/state/oc-review-persist:56` and `:285-287` | `LENSES=" A B C D E F G H I J self redundancy-ontology efficiency-creep cli-automation deletion-safety brain-scrub "` — and the dispatch accepts only `[A-J]`, `[A-J][0-9]`, or a whitelisted name |

**Three consequences, each with its own receipt:**

1. **C1 and C2 are two documents under ONE name.** Same basename, different line count, different
   digest, different content model (briefs vs catalogue). This is the frame's *"two homes for one
   thing"* in its purest form, and it is the thing promotion must collapse.
2. **C4 cannot persist C2/C3's extra lenses.** `oc-review-persist M` (or `P`, `T`) falls through every
   dispatch arm at `:285-287` and dies `rc=2 unknown lens`. The engine can **brief** M/P/T; the donor's
   persistence tool can never **persist** them.
3. **C4's census derivation returns ZERO against C2.** `oc-review-persist:86` derives the expected set
   with `sed -n 's/^ *- \*\*Reviewer \([A-Z]\) .*/\1/p' "$LENSES_MD"` — the **C1** form. Against the
   **C2** file that matches **0** lines (`grep -c '^- \*\*Reviewer [A-Z]'` on C2 = **0**), and the
   `#### STANDING LENS:` arm matches **0** as well (`grep -c '#### STANDING LENS'` on C2 = 0;
   on `fleet-directives.md` = **0**). So `NEXP=0` → `:96` `die 3 "catalog UNDERIVABLE"`. The gate fails
   **LOUD** rather than calling a cycle clean — which is correct behaviour and still means the
   promoted catalogue cannot serve the donor's census gate unmodified.

**The methodology core is a fourth catalogue and is NOT one of the above:** `docs/methodology/02-quality-management.md`
`:88` heads its section *"Periodic **11-Lens** Factory Review"* and lists **11** lens letters
(`Lens ([A-Z]):` → `A B C D E F G H I J S`), i.e. it agrees with **C1** and disagrees with **C2/C3**.
Delta between C2 and the 11: exactly **M, P, T**.

## 2. The mechanism inventory

| # | donor mechanism | receipt (same-turn) | promoted artifact | class | member-facing behaviour | disposition |
|---|---|---|---|---|---|---|
| D-1 | Duty-4 poll fanout to editors | `hq.md:143-152`; `tools/notify/oc-notify-fanout` (75 043 B) | a **declarative input surface** + an executable intake leg | `standalone` | member declares where input lands; the tool reads it | **KERNEL** |
| D-2 | proposal file format `ADD\|CHANGE <rule> in <file+section> BECAUSE <evidence>` | `hq.md:152` | the input schema, versioned with the instrument | `standalone` | member's lanes write to the declared path | **KERNEL** |
| D-3 | proposals written to disk at `reviews/<cycle-id>/proposals/<uuid>.md` | `hq.md:145`; live dir `20260927-c25/proposals/` = **85 files** | the intake directory, cycle-scoped | `seed` | factory-owned; never overwritten by an update | **KERNEL** |
| D-4 | ledger intake leg `oc-ledger stamp proposal` / `events --kind proposal` | `hq.md:147`, `:154-165` | the ledger is a **second input channel**, declared not assumed | `seed` | member may have no ledger — the leg must be optional and **named** when absent | **KERNEL** |
| D-5 | live roster FIRST | `hq.md:150`; `tools/state/oc-roster` (14 808 B) | not shipped — roster is a fleet concept | — | a member has its own lane model | **ROUTED** (donor law) |
| D-6 | cadence: after every FIVE shipped version bumps, shared trigger | `hq.md:139`; `oc-ledger:1384` `cmd_cadence`, boundary = newest `note` matching `^v[0-9]+\.[0-9]+\.[0-9]+ ACCEPTED`, fires at `>=5` | an **observable cadence artifact** — the boundary stamp | `standalone` | the instrument states its own cadence state; a member with no version bumps declares a different trigger | **KERNEL** |
| D-7 | step-0 cycle state + recovery mandate | `hq.md:191-217`; live `20260927-c25/state.json` (379 B) | the cycle state schema + a resume path | `standalone` | the instrument's own state, in the member's tree | **KERNEL** |
| D-8 | **frozen** state schema (five field names are law) | `hq.md:201-211` | the schema definition, once | `standalone` | — | **KERNEL** |
| D-9 | lens execution by **read-only subagents**, one per lens | `hq.md:226-231`; already shipped: `review-lenses.md:8`, `review.py:8`, `:499` | nothing to move | — | already in the template | **ACCEPT** (already shipped) |
| D-10 | hollow-report → ONE retry → inline fallback, **flagged** | `hq.md:233-235` | a refusal/non-vacuity state on the lens | `standalone` | a hollow lens is a **named state**, never a silent pass | **KERNEL** |
| D-11 | persistence: `oc-review-persist <lens> @<file>`, re-read + sha256 verified | `hq.md:250-261`; tool 22 275 B; index line `ts\|lens\|path\|sha256\|bytes` | receipt verification over persisted reports | `standalone` | every persisted report carries a receipt; a report with no index line is **UNRECEIPTED**, a distinct state | **KERNEL** |
| D-12 | complete-or-waived census gate `check-cycle` | `oc-review-persist:23-152`; `waivers.log` format `ts\|lens\|by\|reason` (`:141`) | the lens census + the waiver record | `standalone` | **the waiver is a FILE with a reason, not a dict** — see §3 | **KERNEL** |
| D-13 | waiver semantics: a deliberately-skipped lens is a DECISION | `oc-review-persist:139`, `:147` | as D-12 | `standalone` | a waiver without a reason must be refused | **KERNEL** |
| D-14 | `--dir` explicitness, because `DEFAULT_DIR` points at the frozen root | `hq.md:192-200` | **eliminated by design**: the promoted engine takes its cycle dir as an argument and has no frozen-root default | `standalone` | — | **KERNEL** (as a fix, not a port) |
| D-15 | mechanical corpus pack (`pack.py`) at cycle open, corpus hash recorded | `hq.md:219-224`; `/root/.opencrabs/profiles/ops/projects/jev-bloat-review/pilot/pack.py` (3 520 B); live `evidence/mech-pack.json`, `corpus_hash c936be0e6b991f81` | **NOT promoted** — it is a project-dir trial with a 9-file module set, called by ABSOLUTE PATH | — | a cycle may run on semantic evidence only, **and the record must say so** | **REJECT** (reason: it is not packaged; `hq.md:223` itself calls routing it into `tools/` "a separate decision". The *reporting* obligation it carries — "a missing or failing pack is REPORTED, never silently skipped" — is KERNEL and folds into D-10.) |
| D-16 | layer-2 mechanisation is **REPORT-ONLY** (its gate failed pre-registration: precision 0.111 / recall 0.126 vs bars 0.70 / 0.40, n=66) | `hq.md:244-248` | a **refusal to promote a failed gate**, recorded | — | a mechanisation opportunity names the tool owner AND the command | **ACCEPT** (already decided) |
| D-17 | verdict table; **every accepted finding lands in its entirety**, partition must sum to the census count | `hq.md:169`, `:266` | the **COMPLETENESS** half: a cycle that accepts a finding and lands no home for it is INCOMPLETE | `standalone` | this is a property of the review, portable to any member | **KERNEL** |
| D-18 | the **NO-GATE** half: fixes land with no design gate, no plan card, no owner approval | `hq.md:169`, `:263` | nothing ships | — | **shipping this as a tool property would strip a member owner's own design gate** — the tool would carry an authority it does not have | **DONOR-LAW** |
| D-19 | findings whose fix belongs to another owner are ROUTED and recorded as routed | `hq.md:169`, `:266` | the routing leg of the completeness check | `standalone` | routed is a disposition; dropped is not | **KERNEL** |
| D-20 | reviewer-performance loop + per-lens census (yield / overlap / cost) | `hq.md:268-283` | the lens census artifact | `standalone` | — | **KERNEL** |
| D-21 | cadence-reset close stamp, ANCHORED `^v<digits>.<digits>.<digits> ACCEPTED` | `hq.md:284-286`; `oc-ledger:1392` | the boundary predicate, stated as a predicate and not a substring | `standalone` | the gate must anchor, or a loose grep harvests an END from a row whose point is that none was written | **KERNEL** |
| D-22 | `WITHHELD:` prefix for a note that deliberately writes no END | `hq.md:212-214` | as D-21 | `standalone` | — | **KERNEL** |
| D-23 | cycle id minted ONCE and written to BOTH stores | `hq.md:206` | the id rule | `standalone` | — | **KERNEL** |
| D-24 | `duration_review_min` vs `duration_cycle_min` are TWO numbers | `hq.md:207-209` | both, named | `standalone` | — | **KERNEL** |
| D-25 | session routing, board identifiers, HQ-only actions, owner-topic posting | `hq.md:267` ("posts to owner topic 30220") | nothing ships | — | donor process law | **DONOR-LAW** |
| D-26 | `Duty 4` / `Duty 6` as **names** | `hq.md:137`, `:184` | nothing ships | — | donor-role labels only; the instrument is **Review Rotation** | **DONOR-LAW** |
| D-27 | the `brain-scrub` standing lens | `oc-review-persist:56` whitelist; `hq.md:231`, `:236` family map | must resolve to ONE canonical lens identity | `standalone` | `brain-scrub` and lens **S** name the same lens under two names today | **KERNEL** |

## 3. The two state schemas, side by side

| key | donor live `state.json` (`20260927-c25`, 379 B) | template engine `cmd_init` (`review.py:219-227`) | verdict |
|---|---|---|---|
| `cycle_id` | yes | yes | agree |
| `status` | `IN_PROGRESS` | `IN_PROGRESS` | agree |
| `started_at` | yes | yes | agree |
| `ended_at` | `null` | **absent** | donor-only |
| `duration_review_min` | `null` | **absent** | donor-only |
| `duration_cycle_min` | `null` | **absent** | donor-only |
| `lenses` | `{}` (empty object in the live file) | `{lens: {status, report_path, sha256}}` | **same key, different value shape** |
| `proposals` | `[]` | **absent** | donor-only |
| `codification_plan` | `[]` | `[]` | agree |
| `cadence` | `"9/5 FIRE (boundary n=11363) …"` | **absent** | donor-only |
| `corpus_hash` | `c936be0e6b991f81` | **absent** | donor-only, and D-15's `REJECT` means it does not ship |
| `waivers` | **absent** — waivers live in `waivers.log` as `ts\|lens\|by\|reason` | a top-level `{}` **dict** | **two homes, two shapes** |
| `updated_at` | **absent** | written by `save_state` | engine-only |

**A compatibility path is therefore required, and it is NOT a rewrite:** the donor's live cycle is
evidence and is migrated by a documented adapter or a frozen legacy reader. The engine's
`get_cycle_dir` returns `REPO_ROOT / "reviews" / cycle_id` (`review.py:186-187`) with `REPO_ROOT`
resolved from the module's own path — so a member's cycle dir is its own tree's, and the donor's
two-root split does not exist there.

## 4. What the inventory changes about the plan

- **Step 3's schema definition is now a reconciliation of THREE live shapes** (donor state.json, engine
  state.json, `waivers.log`), not a greenfield definition.
- **Step 5's "reconcile the catalogue" is the largest single item**: FOUR derivations of the lens set
  disagree (§1). One catalogue, one derivation, and `oc-review-persist`'s `[A-J]` dispatch globs must
  widen in the same edit as the whitelist — `oc-review-persist:56`'s own comment records that a
  whitelist-only change leaves the letter accepted by one arm and rejected by another.
- **D-18 is the F5 question in its concrete form**, and the narrower reading stands until HQ rules.

## 5. Bounds — what this inventory does not say

- It does **not** decide which catalogue is canonical; that is step 5's work and the frame's §8 says
  a cross-instrument definition is the methodology lane's.
- It does **not** adjudicate the donor's live cycle: the cycle is **IN_PROGRESS** at this instant
  (`state.json` `status`, `ended_at: null`), so its completeness is not assessable here.
- The `REJECT` on D-15 is a rejection of **shipping that module**, not of the evidence it produces.
