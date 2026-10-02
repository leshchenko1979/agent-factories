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
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import kit_pin  # noqa: E402  (the pin's ONE judgement path; insert must precede it)
import patrol_host_state as P  # noqa: E402  (path insert must precede it)

EVIDENCE = REPO / "evidence"
FACTORY_DIR = REPO / "registry" / "factories"
DECISIONS = REPO / "registry" / "kit-decisions.json"


# == the answering path =============================================================
#
# THE PUBLISHED PAGE IS SERVED FROM A DIFFERENT HOST THAN THIS MEASUREMENT RUNS ON, and
# the CLI it serves with runs HERE. `/opt/questions/backend.py` on the vpn host answers an
# owner's tap by ssh'ing to this box and executing the register CLI, resolving that CLI at
# CALL TIME -- `ls -1 <CLI_ROOT>/*/oc-questions <CLI_ROOT>/oc-questions`, exactly-one or
# exit 127 -- because the CLI moved once (`tools/` -> `tools/state/` on 2026-09-25) and a
# pinned layout silently broke every answer with rc=127. So the resolution happens on this
# host, and this function RUNS it rather than replicating a verdict about it.
#
# WHAT THIS IS NOT. Still not a second measurement of the members' TREES -- the trees are
# the patrol leg's predicate and stay there. This answers a different question: which copy
# the OWNER'S TAP reaches. A tree read cannot answer it in EITHER direction, and both
# directions were measured on 2026-09-27: `infra-factory` held a copy that never executed
# (one real install indexed over a dead file), and a copy can execute with no tree copy at
# all. State the predicate with the number, or the number cannot be read.
ANSWER_CLI_ROOT = os.environ.get(
    "OQ_CLI_ROOT",
    "/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools",
)
ANSWER_AUTHORITY = "/opt/questions/backend.py (CLI_ROOT default + the CLI_RESOLVE glob)"

# THE MEMBER-RELATIVE PATH OF THE TOOL, taken from the manifest's own `TEMPLATE/tools/questions`.
# A member's tree carries it at `<root>/tools/questions` -- the kit's declared path -- while
# the EXECUTING copy lives in the ops profile's skill tree, which sits inside NO member root.
# That gap is the whole reason the per-member column below exists: a tree read cannot see it,
# and on 2026-09-27 it was measured in both directions at once.
ANSWER_TOOL_PATH = "tools/questions"

# A MARKER IS EVIDENCE ABOUT THE LEG IT MEASURES, NEVER ABOUT THE INSTRUMENT. The two legs
# below read DIFFERENTLY at the same instant -- on 2026-09-27 the clarify leg was equal on
# both copies while the publisher-fault leg diverged by all three of its markers -- so one
# marker reported as one verdict would clear a leg it cannot see. Each leg therefore carries
# its own CONTROL, present in any copy of the tool, so that a probe which finds NOTHING is
# distinguishable from a leg that is genuinely absent; a zero without a working control is
# not evidence of absence.
ANSWER_LEGS = (
    {
        "leg": "clarify — what an owner's empty tap does",
        "control": "def republish",
        "fixed": "CLARIFY_EMPTY_TEXT",
        "old": "clarify requires --text",
        "reads": "fixed present = an empty tap is RECORDED as such; old present = the "
                 "pre-#183 refusal that died before recording it",
    },
    {
        "leg": "publisher fault — what a caller learns when a page fails to build",
        "control": "def republish",
        "fixed": "_note_publish_fault",
        "old": '"publish_failed", "SystemExit"',
        "reads": "fixed present = the reason reaches the caller; old present = only the "
                 "exception's class name is logged, and logging is gated OFF by default",
    },
)


def _leg_state(counts: dict) -> str:
    """Read a leg from its own three markers, never from the other leg's."""
    if counts["control"] == 0:
        return "UNPROBED — its control is absent, so this probe says nothing"
    if counts["fixed"] and not counts["old"]:
        return "fixed"
    if counts["old"] and not counts["fixed"]:
        return "PRE-FIX"
    if counts["fixed"] and counts["old"]:
        return "BOTH — carries the fix AND the old form; read it by hand"
    return "neither marker — this copy does not carry the leg"


