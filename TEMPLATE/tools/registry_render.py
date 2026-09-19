#!/usr/bin/env python3
"""Render the factory registry: one human document, one machine index.

`tools/registry.py` owns the SCHEMA and the LIVE READS; this module owns the
RENDER. They are split because they have different failure modes — a schema bug
rejects a good fragment, a render bug publishes a wrong one — and because the
renderer is the only place where two fragments' answers meet, which is where the
dedupe and contradiction rules live.

Both outputs are GENERATED and must never be hand-edited: the drift gate
re-renders and compares. Every claim about live state in them carries the instant
it was read (`resolved_at`), because a claim that describes live state without
naming the instant cannot be re-checked — the same rule that governs a patrol's
board claim (SKILL.md §11, commit 1491b81).

Announcements are ONE source rendered in TWO places, never duplicated:
  * a profile-wide block near the top, deduplicated by `id` across fragments —
    six lanes noticing one box-wide fact is one statement with six declarers,
    not six rows
  * inside each factory's section, the root entries whose `affects` names that
    factory or `profile`, plus each `scope: lane` entry on its own lane's row

Run:  python3 tools/registry.py render
Exit: 0 rendered, 1 nothing to render or a fragment failed to load.
"""

from __future__ import annotations

import datetime
import html
import json
import sqlite3
from pathlib import Path

# The bare local import is the repo's convention for a sibling tool module
# (`ledger.py` -> `ledger_declaration.py`): the tool runs as
# `python3 tools/registry.py`, so `tools/` is already on the path.
from registry import (
    CHECKS,
    FACTORY_CHATS,
    NAME_PREFIXES as REGISTRY_NAME_PREFIXES,
    REPO_ROOT,
    SEVERITIES,
    FleetManifestError,
    all_bindings,
    live_fragment_paths,
    load_fragment,
    profile_dbs,
    read_skill_version,
    resolve_lane,
)

# --- Freshness windows -----------------------------------------------------
#
# The re-attest pacemaker runs DAILY (SKILL.md §3), so a fragment older than a
# small multiple of that cadence is a PROCESS failure — nobody answered — while
# a moved binding is a STATE failure that a re-render fixes. The two are
# rendered separately so a reader is never sent to repair the wrong half.
ATTEST_CADENCE_HOURS = 24
ATTEST_STALE_MULTIPLE = 3
ATTEST_STALE_HOURS = ATTEST_CADENCE_HOURS * ATTEST_STALE_MULTIPLE

# The gate compares state-bearing bytes with the timestamp normalized on both
# sides, so a fresh render is never read as drift. The sentinel is declared here
# rather than in the gate so the two cannot disagree about what "normalized"
# means.
RESOLVED_SENTINEL = "1970-01-01T00:00:00Z"

SEVERITY_MARK = {"critical": "🔴", "warning": "🟡", "info": "🔵"}

# The validator declares severities in ASCENDING scale order (info first) because
# that is how a scale is written down; a reader wants the loudest first. These two
# are DERIVED from the validator's own tuple rather than restated as a second
# literal, so a severity added in one place cannot silently sort last in the other
# — which is exactly what happened when the sort reused the validator's map and
# put every `critical` notice at the bottom of the fleet's shared announcement list.
SEVERITY_RANK = {name: index for index, name in enumerate(reversed(SEVERITIES))}
SEVERITY_DISPLAY_ORDER = tuple(reversed(SEVERITIES))

# A job with no `deliver_to` (or one naming no known lane) is attributed by its
# name. The prefixes are the fleet's naming law made mechanical — every job on
# this box is `<factory>-<what-it-does>` — and the render STATES which basis it
# used, because a name is a label and not an identity field.
#
# The prefixes are IMPORTED, not restated: they are declared per factory in
# `registry/fleet.json` and derived once in `registry.py`. A second copy here was
# the defect this module's own docstring warns about — two declared surfaces that
# can disagree, with the renderer's copy silently winning every attribution.
NAME_PREFIXES = REGISTRY_NAME_PREFIXES

