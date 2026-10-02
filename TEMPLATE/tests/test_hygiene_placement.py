#!/usr/bin/env python3
"""Gate: hygiene's placement map REPORTS a file outside its declared content class.

`ONTOLOGY.md` states the naming half of this surface only as *patterns* (`## Naming law`),
and nothing answered the placement half at all — so a file could sit in a directory its
content does not belong to and every leg of `tools/hygiene.py` would still read clean.
The name census (`tools/kit_names.py`) answers a different question (one name meaning two
things across TREES) and is cited by the law doc, not replaced here (G5 in the surface
inventory).

What this gate holds, and why each arm is needed:

  * the leg holds NO removal path — asserted by reading the leg's own SOURCE, because a
    promise in a docstring is not a mechanism (#220), and a misplaced file is a decision
    for a human to make, never something this leg moves;
  * `removes` is False in the leg's own coverage, so a reader of the REPORT is told the
    same thing the code says;
  * the map is checked against the TREE, not against itself — a top-level directory that
    neither `PLACEMENT_MAP` nor `PLACEMENT_UNMAPPED` names is reported as UNDECLARED, so a
    new directory cannot arrive without a declared content class;
  * the clean verdict is a VERDICT and not a silence: the same call is shown to report a
    planted misplaced file, and the live run is shown to carry files at all;
  * the naming half is read from the LAW's own pattern (`evidence/scores/YYYY-MM-DD.md`),
    with a matching and a non-matching fixture so the pattern is shown to discriminate;
  * an absent directory and an empty one are distinguishable, and neither is a clean zero;
  * a mapped directory is judged in the shipped mirror too, where `TEMPLATE/<rel>` exists;
  * every unmapped directory STATES its reason, so an exemption is a declaration rather
    than an omission;
  * the tool PRINTS the map on every run, driven through the real `main()`.

Every fixture is planted under a THROWAWAY root, never in the live tree: this gate reads
no live board and no fleet manifest, so it passes in a bootstrapped factory exactly as it
does here.

Run:  python3 -m pytest tests/test_hygiene_placement.py -q
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
HYGIENE = REPO / "tools" / "hygiene.py"

def _load_hygiene():
    spec = importlib.util.spec_from_file_location("hygiene_placement_under_test", HYGIENE)
    assert spec and spec.loader, f"cannot load {HYGIENE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

hygiene = _load_hygiene()

LEG_FUNCTIONS = (
    "placement_leg",
    "render_placement",
    "content_class",
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
    return "\n".join(
        inspect.getsource(getattr(hygiene, name)) for name in LEG_FUNCTIONS
    )

def _fixture(root: Path) -> Path:
    """A minimal tree whose directories carry the classes the map declares."""
    (root / "registry").mkdir(parents=True)
    (root / "registry" / "gates.json").write_text("{}")
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "law.md").write_text("prose")
    (root / "evidence" / "scores").mkdir(parents=True)
    (root / "evidence" / "scores" / "2026-01-01.md").write_text("a score record")
    (root / "reviews").mkdir(parents=True)
    return root

def _leg(root: Path) -> dict:
    return hygiene.placement_leg(root)

def _mismatch_paths(leg: dict) -> list[str]:
    return [record["path"] for record in leg["mismatches"]]

# --------------------------------------------------------------------------------------
# The leg is REPORT-ONLY, and says so in code as well as in prose.
# --------------------------------------------------------------------------------------

def test_the_leg_holds_no_removal_path():
    source = _leg_source()
    offenders = [verb for verb in REMOVAL_VERBS if verb in source]
    assert not offenders, (
        f"the placement leg carries a removal/write path {offenders} — it must REPORT a "
        "misplaced file, never move or delete it (#220)"
    )

def test_the_leg_declares_removes_false():
    with tempfile.TemporaryDirectory() as tmp:
        leg = _leg(_fixture(Path(tmp)))
    assert leg["removes"] is False, (
        "the leg's own coverage must declare removes: False, so the report tells a reader "
        "what the source already says"
    )

# --------------------------------------------------------------------------------------
# The map is checked against the TREE: a directory nobody declared is reported.
# --------------------------------------------------------------------------------------

def test_every_top_level_directory_is_DECLARED():
    leg = _leg(REPO)
    assert leg["undeclared"] == [], (
        "top-level directories that hold files but are named by neither PLACEMENT_MAP nor "
        f"PLACEMENT_UNMAPPED: {leg['undeclared']} — a directory must not arrive without a "
        "declared content class"
    )

def test_every_unmapped_directory_states_its_REASON():
    leg = _leg(REPO)
    assert leg["unmapped"], (
        "this tree is expected to carry at least one deliberately unmapped directory; an "
        "empty list would mean the map claims to cover everything"
    )
    for record in leg["unmapped"]:
        assert record["reason"].strip(), (
            f"{record['dir']} is unmapped with no reason — an exemption must be a "
            "declaration, not an omission"
        )

def test_an_undeclared_directory_is_REPORTED():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "brand-new").mkdir()
        (root / "brand-new" / "thing.txt").write_text("x")
        leg = _leg(root)
    assert "brand-new" in leg["undeclared"], (
        "a top-level directory holding files and named nowhere must be reported as "
        "UNDECLARED, or the map would be self-describing and could never see drift"
    )

def test_an_empty_undeclared_directory_is_NOT_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "empty-container").mkdir()
        leg = _leg(root)
    assert "empty-container" not in leg["undeclared"], (
        "a directory holding no files directly is a container, not a placement decision — "
        "the check is about where FILES live"
    )

# --------------------------------------------------------------------------------------
# The placement verdict, with its positive control.
# --------------------------------------------------------------------------------------

def test_a_misplaced_file_is_REPORTED():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "registry" / "notes.py").write_text("# a program in a register directory")
        leg = _leg(root)
    assert "registry/notes.py" in _mismatch_paths(leg), (
        "a python file in a json-only register must be reported as a placement mismatch"
    )
    record = next(r for r in leg["mismatches"] if r["path"] == "registry/notes.py")
    assert record["class"] == "python" and record["allowed"] == ["json"]
    assert record["basis"].strip(), "a mismatch must carry WHY the directory declares that class"

def test_the_SAME_fixture_with_an_ALLOWED_class_is_clean():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "registry" / "another.json").write_text("{}")
        leg = _leg(root)
    assert leg["mismatches"] == [], (
        "the positive control: the same directory, a file of an ALLOWED class, must be "
        f"clean — got {_mismatch_paths(leg)}"
    )

def test_an_unknown_suffix_is_NOT_silently_defaulted():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "registry" / "notes.log").write_text("x")
        leg = _leg(root)
    assert "registry/notes.log" in _mismatch_paths(leg), (
        "an unrecognised suffix must be reported as unknown rather than defaulted to a "
        "class the map might allow"
    )

def test_the_live_tree_reports_no_mismatch():
    leg = _leg(REPO)
    assert leg["status"] == "ASSERTED"
    assert leg["files"] > 0, (
        "the clean verdict is vacuous unless the leg actually examined files"
    )
    assert leg["mismatches"] == [], (
        f"live placement mismatches: {_mismatch_paths(leg)}"
    )
    assert leg["naming"] == [], (
        f"live naming mismatches: {[r['path'] for r in leg['naming']]}"
    )

# --------------------------------------------------------------------------------------
# The naming half, read from the law's own pattern, with both arms.
# --------------------------------------------------------------------------------------

def test_a_misnamed_score_record_is_REPORTED():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "evidence" / "scores" / "notes.md").write_text("not a dated record")
        leg = _leg(root)
    assert "evidence/scores/notes.md" in [r["path"] for r in leg["naming"]], (
        "ONTOLOGY.md states `evidence/scores/YYYY-MM-DD.md`; a file that does not match "
        "that pattern must be reported"
    )

def test_a_date_named_score_record_is_clean():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "evidence" / "scores" / "2026-10-02.md").write_text("a score record")
        (root / "evidence" / "scores" / "2026-10-02-self-audit.md").write_text("a variant")
        leg = _leg(root)
    assert leg["naming"] == [], (
        "the positive control: the law's own example, and its labelled variant, must both "
        f"pass — got {[r['path'] for r in leg['naming']]}"
    )

# --------------------------------------------------------------------------------------
# An absent directory is a state, not a clean zero.
# --------------------------------------------------------------------------------------

def test_an_absent_directory_is_ABSENT_and_never_a_clean_zero():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "registry").mkdir()
        (root / "registry" / "gates.json").write_text("{}")
        leg = _leg(root)
    absent = {r["dir"] for r in leg["directories"] if r["status"] == "absent"}
    assert "evidence" in absent and "docs" in absent, (
        "a mapped directory this tree does not carry must be reported `absent` — a missing "
        f"directory that read as zero mismatches would be exempt by silence; got {absent}"
    )
    assert leg["status"] == "ASSERTED", "an absent directory does not make the run NOT RUN"

def test_a_root_that_is_not_a_directory_is_NOT_RUN():
    leg = hygiene.placement_leg(REPO / "no" / "such" / "directory")
    assert leg["status"] == "NOT RUN", (
        "an unreadable root must be NOT RUN with its reason, never a clean zero"
    )
    assert leg["reason"].strip()

# --------------------------------------------------------------------------------------
# The shipped mirror is judged too, and the report prints one line per directory.
# --------------------------------------------------------------------------------------

def test_the_TEMPLATE_mirror_is_judged_when_it_exists():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "TEMPLATE" / "registry").mkdir(parents=True)
        (root / "TEMPLATE" / "registry" / "notes.py").write_text("# misplaced in the mirror")
        leg = _leg(root)
    assert "TEMPLATE/registry/notes.py" in _mismatch_paths(leg), (
        "TEMPLATE/ is the shipped mirror of the root by construction, so a mapped "
        "directory must be judged there too — a factory inheriting a misplaced file is "
        "the harm this covers"
    )

def test_the_report_prints_one_line_per_declared_directory():
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(Path(tmp))
        (root / "registry" / "notes.py").write_text("# misplaced")
        leg = _leg(root)
    text = hygiene.render_placement(leg)
    assert text.splitlines()[0].startswith("hygiene placement:")
    assert "removes: no" in text, "the report must carry the removes declaration"
    for record in leg["directories"]:
        if record["status"] != "absent":
            assert record["dir"] in text, (
                f"{record['dir']} is judged but not printed — an unprinted population is "
                "the exempt-by-silence surface"
            )
    assert "MISMATCH registry/notes.py" in text

def test_the_tool_PRINTS_the_placement_map_on_every_run():
    result = subprocess.run(
        [sys.executable, str(HYGIENE)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "hygiene placement:" in combined, (
        "the tool must PRINT the placement map on every run, not only under a flag"
    )
    assert "removes: no" in combined
    # The exit code is deliberately NOT asserted: this factory's tree is shared, so a peer
    # lane's stranded path legitimately makes the audit non-zero, and that is not this
    # gate's subject.
