# Template instruments — the cross-instrument law

**Owns:** the definitions that bind **every** template instrument — what an instrument is, the full
set that makes one complete, its class, its name, how it is promoted, distributed and versioned.
**Writer:** the Instruments-methodology lane. **Authority:** cross-factory clauses (any rule binding
a member factory) and the process law *about* instruments are **RETAINED BY HQ**; this file cites
them and never restates them.

A per-instrument law file cites this one and never restates it. Restating is how one definition
becomes two, and two definitions drift.

This file ships: it is the template half of a pair, byte-gated by `tests/test_docs_sync.py`, hashed
by `registry/kit.json`, and symlinked into the skill tree so it survives compaction (see §6).

---

## 1. What an instrument is

**An instrument is the unit of adoption: everything one tool needs to work in a tree.** It is
**not** a file. That understatement is what let a partial copy read as adopted.

**It is a DECLARED object, and nothing in this repo declares one yet.** Measured 2026-09-27: no JSON
or Python file records an instrument together with its file set — `instrument` appears as a declared
grouping in **zero** files. The class exists by usage, not by declaration, so the declaration form
is fixed here. An instrument is declared by its own law file, which names at minimum:

| field | what it answers |
|---|---|
| **name** | what the instrument is called (§4) |
| **executable(s)** | what a caller runs — part 1 of the full set |
| **closure** | what the executable needs but is not — declared, never derived (§1.1) |
| **gate set** | which gates must register it, and where |
| **version source** | where its version identifier is read from (§7) |
| **data surfaces** | what ships as `.example` versus what the factory owns |

A reader holding the law file and the tree can answer *"is this instrument complete here?"* without
enumerating imports.

### 1.1 Completeness is declared, never derived

Two measured proofs, both load-bearing:

- A static `ast` walk finds `tools/ledger.py`'s five local imports but is **blind** to both hooks'
  dependencies, which are loaded from **string constants** through `importlib`
  (`tools/hooks/commit-msg:121`, `tools/hooks/pre-commit:175`). It would report a hook **complete
  while it cannot run** — and the hook degrades to a warning rather than an error.
- The closure's **lazy tier** is reached only on a path the fixture deliberately skips
  (`ledger.py:163`), so a factory can run its whole gate set **green** while missing 138,805 B of
  what it needs.

**A green suite is therefore not evidence that a closure is present.** A factory can hold a complete
instrument and a factory can hold a green one; they are different facts, and only declaration
carries the first.

### 1.2 The two-tier closure

The closure is **not a flat set — it is two tiers**, and the tier that fails *silently* is the
larger one. Measured on `tools/ledger.py`: 67,382 B alone, **243,559 B across 7 files** — the tool
is **27.7 %** of what it needs.

| tier | load | files | bytes | failure when absent |
|---|---|---|---|---|
| **HARD** | top-level import | `ledger_declaration`, `field_predicate`, `reconstruction` | 37,372 | `ModuleNotFoundError` at import — fails loudly (the `#137` finding) |
| **LAZY** | imported inside a function, caught | `registry`, `telemetry`, `registry_render` | **138,805** | **degrades to a MESSAGE** that blames the DATA, not the missing file |

`ledger.py:519` is the specimen: a missing `telemetry.py` sets `extract_task_telemetry = None`, and
the code's own comment reads *"A telem of None is NOT an empty measurement: it is the extractor
saying it has NO WINDOW BASIS"* — so the ledger runs green and reports no window basis forever,
indistinguishably from a genuine one. **The silent tier is 3.7× the loud one**, which is why the
class (§3) is a predicate over files and not a directory convention.

### 1.3 An instrument's executable may be SHARED — and then the closure widens

**An instrument does not own its executable exclusively, and the frame must never require an
instrument to be splittable.** Python gives one file: a runner that feeds several duties' predicates
cannot be divided into "just this instrument's part", so a member may not take a fragment of it.

**The consequence is a rule, not a caveat: when the executable is shared, the closure is declared
over the WHOLE executable, and the declaration states the boundary.** Declaring only the
instrument's own legs produces a closure that is complete on paper and crashes in the tree.

Measured on the first instrument to hit this (`pacemaker`, 2026-09-27): its executable
`tools/patrol_host_state.py` is a multi-leg runner carrying the cron-thinness, notify-receipt and
duty-receipt legs among eight, so its closure of six modules is **wider than its own legs**. Its
owner declared the boundary as it is rather than tidily — the behaviour this section exists to make
legal, because the alternative is the tidy lie.

**A shared executable is a declared fact, never a defect.** What the declaration owes is that a
reader can see the boundary: which legs this instrument owns, and which other duties share the file.
A second instrument built on the same runner declares the same executable and its own legs, and the
two closures overlap by construction — which is correct, and is why the closure is declared rather
than derived (§1.1).

### 1.4 The declared set — membership from what the executable LOADS, the class from the manifest

A declared set derived from the manifest's **classes** under-declares by exactly the paths the
executable reaches **indirectly**. Measured 2026-09-27: `pacemaker.md` §2 declared nine paths and the
true set was eleven — `tests/ledger_boundary.py` and `tools/ledger_declaration.py` are reached by a
path constant (`patrol_host_state.py:91`, loaded at `:1188`) and by `ledger_boundary.py:69`'s own
import, and both are manifest rows of class `closure`. The kit shipped them, so membership was never
declared because nothing asked for it. A member holding the declared nine read **HELD — complete
set — while unable to run at all**, and the defect was in the declaration, not the tree.

