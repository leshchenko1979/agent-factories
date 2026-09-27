# The review-rotation instrument

**Owns:** this instrument's own law — its declared file set, its closure, its gate set, its data
surfaces, its version source and its adoption census. It owns **no** cross-instrument definition;
those live in the frame it cites.
**Writer:** the Review Rotation lane. **Reviewer:** the Instruments-methodology lane — the frame's
own law makes review of a per-instrument file a **requirement, not a courtesy** (frame §8).
**Authority:** **HQ retains cross-factory authority.** Any clause in this file that binds a member
factory is HQ's, and so is the process law *about* instruments; both are cited here, never coined.
**Does not own, by role:** cross-instrument definitions (the frame, §8); the instantiation of a
meta-factory part into a new instrument (the Fleet instruments lane); and any clause binding a member
factory (HQ, §8). This lane owns **one** instrument end to end — its law, its enforcement, and its
member adoption.

**This file cites `template-instruments.md`, the frame, and never restates it** — restating is how one
definition becomes two, and two definitions drift. Parts 4, 7, 8 and 9 are cross-instrument by
construction: the frame defines them **once, precisely so an instrument owner does not coin their
own.** This file therefore supplies only what is true of THIS instrument:

| part | defined by | what this file supplies |
|---|---|---|
| **4** — version identifier | frame §7.1 | the declared file set the identifier is read over (§2, §5) |
| **7** — data surfaces | frame §2 | which surfaces ship as `.example` and which the factory owns (§6) |
| **8** — self-probe | frame §2 | the named probes that make this instrument's gate actually BITE (§7) |
| **9** — update path | frame §7.2 and §6.1 | the member's adoption steps for THIS instrument (§8) |

## 1. What the review-rotation instrument is

**Its job, in one sentence: a factory runs its periodic multi-lens quality review from declared
inputs, with every lens either run or explicitly waived, and with state on disk that a compacted
session can recover from without re-reading anything live.**

The instrument is the promotion of two duties that grew inside one factory's process law —
openCrabs-dev's **Duty 4** (worker-input persistence and ledger intake) and **Duty 6** (periodic
multi-lens review). Those are **donor role labels only**; they name the duties this instrument
carries and are not names of the instrument, its files or its concepts (frame §4).

The lifecycle is one object with an explicit terminal state, and the whole point is that **no state
in it is a silent pass**:

```
   init ──▶ brief ──▶ record ──▶ verify ──▶ compile ──▶ close
    │         │          │          │           │          │
  state   adversarial  receipt   census     verdict    FREEZE +
  v1      sub-agent    + sha256  check      skeleton   input snapshot
          prompt                                                   
   └── intake (declared channels) ──── step0 (recovery, state alone)
```

**Three design commitments, each tracing to a defect this promotion exists to close:**

- **Nothing declared is never read as nothing submitted.** Intake names three separate states —
  REFUSED (no declaration), EMPTY (zero submissions) and INCOMPLETE (a malformed one) — and **none
  of the three is a pass** (§4).
- **A claim in a docstring is not a mechanism.** The engine's module docstring claimed for two steps
  that `state.json` IS the step-0 recovery point while the source carried **zero** hits for `step0`.
  A compacted session cannot execute a paragraph, so the claim is now a command that reads state and
  nothing else (§4, §7).
- **A closed cycle's inputs are historical.** Both intake channels are live and mutable, so reading
  one against a finished cycle answers a different question than the one the cycle closed on. A
  terminal lifecycle FREEZES the cycle and snapshots its declared channels; a later live read is
  REFUSED unless the reader says `--live` and the read says so on stderr (§6).

## 2. The declared file set

**Predicate:** the shipped paths the manifest classifies `standalone` that carry this instrument.
**Scope:** `registry/kit.json` at the instant named in §5. Both halves are listed because the pair is
what a member adopts; the manifest hashes the `TEMPLATE/` half (§5).

