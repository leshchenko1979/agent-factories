# Review Rotation — the promotion decision record

**Owns:** the promotion decision for the **Review Rotation** instrument — its name, its donor, the six
promotion criteria read as evidence, and the scope boundary between reusable mechanics and
donor-only governance.
**Writer:** the Review Rotation lane. **Reviewer:** the Instruments-methodology lane — the frame's own
law makes review of a per-instrument file a **requirement, not a courtesy** (frame §8).
**Authority:** **HQ retains cross-factory authority.** Any clause in this file that binds a member
factory is HQ's, and so is the process law *about* instruments; both are cited here, never coined.

**This file cites `template-instruments.md`, the frame, and never restates it.** The instrument's own
law is `docs/instruments/review-rotation.md`; the frame's definitions (§1 instrument, §2 the nine
parts, §3 class, §4 names, §5 promotion, §7 version and deferred, §8 ownership) are cited by section
and not copied.

**"Duty 4" and "Duty 6" are donor-role labels.** They name opencrabs-dev's own role card sections and
appear nowhere as this instrument's name.

## 1. What is being promoted, and why it is a COMPLETION

**Its job, in one sentence: a factory collects operational input on a declared cadence, runs a
bounded adversarial review across a complete lens catalogue, freezes a cycle's evidence and decisions,
and converges every accepted finding.**

The template ships the **incomplete half** and the donor holds the **orchestration half**:

| half | where it is today | what it carries | what it lacks |
|---|---|---|---|
| review record | `TEMPLATE/tools/review.py` (class `standalone`) | the 14-lens / six-family catalogue, `init`/`brief`/`record`/`waive`/`status`/`verify`/`compile`, the adversarial-brief generator | the docstring claims step-0 recovery and cadence state; the code carries **zero** of the seven tokens in §2 |
| orchestration | opencrabs-dev `hq.md`, Duty 4 at `:137` and Duty 6 at `:184` | Duty-4 intake, the cadence boundary, proposals and decisions, the frozen cycle schema, the full step-0 mechanics | it is a **role card**, not a portable instrument: it binds one factory's session routing, ledger ownership and HQ-only actions |

**Measured starting state** — predicate: the shipped trio and its root pair; scope: this repository;
instant 2026-09-27T14:1xZ:

| path | class (`registry/kit.json`) | bytes | lines | sha256[:12] | root pair |
|---|---|---|---|---|---|
| `TEMPLATE/tools/review.py` | `standalone` | 21 419 | 542 | `5b7f84c4122f` | byte-identical (`cmp` rc=0) |
| `TEMPLATE/tests/test_review.py` | `standalone` | 2 938 | — | `64bd8aad70e7` | byte-identical (`cmp` rc=0) |
| `TEMPLATE/docs/review-lenses.md` | `standalone` | 12 926 | 176 | `e4f1f26b2cbe` | byte-identical (`cmp` rc=0) |

`CATALOG_LENSES` reads **14** lenses over **6** families (`import` of the module, not a count of the
prose).

## 2. Criterion 1 — arrival evidence

Two admissible shapes, and this promotion rests on the second:

- **Independent arrival — NOT claimed.** Five trees carry `tools/review.py` at the identical digest
  `5b7f84c4122f` (`tools/kit_names.py --json`, instant 2026-09-27T14:19Z: `ai-antispam`,
  `inferhub-watch`, `infra-factory`, `meta-factory`, `miidas`). **That is one file delivered five
  times, not five independent constructions** — the four member copies carry mtime 2026-09-27T14:16Z,
  minutes before the census. An identical digest is evidence of a delivery; it is never evidence of
  independent arrival, and reading it as such would be the "same number, different population" error
  this project has already ruled on.
- **One factory demonstrably AHEAD — claimed, and measured.** The donor holds orchestration the
  template does not implement. Predicate: the seven tokens the engine's own docstring presumes;
  scope: `TEMPLATE/tools/review.py`; instant 2026-09-27T14:1xZ — `step0` **0**, `step_0` **0**,
  `cadence` **0**, `boundary_stamp` **0**, `frozen` **0**, `DEFAULT_DIR` **0**, `proposals` **0**.
  The donor's `hq.md` is 334 lines with Duty 4 at `:137` and Duty 6 at `:184`; the engine's docstring
  already names the pair ("Duty 4+6 Review Rotation / P32") while implementing none of it.