**Derive membership from what the executable LOADS:** every REPO-relative path constant it reads,
and every module it imports, transitively. **Let the manifest supply each path's CLASS, never its
MEMBERSHIP.**

### 1.5 The declaration's coordinates — a set a reader cannot find is not declared

The declared set lives in the law file's **§2**, as numbered rows pairing the member path with its
template counterpart, so a reader derives it without a second list to drift. That placement is a
**coordinate**, and a machine reader that assumes it must report when the coordinate is empty instead
of returning a shorter set. Measured 2026-09-27: a census requiring the paired-row form in §2
published two instruments and **refused three** — `kit.md`'s §2 is a one-sided table, `ledger.md`'s §2
is the write-path identity law, `open-questions.md`'s §2 is the lane-side contract. Three refusals,
three different objects, none an omission.

**An aggregate reports the inputs it refused, by PATH, in the artifact a reader meets.** A short list
and a wrong list are otherwise indistinguishable, and a refusal nobody reads is a silent coverage
gap — the same family as a count published without its predicate.

## 2. The full set — nine parts

An instrument is **complete** when all nine are present in the adopting tree. The owner named three
(script, docs, call sites); measured against defects that have already happened here, **six more are
load-bearing**, and each is present because something failed without it.

| # | part | the measurement that forces it |
|---|---|---|
| 1 | **executable(s)** | the owner's "script" |
| 2 | **closure** | `ledger.py` imports three modules; a bare copy dies at import (`#137`) |
| 3 | **gate set + registry entries** | the ledger ships 6 gates and `BOOTSTRAP.md` step 4b names 2 — a partial copy reads as adopted |
| 4 | **version identifier** | 0 hits in `tools/ledger.py` — why staleness stayed invisible until the manifest landed |
| 5 | **docs** — the BOOTSTRAP step, the SKILL clause, the methodology entry | the step that installs the ledger names a subset of what it installs |
| 6 | **call sites**, classified mandated vs recommended | a gate never registered never runs; a lane never told never calls |
| 7 | **data surfaces** — `.example` versus factory-owned | exemptions, event set, actors: the factory's declarations, never overwritten by an update |
| 8 | **self-probe (non-vacuity)** | a gate that has only seen good input has not been shown to bite |
| 9 | **update path + feedback channel + promotion criteria** | §5 and §7 — an instrument with no update path is the temporal defect |

**Parts 4, 7, 8 and 9 are the ones instrument owners most often omit**, and they are the ones this
law defines cross-instrument precisely so each owner does not coin their own: see §7 for 4 and 9.

Coverage today is measurable and thin: of **15 tools** in `TEMPLATE/tools/`, against four declared
surfaces (a gate, a BOOTSTRAP mention, a SKILL/processes mention, a `kit.json` entry) — **2 at 4/4**,
4 at 3/4, 6 at 2/4, 3 at 1/4, and **`kit.json` is the only surface all 15 carry**. The manifest is
therefore today the *de facto* definition of a shipped instrument. **Any figure quoted from this
section must travel with its predicate**: an independent census over the same 15 tools measured 3/4
at 4/4 against these 2, on different surface definitions. Neither is wrong; a figure lifted without
its predicate is unreproducible.

## 3. The class — one predicate per shipped file

Every shipped path carries a class, and **a path without one is a failure, not a default**. The
three classes are the manifest's own (`registry/kit.json`), defined and enforced by
`tools/kit_manifest.py`; this section states what they *mean to an instrument* and does not restate
their implementation.

| class | meaning | what its ABSENCE means |
|---|---|---|
| `standalone` | a standalone instrument — a tool you run | the factory is **BEHIND** |
| `closure` | a module with no interface of its own, present only to be imported | the factory ported its parent **without its closure**, so the parent is **BROKEN at import** |
| `seed` | a seed the factory instantiates under a different name | **not applicable** — never compared byte-for-byte |

**The class is DECLARED per path, never derived from the import graph**, and §1.1 is the proof.
`standalone` is the **residual** — `classify()` returns it for anything not in a declared set — so a
NEW file is never silently unclassified, and a new `.md` under the shipped docs tree takes
`standalone` with no declaration authored.

**Two rules an instrument owner inherits from this, both measured:**

- **A pin travels with its reader.** `TEMPLATE/tools/kit_pin.py` is `closure` and its test is
  `standalone`; a member that takes the pin without the reader holds *a file nobody reads*.
- **Markdown is exempt from the runnable arm** (it guards on `.py`), so a law doc can be
  `standalone` without an entry point — but a `standalone` **`.py`** the kit cannot run by any of its
  three mechanisms is refused. A new closure silently classed `standalone` is what that arm exists to
  catch.

## 4. Names

Three criteria, stated **before** any analysis so that a "keep" is as defensible as a change:

1. **Simpler** — the fewest words that still disambiguate. Worked example: `rework_entries.py` names
   the *output*, `rework_table.py` names the *object*; the module parses a table, so the object name
   is both higher-fidelity and simpler — both criteria agree, and a rename was still owed.
