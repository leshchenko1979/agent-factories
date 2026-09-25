#!/usr/bin/env python3
"""Gate: the delivery leg hands a factory an update as ONE unit, and never touches its own.

WHY THIS GATE EXISTS. Measured 2026-09-25: the kit could tell a factory it had drifted and
had no mechanism to hand it the update (law corpus `vendor` 0, `re-sync` 0, `propagat` 0-1).
A transport that ships without a gate is the class this repo refuses — a mechanism whose
only evidence is the author's word.

WHAT IT PROVES, and the arm that makes each half mean something:
  - a factory at an older kit state RECEIVES the update (its outdated file becomes the
    delivered bytes)
  - its own gate is GREEN after, and a NEGATIVE CONTROL shows that same gate REDS on the
    state a NON-atomic update would create (bytes moved, pin not) — so "green after" is a
    measurement rather than a property the gate could never fail
  - its declaration files are BYTE-UNCHANGED, checked with a digest rather than by eye
  - a local fork is SKIPPED rather than overwritten, and the file's bytes prove it
  - `--dry-run` writes nothing at all

HERMETICITY. Every arm runs inside a TemporaryDirectory. Our own tree's digests are
compared before and after, so "the live tree was not touched" is measured, not asserted.

Run:  python3 tests/test_kit_deliver.py
Exit: 0 all arms hold; 1 a check failed; 0 with a stated SKIP when this tree has no kit.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KIT_ROOT = REPO / "TEMPLATE"
MANIFEST = REPO / "registry/kit.json"
TOOL = REPO / "tools/kit_deliver.py"

# The specimen the fixture holds at OLDER bytes. Small, shipped, and classed `closure`, so
# it is in the delivered population.
STALE = "TEMPLATE/tools/kit_pin.py"
# A file the fixture has forked: it differs from BOTH its pin and the delivered bytes.
FORK = "TEMPLATE/tools/field_predicate.py"
# A `factory`-class path the fixture carries and has edited. The transport must not write it.
DECLARATION = "TEMPLATE/registry/gates.example.json"
# The factory's own data, in no manifest at all.
OWN_DATA = "tools/actors.txt"

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_fixture(root: Path) -> dict:
    """A factory at an OLDER kit state. Returns the facts the arms assert against."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source_files: dict[str, str] = manifest["files"]

    # The pin: the shipped vehicle, moved back one state -- the stale file's digest becomes
    # the OLD bytes' digest, and the version is not the source's.
    pin = json.loads((KIT_ROOT / "registry/kit.example.json").read_text(encoding="utf-8"))
    stale_bytes = (REPO / STALE).read_bytes() + b"\n# an older kit state\n"
    fork_bytes = (REPO / FORK).read_bytes() + b"\n# this factory's own fork\n"
    decl_bytes = b'{"gates": "this factory\'s own declaration"}\n'

    pin["files"][STALE] = hashlib.sha256(stale_bytes).hexdigest()
    pin["kit_version"] = "older-kit-state"
    (root / "registry").mkdir(parents=True, exist_ok=True)
    (root / "registry/kit.json").write_text(
        json.dumps(pin, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    for rel, body in ((STALE, stale_bytes), (FORK, fork_bytes), (DECLARATION, decl_bytes)):
        dst = root / rel[len("TEMPLATE/"):]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(body)
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / OWN_DATA).write_bytes(b"worker: a-lane\n")

    # The factory DECLARES its forks -- that is the designed path, and without it its own
    # gate would red on the declaration file too, which is correct behaviour, not a defect.
    (root / "registry/kit-exemptions.json").write_text(
        json.dumps({"exempt": [{"path": FORK[len("TEMPLATE/"):]},
                               {"path": DECLARATION[len("TEMPLATE/"):]}]},
                   indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "source_files": source_files,
        "source_version": str(manifest.get("kit_version")),
        "stale_bytes": stale_bytes,
        "stale_digest": hashlib.sha256(stale_bytes).hexdigest(),
        "stale_source_digest": source_files[STALE],
    }


def run_tool(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), "--to", str(root), *args],
                          cwd=str(REPO), capture_output=True, text=True)


