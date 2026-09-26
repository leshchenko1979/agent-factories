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
    AUTHORIZED_ACTORS_BY_EVENT,
    DeclarationUnavailable,
    DeclarationUnreadable,
    boundary_for,
    load_exemptions,
    parse_ts,
)

# The field predicate is shared with both schema gates (#88, ledger n=405 clause 5), on the
# same bare-neighbour import and for the same reason: `stage_tool`'s closure walker resolves
# a neighbour by that name when it stages a throwaway tree.
from field_predicate import (
    declared_keys,
    declared_telemetry_provenance,
    declares_field,
    split_canonical_run,
)

# The reconstruction predicate — which rows are reconstructed claims and the interval
# recomputed from the two rows' own `ts` values — is shared with the gate that judges the
# self-declaration, on the same bare-neighbour import and for the same reason: two private
# copies of one predicate drift in silence, and the drift lands on exactly the rows that
# matter (`n=405` clause 5, `n=599`).
from reconstruction import interval_line, reconstructed_claims

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


def session_to_role(session_id: str | None = None) -> tuple[str | None, str]:
    """The role of the lane that is WRITING, derived from its session.

    `OPENCRABS_SESSION_ID` is exported into every tool subprocess the daemon
    spawns, so the identity of the writer is already mechanical — the kit simply
    never asked for it. Resolution reuses the registry's own lane resolver, the
    same code that renders `registry/state.json`, so a lane the registry resolves
    resolves here, and a lane it cannot place is refused BY NAME rather than
    defaulted. A default is how a repair gets stamped as the Worker by a lane
    that never said so.

    Returns `(role, reason)`. `role` is None when the session cannot be resolved,
    and `reason` then names what failed — never a silent fallback.
    """
    sid = (session_id or os.environ.get("OPENCRABS_SESSION_ID") or "").strip()
    if not sid:
        return None, "OPENCRABS_SESSION_ID is not set, so the writing lane is unidentifiable"
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    try:
        import registry  # noqa: PLC0415 — lazy: a fixture append must not pay for it
    except Exception as exc:  # an import failure is environmental, never an identity
        return None, f"the lane resolver is unavailable (registry import failed: {exc})"
    try:
        bindings, errors = registry.all_bindings()
    except Exception as exc:
        return None, f"the lane resolver is unavailable (binding read failed: {exc})"
    if not bindings:
        detail = f" ({'; '.join(errors)})" if errors else ""
        return None, f"no live binding was readable{detail}"
    try:
        paths = registry.live_fragment_paths([])
    except Exception as exc:
        return None, f"the lane resolver is unavailable (fragment read failed: {exc})"
    for path in paths:
        data, err = registry.load_fragment(path)
        if err or not isinstance(data, dict):
            continue
        chat_id = registry.FACTORY_CHATS.get(data.get("factory"))
        for lane in data.get("lanes") or []:
            if not isinstance(lane, dict):
                continue
            resolved = registry.resolve_lane(lane, bindings, {}, chat_id)
            if resolved.get("session_id") and resolved["session_id"] == sid:
                role = resolved.get("role") or lane.get("role")
                if role:
                    return str(role), ""
    return None, f"session {sid} matches no lane declared in {len(paths)} fragment(s)"