2. **Non-conflicting** — measured against a **fleet-wide** census, never this repo alone: no two
   different instruments share a name or near-name across the trees, and no name shadows a stdlib
   module. A stray `/tmp/struct.py` once broke a `ctypes` probe — the failure lands far from the file
   that caused it.
3. **Higher-fidelity** — the name states what the instrument **is** or **does**, never where it came
   from and never an abbreviation only its author recognises.

**Adopted instruments DROP the `oc-` prefix** (owner ruling 2026-09-25): `questions`, not
`oc-questions`. The prefix was carrying a fleet-generic-versus-factory-specific distinction that the
**class field now carries** — a prefix is a namespace, a class is a predicate. The skill repo keeps
its `oc-` names; the template's `tools/` uses bare nouns.

**An adopted instrument KEEPS the contributing factory's name when that name is already the better
one** (owner ruling 2026-09-25), which makes the template's naming a *result* of the census rather
than a convention imposed on it.

**A name is realised on FOUR surfaces, and each has its own reader** — so a name can be right on one
surface and wrong on another, and no single check sees both. Walk all four:

| # | surface | realised as | the mechanism that READS it |
|---|---|---|---|
| S1 | **declared name** | the instrument's name in its law file | the reader of the law, against the three criteria above |
| S2 | **file basename** | `tools/<name>.py` | the Python import machinery; `tools/kit_names.py` (fleet collision + stdlib shadowing); `registry/kit.json`, where the path IS the key |
| S3 | **path slug** | the law doc's filename, its pair, and the reload link | `tests/test_docs_sync.py` (the pair); `registry/kit.json` (path + class); the loader's `discover_aux_files`, which reads top-level `.md` and excludes `SKILL.md`, `README.md`, `CHANGELOG.md` |
| S4 | **published slug** | a URL segment, for an instrument that publishes a page | **the pointer** — the tool reads `pages/latest.json` BEFORE it consults any register, so a slug is READ from the pointer that owns it and is **never assembled from a factory key**: one page directory serves every set, and a path built from a key is a dead link for every factory except the one it happens to name |

**The law slug and the module basename may differ, and usually should:** a law file names the
INSTRUMENT; a module is one executable inside its file set. Each surface is checked against the
mechanism that reads it — never against a hand-written example of the URL.

## 5. Promotion — the owner's law

**Owner order, 2026-09-27, in three clauses, and they bind every promotion:**

1. **Canonical location inside the repo.** When a tool or instrument is promoted to the template,
   its canonical location must be inside `agent-factories`. There is no canonical copy outside it.
2. **The pieces move to the template.** The existing pieces of the future template bundle are moved
   into the template — a promotion that lands only the new file and leaves the old one live has
   created two homes for one thing.
3. **The donor factory migrates to the promoted shape.** The contributing factory then migrates to
   the shape of the instrument it contributed. **This is a migration, not a copy** — and where the
   donor's copy is already byte-identical to the promoted one, the migration is
   **declaration/shape, not a content move**. Measured on the questions instrument: all three of its
   files are byte-identical between `TEMPLATE/` and the donor, so nothing needs porting and scoping
   a port would be work with nothing to do.

### 5.1 The six promotion criteria

Each rests on evidence already in hand:

1. **Arrival evidence** — built independently by **two or more** factories, or one factory is
   demonstrably **ahead** of the template on a template instrument.
2. **Naming** — the three criteria in §4, applied against a **fleet-wide** census, and **the review
   is a CLOSE CONDITION**: the close row cites `naming=<artifact>`, and the artifact walks all four
   §4 surfaces with the mechanism that reads each. A naming review that leaves no file is a review
   that did not happen, exactly as in criterion 3.
3. **Review** — code **and** law, **by a subagent scoped to the template's copy and the template's
   law** (the requirement and its reason are `review-lenses.md`'s *Adversarial Isolation
   Requirement* — the authoring lane suffers conversational self-confirmation bias and an isolated
   adversarial subagent does not; cited, never restated), and **the review is a CLOSE CONDITION,
   not a step.** A promotion's close row cites `review=<artifact>`. A step that leaves no artifact
   is a step that did not happen.
4. **Migration population named** — who must change, and what breaks if they do not.
5. **Second versus replacement stated** — does it replace a template instrument or add one?
6. **Vocabulary** — the instrument's names are read against `ONTOLOGY.md` before landing; every term
   it coins either exists canonically or earns a new row, and **no term it uses means two things**.
   **The review is a CLOSE CONDITION**: the close row cites `vocabulary=<artifact>`, and the
   artifact reports each term's senses and every collision it found. This is a criterion and not
   advice: the first vocabulary review, run over the kit's own classes, found **two false claims in
   `ONTOLOGY.md` itself**.

**Criterion 3 is gateable and the shape already exists** (`close_row_revision` is a declared
invariant with a boundary instant, read through `tests/ledger_boundary.py`); the gate lands with the
**first** promotion, because a gate over a population of zero is the speculative build KISS/YAGNI
forbid.

### 5.2 Two reviews per instrument, both scoped to the template's copy

- **Code and law** — read both, **by a subagent scoped to the template's copy and law** (the
  adversarial-isolation requirement is `review-lenses.md`'s and is cited, not restated here); name
  every assumption the member's tree made that the template does not; produce either a landed fix or
  a **recorded non-fix with its reason**. The member already reviewed its own copy; re-reviewing that
  is duplicated work.
