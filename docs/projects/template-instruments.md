<!-- Landed from the session plan for plan 2646d31a (2026-09-26), so the phases exist
     outside the session. The archive carrying the superseded designs is
     ~/.opencrabs/profiles/ops/projects/meta-factory/files/template-instruments-project.md -->

# Template instruments — full set, distribution, lifecycle, promotion

**Status:** LANDED 2026-09-26 — phases A–E designed, and their implementation steps executed
as plan 2646d31a's checklist: steps 1–15 landed, step 16 reverted with its reason recorded,
and this file is step 17. The session plan it was written in stays archived with the profile.
**Author:** meta-factory HQ
**Asked by:** owner, 2026-09-25, in his stated order: codify what a template instrument's full set consists of; how to share it and what rests where; how to update it and whether meta-factory collects member feedback; how a member instrument is promoted to cross-factory status; and only then, review and fix the ledger and questions implementations.

**This document supersedes the three designs previously in this file.** Each is folded into the phase it belongs to. Their verbatim text and measured evidence are archived in the durable project doc (`projects/meta-factory/files/template-instruments-project.md`), **not on this card** — the rich card is sent whole with no budget, so a document that carries the superseded half renders it to the reader as current.

| previous design | now |
|---|---|
| Multi-factory questions pages (one page per factory) | **Phase E.4** — a surface, not an instrument |
| Fleet kit adoption (classify the manifest; member-side pin) | **Phase B** — the distribution model |
| Instrument adoption member→template (rename, review, reconcile) | **Phase D** — the promotion path |

## Context

**Problem:** Instruments reach member factories by copying files, and four things are uncodified — what a copy must contain, how it is shared, how it is updated, and how a member's better implementation becomes the template's.

**Target state:** An instrument is a defined full set carrying a version; distribution is declared per file class; updates travel a named channel with a feedback loop; promotion has stated criteria.

**Intent:** A factory cannot silently diverge from a file it is meant to share, and a member's better implementation can become the template's — by mechanism, not by discipline.

Every figure below was verified first-hand this session.

| measurement | value | what it proves |
|---|---|---|
| drift over the ten files `BOOTSTRAP.md` 4c names, five factories | **1 same / 20 DIFF / 29 ABSENT** | the copy model does not converge |
| ports after five member replies, each with reasoned per-file decisions | **0** | reporting is not enforcement |
| ledger gates the kit ships | **6** | — |
| ledger gates `BOOTSTRAP.md` step 4b names | **2** | the entry path installs a *partial* instrument |
| member ledger gate sets | **2 / 2 / 1 / 0** of 6 | a function of *when* they copied, not of care |
| member ledgers verifying clean | **4 of 4** (34 / 101 / 426 / 468 rows, `rc=0`) | adoption *succeeded* at the storage layer — which is why nobody escalated |
| version identifier in `tools/ledger.py` | **0 hits** | a member cannot tell its copy is old |
| members exposing `repair` | **3 of 4 lack it** | §11's own remedy is unavailable to them |
| instruments promoted member→template to date | **0** | no promotion path exists |
| the kit manifest itself | **4 of 106 entries wrong** at birth | the reference rots as silently as the copies |

**Two findings shape everything below.**

1. **A partial copy reads as adopted.** The tool works, so the gap is invisible — a factory running the instrument with half its gates reports exactly like one running it whole.
2. **The biting dependency is temporal.** The gate set grew *after* each factory copied: `test_ledger.py` appeared 09-12, `test_ledger_identity.py` on 09-25. A factory bootstrapped 09-12 got one gate; one bootstrapped today gets six. A copy has no update path.

## Terms — codified before the design uses them

The owner asked for better names and terms, so the vocabulary is fixed first and each term states what it is **not**. Three defects found this session were *vocabulary* defects: "instrument" meaning a file, "adoption" meaning a copy, "audience" declared on services while the load sits on lanes.