## 3. Criterion 2 — naming

**Artifact:** `evidence/reviews/2026-09-27-review-rotation-naming.md` — the four-surface naming
review, one row per surface, each naming the mechanism that READS that surface. No slug is checked
against a hand-written example.

**Outcome:** the working name **Review Rotation** and the kebab slug **`review-rotation`** are
adopted. The kebab form had **0** hits fleet-wide at the census instant; the spaced form already
names the instrument inside the shipped engine's own docstring in five trees.

## 4. Criterion 3 — review, and it is a CLOSE CONDITION

**Artifact:** the code-and-law review lands as a file under `evidence/reviews/`, and this promotion's
close row cites `review=<artifact>`.

**Shape, stated because the row schema is fixed** (F8): a ledger row's fields are exactly
`n/ts/event/actor/subject/detail`, so "carries `review=`" can only mean **a `k=v` token inside
`detail`** — never a column, and never a second trailer on the same row.

**Routed, not settled (F7):** `n=1302` closes `#182` at 2026-09-27T05:19:00Z, after the law landed
(`8b030c4`), and carries no `review=` token — while `n=1217` (2026-09-26T22:34:02Z, the row that WROTE
the criterion) is the ledger's **only** `review=` occurrence. Either `#182` is a bundle completion that
the criterion does not reach, or it is a defective close row under it. **This record does not
adjudicate it**; it is routed to HQ, who owns the ruling.

## 5. Criterion 4 — migration population

| who | what must change | what breaks if they do not |
|---|---|---|
| opencrabs-dev (the donor) | `hq.md` Duties 4/6 become ownership pointers to the promoted instrument | two live implementation contracts for one duty, drifting independently |
| the four member trees already carrying the trio | nothing byte-wise; they declare adoption and create their own reload link | the law ships, the copy is un-reloaded after compaction, and the adoption reads as done |
| this repository | the manifest, the pair, the reload link, the gate set | an instrument not in the manifest is not delivered and not censused |

**The member leg is an adoption step, never installed from here** (frame §6.1): `kit_deliver.py`
copies files and creates no symlinks, so the reload link is the adopter's own act.

## 6. Criterion 5 — second versus replacement

**Both, and the split is stated so neither reading is silently true:**

- **Replacement at the donor** — the donor's embedded duty law is replaced by a pointer to the
  promoted instrument. A promotion that leaves the old contract live has created two homes for one
  thing (frame §5, clause 2).
- **Extension in the template** — the template gains the orchestration half its review record lacks.
  It does **not** replace `review.py`: the engine stays the single review transport.

**No second review transport is created.** A factory that already carries `tools/review.py` receives
the completion of that instrument, not a rival to it.

## 7. Criterion 6 — vocabulary

**Artifact:** `evidence/reviews/2026-09-27-review-rotation-vocabulary.md` — every term the instrument
uses read against `ONTOLOGY.md`, with the two-sense check and the ambiguity defects named.

**Outcome:** five of the instrument's own terms (`Lens`, `Review`, `Cycle`, `Waiver`, `Census`) carry
**0** canonical rows today (predicate: the canonical-terms table's first column, 61 rows, instant
2026-09-27T14:1xZ). Terms that are already canonical (`cadence`, `receipt`, `evidence`, `subagent`)
are **reused and never re-coined** — in particular `cadence`, whose canonical row already means
*actual* against *declared* run frequency, is exactly the concept the donor's boundary stamp measures.

## 8. The scope boundary — reusable mechanics versus donor-only governance

Every donor clause is classified before extraction. **A routed clause is a disposition; a dropped one
is not.**

