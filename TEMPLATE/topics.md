# The chat surface

The factory's chat is a **forum group**, and its topics carry state in their
names. This file is the spec: which topics exist, what belongs in each, and how
they change.

> A forum from the start. Converting a group into a forum afterwards strands
> every existing message in `General` — the conversion is a one-way door for
> history.

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
alone; a factory with neither has nowhere to brief a lane.

---

## Topic roles

| Topic | Who writes | What belongs | What does not |
|---|---|---|---|
| `HQ` | Supervisor | Dispatch decisions, rulings, gates, cross-lane conflicts | Routine receipts, status pings, "lane idle" notes |
| `Triage` | Triage | Intake, routing, enforcement, claim conflicts | Implementation detail |
| `{{DOMAIN}}` | The lane owning that workstream | Work in that stream, its evidence and its blocks | Unrelated conversations |
| `Worker — #N` | The lane | Its brief, receipts, and result report | Everything else |
| `Done — #N` | Nobody | The closed record, left in place | New work — reopen as a new issue and topic |

---

## Naming law

| Event | Action |
|---|---|
| Lane spawned for issue `#N` | Create `Worker — #N <title>` |
| Lane reports complete | Rename to `Done — #N <title>` |
| Issue number in title | Always. It is the join key to the board |

The **topic id is stable** and is what a cron's `deliver_to` points at. Rename
the topic; never re-create it. A re-created topic silently orphans every
delivery aimed at the old id.

---

## Delivery

Crons and watchers deliver to a **topic**, never to the group root. A job
delivering to the root defeats the whole map: the message lands in `General`
where nobody's filter looks.

---

## What topics are not

**Topics are for the human.** They are the supervision and archive surface.

Agents do not read them. A briefing posted to a topic performs zero work for
the worker — it only *looks* like dispatch. Instructions reach a lane through a
session notification carrying that lane's session UUID.

This is the single most expensive confusion in a factory, because the failure
is silent: the topic shows a briefing, the lane shows nothing, and the operator
believes work is in progress.
