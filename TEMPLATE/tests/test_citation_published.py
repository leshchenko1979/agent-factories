#!/usr/bin/env python3
"""Gate: a ledger citation is not PUBLISHED before the commit carrying its row is.

Origin: issue #441, ruled at ledger n=2907, dispatched at n=2909.

The defect is an ORDERING one and it is structural, not accidental. A ruling is ONE act
in TWO surfaces: a comment on the PUBLIC board and a `ruling` row in the ledger. The row
is stamped by the same invocation that posts the comment, so the row is by construction
in the WORKING TREE at the instant the comment becomes public -- and a commit authored
this turn cannot be published this turn, because the pusher holds every commit younger
than its 900s grace window (#146/n=1168, scoped by #284/e133c87d). The window is correct
and this gate does not touch it.

Measured 2026-10-08: two ruling comments named `n=2900-2905` on the public board from
06:40:46Z, while the commit carrying those rows was not authored until 06:48:39Z and not
published until 07:09:08Z. For ~28 minutes a public citation named rows that existed
nowhere a reader could go -- and the rows were a RANGE, so a note that expanded only the
first endpoint would have declared 2900 unreachable and stayed silent about the other
five. That is why `cited_rows()` expands ranges and why this gate probes the range form.

WHAT THIS GATE PROVES, AND WHY IT IS OFFLINE
--------------------------------------------
The board side cannot be checked from a test suite -- a gate cannot call `gh`, and the
live board leg belongs to `tools/patrol_host_state.py`. So this gate asserts the half that
travels with the TREE:

  1. The predicate is TWO-SIDED on a real repository: a row in the worktree ledger and
     absent from the tracking ref is reported UNPUBLISHED, and the same read after the
     push reports it published. One side alone is worthless -- a predicate that always
     said "unpublished" would pass the first arm and be useless, and one that always said
     "published" would pass the second.
  2. An UNREADABLE blob is a `reason`, never a clean empty `unpublished`. "I could not
     ask" and "everything is reachable" are different facts and must not render alike.
  3. The acknowledgement NAMES every unpublished row, so a reader of the ruling learns
     the state rather than having to guess it.
  4. The writer is WIRED to the predicate: `main()` resolves the citation state before it
     touches either surface, and the note rides BOTH surfaces (the posted comment and the
     stamped row are the same text). A predicate nothing calls is dead text (P29).

MUTATION CONTROLS
-----------------
Two of the arms above are re-run against a NEUTERED copy of the code, and each must FAIL
there. A probe that has only ever seen the good build has not been shown to bite: the
`high == max` lesson and the disarmed-control lesson (AGENTS.md rule 7) both say the same
thing, and this factory has shipped a vacuously-passing arm before.

Run:  python3 tests/test_citation_published.py
Exit: 0 every arm passed; 1 an arm failed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PUBLISH_TOOL = REPO / "tools" / "publish.py"
RULE_TOOL = REPO / "tools" / "rule.py"
LEDGER_REL = Path("evidence") / "ledger.jsonl"

# `tools/rule.py` imports its neighbours by bare module name (`from field_predicate import
# ...`), exactly as the tools do when run from `tools/`. Loading it by path from here needs
# the same path entry the tool's own runtime has, or the import fails for a reason that has
# nothing to do with what is under test.
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

checks: list[tuple[bool, str, str]] = []

def check(ok: bool, name: str, detail: str = "") -> None:
    checks.append((bool(ok), name, detail))

def load(path: Path, name: str):
    """Import a tool by PATH -- never by name, so a temp mutation is loaded instead."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def git(repo: Path, *args: str, check_rc: bool = True):
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=120)
    if check_rc and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()

def row(n: int, subject: str = "#1") -> str:
    return json.dumps({"n": n, "event": "note", "subject": subject,
                       "detail": f"probe row {n}", "at": "2026-10-08T00:00:00Z"})

