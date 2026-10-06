#!/usr/bin/env python3
"""Gate: a commit may not name a mechanism that does not exist at that commit.

The class (issue #48, ruled 2026-09-26): a law surface names an upholding
mechanism in prose, and nothing checks that the mechanism exists. P29's own gate
reads only the enumerated `## PN —` mapping, so a clause added to a law *section*
names its mechanism invisibly to it. Measured near-miss: commit `500e1b6` landed
law text naming `tests/test_ledger_commit_cites_no_rows.py`, the file did not
exist at that commit, and `tools/audit.py` read HEALTHY throughout — the file
appeared four minutes later, by the author's own diligence and not by any gate.

The rule is a property of the COMMIT, and the commit is the object — the same
shape `tools/hooks/pre-commit` already applies to the kit manifest. It reads one
commit against its own tree and needs no history-wide form:

  a commit that modifies a law surface and INTRODUCES a mechanism reference
  (`tests/*.py`, `tools/*.py`, and their `TEMPLATE/` twins) which does not exist
  in the index — i.e. which will not exist after the commit — is refused.

Only ADDED lines are read, so a law file's pre-existing references (which do
resolve, or an earlier commit would have failed) never red the rule: the defect
is an INTRODUCED name, and the fix is to stage the mechanism in the same commit.

Prevention lives in the hook; the predicate lives here, and both call sites load
this one function, because two implementations drift and the drift is silent.

Run:  python3 tests/test_law_mechanism_same_commit.py
Exit: 0 the probe holds and the wiring is present, 1 otherwise.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The surfaces a law clause is written on. A factory law lives under
# `skills/<name>/`, and the template ships the same law at `TEMPLATE/`; the
# canonical vocabulary and the process register are law by declaration.
#
# THE SUFFIX IS NOT DECORATION, and this rule was caught by its own defect class
# before it landed. A bare `TEMPLATE/` prefix makes every shipped CODE file a law
# surface, and a rule that reads docstrings and probe fixtures as law refuses the
# commits that build it: measured on this item's own commit, `TEMPLATE/tools/
# patrol_host_state.py` "named" `tests/test_x.py` and `TEMPLATE/tests/test_patrol_
# host_state.py` "named" `tests/test_ghost.py` — both example paths in a docstring,
# both absent, both would have been refused. The class is a LAW clause naming its
# mechanism, so the surface must be LAW TEXT: markdown and the `.tmpl` templates a
# factory ships. The item's own near-miss touched `TEMPLATE/SKILL.md.tmpl`, which
# this predicate keeps.
LAW_PREFIXES = ("skills/", "TEMPLATE/")
LAW_FILES = ("ONTOLOGY.md", "docs/processes.md", "docs/best-practices.md")
LAW_SUFFIXES = (".md", ".md.tmpl", ".tmpl")

# A mechanism reference: a Python path under `tests/` or `tools/`, with or
# without the `TEMPLATE/` prefix a shipped law file uses for its twin.
MECHANISM_REF = re.compile(r"\b((?:TEMPLATE/)?(?:tests|tools)/[A-Za-z0-9_./-]+\.py)\b")

# The two call sites the wiring leg asserts. A predicate with no caller is dead
# text (P29), and the hook is the only point that PREVENTS rather than detects.
HOOK_RELATIVE = "tools/hooks/pre-commit"
AUDIT_RELATIVE = "tools/audit.py"
SELF_RELATIVE = "tests/test_law_mechanism_same_commit.py"

def _git(top: Path, *args: str) -> str | None:
    """Run git in `top`; None when it cannot be read (the leg fails OPEN)."""
    proc = subprocess.run(
        ["git", "-C", str(top), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return None
    return proc.stdout

def is_law_surface(path: str) -> bool:
    """True for a file a law clause may be written on.

    LAW TEXT ONLY. A `.py` file under `TEMPLATE/` is shipped code, not law, and a rule that
    reads it as law refuses ordinary implementation commits — see the suffix note above.
    """
    if path in LAW_FILES:
        return True
    if not path.endswith(LAW_SUFFIXES):
        return False
    return any(path.startswith(prefix) for prefix in LAW_PREFIXES)

def added_lines(top: Path, path: str) -> list[str] | None:
    """The lines this commit ADDS to `path`, or None when the diff cannot be read."""
    diff = _git(top, "diff", "--cached", "--unified=0", "--", path)
    if diff is None:
        return None
    out: list[str] = []
    for line in diff.splitlines():
        # A hunk header is `@@ ... @@`; a `+++`/`---` header is not content, and a
        # `-` line is a removal. Only `+` lines are the commit's introduction.
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            out.append(line[1:])
    return out

def introduced_refs(top: Path, staged: list[str]) -> list[tuple[str, str]]:
    """`(law_surface, reference)` pairs this commit INTRODUCES, sorted."""
    pairs: list[tuple[str, str]] = []
    for path in staged:
        if not is_law_surface(path):
            continue
        lines = added_lines(top, path)
        if lines is None:
            continue
        for line in lines:
            for ref in MECHANISM_REF.findall(line):
                pairs.append((path, ref))
    return sorted(set(pairs))

def missing_at_commit(top: Path, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The pairs whose reference will NOT exist after this commit.

    The index IS the pending commit's tree: a path staged for addition is present
    in it, and a path staged for deletion is absent from it, so this reads the
    commit and never the working tree (P37).
    """
    listed = _git(top, "ls-files", "--cached", "-z")
    if listed is None:
        return []  # fail OPEN: an unreadable index is not a defect in the commit
    present = {p for p in listed.split("\0") if p}
    return [(law, ref) for law, ref in pairs if ref not in present]

