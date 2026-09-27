# Instrument survey — which meta-factory parts need to be instruments

**Read:** 2026-09-27, by the Instruments-methodology lane, on `agent-factories` at HEAD `3631532`.
**Why it exists:** the owner ordered a survey of the meta-factory for parts that need to become
instruments, a lane to own their refactor, and the refactor itself. This is the survey half.

---

## 1. The predicate, stated before the figures

An **instrument** is the unit of adoption — everything one tool needs to work in a tree
(`docs/instruments/template-instruments.md` §1). It is a **DECLARED** object, and §1.1 requires the
declaration to travel with §2's nine-part full set: executable, closure, gate set + registry
entries, version identifier, docs, call sites, data surfaces, self-probe, update path.

So a part **needs to be an instrument** when it is both:

- **(a) a unit of adoption or operation** — a coherent job (a tool, its closure, its gates, its
  data surfaces) that a tree must hold *whole* to work; and
- **(b) UNDECLARED** — no law file under `docs/instruments/`, so no reader can answer *"is this
  instrument complete here?"*.

**Population measured:** the meta-factory's own tree (`/root/agent-factories`) — its repo-side
`tools/` (27 `.py`), its shipped `TEMPLATE/tools/` (19 tools: 13 executable + 6 closure, per
`tools/kit_surfaces.py`), its gates (`tests/` 68 files, `TEMPLATE/tests/` 56), and `docs/`.

**The headline figure:** `docs/instruments/` carries **1 file** — the frame itself.
**Zero instruments are declared today.** That is the whole finding this survey elaborates.

---

## 2. The clusters — job, file set, and declaration state

Each row is a candidate: one job, its measured file set, its gates, and whether it is declared.

| # | cluster (job) | executables / closure | gates | declared? |
|---|---|---|---|---|
| 1 | **kit** — ship, measure and version the kit | `kit_manifest`, `kit_census`, `kit_names`, `kit_surfaces`, `kit_deliver` (root-side); `kit_pin` (ships, closure) | `test_kit_manifest`, `test_kit_census`, `test_kit_names`, `test_kit_deliver`, `test_kit_pin` — **and NONE for `kit_surfaces`** | **no** |
| 2 | **ledger** — the append-only evidence store | `ledger`, `ledger_declaration`, `field_predicate`, `reconstruction`, `subject_anchor`, `telemetry`, `registry`, `registry_render` + `hooks/{commit-msg,pre-commit}` | 6 `test_ledger*.py` | **in flight** (ledger lane) |
| 3 | **registry** — the fleet registry + attestation | `registry`, `registry_attest`, `registry_render` | `test_registry*` | **no** |
| 4 | **audit** — coverage + gate budget | `audit`, `gate_budget` | `test_audit_rates`, `test_audit_inflight_guard` | **no** |
| 5 | **review** — artifact review | `review` + `docs/review-lenses.md` | `test_review*` | **no** |
| 6 | **hygiene** — namespace hygiene | `hygiene` | `test_hygiene_namespace` | **no** |
| 7 | **insights** — analytics over the ledger | `insights`, `synthesize_insights`, `brain_metrics`, `compaction_rate`, `telemetry` | `test_synthesize_insights`, `test_synthesize_interface` (both meta-factory-only) | **no** |
| 8 | **patrol** — host-state patrol | `patrol_host_state` | `test_patrol_host_state` | **no** |
| 9 | **publish** / **roadmap** | `publish`; `roadmap` (ships via the Domain add-on) | `test_publish*`; `test_roadmap*` | **no** |
| 10 | **questions** | `questions`, `questions-render.mjs` | `test_questions.py` | **in flight** (questions lane) |

**`kit` is the largest undeclared cluster and the only one with a measured gate gap.**

---

## 3. The gaps this survey measured

Stated with their predicate, because a figure without one is unreproducible.

### 3.1 `tools/kit_surfaces.py` has no gate — and it is the census instrument

**Predicate:** `grep -c kit_surfaces TEMPLATE/tests/gate_registry.py` → **0**; and no
`tests/*surface*.py` exists (the only `*surface*` paths are `docs/addons/surface/` and the
methodology module).

This is the sharpest finding. `kit_surfaces.py` opens *"A re-run has to be a COMMAND … This file is
the predicate, so the figure is derived"* — it exists precisely because two lanes read the same
census and produced **2/15** and **3/15** from prose. It replaces that prose with an executable
predicate, returns a verdict (**FAIL — 1 tool carries an undeclared gap**), and **nothing gates
it**. A non-vacuity probe never runs on it; a regression in its own predicates would be silent.

