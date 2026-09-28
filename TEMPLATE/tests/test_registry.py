#!/usr/bin/env python3
"""Gate: the factory registry's declared half is valid, bound and covered, and its
generated half is byte-reproducible.

Seven checks, each printed with the count it measured:

  1. every fragment validates against the schema — the live store AND the fixtures,
     because a fixture that stops validating has stopped describing the schema
  2. every declared `thread_id` resolves to a live `session_bindings` row ON THE
     DECLARED PROFILE
  3. every declared lane is BOUND — declared-but-unbound is a failure, not a warning
  4. GATE A — the committed `docs/factory-registry.md` and `registry/index.json` are
     identical, byte for byte and with NO normalization, to a replay of the snapshot
     `registry/state.json` recorded beside them
  5. coverage — every factory group known to the fleet has a fragment, and every
     fragment names a known slug
  6. `resolved_at` is gated on its own terms — present, parseable, not in the future,
     and the two artifacts agree on it
  7. every announcement is well-formed and unambiguous

Why the registry needs a gate at all. The document is generated from live state, so it
is true by construction — and for exactly that reason it rots the moment a topic
rebinds, a session is recreated or a lane is renamed, while still READING as true. A
reader cannot tell a stale render from a current binding without the instant it was
taken, which is what `resolved_at` carries and what check 6 gates.

HOW check 4 stays a CORRECTNESS check — the design decision this gate owes, stated here
rather than assumed, and MEASURED rather than reasoned (#103, ruling n=613). The renderer
reads LIVE state — bindings, cron rows, skill versions, predicate results — so comparing a
committed artifact against a fresh render compares the PAST against the INSTANT. Measured
2026-09-19/20 in a pristine detached worktree at the shipped revision with zero dirty
files: `registry/index.json` line 432 carried a committed `"bound_at":
"2026-09-19T17:54:32Z"` against a fresh `"2026-09-19T23:05:16Z"`. So a lane rebinding a
topic REDs the gate at a clean HEAD, with no act by the lane running it, and no lane can
make it green except by re-rendering and committing someone else's state change. One
verdict was riding two properties, and they are now SPLIT:

  GATE A (check 4, in the verdict) — REPRODUCIBILITY, offline and deterministic. The
  committed artifacts are compared against a replay of `registry/state.json`: the snapshot
  of the six live inputs they were rendered from, recorded and committed in the SAME call
  as the artifacts, so a successful render cannot leave a stale snapshot beside fresh bytes.
  Both sides carry the snapshot's own values and its own stamp, so nothing volatile is
  compared, the comparison needs NO normalization, and the verdict is the same at any
  instant on any box. The gate reads the COMMITTED blobs (`git show HEAD:<path>`), never the
  working tree — a gate that read the working tree would pass on a tree re-rendered without
  committing, which is precisely the drift it exists to catch — and every failure message
  names the revision it measured.

  FRESHNESS (a monitor, never in the verdict) — the committed artifact against a render of
  LIVE state, reported as a line. It answers "has the box moved since the render?", which is
  a question about the instant and therefore not gateable: a gate that REDs on a moved
  binding cannot be made green by the lane that finds it. It is printed OUTSIDE `CHECKS`, so
  it can never reach the pass/fail verdict.

The monitor renders its live side AT THE COMMITTED INSTANT — a decision it owes, stated
rather than assumed, and MEASURED rather than reasoned. The renderer computes its freshness
badges from the instant it is handed (`_freshness_badge` compares `age_hours(attested_at,
now)` against the 72 h window), so rendering the live side at a SENTINEL inverts that test
instead of neutralising it: every age becomes NEGATIVE, no fragment can render `STALE`, and
a genuinely stale attestation would come out reading `attested` — the two sides diverge the
moment any fragment is stale, in the direction of HIDING the failure. Rendering at the
committed artifact's OWN instant keeps both sides on one clock, so the monitor reports
genuine state movement and not clock-induced badge churn, and the literal stamp is then
substituted for the sentinel on both sides. The probes below prove that by construction
rather than asserting it — the first version of this paragraph predicted the sentinel would
render everything STALE, and the probe measured the opposite.

`normalize_stamp()` and `drift_problems()` survive the split as the MONITOR's instrument and
the probes': they compare two texts rendered at two instants, which is the shape the probes
drive. GATE A does not use them — it compares two texts rendered from ONE snapshot and needs
no normalization at all, which is the whole point of the split.

Two scope statements this gate carries, because its report is wrong without them:

  (i)  Checks 2, 3 and 5 are scoped to the DECLARED fleet, not to this box. They read
       `registry.KNOWN_FACTORY_SLUGS` and `FACTORY_CHATS`, both of which are derived from
       `registry/fleet.json` — the manifest a factory's HQ writes. So a bootstrapped
       factory that has declared its own factories passes, and one that has declared none
       FAILS naming the undeclared manifest rather than reporting empty coverage. This
       parameterisation is what moved the file out of `gate_registry.OPTIONAL_GATES` and
       into `REQUIRED_GATES`; the gate is now required in the template too.
  (ii) GATE A reads the committed snapshot, so it catches a hand-edited artifact and a
       mutated snapshot, and NOT a box that has moved since the render — that is the
       monitor's report, and the two are deliberately separate. A snapshot that was never
       committed FAILS the gate BY NAME, because an artifact whose inputs cannot be
       replayed is unverifiable rather than stale.

The announcement probes take their slugs from the manifest rather than naming a pair:
`validate_fragment` resolves `factory` against `KNOWN_FACTORY_SLUGS`, so the probe needs
two slugs that are genuinely declared — and which two those are is the box's fact, not
this gate's. `probe_slugs()` refuses a manifest with fewer than two factories instead of
synthesizing one, because a synthesized slug would be rejected by the validator and would
prove the merge while skipping the declaration.

Run:  python3 tests/test_registry.py
Exit: 0 clean, 1 on any failed check.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))

import registry as reg  # noqa: E402
import registry_render as rr  # noqa: E402

PREDICATE = (
    "every fragment in the live store and the fixtures validates; every declared lane "
    "resolves to a live binding on its declared profile; every factory group known to "
    "the fleet has a fragment; the committed artifacts are a byte-exact replay of the "
    "snapshot committed beside them; `resolved_at` is present, parseable, not in the "
    "future and agreed by both artifacts; every announcement is well-formed and no two "
    "entries sharing an `id` carry differing text."
)

failures: list[str] = []
counts: list[str] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)

def load_live() -> list[tuple[Path, dict]]:
    """The live fragments, parsed. A file that does not parse is returned as (path, {})."""
    out: list[tuple[Path, dict]] = []
    for path in reg.live_fragment_paths([]):
        data, _error = reg.load_fragment(path)
        out.append((path, data if isinstance(data, dict) else {}))
    return out

# --- 1. schema --------------------------------------------------------------

def check_fragments_validate() -> list[str]:
    paths = reg.fragment_paths([])
    problems: list[str] = []
    for path in paths:
        data, error = reg.load_fragment(path)
        if error:
            problems.append(error)
            continue
        problems.extend(reg.validate_fragment(data, str(path)))
    counts.append(f"{len(paths)} fragment(s) validated (live store + fixtures)")
    return problems

# --- 2 and 3. the declared lanes resolve live -------------------------------

def check_lanes_bound() -> list[str]:
    """Checks 2 and 3, which are one read of the same rows.

    `resolve_lane` narrows by the factory's OWN chat id, because a thread id is
    unique only WITHIN a chat — thread 4 exists in both the Miidas and the Infra
    chat. What survives that narrowing is scoped to ONE profile here (the rows are
    bucketed by `_profile` before the call), so a lane with several live sessions
    on its topic comes back `superseded`: a supersession chain, resolved by
    recency, and NOT a failure. `ambiguous` is the cross-profile case and is not
    reachable from this check's inputs, but it is counted the same way rather than
    silently accepted or silently failed. Both are stated by count, which is what
    this gate owes a reader who cannot see the binding table.
    """
    bindings, errors = reg.all_bindings()
    problems: list[str] = list(errors)
    by_profile: dict[str, list[dict]] = {}
    for row in bindings:
        by_profile.setdefault(str(row.get("_profile")), []).append(row)

    declared = 0
    superseded = 0
    ambiguous = 0
    for path, fragment in load_live():
        profile = str(fragment.get("profile"))
        scoped = by_profile.get(profile, [])
        if not scoped:
            problems.append(
                f"{path.name}: profile `{profile}` has no readable binding rows — a lane "
                f"cannot be resolved against a profile this gate cannot read"
            )
        chat_id = reg.FACTORY_CHATS.get(str(fragment.get("factory")))
        for lane in fragment.get("lanes") or []:
            if not isinstance(lane, dict):
                problems.append(f"{path.name}: a lane entry is not an object")
                continue
            declared += 1
            resolved = reg.resolve_lane(lane, scoped, {}, chat_id=chat_id)
            status = str(resolved.get("status"))
            where = f"{fragment.get('factory')}/{lane.get('topic')} (thread {lane.get('thread_id')})"
            if status == "resolved":
                continue
            if status == "superseded":
                superseded += 1
                continue
            if status == "ambiguous":
                ambiguous += 1
                continue
            problems.append(
                f"declared lane {where} is {status.upper()} — it "
                f"resolves to no live `session_bindings` row on profile `{profile}`"
            )
    counts.append(
        f"{declared} declared lane(s) checked against {len(bindings)} binding row(s); "
        f"{superseded} supersession chain(s) (one profile, several generations — newest "
        f"renders), {ambiguous} ambiguous (cross-profile, unresolvable)"
    )
    return problems

# --- 5. coverage ------------------------------------------------------------

def check_coverage() -> list[str]:
    problems: list[str] = []
    present = {str(fragment.get("factory")): path for path, fragment in load_live()}
    for slug in sorted(reg.KNOWN_FACTORY_SLUGS - set(present)):
        problems.append(
            f"factory `{slug}` is known to the fleet but has NO fragment in "
            f"registry/factories/ — an absent declaration is a question, not an answer"
        )
    for slug in sorted(set(present) - reg.KNOWN_FACTORY_SLUGS):
        problems.append(
            f"fragment {present[slug].name} declares factory `{slug}`, which is not in "
            f"KNOWN_FACTORY_SLUGS — `affects` entries can never resolve against it"
        )
    counts.append(
        f"coverage {len(set(present) & reg.KNOWN_FACTORY_SLUGS)}/"
        f"{len(reg.KNOWN_FACTORY_SLUGS)} factory group(s)"
    )
    return problems

# --- 4. GATE A (reproducibility) and the freshness monitor -------------------
#
# GATE A is the verdict: the committed bytes against a replay of the committed
# snapshot, byte for byte and with NO normalization. The monitor is a REPORT and never a
# verdict: the committed bytes against a LIVE render, which answers a question about the
# instant and is therefore not gateable (#103). `normalize_stamp` and `drift_problems`
# below are the monitor's and the probes' instrument, not GATE A's.

def normalize_stamp(text: str, stamp: object) -> str:
    """Replace the render instant with the sentinel, so the clock is not compared.

    The MONITOR's instrument and the probes': two texts rendered at two instants. GATE A
    does not call this — both of its sides already carry the snapshot's own stamp.
    """
    if not stamp:
        return text
    return text.replace(str(stamp), rr.RESOLVED_SENTINEL)

def first_difference(committed: str, fresh: str) -> str:
    """Name the first place two rendered texts diverge, for the failure message."""
    for number, (left, right) in enumerate(
        zip(committed.splitlines(), fresh.splitlines()), start=1
    ):
        if left != right:
            return f"line {number}: committed={left[:100]!r} fresh={right[:100]!r}"
    committed_lines = len(committed.splitlines())
    fresh_lines = len(fresh.splitlines())
    if committed_lines != fresh_lines:
        return f"line count differs: committed={committed_lines} fresh={fresh_lines}"
    return "byte difference inside the final line (a trailing newline)"

def drift_problems(
    committed_md: str,
    committed_index: str,
    fresh_md: str,
    fresh_index: str,
    committed_stamp: object,
    fresh_stamp: object = None,
) -> list[str]:
    """The comparison itself, pure — so the acceptance probes can drive it directly.

    Each side is normalized with ITS OWN stamp: the live call passes one stamp for
    both (check 6 enforces that the two artifacts agree), while the probes pass the
    advanced stamp on the committed side to prove that moving the clock alone is
    not read as drift.
    """
    problems: list[str] = []
    fresh_stamp = committed_stamp if fresh_stamp is None else fresh_stamp
    for label, committed, fresh in (
        ("docs/factory-registry.md", committed_md, fresh_md),
        ("registry/index.json", committed_index, fresh_index),
    ):
        left = normalize_stamp(committed, committed_stamp)
        right = normalize_stamp(fresh, fresh_stamp)
        if left != right:
            problems.append(
                f"{label}: committed bytes differ from a fresh render — "
                f"{first_difference(left, right)}"
            )
    return problems

def read_working_tree() -> tuple[str, str, object]:
    """The two artifacts AS THEY SIT IN THE WORKING TREE, and the instant the index
    says they were read.

    This is the PROBES' base and the monitor's helper, never GATE A's: a probe must
    drive the comparison even on a tree whose render is not yet committed. GATE A reads
    the committed blobs (`committed_blob`), because a gate that read the working tree
    would pass on a tree re-rendered without committing — precisely the drift it exists
    to catch (#103).
    """
    committed_md = rr.MD_PATH.read_text(encoding="utf-8")
    committed_index = rr.INDEX_PATH.read_text(encoding="utf-8")
    stamp = json.loads(committed_index).get("resolved_at")
    return committed_md, committed_index, stamp

def relpath(path: Path) -> str:
    """A path as `git show` needs it — relative to the repo root, never absolute."""
    return str(path.relative_to(rr.REPO_ROOT))

def committed_revision() -> tuple[str, str | None]:
    """HEAD's full sha, or an empty string and the reason it could not be read."""
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True)
    if result.returncode != 0:
        return "", (
            "HEAD cannot be resolved — "
            + result.stderr.decode("utf-8", "replace").strip()
        )
    return result.stdout.decode("utf-8").strip(), None

