# The pacemaker instrument

**Owns:** this instrument's own law — its declared file set, its closure, its gate set, its data
surfaces, its version source and its adoption census. It owns **no** cross-instrument definition;
those live in the frame it cites.
**Writer:** the Pacemakers/Crons lane. **Reviewer:** the Instruments-methodology lane — the frame's
own law makes review of a per-instrument file a **requirement, not a courtesy** (frame §8).
**Authority:** **HQ retains cross-factory authority.** Any clause in this file that binds a member
factory is HQ's, and so is the process law *about* instruments; both are cited here, never coined.
**Does not own, by role:** cross-instrument definitions (the frame, §8); the instantiation of a
meta-factory part into a new instrument (the Fleet instruments lane, HQ-chartered 2026-09-27T04:18Z);
and any clause binding a member factory (HQ, §8). This lane owns **one** instrument end to end —
its law, its enforcement, and its member adoption.

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

**Its job, in one sentence: a factory's periodic work rides in a cron row that gates cheaply, wakes a
session only when something is actually ready, and sets a goal so the woken lane keeps draining
instead of answering one turn and settling.**

The concept is four columns of the daemon's `cron_jobs` table (added by migration
`20260915000001_add_cron_trigger_pipeline.sql`; field semantics documented in
`src/docs/reference/templates/cron/README.md`):

| field | the duty it carries |
|---|---|
| `trigger_cmd` | the cheap pre-flight: a shell command run under `/bin/sh -c` (30 s timeout) **before** any agent turn. It watches; it never acts. |
| `trigger_on` | when the watch counts as "something to do": `non_empty` (default) · `exit_zero` · `exit_non_zero` · `regex:<pattern>` · `always`. |
| `deliver_to = session:<uuid>` | the wake. A fired trigger delivers into that session and starts its turn; the cron itself does no work. |
| `set_goal` (+ `goal_template`) | the keeping-going. The fire sets an **active goal** in the target session, so the lane works the detected condition to completion rather than settling after one turn. Refused unless `deliver_to` targets a session. |

