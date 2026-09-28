#!/usr/bin/env python3
"""Gate: a commit carrying the ledger names the concern, not row numbers.

Origin (issue #47, the ledger clause). A ledger row's number is assigned *inside* the
append lock, so it cannot be known before the append — and by the time the commit runs
another lane may have appended further rows. Measured in a single day, three commits
carried the same shape: one named `n=211` and added 211/212/213; another named 212/213
and added 214/215; a third named `n=259` and added `n=261`. That is structural, not
carelessness, which is why the clause removes the claim rather than policing it: the
message names the concern, and where a row must be cited it is cited in the ledger's
own `detail` text — written after the append, where the real number can be read.

**Forward-only, and why.** A history-wide form would be permanently red: 55 of 146
historical commits touching the ledger cite row numbers in their subject. The gate is
therefore bounded by a marker commit — the first ledger commit obeying the clause — and
examines only commits after it. Nothing is backfilled: those historical violations are
history, not a backlog.

**The marker is DECLARED FACTORY DATA, not a hardcoded sha.** The shipped default is the
template's own first-obeying commit, and a factory bootstrapped from the template does not
carry that history — but this file is byte-paired into `TEMPLATE/`
(`tests/test_template_sync.py`), so editing the sha here to re-anchor is either a fork of a
shipped file or a RED on that gate. Measured 2026-09-28: two members (ai-antispam,
inferhub-watch) were blocked from adopting this gate by exactly that, holding a shipped
gate they could neither satisfy nor lawfully anchor. The marker is therefore the `marker`
key of this gate's own data file (`docs/ledger-commit-exemptions.json`) — the surface the
gate already reads, which is never shipped — and `resolve_marker` is its one reader. The
mechanism is `tests/ledger_boundary.py`'s (issue #78, P35): the LOGIC is universal, the
PARAMETERS are declared.

Three outcomes, and the difference between them is the point:
* a DECLARED marker that does not resolve FAILS LOUDLY — the factory named a sha it cannot
  honour, and a declared parameter that cannot be honoured is a defect, not an absence;
* no declaration and the shipped default RESOLVES — judged over the default's range, which
  is this template's own home factory;
* no declaration and the shipped default does NOT resolve — SKIP, with the reason and the
  route named. It examines nothing and says so, rather than passing vacuously or reding a
  tree that has declared nothing.

**The sanctioned exit, and why the marker is not it (ruled at n=328).** A violation
inside the window has an EMPTY REPAIR SPACE, so without a lawful exit one violation reds
the suite forever and the next lane learns to ignore a red gate — which destroys every
other gate's signal. The repairs are all barred: the commit is pushed (rewriting it is
barred by the identity law), a revert does not clear the gate (it reads subjects across
the marker range, so the offending subject stays in range), and re-anchoring the marker past
the violation would make the marker's own definition — "the first commit touching the
ledger whose subject obeys the clause", whose predecessors "predate the rule" — false,
silently converting a live violation into an excused one. So the marker is re-anchored
ONLY at a factory's birth or when a history rewrite invalidates it, and the gate carries
a second, VISIBLE exit: an exemption list.

**The list is factory data read by the gate, never source inside it.** This file is
copied byte-identically into `TEMPLATE/` (guarded by `tests/test_template_sync.py`), so
an inline table naming one factory's sha would either break that gate or ship a foreign
sha into the template. The entries therefore live in
`docs/ledger-commit-exemptions.json`, whose skeleton is
`TEMPLATE/docs/ledger-commit-exemptions.example.json` — the same move that took the
product declaration out of `tools/roadmap.py` and into `docs/products.json`.

**An exemption is a visible debt, not forgiveness.** Every entry that matched is printed
as an `excused:` line on EVERY run, and the closing line distinguishes clean from
excused, so "clean" and "excused" are never the same output. Entries are keyed by the
FULL 40-character sha: a short sha or a tag would match nothing while looking like it
should. Absent or empty data means no exemptions — the shipped state of a new factory. A
malformed entry (not a full sha, no reason, malformed JSON) is a gate ERROR, never a
silent pass, because an exemption list that quietly fails to load is indistinguishable
from no exemptions — the same vacuous-pass shape the marker rule exists to prevent. An
entry that matches no violation in the range is an ERROR too: a stale exemption inflates
the count of visible debt while excusing nothing. And a SECOND exemption of the same
shape is a process defect, not an exemption — one is a debt; two mean the mechanism
(running `tools/audit.py` before a commit that touches the ledger) is not biting.

**The repo root is resolved, not assumed.** The gate's own file sits at `tests/` in a
bootstrapped factory but under `TEMPLATE/tests/` in the template repo, so resolving the
tree from `__file__` alone made the template copy run `git log` with a pathspec relative
to `TEMPLATE/` — matching no commits and reporting "examined 0" as clean. That is the
vacuous pass this gate exists to prevent, so it asks git for the real top level and
passes the ledger and the exemption data as absolute paths.

**It reports the count it examined.** "0 examined" must never read as "clean".

Run:  python3 tests/test_ledger_commit_cites_no_rows.py
Exit: 0 clean, or every violation excused; 1 a post-marker commit cites row numbers
      without an exemption, or the marker is gone, or the exemption data is malformed.
**The mechanism, and why this gate asserts it.** The clause's remedy for a SECOND
exemption of the same shape is a mechanism, not a third row (ruled at n=405): a
versioned `commit-msg` hook that refuses a citing subject before it is recorded. An
uninstalled hook is SILENT — the vacuous-pass shape this repo forbids — so this gate
also asserts the hook is present, executable, and reachable through `core.hooksPath`.
Install it with `git config core.hooksPath tools/hooks`; the config is local, so a
fresh clone runs it once.

"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The installation predicate is shared with `tests/test_commit_pair_hook.py` (#92),
# which asserts the same three facts about a DIFFERENT hook. Two implementations of
# one predicate drift, and the drift is silent — the same class this repo forbids for
# a byte pair, applied to a predicate.
from hook_installation import (  # noqa: E402
    hook_state_problems as shared_hook_state_problems,
)

REPO = Path(__file__).resolve().parent.parent
LEDGER_PATH = "evidence/ledger.jsonl"
EXEMPTIONS_PATH = "docs/ledger-commit-exemptions.json"

# The mechanism the clause makes its remedy (issue #47, ruled at n=405): a versioned
# commit-msg hook, at the only point where the pending subject exists to be refused.
HOOK_PATH = "tools/hooks/commit-msg"
HOOKS_PATH_CONFIG = "tools/hooks"

# The wording this law owns. The shared predicate cannot know which law lost its
# refusal point, so the gate that owns the law supplies the sentence.
MISSING_REASON = (
    f"{HOOK_PATH} is missing — the commit-msg refusal point the ledger clause "
    "makes its remedy (issue #47, ruled at n=405) is not shipped"
)

# The SHIPPED DEFAULT marker: the first commit touching the ledger whose subject obeys
# the clause IN THE TEMPLATE'S OWN HISTORY. It is a default and not a constant because a
# factory bootstrapped from the template does not carry that history, and this file is
# byte-paired (guarded by `tests/test_template_sync.py`) -- so editing the sha here is
# either a fork of a shipped file or a RED on that gate. Measured 2026-09-28: two members
# (ai-antispam, inferhub-watch) were blocked from adopting this gate by exactly that,
# with no non-forking route to re-anchor.
#
# The marker is therefore FACTORY DATA, declared as the `marker` key of this gate's own
# data file (`docs/ledger-commit-exemptions.json`), which is the surface the gate already
# reads and which is never shipped. The mechanism is the one `tests/ledger_boundary.py`
# was created for (issue #78, P35): a byte-paired gate must not assert a live-tree fact
# its own tree cannot satisfy, so the PARAMETERS are declared while the LOGIC is
# universal. Three outcomes, and the difference between them is the point:
#   * declared marker that does not resolve -> FAIL, loudly. The factory asked to be
#     judged over a range and named a sha it cannot honour; that is a defect, not an
#     absence (the #69 clause (e) shape).
#   * no declaration, shipped default resolves -> judged over the default's range. This is
#     the template's own home factory, where the default is real history.
#   * no declaration, shipped default does not resolve -> SKIP with the reason, naming the
#     route. The default belongs to a history this tree does not carry, so the gate says
#     so instead of passing vacuously or reding a tree that has declared nothing.
DEFAULT_MARKER = "743b543"

# The key a factory sets in its own data file to anchor the clause in its own history.
MARKER_KEY = "marker"

# A row citation. The word boundary is load-bearing: without it, `version=3` and
# `conversion=2` both contain the substring `n=` and would be reported as citations.
ROW_CITE = re.compile(r"\bn=\d+\b", re.IGNORECASE)

# An exemption is keyed by a full git sha. Asserted rather than assumed: a short sha or a
# tag would match nothing while looking like it should.
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

def subject_cites_rows(subject: str) -> bool:
    """True when a commit subject cites a ledger row number.

    Factored so synthetic subjects can probe it: a rule that has only ever seen good
    input has not been shown to reject bad input.
    """
    return bool(ROW_CITE.search(subject or ""))

def _git(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True
    )
    return proc.returncode, proc.stdout, proc.stderr

def repo_toplevel() -> Path | None:
    """The git top level containing this gate, so a copy in a subdirectory still works."""
    rc, out, _ = _git("rev-parse", "--show-toplevel")
    return Path(out.strip()) if rc == 0 and out.strip() else None

def hook_state_problems(*, exists: bool, executable: bool, configured: str) -> list[str]:
    """The refusal point's three facts, as a PURE predicate.

    Factored so synthetic state can drive every rejection path: an uninstalled hook
    is SILENT, which is the vacuous-pass shape this repo forbids — the same reason a
    missing marker fails loudly rather than examining zero commits. So absence is a
    gate failure, never an advisory.

    The predicate itself lives in `tests/hook_installation.py`: `tests/test_commit_pair_hook.py`
    (#92) asserts the same three facts about the `pre-commit` hook, and two
    implementations of one predicate drift. This binding keeps the signature its own
    probes drive and supplies the wording this law owns.
    """
    return shared_hook_state_problems(
        hook_path=HOOK_PATH,
        hooks_path_config=HOOKS_PATH_CONFIG,
        exists=exists,
        executable=executable,
        configured=configured,
        missing_reason=MISSING_REASON,
    )

def hook_installation_problems(top: Path) -> list[str]:
    """Read the installation state off the tree and git config, then judge it."""
    hook = top / HOOK_PATH
    rc, out, _ = _git("config", "--get", "core.hooksPath")
    return hook_state_problems(
        exists=hook.is_file(),
        executable=os.access(hook, os.X_OK),
        configured=out.strip() if rc == 0 else "",
    )

def exemptions_file() -> Path:
    """The factory's exemption data, resolved against the git top level.

    Resolved the same way as the ledger, and for the same reason: this file's own
    location moves between `tests/` and `TEMPLATE/tests/`.
    """
    return (repo_toplevel() or REPO) / EXEMPTIONS_PATH

def declared_marker(path: Path | None = None) -> tuple[str | None, list[str]]:
    """`(marker, problems)` read from the factory's own data file, or `(None, [])`.

    The READS are shared with `load_exemptions`, from the same file, so the gate cannot
    hold two opinions about the surface it declares itself on. `None` means the factory
    declared nothing -- which is not an error, and is exactly the state every adopter is
    in until it anchors. A MALFORMED declaration is a problem and never a silent fallback
    to the default: substituting another factory's sha would examine the wrong range and
    call the result a verdict.
    """
    path = path or exemptions_file()
    if not path.is_file():
        return None, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"{path.name} is not JSON: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{path.name}: expected a JSON object"]
    raw = data.get(MARKER_KEY)
    if raw is None:
        return None, []
    if not isinstance(raw, str) or not raw.strip():
        return None, [
            f"{path.name}: {MARKER_KEY!r} must be a non-empty string naming the first "
            "commit that touches the ledger and obeys the clause"
        ]
    return raw.strip(), []

def resolve_marker() -> tuple[str, str, list[str]]:
    """`(marker, source, problems)`. `source` is `'declared'` or `'default'`.

    Reads the declaration and applies `marker_outcome` to it. Kept thin so that the
    DECISION lives in one pure place the probes can drive with both values of the single
    fact that decides it.
    """
    declared, problems = declared_marker()
    if problems:
        return (declared or DEFAULT_MARKER), ("declared" if declared else "default"), problems
    return marker_outcome(declared, resolves=marker_resolves(declared or DEFAULT_MARKER))

def marker_outcome(
    declared: str | None, *, resolves: bool
) -> tuple[str, str, list[str], str | None]:
    """The marker decision, factored pure: `(marker, source, problems, skip_reason)`.

    Factored because the three outcomes are decided by exactly two facts -- whether the
    factory declared a marker, and whether the marker in play RESOLVES -- and driving them
    through `main()` would need a repository standing in each state, which is how a
    rule ends up having only ever seen good input.
    """
    if declared is not None:
        if resolves:
            return declared, "declared", [], None
        return declared, "declared", [
            f"the DECLARED marker {declared} does not resolve — this factory declared the "
            f"sha its ledger clause is bounded by, as {MARKER_KEY!r} in {EXEMPTIONS_PATH}, "
            "and that commit is not in this repository. A declared parameter that cannot be "
            "honoured is a defect, not an absence: correct the key to the first commit "
            "touching the ledger whose subject obeys the clause, or REMOVE it to take the "
            "shipped default. Do not delete the gate."
        ], None
    if resolves:
        return DEFAULT_MARKER, "default", [], None
    return DEFAULT_MARKER, "default", [], (
        f"the shipped default marker {DEFAULT_MARKER} does not resolve in this repository "
        "— it is the template's own first-obeying commit, and a factory bootstrapped from "
        f"the template does not carry that history. Declare this factory's own marker as "
        f"the {MARKER_KEY!r} key in {EXEMPTIONS_PATH} (the first commit touching "
        f"{LEDGER_PATH} whose subject obeys the clause) to begin judging this factory's "
        "range. Until then this gate examines nothing, and says so rather than passing "
        "vacuously."
    )

def marker_resolves(marker: str) -> bool:
    rc, _, _ = _git("rev-parse", "--verify", "--quiet", f"{marker}^{{commit}}")
    return rc == 0

def ledger_commits_after(marker: str) -> list[tuple[str, str, str]]:
    """`[(full_sha, short_sha, subject)]` for commits after `marker`, newest first.

    The full sha is carried because exemptions are keyed by it; the short one is carried
    because it is what a human reads. The ledger is passed as an absolute path, so the
    pathspec resolves against the git top level rather than against this file's own
    directory.
    """
    top = repo_toplevel()
    if top is None:
        raise RuntimeError(f"{REPO} is not inside a git work tree")
    rc, out, err = _git(
        "log", "--format=%H\x1f%h\x1f%s", f"{marker}..HEAD", "--", str(top / LEDGER_PATH)
    )
    if rc != 0:
        raise RuntimeError(f"git log failed: {err.strip()}")
    rows: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        rows.append((parts[0], parts[1], parts[2]))
    return rows

def offenders(commits: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    return [(full, short, s) for full, short, s in commits if subject_cites_rows(s)]

def load_exemptions(path: Path) -> tuple[dict[str, dict], list[str]]:
    """`({full_sha: entry}, problems)` read from the factory data file.

    Absent or empty data means no exemptions. Anything malformed is a problem, never a
    silent pass — see the docstring for why that distinction is load-bearing.
    """
    problems: list[str] = []
    if not path.is_file():
        return {}, problems
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"{path.name} is not JSON: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{path.name}: expected a JSON object with an 'exemptions' list"]
    raw = data.get("exemptions", [])
    if not isinstance(raw, list):
        return {}, [f"{path.name}: 'exemptions' must be a list"]

    entries: dict[str, dict] = {}
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            problems.append(f"{path.name}: entry {i} is not an object")
            continue
        sha = item.get("sha")
        if not isinstance(sha, str) or not FULL_SHA.match(sha):
            problems.append(
                f"{path.name}: entry {i} names a sha that is not a full 40-character "
                f"lowercase hex sha: {sha!r}"
            )
            continue
        if not item.get("reason"):
            problems.append(f"{path.name}: entry {i} ({sha[:12]}) carries no reason")
            continue
        if sha in entries:
            problems.append(f"{path.name}: entry {i} repeats {sha}")
            continue
        entries[sha] = item
    return entries, problems

def probe() -> list[str]:
    """Probe the predicate and the exemption loader against both shapes.

    A rule that has only ever seen good input has not been shown to reject bad input, so
    every rejection path is exercised here — including the ones that would otherwise
    only ever run in a factory that had already made the mistake.
    """
    failures: list[str] = []
    must_catch = [
        "chore(ledger): stamp the claim and carry HQ's ruling rows (n=265)",
        "chore(ledger): n=123",
        "chore(ledger): closes n=9 and n=10",
    ]
    must_pass = [
        "chore(ledger): stamp the claim and carry HQ's ruling rows",
        "chore(ledger): close the board-close-on-settlement subject with its board token",
        # The word-boundary guard: a word merely ending in `n=` is not a citation.
        "fix: bump version=3 of the schema",
        "docs: conversion=2 notes",
    ]
    for subject in must_catch:
        if not subject_cites_rows(subject):
            failures.append(f"probe: predicate missed a row citation in {subject!r}")
    for subject in must_pass:
        if subject_cites_rows(subject):
            failures.append(f"probe: predicate false-positived on {subject!r}")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        full = "0" * 40

        absent = tmpdir / "absent.json"
        entries, problems = load_exemptions(absent)
        if entries or problems:
            failures.append(
                "probe: absent exemption data must mean no exemptions and no error"
            )

        empty = tmpdir / "empty.json"
        empty.write_text('{"exemptions": []}', encoding="utf-8")
        entries, problems = load_exemptions(empty)
        if entries or problems:
            failures.append(
                "probe: an empty exemption list must mean no exemptions and no error"
            )

        good = tmpdir / "good.json"
        good.write_text(
            json.dumps(
                {"exemptions": [{"sha": full, "date": "2026-01-01", "reason": "r"}]}
            ),
            encoding="utf-8",
        )
        entries, problems = load_exemptions(good)
        if problems or set(entries) != {full}:
            failures.append("probe: a well-formed exemption entry must load cleanly")

        short = tmpdir / "short.json"
        short.write_text(
            '{"exemptions": [{"sha": "697b660", "date": "2026-01-01", "reason": "r"}]}',
            encoding="utf-8",
        )
        entries, problems = load_exemptions(short)
        if entries or not problems:
            failures.append(
                "probe: a sha that is not a full sha must be an ERROR, not a silent pass"
            )

        no_reason = tmpdir / "no_reason.json"
        no_reason.write_text(
            json.dumps({"exemptions": [{"sha": full, "date": "2026-01-01"}]}),
            encoding="utf-8",
        )
        entries, problems = load_exemptions(no_reason)
        if entries or not problems:
            failures.append("probe: an entry carrying no reason must be an ERROR")

        broken = tmpdir / "broken.json"
        broken.write_text('{"exemptions": [', encoding="utf-8")
        entries, problems = load_exemptions(broken)
        if entries or not problems:
            failures.append("probe: malformed JSON must be an ERROR, not a silent pass")

    # The hook's installation facts — the mechanism the clause's second exemption is
    # admitted WITH. An uninstalled hook is silent, so every way it can be absent is
    # exercised here rather than discovered in a factory that had lost the mechanism.
    if hook_state_problems(exists=True, executable=True, configured=HOOKS_PATH_CONFIG):
        failures.append("probe: a present, executable, wired hook must report clean")
    for kwargs, why in (
        (
            {"exists": False, "executable": False, "configured": HOOKS_PATH_CONFIG},
            "a missing hook",
        ),
        (
            {"exists": True, "executable": False, "configured": HOOKS_PATH_CONFIG},
            "a hook git cannot execute",
        ),
        ({"exists": True, "executable": True, "configured": ""}, "an unwired hook"),
        (
            {"exists": True, "executable": True, "configured": ".git/hooks"},
            "a hook reachable only through a foreign hooksPath",
        ),
    ):
        if not hook_state_problems(**kwargs):
            failures.append(f"probe: {why} must be reported, not passed")

    # The marker's three outcomes, driven directly. Both values of the one fact that
    # decides them (whether the marker in play resolves) are exercised for both states of
    # the declaration, because a rule that has only ever seen good input has not been shown
    # to reject bad input -- and the SKIP arm in particular is the one a fresh factory
    # meets first, where a silent pass would be indistinguishable from a verified range.
    for declared, resolves, want_source, want_problems, want_skip, why in (
        ("a1b2c3d4", True, "declared", False, False,
         "a DECLARED marker that resolves is used, as declared"),
        ("deadbeefdeadbeef", False, "declared", True, False,
         "a DECLARED marker that does not resolve must FAIL, not skip"),
        (None, True, "default", False, False,
         "an undeclared shipped default that resolves is judged over its range"),
        (None, False, "default", False, True,
         "an undeclared shipped default that does not resolve must SKIP with its reason"),
    ):
        marker, source, probs, skip = marker_outcome(declared, resolves=resolves)
        if source != want_source:
            failures.append(f"probe: {why} — source was {source!r}")
        if bool(probs) != want_problems:
            failures.append(f"probe: {why} — problems={probs}")
        if bool(skip) != want_skip:
            failures.append(f"probe: {why} — skip={skip!r}")
        if want_skip and skip is not None:
            # The SKIP must name the ROUTE, or the adopter is told it examined nothing
            # without being told what to do about it.
            if MARKER_KEY not in skip or LEDGER_PATH not in skip:
                failures.append(
                    "probe: the SKIP reason must name both the declaration key and the "
                    "ledger it governs"
                )
        if source == "declared" and not probs:
            if marker != declared:
                failures.append(f"probe: {why} — marker was {marker!r}, not the declared sha")

    # The declaration's own parsing, on fixtures: absent, well-formed, and the two
    # malformed shapes. A malformed value must never fall back to the default silently,
    # because substituting another factory's sha examines the wrong range.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        absent = tmp / "absent.json"
        absent.write_text('{"exemptions": []}', encoding="utf-8")
        got, probs = declared_marker(absent)
        if got is not None or probs:
            failures.append("probe: an absent marker key means undeclared, with no problem")

        good = tmp / "good.json"
        good.write_text('{"marker": "a1b2c3d4", "exemptions": []}', encoding="utf-8")
        got, probs = declared_marker(good)
        if got != "a1b2c3d4" or probs:
            failures.append(f"probe: a well-formed marker must load cleanly (got {got!r})")

        for payload, why in (
            ('{"marker": 12345}', "a numeric marker"),
            ('{"marker": ""}', "an empty marker"),
            ('{"marker": null}', "an explicitly null marker (undeclared, not an error)"),
        ):
            f = tmp / "bad.json"
            f.write_text(payload, encoding="utf-8")
            got, probs = declared_marker(f)
            if why.endswith("undeclared, not an error)"):
                if got is not None or probs:
                    failures.append(f"probe: {why} must read as undeclared with no problem")
            elif not probs:
                failures.append(f"probe: {why} must be a problem, never a silent fallback")

        broken = tmp / "broken.json"
        broken.write_text('{"marker": ', encoding="utf-8")
        got, probs = declared_marker(broken)
        if not probs:
            failures.append("probe: malformed JSON in the marker's own file must be an ERROR")

    return failures

def main() -> int:
    problems = probe()

    top = repo_toplevel()
    if top is None:
        problems.append(
            f"{REPO} is not inside a git work tree — the hook's installation, and "
            "the ledger's history, cannot be read"
        )
    else:
        problems.extend(hook_installation_problems(top))
    excused: list[tuple[str, dict]] = []

    declared, problems_read = declared_marker()
    problems.extend(problems_read)
    # The guard is this flag and NOT `problems`: an unrelated probe failure must not
    # suppress the history scan, or a gate with a broken probe would report a smaller
    # range than it read -- the silent-coverage-loss shape.
    marker_ok = False
    if problems_read:
        marker = declared or DEFAULT_MARKER
        source = "declared" if declared else "default"
    else:
        marker, source, marker_problems, skip_reason = marker_outcome(
            declared, resolves=marker_resolves(declared or DEFAULT_MARKER)
        )
        problems.extend(marker_problems)
        if skip_reason is not None:
            print(f"SKIP: {skip_reason}")
            return 0
        marker_ok = not marker_problems
    if marker_ok:
        exemptions, data_problems = load_exemptions(exemptions_file())
        problems.extend(data_problems)

        commits = ledger_commits_after(marker)
        bad = offenders(commits)
        print(f"ledger clause: examined {len(commits)} commit(s) after {marker} ({source})")

        for full, short, subject in bad:
            entry = exemptions.get(full)
            if entry is None:
                problems.append(f"{short} cites a row number: {subject}")
            else:
                excused.append((full, entry))

        # A stale exemption matches nothing, so it inflates the count of visible debt
        # while excusing nothing. Reported rather than ignored: an exemption list that
        # silently does nothing is a gate lying about its own coverage.
        for full in sorted(set(exemptions) - {f for f, _, _ in bad}):
            problems.append(
                f"exemption {full} matches no violation in {marker}..HEAD — a stale "
                "exemption excuses nothing; remove it or correct the sha"
            )

        for full, entry in excused:
            print(f"  excused: {full} — {entry.get('reason', '')}")

    if problems:
        for line in problems:
            print(f"  FAIL {line}")
        return 1

    if excused:
        print(
            f"ledger clause: excused — {len(excused)} exempted violation(s) in "
            f"{marker}..HEAD; this is a visible debt, not a clean run"
        )
    else:
        print("ledger clause: clean — no commit after the marker cites row numbers")
    return 0

if __name__ == "__main__":
    sys.exit(main())
