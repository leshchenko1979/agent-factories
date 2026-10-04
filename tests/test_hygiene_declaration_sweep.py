#!/usr/bin/env python3
"""Gate: hygiene's declaration cross-sweep REPORTS a stale debt and never writes.

The declaration families live under `docs/` — the exemption surfaces, where an
unmatched entry is a stale debt. Each surface's own tool reads its own file and checks it
for READABILITY; not one of them asks whether the thing an entry POINTS AT still exists.
So an exemption left behind by a rename or a deletion sits there looking live, and every
surface still reads green. The class is named in `tools/hygiene.py`'s own docstring and
nothing acted on it (G2 in the surface inventory).

What this gate holds, and why each arm is needed:

  * the leg holds NO removal path — asserted by reading the leg's own SOURCE, because a
    promise in a docstring is not a mechanism (#220), and each surface's own tool keeps
    its own write path;
  * `removes` is False in the leg's coverage, so a reader of the REPORT is told the same
    thing the code says;
  * the population is the TREE's, not the map's — a sixteenth declaration family appearing
    under `docs/` is reported as UNDECLARED, which is the drift a self-describing map
    cannot see;
  * the zero on the live run is a VERDICT and not a silence: the same call is shown to
    report a planted missing target, and the live run is shown to carry targets at all;
  * a missing target is reported for BOTH kinds, each with its own instrument, and the
    commit instrument is shown to answer both ways on the real repository;
  * an ABSENT file and an unreadable one are distinguishable, and neither is a clean zero;
  * the tool PRINTS the sweep on every run, driven through the real `main()`.

Run:  python3 -m pytest tests/test_hygiene_declaration_sweep.py -q
Exit: 0 clean, non-zero on any regression in the report leg.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# BOTH INVOCATION MODES MUST REACH THE GUARD (#199). The audit invokes this gate in PYTEST
# mode, and this module has no `main()` at all, so the guard is a module-level `pytestmark`:
# it COLLECTS the tests and SKIPS them (exit 0). A module-level `pytest.skip` would exit 5
# ("no tests were collected"), which the audit reads as a failure.
# STATED SKIP: evidence/ (BOOTSTRAP-created, steps 4b/4c)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_boundary import module_skip  # noqa: E402

_SKIP_REASON = module_skip(REPO)
if _SKIP_REASON:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(True, reason=_SKIP_REASON)
HYGIENE = REPO / "tools" / "hygiene.py"

def _load_hygiene():
    spec = importlib.util.spec_from_file_location("hygiene_declaration_sweep_under_test", HYGIENE)
    assert spec and spec.loader, f"cannot load {HYGIENE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

hygiene = _load_hygiene()

def _plant(root: Path, family: str, payload: dict) -> Path:
    """A declaration file at the coordinate the map expects, under a throwaway root."""
    rel = dict(
        (f, r) for f, r, *_ in hygiene.DECLARATION_SURFACES
    )[family]
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path

def _family(leg: dict, name: str) -> dict:
    for record in leg["families"]:
        if record["family"] == name:
            return record
    raise AssertionError(f"{name} is not in the sweep's population: "
                         f"{[f['family'] for f in leg['families']]}")

# --- the refusal, asserted structurally -------------------------------------

def test_the_leg_holds_no_removal_path() -> None:
    """The refusal, asserted STRUCTURALLY rather than promised in prose (#220).

    `tools/hygiene.py` DOES carry a reaper — that is the tool's job for scratch files — so
    the module cannot be scanned as a whole. The functions that make up this leg are
    scanned instead, which is the narrower and the honest claim: whatever the reaper does
    elsewhere, THIS leg cannot remove or rewrite anything.
    """
    for fn in (hygiene.declaration_sweep_leg, hygiene.render_declaration_sweep,
               hygiene._declaration_probe_targets, hygiene.declaration_families_on_disk,
               hygiene._path_exists, hygiene._commit_exists):
        source = inspect.getsource(fn)
        for verb in ("rmtree", "os.remove", "unlink", "shutil.move", "os.rmdir",
                     "write_text", "open(", "replace("):
            assert verb not in source, (
                f"{fn.__name__} carries a write/removal verb {verb!r}: the cross-sweep is "
                f"report-only, and the surface's own tool owns its own file"
            )

def test_the_leg_declares_removes_false() -> None:
    """A reader of the REPORT is told the same thing the source scan just proved."""
    leg = hygiene.declaration_sweep_leg(root=REPO)
    assert leg["removes"] is False, leg["removes"]
    assert "removes: no" in hygiene.render_declaration_sweep(leg)

# --- the population is the TREE's, not the map's -----------------------------

def test_every_declaration_family_on_disk_is_DECLARED() -> None:
    """The drift control: a family this tree carries that the map does not name is a gap.

    The map cannot be its own population — a sixteenth declaration file appearing under
    `docs/` would be swept by nothing while the sweep reported every family it knew about
    as covered. The tree is the independent declaration of the population, and this is the
    leg that compares the two. One direction only, on purpose: a family the map names and
    the tree does not carry is legitimate (a member ships the skeletons and no live files),
    so a bootstrapped factory is green here rather than taxed.
    """
    on_disk = hygiene.declaration_families_on_disk(REPO)
    declared = {family for family, *_ in hygiene.DECLARATION_SURFACES}
    undeclared = sorted(set(on_disk) - declared)
    assert undeclared == [], (
        f"{undeclared} appear under docs/ but DECLARATION_SURFACES does not name them, so "
        f"nothing sweeps their entries"
    )
    assert len(declared) == len(hygiene.DECLARATION_SURFACES), (
        f"the map carries {len(hygiene.DECLARATION_SURFACES)} entries but names "
        f"{len(declared)} distinct families — a duplicate family name collapses the set, "
        f"and the surface it shadowed goes unswept while the map still reads complete"
    )
    assert hygiene.declaration_sweep_leg(root=REPO)["undeclared"] == []

def test_the_map_covers_EVERY_family_the_tree_carries() -> None:
    """The sweep's own line, and the live population is non-empty so the zero is a verdict.

    A clean sweep over an EMPTY population proves nothing: the same zero would print if the
    map pointed at files that are not there. The count is the arm that separates them.
    """
    leg = hygiene.declaration_sweep_leg(root=REPO)
    assert leg["live_files"] > 0, leg
    assert leg["targets"] > 0, "the sweep found no target at all, so 0 unmatched is vacuous"
    # Derived, never a literal: this arm catches a leg that SKIPS a declared family (a
    # branch that returns without appending), not a population that grows whenever a new
    # declaration surface lands. A pinned constant reds on growth and proves nothing —
    # the stale-constant defect #304 repaired.
    assert len(leg["families"]) == len(hygiene.DECLARATION_SURFACES), (
        len(leg["families"]), len(hygiene.DECLARATION_SURFACES)
    )
    assert leg["unmatched"] == 0, [f["unmatched"] for f in leg["families"] if f["unmatched"]]

# --- the bite: a planted target that is gone ---------------------------------

def test_a_planted_missing_PATH_is_reported_as_a_stale_debt() -> None:
    """THE BITE. The leg names the target that is gone, and the fixture is otherwise clean."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "law-uuid-exemptions",
               {"exempt": [{"path": "skills/gone/SKILL.md", "uuid": "0" * 36}]})
        leg = hygiene.declaration_sweep_leg(root=root)
        record = _family(leg, "law-uuid-exemptions")
        assert record["status"] == "swept", record
        assert record["unmatched"] == ["path:skills/gone/SKILL.md"], record
        assert leg["unmatched"] == 1, leg
        assert "path:skills/gone/SKILL.md" in hygiene.render_declaration_sweep(leg)