| # | path (root half ↔ TEMPLATE half) | class | what it is |
|---|---|---|---|
| 1 | `tools/review.py` ↔ `TEMPLATE/tools/review.py` | `standalone` | **the executable** — every leg of the lifecycle |
| 2 | `tests/test_review.py` ↔ `TEMPLATE/tests/test_review.py` | `standalone` | **the gate** — 17 tests, each named for the behaviour it pins |
| 3 | `docs/review-cycle.schema.json` ↔ `TEMPLATE/docs/review-cycle.schema.json` | `standalone` | the state schema, **emitted** by `review.py schema`, never hand-kept |
| 4 | `docs/review-lenses.md` ↔ `TEMPLATE/docs/review-lenses.md` | `standalone` | the lens catalogue law and the Adversarial Isolation Requirement |
| 5 | `docs/instruments/review-rotation.md` ↔ `TEMPLATE/docs/instruments/review-rotation.md` | `standalone` | this file |

**A reader holding the law file and the tree can answer *"is this instrument complete here?"* without
enumerating imports**, which is what frame §1 requires of a declaration.

## 3. The closure — declared, and it is EMPTY

**Frame §1.1 is the load-bearing half and is cited, not restated: completeness is DECLARED, never
derived**, because a static import walk is blind to a dependency loaded from a string constant and a
gate can be green over a missing closure.

**This instrument's closure is empty, and that is a declaration rather than an omission.** Measured
this turn over the executable at its source:

- `tools/review.py` imports **only stdlib** — `argparse`, `datetime`, `hashlib`, `json`, `os`, `re`,
  `sys`, `pathlib`, `typing` — and carries **no local-module import at all** (0 hits for
  `^import tools`, `^from tools`, `importlib`, `__import__`).
- It therefore has **no HARD tier and no LAZY tier**: frame §1.2's silent tier cannot exist where
  there is no second module to fail to import.

**The consequence is stated because it is the one a member must not get wrong:** this instrument
cannot be broken at import by a missing sibling, so **the `#137` class (ported without its closure)
is not available here**. A member that adopts the declared set and nothing else has a runnable
executable. That is rare on this fleet — the frame measured `tools/ledger.py` at **27.7 %** of what
it needs — and a reader should not assume it of an instrument whose closure is declared empty.

**Declared empty, and re-measured rather than assumed, is the point.** A closure that is empty by
measurement and a closure nobody checked look identical in prose, so the measurement is stated with
its predicate. If a future leg adds a local import, this section is where it is declared.

## 4. The gate set and its registry entries

**The instrument's gate is part 2 of §2** — `tests/test_review.py`, byte-paired with its `TEMPLATE/`
copy. It is a **raw gate and NOT a registered gate** in the kit's own registry, which is why its
registration is stated as an absence rather than invented.

Measured this turn, and the two facts are different:

- `tests/gate_registry.py`'s `REQUIRED_GATES` carries **54** entries and **`test_review.py` is not
  among them**. The module's own scope statement names it explicitly: *"`TEMPLATE/tests/test_review.py`
  is a raw file that is NOT a gate"* (its line 358), listed beside `test_telemetry.py` as a
  false-positive the registry's pattern-based derivation must not pick up.
- **What a member's gate set must contain is therefore the file, at the manifest grain** — not an
  entry in a tuple. The manifest is what keeps a member from *"dropping the runner and keeping the
  file"*, which is the mechanism `REQUIRED_GATES` exists to serve for the gates that ARE registered.

**Four gates cover this instrument, and each covers a different property:**

| gate | property it holds over this instrument |
|---|---|
| `tests/test_review.py` | the instrument's own behaviour — the 17 named tests of §7 |
| `tests/test_docs_sync.py` | the doc pair — every `docs/` ↔ `TEMPLATE/docs/` pair byte-identical |
| `tests/test_template_sync.py` | all **84** pairs, and the portability scan (0 hex literals resolving) |
| `tests/test_kit_pin.py` | the manifest pin — a member's verdict depends on **its own** pin, never ours |
| `tests/test_kit_manifest.py` | that every shipped path carries a class and the digest matches the tree |

**The instrument asserts its own non-absence:** `test_schema_artifact_is_generated` fails if the
shipped schema is stale against `review.py schema`, so the artifact and its emitter cannot drift
apart unnoticed. That is a *self*-check, and it is the reason part 3 is enforceable without a
registry entry.

