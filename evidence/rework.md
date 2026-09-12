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
| **Rework rate** (share of work) | rework entries ÷ (work units closed + rework entries) | `tools/ledger.py` — `close` rows |
| **Rework per close** | rework entries ÷ work units closed | `tools/ledger.py` — `close` rows |
| **Change fail rate** | rework entries caused by a landed change ÷ changes landed | `git rev-list --count HEAD` |

Two forms of the rework number are reported because they answer different
questions: the *share* is comparable across factories, and *per close* is the
one that tells this factory how much repair it pays per unit of planned work.

**Read the first readings with care.** At 2026-09-12 this factory had 3 closes
against 10 rework entries — a share of 77%, which is what a factory looks like
before its gates exist. The number is not alarming; it is *uninformative* until
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

---

## What this log is not

- **Not a blame record.** It records defects of the *process*, not of a lane or a person.
  The rubric is explicit that outcomes are read as properties of the system.
- **Not a duplicate of the ledger.** The ledger records state transitions as they happen;
  this file records what went wrong and what now prevents it. A defect may produce ledger
  rows, but the reasoning lives here.
- **Not closed by fixing the symptom.** An entry is complete when the "prevented by" column
  names something that would fail if the defect returned.