def test_the_SAME_fixture_with_a_LIVE_path_is_clean() -> None:
    """The positive control: the difference is attributable to the target, not the fixture.

    Same family, same file, same shape — one character of the path changed to point at a
    file that is there. A leg that reported the first and the second alike would be
    answering the fixture rather than the question.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "skills" / "live").mkdir(parents=True)
        (root / "skills" / "live" / "SKILL.md").write_text("x", encoding="utf-8")
        _plant(root, "law-uuid-exemptions",
               {"exempt": [{"path": "skills/live/SKILL.md", "uuid": "0" * 36}]})
        leg = hygiene.declaration_sweep_leg(root=root)
        record = _family(leg, "law-uuid-exemptions")
        assert record["targets"] == 1, record
        assert record["unmatched"] == [], record
        assert leg["unmatched"] == 0, leg

def test_a_planted_missing_COMMIT_is_reported() -> None:
    """The second kind: an exemption keyed by a commit that this history does not carry."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "ledger-commit-exemptions",
               {"exemptions": [{"sha": "0" * 40, "date": "2026-01-01", "reason": "x"}]})
        leg = hygiene.declaration_sweep_leg(
            root=root, commit_fn=lambda _root, _sha: False
        )
        record = _family(leg, "ledger-commit-exemptions")
        assert record["unmatched"] == [f"commit:{'0' * 40}"], record

