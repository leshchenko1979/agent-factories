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
         [--ref KIND:VALUE ...]                       typed pointers to other objects
  tail [--n N]                                        read-only, newest last
  verify                                              read-only: structure, and
                                                      each subject's sequence

What a refusal tells you
------------------------
An unrecognized flag is NOT refused with a bare usage line. A typo and a request for
a capability this tool does not carry read identically to argparse, so the refusal
names the two lawful routes instead: `--ref` for a typed pointer from this row to
another object, and `docs/ledger-refs-kinds.json` for a DECLARED new ref kind or
event -- which is how a member factory carries an object the core vocabulary does
not have, without forking this file. A refusal exits 2.

Exit: 0 ok, 1 problem (bad usage, corrupted ledger, unknown event type, or a
`close` — or a `claim` — whose transition sequence is incomplete).

Row shape (one JSON object per line, append-only):
  {"n":1,"ts":"...","event":"claim","actor":"triage","subject":"#6","detail":"..."}

The transition sequence
-----------------------
A subject's rows are a sequence, not a row count: `intake` (filed), then
`claim` (taken), then `close` (finished). A close with no intake is work that
was never filed; a close with no claim is work nobody took. And a `claim` whose
subject has no intake ANYWHERE is work taken on a subject the ledger never
admitted — a leg that used to be invisible until the close failed, so the defect
was discovered hours after it was made, by whoever tried to close. It is now
reported at the claim and refused at the write path.

`verify` reads the sequence and names the subject and the missing leg; `append`
asks the SAME predicate about the row it is about to write, so a defect is named
at the moment it would be created. The claim leg looks for an intake anywhere in
the subject's history, because a late-reconstruction intake lands AFTER the
original claim by design; the close leg stays positional.

The unit you are copying
------------------------
This file is NOT standalone. It imports modules that ship beside it in `tools/`,
and a factory that copies this file alone gets a `ModuleNotFoundError` at import
rather than a ledger. The sets are DECLARED below so they are checkable rather
than prose: `tests/test_ledger_header_closure.py` asserts each declaration equals
this file's actual intra-repo imports of that kind, in both trees.

Closure: ledger_declaration.py, field_predicate.py, reconstruction.py

Deferred: registry.py, telemetry.py

`Closure` modules are imported at MODULE level, so a tree missing one dies at
import -- copy them with the file. `Deferred` modules are imported INSIDE
functions on purpose (a fixture append must not pay for the lane resolver), so a
tree missing one degrades at that call rather than at startup. Both must be
present for the tool to work; only the first kind stops it from loading.

`EVENTS` below is the CORE vocabulary, never the factory's whole one. A factory's
event set is a fact about ITS process, so a member that legitimately adds an event
declares it in `docs/ledger-refs-kinds.json` and `known_events()` folds it in --
the same shape as `tools/actors.txt` for the actor set. Forking this file to add
an event is the wrong move: its constants must match everywhere, which is exactly
why the declaration surfaces are separate files.

Two companion artefacts are part of no copy, and a factory that syncs the modules
WITHOUT them has a dormant declared-invariant leg that fails OPEN -- `verify`
reads clean while the leg examines nothing:

  docs/ledger-invariants.json   instantiated from the shipped
                                `docs/ledger-invariants.example.json`. Absent, the
                                declared boundaries are never read.
  tests/ledger_boundary.py      the shared absence/population reader that this
                                tool and the gates both import. Absent, the
                                boundary legs cannot run at all.

They are named here so a factory can READ that its leg is dormant, rather than
infer it from a clean `verify`.
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
    authorized_for_event,
    boundary_for,
    load_authorizations,
    load_exemptions,
    parse_ts,
)

# RE-EXPORTED, and not used by this module's own code: `tests/test_ledger_schema.py` reads
# AND writes `ledger.AUTHORIZED_ACTORS_BY_EVENT` (the convergence cases), so the binding has
# to live on THIS namespace. Written as an explicit assignment rather than left as a bare
# import because pyflakes 3.4 reports a bare re-export as an unused import, and the
# `as`-alias form does NOT read as a re-export to it -- both measured 2026-09-28. Keep the
# assignment: deleting it as a no-op removes the binding the schema gate mutates.
AUTHORIZED_ACTORS_BY_EVENT = AUTHORIZED_ACTORS_BY_EVENT

# The field predicate is shared with both schema gates (#88, ledger n=405 clause 5), on the
# same bare-neighbour import and for the same reason: `stage_tool`'s closure walker resolves
# a neighbour by that name when it stages a throwaway tree.
from field_predicate import (
    declared_claim,
    declared_keys,
    declared_reclaim,
    declared_reclose,
    declared_revision,
    mentions_reclaim,
    mentions_reclose,
    declared_telemetry_provenance,
    declares_field,
    split_canonical_run,
)

# The reconstruction predicate — which rows are reconstructed claims and the interval
# recomputed from the two rows' own `ts` values — is shared with the gate that judges the
# self-declaration, on the same bare-neighbour import and for the same reason: two private
# copies of one predicate drift in silence, and the drift lands on exactly the rows that
# matter (`n=405` clause 5, `n=599`).
from reconstruction import (
    RECONSTRUCTION_KEY,
    RECONSTRUCTION_VALUE,
    interval_line,
    reconstructed_claims,
)

REPO = Path(__file__).resolve().parent.parent

# The fields that make a row what it is. `detail` is deliberately absent: it is the ONE
# field a lawful repair may extend, and the identity around it is what `verify` and every
# subject-keyed predicate resolve through.
ROW_IDENTITY = ("n", "ts", "event", "actor", "subject")

# THE DECLARED EXTENSION SURFACE (#ledger-instrument, owner order 2026-09-27).
# A ref is a TYPED POINTER from a row to another object, so an edge a row already
# claims in prose becomes one an instrument can follow. Kinds are DECLARED, never
# guessed: the core set below, plus whatever the factory adds in
# docs/ledger-refs-kinds.json -- the same declaration family as
# docs/ledger-exemptions.json, so a member's own object needs no fork.
CORE_REF_KINDS = ("row", "subject", "commit", "session", "rework")
# Every declared surface in this module is relocatable, and for the same reason: a
# member tree whose layout differs must be able to point the instrument at its own
# declaration without editing the instrument. `OC_ACTORS_PATH` and `OC_LEDGER_PATH`
# already work this way, and the fixture seam that makes a declaration relocatable is
# the same seam that makes a fixture lawful.
REFS_KINDS_FILE = Path(
    os.environ.get(
        "OC_REFS_KINDS_PATH", REPO / "docs" / "ledger-refs-kinds.json"
    )
)


def known_events() -> tuple[str, ...]:
    """The core events, plus any this factory declares in `ledger-refs-kinds.json`.

    THE EVENT VOCABULARY IS THE SAME KIND OF THING AS THE REF KINDS: a member's event
    is a fact about that factory's process, not a divergence to be policed. Measured
    2026-09-27: inferhub-watch's ledger carries 8 `ack` rows, an event the shipped
    EVENTS tuple does not name, so `verify` reds on a ledger whose rows were all
    written lawfully -- the member is pushed toward forking this file when what it
    actually has is a DECLARATION it cannot make. Declaring it here makes the member's
    own vocabulary lawful without a fork, and keeps ONE reader for it.

    Core events are never removable: a declaration ADDS, it does not redefine.
    """
    declared = _read_extension_declaration()
    extra = [e for e in declared.get("events", []) if isinstance(e, str)]
    return EVENTS + tuple(e for e in extra if e not in EVENTS)


