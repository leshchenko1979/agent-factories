# Gaps and migration shape

Surveyed 2026-09-11; **updated the same day after the migration pass**. The
surface half of the migration is now done for all four factories. This file is
the actionable half of the survey: what each factory is still missing against
the pattern in [best-practices.md](../docs/best-practices.md).

---

## Summary

| Factory | On topic system | Factory chat | Process skill | Issue board as task list | Ledger |
|---|---|---|---|---|---|
| OpenCrabs development | ✅ | ✅ `Crabs Kanban Board` | ✅ opencrabs-dev | ✅ fork issues | ✅ workers-ledger |
| InferHub Watch | ✅ | ✅ `Inferhub watch` | ✅ `skills/inferhub` | ✅ repo issues | ✅ WORKLOG |
| Miidas | ✅ | ✅ `Miidas Factory` | ✅ `skills/miidas` | ⚠️ enabled, 0 issues | ⚠️ `docs/clients.md` |
| AI AntiSpam | ✅ | ✅ `ai-antispam` (forum) | ✅ `skills/ai-antispam` (router) | ⚠️ enabled, 0 issues | ⚠️ send log only |

Every factory now has a forum group with topics — the ❌ that stood in the
"On topic system" column is gone for all four. Topic ids: [topics.md](topics.md).

---

## Migration log — executed 2026-09-11

| # | Step | Result |
|---|---|---|
| 1 | Create the Miidas factory forum | `Miidas Factory` `-1003996392908`, forum, 6 topics + `General` |
| 2 | Promote the bot in that group | `redevest_admin_tools_bot` was a plain member; promoted to admin with `manage_topics` (rank `factory bot`) |
| 3 | Convert the AI AntiSpam group to a forum | `channels.ToggleForum` on `-1003993000918`; the 10,779 pre-existing messages stay in `General` |
| 4 | Create the AI AntiSpam topics | `Outreach` 10780, `Triage` 10781, `HQ` 10782, `Landing` 10783, `Bot` 10784 |
| 5 | Re-point the crons | all **11** crons delivering to `-1003993000918` moved off the group root: ten → `Outreach` (10780), `max-api-retest` → `Bot` (10784). Zero remain unthreaded |
| 6 | Write the two process skills | `skills/miidas/SKILL.md`, `skills/ai-antispam/SKILL.md` (router) |
| 7 | Convert this project's own chat | `Factories` `-1004497192134` → forum, topics `HQ` 21, `Triage` 20, `Surveys` 19 |
| 8 | Correct the stale repo metadata | `leshchenko1979/miidas` and `leshchenko1979/miidas-template` carried "MOVED to alexeyleshchenko/…" descriptions from a reverted migration; both rewritten |

Every topic id in steps 1, 4 and 7 was read back from live state with
`messages.GetForumTopics`, and step 5 was verified by reading the cron table
after the writes — not from the UI, and not from memory.

**Correction carried from the survey:** the first pass said six crons deliver to
`ai-antispam`. The live count was **eleven** (9 enabled, 2 disabled —
`max-api-retest`, `wave0-sprint-batches`). The re-point used the verified
eleven.

---

## Miidas — what remains

The surface exists and the process law is written. What is still missing is
**practice**, not structure:

- **`ONTOLOGY.md` is not written.** Canonical platform terms (slot, warm pool,
  claim, convert, component, deploy, decommission) plus a banned-synonyms table.
  Without it, "slot" and "container", or "warm pool" and "trial", drift apart
  between the manager code, the ADRs and the reports.
- **The issue board is enabled but unused** — `leshchenko1979/miidas` has issues
  on and **zero open**. The skill declares the board to be the task list; no
  task has been filed on it yet. ADRs still carry the decisions and
  `docs/clients.md` carries the clients, so nothing is lost — but the
  board-is-the-task-list convention is currently a claim, not a practice.
