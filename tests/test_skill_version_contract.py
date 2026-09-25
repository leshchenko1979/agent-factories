#!/usr/bin/env python3
"""Gate: a commit that changes a law file's BODY must move the skill's version line.

Origin (issue #71, ruled at ledger `n=455`). The Delegate reported that
`git log -S "version: 0.1."` returned exactly ONE commit ever touching the version line,
and concluded the field never moves. The pickaxe counts OCCURRENCES, so a VALUE SWAP
(`0.1.0` -> `0.1.1`) leaves the count unchanged and is invisible to it — a count taken by
a pattern is not a count of items. Measured properly — walking every commit that touches a
discovered law file and diffing that file's frontmatter against its body, over BOTH law
files, 2026-09-20T04:58:08Z: **99 commits, of which 92 moved the LAW BODY without moving
the version** (44 in `TEMPLATE/SKILL.md.tmpl`, 48 in `skills/meta-factory/SKILL.md`), 3
moved both, and exactly ONE — `5fcf624c`, `0.1.0` -> `0.1.1` — moved the version with NO
body change. The decoupling runs BOTH ways, which is why the gate carries TWO arms.

**Why the field is a contract, not a formality (n=455 clause 2).** The fleet's own
practice settles it: `oc-drift-check` reads the version line from the canonical `SKILL.md`
and returns DRIFT when a lane's claimed version differs, and the skill-change notify law
requires a reload brief on every bump. A version-keyed staleness check reading a field
that does not move reports "no drift" for a law that changed — the exact failure the check
exists to prevent. Presence-scoring would make the third clause of that check
unimplementable by construction.

**The rule — TWO ARMS (n=484 clause 1), because one arm leaves the mirror defect open.**
For every commit after the declared boundary that touches a law file: **arm 1** — if the
law BODY changed, the version line must have moved in the SAME commit; **arm 2** — if the
version line moved, the law BODY must have changed in the SAME commit. Arm 1 alone catches
the unbumped body changes; arm 2 catches `5fcf624c`, which moved `0.1.0` -> `0.1.1` with NO
body change and minted a version range with no content — the mirror of the ambiguity the
contract exists to remove. Together the arms force the version and the body to move
together, which is what a field naming the bytes means. Per n=528 the arms apply **PER
FILE**: both law files are in scope and each carries its own version, because the two are
not byte-paired (`test_template_sync.py` pairs tools and tests files only — `SKILL.md.tmpl`
appears in none of them), so a shared version field would name two different bodies at once.

**The predicate is a BYTE change, never a semantic judgement (n=484 clause 3).** A gate
cannot judge "was this a substantive law change", and a rule needing judgement is dead text
(P29). Deleting a duplicated paragraph IS a body change and DOES require a bump: a lane
holding the old copy genuinely has different bytes. Nothing is backfilled — the historical
decouplings are grandfathered by the boundary, and a repair written after the fact would be
a falsified record rather than a repair.

**The BODY is defined mechanically, and the splitter must COUNT delimiters (n=484 clause
2).** Everything after the frontmatter's closing delimiter. The law files carry `---`
section separators in their bodies, so a splitter that reads a section separator as the
frontmatter close hashes a fragment — and the gate would then pass a tree it should fail.
`body_of()` anchors at the start of the file and takes the FIRST closing delimiter, so a
separator later in the body is inside the body and cannot terminate the frontmatter; the
probes pin both directions.

**The boundary is DECLARED, not hardcoded, and the population is COMMITS.** The ruling
names the `tests/test_ledger_commit_cites_no_rows.py` shape, whose marker is a hardcoded
sha. That form cannot serve here, for the reason that gate's own docstring states: a sha
written into a file that ships byte-identically to every factory belongs to the history of
the repo the template was written in, and a factory re-anchors it at birth. A sha also
cannot be written BEFORE the commit that adopts the rule — the chicken-and-egg this repo
already solves with a declared instant. So the boundary is the factory's own declaration,
read through `tests/ledger_boundary.py` (the ONE reader of `docs/ledger-invariants.json`),
under the key `skill_version_contract`. An absent key SKIPS with a stated reason — the
state every bootstrapped factory is in until it adopts the invariant; a key that is present
but unreadable FAILS, because a declared parameter that cannot be read is a defect and not
an absence.

**It reuses the declaration READER while carrying its own population.** `ledger_boundary`'s
row helpers (`read_rows`, `post_boundary_rows`, `population_skip_reason`) are scoped to
LEDGER ROWS, and this gate's population is GIT COMMITS dated by commit time. Reusing a
row-scoped helper would print a sentence about "row" over a population of commits — a
message that lies about what was examined is worse than three honest lines. So the shared
half is the declaration reader, and the population, its guard and its skip sentence are
this file's own.

**The law file is DISCOVERED, never hardcoded.** A glob over the tracked tree, so a second
law file is found without editing this gate and a bootstrapped factory — whose slug the
gate cannot know — is judged by the same rule.

**The lane-side half is DEFERRED, and the coupling that defers it is named (n=455 clause
4).** This gate is the WRITE-side contract: it keeps the version line moving. The READ side
— a lane asked to acknowledge a version, and a check that DRIFTS when it has not — is NOT
built here, because nothing on this box reads THIS skill's version today. Verified at
n=455: a grep of the opencrabs-dev tools for `meta-factory` returns nothing, and
`oc-drift-check` — the one tool that reads a version line — is coupled to the
**opencrabs-dev** ledger, which it reaches through `oc-ledger roster`: another repo's ack
store, keyed to another skill. Pointing it at this skill is not a wiring change but a
second ack store, so it is a design decision for that lane's owner rather than a
by-product of this gate. Recorded here so the omission is a NAMED deferral and not an
oversight: the write-side contract is enforceable on its own, and it is worth having
before the read side exists, because the read side is unimplementable against a field
that never moves.

Run:  python3 tests/test_skill_version_contract.py
Exit: 0 clean, or a stated skip; 1 a post-boundary commit moved a law body without moving
      the version line, or the declaration is malformed.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ledger_boundary import (  # noqa: E402
    GateError,
    SkipGate,
    declared_boundary,
)

# The gate's own name, which is the KEY it reads from `docs/ledger-invariants.json`. The
# declaration is keyed by the gate that asserts the invariant, so a reader that hardcodes
# a different string than the gate's name would skip forever without saying so.
BOUNDARY_KEY = "skill_version_contract"

# The law surfaces this repo ships: a factory's own law lives at `skills/<slug>/SKILL.md`,
# and the template's ships as `TEMPLATE/SKILL.md.tmpl`. The globs are the DISCOVERY rule —
# a second law file added under `skills/` is found with no edit here.
LAW_GLOBS = ("skills/*/SKILL.md", "TEMPLATE/SKILL.md.tmpl")

# The frontmatter block, and the version line inside it. Anchored so `version:` cannot
# match a prose mention of the word, and scoped to the frontmatter so a law body that
# QUOTES `version: 0.1.2` as evidence is not read as a declaration — the same class the
# telemetry readers were bitten by when a quoted trailer was read as a measurement.
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
VERSION_LINE = re.compile(r"^version:[ \t]*(\S+)[ \t]*$", re.MULTILINE)


def version_of(text: str | None) -> str | None:
    """The declared version VALUE in a law file, or None when it declares none.

    None is a real answer and not an error: a law file with no version line cannot honour
    a contract, so a body change beside it is a violation — which falls out of the
    comparison below without a special case.
    """
    if text is None:
        return None
    match = FRONTMATTER.match(text)
    if match is None:
        return None
    found = VERSION_LINE.search(match.group(1))
    return found.group(1) if found else None


def body_of(text: str | None) -> str | None:
    """The law BODY — everything after the frontmatter block.

    A file with no frontmatter is body-only, which is the honest reading: nothing was
    carved off, so the whole text is the law.
    """
    if text is None:
        return None
    match = FRONTMATTER.match(text)
    return text[match.end():] if match else text


def contract_problems(path: str, before: str | None, after: str | None) -> list[str]:
    """Problems for ONE file's transition across a commit — the whole rule, pure.

    Factored so the probes can drive it directly with synthetic text: a rule that has only
    ever seen good input has not been shown to reject bad input. A file ABSENT on either
    side is not a body change — creation and deletion are transitions no version line can
    describe, so they are out of the rule rather than excused inside it.

    TWO ARMS (n=484 clause 1), because one arm leaves the mirror defect open. Arm 1 catches
    an unbumped body change; arm 2 catches a bump that names no new bytes — `5fcf624c` moved
    `0.1.0` -> `0.1.1` with NO body change and minted a version range with no content, the
    mirror of the ambiguity the contract exists to remove. Together the arms force the
    version and the body to move in the SAME commit, which is what a field naming the bytes
    means. n=528 settles the scope: both law files are in scope and EACH CARRIES ITS OWN
    version, because the two are not byte-paired — so this predicate is per FILE, and a
    commit may satisfy one file's contract while breaking the other's.

    The predicate is a BYTE change and never "was this a substantive law change" (n=484
    clause 3): a gate cannot judge semantics, and deleting a duplicated paragraph IS a body
    change and DOES require a bump, because a lane holding the old copy genuinely has
    different bytes.
    """
    if before is None or after is None:
        return []
    old, new = version_of(before), version_of(after)
    body_moved = body_of(before) != body_of(after)
    version_moved = old != new
    if body_moved and not version_moved:
        if old is None:
            return [
                f"{path}: the law BODY moved but the file declares no `version:` line — "
                "there is no field to move, so the contract cannot be honoured"
            ]
        return [
            f"{path}: the law BODY moved but `version:` stayed {old} — a law change the "
            "drift check cannot see"
        ]
    if version_moved and not body_moved:
        was = old if old is not None else "(absent)"
        now = new if new is not None else "(absent)"
        return [
            f"{path}: `version:` moved {was} -> {now} but the law BODY is unchanged — a "
            "bump that names no new bytes, so the version no longer identifies a body"
        ]
    return []


def _git(repo: Path, *args: str) -> tuple[int, str, str]:
    """One git call, its exit code and streams — never a pipe, so the rc is first-hand."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    return proc.returncode, proc.stdout, proc.stderr


