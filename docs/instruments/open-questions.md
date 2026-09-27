# Open Questions register — the instrument's law

Writer: Open Questions instrument lane — authors this file.
Frame: docs/instruments/template-instruments.md — cross-instrument definitions are cited from there, never restated here.
Authority: cross-factory clauses, and process law about instruments, rest with meta-factory HQ.

**Owns:** this instrument — its contract, its rollout, and this file. **Re-homed from** `skills/opencrabs-dev/fleet-directives.md` §Open Questions register (owner order 2026-09-27, 05:41 MSK). The source keeps a `[LANE]` pointer to this file, and that pointer is what preserves the contract's reach across the skill-reload path — see §6.

## 1. The instrument, declared

Frame §1 fixes the declaration form: **an instrument is a DECLARED object**, declared by its own law file in six fields. Populated here, so a reader holding only this file and a tree can answer *"is this instrument complete here?"* without enumerating imports:

| field (frame §1) | this instrument |
|---|---|
| **name** | Open Questions register |
| **executable(s)** | the CLI; verbs `ask` · `answer` · `amend` · `notify` · `list` · `publish` · `lint` · `gc`. Its path law is §5.1 |
| **closure** | the render asset that must sit BESIDE the binary, and `node` on PATH — declared, never derived (frame §1.1). A one-file install is INCOMPLETE, not minimal: it registers happily and publishes nothing (§5.2) |
| **gate set** | the instrument's own suite, `tests/test_questions.py`; this law pair is gated by `tests/test_docs_sync.py` |
| **version source** | the kit manifest — DERIVED, never hand-typed (frame §7.1) |
| **data surfaces** | the register store in the profile home, shared by every install shape, so no member owes a migration; shipped `.example` versus factory-owned is declared at adoption (§5.4) |

---

## 2. The declared file set

**Predicate:** the shipped paths the kit manifest classifies `standalone` that carry this instrument —
plus, per frame §1.4, every path the executable reaches **indirectly**, which here is **none**: the CLI
imports only the standard library and its one repo-relative path constant is the render asset that must
sit beside it. **Scope:** `registry/kit.json`, whose population is the `TEMPLATE/` half. Both halves are
listed because the pair is what a member adopts; the manifest hashes the `TEMPLATE/` half.

| # | path (root half ↔ TEMPLATE half) | class | what it is |
|---|---|---|---|
| 1 | `tools/questions` ↔ `TEMPLATE/tools/questions` | `standalone` | **the executable** — every verb: `ask` · `answer` · `amend` · `notify` · `list` · `publish` · `lint` · `gc` · `selftest` |
| 2 | `tools/questions-render.mjs` ↔ `TEMPLATE/tools/questions-render.mjs` | `standalone` | **the render asset**, resolved beside the binary — a one-file install registers happily and publishes nothing (§5.2) |
| 3 | `tests/test_questions.py` ↔ `TEMPLATE/tests/test_questions.py` | `standalone` | **the gate** — invokes the tool's own `selftest` |
| 4 | `docs/instruments/open-questions.md` ↔ `TEMPLATE/docs/instruments/open-questions.md` | `standalone` | this file |

**A reader holding this file and a tree can answer *"is this instrument complete here?"* without
enumerating imports**, which is what frame §1 requires of a declaration. The member's reload link
(`skills/<skill dir>/open-questions.md`) is deliberately **not** in this set: it is the member's own
act under frame §6.1, and the transport creates no links.

---

## 3. The lane-side contract

> **Re-homed verbatim, with THREE departures carried INTO the text rather than appended:** the page-URL mechanism (§4, corrected from the tool rather than from either prose), one pinned line citation de-positioned per §5.5, and the source's own heading demoted so it sits under this section. Everything else below is the source's wording.

### Open Questions register — the sanctioned "blocked on you" channel (owner-commissioned 2026-09-24) [LANE]

The owner cannot see which lane is blocked on him: a parked decision exists only as prose in that lane's own topic, with no aggregate, no ordering by age, and no one-tap answer. The Register is the fix; this clause is the lane-side contract.