def _read_extension_declaration() -> dict:
    """The factory's declared extension surface -- ref kinds and events.

    Unreadable or absent is NOT an error: the core vocabulary stands alone, which is
    what lets the field ship before any factory has declared anything.
    """
    try:
        return json.loads(REFS_KINDS_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def known_ref_kinds() -> tuple[str, ...]:
    """The core ref kinds, plus any this factory declares.

    Unreadable or absent declaration is NOT an error: the core set stands alone,
    which is what lets the field ship before any factory has declared a kind.
    """
    declared = _read_extension_declaration()
    extra = [k for k in (declared.get("kinds") or []) if isinstance(k, str)]
    return CORE_REF_KINDS + tuple(k for k in extra if k not in CORE_REF_KINDS)


def parse_refs(values: list[str]) -> list[dict]:
    """Typed pointers, validated for FORM **and KIND** at the write path.

    `KIND:VALUE`, and a malformed ref is refused HERE, at append, naming the lawful
    kinds -- the form is the one thing the tool can settle without knowing a member's
    object. The EXISTENCE check (a `row` ref must resolve) is a separate leg: it needs
    the ledger's own maximum, which only the append lock holds.

    The KIND check is here rather than at the gate (#232) because `verify` refuses an
    undeclared kind a step LATER, when the row is already written and pushed and can only
    be cleared by declaring the kind -- never by removing the ref, since a row is immutable
    once pushed. That is #187's class one field over, and this is the same move: the
    predicate `known_ref_kinds()` stays single, and the write path and the gate read it.

    A kind that is not lawful is refused by naming BOTH the lawful set and the file that
    extends it, because the lawful remedy for a genuinely new kind is to DECLARE it, never
    to drop the ref. A fixture writer is unaffected: the declaration is read from
    `REFS_KINDS_FILE`, the same `OC_REFS_KINDS_PATH` seam every other reader uses.
    """
    refs: list[dict] = []
    for raw in values:
        kind, sep, value = raw.partition(":")
        if not sep or not kind or not value:
            sys.exit(
                f"ledger append refused: --ref {raw!r} is not KIND:VALUE "
                f"(e.g. row:1228, subject:#149, commit:be47c443). "
                f"Kinds: {', '.join(known_ref_kinds())}"
            )
        lawful = known_ref_kinds()
        if kind not in lawful:
            sys.exit(
                f"ledger append refused: --ref {raw!r} names the kind {kind!r}, which this "
                f"factory does not declare. Kinds: {', '.join(lawful)}. A new kind is "
                f"DECLARED, not invented: add it to the `kinds` list in "
                f"docs/ledger-refs-kinds.json (a factory's own file; nothing in this module "
                f"changes)"
            )
        refs.append({kind: value})
    return refs

# Which declared invariant's boundary governs a correction to a row of each event. Only
# `close` has one: `close_row_revision` is the sole declared invariant constraining a row's
# DETAIL. An event with no entry is REFUSED rather than repaired under some other
# invariant's boundary — a boundary that does not govern the row cannot make a correction
# lawful, it only makes it look lawful (#87).
INVARIANT_FOR_EVENT = {"close": "close_row_revision"}
# Overridable so the gate can be tested against a throwaway ledger. Tests that
# write the real state surface are how a probe becomes permanent corruption.
LEDGER = Path(os.environ.get("OC_LEDGER_PATH", REPO / "evidence" / "ledger.jsonl"))

def _git_common_dir() -> Path:
    """The repository's COMMON git dir — the same path from every linked worktree.

    `--path-format=absolute` is load-bearing, not decoration: without it the main
    checkout answers the RELATIVE `.git` while a linked worktree answers an absolute
    path, so the two would still not agree on a file. The ledger is a REPOSITORY
    surface and a checkout is a private view of it, so this — not the checkout — is
    the boundary a single-writer lock belongs at (#222).

    Any failure falls back to the LEDGER'S OWN DIRECTORY -- never `REPO/.git`,
    which does not exist in exactly the case that reaches the fallback (a scratch
    fixture, or a box without git) and made the lock raise FileNotFoundError before
    the append could fail open. The caller creates that directory immediately before
    taking the lock, so the anchor always has a home.
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=REPO, capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common = Path(proc.stdout.strip())
            if common.is_dir():
                return common
    except (OSError, subprocess.SubprocessError):
        pass
    # A non-git fixture and a box without git both land here. `REPO/.git` is
    # absent in that case by definition, so the ledger's own directory is the
    # only anchor that exists. It is per-checkout, which is correct: with no
    # repository there is no other checkout to serialize against.
    return LEDGER.parent

# The lock is taken against the COMMON git dir, so two checkouts of one repository
# serialize on one file -- and against the ledger's own directory when there is no
# git dir at all, which is the only anchor that exists for a plain-file factory.
# A per-checkout lock still lets two checkouts mint the same
# `n` -- measured 2026-09-28, twice inside four minutes (#222). The anchor is NOT
# sufficient alone: it serializes writers that reach different FILES, so it is the
# precondition for the freshness leg below rather than a substitute for it.
LOCK = _git_common_dir() / "opencrabs-ledger.lock"

# The freshness leg (#221). `read_committed_rows` judges the working file against a
# ref only as fresh as the last fetch, so a peer's push inside that window is
# INVISIBLE: the guard compares against a lineage that has been superseded and the
# next append re-issues a committed `n`. One command answers whether the ref we
# judged against is still the remote's tip, and it has no side effect.
#
# A FETCH IS DELIBERATELY NOT USED. A fetch inside the append lock mutates the
# working tree's refs as a side effect of a write -- a second-writer act in the
# terms of SKILL.md §State — every surface has one writer -- and makes an append network-bound on a box where
# several lanes append within minutes. A refusal costs the caller one fetch and
# tells it why.
_GIT_TIMEOUT = 10
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
# there and not here because these constants must MATCH EVERYWHERE: a lane that
# only one factory has cannot sit in a shared constant, whatever any given copy
# does with the file. (This file is not standalone either -- see the module
# docstring's "The unit you are copying".)
ACTORS = ("hq", "triage", "worker", "carrier", "owner")
ACTORS_FILE = Path(os.environ.get("OC_ACTORS_PATH", Path(__file__).with_name("actors.txt")))


def known_actors() -> tuple[str, ...]:
    """The core actors, plus any this factory declares.

    Two declaration surfaces, and they answer the two halves of one question: `tools/actors.txt`
    names the lanes this factory has, and `docs/ledger-authorizations.json` names what each may
    write. A malformed authorization declaration RAISES rather than reading as none — a
    declaration that fails to load must never pass quietly.
    """
    extra: list[str] = []
    if ACTORS_FILE.exists():
        for line in ACTORS_FILE.read_text(encoding="utf-8").splitlines():
            role = line.split("#", 1)[0].strip()
            if role:
                extra.append(role)
    declared, _ = load_authorizations(REPO)
    extra.extend(declared)
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


def writing_session_id() -> str | None:
    """The writing lane's session id, VERBATIM from `OPENCRABS_SESSION_ID`.

    docs/instruments/ledger.md §2 declares `session` a ROW KEY — "the row carries both" — because a role is the
    CAPACITY a write was made in and two lanes can share a capacity, so a role alone
    cannot trace a row to the lane that wrote it. The fleet paid for that twice: 246 of
    1322 meta rows paste a uuid into free-text `detail`, and one inferhub row put a
    uuid in the `actor` field itself, which is why the matrix cannot bind that row.

    It is read VERBATIM and never resolved — deliberately the opposite of
    `session_to_role` above. Resolution is the lossy step: a session the registry
    cannot place still WROTE the row, and dropping it is exactly how that row becomes
    untraceable.

    Returns None when the variable is unset, which is the honest answer for a write
    made outside a lane. The caller then OMITS the key rather than inventing one: a
    fabricated identity is worse than a missing one, because only the missing one is
    visibly missing.
    """
    return (os.environ.get("OPENCRABS_SESSION_ID") or "").strip() or None


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

def _git_out(*args: str) -> str | None:
    """stdout of `git ...` in REPO, or None when git could not answer at all."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=_GIT_TIMEOUT
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout

def _ledger_rel_path(path: Path) -> str | None:
    """`path` relative to the repository, or None when it lies outside it.

    This is the discriminator both legs below hang on, and getting it wrong is how
    a guard starts refusing lawful writes: a ledger OUTSIDE the repository has no
    committed lineage in it -- there is nothing to be stale about and nothing to
    fail to read -- so both legs are skipped for one. The gate suite drives
    throwaway ledgers under /tmp, which is exactly that case.
    """
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return None

def _git_config_path() -> Path | None:
    """The repository's git CONFIG, resolved WITHOUT running git (#237).

    This exists because the question below -- "is a remote configured?" -- is asked
    precisely when a git read has already failed, so it must not be another git call.
    Measured: with git unreachable, `git remote get-url origin` returns None exactly
    like "no remote configured" does, so a probe built on that would answer "proceed"
    in the one case the refusal exists to catch.

    A plain file read covers every shape: `.git` is a directory in the main checkout,
    and a FILE in a linked worktree naming the per-worktree gitdir, whose `commondir`
    names the shared directory the config actually lives in. Measured on all four
    shapes (main checkout, linked worktree, no-remote repository, non-repository).
    """
    dot_git = REPO / ".git"
    if dot_git.is_dir():
        return dot_git / "config"
    if not dot_git.is_file():
        return None
    try:
        text = dot_git.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = (REPO / gitdir).resolve()
    common = gitdir / "commondir"
    if common.is_file():
        try:
            target = Path(common.read_text(encoding="utf-8").strip())
        except OSError:
            return None
        if not target.is_absolute():
            target = (gitdir / target).resolve()
        return target / "config"
    return gitdir / "config"

def _remote_configured() -> bool:
    """Whether a remote named `origin` is configured, read from the CONFIG FILE.

    The discriminator the freshness leg's two outcomes hang on: no `origin` = there is
    nothing for this guard to be stale against (proceed); `origin` present = there is,
    and a failed read is a refusal. It answers even when the binary that would have
    reported it does not, which is exactly when it is asked (#237).

    Named `origin` and not "any remote", because `origin` is the ref this guard reads:
    a factory with only `upstream` has no `origin/main` to compare against and would be
    refused forever by a broader predicate.
    """
    config = _git_config_path()
    if config is None:
        return False
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return '[remote "origin"]' in text

def _unread_refusal(what: str) -> str:
    """The UNREAD refusal: a remote exists and the read failed (#237).

    Distinct from the stale refusal on purpose. "I looked and the ref had moved" and
    "I could not look" have different remedies, and only the first is about a peer.
    """
    return (
        f"{what}, and a remote IS configured: there is a committed lineage to judge "
        f"against and this guard could not read it. That is the UNREAD case, not the "
        f"fresh one -- minting the next n from a lineage it could not confirm is what "
        f"the single-writer guard exists to prevent. Run `git fetch origin` and retry. "
        f"(A refusal and not a fetch on purpose: fetching inside the append lock would "
        f"rewrite origin/* as a side effect of a write, and would make an append "
        f"network-bound.)"
    )

def stale_ref_refusal(path: Path) -> str | None:
    """A refusal when the ref we are about to judge against is not the remote's tip.

    ONE command decides it, and it has no side effect: `git ls-remote` asks the
    remote, `git rev-parse` asks the local ref, and a difference means the lineage
    `read_committed_rows` is holding has been superseded by a peer's push.

    The UNREAD case is NOT the fail-open case, and telling them apart is the whole fix
    (#237). "No remote is configured" means there is nothing to compare against, so the
    append proceeds. "A remote IS configured but the ref read failed" means there is
    something to compare against and this guard could not read it, so the append is
    REFUSED. Both used to return the same None, so no caller could tell "I verified this
    lineage" from "I could not look" -- and on the second the append minted the next n
    from a lineage it had not confirmed. A fresh factory with no remote keeps its
    carve-out, and now says so out loud.
    """
    if _ledger_rel_path(path) is None:
        return None
    remote = _git_out("ls-remote", "origin", "main")
    if remote is None:
        if _remote_configured():
            return _unread_refusal("the remote's tip could not be read")
        # THE CARVE-OUT ANNOUNCES ITSELF: a run that did not check freshness must not
        # be byte-identical to one that did.
        sys.stderr.write(
            "warning: ledger guard: no remote configured -- freshness NOT checked "
            "(fail-open: there is no committed lineage to be stale against)\n"
        )
        return None
    if not remote.strip():
        # A remote that ANSWERED and carries no `main` yet: a factory's first push.
        # There is nothing committed there to be stale against, so this is the
        # carve-out -- and `ls-remote` ANSWERING is what tells it apart from the
        # unread case above. (Reading this as unread refused every first append in a
        # factory whose remote exists but is empty: measured, and caught by the
        # (222a) probe, which is the shape the gate exists to drive.)
        return None
    local = _git_out("rev-parse", "origin/main")
    if local is None:
        # The remote carries a `main` and this checkout has no local ref for it, so
        # the lineage cannot be judged at all. `git fetch origin` is the remedy, named
        # rather than run: a fetch inside the lock is network-bound and would rewrite
        # origin/* as a side effect of a write.
        return _unread_refusal("the local 'origin/main' ref could not be read")
    remote_sha = remote.split()[0] if remote.split() else ""
    if not remote_sha or remote_sha == local.strip():
        return None
    return (
        f"the local 'origin/main' ref ({local.strip()[:12]}) is not the remote's tip "
        f"({remote_sha[:12]}): the committed lineage just compared is STALE, so a peer's "
        f"push may already have taken the next n. Run `git fetch origin` and retry. "
        f"(A refusal and not a fetch on purpose: fetching inside the append lock would "
        f"rewrite origin/* as a side effect of a write, and would make an append "
        f"network-bound.)"
    )

def read_committed_rows(path: Path) -> tuple[list[dict] | None, str | None, str | None]:
    """The rows the repository has COMMITTED for `path`, and the ref they came from.

    (None, None, None) means no committed lineage was readable — a fresh factory with
    no commits, no remote, or a file that is not tracked. The caller treats that
    as fail-open: the guard makes a revert loud, it never blocks a factory that
    has nothing to compare against.

    (None, None, "unreadable") is the OTHER case: a remote exists, so there IS a
    lineage to compare against and we failed to read it. The caller REFUSES on that,
    because a guard that cannot see committed history is not a guard.
    """
    # THE TWO CASES ARE NOT THE SAME FACT, and until now both wrote the same stderr
    # warning (#221 Q3):
    #
    #   (1) no remote, no commits -- a genuinely fresh factory. There is NOTHING to
    #       compare against, so fail-open is correct and stays.
    #   (2) a remote EXISTS but the lineage could not be read. There IS something to
    #       compare against and we did not read it. That is REFUSED, by name.
    #
    # A stderr warning is not a reader: it is invisible on every surface this factory
    # reads, so case (2) was indistinguishable from case (1) to everyone but the caller.
    rel_path = _ledger_rel_path(path)
    if rel_path is None:
        return None, None, None
    # The SAME discriminator the freshness leg uses (#237): a file read, so it
    # answers even when git does not. `tracked` below still needs git, and that is a
    # stated bound rather than a hole -- with git unreachable the freshness leg
    # refuses first, so this branch is never reached in that arm.
    has_remote = _remote_configured()
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
            return rows, ref, None
        break
    # Reaching here means no ref yielded the file. The two cases are distinct:
    #   UNTRACKED -- nothing was ever committed for it, so there is nothing to
    #                compare against: fail-open, as a fresh factory deserves.
    #   TRACKED but unreadable while a remote exists -- committed history EXISTS
    #                and we failed to read it. That is refused.
    tracked = _git_out("ls-files", "--error-unmatch", rel_path) is not None
    if has_remote and tracked:
        return None, None, "unreadable"
    sys.stderr.write("warning: ledger guard: cannot read committed lineage (proceeding fail-open)\n")
    return None, None, None

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
    by_subject: dict[str, list[tuple[int, str]]], subject: str, index: int,
    event: str = "close",
) -> list[tuple[str, str, str]]:
    """What a `close` — or a `claim` — of `subject` at `index` is missing.

    ONE predicate, and TWO events x TWO call sites. `verify` asks it about every
    close row it reads AND every claim row; `append` asks it about the row it is
    about to write, with `index = len(rows)` — the line that row will occupy — so
    the refusal names the leg the audit would have named later, at the moment the
    write would have created the defect. The close leg is bounded by the *latest*
    intake before the close, so a re-opened subject must be re-claimed after its
    re-open.

    WHY A CLAIM IS CHECKED AT ALL (#137 half 2, the reporter's diff). `close` was
    the only event the sequence predicate ever looked at, so a `claim` whose
    subject had no `intake` ANYWHERE was invisible: `verify` read GREEN while the
    ledger was already defective, and the defect surfaced hours later when someone
    tried to close. Measured by the reporting factory at their ledger 257 rows:
    `verify` returned 0 problems while this leg named a claim with no intake,
    about nine minutes before the close that turned the gate red. A claim is work
    being taken, and work cannot be taken on a subject the ledger never admitted.

    WHY THE CLAIM LEG IS "anywhere" AND NOT "before it". A late-reconstruction
    intake lands AFTER the original claim by design, so a positional claim
    predicate would re-flag the very repair it exists to prompt. The CLOSE leg
    keeps its positional form, because a close could not have been lawful on the
    row it occupies unless its subject was admitted by then.

    WHY NOT A `dispatch` LEG (measured, not assumed). Three legacy subjects carry
    a dispatch and no intake and none has a claim or a close, so a dispatch-keyed
    leg fires false positives on rows that are not defective. The dispatch leg is
    a SEPARATE predicate with its own three classifications; see below.

    Each missing leg is reported INDEPENDENTLY, with no short-circuit: one pass
    should tell the reader everything that is absent, not the first thing the
    predicate happened to notice.
    """
    if not subject:
        return []  # a missing subject is a structural problem, reported as one

    legs = by_subject.get(subject, [])
    # A CLAIM's intake is looked for ANYWHERE, never only before it: the intake it
    # needs may be a late reconstruction that landed after it by design (#137 half
    # 2). A CLOSE's legs stay positional — a close could not have been lawful on
    # the row it occupies unless its subject was already admitted by then.
    # `j` is a GLOBAL ledger index, never a position within `legs`: bounding it by
    # `len(legs)` compares an index against a length and silently misses every
    # intake on the ledger's early rows (the reporting factory measured 39 false
    # positives at 270 rows from exactly that).
    if event == "close":
        intakes = [j for j, ev in legs if ev == "intake" and j < index]
    else:
        intakes = [j for j, ev in legs if ev == "intake"]
    claims = [j for j, ev in legs if ev == "claim" and j < index]

    problems: list[tuple[str, str, str]] = []
    if not intakes:
        tail = " before it" if event == "close" else " anywhere in the ledger"
        problems.append((subject, "intake",
            f"line {index + 1}: {event} for {subject} has no intake{tail}"))
    # The claim leg is a CLOSE leg only: a `claim` row IS its own claim, so asking
    # a claim for a claim would report every claim in the ledger against itself.
    if event == "close" and not claims:
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