- **No declared state writer.** Client runtime state is `pool/slots/*.env` on
  apps; the client record is a markdown file. The skill names the file-based
  registry as the runtime writer, but the *authoritative* record for "who is a
  client" is still ambiguous.
- **No cron.** The first one should be a thin trigger (one `session_notify`),
  not a job that does project work in its prompt.
- **No lane has ever been dispatched from this factory.** The topic map is a
  scaffold. It has not yet carried a brief.

**Constraint, unchanged:** the per-client *product* groups (`МИИДАС: <client>`,
the onboarding funnel, the client-facing forum `Умница Миидаша`) stay
untouched. The factory chat is for the platform's own development.

---

## AI AntiSpam — what remains

- **The routing gap is closed.** All eleven crons now target a topic. This was
  the single most concrete defect in the survey: after the forum conversion the
  reports would still have piled into `General`, because a forum conversion does
  not move existing cron deliveries.
- **The three-way law split is now resolved on paper.** `skills/ai-antispam/`
  is a router that states which layer wins per surface and links out, rather
  than copying content. That precedence is a *convention written today* — it has
  not yet been tested by a disagreement.
- **The issue board is enabled but unused** — zero open on both
  `leshchenko1979/ai-antispam-outreach` (campaign) and
  `alexeyleshchenko/ai-antispam` (service). Campaign work still lives in
  `plans/marketing-plan-monoforum-outreach.md` and a recon queue file: a plan
  document, not a per-item board with owner, state and close condition.
- **Two GitHub identities in play.** The local clone uses the `github.com-alexey`
  SSH alias for `alexeyleshchenko/ai-antispam` (public) while the campaign repo
  is `leshchenko1979/ai-antispam-outreach` (private). The router states which
  repo owns which kind of work; the SSH alias still hides which account owns
  what.
- **What already works and should be kept:** the single-writer rule on the
  Postgres `outreach` schema (P11), the nightly DB→repo export, and the
  skill-governed cron prompts (P7).

---

## Smaller gaps in the factories already on the system

