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

### 2.1 The extension surface — there is none, and §2 is the reason

**This instrument has no extension surface: member subject matter lives outside it** (frame §6.5).

A **declared** state, not an omission, and decidable from this file rather than from taste. §6.5's
contract has four parts, and its **first requires a SHIPPED half** — the specimen's
`TEMPLATE/docs/ledger-refs-kinds.example.json`, declaring nothing, with the factory-owned
`docs/ledger-refs-kinds.json` beside it. **This instrument ships no declaration path at all:** §2's
set is the executable, its render asset, its gate and this file. So there is no shipped half to
declare into and no adopter to hold one, and arm (a) is unavailable here while §2 stands — not
merely unchosen.

Three measured facts close the doors a member would otherwise take:

- **The vocabularies are CLOSED CONSTANTS in the one writer.** A question's `kind` is `single` or
  `multi` and nothing else: the write path refuses any other value **by name**, and those same two
  values are re-read by every consumer that cares — `list` counts a multi question's answers, the
  renderer picks checkbox against radio, `amend` re-resolves a recommendation against it. `--via`
  (`card` · `page` · `cli`) and `--mode` (`turn-end` · `interrupt` · `quiet`) are closed the same
  way. **No declaration file is folded into any of them**, so a member's own value cannot land at a
  point the reader accepts: it would be an edit to the executable — a **fork** by §6.5's test, since
  it changes the shape on a path, and §6.4's tier that refuses.
- **A member's subject matter lands as the SUBJECT, never as a vocabulary.** The instrument is
  domain-agnostic by construction: a question is a title, a Markdown description (tables and Mermaid
  supported) and an optional option list, so a factory's own subject matter needs **no** shape change
  in order to be asked. What a member supplies is *what a question is about*, and none of it is
  folded into how the instrument reads.
- **The one place a member's own LOGIC is needed is already a CORE field, not a declaration.** A
  member that needs its own closure condition passes it to `close_when`, which the instrument's
  single closure reader runs. That field takes a VALUE — a predicate — and names nothing the
  instrument then accepts: it can be neither promoted nor shadowed, which is why it is a core field
  and not an extension surface under §6.5's four-part contract.

**Where a member's subject matter goes instead.** Nowhere new: into the register as its own questions,
read identically for every factory that asks. A member that needs an addition to the instrument
ITSELF — a third question kind, a different answer control — has one path and it is not a private
one: frame §5's promotion, the same route that promoted this instrument.

**A parameterised PATH declares no vocabulary.** `OC_QUESTIONS_DIR` and its siblings point the
instrument at another store, another render asset or another gateway; that changes *which* questions
it holds and *where* the page is written, never what a question may say. Aiming the instrument at a
file is not a way to declare into it.

**The member's duty is CITED here, not authored** (frame §9). **O1 has an object here** — this
instrument ships four paths, so a member holding a divergent copy owes a disposition
(migrate / declare / defer), declared on its own fragment, `registry/factories/<slug>.json`, on this
instrument's axis `instruments.open-questions`; §5.4 governs the member leg. **O4** applies as §6.5
states it — declare what its instrument accepts, or state why it has none — and for this instrument
the answer is the paragraph above, because there is no vocabulary to declare.

---

## 3. The lane-side contract

> **Re-homed verbatim, with FIVE departures carried INTO the text rather than appended:** the page-URL mechanism (§4, corrected from the tool rather than from either prose), one pinned line citation de-positioned per §5.5, the source's own heading demoted so it sits under this section, and the page-model clause corrected a SECOND time when the two-address split landed (2026-09-28) — the instrument now publishes an aggregate plus a page per factory, so the clause's "ONE page directory serves every set" was falsified by the change and is stated below in its current form. Everything else below is the source's wording. (The FIFTH departure, added the same day: the clause's lane-anchor sentence is qualified to say the anchor resolves only while that lane has an open question — an all-answered lane renders no section.)

### Open Questions register — the sanctioned "blocked on you" channel (owner-commissioned 2026-09-24) [LANE]

The owner cannot see which lane is blocked on him: a parked decision exists only as prose in that lane's own topic, with no aggregate, no ordering by age, and no one-tap answer. The Register is the fix; this clause is the lane-side contract.