def resolve_repo(anchor: Path) -> Path:
    """The git top level above `anchor`, or `SkipGate` when there is no history.

    The root is asked of git rather than assumed from `__file__`: this file sits at
    `tests/` in a bootstrapped factory but under `TEMPLATE/tests/` in the template repo,
    and a pathspec resolved relative to the wrong one matches no commits and reports
    "examined 0" as clean — the vacuous pass this gate exists to prevent.
    """
    code, out, err = _git(anchor, "rev-parse", "--show-toplevel")
    if code != 0:
        raise SkipGate(
            f"no git history above {anchor} ({err.strip() or 'not a repository'}) — this "
            "gate judges commits, and a tree with no history has no population to judge"
        )
    return Path(out.strip())


def law_files(repo: Path) -> list[str]:
    """Every tracked law file, by the discovery globs. Never a hardcoded slug."""
    code, out, err = _git(repo, "ls-files")
    if code != 0:
        raise GateError([f"git ls-files failed in {repo}: {err.strip()}"])
    return sorted(
        path
        for path in out.splitlines()
        if path and any(fnmatch.fnmatch(path, glob) for glob in LAW_GLOBS)
    )


def commits_touching(repo: Path, paths: list[str]) -> list[tuple[str, str]]:
    """`(sha, committer-date)` for every commit touching `paths`, OLDEST first.

    The date is read from git rather than inferred, and the order is reversed so the walk
    reads history forwards — the direction a contract is enforced in.
    """
    code, out, err = _git(
        repo, "log", "--reverse", "--format=%H%x1f%cI", "--", *paths
    )
    if code != 0:
        raise GateError([f"git log failed in {repo}: {err.strip()}"])
    pairs: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, _, when = line.partition("\x1f")
        pairs.append((sha.strip(), when.strip()))
    return pairs