| Item | Factory | Note |
|---|---|---|
| Migrated shell `-5414677736` (`Inferhub watch`, 0 members) | InferHub Watch | **Retired 2026-09-12** — not a twin; a migrated shell. See [Decommission records](#decommission-records) |
| Legacy non-forum group `OC Dev` (`-1003627148483`) | OpenCrabs dev | **Retired as a delivery surface 2026-09-12** — superseded, but not dead. See [Decommission records](#decommission-records) |
| `skills/inferhub/SKILL.md` vs `ONTOLOGY.md` vs `WORKLOG.md` | InferHub Watch | Three files, no stated precedence — add a one-line precedence rule |
| Two GitHub identities in play (`leshchenko1979`, `alexeyleshchenko`) | AI AntiSpam | Canonical remote must be stated explicitly per repo in the skill; the local `github.com-alexey` SSH alias hides which account owns what |
| ~~`leshchenko1979/miidas` described as "MOVED to alexeyleshchenko/miidas"~~ | Miidas | **Resolved 2026-09-11.** The owner confirmed miidas was moved back; neither `alexeyleshchenko/miidas` nor `alexeyleshchenko/miidas-template` exists, and both stale descriptions were rewritten. Lesson: verify the live remote with `gh`, never a repo description |

---

## Decommission records

Two places were retired on 2026-09-12. Both records below carry the live facts
they were decided on, so the next survey does not re-litigate them.

### `-5414677736` — `Inferhub watch` — **retired, migrated shell**

The earlier survey called this a *"stale twin"* of the live group. It is not a
twin. It is a **migrated shell** — the old identity of a chat that was upgraded
to a supergroup — and the record also carried the id without its leading minus.

| Field | Value |
|---|---|
| Id | `-5414677736` (the record had `5414677736` — wrong) |
| Title | `Inferhub watch` |
| Shape | group, **not** a forum, **0 members** |
| Created | 2026-09-10T04:38:12Z (`[Service: ChatCreate]`) |
| Last message | 2026-09-10T04:39:31Z — `[Service: ChatMigrateTo]` |
| Lifetime | **79 seconds** — created, renamed, migrated |
| Deliveries targeting it | **0** (all 19 scheduled jobs scanned) |
| Bindings | 1 row — root → `7a96d7a1-c4ce-4faf-9b37-5cba88cae124`, 2026-09-10 04:38:07Z |

**Why it is a shell and not a twin.** A group was created, briefly used (a
working-directory change), renamed, and migrated — all inside 79 seconds. A
`ChatMigrateTo` event as the final message is the signature of an in-place
upgrade; the id survives as a tombstone while the content moves.

**The content did not land in the live group, and that is worth stating.** The
live `Inferhub watch` group is `-1004379632866`, a forum with 16 topics and 2
members. Fetching the shell's message ids from it returns *not found*, and a
text search for its one real message returns nothing. So the shell is **not**
the migration source of the live group either — it is an abandoned pre-upgrade
attempt, and nothing of it needs preserving.

**Resolution:** nothing routes to it; nothing may. **Retired.**

### `-1003627148483` — `OC Dev` — **retired as a delivery surface, still an archive**

The earlier survey called this one *"legacy"* and left the decision open. The
live read says **superseded, not dead** — and that distinction is the whole
record.

| Field | Value |
|---|---|
| Id | `-1003627148483` |
| Title | `OC Dev` |
| Shape | group, **not** a forum, **5 members** |
| Last message | 2026-09-07T13:57:38Z — **5 days before this record** |
| Content | a real conversation with the upstream maintainer (Adolfo Usier, `adolfodev`) about the no-DM-pings rule, with the bot replying |
| Deliveries targeting it | **0** (all 19 scheduled jobs scanned) |
| Bindings | **2 rows** — root → `55943b3e-ad07-4b21-aa81-2243a8a48092` (2026-08-31), thread 1 → `16720f42-c03f-4381-8aa0-6b5a7fdd0fa0` (2026-09-07 13:57:09Z) |
| Superseded by | `Crabs Kanban Board` (`-1003936827469`), now titled `Opencrabs Dev Factory` |

**Why the distinction matters.** A place whose last message is a week old is
not the same as a place whose last message is a service event. Someone was
still talking here five days ago, and the second binding was refreshed within
the same minute as that last message. Calling it dead would have been wrong on
the live evidence — and the binding refresh is itself the signal that the
runtime still considered it live.

**Resolution:** retired **as a delivery surface** — no delivery may target it,
and none does. The group itself **stays**: it holds a decision record, and
retirement means nothing routes to it, never that history is deleted.

### The one thing left open, and whose it is

Both places still carry **binding rows** — one for the shell, two for `OC Dev`.
A binding is what routes a *future* inbound message to a session, so leaving
them is not neutral: the rows are the mechanism by which a retired place could
come back to life.

Retiring them is a write to the **harness's** state, not this repo's, so it is
not done here. It is handed to the harness owner (OpenCrabs Kanban Board HQ)
with the ids above.

---

## What the two migrations taught

Three things that generalise, and belong in the pattern:

1. **A forum conversion does not move anything.** `channels.ToggleForum` gives
   the chat topics and parks every existing message in `General`; every
   delivery path — crons, webhooks, bound sessions — keeps pointing at the chat
   root. Converting a group that is already a delivery sink therefore creates a
   *new* problem (everything still in one stream, now with a misleading topic
   list beside it) unless the deliveries are re-pointed in the same pass.
2. **Surface first, process second, practice third.** Creating topics is
   minutes. Writing the skill is an hour. Getting the board, the ontology and
   the first dispatched lane into use is what actually makes it a factory — and
   that is the part that can silently never happen.
3. **Repo metadata rots.** The single wrong fact in the first survey — miidas's
   repo location — came from reading a repo *description* instead of resolving
   the remote. Any fact that decides routing should be read from the live
   system.
