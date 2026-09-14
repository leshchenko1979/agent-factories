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

### Rule isolation — the skill is the home, not the shared brain

OpenCrabs loads a **workspace brain file** (`AGENTS.md`, plus the other `.md`
files in the profile) into **every** session on that profile — every factory,
every lane, every unrelated conversation. A rule written there is not scoped to
the factory that wrote it; it is a rule for the whole box.

- **A factory's own rules go in its skill file**, which lives in the factory's
  repo and is discovered from the profile's `skills/` directory — versioned,
  diffable, mirrored.
- **The shared brain file carries a one-line pointer** to that skill — the
  recovery anchor — and nothing else.
- **Only a rule that must bind every session on the box** belongs in the shared
  brain.

**Mechanics.** Skills are discovered from three layers, merged by name (last
writer wins): built-ins shipped in the binary; project overlays at
`projects/<slug>/skills/<name>/SKILL.md`; and the profile overlay at
`<profile>/skills/<name>/SKILL.md`. A skill directory may be a **symlink** to
the factory's repo, which keeps one source of truth and no drift.

**Two traps, both live-verified 2026-09-11:**

- **Skill `globs:` frontmatter & just-in-time gate (#150).** In daemon versions
  carrying #150 (`b3b3fc9a`+), skill `globs:` declare governed filesystem paths.
  When any tool call touches a matching path without the skill loaded in the
  current epoch, the daemon intercepts and rejects the call with a `[SKILL GATE]`
  envelope carrying the skill's full text, forcing immediate compliance before
  execution. This mechanically guarantees law adherence across context compactions.
- **A folded-block description (`description: >`) parses as the literal `>`.**
  The frontmatter reader takes `key: value` per line, so `>` becomes the whole
  value and the indented block below it is discarded. The skill then appears in
  every prompt as `/name: >`, and the agent has nothing to decide on. **Write
  the description on one line.**

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

### Delivery mechanics — what the CLI actually does (live-tested 2026-09-11)

Reaching a lane that is **mid-turn** is the normal case, not the exception: an
active lane is `running` most of the time. The three CLI modes behave very
differently there, and only one of them works:

| Invocation | Target mid-turn | Result |
|---|---|---|
| `--mode now` (default) | ❌ | `refused_in_flight` — *"session … is mid-turn and interrupt was not set — retry when idle or resend with interrupt=true (#13 failsafe)"*, **exit 3**. Nothing is queued. |
| `--mode quiet` | ⚠️ hangs | Waits out a **60 s idle window** (`--quiet-for-secs`, default 60) before delivering. Against a busy lane the window never opens, so the call starves toward the **1800 s** cap (`--max-delay-secs`). Looks like a hang. |
| `--interrupt` | ✅ | Delivers immediately. **This is the only reliable path to a running lane.** |

`--interrupt` is documented as a *deprecated alias for `--mode turn-end`*, but
the alias is the one that works: the bare `--mode turn-end` form is still
rejected with exit 4 (*"delivery.mode and interrupt disagree"*) because the CLI
emits `interrupt:false` alongside `delivery.mode`. Use `--interrupt`.

**Budget one call per target.** Each invocation costs ~45 s of daemon init
before it sends. Batching three targets into one shell call blows a 120 s tool
timeout and leaves a partial send — chain them across separate calls, or raise
the timeout to ≥180 s, and read each `rc=` individually.

**Cadence caveat still applies:** `--interrupt` is the *delivery* path for a
running lane, but it interrupts whatever that lane is doing. For a routine
receipt to an idle lane, the deferred/quiet path is still correct — the table
above is about *reaching a busy lane*, not a licence to interrupt for trivia.

**Receipt discipline.** `✅ delivered: delivered to session <uuid>` with `rc=0`
is proof the daemon accepted and routed the message — not that the lane read
it. Confirm by reading the lane's first reply.

---

## Lane creation, reuse discipline, and binding workarounds

A topic-bound session (a "lane") in OpenCrabs requires an entry in `session_bindings`.
The daemon writes this entry **only upon processing an inbound message** (`src/channels/telegram/handler.rs:1890`).
An outbound message from the bot (`telegram_send`) does not claim the topic.

### 1. Primary rule: Reuse existing persistent lanes
Do not spawn fresh lanes or temporary topic workers for each task. The factory should
operate with a fixed roster of spine lanes (HQ, Triage, Surveys, Delegate) and persistent
worker lanes. Route work to these existing lanes via `session_notify`.

### 2. Upstream status: Mechanized topic binding
The absence of a tool or CLI command to programmatically bind a session to a topic is
tracked in upstream issue **`leshchenko1979/opencrabs#170`** (*"no instrument lets a session bind itself to a forum topic"*). OpenCrabs HQ is actively mechanizing this capability.

### 3. Temporary workaround: Userbot kickstart
Until `#170` lands in the daemon binary, if a factory must stand up a fresh topic lane without manual human intervention in the chat UI:
- Use `tg_send_message` (which authenticates as the userbot/operator account) to send the role prompt (e.g. `"You are worker"`) into the target topic.
- Because this message arrives as an **inbound update** to the OpenCrabs bot, the daemon automatically instantiates a new session and writes the `session_bindings` record.
- Read back the newly created session UUID from `session_bindings` before sending briefings via `session_notify`.

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

### The 4-step cron execution loop (Mechanical pre-flight & goal convergence)

To eliminate idle token waste and prevent conversational stopping, recurring
processes follow the 4-step execution architecture (`PROP-01-CRON-GATED-GOAL-PIPELINE`):

1. **Mechanical pre-flight check (`trigger_cmd`):** Execute a host CLI probe
   first (0 LLM tokens). If exit code is 0 / output is empty (no work / no drift),
   the job short-circuits immediately.
2. **Modal evaluation turn:** If work is detected, a lightweight model turn
   evaluates the trigger output and formulates a structured task brief.
3. **Goal notification dispatch:** `session_notify` delivers the goal and
   checkable acceptance criteria to the persistent worker lane.
4. **Inner Ralph convergence loop:** The worker lane converges against the
   goal criteria until mechanically verified, preventing premature one-shot stopping.

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

## The supplier-client loop: advising OpenCrabs and requesting features

The harness is not an external third-party black box: it is built and maintained by the
**OpenCrabs factory** (`leshchenko1979/opencrabs`), which is itself one of the member
factories on our survey roster.

The entire factory fleet (the meta-factory and all surveyed member factories) are the
primary industrial clients of the OpenCrabs harness. This creates an active feedback loop:
1. **Fleet friction & bottlenecks:** Factories encounter operational friction, scheduling
   delays, telemetry gaps (e.g. process run metrics), or awkward workarounds (e.g. topic
   binding).
2. **Consulting & aggregation:** The meta-factory identifies structural harness bottlenecks
   across the fleet and formulates concrete instrument requests.
3. **Feature dispatch:** Requests are dispatched directly to OpenCrabs Factory HQ
   (Crabs Kanban Board topic `OC DEV HQ`, session `d72bd52d-42aa-4dbd-ac99-5b5300770019`)
   via `session_notify`, or filed as fork issues on `leshchenko1979/opencrabs`.
4. **Harness evolution:** The OpenCrabs factory implements, tests, and ships binary updates
   via its release chain, resolving inefficiencies across the entire fleet at once.

Owner order, 2026-09-11: **an inadequate OpenCrabs instrument is reported to
OpenCrabs' own `HQ` as a request for the change** — for this meta-factory, the
Crabs Kanban Board `OC DEV HQ` lane, reached by `session_notify`. Core daemon
faults are a separate route (the fork's issue tracker); the rule is that each
goes to the party who owns that surface.

The same rule generalises: **a factory names the owner of every substrate it
runs on, and a defect in that substrate goes there in the same turn.** A binding
that does not name its owner leaves every future defect homeless.

---

## A write is not a read — `write_file`'s overwrite guard

Live-tested 2026-09-11. The guard is **not** mtime-based — a stale-mtime
diagnosis had been circulated in conversation, untested, and **no committed note
in this repo ever carried it**. This section is the repo's first statement on
the guard. It refuses an overwrite whenever the
file has not been *read* in this session — including a file **this session
wrote moments earlier**:

| Sequence | Result |
|---|---|
| `write_file` (creates) → `write_file` again | **refused**, fresh mtime or not |
| `write_file` (creates) → `read_file` → `write_file` | succeeds |

So the fix is to read the file, or pass `overwrite_read_confirm: true` — not to
reach for `edit_file` because the clock looked wrong. Two consequences worth
carrying:

- **The refusal message is the receipt, not a bug.** "was not fully read in
  this session" is accurate about a file you authored, which reads oddly and
  invites the wrong diagnosis.
- **Diagnose with the variable you can move.** The stale-mtime theory was
  plausible, untested, and wrong; holding mtime constant while varying the read
  separated the two in one probe.

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
