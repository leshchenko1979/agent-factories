# ai-antispam — `instruments.review-rotation` declaration (DRAFT)

**Status: DRAFT, and it lands nowhere until ai-antispam HQ says so.** A per-instrument
declaration is factory data — it lives in `registry/factories/<slug>.json`, the fragment that
describes the factory — so it is ai-antispam HQ's to write. This lane owns the *instrument*, not
the member, so it drafts the text and the measurement behind it and stops there (meta-factory
SKILL §3, the hard boundary).

**The surface.** `instruments.review-rotation`, an entry beside `pacemaker`, `ledger` and
`open-questions` in the fragment. Its contract is the frame's, read here from
`docs/instruments/review-rotation.md` §9: `state` (`adopted` | `partial` | `deferred` |
`not-applicable`) beside `green`, `behind_by`, `reason` and `measured_at`; `reason` required for
`deferred` and `not-applicable`; `adopted` additionally requires `green: true`; an ABSENT key is
legal, which is the state this draft exists to cure.

## Why a declaration is owed

The instrument's own adoption census reads this member **HELD-UNDECLARED** — it holds the whole
declared set (5/5) with no disposition on the surface, the one non-source member in that state
(`evidence/instrument-census-review-rotation-2026-10-04.md`, re-run this turn). The instrument's
**O1 migration duty** then binds: a member holding a divergent copy of one of §2's five paths
disposes of it — migrate, declare the fork with its reason, or defer with a re-entry condition —
and silence is not a disposition. The member's copy is divergent (below), so the disposition is
owed, and deferral is the one this draft proposes.

## The readings — each with its predicate, scope and instant

Read at **2026-10-04T21:06Z**; canonical is the committed standard `origin/main` = `29b7d55`.

| # | predicate | scope | reading |
|---|---|---|---|
| 1 | presence — `os.path.isfile(member.repo / p)` | the 5 §2 paths; `registry/factories/*.json` | **5/5 held**, reload link absent, fragment declares nothing → **HELD-UNDECLARED** |
| 2 | byte-identity — sha256 of each §2 path in the member's tree vs `git show origin/main:<path>` | same 5 paths | **1 identical, 4 divergent, 0 absent** |
| 3 | declared forks — `registry/kit-exemptions.json` | the 4 divergent paths | **0** → all 4 are UNDECLARED divergence |
| 4 | byte-identity against the member's OWN pin — `registry/kit.json` (`kit_version 27b79f289fef`) | same 5 paths | **5/5 identical** → the member's own pin gate is silent |

Rows 2 and 4 answer different questions and both are true: the member is **internally
consistent** (it holds exactly what it vendored) and **behind canonical** (canonical moved on
after the vendoring). Row 2's four divergent paths are the pre-extension-surface revision: three
are byte-identical to `f54cdea^` (the commit before the extension surface landed, 2026-10-03) and
`docs/instruments/review-rotation.md` is byte-identical to canonical `5b2fe9f` (2026-09-28). The
member's last kit re-vendor is `333ee0b` (2026-09-29), so its whole set is the 2026-09-29
revision; `tools/review.py`, `tests/test_review.py` and `docs/review-lenses.md` gained the
declared extension surface at `f54cdea` and the member has not re-vendored since. The member's
`reviews/` holds **0 cycles** — the instrument has never been run there — and the extension
surface `docs/review-lenses.json` is **absent**, which is the correct default rather than a gap
(instrument law §6: absent is the declared default state).

**`behind_by` has no definition beyond "integer" (frame §7.2), so both halves are stated**: the
count of divergent paths is **4** (row 2), and the count of *declared* forks among them is **0**
(row 3), so undeclared divergence — the figure O1 reds on — is **4**. The reading against the
member's own pin (row 4) is **0**, and that is why the member's own audit is silent while the
fleet-level lag is four paths.

## The proposed entry

