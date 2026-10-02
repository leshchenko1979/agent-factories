# The hygiene instrument

**Owns:** this instrument's own law — its declared file set, its closure, its gate set, its data
surfaces, its version source and its adoption census. It owns **no** cross-instrument definition;
those live in the frame it cites.
**Writer:** the Hygiene lane — addressed by the authoring commit's `Session-Id` trailer, never by a
lane name in a heading (frame §8).
**Reviewer:** the Instruments-methodology lane. The frame makes review of a per-instrument law file a
**requirement, not a courtesy** (frame §8).
**Authority:** **HQ retains cross-factory authority.** Any clause in this file that binds a member
factory is HQ's, and so is the process law *about* instruments; both are cited here, never coined.
**Class:** `standalone` — a **shipped** instrument. Canonical half
`TEMPLATE/docs/instruments/hygiene.md`; repo pair `docs/instruments/hygiene.md` (byte-identical);
reload link `skills/meta-factory/hygiene.md` (frame §6).

**This file cites `template-instruments.md`, the frame, and never restates it** — restating is how one
definition becomes two, and two definitions drift. Parts 4, 7, 8 and 9 are cross-instrument by
construction: the frame defines them **once, precisely so an instrument owner does not coin their
own.** This file therefore supplies only what is true of THIS instrument:

| part | defined by | what this file supplies |
|---|---|---|
| **4** — version identifier | frame §7.1 | the declared file set the identifier is read over (§2, §5) |
| **7** — data surfaces | frame §2 | which surface ships as `.example` and which the factory owns (§6) |
| **8** — self-probe | frame §2 | the named probes that make this instrument's gate actually BITE (§7) |
| **9** — update path | frame §7.2 and §6.1 | the member's adoption steps for THIS instrument (§8) |

## 1. What the hygiene instrument is

**Its job, in one sentence: a factory audits and reaps its own workspace on a declared cadence, and
tells a lane's work IN FLIGHT from work STRANDED by age — so a healthy factory with busy lanes never
reads DEGRADED, and genuine litter is still caught.**

It upholds **Process 4 — Workspace Hygiene Sweep** (`docs/processes.md`), HQ-owned, whose declared
cadence is daily and whose client value is *zero runaway storage, zero stale scratch interference,
reproducible builds*.

The lifecycle is one pass over the factory's own tree, and no state in it is a silent pass:

```
    walk ──▶ classify ──▶ (advisory | violation) ──▶ report ──▶ [--clean] reap ──▶ record
                │                                         │
         age vs the grace window              the namespace is PRINTED with its provenance
```

**Four commitments, each tracing to a defect this instrument exists to close. They are stated because
a reader who does not know them will "simplify" the tool back into one of them:**

- **The namespace is OWNED, and derived rather than hardcoded.** `NAMESPACE` is the repository
  directory name, so a factory bootstrapped from this template owns its own prefix automatically. The
  first version globbed `/tmp/oc-*` and went RED for the OpenCrabs dev tooling's litter — a **false
  red**, the mirror of a false green and just as corrosive, because a gate that cries wolf gets
  switched off. `--scratch-glob` adds an owned namespace; it is never a way to widen the list to a
  prefix somebody else already writes to.
- **AGE is the discriminator, never a path allowlist.** This factory's working tree is shared, so "a
  path is dirty" and "a path was abandoned" are different facts. A file written minutes ago belongs to
  a lane still working; the same file a day later is stranded. `--grace-minutes` (default 60) declares
  the window, and it is declared by the CALLER because how long a lane may hold a file is a property
  of the factory's process, not of this tool. The allowlist form was refused by name: exempting one
  path removes that case and leaves the general one.
- **A foreign stranded path is RECORDED, never silenced.** The run's closing invariant admits the
  verdict `workspace_gate=blocked-by-unowned`, lawful only when the run NAMES the blocking paths. It
  is never a forged clean, and `--require-committed <path>` ADDS a leg (a run's own artifacts, no
  grace at all) rather than removing one.
- **A declaration is a FILE, not a flag.** The reaper consults `docs/hygiene-protected.json` before it
  unlinks, because AGE ALONE cannot tell a stale scratch file from LIVE STATE: a lock created once and
  held long-term has an mtime nothing refreshes. A runtime flag is a declaration a cron forgets.

**Two claims this instrument has WITHDRAWN rather than made true, both stated because a reader will
otherwise infer them:**

