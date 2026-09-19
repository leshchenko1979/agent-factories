#!/usr/bin/env python3
"""The factory registry — a factory's self-description, and who can reach it.

Six factories share this box and none of them can say, in one place, what the
others do, who to talk to, or which of them owns a given substrate. This tool
builds that surface from two halves, and the split between them is the whole
design:

  DECLARED  one JSON fragment per factory, written by THAT factory's HQ and by
            nobody else. Purpose, zone, services, announcements.
  DERIVED   read live from `session_bindings` + `sessions` + the Telegram
            surface: lane UUIDs, topic names, reachability. Never hand-typed,
            because a hand-typed UUID is stale the moment a topic rebinds.

**Declared, not derived** is a rule about the DERIVED half, not a preference.
A generator can only see what EXISTS, while the property under test is often
that something is OWED — so a field pulled from the tree returns the empty set
precisely for the factory that has not yet created the thing it owes. The
registry therefore never infers a factory's purpose from its files; it asks, and
renders `unattested` until the answer comes back. (Origin: issue #79, ruled
2026-09-19 — the same reason a gate keyed on a repo's `skills/` directory passes
vacuously on the factory whose law has no load path.)

Commands
--------
  validate [PATH ...]   validate fragments (default: the fragment store, plus
                        the fixtures). Exit 1 on the first file that is invalid.
  resolve               (step 2) the live half, read through a mode=ro URI
  enroll --all          (step 3) scaffold one stub per factory
  render                (step 5) write docs/factory-registry.md + registry/index.json

Exit: 0 ok, 1 problem (invalid fragment, bad usage, unreadable store).

Why `check` is a NAME and never a command
-----------------------------------------
An announcement is written by a member lane and read by every other lane. A gate
that EXECUTES a shell string out of that file is an injection surface, and on
this box it is also an unbounded process budget under a 768 MiB cgroup cap. So
`check` names one of the predicates in `CHECKS` below; the validator rejects an
unknown name AND rejects anything command-shaped, so a typo'd predicate is a
build failure rather than an annotation nobody reads.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRAGMENT_STORE = REPO_ROOT / "registry" / "factories"
FIXTURE_STORE = REPO_ROOT / "tests" / "fixtures"

# ---------------------------------------------------------------------------
# The fleet manifest: the one DECLARED surface this tool reads.
#
# Everything below that names a factory — its slug, its chat, its repo, its law
# file, its display name, its aliases, its cron prefixes — is DATA, not code. It
# was six dicts and a frozenset until this section existed, and that shape had
# exactly one defect: it could not be a template artifact. A template that
# hardcodes `ai-antispam` ships one factory's fleet to every factory that copies
# it, and the copy is then wrong in a way no gate can see, because the gate reads
# the same hardcoded set it is checking.
#
# The split is the registry's own law applied to the registry: a generator can
# read what EXISTS (a live binding, a repo, a skill file), and it can read nothing
# about WHICH factories the box is meant to carry. That is a declaration, so it is
# declared — in `registry/fleet.json`, written by the factory's HQ, read here.
#
# **The names are kept.** `KNOWN_FACTORY_SLUGS`, `FACTORY_CHATS`, `FACTORY_REPOS`,
# `FACTORY_SKILLS`, `FACTORY_DISPLAY_NAMES`, `FACTORY_NAME_ALIASES` and
# `PROFILE_ROOT` are still module-level, so every call site and both sibling
# modules keep working unchanged; they are now DERIVED from the manifest rather
# than restated beside it. A second copy of a factory list is the defect, not the
# constant.
# ---------------------------------------------------------------------------

MANIFEST_PATH = REPO_ROOT / "registry" / "fleet.json"
MANIFEST_ENV = "OC_FLEET_MANIFEST"
# The keys a record must carry, and the type each one must have. A manifest that
# is missing a key is not a smaller fleet — it is an unanswered question, and it
# fails naming the record and the key rather than defaulting to something.
MANIFEST_RECORD_KEYS = (
    ("slug", str),
    ("display_name", str),
    ("chat_id", int),
    ("repo", str),
    ("skill", str),
    ("job_prefixes", list),
    ("aliases", list),
)


class FleetManifestError(Exception):
    """The fleet manifest is absent, unparseable, or incomplete."""


def manifest_path() -> Path:
    """Where the manifest is read from: the environment override, else the default.

    The override exists so a probe or a fixture can point the tool at a manifest
    it built, without writing into the live store — the same reason the fragment
    commands take explicit paths.
    """
    override = os.environ.get(MANIFEST_ENV)
    return Path(override) if override else MANIFEST_PATH


def load_fleet_manifest(path: Path | None = None) -> dict:
    """Read and validate the fleet manifest. Raises `FleetManifestError` on any defect.

    Every failure is named with the path and the reason, because the caller that
    most needs this message is a bootstrapped factory whose manifest was never
    written — and "no such file" alone does not tell it what to write.
    """
    target = path or manifest_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise FleetManifestError(
            f"{target}: cannot read the fleet manifest — {exc}. This file declares which "
            f"factories the registry covers; copy `registry/fleet.example.json` and fill "
            f"it in, or point {MANIFEST_ENV} at one."
        ) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FleetManifestError(f"{target}: does not parse as JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise FleetManifestError(f"{target}: the manifest must be a JSON object")
    for key in ("profile_root", "profile", "factories"):
        if key not in data:
            raise FleetManifestError(f"{target}: no `{key}` key")
    records = data["factories"]
    if not isinstance(records, list) or not records:
        raise FleetManifestError(
            f"{target}: `factories` must be a non-empty list — an empty manifest reads as "
            f"`no factory exists`, which is the declared-not-derived defect it exists to fix"
        )
    seen: set[str] = set()
    for index, record in enumerate(records):
        where = f"{target}: factories[{index}]"
        if not isinstance(record, dict):
            raise FleetManifestError(f"{where} is not an object")
        for key, kind in MANIFEST_RECORD_KEYS:
            if key not in record:
                raise FleetManifestError(f"{where} has no `{key}` key")
            value = record[key]
            # `bool` is a subclass of `int`, and a chat id of `true` is not a chat id.
            if kind is int and (isinstance(value, bool) or not isinstance(value, int)):
                raise FleetManifestError(f"{where}.{key} must be an integer, not {value!r}")
            if kind is not int and not isinstance(value, kind):
                raise FleetManifestError(
                    f"{where}.{key} must be a {kind.__name__}, not {value!r}"
                )
        slug = record["slug"]
        if slug in seen:
            raise FleetManifestError(f"{where}.slug `{slug}` is declared twice")
        seen.add(slug)
    return data


def _manifest_or_empty() -> tuple[dict, str | None]:
    """Load the manifest, and on failure return an empty one plus the reason.

    Module import must not raise: a gate that cannot import its own subject
    reports a traceback, which reads as a broken gate rather than as the missing
    declaration it is. So the failure is CARRIED and reported by the commands and
    by the gate, while the derived collections come back empty — and an empty
    `KNOWN_FACTORY_SLUGS` rejects every fragment loudly, which is the correct
    reading of "no factory is declared".
    """
    try:
        return load_fleet_manifest(), None
    except FleetManifestError as exc:
        return {"profile_root": "", "profile": "", "factories": []}, str(exc)


MANIFEST, MANIFEST_ERROR = _manifest_or_empty()
MANIFEST_RECORDS = {record["slug"]: record for record in MANIFEST["factories"]}

# A slug is what `affects` entries resolve against and what a fragment's `factory`
# field must name, so the set is the DECLARED set rather than a directory listing:
# an empty `registry/factories/` must not read as "no factory exists".
KNOWN_FACTORY_SLUGS = frozenset(MANIFEST_RECORDS)

PROFILE_SCOPE = "profile"  # the literal that `affects` uses for box-wide notices
# The profile field is a DIFFERENT question from the `affects` sentinel above: one
# is a scope keyword, the other is a profile NAME. Every factory on this box runs
# under `ops` (AGENTS.md §Session naming convention: no lane is prefixed "ops"
# because it distinguishes nothing), so the name is declared in the manifest.
FACTORY_PROFILE = MANIFEST["profile"]

FACTORY_CHATS = {slug: r["chat_id"] for slug, r in MANIFEST_RECORDS.items()}
FACTORY_REPOS = {slug: r["repo"] for slug, r in MANIFEST_RECORDS.items()}
FACTORY_SKILLS = {slug: r["skill"] for slug, r in MANIFEST_RECORDS.items()}
FACTORY_DISPLAY_NAMES = {slug: r["display_name"] for slug, r in MANIFEST_RECORDS.items()}
FACTORY_NAME_ALIASES = {slug: tuple(r["aliases"]) for slug, r in MANIFEST_RECORDS.items()}
# Ordered, and the order is the manifest's: the renderer resolves a job's owner by
# testing prefixes in turn, and `oc-` before `ocx-` is a real precedence.
NAME_PREFIXES = tuple(
    (slug, tuple(r["job_prefixes"])) for slug, r in MANIFEST_RECORDS.items()
)

SEVERITIES = ("info", "warning", "critical")
SEVERITY_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
SCOPES = ("profile", "factory", "lane")
# Which scope may be declared WHERE. A lane's entry conditions belong on the
# lane's row and mean nothing at the root; a profile-wide fact is not a lane's
# to declare. Encoding the pairing here is what keeps `scope` from degrading
# into free text that renders nowhere.
ROOT_SCOPES = ("profile", "factory")
LANE_SCOPES = ("lane",)
EVIDENCE_REQUIRED_SEVERITIES = ("warning", "critical")

FRAGMENT_KEYS = frozenset(
    {
        "factory",
        "display_name",
        "profile",
        "repo",
        "skill",
        "purpose",
        "zone",
        "services",
        "substrates_owned",
        "announcements",
        "lanes",
        "status",
        "attested_at",
    }
)
ZONE_KEYS = frozenset({"owns", "does_not_own"})
SERVICE_KEYS = frozenset({"name", "audience", "entry", "cadence"})
LANE_KEYS = frozenset({"topic", "thread_id", "role", "announcements"})
ANNOUNCEMENT_KEYS = frozenset(
    {"id", "scope", "severity", "text", "affects", "since", "review_by", "evidence", "check"}
)

# Keys whose PRESENCE is an error, not whose value is. A UUID is the one thing
# this schema exists to keep out: it is resolved live from `session_bindings`,
# so a declared one is stale on arrival and would be rendered as authoritative.
FORBIDDEN_KEYS = frozenset({"session_id", "uuid", "session"})

# Required at the root. Values may be null — an unattested field is `null`, and
# `null` is a statement ("nobody has told us"), while an ABSENT key is not: it is
# indistinguishable from a generator that forgot to write it. So the key set is
# fixed and the values carry the doubt.
#
# `zone` and `announcements` are deliberately NOT in this tuple: each has its own
# check below that says WHY it is required, and listing them here too reported a
# single missing key twice with two different wordings — a fault should have one
# reason, or the report teaches the reader to skim it.
REQUIRED_ROOT_KEYS = (
    "factory",
    "profile",
    "repo",
    "skill",
    "purpose",
    "services",
    "substrates_owned",
    "lanes",
    "status",
)

STATUSES = ("unattested", "attested")

# name -> implementation, declared ONCE so the validator and the renderer cannot
# disagree about which predicates exist. Populated below the validator.
CHECKS: dict = {}


def _iso_date(value: object) -> str | None:
    """Return an ISO-8601 date/datetime string, or None if it does not parse.

    `datetime.date.fromisoformat` accepts both `2026-09-19` and the full
    `2026-09-19T10:52:00Z` shape (from 3.11), which is what we want: a notice
    carries a date, an evidence line may carry an instant.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for parse in (datetime.datetime.fromisoformat, datetime.date.fromisoformat):
        try:
            parse(text)
            return value
        except ValueError:
            continue
    return None