- **Register in the same turn you park.** A lane whose next action needs an owner decision calls `oc-questions ask` in the SAME turn it stops, naming itself and its ordered question set. A prose "blocked on you" line in the topic is NOT a registration — nothing aggregates it.
- **The Register is the ONLY sanctioned blocked-on-you channel.** Do not open a parallel mechanism, and do not re-ask in the topic on a daily clock once registered: the register's `asked_at` age is what re-surfaces a question, so a repeated topic ping is noise rather than pressure.
- **Each question has exactly two required inputs:** `title` and Markdown `description` (tables and Mermaid supported). A question MAY carry `options[]`, a `recommended` default, and a Clarify action; a free-text answer is always available, and Clarify never silently closes the question.
- **The asking session id comes from the ENVIRONMENT, never typed.** `ask` reads `OPENCRABS_SESSION_ID` — the id the daemon set for the calling turn. It must never be replaced by a cron session, a renderer session, or another lane, because a substituted id orphans the answer. **`--lane` is REMOVED (owner order 2026-09-25):** the lane is resolved BY THE TOOL from the asking session's own binding (`session_bindings` → `chat_id` + `thread_id` → `channel_messages.topic_name`); `sessions.title` is deliberately NOT used, because it carries auto-generated titles for some lanes.
- **The return address follows the UNIT, not only the ask.** The clause above governs what happens AT ASK TIME; a unit that changes hands AFTER its question is registered is a separate hazard, and it has already bitten. So **a re-route dispatch carrying an open question MUST carry that question's current state (asked / answered / hold) in the dispatch body** — a hold addressed to a lane that no longer holds the unit is not a hold the actor received. The durable fix is a tool change: the return address follows the unit's **live claim holder** rather than the asking session (routed to the Toolsmith, `tools/**`); until it lands, the dispatch-body leg is the binding one. Origin, verified on the store rather than recalled: set `ffbfa5` recorded session `c78e78e0`, q2 answered *"Hold — keep the global freeze"* at 22:20:29Z, the unit was then re-routed to `a5b34466`, and that lane filed upstream PR #1732 at 22:53:42Z — **33 minutes after the hold, never having received it**. The destination was CORRECT for the asker and WRONG for the actor, so the hold was not disobeyed; it was addressed to a lane that no longer held the unit. (Triage, 2026-09-27.)
- **The return address selects QUESTIONS, never SETS.** A standing factory set is created once by one lane and then asked into by MANY, so a filter that compares the SET's session against the caller compares the CREATOR against the caller: it shows every other lane ZERO of its own questions, and shows the creator questions it never asked. Both directions are the same defect, and `list --session` carried it until 2026-09-28. The consequence is what makes it worth this bullet: `list` is how a lane checks *"have I already asked this?"*, so a lane that saw zero filed a DUPLICATE and put two questions for one issue on the owner's page — the register reported an empty patch of itself, which reads exactly like having asked nothing. Any verb that filters by the return address filters PER QUESTION, falling back to the containing set's session only when the question carries none of its own. (Fork #632.)
- **A role the law names but nobody staffs is a LAW defect, not one lane's problem.** The editor clause in `SKILL.md` ends an editor's obligation at smoke evidence and hands census, porting, PR filing and upstream lifecycle to the **HARVEST lane**, and `harvest.md` names that lane as the actor for every harvest step. Measured 2026-09-27: **0 harvest lanes exist** — `roster --live` tallies editor 31 · triage 2 · toolsmith 1 · hq 1, and the four apparent harvest rows are editor enrolments whose **feature string** merely contains the word. So the law created an obligation no lane can discharge, while the work runs under editor enrolments that the same clause forbids. **When the owning role is vacant, the work PARKS on the register with the vacancy named as the blocking condition** — never silently assigned to the nearest idle lane, and never left as *"an editor has taken work it does not own"*. Staffing the role is the owner's call; recording the vacancy here is what stops the next lane re-deriving it from scratch.
- **ONE standing set per FACTORY (owner order 2026-09-25).** `ask --factory <KEY>` is REQUIRED, and the factory key IS the standing set id — created on first ask and REUSED, so a factory accumulates its questions in ONE set at 0..N rather than minting a one-off container per call. An **unbound** session is REFUSED non-zero: it can never receive the answer, so it must not register a question at all.
- **The page URLs are CONSTANT and READABLE (owner order 2026-09-25; split 2026-09-28).** Both orders are cited here, not authored. There is no rotating token. A set's page is its OWN factory slug, so a lane's link is `/` + the factory key it asked under — and this IS assembled from the factory key now, which is the opposite of what this clause said before the split, because the path is no longer shared: each factory has its own directory, so a factory-key path resolves to that factory's page rather than to a page named after whichever factory the pointer happened to carry. The **union** lives at the neutral `/all/`, reserved so no factory can take it. `pages/latest.json` records the aggregate. Each lane also gets a **stable anchor** — its page's URL plus `#lane-<lane-slug>` — so a lane can be handed a link that lands directly on its own questions. (Qualified 2026-09-28: that anchor resolves while the lane has an OPEN question. An all-answered lane renders no section — see below — so such a link lands on a page that no longer carries the block. The page ADDRESS is what is permanent; a lane section is not.) The pages group by LANE and show a per-lane open count.
- **Decisions are collected on the PAGE, not from card buttons (owner order 2026-09-24).** Cards with tappable buttons are RETIRED: a tap is dropped while the target session is mid-turn (#553, closed not-planned), so the page is the single aggregate surface. `ask` returns the open-question TOTAL and no card. The page posts each decision back to the lane that asked, resolving the destination from the REGISTER by set-id — never from the request body, so a crafted POST cannot redirect an answer.
- **A Clarify is a request, and the lane owes an amendment.** Clarify never closes a question: its status becomes `clarifying` and the asking lane is notified. The lane MUST then `amend` it (revised title / description / options), which returns it to `open`. A clarifying question left unamended dead-ends the loop and the owner never sees the answer.
- **Closure is mechanical wherever it can be.** Beyond an explicit answer or withdrawal, a question closes when the thing it asked about has moved: a named fork issue reading CLOSED closes it as `resolved_mechanically`, and an explicit `close_when` predicate closes on rc=0. An unreadable predicate prints a SKIP note and closes nothing — never a silent close. Silence is still not an answer.
- **The page is re-rendered on every register mutation** — a new question, an answer, a clarify, an amendment — so it is never stale. The twice-daily cron sweeps expiry and mechanical closure; it is NOT the refresh path.

Store: `~/.opencrabs/profiles/ops/questions/open.json`, with answered sets archived to `archive.jsonl` and the rendered pages under `pages/<factory-slug>/` plus the neutral `pages/all/` aggregate (correction in §4). Tool: `skills/opencrabs-dev/tools/state/oc-questions` — verbs `ask` · `answer` · `amend` · `notify` · `list` · `publish` · `lint` · `gc` (Toolsmith, `tools/**` carve-out); its path law is §5.1, because the path is resolved at call time rather than assumed. Fork issue #547 carries the build. Live pages: the neutral aggregate, plus each factory's own (lane anchors `#lane-<lane-slug>`).

## 4. The page URL — corrected from the tool, and whose law it is

The re-homed contract above states the page URL law. Its **mechanism** was wrong in the source, and it was wrong in the one direction that reaches the owner: a lane following it assembles a URL from its own factory key and hands the owner a dead link.

**The correction, read from the tool rather than from either prose.** The slug is the value recorded in `pages/latest.json` on the first publish and REUSED from then on; the tool reads that pointer BEFORE it consults the register, and the register supplies a slug only when no pointer exists yet. So ONE page directory served every set, and the URL was per-INSTRUMENT rather than per-factory. Measured 2026-09-27: the page directory held ONE entry while the pointer's own `sets` list named three, so two of the three sets had no directory of their own to be served from. Three surfaces agree — the tool's own slug function, the pointer's own content, and the `oc-questions` row of `RC-CONTRACT.md` — and the two that disagreed were the two PROSE statements. That is why this correction is derived from the tool.

**SUPERSEDED 2026-09-28 — the single page is now TWO ADDRESSES, and the conflation this section recorded is resolved.** The paragraph above described the model that stood until the owner ordered the pair: the union had no address of its own, and it was served from whichever factory's name the pointer happened to carry. `/all/` is the union's address now, and every factory has its own. The section is kept because the DERIVATION still governs — the page model is read from the tool, never from prose — and because the pointer-first paragraph is the record of what was being corrected. See §4.1.

**Classification, per clause** — frame §8's split: authorship of a law doc is delegable, authority over a clause that binds a member factory is not.

| clause | class | consequence |
|---|---|---|
| the URL is constant and readable, no rotating token (owner order 2026-09-25) | **AUTHORITY** — cited, not authored here | unchanged; this file does not restate the order, it relies on it |
| the mechanism — the slug is DERIVED from the factory name, so it cannot churn | **INSTRUMENT LAW** — authored here, derived from the tool | §4.1; the pointer-first reuse it replaced is recorded above as superseded |
| the stable per-lane anchor | **INSTRUMENT LAW** — authored here | kept; expressed against the page's OWN URL (the factory slug, or the neutral aggregate) with `#lane-<lane-slug>` |

**No clause authored in this file binds a member factory.** Every clause above governs how this instrument behaves for the lane that invokes it; a member that adopts the instrument inherits that behaviour and takes on no new cross-factory duty. Where a clause would bind member factories it is HQ's, and is cited rather than authored.

### 4.1 The page model — TWO addresses: the neutral aggregate, and a page per factory

**This section states what must hold, never how it is drawn (owner order 2026-09-28).** The law carries the
properties the instrument must satisfy; the markup, the styling, the position and the element choices belong to the
code that implements them. A clause naming an idiom, an element, or a position is falsified the moment the rendering
is revised — one such clause in this file was written and falsified within hours the same day, which is the argument
for keeping them out rather than an inconvenience. What belongs here is the property a rendering must satisfy, and the
assertion that holds it.

The instrument publishes a page for the UNION and a page for each factory (owner order 2026-09-28, verbatim: *"Can we not conflate a factory name with an all questions at once tag?"*). The union had no address of its own: one page carried every factory's questions while being served from ONE factory's name, so the path named a factory and the content was the fleet. Now:

- **The aggregate takes a NEUTRAL constant slug, and it is reserved.** `/all/` carries every factory's open questions. `all` is a RESERVED word: a factory whose slug collides with it — or with another factory's slug — is REFUSED non-zero with BOTH names printed, and nothing is written. Two different objects must not share one directory, and publishing one over the other is the failure the refusal exists to prevent. Tested against a factory literally named `all`, one named `All` (which slugifies to it), and a `infra-factory` / `infra factory` pair that collide with each other.
- **Every factory the register NAMES gets its own page, carrying ONLY its own open sets.** The set's own `factory` field decides the path, never its position and never the pointer.
- **A factory page is minted even with nothing open, and it outlives its set.** The address is a permanent anchor: a page that existed only while questions did would 404 the moment they were answered. Names are drawn from EVERY set the register holds, not only the open ones, so a factory that answered its last question keeps its address — and a page directory is never removed once written, because nothing sweeps a readable slug.
- **Each page's `meta.sets` is its OWN, and the two sides are asserted to agree.** The answer backend accepts a posted set only if that page's own meta lists it, so a card shown under an unlisted set is silently unanswerable. The selftest reads the containment from both directions — the sets the page's cards belong to, and the sets its forms post — against that page's meta, so the property is enforced rather than assumed.
- **Every page is rendered BEFORE any is written.** A renderer fault must leave no half-made directory behind and must leave the previous pages serving, so one bad page cannot leave the others half-live.
- **The pointer names the AGGREGATE.** With a page per factory there is no single "the" page, and the union is the address that stays put no matter which factory moved. `latest.json` therefore records `{"slug": "all"}`.
- **The slug is DERIVED, not stored.** A slug derived from the factory name cannot churn when a set is added or removed: adding a question to one factory cannot move another's path. That is the stability the retired mint-per-publish token and the single reuse-pointer both existed to provide, held here by construction instead of by a recorded value.

The remaining bullets below are the single-page rules that survive the split, PLUS the page-shape orders that followed it, with every rule a later order supersedes marked as such.

- **The title names the SUBJECT, never one factory.** The page is titled `Factory Open Questions (N)`, N being the count of open questions SHOWN. The title previously interpolated the pointer's slug, so a page carrying four factories announced itself as one of them — the owner read a single factory's name over a fleet-wide page. A title derived from a path is a claim about the path, not about the content.
- **The count describes what is SHOWN, and is computed after the filter.** A total taken before narrowing prints a fleet figure beside a filtered view — the same mis-scope that once reached `--json` as a filtered lane list beside an unfiltered total.
- **The per-factory filter is a VIEW, never a partition.** Narrowing what the reader sees must never change what the page carries or what can be answered: every question the page holds stays answerable whichever view is in force, and how the narrowing is drawn is the code's affair. (The per-factory DIRECTORY added 2026-09-28 is an ADDRESS, not a partition of the filter: the filter still narrows whatever page it is on, and the aggregate keeps every factory's sections for it to narrow.)
- **The page works with scripting disabled, and the default view hides nothing.** A reader without scripting must meet the whole page rather than a dead control. That property is asserted, not assumed.
- **The selector names each factory's OPEN COUNT (owner order 2026-09-28).** The reader sees what is waiting per factory before choosing one. The figure is taken from each CARD's own `set` field, never from the span of sets its whole lane block covers: one lane block can span several sets, and a section-level tally would credit every factory in the block with all of the block's cards. The fixture asserts the discriminating case — a lane shared by three factories, where a section-level count reads three for each and the card-level count reads one — rather than a convenient one.
- **A lane with nothing open is not shown (owner order 2026-09-28), which SUPERSEDES the earlier rule that an all-answered lane kept its block.** That rule existed so a handed-out lane anchor kept resolving, and its cost was a page of blocks reporting "0 open" — the reader meets the PAGE. The distinction is now explicit: the page ADDRESS is permanent (a factory page is minted even with nothing open, above), while a lane's block exists only while that lane has an open question. A register with nothing open at all falls to the typed empty state rather than to a screen of blocks reporting nothing.
- **Every card is attributable to its OWN factory from the page as rendered (owner orders 2026-09-28, narrowed 2026-09-30).** The aggregate mixes every factory, so a reader meeting a single card must be able to tell which factory asked it. The 2026-09-28 ordering put the name on the CARD and required the property independently of the lane block; the 2026-09-30 order moved it back to the block, so the card now carries its OWN facts — its age and its `qid` — and the factory is stated on the lane block's own heading, because the heading and the selector both name it already and a card repeating them said it twice. WHERE the name sits inside that model is the code's choice; the law holds the property and the assertion that keeps it honest — the check COUNTS the factory tag against the sections, and a second arm holds the negative half (no question heading may carry it), so a move can never pass as an addition. A page-level substring satisfies neither.
- **Every address the owner already holds keeps serving.** The orders that pin a factory set's page ADDRESS as permanent are cited here, not restated: `/opencrabs-dev/` still resolves, and it now carries that factory's own questions. The aggregate is a NEW address rather than a rename of an old one, so the split adds links without breaking any.
- **The page's NAME is never a factory; and as of the split, neither is the page's ADDRESS (owner question 2026-09-27, resolved 2026-09-28).** A factory name on a page is a VIEW TAG: it labels a filter control and it names the sets of the sections that control scopes. It is not the page's name: no factory name identifies the page, so the reader is never told a page IS one factory. Until the split, a factory name still identified the page in ONE place — the PATH — because the union was served from whichever factory the pointer carried; that was recorded here as "the instrument's one remaining conflation, deliberately left standing rather than silently renamed", on the ground that an address which misleads is a reason to change the ADDRESS. That change has now been made: the union moved to the neutral `/all/`, and `/opencrabs-dev/` narrowed to its own factory's questions. **No path names the fleet after one factory any more**, and every address the owner already holds keeps serving — the per-factory paths are the same readable slugs, and the aggregate is an ADDITION rather than a rename.
- **The page carries no statement of its own permanence (owner order 2026-09-27).** The shell used to assert one — a property the register already holds — as the first thing the reader met. It is gone. The page's `expires_at` stays in the page META, which is where the answer backend reads it from; permanence is a property of the register, never a line of page furniture.
- **The lane's counsel reaches the reader, and the option it names stays selected (owner orders 2026-09-27 and 2026-09-30, which pulled in opposite directions).** Two properties are asserted rather than assumed — the counsel is present as text the reader meets, and the recommended option remains pre-selected. HOW it is drawn is the code's business (§4.1), and both orders are recorded because a reader holding one alone would re-derive the other as a defect: the 2026-09-27 order revealed the counsel behind a native control whose label had to be real text, and the 2026-09-30 order removed the control so the counsel renders directly — which returns the label to generated content. A rule that cannot render reads as live, so each order's superseded mechanism was DELETED rather than left beside its replacement.
- **A clarifying question is compact and stays answerable (owner order 2026-09-27).** A `clarifying` question is waiting on the LANE — the lane owes the amendment that returns it to `open` — so it is not waiting on the reader and must not occupy an actionable question's space. It is shown compactly rather than removed, and it stays answerable: its form remains in the document with the inputs the answer backend reads, so revealing it answers it. The reveal is native and needs no script.