- **The run-scoped form does not exist.** The module docstring once promised a "run-scoped check"
  beside the whole-tree one; the tool has never had it. The claim was withdrawn, because a reader who
  believed it went looking for a flag that is not here.
- **The declaration is a PREVENTION surface, not a repair.** An entry matching nothing is PRINTED but
  is **not** a problem — the point is to declare a path BEFORE the code that creates it lands. That is
  the one deliberate difference from the exemption surfaces, where an unmatched entry is a stale debt.

## 2. The declared file set

**Predicate:** the shipped paths the manifest classifies `standalone` that carry this instrument.
**Scope:** `registry/kit.json` at the instant named in §5. Both halves are listed because the pair is
what a member adopts; the manifest hashes the `TEMPLATE/` half (frame §5.1).

| # | path (root half ↔ TEMPLATE half) | class | what it is |
|---|---|---|---|
| 1 | `tools/hygiene.py` ↔ `TEMPLATE/tools/hygiene.py` | `standalone` | **the executable** — audit, classify, reap |
| 2 | `tests/test_hygiene_inflight.py` ↔ `TEMPLATE/tests/test_hygiene_inflight.py` | `standalone` | **the gate** — in-flight vs stranded |
| 3 | `tests/test_hygiene_namespace.py` ↔ `TEMPLATE/tests/test_hygiene_namespace.py` | `standalone` | **the gate** — the owned namespace |
| 4 | `docs/hygiene-protected.example.json` ↔ `TEMPLATE/docs/hygiene-protected.example.json` | `standalone` | the data-surface skeleton (§6) |
| 5 | `docs/instruments/hygiene.md` ↔ `TEMPLATE/docs/instruments/hygiene.md` | `standalone` | this file |
| 6 | `tests/test_hygiene_build_residue.py` ↔ `TEMPLATE/tests/test_hygiene_build_residue.py` | `standalone` | **the gate** — build residue is declared out and printed (§4) |

**A reader holding the law file and the tree can answer *"is this instrument complete here?"* without
enumerating imports**, which is what frame §1 requires of a declaration. The five pairs of rows 1–4 and
6 were compared byte-for-byte and are identical; row 5's pair is held by `tests/test_docs_sync.py`.

## 3. The closure — declared, and it is EMPTY

**Frame §1.1 is the load-bearing half and is cited, not restated: completeness is DECLARED, never
derived**, because a static import walk is blind to a dependency loaded from a string constant and a
gate can be green over a missing closure.

**This instrument's closure is empty, and that is a declaration rather than an omission.** Measured
over the executable at its source:

- `tools/hygiene.py` imports **only stdlib** — `argparse`, `glob`, `json`, `os`, `shutil`,
  `subprocess`, `sys`, `time`, `pathlib` — and carries **no local-module import at all** (0 hits for
  `^import tools`, `^from tools`, `^from .`).
- It therefore has **no HARD tier and no LAZY tier**: frame §1.2's silent tier cannot exist where
  there is no second module to fail to import.

**The consequence is stated because it is the one a member must not get wrong:** this instrument
cannot be broken at import by a missing sibling, so **the ported-without-its-closure class is not
available here**. A member that adopts the declared set and nothing else has a runnable executable.

## 4. The gate set and its registry entries

**All eight rows are registered in `registry/gates.json`**, which is what makes them run rather than
merely exist — a gate never registered never runs (frame §2, part 3).

| gate | invocation mode | budget (s) | margin | measured (s) | measured at |
|---|---|---|---|---|---|
| `tools/hygiene.py` | `script` | 14.22 | 4.223× | 3.369 | `aa5c175baef03f29ab97400f73fba7ed19315b8a` |
| `tests/test_hygiene_inflight.py` | `pytest` | 26.67 | 4.116× | 6.48 | `d36ce91cae0ef3f1d07c43c389bf58e8384c00a7` |
| `tests/test_hygiene_namespace.py` | `pytest` | 35.95 | 4.085× | 8.8 | `ed419678fb911774d2fac0a4ac48c6e7344f9984` |
| `tests/test_hygiene_build_residue.py` | `pytest` | 63.87 | 4.048× | 15.781 | `049a93cc73c4f02be4c8e47f1028924936644d03` |
| `tests/test_hygiene_declaration_sweep.py` | `pytest` | 51.2 | 4.059× | 12.615 | `0eb39c7915699688a4f42b8f0887de893eac2a83` |
| `tests/test_hygiene_placement.py` | `pytest` | 46.94 | 4.065× | 11.546 | `84dbddf8d9575a181b7401920ff9e63f1516390e` |
| `tests/test_hygiene_stale_dirs.py` | `pytest` | 26.1 | 4.118× | 6.337 | `ae34b695ef90f48abbfeb53a5d717a9b8f1f9643` |
| `tests/test_hygiene_evidence_supersession.py` | `pytest` | 53.46 | 4.057× | 13.178 | `aa5c175baef03f29ab97400f73fba7ed19315b8a` |