- **Vocabulary** — read the identifiers and prose against `ONTOLOGY.md`. **Not optional, and
  measured:** `questions` was promoted into the template and shipped with **zero gates** — nothing
  named `test_*questions*` exists, and its only `tools/audit.py` appearance is the English word in
  three comments. Its verification is a `selftest` no gate invokes, so a green selftest is not
  evidence anything ran it. One review would have caught it; the vocabulary review would have caught
  it twice.

**The ontology-quality requirement binds the FILE, not only the review:** a per-instrument law file
states, for every term it uses, either the canonical `ONTOLOGY.md` row it resolves to or the row it
earns — and an **ambiguous term is reported as a defect in the ontology** rather than tolerated. A
term carrying two senses in the corpus is a defect wherever it is found, including inside
`ONTOLOGY.md` itself.

### 5.3 Promotion is not adoption

A promotion lands the instrument with its **full set** (§2), its **class** (§3), its **version**
(§7) and its promotion record. **The contributing member becomes the evidence, not automatically the
upstream** — unless criterion 5 says the template's copy should be replaced outright.

### 5.4 A promotion is verified against the donor's DATA, not only its code

The two reviews (§5.2) read the code and the law; neither reads the donor's records, and a donor's
records are a different question. Every promotion has a donor, and a donor's corpus carries shapes
the declared contract does not enumerate — so the promotion owes a **read-only replay over the
donor's own data**, and that replay finds a class of defect no review finds.

Measured 2026-09-27 on the review-rotation promotion (donor: opencrabs-dev). Predicate: the key
shape and the value set of every declared status field over the donor's cycle records. Scope: 17
`reviews/*/state.json`, 88 lens entries. Instant: 2026-09-27T17:06Z.
- cycle `status` carries **SIX** values: `COMPLETED` 9, `IN_PROGRESS` 4, `reports_persisted` 1,
  `intake_complete` 1, `VALIDATED` 1, `COMPLETE` 1.
- lens entry `status` carries **FOUR**: `COMPLETED` 66, `COMPLETE` 11, `PENDING` 7, `PERSISTED` 4.
- a lens entry has **THREE** key shapes — `(report_path, status, verdict)` 73, `(path, status)` 11,
  `(findings_count, report_path, status)` 4 — and `sha256` appears in **0 of 88**.

The declared contract enumerates none of it. All three defects the replay found were invisible to
reading the code: a render indexed an **absent field** directly and every migrated cycle died on its
first read; a terminal **synonym** (`COMPLETE` for `COMPLETED`) went unmapped; and the rest were
absorbed **silently**.

Two obligations, and they are what make a replay a verification rather than a demonstration:
- **An unrecognised value is MAPPED or NAMED — never absorbed.** A migration that is silent about
  the values it did not recognise publishes a clean migration over a lossy one, and from the
  migrated side the two are indistinguishable.
- **The replay READS the donor; it never writes into the donor's tree.** The donor-side change is
  the donor's own act in the donor's own tree (§6.1, O2).

### 5.5 A shipped gate judges the ADOPTER — its fixtures are read from the tree under test

An instrument's gate ships as a **byte-identical pair** (§6), and in the half that ships, "this
factory" is the **adopting member**, whose instants are its own. A fixture pinned to the *kit's*
instants, or to a *donor's* data, therefore asserts the wrong tree the moment a member adopts — and
it fails **silently in the donor's favour**: the donor's own tree is green throughout, so nothing
surfaces it until adoption.

Measured 2026-09-27 on the pacemaker instrument, rehearsed read-only against ai-antispam's
committed state (`82d233a`). Predicate: the instrument's own gate, run in the member's tree with the
shipped pair laid over it. Scope: 102 checks. Instant: 2026-09-27T17:2xZ.
- in the member's tree: **8 failed of 102** before the fix; **rc=0, 102 checks** after.
- in the donor half, which by design carries no pin: **14 of 102** read red for the kit leg's reason,
  and **13 of them cleared the moment a manifest pair was supplied** — so probes about the board,
  the cron leg and the duty leg had been measuring the kit leg.

Three root causes, all three in the gate and none in the member:
1. **Fixture data pinned to the kit's instants** — its duty boundary and its close-board anchor as
   literals, while the leg correctly reads the TREE's declaration. Two of the eight then read as
   *"a missing duty receipt never reached the report"*, when the member's cron row had fired before
   its own declared bound and been **correctly EXCUSED**.
2. **A probe driver that injected every dependency except two** the runner accepts as parameters.
3. **A runner that caught only `AssertionError`**, so a reader's declared skip escaped as a
   traceback — the gate's declared SKIP vocabulary invisible to the gate's own runner, which renders
   "nothing to judge" exactly like "a check failed".

Three clauses:
- **A shipped gate's fixtures are DERIVED from the tree under test**; the kit's values survive only
  as pre-adoption fallbacks. The **token is the convention; the anchor is the tree's data**.
- **A probe driver injects EVERY dependency the runner accepts** — a probe about one leg that was
  not given that leg's inputs becomes an assertion about another.
- **A runner honours the exception vocabulary its own readers declare.** A declared skip that
  reaches the runner as a traceback is the reader's contract ignored by its consumer.

The invariant behind all three: **an assertion must never report a verdict about something other
than the thing under test** — the defect class this instrument exists to kill, turned on the
instrument's own probes.

