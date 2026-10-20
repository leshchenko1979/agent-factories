#!/usr/bin/env python3
"""The delivery leg: hand a factory an update as ONE unit, and never touch its own files.

WHY THIS EXISTS. Measured 2026-09-25 over five member factories: 1 same / 20 DIFF / 29
ABSENT across the ten bootstrap-named files, with `tools/gate_budget.py` and both
`tools/hooks/` refusal points absent from ALL FIVE. The kit could tell a factory it had
drifted and had no mechanism to hand it the update — the law corpus carried `vendor` 0,
`re-sync` 0, `propagat` 0-1, and `registry/kit.json` is a manifest, not a channel.

WHAT IT MOVES, AND WHY THOSE CLASSES. The `classes` map in the pin decides:
`standalone` and `closure` are delivered (a tool and the modules it needs to run);
`shared-surface` is delivered for the same reason and more urgently -- the file writes
a box-wide store, so leaving a stale copy in place is what the census reds (#514);
`seed` is NEVER written, because those are the factory's own law and data — its
`SKILL.md`, its `gates.json`, its exemption lists. An update that overwrote a declaration
would destroy the thing the declaration exists to record.

WHY A LOCAL MODIFICATION IS SKIPPED, NOT OVERWRITTEN. A file whose bytes differ from the
member's OWN pin is the member's deliberate work. Overwriting it would silently discard a
fork, so the bytes are left alone. The PIN then claims the MEMBER's digest for that path
rather than ours (#198): a pin claiming bytes this run deliberately did not write would red
the member's gate on a state WE created. Their digest keeps their gate green and keeps the
fork visible where it can be acted on -- the patrol compares this pin against OUR
`registry/kit.json` and sees the divergence. The transport does not decide for them.

WHY THE PIN MOVES WITH THE BYTES, ATOMICALLY. If the bytes moved and the pin did not, the
member's own gate would red on a state WE created — the worst possible outcome, since it
is indistinguishable from the member having broken something. Bytes and pin are written in
one run, and the gate proves the pair.

Run:  python3 tools/kit_deliver.py --to <factory-root> [--dry-run]
Exit: 0 delivered (or would deliver) with no refusal; 1 a refusal or an unreadable target.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import kit_manifest as KM  # noqa: E402
import kit_pin as KP  # noqa: E402

# The classes an update may write. `seed` is absent on purpose -- see the docstring.
# `shared-surface` is PRESENT on purpose: it is a file every factory writes through, so
# refusing to deliver it would leave the stale writer the census exists to report.
DELIVERED_CLASSES = ("standalone", "closure", "shared-surface")

# What the plan says about each path. `seed` and `LOCAL-MODIFICATION` are both refusals
# to write, but they are DIFFERENT facts and a reader must be able to tell them apart.
WRITTEN = ("ADD", "UPDATE")


# THE PIN'S OWN NOTE (#521, remedy point 2). The note that ships in `registry/kit.json` is the
# MANIFEST's -- it describes a snapshot of the template's tree, names the generator, and warns
# against hand-editing THAT file. A pin is a different artifact: it is the member's declaration
# of what it took, it is written by this transport, and its two digests answer two different
# questions. Carrying the manifest's note into the pin was the same conflation as carrying its
# digest, one field over: the note asserted `kit_version` described the manifest while the pin
# used that name for its own triples.
PIN_NOTE = (
    "`kit_version` is a digest over THIS pin's own (path, sha256, class) triples -- what this "
    "pin CARRIES. Recompute it after merging a fork, or it will name bytes the pin does not "
    "hold. `source_kit_version` is the digest of the template manifest this pin was ported "
    "FROM -- which kit state it CAME FROM -- and it is the value "
    "`git log -S<source_kit_version> -- registry/kit.json` resolves in the template repo. A "
    "self-digest cannot answer the second question and a source digest cannot answer the "
    "first, which is why a delivered pin carries both. `class_vocabulary` records the classes "
    "the pin's WRITER knew, so a reader older than a class can name the port instead of "
    "reading a real class as a misspelling."
)

def source_state() -> tuple[dict, dict, dict, str]:
    """Our own manifest: (files, classes, kit_version, note)."""
    declared = json.loads(KM.MANIFEST.read_text(encoding="utf-8"))
    return (
        declared.get("files") or {},
        declared.get("classes") or {},
        str(declared.get("kit_version") or ""),
        str(declared.get("_note") or ""),
    )


# ---------------------------------------------------------------------------
# THE CURRENCY LEG (#523). Two questions that a single "is it current" test conflates,
# each answered by the fact it can actually check.
#
#   (a) DOES THE DECLARED MANIFEST DESCRIBE THIS TREE'S BYTES?  -> REFUSE.
#       `kit_manifest.compare` over the tree's own digests. A manifest that lies about the
#       bytes it names must never be transported: the member's gate would then judge their
#       tree against a reference that describes a different one.
#
#   (b) IS THE TREE BEHIND origin/main?  -> WARN, naming the distance.
#       A deliberate pin, an offline member and a release window are all LAWFUL states, so
#       this must never red. And it must degrade rather than fail: a tree with no remote or
#       one that has never fetched has no origin/main to compare against, and a check that
#       cannot see its population reports THAT rather than reporting zero.
#
# WHAT IS DELIBERATELY NOT HERE: a HEAD-computed `kit_version`. That is the remedy the
# issue's own doc row named, and it would rebuild the defect #185 removed -- a version
# computed from HEAD reds on an unrelated commit in the TEMPLATE repo, and the pin's whole
# purpose is to red only when a factory's tree diverges from its own declaration.
# ---------------------------------------------------------------------------
CURRENCY_UNKNOWN = "currency unknown — no origin/main"

def _behind(root: Path) -> tuple[int | None, str]:
    """How far the tree is behind `origin/main`, or None with the reason it is unknown."""
    try:
        proc = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None, CURRENCY_UNKNOWN
    if proc.returncode != 0:
        return None, CURRENCY_UNKNOWN
    try:
        return int(proc.stdout.strip()), ""
    except ValueError:
        return None, CURRENCY_UNKNOWN

def currency(root: Path | None = None) -> dict:
    """(a) the manifest against the tree's bytes; (b) the distance behind origin/main."""
    base = Path(root) if root is not None else REPO
    out: dict = {"manifest_problem": None, "changed": [], "missing": [], "unlisted": [],
                 "behind": None, "behind_note": ""}
    manifest_path = base / "registry" / "kit.json"
    try:
        declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        out["manifest_problem"] = f"{manifest_path} could not be read: {exc}"
        return out
    changed, missing, unlisted = KM.compare(KM.build(base), declared)
    out.update(changed=changed, missing=missing, unlisted=unlisted)
    if changed or missing or unlisted:
        parts: list[str] = []
        if changed:
            parts.append(f"{len(changed)} changed (e.g. {changed[0]})")
        if missing:
            parts.append(f"{len(missing)} named but absent (e.g. {missing[0]})")
        if unlisted:
            parts.append(f"{len(unlisted)} on disk but unnamed (e.g. {unlisted[0]})")
        out["manifest_problem"] = (
            "the declared manifest does not describe this tree's bytes: "
            + ", ".join(parts)
            + " — regenerate with `python3 tools/kit_manifest.py` before delivering, "
              "because a manifest that lies about the bytes it names must never be "
              "transported"
        )
    distance, note = _behind(base)
    out["behind"] = distance
    out["behind_note"] = note
    return out