The figures are read from `registry/gates.json` and are **budgets, not claims about this instrument**:
a budget is the ceiling the gate may take, and the margin is the multiple between the measured run and
that ceiling. The later rows were measured on a loaded box (build residue at load **10.39**, the declaration
sweep at load **4.14**, the placement map at load **8.23**, the stale-directory leg at load **6.92**, the supersession leg at load **11.05**, the tool itself at load **10.77**), so each is a conservative upper bound
on a quiet-tree runtime rather than a tight one. Each of those rows' basis landed in the
**commit that follows its registration**, deliberately and not in the registration itself: a budget
base may never name the commit that introduces it, because the staleness leg compares the gate file at
`measured_at` against the same file at HEAD, so a base pointing at its own commit would compare the
file with itself and could never report drift.

**The tool's own row was RE-DERIVED here, and the reason is the gate program's whole subject.** When
its basis was declared the tool measured 0.57 s and took a 3.03 s ceiling. G3 and G5 then added two
report legs to it — a worktree census and a directory walk — and each one grew it further: measured
again after G5 it ran 0.93–1.89 s, so the old 3.03 s left a margin of about **1.6×**, and it was
re-declared to 8.32 s; measured again after G6 it runs 1.20–2.82 s, so that was re-declared in turn
to 12.04 s; and measured again after G7 it runs 1.27–3.37 s, so the basis beside this landing
re-declares it a third time, to **14.22 s**. A gate over its budget is **KILLED**, which
reads as a red that says nothing about the tree. A basis is a declaration about what runs, so it is
re-declared rather than left standing as a stale number beside a larger tool — the same class this
instrument exists to catch, caught in its own registry.

**Evidence supersession is REPORTED, report-only (G7; q13, ruled 2026-09-30).** `evidence/` and
`reviews/` are **append-only history**: an artifact is never deleted when a later run replaces it, so
the tree accumulates snapshots and the only thing that says which one governs is a hand-written notice
— or, more often, the reader noticing that a later dated sibling exists. Measured 2026-10-02: **25 dated
artifacts over 15 artifact families**, six of them carrying more than one member, and **zero**
`superseded_by` markers
anywhere in the tree — so every supersession in this repository is prose-only, which is exactly the gap
G7 names. The leg reads **two signals that fail differently**: the **declared naming convention** (a
dated artifact `<stem>-YYYY-MM-DD[-<suffix>].md` whose date is strictly older than its family's newest
is superseded) and a **prose notice naming a successor path** (which catches the singleton case the
convention cannot see). A **tie at the newest date is not a supersession** — the suffix distinguishes a
variant, not an older snapshot, so a plain census beside a `-refused` one are both current. A
mechanical `superseded_by` naming a **live** path **excuses** the artifact and the census moves; a
marker naming nothing is a **STALE MARKER reported separately**, never folded into `marked`, because a
fabricated supersession reads as a decision somebody made and is worse than an unmarked one. An absent
`evidence/` tree is **`absent`**, never a clean zero. This is a **debt census and not a fault list**:
the report is expected to be non-empty here, and the number falls only as markers are added. The
`removes: no` half is asserted **structurally**, by scanning the leg's own source for a removal call —
what a successor *is* is a judgement by the lane that produced the artifact, and a marker this tool
invented would be a fabricated supersession.

