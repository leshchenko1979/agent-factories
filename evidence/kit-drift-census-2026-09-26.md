# Kit-drift census — member adoption of the template's shipped set

Read at **2026-09-26T22:55:00Z** by `tools/kit_census.py`, which calls the patrol's
`kit_drift_leg` — this artifact renders that leg's own result and adds no
comparison of its own.

## 1. The reference, stated first

Every figure below compares a member's tree against **OUR** `registry/kit.json`
(`kit_version` `b0bb09cb288f`, 118 paths). That is a
fact about our shipped bytes as much as about their tree, and it moves when
**we** move — so a DIFF here is not a member's to act on. A member acts on
its own vendored pin, judged by `tests/test_kit_pin.py`.

## 2. The population

- members declared: **5**, reachable: **5**
- **every manifest cell** (590 pairs): same 10 · DIFF 48 · ABSENT 532
- **bootstrap-named subset** (50 cells, the 10 files
  `TEMPLATE/BOOTSTRAP.md` names): same 1 · DIFF 20 · ABSENT 29

Two populations are reported because a number must travel with its own predicate:
the bootstrap subset is what the earlier 1/20/29 baseline was taken over, and quoting
only one of them would leave the other unreproducible.

## 3. Per member — the figure AND the declaration

| member | same | DIFF | ABSENT | own pin | zone own/not | declared |
|---|---|---|---|---|---|---|
| `ai-antispam` | 2 | 9 | 107 | **none** | 5/6 | 2026-09-26T06:20:28Z · attested |
| `infra-factory` | 3 | 15 | 100 | vendored · 0 exempt | 6/8 | 2026-09-26T06:21:03Z · attested |
| `inferhub-watch` | 4 | 8 | 106 | vendored · 0 exempt | 7/6 | 2026-09-26T06:19:04Z · attested |
| `miidas` | 1 | 15 | 102 | **none** | 8/5 | 2026-09-26T06:31:01Z · attested |
| `opencrabs-dev` | 0 | 1 | 117 | **none** | 5/5 | 2026-09-26T06:41:11Z · attested |

Three columns carry the point. **own pin** is the member-actionable half: a
member with no pin has no figure of its own, and the DIFF beside it is against
OUR manifest. **declared** is when it last attested. A member that has DECLARED
a fork and one that has silently diverged produce the same figure, and must not
read the same — which is why section 5 carries what each one said.

## 4. Declared detail

### `ai-antispam`

- attested: **2026-09-26T06:20:28Z** · status `attested`
- declared surfaces: zone owns 5 / not-owns 6 · services 15 · lanes 6 · announcements 3
- DIFF: `tests/test_close_board_recorded.py`, `tests/test_hygiene_namespace.py`, `tests/test_ledger.py`, `tests/test_ledger_schema.py`, `tests/test_ontology.py`, `tests/test_rework.py`, `tools/audit.py`, `tools/hygiene.py` (+1 more)
- ABSENT: `AGENTS.md.tmpl`, `BOOTSTRAP.md`, `ONTOLOGY.md.tmpl`, `README.md`, `SKILL.md.tmpl`, `docs/addons.md`, `docs/addons/domain/consulting.md`, `docs/addons/domain/outreach.md` (+99 more)

### `infra-factory`

- attested: **2026-09-26T06:21:03Z** · status `attested`
- declared surfaces: zone owns 6 / not-owns 8 · services 9 · lanes 5 · announcements 4
- DIFF: `docs/methodology/01-llm-weakness-counters.md`, `docs/methodology/02-quality-management.md`, `docs/methodology/03-documentation-standards.md`, `docs/methodology/04-harness-binding.md`, `roles/carrier.md`, `roles/hq.md`, `roles/triage.md`, `roles/worker.md` (+7 more)
- ABSENT: `AGENTS.md.tmpl`, `BOOTSTRAP.md`, `ONTOLOGY.md.tmpl`, `README.md`, `SKILL.md.tmpl`, `docs/addons.md`, `docs/addons/domain/consulting.md`, `docs/addons/domain/outreach.md` (+92 more)

### `inferhub-watch`

- attested: **2026-09-26T06:19:04Z** · status `attested`
- declared surfaces: zone owns 7 / not-owns 6 · services 6 · lanes 4 · announcements 3
- DIFF: `README.md`, `tests/test_ontology.py`, `tests/test_rework.py`, `tests/test_single_writer.py`, `tools/audit.py`, `tools/field_predicate.py`, `tools/ledger.py`, `tools/ledger_declaration.py`
- ABSENT: `AGENTS.md.tmpl`, `BOOTSTRAP.md`, `ONTOLOGY.md.tmpl`, `SKILL.md.tmpl`, `docs/addons.md`, `docs/addons/domain/consulting.md`, `docs/addons/domain/outreach.md`, `docs/addons/domain/platform.md` (+98 more)

