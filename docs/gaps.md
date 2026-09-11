# Gaps and migration shape

Surveyed 2026-09-11; **updated the same day after the migration pass**. The
surface half of the migration is now done for all four factories. This file is
the actionable half of the survey: what each factory is still missing against
the pattern in [best-practices.md](best-practices.md).

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
| Duplicate forum group `5414677736` (`Inferhub watch`, 0 members) | InferHub Watch | Stale twin of the live group `4379632866`; retire it so reports cannot land in a dead chat |
| Legacy non-forum group `OC Dev` (`-1003627148483`) | OpenCrabs dev | Superseded by `Crabs Kanban Board`; still has a session binding |
| `skills/inferhub/SKILL.md` vs `ONTOLOGY.md` vs `WORKLOG.md` | InferHub Watch | Three files, no stated precedence — add a one-line precedence rule |
| Two GitHub identities in play (`leshchenko1979`, `alexeyleshchenko`) | AI AntiSpam | Canonical remote must be stated explicitly per repo in the skill; the local `github.com-alexey` SSH alias hides which account owns what |
| ~~`leshchenko1979/miidas` described as "MOVED to alexeyleshchenko/miidas"~~ | Miidas | **Resolved 2026-09-11.** The owner confirmed miidas was moved back; neither `alexeyleshchenko/miidas` nor `alexeyleshchenko/miidas-template` exists, and both stale descriptions were rewritten. Lesson: verify the live remote with `gh`, never a repo description |

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
