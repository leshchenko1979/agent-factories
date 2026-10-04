# Lens B — LLM Efficiency, No-Op Pruning & Responsibility Creep

**Cycle:** 20260927-c1 · **Repo under review:** `/root/agent-factories` · **Auditor:** isolated adversarial sub-agent (read-only).

**Surfaces read** (per `CORPUS.md` mapping for lens B): `ONTOLOGY.md`, `README.md`,
`skills/meta-factory/{SKILL.md,state.md,verdicts-and-claims.md}`, `docs/*.md`,
`docs/methodology/*.md`, `docs/instruments/*.md`, and `TEMPLATE/roles/*.md` (the only role
files that exist — the brief's `roles/*.md` maps here). All instrument symlinks
(`skills/meta-factory/<instrument>.md`) were resolved and their targets diffed.

**Method.** Every count below was *read*, never estimated: `wc -lwc`, `awk 'length>N'`,
`grep -c/-n/-o`, `md5sum`, `diff`, `readlink`. Token figures are a **proxy** at the factory's
own declared ratio of 3.5 chars/token (`tools/brain_metrics.py:26`) and are labelled as such.

---

## F1 — HIGH — `state.md` is a wall of unbroken 1000–2257-char paragraphs (cognitive load / token weight)

**File locators:** `skills/meta-factory/state.md:144`, `:54`, `:26`, `:150`, `:79`, `:186`, `:58`, `:24`, `:56`

**Verbatim quote** (`skills/meta-factory/state.md:144`, first 320 of **2,257** chars on ONE line):

> `**A gate whose only exits are barred is a stop with no andon cord.** A gate that reads commit *subjects* across a range can be violated by a commit already PUSHED, and then no repair is available: the commit is immutable, a revert does not remove the offending subject from the range, and re-anchoring the marker past th…`

**Defect analysis.** `state.md` is not optional reading: its own header says
*"Load it before writing any state row or touching a surface's writer"* (state.md:9). Yet it
packs its law into **9 lines longer than 1,000 characters** (measured: lines 24, 26, 54, 56,
58, 79, 144, 150, 186 = 12,777 chars total; the longest is 2,257). Those 9 lines are ~3,650
proxy tokens of unbroken prose with no sub-heading, bullet, or table between them — the exact
opposite of the "Progressive Disclosure" target. An LLM (or a human) gets zero structural
anchors and must hold a ~640-token run-on in working memory to extract a single rule. The
whole file is 31,856 B ≈ **9,100 proxy tokens** for one clause file. The mega-paragraphs also
carry incident biography inline ("four fragments carried an `attested_at` four days stale",
`state.md:26`) that belongs in `evidence/rework.md`, not in the always-reloaded clause tail.

**Actionable remediation.** Split each mega-paragraph into a `###` clause heading plus a 3–6
item bullet list (one rule per bullet). Move the incident narratives to `evidence/rework.md`
and leave a `(#NNN)` pointer. This is a mechanical reformat — no rule changes — and cuts the
read cost materially while giving the reader anchors.

---

## F2 — HIGH — Cache Test: `ONTOLOGY.md` embeds a self-census that is unreproducible and already contradicted

**File locator:** `ONTOLOGY.md:530`

**Verbatim quote:**

> `` `add-on` is canonical (60 uses over 30 law files) and its banned synonyms are `plugin`, `extension`, `module`, `adapter`. ``

**Defect analysis.** This is a derived count hard-coded into law. The Cache Test forbids
exactly this: a number the reader can obtain by `grep` should not be cached in a document,
because it drifts. Measured fresh: `add-on` occurs **60** times across **14** `.md`/`.tmpl`
files; **91** times across **24** git-tracked files; in **34** files when `.git` is excluded.
No measurement yields "30 law files" — the stated figure matches no population on disk. It is
also contradicted by a *second* embedded census in the same repo:
`docs/projects/template-instruments.md:118` states `add-on` **73** · `addon` **65**. Two law
documents cache two different counts of the same string.

**Actionable remediation.** Delete the parenthetical count; state the rule positively
("*`add-on` is canonical; `plugin`/`extension`/`module`/`adapter` are banned*"). If a count is
wanted, assert it with a test (there is already `tests/test_ontology.py`) so it cannot drift
silently.

---

## F3 — HIGH — Cache Test: `README.md` carries 8 raw session UUIDs, one of them *measured dead by the factory itself*

**File locators:** `README.md:94-97` (own lanes) and `README.md:121-124` (member HQ lanes)

**Verbatim quote** (`README.md:121`):

> `| OpenCrabs dev | `d72bd52d-42aa-4dbd-ac99-5b5300770019` | Crabs Kanban Board, topic `OC DEV HQ` |`

**Defect analysis.** The factory's own law says a raw session uuid *"rots the moment the topic
it names is re-opened"* and must be resolved live (`skills/meta-factory/SKILL.md` §5,
board #254). `tests/test_law_no_raw_session_uuid.py` exists to enforce it — **but its
population is "every LAW FILE"** (its docstring: `skills/*/SKILL.md`, `SKILL.md.tmpl`), so
`README.md` is outside it and these 8 uuids are ungated. Worse, the uuid on `README.md:121`
is the very one the gate's docstring records as **dead**: *"Measured 2026-09-30: … named
`d72bd52d-42aa-4dbd-ac99-5b5300770019` for OpenCrabs HQ, and that id carried ZERO bindings"*
(`tests/test_law_no_raw_session_uuid.py:6-7`). The #254 fix cleaned `SKILL.md` §5 and left
the identical stale id in the README a reader is told to read first. `README.md:94-97` also
duplicates `SKILL.md:112-116`'s roster with a *different* read instant ("live as of
2026-09-11 14:20Z" vs "read back … on 2026-09-18 12:20Z") — two freshness claims for one
population.

**Actionable remediation.** Replace both tables' uuid columns with the topic/role **name**
plus the resolution command (`python3 tools/registry.py resolve`), and drop the "All four are
live as of …" sentence. If a printed uuid is genuinely wanted, add `README.md` to the gate's
population or declare the debt in `docs/law-uuid-exemptions.json` (the file currently declares
only the five `SKILL.md` §3 ids).

---

## F4 — MEDIUM-HIGH — Duplication-driven drift: the `required_tools` set differs between two law surfaces

**File locators:** `docs/best-practices.md:643` vs `skills/meta-factory/SKILL.md:325` (and `docs/methodology/04-harness-binding.md:162-166`)

**Verbatim quotes:**

> `docs/best-practices.md:643` — ``- `required_tools`: Explicitly pre-activate critical operational tools (`session_notify`, `session_search`, `bash`, `read_file`, `telegram_send`) …``

> `skills/meta-factory/SKILL.md:325` — ``> and `required_tools` (pre-activating `session_notify`, `session_search`, `bash`, `read_file`, `edit_file`, `write_file`)``

**Defect analysis.** The two surfaces prescribe **different** tool sets for the same
compaction-manifest duty: `best-practices.md` pre-activates `telegram_send`; `SKILL.md` (and
the shipped `TEMPLATE/SKILL.md.tmpl:264` and `04-harness-binding.md:162-166`) pre-activate
`edit_file` + `write_file` instead. This is the responsibility-creep/no-op failure in its purest
form: one directive copied into three places, and the copies have already drifted. A lane that
follows the rulebook loads a set that omits the two file-writing tools; a lane that follows the
skill loads a set that omits `telegram_send`. Either way one surface is wrong.

**Actionable remediation.** Keep the `required_tools` list in ONE place (the harness binding
`04-harness-binding.md` §9.2, which owns the manifest mechanics) and have `best-practices.md`
and `SKILL.md` cite it by pointer instead of restating the list.

---

## F5 — MEDIUM — Responsibility creep: the git-commit clause is byte-identical in three role cards

**File locators:** `TEMPLATE/roles/worker.md:30`, `TEMPLATE/roles/triage.md:48`, `TEMPLATE/roles/carrier.md:50`

**Verbatim quote** (identical on all three lines — verified `md5sum` `a79e9e68a97e947c188779f8a4bbf720` on each):

> `| **Name your paths at the commit** | `git commit -m <msg> -- <paths>`. A bare `git commit` takes the whole index, including a peer's staged work. Everything after `--` is a path, so `-m` and its message come first |`

**Defect analysis.** P2 in the rulebook states the governing law: *"Split a large procedure by
**role**, and make each session load exactly one role file … Prevents: every lane loading
3 000 tokens of someone else's procedure"* (`docs/best-practices.md:43-55`). The identical
git-mechanics row is duplicated in **three** role cards (plus `skills/meta-factory/SKILL.md:219`,
`TEMPLATE/SKILL.md.tmpl:166` and `TEMPLATE/AGENTS.md.tmpl:65` = **6 copies** of one rule). Each
card pays the tokens and each copy is a separate drift surface — the exact hazard F4 already
demonstrated.

**Actionable remediation.** Keep the clause once, in the shared process law / repo `AGENTS.md`
every lane loads; delete the row from the three role cards. A role card should name *what this
role does*, not re-teach git.

---

## F6 — MEDIUM — Responsibility creep: the Triage card is 2.2× the other role cards, carrying law that lives elsewhere

**File locators:** `TEMPLATE/roles/triage.md` (whole file), quote at `triage.md:110` (rework-entry table) and `triage.md:18-95` (watchdog sweep)

**Verbatim quote** (`triage.md:110`, the rework-entry column table):

> `| **Date** | When the defect was found — not when it was introduced, which is often unknown and guessing turns the log into fiction |`

**Defect analysis.** Measured card sizes: `triage.md` **7,440 B / 133 lines**, versus
`hq.md` 3,307 B, `worker.md` 2,495 B, `carrier.md` 2,317 B — Triage is **2.2× the mean** and
**3×** the worker card. It carries (a) the full six-column `evidence/rework.md` entry
specification, which is already the law of `skills/meta-factory/SKILL.md` §12 ("The rework log
is the other half of the ledger … three properties make the log worth keeping"), and (b) the
detailed `stall-census` / CLAIMED-BUT-SILENT / OWED patrol semantics that belong to the patrol
runner, not to a routing card. A Triage lane loads ~2,126 proxy tokens, much of it someone
else's procedure — the P2 anti-pattern.

**Actionable remediation.** Reduce the card to Triage's own acts (intake, route, assign, close,
record rework) and replace the embedded tables with pointers to §12 of the skill and to the
patrol's own doc.

---

## F7 — MEDIUM — Cache Test: `hygiene.md` hard-codes a 6-row adoption census derived from registry state

**File locator:** `docs/instruments/hygiene.md:369-380`

**Verbatim quote** (`hygiene.md:376`):

> ``| `ai-antispam` | no |``

**Defect analysis.** §9 "Adoption census" embeds a six-row table of which member factories
declare the instrument — data whose source is stated in the same block: *"Predicate: the
`instruments` map on each `registry/factories/<slug>.json` fragment"* (`hygiene.md:369`). That
is a value derivable by CLI inspection, cached into law, and it drifts the moment any fragment
changes. It is the same class as F2, in a second law file. `docs/instruments/hygiene.md` also
repeats its pair/reload-path facts twice (header "Class: `standalone` …" block and §10).

**Actionable remediation.** Replace the table with the census command (`tools/instrument_census.py`,
which exists) and a dated pointer to the run that produced it; keep law, drop the snapshot.

---

## F8 — LOW-MEDIUM — Cache Test / stat drift: the "778 compactions / >93% retention" figure is restated in ≥6 places

**File locators:** `docs/best-practices.md:438`, `:635`, `:646`; `docs/methodology/04-harness-binding.md:140`, `:142`, `:143`; `skills/meta-factory/SKILL.md:326`

**Verbatim quote** (`docs/methodology/04-harness-binding.md:143`):

> ``- **Manifest Retention Efficiency:** >93% retention of active skills when guided; 0.00% contradictory auxiliary retention when obsolete skills are explicitly listed in `discard_skills`.``

**Defect analysis.** One empirical snapshot (`N = 778`, ">93%", "0.00%") is asserted as a
standing fact in at least six law locations (measured: `best-practices.md` 3 occurrences of
"778", `04-harness-binding.md` 2, plus the restated ">93%" in `SKILL.md:326`). A point-in-time
measurement restated as law is a cache that cannot be re-derived from the tree; the moment a
new dataset lands, six sentences are stale at once and nothing re-checks them.

**Actionable remediation.** Keep the dataset and its provenance in ONE evidence file
(`evidence/compaction-rate-2026-09-20.md` exists) and cite it by pointer from the law; drop the
inline numerals.

---

## F9 — LOW — Negation Test: prohibition-first clauses that duplicate a positive already stated

**File locators:** `skills/meta-factory/SKILL.md:419`; `skills/meta-factory/state.md:26`

**Verbatim quotes:**

> `skills/meta-factory/SKILL.md:419` — ``1. **Do NOT pause, narrate, wait for a prompt, or ask for operator approval.**``

> `skills/meta-factory/state.md:26` — ``**Do not widen the key to a fuzzy token match.**``

**Defect analysis.** Both are pure prohibitions whose positive content is already given
adjacent. `SKILL.md:419` sits directly above step 2, which lists the positive acts ("patch …
add or sharpen the gate … record … stamp … commit"), so the negation adds tokens and drags
four forbidden behaviours into context for no new information. `state.md:26` re-prohibits
"fuzzy token match" in a paragraph that has *already* stated the positive boundary ("The key is
a **boundary-checked prefix**"). The Negation Test asks for positive targets and actionable
boundaries; both lines are redundant negative steering.

**Actionable remediation.** Delete `SKILL.md:419` (step 2 already carries the positive
directive) or restate it as "*In the same turn: patch, gate, record, commit, report*". Delete
the `state.md:26` sentence; the boundary-checked-prefix sentence already forbids the
alternative.

---

## What I checked and found clean (with method)

- **Classic no-ops.** Searched the whole law surface for the textbook no-op phrases —
  `remember to`, `be careful`, `make sure to`, `you should`, `note that`, `keep in mind`,
  `don't forget`, `it is important to`, `as you know`, `obviously` (`grep -rniE`) — **one hit
  total** (`docs/best-practices.md:658`, quoting the phrase in an unrelated argument). The
  corpus does **not** waste tokens telling the model to do what it does naturally.
- **Instrument symlink integrity.** All seven `skills/meta-factory/<instrument>.md` symlinks
  resolve; the six shipped pairs (`hygiene`, `kit`, `ledger`, `open-questions`, `pacemaker`,
  `review-rotation`, `template-instruments`) are byte-identical to their `TEMPLATE/` half
  (`diff -q`, all `IDENTICAL`); `insights.md` correctly points at the factory-only half (no
  TEMPLATE twin exists). No finding.
- **`docs/factory-registry.md`** (98 KB, the largest file) is machine-generated
  (`tools/registry.py render`) and self-declares *"never hand-edited"* — its size is a render,
  not hand-authored token weight, so it is out of scope for this lens.

## Summary

**9 findings.** The single most severe is **F1**: `skills/meta-factory/state.md` — the clause
file a lane *must* load before writing any state row — compresses its law into **9 paragraphs
of >1,000 characters each (12,777 chars total; longest 2,257)**, with no headings or bullets,
so the reader must hold ~640-token run-ons in working memory to extract one rule; this is the
"progressive disclosure" failure the lens exists to catch, and it is compounded by incident
biography carried inline instead of in `evidence/rework.md`.

**Exact commands that produced the measurements:**

```
wc -lwc <files>                                   # sizes: state.md 31856 B, triage.md 7440 B, …
awk 'length>1000{print NR": "length}' state.md    # 9 lines: 24,26,54,56,58,79,144,150,186
grep -roh 'add-on' --include=*.md --include=*.tmpl . | wc -l      # 60
grep -rl 'add-on' --include=*.md --include=*.tmpl . | wc -l       # 14 files
git grep -o 'add-on' | wc -l ; git grep -l 'add-on' | wc -l       # 91 uses / 24 files
grep -rnE '<uuid-regex>' README.md skills/meta-factory/          # 8 raw uuids in README, 5 in SKILL
sed -n '6,7p' tests/test_law_no_raw_session_uuid.py              # proves d72bd52d… is dead
grep -rn 'required_tools' docs/ skills/ TEMPLATE/                # divergent tool sets
grep -rn 'Name your paths at the commit' . --include=*.md --include=*.tmpl   # 6 copies
sed -n '30p' worker.md | md5sum ; sed -n '48p' triage.md | md5sum ; sed -n '50p' carrier.md | md5sum
grep -n '778' docs/best-practices.md docs/methodology/04-harness-binding.md  # 3 + 2
diff -q TEMPLATE/docs/instruments/<x>.md docs/instruments/<x>.md # all IDENTICAL
```