def blob_at(repo: Path, rev: str, path: str) -> str | None:
    """The file's text at `rev`, or None when it does not exist there.

    Absence is a legitimate answer here (the file is added or deleted at that commit), so
    it is returned rather than raised — but a git call that fails for any OTHER reason is
    a defect and is raised, because a missing blob and a broken invocation must not read
    the same.
    """
    code, out, err = _git(repo, "show", f"{rev}:{path}")
    if code == 0:
        return out
    if "does not exist" in err or "exists on disk, but not in" in err or "unknown revision" in err:
        return None
    raise GateError([f"git show {rev}:{path} failed: {err.strip()}"])


def first_parent(repo: Path, sha: str) -> str | None:
    """The commit's first parent, or None for a root commit."""
    code, out, err = _git(repo, "rev-list", "--parents", "-n", "1", sha)
    if code != 0:
        raise GateError([f"git rev-list {sha} failed: {err.strip()}"])
    parts = out.split()
    return parts[1] if len(parts) > 1 else None


def history_problems(
    repo: Path, since: datetime, paths: list[str]
) -> tuple[list[str], list[tuple[str, str]]]:
    """`(problems, examined)` for the commits at or after `since` touching `paths`.

    The boundary is compared as a PARSED datetime, never as a string: git renders the
    committer date as `%cI` with a `+00:00` offset while the declaration parses to a
    datetime, and a lexical compare between those two forms decides on the offset's
    punctuation rather than on the instant — so a commit exactly at the boundary would read
    as post-boundary, and a format change in either side would silently re-anchor the window.

    `examined` is returned rather than only counted, so the caller can print the population
    it read: a clean verdict over a population the run does not name is indistinguishable
    from a run that examined nothing.
    """
    problems: list[str] = []
    examined: list[tuple[str, str]] = []
    for sha, when in commits_touching(repo, paths):
        try:
            stamp = datetime.fromisoformat(when)
        except ValueError as exc:
            raise GateError(
                [f"commit {sha} carries an unparseable committer date {when!r}: {exc}"]
            ) from exc
        if stamp < since:
            continue
        examined.append((sha, when))
        parent = first_parent(repo, sha)
        if parent is None:
            continue
        for path in paths:
            problems.extend(
                contract_problems(
                    path, blob_at(repo, parent, path), blob_at(repo, sha, path)
                )
            )
    return problems, examined


