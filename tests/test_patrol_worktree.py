"""Gate: worktree, shared-tree rider and attribution — #220/#241/#242

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
    RUNNER,
    _DUTY_BOUND,
    _DUTY_FIRE,
    _EMPTY_GOAL_STORE,
    _EMPTY_LOG_DIR,
    _EMPTY_SCORES_DIR,
    _NO_CRITERION_EXEMPTIONS,
    _NO_REF_ROLE_EXEMPTIONS,
    _NO_RULING_EXEMPTIONS,
    _OWES_NONE_PROMPT,
    _PROBE_TARGET,
    _delivery,
    _duty_leg,
    _duty_row,
    _fires,
    _issue,
    _plus,
    _probe_kit_pair,
    _rows,
    _run,
    _scratch,
    _stall_row,
    _stub_publish_leg,
    _stub_shared_tree_rider,
    _swept,
    _synthetic_kit,
    main,
    _SKIPS,
)


# --- this leg's own helpers -------------------------------------------------
def _git_repo_with_worktree(root: Path) -> tuple[Path, Path]:
    """`(main_checkout, linked_worktree)` — a real worktree, not a path that looks like one.

    Both are derived from the fixture, so the probe resolves in any factory. A linked
    worktree is the move this factory PRESCRIBES for a diverged tree, which is why the
    attribution defect hid behind the remedy rather than behind an exotic state.
    """
    main = root / "main"
    main.mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"],
                 ["config", "user.email", "probe@example.invalid"],
                 ["config", "user.name", "probe"]):
        subprocess.run(["git", "-C", str(main), *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (main / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(main), "add", "-A"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(main), "commit", "-q", "-m", "one"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    linked = root / "linked"
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(linked)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return main, linked

def _wt_records(*paths: str) -> list[dict]:
    return [{"path": p} for p in paths]

def _wt_dirs(count: int) -> tuple[tempfile.TemporaryDirectory, list[str]]:
    """Real directories for the census fixture.

    The leg classifies a record whose directory is GONE as a missing registration — that
    is `git worktree prune`'s class and the reason the missing-directory list exists — so a
    fixture built from invented paths would be measuring that branch instead of the hazard
    branches under test. Directories are created rather than mocked for that reason.
    """
    tmp = tempfile.TemporaryDirectory()
    paths = []
    for index in range(count):
        path = Path(tmp.name) / f"wt{index}"
        path.mkdir()
        paths.append(str(path))
    return tmp, paths

def _park_row(n, unit, days_ago, question=None, *, now, mention=None):
    """A ledger row that DECLARES a park on `unit` (#535, ruling n=4007).

    The declaration is a `park` EVENT carrying the question as a ref of the DECLARED kind
    `question` -- never the `park:owner:qN` prose token this leg read before #535. The token
    shape is what the ruling removed: n=3339 names `park:owner:q39` in the prose of the row
    that ENDED #313's park, and n=2884 names three parks in a ruling whose subject is a
    fourth unit, so a token scan returns the inverse of one row's meaning and invents a park
    on a bystander from another.

    `question` is left free-form so a probe can write the REFUSED forms as well as the
    accepted one: a park naming NO question at all (pass `None`), and a park whose question
    ref is not a register id. `mention` writes a sentence that NAMES a token in the detail
    while the row's own event stays `park` -- the third acceptance arm, where prose must
    declare nothing.
    """
    body = f"CENSUS DISPOSITION -- {unit} is PARKED AT THE OWNER DESIGN GATE.\n\n"
    if mention:
        body += f"{mention}\n\n"
    body += "The park is an EVENT plus a typed ref, not a prose token."
    refs = [{"question": question}] if question else None
    return _stall_row(n, "park", unit, days_ago, now=now, detail=body.rstrip(), refs=refs)

def _unpark_row(n, unit, days_ago, park_n, *, now, reason="the owner answered"):
    """A ledger row that ENDS a park on `unit` (#535 leg 2).

    The park it supersedes travels as `--ref row:<n>`, which is what makes the pair joinable:
    without it an unpark is a second, unattached claim about state, and "which park did this
    end?" has no answer that is not a guess at row order alone.
    """
    return _stall_row(
        n, "unpark", unit, days_ago, now=now,
        detail=f"UNPARK {unit} -- {reason}.", refs=[{"row": str(park_n)}],
    )

def _disposition_row(n, unit, days_ago, token=None, *, now, mention=None):
    """A ledger row that DECLARES a disposition on `unit` (#473).

    The token stands ALONE on the last line, which is the shape a ruling uses and the shape
    the reader requires. `mention` writes a sentence that QUOTES a token without declaring
    one -- the `n=2883` lesson, which withdrew a park on exactly those terms -- and `token`
    is left free-form so a probe can write the REFUSED forms as well as the accepted one.
    """
    body = f"RULING -- {unit} is DISPOSED OF.\n\n"
    if mention:
        body += f"{mention}\n\n"
    if token:
        body += token
    return _stall_row(n, "ruling", unit, days_ago, now=now, detail=body.rstrip())

def _rider(**over) -> dict:
    base = {
        "status": "ASSERTED",
        "read_at": "2026-10-03T02:00:00Z",
        "base": "origin/main",
        "base_sha": "abc1234",
        "dirty": [],
        "blocking": [],
        "reason": None,
        "reconciles": False,
    }
    base.update(over)
    return base

# --- this leg's tests -------------------------------------------------------
def test_probe_the_common_dir_is_shared_by_a_linked_worktree() -> None:
    """The mechanism: a worktree and its main checkout resolve to ONE repository identity.

    Keyed on the CHECKOUT they are two paths and neither matches the manifest's declared
    repo from the other — which is how a lane patrolling from a worktree silently judged
    nobody.
    """
    tmp_path = _scratch()
    main, linked = _git_repo_with_worktree(tmp_path)
    a, b = RUNNER.git_common_dir(main), RUNNER.git_common_dir(linked)
    assert a is not None and b is not None, (a, b)
    assert a == b, f"the common dir must be shared: main={a} linked={b}"
    assert a != linked.resolve(), "a worktree's own path is NOT its repository identity"

def test_probe_the_RELATIVE_OUTPUT_TRAP_is_pinned() -> None:
    """THE TRAP, pinned so a naive edit REDs instead of silently returning [].

    From the MAIN checkout `git rev-parse --git-common-dir` prints the RELATIVE string
    ".git". So `Path(raw).resolve()` resolves against the CALLER's cwd and yields a path
    that matches nothing — the SAME empty result the defect produces, wearing the shape of
    a fix. The repo-relative join is what makes it correct from both ends.
    """
    tmp_path = _scratch()
    main, linked = _git_repo_with_worktree(tmp_path)
    raw = subprocess.run(["git", "-C", str(main), "rev-parse", "--git-common-dir"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert raw == ".git", (
        f"the premise of this probe is that the main checkout prints a RELATIVE path; it "
        f"printed {raw!r} — re-derive the trap before trusting the fix"
    )
    # The naive form, resolved from a cwd that is NOT the repo — the exact edit a future
    # reader would make.
    naive = (tmp_path / raw).resolve()
    assert naive != RUNNER.git_common_dir(main), (
        "the naive `Path(raw).resolve()` must NOT accidentally be correct"
    )
    # And the repo-relative join IS correct, from both ends.
    assert (main / raw).resolve() == RUNNER.git_common_dir(main)
    assert RUNNER.git_common_dir(main) == RUNNER.git_common_dir(linked)

def test_probe_an_empty_prefix_set_makes_the_three_cron_legs_NOT_RUN() -> None:
    """#242 clause 4: prefixes == [] is an UNATTRIBUTABLE population, never a clean box.

    The legs already carry the discriminating counter and `declared_prefixes`' own
    docstring already obliged the caller; ONE caller with THREE call sites complied with
    neither. So a lane from a worktree read `ASSERTED ... 0 problems` from a leg that
    judged nothing — and, in the duty-receipt case, a positive FALSE CONCLUSION.
    """
    rows = [{"name": "factory-x-job", "home": "probe-home", "enabled": True,
             "prompt": "do a thing", "deliver_to": "", "last_run_at": _DUTY_FIRE}]
    with tempfile.TemporaryDirectory() as tmp:
        out = io.StringIO()
        RUNNER.main(
            [], board_fn=lambda slug: [], slug_fn=lambda: "owner/repo",
            rows_fn=lambda: [], cron_rows_fn=lambda: (rows, ["probe-home"], []),
            cron_fires_fn=lambda: [],
            prefixes_fn=lambda: [],
            log_dir=Path(tmp) / "logs",
            scores_dir_fn=lambda: _EMPTY_SCORES_DIR,
            kit_manifest=_synthetic_kit(Path(tmp), files={"tools/a.py": b"a"},
                                        members={})[0],
            fleet_manifest=_synthetic_kit(Path(tmp), files={"tools/a.py": b"a"},
                                          members={})[1],
            out=lambda *a, **k: print(*a, file=out, **k),
            err=lambda *a, **k: None,
            publish_fn=_stub_publish_leg,
            shared_tree_fn=_stub_shared_tree_rider,
            # #133: the driverless-lane leg's goal store and its turn-in-flight read are
            # injected here for the same reason every other live surface is -- and the
            # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
            # granting one, so a probe that never asserts a driver cannot read one.
            driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
            driverless_turn_open_fn=lambda: {},
            # #330: the ref-role store is injected for the same reason the ruling table is.
            ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
        )
        text = out.getvalue()

    for name in ("cron-thinness", "notify-receipt", "duty-receipt"):
        block = text.split(f"LEG {name}")[1].split("LEG ")[0]
        assert "NOT RUN" in block.split("\n")[0], f"{name} must be NOT RUN: {block!r}"
        assert "UNATTRIBUTED" in block, f"{name} must name its unattributed population: {block!r}"
        assert "resolves to no factory" in block, (
            f"{name} must name the manifest reason: {block!r}"
        )
    assert "so no duty owes a receipt on this box" not in text, (
        "the reason must not assert a fact about the box over an empty population"
    )

def test_an_OWES_NONE_declaration_reads_OWES_NONE_and_hunts_no_receipt() -> None:
    """#424 items 1+2+3-clause-3 — ordered at n=2723, re-sequenced at n=3228.

    `factory-publish` runs the pusher in the cron's OWN session, and the ledger's actor set is
    closed — SKILL.md section 11 names the pusher a TOOL, not a lane — so its duty owes no
    receipt at all. Before the bucket the leg read `none` as a STEM, hunted `none-<round>*`,
    found nothing, and RED every round: the false MISSING the amendment ruling reproduced by
    running this very reader hermetically.
    """
    row = _duty_row(prompt=_OWES_NONE_PROMPT)
    leg = _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0))
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["jobs_owing_none"] == 1, leg["coverage"]
    assert leg["coverage"]["owes_none_jobs"] == ["factory-registry-attest"], leg["coverage"]
    # THE TWO SILENCES ARE COUNTED APART: a row that DECLARED it owes none is not a row that
    # declared nothing, and folding them into one number reports the second as the first.
    assert leg["coverage"]["jobs_declaring_receipt"] == 0, leg["coverage"]
    assert leg["coverage"]["jobs_undeclared"] == 0, leg["coverage"]
    # AND THE BUCKET REACHES THE REPORT. Driven from a MIXED population on purpose: a leg
    # whose judged population is empty renders through the generic NOT-RUN block, so an
    # owes-none row ALONE could never prove the bucket is PRINTED — only that it is counted.
    # `factory-publish` owes none beside a duty that does, which is the live shape.
    owes_none = _duty_row(name="factory-publish", prompt=_OWES_NONE_PROMPT,
                          row_id="e30bfc83-3fee-400a-945d-e74b962c142e")
    rc, out, err = _run([], [], cron_rows=[owes_none, _duty_row()], prefixes=["factory-"],
                        cron_fires=_fires((0.5,)))
    assert "OWES NONE" in out, out[-2500:]
    assert "factory-publish" in out, out[-2500:]
    assert "declare NOTHING and are NOT JUDGED" in out, out[-2500:]

def test_the_OWES_NONE_bucket_is_what_stops_the_false_MISSING() -> None:
    """The neuter probe, and without it the arm above proves nothing.

    The neutered reader differs from the live one in ONE respect — whether the token `none` is
    a declaration that nothing is owed or a stem to hunt — so a verdict that MOVES under it is
    attributable to the bucket rather than to the fixture.
    """
    row = _duty_row(prompt=_OWES_NONE_PROMPT)
    assert _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0))["problems"] == []

    real = RUNNER.declared_receipt_disposition

    def _pre_bucket(prompt):
        disposition, stem = real(prompt)
        return ("declares", stem or RUNNER.RECEIPT_OWES_NONE_TOKEN) if (
            disposition == "owes_none") else (disposition, stem)

    RUNNER.declared_receipt_disposition = _pre_bucket
    try:
        neutered = _duty_leg([row], [], read_at=_plus(_DUTY_FIRE, 5.0))
    finally:
        RUNNER.declared_receipt_disposition = real
    assert neutered["problems"], (
        "reading `none` as a STEM must RED the round again — the bucket is the only thing "
        f"standing between this row and a false MISSING every round: {neutered['coverage']}"
    )
    assert "NO duty receipt" in neutered["problems"][0], neutered["problems"][0]

def test_the_SUPPRESSION_predicate_is_anchored_to_the_DAEMONS_own_wording() -> None:
    """#477. The anchor is the daemon's EMITTED text, read here from the CONSTANT rather than
    from a copied literal — so a change in that wording moves this probe instead of silently
    un-excusing every gated round on the box."""
    assert RUNNER.fire_is_suppressed(
        f"Trigger condition not met (exit_code=0, output_bytes=0). "
        f"{RUNNER.CRON_SUPPRESSION_MARKER}."
    ), "the daemon's own suppression wording must read as suppressed"
    assert RUNNER.fire_is_suppressed(
        f"Trigger condition not met (exit_code=1, output_bytes=19070). "
        f"{RUNNER.CRON_SUPPRESSION_MARKER}."
    ), "the marker is the wording, not the exit code — both codes are emitted"
    assert not RUNNER.fire_is_suppressed(""), "an empty run record is not a suppression"
    assert not RUNNER.fire_is_suppressed("the round completed. duty=completed"), (
        "a round that RAN and declared its duty must never read as suppressed"
    )

def test_a_SUPPRESSED_round_is_EXCUSED_and_never_a_missing_duty() -> None:
    """#477 on the round the leg judges directly.

    The round fired on time, the run is stored `status=success`, and no receipt exists — the
    exact shape this leg exists to red, and legitimate all the same, because the job's own
    trigger gate never let the lane wake.
    """
    fires = _fires((0.5,), suppressed=True)
    leg = _duty_leg([_duty_row()], [], fires=fires, read_at=_plus(_DUTY_FIRE, 5.0))
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["rounds_excused_by_suppression"] == 1, leg["coverage"]
    assert any(RUNNER.CRON_SUPPRESSION_MARKER in e for e in leg["excused"]), leg["excused"]

def test_the_SUPPRESSION_excuse_is_what_stops_the_red_round() -> None:
    """The neuter probe for #477: blind the leg to the fire's flag and the round REDS again.

    Built by REMOVING the field the live source carries, not by editing a constant, because
    that is the defect exactly — before #477 the reader did not carry it at all.
    """
    fires = _fires((0.5,), suppressed=True)
    blind = [{k: v for k, v in f.items() if k != "suppressed"} for f in fires]
    assert _duty_leg([_duty_row()], [], fires=fires,
                     read_at=_plus(_DUTY_FIRE, 5.0))["problems"] == []
    neutered = _duty_leg([_duty_row()], [], fires=blind, read_at=_plus(_DUTY_FIRE, 5.0))
    assert neutered["coverage"]["rounds_excused_by_suppression"] == 0, neutered["coverage"]
    assert len(neutered["problems"]) == 1, neutered["problems"]
    assert "NO duty receipt" in neutered["problems"][0], neutered["problems"][0]

def test_a_SUPPRESSED_PRIOR_round_is_excused_on_the_round_the_leg_JUDGES() -> None:
    """#477 on the #281 path, which is the LIVE case rather than a corner.

    `factory-questions-redeliver` carries a 1800 s default residual against a 6 h cadence, so
    its newest round is ALWAYS in flight and the round this leg actually judges is the prior
    one. An excuse wired only to the newest round would leave the live defect standing.
    """
    row = _duty_row(last_run_at=_plus(_DUTY_BOUND, 24.5))
    newest = _fires((24.5,))[0]                       # the round that RAN
    prior = _fires((0.25,), suppressed=True)[0]       # the PRIOR round, suppressed
    fires = [prior, newest]
    leg = _duty_leg([row], [], fires=fires, read_at=_plus(_DUTY_BOUND, 24.5 + 0.1))
    assert leg["coverage"]["rounds_judged_by_fallback"] == 0, (
        f"this fixture must be excused on the PRIOR round, not judged: {leg['coverage']}"
    )
    assert leg["problems"] == [], leg["problems"]
    assert leg["coverage"]["rounds_excused_by_suppression"] == 1, leg["coverage"]
    assert any("PRIOR round" in e for e in leg["excused"]), leg["excused"]

def test_a_NON_suppressed_round_still_REDS_so_the_excuse_is_no_false_CLEAN() -> None:
    """The alternative #477's ruling REFUSED, kept as a probe.

    A declaration-based excuse ("this duty is conditional") would also cover a conditional duty
    that genuinely ran and produced nothing. This is that case: the fire record is present,
    carries no suppression wording, and the round must still RED.
    """
    leg = _duty_leg([_duty_row()], [], fires=_fires((0.5,)),
                    read_at=_plus(_DUTY_FIRE, 5.0))
    assert leg["coverage"]["rounds_excused_by_suppression"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_a_round_no_fire_record_MATCHES_is_JUDGED_and_never_excused() -> None:
    """An unreadable or mismatched fire table must not silently excuse every duty on the box.

    The round's instant is matched to a record by INSTANT, so a record belonging to another
    job can never stand in for it — and a suppression that cannot be ATTRIBUTED to this round
    is one this leg must not act on.
    """
    foreign = {"job_id": "some-other-job", "job_name": "some-other-job",
               "started_at": _DUTY_FIRE, "content": f"{RUNNER.CRON_SUPPRESSION_MARKER}.",
               "suppressed": True}
    leg = _duty_leg([_duty_row()], [], fires=[foreign], read_at=_plus(_DUTY_FIRE, 5.0))
    assert leg["coverage"]["rounds_excused_by_suppression"] == 0, leg["coverage"]
    assert len(leg["problems"]) == 1, leg["problems"]
    assert "NO duty receipt" in leg["problems"][0], leg["problems"][0]

def test_probe_the_duty_reason_NAMES_its_population_and_refuses_the_conclusion() -> None:
    """#242 clause 5. The old text ended "so no duty owes a receipt on this box" — a
    POSITIVE claim about the box drawn from an enumeration that can be empty. An empty
    population supports a statement about the READ, never a conclusion about duties.
    """
    rows = [{"name": "factory-x-job", "home": "probe-home", "enabled": True,
             "prompt": "no receipt declaration here", "deliver_to": "",
             "last_run_at": _DUTY_FIRE}]
    leg = RUNNER.duty_receipt_leg(rows, ["probe-home"], [], ["factory-"], [],
                                  read_at="probe")
    # the STATUS moved with #506 (a census that declares nothing now carries a finding, so
    # the leg is ASSERTED); the clause-5 property below is about the REASON and is unchanged
    assert leg["status"] == "ASSERTED", leg["status"]
    reason = leg["reason"]
    assert "NONE names a receipt STEM to judge" in reason, reason
    assert "NO DUTY WAS JUDGED" in reason, reason
    assert "never a finding" in reason, reason
    assert "so no duty owes a receipt on this box" not in reason, reason
    assert "1 enabled row(s) this factory declares" in reason, (
        f"the reason must name the population it enumerated: {reason}"
    )
    # #424 item 2 / #477: the reason must separate the TWO ways a row can be silent about a
    # receipt -- declaring it OWES NONE (a declaration, read and honoured) and carrying no
    # `receipt_subject:` line at all (a silence the leg cannot act on). A reason that prints
    # one number for both reports the second as the first.
    assert "declares it OWES NONE" in reason, reason
    assert "carries no `receipt_subject:` line at all" in reason, reason

def test_probe_every_probe_is_callable_by_the_SCRIPT_runner() -> None:
    """This file has TWO runners, and a probe must satisfy both (#242, measured).

    `main()` calls every `test_*` with NO arguments, so a probe that takes `tmp_path`
    passes under pytest and raises TypeError under the audit's own invocation — a probe
    that is green in one runner and absent in the other. Measured while landing #242: two
    of the four new probes took `tmp_path` and the script form died on the first of them
    while pytest reported 119 passed.
    """
    import inspect

    offenders = []
    for name, value in sorted(globals().items()):
        if not (name.startswith("test_") and callable(value)):
            continue
        required = [
            p for p in inspect.signature(value).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if required:
            offenders.append(f"{name} requires {[p.name for p in required]}")
    assert offenders == [], (
        "every probe must be callable with no arguments, because main() runs them that "
        "way: " + "; ".join(offenders)
    )

def test_the_worktree_leg_NAMES_both_hazard_classes_with_their_paths() -> None:
    """#220 clause 3: the two hazard classes, WITH THE PATHS.

    A count without the paths sends the reader to `git worktree list` to find what the leg
    already knew, which is the shape that makes a report decorative. Both classes are
    driven here, and the population is asserted too — `scratch` is the complement of the
    FIRST record, because the first record is the tree the command was run from.
    """
    tmp2, dirs = _wt_dirs(4)
    main, a, b, c = dirs
    with tmp2:
        records = _wt_records(main, a, b, c)
        states = {
            main: {"dirty": [], "ahead": 0, "problems": []},
            a: {"dirty": [" M x"], "ahead": 0, "problems": []},
            b: {"dirty": [], "ahead": 3, "problems": []},
            c: {"dirty": [], "ahead": 0, "problems": []},
        }
        leg = RUNNER.worktree_leg(
            read_at="probe",
            records_fn=lambda repo=None: (records, None),
            state_fn=lambda path, **kw: states[path],
        )
        cov = leg["coverage"]
        assert leg["status"] == "ASSERTED", leg
        assert cov["worktrees_total"] == 4, cov
        assert cov["worktrees_scratch"] == 3, cov
        assert cov["missing_directory"] == [], cov
        assert cov["unreachable_commits"] == [{"path": b, "ahead": 3}], cov
        assert cov["uncommitted_work"] == [{"path": a, "paths": 1}], cov
    assert cov["hazard_classes"] == ["unreachable-commit", "uncommitted-work"], cov
    assert cov["base_ref"] == "origin/main", cov
    assert cov["instrument"] == "git worktree list --porcelain / git worktree prune", cov

def test_the_worktree_leg_REPORTS_and_never_removes() -> None:
    """The refusal, asserted STRUCTURALLY rather than promised in prose.

    The ruling refused widening the cleanliness instrument's glob because hygiene's remedy
    is REMOVAL, and removal on a worktree holding uncommitted work destroys it. So this leg
    must hold no mutating path at all — and a promise in a docstring is not a mechanism.
    The module's own source is scanned for every form that would remove or mutate a
    worktree, and the leg declares `removes: False` so a reader of the REPORT is told the
    same thing the code says.
    """
    source = (RUNNER.REPO / "tools" / "patrol_host_state.py").read_text(encoding="utf-8")
    forbidden = ("worktree", "prune"), ("worktree", "remove"), ("shutil.rmtree",),
    for needle in ("prune", "remove"):
        assert f'"worktree", "{needle}"' not in source, f"a worktree {needle} call is present"
    assert "shutil.rmtree" not in source, "an rmtree is present in the runner"
    del forbidden

    tmp, (main, scratch) = _wt_dirs(2)
    with tmp:
        leg = RUNNER.worktree_leg(
            read_at="probe",
            records_fn=lambda repo=None: (_wt_records(main, scratch), None),
            state_fn=lambda path, **kw: {"dirty": [], "ahead": 0, "problems": []},
        )
    assert leg["coverage"]["removes"] is False, leg["coverage"]

def test_the_worktree_leg_is_NOT_RUN_when_the_census_cannot_be_read() -> None:
    """An unreadable census is not an empty one, and an empty one is not a clean one.

    Both arms: the instrument failing (an error from `git worktree list`), and the
    instrument returning NO records — which a repository can never legitimately do, since
    it always carries at least its main worktree. Each must state its reason rather than
    render as a clean verdict.
    """
    failed = RUNNER.worktree_leg(
        read_at="probe",
        records_fn=lambda repo=None: ([], "`git worktree list` could not run: boom"),
        state_fn=lambda path, **kw: {"dirty": [], "ahead": 0, "problems": []},
    )
    assert failed["status"] == "NOT RUN", failed
    assert "could not be read" in failed["coverage"]["reason"], failed["coverage"]

    empty = RUNNER.worktree_leg(
        read_at="probe",
        records_fn=lambda repo=None: ([], None),
        state_fn=lambda path, **kw: {"dirty": [], "ahead": 0, "problems": []},
    )
    assert empty["status"] == "NOT RUN", empty
    assert "at least its main worktree" in empty["coverage"]["reason"], empty["coverage"]

def test_a_NOT_RUN_worktree_leg_RENDERS_its_reason_never_a_clean_verdict() -> None:
    """The render branch, driven separately: NOT RUN must carry its reason.

    Without this arm a NOT RUN leg could render as an empty block, and an unreadable
    census would then be indistinguishable from a clean one in the only surface a reader
    actually meets -- the report.
    """
    def _stub(*, read_at: str, **_kw) -> dict:
        return {
            "name": "worktree", "status": "NOT RUN", "problems": [], "excused": [],
            "coverage": {"reason": "the worktree census could not be read — probe",
                         "read_at": read_at},
        }

    issues = [_issue(1, "OPEN")]
    # The `ruling` row keeps this fixture inside the round's own population (#332), so the
    # only NOT RUN under test is the worktree leg's.
    rows = _swept(("intake", "#1", 1), ("ruling", "#1", 2))
    out, err = io.StringIO(), io.StringIO()
    rc = RUNNER.main(
        [], board_fn=lambda slug: issues, slug_fn=lambda: "owner/repo",
        rows_fn=lambda: rows, cron_rows_fn=lambda: ([], ["probe-home"], []),
        cron_fires_fn=lambda: [],
        prefixes_fn=lambda: [], log_dir=_EMPTY_LOG_DIR,
        scores_dir_fn=lambda: _EMPTY_SCORES_DIR,
        kit_manifest=_probe_kit_pair()[0], fleet_manifest=_probe_kit_pair()[1],
        out=lambda *a, **k: print(*a, file=out, **k),
        err=lambda *a, **k: print(*a, file=err, **k),
        publish_fn=_stub_publish_leg, worktree_fn=_stub,
        shared_tree_fn=_stub_shared_tree_rider,
        # #133: the driverless-lane leg's goal store and its turn-in-flight read are
        # injected here for the same reason every other live surface is -- and the
        # defaults WITHHOLD the driven claim (empty store, no turn open) rather than
        # granting one, so a probe that never asserts a driver cannot read one.
        driverless_goals_fn=lambda: _EMPTY_GOAL_STORE,
        driverless_turn_open_fn=lambda: {},
        # #330: the ref-role store is injected for the same reason the ruling table is.
        ref_role_exemptions_path=_NO_REF_ROLE_EXEMPTIONS,
        # #507: the criterion-path store, injected for the same reason.
        criterion_exemptions_fn=lambda: _NO_CRITERION_EXEMPTIONS,
        ruling_scope_fn=lambda: RUNNER.UNBOUNDED_SCOPE,
        ruling_exemptions_path=_NO_RULING_EXEMPTIONS,
    )
    text = out.getvalue()
    assert rc == 0, text
    assert "LEG worktree — NOT RUN" in text, text
    assert "NOT RUN: the worktree census could not be read — probe" in text, text
    assert "worktrees: " not in text, text

def test_the_worktree_leg_is_the_thing_that_moves_the_report() -> None:
    """The NON-VACUITY control: the same fixture with and without a hazard.

    One fixture, driven twice — once with a tree ahead of the base and once with none — so
    the difference is attributable to the hazard and not to the fixture. Without this arm
    a leg that always printed empty lists would satisfy every assertion above.
    """
    tmp, (main, scratch) = _wt_dirs(2)
    hazard = {"dirty": [" M x"], "ahead": 2, "problems": []}
    clean = {"dirty": [], "ahead": 0, "problems": []}
    with tmp:
        records = _wt_records(main, scratch)
        with_hazard = RUNNER.worktree_leg(
            read_at="probe", records_fn=lambda repo=None: (records, None),
            state_fn=lambda path, **kw: hazard if path == scratch else clean,
        )
        without = RUNNER.worktree_leg(
            read_at="probe", records_fn=lambda repo=None: (records, None),
            state_fn=lambda path, **kw: clean,
        )
    assert len(with_hazard["coverage"]["unreachable_commits"]) == 1, with_hazard["coverage"]
    assert len(with_hazard["coverage"]["uncommitted_work"]) == 1, with_hazard["coverage"]
    assert without["coverage"]["unreachable_commits"] == [], without["coverage"]
    assert without["coverage"]["uncommitted_work"] == [], without["coverage"]

def test_the_whole_run_PRINTS_the_worktree_population_and_never_a_bare_zero() -> None:
    """The clause that keeps a clean run from being read as "no residue".

    Driven through the REAL `main()`, so the render path is exercised rather than the leg
    alone — the leg returning a correct dict and the report dropping it is exactly the
    half-fix this probes for. The figures are asserted WITH their predicate: the population,
    both hazard classes, the `removes: no` declaration, and the read instant.
    """
    issues = [_issue(1, "OPEN")]
    # `ruling` #1 keeps this fixture inside the round's own population (#332); without it
    # the board-unruled leg REDs and this probe would pass while measuring a red run.
    rows = _rows(("intake", "#1", 1), ("ruling", "#1", 2))
    rc, out, _ = _run(issues, rows)
    assert "LEG worktree — ASSERTED" in out, out
    assert "worktrees: 2 total, 1 scratch" in out, out
    assert "the cleanliness instrument's glob cannot reach" in out, out
    assert "removes: no" in out, out
    assert "unreachable-commit (commits not reachable from origin/main): 1 tree(s)" in out, out
    assert "~ /probe/scratch — 1 commit(s) ahead" in out, out
    assert "uncommitted-work (paths differing from HEAD): 1 tree(s)" in out, out
    assert "~ /probe/scratch — 2 path(s)" in out, out
    assert "read at " in out, out

def test_the_stall_census_leg_BITES_and_discriminates_on_every_neighbour() -> None:
    """#260 acceptance (1), the NON-VACUITY probe: the leg must NAME a never-claimed
    dispatch past its threshold, and must NOT name the four neighbours that look like one.

    The discriminating pairs are the whole point, because the naive predicate the ruling
    was written from -- "the latest dispatch row with no later claim row" -- reports every
    one of them. Measured on this ledger 2026-10-03, that literal form reports 36 units
    where the true population is 20: the extras are claimed-then-RE-DISPATCHED
    (`#132` intake n=836, claim n=837, dispatch n=838, close n=840; `#235` claim n=1674,
    close n=1675, dispatch n=1681) and closed-without-claim. So each of these four is a
    live false positive the leg must keep out, and a probe that supplied only the true
    positive would pass a leg that reported all five.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(901, "OPEN"),    # dispatched 3 d ago, NEVER claimed -> OWED
        _issue(902, "OPEN"),    # dispatched seconds ago -> in flight, below threshold
        _issue(903, "OPEN"),    # dispatched, then CLAIMED -> not owed
        _issue(904, "OPEN"),    # dispatched, then CLOSED by a ledger close row
        _issue(905, "CLOSED"),  # never claimed, but the BOARD carries it closed
    ]
    rows = [
        _stall_row(1, "intake", "#901", 4, now=now),
        _stall_row(2, "dispatch", "#901", 3, now=now),
        _stall_row(3, "dispatch", "#902", 0.01, now=now),
        _stall_row(4, "dispatch", "#903", 5, now=now),
        _stall_row(5, "claim", "#903", 4.9, now=now),
        _stall_row(6, "dispatch", "#904", 6, now=now),
        _stall_row(7, "close", "#904", 5.9, now=now),
        _stall_row(8, "dispatch", "#905", 7, now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #901" in named, f"the never-claimed dispatch must be NAMED\n{named}"
    for quiet in ("#902", "#903", "#904", "#905"):
        assert quiet not in named, (
            f"{quiet} must NOT be reported owed: a below-threshold dispatch is in flight, "
            f"a claimed one has a taker, a closed one is finished, and a board-closed item "
            f"owes no claim\n{named}"
        )
    assert leg["coverage"]["units_owed"] == 1, leg["coverage"]

    # ... and the same fixture through the REAL `main()`: the report must carry the OWED
    # line AND the population it was read from. A leg returning a correct dict while the
    # render drops it is the half-fix this half exists to catch.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "LEG stall-census — ASSERTED" in out, out
    assert "OWED #901" in out, out
    assert "population: 5 dispatched unit(s) -- 1 never claimed" in out, out
    assert "read at " in out, out

def test_the_stall_census_leg_PRINTS_the_tracker_assignee_and_still_reads_OWED() -> None:
    """#423: an assigned-but-unclaimed unit is VISIBLE as assigned, and is STILL OWED.

    TWO FACTS, and the second is what keeps the fix honest.

    (a) An OWED unit whose board issue carries an assignee must NAME that assignee on the
    OWED line. Before this the line rendered an assigned-but-unclaimed unit identically to
    one nobody had touched -- the visibility gap the item names.

    (b) The assignee must NOT clear the OWED verdict. An assignee is a tracker field, not a
    session-derived `claim` row, and reading it as a taker would let an assignment silence
    the andon cord. So the SAME fixture still reports the unit OWED, and the line says so
    in words.

    The discriminating pair is the point: the unassigned unit must NOT carry the assignee
    sentence, or a leg that printed a constant would satisfy (a) alone.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(921, "OPEN", ["leshchenko1979"]),  # assigned, still never claimed -> OWED
        _issue(922, "OPEN"),                       # untouched -> OWED, no assignee text
    ]
    rows = [
        _stall_row(1, "dispatch", "#921", 3, now=now),
        _stall_row(2, "dispatch", "#922", 3, now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #921" in named, f"an assigned-but-unclaimed unit stays OWED\n{named}"
    assert "ASSIGNED to leshchenko1979" in named, (
        f"the tracker assignee must be PRINTED on the OWED line\n{named}"
    )
    assert "an assignee is not a ledger claim" in named, named
    assert leg["coverage"]["units_owed"] == 2, leg["coverage"]
    assert leg["coverage"]["units_owed_assigned"] == 1, leg["coverage"]

    # ... and the UNASSIGNED unit carries no assignee sentence: a leg that printed the
    # sentence unconditionally would pass every assertion above just as well.
    line_922 = [ln for ln in leg["problems"] if "#922" in ln]
    assert line_922 and "ASSIGNED to" not in line_922[0], (
        f"an unassigned unit must not read as assigned\n{line_922}"
    )

    # ... and the same fixture through the REAL `main()`: the assignee reaches the report.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "ASSIGNED to leshchenko1979" in out, out

def test_the_stall_census_leg_holds_a_DECLARED_PARK_out_of_the_owed_total() -> None:
    """#331 clause 1, two-sided: a unit whose OWN row declares `park:owner:<question>` reads
    PARKED, is not a finding, and leaves the owed total -- and the SAME rows with the
    declaration line removed still read OWED, so the park is measured as the thing that
    cleared it.

    The declaration is read off the ROWS rather than off a table this tree edits, and the live
    ledger is the reason: Triage's park rows for #317/#320 (n=2881/n=2882) carry the token as
    their last line and each says in as many words that "this row is the declared park HQ's C1
    defines". A table would never have seen them, so the live need would have gone unmet.

    The live need is #317/#320 -- and #301/#312/#313 on q39 -- units dispatched to a lane that
    lawfully cannot take them, parked on an owner question, re-reported as findings every day
    that question stays open.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(931, "OPEN"), _issue(932, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#931", 5, now=now),
        _park_row(2, "#931", 4, "q32", now=now),   # declared -> PARKED
        _stall_row(3, "dispatch", "#932", 5, now=now),        # undeclared -> stays OWED
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #931" not in named, (
        f"a DECLARED park holds the line out of the OWED findings -- a parked line is not a "
        f"finding\n{named}"
    )
    parked = "\n".join(leg["coverage"]["parks"])
    assert "PARKED #931" in parked, leg["coverage"]["parks"]
    # The QUESTION and the DECLARING ROW both travel with the verdict: a park a reader cannot
    # trace to the row that declared it is a claim, not a declaration.
    assert "parked on q32" in parked and "row n=2" in parked, leg["coverage"]["parks"]
    assert "OWED #932" in named, (
        f"the undeclared neighbour must STILL be owed, or a leg that cleared the whole "
        f"population would satisfy the assertions above\n{named}"
    )
    cov = leg["coverage"]
    assert cov["units_owed"] == 1, cov
    assert cov["parks_declared"] == 1, cov
    assert cov["units_parked"] == 1, cov
    assert cov["units_park_superseded"] == 0, cov

    # THE TWO-SIDED HALF: the SAME fixture WITHOUT the declaring row reads #931 OWED, so the
    # park -- and nothing else -- is what moved it. A probe that asserted only the parked read
    # would pass a leg that reported nothing owed at all.
    bare_rows = [row for row in rows if row["n"] != 2]
    bare = RUNNER.stall_census_leg(issues, bare_rows, read_at=read_at)
    assert "OWED #931" in "\n".join(bare["problems"]), bare["problems"]
    assert bare["coverage"]["units_owed"] == 2, bare["coverage"]
    assert bare["coverage"]["units_parked"] == 0, bare["coverage"]
    assert bare["coverage"]["parks_declared"] == 0, bare["coverage"]

    # ... and the render half: the exclusion is PRINTED BESIDE THE VERDICT, so a reader who
    # sees an owed total smaller than the population can tell a declared park from a dropped
    # unit.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"the undeclared neighbour is still OWED, got rc={rc}\n{out}"
    assert "1 declared, 1 OWED unit(s) held PARKED and EXCLUDED from the owed total" in out, out
    assert "PARKED #931" in out, out
    assert "not a finding" in out, out

def test_the_stall_census_leg_reads_a_park_from_the_EVENT_and_never_from_prose() -> None:
    """#535 / ruling n=4007, the READ discipline: a park is a TRANSITION, and prose declares
    nothing.

    THE THREE ACCEPTANCE ARMS the ruling names, each mechanical and each measured here:

      1. a subject with a `park` row and no `unpark` reads PARKED and leaves the owed total;
      2. the same subject with an `unpark` AFTER the park is not parked, and reads OWED;
      3. a row whose DETAIL carries `park:owner:q39` while its event is not `park` is NOT
         parked -- prose is a mention, never a declaration.

    Arms 1 and 2 are the fold: state is the LAST transition in row order, so the pair is what
    makes the verdict a position in a sequence rather than a presence in a file. Arm 3 is why
    the token scan was removed: the live row that WITHDREW #301's park (n=2883) quotes
    `park:owner:q30` and `park:owner:q39` mid-sentence, and a reader matching the substring
    parks #301 on the very correction written to withdraw that park.

    The three units below are discriminated by SHAPE ALONE, and the last is the control that
    keeps this from being a blanket refusal: a park naming NO question, and a park whose
    question ref is not a register id, both stay OWED with a PROBLEM naming them, while a
    park carrying `question:q39` is the only one that holds. HQ's C1 scope ruling (n=2884)
    fixes the shape at ONE -- the register is the only sanctioned blocked-on-you channel.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(n, "OPEN") for n in (951, 952, 953, 954, 955)]
    rows = [
        _stall_row(1, "dispatch", "#951", 5, now=now),
        # ARM 3: the row NAMES the token in prose and carries no park event at all. It is an
        # ordinary `run` row, so nothing about it declares a state.
        _stall_row(
            2, "run", "#951", 4, now=now,
            detail="n=2878 declared park:owner:q30 for it; this row WITHDRAWS that as a "
                   "MIS-CITATION and CARRIES NO PARK TOKEN of its own",
        ),
        # The refused shape the WRITE PATH refuses: a `park` event carrying no question ref.
        _stall_row(3, "dispatch", "#952", 5, now=now),
        _park_row(4, "#952", 4, None, now=now),
        _stall_row(5, "dispatch", "#953", 5, now=now),
        _park_row(6, "#953", 4, "memo:#301", now=now),
        _stall_row(7, "dispatch", "#954", 5, now=now),
        _park_row(8, "#954", 4, "<question>", now=now),
        _stall_row(9, "dispatch", "#955", 5, now=now),
        _park_row(10, "#955", 4, "q39", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    for quiet in ("#951", "#952", "#953", "#954"):
        assert f"OWED {quiet}" in named, (
            f"{quiet} must stay OWED: prose declares nothing, and a park whose question ref "
            f"is missing or is not a register id cannot be read as a declaration\n{named}"
        )
    assert "OWED #955" not in named, (
        f"the park carrying `question:q39` is the CONTROL -- if it did not hold, the probes "
        f"above would pass a reader that parks nothing at all\n{named}"
    )
    # ARM 3 is asserted on the row that PROVES it: #951's detail names the token and the unit
    # is still OWED. A reader that matched the substring would have cleared it here.
    assert "park:owner:q30" in "\n".join(
        r["detail"] for r in rows if r["n"] == 2
    ), "the fixture must actually carry the token in prose, or arm 3 tests nothing"
    # ... and the two refused park shapes are PROBLEMS, each naming the row and the ONE
    # lawful shape: a declaration the census cannot see re-arms the very line it was meant
    # to hold.
    assert "is a `park` naming no question" in named and "row n=4" in named, named
    assert "not a register question id" in named and "memo:#301" in named, named
    assert "<question>" in named and "row n=8" in named, named

    cov = leg["coverage"]
    assert cov["units_owed"] == 4, cov
    assert cov["parks_declared"] == 1, cov
    assert cov["units_parked"] == 1, cov
    assert cov["park_rows_examined"] == 4, cov
    assert "PARKED #955" in "\n".join(cov["parks"]), cov["parks"]

def test_a_park_is_CLEARED_by_a_LATER_unpark_and_the_pair_is_joined_by_its_ROW_ref() -> None:
    """#535 leg 2, acceptance arms 1 and 2: the state is the LAST transition, not the first.

    One fixture, two reads, and the ONLY difference between them is whether the `unpark` row
    is present -- so the verdict is measured as the thing the unpark moved rather than as two
    independent reads that happen to differ.

    The unpark names the park it ends as `--ref row:<n>`. An unpark naming a row that is not
    a park for that subject is a PROBLEM, not a silent close: the write path refuses that
    shape at append, but a row is immutable once pushed, so the leg is the half that can
    still see it.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(981, "OPEN"), _issue(982, "OPEN")]
    base = [
        _stall_row(1, "dispatch", "#981", 6, now=now),
        _park_row(2, "#981", 5, "q39", now=now),
        _stall_row(3, "dispatch", "#982", 6, now=now),
        _park_row(4, "#982", 5, "q40", now=now),
    ]
    parked_leg = RUNNER.stall_census_leg(issues, base, read_at=read_at)
    parked_cov = parked_leg["coverage"]
    assert parked_cov["units_parked"] == 2, parked_cov
    assert parked_cov["units_owed"] == 0, parked_cov
    named = "\n".join(parked_leg["problems"])
    assert "OWED #981" not in named and "OWED #982" not in named, named

    # ARM 2: the SAME fixture plus one unpark row, dated LATER than #981's park. #982 has no
    # unpark and stays parked, so the read discriminates the pair rather than flipping both.
    cleared = base + [_unpark_row(5, "#981", 4, 2, now=now)]
    leg = RUNNER.stall_census_leg(issues, cleared, read_at=read_at)
    cov = leg["coverage"]
    named = "\n".join(leg["problems"])
    assert "OWED #981" in named, (
        f"the unpark row must put #981 back in play -- a park with no end is a permanent gag, "
        f"and an unpark that does not clear is the same defect wearing the other face\n{named}"
    )
    assert "OWED #982" not in named, (
        f"#982's park has no unpark and must STILL hold -- otherwise the arm above passes a "
        f"reader that clears every park it sees\n{named}"
    )
    assert cov["units_parked"] == 1, cov
    assert cov["units_owed"] == 1, cov
    assert cov["park_rows_examined"] == 3, cov

    # A MIS-JOINED unpark is a PROBLEM: here it names #982's park while its subject is #981,
    # which no write path would mint today and which a pushed row can still carry.
    misjoined = base + [_unpark_row(5, "#981", 4, 4, now=now)]
    leg3 = RUNNER.stall_census_leg(issues, misjoined, read_at=read_at)
    named3 = "\n".join(leg3["problems"])
    assert "cannot unpark another unit's park" in named3, named3
    assert "OWED #981" not in named3, (
        f"a refused unpark must NOT clear the park it names, so #981 stays PARKED -- "
        f"honouring it would let a row clear a state it has no authority over\n{named3}"
    )
    assert leg3["coverage"]["units_parked"] == 2, leg3["coverage"]

def test_a_ruling_that_SAYS_blocked_on_the_owner_design_gate_owes_a_park_row() -> None:
    """#535 leg 3: a state that lives only in a ruling's prose is invisible to the census.

    Ruling n=2360 says in as many words that #324 is "BLOCKED on the owner design gate" and no
    `park` row exists for it, so the census could not fold the state and the unit read OWED.
    The leg reports the GAP -- the ruling without the row -- rather than re-reading the prose
    as a declaration, which is the token scan this whole unit removed.

    WINDOW-BOUNDED (#536): the window is ROWS FROM THE LEDGER'S OWN TAIL, so a replayed
    fixture is stable without an injected clock, and an unbounded version would re-litigate
    every historical ruling on the first run. The population examined is asserted, because a
    clean verdict over an examined-nothing read is not a verdict (#242).
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(991, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#991", 6, now=now),
        _stall_row(
            2, "ruling", "#991", 5, now=now,
            detail="## RULED -- #991 is ACCEPTED and BLOCKED on the owner design gate; no "
                   "worker dispatch is owed.",
        ),
    ]
    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    cov = leg["coverage"]
    named = "\n".join(leg["problems"])
    assert cov["owed_units_examined_for_park_gap"] == 1, cov
    assert cov["ruling_park_gaps"] == 1, cov
    assert "no `park` row for it" in named, named
    assert "row n=2" in named, named

    # THE CONTROL: the same ruling WITH its park row reports no gap. The examined count falls
    # to 0 and that is the fix rather than an artefact -- the population is the OWED set, so a
    # unit that IS parked leaves it and is never re-litigated. A leg that kept examining it
    # would report a gap on every parked unit in the factory.
    with_park = rows + [_park_row(3, "#991", 4, "q39", now=now)]
    leg2 = RUNNER.stall_census_leg(issues, with_park, read_at=read_at)
    cov2 = leg2["coverage"]
    assert cov2["owed_units_examined_for_park_gap"] == 0, cov2
    assert cov2["ruling_park_gaps"] == 0, cov2
    assert cov2["units_parked"] == 1, cov2
    assert "no `park` row for it" not in "\n".join(leg2["problems"]), leg2["problems"]

    # A ruling that names NO design gate is not in the population at all, and the count says
    # so -- an empty finding and an empty population must not read the same (#116).
    quiet = [rows[0], _stall_row(2, "ruling", "#991", 5, now=now,
                                 detail="## RULED -- #991 is a duplicate of #990.")]
    leg3 = RUNNER.stall_census_leg(issues, quiet, read_at=read_at)
    assert leg3["coverage"]["owed_units_examined_for_park_gap"] == 1, leg3["coverage"]
    assert leg3["coverage"]["ruling_park_gaps"] == 0, leg3["coverage"]

def test_a_park_matching_NO_owed_line_is_PRINTED_never_dropped() -> None:
    """#470, on the event mechanism: a park declared for a unit the census does NOT report owed
    is PRINTED as a note, never dropped.

    A declaration that matches no OWED line is indistinguishable from a declaration aimed at
    the wrong subject, and dropping it silently is the same failure an unreadable one is. The
    two arms below are the two REASONS a park matches no OWED line, and they read differently
    because the reasons are different: `#955` was never ROUTED, so no park held anything out;
    `#956` WAS routed and its board item is CLOSED, so the off-board filter dropped it.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(955, "OPEN"), _issue(956, "CLOSED")]
    rows = [
        # #955 has no dispatch row at all: no ROUTING ever handed it to a lane, so it was never
        # in the population and its declaration held nothing out. It reads PARKED -- not
        # "matched NO OWED line", whose reasons all describe a unit that WAS routed.
        _park_row(9, "#955", 4, "q39", now=now),
        # #956 WAS routed and the board carries it CLOSED: this is the "matched NO OWED line"
        # disposition, and it must keep a fixture of its own.
        _stall_row(10, "dispatch", "#956", 5, now=now),
        _park_row(11, "#956", 4, "q40", now=now),
    ]
    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    notes = "\n".join(leg["coverage"]["parks"])
    assert "#955" in notes and "PARKED #955" in notes, leg["coverage"]["parks"]
    assert "#956" in notes and "matched NO OWED line" in notes, leg["coverage"]["parks"]
    assert leg["coverage"]["units_parked"] == 0, leg["coverage"]
    assert leg["coverage"]["parks_declared"] == 2, leg["coverage"]

def test_the_stall_census_leg_SUPERSEDES_a_park_a_LATER_dispatch_lifted() -> None:
    """#331 clause 1, the STATE half: a park holds until a LATER dispatch puts the unit back
    in play, and the supersession is PRINTED rather than obeyed.

    Without this guard the clause would be a permanent gag rather than a state. The ledger
    keeps every park row forever, so a unit parked once and re-dispatched a week later would
    stay silently held out of the census for good -- and nothing in the report would say why.
    The two units below carry the SAME two rows in OPPOSITE order, which is the property under
    test: order alone decides whether the declaration still holds.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(961, "OPEN"), _issue(962, "OPEN")]
    rows = [
        # #961: parked FIRST, then re-dispatched -- the park is stale and the unit is OWED.
        _park_row(1, "#961", 5, "q33", now=now),
        _stall_row(2, "dispatch", "#961", 4, now=now),
        # #962: dispatched FIRST, parked after -- the declaration is the newest act.
        _stall_row(3, "dispatch", "#962", 5, now=now),
        _park_row(4, "#962", 4, "q33", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #961" in named, (
        f"a dispatch NEWER than the park puts the unit back in play\n{named}"
    )
    assert "OWED #962" not in named, named
    notes = "\n".join(leg["coverage"]["parks"])
    assert "PARKED #962" in notes, leg["coverage"]["parks"]
    assert "#961" in notes and "SUPERSEDED" in notes, (
        f"the stale declaration is PRINTED, not merely obeyed: a reader must be able to see "
        f"that a park was declared and then lifted\n{notes}"
    )
    assert "row n=2" in notes and "row n=1" in notes, notes
    cov = leg["coverage"]
    assert cov["units_owed"] == 1, cov
    assert cov["units_parked"] == 1, cov
    assert cov["parks_declared"] == 2, cov
    assert cov["units_park_superseded"] == 1, cov

def test_a_BODY_MENTION_neither_ADMITS_a_unit_nor_SUPERSEDES_its_park() -> None:
    """#470, the routing split measured on ONE population, three arms.

    THE DEFECT. Ledger `n=3098` is a Triage escalation whose subject is a descriptive stem
    and whose BODY names `#460` and `#313`. Read permissively, those two tokens were admitted
    to the census population, DATED off the escalation's own write stamp, and -- because that
    same row then counted as their newest "dispatch" -- printed as parks SUPERSEDED. Two units
    nobody had ever dispatched therefore read OWED, and the census totalled 11 where it owed 9.

    THE SPLIT (#470). A row that names a unit only in its prose is a MENTION: it still counts
    in the harvest's coverage (#467 criterion 3, asserted below), but it may take no ROUTING
    slot -- not population admission, not the age, not park supersession.

    THE DISCRIMINATOR IS THE TOKEN'S GRAMMATICAL ROLE, not its offset (#550 re-based this
    from #467's opening-line test, which ruling n=4156 withdrew as inert on one-line
    details). The arms below differ in ROLE ALONE: `#971` is named only in a carrier's body,
    standing in APPOSITION to its clause, and its park HOLDS. `#972` is the SUBJECT of the
    same carrier's opening clause, so it was ROUTED and its park is SUPERSEDED. `#973` is
    routed by a direct dispatch row and is superseded too. An implementation that refused
    every carrier row fails on `#972`; one that obeyed every carrier row fails on `#971` --
    and the carrier is the NEWEST row in both cases, so the mention arm is a live
    supersession that must not happen rather than a row too old to act.

    Note the shape `#972` needs: a token the row PREDICATES something of, never one it merely
    hands to a verb as an object. `this row ROUTES #972.` reads as a MENTION under the role
    test, because the bytes after the token open no clause -- which is the same reason
    `n=4048`'s `#529's tests` does not route. The fixture states the routing the way a real
    dispatch row does: subject first, then the predicate.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(n, "OPEN") for n in (971, 972, 973)]
    rows = [
        # #971: parked, then named only in a carrier's BODY -- the park must HOLD.
        _stall_row(1, "intake", "#971", 6, now=now),
        _park_row(2, "#971", 5, "q40", now=now),
        # #972: parked, then the SUBJECT of the carrier's opening clause -- ROUTED, so
        # SUPERSEDED.
        _stall_row(3, "intake", "#972", 6, now=now),
        _park_row(4, "#972", 5, "q41", now=now),
        # #973: parked, then re-dispatched by a direct row -- SUPERSEDED, the #331 control.
        _stall_row(5, "intake", "#973", 6, now=now),
        _park_row(6, "#973", 5, "q42", now=now),
        _stall_row(7, "dispatch", "#973", 2, now=now),
        # THE CARRIER, and the newest row in the population: a descriptive stem that ROUTES
        # #972 as the subject of its opening clause and only TALKS about #971 further down
        # (the `n=3098` shape).
        _stall_row(8, "dispatch", "stall-census-escalation-probe", 3, now=now,
                   detail="TRIAGE ESCALATION -> the HQ lane: #972 is RE-DISPATCHED here.\n\n"
                          "Its body then talks about #971, and hands it to nobody."),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #971" not in named, (
        f"a token named only in a carrier's BODY is a MENTION, so it neither enters the "
        f"population nor starts the clock on the unit's age\n{named}"
    )
    assert "OWED #972" in named, (
        f"the POSITIVE arm: a token in the carrier's OPENING LINE was ROUTED, so the park it "
        f"supersedes is lifted\n{named}"
    )
    assert "OWED #973" in named, named

    parks = "\n".join(leg["coverage"]["parks"])
    assert "PARKED #971" in parks, (
        f"#971's declaration is RIGHT and the routing is simply absent, so it reads PARKED "
        f"rather than being accused of naming the wrong subject\n{parks}"
    )
    assert "SUPERSEDED" in parks and "#972" in parks and "#973" in parks, parks

    cov = leg["coverage"]
    assert cov["units_owed"] == 2, cov
    assert cov["units_park_superseded"] == 2, cov
    assert cov["parks_declared"] == 3, cov
    # NOT counted among the OWED units a park held out: #971 was never in the population, so
    # the census never owed it a line and the declaration held nothing out.
    assert cov["units_parked"] == 0, cov
    # COVERAGE IS UNCHANGED (#467 criterion 3): the mention is still CARRIED by the harvest
    # and still counted as a mention. The split narrows the ROUTING slot, never the coverage.
    assert cov["carried_units_resolved"] == 2, cov
    assert cov["mentions_rejected"] == 1, cov
    # AND THE TWO POPULATIONS ARE PRINTED SIDE BY SIDE (#470): what a dispatch ROUTED, and
    # what the harvest saw and refused the population slot -- a narrowed read that hides what
    # it dropped is the failure this leg exists to catch.
    assert cov["units_in_population"] == 2, cov
    assert cov["units_named_only_as_mentions"] == 1, cov

def test_the_stall_census_leg_holds_a_RULED_VOID_unit_out_of_the_owed_total() -> None:
    """#473 acceptance, the whole point: a unit a RULING disposed of stops reading OWED even
    though its board item is still OPEN, and the declaring row travels with the verdict.

    THE MEASURED FAILURE THIS ANSWERS. `#453`: intake n=3032, dispatch n=3033, ruled
    "UNSUBSTANTIATED -- not-a-defect ... dispatch at n=3033 is void" at n=3041. The board item
    stayed OPEN, so the census kept printing `OWED #453`, and a Worker lane claimed it at
    n=3202, built a 266-probe arm for a defect ruled non-existent, withdrew it (8dc9a206) and
    closed the unit `outcome=abandoned` at n=3203. The ruling was loud; nothing could read it.

    TWO-SIDED, because a one-sided probe would pass a leg that voids everything: `#981`
    carries the declaration and leaves the owed total, `#982` carries none and stays OWED.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(981, "OPEN"), _issue(982, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#981", 5, now=now),
        _disposition_row(2, "#981", 4, "disposition:void", now=now),
        _stall_row(3, "dispatch", "#982", 5, now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #981" not in named, (
        f"a unit a RULING disposed of is not a finding, and its board item being OPEN is "
        f"exactly the state #473 exists to read\n{named}"
    )
    assert "OWED #982" in named, (
        f"the CONTROL: an undeclared unit must stay OWED, or the probe above would pass a "
        f"census that voids everything\n{named}"
    )
    voided = "\n".join(leg["coverage"]["dispositions"])
    assert "VOID #981" in voided, leg["coverage"]["dispositions"]
    # THE DECLARING ROW TRAVELS WITH THE VERDICT: a disposition no reader can trace to a row
    # is a claim, not a declaration -- and the row is what lets a reader go and read the
    # ruling that decided it.
    assert "row n=2" in voided and "disposition:void" in voided, voided

    cov = leg["coverage"]
    assert cov["units_owed"] == 1, cov
    assert cov["dispositions_declared"] == 1, cov
    assert cov["units_voided"] == 1, cov
    assert cov["units_disposition_superseded"] == 0, cov

    # ... and the exclusion reaches the REPORT, not only the dict: a reader who sees an owed
    # total smaller than the dispatched population must be able to read WHY.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"the control unit is OWED, so the run must fail, got rc={rc}\n{out}"
    assert "ruled VOID and EXCLUDED from the owed total" in out, out
    assert "dispositions (disposition:void on the unit's own rows): 1 declared, 1 OWED" in out, out

def test_the_stall_census_leg_reads_a_disposition_ONLY_from_a_standalone_token() -> None:
    """#473, the READ discipline, two-sided: a declaration is a LINE OF ITS OWN, a token
    quoted inside a sentence is a MENTION, and an unimplemented kind is a PROBLEM.

    The mention arm is not hypothetical -- it is the `n=2883` shape, the row that withdrew a
    park while quoting two park tokens mid-sentence. A reader matching the substring would
    dispose of a unit on a row that merely DISCUSSED disposing of it, which is a worse
    failure than the one #473 repairs: it would silently drop live work.

    The refused forms are PROBLEMS rather than silent passes: a factory that believes it
    disposed of a unit the census cannot see is back in the #453 state with the ruling
    present and unread.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(n, "OPEN") for n in (991, 992, 993, 994)]
    rows = [
        _stall_row(1, "dispatch", "#991", 5, now=now),
        _disposition_row(2, "#991", 4, now=now,
                         mention="n=3041 declared `disposition:void` for it; this row "
                                 "WITHDRAWS that and CARRIES NO DISPOSITION TOKEN"),
        _stall_row(3, "dispatch", "#992", 5, now=now),
        _disposition_row(4, "#992", 4, "disposition:", now=now),
        _stall_row(5, "dispatch", "#993", 5, now=now),
        _disposition_row(6, "#993", 4, "disposition:reopened", now=now),
        _stall_row(7, "dispatch", "#994", 5, now=now),
        _disposition_row(8, "#994", 4, "disposition:void", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    for quiet in ("#991", "#992", "#993"):
        assert f"OWED {quiet}" in named, (
            f"{quiet} must stay OWED: a mention is not a declaration, and an unreadable "
            f"declaration cannot be obeyed\n{named}"
        )
    assert "OWED #994" not in named, (
        f"the standalone declaration is the CONTROL -- if it did not hold, the probe above "
        f"would pass a reader that voids nothing\n{named}"
    )
    assert "cannot read" in named, named
    assert "row n=4" in named and "row n=6" in named, named
    assert "disposition:reopened" in named, named

    cov = leg["coverage"]
    assert cov["units_owed"] == 3, cov
    assert cov["dispositions_declared"] == 1, cov
    assert cov["units_voided"] == 1, cov

def test_the_stall_census_leg_SUPERSEDES_a_void_a_LATER_dispatch_lifted() -> None:
    """#473 clause 3: a void holds until a LATER dispatch puts the unit back in play, and the
    supersession is PRINTED rather than obeyed.

    Without this the clause would be a permanent gag: the ledger keeps every ruling forever,
    so a unit ruled void and then RE-DISPATCHED would stay silently excluded for good and
    nothing in the report would say why. The two units carry the same two acts in OPPOSITE
    order, which is the property under test.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(995, "OPEN"), _issue(996, "OPEN")]
    rows = [
        # #995: ruled void FIRST, then re-dispatched -- the ruling is stale, the unit is OWED.
        _stall_row(1, "dispatch", "#995", 6, now=now),
        _disposition_row(2, "#995", 5, "disposition:void", now=now),
        _stall_row(3, "dispatch", "#995", 4, now=now),
        # #996: dispatched, then ruled void -- the ruling is the newest act.
        _stall_row(4, "dispatch", "#996", 6, now=now),
        _disposition_row(5, "#996", 4, "disposition:void", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #995" in named, (
        f"a dispatch NEWER than the ruling puts the unit back in play\n{named}"
    )
    assert "OWED #996" not in named, named
    notes = "\n".join(leg["coverage"]["dispositions"])
    assert "VOID #996" in notes, leg["coverage"]["dispositions"]
    assert "#995" in notes and "SUPERSEDED" in notes, (
        f"the stale ruling is PRINTED, not merely obeyed\n{notes}"
    )
    assert "row n=2" in notes and "row n=3" in notes, notes
    cov = leg["coverage"]
    assert cov["units_owed"] == 1, cov
    assert cov["units_voided"] == 1, cov
    assert cov["units_disposition_superseded"] == 1, cov

def test_a_DISPOSITION_that_matches_no_OWED_line_is_PRINTED_once() -> None:
    """#473 clause 4 + the #471 rule: a disposition the census cannot act on is PRINTED, and
    a unit carrying BOTH a park and a void is printed under ONE heading.

    Two arms. `#997` was never ROUTED (its token stands in a row's body), so it was never in
    the population -- the declaration STANDS and the note says the routing is absent rather
    than accusing the declaration of naming the wrong subject. `#998` WAS routed and the board
    carries it CLOSED, so it is dropped by the off-board filter: the "matched NO OWED line"
    arm. `#999` carries a park token AND a void token, and must read VOID alone -- one unit
    printed with two contradictory dispositions is the defect #471 reports.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(998, "CLOSED"), _issue(999, "OPEN")]
    rows = [
        _disposition_row(1, "#997", 4, "disposition:void", now=now),
        _stall_row(2, "dispatch", "#998", 5, now=now),
        _disposition_row(3, "#998", 4, "disposition:void", now=now),
        _stall_row(4, "dispatch", "#999", 5, now=now),
        _park_row(5, "#999", 4, "q43", now=now),
        _disposition_row(6, "#999", 3, "disposition:void", now=now),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    notes = "\n".join(leg["coverage"]["dispositions"])
    assert "VOID #997" in notes and "no dispatch ROUTED it" in notes, notes
    assert "#998" in notes and "matched NO OWED line" in notes, notes
    assert "VOID #999" in notes, notes
    parks = "\n".join(leg["coverage"]["parks"])
    assert "#999" not in parks, (
        f"a unit a ruling DISPOSED OF must not also print a park note -- the void decided "
        f"the census, and two dispositions on one unit is the #471 defect\n{parks}"
    )
    cov = leg["coverage"]
    assert cov["units_owed"] == 0, cov
    assert cov["units_voided"] == 1, cov
    assert cov["parks_declared"] == 1, cov
    assert cov["units_parked"] == 0, cov

def test_the_stall_census_leg_names_the_ADDRESSEE_and_never_the_AUTHOR() -> None:
    """#331 clause 2, two-sided: the OWED line names the LANE the dispatch was handed to, and
    a unit whose dispatch declares no target SAYS SO rather than printing the row's author.

    The defect this replaces: the line printed `actor={actor}` -- the author of the
    dispatch-bearing row, which for a census re-dispatch is whoever RAN the census, usually
    Triage, and never the lane the work belongs to -- directly beside the advice to
    "re-dispatch it to the lane that owns it". An author in that slot reads as an assignment,
    which is worse than an empty one.

    Three arms, each of which a wrong implementation fails. #941 is AUTHORED by `hq` and
    ADDRESSED to the Ledger lane by a typed `session` ref the resolver maps to `Ledger`, so a
    leg that printed the author fails. #942 declares a session the resolver does NOT know, and
    #943 declares no target at all -- so a leg that silently fell back to the author, or
    silently printed nothing, fails on those too.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger_session = "11111111-2222-3333-4444-555555555555"
    issues = [_issue(941, "OPEN"), _issue(942, "OPEN"), _issue(943, "OPEN")]
    rows = [
        _stall_row(1, "dispatch", "#941", 5, now=now, actor="hq",
                   refs=[{"session": ledger_session}]),
        _stall_row(2, "dispatch", "#942", 5, now=now, actor="hq",
                   refs=[{"session": "99999999-0000-0000-0000-000000000000"}]),
        _stall_row(3, "dispatch", "#943", 5, now=now, actor="hq"),
    ]
    names = {ledger_session: "Ledger"}

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at,
                                  lane_names_fn=lambda: names)
    line_941 = [ln for ln in leg["problems"] if "#941" in ln][0]
    assert "ADDRESSED to Ledger" in line_941, line_941
    assert "actor=hq" not in line_941, (
        f"the AUTHOR must never stand in the addressee's slot -- it reads as an "
        f"assignment\n{line_941}"
    )
    for unit in ("#942", "#943"):
        line = [ln for ln in leg["problems"] if unit in ln][0]
        assert "NO ADDRESSEE RESOLVES" in line, (
            f"{unit} declares no resolvable target and the line must SAY SO, never fall back "
            f"to the author\n{line}"
        )
        assert "actor=hq" not in line, line
    cov = leg["coverage"]
    assert cov["units_owed"] == 3, cov
    assert cov["addressees_resolved"] == 1, cov
    assert cov["addressees_unresolved"] == 2, cov

    # THE TWO-SIDED HALF: with a resolver that knows NOTHING, the same row cannot name a lane,
    # so "ADDRESSED to Ledger" is a statement about the RESOLUTION and not a constant the leg
    # prints. This is also the shape a member factory without a binding store sees.
    blind = RUNNER.stall_census_leg(issues, rows, read_at=read_at, lane_names_fn=lambda: {})
    assert "ADDRESSED to Ledger" not in "\n".join(blind["problems"]), blind["problems"]
    assert blind["coverage"]["addressees_resolved"] == 0, blind["coverage"]

    # ... and the render half: the addressee and its coverage reach the report, and `actor=`
    # is nowhere on it.
    rc, out, _ = _run(issues, rows, lane_names_fn=lambda: names)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "ADDRESSED to Ledger" in out, out
    assert "addressee: 1 of 3 OWED unit(s) name the lane the work was handed to; " \
           "2 declare none" in out, out
    assert "actor=hq" not in out, out

def test_the_stall_census_leg_DISCHARGES_on_an_act_but_CLEARS_only_on_a_claim_or_close() -> None:
    """#308 acceptance (3): a re-dispatch DISCHARGES the lane's duty but does NOT clear the
    census READING, and does NOT reset the age clock.

    The distinction the Triage card's old sentence collapsed -- *"Clearing an `OWED` line is
    an ACT -- a re-dispatch through `session_notify`, or a board close"* -- into a single
    verb. `stall_census_leg` keys each unit's EARLIEST dispatch-bearing row
    (`carriers.setdefault`) and clears a unit only on a `claim` or a `close`, deliberately,
    so that "a re-dispatch would otherwise reset the clock and hide a stall that has stood
    for a fortnight" (its own docstring).

    So a unit dispatched, then RE-dispatched hours ago, is still OWED at its ORIGINAL age --
    and the age is read off the RENDER, because a leg naming the right unit at the wrong age
    would be a different statement: that the re-dispatch reset the clock.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(911, "OPEN"), _issue(912, "OPEN")]
    rows = [
        _stall_row(1, "intake", "#911", 4, now=now),
        _stall_row(2, "dispatch", "#911", 3, now=now),     # dispatched 3 d ago
        _stall_row(3, "dispatch", "#911", 0.1, now=now),   # RE-dispatched 0.1 d ago
        _stall_row(4, "intake", "#912", 4, now=now),
        _stall_row(5, "dispatch", "#912", 3, now=now),     # dispatched 3 d ago
        _stall_row(6, "claim", "#912", 0.1, now=now),      # then CLAIMED
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #911" in named, (
        f"a re-dispatch is neither a `claim` nor a `close` -- the line must STAND, or the "
        f"census clears on an act it is not supposed to clear on\n{named}"
    )
    assert "dispatched 3.00 d ago" in named, (
        f"the age must run from the EARLIEST dispatch-bearing row: a re-dispatch must not "
        f"reset the clock and hide a stall that has stood for a fortnight\n{named}"
    )
    assert "#912" not in named, (
        f"a `claim` row clears the line -- that unit has a taker\n{named}"
    )
    assert leg["coverage"]["units_owed"] == 1, leg["coverage"]

    # The render half: a leg returning the right dict while the report drops it is the
    # half-fix this catches.
    rc, out, _ = _run(issues, rows)
    assert rc == 1, f"an OWED line must fail the run, got rc={rc}\n{out}"
    assert "OWED #911" in out, out
    assert "dispatched 3.00 d ago" in out, out

    # THE CONTROL, asserted rather than described: the naive "LATEST dispatch row" reading
    # dates #911 at 0.10 d -- below the 1.0 d threshold -- and would report NOTHING owed. A
    # leg that keyed the latest row fails on the assertions above; this measures that the
    # fixture can TELL the two apart, so the probe is never vacuous.
    latest = max(
        (r for r in rows if r["event"] == "dispatch" and r["subject"] == "#911"),
        key=lambda r: r["n"],
    )
    naive_age = (
        now - dt.datetime.strptime(latest["ts"], "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=dt.timezone.utc)
    ).total_seconds() / 86400.0
    assert naive_age < RUNNER.STALL_CENSUS_THRESHOLD_DAYS, (
        f"the control must BITE: the latest-dispatch reading is {naive_age:.2f} d and must "
        f"fall BELOW the {RUNNER.STALL_CENSUS_THRESHOLD_DAYS} d threshold, or the fixture "
        f"cannot tell earliest from latest and the probe proves nothing"
    )

def test_the_stall_census_leg_reads_CARRIED_units_and_only_from_a_CARRIER() -> None:
    """#260 acceptance (1), the population half: a unit dispatched by a WAVE row is a
    dispatched unit, and each of the three shapes that merely LOOK like one is refused.

    This is the measured class the whole leg exists for. Board #181 carries intake n=1221,
    run n=1226 and ruling n=1233 and NO dispatch row of its own -- its dispatch leg is the
    wave row n=1214 (`subject=kit-adoption-wave-2026-09-26`, `refs=None`), whose detail
    reads "...carrying BOTH instruments (board #181 ledger bundle, board #182
    questions)...". A subject-keyed census cannot see it (#2092, ruling n=2100).

    The other half is the false positive the naive `#\\d+` scan generates, and the fixture
    carries each shape the discriminator must refuse:

    * `#908` is named inside a WORK-UNIT dispatch's own detail -- a cross-reference, not a
      carrier's payload, so the row is never scanned as a carrier at all;
    * `#909` is named by a real carrier but has NO ledger rows of its own, which is what a
      prose mention of another repository's number looks like;
    * `#910` HAS rows of its own and is named by a real carrier, yet is not an issue this
      board declares -- the `#366` shape, which carries ledger rows n=433 and n=436 and is
      not on this board at all (the fork's `#366`).

    Measured 2026-10-03, a scan that admitted the prose shapes reported 160 units against a
    true population of 206 examined / 20 owed, and corrupted ages -- a mention moved `#49`
    from 15.05 d to 4.96 d.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(906, "OPEN"), _issue(907, "OPEN"), _issue(908, "OPEN")]
    rows = [
        _stall_row(1, "intake", "#906", 4, now=now),
        _stall_row(2, "dispatch", "kit-adoption-wave-probe", 3, now=now,
                   actor="delegate",
                   detail="dispatched to five member HQs (board #906 ledger bundle)"),
        _stall_row(3, "intake", "#907", 5, now=now),
        _stall_row(4, "dispatch", "#907", 4, now=now,
                   detail="WHY NOT COVERED BY #908"),
        _stall_row(5, "dispatch", "sweep-probe-2026-10-03", 3, now=now,
                   detail="sweep of the board (board #909 backlog)"),
        _stall_row(6, "intake", "#910", 6, now=now),
        _stall_row(7, "dispatch", "relay-probe-2026-10-03", 5, now=now,
                   detail="relayed onward (board #910 follow-up)"),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #906" in named, (
        f"a unit carried by a wave row IS a dispatched unit and must be named\n{named}"
    )
    assert "OWED #907" in named, f"a work-unit dispatch is dispatched too\n{named}"
    assert "#908" not in named, (
        f"a unit named inside another unit's dispatch is a cross-reference, not a "
        f"carrier's payload\n{named}"
    )
    assert "#909" not in named, (
        f"a unit with no ledger rows of its own is a prose mention\n{named}"
    )
    assert "#910" not in named, (
        f"a unit the board does not declare is not a unit of this board's namespace, "
        f"however many ledger rows it carries\n{named}"
    )
    cov = leg["coverage"]
    assert cov["carried_units_resolved"] == 2, cov
    assert cov["units_off_board"] == 1, cov
    assert cov["observation_dispatches"] == 1, cov
    assert cov["units_in_population"] == 3, cov
    assert cov["units_owed"] == 2, cov

def test_the_stall_census_leg_counts_an_OBSERVATION_dispatch_and_never_judges_it() -> None:
    """A descriptive-stem dispatch naming NO work unit is EXPLICITLY LEGAL (ruling n=524),
    and the leg must COUNT it rather than read it as an empty population.

    The pair is deliberate: a leg that judged these would red the run for the ordinary
    relay traffic this factory runs on, and a leg that silently dropped them would report
    the same numbers whether it examined them or never looked.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [_issue(901, "OPEN")]
    rows = [
        _stall_row(1, "intake", "#901", 4, now=now),
        _stall_row(2, "dispatch", "#901", 3, now=now),
        _stall_row(3, "dispatch", "board-hygiene-observation", 2, now=now,
                   detail="nothing in particular was handed over"),
    ]
    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    cov = leg["coverage"]
    assert cov["dispatch_rows_examined"] == 2, cov
    assert cov["observation_dispatches"] == 1, cov
    assert cov["units_in_population"] == 1, cov
    assert cov["units_owed"] == 1, cov
    assert len(leg["problems"]) == 1, leg["problems"]

def test_the_stall_census_leg_PRINTS_its_threshold_with_its_basis() -> None:
    """#260 acceptance (3): the threshold and the basis it rests on are PRINTED on every
    run, never carried in a reader's memory -- and the basis must NAME the distinction the
    ruling drew, or the two thresholds read as one number in two places (n=1861).

    Asserted on the RENDER, not on the constant: a basis declared in a module constant and
    dropped from the report is the same failure as one never written.
    """
    rc, out, _ = _run([_issue(901, "OPEN")], [])
    assert "LEG stall-census — ASSERTED" in out, out
    assert "never claimed past the declared threshold of 1.0 d" in out, out
    assert "threshold basis: 1.0 d" in out, out
    assert "CLAIMED-but-silent" in out, (
        f"the basis must name the Triage card's own predicate it is NOT\n{out}"
    )

def test_the_stall_census_leg_does_not_harvest_a_REPOSITORY_QUALIFIED_mention() -> None:
    """#333 acceptance: a `#N` the prose QUALIFIES as another repository's is not a unit
    of this board, and the harvest itself survives the guard.

    The live collision this arm reproduces, measured 2026-10-05: ledger row n=186
    (`subject "#332-D5"`, a comment on the FORK's issue) names *"fork issue #332"* in its
    detail, while the unrelated intake row n=2421 (`subject "#332"`) makes that same
    number RESIDENT -- so the pre-fix harvest carried `#332` out of the fork mention and
    the patrol printed `OWED #332: dispatched 17.22 d ago` against a board item filed the
    same day.

    FOUR foreign shapes the guard must refuse are covered by the direct unit arm at the
    bottom; this fixture covers the collision end to end AND keeps a legitimate carrier,
    so the probe is never vacuous: a guard that dropped the whole harvest would pass the
    `#901` half and fail the `#902` half.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        _issue(901, "OPEN"),   # the colliding board item: open, never claimed
        _issue(902, "OPEN"),   # carried by THIS board's own dispatch prose -> still OWED
    ]
    rows = [
        # The colliding intake row: it makes `#901` RESIDENT without dispatching it.
        _stall_row(1, "intake", "#901", 20, now=now, actor="triage"),
        # The CARRIER: a fork-issue comment whose prose names "fork issue #901".
        _stall_row(2, "dispatch", "#901-D5", 17.22, now=now, actor="triage",
                   detail="dispatched to OpenCrabs Kanban Board HQ as comment on "
                          "fork issue #901 (issuecomment-5727369776)"),
        # A legitimate unit of this board, made resident by its own intake row.
        _stall_row(3, "intake", "#902", 5, now=now, actor="triage"),
        # A wave whose prose carries THIS board's unit -- the harvest must keep working.
        _stall_row(4, "dispatch", "wave-2026-10-05", 3, now=now,
                   detail="routed #902 to the Worker lane"),
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #901" not in named, (
        "a `#N` the detail QUALIFIES as another repository's (`fork issue #901`) is not a "
        f"unit of this board, however many rows the local issue carries\n{named}"
    )
    assert "OWED #902" in named, (
        "the harvest itself must SURVIVE the scope guard: a wave naming this board's own "
        f"unit still dispatched it\n{named}"
    )
    assert leg["coverage"]["units_owed"] == 1, leg["coverage"]

    # THE CONTROL, asserted rather than described: on THIS fixture the pre-fix predicate
    # (`is_work_unit(token) and token in resident`, no occurrence scope) DOES admit
    # `#901` -- the token is a strict unit and a resident subject -- so the two predicates
    # are distinguishable here and the probe is not vacuous.
    detail = rows[1]["detail"]
    assert "#901" in {str(r["subject"]).strip() for r in rows}, (
        "the collision needs a RESIDENT subject of the same number, or the fixture tests "
        "the residency guard instead of the scope guard"
    )
    assert RUNNER.is_board_unit_occurrence(detail, detail.index("#901")) is False, (
        f"the occurrence guard must refuse the fork mention in {detail!r}"
    )

    # ... and through the REAL `main()`: the render must carry the same verdict, because a
    # leg returning a correct dict while the report drops it is the half-fix this catches.
    rc, out, _ = _run(issues, rows)
    assert "OWED #902" in out, out
    assert "OWED #901" not in out, out

def test_the_scope_guard_refuses_every_measured_foreign_shape() -> None:
    """#333 acceptance, the direct arm: the four shapes the 2026-10-05 measurement found
    on the live ledger, and the two shapes that must stay ADMITTED.

    Named one by one because a guard tuned to the single reported case would pass a
    one-shape probe: the collision is *"fork issue #332"*, but the same defect was live in
    `inferhub-watch#115`, `alexeyleshchenko/ai-antispam#76` and
    `leshchenko1979/opencrabs #366` -- three different spellings of "another repository".
    The two admitted shapes are the ones a scope guard is most likely to over-reach on: a
    UNIT LIST (`#200/#344/#12`, whose slash is a separator, not a path) and a plain
    mention preceded by an ordinary word.
    """
    refused = [
        ("dispatched as comment on fork issue #332 (issuecomment-5727369776)", "#332"),
        ("ai-antispam 13, inferhub 4 (tracked at inferhub-watch#115, NOT routed)", "#115"),
        ("ai-antispam -- alexeyleshchenko/ai-antispam#76, OPEN. Its board...", "#76"),
        ("FILED: leshchenko1979/opencrabs #366 - \"restart recovery\"", "#366"),
    ]
    admitted = [
        ("no claim rows exist for #31 or #32 on the ledger", "#31"),
        ("WHY NOT COVERED BY #200/#344/#12: those cover a different failure", "#12"),
        ("Priority unchanged: #33/#35, then #34 (n=222)", "#34"),
        ("FINDINGS: (1) #33 unclaimed 4h10m", "#33"),
    ]
    for blob, token in refused:
        assert RUNNER.is_board_unit_occurrence(blob, blob.index(token)) is False, (
            f"{token} in {blob!r} names another repository's namespace and must be REFUSED"
        )
    for blob, token in admitted:
        assert RUNNER.is_board_unit_occurrence(blob, blob.index(token)) is True, (
            f"{token} in {blob!r} is written as a unit of THIS board and must be ADMITTED"
        )

def test_the_stall_census_leg_refuses_a_dispatch_that_PREDATES_the_item_it_names() -> None:
    """#415 acceptance: the harvest must not pair a FOREIGN or OLDER mention with a
    today-filed issue.

    Two doors #333's scope guard left open, both measured live 2026-10-06:

    * the CARRIER bare-prose mention -- carrier `n=321` (2026-09-18) writes
      `WHY NOT COVERED BY #200/#344/#12`, while this board minted `#344` on
      2026-10-05, so the carrier PREDATES the item it was read as dispatching;
    * the CROSS-NAMESPACE subject collision -- `#366`'s rows `n=433`/`n=436` are the
      FORK's, while this board minted its own `#366` on 2026-10-05.

    Both read `OWED ... 17 d ago`. The guard: a dispatch row that PREDATES the item's own
    `createdAt` cannot be a dispatch of it. Two controls are deliberate -- `#903` is a
    genuine stall dispatched AFTER its filing (must STAY OWED, so the guard is not an
    over-reaching blanket), and `#904` carries NO `createdAt` (must STAY OWED, so a read
    that omits the field keeps every other verdict intact).
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    minted = (now - dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    minted_older = (now - dt.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [
        {"number": 901, "state": "OPEN", "title": "issue 901", "closedAt": None,
         "createdAt": minted},   # a carrier names it 17 d BEFORE the board minted it
        {"number": 902, "state": "OPEN", "title": "issue 902", "closedAt": None,
         "createdAt": minted},   # a foreign row carries the subject before minting
        {"number": 903, "state": "OPEN", "title": "issue 903", "closedAt": None,
         "createdAt": minted_older},   # a genuine stall: filed 5 d ago, dispatched 3 d ago
        {"number": 904, "state": "OPEN", "title": "issue 904", "closedAt": None},
    ]                            # `#904` declares NO `createdAt` -- the guard is a no-op
    rows = [
        _stall_row(1, "intake", "#901", 20, now=now, actor="triage"),
        _stall_row(2, "dispatch", "wave-2026-09-18", 17, now=now, actor="delegate",
                   detail="WHY NOT COVERED BY #200/#901/#12: those cover a different failure"),
        _stall_row(3, "intake", "#902", 20, now=now, actor="triage"),
        _stall_row(4, "dispatch", "#902", 17, now=now, actor="triage",
                   detail="the fork's row, filed under the same number"),
        _stall_row(5, "intake", "#903", 20, now=now, actor="triage"),
        _stall_row(6, "dispatch", "#903", 3, now=now, actor="hq"),   # AFTER minting
        _stall_row(7, "intake", "#904", 20, now=now, actor="triage"),
        _stall_row(8, "dispatch", "#904", 5, now=now, actor="hq"),   # no createdAt -> judged
    ]

    leg = RUNNER.stall_census_leg(issues, rows, read_at=read_at)
    named = "\n".join(leg["problems"])
    assert "OWED #901" not in named, (
        f"a carrier that PREDATES the board item it names cannot have dispatched it\n{named}"
    )
    assert "OWED #902" not in named, (
        f"a subject-keyed dispatch older than the item is a foreign row, not this "
        f"board's\n{named}"
    )
    assert "OWED #903" in named, (
        f"a genuine stall dispatched AFTER its filing must STAY OWED -- the guard must not "
        f"be an over-reaching blanket\n{named}"
    )
    assert "OWED #904" in named, (
        f"a read that omits `createdAt` must keep the verdict -- the guard is a no-op, "
        f"never a fail-closed\n{named}"
    )
    cov = leg["coverage"]
    assert cov["units_rejected_pre_filing"] == 2, cov
    assert cov["units_owed"] == 2, cov
    assert cov["units_in_population"] == 2, cov

    # THE CONTROL, asserted rather than described: the #333 SCOPE guard ADMITS the carrier
    # mention (a unit list, `#200/#901/#12`), so what refuses it is the FILING guard and
    # not the scope guard -- the probe is never vacuous.
    detail = rows[1]["detail"]
    assert RUNNER.is_board_unit_occurrence(detail, detail.index("#901")) is True, (
        f"the scope guard ADMITS this bare carrier mention; only the filing guard refuses "
        f"it\n{detail!r}"
    )

    # ... and through the REAL `main()`: a leg returning the right dict while the render
    # drops it is the half-fix this catches.
    rc, out, _ = _run(issues, rows)
    assert "OWED #903" in out, out
    assert "OWED #904" in out, out
    assert "OWED #901" not in out, out
    assert "OWED #902" not in out, out

def test_the_rider_prints_the_blocking_paths_AND_the_instant() -> None:
    """The rider's whole job: name the paths that block `reset --keep`, and say WHEN read.

    A claim about a live tree is a claim about the instant it was read, so the instant is
    asserted here beside the paths — without it the rider is testimony, not evidence.
    """
    rider = _rider(
        dirty=[" M a.py", "?? b.py", " M TEMPLATE/registry/kit.example.json"],
        blocking=["TEMPLATE/registry/kit.example.json"],
    )
    text = "\n".join(RUNNER.render_shared_tree_rider(rider))
    assert "read at 2026-10-03T02:00:00Z" in text, text
    assert "3 dirty path(s)" in text, text
    assert "1 BLOCKING" in text, text
    assert "~ TEMPLATE/registry/kit.example.json" in text, text
    assert "origin/main abc1234" in text, text
    assert "REPORTED, never reconciled (reconciles: no)" in text, text

def test_the_rider_reports_an_UNKNOWN_comparison_rather_than_a_zero() -> None:
    """A zero blocking set is a verdict only from a WORKING comparison (#242).

    When the base cannot be resolved the blocking subset is UNKNOWN, and the rider must
    print that — an empty list there would read exactly like a clean tree.
    """
    rider = _rider(
        dirty=[" M a.py"], blocking=None, base_sha=None,
        reason="git rev-parse --verify origin/main^{commit} failed",
    )
    text = "\n".join(RUNNER.render_shared_tree_rider(rider))
    assert "BLOCKING: UNKNOWN" in text, text
    assert "git rev-parse --verify origin/main^{commit} failed" in text, text
    assert "0 BLOCKING" not in text, f"an unknown comparison must not read as zero\n{text}"
    assert "read at 2026-10-03T02:00:00Z" in text, text

def test_the_rider_prints_NOT_RUN_with_its_reason() -> None:
    """A tree that could not be read is NOT RUN with its reason — never an empty rider."""
    rider = _rider(status="NOT RUN", reason="git status --porcelain -z failed: not a repo")
    text = "\n".join(RUNNER.render_shared_tree_rider(rider))
    assert "NOT RUN" in text, text
    assert "git status --porcelain -z failed: not a repo" in text, text
    assert "read attempted at 2026-10-03T02:00:00Z" in text, text
    assert "dirty path(s)" not in text, f"a NOT RUN rider has no population to report\n{text}"

def test_the_rider_is_NON_VACUOUS() -> None:
    """The control: the SAME fixture with and without a blocking path.

    One fixture, rendered twice — once with a path that is dirty AND moved, once with a
    clean tree — so the difference is attributable to the hazard and not to the fixture.
    Without this arm a renderer that always printed an empty list would satisfy the
    assertions above.
    """
    moved = "TEMPLATE/registry/kit.example.json"
    with_hazard = "\n".join(RUNNER.render_shared_tree_rider(
        _rider(dirty=[f" M {moved}"], blocking=[moved])))
    without = "\n".join(RUNNER.render_shared_tree_rider(
        _rider(dirty=[f" M {moved}"], blocking=[])))
    assert "1 BLOCKING" in with_hazard, with_hazard
    assert "0 BLOCKING" in without, without
    assert f"~ {moved}" in with_hazard, with_hazard
    assert f"~ {moved}" not in without, without

def test_an_unreadable_tree_yields_a_NOT_RUN_rider_through_the_real_reader() -> None:
    """The NOT RUN path through `shared_tree_read` itself, not a hand-made dict.

    A repo path that is not a repository makes `git status` fail; the reader must RETURN
    that reason rather than raise, so the rider degrades to NOT RUN instead of taking the
    patrol down.
    """
    state = RUNNER.shared_tree_read(Path("/nonexistent-probe-repo-241"))
    assert state.get("status") == "NOT RUN", state
    assert state.get("reason"), state
    rider = RUNNER.shared_tree_rider("2026-10-03T02:00:00Z",
                                     read_fn=lambda repo: state)
    assert rider["status"] == "NOT RUN", rider
    assert rider["read_at"] == "2026-10-03T02:00:00Z", rider
    assert rider["reconciles"] is False, rider

def test_the_whole_run_PRINTS_the_rider_and_it_moves_NO_verdict() -> None:
    """Driven through the REAL `main()`: the rider is rendered AND cannot gate.

    The rider is printed once, at the head of the board-leg region, and carries no
    problem — so a run whose ONLY unusual fact is a dirty shared tree still exits 0. A
    standalone detection leg was refused as #83's class precisely because a report of a
    state nobody will fix must never move the verdict; this asserts the rider kept that
    property.
    """
    issues = [_issue(1, "OPEN")]
    # The `ruling` row is here so the fixture is CLEAN apart from the dirty tree: the
    # board-unruled leg (added after this probe's fixture was first written) REDs on an
    # intaken OPEN item with no ruling row, and a probe whose exit code is moved by an
    # unrelated leg would be asserting that leg rather than the rider's non-gating.
    rows = _swept(("intake", "#1", 1), ("ruling", "#1", 2))

    def _dirty_rider(*, read_at: str, **_kw) -> dict:
        return _rider(
            read_at=read_at,
            dirty=[" M TEMPLATE/registry/kit.example.json"],
            blocking=["TEMPLATE/registry/kit.example.json"],
        )

    rc, out, _ = _run(issues, rows, shared_tree_fn=_dirty_rider)
    assert rc == 0, f"the rider must not move the exit code\n{out}"
    assert out.count("shared tree rider") == 1, f"the rider prints ONCE\n{out}"
    assert "~ TEMPLATE/registry/kit.example.json" in out, out
    head = out.split("LEG ")[0]
    assert "shared tree rider" in head, (
        f"the rider must precede the board legs it qualifies\n{out}"
    )
    assert "read at " in head, out

def test_538_a_delivery_that_EXISTS_is_never_a_problem_and_a_closed_subject_is_history() -> None:
    """#538, ruled at ledger n=4029: the leg counted its OWN cleared verdicts as problems.

    Measured on the 2026-10-21 read: 96 problems, of which 57 were WINDOW MISMATCHES for
    units that were delivered and then CLOSED, 17 were absences for CLOSED units, and 6 were
    WINDOW MISMATCHES for units still OPEN whose own line says "a DELIVERY EXISTS ... do not
    re-dispatch". So 74 of 96 were history and 6 more were self-cleared -- a count that could
    only RISE as the factory closed more work, which is not a measure of debt.

    THREE ARMS, ALL REQUIRED (the ruling's own positive control). Arm 2 is the one that pins
    it: without it, a leg that simply stopped reading stores would pass arms 1 and 3 and look
    like a fix.
    """
    now = dt.datetime.now(dt.timezone.utc)
    read_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    # 2 h after the write stamp: inside the horizon, past the 5400 s forward window bound.
    landed_at = dispatched + dt.timedelta(hours=2)
    open_board = [{"number": 83, "state": "open"}]
    closed_board = [{"number": 83, "state": "closed"}]

    def _row():
        return _stall_row(171, "dispatch", "#83", 0, now=dispatched, actor="triage",
                          refs=[{"session": _PROBE_TARGET}])

    def _leg(issues, deliveries):
        return RUNNER.dispatch_delivery_leg(
            [_row()], read_at=read_at, bound=bound, issues=issues,
            deliveries_fn=lambda: (deliveries, ["probe-home"], []),
        )

    near = [_delivery(landed_at, "[session-notify from=abc]\nDISPATCH #83 to the lane",
                      session=_PROBE_TARGET)]

    # ARM 1 -- subject OPEN, delivery OUTSIDE the window: EXCUSED, in the window-mismatch
    # key, ABSENT from problems. Every instant and the window survive in the text.
    arm1 = _leg(open_board, near)
    assert arm1["problems"] == [], arm1["problems"]
    assert arm1["coverage"]["delivered_outside_window"] == 1, arm1["coverage"]
    assert "WINDOW MISMATCH" in arm1["excused"][0], arm1["excused"]
    assert landed_at.strftime("%Y-%m-%dT%H:%M:%SZ") in arm1["excused"][0], arm1["excused"]

    # ARM 2 -- subject OPEN, NO delivery in any store: still a PROBLEM, unchanged. This is
    # the arm that makes arms 1 and 3 mean something.
    arm2 = _leg(open_board, [])
    assert len(arm2["problems"]) == 1, arm2["problems"]
    assert "records no delivery" in arm2["problems"][0], arm2["problems"]
    assert arm2["coverage"]["delivered_outside_window"] == 0, arm2["coverage"]

    # ARM 3 -- subject CLOSED, ANY delivery state: excused, counted under
    # judged_closed_subject, ABSENT from problems -- and this holds for BOTH a delivery that
    # exists and one that does not, because a finished unit owes nothing either way.
    for deliveries, label in ((near, "a delivery"), ([], "no delivery")):
        arm3 = _leg(closed_board, deliveries)
        assert arm3["problems"] == [], (
            f"a CLOSED subject owes nothing, with {label}\n{arm3['problems']}"
        )
        assert arm3["coverage"]["dispatch_rows_closed_subject"] == 1, arm3["coverage"]
        assert arm3["coverage"]["judged_closed_subject"] == ["#83"], arm3["coverage"]
        assert arm3["coverage"]["dispatch_rows_examined"] == 0, (
            f"a closed-subject row is scoped OUT of the judged population\n{arm3['coverage']}"
        )

    # THE BOARD READ IS WHAT DECIDES IT, and its absence is stated rather than assumed: with
    # no board injected nothing is scoped out, so arm 3's row is judged exactly as before.
    no_board = _leg(None, [])
    assert no_board["coverage"]["board_read"] is False, no_board["coverage"]
    assert no_board["coverage"]["dispatch_rows_closed_subject"] == 0, no_board["coverage"]
    assert len(no_board["problems"]) == 1, (
        f"with no board read, the row must still be judged\n{no_board['problems']}"
    )

    # THE MUTATION BITE: neuter the board scoping and arm 3 must go RED, so the clean verdict
    # above is attributable to the scoping rather than to the fixture.
    real = RUNNER.closed_board_numbers
    try:
        RUNNER.closed_board_numbers = lambda issues: set()
        neutered = _leg(closed_board, [])
    finally:
        RUNNER.closed_board_numbers = real
    assert neutered["problems"], (
        "the scoping must BITE: with it neutered, a closed-subject row reads as a problem"
    )

def test_538_the_render_PRINTS_the_scoping_and_the_board_it_read() -> None:
    """#538: the scoped-out population is a FIGURE, never N problem lines -- and the board
    read that produced it travels with the figure, so `0 scoped out` cannot stand for both
    "nothing was closed" and "no board was read" (#116)."""
    now = dt.datetime.now(dt.timezone.utc)
    bound = (now - dt.timedelta(days=1), "probe-bound", "")
    dispatched = now - dt.timedelta(hours=1)
    row = _stall_row(181, "dispatch", "#84", 0, now=dispatched, actor="triage",
                     refs=[{"session": _PROBE_TARGET}])
    near = _delivery(dispatched + dt.timedelta(hours=2),
                     "[session-notify from=abc]\nDISPATCH #84 to the lane",
                     session=_PROBE_TARGET)

    # AN INTAKE ROW KEEPS AN UNRELATED LEG OUT OF THE rc: the assertion below is about
    # whether an EXCUSED mismatch moves the exit code, so no other leg may move it either.
    intake = _stall_row(180, "intake", "#84", 0, now=dispatched, actor="triage")
    rc, out, _ = _run([{"number": 84, "state": "open"}], [intake, row], delivery_scope=bound,
                      deliveries=[near])
    assert "LEG dispatch-delivery — ASSERTED" in out, out
    assert "delivered OUTSIDE the window (excused, never a problem): 1 row(s)" in out, out
    assert "scoped OUT as history: 0 dispatch row(s)" in out, out
    assert "carrying 0 closed" in out, out
    assert "    excused: n=181 (#84)" in out, (
        f"each excused instance keeps its own instant and window\n{out}"
    )
    # The run is CLEAN: a delivery that exists moves no exit code (#538).
    assert rc == 0, f"an excused mismatch must not red the run\n{out}"

    rc2, out2, _ = _run([{"number": 84, "state": "closed"}], [intake, row],
                        delivery_scope=bound, deliveries=[near])
    assert "scoped OUT as history: 1 dispatch row(s)" in out2, out2
    assert "carrying 1 closed" in out2, out2
    assert "judged_closed_subject" in out2, out2
    assert rc2 == 0, out2

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