def _is_command_shaped(text: str) -> bool:
    """True when a `check` value looks like a command rather than a name.

    Checked BEFORE the allowlist so the error message can say why: `check` is
    never executed, and a lane writing `test -x /usr/bin/sqlite3` there needs to
    be told that, not told "unknown predicate".
    """
    return bool(re.search(r"[\s/|;&$`(){}<>\n]", text))


def validate_announcements(
    entries: object,
    where: str,
    allowed_scopes: tuple[str, ...],
    errors: list[str],
) -> None:
    """Validate one announcement list. `where` names the declaration site."""
    if entries is None:
        return  # an unattested fragment declares no notices; that is not an error
    if not isinstance(entries, list):
        errors.append(f"{where}: announcements must be a list, got {type(entries).__name__}")
        return
    seen_ids: dict[str, int] = {}
    for i, entry in enumerate(entries):
        at = f"{where}: announcements[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{at}: must be an object")
            continue
        for key in sorted(FORBIDDEN_KEYS & set(entry)):
            errors.append(f"{at}: `{key}` is never declared — it is resolved live")
        for key in sorted(set(entry) - ANNOUNCEMENT_KEYS - FORBIDDEN_KEYS):
            errors.append(f"{at}: unknown key `{key}`")
        for key in ("id", "text", "severity", "since"):
            if key not in entry:
                errors.append(f"{at}: missing required key `{key}`")
        if entry.get("id") is not None:
            seen_ids.setdefault(str(entry["id"]), i)
        severity = entry.get("severity")
        if severity is not None and severity not in SEVERITIES:
            errors.append(
                f"{at}: severity `{severity}` is not one of {'|'.join(SEVERITIES)}"
            )
        scope = entry.get("scope")
        if scope is not None and scope not in SCOPES:
            errors.append(f"{at}: scope `{scope}` is not one of {'|'.join(SCOPES)}")
        elif scope is not None and scope not in allowed_scopes:
            errors.append(
                f"{at}: scope `{scope}` cannot be declared here — "
                f"{where} admits {'|'.join(allowed_scopes)}"
            )
        affects = entry.get("affects")
        if affects is None:
            errors.append(f"{at}: missing required key `affects`")
        elif not isinstance(affects, list) or not affects:
            errors.append(f"{at}: affects must be a non-empty list")
        else:
            for slug in affects:
                if not isinstance(slug, str):
                    errors.append(f"{at}: affects entries must be strings")
                elif slug != PROFILE_SCOPE and slug not in KNOWN_FACTORY_SLUGS:
                    errors.append(
                        f"{at}: affects names unknown factory `{slug}` "
                        f"(known: {', '.join(sorted(KNOWN_FACTORY_SLUGS))}, or `{PROFILE_SCOPE}`)"
                    )
        since = entry.get("since")
        review_by = entry.get("review_by")
        since_ok = _iso_date(since) if since is not None else None
        if since is not None and since_ok is None:
            errors.append(f"{at}: since `{since}` does not parse as ISO-8601")
        if review_by is not None:
            if _iso_date(review_by) is None:
                errors.append(f"{at}: review_by `{review_by}` does not parse as ISO-8601")
            elif since_ok is not None:
                try:
                    a = datetime.date.fromisoformat(str(since)[:10])
                    b = datetime.date.fromisoformat(str(review_by)[:10])
                    if b < a:
                        errors.append(
                            f"{at}: review_by `{review_by}` precedes since `{since}`"
                        )
                except ValueError:
                    pass
        if severity in EVIDENCE_REQUIRED_SEVERITIES and not entry.get("evidence"):
            errors.append(
                f"{at}: severity `{severity}` requires `evidence` — peers act on this"
            )
        check = entry.get("check")
        if check is not None:
            if not isinstance(check, str):
                errors.append(f"{at}: check must be a predicate name")
            elif _is_command_shaped(check):
                errors.append(
                    f"{at}: check `{check}` looks like a command — "
                    "check names a predicate, it is never executed"
                )
            elif check not in CHECKS:
                errors.append(
                    f"{at}: unknown check `{check}` "
                    f"(allowlist: {', '.join(sorted(CHECKS))})"
                )
    return None