def test_the_commit_instrument_answers_BOTH_ways_on_the_real_repository() -> None:
    """The instrument itself, against the live object database — not a stub.

    A checker that always returned False would report every commit exemption as dead debt,
    and one that always returned True would report none. Both are refuted here: HEAD is in
    this history and forty zeros are not.
    """
    assert hygiene._commit_exists(REPO, "HEAD") is True
    assert hygiene._commit_exists(REPO, "0" * 40) is False

def test_an_unanswerable_commit_check_is_NOT_RUN_and_never_a_clean_zero() -> None:
    """A missing instrument is a THIRD state: it is not evidence that a target is alive."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "ledger-commit-exemptions",
               {"exemptions": [{"sha": "0" * 40, "date": "2026-01-01", "reason": "x"}]})
        leg = hygiene.declaration_sweep_leg(
            root=root, commit_fn=lambda _root, _sha: None
        )
        record = _family(leg, "ledger-commit-exemptions")
        assert record["status"] == "NOT RUN", record
        assert "git unavailable" in record["reason"], record
        assert "NOT RUN" in hygiene.render_declaration_sweep(leg)

# --- absence, and the families that carry no target ---------------------------

def test_an_absent_file_is_ABSENT_and_never_a_clean_zero() -> None:
    """No live file and a swept-clean file must not render as the same verdict."""
    with tempfile.TemporaryDirectory() as tmp:
        leg = hygiene.declaration_sweep_leg(root=Path(tmp))
        record = _family(leg, "law-uuid-exemptions")
        assert record["status"] == "absent", record
        assert "absent (no live file)" in hygiene.render_declaration_sweep(leg)
        assert leg["live_files"] == 0 and leg["targets"] == 0, leg

def test_every_unswept_family_states_its_REASON() -> None:
    """A family with no probe is a DECLARATION, not an omission — the note is required.

    The alternative is a family quietly absent from the map, which is the failure this gap
    is about: a surface that reads clean because nothing looked at it.
    """
    for family, rel, probes, note in hygiene.DECLARATION_SURFACES:
        if not probes:
            assert note.strip(), f"{family} declares no probe and no reason"
            assert note.strip() not in ("-", "n/a"), f"{family}: note is a placeholder"
        else:
            assert note == "", f"{family} carries probes AND a not-swept note"
        assert rel.startswith("docs/") and rel.endswith(".json"), (family, rel)

def test_the_report_prints_one_line_per_family() -> None:
    """The acceptance shape: every family on its own line, with its count."""
    leg = hygiene.declaration_sweep_leg(root=REPO)
    rendered = hygiene.render_declaration_sweep(leg)
    for record in leg["families"]:
        assert record["family"] in rendered, record["family"]
    body = [line for line in rendered.splitlines() if line.startswith("  ")]
    assert len(body) == len(leg["families"]), (len(body), len(leg["families"]))

# --- the ruling's other half: it is PRINTED on every run ----------------------

def test_the_tool_PRINTS_the_sweep_on_every_run() -> None:
    """Driven through the real `main()`, because a leg never rendered is invisible.

    The exit code is NOT asserted: this tool legitimately exits non-zero when a peer lane's
    file is mid-flight in the shared tree, and that is a fact about the tree rather than
    about the sweep. The line's presence is the claim under test.
    """
    proc = subprocess.run(
        [sys.executable, str(HYGIENE)],
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert "hygiene declaration sweep:" in proc.stdout, proc.stdout[-600:] + proc.stderr[-400:]
    assert "removes: no" in proc.stdout, proc.stdout[-600:]
