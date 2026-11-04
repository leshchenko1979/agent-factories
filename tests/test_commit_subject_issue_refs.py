#!/usr/bin/env python3
"""Gate: a commit that cites a CLOSED issue carries its own ledger receipt.

Origin (issue #529, ruled at ledger n=3966). A commit subject naming an issue is how
this factory links work to its board item. Once that item is CLOSED the citation stops
being a pointer to open work and becomes a claim about a settled unit, and a claim with
no receipt is exactly the class the ledger exists to make visible. Measured on the full
history before this gate landed: 180 commits make 736 such claims with no row of their
own. That is why the predicate is bounded by a DECLARED marker rather than applied to
history: a history-wide form would be permanently red, and a gate nobody can green is a
gate the next lane learns to ignore.

**The predicate.** For each commit, every `#NNN` in its SUBJECT is examined. `T` is the
`ts` of the ledger's `close` row for `NNN`. If the commit's AUTHOR date is strictly
greater than `T`, the commit must itself ADD a ledger row whose `subject` names `NNN`;
otherwise it is RED, and the report names the commit, the issue and BOTH instants. No
close row for `NNN` means the issue is not settled, so the citation is ordinary work
reference and the commit is GREEN.

**Why strictly greater, and why that is not a loophole.** The lawful closer is excluded
by construction: the commit lands, and its close row is appended AFTER it, so the
closer's author date is never greater than the close instant. The strict comparison IS
that exclusion — `>=` would flag every closing commit in the history.

**AUTHOR date, never committer date.** A rebase rewrites the committer date — the
age-preserving catch-up in the publish runbook depends on exactly that — so a
committer-date predicate would judge a rewritten commit by when it was replayed instead
of when it was written. The author date survives the rewrite.

**The marker is DECLARED FACTORY DATA.** This file is byte-paired into `TEMPLATE/`
(`tests/test_template_sync.py`), so an instant baked here would ship into every factory
that copies this tree, where it names nothing. The `marker` key of
`docs/commit-subject-issue-refs.json` — which is never shipped — is its one reader:
commits whose author date is not greater than it are not judged. Three outcomes, and
the difference between them is the point:
  * declared and parseable -> judged over that range;
  * declared and MALFORMED -> FAIL loudly. The factory named a parameter it cannot
    honour, and that is a defect, not an absence;
  * absent -> SKIP, naming the route. A factory that has declared nothing says so
    rather than passing vacuously.

**Offline, and UNREADABLE is never green (#271).** No `gh`. The population is git's own
history and the ledger's own bytes. A population that cannot be read is a FAIL carrying
the reason, never a silent pass — and the population is PRINTED on every run, so
"examined 0" is never mistaken for "clean".

Run:  python3 tests/test_commit_subject_issue_refs.py
Exit: 0 in range and clean (or excused); 1 on any violation or unreadable population.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER_PATH = "evidence/ledger.jsonl"
EXEMPTIONS_PATH = "docs/commit-subject-issue-refs.json"

# The key a factory sets in its own data file to anchor the clause in its own history.
MARKER_KEY = "marker"

# An issue citation, in a commit subject or in a ledger row's subject. The `\b` is
# load-bearing: without it a colour token such as `#1234abc` would read as a citation.
ISSUE_REF = re.compile(r"#(\d+)\b")

# An exemption is keyed by a full git sha. Asserted rather than assumed: a short sha or a
# tag would match nothing while looking like it should.
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# The instant form the marker accepts. Explicit and narrow: `datetime.fromisoformat`
# accepts forms whose zone is absent, and a naive instant compared against a `Z`-stamped
# one raises instead of judging.
INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def subject_issues(text: str) -> list[int]:
    """Every issue number cited in `text`, ascending and de-duplicated.

    Factored so synthetic subjects can probe it: a rule that has only ever seen good
    input has not been shown to reject bad input.
    """
    return sorted({int(n) for n in ISSUE_REF.findall(text or "")})


def parse_instant(value: object) -> datetime | None:
    """`value` as a naive UTC instant, or `None` when it is not one.

    One reader for every instant this gate compares: a ledger `ts`, a git author date and
    the declared marker all pass through here, so the three can never be compared in two
    different time bases.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    if "." in text:  # fractional seconds carry no information this gate compares on
        head, _, tail = text.partition(".")
        text = head + "Z" if tail.endswith("Z") else head + tail[-6:]
    if not INSTANT.match(text):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _git(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True
    )
    return proc.returncode, proc.stdout, proc.stderr


