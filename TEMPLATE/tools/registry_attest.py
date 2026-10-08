#!/usr/bin/env python3
"""Dispatch the registry re-attestation brief to every factory HQ.

The anti-rot engine for the DECLARED half. `render` keeps the generated half true by
construction (it reads live state at run time) and the drift gate keeps the committed
render equal to a fresh one, but nothing about a fragment changes when the factory
behind it changes: `attested_at` is a human saying "this still describes us", and only a
clock can ask. That clock is this pacemaker, installed as a namespaced cron —
`<factory>-registry-attest`, per the box's cron-naming law (a bare `registry-attest`
is a claim on a namespace no factory owns alone).

**The brief carries THREE questions, not one.** *Confirm or amend your fragment* keeps the
identity card honest; *confirm or expire your announcements* keeps the peer-facing field
honest; *confirm your job prefix and report any cron row you cannot attribute* carries the
one half of the cron-naming law no gate can reach (#101). The announcements are in the
brief deliberately, not as a second job: a notice is the one field whose value DECAYS
WITHOUT ANYONE EDITING IT — "the auto-switcher is retired" stops being useful the day it is
re-armed, and no diff marks the moment. It needs a clock, and the attest cadence is the
clock already being paid for. The third question is here for the same reason: the edit ban
governs a cron table no single factory owns, so it has no gate and must ride a process — and
the process is a question asked on a cadence that already exists, not a new job.

**Targets are resolved live, never remembered.** A factory's HQ lane is read from its own
fragment's `lanes` (role `hq`) against live `session_bindings` on the profile the fragment
declares, every run. A remembered UUID is a dispatch into the void the moment a topic is
rebound — 2026-09-19: the opencrabs-dev HQ topic changed hands and a notify addressed to
the previous holder was accepted and queued rather than refused, and stranded unread.

**Fail-open, and it says so.** A factory whose HQ cannot be resolved is reported by name
and the rest of the fleet is still dispatched: one factory's missing lane must not silence
the others' attestation. The failure is loud in this run's output, which is what
the pacemaker's own report carries.

**The brief names the route it expects the answer on.** A lane reads "reply on this
session" as ITS OWN, because the notify arrived in that lane's session — so on the
2026-10-01 round four of six lanes answered there and delivered nothing to the
collector, which recovered them only by reading each lane's store. The closing line
therefore names `session_notify` and points at the notify's own `from` header. No id is
written into the text: the header is the live source, so nothing in the brief can go
stale, and the tool's own rule against a declared session id still holds.

**The brief names the READ SOURCE, not only the read action.** #439, the missing twin of
the paragraph above: the brief said "Read it back before answering" and named no source,
so the natural path a lane takes is the shared clone, whose working tree is FROZEN —
measured 2026-10-08 at 143 commits behind, with two fragments read from it three days
stale. The trap is not only a wrong answer: a write-back patch built from that image
would have REVERTED a correct line another lane had already landed, so the stale read
corrupts a write as well as an answer. Q1 therefore names the committed bytes at
`origin/main` (`git fetch` then `git show origin/main:registry/factories/<slug>.json`) or
a worktree checked out there, and says plainly that a shared working tree is not it. The
text IS the mechanism here — nothing else gates it — so a probe asserts the source is
named, and a mutation control proves that probe bites.

**The brief's essentials live in its HEAD, because the classic leg elides the MIDDLE.**
The brief is longer than the classic transport's cap, and the cap is tail-preserving: it
keeps `head = inner*2/3` and `tail = inner-head_len` and drops what is between them (#267,
measured: 2313 chars dropped, QUESTION 3 — which sat 2313 chars in — elided while ANSWER BY
survived). So a target on that leg read Q1, Q2 and the answer instruction and could not
read what it was being asked about its prefix and cron rows, and the loss was invisible
from the send side because the send still succeeded. The remedy is structural rather than a
second variant: a CONDENSED block — all three questions and the answer route — sits ABOVE
the full detail, so any cap that preserves head+tail preserves the essentials.
`tests/test_registry_attest.py` projects the brief through that cap and asserts all four
survive, with the pre-fix shape as its mutation control.

**And the collection leg DECLARES its population** (`--collect`). A round is not
complete because M lanes answered; it is complete when the count of M is accounted for
against the N targets, split into answers that arrived BY NOTIFY and answers RECOVERED
by reading a lane's own session, with every recovery named. The split is measured, not
asserted: `by notify` is read out of the collector's OWN session store, where an
inbound notify lands as a user row whose header names the sender. The rest must be
declared, and a target in neither set is UNACCOUNTED and fails the run. That is the
difference between a gap that is a finding and a gap that is a loss.

Run:  python3 tools/registry_attest.py --check          # resolve and print targets
      python3 tools/registry_attest.py --dry-run        # print the brief, send nothing
      python3 tools/registry_attest.py --dispatch       # send to every resolved HQ
      python3 tools/registry_attest.py --collect [--since ISO] [--recovered SLUG,...]
Exit: 0 every target dispatched (or resolved, for --check; or accounted for, for
      --collect); 1 if any HQ failed to resolve, or any target is unaccounted.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import registry as reg  # noqa: E402

OPENCRABS = "/usr/local/bin/opencrabs"
PROFILE = reg.FACTORY_PROFILE
SENDER = "Meta-Factory Delegate"
BRIEF_TITLE = "Registry re-attestation"

# The two shapes an inbound notify leaves in the RECEIVING session's own store: the full
# uuid in the `session-notify` header, the 8-char short form in the delivery line. BOTH
# are read, because a reader that knows one shape reports the other as silence — and the
# 2026-10-01 round carried one of each. Measured on the collector's store, verbatim:
#   `[session-notify from=6a314aac-94db-4b11-974c-f53decc25b9d]  [infra-factory HQ -> …`
#   `📨 notify from 2646d31a: [HQ 2646d31a → Delegate] FOLLOW-UP to the meta-factory …`
NOTIFY_FROM_FULL = re.compile(r"\[session-notify from=([0-9a-fA-F-]{36})\]")
NOTIFY_FROM_SHORT = re.compile(r"notify from ([0-9a-fA-F]{8}):")

BRIEF = """Registry re-attestation — {slug} ({stamp})

