# Ledger adoption by the member factories — census and lessons

**Asked by:** the owner, 2026-09-25 13:39Z (Factories / Delegate topic), in the context of the
instrument-adoption plan — *"when the instruments are adopted from a member factory into the
template … Include ledger and questions reviews into the plan … ask the delegate lane for lessons
from ledger adoption by the member factories and see if this plan needs to be corrected."*

**Measured:** 2026-09-25 ~13:45Z, first-hand on the agents box.
**Reference:** `TEMPLATE/tools/ledger.py` = 67 382 B, sha256 `b6b5e4abf087…` — which **matches**
its `registry/kit.json` manifest entry, so the reference is the shipped tree and not a stale copy.

---

## 1. The census

| Factory | `evidence/ledger.jsonl` | `tools/ledger.py` | vs shipped | verbs exposed | `ledger_declaration.py` |
|---|---|---|---|---|---|
| *(shipped)* | — | 67 382 B | — | append tail verify **repair** | 7 439 B |
| meta-factory | 1 082 rows | 67 382 B | **SAME** | append tail verify repair | present |
| inferhub-watch | 468 rows | 61 063 B | DIFF — 90.6 % | append tail verify repair | 5 685 B (DIFF) |
| vds-servers | 426 rows | 14 055 B | DIFF — 20.9 % | append tail verify | **ABSENT** |
| miidas | 101 rows | 13 178 B | DIFF — 19.6 % | append tail verify | **ABSENT** |
| ai-antispam | 34 rows | 12 438 B | DIFF — 18.5 % | append tail verify | **ABSENT** |
| opencrabs-dev | **none** | **none** | — | — | — |

Ledger **gate** files carried, of the six the kit ships
(`test_ledger.py`, `_schema`, `_no_shrink`, `_identity`, `_close_preflight`, `_commit_cites_no_rows`):

| Factory | carried |
|---|---|
| ai-antispam | 2 / 6 — `test_ledger.py`, `test_ledger_schema.py` |
| miidas | 2 / 6 — same two |
| vds-servers | 1 / 6 — `test_ledger.py` |
| inferhub-watch | **0 / 6** |
| opencrabs-dev | none — no `tests/` directory in either tree |

Two further predicates, both measured:

- **`verified_rows`** (the settlement receipt, retired the author's `rows=` prediction, landed
  2026-09-25) — present in the **shipped** copy and in **no** member copy.
- **The questions instrument:** `registry/kit.json` carries **no** entry matching `question`,
  `TEMPLATE/tools/` has no questions tool, and **no member repo carries one**. The only copy in
  the fleet is the opencrabs-dev **skill repo**: `tools/oc-questions` (166 032 B) +
  `tools/oc-questions-render.mjs`.

---

## 2. Lessons

**L1 — Adoption is a one-time copy with no update path, and the spread is 5×.**
Four of five members DIFF from the shipped tool; three run copies at 18–21 % of its size. The
tool carries no version, so nothing tells a member its copy is old — and nothing measured this
until `registry/kit.json` landed **today 11:58**, with the patrol's kit-drift leg at **12:11**.
The drift is real and long-standing; the *instrument* to see it is hours old.

**L2 — The tool ships; the GATES do not. A partial copy is worse than none, because it reads as
adopted.** Six kit ledger gates exist; members carry 2 / 2 / 1 / 0. So `test_ledger_no_shrink`,
`test_ledger_identity`, `test_ledger_close_preflight` and `test_ledger_commit_cites_no_rows` are
unenforced in four factories — the ledger *runs*, the law does not bite, and the factory's own
audit reports green over it. This is the single largest correction the plan needs.

**L3 — The newest file is the most absent, and it is the one that makes the law enforceable.**
`ledger_declaration.py` exists because #157 found the actor matrix living *inside a paired test
file*, so the writer could not see it and an unauthorized row was written silently. The fix moved
the predicate to a shared module and had `cmd_append` refuse. That module is **absent in three of
four** members — so exactly the factories on the oldest copies have the silent-write gap the fix
was written to close.