def repo_toplevel() -> Path | None:
    """The git top level containing this gate, so a copy in a subdirectory still works."""
    rc, out, _ = _git("rev-parse", "--show-toplevel")
    return Path(out.strip()) if rc == 0 and out.strip() else None


def exemptions_file() -> Path:
    """The factory's own data, resolved against the git top level.

    Resolved the same way as the ledger, and for the same reason: this file's own
    location moves between `tests/` and `TEMPLATE/tests/`.
    """
    return (repo_toplevel() or REPO) / EXEMPTIONS_PATH


def load_data(path: Path) -> tuple[dict, list[str]]:
    """`(data, problems)` from the factory's own file. Absent means declared nothing."""
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"{path.name} is not JSON: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{path.name}: expected a JSON object"]
    return data, []


def validate_exemptions(raw: object, name: str) -> tuple[dict[str, dict], list[str]]:
    """`({full_sha: entry}, problems)` from the `exemptions` list.

    Anything malformed is a problem, never a silent pass: an exemption list that
    silently does nothing is a gate lying about its own coverage.
    """
    problems: list[str] = []
    if raw is None:
        return {}, problems
    if not isinstance(raw, list):
        return {}, [f"{name}: 'exemptions' must be a list"]
    entries: dict[str, dict] = {}
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            problems.append(f"{name}: entry {i} is not an object")
            continue
        sha = item.get("sha")
        if not isinstance(sha, str) or not FULL_SHA.match(sha):
            problems.append(
                f"{name}: entry {i} names a sha that is not a full 40-character "
                f"lowercase hex sha: {sha!r}"
            )
            continue
        if not item.get("reason"):
            problems.append(f"{name}: entry {i} ({sha[:12]}) carries no reason")
            continue
        if sha in entries:
            problems.append(f"{name}: entry {i} repeats {sha}")
            continue
        entries[sha] = item
    return entries, problems


def close_instants(rows: list[dict]) -> tuple[dict[int, datetime], list[str]]:
    """`({issue: close instant}, problems)` from the ledger's own `close` rows.

    An issue closed more than once (re-opened, then re-closed) takes its LAST close: the
    citation is judged against the state the ledger most recently settled it in.
    """
    closes: dict[int, datetime] = {}
    problems: list[str] = []
    for row in rows:
        if row.get("event") != "close":
            continue
        ts = parse_instant(row.get("ts"))
        if ts is None:
            problems.append(f"a close row carries an unparseable ts: {row.get('ts')!r}")
            continue
        for issue in subject_issues(str(row.get("subject", ""))):
            if issue not in closes or ts > closes[issue]:
                closes[issue] = ts
    return closes, problems


def ledger_rows() -> tuple[list[dict] | None, list[str]]:
    """The ledger's rows, or `None` when the population cannot be read (#271)."""
    top = repo_toplevel()
    path = (top or REPO) / LEDGER_PATH
    if not path.is_file():
        return None, [f"{LEDGER_PATH} is missing — the population cannot be read"]
    rows: list[dict] = []
    problems: list[str] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            problems.append(f"{LEDGER_PATH}:{i} is not JSON")
    if not rows:
        return None, problems + [
            f"{LEDGER_PATH} is empty — the population cannot be read"
        ]
    return rows, problems


def commit_rows() -> tuple[list[tuple[str, str, datetime, str]], list[str]]:
    """`[(full_sha, short_sha, author_instant, subject)]`, newest first."""
    rc, out, err = _git("log", "--format=%H\x1f%h\x1f%aI\x1f%s", "HEAD")
    if rc != 0:
        return [], [f"git log failed — the population cannot be read: {err.strip()}"]
    rows: list[tuple[str, str, datetime, str]] = []
    problems: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        author = parse_instant(parts[2])
        if author is None:
            problems.append(f"{parts[1]}: unparseable author date {parts[2]!r}")
            continue
        rows.append((parts[0], parts[1], author, parts[3]))
    return rows, problems


