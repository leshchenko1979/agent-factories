#!/usr/bin/env python3
r"""Gate: no routing surface names upstream `opencrabs/opencrabs` as a binary ISSUE home.

Origin (issue #454). The owner order of 2026-10-09 retired the issue-routing discriminator:
EVERY OpenCrabs binary issue (runtime behaviour, channels, providers, TUI, memory, tools)
goes to the FORK board `leshchenko1979/opencrabs`; FACTORY issues (tooling, CI, release
automation, process) stay on `leshchenko1979/opencrabs-dev-factory`; upstream
`opencrabs/opencrabs` receives PULL REQUESTS ONLY. That order superseded the 2026-10-03
21:17Z two-stream routing, which had sent BINARY issues upstream.

Four surfaces still carried the retired routing when #454 was filed - `skills/meta-factory/
SKILL.md`, `docs/factory-registry.md`, `evidence/factories.md`, and the registry SOURCE
`registry/factories/opencrabs-dev.json` - and nothing compared them: the rework log's #305
entry states the bound this gate closes, "no gate compares these prose surfaces".

NOT in this gate's subject: the register #761 and the census `FORK_ONLY_SURFACE` predicate.
They decide whether a COMMIT can be ported upstream, never which tracker an issue goes to,
and the 2026-10-09 order left both unchanged. Nothing here reads them.

The property, in two legs
-------------------------
Leg 1, the DEFECT: no CLAIM UNIT in a routing surface may pair the upstream slug with
issue-routing vocabulary (issue, defect, bug, ticket, tracker, intake, triage, filing,
report) unless that same unit declares the destination PRs-only. A claim unit is the
smallest self-contained thing that states a destination: a JSON string VALUE, a markdown
table ROW, or a prose SENTENCE. Two exclusions, both deliberate:

  * an occurrence immediately followed by `#` is an issue REFERENCE - `opencrabs/
    opencrabs#2004`, a note about an EXISTING upstream issue - not a routing claim. The
    gate asks where a NEW issue goes, never whether an old one is mentioned.
  * the exemption is the PRs-only DECLARATION itself (`PRs only`, `PULL REQUESTS ONLY`,
    `pull-requests-only`, `no new issues`). A NEGATION about some other repository is not
    an exemption: the pre-#454 text read "the portfolio `leshchenko1979/opencrabs` is
    READ-ONLY, never an issue home" in the very sentence that sent BINARY defects upstream,
    and accepting that phrase as a marker is what let the headline instance pass a draft of
    this gate. A marker must declare the upstream's own status, not a neighbour's.

Leg 2, the RETIRED CITATIONS: the superseded order's own phrases must not survive as a live
restatement - `two-stream`, `three issue streams`, `FORK-ONLY stream`, and the dated
citation `2026-10-03 21:17Z`.

What this gate cannot do, stated rather than implied
---------------------------------------------------
Its population is the DECLARED list below and nothing else. `evidence/scores/*.md`, the
rework log and the ledger are HISTORY: a dated measurement or a closed item's record may
name the retired order without routing anything, so they are outside the scope by the
population's reason, not by an exemption - and a surface the list omits is not covered.
Move a path into the list deliberately, or it is not judged. Leg 1 is a proximity test
inside a claim unit, not a parse: a unit that pairs the slug with issue vocabulary without
declaring PRs-only is reported, and the report prints the unit so the remedy is a phrase.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The declared population: a LIVE surface that states where an issue GOES. The generated
# registry render and index are listed beside their source because a render is read as law
# by whoever opens it; `TEMPLATE/SKILL.md.tmpl` is listed so the kit cannot carry the
# retired routing into every bootstrapped factory. This gate is NOT in its own population
# (its scope is the surfaces above), so it may name the pattern it forbids.
ROUTING_SURFACES = (
    "skills/meta-factory/SKILL.md",
    "TEMPLATE/SKILL.md.tmpl",
    "docs/factory-registry.md",
    "registry/index.json",
    "registry/state.json",
    "registry/fleet.json",
    "registry/factories/opencrabs-dev.json",
    "evidence/factories.md",
)

UPSTREAM = "opencrabs" + "/" + "opencrabs"
REFERENCE = re.compile(re.escape(UPSTREAM) + r"#\d+")

ISSUE_VOCAB = re.compile(
    r"\b(issues?|defects?|bugs?|tickets?|trackers?|intake|triage|filings?|reports?)\b",
    re.IGNORECASE,
)
# The ORDER's own shape: the destination is declared PRs-only. Each alternative is a phrase
# the aligned surfaces actually carry; a NEGATION about another repo is deliberately absent.
PR_ONLY = re.compile(
    r"pull[\s-]?requests?[\s-]?only"
    r"|prs[\s-]?only"
    r"|no new issues",
    re.IGNORECASE,
)
RETIRED = (
    "two-stream",
    "three issue streams",
    "FORK-ONLY stream",
    "2026-10-03 21:17Z",
)

_JSON_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def claim_units(text: str, suffix: str) -> list[str]:
    """The smallest self-contained statement of a destination, per surface shape."""
    if suffix == ".json":
        return [m.group(1).replace("\\n", " ") for m in _JSON_STRING.finditer(text)]
    units: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.split("\n")
        if any(line.lstrip().startswith("|") for line in lines):
            units.extend(line for line in lines if line.strip())  # one table ROW per unit
            continue
        flat = " ".join(" ".join(lines).split())
        units.extend(s for s in re.split(r"(?<=\.)\s+", flat) if s.strip())
    return units


def unit_problems(unit: str) -> list[str]:
    """Leg 1 over one claim unit."""
    if UPSTREAM not in REFERENCE.sub("", unit):
        return []
    if PR_ONLY.search(unit):
        return []
    hit = ISSUE_VOCAB.search(unit)
    if not hit:
        return []
    return [f"{UPSTREAM} is paired with {hit.group(0)!r} and no PRs-only declaration: "
            f"...{' '.join(unit.split())[:200]}..."]


def routing_problems(text: str, suffix: str = ".md") -> list[str]:
    problems: list[str] = []
    for unit in claim_units(text, suffix):
        problems.extend(unit_problems(unit))
    return problems


def retired_citation_problems(text: str) -> list[str]:
    return [f"the retired citation {p!r} survives here" for p in RETIRED if p in text]


def scan() -> tuple[list[str], int, int, list[str]]:
    problems: list[str] = []
    surfaces = 0
    slugs = 0
    missing: list[str] = []
    for rel in ROUTING_SURFACES:
        path = REPO / rel
        if not path.is_file():
            missing.append(rel)
            continue
        surfaces += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        slugs += len(REFERENCE.sub("", text).split(UPSTREAM)) - 1
        problems.extend(f"{rel}: {p}" for p in routing_problems(text, path.suffix))
        problems.extend(f"{rel}: {p}" for p in retired_citation_problems(text))
    return problems, surfaces, slugs, missing


def probe(name: str, text: str, want: bool, failures: list[str], suffix: str = ".md") -> None:
    got = bool(routing_problems(text, suffix) or retired_citation_problems(text))
    if got != want:
        failures.append(f"probe {name!r}: expected problems={want}, got {got}")
    else:
        print(f"  PASS  {name}")


def _probes() -> list[str]:
    """The POSITIVE CONTROL. Every `want=True` probe is verbatim text that shipped before
    #454 - a gate that never looked cannot pass, so the defect's own bytes must fail it."""
    failures: list[str] = []
    probe(
        "the headline prose block is caught",
        "The harness that this meta-factory and all surveyed factories run on is produced and managed\n"
        "by the **OpenCrabs factory** (Crabs Kanban Board topic `OC DEV HQ`), which works from the source\n"
        "fork `leshchenko1979/opencrabs` and files on **two trackers**: a **BINARY** defect (runtime behaviour,\n"
        "channels, providers, TUI, memory, tools) on `opencrabs/opencrabs`, and a **FACTORY** defect (tooling,\n"
        "CI, release automation, process) on `leshchenko1979/opencrabs-dev-factory` - the portfolio\n"
        "`leshchenko1979/opencrabs` is **READ-ONLY**, never an issue home (owner order 2026-10-03 21:17Z).",
        True, failures,
    )
    probe(
        "the substrate TABLE ROW is caught",
        "| OpenCrabs instruments (daemon, core tools, brain/skill loading) | **OpenCrabs Kanban Board HQ** - lane `opencrabs-dev` / `hq`, topic `OC DEV HQ` (thread 30220), resolved live at dispatch; **binary** issues on `opencrabs/opencrabs`, **factory** issues on `leshchenko1979/opencrabs-dev-factory`, and the portfolio `leshchenko1979/opencrabs` READ-ONLY |",
        True, failures,
    )
    probe(
        "the factories.md line is caught ACROSS a line break",
        "A fork of\n`opencrabs/opencrabs` is the working repo; upstream receives PRs **and binary issue filings**\n(owner order 2026-10-03 21:17Z) - **every** binary issue goes to the fork board `leshchenko1979/opencrabs`.",
        True, failures,
    )
    probe(
        "the upstream table ROW is caught",
        "| `opencrabs/opencrabs` | Upstream - PRs, and the **binary issue tracker** |",
        True, failures,
    )
    probe(
        "the JSON does_not_own VALUE is caught",
        '"upstream opencrabs/opencrabs (the historical alias adolfousier/opencrabs redirects there), since the 2026-10-03 two-stream routing order -- our BINARY issue filings"',
        True, failures, ".json",
    )
    probe(
        "the ORDER's own prose shape is clean",
        "process) on `leshchenko1979/opencrabs-dev-factory`; upstream `opencrabs/opencrabs` receives\n"
        "**PULL REQUESTS ONLY - no new issues** (owner order 2026-10-09, which RETIRED the issue-routing\n"
        "discriminator: the fork takes every binary issue, not only fork-only surfaces).",
        False, failures,
    )
    probe(
        "the aligned substrate ROW is clean",
        "| OpenCrabs instruments (daemon, core tools, brain/skill loading) | **OpenCrabs Kanban Board HQ** - lane `opencrabs-dev` / `hq`, resolved live at dispatch; **binary** issues on the fork board `leshchenko1979/opencrabs`, **factory** issues on `leshchenko1979/opencrabs-dev-factory`, and upstream `opencrabs/opencrabs` PULL-REQUESTS-ONLY |",
        False, failures,
    )
    probe(
        "the aligned upstream ROW is clean",
        "| `opencrabs/opencrabs` | Upstream - **PRs only**, never a binary issue home (owner order 2026-10-09) |",
        False, failures,
    )
    probe(
        "the aligned JSON VALUE is clean",
        '"upstream opencrabs/opencrabs (the historical alias adolfousier/opencrabs redirects there), which receives our PULL REQUESTS ONLY -- no new issues (owner order 2026-10-09)"',
        False, failures, ".json",
    )
    probe(
        "an issue REFERENCE is not a routing claim",
        "do not duplicate it: opencrabs/opencrabs#2004 is tracked upstream",
        False, failures,
    )
    probe(
        "a FORK-board destination is not the upstream slug",
        "**every** binary issue goes to the fork board `leshchenko1979/opencrabs`",
        False, failures,
    )
    probe(
        "a retired citation alone is caught",
        "the two-stream routing order is still cited here",
        True, failures,
    )
    return failures


