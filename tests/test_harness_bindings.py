#!/usr/bin/env python3
"""Gate: every law file this repo ships is DECLARED, and every declared source exists (P29).

Origin (issue #79, ruled at ledger `n=531`, dispatched at `n=532`). The template
prescribes a profile skill symlink (`BOOTSTRAP.md`, the harness-link step) and shipped NO
mechanism anywhere that verified it: a factory could bootstrap, pass every gate, and have
its law never load at runtime. That is a P29 gap -- a codified law with no active process
and no deterministic gate upholding it.

The surface is a DECLARED BINDING MANIFEST in the factory's OWN repo, at
`docs/harness-bindings.json` (`docs/harness-bindings.example.json` ships as the skeleton).
The repo's own `skills/` directory cannot be the surface: a derivation sees only what
EXISTS, and the property under test is that something is OWED -- the repo `skills/`
directory is empty exactly when the factory has not yet created a load path, so a gate
keyed on it returns the empty set and passes on the one case that motivated the finding.
A declaration is the only form that can owe.

Row shape, one per bound skill: `skill` (the profile entry name), `repo_path` (relative to
the repo root), `form` (`dir` or `file`). A row may carry `loaded: false` with a `reason`
to record a law that is deliberately not bound. The profile name is a DECLARED FACTORY
PARAMETER carried once at the top of the file, so a second factory declares its own
without editing this gate.

Three legs
----------
* **LEG A, COVERAGE** -- the load-bearing one. DISCOVER every law file the repo ships,
  PRINT the discovered set on every run, and RED naming every discovered law file that no
  binding row covers. It fires on BOTH admissible layouts: a root-level `SKILL.md` (the
  ai-antispam shape, a repo with no `skills/` directory at all) and a `SKILL.md` inside a
  declared skill directory. A discovered set of zero PRINTS as zero, so found-nothing and
  clean are never the same output.
* **LEG B, FORWARD** -- every declared `repo_path` exists and carries a `SKILL.md`; and,
  WHEN a profile root is supplied, the profile load path is a SYMLINK whose realpath equals
  the declared source realpath (form `dir`: `skills/<skill>` is the symlink; form `file`:
  `skills/<skill>` is a real directory and `skills/<skill>/SKILL.md` is the symlink). A
  plain directory or plain file where a symlink is owed is the copy-not-link defect class.
* **LEG C, DISPOSITIONS** -- bound; or `loaded: false` with a reason, PRINTED as excused;
  or uncovered, FAIL naming the path.

THE LIVE PROFILE LEG IS NOT IN THIS GATE. No offline gate can reach a surface outside the
tree, so the live binding is upheld by a PATROL (the surveys lane, one named owner per
P30), whose product is a required section of the measurement artifact. This gate reads a
profile root only when one is SUPPLIED (a fixture, or a patrol that points it at the live
profile); with none supplied the profile leg is EXCUSED with its reason, never silently
passed.

Run:  python3 tests/test_harness_bindings.py    (exit 0 clean/skip, 1 a problem)
      python3 -m pytest tests/test_harness_bindings.py -q
"""

from __future__ import annotations

import json
import os
import posixpath
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DECLARATION_REL = "docs/harness-bindings.json"
DECLARATION_EXAMPLE_REL = "docs/harness-bindings.example.json"
LAW_BASENAME = "SKILL.md"
PRUNE_DIRS = frozenset({".git", "TEMPLATE", ".venv", "node_modules", "__pycache__", ".pytest_cache"})
PROFILE_ROOT_ENV = "OC_HARNESS_PROFILE_ROOT"
FORMS = ("dir", "file")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from declared_surface import GateError, SkipGate, load_declared_json  # noqa: E402

# --- discovery: the law files THIS repo ships ------------------------------------

def discover_law_files(repo: Path) -> list[str]:
    """Every `SKILL.md` the repo ships, repo-relative and sorted.

    A filesystem walk with the prune set applied, never `git ls-files`: a tracked-only
    reader cannot see a law file that is still UNCOMMITTED, so the leg would read GREEN in
    the very worktree that added the undeclared file and RED in the clone of the commit
    being pushed -- the same gate, two verdicts (#207).
    """
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        if LAW_BASENAME in filenames:
            rel = Path(dirpath).relative_to(repo) / LAW_BASENAME
            out.append(rel.as_posix())
    return sorted(out)