def answering_path(cli_root: str = "") -> dict:
    """Which copy an OWNER'S TAP reaches, and which legs of the tool that copy carries.

    Fail-open as UNMEASURED, never as clean: a search that raises, a root that does not
    exist, or a candidate count other than one is reported as the fault it is. The backend
    exits 127 on any count but one, so an ambiguous root is not a degraded measurement --
    it is every tap refused, and it must not render as a quiet single row.
    """
    root = Path(cli_root or ANSWER_CLI_ROOT)
    out: dict = {
        "cli_root": str(root),
        "authority": ANSWER_AUTHORITY,
        "candidates": [],
        "resolved": "",
        "measured": False,
        "ambiguous": False,
        "legs": [],
        "why": "",
    }
    if not root.is_dir():
        out["why"] = f"the CLI root does not exist: {root}"
        return out
    try:
        found = sorted(
            [p for p in root.glob("*/oc-questions") if p.is_file()]
            + ([root / "oc-questions"] if (root / "oc-questions").is_file() else [])
        )
    except OSError as exc:
        out["why"] = f"cannot search {root}: {exc}"
        return out
    out["candidates"] = [str(p) for p in found]
    if len(found) != 1:
        # Not a degradation -- the backend wants exactly one and exits 127 otherwise.
        out["ambiguous"] = True
        out["why"] = (
            f"the backend wants exactly 1 candidate under {root} and finds {len(found)}; "
            f"every tap exits 127 until that is one"
        )
        return out
    path = found[0]
    try:
        text = path.read_text(errors="replace")
        st = path.stat()
    except OSError as exc:
        out["why"] = f"resolved {path} but cannot read it: {exc}"
        return out
    out["measured"] = True
    out["resolved"] = str(path)
    out["bytes"] = st.st_size
    out["mtime"] = dt.datetime.fromtimestamp(
        st.st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for spec in ANSWER_LEGS:
        counts = {
            "control": text.count(spec["control"]),
            "fixed": text.count(spec["fixed"]),
            "old": text.count(spec["old"]),
        }
        out["legs"].append({
            "leg": spec["leg"],
            "reads": spec["reads"],
            **counts,
            "state": _leg_state(counts),
        })
    return out


def _under(root: str, path: str) -> bool:
    """Whether `path` sits inside `root`, by resolved comparison rather than by prefix.

    A string prefix would read `/root/ai-antispam-old` as inside `/root/ai-antispam`; the
    resolved-relative test cannot. Symlinks are followed on both sides, so a link into a
    member's tree counts as inside it — which is the honest answer, since the loader
    follows it too.
    """
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False

def member_copy_state(m: dict, answering: dict, tool_path: str = ANSWER_TOOL_PATH) -> dict:
    """Whether a member's OWN copy sits ON the answering path, OFF it, or is ABSENT.

    Three states, and the distinction is the point this column was added for: on
    2026-09-27 `infra-factory` held a copy that had never executed (a real file, a real
    install, indexed over a dead path) while `miidas` holds one that is inert for OWNER
    TAPS but live for its own lane invocations. Those are different facts about different
    members, and a single "installed" column reported both as the same thing.

    ABSENT is not inert. A member with no copy has installed nothing; rendering it inert
    would say it had something that does not run.

    FAIL-OPEN, and this is the load-bearing branch: INERT is a claim that a copy is OFF
    the answering path, which cannot be made without the path. When the path was not
    measured -- no candidates, an ambiguous root, an unreadable copy -- the state is
    `undetermined` and says so, never `inert`. A probe that cannot see the path must not
    report a member's copy as off it.
    """
    out: dict = {"state": "", "why": "", "copy": ""}
    if not m.get("reachable"):
        out["state"] = "unreachable"
        out["why"] = "the leg could not read its tree"
        return out
    root = Path(m["root"])
    copy = root / tool_path
    if tool_path in (m.get("absent_files") or []) or not copy.exists():
        out["state"] = "ABSENT"
        out["why"] = f"no `{tool_path}` in its tree — it has installed nothing"
        return out
    out["copy"] = str(copy)
    if not answering.get("measured"):
        out["state"] = "undetermined"
        out["why"] = ("it holds a copy, but the answering path was NOT measured — so "
                      "whether that copy is on it cannot be claimed either way")
        return out
    try:
        on_path = copy.resolve() == Path(answering["resolved"]).resolve()
    except OSError as exc:
        out["state"] = "undetermined"
        out["why"] = f"it holds a copy but it cannot be resolved for comparison: {exc}"
        return out
    if on_path:
        out["state"] = "LIVE"
        out["why"] = "this copy IS the one an owner's tap reaches"
    else:
        out["state"] = "inert"
        out["why"] = ("off the answering path — reaches no owner tap; live only for its "
                      "own lane invocations, if it invokes its own copy")
    return out

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

    THE COUNT IS THE PIN'S OWN JUDGEMENT, never a second reading of the file. F5 (#263) was
    this function opening `kit-exemptions.json` itself and reporting `len(exempt)`, while
    the judgement path (`kit_pin.undeclared_divergence`) admits only entries that carry a
    `path` (or a bare string). An entry the pin IGNORES was still COUNTED, so a member read
    a declaration its own gate then reds on — §6.5 contract part 3, lawful at the write path
    and unknown at `verify`. The count now comes off the verdict's own `declared`, so ONE
    computation serves the report and the judgement and the two cannot disagree.

    UNREADABLE IS NOT ZERO, and the three states are three. A member with no pin is not
    vendored; a member whose exemptions file is ABSENT has declared nothing (0); a member
    whose file EXISTS but cannot be judged reads None plus a `why`. The verdict reports
    `declared` 0 in the unreadable case too, so the `exemption_problem` it also carries is
    what tells the two apart — dropping it would trade the over-count this fix removes for
    an absent-vs-zero lie.
    """
    r = Path(root)
    pin = r / "registry" / "kit.json"
    ex = r / "registry" / "kit-exemptions.json"
    out = {"vendored": pin.is_file(), "exemptions": None, "why": ""}
    if not out["vendored"]:
        out["why"] = "no registry/kit.json in the member's tree"
        return out
    if not ex.is_file():
        # The empty state, read from the filesystem rather than inferred from a problem
        # string: the pin admits none of a list that is not there.
        out["exemptions"] = 0
        return out
    loaded, _pin_problem = kit_pin.load_pin(pin)
    verdict = kit_pin.undeclared_divergence(loaded if loaded is not None else {}, r)
    if verdict.get("exemption_problem"):
        out["exemptions"] = None
        out["why"] = f"exemptions unreadable: {verdict['exemption_problem']}"
    else:
        out["exemptions"] = int(verdict.get("declared") or 0)
    return out


def load_decisions() -> dict:
    """Our record of what each member DECLARED, sourced — see the file's own _note."""
    if not DECISIONS.is_file():
        return {}
    try:
        return (json.loads(DECISIONS.read_text()).get("members") or {})
    except (OSError, json.JSONDecodeError):
        return {}


def _cell_row(m: dict, decl: dict, answering: dict | None = None) -> str:
    cs = member_copy_state(m, answering or {})
    if not m["reachable"]:
        return f"| `{m['slug']}` | — | — | — | — | — | — | **unreachable** |"
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
        f"{cs['state']} | {zone} | {declared} |"
    )


