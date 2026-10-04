# Lens D — Deletion Safety & YAGNI Pruning

**Cycle:** 20260927-c1  **Lens:** D (Family 3 — Tools & Interfaces)
**Repo under review:** `/root/agent-factories` (read-only)
**Revision audited:** `a862d47d994bd581110260a0b5a09e8144a7f382`
**Revision note:** the tree is LIVE — HEAD moved from `e679687` to `a862d47` while this audit ran
(`git log --oneline`). `git diff --stat e679687 a862d47` touches only `TEMPLATE/SKILL.md.tmpl`,
`TEMPLATE/registry/kit.example.json`, `registry/kit.example.json`, `registry/kit.json`,
`skills/meta-factory/SKILL.md` — **none** of the files measured below. Every figure here is pinned to
`a862d47`; file md5s are given with each finding so a re-run can confirm the bytes did not move.

**Method (what produced the numbers):** `git ls-files` (496 tracked); a Python reference counter over
the concatenated text of every tracked file (basename + full-path match); a duplicate-content pass
(md5 of every tracked file → 138 identical-content groups); a deleted-path sweep
(`git log --all --diff-filter=D --name-only`, cross-checked against the live corpus for dangling
references); a manifest-existence pass reading `registry/kit.json` `files` (152 paths) and sha256-ing
each against disk; `ls -la`, `wc -l`, `grep -rn`, `md5sum`, `sed -n` on every cited line.

---

## Finding D-1 — The hygiene sweep's own population count is wrong in the SHIPPED law doc and in the tool's own comment (says "15"/"fifteen", the code holds **16**)

**(1) File Locators / quotes (all verbatim):**

- `docs/instruments/hygiene.md:237`
  > ``therefore sweeps all **15 declaration families** over the live `docs/*.json` files and prints one line per family``
- `TEMPLATE/docs/instruments/hygiene.md:237` — byte-identical twin of the above (`md5 145fb19866990121976fe8118081930a`).
- `tools/hygiene.py:435`
  > `# population is all fifteen and a zero on any line is a verdict rather than a silence.`
- `TEMPLATE/tools/hygiene.py:435` — byte-identical twin (`md5 c432feeb4c33add470ee28c3dfa09737`).

**(2) The mechanism (measured, not read from a docstring):** the constant the sentence describes is
`DECLARATION_SURFACES` at `tools/hygiene.py:443`. Parsing the tuple at `a862d47`:

```
python3 -c "import re;src=open('tools/hygiene.py').read();
m=re.search(r'DECLARATION_SURFACES.*?=\s*\((.*?)\n\)\n',src,re.S);
print(len(re.findall(r'^\s*\(\"([a-z0-9-]+)\",',m.group(1),re.M)))"   # -> 16
```
16 entries: `close-board-exemptions, hygiene-protected, law-uuid-exemptions, ledger-authorizations,
ledger-commit-exemptions, ledger-exemptions, ledger-invariants, ledger-no-shrink-exemptions,
ledger-refs-kinds, ledger-retirements, ledger-schema-exemptions, products,
rework-relative-revision-exemptions, shipped-audit-skips, shipped-mechanism-law,
skill-version-exemptions`. The leg prints `len(families)` over that tuple
(`tools/hygiene.py:627`: ``f"hygiene declaration sweep: {len(families)} family(ies) over "``), so the
tool's own output line reads **16 family(ies)**, not 15.

**When it drifted:** `git log -S '"close-board-exemptions", "docs/close-board-exemptions.json"' -- tools/hygiene.py`
→ `9b8253c` *"hygiene: the declaration sweep's map names the surface the tree already carries"*
(2026-10-04). At the parent commit `0eb39c7` the tuple held **15** entries (verified:
`git show 0eb39c7:tools/hygiene.py` parsed → 15), matching the prose. `9b8253c` added the 16th family
and, by its own commit message, fixed the gate's stale constant (`len(declared) == 15` →
`len(hygiene.DECLARATION_SURFACES)`, `tests/test_hygiene_declaration_sweep.py:131`) — **but left the
tool comment and the law doc (both halves) saying fifteen.**

