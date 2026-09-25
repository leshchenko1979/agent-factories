# Bootstrap — create a new factory

An ordered procedure. Each step ends with **evidence** — something read back
from live state, not from memory. Do not proceed past a step whose evidence is
missing.

Fill the [variables](../docs/product.md#fill-in-variables) first; every
skeleton in this directory uses them as `{{PLACEHOLDER}}`.

---

## Step 0 — Decide the shape

Write down, before creating anything:

| Question | Answer goes to |
|---|---|
| One sentence: what does this factory deliver? | `PURPOSE` |
| What is the smallest thing that proves it works? | the first issue |
| Which roles does it need? (`HQ` **plus at least one lane to delegate to** — `HQ` alone is not a valid answer) | `ROLES` |
| Which domain topics does it need? | `DOMAINS` |
| Which add-ons? | `ADDONS` → [docs/addons.md](../docs/addons.md) |
| What command can decide "done"? | `GATES` |
| Which **surface** does it run on? | `SURFACE` |
| Which **harness** do its agents run under? | `HARNESS` |

**Rule:** if you cannot name the smallest thing that proves the factory works,
you are not ready to bootstrap. A factory with no first issue has an
unfalsifiable process — the failure mode is a beautiful scaffold nobody uses.

---

## Step 0b — Take the bindings

A factory runs on **a chat surface** and **an agent harness**. Take exactly one
of each, and read both pages end to end before creating anything:

- a [surface binding](../docs/addons.md#surface) — where the human watches the
  work, how a work unit gets its own named place, how a message is routed there;
- a [harness binding](../docs/addons.md#harness) — how a session loads its law,
  how a lane is addressed directly, what schedules a recurring process.

**Do not copy their mechanics into the core law.** The core states requirements;
the bindings state how those requirements are met on one product. If you find
yourself writing a product name into `SKILL.md` in a sentence that states
mechanics, move it to the binding — that is the [leak test](../TEMPLATE/README.md#the-leak-test).

**Evidence:** the two binding pages named, and the `{{SURFACE}}` / `{{HARNESS}}`
rows filled in §2 of the law.

---

## Step 1 — Create the repository

- Name it after the factory: `{{REPO}}`.
- Enable **issues**. The board is the task list; a factory with issues off has
  no task list.
- Add `AGENTS.md` from [`AGENTS.md.tmpl`](AGENTS.md.tmpl) with placeholders filled.
- Add `ONTOLOGY.md` from [`ONTOLOGY.md.tmpl`](ONTOLOGY.md.tmpl).
- Add `processes.md` from [`processes.md.tmpl`](processes.md.tmpl).
- Add `docs/adr/` with a `0001-` decision record if the add-on `platform` is
  taken.
- Initial commit.

**Evidence:** repo URL, and `gh repo view {{REPO}} --json hasIssuesEnabled`
returning `true`.

---

## Step 2 — Create the chat surface

Create a **forum group** titled `{{CHAT}}`. Not a group with topics bolted on
later — a forum from the start; converting afterwards leaves every existing
message stranded in `General`.

Create the spine topics, in this order:

| Topic | Purpose |
|---|---|
| `HQ` | The HQ lane: process work, rulings, gates |
| `Triage` | Intake, routing, enforcement |
| `{{DOMAIN}}` … | One per domain topic, in the order the factory will use them |

Do **not** create work-unit topics now. They are created at spawn time, named
`Worker — #N <title>`, and renamed to `Done — #N <title>` on close.

`Worker` is nevertheless a **required** member of `ROLES`. `HQ` implements
nothing — it is kept idle for incoming managerial work — so a factory without an
implementation lane has nowhere to put its first work item. The lane is created
with the work unit, not with the spine; what must exist from the start is the
role, so the first dispatch has a destination.

Promote the factory bot to admin with `manage_topics`. Without it the bot
cannot create or rename the work-unit topics, and the whole naming law is
inoperable.

**Stand up each lane.** Creating a topic does not create its lane. A topic's
session is created by its **first inbound message** — an outbound post never
claims one — so a freshly created topic is addressable (deliveries target its
`thread_id`) but unowned: nobody is listening in it yet. Until a lane exists,
anything sent to it is parked, and "the lane is up" is an assumption rather than
a fact.

So the step that actually creates a lane is an **inbound message in its topic**.
The operator writes one line into each spine topic — the role it is to play
(`You are <role>`) — and the daemon binds a session to that topic on arrival.

Two consequences, both load-bearing:

- **Read the lane id back from live state** (`session_bindings` for the chat and
  `thread_id`), and re-read it before every send. A lane id carried over from an
  earlier turn — or worse, a one-shot subagent's id recorded as if it were a lane
  — is how dispatches end up parked against a session that no longer exists.
  A subagent session has no channel binding; it can never be a lane.
- **A topic post is owner visibility, never dispatch.** Writing the role line
  into a topic stands the lane up; it does not brief it. Brief the lane by
  `session_notify` to its session id.

**This is a mechanical choke point, not a design choice — say which one it is.** The operator
writes the line because a binding is created only by an **inbound** message, and no instrument
in the factory's tool set produces one. That is a property of the harness, not a decision
anyone made — and the distinction matters, because a work unit gets its own topic (P5) and
works in it, so this act recurs **per work unit**, not once at bootstrap. A factory whose
lanes can only be created by the founder has the founder in the loop permanently, whatever
its other criteria say.

So: enumerate the acts that still require the operator, count them, and re-run the count on
the measurement cadence (P26). A deliberate approval gate belongs on that list and stays. An
act that needs the operator only because no instrument exists is a candidate for
mechanization — and the count falling is the evidence that the factory is transferable.

**Lane reuse over lane spawning:** To minimize operator friction and avoid topic clutter,
factories should prioritize reusing established persistent worker lanes over spawning a new topic
session for every small subtask. When fresh lane instantiation is mandatory and native harness
mechanization is unavailable, the temporary workaround is to use the surface's userbot sending tool
to post the initial inbound role line on behalf of the operator (see surface add-on notes).

**Retiring a place:** the chat map will accumulate dead entries — a group
superseded by a forum, a group left behind by a migration. A place that still
exists and still has a binding is a place a delivery can still land in, so a
stale place is retired deliberately and the retirement is recorded. The rules
and the order of operations are in `topics.md` and the surface binding.

**Evidence:** for each spine topic, the session id from `session_bindings`; every topic id
read back from live state (`GetForumTopics` or equivalent) — never from the UI, never from
the creation response alone; and the counted list of acts that still require the operator.

---

## Step 3 — Write the process law

Copy [`SKILL.md.tmpl`](SKILL.md.tmpl) into the factory's skill directory and fill it.
Split role-specific procedure into the files in [`roles/`](roles/) — one per
role in `ROLES`.

The law must state, at minimum:

- the three legs (law, chat, board) and where each lives;
- that `HQ` implements nothing and delegates every work item to a lane;
- how a lane is briefed (a session notification to the session UUID — never a
  chat post);
- how a work unit closes (rename the topic, evidence in the topic);
- what happens after a context compaction (reload the law **first**);
- which add-on rules are in force.

Version it. Mirror it to a repo so the law is diffable and survives the
session that wrote it.

**Harness link (OpenCrabs profile symlink):**
If running under OpenCrabs, the active profile's skill loader resolves role cards
from `~/.opencrabs/profiles/<profile>/skills/<name>`. Create an explicit symlink from
the profile directory to the repo skill directory during bootstrap:
```bash
ln -s /path/to/repo/skills/{{NAME}} ~/.opencrabs/profiles/{{PROFILE}}/skills/{{NAME}}
```

**Evidence:**
- the skill file path, and the version string in it;
- for OpenCrabs: `test -L ~/.opencrabs/profiles/{{PROFILE}}/skills/{{NAME}} && test -d ~/.opencrabs/profiles/{{PROFILE}}/skills/{{NAME}}`.

---

## Step 4 — Write the ontology

Fill [`ONTOLOGY.md.tmpl`](ONTOLOGY.md.tmpl): the canonical terms, one definition each,
and a **banned-synonyms table** mapping every word the team actually says to
the term that is allowed.

Then enforce it — a test that fails the build when the code uses a banned
synonym. An ontology nobody can violate is documentation; an ontology a test
enforces is law.

Write the gate so it **parses the banned-synonyms table** rather than repeating
the list in code: with the table as the source of truth, adding a row is what
enforces it, and the ban list cannot drift from the check. Exempt a historical
mention by `(path, substring)` — the line must also contain a justifying
substring — so a rename record can still name the old word without opening the
whole repo to it.

Run the gate before the initial commit and **fix what it finds**: the first run
is what proves the ban list describes words people actually use, rather than
aspirations nobody typed.

**Evidence:** the test command and its passing result, or an explicit note that
enforcement is deferred and why.

---

## Step 4a — Write baseline Subject Matter Documentation

Populate `docs/subject/` with two core files:
- `docs/subject/domain-model.md`: Domain entities, data structures, external APIs, and business logic.
- `docs/subject/client-requirements.md`: Expected deliverables, quality thresholds, client SLAs, and acceptance criteria.

**The Hard Consulting Gate:** A factory without `docs/subject/` is barred from
receiving substantive consulting, diagnostic audits, and root-cause analysis.
Auditing a process without knowing what the process builds produces ungrounded
bureaucracy.

**Evidence:** the committed `docs/subject/` files with domain entities and client specs defined.

---

## Step 4b — Stand up the state surface

**The ledger is SIX gates, not one, and this step named two of them.** Measured
2026-09-25 on a clean fixture: a factory following the old text carried four unenforced
invariants — independently corroborated by the member census, whose ledger gate sets
read 2 / 2 / 1 / 0 of 6. The gate set grew one file at a time AFTER each factory copied,
so the missing gates are a function of *when* a factory bootstrapped rather than of care.

Copy all of it. The list is measured, not transcribed: a fixture built from exactly these
paths runs the six gates, and anything left out shows up as a failure naming itself.

| what | paths | why it travels with the ledger |
|---|---|---|
| the tool | `tools/ledger.py` | the only append path |
| its closure | `tools/field_predicate.py`, `tools/ledger_declaration.py`, `tools/reconstruction.py`, `tools/registry.py`, `tools/registry_render.py`, `tools/telemetry.py`, `tools/kit_identity.py` | a bare copy dies at import — the `#137` finding. `registry.py` and `telemetry.py` arrive through `ledger.py`, and `kit_identity.py` carries `--version` |
| the gates | `tests/test_ledger.py`, `tests/test_ledger_schema.py`, `tests/test_ledger_commit_cites_no_rows.py`, `tests/test_ledger_no_shrink.py`, `tests/test_ledger_close_preflight.py`, `tests/test_ledger_identity.py` | six invariants; naming two installs one third of the ledger |
| their closure | `tests/gate_fixtures.py`, `tests/hook_installation.py`, `tests/ledger_boundary.py` | imported by the gates. The second proves a hook is installed rather than assumed; the third is the SHARED boundary reader, so a gate and the repair path cannot disagree about what this factory declared |
| the hooks | `tools/hooks/commit-msg`, `tools/hooks/pre-commit` | `test_ledger_commit_cites_no_rows.py` reads `commit-msg`'s installation, so the gate cannot pass without it |
| a gate's own dependency | `tools/audit.py`, `tools/gate_budget.py` | `test_ledger.py` imports `audit.py`; `audit.py` imports `gate_budget.py` |

**Create three data surfaces, and copy two seeds:**

```sh
cp TEMPLATE/docs/ledger-invariants.example.json docs/ledger-invariants.json
cp TEMPLATE/registry/fleet.example.json         registry/fleet.json
printf 'hq\ntriage\nworker\ndelegate\nsurveys\nowner\n' > tools/actors.txt
```

- **`tools/actors.txt`** — declare every lane the closed core set does not carry. A lane
  that cannot be declared cannot record its rows.
- **`docs/ledger-invariants.json`** — the boundary each invariant landed at **here**. The
  example ships with `invariants: {}` and that is correct: add a key only once you have
  adopted that invariant, and the key is the name of the gate that asserts it.
- **`registry/fleet.json`** — the lane resolver reads it, and since identity is now derived
  from `OPENCRABS_SESSION_ID` the resolver is on the genesis path too.

**Re-anchor the commit-cites marker.** `tests/test_ledger_commit_cites_no_rows.py` pins a
`MARKER` commit — the first ledger commit obeying the no-row-number clause — and the
shipped sha belongs to the template's own history. Its docstring says a bootstrapped
factory re-anchors it at birth; set `MARKER` to your own first ledger commit once this
step's commit exists.

Then write the genesis row and verify:

```sh
python3 tools/ledger.py append --event genesis --actor hq \
  --subject evidence/ledger.jsonl --detail "state surface created"
python3 tools/ledger.py verify
```

**The genesis row is the one row whose actor may be declared.** Identity is derived from
`OPENCRABS_SESSION_ID` for every other append, and the derivation resolves a session
against the lane fragments — which step 4d enrolls, AFTER this step. So at this instant
there is no lane to resolve against, and the append is accepted with `--actor` when the
live ledger is **empty**. It is reachable exactly once per factory: the no-shrink gate
forbids a live ledger returning to empty, so the concession cannot be re-entered.

**Run all six, and expect two of them to be blocked today:**

```sh
for g in tests/test_ledger*.py; do python3 "$g"; done
```

- **`test_ledger.py`** currently raises `KeyError: 'close_row_revision'` on a fresh factory.
  Its own shipped example promises the gate *SKIPS with a stated reason* when a factory
  has declared no invariant, and the shared reader (`tests/ledger_boundary.py`) implements
  that skip — this gate indexes the declaration directly instead. Filed as a kit defect.
- **`test_ledger_no_shrink.py`**'s live-history probe needs a commit that actually deleted
  ledger rows, which no fresh factory has. Filed with it.
- The other four pass on a clean fixture: `test_ledger_schema.py`,
  `test_ledger_close_preflight.py`, `test_ledger_identity.py`, and `test_ledger.py` once
  the skip is honoured.

**Clear the exemption list when you copy it.** The shipped `tools/ledger.py` is a
byte-identical copy of the one this template was built from, so it also carries
that factory's pre-gate `EXEMPTIONS` — closes written before the gate that
enforces the sequence. A bootstrapped factory's ledger starts with a single
genesis row, so set `EXEMPTIONS = []` when you copy, and add an entry only for a
close that predates **your own** gate. An exemption inherited from another
factory's history excuses a defect your ledger does not have.

**Declare any lane the core set does not have.** The actor set in `tools/ledger.py`
is closed, and it is exactly the four role cards in §3 plus `owner`. A factory whose
law names a lane beyond them — a member-comms lane, a survey lane — writes it into
`tools/actors.txt`, one role per line, beside the tool. A lane that cannot be declared
cannot record its rows, so this is the difference between a lane and a name the ledger
refuses to hear from.

**Install the versioned hooks.** Two refusal points live in `tools/hooks/`, each
enforcing at commit time a law that a gate can otherwise only report after the fact:

- **`commit-msg` — the ledger clause.** A commit carrying the ledger names the
  concern, not a row number. `tests/test_ledger_commit_cites_no_rows.py` reports a
  violation after the fact, and this hook refuses it at the only point where the
  pending subject exists. A `pre-commit` hook cannot do *that* job: at pre-commit
  time the subject does not exist yet, so there is nothing to test.
- **`pre-commit` — the byte-pair clause.** A declared pair staged on ONE side only.
  `tests/test_template_sync.py` has always caught this, but only AFTER the commit
  landed, leaving a red on `main` until the next audit. This hook reads the INDEX
  (`git diff --cached`), never the working tree — a hook that read the working tree
  would PASS a commit that staged one side and fixed the other side on disk without
  staging it, which is a green light on the exact defect it exists to catch. It loads
  the pair table from `tests/test_template_sync.py` rather than keeping a copy, so a
  pair declared there is enforced here with no second edit.

Both are **versioned in the repo** rather than written into `.git/hooks`, which is
not tracked and so would never reach a bootstrapped factory:

```sh
git config core.hooksPath tools/hooks
```

`core.hooksPath` lives in `.git/config`, so run this once per clone — one setting
wires BOTH hooks, and a hook added to that directory later is wired by the same line.
Each hook's gate asserts it is present, executable and reachable through that
setting: an uninstalled hook is silent, which is the vacuous-pass shape this factory
forbids, so absence is a RED gate rather than an advisory.

**Why this is a step and not a habit.** State kept only in chat is a memory of a
conversation: it survives exactly as long as the context does. The ledger is the
durable record, and `tools/ledger.py` is its **only** append path — the lock is
what stops two lanes from both writing row 41. That is the defect that makes
every count taken from the file wrong from then on, while both writers still
look correct in isolation.

**Name the writer for every surface you add.** §13 of the law carries the table;
fill it in when you add a surface, not after. A surface with no named writer is
one that will acquire two.

**Evidence:** `python3 tools/ledger.py verify` exiting 0, and the six
`tests/test_ledger*.py` gates run — with the two blocked ones named above rather than
silently skipped. The schema gate is what makes the single-writer claim *tested* rather
than asserted; `test_ledger.py` is the one that bites a live lane's own row.

---

## Step 4c — Open the rework log

Create `evidence/rework.md` and copy the gate that judges it, then make the log
the **input to the improvement loop** rather than a diary.

**The gate needs EIGHT paths, and copying one of them is not enough.** The gate
imports two shared modules, one of those imports two more, and `tools/audit.py`
imports a third — so a factory that copies `tests/test_rework.py` alone gets
`ModuleNotFoundError: No module named 'audit'` — raised at import, *before* the
gate can report anything, so the error names no remedy. Six of the eight paths
ship with this template and two are created here. The **class** column is the
machine-readable answer to "is this file mine to change?": `shared` and `closure`
ship byte-identical from here, `factory` means the file is yours and a copy of
someone else's is wrong for it.

| Path | Class | Where it comes from |
|---|---|---|
| `tests/test_rework.py` | `shared` | **ships** — the gate itself |
| `tests/rework_table.py` | `closure` | **ships** — the shared entries-table parser, imported by the gate and by `tests/gate_registry.py`, so the table has ONE parser rather than two that drift |
| `tools/audit.py` | `shared` | **ships** — the coverage predicate and the subject vocabulary are imported from it, never re-typed, so one number cannot have two implementations |
| `tools/field_predicate.py` | `closure` | **ships** — imported by `tools/audit.py` |
| `tools/gate_budget.py` | `closure` | **ships** — imported by `tools/audit.py` |
| `tools/kit_identity.py` | `closure` | **ships** — imported by `tools/audit.py`; it is the one place a shipped tool's version and kit digest are computed, so ten executables do not each hand-roll the lookup |
| `evidence/rework.md` | `factory` | **created here** — the log itself |
| `evidence/ledger.jsonl` | `factory` | **created in Step 4b** — the denominator the resolution leg reads |

**This list is a snapshot, and it has already moved once.** It said seven paths
until 2026-09-25, when `tools/kit_identity.py` entered `tools/audit.py`'s imports
and the count became eight — a doc step naming a closure goes stale the moment
anything in it changes, and nothing in the tree tells the reader it is stale. So
do not take this table as the definition. The definition is
`registry/kit.json`'s `classes` map, and the closure is derivable from the import
graph. What this table buys you is the *reason* each path matters, which no
manifest carries.

The log answers the two Stability measures the rubric asks for — change fail
rate and rework rate — and neither can be computed from memory. The log is the
numerator; the ledger is the denominator.

**The entries table has SEVEN columns.** Six describe the defect; the seventh
names the work unit it belongs to, and it is the one the reader keys on:

| Column | What goes in it |
|---|---|
| **Date** | When the defect was **found** — not when it was introduced, which is usually unknown, and guessing turns the log into fiction |
| **Source** | What surfaced it: an owner instruction, a lane report, a gate, a review |
| **Defect** | What was wrong, stated so a reader can tell whether it is fixed |
| **Root cause** | The mechanism, not the symptom. "Careless" is not a root cause |
| **Resolution** | The commit or action that fixed it |
| **Prevented by** | The rule, test or gate that stops recurrence. `nothing yet` is a valid answer — and an important one |
| **Subject** | The work unit this entry belongs to — `#<n>` for a board issue, or the literal `none` when the defect was caught before any change landed. It is how a reader resolves an entry against the ledger, and the gate binds its vocabulary to `tools/audit.py` rather than re-typing it |

**A `## Rates` section is mandatory, and it is where the log becomes measurable.**
Every rate it states must carry **its date** and **its predicate** — the window it
was measured over and the formula it was computed with. A rate with neither is a
number nobody can check, and the gate rejects it.

**Recompute the coverage figure; never copy one.** The section states
`N of M entries carry a subject`, and the gate measures both from your own file on
every run. A figure copied from another factory's log is wrong for yours from the
moment you write it — which is exactly why this step ships no starter
`rework.md`: a log carrying someone else's measurement would be the
invented-value failure this kit forbids everywhere else.

**Placeholders are rejected.** `tbd`, `todo`, `n/a`, `-`, `?`, `unknown` and
`none` are refused in the six defect columns — and `none` in the `Subject` column
means something specific (*caught before any change landed*), not "I did not
fill this in". A bootstrap that has recorded no defect at all is either perfect,
which is not credible, or is not recording.

**This step must stand on its own.** The gate dies at import when a path above is
missing, so the list is here rather than in a later step: nothing else in this
document tells you that `tools/audit.py` and its two dependencies are part of the
rework kit.

**Why this is a step and not a habit.** A defect fixed and not recorded loses its
root cause within a day, and the factory pays for the same mistake again with the
same surprise. The `Prevented by` column is the load-bearing one: it is what
converts a failure into a rule, a test or a gate. A false "prevented by" removes
the defect from the improvement loop, so write `nothing yet` when nothing yet
prevents it.

**The log records the process, never a person.** An entry names a mechanism that
failed, not a lane that erred — otherwise the honest entries stop being written,
and an incomplete log is worse than none.

**Evidence:** `python3 tests/test_rework.py` exiting 0, and at least one entry
already in the log — a bootstrap that has never recorded a defect either had a
perfect bootstrap, which is not credible, or is not recording.

---

## Step 4d — Declare the factory, so a peer can find it

Copy [`tools/registry.py`](tools/registry.py),
[`tools/registry_render.py`](tools/registry_render.py),
[`tools/registry_attest.py`](tools/registry_attest.py),
[`tests/test_registry.py`](tests/test_registry.py) and
[`tests/test_registry_render.py`](tests/test_registry_render.py), then declare
this factory in `registry/fleet.json`:

```sh
cp registry/fleet.example.json registry/fleet.json
# edit: one record — this factory's slug, chat id, repo, skill path, job prefixes, aliases
python3 tools/registry.py enroll <slug>
python3 tools/registry.py render
python3 tools/registry.py validate
python3 tests/test_registry.py
```

**`validate` exits 1 until you have declared something, and that is the empty
state, not a failure.** The loader refuses an empty `factories` list by design —
*"an empty manifest reads as `no factory exists`, which is the declared-not-derived
defect it exists to fix"* — so before your manifest exists it reports `no fragments
found — nothing validated`. That is the correct answer to *what have you declared?*,
which is nothing. **Do not ship a placeholder `registry/fleet.json` to silence it:**
a manifest that is present, parseable and rejected is worse than an absent one,
because it reads as declared.

**`enroll` fills the observed half and nulls the declared half.** It derives your
lanes from the live bindings in your chat, then writes `purpose: null`,
`services: null`, `substrates_owned: null` — `null` is a statement (*nobody has
told us*), while an absent key is indistinguishable from a generator that forgot to
write it. Fill them in by hand: a fragment with a null zone describes a factory that
has not said what it owns.

**Re-enroll once a lane is bound** (Step 7). `enroll` is idempotent over the observed
half and keeps what you wrote in the declared half, so the fragment grows a lane
rather than starting again. A fragment enrolled before its first lane is honest, and
says nothing a peer can use.

**The pacemaker is what keeps it true.** Add one job on a **≥6 h** cadence running
`tools/registry_attest.py`; it wakes each factory's `HQ` with three questions —
*confirm or amend your fragment*, *confirm or expire your announcements*, and *confirm
your job prefix and report any cron row you cannot attribute to your own factory*. The
second is what stops the peer-facing field decaying into stale advice; all three ride one
job rather than three. Nothing on the box wakes a lane more often than every 6 h.

**Name your jobs after your factory, and touch nobody else's.** Every job you create is
named after the **prefix you declare** in `registry/fleet.json`'s `job_prefixes`, never
after your slug: `{{FACTORY_SLUG}}` is the name the registry knows you by, while the
prefix is what the cron table's readers judge — make the two coincide if you can, but
the prefix is the one that binds — the manifest validator refuses an empty
prefix list, and refuses two factories whose prefixes overlap (one nesting inside another
included), so attribution is a property of the manifest rather than of the order it happens
to list them in. The other half of that law cannot be gated, because the cron table is a
surface no single factory owns: **never disable, delete, edit or repace a job attributed to
another factory.** Before you touch a cron row, resolve its owner — `python3
tools/registry.py resolve`, or the Unattributed jobs section of `docs/factory-registry.md` —
and a job you cannot attribute is **reported, never edited**.

**Name the writer.** `HQ` writes `registry/fleet.json`; the lane that runs `enroll`
writes its own fragment; `render` writes the generated half. Add both rows to §13 of
the law — a surface with no named writer is one that will acquire two.

**Evidence:** `python3 tests/test_registry.py` exiting 0 against your own declared
fleet, and a committed `docs/factory-registry.md` that reproduces from
`python3 tools/registry.py render` with no diff.

---

## Step 5 — Wire the board

File the first issues on `{{REPO}}`, using title prefixes that encode kind
(`hq:` process, `probe:`/`site:`/`ops:` as the domain needs).

The first issue is **the smallest thing that proves the factory works** from
Step 0. It must be small enough to close in one lane, in one sitting.

**Evidence:** `gh issue list --repo {{REPO}}` showing the issues, with numbers.

---

## Step 6 — Add the cron trigger

One scheduled job per cadence the factory needs. It does **one thing**: notify
the owning session. It does not carry procedure, and it does not do the work.

Deliver through the scheduler's `deliver_to` pointing at the right topic — a
cron that delivers to the group root defeats the topic map.

**Evidence:** the cron list, showing each job's target topic.

---

## Step 7 — Dispatch the first lane

Spawn a session for the first issue, create its work-unit topic, and brief it.

**Known trap:** `session_notify` does **not** reach a freshly spawned session —
with no channel binding the daemon parks the message
(`No surface claims session … parking until its channel claims it`). Every
kickoff needs a second hop: deliver the brief with `send_input` into the
running session.

**Re-enroll the fragment now** (Step 4d). The lane is bound, so `python3
tools/registry.py enroll <slug>` grows the fragment a lane row instead of starting
again, and a peer can finally resolve it. Re-render in the same commit — the
generated half is a live read, so a binding that moved makes the committed render
stale until it is re-rendered.

**Evidence:** the brief received in the lane, and the lane's first reply.

---

## Step 8 — Close the loop

When the lane reports, rename its topic `Done — #N <title>` and leave it in
place. The forum is the archive.

Then check the factory against the
[success test](../docs/product.md#success-test) — in particular point 4: the
lane must still be able to state its own process **after a compaction**, from
its own files.

**Evidence:** the renamed topic, and the closing comment on the issue.

---

## Step 9 — Score the factory, and schedule the re-score

Record a **baseline score** against the
[quality criteria](../docs/quality-criteria.md) — 19 criteria in 6 families,
0–4 each — in the factory's repo, with the date.

Then make re-scoring a **scheduled job** (§7 of the law): daily to start. A
score with no cadence is a snapshot; a score on a cadence is a signal.

Add any **factory-specific measures** the domain needs — but only ones with a
decision hanging off them. A measure nobody acts on is maintenance with no
payoff.

**Scope.** Score the factory's *effectiveness and health*. Do **not** pull the
domain's own detail up into the score — that is the factory's `HQ`'s business.
What travels is the number and the template law it implies.

**Evidence:** the committed baseline score with its date, and the scheduled job
that re-scores it.

---

## Anti-patterns

| Don't | Why |
|---|---|
| Create the forum by converting an existing group | Every prior message is stranded in `General`; do it right the first time |
| Post a briefing to a topic and call it dispatched | Agents do not read topics. A topic post does zero work for the worker |
| Put procedure in a cron prompt | The prompt cannot be updated by a skill change — it freezes stale law in place |
| Create work-unit topics up front | They carry state in their names; a topic named before its work exists carries a guess |
| Skip the ontology "for now" | The vocabulary drift starts on day one, and it is never cheaper to fix later |
| Bootstrap without a first issue | You get a scaffold nobody uses — the most common failure |