ANSWER BY session_notify TO THE COLLECTOR — reply to the session id in THIS notify's own
`from` header, not into your own session. The collector cannot read your session, so an
answer left there is a gap in the round rather than an answer to it.

THREE QUESTIONS — all three need an answer. Each one is spelled out in full below.

QUESTION 1 — YOUR FRAGMENT. Confirm `registry/factories/{slug}.json` unchanged, or send
back ONLY the fields that changed, as JSON. Read it from the COMMITTED bytes at
`origin/main` — `git fetch` then `git show origin/main:registry/factories/{slug}.json`,
or a worktree checked out there — never a shared working tree, which rots by days.
Read it back before answering.

QUESTION 2 — YOUR ANNOUNCEMENTS. For each entry in your fragment's `announcements`:
STILL HOLDS, or EXPIRED (say why), or AMENDED (send the new text). An empty list is the
honest answer. To ADD an entry, send an OBJECT (id, text, severity, since, affects) —
never a bare string; `evidence` is REQUIRED when severity is warning or critical.

QUESTION 3 — YOUR JOB PREFIX AND YOUR CRON ROWS. (a) PREFIX — the `job_prefixes` entry
your `registry/fleet.json` record declares, and whether it still matches how you name your
jobs. (b) ORPHANS — the set is COMPUTED, not remembered: read `counts.unattributed_jobs`
in `registry/index.json` at `origin/main`. If you have seen a job the render does NOT name
there, name it, the profile home you read it from, and what you saw. "None seen" is a
complete answer, and never disable, delete, edit or repace a job attributed to another
factory.

If every answer is "unchanged", reply CONFIRMED and that is a complete answer.

--- FULL DETAIL BELOW ---

Your factory is one entry in the fleet registry (docs/factory-registry.md). The
GENERATED half of that entry is read live from this box every render, so it cannot
rot. The DECLARED half is yours: it is what you wrote, and only you can say whether
it still describes you. Three questions, and all three need an answer.

