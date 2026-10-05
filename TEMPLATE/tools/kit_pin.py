"""The kit pin: what a factory vendored, and the ONE predicate that compares a tree to it.

A FACTORY VENDORS the kit manifest rather than reading ours. `registry/kit.json` in this
repo is the shipped kit's state today; a copy of it in a factory's own tree is that
factory's PIN — the record of which kit state it ported. The difference is not
bookkeeping, it is the direction a verdict may point:

  gate against OURS   a member's audit goes red when WE move, so a member's verdict is a
                      function of this repo's working tree and of our backlog
  gate against a PIN  a member's audit goes red when ITS tree diverges from ITS declaration,
                      which is the only thing that member can act on

So the pin is the load-bearing choice in the design, and this module is its reader.

ONE PREDICATE, TWO CALLERS. The comparison is the same operation in both directions —
"digest these paths in this tree against this reference" — and only the reference differs:
our patrol leg compares each member against OUR manifest, and a factory's own gate compares
its tree against its pin. Two implementations of one comparison would be the class
`tools/field_predicate.py` exists to prevent, so `compare()` here is the only home and
`tools/patrol_host_state.py`'s kit-drift leg imports it rather than keeping its own loop.

THE `TEMPLATE/` PREFIX RULE LIVES HERE TOO. A manifest path is `TEMPLATE/tools/x.py`
because that is how the template is STORED here; in a factory's tree the same file is
`tools/x.py`. The prefix is an artefact of our storage, never part of what a factory
carries, and a rule that two callers implement differently would make our report and theirs
disagree about the same bytes.

WHY THE CLASSES RIDE IN THE PIN. A factory porting `tools/ledger.py` must bring six
modules with it, and must NOT overwrite its own `tools/actors.txt`. That is a per-file
property of the kit, and the only surface carrying it is the `classes` map — so a pin
without classes would leave a factory unable to apply the port rule it was told to follow.

WHY THE PIN VEHICLE IS NOT AN ENTRY. The pin ships as
`TEMPLATE/registry/kit.example.json`, and that path is EXCLUDED from the manifest it
renders. A file whose content is a rendering of the manifest cannot also be a key in it:
its digest would have to be computed from bytes that contain its own digest, which has no
fixpoint. `registry/kit.json` itself is excluded for the same kind of reason (it is
generated factory data, not shipped kit), so the exception is principled and it is not the
"forgot to list it" case the generator's completeness rule exists to refuse — see
`tools/kit_manifest.py`, which names this file in its own exclusion set with that reason.

Run:  imported by tests/test_kit_pin_ship.py and by tools/patrol_host_state.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Where a factory's vendored copy lives, relative to ITS repo root.
PIN_REL = "registry/kit.json"

# The path the pin is shipped at inside the template. Excluded from the manifest it
# renders -- see the module docstring, "WHY THE PIN VEHICLE IS NOT AN ENTRY".
PIN_VEHICLE_REL = "TEMPLATE/registry/kit.example.json"

TEMPLATE_PREFIX = "TEMPLATE/"

CLASSES = ("standalone", "closure", "seed")


def member_path(manifest_path: str) -> str:
    """A manifest path -> the path that file occupies in a factory's tree.

    `TEMPLATE/tools/x.py` -> `tools/x.py`. A path with no prefix is returned unchanged,
    because the manifest carries a few repo-root entries (docs, methodology) that a
    factory keeps at the same path.
    """
    p = str(manifest_path)
    return p[len(TEMPLATE_PREFIX):] if p.startswith(TEMPLATE_PREFIX) else p


def sha256_of(path: Path) -> str:
    """Digest of a file's bytes, streamed. Never `read()` a large shipped file into a list."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_pin(path: Path) -> tuple[dict | None, str | None]:
    """Read a pin. Returns `(pin, None)` or `(None, problem)`.

    A pin that cannot be read is a PROBLEM, never an empty reference: an empty `files` map
    agrees with every tree, so silently degrading to one would turn a broken pin into a
    permanent green. The shape checks are the same ones the generator's `--check` applies to
    our own manifest, so a hand-edited pin fails here rather than comparing against nothing.
    """
    if not path.is_file():
        return None, f"the pin {path} is absent — nothing to compare against"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"the pin {path} could not be read: {exc}"
    try:
        pin = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"the pin {path} is not valid JSON: {exc}"
    if not isinstance(pin, dict):
        return None, f"the pin {path} is a {type(pin).__name__}, not an object"
    files = pin.get("files")
    if not isinstance(files, dict) or not files:
        return None, (
            f"the pin {path} declares NO files — an empty reference agrees with every tree, "
            f"which is the vacuous-pass shape this reader refuses"
        )
    classes = pin.get("classes")
    if not isinstance(classes, dict) or not classes:
        return None, (
            f"the pin {path} carries no `classes` map — a factory that cannot read which "
            f"files are closure cannot apply the port rule it was told to follow"
        )
    missing = [p for p in files if p not in classes]
    if missing:
        return None, (
            f"the pin {path} carries {len(missing)} path(s) with no class "
            f"(e.g. {sorted(missing)[0]}) — an unclassified path is a `--check` failure in "
            f"the generator and must not be a silent default here"
        )
    bad = sorted({classes[p] for p in files if classes[p] not in CLASSES})
    if bad:
        return None, f"the pin {path} declares unknown class(es) {bad}; expected {list(CLASSES)}"
    return pin, None


