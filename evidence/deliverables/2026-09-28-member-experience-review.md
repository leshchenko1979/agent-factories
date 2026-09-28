# Member-agent-experience review of the instrument law — synthesis

**Order:** owner, 2026-09-28 — *"subagent review the law for the agent experience for the member factories — will they receive enough info? what edge cases may arise? are they covered?"*

**Method.** Two read-only sub-agent reviewers, spawned per frame §5.1.3 (an authoring lane carries
self-confirmation bias, so the review must be isolated), each framed independently and neither shown
the other's brief:

- `1815e77a` **member-agent-experience-review** — reviewed the law as a *document set*.
- `f201fa1c` **member-seat-adoption-walkthrough** — adopted the kit *as* a member lane, step by step,
  choosing `ai-antispam` from `registry/factories/*.json`.

Both were read-only and shell-less. That is itself finding zero and is recorded in both reports: a
lane in that configuration **cannot obey frame §7.5** (*"a measurement reads the COMMITTED revision"*),
so every citation either made is to a working-tree read.

**Verification.** I re-measured every load-bearing claim myself at the commit tree
(`git show HEAD:<path>`), not the working tree. Findings below are marked **CONFIRMED**, **REFUTED**
or **PARTLY** accordingly. Three of the reviewers' claims did not survive that check; one of those
hid a sharper defect that I confirmed instead.

---

## 1. Verdict

**No — a member lane cannot adopt the kit correctly from the delivered bytes alone.**

Both reviewers reach the same conclusion from opposite directions: `1815e77a` by auditing the
obligations against what ships, `f201fa1c` by walking the on-ramp and getting stuck. The content is
sound — the manifest, the class system, the six per-instrument law files and the pin design all
survive scrutiny. **The failure is the entry path and the declaration/reporting legs.**

Its shape in one line: **the instrument's reading and install legs are complete; its declaration and
reporting legs point at surfaces the member cannot write and cannot read.**

---

## 2. Confirmed findings, ranked

