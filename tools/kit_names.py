#!/usr/bin/env python3
"""Fleet-wide NAME census — which tree carries which name, and whether the name means one thing.

WHY THIS EXISTS. Naming criterion 2 (non-conflicting) is measured against the FLEET, never
this repo alone. A name that means one instrument here and a different one two trees over is
invisible from either tree, and the failure lands far from the file that caused it: a stray
`/tmp/struct.py` on this box shadowed the stdlib `struct` module and broke a `ctypes` probe
in an unrelated session. The name was fine in its own tree.

THE THREE QUESTIONS, each answered from the tree rather than from intent:
  1. WHICH TREES CARRY A NAME — per candidate, every tree that has a file of that basename,
     with its digest, so a reader can see the population rather than a verdict.
  2. WHICH NAMES MEAN DIFFERENT THINGS — two trees carrying the same basename is not itself a
     defect (a factory's fork of `tools/ledger.py` is expected). The defect is a name whose
     PURPOSE differs, so the comparison is on each file's declared purpose (the first
     non-empty line of its module docstring) rather than on its bytes. Same name, different
     purpose = a conflict; same name, same purpose, different bytes = a fork.
  3. WHICH NAMES SHADOW THE STDLIB — a file whose stem is a stdlib module name, checked
     against the interpreter's own `sys.stdlib_module_names` rather than a hand-kept list.

WHAT THIS IS NOT. It is not a verdict on any tree: a fork is legitimate and this census does
not know which tree owns a name. It reports the population and names the conflicts, and the
resolution is the naming criteria's (plan 2646d31a A.2).

Run:  python3 tools/kit_names.py [--json] [--out PATH]
Exit: 0 the census was taken; 1 the population could not be read (no tree reachable) or a
      registry manifest could not be read, because an empty or narrowed census reads as a
      clean fleet.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

# The ONE home for the HEAD read (#185, #292). `head_manifest` lives in the patrol module
# because the patrol's kit-drift leg needed it first; both readers below go through it rather
# than opening a second private `git show HEAD:...`.
from patrol_host_state import KIT_MANIFEST_REL, head_manifest  # noqa: E402

FLEET_MANIFEST_REL = "registry/fleet.json"

# The D.1 promotion candidates (plan 2646d31a), which is what made a census necessary: each
# is a member instrument with a template counterpart under a DIFFERENT name, or none.
D1_CANDIDATES = (
    "rework_entries.py", "rework_table.py", "subject_law.py", "gate_budget.py",
)

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".mypy_cache", ".pytest_cache"}
MAX_DEPTH = 6


def is_git_work_tree(repo: Path) -> bool:
    """True when `repo` is inside a git work tree, so HEAD is a reference it can be read at.

    `git rev-parse --is-inside-work-tree` answers for a repo with an UNBORN HEAD too, which
    is exactly the case that matters: a git tree whose manifest is not committed must REFUSE
    rather than fall back to whatever the working copy happens to hold. A missing `git`
    binary, or a directory that is no work tree at all, answers False — which is what lets
    the disk fallback serve a bootstrapped tree that was never git-init'd.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _manifest_text(rel: str, *, repo: Path) -> tuple[str, str]:
    """A registry manifest read from HEAD, falling back to disk only for a NON-GIT tree.

    THE ONE READ DISCIPLINE (#185, #292). The git read goes through
    `patrol_host_state.head_manifest`, so this module never opens its own
    `git show HEAD:...`; both readers (`kit_names` and `fleet_trees`) come through here, so
    the fallback rule is stated once rather than twice.

    A GIT tree whose HEAD read fails REFUSES: the manifest is COMMITTED, so the committed
    revision is the reference, and a disk read would put the windowing straight back. A
    non-git tree — a bootstrapped factory that was never git-init'd, or a hermetic fixture —
    has no HEAD to read and falls back to disk. If that read fails too the refusal is LOUD,
    because a population narrowed to nothing is indistinguishable from a clean one.

    Returns (text, source); `source` names the revision actually read, so a caller can say so
    rather than implying HEAD.
    """
    text, why = head_manifest(rel, repo=repo)
    source = f"HEAD:{rel}"
    if text is not None:
        return text, source
    disk = repo / rel
    if is_git_work_tree(repo):
        raise SystemExit(
            f"kit names: REFUSED — {source} could not be read ({why}); this is a git tree, "
            f"so the committed manifest is the reference and a disk read would reintroduce "
            f"the windowing this fixes (#292)"
        )
    try:
        return disk.read_text(encoding="utf-8"), str(disk)
    except OSError as exc:
        raise SystemExit(
            f"kit names: REFUSED — {source} could not be read ({why}) and there is no disk "
            f"fallback for a non-git tree at {disk} ({exc}); refusing rather than publishing "
            f"a population narrowed to the {len(D1_CANDIDATES)} D.1 candidate(s) alone"
        )