def committed_blob(path: Path) -> tuple[str | None, str | None]:
    """One file's bytes AT HEAD, decoded, or None and the reason it is not there.

    `git show` is captured as BYTES and decoded here rather than with `text=True`:
    universal-newline translation would rewrite a CRLF blob to LF and hide a real byte
    difference from a comparison that claims byte-exactness.
    """
    where = relpath(path)
    result = subprocess.run(
        ["git", "show", f"HEAD:{where}"], cwd=REPO, capture_output=True
    )
    if result.returncode != 0:
        return None, (
            f"{where} is not committed at HEAD — "
            + result.stderr.decode("utf-8", "replace").strip()
        )
    return result.stdout.decode("utf-8"), None

def _committed_replay() -> tuple[str, dict[str, str], dict | None, list[str]]:
    """The three committed blobs, and the snapshot replayed from them.

    Returns `(revision, blobs, snapshot, problems)`. A non-empty `problems` means the
    replay could not be FORMED — an unreadable blob, an unparseable snapshot, an
    unconsumable snapshot — and the caller reports those as the finding. Split out from
    `check_render_reproduces` so the acceptance probes can reach the comparison with a
    snapshot they MUTATED, which is the only way to prove the gate is not vacuous.
    """
    revision, error = committed_revision()
    if error:
        return "", {}, None, [error]

    blobs: dict[str, str] = {}
    for path in (rr.MD_PATH, rr.INDEX_PATH, rr.STATE_PATH):
        text, error = committed_blob(path)
        if error:
            return revision, {}, None, [f"at {revision}: {error}"]
        blobs[relpath(path)] = text

    state_rel = relpath(rr.STATE_PATH)
    try:
        snapshot = json.loads(blobs[state_rel])
    except json.JSONDecodeError as exc:
        return revision, blobs, None, [
            f"at {revision}: {state_rel} does not parse as JSON — {exc}"
        ]
    if not isinstance(snapshot, dict):
        return revision, blobs, None, [f"at {revision}: {state_rel} is not an object"]
    return revision, blobs, snapshot, []

def gate_a_problems(
    blobs: dict[str, str], snapshot: dict, revision: str
) -> list[str]:
    """GATE A's comparison, given committed blobs and a snapshot — pure, so it is drivable.

    Both sides are rendered FROM THE SAME SNAPSHOT, so both carry that snapshot's own
    stamp and the comparison needs NO normalization. That is what lets one function
    serve both the live gate and the probes: mutating a state-bearing key and mutating
    `resolved_at` are the same question asked of the same code, and neither is
    normalized away.
    """
    state_rel = relpath(rr.STATE_PATH)
    try:
        replay_md, replay_index, _ctx = rr.render_from_snapshot(snapshot)
    except Exception as exc:  # noqa: BLE001 — an unconsumable snapshot IS the finding
        return [
            f"at {revision}: {state_rel} cannot be replayed — "
            f"{type(exc).__name__}: {exc}"
        ]

    problems: list[str] = []
    for path, replay in ((rr.MD_PATH, replay_md), (rr.INDEX_PATH, replay_index)):
        committed = blobs.get(relpath(path))
        if committed != replay:
            problems.append(
                f"{relpath(path)}: the bytes committed at {revision} are not a replay "
                f"of {state_rel} — {first_difference(committed or '', replay)}"
            )
    return problems

