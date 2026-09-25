#!/usr/bin/env python3
"""Generate or check `registry/kit.json` — the reference manifest of the shipped kit.

WHAT THIS IS FOR. A member factory's drift was previously unmeasurable: the only
thing that could say whether a factory's copy of `tools/ledger.py` matched the
template's was a person reading both trees. Measured 2026-09-25 over the ten
bootstrap-named files across five member factories: **50 cells, 1 identical
(2%), 20 drifted, 29 absent** -- and three of the absent ones were the write-path
guards (`tools/gate_budget.py` and both `tools/hooks/` refusal points), which had
therefore never bound a single member. Without a manifest a drift leg can only
say that a factory DIFFERS; it cannot say what it is missing or what the
reference is. This file is that reference.

THE SET IS THE TREE, NOT A LIST. The manifest covers every file under
`TEMPLATE/` except transient build artifacts, because a hand-maintained list of
shipped files is a second copy of the tree that goes stale silently -- the class
this factory has ruled against repeatedly. A file added to `TEMPLATE/` appears in
the manifest on the next regeneration, and `--check` FAILS until it does, so a
shipped file cannot escape the manifest by being forgotten.

THE VERSION IS DERIVED FROM THE CONTENT, and that is deliberate. A hand-typed kit
version is a claim about the tree that nothing can test, so it drifts the moment
someone edits a shipped file and forgets the number. This one is a digest over
the manifest's own (path, sha256, CLASS) triples: it cannot be stale, and two trees with
the same version are the same kit by construction rather than by assertion. The class is
inside the digest because it is part of what the reference SAYS about a path -- moving
`shared` to `factory` switches a cell from a finding to no comparison at all, and a
version that did not move would let that happen invisibly.

EVERY SHIPPED PATH CARRIES A CLASS, and a path without one is a failure, not a default.
This manifest was 106 flat `path -> sha256` entries with no per-file predicate, so a
factory's own gate list scored as drift against the template's and a missing dependency
scored the same as a missing instrument: over the ten bootstrap-named files across five
factories the figure was 1 same / 20 DIFF / 29 ABSENT, and four of the five DIFFs were
deliberate, reasoned forks. `shared` / `closure` / `factory` say what a MISSING FILE
MEANS -- behind, broken parent, or not applicable -- and the table is DECLARED per path
below rather than derived from the import graph, because a static walk is blind to the
dependencies loaded through `importlib` from a string constant
(`tools/hooks/commit-msg:121`, `tools/hooks/pre-commit:175`) and would report a hook
complete while it cannot run.

Run:  python3 tools/kit_manifest.py            # regenerate registry/kit.json
      python3 tools/kit_manifest.py --check    # exit 1 naming every drifted file
      python3 tools/kit_manifest.py --identity tools/ledger.py   # which copy is this?
Exit: 0 in agreement (or after a successful regenerate); 1 drift, each file named.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KIT_ROOT = REPO / "TEMPLATE"
MANIFEST = REPO / "registry" / "kit.json"

# Transient artifacts, never part of the kit: a lock file, byte-code caches and
# pytest's own cache directory. Named as DIRECTORIES where they are directories,
# because a name match on a file would miss the tree beneath it.
EXCLUDED_DIRS = frozenset({"__pycache__", ".pytest_cache"})
EXCLUDED_FILES = frozenset({".audit.lock"})
EXCLUDED_SUFFIXES = (".pyc", ".pyo")

# The pin vehicle: the copy of this manifest that ships inside the kit so a factory can
# VENDOR it at the version it ported (plan 2646d31a task 6). It is excluded from the set it
# renders, and the reason is arithmetic rather than taste: the vehicle's content IS a
# rendering of the manifest, so if the manifest carried the vehicle's digest then
# kit_version = H(files including digest(vehicle)) and vehicle = render(kit_version, files)
# would have no fixpoint. `registry/kit.json` is outside the set for the same kind of reason
# (generated factory data, not shipped kit), so this is a principled exception and not the
# "forgot to list it" case the completeness rule exists to refuse.
PIN_VEHICLE_REL = "TEMPLATE/registry/kit.example.json"
# The repo-side copy of the vehicle. The registry examples are PAIRED (fleet, gates, and
# now the pin), so the repo's own tree carries the example too -- which means the vehicle
# must be written at BOTH paths by the ONE command that renders it, or every regeneration
# drifts the pair.
PIN_TWIN_REL = "registry/kit.example.json"

# The vehicle's own header. It is NOT the manifest's note: a reader of the vehicle is a
# factory deciding what to vendor, not this repo describing its own kit, and `kit_version`
# is computed over `files` + `classes` only, so a differing note cannot desynchronise the
# two — which is what lets the vehicle carry instructions its reader needs.
PIN_NOTE = (
    "SHAPE AND SNAPSHOT -- this file is the shipped kit manifest rendered for a factory to "
    "VENDOR. Copy it verbatim to `registry/kit.json` in your own repo at the moment you port "
    "kit files, and thereafter move it only when you deliberately port a new kit state. It is "
    "the record of WHICH kit you ported, and your own gate compares your tree against it.\\n\\n"
    "Why vendor rather than read ours: a gate against this repo's live manifest makes your "
    "verdict a function of OUR working tree and our backlog, so our movement reddens your "
    "audit for a change you never took. A gate against your pin reddens it only when your "
    "tree diverges from your own declaration, which is the only thing you can act on.\\n\\n"
    "`classes` is the field you cannot port without: it tells you which files are `closure` "
    "(they must travel with the tool that imports them), which are `shared` (a tool you run), "
    "and which are `factory` data (yours to fill in, never overwritten by an update). A pin "
    "without it leaves you unable to apply the port rule you were told to follow.\\n\\n"
    "Do not hand-edit this file in your tree. It is generated by `tools/kit_manifest.py` in "
    "the template repo, and `tools/kit_pin.py` is the one reader -- a pin you typed by hand is "
    "a reference nobody can reproduce."
)


def pin_vehicle(manifest: dict) -> dict:
    """The vehicle: the same `files`/`classes`/`kit_version`, with a reader's note."""
    return {
        "_note": PIN_NOTE,
        "kit_version": manifest["kit_version"],
        "file_count": manifest["file_count"],
        "files": manifest["files"],
        "classes": manifest["classes"],
    }