QUESTION 1 — YOUR FRAGMENT. Confirm it unchanged, or amend it.
  registry/factories/{slug}.json
  Read it from the COMMITTED bytes at `origin/main`, never from a shared working tree.
  The shared clone on this box is a FROZEN image: it was measured 143 commits behind,
  and two fragments read from it were three days stale. The trap is not only a wrong
  answer — a write-back patch built from the stale image REVERTS a correct line another
  lane has already landed. So, before answering:

      git fetch origin main
      git show origin/main:registry/factories/{slug}.json

  A worktree checked out at `origin/main` is equivalent and is the better surface if you
  need to edit. Reading a path out of your own working copy is NOT equivalent unless you
  have fetched: that copy answers with whatever it was last synced to.

  Read it back before answering. If it still describes the factory — purpose, zone
  (what you own / what you do not own), services, substrates — answer CONFIRMED and
  it gets a fresh attested_at. If anything has moved, send back ONLY the fields that
  changed, as JSON, exactly as you would declare them. Do not send the whole
  fragment; do not paraphrase another lane's field.

QUESTION 2 — YOUR ANNOUNCEMENTS. Confirm each still holds, or expire it.
  Every entry in your fragment's `announcements` is a fact a peer must know before
  working near you. A notice is the one field whose value decays WITHOUT anyone
  editing it: a "this is retired" warning stops being useful the day it is re-armed,
  and nothing in the tree marks that moment. So go through them one at a time and
  answer for each: STILL HOLDS, or EXPIRED (say why), or AMENDED (send the new text).
  If you have nothing to announce, an empty list is the honest answer — do not
  inflate it.

  AMENDING AN ENTRY THAT IS ALREADY THERE. The object is on disk and only its words
  change, so the new `text` IS the whole answer: name the entry and send the
  replacement words. Nothing else is required.

  ADDING AN ENTRY — your list is empty, or you are adding a further notice. Prose is
  NOT sufficient here, because there is no object for the words to amend. The loader
  requires an OBJECT and rejects a bare string with
  `announcements[0]: must be an object`. Send these fields:

    required   id        a short stable slug, unique within your fragment
               text      the fact itself, one or two sentences
               severity  one of: info | warning | critical
               since     the date the fact BEGAN to hold, ISO-8601
               affects   a non-empty list of factory slugs, or the literal
                         `profile` for a notice that concerns the whole box
    optional   scope     one of: profile | factory | lane. A fragment's root admits
                         profile | factory; `lane` belongs inside a lane block
               evidence  a citation a peer can check. REQUIRED when severity is
                         warning or critical — peers act on those, so the notice
                         must carry the thing that supports it
               review_by when this should be looked at again, ISO-8601. It must not
                         precede `since`
               check     the name of a predicate that answers it
    forbidden  session_id, uuid, session — a session is resolved LIVE from
               session_bindings, so a declared one is stale on arrival

  One entry, as it goes into the fragment:
    {{"id": "attest-paused", "text": "Attestation is paused until X.",
      "severity": "warning", "since": "2026-09-25", "affects": ["miidas"],
      "evidence": "ledger n=1234"}}

  THE ENVELOPE IS NOT YOURS TO INVENT. Send the fields you CHANGED — the words, how
  strongly a peer should act, and whom it concerns. The writer derives the rest:
  `id` and `since` are ENVELOPE, and `since` is the instant of THIS answering
  declaration. If a notice began earlier than you can evidence, say so plainly and
  let the writer record the answering instant — do not invent a fact-origin date,
  because a `since` nobody established is a false record and this brief would rather
  have your honest instant than your guess.

