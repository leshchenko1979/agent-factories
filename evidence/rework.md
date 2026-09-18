# Rework log

**Owns:** every defect, regression and law rollback this factory has produced, with its
root cause and the thing that now prevents it.

The rubric's Stability criterion (O2) asks for two rates: **change fail rate** and
**rework rate**. Neither can be computed from memory, and neither means anything without a
denominator. This file is the numerator; the ledger is the denominator.

> Why this exists: a factory that makes the same mistake quarterly, with the same surprise
> each time, is not learning. An entry with no "prevented by" is a mistake still waiting to
> happen — write that column honestly, even when the answer is *nothing yet*.

---

## Schema

| Column | What goes in it |
|---|---|
| **Date** | When the defect was found, `YYYY-MM-DD`. Not when it was introduced — that is often unknown, and guessing it is how a log becomes fiction |
| **Source** | Who or what surfaced it: an owner instruction, a lane report, a gate, or a review |
| **Defect** | What was wrong, stated so a reader can tell whether it is fixed |
| **Root cause** | Why it happened — the mechanism, not the symptom. "Careless" is not a root cause |
| **Resolution** | The commit or action that fixed it |
| **Prevented by** | The rule, test or gate that stops the recurrence. `nothing yet` is a valid and important answer |

---

## Rates

Both rates are counts, so both are recomputed rather than remembered — never
recalled from the last report.

| Rate | Formula | Denominator from |
|---|---|---|
| **Rework Share** (share of work) | rework entries ÷ (closed work units + rework entries) | `tools/ledger.py` — `closed_subjects` (distinct work units; **not** `close_events`, which counts rows — a re-opened subject carries two) |
| **Rework per Close** | rework entries ÷ closed work units | `tools/ledger.py` — `closed_subjects` (distinct work units; **not** `close_events`, which counts rows — a re-opened subject carries two) |
| **Change fail rate** | rework entries caused by a landed change ÷ changes landed | `git rev-list --count HEAD` |

Two forms of the rework number are reported because they answer different
questions: the *share* is comparable across factories, and *per close* is the
one that tells this factory how much repair it pays per unit of planned work.

**Read the first readings with care.** At 2026-09-12 this factory had 4 closes
against 11 rework entries — a share of 73%, or 2.75 entries per close, which is
what a factory looks like before its gates exist. The number is not alarming; it is *uninformative* until
the gates have had time to bite. What matters is the direction, which is why the
rates are reported in the daily score file as a diff.

---

## Entries