def _print_currency(cur: dict) -> None:
    """The two answers, printed so a green run shows what it examined."""
    if cur["behind_note"]:
        print(f"  {cur['behind_note']} — the distance behind the remote is NOT measured, "
              f"and that is reported rather than read as zero")
    elif cur["behind"]:
        print(f"  WARN behind origin/main by {cur['behind']} commit(s) — a lawful state "
              f"(a deliberate pin, an offline member, a release window); nothing refuses on it")
    else:
        print("  current with origin/main")
    if cur["manifest_problem"]:
        print(f"  REFUSED — {cur['manifest_problem']}")
    else:
        print(f"  manifest agrees with the tree's bytes "
              f"({len(cur['changed']) + len(cur['missing']) + len(cur['unlisted'])} drift)")

def plan(target: Path) -> dict:
    """What an update WOULD do, per path. Pure: it reads, and writes nothing."""
    files, classes, kit, note = source_state()
    pin_path, pin, problem = KP.vendored_pin_in(target)
    if pin is None:
        return {"problem": problem, "rows": [], "pin_path": pin_path}
    pin_files: dict[str, str] = pin.get("files") or {}
    rows: list[dict] = []
    for rel in sorted(files):
        cls = classes.get(rel, "?")
        local = KP.member_path(rel)
        src = files[rel]
        if cls == "seed":
            rows.append({"rel": rel, "local": local, "verdict": "DECLARATION",
                         "cls": cls, "why": "the factory's own — never written"})
            continue
        if cls not in DELIVERED_CLASSES:
            rows.append({"rel": rel, "local": local, "verdict": "REFUSED-CLASS",
                         "cls": cls, "why": "unknown class — refused rather than guessed"})
            continue
        p = target / local
        actual = KP.sha256_of(p) if p.is_file() else None
        pinned = pin_files.get(rel)
        if actual is None:
            verdict, why = "ADD", "the factory does not carry it"
        elif pinned is not None and actual != pinned:
            verdict, why = "LOCAL-MODIFICATION", "differs from its OWN pin — a fork, left alone"
        elif actual == src:
            verdict, why = "CURRENT", "already at the delivered bytes"
        else:
            verdict, why = "UPDATE", "at the pin's older bytes"
        rows.append({"rel": rel, "local": local, "verdict": verdict, "cls": cls,
                     "actual": actual, "why": why})
    retired = sorted(rel for rel in pin_files if rel not in files)
    return {"problem": None, "rows": rows, "pin_path": pin_path,
            "kit_version": kit, "note": note, "pin_version": pin.get("kit_version"),
            "retired": retired}