def render(obj: dict) -> str:
    """The ONE serializer for both outputs, so the vehicle cannot drift in formatting."""
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"

# ---------------------------------------------------------------------------
# THE CLASS TABLE -- DECLARED PER PATH, never derived from the import graph.
# ---------------------------------------------------------------------------
# WHY A CLASS AT ALL. `registry/kit.json` was 106 flat `path -> sha256` entries with
# no per-file predicate, so a factory's OWN gate list scored as drift against the
# template's, and a missing dependency scored the same as a missing instrument. The
# measured consequence: over the ten bootstrap-named files across five factories the
# figure was 1 same / 20 DIFF / 29 ABSENT, and FOUR of the five DIFFs were deliberate,
# reasoned forks (miidas' `subject_law.py` import, inferhub's `ack` event). A number
# that cannot say which of its cells mean something cannot be acted on per file.
#
# WHY DECLARED AND NOT DERIVED (owner ruling, 2026-09-25). An import-graph walk is
# blind to the dependencies that matter most: `tools/hooks/commit-msg:121` and
# `tools/hooks/pre-commit:175` load their predicates through
# `importlib.util.spec_from_file_location` from a STRING CONSTANT, so a static walk
# reports a hook complete while it is missing the file it cannot run without -- and
# the hook degrades to a WARNING rather than crashing. A declaration cannot miss it.
#
# WHAT EACH CLASS ANSWERS. The class is not about imports, it is about what a MISSING
# FILE MEANS, because that is the difference a member has to act on:
#   shared  -- a standalone instrument or document. Absent from a factory means the
#              factory is BEHIND: it never adopted it, or dropped it.
#   closure -- a module with no interface of its own, present only to be imported.
#              Absent means the factory ported its PARENT without its closure, so the
#              parent is BROKEN at import: the measured `#137` defect, where a faithful
#              copy of `tools/ledger.py` died with ModuleNotFoundError on three modules
#              the template imports at :63, :73 and :85.
#   factory -- a seed the factory instantiates under a DIFFERENT name with its own
#              placeholders filled. It is never compared byte-for-byte, because the
#              factory's copy legitimately differs: `processes.md.tmpl` is BOOTSTRAP
#              line 60's "Add `processes.md` from processes.md.tmpl", and a member's
#              `processes.md` is its own law, not a stale copy of ours.
#
# THE DISCRIMINATOR FOR `closure`, measured and stated so it is reproducible: a shipped
# `.py` that has NO `ArgumentParser` and is imported by another shipped file. Presence
# of an `ArgumentParser` is the objective mark of "this has an interface of its own",
# which is why `tools/registry.py` and `tools/telemetry.py` are `shared` even though
# `tools/ledger.py` imports them -- a factory missing `registry.py` is behind on an
# instrument, not missing a dependency. The ten below carry no CLI and no importer of
# their own would work without them.
CLOSURE_MODULES = frozenset({
    # tools/ -- imported by the executables, never invoked directly
    "TEMPLATE/tools/field_predicate.py",     # imported_by 10 shipped files
    "TEMPLATE/tools/gate_budget.py",         # imported by tools/audit.py
    "TEMPLATE/tools/ledger_declaration.py",  # the HARD tier: raises at import
    "TEMPLATE/tools/reconstruction.py",      # the HARD tier: raises at import
    "TEMPLATE/tools/kit_pin.py",             # loaded BY PATH by tools/patrol_host_state.py
                                             # (KIT_PIN) and by a factory's own pin gate; it
                                             # has no CLI, so a factory that ports the runner
                                             # without it gets a leg that reports NOT RUN
    "TEMPLATE/tools/registry_render.py",     # imported by tools/registry.py
    # tests/ -- helper modules the gates import rather than run
    "TEMPLATE/tests/gate_fixtures.py",       # imported_by 5 gates
    "TEMPLATE/tests/gate_registry.py",       # the gate roster, read by audit.py's gate
    "TEMPLATE/tests/hook_installation.py",   # imported by 2 gates
    "TEMPLATE/tests/ledger_boundary.py",     # imported_by 7 gates
    "TEMPLATE/tests/rework_table.py",        # the ONE entries-table parser (miidas
                                             # arrived at the same module independently
                                             # as tools/rework_entries.py -- Phase D
                                             # candidate, and the reason a second
                                             # parser is the drift class)
})