### 4.2 The `--set` contract change

`publish` no longer accepts `--set`. It is REFUSED non-zero with the reason named: `publish` builds every page — the aggregate and one per factory — so a narrowing flag has nothing to address. A caller wanting one factory's questions goes to that factory's own page, or to the filter on any page carrying its sets, never to a narrower publish.

**Why removed rather than kept.** The flag was the mechanism by which the published page could be narrowed to a single set, and narrowing STRANDS the sets it excludes: the answer backend validates a posted set against that page's own recorded set list, so an excluded set's open questions become unanswerable from the page that serves them. A flag whose use can silently strand an owner decision does not belong on the publish path. **The split does not reinstate it** — the per-factory pages come from `page_targets`, which partitions the REGISTER rather than the published output, so no set is excluded from the pages that must carry it.

`--set` remains the ADDRESSING flag on the set-scoped verbs; only `publish` loses it.

### 4.3 The addressing key — `qid`

Every question carries a **`qid`**, and it is the key a consumer must address it by.

- **Stamped at ask time, never re-derived.** It continues the standing set's own numbering, so it is unique within the set and stable across every later mutation — an answer, a clarify, an amendment, a withdrawal. Nothing renumbers it: a new question appends, and a withdrawal sets a status rather than removing the row.
- **`--qid` is its flag.** The set-scoped verbs address a question by `--qid`; the set itself is addressed by `--factory`.
- **Do not reach for `id`.** The set-level field is `id` and it names the SET, so a consumer who reads the law and reaches for the question's `id` gets a missing key — and a missing key reads exactly like an absent value. Stated because it has already happened: a peer enumerated the question object, read `id`, found nothing, and reported that questions carry no identifier at all, while `qid` was present on every row. The failure is silent in both directions and cost a full round.

