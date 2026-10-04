# Owner-Gated Lane Intake — holding a lane's automation while it awaits the owner

**Proposal ID:** `PROP-08-OWNER-GATED-INTAKE`
**Target:** the OpenCrabs harness (runtime behaviour), reaching every factory through the
harness binding
**Author:** meta-factory (this lane)
**Date:** 2026-10-03 · **rev.2 2026-10-04** (§10: peer-lane waits)
**Status:** design input — not law; owner has not ruled
**Related:** `PROP-01` (cron-gated goal pipeline), `PROP-02` (human-load governed pacing),
`docs/addons/harness/opencrabs.md`; upstream `leshchenko1979/opencrabs` — #13 (in-flight
failsafe), #43/#50 (notify quiet mode), #344 (durable await record), #547 (oc-questions)

---

## 1. The problem

A lane's turn can end in **three** states. The harness distinguishes **two**.

| State | Durable record today? | What the harness does when new traffic arrives |
|---|---|---|
| **Done** — no pending work | none needed | wakes the lane; correct |
| **Awaiting an external completion** — a CI run, a peer lane | yes: `await_kind/await_ref/await_at` on the binding (#344) | resumed at boot; re-checked by a periodic sweep |
| **Awaiting the OWNER** — a plan in `Editing`, a `suggest_options` card, an open question | **none** | **wakes the lane and starts a fresh turn** |

The failure, in the owner's words (2026-10-03):

> *"the awaiting user input state is just flooded over by a wave of new notifications and
> info and tasks and the previous work is just lost."*

The mechanism is exact, and it is why the existing gates do not catch it: **an
awaiting-owner lane is idle, not mid-turn.** The #13 mid-turn gate (`session_routes.rs`,
`deliver_to_session`) only refuses while a turn is *running*. So the next cron
`deliver_to: session:<uuid>` (the scheduler calls `deliver_to_session` at
`src/cron/scheduler.rs:1035`), the next `session_notify`, the next background-task
completion all find the lane idle and **start a new turn**. The pending question scrolls out
of the lane's working state; when the owner finally answers, the answer arrives as one more
message in a pile, and the plan card or question must be re-derived from the transcript.

Classify it: a **context-capacity failure** (the pending decision is evicted by intake) whose
counter is **operational** — gate the intake, do not strengthen the generator
(`docs/methodology/01-llm-weakness-counters.md` §13).

---

## 2. What the substrate already has (read from source, this turn)

Almost every part of the fix exists. The gap is that nothing connects them.

| Piece | Where | What it gives us |
|---|---|---|
| Durable await record | `src/db/repository/session_binding.rs:71-77` (`await_kind`, `await_ref`, `await_at`, `is_awaiting()`) | A restart-surviving, per-binding "I am parked" flag |
| Await writer, with `owner_gate` as a kind | `src/brain/tools/await_external.rs` (`AWAIT_KINDS = ci_run, peer_lane, owner_gate, external`) | The **owner wait is already a named kind** — but it is a manual habit and it gates nothing |
| Periodic sweep of stale waits | `src/channels/telegram/await_sweep.rs` | A timer that already re-checks a lane parked too long |
| Boot resume of parked lanes | `src/channels/telegram/resume.rs` (`awaiting_for_channel`) | A parked lane is not lost across restart |
| **Single delivery chokepoint** | `src/brain/agent/service/session_routes.rs` → `deliver_to_session`, `Delivery{Delivered, Parked, NoRoute, RefusedInFlight, Redirected}` | Every non-owner push passes here: `session_notify`, A2A `session/notify`, cron `session:` targets, bg completions, subagents |
| **Durable parking** | `src/brain/agent/service/notify_queue.rs` (`notify_queue` table, `redeliver_persisted`, 72 h reap) | A held push is already persisted, not lost; a redelivery path already exists |
| Delivery policy | `src/brain/agent/service/notify_policy.rs` (`TurnEnd` \| `Interrupt` \| `Quiet`, `max_delay` starvation cap) | Modes and a starvation cap to reuse |
| Mid-turn probe | `session_routes.rs` `turn_probe`, registered by the channel's #501/#845 gate | The shape of a per-session state probe to copy |
| Plan state | `src/tui/plan.rs:654` (`PlanStatus::{Editing, Active}`), plan JSON per session | "Awaiting owner" is **already derivable** for the plan case |
| Open Questions register | upstream #547 (`oc-questions ask`) | A parked owner decision is already a durable artifact |