def check_render_reproduces() -> list[str]:
    """GATE A — the committed artifacts are a byte-exact replay of their snapshot.

    Both sides are rendered FROM THE SNAPSHOT committed beside them, so no volatile
    field is compared, the comparison needs NO normalization, and the verdict is the
    same at any instant on any box. The blobs come from HEAD and never the working
    tree. Every failure names the revision it measured.
    """
    revision, blobs, snapshot, problems = _committed_replay()
    if problems:
        return problems
    problems = gate_a_problems(blobs, snapshot, revision)
    state_rel = relpath(rr.STATE_PATH)
    counts.append(
        f"GATE A: {relpath(rr.MD_PATH)} and {relpath(rr.INDEX_PATH)} at {revision[:12]} "
        f"replayed from {state_rel} ({len(snapshot.get('bindings') or [])} binding(s), "
        f"{len(snapshot.get('jobs') or [])} job(s), no normalization)"
    )
    return problems

def report_freshness() -> str:
    """Has the box MOVED since the last committed render? — reported, never gated.

    This is the question GATE A cannot answer and must not try to: it is a question
    about the INSTANT, so a RED here would be un-greenable by the lane that finds it
    (#103). The line is printed OUTSIDE `CHECKS` and never reaches the verdict.

    The live side is rendered AT THE COMMITTED INSTANT so both sides sit on one clock:
    the renderer's freshness badges are a function of the instant it is handed, so a
    live render at `utc_now()` would report clock-induced badge churn as though the box
    had moved. On one clock, a difference is genuine state movement.
    """
    revision, error = committed_revision()
    if error:
        return f"NOT TAKEN — {error}"

    committed_md, error = committed_blob(rr.MD_PATH)
    if error:
        return f"NOT TAKEN — {error}"
    committed_index, error = committed_blob(rr.INDEX_PATH)
    if error:
        return f"NOT TAKEN — {error}"

    try:
        stamp = json.loads(committed_index).get("resolved_at")
    except json.JSONDecodeError as exc:
        return f"NOT TAKEN — {relpath(rr.INDEX_PATH)} does not parse as JSON — {exc}"

    try:
        live_md, live_index, _ctx = rr.render_texts(resolved_at=str(stamp))
    except Exception as exc:  # noqa: BLE001 — a failed live read is a report, not a verdict
        return f"NOT TAKEN — a live render raised {type(exc).__name__}: {exc}"

    problems = drift_problems(committed_md, committed_index, live_md, live_index, stamp)
    if problems:
        return (
            f"the box has MOVED since the render committed at {revision[:12]} "
            f"({stamp}) — {len(problems)} artifact(s) differ; re-render and commit when "
            f"the movement is wanted. {problems[0]}"
        )
    return (
        f"the box has not moved since the render committed at {revision[:12]} ({stamp})"
    )

def _monitor_reading_the_working_tree() -> str:
    """`report_freshness` with its COMMITTED side read from the WORKING TREE, not HEAD.

    This is the mechanism revert the bite probe below drives. The real monitor reads HEAD
    through `committed_blob`; this one reads the file on disk, which is the shape the probe
    above was written against when it asserted MOVED off its own working-tree edit. It
    exists so that read path can be shown LOAD-BEARING rather than assumed: a substituted
    monitor that reads the tree must make `probe_a_working_tree_edit_does_not_move_the_
    verdict` FAIL, and an exit 0 over an unchanged file can never show that (#113, the P29
    non-vacuity rule: the property is the PROBE's, and the probe is what must be shown to
    bite).
    """
    revision, error = committed_revision()
    if error:
        return f"NOT TAKEN — {error}"

    try:
        committed_md = rr.MD_PATH.read_text(encoding="utf-8")
        committed_index = rr.INDEX_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        return f"NOT TAKEN — a working-tree read raised {type(exc).__name__}: {exc}"

    try:
        stamp = json.loads(committed_index).get("resolved_at")
    except json.JSONDecodeError as exc:
        return f"NOT TAKEN — {relpath(rr.INDEX_PATH)} does not parse as JSON — {exc}"

    try:
        live_md, live_index, _ctx = rr.render_texts(resolved_at=str(stamp))
    except Exception as exc:  # noqa: BLE001 — a failed live read is a report, not a verdict
        return f"NOT TAKEN — a live render raised {type(exc).__name__}: {exc}"

    problems = drift_problems(committed_md, committed_index, live_md, live_index, stamp)
    if problems:
        return (
            f"the box has MOVED since the render committed at {revision[:12]} "
            f"({stamp}) — {len(problems)} artifact(s) differ; re-render and commit when "
            f"the movement is wanted. {problems[0]}"
        )
    return (
        f"the box has not moved since the render committed at {revision[:12]} ({stamp})"
    )

# --- 6. resolved_at, gated on its own terms ---------------------------------

MD_STAMP = re.compile(r"\*\*resolved at\*\* `([^`]+)`")

def check_resolved_at() -> list[str]:
    problems: list[str] = []
    now = datetime.datetime.now(datetime.timezone.utc)
    stamps: dict[str, str] = {}
    try:
        match = MD_STAMP.search(rr.MD_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"{rr.MD_PATH}: cannot read — {exc}"]
    if match is None:
        problems.append(
            "docs/factory-registry.md: no `**resolved at** <stamp>` line — the generated "
            "half carries no instant, so a reader cannot re-check any claim in it"
        )
    else:
        stamps["docs/factory-registry.md"] = match.group(1)
    try:
        index = json.loads(rr.INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"registry/index.json: cannot read or parse — {exc}")
        index = {}
    if "resolved_at" not in index:
        problems.append("registry/index.json: no `resolved_at` key")
    else:
        stamps["registry/index.json"] = str(index.get("resolved_at"))
    for label, stamp in sorted(stamps.items()):
        parsed = rr.parse_instant(stamp)
        if parsed is None:
            problems.append(f"{label}: resolved_at `{stamp}` does not parse as an instant")
        elif parsed > now:
            problems.append(
                f"{label}: resolved_at `{stamp}` is in the FUTURE — a render cannot be "
                f"dated ahead of the read that produced it"
            )
    distinct = sorted(set(stamps.values()))
    if len(distinct) > 1:
        problems.append(
            f"the two artifacts disagree on resolved_at ({distinct}) — they are two "
            f"renderings of ONE read, so one of them is not from that read"
        )
    counts.append(
        f"resolved_at {distinct[0]}" if len(distinct) == 1 else f"resolved_at {distinct}"
    )
    return problems

# --- 7. announcements, well-formed and unambiguous --------------------------

def announcement_problems(merged: list[dict], where: str) -> list[str]:
    """Re-validate the MERGED view through the schema validator.

    Check 1 already validates every declaration site. This is a second receipt on the
    thing peers actually ACT on — the deduplicated list — and it reuses the one
    implementation instead of restating its rules here, so the two cannot drift.
    """
    problems: list[str] = []
    for entry in merged:
        projected = {k: v for k, v in entry.items() if k in reg.ANNOUNCEMENT_KEYS}
        errors: list[str] = []
        reg.validate_announcements(
            [projected], f"merged announcement `{entry.get('id')}`", reg.SCOPES, errors
        )
        problems.extend(errors)
    return problems

def check_announcements() -> list[str]:
    fragments = [fragment for _path, fragment in load_live()]
    merged, conflicts = rr.collect_announcements(fragments)
    problems = list(conflicts)
    problems.extend(announcement_problems(merged, "merged"))
    counts.append(
        f"{len(merged)} announcement(s) merged from {len(fragments)} fragment(s), "
        f"{len(conflicts)} conflicting-text case(s)"
    )
    return problems

# --- acceptance probes ------------------------------------------------------
#
# Each probe drives the SAME function the live check uses, with inputs whose answer
# is known, so a green live check cannot come from a comparison that never compares.

