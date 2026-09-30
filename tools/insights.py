#!/usr/bin/env python3
"""Append and verify immutable insights in evidence/insights.jsonl.

Insights record the empirical discoveries, paradoxes, and mechanisms uncovered
while operating and observing agent factories.

Every entry carries an AUTHOR, so the register distinguishes the owner's own
insights from a lane's. `--author` is explicit; omitted, it is DERIVED from the
writing session (`OPENCRABS_SESSION_ID`) and never defaulted — the same identity
law the ledger reads its own actor under.

Every entry also carries a CLASS, and there are exactly two:

  general         the claim stands outside this fleet: publishable content
  implementation  its subject is this fleet's own machinery: an internal
                  amendment for HQ

`--class` is required. An entry that names no audience feeds neither consumer, and
the two are read by different downstream surfaces, so an unclassified row is
unusable rather than merely tidy.

Every entry also carries a STATUS, which is where it stands in the WORKFLOW rather
than what kind of claim it is. The two axes are orthogonal, and a row needs both to
be actionable:

  pending     recorded; no destination ruled on yet
  publishing  earmarked for the content funnel (the site, the channel, X)
  hq          earmarked for HQ, as an internal process amendment
  published   terminal: the public unit went out
  landed      terminal: HQ acted and a process changed
  refused     NON-terminal: a CONSUMER refused it, and the OWNER now gates it
  dropped     terminal: deliberately not acted on

`refused` is not a synonym for `dropped`, and the difference is who decided. A consumer
refusing a unit is not the owner declining it, so recording the one as the other would
assert a decision nobody took. A refused row therefore WAITS — it is put in front of
the owner for gating, with the refusal's grounds, and it leaves the state by his answer
rather than by anyone's judgement.

A REFUSED or DROPPED row carries a REASON, and these are the statuses that demand a
second field. The status says a unit was not acted on; the reason says why, and
without it the record cannot be checked later or reused. Law section 6 rules 4 and 6
have stated that requirement since the axis landed; here it stops being prose and
becomes a check — the write path REFUSES such a row with no reason, and `verify`
REPORTS one that reached the store anyway. The requirement travels with the status:
when the owner OVERTURNS a refusal the grounds are cleared in the same act, because a
reason on a row that is no longer refused would be grounds for a decision the status
says was never taken.

A CORRECTION is a SUPERSEDING ROW, never an edit. The claims are append-only, so
fixing a stored figure is a NEW row that names the row it corrects (`--supersedes N`)
and carries the corrected value. Readers take the NEWEST governing row, and every
superseded row PRINTS with its number, value and instant — never silence, because a
value that quietly stopped applying is the failure this shape exists to prevent. One
row has ONE successor, or "the newest governs" stops being decidable.

Usage:
  python3 tools/insights.py append <id> <topic> <stage> <naive_assumption> <empirical_reality> <mechanism> [options]
  python3 tools/insights.py list
  python3 tools/insights.py format <id> [--format=tweet|ru|markdown]
  python3 tools/insights.py verify
  python3 tools/insights.py classify --file <mapping.json>   # backfill the class on existing rows
  python3 tools/insights.py status --file <mapping.json>     # move existing rows to a new status
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSIGHTS_PATH = REPO / "evidence" / "insights.jsonl"
LOCK_PATH = REPO / "evidence" / ".insights.lock"

ALLOWED_STAGES = ["stage-0", "stage-1", "stage-2", "stage-3", "stage-4", "fleet-wide"]

# The register feeds TWO consumers, so every entry names the one it serves. The values
# are deliberately coarse: an AUDIENCE split, not a topic taxonomy. A finer value would
# be a second axis pretending to be this one.
ALLOWED_CLASSES = ["general", "implementation"]

# The second axis, deliberately NOT a renaming of the first: `class` says what kind of
# claim the entry is (who it serves), `status` says where it stands in the workflow
# (what has been DONE about it). The values name the two destinations and the terminals
# they can reach, because a routing register that cannot tell "queued for publishing"
# from "published" is a register of intentions rather than of state.
#
# `refused` is deliberately NON-terminal, and that is the whole reason it exists: a
# CONSUMER (the content funnel) refused the unit, and the refusal is now in front of the
# OWNER for gating — so it is a state that is waiting, not one that is settled. Recording
# a consumer's refusal as `dropped` would say the owner decided against it, which is a
# decision nobody took (insights.md §6 rule 6). `dropped` then means only what it says:
# the owner, or the author acting on the owner's word, decided against it.
ALLOWED_STATUSES = ["pending", "publishing", "hq", "published", "landed", "refused", "dropped"]

# The statuses whose whole content is the decision behind them, so a bare verdict is a
# record with its reason missing. ONE home: the append path, the backfill path and
# `verify` all read this set, so what counts as "owes a reason" cannot drift between the
# three — a rule enforced on one write path and not another is the shape this factory
# files against.
REASON_REQUIRED_STATUSES = frozenset({"refused", "dropped"})

# The owner is an AUTHOR no session can stand for, so this literal is accepted
# as a first-class value and is NEVER derived.
OWNER_AUTHOR = "Alexey"

# The canonical key order. A field ADDED to an existing row is INSERTED at its
# position here, and every other key keeps the place it already had — so the diff
# a backfill produces is ADDITIVE: a reader scanning it meets one inserted label
# and no restated claim.
CANONICAL_ORDER = ["n", "id", "ts", "supersedes", "author", "class", "status",
                   "status_at", "reason",
                   "topic", "stage", "naive_assumption", "empirical_reality",
                   "mechanism", "tweet_hook", "ru_summary"]
_RANK = {k: i for i, k in enumerate(CANONICAL_ORDER)}


def _with_field(row: dict, key: str, value) -> dict:
    """`row` with `key` set, INSERTED at its canonical position.

    Nothing else moves: a key already present keeps its place, and a key absent from
    CANONICAL_ORDER is left where the row put it. Setting an ABSENT field is therefore
    purely additive, which is what makes a backfill reviewable — the diff shows one
    inserted label rather than a reshaped row.
    """
    if key in row:
        return {**row, key: value}
    target = _RANK[key]
    out: dict = {}
    placed = False
    for k, v in row.items():
        if not placed and _RANK.get(k, len(CANONICAL_ORDER)) > target:
            out[key] = value
            placed = True
        out[k] = v
    if not placed:
        out[key] = value
    return out


def _without_field(row: dict, key: str) -> dict:
    """`row` with `key` REMOVED, every other key keeping its place.

    The ONE non-additive edit this writer makes, and it is deliberate rather than a
    loophole in the additive promise: `reason` is a refusal's grounds, so it is true
    only while the status is one that owes one. A row whose refusal was overturned
    carries grounds that are no longer true of it — and `verify` refuses exactly that —
    so leaving the key would make the owner's own correction unwritable. Every other
    key keeps its position, so the diff shows one deleted label and no reshaped row.
    """
    return {k: v for k, v in row.items() if k != key}

# A binding title is written by the daemon and ends with the channel reference,
# e.g. `Telegram: Factories / Insights [chat:-100…:topic:6865]`.
_TITLE_TAIL_RE = re.compile(r"\[chat:[^\]]*\]\s*$")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lane_from_title(title: str | None) -> str | None:
    """The lane name carried by a binding title, or None.

    `Telegram: Factories / Insights [chat:-100…:topic:6865]` -> `Insights`.

    The last path segment is the lane, because the leading segments are the
    chat's and the chat is not the lane. This is the ONLY source for a topic no
    factory fragment declares, which is why it is read rather than assumed away.
    """
    text = _TITLE_TAIL_RE.sub("", str(title or "")).strip()
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    lane = text.rsplit("/", 1)[-1].strip()
    return lane or None


def resolve_author(session_id: str | None = None) -> tuple[str | None, str]:
    """The authoring lane, derived from the session that is WRITING.

    Identity is DERIVED from `OPENCRABS_SESSION_ID`, never declared — the same
    rule `tools/ledger.py` reads its own actor under, so a lane cannot silently
    mislabel itself here either. Two sources, in order, and they return DIFFERENT
    KINDS of string, which is why the order is a contract and not a preference:

    1. the fleet registry's DECLARED lanes — a factory fragment carries the lane's
       ROLE, so the answer is the SAME token `tools/ledger.py` derives and
       `tools/actors.txt` declares (`insights`, not `Factories / Insights`). A
       register row can therefore join to a ledger row on the same actor;
    2. the session's own BINDING TITLE — a last resort for a topic NO fragment
       declares, where it returns the title's final segment, a display name such
       as `Insights`. There is no curated role to read in that case, so the two
       legs are NOT interchangeable and the declared leg is asserted to win.

    Returns `(lane, reason)`. `lane` is None when neither source places the
    session, and `reason` then names what failed — never a silent fallback. A
    guessed author is worse than a missing one, because it reads as provenance.
    """
    sid = (session_id or os.environ.get("OPENCRABS_SESSION_ID") or "").strip()
    if not sid:
        return None, ("OPENCRABS_SESSION_ID is not set, so the authoring lane is "
                      "unidentifiable — pass --author")
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    try:
        import registry  # noqa: PLC0415 — lazy: an append must not pay for it
    except Exception as exc:  # an import failure is environmental, never an identity
        return None, f"the lane resolver is unavailable (registry import failed: {exc})"
    try:
        bindings, errors = registry.all_bindings()
    except Exception as exc:
        return None, f"the lane resolver is unavailable (binding read failed: {exc})"
    if not bindings:
        detail = f" ({'; '.join(errors)})" if errors else ""
        return None, f"no live binding was readable{detail}"
    mine = [b for b in bindings if b.get("session_id") == sid]
    if not mine:
        return None, f"session {sid} holds no live channel binding"

    paths: list[str] = []
    try:
        paths = registry.live_fragment_paths([])
        for path in paths:
            data, err = registry.load_fragment(path)
            if err or not isinstance(data, dict):
                continue
            chat_id = registry.FACTORY_CHATS.get(data.get("factory"))
            for lane in data.get("lanes") or []:
                if not isinstance(lane, dict):
                    continue
                resolved = registry.resolve_lane(lane, mine, {}, chat_id)
                if resolved.get("session_id") == sid:
                    role = resolved.get("role") or lane.get("role")
                    if role:
                        return str(role), ""
    except Exception as exc:
        return None, f"the lane resolver is unavailable (fragment read failed: {exc})"

    lane = _lane_from_title(mine[0].get("session_title"))
    if lane:
        return lane, ""
    return None, (f"session {sid} matches no lane declared in {len(paths)} fragment(s) "
                  f"and its binding title carries no channel name — pass --author")


def append_insight(
    slug: str,
    topic: str,
    stage: str,
    naive_assumption: str,
    empirical_reality: str,
    mechanism: str,
    tweet_hook: str = "",
    ru_summary: str = "",
    author: str = "",
    insight_class: str = "",
    status: str = "pending",
    reason: str = "",
    supersedes: int | None = None,
) -> dict:
    if stage not in ALLOWED_STAGES:
        raise ValueError(f"stage must be one of {ALLOWED_STAGES}, got '{stage}'")
    if not str(author or "").strip():
        raise ValueError("author is required — a row with no author reads as provenance "
                         "while carrying none")
    if not str(insight_class or "").strip():
        raise ValueError("class is required — an entry that names no audience feeds "
                         "neither the content pipeline nor HQ")
    if insight_class not in ALLOWED_CLASSES:
        raise ValueError(f"class must be one of {ALLOWED_CLASSES}, got '{insight_class}'")
    # Status is NOT required the way class is, and the asymmetry is the point: the author
    # knows the CLAIM's kind, but the destination is the owner's call, so this DEFAULTS
    # rather than being demanded. A value that IS given must still be in the vocabulary —
    # a typo'd status reads as a routing decision while feeding no consumer.
    if not str(status or "").strip():
        raise ValueError("status must not be blank — omit it to open at 'pending'")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"status must be one of {ALLOWED_STATUSES}, got '{status}'")
    # insights.md §6 rule 4 and rule 6, at the one place the row can still be refused. Checked
    # HERE rather than left to `verify` because a store-level check can only report a bad
    # row, while this one stops it existing — and `refused`/`dropped` are the statuses
    # whose whole content is the decision behind them, so a bare verdict is a record with
    # its reason missing.
    if status in REASON_REQUIRED_STATUSES and not str(reason or "").strip():
        raise ValueError(f"status '{status}' requires a --reason — a refusal and a silence "
                         f"are different records, and only one is checkable later")
    # The field's other lie, refused at the same place and from the same one home: a reason
    # states why a unit was refused or dropped, so one supplied on a live status is grounds
    # for a decision that the status says was never taken. `verify` and the backfill both
    # refuse this; leaving it to them would let the store accept a row its own reader
    # reports, which is the write-path/reader gap this file keeps closing.
    if str(reason or "").strip() and status not in REASON_REQUIRED_STATUSES:
        raise ValueError(
            f"status '{status}' does not carry a reason — a reason states why a unit was "
            f"refused or dropped ({'/'.join(sorted(REASON_REQUIRED_STATUSES))}), and "
            f"'{status}' is neither")

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            entries = []
            if INSIGHTS_PATH.is_file():
                for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        entries.append(json.loads(line))

            next_n = len(entries) + 1

            # An id identifies an INSIGHT, so a second row for one id is a REVISION and
            # must say which row it revises. Left unmarked it would be an ordinary
            # duplicate, and "the newest governs" would have nothing to resolve against.
            same_id = [e for e in entries if e.get("id") == slug]
            if same_id and supersedes is None:
                raise ValueError(
                    f"insight with id '{slug}' already exists — a second row for one id is "
                    f"a REVISION and must name the row it corrects (`--supersedes <n>`)")

            if supersedes is not None:
                if not isinstance(supersedes, int) or isinstance(supersedes, bool):
                    raise ValueError(
                        "supersedes must be the integer n of the row it corrects")
                prior = next((e for e in entries if e.get("n") == supersedes), None)
                if prior is None:
                    raise ValueError(
                        f"supersedes names n={supersedes}, which is not in the register "
                        f"(it holds {len(entries)} row(s))")
                if supersedes >= next_n:
                    raise ValueError(
                        f"supersedes must name an EARLIER row, got n={supersedes}")
                if prior.get("id") != slug:
                    raise ValueError(
                        f"supersedes names n={supersedes}, whose id is "
                        f"'{prior.get('id')}' — a revision carries the id of the insight "
                        f"it revises")
                already = next((e.get("n") for e in entries
                                if e.get("supersedes") == supersedes), None)
                if already is not None:
                    raise ValueError(
                        f"n={supersedes} is already superseded by n={already} — one row has "
                        f"ONE successor, or 'the newest governs' stops being decidable")

            entry: dict = {"n": next_n, "id": slug, "ts": now_iso()}
            if supersedes is not None:
                entry["supersedes"] = supersedes
            entry["author"] = str(author).strip()
            entry["class"] = str(insight_class).strip()
            entry["status"] = str(status).strip()
            entry["status_at"] = now_iso()
            if str(reason or "").strip():
                entry["reason"] = str(reason).strip()
            entry["topic"] = topic
            entry["stage"] = stage
            entry["naive_assumption"] = naive_assumption
            entry["empirical_reality"] = empirical_reality
            entry["mechanism"] = mechanism
            entry["tweet_hook"] = tweet_hook
            entry["ru_summary"] = ru_summary

            with open(INSIGHTS_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

            return entry
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


# Every labelled field, with the vocabulary its values come from. One table, so a new
# label is declared in ONE place and every verb below inherits its validation.
FIELD_VOCAB: dict[str, list[str]] = {"class": ALLOWED_CLASSES, "status": ALLOWED_STATUSES}


def _backfill(updates: dict[str, dict], fields: list[str], noun: str,
              optional_fields: list[str] | None = None) -> list[tuple[str, dict]]:
    """Set the labelled `fields` on entries that ALREADY EXIST, in one transaction.

    Shared by `classify` and `status`: both write a routing label onto existing rows,
    so both owe the same guarantees, and a second copy of this logic would be a second
    place for those guarantees to drift apart.

    `optional_fields` names fields a caller may set WITHOUT demanding one on every row —
    the split matters because `reason` is required only where a status makes it
    meaningful, so "every row must name it" would refuse the 23 rows it does not apply
    to. An optional field IS validated when it is given, and an unknown name is still
    refused, so the narrow-writer guarantee binds both kinds.

    The register is append-only in its CLAIMS, and this keeps that promise in the only
    way a backfill can: it writes the named fields and nothing else, INSERTED at their
    canonical positions, never touching a claim field. Every other key keeps the place
    it already had, so the diff is additive — a reader meets inserted labels rather than
    a reshaped row.

    All-or-nothing by construction: every id, every field name and every value is
    validated before a single byte is written, so a mapping carrying one unknown id
    writes NOTHING rather than a partial backfill — a half-applied change is worse than
    none, because it reads as complete.

    Returns `[(id, {field: prior_value})]` in register order. A prior value is None when
    the row predated the field, which is a different thing from an empty one.
    """
    optional = list(optional_fields or [])
    if not updates:
        raise ValueError(f"no {noun} given — pass an {{id: value}} mapping")
    for slug, value in updates.items():
        if not isinstance(value, dict):
            raise ValueError(f"{noun} for '{slug}' must be an object, got "
                             f"{type(value).__name__}")
        extra = sorted(set(value) - set(fields) - set(optional))
        if extra:
            raise ValueError(f"{noun} for '{slug}' carries unsettable field(s): "
                             f"{', '.join(extra)}")
        for name in fields:
            if name not in value:
                raise ValueError(f"{noun} for '{slug}' names no '{name}'")
            if name in FIELD_VOCAB and value[name] not in FIELD_VOCAB[name]:
                raise ValueError(f"{name} for '{slug}' must be one of "
                                 f"{FIELD_VOCAB[name]}, got '{value[name]}'")
        for name in optional:
            if name in value and not str(value[name] or "").strip():
                raise ValueError(f"{name} for '{slug}' is empty — omit the field rather "
                                 f"than writing a blank one")

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            entries = []
            if INSIGHTS_PATH.is_file():
                for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        entries.append(json.loads(line))

            known = {e.get("id") for e in entries}
            unknown = sorted(s for s in updates if s not in known)
            if unknown:
                raise ValueError(f"unknown id(s), nothing written: {', '.join(unknown)}")

            changes: list[tuple[str, dict]] = []
            cleared: list[str] = []
            out_rows: list[dict] = []
            for entry in entries:
                slug = entry.get("id")
                if slug not in updates:
                    out_rows.append(entry)
                    continue
                before = {name: entry.get(name) for name in fields}
                row = entry
                for name in fields:
                    row = _with_field(row, name, updates[slug][name])
                for name in optional:
                    if name in updates[slug]:
                        row = _with_field(row, name, updates[slug][name])
                # A reason RE-SUPPLIED by the mapping is a different act from the row's own
                # stale grounds, and it is refused rather than quietly absorbed: the caller
                # is asserting reasons for a status that does not take one. Checked BEFORE
                # the clear below, because the clear would otherwise swallow the input and
                # report success on a mapping it discarded — a silent drop, not a refusal.
                if ("reason" in updates[slug]
                        and str(updates[slug]["reason"] or "").strip()
                        and updates[slug].get("status", row.get("status"))
                        not in REASON_REQUIRED_STATUSES):
                    raise ValueError(
                        f"'{slug}' names a reason on status "
                        f"'{updates[slug].get('status', row.get('status'))}' — a reason "
                        f"states why a unit was refused or dropped, so it belongs to "
                        f"{'/'.join(sorted(REASON_REQUIRED_STATUSES))}")
                # The reason is the REFUSAL's grounds, so it is true only while the row sits
                # in a status that owes one. Moving a row OUT of that set — the owner
                # overturning a refusal, which is the whole point of the gate — would
                # otherwise leave grounds that are no longer true of it, and `verify`
                # refuses exactly that, so the owner's own answer could not land. The
                # key is REMOVED here rather than left to strand the correction, and the
                # removal is PRINTED: a deleted label announced is reviewable, one that
                # disappears silently is the class this register files against.
                if ("status" in updates[slug]
                        and updates[slug]["status"] not in REASON_REQUIRED_STATUSES
                        and "reason" in row):
                    row = _without_field(row, "reason")
                    cleared.append(slug)
                # insights.md §6 rule 4 and rule 6, checked on the row AS IT WOULD BE WRITTEN
                # rather than on the mapping alone: a row left in a reason-owing status
                # without one is the same defect as one appended that way, and a rule
                # enforced on one write path and not the other is the shape this factory
                # files against. Raised before any byte is written, so a mapping that
                # would strand a row writes nothing.
                if (row.get("status") in REASON_REQUIRED_STATUSES
                        and not str(row.get("reason") or "").strip()):
                    raise ValueError(
                        f"'{slug}' would be left '{row.get('status')}' with no reason — "
                        f"insights.md §6 rule 4 requires one, so name it in the same mapping")
                # The field's other lie, and the reason the clear above is needed: a reason
                # on a row whose status does not owe one reads as grounds for a decision
                # the status says was never taken.
                if (str(row.get("reason") or "").strip()
                        and row.get("status") not in REASON_REQUIRED_STATUSES):
                    raise ValueError(
                        f"'{slug}' would carry a reason on status '{row.get('status')}' — a "
                        f"reason states why a unit was refused or dropped, so it belongs to "
                        f"{'/'.join(sorted(REASON_REQUIRED_STATUSES))}")
                changes.append((slug, before))
                out_rows.append(row)

            # Atomic replace under the same lock the append takes, so a peer's
            # concurrent append can never interleave with this rewrite.
            tmp = INSIGHTS_PATH.parent / (INSIGHTS_PATH.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for row in out_rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, INSIGHTS_PATH)
            if cleared:
                # Never silent: the register's own law forbids a change that a reader
                # cannot see, and this one DELETES a label rather than adding one.
                print(f"cleared the reason on {len(cleared)} row(s) whose status no longer "
                      f"owes one: {', '.join(cleared)}")
            return changes
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def classify_insights(mapping: dict[str, str]) -> list[tuple[str, str | None, str]]:
    """Set `class` on entries that PREDATE the field. The owner rules on the values;
    this applies the ruling, and `_backfill` carries the guarantees behind it.
    """
    changes = _backfill({k: {"class": v} for k, v in mapping.items()},
                        ["class"], "classifications")
    return [(slug, before["class"] or None, mapping[slug]) for slug, before in changes]


def set_statuses(mapping: dict[str, object]) -> list[tuple[str, str | None, str]]:
    """Move existing entries to a new workflow `status`, stamping the instant they moved.

    `status_at` travels WITH the status rather than beside it, because an undated routing
    register cannot answer the question it exists to answer — which items are still owed,
    and for how long. A status that has never been set reads as absent, not as blank, so
    `pending` and "no status recorded" stay distinguishable in the same way `author` and
    `class` kept their legacy rows distinguishable from empty ones.

    A value may be the status alone or `{"status": …, "reason": …}`, because a row moved
    to `refused` or `dropped` owes a reason and one transaction should carry both — the
    alternative is a window in which such a row has no reason, which is the state
    insights.md §6 rule 4 forbids.

    Moving a row OUT of those statuses CLEARS its reason in the same transaction. That is
    not a convenience: it is what makes the owner's override landable, since a reason on a
    row that is no longer refused would be grounds for a decision the status says was
    never taken, and `verify` refuses exactly that.

    `{"status_at": …}` is accepted for ONE case and is refused everywhere else: a backfill
    that corrects a stored LABEL rather than recording a transition. The instant is then
    the transition the row ALREADY carries — when a consumer's refusal was recorded, say —
    and re-stamping it with `now()` would date that event to the day the label was fixed.
    An instant is READ, never composed, so the door is deliberately narrow: the value must
    equal the instant the row already holds, which makes it carry-forward only. It cannot
    be used to invent a date, which is the only thing that could go wrong with it.
    """
    stamp = now_iso()
    updates: dict[str, dict] = {}
    for k, v in mapping.items():
        if isinstance(v, dict):
            names = sorted(set(v) - {"status", "reason", "status_at"})
            if names:
                raise ValueError(f"status for '{k}' carries unsettable field(s): "
                                 f"{', '.join(names)}")
            if "status" not in v:
                raise ValueError(f"status for '{k}' names no 'status'")
            updates[k] = {"status": v["status"],
                          "status_at": v.get("status_at") or stamp}
            if "reason" in v:
                updates[k]["reason"] = v["reason"]
        else:
            updates[k] = {"status": v, "status_at": stamp}

    # The preserve-only door, checked against the rows BEFORE the transaction: a caller
    # may carry an instant forward, never mint one. Read here rather than inside
    # `_backfill` because it needs the row's PRIOR value, which the backfill deliberately
    # does not consult for the values it writes.
    carried = {k: v["status_at"] for k, v in updates.items()
               if isinstance(mapping.get(k), dict) and mapping[k].get("status_at")}
    if carried:
        prior = {r.get("id"): r.get("status_at") for r in _read_entries()}
        for slug, instant in carried.items():
            if slug not in prior:
                raise ValueError(f"status_at for '{slug}' names an unknown id")
            if prior[slug] != instant:
                raise ValueError(
                    f"status_at for '{slug}' is '{instant}', which the row does not carry "
                    f"(it holds '{prior[slug]}') — this door carries an existing instant "
                    f"forward and never mints one")

    changes = _backfill(updates, ["status", "status_at"], "statuses",
                        optional_fields=["reason"])
    return [(slug, before["status"] or None, updates[slug]["status"])
            for slug, before in changes]

def set_reasons(mapping: dict[str, str]) -> list[tuple[str, str | None, str]]:
    """Set `reason` on entries that already exist, WITHOUT touching their status instant.

    A separate verb from `status` on purpose: re-stating a row's status to record a
    reason would move `status_at`, and the instant is the field's whole value. This sets
    the reason and nothing else, so a backfilled reason cannot silently re-date the
    routing decision that produced it.
    """
    changes = _backfill({k: {"reason": v} for k, v in mapping.items()},
                        ["reason"], "reasons")
    return [(slug, before["reason"] or None, mapping[slug]) for slug, before in changes]


def _read_entries() -> list[dict]:
    """Every parsed row, in store order. The reader's one view of the register."""
    if not INSIGHTS_PATH.is_file():
        return []
    out: list[dict] = []
    for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