**The missing link:** nothing reads the plan state or the open-question state at delivery
time, and `owner_gate` on the await record does not gate anything.

---

## 3. Best practices (what other systems converged on)

| Source | The pattern | The transferable rule |
|---|---|---|
| **Temporal — Approval pattern** | `wait_condition(..., timeout)` blocks the workflow until a **Signal** carries the decision; on timeout it escalates/rejects | (a) an explicit **durable wait state**, (b) the awaited input is a first-class **signal**, (c) a **timeout that escalates**, never an infinite wait |
| **Durable-execution / human-in-the-loop** | pending approvals and history survive request completion and hibernation | the waiting state must be **durable**, not in-memory |
| **Approval-queue pattern (agent frameworks)** | new work **queues behind** a pending approval; approvals survive disconnects | queue the automation, do not drop it and do not interleave it |
| **Actor mailbox + backpressure** | a message queues while the actor is in a waiting state | "idle but waiting" ≠ "idle and free" |
| **Message queueing / `prepareStep`** | queued messages inject at a **step boundary**, never mid-reasoning | delivery point is the turn boundary, same as the existing `turn-end` tier |
| **Support-desk "waiting on customer"** | a conversation status gates further automation | the state is a **named status**, readable and auditable |
| **MCP elicitation** | a tool call needs out-of-band human input; the interaction resumes on the answer | the answer is the **only** thing that clears the wait |

**The convergent core, and the design below is exactly it:** *a durable, named "awaiting the
human" state; the human's reply is the signal that clears it; every other producer's traffic
queues behind it; a timeout escalates to the human rather than waiting forever.*

---

## 4. The design

### 4.1 A first-class state: `awaiting_owner`

Promote `owner_gate` from a manual habit to a **named, durable, per-binding state** on the
session binding — the same home as the existing await record, so it survives restart and is
read by the boot classifier for free.

**Set automatically** (no lane habit) when a turn ends on any of:

- a plan in `PlanStatus::Editing` awaiting Approve;
- `suggest_options` fired (`src/brain/tools/suggest_options.rs` — currently records no state);
- an open question parked (`oc-questions ask`);
- an explicit `await_external kind=owner_gate`.

**Cleared automatically** when the owner's next inbound message arrives on the bound
chat/topic — *that message is the awaited signal* — or on explicit `clear`.

The state is not owner-only. A lane may equally be parked on a **peer lane**, and the
durable record for that already exists (`await_kind = 'peer_lane'`). What differs is the
*signal* that clears it — **correlated**, not origin-based — and the fact that peer waits
can deadlock and block transitively on the owner. §10 works that case through; the gate
below is written once and generalises to it.

### 4.2 Gate at the single chokepoint

Add one check to `deliver_to_session`, **before** the #13 mid-turn gate (the ownership gate
stays outermost):

- If the target `is_awaiting_owner()` **and** the push is not owner-origin **and** the mode
  is not `interrupt` → **park durably** in `notify_queue` and return a new
  `Delivery::HeldForOwner { since }`.