## 6. Distribution — where an instrument's law lives

An instrument's law file is **one artifact in two trees plus a reload path**, and all three are
required:

| role | path | held by |
|---|---|---|
| **canonical, shipped** | `TEMPLATE/docs/instruments/<instrument>.md` | the manifest (sha256 + class) |
| **repo pair** | `docs/instruments/<instrument>.md` — **byte-identical** | `tests/test_docs_sync.py` |
| **reload path** | `skills/meta-factory/<instrument>.md` — **relative symlink** into the template half | the loader, which follows symlinks |

**The reload row is META-FACTORY-SCOPED, and that is a deliberate limit rather than the whole
story.** The path is `skills/meta-factory/`, which is **outside `TEMPLATE/`** — and `TEMPLATE/` is
the manifest's entire population (predicate: the `files` map of `registry/kit.json`, grouped by path
prefix; scope: this repository; instant 2026-09-27T14:17Z — **131 of 131** entries under `TEMPLATE/`,
`skills/` = **0**. The figure this sentence first carried read **120 of 120**: it was correct for its
own instant, and it is superseded here rather than overwritten, because a count published without
its predicate, its scope and its instant goes stale silently). So the
reload leg is **not shipped and cannot be**: `kit_deliver.py` copies manifest paths
(`shutil.copyfile`) and creates **no symlinks by construction**, and no single manifest entry could
express it anyway, because a member's skill directory is named **per member**
(`skills/ai-antispam/`, `skills/inferhub/`, …). **A member that receives a law doc therefore holds a
COPY WITH NO RELOAD LEG until it creates one** — the law ships, and it does not survive that
member's compaction. §6.1 is the step that closes it.

**The reload path exists because law that does not survive compaction is not law.** Measured: the
reload scanner's location is **fixed** (`user_skills_dir()` resolves under the profile home; there
is **no** environment override — `OC_SKILLS_DIR`/`SKILLS_DIR` = 0 hits in source), so the scanner
cannot be aimed at a repo path. And the unit it scans is **a top-level `.md` inside a skill
directory**: `discover_aux_files` inspects top-level entries only, does not recurse, requires `.md`,
and **excludes `SKILL.md`, `README.md`, `CHANGELOG.md` and dotfiles**. A law file is therefore **a
plain `.md` and never a `SKILL.md`** — a second `SKILL.md` in that directory would be unloadable.

**The relative symlink is the whole point:** the containing directory is itself a symlink into the
repo, so `../../TEMPLATE/docs/instruments/<x>.md` resolves without an absolute path to break on a
move — and because the loader and the hashers both **read through** the link, the shipped half and
the reloaded half are **one inode** and cannot drift. Two paths, one file.

**How the doc actually survives compaction — two legs, and the second is why it must be READ:**
`memory_recall` indexes the auxiliary files of every **active** skill, so the doc is recallable with
no prior read; but re-injection into the prompt happens only for files the session has **actually
read**. A law doc is thus cheap until read and the **first** thing shed under budget pressure
(auxiliary docs are dropped before whole skills). That is the right risk profile for law — and the
reason not to fold it into `SKILL.md`.

**Enforcement needs no third gate.** The manifest hashes the shipped half; `test_docs_sync` holds
the pair. A gate for a relation two gates already enforce is the duplication this project's law
forbids. Accepting a law doc means: it appears in `kit.json` with a class, and its pair is
byte-identical.

**The transport is repo-side by design.** `tools/kit_deliver.py` hands a member an update as one
unit and never touches the member's own files; it is declared **meta-factory-only** in
`gate_registry.py` because **a member delivers to nobody**. So an instrument that exists to
distribute does **not** ship — which is why a census of the shipped tree does not see it.

### 6.1 The member leg — an ADOPTION STEP, never installed from here

**A member that adopts an instrument and wants its law to survive compaction creates its own reload
link.** It is the member's act, in the member's tree, because only the member knows its own skill
directory name:

```
<member>/skills/<member-skill>/<instrument>.md  ->  ../../docs/instruments/<instrument>.md
```

**It is a step the adopting factory owns, on the same footing as the other adoption steps** — the
declaration, the install and the verify. Two rules bind it:

- **It is never installed from the meta-factory.** `kit_deliver.py` copies files and creates no
  symlinks; a distribution that wrote into a member's skill tree would be touching the member's own
  files, which its contract forbids outright. **The shape is each member's own decision.**
- **"Absent from the member's tree" is not "unusable".** A law doc with no reload link is perfectly
  readable — it is simply not re-injected after compaction. The census records the absence as a
  **declared state** (§7.2), exactly as it records a deferred migration, and never as a failure.
- **That declared state names both axes (§7.2).** A member can **hold** an instrument's declared
  file set without being **green** on it — and a census counts the first while the member's own gate
  reports the second — so a recorded state that names one is a claim about the other.

**The shape is proven in production, not only in source:** `skills/grafana/` already runs it —
`sql-examples.md` sits as a top-level auxiliary `.md` symlink beside `SKILL.md`, and the loader
discovers and reads it through the link. **That one is absolute; a member adopting this law should
prefer the relative form**, which survives a move of either tree.

### 6.2 The reload path serves a CHECKOUT, not a revision