**Stale directories outside the namespace are REPORTED, report-only (G6; q13, ruled 2026-09-30).** The
reaper's glob is `/tmp/<namespace>-*`, and that glob is the whole of its vision: a directory this
factory created at any other path is invisible to every leg of `tools/hygiene.py`. `git worktree add`
is the declared creation convention that produces exactly that class, and the path is the caller's
choice — `/tmp/af-223` and `/tmp/af-225/wt` are both trees this factory made and **neither** matches
the pattern. Measured 2026-10-02, the leg's first run reports **75 registered trees, all 75 outside the
namespace**, so a tree left behind by a killed lane survives indefinitely and nothing reported it. The
census is **git's own** (`git worktree list --porcelain`), never a `/tmp` glob, because a scratch
prefix would miss the main tree and every tree named outside the namespace. The leg prints the
population — `hygiene stale directories: N tree(s), M outside the namespace \`<pattern>\`, P prunable,
L landed, A older than 24h (removes: no)` — and enumerates only the **prunable** class by name, with
git's own reason, because that is a declaration by the tool that owns the data rather than an inference
by this one. **`landed` and `age` are counts, never a verdict:** a tree's HEAD being an ancestor of the
primary branch means its *work* landed, not that the tree is abandoned — a live lane sits on a landed
commit between edits, and this very worktree did while the leg was written — so both are printed beside
each other and the judgement is left to a reader. An unreadable census is **NOT RUN** with its reason,
and an unanswerable reachability check renders `landed NOT RUN` rather than a false `0 landed`. The
`removes: no` half is asserted **structurally**, by scanning the leg's own source for a removal call —
`git worktree prune` is a write, and the tree may hold a peer lane's uncommitted work.

**Placement is CHECKED against a declared map, report-only (G5; q13, ruled 2026-09-30).** The owner's
own bullet names this surface — "files grouped/regrouped in folders, proper naming consistent with the
contents" — and `ONTOLOGY.md` states the naming half only as *patterns* (`## Naming law`). Nothing
answered the placement half at all, so a file could sit in a directory its content does not belong to
and every leg of `tools/hygiene.py` would still read clean. The leg is the smallest predicate that
bites: a **declared map of directory -> content class**, checked against the tree —
`hygiene placement: N file(s) over M declared directory(ies) — X mismatch(es), Y naming mismatch(es)
(removes: no)`. `tools/kit_names.py` answers a different question (one name meaning two things across
**trees**) and is **cited here, not replaced**. Three properties keep the map honest. **An unmapped
directory states its reason** — never silently exempt, the discipline the declaration sweep applies to
its unswept families. **A mapped directory that is absent is `absent`, not clean**, for the same reason
the other two legs refuse a silent zero. And **the map is checked against the tree rather than against
itself**: a top-level directory holding files that the map names nowhere is reported `UNDECLARED`, so a
new directory cannot arrive without a declared content class — a self-describing map could never see
that drift. The naming half is read from the law's own example
(`evidence/scores/YYYY-MM-DD.md`), and a mapped directory is judged in the shipped mirror as well as at
the root, because `TEMPLATE/` is the root's mirror by construction and a factory inherits what is
there. The `removes: no` half is asserted **structurally**, by scanning the leg's own source for a
removal call — a misplaced file is a decision for a human to make, and this leg only reports it.

**The declaration surfaces are CROSS-SWEPT, report-only (G2; q13, ruled 2026-09-30).** The `docs/*.json`
declaration files are the factory's own debt register: an exemption, a skip or an authorization is a
promise that some named target exists and deserves the exemption. Nothing checked that promise. A
target that is renamed, moved or deleted leaves the entry behind, and a stale exemption is **worse
than none** — it reads as a live grant while granting nothing, so the next reader honours a debt that
has already been paid off, and the surface it was protecting is silently unguarded. `tools/hygiene.py`
therefore sweeps all **15 declaration families** over the live `docs/*.json` files and prints one line per family
with its unmatched count —
`hygiene declaration sweep: N family(ies) over M live file(s) — T target(s), U unmatched (removes: no)`.
It is **report-only**: `removes: no`, and each surface's own tool keeps its write path, because a
second predicate over a population that already has an owner is the defect this factory files against.
Three properties are load-bearing. **A family this leg cannot sweep is declared with its reason, never
silently skipped** — five families name board issues, lanes, ledger rows, dates or vocabulary, none of
which a rename can strand, and each says so on its own line. **An unanswerable check is a third
state, not a false clean** — a commit probe that cannot run reports `NOT RUN` with its reason rather
than zero, because zero is a verdict only from a working instrument. And **a family with no live file
is `absent`, not clean** — the distinction the G3 leg draws for an unreadable census, for the same
reason. The `removes: no` half is asserted **structurally**, by scanning the leg's own source for a
removal call, the shape established for the worktree leg by `leshchenko1979/agent-factories#220`.

