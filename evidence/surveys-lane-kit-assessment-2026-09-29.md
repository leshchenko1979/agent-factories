# Should the Surveys lane be adopted to the kit? — assessment

**Lane:** Instruments methodology · **Instant:** 2026-09-29T07:5xZ · **Subject:** the Surveys lane's
machinery and procedure against the frame's promotion criteria
(`TEMPLATE/docs/instruments/template-instruments.md` §5.1).

---

## Verdict

**Split it. Promote the Tier-1 half; declare the Tier-2 half home-factory-only.**

The instrument is **not one object** — its own text declares a two-tier architecture, and the two
tiers have opposite answers to "does a member need this?".

| Tier | Whose work it is | Answer |
|---|---|---|
| **Tier 1 — Internal Self-Audit** (§5 step 1) | *"Each factory runs its own internal self-audit using `tools/audit.py`"* | **Promote** — member-facing by the doc's own words |
| **Tier 2 — Meta-Audit of Member Factories** (§5 step 2, §4, §6–§9) | *"By Surveys Lane"* — scores, cadence integrity, calibration spot-check, consulting advisory | **Home-factory-only** — a member has no fleet to survey |

Promoting the procedure wholesale would ship a **role a member does not hold**. Promoting nothing
leaves the real gap open: a member has the instrument and not the law that says what to measure.

---

## The tooling is ALREADY adopted — criterion 1 is satisfied and needs no promotion

The tools the procedure names are manifest entries and have **independent arrival evidence**:

| Tool | Manifest class | Member trees carrying it (predicate: file exists in the member's declared `/repo`, scope: the 5 members, instant 2026-09-29T07:5xZ) |
|---|---|---|
| `tools/audit.py` | `standalone` | **4 of 5** — vds-servers, ai-antispam, miidas, inferhub-watch |
| `tools/hygiene.py` | `standalone` | **4 of 6** — the same four + the meta-factory |
| `tools/ledger.py` | `standalone` | 3 — vds-servers, miidas, meta-factory |
| `tools/brain_metrics.py` | `standalone` | 2 — ai-antispam, meta-factory |
| `tools/patrol_host_state.py` | `standalone` | meta-factory (a box-level instrument) |

**Presence is not provenance, so I measured the builds.** The count above is a presence reading; the
divergence below decides what it means:

| Tool | Builds found (md5[:12]) | Reading |
|---|---|---|
| `audit.py` | vds-servers `031a51ac03c8` 484 L · ai-antispam `40482eb1f60c` 786 L · miidas `342c815699c2` 1028 L · inferhub-watch `13d1ed7e86f3` 614 L · **shipped `cb3a561232f3` 2572 L** | **five distinct builds** — the members' are independently built and *smaller*; none is the shipped one |
| `hygiene.py` | vds-servers `8d25895c64` 428 L · miidas `e288f28a2c` 337 L · **ai-antispam `07b9cc4ac8` 444 L** · **shipped `07b9cc4ac8` 444 L** | ai-antispam holds **exactly the shipped build**; two others diverge |

So the two tools give **opposite** answers, and each is a named migration population:

- **`hygiene.py` — one member is already in the promoted shape.** ai-antispam's copy is
  byte-identical to `TEMPLATE/tools/hygiene.py`. Its migration is **declaration, not a content
  move** — the same finding the questions instrument produced (§1.3's vendored state, not
  independent construction).
- **`audit.py` — four divergent doubles.** Every member build differs from the shipped one and from
  each other. Under **§9 O1** each must **dispose**: migrate, declare the fork with its reason, or
  defer with a stated re-entry condition. Silence is not a disposition.

The tooling therefore needs no *promotion* (it already ships), but `audit.py` owes a **named
migration population** — and the divergence is large enough that "migrate" would be a rewrite for
three of the four, which is exactly the case O1's declare-or-defer arms exist for.

---

## What is genuinely missing — the Tier-1 law, not the Tier-1 tool

Tier 1's procedure depends on two documents, and **neither ships**:

| Doc | In manifest | Root-side |
|---|---|---|
| `docs/measurement-procedure.md` (§5 = the Tier-1 steps) | **ABSENT** | exists |
| `docs/quality-criteria.md` (the 19 criteria across 6 families that §5 step 3 scores against) | **ABSENT** | exists |

Measured: **0 of 4** member trees carry any self-audit procedure or quality-criteria rubric.
So a member today holds `tools/audit.py`, runs it, gets a verdict — and has no shipped statement of
*which measures to derive* (first-pass yield, rework rate, lead time), *how to record the tree it
read* (#150's `tree.head_sha` discipline), or *what rubric to score against*.

**That is the defect worth closing.** It is the same shape as §2's part 5 — *"the step that installs
the ledger names a subset of what it installs"* — one level up: the tool ships and the law that
governs its output does not.

---

## Two named tools that do not ship, undeclared at the naming site

`docs/measurement-procedure.md` names **7 tools**; two are absent from the manifest:

| Named tool | Manifest |
|---|---|
| `compaction_rate.py` | **ABSENT** |
| `insights.py` | **ABSENT** |

Both are consistent with the procedure being meta-factory-only — `insights.md` already carries the
§6.3 home-factory-only class. But **nothing at the naming site says so**, so a reader of the
procedure cannot tell a deliberately-unshipped tool from a missing one. Same class as the M2
findings: a path named with no shipping statement beside it.

---

## Defects found while measuring

1. **Duplicate section number `## 6.`** — `:501` *"Cognitive Bounds & Survey Resolution Ratio"* and
   `:546` *"What One Run Must NOT Do"*. Two sections, one number, so `§6` resolves to neither
   reliably. Same class as the numbering collision corrected in the frame (2026-09-27).
2. **No reload leg.** `skills/meta-factory/` carries `SKILL.md` plus **7** instrument links — and no
   link for `measurement-procedure.md`. The only pointer is `SKILL.md:236`. Under §6.3 a
   home-factory-only law doc **still owes its reload leg**: the pair is waived, the leg is not.
3. **The non-shipping is stated only in test comments** — `test_score_artifact_sections.py:642`
   (*"which the template does not ship"*) and `test_citation_clause_titles.py:139`'s
   `PROBE_CARRIED` set. A law reader does not meet either.

---

## Recommendation

| # | Action | Owner |
|---|---|---|
| 1 | **Split `measurement-procedure.md`**: the Tier-1 sections become a shipped member-facing procedure, with `quality-criteria.md`; the Tier-2 sections (§4, §6–§9, and Tier 2's steps) become a home-factory-only doc | meta-factory (HQ) |
| 2 | **Declare the meta-only half** under §6.3 — a stated reason in the doc, and a reload leg `skills/meta-factory/measurement-procedure.md -> ../../docs/measurement-procedure.md` | meta-factory (HQ) |
| 3 | **Mark the two unshipped named tools** at the naming site as meta-factory-only with their reason | meta-factory (HQ) |
| 4 | **Fix the duplicate `## 6.`** | meta-factory (HQ) |
| 5 | **File the Tier-1 promotion** against §5.1 — it needs arrival evidence (satisfied: `audit.py` 4/5), a naming review, a subagent review, a migration population, second-vs-replacement, vocabulary | Instruments methodology (this lane) |

**Sequencing:** #4 and #3 are one-line repairs and can land first. #1–#2 are the substantive split.
#5 is a promotion in its own right and owes the full §5.1 set — it should not be started until the
split exists, or it promotes a document half of which is not for members.

---

## Bound on this assessment

Everything above is read from the artifacts (the manifest, the two docs, the five member trees, the
skill directory, and each `audit.py`/`hygiene.py` build's md5). **Not measured:** whether any member
*wants* the Tier-1 procedure. That is the one input that would change the emphasis — not the split,
which follows from the document's own two-tier text.