### 4.4 The question model — how many options an answer may carry

A question **declares how many of its options an answer may carry**, and that declaration is `kind`: `single` or `multi`. **The control the reader sees is the code's business, not this file's** (owner order 2026-09-28); what is law is the count, and that a reader can tell which applies before answering.

- **Question-level, and fixed at ask time.** The count is a property of the QUESTION, not of an answer and not of the page, so it is declared once, where the options are declared. An answer cannot widen it — the same rule that keeps an asker from setting the wrong subject (the `--subject` refusal).
- **Absent means one.** A question that declares nothing takes a single option. This is the rule that lets every question registered before this field existed keep working unchanged: nothing is reinterpreted, and a default is never guessed from the shape of an answer.
- **A refusal, never a truncation.** An answer carrying more options than the question allows is **refused**, naming the question and the count it got. Taking the first of several and reporting success is the silent-drop class this instrument exists to remove: it records something the reader did not say.
- **A multi answer is recorded as the list of chosen options, in the order chosen, and says so.** `answer_kind` distinguishes one label from several, so a consumer never has to infer the cardinality from the option set — the same reason the delivery stamp exists: a state must be readable, not inferred.
- **A multi question with nothing to choose between is refused at ask time.** It is a question no reader can answer, and registering it puts one on the owner's page.
- **The act is the same however the choices are spelled.** Several of them, one per value or joined into one, are one act with one meaning.

