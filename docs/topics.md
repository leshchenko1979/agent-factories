# Factory topic map

Every id below was read back from live Telegram state on 2026-09-11 with
`messages.GetForumTopics` (MTProto, owner account) — not from memory or from
the UI. Topic ids are the ids of the topic's create-service message.

## The spine

All four factories converge on the same shape. What differs is only the
domain topics in the middle:

```
HQ          the supervisor lane — process work, rulings, gates
Triage      intake, routing, enforcement
<domain>    one topic per workstream the factory actually has
Worker — #N <title>   one topic per dispatched work unit
Done — #N <title>     same topic, renamed when the unit closes
```

`HQ` and `Triage` are the load-bearing pair. InferHub Watch runs on `HQ`
alone; OpenCrabs dev splits supervisor from triage. A factory with neither
has no place for a lane to be briefed.

**Naming law.** Work-unit topics carry the issue number in the title, so the
GitHub board and the chat can be joined by eye. Rename on close, never
re-create — the topic id is stable and is what a cron's `deliver_to` points at.

## 1. OpenCrabs development — `Crabs Kanban Board`

`-1003936827469`. ~20 topics; the load-bearing ones reported in the survey
were `OC DEV HQ` (30220), `Triage` (42487), `Skills` (49643), `Harvest`
(39218), `Ontology` (43993), `Role split` (42360). **Not re-verified** — this
forum's topic list was not re-enumerated in the 2026-09-11 pass.

## 2. InferHub Watch — `Inferhub watch`

`-1004379632866`. Verified 2026-09-11.

| Topic | id |
|---|---|
| `HQ` | 2 |
| `General` | 1 |
| `Worker — HQ cycles` | 32 |
| `Worker — #2 hourly cadence law` | 45 |
| `Worker — #11 Cleanliness & Sync` | 257 |
| `Worker — #12 Auto Route Switcher` | 288 |
| `Done — #13 keys.toml Fallback` | 343 |
| `Done — #14 session_notify alerts` | 357 |
| `Worker — #15 IQ/$ basis alignment` | 399 |
| `Worker — #16 gate rank fidelity` | 421 |

This is the cleanest instance of the pattern: exactly one standing topic
(`HQ`), everything else is a work unit that closes by rename. Note `HQ` has a
custom topic emoji and that `Done —` topics are **left in place**, so the
forum doubles as the archive.

## 3. Miidas — `Miidas Factory` (created 2026-09-11)

`-1003996392908`. Created for this project; the factory previously had no
chat at all.

| Topic | id |
|---|---|
| `HQ` | 4 |
| `Triage` | 5 |
| `Agent runtime` | 6 |
| `Landing` | 7 |
| `CDP` | 8 |
| `Manager` | 9 |
| `General` | 1 |

Domain topics mirror the repo's components (`agent/`, `manager/`, `landing/`,
`cdp/`), which is what the deploy scripts and the per-component AGENTS.md
files already treat as the unit of work. **Constraint carried over from
`gaps.md`: the per-client product groups (`МИИДАС: <client>`, `Умница
Миидаша`) are not touched.** The factory surface is for platform development.

`redevest_admin_tools_bot` was promoted to admin with `manage_topics` in this
group on the same pass — it had joined as a plain member and could not have
created topics.

## 4. AI AntiSpam — `ai-antispam` (converted to a forum 2026-09-11)

`-1003993000918`. Was a plain megagroup; `channels.ToggleForum` flipped it.
The group's 10,779 existing messages stay in `General`.

| Topic | id |
|---|---|
| `Outreach` | 10780 |
| `Triage` | 10781 |
| `HQ` | 10782 |
| `Landing` | 10783 |
| `Bot` | 10784 |
| `General` | 1 |

The bot was already an admin here **with `manage_topics`**, so no promotion
was needed.

### Outstanding: cron delivery still lands in `General`

**11** crons deliver to `telegram:-1003993000918` — 9 enabled, 2 disabled
(`max-api-retest`, `wave0-sprint-batches`). The first survey said six; it was
wrong, and this count was re-verified against the live `cron_manage list`
output on 2026-09-11. None of the eleven sets a `message_thread_id`, so after
the forum conversion they all still land in `General` — the same
undifferentiated timeline the conversion was meant to fix.

| Cron | Proposed topic |
|---|---|
| `wave0-reply-sweep` | `Outreach` |
| `wave0-unactivated-reprobe` | `Outreach` |
| `wave0-sprint-batches` | `Outreach` |
| `outreach-mining-tranche` | `Outreach` |
| `outreach-auto-kick` | `Outreach` |
| `outreach-watch-poll` | `Outreach` |
| `watch-funnel-day7-report` | `Outreach` |
| `kick-watcher-lazy4` | `Outreach` |
| `resume-lazy4-watcher` | `Outreach` |
| `outreach-db-sync` | `Triage` |
| `max-api-retest` | `Bot` |

Delivery syntax is `telegram:<chat_id>:<thread_id>` — the InferHub factory
already uses `telegram:-1004379632866:2` for its HQ topic, so the form is
proven in this codebase.

**Not applied.** Re-pointing eleven production crons is a behaviour change to
live monitoring and is left for the owner to approve.
