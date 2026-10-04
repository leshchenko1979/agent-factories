# LENS A — Redundancy, Ontology & Provenance Sediment

**Repo under review:** `/root/agent-factories` @ HEAD `ee518861e1f20d4b2ebed42313a7508c237072ad` (2026-10-04 20:42:54 +0000)
**Lens letter:** A · **Cycle:** 20260927-c1 · **Mode:** isolated adversarial, read-only
**Scope (mapped by `CORPUS.md`):** `ONTOLOGY.md`; `skills/meta-factory/SKILL.md`; `docs/*.md`;
`docs/methodology/*`; `docs/instruments/*.md`; `README.md`.

**Method (what I read and ran).**
- Read in full: `ONTOLOGY.md` (539 lines), `README.md` (139), `skills/meta-factory/SKILL.md` (496),
  `skills/meta-factory/state.md` (188), `docs/processes.md` (213), `docs/process-audit.md` (partial),
  `docs/growth-stages.md` (partial), `docs/quality-criteria.md` (criterion sections).
- Counted with `grep -cE`, `grep -rn`, `awk`, `cmp`, `wc -l`, `ls` — never estimated.
- Ran the repo's own gates as evidence: `python3 tests/test_ontology.py` (rc=0, "61 canonical term(s),
  3 banned term(s), 189 file(s) scanned"), `python3 tests/test_criteria_count.py` (rc=0),
  `python3 tests/test_law_coverage.py` (rc=0, "37 mapped"), `python3 tests/test_template_sync.py`
  (rc=0, "95 pair(s) byte-identical").
- Resolved counts in code, not docstrings: `tests/gate_registry.REQUIRED_GATES` = **64**;
  `tools/review.CATALOG_LENSES` = **14**; `tests/test_template_sync.PAIRS` = **95**.

**Findings: 12.** Ordered most severe first.

---

## F1 — `P30` names two different laws; the single-ownership law is mis-cited as P30 (it is P31)

**File Locator:** `docs/processes.md:35` and `skills/meta-factory/state.md:87`

**Verbatim Quote:**
```
docs/processes.md:35
5. **Single Process Ownership (P30):** Every declared process has exactly one named

skills/meta-factory/state.md:87
**The Single Ownership Principle (P30):** Every declared process has exactly one named process owner role. Shared ownership is zero ownership.
```

**Defect Analysis.**
The canonical practice register defines `P30` as a *different* law and gives the
single-ownership law the number `P31`:
```
docs/best-practices.md:556   ## P30 — Autonomous incident remediation & template self-healing
docs/best-practices.md:582   ## P31 — Every process has exactly one named owner
```
The repo's own coverage gate agrees and maps the numbers accordingly:
```
tests/test_law_coverage.py:87   "P30": ["evidence/rework.md", "tests/test_rework.py"],  # Autonomous incident remediation
tests/test_law_coverage.py:88   "P31": ["docs/processes.md", "TEMPLATE/roles/hq.md"],  # Every process has exactly one named owner
```
So a reader who resolves the citation `(P30)` from `docs/processes.md` or `state.md` is sent to the
*incident-remediation* law, not to single ownership. This is the exact failure the ontology's own
"numeric enumeration consistency" target names. `tests/test_law_coverage.py` cannot catch it: it
extracts `^##\s+(P\d+)\b` headings from `best-practices.md` only and never reads a *prose citation* of
a P-number, so the two stale citations pass every gate (the gate reports "37 mapped", rc=0).

**Actionable Remediation.** Change the identifier in both files to `(P31)`:
`docs/processes.md:35` → `**Single Process Ownership (P31):**`;
`skills/meta-factory/state.md:87` → `**The Single Ownership Principle (P31):**`. Optionally add a leg
to `tests/test_law_coverage.py` that scans law prose for `\(P(\d+)\)` citations and asserts each
number resolves to the heading whose title matches the sentence.

---