QUESTION 3 — YOUR JOB PREFIX AND YOUR CRON ROWS. Confirm the prefix, report what you
  cannot place. Your factory's jobs are named `<your prefix>-<what-it-does>`, and the
  prefix is the one your `registry/fleet.json` record declares in `job_prefixes` — the
  manifest refuses an empty list and refuses two factories whose prefixes overlap, because
  the prefixes are the only reason a job on a shared box can be attributed to its owner at
  all. Two answers, both short:
    (a) PREFIX — your declared prefix, and whether it still matches how you name your jobs.
    (b) ORPHANS — the set is COMPUTED, not remembered. `registry/index.json` carries
        `counts.unattributed_jobs`, and its `jobs` array names each row with
        `owner: null`; read that at `origin/main` and report from it. A remembered list
        drifts: the one returned every round for weeks was four rows long and wrong in
        both directions — it named a job already attributed, and missed the one live
        unattributed job on the box.
        TWO CENSUSES, TWO POPULATIONS. The ATTRIBUTION leg reads the declared profiles
        only; the box-wide floor leg also reads the DEFAULT home. So a job living in the
        default home is outside the attribution population by construction —
        "unattributable" and "unread" are not the same word, and neither is a licence to
        touch the row.
        The cron table is shared and has no single owner, so the rule is: never disable,
        delete, edit or repace a job attributed to another factory, and report a job you
        cannot attribute instead of touching it. Name the job, the profile home you read it
        from, and what you saw. "None seen" is a complete answer.

ANSWER BY session_notify TO THE COLLECTOR — not in your own session. This brief
arrived as a notify, so the sender's session id is already in that notify's own `from`
header; send your answer there, to that id. The collector cannot read your session, so
an answer left in it is only recovered later by a sweep — a gap in the round rather
than an answer to it.

The registry is a collected document: the collector writes your declared fields back
verbatim, and re-renders. You author the field; you do not need to edit the file,
though you may.

Nothing else in this message is work. If every answer is "unchanged", reply
CONFIRMED and that is a complete answer.
"""


def load_fragments() -> list[tuple[Path, dict]]:
    """Every LIVE fragment (the fixtures are not factories and are never attested)."""
    loaded: list[tuple[Path, dict]] = []
    for path in reg.live_fragment_paths([]):
        data, error = reg.load_fragment(path)
        if error:
            print(f"registry-attest: {path}: {error}", file=sys.stderr)
            continue
        loaded.append((path, data))
    return loaded


def hq_targets(fragments: list[tuple[Path, dict]]) -> tuple[list[dict], list[str]]:
    """Resolve each factory's HQ lane session from live bindings. Returns (targets, problems)."""
    bindings, errors = reg.all_bindings()
    problems = list(errors)
    by_profile: dict[str, list[dict]] = {}
    for row in bindings:
        by_profile.setdefault(str(row.get("_profile")), []).append(row)

    targets: list[dict] = []
    for _path, fragment in sorted(fragments, key=lambda item: str(item[1].get("factory"))):
        slug = str(fragment.get("factory"))
        profile = str(fragment.get("profile"))
        hq_lanes = [
            lane for lane in fragment.get("lanes") or []
            if isinstance(lane, dict) and str(lane.get("role")) == "hq"
        ]
        if not hq_lanes:
            problems.append(f"{slug}: no lane declares role `hq` — nothing to wake")
            continue
        if len(hq_lanes) > 1:
            problems.append(
                f"{slug}: {len(hq_lanes)} lanes declare role `hq` "
                f"({', '.join(str(l.get('topic')) for l in hq_lanes)}) — ambiguous owner"
            )
            continue
        lane = hq_lanes[0]
        resolved = reg.resolve_lane(
            lane, by_profile.get(profile, []), {}, chat_id=reg.FACTORY_CHATS.get(slug)
        )
        session_id = resolved.get("session_id")
        if not session_id:
            problems.append(
                f"{slug}: HQ lane `{lane.get('topic')}` (thread {lane.get('thread_id')}) "
                f"on profile `{profile}` did not resolve — {resolved.get('status')}"
            )
            continue
        targets.append(
            {
                "slug": slug,
                "session_id": session_id,
                "thread_id": lane.get("thread_id"),
                "topic": lane.get("topic"),
                "status": resolved.get("status"),
            }
        )
    return targets, problems