def main() -> int:
# STATED SKIP: registry/state.json (factory data)
    failures = _probes()
    problems, surfaces, slugs, missing = scan()

    print(f"issue-routing surfaces gate: {surfaces} surface(s), {slugs} {UPSTREAM} routing mention(s) examined")
    for m in missing:
        print(f"  MISSING {m} - a declared routing surface is not in this tree")
    for p in problems:
        print(f"  FAIL  {p}")

    if surfaces == 0:
        # THE SHIPPED DEPTH (#459). This gate derives its subject root from its OWN file's
        # location (`REPO = Path(__file__).resolve().parent.parent`), so the copy the kit
        # ships — `TEMPLATE/tests/test_issue_routing_surfaces.py`, which the shipped audit
        # runs with `cwd=TEMPLATE` — reads `TEMPLATE/` as its REPO. Every declared surface
        # is a LIVE routing surface a BOOTSTRAP creates in a factory, and the tree the kit
        # ships carries none of them: the population is EMPTY rather than clean, and a red
        # here is a property of the DEPTH, not of the tree's routing. Unstated, it surfaced
        # as an unaccounted verdict in `tests/test_shipped_audit_runs.py` (#459). STATED
        # SKIP, never a silent pass — the reason is printed, names the absent surfaces, and
        # is declared in `docs/shipped-audit-skips.json`.
        print(f"issue-routing surfaces gate: SKIPPED — none of the {len(ROUTING_SURFACES)} "
              f"declared routing surface(s) is in this tree, so there is no routing to judge. "
              f"They are factory data the kit does not ship (BOOTSTRAP-created).")
        for m in missing:
            print(f"  ABSENT {m}")
        return 0
    if slugs == 0:
        print("issue-routing surfaces gate FAILED: the scan examined no upstream routing "
              "mention - a clean verdict over an empty population is not a verdict")
        return 1
    if problems or failures or missing:
        print(f"issue-routing surfaces gate FAILED: {len(problems)} problem(s), "
              f"{len(failures)} probe failure(s), {len(missing)} missing surface(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"issue-routing surfaces gate passed - {surfaces} surface(s), {slugs} "
          f"{UPSTREAM} routing mention(s), 0 problem(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