### 4.5 The recommendation — named, never counted

A question MAY carry a recommendation, and a caller names it **the way the owner will read it** — by label or by option letter. **The stored value is an index and stays one**, so no question already registered is reinterpreted; only the INPUT is widened.

- **A caller is never made to count.** Forcing an asker to compute an array position is the failure this rule removes: the asker holds the option's NAME and has no reliable way to turn it into a 0-based offset without counting, and a miscount is silent because the index is in range.
- **It costs a cycle when it goes wrong, and the cost is borne by the owner.** Measured: a lane passed the index meaning "the first option" while its own prose said the option's letter, so both questions stored the SECOND option and the owner's page pre-checked the answer OPPOSING each question's own text for over four hours. The lane's own amendment is the evidence.
- **The instrument's own round-trip check cannot catch this class**, and that is the reason for the rule rather than a note about it: an index round-trips correctly through storage while meaning the wrong thing, so the defect is invisible to a check that compares what was stored to what was sent.
- **The resolution is ECHOED, read back from what was stored.** An asker who named a label must see which option it became, and the echo proves the RECORD rather than restating the intention — the same principle as the delivery stamp (§5.7).
- **An unmatched name is REFUSED, naming the options.** Never a fall-back to an index and never a guess: silently choosing is how a wrong answer is recorded as a delivered one.
- **A bare letter matches the OPTIONS' OWN leading letters, not alphabet position.** The two differ the moment a set is labelled X/Y rather than A/B, and the alphabet mapping refuses input that is perfectly well-formed.

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