def probe_a_supersession_chain_is_not_ambiguity() -> None:
    """#100: the multi-match branch splits on PROFILE, and BOTH halves are driven here.

    The defect this pins: the chat narrowing runs BEFORE the length check, so every
    survivor already shares one chat and the condition the old comment named — "two
    chats or two profiles" — could not hold where it was tested. Intra-profile matches
    are a supersession chain (a topic re-opened several times), so the newest binding is
    the lane and the status says so; only a match across two PROFILES is genuinely
    unresolved. The cross-profile leg is asserted as well, because the fix was built
    around that detector and a fix that deleted it would pass the first check alone.
    """
    def binding(profile: str, session: str, updated: int) -> dict:
        return {
            "_profile": profile,
            "chat_id": "-100123",
            "thread_id": 7,
            "session_id": session,
            "updated_at": updated,
        }

    lane = {"topic": "HQ", "role": "hq", "thread_id": 7}
    chain = [binding("ops", "old", 100), binding("ops", "new", 200)]
    row = reg.resolve_lane(lane, chain, {}, chat_id="-100123")
    check(
        "two bindings in ONE profile are a supersession chain, and the newest wins",
        row["status"] == "superseded" and row["session_id"] == "new",
        f"status={row['status']} session={row['session_id']}",
    )
    check(
        "...and the chain is REPORTED: every candidate survives on the row",
        set(row.get("candidates") or []) == {"ops:-100123/7=old", "ops:-100123/7=new"},
        str(row.get("candidates")),
    )
    cross = [binding("ops", "old", 100), binding("family", "other", 200)]
    row = reg.resolve_lane(lane, cross, {}, chat_id="-100123")
    check(
        "a match across two PROFILES is still AMBIGUOUS — the detector survives the fix",
        row["status"] == "ambiguous",
        f"status={row['status']}",
    )
    check(
        "...and the exit predicate fails on it while a chain does not",
        reg.unresolved_total({"ambiguous": 1}) == 1
        and reg.unresolved_total({"superseded": 3}) == 0,
        f"ambiguous={reg.unresolved_total({'ambiguous': 1})} "
        f"superseded={reg.unresolved_total({'superseded': 3})}",
    )
    lone = [binding("ops", "only", 100)]
    row = reg.resolve_lane(lane, lone, {}, chat_id="-100123")
    check(
        "a lone binding is still `resolved`, so the chain branch is not the default",
        row["status"] == "resolved" and "candidates" not in row,
        f"status={row['status']} candidates={row.get('candidates')}",
    )

def probe_a_hand_edit_is_named() -> None:
    committed_md, committed_index, stamp = read_working_tree()
    edited = committed_md.replace(
        "Generated file.", "Generated file. HAND EDIT.", 1
    )
    problems = drift_problems(edited, committed_index, committed_md, committed_index, stamp)
    check(
        "a hand-edit to docs/factory-registry.md is NAMED as drift",
        any("factory-registry.md" in p and "HAND EDIT" in p for p in problems),
        problems[0][:110] if problems else "no problem reported",
    )
    clean = drift_problems(committed_md, committed_index, committed_md, committed_index, stamp)
    check("...while the unedited pair raises nothing", clean == [], "; ".join(clean)[:90])

def probe_only_the_stamp_advanced_passes() -> None:
    """A re-render in which ONLY `resolved_at` advanced must still pass.

    The artifact's bytes are taken from the working tree and the stamp is moved
    forward — which is exactly what a re-render over unchanged live state produces —
    then compared against the same bytes at the committed instant. The normalization is
    what makes the two equal, so this probe fails if it is ever removed. This is the
    MONITOR's instrument: GATE A renders both sides from one snapshot and normalizes
    nothing, so it is not exercised here.
    """
    committed_md, committed_index, stamp = read_working_tree()
    advanced = rr.parse_instant(stamp) + datetime.timedelta(hours=1)
    later = advanced.strftime("%Y-%m-%dT%H:%M:%SZ")
    moved_md = committed_md.replace(str(stamp), later)
    moved_index = committed_index.replace(str(stamp), later)
    check(
        "the stamp actually moved in the probe input",
        later in moved_md and later in moved_index and later != str(stamp),
        f"{stamp} -> {later}",
    )
    problems = drift_problems(
        moved_md, moved_index, committed_md, committed_index, later, stamp
    )
    check(
        "a re-render in which ONLY resolved_at advanced still PASSES",
        problems == [],
        "; ".join(problems)[:110],
    )
    unnormalized = drift_problems(
        moved_md, moved_index, committed_md, committed_index, None, None
    )
    check(
        "...and the same pair WITHOUT normalization is reported, so the probe is not vacuous",
        len(unnormalized) == 2,
        f"{len(unnormalized)} problem(s) with the stamp left in place",
    )

def probe_the_sentinel_would_rewrite_badges() -> None:
    """Why the fresh side renders at the COMMITTED instant and not at the sentinel.

    A pure-function probe over a STALE attestation, which is the case that diverges: at the
    sentinel every age is negative, so the staleness branch cannot fire and a genuinely
    stale fragment renders as freshly attested. The first draft of this probe used a fresh
    attestation — the one case where both instants agree — and measured that the claim in
    the docstring was the wrong way round.
    """
    stale = "2026-09-01T00:00:00Z"
    at_commit = rr._freshness_badge("attested", stale, rr.parse_instant("2026-09-19T14:00:00Z"))
    at_sentinel = rr._freshness_badge("attested", stale, rr.parse_instant(rr.RESOLVED_SENTINEL))
    check(
        "a sentinel render would HIDE a stale attestation (so the fresh side renders at the committed instant)",
        at_sentinel != at_commit and "STALE" in at_commit and "STALE" not in at_sentinel,
        f"at commit: {at_commit!r} · at sentinel: {at_sentinel!r}",
    )
    fresh = "2026-09-19T12:00:00Z"
    check(
        "...while a fresh attestation reads the same at both, which is why the claim is stated per case",
        rr._freshness_badge("attested", fresh, rr.parse_instant("2026-09-19T14:00:00Z"))
        == rr._freshness_badge("attested", fresh, rr.parse_instant(rr.RESOLVED_SENTINEL)),
        f"at commit: {rr._freshness_badge('attested', fresh, rr.parse_instant('2026-09-19T14:00:00Z'))!r}",
    )

def render_carried_binding_index(snapshot: dict) -> tuple[int | None, str]:
    """The index of the LAST snapshot binding the replay CARRIES, and why it qualifies.

    The predicate is the RENDERER'S OWN SELECTION, read from the renderer rather than
    restated here. `registry_render.build_context` resolves every DECLARED lane against
    the snapshot's bindings and copies the winning row's `session_id`, `chat_id`,
    `bound_at`, `last_origin`, `turn_open` and `session_title` into the context both
    artifacts are rendered from. A binding that no declared lane resolves to contributes
    nothing to either artifact, so mutating it is render-NEUTRAL: a probe driven from such
    a row measures the mutation's ABSENCE, never the detector's sensitivity.

    That is precisely the defect this helper replaces (#151). The probe below used to take
    the LAST binding by POSITION (`bindings[:-1]`) on a list REGENERATED from live state,
    so its verdict tracked which chat happened to sort last rather than whether the
    detector works. Measured at e918d9b: `bindings[-1]` is the Avito member chat (thread
    7603), which the render does not carry — 61 of 130 bindings resolve a declared lane —
    so dropping it is render-neutral and the assertion of 2 could not be met. The probe
    then failed for EVERY lane at every revision whose last binding was not render-carried,
    which is what made a position-dependent probe a suite-wide red.

    Returning `None` is a CLAIM ABOUT THE SNAPSHOT, and the caller FAILS on it rather than
    skipping: a snapshot carrying no render-carried binding would make the probe vacuous,
    which is the failure mode this helper exists to prevent. Read from the renderer, so a
    change to the renderer's selection rule can never drift from this predicate — the two
    are not two copies of a rule but one rule and its caller.
    """
    bindings = snapshot.get("bindings") or []
    consumable = [b for b in bindings if isinstance(b, dict)]
    if not consumable:
        return None, "the snapshot carries no binding rows at all"
    try:
        ctx, problems = rr.build_context(
            [], consumable, str(snapshot.get("resolved_at") or ""), recorded=snapshot
        )
    except Exception as exc:  # noqa: BLE001 — an unconsumable snapshot IS the finding
        return None, (
            f"the snapshot cannot be assembled into a render context — "
            f"{type(exc).__name__}: {exc}"
        )
    if problems:
        return None, f"the render context reports {problems[0][:80]}"

    carried = set()
    for factory in ctx.get("factories") or []:
        for lane in factory.get("lanes") or []:
            if lane.get("session_id"):
                carried.add(
                    (
                        str(lane.get("chat_id")),
                        lane.get("thread_id"),
                        str(lane["session_id"]),
                    )
                )
    if not carried:
        return None, "no declared lane resolved to a binding, so no binding reaches the render"

    for index in range(len(bindings) - 1, -1, -1):
        row = bindings[index]
        if not isinstance(row, dict):
            continue
        key = (str(row.get("chat_id")), row.get("thread_id"), str(row.get("session_id")))
        if key in carried:
            return index, (
                f"binding[{index}] (chat {row.get('chat_id')} thread {row.get('thread_id')}) "
                f"resolves a declared lane, so its values reach both artifacts"
            )
    return None, (
        f"{len(carried)} declared lane(s) resolved, but no snapshot binding carries those "
        f"identities — the snapshot and its own lanes disagree"
    )