## F2 — `ONTOLOGY.md` asserts the process register "is not yet written" while it ships `docs/processes.md` as the `ProcessRegister` object

**File Locator:** `ONTOLOGY.md:434`, `ONTOLOGY.md:442`, `ONTOLOGY.md:446`, `ONTOLOGY.md:449` vs `ONTOLOGY.md:368`

**Verbatim Quote:**
```
ONTOLOGY.md:434
| The process audit | Surveys, and the meta-factory | Owner / Governance | Surveys lane | Detection of unexecuted or stopped processes | **proposed** — the register is not written yet |

ONTOLOGY.md:449
keep their own band — and the register itself is not yet written.

ONTOLOGY.md:368
| `docs/processes.md` | `ProcessRegister` | process register with atomic subprocess contracts |
```

**Defect Analysis.**
`ONTOLOGY.md` is internally contradictory. Its own object table (line 368) lists
`docs/processes.md` as the live `ProcessRegister`, and `skills/meta-factory/SKILL.md:375` calls it
"the canonical process register"; but the same file's process section says the register "is not yet
written" and cites `docs/process-audit.md` §4.5 as the place it *would* be defined (line 442). The
repo state refutes the "not yet written" claim: `docs/processes.md` is 213 lines, carries a full
4-process register with atomic subprocess tables, and was last committed 2026-09-27 (`f4a9c6c`),
**two days before** `ONTOLOGY.md`'s own last edit 2026-09-29 (`8508cab`). The 8-row preview table at
`ONTOLOGY.md:425-434` is copied from the *proposed* `docs/process-audit.md` table (whose own header at
line 1 reads "Status: proposed, not law"), and lists processes — "The four gates", "Assignment",
"Execution watchdog" — that do not appear in the live register at all. This is stale provenance
presented as current canon, and it is the kind of contradiction that D4 ("Documentation consistency")
exists to prevent.

**Actionable Remediation.** In `ONTOLOGY.md`: delete the preview table at lines 425-434 and the
paragraph at 444-449; replace them with a pointer — "The register is `docs/processes.md`; the
proposal history is `docs/process-audit.md`." Also fix `docs/process-audit.md:6` ("The register itself
is not yet written"), which is now false, or retitle the file explicitly as a superseded proposal.

---

## F3 — The dead session uuid #254 retired from `SKILL.md` survives as a routing instruction in `README.md` and `docs/addons/harness/opencrabs.md`

**File Locator:** `README.md:121`, `docs/addons/harness/opencrabs.md:303` (and twin `TEMPLATE/docs/addons/harness/opencrabs.md:303`)

**Verbatim Quote:**
```
README.md:121
| OpenCrabs dev | `d72bd52d-42aa-4dbd-ac99-5b5300770019` | Crabs Kanban Board, topic `OC DEV HQ` |

docs/addons/harness/opencrabs.md:303
   (Crabs Kanban Board topic `OC DEV HQ`, session `d72bd52d-42aa-4dbd-ac99-5b5300770019`)
```

**Defect Analysis.**
Board `#254` retired this exact value from the law because it is **dead**:
```
evidence/rework.md:299
`skills/meta-factory/SKILL.md` section 5's substrate-routing table named
`d72bd52d-42aa-4dbd-ac99-5b5300770019` for OpenCrabs HQ, and that id carried ZERO bindings —
the topic it meant (OC DEV HQ, thread 30220) is bound to `0117dd29-5f4b-4184-9bf4-d19dc74ac266`.
```
`grep -n d72bd52d skills/meta-factory/SKILL.md` now returns rc=1 (removed), but the same uuid is
still shipped in two other surfaces a reader follows. `docs/addons/harness/opencrabs.md:303` is not
prose about history — it is the *dispatch instruction* telling a lane to reach OpenCrabs HQ by
`session_notify`, i.e. exactly the "reader follows a uuid that reaches nobody" defect `#254` fixed in
one place. The gate that was built for this class excludes both files by name/reason
(`tests/test_law_no_raw_session_uuid.py`: `NOT_COVERED` lists `README.md` — "orientation prose" — and
`docs/` — "narrative and generated artifacts"), so the incomplete sweep is invisible to every run.
This is a failed post-migration path sweep: the fix touched one surface of three.

