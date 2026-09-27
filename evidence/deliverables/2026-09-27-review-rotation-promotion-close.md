# Review Rotation — the promotion close

**Owns:** the promotion's CLOSING RECORD — the commit order, every member disposition with its
owner, and the adversarial re-run's five checks with their receipts. The instrument's law is
`docs/instruments/review-rotation.md`; the frame is `docs/instruments/template-instruments.md`;
the decision record is `docs/projects/review-rotation.md`. This file cites the frame and coins
no cross-instrument definition (frame §8).

## 1. What was promoted, in one paragraph

opencrabs-dev's **Duty 4** (worker-input persistence and ledger intake) and **Duty 6** (periodic
multi-lens review) were embedded donor law: the template already shipped the review ENGINE
(`review.py`, a 14-lens/six-family catalogue, `docs/review-lenses.md`) while the donor held the
ORCHESTRATION — intake, the cadence boundary, step-0 recovery, the frozen cycle schema. The
promotion completed the template's half and reduced the donor's to a pointer. **The two duty
labels stay donor-role labels**; the instrument is **Review Rotation**.

## 2. AC1 — the commit order, verified against each commit's own tree

**Predicate:** for every commit carrying this session's `Session-Id`, compare `registry/kit.json`
at that commit against the blobs in that commit's tree. **Scope:** 18 commits, `47f6728`…
`e6fb4eb`. **Instant:** 2026-09-27 ~17:1xZ.

**Reading: 18 of 18 commits carry a manifest that agrees with their own tree** — i.e. every
commit is buildable and self-consistent, which is the property frame §7.3 exists to protect.

| # | commit | in dependency order |
|---|---|---|
| 1 | `47f6728` | frame: the slug surface + criteria 2/6 close artifacts |
| 2 | `54d6442` | donor contract inventoried clause by clause |
| 3 | `dada1a6` | the promoted contract and the state schema |
| 4 | `a5e2fe3` | the Duty-4 intake leg, as a declared surface |
| 5 | `fd738ab` | frame: O6, HELD/GREEN, a named declaration surface |
| 6 | `f68e1a0` | engine: step-0, the frozen ledger, one catalogue |
| 7 | `6209756` | the instrument's own law, its reload link, the version regress |
| 8 | `6bcec98` | the §8 review's three changes + the frame's §7.4 citation |
| 9 | `17cd0c8` | engine: the replay's three frictions |
| 10 | `f7ea24e` | evidence: the replay + its durable cycle report |
| 11 | `9bac2cb` | the donor-side transcription HQ lands |
| 12 | `1c64f9b` | the strip's AC2 baseline |
| 13 | `c533434` | evidence: the donor-side boundary + AC3's receipt |
| 14 | `794fafa` | evidence: the battery is FLAKY — three readings |
| 15 | `ad80b30` | the adoption census — one predicate, two legs |
| 16 | `2743224` | evidence: the adoption pilot |
| 17 | `4d67b2d` | engine: the donor's lens-KEY rename, mapped and named |
| 18 | `e6fb4eb` | the replay's verdict marked as a REPLAY |

**Ground-up shape:** law → inventory → contract → engine legs → law doc → migration → census →
pilot → fixes. Each commit is one change; the manifest moved with the bytes it describes.

## 3. AC2 — every open disposition, with its owner

**Predicate:** `tools/instrument_census.py review-rotation`, one row per registry factory, file
PRESENCE of the law doc's §2 declared set. **Instant:** 2026-09-27T17:14:21Z.

| member | held | reload link | disposition | **owner of the next action** |
|---|---|---|---|---|
| `ai-antispam` | 3/5 | absent | **PARTIAL-UNDECLARED** | **ai-antispam** — it holds a divergent copy, which is frame §9 O1's exact case: migrate, declare the fork with a reason, or defer with a re-entry condition |
| `inferhub-watch` | 0/5 | absent | ABSENT — **pilot rehearsed green** | **inferhub-watch** — adoption is its own act: port the set, write `intake.json` if its ledger is declared, create its reload link |
| `infra-factory` | 0/5 | absent | ABSENT | **infra-factory** — via `/root/vds-servers`, which is PULL-ONLY for this fleet, so the port is theirs |
| `miidas` | 0/5 | absent | ABSENT | **miidas** |
| `opencrabs-dev` (the donor) | 0/5 | absent | ABSENT — **its `hq.md` carve LANDED** | **OC DEV HQ** — the donor's adoption and reload link are the donor's own acts (frame §6.1) |
| `meta-factory` | 5/5 | resolves | **SOURCE** | — (the authoring tree; it holds the set by construction and is not an adopter) |

**Two dispositions are NOT any member's, and both are named so they are not read as omissions:**

