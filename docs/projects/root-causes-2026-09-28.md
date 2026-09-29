# Root causes — the defect population of 2026-09-28

**Predicate:** three independent defect surfaces, each read at a stated instant, classified by the
*mechanism* a defect breaks rather than by the component it lives in.

| Surface | Population | Read |
|---|---|---|
| Open issues | **34** (`gh issue list --state open`) | 2026-09-28T23:5xZ |
| Member-experience review | **13** confirmed findings (M1–M13) | committed `db07847` |
| Instrument survey gaps | **5** (§3.1–§3.5) | `evidence/instrument-survey-2026-09-27.md` |

The three surfaces were produced independently — an issue tracker, a two-subagent adoption review,
and a census sweep — and their **root causes overlap almost completely**, which is the finding: the
fleet is not generating 52 unrelated defects. It is generating five shapes, repeatedly.

---

## 1. The five root causes

Classification was mechanical over the 34 open issues (title + body, pattern-matched on the
mechanism each breaks; 8 issues match **two or three** roots, which is why they resist a one-file
fix):

| Root cause | Issues | Shape |
|---|---|---|
| **RC1 — the population is ENUMERATED, never derived** | 11 | a mechanism's scope is a hand-written list, fixed when the artifact was created |
| **RC2 — the reading is taken over MOVING state** | 9 | a measurement over a working tree, live data or uncommitted bytes |
| **RC3 — one fact, TWO HOMES** | 5 | a declaration and its consumer live apart; one moves, the other does not |
| **RC4 — a duty with NO SURFACE, NO TRIGGER, NO READER** | 6 | a clause states an obligation and nothing can receive, fire or read it |
| **RC5 — the CLAIM is broader than the MEASUREMENT** | 4 (+8 multi-shape) | the text asserts a property the mechanism measures only in part |

### RC1 — Enumerated, never derived (the largest, 11 of 34)

The sharpest measured instance is the fleet's **own law corpus**:

```
enumerated law corpus (LAW_GLOBS)      14 files
docs/instruments/*.md                   7 files   in corpus?  NO
TEMPLATE/docs/instruments/*.md          6 files   in corpus?  NO
§ occurrences in those 13 files       680
cross-document citations               22
```

`test_citation_clause_titles.py:50-56` states its corpus as **five globs**, written before
`docs/instruments/` existed. Every instrument law doc — the fleet's newest and largest class of law,
carrying 680 section references — sits **outside every law-reading gate**:

| Gate | Its declared scope | Covers `docs/instruments/`? |
|---|---|---|
| `test_citation_clause_titles` | `LAW_GLOBS` — 5 globs | **no** |
| `test_law_structure` | `skills/*/SKILL.md`, `TEMPLATE/SKILL.md.tmpl` | **no** |
| `test_duplicate_prose` | `skills/*/SKILL.md` | **no** |
| `test_docs_sync` | walks `TEMPLATE/docs/**` only | one direction only (#37) |
| Lens A check 5 (counts) | roles, processes, `SKILL.md` | **no** — fixed 2026-09-28 |
| `test_binding_mechanism_exists` | the harness binding | **no** (#48) |

### The decisive test

Injected a citation that resolves **nowhere** (`template-instruments.md` §99.99 — a section that does
not exist) into `docs/instruments/kit.md`, then ran the gate that exists precisely to catch
unresolvable citations:

```
citation-clause-titles gate passed — 28 citation(s), 21 exemption(s), 0 problem(s)
gate rc=0
```

**A law doc can carry a citation to a section that does not exist, and the check built for that class
is green** — because the doc is in neither of the gate's two populations: not in `SCOPE_DIRS` (where
it looks for citations) and not in `LAW_GLOBS` (what it resolves them against). It is **double-blind**.
The file was restored immediately; `git diff` empty.

The same shape elsewhere: `gate_registry` (**71** hand-declared entries), `PAIRS` (**58**),
`gates.json` (**48**), #219 (registration by presence), #214 (a normaliser missing the hyphen case),
#75 (the close leg has no detector), #162 (the gate assumes one repo root).

**And the fleet already knows the rule.** Frame §1.4:

> *"Derive membership from what the executable LOADS … Let the manifest supply each path's CLASS,
> never its MEMBERSHIP."*

It landed that for **declared file sets** and never applied it to **the gates' own populations**.
`registry/kit.json` is **136 entries, derived from the tree** — the one component that does this —
and it is the component that does not exhibit RC1.

### RC2 — Readings over moving state (9 of 34)

The manifest is generated from the **working tree** (#185), so a member's pin is compared against a
reference no reader can re-derive. The single-writer guard is read-time only and never refreshes its
ref (#221); its lock is per-worktree, so two checkouts mint the same row number (#222). A gate
cannot tell a shallow checkout from a fabricated sha (#224). A reverse probe uses a **live** ledger
row as its fixture, so lawfully repairing that row REDs the gate (#225). 37 worktrees sit outside
the cleanliness population, one holding a commit no remote carries (#220). A served page stayed one
revision stale for 8 minutes and no trigger re-pushed it (#207). A RED gate did not stop a commit
(#197).

Frame §7.3 (*regenerate at the commit*) and §7.5 (*the standard is committed; a live subject names
its axis*) landed today and close this class **for the surfaces that cite them** — the pattern is
known and not yet fleet-wide.

**Live specimen, present in the shared tree at this instant.** A peer's **uncommitted** edit reverts
the landed scope citation in `docs/instruments/template-instruments.md`
(commit `ebd8d6b`, *"criterion 7's Lens A citation carries its scope"*). Measured:

```
kit_manifest.py --check   rc=1   DRIFTED  TEMPLATE/docs/instruments/template-instruments.md
                                 DRIFTED  TEMPLATE/docs/review-lenses.md
test_docs_sync.py         rc=0   (both halves reverted together, so the pair is still identical)
```

Landed law can be reverted in the working tree with **the pair gate green**, because that gate reads
the working tree and the halves agree there. Only the manifest — which records the **committed**
digest — catches it. That is the remedy of RC2 demonstrated working in one gate and blind in the one
beside it: the same §7.6 shape, in the law that states §7.6.

**A second live specimen, in two directions — only one of them published.** I ran `git commit --amend`
intending my own commit, and it amended **a peer's** instead, because HEAD moved between the moment I
staged my file and the moment the amend executed (a lane committed in that window). That commit,
`bbf7127` (00:13:49Z, **unpushed** — a fresh clone cannot resolve it), was never published; the peer's
commit was restored exactly from the reflog and nothing was lost. The same window produced the
**published** specimen in the opposite direction, and it is the one a reader can check: at 00:09:47Z a
peer ran `--amend` intending its own commit `44da237` while HEAD had moved to my `b5124b8` ninety
seconds earlier — and the result, **`958e344` on `origin/main`**, carries my 202-line file at the very
same blob as my own commit (`5e6b01b9822a0b04`), with `git diff --stat b5124b8 958e344` showing the
peer's own file and nothing else. My work was published 15 lines short of finished, under a commit
titled about ledger exemptions and a trailer naming a lane that did not write it. Nothing was lost
(additive-only), and my own commit supersedes it.

The mechanism is neither of the two first filed, and both halves matter. `--amend` inherits **the
amended commit's TREE as its base**, so a correctly-scoped pathspec still cannot scope a *base*: the
pathspec bounds your **change** and never your **base**, and the base is whatever commit HEAD points
at when the verb runs. Measured here (git 2.43.0): with a peer's file staged beside mine, the pathspec
**was honoured** — the amended commit excluded it and the peer's version stayed staged — so the hazard
is the BASE TREE, not the verb, and that is why "name your paths at the commit" (#47), which works for
`git commit`, cannot protect an amend. The corrective is a same-command check of the subject —
`MINE=$(git rev-parse HEAD); [ "$MINE" = "$(git rev-parse <expected>)" ] && git commit --amend ...` —
since the subject is read at one instant and written at another. Same defect as #222 (a lock that is
per-worktree) and #221 (a guard that never refreshes its ref), reproduced by hand; filed as #228.

### RC3 — One fact, two homes (5 of 34)

The topic-name feed is **a copy of the declaration** and render takes no topics input (#196). The
questions register has two homes in two repos, and the copy that serves owner taps is measured by no
surface (#188). A ruling posted as a board comment leaves **no ledger row**, and no reader asks for
one (#223 — 8 instances in one session). A dispatch row is not coupled to a delivery (#49). A
withdrawn claim is indistinguishable from a live one — the ledger has no claim-release event
(#210). A dropped row's reason has no field to live in (#218). Foreign instrument coupling (#85).

### RC4 — A duty with no surface, no trigger, no reader (6 of 34)

A lane can sit driverless for ~48 h with every dispatch delivered — **no leg asks whether a driver
exists** (#133). Ten crons run their own work with no session wake (#118). The template prescribes a
profile skill symlink with **no upholding mechanism** (#79). The close leg has no detector in either
direction (#75). §6 declares a conversion automatic and **no trigger carries it** (#67). No
sanctioned repair exists for a post-gate ledger omission (#52).

From the member review, the same shape: O1 names a declaration surface that is **this repo's**
record (M5); O5 tells a member to *"state a decision"* into **nothing** (M9); O2's third leg
**has no delivery route to the donor** (M12) — and O2 admits it in its own words:

> *"The third leg is the one with **no automatic owner** and is therefore stated here rather than
> assumed."*

### RC5 — The claim is broader than the measurement (4 + 8 multi-shape)

`FALLBACK_DEFAULT_SEC = 120.0` is described as *"the largest declared budget rather than a round
number"* — it is a round number, **9.6×** the largest declared entry in the file it names, and the
shipped suite runs on it (#212, #208). A pickaxe search is used to date an introducing commit, but it
counts **occurrences, not changes** (#77). `kit_surfaces` S1 normalises underscores but not hyphens,
so a hyphenated tool never matches its own gate and drives the instrument's FAIL (#214). A count leg
asserts a number while its own table lists more rows (#144).

This is the class that produced today's most expensive rework: the §1.5 census count (**3 → 1 → 0 in
one evening**), §6.1's *120 of 120*, §7.6's *12 declared surfaces* invalidated by the very ruling it
cited, and three stale figures in `review-rotation.md` §7 — **in the section carrying the sentence
forbidding them**.

---

## 2. The unification

RC1 and RC5 are **one defect seen from two ends**:

- **RC1** — the population is narrower than the claim, silently.
- **RC5** — the claim is broader than the measurement, silently.

In both, the gap between *"what this mechanism says it covers"* and *"what it actually covers"* is
**itself never measured**. No gate asserts *claim = population*. Every other root cause is an
instance of that gap landing somewhere specific.

RC2 (moving state) and RC3 (two homes) are the same gap over **time** and over **location**: a fact
whose identity depends on more than one instant or more than one path.

---

## 3. The closure plan

Ranked by leverage — each entry states its root cause, its owner, and its **acceptance test**, because
a repair without a test is RC4 again.

| # | Repair | RC | Owner | Acceptance |
|---|---|---|---|---|
| **1** | **Declare the law corpus ONCE, derive it from a declared root, and gate coverage.** Replace the five hand-written `LAW_GLOBS` with a derived predicate over declared law roots; assert every `§` citation in every law doc resolves. | RC1+RC5 | mine (frame §1.4 generalised) | a new law doc under `docs/instruments/` is covered **without editing any gate** — proven by adding a file and re-running green |
| **2** | **Every mechanism publishes its scope, and a gate asserts the scope covers its class.** One registry: each class of artifact → the gates that cover it → a gate that REDs on an uncovered class. | RC1+RC5 | mine + HQ (member-binding half) | adding a new artifact class with no covering gate REDs by name |
| **3** | **Ship the "adopt the kit" document.** Chair: the on-ramp is a *creation* procedure, 3 of its links do not resolve, and it uses two coordinate systems. | RC4 | mine | a member reading only shipped bytes can reach a declared state without asking |
| **4** | **Give every obligation surface + trigger + reader.** O1's declaration surface, O5's decision surface, O2's donor notification — each names where it is written and what fires it. | RC4 | mine (§5.3, §9) + HQ (schema) | each clause names a surface that exists and a trigger that fires |
| **5** | **Commit-anchor every reading; a live subject names its axis.** Apply §7.3/§7.5 to the manifest generator, the single-writer guard, the census and every probe fixture. | RC2 | mine + the tools' owners | no reading differs between the working tree and the commit — or its artifact states the axis |
| **6** | **One home per fact, and a reader.** Retire the topic-feed copy, couple a dispatch row to its delivery, give the ledger a claim-release event, give a dropped row a reason field. | RC3 | HQ (these are its surfaces) | a fact read from a copy is RED; the home is the only readable source |

**Sequencing.** #1 and #2 are the leverage — they make every *future* instance of RC1/RC5 visible at
the moment it is created, which is the only way to stop the class rather than clear the backlog. #3–#6
are the specific instances already measured.

**What this plan does not do.** It does not clear the 34 issues. It makes their *class* detectable, so
the 35th is caught by a gate rather than by a lane reading a diff.

---

## 4. Verification

Every figure above is reproducible:

```bash
gh issue list --state open --limit 60 --json number,title,body    # 34 issues
python3 - <<'PY'   # the law corpus vs docs/instruments/
from pathlib import Path
LAW=("skills/*/SKILL.md","TEMPLATE/*.tmpl","TEMPLATE/*.md","TEMPLATE/roles/*.md","ONTOLOGY.md")
R=Path('.')
corpus={str(p) for g in LAW for p in R.glob(g)}
inst=[str(p) for p in (R/'docs/instruments').glob('*.md')]
print(len(corpus), len(inst), any(x in corpus for x in inst))   # 14 7 False
PY
python3 tools/kit_surfaces.py                                     # the census's own FAIL
python3 tools/hygiene.py --audit                                  # rc=0, 6 advisories
```

## 5. Status of this analysis' own counts

This document is **itself** subject to §1.5. Every figure carries its population above; none is
repeated without one. If a reader finds a count here whose predicate cannot be reconstructed, that
is a defect in this file and belongs in the same class as the ones it describes.