**A law doc's reload link resolves to a file in the repository's working tree — so what a lane
reloads is whatever that checkout currently holds, never `origin/main` and never a worktree's tip.**
A `readlink -f` that succeeds proves the path *resolves*; it says nothing about which revision it
serves. Those are different questions and only the second one matters to a lane about to act on the
law.

Measured 2026-09-27 on this repository's own frame checkout. Predicate: the served bytes against the
`origin/main` blob for the same path. Instant: 2026-09-27T17:2xZ.
- the shared tree stood **3 commits behind** `origin/main` (my own §5.5 landing among them);
- the reload link resolved, and served **318 lines** where the pushed doc carried **349**;
- the missing **31 lines** were that law doc's §9 adoption readings — added precisely so the section
  would keep its own promise, and therefore exactly the newest law in the file.

**And a checkout can be AHEAD of every ref, which is the worse case.** Measured in the turn that
wrote this paragraph, on another law doc in this same tree (`pacemaker.md`): at 17:48Z the served
bytes differed from **both** `HEAD` and `origin/main` — a peer's **uncommitted** edit — and by 17:56Z
that peer had committed it, so all three agreed again. The served revision therefore moved twice
inside a single turn, and in between it existed at **no named ref**: not stale, but
**unreproducible** — unreviewed, unnamed, and liable to vanish or be rewritten by a rebase. A lane
that has met only the *behind* case reaches for a `pull`; a `pull` cannot fix this one, because
there is nothing to pull.

**This does not contradict "two paths, one file" above — it qualifies what that claim covers.** The
shipped half and the reloaded half are one inode and cannot drift *from each other*; an inode can
still be **behind**, and nothing in the distribution model measures that. The pair gate
(`test_docs_sync`) reads the working tree too, so it is green on a stale pair by construction.

**One checkout, one served revision.** The link resolves through the containing directory, which is
itself a symlink into this repo — so every lane sharing that skill directory reloads the **same**
tree's HEAD, and no lane can make the served revision current by working in a worktree, because a
worktree is a different directory. A single lane's decision not to pull is therefore not a private
matter: it sets the revision every sibling lane reloads.

Two rules for a reader:
- **When the served revision matters, compare the served bytes against the tip** — never trust the
  symlink. `git diff origin/main -- <path>` answers it: that form reads the **working tree** against
  the tip, so it catches an uncommitted edit. `git diff HEAD origin/main -- <path>` does **not** — it
  compares two refs and is blind to the case above, which is the state the check exists to catch.
- **The shared tree is not a lane's to bring current.** It may carry peers' uncommitted work, and
  touching it is the boundary §7.3 draws. Reading the divergence, or landing one's own change from a
  worktree, is the shape that leaves the tree alone.

## 7. The version identifier and the deferred state

**These two are defined here, once, because they are cross-instrument: an owner coining their own
would make them per-instrument and they would drift.**

### 7.1 Version identifier — part 4

**An instrument's version is DERIVED from the manifest, never hand-typed.** The manifest's
`kit_version` is a digest over its own `(path, sha256, class)` triples; a hand-typed number is a
claim about the tree that nothing can test, and it drifts the moment a shipped file is edited
without the number. **The class is inside the digest deliberately** — moving `standalone` to `seed`
switches a cell from a finding to no comparison at all, and a version that did not move would let
that happen invisibly. A per-instrument identifier is read the same way, over that instrument's own
declared file set (§1), so a member can state **which version of one instrument it holds** — not
merely which kit it holds.

### 7.2 Deferred is a DECLARED state — part 9

**A member behind on an instrument states it as a declaration: "behind by N, deferred because X."**
The gate reds only on **UNDECLARED** divergence. Deferral is not drift; drift is divergence nobody
declared. This is why the migration path is **not** a red gate — measured: a dispatch round produced
**0 ports** from five replies, because *reporting is not enforcement*. The counter is a deferral the
member owns and the census records, never a gate that fails a factory for a decision it took openly.

**A declaration requires a surface, and the clause must NAME it.** An instrument whose adoption can
be DEFERRED must name the surface where the deferral is declared, and that surface must carry a
field for the state. A requirement with no surface to receive it is unsatisfiable as written, and
the failure it produces is silent in the direction that matters: a member that deferred and a member
that never considered the matter read identically. This is the same family as the cross-factory
citation class (§9) — a member cannot follow a citation into the meta-factory's ledger, and cannot
declare into a surface with no field. For the kit that surface is **`registry/factories/<slug>.json`**,
field **`kit`** (§9 O6): states `adopted` / `partial` / `deferred` / `not-applicable`, a non-empty
`reason` required for the last two, and the field ABSENT still valid while the obligation is new.
A per-instrument declaration names its own.

**Adoption has two axes, and neither implies the other: HELD and GREEN.** A member **holds** an
instrument when its declared file set is present (§1); it is **green** when its own gate passes over
that set. A member can hold a complete set and be red — the files arrived as another instrument's
closure (§1.3) with no decision behind them, or it carries a divergent copy of a path (§9 O1). And
it can be green on a partial set, because a gate judges what the tree carries and a missing file is
not a failing one. So a census predicate counts **held** while a member's gate reports **green**, and
a state that records only one reads as a claim about the other. The declared adoption state names
both. Measured 2026-09-27T15:51:34Z, `tools/kit_census.py` (predicate: which copy an owner's tap
reaches against which copies a member's tree holds; scope: **5** declared members, all reachable;
instant as quoted): the census separates exactly these two and records that they disagreed in
**BOTH** directions the same day — one factory held a copy that had never executed, and a copy can
execute with no tree copy at all.

