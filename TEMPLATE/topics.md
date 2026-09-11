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
