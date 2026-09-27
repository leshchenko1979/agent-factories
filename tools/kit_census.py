#!/usr/bin/env python3
"""Publish the kit-drift census — the leg's measurement plus each member's DECLARED state.

WHY A PUBLISHED ARTIFACT. The kit-drift leg measured adoption and the measurement existed
only as transient patrol output: no report a plan or a member could be corrected against.
A figure that lives only in a turn's stdout cannot be re-read, diffed, or cited, so the
plan's own corrections had nothing to reference.

WHAT THIS IS NOT. It is not a second measurement. The leg is the one predicate
(`kit_pin.compare`, shared with each factory's own pin gate); this tool CALLS it and renders
its result. A second comparison would let our report and a member's gate disagree about the
same bytes, which is the one-field-one-predicate rule this kit's law states.

THE REFERENCE, STATED BECAUSE IT IS EASY TO OVER-READ. The leg compares a member's tree
against OUR `registry/kit.json` — the manifest THIS repo generates. A DIFF is therefore a
fact about our shipped bytes as much as about their tree, and it moves when WE move. It is
not actionable by the member, and the artifact says so. What a member CAN act on is its own
vendored pin (`registry/kit.json` in its tree, from the vehicle
`TEMPLATE/registry/kit.example.json`), judged by `tests/test_kit_pin.py`. This census is the
fleet view; the pin gate is the member's own view.

THE DECLARED HALF. A figure alone cannot be acted on: "5 DIFF" does not say whether the
member considered, declined, or never saw the file. So each member's DECLARED state is
rendered beside its figure — read from this repo's `registry/factories/<slug>.json`, which
is the surface the attestation round writes. A member that has declared a fork and a member
that has silently diverged produce the same figure and must not read the same.

Run:  python3 tools/kit_census.py [--out PATH] [--stdout]
Exit: 0 published; 1 the leg examined NOTHING (no reachable member), so there was nothing to
      publish and an empty artifact would read as a clean fleet.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import patrol_host_state as P  # noqa: E402  (path insert must precede it)

EVIDENCE = REPO / "evidence"
FACTORY_DIR = REPO / "registry" / "factories"
DECISIONS = REPO / "registry" / "kit-decisions.json"


def load_declarations(slug: str) -> dict:
    """This repo's record of what a member DECLARED, or an explicit absence.

    Absence is reported as absence rather than as an empty declaration: a member that
    never attested and a member that attested to nothing are different states, and a
    renderer that conflated them would make the second look like the first.
    """
    path = FACTORY_DIR / f"{slug}.json"
    if not path.is_file():
        return {"declared": False, "why": f"no {path.relative_to(REPO)}"}
    try:
        frag = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"declared": False, "why": f"unreadable: {exc}"}
    zone = frag.get("zone") or {}
    return {
        "declared": True,
        "display_name": frag.get("display_name") or slug,
        "status": frag.get("status") or "(unstated)",
        "attested_at": frag.get("attested_at") or "(unstated)",
        "owns": len(zone.get("owns") or []),
        "does_not_own": len(zone.get("does_not_own") or []),
        "services": len(frag.get("services") or []),
        "announcements": len(frag.get("announcements") or []),
        "lanes": len(frag.get("lanes") or []),
    }


def pin_state(root: str) -> dict:
    """Whether the member has vendored a pin, and what it declares exempt.

    This is the member-ACTIONABLE half, and it is machine-readable: `registry/kit.json` in
    the member's tree (from the vehicle) plus its own `registry/kit-exemptions.json`. It
    fills in as members adopt, which is why the census renders it rather than describing
    the intent. A member with no pin has no figure of its own at all — the fleet figure
    below is against OUR manifest and moves when WE move.
    """
    r = Path(root)
    pin = r / "registry" / "kit.json"
    ex = r / "registry" / "kit-exemptions.json"
    out = {"vendored": pin.is_file(), "exemptions": None, "why": ""}
    if not out["vendored"]:
        out["why"] = "no registry/kit.json in the member's tree"
        return out
    if not ex.is_file():
        out["exemptions"] = 0
        return out
    try:
        d = json.loads(ex.read_text())
        out["exemptions"] = len(d.get("exempt") or [])
    except (OSError, json.JSONDecodeError) as exc:
        out["exemptions"] = None
        out["why"] = f"exemptions unreadable: {exc}"
    return out


def load_decisions() -> dict:
    """Our record of what each member DECLARED, sourced — see the file's own _note."""
    if not DECISIONS.is_file():
        return {}
    try:
        return (json.loads(DECISIONS.read_text()).get("members") or {})
    except (OSError, json.JSONDecodeError):
        return {}