def resolve_actor(
    declared: str | None, fixture: bool, bootstrap: bool = False
) -> tuple[str | None, str, str]:
    """The actor for a row, and WHICH of the two it is: `(role, reason, origin)`.

    `origin` is `"derived"` when the role came from the writing session, and
    `"declared"` when a FIXTURE named it. The distinction is load-bearing at the
    call site rather than here, because the two identities are subject to
    different law: a derived role is a LANE and is checked against the
    authorization matrix, while a declared one belongs to a fixture that is not a
    lane at all and has no row in that matrix. Returning it from the one function
    that knows which happened keeps the call site from re-deriving the question.

    `fixture` says the target is NOT the live ledger — a redirected
    `OC_LEDGER_PATH` or a `--subprocess` sub-ledger. A fixture names its own
    actors: a throwaway ledger has no live lane to bind to, so a declared actor
    there is the fixture's declaration and not a claim about who is writing. The
    derivation is still the default when none is given, so a probe can exercise
    it without an env var.

    THE LIVE LEDGER IS UNCHANGED BY THAT CONCESSION, and the reason is the seam
    itself: reaching the live ledger requires the absence of both overrides, so
    the only rows the live path accepts are ones whose actor was derived. A
    fixture cannot smuggle a role into the live ledger by declaring it, because
    declaring it is what marks the target as a fixture.

    `bootstrap` is the ONE case the live path cannot derive, and it is the row
    that BRINGS THE SURFACE INTO EXISTENCE. The derivation reads fragments to map
    a session to a lane; a factory's fragment is enrolled at BOOTSTRAP step 4d,
    which comes AFTER step 4b writes the genesis row — so at that instant the
    resolver is asked a question its own input does not yet exist to answer.
    Measured 2026-09-25 on a clean fixture built from step 4b: the genesis append
    was REFUSED (`matches no lane declared in 0 fragment(s)`), so a factory
    following the step exactly could not stand up its own ledger.

    IT IS BOUNDED BY AN EMPTY LEDGER, never by the event name alone, and that is
    what keeps it from being a hole: the caller sets `bootstrap` only when the
    target is the live ledger AND carries zero rows. So it is reachable exactly
    once per factory — and the no-shrink gate forbids a live ledger returning to
    empty, which closes the only route by which it could be re-entered. A
    declared actor here is a statement about who ran the bootstrap, which is the
    best available answer at the one instant where no lane exists to be asked.
    """
    if fixture or bootstrap:
        if declared:
            return declared, "", "declared"
        derived, reason = session_to_role()
        if derived:
            return derived, "", "derived"
        return None, f"no actor was given and none could be derived: {reason}", "derived"
    derived, reason = session_to_role()
    if derived:
        if declared and declared != derived:
            return None, (
                f"actor '{declared}' does not match the role this session resolves to "
                f"('{derived}') — identity is derived from OPENCRABS_SESSION_ID, not declared"
            ), "derived"
        return derived, "", "derived"
    return None, reason, "derived"

# Closes written before the sequence check existed, keyed by (subject, leg).
# An exemption is a dated, attributed admission, never a convenience: it names
# the subject, the leg, the date it was granted, the reason, and the PROOF — an
# EXTERNAL RECEIPT the reader can check without trusting this file, never a
# restatement of the omission. `verify` prints every entry it uses, so a reader
# can always tell a clean ledger from an excused one, and an entry nobody would
# defend in that output is one that gets fixed instead.
#
# PROOF IS REQUIRED, and it is what admits a POST-gate entry (#52 clause 3,
# ledger n=318). The two cases are not the same question: a leg missing on a
# close written BEFORE the gate existed is excused by the boundary itself, while
# a leg missing on a close written AFTER it is excused only by a receipt that
# establishes why no lawful repair was available — a pushed row cannot be
# renumbered (clause 1), and a missing leg cannot be appended, because order is
# what is broken. An entry with no proof is NOT ADMITTABLE: `verify` refuses it
# at the point it would excuse an omission, so the omission stays a problem. That
# is the doctrine above made mechanical rather than a rule a lane must remember.
# The sequence exemptions are FACTORY DATA in their own file, loaded at the point they are
# used -- `docs/ledger-exemptions.json`, whose skeleton is
# `docs/ledger-exemptions.example.json`. They were inline here until 2026-09-25, carrying
# three of THIS factory's pre-gate closes (`#6`, `#8`, both 2026-09-12) and the rulings that
# granted them, which is a sha that must not ship to every new factory and a defect that is
# not the member's. `SKILL.md` section 11 states the rule in terms -- "an exemption table
# holding the entries as FACTORY DATA in its own file and never inline in the gate" -- and
# the three sibling surfaces (`docs/ledger-commit-exemptions.json`,
# `docs/ledger-no-shrink-exemptions.json`, `docs/ledger-retirements.json`) already followed
# it. This was the last one inline.
EXEMPTIONS_REL = "docs/ledger-exemptions.json"

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
    # THE ORDER LEG IS RETIRED (2026-09-25, plan 2646d31a step 5). It read `claim
    # before intake` as a defect, and the clause is gone because the two rows are
    # written by TWO LANES whose wake latencies are independent: intake is
    # Triage's row and the claim is the implementer's, so the inversion is the
    # designed outcome of a latency gap rather than an error by either lane.
    # Measured before retiring it: 6 instances across 3 factories, and on #161 the
    # claim still preceded the intake by 1m46s even though the filing lane
    # dispatched Triage in the SAME TURN as the filing -- the implementer was idle
    # and woke in 10s while Triage was mid-turn. A rule that fires on the outcome
    # of that race accuses nobody and costs every occurrence a re-claim.
    #
    # WHAT SURVIVES IS PRESENCE, and it is the half that caught the real defect:
    # a close must have BOTH legs somewhere before it, which is the `#137` shape
    # that sat silent for 35 hours. Presence is checkable without asking a lane to
    # control another lane's timing; precedence is not. A claim that lands AFTER
    # its close is still caught, because `claims` is read positionally.
    return problems

