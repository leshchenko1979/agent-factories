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

**The concept's live state, measured 2026-10-05T21:18:44Z** (predicate: `enabled=1` rows in the
**ops profile home only**; `gate` = `length(trigger_cmd) > 0`; `session wake` = `deliver_to`
beginning `session:` — the only non-null delivery forms on this home are `session:<uuid>` and
`telegram:-1003…`, verified by distinct read):

| metric | rows |
|---|---|
| enabled | 35 |
| with a cheap gate | 11 |
| waking a session | 7 |
| gate **AND** session wake | 3 |
| with `set_goal` | 2 |
| gate **AND** session wake **AND** `set_goal` | **0** |

So on this home **no enabled row yet carries the full concept**: the two `set_goal` rows
(`inferhub-hq-pacemaker`, `factory-hq-pacemaker`) carry no gate, and four enabled session-wakes
carry no gate at all and burn a turn on every fire. This table is a snapshot of ONE home at ONE
instant, not a fleet figure — §9 counts member **adoption of the instrument**, a different
population, and the two must not be read as each other.

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
| 6 | `tools/publish.py` ↔ `TEMPLATE/tools/publish.py` | `standalone` | the publish-freshness leg. **SCOPE — the pusher holds its OWN pushes only.** Its 900 s grace window and 6 h cadence are **the pusher's declared bounds**: they bind `tools/publish.py` and nothing else, and they are not a property of the fleet. The leg this row feeds measures **LAG** — commits committed but not yet on the remote — and never cadence compliance. |
| 7 | `tools/registry.py` ↔ `TEMPLATE/tools/registry.py` | `standalone` | the registry read the legs share — also a CLI of its own |
| 8 | `tests/test_board_intake_recorded.py` ↔ `TEMPLATE/tests/test_board_intake_recorded.py` | `standalone` | the board-intake predicate |
| 9 | `tests/test_close_board_recorded.py` ↔ `TEMPLATE/tests/test_close_board_recorded.py` | `standalone` | the close-board gate |
| 10 | `tests/ledger_boundary.py` ↔ `TEMPLATE/tests/ledger_boundary.py` | `closure` | the boundary reader the runner loads by path (`LEDGER_BOUNDARY` in `patrol_host_state.py`) |
| 11 | `tools/ledger_declaration.py` ↔ `TEMPLATE/tools/ledger_declaration.py` | `closure` | imported by row 10 (`ledger_boundary.py:69`), so the runner needs it transitively |

**This is the ONE table the census parses** — `tools/instrument_census.py` derives the declared set
from these numbered rows rather than keeping a second list that would drift, so a shipped path added
here is measured there with no second edit. **A member is HELD only when all eleven are present.**
Rows 4–11 are the closure, and they are declared *here* rather than only explained in §3 because the
census's question is *"is the instrument complete here?"* — and a closure left out of the measured
set answers that question wrongly, which is the defect §3 describes.

**#315's presence leg adds no row to this table, and the set stays eleven.** The presence half is
carried by rows 1–3 — the runner, the predicate and the runner's wiring — which the instrument
already declares, so no member's HELD count moves and no new path has to ship. What the presence
leg reads beyond them is a *declaration* rather than a shipped path: `docs/processes.md` §3, a
register the member versions in its own tree (§6 below), not a file the kit delivers. A row added
here for a path the kit does not ship would make the census demand a TEMPLATE half that does not
exist, so the declaration lives in §6 and this table is left alone.

**Rows 10–11 were missing until a member found them.** infra-factory adopted this instrument and
reported that its tree needed five files rather than three, naming `ledger_boundary.py` and
`ledger_declaration.py` as the closure the boundary reader needs. Measured here: the runner loads
row 10 by path, and row 10 does `from ledger_declaration import …` at its line 69 — so a member
holding rows 1–9 alone reads **9/9 HELD while being unable to run**. That is the exact class §3
warns about, sitting in the instrument's own declaration rather than in a member's tree. Both are
manifest rows of class `closure`, so the kit always shipped them; the census simply was never asked
to look for them. Widening the set changes no member's state — all three adopters already hold 11/11
(measured 2026-09-27T19:0xZ) — it only makes the held leg mean what it claims to mean.

**One instrument, one executable, two gates — not eleven instruments.** Say it explicitly, because a
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