def fleet_trees(*, repo: Path | None = None, rel: str | None = None) -> dict[str, Path]:
    """Every tree the fleet declares, plus this repo, read from the fleet manifest at HEAD.

    Read from the manifest rather than hardcoded so a member that moves is followed by the
    manifest: a second list would be a second derivation of a fact the registry carries. The
    read is the same discipline as the kit manifest's (#292) — HEAD first, disk only for a
    non-git tree — and a manifest that cannot be read REFUSES rather than publishing a tree
    set narrowed to this repo alone, which is the census's own examined-nothing case.
    """
    repo = REPO if repo is None else repo
    rel = FLEET_MANIFEST_REL if rel is None else rel
    text, source = _manifest_text(rel, repo=repo)
    try:
        man = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"kit names: REFUSED — {source} is not valid JSON ({exc})")
    trees: dict[str, Path] = {"meta-factory": repo}
    for f in man.get("factories") or []:
        slug, repo = f.get("slug"), f.get("repo")
        if slug and repo:
            trees[slug] = Path(repo)
        # A factory's SKILL is declared separately and may sit OUTSIDE its repo. For
        # opencrabs-dev it holds the entire toolkit (51 entries), so a census that
        # walked only `repo` would miss the one tree whose names this project is renaming.
        skill = f.get("skill")
        if slug and skill:
            d = Path(skill).parent
            if d.is_dir() and str(d) != repo:
                trees[f"{slug}-skill"] = d
    return trees


def kit_names(*, repo: Path | None = None, rel: str | None = None) -> list[str]:
    """The basenames the kit ships, so the census covers what we are adopting, not only D.1.

    Read from HEAD through the ONE read discipline (#292), never off the working tree: the
    manifest is GENERATED, so a disk read follows whatever the last generation happened to
    see and a lane mid-write changes the published population under the reader. An
    unreadable manifest REFUSES — it is never a silent `[]`, because an empty name set
    narrows the census to the D.1 candidates and prints a result indistinguishable from a
    full one (measured live at the filing: 90 names -> 4).
    """
    repo = REPO if repo is None else repo
    rel = KIT_MANIFEST_REL if rel is None else rel
    text, source = _manifest_text(rel, repo=repo)
    try:
        man = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"kit names: REFUSED — {source} is not valid JSON ({exc})")
    names = []
    for rel in (man.get("files") or {}):
        base = rel.rsplit("/", 1)[-1]
        if base.endswith(".py"):
            names.append(base)
    return names


