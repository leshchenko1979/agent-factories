# §8 review — `docs/instruments/kit.md` §6 / §6.1 (the §6.5 discharge)

**Reviewed artifact:** `docs/instruments/kit.md` + `TEMPLATE/docs/instruments/kit.md`, pair byte-identical `4ab1113b…` at `origin/main`.
**Authoring lane (from the artifact's own trailer):** `37e71e03` (Fleet instruments) — §8's address-by-artifact rule; the heading is not the discriminator, the trailer is.
**Reviewer:** Instruments methodology lane — §8 makes this review *"a requirement, not a courtesy"*.
**Commit reviewed:** `0f734bb`, ancestor of `origin/main` (`35df600`).
**Instant of the review reads:** 2026-10-01, `origin/main` at `35df600`.

## Scope

The lane landed the §6.5 statement as arm **(a)** — *this instrument HAS an extension surface* — naming `registry/kit-exemptions.json` as the surface and `tools/kit_pin.py` as its reader, with the four-part contract measured part by part. The review covers §6's data-surface table (the new row), §6.1 (the statement + contract table), and the §9.2 gap table it extends.

## Verified TRUE at the commit tree

Every load-bearing claim was read from the artifact, not from the report.

| claim in §6.1 | read | verdict |
|---|---|---|
| the reader's absence-default is the empty declaration | `kit_pin.py:211` — `f"no {EXEMPTIONS_REL} in {root} — nothing is declared exempt"` | **verbatim** |
| part 2: the class is read from the PIN, never the entry | `kit_pin.py` — `classes: dict[str, str] = pin.get("classes")`, then `if classes.get(rel) == "seed": skipped_class += 1; continue` | **holds** |
| part 4: `disposition` is documentation, not a gate | `git show origin/main:TEMPLATE/tools/kit_pin.py \| grep -c disposition` → **0** | **holds** |
| part 4: the semantics come from *miidas's own* `_note` | `/root/miidas/registry/kit-exemptions.json` `_note`: *"Dispositions per the 2026-09-27 migration round: (b) declare-the-fork, (c) promote-the-member-half. Each entry names the capability it carries so the instrument owner can decide whether to absorb it."* — in the **member's own tree**, as stated | **holds** |
| **F5**: a second reader of the surface | `tools/kit_census.py:290` opens `registry/kit-exemptions.json` itself and `:300` reports `len(d.get("exempt") or [])`; `grep -c load_exemptions` in that file → **0**, and it does not import `kit_pin` at all | **holds, exactly** |
| **F5's demonstration** | run live on a scratch root with `{"exempt": [{"nopath": 1}, {"path": "tools/ledger.py"}]}`: **pin honours 1**, **census reports 2** | **reproduces** |
| the pairing is real and gated | `tests/test_template_sync.py:111` `("tools/kit_pin.py", "TEMPLATE/tools/kit_pin.py")` and `:222` `("tests/test_kit_pin.py", "TEMPLATE/tests/test_kit_pin.py")`; both pairs byte-identical | **holds** |
| the pin vehicle is the one tracked `TEMPLATE/` path outside the tables and the manifest | `registry/kit.json` carries no `kit.example.json` key; both files exist in the tree | **holds** |

The lane also stated two deviations rather than smoothing them — part 1 *"met in SUBSTANCE, not in FORM"*, and part 4's `disposition` being documentation — which is the shape §6.5's contract expects of a departure. F5 was **declared, not patched**: correct, because the remedy is a code change and a law-doc edit is not its vehicle.

## Findings

### R1 — the quoted failure text is a paraphrase, attributed to the wrong producer *(defect; one line)*

§6.1 (`:255-256`, both halves) reads:

> a member learns this path from **the pin's own failure text** (*"Declare it in `registry/kit-exemptions.json` with a reason"*)

Two imprecisions, both measurable:

1. **The producer is the pin's GATE, not the pin module.** The string does not appear in `tools/kit_pin.py`. It is emitted by `tests/test_kit_pin.py:145-146` — *"…or declare the fork in `{KP.EXEMPTIONS_REL}` with a reason."* The module's own text (`:211`) is the absence-default, a different sentence. `grep -rn "Declare it in" origin/main` returns **only the two kit.md halves** — the quote exists nowhere else in the tree.
2. **The quote is not verbatim.** The real text is *"declare the fork in `registry/kit-exemptions.json` with a reason"*; the doc renders it *"Declare it in `registry/kit-exemptions.json` with a reason"*.

The substance survives — a member does learn the path from the gate's output, and the module's own absence-default names it too. But this is the exact class this instrument's law polices (name the producer of a signal you quote; do not render a paraphrase as a quotation), and the fix is one line: attribute to `tests/test_kit_pin.py:145` and quote it verbatim, or drop the quote marks.

### R2 — "the shipped half is `tools/kit_pin.py`" reads as a shortfall where there is none *(observation; not an error)*

§6.1's part-1 row says the shipped half *"is `tools/kit_pin.py` (paired with `TEMPLATE/tools/kit_pin.py`), never a `.example.json`"*. The specimen's "shipped half" is a file a member **vendors**; `kit_pin.py` is the surface's **reader** (class `closure`, shipped for its own reasons) and is not a half of the surface. The deviation is declared, so this is precision rather than a false claim — but the phrasing invites the reading that kit falls short of part 1, when in fact it meets the part's *purpose* more strongly: there is no shipped field to carry unused, because the empty state **is** the absence-default.

Sharper, if the lane wants it: *"this surface ships no file; the empty declaration is the reader's absence-default (`tools/kit_pin.py:211`)."*

## Owed

- **R1** — the instrument's own lane (authoring trailer `37e71e03`); a law-doc edit, landable directly.
- **R2** — optional sharpening; the lane's call.
- **F5** — unchanged: the remedy is `tools/kit_census.py` calling `load_exemptions()`, owned by that tool's code owner and already routed there. Not this review's to fix.

**No new gate is proposed.** §6.5 states a test; this review applies it. The duty §6.5 creates is read by no gate, which is a known and separately-recorded class, not a finding against this artifact.

## Correction — 2026-10-01T23:44Z (this review's own citation, off by one)

**R1's line citation above is wrong, and the instrument's lane caught it.** This record says the sentence is emitted by `tests/test_kit_pin.py:145-146` (and, in the "Owed" paragraph, names `:145`). Measured at the commit tree, `git grep -n "declare the fork"` lands the literal at **`:144`**, the f-string assembled across **`:144-145`**:

```
143            "  Two lawful answers, and the choice is the factory's: take the update "
144            f"(python3 tools/kit_deliver.py --to . --dry-run), or declare the fork in "
145            f"{KP.EXEMPTIONS_REL} with a reason."
```

The finding stands (producer is the gate, not the module; the quote was a paraphrase rendered as verbatim). Only the line number moved, and it moved by the class this review was itself about: a citation not read from the bytes at the instant it was written. The lane fixed its doc to `:144` by measuring rather than accepting the number this record handed it — which is the correct behaviour and the reason the error stopped here. Recorded beside the original, not over it.

## Correction — 2026-10-02T00:02:31Z (this review's REMEDY DIRECTION — the diagnosis was verified, the prescription was not)

**The "Owed" paragraph above states F5's remedy as `tools/kit_census.py` calling `load_exemptions()`. That is FALSE, and this review had the bytes to refuse it.** Measured at `origin/main` `3705d3d`:

- `load_exemptions()` (`tools/kit_pin.py:218`) returns the **RAW** dict — `return raw, None`. It admits nothing.
- The judgement path is `undeclared_divergence()` (`:221`), which applies the **admission predicate** at `:250-254`: an entry is admitted only if it is a dict carrying a `path`, or a bare string.
- So a census that calls `load_exemptions()` and reports `len(exempt)` **reproduces the over-count** the F5 row exists to name: for `{"exempt": [{"nopath": 1}, {"path": "tools/ledger.py"}]}` the census counts **2**, the pin's `declared` set holds **1**. The remedy this record repeated would have been a **no-op**.

**This was IN scope, not outside it.** The Scope section above declares coverage of "the §9.2 gap table it extends", and §9.2's F5 cell carried the remedy direction. The review verified F5's **diagnosis** to the byte — the second reader at `kit_census.py:290`/`:300` — and did not verify the **remedy** the doc prescribed for it. **The two are independent claims and they fail independently:** a doc can name a defect exactly and prescribe a fix that does not fix it. The artifact's lane caught it and corrected both cells (`3705d3d`); their citation `:248-254` bounds the declared-set construction plus the admission loop, the loop proper being `:250-254`.

**What this review should have done, stated as method rather than as a new rule:** a document's prescribed remedy is a claim **about the code it names**, and it is verifiable the same way the diagnosis is — read the named function and check that it does what the prescription says. Verifying a finding's diagnosis does not verify its remedy direction. Offered to the rubric that owns review method, not asserted here.

Recorded beside the original, not over it.

## Resolution — F5's remedy direction, settled *(appended 2026-10-02T00:08:59Z; beside, not over)*

**Both earlier forms of the remedy are superseded, and the current route is stated here so no reader implements either.** After the lane's `3705d3d` (which replaced the no-op loader call with "`undeclared_divergence()` + the admission predicate"), Meta-Factory HQ ruled the either/or the cell carried and the lane landed the ruling at `c43b8b8`:

- **One route, no new API:** read `declared` off `undeclared_divergence()`'s own return. A shared helper would be a **third reader** — the exact class F5 exists to name.
- **Two caveats, both measured at the bytes this turn:** `declared` is an **int** (`TEMPLATE/tools/kit_pin.py:279`, `len(declared)`), not the list; and the census must also read `exemption_problem` (`:280`), or an **unreadable** exemptions file collapses into **nothing-declared** and `pin_state()`'s `None`-vs-`0` distinction dies (`tools/kit_census.py:296`/`:302`).

**The code is NOT yet changed.** `tools/kit_census.py:290`/`:300` still opens the file independently and reports `len(d.get("exempt") or [])`; the fix is issue **#263**, open, owned by that tool's code owner. What moved at `3705d3d`/`c43b8b8` is the **doc's remedy direction** — the subject of this record's correction — not the census itself.

Verified at `origin/main` this turn, not relayed.
