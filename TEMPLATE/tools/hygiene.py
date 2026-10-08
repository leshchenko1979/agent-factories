#!/usr/bin/env python3
"""Workspace hygiene tool — upholds Process 4 (Workspace Hygiene Sweep).

Prevents host resource exhaustion and recovery failures by auditing and reaping
stale scratch scripts, temporary run artifacts, untracked repository clutter,
and modified tracked working-tree files.

## In-flight is not stranded (issue #38)

This factory's working tree is SHARED. Several lanes edit it at once, so "a path is
dirty" and "a path was abandoned" are different facts, and an audit that cannot tell
them apart is a race, not a health signal: it goes RED whenever a peer lane is
mid-task, and the daily pacemaker then reports DEGRADED on a healthy factory.

The discriminator git actually offers is **age**. A file written two minutes ago
belongs to a lane that is still working; the same file a day later is stranded. So
the audit now classifies every finding as one of:

  * **violation** — fails the gate;
  * **advisory** — printed, does not fail, because it may be a lane's live work.

| Finding | Class |
|---|---|
| stale owned scratch (`/tmp/<this-factory>-*`, older than `MAX_AGE_HOURS`) | violation — already age-based |
| untracked litter (`*.bak` `*.tmp` `*.log` `*.orig`) | violation, no grace — litter is litter |
| untracked other (a new file) | advisory while younger than the grace window, then violation |
| modified tracked file | advisory while younger than the grace window, then violation |
| a path named by `--require-committed` | violation regardless of age |

The grace window is declared by the caller (`--grace-minutes`, default 60) rather
than hidden in this file, because how long a lane may hold a file is a property of
the factory's process, not of this tool.

**Why age and not an allowlist.** #38 warned against a fix that exempts
`evidence/ledger.jsonl` by path: it removes that one case and leaves the general one
(a peer's in-flight gate file). The general form is the same for every path, so the
rule is the same for every path.

**Why #28 stays fixed.** #28 was a *false green*: the audit reported clean without
examining modified tracked files at all. It still examines them, and a stranded one
still fails — it now has to be older than the window to be judged stranded, which is
what "stranded" means. The measurement run's own-artifact invariant gets the sharper
form: `--require-committed <path>` fails on a fresh dirty path with no grace at all,
because the run knows which artifacts are its own.

**The run-scoped form does NOT exist, and this docstring used to claim it did.** The
sentence "a whole-tree check and a run-scoped check ... the run-scoped one is the
blocking one" promised a narrowing the tool has never had, and a reader who believed it
went looking for a flag that is not here (#201, ruled 2026-09-28). The claim is
WITHDRAWN rather than made true, because the two are not the same thing and only one of
them is honest. `<path>` is named because a reader must not infer a form that does not exist.

The real contract, stated so nothing has to be inferred:

  * the walk is WHOLE-TREE and every invocation gets it — nothing narrows it, and
    `--grace-minutes N` moves the boundary for every path, which is why #38 refused it as
    an allowlist by the back door;
  * a run declares its OWN artifacts with `--require-committed <path>`, which ADDS a leg
    and never removes one: it catches a run that has not committed its own output, and it
    is deliberately not a way to stop looking at anyone else's;
  * a foreign stranded path is therefore a state the run must RECORD, not one it can
    silence: the closing invariant admits the second verdict
    `workspace_gate=blocked-by-unowned`, lawful only when the run NAMES the blocking paths,
    and never a forged clean.

## Build residue is DECLARED OUT and PRINTED, never reaped (G3; q15, ruled 2026-09-30)

pytest and ruff write a `.gitignore` containing `*` into the cache they create, so
`__pycache__/`, `.pytest_cache/`, `.ruff_cache/` and `.audit.lock` are SELF-IGNORING:
absent from `git status`, excluded from `registry/kit.json` as transient, and outside this
tool's `/tmp`-only glob. They are invisible to every leg above -- the class that reads as
clean because nothing looked, which is the one failure mode this instrument exists to
catch.

They are not reaped, and the ruling is why: a worktree's cache is that worktree's and dies
with the tree, and a reap races a test that is running. What is owed instead is that the
class be MEASURED, so "we chose not to reap it" can never read as "there is none". So
`build_residue_leg()` prints the population on every run and declares `removes: no` -- the
#220 shape (a report leg, never a widened glob), which G6 reuses for the same reason.

**The bound travels with the number.** The walk is depth-bounded and the bound is
MEASURED, not chosen: over the live census on 2026-10-02 the population by depth was
1:42, 2:132, 3:48, 4+:0, so depth 3 carries the whole class and a deeper walk buys nothing.
Cost is the argument for `find` over `os.walk` -- the same 222 items took 0.19-0.49s warm
through one `find` where an unbounded Python walk took 7.0s cold, against a cap of a few
seconds; a gate KILLED by its own budget reads to every reader as a red.
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# A gate may only glob a namespace this factory OWNS.
#
# `/tmp` is shared. Another factory's tooling writes its own prefix there — a
# busy sibling can leave thousands of scratch files under a prefix it owns. Globbing a
# foreign prefix makes this gate measure someone else's litter: it goes RED for
# work this factory did not do, the mirror of a false green and just as
# corrosive, because a gate that cries wolf gets ignored and then reverted.
#
# The owned namespace is the repository directory name, so a factory
# bootstrapped from this template owns its own prefix automatically. Extra owned
# namespaces are declared with --scratch-glob, never by widening this list to a
# prefix somebody else already uses.
NAMESPACE = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def scratch_patterns_for(namespace: str) -> list[str]:
    """The scratch globs a factory owning `namespace` may inspect.

    Factored out of the module constant so `--namespace` moves the population
    through the SAME expression the default uses. A second copy of the glob
    shape would let the flag and the default drift apart, which is the class
    this factory files against.
    """
    return [f"/tmp/{namespace}-*"]

SCRATCH_PATTERNS = scratch_patterns_for(NAMESPACE)

# The declaration the reaper consults before it unlinks. AGE ALONE cannot tell a
# stale scratch file from LIVE STATE: a lock created once and held long-term has
# an mtime nothing refreshes, so it is indistinguishable from litter by the only
# discriminator this tool has. The file is FACTORY DATA and never ships; the
# skeleton beside it (`docs/hygiene-protected.example.json`) is what a factory
# copies. An ABSENT file means this factory has declared no live paths, which is
# the shipped state of a new factory; a file that EXISTS and cannot be read is a
# reported problem, because only the silent failure is the hazard.
PROTECTED_REL = "docs/hygiene-protected.json"

def repo_root() -> Path:
    """The tree this copy of the tool belongs to."""
    return Path(__file__).resolve().parent.parent

def load_declaration(root: Path | None = None) -> tuple[list[dict], list[dict], list[str]]:
    """(protected, scratch, problems) read from the factory's declaration.

    `protected` entries name paths the reaper must SKIP; `scratch` entries name
    paths that are genuinely reapable, classified so the classifier gate can tell
    a declared literal from a new one. Both are lists of dicts with `path` and
    `why`; `why` is REQUIRED, because an entry nobody could defend in the output
    is one that should be fixed instead.

    An entry that matches nothing is PRINTED but is NOT a problem: this is a
    PREVENTION surface, and the point is to declare a path BEFORE the code that
    creates it lands. That is the one deliberate difference from the exemption
    surfaces, where an unmatched entry is a stale debt.
    """
    root = root or repo_root()
    path = root / PROTECTED_REL
    if not path.is_file():
        return [], [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [], [f"{PROTECTED_REL} exists but cannot be read: {exc}"]

    problems: list[str] = []
    out: dict[str, list[dict]] = {"protected": [], "scratch": []}
    for kind in ("protected", "scratch"):
        entries = data.get(kind, [])
        if not isinstance(entries, list):
            problems.append(f"{PROTECTED_REL}: `{kind}` must be a list")
            continue
        for i, entry in enumerate(entries):
            where = f"{PROTECTED_REL}: {kind}[{i}]"
            if not isinstance(entry, dict):
                problems.append(f"{where} must be an object")
                continue
            p, why = entry.get("path"), entry.get("why")
            if not isinstance(p, str) or not p.startswith("/tmp/"):
                problems.append(f"{where}: `path` must be an absolute /tmp path")
                continue
            if not isinstance(why, str) or not why.strip():
                problems.append(f"{where} ({p}): `why` is required and blank")
                continue
            out[kind].append(entry)
    return out["protected"], out["scratch"], problems

MAX_AGE_HOURS = 24

# How long a dirty path may be explained as a lane still working on it. The
# default is a floor, not a recommendation: a factory whose lanes routinely hold
# work longer raises it with --grace-minutes, in its own process law.
DEFAULT_GRACE_MINUTES = 60

LITTER_SUFFIXES = (".bak", ".tmp", ".log", ".orig")

def reap_stale_scratch(
    dry_run: bool = False,
    patterns: list[str] | None = None,
    protected: set[str] | None = None,
) -> tuple[int, list[str]]:
    """Audit and optionally reap scratch artifacts older than MAX_AGE_HOURS.

    Only the namespaces passed in (default: the ones this factory owns) are
    inspected; a foreign prefix is never globbed. `protected` is the set of paths
    DECLARED LIVE (`docs/hygiene-protected.json`): a protected path is skipped
    entirely — never reported as stale, never unlinked — because age alone cannot
    tell it from litter (#153).
    """
    now = time.time()
    cutoff = now - (MAX_AGE_HOURS * 3600)
    protected = protected or set()
    found: list[str] = []
    reaped = 0

    for pattern in (patterns or SCRATCH_PATTERNS):
        for path in glob.glob(pattern):
            if path in protected:
                continue
            try:
                mtime = os.path.getmtime(path)
                if mtime < cutoff:
                    age_h = int((now - mtime) / 3600)
                    found.append(f"{path} (age: {age_h}h)")
                    if not dry_run:
                        if os.path.isdir(path):
                            shutil.rmtree(path, ignore_errors=True)
                            reaped += 1
                        else:
                            os.remove(path)
                            reaped += 1
            except Exception:
                pass

    return (len(found) if dry_run else reaped), found

# --- Worktree census: ONE `git worktree list`, shared by the G3 and G6 legs -----------

"""The tree census both worktree-reading legs share, and why it lives this high up.

`build_residue_leg` takes `registered_worktrees` as a DEFAULT ARGUMENT, and Python
evaluates a default at definition time -- so the census has to be bound before that
`def` runs, not merely before the leg is called. One census for both legs is also the
point: two `git worktree list` calls would be two populations free to disagree between
themselves, and the G3 leg would then report a residue count over a tree set the G6 leg
had never seen.
"""

WORKTREE_STALE_HOURS = 24.0

def worktree_records(root: Path | None = None) -> tuple[list[dict], str | None]:
    """(records, error) for every tree `git worktree list` reports.

    Each record carries the path git reports, the tree's HEAD, its branch when it is on
    one, and git's own `prunable` reason when it declares one. The census is git's OWN,
    never a `/tmp` glob: a scratch prefix would miss the MAIN tree and every tree named
    outside the namespace, and would sweep a directory belonging to nobody -- the
    #174/#220 class this factory files against. An unreadable census is an ERROR and never
    an empty one: "no trees" and "the instrument failed" must not render as one verdict.
    """
    root = root or repo_root()
    try:
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    except OSError as exc:
        return [], f"`git worktree list` could not run: {exc}"
    if proc.returncode != 0:
        return [], f"`git worktree list` exited {proc.returncode}: {proc.stderr.strip()}"
    records: list[dict] = []
    for block in proc.stdout.strip().split("\n\n"):
        if not block.strip():
            continue
        record: dict = {"path": None, "head": None, "branch": None,
                        "detached": False, "prunable": None}
        for line in block.splitlines():
            if line.startswith("worktree "):
                record["path"] = line[len("worktree "):].strip()
            elif line.startswith("HEAD "):
                record["head"] = line[len("HEAD "):].strip()
            elif line.startswith("branch "):
                record["branch"] = line[len("branch "):].strip()
            elif line.startswith("detached"):
                record["detached"] = True
            elif line.startswith("prunable"):
                record["prunable"] = line[len("prunable"):].strip() or "prunable"
        if record["path"]:
            records.append(record)
    if not records:
        return [], "`git worktree list` reported no tree, which a repository cannot do"
    return records, None

def registered_worktrees(root: Path | None = None) -> tuple[list[str], str | None]:
    """(paths, error) -- the path half of `worktree_records`.

    Kept as its own name because the build-residue leg reads only the paths, and both legs
    share ONE census: two `git worktree list` calls would be two populations that could
    disagree between them.
    """
    records, error = worktree_records(root)
    if error:
        return [], error
    return [record["path"] for record in records], None

# --- Build residue: DECLARED OUT, PRINTED (G3; q15, ruled 2026-09-30) -----------------
#
# The class pytest and ruff create and then HIDE: each writes a `.gitignore` containing `*`
# into the cache it makes, so the directory is self-ignoring -- absent from `git status`,
# excluded from the manifest as transient, and outside this tool's `/tmp`-only glob. It is
# invisible to every leg above, which is why it is PRINTED rather than swept: the debt is
# the silence, not the bytes.
#
# NOT reaped, by ruling: a worktree's cache is that worktree's and dies with the tree, and
# a reap races a test that is running. The #220 shape -- a report leg, `removes: no`, never
# a widened glob -- is what G6 reuses for the same reason.
BUILD_RESIDUE_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache", ".audit.lock")

# MEASURED, not chosen (2026-10-02, live census): the population by depth was 1:42, 2:132,
# 3:48, 4+:0 -- so depth 3 carries the whole class and a deeper walk buys nothing while
# costing the gate's budget. `find` rather than `os.walk` for the same reason: the same 222
# items read in 0.19-0.49s warm through one `find` where an unbounded Python walk took 7.0s
# cold, and a gate KILLED by its own cap reads to every reader as a red.
BUILD_RESIDUE_MAXDEPTH = 3

# Never descended: a nested checkout or an installed environment is not THIS tree's
# residue, and following one would report another repository's caches as ours.
BUILD_RESIDUE_PRUNE = (".git", "node_modules", ".venv", "venv")

def _find_residue(roots: list[str]) -> list[str]:
    """The residue names under `roots`, by ONE bounded `find`.

    One process for every root, not one per root: the cost is in the spawn, and the same
    population read in a single `find` is what keeps this leg inside the gate's cap.
    """
    if not roots:
        return []
    names: list[str] = []
    for name in BUILD_RESIDUE_NAMES:
        names += ["-name", name, "-o"]
    names = names[:-1]
    prune: list[str] = []
    for name in BUILD_RESIDUE_PRUNE:
        prune += ["-name", name, "-prune", "-o"]
    cmd = [
        "find", *roots, "-maxdepth", str(BUILD_RESIDUE_MAXDEPTH),
        *prune, "(", "(", *names, ")", "-print", ")",
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except OSError:
        return []
    return [line for line in proc.stdout.splitlines() if line]

def build_residue_leg(
    worktrees_fn=registered_worktrees,
    find_fn=_find_residue,
) -> dict:
    """The build-residue report leg: the population, PRINTED, and `removes: no`.

    DECLARED OUT rather than reaped (q15). The report IS the mechanism, so this leg holds
    no removal path at all, and `removes` is asserted False here so a reader of the REPORT
    is told the same thing the code does (#220). Both the census and the walk are injected
    so a probe can drive the leg over a throwaway tree rather than the live host.
    """
    paths, error = worktrees_fn()
    coverage: dict = {
        "class": "build residue (pytest/ruff caches, .audit.lock)",
        "predicate": (
            f"one `find <worktree> -maxdepth {BUILD_RESIDUE_MAXDEPTH}` per census, for "
            f"{', '.join(BUILD_RESIDUE_NAMES)}"
        ),
        "maxdepth": BUILD_RESIDUE_MAXDEPTH,
        "worktrees_total": len(paths),
        "removes": False,
    }
    if error:
        # An unreadable census is NOT RUN with its reason, never a clean zero: a leg that
        # cannot see its population must not print one.
        coverage["status"] = "NOT RUN"
        coverage["reason"] = error
        return coverage

    live = [p for p in paths if os.path.isdir(p)]
    found = find_fn(live)
    counts = {name: 0 for name in BUILD_RESIDUE_NAMES}
    for item in found:
        base = os.path.basename(item)
        if base in counts:
            counts[base] += 1
    coverage["status"] = "ASSERTED"
    coverage["items"] = len(found)
    coverage["counts"] = counts
    coverage["paths"] = found
    return coverage

def render_build_residue(coverage: dict) -> str:
    """The leg's one line, carrying its population AND its `removes: no`.

    The counts are printed BY NAME and only where non-zero, so a clean run still states
    which class was read rather than rendering a bare zero a reader cannot attribute.
    """
    if coverage.get("status") != "ASSERTED":
        return (
            "hygiene build residue: NOT RUN — "
            f"{coverage.get('reason') or 'reason not stated'}"
        )
    counts = coverage["counts"]
    parts = ", ".join(f"{name} {counts[name]}" for name in BUILD_RESIDUE_NAMES if counts[name])
    return (
        f"hygiene build residue: {coverage['items']} item(s) over "
        f"{coverage['worktrees_total']} worktree(s) — {parts or 'none of the four names'} "
        f"(declared out, q15; removes: no)"
    )

# --- Declaration surfaces: an entry whose target is gone is a STALE DEBT (G2) ---------
#
# The class this file's OWN docstring names and nothing acted on: "the exemption
# surfaces, where an unmatched entry is a stale debt" (`load_declaration` above). Each
# surface's own tool reads its own file and checks it for READABILITY; not one of them
# asks whether the thing an entry POINTS AT still exists. So an exemption left behind by a
# rename or a deletion sits here looking live, and every surface still reads green.
#
# REPORT-ONLY, and it holds no write path: each surface's own tool owns its own file, and
# a second writer over one population is the defect this factory files against. The leg's
# job is to make the debt VISIBLE on every run, so "we checked" and "nobody looked" stop
# rendering as the same output.
#
# TWO TARGET KINDS, and the choice is stated rather than implied. An entry is swept where
# its target is a PATH in this tree or a COMMIT in this history: both are LOCAL, both are
# decidable without the network, and both go stale in exactly the way this gap describes.
# Every family whose entries name something ELSE is DECLARED below with its reason, so the
# population is all fifteen and a zero on any line is a verdict rather than a silence.
DECL_PATH = "path"
DECL_COMMIT = "commit"

# (family, live file, probes, note). A probe is (container, field, kind): `container` None
# means the file's TOP LEVEL, and `field` None means the container's own KEYS are the
# targets. `note` is REQUIRED on a family with no probes -- it is what makes an unswept
# family a declaration rather than an omission.
DECLARATION_SURFACES: tuple[
    tuple[str, str, tuple[tuple[str | None, str | None, str], ...], str], ...
] = (
    ("close-board-exemptions", "docs/close-board-exemptions.json", (),
     "entries name a BOARD ISSUE (`subject`) and a ledger row `n`, neither of which this "
     "leg can read offline"),
    ("hygiene-protected", "docs/hygiene-protected.json", (),
     "a PREVENTION surface by its own docstring -- an unmatched entry is legal, not a "
     "debt -- and its targets are absolute /tmp paths, not tree paths"),
    ("law-uuid-exemptions", "docs/law-uuid-exemptions.json",
     (("exempt", "path", DECL_PATH),), ""),
    ("ledger-authorizations", "docs/ledger-authorizations.json", (),
     "entries name LANES (actors and by_event values), not a path or a commit"),
    ("ledger-commit-exemptions", "docs/ledger-commit-exemptions.json",
     (("exemptions", "sha", DECL_COMMIT),), ""),
    ("ledger-exemptions", "docs/ledger-exemptions.json", (),
     "entries name a BOARD ISSUE (`subject`), which this leg cannot read offline"),
    ("ledger-invariants", "docs/ledger-invariants.json", (),
     "entries are dates and ledger row numbers, neither of which a rename can strand"),
    ("ledger-no-shrink-exemptions", "docs/ledger-no-shrink-exemptions.json",
     (("exemptions", "sha", DECL_COMMIT),), ""),
    ("ledger-refs-kinds", "docs/ledger-refs-kinds.json", (),
     "entries are ledger VOCABULARY names (kinds and events), not a target object"),
    ("ledger-retirements", "docs/ledger-retirements.json", (),
     "entries name LEDGER ROWS, and the ledger is append-only -- a row cannot be stranded"),
    ("ledger-schema-exemptions", "docs/ledger-schema-exemptions.json", (),
     "entries are keyed by ledger row `n`; the same append-only reason as above"),
    ("products", "docs/products.json", (),
     "entries are product records, whose `id` is an internal label and not a tree object"),
    ("rework-relative-revision-exemptions",
     "docs/rework-relative-revision-exemptions.json", (),
     "entries name a BOARD ISSUE (`subject`), which this leg cannot read offline"),
    ("ruling-board-exemptions", "docs/ruling-board-exemptions.json", (),
     "entries name a GITHUB RULING COMMENT id (`comment`), which this leg cannot read "
     "offline -- the id is the exemption's whole key, so it is deliberately not a tree "
     "path a rename could strand"),
    ("shipped-audit-skips", "docs/shipped-audit-skips.json",
     (("skips", None, DECL_PATH),), ""),
    ("shipped-mechanism-law", "docs/shipped-mechanism-law.json",
     ((None, "law", DECL_PATH), ("required_clauses", "mechanism", DECL_PATH)), ""),
    ("skill-version-exemptions", "docs/skill-version-exemptions.json",
     (("exempt", "path", DECL_PATH), ("exempt", "sha", DECL_COMMIT)), ""),
)

def declaration_families_on_disk(root: Path | None = None) -> list[str]:
    """The live declaration families THIS tree carries.

    A family is the stem of a `docs/*.json` that is neither an `.example` skeleton nor a
    schema. This is the population the sweep must COVER, and it is read from the tree
    rather than from `DECLARATION_SURFACES` on purpose: a map that is its own population
    cannot notice a sixteenth family appearing beside it, which is the drift this
    function exists to make visible.
    """
    root = root or repo_root()
    families = set()
    for path in (root / "docs").glob("*.json"):
        name = path.name
        if name.endswith(".example.json") or name.endswith(".schema.json"):
            continue
        families.add(name[: -len(".json")])
    return sorted(families)

def _declaration_probe_targets(data, container: str | None, field: str | None) -> list[str]:
    """The target strings one probe names, or [] where its coordinate is absent.

    An absent container is NOT an error: a family may legitimately omit a section, and
    the population this leg reads is whatever the file declares.
    """
    node = data if container is None else data.get(container)
    if node is None:
        return []
    if field is None:
        return [key for key in node if isinstance(key, str)] if isinstance(node, dict) else []
    if not isinstance(node, list):
        return []
    return [
        entry[field] for entry in node
        if isinstance(entry, dict) and isinstance(entry.get(field), str)
    ]

def _path_exists(root: Path, target: str) -> bool:
    return (root / target).exists()

def _commit_exists(root: Path, target: str) -> bool | None:
    """True/False, or None where the instrument could not answer at all.

    None is a THIRD state on purpose: a missing `git` is not a missing commit, and
    collapsing the two would let a broken instrument report every exemption as dead debt.
    """
    try:
        proc = subprocess.run(
            ["git", "cat-file", "-e", f"{target}^{{commit}}"],
            cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    return proc.returncode == 0

def declaration_sweep_leg(
    root: Path | None = None,
    path_fn=_path_exists,
    commit_fn=_commit_exists,
) -> dict:
    """The cross-sweep: every declaration family, its targets, and the ones now unmatched.

    REPORT-ONLY and `removes: False`: this leg reads and prints, and the surface's own
    tool keeps its write path. Both checkers are injected so a probe can drive the leg
    over a throwaway tree rather than the live one.
    """
    root = root or repo_root()
    families: list[dict] = []
    for family, rel, probes, note in DECLARATION_SURFACES:
        path = root / rel
        record: dict = {"family": family, "file": rel, "note": note, "probes": len(probes)}
        if not path.is_file():
            record.update(present=False, targets=0, unmatched=[], status="absent")
            families.append(record)
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            record.update(
                present=True, targets=0, unmatched=[], status="NOT RUN",
                reason=f"{rel} exists but cannot be read: {exc}",
            )
            families.append(record)
            continue
        if not isinstance(data, dict):
            record.update(
                present=True, targets=0, unmatched=[], status="NOT RUN",
                reason=f"{rel} is not a JSON object",
            )
            families.append(record)
            continue

        targets: list[tuple[str, str]] = []
        for container, field, kind in probes:
            targets += [
                (target, kind)
                for target in _declaration_probe_targets(data, container, field)
            ]
        unmatched: list[str] = []
        unanswerable = False
        for target, kind in targets:
            if kind == DECL_PATH:
                alive: bool | None = path_fn(root, target)
            else:
                alive = commit_fn(root, target)
            if alive is None:
                unanswerable = True
            elif not alive:
                unmatched.append(f"{kind}:{target}")
        if unanswerable:
            record.update(
                present=True, targets=len(targets), unmatched=unmatched, status="NOT RUN",
                reason="the commit instrument could not answer (git unavailable here)",
            )
        else:
            record.update(
                present=True, targets=len(targets), unmatched=unmatched, status="swept"
            )
        families.append(record)

    undeclared = sorted(set(declaration_families_on_disk(root)) - {f for f, *_ in DECLARATION_SURFACES})
    return {
        "class": "declaration / exemption surfaces",
        "predicate": (
            "for every declared family: each entry whose target is a tree PATH or a "
            "COMMIT, checked against the live tree; an unmatched target is a stale debt"
        ),
        "removes": False,
        "root": str(root),
        "families": families,
        "undeclared": undeclared,
        "live_files": sum(1 for f in families if f["present"]),
        "targets": sum(f["targets"] for f in families),
        "unmatched": sum(len(f["unmatched"]) for f in families),
    }

def render_declaration_sweep(leg: dict) -> str:
    """One line per family, plus the summary that makes the population readable.

    A family that could not be READ is `NOT RUN` with its reason, never a clean zero, and
    a family with no path/commit target says so rather than printing a zero that would
    read as agreement.
    """
    families = leg["families"]
    lines = [
        f"hygiene declaration sweep: {len(families)} family(ies) over "
        f"{leg['live_files']} live file(s) — {leg['targets']} target(s), "
        f"{leg['unmatched']} unmatched (removes: no)"
    ]
    width = max((len(f["family"]) for f in families), default=0)
    for record in families:
        name = record["family"].ljust(width)
        if record["status"] == "absent":
            verdict = "absent (no live file)"
        elif record["status"] == "NOT RUN":
            verdict = f"NOT RUN — {record['reason']}"
        elif record["note"]:
            verdict = f"not swept — {record['note']}"
        else:
            verdict = f"{record['targets']} target(s), {len(record['unmatched'])} unmatched"
            if record["unmatched"]:
                verdict += " — " + ", ".join(record["unmatched"])
        lines.append(f"  {name}  {verdict}")
    if leg["undeclared"]:
        lines.append(
            "  UNDECLARED  " + ", ".join(leg["undeclared"])
            + " — a family this tree carries that DECLARATION_SURFACES does not name, so "
              "nothing sweeps it"
        )
    return "\n".join(lines)

"""## Placement: a file lives where its content belongs, and its name says what it is (G5; q13)

The owner's own bullet names this surface -- "files grouped/regrouped in folders, proper
naming consistent with the contents" -- and `ONTOLOGY.md` states the naming half only as
*patterns* (`## Naming law`). Nothing answered the placement question at all, so a file
could sit in a directory its content does not belong to and no leg would notice: the name
census (`tools/kit_names.py`) answers a different question -- one name meaning two things
across TREES -- and is cited here, not replaced.

This leg is the smallest predicate that bites: a **declared map of directory -> content
class**, checked against the tree. The map is a declaration, not a measurement, which is
the point -- it says what each directory is FOR, so a file whose class is not allowed there
is a placement decision nobody made. Three properties keep it honest:

  * **an unmapped directory states its reason** -- never silently exempt, the same
    discipline the declaration sweep applies to its unswept families;
  * **a mapped directory that is absent is `absent`, not clean** -- a bootstrapped factory
    has no `evidence/`, and a missing directory that read as zero mismatches would be the
    exempt-by-silence surface this factory refuses;
  * **a mapped directory is checked in BOTH trees** where `TEMPLATE/<rel>` exists, because
    `TEMPLATE/` is the shipped mirror of the root by construction.

`evidence/scores/` additionally carries the one tree-path naming pattern `ONTOLOGY.md`
actually states -- `evidence/scores/YYYY-MM-DD.md` -- so the naming half is read from the
law rather than invented here.
"""

PLACEMENT_CLASS: dict[str, str] = {
    ".py": "python",
    ".md": "markdown",
    ".json": "json",
    ".jsonl": "jsonl",
    ".sh": "shell",
    ".tmpl": "template",
    ".mjs": "javascript",
    ".service": "unit",
    ".path": "unit",
    ".txt": "text",
    ".log": "log",
    ".bak": "backup",
}

# (directory, allowed content classes, where the expectation comes from)
PLACEMENT_MAP: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("registry", ("json",),
     "a machine-read register: every file is parsed, never read as prose"),
    ("registry/factories", ("json",),
     "the same register grain, one file per member"),
    ("skills/meta-factory", ("markdown",),
     "a skill is prose law, read by an agent"),
    ("tests", ("python",),
     "a gate is a program; the fixtures it plants live in subdirectories"),
    ("docs", ("markdown", "json"),
     "prose, plus the declaration JSONs the instruments read"),
    ("docs/instruments", ("markdown",), "one law doc per instrument"),
    ("docs/methodology", ("markdown",), "prose"),
    ("docs/projects", ("markdown",), "prose"),
    ("docs/proposals", ("markdown",), "prose"),
    ("docs/stories", ("markdown",), "prose"),
    ("docs/subject", ("markdown",), "prose"),
    ("evidence", ("markdown", "jsonl"),
     "a dated record, plus the append-only ledger"),
    ("evidence/scores", ("markdown",), "one score record per day"),
    ("evidence/deliverables", ("markdown",), "prose"),
    ("evidence/reviews", ("markdown",), "prose"),
    ("TEMPLATE", ("template", "markdown"),
     "the shipped mirror: templates, plus its own README"),
    # `roles/` is a TOP-LEVEL member-factory directory, not a TEMPLATE-only one: BOOTSTRAP.md
    # has every bootstrapped factory split its own procedure into `roles/`, and
    # `tests/test_commit_pathspec_law.py` names `roles/<role>.md` as a path a factory carries.
    # It was declared ONLY as `TEMPLATE/roles`, so the undeclared scan -- which reads the map's
    # TOP-LEVEL segments -- reported `roles` as undeclared in the shipped tree, where REPO IS
    # the TEMPLATE directory. Nothing is lost by moving the declaration up: the mirror branch
    # below generates `TEMPLATE/roles` from this entry whenever that directory exists.
    ("roles", ("markdown",), "one role file per lane; the template ships the four cards"),
    ("tools", ("python", "shell", "javascript", "text"),
     "an executable instrument; python is the house language and shell/js are permitted"),
    ("tools/box", ("unit", "shell", "markdown"),
     "systemd units, the script that drives them, and a README"),
    ("tools/hooks", ("text",),
     "git invokes these by their bare names (`commit-msg`, `pre-commit`), so a suffix is "
     "not expressible"),
)

# Directories that hold files but are deliberately NOT mapped, each with its reason.
PLACEMENT_UNMAPPED: tuple[tuple[str, str], ...] = (
    ("reviews", "a container of per-review subdirectories; no file sits directly under it"),
    ("skills", "a container of per-skill subdirectories; the skill itself is mapped below it"),
)

# (directory, the ONTOLOGY naming pattern, the law sentence it comes from)
PLACEMENT_NAMING: tuple[tuple[str, str, str], ...] = (
    ("evidence/scores", r"^\d{4}-\d{2}-\d{2}(-[a-z0-9-]+)?\.md$",
     "ONTOLOGY.md `## Naming law`: `evidence/scores/YYYY-MM-DD.md`"),
)

# `.audit.lock` is here because the module docstring ABOVE already declares it SELF-IGNORING
# and invisible to every leg -- `BUILD_RESIDUE_NAMES` carries it, the residue leg prints it --
# and `placement_leg` was the one leg that forgot it. Measured 2026-10-02: the nested shipped
# audit creates `TEMPLATE/.audit.lock` and never unlinks it (a `flock` file persists by
# design, `tools/audit.py::acquire_run_lock`), so the ROOT placement gate reported it as
# `unknown:.lock` in a directory that allows only `template`/`markdown` -- a mismatch raised
# by an artifact the tool's own contract says no leg can see. `rm -f` before the audit does
# NOT help: `tests/test_shipped_audit_runs.py` is registered BEFORE this gate and recreates it.
PLACEMENT_SKIP = frozenset(
    {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".audit.lock", ".venv", "venv",
     "node_modules"}
)


def content_class(name: str) -> str:
    """The content class a file's own name declares, or `unknown:<suffix>`.

    An unrecognised suffix is reported as unknown rather than defaulted to a class the
    map might allow: a silent default is how a `.log` in `docs/` would pass a check it
    should fail.
    """
    suffix = Path(name).suffix.lower()
    if not suffix:
        return "text"
    return PLACEMENT_CLASS.get(suffix, f"unknown:{suffix}")


def _gitignored(root: Path, rels: list[str]) -> tuple[set[str], str, str]:
    """(ignored, status, reason) for repo-relative paths, read from git's OWN declaration.

    THE TREE'S OWN DECLARATION, not a list this tool keeps (#282). `.gitignore` is where the
    repo states which artifacts it CREATES but does not track, so the placement predicate
    reads that declaration instead of growing an allowlist. The allowlist form was refused by
    name in this instrument's law -- *exempting one path removes that case and leaves the
    general one* -- and that is exactly how `PLACEMENT_SKIP` accreted: `.audit.lock` was
    appended one path at a time, and each patch left the next case uncaught. Measured
    2026-10-03 on a working checkout, the live leg reported three paths the repo itself
    writes and gitignores (`evidence/.insights.lock`, `evidence/.ledger.lock`,
    `evidence/.ledger-index.sqlite`), so the gate was RED on a clean tree -- which trains
    lanes to ignore a red gate.

    Three outcomes, and the middle one is why this returns a triple rather than a bool:

      * `rc=0` -- git reported at least one ignored path; the set is returned, `APPLIED`.
      * `rc=1` -- git reported NONE ignored. A VALID EMPTY, not an error: the predicate ran
        and found nothing, which is a different statement from the one below.
      * `rc=128` (or git absent) -- NOT A REPOSITORY at this root, so the predicate could not
        be applied. Returned as `NOT APPLIED` with its reason and NEVER as "nothing is
        ignored", because a clean zero from a dead instrument is the surface this module
        refuses. A bootstrapped factory and the shipped `TEMPLATE/` tree both take this path,
        and the report says so rather than reading clean by silence.

    `-z` on BOTH sides -- NUL-terminated input and output -- so a path carrying a space or a
    newline cannot be mis-split. ONE batched call for the whole tree: a subprocess per file
    would make the leg quadratic on a tree this size.
    """
    if not rels:
        return set(), "APPLIED", ""
    payload = b"".join(rel.encode("utf-8") + b"\0" for rel in rels)
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-z", "--stdin"],
            cwd=str(root),
            input=payload,
            capture_output=True,
        )
    except OSError as exc:
        return set(), "NOT APPLIED", f"git could not be run ({exc.__class__.__name__})"
    if proc.returncode == 0:
        return {chunk.decode("utf-8") for chunk in proc.stdout.split(b"\0") if chunk}, "APPLIED", ""
    if proc.returncode == 1:
        return set(), "APPLIED", ""
    detail = [line for line in proc.stderr.decode("utf-8", "replace").splitlines() if line.strip()]
    reason = detail[0] if detail else f"git check-ignore exited {proc.returncode}"
    return set(), "NOT APPLIED", reason

def placement_leg(root: Path | None = None) -> dict:
    """Check every mapped directory against its declared content classes.

    Report-only (`removes: False`): a mismatch is a decision nobody made, so it is
    PRINTED for a human to make, never moved or deleted by this leg.
    """
    root = Path(root) if root is not None else repo_root()
    leg: dict = {
        "class": "placement",
        "predicate": "a file's content class is allowed in the directory that holds it",
        "removes": False,
        "root": str(root),
        "directories": [],
        "unmapped": [],
        "undeclared": [],
        "mismatches": [],
        "naming": [],
        "ignored": [],
        "ignore_status": "APPLIED",
        "ignore_reason": "",
        "files": 0,
    }
    if not root.is_dir():
        leg["status"] = "NOT RUN"
        leg["reason"] = f"{root} is not a directory"
        return leg

    # A mapped directory is judged in BOTH trees when the shipped mirror carries it, so a
    # divergence between root and TEMPLATE is a placement mismatch like any other.
    targets: list[tuple[str, str, tuple[str, ...], str]] = []
    for rel, classes, basis in PLACEMENT_MAP:
        targets.append((rel, rel, classes, basis))
        if (root / "TEMPLATE" / rel).is_dir():
            targets.append((f"TEMPLATE/{rel}", f"TEMPLATE/{rel}", classes, basis))

    # The ignored set is computed ONCE for the whole tree, before the per-directory walk,
    # because `git check-ignore` is a subprocess and one call per file would be quadratic.
    candidates: list[str] = []
    for _shown, _rel, _classes, _basis in targets:
        _directory = root / _rel
        if not _directory.is_dir():
            continue
        for _entry in sorted(_directory.iterdir()):
            if _entry.is_file():
                candidates.append(str(_entry.relative_to(root)))
    ignored, ignore_status, ignore_reason = _gitignored(root, candidates)
    leg["ignore_status"] = ignore_status
    leg["ignore_reason"] = ignore_reason

    for shown, rel, classes, basis in targets:
        directory = root / rel
        if not directory.is_dir():
            leg["directories"].append(
                {"dir": shown, "status": "absent", "files": 0, "allowed": list(classes)}
            )
            continue
        found = 0
        bad = 0
        for entry in sorted(directory.iterdir()):
            if not entry.is_file() or entry.name in PLACEMENT_SKIP:
                continue
            relpath = str(entry.relative_to(root))
            if relpath in ignored:
                # OUT of the placement population, PRINTED BY NAME (#282). Silently dropping
                # it would be the exempt-by-silence surface this factory files against, and
                # the reader of the report is the only one who can say whether the tree's
                # own .gitignore is the right place for that path.
                leg["ignored"].append({"path": relpath, "dir": shown})
                continue
            found += 1
            leg["files"] += 1
            cls = content_class(entry.name)
            if cls not in classes:
                bad += 1
                leg["mismatches"].append(
                    {
                        "path": str(entry.relative_to(root)),
                        "dir": shown,
                        "class": cls,
                        "allowed": list(classes),
                        "basis": basis,
                    }
                )
        leg["directories"].append(
            {"dir": shown, "status": "ok" if not bad else "MISMATCH",
             "files": found, "allowed": list(classes)}
        )

    for rel, pattern, basis in PLACEMENT_NAMING:
        directory = root / rel
        if not directory.is_dir():
            continue
        compiled = re.compile(pattern)
        for entry in sorted(directory.iterdir()):
            if not entry.is_file() or entry.name in PLACEMENT_SKIP:
                continue
            if not compiled.match(entry.name):
                leg["naming"].append(
                    {"path": str(entry.relative_to(root)), "dir": rel, "pattern": pattern,
                     "basis": basis}
                )

    for rel, reason in PLACEMENT_UNMAPPED:
        if (root / rel).is_dir():
            leg["unmapped"].append({"dir": rel, "reason": reason})

    # A directory that holds files directly and is named NOWHERE is a placement decision
    # nobody made -- the same bite the declaration sweep applies to an undeclared family.
    declared = {rel.split("/")[0] for rel, _, _ in PLACEMENT_MAP}
    declared |= {rel for rel, _ in PLACEMENT_UNMAPPED}
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in PLACEMENT_SKIP or entry.name.startswith("."):
            continue
        if entry.name in declared:
            continue
        if any(child.is_file() for child in entry.iterdir()):
            leg["undeclared"].append(entry.name)

    leg["status"] = "ASSERTED"
    return leg


def render_placement(leg: dict) -> str:
    """One summary line, then one line per declared directory (G5)."""
    if leg.get("status") == "NOT RUN":
        return f"hygiene placement: NOT RUN — {leg.get('reason', 'no reason recorded')}"
    head = (
        f"hygiene placement: {leg['files']} file(s) over "
        f"{sum(1 for d in leg['directories'] if d['status'] != 'absent')} declared directory(ies)"
        f" — {len(leg['mismatches'])} mismatch(es), {len(leg['naming'])} naming mismatch(es), "
        f"{len(leg.get('ignored', []))} git-ignored (excluded) (removes: no)"
    )
    lines = [head]
    if leg.get("ignore_status", "APPLIED") != "APPLIED":
        # The predicate could not be applied -- NOT A CLEAN ZERO. Printed as its own line so
        # a reader never mistakes "git could not answer" for "nothing is ignored" (#282).
        lines.append(
            f"  gitignore predicate NOT APPLIED — {leg.get('ignore_reason', 'no reason recorded')}"
        )
    for record in leg.get("ignored", []):
        lines.append(
            f"  IGNORED {record['path']} — the tree's own .gitignore declares this path, so it "
            f"is OUT of the placement population (the repo creates it; it does not track it)"
        )
    for record in leg["directories"]:
        if record["status"] == "absent":
            lines.append(f"  {record['dir']:24} absent (no such directory)")
        else:
            lines.append(
                f"  {record['dir']:24} {record['files']:3} file(s), "
                f"{'|'.join(record['allowed'])}"
            )
    for record in leg["unmapped"]:
        lines.append(f"  {record['dir']:24} unmapped — {record['reason']}")
    for record in leg["undeclared"]:
        lines.append(
            f"  UNDECLARED {record} — a directory this tree carries that neither "
            f"PLACEMENT_MAP nor PLACEMENT_UNMAPPED names, so nothing checks its contents"
        )
    for record in leg["mismatches"]:
        lines.append(
            f"  MISMATCH {record['path']} — {record['class']}, and `{record['dir']}` declares "
            f"{'|'.join(record['allowed'])} ({record['basis']})"
        )
    for record in leg["naming"]:
        lines.append(
            f"  NAME {record['path']} — does not match `{record['pattern']}` "
            f"({record['basis']})"
        )
    return "\n".join(lines)


"""Stale directories OUTSIDE the namespace, PRINTED and never reclaimed (G6; q13).

The reaper above globs `/tmp/<namespace>-*`, and that glob is the whole of its vision: a
directory this factory created at a path that does not match it is invisible to every leg
of this tool. `git worktree add` is the declared creation convention that produces exactly
that class -- the path is the caller's choice, so `/tmp/af-223` and `/tmp/af-225/wt` are
both worktrees this factory made and NEITHER matches the pattern. Measured 2026-10-02: 75
registered trees, 75 of them outside the namespace, so a tree left behind by a killed lane
survives indefinitely and no leg reports it.

What this leg PRINTS is git's own census, plus three facts read from it:

  * **prunable** -- git itself says the tree's gitdir points at a non-existent location.
    This is the definitive stale class and the only one this leg ENUMERATES, because it is
    a declaration by the tool that owns the data rather than an inference by this one;
  * **outside the namespace** -- the structural fact that the reaper cannot see the tree at
    all, reported as a count because it holds of every tree here and so cannot discriminate;
  * **landed** and **age** -- reported as counts and never as a verdict. A tree's HEAD being
    an ancestor of the primary branch means its WORK LANDED, NOT that the tree is abandoned:
    a live lane sits on a landed commit between edits, and this very worktree did while the
    leg was being written. Age is the discriminator this factory already uses for in-flight
    versus stranded (#38), so both are printed BESIDE each other and the judgement is left
    to a reader.

`removes: no`, and the leg never reclaims: `git worktree prune` is a write, the tree may
hold a peer lane's uncommitted work, and the shape established for this class by
leshchenko1979/agent-factories#220 is a report that a human acts on.
"""


def _primary_reachable(root: Path) -> tuple[str | None, set[str] | None, str | None]:
    """(revision, every commit reachable from it, error) for the landed test.

    ONE `git rev-list` call rather than one `merge-base --is-ancestor` per tree: 75
    subprocesses would cost more than this whole leg, and the reachable set answers the
    same question for every tree at once. `origin/main` is preferred and the local `main`
    is the fallback, because a factory with no remote still has a primary branch; when
    NEITHER resolves the landed count is `NOT RUN` with its reason, never a zero.
    """
    for rev in ("origin/main", "main"):
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            listed = subprocess.run(
                ["git", "rev-list", rev],
                cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            if listed.returncode != 0:
                return rev, None, (
                    f"`git rev-list {rev}` exited {listed.returncode}: {listed.stderr.strip()}"
                )
            return rev, set(listed.stdout.split()), None
    return None, None, "neither `origin/main` nor `main` resolves here"

def stale_dirs_leg(
    root: Path | None = None,
    namespace: str | None = None,
    records_fn=None,
    reachable_fn=None,
) -> dict:
    """The population of directories this factory created outside its own scratch glob.

    Report-only (`removes: False`): the tree may hold a peer lane's uncommitted work, so
    the leg PRINTS and a human decides.
    """
    root = Path(root) if root is not None else repo_root()
    namespace = namespace or NAMESPACE
    pattern = f"/tmp/{namespace}-*"
    records_fn = records_fn or worktree_records
    reachable_fn = reachable_fn or _primary_reachable

    leg: dict = {
        "class": "stale-directories",
        "predicate": "a directory this factory created is visible to the reaper that maintains it",
        "removes": False,
        "root": str(root),
        "namespace": namespace,
        "pattern": pattern,
        "grace_hours": WORKTREE_STALE_HOURS,
        "total": 0,
        "outside": [],
        "prunable": [],
        "landed": [],
        "aged": [],
        "trees": [],
        "reach_rev": None,
        "reach_error": None,
    }

    records, error = records_fn(root)
    if error:
        leg["status"] = "NOT RUN"
        leg["reason"] = error
        return leg

    rev, reachable, reach_error = reachable_fn(root)
    leg["reach_rev"] = rev
    leg["reach_error"] = reach_error

    now = time.time()
    for record in records:
        path = record["path"]
        try:
            age = (now - os.path.getmtime(path)) / 3600.0
        except OSError:
            age = None
        inside = fnmatch.fnmatch(path, pattern)
        landed = None
        if reachable is not None and record.get("head"):
            landed = record["head"] in reachable
        leg["trees"].append(
            {
                "path": path,
                "head": record.get("head"),
                "prunable": record.get("prunable"),
                "inside_namespace": inside,
                "age_hours": age,
                "landed": landed,
            }
        )
        if not inside:
            leg["outside"].append(path)
        if record.get("prunable"):
            leg["prunable"].append(path)
        if landed:
            leg["landed"].append(path)
        if age is not None and age > WORKTREE_STALE_HOURS:
            leg["aged"].append(path)

    leg["total"] = len(records)
    leg["status"] = "ASSERTED"
    return leg

def render_stale_dirs(leg: dict) -> str:
    """One summary line, then one line per PRUNABLE tree (G6)."""
    if leg.get("status") == "NOT RUN":
        return f"hygiene stale directories: NOT RUN — {leg.get('reason', 'no reason recorded')}"
    bits = [
        f"{leg['total']} tree(s)",
        f"{len(leg['outside'])} outside the namespace `{leg['pattern']}`",
        f"{len(leg['prunable'])} prunable",
    ]
    if leg.get("reach_error"):
        bits.append(f"landed NOT RUN ({leg['reach_error']})")
    else:
        bits.append(f"{len(leg['landed'])} landed")
    bits.append(f"{len(leg['aged'])} older than {leg['grace_hours']:.0f}h")
    lines = ["hygiene stale directories: " + ", ".join(bits) + " (removes: no)"]
    for path in leg["prunable"]:
        why = next(
            (tree["prunable"] for tree in leg["trees"] if tree["path"] == path), "prunable"
        )
        lines.append(f"  PRUNABLE {path} — git reports: {why}")
    return "\n".join(lines)


# --- Evidence supersession: PROSE-ONLY supersessions are REPORTED (G7; q13) -----------
"""An evidence artifact superseded in PROSE but not MECHANICALLY, reported (G7; q13).

`evidence/` and `reviews/` are append-only history: an artifact is never deleted when a
later run replaces it, so the tree accumulates snapshots and the ONLY thing that says which
one governs is a hand-written notice -- or, more often, the reader noticing that a later
dated sibling exists. Measured 2026-10-02: 25 dated artifacts over 15 families, 6 families
with more than one member, and **zero** `superseded_by` markers anywhere in the tree. So
every supersession in this repository is prose-only, which is the gap G7 names.

Two signals say an artifact is superseded, and the leg reads BOTH because they fail
differently:

  * **the naming convention** -- a dated artifact `<stem>-YYYY-MM-DD[-<suffix>].md` whose
    date is STRICTLY older than its family's newest date. A tie at the newest date is a
    set of CURRENT siblings, not a supersession: the suffix distinguishes a variant (a
    refused census is not an older census);
  * **a prose notice** -- the artifact's own text names a successor path. This catches the
    singleton case the convention cannot see, where a file supersedes something outside
    its own family.

A mechanical marker is the declared field `superseded_by:` naming an existing path. An
artifact that is superseded by EITHER signal and carries NO marker is the population this
leg reports. It is a DEBT CENSUS and not a fault list: the report is expected to be
non-empty on this tree, and the number falls only as markers are added.

`removes: no`, and the leg never writes a marker for you: what a successor IS is a
judgement by the lane that produced the artifact, and a marker this tool invented would be
a fabricated supersession -- worse than an unmarked one, because it reads as a decision
somebody made. The shape is the one established for this class by
leshchenko1979/agent-factories#220.
"""

SUPERSEDED_FIELD = "superseded_by"

# `<stem>-YYYY-MM-DD[-<suffix>].md`: the DECLARED naming convention. The suffix is part of
# the convention rather than an exception to it -- `-refused` and `-self-audit` are real
# members of this tree, and a variant shares its date with its sibling.
DATED_ARTIFACT = re.compile(
    r"^(?P<stem>.+?)-(?P<date>\d{4}-\d{2}-\d{2})(?:-(?P<suffix>[A-Za-z0-9._-]+))?\.md$"
)

# A prose notice that names a successor. Deliberately narrow: it requires a PATH-like token
# ending in `.md`, because "superseded" as a bare word appears in this tree describing
# ledger rows, measurements and channel surfaces, none of which is an artifact.
SUPERSESSION_NOTICE = re.compile(
    r"(?i)supersed(?:e[sd]?|ing)\s+by\s+`?(?P<path>[\w./-]+\.md)`?"
)

EVIDENCE_DIR = "evidence"

def _dated_artifacts(root: Path) -> list[dict]:
    """Every artifact under `evidence/` whose name carries the convention's date."""
    base = root / EVIDENCE_DIR
    records: list[dict] = []
    for path in sorted(base.rglob("*.md")):
        match = DATED_ARTIFACT.match(path.name)
        if not match:
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "family": (path.parent / match.group("stem")).relative_to(root).as_posix(),
                "date": match.group("date"),
            }
        )
    return records

def _reads_marker(root: Path, rel: str) -> str | None:
    """The declared `superseded_by` value, or None when the artifact carries no marker.

    A marker whose target does not exist is returned as-is and reported SEPARATELY: it is
    a stale marker rather than a clean one, and folding it into "marked" would let a
    fabricated supersession read as a satisfied one.
    """
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines()[:40]:
        stripped = line.strip().lstrip("*-").strip()
        if stripped.lower().startswith(SUPERSEDED_FIELD):
            _, _, value = stripped.partition(":")
            value = value.strip().strip("`").strip()
            if value:
                return value
    return None

def _names_successor(root: Path, rel: str) -> str | None:
    """The successor path a prose notice names, when it names one that exists."""
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for match in SUPERSESSION_NOTICE.finditer(text):
        candidate = match.group("path")
        for form in (root / candidate, root / EVIDENCE_DIR / candidate):
            if form.is_file():
                return form.relative_to(root).as_posix()
    return None

def evidence_supersession_leg(root: Path | None = None) -> dict:
    """The artifacts superseded by convention or prose that carry no marker (G7).

    Report-only (`removes: False`): a supersession is a judgement by the lane that produced
    the artifact, so the leg PRINTS the debt and a human settles it.
    """
    root = Path(root) if root is not None else repo_root()
    leg: dict = {
        "class": "evidence-supersession",
        "predicate": "an artifact superseded in prose or by the naming convention carries a mechanical marker",
        "removes": False,
        "root": str(root),
        "dir": EVIDENCE_DIR,
        "field": SUPERSEDED_FIELD,
        "artifacts": [],
        "families": {},
        "newest": {},
        "by_convention": [],
        "by_prose": [],
        "marked": [],
        "stale_marker": [],
        "prose_only": [],
    }

    base = root / EVIDENCE_DIR
    if not base.is_dir():
        leg["status"] = "absent"
        leg["reason"] = f"no `{EVIDENCE_DIR}/` in this tree"
        return leg
    if not os.access(base, os.R_OK):
        leg["status"] = "NOT RUN"
        leg["reason"] = f"`{EVIDENCE_DIR}/` exists but cannot be read"
        return leg

    records = _dated_artifacts(root)
    leg["artifacts"] = records
    families: dict[str, list[str]] = {}
    for record in records:
        families.setdefault(record["family"], []).append(record["date"])
    leg["families"] = {family: sorted(dates) for family, dates in families.items()}
    leg["newest"] = {family: max(dates) for family, dates in families.items()}

    for record in records:
        rel = record["path"]
        newest = leg["newest"][record["family"]]
        by_convention = record["date"] < newest
        successor = _names_successor(root, rel)
        marker = _reads_marker(root, rel)
        entry = {
            "path": rel,
            "family": record["family"],
            "date": record["date"],
            "newest": newest,
            "by_convention": by_convention,
            "successor": successor,
            "marker": marker,
        }
        if by_convention:
            leg["by_convention"].append(rel)
        if successor:
            leg["by_prose"].append(rel)
        if marker:
            if (root / marker).is_file():
                leg["marked"].append(rel)
                continue
            leg["stale_marker"].append(entry)
        if by_convention or successor:
            leg["prose_only"].append(entry)

    leg["status"] = "ASSERTED"
    return leg

def render_evidence_supersession(leg: dict) -> str:
    """One summary line, then one line per unmarked supersession (G7)."""
    if leg.get("status") == "NOT RUN":
        return f"hygiene evidence supersession: NOT RUN — {leg.get('reason', 'no reason recorded')}"
    if leg.get("status") == "absent":
        return f"hygiene evidence supersession: absent — {leg.get('reason', 'no evidence tree')}"
    head = (
        f"hygiene evidence supersession: {len(leg['artifacts'])} dated artifact(s) over "
        f"{len(leg['families'])} family(ies) — {len(leg['by_convention'])} superseded by the "
        f"naming convention, {len(leg['prose_only'])} prose-only (unmarked), "
        f"{len(leg['marked'])} marked (removes: no)"
    )
    lines = [head]
    for entry in leg["prose_only"]:
        why = (
            f"superseded by {entry['family']}-{entry['newest']}.md"
            if entry["by_convention"]
            else f"names {entry['successor']} as its successor"
        )
        lines.append(
            f"  PROSE-ONLY {entry['path']} — {why}, and carries no `{leg['field']}` marker"
        )
    for entry in leg["stale_marker"]:
        lines.append(
            f"  STALE MARKER {entry['path']} — declares `{leg['field']}: {entry['marker']}`, "
            f"which does not exist in this tree"
        )
    return "\n".join(lines)

def _split_status_line(line: str) -> tuple[str, str]:
    """Return (status code, path) from one `git status --porcelain` line.

    A rename is reported as `R  old -> new`; the path that exists on disk — the
    one whose age is meaningful — is the new one.
    """
    status_code = line[:2]
    path = line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1].strip()
    if len(path) > 1 and path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    return status_code, path

