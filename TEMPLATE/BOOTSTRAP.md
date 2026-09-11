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

**Rule:** if you cannot name the smallest thing that proves the factory works,
you are not ready to bootstrap. A factory with no first issue has an
unfalsifiable process — the failure mode is a beautiful scaffold nobody uses.

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
| `HQ` | The supervisor lane: process work, rulings, gates |
| `Triage` | Intake, routing, enforcement — omit only if `ROLES` is `HQ` alone |
| `{{DOMAIN}}` … | One per domain topic, in the order the factory will use them |

Do **not** create work-unit topics now. They are created at spawn time, named
`Worker — #N <title>`, and renamed to `Done — #N <title>` on close.

Promote the factory bot to admin with `manage_topics`. Without it the bot
cannot create or rename the work-unit topics, and the whole naming law is
inoperable.

**Evidence:** every topic id read back from live state (`GetForumTopics` or
equivalent) — never from the UI, never from the creation response alone.

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

**Evidence:** the test command and its passing result, or an explicit note that
enforcement is deferred and why.

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

## Anti-patterns

| Don't | Why |
|---|---|
| Create the forum by converting an existing group | Every prior message is stranded in `General`; do it right the first time |
| Post a briefing to a topic and call it dispatched | Agents do not read topics. A topic post does zero work for the worker |
| Put procedure in a cron prompt | The prompt cannot be updated by a skill change — it freezes stale law in place |
| Create work-unit topics up front | They carry state in their names; a topic named before its work exists carries a guess |
| Skip the ontology "for now" | The vocabulary drift starts on day one, and it is never cheaper to fix later |
| Bootstrap without a first issue | You get a scaffold nobody uses — the most common failure |
