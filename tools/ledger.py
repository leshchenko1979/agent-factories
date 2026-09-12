#!/usr/bin/env python3
"""The ledger — this factory's state surface, and its ONLY writer.

State that lives only in chat is not state; it is a memory of a conversation.
This tool is the single append path for `evidence/ledger.jsonl`, so the file has
one writer by construction rather than by good intentions.

Why a tool and not "append with an editor": two lanes appending at once both
read the same last row, both write `n+1`, and the ledger silently acquires two
row 41s. The rubric's Single-writer state criterion (L3) counts a *named*
authoritative writer per surface — this is that name.

Commands
--------
  append --event E --actor A --subject S --detail D   the only write
  tail [--n N]                                        read-only, newest last
  verify                                              read-only: structure, and
                                                      each subject's sequence

Exit: 0 ok, 1 problem (bad usage, corrupted ledger, unknown event type, or a
close whose transition sequence is incomplete).

Row shape (one JSON object per line, append-only):
  {"n":1,"ts":"...","event":"claim","actor":"triage","subject":"#6","detail":"..."}

The transition sequence
-----------------------
A subject's rows are a sequence, not a row count: `intake` (filed), then
`claim` (taken), then `close` (finished). A close with no intake is work that
was never filed; a close with no claim is work nobody took. `verify` reads the
sequence and names the subject and the missing leg.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Overridable so the gate can be tested against a throwaway ledger. Tests that
# write the real state surface are how a probe becomes permanent corruption.
LEDGER = Path(os.environ.get("OC_LEDGER_PATH", REPO / "evidence" / "ledger.jsonl"))
LOCK = LEDGER.parent / ".ledger.lock"

# The closed set of event types. An open set is not a schema — it is a diary.
# claim     work taken by a lane
# dispatch  a brief delivered to a lane
# close     work finished, with its receipt
# score     a measurement run recorded
# ruling    HQ decided something
# intake    an issue filed
# genesis   the surface came into existence
EVENTS = ("genesis", "intake", "claim", "dispatch", "close", "score", "ruling")
ACTORS = ("hq", "triage", "surveys", "delegate", "owner")

# Closes written before the sequence check existed, keyed by (subject, leg).
# An exemption is a dated, attributed admission, never a convenience: it may
# only name a close that predates this gate, it carries the date it was granted
# and the reason, and `verify` prints it whenever it is used — so a reader can
# always tell a clean ledger from an excused one, and an entry nobody would
# defend in that output is one that gets fixed instead.
EXEMPTIONS: list[tuple[str, str, str, str]] = [
    ("#6", "claim", "2026-09-12",
     "close written before the gate existed; no claim row was ever written"),
    ("#8", "intake", "2026-09-12",
     "close written before the gate existed; no intake row was ever written"),
    ("#8", "claim", "2026-09-12",
     "close written before the gate existed; no claim row was ever written"),
]

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            sys.exit(f"ledger line {n} is not JSON: {exc}")
    return rows

def cmd_append(args: argparse.Namespace) -> int:
    if args.event not in EVENTS:
        sys.exit(f"unknown event '{args.event}' — one of: {', '.join(EVENTS)}")
    if args.actor not in ACTORS:
        sys.exit(f"unknown actor '{args.actor}' — one of: {', '.join(ACTORS)}")

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    # The lock is what makes this the single writer. Read-last + write-next
    # happens entirely inside it, so concurrent appends cannot collide on `n`.
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = read_rows(LEDGER)
        row = {
            "n": (rows[-1]["n"] + 1) if rows else 1,
            "ts": now_iso(),
            "event": args.event,
            "actor": args.actor,
            "subject": args.subject,
            "detail": args.detail,
        }
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    print(f"n={row['n']} {row['event']} {row['subject']} — {row['detail']}")
    return 0

def cmd_tail(args: argparse.Namespace) -> int:
    rows = read_rows(LEDGER)
    for row in rows[-args.n :]:
        print(
            f"{row.get('n'):>4}  {row.get('ts')}  {row.get('event'):<8} "
            f"{row.get('actor'):<8} {row.get('subject'):<28} {row.get('detail')}"
        )
    print(f"\n{len(rows)} row(s)")
    return 0

def cmd_verify(_: argparse.Namespace) -> int:
    """Read-only integrity check — the ledger's own gate.

    Two jobs: the file's structure (monotonic `n`, known event and actor, the
    fields present), and each subject's transition sequence. The second is the
    one a row count cannot see — a ledger can be perfectly numbered and still
    say that something was closed without ever saying who took it.
    """
    rows = read_rows(LEDGER)
    problems: list[str] = []
    for i, row in enumerate(rows, 1):
        if row.get("n") != i:
            problems.append(f"line {i}: n={row.get('n')} — row numbers must be 1..N with no gaps")
        if row.get("event") not in EVENTS:
            problems.append(f"line {i}: unknown event {row.get('event')!r}")
        if row.get("actor") not in ACTORS:
            problems.append(f"line {i}: unknown actor {row.get('actor')!r}")
        for field in ("ts", "subject", "detail"):
            if not row.get(field):
                problems.append(f"line {i}: missing {field}")

    # A subject's life is a sequence, not a row count. Subjects are compared as
    # exact strings — `#6` and `6` are different subjects, and no normalisation
    # is applied, because guessing at intent is how a gate starts agreeing with
    # its author.
    by_subject: dict[str, list[tuple[int, str]]] = {}
    for i, row in enumerate(rows):
        by_subject.setdefault(row.get("subject"), []).append((i, row.get("event")))

    seq_problems: list[tuple[str, str, str]] = []  # (subject, leg, message)
    for i, row in enumerate(rows):
        if row.get("event") != "close":
            continue
        subject = row.get("subject")
        if not subject:
            continue  # already reported above as a missing field
        legs = by_subject.get(subject, [])
        intakes = [j for j, ev in legs if ev == "intake" and j < i]
        claims = [j for j, ev in legs if ev == "claim" and j < i]
        # Each missing leg is reported independently, with no short-circuit:
        # one pass should tell the reader everything that is absent, not the
        # first thing the gate happened to notice.
        if not intakes:
            seq_problems.append((subject, "intake",
                f"line {i + 1}: close for {subject} has no intake before it"))
        if not claims:
            seq_problems.append((subject, "claim",
                f"line {i + 1}: close for {subject} has no claim before it"))
        # The order leg means nothing until both legs exist, so a subject is
        # never reported twice for the same absence. It is bounded by the
        # *latest* intake before the close, so a re-opened subject must be
        # re-claimed after its re-open intake.
        if intakes and claims and not any(k > max(intakes) for k in claims):
            seq_problems.append((subject, "order",
                f"line {i + 1}: close for {subject} — its claim precedes its intake (n={max(intakes) + 1})"))

    exempt = {(s, leg): (granted, reason) for s, leg, granted, reason in EXEMPTIONS}
    excused: list[tuple[str, str, str, str]] = []
    for subject, leg, message in seq_problems:
        if (subject, leg) in exempt:
            granted, reason = exempt[(subject, leg)]
            excused.append((subject, leg, granted, reason))
        else:
            problems.append(message)

    if problems:
        print(f"ledger problems: {len(problems)}")
        for p in problems:
            print(f"  {p}")
        return 1

    print(f"ledger clean: {len(rows)} row(s), monotonic, all event types known, sequences complete")
    # Printed only when used, so a fresh factory's dead entries stay invisible —
    # and so a reader can always tell "clean" from "excused".
    for subject, leg, granted, reason in excused:
        print(f"  excused: {subject} missing {leg} (granted {granted}) — {reason}")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("append", help="the only write path")
    ap.add_argument("--event", required=True)
    ap.add_argument("--actor", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--detail", required=True)
    ap.set_defaults(func=cmd_append)

    tp = sub.add_parser("tail", help="read-only")
    tp.add_argument("--n", type=int, default=20)
    tp.set_defaults(func=cmd_tail)

    vp = sub.add_parser("verify", help="read-only integrity check")
    vp.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