def own_gate(root: Path) -> dict:
    """The factory's OWN verdict: its tree against its pin, forks declared."""
    sys.path.insert(0, str(REPO / "tools"))
    import kit_pin as KP  # noqa: PLC0415

    _, pin, problem = KP.vendored_pin_in(root)
    if pin is None:
        return {"error": problem}
    return KP.undeclared_divergence(pin, root)


def main() -> int:
    print("kit deliver — a factory receives an update as one unit (plan 2646d31a step 7)")

    if not KIT_ROOT.is_dir():
        print("kit deliver: SKIPPED — this tree carries no TEMPLATE/, so there is no kit "
              "to deliver. A bootstrapped factory lands here.")
        return 0

    live_before = {p: sha(p) for p in (MANIFEST, TOOL, REPO / STALE)}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "factory"
        facts = build_fixture(root)

        # ARM 1 — DRY RUN writes nothing at all.
        r = run_tool(root, "--dry-run")
        check("dry run exits 0 and reports the plan",
              r.returncode == 0 and "dry run" in r.stdout, r.stdout.strip().splitlines()[:1])
        check("dry run left the stale file at its OLD bytes",
              sha(root / STALE[len("TEMPLATE/"):]) == facts["stale_digest"], "unchanged")

        # ARM 2 — THE DELIVERY. The stale file becomes the delivered bytes.
        r = run_tool(root)
        check("delivery exits 0", r.returncode == 0, r.stdout.strip().splitlines()[:1])
        check("the factory RECEIVED the update: the stale file now matches the source",
              sha(root / STALE[len("TEMPLATE/"):]) == facts["stale_source_digest"],
              f"{STALE} == delivered bytes")

        # ARM 3 — DECLARATIONS AND FORKS ARE UNTOUCHED. Digests, not eyeballs.
        check("a `factory`-class declaration is BYTE-UNCHANGED",
              sha(root / DECLARATION[len("TEMPLATE/"):])
              == hashlib.sha256(b'{"gates": "this factory\'s own declaration"}\n').hexdigest(),
              DECLARATION)
        check("the factory's own data file is BYTE-UNCHANGED",
              sha(root / OWN_DATA) == hashlib.sha256(b"worker: a-lane\n").hexdigest(), OWN_DATA)
        check("a LOCAL FORK is skipped, not overwritten",
              sha(root / FORK[len("TEMPLATE/"):])
              == hashlib.sha256((REPO / FORK).read_bytes() + b"\n# this factory's own fork\n").hexdigest(),
              f"{FORK} still holds the factory's own bytes")

        # ARM 4 — THE PIN MOVED WITH THE BYTES, which is what makes the next arm green.
        pin = json.loads((root / "registry/kit.json").read_text(encoding="utf-8"))
        check("the pin moved to the delivered kit version",
              pin.get("kit_version") == facts["source_version"],
              f"older-kit-state -> {pin.get('kit_version')}")

        # ARM 5 — THE FACTORY'S OWN GATE IS GREEN, and it JUDGED something.
        verdict = own_gate(root)
        check("the factory's own gate is GREEN after the update",
              verdict.get("diverging") == [], f"carried {verdict.get('carried')} path(s)")
        check("that gate is not vacuous — it examined the paths the factory carries",
              (verdict.get("carried") or 0) >= 3, f"carried={verdict.get('carried')}")

        # ARM 6 — NEGATIVE CONTROL: the state a NON-ATOMIC update leaves. Revert the pin's
        # entry for the delivered file (bytes moved, pin did not) and the SAME gate must red.
        pin["files"][STALE] = facts["stale_digest"]
        (root / "registry/kit.json").write_text(
            json.dumps(pin, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verdict = own_gate(root)
        named = [d["path"] for d in (verdict.get("diverging") or [])]
        check("NEGATIVE CONTROL: bytes-moved-pin-not REDS that same gate, naming the file",
              STALE[len("TEMPLATE/"):] in named, f"diverging={named}")

    # ARM 7 — HERMETICITY: nothing above touched our own tree.
    live_after = {p: sha(p) for p in (MANIFEST, TOOL, REPO / STALE)}
    check("our own tree was never written to", live_before == live_after,
          "manifest, tool and specimen digests identical")

    if _failures:
        print(f"kit deliver FAILED: {len(_failures)} check(s)")
        return 1
    print("kit deliver passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