**Build residue is DECLARED OUT, and its population is PRINTED (G3; q15, ruled 2026-09-30).** The four
residue names — `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.audit.lock` — are **not** reaped by
this instrument and are **not** a gate failure. The reason is the one a member must not get wrong: a
worktree's cache belongs to that worktree and dies with the tree, so removing it from outside buys
nothing the tree's own removal does not, while a reaper that reaches into a peer lane's live worktree
is exactly the class of harm the report-leg shape (`removes: no`) exists to refuse. What the ruling
requires instead is **visibility**, and `tools/hygiene.py` prints the population on every run —
`hygiene build residue: N item(s) over M worktree(s) — <counts> (declared out, q15; removes: no)` —
with an unreadable worktree census reporting **NOT RUN** and its reason, never a clean zero. The
`removes: no` half is asserted **structurally**, by scanning the leg's own source for a removal call,
the shape established for the worktree leg by `leshchenko1979/agent-factories#220`.


**The docs leg is PARTIAL, and this is a declared gap rather than a footnote (frame §2, part 5).** The
BOOTSTRAP step exists — `TEMPLATE/BOOTSTRAP.md` names the tool, both gates and the declaration
skeleton, and names `--audit` as the adoption evidence — and the methodology entry exists
(`docs/processes.md`, the Process 4 row and its §4.4). **The SKILL clause does not exist:** measured
over `skills/meta-factory/SKILL.md` and `TEMPLATE/SKILL.md.tmpl`, this instrument's name occurs **0**
times in either. Adding one is a clause about the process *about* an instrument, which is **HQ's
authority, not this lane's** (frame §8) — so it is recorded here as a declared gap and routed, never
coined in this file.

**Scope, as ruled (q13, answered 2026-09-30).** Hygiene owns the **whole inventory** — all five surface
classes (A language, B filesystem, C work state, D kit, E runtime) — and it owns the **declaration** of
"clean" for each: the predicate and the population. It **builds a gate only where none exists**; where a
surface already has one, this law doc **cites** it, because a second predicate over the same population
is the defect this factory files against. The surface inventory, the gap table and each gap's
disposition live in `docs/projects/hygiene-surfaces.md` §6.

## 5. The version identifier — part 4

**This instrument's version is DERIVED from the manifest, never hand-typed, and the executable carries
no version string of its own** — measured over `tools/hygiene.py`, which carries no version attribute
and no self-probe flag. That is the frame's requirement rather than a gap (§7.1): a hand-typed number
is a claim about the tree that nothing can test.

The identifier is read over **the declared file set of §2** — not over the whole kit — so a member can
state *which version of the hygiene instrument it holds*:

```
python3 tools/kit_manifest.py --identity tools/hygiene.py tests/test_hygiene_inflight.py \
    tests/test_hygiene_namespace.py docs/hygiene-protected.example.json docs/instruments/hygiene.md
```

**This file cannot publish its own current value, and that is a property of the measurement rather
than a defect of it** (frame §7.4): the doc is itself a manifest path, so any edit to it moves the
digest it would be quoting, and the reading would move because the writer wrote. Publish instead the
**predicate** and the **command** above; the row a reviewer can reproduce is the one at the COMMIT
this file ships in.

## 6. Data surfaces — part 7

Two surfaces, and the split is the whole point (frame §2):

| surface | ships? | what it is |
|---|---|---|
| `docs/hygiene-protected.example.json` ↔ `TEMPLATE/docs/hygiene-protected.example.json` | **ships** — `standalone`, a declared path of §2 | the skeleton a factory copies; **the example itself is never read** |
| `docs/hygiene-protected.json` | **never ships** — factory data, and deliberately not a manifest path | the factory's own declaration of which paths inside its scratch namespace are LIVE STATE |

**The declaration carries two lists, `protected` and `scratch`, and both are empty in the shipped
state.** `protected` entries name paths the reaper must SKIP — never reported as stale, never
unlinked. `scratch` entries name paths that are genuinely reapable, classified so the classifier leg
can tell a declared literal from a new one. **Every entry carries two REQUIRED fields — `path` and
`why` — and a blank `why` is REFUSED when the declaration is read**, because an entry nobody could
defend in the output is one that should be fixed instead.

