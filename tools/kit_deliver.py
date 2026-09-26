#!/usr/bin/env python3
"""The delivery leg: hand a factory an update as ONE unit, and never touch its own files.

WHY THIS EXISTS. Measured 2026-09-25 over five member factories: 1 same / 20 DIFF / 29
ABSENT across the ten bootstrap-named files, with `tools/gate_budget.py` and both
`tools/hooks/` refusal points absent from ALL FIVE. The kit could tell a factory it had
drifted and had no mechanism to hand it the update — the law corpus carried `vendor` 0,
`re-sync` 0, `propagat` 0-1, and `registry/kit.json` is a manifest, not a channel.

WHAT IT MOVES, AND WHY THOSE CLASSES. The `classes` map in the pin decides:
`standalone` and `closure` are delivered (a tool and the modules it needs to run);
`seed` is NEVER written, because those are the factory's own law and data — its
`SKILL.md`, its `gates.json`, its exemption lists. An update that overwrote a declaration
would destroy the thing the declaration exists to record.

WHY A LOCAL MODIFICATION IS SKIPPED, NOT OVERWRITTEN. A file whose bytes differ from the
member's OWN pin is the member's deliberate work. Overwriting it would silently discard a
fork; skipping it leaves the pin claiming the new state, so the member's own gate reds
until they either take the update or declare the fork. The gate says so; the transport
does not decide for them.

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
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import kit_manifest as KM  # noqa: E402
import kit_pin as KP  # noqa: E402

# The classes an update may write. `seed` is absent on purpose -- see the docstring.
DELIVERED_CLASSES = ("standalone", "closure")

# What the plan says about each path. `seed` and `LOCAL-MODIFICATION` are both refusals
# to write, but they are DIFFERENT facts and a reader must be able to tell them apart.
WRITTEN = ("ADD", "UPDATE")


def source_state() -> tuple[dict, dict, dict, str]:
    """Our own manifest: (files, classes, kit_version, note)."""
    declared = json.loads(KM.MANIFEST.read_text(encoding="utf-8"))
    return (
        declared.get("files") or {},
        declared.get("classes") or {},
        str(declared.get("kit_version") or ""),
        str(declared.get("_note") or ""),
    )


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
        rows.append({"rel": rel, "local": local, "verdict": verdict, "cls": cls, "why": why})
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
    for rel in planned["retired"]:
        merged_files[rel] = (pin.get("files") or {})[rel]
        merged_classes[rel] = (pin.get("classes") or {}).get(rel, "seed")
    pin["files"] = merged_files
    pin["classes"] = merged_classes
    pin["file_count"] = len(merged_files)
    pin["kit_version"] = kit
    if note:
        pin["_note"] = note
    planned["pin_path"].write_text(
        json.dumps(pin, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"\npin updated to {kit} — bytes and pin moved in one run")
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
