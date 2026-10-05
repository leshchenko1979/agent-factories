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
        # no `gh`, no `git remote`. A validation step that itself needs the network is a
        # step that can fail for reasons the operator did not ask about, and this gate's
        # probes run it inside a bare test tree.
        where = args.repo or "the origin remote"
        print(
            f"rule: DRY RUN — would post a {patrol.RULING_CANONICAL_HEADING!r} comment on "
            f"{where}#{args.issue} and stamp `ruling` for '#{args.issue}' carrying "
            f"{PAIRING_KEY}=<id>; wrote NOTHING"
        )
        return 0

    repo = resolve_repo(args.repo)

    # ---- leg 1: the board comment -------------------------------------------------
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(body)
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
         "--detail", build_detail(body, comment_id)]
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
        f"  row:     n={row} ({PAIRING_KEY}={comment_id})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
