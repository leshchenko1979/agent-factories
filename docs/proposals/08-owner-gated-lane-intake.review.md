# Adversarial review — `PROP-08-OWNER-GATED-INTAKE` (rev.2)

**Reviews:** `docs/proposals/08-owner-gated-lane-intake.md` @ `ccfd418` (322 lines, rev.2)
**Substrate read:** `/root/opencrabs` @ `4a4f62d5c` (fork `main`)
**Method:** two independent subagents, different model families, read-only briefs, no shared
context with the author — one *evidence auditor* (falsify every cited file:line), one *design
adversary* (break the mechanism, not the citations).
**Instant:** 2026-10-04T06:23:03Z
**Verdict:** **fundamentally flawed as written, fixable in shape.** The diagnosis is right and
the substrate inventory is largely accurate; the load-bearing mechanism (§4.2) is a **no-op**
against the very producers it names, and three independent paths deliver a parked wave past
the gate. Every finding below was re-read from source by this lane before it was written down.

---

## 1. The convergent fatal finding — the gate's bypass predicate is `true` by construction

Both reviewers found this independently, from different directions. This lane then verified it
directly.

The gate is specified as *"if not owner-origin **and** mode is not `interrupt` → park"* (§4.2).

The only mode signal `deliver_to_session` receives is a bare `interrupt: bool`:

```
src/brain/agent/service/session_routes.rs:366
pub fn deliver_to_session(session_id: Uuid, msg: QueuedUserMessage, interrupt: bool) -> Delivery
```

and it is the **same flag that disarms the #13 mid-turn gate**:

```
src/brain/agent/service/session_routes.rs:416
    if !interrupt && turn_probe(target).is_some_and(|probe| probe()) {
```

Every production producer hardcodes it `true` — deliberately, with the reason in the code:

| Producer | Line | Value |
|---|---|---|
| cron `session:` arm | `src/cron/scheduler.rs:1035` | `true` |
| A2A `session/notify` | `src/a2a/handler/notify.rs:347` | `let interrupt = true;` |
| `session_notify` tool | `src/brain/tools/subagent/notify.rs:563` | `let interrupt = true;` |
| subagent spawn | `src/brain/tools/subagent/spawn.rs:99` | `true` |
| background task (×2) | `src/brain/agent/service/background_tasks.rs:1363,1443` | `true` |
| restart recovery | `src/brain/agent/service/restart_recovery.rs:700` | `true` |
| quiet release | `src/brain/agent/service/quiet_delivery.rs:198` | `let interrupt = true;` |

The code says why, in two places:

```
src/brain/tools/subagent/notify.rs:558-562
        // #393 TRAP: this literal MUST stay `true`. It is what keeps the
        // mid-turn gate disarmed for EVERY mode — #373's queue-instead-of-
        // refuse posture. Feeding the resolved mode into this parameter would
        // set it `false` for `turn-end` and start REFUSING deliveries that
        // today queue. The urgent tier is expressed in the frame, not here.
```

**Consequence.** A gate keyed on this bool parks **nothing**, for exactly the producers §1
blames for the flood. As written the design ships unchanged behaviour plus a new enum variant.
The design has conflated two things this codebase deliberately collapsed: the **urgent tier**
(a frame, `URGENT_FRAME`) and the **gate-disarm boolean** (`interrupt`).

**Correction (rev.3).** Do **not** flip the literal — that re-arms the mid-turn gate and
starts refusing deliveries #373 deliberately stopped refusing. Plumb the **resolved
`DeliveryMode`** into `deliver_to_session` and gate on `mode != Interrupt`. `resolve_mode`
already computes it (`src/brain/agent/service/notify_policy.rs:151`) and the two notify
handlers throw it away before the call. Gate on the mode; leave the legacy bool to its
existing job.

---

## 2. Second fatal — the state's writer and its readers are specified against different predicates

§4.1 sets the state *automatically*; §4.4 and §4.1 then claim it is *"read by the boot
classifier for free"* and that `await_sweep` can be reused.

But both readers key on `await_at IS NOT NULL`, and neither auto-derived trigger writes it:

- sweep selection: `src/db/repository/session_binding.rs:330-331`
  `WHERE b.channel = ?1 AND b.await_at IS NOT NULL ORDER BY b.await_at ASC`
- boot classifier: `src/channels/telegram/resume.rs:2166` `awaiting_for_channel("telegram")`
- `is_awaiting()` itself: `src/db/repository/session_binding.rs:83` `self.await_at.is_some()`

And the **action** both readers take is to **wake**, not hold: `resume.rs:2195-2200` pushes
into `recovery.awaiting` → `spawn_resumes` → `resume_session`; `await_sweep` clears the record
then wakes. So:

- new boolean column → `await_at` stays `NULL` → both readers skip the row → the state is
  invisible and "read for free" is false;
- reuse `await_kind='owner_gate'` + stamp `await_at` → visible, but then `is_awaiting()` is
  also true for every `ci_run`/`peer_lane`/`external` wait, and the sweep **wakes** the
  owner-wait lane — the flood.

Either horn is wrong. **Correction:** one writer, one predicate, and a **no-wake** branch for
the owner kind in both the boot classifier and the sweep.

---

## 3. Third fatal — the "single chokepoint" is not single

§2: *"Every non-owner push passes here."* It does not. `deliver_or_park` calls the route
function **directly**, skipping `deliver_to_session`:

```
src/brain/agent/service/restart_recovery.rs:109-111
pub fn deliver_or_park(session_id: Uuid, msg: QueuedUserMessage) -> bool {
    if let Some(route) = super::session_routes::session_route(session_id) {
        route(session_id, msg);
```

and it is the exact path the boot redelivery of **held** rows uses:

```
src/brain/agent/service/notify_queue.rs:231
        if super::restart_recovery::deliver_or_park(row.session_id, msg) {
```

Also `spawn_resumes` → `resume_session` (`resume.rs:1968`) and `flush_parked` → `local(...)`.

**Consequence.** The hold does not survive the restart it claims durability across: on the
next boot every held row is delivered and retired. §6's "held rows ride the existing boot
redelivery" is, in fact, flood-on-restart.

**Correction.** Move the gate's authority to the **route layer** (`session_route` /
`deliver_or_park`), or have redelivery call `deliver_to_session`. One gate, at the layer every
path already passes.

---

## 4. Majors

| # | Finding | Evidence | Correction |
|---|---|---|---|
| M1 | **`owner-origin` is not representable.** `PushOrigin` has no owner variant; `QueuedUserMessage` carries no sender identity. The gate's owner arm tests a property the message type does not have, and cannot tell the owner from another member in the same topic. | `types.rs:218-232`, `:311-321`; owner inbound enters at `handler.rs:738 handle_message`, not the gate | Key the clear on the channel's configured owner id inside the handler; drop the owner predicate from the delivery gate |
| M2 | **The clear misses the two approval surfaces the owner actually uses.** Plan Approve is a callback button, and 👍 is a reaction — neither is `handle_message`. So the owner approves and the state never clears; the lane stays parked until the cap. | `flow_chrome.rs:63` (`callback("✅ Approve plan","plan:ok")`), `agent.rs:1813`; `agent.rs:2431-2436` `handle_reaction` | One owner-inbound clear hook covering **text + callback + reaction**, keyed to (owner identity, bound session) |
| M3 | **The clear keys on ANY owner message, not the answer.** The owner posts anything unrelated → state clears, wave drains, and the question is buried again — behind the drained batch. Contradicts the design's own §3 rule ("the answer is the only thing that clears the wait"). | §4.1 vs §3 | Clear only on the **correlated** signal: the plan approve/discard callback, the `oc-questions` answer, the tapped option |
| M4 | **`deliver_to_session` is sync, reads only statics, and has no DB handle** — it cannot read the durable binding or the plan state at delivery time. | `session_routes.rs:366`; plan state is async/DB (`plan_files.rs:91`) | Specify an in-memory probe registry for the awaiting bit, populated at binding/connect, mirroring `register_turn_probe`; state the re-arm after restart |
| M5 | **The starvation cap contradicts the goal.** Force-delivery at ~1800 s injects the wave into the lane **while the question is still open** — the exact eviction, delayed 30 min. | `notify_policy.rs:179` (`max_delay_secs` 1800); §4.4, §8.2 | Key the cap on owner non-response: **escalate to the owner**; never inject the automation into the lane while the question is open |
| M6 | **Boot resume wakes an owner-gated lane.** Both boot and sweep read `await_at` regardless of kind and wake. | `resume.rs:2166-2200`, `:1943`; `await_sweep.rs:239,268` | Add the owner kind as **no-wake** in both |
| M7 | **§10's correlation token has no entry point.** The A→B request has no request-side field carrying A's token, so B cannot echo it. `reply_to` is reply-side only. | `a2a/handler/notify.rs:56-144`; `subagent/notify.rs:136-205` | Add a **request-side** `request_id`/`correlation_id`; `notify_id` is a dedup receipt, not it |
| M8 | **`await_ref` is free text, so the wait-for graph is unbuildable.** The tool stores "the lane name, the issue number" verbatim; a lane name cannot be joined to a `session_id`. §10.5.1 (mint a token, keep `await_ref` as the human handle) contradicts §10.5.5 (derive edges from `await_ref`). | `await_external.rs:36,88-92`; `session_binding.rs:246` | Store the peer's **session id** (validated) plus the minted token in its own column; derive from ids, not handles |
| M9 | **The cycle rule races.** `set_await` is a single UPDATE with no transaction spanning graph-read + edge-write; two concurrent declares each miss the other's edge and both pass. | `await_external.rs:150-160` | Serialise declares through one writer, or detect cycles in the sweep |
| M10 | **The sweep cannot be reused as specified.** It consumes the record *before* waking ("woken once per DECLARATION") and serves telegram only. For owner-gate it would clear-then-wake (flood), or re-nudge every tick with no dedup, and Discord/Slack get nothing. | `await_sweep.rs:44,230-239,268` | Separate owner-gate handling: nudge (not wake), `last_nudge_at` dedup, every channel |
| M11 | **Auto-set on `suggest_options` is wrong by the tool's own contract** — it is explicitly non-blocking/optional and has no repo handle to write state. Parking a lane on an informational card stalls its automation. | `suggest_options.rs:1-14` | Never auto-set on `suggest_options`; set only on a genuine blocking question (plan `pending_approval`, open question, explicit `owner_gate`) |