| open item | owner | why it blocks |
|---|---|---|
| **a PER-INSTRUMENT declaration surface** | **HQ** | `registry/factories/<slug>.json` carries a `kit` field (the KIT's state, O6) and **no field for an instrument's disposition**. Until it exists, the census reports the declared leg `unestablished` for every member and **no member can lawfully reach ADOPTED**. Which key a member declares on is HQ's schema call; none is coined here |
| the flaky `oc-ledger --selftest` (three readings in one hour) | **Toolsmith** | reported this session; it is a property of ONE gate, so the methodology lane correctly declined to make it a frame clause |

**The port to the remaining members did NOT run**, and must not until the declaration surface
exists. Criterion 2's sequencing is satisfied: exactly one member was rehearsed, and it was green
before any other was touched.

## 4. AC3 — the adversarial re-run, five checks, each with a same-turn receipt

### (a) Duplicate duty law — **PASS**
**Predicate:** count of the contract's own vocabulary in each candidate home.
- The donor's Duty 4/Duty 6 regions: `oc-review-persist` **0**, `review-lenses.md` **0**,
  `Step-0` **0**, `duration_review_min` **0**, `duration_cycle_min` **0**, `cycle_id` **0**, and
  the regions shrank (Duty 4 → 26 lines, Duty 6 → 40 lines; file 333 → 267).
- The two residual hits are **naming**, not restatement: `:179` lists what MOVED, and `:207`
  names the enum inside the clause recording that the key-set-closure rule has no mechanical
  carrier and therefore STAYS.
- The reverse direction: the shipped law carries `30220` **0**, `OC_DEV_STATE` **0**,
  `oc-notify-fanout` **0**, `oc-review-persist` **0**, `/root/.opencrabs` **0**. Its single
  `session_notify` is inside §7's negative assertion ("the shipped file names no donor surface").

### (b) A stale donor pointer — **PASS**
**Predicate:** every repo-relative reference the shipped law doc makes must resolve.
**Reading:** 12 of 13 resolve directly; the 13th is `skills/grafana/`, which is the FRAME's
production example and lives in the ops profile, not this repo — verified present
(`~/.opencrabs/profiles/ops/skills/grafana/sql-examples.md`, a symlink to `vds-servers`, resolves).
The donor's own pointer names `docs/instruments/review-rotation.md` and says it is "NOT resolvable
from this skill tree" — which is true and is the point of a `[LANE]` pointer.

### (c) A manifest/index mismatch — **PASS**
**Predicate:** `kit_manifest.py --check` at the tip, plus the per-commit comparison of §2.
**Reading:** tip **135 files, 0 mismatched, 0 absent**, `kit_version ab24bc048891`; **18/18** at
the commits.

### (d) A missing member reload link — **PASS (named, not silently absent)**
**Predicate:** `<member skill dir>/review-rotation.md`, per member.
**Reading:** `meta-factory` **resolves**; the other five **absent** — reported per member by the
census, and `absent` is a DECLARED STATE (frame §6.1), not a failure. The link is the member's
own act and is never installed from here; a law doc with no link is perfectly readable, merely
not re-injected after compaction.

### (e) A cycle that only looks complete because a lens was skipped — **PASS**
**Predicate:** `review.py verify` over a cycle built with the engine's OWN commands
(`init` → `record` × 13 → `waive`), then mutated. **Scope:** cycle `rr-skip-probe`, 14 catalog
lenses. **Instant:** 2026-09-27 ~17:1xZ.

| variant | rc | verdict |
|---|---|---|
| 13 recorded + **one lens WAIVED with a reason** | **0** | `PASS: census verified clean across all 14 lenses` — **non-vacuity: the gate CAN pass** |
| the same cycle, the waiver's **reason emptied** | 1 | `Missing or incomplete lenses: S (waived with no reason)` |
| the lens flipped to **PENDING** (the skip hidden as unfinished) | 1 | `Missing or incomplete lenses: S (PENDING)` |

**The first row is what makes the other two mean anything.** And the live corroboration is the
replay of the donor's own `20260925-c24`: its `verify` returned rc=1 naming four PENDING lenses,
so a record that looks finished does not pass by looking finished.

## 5. The post-promotion review — what this promotion taught, and one thing it got right by accident

**The replay found what the review could not, and it is now frame law.** Reading the engine's
code missed three defects that running donor data through it found immediately: a render that
crashed on a migrated record, a terminal value left unrecognised, and — found by the methodology
lane's §5.4 verification and then reproduced here — a lens-entry **KEY RENAME** that my own fix
did not survive. The last one was the sharpest: the migration's key filter DROPPED eleven donor
lens report paths in silence, and the render printed `None` for a lens that has a report. **A
replay over the donor's data is a different instrument from a review of its code**, and frame
§5.4 now says so.

**One check was mis-scoped and is corrected here rather than quietly dropped.** Check (b)'s first
pass treated `skills/grafana/` as a repo-relative reference and read it as a miss; the frame cites
it as a production example in ANOTHER tree. The predicate was too narrow, not the pointer stale —
the same one-scope-two-populations class this fleet files most often.

**And one honest boundary:** `oc-ledger --selftest` reads live roster state, so the donor's gate
result depends on how busy the box is (281/2 PASS-fail-FAIL at 16:22, 283/0 at 16:56, 282/1 at
17:01). A lone green there is not a measurement, which is why three readings are published and
the finding is the Toolsmith's rather than folded into a pass.
