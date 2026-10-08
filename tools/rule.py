#!/usr/bin/env python3
"""The atomic ruling act: ONE invocation posts the board ruling comment AND stamps the
ledger `ruling` row — or leaves NEITHER surface touched.

Origin: issue #270, ruled at ledger n=1925, dispatched at n=1927.

WHY A TOOL AND NOT A CONVENTION. A ruling is today two acts in two surfaces — a board
comment (`gh issue comment`) and a ledger `ruling` row (`tools/ledger.py append`) — and
nothing binds them. The board-ruling leg in `tools/patrol_host_state.py` REPORTS the
divergence after the fact; it cannot prevent one, and the class regrew 11 -> 13 while it
watched. A reader does not prevent. #223 shape (2) refused a same-turn convention because
the transition had ZERO READERS; that premise is dead — the leg is the reader — and the
mechanism is still the remedy, because a reader without a writer on the path is a
detector, not a gate.

WHAT MAKES IT ATOMIC. Single entry, single exit, and the two legs are ORDERED so a
failure on either leaves neither surface carrying a half-ruling:

  1. validate    -- the body must OPEN with the canonical head. A refusal here is free:
                    nothing has been posted and nothing has been stamped.
  2. POST        -- the board comment. On failure, return non-zero with NOTHING stamped.
  3. APPEND      -- the ledger `ruling` row, carrying `comment=<id>` in its canonical
                    terminal run. On failure, DELETE the comment just posted, so the
                    board is returned to the state it had before this call.

The residual, stated rather than implied: if leg 2 succeeds and the comment's id cannot
be read back from its own output, the tool refuses to stamp and DELETES the comment it
cannot name. A pairing whose id is unknown cannot be recorded truthfully, and a comment
left behind would be exactly the divergence this tool exists to remove. It is the one
path where the two legs cannot both be undone, so it is loud.

THE HEAD IS NOW ENFORCED, NOT MERELY DECLARED. `RULING_CANONICAL_HEADING` in
`tools/patrol_host_state.py` states the canonical opening and explains that a rule "use
this head" was unenforceable "exactly where it matters" — because the writer was an agent
typing `gh issue comment` and there was no tool on that path. This is the tool on that
path. The predicate is IMPORTED from that module, never restated here: a second copy of
the accepted openings is the drift class this repo files repeatedly, and the reader's
own widening clause (`unmatched_heading_comments`) exists precisely because a spelling
can drift away from the convention.

Run:
  python3 tools/rule.py --issue 270 --body-file /tmp/ruling.md
  python3 tools/rule.py --issue 270 --body-file /tmp/ruling.md --dry-run
Exit: 0 paired (both surfaces), 1 a leg failed (neither surface), 2 refused before any write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# The pairing key's ONE home (#297). Imported, never restated: this writer,
# `tools/ledger.py append` (which refuses a `ruling` row carrying no well-formed
# `comment=<id>`) and the gate `tests/test_ruling_row_recorded.py` all read the SAME key, and
# a private copy in any of them drifts in silence — the writer would put a token on the row
# that the reader does not look for, and the pairing would exist and be invisible. The bare
# neighbour import is the form `tools/ledger.py` uses for the same reason: this tool runs as
# `python3 tools/rule.py`, so `tools/` is on `sys.path`.
from field_predicate import PAIRING_KEY

REPO = Path(__file__).resolve().parent.parent
PATROL = REPO / "tools" / "patrol_host_state.py"
LEDGER_TOOL = REPO / "tools" / "ledger.py"
# The publication predicate's OWN home (#441). `tools/publish.py` already owns the remote
# tip, the grace window and the pusher's bounds; asking it "is row N readable from the
# remote yet?" keeps ONE predicate for one question rather than a second implementation
# here that would drift from the pusher the moment either moved.
PUBLISH_TOOL = REPO / "tools" / "publish.py"

# `gh issue comment` prints the comment's own URL, whose fragment carries its id.
_COMMENT_URL_RE = re.compile(r"#issuecomment-(\d+)")
# `git@github.com:OWNER/NAME.git` and `https://github.com/OWNER/NAME` both land here.
_REMOTE_RE = re.compile(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$")
# The row the append prints: `n=1948 ruling #270 — …`.
_ROW_RE = re.compile(r"\bn=(\d+)\b")

# The trailer key naming the board comment this row was paired with — IMPORTED above from
# its one home, `tools/field_predicate.py` (#297), and never restated here. It sits in the
# row's canonical terminal run (the maximal run of `=`-carrying tokens at the END of
# `detail`), which is what makes it readable by the shared positional reader rather than by
# prose — and it is the SAME key the refuser in `tools/ledger.py` and the gate
# `tests/test_ruling_row_recorded.py` read.


def load_patrol():
    """The heading predicate's OWN home, loaded by PATH.

    `tools/patrol_host_state.py` owns the accepted ruling openings; this tool enforces the
    canonical one. Imported rather than restated, so the writer and the reader cannot
    drift apart — the failure mode that produced `unmatched_heading_comments`.
    """
    spec = importlib.util.spec_from_file_location("_rule_patrol", PATROL)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit(f"rule: cannot load {PATROL} — the heading predicate's home")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_publish():
    """The publication predicate's OWN home, loaded by PATH (#441).

    Imported rather than restated for the reason `load_patrol` gives one screen up: a second
    implementation of "is this row readable from the remote" would answer differently from
    the pusher the moment either moved, and the divergence would be silent.
    """
    spec = importlib.util.spec_from_file_location("_rule_publish", PUBLISH_TOOL)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit(f"rule: cannot load {PUBLISH_TOOL} — the publication predicate's home")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# --- the citation state (issue #441, ruled at ledger n=2907) ---------------------------
#
# A ruling body NAMES ledger rows -- "Intake row: `n=2906`", "rows n=2900-2905" -- and the
# body is posted to the PUBLIC BOARD while the rows it names are, BY CONSTRUCTION, not yet
# readable: this tool stamps the ruling row in the same invocation, and a row committed this
# turn cannot be published this turn (the pusher holds a commit younger than its 900s grace
# window -- #146/n=1168, scoped by #284/e133c87d).
#
# Measured 2026-10-08: two ruling comments named `n=2900-2905` on the public board from
# 06:40:46Z while the commit carrying those rows was not authored until 06:48:39Z and not
# published until 07:09:08Z -- ~28 minutes in which the citation was public and its referent
# existed nowhere a reader could go.
#
# Of the three remedies the ruling offers, the DEFERRED comment is refused because it breaks
# this tool's atomicity (the comment and the row are ONE act, and a comment waiting on a push
# is a third state the two-surface contract has no place for), and the PRE-PUBLISH step is
# refused because a ruling path that pushes is the direct-push anti-pattern #329 removed. The
# third -- an explicit statement of the state -- is what this does.
CITED_ROW_RE = re.compile(r"\bn=(\d+)(?:\s*[\u2013\u2014-]\s*(\d+))?")
CITED_RANGE_MAX = 500

def cited_rows(body: str) -> list[int]:
    """The ledger rows a ruling body NAMES, in order of appearance, deduplicated.

    Two shapes, because the bodies use two: a single `n=2906` (`Intake row: n=2906`) and an
    inclusive range `n=2900-2905`. The range form is not a nicety — it is what the incident
    this note exists for actually said, and a reader that expanded only the first endpoint
    would have declared 2900 unreachable and stayed silent about 2901-2905, i.e. exactly the
    silent-partial-citation defect the ruling is about. A range wider than
    `CITED_RANGE_MAX` is NOT expanded: it is almost certainly a typo or a non-row use of the
    token, and inflating it into hundreds of numbers would make the note unreadable rather
    than more honest.

    It is deliberately NOT the shared positional predicate: that reader answers what a row's
    canonical trailer DECLARES, while this asks what a ruling body MENTIONS — different
    questions over different text.
    """
    seen: list[int] = []
    for match in CITED_ROW_RE.finditer(body):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        span = range(start, end + 1) if start <= end <= start + CITED_RANGE_MAX else (start,)
        for row in span:
            if row not in seen:
                seen.append(row)
    return seen

def read_publication(rows: list[int], *, remote: str | None = None, branch: str | None = None, runner=None) -> dict:
    """The publication state of `rows`, read from the REMOTE's ledger.

    The FETCH is what makes the local tracking ref the remote's tip; without it the ref is a
    cache and the verdict would report the fact in doubt -- the rule `tools/publish.py` states
    at its own top. A FAILED fetch does not abort the ruling (this tool's job is to STATE the
    state, not to require the network), but it is carried into the note, because a stale read
    and a fresh one must never render alike.
    """
    run = runner or _run
    pub = load_publish()
    remote = remote or pub.DEFAULT_REMOTE
    branch = branch or pub.DEFAULT_BRANCH
    fetched = run(["git", "-C", str(REPO), "fetch", remote, branch]).returncode == 0
    state = pub.unpublished_rows(REPO, rows, ref=pub.DEFAULT_TRACKING_REF)
    state["fetched"] = fetched
    return state

def citation_note(rows: list[int], state: dict, instant: str) -> str:
    """The acknowledgement appended to the ruling body before it is posted AND stamped.

    ALWAYS emitted, never only in the bad case: "these rows are readable", "these rows are
    not", and "this ruling names no rows" are three different facts, and a note that appears
    only when something is wrong makes its ABSENCE ambiguous between the other two -- the
    `remote_tip` rule again, where "I could not ask" must never render as "there is nothing to
    ask about".
    """
    where = f"`{state['ref']}`"
    if not state.get("fetched"):
        where += " — the fetch FAILED, so this read is a possibly-stale cache"
    if not rows:
        body = "This ruling names no ledger row, so there is no citation to reach."
    elif state.get("reason"):
        body = (
            f"The publication of the rows named above could NOT be read: {state['reason']} — "
            f"treat them as possibly unreadable and verify before following them."
        )
    elif not state.get("unpublished"):
        body = "Every ledger row named above is readable from the remote."
    else:
        listed = ", ".join(f"`n={row}`" for row in state["unpublished"])
        body = (
            f"This ruling names ledger rows that are **NOT YET READABLE from the remote**: "
            f"{listed}. A reader following those citations reaches nothing until the commit "
            f"carrying them is published — the pusher holds a commit younger than its 900s "
            f"grace window, so this is the designed ordering and not a delay anyone should "
            f"wait on. They become readable when `origin/main`'s `evidence/ledger.jsonl` "
            f"carries them."
        )
    return f"\n\n---\n\n**Citation state (read {instant}, {where}).** {body}\n"

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def citation_acknowledgement(row: str, cited: list[int], state: dict) -> str:
    """The one-line acknowledgement `main()` prints after a PAIRED stamp (#441, property 2).

    Two facts, because the ruling names two: the row THIS invocation stamped is not readable
    either -- it was appended to the working tree and cannot be published until its commit
    clears the pusher's grace window -- and the rows the ruling body CITED are readable or
    not. The stamped row is stated first: it is the one a reader reaches by following this
    tool's own output.
    """
    lines = [
        f"n={row} is NOT YET READABLE from `{state['ref']}` — it was appended to the working "
        f"tree this invocation; publish the commit carrying it before citing it."
        if row != "?"
        else "the stamped row's number could NOT be read from the append output, so its "
             "publication is unstated — read it from the ledger tail."
    ]
    if not cited:
        lines.append("the ruling body names no ledger row, so it cites nothing unreachable.")
    elif state.get("reason"):
        lines.append(f"the cited rows could NOT be checked: {state['reason']}")
    elif state.get("unpublished"):
        listed = ", ".join(f"n={r}" for r in state["unpublished"])
        lines.append(f"cited and NOT readable from `{state['ref']}`: {listed} (stated in the body).")
    else:
        lines.append(f"every cited row is readable from `{state['ref']}` (stated in the body).")
    if not state.get("fetched"):
        lines.append("the fetch FAILED, so the cited-row read is a possibly-stale cache.")
    return " ".join(lines)

def head_problem(body: str, patrol) -> str | None:
    """Why `body` may not be posted as a ruling, or None when it may.

    PURE, so a synthetic body can probe it: a rule that has only ever seen good input has
    not been shown to reject bad input.

    The check is BOUNDARY-CHECKED for the reason `_accepted_heading` is: `startswith`
    alone admits an EXTENSION, so `## RULED-OUT — …` would read as a ruling opening.
    """
    first = ""
    for line in body.splitlines():
        if line.strip():
            first = line.strip()
            break
    if not first:
        return "the ruling body is empty — a ruling with no text is a drop wearing a head"
    canonical = patrol.RULING_CANONICAL_HEADING
    if not first.startswith(canonical):
        return (
            f"the ruling body must OPEN with {canonical!r} (the canonical head); "
            f"this one opens with {first[:70]!r}"
        )
    rest = first[len(canonical):]
    if rest and rest[0].isalnum():
        return (
            f"{first[:70]!r} EXTENDS the canonical head {canonical!r} — the character "
            f"after it must not be alphanumeric, or a different heading reads as this one"
        )
    return None


def build_detail(body: str, comment_id: str) -> str:
    """The row's `detail`: the ruling body, then the pairing token as the LAST token."""
    return f"{body.rstrip()}\n\n{PAIRING_KEY}={comment_id}"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def resolve_repo(declared: str | None) -> str:
    """`OWNER/NAME` for the board, DERIVED from the origin remote when not declared.

    Never a literal: a repository name hardcoded here would be one factory's identity
    shipped into every factory that vendors this file.
    """
    if declared:
        return declared
    proc = _run(["git", "-C", str(REPO), "remote", "get-url", "origin"])
    if proc.returncode != 0:
        raise SystemExit("rule: cannot read the `origin` remote — pass --repo OWNER/NAME")
    match = _REMOTE_RE.search(proc.stdout.strip())
    if not match:
        raise SystemExit(
            f"rule: cannot parse the origin URL {proc.stdout.strip()!r} — pass --repo OWNER/NAME"
        )
    return f"{match.group(1)}/{match.group(2)}"


def delete_comment(repo: str, comment_id: str) -> bool:
    """Undo leg 2. Returns whether the board was actually returned to its prior state."""
    proc = _run(["gh", "api", "-X", "DELETE", f"repos/{repo}/issues/comments/{comment_id}"])
    return proc.returncode == 0


def read_back_comment_id(repo: str, issue: int) -> str | None:
    """The id of the newest comment on `issue` — the fallback when the post's own URL
    could not be parsed. Read from the API rather than guessed."""
    proc = _run(
        ["gh", "api", f"repos/{repo}/issues/{issue}/comments",
         "--jq", ".[-1].id // empty"]
    )
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post a board ruling comment and stamp its ledger `ruling` row, or neither."
    )
    parser.add_argument("--issue", type=int, required=True, help="the board issue number")
    parser.add_argument("--repo", default=None, help="OWNER/NAME; derived from origin when omitted")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--body-file", help="a file holding the ruling body")
    source.add_argument("--body", help="the ruling body as one argument")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="validate and report what would happen; write NOTHING to either surface",
    )
    args = parser.parse_args(argv)

    try:
        body = (
            Path(args.body_file).read_text(encoding="utf-8")
            if args.body_file
            else args.body
        )
    except OSError as exc:
        print(f"rule refused (nothing posted, nothing stamped): {exc}", file=sys.stderr)
        return 2

    patrol = load_patrol()
    problem = head_problem(body, patrol)
    if problem:
        print(f"rule refused (nothing posted, nothing stamped): {problem}", file=sys.stderr)
        return 2

    if args.dry_run:
        # HERMETIC: the dry run touches neither surface AND resolves nothing external --
        # no `gh`, no `git remote`, and (since #441) no fetch either. A validation step that
        # itself needs the network is a step that can fail for reasons the operator did not
        # ask about, and this gate's probes run it inside a bare test tree.
        where = args.repo or "the origin remote"
        print(
            f"rule: DRY RUN — would post a {patrol.RULING_CANONICAL_HEADING!r} comment on "
            f"{where}#{args.issue} and stamp `ruling` for '#{args.issue}' carrying "
            f"{PAIRING_KEY}=<id>; wrote NOTHING\n"
            f"  citation state NOT resolved (hermetic): the live run would name the "
            f"publication of the {len(cited_rows(body))} ledger row(s) this body mentions"
        )
        return 0

    repo = resolve_repo(args.repo)

    # ---- the citation state (#441, ruled at n=2907) --------------------------------
    #
    # Resolved BEFORE either surface is touched, because the note is part of BOTH: the posted
    # comment and the stamped row carry the same text, so a reader who reaches either one
    # learns whether the rows it names were readable at the instant it was written.
    cited = cited_rows(body)
    state = read_publication(cited)
    posted_body = body + citation_note(cited, state, _now_iso())

    # ---- leg 1: the board comment -------------------------------------------------
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(posted_body)
        body_path = handle.name
    posted = _run(
        ["gh", "issue", "comment", str(args.issue), "--repo", repo, "--body-file", body_path]
    )
    if posted.returncode != 0:
        print(
            "rule: the BOARD COMMENT failed, so NOTHING was stamped — no row, no comment:\n"
            f"{posted.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    match = _COMMENT_URL_RE.search(posted.stdout)
    comment_id = match.group(1) if match else read_back_comment_id(repo, args.issue)
    if comment_id is None:
        print(
            "rule: the board comment posted but its id could NOT be read back, so the "
            "pairing cannot be recorded truthfully and NO row was stamped.\n"
            f"  the comment is here and needs a hand: {posted.stdout.strip()!r}\n"
            "  delete it, or stamp its row by hand with the id in the URL above.",
            file=sys.stderr,
        )
        return 1

    # ---- leg 2: the ledger row ----------------------------------------------------
    appended = _run(
        [sys.executable, str(LEDGER_TOOL), "append",
         "--event", "ruling", "--subject", f"#{args.issue}",
         "--detail", build_detail(posted_body, comment_id)]
    )
    if appended.returncode != 0:
        rolled_back = delete_comment(repo, comment_id)
        state = (
            f"comment {comment_id} DELETED — neither surface carries this ruling"
            if rolled_back
            else f"comment {comment_id} COULD NOT BE DELETED — it is on the board alone, "
                 f"which is the divergence this tool exists to remove; delete it by hand"
        )
        print(
            f"rule: the LEDGER APPEND failed, so the board comment was rolled back: {state}\n"
            f"{appended.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    row_match = _ROW_RE.search(appended.stdout)
    row = row_match.group(1) if row_match else "?"
    print(
        f"rule: PAIRED — {repo}#{args.issue}\n"
        f"  comment: https://github.com/{repo}/issues/{args.issue}"
        f"#issuecomment-{comment_id}\n"
        f"  row:     n={row} ({PAIRING_KEY}={comment_id})\n"
        f"  {citation_acknowledgement(row, cited, state)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
