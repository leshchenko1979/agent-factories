"""Gate: a derived runner's kills leave a DURABLE row (#641).

HQ ruling n=5018, three criteria, each with its own arm below: (1) one row per kill,
written AT KILL TIME through the ledger's one writer, so a run that dies later still
leaves the row; (2) the cause is a FIELD from the runner's own no-verdict vocabulary --
countable, never free prose; (3) `tools/gate_budget_rederive.py` is READ-ONLY against
that store, asserted behaviourally (the store's bytes are compared before and after a
read) and structurally (its source carries no writer for the store).

The store is `evidence/subprocesses/gate-select.jsonl`, written ONLY by
`tools/ledger.py append --subprocess` -- the single-writer law owns that surface, so
these probes drive the real writer and never touch the file themselves except to READ
and to compare hashes.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tests"))

from gate_budget import margin_for  # noqa: E402

GATE_SELECT = REPO / "tools" / "gate_select.py"
GATE_BUDGET = REPO / "tools" / "gate_budget.py"
REDERIVE = REPO / "tools" / "gate_budget_rederive.py"

FAILURES: list[str] = []


def check(claim: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} {claim}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(f"{claim} — {detail}")


def _gate_select_module():
    spec = importlib.util.spec_from_file_location("gate_select_641", GATE_SELECT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gate_select_641"] = mod  # dataclass-bearing modules need registration
    spec.loader.exec_module(mod)
    return mod


# ---- fixture: a repo whose audit declares three gates, one of which burns its budget ----

FIXTURE_641_AUDIT = (
    "from __future__ import annotations\n"
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
    "from gate_budget import gate_key_for_cmd  # noqa: E402\n"
    "\n"
    # The runner reads LOCK_HELD_EXIT_CODE out of its own directory's audit (#637's
    # lesson): without it every fixture run dies on the constant, not on the kill.
    "LOCK_HELD_EXIT_CODE = 75\n"
    "\n"
    "gates_to_run = []\n"
    'gates_to_run.append([sys.executable, "tests/fixture_641_a_kill.py"])\n'
    'gates_to_run.append([sys.executable, "tests/fixture_641_b_hang.py"])\n'
    'gates_to_run.append([sys.executable, "tests/fixture_641_c_ok.py"])\n'
    "\n"
    "def registered_gates(repo_root):\n"
    "    return [cmd for cmd in gates_to_run if gate_key_for_cmd(cmd, repo_root)]\n"
)

# The selection runs ALPHABETICALLY, so the a/b/c names are the ORDER CONTROL, the same
# device the #637 fixture uses: the kill gate must burn its budget and have its row
# written BEFORE the hang gate ever starts, or the SIGTERM arrives before any kill and
# the "row survives a killed run" arm measures an empty store instead of a durable one.
FIXTURE_641_GATES = {
    "tests/fixture_641_a_kill.py": "import time; time.sleep(30)\n",
    "tests/fixture_641_b_hang.py": (
        "import os, pathlib, time\n"
        "pathlib.Path(os.environ['OC_641_HANG_MARKER']).write_text(str(os.getpid()))\n"
        "time.sleep(120)\n"
    ),
    "tests/fixture_641_c_ok.py": "raise SystemExit(0)\n",
}

# The kill gate's OWN budget, built through the budget module's own margin law because a
# thin hand-written entry is refused by the reader. margin_for(0.0625) = 4 + 0.75/0.0625
# = 16.0, so the entry declares budget_sec 1.0 from a measured 0.0625 s.
KILL_BUDGET_MEASURED = 0.0625


def _fixture_641(root: Path, *, with_hang: bool) -> None:
    for part in ("tools", "tests", "registry"):
        (root / part).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(GATE_BUDGET, root / "tools" / "gate_budget.py")
    (root / "tools" / "audit.py").write_text(FIXTURE_641_AUDIT, encoding="utf-8")
    for relative, body in FIXTURE_641_GATES.items():
        if relative.endswith("fixture_641_b_hang.py") and not with_hang:
            body = "raise SystemExit(0)\n"
        (root / relative).write_text(body, encoding="utf-8")
    budget = round(margin_for(KILL_BUDGET_MEASURED) * KILL_BUDGET_MEASURED, 4)
    (root / "registry" / "gate_triggers.json").write_text(
        json.dumps(
            {"gates": {gate: ["*.txt"] for gate in FIXTURE_641_GATES},
             "floor": [], "default": "full"}
        ),
        encoding="utf-8",
    )
    (root / "registry" / "gates.json").write_text(
        json.dumps(
            {
                "default": {"budget_sec": budget},
                "gates": {
                    "tests/fixture_641_a_kill.py": {
                        "budget_sec": budget,
                        "measured_sec": KILL_BUDGET_MEASURED,
                        "margin_x": margin_for(KILL_BUDGET_MEASURED),
                        "measured_at": "HEAD",
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _run_641(root: Path, log: Path, hang_marker: Path, *, kill: bool,
             store: Path) -> tuple[int, list[str]]:
    """Run the real CLI over the fixture; SIGTERM it once the hang gate is live."""
    env = dict(os.environ,
               OC_641_HANG_MARKER=str(hang_marker),
               OC_SUBPROCESS_DIR=str(store))
    with log.open("wb") as handle:
        proc = subprocess.Popen(
            [sys.executable, str(GATE_SELECT), "--paths", "x.txt", "--run",
             "--repo-root", str(root)],
            stdout=handle, stderr=subprocess.STDOUT, cwd=str(root), env=env,
        )
        try:
            if kill:
                deadline = time.monotonic() + 60
                while not hang_marker.exists() and time.monotonic() < deadline:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                proc.send_signal(signal.SIGTERM)
            rc = proc.wait(timeout=90)
        finally:
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=10)
    return rc, log.read_text(encoding="utf-8").splitlines()


def _store_rows(store: Path) -> list[dict]:
    raw = (store / "gate-select.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


# ---- criterion 1: one row per kill, AT KILL TIME, surviving even a killed run ----

def probe_a_budget_killed_gate_leaves_a_durable_row() -> None:
    """End to end: the real CLI, a real budget kill, the real ledger writer."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "repo"
        store = base / "store"
        _fixture_641(root, with_hang=False)
        rc, lines = _run_641(root, base / "run.log", base / "unused.marker",
                             kill=False, store=store)
        summary = [line for line in lines if "gate(s) ran" in line]
        rows = _store_rows(store)
        kills = [r for r in rows if r["subject"].endswith("fixture_641_a_kill.py")]

        check("the run COMPLETES with its kill counted, never silently green",
              rc == 124 and summary and "1 no-verdict" in summary[0],
              f"rc={rc} summary={summary}")
        check("the store carries ONE ROW — the retry arm folds both kills into one line",
              len(kills) == 1, f"{len(kills)} row(s): {[r['subject'] for r in rows]}")
        check("every row is a run event by the worker actor, citing the board",
              all(r["event"] == "run" and r["actor"] == "worker" and
                  any(ref.get("board") == "641" for ref in r.get("refs", []))
                  for r in kills), str(kills[:1]))
        check("the detail carries the cause FIELD and the VERBATIM no-verdict line",
              all(r["detail"].startswith("cause=budget; ") and
                  r["detail"].split("; ", 1)[1] in
                  [line.split("NO VERDICT ", 1)[1] for line in lines
                   if "NO VERDICT" in line]
                  for r in kills), str(kills[:1]))


