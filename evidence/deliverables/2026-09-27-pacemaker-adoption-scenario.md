# Pacemaker — the adoption scenario, completed end-to-end

**Owns:** the pacemaker instrument's adoption RECEIPT: the delivery rehearsed against a real
member's committed bytes, the instrument's own gate green in that member's tree, and the two
defects the rehearsal found in the gate itself. Cites the frame (`docs/instruments/template-instruments.md`)
and coins no cross-instrument definition. The law is `docs/instruments/pacemaker.md`.

## 1. The scenario

**Predicate:** a member carrying a vendored pin (`registry/kit.json`), because the instrument's
own runner refuses to start without one (the kit-drift leg's `registry/fleet.json` is a hard
prerequisite — `registry.load_fleet_manifest()` raises before the `legs = [...]` list is built).

**Member: ai-antispam** — its committed set is complete as of `82d233a` (2026-09-27T16:00:56Z),
which is the state rehearsed here.

**Method (borrowed from the review-rotation pilot, `evidence/deliverables/2026-09-27-review-rotation-adoption-pilot.md`):**
the member's COMMITTED state is materialized read-only and the shipped pair is laid over it, so
the member's live tree is never touched.

```
git -C /root/ai-antispam archive HEAD | tar -x -C /tmp/pm-pilot3
cp <donor>/TEMPLATE/tools/patrol_host_state.py <pilot>/tools/
cp <donor>/TEMPLATE/tests/test_patrol_host_state.py <pilot>/tests/
```

**Scope limit, stated:** the base is the member's committed state, so its untracked files are not
in it. That is the right base for judging a delivery and it is stated rather than left implicit.

## 2. The receipts

| leg | reading | predicate | instant |
|---|---|---|---|
| declared set present in the member's committed state | 4 / 5 | `ls` each of the five paths | 2026-09-27T17:0xZ |
| the held path | `tests/test_patrol_host_state.py` absent by DECISION | member declared it held, not shipped red | — |
| **the instrument's own gate, in the member's tree** | **`patrol-runner gate passed: 102 check(s)`, rc=0** | `python3 tests/test_patrol_host_state.py` | 2026-09-27T17:2xZ |
| the same gate in the donor tree | rc=0 — 101 check(s), 1 SKIPPED | same, `TEMPLATE/` half | same |
| the same gate in the kit's own tree | rc=0 — 102 check(s) | same, root half | same |
| drift, before the fix | **8 failed of 102**, then 3, then 0 | same command | 17:13Z → 17:2xZ |

## 3. The two defects the rehearsal found — both in the gate, not in the member

The gate ships as a byte-identical pair, and in the half that ships **"this factory" is the
ADOPTING MEMBER**, whose instants are its own. Two things were pinned to the kit's literals
instead:

1. **A dependency `_run` never injected.** The probe driver injected the board, the rows, the
   cron table, the log surface and the publish leg — every dependency except the kit-drift leg's
   two manifests, which `main()` has always accepted as parameters. In a tree that carries no pin
   (the donor half, which by design ships only `kit.example.json`) **every** probe driven through
   `_run` read red for the kit leg's reason: measured 14 failed of 102, and exactly 13 of them
   cleared the moment a manifest pair was supplied. The probes about the board, the cron leg and
   the duty leg were measuring the kit leg.

2. **Fixture data pinned to the kit's instants.** The duty and board fixtures carried the kit's
   own boundary (`2026-09-25T07:01:07Z`), its round date and its close-board anchor
   (`2026-09-18T18:04:24Z`) as literals, while the leg correctly reads the TREE's declaration.
   A member declaring its own boundary therefore saw probes fail for asserting the kit — and two
   of the eight read as *"a missing duty receipt never reached the report"* when the member's cron
   row had simply fired before its own declared bound and been **correctly EXCUSED** by the leg.

Both are the same class the instrument exists to kill, turned on the instrument's own probes: an
assertion that reports a verdict about something other than the thing under test.

## 4. The fix, and what was deliberately NOT changed

Instants are now derived from the tree's own declaration and the gate's own anchor, read through
the same readers the legs use, with the kit's literals kept only as pre-adoption fallbacks. The
probe that asserts the leg binds to the GATE's constant keeps its real content — it must reach the
gate's constant, not a private copy — and no longer asserts that the anchor equals the kit's date,
because a member carrying its own is the entire point of the `standalone` class. The **token**
stays asserted: the token is the convention; the anchor is the tree's data.

## 5. What the fix does NOT claim

- The member's `tests/test_patrol_host_state.py` **remains held**. It is byte-identical to the
  donor and now passes there, but committing it is the member's call and was not taken here.
- `registry/factories/` (the fragment store) is still absent in the member's tree; the duty leg
  reports that honestly rather than passing over it.
- The pytest form of the gate in the member's tree is blocked by their own conftest requiring
  `BOT_TOKEN` — a pre-existing condition of their tree, unrelated to this gate, and recorded
  rather than worked around.
