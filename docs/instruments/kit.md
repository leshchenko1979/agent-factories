# The kit instrument

**Owns:** this instrument's own law — its declared file set, its closure, its gate set, its data
surfaces, its version source and its census. It owns **no** cross-instrument definition; those live
in the frame it cites.
**Writer:** the Fleet-instruments lane. **Reviewer:** the Instruments-methodology lane — the frame's
own law makes review of a per-instrument file a **requirement, not a courtesy** (frame §8).
**Authority:** **HQ retains cross-factory authority.** Any clause in this file that binds a member
factory is HQ's, and so is the process law *about* instruments; both are cited here, never coined.

**This file cites `template-instruments.md`, the frame, and never restates it** — restating is how one
definition becomes two, and two definitions drift. Parts 4, 7, 8 and 9 are cross-instrument by
construction: the frame defines them **once, precisely so an instrument owner does not coin their
own.** This file therefore supplies only what is true of THIS instrument:

| part | defined by | what this file supplies |
|---|---|---|
| **4** — version identifier | frame §7.1 | the declared file set the identifier is read over (§2) |
| **7** — data surfaces | frame §2 | which surfaces ship as `.example` and which the factory owns (§6) |
| **8** — self-probe | frame §2 | the named probes that make this instrument's gate actually BITE (§7) |
| **9** — update path | frame §7.2 and §6.1 | the member's adoption steps for THIS instrument (§8) |

## 1. What the kit instrument is

**Its job, in one sentence: a factory's shipped set is a MEASURED object with a version, and this
instrument is the unit that makes that checkable in a tree** — it regenerates, verifies, censuses,
names, delivers and pins the kit.

The instrument **delivers every other instrument** (frame §2, part 6: *call sites*). That is why its
completeness gates everything downstream: an instrument that is not in the manifest is not delivered,
and an instrument that is not censused is not measured against its adopters.

**Name:** `kit` — a bare noun, per frame §4: adopted instruments drop the `oc-` prefix, because the
class field now carries the fleet-generic-versus-factory-specific distinction the prefix used to
carry.

### 1.1 One instrument with TWO HOMES, and the split is by POPULATION

The frame requires a declaration so a reader can answer *"is this instrument complete here?"* without
enumerating imports (frame §1). For this instrument that question has **two different answers in two
different trees**, because the fleet-serving half does not ship:

| home | population | why |
|---|---|---|
| **shipping** | `TEMPLATE/` — the manifest's own population | a member must PIN its own kit against the version it ported, so the pin reader must be in its tree |
| **root-side** | this repo's `tools/`+`tests/` — in **no** manifest | the census, naming and delivery tools serve the FLEET. A member delivers to nobody (frame §6), so it has no caller for them |

**The consequence is a declaration rule, not a footnote:** a class in `registry/kit.json` is a
statement about a **shipped** path, so a root-side executable **cannot** carry one — it is outside
that manifest's population by construction. Its class lives in `TEMPLATE/tests/gate_registry.py` as a
`meta-factory-only` entry whose `reason` names the population. So this instrument's classes live in
**two homes**, and a reader who greps `kit.json` for `kit_surfaces`, finds nothing, and files that
absence as a part-3 defect has read the wrong manifest for that half (§4 states the same fact from
the gate side).

## 2. The declared file set

**Predicate:** the shipped paths a member of this instrument receives — the manifest rows that carry
it. **Scope:** `registry/kit.json` at the instant named in §5. Both halves of each row are listed
because the pair is what a member adopts, and the manifest hashes the `TEMPLATE/` half.

| # | path (member half ↔ TEMPLATE half) | class | what it is |
|---|---|---|---|
| 1 | `tools/kit_pin.py` ↔ `TEMPLATE/tools/kit_pin.py` | `closure` | **the pin reader** — imported rather than run |
| 2 | `tests/test_kit_pin.py` ↔ `TEMPLATE/tests/test_kit_pin.py` | `standalone` | **the gate** — judges a member's tree against its OWN pin |

**This is the ONE table the census parses** — `tools/instrument_census.py` derives the declared set
from these numbered rows rather than keeping a second list that would drift, so a shipped path added
here is measured there with no second edit. **A member is HELD when both rows are present.** The set
is two paths because the transport delivers two paths, and §9.1's per-member census measures the same
two — the parsed coordinate and the adoption table agree by construction rather than by maintenance.

**Six modules, five root-side gates, one shipping gate — and it is ONE instrument, not eleven.** Say
it explicitly, because a reader counting the files as so many instruments reads the census in §9 wrong.
Rows 1–2 are the shipping half; §2.1 is the rest, deliberately outside the parsed set for the reason
stated there.

**The pin reader is SHARED, and the frame already makes that legal.** `TEMPLATE/tools/kit_pin.py` is
imported by this instrument's own transport **and** by `TEMPLATE/tools/patrol_host_state.py`, the
pacemaker instrument's runner (frame §1.3: *an instrument does not own its executable exclusively*).
The class the manifest assigns it is `closure`, so it is present only to be imported, and the frame's
own §3 rule applies: **a pin travels with its reader** — which is why `kit_pin.py` and
`test_kit_pin.py` are two rows of the same kit and not two independently adoptable files. A member
that keeps the gate and drops the module holds a gate that cannot import.

### 2.1 The root-side half — meta-factory-only, and deliberately NOT in the parsed set

| role | path | why it cannot ship |
|---|---|---|
| **executable** — regenerate/verify the manifest | `tools/kit_manifest.py` | it is the reference; a member measures itself against its VENDORED pin, not our generator |
| **executable** — the fleet adoption census | `tools/kit_census.py` | its population is the member trees (`registry/fleet.json`) |
| **executable** — the fleet naming census | `tools/kit_names.py` | its population is the other trees; a member does not sweep the fleet |
| **executable** — the four-surface census | `tools/kit_surfaces.py` | its population is `TEMPLATE/tools/`; a member has no template tree |
| **executable** — the transport | `tools/kit_deliver.py` | a member delivers to nobody |