def build_repo(root: Path, published: list[int], worktree_extra: list[int] = ()) -> tuple[Path, Path]:
    """A work repo with a bare remote whose ledger carries `published` rows, plus
    `worktree_extra` rows committed but NOT pushed. Returns (work, bare)."""
    bare = root / "remote.git"
    work = root / "work"
    bare.mkdir(parents=True)
    git(bare, "init", "--bare", "-q")
    git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    work.mkdir(parents=True)
    git(work, "init", "-q")
    git(work, "symbolic-ref", "HEAD", "refs/heads/main")
    git(work, "config", "user.email", "probe@probe.invalid")
    git(work, "config", "user.name", "probe")
    git(work, "remote", "add", "origin", str(bare))
    ledger = work / LEDGER_REL
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("".join(row(n) + "\n" for n in published), encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "seed")
    git(work, "push", "-q", "origin", "main")
    git(work, "fetch", "-q", "origin")
    if worktree_extra:
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write("".join(row(n) + "\n" for n in worktree_extra))
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "unpushed rows")
    return work, bare

# --- arm 1+2: the predicate, two-sided, on a real repository --------------------------

def arm_the_predicate_is_two_sided() -> None:
    pub = load(PUBLISH_TOOL, "_gate_publish")
    with tempfile.TemporaryDirectory() as tmp:
        work, bare = build_repo(Path(tmp), published=[1, 2], worktree_extra=[3])

        state = pub.unpublished_rows(work, [1, 2, 3])
        check(state["unpublished"] == [3],
              "a row in the worktree ledger and absent from the tracking ref is UNPUBLISHED",
              f"unpublished={state['unpublished']} reason={state['reason']!r} ref={state['ref']}")
        check(state["reason"] == "",
              "and the read reports NO reason, so the finding is a verdict and not a failure",
              f"reason={state['reason']!r}")
        check(state["checked"] == 3,
              "the read states how many rows it checked",
              f"checked={state['checked']}")

        control = pub.unpublished_rows(work, [1, 2])
        check(control["unpublished"] == [],
              "CONTROL: rows already at the tracking ref are published",
              f"unpublished={control['unpublished']}")

        # The other side of the SAME row: push it and the verdict flips. Without this the
        # arm is satisfied by a predicate that always answers "unpublished".
        git(work, "push", "-q", "origin", "main")
        git(work, "fetch", "-q", "origin")
        after = pub.unpublished_rows(work, [3])
        check(after["unpublished"] == [],
              "the SAME row is published once its commit reaches the remote",
              f"unpublished={after['unpublished']} — the predicate is not stuck on one side")

def arm_an_unreadable_blob_is_a_reason() -> None:
    pub = load(PUBLISH_TOOL, "_gate_publish2")
    with tempfile.TemporaryDirectory() as tmp:
        work, bare = build_repo(Path(tmp), published=[1], worktree_extra=[])
        # Destroy the tracking ref: the blob can no longer be read at all.
        git(work, "update-ref", "-d", pub.DEFAULT_TRACKING_REF)
        state = pub.unpublished_rows(work, [1])
        check(bool(state["reason"]),
              "an unreadable ledger blob is reported as a REASON",
              f"reason={state['reason']!r}")
        check(state["unpublished"] == [1],
              "and an unreadable blob never folds into a clean empty `unpublished`",
              f"unpublished={state['unpublished']} — 'I could not ask' must not read as "
              f"'everything is reachable'")

# --- arm 3: the citation reader -------------------------------------------------------

def arm_cited_rows_reads_both_shapes() -> None:
    rule = load(RULE_TOOL, "_gate_rule")
    check(rule.cited_rows("Intake row: `n=2906`.") == [2906],
          "a single `n=<N>` is read", f"{rule.cited_rows('Intake row: `n=2906`.')}")
    got = rule.cited_rows("rows n=2900-2905 on the public board")
    check(got == [2900, 2901, 2902, 2903, 2904, 2905],
          "a RANGE expands to every row it names — the shape the 2026-10-08 incident used",
          f"got={got} — expanding only the first endpoint is the silent-partial-citation "
          f"defect this note exists to remove")
    check(rule.cited_rows("n=2901 and n=2901 again") == [2901],
          "a row named twice is counted once", f"{rule.cited_rows('n=2901 and n=2901 again')}")
    check(rule.cited_rows("no row here") == [],
          "a body naming no row yields none", f"{rule.cited_rows('no row here')}")
    check(rule.cited_rows("n=10-99999") == [10],
          "an implausibly wide range is NOT expanded — a typo must not become 99,990 numbers",
          f"{rule.cited_rows('n=10-99999')}")