def probe_a_killed_run_still_leaves_its_rows() -> None:
    """The dispatch headline: a run that DIES mid-flight has already written its kills."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "repo"
        store = base / "store"
        _fixture_641(root, with_hang=True)
        hang_marker = base / "hang.marker"
        rc, lines = _run_641(root, base / "run.log", hang_marker, kill=True, store=store)
        rows = _store_rows(store)
        kills = [r for r in rows if r["subject"].endswith("fixture_641_a_kill.py")]

        check("the SIGTERM'd run exits 124 and prints NO completed-run summary",
              rc == 124 and not any("gate(s) ran" in line for line in lines),
              f"rc={rc}")
        check("the budget kill is DURABLE anyway — written at kill time, before the death",
              len(kills) == 1 and all(r["detail"].startswith("cause=budget; ")
                                      for r in kills),
              f"{len(kills)} kill row(s) in {store}")


# ---- fail-open: a store that cannot take the row never turns a kill into a crash ----

def probe_a_store_that_cannot_take_the_row_is_fail_open() -> None:
    """MUTANT for arm 1: same fixture, the store path is a FILE, so every append dies."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "repo"
        broken = base / "not-a-dir"
        broken.write_text("this is a file, not a directory\n", encoding="utf-8")
        _fixture_641(root, with_hang=False)
        rc, lines = _run_641(root, base / "run.log", base / "unused.marker",
                             kill=False, store=broken)
        summary = [line for line in lines if "gate(s) ran" in line]

        check("the run still COMPLETES with the same verdicts — the kill is unaffected",
              rc == 124 and summary and "1 no-verdict" in summary[0],
              f"rc={rc} summary={summary}")
        check("the loss is STATED on stderr, naming the gate — never silent",
              any("could NOT be recorded" in line and "fixture_641_a_kill.py" in line
                  for line in lines), str([line for line in lines if "NOT be recorded"
                                           in line][:2]))


