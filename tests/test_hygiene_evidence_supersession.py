#!/usr/bin/env python3
"""Gate: hygiene's evidence-supersession leg REPORTS the prose-only supersessions (G7).

`evidence/` and `reviews/` are append-only history -- an artifact is never deleted when a
later run replaces it -- so the ONLY thing that says which snapshot governs is a hand-written
notice, or the reader noticing that a later dated sibling exists. Measured 2026-10-02: 25
dated artifacts over 15 families, 6 families with more than one member, and ZERO
`superseded_by` markers anywhere in the tree. Every supersession in this repository is
prose-only, which is the gap G7 names.

What this gate holds, and why each arm is needed:

  * the leg holds NO removal path -- asserted by reading the leg's own SOURCE, because a
    promise in a docstring is not a mechanism (#220), and `evidence/` is append-only history
    a later run replaces by ADDING, never by deleting;
  * `removes` is False in the leg's own coverage AND in the rendered line;
  * the naming convention DISCRIMINATES: in a two-member family the older artifact is
    reported and the newest is not, so a leg that simply flagged every dated file would red
    here;
  * a TIE at the newest date is NOT a supersession -- a suffix distinguishes a variant, so
    two same-date siblings are both current. This is the live `instrument-census-insights`
    case (a plain census beside a `-refused` one), asserted on the real tree;
  * the prose signal catches the SINGLETON case the convention cannot see, where a file
    names a successor outside its own family;
  * a prose notice naming a path that does NOT exist is NOT a supersession -- the pattern is
    deliberately narrow, so a bare "superseded" in prose (this tree uses the word for ledger
    rows and channel surfaces) cannot be read as an artifact relation;
  * a mechanical marker naming an EXISTING path EXCUSES the artifact, so the number MOVES;
  * a marker naming a path that does NOT exist is a STALE MARKER, reported SEPARATELY and
    never folded into `marked` -- a fabricated supersession is worse than an unmarked one,
    because it reads as a decision somebody made;
  * an absent `evidence/` tree is `absent` and an unreadable one is NOT RUN, neither of them
    a clean zero: a bootstrapped factory has no evidence/ yet, and a silent zero there is the
    exempt-by-silence surface;
  * the live tree is non-vacuous and the report names the current prose-only supersessions;
  * the tool PRINTS the leg on every run, driven through the real `main()`.

Every fixture is planted under a THROWAWAY root, never in the live tree: this gate reads no
live board and no fleet manifest, so it passes in a bootstrapped factory exactly as it does
here.

Run:  python3 -m pytest tests/test_hygiene_evidence_supersession.py -q
Exit: 0 clean, non-zero on any regression in the report leg.
"""

from __future__ import annotations

import importlib.util
import inspect
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
    spec = importlib.util.spec_from_file_location("hygiene_evidence_under_test", HYGIENE)
    assert spec and spec.loader, f"cannot load {HYGIENE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hygiene = _load_hygiene()

LEG_FUNCTIONS = (
    "evidence_supersession_leg",
    "render_evidence_supersession",
    "_dated_artifacts",
    "_reads_marker",
    "_names_successor",
)

REMOVAL_VERBS = (
    "rmtree",
    "os.remove",
    "unlink",
    "shutil.move",
    "os.rmdir",
    "write_text",
    "open(",
    "replace(",
)


def _leg_source() -> str:
    return "\n".join(inspect.getsource(getattr(hygiene, name)) for name in LEG_FUNCTIONS)


def _plant(root: Path, name: str, text: str = "a census\n") -> Path:
    path = root / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _leg(root: Path) -> dict:
    return hygiene.evidence_supersession_leg(root)


def _prose_only(leg: dict) -> list[str]:
    return [entry["path"] for entry in leg["prose_only"]]


# --------------------------------------------------------------------------------------
# The leg is REPORT-ONLY, and says so in code as well as in prose.
# --------------------------------------------------------------------------------------


