# PROPOSAL 07 — the kit's vocabulary: what to rename, what to fix, what to leave alone

**Status:** design input, not law. Produced by a read-only subagent review of the
terminology this project coined, and **verified against the tree** before anything here
was repeated. Every count states its predicate.

**Instant:** 2026-09-26T21:30Z. **Population:** tracked files under
`/root/agent-factories`.

---

## 0. Why this is a proposal and not a rename

Three of the four class names in `registry/kit.json` were coined **this week**
(`shared` / `closure` / `factory`, landed by `kit_manifest.py`). Renaming them is cheap
now and expensive after members vendor a pin — and the pin is exactly the mechanism that
freezes a name into five trees. So the window is open for a few days, not months.

And the corpus already shows what an unfinished rename costs: the `twin` → `copy`
canonisation landed this week and left the term **live in code**, then denied it had
(§1 below). That is the failure mode to avoid, not the vocabulary to argue about.

---

## 1. Two contradictions in `ONTOLOGY.md` that I introduced — verified, not inferred

`ONTOLOGY.md` is the canonical vocabulary: *"Every term below is the only word allowed for
that concept … Anything in the Not column is a defect to fix, not a synonym to tolerate."*
Two rows I added this session break it.

### 1.1 `surface` — the canonical table and my own row disagree

| line | text |
|---|---|
| `ONTOLOGY.md:32` | `surface` = **"The chat product a factory runs on"** — banned synonyms: *chat, channel, platform, messenger* |
| `ONTOLOGY.md:460` (added by me, task 11) | *"Ownership answers WHO may write **a surface** (§11) — it is authority over **a surface**"* |

Line 460 uses `surface` in §11's sense — a durable state file with one writer — which the
table at line 32 says it does **not** mean. §11 is literally titled *"State — every surface
has one writer"* and enumerates `evidence/ledger.jsonl`, `evidence/rework.md`,
`evidence/scores/<date>.md` and the issue board. `tools/kit_surfaces.py` adds a **third**
sense: *"THE FOUR SURFACES: S1 gate exercises the tool, S2 BOOTSTRAP.md installs it, S3 law
corpus names it, S4 registry/kit.json carries it."*

Predicate for the spread, over tracked files, `grep -P '\bsurfaces?\b'`: **1,218 hits in 82
files**, splitting roughly 64 chat / 186 state-file / 22 audit-facet / ~946 ordinary
English. A model meeting bare `surface` cannot tell which of four things it is, and the
canonical row actively misdirects it toward the rarest sense.

### 1.2 `twin` — my row claims a clean-up the code does not have

`ONTOLOGY.md:459` (mine) states that after the split, `twin` *"names a different object in
every live use"*. **Falsified by reading the files:**

```
tools/hooks/pre-commit:328   for staged_side, twin in one_sided(pairs, staged):
tools/hooks/pre-commit:104   twin:    {twin}   (not staged)
tools/hooks/pre-commit:112   git add {twin}
tools/hooks/pre-commit:21    …does this commit name one side without its twin?
tests/test_template_sync.py:64      The twins are the same file in two trees
tests/test_commit_pair_hook.py:27   naming the staged path AND its twin
tests/test_ontology.py:163          drift from its twin
tools/ledger.py:1049       twin = next((w for w in added if without_n(w) == …))
```

Ten uses in `pre-commit` alone, including a **variable** and **user-facing remedy text**.
So the term is live in the code that enforces the pair rule, and the ontology denies it.
`tools/ledger.py:1049` is a *fourth* sense — a duplicate ledger row without an ordinal.

**This is the finding worth the most:** the ontology is the file that is supposed to settle
vocabulary, and it now contains a claim about the code that the code contradicts. A reader
who trusts line 459 will not look for `twin` in `pre-commit`.

---

## 2. The renames — ordered by evidence strength

### 2.1 `factory` (class) → `seed` — strongest case; the code already says it

`tools/kit_manifest.py`, which **owns** the class, already uses `seed` to explain it:

```
kit_manifest.py:149   factory -- a seed the factory instantiates under a DIFFERENT name
kit_manifest.py:185   The seeds. Declared per path rather than matched on suffix, so that
                      a file named … cannot force a comparison on a naming accident
kit_manifest.py:260   `factory` = a seed the factory instantiates under a different name,
                      never compared byte-for-byte
```

So this is not an invention; it is **finishing a thought the code already has**, and
promoting the word the instrument uses for itself into the name of its class.

Why the current name is worse than any alternative: it names a file class after **the whole
system that hosts it**. `class: factory` on `registry/kit.example.json` asks a reader
whether this is factory-*level scope*, factory-*owned*, or a factory *seed* — and the
answer is in 200 lines of docstring, not in the word.

Collision check, stated with its predicate. `grep -rn '\bseed\b'` over tracked files: 12
hits, but they are **test-local fixture variables** (`tests/test_publish.py:326
seed = init_work(root / "seed", remote)`; `test_patrol_host_state.py:1571`) and the
manifest's own word for this class. No hit is corpus vocabulary for something else, so the
name is free where it matters.

### 2.2 `closure` (class) → `support` — the word names a different concept

`closure` is a programming term for *a function plus the environment it captured*. What the
class holds is **the set of files a tool needs in order to run** — a dependency list, not a
capture. The collision is not hypothetical: this very document, and the review it came
from, discuss `ledger.py`'s *"lazy tier"* and *"import closure"* alongside ordinary English
*"closure"* and *"close the work unit"* (work-unit closure is already a term of art here —
`ONTOLOGY.md` defines `settlement` and `close`).