def validate_fragment(data: object, path: str = "<memory>") -> list[str]:
    """Validate one fragment. Returns a list of errors; empty means valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{path}: fragment must be a JSON object"]
    for key in sorted(FORBIDDEN_KEYS & set(data)):
        errors.append(f"{path}: `{key}` is never declared — it is resolved live")
    for key in sorted(set(data) - FRAGMENT_KEYS - FORBIDDEN_KEYS):
        errors.append(f"{path}: unknown key `{key}`")
    for key in REQUIRED_ROOT_KEYS:
        if key not in data:
            errors.append(f"{path}: missing required key `{key}`")
    if "zone" not in data:
        # Called out separately from the loop above: a fragment with no zone has
        # not said what it owns, which is the field's entire purpose.
        errors.append(f"{path}: missing `zone` — a factory that owns nothing owns nothing")
    factory = data.get("factory")
    if factory is not None and factory not in KNOWN_FACTORY_SLUGS:
        errors.append(
            f"{path}: factory `{factory}` is not a known slug "
            f"({', '.join(sorted(KNOWN_FACTORY_SLUGS))})"
        )
    status = data.get("status")
    if status is not None and status not in STATUSES:
        errors.append(f"{path}: status `{status}` is not one of {'|'.join(STATUSES)}")
    if data.get("attested_at") is not None and _iso_date(data["attested_at"]) is None:
        errors.append(f"{path}: attested_at `{data['attested_at']}` does not parse as ISO-8601")
    zone = data.get("zone")
    if zone is not None:
        if not isinstance(zone, dict):
            errors.append(f"{path}: zone must be an object")
        else:
            for key in sorted(set(zone) - ZONE_KEYS):
                errors.append(f"{path}: zone has unknown key `{key}`")
            for key in ("owns", "does_not_own"):
                if key not in zone:
                    errors.append(f"{path}: zone is missing `{key}`")
                elif zone[key] is not None and not isinstance(zone[key], list):
                    errors.append(f"{path}: zone.{key} must be a list")
    services = data.get("services")
    if services is not None:
        if not isinstance(services, list):
            errors.append(f"{path}: services must be a list")
        else:
            for i, service in enumerate(services):
                at = f"{path}: services[{i}]"
                if not isinstance(service, dict):
                    errors.append(f"{at}: must be an object")
                    continue
                for key in sorted(set(service) - SERVICE_KEYS):
                    errors.append(f"{at}: unknown key `{key}`")
                for key in ("name", "audience", "entry"):
                    if key not in service:
                        errors.append(f"{at}: missing required key `{key}`")
                audience = service.get("audience")
                if audience is not None and audience not in ("agent", "owner"):
                    errors.append(f"{at}: audience `{audience}` is not agent|owner")
    substrates = data.get("substrates_owned")
    if substrates is not None and not isinstance(substrates, list):
        errors.append(f"{path}: substrates_owned must be a list")
    if "announcements" not in data:
        errors.append(
            f"{path}: missing `announcements` — the key is required and an empty "
            "list is the honest value for a factory with nothing to announce"
        )
    else:
        validate_announcements(data["announcements"], path, ROOT_SCOPES, errors)
    lanes = data.get("lanes")
    if lanes is not None:
        if not isinstance(lanes, list):
            errors.append(f"{path}: lanes must be a list")
        else:
            for i, lane in enumerate(lanes):
                at = f"{path}: lanes[{i}]"
                if not isinstance(lane, dict):
                    errors.append(f"{at}: must be an object")
                    continue
                for key in sorted(FORBIDDEN_KEYS & set(lane)):
                    errors.append(f"{at}: `{key}` is never declared — it is resolved live")
                for key in sorted(set(lane) - LANE_KEYS - FORBIDDEN_KEYS):
                    errors.append(f"{at}: unknown key `{key}`")
                for key in ("topic", "role"):
                    if key not in lane:
                        errors.append(f"{at}: missing required key `{key}`")
                if "thread_id" in lane and lane["thread_id"] is not None:
                    if not isinstance(lane["thread_id"], int) or isinstance(lane["thread_id"], bool):
                        errors.append(f"{at}: thread_id must be an integer")
                if "announcements" in lane:
                    validate_announcements(lane["announcements"], at, LANE_SCOPES, errors)
    return errors


def load_fragment(path: Path) -> tuple[object, str | None]:
    """Read one fragment file. Returns (data, error)."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"{path}: does not parse as JSON — {exc}"
    except OSError as exc:
        return None, f"{path}: cannot read — {exc}"


def fragment_paths(explicit: list[str]) -> list[Path]:
    """Which files `validate` should read.

    No argument means the two stores that hold fragments: the live store
    (`registry/factories/`, seeded by `enroll`) and the fixtures. Both must pass
    — a fixture that stops validating is a fixture that has stopped describing
    the schema. The live store is optional only while it is empty, and the
    distinction is printed rather than assumed.
    """
    if explicit:
        return [Path(p) for p in explicit]
    paths = sorted(FIXTURE_STORE.glob("*.json")) if FIXTURE_STORE.is_dir() else []
    if FRAGMENT_STORE.is_dir():
        paths = sorted(FRAGMENT_STORE.glob("*.json")) + paths
    return paths


def live_fragment_paths(explicit: list[str]) -> list[Path]:
    """Which files describe the FLEET — the live store only, never the fixtures.

    `validate` reads both stores, because a fixture that stops validating has
    stopped describing the schema. Every other command reads live state, and a
    fixture is not live state: `tests/fixtures/factory-fragment.example.json` is
    an ai-antispam fragment carrying a lane, an `attested` status and a sample
    announcement, so resolving or rendering it would report a seventh fragment,
    duplicate that factory's lane count, and publish a test double as a factory's
    declaration. The two sets are different questions and are read by different
    commands.
    """
    if explicit:
        return [Path(p) for p in explicit]
    return sorted(FRAGMENT_STORE.glob("*.json")) if FRAGMENT_STORE.is_dir() else []


# ---------------------------------------------------------------------------
# The check allowlist: name -> implementation, declared ONCE.
#
# Every predicate is bounded on purpose: a local connect with a timeout, a
# read-only DB URI, a subprocess the gate can time out. A gate that can hang is
# a gate that stops the build for the wrong reason, and this box runs its
# daemons under a 768 MiB cgroup cap — so no predicate may fetch a network
# resource or read a file unbounded.
# ---------------------------------------------------------------------------

# The box's profile root, from the manifest. An empty value is not a default: the
# predicates below glob it, and a glob over `""` silently matches nothing — which
# reads as "no profile has a DB", the shape of a check that cannot fail. So the
# empty case is named at the call site rather than allowed to answer.
PROFILE_ROOT = Path(MANIFEST["profile_root"]) if MANIFEST["profile_root"] else None
A2A_CONFIG = (PROFILE_ROOT / FACTORY_PROFILE / "config.toml") if PROFILE_ROOT else None
CGROUP_UNITS = ("opencrabs", "opencrabs-ops", "opencrabs-family")
MIN_CRON_GAP_MINUTES = 360  # owner order 2026-09-18: nothing wakes a lane < 6 h