**Actionable Remediation.** Replace the uuid with the lane/topic name in both files and the TEMPLATE
twin (`README.md:121` → `OpenCrabs dev / hq`, topic `OC DEV HQ`; `docs/addons/harness/opencrabs.md:303`
→ "…reached by `session_notify` to the lane `opencrabs-dev`/`hq`, resolved live at dispatch").
Then either narrow the gate's `NOT_COVERED` reason so a *routing instruction* in `docs/` is still
covered, or add these two paths to `docs/law-uuid-exemptions.json` so the residual debt prints on
every run instead of being silently excused.

---

## F4 — `ONTOLOGY.md`'s `pair` vs `twin` row asserts "The residual uses are NOT the pair relation" — false; ≥6 law-surface lines use `twin` for exactly that relation

**File Locator:** `ONTOLOGY.md:462`

**Verbatim Quote:**
```
ONTOLOGY.md:462
| `pair` vs `twin` | … **The residual uses are NOT the pair relation** and are kept: `tools/ledger.py`'s `twin` variable names the row sharing a patch-id; `docs/addons/surface/telegram-forums.md` names a migrated group; one `test_patrol_host_state.py` fixture string uses it of two candidate rows. **Predicate for any count here**, since a bare number cannot be checked: `grep -rn '\btwin\b'` over the law corpus, then exclude `docs/proposals/` and `docs/projects/` (the rename discussion itself). …
```

**Defect Analysis.**
Running the row's *own prescribed predicate* (`grep -rn '\btwin\b'` over the law corpus, excluding
`docs/proposals/` and `docs/projects/`) yields residual uses that **are** the byte-identical pair
relation, contradicting the row's claim:
```
docs/instruments/open-questions.md:307   …not in the law pair's twin gate, so nothing checks it…
docs/instruments/pacemaker.md:188         row of class `closure`, byte-paired with its root twin (`cmp` rc=0)…
docs/instruments/kit.md:257               `tests/test_kit_pin.py:144`, paired byte-identically with its `TEMPLATE/` twin,
tools/patrol_host_state.py:2335           file is byte-identical to its TEMPLATE twin, whose REPO resolves to TEMPLATE/…
tests/test_patrol_host_state.py:2328      # TEMPLATE twin, whose REPO resolves to TEMPLATE/ where `registry/kit.json` is
tools/review.py:1572                      (`TEMPLATE/docs/` twin) is generated from THIS command…
```
Each of these names the shipped-file ↔ template-copy relation, which the row itself declares "`twin`
is not the term" for. Because `twin` is only a *contextual* synonym (the `## Banned synonyms` table
holds just 3 entries — `supervisor`, `meta-layer`, `meta layer` — and the gate confirms "3 banned
term(s)"), the rival spelling survives ungated in the instrument docs. The row's claim of
completeness is therefore a false all-clear: a reader trusting it stops looking, and the rename is
half-done in the law surfaces the ontology points at.

**Actionable Remediation.** Either (a) rename these six `twin` uses to `pair`, or (b) correct the row
to enumerate them and stop claiming "NOT the pair relation". If `twin` (pair sense) is to be
enforced, add it to the `## Banned synonyms` table — which the gate parses — rather than leaving it a
"Terms that are not synonyms" note.

---

## F5 — `ONTOLOGY.md`'s "live instances" object table is stale: `Score` = "2026-09-12, 14 of 52", `WorkUnit` = "issues #6 to #12"

**File Locator:** `ONTOLOGY.md:362` and `ONTOLOGY.md:359`

**Verbatim Quote:**
```
ONTOLOGY.md:362
| 2026-09-12, 14 of 52 | `Score` | the latest reading of this factory |

ONTOLOGY.md:359
| issues #6 to #12 | `WorkUnit` | the work units this factory has run |
```

