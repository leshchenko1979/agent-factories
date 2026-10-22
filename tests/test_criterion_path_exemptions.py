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

Two arms are LIVE, and neither judges this factory's store against a live population (#540,
ruling n=4049). The gate judges the MACHINERY on a fixture store and a fixture population, and
the live reconciliation stays where it belongs — `criterion_path_leg` in the patrol, which
reads the real board. What the gate keeps from the live store is the one property the admission
rule promises and nothing checked: every declared entry's `authority` must RESOLVE, to a
`file:line` present in the committed tree or to an `n=` row present in the ledger at HEAD.
"""

from __future__ import annotations

import importlib.util
import json
import re
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

# The fixture population the MACHINERY arm judges over (#540): one undeclared absence and one
# stale entry, both inside the fixture tree. Neither exists on this board — that arm's subject
# is the partition, not this factory's own store.
UNDECLARED_ABSENT = "tools/undeclared-probe.py"
STALE_IN_FIXTURE = "docs/stale-in-fixture.json"

# An `authority` is a CHECKABLE coordinate, not prose: a ruling row (`n=NNN`) or a law
# `file:line` a reader can open. Resolving those against the COMMITTED tree and the ledger at
# HEAD is what keeps the authority arm hermetic — no board read, no network.
AUTHORITY_FILE_LINE = re.compile(
    r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|json|jsonl|txt|toml|yaml|yml|sh)):(\d+)"
)
AUTHORITY_ROW = re.compile(r"\bn=(\d+)")

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

def _authority_coordinates(authority: str) -> list[tuple[str, str, int | None]]:
    """Every checkable coordinate an `authority` names, in the order it names them."""
    found: list[tuple[str, str, int | None]] = []
    for path, line in AUTHORITY_FILE_LINE.findall(authority):
        found.append(("file", path, int(line)))
    for row in AUTHORITY_ROW.findall(authority):
        found.append(("row", row, None))
    return found

def _head_ledger_rows() -> tuple[set[int] | None, str]:
    """The `n` values in the ledger AT HEAD, or `(None, why)` when it cannot be read.

    HEAD and not the working tree: the ledger is shared, another lane appends to it while this
    gate runs, and a verdict that depends on an uncommitted append is reproducible by nobody.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO), "show", "HEAD:./evidence/ledger.jsonl"],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git show HEAD:./evidence/ledger.jsonl could not run: {exc}"
    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        return None, lines[-1] if lines else "git show HEAD:./evidence/ledger.jsonl failed"
    rows: set[int] = set()
    for number, line in enumerate(proc.stdout.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.add(int(json.loads(line)["n"]))
        except (ValueError, KeyError, TypeError):
            return None, f"row {number} of the ledger at HEAD carries no readable `n`"
    return rows, ""

def _coordinate_resolves(kind: str, value: str, line: int | None,
                         ledger_rows: set[int] | None, ledger_why: str) -> tuple[bool, str]:
    """Whether one cited coordinate can actually be opened, and WHY NOT when it cannot."""
    if kind == "row":
        if ledger_rows is None:
            return False, f"the ledger at HEAD could not be read: {ledger_why}"
        if int(value) not in ledger_rows:
            return False, "no row with that number in the ledger at HEAD"
        return True, ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO), "show", f"HEAD:./{value}"],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"git show HEAD:./{value} could not run: {exc}"
    if proc.returncode != 0:
        return False, "the file is not in the committed tree at HEAD"
    total = len(proc.stdout.splitlines())
    if line is not None and line > total:
        return False, f"the file has {total} line(s) at HEAD, so line {line} cannot be opened"
    return True, ""

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

    # --- arm 11: the MACHINERY, judged on a FIXTURE store and a FIXTURE population ------
    # This arm used to reconcile the LIVE store against the LIVE committed tree, over a fixture
    # issue that named exactly the two declared paths — so it judged the store's CONTENTS, not
    # the predicate, and a THIRD lawful exemption red the gate (ruling n=4049, measured:
    # `FAIL — 3 declared but 2 matched a live absence`). Three faults in one shape: a gate whose
    # expectation is a mutable live artifact (rule 7 — the fixture is the control, the live read
    # is corroboration), a surface that cannot grow, and a DUPLICATE of `criterion_path_leg`'s
    # own live reconciliation — which is the defect rather than a second opinion.
    # What it judges now is the PARTITION, in ONE read, over a store and a population that both
    # live in the fixture: no board read, no `gh`.
    cases += 1
    machinery_store = _store_file({"exempt": [
        _entry(LAW_ABSENT),
        _entry(LAW_ABSENT_TWIN, issue=901),
        _entry(STALE_IN_FIXTURE),
    ]})
    leg = _leg(
        module, tree,
        [_issue(900, f"Done when `{LAW_ABSENT}` and `{UNDECLARED_ABSENT}` exist."),
         _issue(901, f"Done when `{LAW_ABSENT_TWIN}` exists."),
         _issue(902, f"Done when `{BLOCKED_ABSENT}` passes."),
         _issue(903, f"Done when `{LAW_ABSENT_TWIN}` exists.")],
        store=machinery_store,
    )
    cov = leg["coverage"]
    # declared-exempt 2 — the declared path on #900, and the NARROWED entry on #901, nothing
    # else. unresolved 4 — the undeclared absence, the blocked absence (which must stay a
    # problem WITH an exemption surface present), #903's spelling of a path the store narrows
    # to #901, and the stale entry, which the leg counts here as well as naming separately.
    if (cov["exemptions_declared"], cov["declared_exempt"], cov["unresolved"]) != (3, 2, 4):
        problems.append(f"arm 11: the partition is wrong: {cov}")
    excused_text = " ".join(leg["excused"])
    for ref in (LAW_ABSENT, LAW_ABSENT_TWIN):
        if ref not in excused_text:
            problems.append(
                f"arm 11: a declared path did not print as excused: {ref} — {leg['excused']}"
            )
    joined = " ".join(leg["problems"])
    for ref in (UNDECLARED_ABSENT, BLOCKED_ABSENT, STALE_IN_FIXTURE):
        if ref not in joined:
            problems.append(
                f"arm 11: a class that must red read clean: {ref} — {leg['problems']}"
            )
    # The narrowing must BIND, both ways: #901's declared path is excused and #903's identical
    # spelling is not. A leg that ignored `issue` would pass a count-only assertion, so the two
    # rows are read one at a time.
    if not any("#903" in p and LAW_ABSENT_TWIN in p for p in leg["problems"]):
        problems.append(
            f"arm 11: a narrowed entry excused another item's identical path: {leg['problems']}"
        )
    for number, ref in ((900, LAW_ABSENT), (901, LAW_ABSENT_TWIN)):
        if any(f"#{number}" in p and f"`{ref}`" in p for p in leg["problems"]):
            problems.append(
                f"arm 11: a DECLARED path was reported as a problem on #{number}: "
                f"{ref} — {leg['problems']}"
            )

    # --- arm 12: every DECLARED entry's AUTHORITY resolves (#540(c)) --------------------
    # The store's own admission rule is an AUTHORITY OBLIGATION — an entry carries "a ruling row
    # `n=` or a law file:line a reader can open" — and nothing checked it, so an entry could
    # cite a row that never existed and still excuse its path. This is the ONE live arm that
    # replaces the content pin, and it is HERMETIC: the committed tree and the ledger AT HEAD,
    # never the board and never the network. An ABSENT store is the shipped state of a member
    # factory (the `.example.json` skeleton is what ships; the real store is factory data), so
    # absence is not a failure here — and deleting the store cannot buy silence, because every
    # absent path then becomes an undeclared PROBLEM in the patrol.
    cases += 1
    if STORE.is_file():
        entries, store_problems = module.load_criterion_path_exemptions(STORE)
        if store_problems:
            problems.append(f"live authority arm: the store does not load: {store_problems}")
        ledger_rows, ledger_why = _head_ledger_rows()
        for entry in entries:
            coordinates = _authority_coordinates(entry["authority"])
            if not coordinates:
                problems.append(
                    f"live authority arm: `{entry['path']}` states an authority that names no "
                    f"file:line and no `n=` row, so no reader can check it: "
                    f"{entry['authority']!r}"
                )
                continue
            for kind, value, line in coordinates:
                resolved, why = _coordinate_resolves(kind, value, line, ledger_rows, ledger_why)
                if not resolved:
                    cited = f"{value}:{line}" if line is not None else f"n={value}"
                    problems.append(
                        f"live authority arm: `{entry['path']}` cites {cited}, which does not "
                        f"resolve: {why}"
                    )

    return problems, cases

def main() -> int:
    if not RUNNER_PATH.is_file():
        print(f"NOT RUN — the reader is absent: {RUNNER_PATH}", file=sys.stderr)
        return 1

    module = load_runner()
    problems, cases = check(module)

    live = "absent (empty state)"
    authorities = "no authority to resolve"
    if STORE.is_file():
        entries, _ = module.load_criterion_path_exemptions(STORE)
        coordinates = sum(len(_authority_coordinates(e["authority"])) for e in entries)
        live = f"{len(entries)} declared exemption(s)"
        authorities = f"{coordinates} authority coordinate(s) resolved against HEAD"

    summary = f"table {live}; {authorities}; probe: {cases} case(s) examined"
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