def render(leg: dict, read_at: str, answering: dict | None = None) -> str:
    cov = leg.get("coverage") or {}
    members = cov.get("members") or []
    mc = cov.get("manifest_cells") or {}
    bc = cov.get("bootstrap_cells") or {}
    names = cov.get("bootstrap_named") or []

    out: list[str] = []
    out.append("# Kit-drift census — member adoption of the template's shipped set")
    out.append("")
    out.append(f"Read at **{read_at}** by `tools/kit_census.py`, which calls the patrol's")
    out.append("`kit_drift_leg` — this artifact renders that leg's own result. It adds ONE")
    out.append("measurement of its own (section 2, the answering path), which is a DIFFERENT")
    out.append("predicate and not a second comparison of the same bytes.")
    out.append("")
    out.append("## 1. The reference, stated first")
    out.append("")
    out.append("Every figure below compares a member's tree against **OUR** "
               "`registry/kit.json`")
    out.append(f"(`kit_version` `{cov.get('kit_version')}`, {cov.get('manifest_files')} "
               f"paths). That is a")
    out.append("fact about our shipped bytes as much as about their tree, and it moves when")
    out.append("**we** move — so a DIFF here is not a member's to act on. A member acts on")
    out.append("its own vendored pin, judged by `tests/test_kit_pin.py`.")
    out.append("")
    out.append("## 2. The answering path — which copy an owner's tap reaches")
    out.append("")
    out.append("A DIFFERENT PREDICATE FROM EVERY NUMBER ELSEWHERE IN THIS ARTIFACT, and that is")
    out.append("why it is here: the figures below say what a member HOLDS, this one says what an")
    out.append("owner's tap REACHES. On 2026-09-27 the two disagreed in BOTH directions — one")
    out.append("factory held a copy that had never executed, and a copy can execute with no tree")
    out.append("copy at all — so neither can be read off the other.")
    out.append("")
    if answering is None:
        out.append("**NOT MEASURED** — the caller passed no answering-path result, so this")
        out.append("section states nothing about which copy is live. It is stated rather than")
        out.append("omitted because an absent section and a clean section read the same, and that")
        out.append("is the one confusion this row exists to prevent.")
        out.append("")
    elif answering.get("ambiguous"):
        out.append("**AMBIGUOUS — NOT ONE COPY.** " + str(answering["why"]))
        out.append("")
        out.append("- candidates found: %d; the backend wants exactly one and exits 127"
                   % len(answering["candidates"]))
        out.append("  otherwise, so this is every tap REFUSED rather than a degraded reading.")
        out.append("")
    elif not answering.get("measured"):
        out.append("**UNMEASURED** — " + str(answering.get("why", "no reason recorded")))
        out.append("")
    else:
        out.append("- resolved by the backend's own search — " + str(answering["authority"]))
        out.append("- CLI root searched: `" + str(answering["cli_root"]) + "`")
        out.append("- candidates: **%d** — the backend requires exactly one, so a count"
                   % len(answering["candidates"]))
        out.append("  other than 1 is reported above as a refusal, not as a partial reading")
        out.append("- **executing copy**: `" + str(answering["resolved"]) + "`")
        out.append("  - **%s B**, mtime **%s** — size and time only, no digest: this copy"
                   % (answering["bytes"], answering["mtime"]))
        out.append("    moved twice inside one day, so a fixed hash here would be a stale")
        out.append("    claim rather than a measurement")
        out.append("")
        out.append("Each leg is probed with ITS OWN control and reported on its own row:")
        out.append("")
        out.append("| leg | control | fix marker | old marker | reads |")
        out.append("|---|---|---|---|---|")
        for lg in answering["legs"]:
            out.append("| " + str(lg["leg"]) + " | " + str(lg["control"]) + " | "
                       + str(lg["fixed"]) + " | " + str(lg["old"]) + " | **"
                       + str(lg["state"]) + "** |")
        out.append("")
        out.append("One row per leg because the legs can DISAGREE — on 2026-09-27 this copy")
        out.append("carried the clarify fix and NOT the publisher-fault fix, so a single marker")
        out.append("summarised as one verdict would have cleared the leg it cannot see. A marker")
        out.append("is evidence about the leg it measures, never about the instrument.")
        out.append("")
        hits = [m["slug"] for m in members
                if m.get("reachable") and _under(m["root"], answering["resolved"])]
        if hits:
            out.append("**The tree holding that copy**: "
                       + ", ".join("`" + s + "`" for s in hits)
                       + " — a member's own tree IS the answering path, so that member's")
            out.append("copy reads LIVE in the section 4 column.")
        else:
            out.append("**The tree holding that copy**: NONE of the declared members. The")
            out.append("executing copy sits outside every member root, so no row in section 4")
            out.append("can read LIVE — and a member's own copy, however current it is, is")
            out.append("inert for owner taps.")
        out.append("")

    out.append("## 3. The population")
    out.append("")
    out.append(f"- members declared: **{cov.get('members_declared')}**, "
               f"reachable: **{cov.get('members_reachable')}**")
    if cov.get("members_unreachable"):
        out.append(f"- unreachable: {', '.join('`' + s + '`' for s in cov['members_unreachable'])}")
    out.append(f"- **every manifest cell** ({cov.get('manifest_cells_total')} pairs): "
               f"same {mc.get('same')} · DIFF {mc.get('DIFF')} · ABSENT {mc.get('ABSENT')}")
    out.append(f"- **bootstrap-named subset** ({cov.get('bootstrap_cells_total')} cells, "
               f"the {len(names)} files `TEMPLATE/BOOTSTRAP.md` names): "
               f"same {bc.get('same')} · DIFF {bc.get('DIFF')} · ABSENT {bc.get('ABSENT')}")
    out.append("")
    out.append("Two populations are reported because a number must travel with its own "
               "predicate:")
    out.append("the bootstrap subset is what the earlier 1/20/29 baseline was taken over, "
               "and quoting")
    out.append("only one of them would leave the other unreproducible.")
    out.append("")
    out.append("## 4. Per member — the figure AND the declaration")
    out.append("")
    out.append("| member | same | DIFF | ABSENT | own pin | own copy | zone own/not | declared |")
    out.append("|---|---|---|---|---|---|---|---|")
    decls = {}
    for m in members:
        d = load_declarations(m["slug"])
        decls[m["slug"]] = d
        out.append(_cell_row(m, d, answering))
    out.append("")
    out.append("Four columns carry the point. **own pin** is the member-actionable half: a")
    out.append("member with no pin has no figure of its own, and the DIFF beside it is against")
    out.append("OUR manifest. **own copy** is a DIFFERENT PREDICATE from every figure beside it")
    out.append("— not a comparison of the same bytes but a statement about which copy an")
    out.append("owner's tap REACHES: LIVE (it is that copy), inert (off that path, so it reaches")
    out.append("no owner tap), ABSENT (there is no copy to reach with), or undetermined when the")
    out.append("path itself was not measured. It is read from section 2, so it moves when the")
    out.append("answering path moves and not when a member's tree does. **declared** is when it")
    out.append("last attested. A member that has DECLARED a fork and one that has silently")
    out.append("diverged produce the same figure, and must not read the same — which is why")
    out.append("section 6 carries what each one said.")
    out.append("")
    out.append("## 5. Declared detail")
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
    out.append("## 6. Declared decisions — what each member SAID about its own figure")
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
                    out.append("  - filed on its own tracker: "
                               + ", ".join(f"`{f}`" for f in wave["filed"]))
            out.append("")
    out.append("## 7. Bounds — what this census does not say")
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

    text = render(leg, read_at, answering_path())
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