### `miidas`

- attested: **2026-09-26T06:31:01Z** · status `attested`
- declared surfaces: zone owns 8 / not-owns 5 · services 6 · lanes 5 · announcements 4
- DIFF: `README.md`, `docs/methodology/01-llm-weakness-counters.md`, `docs/methodology/02-quality-management.md`, `docs/methodology/03-documentation-standards.md`, `docs/methodology/04-harness-binding.md`, `docs/subject/client-requirements.md`, `docs/subject/domain-model.md`, `tests/test_ledger.py` (+7 more)
- ABSENT: `AGENTS.md.tmpl`, `BOOTSTRAP.md`, `ONTOLOGY.md.tmpl`, `SKILL.md.tmpl`, `docs/addons.md`, `docs/addons/domain/consulting.md`, `docs/addons/domain/outreach.md`, `docs/addons/domain/platform.md` (+94 more)

### `opencrabs-dev`

- attested: **2026-09-26T06:41:11Z** · status `attested`
- declared surfaces: zone owns 5 / not-owns 5 · services 6 · lanes 37 · announcements 1
- DIFF: `README.md`
- ABSENT: `AGENTS.md.tmpl`, `BOOTSTRAP.md`, `ONTOLOGY.md.tmpl`, `SKILL.md.tmpl`, `docs/addons.md`, `docs/addons/domain/consulting.md`, `docs/addons/domain/outreach.md`, `docs/addons/domain/platform.md` (+109 more)

## 5. Declared decisions — what each member SAID about its own figure

Read from `registry/kit-decisions.json` — OUR record of what each member
declared, not a surface a member writes. Each entry names its source and
instant so it can be checked rather than trusted. Instants are quoted AS THE
MEMBER STATED THEM, so some are approximate; the round's own ledger rows
(`tool-full-set-census`, `ledger-adoption-census`) carry the measured halves.

### `ai-antispam`

