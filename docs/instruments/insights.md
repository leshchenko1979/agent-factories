# Insights register — the instrument's law

Writer: Insights lane — authors this file.
Frame: `docs/instruments/template-instruments.md` — cross-instrument definitions are cited from there, never restated here.
Authority: cross-factory clauses, and process law about instruments, rest with meta-factory HQ.

**Owns:** this instrument — the record's semantics (the routing group `audience` · `process` · `surface`, plus `author` and `status`), its writer, its gate set, and this file. It exists because `author`, `class` and `status` were added to the register with no law home anywhere: their meaning lived only in a docstring and three test files, which is why a cross-instrument identity disagreement (#216: the register naming a lane `Factories / Insights` while the ledger named the same lane `insights`) could not be settled from any artifact.

## 1. The instrument, declared

Frame §1 fixes the declaration form: **an instrument is a DECLARED object**, declared by its own law file in six fields. Populated here, so a reader holding only this file and a tree can answer *"is this instrument complete here?"* without enumerating imports:

| field (frame §1) | this instrument |
|---|---|
| **name** | Insights register |
| **executable(s)** | `tools/insights.py` — verbs `append` · `list` · `verify` · `audience` · `process` · `surface` · `routing` · `status` · `reason` · `format`. One writer, ten verbs (§5, §6, §7) |
| **closure** | **none** — the CLI imports only the standard library, and its one repo-relative constant is the store it writes. There is no asset that must sit beside the binary (contrast `open-questions.md` §1, whose render asset is a closure member) |
| **gate set** | the instrument's own suite, all root-local: `tests/test_insights_author.py` · `tests/test_insights_audience.py` · `tests/test_insights_status.py`, plus the ledger-invariant gate `tests/test_insights_gate_recorded.py` — it judges this artifact's closing verdict and belongs to a shared family (`test_close_row_revision.py`, `test_score_gate_recorded.py`), and it is factory-local since 2026-09-28 (§2) |
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
| `tests/test_insights_author.py` · `tests/test_insights_audience.py` · `tests/test_insights_status.py` | gates | the three axes' gates |
| `tests/test_insights_gate_recorded.py` | gate | the ledger-invariant gate — the closing workspace-gate verdict for this artifact, sibling to `test_close_row_revision.py` and `test_score_gate_recorded.py`, sharing ONE boundary reader (`tests/ledger_boundary.py`). Factory-local by the order above; registered in this factory's audit behind a presence guard |
| `tests/test_synthesize_insights.py` | gate | the proposer's gate |
| `evidence/insights.jsonl` | data | the store |

**The census REFUSES for this instrument, and that is a declared state rather than a malformed table.** `tools/instrument_census.py` measures member *adoption* of a declared set, and an empty set has no adoption to measure: the parser returns no `↔` rows and the census refuses by design (`test_instrument_census.py` arm 7 — a zero parsed declared set is a refusal, never a clean census). The published census for this instrument is therefore a **refusal artifact**, not a table: `evidence/instrument-census-insights-2026-09-28-refused.md`, recorded at `2026-09-28T20:53Z` when the set emptied — it supersedes `evidence/instrument-census-insights-2026-09-28.md`, whose `1 path(s)` reading was correct at `18:43:13Z`, before the order. Run `instrument_census.py insights` and expect `rc=1` with that refusal named by path. The reload link (frame §6.3) is unaffected and still carries this doc across a compaction.

**Consequence, stated so a reader does not derive it wrongly:** a future decision to ship any part of this instrument changes this section FIRST — and moves the path concerned into `registry/kit.json`, a `TEMPLATE/` half, a `PAIRS` entry and `REQUIRED_GATES`/`OPTIONAL_GATES` together, since a half-shipped instrument is the state this section now rules out.

### 2.1 The extension surface — there is none, and §2 is the reason

**This instrument has no extension surface: member subject matter lives outside it** (frame §6.5).

A **declared** state, not an omission — and decidable from this section rather than from taste. §6.5's contract has four parts, and its **first requires a SHIPPED half**: the specimen's `TEMPLATE/docs/ledger-refs-kinds.example.json`, declaring nothing, with the factory-owned `docs/ledger-refs-kinds.json` beside it. **This instrument ships no path at all (§2), so it has no shipped half to declare into and no adopter to hold one** — arm (a) is unavailable here while §2 stands, not merely unchosen.