def compare(pin: dict, root: Path, subset: tuple[str, ...] | None = None) -> dict:
    """Compare a tree against a pin, per path, with the counts and the names.

    `subset` narrows the population to named MANIFEST paths (e.g. the ten files
    `BOOTSTRAP.md` step 4c names). It is a filter on the reference, never a second list:
    a caller that passes a path the pin does not carry gets a problem naming it, because
    silently ignoring an unknown path is how a census reports a figure over a population
    the reader never examined.
    """
    files: dict[str, str] = pin.get("files") or {}
    classes: dict[str, str] = pin.get("classes") or {}
    problems: list[str] = []
    if subset is not None:
        unknown = [p for p in subset if p not in files]
        if unknown:
            problems.append(
                f"the subset names {len(unknown)} path(s) the pin does not carry "
                f"(e.g. {sorted(unknown)[0]}) — the population would be smaller than the "
                f"figure claims"
            )
            subset = tuple(p for p in subset if p in files)
    else:
        subset = tuple(files)

    counts = {"same": 0, "DIFF": 0, "ABSENT": 0}
    diff_files: list[str] = []
    absent_files: list[str] = []
    by_class: dict[str, dict[str, int]] = {}
    for rel in subset:
        want = files[rel]
        local = root / member_path(rel)
        cls = classes.get(rel, "?")
        slot = by_class.setdefault(cls, {"same": 0, "DIFF": 0, "ABSENT": 0})
        if not local.is_file():
            counts["ABSENT"] += 1
            slot["ABSENT"] += 1
            absent_files.append(member_path(rel))
        elif sha256_of(local) == want:
            counts["same"] += 1
            slot["same"] += 1
        else:
            counts["DIFF"] += 1
            slot["DIFF"] += 1
            diff_files.append(member_path(rel))

    return {
        "pin_version": pin.get("kit_version"),
        "pin_files": len(files),
        "population": len(subset),
        "counts": counts,
        "total": sum(counts.values()),
        "diff_files": sorted(diff_files),
        "absent_files": sorted(absent_files),
        "by_class": {k: dict(v) for k, v in sorted(by_class.items())},
        "problems": problems,
        "read_from": str(root),
    }


def vendored_pin_in(root: Path) -> tuple[Path, dict | None, str | None]:
    """Locate and load the pin a factory vendored at `root`.

    Returns `(path, pin, problem)` so a caller can report WHERE it looked. A missing pin is
    a problem with a name, not a None that a caller may mistake for an empty population.
    """
    p = root / PIN_REL
    pin, problem = load_pin(p)
    return p, pin, problem


EXEMPTIONS_REL = "registry/kit-exemptions.json"