_DOW_NAMES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _bounded(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    """Run a command with a hard timeout. Never raises; rc=-1 means timed out."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.TimeoutExpired, OSError) as exc:
        return -1, f"{type(exc).__name__}: {exc}"


def _field_values(field: str, lo: int, hi: int, names: dict | None = None) -> set[int]:
    """Expand one cron field into the set of values it matches.

    Supports the four forms the live table actually uses — `*`, `*/n`, `a-b`,
    and comma lists of any of those (including `Mon,Wed,Fri`). Raises ValueError
    on anything else, so a schedule the parser cannot read is reported rather
    than silently treated as unrestricted.
    """
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            step = int(step_text)
        if step <= 0:
            raise ValueError(f"bad step in `{field}`")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            left, _, right = part.partition("-")
            start, end = _num(left, names), _num(right, names)
        else:
            start = end = _num(part, names)
        if start < lo or end > hi or start > end:
            raise ValueError(f"out of range in `{field}`")
        values.update(range(start, end + 1, step))
    return values


# The scan's day 0 is a Monday, so `(weekday() + 1) % 7` maps Python's Monday=0
# onto cron's Sunday=0..Saturday=6 exactly.
SCAN_START = datetime.date(2024, 1, 1)
SCAN_DAYS = 35


def _num(token: str, names: dict | None) -> int:
    token = token.strip().lower()
    if names and token in names:
        return names[token]
    return int(token)


def parse_cron(expr: str) -> tuple | None:
    """Parse a 5-field cron expression into its five value sets, or None.

    None is a REPORT, not a pass: a schedule the parser cannot read is surfaced
    by the caller. Treating an unparseable expression as unrestricted is how a
    sub-6 h job hides from the census that exists to find it.
    """
    fields = expr.split()
    if len(fields) != 5:
        return None
    try:
        return (
            _field_values(fields[0], 0, 59),
            _field_values(fields[1], 0, 23),
            _field_values(fields[2], 1, 31),
            _field_values(fields[3], 1, 12, _MONTH_NAMES),
            _field_values(fields[4], 0, 6, _DOW_NAMES),
        )
    except ValueError:
        return None


def cron_fires_at(parsed: tuple, day: int, hour: int, minute: int) -> bool:
    """Does a parsed expression fire at this minute of the scan window?"""
    minutes, hours, dom, months, dow = parsed
    if minute not in minutes or hour not in hours:
        return False
    date = SCAN_START + datetime.timedelta(days=day)
    if date.month not in months:
        return False
    dom_restricted = len(dom) < 31
    dow_restricted = len(dow) < 7
    dom_match = date.day in dom
    dow_match = ((date.weekday() + 1) % 7) in dow
    if dom_restricted and dow_restricted:
        # Real cron ORs the two day fields when both are restricted.
        return dom_match or dow_match
    if dom_restricted:
        return dom_match
    if dow_restricted:
        return dow_match
    return True


def cron_min_gap(expr: str) -> tuple[int | None, str]:
    """The smallest gap, in minutes, between two consecutive firings.

    A schedule whose day-of-month or month is restricted cannot fire more than
    once a day, so it is answered arithmetically; the rest are scanned over five
    weeks. A scan finding fewer than two firings returns None — "not
    established" — rather than a number nobody measured.
    """
    parsed = parse_cron(expr)
    if parsed is None:
        return None, f"cannot parse `{expr}`"
    _, _, dom, months, dow = parsed
    if (len(dom) < 31 or len(months) < 12) and len(dow) == 7:
        return 1440, "restricted day/month: at most one firing per day"
    fired: list[int] = []
    for day in range(SCAN_DAYS):
        for hour in range(24):
            for minute in range(60):
                if cron_fires_at(parsed, day, hour, minute):
                    fired.append(day * 1440 + hour * 60 + minute)
    if len(fired) < 2:
        return None, f"fewer than two firings in a {SCAN_DAYS}-day scan of `{expr}`"
    fired.sort()
    gaps = [b - a for a, b in zip(fired, fired[1:])]
    return min(gaps), f"min gap {min(gaps)} min over a {SCAN_DAYS}-day scan"


def check_sqlite3_present() -> tuple[bool, str]:
    path = shutil.which("sqlite3")
    return (bool(path), path or "sqlite3 not on PATH")


def profile_db_glob() -> list[Path]:
    """The per-profile daemon DBs, or a refusal when the root was never declared.

    A `Path("").glob("*/opencrabs.db")` returns the empty list, so an undeclared
    profile root would make every predicate built on this read `no DB, nothing to
    check` and PASS — the exact shape of a check that cannot fail. Returning the
    empty list here is therefore not an option; the caller must be told.
    """
    if PROFILE_ROOT is None:
        raise FleetManifestError(
            "the fleet manifest declares no `profile_root`, so no profile's daemon DB can "
            "be located — a predicate over an unknown root would answer `nothing to check`"
        )
    return sorted(PROFILE_ROOT.glob("*/opencrabs.db"))


def check_cron_min_gap_ge_6h() -> tuple[bool, str]:
    """No ENABLED job on the box may have a minimum gap below 6 h."""
    offenders: list[str] = []
    unreadable: list[str] = []
    checked = 0
    try:
        dbs = profile_db_glob()
    except FleetManifestError as exc:
        return (False, str(exc))
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        except sqlite3.Error as exc:
            unreadable.append(f"{db.name}: {exc}")
            continue
        try:
            for name, expr in conn.execute(
                "select name, cron_expr from cron_jobs where enabled = 1"
            ):
                checked += 1
                gap, note = cron_min_gap(expr)
                if gap is None:
                    unreadable.append(f"{name} ({expr}): {note}")
                elif gap < MIN_CRON_GAP_MINUTES:
                    offenders.append(f"{name} ({expr}) gap {gap} min")
        finally:
            conn.close()
    if offenders:
        return False, "; ".join(offenders[:4])
    if unreadable:
        return False, f"{len(unreadable)} job(s) unreadable: {'; '.join(unreadable[:3])}"
    return True, f"{checked} enabled job(s), none below {MIN_CRON_GAP_MINUTES} min"


def check_daemon_cgroup_cap_present() -> tuple[bool, str]:
    """Each daemon unit must carry a FINITE memory.high.

    Read from the USER manager: a system-scope `systemctl show` resolves to a
    stub and reports `infinity` with an empty FragmentPath, i.e. a false "no
    caps" reading rather than a cap that was lifted.
    """
    missing: list[str] = []
    seen = 0
    for unit in CGROUP_UNITS:
        rc, out = _bounded(
            ["systemctl", "--user", "show", f"{unit}.service", "-p", "MemoryHigh"]
        )
        if rc != 0 or "MemoryHigh=" not in out:
            missing.append(f"{unit}: unreadable (rc={rc})")
            continue
        value = out.strip().split("=", 1)[1].strip()
        seen += 1
        if not value or value == "infinity":
            missing.append(f"{unit}: MemoryHigh={value or 'empty'}")
    if missing:
        return False, "; ".join(missing[:3])
    return True, f"{seen} unit(s) capped"


def check_cross_profile_cli_route() -> tuple[bool, str]:
    """The CLI must expose the cross-profile notify subcommand."""
    rc, out = _bounded(["opencrabs", "session", "--help"])
    if rc != 0:
        return False, f"`opencrabs session --help` rc={rc}"
    if "notify" not in out:
        return False, "`opencrabs session --help` lists no notify subcommand"
    return True, "opencrabs session notify present"


def check_profile_gateway_listening() -> tuple[bool, str]:
    """The declared A2A port must accept a connection."""
    port = None
    if A2A_CONFIG is None:
        return (
            False,
            "the fleet manifest declares no `profile_root`/`profile`, so no profile config "
            "names the A2A port — a probe with no port would answer `nothing to check`",
        )
    try:
        text = A2A_CONFIG.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"cannot read {A2A_CONFIG}: {exc}"
    in_a2a = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_a2a = stripped == "[a2a]"
            continue
        if in_a2a and stripped.startswith("port"):
            match = re.search(r"(\d+)", stripped)
            if match:
                port = int(match.group(1))
            break
    if port is None:
        return False, "no [a2a] port declared in config.toml"
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True, f"127.0.0.1:{port} accepts a connection"
    except OSError as exc:
        return False, f"127.0.0.1:{port} refused: {exc}"


CHECKS.update(
    {
        "sqlite3_present": check_sqlite3_present,
        "cron_min_gap_ge_6h": check_cron_min_gap_ge_6h,
        "daemon_cgroup_cap_present": check_daemon_cgroup_cap_present,
        "cross_profile_cli_route": check_cross_profile_cli_route,
        "profile_gateway_listening": check_profile_gateway_listening,
    }
)


# ---------------------------------------------------------------------------
# The live half: which session is actually behind each declared lane.
#
# Every read goes through a `file:<path>?mode=ro` URI. The DB is never copied:
# a copy without its WAL is stale state, and on this box a bare `cp` of a 1 GB
# database is both a disk leak and memory pressure under a 768 MiB cgroup cap.
#
# A lane is resolved by its `thread_id`, and the answer is the session UUID the
# binding table currently names. That indirection is the point: a fragment
# declares a stable PLACE (the topic), and the session behind it is whatever the
# binding says today. Declaring a UUID would be wrong within days, which is why
# the schema rejects one.
# ---------------------------------------------------------------------------


def profile_dbs() -> list[Path]:
    """Every profile's database, sorted. Read-only, never copied.

    Raises rather than returning `[]` when the manifest declares no
    `profile_root`: an empty list here is indistinguishable from a box with no
    profiles, and every caller would read that as "nothing to check".
    """
    return profile_db_glob()


def read_bindings(db: Path) -> list[dict]:
    """Read one profile's bindings, joined to the session it names.

    `left join` on purpose: a binding whose session row is gone is a fact worth
    reporting (a lane pointing at nothing), and an inner join would hide it.

    The columns are PROBED rather than assumed. Older profile homes carry a
    `session_bindings` without `last_origin`/`turn_open_at`, and a fixed SELECT
    fails outright there — which reads as "this profile has no bindings", the one
    wrong answer that is indistinguishable from a healthy empty result. So a
    missing column becomes NULL and the row shape stays constant.
    """
    rows: list[dict] = []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        return [{"_error": f"{db}: {exc}"}]
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            row[0]
            for row in conn.execute("select name from sqlite_master where type='table'")
        }
        if "session_bindings" not in tables:
            return [{"_error": f"{db}: no session_bindings table"}]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(session_bindings)")}
        select = ["b.session_id", "b.channel", "b.chat_id", "b.thread_id", "b.updated_at"]
        for optional in ("last_origin", "turn_open_at"):
            select.append(f"b.{optional}" if optional in columns else f"NULL as {optional}")
        if "sessions" in tables:
            select += ["s.title as session_title", "s.updated_at as session_updated_at"]
        else:
            select += ["NULL as session_title", "NULL as session_updated_at"]
        sql = (
            "select " + ", ".join(select) + " from session_bindings b "
            + ("left join sessions s on s.id = b.session_id" if "sessions" in tables else "")
        )
        for row in conn.execute(sql):  # iterated, never materialised into a second list
            record = dict(row)
            record["_profile"] = db.parent.name
            record["_db"] = str(db)
            rows.append(record)
    except sqlite3.Error as exc:
        rows.append({"_error": f"{db}: {exc}"})
    finally:
        conn.close()
    return rows

def load_topic_names(path: str | None) -> dict:
    """Topic names read from the Telegram surface, where the caller supplied them.

    The daemon DB holds `thread_id` and the session's own title, not the forum
    topic's NAME — that lives on the Telegram surface. So the name is an INPUT,
    and an announcement or lane row whose name did not come from this file is
    rendered `unverified` rather than guessed from a session title that happens
    to look similar.
    """
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"resolve: cannot read --topics {path}: {exc}")
    entries = data.get("topics", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise SystemExit("resolve: --topics must be a list, or an object with a `topics` list")
    names: dict = {}
    for entry in entries:
        if not isinstance(entry, dict) or "thread_id" not in entry:
            continue
        names[(str(entry.get("chat_id", "")), int(entry["thread_id"]))] = entry.get("name")
    return names


def resolve_lane(lane: dict, bindings: list[dict], topic_names: dict, chat_id=None) -> dict:
    """Resolve one declared lane against the live binding rows.

    `chat_id` is the factory's OWN chat, and it is a narrowing rather than a
    guess: a thread id is unique only WITHIN a chat, so thread 4 exists in both
    the Miidas and the Infra chat and an unscoped match reported Miidas's HQ
    session among the candidates for Infra's HQ lane. Where the factory's chat is
    known and the declared thread is not in it, the lane is `unbound` — the
    honest answer, since the room it names does not exist in that chat.
    """
    thread_id = lane.get("thread_id")
    result = {
        "topic": lane.get("topic"),
        "role": lane.get("role"),
        "thread_id": thread_id,
        "session_id": None,
        "status": "unbound",
        "channel": None,
        "chat_id": None,
        "bound_at": None,
        "binding_age_s": None,
        "last_origin": None,
        "turn_open": None,
        "session_title": None,
        "topic_name": None,
        "topic_name_verified": False,
    }
    if thread_id is None:
        result["status"] = "no-thread-id"
        return result
    matches = [b for b in bindings if b.get("thread_id") == thread_id and "_error" not in b]
    if chat_id is not None:
        matches = [b for b in matches if str(b.get("chat_id")) == str(chat_id)]
    if not matches:
        return result
    if len(matches) > 1:
        # A thread id that appears in two chats or two profiles is ambiguous, and
        # picking one silently is how a registry sends work to the wrong lane.
        newest = max(matches, key=lambda b: b.get("updated_at") or 0)
        result["status"] = "ambiguous"
        result["candidates"] = sorted(
            f"{b['_profile']}:{b['chat_id']}/{b['thread_id']}={b['session_id']}" for b in matches
        )
    else:
        newest = matches[0]
        result["status"] = "resolved"
    result.update(
        {
            "session_id": newest.get("session_id"),
            "channel": newest.get("channel"),
            "chat_id": newest.get("chat_id"),
            "last_origin": newest.get("last_origin"),
            "turn_open": bool(newest.get("turn_open_at")),
            "session_title": newest.get("session_title"),
        }
    )
    updated = newest.get("updated_at")
    if updated:
        result["bound_at"] = datetime.datetime.fromtimestamp(
            updated, datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        result["binding_age_s"] = int(
            datetime.datetime.now(datetime.timezone.utc).timestamp() - updated
        )
    key = (str(newest.get("chat_id", "")), int(thread_id))
    if key in topic_names:
        result["topic_name"] = topic_names[key]
        result["topic_name_verified"] = True
    return result


def collect_declared_lanes(paths: list[Path]) -> tuple[dict, list[str]]:
    """Every lane the fragments declare, grouped by factory slug."""
    lanes: dict = {}
    problems: list[str] = []
    for path in paths:
        data, error = load_fragment(path)
        if error:
            problems.append(error)
            continue
        if not isinstance(data, dict):
            continue
        factory = data.get("factory") or path.stem
        bucket = lanes.setdefault(str(factory), [])
        for lane in data.get("lanes") or []:
            if isinstance(lane, dict):
                bucket.append(lane)
    return lanes, problems


def cmd_resolve(args: argparse.Namespace) -> int:
    paths = live_fragment_paths(args.paths)
    if not paths:
        print("registry: no fragments to resolve", file=sys.stderr)
        return 1
    topic_names = load_topic_names(args.topics)
    lanes_by_factory, problems = collect_declared_lanes(paths)
    bindings: list[dict] = []
    errors: list[str] = []
    try:
        dbs = profile_dbs()
    except FleetManifestError as exc:
        print(f"registry: {exc}", file=sys.stderr)
        return 1
    for db in dbs:
        rows = read_bindings(db)
        errors.extend(r["_error"] for r in rows if "_error" in r)
        bindings.extend(r for r in rows if "_error" not in r)

    resolved: dict = {}
    totals = {"lanes": 0, "resolved": 0, "unbound": 0, "ambiguous": 0, "no-thread-id": 0}
    for factory, lanes in sorted(lanes_by_factory.items()):
        rows = [
            resolve_lane(lane, bindings, topic_names, FACTORY_CHATS.get(factory))
            for lane in lanes
        ]
        for row in rows:
            totals["lanes"] += 1
            totals[row["status"]] = totals.get(row["status"], 0) + 1
        resolved[factory] = rows

    payload = {
        "resolved_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "profiles_read": [str(db) for db in dbs],
        "fragment_sources": [str(p) for p in paths],
        "bindings_seen": len(bindings),
        "factories": resolved,
        "summary": totals,
        "errors": errors + problems,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=False))
    else:
        print(f"resolved_at {payload['resolved_at']}  ({len(bindings)} bindings read)")
        for factory, rows in sorted(resolved.items()):
            for row in rows:
                name = row["topic_name"] or row["session_title"] or "-"
                print(
                    f"  {row['status']:<10} {factory:<16} {str(row['topic']):<12} "
                    f"thread={row['thread_id']} session={row['session_id']}  {name}"
                )
        print(
            "summary: {lanes} lane(s), {resolved} resolved, {unbound} unbound, "
            "{ambiguous} ambiguous".format(**totals)
        )
    if errors or problems:
        for line in errors + problems:
            print(f"resolve: {line}", file=sys.stderr)
    unresolved = totals["unbound"] + totals["ambiguous"] + totals["no-thread-id"]
    return 1 if unresolved else 0


# ---------------------------------------------------------------------------
# Enrollment — stage 1 of the five-stage process
# ---------------------------------------------------------------------------
#
# `enroll` writes the OBSERVED half of a fragment mechanically and leaves the
# DECLARED half explicitly null. The split is the point of the exercise: a
# generator can read a repo, a skill file and a live binding table, and it can
# read NOTHING about what a factory offers or what it owns. So it fills what it
# can prove, and writes `null` where the answer belongs to the factory itself.
#
# A stub is a QUESTION, not a claim — which is why this is legitimate for
# Meta-Factory to run against member factories at all (SKILL.md §3): it authors
# no member's self-description, it asks the owner to. `status: "unattested"` is
# how a fragment says nobody has answered yet.
#
# Enrollment is keyed on the factory ID and the file is named for it, so a
# re-delivered brief converges on one fragment instead of writing a second —
# `session_notify` replay is a verified failure mode on this box (fork #366).

# The factory's own forum chat, its repo, its law file and its display name are
# all DECLARED in `registry/fleet.json` and derived at the top of this module —
# see §The fleet manifest. They were six hardcoded dicts here, which is what made
# this file un-portable: a template carrying them ships one box's fleet to every
# factory that copies it.
#
# The comment those dicts carried is kept, because it explains the manifest's
# SHAPE and would otherwise be lost with them: a chat is an ID and not a name,
# deliberately, because the same chat renders under two names in live binding
# titles ("Opencrabs Dev Factory" and "Crabs Kanban Board") and a name-keyed
# lookup would split one chat into two. And the law file is not uniform across
# factories: `opencrabs-dev` keeps its law in a repository of its own under the
# profile (remote `opencrabs-skill`), while `ai-antispam` has a REAL DIRECTORY in
# the profile skills tree that no bootstrap symlink ever pointed at (issue #79) —
# so the manifest declares a PATH per factory, and the repo's copy is the one the
# factory's own law names as authoritative.

# A topic is not a lane, and binding alone cannot tell them apart: opencrabs-dev's
# chat holds 42 bound thread ids of which two name a role. Three named rules
# narrow the set, and the enrollment summary PRINTS what each one removed — a
# count taken by a pattern is a count of the pattern, never of the lanes, and
# the output says which of the two numbers it reports:
#
# (The names in this block are the history that produced the rule — one box's
# evidence, kept because a rule without its counter-example gets "simplified"
# back into the defect. A factory bootstrapping from this template inherits the
# three rules and none of these names.)
#
#   1. a name that states another factory is a conversation ABOUT a peer — the
#      OC DEV chat carries `МИИДАС`, `Miidas marketing` and `Inferhub watch`
#   2. a session-internal title (`subagent: ...`) is a label a dispatch gave
#      itself, not a room
#   3. everything else is kept, with `role: null` where the name states no role
#
# Rule 3 is deliberate, and it is the fix for a defect this tool found by being
# run against the live fleet: a role-name filter SILENTLY DROPS the most
# important lane in the registry. InferHub's HQ session (359fe71b) sits in
# thread 2 under the title `InferHub Watch: Fallback Publisher Diversity &
# Predictors` — no role word anywhere in it — and meta-factory's own HQ and
# Triage lanes carry hand-written titles too. A filter keeping only recognised
# roles returns a stub missing its own HQ, and a missing row is indistinguishable
# from a factory that has no HQ. So the filter narrows and never decides:
# `role: null` states that the name states no role, and the stub asks the HQ.
LANE_ROLE_HINTS = (
    ("hq", r"\bhq\b|headquarters"),
    ("triage", r"\btriage\b"),
    ("worker", r"\bworker\b"),
    ("delegate", r"\bdelegate\b"),
    ("surveys", r"\bsurveys?\b"),
    ("carrier", r"\bcarrier\b"),
    ("editor", r"\beditor"),
    ("outreach", r"\boutreach\b"),
    ("landing", r"\blanding\b"),
    ("marketing", r"\bmarketing\b"),
    ("bot", r"\bbot\b"),
    ("gateway", r"\bgateway\b"),
    ("grafana", r"\bgrafana\b"),
)

# A chat carries rooms that belong to ANOTHER factory, and such a room is a
# conversation about a peer rather than a lane of this factory. The test is
# mechanical — the name states a peer's own name — and it is deliberately
# narrow: a shared word like "infra" would fire on half the fleet. The aliases
# are declared per factory in `registry/fleet.json`; the rule is stated here and
# the vocabulary is data, because the vocabulary is the part that differs per box.

SKILL_VERSION_RE = re.compile(r"^version:\s*(\S+)\s*$", re.MULTILINE)
# `Telegram: <group> / <topic> [chat:...]` — the topic segment, and only that
# form. A session created inside a topic inherits it, so this is the one title
# shape whose topic segment is a READ of the room's name.
TOPIC_SEGMENT_RE = re.compile(r"^Telegram: [^/]+? / (.+?)(?: \[chat:|$)")
# `Telegram: <group> [chat:...]` or `Telegram: <group> / <topic> [chat:...]`.
GROUP_SEGMENT_RE = re.compile(r"^Telegram: ([^/]+?)(?: / | \[chat:)")
# A dispatch names itself, and that label is not a room. Only `subagent:` is
# treated this way: `worker: inferhub-watch-lane` looks like a lane's own
# session and dropping it would lose a real lane, which is the worse error.
SESSION_INTERNAL_TITLE_RE = re.compile(r"^subagent\s*:", re.IGNORECASE)


def read_skill_version(path: Path) -> str | None:
    """The declared `version:` line of a law file, or None. Never a default."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = SKILL_VERSION_RE.search(text)
    return match.group(1) if match else None


def lane_name_from_title(title: object) -> tuple[str | None, bool]:
    """A bound session's title -> (room name, came_from_the_canonical_form).

    The canonical form first: a session created inside a topic inherits
    `Telegram: <group> / <topic> [chat:...]`, and that topic segment is a read
    of the room's own name. Any other title was written by whoever created the
    session, so the name it yields is PROVISIONAL — usually right (meta-factory's
    HQ lane reads `Meta-Factory HQ: ASIF Architecture & Crons`) and never
    verified. The caller counts how many names came this way, so a summary can
    never present a provisional name as a read one.
    """
    if not isinstance(title, str):
        return None, False
    match = TOPIC_SEGMENT_RE.match(title)
    if match:
        return (match.group(1).strip() or None), True
    if GROUP_SEGMENT_RE.match(title):
        # The bare `Telegram: <group> [chat:...]` form: the session sits in a
        # topic (thread 1, or a room named after the chat itself) whose name the
        # title does not carry. Reading the GROUP name out of it would file a
        # room under its parent chat's name — a wrong answer, not a missing one.
        return None, False
    stripped = title.strip()
    if not stripped or SESSION_INTERNAL_TITLE_RE.match(stripped):
        return None, False
    return stripped, False


def group_name_from_title(title: object) -> str | None:
    """The chat segment of a bound session title, or None when it has none."""
    if not isinstance(title, str):
        return None
    match = GROUP_SEGMENT_RE.match(title)
    if not match:
        return None
    return match.group(1).strip() or None


def lane_role(name: str) -> str | None:
    """The role a name states, or None. The EARLIEST role word wins.

    Position, not table order: `Worker — HQ cycles` states two roles, and it is
    the worker lane carrying that topic. Table order reads the `HQ` inside the
    phrase and files the row under the wrong role — a wrong role being worse
    than no role, because it reads as an answer.
    """
    lowered = name.lower()
    best: tuple[int, str] | None = None
    for role, pattern in LANE_ROLE_HINTS:
        match = re.search(pattern, lowered)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), role)
    return best[1] if best else None