# --- the dispatch leg (#45, ruling n=255, refined n=524) ------------------------
#
# `verify` modelled a subject's life as intake -> claim -> close, and `dispatch` was not
# a leg of that model at all. Nothing asserted that a subject was FILED before it was
# ROUTED, so the ledger could answer "this was dispatched" for a subject it could not
# answer "was this ever taken in?" for.
#
# THREE classifications, and the split is the ruling's own (n=524), taken because a
# binary split certified a row it could not see:
#
#   (1) a strict `#<n>` subject  — a WORK-UNIT handoff. That subject's intake must
#       precede the dispatch, or the route promises a filing that never happened.
#   (2) a descriptive stem       — an observation dispatch, EXPLICITLY LEGAL. These are
#       not work-unit handoffs and sit outside the ordering leg entirely.
#   (3) a BARE or HASH-LED form that is not strict (`77`, `# 12`, `#12a`) — a DEFECT IN
#       THE ROW: a work-unit dispatch was INTENDED and its subject cannot be resolved by
#       any subject-keyed predicate. REPORTED and named, never gated: the row's identity
#       is immutable once pushed (#52 clause 1), so only a NEW row can repair it.
#
# FORWARD-ONLY, WITH A DECLARED BOUNDARY — and the boundary is a measured decision, not
# a convenience. The law ("a work-unit dispatch promises the subject was filed") has
# never been enforced, so every historical instance is PRE-GATE by construction, and the
# measured population is 28, not the 2 the ruling knew: their gaps run 0.3 min to
# 276.7 min with NO SEAM that could separate a same-turn race from a genuine
# routing-before-filing. An EXEMPTIONS entry is admitted by an EXTERNAL RECEIPT
# (n=620), so 28 entries would mean inventing 26 receipts that do not exist. The
# boundary excuses and PRINTS the historical population instead — never backfilled, and
# never by weakening the leg (the #190 pattern).
DISPATCH_LEG_BOUNDARY = "2026-09-27T16:22:43Z"
def is_work_unit(subject: str) -> bool:
    """A STRICT `#<n>` subject — a hash, then digits, then nothing else.

    Deliberately not a regex: the test is three predicates over a short string, and
    `tools/ledger.py` carries no `re` import for good reason — this module must run
    wherever the ledger runs, and a regex engine is one more dependency on that path.
    `#12a`, `# 12` and `#332-D5` all fail it, which is the point: they are neither a
    work unit nor a descriptive stem, and class (3) of the ruling exists for them.
    """
    return len(subject) > 1 and subject[0] == "#" and subject[1:].isdigit()