def dispatch(target: dict, stamp: str, dry_run: bool) -> tuple[bool, str]:
    """Send one HQ its brief. Returns (sent, detail).

    The elapsed seconds ride in the detail on purpose. Each send is a whole CLI
    invocation, so a six-target run is six process spawns and it is NOT instant: the
    first paced run was killed part-way through and the only surviving evidence was that
    the targets sharing a PREFIX of the send order had answered and the rest had not.
    A duration per target makes the next cut-off legible from the run's own output
    instead of inferable only from who happened to reply.
    """
    text = BRIEF.format(slug=target["slug"], stamp=stamp)
    command = [
        OPENCRABS, "-p", PROFILE, "session", "notify", str(target["session_id"]),
        "--text", text,
        "--sender", SENDER,
        "--title", f"{BRIEF_TITLE} {stamp}",
        "--mode", "turn-end",
        "--format", "json",
    ]
    if dry_run:
        return True, f"dry-run: {len(text)} chars to {target['slug']}"
    started = time.monotonic()
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc} ({time.monotonic() - started:.1f}s)"
    elapsed = time.monotonic() - started
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        return False, f"rc={done.returncode}: {detail[-1] if detail else 'no output'} ({elapsed:.1f}s)"
    line = (done.stdout or "").strip()
    try:
        payload = json.loads(line)
        return True, f"delivery={payload.get('status') or payload.get('delivery') or 'ok'} ({elapsed:.1f}s)"
    except (json.JSONDecodeError, AttributeError):
        return True, f"{line[:80] or 'ok'} ({elapsed:.1f}s)"


