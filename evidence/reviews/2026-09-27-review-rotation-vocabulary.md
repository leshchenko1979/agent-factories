# Vocabulary review — the Review Rotation instrument

**Owns:** promotion criterion 6 (`template-instruments.md` §5.1.6 — the instrument's names read
against `ONTOLOGY.md`) for **Review Rotation**.
**Written:** 2026-09-27, by the Review Rotation lane. **Reviewer:** the Instruments-methodology lane.
**Method:** every term the instrument's own artifacts use, read against the canonical-terms table and
the banned-synonyms table of `ONTOLOGY.md`; then the two-sense check over the corpus.

**Predicate and scope for every count below:** `ONTOLOGY.md` canonical-terms table, first column
(instant 2026-09-27T14:1xZ: **61** rows), and — for corpus counts — `*.md`/`*.py` under
`docs/`, `TEMPLATE/docs/`, `tools/`, `TEMPLATE/tools/`, `tests/`, `TEMPLATE/tests/`, **excluding
`docs/proposals/` and `docs/projects/` BY PATH ANCHOR** (233 files). Exclusions are path-anchored,
never line-substrings: an un-anchored exclusion deletes any row that merely NAMES the excluded path,
including the row that defines the exclusion.

## 1. The terms, term by term

| term | canonical row in `ONTOLOGY.md`? | senses in the corpus | disposition |
|---|---|---|---|
| `Lens` | **NO — 0 rows** | the review catalogue's unit (14 in the shipped catalogue, **11** in the methodology core — see V1) | **earns a row** (cross-instrument: every member running P32 needs it) |
| `Review` | **NO — 0 rows** | the act; also the verb of a code review | earns a row, defined as the periodic multi-lens review |
| `Cycle` | **NO — 0 rows** | a bounded review rotation (`review.py` 20 uses; `review-lenses.md` 6) | earns a row — or is **defined in the instrument law** if it is not cross-instrument |
| `Waiver` | **NO — 0 rows** | a lens explicitly not run, with a reason; **the same word is used for a kit exemption** in `tools/kit_surfaces.py` (V4) | earns a row with the sense pinned to the lens, or the kit's use is renamed |
| `Census` | **NO — 0 rows** | the complete-or-waived **lens** census; the kit's **adoption / name / surface** censuses (V3) | earns a row per sense, or the instrument's sense is named distinctly |
| `Family` | **NO — 0 rows as a term**, but `rubric` is defined as *"the 19 quality criteria across **6 families**"* | the review's 6 lens families; the rubric's 6 quality families — **the same number naming two different sets** (V2) | **earns a row and a qualifier**; the bare "6 families" is ambiguous today |
| `Finding` | NO — 0 rows | a review finding; a patrol finding (`patrol_host_state.py` 12 uses) | define in the instrument law; cross-instrument only if another instrument adopts it |
| `Step 0` / `step-0` | NO — 0 rows | the frozen-input step of a cycle | define in the instrument law |
| `Boundary stamp` | NO — 0 rows | the observable cadence artifact | define in the instrument law, **derived from `cadence`** rather than coining a rival |
| `Consolidation` / `convergence` | NO — 0 rows | the leg that lands every accepted finding | define in the instrument law |
| `cadence` | **YES** — *"How often a process actually runs, against how often it is declared to run"* | — | **REUSE. Never re-coin.** The donor's boundary stamp measures exactly this row's concept |
| `receipt` | **YES** | — | REUSE |
| `evidence` | **YES** | — | REUSE |
| `subagent` | **YES** — *"A one-shot spawned session with no channel binding. **Never a lane**"* | — | REUSE — and see V5 for the spelling |
| `run`, `process`, `product`, `law` | **YES** | — | REUSE |

**Nothing in this instrument needs a NEW word for an existing concept.** The four already-canonical
terms above cover the process vocabulary the donor expressed in role-card prose.

## 2. Findings