**Three states, and only one of them is a problem.** An **ABSENT** file means this factory has
declared no live paths, which is the shipped state of a new factory. A **readable** file is read. A
file that **EXISTS and cannot be read** is a reported problem — because only the silent failure is the
hazard. Every run prints how many entries are declared, so a reaper protecting nothing can never read
as one protecting everything.

## 7. Self-probe and non-vacuity — part 8

**A gate that has only seen good input has not been shown to bite** (frame §2). This instrument's
probes are its two gates, and each bites a different failure — neither is satisfied by the other:

- **`tests/test_hygiene_namespace.py`** probes the OWNERSHIP property by **planting litter under a
  prefix this factory does not own** (`oc-snap-oc-deploy-*`) inside a throwaway directory, and
  asserting the audit neither reports nor reaps it. It also pins that the prefix is **derived, not
  hardcoded**: `NAMESPACE` must equal the repository directory name, so a fork owns its own.
- **`tests/test_hygiene_inflight.py`** probes the CLASSIFICATION property. Its load-bearing arm runs
  the **SAME fresh edit** at the default window (rc=0, the in-flight criterion) and at
  `--grace-minutes 0` (rc=1, the stranded criterion in its strict form). The two criteria cannot both
  hold at one window, so the gate proves the window is the lever rather than asserting a
  classification.

**Both probes are hermetic**: every arm runs in a throwaway repo with the tool shipped into it, so the
live working tree is never touched and the exit codes under test are the real ones.

## 8. Update path and the member's adoption — part 9

The three legs are the frame's (§6) and are not restated here; what this section supplies is the
member's steps for THIS instrument:

1. **Take the declared set of §2** — the four executable, gate and skeleton pairs, and this file's
   pair.
2. **Regenerate or verify against the member's own pin**, never against this repo's live manifest
   (frame §9 O3).
3. **Create the member's own reload link** — `skills/<member-skill>/hygiene.md` →
   `../../docs/instruments/hygiene.md`. It is the member's act, in the member's tree, because only the
   member knows its own skill directory name, and it is never installed from here (frame §6.1).
4. **Declare the state** — `instruments.hygiene` on the member's own fragment
   (`registry/factories/<slug>.json`), naming BOTH axes: `held` and `green` (frame §7.2). A deferral
   names its reason; **silence is not a disposition**, and absence is valid only while the obligation
   is new.
5. **Set the window in the member's own process law.** A single-lane factory gets the strict form by
   declaring `--grace-minutes 0`; a factory with lanes declares a non-zero one. The tool will not
   choose for the member.

**A note on the run site, because it is a live trap.** `--namespace` defaults to the directory the
TOOL sits in, so a run from a **worktree** measures a namespace belonging to nobody. The namespace and
its provenance are PRINTED on every run for exactly this reason.

## 9. Adoption census

**Predicate:** the `instruments` map on each `registry/factories/<slug>.json` fragment.
**Scope:** the six fragments present. **Instant:** the turn that wrote this file.

| fragment | declares hygiene? |
|---|---|
| `ai-antispam` | no |
| `inferhub-watch` | no |
| `infra-factory` | no |
| `meta-factory` | no |
| `miidas` | no |
| `opencrabs-dev` | no |

**Zero of six declare it, and that is the census rather than a verdict**: no member has been asked for
this instrument yet, and a member that never considered it and one that deferred it read identically
until a fragment names it (frame §7.2). The row exists so the first declaration has a place to land,
and so a later census has a baseline it did not have to reconstruct.

**And the reload leg is verified in the MEMBER's tree, never in a worktree** (frame §6.3): a link that
exists only here reads `absent` against a member, correctly, because the member's tree has not
advanced.

## 10. Where this instrument's law lives

| role | path | held by |
|---|---|---|
| **canonical, shipped** | `TEMPLATE/docs/instruments/hygiene.md` | the manifest (`registry/kit.json`, sha256 + class) |
| **repo pair** | `docs/instruments/hygiene.md` — **byte-identical** | `tests/test_docs_sync.py` |
| **reload path** | `skills/meta-factory/hygiene.md` — **relative symlink** into the template half | the loader, which follows symlinks |

**Enforcement needs no third gate** (frame §6): the manifest hashes the shipped half and
`tests/test_docs_sync.py` holds the pair. A gate for a relation two gates already enforce is the
duplication this project's law forbids.
