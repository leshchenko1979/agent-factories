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

Run:  python3 tools/registry_attest.py --check          # resolve and print targets
      python3 tools/registry_attest.py --dry-run        # print the brief, send nothing
      python3 tools/registry_attest.py --dispatch       # send to every resolved HQ
Exit: 0 every target dispatched (or resolved, for --check); 1 if any HQ failed to resolve.
"""

from __future__ import annotations

import argparse
import datetime
import json
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

BRIEF = """Registry re-attestation — {slug} ({stamp})

Your factory is one entry in the fleet registry (docs/factory-registry.md). The
GENERATED half of that entry is read live from this box every render, so it cannot
rot. The DECLARED half is yours: it is what you wrote, and only you can say whether
it still describes you. Three questions, and all three need an answer.

QUESTION 1 — YOUR FRAGMENT. Confirm it unchanged, or amend it.
  registry/factories/{slug}.json
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

QUESTION 3 — YOUR JOB PREFIX AND YOUR CRON ROWS. Confirm the prefix, report what you
  cannot place. Your factory's jobs are named `<your prefix>-<what-it-does>`, and the
  prefix is the one your `registry/fleet.json` record declares in `job_prefixes` — the
  manifest refuses an empty list and refuses two factories whose prefixes overlap, because
  the prefixes are the only reason a job on a shared box can be attributed to its owner at
  all. Two answers, both short:
    (a) PREFIX — your declared prefix, and whether it still matches how you name your jobs.
    (b) ORPHANS — any cron row you have seen that you cannot attribute to your own factory.
        The cron table is shared and has no single owner, so the rule is: never disable,
        delete, edit or repace a job attributed to another factory, and report a job you
        cannot attribute instead of touching it. Name the job, the profile home you read it
        from, and what you saw. "None seen" is a complete answer.

Reply on this session. The registry is a collected document: this lane writes your
declared fields back verbatim, and re-renders. You author the field; you do not need
to edit the file, though you may.

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="resolve and print targets, send nothing")
    group.add_argument("--dry-run", action="store_true", help="print the brief, send nothing")
    group.add_argument("--dispatch", action="store_true", help="send to every resolved HQ")
    parser.add_argument(
        "--only",
        metavar="SLUG[,SLUG...]",
        help=(
            "restrict to these factory slugs (with --dispatch). A run can be cut short — "
            "six sequential CLI invocations outlive a foreground shell's patience — and the "
            "targets that already answered must not be woken a second time to reach the ones "
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
