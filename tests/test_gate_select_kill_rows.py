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

IT IS FACTORY DATA AND DOES NOT SHIP (#644, route A). A kill row records a RUN ON A HOST,
not a property of the tree, so `.gitignore` keeps the whole surface out of the index and
`probe_the_store_does_not_ship_and_cannot_be_readded` gates that. It shipped once and the
tree carried 86 rows naming scripts that exist in no tree against 4 naming real gates --
noise from ad-hoc runs that did not pin `OC_SUBPROCESS_DIR`, which append-only law then
forbids removing. The invariant ("a row that ships in the tree names a gate that exists in
the tree") is held by construction while nothing ships; the rejected alternative gated it
post-hoc against a baseline whose only remedy for a violation is being widened.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
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
             store: Path, unbound: bool = False) -> tuple[int, list[str]]:
    """Run the real CLI over the fixture; SIGTERM it once the hang gate is live.

    `unbound=True` removes `OPENCRABS_SESSION_ID` from the child's environment, which is what a
    CRON-LAUNCHED run looks like: no lane is awake. The actor is declared by the writer
    (`KILL_ROW_ACTOR`), so such a run must still write the primary store — see the arm below.
    """
    env = dict(os.environ,
               OC_641_HANG_MARKER=str(hang_marker),
               OC_SUBPROCESS_DIR=str(store))
    if unbound:
        env.pop("OPENCRABS_SESSION_ID", None)
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
        check("every row is a run event by the DECLARED worker actor, citing the board",
              all(r["event"] == "run" and r["actor"] == _gate_select_module().KILL_ROW_ACTOR
                  and
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


def probe_an_unbound_run_still_writes_the_PRIMARY_store() -> None:
    """#641's test-authority arm: a cron-like run has no session, and still leaves a row.

    The defect this pins, measured by HQ 2026-11-15: the actor was DERIVED from ambient
    `OPENCRABS_SESSION_ID`, so with no session the append was REFUSED, the primary store was
    never created, and every kill fell to the fallback store — "a durable row in the subprocess
    ledger" was therefore true only for session-bound runs, which is not what criterion 1 says.
    HQ's cron-like arm died `FileNotFoundError: .../store/gate-select.jsonl` for exactly that
    reason. The actor is now DECLARED (`KILL_ROW_ACTOR`), so a run nobody is awake for writes
    the primary store like any other, and the fallback goes back to meaning one thing only:
    the lock or the filesystem refused.
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "repo"
        store = base / "store"
        _fixture_641(root, with_hang=False)
        rc, lines = _run_641(root, base / "run.log", base / "unused.marker",
                             kill=False, store=store, unbound=True)
        summary = [line for line in lines if "gate(s) ran" in line]
        primary = store / "gate-select.jsonl"
        rows = _store_rows(store) if primary.exists() else []
        kills = [r for r in rows if r["subject"].endswith("fixture_641_a_kill.py")]
        fallback = store / "gate-select.pending.jsonl"

        check("an UNBOUND run still completes with its kill counted, never silently green",
              rc == 124 and summary and "1 no-verdict" in summary[0],
              f"rc={rc} summary={summary}")
        check("the PRIMARY store exists and carries the row — no session was needed",
              len(kills) == 1 and kills[0]["actor"] == _gate_select_module().KILL_ROW_ACTOR,
              f"primary exists={primary.exists()} rows={[r['subject'] for r in rows]}")
        check("the FALLBACK was never needed — it means a refusal, not an absent lane",
              not fallback.exists(), f"fallback exists: {fallback}")

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


# ---- the RETRY is the fix for the MEASURED defect, so it is probed, not assumed ----

def probe_a_CONTENDED_lock_is_retried_and_the_primary_row_still_lands() -> None:
    """#641's residual: ONE bounded attempt against a contended lock DROPPED the row.

    Measured by HQ on a clean worktree 2026-11-15 17:33-17:54Z: four gates hit no-verdict,
    THREE rows landed and the fourth was dropped, its only trace the run's own stderr
    `timed out after 10.0 seconds` in a /tmp log — the same traceless place this defect's
    kills died before the store existed. The contention is not an edge: peers run their gate
    sets concurrently on this box, so an append queuing behind another lane's IS the normal
    case.

    This probe HOLDS the store's own lock (`.<store>.lock`, the file `ledger.py` flocks) in a
    child process and releases it mid-retry, so the recorder's FIRST attempt genuinely times
    out. The row must still land in the PRIMARY store. If it lands in the fallback, the retry
    is decoration and the measured defect is still open.
    """
    mod = _gate_select_module()
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "store"
        store.mkdir(parents=True, exist_ok=True)
        os.environ["OC_SUBPROCESS_DIR"] = str(store)
        saved_timeouts = mod.KILL_ROW_APPEND_TIMEOUTS
        saved_backoff = mod.KILL_ROW_APPEND_BACKOFF_SEC
        holder = None
        try:
            # Short walls so the probe is fast: the SHAPE is under test, not the production
            # seconds (10/20/30), which are sized for a real peer's append.
            mod.KILL_ROW_APPEND_TIMEOUTS = (0.4, 20.0)
            mod.KILL_ROW_APPEND_BACKOFF_SEC = (0.2,)
            lock_path = store / f".{mod.KILL_ROW_STORE_NAME}.lock"
            holder = subprocess.Popen(
                [sys.executable, "-c", (
                    "import fcntl, sys, time\n"
                    "fh = open(sys.argv[1], 'a')\n"
                    "fcntl.flock(fh, fcntl.LOCK_EX)\n"
                    "print('held', flush=True)\n"
                    "time.sleep(2.0)\n"
                ), str(lock_path)],
                stdout=subprocess.PIPE, text=True,
            )
            assert holder.stdout is not None
            holder.stdout.readline()      # the lock is HELD until the child exits
            killed = ("tests/fixture_contended.py — killed at its declared budget "
                      "(1.00s) after running 1.01s; it neither passed nor failed")
            recorded, lost = mod.record_kill_rows([killed])
            primary = store / "gate-select.jsonl"
            fallback = store / mod.KILL_ROW_FALLBACK_STORE_NAME
            rows = _store_rows(store) if primary.exists() else []
            check("a CONTENDED lock is RETRIED and the kill lands in the PRIMARY store",
                  recorded == 1 and not lost and len(rows) == 1,
                  f"recorded={recorded} lost={lost} primary={primary.exists()} "
                  f"rows={len(rows)}")
            check("the FALLBACK is NOT used — the retry won, so it still means refusal",
                  not fallback.exists(), f"fallback exists: {fallback}")
        finally:
            if holder is not None:
                holder.kill()
                holder.wait(timeout=10)
            mod.KILL_ROW_APPEND_TIMEOUTS = saved_timeouts
            mod.KILL_ROW_APPEND_BACKOFF_SEC = saved_backoff
            os.environ.pop("OC_SUBPROCESS_DIR", None)

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


# ---- #644: the store is FACTORY DATA and nothing about it ships ----

STORE_REL = "evidence/subprocesses/gate-select.jsonl"

def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)

def _rows_of(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]

def _newest_commit_carrying_store() -> tuple[str, list[dict]]:
    """The newest commit whose tree still contains the store, and its rows.

    Walked rather than assumed: once the untracking commit lands, `git show HEAD:<path>`
    fails, and `git log --diff-filter=D` names the commit where the file is ABSENT — so the
    question "which commit still carries it?" is answered by asking each candidate for its
    bytes, never by guessing HEAD~1.
    """
    shas = _git("log", "--all", "--format=%H", "--", STORE_REL).stdout.split()
    for sha in shas:
        show = _git("show", f"{sha}:{STORE_REL}")
        if show.returncode == 0:
            return sha, _rows_of(show.stdout)
    return "", []

def probe_the_store_does_not_ship_and_cannot_be_readded() -> None:
    """#644 route A: the kill-row store is FACTORY DATA, so nothing about it ships.

    THREE CHECKS, each reading a COMMITTED declaration — the git index, the ignore file, and
    git history — never a live mutable surface. That matters here more than usual: the store
    is a file that peers' runs append to WHILE this arm reads it, so any check keyed on its
    row COUNT would be a race. The superset property below is the one that is stable under
    concurrent appends and still catches a deletion.

    (a) The index holds no file under `evidence/subprocesses/` — #644's own criterion A.
    (b) The path is IGNORED, so a future lane's `git add` cannot silently re-track it. THIS
        IS THE DRIFT GUARD: the invariant the issue names — "a row that ships in the tree
        names a gate that exists in the tree" — is held by construction only while nothing
        ships, so the rule that keeps it out is the thing worth gating. Deleting the
        `.gitignore` line reds this arm.
    (c) The pre-cutover rows are PRESERVED rather than deleted to make (a) true: the newest
        commit that still carries the store has rows, and when the file exists on disk it is
        a SUPERSET of them. Stated skip when the file is absent — a fresh clone legitimately
        has no store, because factory data does not ship, and a check that demanded one would
        red every clone for being correct.
    """
    tracked = [line for line in _git("ls-files", "evidence/subprocesses/").stdout.splitlines() if line.strip()]
    check("(a) no file under evidence/subprocesses/ is tracked", not tracked, f"tracked: {tracked}")

    ignored = _git("check-ignore", "-q", STORE_REL)
    check(
        "(b) the store path is git-ignored, so `git add` cannot re-track it",
        ignored.returncode == 0,
        f"git check-ignore rc={ignored.returncode}: the .gitignore rule that keeps the "
        "store out of the tree is gone, and with it the only thing holding #644's invariant",
    )

    sha, committed_rows = _newest_commit_carrying_store()
    check(
        "(c1) history still carries the pre-cutover rows",
        bool(committed_rows),
        f"no commit under --all carries {STORE_REL}: the rows that shipped at 5ff312d7 were "
        "deleted from history instead of being removed from the INDEX, which is not what "
        "route A does",
    )

    on_disk = REPO / STORE_REL
    if not on_disk.is_file():
        print(
            f"STATED SKIP (c2) {STORE_REL} is absent on this host — factory data does not "
            "ship, so a clone has no store and owes no rows; the history half (c1) is the "
            "check that binds here"
        )
        return

    disk_rows = _rows_of(on_disk.read_text(encoding="utf-8"))
    key = lambda r: (r.get("n"), r.get("ts"), r.get("subject"))  # noqa: E731
    missing = {key(r) for r in committed_rows} - {key(r) for r in disk_rows}
    check(
        "(c2) every committed row survives on disk (append-only: nothing deleted to pass)",
        not missing,
        f"{len(missing)} committed row(s) missing from the on-disk store, e.g. "
        f"{sorted(m for m in missing if m[0] is not None)[:3]}",
    )

PROBES = (
    probe_a_budget_killed_gate_leaves_a_durable_row,
    probe_a_killed_run_still_leaves_its_rows,
    probe_an_unbound_run_still_writes_the_PRIMARY_store,
    probe_a_store_that_cannot_take_the_row_is_fail_open,
    probe_a_CONTENDED_lock_is_retried_and_the_primary_row_still_lands,

    probe_only_kill_lines_get_rows,
    probe_an_impossible_store_costs_the_run_nothing,
    probe_the_cause_is_a_countable_field,
    probe_the_rederive_reader_is_read_only,
    probe_the_rederive_module_carries_no_writer,
    probe_the_render_names_all_three_states,

    probe_the_store_does_not_ship_and_cannot_be_readded,
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