def load_exemptions(root: Path) -> tuple[dict | None, str | None]:
    """Read a factory's declared forks. `(data, None)` or `(None, problem)`.

    A factory is ALLOWED to fork a kit file — its own event set, its own actors, its own
    box's measurements. The declaration surface is FACTORY DATA, and the fact that it made
    the `commit-msg` port cheap for one factory (measured, miidas) is why the fork is a
    declaration rather than a source edit.

    THIS IS A LOADER, NEVER A JUDGE. It returns the RAW `exempt` list and admits nothing:
    the ADMISSION PREDICATE — the filter that keeps only entries carrying a `path` (or a
    bare string) — lives inside `undeclared_divergence()`, which is where a declaration
    becomes honoured. So a caller that wants the DECLARED COUNT must read it off that
    judgement (`undeclared_divergence(pin, root)["declared"]`) and must NOT count this list
    itself: the raw list and the admitted set are different populations, and a second count
    is the divergence docs/instruments/kit.md §6.5 forbids (F5, issue #263 — `tools/kit_census.py`
    reported the raw `len(exempt)` and counted an entry this predicate drops).

    THE PROBLEM STRING IS NOT A VERDICT ON EMPTINESS. A MISSING file and an UNREADABLE one
    both return a non-empty problem here, so "there is no exemptions file" cannot be
    inferred from a problem alone — a caller that tried would misread the common
    no-declarations case as a failure. Test the file's presence on the filesystem first.
    """
    p = root / EXEMPTIONS_REL
    if not p.is_file():
        return None, f"no {EXEMPTIONS_REL} in {root} — nothing is declared exempt"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{EXEMPTIONS_REL} could not be read: {exc}"
    if not isinstance(raw, dict) or "exempt" not in raw:
        return None, f"{EXEMPTIONS_REL} carries no `exempt` list"
    return raw, None


def undeclared_divergence(pin: dict, root: Path) -> dict:
    """The population a FACTORY may be judged on: the kit paths it actually carries.

    This is deliberately NOT `compare()`. A factory ports a SUBSET of the kit, so over the
    whole manifest a fresh factory reads as ~104 ABSENT cells, and a gate that reddened on
    those would punish exactly the behaviour the port rule asks for. The finding here is
    narrower and it is the one the design names:

      a path the tree CARRIES whose bytes are not what the pin declares, and which the
      tree has not declared exempt.

    ABSENT is therefore not a verdict at all — it is the population filter — and a path the
    factory never took cannot diverge from anything.

    `seed`-CLASS PATHS ARE NOT JUDGED, which is what the class means rather than a
    convenience: the class doc says such a file "is never compared byte-for-byte, because the
    factory's copy legitimately differs". The first version of this predicate compared them
    anyway, so the class map and the predicate disagreed -- and the disagreement was not
    theoretical: `TEMPLATE/README.md` maps to `README.md`, so EVERY factory would have been
    reported as diverging on its own README, a document it is supposed to own. They are
    COUNTED in `skipped_class` rather than dropped, because an exclusion nobody can see is
    the silent-exclusion shape this kit's law refuses: a caller can print how many paths left
    the population and why.
    """
    files: dict[str, str] = pin.get("files") or {}
    classes: dict[str, str] = pin.get("classes") or {}
    exemptions, exempt_problem = load_exemptions(root)
    declared: set[str] = set()
    if exemptions is not None:
        for e in exemptions.get("exempt") or []:
            if isinstance(e, dict) and e.get("path"):
                declared.add(str(e["path"]))
            elif isinstance(e, str):
                declared.add(e)

    carried = 0
    skipped_class = 0
    diverging: list[dict] = []
    for rel, want in files.items():
        local = root / member_path(rel)
        if not local.is_file():
            continue
        if classes.get(rel) == "seed":
            skipped_class += 1
            continue
        carried += 1
        got = sha256_of(local)
        if got == want:
            continue
        mp = member_path(rel)
        if mp in declared or rel in declared:
            continue
        diverging.append({"path": mp, "class": classes.get(rel, "?"),
                          "pin_sha": want[:12], "tree_sha": got[:12]})
    return {
        "pin_version": pin.get("kit_version"),
        "carried": carried,
        "skipped_class": skipped_class,
        "declared": len(declared),
        "exemption_problem": exempt_problem,
        "diverging": sorted(diverging, key=lambda d: d["path"]),
    }