**(3) Defect analysis:** the hygiene law is a *shipped* instrument; `TEMPLATE/docs/instruments/hygiene.md`
is the canonical half every member adopts. Its family count is the one number a deletion-safety reader
uses to decide whether the sweep's coverage is complete — "15 families swept" reads as a covered
population. The tree's own tool now sweeps 16 and prints 16, so the doc understates the population by
one: a reader reconciling doc against output sees a disagreement with no way to tell which side is
authoritative. This is the exact class the instrument exists to catch ("a stale number beside a larger
tool"), caught in the instrument's own law file — the same failure the file already confesses for its
gate budget (§4: *"re-declared rather than left standing as a stale number beside a larger tool"*).

**(4) Remediation:** in `docs/instruments/hygiene.md:237` and `TEMPLATE/docs/instruments/hygiene.md:237`
replace `**15 declaration families**` with `**16 declaration families**` (or, better, delete the numeral
and cite the predicate, as the file already does for its version identifier at §5); in
`tools/hygiene.py:435` and `TEMPLATE/tools/hygiene.py:435` replace `all fifteen` with `all sixteen` —
or, to prevent recurrence, write `all of DECLARATION_SURFACES`. Keep both halves byte-identical (the
pair is held by `tests/test_docs_sync.py`) and regenerate `registry/kit.json` in the same commit
(§10).

---

## Finding D-2 — A committed `.bak` in the tree that the factory's own litter rule calls a violation, and no leg can see it (tracked litter is a blind spot)

**(1) File Locators / quotes (verbatim):**

- `reviews/rr-donor-replay/state.json.pre-v1.bak` — **tracked**, 3842 B, `md5 9d46f57cbab8111cf4624efbb7c40d8a`:
  ```
  git ls-files --error-unmatch reviews/rr-donor-replay/state.json.pre-v1.bak   # exits 0 — tracked
  ```
- `tools/hygiene.py:25` (module docstring, the instrument's own contract):
  > ``| untracked litter (`*.bak` `*.tmp` `*.log` `.orig`) | violation, no grace — litter is litter |``
  (verbatim: ``| untracked litter (`*.bak` `*.tmp` `*.log` `*.orig`) | violation, no grace — litter is litter |``)
- `tools/hygiene.py:195`
  > `LITTER_SUFFIXES = (".bak", ".tmp", ".log", ".orig")`
- `docs/projects/hygiene-surfaces.md:80`
  > `| **Repo working tree** | zero litter (`.bak` `.tmp` `.log` `.orig` — violation at any age); …`

**(2) The mechanism:** the only litter predicate is inside `inspect_git_working_tree`, and it fires
**only on the `??` (untracked) status code** — `tools/hygiene.py:1427-1429`:
```python
if status_code == "??":
    if path.endswith(LITTER_SUFFIXES):
        violations.append(f"untracked git clutter: {path}")
```
The population is `git status --porcelain` (`tools/hygiene.py:1383`), i.e. untracked + modified paths
only. A **tracked** `.bak` is never in that output, so no leg reports it. The placement leg does not
catch it either: `reviews` is in `PLACEMENT_UNMAPPED` (`tools/hygiene.py:757`), so
`reviews/rr-donor-replay/` is outside the placement population. Measured: the tree carries exactly
one tracked `*.bak` (the `git ls-files | grep -Ei '\.(bak|orig|…)$'` sweep returns it and nothing
else), and `tools/hygiene.py:692` even gives `.bak` the content class `"backup"` — a class no allowed
list admits.

**(3) Defect analysis:** the law's blanket rule ("litter is litter", "violation at any age") and the
tree disagree: the repo commits a `.bak` the rule declares a violation. The pre-image is *deliberate*
— `tools/review.py:1786` writes `state.json.pre-v1.bak` on migration, and `tests/test_review.py:340`
asserts it — so the artifact is intended; the defect is that **nothing scans tracked files for litter
suffixes**, so a committed `.bak`/`.tmp`/`.orig` is invisible to every leg and the "zero litter"
claim on `docs/projects/hygiene-surfaces.md:80` is only true of the untracked population. A reader
who trusts that line would conclude this repo carries no `.bak`; it carries one.

**(4) Remediation:** two shapes, both honest — (a) narrow the law to what it measures: qualify
`docs/projects/hygiene-surfaces.md:80` and the `tools/hygiene.py:25` row as *untracked* litter and add
a one-line note that a tracked pre-image is out of scope; or (b) close the gap: add a
tracked-file sweep over `git ls-files` for `LITTER_SUFFIXES` that PRINTS each hit (report-only,
`removes: no`, matching the file's other legs) and declare the two legitimate pre-images
(`reviews/rr-donor-replay/state.json.pre-v1.bak`, and any in-flight one) as an explicit exemption. Do
**not** simply delete the pre-image: the gate at `tests/test_review.py:340`/`:777` reads it as the
donor's own bytes and would red.

---

## Finding D-3 — A dangling reference to a retired exemption file survives in a proposal

**(1) File Locator / quote:**

- `docs/proposals/05-ledger-number-roots.md:28`
  > ``The two genuine mismatches, both in `docs/close-verify-count-exemptions.json` as``

**(2) The mechanism:** `docs/close-verify-count-exemptions.json` **does not exist**
(`ls docs/close-verify-count-exemptions.json` → *No such file or directory*; it is absent from
`git ls-files`). It was retired in commit `aa091e7` *"retire(ledger): the settlement receipt is the
tool's, not the author's"*, whose message enumerates what it removed: *"the gate
`tests/test_close_verify_count_declared.py` and its twin, **both exemption files**, its
REQUIRED_GATES entry, its pair entry, its budget entry and its declared boundary."* The retirement
swept `registry/kit.json`, `registry/gates.json` and the test suite cleanly (grep for
`close_verify_count|close-verify-count` over `registry/*.json` and `tests/ tools/` returns **0**), but
did not touch this proposal.

**(3) Defect analysis:** the proposal is the *explanation* of the very class the file was the exit for;
a reader who follows `docs/close-verify-count-exemptions.json:28` to learn where the "PERMANENT DEBT"
(n=931, n=1014) is declared finds nothing, and the same paragraph still asserts the file is *"as
PERMANENT DEBT"* — reading as a live surface. The retirement was otherwise disciplined; this is the one
surface it left pointing at a deleted path. (Scope note: the *only* surviving dangling reference to a
retired path anywhere in the tree that is not the append-only `evidence/ledger.jsonl` /
`evidence/rework.md` history is this one — see the method paragraph; `TEMPLATE/BOOTSTRAP.md:418`,
`TEMPLATE/docs/instruments/kit.md:488` and `TEMPLATE/tests/test_template_integrity.py:11` name retired
paths *as* retired, deliberately, and are correct.)

**(4) Remediation:** edit `docs/proposals/05-ledger-number-roots.md:28` to mark the retirement, e.g.
append *(retired 2026-09-25 in `aa091e7`; the `rows=` receipt moved into the write path — see the
`run … verified_rows=N` row)*, and re-word "as PERMANENT DEBT" to past tense. A proposal is a dated
design record and may keep its history, but it must not name a live path for a dead surface.

---

## Finding D-4 — Evidence supersession is entirely prose-only: 16 dated artifacts across 6 families carry **0** `superseded_by` markers

**(1) File Locator / quote (the law states the debt itself):**

- `docs/instruments/hygiene.md:157-159`
  > ``Measured 2026-10-02: **25 dated`` … ``artifacts over 15 artifact families**, six of them carrying more than one member, and **zero**`` … `` `superseded_by` markers anywhere in the tree``

**(2) The measurement (re-run at `a862d47`, over `evidence/**/*.md`, naming convention
`<stem>-YYYY-MM-DD[-suffix].md`):**

| figure | value |
|---|---|
| dated artifacts total | **26** |
| distinct dated families | **15** |
| families with >1 distinct date | **6** |
| artifacts inside multi-member families | **16** |
| `superseded_by` markers in the tree | **0** |

The six multi-member families: `instrument-census-ledger` (3), `instrument-census-open-questions` (3),
`instrument-census-pacemaker` (2), `instrument-census-review-rotation` (2), `kit-drift-census` (4),
`name-census` (2). `grep -rl superseded_by` returns only test code and the law prose that *describes
the absence* — never an artifact carrying one.

**(3) Defect analysis:** the law already declares this as a debt census and not a fault list
(`docs/instruments/hygiene.md:167-171`), and `evidence/` is append-only by law, so **deletion is not
the remedy and must not be proposed** — the brief's "DELETE-SAFE (0 references)" classification does
*not* apply to `evidence/`. The residual deletion-safety hazard is the one the law names: which census
governs is knowable only by a reader noticing a later dated sibling, and the debt has **not fallen**
since 2026-10-02 (the law's "25/15" is now 26/15; the marker count is still zero). This is a *KEEP +
annotate* class, not a delete class.

**(4) Remediation:** add a mechanical `superseded_by: <path>` line to the older member of each of the
six families (the leg excuses a marker naming a live path — `docs/instruments/hygiene.md:166`), and
update the "Measured 2026-10-02: 25/15" figure in both halves of `hygiene.md` to the current 26/15 with
its instant. **Do not delete any `evidence/` artifact** — the instrument's G7 leg asserts `removes: no`
structurally, and an artifact deleted when a later run replaces it violates the append-only law.

---

## Finding D-5 — `tools/sigpipe_threshold.sh` is an ungated, unshipped one-off whose header cites paths that do not exist in this repo

**(1) File Locators / quotes (verbatim):**

- `tools/sigpipe_threshold.sh:5`
  > ``# THE MECHANISM. `tools/state/oc-ledger:140` sets `set -o pipefail`, while the selftest asserted with``
- `tools/sigpipe_threshold.sh:32`
  > ``# linter's accumulated output CAN exceed the buffer, and `tools/audit/oc-lint-laws:179,180` pipes``

**(2) The mechanism:** neither cited path exists. `ls -d tools/state tools/audit` → *No such file or
directory*; `find . -type d -name state -o -type d -name audit` (excluding `.git`) → **nothing**. The
script is referenced by exactly one artifact (`evidence/deliverables/2026-09-27-review-rotation-donor-migration.md:163`),
is **not** in `registry/kit.json` (`grep -c sigpipe_threshold registry/kit.json` → **0**) and **not** in
`registry/gates.json` (→ **0**), and has no test file. The factory's own survey already flagged the
class: `evidence/instrument-survey-2026-09-27.md:78` — *"`compaction_rate` **0**, `render-trap-runbook`
**0**"* — root-side tools with no gate.

**(3) Defect analysis:** a reproduction script whose own header points at `file:line` locators in a
*different* tree is a citation that cannot be checked here: the reader of
`2026-09-27-review-rotation-donor-migration.md` is told to reproduce via
`bash tools/sigpipe_threshold.sh` (which works) but the surrounding prose about `oc-ledger:140` and
`oc-lint-laws:179,180` resolves to nothing. It is a single-defect reproduction harness kept past its
use — a YAGNI/ARCHIVE candidate, not DELETE-SAFE (one live doc still cites it).

**(4) Remediation:** either **ARCHIVE** it into the dated deliverable that cites it
(`evidence/deliverables/2026-09-27-…` — inline the script, as `137-claim-leg-port-spec.md` did for its
`.diff`) and delete `tools/sigpipe_threshold.sh`, or **KEEP** it and rewrite the two header lines to
say the cited sites live in the *donor* tree (`oc-ledger`/`oc-lint-laws`, not this repo), so the
locators are not read as local. If kept, register it or state in `tools/` why it is deliberately
ungated (the survey's S1 leg already reports "no gate exercises this tool").

---

## Finding D-6 — A second non-reproducible count in the same shipped paragraph ("five families")

**(1) File Locator / quote:**

- `docs/instruments/hygiene.md:243`
  > ``silently skipped** — five families name board issues, lanes, ledger rows, dates or vocabulary, none of``

**(2) The mechanism:** the same paragraph (Finding D-1) counts the *unswept* families as "five". Parsed
from `DECLARATION_SURFACES` at `a862d47`: **10** families carry an empty probe tuple `()` (i.e. are
declared-but-unswept) and **6** carry probes. Of the 10 unswept, **8** fall in the categories the
sentence names (board issues: `close-board-exemptions`, `ledger-exemptions`,
`rework-relative-revision-exemptions`; lanes: `ledger-authorizations`; ledger rows:
`ledger-retirements`, `ledger-schema-exemptions`; dates: `ledger-invariants`; vocabulary:
`ledger-refs-kinds`), the other two being `hygiene-protected` (prevention surface) and `products`
(product records) — which the sentence does not name. No reading of the map yields five.

**(3) Defect analysis:** same class as D-1 — a shipped law doc carrying a numeral that the code it
describes contradicts, in the same paragraph, so a member reconciling the two sees two disagreements
and cannot trust either. Low blast radius (it describes a secondary property) but it is the same stale
constant.

**(4) Remediation:** replace `five families` with `ten families` (or the category-scoped figure, stated
with its predicate), or drop the numeral and say *"each unswept family names its reason on its own
line"* — which is the property actually under test. Fix both halves in one commit.

---

## Finding D-7 — 494 KB of regenerable derived JSON is committed (YAGNI/bloat; KEEP, but recorded)

**(1) File Locators / quotes:**

- `registry/index.json` — 163792 B, first line `"generated_by": "tools/registry.py render"`.
- `registry/state.json` — 329888 B, same generator; `"snapshot_schema"` + `"resolved_at"`.

**(2) The mechanism:** both are produced by `tools/registry.py render`; `tests/test_registry.py:2109`
marks them *"STATED SKIP … (factory data)"* and compares the committed copy against a fresh render
(`tests/test_registry.py:293`). So they are a committed *snapshot*, deliberately not gitignored (unlike
the derived `evidence/.ledger-index.sqlite`, which `.gitignore:7` declares out).

**(3) Defect analysis:** this is a note rather than a defect — the files are the registry's declared
data surface and the gates compare against them, so **KEEP**. It is recorded because they are the two
largest tracked artifacts in the repo (494 KB of the 16.4 MB tracked total) and are fully regenerable;
if the snapshot were ever made derivable at read time, they would be the first YAGNI candidates. No
action recommended now.

**(4) Remediation:** none. Recorded so a later pruning pass does not re-derive the question.

---

## Surfaces checked and found genuinely clean (with method)

- **Manifest closure is intact.** Every one of the 152 paths in `registry/kit.json` `files` exists on
  disk **and** matches its recorded sha256 (script: read `kit.json`, `os.path.exists` + `hashlib.sha256`
  per path). `file_count` = 152 = `len(files)`. **0 missing, 0 hash-mismatched** — no shipped path has
  been silently deleted.
- **All root↔TEMPLATE pairs are byte-identical.** A duplicate-content pass over all 496 tracked files
  (md5 per file) yields **138 identical-content groups**; every group is exactly a `TEMPLATE/…` ↔
  `…` pair (or the 3-way `TEMPLATE/x` + `x` + the `skills/meta-factory/x` symlink). No orphaned
  half-pair, no drift. The one non-shipped instrument is `insights` (`TEMPLATE/docs/instruments/insights.md`
  does not exist — checked — which is why its reload link alone points at the root half; correct, not a
  defect).
- **Test fixtures and helpers are all live.** `tests/fixtures/` holds exactly one file,
  `factory-fragment.example.json`, read by `tests/test_registry.py:2002` as *"the live specimen of the
  layout arm"* (referenced by both halves of `test_registry.py` and `tools/registry.py:746`) — KEEP.
  The five non-test helper modules (`gate_fixtures.py`, `gate_registry.py`, `hook_installation.py`,
  `ledger_boundary.py`, `rework_table.py`) are each imported by ≥6 files — no orphan.
- **No stray files.** `git status --porcelain` (tracked view) is empty; the only untracked entries are
  the declared-out residue (`.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `.audit.lock`,
  `evidence/.ledger-index.sqlite`, `evidence/.{ledger,insights}.lock`, `evidence/publish-receipt.json`),
  all matched by `.gitignore` (`git check-ignore -v` confirms `.audit.lock`, `.ledger-index.sqlite`,
  and the `.gitignore`-in-cache `*` rules) or by `PLACEMENT_SKIP`. No `pyproject.toml`, `setup.cfg`,
  `tox.ini`, `Makefile`, `conftest.py` or CI config exists — there is **no legacy build config** to
  prune (checked: `git ls-files | grep -iE 'pyproject|setup\.|tox|Makefile|\.cfg|\.toml|conftest'` → empty).
- **`docs/*.example.json` without a live counterpart are declared states, not stale orphans.** Only
  three examples lack a `docs/<name>.json`: `hygiene-protected` (prevention surface, absence is the
  shipped state — `docs/instruments/hygiene.md:296`), `ledger-schema-exemptions` (keyed by ledger row
  `n`, absence = no exemptions — `docs/ledger-schema-exemptions.example.json:2`), and `review-lenses`
  (member extension surface, absent is the default — `docs/instruments/review-rotation.md:288`). Each
  is named in `DECLARATION_SURFACES` (`tools/hygiene.py:443`) and renders `absent (no live file)`.
- **The retired `close-verify-count` surface is clean in the registry and the suite.** Grep for
  `close_verify_count|close-verify-count` over `registry/*.json`, `tests/`, `tools/` → **0**; the only
  surviving reference is the proposal in Finding D-3.

## Classification table

| path | class | basis |
|---|---|---|
| `reviews/rr-donor-replay/state.json.pre-v1.bak` | **KEEP** (declared; but make it visible) | read by `tests/test_review.py:340,777`; D-2 |
| `docs/close-verify-count-exemptions.json` | **already DELETED** (aa091e7) — fix the dangling ref | D-3 |
| `docs/proposals/05-ledger-number-roots.md:28` | **EDIT** | D-3 |
| `tools/sigpipe_threshold.sh` | **ARCHIVE or KEEP+annotate** (not DELETE-SAFE: 1 live cite) | D-5 |
| `tools/compaction_rate.py`, `tools/render-trap-runbook.py` | **KEEP** (cited by `docs/measurement-procedure.md` / a live deliverable); ungated | survey §3.2 |
| `evidence/**` (all dated censuses) | **KEEP** (append-only by law) + add `superseded_by` markers | D-4 |
| `registry/index.json`, `registry/state.json` | **KEEP** (gates compare against them) | D-7 |
| `tests/fixtures/factory-fragment.example.json` | **KEEP** | live specimen |
| `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `.audit.lock` | **KEEP / declared out** (q15) | `PLACEMENT_SKIP`, `.gitignore` |

---

## Summary

**Seven findings, most severe first: D-1 (shipped law doc + tool comment understate the hygiene
sweep's family count — "15"/"fifteen" vs the code's 16, drifted in `9b8253c` which fixed the test but
not the doc), D-2 (a tracked `.bak` the litter rule calls a violation, invisible because the leg reads
only `git status`), D-3 (a dangling reference to the `aa091e7`-retired `docs/close-verify-count-exemptions.json`
in `docs/proposals/05-ledger-number-roots.md:28`), D-4 (evidence supersession is 100% prose-only: 0
`superseded_by` markers over 16 artifacts in 6 families), D-5 (`tools/sigpipe_threshold.sh` cites
non-existent `tools/state/oc-ledger` / `tools/audit/oc-lint-laws`; ungated and unshipped), D-6 (the
same paragraph's "five families" is also non-reproducible: 10 unswept), D-7 (494 KB of regenerable
registry JSON committed — recorded, KEEP).** The single most severe is **D-1**: it is a wrong number in
a *shipped* instrument's own law, in both halves, contradicting the tool that prints 16 — the exact
"stale number beside a larger tool" the hygiene instrument exists to catch, caught in its own file.
**Measurements were produced by:** `git rev-parse HEAD` / `git log --oneline` / `git diff --stat`;
`git ls-files`; a Python basename-and-full-path reference counter over the concatenated tracked corpus;
a Python md5 duplicate-content pass (138 groups); `git log --all --diff-filter=D --name-only` plus a
cross-check of each deleted path against the live corpus for dangling references; a Python parse of
`DECLARATION_SURFACES` at HEAD and at `0eb39c7`; a Python sha256 existence pass over `registry/kit.json`
`files` (152 paths); and `grep -rn` / `ls -la` / `wc -l` / `md5sum` / `sed -n` on every cited line
(`tools/hygiene.py:25,195,435,443,627,692,757,1427-1429`; `docs/instruments/hygiene.md:157-159,237,243`;
`docs/projects/hygiene-surfaces.md:80`; `docs/proposals/05-ledger-number-roots.md:28`;
`tools/sigpipe_threshold.sh:5,32`; `registry/index.json`; `registry/state.json`).