def test_the_leg_holds_no_removal_path():
    source = _leg_source()
    offenders = [verb for verb in REMOVAL_VERBS if verb in source]
    assert not offenders, (
        f"the evidence-supersession leg carries a removal/write path {offenders} -- "
        "`evidence/` is append-only history and this leg only REPORTS (#220)"
    )


def test_the_leg_declares_removes_false():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "census-2026-01-01.md")
        _plant(root, "census-2026-01-02.md")
        leg = _leg(root)
    assert leg["removes"] is False
    assert "(removes: no)" in hygiene.render_evidence_supersession(leg)


# --------------------------------------------------------------------------------------
# The naming convention discriminates.
# --------------------------------------------------------------------------------------


def test_the_naming_convention_reports_the_older_and_NOT_the_newest():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "kit-drift-census-2026-01-01.md")
        _plant(root, "kit-drift-census-2026-01-02.md")
        leg = _leg(root)
    assert _prose_only(leg) == ["evidence/kit-drift-census-2026-01-01.md"], (
        f"only the OLDER member is superseded; got {_prose_only(leg)}"
    )
    assert "evidence/kit-drift-census-2026-01-02.md" not in _prose_only(leg), (
        "the newest member of a family is current and must never be reported"
    )


def test_a_TIE_at_the_newest_date_is_NOT_a_supersession():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "census-2026-01-02.md")
        _plant(root, "census-2026-01-02-refused.md")
        leg = _leg(root)
    assert _prose_only(leg) == [], (
        "two same-date siblings are both CURRENT -- a suffix distinguishes a variant, not "
        f"an older snapshot; got {_prose_only(leg)}"
    )
    assert leg["by_convention"] == []


def test_the_live_insights_TIE_is_read_as_current():
    """The real `instrument-census-insights` pair: a plain census beside a `-refused` one."""
    leg = hygiene.evidence_supersession_leg(REPO)
    assert leg["status"] == "ASSERTED"
    tied = "evidence/instrument-census-insights-2026-09-28.md"
    refused = "evidence/instrument-census-insights-2026-09-28-refused.md"
    assert tied in [a["path"] for a in leg["artifacts"]], "the plain census must be in scope"
    assert refused in [a["path"] for a in leg["artifacts"]]
    assert tied not in leg["by_convention"] and refused not in leg["by_convention"], (
        "a tie at the newest date must not be read as a supersession on the live tree"
    )


def test_a_SINGLETON_superseded_by_prose_is_caught_by_the_other_signal():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "lone-report-2026-01-01.md", "Superseded by `successor-2026-02-01.md`.\n")
        _plant(root, "successor-2026-02-01.md")
        leg = _leg(root)
    assert "evidence/lone-report-2026-01-01.md" in leg["by_prose"], (
        "a prose notice naming a successor is a supersession even with no dated sibling"
    )
    assert "evidence/lone-report-2026-01-01.md" in _prose_only(leg)


def test_a_prose_notice_naming_a_MISSING_path_is_NOT_a_supersession():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "lone-2026-01-01.md", "Superseded by `nowhere-2026-02-01.md`.\n")
        leg = _leg(root)
    assert leg["by_prose"] == [], (
        "a notice naming a path that does not exist is not an artifact relation; the "
        "pattern is narrow so a bare 'superseded' in prose cannot be read as one"
    )
    assert _prose_only(leg) == []


def test_a_bare_SUPERSEDED_word_is_not_a_supersession():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(
            root,
            "lone-2026-01-01.md",
            "The measurement was superseded by a later run, and the row is superseded.\n",
        )
        leg = _leg(root)
    assert leg["by_prose"] == [], (
        "this tree uses 'superseded' for ledger rows and channel surfaces; only a notice "
        "naming a PATH is an artifact relation"
    )


# --------------------------------------------------------------------------------------
# The marker EXCUSES, and a marker naming nothing is its own debt.
# --------------------------------------------------------------------------------------