def names_other_factory(name: str, slug: str) -> str | None:
    """The other factory this name states, or None when it states none."""
    lowered = name.lower()
    for other, aliases in FACTORY_NAME_ALIASES.items():
        if other == slug:
            continue
        for alias in aliases:
            if alias in lowered:
                return other
    return None


def all_bindings() -> tuple[list[dict], list[str]]:
    """Every binding row from every profile DB, read in place via mode=ro.

    An undeclared `profile_root` comes back as an ERROR, never as an empty
    result: the callers of this function write a resolved registry, and "no
    profile was readable" must not render as "no lane is bound".
    """
    rows: list[dict] = []
    errors: list[str] = []
    try:
        dbs = profile_dbs()
    except FleetManifestError as exc:
        return [], [str(exc)]
    for db in dbs:
        found = read_bindings(db)
        errors.extend(r["_error"] for r in found if "_error" in r)
        rows.extend(r for r in found if "_error" not in r)
    return rows, errors


def derive_lanes(chat_id: int, bindings: list[dict], slug: str) -> tuple[list[dict], dict]:
    """Derive a factory's lanes from its own chat's live bindings.

    One lane per THREAD: a chat binds several sessions to one topic (thread
    30220 carries four), and listing each would report one room four times.
    """
    stats = {
        "threads_seen": 0,
        "roleless": 0,
        "provisional_names": 0,
        "dropped_other_factory": [],
        "dropped_unnamed": [],
    }
    by_thread: dict = {}
    for row in bindings:
        # `chat_id` is TEXT in the binding table and an int in the constant, so
        # the comparison is made on the string form. Matching on the raw values
        # silently returns zero lanes for every factory — a wrong answer that
        # reads exactly like a factory with no lanes.
        if str(row.get("chat_id")) != str(chat_id) or row.get("thread_id") is None:
            continue
        by_thread.setdefault(row["thread_id"], []).append(row)
    stats["threads_seen"] = len(by_thread)
    lanes: list[dict] = []
    for thread_id in sorted(by_thread):
        name: str | None = None
        canonical = False
        for row in by_thread[thread_id]:
            candidate, is_canonical = lane_name_from_title(row.get("session_title"))
            if candidate and (name is None or (is_canonical and not canonical)):
                name, canonical = candidate, is_canonical
                if canonical:
                    break
        if name is None:
            # `session_title` is NULL for a session whose title was never set.
            # Such a thread is a room this tool cannot name, and naming it by its
            # session UUID would put an identifier in a field that carries a name.
            stats["dropped_unnamed"].append(thread_id)
            continue
        other = names_other_factory(name, slug)
        if other:
            stats["dropped_other_factory"].append(f"{thread_id}={name} (about {other})")
            continue
        role = lane_role(name)
        if role is None:
            stats["roleless"] += 1
        if not canonical:
            stats["provisional_names"] += 1
        lanes.append({"topic": name, "thread_id": thread_id, "role": role, "announcements": []})
    return lanes, stats