Every copy named in this file MOVES — one of them moved twice while this file was being written. So no clause here may pin a byte size, a digest, or a line number of any copy. Derive a boundary at run time from heading text rather than from a remembered position, and state the PROPERTY that must hold — the closure is two files, exactly one CLI resolves, every page's `meta.sets` covers the cards it renders — never the measurement that happened to hold at writing time. (The properties named here have themselves been corrected once: this clause used to require that "the pointer is read first", which the 2026-09-28 split made false. A property list is a claim about behaviour and goes stale the same way a number does.)

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

### 5.7 Delivery is a separate fact from the answer (#Triage q7)

**The register can be complete and a lane still be blocked.** Recording an answer and delivering it are two acts: `answer` records, `notify` delivers. The store held the answer's state and nothing about its delivery, so a question read `answered` while the lane that asked had never seen the reply — and no surface, machine or human, could tell the two apart. That is the shape where a state is enterable with no reader and no representation, so its absence is invisible from the machine's own side.

**The duty: whoever delivers records the attempt.** `notify` stamps the outcome and the instant on every question its body carried, and the outcome distinguishes delivered from refused from unreachable. A consequence is not a receipt — the same split the ledger keeps between an attestation and the thing it attests.

**A delivery that FAILED must be recorded as failed, not omitted.** An exit code reaches the caller that ran the verb and nobody else; the register is what a later reader has. So a failure is stamped as loudly as a success, and the transport failure has its own value rather than borrowing an HTTP code it never received.

**An answer with no stamp reads as NOT RECORDED, and that absence is PRINTED rather than omitted.** Every answer recorded before this duty existed, and every answer a lane recorded without notifying, is in exactly that state; suppressing it would restore the ambiguity the stamp exists to remove.

**`answer` does NOT notify, and must not grow the duty.** Two distinct failures would then ride one verb, and every caller that already notifies would deliver twice. This is the same separation the ledger's write path keeps, and for the same reason.

**Bound: the stamp covers the LIVE register.** A set that has been archived carries its questions in the archive, which is history and is not rewritten to record a delivery — rewriting history to close a gap is worse than the gap. A question in the archive therefore still reads without a delivery record, and that is a stated bound, not an oversight.

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
