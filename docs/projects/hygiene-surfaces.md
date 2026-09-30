# Self-cleanliness — the surfaces, and the hierarchy of acts that hold them clean

> **Owns:** the hygiene instrument's surface inventory — which objects must stay clean, what
> "clean" means for each one, and which act upholds it.
> **Writer:** the hygiene instrument's owner lane. **Status:** DRAFT, pre-promotion, owner-gated
> (rule 10) — this is the thinking artifact the owner asked for, not the instrument's law.
> **Readings:** every count below is a reading taken at **2026-09-30T11:04:14Z**, HEAD `c325fc1`
> (`registry/kit.json` 138 files / `f582a2e92bb5`; `registry/gates.json` 49 declared gates;
> `docs/*.json` 25 files over 15 families; instrument law docs shipped: 6).

---

## 1. "Clean" is three different predicates, and only one of them is about dust

| Predicate | What it means | The failure it catches | The failure it does NOT catch |
|---|---|---|---|
| **EMPTY** | no debris: no stale scratch file, no stranded dirty path, no residue | disk exhaustion, stale scratch interference, unreproducible builds | a surface that is tidy and **wrong** |
| **TRUE** | nothing on the surface claims more than it is; a state claim is reproducible from its own record | the **false green** — a gate reporting clean over a population it never read | a surface **nobody reads at all** |
| **DECLARED** | every state a reader must act on sits at a findable coordinate, and an absence is distinguishable from a silence | a state that exists but no reader can find | — |

The factory's own history says the second predicate is the expensive one. Every hygiene defect on
the board is a `TRUE` failure, not a dust failure:

| Issue | The lie | State |
|---|---|---|
| #28 | "clean git tree" reported without ever testing modified tracked files | CLOSED |
| #38 | the audit went RED on a healthy factory whenever a peer lane was mid-task | CLOSED |
| #153 | the reap set and a factory's live state shared one namespace, globs widening but never excluding | CLOSED |
| #174 | a worktree run measured a namespace belonging to nobody | CLOSED |
| #199 | `git status` paths joined against the tool's directory, not the repo root — a false POSITIVE naming files that are present | CLOSED |
| #201 | the docstring promised a run-scoped form the tool has never had | CLOSED |
| #205 | a failing gate's headline cause was read from an informational line printed on every run | CLOSED |
| #220 | 37 registered worktrees sat outside the cleanliness instrument's population; one held a commit no remote and no branch carried | CLOSED |
| #54 | P7's mapped gate (`tools/hygiene.py`) never reads a cron row, so a work-executing pacemaker passed every gate | CLOSED |

So the hierarchy below is ordered by **what an act can prevent**, not by how much dust it removes.

---

## 2. The hierarchy of acts

| Level | Act | When it runs | Who holds it | A miss costs |
|---|---|---|---|---|
| **L0** | **Write-path prevention** — the object cannot represent the dirt | every write | the object's own instrument (ledger write path, hygiene's `--require-committed`, plan-store heal) | nothing: the state is unrepresentable |
| **L1** | **Mechanical gate** — a deterministic predicate over a declared population | every `audit.py` run | `tests/*` wired into `registry/gates.json` (49 entries, 77 invocation modes) | a defect that recurs until a gate exists |
| **L2** | **Pacemaker sweep** — a scheduled act that reaps or reports | daily / 6 h | Process 4 (`tools/hygiene.py`), `tools/patrol_host_state.py` | debris that accumulates between audits |
| **L3** | **Adversarial lens** — a sub-agent review for what no predicate can express | per review cycle | the 14-lens catalogue (`docs/review-lenses.md`), run by `tools/review.py` | rot nobody can write a predicate for yet |
| **L4** | **Promotion / retirement** — a finding becomes an L0/L1 mechanism, or is declared inapplicable | per finding | Process 2 (rework loop), `template-instruments.md` §5 promotion | the same defect returns |

**Two laws bind the whole ladder.**