def evaluate(
    repo: Path,
) -> tuple[str, str, list[str], list[tuple[str, str]], list[str]]:
    """`(status, reason, problems, examined, paths)` — the whole verdict, pure over a repo.

    `status` is one of `skip` (no law file, or no declared boundary), `empty` (a declared
    boundary with no commit in its window), `fail` and `clean`. It is factored out of
    `main` so a probe can drive a SYNTHETIC history through the same code path the run
    takes: a rule exercised only through its own script form is a rule whose probes can
    drift from it, and the `empty` state exists so an empty window is a STATED SKIP rather
    than a silent pass — the #112 ruling's point that a forward-only gate's population is
    legitimately empty until its next instance, which is why the loud-fail-on-zero form
    would be the wrong guard here.
    """
    try:
        paths = law_files(repo)
    except GateError as err:
        return "fail", "", err.problems, [], []
    if not paths:
        return (
            "skip",
            "no tracked law file matches "
            + ", ".join(LAW_GLOBS)
            + " — nothing to judge",
            [],
            [],
            [],
        )
    try:
        boundary, declared = declared_boundary(repo, BOUNDARY_KEY)
    except SkipGate as skip:
        return "skip", str(skip), [], [], []
    except GateError as err:
        return "fail", "", err.problems, [], []

    # The boundary is compared as a PARSED INSTANT, never as text: git renders the
    # committer date as `%cI` (`+00:00`) while the declaration parses to a datetime, and a
    # lexical compare between two offset spellings would decide on punctuation rather than
    # on the instant — every commit could read as post-boundary and the grandfathering
    # would silently disappear. A declaration written without an offset is read as UTC,
    # which is the only zone `tools/ledger.py` writes.
    since = boundary if boundary.tzinfo else boundary.replace(tzinfo=timezone.utc)

    try:
        problems, examined = history_problems(repo, since, paths)
    except GateError as err:
        return "fail", "", err.problems, [], paths

    if problems:
        return "fail", declared, problems, examined, paths
    if not examined:
        return "empty", declared, [], [], paths
    return "clean", declared, [], examined, paths