# The seeds. Declared per path rather than matched on suffix, so that a file named
# `*.example.json` which is in fact a shipped instrument cannot sneak out of the
# comparison on a naming accident -- and so that adding a seed is a decision.
FACTORY_SEEDS = frozenset({
    # The template DIRECTORY's own README, and it is a seed because the mapping is
    # `TEMPLATE/README.md` -> `README.md`: a factory's root README is its OWN document
    # describing its own factory, and it legitimately differs from this one. Measured
    # 2026-09-25 while building the member-side gate: classed `shared`, it made EVERY
    # member red falsely -- the repo's own README differs from the template's by design,
    # and a member's would too. `BOOTSTRAP.md` never instructs a factory to copy it (its
    # only mention is a leak-test link), which is what settles the class rather than the
    # similarity of the filenames.
    "TEMPLATE/README.md",
    "TEMPLATE/AGENTS.md.tmpl",
    "TEMPLATE/ONTOLOGY.md.tmpl",
    "TEMPLATE/SKILL.md.tmpl",
    "TEMPLATE/growth-stages.md.tmpl",
    "TEMPLATE/processes.md.tmpl",
    "TEMPLATE/docs/ledger-commit-exemptions.example.json",
    "TEMPLATE/docs/ledger-invariants.example.json",
    "TEMPLATE/docs/ledger-no-shrink-exemptions.example.json",
    "TEMPLATE/docs/ledger-retirements.example.json",
    "TEMPLATE/docs/products.example.json",
    "TEMPLATE/docs/rework-relative-revision-exemptions.example.json",
    "TEMPLATE/registry/fleet.example.json",
    "TEMPLATE/registry/gates.example.json",
    "TEMPLATE/registry/kit.example.json",      # the pin vehicle -- a factory data file
})

CLASSES = ("shared", "closure", "factory")

# THE RUNNABLE PREDICATE -- one home, consumed by `class_gaps` below and by
# `tools/kit_surfaces.py`'s census. Two call sites, ONE predicate: a second copy is how
# those two instruments came to disagree about `kit_pin.py` in the first place.
#
# It asks ONE question -- can the kit RUN this file? -- and the kit runs files THREE ways:
# directly (an entry point), through `tools/audit.py`'s registration with an
# `ArgumentParser`, or through that same registration as a pytest-form gate. All three
# must be in the predicate. The first version knew only the first two and refused ten
# correct pytest gates as `unrunnable`; a false refusal is the one direction this arm
# must never take, because it would make a correct declaration red.
ENTRY_POINT = re.compile(r'^\s*if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:', re.M)
PYTEST_FORM = re.compile(r'^def\s+test_', re.M)