### 7.3 A generated artifact is regenerated at the COMMIT, never in a shared tree

**The manifest and both pin vehicles are GENERATED, the generator walks the WORKING TREE
(`KIT_ROOT.rglob("*")`), and the pre-commit hook hashes the INDEX.** In a shared tree those two
diverge the moment any lane holds an unstaged or staged edit inside the population, and the failure
runs in both directions: a plain regeneration bakes a peer's in-flight bytes into the reference every
member is measured against, and the commit is then refused because the manifest does not describe the
index. Measured three times on 2026-09-27, by three lanes on three different mechanisms — a peer's
unstaged `TEMPLATE/tests/test_patrol_host_state.py` reddened three gates for every other lane; a
peer's STAGED `TEMPLATE/tools/questions` refused a commit whose manifest had been generated at HEAD;
and a `pull --rebase --autostash` left the manifest and both vehicles conflicted. **The conforming
technique is to regenerate against a tree where every path but your own sits at the commit** — a
clean detached worktree at HEAD (`git worktree add --detach <tmp> HEAD`), or a private index
(`GIT_INDEX_FILE`) so a peer's staging survives untouched. Verify the COMMIT rather than the disk:
every entry's committed blob must equal the committed manifest, which is a different test from
`kit_manifest.py --check`, whose read is the working tree and which therefore reports drift a peer
owns. **A generated artifact is a function of the COMMITTED tree; a manifest built from anything else
describes a tree that does not exist.**

### 7.4 A law file cannot publish its own version — the self-reference regress

**A law doc that is itself a manifest path cannot state the current version of itself, and that is a
PROPERTY of the measurement, not a defect of it.** Measured 2026-09-27 on `review-rotation.md`,
standing on the commit that ships it: a controlled probe moving ONE byte of the doc moved the doc's
own sha256 and the manifest's `kit_version` in the same step — the reading moved because the writer
wrote. This is the sharper form of §7.1: there a hand-typed number was untestable because nothing
checked it, while here the DERIVED number is untestable from inside the file that carries it. Every
instrument law doc is a `standalone` manifest path, so every one of them has this regress, and a
clause stated per-instrument would be coined once per file.

**What to publish instead:** the reading WITH its instant and its predicate, never as a claim of
currency — and **the row a reviewer can reproduce is the one at the COMMIT the doc ships in**, since
a mid-flight reading is a real instant that is also already superseded. Two consequences: (a) the doc
states that its value moves whenever any shipped file moves, including files the instrument does not
own; and (b) **to read a version, read `registry/kit.json`** — the manifest is the only surface where
the reading and the tree are the same object.

### 7.5 A measurement reads the COMMITTED revision, never a working tree on a shared repo

A byte-identity or census predicate that reads a **working tree** measures a population that moves
under it. Measured 2026-09-27: two lanes measured one member's divergence and got **4** divergent
paths and **3**. Against `git show HEAD:TEMPLATE/<path>` the member was **byte-identical**
(md5 `dd0005c251eb377ced61097886adb494` on both sides); the fourth "divergence" was another lane's 36
uncommitted lines. Had the higher figure been written, a member's durable declaration would have
recorded a divergence against a revision that **exists nowhere in git**, and it would have been false
against HEAD from the moment it was written. **A figure that cannot be reproduced from the commit is
not a measurement.**

Read `git show HEAD:<path>`, or a clean worktree at HEAD (§7.3). A count that moves minutes apart is
not two readings; it is one reading of a moving object.

**A count still owes its predicate.** `behind_by` is validated only as an integer
(`tools/registry.py:350`), so nothing defines what it counts — every divergent path, or genuine lags
only, excluding a member's declared forks? The count is a measurement; the classification is the
member's reading. State both, or the number is unreproducible behind a judgement call.

## 8. Ownership and scope

| who | what |
|---|---|
| **this lane (Instruments methodology)** | this frame; review of every per-instrument law file (a **requirement**, not a courtesy) |
| **each instrument's owner** | that instrument's own law file, authored under this frame's review |
| **the Fleet instruments lane (topic 4555, session `37e71e03`)** | **instantiation** — turning a meta-factory part into a declared instrument: its declaration, its law file, its class, its version, under this frame. It owns the law file of each instrument it instantiates, so the row above applies to it unchanged for those files. |
| **HQ** | **cross-factory authority** — any clause binding a member factory, and the process law *about* instruments |

**The split is authorship versus authority, and they are not the same thing.** Authorship of a law
doc under this frame is delegable because `docs/instruments/` appears in **no row** of the SS11
writer table — no owner waiver is needed. Authority over a clause that binds a member factory is
**not** delegable and stays at HQ. **A per-instrument file's scope header states both halves**, so
the next reader cannot confuse the writer of a file with the authority behind a clause in it.

