#!/usr/bin/env python3
"""Publish the adoption census for ONE instrument — held, declared, and the pair's two legs.

WHY A PUBLISHED ARTIFACT. An instrument is a unit of adoption (template-instruments.md §1),
and its law doc DECLARES the file set a member must hold. A census that lives only in a turn's stdout cannot be
re-read, diffed, or cited — and the promotion's own law file says its readings are written
"when the wave returns them", each with its own instant.

WHAT THIS IS, AND WHAT IT IS NOT. It is ONE predicate applied to a declared population:
*did each path the law doc declares exist, at the member's recorded repository path, at this
instant.* It is NOT a second comparison of the kit's bytes — `kit_census.py` owns that, and two
predicates over the same population would let this file and a member's own gate disagree.
A path that is PRESENT here may still differ byte-wise from the manifest; that is `kit_pin`'s
question, and this file says so rather than quietly answering it. And PRESENT means present on
the WORKING TREE: a declared path may be present and UNTRACKED, so a `held` figure is never a
fact about the member's repository (template-instruments.md §7.5) — a member can read
held-complete over a commit that cannot run the instrument from a clone.

THE TWO LEGS — the counting rule, and the defect this exists to avoid. A member is counted
**adopted** only when BOTH hold:
  1. **held** — every declared path is present on the member's WORKING TREE at its recorded
     repo path (the measured leg — a live-subject reading, never a repository fact;
     template-instruments.md §7.5); and
  2. **declared** — the member's own fragment declares a disposition at `instruments.<slug>`,
     the per-instrument surface, and says `adopted` with `green: true` (the declared leg).
     The shape of that declaration is NOT restated here: `tools/registry.py` owns it and this
     file calls its predicate, so a state this census prints is one the registry gate accepts.
     An ABSENT key is legal and reads as the member's silence; a PRESENT key the registry
     refuses reads `DECLARED-INVALID` and is listed with the registry's own errors.
A copy alone is not adoption: a member can hold a complete set that arrived as another
instrument's closure (template-instruments.md §1.3) with no decision behind it, and it can be green on a partial
set because a gate judges what the tree carries and a missing file is not a failing one. So the
row carries both legs, and a member with one leg is reported as exactly that.

THE PREDICATE'S SOURCE IS THE LAW DOC, deliberately. That table is the declaration; deriving the
path list from it keeps one source of truth instead of a second list here that drifts. The parse
is guarded by a POSITIVE CONTROL — it refuses rather than censusing an empty set, because a zero
over a failed parse is indistinguishable from a zero over an empty population.

Run:  python3 tools/instrument_census.py <instrument> [--out PATH] [--stdout]
Exit: 0 published; 1 the declared set could not be derived, or no member was reachable, so an
      empty artifact would read as a clean fleet. A REFUSAL ALSO WRITES an artifact naming the
      refused input by path (template-instruments.md §1.5): an exit code reaches a caller, and a reader meets
      artifacts, so a refusal that reaches no artifact is a coverage gap that looks like a
      shorter list.
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

# The declaration's shape is NOT restated here. The state set, the reason requirement and the
# `green` axis live in `tools/registry.py::validate_disposition`, and this file calls it — a
# second copy of those literals would drift silently, and a census printing states the registry
# gate no longer accepts is worse than one printing none. `_REGISTRY` caches that import.
_REGISTRY = None

# The member-side path of the reload link is `<skill dir>/<instrument>.md` -- the member's own
# act, in the member's own tree, named for the instrument (template-instruments.md §6.1).


def declared_paths(instrument: str) -> tuple[list[str], str]:
    """The member-side paths the law doc DECLARES, and the law doc path it read.

    That table carries both halves per row — `tools/review.py` ↔ `TEMPLATE/tools/review.py` —
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
    """(state, path) for the member's reload link. NEVER installed from here (template-instruments.md §6.1)."""
    skill = str(member.get("skill") or "")
    if not skill:
        return "no-skill-declared", ""
    link = Path(os.path.dirname(skill)) / f"{instrument}.md"
    if link.is_symlink():
        return ("resolves" if link.exists() else "BROKEN"), str(link)
    if link.is_file():
        return "regular-file", str(link)
    return "absent", str(link)


def _registry_module():
    """`tools/registry.py`, imported BY PATH so one rule keeps one home.

    The per-instrument declaration's shape — its state set, its reason requirement, and the
    `green` axis `adopted` must name — is `validate_disposition` in that file. Restating any of
    it here would split one rule across two readers, and the drift would be silent: every row
    this census prints would describe a schema the registry gate no longer enforces. Imported by
    path rather than as a package because `tools/` is not one — the technique the pre-commit hook
    uses for the same reason.
    """
    global _REGISTRY
    if _REGISTRY is None:
        import importlib.util
        src = REPO / "tools" / "registry.py"
        spec = importlib.util.spec_from_file_location("oc_registry", src)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _REGISTRY = module
    return _REGISTRY