def main(repo: Path | None = None) -> int:
    """Script form: the same verdict, with the population on STDOUT.

    `repo` is a parameter so a probe can exercise the printed form against a synthetic
    history — the TEMPLATE copy has no law history of its own to print.
    """
    if repo is None:
        try:
            repo = resolve_repo(Path(__file__).resolve().parent)
        except SkipGate as skip:
            print(f"skill-version contract: SKIP — {skip}")
            return 0

    status, reason, problems, examined, paths = evaluate(repo)

    if status == "skip":
        print(f"skill-version contract: SKIP — {reason}")
        return 0

    print(f"skill-version contract: boundary {reason} — law files: {', '.join(paths)}")
    print(f"  examined {len(examined)} commit(s) touching a law file at or after the boundary")

    if status == "empty":
        print(
            f"  SKIP — no commit touching a law file at or after the declared boundary "
            f"{reason}: the population is empty, so this is a stated skip and not a "
            f"silent pass"
        )
        return 0

    if status == "fail":
        for problem in problems:
            print(f"  FAIL {problem}")
        return 1

    print(
        "  clean — every law-file change in the window moved its BODY and its version "
        "line together, per file"
    )
    return 0


# --- probes: the predicate must reject bad input, not only accept good ----------------
#
# This gate judges a HISTORY, so a probe cannot invent one in memory — it builds a
# throwaway git repository. Two environment dependencies are removed rather than assumed:
# the committer IDENTITY is passed with `-c` (a probe must not depend on the host's global
# git config), and the committer DATE is set explicitly, because the gate reads `%cI` and a
# probe that let git stamp "now" would be measuring the clock instead of the boundary.

REPO = Path(__file__).resolve().parent.parent

BEFORE = "2025-01-01T00:00:00+00:00"
AFTER = "2025-06-01T00:00:00+00:00"
BOUNDARY = "2025-03-01T00:00:00Z"


def _probe_git(repo: Path, *args: str, when: str | None = None) -> None:
    """One git call inside a probe tree, asserted — a silently failed probe is worse than
    no probe, because it reports on a history that was never built."""
    env = dict(os.environ)
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=probe@example.invalid",
            "-c",
            "user.name=probe",
            *args,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"


def _probe_repo(
    root: Path, *, boundary: str | None = BOUNDARY, key: str = BOUNDARY_KEY
) -> Path:
    """A fresh git repo carrying a declaration, or none when `boundary` is None."""
    root.mkdir(parents=True, exist_ok=True)
    _probe_git(root, "init", "-b", "main")
    if boundary is not None:
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs/ledger-invariants.json").write_text(
            json.dumps({"_note": "probe", "invariants": {key: boundary}}),
            encoding="utf-8",
        )
    return root


def _law(version: str | None, body: str) -> str:
    """A law file with optional frontmatter `version:` and the given body."""
    head = "---\nname: probe\n"
    if version is not None:
        head += f"version: {version}\n"
    return head + "---\n" + body


