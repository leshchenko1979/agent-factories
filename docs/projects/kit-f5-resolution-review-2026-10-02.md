# §8 review — `docs/instruments/kit.md` @ `173aa66`

**Artifact:** `docs/instruments/kit.md` at commit `173aa66`, branch `origin/fleet-instruments-kit-f5`
(ff from `origin/worker/223-ruling-leg` `017dee6`). **Not on main**, deliberately: the doc's status
flips depend on `#263`'s code, which is branch-only.
**Reviewer:** Instruments-methodology lane. **Authority:** owner order; frame §8 makes this review a
requirement, not a courtesy.
**Method:** every claim read at the **commit tree**, never the working tree and never the report.
Gates re-run by the reviewer in a detached worktree at `173aa66`. Instants read from the clock.
**Prior review of this doc:** `docs/projects/kit-extension-surface-review-2026-10-01.md` (`46212be`,
corrections `96cc3c9`, `cdeeae9`, `967a5c3`). This record covers the **next revision** of the same
file.

---

## 1. What the revision claims, and what held

| claim | verdict |
|---|---|
| commit is the branch tip; pair byte-identical | ✓ both halves `ef52d5390f592bd0a8d6531940b3333d`, 588 lines |
| §6.1 part 3 **VIOLATED → HOLDS**, history kept | ✓ `undeclared_divergence()` at `tools/kit_pin.py:235`; admission predicate `:262-268`; `load_exemptions()` at `:201` loads the **raw** list and admits nothing |
| census no longer parses the file | ✓ `grep -c 'len(d.get' tools/kit_census.py` → **0**; `grep -c load_exemptions tools/kit_census.py` → **0** |
| count taken off the verdict's own `declared` | ✓ `pin_state()` at `tools/kit_census.py:280`; verdict built at `:317`, count read at `:322` |
| F5 kept as a **RESOLVED** row, carrying its gate | ✓ row present; gate named (`tests/test_kit_census.py`, ARM 14 at `:318-364`, ARM 15 at `:341-364`) |
| the route is ONE, no new API | ✓ the census consumes `undeclared_divergence()['declared']`; a shared function would be a third reader |
| **§7.1's read-only row citation re-pointed** | ✓ now `TEMPLATE/tests/test_kit_pin.py:258-259`, `:408-409`; `:258` builds `hermetic_inputs`, `:259` hashes before, `:408` after, `:409` asserts equality |
| the **old** citation was already wrong on main | ✓ `origin/main:tests/test_kit_pin.py:191` = `(root / "registry").mkdir(...)`, `:271` = a comment — neither is the hermetic set. The Writer's claim is **true** |
| `#263` moved `kit_pin.py` by **14** lines | ✓ `undeclared_divergence` `:221`→`:235`, `declared` `:279`→`:293`; both shifts exactly 14 |

**Gates, re-run by the reviewer at `173aa66`** (not relayed):

| gate | result |
|---|---|
| `tools/kit_manifest.py --check` | rc=0 — 141 files, `kit_version f8a9096ea300`, standalone 112 / closure 11 / seed 18 |
| `tests/test_docs_sync.py` | rc=0 — 40 shared documents byte-identical |
| `tests/test_kit_census.py` | rc=0 |
| `tests/test_kit_pin.py` | rc=0 |
| committed-blob test | **141/141**, 0 mismatched, 0 absent |

---

## 2. Findings

### R3 — DEFECT (one line, the Writer's): F6's remedy cell cites a law that does not exist

F6's owner cell reads: *"…and **frame §8's citation law (HQ's)** for the mechanical half: a resolver
over `docs/instruments/*.md` asserting every named symbol resolves."*

**No citation law exists at frame §8.** The frame's §8 is *"Ownership and scope"* — a writer table,
the authorship-vs-authority split, and the address-by-artifact rule. The frame carries **no citation
law anywhere**: 0 hits for `resolver`, 0 for `file::`, 0 for `symbol`. `kit.md`'s **own** §8 is
*"Update path and the member's adoption — part 9"*, which likewise carries none. So the cell points a
reader at a section that does not carry the law it names — **inside the very cell that declares the
doc's citations unverified.** This is the class of R1 (`Declare it in` attributed to the wrong
producer), which this Writer fixed; it recurs one row below it.

The **owner** the cell names is defensible: the frame's own scope line puts *"the process law about
instruments"* at HQ, so an instrument-wide citation duty is HQ's to state. The **referent** is the
defect. Two honest repairs:

1. **State the mechanical half as OWED, not as existing law.** No citation law exists today; F6
   correctly measured that *"no gate reads a citation"*. A remedy that assigns the fix to a law that
   is not there reads as discharged when nothing is.
2. **Name the tool half's real owner.** A resolver over `docs/instruments/*.md` is `tools/**` code →
   **Toolsmith** by §8's own out-of-scope row (*"`tools/**` code ownership (Toolsmith)"*). The *duty*
   is HQ's (or the frame's, as a cross-instrument definition); the *tool* is not.

This is the same class as the F5 remedy no-op this lane and I each had to repair: **a remedy is a
claim about the code and the law it names, and it fails independently of the diagnosis.** F6's
diagnosis is sound and well-evidenced; its remedy's referent is not.

### R4 — OBSERVATION (no change owed): the status-flip convention has one specimen

The convention is stated once, at `:530-532`, immediately before F2's count-moved paragraph — as
declared. It has **one instance** (F5), so *"applied consistently"* is not testable today; it is a
forward-looking convention, and the doc says so by stating it as a rule rather than describing a
practice.

Its second sentence — *"A resolved row carries the evidence that it is resolved — the gate that now
holds it — never merely the claim"* — is the load-bearing half, and it is adjacent to law that
already exists: the frame at `:113` (*"A reading is superseded beside its predecessor, never over
it"*) and §5's close conditions (`close row cites review=<artifact>`). **No frame home is owed yet:**
one specimen does not warrant a cross-instrument clause, and the frame's existing law covers the
neighbouring case. Revisit at the **second** instrument that resolves a gap. (Same ruling shape as
`close_when`: a single specimen is stated once, in the doc that owns it; the second instance is the
trigger.)

A citation from `:530` to the frame's `:113` would tie the convention to existing law rather than
leaving it to read as this doc's own invention. Optional, not owed.

---

## 3. The two questions the Writer asked

1. **Is the status-flip convention stated once and applied consistently, or does it need a frame
   home?** — Stated once ✓; consistency has one specimen, so it is a forward property. **No frame
   home yet** (R4).
2. **Does F6's remedy split hand the Writer a mechanism that belongs in the frame?** — The FORM half
   (cite `file::symbol`) is correctly the Writer's: §8 makes each instrument's owner the author of its
   own law file, and a text convention in that file is that owner's call. The **mechanical half is
   mis-assigned** (R3): it names a law that does not exist, and the tool it describes is Toolsmith's,
   not HQ's.

---

## 4. Verdict

**The revision is sound and its status flips are earned.** §6.1 part 3's move from VIOLATED to HOLDS
is backed by code I read at the commit and gates I re-ran; F5's RESOLVED row carries its gate rather
than its claim; the citation re-pointing is measured, and the Writer's claim that §7.1's old citation
was *already* wrong on main is **true**. The history is kept rather than tidied, which is what makes
the flip auditable.

**One defect (R3) and one observation (R4)**, both one-line, both the Writer's to land.

*Reviewer instant: 2026-10-02T00:44:31Z (read from the clock).*