## 5. Minors

- **`PlanStatus::Editing` is not one state** — the approvable state is
  `PlanModeState::PostInitEditing` (`plan_files.rs:205-218`, mapping `:299-310`); a bare
  `Editing` also covers pre-init drafts. `plan_mode_state` has a side effect (removes a stale
  marker, `:283-289`) — unsafe on a delivery hot path.
- **A new `Delivery` variant touches every exhaustive match** (`scheduler.rs:1075`
  "Exhaustive arms, deliberately"; `a2a/handler/notify.rs:352`; `subagent/notify.rs:573`;
  `spawn.rs:99`; `background_tasks.rs:1363,1443`; `helpers.rs:1126`; `quiet_delivery.rs:219`).
  The compile break is good — but each caller's outcome must be specified: a held row is
  **not** cleared and the sender is told "held", not "delivered".
- **Channel-inbound traffic does not pass the gate at all** — `handle_message` /
  `handle_reaction` enqueue turns directly (`handler.rs:1871`). If inbound is in scope, say so.
- **Gate placement vs the ownership redirect is unspecified** — the ownership gate is
  outermost and may redirect to a different session; state whether the check reads the
  original or the final target.
- **§10.1's field list omits `confirm` and `goal_max_turns`** (neither is a correlation field,
  so the substantive claim stands).
- **`oc-questions` has no in-repo write path** — `grep -rn 'oc-questions' src/ docs/` → no
  hits. It is upstream #547; the hook does not exist here yet.
- **The drain is un-re-anchored** — the owner's message starts a turn, and the drained batch
  lands at that turn's next tool-loop boundary with no link back to the pending question, so
  "previous work is just lost" is only half-fixed. Specify the drain to run **after** the
  answer turn, framed with a reference to the question.

---

## 6. What survives

- **The diagnosis is exact and non-obvious:** an awaiting-owner lane is *idle*, not mid-turn,
  so the #13 gate (`session_routes.rs:416`) never sees it. That is the real mechanism.
- **The state belongs on the durable binding record** (`await_kind/await_ref/await_at`,
  `session_binding.rs:71-83`); `owner_gate` is already a named kind (`await_external.rs:36`).
- **Parking in `notify_queue` rather than dropping** matches the existing durability posture
  (`notify_queue.rs:124-215`, 72 h reap with loud logs). Held ≠ lost is a real property.
- **§10.1's framing is sharp:** a peer wait's reply is an *ordinary push*, so origin-based
  bypass is wrong and a correlation token is required; the two failure classes (cycle,
  transitive block on the owner) are real.
- **The verification list (§7) is honest**, including the positive control — the same
  discipline this review applied to find the tautology.
- Substrate inventory otherwise accurate: `Delivery`'s five variants, `redeliver_persisted`,
  `notify_policy` modes + 1800 s cap, `turn_probe`, `PlanStatus` at `plan.rs:654`,
  `suggest_options` recording no state.

---

## 7. Net

The proposal's **problem statement, state model and best-practice survey stand**. Its
**mechanism does not**: §4.2–§4.4 are unimplementable against the current wire, and three
paths defeat the gate even if the wire is fixed. rev.3 must (i) gate on the resolved
`DeliveryMode`, at the **route layer**; (ii) give the state one writer and a no-wake reader
branch; (iii) clear on the **correlated** signal, from one hook covering text + callback +
reaction; (iv) drop auto-set on `suggest_options`; (v) add a request-side correlation field
and store the peer's session id. Then it is buildable.

Nothing here is implemented; the design gate (AGENTS.md rule 10) stands — owner approval
first. Harness changes belong in a fork issue on `leshchenko1979/opencrabs`; this factory's
half is the lane-side law.
