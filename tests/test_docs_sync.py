#!/usr/bin/env python3
"""Gate: the documents a factory ships, and the documents its law references.

`TEMPLATE/` is what a new factory bootstraps from. Some documents are carried in
both trees — the methodology core, the review lenses, the subject-matter
skeletons, the add-on packs — and `tests/test_template_sync.py` only guards the
*tool* copies. The documents were therefore unguarded, and they drifted: the
section shipped for issue #30 landed in `docs/methodology/04-harness-binding.md`
and never reached the template, so every factory bootstrapped afterwards would
have been born without it.

Two rules, in two directions (issue #37):

1. **PAIRING.** A path present in both trees is byte-identical. A file that
   genuinely needs to differ is not a pair — it carries a `.tmpl` suffix and
   lives outside the shared path (see `TEMPLATE/processes.md.tmpl`), which is
   also what makes the difference visible instead of silent.

2. **REFERENCE.** Every `docs/<path>.md` a shipped law file names must RESOLVE
   in the member's tree — either shipped at `TEMPLATE/docs/<path>.md`, or a
   SEED the member instantiates (`TEMPLATE/<path>.tmpl`), or a declared
   exemption for a document the MEMBER generates. A reference that resolves to
   nothing tells the member to use a file that ships by nobody: the #37 class,
   where six documents the template's own law named were shipped by no one.

The reference leg PRINTS the population it examined, so `examined 0` is never
the same output as `examined N, 0 problems` — a leg that read nothing must not
read as a leg that found everything clean.

Both legs are probeable and carry a self-probe: `_probe()` builds synthetic
trees on which each leg MUST bite, and the gate refuses to report GREEN when one
has stopped biting. A rule that has only ever seen good input has not been shown
to reject bad input.

Run:  python3 tests/test_docs_sync.py
Exit: 0 in sync (or no template tree), 1 on drift, an unresolved reference, or a
      probe that no longer bites.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHARED_ROOT = "docs"
TEMPLATE_ROOT = "TEMPLATE/docs"
TEMPLATE_TREE = "TEMPLATE"

# Documents a shipped law file names that the MEMBER generates, so their absence
# from `TEMPLATE/docs/` is correct. Each carries its justification; the leg
# prints this population on every run, so a silently-growing list is visible.
REFERENCE_EXEMPTIONS = {
    "factory-registry.md": "generated in the member's own tree by `tools/registry.py render`",
    "projects/hygiene-surfaces.md": "the member's own project note",
    "reference/templates/cron/README.md": "the member's own cron template README",
}

# A `docs/<path>.md` mention inside a shipped law file. Both the markdown-link
# form (`](../docs/x.md)`) and the bare backticked form are captured.
DOC_REF = re.compile(r"docs/([A-Za-z0-9._/-]+\.md)")


def _law_files(root: Path) -> list[str]:
    """Every shipped law file under `root`, repo-relative and sorted.

    A filesystem walk, not `git ls-files`. A tracked-only reader cannot see a
    referrer that is still UNCOMMITTED, so the leg would read GREEN in the very
    worktree that wrote the offending reference and RED in the clone of the
    commit being pushed — the same gate, two verdicts.
    """
    base = root / TEMPLATE_TREE
    if not base.is_dir():
        return []
    out: list[str] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.name.endswith(".md") or path.name.endswith(".md.tmpl"):
            out.append(str(path.relative_to(root)))
    return out


def pairing_leg(root: Path = REPO) -> tuple[int, list[str], list[str]]:
    """The byte-identity direction. Returns (pairs, drifted, missing)."""
    ours = root / SHARED_ROOT
    theirs = root / TEMPLATE_ROOT
    pairs = 0
    drifted: list[str] = []
    missing: list[str] = []
    for template_file in sorted(p for p in theirs.rglob("*") if p.is_file()):
        rel = template_file.relative_to(theirs)
        root_file = ours / rel
        if not root_file.is_file():
            missing.append(str(rel))
            continue
        pairs += 1
        if root_file.read_bytes() != template_file.read_bytes():
            drifted.append(str(rel))
    return pairs, drifted, missing


def reference_leg(
    root: Path = REPO, exemptions: "dict[str, str] | None" = None
) -> tuple[int, list[str], list[str]]:
    """The resolution direction. Returns (examined, unresolved, exempted_hits)."""
    examined = 0
    unresolved: list[str] = []
    exempted: list[str] = []
    declared = REFERENCE_EXEMPTIONS if exemptions is None else exemptions
    for rel in _law_files(root):
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ref in sorted(set(DOC_REF.findall(text))):
            examined += 1
            if (root / TEMPLATE_ROOT / ref).is_file():
                continue  # shipped
            stem = Path(ref).with_suffix("")
            if (root / TEMPLATE_TREE / f"{stem}.md.tmpl").is_file():
                continue  # seed — the member instantiates it
            if ref in declared:
                exempted.append(ref)
                continue
            unresolved.append(f"{rel} names docs/{ref} — shipped by nobody")
    return examined, unresolved, exempted


def _probe() -> list[str]:
    """Show BOTH legs bite, on synthetic trees, before their verdict is trusted.

    A rule that has only ever seen good input has not been shown to reject bad
    input. Five cases: an unresolvable reference, the three ways one RESOLVES
    (shipped, seed, declared exemption), and a drifted pair.
    """
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "TEMPLATE" / "docs").mkdir(parents=True)
        law = root / "TEMPLATE" / "BOOTSTRAP.md"
        law.write_text("see `docs/ghost.md`\n", encoding="utf-8")

        # 1. named by a shipped law file, shipped by nobody, no seed.
        examined, unresolved, _ = reference_leg(root, {})
        if examined != 1:
            problems.append(f"reference leg examined {examined}, expected 1")
        if not any("ghost.md" in u for u in unresolved):
            problems.append("an unresolvable reference was NOT reported")

        # 2. a SEED resolves it — the member instantiates the `.md`.
        (root / "TEMPLATE" / "ghost.md.tmpl").write_text("seed\n", encoding="utf-8")
        if reference_leg(root, {})[1]:
            problems.append("a SEED did not resolve the reference")

        # 3. a SHIPPED copy resolves it.
        (root / "TEMPLATE" / "ghost.md.tmpl").unlink()
        (root / "TEMPLATE" / "docs" / "ghost.md").write_text("x\n", encoding="utf-8")
        if reference_leg(root, {})[1]:
            problems.append("a SHIPPED document did not resolve the reference")

        # 4. a DECLARED exemption resolves it.
        (root / "TEMPLATE" / "docs" / "ghost.md").unlink()
        if reference_leg(root, {"ghost.md": "probe"})[1]:
            problems.append("a DECLARED exemption did not resolve the reference")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "TEMPLATE" / "docs").mkdir(parents=True)
        (root / "docs" / "x.md").write_text("a\n", encoding="utf-8")
        (root / "TEMPLATE" / "docs" / "x.md").write_text("b\n", encoding="utf-8")

        # 5. a pair that differs.
        pairs, drifted, _ = pairing_leg(root)
        if pairs != 1 or drifted != ["x.md"]:
            problems.append(
                f"a drifted pair was NOT reported (pairs={pairs}, drifted={drifted})"
            )
    return problems

def main() -> int:
    probe = _probe()
    if probe:
        print("the gate does not bite:\n", file=sys.stderr)
        for p in probe:
            print(f"  {p}", file=sys.stderr)
        return 1

    theirs = REPO / TEMPLATE_ROOT
    if not theirs.is_dir():
        # A bootstrapped factory has no TEMPLATE/ tree: there is nothing to pair.
        print(f"no {TEMPLATE_ROOT} tree — nothing to pair")
        return 0
    ours = REPO / SHARED_ROOT
    if not ours.is_dir():
        print(f"missing {SHARED_ROOT} tree", file=sys.stderr)
        return 1

    pairs, drifted, missing_in_root = pairing_leg()
    examined, unresolved, exempted = reference_leg()

    rc = 0
    if drifted or missing_in_root:
        rc = 1
        print("documentation drift:\n", file=sys.stderr)
        for d in drifted:
            print(
                f"  {TEMPLATE_ROOT}/{d} differs from {SHARED_ROOT}/{d}",
                file=sys.stderr,
            )
        for m in missing_in_root:
            print(
                f"  {SHARED_ROOT}/{m}: missing — the template ships it, the "
                f"factory does not",
                file=sys.stderr,
            )
        print(
            f"\nRe-copy: cp {SHARED_ROOT}/<path> {TEMPLATE_ROOT}/<path> — then "
            f"re-run this gate. If the two genuinely must differ, rename the "
            f"template copy to <name>.tmpl and move it out of the shared path.",
            file=sys.stderr,
        )

    if unresolved:
        rc = 1
        print("unresolved references:\n", file=sys.stderr)
        for u in unresolved:
            print(f"  {u}", file=sys.stderr)
        print(
            "\nShip the document at TEMPLATE/docs/<path>, ship a seed at "
            "TEMPLATE/<path>.tmpl for the member to instantiate, or add it to "
            "REFERENCE_EXEMPTIONS with its justification (and move the mention "
            "to a shipped surface if the doc is the member's own).",
            file=sys.stderr,
        )

    if rc == 0:
        print(
            f"docs in sync: {pairs} shared document(s) byte-identical; "
            f"references: examined {examined}, "
            f"{len(exempted)} exempt, 0 unresolved; probe: 5 case(s) held"
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