| donor clause | disposition | why |
|---|---|---|
| lens execution, complete-or-waived census | **KERNEL** | portable: it is the instrument's own contract, and the catalogue already ships |
| cycle init, frozen inputs, step-0 evidence, receipt verification, consolidation, lifecycle states | **KERNEL** | the engine's docstring presumes them and the code has none |
| cadence boundary as an observable artifact | **KERNEL** | portable if it is a declared state, not prose |
| adversarial isolation (review by an isolated subagent) | **ACCEPT — already shipped** | `review-lenses.md:8` states it; `review.py:8` and `:499` implement the brief generator |
| "every accepted finding lands **in its entirety**" — the COMPLETENESS half | **KERNEL, as a duty on the cycle** | a cycle that accepts a finding and lands no home for it is incomplete; that is a property of the review, not of a tool |
| the **NO-GATE** half (fixes land with no design gate, no plan card, no owner approval) | **DONOR LAW / HQ OBLIGATION** | it is scoped to *this* factory's law surface and explicitly excludes owner-gated actions. Shipping it as a tool property would strip a member owner's own design gate — the tool would carry an authority it does not have |
| session routing, ledger ownership, board identifiers, HQ-only actions | **ROUTED** | these belong to the donor's process law; the shipped executable must not carry them |
| donor cycle state (`reviews/<cycle-id>/state.json`) | **ROUTED to a migration policy** | the two schemas differ; historical evidence is migrated by a documented adapter or a frozen legacy reader, never rewritten in place |

**F5 — the fix duty — is ANSWERED** (owner ruling, recorded 2026-09-28T17:24:42Z in the open-questions
register, set `meta-factory`, `q10`; landed in the frame at `32d5662`, §5.2). A promotion review does
**not** inherit Duty 4/6's completeness bar: **a finding is dispositioned, not completed** — a non-fix
is lawful, and its recorded reason must name its **disposition class** (`declared-fork`,
`factory-specific` or `out-of-scope-here`). The narrower reading this section carried is confirmed,
with that class requirement added; the frame's §5.2 is the ruling's home and is cited, never restated.

## 9. Authority split (frame §8, applied)

| who | what |
|---|---|
| Instruments-methodology lane | the frame; review of this instrument's law file (**requirement, not courtesy**) |
| this lane (Review Rotation) | this instrument's implementation, law doc, adoption and donor migration |
| HQ | cross-factory authority: any clause binding a member factory, and the process law about instruments |

## 10. The engine's shape — one engine, no split

Task 6 asked for the engine's responsibilities to be reconciled, with a split **only on a stable
reusable boundary**. Measured this turn, before deciding: the review state has **one** consumer in
this repo. `grep -rl` for a reader of `reviews/*/state.json` or an importer of the engine returns
`tests/test_review.py`, the engine itself, and prose (`docs/review-lenses.md`,
`docs/projects/review-rotation.md`, the demoted legacy verdict). No second program reads the state,
so a state-IO module would have exactly one caller — which is the speculative build **KISS/YAGNI**
forbid, not a boundary. **The engine stays one file**, and the split is deferred until a real second
consumer appears; if one does, the boundary is named here rather than guessed now.

What was reconciled instead, so one catalogue and one lifecycle govern every user:

- **One catalogue.** `CATALOG_LENSES` (14) is the single lens list every leg iterates — `init`,
  `status`, `verify` and `compile` all read it rather than carrying their own copy.
- **The step-0 claim became a mechanism.** The docstring had claimed since promotion that
  `state.json` IS the step-0 recovery point, while the code had **zero** hits for `step0`: a claim
  in a paragraph a compacted session cannot execute. `step0 <cycle>` now reads state and nothing
  else, and `--record` appends to `step0_log` — durable evidence rather than an assertion.
- **No silent live read.** A terminal lifecycle FREEZES the cycle and snapshots its declared
  channels (`inputs_snapshot`, digests streamed in constant memory). `intake` and `cadence --write`
  are REFUSED against a frozen cycle; `--live` is the deliberate override and says so on stderr.

## 11. Findings and questions carried by this record

**Resolved since the promotion:**

1. **F5 — the fix duty** — **ANSWERED** (owner ruling, `q10`, answered 2026-09-28; §8 above — the frame
   §5.2 is the ruling's home): a promotion finding is **dispositioned, not completed**, and a non-fix
   names its disposition class.

**Still open:**

1. **The instrument NAME** — **Review Rotation** is a working name, collision-checked. A rename is
   cheap now (no slug is published, no member has adopted a law file) and expensive after step 9.

## 12. Provenance

- Promotion plan: this lane's own session plan; the tasking design is the methodology lane's and is
  **not** cited by path anywhere in this record or in the instrument's artifacts.
- Every figure in this file was re-derived in the same turn it was published, from the artifact it
  describes, and carries its predicate, its scope and its instant.