def deliver(target: Path, dry_run: bool) -> int:
    """Write the plan. Bytes and pin move together, or nothing moves."""
    planned = plan(target)
    if planned["problem"]:
        print(f"kit deliver: REFUSED — {planned['problem']}")
        return 1

    # (a) REFUSES, (b) WARNS — read before a single byte moves, and printed either way so a
    # green run shows what it examined rather than only that it passed (#523).
    # BOTH QUESTIONS ARE ABOUT THE SOURCE, not the member (#523). The transport ships OUR
    # manifest; if it lies about our bytes, the member receives a lie. The member's own pin
    # is deliberately NOT judged here -- a factory carries forks, so its pin legitimately
    # disagrees with our manifest, and reading that as a refusal would refuse every delivery.
    cur = currency()
    print(f"kit deliver — source state ({REPO})")
    if cur["manifest_problem"]:
        print(f"kit deliver: REFUSED — {cur['manifest_problem']}")
        return 1
    _print_currency(cur)

    rows = planned["rows"]
    written = [r for r in rows if r["verdict"] in WRITTEN]
    skipped = [r for r in rows if r["verdict"] == "LOCAL-MODIFICATION"]
    declarations = [r for r in rows if r["verdict"] == "DECLARATION"]
    refused = [r for r in rows if r["verdict"] == "REFUSED-CLASS"]

    head = "would deliver" if dry_run else "delivering"
    print(f"kit deliver — {head} {planned['kit_version']} to {target}")
    print(f"  pin: {planned['pin_path']}  (was {planned['pin_version']})")
    print(f"  population {len(rows)} path(s): {len(written)} written, "
          f"{len(skipped)} local fork(s) skipped, {len(declarations)} declaration(s) untouched, "
          f"{len(refused)} refused")

    if refused:
        print("\nREFUSED (an unknown class is not a licence to guess):")
        for r in refused:
            print(f"  {r['rel']}  class={r['cls']}")
        return 1

    for r in written:
        print(f"  {r['verdict']:6} {r['local']}  ({r['cls']})")
        if dry_run:
            continue
        src = REPO / r["rel"]
        dst = target / r["local"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    if skipped:
        print("\nSKIPPED — the factory's own work; its gate will name the divergence:")
        for r in skipped:
            print(f"  {r['local']}")

    if planned["retired"]:
        print(f"\nRETIRED in the source, kept in the pin ({len(planned['retired'])}):")
        for rel in planned["retired"]:
            print(f"  {rel}")

    if dry_run:
        print("\ndry run — nothing written, the pin did not move")
        return 0

    # THE PIN MOVES WITH THE BYTES. It becomes the delivered state, plus any retired entry
    # the factory still carries, so a path we stopped shipping is not silently un-declared.
    files, classes, kit, note = source_state()
    _, pin, problem = KP.vendored_pin_in(target)
    if pin is None:
        print(f"kit deliver: REFUSED after writing — {problem}")
        return 1
    merged_files = dict(files)
    merged_classes = dict(classes)
    # A LOCAL-MODIFICATION keeps the MEMBER's own digest (#198). The bytes are deliberately
    # NOT written, so a pin claiming OUR digest would red the member's gate on a state this
    # deliver itself created -- the one outcome the atomicity rule exists to prevent, and
    # indistinguishable to them from having broken something. Their digest keeps their gate
    # green; the fork stays visible where it can be acted on, because the patrol compares
    # this pin against OUR registry/kit.json and sees the divergence.
    for r in skipped:
        merged_files[r["rel"]] = r["actual"]
    for rel in planned["retired"]:
        merged_files[rel] = (pin.get("files") or {})[rel]
        merged_classes[rel] = (pin.get("classes") or {}).get(rel, "seed")
    pin["files"] = merged_files
    pin["classes"] = merged_classes
    pin["file_count"] = len(merged_files)
    # THE FIELD SPLITS (#521). Two different questions, two different values:
    #
    #   source_kit_version = OUR manifest digest -> WHICH KIT STATE this pin was ported
    #       from. This is the value `git log -S<value> -- registry/kit.json` resolves in the
    #       template repo, so it is the provenance handle and it must stay OURS.
    #   kit_version        = a digest over the PIN'S OWN triples, recomputed AFTER the #198
    #       fork merge -> WHAT THIS PIN CARRIES. A member-side arm asserting that the pin's
    #       `kit_version` describes the pin it sits in is correct, and before this split it
    #       REDded on a pin our own tool wrote.
    #
    # Both are written, so neither question is answered by a value that belongs to the other.
    pin["source_kit_version"] = kit
    pin["kit_version"] = KM.kit_version(merged_files, merged_classes)
    pin["class_vocabulary"] = sorted(KP.CLASSES)
    # The pin's note is the PIN's, never the manifest's (#521 point 2). `note` from
    # source_state() describes the manifest; carrying it here made the pin assert that
    # `kit_version` described the manifest two lines above a value that did not.
    pin["_note"] = PIN_NOTE
    planned["pin_path"].write_text(
        json.dumps(pin, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"\npin updated — kit_version {pin['kit_version']} (this pin's own triples), "
          f"source_kit_version {pin['source_kit_version']} (the state it came from)")
    print("bytes and pin moved in one run")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", required=True, help="the factory's repo root")
    parser.add_argument("--dry-run", action="store_true",
                        help="report the plan and write nothing")
    args = parser.parse_args(argv)
    target = Path(args.to).resolve()
    if not target.is_dir():
        print(f"kit deliver: REFUSED — {target} is not a directory")
        return 1
    return deliver(target, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