def probe_a_mutated_snapshot_is_named() -> None:
    """Criterion 2, leg 1 — a MUTATED snapshot must be REPORTED, never silently replayed.

    The gate is only a correctness check if a wrong snapshot can turn it red. Two
    mutations are driven: `resolved_at` (the stamp, which no side normalizes away because
    both sides render from the SAME snapshot) and a state-bearing key (`bindings`). Each
    must be reported in BOTH artifacts — the two-artifact shape is asserted, not assumed,
    because a mutation reaching one artifact would still pass a one-artifact assertion.

    The binding to mutate is chosen by the PREDICATE that makes it render-relevant, never
    by its POSITION in the list (#151, ruled n=988). `render_carried_binding_index` reads
    the renderer's own lane resolution and returns a row whose removal must change the
    bytes; the probe asserts it FOUND such a row BEFORE mutating, so a snapshot with none
    fails on its own precondition instead of reporting a clean verdict it never earned.
    """
    revision, blobs, snapshot, problems = _committed_replay()
    if problems:
        check("a MUTATED snapshot is NAMED as drift", False,
              f"committed replay unavailable: {problems[0][:80]}")
        return

    baseline = gate_a_problems(blobs, snapshot, revision)
    check(
        "the UNMUTATED committed pair replays clean, so the mutations below are the cause",
        baseline == [],
        "; ".join(baseline)[:110],
    )

    stamped = copy.deepcopy(snapshot)
    stamped["resolved_at"] = "2030-01-01T00:00:00Z"
    drift = gate_a_problems(blobs, stamped, revision)
    check(
        "a snapshot whose `resolved_at` is MUTATED is NAMED as drift in both artifacts",
        len(drift) == 2,
        f"{len(drift)} problem(s) reported",
    )

    target, why = render_carried_binding_index(snapshot)
    check(
        "the state-bearing mutation TARGETS a binding the render carries, so the probe can bite",
        target is not None,
        why[:110],
    )
    if target is None:
        return

    keyed = copy.deepcopy(snapshot)
    keyed["bindings"] = [
        row for index, row in enumerate(snapshot["bindings"]) if index != target
    ]
    drift = gate_a_problems(blobs, keyed, revision)
    check(
        "...and a STATE-BEARING key mutated is NAMED too, so no key is normalized away",
        len(drift) == 2,
        f"{len(drift)} problem(s) reported after dropping {why}",
    )

def probe_a_hand_edited_committed_artifact_is_named() -> None:
    """Criterion 2, leg 2 — a hand-edited COMMITTED artifact must be reported.

    The snapshot is left untouched and one committed blob is edited instead, which is the
    opposite direction from the probe above: there the artifact was right and the snapshot
    wrong, here the snapshot is right and the artifact wrong. Both directions must be
    named, and the untouched artifact in the same pair must stay silent — otherwise a
    comparison that reported every file on any difference would pass this probe.
    """
    revision, blobs, snapshot, problems = _committed_replay()
    if problems:
        check("a hand-edited COMMITTED artifact is NAMED as drift", False,
              f"committed replay unavailable: {problems[0][:80]}")
        return

    md_rel = relpath(rr.MD_PATH)
    edited = dict(blobs)
    edited[md_rel] = edited[md_rel].replace(
        "Generated file.", "Generated file. HAND EDIT.", 1
    )
    drift = gate_a_problems(edited, snapshot, revision)
    check(
        "a hand-edit to the COMMITTED artifact is NAMED as drift",
        any(md_rel in p and "HAND EDIT" in p for p in drift),
        drift[0][:110] if drift else "no problem reported",
    )
    check(
        "...while the untouched artifact of the same pair is NOT reported",
        not any(relpath(rr.INDEX_PATH) in p for p in drift),
        f"{len(drift)} problem(s): {'; '.join(drift)[:80]}",
    )


# The marker the working-tree probe writes. The probe writes its BYTES and the assertion
# searches the TEXT, so one constant keeps the two from drifting apart — and the marker is
# what makes the assertion deterministic rather than live-state dependent: HEAD cannot
# contain it and the live render cannot contain it, so it can only appear in the monitor's
# output if the monitor read the working tree.
TREE_EDIT_MARKER = "<!-- working-tree-only edit -->"


def probe_a_working_tree_edit_does_not_move_the_verdict() -> None:
    """Criterion 3 — a working-tree edit must move NEITHER the verdict NOR the monitor:
    both read HEAD, and neither reads the working tree.

    This is the split's load-bearing property: GATE A reads HEAD, so a tree re-rendered
    (or hand-edited) without committing is not read as a pass. If the gate read the
    working tree it would go GREEN on exactly the drift it exists to catch — so this probe
    is what distinguishes the two read paths.

    The monitor is bound here by the MARKER its own edit writes, never by the text it
    happens to return and never by a before/after DELTA. Two earlier bindings each passed
    for a reason unrelated to their own stimulus (#113): asserting that MOVED appears made
    the probe pass whenever genuine drift happened to exist and fail once the render was
    fresh; and asserting that two consecutive monitor reads are IDENTICAL is not a property
    this probe controls — the monitor re-reads LIVE state on every call, so that comparison
    flaked the moment live state moved between the two calls, which it did. The marker is
    deterministic: HEAD cannot contain it and the live render cannot contain it, so it can
    only appear if the monitor read the working tree. The monitor's sensitivity to LIVE
    state is probed directly by the `drift_problems` hand-edit probe above, and its read
    path is proven load-bearing by the bite probe below, which substitutes a monitor that
    reads the working tree and requires THIS probe to fail.

    The working-tree file is written, measured and RESTORED byte-identically, and the
    restoration is asserted by digest inside the probe rather than trusted: a probe that
    left the tree dirty would corrupt every later reading, its own included.
    """
    before = len(counts)
    original = rr.MD_PATH.read_bytes()
    digest = hashlib.md5(original).hexdigest()
    try:
        rr.MD_PATH.write_bytes((TREE_EDIT_MARKER + "\n").encode() + original)
        verdict = check_render_reproduces()
        del counts[before:]  # the probe drives the verdict; it does not report a second time
        monitor = report_freshness()
    finally:
        rr.MD_PATH.write_bytes(original)

    check(
        "a WORKING-TREE edit does NOT move GATE A's verdict — it reads HEAD, not the tree",
        verdict == [],
        "; ".join(verdict)[:110] if verdict else "",
    )
    check(
        "...and the working-tree file is restored byte-identical, asserted by digest",
        hashlib.md5(rr.MD_PATH.read_bytes()).hexdigest() == digest,
        f"md5 {digest[:12]}",
    )
    check(
        "...and the freshness MONITOR does not see the edit either — its committed side "
        "comes from HEAD through the same committed_blob the gate uses, so the marker text "
        "this probe wrote cannot appear anywhere in its output",
        not monitor.startswith("NOT TAKEN") and TREE_EDIT_MARKER not in monitor,
        monitor[:110],
    )

def probe_the_monitor_read_path_is_load_bearing() -> None:
    """The BITE for the assertion above — the monitor's read path is proven, not asserted.

    An exit 0 over an unchanged file shows nothing, so the probe above is shown to be
    non-vacuous by a MECHANISM REVERT: `report_freshness` is swapped for a substituted
    monitor that reads the WORKING TREE where the real one reads HEAD, and the probe must
    then FAIL. The failure is required to NAME the assertion rather than merely to be
    non-empty — a probe that broke for an unrelated reason would satisfy "it failed" while
    proving nothing about the read path.

    The substitution is scoped to this probe: the module global is restored in a `finally`,
    so the informational line `main()` prints after the probes uses the real monitor.
    """
    real = globals()["report_freshness"]
    globals()["report_freshness"] = _monitor_reading_the_working_tree
    try:
        mark = len(failures)
        probe_a_working_tree_edit_does_not_move_the_verdict()
        produced = failures[mark:]
        # The failure this probe INDUCED is its evidence, not the gate's verdict: it is
        # captured above and removed here, or the deliberately-reverted run would leave the
        # gate exiting 1 on a tree where every real check is clean.
        del failures[mark:]
    finally:
        globals()["report_freshness"] = real

    check(
        "the probe BITES: a monitor that reads the WORKING TREE makes it FAIL, naming the "
        "monitor assertion — so that assertion is load-bearing, not decoration",
        any("freshness MONITOR does not see the edit" in name for name in produced),
        f"the reverted read path produced {len(produced)} failure(s): "
        + ("; ".join(name[:70] for name in produced) if produced else "none"),
    )