`support` states what it is: a module that supports an executable or a gate, with no entry
point of its own. Its absence means a broken dependency (`ModuleNotFoundError`, the `#137`
defect) — which is exactly the property the class exists to protect.

### 2.3 `shared` (class) → `standalone` — removes a real ambiguity

`shared` currently means "shipped byte-identical, absence means the factory is behind". But
on this box `shared` already means **the shared brain files** (`AGENTS.md` is shared by
every lane on the ops profile) and **shared cgroups**. `standalone` names the actual
property — it runs by itself, no closure — and it is the word `kit_manifest.py` already
uses in its own comments.

### 2.4 `twin` → `mirror`, and finish the job

Given §1.2, the choice is not "rename `twin`" — it is **pick one and make the file true**.
`mirror` states the operational property (a byte-for-byte reflection across two trees) and
does not collide with the Telegram migrated-group sense or the git patch-id sense. The
blast radius is 284 hits across ~30 files, and **`pre-commit`'s variable and remedy text
must move together**, because a rename that misses a variable is how this session broke
four gates once already.

### 2.5 `pair` (in the gate registry) → `registration`

`pair` is overloaded: the byte-identity relation (`PAIRS`, `test_template_sync.py`) **and**
the association of a gate with its budget/runner/registry entry (`gate_registry.py`, ~114
hits). Reserving `pair`/`mirror` for two-element equality and calling the other thing
`registration` removes the collision in both directions, and "a gate is registered" is what
the code does.

### 2.6 `surface` (in `kit_surfaces.py`) → `facet`, and the tool with it

S1–S4 are **evaluation facets** of instrument adoption — not chat products, not state
files. Renaming the module `kit_facets.py` and the term `facet` frees `surface` for §11's
state-file sense, which is the one the law actually needs. Then `ONTOLOGY.md:32` can keep
`surface` for chat, and §11 gets its own word.

### 2.7 `delivery leg` → `transport`

`leg` carries ~2,190 hits in this corpus and predominantly means a **patrol sub-check**
(`patrol_host_state.py`'s duty-receipt leg, notify-receipt leg). `kit_deliver.py` is a
transport mechanism, not a leg of anything, and calling it a leg makes the two nearest
concepts sound like one.

### 2.8 `full set` → `instrument bundle`

`full set` is generic English with no local meaning; "the nine parts" reads like a list
rather than a bounded unit. `bundle` names the thing that adoption either has or lacks.

---

## 3. Leave these alone — verified, and the reason matters

| term | verdict |
|---|---|
| `pin`, `vendored pin` | **KEEP.** It names a fixed reference point against which a tree is judged, which is exactly what it is. Short, distinctive, no competing sense in this corpus. Renaming it would be churn for appearance's sake. |
| `receipt` | **KEEP.** The load-bearing term of the whole law surface — same-turn tool output that proves a claim. `ONTOLOGY.md` defines it and §8 enforces it. |
| `duty`, `round` | **KEEP.** `duty` separates a scheduled obligation from a dispatched task; `round` names one execution cycle of it. Both are needed by the receipt law and neither collides. |
| `boundary`, `invariant` | **KEEP.** Standard systems words, used precisely: `boundary` is where enforcement begins (`tests/ledger_boundary.py`), `invariant` is what is enforced from there. |
| `gate`, `excused`, `settlement` | **KEEP.** Established, defined, and each has exactly one sense in this corpus. |

---

## 4. The structural gap — one taxonomy, not eight renames

The individual renames are worth less than this part. The corpus has **four anatomical
parts** of an instrument and uses **four different phrases for each**:

| what it is | phrases in use |
|---|---|
| the runnable CLI | `tool`, `script`, `executable`, `class shared` |
| the modules it needs | `closure`, `import closure`, `class closure`, `what travels with the tool` |
| the gates that prove it works | `gate set`, `gates`, `gate pairing`, `paired test files` |
| the files the factory owns | `factory data`, `data surfaces`, `declaration surfaces`, `class factory` |

So propose the names **as a set**, because the value is in the mapping being 1:1:

```
instrument
├── executable     tools/ledger.py            class: standalone
├── support        tools/field_predicate.py   class: support
├── gate suite     tests/test_ledger.py       class: standalone
└── declaration    registry/kit.example.json  class: seed
```

Four anatomical roles, three distribution classes, one word each. That is what makes a
model's reading locally decodable: `class: support` needs no surrounding context, and
`declaration` no longer competes with `surface`.

---

## 5. What I would do with this

1. **Fix §1's two contradictions now.** They are in the file whose job is to settle
   vocabulary, and one of them is a false claim about the code. That is not a naming
   preference; it is the ontology lying.
2. **Take the three class renames** (`seed`, `support`, `standalone`) **before members
   vendor a pin** — mechanical, ~230 hits, and `kit_manifest.py` already speaks two of the
   three.
3. **Finish or retract the `twin` claim**, whichever way the term goes. An ontology row
   that denies live usage is worse than no row.
4. **Do not rename `pin`, `receipt`, `duty`, `round`, `boundary`, `invariant`.**
5. The `surface` split (§1.1 + §2.6) is the biggest single win for LLM efficiency, because
   1,218 hits currently require context to disambiguate — but it touches §11's title and
   the law corpus, so it is the one that needs its own work unit rather than a sweep.

**Bounds, stated.** The subagent read the corpus; I verified §1, §2.1, §2.4 and the class
counts against the tree this turn. The collision counts are the agent's predicates, which I
spot-checked for `seed` and `twin` and did not independently re-derive for `surface`, `leg`
or `pair`. No file was modified in producing this document.