**The economy is the point.** When the condition is not met the run is short-circuited at **0 tokens**
and recorded as a skipped run — the prompt never executes and nothing is delivered
(`cron_manage.rs:106`: *"If output is empty / non-zero based on `trigger_on`, job execution is
short-circuited (0 tokens)"*). A periodic duty with no gate burns a full agent turn on every fire,
whether or not there was anything to do; and a wake without `set_goal` drains the queue only as far
as one turn reached.

**The law this instrument upholds** is `docs/best-practices.md` P7 (*"Cron is a thin pacemaker
trigger, not the worker"*) and P28 (*"Every periodic process is driven by a thin nudging cron"*),
together with the two contracts that law's consequences added — the **duty receipt** and the
**redirect log**, whose surfaces §6 declares.

**Declaration and enforcement are different objects, and this doc is about both, in that order.**
What ships to *check* these rows is `tools/patrol_host_state.py` (the live runner: it reads the cron
table and feeds the predicates real rows) plus `tests/test_cron_thinness.py` (the pure predicate).
The patrol is the upholder; the pacemaker is the cron row. §2 declares the upholder's file set,
because that is what a tree census counts — but the **property** it upholds is the four columns
above, and a member that ports the files without gating its own crons has adopted the checker and
not the concept. An instrument is a **declared** object (frame §1), and this file is its declaration.

**The concept's live state, measured 2026-09-27T12:33:45Z** (predicate: `enabled=1` rows in the
**ops profile home only**; `gate` = `length(trigger_cmd) > 0`; `session wake` = `deliver_to`
beginning `session:` — the only non-null delivery forms on this home are `session:<uuid>` and
`telegram:-1003…`, verified by distinct read):

| metric | rows |
|---|---|
| enabled | 33 |
| with a cheap gate | 10 |
| waking a session | 8 |
| gate **AND** session wake | 2 |
| with `set_goal` | 2 |
| gate **AND** session wake **AND** `set_goal` | **0** |

So on this home **no enabled row yet carries the full concept**: the two gated session-wakes
(`ai-antispam-43-close-gate`, `ai-antispam-52-close-gate`) do not set a goal, and the two
`set_goal` rows (`oc-triage-factory-patrol`, `inferhub-hq-pacemaker`) have no gate. Six enabled
session-wakes have no gate at all and burn a turn on every fire. This table is a snapshot of ONE
home at ONE instant, not a fleet figure — §9 counts member **adoption of the instrument**, a
different population, and the two must not be read as each other.

**Name:** `pacemaker` — a bare noun, per frame §4: adopted instruments drop the `oc-` prefix, because
the class field now carries the fleet-generic-versus-factory-specific distinction the prefix used to
carry.
## 2. The declared file set

**Predicate:** the shipped paths the manifest classifies `standalone` or `closure` that carry this
instrument. **Scope:** `registry/kit.json` at the instant named in §9. Both halves of each row are
listed because the pair is what a member adopts, and the manifest hashes the `TEMPLATE/` half.

| # | path (member half ↔ TEMPLATE half) | class | what it is |
|---|---|---|---|
| 1 | `tools/patrol_host_state.py` ↔ `TEMPLATE/tools/patrol_host_state.py` | `standalone` | **the executable** — the live multi-leg runner |
| 2 | `tests/test_cron_thinness.py` ↔ `TEMPLATE/tests/test_cron_thinness.py` | `standalone` | **the gate** — the pure predicate over rows |
| 3 | `tests/test_patrol_host_state.py` ↔ `TEMPLATE/tests/test_patrol_host_state.py` | `standalone` | **the gate** — the runner's wiring |
| 4 | `tools/field_predicate.py` ↔ `TEMPLATE/tools/field_predicate.py` | `closure` | the canonical-trailer read the close-board leg binds to |
| 5 | `tools/kit_pin.py` ↔ `TEMPLATE/tools/kit_pin.py` | `closure` | the pin reader — travels with its pin (frame §3) |
| 6 | `tools/publish.py` ↔ `TEMPLATE/tools/publish.py` | `standalone` | the publish-freshness leg |
| 7 | `tools/registry.py` ↔ `TEMPLATE/tools/registry.py` | `standalone` | the registry read the legs share — also a CLI of its own |
| 8 | `tests/test_board_intake_recorded.py` ↔ `TEMPLATE/tests/test_board_intake_recorded.py` | `standalone` | the board-intake predicate |
| 9 | `tests/test_close_board_recorded.py` ↔ `TEMPLATE/tests/test_close_board_recorded.py` | `standalone` | the close-board gate |

**This is the ONE table the census parses** — `tools/instrument_census.py` derives the declared set
from these numbered rows rather than keeping a second list that would drift, so a shipped path added
here is measured there with no second edit. **A member is HELD only when all nine are present.** Rows
4–9 are the closure, and they are declared *here* rather than only explained in §3 because the
census's question is *"is the instrument complete here?"* — and a closure left out of the measured
set answers that question wrongly, which is the defect §3 describes.

**One instrument, one executable, two gates — not nine instruments.** Say it explicitly, because a
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

**The six closure modules — the SET the executable loads, whatever each one's manifest class — are
declared in §2's table, rows 4–9.** They are deliberately not repeated here, so
the measured list and the documented list cannot drift apart. The census parses §2; a second copy in
this section would be a list that drifts from the one being measured.

**And the closure is not the whole prerequisite.** The runner also refuses to start without one input
that is **member-authored and therefore never shipped**:

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

**That mechanism is a FILE the adopter must hold, and this doc did not name it until
`infra-factory` found the omission (§9.1 item 5).** `TEMPLATE/tests/gate_registry.py` is a manifest
row of class **`closure`**, byte-paired with its root twin (`cmp` rc=0) and stdlib-only, so it is
self-sufficient. It is **not** in §3's table because the RUNNER does not load it — it belongs to the
ADOPTION's closure, not the executable's. What it provides is the pair coupling: a member whose audit
discovers gates by glob holds no mechanism that notices the runner was dropped, and §8 step 3 is
unimplementable without it. Porting these gates means porting this file **AND the wrapper that runs
it** — and the second half is measured, not assumed.

**The registry is a LIBRARY, and a file nothing invokes is the defect §4 exists to prevent.**
Executed directly, `gate_registry.py` exits **rc=0 and prints nothing**: it defines functions and runs
none. What executes it is `TEMPLATE/tests/test_gate_registration.py` (manifest class `standalone`),
which matches the `test_*.py` glob a glob-discovering audit uses. So a member that ports the registry
alone holds a file nothing invokes — the disease reproduced by its own remedy. `infra-factory` is the
specimen: it holds `gate_registry.py` and its audit globs `tests/test_*.py`, and running the registry
by hand returns rc=0 with **empty output**.

**And the wrapper couples to the audit's INTERFACE, not just its presence.** It calls
`audit.run_gate(cmd, cwd, budget_sec)`. Measured in `infra-factory`'s tree, whose `tools/audit.py` is
a **484-line** revision with a **2-argument** `run_gate` (against the template's 2 414-line, 3-argument
form), the wrapper raises `TypeError: run_gate() takes 2 positional arguments but 3 were given` — it
crashes rather than reporting. So §8 step 3's honest options are: port the registry **and** the wrapper
**and** a compatible `tools/audit.py`; or state the gap. A member on a divergent audit has no cheap
path to this protection, and that is a measurement rather than a preference.

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
| `docs/ledger-invariants.json` | `docs/ledger-invariants.example.json` | **the factory** | the DECLARED duty-receipt boundary (#78 clause b): the runner's `duty_receipt_leg` reads it through the one reader, and a tree that has not declared one gets `DeclarationUnavailable` — measured in `ai-antispam`, whose gate exits **rc=1** on the absent file |
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
2. **Write your own declarations — `registry/fleet.json` and `docs/ledger-invariants.json`. Both are
   PREREQUISITES, not niceties, and both skeletons ship as manifest class `seed` (the class a member
   instantiates under its own name).**
   - **`registry/fleet.json`.** The runner will not start without it: `load_fleet_manifest` raises
     `FleetManifestError` (absent, unparseable, missing key, an empty `factories` list), and that call
     sits outside the board-read guard — so a member holding every shipped path still gets a crash, not
     a quiet week. Copy `registry/fleet.example.json` and fill it in. Your record's `job_prefixes` is
     what attributes your own cron rows to you; until it is declared, every row you own is reported as
     unattributable — named and counted, never judged, and never silently folded into someone else's
     factory. The two effects are separate: the file makes the runner RUN, the `job_prefixes` field
     makes its verdicts YOURS.
   - **`docs/ledger-invariants.json`.** The duty-receipt boundary is a DECLARED factory parameter (#78
     clause b), read through one reader. A tree that has not declared one gets
     `DeclarationUnavailable`, which surfaces as an **unhandled `SkipGate`** and exits **rc=1** — so
     here it is the **gate**, not the runner, that a member meets first (measured in `ai-antispam`,
     2026-09-27). Copy `docs/ledger-invariants.example.json` and fill in your own boundary. Note the
     shape rather than the fix: the skip vocabulary EXISTS and is keyed on a data condition, so a
     structural absence arriving as an unhandled raise is a shape worth reporting to this instrument's
     owner rather than working around.
3. **Register the gates** at the grain §4 states, so the manifest can keep you from dropping the
   runner and keeping the file. This step needs `tests/gate_registry.py` (§4) — if your tree has no
   gate registry and your audit discovers gates by glob, discovery gives you the RUN but not the
   PAIRING, so a dropped runner leaves a green file over an empty question. Port it or state the gap;
   do not record the gates as registered when nothing couples them.
4. **Create your own reload link** if you want this law to survive your own compaction — the frame's
   §6.1 defines it and it is **your** act, in **your** tree; it is never installed from the template.
   Absent from your tree is a **declared state**, not a failure.

**Three prerequisites, and they fail in different places.** Step 1's closure fails **loud** (§3) — the
runner crashes. Step 2's manifest also fails **loud**, and earlier: the `legs = [...]` expression raises
before any leg runs. Step 2's SECOND declaration fails loud in the other entry point: a tree with no
`docs/ledger-invariants.json` gets `DeclarationUnavailable` from the gate rather than the runner
(measured in `ai-antispam`, rc=1). The board convention (§9.1 item 4) fails **quiet in the legs and loud in the
gates**: the runner completes and honestly reports `examined 0`, while two of the discovered gates red
on every post-invariant close row the member's ledger holds. A member whose board surface is not
GitHub — one whose issue board *is* its own ledger — either carries the token convention or has those
two gates declare an INAPPLICABLE-skip carrying the reason. Adopting without deciding is the one shape
that leaves the member's own suite permanently red.

## 9. Adoption census

**TWO predicates, stated separately because they answer different questions — and a figure must carry
the one it came from.**

- **HELD** — `os.path.isfile(member.repo / p)` for each of §2's **nine** declared paths. This is
  `tools/instrument_census.py`'s predicate, and its published artifact is the citable form.
- **CURRENT** — byte-identity of each held file against the template half (`cmp -s`). A member can
  hold every path and still be **behind**: adoption is a revision, not a copy.

**Scope:** the member fragments in `registry/factories/*.json`. **Instant:** HELD read by
`tools/instrument_census.py` at **2026-09-27T17:49:48Z** — the stamp the committed artifact
`evidence/instrument-census-pacemaker-2026-09-27.md` carries on its own first line, so this citation
resolves to a receipt that agrees with it. **CURRENT** read by `cmp -s` at **2026-09-27T17:37Z** over
the same nine paths in the same five member repos. Earlier instants: 07:27:09Z, 08:38Z, 15:19:17Z.

| factory | held | current | disposition |
|---|---|---|---|
| `infra-factory` | **9/9** | 6/9 | **ADOPTED** — commits `e334161e` + `5cd8aefe`, pushed 0/0; its runner executes all **eight legs** and its own gate passes **86 check(s), rc=0**. |
| `ai-antispam` | **9/9** | 6/9 | **ADOPTED-WITH-FORKS** — commit `0ea9c66`, pushed 0/0; `test_cron_thinness.py` registered as audit gate 13 (16 passed). All three divergent files are **declared**: `registry.py` (fork #7, refreshed for `KIT_KEYS`) plus the two board gates, which carry its own anchor and the #59 exemption surface. Its patrol gate is **held uncommitted and declared** rather than shipped red. |
| `inferhub-watch` | **9/9** | 6/9 | **PORTING** — declared set now complete; the divergent `field_predicate.py` has been refreshed. Remaining: `patrol_host_state.py`, `test_patrol_host_state.py` and `registry.py` are **pre-fix revisions**, and its runner still raises `FleetManifestError` until it writes `registry/fleet.json`. |
| `miidas` | 1/9 | 1/9 | DEFER (declared) — behind by 8 of 9. Its **transport blocker is discharged**: the manual port proved in `infra-factory` needs no selector (§9.1 item 3), and the requirement was relayed to it 2026-09-27T08:35:59Z. The **board-convention prerequisite** (§9.1 item 4) stands. |
| `opencrabs-dev` | 0/9 | 0/9 | DEFER (declared) — `registry/` **does not exist** in its tree at all (`ls` rc=2). Its reason is SCOPE rather than effort: the prerequisite (`registry/kit.json` + `tools/kit_pin.py`) does not bootstrap one instrument — it **enrols the factory in the kit manifest system for every instrument at once**, a fleet-level decision that a pacemaker brief would otherwise decide by side effect. Re-entry: when it enrols in the kit for ANY instrument. |

**The three members that hold the set are each 6/9 CURRENT, and the divergence has one cause: they
adopted from a revision that predates this instrument's 2026-09-27 fixes.** `infra-factory` and
`inferhub-watch` both differ on exactly `patrol_host_state.py`, `test_patrol_host_state.py` and
`registry.py` — the gate's declared-skip fix and the registry refresh. That is a **version gap, not a
port error**, and the kit's own `behind_by` field exists to declare it; what it must not be is silent,
because a member holding a pre-fix gate reads green over a defect the fix removed.

**HELD is not ADOPTED — the second leg is the reason, and it is a surface no member has yet written
to.** The census reads the per-instrument disposition from `registry/factories/<slug>.json` →
`instruments.<slug>`, a map `tools/registry.py` gained at 17:29:36Z on 2026-09-27 — nineteen minutes
AFTER the census tool that must read it (17:10:24Z). The tool's own artifact reported the declared leg
as `unestablished` for every member **as a schema fact**, which was TRUE when written and false by
17:29, so the reader was extended and now checks the instrument's own entry first and falls back to
`kit` **labelled as the kit's**. The distinction the original reading existed to keep therefore
survives the fix, and it still decides the row: a `kit`-level `adopted` can never produce `ADOPTED`
here, because a member that declared its kit adopted has said nothing about this instrument.

**The reading is UNCHANGED by that fix, and that is the honest result:** every row below still reads
`unestablished`, because no member has declared into the surface yet. That is a member's own act, not
a gap in the reader — and the census renders the silence rather than defaulting it.

**Three of five members hold the complete declared set; two have declared a deferral with a reason and
a re-entry condition.** The distinction is the point of frame §7.2: a declared deferral
is a *state*, and only undeclared divergence reds. A census that reported "3 of 5" alone would erase
the difference between a member that measured itself and said why, and one that has gone quiet — so
the disposition column is not decoration, it is the half of the figure that a bare count destroys.

**The live path for a member that cannot take the whole kit is the MANUAL PORT, and it is the only
one.** `infra-factory` is the worked example: it took the declared set plus the closure as ordinary
files, wrote its own `registry/fleet.json`, and its runner executes all eight legs. No per-instrument
selector exists on the transport (§9.1 item 3) and none is required — which matters because a selector
would hand a member a *subset* of the closure, the exact partial-copy state §3 says raises rather than
degrades. A member adopting this instrument takes the FULL closure, by hand if necessary.

### 9.1 Five corrections from the adoption round, all measured

1. **A record in another factory's manifest does not satisfy step 2.** `ai-antispam` reported step 2
   already satisfied, citing a `registry/fleet.json` record carrying its own slug and job prefix. Read
   first-hand: `/root/ai-antispam/registry/` **does not exist**. The record it read is the
   **meta-factory's own** `registry/fleet.json` — a correct record of ai-antispam, sitting in a file
   the runner will never open from ai-antispam's tree, because the runner reads `REPO / "registry" /
   "fleet.json"` where `REPO` is the *runner's* root. This is the adjacency attribution this repo keeps
   ruling against: the row was read, the row was right, and it was not the row that binds.
2. **A peer's derived closure did not reproduce on the artifact it named, so the figure is
   withdrawn rather than restated.** `inferhub-watch` reported that `tools/field_predicate.py` imports
   `ledger_declaration` and `reconstruction` in turn, putting the transitive closure near 11 modules
   rather than 6. Read first-hand in their own tree, that file imports **`re` and `typing` only**
   (`:65-70`), and neither name appears in it in any form — so the claim does not reproduce against the
   artifact it names. Two facts sit beside it: their copy is **not** byte-identical to the template's
   (`cmp` differs at byte 671, line 12; theirs is dated 2026-09-21), so they hold a **stale** copy of the
   predicate; and the runner's own load resolves the name `oc_registry` to the FILE
   `tools/registry.py`, which is why a count taken over module *names* overstates the closure. A
   member's transitive dependencies may of course exceed §3's declared six — that is exactly why the
   frame requires the closure be **declared, never derived** — but that is a general caveat, not a
   figure. No figure stands here until it is measured on the tree it names.
3. **The sanctioned transport cannot single out this instrument.** Confirmed at source:
   `tools/kit_deliver.py` accepts exactly `--to` and `--dry-run`; a grep for `instrument|--only|--paths|
   selector` returns **0** hits. A member's choice is therefore the whole population or a manual port of
   the declared set — the wave does not ask for the former, and the second is what `infra-factory` did.

4. **The board legs and the two board gates need a CONVENTION, not just the files — and the gates, not
   the legs, are what a member feels.** `miidas` measured its own and `infra-factory`'s ledgers: 0 of 34
   and 0 of 65 post-invariant close rows carry `board=closed`, so `board_close_leg` examines 0. Those
   figures reproduce **exactly**. They are not fleet-wide: `ai-antispam` examines 1 and the TEMPLATE home
   examines 119 — the leg is not inert by construction, it is inert where the convention is absent. The
   sharper half is the GATE, which neither of us had stated: `test_close_board_recorded.py`'s `main()`
   reads the **LIVE** ledger and reds on every post-invariant close row missing the token, so the
   adopted tree exits `rc=1` with 65 problems. A member that adopts without the convention — or without
   deciding it is inapplicable to its board shape — turns two discovered gates permanently red. That is
   how `infra-factory` read it, and why it declared them forks rather than deleting them: deleting would
   fork the runner, which references both by path.

5. **§4's protection does not survive adoption unless `tests/gate_registry.py` travels with the
   gates — and this doc's §2/§3 never named it.** `infra-factory` measured the gap in its own tree: it
   carries no `tests/gate_registry.py`, and its `tools/audit.py` discovers gates by GLOB
   (`for test_file in sorted((repo_root / "tests").glob("test_*.py"))`). Discovery supplies the RUN but
   not the PAIRING, so §8 step 3 was unimplementable as written and the failure §4 exists to prevent
   was live in the only adopting tree: keep the predicate, drop the runner, keep a green file over an
   empty question. `TEMPLATE/tests/gate_registry.py` is a manifest row of class `closure`, byte-paired
   (`cmp` rc=0), stdlib-only. It belongs to the adoption's closure rather than §3's, because the runner
   does not load it — which is precisely why the omission survived four readings of this file. Found by
   the lane it affects, not by its author.

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