def _announcement(ident: str, text: str, **over) -> dict:
    entry = {
        "id": ident,
        "scope": "profile",
        "severity": "info",
        "text": text,
        "affects": ["profile"],
        "since": "2026-09-19",
        "review_by": "2026-12-19",
        "evidence": "probe fixture, never a live declaration",
    }
    entry.update(over)
    return entry

# The probe pair uses REAL factory slugs, not synthetic ones: `validate_fragment` resolves
# `factory` against `KNOWN_FACTORY_SLUGS`, so a pair named "alpha"/"beta" is rejected by
# the validator and would prove the MERGE while skipping the DECLARATION — the half a peer
# actually writes, and the half a schema can reject.
#
# WHICH slugs those are is the box's own declaration, read from the fleet manifest, not a
# fact this gate may restate. A hardcoded pair REDs on a bootstrapped factory before it has
# enrolled anything, and the failure would name a factory that box does not have.
def probe_slugs() -> tuple[str, str]:
    """Two declared slugs, in manifest order — a probe needs a peer to merge with."""
    ordered = [record["slug"] for record in reg.MANIFEST["factories"]]
    if len(ordered) < 2:
        raise SystemExit(
            f"this gate probes a merge between two factories; the fleet manifest declares "
            f"{len(ordered)} ({', '.join(ordered) or 'none'}) — declare a second factory, or "
            f"the probe has nothing to merge"
        )
    return (ordered[0], ordered[1])


def _fragment(slug: str, announcements: list[dict]) -> dict:
    # The repo and skill come from the manifest too: they are DECLARED paths, and a
    # synthesized `/root/<slug>` would be a second, wrong declaration of the same fact.
    return {
        "factory": slug,
        "display_name": reg.FACTORY_DISPLAY_NAMES[slug],
        "profile": reg.FACTORY_PROFILE,
        "repo": reg.FACTORY_REPOS[slug],
        "skill": reg.FACTORY_SKILLS[slug],
        "purpose": f"{slug} purpose",
        "zone": {"owns": ["x"], "does_not_own": ["y"]},
        "services": [],
        "substrates_owned": ["s"],
        "announcements": announcements,
        "lanes": [],
        "status": "unattested",
        "attested_at": None,
    }

def _fragments_on_disk(
    fragments: list[dict],
) -> tuple[list[dict], list[str], tempfile.TemporaryDirectory]:
    """Write fragments as REAL files and read them back through the gate's own loader.

    The announcement probes below drive the clauses through the same path the live check
    uses — a JSON file on disk, `reg.load_fragment`, `reg.validate_fragment` — rather than
    through an in-memory dict the loader never sees. A probe that hands the merge function a
    dict it built itself proves the MERGE and skips the DECLARATION, which is the half a
    peer actually writes and the half a schema can reject.
    """
    tmp = tempfile.TemporaryDirectory()
    loaded: list[dict] = []
    errors: list[str] = []
    for fragment in fragments:
        path = Path(tmp.name) / f"{fragment['factory']}.json"
        path.write_text(json.dumps(fragment), encoding="utf-8")
        data, error = reg.load_fragment(path)
        if error:
            errors.append(f"{path.name}: {error}")
            continue
        errors.extend(reg.validate_fragment(data, str(path)))
        loaded.append(data)
    return loaded, errors, tmp

def _render_for(fragments: list[dict]) -> str:
    """The document for a synthetic fragment set — the Announcements section only."""
    merged, _problems = rr.collect_announcements(fragments)
    ctx = {
        "resolved_at": "2026-09-19T14:00:00Z",
        "factories": [
            {
                "fragment": fragment,
                "slug": fragment["factory"],
                "lanes": [],
                "skill_version": "0.0.0",
                "attested_at": None,
                "status": "unattested",
            }
            for fragment in fragments
        ],
        "announcements": merged,
        "jobs": [],
        "problems": [],
    }
    text = rr.render_markdown(ctx)
    return text.split("## Announcements", 1)[1].split("## Reachability", 1)[0]

def probe_same_id_same_text_is_one_entry() -> None:
    """Several lanes observing ONE fact is a legitimate duplicate, not a conflict."""
    note = "The registry renders one entry per `id`, with every declarer named."
    pair = probe_slugs()
    loaded, errors, tmp = _fragments_on_disk([
        _fragment(pair[0], [_announcement("shared-fact", note)]),
        _fragment(pair[1], [_announcement("shared-fact", note)]),
    ])
    check(
        "both duplicate declarations are VALID fragments, loaded from disk",
        errors == [] and len(loaded) == 2,
        "; ".join(errors)[:110] or f"{len(loaded)} fragment(s) loaded",
    )
    merged, conflicts = rr.collect_announcements(loaded)
    check(
        "same `id` + same `text` merges to ONE entry naming BOTH origins",
        len(merged) == 1 and conflicts == []
        and sorted(merged[0]["origins"]) == sorted(pair),
        f"entries={len(merged)} origins={merged[0]['origins'] if merged else []} "
        f"conflicts={len(conflicts)}",
    )
    rendered = _render_for(loaded)
    check(
        "...and it RENDERS once, not twice",
        rendered.count("**`shared-fact`**") == 1,
        f"{rendered.count('**`shared-fact`**')} rendering(s) in the Announcements section",
    )
    del tmp

def probe_differing_text_under_one_id_fails() -> None:
    """Two lanes publishing contradictory guidance under one name must fail, named."""
    pair = probe_slugs()
    loaded, errors, tmp = _fragments_on_disk([
        _fragment(pair[0], [_announcement("contested", "Read the DB with the mode=ro URI.")]),
        _fragment(pair[1], [_announcement("contested", "Copy the DB to /tmp and read that.")]),
    ])
    check(
        "each side of the contradiction is a VALID fragment alone — the conflict is not a schema fault",
        errors == [] and len(loaded) == 2,
        "; ".join(errors)[:110] or f"{len(loaded)} fragment(s) loaded",
    )
    merged, conflicts = rr.collect_announcements(loaded)
    check(
        "same `id` with DIFFERING `text` is reported as a conflict",
        len(conflicts) == 1,
        f"{len(conflicts)} conflict(s)",
    )
    check(
        "...naming BOTH origins",
        bool(conflicts) and all(slug in conflicts[0] for slug in pair),
        conflicts[0][:110] if conflicts else "no conflict reported",
    )
    check(
        "...and the contradiction is RENDERED, never silently resolved",
        "CONFLICTING TEXT" in _render_for(loaded),
        "the render hides which text won",
    )
    check(
        "...while the merged view still carries one entry, so the conflict is the finding",
        len(merged) == 1 and merged[0]["conflict"] != [],
        f"entries={len(merged)} conflicts={merged[0]['conflict'] if merged else []}",
    )
    del tmp

def probe_a_warning_without_evidence_fails() -> None:
    """Severity `warning`/`critical` demands evidence, and the LOADER is where it lands."""
    pair = probe_slugs()
    _loaded, errors, tmp = _fragments_on_disk([
        _fragment(pair[0], [
            _announcement("unevidenced", "Peers act on this.", severity="warning", evidence="")
        ]),
    ])
    check(
        "a `warning`-severity announcement with empty `evidence` FAILS the fragment loader",
        any("requires `evidence`" in e for e in errors),
        errors[0][:110] if errors else "no error reported",
    )
    _ok, ok_errors, ok_tmp = _fragments_on_disk([
        _fragment(pair[0], [_announcement("evidenced", "Peers act on this.", severity="warning")]),
    ])
    check(
        "...and the same entry carrying evidence passes",
        ok_errors == [],
        "; ".join(ok_errors)[:90],
    )
    del tmp, ok_tmp

