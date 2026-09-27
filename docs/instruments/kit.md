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

Read from `registry/kit.json` for the shipping half, and from the tree for the root-side half.
`kit_version` at the instant of writing is in §5.

**The shipping half — the instrument's own manifest rows:**

| role | path | class |
|---|---|---|
| **closure** — the pin reader, imported rather than run | `TEMPLATE/tools/kit_pin.py` | `closure` |
| **gate** — the pin's own reader | `TEMPLATE/tests/test_kit_pin.py` | `standalone` |

**The root-side half — meta-factory-only, and therefore in NO manifest:**

| role | path | why it cannot ship |
|---|---|---|
| **executable** — regenerate/verify the manifest | `tools/kit_manifest.py` | it is the reference; a member measures itself against its VENDORED pin, not our generator |
| **executable** — the fleet adoption census | `tools/kit_census.py` | its population is the member trees (`registry/fleet.json`) |
| **executable** — the fleet naming census | `tools/kit_names.py` | its population is the other trees; a member does not sweep the fleet |
| **executable** — the four-surface census | `tools/kit_surfaces.py` | its population is `TEMPLATE/tools/`; a member has no template tree |
| **executable** — the transport | `tools/kit_deliver.py` | a member delivers to nobody |

**Six modules, five root-side gates, one shipping gate — and it is ONE instrument, not eleven.**
Say it explicitly, because a reader counting the files as so many instruments reads the census in §9
wrong.

**The pin reader is SHARED, and the frame already makes that legal.** `TEMPLATE/tools/kit_pin.py` is
imported by this instrument's own transport **and** by `TEMPLATE/tools/patrol_host_state.py`, the
pacemaker instrument's runner (frame §1.3: *an instrument does not own its executable exclusively*).
The class the manifest assigns it is `closure`, so it is present only to be imported, and the frame's
own §3 rule applies: **a pin travels with its reader** — which is why `kit_pin.py` and
`test_kit_pin.py` are two rows of the same kit and not two independently adoptable files. A member
that keeps the gate and drops the module holds a gate that cannot import.

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

**A surface absent from this table is absent by measurement, not by omission.** The one tracked
`TEMPLATE/` path deliberately outside these tables — and outside the manifest — is the pin vehicle,
and §5 states its reason.

## 7. Self-probe and non-vacuity — part 8

**A gate that has only seen good input has not been shown to bite** (frame §2, part 8).

### 7.1 The shipping gate's probes — present today

| probe | where | what it shows |
|---|---|---|
| the pin comparison BITES on a drifted file | `TEMPLATE/tests/test_kit_pin.py` | a manifest that names a file whose digest moved produces `differs-from-kit`, not a clean run |
| the pin reports a file **absent** from the tree | `TEMPLATE/tests/test_kit_pin.py` | a `missing` outcome is distinguishable from a match |
| the pin reports a file **not in the manifest** | `TEMPLATE/tests/test_kit_pin.py` | `not-in-kit` is reported rather than folded into a match |
| the gate leaves the live `registry/kit.json` and `tools/kit_pin.py` **unmodified** | `TEMPLATE/tests/test_kit_pin.py:191`, `:271` | the probe is read-only: it hashes both before and after |

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

**What you do NOT take is the five root-side modules of §2.** They are this repo's fleet instruments
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

Dry-run readings, 2026-09-27T14:0xZ (`--dry-run`, nothing written, `rc=0` all three):

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
4. **The member has nowhere to declare the state.** All six member manifests carry the same thirteen
   keys and **none carries a kit, adoption, deferred or drift field** (scanned this turn). Frame §7.2
   makes a deferral a **declared** state, but the member's own manifest has no home for it, so a
   member that has decided to wait reads exactly like one that never considered it.

Reason 4 is the one that keeps the others invisible, and it is a **schema** question, not a
per-instrument one: the surface a member declares adoption on is `registry/factories/<slug>.json`,
which this instrument does not own.

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


### 9.2 The gaps this instrument declares

Each is **declared** rather than silently patched, with its reproduce command, so a later reader
meets a decision instead of an unknown.

| # | gap | reproduce | owner of the remedy |
|---|---|---|---|
| **F1** | `tools/kit_surfaces.py` has **no gate** — frame §2 part 8 is missing in the instrument that defines the census | `grep -c kit_surfaces TEMPLATE/tests/gate_registry.py` → **0**; no `tests/test_kit_surfaces.py` in either tree | the gate named in §7.2; `tests/**` code, built by the code owner and reviewed by the methodology lane |
| **F2** | the census returns **FAIL — 2 tool(s) carry an undeclared gap** | `python3 tools/kit_surfaces.py` → `ledger-index` missing S1,S2; `subject_anchor` missing S2 | the two tools' owners; `subject_anchor` is the one the survey named, and `ledger-index` has drifted in since |

**F2's count moved while this file was being written, and that is the point of stating a predicate
rather than a figure.** The survey measured **1** undeclared gap; the same command this turn returns
**2**. A bare "1" would have been a dated claim wearing a general one's clothes.

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
   machine-enforced by `tools/kit_manifest.py --check` and `TEMPLATE/tests/test_docs_sync.py`, so the
   pointer row left behind must name **the enforcing command**, not a prose line a later edit can move
   without any gate noticing.

**Skill-text authorship is HQ's, not this lane's** (frame §8: an instrument owner supplies text to
the lane that owns a file; they do not land it there). So the extraction of the kit's SKILL sections
into this file is supplied to HQ, and **until it lands, `skills/meta-factory/SKILL.md` remains the
operative home and this file is its declaration and its citation target.** This file does not claim a
move it did not make.