def _superseded_by(entries: list[dict]) -> dict[int, int]:
    """`{superseded_n: successor_n}` — the newest governing row, made explicit.

    A reader that resolves a correction must be able to SAY so, so this returns the map
    rather than a bare predicate: the superseded row prints the number that governs it,
    which is what turns "the newest wins" from a rule the reader applies silently into
    one the output shows.
    """
    out: dict[int, int] = {}
    for row in entries:
        target = row.get("supersedes")
        if isinstance(target, int) and not isinstance(target, bool):
            out[target] = row.get("n")
    return out

def verify_insights() -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not INSIGHTS_PATH.is_file():
        return True, []

    lines = [l.strip() for l in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen_ids = set()
    expected_n = 1
    parsed: list[dict] = []

    for idx, line in enumerate(lines, start=1):
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {idx}: invalid JSON: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"line {idx}: a row must be a JSON object")
            continue
        parsed.append(data)

        n = data.get("n")
        if n != expected_n:
            errors.append(f"line {idx}: expected n={expected_n}, got n={n}")
        expected_n += 1

        slug = data.get("id")
        if not slug:
            errors.append(f"line {idx}: missing id")
        elif slug in seen_ids:
            # A second row for one id is a REVISION, and must say which row it revises.
            # Unmarked it is an ordinary duplicate, and "the newest governs" would have
            # nothing to resolve against.
            if data.get("supersedes") is None:
                errors.append(f"line {idx}: duplicate id '{slug}' — a second row for one id "
                              f"is a revision and must declare 'supersedes'")
        else:
            seen_ids.add(slug)

        if data.get("stage") not in ALLOWED_STAGES:
            errors.append(f"line {idx}: invalid stage '{data.get('stage')}'")

        for req in ["topic", "naive_assumption", "empirical_reality", "mechanism"]:
            if not data.get(req):
                errors.append(f"line {idx}: missing required field '{req}'")

        # `author` is required on every row written since the field landed. Rows
        # predating it carry no key at all and stay valid — the register is
        # append-only, so history is not rewritten to invent one. An EMPTY value
        # is a defect either way: it reads as provenance while carrying none.
        if "author" in data and not data.get("author"):
            errors.append(f"line {idx}: empty author")

        # `class` follows the same rule as `author`: rows predating the field carry no
        # key at all and stay valid, while an EMPTY value is a defect either way. An
        # UNKNOWN value is the same defect wearing a value — a typo'd class feeds
        # neither consumer while reading as a classification.
        if "class" in data:
            if not data.get("class"):
                errors.append(f"line {idx}: empty class")
            elif data["class"] not in ALLOWED_CLASSES:
                errors.append(f"line {idx}: unknown class '{data['class']}'")

        # `status` follows the same rule as the two fields before it: a row predating the
        # field carries no key and stays valid, while an EMPTY or UNKNOWN value is a
        # defect either way. Its one shape unique to this field is a status with NO
        # instant — it cannot be aged out or swept by a deadline, so it is reported rather
        # than tolerated, since "how long has this been sitting here?" is the question the
        # field exists to make answerable.
        if "status" in data:
            if not data.get("status"):
                errors.append(f"line {idx}: empty status")
            elif data["status"] not in ALLOWED_STATUSES:
                errors.append(f"line {idx}: unknown status '{data['status']}'")
            elif not data.get("status_at"):
                errors.append(f"line {idx}: status '{data['status']}' carries no status_at")

        # insights.md §6 rule 4 and rule 6 — a status that owes a reason must carry one — is
        # enforced at the write path, and REPORTED here. Both are owed: the write path
        # stops the row existing, and this leg catches one that reached the store by
        # another route, which is the difference between a rule and a rule that holds.
        if (data.get("status") in REASON_REQUIRED_STATUSES
                and not str(data.get("reason") or "").strip()):
            errors.append(f"line {idx}: status '{data.get('status')}' carries no reason — "
                          f"insights.md §6 rule 4 requires one (a refusal and a silence are "
                          f"different records)")
        # A `reason` on a row whose status does not owe one is the field's other lie: it
        # reads as a decision's grounds while the status says no such decision was taken.
        if "reason" in data:
            if not str(data.get("reason") or "").strip():
                errors.append(f"line {idx}: empty reason")
            elif data.get("status") not in REASON_REQUIRED_STATUSES:
                errors.append(f"line {idx}: reason recorded on status "
                              f"'{data.get('status')}' — a reason states why a unit was "
                              f"refused or dropped, so it belongs to "
                              f"{'/'.join(sorted(REASON_REQUIRED_STATUSES))}")

    # Half 2 — supersession. A correction is a NEW row naming the row it corrects, and
    # the reader takes the NEWEST. Two ways that reading breaks, both checked here: a
    # pointer to a row that does not exist, and two successors for one row, which leaves
    # "newest" undecidable. Checked over the parsed rows, so a superseded row that was
    # never written is caught as the dangling reference it is.
    successors: dict[int, list[int]] = {}
    by_n = {r.get("n"): r for r in parsed if isinstance(r.get("n"), int)}
    for row in parsed:
        target = row.get("supersedes")
        if target is None:
            continue
        n = row.get("n")
        if not isinstance(target, int) or isinstance(target, bool):
            errors.append(f"n={n}: supersedes must be the integer n of the row it corrects")
            continue
        if target not in by_n:
            errors.append(f"n={n}: supersedes names n={target}, which is not in the register")
            continue
        if target >= n:
            errors.append(f"n={n}: supersedes names n={target}, which is not an EARLIER row")
        elif by_n[target].get("id") != row.get("id"):
            errors.append(f"n={n}: supersedes n={target} whose id is "
                          f"'{by_n[target].get('id')}' — a revision carries the id of the "
                          f"insight it revises")
        successors.setdefault(target, []).append(n)
    for target, rows in sorted(successors.items()):
        if len(rows) > 1:
            errors.append(f"n={target}: superseded by {len(rows)} rows "
                          f"({', '.join('n=' + str(r) for r in sorted(rows))}) — one row "
                          f"has ONE successor, or 'the newest governs' is undecidable")

    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Insights ledger manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_append = sub.add_parser("append", help="Append an empirical insight")
    p_append.add_argument("id", help="Unique slug identifier (e.g. queue-lag-trap)")
    p_append.add_argument("topic", help="Topic title")
    p_append.add_argument("stage", choices=ALLOWED_STAGES, help="Factory growth stage")
    p_append.add_argument("naive_assumption", help="The common naive intuition")
    p_append.add_argument("empirical_reality", help="What empirical telemetry proved")
    p_append.add_argument("mechanism", help="The structural fix or mechanism that solved it")
    p_append.add_argument("--author", default="",
                          help=f"the authoring lane, or the literal {OWNER_AUTHOR} for the "
                               f"owner's own insights. Omitted: DERIVED from "
                               f"OPENCRABS_SESSION_ID, and refused when it resolves to nothing")
    p_append.add_argument("--class", dest="insight_class", default="",
                          choices=ALLOWED_CLASSES,
                          help="the audience this entry serves: 'general' for publishable "
                               "content, 'implementation' for an internal HQ amendment. "
                               "Required.")
    p_append.add_argument("--status", default="pending", choices=ALLOWED_STATUSES,
                          help="where the entry stands in the workflow. Omitted: opens at "
                               "'pending', which asserts the row's own state and never "
                               "guesses the owner's routing decision")
    p_append.add_argument("--tweet", default="", help="Draft tweet narrative hook")
    p_append.add_argument("--ru", default="", help="Russian summary for Miidas/Ru-speaking audience")
    p_append.add_argument("--reason", default="",
                          help="why the entry was not acted on. REQUIRED when --status is "
                               "'refused' or 'dropped' (law section 6 rules 4 and 6) and "
                               "refused when empty")
    p_append.add_argument("--supersedes", type=int, default=None, metavar="N",
                          help="the n of the row this one CORRECTS. Required when the id "
                               "already exists: a second row for one id is a revision, and "
                               "readers take the NEWEST governing row")

    sub.add_parser("list", help="List all insights")
    sub.add_parser("verify", help="Verify integrity of insights ledger")

    p_cls = sub.add_parser("classify",
                           help="Set the class on entries that predate the field")
    p_cls.add_argument("--file", required=True, metavar="MAPPING.json",
                       help="JSON object {id: class}, applied in ONE transaction")

    p_st = sub.add_parser("status",
                          help="Move existing entries to a new workflow status")
    p_st.add_argument("--file", required=True, metavar="MAPPING.json",
                      help="JSON object {id: status}, or {id: {\"status\": …, \"reason\": …}} "
                           "when a row moves to 'refused' or 'dropped' and owes its reason "
                           "in the same transaction. A move OUT of those statuses CLEARS "
                           "the reason, which is how the owner's override lands. Applied "
                           "in ONE transaction")

    p_rs = sub.add_parser("reason",
                          help="Set the reason on entries that already exist")
    p_rs.add_argument("--file", required=True, metavar="MAPPING.json",
                      help="JSON object {id: reason}. Sets the reason and NOTHING else — "
                           "re-stating the status would move status_at, and the instant is "
                           "the field's whole value. Lawful only on a 'refused' or "
                           "'dropped' row: a reason on a live row is grounds for a "
                           "decision the status says was never taken")

    p_fmt = sub.add_parser("format", help="Format insight for publishing")
    p_fmt.add_argument("id", help="Insight slug")
    p_fmt.add_argument("--format", choices=["tweet", "ru", "markdown"], default="markdown")

    args = parser.parse_args()

    if args.cmd == "append":
        author = (args.author or "").strip()
        if not author:
            author, why = resolve_author()
            if not author:
                print(f"FAIL: --author is required — {why}", file=sys.stderr)
                return 2
        try:
            entry = append_insight(
                slug=args.id,
                topic=args.topic,
                stage=args.stage,
                naive_assumption=args.naive_assumption,
                empirical_reality=args.empirical_reality,
                mechanism=args.mechanism,
                tweet_hook=args.tweet,
                ru_summary=args.ru,
                author=author,
                insight_class=args.insight_class,
                status=args.status,
                reason=args.reason,
                supersedes=args.supersedes,
            )
            print(f"appended insight #{entry['n']}: {entry['id']} [{entry['stage']}] "
                  f"by {entry['author']} [{entry['class']}] [{entry['status']}]")
            if entry.get("supersedes") is not None:
                print(f"  revises n={entry['supersedes']} — the newest governing row wins")
            return 0
        except ValueError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "verify":
        ok, errors = verify_insights()
        if not ok:
            print("FAIL: insights verification failed:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        print("insights ledger clean")
        return 0

    elif args.cmd == "list":
        if not INSIGHTS_PATH.is_file():
            print("no insights recorded yet")
            return 0
        entries = _read_entries()
        superseded_by = _superseded_by(entries)
        for d in entries:
            # A row predating the field prints `legacy` rather than a blank,
            # so "no author recorded" is never mistaken for an authored blank.
            mark = ""
            if d.get("supersedes") is not None:
                mark = f" [revises n={d['supersedes']}]"
            elif d["n"] in superseded_by:
                # NEVER SILENT: a value that quietly stopped applying is the failure the
                # supersession shape exists to prevent, so the row says so in place.
                mark = f" [superseded by n={superseded_by[d['n']]}]"
            print(f"#{d['n']} [{d['stage']}] [{d.get('class') or 'legacy'}] "
                  f"[{d.get('status') or 'unrouted'}] "
                  f"{d['id']} ({d.get('author') or 'legacy'}): {d['topic']}{mark}")
        return 0

    elif args.cmd == "format":
        if not INSIGHTS_PATH.is_file():
            print("no insights file", file=sys.stderr)
            return 1
        entries = _read_entries()
        # A reader takes the NEWEST governing row for the id, and every superseded row
        # prints beneath it with its own values and instant — so a corrected figure is
        # never silently replaced, it is visibly retired.
        matches = [e for e in entries if e.get("id") == args.id]
        if not matches:
            print(f"insight '{args.id}' not found", file=sys.stderr)
            return 1
        target = max(matches, key=lambda e: e["n"])
        superseded_by = _superseded_by(entries)
        retired = [e for e in matches if e["n"] != target["n"]]

        if args.format == "tweet":
            print(target.get("tweet_hook") or "No tweet draft recorded.")
        elif args.format == "ru":
            print(target.get("ru_summary") or "No Russian summary recorded.")
        else:
            print(f"## Insight #{target['n']}: {target['topic']} ({target['stage']})\n")
            print(f"**Author:** {target.get('author') or 'legacy — predates the field'}\n")
            print(f"**Class:** {target.get('class') or 'legacy — predates the field'}\n")
            since = f" (since {target['status_at']})" if target.get("status_at") else ""
            print(f"**Status:** {target.get('status') or 'unrouted'}{since}\n")
            if target.get("reason"):
                print(f"**Reason:** {target['reason']}\n")
            print(f"**Naive assumption:** {target['naive_assumption']}\n")
            print(f"**Empirical reality:** {target['empirical_reality']}\n")
            print(f"**Structural mechanism:** {target['mechanism']}\n")
            if target.get("tweet_hook"):
                print(f"**Tweet hook:**\n```\n{target['tweet_hook']}\n```\n")
            if target.get("ru_summary"):
                print(f"**Russian publication summary:**\n{target['ru_summary']}\n")
            # The supersession PRINTS. A reader takes the newest governing row, and the
            # rows it retired are shown with their own number, value and instant — so a
            # corrected figure is visibly retired rather than silently replaced, and a
            # reader can tell a correction from a row that always said this.
            if retired:
                print(f"**Superseded rows ({len(retired)})** — the row above governs; "
                      f"these are printed, never deleted:\n")
                for old in sorted(retired, key=lambda e: e["n"]):
                    print(f"- n={old['n']} ({old.get('ts') or 'no ts'}) — "
                          f"*{old['empirical_reality']}*")
                print("")
            if target["n"] in superseded_by:
                print(f"**Superseded by n={superseded_by[target['n']]}** — this row no "
                      f"longer governs.\n")
        return 0

    elif args.cmd == "classify":
        try:
            mapping = json.loads(Path(args.file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL: cannot read mapping {args.file}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(mapping, dict):
            print("FAIL: the mapping must be a JSON object {id: class}", file=sys.stderr)
            return 1
        try:
            changes = classify_insights({str(k): str(v) for k, v in mapping.items()})
        except ValueError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        counts: dict[str, int] = {}
        for slug, old, new in changes:
            print(f"  {slug}: {old or 'legacy'} -> {new}")
            counts[new] = counts.get(new, 0) + 1
        summary = ", ".join(f"{n} {cls}" for cls, n in sorted(counts.items()))
        print(f"classified {len(changes)} entr{'y' if len(changes) == 1 else 'ies'}: {summary}")
        return 0

    elif args.cmd == "status":
        try:
            mapping = json.loads(Path(args.file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL: cannot read mapping {args.file}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(mapping, dict):
            print("FAIL: the mapping must be a JSON object {id: status}", file=sys.stderr)
            return 1

        # A value may be the status alone, or an object naming the reason too — a row
        # moved to `dropped` owes one, and both must travel in ONE transaction or the
        # register passes through a state insights.md §6 rule 4 forbids.
        normalized: dict[str, object] = {}
        for k, v in mapping.items():
            if isinstance(v, dict):
                normalized[str(k)] = {str(a): b for a, b in v.items()}
            else:
                normalized[str(k)] = str(v)

        try:
            changes = set_statuses(normalized)
        except ValueError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        counts: dict[str, int] = {}
        for slug, old, new in changes:
            print(f"  {slug}: {old or 'unrouted'} -> {new}")
            counts[new] = counts.get(new, 0) + 1
        summary = ", ".join(f"{n} {st}" for st, n in sorted(counts.items()))
        print(f"set status on {len(changes)} entr{'y' if len(changes) == 1 else 'ies'}: {summary}")
        return 0

    elif args.cmd == "reason":
        try:
            mapping = json.loads(Path(args.file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL: cannot read mapping {args.file}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(mapping, dict):
            print("FAIL: the mapping must be a JSON object {id: reason}", file=sys.stderr)
            return 1
        try:
            changes = set_reasons({str(k): str(v) for k, v in mapping.items()})
        except ValueError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        for slug, old, new in changes:
            print(f"  {slug}: {old or 'no reason'} -> {new}")
        print(f"set reason on {len(changes)} entr{'y' if len(changes) == 1 else 'ies'}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
