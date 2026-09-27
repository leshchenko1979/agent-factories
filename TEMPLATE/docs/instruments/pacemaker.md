# The pacemaker instrument

**Owns:** this instrument's own law — its declared file set, its closure, its gate set, its data
surfaces, its version source and its adoption census. It owns **no** cross-instrument definition;
those live in the frame it cites.
**Writer:** the Pacemakers/Crons lane. **Reviewer:** the Instruments-methodology lane — the frame's
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

## 1. What the pacemaker instrument is

**Its job, in one sentence: a factory's scheduled jobs are thin WAKES whose duties are receipted, and
this instrument is the unit that makes that checkable in a tree.**

It upholds the Pacemaker Law — `docs/best-practices.md` P7 (*"Cron is a thin pacemaker trigger, not
the worker"*) and P28 (*"Every periodic process is driven by a thin nudging cron"*) — together with the
two contracts that law's consequences added, the **duty receipt** and the **redirect log**.

An instrument is a **declared** object (frame §1), and this file is its declaration. It names the
fields the frame fixes — name, executable(s), closure, gate set, version source, data surfaces — so a
reader holding this file and a tree can answer *"is the pacemaker instrument complete here?"* without
enumerating imports.

**Name:** `pacemaker` — a bare noun, per frame §4: adopted instruments drop the `oc-` prefix, because
the class field now carries the fleet-generic-versus-factory-specific distinction the prefix used to
carry.

## 2. The declared file set

Read from `registry/kit.json` (the manifest, `kit_version` at the instant of writing in §9):

| role | path | class |
|---|---|---|
| **executable** — the live runner | `TEMPLATE/tools/patrol_host_state.py` | `standalone` |
| **gate** — the pure predicate over rows | `TEMPLATE/tests/test_cron_thinness.py` | `standalone` |
| **gate** — the runner's wiring | `TEMPLATE/tests/test_patrol_host_state.py` | `standalone` |

**One instrument, one executable, two gates — not three instruments.** Say it explicitly, because a
reader counting the instrument's files as so many instruments reads the census in §9 wrong.

**The executable is a SHARED, multi-leg runner, and that boundary is real rather than tidy.**
`patrol_host_state.py` feeds live host state into the predicates of several duties; the pacemaker law
owns its **cron-thinness**, **notify-receipt** and **duty-receipt** legs. Python gives one file, so
the instrument's executable is indivisible — a member cannot take "just the pacemaker part" of it —
and the closure in §3 is therefore wider than the pacemaker's own legs. A declaration that pretended
otherwise would be the tidy lie this section exists to prevent.

## 3. The closure — declared, and it is the LOUD tier

Part 2 of the full set. The frame requires a closure be **declared, never derived** (§1), because a
static import walk is blind to modules loaded by path — and the frame's own specimen is a factory
running a green suite while missing 138,805 B of what it needs.

**Read first-hand: `patrol_host_state.py` loads six modules by path through `importlib`, and this
instrument's closure is on the LOUD side of the frame's two-tier split.** The distinction matters, so
state the mechanism rather than the label: `load_module` raises when it cannot load the target, and
the runner's only `try/except BoardReadError` wraps the **board read**, not the `legs = [...]` list
the call sits in. So a member holding the gate and the runner but **not** their closure does not get a
quiet week — it gets a crash. The frame's warning about the silent tier is about a *different* shape;
this instrument does not have it, and claiming the exotic failure would be the more flattering error.

Closure, declared (each path as it appears in the manifest, and verified present in the template at
the instant of writing):

| path | what the runner loads it for |
|---|---|
| `TEMPLATE/tools/field_predicate.py` | the canonical-trailer read that the close-board leg binds to |
| `TEMPLATE/tools/kit_pin.py` | the pin reader — travels with its pin (frame §3) |
| `TEMPLATE/tools/publish.py` | the publish-freshness leg |
| `TEMPLATE/tools/registry.py` | the registry read the legs share |
| `TEMPLATE/tests/test_board_intake_recorded.py` | the board-intake predicate |
| `TEMPLATE/tests/test_close_board_recorded.py` | the close-board gate |

The table above is the **shipped** half. The runner also refuses to start without one input that is
**member-authored and therefore never shipped**:

| path | what the runner loads it for |
|---|---|
| `<your repo>/registry/fleet.json` | the fleet manifest — `tools/registry.py::load_fleet_manifest`, called while the `legs` list is built |

Only `TEMPLATE/registry/fleet.example.json` ships (§6). `load_fleet_manifest` raises
`FleetManifestError` on **any** defect — absent, unparseable, a missing top-level key, an empty
`factories` list, a non-integer `chat_id`, a duplicate slug — and that call sits **outside** the
`try/except BoardReadError` that guards the board read, in the same `legs = [...]` expression as the
eight legs. So a member holding **every** shipped path above still cannot run the runner until it
writes this file. §8 step 2 states it as a step; it is a prerequisite.

**The shape a member must not adopt is the two-file copy.** `test_cron_thinness.py` is a pure
predicate: it judges a list handed to it and reads no live table. Copied alone, it passes — and it
has never been asked a question about the member's own box, because nothing feeds it rows. The runner
is what supplies that input, and the runner does not work without the six modules above. This is the
instrument's single most important adoption fact.

## 4. The gate set and its registry entries

Part 3 of the full set. Both gates are registered in `TEMPLATE/tests/gate_registry.py` as **REQUIRED**,
and the registry states the reason in its own words, which is why this file cites it instead of
paraphrasing it: *"It is byte-paired with a TEMPLATE copy, so the manifest grain is what keeps a
factory from dropping the runner and keeping the file."*

**That sentence is the instrument's whole adoption failure, stated in advance by the mechanism that
prevents it.** A factory that keeps `test_cron_thinness.py` and drops `patrol_host_state.py` holds a
gate that passes over an empty question — which is why the two are manifest rows of the same kit and
not two independently adoptable files.

| gate | registered at | grain | why that grain |
|---|---|---|---|
| `test_cron_thinness.py` | `gate_registry.py`, REQUIRED | required | the predicate is PURE over a list of rows and reads no live table, so it passes in a bootstrapped factory exactly as it does here — there is no `TEMPLATE` comparison or box-local fixture that would make it red |
| `test_patrol_host_state.py` | `gate_registry.py`, REQUIRED | required | it drives the instrument's own selftest against a throwaway register in a temp directory: no live register, no fleet manifest, no box-local fixture |

## 5. The version identifier — part 4

**Defined in frame §7.1 and cited here, not restated.** What this file supplies is the set the
identifier is read over: **the three paths in §2.**

Measured at the instant of writing, the part-4 forcing fact is present here as it was on the ledger:
**no hand-typed version exists in this instrument.** `tools/patrol_host_state.py` and
`tests/test_patrol_host_state.py` return **0** hits for `VERSION|__version__`; `test_cron_thinness.py`
returns **1**, and that one is the English word inside a docstring (*"that command's logic is a
VERSIONED REPO FILE"*), not a constant. State the hit rather than rounding it to zero: a count taken by
a pattern is not a count of items, and the honest report of this measurement is *one match, zero
identifiers*.

## 6. Data surfaces — part 7

Which surfaces ship as `.example` and which the factory **owns**. The frame's rule is the load-bearing
half: *the factory's declarations are never overwritten by an update* (frame §2, part 7). An
instrument that overwrote its adopter's declarations would silently reassign ownership of cron rows,
which is the one thing `job_prefixes` exists to state.

| surface | ships as | owner | why it must not be overwritten |
|---|---|---|---|
| `registry/fleet.json` → `job_prefixes` | `registry/fleet.example.json` | **the factory** | it IS the ownership declaration: the runner attributes each cron row to a factory by this field, never by the home a row sits in (measured: all twelve ai-antispam rows live in the ops home) |
| `registry/factories/*.json` | the adopter writes its own | **the factory** | the fragment store the attestation round reads and writes |
| `evidence/ledger.jsonl` | created on first append | **the factory** | the duty-receipt store — the run rows that make a duty's completion provable |
| `/tmp/<job-name>.log` | created by the job | **the factory** | the redirect log; its label must equal the job name, which is a contract between every pacemaker and the leg that reads it |
| `registry/kit.json` | generated | the **kit** | the version source (§5) — regenerated, never hand-edited |

**A surface absent from this table is absent by measurement, not by omission.**

## 7. Self-probe and non-vacuity — part 8

**A gate that has only seen good input has not been shown to bite** (frame §2, part 8). This
instrument's probes are named, not implied:

| probe | where | what it shows |
|---|---|---|
| `test_the_cron_leg_BITES_on_a_defect_in_a_row_this_factory_declares` | `tests/test_patrol_host_state.py` | the leg produces a PROBLEM on a synthetic defect, not merely a clean run |
| `test_the_cron_leg_RUNS_and_states_the_population_it_examined` | `tests/test_patrol_host_state.py` | coverage is printed beside the verdict: "0 problems" over "0 examined" and over "29 examined" are different facts |
| `test_the_cron_leg_fails_LOUDLY_when_nothing_is_attributed` | `tests/test_patrol_host_state.py` | a clean verdict over an examined-nothing read is not a verdict |
| `test_the_law_content_class_BITES_on_a_row_this_factory_declares` | `tests/test_patrol_host_state.py` | the embedded-law-content class bites on a row of the factory's own |
| `test_probe_is_offline` | `tests/test_cron_thinness.py` | the predicate is pure over a list, asserted structurally |
| `test_the_live_negative_specimen_stays_a_problem_for_the_right_reason` | `tests/test_cron_thinness.py` | a real row stays a finding, for the right reason and not by luck |

**The live probe is the runner itself:** `python3 tools/patrol_host_state.py` prints each leg's own
coverage count beside its verdict. A probe that reported only its verdict would be the vacuity this
part exists to prevent.

## 8. Update path and the member's adoption — part 9

**The deferred state is defined in frame §7.2 and cited here: a member behind on this instrument
states it as a declaration — "behind by N, deferred because X" — and only UNDECLARED divergence reds.**

The member's steps for THIS instrument, in order. The declaration is the file you are reading; the
install travels `registry/kit.json` (§3 of the frame's own model — manifest grain, never a per-member
dispatch):

1. **Port the kit rows.** The three paths in §2, carrying the classes the manifest assigns them, plus
   the six closure modules in §3. Nothing here is optional and nothing is ported "later": the closure
   is what makes the executable run, and a missing module crashes rather than degrades (§3).
2. **Write your own `registry/fleet.json` — a PREREQUISITE, not a nicety.** The runner will not start
   without it: `load_fleet_manifest` raises `FleetManifestError` (absent, unparseable, missing key, an
   empty `factories` list), and that call sits outside the board-read guard — so a member holding every
   shipped path still gets a crash, not a quiet week. Copy `registry/fleet.example.json` and fill it in.
   Your record's `job_prefixes` is what attributes your own cron rows to you; until it is declared,
   every row you own is reported as unattributable — named and counted, never judged, and never
   silently folded into someone else's factory. The two effects are separate: the file makes the
   runner RUN, the `job_prefixes` field makes its verdicts YOURS.
3. **Register the gates** at the grain §4 states, so the manifest can keep you from dropping the
   runner and keeping the file.
4. **Create your own reload link** if you want this law to survive your own compaction — the frame's
   §6.1 defines it and it is **your** act, in **your** tree; it is never installed from the template.
   Absent from your tree is a **declared state**, not a failure.

## 9. Adoption census

**Predicate:** each of the three declared paths of §2 exists in the factory's own declared `/repo`
(a member counts as present only if the path is there — the closure of §3 is measured separately,
because a partially-ported closure is a crash rather than a smaller number).
**Scope:** all five member manifests in `registry/factories/*.json` (the key is `factory`, not `slug`).
**Instant:** 2026-09-27T07:03:01Z.

| factory | declared set | own `fleet.json` | disposition |
|---|---|---|---|
| `infra-factory` | **3/3** | **written** | **ADOPTED** — closure 10/11 + its own manifest; its own gate passes **86 check(s), rc=0**. Untracked in its tree at the instant of measurement, so this is a port in progress, not a committed one. |
| `ai-antispam` | 0/3 | absent | DEFER (declared) — behind by 3/3, closure 1/6; blocked on its own project-write gate |
| `inferhub-watch` | 0/3 | absent | DEFER (declared) — behind by 8 of 9 declared paths; re-entry scoped against two adjacent instruments first |
| `miidas` | 0/3 | absent | DEFER (declared) — behind by 8 of 9; blocked because the transport is kit-wide and offers no per-instrument selector |
| `opencrabs-dev` | 0/3 | absent | BRIEFED — no disposition returned at this instant |

**One of five members has adopted it; three have declared a deferral with a reason and a re-entry
condition; one has not yet answered.** The distinction is the point of frame §7.2: a declared deferral
is a *state*, and only undeclared divergence reds. A census that reported "1 of 5" alone would erase
the difference between a member that measured itself and said why, and one that has gone quiet — so
the disposition column is not decoration, it is the half of the figure that a bare count destroys.

### 9.1 Three corrections from the adoption round, all measured

1. **A record in another factory's manifest does not satisfy step 2.** `ai-antispam` reported step 2
   already satisfied, citing a `registry/fleet.json` record carrying its own slug and job prefix. Read
   first-hand: `/root/ai-antispam/registry/` **does not exist**. The record it read is the
   **meta-factory's own** `registry/fleet.json` — a correct record of ai-antispam, sitting in a file
   the runner will never open from ai-antispam's tree, because the runner reads `REPO / "registry" /
   "fleet.json"` where `REPO` is the *runner's* root. This is the adjacency attribution this repo keeps
   ruling against: the row was read, the row was right, and it was not the row that binds.
2. **The declared closure of §3 is not the whole closure — it is the declared one.** `inferhub-watch`
   measured `tools/field_predicate.py` importing `ledger_declaration` and `reconstruction` in turn, and
   put its transitive closure at ~11 modules rather than 6. That is consistent, not contradictory: the
   frame (§1) requires the closure be **declared, never derived**, precisely because a static walk is
   blind to path-loaded modules. §3 declares what this instrument *loads*; a member's own transitive
   dependencies sit beneath it.
3. **The sanctioned transport cannot single out this instrument.** Confirmed at source:
   `tools/kit_deliver.py` accepts exactly `--to` and `--dry-run`; a grep for `instrument|--only|--paths|
   selector` returns **0** hits. A member's choice is therefore the whole population or a manual port of
   the declared set — the wave does not ask for the former, and the second is what `infra-factory` did.

## 10. Where this instrument's law lives

This file is the instrument's law home. The law it **takes over** is currently stated elsewhere, and
the move is deliberately not in this commit:

| today's home | what it carries about this instrument |
|---|---|
| `skills/meta-factory/SKILL.md` §11 *State — every surface has one writer* | the **duty receipt** (a `run` row written by the woken lane, declaring `receipt_subject`) and the **redirect log** (its label equals the job name) |
| `docs/best-practices.md` P7, P28 | the thin-wake rule itself |
| `tools/patrol_host_state.py` | the enforcement of all three, as machine-checked legs |

**Two facts settle how that move must be done, both measured 2026-09-27:**

1. **No surface cites those clauses by number.** A fleet-wide sweep of the `SKILL.md:<N>` form, plus
   bare `:N`, `line N` and `§N` forms, returned **zero** citations of any of them. The risk is
   therefore not a broken citation.
2. **What binds them is code, and code is the stronger citation.** The duty-receipt contract is
   machine-enforced in `tools/patrol_host_state.py`, so the pointer row left behind must name **the
   enforcing line**, not a prose line that a later edit can move without any gate noticing.

**Skill-text authorship is HQ's, not this lane's** (frame §8: an instrument owner supplies text to the
lane that owns a file; they do not land it there). So the extraction of §11 into this file is supplied
to HQ, and **until it lands, SKILL.md remains the operative home and this file is its declaration and
its citation target.** This file does not claim a move it did not make.
