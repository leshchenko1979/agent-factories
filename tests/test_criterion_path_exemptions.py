#!/usr/bin/env python3
"""Gate: a path absent BY LAW is exempted by the tree's OWN declaration, and nothing else (#507).

The criterion-path leg resolves every path a board item's criteria name, in the issue BODY and
in the RULING COMMENT, against the COMMITTED tree, and reports each name that resolves to
nothing. The defect this gate was built for is that the leg cannot tell a MISSING file from a
DELIBERATELY UNSHIPPED one: `docs/hygiene-protected.json` never ships
(`skills/meta-factory/SKILL.md:414`), so a criterion naming it is correct and the leg was
wrong to red it. Ruling n=2693 had already returned that half of #422 as NOT UPHELD, which
settles the declaration and leaves the predicate as the thing to repair.

Ruling n=3539 fixed the shape, and this gate is its arm set:

  * an ABSENT path with no declaration is a PROBLEM carrying the remedy, and the population
    prints all three parts — examined, unresolved, declared-exempt — so a green reads as
    examined-minus-exempt and never as examined-nothing;
  * a DECLARED entry excuses its path and PRINTS its reason and its authority, because an
    exemption nobody can check is forgiveness;
  * a path absent because its work is BLOCKED stays a PROBLEM with the declaration in place —
    the distinction is the whole value of the surface, and this arm is the positive control
    that bites both ways (with the entry removed the exempt case reds; with it in place the
    blocked case still reds);
  * an entry matching NOTHING in the live population is an ERROR, because retired debt must
    not sit here looking live;
  * an entry with no `authority`, no `reason`, or a duplicate of another entry is an ERROR and
    excuses nothing — an unreadable exemption would red every adjudicated path while reading
    as an excuse;
  * an ABSENT store is the shipped state of a new factory, never a failure;
  * `issue` narrows an entry to one board item, and a narrowed entry does not excuse another
    item's identical path.

The live arm reconciles this factory's own store against this factory's own committed tree,
so an entry that stops describing the tree reds the audit rather than the patrol alone.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "docs" / "criterion-path-exemptions.json"
RUNNER_PATH = REPO / "tools" / "patrol_host_state.py"

# The two paths ruling n=3539 named as the FIRST entries, and the one it named as the control
# that must NOT be exempted: absent because its work is blocked on the owner design gate
# (ruling n=2360), which is unresolved work rather than law-forbidden absence.
LAW_ABSENT = "docs/hygiene-protected.json"
LAW_ABSENT_TWIN = "TEMPLATE/docs/hygiene-protected.json"
BLOCKED_ABSENT = "TEMPLATE/tests/test_audit_cadence.py"

def load_runner():
    spec = importlib.util.spec_from_file_location("patrol_host_state_criterion", RUNNER_PATH)
    assert spec and spec.loader, f"cannot load {RUNNER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _issue(number: int, body: str, state: str = "OPEN") -> dict:
    return {"number": number, "state": state, "body": body, "comments": []}

def _store_file(payload) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="criterion-paths-gate-"))
    path = directory / "criterion-path-exemptions.json"
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )
    return path

def _temp_tree() -> Path:
    """A committed tree that holds NOTHING the criteria name — the population's base."""
    root = Path(tempfile.mkdtemp(prefix="criterion-paths-tree-"))
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    (root / "README.md").write_text("probe tree\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=probe", "-c", "user.email=probe@example",
         "commit", "-q", "-m", "probe"],
        check=True,
    )
    return root

def _leg(module, tree: Path, issues, *, store=None):
    return module.criterion_path_leg(
        issues, read_at="2026-10-17T00:00:00Z", repo=tree, rev="HEAD",
        exemptions_path=store if store is not None else Path("/nonexistent/store.json"),
    )

def _entry(path: str, *, authority: str = "skills/meta-factory/SKILL.md:414 + ruling n=2693",
           reason: str = "probe: absent by law", issue: int | None = None) -> dict:
    entry = {"path": path, "authority": authority, "reason": reason}
    if issue is not None:
        entry["issue"] = issue
    return entry