**Why these five are excluded from the parsed rows above, and why that is not a gap.** The parser
reads a paired row as *"a member must hold both halves"*. These five have **no `TEMPLATE/` counterpart
at all** — every entry in `registry/kit.json` is `TEMPLATE/`-rooted, which is the predicate, not a
count — so there is no member half to pair, and a row asserting one would state a falsehood. Pairing
each to itself would put five paths into the declared set that the transport never delivers, and then
**every member in the fleet would read short by five for a state that is correct by design.** That is
frame §7.2's *not applicable* wearing a shortfall's clothing, and it is the same error as scoring
`opencrabs-dev` 0-of-2: a scope mistake filed as a shortfall, which is worse than no measurement
because it looks like one.

The class of **four** of the five lives in `TEMPLATE/tests/gate_registry.py` as `meta-factory-only`
entries — the home §4 names for an executable outside the manifest population. So a reader grepping
`kit.json` for `kit_manifest`, `kit_census`, `kit_names` or `kit_deliver` finds nothing, **and that
absence is not a part-3 defect.** One instrument, two class homes, and this section is where the
split is stated rather than left to be rediscovered.

**The fifth is the exception, and it is the reason this row says four rather than five.**
`tools/kit_surfaces.py` has **no** registry entry and **no** gate — `grep -c kit_surfaces
TEMPLATE/tests/gate_registry.py` → **0** — so it is the one root-side executable whose class lives
**nowhere**: neither in `kit.json` (outside that population) nor in `gate_registry.py` (no entry).
That is the sharpest gap this instrument carries, it is measured and owed in full at **§4.1**, and
it is listed as **F1** in §9.2. A reader who takes this section's rule as a blanket would stop
looking at exactly the path that needs looking at — so the exception is stated here, where the rule
is, rather than left to be found further down.

## 3. The closure — declared, never derived

Part 2 of the full set. The frame requires the closure be **declared, never derived** (§1.1), because
a static import walk is blind to modules loaded by path — and a derived closure reports a tree
complete while it cannot run. Measured first-hand, module by module, over the five root-side
executables and the shipping pair:

| module | what it imports beyond the stdlib | tier |
|---|---|---|
| `tools/kit_manifest.py` | **nothing** — stdlib only, so it is self-sufficient | — |
| `tools/kit_names.py` | `ast` (stdlib) | — |
| `tools/kit_surfaces.py` | `kit_manifest` | **HARD** — a top-level import |
| `tools/kit_deliver.py` | `kit_manifest`, `kit_pin` | **HARD** |
| `tools/kit_census.py` | `patrol_host_state` | **HARD** |

**This instrument's closure crosses an instrument boundary, and that is the frame's §1.3 case rather
than a defect.** `tools/kit_census.py` reaches `patrol_host_state` — the pacemaker instrument's
runner — to call `P.kit_drift_leg()`: the census **renders that leg's own result** instead of
re-implementing the comparison. So a change to the pacemaker's runner reaches this instrument's
census, and the two closures overlap by construction. Declaring a tidy closure that stopped at this
instrument's own files would produce a declaration that is complete on paper and crashes in the
tree, which is the failure frame §1.3 exists to make illegal.

**The root-side tier is HARD, not lazy.** `sys.path.insert(0, str(REPO / "tools"))` runs at module
scope and the imports follow it, so a missing `kit_manifest.py` or `patrol_host_state.py` raises at
import rather than degrading to a message. This instrument does **not** have the frame's silent
tier, and claiming the exotic failure would be the more flattering error.

**What a MEMBER needs is the shipping half only, and it is two files.** `TEMPLATE/tools/kit_pin.py`
(imported by the gate) and `TEMPLATE/tests/test_kit_pin.py` (the reader). The five root-side
modules are this repo's instruments for measuring the fleet; a member holds none of them, and their
absence from a member's tree is **not applicable**, never a gap.

## 4. The gate set and its registry entries

Part 3 of the full set. Read from `TEMPLATE/tests/gate_registry.py`; the grains differ by half, and
the reason is the same one that fixes §1.1.

**The shipping gate is REQUIRED:**

| gate | registered at | grain | why that grain |
|---|---|---|---|
| `test_kit_pin.py` | `gate_registry.py:512` | **REQUIRED** | it is byte-paired with its root copy, so the manifest grain is what keeps a factory from dropping the pin reader and keeping the gate |

**The four root-side gates are OPTIONAL, each `meta-factory-only` with its own stated reason** —
which this file cites rather than paraphrases, because the registry's `reason` is the mechanism
that makes the absence a *declaration* instead of a silent skip:

| gate | grain | the registry's own reason, cited |
|---|---|---|
| `tests/test_kit_manifest.py` | OPTIONAL | *"meta-factory-only (plan 2646d31a step 9) — its POPULATION is `TEMPLATE/`, the reference manifest of the shipped kit. A bootstrapped factory has no TEMPLATE/ tree … it skips with that reason rather than passing silently."* |
| `tests/test_kit_deliver.py` | OPTIONAL | *"meta-factory-only (plan 2646d31a step 7) — its subject tool tools/kit_deliver.py is the TRANSPORT … a member delivers to nobody, so a member running this gate would be exercising a tool it is not supposed to carry."* |
| `tests/test_kit_names.py` | OPTIONAL | *"meta-factory-only (plan 2646d31a step 10) — its POPULATION is the other trees, read through `registry/fleet.json`. A member does not sweep the fleet."* |
| `tests/test_kit_census.py` | OPTIONAL | *"meta-factory-only (plan 2646d31a step 9) — its POPULATION is the five MEMBER repositories, read through `registry/fleet.json`."* |

