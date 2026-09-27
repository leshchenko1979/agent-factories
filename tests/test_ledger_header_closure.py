#!/usr/bin/env python3
"""Gate: the ledger header's declared closure equals its ACTUAL intra-repo imports.

Predicate, with its population printed on every run: parse the `Closure:` declaration
from `tools/ledger.py`'s module docstring, derive the set of modules that file actually
imports from its own directory, and assert the two sets are EQUAL.

Why the law exists. The header told a factory to copy the file byte-identically, and the
file is not standalone: it imports three siblings, so a faithful copy dies at import with
`ModuleNotFoundError`, and the kit's real unit -- a closure plus a per-factory event set --
was nowhere stated. meta-factory #137, reported by a member factory that hit it.

Both directions are violations, and each means something different:
  STATED omits an import   the header UNDERSTATES the unit, so a copying factory is misled
  STATED names a non-import the header carries a STALE name, so a reader trusts a module
                           the file no longer needs

The declaration is a marker rather than prose for the same reason the repo's other
declarations are: a claim in a sentence cannot be compared to anything, and the defect this
gate exists to prevent was exactly a claim in a sentence that nothing checked.

Run:  python3 tests/test_ledger_header_closure.py
Exit: 0 the declaration matches, in both trees; 1 a mismatch, a missing declaration, or a
      probe that failed to bite.
"""

from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The shipped tool and the repo-side tool. Both are scanned because BOTH trees are copied
# from: a drift in either half reaches somebody.
SCANNED = ("tools/ledger.py", "TEMPLATE/tools/ledger.py")

DECLARATION_RE = re.compile(r"^Closure:\s*(.+?)\s*$", re.MULTILINE)
DEFERRED_RE = re.compile(r"^Deferred:\s*(.+?)\s*$", re.MULTILINE)

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def declared_closure(source: str, regex: re.Pattern[str] = DECLARATION_RE) -> set[str] | None:
    """The module filenames the docstring declares under `regex`, or None when it declares none."""
    doc = ast.get_docstring(ast.parse(source)) or ""
    m = regex.search(doc)
    if not m:
        return None
    return {tok.strip() for tok in m.group(1).split(",") if tok.strip()}


def actual_closure(path: Path, source: str | None = None, *, deferred: bool = False) -> set[str]:
    """The modules this file imports FROM ITS OWN DIRECTORY, by KIND.

    `deferred=False` (default) collects MODULE-LEVEL imports only: a tree missing one of
    these dies at import. `deferred=True` collects imports nested inside functions, which a
    factory can be missing and still start — the call degrades instead.

    Resolved by asking whether `<module>.py` exists beside the file, never by matching a
    name: a stdlib or third-party import that happens to share a sibling's name is a
    different object, and a name-keyed predicate cannot tell them apart.
    """
    src = source if source is not None else path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    # Module-level imports are the tree body's direct children; anything deeper is deferred.
    top_level_ids = {id(n) for n in tree.body}
    found: set[str] = set()
    for node in ast.walk(tree):
        nested = id(node) not in top_level_ids
        if nested != deferred:
            continue
        mods: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
        for mod in mods:
            if (path.parent / f"{mod}.py").is_file():
                found.add(f"{mod}.py")
    return found


def problems_for(path: Path, source: str | None = None) -> list[str]:
    """The one predicate. Returns a list of named problems, empty when the pair agrees."""
    src = source if source is not None else path.read_text(encoding="utf-8")
    out: list[str] = []
    for kind, regex, is_deferred in (("Closure", DECLARATION_RE, False),
                                     ("Deferred", DEFERRED_RE, True)):
        stated = declared_closure(src, regex)
        if stated is None:
            out.append(f"{path}: the module docstring declares no `{kind}:` line, so the unit "
                       f"a factory copies is unstated for that kind and this leg examined "
                       f"nothing")
            continue
        actual = actual_closure(path, src, deferred=is_deferred)
        for mod in sorted(actual - stated):
            out.append(f"{path}: imports `{mod}` at "
                       f"{'call' if is_deferred else 'module'} level but the {kind} declaration "
                       f"omits it — the header UNDERSTATES the unit a factory copies")
        for mod in sorted(stated - actual):
            out.append(f"{path}: declares `{mod}` under {kind} but does not import it that way "
                       f"— a STALE name a reader would trust")
    return out