def _commit_law(root: Path, rel: str, text: str, when: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _probe_git(root, "add", rel)
    _probe_git(root, "commit", "-m", f"probe {rel}", when=when)


def test_live_the_shipped_history_is_not_in_violation() -> None:
    """The real tree's own verdict, and it must be a STATED one — clean, an empty window
    or a skip. A silent pass is the one outcome this probe will not accept."""
    status, reason, problems, _, paths = evaluate(REPO)
    assert status in {"clean", "empty", "skip"}, (status, reason, problems)


def test_probe_a_body_change_without_a_version_move_fails(tmp_path: Path) -> None:
    """THE BITE — arm 1, the case the gate exists for, and the shape 92 of the 99 law-file
    commits had. A gate never shown to reject this has not been shown to work."""
    root = _probe_repo(tmp_path / "bite")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law B\n"), AFTER)
    status, _, problems, examined, _ = evaluate(root)
    assert status == "fail", (status, problems)
    # ONE commit examined: the pre-boundary commit that created the file is grandfathered
    # OUT of the population, which is what "the window is the window" means.
    assert len(examined) == 1, examined
    assert any("BODY moved but `version:` stayed 0.1.0" in p for p in problems), problems


def test_probe_a_version_move_with_the_body_change_is_clean(tmp_path: Path) -> None:
    root = _probe_repo(tmp_path / "moved")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.1", "law B\n"), AFTER)
    status, _, problems, examined, _ = evaluate(root)
    assert (status, problems) == ("clean", []), problems
    assert len(examined) == 1, examined


def test_probe_a_pre_boundary_violation_is_grandfathered(tmp_path: Path) -> None:
    """Nothing is backfilled: a decoupling that predates the declaration is outside the
    population rather than excused inside it."""
    root = _probe_repo(tmp_path / "grand")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law B\n"), BEFORE)
    status, _, problems, examined, _ = evaluate(root)
    assert (status, examined, problems) == ("empty", [], [])


def test_probe_the_law_file_is_discovered_not_hardcoded(tmp_path: Path) -> None:
    """A SECOND law file is found with no edit to this gate, and is judged by the same
    rule — the acceptance criterion that makes the gate shippable in the template."""
    root = _probe_repo(tmp_path / "discover")
    _commit_law(root, "skills/one/SKILL.md", _law("0.1.0", "one A\n"), BEFORE)
    _commit_law(root, "skills/two/SKILL.md", _law("0.1.0", "two A\n"), BEFORE)
    _commit_law(root, "skills/two/SKILL.md", _law("0.1.0", "two B\n"), AFTER)
    assert law_files(root) == ["skills/one/SKILL.md", "skills/two/SKILL.md"]
    status, _, problems, _, paths = evaluate(root)
    assert status == "fail", problems
    assert paths == ["skills/one/SKILL.md", "skills/two/SKILL.md"], paths
    assert any(p.startswith("skills/two/SKILL.md") for p in problems), problems


def test_probe_a_body_change_with_no_version_line_fails(tmp_path: Path) -> None:
    root = _probe_repo(tmp_path / "noversion")
    _commit_law(root, "skills/probe/SKILL.md", _law(None, "law A\n"), BEFORE)
    _commit_law(root, "skills/probe/SKILL.md", _law(None, "law B\n"), AFTER)
    status, _, problems, _, _ = evaluate(root)
    assert status == "fail", problems
    assert any("declares no `version:` line" in p for p in problems), problems


def test_probe_a_creation_is_not_a_violation(tmp_path: Path) -> None:
    """A root commit has no parent to diff against. Creation is out of the rule, not
    excused inside it."""
    root = _probe_repo(tmp_path / "create")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), AFTER)
    status, _, problems, examined, _ = evaluate(root)
    assert (status, problems) == ("clean", []), problems
    assert len(examined) == 1, examined


def test_probe_a_version_only_bump_fails(tmp_path: Path) -> None:
    """ARM 2 — the mirror defect (n=484 clause 1). `5fcf624c` moved `0.1.0` -> `0.1.1` with
    NO body change and minted a version range with no content, the mirror of the ambiguity
    the contract exists to remove. Arm 1 alone passes it, and an earlier revision of this
    probe ASSERTED that clean verdict — the probe enshrined the bug. A bump that names no
    new bytes must fire."""
    root = _probe_repo(tmp_path / "bump")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.1", "law A\n"), AFTER)
    status, _, problems, examined, _ = evaluate(root)
    assert status == "fail", (status, problems)
    assert len(examined) == 1, examined
    assert any("`version:` moved 0.1.0 -> 0.1.1 but the law BODY is unchanged" in p
               for p in problems), problems


def test_probe_adding_a_version_line_alone_is_arm_2(tmp_path: Path) -> None:
    """Arm 2 is a comparison of two VALUES, and an absent field is one of them: a commit
    that introduces `version: 0.1.0` without touching the body has moved the version and
    named no new bytes."""
    root = _probe_repo(tmp_path / "addline")
    _commit_law(root, "skills/probe/SKILL.md", _law(None, "law A\n"), BEFORE)
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), AFTER)
    status, _, problems, _, _ = evaluate(root)
    assert status == "fail", (status, problems)
    assert any("`version:` moved (absent) -> 0.1.0" in p for p in problems), problems


def test_probe_both_arms_fire_per_file(tmp_path: Path) -> None:
    """n=528: the two law files are independent documents, so the arms apply PER FILE. One
    run can fail one file on arm 1 and the other on arm 2, and the gate must name BOTH
    rather than stopping at the first problem it finds."""
    root = _probe_repo(tmp_path / "perfile")
    _commit_law(root, "skills/one/SKILL.md", _law("0.1.0", "one A\n"), BEFORE)
    _commit_law(root, "skills/two/SKILL.md", _law("0.1.0", "two A\n"), BEFORE)
    _commit_law(root, "skills/one/SKILL.md", _law("0.1.0", "one B\n"), AFTER)
    _commit_law(root, "skills/two/SKILL.md", _law("0.1.1", "two A\n"), AFTER)
    status, _, problems, _, _ = evaluate(root)
    assert status == "fail", (status, problems)
    assert any(p.startswith("skills/one/SKILL.md") and "BODY moved" in p
               for p in problems), problems
    assert any(p.startswith("skills/two/SKILL.md") and "BODY is unchanged" in p
               for p in problems), problems