def arm_the_note_names_the_state() -> None:
    rule = load(RULE_TOOL, "_gate_rule2")
    ref = "refs/remotes/origin/main"
    unpublished = rule.citation_note([2900, 2901],
                                     {"ref": ref, "checked": 2, "unpublished": [2901],
                                      "reason": "", "fetched": True},
                                     "2026-10-08T00:00:00Z")
    check("`n=2901`" in unpublished and "NOT YET READABLE" in unpublished,
          "the note NAMES each unpublished row", unpublished.strip()[:200])
    check(ref in unpublished and "2026-10-08T00:00:00Z" in unpublished,
          "and states the ref it read AND the instant it read it",
          "a verdict without its scope and its instant is not a reading")

    clean = rule.citation_note([1], {"ref": ref, "checked": 1, "unpublished": [],
                                     "reason": "", "fetched": True}, "2026-10-08T00:00:00Z")
    check("readable from the remote" in clean and "NOT YET READABLE" not in clean,
          "a fully-published citation says so", clean.strip()[:200])

    none = rule.citation_note([], {"ref": ref, "checked": 0, "unpublished": [],
                                   "reason": "", "fetched": True}, "2026-10-08T00:00:00Z")
    check("names no ledger row" in none,
          "a ruling naming no row is distinguished from a ruling naming only published ones",
          none.strip()[:200])

    unreadable = rule.citation_note([5], {"ref": ref, "checked": 1, "unpublished": [5],
                                          "reason": "git show exited 128", "fetched": True},
                                    "2026-10-08T00:00:00Z")
    check("could NOT be read" in unreadable and "git show exited 128" in unreadable,
          "an unreadable read is stated as such, with its reason", unreadable.strip()[:200])

    stale = rule.citation_note([1], {"ref": ref, "checked": 1, "unpublished": [],
                                     "reason": "", "fetched": False}, "2026-10-08T00:00:00Z")
    check("fetch FAILED" in stale,
          "a stale cache read says so — a possibly-stale read must not render as a fresh one",
          stale.strip()[:200])

# --- arm 4: the writer is WIRED to the predicate --------------------------------------

def arm_the_writer_resolves_the_state_before_touching_a_surface() -> None:
    src = RULE_TOOL.read_text(encoding="utf-8")
    check("state = read_publication(cited)" in src,
          "tools/rule.py calls the publication predicate",
          "a predicate nothing calls is dead text (P29)")
    check("posted_body = body + citation_note(cited, state, _now_iso())" in src,
          "and the note is composed into the text both surfaces carry",
          "the comment and the row must not diverge — one text, two surfaces")
    check("handle.write(posted_body)" in src and "build_detail(posted_body, comment_id)" in src,
          "BOTH surfaces carry the noted body, not the bare one",
          "a note on the comment alone leaves the row citing unreachable numbers silently")

    resolved = src.find("state = read_publication(cited)")
    posted = src.find("handle.write(posted_body)")
    check(0 <= resolved < posted,
          "the state is resolved BEFORE the board comment is written",
          f"read_publication at {resolved}, comment write at {posted}")

    # The DRY RUN must stay hermetic: a validation step that itself needs the network is a
    # step that can fail for reasons the operator did not ask about.
    dry = src.find("if args.dry_run:")
    check(0 <= dry < resolved,
          "the dry run returns BEFORE the state is resolved — it stays hermetic",
          f"dry-run block at {dry}, read_publication at {resolved}")
    dry_block = src[dry:resolved]
    check("read_publication" not in dry_block,
          "and the dry-run block calls no reader that reaches the network",
          "a `--dry-run` that fetches is not a dry run")

