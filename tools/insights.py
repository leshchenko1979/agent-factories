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
  dropped     terminal: deliberately not acted on

Unlike `--class`, status is NOT demanded at the append. Class is a property of the
CLAIM, which the author is the one who knows; status is a property of the WORKFLOW,
whose destination is the owner's routing call. A new entry therefore OPENS at
`pending` — an assertion about the row's own state, never a guess at someone else's
decision.

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
ALLOWED_STATUSES = ["pending", "publishing", "hq", "published", "landed", "dropped"]

# The owner is an AUTHOR no session can stand for, so this literal is accepted
# as a first-class value and is NEVER derived.
OWNER_AUTHOR = "Alexey"

# The canonical key order. A field ADDED to an existing row is INSERTED at its
# position here, and every other key keeps the place it already had — so the diff
# a backfill produces is ADDITIVE: a reader scanning it meets one inserted label
# and no restated claim.
CANONICAL_ORDER = ["n", "id", "ts", "author", "class", "status", "status_at",
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
    mislabel itself here either. Two sources, in order:

    1. the fleet registry's DECLARED lanes — a factory fragment names its topics,
       so the answer is canonical, reviewed, and versioned in the repo;
    2. the session's own BINDING TITLE — the daemon records the chat and topic
       name there, and that is the only source for a topic no fragment declares.

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
                if resolved.get("session_id") == sid and lane.get("topic"):
                    return str(lane["topic"]), ""
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

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            entries = []
            if INSIGHTS_PATH.is_file():
                for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        entries.append(json.loads(line))

            # Check duplicate slug
            for e in entries:
                if e.get("id") == slug:
                    raise ValueError(f"insight with id '{slug}' already exists")

            next_n = len(entries) + 1
            entry = {
                "n": next_n,
                "id": slug,
                "ts": now_iso(),
                "author": str(author).strip(),
                "class": str(insight_class).strip(),
                "status": str(status).strip(),
                "status_at": now_iso(),
                "topic": topic,
                "stage": stage,
                "naive_assumption": naive_assumption,
                "empirical_reality": empirical_reality,
                "mechanism": mechanism,
                "tweet_hook": tweet_hook,
                "ru_summary": ru_summary,
            }

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


def _backfill(updates: dict[str, dict], fields: list[str], noun: str) -> list[tuple[str, dict]]:
    """Set the labelled `fields` on entries that ALREADY EXIST, in one transaction.

    Shared by `classify` and `status`: both write a routing label onto existing rows,
    so both owe the same guarantees, and a second copy of this logic would be a second
    place for those guarantees to drift apart.

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
    if not updates:
        raise ValueError(f"no {noun} given — pass an {{id: value}} mapping")
    for slug, value in updates.items():
        if not isinstance(value, dict):
            raise ValueError(f"{noun} for '{slug}' must be an object, got "
                             f"{type(value).__name__}")
        extra = sorted(set(value) - set(fields))
        if extra:
            raise ValueError(f"{noun} for '{slug}' carries unsettable field(s): "
                             f"{', '.join(extra)}")
        for name in fields:
            if name not in value:
                raise ValueError(f"{noun} for '{slug}' names no '{name}'")
            if name in FIELD_VOCAB and value[name] not in FIELD_VOCAB[name]:
                raise ValueError(f"{name} for '{slug}' must be one of "
                                 f"{FIELD_VOCAB[name]}, got '{value[name]}'")

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


def set_statuses(mapping: dict[str, str]) -> list[tuple[str, str | None, str]]:
    """Move existing entries to a new workflow `status`, stamping the instant they moved.

    `status_at` travels WITH the status rather than beside it, because an undated routing
    register cannot answer the question it exists to answer — which items are still owed,
    and for how long. A status that has never been set reads as absent, not as blank, so
    `pending` and "no status recorded" stay distinguishable in the same way `author` and
    `class` kept their legacy rows distinguishable from empty ones.
    """
    stamp = now_iso()
    changes = _backfill({k: {"status": v, "status_at": stamp} for k, v in mapping.items()},
                        ["status", "status_at"], "statuses")
    return [(slug, before["status"] or None, mapping[slug]) for slug, before in changes]


def verify_insights() -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not INSIGHTS_PATH.is_file():
        return True, []

    lines = [l.strip() for l in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen_ids = set()
    expected_n = 1

    for idx, line in enumerate(lines, start=1):
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {idx}: invalid JSON: {exc}")
            continue

        n = data.get("n")
        if n != expected_n:
            errors.append(f"line {idx}: expected n={expected_n}, got n={n}")
        expected_n += 1

        slug = data.get("id")
        if not slug:
            errors.append(f"line {idx}: missing id")
        elif slug in seen_ids:
            errors.append(f"line {idx}: duplicate id '{slug}'")
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

    sub.add_parser("list", help="List all insights")
    sub.add_parser("verify", help="Verify integrity of insights ledger")

    p_cls = sub.add_parser("classify",
                           help="Set the class on entries that predate the field")
    p_cls.add_argument("--file", required=True, metavar="MAPPING.json",
                       help="JSON object {id: class}, applied in ONE transaction")

    p_st = sub.add_parser("status",
                          help="Move existing entries to a new workflow status")
    p_st.add_argument("--file", required=True, metavar="MAPPING.json",
                      help="JSON object {id: status}, applied in ONE transaction")

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
            )
            print(f"appended insight #{entry['n']}: {entry['id']} [{entry['stage']}] "
                  f"by {entry['author']} [{entry['class']}] [{entry['status']}]")
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
        for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                # A row predating the field prints `legacy` rather than a blank,
                # so "no author recorded" is never mistaken for an authored blank.
                print(f"#{d['n']} [{d['stage']}] [{d.get('class') or 'legacy'}] "
                      f"[{d.get('status') or 'unrouted'}] "
                      f"{d['id']} ({d.get('author') or 'legacy'}): {d['topic']}")
        return 0

    elif args.cmd == "format":
        if not INSIGHTS_PATH.is_file():
            print("no insights file", file=sys.stderr)
            return 1
        target = None
        for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("id") == args.id:
                    target = d
                    break
        if not target:
            print(f"insight '{args.id}' not found", file=sys.stderr)
            return 1

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
            print(f"**Naive assumption:** {target['naive_assumption']}\n")
            print(f"**Empirical reality:** {target['empirical_reality']}\n")
            print(f"**Structural mechanism:** {target['mechanism']}\n")
            if target.get("tweet_hook"):
                print(f"**Tweet hook:**\n```\n{target['tweet_hook']}\n```\n")
            if target.get("ru_summary"):
                print(f"**Russian publication summary:**\n{target['ru_summary']}\n")
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

        try:
            changes = set_statuses({str(k): str(v) for k, v in mapping.items()})
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
