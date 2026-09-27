#!/usr/bin/env python3
"""Publish the adoption census for ONE instrument — held, declared, and the pair's two legs.

WHY A PUBLISHED ARTIFACT. An instrument is a unit of adoption (frame §1), and its law doc §2
DECLARES the file set a member must hold. A census that lives only in a turn's stdout cannot be
re-read, diffed, or cited — and the promotion's own law file §9 says its readings are written
"when the wave returns them", each with its own instant.

WHAT THIS IS, AND WHAT IT IS NOT. It is ONE predicate applied to a declared population:
*did each path the law doc declares exist, at the member's recorded repository path, at this
instant.* It is NOT a second comparison of the kit's bytes — `kit_census.py` owns that, and two
predicates over the same population would let this file and a member's own gate disagree.
A path that is PRESENT here may still differ byte-wise from the manifest; that is `kit_pin`'s
question, and this file says so rather than quietly answering it.

THE TWO LEGS — the counting rule, and the defect this exists to avoid. A member is counted
**adopted** only when BOTH hold:
  1. **held** — every declared path is present at its recorded repo (the measured leg); and
  2. **declared** — the member's own fragment carries a disposition (the declared leg).
A copy alone is not adoption: a member can hold a complete set that arrived as another
instrument's closure (frame §1.3) with no decision behind it, and it can be green on a partial
set because a gate judges what the tree carries and a missing file is not a failing one. So the
row carries both legs, and a member with one leg is reported as exactly that.

THE PREDICATE'S SOURCE IS THE LAW DOC, deliberately. §2's table is the declaration; deriving the
path list from it keeps one source of truth instead of a second list here that drifts. The parse
is guarded by a POSITIVE CONTROL — it refuses rather than censusing an empty set, because a zero
over a failed parse is indistinguishable from a zero over an empty population.

Run:  python3 tools/instrument_census.py <instrument> [--out PATH] [--stdout]
Exit: 0 published; 1 the declared set could not be derived, or no member was reachable, so an
      empty artifact would read as a clean fleet.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The states a module's disposition can take. `UNDECLARED` is not a disposition — it is the
# ABSENCE of one, which is the state the frame's §7.2 forbids ("silence is not a disposition").
DISPOSITIONS = ("adopted", "partial", "deferred", "not-applicable")

# The member-side path of the reload link is `<skill dir>/<instrument>.md` (frame §6.1): the
# member's own act, in the member's own tree, and named for the instrument.


def declared_paths(instrument: str) -> tuple[list[str], str]:
    """The member-side paths the law doc §2 declares, and the law doc path it read.

    §2's table carries both halves per row — `tools/review.py` ↔ `TEMPLATE/tools/review.py` —
    and the MEMBER adopts the root half, so the left-hand path is the one measured.
    """
    law = REPO / "docs" / "instruments" / f"{instrument}.md"
    if not law.is_file():
        return [], str(law)
    text = law.read_text(encoding="utf-8")
    rows = re.findall(r"^\|\s*\d+\s*\|\s*`([^`]+)`\s*↔\s*`([^`]+)`", text, re.M)
    if not rows:
        # A DIFFERENT table shape, or the section was rewritten. Return EMPTY so the caller
        # refuses — never parse-zero-paths into a clean census.
        return [], str(law)
    return [left.strip() for left, _right in rows], str(law)


def members() -> list[dict]:
    out = []
    for f in sorted((REPO / "registry" / "factories").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(d, dict):
            d["_fragment"] = str(f.relative_to(REPO))
            out.append(d)
    return out


def reload_link_state(member: dict, instrument: str) -> tuple[str, str]:
    """(state, path) for the member's reload link. NEVER installed from here (frame §6.1)."""
    skill = str(member.get("skill") or "")
    if not skill:
        return "no-skill-declared", ""
    link = Path(os.path.dirname(skill)) / f"{instrument}.md"
    if link.is_symlink():
        return ("resolves" if link.exists() else "BROKEN"), str(link)
    if link.is_file():
        return "regular-file", str(link)
    return "absent", str(link)


def declared_disposition(member: dict) -> str:
    """The member's DECLARED state, read from the only declaration surface the registry carries.

    TWO SURFACES, AND THEY ARE NOT INTERCHANGEABLE — the distinction this function exists to
    keep. `registry/factories/<slug>.json` carries a `kit` field (HQ's schema) whose value is
    the **KIT's** adoption state; there is no field for a PER-INSTRUMENT disposition, so this
    reader must never render one as the other. A member that declared its kit adopted has said
    nothing about this instrument, and reading it across would manufacture an adoption nobody
    decided.

    So it returns the kit state LABELLED as the kit's, or `unestablished` — and the census
    reports the instrument-level leg as unestablished for every member rather than defaulting it.
    That is a fact about the schema (HQ's to extend), not a member's omission, and the artifact
    says so.
    """
    kit = member.get("kit")
    if isinstance(kit, dict):
        state = kit.get("state")
        if isinstance(state, str) and state.strip():
            return f"kit={state.strip()}"
    return "unestablished"


