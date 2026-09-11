# Factory topic map

Every id below was read back from live Telegram state on 2026-09-11 with
`messages.GetForumTopics` (MTProto, owner account) — not from memory or from
the UI. Topic ids are the ids of the topic's create-service message.

## The spine

All four factories converge on the same shape. What differs is only the
domain topics in the middle:

```
HQ          the HQ lane — process work, rulings, gates
Triage      intake, routing, enforcement
<domain>    one topic per workstream the factory actually has
Worker — #N <title>   one topic per dispatched work unit
Done — #N <title>     same topic, renamed when the unit closes
```

`HQ` and `Triage` are the load-bearing pair. InferHub Watch runs on `HQ`
alone; OpenCrabs dev splits HQ from triage. A factory with neither
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

### Cron routing — applied 2026-09-11

**11** crons delivered to `telegram:-1003993000918` — 9 enabled, 2 disabled
(`max-api-retest`, `wave0-sprint-batches`). The first survey said six; it was
wrong, and the count was re-verified against the live cron table before the
re-point. None of the eleven set a `message_thread_id`, so after the forum
conversion they would all still have landed in `General` — the same
undifferentiated timeline the conversion was meant to fix.

All eleven were re-pointed in the same pass. Verified by reading the cron table
back afterwards: **zero** rows remain on the unthreaded target.

| Cron | Topic | thread_id |
|---|---|---|
| `wave0-reply-sweep` | `Outreach` | 10780 |
| `wave0-unactivated-reprobe` | `Outreach` | 10780 |
| `wave0-sprint-batches` | `Outreach` | 10780 |
| `outreach-mining-tranche` | `Outreach` | 10780 |
| `outreach-auto-kick` | `Outreach` | 10780 |
| `outreach-watch-poll` | `Outreach` | 10780 |
| `watch-funnel-day7-report` | `Outreach` | 10780 |
| `kick-watcher-lazy4` | `Outreach` | 10780 |
| `resume-lazy4-watcher` | `Outreach` | 10780 |
| `outreach-db-sync` | `Outreach` | 10780 |
| `max-api-retest` | `Bot` | 10784 |

`outreach-db-sync` went to `Outreach`, not `Triage` as first proposed: it is an
outreach-state sync, and `Triage` in this pattern means *incoming signal
needing a decision*, not an automated heartbeat. `Triage`, `HQ` and `Landing`
therefore hold no cron delivery — they are for the human and for lanes.

Delivery syntax is `telegram:<chat_id>:<thread_id>` — the InferHub factory
already uses `telegram:-1004379632866:2` for its HQ topic, so the form is
proven in this codebase.

## 5. Agent Factories — `Factories` (converted to a forum 2026-09-11)

`-1004497192134`. This project's own chat. Was a plain megagroup; flipped with
`channels.ToggleForum` in the same pass.

| Topic | id |
|---|---|
| `HQ` | 21 |
| `Triage` | 20 |
| `Surveys` | 19 |
| `General` | 1 |

The three topics were created concurrently, so their ids are in reverse creation
order — the ids are the topic's create-service message id, which is why they
sit just above the group's existing message ids rather than in a tidy run. This
is normal and is exactly why **ids are read back, never derived**: a topic id
cannot be predicted from the topic's position in the list.

## Creating and renaming topics

Topic management goes through the **userbot** (`tg_mtproto`), never the Bot API —
a bot cannot manage topics it did not create, and the Bot API has no
`listForumTopics` endpoint at all, so the bot can only learn topic names from
messages it happens to see.

```
# create   (namespace is messages.*, NOT channels.* — channels has no CreateForumTopic)
messages.CreateForumTopic
  {"peer": <chat_id>, "title": "<title>", "random_id": <unique int64>, "icon_color": <int>}

# list
messages.GetForumTopics
  {"peer": <chat_id>, "offset_date": 0, "offset_id": 0, "offset_topic": 0, "limit": 100}

# rename on close
channels.EditForumTopic
  {"channel": <chat_id>, "topic_id": <id>, "title": "Done — #N <title>"}

# convert a megagroup into a forum
channels.ToggleForum
  {"channel": <chat_id>, "enabled": true, "tabs": false}
```

`ToggleForum` lives in `channels.*`; `CreateForumTopic` / `GetForumTopics` /
`EditForumTopic` live in `messages.*`. The `peer` argument is named `peer`, not
`channel`. `random_id` must be unique per topic, and the ids already consumed by
this pass are `900000000001`–`900000000006` (Miidas), `900000000011`–
`900000000015` (AI AntiSpam) and `900000000021`–`900000000023` (Factories).