def test_probe_a_mode_only_change_is_not_a_violation(tmp_path: Path) -> None:
    """A commit that touches a law file without changing its BYTES — a chmod — moves neither
    the body nor the version, and neither arm may fire on it. The predicate is a byte
    change (n=484 clause 3), so a mode bit is not a law change."""
    root = _probe_repo(tmp_path / "mode")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    _probe_git(root, "update-index", "--chmod=+x", "skills/probe/SKILL.md")
    _probe_git(root, "commit", "-m", "probe chmod", when=AFTER)
    status, _, problems, examined, _ = evaluate(root)
    assert (status, problems) == ("clean", []), problems
    assert len(examined) == 1, examined


def test_probe_a_section_separator_does_not_close_the_frontmatter() -> None:
    """n=484 clause 2, the clause's own stated failure: the law files carry `---` section
    separators in their BODIES, so a splitter that reads one as the frontmatter close hashes
    a FRAGMENT — "and the gate would then pass a tree it should fail". The splitter must
    COUNT delimiters: the frontmatter ends at the SECOND one, whatever follows.

    The two texts below share a frontmatter and differ ONLY after a `---` separator. A
    truncating splitter would hash them as equal and report clean."""
    head = "---\nname: probe\nversion: 0.1.0\n---\n"
    tail_a = "## A\nalpha\n\n---\n\n## B\nbeta\n\n---\n\n## C\ngamma\n"
    tail_b = tail_a.replace("gamma", "GAMMA")
    assert body_of(head + tail_a) == tail_a
    assert body_of(head + tail_a) != body_of(head + tail_b)
    # every separator is INSIDE the body, not consumed as frontmatter
    assert body_of(head + tail_a).count("---") == 2


def test_probe_a_leading_separator_in_the_body_is_not_swallowed() -> None:
    """The mirror of the clause: a body whose FIRST line is a separator keeps it. Counting
    delimiters means the frontmatter is the first TWO — a third `---` is body content, and a
    body that opens with one must not lose its first section."""
    text = "---\nname: probe\nversion: 0.1.0\n---\n---\n## Section\nlaw\n"
    assert body_of(text) == "---\n## Section\nlaw\n"


def test_probe_a_body_change_after_a_separator_fails_the_gate(tmp_path: Path) -> None:
    """The clause's consequence, end to end: a commit that changes ONLY the region after a
    `---` separator, without moving the version, must FIRE. This is the tree the fragmenting
    splitter would have passed."""
    head = "---\nname: probe\nversion: 0.1.0\n---\n"
    root = _probe_repo(tmp_path / "sep")
    _commit_law(root, "skills/probe/SKILL.md",
                head + "## A\nalpha\n\n---\n\n## B\nbeta\n", BEFORE)
    _commit_law(root, "skills/probe/SKILL.md",
                head + "## A\nalpha\n\n---\n\n## B\nGAMMA\n", AFTER)
    status, _, problems, examined, _ = evaluate(root)
    assert status == "fail", (status, problems)
    assert len(examined) == 1, examined
    assert any("BODY moved" in p for p in problems), problems


def test_probe_a_quoted_version_in_the_body_is_not_the_declaration() -> None:
    """A law body that QUOTES `version: 0.1.9` as evidence must not be read as declaring
    it — the same class the telemetry readers were bitten by when a quoted trailer was
    read as a measurement."""
    text = _law("0.1.0", "the earlier release read `version: 0.1.9` in its frontmatter\n")
    assert version_of(text) == "0.1.0"
    assert version_of("no frontmatter here\nversion: 0.9.9\n") is None
    assert version_of(None) is None