def law_mechanism_problems(top: Path, staged: list[str]) -> list[str]:
    """The one predicate both call sites load. Empty list == the commit is clean."""
    missing = missing_at_commit(top, introduced_refs(top, staged))
    return [
        f"{law} names {ref} — absent at this commit (stage it in the same commit)"
        for law, ref in missing
    ]

def _gate_registry():
    """The tree's OWN audit-registration parser — the independent declaration.

    REGISTERED cannot be judged by a substring over the audit: a `gates_to_run.append`
    swapped for a bare `pass` leaves the filename sitting in the dead `if … .is_file():`
    above it, and a substring check reads that as registered. Measured on this rule's own
    wiring — that mutation left `wiring_problems()` empty. The parser below reads the
    APPEND's argv, so the declaration is the registration and not a name that happens to
    occur in the file.
    """
    spec = importlib.util.spec_from_file_location(
        "oc_gate_registry_for_law_mechanism", REPO / "tests" / "gate_registry.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def wiring_problems() -> list[str]:
    """The rule must be REGISTERED and WIRED, or it is dead text (P29)."""
    problems: list[str] = []
    try:
        registry = _gate_registry()
        audit = (REPO / AUDIT_RELATIVE).read_text(encoding="utf-8", errors="replace")
        targets = {entry["target"] for entry in registry.registration_entries(audit)}
    except Exception as exc:  # an unreadable declaration is not a clean one
        return [f"the audit's registration could not be read — {type(exc).__name__}: {exc}"]
    if SELF_RELATIVE not in targets:
        problems.append(
            f"{SELF_RELATIVE} is not REGISTERED in {AUDIT_RELATIVE} — no "
            f"`gates_to_run.append` names it, so nothing runs this rule"
        )
    hook = (REPO / HOOK_RELATIVE).read_text(encoding="utf-8", errors="replace")
    if "law_mechanism_problems(" not in hook:
        problems.append(
            f"{HOOK_RELATIVE} does not CALL the predicate — the rule detects, never prevents"
        )
    return problems

def _probe() -> list[str]:
    """Show the rule BITES, in a throwaway repo, never on this tree (ruling c1).

    `probe 5 case(s) held` — five cases: the defect (law names an absent mechanism)
    fails; the control (the mechanism is staged in the same commit) passes; a law
    file's PRE-EXISTING reference to an absent path is not re-reported, because only
    introduced names are read; the same reference NEWLY introduced IS reported; and a
    `.py` file under a law PREFIX is not a law surface at all.
    """
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        top = Path(tmp)
        env = ["-c", "user.email=probe@example.invalid", "-c", "user.name=probe"]
        _git(top, "init", "-q")
        (top / "skills").mkdir()
        law = top / "skills" / "SKILL.md"
        law.write_text("# law\n\nno mechanism yet\n", encoding="utf-8")
        _git(top, *env, "add", "-A")
        _git(top, *env, "commit", "-q", "-m", "seed")

        # 1. THE DEFECT: the law now names a mechanism that does not exist.
        law.write_text("# law\n\nsee `tests/test_ghost.py`\n", encoding="utf-8")
        _git(top, "add", "-A")
        staged = _git(top, "diff", "--cached", "--name-only").split()
        if not law_mechanism_problems(top, staged):
            problems.append("an introduced reference to an absent mechanism was NOT reported")

        # 2. THE CONTROL: the mechanism is staged in the same commit.
        (top / "tests").mkdir()
        (top / "tests" / "test_ghost.py").write_text("# gate\n", encoding="utf-8")
        _git(top, "add", "-A")
        staged = _git(top, "diff", "--cached", "--name-only").split()
        if law_mechanism_problems(top, staged):
            problems.append("a commit whose reference RESOLVES was reported as a problem")

        _git(top, *env, "commit", "-q", "-m", "land the mechanism")

        # 3. THE PRE-EXISTING CASE: a law file that ALREADY names an absent path is
        #    not re-reported when a later commit edits it for another reason. Only
        #    INTRODUCED names are read, so a resolved-in-an-earlier-life reference
        #    cannot red every later commit to the file.
        (top / "docs").mkdir()
        register = top / "docs" / "processes.md"
        register.write_text("# register\n\nsee `tools/ghost_tool.py`\n", encoding="utf-8")
        _git(top, *env, "add", "-A")
        _git(top, *env, "commit", "-q", "-m", "a law file that names an absent mechanism")
        register.write_text(
            "# register\n\nsee `tools/ghost_tool.py`\n\nan unrelated edit\n",
            encoding="utf-8",
        )
        _git(top, "add", "-A")
        staged = _git(top, "diff", "--cached", "--name-only").split()
        if law_mechanism_problems(top, staged):
            problems.append("a PRE-EXISTING absent reference was re-reported")

        # 4. THE NEWLY-ADDED CASE: the same reference, introduced BY this commit,
        #    IS reported — the rule reads an introduction, not a file's mere presence.
        _git(top, *env, "commit", "-q", "-m", "the unrelated edit")
        (top / "skills" / "other").mkdir()
        (top / "skills" / "other" / "SKILL.md").write_text(
            "# more law\n\nsee `tools/ghost_tool.py`\n", encoding="utf-8"
        )
        _git(top, "add", "-A")
        staged = _git(top, "diff", "--cached", "--name-only").split()
        if not law_mechanism_problems(top, staged):
            problems.append("a NEWLY INTRODUCED absent reference was NOT reported")

        # 5. THE CODE-FILE CASE: a `.py` file under `TEMPLATE/` is SHIPPED CODE, not a law
        #    surface, and reading it as one refuses ordinary implementation commits. This
        #    case is not hypothetical — it was measured on this rule's own landing commit,
        #    where `TEMPLATE/tools/patrol_host_state.py` and its probe "named" the example
        #    paths `tests/test_x.py`, `tools/y.py` and `tests/test_ghost.py` in their own
        #    docstrings and every one of them read as an absent mechanism.
        _git(top, *env, "commit", "-q", "-m", "settle")
        (top / "tools").mkdir(exist_ok=True)
        (top / "tools" / "shipped.py").write_text(
            "# a shipped tool; its docstring says `tests/test_x.py` as an example\n",
            encoding="utf-8",
        )
        _git(top, "add", "-A")
        staged = _git(top, "diff", "--cached", "--name-only").split()
        if law_mechanism_problems(top, staged):
            problems.append(
                "a CODE file under a law PREFIX was read as a law surface — it names an "
                "example path in its own docstring and the commit was refused"
            )
    return problems

def main() -> int:
    problems = _probe() + wiring_problems()
    if problems:
        print("law/mechanism same-commit rule is not upheld:\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(
        "law/mechanism same-commit rule: probe 5 case(s) held, predicate wired at "
        f"{HOOK_RELATIVE} and registered in {AUDIT_RELATIVE}"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