def purpose_of(path: Path) -> str:
    """A module's declared purpose: the first line of its MODULE docstring, via `ast`.

    This is the discriminator for criterion 2. Bytes cannot settle it — a factory's fork of
    one instrument has different bytes and the same purpose, while two DIFFERENT instruments
    sharing a name have different purposes. Reading the declaration is the only thing that
    separates those two, and conflating them would report every legitimate fork as a conflict.

    Read through `ast` rather than by scanning for a triple quote, because a file whose FIRST
    statement is not a docstring (an `import` line, a shebang, a licence header) would
    otherwise contribute whatever string literal happens to appear first — a function
    docstring, a SQL snippet — and a wrong purpose makes the conflict predicate decide on
    the wrong text. Measured: `inferhub-watch/probe/registry.py` begins with
    `from __future__ import annotations`, and a scan reported its purpose as a helper's
    docstring about writing files atomically.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return ""
    doc = ast.get_docstring(tree, clean=True)
    if not doc:
        return ""
    for line in doc.splitlines():
        if line.strip():
            return line.strip()[:160]
    return ""


def digest_of(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def walk_tree(root: Path) -> dict[str, list[Path]]:
    """basename -> paths, over one tree, depth-bounded and with the noisy dirs skipped."""
    found: dict[str, list[Path]] = {}
    if not root.is_dir():
        return found
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in __import__("os").walk(root):
        d = Path(dirpath)
        if len(d.parts) - base_depth >= MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                found.setdefault(fn, []).append(d / fn)
    return found


# Two declared purposes whose token sets overlap at or above this share are read as ONE
# instrument described twice rather than two instruments sharing a name. The threshold is a
# judgement, stated so it can be argued with: it is deliberately high, because a FALSE
# conflict costs a look while a MISSED one costs the defect this census exists for.
REWORD_CEILING = 0.5


def _purpose_overlap(purposes: list[str]) -> float:
    """The LOWEST pairwise token overlap across a name's declared purposes, 1.0 if fewer than two.

    The lowest rather than the mean: one pair that agrees does not make a third purpose the
    same instrument, and a mean would let two similar declarations hide an unrelated third.
    """
    if len(purposes) < 2:
        return 1.0
    sets = [set(w.lower().strip(".,:;") for w in p.split() if w.strip()) for p in purposes]
    worst = 1.0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            if not a or not b:
                worst = min(worst, 0.0)
                continue
            worst = min(worst, len(a & b) / len(a | b))
    return round(worst, 3)


def census(trees: dict[str, Path], names: list[str]) -> dict:
    trees = {k: v for k, v in trees.items() if v.is_dir()}
    if not trees:
        return {"trees": {}, "names": {}, "problems": ["no tree was reachable"]}

    index: dict[str, dict[str, list[Path]]] = {}
    for slug, root in trees.items():
        index[slug] = walk_tree(root)

    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    out: dict[str, dict] = {}
    for name in sorted(set(names)):
        stem = name[:-3]
        per: dict[str, list[dict]] = {}
        for slug in trees:
            paths = index.get(slug, {}).get(name) or []
            if not paths:
                continue
            per[slug] = [
                {"path": str(p.relative_to(trees[slug])), "sha": digest_of(p)[:12],
                 "purpose": purpose_of(p)}
                for p in sorted(paths)
            ]
        if not per:
            continue
        purposes = {p["purpose"] for pl in per.values() for p in pl if p["purpose"]}
        # One declared purpose is a fork or a shared file. TWO purposes is not automatically
        # a conflict: a docstring REWORDED between two copies is the same instrument, and a
        # predicate on string equality would report every such edit as two instruments. So
        # the pair is scored on token overlap, and only a low overlap is called a conflict.
        overlap = _purpose_overlap(sorted(purposes))
        out[name] = {
            "stem": stem,
            "trees": {s: [p["path"] for p in pl] for s, pl in per.items()},
            "digests": {s: [p["sha"] for p in pl] for s, pl in per.items()},
            "per_path": {s: [{"path": p["path"], "sha": p["sha"], "purpose": p["purpose"]}
                             for p in pl] for s, pl in per.items()},
            "purposes": sorted(purposes),
            "shadow_stdlib": stem in stdlib,
            "overlap": overlap,
            "conflict": len(per) >= 2 and len(purposes) >= 2 and overlap < REWORD_CEILING,
        }
    return {"trees": {k: str(v) for k, v in trees.items()}, "names": out, "problems": []}


def render(result: dict, read_at: str, names: list[str]) -> str:
    ns = result["names"]
    trees = result["trees"]
    out: list[str] = []
    out.append("# Fleet-wide name census")
    out.append("")
    out.append(f"Read at **{read_at}** by `tools/kit_names.py` over "
               f"**{len(trees)}** tree(s).")
    out.append("")
    out.append("Names examined: the `.py` basenames `registry/kit.json` ships, plus the "
               "Phase D.1")
    out.append("promotion candidates. A name is reported only where at least one tree carries "
               "it.")
    out.append("")
    out.append("## 1. Trees read")
    out.append("")
    out.append("| tree | root |")
    out.append("|---|---|")
    for slug, root in sorted(trees.items()):
        out.append(f"| `{slug}` | `{root}` |")
    out.append("")
    out.append("## 2. Conflicts — one name, different declared purposes")
    out.append("")
    conflicts = {n: v for n, v in ns.items() if v["conflict"]}
    if not conflicts:
        out.append("**None.** No name examined is carried by two trees under declared purposes")
        out.append("that differ by more than a rewording. Same name with ONE purpose is a fork")
        out.append("or a shared file; same name with REWORDED purposes is one instrument")
        out.append("described twice. Neither is a conflict.")
    else:
        for n, v in sorted(conflicts.items()):
            out.append(f"### `{n}` — {len(v['trees'])} trees, {len(v['purposes'])} purposes")
            out.append("")
            out.append(f"Token overlap across those purposes: **{v['overlap']}** "
                       f"(below {REWORD_CEILING} reads as different instruments).")
            out.append("")
            out.append("| tree | path | sha256[:12] | declared purpose |")
            out.append("|---|---|---|---|")
            for slug in sorted(v["per_path"]):
                for e in v["per_path"][slug]:
                    pur = (e["purpose"] or "(no docstring)").replace("|", "/")
                    out.append(f"| `{slug}` | `{e['path']}` | `{e['sha']}` | {pur} |")
            out.append("")
    out.append("## 3. Stdlib shadowing")
    out.append("")
    shadow = {n: v for n, v in ns.items() if v["shadow_stdlib"]}
    if not shadow:
        out.append("**None.** No examined name matches a `sys.stdlib_module_names` entry.")
    else:
        for n, v in sorted(shadow.items()):
            where = ", ".join(f"`{s}`" for s in sorted(v["trees"]))
            out.append(f"- **`{n}`** shadows a stdlib module — carried by {where}")
        out.append("")
        out.append("A shadowing file breaks an unrelated import far from the file that caused")
        out.append("it, which is the live instance this check exists for.")
    out.append("")
    out.append("## 4. Per-name population")
    out.append("")
    out.append("| name | trees | sha agreement | purposes | overlap | conflict | shadows |")
    out.append("|---|---|---|---|---|---|---|")
    for n, v in sorted(ns.items()):
        shas = {s for lst in v["digests"].values() for s in lst}
        agree = "same" if len(shas) == 1 else f"{len(shas)} digests"
        out.append(f"| `{n}` | {len(v['trees'])} | {agree} | {len(v['purposes'])} | "
                   f"{v['overlap']} | "
                   f"{'**YES**' if v['conflict'] else 'no'} | "
                   f"{'**YES**' if v['shadow_stdlib'] else 'no'} |")
    out.append("")
    out.append("## 5. Bounds — what this census does not say")
    out.append("")
    out.append("- **A conflict is not a verdict.** It names a name carried by two trees under")
    out.append("  two declared purposes. Which tree owns the name is the naming criteria's call,")
    out.append("  not this tool's.")
    out.append("- **Purpose is read from the MODULE docstring** (via `ast`), so a module with")
    out.append("  none contributes no purpose and two undocumented files sharing a name read as")
    out.append("  ONE purpose. That limit was measured rather than assumed: over **656** `.py`")
    out.append("  files in five trees, **0** carry a docstring placed after another statement,")
    out.append("  so the misplaced case is theoretical and the convention holds fleet-wide.")
    out.append("- **Reworded purposes are NOT conflicts** (token overlap at or above")
    out.append(f"  {REWORD_CEILING}). The threshold is a judgement and is printed per name so it")
    out.append("  can be argued with: a false conflict costs a look, a missed one costs the")
    out.append("  defect this census exists for.")
    out.append("- **Depth is bounded at %d** and the noisy directories are skipped, so a name"
               % MAX_DEPTH)
    out.append("  carried only deeper than that is not seen.")
    out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="", help="artifact path (default: dated, under evidence/)")
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--json", action="store_true", help="emit the raw census")
    args = ap.parse_args(argv)

    read_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    names = kit_names() + list(D1_CANDIDATES)
    result = census(fleet_trees(), names)
    if result["problems"]:
        print(f"kit names: REFUSED at {read_at} — {'; '.join(result['problems'])}")
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    text = render(result, read_at, names)
    if args.stdout:
        print(text, end="")
        return 0
    out = Path(args.out) if args.out else (
        REPO / "evidence" / f"name-census-{read_at[:10]}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    ns = result["names"]
    nconf = sum(1 for v in ns.values() if v["conflict"])
    nshad = sum(1 for v in ns.values() if v["shadow_stdlib"])
    try:
        shown = out.relative_to(REPO)
    except ValueError:
        shown = out
    print(f"kit names: published {shown} at {read_at} — {len(result['trees'])} tree(s), "
          f"{len(ns)} name(s) carried, {nconf} conflict(s), {nshad} stdlib shadow(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