def test_probe_the_boundary_comes_from_the_declaration_not_this_file(tmp_path: Path) -> None:
    """The same history under two declarations yields two verdicts — the window is the
    factory's own parameter, never a constant inside a file that ships to every factory."""
    early = _probe_repo(tmp_path / "early", boundary="2025-03-01T00:00:00Z")
    _commit_law(early, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    _commit_law(early, "skills/probe/SKILL.md", _law("0.1.0", "law B\n"), AFTER)
    assert evaluate(early)[0] == "fail"
    late = _probe_repo(tmp_path / "late", boundary="2026-01-01T00:00:00Z")
    _commit_law(late, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    _commit_law(late, "skills/probe/SKILL.md", _law("0.1.0", "law B\n"), AFTER)
    assert evaluate(late)[0] == "empty"


def test_probe_a_tree_with_no_declaration_skips(tmp_path: Path) -> None:
    root = _probe_repo(tmp_path / "nodecl", boundary=None)
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), AFTER)
    status, reason, _, _, _ = evaluate(root)
    assert status == "skip", status
    assert "ledger-invariants.json" in reason, reason


def test_probe_a_missing_key_skips(tmp_path: Path) -> None:
    root = _probe_repo(tmp_path / "otherkey", key="some_other_invariant")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), AFTER)
    status, reason, _, _, _ = evaluate(root)
    assert status == "skip", status
    assert BOUNDARY_KEY in reason, reason


def test_probe_a_malformed_declaration_fails_rather_than_raising(tmp_path: Path) -> None:
    """A declared parameter that cannot be read is a DEFECT, not an absence — it must
    never be quietly downgraded onto the skip path."""
    root = _probe_repo(tmp_path / "broken")
    (root / "docs/ledger-invariants.json").write_text("{not json", encoding="utf-8")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), AFTER)
    status, _, problems, _, _ = evaluate(root)
    assert status == "fail", status
    assert any("not valid JSON" in p for p in problems), problems


def test_probe_an_unreadable_boundary_value_fails(tmp_path: Path) -> None:
    root = _probe_repo(tmp_path / "badvalue", boundary="not-a-timestamp")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), AFTER)
    status, _, problems, _, _ = evaluate(root)
    assert status == "fail", status
    assert any("not a readable ISO-8601" in p for p in problems), problems


def test_probe_a_tree_with_no_law_file_skips(tmp_path: Path) -> None:
    root = _probe_repo(tmp_path / "nolaw")
    _probe_git(root, "commit", "--allow-empty", "-m", "probe empty", when=AFTER)
    status, reason, _, _, paths = evaluate(root)
    assert (status, paths) == ("skip", []), (status, paths)
    assert "no tracked law file" in reason, reason


def test_probe_the_script_form_prints_its_population(tmp_path: Path, capsys) -> None:
    """Non-vacuity is a property of the PROBE, population visibility is the property of
    the RUN: a clean verdict over a population the run never names reads exactly like a
    run that examined nothing."""
    root = _probe_repo(tmp_path / "printed")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law B\n"), AFTER)
    assert main(root) == 1
    out = capsys.readouterr().out
    assert "examined 1 commit(s)" in out, out
    assert "FAIL skills/probe/SKILL.md" in out, out


def test_probe_an_empty_window_is_a_stated_skip(tmp_path: Path, capsys) -> None:
    """A forward-only gate's population is legitimately empty until its next instance, so
    the loud-fail-on-zero form would be the wrong guard — the SKIP must be STATED."""
    root = _probe_repo(tmp_path / "emptywin")
    _commit_law(root, "skills/probe/SKILL.md", _law("0.1.0", "law A\n"), BEFORE)
    assert main(root) == 0
    out = capsys.readouterr().out
    assert "examined 0 commit(s)" in out, out
    assert "stated skip and not a silent pass" in out, out


def test_probe_the_predicate_is_pure_and_offline() -> None:
    """No network, no board, no `gh` — asserted on the IMPORTS rather than on prose, so a
    later 'improvement' that reaches out fails here. `subprocess` is deliberately NOT
    banned: this gate reads a local git repository, which is repo-mechanical and offline."""
    imports = set(
        re.findall(
            r"^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)",
            Path(__file__).read_text(encoding="utf-8"),
            re.M,
        )
    )
    banned = {"socket", "urllib", "urllib.request", "http", "requests"}
    assert not (imports & banned), sorted(imports & banned)


if __name__ == "__main__":
    sys.exit(main())