def _cell_row(m: dict, decl: dict) -> str:
    if not m["reachable"]:
        return f"| `{m['slug']}` | — | — | — | — | — | **unreachable** |"
    d = decl
    if d.get("declared"):
        declared = f"{d['attested_at']} · {d['status']}"
        zone = f"{d['owns']}/{d['does_not_own']}"
    else:
        # A member with NO fragment on record is a state, not a crash: `load_declarations`
        # returns the absence explicitly, and a renderer that indexed the missing keys
        # would take the whole census down for the one member it could not describe.
        declared = f"**not declared** ({d.get('why', 'no record')})"
        zone = "—"
    ps = pin_state(m["root"])
    if ps["vendored"]:
        pin = f"vendored · {ps['exemptions']} exempt" if ps["exemptions"] is not None else "vendored"
    else:
        pin = "**none**"
    return (
        f"| `{m['slug']}` | {m['same']} | {m['DIFF']} | {m['ABSENT']} | {pin} | "
        f"{zone} | {declared} |"
    )


def render(leg: dict, read_at: str) -> str:
    cov = leg.get("coverage") or {}
    members = cov.get("members") or []
    mc = cov.get("manifest_cells") or {}
    bc = cov.get("bootstrap_cells") or {}
    names = cov.get("bootstrap_named") or []

    out: list[str] = []
    out.append("# Kit-drift census — member adoption of the template's shipped set")
    out.append("")
    out.append(f"Read at **{read_at}** by `tools/kit_census.py`, which calls the patrol's")
    out.append("`kit_drift_leg` — this artifact renders that leg's own result and adds no")
    out.append("comparison of its own.")
    out.append("")
    out.append("## 1. The reference, stated first")
    out.append("")
    out.append(f"Every figure below compares a member's tree against **OUR** "
               f"`registry/kit.json`")
    out.append(f"(`kit_version` `{cov.get('kit_version')}`, {cov.get('manifest_files')} "
               f"paths). That is a")
    out.append("fact about our shipped bytes as much as about their tree, and it moves when")
    out.append("**we** move — so a DIFF here is not a member's to act on. A member acts on")
    out.append("its own vendored pin, judged by `tests/test_kit_pin.py`.")
    out.append("")
    out.append("## 2. The population")
    out.append("")
    out.append(f"- members declared: **{cov.get('members_declared')}**, "
               f"reachable: **{cov.get('members_reachable')}**")
    if cov.get("members_unreachable"):
        out.append(f"- unreachable: {', '.join('`' + s + '`' for s in cov['members_unreachable'])}")
    out.append(f"- **every manifest cell** ({cov.get('manifest_cells_total')} pairs): "
               f"same {mc.get('same')} · DIFF {mc.get('DIFF')} · ABSENT {mc.get('ABSENT')}")
    out.append(f"- **bootstrap-named subset** ({cov.get('bootstrap_cells_total')} cells, the "
               f"{len(names)} files")
    out.append("  `TEMPLATE/BOOTSTRAP.md` names): "
               f"same {bc.get('same')} · DIFF {bc.get('DIFF')} · ABSENT {bc.get('ABSENT')}")
    out.append("")
    out.append("Two populations are reported because a number must travel with its own "
               "predicate:")
    out.append("the bootstrap subset is what the earlier 1/20/29 baseline was taken over, "
               "and quoting")
    out.append("only one of them would leave the other unreproducible.")
    out.append("")
    out.append("## 3. Per member — the figure AND the declaration")
    out.append("")
    out.append("| member | same | DIFF | ABSENT | own pin | zone own/not | declared |")
    out.append("|---|---|---|---|---|---|---|")
    decls = {}
    for m in members:
        d = load_declarations(m["slug"])
        decls[m["slug"]] = d
        out.append(_cell_row(m, d))
    out.append("")
    out.append("Three columns carry the point. **own pin** is the member-actionable half: a")
    out.append("member with no pin has no figure of its own, and the DIFF beside it is against")
    out.append("OUR manifest. **declared** is when it last attested. A member that has DECLARED")
    out.append("a fork and one that has silently diverged produce the same figure, and must not")
    out.append("read the same — which is why section 5 carries what each one said.")
    out.append("")
    out.append("## 4. Declared detail")
    out.append("")
    for m in members:
        d = decls[m["slug"]]
        out.append(f"### `{m['slug']}`")
        out.append("")
        if not d["declared"]:
            out.append(f"- **no declaration on record** — {d['why']}")
            out.append("")
            continue
        out.append(f"- attested: **{d['attested_at']}** · status `{d['status']}`")
        out.append(f"- declared surfaces: zone owns {d['owns']} / not-owns "
                   f"{d['does_not_own']} · services {d['services']} · "
                   f"lanes {d['lanes']} · announcements {d['announcements']}")
        if m["reachable"]:
            if m["diff_files"]:
                shown = ", ".join(f"`{f}`" for f in m["diff_files"][:8])
                more = f" (+{len(m['diff_files']) - 8} more)" if len(m["diff_files"]) > 8 else ""
                out.append(f"- DIFF: {shown}{more}")
            if m["absent_files"]:
                shown = ", ".join(f"`{f}`" for f in m["absent_files"][:8])
                more = f" (+{len(m['absent_files']) - 8} more)" if len(m["absent_files"]) > 8 else ""
                out.append(f"- ABSENT: {shown}{more}")
        out.append("")
    out.append("## 5. Declared decisions — what each member SAID about its own figure")
    out.append("")
    decisions = load_decisions()
    if not decisions:
        out.append("No declaration record on file (`registry/kit-decisions.json` is absent), so "
                   "every figure above is bare. A bare figure cannot be acted on.")
        out.append("")
    else:
        out.append("Read from `registry/kit-decisions.json` — OUR record of what each member")
        out.append("declared, not a surface a member writes. Each entry names its source and")
        out.append("instant so it can be checked rather than trusted. Instants are quoted AS THE")
        out.append("MEMBER STATED THEM, so some are approximate; the round's own ledger rows")
        out.append("(`tool-full-set-census`, `ledger-adoption-census`) carry the measured halves.")
        out.append("")
        for m in members:
            e = decisions.get(m["slug"])
            out.append(f"### `{m['slug']}`")
            out.append("")
            if not e:
                out.append("- **no declaration recorded** — its figure above is bare.")
                out.append("")
                continue
            out.append(f"- declared **{e.get('declared_at', '(unstated)')}**, when its own "
                       f"measurement read: {e.get('figure_at_declaration', '(unstated)')}")
            forks = e.get("forks_declared") or []
            out.append(f"- forks declared exempt-or-deliberate: "
                       f"{len(forks)}" + (f" ({', '.join('`' + f + '`' for f in forks)})" if forks else ""))
            for d in e.get("decisions") or []:
                out.append(f"- {d}")
            wave = e.get("wave_2026_09_26")
            if wave:
                fields = "; ".join(
                    f"**{k}** {v}" for k, v in wave.items()
                    if k not in ("declared_at", "filed", "note"))
                out.append(f"- **2026-09-26 wave**, declared "
                           f"{wave.get('declared_at', '(unstated)')}: {fields}")
                if wave.get("note"):
                    out.append(f"  - {wave['note']}")
                if wave.get("filed"):
                    out.append(f"  - filed on its own tracker: "
                               + ", ".join(f"`{f}`" for f in wave["filed"]))
            out.append("")
    out.append("## 6. Bounds — what this census does not say")
    out.append("")
    out.append("- **DIFF is measured; behind-vs-forked is not.** The leg compares bytes. It")
    out.append("  cannot say whether a member is BEHIND the template or has deliberately")
    out.append("  forked, and those need opposite actions.")
    out.append("- **ABSENT is not a verdict.** A factory ports a subset by design; a path it")
    out.append("  never took cannot diverge from anything.")
    nopin = [m["slug"] for m in members if not pin_state(m["root"])["vendored"]]
    out.append(f"- **The pin gate is the member's own view.** "
               f"{len(nopin)} of {len(members)} members have vendored no pin"
               + (f" ({', '.join('`' + s + '`' for s in nopin)})" if nopin else "")
               + ", so for those the figure above is against OUR manifest and is not theirs to")
    out.append("  act on. The vehicle exists (`TEMPLATE/registry/kit.example.json`) and "
               "`tests/test_kit_pin.py`")
    out.append("  is the gate that judges it; this census is where that adoption is observed.")
    out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="", help="artifact path (default: dated, under evidence/)")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = ap.parse_args(argv)

    read_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    leg = P.kit_drift_leg(read_at=read_at)
    cov = leg.get("coverage") or {}

    if not cov.get("members_reachable"):
        print(f"kit census: REFUSED at {read_at} — the leg reached no member repository, so "
              f"there is nothing to publish; an empty artifact would read as a clean fleet.")
        for p in leg.get("problems") or []:
            print(f"  {p}")
        return 1

    text = render(leg, read_at)
    if args.stdout:
        print(text, end="")
        return 0

    out = Path(args.out) if args.out else (
        EVIDENCE / f"kit-drift-census-{read_at[:10]}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    # `--out` may legitimately point outside the repo (a scratch path, another tree), and
    # `relative_to` RAISES rather than falling back -- which would crash AFTER the file was
    # written, reporting failure for work that succeeded.
    try:
        shown = out.relative_to(REPO)
    except ValueError:
        shown = out
    print(f"kit census: published {shown} at {read_at} — "
          f"{cov.get('members_reachable')}/{cov.get('members_declared')} members reachable, "
          f"bootstrap cells same {cov.get('bootstrap_cells', {}).get('same')} · "
          f"DIFF {cov.get('bootstrap_cells', {}).get('DIFF')} · "
          f"ABSENT {cov.get('bootstrap_cells', {}).get('ABSENT')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