def derive_display_name(chat_id: int, bindings: list[dict], slug: str) -> tuple[str, list[str]]:
    """The chat's live group name, and every name it has rendered under.

    More than one name is not an error — it is a rename, and the caller prints
    the whole set so the older one is visible rather than silently dropped.
    """
    seen: dict = {}
    for row in bindings:
        if str(row.get("chat_id")) != str(chat_id):
            continue
        name = group_name_from_title(row.get("session_title"))
        if name:
            seen[name] = seen.get(name, 0) + 1
    if not seen:
        return FACTORY_DISPLAY_NAMES.get(slug, slug), []
    ranked = sorted(seen, key=lambda n: (-seen[n], n))
    return ranked[0], ranked


def build_stub(slug: str, bindings: list[dict]) -> tuple[dict, dict]:
    """The observed half, filled; the declared half, explicitly null."""
    chat_id = FACTORY_CHATS[slug]
    lanes, stats = derive_lanes(chat_id, bindings, slug)
    display_name, names_seen = derive_display_name(chat_id, bindings, slug)
    skill_path = Path(FACTORY_SKILLS[slug])
    fragment = {
        "factory": slug,
        # Observed: the chat's own live name. The declared identity of a factory
        # is not its group name, but this field is the label a reader matches
        # against their client, and the client shows the group name.
        "display_name": display_name,
        "profile": FACTORY_PROFILE,
        "repo": FACTORY_REPOS[slug],
        "skill": FACTORY_SKILLS[slug],
        # Declared half — `null` is a statement ("nobody has told us"), while an
        # absent key is indistinguishable from a generator that forgot to write
        # it. So the key set is complete and the values carry the doubt.
        "purpose": None,
        "zone": {"owns": None, "does_not_own": None},
        "services": None,
        "substrates_owned": None,
        # Required, and an empty list is the honest value for a factory with
        # nothing to announce — an absent key would let the render imply an
        # answer that was never given.
        "announcements": [],
        "lanes": lanes,
        "status": "unattested",
        "attested_at": None,
    }
    stats.update(
        {
            "factory": slug,
            "chat_id": chat_id,
            "display_name": display_name,
            "names_seen": names_seen,
            "skill_path": str(skill_path),
            "skill_version": read_skill_version(skill_path),
            "skill_present": skill_path.is_file(),
            "repo_present": Path(FACTORY_REPOS[slug]).is_dir(),
            "lanes": len(lanes),
            "lane_rows": lanes,
        }
    )
    return fragment, stats