| term | definition | is **not** |
|---|---|---|
| **instrument** | the unit of adoption: everything one tool needs to work in a tree | a single file — this understatement is what let a partial copy read as adopted |
| **full set** | the nine parts in Phase A | "the script plus whatever it imports" |
| **executable** | the runnable entry point inside an instrument | the instrument |
| **closure** | everything a tool needs that is not the tool. Measured on `tools/ledger.py`: 67,382 B alone, **243,559 B across 7 files** — the tool is **27.7%** of what it needs. It is **not a flat set — it is two tiers**, and the tier that fails silently is **3.7x larger** than the tier that fails loudly: **HARD** (top-level import — `ledger_declaration`, `field_predicate`, `reconstruction`, 37,372 B): a missing one raises `ModuleNotFoundError` at import, which is the `#137` finding; **LAZY** (imported inside a function and caught — `registry`, `telemetry`, `registry_render`, 138,805 B): a missing one does **not** crash, it degrades to a *message*, and the message blames the **data** rather than the missing file. `ledger.py:519` is the specimen: a missing `telemetry.py` sets `extract_task_telemetry = None`, and the code's own comment reads *A telem of None is NOT an empty measurement: it is the extractor saying it has NO WINDOW BASIS* — so the factory's ledger runs green and reports no window basis forever, indistinguishably from a genuine one | a shared library — a closure is *specific* to its parent |
| **class** | `standalone` \| `closure` \| `seed` — the per-file predicate the manifest lacks today | a directory or a naming convention |
| **call site** | a place that invokes the instrument; **mandated** (a gate must register it) or **recommended** (a lane may use it) | documentation |
| **extension point** | a declared seam a factory may fill without editing the instrument | a fork |
| **fork** | a declared, dated divergence recorded in the factory's own data | drift (undeclared divergence) |
| **promotion** | moving an instrument member→template, with a name, a review and a migration population | copying it in |
| **census** | a published, per-factory measurement a plan can be corrected against | a patrol log line |

## Phase A — what a template instrument's full set consists of

### A.0 — the measured before-state: what a full set is TODAY

The nine parts below are the target. What exists today is thinner, and it is measurable.

**15 tools ship in `TEMPLATE/tools/`.** Against **four declared surfaces** — a gate at `TEMPLATE/tests/test_<stem>.py`, a BOOTSTRAP mention, a SKILL/processes mention, a `kit.json` entry:

| coverage | tools | which |
|---|---|---|
| **4 of 4** | **2** | `ledger.py`, `registry.py` |
| 3 of 4 | 4 | `audit.py`, `field_predicate.py`, `patrol_host_state.py`, `registry_render.py` |
| 2 of 4 | 6 | `brain_metrics.py`, `gate_budget.py`, `hygiene.py`, `registry_attest.py`, `review.py`, `roadmap.py` |
| 1 of 4 | 3 | `ledger_declaration.py`, `reconstruction.py`, `telemetry.py` |

**`kit.json` is the only surface all 15 carry.** So the manifest is today the *de facto* definition of a shipped instrument, and the other three surfaces are optional in practice — which is precisely the gap this project closes.

**The predicate must travel with any figure quoted from this section.** The Delegate's independent census over the same 15 tools measured **3 of 15 at 4/4** against my **2**, and our terminology counts also differ (`port` 50 vs 81). Different surface definitions give different numbers and neither is wrong, so a figure lifted from this document without its predicate is unreproducible — the class the repo already rules on elsewhere.

The owner named three parts: script, docs, call sites. Measured against the defects in Context, **six more are load-bearing**, and each is here because something already failed without it.

| # | part | the measurement that forces it |
|---|---|---|
| 1 | **executable(s)** | the owner's "script" |
| 2 | **closure** | `tools/ledger.py` imports three modules; a bare copy dies at import — the `#137` finding |
| 3 | **gate set + registry entries** | the ledger ships 6 gates and step 4b names 2; a partial copy reads as adopted |
| 4 | **version identifier** | 0 hits in `tools/ledger.py` — why staleness stayed invisible until the manifest landed |
| 5 | **docs** — the BOOTSTRAP step, the SKILL clause, the methodology entry | the step that installs the ledger names a subset of what it installs |
| 6 | **call sites**, classified mandated vs recommended | a gate never registered never runs; a lane never told never calls |
| 7 | **data surfaces** — what ships as `.example` vs what the factory owns | exemptions, event set, actors: the factory's declarations, never overwritten by an update |
| 8 | **self-probe (non-vacuity)** | this repo's own pattern: a gate that has only seen good input has not been shown to bite |
| 9 | **update path + feedback channel + promotion criteria** | Phases C and D — an instrument with no update path is the temporal defect above |

**The owner's three are parts 1, 5 and 6.** So "maybe something else?" answers yes: six things, and none is speculative — each is named by a defect that has already happened here.

### A.1 — the completeness rule

An instrument is **complete** when all nine parts are present in the adopting tree. Two mechanisms make that checkable, and both are owed today:

- **the version identifier** (part 4) — absent, which is why a member cannot tell its copy is old;
- **a gate-count census** (part 3) — the measured member sets are 2/2/1/0 of 6, and nothing reports it.