def probe_a_deferral_without_a_reason_fails() -> None:
    """O6's asymmetry: `deferred`/`not-applicable` must name WHY, and the LOADER is where it lands.

    The clause's own wording is "behind by N, deferred because X", so a deferral carrying
    no X is the undeclared state wearing a declared label — which is the thing the field
    exists to make impossible. The four accepted arms are here beside the refused ones
    because a schema that refuses everything is as useless as one that refuses nothing:
    `adopted` carries no reason by design, and `kit` ABSENT is still valid while the
    obligation is new, so the field's arrival cannot red a member that has not answered.
    """
    pair = probe_slugs()
    arms = (
        ("adopted with no reason", {"state": "adopted"}, True),
        ("partial with behind_by", {"state": "partial", "behind_by": 88}, True),
        ("deferred WITH a reason", {"state": "deferred", "reason": "waiting on the pin pair"}, True),
        (
            "not-applicable WITH a reason",
            {"state": "not-applicable", "reason": "upstream source, no pin"},
            True,
        ),
        ("deferred with NO reason", {"state": "deferred"}, False),
        ("deferred with a blank reason", {"state": "deferred", "reason": "   "}, False),
        ("not-applicable with NO reason", {"state": "not-applicable"}, False),
        ("a state outside the four", {"state": "maybe"}, False),
        ("no state at all", {"reason": "x"}, False),
        ("an unknown key", {"state": "adopted", "drift": 3}, False),
        ("behind_by that is not an int", {"state": "partial", "behind_by": "many"}, False),
        ("measured_at that is not ISO", {"state": "adopted", "measured_at": "yesterday"}, False),
    )
    for label, kit, expect_ok in arms:
        fragment = _fragment(pair[0], [])
        fragment["kit"] = kit
        _loaded, errors, tmp = _fragments_on_disk([fragment])
        kit_errors = [e for e in errors if ": kit" in e]
        check(
            f"kit {label} -> {'accepted' if expect_ok else 'refused'}",
            (not kit_errors) == expect_ok,
            kit_errors[0][:110] if kit_errors else "accepted",
        )
        del tmp
    # The control that keeps the field from arriving as a hard requirement: absent is valid.
    _loaded, errors, tmp = _fragments_on_disk([_fragment(pair[0], [])])
    check(
        "kit ABSENT is still valid while the obligation is new",
        not [e for e in errors if "kit" in e],
        "; ".join(e for e in errors if "kit" in e)[:100] or "accepted",
    )
    del tmp


def probe_a_per_instrument_declaration_needs_both_axes() -> None:
    """The per-instrument map: one vocabulary with the kit, plus the phantom-name control.

    Frame 7.2 requires a deferrable instrument to NAME its declaration surface and that
    the surface CARRY A FIELD. It also establishes that HELD and GREEN are independent and
    that the declared state names both — so `adopted` cannot be claimed while red on the
    member's own gate, which is the manufactured adoption the frame measured on 2026-09-27.

    The key check is the control the kit field cannot have: the census derives an
    instrument's declared set from docs/instruments/<slug>.md, so a slug with no law doc is
    a phantom name rather than a disposition. Refusing it here is what stops a typo
    censusing zero paths and reading as a clean member.
    """
    pair = probe_slugs()
    arms = (
        # accepted — a real instrument, both axes named
        ("ledger adopted + green", {"ledger": {"state": "adopted", "green": True}}, True),
        ("ledger partial + behind_by", {"ledger": {"state": "partial", "behind_by": 2, "green": False}}, True),
        (
            "ledger deferred WITH a reason",
            {"ledger": {"state": "deferred", "reason": "waiting on the pin pair"}},
            True,
        ),
        (
            "two instruments in one map",
            {
                "ledger": {"state": "adopted", "green": True},
                "pacemaker": {"state": "not-applicable", "reason": "no pacemaker here"},
            },
            True,
        ),
        # refused — the both-axes rule, which is what separates this from the kit field
        ("adopted with NO green", {"ledger": {"state": "adopted"}}, False),
        ("adopted with green:false", {"ledger": {"state": "adopted", "green": False}}, False),
        ("green that is not a boolean", {"ledger": {"state": "partial", "green": "yes"}}, False),
        ("deferred with NO reason", {"ledger": {"state": "deferred"}}, False),
        # refused — the phantom-name control
        ("a slug with no law doc", {"nosuch-instrument": {"state": "partial"}}, False),
        # refused — the shared vocabulary still closes unknown keys
        ("an unknown key", {"ledger": {"state": "partial", "drift": 3}}, False),
    )
    for label, instruments, expect_ok in arms:
        fragment = _fragment(pair[0], [])
        fragment["instruments"] = instruments
        _loaded, errors, tmp = _fragments_on_disk([fragment])
        ins_errors = [e for e in errors if ": instruments" in e]
        check(
            f"instruments {label} -> {'accepted' if expect_ok else 'refused'}",
            (not ins_errors) == expect_ok,
            ins_errors[0][:110] if ins_errors else "accepted",
        )
        del tmp
    # The control that keeps the field from arriving as a hard requirement: absent is valid,
    # so its arrival cannot red a member that has not answered — the same asymmetry the kit
    # field's own probe pins.
    _loaded, errors, tmp = _fragments_on_disk([_fragment(pair[0], [])])
    check(
        "instruments ABSENT is still valid while the obligation is new",
        not [e for e in errors if "instruments" in e],
        "; ".join(e for e in errors if "instruments" in e)[:100] or "accepted",
    )
    del tmp
    # And the two surfaces must not diverge in vocabulary: a kit `deferred` and an
    # instrument `deferred` are refused by ONE predicate for the SAME reason.
    kit_errs = reg.validate_disposition("k", "kit", {"state": "deferred"})
    ins_errs = reg.validate_disposition("i", "instruments.ledger", {"state": "deferred"})
    check(
        "kit and instruments share one deferral rule",
        bool(kit_errs) and bool(ins_errs)
        and kit_errs[0].split("requires")[-1] == ins_errs[0].split("requires")[-1],
        f"kit={kit_errs[0][-40:]!r} instr={ins_errs[0][-40:]!r}",
    )


def probe_a_command_shaped_check_fails() -> None:
    """`check` names a predicate; a raw command is rejected rather than executed."""
    command: list[str] = []
    reg.validate_announcements(
        [_announcement("cmd", "text", check="test -x /usr/bin/sqlite3")],
        "probe",
        reg.SCOPES,
        command,
    )
    check(
        "a command-shaped `check` is REJECTED",
        any("looks like a command" in e for e in command),
        command[0][:110] if command else "no error reported",
    )
    unknown: list[str] = []
    reg.validate_announcements(
        [_announcement("typo", "text", check="sqlite3_present_typo")], "probe", reg.SCOPES, unknown
    )
    check(
        "an unknown predicate NAME is rejected too",
        any("unknown check" in e for e in unknown),
        unknown[0][:110] if unknown else "no error reported",
    )

def probe_a_future_review_by_fails() -> None:
    errors: list[str] = []
    reg.validate_announcements(
        [_announcement("backwards", "text", since="2026-09-19", review_by="2026-09-01")],
        "probe",
        reg.SCOPES,
        errors,
    )
    check(
        "a `review_by` that precedes `since` is rejected",
        any("precedes" in e for e in errors),
        errors[0][:110] if errors else "no error reported",
    )

