#!/usr/bin/env python3
"""The identity of a shipped instrument, read from the kit manifest it shipped in.

WHY THIS IS A MODULE AND NOT TEN COPIES. Ten shipped executables need to answer the
same question -- "which copy of me is this?" -- and a version string hand-written into
each of them is ten implementations of one predicate, which is the drift class this
kit already rules on elsewhere (the `#143` remedy is literally "ONE predicate, shared,
so the class cannot recur per-site"). So the lookup lives here once and every
executable imports it, which makes this file CLOSURE of all ten: a factory that ports
`tools/ledger.py` without this module gets `ModuleNotFoundError` at import, loudly,
rather than a ledger whose `--version` silently lies.

WHY THE VERSION IS NEVER TYPED INTO THE FILE IT DESCRIBES. That is not a preference,
it is a circularity: `registry/kit.json` records the sha256 of every shipped file, so
writing a version string into `tools/ledger.py` would move that file's digest, which
would move `kit_version`, which would make the string stale the moment it was written
and would force a regeneration that moves it again. A generated version therefore has
to live OUTSIDE the bytes it identifies, and the instrument has to READ it back from
the manifest. The consequence worth stating plainly: the string this prints is the
manifest's own, so it cannot disagree with the reference -- and it cannot be hand-set
either, which is the point.

WHAT IT ANSWERS, AND WHAT IT DOES NOT. It prints this copy's sha256 and the kit
version the manifest says it belongs to. It does NOT say whether the copy is CURRENT:
that needs the template's live kit_version, which a member tree cannot see. The
published census (the kit-drift leg's artifact) carries the live figure, so a factory
compares its own printed version against the published one. Absent that comparison
this module reports identity, not freshness -- and saying so is the difference between
a version string that means something and one that reads as a clean bill.

LAYOUT. The manifest is found by walking up from this file to the first `registry/
kit.json`, which works in both trees that matter: here, where the instrument sits at
`TEMPLATE/tools/kit_identity.py`, and in a factory that ported it, where it sits at
`tools/kit_identity.py`. The lookup key is then re-prefixed with `TEMPLATE/`, because
the manifest's keys keep that prefix in EVERY tree -- the drift leg compares a member
at `<member>/<path minus TEMPLATE/>`, so the prefix is an artefact of how the kit is
stored here and never part of what a factory carries.

Run:  python3 tools/kit_identity.py            # this module's own identity
Exit: 0 identity printed; 1 no manifest found, and the reason named.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

MANIFEST_REL = ("registry", "kit.json")
PREFIX = "TEMPLATE/"


def find_manifest(start: Path) -> Path | None:
    """The nearest `registry/kit.json` at or above `start`, or None.

    Walking rather than assuming a fixed number of parents is what makes this work in
    both layouts. A hard-coded `parents[2]` would resolve to the wrong directory in a
    factory tree and read a manifest that is not the one this copy shipped against --
    which is the wrong-object class, in a path.
    """
    start = start.resolve()
    for parent in (start, *start.parents):
        cand = parent.joinpath(*MANIFEST_REL)
        if cand.is_file():
            return cand
    return None


def manifest_key(here: Path, manifest: Path) -> str:
    """This file's key inside `manifest` -- TEMPLATE/-prefixed, whatever tree it runs in.

    Returns `str`, and that is load-bearing rather than cosmetic: the manifest's keys
    are JSON strings, so a `PosixPath` here misses every lookup and the caller reports
    "identity cannot be read" for a file the manifest describes perfectly well. Measured
    2026-09-25 -- the first version returned the Path and failed on its own entry.
    """
    rel = str(here.resolve().relative_to(manifest.parent.parent))
    return rel if rel.startswith(PREFIX) else PREFIX + rel


class VersionAction(argparse.Action):
    """`--version` that prints this copy's identity WITHOUT argparse's line wrapping.

    WHY NOT `action="version"`. Argparse routes that through `HelpFormatter`, which
    wraps at the terminal width, so the version string breaks mid-token on a narrow
    terminal -- measured 2026-09-25: at COLUMNS=40, `ledger.py --version` printed the
    sha and the kit version on SEPARATE LINES, and a script parsing the output would see
    a newline where the format says a space. A version string is machine-read as often
    as it is read by eye, so its shape must not depend on how wide the caller's terminal
    happens to be. This action writes the line directly and exits.

    `nargs=0` is what makes it an action rather than an option taking a value.
    """

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        # `sys.argv[0]` is the invoked script -- the executable whose identity is being
        # asked for, which is not necessarily this module.
        print(version_string(Path(sys.argv[0])))
        parser.exit(0)


def identity_of(path: Path) -> tuple[str, str, str, str, str] | None:
    """`(status, actual12, kit_version, declared12, key)` — or None when unreadable.

    `status` is one of `ok` (bytes match the manifest), `edited` (bytes differ — a fork
    or undeclared drift), `not-listed` (a manifest was found and does not describe this
    path), or `unreadable` (a manifest exists but cannot be parsed).

    FOUR OUTCOMES RATHER THAN A BOOLEAN, because the first version collapsed "no
    manifest" and "not in the manifest" into one None and reported the first for both —
    measured 2026-09-25 on an unshipped probe file, where it printed "no kit manifest
    found at or above tools/" for a tree whose manifest was right there. A message that
    names the wrong cause sends the reader to fix the wrong thing.
    """
    manifest = find_manifest(path)
    if manifest is None:
        return None
    try:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ("unreadable", "", "", "", str(manifest))
    files = doc.get("files") or {}
    key = manifest_key(path, manifest)
    declared = files.get(key)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    actual = h.hexdigest()
    kit = str(doc.get("kit_version") or "")
    if declared is None:
        return ("not-listed", actual[:12], kit, "", key)
    if actual != declared:
        return ("edited", actual[:12], kit, str(declared)[:12], key)
    return ("ok", actual[:12], kit, str(declared)[:12], key)


def version_string(path: Path, prog: str | None = None) -> str:
    """The one-line version a shipped executable prints. Identity, never a freshness claim.

    Each outcome says what it actually knows, and no outcome prints a version it cannot
    support: `ok` reports the copy as shipped, `edited` reports it as diverged from the
    manifest and names both digests, `not-listed` says the manifest does not describe
    this path, and a missing manifest says so rather than inventing a number.
    """
    name = prog or path.name
    got = identity_of(path)
    if got is None:
        return (f"{name}: no kit manifest at or above {path.parent} — this copy's identity "
                "cannot be read, and printing a version anyway would be a claim with "
                "nothing behind it")
    status, actual, kit, declared, key = got
    if status == "unreadable":
        return f"{name}: the kit manifest {key} exists but could not be parsed"
    if status == "not-listed":
        return (f"{name}: sha {actual} @ kit {kit} — NOT IN THE MANIFEST: {key} is not a "
                "shipped path, so this is either a new file the manifest has not caught up "
                "with or a copy installed outside the kit")
    if status == "edited":
        return (f"{name}: sha {actual} @ kit {kit} — EDITED IN PLACE: the manifest declares "
                f"{declared} for {key}, so this is a declared fork or an undeclared drift, "
                "not the shipped copy")
    return f"{name}: sha {actual} @ kit {kit} ({key})"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = Path(argv[0]) if argv else Path(__file__)
    print(version_string(target))
    return 0 if identity_of(target) else 1


if __name__ == "__main__":
    sys.exit(main())
