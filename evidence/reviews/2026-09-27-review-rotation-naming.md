# Naming review — the Review Rotation instrument

**Owns:** promotion criterion 2 (`template-instruments.md` §5.1.2 — naming against a fleet-wide
census) for **Review Rotation**, and the four-surface review of its names.
**Written:** 2026-09-27, by the Review Rotation lane. **Read against:** `template-instruments.md` §4.
**Reviewer:** the Instruments-methodology lane.

A name is **realised on four surfaces**, and each surface has its own reader — so a name that is
right on one and wrong on another is a defect that no single check can see. The frame's §4 documents
the criteria; the surfaces below are what this review walks, and the §4 amendment in this same change
adds the missing one.

| # | surface | how the name is realised | the mechanism that READS it |
|---|---|---|---|
| S1 | **declared name** | the instrument's name in its law file | the reader of the law; `template-instruments.md` §4's criteria |
| S2 | **file basename** | `tools/review.py`, `tests/test_review.py` | the Python import machinery (module identity); `tools/kit_names.py` (fleet collision + stdlib shadowing); `registry/kit.json` (the path IS the key) |
| S3 | **path slug** | `TEMPLATE/docs/instruments/review-rotation.md`, its root pair, and the reload link `skills/meta-factory/review-rotation.md` | `tests/test_docs_sync.py` (pair); `registry/kit.json` (path + class); `discover_aux_files` (`/root/opencrabs/src/brain/skills.rs:428`) for the reload link |
| S4 | **published slug** | a URL segment, for an instrument that publishes a page | the **pointer** — the tool reads `pages/latest.json` BEFORE it consults any register |

## S1 — declared name: **Review Rotation** — KEEP

- **Simpler** (§4.1): two words, and no shorter form disambiguates it from the catalogue it governs
  (`review-lenses.md`) or the engine it drives (`review.py`).
- **Higher-fidelity** (§4.3): it states what the instrument **does** — a rotation of periodic
  multi-lens reviews — and names no donor. **The donor-role labels "Duty 4"/"Duty 6" are explicitly
  NOT the name**; they name two sections of one factory's role card.
- **Non-conflicting** (§4.2): the string already names this instrument inside the shipped engine's
  own docstring in five trees (`Multi-Lens Review Engine (Duty 4+6 Review Rotation / P32)`), and no
  other instrument claims it.

## S2 — file basename: `review.py` / `test_review.py` — KEEP

Receipt: `tools/kit_names.py --json`, instant **2026-09-27T14:19Z** — five trees
(`ai-antispam`, `inferhub-watch`, `infra-factory`, `meta-factory`, `miidas`), **one** digest
`5b7f84c4122f`, purpose overlap **1.0**, `conflict: false`; stdlib shadowing **none**.

**An identical digest across five trees is evidence of ONE file delivered five times, not five
independent instruments** — the member copies carry mtime 2026-09-27T14:16Z, minutes before the
census. This is the only reading under which the census' `conflict: false` means what a reader takes
it to mean.

## S3 — path slug: `review-rotation` — ADOPT

**Receipt, predicate `-F 'review-rotation'` over `*.md`/`*.py`/`*.json`/`*.toml`/`*.yaml` across the
seven declared trees, instant 2026-09-27T14:17Z: 0 files.** The kebab slug is free.

**The law slug and the module basename differ, and that is the established pattern rather than a
defect** — a law file names the INSTRUMENT, a module is one executable inside its file set:

| law file | its executable(s) |
|---|---|
| `docs/instruments/kit.md` | `kit_manifest.py`, `kit_census.py`, `kit_names.py`, `kit_surfaces.py`, `kit_deliver.py`, `kit_pin.py` |
| `docs/instruments/pacemaker.md` | `patrol_host_state.py` |
| `docs/instruments/open-questions.md` | `oc-questions` (extensionless) |
| `docs/instruments/ledger.md` | `ledger.py`, `ledger_declaration.py`, `ledger-index.py` |

The reload link inherits the law slug by construction, and `discover_aux_files` reads it as a
top-level `.md` — so `review-rotation.md` is loadable and `review-rotation.md` cannot be confused
with `SKILL.md`, `README.md` or `CHANGELOG.md`, which the loader excludes by exact name.

## S4 — published slug: **NOT APPLICABLE**, and the reason is recorded

This instrument publishes no page, so no URL is assembled from any key. The surface is still walked,
because the **failure it produces is silent**: a contract that publishes
`<host>/<factory-slug>/` while the tool reads its slug from the pointer (`pages/latest.json`) serves
a dead link to every factory except the one the key happens to name. The correction that established
this is another instrument's law — `docs/instruments/open-questions.md` §3 — and is **cited, never
restated** (frame §4: a per-instrument file cites the frame and the law it does not own).

**Consequence for this instrument:** no slug may be assembled from a factory key anywhere in its law,
its engine or its adoption steps, and this instrument ships no such surface.

## Findings

| ID | finding | disposition |
|---|---|---|
| N1 | The frame is **0-hit for `slug`** while a shipped contract publishes a key-assembled URL — the fourth surface is undocumented, so a reviewer cannot walk it | **FIXED in this change**: the §4 amendment adds the slug surface and names its reader |
| N2 | The law slug differs from the module basename | **NOT a defect** — the pattern is established across four shipped instruments (table in S3) |
| N3 | The census population **moved between two reads of the same command**: `review.py` read **1** tree at 09:51Z and **5** at 14:19Z | Recorded. A census figure without its instant is unreproducible, and two such figures read as a contradiction when both are correct for their own instant |
| N4 | An identical digest across trees is read as independent arrival | Recorded. It is evidence of a delivery; arrival evidence (criterion 1) rests on the donor being **ahead**, measured separately in the decision record §2 |
