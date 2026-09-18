# Add-on: `roadmap` — mapping processes to products

**Class:** domain · **Status:** proven (the meta-factory) · **Cost:** low — one tool, one document

Take it when the factory must show **which process serves which client product**, and at
what maturity stage, to an audience that does not read the repo.

---

## What it adds

**A roadmap renderer.** `tools/roadmap.py` turns a declared product list into GFM tables
and a Mermaid flowchart — process → product → client → growth stage — and audits the
artifacts each product claims to deliver.

**A process-to-product matrix.** The M:N join that makes the roadmap checkable rather
than decorative: every process names its client, and every declared artifact either
exists or the audit says so.

**A growth-stage ladder.** What changes at each stage, so "we should scale" becomes a
named transition with a mechanism rather than an intention.

---

## Rules

- **The audit is the point.** A roadmap nobody can falsify is decoration. `--audit`
  walks the declared artifacts and returns non-zero when one is missing, so the picture
  cannot drift from the tree.
- **Declare the products, then keep them true.** The tool ships with a product list that
  is **not yours** — see the table below. Replace it before the first audit, or the audit
  measures someone else's factory.
- **A stage with no transition mechanism is a label.** Do not promote a stage until the
  thing that changes at that stage is named.

---

## Costs

One tool and one document, both cheap. The real cost is the second rule above: the tool
arrives carrying a product matrix from the factory it was derived from, and an
un-replaced matrix produces a confident, wrong roadmap. Budget one pass to fill it in.

---

## What changes if the domain is swapped

Drop the pack and the renderer, the matrix and the ladder go with it. The factory still
has work units, a ledger and gates — it simply cannot draw its own shape for an outside
reader.

The audit in `tools/roadmap.py` is the part worth re-homing if you keep anything: it is
the general idea that a declared artifact must be checked for existence, and that idea is
not specific to roadmaps. If you find yourself needing it without the pack, that is a
signal the rule belongs in the core.

---

## Artifacts — what the template ships, and what the factory must create

| Artifact | Status | Detail |
|---|---|---|
| `tools/roadmap.py` | **shipped by the template** | A paired copy. It runs as-is, but its `CANONICAL_PRODUCTS` list is the deriving factory's — **replace it with your own products before the first audit**, or `--audit` reports on a factory that is not yours |
| `docs/growth-stages.md` | **shipped as a skeleton, created by the factory** | The template carries `growth-stages.md.tmpl`, with `{{PLACEHOLDER}}` markers. Filling it is the factory's work; the filled document is not payload |

The template ships the tool and the skeleton. It cannot ship the product list or the
filled ladder — both describe *this* factory, and a template has no products and no
stages of its own.