1. **P29 — Law-Upholding Law.** Every codified rule must be upheld by an active registered process
   or a deterministic gate. A rule with neither is dead text. So *every surface named in §3 must
   carry an entry in the "upheld by" column, or it is a gap* — that is what makes this inventory
   checkable rather than a wish list.
2. **Re-arm on surface change.** A control disarms silently when the surface it mutates changes:
   a new second occurrence of a string it rewrites, or a new element satisfying a condition it
   removes. The control keeps passing while testing nothing (measured 2026-09-28: adding post links
   to the channel directory disarmed a permalink control and a title substring test in one commit).
   **Every leg below is a control, so every leg below owes a re-arm when its surface moves.**

---

## 3. The surfaces

### Class A — Language: the brain and the law

| Surface | Clean means | Upheld today by | Gap |
|---|---|---|---|
| **Shared profile brain files** (`SOUL` `USER` `AGENTS` `TOOLS` `CODE` `SECURITY` `BOOT` `MEMORY`) | no factory-specific rule leaks in (P25 isolation); one-line pointers only; no provenance sediment; every directive routed to the file that OWNS it | `tools/brain_metrics.py` (size reading, legs A/B/C, gates nothing); Lens S; the routing law in `AGENTS.md` §Memory | **No mechanical gate.** These files live in no repository, so no repo gate can read them. One bad line here binds every lane on the box. |
| **Factory skills** (`SKILL.md` + role files) | within the 500-line budget; no rule stated twice; current version, reloaded after compaction | `test_law_structure`, `test_law_coverage`, `test_duplicate_prose`, `test_ontology`, `docs/skill-version-exemptions.json`; Lens A/B/G | Skill-version staleness after compaction is **declared** (quality criterion L1) — I state the declaration surface here, not its coverage; I did not read the gate that consumes it in this pass. |
| **Process law** (`processes.md`, `docs/instruments/*.md`, `docs/methodology/*`, `best-practices.md`) | current rule only, never its biography; counts in prose match their definitions; every rule gated | `test_law_coverage`, `test_duplicate_prose`, `test_law_structure`, `test_docs_sync`; Lens A | **Hygiene has no law doc at all** — see G1, Class D. |
| **`ONTOLOGY.md`** | one concept = one name; banned synonyms unused | `test_ontology` (parses the ban table, so list and gate cannot drift) | The **naming patterns** (issue, place, decision record, score record) are declared in the table but only the *vocabulary* is gated, never the pattern. |

### Class B — Filesystem: the disk

