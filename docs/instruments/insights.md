# Insights register — the instrument's law

Writer: Insights lane — authors this file.
Frame: `docs/instruments/template-instruments.md` — cross-instrument definitions are cited from there, never restated here.
Authority: cross-factory clauses, and process law about instruments, rest with meta-factory HQ.

**Owns:** this instrument — the record's semantics (`author`, `class`, `status`), its writer, its gate set, and this file. It exists because `author`, `class` and `status` were added to the register with no law home anywhere: their meaning lived only in a docstring and three test files, which is why a cross-instrument identity disagreement (#216: the register naming a lane `Factories / Insights` while the ledger named the same lane `insights`) could not be settled from any artifact.

## 1. The instrument, declared

Frame §1 fixes the declaration form: **an instrument is a DECLARED object**, declared by its own law file in six fields. Populated here, so a reader holding only this file and a tree can answer *"is this instrument complete here?"* without enumerating imports:

| field (frame §1) | this instrument |
|---|---|
| **name** | Insights register |
| **executable(s)** | `tools/insights.py` — verbs `append` · `list` · `verify` · `format` · `classify` · `status` · `reason`. One writer, seven verbs (§6, §7) |
| **closure** | **none** — the CLI imports only the standard library, and its one repo-relative constant is the store it writes. There is no asset that must sit beside the binary (contrast `open-questions.md` §1, whose render asset is a closure member) |
| **gate set** | the instrument's own suite, all root-local: `tests/test_insights_author.py` · `tests/test_insights_class.py` · `tests/test_insights_status.py`, plus the ledger-invariant gate `tests/test_insights_gate_recorded.py` — it judges this artifact's closing verdict and belongs to a shared family (`test_close_row_revision.py`, `test_score_gate_recorded.py`), and it is factory-local since 2026-09-28 (§2) |
| **version source** | **none** — the instrument is not a kit member, so it carries no manifest hash and owes no version (§2) |
| **data surfaces** | `evidence/insights.jsonl` — factory-owned, in-repo, append-only (§3). No external store, so no member owes a migration |

---

## 2. The declared file set

**Predicate:** the shipped paths the kit manifest classifies that carry this instrument. **Scope:** `registry/kit.json`, whose population is the `TEMPLATE/` half; a member adopts the root half.

**No path in this instrument ships — the declared set is empty.**

This is the owner's order of 2026-09-28: *"this insights tool should not be a part of the kit — it's the meta factory's subject matter only."* It was one path until then, and this section is where that decision lives.

The class is **home-factory-only** (frame §6.3), and the reason is not an omission: a new factory bootstraps from `TEMPLATE/`, and a new factory has no insights register to govern. The template's own doctrine already said so — `TEMPLATE/docs/addons/domain/stories.md` classes `tools/insights.py` and `evidence/insights.jsonl` as **"the factory creates it"**, because *"a ledger of discoveries a factory never made is a file of another factory's history"*. The shipped ledger-invariant gate contradicted that doctrine: it governed `evidence/insights.jsonl`, which never shipped, so a member inherited a boundary parameter with no artifact to apply.

Everything in the instrument is therefore **factory-local** and in no kit manifest:

| path | kind | what it is |
|---|---|---|
| `tools/insights.py` | tool | the writer (§6) |
| `tools/synthesize_insights.py` | tool | the weekly **proposer** — it prints JSON and has no write path to the store (§7) |
| `tests/test_insights_author.py` · `tests/test_insights_class.py` · `tests/test_insights_status.py` | gates | the three axes' gates |
| `tests/test_insights_gate_recorded.py` | gate | the ledger-invariant gate — the closing workspace-gate verdict for this artifact, sibling to `test_close_row_revision.py` and `test_score_gate_recorded.py`, sharing ONE boundary reader (`tests/ledger_boundary.py`). Factory-local by the order above; registered in this factory's audit behind a presence guard |
| `tests/test_synthesize_insights.py` | gate | the proposer's gate |
| `evidence/insights.jsonl` | data | the store |

