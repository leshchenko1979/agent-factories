"""Gate: publish freshness, cadence and pacemaker presence — #146/#284/#315/#468

Split from tests/test_patrol_host_state.py by #602: one gate per leg, each
carrying its own measured budget, so one slow leg can no longer withhold a
verdict from the whole fleet.
"""

# --- imports ---------------------------------------------------------------
from __future__ import annotations
import importlib.util
import io
import json
import os
import sqlite3
import shutil
import subprocess
import tempfile
import datetime as dt
from pathlib import Path
from unittest import mock
import pytest

from patrol_fixtures import (  # noqa: F401
    REPO,
    RUNNER,
    RUNNER_PATH,
    _DUTY_BOUND,
    _DUTY_FIRE,
    _NONE_DECL,
    _PRESENCE_BINDINGS,
    _PRESENCE_FRAGMENT,
    _PRESENCE_REGISTER,
    _StubRegistry,
    _WAKE_PROMPT,
    _declared_skip,
    _duty_leg,
    _duty_row,
    _duty_tree,
    _git,
    _plus,
    _run,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _bare(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--bare", "-q")
    _git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    return path

def _work(path: Path, remote: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(path, "config", "user.email", "probe@probe.invalid")
    _git(path, "config", "user.name", "probe")
    _git(path, "remote", "add", "origin", str(remote))
    return path

def _commit(repo: Path, name: str, *, when: dt.datetime | None = None,
            trailer: str | None = None) -> str:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    env = {}
    if when is not None:
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    message = name if trailer is None else f"{name}\n\nSession-Id: {trailer}\n"
    _git(repo, "commit", "-q", "-m", message, env=env)
    return _git(repo, "rev-parse", "HEAD")

def _seeded(root: Path):
    """A bare remote carrying one commit, and a clone of it. Returns (remote, work).

    The seed commit is BACKDATED. A repo with history has an old tip, and the publish leg's
    tip-age arm (issue #284) reads a tip younger than the pusher's grace window as one no
    governed push explains -- which a just-created seed would be. Backdating keeps the
    fixture representative, so a control that asserts a clean leg is asserting it about a
    healthy repo rather than about an artifact of the fixture's own clock.
    """
    remote = _bare(root / "remote.git")
    seed = _work(root / "seed", remote)
    _commit(seed, "a.txt", when=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=6))
    _git(seed, "push", "-q", "origin", "main:main")
    work = root / "work"
    _git(root, "clone", "-q", str(remote), str(work))
    _git(work, "config", "user.email", "probe@probe.invalid")
    _git(work, "config", "user.name", "probe")
    return remote, work

def _sibling(work: Path, root: Path, name: str = "sibling") -> Path:
    """A SECOND checkout of the SAME repository, sharing its git common dir (#445).

    A `git worktree` is the only shape that gives one repository two working directories:
    the sibling's `.git` is a FILE pointing into the main checkout's `.git/worktrees/`, so
    `rev-parse --git-common-dir` resolves BOTH checkouts to the same directory. That is what
    makes a receipt written here visible to a reader in `work` -- and what makes a
    checkout-local fallback in `receipt_path` FAIL these arms rather than pass them.
    """
    sib = root / name
    _git(work, "worktree", "add", "-q", "--detach", str(sib))
    return sib

def _pusher():
    return RUNNER.load_module("publish", RUNNER.PUBLISH_PUSHER)

def _binding_fixture(root: Path, *, behind: bool = False, publish_extra: str | None = None):
    """`(repo, profile_root, declaration_path, reference_sha)` for a synthetic factory.

    The profile root carries `skills/demo` as a SYMLINK to the repo's own `skills/demo`, so
    the fixture is the live shape and not an approximation of it. With `behind=True` the
    loaded tree is reset one commit back AFTER the reference was pushed -- the loaded tree
    stands BEHIND `origin/main`, which is exactly the state the live box is in and the one a
    timestamp cannot distinguish from a healthy tree.
    """
    remote = _bare(root / "remote.git")
    work = _work(root / "work", remote)
    law = work / "skills" / "demo"
    law.mkdir(parents=True)
    (law / "SKILL.md").write_text("v1\n", encoding="utf-8")
    (work / "docs").mkdir()
    (work / "docs" / "harness-bindings.json").write_text(
        json.dumps({
            "profile": "probe",
            "bindings": [{"skill": "demo", "repo_path": "skills/demo", "form": "dir"}],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    _commit(work, "seed-law")
    _git(work, "push", "-q", "origin", "main:main")

    (law / "SKILL.md").write_text("v2 -- the published law\n", encoding="utf-8")
    if publish_extra:
        (law / publish_extra).write_text(f"{publish_extra}\n", encoding="utf-8")
    _commit(work, "publish-law")
    _git(work, "push", "-q", "origin", "main:main")
    reference = _git(work, "rev-parse", "HEAD")
    if behind:
        _git(work, "reset", "--hard", "HEAD~1")

    profile = root / "profile"
    (profile / "skills").mkdir(parents=True)
    (profile / "skills" / "demo").symlink_to(law)
    return work, profile, work / "docs" / "harness-bindings.json", reference

def _run_arm(repo: Path, profile: Path, declaration: Path, reference: str | None):
    return RUNNER.binding_freshness_arm(
        repo=repo, profile_root=profile, declaration_path=declaration,
        reference_ref=reference, reference_source="probe", read_at="probe",
    )

def _presence_leg(rows, *, register=_PRESENCE_REGISTER, fragment=_PRESENCE_FRAGMENT,
                  bindings=_PRESENCE_BINDINGS, prefixes=("factory-",)):
    return RUNNER.pacemaker_presence_leg(
        rows, bindings, register, fragment, read_at="2026-10-05T00:00:00Z",
        slug="meta-factory", prefixes=list(prefixes), homes_read=["probe-home"],
        registry=_StubRegistry(),
    )

# --- this leg's tests -------------------------------------------------------
def test_the_publish_leg_BITES_when_a_commit_has_been_unpushed_past_the_window() -> None:
    """The leg's whole purpose: a commit no healthy pusher can explain, NAMED."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        now = dt.datetime.now(dt.timezone.utc)
        stale = now - dt.timedelta(seconds=RUNNER.PUBLISH_RESIDUAL_SECS * 2)
        sha = _commit(work, "b.txt", when=stale, trailer="deadbeef-lane")

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"], "an unpushed commit past the window must be a problem"
        assert any(sha in problem for problem in leg["problems"]), leg["problems"]
        assert any("deadbeef-lane" in problem for problem in leg["problems"]), (
            f"a finding must NAME the lane that authored it: {leg['problems']}"
        )
        assert leg["coverage"]["unpushed"] == 1 and leg["coverage"]["shas"] == [sha]
        assert len(leg["coverage"]["stale"]) == 1

def test_the_publish_leg_HOLDS_a_commit_inside_the_residual_window_and_still_names_it() -> None:
    """The control. Without it, a leg that flagged EVERY unpushed commit would pass the
    arm above -- and would red the patrol on every round between two healthy pushes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        now = dt.datetime.now(dt.timezone.utc)
        fresh = now - dt.timedelta(seconds=60)
        sha = _commit(work, "b.txt", when=fresh)

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"] == [], leg["problems"]
        assert leg["coverage"]["unpushed"] == 1, leg["coverage"]
        assert leg["coverage"]["shas"] == [sha]
        assert leg["coverage"]["stale"] == []
        assert leg["coverage"]["residual_secs"] == RUNNER.PUBLISH_RESIDUAL_SECS

def test_the_publish_leg_reports_an_UNREACHABLE_remote_as_a_finding() -> None:
    """'I could not ask' and 'there is nothing to publish' are different facts. A leg
    that read an unreachable remote as in-sync would report a clean result over a
    question it never got an answer to."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        work = _work(root / "work", root / "does-not-exist.git")
        _commit(work, "a.txt")
        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe"
        )
        assert leg["problems"], "an unreadable remote must be a finding"
        assert any("could not be read" in p for p in leg["problems"]), leg["problems"]
        assert leg["coverage"]["remote_tip"] is None

def test_the_publish_leg_reads_the_REMOTE_not_the_local_ref() -> None:
    """`origin/main` is a cache updated only by a fetch. A leg reading it would report the
    fact in doubt -- the same substitution the pusher itself refuses."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        stale_ref = _git(work, "rev-parse", "origin/main")

        peer = root / "peer"
        _git(root, "clone", "-q", str(remote), str(peer))
        _git(peer, "config", "user.email", "probe@probe.invalid")
        _git(peer, "config", "user.name", "probe")
        _commit(peer, "peer.txt")
        _git(peer, "push", "-q", "origin", "main:main")
        moved = _git(remote, "rev-parse", "refs/heads/main")

        assert moved != stale_ref, "the arm's own precondition: the local ref is stale"

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe"
        )
        assert leg["coverage"]["remote_tip"] == moved, (
            f"reported {leg['coverage']['remote_tip']} but the remote tip is {moved}"
        )

def test_the_publish_leg_shares_the_PUSHER_own_predicate() -> None:
    """One predicate, two call sites. A private `git` call here would let the leg and the
    mechanism disagree about what 'unpushed' means -- the drift the kit-drift leg avoids
    by reading through `tools/kit_pin.py`."""
    source = RUNNER_PATH.read_text(encoding="utf-8")
    start = source.index("def publish_freshness_leg")
    end = source.index("def deferred_legs")
    body = source[start:end]
    assert 'load_module("publish"' in body, "the leg must load the pusher's own module"
    assert 'pub.remote_tip(' in body and 'pub.unpushed_commits(' in body, body[:400]
    assert '"ls-remote"' not in body, "the leg must not restate the remote read"
    assert '"rev-list"' not in body, "the leg must not restate the unpushed read"

def test_the_publish_leg_is_WIRED_into_the_runner_and_prints_its_population() -> None:
    """A leg that is not wired is a leg nobody runs; a leg whose population never renders
    is a leg nobody reads. A count without its predicate is unreadable."""
    source = RUNNER_PATH.read_text(encoding="utf-8")
    # The property is WIRED **and** INJECTABLE, not a literal: the leg reads the remote, so
    # the seam that lets a probe stub it is part of what must be true (see the 40s-to-4s
    # measurement in the stub's own docstring).
    assert "(publish_fn or publish_freshness_leg)(read_at=read_at)," in source, (
        "not wired into main(), or wired without the injection seam"
    )
    assert "publish_fn=None," in source, "main() must accept a publish_fn"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        now = dt.datetime.now(dt.timezone.utc)
        stale = now - dt.timedelta(seconds=RUNNER.PUBLISH_RESIDUAL_SECS * 2)
        sha = _commit(work, "b.txt", when=stale, trailer="cafebabe-lane")

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-09-26T00:00:00Z", issues=[]
        )
        assert "LEG publish-freshness" in text, text
        assert "residual window" in text, text
        assert sha in text and "cafebabe-lane" in text, text
        assert "STALE" in text, text

def test_the_publish_leg_does_not_RED_a_pure_ancestor_tree_but_still_REDs_a_DIVERGENCE() -> None:
    """#418, the hermetic fixture PAIR for the leg. The live tree exhibits ONLY the BEHIND
    state (the shared tree is a pure ancestor of `origin/main`), so the leg cannot be shown
    on it to tell the two shapes apart. Fixture A (pure ancestor, ahead==0) must produce NO
    problem and print BEHIND; fixture B (ahead>0 AND behind>0) must still RED with DIVERGED.

    Both halves are load-bearing: without fixture B a leg that stopped reddening EVERYTHING
    would pass, and without fixture A the leg's old one-sided test (which red the normal
    steady state) would pass. The leg's own population print must survive in both.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(hours=6)

        # --- fixture A: pure BEHIND. The peer's commit is BACKDATED past the grace window
        # so the tip-age arm (which fires on a tip SAMPLED while young) stays out of it.
        remote_a, work_a = _seeded(root / "a")
        peer = root / "a" / "peer"
        _git(root / "a", "clone", "-q", str(remote_a), str(peer))
        _git(peer, "config", "user.email", "probe@probe.invalid")
        _git(peer, "config", "user.name", "probe")
        _commit(peer, "peer.txt", when=old, trailer="peer-lane")
        _git(peer, "push", "-q", "origin", "main:main")
        # FETCH, so the remote tip object is LOCAL: `rev-list --count` needs it, and a
        # behind tree normally has it (the live #418 reading was a readable `11`). Without
        # the fetch the count reads "unreadable", which would mask the reading under test.
        # After the fetch `work_a`'s HEAD is STILL a pure ancestor of the remote tip.
        _git(work_a, "fetch", "-q", "origin")
        leg_a = RUNNER.publish_freshness_leg(
            repo=work_a, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg_a["problems"] == [], (
            f"a pure-ancestor (BEHIND) tree must NOT be a problem: {leg_a['problems']}"
        )
        assert leg_a["coverage"]["behind"] is True, leg_a["coverage"]
        assert leg_a["coverage"]["diverged"] is False, leg_a["coverage"]

        text_a = RUNNER.render(
            [leg_a], [], slug="owner/repo", read_at="2026-10-06T00:00:00Z", issues=[]
        )
        assert "BEHIND" in text_a, text_a
        assert "remote tip" in text_a and "unpushed commit(s)" in text_a, (
            f"the population print must survive: {text_a}"
        )

        # --- fixture B: genuine DIVERGENCE (ahead>0 AND behind>0). The local commit is
        # FRESH so only the divergence arm speaks (the stale arm stays out of it).
        remote_b, work_b = _seeded(root / "b")
        _commit(work_b, "mine.txt", when=now - dt.timedelta(seconds=60), trailer="mine-lane")
        peer_b = root / "b" / "peer"
        _git(root / "b", "clone", "-q", str(remote_b), str(peer_b))
        _git(peer_b, "config", "user.email", "probe@probe.invalid")
        _git(peer_b, "config", "user.name", "probe")
        _commit(peer_b, "peer.txt", when=old, trailer="peer-b-lane")
        _git(peer_b, "push", "-q", "origin", "main:main")
        # FETCH, so both counts are READABLE (see fixture A's note): after it `work_b` has
        # one commit the remote lacks (ahead 1) and one it lacks (behind 1) -- a genuine
        # divergence, not an unreadable-count fallback.
        _git(work_b, "fetch", "-q", "origin")

        leg_b = RUNNER.publish_freshness_leg(
            repo=work_b, remote="origin", branch="main", read_at="probe", now=now
        )
        assert any("DIVERGED" in p for p in leg_b["problems"]), (
            f"a genuine divergence must still RED: {leg_b['problems']}"
        )
        assert leg_b["coverage"]["diverged"] is True, leg_b["coverage"]
        assert leg_b["coverage"]["behind"] is False, leg_b["coverage"]

        text_b = RUNNER.render(
            [leg_b], [], slug="owner/repo", read_at="2026-10-06T00:00:00Z", issues=[]
        )
        assert "DIVERGED" in text_b, text_b

def test_the_publish_leg_REPORTS_an_ungoverned_push_BY_NAME() -> None:
    """Leg (c)(2). The receipt names the sha the pusher pushed; a tip that is not that sha
    left through some other path, and the finding must NAME the tip, the lane trailer of its
    commit and the receipt it contradicts. A count alone cannot be dispatched or closed.

    THE RECEIPT IS WRITTEN BY A SIBLING CHECKOUT (#445): the record is per-REPOSITORY, so a
    reader in `work` must still see it and report the mismatch -- a checkout-local fallback
    would read no receipt at all and this arm would silently weaken to the tip-age case.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(hours=6)

        governed = _commit(work, "b.txt", when=old, trailer="gov-lane")
        _git(work, "push", "-q", "origin", "main:main")
        writer = _sibling(work, root, "writer")
        path, why = pub.write_receipt(
            writer, sha=governed, remote="origin", branch="main",
            instant=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert path is not None and not why, why

        # The ungoverned push: committed 6h ago (so the tip-age arm stays out of it) and
        # pushed straight to the remote, bypassing the pusher entirely.
        rogue = _commit(work, "rogue.txt", when=old, trailer="rogue-lane")
        _git(work, "push", "-q", "origin", "main:main")

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        joined = " ".join(leg["problems"])
        assert leg["problems"], "a tip the receipt does not account for must be a finding"
        assert rogue in joined, f"the finding must NAME the ungoverned sha: {leg['problems']}"
        assert "rogue-lane" in joined, f"the finding must NAME its lane: {leg['problems']}"
        assert governed in joined, (
            f"the finding must NAME the receipt it contradicts: {leg['problems']}"
        )
        assert leg["coverage"]["receipt_mismatch"]["remote_tip"] == rogue
        # The record was written by the SIBLING and the finding says so, rather than
        # attributing it to the checkout that happens to be reading (#445).
        assert leg["coverage"]["receipt_mismatch"]["receipt_origin_checkout"] == str(
            writer.resolve()
        ), leg["coverage"]["receipt_mismatch"]

        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-10-03T00:00:00Z", issues=[]
        )
        assert "UNGOVERNED PUSH" in text and rogue in text, text

def test_the_publish_leg_is_QUIET_when_the_receipt_ACCOUNTS_for_the_tip() -> None:
    """The control. Without it, a leg that red on ANY receipt would pass the arm above --
    and would red the patrol on every healthy round, since a governed push leaves the tip
    exactly equal to the sha the pusher recorded.

    THE RECEIPT IS WRITTEN IN A SIBLING CHECKOUT (#445). The record is per-REPOSITORY (git
    common dir), so this control writes it from a `git worktree` sibling and reads it from
    `work`. A checkout-local fallback would find no receipt in `work` and the leg would
    report `no receipt recorded` -- the exact false negative this shape removes -- so the
    control FAILS against the old shape rather than passing it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(hours=6)

        governed = _commit(work, "b.txt", when=old, trailer="gov-lane")
        _git(work, "push", "-q", "origin", "main:main")
        writer = _sibling(work, root, "writer")
        path, why = pub.write_receipt(
            writer, sha=governed, remote="origin", branch="main",
            instant=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert path is not None and not why, why

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"] == [], leg["problems"]
        assert leg["coverage"]["receipt_mismatch"] is None
        assert leg["coverage"]["receipt"]["sha"] == governed
        assert leg["coverage"]["tip_younger_than_grace"] is False
        # The record was written by the SIBLING, and the coverage says so rather than
        # attributing it to the checkout that happens to be reading (#445).
        assert leg["coverage"]["receipt"]["origin_checkout"] == str(writer.resolve()), (
            leg["coverage"]["receipt"]
        )
        assert leg["coverage"]["reading_checkout"] == str(work.resolve())
        assert leg["coverage"]["receipt_path"] == str(pub.receipt_path(work))

def test_the_receipt_is_SHARED_across_worktrees_of_one_repository() -> None:
    """#445 acceptance: the SAME remote tip, read from TWO checkouts of ONE repository,
    returns the SAME verdict -- the fixture pair.

    This is the defect itself, as a discriminating arm. Before #445 the receipt sat under
    `evidence/`, gitignored and therefore checkout-local, so one tip read 0 problems in the
    checkout that had pushed and 1 in a sibling that had not: a GLOBAL remote tip judged
    against a LOCAL record, with the finding naming a lane that had pushed correctly. Both
    checkouts now read the ONE record in the git common dir, so the arm asserts EQUALITY of
    the two verdicts AND that both resolve the SAME receipt file -- merely asserting each is
    quiet would pass a leg that read no receipt at all.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(hours=6)

        governed = _commit(work, "b.txt", when=old, trailer="gov-lane")
        _git(work, "push", "-q", "origin", "main:main")
        sibling = _sibling(work, root, "sibling")

        # The pusher pushed FROM `work` and recorded its receipt there.
        path, why = pub.write_receipt(
            work, sha=governed, remote="origin", branch="main",
            instant=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert path is not None and not why, why

        leg_a = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        leg_b = RUNNER.publish_freshness_leg(
            repo=sibling, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg_a["problems"] == [] and leg_b["problems"] == [], (
            f"one repository, one receipt: the two checkouts must agree, got "
            f"{leg_a['problems']} vs {leg_b['problems']}"
        )
        assert (
            leg_a["coverage"]["receipt_path"] == leg_b["coverage"]["receipt_path"]
        ), "both checkouts must read the SAME receipt file (git common dir)"
        # The reading checkout differs; the receipt's origin does not.
        assert leg_a["coverage"]["reading_checkout"] == str(work.resolve())
        assert leg_b["coverage"]["reading_checkout"] == str(sibling.resolve())
        assert leg_a["coverage"]["receipt"]["origin_checkout"] == str(work.resolve())
        assert leg_b["coverage"]["receipt"]["origin_checkout"] == str(work.resolve())

def test_a_PUSHER_made_push_reads_GOVERNED_from_a_SIBLING_worktree() -> None:
    """#445 acceptance, driven by a REAL pusher push rather than a hand-written receipt.

    The arm above writes the record through `write_receipt` directly; this one runs the
    PUSHER -- `publish(..., apply=True)` -- so the receipt read is the one the tool itself
    writes on a round it published, and then reads the leg from a SIBLING worktree that
    holds no record of its own. Before #445 that sibling read `no receipt recorded` (the
    measured false negative) or a stale checkout-local receipt (the measured false positive
    that named the lane which had pushed correctly); now it reads the one per-repository
    record and reports the tip as GOVERNED.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(seconds=RUNNER.PUBLISH_GRACE_SECS * 4)

        sha = _commit(work, "b.txt", when=old, trailer="gov-lane")
        report = pub.publish(
            work, remote="origin", branch="main",
            grace_secs=RUNNER.PUBLISH_GRACE_SECS, apply=True,
        )
        assert report["status"] == "published" and report["receipt"]["sha"] == sha, report

        sibling = _sibling(work, root, "sibling")
        leg = RUNNER.publish_freshness_leg(
            repo=sibling, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"] == [], (
            f"a push the pusher ITSELF made must read governed from a sibling worktree: "
            f"{leg['problems']}"
        )
        # The DISCRIMINATING assertion. Against the old checkout-local shape the sibling
        # reads no receipt at all, so `problems` is ALSO empty -- the false negative is
        # silent -- and only a read of the record itself separates the two shapes.
        assert leg["coverage"]["receipt"] is not None, (
            "the sibling must READ the record the pusher wrote in the OTHER checkout, not "
            f"report it absent (receipt_reason={leg['coverage']['receipt_reason']!r})"
        )
        assert leg["coverage"]["receipt"]["sha"] == sha
        assert leg["coverage"]["receipt_mismatch"] is None
        assert leg["coverage"]["receipt"]["origin_checkout"] == str(work.resolve()), (
            leg["coverage"]["receipt"]
        )

def test_a_STALE_checkout_local_receipt_does_not_mislead_the_leg() -> None:
    """#445 acceptance, the STALE half of the fixture pair.

    The sibling arm covers the checkout that holds NO record. This one plants the OLD
    shape's leftover -- a checkout-local `evidence/publish-receipt.json` naming a sha the
    remote tip does NOT match -- in the READING checkout, and asserts the leg still reads
    the ONE per-repository record and reports the tip GOVERNED. It is the false positive
    itself: before #445 the leg read that stale file and named the lane that had pushed
    correctly.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        pub = _pusher()
        now = dt.datetime.now(dt.timezone.utc)
        old = now - dt.timedelta(seconds=RUNNER.PUBLISH_GRACE_SECS * 4)

        sha = _commit(work, "b.txt", when=old, trailer="gov-lane")
        report = pub.publish(
            work, remote="origin", branch="main",
            grace_secs=RUNNER.PUBLISH_GRACE_SECS, apply=True,
        )
        assert report["status"] == "published" and report["receipt"]["sha"] == sha, report

        sibling = _sibling(work, root, "sibling")
        # The leftover: a stale record in the OLD, checkout-local location.
        stale_dir = sibling / "evidence"
        stale_dir.mkdir(parents=True, exist_ok=True)
        (stale_dir / "publish-receipt.json").write_text(
            json.dumps({
                "sha": "0" * 40,
                "instant": "2026-01-01T00:00:00Z",
                "remote": "origin",
                "branch": "main",
            }) + "\n",
            encoding="utf-8",
        )

        leg = RUNNER.publish_freshness_leg(
            repo=sibling, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["problems"] == [], (
            f"a stale checkout-local receipt must not make a governed push read "
            f"UNGOVERNED: {leg['problems']}"
        )
        assert leg["coverage"]["receipt"] is not None, leg["coverage"]["receipt_reason"]
        assert leg["coverage"]["receipt"]["sha"] == sha, (
            "the leg must read the per-repository record, not the stale local file"
        )
        assert leg["coverage"]["receipt_mismatch"] is None
        assert leg["coverage"]["receipt_path"] == str(pub.receipt_path(work)), (
            leg["coverage"]["receipt_path"]
        )

def test_the_publish_leg_flags_a_YOUNG_tip_no_receipt_can_explain() -> None:
    """Leg (c)(3), the cheap arm. The pusher HOLDS a commit younger than its grace window,
    so a tip that young cannot have left through it -- and this arm speaks when there is no
    receipt at all, which is the case the receipt arm is blind to. Its bound is printed
    beside it: it sees only a tip SAMPLED while still young."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        now = dt.datetime.now(dt.timezone.utc)

        fresh = _commit(
            work, "direct.txt", when=now - dt.timedelta(seconds=30), trailer="direct-lane"
        )
        _git(work, "push", "-q", "origin", "main:main")

        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe", now=now
        )
        assert leg["coverage"]["receipt"] is None, "the arm's own precondition: no receipt"
        assert leg["coverage"]["tip_younger_than_grace"] is True
        joined = " ".join(leg["problems"])
        assert fresh in joined, f"the young tip must be NAMED: {leg['problems']}"
        assert "grace window" in joined, leg["problems"]

        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-10-03T00:00:00Z", issues=[]
        )
        assert "tip-age arm bound" in text, text

def test_the_publish_leg_prints_the_PUSHERS_bounds_and_its_OWN_scope() -> None:
    """Leg (b)(2). The three figures travel as the PUSHER's declared bounds, and the leg's
    own scope is printed beside them -- a coverage line that reads as a fleet-wide property
    is the defect #284 closes. Presence is not behaviour, so this reads the rendered text."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote, work = _seeded(root)
        leg = RUNNER.publish_freshness_leg(
            repo=work, remote="origin", branch="main", read_at="probe"
        )
        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-10-03T00:00:00Z", issues=[]
        )
        assert "the PUSHER's declared bounds" in text, text
        assert "SCOPE: LAG only" in text, text
        assert "not a property of the fleet" in text.lower(), text
        assert "pusher receipt:" in text, text

def test_the_binding_arm_BITES_when_the_loaded_law_stands_BEHIND_the_reference() -> None:
    """The arm's whole purpose, on the live shape: the tree the profile LOADS is behind the
    tree this repository publishes. The finding must NAME the file and BOTH content hashes --
    a count cannot be dispatched, a named file can."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp), behind=True)
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert problems, "a loaded tree behind the reference must be a finding"
        assert cov["stale"] == ["skills/demo/SKILL.md"], cov
        joined = " ".join(problems)
        assert "skills/demo/SKILL.md" in joined, joined
        assert "STALE" in joined, joined
        assert cov["rows"][0]["resolution"] == "resolved", (
            f"the binding RESOLVES and is still stale -- that split is the defect: {cov['rows']}"
        )
        assert cov["rows"][0]["stale"] == 1, cov["rows"]
        item = [f for f in cov["rows"][0]["files"] if f["path"] == "skills/demo/SKILL.md"][0]
        assert item["status"] == "STALE", item
        assert item["loaded"] != item["at_reference"], (
            f"both hashes must travel, and they must DIFFER: {item}"
        )

def test_the_binding_arm_is_QUIET_when_the_loaded_law_MATCHES_the_reference() -> None:
    """The control. Without it an arm that reds on every round would pass the probe above --
    and would teach the next reader to ignore it, which is the false RED #146's ruling warns
    of. It also proves the fixture is a real comparison: the same files, the same reference."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp))
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert problems == [], problems
        assert cov["stale"] == [] and cov["missing_local"] == [], cov
        assert len(cov["rows"][0]["files"]) == 1, cov["rows"][0]["files"]
        assert cov["rows"][0]["files"][0]["status"] == "equal", cov["rows"][0]["files"]
        assert cov["reference_ref"] == reference, cov["reference_ref"]

def test_the_binding_arm_reads_CONTENT_and_is_not_disarmed_by_an_IDENTICAL_rewrite() -> None:
    """The ruling's own clause (n=3137): the predicate is a CONTENT hash, NEVER a timestamp.

    A rewrite of identical bytes moves the mtime and changes no law -- this factory has
    already logged that as an instrument error, and a timestamp predicate here would red a
    healthy binding every time a lane touched the file. The probe asserts the mtime really
    moved, so it cannot pass by the rewrite having been a no-op.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp))
        path = repo / "skills" / "demo" / "SKILL.md"
        before = path.stat().st_mtime_ns
        body = path.read_text(encoding="utf-8")
        path.write_text(body, encoding="utf-8")
        os.utime(path, ns=(before + 10_000_000_000, before + 10_000_000_000))
        assert path.stat().st_mtime_ns != before, "the probe must actually move the mtime"

        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert problems == [], (
            f"an identical rewrite changes no law and must not be a finding: {problems}"
        )
        assert cov["stale"] == [], cov

def test_the_binding_arm_REDs_a_COPY_where_the_profile_owes_a_SYMLINK() -> None:
    """The resolution half, which #79 owns and this arm must not go blind to: a profile that
    carries a COPY of the law serves whatever it copied, forever, and no hash can see it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, profile, declaration, reference = _binding_fixture(root)
        entry = profile / "skills" / "demo"
        entry.unlink()
        shutil.copytree(repo / "skills" / "demo", entry)
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert any("not a symlink" in p for p in problems), problems
        assert cov["rows"][0]["resolution"] == "NOT A SYMLINK", cov["rows"]

def test_the_binding_arm_REDs_a_symlink_that_RESOLVES_ELSEWHERE() -> None:
    """A symlink is not enough: it must resolve to the source THIS repo declares. A link into
    a sibling checkout -- or into another repository entirely -- serves law this repo does not
    author, and it resolves perfectly while doing so."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, profile, declaration, reference = _binding_fixture(root)
        other = root / "other" / "skills" / "demo"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("someone else's law\n", encoding="utf-8")
        entry = profile / "skills" / "demo"
        entry.unlink()
        entry.symlink_to(other)
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert any("RESOLVES ELSEWHERE" in p or "not `skills/demo`" in p for p in problems), problems
        assert cov["rows"][0]["resolution"] == "RESOLVES ELSEWHERE", cov["rows"]

def test_the_binding_arm_does_NOT_RED_a_SIBLING_worktree_of_the_SAME_repo() -> None:
    """The false-RED the arm must NOT raise, and the reason it compares COMMON DIRS.

    Under the worktree law a lane works in a worktree while the profile may load the SHARED
    tree, so two DIFFERENT paths are routinely ONE repository. A path comparison would red
    the very shape the law prescribes -- and a guard that fires on the prescribed shape is
    the one its readers learn to ignore. The common dir is what tells the two apart, so the
    probe holds that split: the sibling serves the same law file at the same relative path,
    the bytes match the reference, and there is NO finding.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, profile, declaration, reference = _binding_fixture(root)
        sib = _sibling(repo, root)
        entry = profile / "skills" / "demo"
        entry.unlink()
        entry.symlink_to(sib / "skills" / "demo")
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert cov["rows"][0]["resolution"] == "resolved", (
            f"a sibling worktree of the SAME repo serves this repo's own law at the "
            f"declared path: {cov['rows']}"
        )
        assert not problems, (
            f"the worktree shape the law prescribes must not be a finding: {problems}"
        )

def test_the_binding_arm_REDs_a_law_file_the_reference_does_NOT_publish() -> None:
    """A law file the profile serves and the repository never published is either local-only
    or moved upstream; both are staleness, and a hash over local files alone would read the
    first as clean."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp))
        (repo / "skills" / "demo" / "local-only.md").write_text("local\n", encoding="utf-8")
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert any("does not exist at" in p for p in problems), problems
        assert cov["stale"] == ["skills/demo/local-only.md"], cov

def test_the_binding_arm_REDs_a_law_file_the_reference_PUBLISHES_and_the_tree_LACKS() -> None:
    """The OTHER direction, and the reason the arm lists the reference's own tree: the #443
    clause landed inside an existing file, but a NEW clause file upstream is the same
    staleness in a shape a local-only hash can never see."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(
            Path(tmp), behind=True, publish_extra="newer.md"
        )
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert cov["missing_local"] == ["newer.md"], cov
        assert any("ABSENT from the loaded tree" in p for p in problems), problems

def test_the_binding_arm_is_NOT_RUN_when_the_repo_declares_no_binding() -> None:
    """A factory that never adopted the manifest is not measured against one, and the reason
    is STATED -- an arm that silently read clean over zero declarations would be the exact
    found-nothing-is-not-clean defect this file's doctrine forbids."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp))
        declaration.unlink()
        problems, cov = _run_arm(repo, profile, declaration, reference)
        assert problems == [], problems
        assert "declares no binding" in cov["binding_reason"], cov
        assert cov["rows"] == [], cov

def test_the_binding_arm_REDs_an_UNREADABLE_reference_rather_than_reading_clean() -> None:
    """'I could not ask' and 'the law is level' are different facts. With no reference to
    compare against, the arm has no verdict to give -- and must say so, never pass."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, _ = _binding_fixture(Path(tmp))
        problems, cov = _run_arm(repo, profile, declaration, None)
        assert any("no `origin/main` to compare" in p for p in problems), problems
        assert "unreadable reference is never a clean result" in cov["binding_reason"], cov

def test_the_binding_arm_rides_the_LEG_and_its_keys_do_not_COLLIDE_with_the_legs_own() -> None:
    """#3137: the detector RIDES the existing leg -- no new instrument. It must therefore
    reach the report through the leg, and its coverage must be NAMESPACED: the arm and the
    leg both carry a `stale` list, and a flat merge silently overwrote the leg's commit list
    with the arm's law-file list -- which read as a clean round on the leg's own probe."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, profile, declaration, reference = _binding_fixture(Path(tmp), behind=True)
        now = dt.datetime.now(dt.timezone.utc)
        leg = RUNNER.publish_freshness_leg(
            repo=repo, remote="origin", branch="main", read_at="probe", now=now,
            profile_root=profile,
        )
        assert leg["name"] == "publish-freshness", leg["name"]
        assert any("skills/demo/SKILL.md is STALE" in p for p in leg["problems"]), leg["problems"]
        assert leg["coverage"]["binding"]["stale"] == ["skills/demo/SKILL.md"], (
            leg["coverage"]["binding"]
        )
        assert all(not str(s).endswith(".md") for s in leg["coverage"]["stale"]), (
            f"the leg's own commit `stale` list must survive beside the arm's: "
            f"{leg['coverage']['stale']}"
        )
        text = RUNNER.render(
            [leg], [], slug="owner/repo", read_at="2026-10-16T00:00:00Z", issues=[]
        )
        assert "binding freshness:" in text, text
        assert "skills/demo/SKILL.md" in text, text
        assert "CONTENT only" in text, text

def test_a_round_that_fired_BEFORE_the_declared_bound_is_EXCUSED_and_named() -> None:
    """Acceptance 1: a pre-bound round is excused, and the excuse NAMES it.

    The measured instances are `factory-template-weekly` (round 2026-09-21, four days
    before the convention) and `factory-growth-map-biweekly` (round 2026-09-16, nine days
    before). Both fired when no receipt was possible, and both were reported MISSING.
    """
    leg = _duty_leg([_duty_row(last_run_at="2026-09-21T06:00:27Z")], [])
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["duties_judged"] == [], "a pre-bound round is NOT judged"
    assert leg["coverage"]["rounds_excused_by_bound"] == 1, leg["coverage"]
    excuse = [e for e in leg["excused"] if "BEFORE the declared" in e]
    assert len(excuse) == 1, leg["excused"]
    text = excuse[0]
    assert "factory-registry-attest" in text, text
    assert "9ec28cec" in text, "the excuse must name the cron row it excused, by id"
    assert _DUTY_BOUND in text, f"the excuse must print the bound it applied: {text}"
    assert "NEVER backfilled" in text, text

def test_the_bound_NARROWS_the_population_and_the_leg_STILL_REDs_after_it() -> None:
    """Acceptance 2, the negative control — the bound must not silence the leg.

    A bound that excused everything would pass acceptance 1 and read as a clean run, so
    the two rounds are driven TOGETHER: the pre-bound one excused, the post-bound one
    still RED. This is the arm that proves the bound narrows rather than hides.
    """
    leg = _duty_leg(
        [_duty_row(name="factory-old", last_run_at=_plus(_DUTY_BOUND, -48),
                   row_id="aaaa1111-0000-0000-0000-000000000001"),
                  _duty_row(name="factory-new", last_run_at=_DUTY_FIRE,
                   row_id="bbbb2222-0000-0000-0000-000000000002")],
        [],
    )
    assert leg["coverage"]["rounds_excused_by_bound"] == 1, leg["coverage"]
    problems = [p for p in leg["problems"] if "NO duty receipt" in p]
    assert len(problems) == 1, problems
    assert "factory-new" in problems[0], problems
    assert "factory-old" not in problems[0], "the excused round must not also be a problem"

def test_an_UNDECLARED_bound_REFUSES_instead_of_judging_every_round() -> None:
    """Acceptance 4: no declaration is a REFUSAL, never the pre-fix behaviour arriving
    as a clean run. Judging the whole population unbounded is exactly what #175 exists
    to stop, so a tree that declares nothing must be told so rather than shown green.
    """
    leg = _duty_leg([_duty_row()], [], repo=_duty_tree(invariants={}))
    assert len(leg["problems"]) == 1, leg["problems"]
    refusal = leg["problems"][0]
    assert "duty_receipt_declared" in refusal, refusal
    assert "REFUSED" in refusal, refusal
    assert leg["coverage"]["duties_judged"] == [], (
        "no round may be judged while the bound is unreadable — that is the unbounded "
        "pre-fix behaviour arriving silently")
    assert leg["coverage"]["bound"] == "", leg["coverage"]
    assert leg["coverage"]["bound_refusal"], leg["coverage"]

def test_a_MALFORMED_bound_REFUSES_with_the_reader_s_own_problems() -> None:
    """A declared-but-unreadable bound is a DEFECT, never a skip and never a pass.

    The reader's own policy (absent SKIPS, malformed FAILS) is mapped here onto
    refuse-vs-refuse, because for this leg an absent declaration is also not a licence to
    judge unbounded. The distinction survives in the WORDING, which is what a reader of
    the report needs in order to act on it.
    """
    leg = _duty_leg([_duty_row()], [], repo=_duty_tree(declaration="not json {{{"))
    assert len(leg["problems"]) == 1, leg["problems"]
    refusal = leg["problems"][0]
    assert "cannot be read" in refusal, refusal
    assert leg["coverage"]["duties_judged"] == [], leg["coverage"]

def test_the_bound_is_FACTORY_DATA_read_through_the_ONE_reader() -> None:
    """Acceptance 3: the instant is declared factory data, never a second constant.

    A bootstrapped factory's history is its own, so a leg that hardcoded this factory's
    date would judge a tree it does not describe — the same reason the boundary-reading
    gates declare theirs. The grep is the whole probe: no instant of the bound may appear
    in the runner, and the key must resolve through `tests/ledger_boundary.py`.
    """
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "2026-09-25T07:01:07" not in source, (
        "the bound instant is hardcoded in the leg; it belongs in docs/ledger-invariants.json")
    assert RUNNER.DUTY_RECEIPT_BOUNDARY_KEY == "duty_receipt_declared", source
    reader = RUNNER.load_module("ledger_boundary", RUNNER.LEDGER_BOUNDARY)
    try:
        bound, text = reader.declared_boundary(REPO, RUNNER.DUTY_RECEIPT_BOUNDARY_KEY)
    except reader.SkipGate as exc:
        # The bound is FACTORY DATA (#78 clause b) and this tree declares none, so there
        # is no live declaration for the probes to agree with. `ledger_boundary.py`
        # states the outcome: SKIP, with the reason. The two probes above still ran —
        # only the agreement is set aside — so the skip is narrow, not a blanket pass.
        _declared_skip("the bound is factory data", str(exc))
        return
    except reader.GateError as exc:
        raise AssertionError(
            f"the boundary declaration is unreadable: {exc}"
        ) from exc
    assert text == _DUTY_BOUND, f"the probes and the live declaration disagree: {text}"

def test_the_leg_prints_the_bound_beside_the_population_it_judged() -> None:
    """Acceptance 1's second half: the bound is PRINTED, so a clean verdict can never be
    mistaken for an unbounded one that happened to find nothing.

    Driven through main() rather than the leg alone, because a bound that exists only in
    the data and never reaches the report is a bound nobody can audit. The assertion is
    portable on purpose: a bootstrapped factory declares no key and prints UNDECLARED,
    which satisfies the same property — the reader is always told WHICH bound applied.
    """
    rc, out, err = _run([], [], cron_rows=[_duty_row()], prefixes=["factory-"])
    assert rc == 1, (rc, out[-2000:], err[-2000:])  # the fixture round carries no receipt
    assert "LEG duty-receipt" in out, out
    assert "backward bound `duty_receipt_declared`" in out, out[-3000:]
    assert "forward residual:" in out, out[-3000:]
    assert (_DUTY_BOUND in out) or ("UNDECLARED" in out), (
        "the run must print either the instant it bounded against or say plainly that "
        f"no bound is declared: {out[-3000:]}")

def test_the_pacemaker_presence_leg_NAMES_an_owner_with_no_wake() -> None:
    """THE BITING PROBE. A register-declared owner with no inbound wake is NAMED.

    The row population is NON-EMPTY and carries a wake for a DIFFERENT session, so a clean
    verdict cannot come from an empty read — the failure is found in a populated table,
    which is exactly the #253 shape (a deleted row leaves the rest intact).
    """
    rows = [{"name": "factory-other", "prompt": "", "deliver_to": "session:SOMEONE-ELSE"}]
    leg = _presence_leg(rows)
    assert leg["status"] == "ASSERTED", leg
    assert len(leg["problems"]) == 3, leg["problems"]
    hq = [p for p in leg["problems"] if p.startswith("HQ")]
    assert len(hq) == 1, leg["problems"]
    assert "U-HQ" in hq[0] and "NO inbound wake" in hq[0], hq
    assert "HQ (U-HQ): NO WAKE" in leg["coverage"]["owners"], leg["coverage"]["owners"]
    assert leg["coverage"]["owners_declared"] == 3, leg["coverage"]

def test_the_pacemaker_presence_leg_is_QUIET_when_a_woken_sibling_is_present() -> None:
    """THE CONTROL. The same read that names an unwoken owner must clear a woken one.

    Both wake SHAPES are exercised — HQ by `deliver_to = session:<uuid>`, Triage by a
    prompt-carried notify — so the control proves the leg is not a constant RED and that
    the wake vocabulary is the thinness gate's own, not a `deliver_to`-only test.
    """
    rows = [
        {"name": "factory-hq-pacemaker", "prompt": "", "deliver_to": "session:U-HQ"},
        {"name": "factory-triage-patrol", "prompt": "", "deliver_to": "session:U-TRIAGE"},
    ]
    leg = _presence_leg(rows)
    problems = [p for p in leg["problems"] if p.startswith(("HQ", "Triage"))]
    assert problems == [], problems
    owners = leg["coverage"]["owners"]
    assert any(o.startswith("HQ (U-HQ): woken by factory-hq-pacemaker") for o in owners), owners
    assert any(o.startswith("Triage (U-TRIAGE): woken") for o in owners), owners

def test_a_presence_problem_FAILS_the_run() -> None:
    """A problem the leg reports must reach the run's verdict, never sit in a block only."""
    rows = [{"name": "factory-other", "prompt": "", "deliver_to": "session:SOMEONE-ELSE"}]
    leg = _presence_leg(rows)
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"],
                      presence_fn=lambda *a, **k: leg)
    assert rc == 1, f"a presence problem must FAIL the run, got rc={rc}\n{out}"
    assert "declared periodic process owner with NO inbound wake" in out, out

def test_the_pacemaker_presence_leg_PRINTS_its_examined_population() -> None:
    """A clean read over zero owners must not be indistinguishable from a verified one.

    The render names the register, the owner count, the rows judged and EVERY owner with
    its resolved session and the wake that satisfies it — the population travels with the
    verdict (#242).
    """
    _thin_decl = f"{_WAKE_PROMPT}\n\n{_NONE_DECL}"
    rows = [{"name": "factory-hq-pacemaker", "prompt": _thin_decl,
             "deliver_to": "session:U-HQ"},
            {"name": "factory-triage-patrol", "prompt": _thin_decl,
             "deliver_to": "session:U-TRIAGE"},
            {"name": "factory-measurement-daily", "prompt": _thin_decl,
             "deliver_to": "session:U-SURVEYS"}]
    leg = _presence_leg(rows)
    assert leg["problems"] == [], leg["problems"]
    rc, out, _ = _run([], [], cron_rows=rows, homes=["probe-home"], prefixes=["factory-"],
                      presence_fn=lambda *a, **k: leg)
    assert rc == 0, out
    assert "LEG pacemaker-presence — ASSERTED" in out, out
    assert "3 owner(s) declared" in out, out
    assert "population (owner — resolved session — the wake that satisfies it):" in out, out
    assert "HQ (U-HQ): woken by factory-hq-pacemaker" in out, out
    assert "Surveys (U-SURVEYS): woken by factory-measurement-daily" in out, out
    assert "3 declared periodic owner(s) checked for an inbound wake" in out, out

def test_the_pacemaker_presence_leg_fails_OPEN_when_the_register_is_absent() -> None:
    """An unreadable DECLARATION is NOT RUN with its reason — never a clean read.

    The expected set comes from the register; if the register cannot be read, the leg has
    verified nothing, and a silent clean verdict here is the very failure #315 exists to
    close (the check passing while testing nothing).
    """
    missing = Path(tempfile.mkdtemp(prefix="probe-no-register-")) / "processes.md"
    leg = RUNNER.pacemaker_presence_leg(
        [{"name": "factory-x", "prompt": "", "deliver_to": ""}], [],
        None, None, read_at="2026-10-05T00:00:00Z", prefixes=["factory-"],
        register_path=missing,
    )
    assert leg["status"] == "NOT RUN", leg
    assert leg["problems"] == [], leg
    assert "could not be read" in leg["coverage"]["reason"], leg["coverage"]
    assert str(missing) in leg["coverage"]["reason"], leg["coverage"]
    rc, out, _ = _run([], [], cron_rows=[], homes=["probe-home"], prefixes=["factory-"],
                      presence_fn=lambda *a, **k: leg)
    assert "LEG pacemaker-presence — NOT RUN" in out, out
    assert "NOT RUN: the process register" in out, out

def test_an_owner_with_no_resolvable_session_is_reported_never_excused() -> None:
    """A role the fragment does not map, or a lane with no live session, is a PROBLEM.

    Dropping the owner here would be the leg committing the very failure it exists to
    catch — an owner silently excused. The CAUSE travels in the coverage notes, the
    PROBLEM comes from the pure predicate (one source for the verdict, never two).
    """
    fragment = {"lanes": [{"role": "hq", "thread_id": 21}]}  # Triage/Surveys unmapped
    leg = _presence_leg(
        [{"name": "factory-hq-pacemaker", "prompt": "", "deliver_to": "session:U-HQ"}],
        fragment=fragment,
    )
    assert len(leg["problems"]) == 2, leg["problems"]
    assert all("could not be resolved" in p for p in leg["problems"]), leg["problems"]
    assert any("no lane with role 'triage'" in n for n in leg["coverage"]["resolution_notes"]), \
        leg["coverage"]["resolution_notes"]

def test_the_presence_leg_is_INJECTABLE_and_wired_by_default() -> None:
    """`presence_fn` is a real parameter, and the default is the live wiring."""
    import inspect
    params = inspect.signature(RUNNER.main).parameters
    assert "presence_fn" in params, sorted(params)
    assert hasattr(RUNNER, "live_pacemaker_presence_leg"), "the live wiring must exist"
    assert hasattr(RUNNER, "declared_slug"), "the slug resolver must exist"

def main() -> int:
    checks = [value for name, value in sorted(globals().items())
              if name.startswith("test_") and callable(value)]
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except pytest.skip.Exception:
            continue
        except AssertionError as exc:
            failures.append(f"{check.__name__}: {exc}")
            print(f"  FAIL  {check.__name__} — {exc}")
        else:
            print(f"  PASS  {check.__name__}")
    print()
    if failures:
        print(f"patrol-runner gate FAILED: {len(failures)} check(s)")
        return 1
    ran = len(checks) - len(_SKIPS)
    skipped = f", {len(_SKIPS)} SKIPPED (nothing to judge)" if _SKIPS else ""
    print(f"patrol-runner gate passed: {ran} check(s){skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
