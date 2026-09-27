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


def main() -> int:
    print("kit pin — a factory's tree against the pin it vendored (plan 2646d31a step 8)")

    # ARM 1 — THE LIVE TREE. In this repo the pin IS the manifest it generates, and its own
    # copies are byte-paired, so the verdict is green over a NON-EMPTY population. That is the
    # only reason a green here means anything.
    code, lines = verdict(REPO)
    for line in lines:
        print("  " + line)
    check("the live tree is judged and green", code == 0 and "OK —" in " ".join(lines),
          lines[-1][:110])
    check("the live population is not empty — the green examined real paths",
          "judged 0 carried" not in " ".join(lines), lines[2].strip()[:90])

    live_before = {p: sha(p) for p in (REPO / "registry/kit.json", REPO / "tools/kit_pin.py")}

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

    # ARM 9 — HERMETICITY: every arm ran in a TemporaryDirectory, so our own tree is intact.
    live_after = {p: sha(p) for p in (REPO / "registry/kit.json", REPO / "tools/kit_pin.py")}
    check("our own tree was never written to", live_before == live_after,
          "manifest and predicate digests identical")

    if _failures:
        print(f"kit pin FAILED: {len(_failures)} check(s)")
        return 1
    print("kit pin passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