def check(module) -> tuple[list[str], int]:
    """Every arm, in one list, plus how many cases this gate examined."""
    problems: list[str] = []
    cases = 0
    tree = _temp_tree()

    # --- arm 1: an ABSENT path with no declaration is a PROBLEM, with the remedy ---------
    cases += 1
    leg = _leg(module, tree, [_issue(900, f"Done when `{LAW_ABSENT}` exists.")])
    if not leg["problems"]:
        problems.append("arm 1: an undeclared absent path read clean")
    elif "dispatch a work item naming" not in " ".join(leg["problems"]):
        problems.append(f"arm 1: the remedy text is gone: {leg['problems']}")
    cov = leg["coverage"]
    if (cov["refs_examined"], cov["unresolved"], cov["declared_exempt"]) != (1, 1, 0):
        problems.append(f"arm 1: the population is not the three-part one: {cov}")

    # --- arm 2: a DECLARED entry excuses the path and PRINTS reason + authority ----------
    cases += 1
    store = _store_file({"exempt": [_entry(LAW_ABSENT)]})
    leg = _leg(module, tree, [_issue(900, f"Done when `{LAW_ABSENT}` exists.")], store=store)
    if leg["problems"]:
        problems.append(f"arm 2: a declared exemption did not excuse: {leg['problems']}")
    if leg["coverage"]["declared_exempt"] != 1 or leg["coverage"]["unresolved"] != 0:
        problems.append(f"arm 2: counts wrong after excusal: {leg['coverage']}")
    if not any("authority: skills/meta-factory/SKILL.md:414" in line for line in leg["excused"]):
        problems.append(f"arm 2: the authority was not printed: {leg['excused']}")

    # --- arm 3: the BLOCKED-absent control still reds WITH the exemption in place --------
    cases += 1
    leg = _leg(
        module, tree,
        [_issue(900, f"Done when `{LAW_ABSENT}` exists and `{BLOCKED_ABSENT}` passes.")],
        store=store,
    )
    if not any(BLOCKED_ABSENT in p for p in leg["problems"]):
        problems.append(
            "arm 3: the blocked-absent path was swallowed by an exemption that does not "
            f"name it: {leg['problems']}"
        )
    if not any(LAW_ABSENT in line for line in leg["excused"]):
        problems.append(f"arm 3: the law-absent path stopped being excused: {leg['excused']}")

    # --- arm 4: an entry matching NOTHING is an ERROR ------------------------------------
    cases += 1
    stale = _store_file({"exempt": [_entry("docs/no-such-criterion-path.json")]})
    leg = _leg(module, tree, [_issue(900, f"Done when `{LAW_ABSENT}` exists.")], store=stale)
    if not any("matches no live absence" in p for p in leg["problems"]):
        problems.append(f"arm 4: a stale exemption read clean: {leg['problems']}")

    # --- arm 5: an entry with no AUTHORITY excuses nothing -------------------------------
    cases += 1
    no_authority = _store_file({"exempt": [
        {"path": LAW_ABSENT, "reason": "probe: no authority"},
    ]})
    entries, store_problems = module.load_criterion_path_exemptions(no_authority)
    if not store_problems or "authority" not in " ".join(store_problems):
        problems.append(f"arm 5: an authority-less entry was honoured or dropped: {store_problems}")
    if entries:
        problems.append(f"arm 5: an authority-less entry became an exemption: {entries}")

    # --- arm 6: an entry with no REASON excuses nothing ----------------------------------
    cases += 1
    no_reason = _store_file({"exempt": [
        {"path": LAW_ABSENT, "authority": "ruling n=2693"},
    ]})
    entries, store_problems = module.load_criterion_path_exemptions(no_reason)
    if not store_problems or "reason" not in " ".join(store_problems):
        problems.append(f"arm 6: a reason-less entry was honoured or dropped: {store_problems}")
    if entries:
        problems.append(f"arm 6: a reason-less entry became an exemption: {entries}")

    # --- arm 7: a DUPLICATE entry is an ERROR, not two exemptions ------------------------
    cases += 1
    duplicate = _store_file({"exempt": [_entry(LAW_ABSENT), _entry(LAW_ABSENT)]})
    entries, store_problems = module.load_criterion_path_exemptions(duplicate)
    if not store_problems or "duplicates" not in " ".join(store_problems):
        problems.append(f"arm 7: a duplicate entry was accepted: {store_problems}")
    if len(entries) != 1:
        problems.append(f"arm 7: a duplicate entry became two exemptions: {entries}")

    # --- arm 8: an ABSENT store is the shipped empty state ------------------------------
    cases += 1
    leg = _leg(module, tree, [_issue(900, f"Done when `{LAW_ABSENT}` exists.")])
    if leg["coverage"]["exemptions_declared"] != 0:
        problems.append(f"arm 8: an absent store declared something: {leg['coverage']}")
    if not leg["problems"]:
        problems.append("arm 8: an absent store silenced the undeclared path")

    # --- arm 9: `issue` narrows an entry to ONE board item ------------------------------
    cases += 1
    narrowed = _store_file({"exempt": [_entry(LAW_ABSENT, issue=900)]})
    leg = _leg(
        module, tree,
        [_issue(900, f"Done when `{LAW_ABSENT}` exists."),
         _issue(901, f"Done when `{LAW_ABSENT}` exists.")],
        store=narrowed,
    )
    if leg["coverage"]["declared_exempt"] != 1 or leg["coverage"]["unresolved"] != 1:
        problems.append(f"arm 9: narrowing did not bind to one item: {leg['coverage']}")
    if not any("#901" in p for p in leg["problems"]):
        problems.append(f"arm 9: the un-narrowed item did not red: {leg['problems']}")

    # --- arm 10: an UNPARSEABLE store cannot silently excuse ----------------------------
    cases += 1
    broken = _store_file("{not json")
    entries, store_problems = module.load_criterion_path_exemptions(broken)
    if not store_problems or entries:
        problems.append(f"arm 10: an unparseable store did not fail closed: {store_problems}")

    # --- arm 11: the LIVE store reconciles against the LIVE committed tree --------------
    # An ABSENT live store is the shipped state of a member factory (the `.example.json`
    # skeleton is what ships; the real store is factory data), so this arm must not red it.
    # The guard it loses by tolerating absence is not the important one: DELETING the store
    # cannot silence the leg, because every absent path then becomes an undeclared PROBLEM
    # — the failure mode of a missing store is a RED patrol, never a green one.
    cases += 1
    if STORE.is_file():
        leg = module.criterion_path_leg(
            [_issue(900, f"Done when `{LAW_ABSENT}` and `{LAW_ABSENT_TWIN}` exist.")],
            read_at="gate", repo=REPO, rev="HEAD", exemptions_path=STORE,
        )
        cov = leg["coverage"]
        if cov["exemptions_declared"] != cov["declared_exempt"]:
            problems.append(
                f"live arm: {cov['exemptions_declared']} declared but "
                f"{cov['declared_exempt']} matched a live absence — a stale entry excuses "
                f"nothing: {leg['problems']}"
            )
        if cov["unresolved"]:
            problems.append(
                f"live arm: {cov['unresolved']} undeclared absent path(s) among the "
                f"declared set: {leg['problems']}"
            )

    return problems, cases