**And completeness must be declared, not derived, because the closure's lazy tier is invisible to both a test suite and a static walk.** Two measured proofs: (i) an `ast` walk finds `ledger.py`'s five local imports but is **blind** to both hooks' dependencies, which are loaded from string constants through `importlib` (`commit-msg:121`, `pre-commit:175`) — it would report a hook complete while it cannot run; (ii) the lazy tier is reached only on a code path the **fixture** deliberately skips (`ledger.py:163`, *lazy: a fixture append must not pay for it*), so a factory can run its whole gate set green while missing 138,805 B of what it needs. A green suite is therefore **not** evidence that a closure is present.

### A.2 — names and terms

Three naming criteria, stated before any analysis so that a "keep" is as defensible as a change:

1. **Simpler** — the fewest words that still disambiguate. Worked example: `rework_entries.py` names the output, `rework_table.py` names the object; the module parses a table and exposes entries by name, so the object name is both higher-fidelity *and* simpler — both criteria agree, which is the case where a rename is not owed.
2. **Non-conflicting** — measured against a fleet-wide census, never this repo alone: no two different instruments may share a name or near-name across the six trees, and no name may shadow a stdlib module. Live instance: a stray `/tmp/struct.py` broke a `ctypes` probe this session — that failure lands far from the file that caused it.
3. **Higher-fidelity** — the name states what the instrument **is** or **does**, never where it came from and never an abbreviation only its author recognises.

**The terminology before-state, measured** (law corpus, this repo, one predicate — see the warning in A.0): `template` 723 · `binding` 394 · `pair` 270 · `hook` 247 · `add-on` 73 · `twin` 68 · `addon` 65 · `port` 50 · `plugin` **1** · `vendor` **0**. Two facts fall out: **`pair` (270) and `twin` (68) name the same relation**, so the project must pick one; and **`add-on` (73) / `addon` (65) are already split across spellings** — a naming defect that exists today and that any canonisation should fix rather than inherit.

**The naming question, now ruled (owner, 2026-09-25).** The template's `tools/` uses bare nouns (`ledger.py`, `audit.py`, `hygiene.py`) while the skill repo uses an `oc-` prefix (`oc-questions`, `oc-ledger`, `oc-drift-check`). An instrument adopted **into** the template **drops the prefix** — `questions`, not `oc-questions`. This reverses my own recommendation, and the ruling is the better reading: criterion 2 (non-conflicting) is satisfied by the fleet-wide census rather than by the prefix, and the fleet-generic-vs-factory-specific distinction the prefix was carrying is now carried by the **`class` field** (B.1). A prefix is a namespace; a class is a predicate.

### A.3 — a plugin / add-on system?

The question is whether an instrument should declare **hook points** rather than being copied whole. Measured: the seams already exist and are already used — they are simply not named as such.

| seam | where it is used today | what it buys |
|---|---|---|
| gate registration | `tools/audit.py` gate list, `tests/gate_registry.py` | a factory adds gates without editing the runner |
| field predicates | `field_predicate.py` (`declared_outcome`, `declared_duty`, `declared_keys`) | one predicate, many readers — the `#143` remedy |
| event set | the ledger's `EVENTS` tuple | a factory adds `ack` without forking the tool (inferhub's case) |
| exemption data | `docs/ledger-*-exemptions.json`, `registry/kit-exemptions.json` | a factory declares a deviation without touching source |
| hook installation | `tests/hook_installation.py` | a factory installs a hook its own way |

**Verdict: do not build a plugin loader.** What a loader would add is *discovery* — a declared manifest of seams — and that same value is available from part 7 of the full set plus the naming rules, at a fraction of the cost. A loader also creates a second dispatch path beside the gate registry, which is the duplication §11 forbids. **The discipline owed is naming the seams that already exist, not inventing a container for them** — recorded so the question is answered rather than deferred.

**The add-on system already exists, and instruments are not in its taxonomy.** `docs/addons.md` (+ a byte-identical TEMPLATE twin, `cmp rc=0`) defines **two classes** — `Binding` (what substrate the factory runs *on*: exactly one of each kind, mandatory) and `Domain` (what the factory *does*: zero or more, composable) — across `docs/addons/{surface,harness,domain}/`. Every pack is **markdown**; no pack ships a script.

So the owner's plugin question has **no existing home to extend**. It is either a third class (`instrument`) or a new axis beside the two, and that is a design decision this phase must *make* rather than inherit. It does not change the verdict above — a *loader* is still not owed — but the five seams need a declared home if they are to be discoverable at all.