def declared_disposition(member: dict, instrument: str) -> tuple[str, str, list[str]]:
    """`(label, state, errors)` — the member's declaration FOR THIS INSTRUMENT, and HQ's verdict.

    THE SURFACE IS `instruments.<slug>` — a MAP on the member's fragment, keyed by slug (HQ's
    schema, enforced in `tools/registry.py`). The `kit` key beside it is the **KIT's** adoption
    state and says NOTHING about this instrument, so the two are read apart and never rendered as
    each other: a member that declared its kit adopted has not declared this instrument.

    An ABSENT key is a LEGAL state, not a failure — the schema makes absence valid, so a member
    that never considered the instrument stays distinguishable from one that considered it and
    said nothing. Absence returns `absent` with no errors, and the row reads as
    held-with-no-declaration rather than being defaulted to a state.

    A PRESENT key is validated by the registry's OWN predicate with `require_green=True` — the
    call `validate_instruments` makes. So a deferral with no reason, or an `adopted` that leaves
    its `green` axis unspoken, is reported here as INVALID carrying the registry's own errors,
    never silently accepted.
    """
    surface = member.get("instruments")
    if not isinstance(surface, dict) or instrument not in surface:
        return "absent", "", []
    disp = surface[instrument]
    errors = _registry_module().validate_disposition(
        str(member.get("_fragment") or "<fragment>"),
        f"instruments.{instrument}", disp, require_green=True)
    if errors:
        state = disp.get("state") if isinstance(disp, dict) else None
        return "INVALID", state if isinstance(state, str) else "", errors
    state = str(disp.get("state"))
    green = disp.get("green")
    if isinstance(green, bool):
        return f"{state} · green={str(green).lower()}", state, []
    return state, state, []


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
        declared, declared_state, declared_errors = declared_disposition(m, instrument)
        complete = held == len(paths)
        if repo and Path(repo, "TEMPLATE", paths[0]).is_file():
            # THIS member's tree is an AUTHORING tree — it carries the `TEMPLATE/` half, which
            # only the repo the instrument is authored in does. It holds the set by
            # construction, so counting it as an adoption site would report the source as its
            # own adopter and inflate every wave by one.  Detected from the ARTIFACT rather
            # than by comparing paths: this tool runs from a worktree, whose root is not the
            # member's root, so a path equality would silently miss it.
            status = "SOURCE"
        elif declared == "absent":
            # BOTH LEGS, and the reason this column exists: held-with-no-declaration is the
            # template-instruments.md §7.2 silence, and it must not read as adoption. An absent key is LEGAL
            # (HQ's schema), so this is a reading of the member's own silence, not a refusal.
            status = "HELD-UNDECLARED" if complete else ("PARTIAL-UNDECLARED" if held else "ABSENT")
        elif declared_errors:
            # The key IS there and the registry's own predicate rejects it — a deferral with no
            # reason, or an `adopted` that left its `green` axis unspoken. Reported as its own
            # status rather than absorbed into a state, because "declared" and "declared
            # lawfully" are different readings and only the second one is a disposition.
            status = "DECLARED-INVALID"
        else:
            # A complete set under a declaration that says adopted; anything else keeps the
            # state it named, so a member that declared `partial` over a complete set reads as
            # what it said rather than as an adoption nobody decided.
            status = ("ADOPTED" if (complete and declared_state == "adopted")
                      else f"DECLARED-{declared_state.upper()}")
        rows.append({"member": m.get("factory") or "?", "repo": repo,
                     "fragment": m.get("_fragment"), "cells": cells, "held": held,
                     "of": len(paths), "reload_link": link_state, "reload_path": link_path,
                     "declared": declared, "declared_state": declared_state,
                     "declared_errors": declared_errors, "status": status})
    return {"problem": None, "instant": instant, "rows": rows, "paths": paths, "law": law}