def arm_the_writer_acknowledges_after_stamping() -> None:
    """The one-line acknowledgement `main()` prints once the row is stamped (property 2).

    Probed as a PURE function: it is the shape a lane reads on STDOUT, and it must state
    the stamped row's own unreachability as well as the cited rows' — the stamped row is
    the one a reader reaches by following this tool's output.
    """
    rule = load(RULE_TOOL, "_gate_rule3")
    state = {"ref": "refs/remotes/origin/main", "checked": 1, "unpublished": [],
             "reason": "", "fetched": True}
    line = rule.citation_acknowledgement("2909", [1], state)
    check("n=2909 is NOT YET READABLE" in line,
          "the stamped row's own unreachability is stated first", line)
    check("every cited row is readable" in line,
          "and the cited rows' state is stated beside it", line)

    bad = rule.citation_acknowledgement("2909", [2900, 2901],
                                        {"ref": "refs/remotes/origin/main", "checked": 2,
                                         "unpublished": [2901], "reason": "", "fetched": True})
    check("n=2901" in bad and "NOT readable" in bad,
          "an unreachable CITED row is named in the acknowledgement", bad)

    unknown = rule.citation_acknowledgement("?", [1], state)
    check("could NOT be read" in unknown,
          "an unreadable append output is stated, never silently rendered as a number",
          unknown)

# --- arm 5: the dry run, end to end and offline ---------------------------------------

