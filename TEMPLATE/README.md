# The template

The instantiable skeleton. Copy it, fill the placeholders, follow the
checklist.

## Files

| File | What it is |
|---|---|
| [`BOOTSTRAP.md`](BOOTSTRAP.md) | **Start here.** The ordered checklist that takes an empty directory to a running factory. Each step ends with evidence. |
| [`SKILL.md.tmpl`](SKILL.md.tmpl) | The process law — how the factory runs. Becomes the factory's skill file. |
| [`AGENTS.md.tmpl`](AGENTS.md.tmpl) | The repository law — build, test, commit, review. Becomes the factory repo's `AGENTS.md`. |
| [`ONTOLOGY.md.tmpl`](ONTOLOGY.md.tmpl) | Canonical terms and banned synonyms. |
| [`topics.md`](topics.md) | The chat surface spec: which topics exist, what goes in each, how they change. |
| [`roles/`](roles/) | One card per role. A session loads its own card and the law — not the others. |

`.tmpl` files carry `{{PLACEHOLDER}}` markers and are meant to be filled. The
`.md` files are specs you read and adapt, not fill in.

## How to use it

1. Answer the [fill-in variables](../docs/product.md#fill-in-variables).
2. Pick your [add-ons](../docs/addons.md).
3. Walk [`BOOTSTRAP.md`](BOOTSTRAP.md) top to bottom. Do not skip a step's
   evidence — every one of them is a check that has caught a real failure.
4. Delete the `{{PLACEHOLDER}}` markers and the HTML comment guidance blocks
   from the filled files before committing.

## Why the placeholders exist

A template with no placeholders is a document you read and then re-derive from
memory. Placeholders force the decisions — *what does this factory deliver, who
is the authoritative writer, what command decides done* — to be made explicitly
and written down, which is the whole difference between a factory and a repo
some agent edits sometimes.

If a placeholder has no answer yet, write `UNRESOLVED: <what would resolve it>`
rather than deleting it. An unresolved marker is honest; a deleted one is a
decision that will be made silently later, by whoever happens to hit it.

## Versioning

The template is versioned with this repository. A factory records the template
version it was bootstrapped from, so a later change to the template can be
diffed against what the factory actually runs.