def _deleted_age_minutes(full: str, now: float) -> int | None:
    """Age, in minutes, of a path that is GONE from the working tree (#447).

    A deleted path has no mtime, so the age is read from its nearest EXISTING
    ancestor directory: deleting an entry stamps the directory that held it, so
    `git rm` across N files stamps each file's directory as it goes. The estimate
    can only come out too YOUNG (a sibling entry changed since), which errs toward
    ADVISORY — the safe direction in a shared tree, where a false RED on a peer's
    in-flight deletion is the very defect this discriminates. `None` when no
    ancestor is readable; the caller treats that as the pre-#447 behaviour.
    """
    probe = os.path.dirname(full)
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent
    try:
        return int((now - os.path.getmtime(probe)) / 60)
    except OSError:
        return None

def inspect_git_working_tree(
    repo_dir: str | None = None, now: float | None = None
) -> tuple[list[str], list[str], list[str]]:
    """Classify the working tree into (violations, advisories, explanations).

    A dirty path younger than the grace window is an advisory: it may be a lane's
    live work. The same path older than the window is a violation: nothing is
    working on it any more. Untracked litter is always a violation — age does not
    make a `.bak` legitimate.
    """
    now = time.time() if now is None else now
    try:
        repo_dir = repo_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        # THE PATHS ARE REPO-ROOT-RELATIVE, WHICHEVER DIRECTORY THE TOOL SITS IN (#199).
        # `git status --porcelain` reports paths relative to the REPOSITORY ROOT, while
        # `repo_dir` above is the TOOL's own directory. Those coincide only when the tool is
        # at the root: run from a subdirectory -- the shipped tree's `TEMPLATE/`, say -- every
        # modified file was joined against the wrong base, `getmtime` raised OSError, and the
        # file was reported as "missing from the working tree". A false POSITIVE for every
        # dirty path, which is worse than a miss: it names files that are present.
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        root = toplevel.stdout.strip() if toplevel.returncode == 0 else repo_dir
    except Exception as e:
        return ([f"git status failed: {e}"], [], [])

    violations: list[str] = []
    advisories: list[str] = []
    explanations: list[str] = []

    for line in res.stdout.splitlines():
        if not line:
            continue
        status_code, path = _split_status_line(line)
        full = os.path.join(root, path)
        try:
            age_min = int((now - os.path.getmtime(full)) / 60)
        except OSError:
            # The path is GONE from the working tree: git reports a deleted tracked
            # file as ` D` (unstaged) or `D ` (staged). Its own mtime is unavailable,
            # so the age is read from the nearest existing ancestor directory and the
            # SAME grace discriminator applies as for every other dirty path (#447).
            # The old branch called any deletion a violation at ANY age, conflating
            # "the content is not being edited" with "the change is not being made":
            # a lane that has run `git rm` across N files and is verifying before
            # committing is exactly in flight, and the audit went RED on it — the #38
            # race, re-introduced for this one class of change.
            age_min = _deleted_age_minutes(full, now)
            if age_min is None:
                violations.append(
                    f"[{status_code}] {path} (deleted from the working tree, age unknown)"
                )
            elif age_min >= GRACE_MINUTES:
                violations.append(
                    f"[{status_code}] {path} (deleted from the working tree, aged {age_min}m)"
                )
            else:
                advisories.append(
                    f"[{status_code}] {path} (deleted {age_min}m ago — possibly a lane's work in flight)"
                )
            continue

        if status_code == "??":
            if path.endswith(LITTER_SUFFIXES):
                violations.append(f"untracked git clutter: {path}")
            elif age_min >= GRACE_MINUTES:
                violations.append(f"untracked file: {path} (untouched for {age_min}m)")
            else:
                advisories.append(f"untracked file: {path} (age {age_min}m — possibly a lane's work in flight)")
        else:
            if age_min >= GRACE_MINUTES:
                violations.append(f"modified tracked file: [{status_code}] {path} (untouched for {age_min}m)")
            else:
                advisories.append(
                    f"modified tracked file: [{status_code}] {path} (age {age_min}m — possibly a lane's work in flight)"
                )

    for path in REQUIRED_COMMITTED:
        full = os.path.join(root, path)
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", path],
            cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()
        if status:
            violations.append(f"required committed, but dirty: {path} ({status})")
        elif not os.path.exists(full):
            violations.append(f"required committed, but absent: {path}")
        else:
            explanations.append(f"required committed: {path} clean")

    return (violations, advisories, explanations)

