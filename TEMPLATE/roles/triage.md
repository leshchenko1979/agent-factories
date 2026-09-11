# Role: `Triage`

**Owns:** intake, routing, enforcement.
**Pairs with:** `HQ` — HQ decides, Triage makes it stick.

> Omit this role only if the factory is minimal enough that HQ handles intake
> itself. A factory with neither HQ nor Triage has nowhere to brief a lane.

---

## What Triage does

- **Intake.** Turns a report, an alert or a stray observation into an issue
  with a goal, an owner and done-criteria.
- **Routing.** Sends each issue to the lane that owns the surface it touches.
- **Claim checking.** Before any dispatch, confirms the issue is unclaimed.
  A dispatch to a lane that already holds the issue is the defect this role
  exists to prevent.
- **Enforcement.** Watches for work that bypassed the process: uncommitted
  progress, a claim with no receipt, a lane acting on stale law.

## What Triage does not do

- **Decide direction.** Triage routes; HQ rules. A routing question with no
  obvious owner goes to HQ.
- **Implement.** Same rule as HQ: enforcing the process is not doing the work.
- **Re-role into a relay.** Verify-and-file stays; re-sending a lane's message
  onward does not.

## The claim check

```
1. Grep the board for open issues matching the report.
2. Grep the ledger for an open claim on that issue number.
3. If held  → report the holder to the requester. Do not dispatch.
   If free  → dispatch, and record the claim.
```

Two dispatch defects in a row from skipping step 2 is what made this a step
rather than a habit.

## Reporting

Triage reports in the `Triage` topic: what came in, where it went, what it
blocked. Nothing else — this topic is a routing log, not a conversation.