| # | Finding | Evidence | Severity |
|---|---|---|---|
| M1 | **The on-ramp is a creation procedure, and nothing else ships.** `TEMPLATE/BOOTSTRAP.md` title reads *"Bootstrap — create a new factory"*; a member that follows it literally is told to **create a repo**, not to adopt into an existing one. No shipped document titled "adopt the kit" exists; the only member-facing adoption text is the per-instrument §8 blocks plus §9's obligations, both of which presuppose the reader already knows adoption exists. `docs/product.md:149-153` states the template **explicitly does not cover factory migration**. | CONFIRMED | **blocker** |
| M2 | **7 links in the shipped on-ramp escape `TEMPLATE/` and 3 of their targets do not ship.** `TEMPLATE/BOOTSTRAP.md` §0 links `../docs/product.md#fill-in-variables` (the variable table — *"Fill the variables first"*), §7 links `../docs/product.md#success-test`, §9 links `../docs/quality-criteria.md` (**the entire 19-criteria rubric the step asks the member to score against**), plus `../docs/addons.md` ×3. `docs/product.md` and `docs/quality-criteria.md` exist at root with **no TEMPLATE half** → absent from the manifest → not delivered. Delivered equivalents sit unlinked one directory over (`TEMPLATE/docs/addons/*`). | CONFIRMED | **blocker** |
| M3 | **`registry/gates.json` is a stated prerequisite that no step creates.** `BOOTSTRAP.md:19` requires it (*"which is which is declared per gate in `registry/gates.json`'s `modes`"*); grep for `gates.json` in the whole document returns only `:19` and `:24`; only `TEMPLATE/registry/gates.example.json` ships (`seed`). | CONFIRMED | **major** |
| M4 | **Two coordinate systems in one document.** Step 4b writes `cp TEMPLATE/registry/fleet.example.json registry/fleet.json` (`:266`); Step 4d writes `cp registry/fleet.example.json registry/fleet.json` (`:492`) for the same file. The member's tree has **no `TEMPLATE/` directory** (delivered bytes are prefix-stripped), so one of the two forms is wrong and nothing states which. | CONFIRMED | **major** |
| M5 | **The declaration surfaces are not member-writable, and no vehicle ships for them.** §9 O1 names `registry/kit-decisions.json` as *"the declaration surface"* — it is this repo's record. §7.2/O6 put the `kit` field on `registry/factories/<slug>.json` — the census reads those from **this** repo (`instrument_census.py:members()` globs `REPO/registry/factories/*.json`). Measured at the commit tree: **0 of 6 fragments carry `kit`** (all six carry `instruments`; 14 keys each), and `glob TEMPLATE/registry/*` ships three examples — `fleet`, `gates`, `kit` — none a decisions/exemptions/factories vehicle. | CONFIRMED | **blocker** |
| M6 | **The member's own fragment copy diverges from the copy the census reads.** `ai-antispam`'s tree holds its own `registry/factories/ai-antispam.json`; this repo holds another, with different `instruments` and `attested_at` values. Nothing reconciles the two, and which copy is authoritative is stated nowhere a member can read. | CONFIRMED (per reviewer 2's measured read; I verified the two-copy structure, not the byte values) | **major** |
| M7 | **The reload leg's prescribed shape breaks for a member whose skill dir is not a symlink into its repo.** §6.1 prescribes the **relative** form justified by *"the containing directory is itself a symlink"* (`:463-467`). Measured: `ai-antispam`'s profile skill dir is a **real directory**, where `../../docs/instruments/<x>.md` resolves to a non-existent path. | CONFIRMED (structure verified; per-member resolution from reviewer 2) | **major** |
| M8 | **The signal that would tell a member it adopted wrongly is generated only inside a repo it cannot read.** The census tool and its `evidence/instrument-census-*.md` artifacts are meta-factory-only — `tools/instrument_census.py` is **not in the manifest** (0 hits). A member therefore has no local reader reporting `HELD-UNDECLARED`. | CONFIRMED | **major** |
| M9 | **O5 tells the member to state a decision into nothing.** The clause reads *"picks ONE disposition and states it"* and names **no surface**; the canonical text it leans on (`skills/meta-factory/SKILL.md:740`) is not shipped (`skills/` = **0** manifest entries). | CONFIRMED | **major** |
| M10 | **The ledger's declared set has five defensible readings in the delivered bytes.** `ledger.md` §2 declares 15 paths; §5 says six gates and its table lists six rows *one of which is a `closure` module*; §2 rows 8-14 are seven gate rows; BOOTSTRAP says "SIX gates" and names six excluding `test_ledger_index.py`; the manifest ships **nine** `test_ledger*.py`. So *"am I compliant?"* — the question the whole census rests on — has no single answer member-side. | CONFIRMED (counts verified); **the resolution is partly mine** — see §4 | **major** |
| M11 | **§1 explicitly corrects the closure to exclude `tools/telemetry.py` and `tools/registry.py`, and shipped `tools/ledger.py` imports `registry` and `telemetry`.** A lane that follows the law loses the LOUD lazy tier, and §1.2's own specimen says the loss *"degrades to a MESSAGE that blames the DATA, not the missing file"* — green forever, stamping `telemetry=unavailable`. | CONFIRMED (imports present at `ledger.py:324`, `:946`); **which side is right is mine to rule** — see §4 | **major** |
| M12 | **O2's third leg has no delivery route to the donor.** §5.1 criterion 4 names the migration population, but that is internal to this repo; no artifact tells a *donor* it was a donor or what the promoted shape is. | CONFIRMED — and **this is the gap the owner asked about earlier today**: the law requires the donor to migrate and never requires that the donor be *told*. | **major** |
| M13 | **No shipped vehicle for `tools/actors.txt`** (O4 declares a duty; `BOOTSTRAP.md` Step 4b says `printf` it). Trivially creatable, no template to conform to. | CONFIRMED | minor |

---

## 3. Refuted — three reviewer claims that did not survive verification

Recorded in full, because each is the class the fleet files most often: **a zero read from a
population that excludes the subject by design.**

**R1 — "`TEMPLATE/registry/kit.example.json` is not in the manifest, therefore not shipped." (both reviewers) — REFUTED.**
It ships by a **second carrier**: it is a declared PAIR (`tests/test_template_sync.py:204`), and it is
excluded from the manifest **by design**, in the generator's own words:

> *"would have no fixpoint. `registry/kit.json` is outside the set for the same kind of reason
> (generated factory data, not shipped kit), so this is a **principled exception** and not the
> 'forgot to list it' case the completeness rule exists to refuse."* — `tools/kit_manifest.py:74-76`

Including the pin vehicle inside the manifest would change the manifest's own digest — an
unavoidable fixpoint regress. `manifest hit = 0` is a true reading of a population that excludes it.

**R2 — "a shipped gate reads a file the kit does not ship" (both reviewers) — REFUTED as stated, with a real kernel.**
`TEMPLATE/tests/test_kit_pin.py` does read `TEMPLATE/registry/kit.example.json` (`:69`, `:156`, `:187`)
and that path is absent from the manifest — but the file **arrives** (PAIR carrier, R1). The real
kernel is different and already law: those fixture arms resolve `TEMPLATE/`-only paths, and **no
member tree carries `TEMPLATE/`**, so the arms **SKIP** for every adopter and the **live arm
carries the verdict** — recorded at `pacemaker.md` §9.1.1: an adopter should read a member-tree green
as *"the live population is judged"*, never as *"every probe ran."* The finding is right; its
mechanism was misidentified.

**R3 — "`docs/product.md` and `docs/quality-criteria.md` should ship" — PARTLY.**
They do not ship, confirmed. But neither declares itself home-factory-only (grep for
`home-factory-only|does not ship` → **0** in both), so they are neither shipped nor *declared
exempt* — the state §6.3, landed today, exists to make lawful. **Either they ship, or they declare.**
That choice is HQ's, since the frame's own §6.3 requires the declaration and these are not my files.

---

## 4. The four findings that are mine to rule

| # | Question | Ruling |
|---|---|---|
| A | **M12 — does the law require notifying the donor and stating where ownership now lies?** | **No, and it should.** Measured this evening: a duty to *notify* the donor → **0 hits** in the frame; *"the meta-factory owns"* / *"ownership lies"* → **0 hits**. §8 is a **writer table** (who authors which file), not a statement that ownership moves. §5.3 says only that the donor *"becomes the evidence, not automatically the upstream"* — half a clause. O2 admits the hole itself: *"The third leg is the one with **no automatic owner** and is therefore stated here rather than assumed."* The migration duty is written down and **nothing triggers it**. §2 part 9 further requires a *"feedback channel"* that is **never defined anywhere**. **Fix: extend §5.3** — the promoting lane notifies the donor's owning lane in the same round as the landing (what was promoted, where the canonical copy now lives, what the donor owes); the canonical copy is the meta-factory's and the donor's becomes a vendored instance under O1; part 9's feedback channel is this clause. |
| B | **M11 — is `ledger.md` §1 right to exclude `telemetry.py`/`registry.py`, or is the tool right to import them?** | **Settled: the tool is the evidence, and its own docstring names the tier the law omits.** `TEMPLATE/tools/ledger.py:70-78` declares **three** tiers — *"Closure: ledger_declaration.py, field_predicate.py, reconstruction.py / **Deferred: registry.py, telemetry.py**"* — and states the consequence in its own words: *"Both must be present for the tool to work; only the first kind stops it from loading."* `ledger.md` carries **no Deferred tier at all** (`grep -c 'Deferred'` over the law doc → **0**), so its “NOT in the closure” row is true of the HARD tier and **incomplete as a whole**: a member actions it as *“I do not need these two.”* §1's predicate is not wrong, its **conclusion** is — the same shape as §1.5's and §7.6's stale counts, and the §1.4 class the frame names. Resolve by deriving the set from what the executable **loads** (module-level ⇒ HARD, in-function ⇒ DEFERRED, absent ⇒ absent), stating **both** tiers in the law, and letting the manifest supply each path's **class**. |
| C | **M10 — which of the five readings of the ledger's declared set is canonical?** | The instrument owner's, with **one** declaration at **one** coordinate — the §4/§7.6 discipline: a set stated once, at a named section, derived from what the executable loads, never from a prose count. |
| D | **M7 — the reload leg's relative form** | **Verified correct for symlinked skill dirs and wrong for real directories.** §6.1's justification (`:463-467`) states the precondition explicitly; what is missing is the *else* arm for a member whose skill dir is a real directory — an absolute link, or a copy. |

---

## 5. What this review does **not** say

It does not say the kit is unfit. Both reviewers independently list what is **right**, and their lists
agree: the manifest + class system is a real, checkable artifact; the six per-instrument law files
carry predicate, scope and instant with unusual discipline; the pin-vs-live-manifest distinction is
the correct design; the failure taxonomy is non-redundant. `f201fa1c`'s verdict sentence is the
accurate one — *"the kit's problem is not its content — it is that its **entry path and its declared
sets were never held to the same standard as its gates**, which is precisely the defect class its own
law names."*

---

## 6. Ranked repair list

| Order | Repair | Owner | Why first |
|---|---|---|---|
| 1 | **Ship an "adopt the kit" document** that states where the delivered bytes land, one coordinate system, the per-instrument declared sets, and admits it is not `BOOTSTRAP.md` | meta-factory (mine) | M1 + M4: without it every member either creates a second factory or stops at step 4b |
| 2 | **Resolve M2's three unshipped link targets** — ship `product.md`/`quality-criteria.md`, or re-point the links at the shipped equivalents | HQ (files are not mine) | the on-ramp's first instruction and its final scoring step are both broken |
| 3 | **§5.3 donor-notification + ownership clause** | mine — ruling A above | closes O2's orphaned leg and defines part 9's undefined feedback channel |
| 4 | **One canonical declared set per instrument, at one coordinate** | each instrument's lane | M10: the census's verdicts are not reproducible member-side until this holds |
| 5 | **A member-readable adoption signal** — ship the census, or a member-side equivalent | review-rotation lane (owns the tool) | M8: today the only artifact naming a wrong adoption lives where the member cannot read it |
| 6 | **`gates.json` creation step + one coordinate system in BOOTSTRAP** | meta-factory (mine) | M3 + M4: two defects that stop a literal reading |
| 7 | **Declaration surface: vehicles, and one authoritative copy** | HQ (schema) + meta-factory | M5 + M6: 0/6 fragments carry `kit`; two copies disagree |
| 8 | **Merge O5 and O1's named surface with a real member-writable one** | HQ | M9: currently a clause that points at nothing |

**Reproduce the reviewers' reports:** `~/.opencrabs/profiles/ops/tmp/detached/{1815e77a,f201fa1c}.json`,
field `finish.output_full`.