# Set by main() from --grace-minutes / --require-committed, so the classifier stays
# callable as a pure function from tests with an explicit window.
GRACE_MINUTES = DEFAULT_GRACE_MINUTES
REQUIRED_COMMITTED: list[str] = []

def main() -> int:
    global GRACE_MINUTES, REQUIRED_COMMITTED

    parser = argparse.ArgumentParser(description="Workspace hygiene and GC audit tool.")
    parser.add_argument("--audit", action="store_true", help="Audit without removing")
    parser.add_argument("--clean", action="store_true", help="Reap stale scratch items")
    parser.add_argument(
        "--scratch-glob",
        action="append",
        metavar="GLOB",
        help="Additional scratch namespace this factory owns (repeatable). "
        "Never pass a prefix another tool already writes to.",
    )
    parser.add_argument(
        "--namespace",
        default=NAMESPACE,
        metavar="NAME",
        help=f"The scratch namespace this factory OWNS (default: the repository "
        f"directory name, {NAMESPACE!r}). Pass it explicitly when running from a "
        f"worktree: the default follows the directory the TOOL sits in, so a "
        f"worktree measures a namespace belonging to nobody.",
    )
    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=DEFAULT_GRACE_MINUTES,
        metavar="N",
        help=f"How long a dirty path may be explained as a lane's work in flight "
        f"(default {DEFAULT_GRACE_MINUTES}). A path older than this is stranded.",
    )
    parser.add_argument(
        "--require-committed",
        action="append",
        default=[],
        metavar="PATH",
        help="A path this run owns and must find committed. Fails with NO grace, "
        "regardless of age (repeatable). This is the measurement run's closing "
        "invariant — the run-scoped form of the #28 catch.",
    )
    args = parser.parse_args()

    if not args.audit and not args.clean:
        args.audit = True

    GRACE_MINUTES = args.grace_minutes
    REQUIRED_COMMITTED = list(args.require_committed)

    dry_run = args.audit and not args.clean
    # The namespace is PRINTED on every run, with its provenance: a verdict over
    # a namespace the reader cannot see is unreproducible, and a worktree's run
    # site is exactly how the wrong one got measured in silence (#174).
    origin = (
        "default, the repository directory name"
        if args.namespace == NAMESPACE
        else "declared"
    )
    print(f"hygiene namespace: {args.namespace} ({origin})")
    protected_entries, scratch_entries, decl_problems = load_declaration()
    if decl_problems:
        for problem in decl_problems:
            print(f"hygiene declaration problem: {problem}", file=sys.stderr)
        return 1
    protected = {e["path"] for e in protected_entries}
    # The declaration's population is PRINTED on every run, with the counts a
    # reader needs to tell "nothing is declared live" from "the file was never
    # found": a reaper that silently protects nothing is the defect itself.
    print(
        f"hygiene declaration: {len(protected)} path(s) declared live, "
        f"{len(scratch_entries)} declared scratch ({PROTECTED_REL})"
    )
    # The build-residue population, PRINTED on every run and never reaped (G3; q15). It is
    # the class no other leg can see -- self-ignoring caches -- so its whole remedy is that
    # a reader meets its size here rather than inferring "none" from silence.
    print(render_build_residue(build_residue_leg()))
    # The declaration cross-sweep, PRINTED on every run (G2). Each surface's own tool reads
    # its own file for readability; nothing asked whether the thing an entry points at still
    # exists, so a debt left by a rename read as a live exemption on every one of them.
    print(render_declaration_sweep(declaration_sweep_leg()))
    # The placement map, PRINTED on every run (G5). Nothing answered "is this file in the
    # folder its content belongs to", so a file could sit in a directory its content does
    # not belong to and every leg above would still read clean.
    print(render_placement(placement_leg()))
    # The stale-directory population OUTSIDE the scratch namespace, PRINTED on every run
    # (G6). The reaper's glob is the whole of its vision, so a tree this factory created at
    # a path that does not match it -- every `git worktree add` -- is invisible to it.
    print(render_stale_dirs(stale_dirs_leg(namespace=args.namespace)))
    # The evidence artifacts superseded in PROSE that carry no mechanical marker (G7).
    # A DEBT CENSUS and not a fault list: `evidence/` is append-only history, so an
    # unmarked supersession is the expected state and the number falls only as markers
    # are added by the lanes that produced the artifacts.
    print(render_evidence_supersession(evidence_supersession_leg()))
    patterns = scratch_patterns_for(args.namespace) + list(args.scratch_glob or [])
    count, items = reap_stale_scratch(
        dry_run=dry_run, patterns=patterns, protected=protected
    )
    violations, advisories, explanations = inspect_git_working_tree()

    if dry_run:
        # Audit mode: stale scratch, litter, stranded dirty paths and any path this
        # run declared as its own all fail the gate. Advisories are printed so the
        # signal is not lost — an audit that hides what it saw is how #28 happened —
        # but they do not fail, because a peer lane mid-task is not a defect.
        total_violations = len(items) + len(violations)
        for item in items:
            violations.insert(0, f"stale scratch file: {os.path.basename(item)}")
        if advisories:
            print(f"hygiene audit: {len(advisories)} advisory item(s) — not failures:", file=sys.stderr)
            for a in advisories:
                print(f"  ~ {a}", file=sys.stderr)
        if total_violations > 0:
            # The marker comes FIRST and is a DECLARATION of the count (#205): the audit's
            # headline reads it rather than guessing from the sentence below, whose noun
            # (`issue(s)`) its noun class did not carry -- so the count was dropped and the
            # recorded cause fell through to the LAST line, an informational declaration
            # line this tool prints on EVERY run, clean or not. A reader sent there was
            # sent to a fix that could not clear the gate.
            print(f"oc-cause-count: {total_violations}", file=sys.stderr)
            # The header states the window it judged on: a verdict that does not
            # carry its own predicate cannot be reproduced by its reader.
            print(
                f"hygiene audit found {total_violations} issue(s) "
                f"(stranded = untouched for {GRACE_MINUTES}m or more):",
                file=sys.stderr,
            )
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            return 1
        print(
            f"hygiene audit clean: 0 stale scratch items in "
            f"{', '.join(patterns)}, 0 stranded dirty paths (grace "
            f"{GRACE_MINUTES}m), {len(advisories)} advisory item(s), "
            f"working tree clean of violations"
        )
        return 0

    print(f"hygiene cleanup complete: {count} scratch item(s) reaped")
    if advisories:
        print(f"warning: {len(advisories)} dirty path(s) within the {GRACE_MINUTES}m grace window:", file=sys.stderr)
        for a in advisories:
            print(f"  ~ {a}", file=sys.stderr)
    if violations:
        print(f"warning: {len(violations)} stranded item(s) in the working tree:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
