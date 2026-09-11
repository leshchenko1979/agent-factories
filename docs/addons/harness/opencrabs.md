# Add-on: `harness/opencrabs`

**Class:** binding — harness · **Status:** proven (all four factories)
**Binds:** OpenCrabs as the agent runtime

A **harness binding** is the runtime the factory's agents run inside. It adds no
domain topics, no roles and no gates of its own. What it adds is the
*mechanics* by which the core's runtime requirements are met on one product.

---

## Take it when

The factory's lanes are OpenCrabs sessions — spawned, resumed, addressed and
scheduled by the OpenCrabs daemon.

If the lanes run under a different runtime, this binding does not apply. Write
the binding for that runtime instead; the
[binding rule](../../addons.md#the-binding-rule) is what makes that swap cheap.

---

## What it binds

| Core requirement | How OpenCrabs satisfies it |
|---|---|
| A session loads its law before acting | Skill files + `load_brain_file`; the always-loaded brain file carries a recovery anchor |
| A lane is addressed directly | `session_notify` to the session UUID |
| A lane can be woken for a new turn | `send_input` into a running session; `resume_agent` for a stopped one |
| Periodic processes exist | **`cron_manage`** — scheduled jobs that run in isolated sessions |
| A check can be a command | `bash` with a return-code contract, plus the `oc-*` tool set |
| Work leaves a durable trace | Ledger/journal files, git-tracked |

---

## Loading the law

The process law is a **skill file**. A session reads it, and — because the law
lives in message history and history is cleared by compaction — **re-reads it
after every compaction, before any ruling, dispatch or status claim.**

The always-loaded brain file carries a one-line pointer to the skill. That
pointer is the recovery anchor: it is re-injected on every turn, so it survives
what the skill itself does not.

**Brain files are workspace state, not repo state.** They live outside the
factory repo and are not versioned with it. A rule that must survive belongs in
the skill (versioned, mirrored) or in the always-loaded brain file — never only
in a session's context.

---

## Direct address — `session_notify`

A lane is briefed by a notification carrying its **session UUID**. Never by a
post in the shared channel: agents do not read the chat surface.

### The parking trap

> **`session_notify` does not reach a freshly spawned session.**

A new session has no channel binding yet, so the daemon parks the message:

```
No surface claims session <uuid> … parking until its channel claims it
```

The notification is *accepted* — it returns a receipt id — and then does
nothing. This is the silent-no-op failure mode: dispatch looks successful and
the lane idles blind.

**Every kickoff therefore has two hops:**

1. `session_notify` — for the record, and for any session already bound.
2. `send_input` into the running session — the hop that actually delivers.

Verify by reading the lane's first reply. A receipt id is proof the message was
*accepted*, not that it was *read*.

### Delivery cadence

`session_notify` supports a delivery mode. Default to the **deferred** mode for
receipts and acknowledgements; use the immediate mode only for something
genuinely urgent. A lane that gets interrupted for every routine receipt stops
making progress.

### Known defect

`opencrabs session notify --mode turn-end` from the CLI is unusable: the CLI
always emits `interrupt:false` alongside `delivery.mode`, and the policy
rejects the pair (exit 4, *"delivery.mode and interrupt disagree"*). Use the
tool surface, not the CLI, until that is fixed.

---

## Periodic processes — `cron_manage`

**Every recurring process in an OpenCrabs factory is a `cron_manage` job.** It
is the only supported scheduling surface, and it is where "do this daily" is
expressed.

| Field | Meaning |
|---|---|
| `name` | Job name — the identifier you will use to update it |
| `cron` | Five-field expression: `min hour dom mon dow` |
| `tz` | IANA timezone — the schedule runs in that zone's local wall clock, DST-aware |
| `prompt` | What the isolated session does when the job fires |
| `deliver_to` | Where the result lands — a **topic**, never the group root |
| `enabled` | Whether it fires at all |

**Actions:** `create` · `list` · `update` (only the fields you pass are touched)
· `delete` (needs `confirm: true`) · `enable` / `disable` · `test` (fires on the
next scheduler tick).

### The thin-trigger rule

> **A cron does one thing: notify the owning session. The work runs in that
> session, under the current law.**

A cron prompt is frozen at creation. It cannot be updated by a skill change, so
procedure placed inside a prompt silently goes stale while the law around it
moves on. Keep prompts thin and the law in the skill.

### Delivery

Deliver through `deliver_to` pointing at the right **topic**
(`oc://telegram/<chat>/<thread>`, or the legacy `telegram:<chat>:<thread>`).
A job delivering to the group root defeats the topic map — the message lands in
`General` where nobody's filter looks.

### Creating one

Creating a job is a write, and a write needs a receipt. **Never announce a
scheduled job without the `cron_manage` result that created it** — a described
job that was never created runs never, and the failure is silent until someone
asks why nothing happened.

---

## Mechanical gates

Where a check can be a command, it is a command with a documented return code.
The harness supplies `bash` plus the `oc-*` tool family
(`oc-ledger`, `oc-prchecks`, `oc-order-validate`, `oc-deploy`, `oc-attrib`).

Two harness-specific traps when writing gates:

- **The shell is `dash`, not `bash`.** `${PIPESTATUS[0]}`, `[[ ]]` and arrays
  fail. `cmd | head; echo $?` reports *head's* return code, not the command's —
  a false verdict waiting to happen. Redirect and read the tool's own code:
  `cmd > /tmp/o 2>/tmp/e; echo rc=$?`
- **Text read back through tool output can differ from the bytes on disk.**
  Never file a defect on a rendering. Prove it with an exit code or a checksum:
  `cmp -s a b; echo rc=$?` — numbers and hex cannot be text-mangled.

---

## Costs

- **Sessions are stateful and long-lived**, so a factory accumulates context
  that must be compacted — and compaction is what the recovery anchor exists
  for.
- **Brain files are outside the repo**, so they are not diffable with the law
  and not restored by a checkout. Mirror anything durable to a git remote.
- **Cron prompts are immutable in practice** (see the thin-trigger rule), which
  puts real pressure on keeping them trivial.

---

## What changes if the harness is swapped

Take this binding out and the following core rules lose their mechanics — each
needs a replacement, not a deletion:

| Core rule | Needs, on the new runtime |
|---|---|
| A session reloads its law after compaction | An always-injected anchor + a versioned law file |
| A lane is addressed directly, not via the chat | A per-agent inbox with a stable address |
| A freshly started agent may not be reachable | A delivery-confirmation step before trusting dispatch |
| Recurring processes are scheduled jobs | A scheduler, with per-job delivery targets |
| A cron prompt cannot carry procedure | The same constraint, stated wherever jobs are defined |
| Checks are commands with return codes | A shell or equivalent with a usable exit-status contract |
| Durable state is mirrored off the working box | A remote store, versioned |

The **parking trap** is the sharpest example of why this split exists. It is
not a law of agent factories — it is a quirk of one harness. Filed in the core,
it would teach every future factory a lesson that does not apply to it.