def probes() -> None:
    """The gate must BITE, driven from constructed sources rather than today's prose."""
    good = '''#!/usr/bin/env python3
"""A tool.

Closure: alpha.py, beta.py
Deferred: gamma.py
"""
import alpha
from beta import thing


def use():
    import gamma
    return gamma
'''
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "alpha.py").write_text("x = 1\n", encoding="utf-8")
        (root / "beta.py").write_text("thing = 1\n", encoding="utf-8")
        (root / "gamma.py").write_text("y = 1\n", encoding="utf-8")
        (root / "tool.py").write_text(good, encoding="utf-8")

        # CONTROL — a matching declaration is clean, so the probes below are about the
        # declaration rather than about the predicate reding on everything.
        check("CONTROL: a declaration matching the imports is clean",
              problems_for(root / "tool.py") == [],
              "alpha + beta at module level, gamma deferred — each declared under its kind")

        # BITE 1 — an import the declaration OMITS.
        omitted = good.replace("Closure: alpha.py, beta.py", "Closure: alpha.py")
        (root / "tool.py").write_text(omitted, encoding="utf-8")
        probs = problems_for(root / "tool.py")
        check("BITE: an import the declaration OMITS is reported, naming the module",
              any("beta.py" in p and "UNDERSTATES" in p for p in probs), probs[:1])

        # BITE 2 — a name the file does NOT import.
        stale = good.replace("Closure: alpha.py, beta.py",
                             "Closure: alpha.py, beta.py, delta.py")
        (root / "tool.py").write_text(stale, encoding="utf-8")
        probs = problems_for(root / "tool.py")
        check("BITE: a declared module the file does NOT import is reported as STALE",
              any("delta.py" in p and "STALE" in p for p in probs), probs[:1])

        # BITE 3 — the WRONG KIND. `gamma` is imported inside a function; declaring it
        # under Closure claims the file dies at import when it does not, and leaves the
        # Deferred set short — both directions of the same misstatement.
        wrong_kind = good.replace("Deferred: gamma.py", "Deferred: alpha.py")
        (root / "tool.py").write_text(wrong_kind, encoding="utf-8")
        probs = problems_for(root / "tool.py")
        check("BITE: an import declared under the WRONG KIND is reported both ways",
              any("Deferred declaration omits" in p for p in probs), probs[:1])

        # BITE 4 — no declaration at all is a FAILURE, never a vacuous pass.
        (root / "tool.py").write_text(good.replace("Closure: alpha.py, beta.py\n", "")
                                      .replace("Deferred: gamma.py\n", ""), encoding="utf-8")
        probs = problems_for(root / "tool.py")
        check("BITE: a docstring with NO declaration is a failure, not a clean read",
              len(probs) == 2 and all("examined nothing" in p for p in probs), probs[:1])


def main() -> int:
    print("ledger header closure — the declared unit equals the real one (meta-factory #137)")
    total = 0
    for rel in SCANNED:
        path = REPO / rel
        if not path.is_file():
            print(f"  SKIPPED  {rel} — absent from this tree")
            continue
        probs = problems_for(path)
        total += 1
        if probs:
            for p in probs:
                print(f"  FAIL  {p}")
                _failures.append(p)
        else:
            stated = declared_closure(path.read_text(encoding="utf-8")) or set()
            deferred = declared_closure(path.read_text(encoding="utf-8"), DEFERRED_RE) or set()
            print(f"  PASS  {rel}: {len(stated)} module-level + {len(deferred)} deferred "
                  f"declared, imports exactly those — {', '.join(sorted(stated))}"
                  f" | deferred: {', '.join(sorted(deferred))}")

    if total == 0:
        print("  FAIL  no scanned file exists — the population is empty, so nothing was judged")
        _failures.append("empty population")

    probes()

    if _failures:
        print(f"ledger header closure FAILED: {len(_failures)} problem(s)")
        return 1
    print(f"ledger header closure passed — {total} file(s) judged, declaration equals imports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