def render_refusal(instrument: str, law: str, instant: str, reason: str) -> str:
    """The artifact written when the declared set cannot be derived.

    WHY A REFUSED RUN STILL WRITES. template-instruments.md §1.5: an aggregate must report the inputs it REFUSED,
    by PATH, in the artifact a reader meets — otherwise a short list and a wrong list are
    indistinguishable, and a refusal nobody reads is a silent coverage gap. The exit code and the
    stderr line reach an interactive caller only; a reader who lists `evidence/` sees artifacts,
    so the refusal has to be one of them.
    """
    try:
        shown = Path(law).relative_to(REPO)
    except ValueError:
        shown = law
    # The reason string carries the same path the caller resolved, so REPO-normalise it too: an
    # absolute worktree path in a published artifact is a figure that does not travel.
    reason = str(reason).replace(str(REPO) + "/", "")
    return "\n".join([
        f"# Instrument adoption census — REFUSED: {instrument}",
        "",
        f"Read at **{instant}** by `tools/instrument_census.py`.",
        "",
        "## This instrument was NOT censused",
        "",
        f"**Refused input (by path):** `{shown}`",
        f"**Reason:** {reason}",
        "",
        "**Exit status:** 1 — no census was produced for this instrument.",
        "",
        "## Why this file exists rather than an absent one",
        "",
        "A refusal that reaches only the exit code and the stderr line is invisible to a reader",
        "who meets the published artifacts: two files in `evidence/` and three refusals would",
        "read identically to two adopted instruments and no gap at all. So the refused input is",
        "named HERE, in the artifact a reader meets (template-instruments.md §1.5).",
        "",
        "This is a COORDINATE reading, not a defect verdict on the law file: the census derives",
        "the declared set from the law doc's declared-set table as numbered rows pairing the member",
        "path with",
        "its template counterpart, and that table may hold a different object for a good reason. The",
        "coordinate fix belongs to that instrument's own lane; this file's job is to say so out",
        "loud rather than to return a shorter list.",
        "",
    ])

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
        f"law doc's declared-set table declares — **{n} path(s)** — plus the reload link's own state.",
        "**Scope:** the member fragments in `registry/factories/*.json`.",
        f"**Instant:** {c['instant']}.",
        "",
        "**WHAT THIS DOES NOT MEASURE.** It is ONE predicate on file PRESENCE. A present file may",
        "differ byte-wise from the manifest — that is `kit_pin`'s question, not this one —",
        "and a `seed`-class absence is a declaration, not a gap. Read a `held` figure as *held*,",
        "never as *current*.",
        "",
        "**And `held` is a presence measurement over a WORKING TREE, so a path may be present AND",
        "untracked.** A member can therefore read held-complete over a commit that cannot run the",
        "instrument from a clone at all. So `held` is a reading of a live tree and is **never a",
        "fact about the member's repository** — those are two different figures wherever a declared",
        "path is untracked. The axis and its prohibition are template-instruments.md §7.5, not",
        "this tool's.",
        "",
        f"**Declared set, derived from `{Path(c['law']).relative_to(REPO)}`'s declared-set table** (the parse",
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
    rejected = [r for r in rows if r["declared_errors"]]
    if rejected:
        lines += [
            "",
            "## Declarations the registry's own predicate rejects",
            "",
            "The key IS present and `tools/registry.py::validate_disposition` refuses it. A",
            "refused declaration is NOT a disposition — it is a declaration wearing a state it",
            "has not earned — so it is listed with the registry's own errors rather than",
            "absorbed into a state, and the row above reads `DECLARED-INVALID`.",
            "",
        ]
        for r in rejected:
            lines.append(f"**`{r['member']}`** — `instruments.<slug>`: {r['declared']}")
            lines += [f"- {e}" for e in r["declared_errors"]]
    lines += [
        "",
        "## The two legs, and why a copy alone is not adoption",
        "",
        "A row is **ADOPTED** only when the declared set is COMPLETE *and* the member's own",
        "declaration says `adopted` with `green: true`. `HELD-UNDECLARED` is a member holding",
        "every path with no decision behind it (template-instruments.md §1.3 — the files can arrive",
        "as another",
        "instrument's closure), and `PARTIAL-UNDECLARED` is a member holding some of them. Both",
        "are reported as what they are: silence is a state here, never a pass.",
        "",
        "**THE DECLARED LEG IS READ FROM `instruments.<slug>`, HQ's per-instrument surface.**",
        "The fragment's `kit` key beside it is the **KIT's** adoption state (obligation O6) and",
        "says nothing about this instrument, so it is never read as one: a member that declared",
        "its kit adopted has not declared this instrument. An **absent** key is a LEGAL state —",
        "the schema makes absence valid — so it is reported as the member's silence, which is a",
        "reading rather than a refusal, and it is what keeps a member that considered the",
        "instrument distinguishable from one that never did.",
        "",
        "`SOURCE` marks the member whose repo IS the repo the instrument is authored in. It holds",
        "the set by construction; counting it as an adoption site would report the source as its",
        "own adopter and inflate every wave by one.",
        "",
        "The **reload link** is the member's own act (template-instruments.md §6.1) and is never",
        "installed from this",
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
        # The refusal is PUBLISHED, not only printed: template-instruments.md §1.5 requires the
        # refused inputs to
        # reach the artifact a reader meets, so the exit code alone is not the deliverable.
        instant = c.get("instant") or dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        body_out = Path(args.out) if args.out else (
            REPO / "evidence"
            / f"instrument-census-{args.instrument}-{instant[:10]}.md")
        body_out.parent.mkdir(parents=True, exist_ok=True)
        body_out.write_text(
            render_refusal(args.instrument, str(c.get("law") or ""), instant, c["problem"]),
            encoding="utf-8")
        shown = (body_out.relative_to(REPO)
                 if body_out.is_relative_to(REPO) else body_out)
        print(f"instrument census: REFUSED — {c['problem']}")
        print(f"instrument census: refusal recorded at {shown} at {instant}")
        if args.stdout:
            print(body_out.read_text(encoding="utf-8"))
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