Two measured facts close the other door, the one a member would otherwise take:

- **The vocabularies are CLOSED CONSTANTS in the one writer.** `ALLOWED_STAGES` · `ALLOWED_CLASSES` · `ALLOWED_STATUSES` live in `tools/insights.py`, each refused **by name** at the write path (`stage must be one of […]`) and re-read by `verify` (`unknown status '…'`). No declaration file is folded in, so a member's own value cannot land at a point the reader accepts: it would be an edit to the module — a **fork** by §6.5's test, since it changes the shape on a path, and §6.4's tier that refuses.
- **The store is single-instance and unparameterised.** `INSIGHTS_PATH = REPO / "evidence" / "insights.jsonl"`; there is **no** environment override, and the only JSON the tool takes is the backfill mapping passed on the command line. (The lane resolver does read the fleet registry — but that is §4's **identity** join, answering *who wrote this row*, never *what the row may say*.) There is no second store to point at and no vocabulary to declare into.

**Where a member's subject matter goes instead.** A factory's own discoveries are its own register, created in its own tree — the doctrine §2 already quotes: `TEMPLATE/docs/addons/domain/stories.md` classes `tools/insights.py` as **"the factory creates it"**, because *"a ledger of discoveries a factory never made is a file of another factory's history"*. The member's material lands in the member's own instrument instance, and the duty that binds it is **frame §9 O4** as §6.5 states it — declare what its instrument accepts, or state why it has none. **O1 has no object here:** nothing ships, so no member holds a copy of a kit instrument file to dispose of. Neither clause is authored here; both are cited from §9.

**The re-entry condition, so this cannot go stale silently.** The statement is a function of §2 and moves with it: **if any part of this instrument ever ships, this subsection is revisited in the same change** — a shipped half that declares nothing is arm (a), and an instrument that ships nothing is this one. This file's own half pairs by tree presence (`tests/test_docs_sync.py`) rather than through `PAIRS`, which §2's consequence list names for the instrument's tool and gate paths.

**This builds no gate.** No offline predicate reads whether an extension is lawful; §6.5 states the test, and this subsection answers it for this instrument.

---

## 3. The record

One JSON object per line, append-only. A row is one insight, and it carries three separable things — never conflate them:

| group | fields | what it asserts |
|---|---|---|
| **identity** | `n` · `id` · `ts` · `topic` · `stage` | which record this is, when, and what it is called |
| **the claim** | `naive_assumption` · `empirical_reality` · `mechanism` | what was assumed, what was measured, and why they differ |
| **routing** | `audience` · `process` · `surface` (+ the RETIRED `class`) | who may read it, whether it changes how we work, and where a unit lands (§5) |
| **provenance** | `author` | which lane wrote it (§4) |
| **workflow** | `status` (+ `status_at` · `reason`) | where it stands in the workflow (§6) |
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

## 5. The routing group — `audience` · `process` · `surface`

Three fields, each answering **one** question, and each read by a **different consumer** — which is why there are three and not one. The values are deliberately coarse: a routing split, not a topic taxonomy. A finer value would be a second axis pretending to be this one.

### 5.1 `audience` — does the claim have a reader OUTSIDE this factory?

Two values: **`public`** (yes — routes it to a publishing surface) and **`internal`** (no).

**The test:** *does the claim have a reader outside this factory?* It is a **property of the claim**, never the funnel's verdict on it.

**Why it replaced `class`, and what the replacement fixes.** `class` asked *"does the claim hold for a reader who has never heard of agent-factories?"* — gate-independence. That is a claim about the claim, and it was **read as** a claim about audience, which it never was. The register ended up holding rows whose declared routing contradicted their fate: `class=general` sent 14 claims to the content funnel and **8 came back `dropped`**, because gate-independence is *necessary* for publication and not *sufficient* for it. `audience` asks the routing question **directly**, so an author asserts what they are in a position to know — that the claim travels — and the funnel's verdict stays the funnel's.

**`audience: public` is still not a publishability verdict**, and the axis's first live population is the proof: it landed with 8 rows and **all 8 are `dropped`**. A claim can have an outside reader and still be refused. `public` routes; it does not promise.

**`audience` is REQUIRED at the append**, together with `process` (§5.2) — both routing questions are owed on every arrival. A row that answers one and not the other is exactly the defect the retired `class` produced: one answer standing in for two, with the second never asked.

**A misspelled value is REFUSED, not defaulted** — an unknown value passes any "is it set?" check while reaching no consumer, which is the failure mode the argument-choices check exists to prevent.

### 5.2 `process` — does it change how we work?

Two values: **`yes`** (routes the row to **HQ** as an internal amendment) and **`no`**.

**It is asked of EVERY row, whatever its audience.** An insight routed to a publishing surface was never asked whether it changes how we work — and the answer is owed either way. `no` is a **RECORDED FINDING, not silence**: *"we looked, and this does not change our process"* is a result, and a row that skips the question is indistinguishable from one nobody read.

This is the axis that closes the gap §8 used to have: before it, a `public` claim left the factory and its applicability to our own processes was never asked. The duty to ask it is stated in §9; the consumer it feeds is in §8.

### 5.3 `surface` — where a unit lands

**`x`** · **`miidas`** · **`both`.** `surface` names **where** a unit is published, because the **lane** that owns it differs by surface: X is authored **here** (the `viral-x-post` skill), the miidas blog is handed to the **Marketing** lane and follows its own funnel law. `both` is **two units under two contracts**, not one artifact cross-posted.

`surface` is **NOT required the way the two axes are** — only a row in the **publishing path** owes one (§6 rule 7), because a unit cannot be published without naming where it went. A `surface` on a row **outside** that path is refused, the same way a `reason` on a row that owes none is.

### 5.4 The retired `class` — kept, never deleted

`class` was **RETIRED on 2026-10-02** by the re-cut above. It is retired **in place, never dropped**: the rows that carry it keep their key and their position in the canonical order, because deleting it would restate the record to make room for a new field — the one thing §3's additive promise forbids.

- Its vocabulary (`general`, `implementation`) is kept as **the record of what those rows were classified under**. It is **not a live vocabulary**: no value is validated against it any more, and `verify` no longer rejects an unknown one.
- New rows carry **no `class` at all**.
- A reader meeting a `class` key is meeting a **legacy label**. The question it was read as answering is now asked directly, by §5.1.

---

## 6. `status` — where it stands in the workflow

`status` is the **tracker**, deliberately separate from the routing group (§5). The axes say what a claim **IS** and who it serves; `status` says where it stands in the **workflow** — what has been DONE about it. They divide the same population differently, and neither derives from the other: a `public` claim can be `pending` just as an `internal` claim can be `dropped`.

The two are held in **agreement** by the cross-axis invariants (rules 7–9), checked at the write path and reported by `verify` — because a routing register that cannot tell *"queued for publishing"* from *"published"* is a register of intentions rather than of state.

| status | meaning |
|---|---|
| `pending` | recorded, destination not yet ruled on — **the append default** |
| `publishing` | earmarked for a publishing surface — the row owes a `surface` (§5.3, §8) |
| `hq` | earmarked for HQ as an internal amendment — the row asserts `process: yes` (§5.2, §8) |
| `refused` | **waiting** — a consumer refused it, the refusal's grounds are in `reason`, and the insight now waits on the OWNER (§6 rule 6) |
| `published` | **terminal** — the unit went out |
| `landed` | **terminal** — HQ changed a process |
| `dropped` | **terminal** — deliberately not acted on, with the reason in `reason` |

Nine rules, each of which has a way of going wrong that this file closes:

1. **A fresh row opens `pending`, and `status` is NOT required at the append.** A destination is a *routing* decision, not a property of the claim, so a new row asserts only its own state rather than guessing someone else's decision. If the two axes were coupled at the append, the register would record an intent nobody formed.
2. **`status_at` travels with `status`.** Without the instant, *"what has been sitting in `hq` for a fortnight?"* — the question the field exists to answer — is unanswerable.
3. **Terminal states are recorded when they happen, never forecast.** `published` and `landed` are outcomes; a row that asserted one on expectation would be a prediction wearing a record's clothes.
4. **A status that owes a reason requires one, and the rule is MECHANICALLY ENFORCED.** Silence and refusal are different records, and only one of them is checkable later — so the requirement is not left to the law's own reader. Two statuses owe a reason — **`refused` and `dropped`** — and they are held in ONE place (`REASON_REQUIRED_STATUSES`), read by all four enforcement points, so the write path and the reader cannot drift apart on which statuses owe one. The **write path REFUSES** a row left reason-owing with no `reason` (the append, and every backfill that sets the status), and `verify` **REPORTS** a stored row that carries none. A law whose only enforcer is whoever reads it is the shape this rule was written to close: the clause and its check land together, or the clause is decoration. Setting the status and setting the reason are one act — `status {"<id>": {"status": "refused", "reason": "…"}}` — so there is no window in which such a row exists without one. **Both directions are refused**: a reason on a row in neither state is the field's other lie.
5. **`reason` is prose, not a vocabulary.** It is a **settable field** (`status` · `reason`) and never a `FIELD_VOCAB` member, because the vocabulary is closed and a reason's whole value is saying the specific thing that was decided. A `reason` on a row that owes none is the field's other lie — it reads as a refusal where none was recorded — and `verify` refuses it. **The overturn clears it**: when the owner overturns a refusal, the status moves and the reason is *removed*, because a reason left standing beside a non-owing status is a reader trap — it says the row was refused while the status says it is moving. This is the one non-additive edit a backfill may make, it is **declared** rather than silent, and it is reported by name.
6. **A refusal is NOT terminal: it directs the insight to the OWNER for gating.** `refused` means a *consumer* — for a `public` claim, the content funnel — declined the unit, and recorded its grounds. It is emphatically **not** `dropped`: `dropped` records a decision the owner made, and a consumer's refusal recorded as the owner's decision puts a judgement in his mouth that he never formed. So the refusal **waits on the owner**, who settles it one way or the other:

   - **uphold the refusal** → `dropped`, with the refusal's grounds kept as the reason (the consumer's words, not a re-typed paraphrase)
   - **overturn** → the row returns to the workflow (`publishing` for a `public` claim) and its `reason` is cleared by §6 rule 5

   The vehicle is the **open questions register** (`docs/instruments/open-questions.md`), one question carrying every refused row with its grounds, defaulting to *uphold* — so the owner marks only what he would overturn rather than voting on each. A refusal that never reaches him is the same defect class as #216 and #227, one surface over: a rule whose only carrier is whoever happened to see it. This is where the owner keeps the last word without becoming the classifier.

   **What a refusal is based on, derived rather than invented.** The funnel's refusals fall into three tests, taken from its own dispositions (miidas Marketing, 2026-09-28: `863b4b4` / `159bb80`, board #80) rather than composed here — a unit is refused when it

   - **reports a design rather than an outcome** — the funnel's own words are *"specifications, not outcomes"*
   - **restates a finding the register already carries** — *"one builder-only insight appearing in four spellings"*; the first statement is the unit, its restatements are not
   - **gives the reader nothing they do not already have** — *"the buyer-facing core is already carried by a published post, and the row adds only builder-level mechanism"*

   These are the grounds a refusal **records**, not a gate: no offline predicate reads them, and the decision stays with the owner under this rule. Each refusal names the test it failed in its own `reason`, with a link to the entry or published piece it overlaps, so the grounds are checkable rather than a matter of taste. The derivation is kept here for the same reason §9 keeps its research: a rule whose only carrier is the turn that produced it does not survive a compaction.