def is_runnable(src: str) -> bool:
    """Whether the kit can run this file, by any of the three mechanisms it ships."""
    if ENTRY_POINT.search(src):
        return True
    if PYTEST_FORM.search(src):
        return True
    return "ArgumentParser" in src


def classify(rel: str) -> str:
    """One class per shipped path. `shared` is the residual, so a NEW file is never
    silently unclassified -- and `--check` refuses a closure/seed path that is no
    longer shipped, which is how the declaration itself cannot rot."""
    if rel in CLOSURE_MODULES:
        return "closure"
    if rel in FACTORY_SEEDS:
        return "factory"
    return "shared"

NOTE = (
    "Reference manifest of the shipped kit: every file under TEMPLATE/, with its "
    "sha256 AND its class. GENERATED by tools/kit_manifest.py -- never hand-edited, "
    "because a hand-kept list of shipped files is a second copy of the tree that goes "
    "stale silently. `kit_version` is a digest over the manifest's own "
    "(path, sha256, class) triples, so it cannot describe a tree other than the one it "
    "was computed from. `files` maps each path to its sha256; `classes` maps each path "
    "to what a MISSING FILE MEANS in a factory: `shared` = a standalone instrument, so "
    "its absence means the factory is BEHIND; `closure` = a module with no interface of "
    "its own, so its absence means the factory ported its parent without its closure and "
    "the parent is BROKEN at import (the #137 defect); `factory` = a seed the factory "
    "instantiates under a different name, never compared byte-for-byte. Every shipped "
    "path carries a class and a path without one is a `--check` failure, not a default. "
    "Transient artifacts (__pycache__, .pytest_cache, .audit.lock, *.pyc) are excluded: "
    "they are build residue, not kit. Regenerate with `python3 tools/kit_manifest.py`; "
    "verify with `--check`, which names every drifted, missing, unlisted and unclassified "
    "file."
)

def in_manifest_population(rel: str) -> bool:
    """Whether a repo-relative path belongs to the set the manifest describes.

    The pin VEHICLE is outside it by construction: it carries the manifest's own
    content, so it cannot carry its own digest. Asking this question in ONE place is
    what keeps the generator and the drift predicate from disagreeing — when only
    the generator asked it, a staged vehicle was reported by the hook as having
    "escaped" a manifest it is not part of, which is a FALSE FAILURE rather than a
    lenient one.
    """
    return rel != PIN_VEHICLE_REL


def kit_paths() -> list[str]:
    """Every shipped file, repo-relative, sorted — the set the manifest describes."""
    out: list[str] = []
    for path in KIT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.name in EXCLUDED_FILES or path.suffix in EXCLUDED_SUFFIXES:
            continue
        relative = str(path.relative_to(REPO))
        if not in_manifest_population(relative):
            continue
        out.append(relative)
    return sorted(out)