def cmd_enroll(args: argparse.Namespace) -> int:
    """Write the stub for one factory, or for the whole fleet with --all."""
    slugs = sorted(KNOWN_FACTORY_SLUGS) if args.all else [args.factory]
    unknown = [s for s in slugs if s not in KNOWN_FACTORY_SLUGS]
    if unknown:
        print(f"enroll: unknown factory slug(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    bindings, errors = all_bindings()
    if not bindings:
        print("enroll: no live bindings read — refusing to write a blind stub", file=sys.stderr)
        return 1

    FRAGMENT_STORE.mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    skipped: list[str] = []
    for slug in slugs:
        path = FRAGMENT_STORE / f"{slug}.json"
        if path.exists() and not args.force:
            existing, error = load_fragment(path)
            status = existing.get("status") if isinstance(existing, dict) else None
            if error is None and status == "attested":
                # A filled fragment is a factory's own answer. Overwriting it
                # with a blank stub would destroy the only declared data the
                # registry has, so it takes --force to do that on purpose.
                skipped.append(f"{slug} (attested — use --force to reset)")
                continue
        fragment, stats = build_stub(slug, bindings)
        problems = validate_fragment(fragment, str(path))
        if problems:
            for line in problems:
                print(f"enroll: {line}", file=sys.stderr)
            return 1
        if args.dry_run:
            written.append({**stats, "path": str(path), "dry_run": True})
            continue
        path.write_text(json.dumps(fragment, indent=2) + "\n", encoding="utf-8")
        written.append({**stats, "path": str(path), "dry_run": False})

    for stats in written:
        names = stats["names_seen"]
        alias = "" if len(names) <= 1 else f"  (also rendered as: {', '.join(names[1:])})"
        print(
            f"  {stats['factory']:<16} lanes={stats['lanes']:<3} "
            f"threads_seen={stats['threads_seen']:<3} roleless={stats['roleless']:<3} "
            f"provisional_name={stats['provisional_names']:<3} "
            f"other_factory={len(stats['dropped_other_factory']):<3} "
            f"unnamed={len(stats['dropped_unnamed']):<3} "
            f"skill={stats['skill_version'] or 'UNKNOWN'}"
            f"{'' if stats['skill_present'] else ' [SKILL FILE MISSING]'}"
            f"{'' if stats['repo_present'] else ' [REPO MISSING]'}{alias}"
        )
        if args.explain:
            for line in stats["dropped_other_factory"]:
                print(f"      not a lane (another factory's room): {line}")
            for thread_id in stats["dropped_unnamed"]:
                print(f"      not a lane (no title to read a room name from): thread {thread_id}")
            for lane in stats["lane_rows"]:
                if lane["role"] is None:
                    print(f"      role unstated: {lane['thread_id']} {lane['topic']}")
    for line in skipped:
        print(f"  skipped {line}")
    print(
        f"enroll: {len(written)} fragment(s) "
        f"{'planned' if args.dry_run else 'written'} to {FRAGMENT_STORE}"
    )
    for line in errors:
        print(f"enroll: {line}", file=sys.stderr)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    paths = fragment_paths(args.paths)
    if not paths:
        print("registry: no fragments found — nothing validated", file=sys.stderr)
        return 1
    failures = 0
    for path in paths:
        data, error = load_fragment(path)
        errors = [error] if error else validate_fragment(data, str(path))
        if errors:
            failures += 1
            for line in errors:
                print(f"INVALID {line}", file=sys.stderr)
        else:
            print(f"ok {path}")
    if failures:
        print(f"registry: {failures} of {len(paths)} fragment(s) invalid", file=sys.stderr)
        return 1
    print(f"registry: {len(paths)} fragment(s) valid")
    return 0


def cmd_checks(args: argparse.Namespace) -> int:
    """Run every predicate in the allowlist and print its verdict.

    The renderer calls these through the same mapping, so a predicate is
    exercised here long before an announcement depends on it — and a predicate
    that cannot run at all is visible as FAIL rather than as a missing badge.
    """
    failures = 0
    for name in sorted(CHECKS):
        try:
            holds, evidence = CHECKS[name]()
        except Exception as exc:  # a predicate must never take the tool down
            holds, evidence = False, f"{type(exc).__name__}: {exc}"
        marker = "HOLDS" if holds else "FAILS"
        if not holds:
            failures += 1
        print(f"{marker} {name}: {evidence}")
    print(f"registry: {len(CHECKS) - failures}/{len(CHECKS)} predicate(s) hold")
    return 1 if failures else 0


def cmd_render(args: argparse.Namespace) -> int:
    """Render the two artifacts: the document and the machine index.

    Imported INSIDE the function on purpose. `registry_render` imports this
    module at its top level, so a top-level import here would be a cycle — and
    the renderer needs this module's predicates and readers, not the other way
    round.
    """
    import registry_render

    resolved_at = args.at or None
    code, report = registry_render.render_all(
        explicit=args.paths, resolved_at=resolved_at, write=not args.check
    )
    if code != 0:
        print(f"registry: {report['error']}", file=sys.stderr)
        return code
    for problem in report["problems"]:
        print(f"WARN {problem}", file=sys.stderr)
    mode = "checked (not written)" if args.check else "wrote"
    print(
        f"registry: {mode} {report['markdown']} and {report['index']} — "
        f"{report['factories']} factory/factories, {report['lanes']} lane(s), "
        f"{report['announcements']} announcement(s), {report['jobs']} job(s) "
        f"({report['unattributed_jobs']} unattributed), "
        f"resolved_at={report['resolved_at']}"
    )
    return 0

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The factory registry.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate", help="validate fragment JSON")
    p_validate.add_argument("paths", nargs="*", help="fragment files (default: both stores)")
    p_validate.set_defaults(func=cmd_validate)
    p_checks = sub.add_parser("checks", help="run every predicate in the allowlist")
    p_checks.set_defaults(func=cmd_checks)
    p_resolve = sub.add_parser("resolve", help="resolve each declared lane to a live session")
    p_resolve.add_argument("paths", nargs="*", help="fragment files (default: both stores)")
    p_resolve.add_argument("--json", action="store_true", help="machine-readable output")
    p_resolve.add_argument(
        "--topics",
        help="JSON list of {chat_id, thread_id, name} read from the Telegram surface; "
        "without it, topic names render unverified",
    )
    p_resolve.set_defaults(func=cmd_resolve)
    p_enroll = sub.add_parser(
        "enroll", help="write a factory's stub: observed half filled, declared half null"
    )
    p_enroll.add_argument("--all", action="store_true", help="every known factory")
    p_enroll.add_argument("factory", nargs="?", help="one factory slug")
    p_enroll.add_argument("--force", action="store_true", help="overwrite an attested fragment")
    p_enroll.add_argument("--dry-run", action="store_true", help="report without writing")
    p_enroll.add_argument(
        "--explain",
        action="store_true",
        help="print every thread the derivation kept without a role, and every one it dropped",
    )
    p_enroll.set_defaults(func=cmd_enroll)
    p_render = sub.add_parser(
        "render", help="write docs/factory-registry.md and registry/index.json"
    )
    p_render.add_argument("paths", nargs="*", help="fragment files (default: live store)")
    p_render.add_argument(
        "--at",
        help="the instant to stamp as resolved_at (default: now); the drift gate "
        "passes a fixed sentinel so a fresh render is not read as drift",
    )
    p_render.add_argument(
        "--check",
        action="store_true",
        help="render and report without writing — the drift gate's read path",
    )
    p_render.set_defaults(func=cmd_render)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