def _instant(value: str) -> int | None:
    """Parse a window bound as a bare epoch integer or an ISO-8601 stamp. None if unparseable."""
    text = (value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return int(parsed.timestamp())

def _utc_day_start(now: int) -> int:
    """Midnight UTC of the day `now` falls in — the default collection window's floor."""
    moment = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    return int(moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

def notified_senders(session_id: str, since: int, until: int) -> tuple[set[str], int, list[str]]:
    """Sender ids observed delivering a notify INTO `session_id` inside the window.

    Returns `(senders, rows_examined, problems)`. An inbound notify lands in the
    RECEIVING session as a user-role row whose header names the SENDER, in either the
    full-uuid shape or the 8-char short one, so both are read.

    The collector's OWN id is excluded. A lane's outbound send echoes back into its own
    session, so leaving it in would let a collector count itself among the targets that
    answered — measured on the 2026-10-01 collector's store, where its own id appeared
    among the observed senders.

    `rows_examined` is RETURNED rather than kept internal, because a reader that scanned
    nothing has reported nothing — it has not reported "nobody answered" — and the caller
    prints it. An unreadable profile DB is a problem, never an empty result: "no profile
    was readable" must not render as "no lane replied".
    """
    senders: set[str] = set()
    examined = 0
    problems: list[str] = []
    wanted = session_id.strip().lower()
    try:
        dbs = reg.profile_dbs()
    except Exception as exc:  # noqa: BLE001 — a manifest error is a problem, not a crash
        return senders, examined, [f"profile DBs unreadable: {type(exc).__name__}: {exc}"]
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error as exc:
            problems.append(f"{db}: {exc}")
            continue
        try:
            tables = {
                row[0]
                for row in conn.execute("select name from sqlite_master where type='table'")
            }
            if "messages" not in tables:
                continue
            for role, content in conn.execute(
                "select role, content from messages "
                "where session_id = ? and created_at between ? and ?",
                (session_id.strip(), since, until),
            ):
                examined += 1
                if role != "user" or not content:
                    continue
                for found in NOTIFY_FROM_FULL.findall(content):
                    if found.strip().lower() != wanted:
                        senders.add(found.strip().lower())
                for found in NOTIFY_FROM_SHORT.findall(content):
                    if not wanted.startswith(found.strip().lower()):
                        senders.add(found.strip().lower())
        except sqlite3.Error as exc:
            problems.append(f"{db}: {exc}")
        finally:
            conn.close()
    return senders, examined, problems

def classify_answers(
    targets: list[dict], observed: set[str], recovered: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Split the targets into by-notify / recovered / UNACCOUNTED. Pure over its inputs.

    No store and no clock, so a gate drives it with synthetic rows. `observed` is what
    the collector's own store actually saw; `recovered` is what an operator read out of
    the lanes' own sessions. A target in NEITHER set comes back as unaccounted rather
    than being folded into "no answer": that silence is exactly what let the 2026-10-01
    gap open, and the leg exists so that a gap DECLARED is a finding while a gap omitted
    is a loss.

    Matching is on the full id first and the 8-char short form second, because the store
    carries both shapes; `recovered` is matched by slug.
    """
    declared = {slug.strip() for slug in recovered if slug.strip()}
    by_notify: list[str] = []
    recovered_rows: list[str] = []
    unaccounted: list[str] = []
    for target in targets:
        slug = str(target["slug"])
        session_id = str(target["session_id"]).strip().lower()
        if session_id in observed or session_id[:8] in observed:
            by_notify.append(slug)
        elif slug in declared:
            recovered_rows.append(slug)
        else:
            unaccounted.append(slug)
    return by_notify, recovered_rows, unaccounted

def cmd_collect(targets: list[dict], problems: list[str], args: argparse.Namespace) -> int:
    """Declare the round's population: how many of N targets answered, and by which route."""
    collector = (args.collector or os.environ.get("OPENCRABS_SESSION_ID") or "").strip()
    if not collector:
        print(
            "registry-attest --collect: no collector session — pass --collector or set "
            "OPENCRABS_SESSION_ID (the identity is DERIVED, never declared)",
            file=sys.stderr,
        )
        return 1

    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    since = _instant(args.since) if args.since else _utc_day_start(now)
    until = _instant(args.until) if args.until else now
    if since is None or until is None or since > until:
        print(
            f"registry-attest --collect: bad window — since={args.since!r} until={args.until!r}",
            file=sys.stderr,
        )
        return 1

    declared = [slug.strip() for slug in (args.recovered or "").split(",") if slug.strip()]
    resolved_slugs = {str(target["slug"]) for target in targets}
    unknown = [slug for slug in declared if slug not in resolved_slugs]
    if unknown:
        print(
            f"registry-attest --collect: --recovered names no resolved target: "
            f"{', '.join(unknown)}",
            file=sys.stderr,
        )
        return 1

    observed, examined, read_problems = notified_senders(collector, since, until)
    problems = list(problems) + read_problems
    by_notify, recovered_rows, unaccounted = classify_answers(targets, observed, declared)

    window = (
        f"{datetime.datetime.fromtimestamp(since, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"..{datetime.datetime.fromtimestamp(until, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    print(f"registry-attest --collect — window {window}")
    print(f"  collector  {collector}")
    print(f"  examined   {examined} session row(s); {len(observed)} distinct sender(s) seen")
    print(f"  targets    {len(targets)} resolved, {len(problems)} unresolved")

    by_notify_set = set(by_notify)
    for target in targets:
        slug = str(target["slug"])
        if slug in by_notify_set:
            print(f"  {slug:<16} BY NOTIFY")
        elif slug in recovered_rows:
            print(f"  {slug:<16} RECOVERED  read from its own session (declared)")
        else:
            print(f"  {slug:<16} UNACCOUNTED")
    for problem in problems:
        print(f"  UNRESOLVED  {problem}")

    print(
        f"population: {len(by_notify) + len(recovered_rows)} of {len(targets)} accounted — "
        f"{len(by_notify)} by notify, {len(recovered_rows)} recovered by session read"
    )
    print(f"  by notify : {', '.join(by_notify) or '(none)'}")
    print(f"  recovered : {', '.join(recovered_rows) or '(none)'}")

    if not targets:
        print(
            "registry-attest --collect: 0 targets resolved — a population of zero is a "
            "broken instrument, not a clean round",
            file=sys.stderr,
        )
        return 1
    if unaccounted:
        print(
            f"registry-attest --collect: UNACCOUNTED {len(unaccounted)} of {len(targets)}: "
            f"{', '.join(unaccounted)} — neither delivered a notify into the collector nor "
            f"declared recovered. A silent fallback is what opened the 2026-10-01 gap; "
            f"declare it with --recovered or chase it.",
            file=sys.stderr,
        )
    return 1 if (problems or unaccounted) else 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="resolve and print targets, send nothing")
    group.add_argument("--dry-run", action="store_true", help="print the brief, send nothing")
    group.add_argument("--dispatch", action="store_true", help="send to every resolved HQ")
    group.add_argument(
        "--collect",
        action="store_true",
        help=(
            "declare the round's collection population: how many of N targets answered, "
            "split into answers that arrived BY NOTIFY (measured from the collector's own "
            "session store) and answers RECOVERED by reading a lane's own session "
            "(declared with --recovered). An unaccounted target fails the run."
        ),
    )
    parser.add_argument(
        "--since",
        metavar="ISO-OR-EPOCH",
        help=(
            "with --collect: the floor of the collection window (ISO-8601 or a bare epoch). "
            "Defaults to midnight UTC of today, and the EFFECTIVE window is always printed — "
            "a window that is not stated is not a scope."
        ),
    )
    parser.add_argument(
        "--until",
        metavar="ISO-OR-EPOCH",
        help="with --collect: the ceiling of the collection window. Defaults to now.",
    )
    parser.add_argument(
        "--collector",
        metavar="SESSION_ID",
        help=(
            "with --collect: the session that ran the round and received the answers. "
            "Defaults to OPENCRABS_SESSION_ID, because the identity is DERIVED and never "
            "declared — a remembered id is a dispatch into the void."
        ),
    )
    parser.add_argument(
        "--recovered",
        metavar="SLUG[,SLUG...]",
        help=(
            "with --collect: the targets whose answer was recovered by READING the lane's "
            "own session, because it did not deliver a notify. Every one is NAMED in the "
            "report; a slug that resolves to no target is refused rather than swallowed."
        ),
    )
    parser.add_argument(
        "--only",
        metavar="SLUG[,SLUG...]",
        help=(
            "restrict to these factory slugs (with --dispatch or --collect). A run can be cut "
            "short — six sequential CLI invocations outlive a foreground shell's patience — and "
            "the targets that already answered must not be woken a second time to reach the ones "
            "that did not. A slug that resolves to no HQ is refused rather than skipped, so a "
            "typo cannot silently send nothing."
        ),
    )
    args = parser.parse_args()

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    targets, problems = hq_targets(load_fragments())

    if args.only:
        wanted = [slug.strip() for slug in args.only.split(",") if slug.strip()]
        resolved = {target["slug"] for target in targets}
        unknown = [slug for slug in wanted if slug not in resolved]
        if unknown:
            print(
                f"registry-attest: --only names no resolved HQ: {', '.join(unknown)}",
                file=sys.stderr,
            )
            return 1
        targets = [target for target in targets if target["slug"] in wanted]

    if args.collect:
        return cmd_collect(targets, problems, args)

    print(f"registry-attest {stamp} — {len(targets)} HQ target(s) resolved", flush=True)
    for target in targets:
        print(
            f"  {target['slug']:<16} thread {str(target['thread_id']):<6} "
            f"{target['status']:<10} {target['session_id']}  ({target['topic']})",
            flush=True,
        )
    for problem in problems:
        print(f"  UNRESOLVED  {problem}", flush=True)

    if args.check:
        return 1 if problems else 0

    failures = 0
    for target in targets:
        sent, detail = dispatch(target, stamp, dry_run=args.dry_run)
        if not sent:
            failures += 1
        print(f"  {'sent' if sent else 'FAILED'}  {target['slug']:<16} {detail}", flush=True)

    if args.dry_run:
        print("")
        print(BRIEF.format(slug=targets[0]["slug"] if targets else "<slug>", stamp=stamp))
        return 1 if problems else 0

    print(f"registry-attest: {len(targets) - failures} sent, {failures} failed, "
          f"{len(problems)} unresolved")
    return 1 if (failures or problems) else 0


if __name__ == "__main__":
    sys.exit(main())