def census(instrument: str) -> dict:
    paths, law = declared_paths(instrument)
    instant = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not paths:
        return {"problem": f"no declared paths parsed from {law}", "instant": instant,
                "rows": [], "paths": [], "law": law}

    rows = []
    for m in members():
        repo = str(m.get("repo") or "")
        cells = []
        for p in paths:
            present = bool(repo) and Path(repo, p).is_file()
            cells.append({"path": p, "present": present})
        held = sum(1 for c in cells if c["present"])
        link_state, link_path = reload_link_state(m, instrument)
        declared = declared_disposition(m)
        complete = held == len(paths)
        if repo and Path(repo, "TEMPLATE", paths[0]).is_file():
            # THIS member's tree is an AUTHORING tree — it carries the `TEMPLATE/` half, which
            # only the repo the instrument is authored in does. It holds the set by
            # construction, so counting it as an adoption site would report the source as its
            # own adopter and inflate every wave by one.  Detected from the ARTIFACT rather
            # than by comparing paths: this tool runs from a worktree, whose root is not the
            # member's root, so a path equality would silently miss it.
            status = "SOURCE"
        elif declared == "unestablished":
            # BOTH LEGS, and the reason this column exists: held-with-no-declaration is the
            # frame's §7.2 silence, and it must not read as adoption.
            status = "HELD-UNDECLARED" if complete else ("PARTIAL-UNDECLARED" if held else "ABSENT")
        else:
            status = "ADOPTED" if complete else f"DECLARED-{declared.upper()}"
        rows.append({"member": m.get("factory") or "?", "repo": repo,
                     "fragment": m.get("_fragment"), "cells": cells, "held": held,
                     "of": len(paths), "reload_link": link_state, "reload_path": link_path,
                     "declared": declared, "status": status})
    return {"problem": None, "instant": instant, "rows": rows, "paths": paths, "law": law}


def render(c: dict) -> str:
    paths, rows = c["paths"], c["rows"]
    n = len(paths)
    lines = [
        "# Instrument adoption census — one predicate over the declared population",
        "",
        f"Read at **{c['instant']}** by `tools/instrument_census.py`.",
        "",
        "## The predicate, stated before the figures",
        "",
        "**Predicate:** for each member, `os.path.isfile(member.repo / p)` for every path `p` the",
        f"law doc's §2 declares — **{n} path(s)** — plus the reload link's own state.",
        "**Scope:** the member fragments in `registry/factories/*.json`.",
        f"**Instant:** {c['instant']}.",
        "",
        "**WHAT THIS DOES NOT MEASURE.** It is ONE predicate on file PRESENCE. A present file may",
        "differ byte-wise from the manifest — that is `kit_pin`'s question, not this one —",
        "and a `seed`-class absence is a declaration, not a gap. Read a `held` figure as *held*,",
        "never as *current*.",
        "",
        f"**Declared set, derived from `{Path(c['law']).relative_to(REPO)}` §2** (the parse is",
        "guarded: zero parsed paths refuses rather than censusing an empty set):",
        "",
    ]
    for i, p in enumerate(paths, 1):
        lines.append(f"{i}. `{p}`")
    lines += [
        "",
        "## The readings",
        "",
        "| member | held | reload link | fragment declares | status |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| `{r['member']}` | {r['held']}/{r['of']} | {r['reload_link']} | "
                     f"{r['declared']} | **{r['status']}** |")
    lines += [
        "",
        "## The two legs, and why a copy alone is not adoption",
        "",
        "A row is **ADOPTED** only when the declared set is COMPLETE *and* the member has a",
        "DECLARATION behind it. `HELD-UNDECLARED` is a member holding every path with no decision",
        "behind it (frame §1.3 — the files can arrive as another instrument's closure), and",
        "`PARTIAL-UNDECLARED` is a member holding some of them. Both are reported as what they",
        "are: silence is a state here, never a pass.",
        "",
        "**THE DECLARED LEG IS UNESTABLISHED, FOR EVERY MEMBER, AND THAT IS A SCHEMA FACT.**",
        "`registry/factories/<slug>.json` carries a `kit` field whose value is the **KIT's**",
        "adoption state (obligation O6). There is no field for a PER-INSTRUMENT disposition, so a",
        "member that declared its kit adopted has said nothing about this instrument — and reading",
        "one as the other would manufacture an adoption nobody decided. This census therefore",
        "reports the leg as unestablished rather than defaulting it, and **no member can reach",
        "ADOPTED until that surface exists or a member declares on one this census can read.**",
        "That is HQ's schema to extend, not a member's omission.",
        "",
        "`SOURCE` marks the member whose repo IS the repo the instrument is authored in. It holds",
        "the set by construction; counting it as an adoption site would report the source as its",
        "own adopter and inflate every wave by one.",
        "",
        "The **reload link** is the member's own act (frame §6.1) and is never installed from this",
        "repo. `absent` is a declared state, not a failure — a law doc with no reload link is",
        "perfectly readable, it is simply not re-injected after compaction.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("instrument", help="instrument slug, e.g. review-rotation")
    ap.add_argument("--out", default="", help="artifact path (default: dated, under evidence/)")
    ap.add_argument("--stdout", action="store_true", help="also print the artifact")
    args = ap.parse_args(argv)

    c = census(args.instrument)
    if c["problem"]:
        print(f"instrument census: REFUSED — {c['problem']}")
        return 1
    if not any(r["held"] for r in c["rows"]):
        # NOT necessarily an error — a fresh instrument is held by nobody. But say so, with
        # the population, rather than letting a wall of zeros read as a clean sweep.
        print(f"instrument census: 0 of {len(c['rows'])} members hold any declared path "
              f"at {c['instant']} (population: {', '.join(r['member'] for r in c['rows'])})")

    body = render(c)
    out = Path(args.out) if args.out else (
        REPO / "evidence" / f"instrument-census-{args.instrument}-{c['instant'][:10]}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"instrument census: published {out.relative_to(REPO) if out.is_relative_to(REPO) else out}"
          f" at {c['instant']} — {len(c['rows'])} member(s), declared set {len(c['paths'])}")
    if args.stdout:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