| ID | finding | evidence | disposition |
|---|---|---|---|
| **V1** | **Two incompatible lens catalogues are live in the same corpus.** The shipped catalogue is **14 lenses / 6 families**; the methodology core describes an **11-lens** review over **5 families** | predicate: the module's own `CATALOG_LENSES` (14) vs `Lens ([A-Z]):` read out of `docs/methodology/02-quality-management.md` (11). Difference: shipped-only `M`, `P`, `T`; methodology-only: none | The instrument lands **one** catalogue and one lifecycle; the methodology core's §4 is a **second home for one thing** and is routed to its owner (HQ authors cross-factory law) |
| **V2** | **`Family` names two different sets of six.** `ONTOLOGY.md:40` defines `rubric` as *"the 19 quality criteria across 6 families"* (Documentation, Output, Machine, Law, Stewardship, Autonomy — `docs/quality-criteria.md:3`); the review catalogue's six are Docs & Language, Mechanical & Protocol, Tools & Interfaces, Artifacts/State/Flow, Economics & Telemetry, Meta & Governance | predicate: `\bfamil(y|ies)\b` over the corpus = **250** hits, top files `tests/test_criteria_count.py` (32) and `tools/review.py` (20) | **Ambiguity reported as a defect in the ontology, not tolerated.** The instrument's families take a qualifier (`lens family`) or the ontology gains a disambiguating row |
| **V3** | **`Census` carries two senses** — the review's complete-or-waived lens census, and the kit's fleet/tree enumerations (`kit_census.py` adoption, `kit_names.py` names, `kit_surfaces.py` surfaces) | predicate `\bcensus\b` = **197** hits; top: `docs/instruments/kit.md` (22), `tools/kit_names.py` (15) | The instrument's sense is named in its own law; if it is used cross-instrument it earns its own row |
| **V4** | **`Waiver` and `exemption` are near-synonyms for different objects.** The review waives a LENS (a reason for not running one); the kit declares an EXEMPTION (factory data, 487 hits vs 25) — yet `tools/kit_surfaces.py` uses "waiver" for the kit's own sense | predicate: `\bwaivers?\b` **25** vs `\bexemptions?\b` **487**; `grep -n waiv tools/kit_surfaces.py` → 4 lines, e.g. *"SHAPE, not a waiver for a missing file"* | Route to the kit instrument's owner: the kit's use should read `exemption`, which its own data files already use |
| **V5** | **The canonical term is spelled two ways inside the instrument's own files**: `sub-agent` **2**, `subagent` **3** | `review-lenses.md:8` and `review.py:8` say *sub-agent*; `review-lenses.md:64,135` and `review.py:499` say *subagent*. `ONTOLOGY.md` canonicalises `subagent` | Fix in the instrument's own text when the law lands (step 6); the frame's §5.1.3/§5.2 wording cites the requirement, and the review-lenses text is the catalogue's own file |
| **V6** | **The engine's family labels disagree with the catalogue's headings**: `review.py` Family 4 = *"STATE, DELIVERY & FLOW"* and Family 6 = *"META-GOVERNANCE"*, while `review-lenses.md` heads them *"ARTIFACTS, STATE & FLOW"* and *"META & GOVERNANCE"* | `grep -o '"family": "[^"]*"' tools/review.py \| sort -u` vs `grep -n '^## .*Family' docs/review-lenses.md` | A one-catalogue reconciliation is part of the engine step: two labels for one family is the same defect one level down |
| **V7** | **`Rotation` is not a term of art in the corpus** — 15 hits, none defining it | predicate `\brotation\b` = **15** hits, top file 2 | The instrument's NAME may use it; the law must not lean on it as a defined concept without a row |

## 3. What this review does NOT decide

- **Which terms are genuinely cross-instrument** is the frame's call, not this file's. This review
  reports the senses and the collisions; the frame's §8 split says a cross-instrument DEFINITION
  belongs to the methodology lane, and HQ authors anything that binds a member factory.
- **The methodology core's 11-lens catalogue is another owner's file.** V1 is reported, routed and
  not edited here.
- **A term that is only this instrument's** is defined in the instrument law (step 3) rather than
  earning a row in a shared ontology.