def main() -> int:
    if not RUNNER_PATH.is_file():
        print(f"NOT RUN — the reader is absent: {RUNNER_PATH}", file=sys.stderr)
        return 1

    module = load_runner()
    problems, cases = check(module)

    live = "absent (empty state)"
    population = "0 reference(s)"
    if STORE.is_file():
        leg = module.criterion_path_leg(
            [_issue(900, f"Done when `{LAW_ABSENT}` and `{LAW_ABSENT_TWIN}` exist.")],
            read_at="gate", repo=REPO, rev="HEAD", exemptions_path=STORE,
        )
        cov = leg["coverage"]
        live = f"{cov['exemptions_declared']} declared exemption(s)"
        population = (
            f"{cov['refs_examined']} reference(s) examined, {cov['unresolved']} unresolved, "
            f"{cov['declared_exempt']} declared-exempt"
        )

    summary = f"table {live}; {population}; probe: {cases} case(s) examined"
    if problems:
        print(f"FAIL — {summary}", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nAn exemption is a DECLARED adjudication with an AUTHORITY: name the path, "
            "state why the law forbids it, and cite the ruling or the file:line a reader "
            "can open. Fix the store or fix the criterion — never leave a path excused by "
            "an entry nobody can check.",
            file=sys.stderr,
        )
        return 1

    print(f"PASS — {summary}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