**L4 — Stale is measured in FEATURES, not bytes.** Three members (ai-antispam, vds-servers,
miidas) expose `append tail verify` and **no `repair` verb**. §11's own remedy — *"a repair must
not terminate the canonical run"*, with `ledger.py repair` inserting text before the trailer — is
therefore **unavailable** to them. Their law prescribes a repair path their tool does not have.

**L5 — "Adopted" is not binary: a member can carry the vocabulary without the artefact.**
opencrabs-dev has no `evidence/ledger.jsonl` and no `tools/ledger.py`; its ledger is
`workers-ledger.json` — 3 950 670 B, a skill-version acknowledgement dict, a different object with
a different identity model. A plan that assumes "members run the ledger" is wrong for the factory
that most needs one.

**L6 — A bootstrap step is not a delivery mechanism.** Three separate entry-path blockers, all
measured today: **#155** — `BOOTSTRAP.md` Step 4c names 2 of the 7 files its own gate needs, and
followed literally it dies `ModuleNotFoundError: No module named 'audit'`; **#164** — the template
tree ships a **RED** `test_ledger_schema.py` (an absent ledger reported as a VIOLATION) that no
bootstrap step can clear; **#162** — the gate resolves `REPO = parent.parent` with no override, so
a split-repo factory (state repo with `evidence/`, skill repo with `tools/`) cannot run it in
either tree. A new instrument delivered by a doc step inherits all three.

**L7 — Renaming is the easy half; identity is the hard half.** For the **ledger**, there is no
member-factory instrument to adopt *into* the template: the members carry stale copies of the
template's own tool. The only genuinely different ledger in the fleet is opencrabs-dev's
`oc-ledger` (262 KB, `workers-ledger.json`, ~22 kinds, no `n` ordinal). The yylo spike already
measured what a vocabulary swap costs — *"different storage, vocabulary and identity model; 44
readers and 50 gates cannot consume it unchanged."* So the ledger review is a decision between a
**second** ledger (two identity models — the multi-board collision class already ruled a defect)
and a **migration** (44 readers + 50 gates).

**L8 — For questions there is no member instrument to adopt either.** TEMPLATE ships none, no
member carries one, and the only copy is the dev skill repo's `oc-questions`. The questions half
of the plan is a **new-instrument landing** (needs a template home, a version, a test), not an
adoption from a member — a different review with a different close condition.

---

## 3. What the plan should carry

1. **Define "the instrument" as its full file set — tool + shared modules + its gate set — and make
   completeness a close condition.** The measured failure mode is a partial copy that reads as
   adopted (L2, L3).
2. **Ride the existing kit-drift leg** (`registry/kit.json`, 106 files, per-file sha256; the
   patrol's kit-drift leg, population five other repos, same/DIFF/ABSENT with names) rather than
   building a second adoption measurement. **Publish a census artifact** — none exists today, so
   "adoption" currently has no report to correct a plan against.
3. **Fix the entry path before adopting anything new** (#155, #164, #162). A new instrument
   delivered by a doc step inherits all three blockers.
4. **For each candidate, state second-vs-replacement and name the migration population**
   (readers, gates, identity model). Renaming is orthogonal to both.
5. **Check the member actually carries the object before calling it adoption** (L5).

---

## 4. Bounds — what this census does not say

- **DIFF is measured; *behind* vs *forked* is inferred** from the verb set and markers, not from a
  full content diff. The verb evidence is decisive for the three 3-verb copies; the exact number
  of releases behind is not established.
- Size is not staleness on its own: inferhub-watch is 90.6 % of the shipped tool and is the only
  member with the shared declaration module.
- The kit-drift leg was **not run** for this census; the per-file comparison here was computed
  directly against the manifest. No kit-drift report artifact exists yet.
- Members' `evidence/ledger.jsonl` row counts are as read at ~13:45Z and move with their activity.
