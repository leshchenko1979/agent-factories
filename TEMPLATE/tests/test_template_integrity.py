#!/usr/bin/env python3
"""Gate: every file the template ships is accounted for, and every pack is registered.

Two defects, one property: **a file may not exist in the template that no
registry, no pair and no gate accounts for.**

**#33 — an orphan is invisible.** `TEMPLATE/` is the one tree where a file could
be created, abandoned and drift for months. `tests/test_template_sync.py`
deliberately does not guard itself — *"a copy of a pair-guard would need its own
pair-guard"* — which left the template as the one place nothing checked. The
predicted orphan duly appeared: `TEMPLATE/tests/test_template_sync.py` sat stale
until someone grepped for it.

**#35 — a pack is invisible from the documented path.** `TEMPLATE/docs/addons/`
shipped nine pack files while `docs/addons.md` — the page that defines what an
add-on *is* — was not shipped at all, and three of the nine were in no registry.

So this gate asserts, over the **shipped** set:

  every file is exactly one of
    (a) a copy listed in `tests/test_template_sync.py` PAIRS,
    (b) a skeleton — `*.tmpl`,
    (c) a shared document — anything under `docs/`, paired whole-tree by
        `tests/test_docs_sync.py`,
    (d) a role card — `roles/<name>.md`, the law's own cards, paired with nothing
        because a factory chooses its own role set at bootstrap, or
    (e) a declared entry file — an allowlist entry carrying its reason;

  every pack under `docs/addons/` is listed in `docs/addons.md` and carries the
  headings the add-on law requires of its class.

**The shipped set is `git ls-files`, not a filesystem walk.** `TEMPLATE/tests/__pycache__/`
holds six untracked `.pyc` build artifacts, and a `find`-based walk would fail on
them for a reason that has nothing to do with orphans. But a walk that simply
ignored untracked files would miss the opposite defect: a file written and never
`git add`ed is present in the tree and shipped by nobody. So untracked files are
checked too, and the only exclusion is `.gitignore` itself — a `.pyc` is ignored,
a forgotten `docs/x.md` is not.

Run:  python3 tests/test_template_integrity.py
Exit: 0 clean, 1 an unaccounted file or an unregistered pack.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

TEMPLATE_DIR = "TEMPLATE"
PAIR_GUARD = "tests/test_template_sync.py"

# Entry files: shipped, and deliberately not a copy of a factory file. Each
# carries its reason, because an allowlist entry without one is an escape hatch
# with no review surface.
DECLARED: dict[str, str] = {
    "BOOTSTRAP.md": (
        "the bootstrap procedure the operator walks — it describes how to build a "
        "factory, so there is no factory file it could pair with"
    ),
    "README.md": (
        "the template's own map of itself — its subject is the template directory, "
        "which exists only here"
    ),
    "topics.md": (
        "a pointer to the surface binding, kept so the old path still resolves"
    ),
}

SKELETON_SUFFIX = ".tmpl"
SHARED_DOC_PREFIX = "docs/"
# The law's own role cards. They are not copies of a factory file and cannot be:
# a factory chooses its own role set at bootstrap, and `roles/<name>.md` is the
# core set it chooses from. Classified by directory, paired with nothing.
ROLE_CARD_PREFIX = "roles/"

# --- add-on packs -------------------------------------------------------------
# Both are relative to the template's `docs/`, not to the repo root.

ADDONS_DIR = "addons"
REGISTRY = "addons.md"

DOMAIN_HEADINGS = (
    "What it adds",
    "Rules",
    "Costs",
    "What changes if the domain is swapped",
)
BINDING_HEADINGS = (
    "Take it when",
    "What it binds",
    "Costs",
)
BINDING_SWAP = re.compile(r"^##\s+What changes if .+ is swapped\s*$", re.M)

def _rel(path: Path) -> str:
    """A path as the reader sees it — relative to whichever tree it lives in."""
    for base in (REPO, REPO / TEMPLATE_DIR):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.as_posix()

def _template_root() -> Path | None:
    """The tree to classify, or None when there is nothing to classify.

    In this repo the template is a subtree. In a bootstrapped factory there is no
    `TEMPLATE/` — the factory *is* the instantiation — so this gate has nothing to
    say about orphans and returns None, saying so rather than passing quietly.
    """
    candidate = REPO / TEMPLATE_DIR
    return candidate if candidate.is_dir() else None

def _git(*args: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]

def _shipped(template_root: Path) -> tuple[set[str], set[str]]:
    """(shipped, present-but-unshipped), relative to the template root."""
    rel_root = template_root.relative_to(REPO).as_posix()
    prefix = rel_root + "/"

    def under(paths: list[str]) -> set[str]:
        return {p[len(prefix):] for p in paths if p.startswith(prefix)}

    return (
        under(_git("ls-files", "--", rel_root)),
        under(_git("ls-files", "--others", "--exclude-standard", "--", rel_root)),
    )

def _template_pairs() -> set[str]:
    """The copy targets listed in the pair-guard, relative to the template root."""
    text = (REPO / PAIR_GUARD).read_text(encoding="utf-8")
    match = re.search(r"^PAIRS = \[(.*?)^\]", text, re.M | re.S)
    if not match:
        raise RuntimeError(f"{PAIR_GUARD}: no PAIRS list — the copy registry is unreadable")

    pairs: set[str] = set()
    for _original, copy in re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', match.group(1)):
        if not copy.startswith(TEMPLATE_DIR + "/"):
            raise RuntimeError(f"{PAIR_GUARD}: pair target {copy!r} is not under {TEMPLATE_DIR}/")
        pairs.add(copy[len(TEMPLATE_DIR) + 1:])
    if not pairs:
        raise RuntimeError(f"{PAIR_GUARD}: PAIRS parsed empty — the registry shape changed")
    return pairs

def classify(rel: str, pairs: set[str]) -> str | None:
    """The one class this path belongs to, or None when nothing accounts for it."""
    if rel in pairs:
        return "pair"
    if rel.endswith(SKELETON_SUFFIX):
        return "skeleton"
    if rel.startswith(SHARED_DOC_PREFIX):
        return "shared document"
    if rel.startswith(ROLE_CARD_PREFIX):
        return "role card"
    if rel in DECLARED:
        return "declared entry file"
    return None

def check_template(template_root: Path) -> list[str]:
    """Every shipped file classified, and no file present that is not shipped."""
    shipped, unshipped = _shipped(template_root)
    pairs = _template_pairs()
    problems: list[str] = []

    for rel in sorted(shipped):
        if classify(rel, pairs) is None:
            problems.append(
                f"{TEMPLATE_DIR}/{rel}: no pair in {PAIR_GUARD}, no {SKELETON_SUFFIX} "
                f"suffix, not under {SHARED_DOC_PREFIX} or {ROLE_CARD_PREFIX}, and not "
                f"a declared entry file — nothing accounts for it"
            )

    for rel in sorted(unshipped):
        problems.append(
            f"{TEMPLATE_DIR}/{rel}: present in the tree but not shipped — `git add` it "
            f"or remove it. A file that is neither committed nor ignored is invisible "
            f"to every other gate, so it cannot be reviewed either"
        )

    for rel in sorted(pairs):
        if rel not in shipped:
            problems.append(f"{TEMPLATE_DIR}/{rel}: listed in PAIRS but not shipped")

    return problems

def _headings(path: Path) -> list[str]:
    return [
        h.strip()
        for h in re.findall(r"^##\s+(.+?)\s*$", path.read_text(encoding="utf-8"), re.M)
    ]

def check_addons(template_root: Path) -> list[str]:
    """Every pack is registered, and carries the headings its class requires."""
    docs = template_root / "docs"
    packs_dir = docs / ADDONS_DIR
    registry = docs / REGISTRY

    if not packs_dir.is_dir():
        return []

    if not registry.is_file():
        return [
            f"{_rel(registry)}: the pack law is not shipped while {ADDONS_DIR}/ is — a "
            f"factory receives the packs and no page defining what an add-on is"
        ]

    registered = set(
        re.findall(r"\]\(addons/([^)\s]+)\)", registry.read_text(encoding="utf-8"))
    )
    problems: list[str] = []

    # The reverse direction: a registered pack must actually be shipped. Without
    # this the registry can name a pack the template does not carry, and the
    # documented path leads nowhere — the same defect as an unregistered pack,
    # seen from the other side.
    for rel in sorted(registered):
        if not (packs_dir / rel).is_file():
            problems.append(
                f"{_rel(registry)}: lists {rel!r} but the template ships no such pack "
                f"— the documented path leads nowhere"
            )

    for pack in sorted(packs_dir.rglob("*.md")):
        rel = pack.relative_to(packs_dir).as_posix()
        if rel not in registered:
            problems.append(
                f"{_rel(pack)}: not listed in {_rel(registry)} — an unregistered pack "
                f"is reachable only by accident, never from the documented path"
            )
            continue

        headings = _headings(pack)
        if rel.startswith("domain/"):
            missing = [h for h in DOMAIN_HEADINGS if h not in headings]
            if missing:
                problems.append(
                    f"{_rel(pack)}: a domain pack is missing "
                    + ", ".join(repr(m) for m in missing)
                )
        else:
            missing = [h for h in BINDING_HEADINGS if h not in headings]
            if missing:
                problems.append(
                    f"{_rel(pack)}: a binding is missing "
                    + ", ".join(repr(m) for m in missing)
                )
            if not BINDING_SWAP.search(pack.read_text(encoding="utf-8")):
                problems.append(
                    f"{_rel(pack)}: a binding must state 'What changes if <the bound "
                    f"thing> is swapped' — that list is what proves the pack did not "
                    f"leak into the core"
                )

    return problems

def check(template_root: Path) -> list[str]:
    """Every problem in the template tree. Empty means clean."""
    return check_template(template_root) + check_addons(template_root)

def main() -> int:
    template_root = _template_root()
    if template_root is None:
        print("no TEMPLATE/ tree — the factory is the instantiation, nothing to classify")
        return 0

    problems = check(template_root)
    if problems:
        print("template integrity problems:\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print(
            "\nA file in TEMPLATE/ must be a copy listed in PAIRS, a .tmpl skeleton, a\n"
            "shared document under docs/, a role card under roles/, or a declared entry\n"
            "file with a reason. A pack under docs/addons/ must be listed in\n"
            "docs/addons.md and carry the headings its class requires.",
            file=sys.stderr,
        )
        return 1

    shipped, _ = _shipped(template_root)
    packs = list((template_root / "docs" / ADDONS_DIR).rglob("*.md"))
    print(
        f"template integrity clean: {len(shipped)} shipped file(s) classified, "
        f"{len(packs)} pack(s) registered"
    )
    return 0

def test_every_shipped_template_file_is_accounted_for() -> None:
    template_root = _template_root()
    if template_root is None:
        return
    problems = check(template_root)
    assert not problems, "unaccounted template files: " + "; ".join(problems)

if __name__ == "__main__":
    raise SystemExit(main())