- **Register in the same turn you park.** A lane whose next action needs an owner decision calls `oc-questions ask` in the SAME turn it stops, naming itself and its ordered question set. A prose "blocked on you" line in the topic is NOT a registration — nothing aggregates it.
- **The Register is the ONLY sanctioned blocked-on-you channel.** Do not open a parallel mechanism, and do not re-ask in the topic on a daily clock once registered: the register's `asked_at` age is what re-surfaces a question, so a repeated topic ping is noise rather than pressure.
- **Each question has exactly two required inputs:** `title` and Markdown `description` (tables and Mermaid supported). A question MAY carry `options[]`, a `recommended` default, and a Clarify action; a free-text answer is always available, and Clarify never silently closes the question.
- **The asking session id comes from the ENVIRONMENT, never typed.** `ask` reads `OPENCRABS_SESSION_ID` — the id the daemon set for the calling turn. It must never be replaced by a cron session, a renderer session, or another lane, because a substituted id orphans the answer. **`--lane` is REMOVED (owner order 2026-09-25):** the lane is resolved BY THE TOOL from the asking session's own binding (`session_bindings` → `chat_id` + `thread_id` → `channel_messages.topic_name`); `sessions.title` is deliberately NOT used, because it carries auto-generated titles for some lanes.
- **The return address follows the UNIT, not only the ask.** The clause above governs what happens AT ASK TIME; a unit that changes hands AFTER its question is registered is a separate hazard, and it has already bitten. So **a re-route dispatch carrying an open question MUST carry that question's current state (asked / answered / hold) in the dispatch body** — a hold addressed to a lane that no longer holds the unit is not a hold the actor received. The durable fix is a tool change: the return address follows the unit's **live claim holder** rather than the asking session (routed to the Toolsmith, `tools/**`); until it lands, the dispatch-body leg is the binding one. Origin, verified on the store rather than recalled: set `ffbfa5` recorded session `c78e78e0`, q2 answered *"Hold — keep the global freeze"* at 22:20:29Z, the unit was then re-routed to `a5b34466`, and that lane filed upstream PR #1732 at 22:53:42Z — **33 minutes after the hold, never having received it**. The destination was CORRECT for the asker and WRONG for the actor, so the hold was not disobeyed; it was addressed to a lane that no longer held the unit. (Triage, 2026-09-27.)
- **A role the law names but nobody staffs is a LAW defect, not one lane's problem.** The editor clause in `SKILL.md` ends an editor's obligation at smoke evidence and hands census, porting, PR filing and upstream lifecycle to the **HARVEST lane**, and `harvest.md` names that lane as the actor for every harvest step. Measured 2026-09-27: **0 harvest lanes exist** — `roster --live` tallies editor 31 · triage 2 · toolsmith 1 · hq 1, and the four apparent harvest rows are editor enrolments whose **feature string** merely contains the word. So the law created an obligation no lane can discharge, while the work runs under editor enrolments that the same clause forbids. **When the owning role is vacant, the work PARKS on the register with the vacancy named as the blocking condition** — never silently assigned to the nearest idle lane, and never left as *"an editor has taken work it does not own"*. Staffing the role is the owner's call; recording the vacancy here is what stops the next lane re-deriving it from scratch.
- **ONE standing set per FACTORY (owner order 2026-09-25).** `ask --factory <KEY>` is REQUIRED, and the factory key IS the standing set id — created on first ask and REUSED, so a factory accumulates its questions in ONE set at 0..N rather than minting a one-off container per call. An **unbound** session is REFUSED non-zero: it can never receive the answer, so it must not register a question at all.
- **The page URL is CONSTANT and READABLE (owner order 2026-09-25).** The order is cited here, not authored. There is no rotating token — and the reason is the POINTER, never the factory key: the slug is the value recorded in `pages/latest.json` on the first publish and REUSED from then on, and the tool reads that pointer BEFORE it consults the register, the register supplying a slug only when no pointer exists yet. So a lane publishes the URL it READ from the pointer and NEVER assembles one from its factory key: ONE page directory serves every set, so a path built from the factory key is a dead link for every factory except the one it happens to name. Measured 2026-09-27: `pages/` held ONE directory while the pointer's own `sets` list named three. Each lane also gets a **stable anchor** — the pointer's URL plus `#lane-<lane-slug>` — so a lane can be handed a link that lands directly on its own questions. The page groups by LANE and shows a per-lane open count.
- **Decisions are collected on the PAGE, not from card buttons (owner order 2026-09-24).** Cards with tappable buttons are RETIRED: a tap is dropped while the target session is mid-turn (#553, closed not-planned), so the page is the single aggregate surface. `ask` returns the open-question TOTAL and no card. The page posts each decision back to the lane that asked, resolving the destination from the REGISTER by set-id — never from the request body, so a crafted POST cannot redirect an answer.
- **A Clarify is a request, and the lane owes an amendment.** Clarify never closes a question: its status becomes `clarifying` and the asking lane is notified. The lane MUST then `amend` it (revised title / description / options), which returns it to `open`. A clarifying question left unamended dead-ends the loop and the owner never sees the answer.
- **Closure is mechanical wherever it can be.** Beyond an explicit answer or withdrawal, a question closes when the thing it asked about has moved: a named fork issue reading CLOSED closes it as `resolved_mechanically`, and an explicit `close_when` predicate closes on rc=0. An unreadable predicate prints a SKIP note and closes nothing — never a silent close. Silence is still not an answer.
- **The page is re-rendered on every register mutation** — a new question, an answer, a clarify, an amendment — so it is never stale. The twice-daily cron sweeps expiry and mechanical closure; it is NOT the refresh path.

Store: `~/.opencrabs/profiles/ops/questions/open.json`, with answered sets archived to `archive.jsonl` and the rendered page under `pages/<pointer-slug>/` — the slug READ from the pointer, never assembled from the factory key (correction in §4). Tool: `skills/opencrabs-dev/tools/state/oc-questions` — verbs `ask` · `answer` · `amend` · `notify` · `list` · `publish` · `lint` · `gc` (Toolsmith, `tools/**` carve-out); its path law is §5.1, because the path is resolved at call time rather than assumed. Fork issue #547 carries the build. Live page: the URL recorded in `pages/latest.json` (lane anchors `#lane-<lane-slug>`).

## 4. The page URL — corrected from the tool, and whose law it is

The re-homed contract above states the page URL law. Its **mechanism** was wrong in the source, and it was wrong in the one direction that reaches the owner: a lane following it assembles a URL from its own factory key and hands the owner a dead link.

**The correction, read from the tool rather than from either prose.** The slug is the value recorded in `pages/latest.json` on the first publish and REUSED from then on; the tool reads that pointer BEFORE it consults the register, and the register supplies a slug only when no pointer exists yet. So ONE page directory serves every set, and the URL is per-INSTRUMENT rather than per-factory. Measured 2026-09-27: the page directory held ONE entry while the pointer's own `sets` list named three, so two of the three sets had no directory of their own to be served from. Three surfaces agree — the tool's own slug function, the pointer's own content, and the `oc-questions` row of `RC-CONTRACT.md` — and the two that disagreed were the two PROSE statements. That is why this correction is derived from the tool.

**Classification, per clause** — frame §8's split: authorship of a law doc is delegable, authority over a clause that binds a member factory is not.

| clause | class | consequence |
|---|---|---|
| the URL is constant and readable, no rotating token (owner order 2026-09-25) | **AUTHORITY** — cited, not authored here | unchanged; this file does not restate the order, it relies on it |
| the mechanism — pointer-first, recorded on first publish, reused thereafter | **INSTRUMENT LAW** — authored here, derived from the tool | the corrected text above |
| the stable per-lane anchor | **INSTRUMENT LAW** — authored here | kept, but expressed against the pointer's URL rather than a factory-key path |

**No clause authored in this file binds a member factory.** Every clause above governs how this instrument behaves for the lane that invokes it; a member that adopts the instrument inherits that behaviour and takes on no new cross-factory duty. Where a clause would bind member factories it is HQ's, and is cited rather than authored.

### 4.1 The page model — ONE page, honestly titled, filterable per factory

The instrument publishes ONE page and it carries every open factory's questions. That was always the design — one pointer, one directory, populated from the register's own set list — but the page did not SAY so, and the gap reached the owner as a false statement about the instrument.

- **The title names the SUBJECT, never one factory.** The page is titled `Factory Open Questions (N)`, N being the count of open questions SHOWN. The title previously interpolated the pointer's slug, so a page carrying four factories announced itself as one of them — the owner read a single factory's name over a fleet-wide page. A title derived from a path is a claim about the path, not about the content.
- **The count describes what is SHOWN, and is computed after the filter.** A total taken before narrowing prints a fleet figure beside a filtered view — the same mis-scope that once reached `--json` as a filtered lane list beside an unfiltered total.
- **The per-factory filter is a VIEW, never a partition.** A control lists every factory present on the page plus "All"; choosing one hides the sections whose `data-set` does not name it. The sections already carry `data-set` for exactly this purpose — the renderer's own comment says it is for the READER, not the tool — and the filter ships inside the UI script the instrument already generates and tests. No second asset, no server change, no per-factory directory.
- **The filter defaults to "All", and the page works with scripting disabled.** The control is built by the script, so the delivered HTML carries none: with scripting off the reader sees the full page rather than a dead bar. That property is asserted, not assumed.
- **The URL does not change, and that is deliberate.** The bookmarked path keeps serving the whole page — the owner order that pins the pointer's slug as a permanent bookmark is cited here, not restated. The filter changes what the page SHOWS; it does not repurpose the path.
- **The page's NAME is never a factory; only its ADDRESS is a holdover (owner question 2026-09-27).** A factory name on this page is a VIEW TAG: it labels a filter control and it names the `data-set` of the sections it scopes. It is not the page's name. The title and the `h1` are neutral, so the reader is never told the page IS one factory. The single place a factory name still identifies the page is the PATH, which is the pinned permanent bookmark and therefore an ADDRESS, not a label — repurposing it would break the link the owner order protects. An address that misleads is a reason to change the ADDRESS, and that is an owner decision, not a rendering one: it is recorded here as the instrument's one remaining conflation, deliberately left standing rather than silently renamed.
- **The chrome above the `h1` is empty (owner order 2026-09-27).** The shell used to emit one meta line reading "permanent link" — a statement of a property the register already holds, placed as the first thing the reader met. It is gone. The page's `expires_at` stays in the page META, which is where the answer backend reads it from; permanence is a property of the register, never a line of chrome.
- **A clarifying question is COMPACT and its form is COLLAPSED (owner order 2026-09-27).** A `clarifying` question is waiting on the LANE — the lane owes the amendment that returns it to `open` — so it is not waiting on the reader and must not occupy an actionable question's space. The card shrinks, and its form moves behind a native `<details>` whose summary reads "Answer anyway". The form stays in the DOM with its `token` / `set` / `qid` inputs, so the question remains answerable when opened, and the toggle is native HTML: inert with scripting off, never a script dependency.

### 4.2 The `--set` contract change

`publish` no longer accepts `--set`. It is REFUSED non-zero with the reason named: the page carries every open set, so a narrowing flag has nothing to address. The verb's contract is now the whole register, and a caller wanting one factory's questions asks for a VIEW (the filter above), never a narrower publish.

**Why removed rather than kept.** The flag was the mechanism by which the published page could be narrowed to a single set, and narrowing STRANDS the sets it excludes: the answer backend validates a posted set against that page's own recorded set list, so an excluded set's open questions become unanswerable from the page that serves them. A flag whose use can silently strand an owner decision does not belong on the publish path.

`--set` remains the ADDRESSING flag on the set-scoped verbs; only `publish` loses it.

### 4.3 The addressing key — `qid`

Every question carries a **`qid`**, and it is the key a consumer must address it by.

- **Stamped at ask time, never re-derived.** It continues the standing set's own numbering, so it is unique within the set and stable across every later mutation — an answer, a clarify, an amendment, a withdrawal. Nothing renumbers it: a new question appends, and a withdrawal sets a status rather than removing the row.
- **`--qid` is its flag.** The set-scoped verbs address a question by `--qid`; the set itself is addressed by `--factory`.
- **Do not reach for `id`.** The set-level field is `id` and it names the SET, so a consumer who reads the law and reaches for the question's `id` gets a missing key — and a missing key reads exactly like an absent value. Stated because it has already happened: a peer enumerated the question object, read `id`, found nothing, and reported that questions carry no identifier at all, while `qid` was present on every row. The failure is silent in both directions and cost a full round.

## 5. Operational law

Each section below exists because it has already cost a real cycle. All of it asserts SHAPE — never a byte size, a digest, or a line number (§5.5).

### 5.1 The executing path is RESOLVED, never assumed

The CLI is located by a glob under the skill's tools root, and the resolution demands EXACTLY ONE match: zero or two-or-more is a hard exit, not a fallback. Two consequences bind every reader of this file:

- **A vendored copy and the skill's copy are not interchangeable.** A tree can hold its own copy and never execute it; a tree can hold none and still have the instrument working.
- **A census must run the tool on the path its runtime INVOKES** — never index trees. A tree read reports an install that does not run, and reports nothing for a factory whose runtime path works. Both are the same instrument error in opposite directions, and both have been produced for real this cycle.

The path is resolved at call time, so no clause in this file may pin it.

### 5.2 The install closure is TWO files, and the failure is SILENT

The binary resolves its render asset BESIDE ITSELF, by a name that tracks the binary's own name. The closure is therefore the tool PLUS that asset, and the two names are coupled: renaming or relocating one leg without the other breaks the render path.

The hazard is NAMING, not content — a rename separates the halves while each file remains individually correct. And the failure is soft: a half-install registers a question happily and publishes nothing, so a caller checking only the exit code reads a stranded question as a success. This is why §1's `closure` field is DECLARED rather than derived (frame §1.1), and why a one-file install is INCOMPLETE rather than minimal.

### 5.3 The stranded question — a fault that reaches nobody (#189)

A mutation that auto-publishes SWALLOWS a render fault: the publish leg catches its own fatal exit and reports "no page", and the mutation path then treats the page as optional. The consequences compound:

- **A deliberate skip and a broken renderer produce different output on stderr but not in JSON.** Both leave the page absent (`page: null` in JSON), so a consumer parsing only `--json` cannot tell "I asked for no page" from "the page was not built". However, on stderr the skip prints nothing while a fault prints a warning — so a caller seeing stderr can distinguish them.
- **The reason survives and is logged.** The fix records the reason in a module-level slot (`_LAST_RENDER_FAULT`), names it on stderr via `_note_publish_fault()`, and logs it with `oc_log_extra("publish_failed", why)`. The log helper now writes the reason, but note the unified tools log is still disabled by default (`--no-log`), so on the ordinary daemon path the fault reaches nobody via the log.
- **The instrument's own suite now accepts both properties.** The standalone `publish` verb still fails loudly on a fault (die(4)), while the mutation path treats the page as optional and names the fault on stderr — so one instrument has two entry points with context-appropriate verdicts.

**Landed fix:** commit `b16451e` (2026-09-27T04:51:55Z) implements the above. The exit code stays 0 by design, the fault reason is named on the mutation's own stderr, and stdout stays parseable so a caller reading `--json` is unaffected. The item's acceptance is channel-agnostic — "the property to satisfy, not the channel" — so naming the fault on stderr satisfies it; a relayed restatement of the criterion named stdout, which the implementation deliberately did not take, to keep the `--json` payload usable.

### 5.4 Rollout and adoption

**declaration → install → verify.** The shape is each member's OWN decision (frame §3, §6.1), and two rules bind this lane:

- **Never install unilaterally.** A copy placed where none was asked for is drift the member did not choose.
- **"Absent from its own tree" is NOT "unusable."** Reaching a shared copy is a legitimate adoption shape, and for at least one member it is the DECIDED one. State which shape a member chose; never imply a gap where a decision was taken.

The member leg is an ADOPTION STEP, not a push from here: the transport copies files and creates no links, so a member that wants its law doc on a skill-reload path creates its OWN relative link (frame §6.1).

### 5.5 Assert SHAPE, not hash

Every copy named in this file MOVES — one of them moved twice while this file was being written. So no clause here may pin a byte size, a digest, or a line number of any copy. Derive a boundary at run time from heading text rather than from a remembered position, and state the PROPERTY that must hold — the pointer is read first, the closure is two files, exactly one CLI resolves — never the measurement that happened to hold at writing time.

### 5.6 The ontology collapse — fields that were written and never read

The register carried fields no consumer reads, and one of them produced a false finding before it was removed. They are gone; this records which, and the bar for keeping one: a READER, never a writer.

| removed | why it went |
|---|---|
| the register's top-level `version` | written once, read by nothing |
| the set entry's `factory` | a second name for the set's own `id` — one value under two keys |
| the set entry's `updated_at`, the question's `amended_at` and `withdrawn_at` | write-only timestamps; the mutation that sets them is already recorded by the field it changes |
| the page meta's `created_at` | write-only |
| the page meta's `token` | a second name for the same page's `slug`, and the answer path takes the token from the REQUEST and uses it as a path component — it never reads the stored field |

**The pointer is now a pointer.** `pages/latest.json` previously carried a full COPY of the page meta it points at, while the only field its reader needs is the slug. It now carries the slug alone, so the two surfaces cannot disagree — which is exactly what the duplicate was inviting.

**"Unused" is not "unread", and a population count cannot tell them apart.** Two categories survive on purpose and must not be swept:

- **A capability with no rows yet is not dead.** A field can be written by one path and read by another while no live row carries it; a row-count sweep reads that as unused and would delete an owner-ordered feature. Check for a READER, not for a row.
- **Provenance on ARCHIVED rows is the payload, not residue.** A closed set keeps who answered it and when, because the archive is history.

**A write-only field is not merely unused bytes — it is a trap for the next reader.** One removed timestamp disagreed with its question's own status on a handful of rows, because an amendment re-opens a question and leaves the earlier stamp behind. The rows were healthy and the FIELD was the defect: a reader comparing the two reports a contradiction that does not exist. This lane filed precisely that false finding before the field was removed.

## 6. Ownership, and the reload leg

| who | what |
|---|---|
| **this lane (Open Questions instrument)** | this file; the instrument's contract, its rollout and its behaviour |
| **Instruments methodology** | the frame this file cites; review of this file is a REQUIREMENT, not a courtesy (frame §8) |
| **meta-factory HQ** | cross-factory clauses, and the process law ABOUT instruments (frame §8) |

**Out of scope for this lane, by role (frame §8):** `tools/**` code (Toolsmith — file the defect, never edit it), daemon and core source (Editor), and the surface an instrument runs on where that belongs to another factory. This lane supplies TEXT to the lane that owns a file; it does not land it there.

### 6.1 The reload leg — why the source keeps a pointer, and the order of the move

This file is canonical here, and it reaches the skill-reload path through a RELATIVE symlink from the skill directory — so one inode carries two paths and the halves cannot drift. That link is a THIRD artifact: it is not in the kit manifest (whose population is the template tree) and not in the law pair's twin gate, so nothing checks it but the reader, which is why it is stated here.

**The strip of the old copy is GATED on the link existing.** A top-level law file inside a skill directory is reloaded across compaction, and this file's predecessor was one — that is how the contract survived compaction before this carve. So the old copy may be reduced to a pointer ONLY once the new home is linked and the link resolves. Otherwise the carve silently costs the contract its reach across compaction: a regression delivered by the fix. Sequence: pair written → link resolves → then the pointer.