- declared **2026-09-25T12:20:00Z**, when its own measurement read: same=0 DIFF=5 ABSENT=5 of 10
- forks declared exempt-or-deliberate: 5 (`tools/ledger.py`, `tools/audit.py`, `tests/test_ledger.py`, `tests/test_ontology.py`, `tests/test_rework.py`)
- the five DIFF are deliberate forks, not drift: ledger.py lacks the write-path refusal (#144) and audit.py carries the #38 yield fix the template still lacks (#143)
- no deliberate absences: all five ABSENT are real gaps, tracked on its own #40
- port order defended: field_predicate first (fixes a live false-RED class — its audit parses detail.split() naively at :102 and :145), then rework_table (it carries TWO inline parsers of evidence/rework.md), then the two hooks, then gate_budget last (needs a per-gate measurement pass it has not taken)

### `infra-factory`

- declared **2026-09-25T12:20:00Z**, when its own measurement read: same=0 DIFF=5 ABSENT=5 of 10
- forks declared exempt-or-deliberate: 5 (`tools/ledger.py`, `tools/audit.py`, `tests/test_ledger.py`, `tests/test_ontology.py`, `tests/test_rework.py`)
- the five DIFF are its own gates for its own code: DO NOT PORT — replacing working gates with ones bound to files it does not carry trades a green gate for an unknown one
- one decision the dispatch expected is NOT NEEDED: EVENTS is IDENTICAL (both eight events), so there is nothing to decide there
- copying the template ledger.py over its own would INTRODUCE imports it lacks (its copy is 311 lines, stdlib-only) and break verify (its EXEMPTIONS is a 4-tuple where the template's is a 5-tuple)
- hooks/pre-commit NOT APPLICABLE: it is a template-sync concern and this factory is not template-synced
- field_predicate and rework_table NOT NEEDED standalone: nothing in its tree imports either
- ADOPT hooks/commit-msg AND its predicate (two files): 12 of its last 40 subjects cite a row number, and it has a first-hand instance of the exact failure the rule names (committed n=353 when the row was 354)
- CANDIDATE gate_budget: needs registry/gates.json authored from measurements it has not taken

### `inferhub-watch`

- declared **2026-09-25T12:2xZ**, when its own measurement read: same=1 DIFF=5 ABSENT=4 of 10
- forks declared exempt-or-deliberate: 5 (`tools/ledger.py`, `tools/audit.py`, `tests/test_ledger.py`, `tests/test_ontology.py`, `tests/test_rework.py`)
- the five DIFF are deliberate: its EVENTS carries `ack`, a member-added event the template does not ship — a faithful copy drops it and takes 5 of 7 ack probes red against 8 live rows (the defect it filed upstream as agent-factories #137)
- BLOCKER 1: commit-msg cannot be ported as-is — its predicate would refuse 114 of its last 200 subjects because this repo is append-then-cite (the number is a RECEIPT read from the tool's own output, not a prediction)
- BLOCKER 2: pre-commit was unportable AS SHIPPED — its PAIRS dependency sat in neither TEMPLATE/tests nor the manifest, so a port got a hook that warned and refused nothing (fixed at db9b658; both legs now skip silently where TEMPLATE/ is absent)
- BLOCKER 3: gate_budget needs registry/gates.json and this tree has no registry/ directory
- deliberate absences declared: tools/hygiene.py (local #105), tests/test_single_writer.py (local #106), tests/test_template_sync.py (meta-factory-only), docs/ledger-commit-exemptions.json
- CAN TAKE tests/test_ledger.py, whose closure includes tests/hook_installation.py

### `miidas`

- declared **2026-09-25T12:3xZ**, when its own measurement read: same=0 DIFF=5 ABSENT=5 of 10
- forks declared exempt-or-deliberate: 5 (`tools/ledger.py`, `tools/audit.py`, `tests/test_ledger.py`, `tests/test_ontology.py`, `tests/test_rework.py`)
- genuinely deliberate forks: its ledger imports tools/subject_law.py (its #28, repo-qualified subjects) and carries a row-scoped EXEMPTIONS shape its #36 landed — a wholesale copy drops both
- NOT deliberate, and stated as such: the template grew a TELEMETRY + PREDICATE layer it never adopted (cost_usd 0, tokens_in 0, tokens_out 0 against turns 32 on its last 100 rows) — a feature gap, not drift
- commit-msg is its STRONGEST port, with one collision: the row-number refusal would refuse 10 of its last 60 subjects, so it wants the trailer alone — adopt the trailer, keep append-then-cite, exempt rather than rewrite
- gate_budget PARTIAL: it closed its #42 implementing the verdict half (per-gate budget, three-way PASS/FAIL/UNKNOWN, margin x measured); the MANIFEST half is absent
- rework_table: it already has tools/rework_entries.py arrived at independently — RECONCILE, not copy (its column_index is hardcoded where the template derives from the header)
- pre-commit: not assessed either way, and it does not claim otherwise

### `opencrabs-dev`

- declared **2026-09-25T12:2xZ**, when its own measurement read: 10 ABSENT of 10 in /root/opencrabs and in the skill repo tools/
- forks declared exempt-or-deliberate: 0
- all ten recorded as DELIBERATE ABSENCE, not drift: our tools/ is a different OBJECT (the oc-* fleet, 51 entries versioned in the skill repo, shared by every lane — there is no per-factory toolkit by design)
- its ledger is a different OBJECT too: workers-ledger.json is a skill-version ACK dict with no `n` ordinal, not an event ledger
- the repo SPLIT is deliberate (v0.4.60): tools+law versioned in the skill repo, runtime state in the state repo
- it asked that the measured tree be NAMED in any report, because measuring /root/opencrabs will always return 10-of-10 ABSENT — that tree has no tools/ at all, so the reading is structural and carries no information
- on the substrate-independent half it measured rather than agreed: 8 of its last 400 subjects cite n=<digits> and every cited row PREDATES its commit (no phantoms), but the invariant is UNENFORCED — queued to its Toolsmith as a tools/** change
- the Session-Id trailer is already its law and working: fork repo 197/200, skill repo 147/200

## 6. Bounds — what this census does not say

- **DIFF is measured; behind-vs-forked is not.** The leg compares bytes. It
  cannot say whether a member is BEHIND the template or has deliberately
  forked, and those need opposite actions.
- **ABSENT is not a verdict.** A factory ports a subset by design; a path it
  never took cannot diverge from anything.
- **The pin gate is the member's own view.** 3 of 5 members have vendored no pin (`ai-antispam`, `miidas`, `opencrabs-dev`), so for those the figure above is against OUR manifest and is not theirs to
  act on. The vehicle exists (`TEMPLATE/registry/kit.example.json`) and `tests/test_kit_pin.py`
  is the gate that judges it; this census is where that adoption is observed.