**Address by ARTIFACT, never by name.** A review, correction or dispatch about an instrument goes to
the lane that owns the artifact, and ownership is settled **from the artifact** — the authoring
commit's `Session-Id` trailer — never from a lane name in a heading. Measured 2026-09-27: a §8 review
headed "→ Fleet instruments" was delivered to the Pacemakers/Crons lane (`ee5cd2f5`) while the
intended lane (`37e71e03`) received nothing, so the review was owed and unlanded for half an hour.
The heading named a role; the trailer names the owner. The discriminator is live and cheap:
`git log -1 --format='%(trailers:key=Session-Id)' -- docs/instruments/kit.md` returns `37e71e03`,
and the same command on `pacemaker.md` returns `ee5cd2f5`.

**The split, in one line:** this frame defines what an instrument **IS**; the Fleet instruments lane
instantiates meta-factory parts **INTO** instruments; each instrument's own lane **OWNS** that
instrument — its law file, its enforcement, and its member adoption.

**Out of scope for an instrument owner, by role:** `tools/**` code ownership (Toolsmith),
daemon and core source (Editor), and the surface an instrument runs on where that belongs to another
factory. An instrument owner supplies text to the lane that owns a file; they do not land it there.

## 9. Member obligations — stated here, authored by HQ

**Authored by HQ; authority is the ruling row named against each clause.** A member factory can read this file. A member cannot follow a citation into the meta-factory's ledger, so an obligation that binds a member is stated IN FULL here and the ruling row is its authority record, never its delivery route. This is §8's split applied to the clause class §8 had not yet covered: cross-instrument DEFINITIONS are the frame's and are cited; cross-factory OBLIGATIONS are HQ's and are shipped.

**A kit-side change is not a member obligation.** Clauses ruled about a shipped tool — the hygiene declaration surface, the template-law port, the lane-derivation fix — are things the kit does; a member receives them by porting. They are not listed here, and padding this section with them would make a member responsible for work that is ours.

### O1 — Migration duty
A member factory holding a divergent copy of a kit instrument file must **dispose** of it one of three ways, and silence is not a disposition:

- **migrate** to the promoted shape;
- **declare the fork**, with the reason, in its own declaration surface;
- **defer**, with a stated re-entry condition.

*Authority:* ruling n=1292 (C1). The declaration surface is registry/kit-decisions.json, which already carries the 2026-09-26 wave; a fork declared there is not drift, an undeclared one is.

### O2 — Promotion duty
When an instrument is promoted into the template, its canonical location is **inside this repo**; the existing pieces of the future bundle move to the template; and **the donor factory then migrates to the shape of the promoted instrument**. The third leg is the one that has no automatic owner and is therefore stated here rather than assumed.

*Authority:* ruling n=1283, recording the owner's law verbatim — it existed in no durable surface before that row.

### O3 — Pin duty
Every member factory vendors registry/kit.json as its **own pin** and its own gate goes red on undeclared divergence from **that pin** — never from the meta-factory's live manifest. A member's verdict must depend on its own tree and never on ours; a gate that reads our working tree makes a member's audit a function of our backlog and our queue.

*Authority:* ruling n=1292 (C4). The mechanism ships (tools/kit_pin.py, tests/test_kit_pin.py, registry/kit-exemptions.json as factory data), so this is an obligation on members rather than new machinery. An absent pin SKIPs behind a named vacuity guard; it never passes silently.

### O4 — Declaration duty
A member factory declares what its ledger accepts: tools/actors.txt, the authorized-event matrix, and its ref kinds — or states why it has none. **A factory that declares nothing cannot be governed**, and a silent absence is indistinguishable from a permitted one.

*Authority:* ruling n=1292 (C5). Measured 2026-09-27: the matrix file is absent in four of the five member trees, present only in inferhub-watch; among the four ledger-holders, three accept an unauthorized row today.

### O5 — Subject-namespace duty
A ledger's bare hash-N namespace is **one board's**. Keeping it unique is the factory's obligation and the kit cannot check it: the sequence predicate keys on the exact subject string, so two boards sharing a numbering make one bare hash-N name two work units, and the collision does not red — a close on the second board's unit is accepted on the first board's intake and claim, which is a defeated guard reported as clean. A factory carrying more than one board picks ONE disposition and states it: scope lifecycle rows to the board the ledger records and name a second board's units with a distinct descriptive stem, or keep a second ledger via OC_LEDGER_PATH. A qualified reference is no discriminator, and a board lookup cannot close it — a row records a NUMBER, not which board it meant.

*Authority:* ruling n=971, and the clause is already law in full at skills/meta-factory/SKILL.md:740. It is restated here because a member cannot read that file; the meta-factory's own copy stays the canonical text and this section cites it.

### O6 — a member factory is initialized to the kit system, and its state is declared

A member factory is initialized to the kit system, and its state is declared. The delivery leg exists and is one command per member: `python3 tools/kit_deliver.py --to <member-root> [--dry-run]` (BOOTSTRAP Step 4f). It writes the bytes and the vendored pin in ONE run, so the member's own gate cannot red on a state we created — measured `--dry-run` rc=0 on three trees, 105 / 88 / 101 files to add. Nothing runs it on a cadence today, and that is the obligation: a member is initialized, or it declares why not. The declaration is the `kit` field on the member's own fragment. Silence is not a disposition — a member that deferred and a member that never considered the kit must be distinguishable on the surface that exists.

*Authority:* owner order 2026-09-27T14:00Z ("the member factories should be initialized to use the kit system"); n=1283 Q2 (a clause binding a member factory stays at HQ).