def digest_path(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def digest(rel: str) -> str:
    """The sha256 of one shipped file, at its repo-relative path."""
    return digest_path(REPO / rel)


def manifest_key(local: str) -> str:
    """The manifest key for a file the caller holds.

    The manifest is keyed TEMPLATE-relative, because that is where the kit lives in THIS
    repo; a factory that ported a file holds it at the UNprefixed path (`tools/ledger.py`)
    and often has no TEMPLATE/ directory at all. So one rule: strip a leading TEMPLATE/,
    then re-prefix it. Stated here rather than in a caller, because a second copy of this
    rule is how a lookup starts answering `not-in-kit` for a file the kit does ship.
    """
    parts = [p for p in pathlib.PurePosixPath(local).parts if p != "."]
    if parts and parts[0] == "TEMPLATE":
        parts = parts[1:]
    return "TEMPLATE/" + "/".join(parts)


def identity(paths: list[str]) -> int:
    """Print, per file, the digest the caller holds and what the kit says about it."""
    if not MANIFEST.is_file():
        print(f"kit identity: {MANIFEST.relative_to(REPO)} is absent, so there is no "
              "reference to answer against. A factory that never vendored the pin lands "
              "here -- see BOOTSTRAP step 4b and registry/kit.json.")
        return 1
    declared = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = declared.get("files") or {}
    classes = declared.get("classes") or {}
    kit = declared.get("kit_version")
    bad = 0
    for local in paths:
        p = pathlib.Path(local)
        if not p.is_file():
            print(f"{local}: UNREADABLE — no such file")
            bad = 1
            continue
        key = manifest_key(local)
        mine = digest_path(p.resolve())
        cls = classes.get(key)
        want = files.get(key)
        tail = f"class={cls}" if cls else "class=?"
        if want is None:
            # Not a failure: the kit does not ship this path, so there is nothing to
            # compare. Naming the key that was looked up is what lets a reader tell
            # "the kit lacks it" from "my prefix rule is wrong".
            print(f"{local}: sha256={mine} not-in-kit (looked up {key}) "
                  f"kit_version={kit}")
        elif mine == want:
            print(f"{local}: sha256={mine} matches-kit {tail} kit_version={kit}")
        else:
            print(f"{local}: sha256={mine} differs-from-kit "
                  f"declared={want} {tail} kit_version={kit}")
    return bad

def kit_version(files: dict[str, str], classes: dict[str, str] | None = None) -> str:
    """A digest over the manifest's own (path, sha256, class) triples.

    Built from the SORTED triples with an explicit separator, so two different trees
    cannot produce the same digest by concatenation ambiguity.

    The CLASS IS IN THE DIGEST, and that is deliberate rather than incidental: the
    class is part of what the reference SAYS about a path, so reclassifying a file
    changes the reference and must move its version. A version that covered only the
    bytes would let `shared` become `factory` -- which switches a cell from a finding
    to no comparison at all -- without any consumer noticing that the meaning of the
    manifest had moved.
    """
    h = hashlib.sha256()
    for rel, sha in sorted(files.items()):
        h.update(f"{rel}\0{sha}\0{(classes or {}).get(rel, '')}\n".encode())
    return h.hexdigest()[:12]

def class_gaps(classes: dict[str, str], files: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    """(unclassified, stale, unrunnable_shared) -- paths with no class, classes naming
    paths the kit no longer ships, and `shared` paths that cannot be run.

    The first two are refusals of ONE direction each: an unclassified shipped file would
    be compared by a consumer with no predicate to apply, and a stale class entry is a
    declaration that outlived the file it described -- the phantom-artefact shape, in the
    manifest.

    The third is the residual-default failure, and it is measured rather than theoretical:
    `classify()` returns `shared` for anything not in a declared set, so a NEW closure
    module is silently classed `shared` and nothing in the tree says otherwise. That is
    exactly what happened to `TEMPLATE/tools/kit_pin.py` when it landed (plan 2646d31a
    task 6) -- two instruments in this repo then disagreed about its class, the manifest
    saying `shared` and `tools/kit_surfaces.py` saying `closure`, and `--check` was green
    because it only ever compares the manifest to the tree, never a class to a property.

    So this arm refuses the combination that cannot be true: the NOTE defines `shared` as
    *"a standalone instrument"*, and a file the kit cannot run by ANY of its three
    mechanisms is not one. It is deliberately UNSCOPED over the shipped `.py` files --
    a new closure anywhere in the kit is what the residual default silently absorbs, and
    a directory allow-list would be the same bet one level down. Measured clean over the
    108 shipped paths: `shared` 84, `closure` 11, `factory` 13, zero unrunnable.
    It is ONE-DIRECTIONAL on purpose. It never tries to derive which files ARE closure --
    A.1 measures that an `ast` walk is blind to both hooks' `importlib` loads and to the
    lazy tier a fixture skips, so a derived closure would be wrong in the other direction
    and would refuse correct declarations. A declared `closure` that is runnable passes
    here; an undeclared `shared` that is not, does not.
    """
    unclassified = sorted(rel for rel in files if rel not in classes)
    stale = sorted(rel for rel in classes if rel not in files)
    unrunnable = []
    for rel, cls in classes.items():
        if cls != "shared" or rel not in files:
            continue
        if not rel.endswith(".py"):
            continue
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if is_runnable(src):
            continue
        unrunnable.append(rel)
    return unclassified, stale, sorted(unrunnable)

def build() -> dict:
    files = {rel: digest(rel) for rel in kit_paths()}
    classes = {rel: classify(rel) for rel in files}
    return {
        "_note": NOTE,
        "kit_version": kit_version(files, classes),
        "file_count": len(files),
        "files": files,
        "classes": classes,
    }

def compare(current: dict, declared: dict) -> tuple[list[str], list[str], list[str]]:
    """(changed, missing, unlisted) — three DIFFERENT facts, never folded together.

    A file whose bytes moved is a port; a file the manifest names but the tree does
    not carry is a deletion; a file the tree carries but the manifest does not name
    is one that ESCAPED the manifest. The last is the one a hand-kept list would
    hide, which is why it is a failure rather than a note.

    The population is `in_manifest_population`, not "everything under TEMPLATE/":
    the pin vehicle carries the manifest's own content and so cannot carry its own
    digest, and reporting it as escaped would be a false failure.
    """
    cur, dec = current.get("files") or {}, declared.get("files") or {}
    changed = sorted(rel for rel in dec if rel in cur and cur[rel] != dec[rel])
    missing = sorted(rel for rel in dec if rel not in cur)
    unlisted = sorted(
        rel for rel in cur if rel not in dec and in_manifest_population(rel)
    )
    return changed, missing, unlisted

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="verify the tree against the manifest instead of regenerating it",
    )
    parser.add_argument(
        "--identity", nargs="+", metavar="PATH",
        help="print which kit copy each PATH is, and exit (a query, not a gate)",
    )
    args = parser.parse_args(argv)

    if args.identity:
        return identity(args.identity)

    if not KIT_ROOT.is_dir():
        print(
            f"kit manifest: {KIT_ROOT} does not exist — there is no shipped kit in this "
            "tree, so there is nothing to describe. A bootstrapped factory lands here."
        )
        return 0

    current = build()

    if not args.check:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(render(current), encoding="utf-8")
        rendered = render(pin_vehicle(current))
        for rel in (PIN_VEHICLE_REL, PIN_TWIN_REL):
            path = REPO / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        print(f"kit manifest written: {MANIFEST.relative_to(REPO)} — "
              f"{current['file_count']} file(s), kit_version {current['kit_version']}")
        print(f"pin vehicle written:  {PIN_VEHICLE_REL} — vendored by a factory verbatim, "
              f"excluded from the set it renders")
        return 0

    if not MANIFEST.is_file():
        print(f"kit manifest: {MANIFEST.relative_to(REPO)} is absent — regenerate it with "
              "`python3 tools/kit_manifest.py`")
        return 1

    declared = json.loads(MANIFEST.read_text(encoding="utf-8"))
    changed, missing, unlisted = compare(current, declared)

    for rel in changed:
        print(f"  DRIFTED   {rel} — {declared['files'][rel][:12]} -> {current['files'][rel][:12]}")
    for rel in missing:
        print(f"  MISSING   {rel} — named by the manifest, absent from the tree")
    for rel in unlisted:
        print(f"  UNLISTED  {rel} — in the tree but not in the manifest (escaped it)")

    # The class check is SEPARATE from `compare`, which the shipped pre-commit hook
    # unpacks as a 3-tuple; widening that arity would break a consumer this file does
    # not own. A path with no class is a path a member cannot be judged on.
    unclassified, stale, unrunnable = class_gaps(
        declared.get("classes") or {}, declared.get("files") or {}
    )
    for rel in unclassified:
        print(f"  NO-CLASS  {rel} — shipped, but carrying no class, so a consumer has no "
              f"predicate to apply to it")
    for rel in stale:
        print(f"  STALE-CLASS {rel} — a class is declared for a path the manifest no longer "
              f"ships")
    for rel in unrunnable:
        print(f"  UNRUNNABLE {rel} — classed `shared` (a standalone instrument) but it "
              f"carries no entry point and no parser, so nothing can run it")
    bad_class = sorted(
        f"{rel}={cls}" for rel, cls in (declared.get("classes") or {}).items() if cls not in CLASSES
    )
    for entry in bad_class:
        print(f"  BAD-CLASS {entry} — not one of {', '.join(CLASSES)}")

    if changed or missing or unlisted or unclassified or stale or bad_class or unrunnable:
        print(f"kit manifest DRIFTED: {len(changed)} changed, {len(missing)} missing, "
              f"{len(unlisted)} unlisted, {len(unclassified)} unclassified, "
              f"{len(stale)} stale-class, {len(unrunnable)} unrunnable-shared — "
              f"regenerate with `python3 tools/kit_manifest.py`")
        return 1

    counts: dict[str, int] = {}
    for cls in (declared.get("classes") or {}).values():
        counts[cls] = counts.get(cls, 0) + 1
    breakdown = ", ".join(f"{c}={counts[c]}" for c in CLASSES if counts.get(c))
    print(f"kit manifest in agreement: {current['file_count']} file(s), "
          f"kit_version {declared.get('kit_version')}, classes {breakdown}")
    return 0

if __name__ == "__main__":
    sys.exit(main())