**Defect Analysis.**
The table is introduced at `ONTOLOGY.md:346` as "these are the objects: this factory's **live
instances** of them", but both rows are superseded. The latest score file is
`evidence/scores/2026-10-04.md` (v0.5, max 76), not `2026-09-12`; and `14 of 52` is not even on the
current scale — 52 was the retired v0.4 maximum (`docs/growth-stages.md:128` labels v0.4 as
"superseded by v0.5 (19 criteria across 6 families, max 76)"). The work-unit range `#6 to #12` is
long past: `evidence/ledger.jsonl` holds 2245 rows and the board runs into the 300s. A canonical
ontology that presents retired readings as live teaches the reader a stale fact every time it is
opened. (This is not gated: `tests/test_criteria_count.py` checks `N criteria`/`N families` claims,
not a `Score` object instance.)

**Actionable Remediation.** Refresh `ONTOLOGY.md:362` to the latest reading (`2026-10-04`) or replace
the row with a pointer to `evidence/scores/`; change `:359` to "the closed work units (see the
board / `evidence/ledger.jsonl`)" and drop the bounded range.

---

## F6 — `TEMPLATE/roles/hq.md` says "the 11-lens review"; the catalog and the tool are 14 lenses

**File Locator:** `TEMPLATE/roles/hq.md:20`

**Verbatim Quote:**
```
TEMPLATE/roles/hq.md:20
  (the 11-lens review, **P32** / `docs/review-lenses.md`), triple-checks findings,
```

