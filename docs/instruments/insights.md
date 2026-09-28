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
| **executable(s)** | `tools/insights.py` — verbs `append` · `list` · `verify` · `format` · `classify` · `status`. One writer, six verbs (§6) |
| **closure** | **none** — the CLI imports only the standard library, and its one repo-relative constant is the store it writes. There is no asset that must sit beside the binary (contrast `open-questions.md` §1, whose render asset is a closure member) |
| **gate set** | the instrument's own suite, root-local: `tests/test_insights_author.py` · `tests/test_insights_class.py` · `tests/test_insights_status.py`. Plus the shipped ledger-invariant gate `tests/test_insights_gate_recorded.py`, which judges this artifact's closing verdict and belongs to a shared family, not to this tool (§2) |
| **version source** | **none** — the instrument is not a kit member, so it carries no manifest hash and owes no version (§2) |
| **data surfaces** | `evidence/insights.jsonl` — factory-owned, in-repo, append-only (§3). No external store, so no member owes a migration |

---

## 2. The declared file set

**Predicate:** the shipped paths the kit manifest classifies `standalone` that carry this instrument. **Scope:** `registry/kit.json`, whose population is the `TEMPLATE/` half; the member adopts the root half.

Exactly **one** path in this instrument ships:

| # | path (root half ↔ TEMPLATE half) | class | what it is |
|---|---|---|---|
| 1 | `tests/test_insights_gate_recorded.py` ↔ `TEMPLATE/tests/test_insights_gate_recorded.py` | `standalone` | the **ledger-invariant gate** — the closing workspace-gate verdict for this artifact, sibling to `test_close_row_revision.py` and `test_score_gate_recorded.py`, sharing ONE boundary reader (`tests/ledger_boundary.py`). It ships because it is parameterised by the factory's own `docs/ledger-invariants.json`; a factory whose pacemaker is named differently finds no governed row and SKIPS with its reason |

It ships alone, and that asymmetry is deliberate rather than an omission: the *rule* it enforces (an artifact's run records its closing verdict) is cross-factory, while the tool and the store it judges are this factory's own.

Everything else in the instrument is **factory-local** and is NOT in the kit. Listed here for completeness, in a shape this file's census reader does not parse — **no member adopts these, so they are not a declared set**:

| path | kind | what it is |
|---|---|---|
| `tools/insights.py` | tool | the writer (§6) |
| `tools/synthesize_insights.py` | tool | the weekly **proposer** — it prints JSON and has no write path to the store (§7) |
| `tests/test_insights_author.py` · `tests/test_insights_class.py` · `tests/test_insights_status.py` | gates | the three axes' gates |
| `tests/test_synthesize_insights.py` | gate | the proposer's gate |
| `evidence/insights.jsonl` | data | the store |

**Consequence, stated so a reader does not derive it wrongly:** this instrument is **home-factory-only**. It has no `TEMPLATE/docs/instruments/insights.md` twin and needs none — `TEMPLATE/` is what a new factory bootstraps from, and a new factory has no insights register to govern. A future decision to ship it changes this section first.

---

## 3. The record

One JSON object per line, append-only. A row is one insight, and it carries three separable things — never conflate them:

| group | fields | what it asserts |
|---|---|---|
| **identity** | `n` · `id` · `ts` · `topic` · `stage` | which record this is, when, and what it is called |
| **the claim** | `naive_assumption` · `empirical_reality` · `mechanism` | what was assumed, what was measured, and why they differ |
| **routing** | `author` · `class` · `status` (+ `status_at`) | who wrote it, what it requires of its reader, and where it stands |
| **publication seed** | `tweet_hook` · `ru_summary` | material for the content funnel (`ru_summary` is REQUIRED at the append) |

`n` is the store's own ordinal and `id` is the stable slug; both are cited elsewhere, so neither is ever reassigned. Corrections are **appended as new rows citing the old `id`** — a stored claim is never restated to make room for a new field, which is the property §6's backfill verbs are built around.

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
| `published` | **terminal** — the unit went out |
| `landed` | **terminal** — HQ changed a process |
| `dropped` | **terminal** — deliberately not acted on, with the reason |

Four rules, each of which has a way of going wrong that this file closes:

1. **A fresh row opens `pending`, and `status` is NOT required at the append.** A destination is a *routing* decision, not a property of the claim, so a new row asserts only its own state rather than guessing someone else's decision. If the two axes were coupled at the append, the register would record an intent nobody formed.
2. **`status_at` travels with `status`.** Without the instant, *"what has been sitting in `hq` for a fortnight?"* — the question the field exists to answer — is unanswerable.
3. **Terminal states are recorded when they happen, never forecast.** `published` and `landed` are outcomes; a row that asserted one on expectation would be a prediction wearing a record's clothes.
4. **`dropped` requires a stated reason.** Silence and refusal are different records, and only one of them is checkable later.

---

## 7. The writer

- **`tools/insights.py` is the ONE writer.** Every write verb it exposes is the SAME writer; there is no second path by construction rather than by good intentions.
- **The weekly proposer does not write.** `tools/synthesize_insights.py` prints JSON and has **no** write path to the store — `INSIGHTS_PATH` is only ever read, and the `insights` it builds is a local list. A lane does the appending. This matters twice over: the register has one writer, and adding a required field cannot break the weekly cron, because the proposer never appends.
- **`classify` and `status` are BACKFILLS over one shared mechanism**, and their safety property is asserted rather than asserted-to-be-true: strip the keys they add and the store is **byte-identical** to its previous revision. A backfill adds a label; it never restates a claim.
- **All-or-nothing.** One unknown `id` writes nothing.
- **Refusal is loud.** An unspecified or unrecognised verb exits non-zero rather than reporting success.

---

## 8. `verify`, and what each axis feeds

`verify` is the store's own precondition: it rejects a stored **blank** or **unknown** value on any axis, while **accepting an absent key** on a legacy row — the distinction between *unrecorded* and *recorded as empty* is the whole point. `list` and `format` print `[legacy]` for a row that predates a field, so "not recorded" can never be read as a category.

The two classes feed two different consumers, and both are DECLARED:

| class | derived output | consumer |
|---|---|---|
| `general` | publishable content units (site, Telegram channel, X) | the miidas content funnel — Marketing drafts under `CONTENT-FUNNEL.md` §6, and the **owner approves final copy** under §5 |
| `implementation` | factory improvement ideas and process amendments | **HQ**, worked **one item at a time**, with this register's own `status` axis as the tracker — `hq` → `landed` or `dropped` |

**No second artifact.** The register is the single source for both derivatives; a brief, a summary or a queue minted beside it is the drift class this factory keeps measuring. HQ's ruling of 2026-09-28 states the intake shape: the pointer is the register, the cadence is per-item rather than batched, and the tracker is the `status` axis that already exists — never a parallel one.

---

## 9. Rollout

- **Declared executor: meta-factory.** Not a kit member (§2), so nothing is owed to a member and no version bump attends a change here.
- **A change to this file's meaning owes the three axis gates**, which is why they exist: `test_insights_author.py`, `test_insights_class.py`, `test_insights_status.py`. Each drives the CLI, and the author gate additionally drives **both** instruments (§4) and asserts one string, so the register and the ledger cannot drift apart on a lane's identity again without a red.
- **The store is the record, and this file defines it — not the reverse.** Where they disagree, one of the two is wrong and the disagreement is a defect to file, never a reading to reconcile by hand.
