# The chat surface

> **This file has moved.** The chat surface is a **binding** — mechanics that
> belong to one product, not to the core law.
>
> See [`docs/addons/surface/telegram-forums.md`](../docs/addons/surface/telegram-forums.md)
> for the Telegram forums binding: the topic spine, the naming law, topic ids,
> delivery targeting, bot rights, and the one-way door.

## Why it is not in the core

The core law states a **requirement**: *a work unit has its own named place, and
its state is readable at a glance.* That is true on any surface.

Everything this file used to say — topics, forum groups, `thread_id`, the
`GetForumTopics` read-back — is the **mechanics** by which one particular
surface satisfies that requirement. Keep those in the binding and the core
survives a surface swap; copy them into the core and the law quietly goes wrong
the day the surface changes.

See [the binding rule](../docs/addons.md#the-binding-rule).

## Retiring a place

The chat map accumulates dead entries: a group superseded by a forum, a forum
whose factory moved, a group left behind by a migration. **A place that still
exists and still has a binding is a place a delivery can still land in**, so a
stale place is retired deliberately rather than left to rot.

Three rules hold on any surface:

- **Read the live shape before trusting a written record.** Chat type, member
  count and last message date come from the surface. A record can be wrong in
  ways that still look right.
- **A migrated group is not a duplicate.** A group upgraded to a supergroup
  leaves a zero-member shell with a migration event as its last message. It is
  the same place's old identity, not a twin — leave it, and point nothing at it.
- **Never retire a place that is still the archive.** Retirement means nothing
  routes to it any more; it does not mean deleting history.

The order of operations — re-point the deliveries and re-read the table, retire
the bindings, record the live facts — is **mechanics**, and lives in the
binding: [`docs/addons/surface/telegram-forums.md`](../docs/addons/surface/telegram-forums.md#decommissioning-a-place).