def arm_the_dry_run_stays_offline_and_counts_the_citations() -> None:
    rule = load(RULE_TOOL, "_gate_rule4")
    patrol = load(REPO / "tools" / "patrol_host_state.py", "_gate_patrol")
    body = f"{patrol.RULING_CANONICAL_HEADING} probe\n\nrows n=2900-2905 were named.\n"
    proc = subprocess.run(
        [sys.executable, str(RULE_TOOL), "--dry-run", "--issue", "1", "--body", body],
        capture_output=True, text=True, cwd=str(REPO), timeout=120,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    check(proc.returncode == 0,
          "the dry run exits 0 without a board, a remote or a network",
          f"rc={proc.returncode} stderr={proc.stderr.strip()[:200]}")
    check("citation state NOT resolved (hermetic)" in proc.stdout,
          "and it STATES that it resolved nothing, rather than implying a clean read",
          proc.stdout.strip()[:300])
    check("6 ledger row(s)" in proc.stdout,
          "and counts the citations the live run would resolve (the range expands)",
          proc.stdout.strip()[:300])

# --- arm 6: mutation controls ---------------------------------------------------------

def _mutated_publish(root: Path, replacement: str) -> Path:
    """A copy of `tools/publish.py` whose `unpublished_rows` body is replaced."""
    src = PUBLISH_TOOL.read_text(encoding="utf-8")
    start = src.index("def unpublished_rows(")
    end = src.index("\ndef publishable(", start)
    mutated = src[:start] + replacement + src[end:]
    path = root / "publish_mutated.py"
    path.write_text(mutated, encoding="utf-8")
    return path

def arm_the_predicate_control_bites() -> None:
    """Neuter the predicate so it always answers "published" — arm 1 must FAIL."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _mutated_publish(root, '''def unpublished_rows(repo, rows, *, ref="refs/remotes/origin/main"):
    return {"ref": ref, "checked": len(list(rows)), "unpublished": [], "reason": ""}
''')
        pub = load(path, "_gate_publish_mut")
        work, bare = build_repo(root / "repo", published=[1, 2], worktree_extra=[3])
        state = pub.unpublished_rows(work, [1, 2, 3])
        check(state["unpublished"] != [3],
              "CONTROL: with the predicate neutered to always say 'published', arm 1's "
              "positive finding DISAPPEARS — so arm 1 is testing the predicate",
              f"a neutered predicate reported unpublished={state['unpublished']}; if this "
              f"had still read [3] the arm would be reading something else")

def arm_the_note_control_bites() -> None:
    """Drop the row listing from the note — arm 3 must FAIL."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = RULE_TOOL.read_text(encoding="utf-8")
        start = src.index("def citation_note(")
        end = src.index("\ndef _now_iso(", start)
        mutated = src[:start] + '''def citation_note(rows, state, instant):
    return "\\n\\n---\\n\\n**Citation state.** (listings removed by the control)\\n"
''' + src[end:]
        path = root / "rule_mutated.py"
        path.write_text(mutated, encoding="utf-8")
        rule = load(path, "_gate_rule_mut")
        note = rule.citation_note([2901], {"ref": "refs/remotes/origin/main", "checked": 1,
                                          "unpublished": [2901], "reason": "", "fetched": True},
                                  "2026-10-08T00:00:00Z")
        check("`n=2901`" not in note,
              "CONTROL: with the listing removed from the note, arm 3's 'the note NAMES the "
              "row' assertion DISAPPEARS — so that arm is testing the note",
              f"a listing-free note read {note.strip()[:120]!r}")

# --- arm 7: the live tree -- a PUBLISHED citation must reach its target ---------------

def _typed_row_refs(entry: dict) -> list[int]:
    """The `row:` refs a ledger row carries, as ints. The OTHER ref kinds (`commit:`,
    `comment:`, `pr:`) name objects with their own lifecycles and are not this gate's."""
    out: list[int] = []
    for ref in (entry.get("refs") or []):
        if isinstance(ref, dict) and "row" in ref:
            try:
                out.append(int(ref["row"]))
            except (TypeError, ValueError):
                continue
    return out

def _unresolved_citations(rows: list[dict]) -> list[tuple[int, int]]:
    present = {r["n"] for r in rows if isinstance(r.get("n"), int)}
    return [(r["n"], target) for r in rows if isinstance(r.get("n"), int)
            for target in _typed_row_refs(r) if target not in present]

def arm_a_published_citation_must_reach_its_target() -> None:
    """The arms above prove the predicate on a repo BUILT to exercise it; this one runs
    the same question over the population this tree actually carries.

    Scoped to the PUBLISHED blob deliberately. A row that is itself unpushed may cite a
    sibling appended in the SAME commit -- that is the ordinary pre-publish state this
    whole mechanism exists to ACKNOWLEDGE, and failing it here would forbid the very
    ordering #441 protects (the citation is not wrong, it is merely not yet readable, and
    the note says so). So: the population is the ledger AT THE TRACKING REF, and the
    predicate is that every typed `row:` ref inside it resolves inside it. What that
    catches is the citation that is public and names a row a reader can never reach -- a
    typo, a foreign ledger's number, or a row a rebase dropped.

    A zero is a verdict only from a working instrument (AGENTS.md rule 7), so the control
    comes FIRST: a repository whose published blob carries exactly that defect, read
    through the production reader, must report it. Without that leg "no unresolved
    citations" and "the reader returned nothing" would render identically.
    """
    publish = load(PUBLISH_TOOL, "probe_publish_live")
    ref = getattr(publish, "DEFAULT_TRACKING_REF", "refs/remotes/origin/main")

    # --- positive control: a published row citing a row that is not there ---
    with tempfile.TemporaryDirectory(prefix="af441-live-") as tmp:
        work, _bare = build_repo(Path(tmp), published=[])
        ledger = work / LEDGER_REL
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            row(1) + "\n"
            + json.dumps({"n": 2, "event": "ruling", "subject": "#1",
                          "detail": "a published citation naming a row nobody can reach",
                          "at": "2026-10-08T00:00:00Z",
                          "refs": [{"row": 3}, {"commit": "0" * 40}]}) + "\n",
            encoding="utf-8")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "a citation into the void")
        git(work, "push", "-q", "origin", "main")
        git(work, "fetch", "-q", "origin")
        control_rows = _rows_from_ref(work, ref)
        check(control_rows is not None,
              "CONTROL: the published blob of the probe repository is readable",
              f"`git show {ref}:{LEDGER_REL}` did not resolve")
        control_findings = _unresolved_citations(control_rows or [])
        check(control_findings == [(2, 3)],
              "CONTROL: the predicate BITES on a published row citing an absent row",
              f"expected [(2, 3)], got {control_findings!r}")
        control_published, _why = publish.ledger_rows_at(work, ref)
        check(control_published == {1, 2},
              "and the production reader agrees on that population",
              f"ledger_rows_at read {control_published!r}")

    # --- the live leg ---
    rows = _rows_from_ref(REPO, ref)
    if rows is None:
        print(f"  skip  published-citation arm: the ledger at {ref} is unreadable here",
              file=sys.stderr)
        return
    published, why = publish.ledger_rows_at(REPO, ref)
    check(published is not None and published == {r["n"] for r in rows},
          "the live population read here is the one the production reader sees",
          f"ledger_rows_at={None if published is None else len(published)} rows "
          f"({why or 'ok'}), this arm={len(rows)}")
    findings = _unresolved_citations(rows)
    cited = sum(1 for r in rows if _typed_row_refs(r))
    check(not findings,
          f"every typed row: ref among the {len(rows)} PUBLISHED rows "
          f"({cited} rows cite at least one) resolves inside them",
          f"{len(findings)} unresolved: {findings[:5]}")