def commits_touching_ledger() -> tuple[set[str], list[str]]:
    """Every commit that touches the ledger, as full shas. Cheap: no patch bodies.

    The cheap half of the receipt lookup's coverage guard. `git log -p` over the whole
    history costs ~46 s on this tree, so the patch bodies are read over a SCOPED range;
    this list is what proves the scoped read saw every commit it had to.
    """
    top = repo_toplevel()
    if top is None:
        return set(), [f"{REPO} is not inside a git work tree"]
    rc, out, err = _git("log", "--format=%H", "HEAD", "--", str(top / LEDGER_PATH))
    if rc != 0:
        return set(), [f"git log failed — the population cannot be read: {err.strip()}"]
    return {line.strip() for line in out.splitlines() if line.strip()}, []


def added_ledger_rows(since: str | None = None) -> tuple[dict[str, list[dict]], list[str]]:
    """`{commit_sha: [row, ...]}` — the ledger rows each commit itself ADDS.

    One `git log -p` pass rather than a `git show` per commit. `since` scopes it to a
    range, which is the difference between ~46 s over this history and ~0.4 s: measured,
    and the reason the caller carries a coverage guard rather than trusting the scope.
    A merge commit is included (`-m`) because 30 merges in this history touch the ledger,
    and a plain `git show` of a merge prints no diff at all — a receipt read that
    silently skips merges is a green that never looked.
    """
    top = repo_toplevel()
    if top is None:
        return {}, [f"{REPO} is not inside a git work tree"]
    rev = ["HEAD"] if since is None else [f"--since={since}", "HEAD"]
    rc, out, err = _git(
        "log",
        "-p",
        "-m",
        "--unified=0",
        "--format=%x00%H",
        *rev,
        "--",
        str(top / LEDGER_PATH),
    )
    if rc != 0:
        return {}, [f"git log -p failed — added rows cannot be read: {err.strip()}"]
    added: dict[str, list[dict]] = {}
    problems: list[str] = []
    current: str | None = None
    for line in out.splitlines():
        if line.startswith("\x00"):
            current = line[1:].strip()
            added.setdefault(current, [])
            continue
        if current is None or not line.startswith("+") or line.startswith("+++"):
            continue
        text = line[1:].strip()
        if not text:
            continue
        try:
            added[current].append(json.loads(text))
        except json.JSONDecodeError:
            problems.append(f"{current[:12]}: an added ledger line is not JSON")
    return added, problems



def judged_pairs(
    commits: list[tuple[str, str, datetime, str]],
    closes: dict[int, datetime],
    added: dict[str, list[dict]],
    marker: datetime,
) -> list[tuple[str, str, int, datetime, datetime]]:
    """`[(sha, short, issue, author_instant, close_instant)]`, one per receiptless claim.

    A PURE function of its four arguments, so synthetic history can drive every arm —
    including the ones real history happens not to contain.
    """
    pairs: list[tuple[str, str, int, datetime, datetime]] = []
    for sha, short, author, subject in commits:
        if author <= marker:
            continue
        for issue in subject_issues(subject):
            close_ts = closes.get(issue)
            if close_ts is None or author <= close_ts:
                continue
            receipt = any(
                issue in subject_issues(str(row.get("subject", "")))
                for row in added.get(sha, [])
            )
            if receipt:
                continue
            pairs.append((sha, short, issue, author, close_ts))
    return pairs