**The census REFUSES for this instrument, and that is a declared state rather than a malformed table.** `tools/instrument_census.py` measures member *adoption* of a declared set, and an empty set has no adoption to measure: the parser returns no `↔` rows and the census refuses by design (`test_instrument_census.py` arm 6 — a zero parsed declared set is a refusal, never a clean census). The published census for this instrument is therefore a **refusal artifact**, not a table: `evidence/instrument-census-insights-2026-09-28-refused.md`, recorded at `2026-09-28T20:53Z` when the set emptied — it supersedes `evidence/instrument-census-insights-2026-09-28.md`, whose `1 path(s)` reading was correct at `18:43:13Z`, before the order. Run `instrument_census.py insights` and expect `rc=1` with that refusal named by path. The reload link (frame §6.3) is unaffected and still carries this doc across a compaction.

**Consequence, stated so a reader does not derive it wrongly:** a future decision to ship any part of this instrument changes this section FIRST — and moves the path concerned into `registry/kit.json`, a `TEMPLATE/` half, a `PAIRS` entry and `REQUIRED_GATES`/`OPTIONAL_GATES` together, since a half-shipped instrument is the state this section now rules out.

---

## 3. The record

One JSON object per line, append-only. A row is one insight, and it carries three separable things — never conflate them:

| group | fields | what it asserts |
|---|---|---|
| **identity** | `n` · `id` · `ts` · `topic` · `stage` | which record this is, when, and what it is called |
| **the claim** | `naive_assumption` · `empirical_reality` · `mechanism` | what was assumed, what was measured, and why they differ |
| **routing** | `author` · `class` · `status` (+ `status_at` · `reason`) | who wrote it, what it requires of its reader, and where it stands |
| **revision** | `supersedes` | present only on a row that corrects an earlier one — the `n` it names |
| **publication seed** | `tweet_hook` · `ru_summary` | material for the content funnel (`ru_summary` is REQUIRED at the append) |

`n` is the store's own ordinal and `id` is the stable slug; both are cited elsewhere, so neither is ever reassigned. A stored claim is never restated to make room for a new field, which is the property §6's backfill verbs are built around.

**A correction is a SUPERSEDING ROW, and the reader takes the NEWEST.** The claims are append-only by construction, so a correction is not an edit: it is a **new row naming the row it corrects** — `supersedes: <n>` — carrying the corrected value. Two requirements travel with it, and neither is optional:

1. **The newest governing row decides.** `supersedes` names an **earlier** row whose `id` it shares, so "newest" is decidable rather than inferred; `verify` refuses a marker that names a later row, a missing row, a row of a different `id`, or a row that already has a successor. One row has **one** successor, or *"the newest governs"* stops resolving.
2. **The supersession PRINTS.** `list` marks both ends — `[revises n=N]` on the successor, `[superseded by n=N]` on the row it governs — and `format` states it in the body. Never silence: a reader meets *"superseded by n=N"* rather than only a value, so a stale figure cannot be read as the current one.

`verify` also refuses a second row for an existing `id` that carries **no** `supersedes`: a duplicate and a revision are different records, and left unmarked the duplicate would leave *"the newest governs"* with nothing to resolve against. The `n`-integer marker is this store's own expression of *"names the row it corrects"* — the ledger's typed `refs` are the same shape stated for a different surface, and this file does not need that machinery, because an insight row's only correction target is another insight row.

---

## 4. `author` — who wrote it

**The value is the lane's ROLE, not its chat-prefixed topic** — `insights`, not `Factories / Insights`.

This is the one definition in this file that is not a free choice, and the reason is a join: `tools/ledger.py::session_to_role()` derives a lane's ledger actor from the fragment's `role` field, so a register row authored `Factories / Insights` **cannot be joined** to the ledger row for the same work. The role is canonical for one further reason: it is the only value both legs can produce. The title-fallback leg can never reproduce a curated role (`Open Question Tool` → `open-question-tool` ≠ `questions`), so aligning the other way is impossible rather than merely undesirable.

