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
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# A gate may only glob a namespace this factory OWNS.
#
# `/tmp` is shared. Another factory's tooling writes its own prefix there — the
# OpenCrabs dev tools leave `oc-snap-*` behind by the thousand. Globbing a
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

def registered_worktrees(root: Path | None = None) -> tuple[list[str], str | None]:
    """(paths, error) for every tree `git worktree list` reports.

    The census is git's OWN, never a `/tmp` glob: a scratch prefix would miss the MAIN tree
    and every tree named outside the namespace, and would sweep a directory belonging to
    nobody -- the #174/#220 class this factory files against. An unreadable census is an
    ERROR and never an empty one: "no trees" and "the instrument failed" must not render as
    the same verdict.
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
    paths = [
        line[len("worktree "):].strip()
        for line in proc.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    if not paths:
        return [], "`git worktree list` reported no tree, which a repository cannot do"
    return paths, None

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
            # Deleted from the working tree: nothing can be in flight about a file
            # that is gone, and a deleted tracked file left uncommitted is stranded.
            violations.append(f"[{status_code}] {path} (missing from the working tree)")
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