| Date | Source | Defect | Root cause | Resolution | Prevented by |
|---|---|---|---|---|---|
| 2026-09-11 | Owner instruction (`list sessions`) | A one-shot subagent (`f5a2d0fd`, 0 channel bindings) was recorded in the law as "the Delegate lane session". Six member-HQ replies then parked in its queue with nothing left to read them | A dispatch receipt was treated as evidence that a lane existed. The id was carried into the law from the dispatch, never read back from `session_bindings` | `9eda700` — all four lanes recorded, plus "a subagent id is not a lane" | Lane ids are read from live state in the same turn; `ONTOLOGY.md` carries the `subagent` vs `lane` distinction |
| 2026-09-11 | Triage intake | `README.md` recorded Miidas as having no HQ lane, and named it "the open gap" | Written before the lane existed and never re-checked — a stale claim in a file that reads as current | `8f47648` | Member-factory rows carry the lane session id, which is checkable; Triage re-verifies claims before recording them |
| 2026-09-11 | Triage intake (#3) | The measurement procedure required a dated score file; the baseline existed only in chat | The procedure was written after the score, and the file was never created | `522a948` — `evidence/scores/2026-09-11.md` | Score files live at a fixed path; the daily job writes one per run |
| 2026-09-12 | Triage intake (#5) | The leak test guarded three template files, but `best-practices.md` calls itself core law and was outside its scope — and carried substrate mechanics in a heading | The test's file list was written before the core-law set was defined | `d90e593` + `3a306ef` | `TEMPLATE/README.md` now names the scanned set explicitly |
| 2026-09-12 | Self-audit | The score file claimed the surveyed factories "score higher on output and law" than the `meta-layer`, while the same file marked them not-yet-scored | A comparative claim written before the comparison existed | `7857888` — claim dropped | `not scored is not scored zero` is stated in the score file; the ontology separates `score` from `evidence` |
| 2026-09-12 | The new vocabulary gate | Ten occurrences of `meta-layer` — a second name for this project — across five files | Two names were in use since the first week, and nothing checked | `744819f` | `tests/test_ontology.py` fails the build on it |
| 2026-09-12 | Self-caught while writing the gate | The vocabulary gate used plain `git ls-files`, so a brand-new file carrying drift passed until the commit that landed it | The obvious command was used without asking what it returns: tracked files only | `677a477` — `--cached --others --exclude-standard` | The gate's own probe: an untracked file with drift must exit 1 |
| 2026-09-12 | Self-caught while probing the gate above | The first probe of the rework gate reported a clean pass on a deliberately malformed row | The probe appended the row *after* the `## Entries` section, so the gate never parsed it — and an empty result from an unparsed region was read as a pass | Probe corrected in the same turn, then re-run: the malformed row was caught | A probe must write *inside* the region it claims to test, and a pass that follows a malformed input is checked against where that input landed |
| 2026-09-12 | Self-caught while probing the ledger above | The ledger's concurrency probe ran against the **live** `evidence/ledger.jsonl` and left 20 probe rows in it | The tool's path was not parameterised when the probe was written, so "run the probe" meant "run it against the real file" — and the real file was the thing the probe existed to protect | `OC_LEDGER_PATH` added; the probe moved into `tests/test_ledger.py` against a temp file, and the live ledger was reset to its genuine rows | The test cannot reach the real ledger: it appends to a temp path and asserts the row numbers are `1..N` |
| 2026-09-12 | Self-caught while writing the #7 receipt | A receipt comment on the board cited a rework entry for the ledger-probe defect that **did not exist** in this log | The citation was written from memory of the defect rather than from a read of the file — and the defect was in fact missing from the log entirely, so the memory was the only thing that noticed | The entry was added (this row) and the receipt corrected | A receipt that cites a row number is checked against the log in the same turn, the same way any other identifier is |
| 2026-09-12 | Self-caught while repairing this file | The Rates paragraph stated "3 closes against 10 rework entries — a share of 77%" while the ledger already held 4 closes, so the log's own headline number was wrong | The paragraph was written before #9 closed and nothing recomputes it: the file's rule "recomputed rather than remembered" had no mechanism behind it | Recomputed from live state and rewritten — 4 closes, 11 entries, 73% | `tests/test_rework.py` now requires every rate claim in `## Rates` to carry its own date *and* name which form it is — the share of work, or per close. An undated figure was the defect; a figure that names no form is the same defect one step later, because two different numbers travel under the name "rework rate". Probed against both shapes, and against prose that merely names the forms without stating a number |
| 2026-09-13 | Self-caught while answering an owner question | The canonical-term count was published as 27, and the total after eight terms were added as 35. Both were 7 too high — the true figures are 20 and 28 | The count came from a pattern matching every row whose first cell was a backticked term. Three tables in `ONTOLOGY.md` start a row that way — the terms, the objects, the banned synonyms — so seven non-term rows were counted as terms. The figure was then published without its predicate, so no reader could reproduce it | Corrected in `docs/process-audit.md` §6, with the predicate stated beside the number | The vocabulary gate now prints the canonical-term count parsed from the `## Canonical terms` section, so the next run contradicts a wrong figure in the same line it reports clean |
| 2026-09-14 | Surveys run (daily measurement) | Score file `evidence/scores/2026-09-14.md` was committed under an off-rubric lens (invented F1–F3/O1–O4/E1–E3/S1–S3 codes), breaking trend diffability against the 09-13 baseline | Evening survey run substituted the codified 13-criteria rubric with an unadopted process lens before updating the baseline comparison specification | `4e3237c` — canonical measurement run superseded the file and restored the 13-criteria rubric and trend line (ledger n=32) | `docs/measurement-procedure.md` explicitly binds the daily job to `docs/quality-criteria.md`; score files validate against the 13-criteria rubric |
| 2026-09-16 | Infra Factory incident report | `skills/infra-factory/roles/` role cards failed to resolve during hourly triage because the active profile lacked a symlink to the repo's skill directory | `TEMPLATE/BOOTSTRAP.md` Step 3 omitted the explicit profile skill symlink instruction and verification gate for OpenCrabs harnesses | `TEMPLATE/BOOTSTRAP.md` updated with explicit profile symlink instruction & evidence gate | `TEMPLATE/BOOTSTRAP.md` Step 3 carries `test -L ~/.opencrabs/profiles/{{PROFILE}}/skills/{{NAME}}`; P30 mandates autonomous template healing |
| 2026-09-17 | Self-caught reviewing my own diff before commit | A `hashline_edit` replace anchored on a hash read from an *earlier* read of a different region replaced the `## 10. Add-ons in force` heading instead of the intended `## 12. Boundaries`, leaving the law file with two `## 12` sections, no section 10, and the add-ons table sitting under a wrong heading | A 4-char content hash was reused across reads: the same text appears in several regions of the file, so the anchor resolved to a different line than intended. Nothing re-verified the structure after a structural edit | Repaired in the same turn: the heading and section order were restored and the pre-existing duplicate `## 12` was renumbered to `## 14` | `tests/test_law_coverage.py::test_law_sections_are_numbered_contiguously` asserts every `skills/*/SKILL.md` numbered section is contiguous from 0 — a duplicate or a gap fails the build. Probed against both defect shapes (duplicate number, removed section); both fail the gate |
| 2026-09-18 | Self-caught while auditing the gate suite | The hygiene scratch audit globbed `/tmp/oc-*` — a prefix the OpenCrabs dev tooling owns — so 2757 foreign `oc-snap-*` files made this factory's audit report RED for litter it never wrote | The glob was picked for local convenience ("our scratch lives in /tmp") without asking who else writes that prefix. A shared namespace was treated as a private one | `4dafb9d` — the owned prefix is derived from the repository directory name, and extra owned globs are declared with `--scratch-glob` instead of widening the default | `tests/test_hygiene_namespace.py` plants foreign litter in a throwaway directory and asserts it is neither reported nor reaped, while this factory's own stale scratch still is |
| 2026-09-18 | Self-caught while shipping the context-manifest section (issue #30) | The section landed in `docs/methodology/04-harness-binding.md` and never reached `TEMPLATE/docs/methodology/04-harness-binding.md`, so every factory bootstrapped afterwards would have been born without it | `tests/test_template_sync.py` guarded the tool copies only; the documents carried in both trees were unguarded, and nothing named them as a pair to check | `ec53f3c` — `tests/test_docs_sync.py` walks both trees and asserts a path present in both is byte-identical; 17 shared documents are now in sync | `tests/test_docs_sync.py`, registered in `tools/audit.py` by `d5e5d8b`. A document that genuinely must differ carries a `.tmpl` suffix outside the shared path, so the difference is visible rather than silent |
| 2026-09-18 | HQ lane report while shipping #31 (task 4, template sync) | `TEMPLATE/tests/test_template_sync.py` was a stale, unmaintained copy of this repo's own pair-guard — last touched `6efc4f0` — listing **7** pairs against the guard's **15**, so it was missing **8** (`test_ledger_schema`, `roadmap`, `telemetry`, `review`, `test_review`, `test_law_structure`, `test_hygiene_namespace`, `test_docs_sync`) | The pair-guard cannot guard itself: it is correctly absent from `PAIRS`, which left `TEMPLATE/` as the one tree where a file could exist with no pair, no gate and no reader. Nothing asserted that every file the template ships is either a listed copy or a declared template artifact | `b995a09` (shipped under #31) — the stale copy was removed (`git rm`, 61 deletions); `git cat-file -e HEAD:TEMPLATE/tests/test_template_sync.py` exits 128. `tools/audit.py` registers that file as a gate **if present**, and its pairs point at `TEMPLATE/…` paths a bootstrapped factory does not have, so any factory receiving it would carry a permanent false RED — the mirror of #28's false green. Inert only by luck: `TEMPLATE/BOOTSTRAP.md` copies files by name and never names it | nothing yet — #33 proposes a gate walking `TEMPLATE/` and asserting every file is a listed `PAIRS` copy, a declared template artifact (`*.tmpl`, `BOOTSTRAP.md`, …) or an explicit allowlist entry; until it lands, an orphan can still appear unseen |

---

## What this log is not

- **Not a blame record.** It records defects of the *process*, not of a lane or a person.
  The rubric is explicit that outcomes are read as properties of the system.
- **Not a duplicate of the ledger.** The ledger records state transitions as they happen;
  this file records what went wrong and what now prevents it. A defect may produce ledger
  rows, but the reasoning lives here.
- **Not closed by fixing the symptom.** An entry is complete when the "prevented by" column
  names something that would fail if the defect returned.