- **Owner-origin messages bypass and clear** the state (they are the signal).
- **`interrupt` bypasses** — the urgent tier (#393) must still land (Gatus alerts).
- **Unknown state → deliver** (fail open), the same posture as every existing gate.

One chokepoint covers every producer: `session_notify`, A2A `session/notify`, the cron
scheduler's `session:` arm, background-task completions, subagents. No producer needs to
learn a new rule.

### 4.3 Drain on clear

When the state clears, re-offer the session's parked rows **in arrival order, after the
owner's message has been processed**. Reuse the per-session machinery in
`notify_queue::redeliver_persisted` (a `drain_for_session(id)` beside it). One turn per
boundary; the existing queued-message join (`queued_message_join_test`) coalesces the batch.

### 4.4 Timeout escalates to the owner, never waits forever

Reuse `await_sweep`. For `awaiting_owner` the sweep must **re-nudge the owner** (re-surface
the pending question) rather than wake the lane — waking the lane is the flood this proposal
exists to stop. Independently, a held push older than a declared cap is **force-delivered**
(the `Quiet` mode's `max_delay` precedent) so a never-answered question cannot starve a
lane's automation indefinitely.

### 4.5 Receipts — a hold must print itself

- A held push logs and reports itself (`HELD: awaiting owner since <ts>`), so "held
  deliberately" and "silently dropped" are never the same output.
- The state is readable from the binding, so a third party can tell why a lane is quiet.

```mermaid
flowchart TD
    A(["push for session S<br/>session_notify · cron session: · bg completion"]) --> B{"S.is_awaiting_owner?"}
    B -->|unknown / no| D["deliver (fail open)"]
    B -->|yes| C{"origin = owner?"}
    C -->|yes — the signal| E["deliver AND clear state"]
    C -->|no| F{"mode = interrupt?"}
    F -->|yes — urgent| D
    F -->|no| G["PARK in notify_queue<br/>Delivery::HeldForOwner"]
    E --> H["drain parked rows<br/>in arrival order"]
    G -.->|starvation cap| D
    G -.->|sweep: re-nudge owner| I(["owner re-prompted"])
    style G fill:#fff3cd,stroke:#b8860b
    style E fill:#d4edda,stroke:#2e7d32
```

---

## 5. What changes, per file

| File | Change | Risk |
|---|---|---|
| `db/repository/session_binding.rs` | add `awaiting_owner` (or reuse `await_kind='owner_gate'`) set/clear/read helpers | migration-light (column already exists) |
| `brain/tools/plan_tool.rs`, `suggest_options.rs`, `oc-questions` | set the state when a turn ends on a user question | must not fire on non-interactive surfaces |
| `brain/agent/service/session_routes.rs` | new `Delivery::HeldForOwner`; gate + park branch; owner-origin bypass | the one behavioural change; unit-testable |
| `brain/agent/service/notify_queue.rs` | `drain_for_session(id)` on clear | reuses `redeliver_persisted` internals |
| `channels/*/handler.rs` | clear the state on the owner's inbound message | must be the owner, not any member |
| `channels/telegram/await_sweep.rs` | for `awaiting_owner`: nudge the owner, not the lane | changes sweep semantics for one kind only |
| `cron/scheduler.rs` | none (already routes through `deliver_to_session`) | — |

---

## 6. Failure modes and their guards

| Failure | Guard |
|---|---|
| A lane is wrongly marked awaiting → its automation stalls | fail open: unknown/unreadable state delivers; the state clears on the owner's next message; a starvation cap force-delivers |
| A push is held and then lost | `notify_queue` is already durable; held rows ride the existing boot redelivery; the 72 h reap logs every drop loudly |
| A lane is never answered | sweep re-nudges the owner; cap force-delivers the held automation |
| An urgent alert is held | `interrupt` bypasses the gate |
| The gate itself becomes the flood (the sweep re-waking lanes) | for `awaiting_owner` the sweep targets the owner, not the lane |
| A non-owner member clears the state | the clear is keyed to the owner identity, not to any inbound message |

---

## 7. Verification

- **Unit — the gate says no:** a binding with `awaiting_owner` + a `session_notify` push →
  `Delivery::HeldForOwner`, one row in `notify_queue`, no turn started.
- **Unit — the signal:** an owner-origin message → `Delivered`, state cleared, parked rows
  drained in order.
- **Unit — urgent bypass:** same binding + `interrupt` → `Delivered`.
- **Positive control:** no binding / unreadable state → `Delivered` (proves the gate can
  return "no", so its "yes" is not vacuous).
- **Integration:** a lane in plan `Editing`; a cron with `deliver_to: session:<uuid>` fires →
  the cron parks; the owner presses Approve → the plan proceeds and the parked cron drains.
- **Starvation:** a held row past the cap → force-delivered and logged.

---

## 8. Open questions for the owner

1. **Automatic or opt-in?** Derive the state from the known cases (plan `Editing`,
   `suggest_options`, open question) with explicit declaration for anything else — or require
   every lane to declare it? *Recommended: automatic for the known cases.*
2. **Starvation cap.** How long may a notification be held before force-delivery? *Recommended:
   the existing 1800 s `quiet` cap, configurable.*
3. **Does `interrupt` bypass?** *Recommended: yes — an alert must land.*
4. **A held cron: drained, or re-scheduled?** *Recommended: drained (the work is not lost).*
5. **Scope of the state:** per binding (channel) or per session? *Recommended: per binding,
   matching the await record.*

---

## 9. Boundary — who implements what

The runtime change belongs to the **OpenCrabs harness** (a fork issue on
`leshchenko1979/opencrabs`, this proposal attached). This factory's part is the **process
law** that follows from it: what a lane must do when it parks, and what a sender must expect
(its push may be held). The two ship together — the harness leg alone would hold pushes with
no lane-side rule to declare the wait; the law alone would have nothing to enforce.

---

## 10. Peer-lane waits — the same state, a correlated signal, and two new failure classes

Raised by the owner, 2026-10-04: *"What if a lane is waiting not on the human but on
another lane?"*

### 10.1 The state already exists — the signal and the gate do not

`await_external` accepts `peer_lane` as a kind today (`src/brain/tools/await_external.rs:36`),
the record is durable on the binding (`await_kind`/`await_ref`/`await_at`), the boot
classifier resumes it (`resume.rs`), and the sweep re-checks it after `await_stale_secs`
(`await_sweep.rs`). So a peer wait is **not** a gap in the state.

It is a gap in **how the wait is cleared**. For an owner wait the clearing signal is
origin-identifiable: the owner's inbound message on the bound chat/topic. For a peer wait the
reply is an ordinary push. `session/notify` carries `session_id`, `message`, `title`,
`sender`, `interrupt`, `delivery`, `notify_id`, `goal` — and **no correlation field** (read
this turn, `src/a2a/handler/notify.rs:56-144`). `notify_id` is a dedup receipt for the notify
itself, not a link back to the waiter's `await_ref`. Consequences of gating without a
correlation:

- bypass "anything from the peer" → the peer's **unrelated** pushes walk straight through and
  the flood resumes;
- bypass nothing → the **actual answer** is held behind the very gate that waits for it.

Neither is correct. The wait needs a **correlation token** (§10.4.2).

### 10.2 Two failure classes owner-waits do not have

| Failure | Shape | Why owner-waits are immune |
|---|---|---|
| **Cyclic wait (deadlock)** | A waits on B, B waits on A. Both park; no human is in the loop to break it; only the sweep eventually fires | a human answers, or does not — there is no second waiter to close a cycle |
| **Transitive block on the owner** | A waits on B; B is parked on `owner_gate`. A is blocked on the **owner** through B, but A's record says `peer_lane`, so the sweep wakes *A* — into the same flood — while the real blocker is the owner's unanswered question | an owner wait's root block *is* the owner; a peer wait's root block may be one hop away |

Both are structural. They are the reason the peer case needs a deadline and a cycle rule, not
just the gate.

### 10.3 What the best practices say

| Source | Pattern | Transferable rule |
|---|---|---|
| **Temporal — Signals** | `wait_condition` unblocks on a *named* Signal, not on any workflow event; `signal_with_start` carries the correlation | the awaited reply is a **named, correlated signal** |
| **Erlang / Akka — selective receive** | `receive { {Ref, Reply} -> … }` matches one ref and **leaves every other message in the mailbox** | consume only the correlated reply; park the rest — the gate, scoped to one wait |
| **gRPC** | deadline propagation; cancellation propagation | a peer wait **inherits** the peer's deadline; cancelling upstream cancels downstream |
| **BPMN / workflow engines** | *message catch event* with a **correlation key** + a **boundary timer** | a wait is a pair: (correlation key, timer → escalation) |
| **AMQP / message queues** | `reply_to` + `correlation_id` on the message | the **transport** carries the correlation, not the receiver's memory |
| **Distributed deadlock detection** | wait-for graph; Chandy–Misra–Haas probe messages; wound-wait | a cycle in lane waits must be **broken by a rule** — earlier deadline escalates, later one keeps waiting |
| **Circuit breaker / bulkhead** | a peer that never answers must not consume capacity forever | bounded wait → escalate; never infinite |
| **Saga / orchestration** | a timeout triggers a **compensation** | the waiter reports `blocked upstream` to its own consumer instead of hanging |

**The convergent core:** *the same durable wait state; a signal that is **correlated** rather
than **origin-based**; a **deadline that propagates** along the wait chain; and a **cycle
rule** — because peer waits, unlike owner waits, can deadlock.*

### 10.4 Design extension (generalise §4, add four pieces)

1. **Generalise the gate.** Key §4.2 on `is_awaiting()` (the predicate already exists,
   `session_binding.rs:82`) rather than on `owner_gate` alone. Hold every push except (a) the
   awaited signal and (b) `interrupt`. One gate, both kinds.
2. **Correlated bypass — the one new wire field.** Add `reply_to` to `session/notify` and the
   `session_notify` tool. A push whose `reply_to` matches the waiter's wait token is
   **delivered and clears the wait**; every other push parks. This is the AMQP / Temporal
   rule and it is the only new parameter the design needs.
3. **Deadline propagation.** Add `await_deadline`. When A declares `peer_lane ref=B`, A's
   effective deadline is `min(A's own, B's remaining)`. The sweep walks deadlines, not arrival
   order, so a chain unblocks from the root outward.
4. **Cycle rule (wound-wait).** Before recording a `peer_lane` wait, walk the wait-for graph
   for a path `B → … → A`. On a cycle, the **earlier-deadline wait is broken by escalating**;
   the later one keeps waiting. Cheapest correct rule at this scale — the probe-message
   algorithm is overkill for a fleet of tens of lanes.
5. **Transitive escalation.** When the sweep finds a `peer_lane` waiter whose peer is itself
   parked on `owner_gate`, escalate to the **owner**, naming the chain — *"A is blocked
   because B awaits your approval"* — and do **not** wake A.
6. **Sweep semantics change for one case only.** Today the sweep clears the record and wakes
   the waiter. For a gated peer wait: **probe the peer first**; wake the waiter only if the
   peer cannot answer; if the chain ends at the owner, nudge the owner (§4.4). Otherwise the
   sweep is the flood it exists to prevent.
7. **Idempotency.** A boot redelivery can deliver the peer's reply twice. The waiter must
   dedupe on the correlation token, so the reply is consumed exactly once.

### 10.5 Open questions (peer case)

1. **Correlation token:** reuse `await_ref` as the token, or mint a per-wait id? *Recommended:
   a minted per-wait id, with `await_ref` as the human-readable handle — a lane may wait on
   the same peer twice.*
2. **Cycle rule:** wound-wait (earlier deadline wins), or a hard refusal of any wait that
   would close a cycle? *Recommended: wound-wait — a refusal would require the declaring lane
   to know the whole graph.*
3. **Deadline source:** a fixed cap, or propagated from the peer? *Recommended: propagated,
   floored at a fixed minimum so a peer cannot shorten a wait below usefulness.*
4. **Transitive escalation target:** the owner, or the peer's own handler? *Recommended: the
   owner — the root block is an `owner_gate`; the peer gets an informational copy.*
5. **Graph storage:** the wait-for edges are derivable from `(session_id, await_ref)` on the
   bindings, so no new table is needed — *Recommended: derive, do not store.*