### 3.2 Two root-only tools are registered nowhere

**Predicate:** `grep -c <stem> TEMPLATE/tests/gate_registry.py` → `compaction_rate` **0**,
`render-trap-runbook` **0**.

Both are root-side (unshipped) meta-factory tools with no gate and no `gate_registry` entry, so
neither is exercised by any declared gate.

### 3.3 `subject_anchor` — an undeclared gap in the SHIPPED tree

**Predicate:** `python3 tools/kit_surfaces.py` → `VERDICT: FAIL — 1 tool(s) carry an undeclared
gap: subject_anchor missing S2` (S2 = `TEMPLATE/BOOTSTRAP.md` installs it).

A shipped executable that no bootstrap step installs. This is the one gap the census itself calls
undeclared — every other shortfall carries a declared exemption.

### 3.4 Two fleet-wide name conflicts (frame §4 criterion 2)

**Predicate:** `python3 tools/kit_names.py` → *10 tree(s), 76 name(s) carried, **2 conflict(s)**,
0 stdlib shadow(s)*.

| name | trees | purposes | overlap |
|---|---|---|---|
| `test_ontology.py` | 5 | **4** | **0.0** |
| `test_single_writer.py` | 5 | 2 | 0.2 |

Below 0.5 token overlap reads as *different instruments sharing a name* — which is exactly what
criterion 2 forbids. `test_ontology.py` at overlap 0.0 across four purposes is a name carrying four
different gates.

### 3.5 Fleet adoption is thin

**Predicate:** `python3 tools/kit_census.py --stdout`, over 5 reachable members × 120 manifest paths
= **600 pairs: same 11 · DIFF 48 · ABSENT 541**. The bootstrap-named subset (50 cells) reads
same 1 · DIFF 20 · ABSENT 29.

Not a defect in itself — adoption is the members' step (§7.2 defers as a declared state) — but it
is the baseline any promotion is measured against.

---

## 4. What this survey concludes

1. **The frame exists and nothing else does.** One law file; zero declared instruments.
2. **Three clusters are already claimed**: `ledger`, `questions` (lanes in flight), and `pacemaker`
   (a third lane, not a cluster in §2 because it is `tools/registry_attest.py` + `patrol_host_state`
   — the attestation/patrol job).
3. **The unclaimed, undeclared clusters** are `kit`, `registry`, `audit`, `review`, `hygiene`,
   `insights`, `publish`, `roadmap` — of which **`kit` is the largest and the only one with a
   measured gate gap** (§3.1).
4. **The refactor is not "write nine-part declarations for eight clusters" lazily.** Per the frame's
   §5.1, each promotion names its **migration population**, and per KISS/YAGNI the cheap first
   move is the **declaration** (§1) plus the **law file** (§6) plus the **measured gap** (§3.1) —
   not inventing parts a cluster does not have.

**Priority, by evidence in hand:** (1) `kit` — largest cluster, one measured gate gap, and it is the
instrument that *delivers every other instrument*, so its completeness gates everything downstream;
(2) `subject_anchor` §3.3 — a one-line gap in the shipped tree; (3) the two name conflicts §3.4;
(4) the remaining unclaimed clusters, each as its own declaration.

---

## 5. Reproduce

```
cd /root/agent-factories
python3 tools/kit_surfaces.py          # §3.3 + the 4/4 coverage figure
python3 tools/kit_names.py             # §3.4
python3 tools/kit_census.py --stdout   # §3.5
python3 tools/kit_manifest.py --check  # the manifest's own gate
```

---

## 6. Status of this survey's own counts

**This file is a dated read (HEAD `3631532`, 04:16Z) and its counts are snapshots, not live state.**
Measured at commit time, one figure has moved and is corrected here rather than rewritten above:

| figure | as read | at commit |
|---|---|---|
| files in `docs/instruments/` | 1 (this frame only) | **4** — `template-instruments.md`, plus `ledger.md` (`54249c2`), `open-questions.md` (`ef2489f`), `pacemaker.md` (`32a4051`) |

The cluster ranking and the five gaps are unchanged by that: the three new files are law homes for
instruments the census already saw, not instruments newly promoted by this survey. The lane that
owns the refactor derives from §3, not from this table.