def dispatch_problems(
    rows: list[dict], by_subject: dict[str, list[tuple[int, str]]],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, int]], list[tuple[str, int, str]]]:
    """(problems, malformed, excused) for the dispatch leg — PURE over the row list.

    Returned as three populations rather than one verdict, because they are three
    different facts: a post-boundary ordering defect (a problem), a row whose subject
    cannot be resolved (a report), and a pre-boundary instance (a visible debt printed
    as an `excused:` line). Collapsing them would make the report of an unrepairable
    row indistinguishable from a defect the lane could fix.
    """
    problems: list[tuple[str, str, str]] = []
    malformed: list[tuple[str, int]] = []
    excused: list[tuple[str, int, str]] = []
    for i, row in enumerate(rows):
        if row.get("event") != "dispatch":
            continue
        subject = str(row.get("subject") or "").strip()
        if is_work_unit(subject):
            precedes = any(
                ev == "intake" and j < i for j, ev in by_subject.get(subject, [])
            )
            if precedes:
                continue
            ts = str(row.get("ts") or "")
            if ts and ts < DISPATCH_LEG_BOUNDARY:
                excused.append((subject, i + 1, ts))
                continue
            problems.append((subject, "dispatch",
                f"line {i + 1}: dispatch of {subject} has no intake before it — a "
                f"work-unit dispatch promises the subject was filed, and the board has "
                f"no record of this one being taken in"))
        elif subject and (subject[0].isdigit() or subject[0] == "#"):
            malformed.append((subject, i + 1))
    return problems, malformed, excused


# THE LEXICAL BRANCH OF A DECLARATION GUARD IS A NOTE, NEVER A REFUSAL (#247).
#
# Both declaration guards below (`reclose` on `close`, `reclaim` on `claim`) ask two
# questions: does this detail DECLARE the token, and does it merely MENTION it? The
# second is lexical by construction — `mentions_*` asks whether any whitespace-separated
# token starts with the key — and it was given ENFORCEMENT powers it never needed. Its
# own purpose statement is a MESSAGE ("a malformed declaration is NAMED, never silently
# ignored"), and enforcement is what made it refuse a row that duplicates nothing: a
# FIRST row that merely documents or quotes the convention, with no prior row to answer,
# was refused and then told to write the token it was already discussing.
#
# THE PROTECTION IS STRUCTURAL, NOT ARGUED. `prior_closes` / `prior_claims` sit inside
# the SAME `if` and run AFTER the lexical branch, and a re-entry declaration is only
# meaningful against a prior row. So demoting the branch loses no refusal: a first row
# quoting the token is ADMITTED, and a second same-actor row declaring nothing is still
# refused by the prior-row leg — whose message now carries the malformation note too, so
# an author who DID mean to declare still learns why their token did not take.
#
# THIS IS THE INVERSE OF #215, and the pair names a clause that was unwritten. #215: a
# lexical test let a row that REFUSES the token PASS — a false clean. This: a lexical
# test REFUSES a row that merely QUOTES the token — a false refusal. Both are a lexical
# test used as a semantic predicate, and only one direction was stated ("prose must not
# SATISFY a field"); its mirror is "prose must not VIOLATE a field".
#
# THE NOTE STATES BOTH LAWFUL RESPONSES, because the old message prescribed one for a
# situation with two: declaring the token in ONE TOKEN, or leaving the prose alone when
# this is not a second row for the same actor. It is printed to STDERR so it never
# pollutes the row line a caller parses from STDOUT.
_RECLOSE_NOTE = (
    "ledger append note: this detail carries a bare `reclose=` token that is NOT a "
    "declaration — a value containing a space TERMINATES the canonical trailing run, so "
    "the token sits outside the run every trailer-scoped reader stops at. TWO lawful "
    "responses, and only the author knows which applies: (a) if this IS a second close "
    "of a re-opened subject, write `reclose=<one-token>` and keep the explanation in the "
    "detail's prose; (b) if it is NOT — the detail merely documents or quotes the "
    "convention — the prose is fine and NOTHING IS OWED. This row is admitted unless the "
    "prior-close leg below refuses it (#247)."
)

_RECLAIM_NOTE = (
    "ledger append note: this detail carries a bare `reclaim=` token that is NOT a "
    "declaration — a value containing a space TERMINATES the canonical trailing run, so "
    "the token sits outside the run every trailer-scoped reader stops at. TWO lawful "
    "responses, and only the author knows which applies: (a) if this IS a second claim "
    "of the same subject by the same actor, write `reclaim=<one-token>` and keep the "
    "explanation in the detail's prose; (b) if it is NOT — the detail merely documents or "
    "quotes the convention — the prose is fine and NOTHING IS OWED. This row is admitted "
    "unless the prior-claim leg below refuses it (#247)."
)

def _malformation_sentence(key: str) -> str:
    """The note a PRIOR-ROW REFUSAL carries when the same detail was also malformed.

    The two branches are now separated, so the refusal must restate the malformation
    rather than assume the reader saw the note above it: a detail can carry a bare
    `reclaim=` token AND be a second same-actor claim, and then BOTH facts are true and
    the author needs both. Kept as one function so the two ends cannot drift.
    """
    return (
        f" NOTE: this detail ALSO carries a bare `{key}=` token that is NOT a "
        f"declaration — its value must be ONE token (no spaces), because a value "
        f"containing a space TERMINATES the canonical trailing run and the token then "
        f"sits outside the run every trailer-scoped reader stops at. Write "
        f"`{key}=<one-token>` if you meant to declare."
    )