7. **A row in the PUBLISHING PATH owes a `surface`, and the path is held in ONE home.** The path is `publishing` · `published` (`SURFACE_REQUIRED_STATUSES`), read by the append path, the backfill path and `verify` — the same one-home shape rule 4 gives the reason-owing statuses, for the same reason. A unit cannot be published without naming where it went, because the **lane that owns it differs by surface** (§5.3). **The CLEAR is part of the rule:** a row that LEAVES the path loses its `surface` in the same transaction, exactly as it loses its `reason` — a destination on a row that is not going anywhere is the field's other lie, and `verify` refuses it.

8. **D4's first invariant — the publishing path asserts a PUBLIC audience.** A row whose `status` is in the publishing path asserts `audience: public`; a publishing row declaring `internal` contradicts itself, and the write path refuses it. The invariant fires **only where the row CARRIES the routing group** — a row predating the re-cut is not condemned for a claim it never made.

   **The carrier guard belongs to the READ leg, and the write leg must NOT carry it (#279, ruled).** The two legs apply one invariant over two **different populations**, and the difference is deliberate. `verify` reads every row, legacy ones included, so it exempts a row that does not carry the group; the write path only ever sees a row being written, which must carry the group, so it exempts nothing. Widening the write leg to match would let a single-field verb write a **partial group** that `verify`'s own `carries_routing_group` marker then forgives — which is why HQ's ruling on #279 (`faee48f`, 2026-10-02) REFUSED that direction.

   **What #279 measured is the refusals' SHAPE, not the legs' divergence.** All three single-field verbs (`process`, `audience`, `surface`) refuse on a pre-re-cut row, each naming a **different** missing sibling and **none naming the door that works** — a **refusal cycle with no exit** for the population those verbs cannot serve. The door is **`routing`** (§7), which lands the whole group in one transaction; the single-field verbs are for rows **already carrying** the group, and each refusal now names it. The ruling ordered four sub-legs instead of the widening, and all four are implemented: a **named backfill verb** for the routing group (`set_routing`, the CLI's `routing`); the three single-field docstrings narrowed to their real population, with their refusals naming the working door; the invariant implemented **once** (`routing_group_violations`, with the legacy exemption an explicit `exempt_legacy` parameter read by all three call sites); and the **test gap** closed (`set_surfaces` is covered on its lawful population and on a legacy publishing row, and a probe that bites covers the whole door).

9. **D4's second invariant — a row routed to HQ asserts `process: yes`.** `hq` and `landed` (`HQ_PATH_STATUSES`) assert that the insight **IS applicable to our processes**, so `process` must say `yes` on them. The two fields stay separate — `audience` and `process` answer different questions — but they must not **contradict** each other, and this is the set on which they could. Refused at the write path, reported by `verify`.

**A routed row migrates ATOMICALLY.** A row that is `hq`/`landed` owes `process: yes`; a row in the publishing path owes `audience: public` **and** a `surface`. So a routed row can take **no single field alone** — which is why the door for a legacy routed row is `routing` (§7), which lands the whole group in ONE transaction and writes no status, and not any one of the three axes.

---

## 7. The writer

- **`tools/insights.py` is the ONE writer.** Every write verb it exposes is the SAME writer; there is no second path by construction rather than by good intentions.
- **The weekly proposer does not write.** `tools/synthesize_insights.py` prints JSON and has **no** write path to the store — `INSIGHTS_PATH` is only ever read, and the `insights` it builds is a local list. A lane does the appending. This matters twice over: the register has one writer, and adding a required field cannot break the weekly cron, because the proposer never appends.
- **`audience`, `process`, `surface`, `status` and `reason` are BACKFILLS over one shared mechanism**, and their safety property is asserted rather than asserted-to-be-true: strip the keys they add and the store is **byte-identical** to its previous revision. A backfill adds a label; it never restates a claim. `reason` is a settable field rather than a vocabulary member (§6 rule 5), and it is its own verb because a backfilled reason must not re-date the row: `status` moves `status_at`, while `reason` sets the prose and nothing else, so an unset field filled in later cannot silently move the instant that field's sibling exists to record.
- **The single-field verbs are for rows ALREADY carrying the routing group.** A legacy routed row — one written before the re-cut — cannot take one axis alone: §6's invariants refuse each, and each refusal now **NAMES the door that works** rather than a sibling the caller must guess at (#279). That door is **`routing`**, which backfills `audience` + `process` (+ `surface` where the status owes one) in **ONE transaction** — the group is atomic, so a sequence of single-field writes would pass through a partial group that `verify`'s own carrier marker forgives. `routing` writes **no `status` and no `status_at`**, so a backfilled group cannot re-date the transition that produced the row. Where the move is a **status** transition, `status` remains the door — and for a legacy routed row it carries the row's **OWN** `status_at` forward, being the **preserve-only door** for the instant, so a caller may carry an instant forward and may never mint one. Either way the result is additive in the same sense as every other backfill: the strip is byte-identical.
- **All-or-nothing.** One unknown `id` writes nothing.
- **Refusal is loud.** An unspecified or unrecognised verb exits non-zero rather than reporting success.

---

## 8. `verify`, and what each axis feeds

`verify` is the store's own precondition: it rejects a stored **blank** or **unknown** value on any axis, while **accepting an absent key** on a legacy row — the distinction between *unrecorded* and *recorded as empty* is the whole point. `list` and `format` print `[legacy]` for a row that predates a field, so "not recorded" can never be read as a category. Six further refusal classes ride the same reader, each one a rule §3 or §6 states and this section enforces: a row left reason-owing (`refused` or `dropped`) with no `reason` (§6 rule 4); a `reason` recorded on a row that owes none (§6 rule 5); a broken **supersession** chain — a marker naming a later, missing, differently-`id`d or already-superseded row (§3); a row in the **publishing path** with no `surface`, and its mirror, a `surface` on a row **outside** the path (§6 rule 7); a publishing row whose `audience` is not `public` (§6 rule 8); and an `hq`/`landed` row whose `process` is not `yes` (§6 rule 9).

**One predicate, two legs — over two populations, and the difference is deliberate (#279, ruled).** The cross-axis classes above are enforced at the write path *and* reported by `verify`, and both legs read the SAME declared set (`SURFACE_REQUIRED_STATUSES`, `HQ_PATH_STATUSES`). Their **populations** differ, and that is the ruled shape: `verify` exempts a row that does not carry the routing group because it reads legacy rows, while the write path exempts nothing because it only ever sees rows being written — so widening the write leg would admit a **partial group** that `verify`'s own carrier marker then forgives. What #279 measured was the refusals' shape rather than that divergence: a refusal cycle with no exit, whose four sub-legs are ordered in §6 rule 8.

The register feeds **three** consumers, and all three are DECLARED. The axis that selects each one is stated, so a row's destination is read **off the row** rather than inferred:

| axis value | derived output | consumer |
|---|---|---|
| `process: yes` | factory improvement ideas and process amendments | **HQ**, worked **one item at a time**, with this register's own `status` axis as the tracker — `hq` → `landed` or `dropped` |
| `surface: x` | a post for the X account | **this lane**, authored with the `viral-x-post` skill |
| `surface: miidas` (or `both`) | a unit for the miidas blog | the **miidas content funnel** — Marketing drafts under `CONTENT-FUNNEL.md` §6, and the **owner approves final copy** under §5 |

**`process` and `surface` are independent, and a row can feed both.** They answer different questions — *does it change how we work?* and *where does it land?* — so a row may be `process: yes` **and** `surface: x`. `both` means two units under two contracts (§5.3), not one artifact cross-posted.

**The consumers are addressed by LANE, never by a topic.** The X series is authored **here**; the miidas units are handed to **Marketing**; the `process` queue is **HQ's**. A handoff is verified **by content in the target's own rows** — never by a send receipt.

**No second artifact.** The register is the single source for all three derivatives; a brief, a summary or a queue minted beside it is the drift class this factory keeps measuring. HQ's ruling of 2026-09-28 states the intake shape: the pointer is the register, the cadence is per-item rather than batched, and the tracker is the `status` axis that already exists — never a parallel one.

---

## 9. Intake — what happens when an insight arrives

**One arrival, three outputs, in one turn — and they land in the ROW, not only in the reply.** An insight posted into the Insights topic — the owner's or a lane's — is handled in the turn it arrives, and that turn owes **all three**. A record without its research and its mapping is an intake that stopped halfway. The owner ordered this shape on 2026-09-28; that it reached no artifact until #227 is the same defect class as #216 — a binding rule whose only carrier was a conversation.

That defect sat one surface further in on 2026-09-29, and this section is where it was closed: measured at the row for `n=32`, **1 of 10** research findings — 1 of 5 cited sources and 0 of 5 mapping clause names — had reached the register, because this clause required the research to be *presented* and said nothing about where it was *kept*. A reply is a context-time object, which is precisely the thing rung 1 of that same insight externalises. So each of the three outputs is required to **land in the row**, where a later lane reaches it after a compaction, and not merely where the turn that produced it could see it.

1. **RECORD.** One `append`, carrying its `author` (§4) and the **routing group** — `audience` **and** `process` are both **REQUIRED at the append** (§5), and a `surface` is owed the moment the row lands in the publishing path (§6 rule 7). The owner's insights carry `author: Alexey`. Both axes are the authoring lane's call, derived by §5's tests — *does it have a reader outside the factory?* and *does it change how we work?* — never by the submitter's sense of audience.
2. **RESEARCH.** Search external best practice on the problem the insight discusses, and present it with **its sources and their dates**, stating of each whether it **agrees with**, **sharpens**, or **contradicts** the insight. **Every source lands in the row, cited by id and date, in the field it evidences** — `n=32` is the pattern rather than an exception: its `empirical_reality` carries *arXiv:2606.22953* with the figures it contributes (4.1×, 34.7 pp, 56.7% → 22.0%), so the evidence is readable from the store alone. A source that reached only the reply is one the register cannot show, and the finding dies with the turn that found it. `No practice found` is a **declared finding**, never silence: the search is itself evidence, an empty result is still a result, **and the row records it as one**.
3. **MAP.** State what the insight would change, in **which** factories, and **where it does not apply**. **The mapping lands in the row too** — where the insight is **already codified**, the **clause names** it points at are recorded in the row, so *"already codified"* is checkable by a later reader rather than recalled by whoever held the turn. The mapping is a dedupe as much as a translation: an insight the fleet **already codifies** is answered by **pointing at the clause**, and is settled `landed` with that clause as its reason rather than re-filed — the already-codified arm of the sort §8's `process: yes` consumer works one item at a time.

**The `process` verdict is a DUTY, not an option — and it is owed on EVERY arrival.** *"We looked, and this does not change our process"* is a **recorded finding** (`process: no`), and it is the answer most arrivals will get. What is not permitted is **not asking**: before this axis existed, a claim routed to a publishing surface was never asked whether it applies to our own processes, so the fleet's own improvement ideas could leave as marketing copy and never reach HQ. The verdict is owed in the turn the insight arrives, by the lane that records it — the same turn that owes the research and the mapping.

**The bound.** Intake is a judgement about content, and it builds **no gate**: no offline predicate reads whether a mapping is honest or a cited practice real, and this clause adds none. *Requiring a finding to be stored is not requiring it to be true* — that is why `verify` reads the axes and never the prose, and why the difference between the two is stated here rather than left to be assumed. What upholds the workflow is the authoring lane performing it **and the finding reaching the row**; the reload leg exists so that this clause itself survives a compaction, which is the same argument one level up.

---

## 10. Rollout

- **Declared executor: meta-factory.** Not a kit member (§2), so nothing is owed to a member and no version bump attends a change here.
- **A change to this file's meaning owes the three axis gates**, which is why they exist: `test_insights_author.py`, `test_insights_audience.py`, `test_insights_status.py`. Each drives the CLI, and the author gate additionally drives **both** instruments (§4) and asserts one string, so the register and the ledger cannot drift apart on a lane's identity again without a red.
- **The re-cut is a rollout, not a rewrite of history.** `class` is retired **in place** (§5.4) and no row is backfilled to remove it; the 7 publishing-path rows still owe their routing group **atomically**, on the owner's answer to the question that carries them, and they take it through `status`, carrying their own `status_at` forward (§7). Nothing is backfilled by a second path.
- **The store is the record, and this file defines it — not the reverse.** Where they disagree, one of the two is wrong and the disagreement is a defect to file, never a reading to reconcile by hand.
- **This instrument is factory-local, so the doc-pair contract's shipped half does not apply — and the reload link is the exception that declares it.** `skills/meta-factory/SKILL.md` §11 states that an instrument ships as a doc pair (`docs/instruments/<instrument>.md` + `TEMPLATE/docs/instruments/<instrument>.md`) and reloads through a relative symlink. §2 above declares that **no path in this instrument ships** — the owner's order of 2026-09-28 (quoted at §2) — so there is no shipped half to pair with and none is created: a `TEMPLATE/docs/instruments/insights.md` would contradict §2 and re-ship exactly what the order withheld. The reload link therefore resolves to the ROOT doc (`skills/meta-factory/insights.md -> ../../docs/instruments/insights.md`), unlike every shipped instrument whose link resolves to its `TEMPLATE/` half (`hygiene.md -> ../../TEMPLATE/docs/instruments/hygiene.md`). That divergence is the declaration, not drift. The gate half is tracked at **#37** (a root-only doc is invisible to `tests/test_docs_sync.py`, which walks TEMPLATE -> root only); the contract-level contradiction in §11's *every instrument* wording is tracked at **#358** and routed to HQ.