**Defect Analysis.**
The named catalog is titled "The Generic **14**-Lens Factory Review Catalog"
(`docs/review-lenses.md:1`), carries 14 `### Lens` headings (`grep -c "^### Lens"` = 14), and the
tool agrees (`tools/review.CATALOG_LENSES` = 14: `['A','B','G','J','P','C','E','F','D','H','M','T','I','S']`).
The HQ role card tells its reader to expect 11. This is a numeric enumeration inconsistency inside a
role card — the closest surface in this repo to the brief's `roles/*.md` — and it is the same
`Family`/count split the 2026-09-27 vocabulary review recorded as finding V1 ("The shipped catalogue
is 14 lenses / 6 families; the methodology core describes an 11-lens review over 5 families").

**Actionable Remediation.** Change `TEMPLATE/roles/hq.md:20` to "the 14-lens review". If a lens-count
gate is wanted, extend `tests/test_criteria_count.py`'s predicate to `N-lens` claims over
`docs/review-lenses.md`.

---

## F7 — `docs/growth-stages.md` claims the meta-factory "runs 8 deterministic gates" — the live registry declares 64

**File Locator:** `docs/growth-stages.md:159`

**Verbatim Quote:**
```
docs/growth-stages.md:159
   - **Meta-factory & OpenCrabs dev:** Full Stage 3 maturity. Meta-factory runs 8 deterministic gates via `tools/audit.py`, measuring lead times, yields, and automated issue generation (P1/P27).
```

**Defect Analysis.**
`tests/gate_registry.REQUIRED_GATES` holds **64** entries (measured by import, not by docstring). The
"8" is a fossil of the same class `docs/processes.md:134` already confesses to ("this line read 'all
8 mechanical gates passing in <10s' while the suite was 15 gates and ~25s"). Unlike the `processes.md`
line — which is now correctly framed as a corrected historical example — the `growth-stages.md` claim
sits in an *undated* "Stage-by-Stage Verification Summary" presented as the current fleet reading
(the file carries no date or version header; `docs/growth-stages.md:141` onward reads as live state).
A number that drifts with no gate reading it is the P29 shape.

**Actionable Remediation.** Delete the hardcoded "8" and read the count live (the file already has a
precedent for "read live, never restated" in `docs/processes.md:128-134`), or stamp the section with
the date of the snapshot it describes.

---

## F8 — The lane roster is duplicated in `README.md` and `SKILL.md §3`, and README's copy is stale (4 lanes, no Worker, dated 2026-09-11)

**File Locator:** `README.md:92-97` (vs `skills/meta-factory/SKILL.md:110-116`)

**Verbatim Quote:**
```
README.md:94-97
| `HQ` | 21 | `2646d31a-71ee-49f0-be81-9c8dc32d32fa` | Analysis, rulings, owner conversation |
| `Delegate` | 68 | `23549292-77ff-40d1-97e3-5aa0bdd19d74` | Member-factory comms — dispatches to member HQs, and their answers |
| `Triage` | 20 | `f4c192c9-a8e9-4268-9026-ee3e4970cc8a` | Intake and routing |
| `Surveys` | 19 | `5c99ad51-8889-40cb-b589-fa13fd673c06` | Survey and measurement work |
README.md:100
message arrives — outbound sends never claim a topic. All four are live as of
```

**Defect Analysis.**
One roster, two homes, and the two disagree. `SKILL.md §3` lists **five** lanes (adds
`Worker` | 1271 | `dcd8f7a9-…`) read back "on 2026-09-18 12:20Z" and explains the Worker lane was
added by owner order; `README.md` lists **four** and says "All four are live as of 2026-09-11
14:20Z". The Worker lane — the implementation destination `SKILL.md` §3 makes load-bearing ("a work
item with no lane to take it is a missing lane") — is absent from the README a newcomer reads first.
Duplication of a state table is the class `SKILL.md §11` ("one writer per surface") forbids; here the
second copy has drifted.

**Actionable Remediation.** Reduce `README.md`'s "This project's own surface" section to a pointer
("The live roster is `skills/meta-factory/SKILL.md` §3; ids are re-read from `session_bindings` before
any send"), or generate it from the same source.

---

## F9 — Provenance sediment: dated incident narratives are embedded in the canonical ontology tables

**File Locator:** `ONTOLOGY.md:462` and `ONTOLOGY.md:463`

**Verbatim Quote:**
```
ONTOLOGY.md:462
… **`twin` is not the term, and on 2026-09-26 the kit's own shipped hook was using it for exactly that relation** … Renamed to `pair` in the hook, its gate and four test comments. … A count published without that predicate was wrong twice while this row was being written — 6, then 49, then 45 …
ONTOLOGY.md:463
… Measured 2026-09-26: **~727 generic mechanism**, **57 state**, **9 chat**. …
```

**Defect Analysis.**
The brief's target 3: dates, post-mortem anecdotes and history belong in a changelog. `ONTOLOGY.md`
is the canonical vocabulary — "One term, one meaning" — yet two of its "Terms that are not synonyms"
rows carry multi-sentence incident narratives (a hook rename on a named date, a count that "was wrong
twice … 6, then 49, then 45", a bucket measurement of "~727 / 57 / 9" on a named date). The ontology
already has a home for exactly this history: `evidence/rework.md` (229 dated entries) and the
`docs/proposals/` rename discussion the row itself tells readers to exclude. Keeping the narrative in
the vocabulary table inflates the canonical file and mixes the term's *meaning* with the story of how
it was found — the reader who wants the definition must parse the post-mortem.

**Actionable Remediation.** Move the narrative halves of `ONTOLOGY.md:462-463` into
`evidence/rework.md` (they are rework entries in all but location) and leave each row as: the term,
its one-sentence meaning, the banned synonym, and the checkable predicate — no dates, no incident.

---

## F10 — `SKILL.md §11` states a universal ("every instrument ships as a doc pair") that `docs/instruments/insights.md` refutes

**File Locator:** `skills/meta-factory/SKILL.md:360` (vs `docs/instruments/insights.md:28`)

**Verbatim Quote:**
```
skills/meta-factory/SKILL.md:360
… The contract for an instrument — its verbs, store path, gates and closure — ships as a doc pair (`docs/instruments/<instrument>.md` + `TEMPLATE/docs/instruments/<instrument>.md`) …

docs/instruments/insights.md:28
**No path in this instrument ships — the declared set is empty.**
```

**Defect Analysis.**
`docs/instruments/` holds 8 files; `TEMPLATE/docs/instruments/` holds 7 (`ls | wc -l`). The missing
twin is `insights.md`, and the instrument's own law declares the absence deliberate — owner order
2026-09-28, "this insights tool should not be a part of the kit — it's the meta factory's subject
matter only" (`docs/instruments/insights.md:28-30`). So `SKILL.md §11`'s unqualified universal is
false for 1 of its 8 instruments, and a member reading §11 would expect a shipped
`TEMPLATE/docs/instruments/insights.md` that must never exist. This is the factory's own recorded
defect class — "a rule generalised from a population that excluded the counterexample class"
(`evidence/rework.md:323`, #291) — reappearing in the law.

**Actionable Remediation.** Qualify `SKILL.md:360`: "every instrument that **ships** ships as a doc
pair", and name `insights` as the declared meta-factory-only exception (or move the sentence's
subject to "a shipped instrument").

---

## F11 — Canonical vocabulary used as law but not codified as terms: `pair`, `Worker`, `Carrier`, `family`

**File Locator:** `ONTOLOGY.md:462` (declares `pair` "the term"), canonical table at `ONTOLOGY.md:22-84` (no `pair` row)

**Verbatim Quote:**
```
ONTOLOGY.md:462
| `pair` vs `twin` | A **pair** is the byte-identical relation between a shipped file and its template copy — the term the manifest, the gate and the hook use (`PAIRS`, `test_template_sync.py`). …
```

**Defect Analysis.**
`ONTOLOGY.md:17` states the rule: "Every term below is the **only** word allowed for that concept".
But several words the law treats as canonical are not *below* — they are not in the terms table at
all, so a reader cannot look them up:
- **`pair`** — declared "the term" for the shipped↔template relation (line 462) but absent from the
  canonical table (`grep '^| \`pair\`' ONTOLOGY.md` returns nothing; `pair` appears only in the
  narrative row).
- **`Worker` / `Carrier`** — first-class roles/lanes in the law (`TEMPLATE/roles/worker.md`,
  `carrier.md`; the participants table at `ONTOLOGY.md:389-390`), while the four other lane terms
  (`HQ`, `Delegate`, `Triage`, `Surveys`) are codified. `Worker` appears in 46 files, `Carrier` in 6.
- **`family`** — used as a canonical unit ("the 19 quality criteria across 6 families", `ONTOLOGY.md:40`)
  but never defined, and the 2026-09-27 vocabulary review flagged that the same word names two
  different sets of six (the rubric's families vs the lens catalogue's). No disambiguating row was
  added.

**Actionable Remediation.** Add canonical rows for `pair`, `Worker`, `Carrier`, and `family` (or an
explicit "not a term of art" note for `family`), so the vocabulary the law actually binds is the
vocabulary the ontology codifies.

---

## F12 — Rule duplication: the single-ownership law is restated verbatim on three surfaces

**File Locator:** `docs/processes.md:35-36`, `skills/meta-factory/state.md:87`, `docs/best-practices.md:582-584`

**Verbatim Quote:**
```
docs/best-practices.md:584   Every declared process has exactly one named process owner role. Shared
skills/meta-factory/state.md:87   …Every declared process has exactly one named process owner role. Shared ownership is zero ownership.
docs/processes.md:36   **process owner** role. Shared ownership is zero ownership. Accountability cannot
```

**Defect Analysis.**
The same constraint — "Every declared process has exactly one named process owner role. Shared
ownership is zero ownership." — is stated word-for-word in three law files. `docs/best-practices.md`
is the canonical register (the law-coverage gate treats its `## Pn` headings as the source of truth),
so the two restatements in `state.md` and `processes.md` are copies that can drift — and, as F1
shows, they already have (both carry the wrong number `P30`). Duplicated prose is exactly the class
the factory's own P29 ("a rule without an upholding mechanism is dead text") and the `#43` rework entry
("restated in prose on each surface instead of being derived") record as the cause of prior drift.

**Actionable Remediation.** Keep the definition in `docs/best-practices.md` P31; in `state.md:87` and
`processes.md:35` replace the restatement with a pointer ("single ownership, P31 — see
`docs/best-practices.md`") so the wording has one home.

---

## What I checked and found clean (so the pass is not silent)

- **Rubric count.** "19 criteria / 6 families / max 76" is consistent and gated: I counted the
  criterion rows by family in `docs/quality-criteria.md` (D1-D4, O1-O3, M1-M4, L1-L3, S1-S3, A1-A2 =
  **19**) and ran `tests/test_criteria_count.py` (rc=0, "23 claim(s) over 104 file(s) all read 19
  criteria / 6 families, 3 excused").
- **Banned-synonym gate.** `python3 tests/test_ontology.py` passes (rc=0, "61 canonical term(s), 3
  banned term(s), 189 file(s) scanned"); no unexempted `supervisor` / `meta-layer` / `meta layer` use
  survives in the scanned corpus (`grep -rn` finds only the ontology's own ban table and contextual-
  synonym column).
- **Template sync.** `python3 tests/test_template_sync.py` passes (rc=0, "95 pair(s) byte-identical").
- **Law coverage.** `python3 tests/test_law_coverage.py` passes (rc=0, "37 mapped"); every declared
  `## Pn` heading is mapped and every key resolves.
- **No CI config exists**, so `ONTOLOGY.md:504`'s "no CI runner is configured yet" is accurate, not
  stale.
- **Instrument symlinks.** All eight `skills/meta-factory/*.md` symlinks resolve to existing files
  (`find`/`readlink -f`); none are dead.

---

## Summary

**12 findings.** The single most severe is **F1**: the identifier `P30` names two different laws
across the corpus — `docs/best-practices.md:556` defines `P30` as "Autonomous incident remediation &
template self-healing" and `P31` as "Every process has exactly one named owner" — yet
`docs/processes.md:35` and `skills/meta-factory/state.md:87` both cite `(P30)` for the
single-ownership law, so a reader resolving the citation is sent to the wrong law and no gate can
catch it (`tests/test_law_coverage.py` never reads a prose P-number citation).

Measurements that produced the findings: `grep -cE "^## P[0-9]+" docs/best-practices.md` → **37**
(P1–P37); `grep -rn "P30" --include=*.md .` and `grep -n "P31" tests/test_law_coverage.py` →
the collision; `read_file` of `ONTOLOGY.md` (lines 346-449) and `grep -n "not yet written"` →
the stale register claim; the row's own predicate `grep -rn '\btwin\b' --include=*.md --include=*.py .`
(minus `docs/proposals/`, `docs/projects/`) → 6 pair-relation residuals; `grep -n d72bd52d README.md
docs/addons/harness/opencrabs.md` + `grep -n d72bd52d skills/meta-factory/SKILL.md` (rc=1) →
the incomplete #254 sweep; `python3 -c "import tests.gate_registry as g; print(len(g.REQUIRED_GATES))"`
→ **64** vs the "8" in `docs/growth-stages.md:159`; `grep -c "^### Lens" docs/review-lenses.md` → **14**
vs "11-lens" in `TEMPLATE/roles/hq.md:20`; `ls docs/instruments | wc -l` (**8**) vs
`ls TEMPLATE/docs/instruments | wc -l` (**7**) → the `insights.md` doc-pair exception; and the repo's
own gates `tests/test_ontology.py`, `test_criteria_count.py`, `test_law_coverage.py`,
`test_template_sync.py` all run rc=0 (so the defects above are in surfaces the gates do not read, not
gates that are failing).