### 4.1 The one gate this instrument is MISSING — and it is the census instrument

**`tools/kit_surfaces.py` has no gate, and no registry entry. Measured, not inferred:**

- Predicate: `grep -c kit_surfaces TEMPLATE/tests/gate_registry.py` → **0** (rc=1).
- Scope: both trees. No `tests/test_kit_surfaces.py` exists in either.
- Instant: 2026-09-27T11:5xZ.

**Why this is the sharpest gap in the tree rather than one missing file among many:** `kit_surfaces.py`
is the census instrument that **exists because a figure was read two ways** — its own docstring reads
*"the PREDICATE lived in prose that each reader completed differently. This file is the predicate, so
the figure is derived."* It returns a verdict and **nothing exercises it**. Its non-vacuity probes are
never run by any gate, so a regression in its own predicates would be silent — which is frame §2
part 8 (self-probe) missing **in the instrument that defines the census**. §7 names the gate and the
probes; the build is owed, not implied.

## 5. The version identifier — part 4

**Defined in frame §7.1 and cited here, not restated.** What this file supplies is the set the
identifier is read over: **the shipping half of §2**, and the mechanism by which it is computed.

`registry/kit.json` carries `kit_version`, a digest over the manifest's **own** `(path, sha256,
class)` triples, generated by `tools/kit_manifest.py` and never hand-edited. Measured live, both
readings this turn:

- Predicate: `python3 tools/kit_manifest.py` / `--check` → **128 file(s), `kit_version
  e90c5558a39b`**; `--check` rc=0 on the read that produced that digest.
- Instant: 2026-09-27T11:5xZ.

**A digest quoted without its instant is the defect this identifier exists to prevent**, so state
the reading and its time together: the same `--check` on a later read this turn returned **rc=1**
with `TEMPLATE/tests/test_patrol_host_state.py` **DRIFTED** (`1c9433f717c5` → `50fc6456fd83`) — a peer's
in-flight edit, and exactly the state `kit_version` is designed to make visible.

**One path is excluded from the set by design, and the reason is arithmetic.**
`TEMPLATE/registry/kit.example.json` is the **pin vehicle** — the copy of the manifest that ships so
a factory can vendor it. `tools/kit_manifest.py:69-79` excludes it because the vehicle's content IS a
rendering of the manifest: carrying its digest would give `kit_version = H(files including
digest(vehicle))` against `vehicle = render(kit_version, files)`, which has **no fixpoint**. It is
tracked, paired with `registry/kit.example.json`, and deliberately unclassed. **That is a principled
exception, not a path a sweep forgot** — and it is why `--check` reports `0 unlisted` while a tracked
`TEMPLATE/` path is absent from the manifest.

## 6. Data surfaces — part 7

Which surfaces ship as `.example` and which the factory **owns**. The frame's rule is the
load-bearing half: *the factory's declarations are never overwritten by an update* (frame §2, part
7). This instrument is unusual in that its **primary surface is generated**, so the table says who
owns each one.

| surface | ships as | owner | why it must not be overwritten |
|---|---|---|---|
| `registry/kit.json` | generated | the **kit** | the version source (§5) — regenerated by `tools/kit_manifest.py`, never hand-edited, because a hand-kept list of shipped files is a second copy of the tree that goes stale silently |
| `TEMPLATE/registry/kit.example.json` | paired with `registry/kit.example.json` | the **kit** | the **pin vehicle**: the copy a member VENDORS at the version it ported. Excluded from the set it renders, by the fixpoint reason in §5 |
| `registry/kit-decisions.json` | the adopter writes its own | the **factory** | the decisions store `tools/kit_census.py` reads; a factory's own adoption decisions are its declarations |
| `registry/fleet.json` | `TEMPLATE/registry/fleet.example.json` | the **factory** | the fleet POPULATION the naming and census instruments read. Never installed from the template — a member copies the example and declares its own |
| `registry/factories/*.json` | the adopter writes its own | the **factory** | the member manifests `kit_census` counts |
| `registry/gates.json` | `TEMPLATE/registry/gates.example.json` | the **factory** | the declared-gate inventory the registry leg reads |
| `registry/kit-exemptions.json` | **nothing** — absence IS the empty state | the **factory** | a member's own declared forks, and this instrument's **extension surface** (§6.1). The reader's absence-default is *"nothing is declared exempt"* and absence is **GREEN**, so there is no shipped copy for an update to overwrite, and none for a member to carry unused |

**A surface absent from this table is absent by measurement, not by omission.** The one tracked
`TEMPLATE/` path deliberately outside these tables — and outside the manifest — is the pin vehicle,
and §5 states its reason.

### 6.1 The extension surface — a member's fork is a DECLARATION, and this is its contract

**This instrument HAS an extension surface: `registry/kit-exemptions.json`.** That is the statement
frame §6.5 requires at this naming site, and the alternative it offers — *"no extension surface:
member subject matter lives outside it"* — would be false of a file this instrument's own reader
consumes. §6.4's fork test and this section read one predicate from opposite sides: a member's own
subject matter (its own event set, its own actors, its own box's measurements) lands here **as a
declaration**, while the member's divergent bytes stay in the member's own tree.

**This surface ships no file: its empty state IS its reader's absence-default — and that is the one
place this instrument departs from the specimen's shape.** `ledger`'s surface ships as an empty
`.example.json`; kit ships **no file at all**, because the reader's own absence-default *is* the
empty declaration — `load_exemptions()`
(`tools/kit_pin.py:201`) returns *"no `registry/kit-exemptions.json` in {root} — nothing is declared
exempt"* and the pin stays **GREEN**. Contract part 1's substance therefore holds — *an adopter that
declares nothing carries no dead vocabulary* — by a different mechanism than the specimen's, and the
consequence is stated rather than smoothed: **a member learns this path from the pin GATE's own
failure text** — `tests/test_kit_pin.py:144`, paired byte-identically with its `TEMPLATE/` twin,
prints *"…or declare the fork in `registry/kit-exemptions.json` with a reason."* The sentence is
emitted by the **gate**, never by the pin module, whose own text is the absence-default above — so
the path reaches a member **from that gate or from this doc, never from a shipped file.**

**The contract, four parts, measured against the specimen** (`ledger.md` §3):

| # | part | measured on this instrument |
|---|---|---|
| **1** | shipped EMPTY | **met in SUBSTANCE, not in FORM** — this surface ships **no file at all**: the empty declaration IS the reader's absence-default (`tools/kit_pin.py::load_exemptions`, `:225`), where the specimen ships an empty `.example.json`. The reader is the surface's **judge**, not a half of it, and it is closure-paired with `TEMPLATE/tools/kit_pin.py` |
| **2** | a declaration **ADDS**; it never removes or redefines a core entry | **holds.** An entry declares a path the member **carries** whose bytes differ from its **own** pin. It cannot drop a path from the manifest, and it cannot move a path's class: `undeclared_divergence()` reads the class from the **pin** (`:260`), never from the entry — so the `class` field an entry carries is **documentation**, and a member can neither exempt a `seed` path into judgement (`:277` skips that class regardless) nor redefine what a `standalone` path means |
| **3** | **ONE reader** serves the instrument's paths, so its writer and its verifier cannot disagree | **HOLDS — it was VIOLATED until #263, and that history is kept in F5.** The judgement path is `undeclared_divergence()` (`tools/kit_pin.py::undeclared_divergence`, `:235`), which applies the **admission predicate** at `:262-268`; `load_exemptions()` (`:201`) only **LOADS** the raw list and admits nothing. The census no longer parses the file: `pin_state()` (`tools/kit_census.py::pin_state`, `:280`) takes its count off the verdict's own `declared` (`:323`), so ONE computation serves the report and the judgement and the two cannot disagree. The class it closed is kept in view rather than tidied away: the census used to report `len(exempt)`, so for `{"exempt": [{"nopath": 1}, {"path": "tools/ledger.py"}]}` it read **2 declared** where the pin's declared set held **1** — a member read a declaration the judge did not honour, and its pin then red on divergence it believed it had declared. That is §6.5's own failure mode: *lawful at the write path, unknown at `verify`* |
| **4** | an addition a SECOND factory needs **PROMOTES to the core** | **holds, and the route is declared IN THE DATA**: an entry's `disposition` names it — `(b)` declare-the-fork, `(c)` promote-the-member-half, the semantics `miidas`'s own `_note` records for the 2026-09-27 migration round. **The field is documentation, not a machine gate** — `grep -c disposition tools/kit_pin.py` → **0**, so the promotion itself is frame §5's process, not something this reader performs. `miidas`'s `_note` states the purpose the frame gives this channel: *"Each entry names the capability it carries so the instrument owner can decide whether to absorb it"* — the fleet's R&D channel, with the member's half as the arrival evidence frame §5.1 criterion 1 wants |

**The member's duty is CITED here, never authored** (frame §6.5's own scope): O1's
migrate-or-declare-or-defer disposition for a copy it already holds, and O4's duty to declare what
its instrument accepts — or to state why it has none. This section declares the **instrument's**
surface; §9's O-series carries what the **member** owes.

## 7. Self-probe and non-vacuity — part 8

**A gate that has only seen good input has not been shown to bite** (frame §2, part 8).

### 7.1 The shipping gate's probes — present today

| probe | where | what it shows |
|---|---|---|
| the pin comparison BITES on a drifted file | `TEMPLATE/tests/test_kit_pin.py` | a manifest that names a file whose digest moved produces `differs-from-kit`, not a clean run |
| the pin reports a file **absent** from the tree | `TEMPLATE/tests/test_kit_pin.py` | a `missing` outcome is distinguishable from a match |
| the pin reports a file **not in the manifest** | `TEMPLATE/tests/test_kit_pin.py` | `not-in-kit` is reported rather than folded into a match |
| the gate leaves the live `registry/kit.json` and `tools/kit_pin.py` **unmodified** | `TEMPLATE/tests/test_kit_pin.py:258-259`, `:408-409` | the probe is read-only: it hashes both before and after |

### 7.2 The probes the MISSING gate owes — named, not implied

This is the remedy for §4.1. The gate is **`tests/test_kit_surfaces.py`**, meta-factory-only at the
same grain as its four siblings, and its subject tool is `tools/kit_surfaces.py`. The probes it must
carry, each written against the census's own published contract:

| # | probe | what it must show |
|---|---|---|
| 1 | **it BITES on an undeclared gap** | a synthetic tool carrying an undeclared shortfall must produce the `FAIL — N tool(s) carry an undeclared gap` verdict. The census's live verdict today is already a FAIL (§9.1), so a gate that ran only against today's tree would be red for the wrong reason and green never — the biting probe must use a fixture whose expected verdict is known |
| 2 | **it prints the POPULATION it examined** | the executable/closure counts and the per-tool `n/4`. The census's own text grounds this: *"A zero there would be a real gap and this exemption would be a lie, which is why the column is printed rather than the claim asserted"* |
| 3 | **a DECLARED exemption is not counted as a gap** | the exemption logic itself is exercised: a shortfall carrying a declared reason must NOT appear in the `UNDECLARED` list. This is the one that keeps probe 1 honest — a gate that reds on every shortfall would red on correct declared state |

**The live run is the census itself:** `python3 tools/kit_surfaces.py` prints each tool's surfaces
beside its status and ends with the FIGURE-by-kind block. A probe that reported only its verdict,
without the population it examined, would be the vacuity this part exists to prevent.

## 8. Update path and the member's adoption — part 9

**The deferred state is defined in frame §7.2 and cited here: a member behind on this instrument
states it as a declaration — "behind by N, deferred because X" — and only UNDECLARED divergence
reds.**

The member's steps for THIS instrument, in order. The declaration is the file you are reading; the
install travels `registry/kit.json` (manifest grain, never a per-member dispatch):

1. **Port the two shipping paths of §2** — `TEMPLATE/tools/kit_pin.py` and
   `TEMPLATE/tests/test_kit_pin.py` — carrying the classes the manifest assigns them (`closure` and
   `standalone`). Take **both**: the frame's §3 rule is *a pin travels with its reader*, and the
   module is classed `closure`, so a member that keeps the gate and drops the module holds a gate
   that cannot import — a crash at import, not a quiet week (§3).
2. **Vendor your own pin.** Copy `TEMPLATE/registry/kit.example.json` (the vehicle) into your tree at
   the version you ported. This is what makes your drift measurable against *the version you took*
   rather than against ours — the mechanism §5's identifier exists for. Absent, the pin gate has
   nothing to compare and says so.
3. **Register `test_kit_pin.py` at the grain §4 states (REQUIRED).** The registry's own reason for
   that grain is on the row: it is byte-paired, and the manifest grain is what keeps you from
   dropping the reader and keeping the gate.
4. **Create your own reload link** if you want this law to survive your own compaction — the frame's
   §6.1 defines it and it is **your** act, in **your** tree; it is never installed from the template.
   Absent from your tree is a **declared state**, not a failure.

**What you do NOT take is the five root-side modules of §2.1.** They are this repo's fleet instruments
(census, naming, delivery, surfaces); their absence from your tree is **not applicable**, never a
gap, and no step above asks for them. A member that copied `kit_census.py` and found its population
empty would be running a fleet sweep in a tree that is not the fleet — §4's own reason for the
`meta-factory-only` grain.

## 9. Adoption census, and the gaps this instrument DECLARES

### 9.1 Adoption of the shipping half

**Predicate:** each of the two shipping paths of §2 exists in the member's own declared `/repo`
(a member counts as holding the instrument only if **both** are present — the frame's §3 rule is that
a pin travels with its reader, so one file alone is a partial copy, and the frame is explicit that a
partial copy reads as adopted).
**Scope:** the six member manifests in `registry/factories/*.json`. **Instant:**
2026-09-27T14:0xZ.

| factory | `tools/kit_pin.py` | `tests/test_kit_pin.py` | own pin | disposition |
|---|---|---|---|---|
| `ai-antispam` | present | present | present | **ADOPTED** — 2 of 2, gate green |
| `miidas` | present | **member-side gate** | present | **ADOPTED with a fork** — 2 of 2 by its own reader |
| `infra-factory` | present | **absent** | present | **PARTIAL** — 1 of 2 |
| `inferhub-watch` | absent | absent | present | 0 of 2 (pin only) |
| `opencrabs-dev` | absent | absent | **absent** | out of scope — see below |
| `meta-factory` | present | present | present | the template's own tree |

**Superseded beside, never over — the same predicate re-read at 2026-09-27T21:23:57Z by
`tools/instrument_census.py kit`** (rc=0, declared set 2, the §2 rows above). Two rows moved, and
**the observer caused both movements**, which is why the predecessor stays in place rather than being
silently corrected:

| member | 14:0xZ | 21:23:57Z | cause |
|---|---|---|---|
| `inferhub-watch` | 0 of 2 | **2 of 2** | this instrument's own transport wrote both paths at 14:16; the member kept them |
| `miidas` | 2 of 2 *(by its own reader)* | **1 of 2** | the strict predicate names `tests/test_kit_pin.py`; miidas's fork is `test_kit_pin_member.py`, and the delivered copy was withdrawn at 15:04 |

**So a delivery wave and a withdrawal are not adoption events, and a census run across them measures
the wave, not a decision.** Both new rows read `HELD-UNDECLARED` — the declared leg is a member's act,
and no member has answered in it. The frame's own warning applies to the row above mine as much as to
any other: `held` is a presence reading over a **working tree**, so it is never a fact about a
member's repository.

**One member has adopted this instrument since the previous reading, and the census moved in BOTH
directions.** `ai-antispam` went 0 of 2 → **2 of 2** and its gate returns **rc=0** (judged 14 carried
paths, 6 declared exempt). `miidas` is the sharper row: it carries no `tests/test_kit_pin.py`, so a
presence-only predicate calls it partial — but it carries `tests/test_kit_pin_member.py` with
`registry/kit-exemptions.json`, and that gate also returns **rc=0** (24 carried paths judged, 17 forks
declared, 0 undeclared divergence). Two independent readings of one row:

- **by §2's file list:** 1 of 2 — **PARTIAL**;
- **by what the member can actually judge itself with:** adopted, with a forked reader.

A file-presence predicate cannot see the second, **and neither reading is wrong** — they answer
different questions. This is why the disposition column names the reader, not only the file.

**And the census carries a predicate bound: it measures the TREE'S AGE, never its owner's decision.**
The initialization step (§9.1.1 reason 1) postdates five of the six trees, so a member reading 0 of 2
records *when it was built*, not a judgement about the kit. A later reader must take this table as a
measurement of the fleet at an instant — and must not read a low row as a member that declined.

**`opencrabs-dev` is out of scope by repo kind, not behind.** Its declared `/repo` is `/root/opencrabs`,
the OpenCrabs **source** tree. It holds no pin and no kit file, and a factory whose repo is upstream
source has no tree for this instrument to land in. Reading it as 0-of-4 would file a scope error as a
shortfall.

**The partial copies are the frame §1.3 predicted state, and their provenance is measured, not
suspected.** `infra-factory` carries `tools/kit_pin.py` and no reader gate — a module **nothing in its
tree exercises** — because it is a confirmed pacemaker adopter: `TEMPLATE/tools/patrol_host_state.py:88`
binds `KIT_PIN = REPO / "tools" / "kit_pin.py"` and `:1454` loads it **by that path**
(`load_module("kit_pin", KIT_PIN)`, never an `import`), and `pacemaker.md:124` declares
`TEMPLATE/tools/kit_pin.py` in **the pacemaker's own closure** — "the pin reader — travels with its pin
(frame §3)". A member that adopted the **pacemaker** therefore received this file as a piece of *that*
instrument, which is frame §1.3 exactly: an executable may be shared, and when it is, the closure is
declared over the whole executable. So a factory can hold a complete instrument **and** a partial one
at the same time, and only declaration tells them apart.

### 9.1.1 Why the adoption is incomplete — the mechanism measured

The step exists, and it is **one command per member**. `TEMPLATE/BOOTSTRAP.md` **Step 4f** ("Vendor
the pin, so you can judge yourself") names it, and `tools/kit_deliver.py` implements it: bytes and pin
are written **in one run**, so the member's own gate cannot red on a state we created.

Dry-run readings, 2026-09-27T14:0xZ (`--dry-run`, nothing written, `rc=0` all three). The counts are
**one instant's property**, exactly as §9.1.2 states for the delivery table beside them — the version
in force at this reading is the one §9.1.2's pin column names, so an ADD figure travels with it or it
is unreproducible:

| target | ADD | the two shipping paths |
|---|---|---|
| `inferhub-watch` | **105** | both — `tests/test_kit_pin.py` and `tools/kit_pin.py` |
| `infra-factory` | **88** | the gate it lacks (`tools/kit_pin.py` is already at the delivered bytes) |
| `ai-antispam` | **101** | **neither** — the pair is already current |

So the four measured reasons the census is where it is — none of them a refusal:

1. **The step postdates five of the six trees.** Step 4f landed 2026-09-25 (`ec04e5f`), and
   `kit_deliver.py` the same day (`a211cbc`). A member bootstrapped before that step never had it,
   so its state records *when it was built*, not a judgement about the kit.
2. **Provenance** — reason 1 of §9.1 above: a piece arrives as another instrument's closure, which is
   a partial copy without a decision behind it.
3. **Nothing runs it on a cadence, and reporting is not enforcement.** Step 4f's own text is *"run by
   the meta-factory, or handed to you"* — there is no cron and no lane duty. Frame §7.2 records the
   measured cost: *"a dispatch round produced 0 ports from five replies."*
4. **The member had nowhere to declare the state — and this one is now CLOSED.** At the census
   instant all six member manifests carried the same thirteen keys and **none carried a kit,
   adoption, deferred or drift field** (scanned then). Frame §7.2 makes a deferral a **declared**
   state, but the member's own manifest had no home for it, so a member that had decided to wait
   read exactly like one that never considered it.

Reason 4 is the one that kept the others invisible, and it was a **schema** question, not a
per-instrument one: the surface a member declares adoption on is `registry/factories/<slug>.json`,
which this instrument does not own. **The home now exists** — commit `a29a18e` adds it as an
optional object, `kit`, with four states (`adopted` / `partial` / `deferred` / `not-applicable`) and
`KIT_REASON_REQUIRED = ("deferred", "not-applicable")` (`tools/registry.py:298-300`), so a deferral
or a not-applicable must carry its reason while a member that has not yet answered stays legal
(absent is a valid state while the obligation is new). **This changes the census above not at all:**
the six manifests still read thirteen keys with no `kit` value, which is now an *unanswered* state
rather than an *undeclarable* one — and the table moves only when a member answers on its own
measurement.

**And the gate's self-probe is stated, not hidden.** In a member tree the fixture arms **SKIP** —
their inputs are `TEMPLATE/`-only paths and no member carries a `TEMPLATE/` (measured: `ai-antispam`,
`miidas`, `infra-factory` all NO). The live arm carries the verdict there, and the gate prints the
skip rather than passing quietly (`f9cc405` made it reach a verdict instead of crashing). An adopter
should read a member-tree green as *the live population is judged*, never as *every probe ran*.

### 9.1.2 The initialization delivery of 2026-09-27 — measured

**Instant:** 2026-09-27T14:1xZ. **Command:** `python3 tools/kit_deliver.py --to <member-root>`, once per
member, on owner order (*"the member factories should be initialized to use the kit system"*).

| member | written | local files kept | pin before → after | its gate, after |
|---|---|---|---|---|
| `ai-antispam` | 101 | 6 | `ab929a61bcc2` → `6f10a14dcb5f` | **rc=0** |
| `inferhub-watch` | 105 | 7 | `db6aa904a8a1` → `6f10a14dcb5f` | **rc=1** — 7 undeclared divergences |
| `infra-factory` | 88 | 21 | `b0bb09cb288f` → `6f10a14dcb5f` | **rc=1** — 18 undeclared divergences |
| `miidas` | 91 | 17 | `6ab591c618ec` → `6f10a14dcb5f` | **rc=0** |
| `opencrabs-dev` | — | — | **REFUSED** — no pin | out of scope (§9.1) |

**The counts above are ONE INSTANT's property, and the instant is the version named in the pin
column.** The manifest moved twice on 2026-09-27 alone — `6f10a14dcb5f` at this delivery,
`685f40d3648a` after this file's own registration, and a peer's further drift after that — so an ADD
count without its version beside it is unreproducible, which is the rule §5 already states for the
identifier itself.

**Every one of the four now holds both shipping paths of §2**, so §9.1's own predicate reads 2 of 2 for
all four. The two red gates are **not** caused by the delivery, and that is measured rather than
argued: the delivery **never overwrites an existing file** (it counts them as *local files kept*), so
each diverging path was compared against the member's **own pre-delivery pin** — and **every one was
already divergent there** (`inferhub-watch` 7 of 7, `infra-factory` 18 of 18). What the delivery changed
is that two of these members now **have the reader** that makes their drift measurable at all; before
it, both carried no `tests/test_kit_pin.py` and could not judge themselves.

**So the delivery resolves the ADD half and leaves the DIVERGENCE half, which is the member's own
decision** — the gate names both lawful answers (take the update, or declare the fork in
`registry/kit-exemptions.json` with a reason), and frame §9's O-series is the same rule.

Two smaller measurements from the same run. `miidas`'s pin carries **132** entries, the extra being
`TEMPLATE/tests/test_template_sync.py` — a path **retired in the source and kept in the member's pin**
(the tool names it as such on every run, so it is a declared observation, not drift). And the tool's
own phrase *"local files kept"* is broader than divergence: it counts **every** existing path it
declines to overwrite, including those byte-identical to the pin — which is why its count (21 for
`infra-factory`) exceeds the gate's divergence count (18).

**Disposition, ruled by the owner 2026-09-27T15:16Z: *"Leave them for the members."*** Three of the
four trees keep the delivery **uncommitted and in place** — `ai-antispam`, `inferhub-watch`, and
`infra-factory`'s declared root `/root/vds-servers` — and whether to commit, adopt selectively, or
withdraw is **each member's own decision**. The delivery is purely additive, so holding it blocks no
member. `miidas` was **withdrawn at that member's own request** (2026-09-27T15:04–15:06Z: archived
first, then removed, pin restored, `git status --porcelain` back to **0 lines**) because its declared
posture is 17 forks plus a deferred pacemaker, and a wholesale arrival would have changed that posture
without its decision. **The withdrawal restored `registry/kit.json` by NAME, never a blanket
`git checkout .`** — which is why that member's uncommitted `evidence/rework.md` survived it.

**One caveat a committing member must weigh, measured 15:2xZ: the delivered `tools/registry.py`
predates the kit-adoption field.** The delivery ran **14:16Z**; `a29a18e` — the commit adding
`KIT_KEYS` / `KIT_STATES` / `KIT_REASON_REQUIRED` — landed **14:35:08Z**, 19 minutes later. So the
two trees that received the file **newly** return **0 hits for `KIT_KEYS` against TEMPLATE's 2**:
`ai-antispam` and `inferhub-watch`, both untracked at mtime 14:16:10 / 14:16:12. `/root/vds-servers`
also reads 0, but its `tools/registry.py` is **tracked at mtime 06:10:16** — *older than the
delivery*, so it is that member's own pre-existing file, **kept** rather than written (the delivery
never overwrites), and is **not** attributable to this round. A member that commits today adopts a
validator **blind to the field O6's obligation runs on**; the deliver-side remedy is declared as
**F3** in §9.2.


### 9.2 The gaps this instrument declares

Each is **declared** rather than silently patched, with its reproduce command, so a later reader
meets a decision instead of an unknown.

| # | gap | reproduce | owner of the remedy |
|---|---|---|---|
| **F1** | `tools/kit_surfaces.py` has **no gate** — frame §2 part 8 is missing in the instrument that defines the census | `grep -c kit_surfaces TEMPLATE/tests/gate_registry.py` → **0**; no `tests/test_kit_surfaces.py` in either tree | the gate named in §7.2; `tests/**` code, built by the code owner and reviewed by the methodology lane |
| **F2** | the census returns **FAIL — 2 tool(s) carry an undeclared gap** | `python3 tools/kit_surfaces.py` → `ledger-index` missing S1,S2; `subject_anchor` missing S2 | the two tools' owners; `subject_anchor` is the one the survey named, and `ledger-index` has drifted in since |
| **F3** | `tools/kit_deliver.py` writes a pin **without checking the pin is current**, so a deliver run behind TEMPLATE's own HEAD writes a pin that is **stale on arrival** — and nothing reds, because the member's gate judges it against the pin it was **handed**, not against the kit that **exists** | `grep -cE 'stale\|current\|newer\|ahead\|behind' tools/kit_deliver.py` → **0**, rc=1; the tool reads `kit_version` (`:54`, `:59`, `:98`) and writes it (`:166`), and never compares it against the source repo's HEAD-computed version | the tool's code owner; a deliver-side guard that refuses or warns when `source_state()['kit_version']` differs from the HEAD-computed one |
| **F4** | `tools/kit_deliver.py` **AUTHORS the member's pin** — it writes `registry/kit.json` (`:166`) even into a tree that already carries a deliberately authored, committed pin, so a transport rewrites a declaration that is the member's by frame §8 | `sed -n '160,170p' tools/kit_deliver.py` → `pin["kit_version"] = kit` then `planned["pin_path"].write_text(...)`; measured on two trees: `inferhub-watch` HEAD `db6aa904a8a1` / 118 → `6f10a14dcb5f` / 131, `vds-servers` HEAD `b0bb09cb288f` / 118 → `6f10a14dcb5f` / 131 | the tool's code owner; **refuse to write `registry/kit.json` into a tree that already carries one**, unless that member asked for the refresh |
| **F5** | **RESOLVED** — was **a SECOND reader of the extension surface**, which frame §6.5's contract part 3 forbids: `tools/kit_census.py` parsed `registry/kit-exemptions.json` itself and reported `len(exempt)`, so an entry the **pin ignores** was still reported as a declaration | `grep -c 'len(d.get' tools/kit_census.py` → **0** (was **1**); `grep -c load_exemptions tools/kit_census.py` → **0** — the census calls the **judgement**, not the loader, and the loader still returns the **raw** list, so counting it would remain a no-op. The count is read at `tools/kit_census.py:323` off the verdict built at `:318`. Held by `python3 tests/test_kit_census.py` (rc=0): **ARM 14** checks the census's count against the pin's admitted set, **ARM 15** that an unreadable file reads `None` and never `0`. Both were neutered and each bit **alone** — restoring `len(exempt)` failed ARM 14 only, a naive `declared` read failed ARM 15 only (measured 2026-10-02) | resolved by the tool's code owner under agent-factories**#263**: fix `281bd2a` on `worker/223-ruling-leg`. The route is **ONE**, and it is the pin's own verdict — the census consumes `undeclared_divergence()['declared']`, so divergence is impossible by construction; the rejected arm, a new *shared* function, would be a **third reader** whose contract can drift from the judgement it mirrors |
| **F6** | this doc's **own `file:line` citations are unverified and drift silently** — nothing reds when a named file moves, so a reader is sent to a line that now says something else | #263 moved `tools/kit_pin.py` by **14** lines (`undeclared_divergence` `:221`→`:235`, `declared` `:279`→`:293`), invalidating every citation this file makes past `:205` in that path, and `tools/kit_census.py` likewise; no gate reads a citation, so the drift is visible only to whoever sweeps it by hand | this doc's Writer, for the FORM — cite `file::symbol` and let the line follow, so a reader resolves the **name** and the number is a convenience. The mechanical half is **OWED, not existing law** — no citation law exists today: the frame's §8 is *Ownership and scope* and the frame carries **0** hits for `resolver`, `file::`, `symbol` (measured 2026-10-02) — and the resolver it needs is `tools/**` code, so its **tool** owner is **Toolsmith** by frame §8's own out-of-scope row, while the **duty** to state a cross-instrument citation convention sits with **HQ** (frame §8: *the process law about instruments*) |

**F5 is kept as a RESOLVED row rather than deleted, so the identifier stays resolvable** — `#263`, the §8
review record and §6.1 part 3 all name it, and a reader following that name from any of them should land here.
A resolved row carries the evidence that it is resolved — the gate that now holds it — never merely the claim; the frame already states the neighbouring law at `:113` (*a reading is superseded beside its predecessor, never over it*), so this convention is that law applied here rather than invented.
**F2's count moved while this file was being written, and that is the point of stating a predicate
rather than a figure.** The survey measured **1** undeclared gap; the same command this turn returns
**2**. A bare "1" would have been a dated claim wearing a general one's clothes.

**F3 is the one gap this round PRODUCED rather than found**, and it was named by a member lane, not by
this instrument. The `miidas` lane caught a stale validator in its own tree by running its vendored pin
against a TEMPLATE it went and found — a signal **no member gets from the transport**, which is exactly
why the remedy is a deliver-side obligation rather than a member-side one. A member that trusts the
delivery receives whatever the pin held at deliver time and has no way to learn it was 19 minutes
behind a landing. The same member asked for a **per-instrument selector** (`kit_deliver` accepts only
`--to` and `--dry-run`), because a wholesale arrival changes a deliberately-partial posture without the
member's decision; that is a second, separate remedy on the same tool.

**F4 is the same tool violating a DIFFERENT principle, and its harm was measured on two trees the same
evening.** A pin is the member's *declaration of what it took* — frame §8, and `kit_pin.py`'s own
docstring says it: *"a gate against MY pin"*. Both trees already carried a **deliberately authored,
committed** pin: `inferhub-watch`'s commit `04ca2ce` states the reasoning in its own message (*"a gate
against THEIR live manifest makes my verdict a function of their backlog … A gate against my pin
reddens it only when my tree diverges from my own declaration"*), and `vds-servers`' refresh is a
ledger-recorded act (row `n=567`, subject `kit-pin-refresh`). The deliver replaced both with ours. The
harm is not the file swap — it is that each member's gate then judges its **own declared forks** as
divergence from a declaration **it never made**: `inferhub-watch` went to **7 undeclared divergences,
every one its own declared fork**, having had a pin and no gate before the run. So the delivery wrote
the gate and our pin together, and the member did not choose to be judged. Recovery is one command
each, member-side, and it restores the member's own bytes: `git checkout registry/kit.json`.

## 10. Where this instrument's law lives

This file is the instrument's law home. The law it **takes over** is currently stated elsewhere, and
the move is deliberately not in this commit:

| today's home | what it carries about this instrument |
|---|---|
| `skills/meta-factory/SKILL.md` | the kit's own sections — the manifest, the class system, the pin, the delivery transport |
| `docs/best-practices.md` | the shipped-set discipline the classes encode |
| `tools/kit_manifest.py` | the enforcement, as a generated manifest with a `--check` verb |

**Two facts settle how that move must be done, both measured 2026-09-27:**

1. **No surface cites those clauses by number.** A sweep of the `SKILL.md:<N>` form over the corpus,
   plus the bare `:N`, `line N` and `§N` forms, returned **zero** citations of the kit clauses. The
   risk is therefore not a broken citation.
2. **What binds them is code, and code is the stronger citation.** The manifest and the pair gate are
   machine-enforced by `tools/kit_manifest.py --check` and **`tests/test_docs_sync.py` — the ROOT-side
   copy, and the half is part of the name.** That is frame **§7.6**'s rule, and this row is a specimen
   of it rather than a restatement: the `TEMPLATE/`-side copy of the same script resolves its repo
   root to `TEMPLATE/`, finds no `TEMPLATE/docs` beneath it, and exits **0** with *"no TEMPLATE/docs
   tree — nothing to pair"* — a green over an empty population, which is a verdict about nothing. So
   the pointer row must name **the enforcing command AND its half**, not a prose line a later edit can
   move without any gate noticing. The class is §2.1's one tool over — a right name in the wrong half
   of a pair, where the number checks out and the reader lands on the copy that has never bitten.

**Skill-text authorship is HQ's, not this lane's** (frame §8: an instrument owner supplies text to
the lane that owns a file; they do not land it there). So the extraction of the kit's SKILL sections
into this file is supplied to HQ, and **until it lands, `skills/meta-factory/SKILL.md` remains the
operative home and this file is its declaration and its citation target.** This file does not claim a
move it did not make.