## 5. The version identifier — part 4

**Defined in frame §7.1 and cited here, not restated.** What this file supplies is the set the
identifier is read over: **the five paths in §2**, both halves.

**No hand-typed version exists in this instrument**, which is the part-4 forcing fact. Measured:
`tools/review.py` returns **0** hits for `VERSION`/`__version__` as an assigned constant; the only
version-shaped string in the file is `SCHEMA_VERSION = 1`, and that numbers the **state schema**, not
the instrument. A hand-typed instrument number drifting from the tree is exactly what frame §7.1
forbids, so none is coined here.

**The readings, each WITH its instant, and none of them a claim about now:**

| reading | value | predicate | instant |
|---|---|---|---|
| kit manifest version | `8d15725ac358` | digest over the manifest's own `(path, sha256, class)` triples, **134** files | 2026-09-27T16:14Z |
| this instrument's declared set | **5 paths** (10 with both halves) | manifest paths carrying this instrument (§2) | as above |

**The manifest reading above was taken BEFORE this file joined the manifest**, so it does not yet
count the law you are reading. The second reading is the one taken WITH this file present:

| reading | value | predicate | instant |
|---|---|---|---|
| before this doc joined | `8d15725ac358` | 134 files, 106 `standalone` | 2026-09-27T16:14Z |
| with this doc present | `4c142a360cff` | **135** files, **107** `standalone` | 2026-09-27T16:26Z |

**A corrected reading is written BESIDE the old one, never over it** (frame §7.1's own discipline for
a superseded figure), so both stand.

**And no value written in this file can ever be current — measured, not reasoned.** This law doc is
itself a `standalone` manifest path, so **editing this file changes the digest that reports the
version of this file.** Controlled probe this turn: one appended byte moved this doc's own sha256
from `096942ab8ff1` to `c05479b31cce` and moved `kit_version` from `4c142a360cff` to
`44720ca152e1` — the reading moved because the writer wrote. The value is therefore published with
its instant and its reason for being superseded, never as a claim of currency.

**This is a property, not a defect of the measurement**, and it is the sharpest form of frame §7.1's
rule that a hand-typed number is a claim nothing can test: here the DERIVED number is also
untestable from inside the file that carries it. **To read the version, read
`registry/kit.json`** — the manifest is the only surface where the reading and the tree are the same
object.

**These are readings at the instant shown and NOT a statement that the instrument is current.** The
manifest moves whenever any shipped file moves, including files this instrument does not own, so a
version quoted without its instant is a claim that cannot be tested — the defect frame §7.1 exists to
prevent.

## 6. Data surfaces — part 7

Which surfaces ship and which the factory **owns**. The frame's rule is the load-bearing half: *the
factory's declarations are never overwritten by an update* (frame §2, part 7). An update that
overwrote a member's proposals or intake declaration would destroy the evidence the review exists to
collect.

| surface | ships as | owner | why it must not be overwritten |
|---|---|---|---|
| `reviews/<cycle_id>/state.json` | **created by `init`** | **the factory** | the cycle's own lifecycle, census, proposals index and freeze snapshot — the instrument's memory of one review |
| `reviews/<cycle_id>/proposals/*` | **the member writes them** | **the factory** | the worker input the review exists to collect; intake is READ-ONLY over it, asserted by `test_intake_is_read_only_over_member_data` |
| `reviews/<cycle_id>/intake.json` | **the member writes it** | **the factory** | the DECLARATION of where input lands; no `.example` ships because the channels are the member's and a template would name ours |
| `reviews/<cycle_id>/reports/lens-*.md` | written by `record` | **the factory** | the lens evidence, checksummed into the state |
| the declared LEDGER path | the member's own | **the factory** | optional and explicitly declared; intake reads it and never writes it |
| `registry/kit.json` | generated | the **kit** | the version source (§5) — regenerated, never hand-edited |
| `docs/review-cycle.schema.json` | generated | the **kit** | emitted by `review.py schema`; the pair is held byte-identical by `test_docs_sync.py` |

