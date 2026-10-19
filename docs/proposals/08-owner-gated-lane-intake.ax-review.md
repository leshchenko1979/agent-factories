# AX review — PROP-08 rev.12 (calling-agent usability)

**Reviewer:** sub-agent `8bc3fd49` (read-only) · **Date:** 2026-10-05
**Verified against:** `/root/opencrabs/src` at HEAD per doc `717dfcd90`. All proposed names return 0 hits (design, not code).
**Scope:** agent discoverability / callability / parseability / recoverability of the surfaces the design adds.

---

## BLOCKER

**B1 — The held outcome has no verdict string on any surface.**
`Delivery::HeldForOwner { since }` is added (`session_routes.rs:319-339`), but the three consumers never learn a `notify_state` for it. The tool's vocabulary is `delivered|queued|refused|redirected` (`subagent/notify.rs:574-760`); A2A's is `delivered|parked|deferred|refused_in_flight|no_route` (`a2a/handler/notify.rs:353-437`); the CLI maps outcome→exit at `cli/session_notify.rs:311-315`. §4.7 gives only a *log* line (`HELD: awaiting owner since <ts>`), not the returned state. An agent cannot branch on "held".
*Fix:* name it (e.g. `notify_state="held"` + `held_since` metadata), and add `held` to the CLI OK set at `cli/session_notify.rs:312` (or a dedicated exit code).

**B2 — `session/held` / `session held` / `session_notify action="list"` have no specified return shape.**
§4.5 names three read surfaces and specifies none: the tool result metadata, the A2A result body, and the CLI `--json` object are all unstated (only prose "sender · instant · first line"; `--full` "returns the rows verbatim" without naming fields). The row is `id, session_id, context_text, display_text, origin, bg_meta, created_at` (`notify_queue.rs:24-32`).
*Fix:* give the exact JSON shape per surface, and say whether `action="list"` returns index or full rows.

**B3 — `graph` has no machine-readable shape.**
§4.2/E.2 show ASCII (`A --peer_lane--> B`, `ROOT: (owner)`, "broken edge") and name nodes/edges/roots, but no JSON object for the tool's `graph` result, the A2A `session/await/graph` result, or `session await graph --json`. `await_external.rs:100-160` currently has no such schema.
*Fix:* pin a shape, e.g. `{nodes:[{session,kind,target,root,broken}], cycles:[[...]]}`.

**B4 — The new A2A methods don't exist and their params are unspecified.**
`dispatch.rs:20-49` has only `message/send`, `session/notify`, `session/notify-status`, `tasks/get`, `tasks/cancel`. `session/await`, `session/await/graph`, `session/held` are new with no param schema; the set/clear discriminator is unnamed; and E.3 uses key `session` where the sibling method uses `session_id` (`a2a/handler/notify.rs:63`). An agent guessing `session_id` (correct for `session/notify`) fails on `session/await`.
*Fix:* full JSON-RPC param schema per method, and align the key name with `session/notify`.

**B5 — The `key` param and its claimed verdict are wrong/unnamed.**
§4.6 says the send returns `queued` or `injected`. `injected` is only a *receipt* state read by `status` (`notify_receipts.rs:20-30,131-135`), never a send-path return; the send vocabulary is `delivered|queued|refused|redirected` (tool) / `delivered|parked|deferred|refused_in_flight|no_route` (A2A) — a send cannot know "injected" synchronously. The `key` param is named on the tool only; A2A param and CLI flag are unstated.
*Fix:* name the keyed-supersede verdict (e.g. `queued`/`superseded`), and give `key` on all three surfaces + CLI.

## MAJOR

**M1 — `session_notify action="list"` is unavailable exactly where the design needs it.**
The tool is registered only `if !headless` (`cli/tool_setup.rs:193-199`) and `execute` hard-errors headless *before* action dispatch (`subagent/notify.rs:204-210`). Cron/sub-agent/one-shot lanes — the parked-lane population — cannot pull held rows through the tool.
*Fix:* expose a read-only list path headless, or name the A2A/CLI route as the headless read and drop the tool claim.

**M2 — `await_external graph` schema and the new `target` contract are unspecified.**
Is `target` required for `peer_lane`? What is returned when `target` names no binding (root vs error) or is omitted? §4.2 says peer_lane target is "validated to exist" but never gives the failure output. `await_external.rs:100-160` has no such schema.
*Fix:* per-action param schema, `target` required-ness by kind, and the error text for invalid/dangling targets.

**M3 — The correlation field has two names and no surface binding.**
§10.4: "Add a request-side `request_id` / `correlation_id`"; E.11 uses `--request-id`. No A2A param name, no tool param name, no CLI flag is fixed. Grep confirms no such field exists today (`a2a/handler/notify.rs:63-144`).
*Fix:* pick one name, list it as a param on all three surfaces.

**M4 — Discovery gap: schemas/enums/help are not updated in the plan.**
Agents discover actions via `input_schema().enum` — `await_external` is `["set","clear"]` (`await_external.rs:151`), `session_notify` is `["send","status"]` (`subagent/notify.rs:151`). §5 lists the tool changes but never the enum/description updates; without them `graph` and `list` are undiscoverable.
*Fix:* add the new enum members + description text to §5 explicitly.

**M5 — `target_session` is `required` before action dispatch.**
`subagent/notify.rs:203` (`"required": ["target_session"]`) and the parse at `:221-233` run before the action match at `:238-248`, so `action="list"` would demand a target session (and `status` already does despite using only `notify_id`).
*Fix:* state the `list` param contract and relax `required` accordingly.

## MINOR

- **m1 — Field-name drift.** DB column `await_target` vs param `target` vs E.1's `target=null`; `await_prompt` vs `--prompt`. Name both as (column, param) pairs.
- **m2 — `HeldForOwner { since }` type/units unstated** (unix secs, cf. `await_at`, `session_binding.rs:75-77`).
- **m3 — `graph --session` omission semantics** (whole graph?) unspecified.
- **m4 — `--json` vs default text.** `session await graph` and `session held` offer both; say `--json` is the machine path (prose default is unparseable).
- **m5 — Digest template undefined.** "question first" and "sender · instant · first line" are prose; the losslessness test (§7) counts lines but not how "the question" is identified.
- **m6 — Column list incomplete.** §5 lists only `push_sender`; §4.6 also needs `key` on `notify_queue` (and `record()` at `notify_queue.rs:69-95` takes neither). State all new columns.
- **m7 — Held-push receipt linkage unstated.** `record_queued` fires on `Delivered`/`Parked`/`Redirected` (`a2a/handler/notify.rs:355,377,409`); the new `HeldForOwner` arm must decide whether a held push gets a receipt, or `--status` on it returns `unknown_id`.
- **m8 — Tool vs CLI syntax conflated.** §4.2 writes tool calls as `--kind/--target` (CLI convention); tool calls are JSON keys. Cosmetic but a real source of agent error.

---

**Verdict: not ready for an agent to implement** — the gate's held verdict (B1) and all three new read surfaces (B2, B3, B4) have no specified return shapes or param names, so an implementing agent would have to invent the public interface the design claims to fix.