CRON_COLUMNS = (
    "id",
    "name",
    "cron_expr",
    "timezone",
    "prompt",
    "deliver_to",
    "enabled",
    "set_goal",
    "goal_template",
    "next_run_at",
    "last_run_at",
    "trigger_cmd",
)


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(value: object) -> datetime.datetime | None:
    """An ISO-8601 instant, or None. Never a default — absence is unknown."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def age_hours(value: object, now: datetime.datetime) -> float | None:
    parsed = parse_instant(value)
    if parsed is None:
        return None
    return (now - parsed).total_seconds() / 3600.0


def cell(value: object) -> str:
    """One markdown table cell: pipes escaped, newlines folded."""
    if value is None:
        return "—"
    text = str(value).strip()
    if not text:
        return "—"
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


TRIGGER_CMD_LIMIT = 72


def short_cmd(value: object, limit: int = TRIGGER_CMD_LIMIT) -> str:
    """A `trigger_cmd`, folded to one line and truncated for a table cell.

    These are shell scripts — one live row carries a four-line program with
    pipes in it — and a cell holding all of it makes the whole table unreadable
    and the row's other columns impossible to compare. The full value is carried
    in `registry/index.json`, which is the machine surface; the document shows a
    summary and SAYS that it is one.
    """
    if value is None or not str(value).strip():
        return "—"
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return cell(text)
    return cell(text[: limit - 1].rstrip() + "…")


def title_text(value: object) -> str:
    """A lane/session title, decoded back out of Telegram's HTML escaping.

    Titles are stored HTML-escaped (`&amp;` for `&`), which is correct for the
    Bot API payload and wrong for a markdown document. Decoding happens here and
    only here, so the raw value stays untouched everywhere else — this is a
    display normalization of a known escaping layer, not a rewrite of state.
    """
    if value is None:
        return "—"
    text = html.unescape(str(value)).strip()
    return cell(text) if text else "—"


# ---------------------------------------------------------------------------
# Announcements — the peer-facing field, merged across fragments
# ---------------------------------------------------------------------------

def collect_announcements(fragments: list[dict]) -> tuple[list[dict], list[str]]:
    """Merge every fragment's announcements into one deduplicated list.

    Dedupe is by `id` and the merge keeps EVERY origin. Two entries sharing an
    `id` with DIFFERING `text` are a contradiction two lanes publish under one
    name: the render keeps the first text and marks the conflict visibly rather
    than letting one of them read as authoritative — the gate fails the build on
    the same input, and a render that hid it would be worse than either.
    """
    merged: dict[str, dict] = {}
    problems: list[str] = []
    for fragment in fragments:
        slug = str(fragment.get("factory") or "?")
        sites: list[tuple[dict, dict | None]] = []
        for entry in fragment.get("announcements") or []:
            if isinstance(entry, dict):
                sites.append((entry, None))
        for lane in fragment.get("lanes") or []:
            if not isinstance(lane, dict):
                continue
            for entry in lane.get("announcements") or []:
                if isinstance(entry, dict):
                    sites.append((entry, lane))
        for entry, lane in sites:
            ident = entry.get("id")
            if not isinstance(ident, str) or not ident:
                continue
            record = merged.get(ident)
            if record is None:
                record = {
                    "id": ident,
                    "text": entry.get("text"),
                    "severity": entry.get("severity"),
                    "since": entry.get("since"),
                    "review_by": entry.get("review_by"),
                    "evidence": entry.get("evidence"),
                    "check": entry.get("check"),
                    "scope": entry.get("scope"),
                    "origins": [],
                    "affects": [],
                    "lanes": [],
                    "conflict": [],
                }
                merged[ident] = record
            elif entry.get("text") != record["text"]:
                record["conflict"].append(f"{slug}: {entry.get('text')!r}")
                problems.append(
                    f"announcement `{ident}` carries two different texts — "
                    f"declared by {', '.join(record['origins']) or '?'} and {slug}"
                )
            if slug not in record["origins"]:
                record["origins"].append(slug)
            for affected in entry.get("affects") or []:
                if affected not in record["affects"]:
                    record["affects"].append(affected)
            if lane is not None:
                record["lanes"].append(f"{slug}/{lane.get('topic')}")
    ordered = sorted(
        merged.values(),
        key=lambda r: (
            SEVERITY_RANK.get(str(r.get("severity")), len(SEVERITY_RANK)),
            _descending_since(r.get("since")),
            str(r["id"]),
        ),
    )
    return ordered, problems


def _descending_since(value: object) -> tuple[int, float]:
    """Sort key placing the most recent `since` first inside a severity band.

    A missing or unparseable date sorts last rather than crashing the render:
    the validator owns that error, and a renderer that dies on bad input hides
    every good entry behind it.
    """
    parsed = parse_instant(value)
    if parsed is None:
        return (1, 0.0)
    return (0, -parsed.timestamp())


def run_check(name: object, cache: dict) -> tuple[bool | None, str]:
    """Run one allowlisted predicate, once per render.

    The cache matters: `cron_min_gap_ge_6h` opens every OpenCrabs home's database
    — the box-wide read #102 widened it to — and `daemon_cgroup_cap_present`
    shells out to systemd, so six announcements citing one predicate must not run
    it six times on a box whose daemons live under a 768 MiB cgroup cap.
    """
    if not isinstance(name, str) or not name:
        return None, "no check declared"
    if name not in CHECKS:
        return None, f"unknown predicate `{name}`"
    if name not in cache:
        try:
            cache[name] = CHECKS[name]()
        except Exception as exc:  # a predicate must never take the render down
            cache[name] = (False, f"{type(exc).__name__}: {exc}")
    holds, evidence = cache[name]
    return bool(holds), str(evidence)


# ---------------------------------------------------------------------------
# Pacemakers — each job's LIVE row, never a projection of it
# ---------------------------------------------------------------------------
#
# Rendering `set_goal` alone shows a healthy-looking flag on the one row that
# actually bites: `set_goal=1` WITH a `goal_template` is a configured
# convergence, while `set_goal=1` WITHOUT one falls back to the prompt prose as
# the goal text, which declares no criteria and auto-pauses the session after
# three NO_EVIDENCE runs (fork #299/#364). The pair carries the meaning, so the
# pair is what renders.

def cron_rows() -> tuple[list[dict], list[str], list[str]]:
    """Every cron row in the DECLARED PROFILES, read in place from each profile's DB.

    The population is the declared profile root, NOT the box, and the section that
    prints these rows states it: the rows are attributed against the factories one
    manifest declares, so a home outside that root is outside this reader and its
    jobs are not counted here. The box-wide floor law reads through
    `registry.opencrabs_home_dbs` instead, which is the population its own claim
    names — a reader and the claim made over it are one decision, not two (#102).

    An undeclared `profile_root` is reported as an ERROR rather than yielding no
    rows: the renderer would otherwise publish a fleet with zero jobs, which
    reads as a clean box rather than as an unread one.

    Returns `(rows, errors, homes)` — `homes` is the population the read actually
    covered, so the render can NAME it instead of asserting a scope it never read.
    """
    rows: list[dict] = []
    errors: list[str] = []
    homes: list[str] = []
    try:
        dbs = profile_dbs()
    except FleetManifestError as exc:
        return [], [str(exc)], []
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error as exc:
            errors.append(f"{db}: {exc}")
            continue
        homes.append(db.parent.name)
        try:
            available = {r[1] for r in conn.execute("PRAGMA table_info(cron_jobs)")}
            if not available:
                continue  # a profile with no cron table is not an error
            columns = [c for c in CRON_COLUMNS if c in available]
            sql = f"select {', '.join(columns)} from cron_jobs order by name"
            for raw in conn.execute(sql):
                row = dict(zip(columns, raw))
                row["_profile"] = db.parent.name
                rows.append(row)
        except sqlite3.Error as exc:
            errors.append(f"{db}: {exc}")
        finally:
            conn.close()
    return rows, errors, homes


def job_owner(job: dict, uuid_owner: dict, chat_owner: dict) -> tuple[str | None, str]:
    """Which factory a job belongs to, and the BASIS the answer rests on.

    The basis is returned rather than implied because a name is a label and not
    an identity field: `deliver_to` names a lane the registry resolved, while a
    name prefix is a naming convention that a peer may break tomorrow.
    """
    deliver = str(job.get("deliver_to") or "")
    if deliver.startswith("session:"):
        uuid = deliver.split(":", 1)[1].strip()
        owner = uuid_owner.get(uuid)
        if owner:
            return owner, "deliver_to -> lane"
    if deliver.startswith("telegram:"):
        parts = deliver.split(":")
        chat = parts[1] if len(parts) > 1 else ""
        owner = chat_owner.get(chat)
        if owner:
            return owner, "deliver_to -> chat"
    name = str(job.get("name") or "")
    for slug, prefixes in NAME_PREFIXES:
        if any(name.startswith(p) for p in prefixes):
            return slug, "name prefix"
    return None, "unattributed"


# ---------------------------------------------------------------------------
# Context — everything the two renderers read, assembled once
# ---------------------------------------------------------------------------

def build_context(
    fragment_paths: list[Path],
    bindings: list[dict],
    resolved_at: str,
) -> tuple[dict, list[str]]:
    """Assemble the render context. One pass, so both outputs agree.

    The two renderers MUST read the same context: a document and an index
    generated from two separate reads can disagree about which session owns a
    topic, and the machine form is the one a peer would act on.
    """
    fragments: list[dict] = []
    problems: list[str] = []
    for path in fragment_paths:
        data, error = load_fragment(path)
        if error:
            problems.append(error)
            continue
        if isinstance(data, dict):
            data["_path"] = str(path)
            fragments.append(data)
    fragments.sort(key=lambda f: str(f.get("factory")))

    # Which factory each live session belongs to, and which factory each chat
    # belongs to. The first is what makes a `deliver_to: session:<uuid>` job
    # attributable by IDENTITY rather than by the name someone typed.
    chat_owner = {str(chat): slug for slug, chat in FACTORY_CHATS.items()}
    uuid_owner: dict[str, str] = {}

    factories: list[dict] = []
    for fragment in fragments:
        slug = str(fragment.get("factory"))
        lanes = []
        for lane in fragment.get("lanes") or []:
            if not isinstance(lane, dict):
                continue
            resolved = resolve_lane(
                lane, bindings, {}, chat_id=FACTORY_CHATS.get(slug)
            )
            resolved["declared_announcements"] = [
                e for e in (lane.get("announcements") or []) if isinstance(e, dict)
            ]
            if resolved.get("session_id"):
                uuid_owner[str(resolved["session_id"])] = slug
            lanes.append(resolved)
        factories.append(
            {
                "fragment": fragment,
                "slug": slug,
                "lanes": lanes,
                "skill_version": read_skill_version(
                    Path(str(fragment.get("skill") or ""))
                ),
                "attested_at": fragment.get("attested_at"),
                "status": fragment.get("status"),
            }
        )

    announcements, conflicts = collect_announcements(fragments)
    problems.extend(conflicts)

    jobs, job_errors, job_homes = cron_rows()
    problems.extend(job_errors)
    for job in jobs:
        owner, basis = job_owner(job, uuid_owner, chat_owner)
        job["_owner"] = owner
        job["_basis"] = basis

    return (
        {
            "resolved_at": resolved_at,
            "factories": factories,
            "announcements": announcements,
            "jobs": jobs,
            "job_homes": job_homes,
            "problems": problems,
        },
        problems,
    )


def _fragment_root_announcements(fragment: dict, slug: str) -> list[dict]:
    """Root notices that name this factory or the profile."""
    out = []
    for entry in fragment.get("announcements") or []:
        if not isinstance(entry, dict):
            continue
        affects = entry.get("affects") or []
        if "profile" in affects or slug in affects:
            out.append(entry)
    return out


def _announcement_line(entry: dict, check_cache: dict, indent: str = "") -> list[str]:
    """One announcement, rendered identically wherever it appears."""
    mark = SEVERITY_MARK.get(str(entry.get("severity")), "•")
    lines = [f"{indent}- {mark} **`{entry.get('id')}`** — {entry.get('text')}"]
    meta = [
        f"affects: {', '.join(entry.get('affects') or []) or '—'}",
        f"since: {entry.get('since') or '—'}",
    ]
    if entry.get("review_by"):
        due = ""
        review = parse_instant(entry.get("review_by"))
        if review is not None and review < datetime.datetime.now(datetime.timezone.utc):
            due = " ⚠️ REVIEW DUE"
        meta.append(f"review by: {entry['review_by']}{due}")
    if entry.get("origins"):
        meta.append(f"declared by: {', '.join(entry['origins'])}")
    if entry.get("lanes"):
        meta.append(f"lane: {', '.join(entry['lanes'])}")
    lines.append(f"{indent}  - {' · '.join(meta)}")
    check = entry.get("check")
    if check:
        holds, evidence = run_check(check, check_cache)
        verdict = (
            "✅ HOLDS"
            if holds
            else ("⚠️ NO LONGER HOLDS" if holds is False else "⛔ NOT CHECKED")
        )
        lines.append(f"{indent}  - check: `{check}` -> {verdict} — {evidence}")
    if entry.get("conflict"):
        lines.append(
            f"{indent}  - ⛔ CONFLICTING TEXT under one id, also declared as: "
            f"{'; '.join(entry['conflict'])}"
        )
    if entry.get("evidence") and str(entry.get("severity")) not in ("warning", "critical"):
        lines.append(f"{indent}  - evidence: {entry['evidence']}")
    return lines


def _freshness_badge(status: object, attested_at: object, now: datetime.datetime) -> str:
    """The declared half's freshness, rendered — never hidden, never gated."""
    if str(status) != "attested":
        return "⛔ INCOMPLETE — no declared half yet"
    hours = age_hours(attested_at, now)
    if hours is None:
        return "⛔ INCOMPLETE — attested with no readable `attested_at`"
    if hours > ATTEST_STALE_HOURS:
        return f"⚠️ STALE — last attested {attested_at}"
    return f"✅ attested {attested_at}"


def _pacemaker_table(jobs: list[dict], basis_filter=None) -> list[str]:
    """Every job's LIVE row. `set_goal` renders BESIDE `goal_template`, never alone."""
    lines = [
        "| job | cron_expr | timezone | enabled | set_goal | goal_template | "
        "next_run_at | deliver_to | trigger_cmd |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for job in jobs:
        if basis_filter is not None and job.get("_basis") not in basis_filter:
            continue
        template = job.get("goal_template")
        lines.append(
            "| `{}` | `{}` | {} | {} | {} | {} | {} | {} | {} |".format(
                cell(job.get("name")),
                cell(job.get("cron_expr")),
                cell(job.get("timezone")),
                "yes" if job.get("enabled") else "**no**",
                cell(job.get("set_goal")),
                ("present" if template else "**absent**"),
                cell(job.get("next_run_at")),
                cell(job.get("deliver_to")),
                short_cmd(job.get("trigger_cmd")),
            )
        )
    return lines


def render_markdown(ctx: dict) -> str:
    """The document. Generated — the gate re-renders and compares it."""
    now = parse_instant(ctx["resolved_at"]) or datetime.datetime.now(
        datetime.timezone.utc
    )
    out: list[str] = []
    factories = ctx["factories"]
    attested = sum(1 for f in factories if str(f["status"]) == "attested")
    checks = ctx.setdefault("_check_cache", {})

    out.append("# Fleet Factory Registry")
    out.append("")
    out.append(
        "**Generated** by `tools/registry.py render` — never hand-edited; the drift "
        "gate re-renders and compares the state-bearing bytes."
    )
    out.append("")
    out.append(
        f"**resolved at** `{ctx['resolved_at']}` — every binding, lane and job row "
        "below was read at that instant. The declared half ages on its own clock: a "
        "moved binding is a state change (re-rendering fixes it), while an old "
        "attestation is a process failure (re-rendering fixes nothing)."
    )
    out.append("")

    out.append("## Freshness")
    out.append("")
    out.append("| Half | Source | State |")
    out.append("|---|---|---|")
    out.append(
        f"| declared | {len(factories)} fragment(s) | {attested} attested, "
        f"{len(factories) - attested} awaiting an answer |"
    )
    out.append(f"| generated | live reads | resolved `{ctx['resolved_at']}` |")
    out.append("")

    # --- Announcements -----------------------------------------------------
    out.append("## Announcements")
    out.append("")
    out.append(
        "Deduplicated by `id` across every fragment: several lanes noticing one fact "
        "is one statement with several declarers. An entry naming a `check` is "
        "mechanically verified; the rest rest on `review_by` alone."
    )
    out.append("")
    if not ctx["announcements"]:
        out.append("_None declared. Every field is a question until an HQ answers it._")
        out.append("")
    for severity in SEVERITY_DISPLAY_ORDER:
        band = [a for a in ctx["announcements"] if str(a.get("severity")) == severity]
        if not band:
            continue
        out.append(f"### {SEVERITY_MARK.get(severity, '•')} {severity} ({len(band)})")
        out.append("")
        for entry in band:
            out.extend(_announcement_line(entry, checks))
        out.append("")

    # --- Reachability ------------------------------------------------------
    out.append("## Reachability")
    out.append("")
    out.append("| Hop | Mechanism | State |")
    out.append("|---|---|---|")
    out.append("| lane -> lane, same factory | `session_notify` (UUID) | works |")
    out.append("| factory -> factory, same profile | `session_notify` (UUID) | works |")
    out.append(
        "| factory -> factory, other profile | "
        "`opencrabs -p <profile> session notify <uuid>` | works — the CLI posts over "
        "that profile's own A2A gateway, so it crosses a process boundary the "
        "in-session tool cannot |"
    )
    out.append(
        "| owner -> factory | Telegram topic | works — human surface only; agents do "
        "not read topics |"
    )
    out.append("")
    out.append(
        "CLI exit contract: `0` delivered/redirected/parked · `2` unknown or dead "
        "uuid · `4` **transport — a catch-all, not a diagnosis**. Exit `4` carries at "
        "least three causes: the A2A gateway being unreachable, `--mode now` being "
        "refused as retired, and pure **caller errors** — `--status` with no id, a "
        "missing `--text`, an empty `--text` — because there is no `EXIT_USAGE` "
        "constant for those to land in. So on rc 4 a caller **cannot tell a retryable "
        "infrastructure condition from a non-retryable caller bug**: read the reason "
        "string before retrying, and never treat rc 4 as a blanket retry. Exit `3` is "
        "retained as a constant but is **unreachable**: no CLI flag produces it, "
        "because a mid-turn target queues rather than refusing."
    )
    out.append("")
    out.append(
        "**Omit `--mode` entirely.** The flag's own help still reads "
        "`now (default)`, but the runtime's default is `turn-end` — verified by "
        "probe against a live target: no `--mode` at all → rc 0 `delivered`; "
        "`--mode turn-end` → rc 0 `delivered`; `--mode now` → rc 4 "
        "`delivery.mode 'now' is retired`. A route documented from the help text "
        "would hand the reader the one value that cannot work."
    )
    out.append("")

    # --- Factories ---------------------------------------------------------
    out.append("## Factories")
    out.append("")
    for entry in factories:
        fragment = entry["fragment"]
        slug = entry["slug"]
        out.append(f"### {slug} — {fragment.get('display_name') or slug}")
        out.append("")
        out.append("| Field | Value |")
        out.append("|---|---|")
        out.append(
            f"| freshness | {_freshness_badge(entry['status'], entry['attested_at'], now)} |"
        )
        out.append(f"| purpose | {cell(fragment.get('purpose'))} |")
        out.append(f"| profile | `{cell(fragment.get('profile'))}` |")
        out.append(f"| repo | `{cell(fragment.get('repo'))}` |")
        out.append(
            f"| law | `{cell(fragment.get('skill'))}` — revision "
            f"{cell(entry['skill_version'])} |"
        )
        zone = fragment.get("zone") or {}
        out.append(f"| owns | {cell(zone.get('owns'))} |")
        out.append(f"| does not own | {cell(zone.get('does_not_own'))} |")
        out.append(f"| substrates owned | {cell(fragment.get('substrates_owned'))} |")
        out.append(f"| attested at | {cell(fragment.get('attested_at'))} |")
        out.append("")

        services = fragment.get("services") or []
        out.append("**Services**")
        out.append("")
        if not services:
            out.append("_None declared._")
        else:
            out.append("| name | audience | entry | cadence |")
            out.append("|---|---|---|---|")
            for service in services:
                if not isinstance(service, dict):
                    continue
                out.append(
                    "| {} | {} | {} | {} |".format(
                        cell(service.get("name")),
                        cell(service.get("audience")),
                        cell(service.get("entry")),
                        cell(service.get("cadence")),
                    )
                )
        out.append("")

        root_notices = _fragment_root_announcements(fragment, slug)
        if root_notices:
            out.append("**Announcements reaching this factory**")
            out.append("")
            for notice in root_notices:
                merged = next(
                    (a for a in ctx["announcements"] if a["id"] == notice.get("id")),
                    None,
                )
                out.extend(_announcement_line(merged or notice, checks))
            out.append("")

        out.append("**Lanes**")
        out.append("")
        out.append(
            "| topic | thread | role | session | session title | status | "
            "channel | last active | lane announcements |"
        )
        out.append("|---|---|---|---|---|---|---|---|---|")
        for lane in entry["lanes"]:
            lane_notes = lane.get("declared_announcements") or []
            note_text = "; ".join(
                f"{SEVERITY_MARK.get(str(n.get('severity')), '•')} "
                f"**`{n.get('id')}`** — {n.get('text')}"
                + (f" (review by {n['review_by']})" if n.get("review_by") else "")
                for n in lane_notes
            )
            out.append(
                "| {} | {} | {} | `{}` | {} | {} | {} | {} | {} |".format(
                    title_text(lane.get("topic")),
                    cell(lane.get("thread_id")),
                    cell(lane.get("role")) if lane.get("role") else "_unstated_",
                    cell(lane.get("session_id")),
                    title_text(lane.get("session_title")),
                    cell(lane.get("status")),
                    cell(lane.get("channel")),
                    cell(lane.get("bound_at")),
                    note_text or "—",
                )
            )
        out.append("")

        factory_jobs = [j for j in ctx["jobs"] if j.get("_owner") == slug]
        out.append("**Pacemakers**")
        out.append("")
        if not factory_jobs:
            out.append("_No job attributed to this factory._")
        else:
            out.extend(_pacemaker_table(factory_jobs))
            bases = sorted({str(j.get("_basis")) for j in factory_jobs})
            out.append("")
            out.append(f"Attribution basis: {', '.join(bases)}.")
            if any(j.get("trigger_cmd") for j in factory_jobs):
                out.append(
                    f"`trigger_cmd` is truncated to {TRIGGER_CMD_LIMIT} characters "
                    "here; the full command is in `registry/index.json`."
                )
            no_target = sum(1 for j in factory_jobs if not j.get("deliver_to"))
            if no_target:
                out.append(
                    f"{no_target} of {len(factory_jobs)} job(s) carry no explicit "
                    "`deliver_to`. The column is rendered as the live row holds it; "
                    "whether a null falls back to the creating session or to nothing "
                    "is the scheduler's contract, and this registry does not assert it."
                )
        out.append("")

    # --- Unattributed jobs -------------------------------------------------
    orphans = [j for j in ctx["jobs"] if not j.get("_owner")]
    homes = ctx.get("job_homes") or []
    out.append("## Unattributed jobs")
    out.append("")
    # The population is STATED, never implied. The section's own claim used to read
    # "every cron row on the box" over a reader that reads the declared profiles,
    # which is the #102 shape: a claim wider than its reader. The reader keeps its
    # profile scope (attribution is against one manifest's factories), so the
    # sentence moves to match the reader instead.
    population = (
        f"Read from the declared profile homes: {len(homes)} home(s) opened, "
        f"{len(ctx['jobs'])} job row(s)."
    )
    if homes:
        population += f" Homes read: {', '.join(sorted(homes))}."
    out.append(population)
    out.append("")
    if not orphans:
        out.append("_Every cron row in that population is attributed to a factory._")
    else:
        out.append(
            "These rows name no known factory in their `deliver_to` and match no "
            "naming prefix. They are rendered rather than dropped: a job the "
            "registry cannot place is a finding, not an omission."
        )
        out.append("")
        out.extend(_pacemaker_table(orphans))
    out.append("")

    if ctx["problems"]:
        out.append("## Render warnings")
        out.append("")
        for problem in ctx["problems"]:
            out.append(f"- ⚠️ {problem}")
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        "Generated file. Edit `registry/factories/<slug>.json` instead, then re-render."
    )
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The machine index
# ---------------------------------------------------------------------------

INDEX_SCHEMA = "factory-registry/1"


def render_index(ctx: dict) -> dict:
    """The machine form: same context, no prose, no prompt bodies.

    `cron_jobs.prompt` is dropped on purpose. It is the largest field on the row
    and the least machine-readable — a peer reading this index needs the
    SCHEDULE, the delivery target and the goal contract, not the prose that
    wakes the lane. Keeping it would multiply the artifact's size on a box whose
    daemons live under a 768 MiB cgroup cap.
    """
    factories = []
    for entry in ctx["factories"]:
        fragment = entry["fragment"]
        factories.append(
            {
                "factory": entry["slug"],
                "display_name": fragment.get("display_name"),
                "status": fragment.get("status"),
                "attested_at": fragment.get("attested_at"),
                "profile": fragment.get("profile"),
                "repo": fragment.get("repo"),
                "skill": fragment.get("skill"),
                "skill_revision": entry["skill_version"],
                "purpose": fragment.get("purpose"),
                "zone": fragment.get("zone") or {},
                "substrates_owned": fragment.get("substrates_owned") or [],
                "services": fragment.get("services") or [],
                "lanes": [
                    {
                        "topic": lane.get("topic"),
                        "thread_id": lane.get("thread_id"),
                        "role": lane.get("role"),
                        "session_id": lane.get("session_id"),
                        "status": lane.get("status"),
                        "channel": lane.get("channel"),
                        "bound_at": lane.get("bound_at"),
                        "announcements": [
                            {
                                "id": n.get("id"),
                                "severity": n.get("severity"),
                                "text": n.get("text"),
                                "review_by": n.get("review_by"),
                            }
                            for n in (lane.get("declared_announcements") or [])
                        ],
                    }
                    for lane in entry["lanes"]
                ],
                "announcements": [
                    {
                        "id": n.get("id"),
                        "severity": n.get("severity"),
                        "text": n.get("text"),
                        "scope": n.get("scope"),
                        "since": n.get("since"),
                        "review_by": n.get("review_by"),
                        "check": n.get("check"),
                        "affects": n.get("affects") or [],
                        "evidence": n.get("evidence"),
                    }
                    for n in (fragment.get("announcements") or [])
                    if isinstance(n, dict)
                ],
            }
        )

    jobs = []
    for job in ctx["jobs"]:
        jobs.append(
            {
                "id": job.get("id"),
                "name": job.get("name"),
                "cron_expr": job.get("cron_expr"),
                "timezone": job.get("timezone"),
                "enabled": job.get("enabled"),
                "set_goal": job.get("set_goal"),
                "has_goal_template": bool(job.get("goal_template")),
                "next_run_at": job.get("next_run_at"),
                "last_run_at": job.get("last_run_at"),
                "deliver_to": job.get("deliver_to"),
                "trigger_cmd": job.get("trigger_cmd"),
                "profile": job.get("_profile"),
                "owner": job.get("_owner"),
                "owner_basis": job.get("_basis"),
            }
        )
    jobs.sort(key=lambda j: (str(j.get("owner") or "~"), str(j.get("name"))))

    return {
        "schema": INDEX_SCHEMA,
        "generated_by": "tools/registry.py render",
        "resolved_at": ctx["resolved_at"],
        "counts": {
            "factories": len(factories),
            "attested": sum(1 for f in factories if f.get("status") == "attested"),
            "lanes": sum(len(f["lanes"]) for f in factories),
            "announcements": len(ctx["announcements"]),
            "jobs": len(jobs),
            "unattributed_jobs": sum(1 for j in jobs if not j.get("owner")),
        },
        "announcements": [
            {
                "id": a.get("id"),
                "severity": a.get("severity"),
                "scope": a.get("scope"),
                "text": a.get("text"),
                "since": a.get("since"),
                "review_by": a.get("review_by"),
                "check": a.get("check"),
                "evidence": a.get("evidence"),
                "affects": a.get("affects") or [],
                "origins": a.get("origins") or [],
                "conflict": a.get("conflict") or [],
            }
            for a in ctx["announcements"]
        ],
        "factories": factories,
        "jobs": jobs,
        "problems": ctx["problems"],
    }


# ---------------------------------------------------------------------------
# Entry point used by `registry.py render` and by the drift gate
# ---------------------------------------------------------------------------

MD_PATH = REPO_ROOT / "docs" / "factory-registry.md"
INDEX_PATH = REPO_ROOT / "registry" / "index.json"


def render_texts(
    explicit: list[str] | None = None,
    resolved_at: str | None = None,
) -> tuple[str, str, dict]:
    """Render both artifacts to STRINGS, writing nothing.

    The gate uses this: it re-renders and compares bytes, and a renderer that
    could only write to disk would force the gate to write before it could
    compare — mutating the artifact it is judging.
    """
    stamp = resolved_at or utc_now()
    paths = live_fragment_paths(explicit or [])
    bindings, binding_errors = all_bindings()
    ctx, problems = build_context(paths, bindings, stamp)
    for error in binding_errors:
        if error not in problems:
            problems.append(error)
            ctx["problems"].append(error)
    markdown = render_markdown(ctx)
    index = render_index(ctx)
    return markdown, json.dumps(index, indent=2, ensure_ascii=False) + "\n", ctx


def render_all(
    explicit: list[str] | None = None,
    resolved_at: str | None = None,
    write: bool = True,
) -> tuple[int, dict]:
    """Render both artifacts. Returns (exit code, report).

    Exit `1` with NO write when the live store holds no fragment: rendering an
    empty registry would publish "no factories" as a fact, and the registry's
    whole purpose is that absence reads as a question, not as an answer.
    """
    paths = live_fragment_paths(explicit or [])
    if not paths:
        return 1, {
            "error": "no fragments in registry/factories/ — run `enroll --all` first",
            "paths": [],
        }
    markdown, index_text, ctx = render_texts(explicit, resolved_at)
    report = {
        "resolved_at": ctx["resolved_at"],
        "fragments": len(paths),
        "factories": len(ctx["factories"]),
        "lanes": sum(len(f["lanes"]) for f in ctx["factories"]),
        "announcements": len(ctx["announcements"]),
        "jobs": len(ctx["jobs"]),
        "unattributed_jobs": sum(1 for j in ctx["jobs"] if not j.get("_owner")),
        "problems": ctx["problems"],
        "markdown": str(MD_PATH),
        "index": str(INDEX_PATH),
    }
    if write:
        MD_PATH.parent.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        MD_PATH.write_text(markdown, encoding="utf-8")
        INDEX_PATH.write_text(index_text, encoding="utf-8")
        report["markdown_bytes"] = MD_PATH.stat().st_size
        report["index_bytes"] = INDEX_PATH.stat().st_size
    return 0, report
