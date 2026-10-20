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

import copy
import hashlib
import importlib.util
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
# A `seed`-class path the fixture carries and has edited. The transport must not write it.
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


def load_deliver():
    """The tool as a MODULE, so the currency predicate can be driven without a CLI round trip."""
    spec = importlib.util.spec_from_file_location("kit_deliver_gate", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _resolves_in_history(digest: str) -> bool:
    if not digest:
        return False
    proc = subprocess.run(["git", "log", "-S", digest, "--format=%H", "--", "registry/kit.json"],
                          cwd=str(REPO), capture_output=True, text=True)
    return proc.returncode == 0 and bool(proc.stdout.strip())

def pin_arms(pin: dict) -> tuple[bool, bool, str]:
    """The TWO #521 arms, evaluated on an arbitrary pin so each can be neutered ALONE.

    (i)  `kit_version` is a digest over THIS pin's own (path, sha256, class) triples — what
         the pin CARRIES. Recomputed here, never read back.
    (ii) `source_kit_version` is a digest this repo's HISTORY resolves — the provenance
         handle a self-digest cannot provide.

    Arm (ii) states which digest it resolved, and falls back to the HEAD manifest's digest
    ONLY in the one legitimate case: the pin was written from an UNCOMMITTED manifest, whose
    digest cannot be in history yet. Reading that as a failure would red the gate on the very
    act that will commit it. Any other unresolvable handle still reds.
    """
    sys.path.insert(0, str(REPO / "tools"))
    import kit_manifest as KM  # noqa: PLC0415

    want = KM.kit_version(pin.get("files") or {}, pin.get("classes") or {})
    self_consistent = pin.get("kit_version") == want

    src = str(pin.get("source_kit_version") or "")
    ours = str(json.loads(MANIFEST.read_text(encoding="utf-8")).get("kit_version") or "")
    if src and src == ours and not _resolves_in_history(src):
        head = subprocess.run(["git", "show", "HEAD:registry/kit.json"],
                              cwd=str(REPO), capture_output=True, text=True)
        try:
            head_version = str(json.loads(head.stdout).get("kit_version") or "")
        except (json.JSONDecodeError, AttributeError):
            head_version = ""
        return (self_consistent, _resolves_in_history(head_version),
                "the pin's handle is the UNCOMMITTED manifest's digest, so the HEAD "
                "manifest's digest was resolved instead")
    return (self_consistent, _resolves_in_history(src), "the pin's own handle")

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
        check("a `seed`-class declaration is BYTE-UNCHANGED",
              sha(root / DECLARATION[len("TEMPLATE/"):])
              == hashlib.sha256(b'{"gates": "this factory\'s own declaration"}\n').hexdigest(),
              DECLARATION)
        check("the factory's own data file is BYTE-UNCHANGED",
              sha(root / OWN_DATA) == hashlib.sha256(b"worker: a-lane\n").hexdigest(), OWN_DATA)
        check("a LOCAL FORK is skipped, not overwritten",
              sha(root / FORK[len("TEMPLATE/"):])
              == hashlib.sha256((REPO / FORK).read_bytes() + b"\n# this factory's own fork\n").hexdigest(),
              f"{FORK} still holds the factory's own bytes")

        # ARM 4 — THE PIN MOVED WITH THE BYTES, and it answers TWO questions (#521).
        pin = json.loads((root / "registry/kit.json").read_text(encoding="utf-8"))
        check("the pin records the SOURCE it was ported from (`source_kit_version`)",
              pin.get("source_kit_version") == facts["source_version"],
              f"older-kit-state -> {pin.get('source_kit_version')}")

        self_ok, src_ok, src_note = pin_arms(pin)
        check("#521 (i) the delivered pin's `kit_version` IS a digest over its own triples",
              self_ok, f"kit_version={pin.get('kit_version')}")
        check("#521 (ii) the delivered pin's `source_kit_version` RESOLVES in our history",
              src_ok, f"{pin.get('source_kit_version')} — {src_note}")
        check("the pin's `_note` is the PIN's, not the manifest's (#521 point 2)",
              bool(pin.get("_note")) and "source_kit_version" in pin["_note"]
              and pin["_note"] != json.loads(MANIFEST.read_text(encoding="utf-8")).get("_note"),
              "it describes both digests")
        check("#522 the pin declares the class vocabulary its writer knew",
              pin.get("class_vocabulary") == sorted(
                  json.loads(MANIFEST.read_text(encoding="utf-8")).get("class_vocabulary") or []),
              f"{len(pin.get('class_vocabulary') or [])} class(es)")

        # MUTATION CONTROLS — each arm must red ALONE, or it is one arm wearing two names.
        bad_self = copy.deepcopy(pin)
        bad_self["kit_version"] = "deadbeefdead"
        sc, res, _ = pin_arms(bad_self)
        check("CONTROL: a `kit_version` that is not the pin's own digest reds arm (i) ALONE",
              sc is False and res is True, "arm (i) red, arm (ii) green")
        bad_src = copy.deepcopy(pin)
        bad_src["source_kit_version"] = "0" * 12
        sc, res, _ = pin_arms(bad_src)
        check("CONTROL: a `source_kit_version` that resolves nowhere reds arm (ii) ALONE",
              sc is True and res is False, "arm (i) green, arm (ii) red")

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

        # ARM 8 — THE CURRENCY LEG (#523): two facts, two responses.
        KD = load_deliver()

        # (a) REFUSES when the declared manifest disagrees with the tree's own bytes.
        drift_root = Path(tmp) / "drifting-source"
        (drift_root / "registry").mkdir(parents=True)
        (drift_root / "registry/kit.json").write_text(
            MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
        cur = KD.currency(drift_root)
        check("#523 (a) a manifest that does not describe its tree is a REFUSAL",
              bool(cur["manifest_problem"]), (cur["manifest_problem"] or "")[:90])
        # ... and the guard is WIRED, not merely computed: drive deliver() itself.
        real_currency = KD.currency
        KD.currency = lambda *a, **k: {"manifest_problem": "synthetic disagreement",
                                       "changed": [], "missing": [], "unlisted": [],
                                       "behind": None, "behind_note": ""}
        try:
            refused = KD.deliver(root, True)
        finally:
            KD.currency = real_currency
        check("#523 (a) `deliver` REFUSES on that manifest and writes nothing",
              refused == 1, f"rc={refused}")

        # (b) WARNS on a tree behind its remote, and NEVER fails on it.
        KD.currency = lambda *a, **k: {"manifest_problem": None, "changed": [], "missing": [],
                                       "unlisted": [], "behind": 5, "behind_note": ""}
        try:
            warned = KD.deliver(root, True)
        finally:
            KD.currency = real_currency
        check("#523 (b) a tree BEHIND its remote is a WARNING, never a refusal",
              warned == 0, f"rc={warned} behind=5")

        # (b) DEGRADES: no readable origin/main reports UNKNOWN rather than zero.
        plain = Path(tmp) / "no-remote"
        plain.mkdir()
        distance, note = KD._behind(plain)
        check("#523 (b) with no origin/main the distance reads UNKNOWN, never 0",
              distance is None and note == KD.CURRENCY_UNKNOWN, note)

        # (b) MEASURED on a real git tree: one commit behind its own origin/main.
        ahead = Path(tmp) / "behind-by-one"
        ahead.mkdir()
        git = ["git", "-C", str(ahead), "-c", "user.email=gate@example.invalid",
               "-c", "user.name=gate"]
        subprocess.run(git + ["init", "-q"], check=True, capture_output=True)
        (ahead / "f.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(git + ["add", "f.txt"], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-qm", "one"], check=True, capture_output=True)
        (ahead / "f.txt").write_text("two\n", encoding="utf-8")
        subprocess.run(git + ["commit", "-qam", "two"], check=True, capture_output=True)
        subprocess.run(git + ["update-ref", "refs/remotes/origin/main", "HEAD"],
                       check=True, capture_output=True)
        subprocess.run(git + ["reset", "-q", "--hard", "HEAD~1"], check=True, capture_output=True)
        distance, note = KD._behind(ahead)
        check("#523 (b) a tree one commit behind origin/main measures EXACTLY 1",
              distance == 1 and note == "", f"distance={distance} note={note!r}")

        # And our own source state is the control the leg can PASS on.
        cur = KD.currency()
        check("#523 control: OUR OWN manifest is honest, so the leg is a guard and not a "
              "standing red (regenerate with tools/kit_manifest.py if this reds)",
              cur["manifest_problem"] is None,
              (cur["manifest_problem"] or "in agreement")[:90])

    # ARM 9 — HERMETICITY: nothing above touched our own tree.
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