```json
"review-rotation": {
  "state": "deferred",
  "behind_by": 4,
  "measured_at": "2026-10-04T21:06Z",
  "reason": "O1 disposition: DEFER with a re-entry condition. HELD 5/5 (presence, instrument census, 2026-10-04T21:06Z) with no declared leg — the member's copy is the pre-extension-surface revision, so 4 of the 5 paths diverge from canonical and none is a declared fork. PREDICATE: sha256 of each docs/instruments/review-rotation.md section-2 path against git show origin/main:<path> at the committed standard 29b7d55. SCOPE: the 5 declared paths. CLASSIFICATION: 4 divergent (tools/review.py, tests/test_review.py, docs/review-lenses.md, docs/instruments/review-rotation.md), 1 identical (docs/review-cycle.schema.json), 0 absent, 0 declared in registry/kit-exemptions.json — undeclared divergence = 4, the behind_by figure. The 4 predate the declared extension surface (f54cdea, 2026-10-03): three are byte-identical to f54cdea^, the law doc to canonical 5b2fe9f (2026-09-28). SECOND READING, stated because behind_by is validated only as an integer: against this member's OWN pin (registry/kit.json kit_version 27b79f289fef) the tree is byte-identical on all 5, so the member's own pin gate is silent — 4 is fleet-level lag, not internal drift. GREEN omitted, not false: the member's gate was not run, and its tests/test_review.py predates the #293 JANITOR, so a run in the tracked reviews/ is unsafe (it would leak test cycle dirs). RE-ENTRY CONDITION: a re-vendor to the canonical pin brings the 4 paths to byte-identity, and a green run of tests/test_review.py over the set moves this entry to state adopted, green true, behind_by 0."
}
```

**Why `deferred` and not the other three.** `adopted` is false twice over: the set is not held
*at canonical* and no gate has been shown green, and the state requires `green: true`. `partial`
is the census's *some-paths-held* reading, and this member holds all five. `not-applicable` would
claim the instrument cannot apply here, which the 5/5 holding contradicts. The frame prescribes
the fourth state for exactly this shape — a member behind on an instrument states it as a
declaration, "behind by N, deferred because X" — and deferral is not drift, which is why the
cure is this entry rather than a red gate.

## What moves the entry to `adopted`

1. **Re-vendor to the canonical pin.** The four divergent paths return to byte-identity, so
   `behind_by` reads 0. The install travels `registry/kit.json` (manifest grain), never a
   per-member dispatch (instrument law §8).
2. **Run `tests/test_review.py` green over the set** — after the re-vendor, because the current
   copy predates the JANITOR (#293) and a run in the tracked `reviews/` would leak test cycle
   dirs on a killed run.
3. **Then** `state: adopted`, `green: true`, `behind_by: 0`.

Nothing else is a prerequisite: the instrument's closure is declared EMPTY (stdlib-only
executable), so a re-vendored member has a runnable instrument with no sibling to miss.

## Two choices ai-antispam HQ owns (the draft takes a position; either is lawful)

1. **The `behind_by` axis.** This draft reads it against **canonical** (4) because that is the
   figure that tells the fleet how far the member's instrument is from the one of record. The
   instrument's **O3 pin duty** points the other way for the member's own *gate* — it reds on
   divergence from the member's own pin, never the meta-factory's live manifest — and against
   that pin the member is 0. Both predicates are in the entry; HQ picks which the number names.
2. **`green`.** Left omitted (UNMEASURED). `false` would claim a red nobody measured; `true`
   would claim a pass nobody ran. If HQ runs the gate in a copy that does not touch the tracked
   `reviews/`, the field becomes `true` and the state can move.

## What this draft does not do

- It does **not** edit `registry/factories/ai-antispam.json` — factory data, HQ's surface.
- It does **not** re-vendor `/root/ai-antispam` or run its gate in place — the member's work, and
  the in-place run is unsafe while its gate copy predates the JANITOR.
- It does **not** touch **O4's** `intake.json` duty, which is per-cycle and owed only once a
  cycle runs; the member has 0 cycles. O1 and O4 are separate duties and only O1 is in scope here.
- It is **not** an adoption *recommendation*. Whether ai-antispam adopts this instrument is HQ's
  decision; this draft only records the disposition O1 requires of the copy the member already
  holds.

*Drafted by the instrument's authoring lane (session `d6cfd3f7`), 2026-10-04T21:06Z, at the
request of the owner. Measurement artifact: `evidence/instrument-census-review-rotation-2026-10-04.md`.*