# ---- criterion 1's boundary: refusals and never-ran lines are NOT kills ----

def probe_only_kill_lines_get_rows() -> None:
    """Unit: the recorder classifies what it is given; refusals write nothing."""
    mod = _gate_select_module()
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "store"
        os.environ["OC_SUBPROCESS_DIR"] = str(store)
        try:
            refused = ("tests/fixture_refused.py — REFUSED, the run never started "
                       "(exit 3): another audit run held the repository's run lock")
            never = ("tests/fixture_never.py — NEVER RAN: its own cgroup could "
                     "not be created")
            killed = ("tests/fixture_killed.py — killed at its declared budget "
                      "(1.00s) after running 1.01s; it neither passed nor failed")
            recorded, lost = mod.record_kill_rows([refused, never, killed])
            rows = _store_rows(store) if (store / "gate-select.jsonl").exists() else []
            check("REFUSED and NEVER RAN write NO row — a refusal is not a kill",
                  recorded == 1 and not lost and len(rows) == 1 and
                  rows[0]["subject"].endswith("fixture_killed.py"),
                  f"recorded={recorded} lost={lost} rows={len(rows)}")
            check("the KILLED line's row names the gate and carries its cause field",
                  rows and rows[0]["detail"].startswith(
                      "cause=budget; tests/fixture_killed.py — killed at its declared "
                      "budget"),
                  str(rows[:1]))
        finally:
            os.environ.pop("OC_SUBPROCESS_DIR", None)


def probe_an_impossible_store_costs_the_run_nothing() -> None:
    """FAIL-OPEN by construction: ledger.py itself dies; the recorder absorbs it."""
    mod = _gate_select_module()
    saved = os.environ.get("OC_SUBPROCESS_DIR")
    os.environ["OC_SUBPROCESS_DIR"] = "/proc/no/such/dir"
    try:
        killed = ("tests/fixture_killed.py — killed at its declared budget "
                  "(1.00s) after running 1.01s; it neither passed nor failed")
        recorded, lost = mod.record_kill_rows([killed])
        check("an unwritable store yields zero recorded rows and ONE named loss",
              recorded == 0 and len(lost) == 1 and lost[0][0].endswith("fixture_killed.py"),
              f"recorded={recorded} lost={lost}")
    finally:
        if saved is None:
            os.environ.pop("OC_SUBPROCESS_DIR", None)
        else:
            os.environ["OC_SUBPROCESS_DIR"] = saved


# ---- criterion 2: the cause is a countable FIELD, readable without re-deriving ----

def probe_the_cause_is_a_countable_field() -> None:
    """Read the row back through the rederive reader; the cause is a value, not prose."""
    rederive = _rederive_module()
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "store"
        os.environ["OC_SUBPROCESS_DIR"] = str(store)
        try:
            mod = _gate_select_module()
            killed = ("tests/fixture_killed.py — killed at its declared budget "
                      "(1.00s) after running 1.01s; it neither passed nor failed")
            mod.record_kill_rows([killed, killed])
            kills = rederive.read_derived_kills(store / "gate-select.jsonl")
            counted: dict[str, int] = {}
            for row in kills or ():
                counted[row.cause] = counted.get(row.cause, 0) + 1
            check("the reader returns the rows and the cause counts WITHOUT prose parsing",
                  kills is not None and len(kills) == 2 and counted == {"budget": 2},
                  f"kills={len(kills or ())} counted={counted}")
            check("the cause value is INSIDE the runner's own vocabulary",
                  all(row.cause in ("budget", "refused", "never_ran") for row in kills or ()),
                  str([row.cause for row in kills or ()]))
        finally:
            os.environ.pop("OC_SUBPROCESS_DIR", None)


# ---- criterion 3: the rederive tool is READ-ONLY against the store ----

