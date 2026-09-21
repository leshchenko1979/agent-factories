#!/usr/bin/env python3
r"""Gate: the brain-metrics instrument measures what it says, and gates none of it.

WHAT THIS GATE UPHOLDS. `docs/measurement-procedure.md` §5 declares the brain-metrics
COMPANION readings — the always-injected brain-file line count, and the post-compaction
input-token figure read from the daemon log — as a standing obligation every factory owes
(P29). `tools/brain_metrics.py` is the mechanism that stands behind that clause, and this
file is its gate. A declared reading with no instrument is dead text; an instrument with
no gate is a reading nobody can check.

WHY EVERY PROBE IS A FIXTURE, AND THE LIVE TREE IS NEVER JUDGED. The instrument's live
figures are properties of an INSTANT, not of a revision. Measured over 09-19 → 09-21, leg A
moved +82 lines and leg B +215 lines, and inside a single turn's window leg A moved 419 B
while leg B stood byte-identical — because leg A's files live in no repository, so a
revision stamp pins leg B and pins nothing about leg A. An acceptance criterion pinned to
any of those figures fails a CORRECT instrument, so reproducibility is asserted HERE
against fixture trees (deterministic, offline, no live state) and the live reading is
REPORTED by the instrument instead. This gate therefore reads no database, opens no socket
and shells out to nothing.

THE PROBES, each aimed at the shape it forbids:

  (i)   LINE is the unit, never bytes — a fixture file holding ONE very long line reports
        one line, with its byte count printed BESIDE it. This is the unit confusion the
        factory has already paid for once: a published limit in TOKENS encoded as a
        character cap.
  (ii)  A missing named file is NAMED, never silently dropped — a population that quietly
        shrank would read as a smaller law.
  (iii) THE OTHER DENOMINATOR. `Context at NN percent (>65 percent)` measures effective
        tokens over effective max (window MINUS reserves) and sits beside the summarizer
        line in the same log; counting it as a fraction of the provider window overstates
        the floor.
  (iv)  An empty leg-C window EXITS NONZERO and names itself. A gate that reports a clean
        verdict over a population it never found is the failure this whole file exists for.
  (v)   The COUNT and the FLOOR are DIFFERENT figures. Two fixture logs with the SAME token
        distribution and different counts must render identical mean/median/p90, so a rising
        event count can never be read as a heavier law.
  (vi)  No exit code depends on any measured figure, INCLUDING the oracle comparison: the
        same fixture under a 1-token and a 10 000 000-token window must exit identically
        while its printed shares move, and the delta against the dated snapshot is PRINTED
        rather than judged.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import importlib.util
import io
import re
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
INSTRUMENT_PATH = REPO / "tools" / "brain_metrics.py"

def load_instrument():
    spec = importlib.util.spec_from_file_location("brain_metrics", INSTRUMENT_PATH)
    assert spec and spec.loader, f"cannot load {INSTRUMENT_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

BM = load_instrument()

def check(name: str, condition: bool, detail: str, failures: list) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(f"{name} — {detail}")

def _stamp_ago(minutes: float) -> str:
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def _compaction_line(tokens: int, minutes_ago: float = 5.0) -> str:
    """The ONE line leg C parses, in the shape the daemon emits it."""
    return (
        f"{_stamp_ago(minutes_ago)} INFO run_tool_loop{{session_id=fixture}}: "
        f"Compaction: sending 10 / 10 messages to summarizer ({tokens} / 200000 input "
        f"tokens, reserving 9000 for output)"
    )

def _other_denominator_line() -> str:
    """The trigger line leg C must NEVER parse — a different denominator."""
    return (
        f"{_stamp_ago(4.0)} WARN compaction: Context at 71 percent (>65 percent): "
        f"effective 142000 over effective max 200000"
    )

STAGED = {"homes": 0, "logs": 0, "lines": 0}

def _stage(tmp: Path, tokens: tuple[int, ...] = (10_000, 20_000, 30_000)):
    """A fixture home (leg A) and a fixture log dir (leg C). Returns (home, logs)."""
    home, logs = tmp / "home", tmp / "logs"
    home.mkdir(parents=True)
    logs.mkdir()
    # ONE very long line: 40 000 bytes of text, and a newline. One line, not 40 000 lines.
    (home / "SOUL.md").write_text("x" * 40_000 + "\n", encoding="utf-8")
    (home / "USER.md").write_text("user line\n" * 3, encoding="utf-8")
    (home / "AGENTS.md").write_text("agent line\n" * 5, encoding="utf-8")
    body = "\n".join(_compaction_line(t) for t in tokens) + "\n"
    (logs / "opencrabs.2026-09-21").write_text(body, encoding="utf-8")
    STAGED["homes"] += 1
    STAGED["logs"] += 1
    STAGED["lines"] += 3 + len(tokens)
    return home, logs

def _namespace(
    home: Path, logs: Path, window: int = 200_000, hours: float = 24.0,
    brain_files=("SOUL.md", "USER.md", "AGENTS.md"),
):
    return argparse.Namespace(
        home=str(home), hours=hours, log_dir=str(logs), window=window,
        brain_files=tuple(brain_files),
    )

def _render(home: Path, logs: Path, **kwargs) -> str:
    return BM.render(BM.read(_namespace(home, logs, **kwargs)))

def _run_main(args: list) -> tuple:
    """Drive main() itself — the exit-code surface is what probes (iv) and (vi) are about."""
    buffer = io.StringIO()
    with mock.patch.object(sys, "argv", ["brain_metrics.py", *args]):
        with contextlib.redirect_stdout(buffer):
            rc = BM.main()
    return rc, buffer.getvalue()

def _leg_c_block(text: str) -> str:
    """The leg-C section alone — the oracle block also prints a mean/median/p90."""
    if "--- LEG C" not in text:
        return ""
    head = text.split("--- LEG C", 1)[1]
    for tail in ("--- ORACLE", "BOUNDS."):
        head = head.split(tail, 1)[0]
    return head

def _figure(block: str, label: str):
    match = re.search(rf"{label}\s+(-?\d+)\s+tok", block)
    return int(match.group(1)) if match else None

def _count(block: str):
    """The event count renders as `n=NN event(s)` — never as a token figure."""
    match = re.search(r"n=(\d+)\s+event", block)
    return int(match.group(1)) if match else None

def probe_line_unit(home: Path, failures: list) -> None:
    a = BM.leg_a(str(home), ("SOUL.md",))
    entry = a["files"][0]
    check(
        "(i) a 40 001-byte file holding ONE line reports 1 line",
        entry["lines"] == 1,
        f"lines={entry['lines']} for bytes={entry['bytes']}",
        failures,
    )
    check(
        "(i) its bytes are reported BESIDE the line count, not substituted for it",
        entry["bytes"] == 40_001 and entry["bytes"] != entry["lines"],
        f"lines={entry['lines']} bytes={entry['bytes']}",
        failures,
    )

def probe_missing_file_is_named(home: Path, logs: Path, failures: list) -> None:
    a = BM.leg_a(str(home), ("SOUL.md", "ABSENT.md"))
    check(
        "(ii) a named file that is absent is NAMED, not dropped",
        a["missing"] == ["ABSENT.md"],
        f"missing={a['missing']}",
        failures,
    )
    check(
        "(ii) the total covers only what exists — the absent file is not a silent zero",
        a["lines"] == 1 and len(a["files"]) == 1,
        f"lines={a['lines']} files={len(a['files'])}",
        failures,
    )
    text = _render(home, logs, brain_files=("SOUL.md", "ABSENT.md"))
    check(
        "(ii) the rendering prints it by name",
        "ABSENT.md" in text and "MISSING — named in the population" in text,
        "the absent file does not appear in the rendered population",
        failures,
    )

def probe_other_denominator(logs: Path, failures: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        both = Path(tmp) / "logs"
        both.mkdir()
        body = "\n".join(
            [_compaction_line(t) for t in (10_000, 20_000, 30_000)] + [_other_denominator_line()]
        ) + "\n"
        (both / "opencrabs.2026-09-21").write_text(body, encoding="utf-8")
        STAGED["logs"] += 1
        STAGED["lines"] += 4
        now = datetime.datetime.now(datetime.timezone.utc)
        c = BM.leg_c(str(both), now - datetime.timedelta(hours=24), now)
        check(
            "(iii) the `Context at NN percent` line is NOT parsed by leg C",
            c["samples"] == [10_000, 20_000, 30_000],
            f"samples={c['samples']} (a fourth sample means the other denominator counted)",
            failures,
        )

def probe_empty_population_is_not_clean(tmp: Path, failures: list) -> None:
    home, logs = tmp / "empty" / "home", tmp / "empty" / "logs"
    home.mkdir(parents=True)
    logs.mkdir()
    (home / "SOUL.md").write_text("x\n", encoding="utf-8")
    (logs / "opencrabs.2026-09-21").write_text("nothing to see\n", encoding="utf-8")
    STAGED["homes"] += 1
    STAGED["logs"] += 1
    rc, out = _run_main(["--home", str(home), "--log-dir", str(logs)])
    check(
        "(iv) an empty leg-C window exits NONZERO",
        rc != 0,
        f"rc={rc} — an empty population was reported as a clean verdict",
        failures,
    )
    check(
        "(iv) and the empty population is NAMED in its own words",
        "EMPTY" in out and "not a clean verdict" in out,
        "the run did not name the population it failed to find",
        failures,
    )

def probe_count_is_not_the_floor(tmp: Path, failures: list) -> None:
    home, logs = tmp / "flat" / "home", tmp / "flat" / "logs"
    home.mkdir(parents=True)
    logs.mkdir()
    (home / "SOUL.md").write_text("x\n", encoding="utf-8")
    trio = (10_000, 20_000, 30_000)
    (logs / "opencrabs.2026-09-21").write_text(
        "\n".join(_compaction_line(t) for t in trio) + "\n", encoding="utf-8"
    )
    STAGED["homes"] += 1
    STAGED["logs"] += 1
    STAGED["lines"] += 3 + len(trio)
    many = tmp / "rising" / "logs"
    many.mkdir(parents=True)
    (many / "opencrabs.2026-09-21").write_text(
        "\n".join(_compaction_line(t) for t in trio * 10) + "\n", encoding="utf-8"
    )
    STAGED["logs"] += 1
    STAGED["lines"] += len(trio) * 10
    few_block, many_block = _leg_c_block(_render(home, logs)), _leg_c_block(_render(home, many))
    check(
        "(v) the COUNT is rendered as its own labelled figure",
        _count(few_block) == 3 and _count(many_block) == 30,
        f"n={_count(few_block)} and n={_count(many_block)}",
        failures,
    )
    check(
        "(v) the same distribution under a 10x count renders the SAME floor figures",
        all(
            _figure(few_block, label) == _figure(many_block, label) is not None
            for label in ("mean", "median", "p90")
        ),
        f"few={[_figure(few_block, x) for x in ('mean', 'median', 'p90')]} "
        f"many={[_figure(many_block, x) for x in ('mean', 'median', 'p90')]}",
        failures,
    )
    check(
        "(v) and the caveat that forbids reading the count as the law is carried in the output",
        "never read a rising count" in many_block,
        "the caveat is missing, so a rising count could be read as a heavier law",
        failures,
    )

def probe_no_figure_gates_the_run(home: Path, logs: Path, failures: list) -> None:
    rc_small, out_small = _run_main(
        ["--home", str(home), "--log-dir", str(logs), "--window", "1"]
    )
    rc_big, out_big = _run_main(
        ["--home", str(home), "--log-dir", str(logs), "--window", "10000000"]
    )
    check(
        "(vi) the SAME fixture exits identically under a 1-token and a 10 000 000-token window",
        rc_small == rc_big,
        f"rc={rc_small} vs rc={rc_big} — an exit code followed a measured figure",
        failures,
    )
    check(
        "(vi) while the printed shares DID move with the window",
        out_small != out_big and "% of the window" in out_big,
        "the two runs rendered identically, so the probe proved nothing about the shares",
        failures,
    )
    check(
        "(vi) the oracle comparison is PRINTED, never judged",
        "ORACLE" in out_big and "DELTA" in out_big and "2026-09-19" in out_big,
        "the dated snapshot is not printed beside the live reading",
        failures,
    )

def main() -> int:
    if not INSTRUMENT_PATH.is_file():
        print(f"FAIL: no instrument at {INSTRUMENT_PATH.relative_to(REPO)} — nothing to gate")
        return 1

    failures: list = []
    probes = 0
    print("brain-metrics gate — the instrument measures what it says, and gates none of it")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        home, logs = _stage(tmp)
        for probe in (
            lambda: probe_line_unit(home, failures),
            lambda: probe_missing_file_is_named(home, logs, failures),
            lambda: probe_other_denominator(logs, failures),
            lambda: probe_empty_population_is_not_clean(tmp, failures),
            lambda: probe_count_is_not_the_floor(tmp, failures),
            lambda: probe_no_figure_gates_the_run(home, logs, failures),
        ):
            probe()
            probes += 1

    print(
        f"  population: {probes} probe(s) run over {STAGED['homes']} fixture home(s), "
        f"{STAGED['logs']} fixture log file(s), {STAGED['lines']} fixture line(s) written"
    )
    if probes == 0 or STAGED["homes"] == 0 or STAGED["logs"] == 0:
        print("FAIL  the gate examined nothing — a clean run and an unexamined one differ")
        return 1
    if failures:
        print(f"FAIL  {len(failures)} probe failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"brain-metrics gate passed ({probes} probe(s), 0 failure(s))")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