def probe() -> list[str]:
    """Every arm of the predicate, driven by synthetic input.

    A gate that has only ever seen a clean tree has not been shown to reject a dirty
    one, so each rejection path is exercised here rather than assumed.
    """
    failures: list[str] = []

    for text, want in (
        ("#529 gate lands", [529]),
        ("no issue here", []),
        ("#529 and #607 both", [529, 607]),
        ("#529 and #529 again", [529]),
        ("colour #1234abc is not an issue", []),
        ("version=3 is not an issue", []),
    ):
        got = subject_issues(text)
        if got != want:
            failures.append(f"probe: subject_issues({text!r}) must be {want}, got {got}")

    for value, ok in (
        ("2026-11-04T00:00:00Z", True),
        ("2026-11-03T11:51:10+00:00", True),
        ("2026-11-03T11:51:10.123Z", True),
        ("2026-11-03", False),
        ("2026-11-03T11:51:10", False),
        ("not an instant", False),
        (None, False),
        (1770000000, False),
    ):
        got = parse_instant(value) is not None
        if got != ok:
            failures.append(f"probe: parse_instant({value!r}) must parse={ok}, got {got}")

    marker = parse_instant("2026-10-01T00:00:00Z")
    closes = {529: parse_instant("2026-10-27T09:00:00Z")}
    cases = (
        # (label, author date, rows the commit adds, in range?, expected violations)
        ("a citation after the close with no receipt",
         "2026-10-28T00:00:00Z", [], True, 1),
        ("a citation after the close WITH its own receipt",
         "2026-10-28T00:00:00Z", [{"subject": "#529 follow-up"}], True, 0),
        ("a receipt naming a DIFFERENT issue does not excuse it",
         "2026-10-28T00:00:00Z", [{"subject": "#607 unrelated"}], True, 1),
        ("the lawful closer, authored before its own close row",
         "2026-10-26T00:00:00Z", [], True, 0),
        ("a citation before the marker is out of range",
         "2026-09-30T00:00:00Z", [], False, 0),
        ("a citation at exactly the marker is out of range",
         "2026-10-01T00:00:00Z", [], False, 0),
        ("a citation at exactly the close instant is out of range",
         "2026-10-27T09:00:00Z", [], True, 0),
    )
    for label, author_text, receipts, want_in_range, want in cases:
        author = parse_instant(author_text)
        # The arm must exercise the predicate it CLAIMS. An arm whose commit sits
        # outside the judged range proves nothing about the comparison it names, and
        # would pass for the wrong reason — the vacuous arm this assertion exists to
        # catch, found in this gate's own first draft.
        got_in_range = author > marker
        if got_in_range != want_in_range:
            failures.append(
                f"probe: {label} must be in range={want_in_range}, got {got_in_range}"
            )
            continue
        commits = [("a" * 40, "aaaaaaa", author, "#529 work")]
        added = {"a" * 40: receipts} if receipts else {}
        got = len(judged_pairs(commits, closes, added, marker))
        if got != want:
            failures.append(f"probe: {label} must yield {want} violation(s), got {got}")

    unclosed = judged_pairs(
        [("b" * 40, "bbbbbbb", parse_instant("2026-11-02T00:00:00Z"), "#999 work")],
        closes,
        {},
        marker,
    )
    if unclosed:
        failures.append("probe: an issue with no close row must never be a violation")

    entries, problems = validate_exemptions(
        [
            {"sha": "c" * 40, "reason": "r"},
            {"sha": "deadbeef", "reason": "r"},
            {"sha": "d" * 40},
            {"sha": "c" * 40, "reason": "again"},
        ],
        "probe.json",
    )
    if len(entries) != 1:
        failures.append(f"probe: exactly one exemption must validate, got {len(entries)}")
    if len(problems) != 3:
        failures.append(
            f"probe: three malformed exemptions must be problems, got {len(problems)}"
        )

    return failures