**The pacemaker-presence leg (#315) rides these SAME two gates — it is not a third.** The
thinness predicate asks *"is this row a thin wake?"*; it is silent about a row that does not
exist, and that silence is what board **#253** cost: the `factory-hq-pacemaker` row was
**deleted**, and no run failed, because a predicate over a list of rows cannot see the absence
of one. The presence half is therefore carried by the same pair:

| leg | predicate | runner wiring |
|---|---|---|
| **pacemaker-presence** | `pacemaker_presence_problems` + `declared_periodic_owners` + `row_wakes_session`, in `tests/test_cron_thinness.py` | `pacemaker_presence_leg` + `owner_sessions` + `live_pacemaker_presence_leg`, in `tools/patrol_host_state.py` |

**The expected set is INDEPENDENT of the table the leg judges** (frame §2 part 7, the control
law). WHO owes a pacemaker is read from the process register (§6), a **versioned** file, while
the live `cron_jobs` table is asked only whether a wake exists — a leg whose expectation came
from the table it judges would be self-consistent and would prove nothing. The wake notion is
the thinness gate's OWN (`SESSION_TARGET_PREFIX` + `WAKE_RE`), so a shape-2 row (a NULL target
whose prompt invokes a session notify) satisfies presence exactly as it satisfies thinness leg
(a); a `deliver_to`-only test would call the meta-factory's own Surveys and Triage pacemakers
ABSENT and RED on healthy rows. The leg is wired into `patrol_host_state.py`'s `main()` with
`presence_fn` injectable, so a probe drives it without a live register, fragment or binding set.
**Its sensitivity bound is per-OWNER, and it is stated rather than implied:** the leg fires when
an owner loses **all** its wakes, so deleting one row of several that wake the same owner is
**not** caught — the register declares owners, not per-row pacemakers, and a row-level check has
no stable independent declaration to read. Widening it to a per-row check is an owner decision,
not this leg's.

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
| `registry/fleet.json` → `job_prefixes` | `registry/fleet.example.json` | **the factory** | it IS the ownership declaration: the runner attributes each cron row to a factory by this field, never by the home a row sits in (measured 2026-10-05T21:18:44Z: all 18 ai-antispam rows live in the ops home) |
| `docs/processes.md` → §3 *The Meta-Factory Process Register* | **versioned in the tree** | **the factory** | it IS the pacemaker-presence leg's **independent declaration**: the `Process Owner` column (located by header name) names WHO owes a wake, and the presence leg reads it precisely so its expectation does not come from the `cron_jobs` table it judges. A register that dropped an owner would silently narrow the population the leg examines, so it is read on every run and never overwritten by an update |
| `docs/ledger-invariants.json` | `docs/ledger-invariants.example.json` | **the factory** | the DECLARED duty-receipt boundary (#78 clause b): the runner's `duty_receipt_leg` reads it through the one reader, and a tree that has not declared one gets `DeclarationUnavailable` — measured in `ai-antispam`, whose gate exits **rc=1** on the absent file |
| `registry/factories/*.json` | the adopter writes its own | **the factory** | the fragment store the attestation round reads and writes |
| `evidence/ledger.jsonl` | created on first append | **the factory** | the duty-receipt store — the run rows that make a duty's completion provable |
| `/tmp/<job-name>.log` | created by the job | **the factory** | the redirect log; its label must equal the job name, which is a contract between every pacemaker and the leg that reads it |
| `<git-common-dir>/publish-receipt.json` | created by the pusher | **the factory** | the pusher's record of its OWN last push — `{sha, instant, remote, branch, checkout}` (issues #284, #445). **ONE record per REPOSITORY, in the git COMMON dir, and never committed:** a receipt that rode the pushed history would move the remote tip PAST the sha it records, which is the one property the publish-freshness leg compares against. It sits in the common dir so every worktree of the repository reads the SAME record — a checkout-local copy made the leg compare a GLOBAL remote tip against whichever checkout happened to be reading (#445) — and `checkout` names the worktree that wrote it, so a reader can say WHO pushed rather than assuming it was itself. Its residual is LAST-WRITER-WINS: the record names the most recent push from ANY worktree, never this checkout's own. Written by `tools/publish.py`, read through the pusher's own `read_receipt`, and never a ledger row — the pusher is not a lane and the ledger's actor set is closed |
| `registry/kit.json` | generated | the **kit** | the version source (§5) — regenerated, never hand-edited |

**A surface absent from this table is absent by measurement, not by omission.**

### 6.1 Extension surface — this instrument has none

**The frame's §6.5 owes this instrument ONE of two statements at its naming site, and this is the
second of the two it allows: this instrument has no extension surface — member subject matter lives
outside it.**

The claim is measured, not asserted. Against §6.5's own four-part contract — read from the live
specimen, `ledger.md` §3 — neither of the two surfaces §6 names as member-writable qualifies:

| §6.5 contract part | `registry/fleet.json` | `docs/ledger-invariants.json` |
|---|---|---|
| **1. shipped EMPTY** — the template's copy declares nothing | **fails** — it ships a populated specimen (`example-factory`) | holds — it ships `{"invariants": {}}` |
| **2. a declaration ADDS; it never removes or redefines a core entry** | not the discriminator — a prefix list is additive by construction, and there is no core-entry vocabulary here to shadow | not the discriminator — same |
| **3. ONE reader serves the instrument's paths** | holds — `load_fleet_manifest` | holds — `tests/ledger_boundary.py` |
| **4. an addition a SECOND factory needs PROMOTES to the core** | **fails** — a `job_prefix` is per-factory identity and can never promote | **fails** — an `invariants` key is keyed on the tree's OWN gates, never on a name a member chose |

Both are manifest class **`seed`** — configuration a member instantiates under its own name, which is
exactly how §6 names them. Part 1 fails for one and part 4 for both, so a "contract" that would hold
on two of four parts is not an extension surface; claiming one here would be the over-claim §6.5
exists to prevent.

**This instrument's own vocabulary is CLOSED, and it lives in shipped code.** The runner's one
closed-vocabulary declaration is `deferred_legs()` — an entry must declare an integer `tracker` and
`claims` that are checked against HEAD on every run — and it sits INSIDE
`tools/patrol_host_state.py`, a manifest-class `standalone` file. An entry added there edits a shipped
file, which is a **FORK** by §6.4's test, not an extension by §6.5's. The rest of the declared set is
`standalone` in the same way (the law doc, the runner, its two gates), so a member's content enters
this instrument only as **data**, at the two seed surfaces §6 names.

**What a member's subject matter is, and where it therefore lives.** Which factories exist, which cron
rows are theirs, and when their ledger invariants landed are declarations a member makes in its own
tree — in those two seeds, and in its own `registry/factories/<slug>.json` fragment (§8 step 5). None
of them adds a NAME the instrument's core did not already know, and that is the whole difference
between a declaration and an extension. The member's duty here is **cited, never authored** (frame
§6.5, and that frame's own scope): O1's migrate-or-declare-or-defer disposition for a copy it already
holds, and O4's duty to declare what its instrument accepts — or to state why it has none.

### 6.2 The one-time sweep of the legacy receipt — and why it is not a `.gitignore` line

**The receipt row above describes where the record lives NOW. It does not reach the copies already
on disk**, and that gap is what #452 measured: the migration to the common dir moved the WRITER, so
every checkout that had already pushed kept the pre-#445 `evidence/publish-receipt.json` behind.
Nothing creates it any more and nothing declares it, so the placement leg reads it as a **true
mismatch** — a JSON file in `evidence/`, a directory that admits only markdown and jsonl. Measured
2026-10-09: present in four of six checkouts, absent in the two that had never pushed.

Two halves, and only the first is automatic:

1. **The pusher sweeps the checkout it pushes from.** On a successful push, `tools/publish.py`
   removes `<repo>/evidence/publish-receipt.json` if it is there — **INERT when absent** (one stat),
   so a member that never carried the path pays nothing and its round reports no removal. This is
   what makes the instrument's existing promise true over the carried-over population too: no
   checkout-local receipt survives a push.
2. **A checkout that will never push again is STRUCTURALLY UNREACHABLE by that leg** — it runs
   wherever a push runs, and there is no push. That population is what the **one-time sweep** is
   for. It is run ONCE per repository, by hand, after which half 1 holds it:

   ```
   git -C <repo> worktree list --porcelain | awk '/^worktree /{print $2}' \
     | while read -r wt; do rm -f "$wt/evidence/publish-receipt.json"; done
   ```

   `worktree list` is the reachability route: it names every checkout of the repository, so one run
   covers them all rather than one per checkout. `rm -f` is inert on a checkout that never had one.

**NOT a `.gitignore` line, and the difference is not stylistic.** Declaring the path would put it OUT
of the placement population — printed by name as ignored, and therefore never reported — which is an
allowlist wearing gitignore's clothes, suppressing a finding that is true (`tools/hygiene.py:783-784`).
The remedy is to remove the file, never to teach the reader to stop seeing it.

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
| `test_a_declared_owner_with_no_wake_is_named_by_role` | `tests/test_cron_thinness.py` | the presence predicate BITES: an owner with no wake is NAMED by role and session, over a populated row set |
| `test_a_woken_sibling_is_clean_under_the_SAME_read` | `tests/test_cron_thinness.py` | the control: the same read clears a woken sibling, so the leg is not a constant RED |
| `test_shape_two_prompt_notify_satisfies_presence` | `tests/test_cron_thinness.py` | a NULL target whose prompt invokes a notify IS a wake — the half a `deliver_to`-only test gets wrong |
| `test_a_wake_naming_ANOTHER_session_does_not_satisfy_this_owner` | `tests/test_cron_thinness.py` | the negative control for the prompt leg: presence keys on the uuid, not on a notify's mere presence |
| `test_the_register_parse_locates_the_owner_column_BY_HEADER` | `tests/test_cron_thinness.py` | the column is found by NAME, so an inserted column cannot hijack the owner set while still returning something |
| `test_the_pacemaker_presence_leg_NAMES_an_owner_with_no_wake` | `tests/test_patrol_host_state.py` | the RUNNER's presence leg bites over a synthetic register+fragment+rows |
| `test_the_pacemaker_presence_leg_is_QUIET_when_a_woken_sibling_is_present` | `tests/test_patrol_host_state.py` | the runner control, under both wake shapes |
| `test_the_pacemaker_presence_leg_PRINTS_its_examined_population` | `tests/test_patrol_host_state.py` | coverage is printed: the register, the owner count and every owner with its wake travel with the verdict |
| `test_the_pacemaker_presence_leg_fails_OPEN_when_the_register_is_absent` | `tests/test_patrol_host_state.py` | an unreadable DECLARATION is NOT RUN with its reason, never a clean read |

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
5. **Declare the adoption, in your fragment.** A complete tree is not an adoption on the record —
   `registry/factories/<your-slug>.json` carries an `instruments` map, and the census needs
   `instruments.<this-instrument>` before it will read anything but silence:

       "instruments": {"pacemaker": {"state": "adopted", "green": true, "measured_at": "<ISO instant>"}}

   - `state` is one vocabulary for every adoption declaration: `adopted` · `partial` · `deferred` ·
     `not-applicable`. `deferred` and `not-applicable` **require a non-empty `reason`**; a reasonless
     one is refused, because "behind by N, deferred because X" is the clause's own wording and a
     deferral with no X is an undeclared state wearing a declared label.
   - **`adopted` requires `green: true`** — HELD and GREEN are independent axes (frame §7.2), so
     adoption cannot claim one and leave the other unspoken. `green` is YOUR gate's verdict over YOUR
     tree; nobody else can measure it for you.
   - Validate before you commit: `python3 tools/registry.py validate <your fragment>` returns rc=0 for
     a conforming block and **rc=1 with the axis named** for one that omits `green`.

   **Why this step is not optional, measured on 2026-09-27:** three members held this instrument's
   complete set as §2 then declared it (nine paths) and **not one fragment in the fleet carried `instruments`**, so the census
   reported `HELD-UNDECLARED` for all of them and could record no adoption, for any instrument,
   whatever the trees contained. A declared `partial` or `deferred` is a **state, not a failure** — it
   is the one thing the census can render. Silence is the only reading it cannot distinguish from a
   member that never considered the instrument.

**Four prerequisites, and they fail in different places.** Step 1's closure fails **loud** (§3) — the
runner crashes. Step 2's manifest also fails **loud**, and earlier: the `legs = [...]` expression raises
before any leg runs. Step 2's SECOND declaration fails loud in the other entry point: a tree with no
`docs/ledger-invariants.json` gets `DeclarationUnavailable` from the gate rather than the runner
(measured in `ai-antispam`, rc=1). **Step 5 fails the opposite way — in SILENCE:** nothing crashes and
nothing reds; the census simply reads `HELD-UNDECLARED`, which is indistinguishable in the artifact
from a member that never looked. The board convention (§9.1 item 4) fails **quiet in the legs and loud in the
gates**: the runner completes and honestly reports `examined 0`, while two of the discovered gates red
on every post-invariant close row the member's ledger holds. A member whose board surface is not
GitHub — one whose issue board *is* its own ledger — either carries the token convention or has those
two gates declare an INAPPLICABLE-skip carrying the reason. Adopting without deciding is the one shape
that leaves the member's own suite permanently red.

## 9. Adoption census

**TWO predicates, stated separately because they answer different questions — and a figure must carry
the one it came from.**

- **HELD** — `os.path.isfile(member.repo / p)` for each of §2's **eleven** declared paths. This is
  `tools/instrument_census.py`'s predicate, and its published artifact is the citable form. It reads
  a **working tree**, so a member reads 11/11 while its own **commit** carries fewer: measured
  2026-09-27T21:42:07Z, `inferhub-watch` reads 11/11 held and a clone of its `HEAD` (`dbdab59`) carries
  **8 of the 11**, the three absent being rows 1, 3 and 9 (`tools/patrol_host_state.py`,
  `tests/test_patrol_host_state.py`, `tests/test_close_board_recorded.py`). Read HELD as *present on
  disk*, never as *in the repo* — a third axis beside held-vs-current, and the one a fresh clone settles.
  (An earlier revision of this bullet read 6 of 11 / five untracked; the member has since committed
  two of them, which is the reference moving again — hence the member sha beside the figure.)
- **CURRENT** — byte-identity of each held file against the template half (`cmp -s`). A member can
  hold every path and still be **behind**: adoption is a revision, not a copy.
- **What a clone cannot see has TWO mechanisms, and they differ in who is blind.** A file is missing
  from a fresh checkout either because it is **untracked by design** (`inferhub-watch` row 9 — its
  declared carve-out) or because it carries an **uncommitted edit** (`infra-factory` row 8, `M` in its
  tree: disk `e3fd9f1a…` == TEMPLATE HEAD while its own HEAD holds the pre-repair `49ed31df…`).
  Both are invisible to a clone; only the second is invisible to its own operator too, and the remedy
  differs by mechanism — the untracked file needs a decision, the uncommitted edit needs a **commit**,
  not a re-copy. On one row the on-disk and committed readings therefore point in **opposite**
  directions, each correct for its own predicate (frame §7.5).

**Scope:** the member fragments in `registry/factories/*.json`. **Instant:** HELD read by
`tools/instrument_census.py` at **2026-09-28T02:40:27Z** — the stamp the artifact
`evidence/instrument-census-pacemaker-2026-09-28.md` carries, so this citation resolves to a receipt
that agrees with it. **The artifact RE-STAMPS on every run** — the tool always writes it
(`--stdout` only *also* prints) — so read the stamp from the copy in hand rather than from this line.
An earlier revision of this sentence cited `2026-09-27T19:16:27Z` and called it the artifact's *first
line*; measured against the committed copy it matched neither, since the stamp rides the artifact's
`Read at` / `Instant:` lines and moves every run. Its readings were unaffected by that re-stamp —
only the stamp moved, which is the reference moving while the measurement stands still. That artifact
reads the **eleven**-path set §2 declares (its predecessor at 18:58:07Z read nine). **CURRENT** read by
blob hash — `git rev-parse HEAD:<path>` on both sides, so the comparison is like-with-like, plus
`git hash-object` for a working-tree file — against the **committed** template halves
(`git show HEAD:TEMPLATE/<path>`, not a working tree other lanes are editing) at
**2026-09-28T02:42:06Z** at HEAD `2884edf` over the same eleven paths in the same six member repos,
with the authoring repo as a **positive control**: it must read 11/11 against itself, and did.
Earlier instants: 07:27:09Z, 08:38Z, 15:19:17Z, 18:49:37Z, 19:05Z, 21:21:50Z.

**The reference moves under a census, and it has now moved twice on the same rows.** Row 10
(`tests/ledger_boundary.py`) changed at 19:58:46Z (`3793de5`), twenty-three minutes after a 19:35
reading that had called all three holders byte-identical. Then `94f69b8` (2026-09-28T01:08:03Z,
*"the shipped tree's own audit is EXECUTED"*) moved **three declared rows at once — 8, 9 and 10** —
and every adopter's declaration predates it. So all three now lag on at least one declared row
**without any of them changing a file**: the counts moved, the members did not, and every measurement
was correct when taken. That is the purest form of the class. The predicate that survives is the
frame's (§7.5): read the **committed** revision and name its sha beside the instant, because a figure
without the sha is unreproducible the moment anyone else runs it. **Resolve the member's repo from its
own registry fragment — never from `/root/<slug>`.** `infra-factory` lives at `/root/vds-servers`; a
probe that assumed the slug returned a clean *all eleven absent* for a directory that was never there,
which reads exactly like a member that adopted nothing. **And the authoring repo is the probe's own
positive control:** a reading in which the SOURCE differs from its own standard is not a finding about
the fleet, it is a broken instrument — which is how both defects in §9.1 item 8 were caught.

| factory | held | current | disposition |
|---|---|---|---|
| `infra-factory` | **11/11** | 8/11 | **ADOPTED** — the fleet's FIRST declared instrument row, and the member that found a defect in this declaration. Its fragment carries `instruments.pacemaker` = `state: adopted`, `green: true`, `behind_by: 0`, `measured_at 2026-09-27T22:12Z`, so the census reads **ADOPTED** on a live member rather than `HELD-UNDECLARED`. Its own gate: `rc=0`, **101 check(s), 1 SKIPPED**; `cron_thinness` `rc=0`. It re-copied all five files this instrument's briefs flagged — including a fourth the brief did not name (`test_board_intake_recorded.py`) — plus the boundary reader and `ledger_declaration` closure. **It adopted five files rather than three**, which is why §2 now declares eleven paths (§9.1 item 6). It also corrected my framing: the pre-fix gate did **not** crash in its tree, it read green while never exercising the reader's declared SKIP path, so *coverage gap* is the true statement and *adopting fixed a crash* must not travel. **CURRENT 8/11, measured at HEAD `2884edf` (2026-09-28T02:42:06Z): rows 8, 9 and 10 differ and all three are LAGS** — each holds the pre-`94f69b8` revision, so this member is behind by a **revision**, not by a port: re-copy three files and it is current. Its `behind_by: 0` was true at 22:12Z and is stale now by the standard's own move, not by any error in its measurement. Its `reason` field carries the one qualifier honestly: two board gates are RED on a **declared inapplicability** — its issue board IS its ledger, one surface, so a board/ledger close-agreement predicate has nothing to agree about (§9.1 item 4) — filed at ledger n=611 and routed to the Instruments-methodology lane. Its `reason` also carries the two wrong mechanisms §9.1 item 7 corrects. |
| `ai-antispam` | **11/11** | 8/11 | **ADOPTED** — declared `adopted · green=true · behind_by 0` at `measured_at 2026-09-27T20:24Z` and the declaration is in the store, so the census reads **ADOPTED**. The patrol pair landed (`95b7388`, re-ported to the fixed upstream) and the pin re-vendored (`657108d`); the gate is **registered as its own audit row, gate 14**, and reads `rc=0` / 102 checks in BOTH its script and pytest forms — the declared-skip fix turned a build-push red into a green gate, after a 15.5 h block earlier the same day. **CURRENT 8/11 at HEAD `2884edf` (2026-09-28T02:42:06Z): rows 8–9 differ as its DECLARED BOARD FORKS** (own anchor + the #59 exemption surface, each a decision) **and row 10 differs as a LAG** (the pre-`94f69b8` revision). Its `behind_by 0` was true at 20:24Z — when it was the one adopter current on row 10 — and the standard's 01:08:03Z move made it 1 without this member touching anything. |
| `inferhub-watch` | **11/11** | 6/11 | **ADOPTED** — declared `adopted · green=true · behind_by 1` at `measured_at 2026-09-28T02:36Z`, and its own reason separates the two axes correctly: TRACKEDNESS (8 of 11 in its commit tree; 3 untracked) from REVISION LAG. **CURRENT 6/11 at HEAD `2884edf` (2026-09-28T02:42:06Z): three paths are ABSENT from its commit tree** — rows 1, 3 and 9 (`tools/patrol_host_state.py`, `tests/test_patrol_host_state.py`, `tests/test_close_board_recorded.py`), its declared carve-out, present on disk and in **no clone**; **rows 8 and 10 differ and both are LAGS** (row 8 pre-`94f69b8`; row 10 `ce314a20…` = `3878936`'s revision, two moves deep). Its gate reads `rc=0`, 101 checks, 1 SKIPPED. **Its earlier row here was wrong in two particulars and is withdrawn**: it said the runner *still raises `FleetManifestError` until it writes* `registry/fleet.json`. Measured, `registry/fleet.json` exists, is **tracked**, and carries `profile_root` / `profile` / `factories[]` with `job_prefixes ["inferhub-"]`; the runner **completes all eight legs** and `rc=1` is a **verdict, not a crash** — 4 problems over 9 open issues examined, 4 cron rows attributed and judged. A false *cannot start* in a census row sends the next adopter to fix something already fixed. Its declared `behind_by 1` does not reproduce on my reading of the same predicate — I count **two** lagging tracked rows, 8 and 10 — and the field is the member's own measurement, so the discrepancy is recorded here rather than silently reconciled. |
| `miidas` | 1/11 | 1/11 | DEFER (declared) — behind by 10 of 11. Its **transport blocker is discharged**: the manual port proved in `infra-factory` needs no selector (§9.1 item 3), and the requirement was relayed to it 2026-09-27T08:35:59Z. The **board-convention prerequisite** (§9.1 item 4) stands. |
| `opencrabs-dev` | 0/11 | 0/11 | DEFER (declared) — `registry/` **does not exist** in its tree at all (`ls` rc=2). Its reason is SCOPE rather than effort: the prerequisite (`registry/kit.json` + `tools/kit_pin.py`) does not bootstrap one instrument — it **enrols the factory in the kit manifest system for every instrument at once**, a fleet-level decision that a pacemaker brief would otherwise decide by side effect. Re-entry: when it enrols in the kit for ANY instrument. |

**Two adjacent columns can both read `absent` and mean different things.** The census's reload-link
column is about the member's OWN law-survival symlink (step 4, optional and the member's act); the
declares column is about the fragment's `instruments` entry. `infra-factory` reads `absent` in the
first and `adopted · green=true` in the second, which is a complete adoption with no reload link — not
a partial one. Raised by the Delegate from the artifact rather than from a defect report, and recorded
here because the header that disambiguates them is a scroll away.

**The version gap closed, reopened on one path, then reopened on three at once.** At the 18:49Z
reading all three were 6/9 CURRENT; `infra-factory` and `inferhub-watch` re-ported and read 11/11 at
19:05Z; `3793de5` (19:58:46Z) moved row 10 and left `ai-antispam` the only adopter current on it; then
`94f69b8` (2026-09-28T01:08:03Z) moved rows **8, 9 and 10** and left **all three** behind — a pure
reference move, since none of them changed a file. The lesson that survives the specific numbers is the
one `infra-factory` paid for: a member can hold every declared path and still be behind, because
**adoption is a revision, not a copy** — and the kit's `behind_by` field exists to declare it. Silence
is what must not happen, since a member holding a pre-fix gate reads green over a defect the fix
removed.

**HELD is not ADOPTED — the second leg is the reason, and it is now written by a member.** The
census reads the per-instrument disposition from `registry/factories/<slug>.json` →
`instruments.<slug>`, a map `tools/registry.py` gained at 17:29:36Z on 2026-09-27, nineteen minutes
after the census tool that must read it (17:10:24Z). That window was real and it is **CLOSED**: the
reader was extended (`84a94ba`) to check the instrument's own entry first and fall back to `kit`
**labelled as the kit's**, and re-run at HEAD `0aebae9` it publishes **ADOPTED** for `infra-factory`
rather than `unestablished` for all six. The distinction the original reading existed to keep therefore
survives the fix, and it still decides the row: a `kit`-level `adopted` can never produce `ADOPTED`
here, because a member that declared its kit adopted has said nothing about this instrument.

**The reading has MOVED three times, and all three holders have now declared.** At the 17:48:33Z
read every row was silent; `infra-factory` read **ADOPTED** from 2026-09-27T18:49:37Z — the fleet's
first declared instrument row — and by 2026-09-28T02:37:37Z **`ai-antispam` and `inferhub-watch` read
ADOPTED as well**. Three of the five members, and three of the four non-source members, carry a live
declaration. Every one was written by the member's OWN HQ (`tools/registry.py`: the fragment is
written by that factory's HQ and by nobody else) and transcribed by the Delegate — never by this
lane, because `green` is the member's own verdict over the member's own tree, and a declaration
written from here would be the manufactured adoption the census's two-leg design exists to catch.

**Three of five members have declared ADOPTED; two have declared a deferral with a reason and
a re-entry condition.** The distinction is the point of frame §7.2: a declared deferral is a *state*,
and only undeclared divergence reds. A census that reported "3 of 5" alone would erase the difference
between a member that measured itself and said why, and one that has gone quiet — so the disposition
column is not decoration, it is the half of the figure that a bare count destroys. **No row reads
`HELD-UNDECLARED` at this instant**, which is the state the whole round existed to eliminate: every
member either holds the complete set with a declaration behind it, or has declared what it lacks and
why.

**The live path for a member that cannot take the whole kit is the MANUAL PORT, and it is the only
one.** `infra-factory` is the worked example: it took the declared set plus the closure as ordinary
files, wrote its own `registry/fleet.json`, and its runner executes all eight legs. No per-instrument
selector exists on the transport (§9.1 item 3) and none is required — which matters because a selector
would hand a member a *subset* of the closure, the exact partial-copy state §3 says raises rather than
degrades. A member adopting this instrument takes the FULL closure, by hand if necessary.
### 9.1 Eight corrections from the adoption round, all measured

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

6. **The declared set was under-declared, and a member's adoption found it.** §2 declared nine paths;
   the true set is eleven. `infra-factory` adopted the instrument and reported that its tree needed
   **five files rather than three**, naming `tests/ledger_boundary.py` and `tools/ledger_declaration.py`
   as the closure the boundary reader needs. Measured here, it is right and worse than a member's
   local note: `LEDGER_BOUNDARY` in `patrol_host_state.py` sets `REPO / "tests" / "ledger_boundary.py"`,
   the runner loads it by path in `_BOUNDARY_READER = load_module("ledger_boundary", LEDGER_BOUNDARY)`,
   and `ledger_boundary.py` does `from ledger_declaration import …`.
   So a member holding rows 1–9 alone reads **HELD — complete set — while being unable to run at
   all**: the runner raises on the missing path-load. That is the exact class §3 warns about, sitting
   in the instrument's own declaration rather than in any member's tree. Both files are manifest rows of class `closure`, so the kit always shipped them;
   the census was simply never asked to look for them, because §2 never listed them. Widening the set
   changed no member's state — all three adopters already hold 11/11 (measured 19:05Z) — it only made
   the held leg mean what it claims to mean. The general form is not mine to encode: **a declared set
   derived from what the manifest classes, rather than from what the executable loads, under-declares
   by exactly the paths it reaches indirectly.** Routed to the frame's author as a cross-instrument
   clause rather than patched here.


7. **A citation can carry the right number in the wrong ROLE, and this one sits in a durable field.**
   `infra-factory`'s `reason` justifies its `gate_registry.py` divergence with two claims that do not
   reproduce. (a) *"resolves `<cwd>/tools/audit.py`, which is `/root/tools/audit.py`, absent"* — the
   source is `REPO = Path(__file__).resolve().parent.parent`, so it resolves the **member's own repo**,
   and the measured failure is `ImportError: cannot import name 'render_tree_line' from 'audit'
   (/root/vds-servers/tools/audit.py)`: the **symbol** is absent from that member's deliberately-forked
   audit, not a path outside the tree. (b) *"`gate_registry.py`'s own law at `:671`"* — `:671` sits
   inside the `test_kit_names.py` entry of the same file; the clause meant (*each absent one FAILS
   naming it*) is at **`:687`**. Both are the class this record keeps returning to: an arithmetic
   check on the number passes, and only reading the line settles the role. The fork itself is genuine
   and justified — the template registry registers two gates whose symbols this member's audit does not
   carry, and its second gate is **not present in that tree at all** (and its `registry/gates.json`
   ships only as `gates.example.json`, a manifest `seed`) — so the correction is to the mechanism, not
   to the decision. The general form (*a citation asserts a role; no recomputation of its number tests
   that*) is the frame's reading discipline and is supplied there, not encoded here.
8. **This instrument's own census probe was wrong twice, and a positive control is what caught both.**
   Each defect returned a *uniform* verdict that looked like a finding. (a) The declared-set table's
   right-hand cell **already carries the `TEMPLATE/` prefix**, and the probe prefixed it again, so every
   comparison ran against `TEMPLATE/TEMPLATE/…` — a path that never existed — and returned *every
   member 0/11*, including the member that IS the authoring repo. (b) The disk axis compared a
   **sha256 of the file's contents** against the other side's **git blob hash**: different quantities
   inside one comparison, so every row read *"[disk differs from commit]"* — again including the
   source against itself. The tell is the same in both and it is the general rule: **the authoring repo
   is the probe's own positive control.** If the SOURCE does not read clean against its own standard,
   the instrument is broken and nothing below it is a finding. A probe that returns one uniform answer
   for every subject has not measured the subjects; it has measured itself. The corrected probe reads
   **11/11** for the source and is the one whose figures §9 now carries. The general form (*a sweep
   that must prove an absence carries a control that can FAIL*) is routed to the frame's author.
## 10. Where this instrument's law lives

This file is the instrument's **declaration**. The law it **takes over** is still stated elsewhere,
and the move is deliberately not in this commit. This section is therefore a **declared obligation
with a checkable exit**, not a claim that the move has happened:

| today's home | what it carries about this instrument |
|---|---|
| `skills/meta-factory/state.md` (the clause tail of `SKILL.md` §11 *State — every surface has one writer*) | the **duty receipt** (a `run` row written by the woken lane, declaring `receipt_subject`) and the **redirect log** (its label equals the job name) |
| `docs/best-practices.md` P7, P28 | the thin-wake rule itself |
| `tools/patrol_host_state.py` | the enforcement of all three, as machine-checked legs |

**Two facts settle how that move must be done, both measured 2026-09-27:**

1. **No surface cites those clauses by number.** A fleet-wide sweep of the `SKILL.md:<N>` form, plus
   bare `:N`, `line N` and `§N` forms, returned **zero** citations of any of them. The risk is
   therefore not a broken citation.
2. **What binds them is code, and code is the stronger citation.** The duty-receipt contract is
   machine-enforced in `tools/patrol_host_state.py`, so the pointer row left behind must name **the
   enforcing line**, not a prose line that a later edit can move without any gate noticing.

**Owner of the move: HQ.** Skill-text authorship is HQ's, not this lane's (frame §8: an instrument
owner supplies text to the lane that owns a file; they do not land it there). **Exit criterion, and
it is checkable without reading intent:** the move has landed when the clause text is present in this
file and `skills/meta-factory/state.md` no longer carries it. The measurable handle is the token the
duty-receipt contract keys on — `receipt_subject`: measured 2026-10-05T21:18:44Z, `state.md` carries
it **2×** (this file's table row above cites it once as content; this sentence is the count, not the clause). The move is done when that count in `state.md`
reaches 0 and the text sits here. **Until then, SKILL.md remains the operative home and this file is
its declaration and its citation target** — this file does not claim a move it did not make.