def _norm(path: str) -> str:
    return posixpath.normpath(path.strip().lstrip("./")) if path.strip() not in (".", "") else "."

def _covered_law(row: dict) -> str:
    """The law file a binding row covers, as a repo-relative path.

    form `dir` covers `<repo_path>/SKILL.md` (and `.`/`""` covers the root-level
    `SKILL.md`); form `file` covers `repo_path` itself.
    """
    repo_path = _norm(str(row.get("repo_path", "")))
    if row.get("form") == "file":
        return repo_path
    if repo_path in (".", ""):
        return LAW_BASENAME
    return f"{repo_path}/{LAW_BASENAME}"

# --- the predicate ----------------------------------------------------------------

def _row_problems(repo: Path, row: dict, profile_root: Path | None) -> tuple[list[str], str]:
    """`(problems, disposition-line)` for ONE binding row, or `([], "")` when it is clean."""
    problems: list[str] = []
    skill = row.get("skill")
    if not isinstance(skill, str) or not skill.strip():
        return ["a binding row has no `skill` (the profile entry name)"], ""
    if row.get("form") not in FORMS:
        return [f"{skill}: `form` must be one of {FORMS}, got {row.get('form')!r}"], ""
    repo_path = row.get("repo_path")
    if not isinstance(repo_path, str) or not repo_path.strip():
        return [f"{skill}: a binding row has no `repo_path`"], ""

    source = repo / repo_path
    if row["form"] == "dir":
        if not source.is_dir():
            problems.append(f"{skill}: declared source {repo_path!r} is not a directory")
        elif not (source / LAW_BASENAME).is_file():
            problems.append(f"{skill}: declared source {repo_path!r} carries no {LAW_BASENAME}")
    else:
        if not source.is_file():
            problems.append(f"{skill}: declared source {repo_path!r} is not a file")
        elif source.name != LAW_BASENAME:
            problems.append(f"{skill}: a `file` binding must point at a {LAW_BASENAME}, got {source.name!r}")

    # LEG B, the profile half: only when a root is SUPPLIED. Never a silent pass otherwise.
    if profile_root is not None:
        entry = profile_root / "skills" / skill
        target = source.resolve()
        if row["form"] == "dir":
            if not entry.is_symlink():
                problems.append(
                    f"{skill}: profile load path {entry} must be a SYMLINK to {repo_path!r} "
                    f"(a plain directory is the copy-not-link defect)"
                )
            elif entry.resolve() != target:
                problems.append(
                    f"{skill}: profile load path {entry} resolves to {entry.resolve()}, "
                    f"not the declared source {target}"
                )
        else:
            if entry.is_symlink():
                problems.append(
                    f"{skill}: form `file` needs {entry} to be a REAL DIRECTORY carrying a "
                    f"{LAW_BASENAME} symlink, not a symlink itself"
                )
            elif not entry.is_dir():
                problems.append(f"{skill}: form `file` needs {entry} to be a real directory")
            else:
                leaf = entry / LAW_BASENAME
                if not leaf.is_symlink():
                    problems.append(
                        f"{skill}: {leaf} must be a SYMLINK to the declared source {repo_path!r} "
                        f"(a plain file is the copy-not-link defect)"
                    )
                elif leaf.resolve() != target:
                    problems.append(f"{skill}: {leaf} resolves to {leaf.resolve()}, not {target}")

    if row.get("loaded", True) is False:
        reason = row.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"{skill}: `loaded: false` must carry a `reason`")
            return problems, ""
        return problems, f"{skill}: deliberately unloaded — {reason}"
    return problems, f"{skill}: bound -> {repo_path} ({row['form']})"

