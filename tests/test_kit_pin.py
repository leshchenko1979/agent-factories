#!/usr/bin/env python3
"""Gate: a factory's tree against the pin it VENDORED — the member-side half of drift.

WHY THIS GATE EXISTS. The kit could tell a factory it had drifted and had no way for the
factory to judge itself: `registry/kit.json` is the manifest this repo GENERATES, and a gate
against it would make a member's verdict a function of OUR working tree and OUR backlog — our
movement would redden their audit for a change they never took. So a factory VENDORS the pin
(the vehicle `TEMPLATE/registry/kit.example.json`, copied to its own `registry/kit.json` at
port time) and this gate compares the tree against THAT. Its verdict moves only when the
factory's tree diverges from the factory's own declaration, which is the only thing it can
act on.

THE TWO POPULATION RULES, both load-bearing and both printed:
  ABSENT is not a verdict. A factory ports a SUBSET of the kit, so a fresh factory is ~104
  ABSENT cells over the whole manifest; reddening on those would punish exactly the behaviour
  the port rule asks for. A path the factory never took cannot diverge from anything.
  `seed`-CLASS paths are not judged. Those are seeds the factory owns — its README, its
  `gates.json`, its exemption lists — and the class means "never compared byte-for-byte,
  because the factory's copy legitimately differs". They are COUNTED rather than dropped, so
  the exclusion is visible: an exclusion nobody can see is the silent-exclusion shape this
  kit's law refuses.

WHAT IT CANNOT DO, stated so its green is not over-read. It cannot tell whether the factory
ported the right SET — only whether what it carries matches what it declared. A factory that
vendored a pin and ported nothing reads as GREEN over an empty judged population, which is
why that case is a REFUSAL here rather than a pass.

Run:  python3 tests/test_kit_pin.py
Exit: 0 green, or a stated SKIP when this tree carries no pin; 1 a divergence, a broken pin,
      or a vacuous population.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

try:
    import kit_pin as KP
except ImportError as exc:  # a factory that ported this gate without its closure
    print(f"kit pin: FAILED — {REPO}/tools/kit_pin.py could not be imported: {exc}")
    print("  tools/kit_pin.py is class `closure` in the pin, so it travels WITH this gate;")
    print("  a gate that cannot read a pin cannot judge one.")
    sys.exit(1)

# The specimen the fixture carries and then mutates. Shipped, classed `closure`, so it is
# inside the JUDGED population — the arm would prove nothing on a factory-class path.
SPECIMEN = "TEMPLATE/tools/field_predicate.py"
# A factory-class path whose bytes differ from the pin BY DESIGN. The arm that keeps the
# class rule from regressing: this must NOT be reported as a divergence.
OWNED = "TEMPLATE/README.md"
# The delivery leg, for the #198 arms below. Repo-side only: a member tree that ported
# this gate carries no `tools/kit_deliver.py`, so those arms are gated on its presence.
DELIVER = REPO / "tools/kit_deliver.py"
STALE_REL = "TEMPLATE/tools/kit_pin.py"   # shipped, class `closure`

# The fixture arms below build a specimen tree by copying TEMPLATE/-only paths. Those exist
# ONLY in the repository that SHIPS the template: a member tree that ported this gate carries
# no TEMPLATE/ at all, so the arms cannot run there -- and a crash is not a verdict. The live
# arm above is this gate's verdict in a member tree; the fixture arms are this repo's
# test-of-the-test, and they are named here by the exact inputs they depend on.
FIXTURE_INPUTS = (REPO / "TEMPLATE/registry/kit.example.json", REPO / SPECIMEN)
TEMPLATE_PRESENT = all(p.is_file() for p in FIXTURE_INPUTS)

_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verdict(root: Path) -> tuple[int, list[str]]:
    """The gate's judgement of ONE tree: `(exit code, lines to print)`.

    A function rather than a straight-line `main` so the arms drive THE REAL CODE PATH
    against fixtures instead of re-implementing the rules they are meant to test — the
    re-implementation is how a gate comes to pass while the thing it guards is broken.
    """
    pin_path = root / KP.PIN_REL
    if not pin_path.is_file():
        return 0, [
            f"kit pin: SKIPPED — this tree carries no {KP.PIN_REL}, so there is no declaration "
            f"to judge it against.",
            f"  A factory that never vendored the pin lands here. Vendor it by copying "
            f"TEMPLATE/registry/kit.example.json to {KP.PIN_REL} at the moment you port kit "
            f"files — until then nothing in this tree claims to be a port of anything.",
        ]

    pin, problem = KP.load_pin(pin_path)
    if pin is None:
        return 1, [
            f"kit pin: FAILED — {KP.PIN_REL} exists but could not be used: {problem}",
            "  A pin that cannot be read is not an empty reference: an empty reference agrees "
            "with every tree, so degrading to one would turn a broken pin into a permanent green.",
        ]

    exempt_path = root / KP.EXEMPTIONS_REL
    if exempt_path.is_file():
        data, exempt_problem = KP.load_exemptions(root)
        if data is None:
            return 1, [
                f"kit pin: FAILED — {KP.EXEMPTIONS_REL} exists but could not be read: "
                f"{exempt_problem}",
                "  A malformed exemption surface is a failure, never an empty one: reading it "
                "as empty would silently drop the factory's own declared forks back into the "
                "judged population.",
            ]

    found = KP.undeclared_divergence(pin, root)
    lines = [
        f"kit pin — {root}",
        f"  pin {KP.PIN_REL}: version {found['pin_version']}, {len(pin.get('files') or {})} path(s) declared",
        f"  judged {found['carried']} carried path(s); {found['skipped_class']} factory-class "
        f"path(s) excluded by class; {found['declared']} declared exempt",
    ]

    if found["carried"] == 0:
        return 1, lines + [
            "FAIL — the pin declares paths and this tree carries NONE of the judged population, "
            "so the comparison examined nothing.",
            "  That is the vacuous pass this guard refuses: a green over an empty population "
            "reads identically to a green over a clean one.",
        ]

    if found["diverging"]:
        lines.append("FAIL — carried paths that diverge from YOUR OWN pin and are not declared exempt:")
        for d in found["diverging"]:
            lines.append(f"  {d['path']}  class={d['class']}  pin={d['pin_sha']} tree={d['tree_sha']}")
        lines.append(
            "  Two lawful answers, and the choice is the factory's: take the update "
            f"(python3 tools/kit_deliver.py --to . --dry-run), or declare the fork in "
            f"{KP.EXEMPTIONS_REL} with a reason."
        )
        return 1, lines

    lines.append(f"  OK — every carried path matches the pin ({found['pin_version']})")
    return 0, lines


def build_fixture(root: Path) -> dict:
    """A factory that ported a few files and vendored the pin. Returns the facts to assert on."""
    manifest = json.loads((REPO / "registry/kit.json").read_text(encoding="utf-8"))
    pin = json.loads((REPO / "TEMPLATE/registry/kit.example.json").read_text(encoding="utf-8"))
    (root / "registry").mkdir(parents=True, exist_ok=True)
    (root / "registry/kit.json").write_text(
        json.dumps(pin, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Two JUDGED paths, carried at exactly the pin's bytes.
    carried = [SPECIMEN, "TEMPLATE/tools/kit_pin.py"]
    for rel in carried:
        dst = root / KP.member_path(rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((REPO / rel).read_bytes())

    # One FACTORY-CLASS path, deliberately DIFFERENT: a factory's own document.
    owned = root / KP.member_path(OWNED)
    owned.parent.mkdir(parents=True, exist_ok=True)
    owned.write_bytes(b"# this factory's own README\n\nNothing like the template's.\n")

    return {
        "pin_version": str(manifest.get("kit_version")),
        "carried": carried,
        "owned": owned,
        "specimen_local": KP.member_path(SPECIMEN),
    }


def build_deliver_fixture(root: Path, *, fork: bool) -> dict:
    """A factory one kit state behind, optionally carrying a FORK the deliver must skip.

    The fork's bytes differ from BOTH its pin entry and the delivered bytes, so the plan's
    verdict is LOCAL-MODIFICATION -- the shape #198 is about.
    """
    pin = json.loads((REPO / "TEMPLATE/registry/kit.example.json").read_text(encoding="utf-8"))
    stale_bytes = (REPO / STALE_REL).read_bytes() + b"\n# an older kit state\n"
    pin["files"][STALE_REL] = hashlib.sha256(stale_bytes).hexdigest()
    pin["kit_version"] = "older-kit-state"
    (root / "registry").mkdir(parents=True, exist_ok=True)
    (root / "registry/kit.json").write_text(
        json.dumps(pin, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    (root / KP.member_path(STALE_REL)).parent.mkdir(parents=True, exist_ok=True)
    (root / KP.member_path(STALE_REL)).write_bytes(stale_bytes)

    fork_local = None
    if fork:
        fork_local = KP.member_path(SPECIMEN)
        (root / fork_local).parent.mkdir(parents=True, exist_ok=True)
        (root / fork_local).write_bytes((REPO / SPECIMEN).read_bytes() + b"\n# this factory's own fork\n")
        # The pin still declares OUR bytes for that path, which is what makes it a fork.
    return {"fork_local": fork_local,
            "source_version": str(json.loads((REPO / "registry/kit.json").read_text())["kit_version"]),
            "source_stale_digest": json.loads((REPO / "registry/kit.json").read_text())["files"][STALE_REL]}


def shared_tree_dirty() -> set[str]:
    """Member paths whose WORKING-TREE bytes differ from the manifest digest.

    The deliver writes WORKING-TREE bytes for an `ADD` and records the MANIFEST digest, so in
    a shared tree carrying peer-dirty shipped files those two disagree for a reason that has
    nothing to do with #198. Excluded BY NAME rather than silently: a check that cannot say
    why it is red is a check nobody can act on.
    """
    manifest = json.loads((REPO / "registry/kit.json").read_text(encoding="utf-8"))["files"]
    out = set()
    for rel, want in manifest.items():
        p = REPO / KP.member_path(rel)
        if p.is_file() and sha(p) != want:
            out.add(KP.member_path(rel))
    return out


def drive_deliver(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(DELIVER), "--to", str(root)],
                          cwd=str(REPO), capture_output=True, text=True)


def main() -> int:
    print("kit pin — a factory's tree against the pin it vendored (plan 2646d31a step 8)")

    # ARM 1 — THE LIVE TREE. In this repo the pin IS the manifest it generates, and its own
    # copies are byte-paired, so the verdict is green over a NON-EMPTY population. That is the
    # only reason a green here means anything.
    code, lines = verdict(REPO)
    for line in lines:
        print("  " + line)
    # TWO SHAPES, and the shipped tree takes the second. `TEMPLATE/registry/` carries
    # `kit.example.json` and NOT `registry/kit.json`, so this gate SKIPS in the tree the kit
    # ships from -- the correct verdict, since a tree that never vendored a pin has nothing
    # to be judged against. Indexing the population line unconditionally crashed there
    # (IndexError on a 2-line skip), which is a crash rather than a verdict.
    if (REPO / KP.PIN_REL).is_file():
        check("the live tree is judged and green", code == 0 and "OK —" in " ".join(lines),
              lines[-1][:110])
        check("the live population is not empty — the green examined real paths",
              "judged 0 carried" not in " ".join(lines), lines[2].strip()[:90])
    else:
        check("the live tree SKIPS and names the absence — no pin is vendored here",
              code == 0 and "SKIPPED" in " ".join(lines) and KP.PIN_REL in " ".join(lines),
              lines[0][:110])

    # The shipped tree carries NO `registry/kit.json` (only the `.example` vehicle), so the
    # hermeticity set is built from what is actually here. Reading a path that does not exist
    # raised FileNotFoundError and made this gate CRASH in the very tree it ships from.
    hermetic_inputs = [p for p in (REPO / KP.PIN_REL, REPO / "tools/kit_pin.py") if p.is_file()]
    live_before = {p: sha(p) for p in hermetic_inputs}

    if not TEMPLATE_PRESENT:
        print("  SKIPPED  the fixture arms — their inputs are TEMPLATE/-only and this tree")
        print("           carries none of them. The live arm above is this gate's verdict here.")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "factory"
            facts = build_fixture(root)

            # ARM 2 — CONTROL: the fixture is green, and its factory-class path was EXCLUDED
            # rather than silently judged. Without the control the arms below cannot tell a
            # working predicate from one that reds on everything.
            code, lines = verdict(root)
            joined = " ".join(lines)
            check("CONTROL: a fixture factory at its pin's bytes is GREEN", code == 0, lines[-1][:110])
            # The strong form: the fixture's factory-class path DIFFERS from the pin, and the
            # verdict is green anyway BECAUSE it was excluded. Asserting the count alone would
            # pass on a predicate that never examined the path for a different reason.
            check("a `seed`-class path that DIFFERS is excluded by class, not reported",
                  code == 0 and "1 factory-class path(s) excluded" in joined
                  and "README.md" not in joined,
                  [ln.strip() for ln in lines if "factory-class" in ln][:1])
            check("that exclusion is COUNTED, not silent", "1 factory-class path(s) excluded" in joined,
                  "the class exclusion is printed")

            # ARM 3 — THE MUTATION CONTROL. One carried path moves off its pin's bytes.
            sp = root / facts["specimen_local"]
            sp.write_bytes(sp.read_bytes() + b"\n# a local edit nobody declared\n")
            code, lines = verdict(root)
            joined = " ".join(lines)
            check("MUTATION CONTROL: a carried path off its pin's bytes goes RED, naming it",
                  code == 1 and facts["specimen_local"] in joined and "FAIL —" in joined,
                  [ln.strip() for ln in lines if "FAIL —" in ln][:1])

            # ARM 4 — THE EXEMPTION SURFACE. The same mutation, now DECLARED, is green again —
            # which is what makes ARM 3 a finding about the declaration rather than about bytes.
            (root / KP.EXEMPTIONS_REL).write_text(
                json.dumps({"exempt": [{"path": facts["specimen_local"],
                                        "reason": "this factory's own event set"}]}, indent=2) + "\n",
                encoding="utf-8")
            code, lines = verdict(root)
            check("the same divergence DECLARED exempt is GREEN again",
                  code == 0 and "1 declared exempt" in " ".join(lines),
                  "the fork is a declaration, not a source edit")

            # ARM 5 — A MALFORMED EXEMPTION SURFACE is a failure, never an empty one.
            (root / KP.EXEMPTIONS_REL).write_text("{not json", encoding="utf-8")
            code, lines = verdict(root)
            check("a malformed exemption surface FAILS rather than reading as empty",
                  code == 1 and "could not be read" in " ".join(lines), lines[0][:110])
            (root / KP.EXEMPTIONS_REL).unlink()

            # ARM 6 — AN ABSENT PIN SKIPS AND NAMES THE ABSENCE, rather than reading clean.
            (root / KP.PIN_REL).unlink()
            code, lines = verdict(root)
            joined = " ".join(lines)
            check("an absent pin SKIPS with its reason named",
                  code == 0 and "SKIPPED" in joined and KP.PIN_REL in joined
                  and "never vendored the pin" in joined,
                  lines[0][:110])

            # ARM 7 — A PIN PRESENT BUT NOTHING CARRIED is a REFUSAL, not a vacuous green.
            (root / KP.PIN_REL).write_text(
                json.dumps(json.loads((REPO / "TEMPLATE/registry/kit.example.json").read_text()),
                           indent=2, sort_keys=True) + "\n", encoding="utf-8")
            for rel in facts["carried"]:
                (root / KP.member_path(rel)).unlink()
            facts["owned"].unlink()
            code, lines = verdict(root)
            check("a pin with NOTHING carried is REFUSED as vacuous, not passed",
                  code == 1 and "examined nothing" in " ".join(lines), lines[-1][:110])

            # ARM 8 — A MALFORMED PIN is a failure, never an empty reference.
            (root / KP.PIN_REL).write_text("{broken", encoding="utf-8")
            code, lines = verdict(root)
            check("a malformed pin FAILS rather than comparing against nothing",
                  code == 1 and "could not be used" in " ".join(lines), lines[0][:110])

        # ARMS 10-12 — #198: THE PIN CARRIES THE MEMBER'S OWN DIGEST FOR A SKIPPED FORK.
        # The deliver refuses to write a forked path, so a pin claiming OUR digest for it
        # would red the member's gate on a state the deliver itself created.
        if not DELIVER.is_file():
            print("  SKIPPED  the #198 deliver arms — tools/kit_deliver.py is repo-side only,")
            print("           so a member tree that ported this gate carries none of it.")
        else:
            with tempfile.TemporaryDirectory() as tmp2:
                d = Path(tmp2) / "forked"
                d.mkdir(parents=True)
                f = build_deliver_fixture(d, fork=True)

                # ARM 10 — THE NEGATIVE CONTROL, and it comes FIRST: a fork with NO deliver
                # run must still RED. If this passed, the arms below would prove nothing.
                code, lines = verdict(d)
                check("NEGATIVE CONTROL: a forked path with NO deliver run still REDS",
                      code == 1 and f["fork_local"] in " ".join(lines),
                      [ln.strip() for ln in lines if "FAIL —" in ln][:1])

                # ARM 11 — THE DELIVERY. Criterion 1: rc=0 after, and the pin entry equals
                # the TREE's digest for every skipped path.
                r = drive_deliver(d)
                check("the deliver exits 0 over a tree carrying a declared fork",
                      r.returncode == 0, (r.stdout or r.stderr or "").strip().splitlines()[-1:])
                pin_after = json.loads((d / KP.PIN_REL).read_text(encoding="utf-8"))
                tree_digest = sha(d / f["fork_local"])
                check("the pin claims the TREE's digest for the SKIPPED fork, not ours",
                      pin_after["files"].get(SPECIMEN) == tree_digest,
                      f"pin={str(pin_after['files'].get(SPECIMEN))[:12]} tree={tree_digest[:12]}")
                _, pin_now, _ = KP.vendored_pin_in(d)
                left = sorted(x["path"] for x in (KP.undeclared_divergence(pin_now, d).get("diverging") or []))
                # The CRITERION's subject is the forked path: a pin claiming bytes this run
                # deliberately did not write would red the member's gate on OUR state. Any
                # other residue belongs to this shared tree (a peer-dirty shipped file the
                # deliver copied while pinning the manifest's digest) and is named, not hidden.
                check("the member's own gate is GREEN after the deliver (#198 criterion 1)",
                      f["fork_local"] not in left,
                      f"fork diverging={f['fork_local'] in left}; other residue in this shared "
                      f"tree: {[p for p in left if p != f['fork_local']]}")
                # The fork stays VISIBLE where it can be acted on: the pin and OUR manifest
                # now disagree about that path, which is what the patrol reads.
                ours = json.loads((REPO / "registry/kit.json").read_text())["files"]
                check("the fork stays VISIBLE — the pin still differs from OUR manifest",
                      pin_after["files"].get(SPECIMEN) != ours.get(SPECIMEN),
                      "the patrol's comparison is the surface that sees it")

            with tempfile.TemporaryDirectory() as tmp3:
                n = Path(tmp3) / "clean"
                n.mkdir(parents=True)
                g = build_deliver_fixture(n, fork=False)
                r = drive_deliver(n)
                pin_after = json.loads((n / KP.PIN_REL).read_text(encoding="utf-8"))
                # ARM 12 — Criterion 2: a tree with NO fork still TAKES the new pin version
                # and stays green. Without this half the fix could freeze the pin for members
                # that took the update.
                check("a tree with NO fork still RECEIVES the new pin version",
                      r.returncode == 0 and pin_after.get("kit_version") == g["source_version"],
                      f"older-kit-state -> {pin_after.get('kit_version')}")
                _, pin_n, _ = KP.vendored_pin_in(n)
                left = sorted(x["path"] for x in (KP.undeclared_divergence(pin_n, n).get("diverging") or []))
                # Criterion 2's subject is that the fix must NOT freeze the pin for a member
                # that took the update. The deliver WROTE every carried path here, so the pin
                # and the tree agree except where this shared tree's working bytes moved under
                # the run — named beside the verdict rather than folded into it.
                check("that no-fork tree is GREEN after the deliver (#198 criterion 2)",
                      set(left) <= shared_tree_dirty(),
                      f"diverging={left} (residue is this shared tree's dirty shipped "
                      f"file(s): {sorted(shared_tree_dirty())})")

    # ARM 9 — HERMETICITY: every arm ran in a TemporaryDirectory, so our own tree is intact.
    live_after = {p: sha(p) for p in hermetic_inputs}
    check("our own tree was never written to", live_before == live_after,
          "manifest and predicate digests identical")

    if _failures:
        print(f"kit pin FAILED: {len(_failures)} check(s)")
        return 1
    print("kit pin passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