def cmd_append(args: argparse.Namespace) -> int:
    if args.event not in EVENTS:
        sys.exit(f"unknown event '{args.event}' — one of: {', '.join(EVENTS)}")
    # THE TARGET DECIDES WHICH IDENTITY LAW APPLIES, and it is decided BEFORE the
    # actor is resolved because the resolver needs to know. A `--subprocess`
    # append writes a domain sub-ledger and a redirected `OC_LEDGER_PATH` writes a
    # throwaway file; both are FIXTURES, and the seam that redirects them is the
    # same seam that makes their actor declarations legitimate. Only the live
    # ledger's path reaches the strict branch, and reaching it requires BOTH
    # overrides to be absent — so no declaration can smuggle a role into the live
    # ledger. Measured 2026-09-25 (#binding probes): the first cut of this change
    # keyed on `OC_LEDGER_PATH` alone, so `--subprocess` fixtures began failing at
    # the resolver ("no live binding was readable") — a staged tool copy has no
    # fleet manifest to resolve against, and the seam's own probe caught it.
    fixture = bool(os.environ.get("OC_LEDGER_PATH")) or bool(getattr(args, "subprocess", None))
    # BOOTSTRAP — the one live-path case that cannot be derived, and it is bounded by an
    # EMPTY ledger rather than by the event name. A factory's fragment is enrolled at
    # step 4d, after step 4b writes this row, so the resolver has nothing to resolve
    # against; measured 2026-09-25, the genesis append was refused and a factory could
    # not stand up its own ledger. Requiring zero rows makes it reachable exactly once
    # per factory, and the no-shrink gate forbids a live ledger returning to empty.
    bootstrap = (
        not fixture
        and args.event == "genesis"
        and not read_rows(LEDGER)
    )
    actor, actor_why, actor_origin = resolve_actor(args.actor, fixture, bootstrap)
    if actor is None:
        sys.exit(f"ledger append refused: {actor_why}")
    args.actor = actor
    if args.actor not in known_actors():
        sys.exit(f"unknown actor '{args.actor}' — one of: {', '.join(known_actors())}")
    # THE MATRIX BINDS A LANE, NOT A FIXTURE. It answers "is this ROLE allowed to
    # write this EVENT", and a fixture-declared actor has no row in it because a
    # fixture is not a lane — the pinned vocabulary in `probe_actors_path` is the
    # whole point of that seam. A derived role always has a row, because the
    # derivation resolves through the same registry the matrix is written for.
    authorized = AUTHORIZED_ACTORS_BY_EVENT.get(args.event, ())
    if authorized and actor_origin == "derived" and args.actor not in authorized:
        sys.exit(
            f"ledger append refused: actor '{args.actor}' is not authorized for a "
            f"'{args.event}' row (authorized: {', '.join(authorized)}) — membership is "
            "not authorization, and the matrix is enforced here so an unauthorized row "
            "is refused when it is written rather than reported a day later"
        )

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
            # ONE form, and it is the bare NEIGHBOUR import -- the same form the three
            # sibling imports at the head of this file use, and for the same reason:
            # this tool runs as `python3 tools/ledger.py`, so `tools/` is on the path,
            # while a dotted `tools.telemetry` import would need the REPO ROOT there --
            # and `tools/__init__.py` does not exist, so `tools` is a PEP 420 namespace
            # package and that form can only ever fail. It was the FIRST form tried and
            # it never succeeded: measured directly (#129), the dotted form raised
            # ImportError while the bare form resolved, in the normal CLI form, in the
            # same process. Collapsing the chain to the one reachable form also removes
            # a level of nesting from the block below.
            try:
                from telemetry import extract_task_telemetry
            except ImportError:
                extract_task_telemetry = None

            # A `telem` of None is NOT an empty measurement: it is the extractor saying it
            # has NO WINDOW BASIS, and #130 part 3 is the ruling that it must SAY SO rather
            # than invent one. It used to substitute `now - 300` for a window it had never
            # measured, so a close row whose subject had no `claim` row shipped
            # `duration=300s` -- a CONSTANT that every consumer read as a measurement
            # (n=405 clause 6: absence must be STATED, never manufactured). BOTH causes of
            # None land in the branch below, which states the absence in #129's spelling.
            telem = (extract_task_telemetry(args.subject, ledger_path=target_ledger)
                     if extract_task_telemetry else None)
            if telem is not None:
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
                    provenance = "measured"
                elif not declares_field(detail, "duration"):
                    # The COMPLEMENT of the append above, and the half that was missing.
                    # The two branches have DIFFERENT populations, and the boundary is the
                    # `> 0` test: a window LONGER than a second is the guard above's, a
                    # window of ZERO seconds is this one's. Every append above is guarded
                    # on its value being `> 0`, so a close row whose window was too short
                    # to contain a turn shipped SILENCE -- and the case is SYSTEMATIC, not
                    # incidental: a lane that claims and closes together at the end of a
                    # work item writes both rows inside the same second, so the window
                    # holds nothing and every cost and yield figure computed from that row
                    # silently degrades (n=405 clause 6: absence must be STATED, never
                    # silent). The RECEIPTED instance is n=607 (#98): claim and close both
                    # stamped 2026-09-19T17:57:10Z, a ZERO-SECOND window, no telemetry
                    # declared -- committed, and the guard above provably cannot reach it.
                    # `duration_sec` IS the window the extractor already used, so stating
                    # it needs no new plumbing, and the `duration=` spelling keeps ONE
                    # token per field -- it is the key `field_predicate` already reads for
                    # a unit-carrying window. `duration=0s` is the honest reading: it says
                    # the window was too short, which IS the finding. Guarded on the
                    # DECLARED field so an author's own duration is never duplicated.
                    detail = f"{detail} duration={telem.get('duration_sec', 0)}s".strip()
                    provenance = "measured"
                else:
                    # THE TOOL CONTRIBUTED NOTHING, AND THE ROW NOW SAYS SO (#130 part 2).
                    # This is the branch every HAND-TYPED row reaches: the extractor found
                    # its window basis present and its five keys already declared, so it
                    # added nothing -- and #130's class lives exactly here, because the
                    # values in the row are the AUTHOR's, not a measurement. HQ measured all
                    # three candidate structural predicates (position, completeness, value
                    # equality) and each FAILED, so the writer states it instead.
                    provenance = "typed"
                # PROVENANCE, CARRIED (#130 part 2). The five keys above are TOOL-OWNED: a
                # consumer must be able to tell a value the tool TOOK from one an author
                # TYPED, and no structural read of a row can make that distinction, so the
                # WRITER states it. `telemetry=` is the field #129 introduced for the
                # absence case; these are its other two values. Written once, from the
                # branch that decided it, and only when the row does not already declare
                # one -- two tokens for one field have no canonical reading (SKILL.md
                # section 8) -- which is also why the read is POSITIONAL through the shared
                # predicate rather than a substring test here.
                if not declared_telemetry_provenance(detail):
                    detail = f"{detail} telemetry={provenance}".strip()
            else:
                # TWO CAUSES LAND HERE, AND THE ROW NOW SAYS SO (#129, #130 part 3).
                # `extract_task_telemetry` resolving to None used to skip this whole
                # block in silence: the row was appended, rc was 0, and NOTHING in it
                # said no measurement had been taken -- a close row that reads as
                # measured while carrying none. That is n=405 clause 6, "absence must
                # be STATED, never silent", applied to the guard's own availability
                # rather than to the window it used. The class is receipted: EIGHT
                # post-guard close rows shipped with no telemetry at all (n=169, 173,
                # 210, 341, 370, 399, 607, 686), and for SIX of them the cause is
                # established BY VARIATION -- both import forms raised ImportError
                # because the writer's `sys.path[0]` was neither the repo root nor
                # `tools/`, so the truthiness gate above skipped the block entirely.
                # The token names the FIELD and its STATE, so a reader can see WHY the
                # row carries no numbers; it is not one of the five keys
                # `field_predicate` reads, so it declares no measurement.
                if not declared_telemetry_provenance(detail):
                    detail = f"{detail} telemetry=unavailable".strip()

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

        # THE SETTLEMENT RECEIPT, AND WHY IT IS THE TOOL'S TO WRITE (#96, ruling n=745;
        # superseded in part by the simplification this block implements).
        #
        # WHAT WAS WRONG. Settlement is `append the close row, then verify`, so the receipt
        # must cover the row it certifies -- and the receipt has to live IN that row. Those
        # two requirements cannot both hold in one append, so the law resolved it by asking
        # the AUTHOR to declare `rows=<count>` where the count must be at least the row's
        # own number. The author cannot know that number: it is assigned three lines above,
        # INSIDE this lock. The only way to satisfy the predicate was to PREDICT
        # `current_count + 1`, which is right until a peer appends in between -- measured
        # across all five factory ledgers, 2 of 17 declaring closes were off by exactly one
        # for exactly that reason, and both are recorded as permanent debt because an
        # append-only ledger has no repair space for a wrong number.
        #
        # So the declaration was retired and the guarantee moved HERE, where the value is
        # not a prediction but a fact this function already holds: `row["n"]` IS the count
        # the sequence check above covered, because the check ran with the close row present
        # at index `len(rows)`. The receipt is therefore a SECOND row -- the law's own
        # framing, a `run` row authored on behalf of the settlement -- and it is written
        # inside the SAME lock as the row it receipts, so no peer can interleave.
        #
        # WHY A SECOND ROW AND NOT A FIELD IN THE FIRST. A field would have to state the
        # count of a ledger that includes the row carrying it, which is the self-reference
        # that produced the prediction in the first place. The receipt is a row ABOUT a row,
        # so it sits after it and needs no such trick: `verified_rows=N` in row N+1 is a
        # claim about rows 1..N, every one of which already existed when it was written.
        #
        # WHY `run` AND NOT `close`. A second close row would re-enter the sequence index
        # for the subject and be read by `verify` as another settlement of the same unit.
        # `run` is the event this ledger already uses for "the tool did something and says
        # so" -- `repair` writes its own beside the row it corrects, and this mirrors that.
        #
        # WHY IT CARRIES NO `outcome=`. A run row declaring an outcome ENTERS
        # `first_pass_yield_population` (`tools/audit.py`), and a settlement receipt is
        # SELECTION-BIASED -- it is written only where a settlement ran -- so admitting it
        # would make the published yield structurally optimistic. Same reasoning as the
        # duty receipt's `duty=` key (ruled at ledger n=1041); the field is absent by
        # construction, not by convention.
        #
        # MAIN LEDGER ONLY, matching the sequence check above: a sub-ledger is a domain
        # event stream whose vocabulary has no `close`, so there is no sequence to receipt.
        receipt = None
        if args.event == "close" and target_ledger == LEDGER:
            receipt = {
                "n": row["n"] + 1,
                "ts": now_iso(),
                "event": "run",
                "actor": args.actor,
                "subject": args.subject,
                "detail": (
                    f"SETTLEMENT RECEIPT for the close row at n={row['n']} — the sequence "
                    f"check ran with that row present and covered verified_rows={row['n']} "
                    f"row(s) of {args.subject}, and found no problem"
                ),
            }
            with open(target_ledger, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    prefix = f"[{args.subprocess}] " if getattr(args, "subprocess", None) else ""
    print(f"{prefix}n={row['n']} {row['event']} {row['subject']} — {row['detail']}")
    if receipt is not None:
        print(f"{prefix}n={receipt['n']} run {receipt['subject']} — {receipt['detail']}")
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
    actor, actor_why, _actor_origin = resolve_actor(
        args.actor, bool(os.environ.get("OC_LEDGER_PATH"))
    )
    if actor is None:
        sys.exit(f"ledger repair refused: {actor_why}")
    args.actor = actor
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
        # THE RE-DECLARATION REFUSAL (#104, ruled at ledger n=620 PART 4). The sentence
        # the insertion rule below rests on — "a `key=value` append EXTENDS the run and is
        # safe either way" — holds only when the key is NEW. An append that introduces a
        # key the row's canonical run ALREADY declares leaves the row carrying one field
        # twice, and a reader that takes the last occurrence as canonical then reads the
        # appended value while the row's own declaration still stands beside it. Refusing
        # costs nothing lawful: repair's lawful case is a row INCOMPLETE against a declared
        # invariant, and an incomplete row is MISSING the key, never carrying it twice.
        #
        # Both sides are read through the SHARED predicate and both are scoped to a
        # canonical run. The row's run is the row's own declaration, so prose in its head
        # is not a declaration of the field; the appended text is read the same way, so a
        # prose note that merely NAMES a field is not refused. The refusal happens HERE —
        # before `rows[index]` is rebuilt and before the atomic replace — so a refused
        # repair leaves the ledger byte-identical.
        re_declared = [
            key for key in declared_keys(appended) if key in declared_keys(old_detail)
        ]
        if re_declared:
            names = ", ".join(repr(key) for key in re_declared)
            sys.exit(
                f"ledger repair refused: --append-detail declares {names}, which "
                f"n={args.n}'s canonical run ALREADY declares — a `key=value` append "
                f"extends the run only when the key is NEW, and a field carried twice has "
                f"no canonical reading (#104, ruled at ledger n=620 PART 4). Repair a row "
                f"MISSING a field, never one that already carries it."
            )
        # The appended text goes BEFORE the canonical run, never after it (#91, ruled at
        # ledger n=572 PART 3). A row's trailer is POSITIONAL — the run of `key=value`
        # tokens at the END of the detail — so text placed after the run TERMINATES it
        # and the row's declared telemetry silently leaves the trailing run that every
        # trailer-scoped reader stops at. Measured on n=303: its telemetry was canonical
        # when the row was written, and a repair note appended after it displaced
        # cost_usd=2.7719 out of the fleet total. A `key=value` append EXTENDS the run
        # safely when its key is NEW; a prose append does not, and the tool cannot know
        # which it was given — EXCEPT when the key is one the run already declares, which
        # the refusal above settles before this point (#104, ruled at ledger n=620 PART 4).
        # Inserting before the run is correct for every append that reaches here, so no
        # further judgement is required.
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

def _read_rows_at(rev: str, path: Path) -> list[dict]:
    """The rows committed at `rev` for `path`, or a LOUD exit when unreadable.

    `--against` is asked a question about a REVISION, so a revision that cannot be
    read is not "no changes" — it is no answer. Failing open here would report a
    clean comparison over an empty population, which is the shape this repo has
    already ruled against (a truncated log window is not an empty one).
    """
    try:
        rel_path = path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        sys.exit(f"verify --against: {path} is outside {REPO}, so no revision can be read for it")
    text = _git_show(rev, rel_path)
    if text is None:
        sys.exit(
            f"verify --against: cannot read {rel_path} at {rev!r} — is the revision "
            f"fetched, and is the file tracked there?"
        )
    rows: list[dict] = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            sys.exit(f"verify --against: {rel_path} at {rev!r} line {n} is not JSON: {exc}")
    return rows

def _verify_against(rev: str, path: Path, working: list[dict]) -> int:
    """Compare the working ledger against its committed self at `rev`.

    Clause 1 of the #52 ruling says a row's IDENTITY — `(n, ts, event, actor,
    subject)` — is immutable once pushed, because `n` is what an external citation
    means: the same number quietly describing a different row changes what someone
    else's reference points at. The version-control defence for that was a sentence
    a reader had to reconstruct from `git log`; this is the command that reads it.

    Identity violations are reported and are FATAL — clause 1 has no exception.
    Content changes are reported too, and they are a different question: clause 2
    permits a correction to a row's `detail` when the row itself discloses it, so a
    changed detail is fatal only when the row does not carry that disclosure. The
    marker is the row's own `REPAIR NOTE`, the token the ruling names and the rows
    corrected under it actually carry. It is a DISCLOSURE, not proof the disclosure
    is true: it makes the edit visible to this command, and the git diff remains the
    audit of what it says.

    Additions are reported and are NOT fatal. A ledger that grows is the normal
    state; clause 1 protects the identity of rows already published, not the file's
    length.
    """
    committed = _read_rows_at(rev, path)
    by_n_working = {row.get("n"): row for row in working}
    by_n_committed = {row.get("n"): row for row in committed}

    def identity(row: dict) -> tuple:
        return tuple(row.get(k) for k in ROW_IDENTITY)

    def without_n(row: dict) -> tuple:
        return tuple(row.get(k) for k in ROW_IDENTITY if k != "n")

    added: list[dict] = []
    removed: list[dict] = []
    identity_changes: list[tuple[int, dict, dict]] = []  # (n, working row, committed row)
    content_changes: list[tuple[dict, bool]] = []

    for n, row in by_n_working.items():
        other = by_n_committed.get(n)
        if other is None:
            added.append(row)
            continue
        if identity(row) != identity(other):
            identity_changes.append((n, row, other))
        elif row.get("detail") != other.get("detail"):
            content_changes.append((row, "REPAIR NOTE" in (row.get("detail") or "")))

    # A row that MOVED is reported as a move, not as a delete beside an insert: the
    # reader asked what happened to the rows, and "removed n=3, added n=4" describes
    # the same fact twice without saying the row survived.
    #
    # The move has TWO shapes, and only the first is visible to a reader who thinks in
    # terms of the file's length. (i) A number VACATED: a committed row's number is gone
    # from the working file and its content stands elsewhere. (ii) A PERMUTATION, which
    # is what a renumber actually looks like in a ledger that stays contiguous — every
    # number still exists, so nothing is "added" or "removed", yet two rows have swapped
    # places and each number now describes the other's work. A detector that only knew
    # shape (i) would report a swapped pair as two ordinary identity changes and never
    # say the rows MOVED, which is the fact a reader needs; the probe written for this
    # clause is what surfaced the gap, by failing to reach this branch at all.
    ident_to_committed: dict[tuple, list[int]] = {}
    for cn, crow in by_n_committed.items():
        ident_to_committed.setdefault(without_n(crow), []).append(cn)

    moves: list[tuple[int, int, dict]] = []  # (from n, to n, the row that moved)

    for cn, crow in by_n_committed.items():
        if cn in by_n_working:
            continue
        twin = next((w for w in added if without_n(w) == without_n(crow)), None)
        if twin is not None:
            moves.append((cn, twin.get("n"), crow))
            added.remove(twin)
        else:
            removed.append(crow)

    still_changed: list[tuple[int, dict, dict]] = []
    for n, row, other in identity_changes:
        elsewhere = [cn for cn in ident_to_committed.get(without_n(row), []) if cn != n]
        if elsewhere:
            moves.append((elsewhere[0], n, row))
        else:
            still_changed.append((n, row, other))
    identity_changes = still_changed

    undisclosed = [row for row, disclosed in content_changes if not disclosed]
    changes = (len(identity_changes) + len(moves) + len(added) + len(removed)
               + len(content_changes))

    if not changes:
        print(f"ledger vs {rev}: no change ({len(working)} row(s) compared)")
        return 0

    print(f"ledger vs {rev}: {changes} change(s)")
    for row in removed:
        print(f"  REMOVED     n={row.get('n')} subject={row.get('subject')!r} "
              f"event={row.get('event')!r}")
    for line in identity_changes:
        n, row, other = line
        diffs = [
            f"{k} {other.get(k)!r} -> {row.get(k)!r}"
            for k in ROW_IDENTITY
            if k != "n" and row.get(k) != other.get(k)
        ]
        print(f"  IDENTITY    n={n} subject={row.get('subject')!r}: " + ", ".join(diffs))
    for from_n, to_n, row in moves:
        print(f"  RENUMBERED  n={from_n} -> n={to_n} subject={row.get('subject')!r} "
              f"event={row.get('event')!r}: the row MOVED — a number is a citation, "
              f"so a row that survives under a different one is reported as a move")
    for row, disclosed in content_changes:
        print(f"  CONTENT     n={row.get('n')} subject={row.get('subject')!r}: detail "
              f"changed ({'disclosed by a REPAIR NOTE' if disclosed else 'NO DISCLOSURE'})")
    # Additions are bounded in the listing but never in the count: a comparison against a
    # distant revision can carry hundreds of them, and a report nobody can read is how a
    # real line in it gets missed. The fatal categories above are printed in full — they
    # are the ones a reader must act on, and they are rare by construction.
    for row in added[:20]:
        print(f"  ADDED       n={row.get('n')} subject={row.get('subject')!r} "
              f"event={row.get('event')!r}")
    if len(added) > 20:
        print(f"  ADDED       … and {len(added) - 20} more")

    fatal = len(identity_changes) + len(moves) + len(removed) + len(undisclosed)
    if fatal:
        print(
            f"ledger vs {rev}: {fatal} fatal change(s) — a row's identity is immutable "
            f"once pushed, and a content change is admitted only by the row's own "
            f"disclosure (#52 clauses 1 and 2)"
        )
        return 1
    print(f"ledger vs {rev}: additions and disclosed corrections only")
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

    # PROOF is what ADMITS a POST-gate entry (#52 clause 3), so a proofless entry is
    # not admittable and is refused HERE — at the point it would excuse an omission —
    # which leaves the omission a problem naming the entry that failed to excuse it.
    # Refusing on the USED path rather than at load keeps a fresh factory's dead
    # entries invisible, exactly as the printed-only-when-used rule below does, and it
    # keeps the refusal where the reader is already looking. This is the doctrine at
    # the top of this module made mechanical: an exemption is a visible debt, and a
    # debt nobody would defend in the output below is one that gets fixed instead.
    # Loaded HERE rather than at import, for the module's own stated reason: refusing on
    # the USED path keeps the refusal where the reader is already looking. ABSENT means the
    # factory has nothing to excuse; a file that EXISTS and cannot be read is a PROBLEM,
    # because "an exemption list that quietly fails to load is indistinguishable from no
    # exemptions" and only the silent case is the hazard.
    try:
        _declared = load_exemptions(REPO)
    except (DeclarationUnavailable, DeclarationUnreadable) as exc:
        problems.append(
            f"the sequence exemptions could not be read, so an omission below may be "
            f"reported that a declaration would have excused: {exc}")
        _declared = []
    exempt = {(s, leg): (granted, reason, proof)
              for s, leg, granted, reason, proof in _declared}
    excused: list[tuple[str, str, str, str]] = []
    for subject, leg, message in seq_problems:
        if (subject, leg) in exempt:
            granted, reason, proof = exempt[(subject, leg)]
            if not proof.strip():
                problems.append(
                    f"{message} — the EXEMPTIONS entry for {subject}/{leg} is not "
                    f"admittable: it carries no proof, and an exemption is admitted "
                    f"by an external receipt, never by the omission it excuses")
                continue
            excused.append((subject, leg, granted, reason))
        else:
            problems.append(message)

    if problems:
        print(f"ledger problems: {len(problems)}")
        for p in problems:
            print(f"  {p}")
        rc = 1
    else:
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
        #
        # The interval prints beside the row (`n=687` clause 1, #115): the interval moved
        # from DECLARED to RECOMPUTED-AND-PRINTED, because the author controls the ACT of
        # declaring and never the interval — the close row's `ts` is assigned by whoever
        # appends the close, under the append lock. So the reader recomputes it from the
        # two rows' own `ts` values and PRINTS it. Both the population predicate and the
        # interval come from `tools/reconstruction.py`, shared with
        # `tests/test_reconstructed_claim_declared.py` — one field predicate, one home
        # (`n=405` clause 5, `n=599`), never a private copy that can drift in silence.
        for row in reconstructed_claims(rows):
            print(f"  {interval_line(row, rows)}")
        rc = 0

    # The revision comparison runs whatever the structure check found: a ledger that is
    # internally consistent can still have had a row's identity changed, which is exactly
    # the case plain `verify` cannot see (the #52 shape — n=302 kept its number and became
    # a different row). Reporting it only on the clean path would hide it on the path where
    # a reader most needs it.
    against = getattr(args, "against", None)
    if against:
        rc = max(rc, _verify_against(against, target_ledger, rows))
    return rc

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("append", help="the only write path")
    ap.add_argument("--event", required=True)
    ap.add_argument(
        "--actor", required=False,
        help="the writing lane's role; DERIVED from OPENCRABS_SESSION_ID and accepted only when it matches",
    )
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
    vp.add_argument(
        "--against", required=False, metavar="REV",
        help="also compare the working ledger against its committed self at REV "
             "(reports every identity change and every content change)",
    )
    vp.set_defaults(func=cmd_verify)

    # `--append-detail` and `--note` are optional to ARGPARSE and required by the handler,
    # so a caller who omits one is told WHY it is required (a repair that appends nothing
    # is not a repair; a repair with no stated reason is indistinguishable from a silent
    # edit). Argparse's own "the following arguments are required" would state neither.
    rp = sub.add_parser("repair", help="correct a row's detail in place, under the append lock")
    rp.add_argument("--n", type=int, required=True, help="the row number to correct")
    rp.add_argument("--append-detail", required=False, help="the text appended to that row's detail")
    rp.add_argument("--note", required=False, help="WHY the correction is lawful; recorded in the run row beside it")
    rp.add_argument(
        "--actor", required=False,
        help="the lane performing the repair; DERIVED from OPENCRABS_SESSION_ID, never defaulted",
    )
    rp.add_argument("--invariant", required=False, help="the declared invariant whose boundary governs the row (default: derived from its event)")
    rp.set_defaults(func=cmd_repair)

    args = parser.parse_args()
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