## Phase B — how to share: what rests where, who may modify

### B.1 — classify before comparing

`registry/kit.json` is 106 flat `path → sha256` entries with **no per-file class**, so a factory's own gate list is scored as drift against the template's. Four of five forks are deliberate and reasoned, and the current figure both overstates the problem and cannot be acted on per file.

The three classes (see Terms): `standalone` — byte-identical everywhere or a finding; `closure` — travels with its parent; `seed` — never compared, and the template ships an `.example`.

### B.2 — what rests where

| surface | owner | why |
|---|---|---|
| the instrument's source | **template** | one upstream; a factory edit makes the update path impossible |
| its gate set | **template** | the invariants are not factory opinions |
| its version | **template** | generated from the manifest, never hand-set |
| its declarations | **factory** | exemptions, event set, actors — data, not source |
| its call sites | **factory** | which gates it registers, which lanes it obliges |
| its fork declarations | **factory** | a dated reason, in the factory's own registry fragment |

**Where the set physically rests — measured, and it is not one directory.** A transitive walk of `tools/ledger.py` returns **7 files / 243,559 B, every one under `tools/`** — including `registry_render.py`, which arrives through `registry.py` rather than directly. So the **code half is already single-dir**. The **full set spans four roots**, by convention rather than accident:

| part | rests at | why there |
|---|---|---|
| tool + closure + `hooks/` | `tools/` | one dir, already |
| the gate set — 6 gates, 152,586 B | `tests/` | the audit runner discovers gates by convention |
| the hooks' predicates | `tests/` | `commit-msg:121` / `pre-commit:175` load them from string constants |
| data surfaces | `tools/actors.txt` · `evidence/ledger.jsonl` · `registry/gates.json` | one per surface, root-anchored |

