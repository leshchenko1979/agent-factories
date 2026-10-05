# Owner-Gated Lane Intake — holding a lane's automation while it awaits the owner

**Proposal ID:** `PROP-08-OWNER-GATED-INTAKE`
**Target:** the OpenCrabs harness (runtime behaviour), reaching every factory through the
harness binding
**Author:** meta-factory (this lane)
**Date:** 2026-10-03 · **rev.8** 2026-10-05 — **streamlined**: every correction from revs.2–7 is
folded into the body instead of stacked as a supersession; the revision log is compressed to the
Appendix. All load-bearing citations re-verified at harness HEAD `b7470b56` (2026-10-05).
**Status:** design input — **not law**. Owner ruled 2026-10-05: **HOLD + rework** (q59);
Q1 (q60) and Q6 (q61) answered and folded (§4.1, §10). **Nothing is implemented** — the six
proposed names are absent from the tree (checked this turn).
**Related:** `PROP-01` (cron-gated goal pipeline), `PROP-02` (human-load pacing),
`docs/addons/harness/opencrabs.md`; harness issues upstream — #13 (in-flight failsafe),
#43/#50 (notify quiet mode), #344 (durable await record), #393 (delivery modes),
#547 (oc-questions). Adversarial review: `docs/proposals/08-owner-gated-lane-intake.review.md`.

---

## 1. The problem

A lane's turn can end in **three** states. The harness distinguishes **two**.