def cmd_append(args: argparse.Namespace) -> int:
    if args.event not in known_events():
        sys.exit(
            f"unknown event '{args.event}' — one of: {', '.join(known_events())}. "
            f"A member's own event is DECLARED in docs/ledger-refs-kinds.json "
            f"(\"events\": [\"{args.event}\"]) rather than added to the core tuple."
        )
    # Refuse a malformed ref BEFORE the lock is taken: a write path that acquires the
    # lock and then rejects its own arguments has serialised a lane against nothing.
    refs = parse_refs(getattr(args, "ref", []) or [])
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

    # docs/instruments/ledger.md §2's SECOND identity key, and the one the role cannot carry. A role is the
    # CAPACITY a write was made in, and two lanes can share a capacity, so a role alone
    # cannot trace a row to the lane that wrote it. Read VERBATIM and never resolved:
    # resolution is the lossy step, and a session the registry cannot place still WROTE
    # the row.
    #
    # FIXTURE writes carry none. A fixture is not a live lane, and stamping the test
    # runner's session into a fixture row would make that row's identity depend on WHO
    # RAN THE SUITE — the same suite would produce different bytes for different runners.
    # A live write omits it too when the variable is unset, which is the honest answer
    # for a write made outside a lane.
    session_id = None if fixture else writing_session_id()
    # THE MATRIX BINDS A LANE, NOT A FIXTURE. It answers "is this ROLE allowed to
    # write this EVENT", and a fixture-declared actor has no row in it because a
    # fixture is not a lane — the pinned vocabulary in `probe_actors_path` is the
    # whole point of that seam. A derived role always has a row, because the
    # derivation resolves through the same registry the matrix is written for.
    # The composed predicate lives in ONE home, because the schema gate reads it too: while
    # the two held separate copies a declared authorization would pass here and red there.
    authorized = authorized_for_event(REPO, args.event)
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
        stale = stale_ref_refusal(target_ledger)
        if stale:
            sys.exit(f"ledger append refused: {stale}")
        committed_rows, ref_name, unreadable = read_committed_rows(target_ledger)
        if unreadable:
            sys.exit(
                "ledger append refused: this repository HAS a remote but its committed "
                "lineage for the ledger could not be read, so the single-writer guard "
                "cannot see what is already committed. Run `git fetch origin` (and check "
                "the ledger is tracked) and retry. Fail-open is for a factory with "
                "nothing to compare against, not for one that failed to look."
            )
        if committed_rows is not None:
            divergence = lineage_divergence(rows, committed_rows, ref_name)
            if divergence:
                sys.exit(f"ledger append refused: {divergence}")
        # A REF MUST RESOLVE AT THE INSTANT IT IS WRITTEN, and this lock is the only
        # place the check is cheap: the ledger's maximum `n` is a fact THIS lock
        # already holds, three lines above, so the predicate costs one comparison.
        # Checked here rather than at read time because a dangling pointer is
        # cheapest to kill before it exists -- `verify` is the second half of this
        # leg, not a substitute for it: only read time can see a ref that was valid
        # when written and broken afterwards, and only write time can prevent one.
        _max_n = rows[-1]["n"] if rows else 0
        for _ref in refs:
            for _kind, _value in _ref.items():
                if _kind != "row":
                    continue
                if not str(_value).isdigit():
                    sys.exit(
                        f"ledger append refused: ref row:{_value!r} is not a row "
                        f"number"
                    )
                if int(_value) > _max_n:
                    sys.exit(
                        f"ledger append refused: ref row:{_value} points at a row "
                        f"that does not exist -- this ledger holds {_max_n} row(s), "
                        f"and a ref is a pointer to something, never a wish"
                    )
        # A RELEASE MUST NAME THE CLAIM IT WITHDRAWS (#210, ruling n=1577). The body
        # offered a withdrawal wearing a `close`, and that shape is REFUSED: `close`
        # means COMPLETION here, its contract carrying the board state observed,
        # `head=<sha>` and a rework disposition, so a withdrawal dressed as a close
        # asserts a completion that never happened (the false-clean class) and would
        # satisfy the intake+claim sequence while meaning the opposite. So the
        # transition is its own event, DECLARED locally in `ledger-refs-kinds.json`
        # rather than widened into the core tuple, and the row POINTS AT the claim it
        # terminates -- a release naming no claim is indistinguishable from an intake,
        # and the claim it was meant to withdraw stays open forever, so the ledger
        # cannot answer "withdrawn, or still in flight?". Asked HERE, beside the other
        # ref predicates, because the rows list is already in hand under the lock and
        # only write time can prevent a release that names nothing.
        if args.event == "release":
            released_ns = [
                int(value) for _ref in refs for kind, value in _ref.items()
                if kind == "row" and str(value).isdigit()
            ]
            if not released_ns:
                sys.exit(
                    "ledger append refused: a 'release' must name the claim it "
                    "withdraws as a ref of kind 'row' (--ref row:<n>). A release "
                    "naming no claim is indistinguishable from an intake, and the "
                    "claim it was meant to withdraw stays open forever"
                )
            for _n in released_ns:
                _target = next((r for r in rows if r.get("n") == _n), None)
                if _target is None:
                    sys.exit(
                        f"ledger append refused: release names row n={_n}, which "
                        f"this ledger does not hold"
                    )
                if _target.get("event") != "claim":
                    sys.exit(
                        f"ledger append refused: release names row n={_n}, whose "
                        f"event is {_target.get('event')!r} -- a release withdraws a "
                        f"CLAIM, and a claim is the only row it can terminate"
                    )
                # A SECOND RELEASE OF ONE CLAIM IS REFUSED, AND THE REFUSAL NAMES THE
                # RELEASE THAT LANDED -- #213's class on a brand-new event: `append` is
                # not idempotent, so a client-side timeout on a COMPLETED write leaves
                # the caller with no output, and a caller reading "no output" as "the
                # write did not happen" retries and mints a duplicate. Measured four
                # times on `close` in one day before that refusal landed. The same
                # predicate, the same remedy: name the row that landed, so the writer
                # learns its first write succeeded.
                _prior = [
                    r for r in rows
                    if r.get("event") == "release"
                    and any(str(ref.get("row")) == str(_n)
                            for ref in (r.get("refs") or []))
                ]
                if _prior:
                    _p = _prior[-1]
                    sys.exit(
                        f"ledger append refused: claim n={_n} already carries a "
                        f"release at n={_p.get('n')} ({_p.get('ts')}). A claim is "
                        f"released once; a second release is either a deliberate "
                        f"re-release, which is a new claim, or a DUPLICATE minted by "
                        f"retrying an append that had already completed (#213)"
                    )
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
        # A `close` AND a `claim` are both refused at the WRITE PATH when the row
        # about to be written would create an incomplete sequence — the SAME
        # predicate `verify` runs, asked here with `index = len(rows)`, the line it
        # will occupy. A claim whose subject was never admitted anywhere in the
        # ledger is invisible to a close-keyed reading until the close fails
        # (#137 half 2), so the leg is asked of the claim itself. The predicate
        # phrases the message for the event that triggered it — `claim` stays
        # `claim`.
        # THE `claim` KEY IS SINGLE-VOCABULARY (#249, ruling `n=1792`). `claim` has exactly
        # ONE lawful value in this factory — `claim=reconstructed`, the declaration a lane
        # writes when it stamps a claim row AFTER its first edit and must say so
        # (`tools/reconstruction.py:31`; the only reader is `declares_token(..., "claim",
        # "reconstructed")`, and a grep over `tools/*.py` and `tests/*.py` finds NO reader
        # of any other value). The law has stood since #98, ruled at ledger `n=602`.
        #
        # MEASURED, through the shared predicate over all 1794 rows of
        # `evidence/ledger.jsonl`: THREE rows put something else in it — `n=1754` and
        # `n=1755` (`claim=#220`), `n=1767` (`claim=#239`) — each an author-typed ECHO of
        # the row's own `subject`, which every row already carries as a first-class field.
        # So `claim=#220` is not a second vocabulary in the sense of two readers
        # disagreeing; it is a NON-DECLARATION SQUATTING ON A DECLARATION KEY. The filing's
        # own framing — "the repair path cannot reach such a row" — was ruled against on
        # that measurement: the repair path is CORRECT, and the defect is UPSTREAM of it.
        #
        # THE DAMAGE IS THE REPAIR SPACE, and it is why this belongs at the write path
        # rather than in a reader. `repair --append-detail` refuses to give a key a second
        # value (#104, ruled at ledger `n=620` PART 4 — one field carrying two values has
        # no canonical reading, so a consumer taking the first or the last gets a different
        # answer). So the ONE repair that would make such a row lawful is unreachable from
        # the moment the squat is written. HQ drove it on a detached copy: `repair --n 1754
        # --invariant close_row_revision --note probe --append-detail "claim=reconstructed"`
        # returns rc=1 and leaves the ledger byte-identical. Refusing the squat when it is
        # TYPED is what stops the trap being created again; it cannot reach a row already
        # written, and it is not meant to — see the no-backfill clause below.
        #
        # THE LAWFUL HOME ALREADY EXISTS: `--ref subject:#N`. `CORE_REF_KINDS` carries
        # `subject` and `--ref KIND:VALUE` is repeatable, so a row that wants to point at a
        # subject has a typed, followable edge instead of a hijacked declaration key.
        #
        # EVENT-AGNOSTIC, AND THE SCOPE IS STATED RATHER THAN IMPLIED. The ruling's sentence
        # is "an append whose canonical trailer declares claim=<anything but reconstructed>",
        # and the hazard is a property of the KEY, not of the event that carries it: a squat
        # on ANY row empties that row's repair space, and `repair` reaches a sub-ledger as
        # readily as the main one. The same 1794-row scan finds `claim=` in the canonical
        # trailer of NO event other than `claim` (28 declaring `reconstructed`, the 3 above),
        # so the wider scope reaches no history it would have to excuse.
        #
        # NO BOUNDARY AND NO EXEMPTION SURFACE, for the reason the sibling refusals state:
        # this binds the row about to be written, so it can never predate itself. The three
        # rows stand UNREPAIRED and are NOT backfilled — they are ordinary pre-first-edit
        # claims, not reconstructions, needing no token, with nothing reading their value —
        # and a row that already carries the collision re-enters by the designed path
        # (#246): `reclaim=<reason>` plus a fresh row.
        #
        # THE READ IS THE SHARED PREDICATE (`declared_claim`), never a private scan: one
        # field, one predicate (`n=405` PART 5, `n=599`). It is POSITIONAL — the canonical
        # trailer — because `detail` is free prose that QUOTES trailers as evidence, and a
        # whole-detail scan takes a quotation for a declaration. That is not hypothetical in
        # this file's own history: this lane's #247 close row (`n=1785`) counted eight prose
        # quotations as eight declarations and put a false population into a durable record,
        # corrected forward-only at `n=1790` (the #99 class).
        _unlawful_claims = [value for value in declared_claim(args.detail)
                            if value != RECONSTRUCTION_VALUE]
        if _unlawful_claims:
            sys.exit(
                f"ledger append refused: this detail's canonical trailer declares "
                f"`{RECONSTRUCTION_KEY}` with a value outside its single lawful "
                f"vocabulary ({', '.join(repr(v) for v in _unlawful_claims)}). "
                f"`{RECONSTRUCTION_KEY}` has exactly ONE lawful value, "
                f"`{RECONSTRUCTION_KEY}={RECONSTRUCTION_VALUE}` — the declaration a claim "
                f"row writes when it is stamped AFTER its first edit (#98, ruled at ledger "
                f"n=602) — and any other value OCCUPIES the key, which empties the row's "
                f"repair space: `repair --append-detail` refuses to give a key a second "
                f"value (#104). A SUBJECT POINTER IS NOT A CLAIM: it belongs in "
                f"`--ref subject:#N`, a typed edge that is first-class on every row and "
                f"repeatable, and the row's own `subject` field already carries it (#249)."
            )
        if args.event in ("close", "claim") and target_ledger == LEDGER:
            problems = sequence_problems(
                index_by_subject(rows), args.subject, len(rows), args.event)
            if problems:
                sys.exit("ledger append refused: "
                         + "; ".join(message for _subject, _leg, message in problems))
            # A SECOND CLOSE FOR ONE SUBJECT IS REFUSED, AND THE REFUSAL NAMES THE
            # EXISTING ROW (#213). The job is not tidiness: `append` is not idempotent,
            # so a client-side timeout on a COMPLETED write leaves the caller with no
            # output, and a caller that reads "no output" as "the write did not happen"
            # retries and mints a byte-equivalent duplicate. Measured 4 times in one
            # day (`#140` n=930/931, `#169` n=1361/1363, `#202` n=1502/1504,
            # `#84` n=1509/1511), and `verify` was CLEAN over every one of them —
            # the sequence leg looks for PRESENCE of a close, never for a second one.
            #
            # SO THE REFUSAL CARRIES THE ANSWER THE RETRYING WRITER NEEDED: it prints
            # the existing row's `n` and `ts`, which is the one fact that tells that
            # writer its first write landed. A refusal that merely said "already
            # closed" would leave the same ambiguity the timeout created.
            #
            # RE-ENTRY IS DECLARED, NOT IMPLIED, and it uses the idiom this ledger
            # already carries (`claim=reconstructed`, `head=<sha>`): a deliberate
            # re-close states `reclose=<reason>` in its own detail. Measured: two of
            # the six multi-close subjects (`#22` n=95/125, `#26` n=118/135) are
            # genuine re-closes hours apart by different actors, so a blanket
            # one-close-per-subject rule would have been wrong -- the declaration is
            # what separates a re-open from a retry.
            #
            # NO BOUNDARY AND NO EXEMPTION SURFACE, for the reason the two refusals
            # above state: this binds the row about to be written, so it can never
            # reach history. EXEMPTIONS govern `verify`'s reading of history only.
            if args.event == "close" and not declared_reclose(args.detail):
                # A MALFORMED DECLARATION IS NAMED, NEVER SILENTLY IGNORED -- and
                # NAMING it is all this branch does (#247). A `reclose` value
                # containing a SPACE terminates the canonical trailing run, so the
                # row declares nothing even though its author wrote the token --
                # measured 2026-09-28: the guard prescribed a declaration,
                # `declares_field` could never accept it (it type-tests the value),
                # and once that was fixed a multi-word reason turned out to break
                # the run itself. Two stacked defects reached the shipped tool
                # because the leg had NO behavioural probe.
                #
                # WHAT IT MUST NOT DO IS REFUSE. It fires BEFORE the prior-close leg
                # below and asks a LEXICAL question -- "does any token start with
                # `reclose=`" -- so it refused a FIRST close that merely quoted the
                # convention, with nothing to refuse. The note states the VALUE FORM,
                # the reason, and BOTH lawful responses; the refusal below carries the
                # same fact again for the author who really was declaring (#247).
                if mentions_reclose(args.detail):
                    print(_RECLOSE_NOTE, file=sys.stderr)
                prior_closes = [r for r in rows
                                if r.get("event") == "close"
                                and r.get("subject") == args.subject]
                if prior_closes:
                    last = prior_closes[-1]
                    malformed = (_malformation_sentence("reclose")
                                 if mentions_reclose(args.detail) else "")
                    sys.exit(
                        f"ledger append refused: {args.subject} already carries a close at "
                        f"n={last.get('n')} ({last.get('ts')}). IF THIS IS A RETRY after a "
                        f"timeout, THE FIRST WRITE LANDED -- do not append again. A "
                        f"deliberate re-close (the subject was re-opened) declares itself "
                        f"with `reclose=<one-token>` in its canonical trailer (#213)."
                        f"{malformed}"
                    )
            # A SUBJECT CLAIMED TWICE BY THE SAME ACTOR (#246). `close` has carried all
            # three mechanisms since #213 — a declaration, a write-path refusal and a read
            # leg — and `claim`, the other end of the same lifecycle, carried none of them.
            # Measured at origin 4e142dd: 226 claim rows, 8 subjects with more than one,
            # and `verify` reads rc=0 over every one of them.
            #
            # THE ACTOR SCOPE IS MEASURED, NOT CHOSEN. An actor-blind refusal was refused
            # because it would have blocked the two LAWFUL multi-actor cases in that same
            # population: `#34` (hq takes it, then worker) and `#234` (surveys claims the
            # derivation half, worker the law half). A hand-off and a two-half unit are both
            # correct states, and only a second claim by the SAME actor is the class this
            # answers.
            #
            # RE-ENTRY IS DECLARED, NOT IMPLIED — the idiom this ledger already carries
            # (`reclose=<one-token>`, `claim=reconstructed`, `head=<sha>`). A deliberate
            # re-claim states `reclaim=<reason>` in its own canonical trailer, which is why
            # the token is a FORMALISATION rather than a new burden: three of the eight
            # multi-claim subjects already declare themselves in prose.
            #
            # NO BOUNDARY AND NO EXEMPTION SURFACE, for the reason the two refusals above
            # state: this binds the row about to be written, so it can never reach history.
            if args.event == "claim" and not declared_reclaim(args.detail):
                # A MALFORMED DECLARATION IS NAMED, NEVER SILENTLY IGNORED — and NAMING
                # it is all this branch does (#247), for the reason its `reclose` twin
                # states at length: the lexical question it asks is not the semantic one
                # the refusal below asks, and answering it with a refusal refused a FIRST
                # claim that merely quoted the convention.
                if mentions_reclaim(args.detail):
                    print(_RECLAIM_NOTE, file=sys.stderr)
                prior_claims = [r for r in rows
                                if r.get("event") == "claim"
                                and r.get("subject") == args.subject
                                and r.get("actor") == args.actor]
                if prior_claims:
                    last = prior_claims[-1]
                    malformed = (_malformation_sentence("reclaim")
                                 if mentions_reclaim(args.detail) else "")
                    sys.exit(
                        f"ledger append refused: {args.subject} is already claimed by "
                        f"'{args.actor}' at n={last.get('n')} ({last.get('ts')}). IF THIS IS "
                        f"A RETRY after a timeout, THE FIRST WRITE LANDED -- do not append "
                        f"again. A deliberate re-claim (the work was re-taken, or the intake "
                        f"leg landed after the first claim) declares itself with "
                        f"`reclaim=<one-token>` in its canonical trailer (#246)."
                        f"{malformed}"
                    )
            # AND THE ROW MUST DECLARE THE REVISION ITS RECEIPTS DESCRIBE (#187). The
            # invariant is `close_row_revision`, enforced by
            # `tests/test_close_row_revision.py` and — until this refusal existed — by
            # NOTHING at the write path: four instances in one session were each repaired
            # by a SECOND append (`n=1065`->`n=1079`, `n=1126`->`n=1135`,
            # `n=1258`->`n=1262`, `n=1260`->`n=1263`), and the rate was not falling. This
            # is #157's class one trailer over — a predicate that lived only in a paired
            # test the writer never reads. The invariant is named ONCE, in
            # INVARIANT_FOR_EVENT above, and read from there rather than re-invented.
            #
            # NO BOUNDARY READ HERE, for the reason the sequence refusal above states: a
            # close appended now can never predate the boundary, so the rule reaches every
            # row this path can write. History is the gate's business, and EXEMPTIONS
            # govern the gate's reading of it.
            #
            # THE PREDICATE IS THE CANONICAL RUN, through the shared `declared_revision`
            # and never a whole-detail scan. Three live rows carry `head=` in PROSE only
            # (`n=1077`, `n=1083`, `n=1091`), so a permissive reading would let a writer
            # satisfy this refusal by quoting any hex-shaped token — while the existence
            # leg, which reads the run, never resolves that token at all.
            if (INVARIANT_FOR_EVENT.get(args.event) == "close_row_revision"
                    and declared_revision(args.detail) is None):
                sys.exit(
                    "ledger append refused: a close row must declare head=<sha> in its "
                    "canonical trailer — the revision its receipts describe — and this "
                    "detail declares none. The token is read from the trailing run, so a "
                    "revision mentioned in prose does not satisfy it (#187)."
                )
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
        # ADDITIVE: a row without refs stays valid, so the five forked copies are not
        # broken on day one. The key appears only when there is something to point at.
        if refs:
            row["refs"] = refs
        # ADDITIVE on the same rule: a row written outside a lane carries no `session`
        # and stays valid. docs/instruments/ledger.md §2 declares the key OPTIONAL precisely so the forked member
        # copies are not broken on day one.
        if session_id:
            row["session"] = session_id
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
            # The receipt is a ROW, and docs/instruments/ledger.md §2 makes the key intrinsic to a write rather
            # than conditional on the event: a close written by a lane and receipted by
            # the tool would otherwise lose the lane on exactly the row that settles it.
            if session_id:
                receipt["session"] = session_id
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
    and never edited (SKILL.md §State — every surface has one writer).

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
    # docs/instruments/ledger.md §2's second identity key, on the append path's own rule: a redirected (fixture)
    # target carries none, and an unset variable is omitted rather than invented.
    session_id = None if os.environ.get("OC_LEDGER_PATH") else writing_session_id()
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
        committed_rows, ref_name, unreadable = read_committed_rows(target_ledger)
        if unreadable:
            sys.exit(
                "ledger repair refused: this repository HAS a remote but its committed "
                "lineage for the ledger could not be read. Run `git fetch origin` and retry."
            )
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
        if session_id:
            run_row["session"] = session_id

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
        if row.get("event") not in known_events():
            problems.append(f"line {i}: unknown event {row.get('event')!r}")
        if row.get("actor") not in known_actors():
            problems.append(f"line {i}: unknown actor {row.get('actor')!r}")
        for field in ("ts", "subject", "detail"):
            if not row.get(field):
                problems.append(f"line {i}: missing {field}")

    # THE REFS LEG -- an edge a row CLAIMS must resolve, and here the claim is
    # checked rather than believed. `append` refuses a dangling `row` ref at write
    # time; that check cannot see a ref broken AFTERWARDS (a rewrite, a truncation,
    # a hand-edit), and this leg is the half that can. A kind that is neither core
    # nor declared is reported too: an undeclared kind is a member's object the
    # instrument has no vocabulary for, and silence would read as support.
    refs_examined = 0
    for i, row in enumerate(rows, 1):
        for ref in (row.get("refs") or []):
            for kind, value in ref.items():
                refs_examined += 1
                if kind == "row":
                    if not str(value).isdigit():
                        problems.append(
                            f"line {i}: ref row:{value!r} is not a row number")
                    elif int(value) > len(rows):
                        problems.append(
                            f"line {i}: dangling ref row:{value} -- the ledger "
                            f"holds {len(rows)} row(s), so it points at nothing")
                elif kind not in known_ref_kinds():
                    problems.append(
                        f"line {i}: ref kind {kind!r} is not declared -- one of: "
                        f"{', '.join(known_ref_kinds())}")

    # A subject's life is a sequence, not a row count. Subjects are compared as
    # exact strings — `#6` and `6` are different subjects, and no normalisation
    # is applied, because guessing at intent is how a gate starts agreeing with
    # its author. The index is built ONCE and the predicate is asked per close
    # row; `append` asks the SAME predicate about the row it is about to write,
    # so a defect is named at the moment it would be created (#98, n=596).
    by_subject = index_by_subject(rows)
    seq_problems: list[tuple[str, str, str]] = []  # (subject, leg, message)
    for i, row in enumerate(rows):
        event = row.get("event")
        # `claim` is checked as well as `close` (#137 half 2). A claim whose subject
        # has no intake anywhere in the ledger is a defect a close-keyed reading
        # cannot see until the close is attempted, hours later — and by then the
        # ledger has been carrying it. The predicate keeps the close leg positional
        # and the claim leg global; see sequence_problems for why.
        if event not in ("close", "claim"):
            continue
        seq_problems.extend(
            sequence_problems(by_subject, row.get("subject"), i, event))

    # The dispatch leg is INDEPENDENT of the close sequence above (n=524: the malformed
    # check "may land with it or before it"), and its two halves have different
    # dispositions: the ordering half is EXEMPTABLE like every other leg, the malformed
    # half is REPORTED and never gated.
    dispatch_defects, dispatch_malformed, dispatch_excused = dispatch_problems(
        rows, by_subject
    )
    seq_problems.extend(dispatch_defects)
    dispatch_examined = sum(1 for r in rows if r.get("event") == "dispatch")
    dispatch_work_units = sum(
        1 for r in rows if r.get("event") == "dispatch"
        and is_work_unit(str(r.get("subject") or "").strip())
    )
    dispatch_observations = (
        dispatch_examined - dispatch_work_units - len(dispatch_malformed)
    )

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

    # The population is printed BESIDE the verdict, never implied by it: a leg that
    # examined nothing must not read as a leg that examined the ledger and found it
    # clean. Same convention as the patrol legs.
    print(f"refs examined: {refs_examined}")
    # The dispatch leg's population, printed BESIDE the verdict rather than implied by
    # it — a leg that examined nothing must not read as one that examined the ledger.
    print(
        f"dispatch rows examined: {dispatch_examined} "
        f"({dispatch_work_units} work-unit, {dispatch_observations} observation, "
        f"{len(dispatch_malformed)} malformed), ordering leg forward-only from "
        f"{DISPATCH_LEG_BOUNDARY}"
    )
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
        for subject, line_no, ts in dispatch_excused:
            print(
                f"  excused: dispatch of {subject} at line {line_no} ({ts}) precedes "
                f"its intake — pre-boundary, and the law that orders them has never "
                f"been enforced before {DISPATCH_LEG_BOUNDARY}"
            )
        rc = 0
    # The malformed population prints on BOTH paths: a row whose subject cannot be
    # resolved is a finding about the ROW, and it stays visible even when the ledger is
    # otherwise clean — which is the only way a reader meets it at all.
    for subject, line_no in dispatch_malformed:
        print(
            f"  malformed subject: dispatch at line {line_no} carries {subject!r} — "
            f"neither a strict '#<n>' nor a descriptive stem, so a work-unit dispatch "
            f"was intended and no subject-keyed predicate can resolve it. The row's "
            f"identity is immutable once pushed; the repair is a NEW row"
        )

    # A SUBJECT CLOSED MORE THAN ONCE (#213). The write path now REFUSES a second
    # close that declares no `reclose=`, so the class cannot be created going
    # forward -- but refusing new ones says nothing about the ones already here,
    # and this leg is what makes the population visible. It printed nothing before:
    # the sequence predicate looks for PRESENCE of a close, so a subject carrying
    # TWO of them satisfied it twice over, and `verify` returned "sequences
    # complete" over four measured duplicate pairs in a single day (`#140`, `#169`,
    # `#202`, `#84`). An instrument that cannot OBSERVE a defect class cannot clear
    # the surface it is aimed at, and this one was reading those four as clean.
    #
    # IT NAMES THEM ON BOTH PATHS, beside `malformed subject`, and for the same
    # reason: a historical defect with no in-place repair must stay visible even
    # when the ledger is otherwise clean, because the alternative is a reader who
    # never meets it. The repair is a NEW row -- identity is immutable once pushed.
    #
    # IT PRINTS ITS POPULATION, NOT ONLY ITS HITS (#94's law, and HQ's #213 ruling):
    # "count examined, each pair named". A finding printed over an UNSTATED
    # population cannot be told from a finding printed over a narrowed one, so the
    # count of subjects examined is stated even when it finds nothing.
    #
    # IT PRINTS WHETHER THE DECLARATION IS PRESENT, not merely the count, because
    # the two populations need different readings: a pair declaring `reclose=` is a
    # recorded re-open, and a pair declaring nothing is either an undeclared
    # re-close or a retried-append duplicate. Measured split: 2 re-closes hours
    # apart by different actors (`#22` n=95/125, `#26` n=118/135) against 4
    # same-text pairs minutes apart.
    #
    # THE FORM FOR A LAWFUL RE-CLOSE IS THE DECLARED TOKEN, and it is stated here
    # because the choice IS the decision (HQ, #213): the predicate is NOT
    # "byte-equivalent detail", it is "declares `reclose=`". Byte-equivalence would
    # have passed all four observed duplicates silently -- they are the SAME text
    # by construction, which is what a retry produces -- so it is the weaker form
    # of the two. A re-open that means it says so; a retry that cannot know
    # whether it landed is told by the refusal, which names the row that landed.
    close_subjects = sorted({r.get("subject") for r in rows
                             if r.get("event") == "close"})
    multi_closes: list[str] = []
    for subject in close_subjects:
        closes = [r for r in rows
                  if r.get("event") == "close" and r.get("subject") == subject]
        if len(closes) < 2:
            continue
        ns = ", ".join(f"n={r.get('n')}" for r in closes)
        undeclared = [r for r in closes[1:]
                      if not declares_field(r.get("detail") or "", "reclose")]
        multi_closes.append(subject)
        if undeclared:
            print(
                f"  multiple closes: {subject} carries {len(closes)} close rows "
                f"({ns}), and {len(undeclared)} of them declare no `reclose=` reason — "
                f"either a deliberate re-close that did not declare itself, or a "
                f"DUPLICATE minted by retrying an append that had already completed "
                f"(#213). A second close declaring no `reclose=` is now refused at the "
                f"write path; this reading is of history, whose rows are immutable"
            )
        else:
            print(
                f"  multiple closes: {subject} carries {len(closes)} close rows "
                f"({ns}), each after the first declaring `reclose=` — declared "
                f"re-closes, not duplicates"
            )
    print(
        f"  multiple closes examined: {len(close_subjects)} closed subject(s), "
        f"{len(multi_closes)} carrying more than one close"
    )

    # A SUBJECT CLAIMED MORE THAN ONCE (#246) — the read half of the pair above, and it
    # prints its POPULATION, not only its hits (#94's law): a finding printed over an
    # UNSTATED population cannot be told from one printed over a narrowed population, so
    # the count of subjects examined is stated even when it finds nothing.
    #
    # IT SPLITS DECLARED FROM UNDECLARED, which is the whole reading. A pair declaring
    # `reclaim=` is a recorded re-claim, and a pair declaring nothing is either an
    # undeclared re-claim or a retried-append duplicate — measured at origin 4e142dd, the
    # eight subjects with more than one claim split FOUR ways, and only one of the four is
    # a defect: three declared re-claims (#73, #113, #161), two multi-actor cases that are
    # LAWFUL and are why the refusal is actor-scoped (#34 hand-off, #234 two halves), one
    # duplicate-resolution row (#22), one pair of distinct tasks under one subject (#26),
    # and ONE accidental duplicate (#220, same actor, same wording, 18 minutes apart).
    #
    # IT REPORTS AND NEVER GATES: a multi-claim subject is not by itself a defect, so this
    # leg has no red to give — the same shape the multiple-closes leg has. NO BACKFILL:
    # the rows it prints are immutable, exactly as #213's own reading states.
    claim_subjects = sorted({r.get("subject") for r in rows
                             if r.get("event") == "claim"})
    multi_claims: list[str] = []
    for subject in claim_subjects:
        claims = [r for r in rows
                  if r.get("event") == "claim" and r.get("subject") == subject]
        if len(claims) < 2:
            continue
        ns = ", ".join(f"n={r.get('n')} ({r.get('actor')})" for r in claims)
        # THE SPLIT IS THE REFUSAL'S OWN SCOPE, or the reading reports lawful states as
        # suspects. The refusal admits a second claim by a DIFFERENT actor (#34's hand-off,
        # #234's two halves), so a pair whose actors all differ is a state the write path
        # PERMITS — printing it under the duplicate wording would send a reader to repair
        # something no rule forbids. So the three forms are distinguished, and only the
        # same-actor undeclared one carries the refusal's sentence.
        by_actor: dict[str, list[dict]] = {}
        for row in claims:
            by_actor.setdefault(str(row.get("actor") or "?"), []).append(row)
        same_actor_undeclared = [
            row for group in by_actor.values() if len(group) > 1
            for row in group[1:]
            if not declared_reclaim(row.get("detail") or "")
        ]
        declared = [r for r in claims[1:]
                    if declared_reclaim(r.get("detail") or "")]
        multi_claims.append(subject)
        if same_actor_undeclared:
            print(
                f"  multiple claims: {subject} carries {len(claims)} claim rows "
                f"({ns}), and {len(same_actor_undeclared)} of them "
                f"{'carries' if len(same_actor_undeclared) == 1 else 'carry'} no "
                f"`reclaim=` reason for a SAME-ACTOR second claim — either a deliberate "
                f"re-claim that did not declare itself, or a DUPLICATE minted by retrying "
                f"an append that had already completed (#246). A second claim by the same "
                f"actor declaring no `reclaim=` is now refused at the write path; this "
                f"reading is of history, whose rows are immutable"
            )
        elif declared:
            print(
                f"  multiple claims: {subject} carries {len(claims)} claim rows "
                f"({ns}), each after the first declaring `reclaim=` — declared "
                f"re-claims, not duplicates"
            )
        else:
            print(
                f"  multiple claims: {subject} carries {len(claims)} claim rows "
                f"({ns}), all by DIFFERENT actors — a hand-off or a two-half unit, which "
                f"the write path admits; no same-actor second claim, so no declaration is "
                f"owed"
            )
    print(
        f"  multiple claims examined: {len(claim_subjects)} claimed subject(s), "
        f"{len(multi_claims)} carrying more than one claim"
    )

    # THE CLAIM LIFECYCLE (#210, ruling n=1577). A claim terminates one of two ways: a
    # `close` for its subject AFTER it (work finished), or a `release` naming its own
    # row (work withdrawn). Anything else is OPEN -- claimed, and neither finished nor
    # withdrawn.
    #
    # WHY THIS LEG EXISTS. HQ's ruling names "the claim-without-close sweep", and
    # measured at source there was NO such leg: `verify` modelled a subject's life as
    # intake -> claim -> close, and the claim leg asked only whether an intake existed
    # ANYWHERE (#137 half 2). So a claim that was given up sat indistinguishable from
    # work in flight, and the two `#172`/`#52` withdrawals lived in PROSE because no row
    # could say it. Build what the ruling names, then read it: a declaration nothing
    # READS is a field written but never read (#218), so the declaration and this reader
    # land in the same change.
    #
    # IT PRINTS ITS POPULATION AND ITS FINDINGS, AND IT NEVER GATES. An open claim is
    # NORMAL -- work in flight -- so this leg reports rather than reds, exactly as the
    # dispatch-malformed leg does. What it makes visible is the reading a reader could
    # not previously get: finished, withdrawn, or still open, counted AND named. The
    # population is printed BESIDE the verdict (#94's law): a leg that examined nothing
    # must not read as a leg that examined the ledger and found it clean.
    claim_life_rows = [(i, r) for i, r in enumerate(rows) if r.get("event") == "claim"]
    release_targets: dict[int, list[dict]] = {}
    for _r in rows:
        if _r.get("event") != "release":
            continue
        for _ref in (_r.get("refs") or []):
            for _kind, _value in _ref.items():
                if _kind == "row" and str(_value).isdigit():
                    release_targets.setdefault(int(_value), []).append(_r)
    close_index: dict[str, list[int]] = {}
    for _i, _r in enumerate(rows):
        if _r.get("event") == "close":
            close_index.setdefault(_r.get("subject"), []).append(_i)
    released_claims: list[dict] = []
    open_claims: list[dict] = []
    for _i, _r in claim_life_rows:
        if release_targets.get(_r.get("n")):
            released_claims.append(_r)
        elif any(_j > _i for _j in close_index.get(_r.get("subject"), [])):
            continue
        else:
            open_claims.append(_r)
    # A RELEASE WHOSE REF NAMES NO CLAIM is the write path's predicate read at its other
    # call site -- one predicate, two call sites, the shape the sequence leg already has
    # (#98). Only read time can see a release whose target stopped being a claim after it
    # was written; the write path is the half that prevents it.
    orphan_releases: list[dict] = []
    for _n, _rels in sorted(release_targets.items()):
        _t = next((r for r in rows if r.get("n") == _n), None)
        if _t is not None and _t.get("event") != "claim":
            orphan_releases.extend(_rels)
    print(
        f"  claim lifecycle examined: {len(claim_life_rows)} claim row(s) over "
        f"{len({r.get('subject') for _i, r in claim_life_rows})} subject(s) — "
        f"{len(claim_life_rows) - len(released_claims) - len(open_claims)} terminal by "
        f"close, {len(released_claims)} terminal by release, {len(open_claims)} open; "
        f"{len(release_targets)} release(s) examined"
    )
    for _r in released_claims:
        print(
            f"  released claim: n={_r.get('n')} {_r.get('subject')} — withdrawn by "
            f"release n={release_targets[_r.get('n')][-1].get('n')}, so it is terminal "
            f"and not counted as in flight"
        )
    for _r in open_claims:
        print(
            f"  open claim: n={_r.get('n')} {_r.get('subject')} claimed by "
            f"{_r.get('actor')} — no close after it and no release naming it, so the "
            f"ledger cannot tell in-flight work from withdrawn work. A withdrawal is "
            f"recorded as a `release` naming this row"
        )
    for _r in orphan_releases:
        print(
            f"  release at n={_r.get('n')} names a row that is not a claim — a release "
            f"withdraws a CLAIM, and a claim is the only row it can terminate"
        )

    # The revision comparison runs whatever the structure check found: a ledger that is
    # internally consistent can still have had a row's identity changed, which is exactly
    # the case plain `verify` cannot see (the #52 shape — n=302 kept its number and became
    # a different row). Reporting it only on the clean path would hide it on the path where
    # a reader most needs it.
    against = getattr(args, "against", None)
    if against:
        rc = max(rc, _verify_against(against, target_ledger, rows))
    return rc