def _rows_from_ref(repo: Path, ref: str) -> list[dict] | None:
    """The parsed ledger blob at `ref`, or None when it is unreadable. Deliberately the
    same `git show <ref>:<path>` the production reader issues -- this arm must not become
    a second, differently-behaved reader of the same blob."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{LEDGER_REL.as_posix()}"],
        capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return None
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            return None
        if isinstance(parsed, dict) and isinstance(parsed.get("n"), int):
            rows.append(parsed)
    return rows

def arm_the_mechanism_is_present_at_all() -> None:
    """The cheapest arm first, so a tree WITHOUT the mechanism fails with a name rather
    than a traceback. A gate that dies on `AttributeError` still exits non-zero, but its
    message sends the next reader to the wrong file — the failure mode #53 clause 8 paid
    for when a fixture's `ModuleNotFoundError` was blamed on a row it was parsing.
    """
    pub_src = PUBLISH_TOOL.read_text(encoding="utf-8")
    rule_src = RULE_TOOL.read_text(encoding="utf-8")
    check("def unpublished_rows(" in pub_src,
          "tools/publish.py declares the publication predicate",
          "without it a citation cannot be checked against the remote at all (#441)")
    check("def ledger_rows_at(" in pub_src,
          "and the blob reader it is built on",
          "`unpublished_rows` must not restate the read it depends on")
    for symbol in ("cited_rows", "citation_note", "read_publication"):
        check(f"def {symbol}(" in rule_src,
              f"tools/rule.py declares {symbol}",
              "the writer must resolve and state the citation, not merely be able to")

def main() -> int:
    if not PUBLISH_TOOL.is_file() or not RULE_TOOL.is_file():
        print("citation-published gate: SKIP — tools/publish.py or tools/rule.py absent",
              file=sys.stderr)
        return 0
    arm_the_mechanism_is_present_at_all()
    if any(not ok for ok, _, _ in checks):
        for ok, name, detail in checks:
            if not ok:
                print(f"  FAIL  {name}\n        {detail}", file=sys.stderr)
        print("\ncitation-published gate: FAILED — the mechanism is absent from this tree",
              file=sys.stderr)
        return 1
    arm_the_predicate_is_two_sided()
    arm_an_unreadable_blob_is_a_reason()
    arm_cited_rows_reads_both_shapes()
    arm_the_note_names_the_state()
    arm_the_writer_resolves_the_state_before_touching_a_surface()
    arm_the_writer_acknowledges_after_stamping()
    arm_the_dry_run_stays_offline_and_counts_the_citations()
    arm_the_predicate_control_bites()
    arm_the_note_control_bites()
    arm_a_published_citation_must_reach_its_target()

    failed = [(name, detail) for ok, name, detail in checks if not ok]
    for ok, name, detail in checks:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
        if not ok and detail:
            print(f"        {detail}")
    print(f"\ncitation-published gate: {len(checks) - len(failed)}/{len(checks)} arms passed")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