**A surface absent from this table is absent by measurement, not by omission.** Note the shape that
distinguishes this instrument: **it ships no `.example` data at all.** Its inputs are the member's,
declared at runtime; the only shipped artifacts are the executable, its gate, its schema and its law.
A member therefore cannot "adopt the example and keep the runner" here — there is no example to
adopt, which is why §4's manifest grain carries the whole weight.

## 7. Self-probe and non-vacuity — part 8

**A gate that has only seen good input has not been shown to bite** (frame §2, part 8). This
instrument's probes are named, not implied — all **17** are in `tests/test_review.py`, and each is
named for the behaviour it pins. The four this promotion added are the ones that make the new
mechanisms non-vacuous:

| probe | what it shows |
|---|---|
| `test_step0_recovery_reads_state_alone_and_records_durable_evidence` | step 0 answers from state and `--record` leaves EVIDENCE — a printed reading is not a durable one |
| `test_frozen_cycle_refuses_a_live_channel_read` | the freeze REFUSES a live read (rc=2) **and** `--live` warns rather than silently proceeding; the close also wrote a snapshot carrying a digest |
| `test_a_lens_waiver_requires_a_named_reason` | a blank waiver is refused, so the census cannot read complete over an undecided lens |
| `test_a_missing_closure_cannot_pass_verify` | the status says COMPLETED and the bytes are gone → verify FAILS; a status trusted alone reports a clean census over absent evidence |

**The remaining thirteen pin the older surface**, and they are listed because a probe set stated as a
count is not a probe set stated by name: `test_review_lifecycle`, `test_schema_artifact_is_generated`,
`test_cadence_boundary_is_anchored`, `test_cadence_reads_both_shipped_ledger_formats`,
`test_legacy_state_is_refused_and_migrated_explicitly`, `test_close_sets_both_durations`,
`test_verify_reports_unreceipted_lenses`, `test_intake_refuses_with_no_declarations`,
`test_intake_is_read_only_over_member_data`, `test_intake_names_empty_and_incomplete`,
`test_intake_refuses_a_declared_channel_that_is_absent`,
`test_intake_receipts_validate_against_the_schema`, `test_shipped_executable_carries_no_donor_tokens`.

**Two of these are structural rather than behavioural, and they are the ones a member most needs:**