| State | Durable record today? | What the harness does when new traffic arrives |
|---|---|---|
| **Done** — no pending work | none needed | wakes the lane; correct |
| **Awaiting an external completion** — a CI run, a peer lane | yes: `await_kind/await_ref/await_at` (#344) | resumed at boot; re-checked by a sweep |
| **Awaiting the OWNER** — a plan card, a blocking question | **none** | **wakes the lane and starts a fresh turn** |

The failure, in the owner's words (2026-10-03):

> *"the awaiting user input state is just flooded over by a wave of new notifications and
> info and tasks and the previous work is just lost."*

The mechanism is exact, and it is why no existing gate catches it: **an awaiting-owner lane is
idle, not mid-turn.** The #13 mid-turn gate (`session_routes.rs:416`) refuses only while a turn
is *running*. So the next cron `deliver_to: session:<uuid>`, the next `session_notify`, the next
background completion all find the lane idle and **start a new turn**; the pending question
scrolls out of working state.

Classify it: a **context-capacity failure** (a pending decision evicted by intake) whose counter
is **operational** — gate the intake, do not strengthen the generator
(`docs/methodology/01-llm-weakness-counters.md` §13).

---

## 2. What the substrate already has

Almost every part of the fix exists. The gap is that nothing connects them.

| Piece | Where (HEAD `b7470b56`) | What it gives |
|---|---|---|
| Durable await record | `session_binding.rs:71-83` (`await_kind/await_ref/await_at`, `is_awaiting()`) | a restart-surviving per-binding "I am parked" flag |
| Await writer, `owner_gate` a named kind | `await_external.rs:36` (`AWAIT_KINDS`) | the owner wait is **already a named kind** — but gates nothing |
| Periodic sweep | `await_sweep.rs:217` (`sweep_inner`) | a timer that re-checks a lane parked too long |
| Boot resume | `resume.rs:2166` (`awaiting_for_channel`) | a parked lane is not lost across restart |
| **Delivery chokepoint** | `session_routes.rs:366` `deliver_to_session` → `Delivery{Delivered, Parked, NoRoute, RefusedInFlight, Redirected}` | every non-owner push passes here |
| **Durable parking** | `notify_queue.rs:38,85,169` (`MAX_ROW_AGE_SECS`, `wrap_busy_once`, `redeliver_persisted`) | a held push is persisted, not lost; redelivery exists |
| Delivery policy (#393) | `notify_policy.rs:29` `DeliveryMode{TurnEnd, Interrupt, Quiet{quiet_for, max_delay}}`; `resolve_mode:155` | modes + a starvation cap to reuse |
| Mid-turn probe | `session_routes.rs` `turn_probe` (channel gate #501/#845) | the shape of a per-session state probe to copy |
| Plan state | `plan_files.rs:200-218` (`PlanModeState::PostInitEditing:208`) | "awaiting owner" is already derivable for the plan case |
| Open Questions register | upstream #547 (`oc-questions`) — **an external add-on, not in the harness** | a parked owner decision is already durable |

**The missing link:** nothing reads the await state at delivery time, and `owner_gate` gates
nothing.

---

## 3. Best practices — the convergent core

Approval-pattern workflow engines (Temporal `wait_condition` + Signal + timeout), durable-execution
human-in-the-loop, actor mailboxes with backpressure, support-desk "waiting on customer", MCP
elicitation and BPMN message-catch events all converge on one shape: **a durable, named "awaiting
the human" state; the human's reply is the signal that clears it; every other producer queues
behind it; a timeout escalates to the human rather than waiting forever.** The design below is
exactly that.

---

## 4. The design

### 4.1 The state: `awaiting_owner`, declared — not inferred

One durable state on the session binding, the same home as the await record, so it survives
restart.

**Set path — opt-in + a per-lane declaration (owner ruling q60, 2026-10-05).** The harness does
**not** infer the state from a generic turn end; a lane that wants its automation held says so.
Two paths set it, and both are *named objects the lane created*, not inferences:

| Producer | Sets the state? |
|---|---|
| A plan in `PlanModeState::PostInitEditing` (the approvable card) | **yes** — an explicit object the lane created |
| `await_external kind=owner_gate` | **yes** — the call names the kind |
| `suggest_options` fired | **only on an opt-in flag** — non-blocking by contract (`suggest_options.rs:1-14`); a flagged card joins the declaration surface |
| an open question parked (`oc-questions`) | **no harness path** — the add-on declares via the CLI below |

**The declaration surface** — one CLI verb mirroring `opencrabs session notify` → `session/notify`
→ `deliver_to_session` (`cli/session_notify.rs`):

```
opencrabs session await set   --session <id> --kind <owner_gate|peer_lane> --ref <id> [--prompt <text>]
opencrabs session await clear --session <id>
```

posting to a new `session/await` A2A method. This is how the open-questions add-on — and any
future add-on — parks its lane, and it keeps the direction right: **add-on → harness public
interface**, never the reverse (the harness names no add-on; `grep -rn "oc-questions" src/` → 0
hits).

**Cleared** by the correlated signal (§4.3), or explicitly.

The state is not owner-only: a lane may be parked on a **peer lane**, whose record already exists
(`await_kind='peer_lane'`). §11 generalises the gate to it.

### 4.2 The gate — one place, keyed on the resolved mode

Add one check at the **route layer** (`session_route:492` / `deliver_or_park`), not only inside
`deliver_to_session`: the "single chokepoint" is not single today — `deliver_or_park` calls
`session_route` directly (`restart_recovery.rs:109-111`) and that is the exact path the boot
redelivery of held rows uses (`notify_queue.rs:231`). A gate placed above that layer leaks the
whole held wave on restart.

- If the target `is_awaiting()` **and** the resolved mode is **not** `Interrupt` **and** the push
  is not the awaited signal → **park durably** in `notify_queue`, return a new
  `Delivery::HeldForOwner { since }`.
- **`Interrupt` bypasses** — the urgent tier (#393) must land (Gatus alerts).
- **Unknown state → deliver** (fail open), the posture of every existing gate.

**Key the gate on the mode, never on the `interrupt` bool.** `deliver_to_session` receives a bare
`interrupt: bool` (`session_routes.rs:366`) and **every production producer hardcodes it `true`** —
cron `:1035`, A2A `:347`, the `session_notify` tool `:563`, subagent spawn `:99`, background tasks
`:1363,1443`, restart recovery `:700`, quiet release `:198`. The code says why: `#393 TRAP: this
literal MUST stay true … keeps the mid-turn gate disarmed for EVERY mode` (`subagent/notify.rs:558-562`,
`a2a/handler/notify.rs:342-346`). A gate keyed on that bool parks nothing. **Do not flip the
literal** — that re-arms the mid-turn gate and refuses deliveries #373 deliberately stopped
refusing.

Since #393 the resolved `DeliveryMode` is already computed in both notify handlers
(`resolve_mode`, `notify_policy.rs:155`) and then discarded before the call. The change is one
step: **plumb the mode into `deliver_to_session`** (as an added parameter — the bool keeps its
job) and gate on `mode != Interrupt`. No producer learns a new rule.

### 4.3 The clear — correlated, on one hook, three surfaces

The clear must be the **signal**, not any owner message. An unrelated owner message is *input*;
clearing on it drains the wave and buries the question again — contradicting §3's own rule.

- **Correlated signal only:** the plan approve/discard callback (`flow_chrome.rs:63` `"plan:ok"`,
  handled `agent.rs:1813`), the tapped option, the open-question answer.
- **One hook, three surfaces:** text, **callback query** and **reaction** (👍, `agent.rs:2436`).
  Neither of the owner's two real approval gestures is `handle_message`, so a clear in
  `channels/*/handler.rs` alone misses both.
- **Owner identity is not on the wire:** `PushOrigin` has no owner variant (`types.rs:218`) and
  `QueuedUserMessage` carries no sender (`:311`). Key the clear on the channel's configured owner
  id inside the handler; drop the owner predicate from the delivery gate.

### 4.4 Drain as a digest, not a wave

When the state clears, **do not** deliver the parked rows as N turns — that reproduces the flood,
merely delayed, and re-buries the question the hold protected. Deliver **one** summary turn —
*"14 pushes were held while you were away"*, one line each, **the pending question first** — and
let the owner pull the rest. The seam exists (`wrap_busy_once`, the `queued_message_join`
coalescing path). The digest runs **after** the answer turn, framed with a reference to the
question.

### 4.5 Receipts — a hold must print itself

- A held push logs and reports itself (`HELD: awaiting owner since <ts>`), so "held
  deliberately" and "silently dropped" are never the same output.
- The state is readable from the binding, so a third party can tell why a lane is quiet.

```mermaid
flowchart TD
    A(["push for session S<br/>session_notify · cron session: · bg completion"]) --> B{"S.is_awaiting()?"}
    B -->|no / unknown| D["deliver (fail open)"]
    B -->|yes| F{"resolved mode = Interrupt?"}
    F -->|yes — urgent| D
    F -->|no| C{"correlated to S's wait?"}
    C -->|yes — the signal| E["deliver AND clear state"]
    C -->|no| G["PARK in notify_queue<br/>Delivery::HeldForOwner"]
    E --> H["digest the parked rows<br/>question first"]
    G -.->|TTL / nudge budget| I(["owner re-nudged · then terminal state"])
    style G fill:#fff3cd,stroke:#b8860b
    style E fill:#d4edda,stroke:#2e7d32
```

---

## 5. What changes, per file

| File | Change | Risk |
|---|---|---|
| `db/repository/session_binding.rs` | `awaiting_owner` set/clear/read (or reuse `await_kind='owner_gate'`); add `await_prompt`, `last_nudge_at` | migration-light (await columns already exist) |
| `brain/tools/plan_tool.rs`, `suggest_options.rs` | set the state for the approvable plan card, or a card the lane flagged blocking | opt-in only; must not fire on non-interactive surfaces |
| `cli/session_notify.rs` + new `cli/session_await.rs`; A2A `session/await` | the declaration verb (add-on → harness public interface) | new public interface; the harness must name no add-on |
| `brain/agent/service/session_routes.rs` | new `Delivery::HeldForOwner`; gate at the **route layer**; plumb the resolved `DeliveryMode` in | the one behavioural change; unit-testable |
| `brain/agent/service/notify_queue.rs` | `drain_for_session(id)` emitting the **digest** | reuses `redeliver_persisted` internals |
| `channels/*/handler.rs` + `agent.rs` (callback / reaction hooks) | clear the state on the correlated signal, on **all three** surfaces | must be the owner, not any member |
| `channels/telegram/await_sweep.rs` | for `awaiting_owner`: nudge the **owner** (no wake), `last_nudge_at`, geometric backoff | changes sweep semantics for one kind only |
| `cron/scheduler.rs` | none — already routes through `deliver_to_session` | — |

---

## 6. Failure modes and their guards

| Failure | Guard |
|---|---|
| A lane wrongly marked awaiting → its automation stalls | fail open: unknown/unreadable state delivers; the state clears on the correlated signal; a TTL expires the held rows |
| A push is held and then lost | `notify_queue` is already durable; held rows ride the existing boot redelivery; the 72 h reap logs every drop loudly |
| A lane is never answered | the sweep re-nudges the owner (no-wake); a nudge budget then a terminal state (§8) |
| An urgent alert is held | `Interrupt` bypasses the gate |
| The gate itself becomes the flood (the sweep re-waking lanes) | for `awaiting_owner` the sweep targets the owner, not the lane |
| A non-owner member clears the state | the clear is keyed to the owner identity, not to any inbound message |
| **Peer case:** a cyclic wait (A↔B) | wound-wait cycle rule (§11) |
| **Peer case:** a waiter blocked transitively on the owner | the sweep probes the peer first and escalates to the owner (§11) |

---

## 7. Verification

- **Unit — the gate says no:** a binding with `awaiting_owner` + a `session_notify` push →
  `Delivery::HeldForOwner`, one row in `notify_queue`, no turn started.
- **Unit — the signal:** a correlated owner signal → `Delivered`, state cleared.
- **Unit — urgent bypass:** same binding + `Interrupt` → `Delivered`.
- **Unit — the digest:** N held rows + a clear → **one** summary turn (not N), question first.
- **Positive control:** no binding / unreadable state → `Delivered` (proves the gate can return
  "no", so its "yes" is not vacuous).
- **Integration:** a lane parked on a plan card; a cron with `deliver_to: session:<uuid>` fires →
  the cron parks; the owner presses Approve → the plan proceeds and the digest follows.
- **Starvation:** a held row past the TTL → expired with the reason recorded, never delivered
  stale.

---

## 8. Open questions for the owner

The HOLD was a rework order, not a rejection of the diagnosis. Q1 (q60) and Q6 (q61) are answered
and folded; Q7 (off-hours) and Q8 (declaration verb) were resolved in revision. What remains:

| # | Question | Recommendation | Blocks re-approval? |
|---|---|---|---|
| **Q2** | Starvation cap: how long may a push be held? | the existing 1800 s `quiet` cap, configurable | no — mechanism detail |
| **Q3** | Does `Interrupt` bypass? | yes — an alert must land (the Gatus exception) | **eyeball this one** |
| **Q4** | A held cron: drained, or re-scheduled? | neither — **digest** (§4.4) | no |
| **Q5** | State scope: per binding or per session? | per binding, matching the await record | no |
| **Q9** | Nudge window & budget | measured, not configured (owner-scoped clock, §Appendix); 3 nudges, geometric backoff, TTL 24 h | no |
| **Q10.1–5** | Peer-case details | minted per-wait id; wound-wait; propagated deadline (floored); owner as escalation target; derive the graph, do not store | no — §11 extension |

---

## 9. Boundary — who implements what

The runtime change belongs to the **OpenCrabs harness** (a fork issue on
`leshchenko1979/opencrabs`, this proposal attached). This factory's part is the **process law**
that follows from it: what a lane must do when it parks, what a sender must expect (its push may
be held), and the reversibility test it applies before asking at all (§10). The two ship
together — the harness leg alone would hold pushes with no lane-side rule to declare the wait;
the law alone would have nothing to enforce.

---

## 10. The reversibility test — lane-side law, upstream of the gate (owner ruling q61)

The owner's objection to "safe default on timeout", and it is correct: *if the lane knows what it
would do, why did it ask?* The default is not a *timeout policy* — it is an **ask-time
classification test**, and the presence of a safe default is itself the evidence the question
need not have been asked. Best practices converge on **reversibility**, not preference (Bezos'
one-way/two-way doors; Parasuraman levels of automation; human-on-the-loop; Apache lazy
consensus).

| Decision class | Test | Action | Parks the lane? |
|---|---|---|---|
| **Two-way door** | reversible, bounded blast radius | decide, record, **notify as FYI** | **no** |
| **One-way door** | irreversible or unbounded | ask; on timeout **escalate / hold — never auto-proceed** | yes |
| **Reversible, but the owner cares** | reversible, but a cost or rule he would want to weigh | **lazy consensus**: announce the default + a deadline | soft (only if T > 0) |

The residual timeout default survives **only** as lazy consensus — an *announced* default with a
deadline, never a default bolted silently onto an open question. **Q2 is upstream of Q1:** if
two-way-door decisions stop parking lanes, most of the flood disappears at the root and the §4
gate carries only genuine one-way-door asks. The gate is the safety net; this rule is the
load-shedding. It is **lane-side process law** (the factory's half of the §9 boundary), not a
harness behaviour — the harness cannot know whether a question is a two-way door.

---

## 11. Peer-lane waits — the same state, a correlated signal, and two new failure classes

Raised by the owner, 2026-10-04: *"What if a lane is waiting not on the human but on another
lane?"*

### 11.1 The state already exists — the signal and the gate do not

`await_external` accepts `peer_lane` today (`await_external.rs:36`), the record is durable on the
binding, boot resumes it, and the sweep re-checks it. So a peer wait is **not** a gap in the
state — it is a gap in **how the wait is cleared**. For an owner wait the clearing signal is
origin-identifiable; for a peer wait the reply is an ordinary push, and `session/notify` carries
**no correlation field** (`grep request_id|correlation|reply_to` → **0 hits**). Gating without a
correlation is wrong either way: bypass "anything from the peer" and the peer's *unrelated*
pushes walk through; bypass nothing and the *actual answer* is held behind the gate that waits
for it.

### 11.2 Two failure classes owner-waits do not have

| Failure | Shape | Why owner-waits are immune |
|---|---|---|
| **Cyclic wait (deadlock)** | A waits on B, B waits on A; no human is in the loop to break it | a human answers, or does not — there is no second waiter to close a cycle |
| **Transitive block on the owner** | A waits on B; B is parked on `owner_gate`. A's record says `peer_lane`, so the sweep wakes *A* — into the flood — while the real blocker is the owner's unanswered question | an owner wait's root block *is* the owner; a peer wait's root block may be one hop away |

### 11.3 What the best practices say

Temporal Signals (`wait_condition` on a *named* Signal); Erlang/Akka selective receive (consume
only the correlated ref, leave the rest in the mailbox); gRPC deadline/cancellation propagation;
BPMN message-catch with a correlation key + boundary timer; AMQP `reply_to` + `correlation_id`;
Chandy–Misra–Haas deadlock probes / wound-wait; circuit-breaker bulkheads; saga compensation.
**Convergent core:** the same durable wait state, a signal that is **correlated** rather than
**origin-based**, a **deadline that propagates** along the chain, and a **cycle rule** — because
peer waits, unlike owner waits, can deadlock.

### 11.4 Design additions (generalise §4, add four pieces)

1. **Generalise the gate.** Key §4.2 on `is_awaiting()` (predicate exists, `session_binding.rs:82`)
   rather than on `owner_gate` alone. One gate, both kinds.
2. **Correlated bypass — the one new wire field.** Add a **request-side** `request_id` /
   `correlation_id` to `session/notify` and the `session_notify` tool (a *reply-side* `reply_to` is
   wrong — B cannot echo a token it never received). A push whose token matches the waiter's wait
   token is **delivered and clears the wait**; every other push parks.
3. **Deadline propagation.** Add `await_deadline`; A's effective deadline is `min(A's own, B's
   remaining)`. The sweep walks deadlines, not arrival order, so a chain unblocks root-outward.
4. **Cycle rule (wound-wait).** Before recording a `peer_lane` wait, walk the wait-for graph for a
   path `B → … → A`. On a cycle, the earlier-deadline wait is broken by escalating; the later keeps
   waiting. (`set_await` has no transaction spanning graph-read + edge-write, `await_external.rs:150-160`
   — serialise declares, or detect cycles in the sweep.)
5. **Transitive escalation.** When the sweep finds a `peer_lane` waiter whose peer is itself parked
   on `owner_gate`, escalate to the **owner**, naming the chain — *"A is blocked because B awaits
   your approval"* — and do **not** wake A.
6. **Sweep semantics change for one case only.** Today the sweep clears the record and wakes the
   waiter; for a gated peer wait, **probe the peer first**; wake only if the peer cannot answer;
   if the chain ends at the owner, nudge the owner.
7. **Idempotency.** A boot redelivery can deliver a reply twice — the waiter dedupes on the token.

### 11.5 Open questions (peer case)

Minted per-wait id with `await_ref` as the human-readable handle (a lane may wait on the same peer
twice) · wound-wait, not hard refusal (a refusal would need the whole graph) · a propagated
deadline floored at a fixed minimum · the owner as escalation target (the peer gets an
informational copy) · derive the edges, do not store — but from the **validated peer session id +
token in its own column**, never from free-text `await_ref` (`await_external.rs:86`).

---

## Appendix — corrections folded into this revision, and the revision log

This rev.8 replaces the stacked supersession sections (revs.3–7) with one design. The corrections
they carried are all **in the body above**; this appendix records what they were, so a reader who
saw an earlier revision can find where each landed.

### A. Corrections from the adversarial review (were §11)

| rev.2 said | Corrected (now in) |
|---|---|
| gate on `mode != interrupt`, but `deliver_to_session` takes a bare bool that is `true` everywhere | gate on the **resolved `DeliveryMode`**, plumbed in — never flip the literal (§4.2) |
| gate inside `deliver_to_session` alone | gate at the **route layer** — `deliver_or_park` bypasses it, and boot redelivery uses that path (§4.2) |
| set the state on `suggest_options` | never auto — **opt-in flag only** (§4.1) |
| reuse `await_sweep` as-is | it consumes-then-wakes and serves telegram only; add a **no-wake nudge** branch, `last_nudge_at`, every channel (§5) |
| starvation cap force-delivers the wave | cap on **owner non-response** → escalate / expire; never inject automation into the lane while the question is open (§6, §8) |
| clear in `channels/*/handler.rs` | clear on **three surfaces** (text, callback, reaction) — the owner's two real gestures are neither (§4.3) |
| drain parked rows in arrival order | **digest**, one turn, question first (§4.4) |
| `PlanStatus::Editing` | the approvable state is `PlanModeState::PostInitEditing` (`plan_files.rs:208`); `plan_mode_state` has a side effect — unsafe on the hot path (§2) |

### B. Corrections from the owner review (were §12–§13, §15)

| Point | Folded in |
|---|---|
| `oc-questions` is an **external add-on**; the harness must not depend on it | the declaration is a **CLI verb → `session/await`**; direction is add-on → harness (§4.1) |
| the sweep has **no payload to re-emit** | new optional **`await_prompt`** (the owner-facing text/card); cadence bounded, `last_nudge_at` dedup (§4.1, §5) |
| quiet hours were an **assumption** where the substrate has a **measurement** | the nudge consumes an **owner-scoped** activity clock — `note_owner_activity()`, written beside the fleet-wide `LAST_ACTIVITY` (which is fleet-scoped and branches on nothing, so it cannot say "the owner is awake"); polarity is the **inverse** of the reclaim; the reclaim's starvation cap must **not** force through this gate (§8 Q9) |
| "safe default on timeout" is incoherent | replaced by the **ask-time reversibility test** (§10) — owner ruling q61 |
| the auto-set list | **withdrawn**; opt-in + per-lane declaration — owner ruling q60 (§4.1) |

### C. Citation re-verification (was §14)

Every load-bearing citation was re-read through the **code index** (`scope="external"`, which
covers `/root/opencrabs/src`) **and** confirmed against source, then re-confirmed at HEAD
`b7470b56` for this revision. Two line slips found and fixed: `resolve_mode` is
**`notify_policy.rs:155`** (rev.6 wrote `:151`); the binding setter is **`set_await:229`** and
`:288` is `clear_await_of_kind` (rev.5 wrote `:288`). Two citation slips whose *claims* stand.
Instrument characterised before trusting a zero (AGENTS.md rule 7): the index answers a bare
symbol well but returns "No matches" for an English query against a *type* — a phrasing artifact,
not an absence. The six proposed names (`HeldForOwner`, `awaiting_owner`, `await_prompt`,
`last_nudge_at`, `note_owner_activity`, `session/await`) return **0 hits each** — the positive
check that this is still a design, not code.

### D. Revision log

| rev | date | change |
|---|---|---|
| 1–2 | 2026-10-03/04 | initial design; peer-lane waits added |
| 3 | 2026-10-04 | adversarial-review corrections (mode-vs-bool, route-layer gate, clear surfaces, digest) |
| 4 | 2026-10-04 | add-on boundary, `await_prompt` re-nudge payload, sleeping-owner rules |
| 5 | 2026-10-04 | off-hours measured not configured; safe-default → ask-time test |
| 6 | 2026-10-04 | every citation re-verified through the code index |
| 7 | 2026-10-05 | owner rulings: HOLD + rework; Q1 opt-in + declaration; Q6 reversibility test |
| **8** | **2026-10-05** | **streamlined** — revs.3–7 folded into one design + this appendix; line slips fixed |