def probe_the_box_wide_reader_reaches_the_default_home() -> None:
    """#102: the box-wide leg is a SUPERSET of the profile glob, and it says so.

    The defect this pins is a claim wider than its reader: `check_cron_min_gap_ge_6h`
    claims the BOX and read `profile_db_glob()`, so the one job on this box below the
    6 h floor — in the DEFAULT home — sat outside the population the predicate could
    see, and the predicate reported HOLDS.

    The fixture is a THROWAWAY root, so no live DB is opened and the offender can be
    placed exactly where the old reader could not reach it. Both halves of the fix are
    asserted: the wider reader FINDS it, and a home the enumeration cannot reach is
    REPORTED as unreached rather than silently dropped — a narrower read that says so
    is the point, because a narrower read that stays quiet is the defect.
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Root A carries BOTH a default home and a profile home, plus a directory that
        # yields no DB at all.
        root_a = base / "a" / "profiles"
        (root_a / "ops").mkdir(parents=True)
        (root_a / "ghost").mkdir()
        default_db = base / "a" / "opencrabs.db"
        profile_db = root_a / "ops" / "opencrabs.db"
        for path, rows in (
            (default_db, [("default-offender", "0 9,14,19 * * *")]),
            (profile_db, [("profile-fine", "0 */6 * * *")]),
        ):
            conn = sqlite3.connect(path)
            conn.execute("create table cron_jobs(name text, cron_expr text, enabled integer)")
            conn.executemany("insert into cron_jobs values (?, ?, 1)", rows)
            conn.commit()
            conn.close()

        dbs, unreached = reg.opencrabs_home_dbs(root=root_a)
        check(
            "the box-wide reader opens the DEFAULT home the profile glob cannot reach",
            default_db in dbs and profile_db in dbs,
            f"{len(dbs)} db(s): {[d.parent.name for d in dbs]}",
        )
        offenders, _unreadable, checked = reg.cron_min_gap_problems(dbs)
        check(
            "...and the offender in that default home is FOUND, not skipped",
            any("default-offender" in o and "300 min" in o for o in offenders),
            f"{checked} job(s) read; offenders: {offenders}",
        )
        check(
            "a home that yields no DB is REPORTED as unreached, never omitted",
            any("ghost" in u for u in unreached),
            f"unreached: {unreached}",
        )

        # Root B has no default home at all. An absent default home must be stated as
        # absent: "nothing to check there" and "clean there" are different answers.
        root_b = base / "b" / "profiles"
        root_b.mkdir(parents=True)
        _dbs_b, unreached_b = reg.opencrabs_home_dbs(root=root_b)
        check(
            "an ABSENT default home is stated as absent, not read as clean",
            any("default home" in u for u in unreached_b),
            f"unreached: {unreached_b}",
        )

        # The widening must NOT have leaked into the profile-scoped reader: its four
        # consumers resolve declared lanes against ONE manifest's profiles, and adding
        # another home's bindings to that match set is how a resolver picks the wrong
        # daemon. A strict subset is the property, not a count — the count moves with
        # whatever probe profiles happen to exist on the box.
        box_dbs, _ = reg.opencrabs_home_dbs()
        globbed = reg.profile_db_glob()
        check(
            "profile_db_glob() keeps its profile scope — the box reader is a strict superset",
            set(globbed) < set(box_dbs)
            and all(str(p).startswith(str(reg.PROFILE_ROOT)) for p in globbed),
            f"profile glob {len(globbed)} db(s), box reader {len(box_dbs)} db(s)",
        )

def _manifest_record(slug: str, prefixes: list) -> dict:
    """One minimal manifest record — every key `MANIFEST_RECORD_KEYS` demands."""
    return {
        "slug": slug,
        "display_name": slug,
        "chat_id": -1000000000000 - len(slug),
        "repo": f"owner/{slug}",
        "skill": f"skills/{slug}/SKILL.md",
        "job_prefixes": prefixes,
        "aliases": [],
    }

def _write_manifest(tmp: Path, records: list[dict]) -> Path:
    """A throwaway manifest. No live file is read or written by these probes."""
    path = tmp / "fleet.json"
    path.write_text(
        json.dumps(
            {"profile_root": "/tmp/probe-profiles", "profile": "probe", "factories": records}
        ),
        encoding="utf-8",
    )
    return path

def _manifest_verdict(records: list[dict]) -> tuple[bool, str]:
    """Load a fixture manifest. Returns (loaded_clean, message_or_reason)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_manifest(Path(tmp), records)
        try:
            reg.load_fleet_manifest(path)
        except reg.FleetManifestError as exc:
            return False, str(exc)
        return True, "loaded clean"

def probe_a_factory_with_no_prefixes_fails() -> None:
    """#101: `job_prefixes` is required, but an EMPTY one is a manifest that cannot
    attribute anything — the key is present and the answer is missing.

    Both legs, because the negative alone is satisfiable by a fixture that fails for
    an unrelated reason: the control record proves the fixture shape loads, so the
    failure the negative leg reads is the empty list and nothing else.
    """
    ok, why = _manifest_verdict(
        [_manifest_record("beta", ["beta-"]), _manifest_record("alpha", [])]
    )
    check(
        "a factory declaring NO job_prefixes FAILS, naming the record",
        not ok and "alpha" in why and "job_prefixes" in why,
        why[:110],
    )

    ok, why = _manifest_verdict([_manifest_record("beta", ["beta-"])])
    check("...while the fixture shape itself loads clean", ok, why[:110])

def probe_overlapping_prefixes_fail() -> None:
    """#101: two factories claiming the same prefix — or one nesting inside another.

    The nesting case is the one that matters, and `str.startswith` is why: a job named
    `alpha-beta-job` matches BOTH `alpha-` and `alpha-beta-`, so before this check its
    owner was whichever entry the manifest happened to list first. That makes the OWNER
    a property of manifest ORDER, and a harmless reorder silently re-attributes jobs.

    The nesting pair is chosen to actually nest. The first draft of this probe used
    `oc-` against `ocx-` and passed the control leg by accident — `ocx-` does NOT start
    with `oc-`, so those two were already disjoint and the probe measured nothing.
    """
    ok, why = _manifest_verdict(
        [_manifest_record("alpha", ["oc-"]), _manifest_record("beta", ["cx-"])]
    )
    check(
        "...two prefixes that merely LOOK alike still load (control against over-refusal)",
        ok,
        why[:110],
    )

    ok, why = _manifest_verdict(
        [_manifest_record("alpha", ["oc-"]), _manifest_record("beta", ["oc-"])]
    )
    check(
        "two factories claiming the SAME prefix FAIL, naming both",
        not ok and "alpha" in why and "beta" in why and "oc-" in why,
        why[:110],
    )

    ok, why = _manifest_verdict(
        [_manifest_record("alpha", ["alpha-"]), _manifest_record("beta", ["alpha-beta-"])]
    )
    check(
        "a prefix NESTING inside another FAILS — the startswith shape attribution uses",
        not ok and "overlap" in why,
        why[:110],
    )

def probe_the_live_manifest_satisfies_the_prefix_law() -> None:
    """The shipped `registry/fleet.json` passes the new assertions — and they BITE.

    A validator nobody's data can fail is indistinguishable from no validator, so this
    probe also reports what it read: the prefixes actually declared, per factory.
    """
    data = reg.load_fleet_manifest()
    declared = {
        r["slug"]: list(r["job_prefixes"]) for r in data["factories"]
    }
    check(
        "the live manifest loads and every declared factory carries a prefix",
        bool(declared) and all(v for v in declared.values()),
        f"{len(declared)} factory(s): {declared}",
    )

CHECKS = (
    ("1. every fragment validates against the schema", check_fragments_validate),
    ("2+3. every declared lane resolves to a live binding", check_lanes_bound),
    ("4. GATE A: the committed artifacts replay their committed snapshot", check_render_reproduces),
    ("5. every known factory group is covered", check_coverage),
    ("6. resolved_at is present, parseable, not in the future", check_resolved_at),
    ("7. every announcement is well-formed and unambiguous", check_announcements),
)

PROBES = (
    probe_a_supersession_chain_is_not_ambiguity,
    probe_a_hand_edit_is_named,
    probe_only_the_stamp_advanced_passes,
    probe_the_sentinel_would_rewrite_badges,
    probe_a_mutated_snapshot_is_named,
    probe_a_hand_edited_committed_artifact_is_named,
    probe_a_working_tree_edit_does_not_move_the_verdict,
    probe_the_monitor_read_path_is_load_bearing,
    probe_same_id_same_text_is_one_entry,
    probe_differing_text_under_one_id_fails,
    probe_a_warning_without_evidence_fails,
    probe_a_deferral_without_a_reason_fails,
    probe_a_per_instrument_declaration_needs_both_axes,
    probe_a_command_shaped_check_fails,
    probe_a_future_review_by_fails,
    probe_the_box_wide_reader_reaches_the_default_home,
    probe_a_factory_with_no_prefixes_fails,
    probe_overlapping_prefixes_fail,
    probe_the_live_manifest_satisfies_the_prefix_law,
)

def main() -> int:
# STATED SKIP: docs/factory-registry.md + registry/index.json (factory data)
    print("Gate: factory registry")
    print(f"  predicate: {PREDICATE}")
    # THE REGISTRY IS FACTORY DATA (#199). `docs/factory-registry.md` and `registry/index.json`
    # are this factory's own records — generated from ITS fleet manifest — and the tree the kit
    # ships carries neither. Without this arm the gate died with FileNotFoundError in that tree:
    # a CRASH rather than a verdict, over a subject that is absent by design. The artifact is
    # named, so a reader can tell "nothing to judge yet" from "clean".
    if not rr.MD_PATH.is_file() or not rr.INDEX_PATH.is_file():
        missing = [str(p.relative_to(REPO)) for p in (rr.MD_PATH, rr.INDEX_PATH) if not p.is_file()]
        print(f"  SKIPPED — no {', '.join(missing)} in this tree, so there is no registry to "
              f"judge. Both are FACTORY DATA generated from this factory's own fleet manifest; "
              f"the kit ships the shape, not a member's records.")
        return 0
    print("")
    for label, function in CHECKS:
        problems = function()
        check(label, not problems, problems[0][:120] if problems else "")
        for extra in problems[1:]:
            print(f"        - {extra[:160]}")
    print("")
    print("Freshness monitor (informational — printed OUTSIDE the verdict):")
    print(f"  {report_freshness()}")
    print("")
    print("Acceptance probes (each drives the live comparison or the validator directly):")
    for probe in PROBES:
        probe()
    print("")
    for line in counts:
        print(f"  {line}")
    print("")
    if failures:
        print(f"FAIL — {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print(f"OK — {len(CHECKS)} check(s) clean, {len(PROBES)} probe(s) passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
