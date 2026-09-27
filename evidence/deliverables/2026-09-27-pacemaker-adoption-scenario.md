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

---

## 6. The declaration leg — the one stage no lane but the member's can supply

Added 2026-09-27T17:5xZ. §1–§5 close the ADOPTION *scenario* in a member's tree; this section
records the stage after it, where the fleet's census reads the result.

### 6.1 What was wrong, and how it was found

The census (`tools/instrument_census.py`, 17:10:24Z) requires **two legs** for `ADOPTED`: the
declared set complete, AND the instrument's own declaration behind it. On its first run it
reported the declared leg as `unestablished` for **every** member — as a *schema fact*, and it
said so: no per-instrument declaration surface existed.

That was true when written and false 19 minutes later: `tools/registry.py` (17:29:36Z, HQ
`bee6353`) added `instruments.<slug>`. Two halves of one law landed out of step, and nobody
noticed until the census was run against a law doc that finally parsed.

**Same class as the rest of this instrument: a reader that predates its surface reads clean over
it.** The census's own docstring asked for the field ("HQ's schema to extend"); HQ extended it;
the reader was not updated. Measured consequence: **no member could reach `ADOPTED` whatever it
declared**, so the fleet's adoption tracker could report no adoption at all, for any instrument.

The reader was extended by the tool's owning lane (`84a94ba`) and carries a gate of its own:
`tests/test_instrument_census.py`, **10 arms, rc=0**, including the non-vacuity arm that reads
`ADOPTED` over a complete set — the path no member had walked.

### 6.2 The rehearsal — the live member is one declaration away

Run against `infra-factory`'s **real** tree (`/root/vds-servers`), with the declaration supplied
in a **temporary fragment store**: no live store and no member tree was written.

    infra-factory    held=9/9  declares=adopted · green=true   -> ADOPTED

So the pipe is proven end to end over live fleet data, and the only missing input is the member's
own measurement. That is not a technical gap — the frame is explicit that the fragment is
"written by THAT factory's HQ and by nobody else", so neither the instrument owner nor the scribe
can supply it.

### 6.3 Live state at the reading

`tools/instrument_census.py`, artifact `evidence/instrument-census-pacemaker-2026-09-27.md`,
instant **2026-09-27T17:48:33Z**:

| member | held | fragment declares | status |
|---|---|---|---|
| `ai-antispam` | 9/9 | unestablished | HELD-UNDECLARED |
| `inferhub-watch` | 9/9 | unestablished | HELD-UNDECLARED |
| `infra-factory` | 9/9 | unestablished | HELD-UNDECLARED |
| `meta-factory` | 9/9 | — | SOURCE |
| `miidas` | 1/9 | unestablished | PARTIAL-UNDECLARED |
| `opencrabs-dev` | 0/9 | unestablished | ABSENT |

**All three holders are `HELD-UNDECLARED`, and that is the correct reading, not a failure** —
it is frame §7.2's silence rendered as silence. The declaration is each member's own act.

### 6.4 The declaration shape, verified against the registry's own validator

    "instruments": {"pacemaker": {"state": "adopted", "green": true, "measured_at": "<instant>"}}

- valid shape → `python3 tools/registry.py validate <fragment>` **rc=0**
- `green` omitted → **rc=1**, refusal: *"instruments.pacemaker.state `adopted` requires `green:
  true` — HELD and GREEN are independent (frame 7.2)…"*
- live store, 17:5xZ → rc=0, 7 fragments valid, **zero carrying `instruments`**

### 6.5 Dispatched, and what it awaits

- `infra-factory HQ` — asked to declare, with the shape above and the validator receipts, and
  with the honest caveat attached: its tree is 6/9 **current**, three files being pre-fix
  revisions, so it was asked to re-copy and re-measure before declaring rather than to adopt on
  a stale green.
- `Delegate` (topic 68) — the lane that commits fragments from member declarations; told the
  field exists and is readable, with the same receipts. Not asked to declare on anyone's behalf:
  a scribe cannot supply a measurement it did not take.

**Re-entry, stated so this is not silence:** the pacemaker's first live `ADOPTED` row appears the
moment one holder replies with `state: adopted` + its own `green`. Everything already exists to
render it; §6.2 is the receipt that it will.

---

## 7. The closure warning, proven at CI level — "green locally, red in a fresh clone"

Added 2026-09-27T17:5xZ. §3 of `docs/instruments/pacemaker.md` warns that the closure must travel
with the pair. Until now the evidence was a crash in a **constructed** partial copy. A member's own
CI produced the same failure on real work, and it is a sharper specimen because of *when* it shows.

**The mechanism, read from the runner's own constants.** `patrol_host_state.py` loads its
dependencies by path, not by import:

| constant | line | loaded by |
|---|---|---|
| `REGISTRY = REPO / "tools" / "registry.py"` | `:198` | `load_module("oc_registry", REGISTRY)` at `:594`, `:612`, `:751` |
| `LEDGER_BOUNDARY` | — | `load_module("ledger_boundary", …)` at `:1188` |
| `KIT_PIN` | — | `load_module("kit_pin", …)` at `:1530` |
| `PREDICATE` / `CLOSE_BOARD_GATE` | `:131`, `:189` | the board legs |

`load_module` raises when the path is absent, and those calls build the `legs = [...]` list — so an
absent closure is a crash, and the crash happens **while the list is being built**, before any leg
runs. That is §3's loud tier, confirmed at four call sites rather than one.

**The specimen.** In `inferhub-watch`'s tree, measured 2026-09-27T17:53Z: the patrol gate and runner
were **tracked**, while `tools/registry.py` was **present but UNTRACKED** (`git ls-files
--error-unmatch` → not tracked; the file is on disk). Local runs pass, because the loader reads the
working tree. A fresh CI clone has no `registry.py`, so `:594` raises and the gate fails **there and
only there**.

**Why this is a new class rather than a restatement.** A partial copy fails everywhere, and a
missing gate fails nowhere. This specimen fails in exactly one place: **the tree that does not carry
the untracked file — which is every tree but the author's working copy.** The gate's own verdict
locally is "102 checks passed" and the commit does not carry the file its verdict depended on. It is
the examined-nothing class one level up: the gate examined something, but the *commit* cannot
reproduce the examination.

**The rule it implies**, and the reason it belongs beside §3 rather than in a footnote: *a member
adopting the pair must adopt the closure **in the same commit**, and "it passes in my tree" is not
evidence until the same command passes from a clone of the commit.* A green local run over a
present-but-untracked dependency is indistinguishable from a green local run over a tracked one —
the difference is invisible in every surface except a fresh checkout.

**Status: the member found it, not us, and repaired it by untracking the pair.** Recorded as
evidence about the *instrument's* adoption shape; the member's CI state is its own to settle, and
nothing here asks it to change course. The peer's report of the mechanism is confirmed first-hand
against the two files it named.