def _rederive_module():
    spec = importlib.util.spec_from_file_location("rederive_641", REDERIVE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rederive_641"] = mod  # dataclass-bearing modules need registration
    spec.loader.exec_module(mod)
    return mod


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_the_rederive_reader_is_read_only() -> None:
    """Behavioural: the store's bytes are IDENTICAL before and after a read."""
    rederive = _rederive_module()
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "gate-select.jsonl"
        rows = [
            {"n": 1, "ts": "2026-11-14T14:29:08Z", "event": "run", "actor": "worker",
             "subject": "tests/one.py",
             "detail": "cause=budget; NO VERDICT tests/one.py — killed",
             "refs": [{"board": "641"}]},
            "this line is not json",
            {"n": 2, "ts": "2026-11-14T14:30:00Z", "event": "run", "actor": "worker",
             "subject": "tests/two.py", "detail": "no cause field here"},
            ["not", "a", "dict"],
            {"n": 3, "ts": "2026-11-14T14:31:00Z", "event": "run", "actor": "worker",
             "subject": "tests/three.py",
             "detail": "cause=refused; NO VERDICT tests/three.py — REFUSED"},
        ]
        store.write_text(
            "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        before = _sha(store)
        parsed = rederive.read_derived_kills(store)
        after = _sha(store)
        check("the read leaves the store byte-identical",
              before == after, f"before={before[:12]} after={after[:12]}")
        check("well-formed rows parse; junk lines and non-dicts are skipped, not fatal",
              parsed is not None and len(parsed) == 3 and
              [row.key for row in parsed] ==
              ["tests/one.py", "tests/two.py", "tests/three.py"],
              f"parsed={None if parsed is None else len(parsed)}")
        check("the cause is read from the row's own cause= prefix, one value per row — "
              "a row with no field reads UNSTATED, never invented",
              parsed is not None and
              [row.cause for row in parsed] == ["budget", "", "refused"], str(parsed))
        check("an UNREADABLE store is None — an inability, never a clean bill",
              rederive.read_derived_kills(Path(tmp) / "absent.jsonl") is None, "")
        empty = Path(tmp) / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        check("a READ-AND-EMPTY store is an empty tuple — a reading, not an inability",
              rederive.read_derived_kills(empty) == (), "")


def probe_the_rederive_module_carries_no_writer() -> None:
    """Structural: no WRITE CALL in the module ever names the derived-kills store.

    The tool lawfully writes its OWN manifest (the streak store) — the property under
    test is narrower than "no writes": the subprocess ledger must be reachable from READS
    only, so every write call's argument strings are swept for the store's name.
    """
    source = REDERIVE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Attribute) and
             node.func.attr in ("write_text", "write_bytes", "append", "mkdir")) or
            (isinstance(node.func, ast.Name) and node.func.id == "open")
        ):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    if "gate-select" in sub.value or "subprocesses" in sub.value:
                        offenders.append(
                            f"{getattr(node.func, 'attr', 'open')}({sub.value[:60]!r})")
                if isinstance(sub, ast.Name) and sub.id == "DERIVED_KILLS_STORE":
                    offenders.append(
                        f"{getattr(node.func, 'attr', 'open')}(DERIVED_KILLS_STORE)")
    check("no write call in the rederive module ever NAMES the derived-kills store",
          not offenders, f"{len(offenders)} offender(s): {offenders[:3]}")
    check("the store constant is declared exactly once, as a READ source",
          source.count("gate-select.jsonl") == 1 and
          "DERIVED_KILLS_STORE" in source, "")


def probe_the_render_names_all_three_states() -> None:
    """The renderer speaks the three states apart: unread, read-and-empty, rows."""
    source = REDERIVE.read_text(encoding="utf-8")
    unread = "derived-run kills: unstated (the subprocess ledger could not be read)"
    reading = "the subprocess ledger was READ and holds no row"
    streak = "NOT streak rounds and never feed the probe"
    check("an unread ledger is NAMED an inability, never a clean result",
          source.count(unread) == 1 and "INABILITY, not a clean result" in source, "")
    check("a read-and-empty ledger is NAMED a reading, never a clean bill",
          source.count(reading) == 1 and "READING, not a clean bill" in source, "")
    check("rows are printed BESIDE the streak and explicitly never INTO it",
          source.count(streak) == 1, "")


PROBES = (
    probe_a_budget_killed_gate_leaves_a_durable_row,
    probe_a_killed_run_still_leaves_its_rows,
    probe_a_store_that_cannot_take_the_row_is_fail_open,
    probe_only_kill_lines_get_rows,
    probe_an_impossible_store_costs_the_run_nothing,
    probe_the_cause_is_a_countable_field,
    probe_the_rederive_reader_is_read_only,
    probe_the_rederive_module_carries_no_writer,
    probe_the_render_names_all_three_states,
)


def main() -> int:
    print(f"gate-select kill rows (#641): {len(PROBES)} probe(s)")
    for probe in PROBES:
        probe()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s)")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all probes passed")
    return 0


def test_gate_select_kill_rows() -> None:
    for probe in PROBES:
        probe()
    assert not FAILURES, FAILURES


if __name__ == "__main__":
    raise SystemExit(main())