class _LedgerParser(argparse.ArgumentParser):
    """Argparse refuses an unknown flag with a bare usage line, and that line cannot
    tell a TYPO from a REQUEST FOR A CAPABILITY this tool does not carry. The two read
    identically, so the refusal names the two lawful routes instead -- the answer is
    then in the refusal itself rather than in a reader's guess about it.
    """

    _ROUTES = (
        "  Two lawful routes for data the core flag set does not carry:\n"
        "    --ref <kind>:<value>         a typed pointer from this row to another object\n"
        "    docs/ledger-refs-kinds.json  declare a new ref kind (or event), for a\n"
        "                                 member factory's own object\n"
        "  Full append surface: --event --actor --subject --detail [--ref ...]\n"
        "  [--subprocess]"
    )

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        sys.stderr.write("\nledger refusal: %s\n%s\n" % (message, self._ROUTES))
        self.exit(2)


def main() -> int:
    parser = _LedgerParser(description=__doc__)
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
    ap.add_argument(
        "--ref", action="append", default=[], metavar="KIND:VALUE",
        help="a typed pointer from this row to another object; repeatable. KIND is one of "
             "row, subject, commit, session, rework, or a kind declared in "
             "docs/ledger-refs-kinds.json",
    )
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
    try:
        return args.func(args)
    except DeclarationUnreadable as exc:
        # A declaration that cannot be read must FAIL, never read as none: a factory whose
        # own lanes vanished from the matrix on a typo would have its rows refused with a
        # membership error that names no file.
        sys.exit(f"ledger refused: {exc}")

if __name__ == "__main__":
    raise SystemExit(main())