def evaluate(
    repo: Path, profile_root: Path | None = None
) -> tuple[str, str, list[str], list[str], list[str], list[str]]:
    """`(status, reason, problems, excused, discovered, bound)` over `repo` — the core.

    `status` is `"pass"`, `"skip"` or `"fail"`. A real problem always outranks a skip, and
    a SHIPPED law file is never hidden behind an absent declaration: the declaration reader
    skips, but a skip is only lawful when the tree ships nothing to judge.
    """
    discovered = discover_law_files(repo)
    try:
        data = load_declared_json(repo, DECLARATION_REL, DECLARATION_EXAMPLE_REL, "harness-binding")
    except SkipGate as exc:
        if discovered:
            return (
                "fail",
                "",
                [
                    f"{law}: shipped law file with no binding row, and {DECLARATION_REL} "
                    f"does not exist — {exc}"
                    for law in discovered
                ],
                [],
                discovered,
                [],
            )
        return "skip", str(exc), [], [], discovered, []
    except GateError as exc:
        return "fail", "", list(exc.problems), [], discovered, []

    problems: list[str] = []
    profile = data.get("profile")
    if not isinstance(profile, str) or not profile.strip():
        problems.append(f"{DECLARATION_REL}: a `profile` (the declared factory parameter) is required")
    rows = data.get("bindings")
    if not isinstance(rows, list):
        problems.append(f"{DECLARATION_REL}: `bindings` must be a list")
        return "fail", "", problems, [], discovered, []

    excused: list[str] = []
    bound: list[str] = []
    covered: set[str] = set()
    if profile_root is None and rows:
        excused.append(
            f"profile leg NOT RUN — no profile root supplied (set {PROFILE_ROOT_ENV} to check "
            f"the live binding); the surveys patrol upholds the live leg"
        )
    for row in rows:
        if not isinstance(row, dict):
            problems.append(f"{DECLARATION_REL}: every binding row must be a JSON object")
            continue
        row_problems, disposition = _row_problems(repo, row, profile_root)
        problems += row_problems
        if disposition:
            (bound if row.get("loaded", True) is not False else excused).append(disposition)
        covered.add(_covered_law(row))

    problems += [
        f"law file not covered by any binding row: {law}" for law in discovered if law not in covered
    ]
    if problems:
        return "fail", "", problems, excused, discovered, bound
    if not discovered and not rows:
        return "skip", "this tree ships no law file and declares no binding row", [], excused, discovered, bound
    return "pass", "", [], excused, discovered, bound

# --- the live gate -----------------------------------------------------------------

def _live_verdict():
    root = os.environ.get(PROFILE_ROOT_ENV)
    profile_root = Path(root) if root else None
    status, reason, problems, excused, discovered, bound = evaluate(REPO, profile_root)
    for line in excused:
        print(f"  excused: {line}")
    print(f"  discovered law file(s): {len(discovered)}" + (f" — {', '.join(discovered)}" if discovered else ""))
    for line in bound:
        print(f"  bound: {line}")
    if status == "skip":
        print(f"  SKIP: {reason}")
        pytest.skip(reason)
    if status == "fail":
        raise AssertionError(
            "every law file this repo ships must be DECLARED in "
            f"{DECLARATION_REL}, and every declared source must exist:\n  " + "\n  ".join(problems)
        )
    return discovered, bound

def test_live_law_files_are_declared() -> None:
    """The discovered set is PRINTED, never asserted to a constant: it is a property of the tree."""
    discovered, bound = _live_verdict()
    print(
        f"harness-binding gate: {len(discovered)} law file(s) discovered, {len(bound)} bound row(s); "
        f"every discovered law file is covered by a declaration"
    )

# --- probes: the tree the gate runs in, then the predicate it applies --------------

def _write_declaration(repo: Path, profile: str, bindings: list[dict]) -> None:
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / DECLARATION_REL).write_text(
        json.dumps({"profile": profile, "bindings": bindings}), encoding="utf-8"
    )

def _symlink(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)

def test_probe_a_shipped_law_file_with_no_binding_row_fails(tmp_path: Path) -> None:
    """The ai-antispam shape: a root-level SKILL.md and no binding row (#79 answer 2)."""
    (tmp_path / LAW_BASENAME).write_text("# law\n", encoding="utf-8")
    _write_declaration(tmp_path, "ops", [])
    status, _, problems, _, discovered, _ = evaluate(tmp_path)
    assert status == "fail", problems
    assert discovered == [LAW_BASENAME]
    assert any(LAW_BASENAME in p for p in problems), problems

def test_probe_a_shipped_law_file_with_no_declaration_at_all_fails(tmp_path: Path) -> None:
    """No declaration is NOT a skip while the tree ships a law file — the whole gap."""
    (tmp_path / "skills" / "widget").mkdir(parents=True)
    (tmp_path / "skills" / "widget" / LAW_BASENAME).write_text("# law\n", encoding="utf-8")
    status, _, problems, _, _, _ = evaluate(tmp_path)
    assert status == "fail", problems
    assert any("skills/widget/SKILL.md" in p for p in problems), problems