- **Explicit** whenever the writing lane passes one.
- **Derived** from the writing session when omitted — the fragment leg first, the binding title as fallback.
- **REFUSED when it resolves to nothing.** Never defaulted: a guessed author reads as provenance and there is no way for a later reader to tell it from a measured one.
- **Legacy rows carry no key and stay valid.** The 31 rows written before this field existed are not backfilled — a date-of-record written today for a row that predates the field would be a falsified record, not a repair. `list` and `format` print `[legacy]`.

---

## 5. `class` — what the claim requires of its reader

Two values, and the test is stated rather than left to judgement:

**Does the claim hold for a reader who has never heard of agent-factories?**

- **`general`** — yes. It survives without our internal machinery, so it travels beyond this factory. **It does NOT follow that it is publishable.** The first live use of this axis sent 14 `general` claims to the content funnel and **8 came back `dropped`** — gate-independence is *necessary* for publication and not *sufficient* for it.
- **`implementation`** — no; it is only intelligible once you know our gates, ledgers or processes. It is a technical finding for a narrower audience, and its consumer is HQ (§8).

Both bullets answer *what the claim requires of its reader*. Neither answers *who will want to read it*, and the 2026-09-28 measurement is the proof: of 14 `general` claims the funnel took 5 and dropped 8 — four because one finding appeared in four spellings, three because they were specifications rather than outcomes, and one because it partly duplicated an already-published post. **Class is not an audience axis**, and reading it as one is the error this paragraph exists to block.

**Class is REQUIRED at the append**, and rightly so: the class is a property of the claim itself, and the author is the one who knows it. A default would be this file inventing a routing decision the author was in a position to make.

**A misspelled class is REFUSED, not defaulted** — an unknown value passes any "is it set?" check while reaching no consumer, which is the failure mode the argument-choices check exists to prevent.

---

## 6. `status` — where it stands in the workflow

`status` is **orthogonal to `class`**. `class` says *what the claim requires of its reader*; `status` says *what has been DONE about it*. They divide the same population differently, and neither derives from the other — a `general` claim can be `pending` just as an `implementation` claim can be `dropped`.

| status | meaning |
|---|---|
| `pending` | recorded, destination not yet ruled on — **the append default** |
| `publishing` | earmarked for the content funnel (§8) |
| `hq` | earmarked for HQ as an internal amendment (§8) |
| `refused` | **waiting** — a consumer refused it, the refusal's grounds are in `reason`, and the insight now waits on the OWNER (§6 rule 6) |
| `published` | **terminal** — the unit went out |
| `landed` | **terminal** — HQ changed a process |
| `dropped` | **terminal** — deliberately not acted on, with the reason in `reason` |

Six rules, each of which has a way of going wrong that this file closes:

1. **A fresh row opens `pending`, and `status` is NOT required at the append.** A destination is a *routing* decision, not a property of the claim, so a new row asserts only its own state rather than guessing someone else's decision. If the two axes were coupled at the append, the register would record an intent nobody formed.
2. **`status_at` travels with `status`.** Without the instant, *"what has been sitting in `hq` for a fortnight?"* — the question the field exists to answer — is unanswerable.
3. **Terminal states are recorded when they happen, never forecast.** `published` and `landed` are outcomes; a row that asserted one on expectation would be a prediction wearing a record's clothes.
4. **A status that owes a reason requires one, and the rule is MECHANICALLY ENFORCED.** Silence and refusal are different records, and only one of them is checkable later — so the requirement is not left to the law's own reader. Two statuses owe a reason — **`refused` and `dropped`** — and they are held in ONE place (`REASON_REQUIRED_STATUSES`), read by all four enforcement points, so the write path and the reader cannot drift apart on which statuses owe one. The **write path REFUSES** a row left reason-owing with no `reason` (the append, and every backfill that sets the status), and `verify` **REPORTS** a stored row that carries none. A law whose only enforcer is whoever reads it is the shape this rule was written to close: the clause and its check land together, or the clause is decoration. Setting the status and setting the reason are one act — `status {"<id>": {"status": "refused", "reason": "…"}}` — so there is no window in which such a row exists without one. **Both directions are refused**: a reason on a row in neither state is the field's other lie.
5. **`reason` is prose, not a vocabulary.** It is a **settable field** (`classify` · `status` · `reason`) and never a `FIELD_VOCAB` member, because the vocabulary is closed and a reason's whole value is saying the specific thing that was decided. A `reason` on a row that owes none is the field's other lie — it reads as a refusal where none was recorded — and `verify` refuses it. **The overturn clears it**: when the owner overturns a refusal, the status moves and the reason is *removed*, because a reason left standing beside a non-owing status is a reader trap — it says the row was refused while the status says it is moving. This is the one non-additive edit a backfill may make, it is **declared** rather than silent, and it is reported by name.
6. **A refusal is NOT terminal: it directs the insight to the OWNER for gating.** `refused` means a *consumer* — for a `general` claim, the content funnel — declined the unit, and recorded its grounds. It is emphatically **not** `dropped`: `dropped` records a decision the owner made, and a consumer's refusal recorded as the owner's decision puts a judgement in his mouth that he never formed. So the refusal **waits on the owner**, who settles it one way or the other:

   - **uphold the refusal** → `dropped`, with the refusal's grounds kept as the reason (the consumer's words, not a re-typed paraphrase)
   - **overturn** → the row returns to the workflow (`publishing` for a `general` claim) and its `reason` is cleared by §6 rule 5

   The vehicle is the **open questions register** (`docs/instruments/open-questions.md`), one question carrying every refused row with its grounds, defaulting to *uphold* — so the owner marks only what he would overturn rather than voting on each. A refusal that never reaches him is the same defect class as #216 and #227, one surface over: a rule whose only carrier is whoever happened to see it. This is where the owner keeps the last word without becoming the classifier.

---

## 7. The writer

- **`tools/insights.py` is the ONE writer.** Every write verb it exposes is the SAME writer; there is no second path by construction rather than by good intentions.
- **The weekly proposer does not write.** `tools/synthesize_insights.py` prints JSON and has **no** write path to the store — `INSIGHTS_PATH` is only ever read, and the `insights` it builds is a local list. A lane does the appending. This matters twice over: the register has one writer, and adding a required field cannot break the weekly cron, because the proposer never appends.
- **`classify`, `status` and `reason` are BACKFILLS over one shared mechanism**, and their safety property is asserted rather than asserted-to-be-true: strip the keys they add and the store is **byte-identical** to its previous revision. A backfill adds a label; it never restates a claim. `reason` is a settable field rather than a vocabulary member (§6 rule 5), and it is its own verb because a backfilled reason must not re-date the row: `status` moves `status_at`, while `reason` sets the prose and nothing else, so an unset field filled in later cannot silently move the instant that field's sibling exists to record.
- **All-or-nothing.** One unknown `id` writes nothing.
- **Refusal is loud.** An unspecified or unrecognised verb exits non-zero rather than reporting success.

---

## 8. `verify`, and what each axis feeds

`verify` is the store's own precondition: it rejects a stored **blank** or **unknown** value on any axis, while **accepting an absent key** on a legacy row — the distinction between *unrecorded* and *recorded as empty* is the whole point. `list` and `format` print `[legacy]` for a row that predates a field, so "not recorded" can never be read as a category. Three further refusal classes ride the same reader, each one a rule §3 or §6 states and this section enforces: a row left reason-owing (`refused` or `dropped`) with no `reason` (§6 rule 4), a `reason` recorded on a row that owes none (§6 rule 5), and a broken **supersession** chain — a marker naming a later, missing, differently-`id`d or already-superseded row (§3).

The two classes feed two different consumers, and both are DECLARED:

| class | derived output | consumer |
|---|---|---|
| `general` | publishable content units (site, Telegram channel, X) | the miidas content funnel — Marketing drafts under `CONTENT-FUNNEL.md` §6, and the **owner approves final copy** under §5 |
| `implementation` | factory improvement ideas and process amendments | **HQ**, worked **one item at a time**, with this register's own `status` axis as the tracker — `hq` → `landed` or `dropped` |

**No second artifact.** The register is the single source for both derivatives; a brief, a summary or a queue minted beside it is the drift class this factory keeps measuring. HQ's ruling of 2026-09-28 states the intake shape: the pointer is the register, the cadence is per-item rather than batched, and the tracker is the `status` axis that already exists — never a parallel one.

---

## 9. Intake — what happens when an insight arrives

**One arrival, three outputs, in one turn — and they land in the ROW, not only in the reply.** An insight posted into the Insights topic — the owner's or a lane's — is handled in the turn it arrives, and that turn owes **all three**. A record without its research and its mapping is an intake that stopped halfway. The owner ordered this shape on 2026-09-28; that it reached no artifact until #227 is the same defect class as #216 — a binding rule whose only carrier was a conversation.

That defect sat one surface further in on 2026-09-29, and this section is where it was closed: measured at the row for `n=32`, **1 of 10** research findings — 1 of 5 cited sources and 0 of 5 mapping clause names — had reached the register, because this clause required the research to be *presented* and said nothing about where it was *kept*. A reply is a context-time object, which is precisely the thing rung 1 of that same insight externalises. So each of the three outputs is required to **land in the row**, where a later lane reaches it after a compaction, and not merely where the turn that produced it could see it.

1. **RECORD.** One `append`, carrying its `author` (§4) and its `class` (§5). The owner's insights carry `author: Alexey`. `class` is the authoring lane's call, derived by §5's test — of what the claim requires of its reader — never by the submitter's sense of audience.
2. **RESEARCH.** Search external best practice on the problem the insight discusses, and present it with **its sources and their dates**, stating of each whether it **agrees with**, **sharpens**, or **contradicts** the insight. **Every source lands in the row, cited by id and date, in the field it evidences** — `n=32` is the pattern rather than an exception: its `empirical_reality` carries *arXiv:2606.22953* with the figures it contributes (4.1×, 34.7 pp, 56.7% → 22.0%), so the evidence is readable from the store alone. A source that reached only the reply is one the register cannot show, and the finding dies with the turn that found it. `No practice found` is a **declared finding**, never silence: the search is itself evidence, an empty result is still a result, **and the row records it as one**.
3. **MAP.** State what the insight would change, in **which** factories, and **where it does not apply**. **The mapping lands in the row too** — where the insight is **already codified**, the **clause names** it points at are recorded in the row, so *"already codified"* is checkable by a later reader rather than recalled by whoever held the turn. The mapping is a dedupe as much as a translation: an insight the fleet **already codifies** is answered by **pointing at the clause**, and is settled `landed` with that clause as its reason rather than re-filed — the already-codified arm of the sort §8's `implementation` consumer works one item at a time.

**The bound.** Intake is a judgement about content, and it builds **no gate**: no offline predicate reads whether a mapping is honest or a cited practice real, and this clause adds none. *Requiring a finding to be stored is not requiring it to be true* — that is why `verify` reads the axes and never the prose, and why the difference between the two is stated here rather than left to be assumed. What upholds the workflow is the authoring lane performing it **and the finding reaching the row**; the reload leg exists so that this clause itself survives a compaction, which is the same argument one level up.

---

## 10. Rollout

- **Declared executor: meta-factory.** Not a kit member (§2), so nothing is owed to a member and no version bump attends a change here.
- **A change to this file's meaning owes the three axis gates**, which is why they exist: `test_insights_author.py`, `test_insights_class.py`, `test_insights_status.py`. Each drives the CLI, and the author gate additionally drives **both** instruments (§4) and asserts one string, so the register and the ledger cannot drift apart on a lane's identity again without a red.
- **The store is the record, and this file defines it — not the reverse.** Where they disagree, one of the two is wrong and the disagreement is a defect to file, never a reading to reconcile by hand.