- `test_shipped_executable_carries_no_donor_tokens` — the shipped file names **no** donor surface
  (session uuids, board ids, recipient names, `session_notify`, the donor's law files). Measured 0 in
  **both** halves. A shipped literal would send a member's review to the donor's lanes.
- `test_intake_receipts_validate_against_the_schema` — every key a receipt carries is DECLARED by the
  shipped schema, so the artifact and the emitter cannot drift.

**Non-vacuity of the LIVE leg:** the schema probe is the live one — `review.py schema` is run against
the shipped artifact on every invocation of the gate, so a stale artifact fails rather than passing
quietly. A gate that only compared two stored copies would be the vacuity this part prevents.

## 8. Update path and the member's adoption — part 9

**The deferred state is defined in frame §7.2 and cited here: a member behind on this instrument
states it as a declaration — "behind by N, deferred because X" — and only UNDECLARED divergence
reds.** The surface it declares onto is named by the frame (§7.2), not by this file.

The member's steps for THIS instrument, in order. The declaration is the file you are reading; the
install travels `registry/kit.json` (manifest grain, never a per-member dispatch):

1. **Port the declared set (§2)** — the five paths, both halves. The manifest's classes come with
   them, so a dropped path is visible as a `standalone` absence rather than a smaller number.
2. **Nothing else is a prerequisite, and that is measured rather than assumed.** The closure is
   empty (§3): the executable is stdlib-only and cannot crash at import on a missing sibling. This is
   the one adoption step in this fleet that carries no loud failure — **and that is exactly why it is
   stated here**, because a member that expects a crash will not look for the absence of one.
3. **Write your own `intake.json` if your input lands in a ledger.** A member with no ledger needs no
   declaration and intake still works off `proposals/`. A member WITH one must declare it, because an
   undeclared ledger is reported ABSENT rather than read as empty — and reading a ledger nobody
   declared is how a factory's input silently becomes a different factory's.
4. **Register the gate at the manifest grain (§4).** `test_review.py` is a raw gate and not a
   `REQUIRED_GATES` entry, so the pairing into your manifest is what keeps a dropped runner from
   leaving a green file over an empty question.
5. **Create your own reload link** if you want this law to survive your own compaction — the frame's
   §6.1 defines it and it is **your** act, in **your** tree; it is never installed from the template.
   Absent from your tree is a **declared state**, not a failure.

### 8.1 The HQ-authored obligations that bind a member here

**These are HQ's, stated in full in the frame's §9, which a member can read; they are cited here with
their ruling identities and NOT restated, because restating is how one definition becomes two.** What
this subsection adds is only what each means **for an instrument adopted at this manifest grain**:

| obligation | authority | what it requires of a member adopting THIS instrument |
|---|---|---|
| **O1 — migration duty** | ruling n=1292 (C1) | a member holding a divergent copy of one of §2's five paths disposes of it: migrate, declare the fork with its reason, or defer with a re-entry condition — silence is not a disposition |
| **O2 — promotion duty** | ruling n=1283 | this instrument IS the promoted shape; a donor factory migrates to it rather than keeping its own (the migration population is named in the promotion record) |
| **O3 — pin duty** | ruling n=1292 (C4) | the member vendors `registry/kit.json` as **its own pin** and reds on divergence from **that pin**, never from the meta-factory's live manifest |
| **O4 — declaration duty** | ruling n=1292 (C5) | for this instrument the declaration is `intake.json` (§6): where your input lands, or a stated reason you have none |
| **O5 — subject-namespace duty** | ruling n=971 | not specific to this instrument, and it binds every ledger-holder: a bare hash-N namespace is one board's |
| **O6 — initialization duty** | owner order 2026-09-27T14:00Z; n=1283 Q2 | a member is initialized to the kit system **or declares why not**, on the surface the frame names — a deferral must be distinguishable from a decision nobody took |

**Every obligation above is HQ's and none of it is coined here.** If a member needs one changed, the
change belongs at HQ, not in this file.

## 9. Adoption census

**Predicate:** each of the five declared paths of §2 exists in the member's own declared `/repo`
(a member counts as present only if the path is there; both halves are counted, because a member that
took the root half and not the `TEMPLATE/` half holds a pair it cannot sync).
**Scope:** the member manifests in `registry/factories/*.json`.
**Instant:** the census has **not** been run for this instrument yet — the wave is step 9 of the
promotion, and no number is published here in advance of it.

**Stated as an absence with its reason, never as a zero.** Zero members hold this instrument today
and zero members have declared a deferral. Those are different facts — an absence of adoption and an
absence of *declaration* — and publishing `0` without both predicates would make a wave that has not
run look like a wave that found nothing. Both readings are written here when the wave returns them,
each with its own instant.

## 10. Where this instrument's law lives

**One copy, two paths, plus the reload link (HQ ruling C — the convention for every instrument):**

| path | role |
|---|---|
| `TEMPLATE/docs/instruments/review-rotation.md` | the canonical half — the one the manifest hashes |
| `docs/instruments/review-rotation.md` | the byte-identical root half, held in sync by `test_docs_sync.py` |
| `skills/meta-factory/review-rotation.md` | a **RELATIVE** symlink to the canonical half — `../../TEMPLATE/docs/instruments/review-rotation.md` |

**Why a RELATIVE link:** it survives a move of either tree, which the absolute form does not (the
frame's §6.1 records the same preference from the `skills/grafana/` production precedent). This link
is the **meta-factory's own** reload link, created by this lane as the meta-factory's instrument
owner; **a member creates its own** and the form is its decision (§8 step 5).

**The link existing is not the same as the link being loaded.** The loader discovers top-level
auxiliary `.md` files beside `SKILL.md` through the link, so the law re-enters context after a
compaction only for the tree that carries the link — which is the whole reason the step is the
member's and not ours.
