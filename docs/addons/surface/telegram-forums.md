# Add-on: `surface/telegram-forums`

**Class:** binding — surface · **Status:** proven (all four factories)
**Binds:** Telegram, a group with **topics** enabled (a "forum")

A **surface binding** is the chat the factory runs on. It adds no domain topics,
no roles and no gates of its own. What it adds is the *mechanics* by which the
core's surface requirements are met on one particular product.

---

## Take it when

The factory's chat is a Telegram forum group, and the human supervises the work
by reading it.

If the factory's chat is somewhere else — a Slack workspace, a Discord server,
a web dashboard, an email thread — this binding does not apply. Write the
binding for that surface instead; the
[binding rule](../../addons.md#the-binding-rule) is what makes that swap cheap.

---

## What it binds

| Core requirement | How Telegram satisfies it |
|---|---|
| The human can see every work unit | One topic per work unit, in one forum group |
| A work unit's state is readable at a glance | The topic **name** carries the state: `Worker — #N` → `Done — #N` |
| A work unit has a stable address | The **topic id** — stable across renames, and what deliveries target |
| A message can be routed to one work unit | `deliver_to` targets `telegram:<chat_id>:<thread_id>` |
| The surface is an archive | Closed topics stay in place; nothing is deleted |
| The surface reaches no agent | Nothing posted to a topic is read by a session |

---

## The spine

```
HQ                  the supervisor lane — process work, rulings, gates
Triage              intake, routing, enforcement
<domain>            one topic per workstream the factory actually has
Worker — #N <title> one topic per dispatched work unit
Done — #N <title>   the same topic, renamed on close
```

`HQ` and `Triage` are the load-bearing pair. A minimal factory runs on `HQ`
alone; a factory with neither has nowhere to observe a lane.

Work-unit topics are **not** created up front. A topic named before its work
exists carries a guess, and the naming law is the point.

---

## Topic roles

| Topic | Who writes | What belongs | What does not |
|---|---|---|---|
| `HQ` | Supervisor | Dispatch decisions, rulings, gates, cross-lane conflicts | Routine receipts, status pings, "lane idle" notes |
| `Triage` | Triage | Intake, routing, enforcement, claim conflicts | Implementation detail |
| `<domain>` | The lane owning that workstream | Work in that stream, its evidence and its blocks | Unrelated conversations |
| `Worker — #N` | The lane | Its brief, receipts, and result report | Everything else |
| `Done — #N` | Nobody | The closed record, left in place | New work — reopen as a new issue and topic |

---

## Naming law

| Event | Action |
|---|---|
| Lane spawned for issue `#N` | Create `Worker — #N <title>` |
| Lane reports complete | Rename to `Done — #N <title>` |
| Issue number in title | Always. It is the join key to the board |

**Rename the topic; never re-create it.** A re-created topic gets a new id and
silently orphans every delivery aimed at the old one.

---

## Topic ids

A topic id is the id of the topic's **create-service message**. Two
consequences:

- It **cannot be derived** from the topic's position in a list, its name, or
  the order you asked for. Read it back from live state (`GetForumTopics` or
  equivalent) — never predict it, never take the creation response as proof.
- It is **stable across renames**, which is why the naming law can flip a
  topic's state without breaking anything pointed at it.

Create topics **serially** if you want ordered ids. Read them back either way.

---

## Creating and renaming a topic

Telegram exposes topic creation on **MTProto**, not through the bot API surface
most harnesses wrap — so on a harness with no topic tool you reach for the raw
invoke. Two facts cost real time to rediscover, and both fail in a way that
reads like something else:

- **The methods live under `messages.*`, not `channels.*`.** `channels` carries
  `ToggleForum` and nothing else for topics. Calling `channels.createForumTopic`
  fails as a *missing module attribute* — which reads like a Telethon version
  problem, and is not.
- **The peer parameter is named `peer`, not `channel`.** The request resolves
  the peer correctly and *then* rejects the keyword. The error names the
  parameter it wanted; read it instead of guessing a second time.

| Action | Method | Params that matter |
|---|---|---|
| Create | `messages.createForumTopic` | `peer`, `title`, `random_id`, `icon_color` |
| Rename | `messages.editForumTopic` | `peer`, `topic_id`, `title` |
| List | `messages.getForumTopics` | `peer`, `offset_date`, `offset_id`, `offset_topic`, `limit` |
| Read one back | `messages.getForumTopicsByID` | `peer`, `topics` — a **list** |

`random_id` is an idempotency nonce: any random 63-bit integer. It is **not**
the topic id. The topic id is the id of the create-service message, and the
creation response's `UpdateMessageID` is a *claim*, not proof — read the topic
back with `getForumTopicsByID` and take the id from there.

**Rename, never re-create.** A re-created topic gets a new id and silently
orphans every delivery aimed at the old one.

### A topic's session arrives on its first inbound message

A session claims a topic when a message **arrives** in it — the binding is
written on inbound resolution, and an outbound post never creates one. So a
freshly created topic is addressable (deliveries target its `thread_id`) but
unowned: nobody is listening in it yet.

Two consequences worth knowing before you plan a lane:

- A lane that must be *conversible* — the human writes to it and the same
  session answers — needs the topic's first inbound message to come from the
  human. Until then, route work to the lane by the harness's direct-address
  primitive, and treat the topic as the reporting surface only.
- A topic post is therefore **owner visibility**, never dispatch. This is the
  surface half of the "topics are for the human" rule above, and it is why a
  briefing posted into a topic performs no work.

---

## Delivery

Crons and watchers deliver to a **topic**, never to the group root. A job
delivering to the root defeats the whole map: the message lands in `General`
where nobody's filter looks.

Target form: `telegram:<chat_id>:<thread_id>`.

---

## Rights

The factory bot must be an administrator with **`manage_topics`**. Without it
the bot cannot create or rename work-unit topics, and the entire naming law is
inoperable.

---

## Topics are for the human

This is the surface half of a core rule, and it is the single most expensive
confusion in a factory, because the failure is silent.

**Agents do not read topics.** A briefing posted to a topic performs zero work
for the worker — it only *looks* like dispatch. The topic shows a briefing, the
lane shows nothing, and the operator believes work is in progress.

Instructions reach a lane through the *harness's* direct-address primitive, not
through the surface. See [`harness/opencrabs`](../harness/opencrabs.md).

---

## The one-way door

> **A forum from the start. Converting a group afterwards strands every existing
> message in `General`.**

`ToggleForum` gives the chat topics and parks all prior history in `General`.
Worse: every delivery path — crons, webhooks, bound sessions — keeps pointing
at the **chat root**, so a group that was already a delivery sink becomes a
forum whose topics are decorative. The reports still pile into one
undifferentiated stream, now with a topic list beside it that suggests
otherwise.

Re-point the deliveries in the same pass, and verify by **reading the delivery
table back** — not by looking at the surface.

*Proven:* ai-antispam, 2026-09-11 — eleven crons all still targeted the bare
chat id after the conversion; all eleven were re-pointed and the table re-read
to confirm zero rows remained on the unthreaded target.

---

## Costs

- **One topic per work unit** means the forum grows without bound. That is
  deliberate — the forum is the archive — but it is a surface that gets noisy at
  high volume, and `Done —` topics are never pruned.
- **The naming law needs admin rights**, so the bot's permissions are a
  hard dependency of the process, not an operational detail.
- **Topic ids are opaque.** Every cron, watcher and bound session holds a
  `thread_id` that only live state can confirm.

---

## What changes if the surface is swapped

Take this binding out and the following core rules lose their mechanics — each
needs a replacement, not a deletion:

| Core rule | Needs, on the new surface |
|---|---|
| One named place per work unit | A channel/thread concept with a stable id |
| State in the name | A renameable label — or a different state carrier, if the surface has no names |
| Closed units stay as archive | Non-destructive retention |
| Delivery targets a work unit | An addressable per-unit route |
| Agents do not read the surface | The same, plus the harness's direct-address path |
| Topic id read back, never predicted | An id that is likewise not derivable from position |

If the new surface has no renameable names, the naming law is not "adapted" —
it is replaced. The requirement it served (state readable at a glance) still
has to be met some other way.