def main() -> int:
    problems = probe()

    data_path = exemptions_file()
    data, data_problems = load_data(data_path)
    problems.extend(data_problems)
    exemptions, exemption_problems = validate_exemptions(
        data.get("exemptions", []), data_path.name
    )
    problems.extend(exemption_problems)

    raw_marker = data.get(MARKER_KEY)
    if raw_marker is None and not data_problems:
        print(
            f"SKIP: {EXEMPTIONS_PATH} declares no {MARKER_KEY!r}, so this factory has "
            "not anchored the clause. Declare the instant from which a commit citing a "
            "closed issue must carry its own ledger receipt — the commit that lands this "
            "gate — to begin judging. Until then this gate examines nothing, and says so "
            "rather than passing vacuously."
        )
        for line in problems:
            print(f"  FAIL {line}")
        return 1 if problems else 0

    marker = parse_instant(raw_marker)
    if marker is None:
        problems.append(
            f"{EXEMPTIONS_PATH}: {MARKER_KEY!r} is not an instant of the form "
            f"YYYY-MM-DDTHH:MM:SSZ: {raw_marker!r} — a declared parameter that cannot "
            "be honoured is a defect, not an absence"
        )
        for line in problems:
            print(f"  FAIL {line}")
        return 1

    rows, ledger_problems = ledger_rows()
    problems.extend(ledger_problems)
    commits, commit_problems = commit_rows()
    problems.extend(commit_problems)
    ledger_commits, touch_problems = commits_touching_ledger()
    problems.extend(touch_problems)

    # The receipt lookup reads patch bodies over a SCOPED range, because the full walk
    # costs ~46 s against ~0.4 s scoped. The scope is a filter on COMMITTER date, so it
    # is a superset of what is needed in normal history and can be short only under clock
    # skew — the direction that turns a receipt into a false RED rather than a false
    # green. Either way it is VERIFIED, never trusted: every in-range commit that touches
    # the ledger must appear in the scoped read, and one that does not sends this gate
    # back to the full walk.
    added, added_problems = added_ledger_rows(raw_marker)
    problems.extend(added_problems)
    needed = {c[0] for c in commits if c[2] > marker} & ledger_commits
    missing = needed - set(added)
    if missing:
        added, added_problems = added_ledger_rows(None)
        problems.extend(added_problems)
        print(
            f"receipts: the scoped read missed {len(missing)} commit(s) that touch the "
            "ledger — re-read over the full history"
        )
        still_missing = needed - set(added)
        if still_missing:
            problems.append(
                f"the ledger's added rows could not be read for {len(still_missing)} "
                "commit(s) — the population cannot be read"
            )

    if rows is None or not commits:
        for line in problems:
            print(f"  FAIL {line}")
        return 1

    closes, close_problems = close_instants(rows)
    problems.extend(close_problems)

    in_range = [c for c in commits if c[2] > marker]
    judged = judged_pairs(commits, closes, added, marker)
    print(
        f"issue receipts: examined {len(in_range)} commit(s) after {raw_marker} "
        f"(declared) against {len(closes)} closed issue(s); "
        f"{len(judged)} citation(s) carry no receipt"
    )

    excused: list[tuple[str, dict]] = []
    for sha, short, issue, author, close_ts in judged:
        entry = exemptions.get(sha)
        if entry is None:
            problems.append(
                f"{short} cites #{issue}, closed at "
                f"{close_ts.strftime('%Y-%m-%dT%H:%M:%SZ')}, at author date "
                f"{author.strftime('%Y-%m-%dT%H:%M:%SZ')} and adds no ledger row "
                f"naming #{issue}"
            )
        else:
            excused.append((sha, entry))

    # A stale exemption matches nothing, so it inflates the count of visible debt while
    # excusing nothing. Reported rather than ignored.
    for sha in sorted(set(exemptions) - {s for s, _, _, _, _ in judged}):
        problems.append(
            f"exemption {sha} matches no violation after {raw_marker} — a stale "
            "exemption excuses nothing; remove it or correct the sha"
        )

    for sha, entry in excused:
        print(f"  excused: {sha} — {entry.get('reason', '')}")

    if problems:
        for line in problems:
            print(f"  FAIL {line}")
        return 1

    if excused:
        print(
            f"issue receipts: excused — {len(excused)} exempted citation(s) after "
            f"{raw_marker}; this is a visible debt, not a clean run"
        )
    elif not in_range:
        # An empty range is not a clean history. Saying "clean" here would be the
        # vacuous pass this repo forbids: the verdict would describe a population of
        # zero, and a reader would take it as a judgement on commits that exist.
        print(
            f"issue receipts: nothing judged — no commit is authored after "
            f"{raw_marker}, so this run says nothing about the tree's history"
        )
    else:
        print(
            f"issue receipts: clean — {len(in_range)} commit(s) after {raw_marker} "
            "judged, none cites a closed issue without a ledger row of its own"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