So the distributable unit is **not a directory inside the root — it is the root plus a declared set of destinations.** Two consequences the design must carry: (i) a single-dir port today is **incomplete**, because both hooks resolve their predicate from `tests/` and degrade to a warning when it is absent — the silent-incompleteness class this project exists to fix; (ii) moving the gates under a kit directory would **dissolve `#162`** (the gate resolves `REPO=parent.parent` with no override, which is why opencrabs-dev's split repo can run it in neither tree) — but that changes how the audit runner discovers gates, so it is a decision, not a tidy-up. See Owner decision 5.

### B.3 — are factories allowed to modify?

Three answers, and the taxonomy *is* the answer — "may they modify?" is unanswerable as one question:

| class of edit | verdict | mechanism |
|---|---|---|
| the executable or a shared module | **no** | the update path breaks the moment two trees hold different source |
| a declaration (exemptions, event set, actors) | **yes, expected** | factory data, never overwritten by an update |
| a fork of the source | **yes, with a declaration** | recorded with reason and date; the census reports it as declared, not as drift |

**Measured precedent that this works:** miidas reports the `commit-msg` port as "cheap here" *because* the exemption path is factory data rather than source — and inferhub's `ack` event is a legitimate fork that a faithful copy would destroy (5 of 7 ack probes red against 8 live rows).

### B.4 — the distribution model

Seven options were analysed in the superseded design 2; the verdict stands.

| # | option | verdict |
|---|---|---|
| 1 | status quo — report only | **insufficient** — 5 replies, 0 ports |
| 2 | **member-side gate on a vendored pin** | **recommended** |
| 3 | member-side gate on the *live* manifest | **rejected** — couples a member's verdict to our working tree |
| 4 | shared checkout / symlink | **rejected** — four of five forks are legitimate |
| 5 | submodule / subtree | **rejected** — disproportionate to four factories |
| 6 | generated copies + overlay | **deferred** |
| 7 | **classify the manifest first** | **precondition** |

The pin is the load-bearing choice: the factory vendors the manifest at the version it ported and gates against **its own** declaration, so a member's verdict depends on its own tree and never on ours.

**There is no delivery leg, and that is the gap under this phase.** Measured over the law corpus: `drift` 14 mentions, `vendor` **0**, `re-sync` **0**, `propagat` **0–1**. `kit.json`'s keys are `_note`, `kit_version`, `file_count`, `files` — a **manifest, not a channel**. So the kit can tell a member it has drifted and has **no mechanism to hand it the update**. The pin in option 2 makes the *verdict* self-owned; the **transport** — how a factory actually receives a ported file — remains unbuilt, and is owed by this phase rather than by the patrol leg that reports drift.

### B.5 — expansion and hook-in opportunities

Answering the owner's question directly: **yes, and the design already owes them.** The five seams in A.3 are the hook-in surface, and part 7 of the full set is what makes them declarable. What is *not* owed is a container — see A.3.

### B.6 — the entry path must be fixed first

A new instrument delivered by a doc step **inherits** every defect in that step. Confirmed first-hand: step 4b names **2 of the 6** ledger gates it installs, so a factory following it exactly still carries four unenforced invariants — corroborated independently by the census (2/2/1/0).

Three entry-path defects block any new adoption:

- **#155** — 4c names 2 of the 7 paths its own gate needs; followed literally, it dies at import.
- **#164** — the template ships a schema gate that REDs on an absent ledger (fixed, closed 13:33:11Z).
- **#162** — the gate resolves one root with no override, so a split-repo factory cannot run it in either tree.

## Phase C — how to update, and the feedback loop

### C.1 — the version identifier

The instrument carries a version, **generated from the manifest and never hand-set**. Measured today: `grep -cE 'VERSION|__version__' tools/ledger.py` = **0**, so a member cannot tell its copy is old — which is why the whole staleness went unmeasured until `kit.json` landed and the patrol leg followed.

### C.2 — the pin, and the "behind" report

The factory vendors the manifest at the version it ported; its own gate reds on undeclared divergence from **its own** pin (B.4 option 2). The patrol's kit-drift leg stays as level 2 and reports "behind" per factory — advisory, no gate.

### C.3 — the update act

**Who runs it:** the factory, not us. **What it costs:** measured this round — five replies, each naming what it would and would not port, and for four of five the honest answer was "not yet, and here is why". So the update path must support **deferral as a declared state**: "behind by N, deferred because X" is recorded by the census, rather than a red gate that teaches lanes to ignore red.

**What travels:** an update is a **port**, not a copy — three steps measured in `#137`: the file, its closure, and a per-factory decision. A factory whose `ledger.py` is self-contained has no closure to bring, and the closure requirement **travels with the file, not with the name** (infra-factory's correction, and inferhub's is the counter-case: its `ledger.py` carries the template's three imports).

### C.4 — should meta-factory collect feedback from members?

**Yes — and the shape is already proven, not proposed.** This round produced five replies, each with per-file decisions and measured evidence, and **three of them found defects in our own reference**: the manifest was stale from birth (4 of 106 entries), the shipped `pre-commit` hook was unportable as written, and a SAME file was mis-attributed across two factories. A feedback loop that catches our own defects is not a courtesy — it is a mechanism.

The instrument: the **census artifact** (correction ii), published per round, recording each factory's declared decisions. A member's deliberate absence is a **declaration**, recorded and distinguishable from silence.

**Cadence:** ride the existing patrol round. Do not add a second schedule — the box-wide 6 h floor binds, and a second pacemaker for the same duty is the duplication §11 forbids.

### C.5 — retirement

An instrument that stops being maintained is retired by an **explicit act**, never by neglect. The `#144` precedent: the declaration, its reader, its gate, its exemption files and its boundary were retired **together**, and the dead references were recorded rather than left behind. A retired instrument's references in durable artifacts are a reader hazard and are named — that is the `#96` lesson, where two rework entries pointed at deleted paths.

## Phase D — how to promote a member instrument to cross-factory status

### D.1 — the candidates, measured

| member instrument | template counterpart | relationship |
|---|---|---|
| miidas `tools/rework_entries.py` | `tests/rework_table.py` | same module arrived at independently — **different name AND different directory** |
| miidas `tools/subject_law.py` | none | repo-qualified subjects (`#28`); no template equivalent |
| ai-antispam `tools/audit.py` yield fix (`#38`) | `tools/audit.py` | member is **ahead**; the template still lacks it (`#143`) |
| miidas `gate_budget.py` verdict half (`#42`) | `tools/gate_budget.py` | member has the verdict half, the template has the manifest half; **neither has both** |

#### D.1 verdicts — the three criteria applied, measured 2026-09-25

Each verdict names the criterion behind it, and a KEEP is recorded rather than omitted.
Criterion 2 is settled by `tools/kit_names.py` (the fleet census), never by this repo alone.

**1. `rework_entries.py` → RENAME to `rework_table.py`** (criteria 1 + 2 + 3, all agreeing).
Measured: the two files expose the SAME concepts under three identical names
(`is_header`, `is_separator`, `entry_rows`) and each carries a different superset —
miidas has `count_entries`, `stray_entry_rows`, `cells_of`; the template has
`column_index`/`column_cells`, the column-**by-name** reader miidas's own report says it
lacks. So it is ONE instrument arrived at twice. On criterion 3 the module's own docstring
says it "owns the SHAPE of the entries table" — the object name is more faithful than the
output name, and A.2's worked example reached the same conclusion. On criterion 2 the
census counts `rework_table.py` in **two** trees (inferhub-watch, meta-factory) against
`rework_entries.py` in one, so adopting the majority name removes a name rather than
adding one. **The directory differs too** (`tools/` vs `tests/`) — that is a placement
question (Phase B), not a naming one, and it is NOT settled by this verdict.

**2. `subject_law.py` → KEEP** (criterion 3; criterion 2 raises a near-name to resolve).
It names what it is — the law of subjects — in two words, and no shorter name
disambiguates it from `test_subject_form.py`. **And it is the most valuable promotion
candidate in this list for a reason that is not naming:** its docstring records the same
collision ruled here this morning (`ledger-subject-board-collision`), and it ENFORCES the
fix by making the repository part of the subject (`<owner>/<repo>#<n>`), refusing a
foreign-repo subject on write and flagging it at `verify`. That is strictly stronger than
the ruling I gave, which said a board lookup "can't close it" because a row records a
number and not which board — miidas removed the ambiguity at the SOURCE instead of
checking for it. **Criterion-2 near-name to resolve, named rather than left:** ours is
`test_subject_form.py`, which validates the FORM and states no board lookup exists. They
are adjacent, not the same instrument — but a reader meeting both should be told which
answers which, and that is a D.2.3 review item.

**3. the ai-antispam `audit.py` yield fix (`#38`) → KEEP the name; the FIX travels.**
Criterion 2 measured: `audit.py` is carried by five trees under two declared purposes at
0.667 overlap, which the census reads as a FORK and not a conflict — the same instrument,
differing by design. So there is no naming question here at all: the promotion is a fix
into an existing instrument under its existing name, which is why this candidate is the
one where D.2.5 (second vs replacement) is the whole decision.

**4. the `gate_budget.py` verdict half (`#42`) → KEEP the name; the SHAPE is the question.**
Measured, and it corrects the candidate as stated: **miidas carries no file named
`gate_budget.py`** — the census finds that name in meta-factory only. miidas's verdict half
lives INSIDE `tools/audit.py` (`GATE_UNKNOWN_EXIT_CODE`, `run_gate(budget_sec=...)`,
`outcome=unknown`). So this is not two names for one instrument but one instrument SPLIT
across two shapes: the template has it as a module, the member has it as a section of its
audit runner. Criterion 3 favours the module name — it states what the thing is — and the
migration question is therefore which SHAPE wins, not which word.

### D.2 — the criteria

Five, each resting on evidence already in hand:

1. **Arrival evidence** — built independently by **two or more** factories, or one factory is demonstrably **ahead** of the template on a template instrument. The miidas rework case is the first shape (same defect, same fix, arrived at independently, under a different name); the ai-antispam yield fix is the second.
2. **Naming** — the three criteria in A.2, applied against a **fleet-wide** census.
3. **Review** — code **and** law, by a subagent scoped to the template's copy (D.3).
4. **Migration population named** — who must change, and what breaks if they do not.
5. **Second vs replacement stated** — does it replace a template instrument or add one? (Correction iv; renaming is orthogonal to this.)

### D.3 — the review protocol

One subagent per instrument, scoped to the **template's** copy and the template's law. It must read both; name every assumption the member's tree made that the template does not; and produce either a landed fix or a **recorded non-fix with its reason**. The member already reviewed its own copy — re-reviewing that is duplicated work.

### D.4 — promotion is not adoption

A promotion lands the instrument with its **full set** (Phase A), its **class** (Phase B), its **version** (Phase C) and its promotion record. The contributing member becomes the **evidence**, not automatically the upstream — unless D.2.5 says the template's copy should be replaced by theirs outright.

## Phase E — the reviews and fixes (only after A–D)

The ordering is the owner's and it is load-bearing: the review needs the vocabulary (Phase A), the placement rule (Phase B) and the naming criteria (Phase D). Running it first is what produced three separate designs that had to be re-framed.

### E.1 — ledger instrument review

`tools/ledger.py` + `ledger_declaration.py` + `field_predicate.py` + `reconstruction.py`, against §11, §12 and `docs/processes.md`. The review's own test: this session changed the actor path (now derived from `OPENCRABS_SESSION_ID`), the settlement receipt (now the tool's, not the author's) and the authorization matrix (now enforced at the write path) — so the law and the closure are re-read against the code **as it now stands**, never as it stood at dispatch.

Known inputs: the `#139` fourth class (the delivered form can never satisfy the receipt predicate — both forms are daemon-produced, so the fix is in the reader); the `#144` retirement; and the write-path/repair gap (3 of 4 members expose no `repair`, so §11's own remedy is unavailable to them).

### E.2 — questions instrument review

`oc-questions` (skill repo: `~/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/`), the register clause added to §11, and the per-factory page design (E.4). Known inputs: the Toolsmith's four clarify defects and the four law candidates (E.3). This is also where the naming question is unavoidable — an `oc-*` name landing in a tree that does not use the prefix.

### E.3 — the four law candidates

- **(a)** a state transition must carry the content that justifies it, or be refused.
- **(b)** every state a machine can enter must be distinguishable in the surface the human reads.
- **(c)** an error path must be rendered by the surface that triggers it.
- **(d)** a field written but never read is a record that can only lie.

**(d) generalises furthest**, and it already has two independent instances found in one day: `answer_kind` (cleared by `amend` but never read by the builder) and the `outcome=` field the Worker measured as dead code on real receipts (`#160`).

### E.4 — per-factory questions pages

Superseded design 1, kept in full in **Appendix A**. The load-bearing finding stands: the change is small because **three surfaces need no edit** — `backend.py`'s `token_meta` already reads `PAGES_DIR/<token>/meta.json`, the Caddyfile already serves any single-segment slug, and the push already rsyncs the whole tree. What changes is the publish loop, the pointer, the reader — and the slug pinning is **deleted rather than generalised**, because its only purpose was keeping one shared path from moving.

### E.5 — the corrections already established

The five corrections from the Delegate's adoption census are folded into the phases rather than restated: **(i)** define the instrument and make completeness a close condition → A.1; **(ii)** ride the existing leg and publish a census artifact → C.4; **(iii)** fix the entry path before adopting anything new → B.6; **(iv)** state second-vs-replacement and name the migration population → D.2; **(v)** the questions instrument is a landing already carrying defects → E.2 and E.3.

## Risks and what could break

| risk | mitigation |
|---|---|
| The classification is a judgement call | derived from BOOTSTRAP's existing ships / created-here column, and the manifest gate makes a missing class a red |
| The pin itself goes stale | one file, and its staleness is **visible**; the patrol reports "behind" — a smaller and louder failure than silent file drift |
| A factory with no pin gets a permanent SKIP | the guard names the absence in the gate's own output, so an absent pin cannot read as clean |
| Members legitimately fork and the gate punishes it | the exemption surface is factory **data** — measured to be exactly what made the `commit-msg` port cheap for miidas |
| Renaming churn | every verdict records "keep" too; the criteria are stated before the analysis, not after |
| The subagent review duplicates the member's own review | scope is the template's copy and law, never the member's tree |
| The review finds a defect in an instrument already shipped to five factories | it routes as a kit defect and ships through the same adoption path — the loop this design closes |
| Second-writer hazard | `tools/oc-questions` is dirty from another lane (mtime 13:20:49Z); every implementation step re-checks the tree first |
| The project is too large to land in one plan | the phases are independent and each carries its own close condition; **Phase E does not begin until A–D are approved** |

## Owner decisions (ruled 2026-09-25)

1. **Three classes or two? — RULED: declared, and now PROVEN rather than preferred.** `closure` is declared in the manifest, never derived from the import graph. The proof is a measurement: a static `ast` walk of `tools/ledger.py` finds its five local imports, but the same walk is **blind** to both hooks' dependencies — `tools/hooks/commit-msg:121` and `tools/hooks/pre-commit:175` load their predicates through `importlib.util.spec_from_file_location` from a **string constant** (`GATE_RELATIVE`, `PAIR_TABLE_RELATIVE`). A derived walk would report a hook **complete** while it is missing the file it cannot run without, and the hook degrades to a warning — the silent-incompleteness class this project exists to fix. Declaration is the only form that cannot miss it.
2. **Does the `oc-` prefix survive adoption into the template? — RULED: no.** Adopted instruments **drop the prefix**. See A.2.
3. **Does an adopted instrument keep its contributing factory's name? — RULED: yes.** When the contributing name is already the better one, the template adopts it — which makes the template's naming a **result** of the census rather than a convention imposed on it.
4. **Where are the questions pages linked from? — RULED: the register index** (accepted). A card per topic is rejected: the register clause exists because per-lane pings are the load problem, not the solution.

5. **Single-dir distribution, or root-plus-destinations? — OPEN.** Measured: the code half is **already single-dir** (7 files, every one under `tools/`), while the full set spans four roots by convention. Option (a): declare the **root** as the unit and keep the layout — cheapest, leaves `#162` standing. Option (b): move the gate set and the hooks' predicates under a kit directory, making one dir portable — this **dissolves `#162`** (the gate would resolve its root from its own location rather than `parent.parent`), but it changes how the audit runner discovers gates. My reading: **(b) for the hook predicates** (a two-file move that removes a real defect — a hook that cannot load its predicate degrades to a warning), **(a) for the gates** until the runner's discovery is itself in scope. Neither is built.

## Implementation steps

1. **Classify the manifest.** Add `class: shared | closure | factory` per file, derived inside `tools/kit_manifest.py` from an explicit table in that file — never hand-edited into `kit.json`. Done when `python3 tools/kit_manifest.py --check` exits 0 and all 106 paths carry a class.

2. **Give every shipped instrument a version identifier**, generated from the manifest rather than hand-set. Done when `tools/ledger.py` prints its version and the manifest records the same string.

3. **Fix the entry path — `BOOTSTRAP.md` step 4b.** It names 2 of the 6 ledger gates it installs. Done when a clean fixture bootstrapped from 4b passes the full six-gate ledger set.

4. **Fix step 4c's seven-path list (`#155`) and carry the class per file.** Done when a clean fixture bootstrapped from 4c runs its own gate, and each named path states whether it ships or is created here.

5. **Complete the four declared surfaces** for all 15 shipped tools, or declare per tool which surfaces are optional and why — derived from the A.0 coverage table. Done when a re-run of the A.0 census reports every tool at 4 of 4 or carrying a declared exemption, and the census predicate is printed with the figure.

6. **Ship the vendorable pin** (`TEMPLATE/registry/kit.json`) carrying the classes. Done when a fixture factory can vendor it and its gate resolves against that copy rather than against ours.

7. **Build the delivery leg** — the transport that hands a factory an update, which does not exist today (`vendor` 0, `re-sync` 0). It must move source + closure + gate set as one unit and never overwrite a factory's declarations. Done when a fixture factory at an older kit version receives an update, its own gate goes green, and its declaration files are byte-unchanged.

8. **Add the member-side gate** `tests/test_kit_pin.py` — red on undeclared divergence from the factory's **own** pin, with `registry/kit-exemptions.json` declaring forks, and an absent pin SKIPping behind a named vacuity guard. Done when the gate is green here and its mutation control bites.

9. **Publish the census artifact** from the existing kit-drift leg, recording each factory's declared decisions. Done when the leg's output lands as a dated artifact a plan can be corrected against.

10. **Build the fleet-wide name census** across the six trees. Done when it reports, per candidate name, which trees carry it and whether any two carry different instruments under one name.

11. **Canonise the terminology** using the A.2 before-state: pick one of `pair` / `twin` for the byte-identical relation, and one spelling of `add-on` / `addon`. Done when the chosen term is used in the law corpus and the rejected one appears only in historical records.

12. **Decide the add-on taxonomy** — whether an instrument becomes a third class beside `Binding` and `Domain`, or a new axis. Done when `docs/addons.md` states the decision and its TEMPLATE twin is byte-identical.

13. **Apply the three naming criteria to the four candidates in D.1**, recording "keep" verdicts as well as renames. Done when every candidate carries a verdict with the criterion behind it.

14. **Ledger instrument review (E.1)**, subagent-scoped to the template's copy and law. Done when every factory-specific assumption is removed or declared, and the law matches the code as it now stands — including the derived actor, the tool-owned settlement receipt, and the write-path matrix.

15. **Questions instrument review (E.2)** including the four law candidates (E.3). Done when each clarify leg is fixed or recorded as a non-fix with its reason, and the instrument has landed in the template under its ruled name — `questions`, with no prefix (owner decision 2).

16. **Per-factory questions pages (E.4).** Done when each factory renders its own page, the served pages carry only their own sets, and the slug pinning is deleted rather than generalised.

17. **Land this document as a durable project doc** in the repo once approved. Done when the phases exist outside the session plan. The superseded designs are already archived beside it (`projects/meta-factory/files/template-instruments-project.md` — the full document, appendix included), so landing is this card's text copied next to that archive.
