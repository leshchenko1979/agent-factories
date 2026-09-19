#!/usr/bin/env python3
"""The ledger — this factory's state surface, and its ONLY writer.

State that lives only in chat is not state; it is a memory of a conversation.
This tool is the single append path for `evidence/ledger.jsonl`, so the file has
one writer by construction rather than by good intentions.

Why a tool and not "append with an editor": two lanes appending at once both
read the same last row, both write `n+1`, and the ledger silently acquires two
row 41s. The rubric's Single-writer state criterion (L3) counts a *named*
authoritative writer per surface — this is that name.

The lock serialises appenders, but it cannot vouch for the file they append to.
A revert — `git checkout -- evidence/ledger.jsonl`, `git restore`, a stale-copy
overwrite — lowers the working file WITHOUT taking the lock, and the next lawful
append then re-issues a row number already committed. So `append` also compares
the working file against the COMMITTED lineage (`origin/main`, degrading to
`HEAD`) and refuses, writing nothing, when the working file is shorter than what
is committed or when any shared row differs. The refusal names the first
divergence. Where no committed lineage is readable at all — a fresh factory, no
remote, an untracked file — the guard warns and proceeds: the guard exists to make
a revert loud, never to block a factory that has nothing to compare against.

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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The declaration's READER is shared with the gates (`tests/ledger_boundary.py`), because
# the repair path and the gates must agree on which rows a boundary governs: two readers
# would drift on exactly the inputs that matter, leaving a gate that excuses a row the
# repair path refuses to correct. Imported as a plain LOCAL module, never as
# `tools.ledger_declaration` — this tool runs as `python3 tools/ledger.py`, so `tools/` is
# already on the path, and `stage_tool`'s closure walker resolves a neighbour by that same
# bare name when it stages a throwaway tree.
from ledger_declaration import (
    DeclarationUnavailable,
    DeclarationUnreadable,
    boundary_for,
    parse_ts,
)

# The field predicate is shared with both schema gates (#88, ledger n=405 clause 5), on the
# same bare-neighbour import and for the same reason: `stage_tool`'s closure walker resolves
# a neighbour by that name when it stages a throwaway tree.
from field_predicate import declares_field, declares_token, split_canonical_run

REPO = Path(__file__).resolve().parent.parent

# The fields that make a row what it is. `detail` is deliberately absent: it is the ONE
# field a lawful repair may extend, and the identity around it is what `verify` and every
# subject-keyed predicate resolve through.
ROW_IDENTITY = ("n", "ts", "event", "actor", "subject")

# Which declared invariant's boundary governs a correction to a row of each event. Only
# `close` has one: `close_row_revision` is the sole declared invariant constraining a row's
# DETAIL. An event with no entry is REFUSED rather than repaired under some other
# invariant's boundary — a boundary that does not govern the row cannot make a correction
# lawful, it only makes it look lawful (#87).
INVARIANT_FOR_EVENT = {"close": "close_row_revision"}
# Overridable so the gate can be tested against a throwaway ledger. Tests that
# write the real state surface are how a probe becomes permanent corruption.
LEDGER = Path(os.environ.get("OC_LEDGER_PATH", REPO / "evidence" / "ledger.jsonl"))
LOCK = LEDGER.parent / ".ledger.lock"
SUBPROCESSES_DIR = Path(os.environ.get("OC_SUBPROCESS_DIR", REPO / "evidence" / "subprocesses"))

# The closed set of event types. An open set is not a schema — it is a diary.
# claim     work taken by a lane
# dispatch  a brief delivered to a lane
# close     work finished, with its receipt
# score     a measurement run recorded
# ruling    HQ decided something
# intake    an issue filed
# genesis   the surface came into existence
# run       a process execution recorded per processes.md
EVENTS = ("genesis", "intake", "claim", "dispatch", "close", "score", "ruling", "run")

# The closed set of actors — the roles a factory's law names as lanes. A role
# that is not listed cannot write a row, so adding one is a law change, never a
# convenience. The core set is exactly the roles this template ships cards for
# (`roles/`), plus `owner`, who directs without being a lane. A factory whose
# law names a lane the core set does not have — a meta-factory's member-comms
# lane, say — declares it in `tools/actors.txt`, one role per line. It lives
# there and not here because this file is copied byte-identically into every
# factory: a lane that only one factory has cannot sit in a constant that must
# match everywhere.
ACTORS = ("hq", "triage", "worker", "carrier", "owner")
ACTORS_FILE = Path(os.environ.get("OC_ACTORS_PATH", Path(__file__).with_name("actors.txt")))


def known_actors() -> tuple[str, ...]:
    """The core actors, plus any this factory declares in `tools/actors.txt`."""
    extra: list[str] = []
    if ACTORS_FILE.exists():
        for line in ACTORS_FILE.read_text(encoding="utf-8").splitlines():
            role = line.split("#", 1)[0].strip()
            if role:
                extra.append(role)
    return ACTORS + tuple(role for role in extra if role not in ACTORS)

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

def _git_show(ref: str, rel_path: str) -> str | None:
    """The committed bytes of `rel_path` at `ref`, or None when unreadable."""
    try:
        proc = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout

def read_committed_rows(path: Path) -> tuple[list[dict] | None, str | None]:
    """The rows the repository has COMMITTED for `path`, and the ref they came from.

    (None, None) means no committed lineage was readable — a fresh factory with
    no commits, no remote, or a file that is not tracked. The caller treats that
    as fail-open: the guard makes a revert loud, it never blocks a factory that
    has nothing to compare against.
    """
    try:
        rel_path = path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        sys.stderr.write(
            "warning: ledger guard: cannot read committed lineage (proceeding fail-open)\n"
        )
        return None, None
    for ref in ("origin/main", "HEAD"):
        text = _git_show(ref, rel_path)
        if text is None:
            continue
        rows: list[dict] = []
        parsed = True
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                parsed = False
                break
        if parsed:
            return rows, ref
        break
    sys.stderr.write(
        "warning: ledger guard: cannot read committed lineage (proceeding fail-open)\n"
    )
    return None, None

def lineage_divergence(
    rows: list[dict], committed_rows: list[dict], ref_name: str
) -> str | None:
    """The first way the working file diverges from the committed lineage, else None.

    Two shapes, both fatal. The working file is SHORTER than what is committed:
    a revert, and the next append would re-issue a committed `n`. Or a shared row
    differs: already-committed history was edited. The message names the row and
    the subject, because "the ledger is inconsistent" is not actionable.
    """
    if len(rows) < len(committed_rows):
        i = len(rows)
        c = committed_rows[i]
        return (
            f"working file has {len(rows)} row(s), but committed lineage "
            f"({ref_name}) has {len(committed_rows)} row(s). First divergence at "
            f"row {i + 1}: committed is n={c.get('n')} subject={c.get('subject')!r}"
        )
    for i, (w, c) in enumerate(zip(rows, committed_rows), 1):
        if (
            w.get("n") != c.get("n")
            or w.get("subject") != c.get("subject")
            or w.get("event") != c.get("event")
        ):
            return (
                f"row {i} diverges from committed lineage ({ref_name}): working "
                f"has n={w.get('n')} subject={w.get('subject')!r} "
                f"event={w.get('event')!r}, committed has n={c.get('n')} "
                f"subject={c.get('subject')!r} event={c.get('event')!r}"
            )
    return None

def index_by_subject(rows: list[dict]) -> dict[str, list[tuple[int, str]]]:
    """Every row's (index, event), grouped by subject — built ONCE per pass.

    The sequence predicate is asked about many subjects in a single pass, so the
    index is built once and handed to it rather than rebuilt per question. Two
    call sites share this: `verify` asks about every close row in history, and
    `append` asks about the one row it is about to write (#98, ruling n=596).
    """
    by_subject: dict[str, list[tuple[int, str]]] = {}
    for i, row in enumerate(rows):
        by_subject.setdefault(row.get("subject"), []).append((i, row.get("event")))
    return by_subject

def sequence_problems(
    by_subject: dict[str, list[tuple[int, str]]], subject: str, index: int
) -> list[tuple[str, str, str]]:
    """What a `close` of `subject` at `index` is missing, as (subject, leg, message).

    ONE predicate, TWO call sites. `verify` asks it about every close row it
    reads; `append` asks it about the row it is about to write, with
    `index = len(rows)` — the line that row will occupy — so the refusal names
    the leg the audit would have named later, at the moment the write would have
    created the defect. The order leg is bounded by the *latest* intake before
    the close, so a re-opened subject must be re-claimed after its re-open.

    Each missing leg is reported INDEPENDENTLY, with no short-circuit: one pass
    should tell the reader everything that is absent, not the first thing the
    predicate happened to notice.
    """
    if not subject:
        return []  # a missing subject is a structural problem, reported as one

    legs = by_subject.get(subject, [])
    intakes = [j for j, ev in legs if ev == "intake" and j < index]
    claims = [j for j, ev in legs if ev == "claim" and j < index]

    problems: list[tuple[str, str, str]] = []
    if not intakes:
        problems.append((subject, "intake",
            f"line {index + 1}: close for {subject} has no intake before it"))
    if not claims:
        problems.append((subject, "claim",
            f"line {index + 1}: close for {subject} has no claim before it"))
    # The order leg means nothing until both legs exist, so a subject is never
    # reported twice for the same absence.
    if intakes and claims and not any(k > max(intakes) for k in claims):
        problems.append((subject, "order",
            f"line {index + 1}: close for {subject} — its claim precedes its intake (n={max(intakes) + 1})"))
    return problems

def cmd_append(args: argparse.Namespace) -> int:
    if args.event not in EVENTS:
        sys.exit(f"unknown event '{args.event}' — one of: {', '.join(EVENTS)}")
    if args.actor not in known_actors():
        sys.exit(f"unknown actor '{args.actor}' — one of: {', '.join(known_actors())}")

    target_ledger = LEDGER
    target_lock = LOCK
    if getattr(args, "subprocess", None):
        sub_name = args.subprocess.strip()
        SUBPROCESSES_DIR.mkdir(parents=True, exist_ok=True)
        target_ledger = SUBPROCESSES_DIR / f"{sub_name}.jsonl"
        target_lock = SUBPROCESSES_DIR / f".{sub_name}.lock"

    target_ledger.parent.mkdir(parents=True, exist_ok=True)
    # The lock is what makes this the single writer. Read-last + write-next
    # happens entirely inside it, so concurrent appends cannot collide on `n`.
    with open(target_lock, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = read_rows(target_ledger)
        # The lock vouches for the appenders, not for the file. A revert
        # lowers the working file outside the lock, and the next lawful
        # append would re-issue a committed `n`. Compare against the
        # committed lineage first, and refuse before anything is written.
        committed_rows, ref_name = read_committed_rows(target_ledger)
        if committed_rows is not None:
            divergence = lineage_divergence(rows, committed_rows, ref_name)
            if divergence:
                sys.exit(f"ledger append refused: {divergence}")
        # A close row is refused at the WRITE PATH when its subject has no
        # preceding intake and claim — the SAME predicate `verify` runs, asked
        # here about the row about to be written, with `index = len(rows)`, the
        # line it will occupy. That is what makes the two call sites one
        # question rather than two rules: a defect is named at the moment it
        # would be created instead of being discovered in history later (#98,
        # ruling n=596).
        #
        # MAIN LEDGER ONLY. A sub-ledger is a domain event stream, not the
        # lifecycle ledger — intake/claim/close are not its vocabulary — so the
        # sequence law does not reach it. Nothing is lost by that: no sub-ledger
        # exists on disk and none carries a close row.
        #
        # NO EXEMPTION SURFACE here, and none is needed: a close appended now
        # can never predate the gate. EXEMPTIONS governs `verify`'s reading of
        # history only, and stays printed there. This does not replace `verify`
        # — the order leg and any row written around this path remain its.
        if args.event == "close" and target_ledger == LEDGER:
            problems = sequence_problems(index_by_subject(rows), args.subject, len(rows))
            if problems:
                sys.exit("ledger append refused: "
                         + "; ".join(message for _subject, _leg, message in problems))
        detail = args.detail
        if args.event == "close":
            try:
                from tools.telemetry import extract_task_telemetry
            except ImportError:
                try:
                    from telemetry import extract_task_telemetry
                except ImportError:
                    extract_task_telemetry = None

            if extract_task_telemetry:
                telem = extract_task_telemetry(args.subject, ledger_path=target_ledger)
                missing = []
                # A substring test here is what made this the third site of the
                # prose-as-data class (#88, n=405 clause 5): a close row whose PROSE
                # mentioned `tokens_out=` suppressed the measurement the tool had
                # genuinely taken, so the row shipped with no telemetry and nothing
                # said so. Test for a DECLARED field, never a mention.
                if not declares_field(detail, "cost_usd") and telem.get("cost_usd", 0.0) > 0:
                    missing.append(f"cost_usd={telem['cost_usd']:.4f}")
                if not declares_field(detail, "tokens_in") and telem.get("tokens_in", 0) > 0:
                    missing.append(f"tokens_in={telem['tokens_in']}")
                if not declares_field(detail, "tokens_out") and telem.get("tokens_out", 0) > 0:
                    missing.append(f"tokens_out={telem['tokens_out']}")
                if not declares_field(detail, "turns") and telem.get("turns", 0) > 0:
                    missing.append(f"turns={telem['turns']}")
                if not declares_field(detail, "duration") and telem.get("duration_sec", 0) > 0:
                    missing.append(f"duration={telem['duration_sec']}s")
                # `outcome=` and `gate=` are VERDICTS, and this trailer used to write
                # `outcome=accepted` and `gate=all-pass` whenever the author stated
                # neither. A verdict nobody recorded must not be written as one, and
                # the default here was the FAVOURABLE value, so First-Pass Yield and
                # Cost / Successful Task could only ever report success (#53, ruling
                # n=333 clause 1). The measurement fields above stay: cost_usd,
                # tokens_in, tokens_out, turns and duration are numbers the tool
                # genuinely took, and taking them is not a judgement.
                if missing:
                    detail = f"{detail} {' '.join(missing)}".strip()

        row = {
            "n": (rows[-1]["n"] + 1) if rows else 1,
            "ts": now_iso(),
            "event": args.event,
            "actor": args.actor,
            "subject": args.subject,
            "detail": detail,
        }
        with open(target_ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    prefix = f"[{args.subprocess}] " if getattr(args, "subprocess", None) else ""
    print(f"{prefix}n={row['n']} {row['event']} {row['subject']} — {row['detail']}")
    return 0

def cmd_repair(args: argparse.Namespace) -> int:
    """Correct ONE row's `detail` in place, then append the record of the repair.

    The ledger is append-only, and this is its single lawful exception: a row whose
    detail is INCOMPLETE against an invariant this factory has DECLARED, and whose own
    timestamp falls AFTER that invariant's declared boundary (#52 clause 2). Everything
    that makes the row what it is — `n`, `ts`, `event`, `actor`, `subject` — is left
    untouched, because a row wrong in one of THOSE is retired by naming it in a new row
    and never edited (SKILL.md §11).

    Two refusals carry the law:

    * A row that PREDATES its invariant's boundary is refused, not repaired. The
      boundary is exactly the statement that the rule was not yet written when that row
      was made, so correcting one backfills a record the factory already agreed to leave
      standing (#53 clause 2).
    * A repair with no `--note` is refused. The note is the only thing separating a
      lawful correction from a silent edit, and a silent edit of an append-only surface
      is the failure this whole section exists to prevent.
    """
    if args.actor not in known_actors():
        sys.exit(f"unknown actor '{args.actor}' — one of: {', '.join(known_actors())}")
    if not (args.note or "").strip():
        sys.exit(
            "ledger repair refused: --note is required — it records WHY the correction "
            "is lawful, and is the only thing distinguishing a repair from a silent edit "
            "of an append-only surface (#52 clause 2)"
        )
    appended = (args.append_detail or "").strip()
    if not appended:
        sys.exit(
            "ledger repair refused: --append-detail is required — a repair that appends "
            "nothing changes nothing"
        )

    target_ledger = LEDGER
    target_lock = LOCK
    if getattr(args, "subprocess", None):
        sub_name = args.subprocess.strip()
        SUBPROCESSES_DIR.mkdir(parents=True, exist_ok=True)
        target_ledger = SUBPROCESSES_DIR / f"{sub_name}.jsonl"
        target_lock = SUBPROCESSES_DIR / f".{sub_name}.lock"

    target_ledger.parent.mkdir(parents=True, exist_ok=True)
    # The SAME lock as `append`, for the same reason: the next row number is computed
    # inside it. A repair holding its own lock would be a second writer, and two writers
    # each reading the same last row each write the same `n`.
    with open(target_lock, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = read_rows(target_ledger)
        committed_rows, ref_name = read_committed_rows(target_ledger)
        if committed_rows is not None:
            divergence = lineage_divergence(rows, committed_rows, ref_name)
            if divergence:
                sys.exit(f"ledger repair refused: {divergence}")

        index = next((i for i, row in enumerate(rows) if row.get("n") == args.n), None)
        if index is None:
            highest = max(
                (row.get("n") for row in rows if isinstance(row.get("n"), int)),
                default=0,
            )
            sys.exit(
                f"ledger repair refused: no row n={args.n} in {target_ledger.name} "
                f"(highest is n={highest})"
            )
        original = rows[index]

        event = original.get("event")
        key = getattr(args, "invariant", None) or INVARIANT_FOR_EVENT.get(event)
        if key is None:
            sys.exit(
                f"ledger repair refused: n={args.n} is a '{event}' row and no declared "
                f"invariant governs that event — name one with --invariant if the "
                f"correction is lawful under a boundary this tool does not map"
            )
        try:
            boundary, declared_text = boundary_for(REPO, key)
        except DeclarationUnavailable as exc:
            sys.exit(
                f"ledger repair refused: cannot establish the boundary for '{key}', so "
                f"this correction cannot be shown lawful rather than a backfill — {exc}"
            )
        except DeclarationUnreadable as exc:
            sys.exit(f"ledger repair refused: {exc}")

        if parse_ts(original["ts"]) < boundary:
            sys.exit(
                f"ledger repair refused: n={args.n} ({original['ts']}) PREDATES the "
                f"boundary declared for '{key}' ({declared_text}) — a row that predates "
                f"the rule is excused and left standing, never corrected (#53 clause 2)"
            )

        # Build the repaired row as a NEW object rather than mutating in place, so the
        # identity check below compares against pre-repair values instead of against
        # itself. A check that cannot fail is not a check.
        identity_before = {field: original.get(field) for field in ROW_IDENTITY}
        old_detail = str(original.get("detail", ""))
        # The appended text goes BEFORE the canonical run, never after it (#91, ruled at
        # ledger n=572 PART 3). A row's trailer is POSITIONAL — the run of `key=value`
        # tokens at the END of the detail — so text placed after the run TERMINATES it
        # and the row's declared telemetry silently leaves the trailing run that every
        # trailer-scoped reader stops at. Measured on n=303: its telemetry was canonical
        # when the row was written, and a repair note appended after it displaced
        # cost_usd=2.7719 out of the fleet total. A `key=value` append EXTENDS the run
        # safely; a prose append does not, and the tool cannot know which it was given.
        # Inserting before the run is correct for both, so no judgement is required.
        head, run = split_canonical_run(old_detail)
        if run:
            # `rstrip`/`lstrip` normalise only the DELIMITERS at the insertion point —
            # the author's interior spacing, punctuation and the run itself are carried
            # through verbatim, so the repaired detail re-reads as the original with one
            # token-sequence inserted ahead of its trailer.
            repaired_detail = f"{head.rstrip()} {appended} {run}".lstrip()
        else:
            # No run to protect: the detail has no canonical trailer, so appending at the
            # end displaces nothing and the historic behaviour stands. A separator is
            # still owed — the caller passes the field alone (`head=<sha>`), and welding
            # it to the previous token (`turns=36head=…`) makes it unreadable as a field
            # to every consumer, including the gate this repair exists to satisfy.
            separator = "" if (not old_detail or old_detail[-1].isspace()) else " "
            repaired_detail = f"{old_detail}{separator}{appended}"
        repaired = {**original, "detail": repaired_detail}

        for field in ROW_IDENTITY:
            if repaired.get(field) != identity_before[field]:
                sys.exit(
                    f"ledger repair refused: {field} would change — row identity is "
                    f"immutable once pushed (#52 clause 1)"
                )

        note = (
            f"repair n={args.n} ({original.get('event')} {original.get('subject')}): "
            f"{args.note.strip()} — appended {appended!r} under invariant '{key}' "
            f"(boundary {declared_text})"
        )
        run_row = {
            "n": (rows[-1]["n"] + 1) if rows else 1,
            "ts": now_iso(),
            "event": "run",
            "actor": args.actor,
            "subject": original.get("subject"),
            "detail": note,
        }

        # Replace-then-append, and the replace is ATOMIC. A rewrite that dies halfway
        # truncates the ledger — the one outcome worse than the incomplete row this
        # command exists to correct — so the new text is built beside it and swapped in
        # with `os.replace`, which is atomic within a filesystem.
        rows[index] = repaired
        tmp = target_ledger.with_name(target_ledger.name + ".repair-tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target_ledger)

        with open(target_ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(run_row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    prefix = f"[{args.subprocess}] " if getattr(args, "subprocess", None) else ""
    print(f"{prefix}repaired n={args.n}: appended {appended!r}")
    print(f"{prefix}n={run_row['n']} run {run_row['subject']} — {note}")
    return 0

def cmd_tail(args: argparse.Namespace) -> int:
    target_ledger = LEDGER
    if getattr(args, "subprocess", None):
        sub_name = args.subprocess.strip()
        target_ledger = SUBPROCESSES_DIR / f"{sub_name}.jsonl"

    rows = read_rows(target_ledger)
    for row in rows[-args.n :]:
        print(
            f"{row.get('n'):>4}  {row.get('ts')}  {row.get('event'):<8} "
            f"{row.get('actor'):<8} {row.get('subject'):<28} {row.get('detail')}"
        )
    print(f"\n{len(rows)} row(s)")
    return 0

def cmd_verify(args: argparse.Namespace) -> int:
    """Read-only integrity check — the ledger's own gate.

    Two jobs: the file's structure (monotonic `n`, known event and actor, the
    fields present), and each subject's transition sequence. The second is the
    one a row count cannot see — a ledger can be perfectly numbered and still
    say that something was closed without ever saying who took it.
    """
    target_ledger = LEDGER
    if getattr(args, "subprocess", None):
        sub_name = args.subprocess.strip()
        target_ledger = SUBPROCESSES_DIR / f"{sub_name}.jsonl"

    rows = read_rows(target_ledger)
    problems: list[str] = []
    for i, row in enumerate(rows, 1):
        if row.get("n") != i:
            problems.append(f"line {i}: n={row.get('n')} — row numbers must be 1..N with no gaps")
        if row.get("event") not in EVENTS:
            problems.append(f"line {i}: unknown event {row.get('event')!r}")
        if row.get("actor") not in known_actors():
            problems.append(f"line {i}: unknown actor {row.get('actor')!r}")
        for field in ("ts", "subject", "detail"):
            if not row.get(field):
                problems.append(f"line {i}: missing {field}")

    # A subject's life is a sequence, not a row count. Subjects are compared as
    # exact strings — `#6` and `6` are different subjects, and no normalisation
    # is applied, because guessing at intent is how a gate starts agreeing with
    # its author. The index is built ONCE and the predicate is asked per close
    # row; `append` asks the SAME predicate about the row it is about to write,
    # so a defect is named at the moment it would be created (#98, n=596).
    by_subject = index_by_subject(rows)
    seq_problems: list[tuple[str, str, str]] = []  # (subject, leg, message)
    for i, row in enumerate(rows):
        if row.get("event") != "close":
            continue
        seq_problems.extend(sequence_problems(by_subject, row.get("subject"), i))

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
    # A RECONSTRUCTED claim DECLARES itself with the token `claim=reconstructed`, and
    # those rows print here, beside the `excused:` lines, for the same reason the
    # exemptions do: clean, excused and reconstructed must never be the same output
    # (#98, ruling n=602 PART 5). A declaration that lived only in prose could be
    # counted only by reading prose — this repo's own ruled class (#88 / n=405
    # clause 5). The scan is scoped to CLAIM rows, because that is the row the token
    # describes; a row of another event that merely QUOTES the token is out of the
    # population before the predicate is asked, which is what keeps a ruling row that
    # defines the token (measured: n=602) from reading as a reconstruction.
    for row in rows:
        if row.get("event") != "claim":
            continue
        if declares_token(row.get("detail"), "claim", "reconstructed"):
            print(f"  reconstructed claim: n={row.get('n')} subject={row.get('subject')}")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("append", help="the only write path")
    ap.add_argument("--event", required=True)
    ap.add_argument("--actor", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--detail", required=True)
    ap.add_argument("--subprocess", required=False, help="optional subprocess domain sub-ledger name")
    ap.set_defaults(func=cmd_append)

    tp = sub.add_parser("tail", help="read-only")
    tp.add_argument("--n", type=int, default=20)
    tp.add_argument("--subprocess", required=False, help="optional subprocess domain sub-ledger name")
    tp.set_defaults(func=cmd_tail)

    vp = sub.add_parser("verify", help="read-only integrity check")
    vp.add_argument("--subprocess", required=False, help="optional subprocess domain sub-ledger name")
    vp.set_defaults(func=cmd_verify)

    # `--append-detail` and `--note` are optional to ARGPARSE and required by the handler,
    # so a caller who omits one is told WHY it is required (a repair that appends nothing
    # is not a repair; a repair with no stated reason is indistinguishable from a silent
    # edit). Argparse's own "the following arguments are required" would state neither.
    rp = sub.add_parser("repair", help="correct a row's detail in place, under the append lock")
    rp.add_argument("--n", type=int, required=True, help="the row number to correct")
    rp.add_argument("--append-detail", required=False, help="the text appended to that row's detail")
    rp.add_argument("--note", required=False, help="WHY the correction is lawful; recorded in the run row beside it")
    rp.add_argument("--actor", required=False, default="worker", help="the lane performing the repair (default: worker)")
    rp.add_argument("--invariant", required=False, help="the declared invariant whose boundary governs the row (default: derived from its event)")
    rp.set_defaults(func=cmd_repair)

    args = parser.parse_args()
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