def test_a_mechanical_marker_naming_a_LIVE_path_EXCUSES_the_artifact():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "census-2026-01-01.md", "superseded_by: evidence/census-2026-01-02.md\n")
        _plant(root, "census-2026-01-02.md")
        leg = _leg(root)
    assert leg["marked"] == ["evidence/census-2026-01-01.md"], "the marker must be read"
    assert _prose_only(leg) == [], (
        "a marked artifact is EXCUSED, so the debt census must MOVE when a marker is added"
    )
    assert "1 marked" in hygiene.render_evidence_supersession(leg)


def test_a_marker_naming_a_MISSING_path_is_a_STALE_MARKER_not_a_clean_one():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "census-2026-01-01.md", "superseded_by: evidence/census-2026-01-02.md\n")
        _plant(root, "census-2026-01-03.md")
        leg = _leg(root)
    assert leg["marked"] == [], (
        "a marker whose target does not exist is NOT a satisfied marker"
    )
    assert [e["path"] for e in leg["stale_marker"]] == ["evidence/census-2026-01-01.md"]
    rendered = hygiene.render_evidence_supersession(leg)
    assert "STALE MARKER" in rendered and "does not exist" in rendered, (
        "a fabricated supersession must be reported separately -- it is worse than an "
        "unmarked one, because it reads as a decision somebody made"
    )


# --------------------------------------------------------------------------------------
# An instrument that failed, or a tree that has none, is NOT a clean zero.
# --------------------------------------------------------------------------------------


def test_an_absent_evidence_tree_is_ABSENT_and_never_a_clean_zero():
    with tempfile.TemporaryDirectory() as tmp:
        leg = _leg(Path(tmp))
    assert leg["status"] == "absent", "a bootstrapped factory has no evidence/ yet"
    rendered = hygiene.render_evidence_supersession(leg)
    assert "absent" in rendered and "0 dated artifact" not in rendered, (
        "an absent tree must never render as a clean population of zero"
    )


# --------------------------------------------------------------------------------------
# The live tree: non-vacuous, and the report names the current prose-only set.
# --------------------------------------------------------------------------------------


def test_the_live_tree_is_NON_VACUOUS():
    leg = hygiene.evidence_supersession_leg(REPO)
    assert leg["status"] == "ASSERTED"
    assert len(leg["artifacts"]) > 0, "the live tree carries dated evidence artifacts"
    assert len(leg["families"]) > 0, "and at least one family"
    assert len(leg["by_convention"]) > 0, (
        "the gap G7 names is live: this tree carries dated siblings and none is marked"
    )


def test_the_report_names_each_prose_only_artifact_with_its_successor():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant(root, "kit-drift-census-2026-01-01.md")
        _plant(root, "kit-drift-census-2026-01-02.md")
        leg = _leg(root)
    rendered = hygiene.render_evidence_supersession(leg)
    lines = rendered.splitlines()
    assert lines[0].startswith("hygiene evidence supersession:")
    for fragment in ("dated artifact(s)", "family(ies)", "prose-only", "marked", "removes: no"):
        assert fragment in lines[0], f"the summary line must carry {fragment!r}: {lines[0]}"
    assert any(
        "evidence/kit-drift-census-2026-01-01.md" in line and "superseded by" in line
        for line in lines[1:]
    ), "each prose-only artifact is NAMED with the successor that supersedes it"


def test_the_tool_PRINTS_the_supersession_leg_on_every_run():
    result = subprocess.run(
        [sys.executable, str(HYGIENE)], cwd=str(REPO), capture_output=True, text=True
    )
    combined = result.stdout + result.stderr
    assert "hygiene evidence supersession:" in combined, (
        "the tool must PRINT the supersession census on every run, not only under a flag"
    )
    assert "removes: no" in combined
    # The exit code is deliberately NOT asserted: this factory's tree is shared, so a peer
    # lane's stranded path legitimately makes the audit non-zero, and that is not this
    # gate's subject.
