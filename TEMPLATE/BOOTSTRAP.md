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
| Which roles does it need? (`HQ` alone is a valid answer) | `ROLES` |
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
| `Triage` | Intake, routing, enforcement — omit only if `ROLES` is `HQ` alone |
| `{{DOMAIN}}` … | One per domain topic, in the order the factory will use them |

Do **not** create work-unit topics now. They are created at spawn time, named
`Worker — #N <title>`, and renamed to `Done — #N <title>` on close.

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
- how a lane is briefed (a session notification to the session UUID — never a
  chat post);
- how a work unit closes (rename the topic, evidence in the topic);
- what happens after a context compaction (reload the law **first**);
- which add-on rules are in force.

Version it. Mirror it to a repo so the law is diffable and survives the
session that wrote it.

**Evidence:** the skill file path, and the version string in it.

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

## Step 4b — Stand up the state surface

Copy [`tools/ledger.py`](tools/ledger.py) and
[`tests/test_ledger.py`](tests/test_ledger.py), create `evidence/ledger.jsonl`,
and write the genesis row:

```sh
python3 tools/ledger.py append --event genesis --actor hq \
  --subject evidence/ledger.jsonl --detail "state surface created"
python3 tools/ledger.py verify
python3 tests/test_ledger.py
```

**Clear the exemption list when you copy it.** The shipped `tools/ledger.py` is a
byte-identical copy of the one this template was built from, so it also carries
that factory's pre-gate `EXEMPTIONS` — closes written before the gate that
enforces the sequence. A bootstrapped factory's ledger starts with a single
genesis row, so set `EXEMPTIONS = []` when you copy, and add an entry only for a
close that predates **your own** gate. An exemption inherited from another
factory's history excuses a defect your ledger does not have.

**Why this is a step and not a habit.** State kept only in chat is a memory of a
conversation: it survives exactly as long as the context does. The ledger is the
durable record, and `tools/ledger.py` is its **only** append path — the lock is
what stops two lanes from both writing row 41. That is the defect that makes
every count taken from the file wrong from then on, while both writers still
look correct in isolation.

**Name the writer for every surface you add.** §13 of the law carries the table;
fill it in when you add a surface, not after. A surface with no named writer is
one that will acquire two.

**Evidence:** `python3 tools/ledger.py verify` exiting 0, and
`python3 tests/test_ledger.py` passing — the second is what makes the
single-writer claim *tested* rather than asserted.

---

## Step 4c — Open the rework log

Create `evidence/rework.md`, copy [`tests/test_rework.py`](tests/test_rework.py),
and make the log the **input to the improvement loop** rather than a diary.

The log answers the two Stability measures the rubric asks for — change fail
rate and rework rate — and neither can be computed from memory. The log is the
numerator; the ledger is the denominator.

| Column | What goes in it |
|---|---|
| **Date** | When the defect was **found** — not when it was introduced, which is usually unknown, and guessing turns the log into fiction |
| **Source** | What surfaced it: an owner instruction, a lane report, a gate, a review |
| **Defect** | What was wrong, stated so a reader can tell whether it is fixed |
| **Root cause** | The mechanism, not the symptom. "Careless" is not a root cause |
| **Resolution** | The commit or action that fixed it |
| **Prevented by** | The rule, test or gate that stops recurrence. `nothing yet` is a valid answer — and an important one |

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
[quality criteria](../docs/quality-criteria.md) — 13 criteria in 4 families,
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