def test_probe_a_plain_directory_where_a_symlink_is_owed_fails(tmp_path: Path) -> None:
    """LEG B's copy-not-link class: the profile entry is a REAL directory, not a symlink."""
    (tmp_path / "skills" / "widget").mkdir(parents=True)
    (tmp_path / "skills" / "widget" / LAW_BASENAME).write_text("# law\n", encoding="utf-8")
    _write_declaration(tmp_path, "ops", [{"skill": "widget", "repo_path": "skills/widget", "form": "dir"}])
    profile = tmp_path / "profile"
    (profile / "skills" / "widget").mkdir(parents=True)  # a plain directory, not a symlink
    status, _, problems, _, _, _ = evaluate(tmp_path, profile)
    assert status == "fail", problems
    assert any("must be a SYMLINK" in p for p in problems), problems

def test_probe_a_resolving_symlink_passes(tmp_path: Path) -> None:
    """The healthy binding: dir form, the profile entry a symlink to the declared source."""
    (tmp_path / "skills" / "widget").mkdir(parents=True)
    (tmp_path / "skills" / "widget" / LAW_BASENAME).write_text("# law\n", encoding="utf-8")
    _write_declaration(tmp_path, "ops", [{"skill": "widget", "repo_path": "skills/widget", "form": "dir"}])
    profile = tmp_path / "profile"
    _symlink(tmp_path / "skills" / "widget", profile / "skills" / "widget")
    status, _, problems, _, _, bound = evaluate(tmp_path, profile)
    assert status == "pass", problems
    assert bound and "widget" in bound[0]

def test_probe_a_deliberately_unloaded_row_is_excused_not_a_pass(tmp_path: Path) -> None:
    (tmp_path / LAW_BASENAME).write_text("# law\n", encoding="utf-8")
    _write_declaration(
        tmp_path, "ops", [{"skill": "widget", "repo_path": LAW_BASENAME, "form": "file", "loaded": False, "reason": "adopted later"}]
    )
    status, _, problems, excused, _, bound = evaluate(tmp_path)
    assert status == "pass", problems
    assert not bound
    assert any("deliberately unloaded" in e for e in excused), excused

def test_probe_a_malformed_declaration_fails_rather_than_skipping(tmp_path: Path) -> None:
    (tmp_path / LAW_BASENAME).write_text("# law\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / DECLARATION_REL).write_text("{not json", encoding="utf-8")
    status, _, problems, _, _, _ = evaluate(tmp_path)
    assert status == "fail", problems
    assert any("not JSON" in p for p in problems), problems

def test_probe_a_tree_with_nothing_to_judge_skips(tmp_path: Path) -> None:
    status, reason, problems, _, discovered, _ = evaluate(tmp_path)
    assert status == "skip", problems
    assert discovered == []
    assert reason

def test_probe_the_discovered_set_is_never_silently_empty(tmp_path: Path) -> None:
    """A discovered set of zero PRINTS as zero — found-nothing is never a clean verdict."""
    (tmp_path / "skills" / "widget").mkdir(parents=True)
    (tmp_path / "skills" / "widget" / LAW_BASENAME).write_text("# law\n", encoding="utf-8")
    _write_declaration(tmp_path, "ops", [])
    _, _, _, _, discovered, _ = evaluate(tmp_path)
    assert discovered == ["skills/widget/SKILL.md"]

def main() -> int:
    root = os.environ.get(PROFILE_ROOT_ENV)
    profile_root = Path(root) if root else None
    status, reason, problems, excused, discovered, bound = evaluate(REPO, profile_root)
    print(f"discovered law file(s): {len(discovered)}")
    for law in discovered:
        print(f"  {law}")
    for line in excused:
        print(f"  excused: {line}")
    for line in bound:
        print(f"  bound: {line}")
    if status == "skip":
        print(f"harness-binding gate: SKIP: {reason}")
        return 0
    if status == "fail":
        print("harness-binding gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"harness-binding gate: clean — {len(discovered)} law file(s) discovered and every one "
        f"covered; {len(bound)} bound row(s)"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
