# Gaps and migration shape

Surveyed 2026-09-11. This file is the actionable half of the survey: what each
factory is missing against the pattern in
[best-practices.md](best-practices.md), and what converting the last two
factories actually involves.

---

## Summary

| Factory | On topic system | Factory chat | Process skill | Issue board as task list | Ledger |
|---|---|---|---|---|---|
| OpenCrabs development | ✅ | ✅ `Crabs Kanban Board` | ✅ opencrabs-dev | ✅ fork issues | ✅ workers-ledger |
| InferHub Watch | ✅ | ✅ `Inferhub watch` | ✅ `skills/inferhub` | ✅ repo issues | ✅ WORKLOG |
| Miidas | ❌ | ❌ **none** | ⚠️ repo `AGENTS.md` only | ⚠️ ADRs, no live board | ⚠️ `docs/clients.md` |
| AI AntiSpam | ❌ | ⚠️ plain group, cron sink | ⚠️ split 3 ways | ❌ none | ⚠️ send log only |

---

## Miidas — what is missing

**No factory chat at all.** Miidas work is dispatched from a private operator
DM and tracked in repo ADRs. There is no forum group where a lane can be
briefed, where evidence lands, and where the owner can watch the line run.

**No process skill.** `AGENTS.md` is a good *repo* instruction file — build,
verify, deploy, never-do — but it is not a factory process: it says nothing
about intake, dispatch, lane structure or where state lives.

**No live task board.** ADRs record decisions; they do not record what is in
flight. `docs/clients.md` tracks clients, not work.

**Client traffic is well-structured already** — per-client groups
(`МИИДАС: <client>`, the onboarding funnel `МИИДАС · Бухгалтерия без лишнего
человека`) and a client-facing forum (`Умница Миидаша`). That is the *product*
surface; it is not the *factory* surface, and the two must not be confused.

### Migration shape (proposal, not yet approved)

1. Create a forum group, e.g. `Miidas factory`. Topics: `HQ`, `Triage`, and one
   per workstream — at minimum `agent runtime`, `manager`, `landing`, `cdp`,
   plus `Worker — #N …` topics as work is dispatched.
2. Write `skills/miidas/SKILL.md`: mission, issue law (issues on
   `leshchenko1979/miidas` as the task list), delegation law, verification law
   (pointing at the existing per-component commands — do not duplicate them,
   reference them).
3. Add `ONTOLOGY.md` with the platform's canonical terms (slot, warm pool,
   convert, component, deploy) and a banned-synonyms table.
4. Pick one state writer. Today, client runtime state is `pool/slots/*.env` on
   apps and the client log is a markdown file — declare which one is
   authoritative and let the other be a snapshot.
5. One thin cron that notifies the HQ session.

**Constraint:** the per-client *product* groups stay untouched. The factory
chat is for the platform's own development, not for client conversations.

---

## AI AntiSpam — what is missing

**The group is a delivery sink, not a factory.** `ai-antispam`
(`-1003993000918`, 2 members) is a **plain group** — it cannot hold topics — and
six campaign crons deliver into it. Reports pile up in one timeline with no
lane structure and nothing to reply *in*.

**No issue board.** Campaign work is tracked in
`plans/marketing-plan-monoforum-outreach.md` and a recon queue file. That is a
plan document, not a task board: there is no per-item owner, state or close
condition.

**Process law is split three ways** — repo `CLAUDE.md`, `memory-bank/*.md`, and
the `outreach-reply-sweep` skill. Each is good in isolation; nothing states
which wins when they disagree.

**What already works and should be kept:** the single-writer rule on the
Postgres `outreach` schema (P11), the nightly DB→repo export, and the
skill-governed cron prompts (P7).

### Migration shape (proposal, not yet approved)

1. Convert `ai-antispam` to a **forum** (or create a sibling factory group if
   the owner prefers to keep the delivery sink quiet). Topics: `HQ`,
   `Outreach`, `Bot`, `Landing`, `Worker — #N …`.
2. Move campaign crons' `deliver_to` into the matching topic rather than the
   group's General.
3. Create the issue board — on `leshchenko1979/ai-antispam-outreach` for
   campaign items and `alexeyleshchenko/ai-antispam` for product items; state
   in the skill which repo owns which kind.
4. Write `skills/ai-antispam/SKILL.md` as the router that says which of the
   three existing law layers wins, and link out — do not copy their content.
5. Keep the DB as the single operational writer; the repo stays a snapshot.

---

## Smaller gaps in the two factories already on the system

| Item | Factory | Note |
|---|---|---|
| Duplicate forum group `5414677736` (`Inferhub watch`, 0 members) | InferHub Watch | Stale twin of the live group `4379632866`; retire it so reports cannot land in a dead chat |
| Legacy non-forum group `OC Dev` (`-1003627148483`) | OpenCrabs dev | Superseded by `Crabs Kanban Board`; still has a session binding |
| `skills/inferhub/SKILL.md` vs `ONTOLOGY.md` vs `WORKLOG.md` | InferHub Watch | Three files, no stated precedence — add a one-line precedence rule |
| Two GitHub identities in play (`leshchenko1979`, `alexeyleshchenko`) | AI AntiSpam | Canonical remote must be stated explicitly per repo in the skill; the local `github.com-alexey` SSH alias hides which account owns what |
| `leshchenko1979/miidas` described as "MOVED to alexeyleshchenko/miidas" | Miidas | The target repo did not resolve at survey time while the local clone still pushes to the `leshchenko1979` remote — **resolve before writing the skill** |