| Surface | Clean means | Upheld today by | Gap |
|---|---|---|---|
| **`/tmp` scratch namespace** | no owned scratch older than `MAX_AGE_HOURS` (24); a declared-live path is never touched | `tools/hygiene.py` (`scratch_patterns_for(namespace)`, namespace = the repo directory name); `docs/hygiene-protected.json` (#153); gate `test_hygiene_namespace` | A foreign prefix is never globbed — correct — but that also means nothing here covers a directory created under a lane-chosen name. |
| **Repo working tree** | zero litter (`.bak` `.tmp` `.log` `.orig` — violation at any age); zero stranded dirty paths (older than the grace window, default 60 m); a run's own artifacts committed | `tools/hygiene.py` (`inspect_git_working_tree`, `--require-committed`); gate `test_hygiene_inflight` (#28, #38, #199, #201) | — |
| **Worktrees** | every registered tree reported with its hazard class; residue REPORTED, never removed | `tools/patrol_host_state.py` report leg, shipped `524f404` (2026-09-29); read that day: 34 trees, 33 scratch, 2 holding unreachable commits, 11 with uncommitted work, `removes: no` asserted structurally by a self-scan | The reaper is deliberately refused; a lane removes its OWN tree. That is a policy, not a gap — but it means the population is bounded only by the report. |
| **Build residue** (`__pycache__`, `.pytest_cache`, `.ruff_cache`, `.audit.lock`) | no accumulation | **nothing** | **G3.** pytest and ruff write an inner `.gitignore` containing `*`, so these directories are **self-ignoring**: invisible to `git status`, therefore invisible to hygiene's tree leg; excluded from `registry/kit.json` as transient; and hygiene's glob is `/tmp`-only. Present on disk at this instant: `.pytest_cache`, `.ruff_cache`, `TEMPLATE/.pytest_cache`, `tools/__pycache__`, `tests/__pycache__`, `.audit.lock`, `TEMPLATE/.audit.lock`. With 30+ worktrees each carrying its own caches, nobody reaps them. |
| **Stale directories created by us** | no directory we made survives its purpose | partially: worktrees (above); hygiene globs *paths*, and a directory is caught only if its name matches `/tmp/<namespace>-*` | **G6.** A directory outside that prefix and outside worktree registration is reported by no leg. |
| **Grouping and naming vs contents** | a file lives where its content belongs; its name says what it is | `ONTOLOGY.md` §Naming law (patterns only); `tools/kit_names.py` (a cross-TREE census: one name, different purposes, e.g. `test_ontology.py` = 5 trees / 4 purposes) | **G5.** No predicate answers "is this file in the folder its content belongs to". The name census answers a different question. |
| **`evidence/` and `reviews/` trees** | append-only history, labelled and superseded — never deleted ("looks stale is a hypothesis, never a verdict", Lens D) | Lens D; `test_rework` for the rework log | **G7.** Nothing mechanically marks an artifact superseded; the supersession lives in prose notices by hand (e.g. the dated `name-census-2026-09-25` beside `name-census-2026-09-27`). |
| **Host disk / box storage** | unexhausted | **boundary, not ours** — Gatus endpoint alerts are infra-factory's surface | Named so it is not silently absorbed. |

### Class C — Work state

| Surface | Clean means | Upheld today by | Gap |
|---|---|---|---|
| **Ledger** | append-only; nothing removed; a retirement NAMES a row; no shrink; monotonic sequence; one writer | `tools/ledger.py` (write path refuses removal and stale refs), `test_ledger_no_shrink`, `test_ledger_schema`, `test_single_writer`, `test_ledger_index`, `test_ledger.py`; Lens H | The most heavily gated object in the factory. Its exemption surfaces are the weak side (next row). |
| **Exemption / declaration surfaces** (25 JSON files over 15 families; 15 of them `ledger-*`) | an entry whose target is gone is a **stale debt**, reported | **partially**: each surface's own tool reads its own file | **G2.** No cross-sweep. `tools/hygiene.py`'s docstring names the class exactly — "the exemption surfaces, where an unmatched entry is a stale debt" — and then checks only its own declaration, and only for readability (its entries are deliberately a prevention surface, where unmatched is legal). |
| **Board (issues)** | board and ledger agree; every open issue has an intake row; every close row's observation is TRUE of the live board | `tests/test_board_intake_recorded.py`, `test_close_board_recorded.py` (predicates), `tools/patrol_host_state.py` (feeds them LIVE host state — "a green predicate with no live input is a gate that has never been asked a question") | WIP stagnation is a Lens M finding, not a gate. |
| **Pacemakers (cron)** | every periodic process has a live job (P28); prompts thin; namespaced per factory; no dead-text schedule | `test_cron_thinness`; `pacemaker.md`; namespacing law in `AGENTS.md` §Cron | A job whose target session is gone, or whose declared cadence and actual runs diverge, is a report today — no gate. |
| **Open questions** | no stranded question; `asked_at` age does the re-surfacing; no field written and never read | `docs/instruments/open-questions.md` §5.3 (stranded question, #189), §5.6 (ontology collapse) | — |
| **`evidence/insights.jsonl`** | every entry carries a status and a verify axis | `docs/instruments/insights.md`; `test_synthesize_insights` | Stale entries (status frozen mid-lifecycle) — declared as a workflow, not swept. |
| **`evidence/rework.md`** | every entry owes a `Prevented by` gate | `test_rework.py`; Process 2 | A gate removed later leaves the entry pointing at nothing — the dead-guard shape. |
| **`registry/` fleet state** | a snapshot states its instant; a fragment's provenance is knowable | `registry/state.json` carries `resolved_at` (read: `2026-09-29T14:07:33Z` — stale by construction, it is a snapshot); `test_registry`, `registry_attest` | Its fragments are read from `/tmp/oc-aa/...` — a Class B path living in `/tmp` under a namespace hygiene does not own. |

### Class D — Kit and distribution

| Surface | Clean means | Upheld today by | Gap |
|---|---|---|---|
| **TEMPLATE ↔ root pairs** | byte-for-byte, or the divergence is declared | `test_template_sync`, `test_docs_sync`, `kit_manifest --check` | — |
| **Kit manifest** | every shipped path has a class; `kit_version` is a digest over the manifest's own triples | `tools/kit_manifest.py` (138 files, 110 `standalone` / 17 `seed` / 11 `closure`) | — |
| **Member pins** | no UNDECLARED divergence from the pin | `tools/kit_pin.py`, `kit_census.py`, `kit-exemptions.json` (a peer's rule: porting an instrument means adding its exemption in the same change, or the audit reds) | — |
| **The hygiene instrument itself** | declared: a law doc with §2 declared set, a version identifier, a self-probe, an adoption census | **nothing** — it ships 4 kit rows (`TEMPLATE/tools/hygiene.py`, two gates, `TEMPLATE/docs/hygiene-protected.example.json`) and **no** `docs/instruments/hygiene.md` | **G1 (structural).** The six shipped law docs are kit, ledger, open-questions, pacemaker, review-rotation, template-instruments. Per `template-instruments.md` §1.1 — *completeness is declared, never derived* — a member cannot answer "is hygiene complete here?", and the instrument carries no declared set, no version id, no self-probe and no adoption census. |

### Class E — Runtime and harness

| Surface | Clean means | Upheld today by | Gap |
|---|---|---|---|
| **Context window / compaction** | the always-injected floor stays inside budget; a compacted session recovers its state without re-reading anything live | `tools/brain_metrics.py` (legs A/B/C), `docs/measurement-procedure.md` §5, pre-compaction flush into `session_context` + plan card | Leg C is supplied by hand (11 of 11 compaction events were manual) — a note pipeline that needs a clock has an event. |
| **Lanes / session bindings** | every declared lane exists, holds a valid distinct UUID4, no two share a session | `test_session_bindings`; Triage's roster sweep (pruned 11 phantom enrollments, 2026-09-14) | — |
| **Token economics** | no cache-busting timestamps, no frontier model on mechanical work | Lens T | A lens, not a gate. |
| **Secrets on three surfaces** | — | **DECIDED OFF**: owner order 2026-09-29 accepts a key in a private repo, a transcript or a host log; rotation is declined and not owed. What remains is output masking (`SECURITY.md` §Confidential File Protection) | Not a gap — a ruling. Listed so it is not re-filed. |

---

## 4. The gaps, ranked

| # | Gap | Class | Why it ranks here |
|---|---|---|---|
| **G1** | **The hygiene instrument is indeclared** — no `docs/instruments/hygiene.md` | D | Structural: it blocks the member leg entirely. Every other kit instrument has a law doc; this one ships code, two gates and an example, and a member cannot tell complete from partial. It is also the only gap whose fix is *entirely ours*. |
| **G2** | **No cross-sweep of exemption / declaration surfaces** | C | The class is already NAMED in shipped law (`hygiene.py`'s own docstring: "an unmatched entry is a stale debt") and nothing acts on it. 25 JSON files over 15 families, each read only by its own tool. Dead debt accumulates silently and every surface looks green. |
| **G3** | **Build residue is invisible to every sweep** | B | Verified mechanism: pytest and ruff write an inner `.gitignore` with `*`, so the directories are self-ignoring — absent from `git status`, excluded from the kit manifest, and outside hygiene's `/tmp` glob. Multiplied by 30+ worktrees. |
| **G4** | **The shared profile brain has no mechanical gate** | A | Highest blast radius per byte: one line there binds every lane on the box, and it lives in no repository, so no repo gate can read it. Its only defences are a periodic lens and a size reading. |
| **G5** | **No predicate for placement / naming-vs-content** | B | The owner's own bullet ("files grouped/regrouped in folders, proper naming consistent with the contents"). Partially lawed in `ONTOLOGY.md` (patterns) but gated only for vocabulary. |
| **G6** | **Stale directories outside the `/tmp` namespace and outside worktree registration** | B | A directory we created under a lane-chosen name is reported by no leg. |
| **G7** | **Evidence-artifact supersession is hand-maintained** | B | Prose notices only; nothing mechanically distinguishes current from superseded in `evidence/`. |

**A note on G3 and G6 together:** they are the same shape — *the instrument's population is defined by a
naming convention it owns, and anything we create outside that convention is unmeasured from every
direction.* #220 was exactly this, for worktrees, and the fix was a **report leg with `removes: no`**
rather than a widened glob. That precedent is the template for both.

---

## 5. Ownership split — what "I own the hygiene instrument" means

| Half | Lives where | Owned by |
|---|---|---|
| **The instrument** — the law doc, `hygiene.py` + its closure, its gates, the declaration example, the version identifier, the adoption census, the re-arm duty | `TEMPLATE/` (ships) + the root pair | this lane |
| **The instance** — `docs/hygiene-protected.json`, `--grace-minutes`, `--namespace`, its own litter policy, its own exemption surfaces | the member's own tree, never shipped | the member's own HQ |

This split is already the tool's design ("the grace window is declared by the caller … a property of
the factory's process, not of this tool"); what is missing is that it is nowhere **stated as law**,
which is G1. A member's declaration is data; our law is the predicate.

---

## 6. Open questions for the owner

**Q1 — Scope.** Does hygiene own the whole inventory above (all five classes), or Class B plus the
cross-surface sweep? *My recommendation: hygiene owns the **predicate class** — "is a declared state
findable, and is its claim true?" — for every class, while each surface's own instrument keeps its own
gates.* Otherwise we would build a second, competing gate for the ledger or the kit, and two
predicates over one population is the defect this factory files against.

**Q2 — First deliverable.** The missing law doc (`docs/instruments/hygiene.md`, closing G1), or the
exemption cross-sweep (a gate, closing G2)? *My recommendation: G1 first — it is ours alone, it is
the structural gap, and G2's sweep is one of the legs that law doc should declare.*

**Q3 — Build residue (G3).** Reap it, or declare it out of scope with a reason (a worktree's cache is
that worktree's, and it dies with the tree)? *My recommendation: declare it, and make the declaration
mechanical — a printed population, so "we chose not to reap it" can never read as "there is none".*

**Q4 — The shared profile brain (G4).** Is that surface ours to gate, or the harness's? It sits
outside every repository, so a gate over it would be the first instrument that reads a path no repo
owns.

---

## What now / next

- **In flight:** nothing committed. This file is the only write (`docs/projects/hygiene-surfaces.md`),
  and it is deliberately uncommitted until the owner rules on §6 — the tree also carries four
  peer-lane modifications (`tools/patrol_host_state.py`, `tests/test_ledger_claim_preflight.py` and
  their TEMPLATE pairs) that are not mine to touch.
- **Next step + owner:** the owner rules on Q1–Q4; then this lane writes the design card for
  whichever of G1/G2 is chosen. Owner-gated by rule 10 — no implementation before approval.
- **Blocked on the owner:** Q1 (scope) is the one that changes what the other three mean.
