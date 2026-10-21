#!/usr/bin/env python3
r"""Gate: a cron envelope that produces a receipt must name a LANDING ROUTE that RESOLVES.

THE DEFECT CLASS THIS CLOSES (board #485; instances #474, #479, #480, #481). A cron envelope
carries *the invocation and the mechanical envelope, never the law* -- so when the envelope
orders a lane to append a receipt row and names no route to LAND it, the woken lane supplies
the route from habit and pushes raw, or invents one pointing at the shared tree. Both were
measured: `#474` and `#479` appended and pushed with no route named at all; `#480` and `#481`
named a route into `/root/agent-factories`, the READ surface whose `tools/publish.py` is the
pre-`#445` copy that writes the LEGACY receipt path -- so the push succeeded, `rc=0`, and the
patrol's `publish-freshness` leg still read the commit `UNGOVERNED PUSH`.

WHY THE OBVIOUS PREDICATE IS NOT ENOUGH. A presence sweep (`push|publish|land|origin/main`,
the #481 census predicate) passes `#480` CLEAN: that envelope names a route. It is a route
whose target does not resolve at `origin/main`, and the difference is invisible to a sweep
that only asks whether a route was mentioned. So this gate carries TWO legs and the second
is the one that bites:

  (a) PRESENT  -- a population row must name the pusher (`tools/publish.py`).
  (b) RESOLVES -- and must not EXECUTE a script out of the shared tree. A shared-tree READ is
      NOT a violation: `factory-publish` fetches the pusher from `origin/main` at run time
      (`git -C /root/agent-factories show origin/main:tools/publish.py`), which is the
      correct shape and is asserted GREEN here.
  (c) BOUND    -- and a RUN of a FETCHED copy must pass `--repo` (#525). Leg (a) cannot see
      this: `git show origin/main:tools/publish.py > /tmp/p.py && python3 /tmp/p.py --apply`
      NAMES the pusher inside the fetch and executes nothing, while the run it does perform is
      unrunnable -- the copy derives its repo root from its own `__file__`, resolves `/`, and
      stops at startup with `unbound-repo`. The asymmetry that let it through: the fetch is
      MASKED for leg (b) and was not accounted for in leg (a) at all.

POPULATION. Rows whose prompt declares `receipt_subject:` with a value other than `none`.
A row that declares no receipt produces nothing to land, so it is EXCUSED and PRINTED rather
than silently skipped -- `factory-publish` is the standing example (it IS the pusher).

PURITY (#68). The predicate is PURE over a LIST of rows and reads no live `cron_jobs` table:
cron state lives in the harness database, so a gate reading that table would RED in every
bootstrapped factory that has no such table. `test_probe_is_offline` parses this file's own
AST and forbids the imports that would let it read live state.

THE LIVE LEG'S TWO SURFACES. `registry/state.json` carries the envelopes; the violations
standing on the day this gate landed are DECLARED in `docs/landing-route-debt.json` with
their measurements, so the live leg asserts the violation set EQUALS the declared set -- an
undeclared new instance REDs, and a declared instance that has been repaired REDs as a stale
declaration. Without that pairing a gate over live data can only report, and a report is read
by nothing.

WHAT THIS DOES NOT CLAIM. The live leg reads the tree it is in; a bootstrapped factory has no
`registry/state.json` and no debt file, so both arms SKIP with the artifact NAMED (#199) while
the fixture arms still run. The predicate reads the invocation as a LOGICAL LINE (backslash
continuations joined), so a route split across a shell heredoc is not seen; the population is
`receipt_subject:`-bearing rows, so an envelope that lands work without declaring a receipt
subject is out of scope by construction, not by oversight.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_REL = Path("registry/state.json")
DEBT_REL = Path("docs/landing-route-debt.json")
TEMPLATE_GATE_REL = Path("TEMPLATE/tests/test_cron_landing_route.py")
GATE_NAME = "tests/test_cron_landing_route.py"

SHARED_TREE = "/root/agent-factories"

# The #481 census predicate, kept VERBATIM as the corpus's own presence sweep so a fixture's
# recorded hit count is reproducible here. It is NOT the gate's verdict -- leg (a) is the
# narrower `names_pusher`, and the sweep is carried to show that the stale shape passes it.
CENSUS_RE = re.compile(r"push|publish|land|origin/main", re.IGNORECASE)

RECEIPT_SUBJECT_RE = re.compile(r"receipt_subject:\s*(\S+)")
PUSHER_RE = re.compile(r"\btools/publish\.py\b")

# A read of a file AT a revision: `git -C <shared> show origin/main:<path>`. Masked out BEFORE
# the shared-tree sweep, because fetching a tool from origin/main is the CORRECT landing shape
# (`factory-publish`) and a predicate that cannot tell it from an execution would red it.
ORIGIN_MAIN_READ_RE = re.compile(r"origin/main:[^\s\"'\\|;&)]+")

# An absolute path to a script under the shared tree, executed.
SHARED_ABS_SCRIPT_RE = re.compile(rf"{re.escape(SHARED_TREE)}/[\w./-]+\.(?:py|sh)\b")

# `cd /root/agent-factories` -- the shared tree entered as a WORKING directory.
CD_SHARED_RE = re.compile(rf"\bcd\s+[\"']?{re.escape(SHARED_TREE)}\b")

# A repo-relative script token, the shape that becomes an execution once the working
# directory is the shared tree.
SCRIPT_TOKEN_RE = re.compile(r"[\w./-]+\.(?:py|sh)\b")

# --- the FETCH/RUN split (#525) ------------------------------------------------------
# Leg (a) answers "does the envelope NAME the pusher", and `git show origin/main:tools/publish.py`
# answers YES while RUNNING NOTHING. That is not a corner case: the mandated landing route FETCHES
# the pusher to a copy outside the tree and runs the COPY, and the copy derives its repo from its
# own `__file__`, so a copy at `/tmp/p.py` resolves `/` and dies unless the invocation passes
# `--repo`. Measured on the live envelopes: `git -C /root/agent-factories show
# origin/main:tools/publish.py > /tmp/p.py && python3 /tmp/p.py --apply` names the pusher, is
# unrunnable, and read CLEAN.
PUSHER_FETCH_RE = re.compile(r"origin/main:tools/publish\.py\s*>\s*([^\s;&|]+\.py)")
PY_INVOKE_RE = re.compile(r"\bpython3?\s+([^\s;&|]+\.py)\b")


def text(value: object) -> str:
    """Coerce a row field to str. A row is data read off a disk, so any field may be absent."""
    return value if isinstance(value, str) else ""


def receipt_subject(prompt: str) -> str | None:
    """The declared receipt subject, or None when the envelope declares none at all."""
    match = RECEIPT_SUBJECT_RE.search(prompt)
    return match.group(1) if match else None


def in_population(prompt: str) -> bool:
    """A row is judged when it declares a receipt subject other than `none`."""
    subject = receipt_subject(prompt)
    return subject is not None and subject.lower() != "none"


def logical_lines(prompt: str) -> list[str]:
    """Shell LOGICAL lines: a backslash continuation joins the next physical line.

    A route is an INVOCATION, and an invocation split across a continuation is one line to
    the shell. Reading physical lines would let a route hide behind a trailing backslash.
    """
    out: list[str] = []
    buf = ""
    for raw in prompt.splitlines():
        buf = f"{buf} {raw}".strip() if buf else raw
        if buf.rstrip().endswith("\\"):
            buf = buf.rstrip()[:-1]
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def mask_origin_main_reads(line: str) -> str:
    """Replace `origin/main:<path>` reads so a shared-tree FETCH is not read as an execution."""
    return ORIGIN_MAIN_READ_RE.sub("<origin-main-read>", line)


def stale_sites(prompt: str) -> list[str]:
    """Executions of a script out of the SHARED tree, each named with its site.

    Two shapes, both measured on real envelopes: an absolute `/root/agent-factories/...py`
    invoked directly, and a `cd /root/agent-factories` whose command is a repo-relative
    script -- the `#480` shape, where the relative path becomes an execution because the
    working directory IS the shared tree.
    """
    sites: list[str] = []
    for raw in logical_lines(prompt):
        line = mask_origin_main_reads(raw)
        for match in SHARED_ABS_SCRIPT_RE.finditer(line):
            sites.append(match.group(0))
        cd = CD_SHARED_RE.search(line)
        if cd:
            for match in SCRIPT_TOKEN_RE.finditer(line[cd.end():]):
                sites.append(f"cd {SHARED_TREE} && {match.group(0)}")
    return sites


def names_pusher(prompt: str) -> bool:
    """Leg (a): the envelope names the pusher -- the tool that lands a commit and receipts it."""
    return bool(PUSHER_RE.search(prompt))


def census_hits(prompt: str) -> int:
    """The #481 census predicate's own count, carried for fixture reproducibility."""
    return len(CENSUS_RE.findall(prompt))

def fetched_pusher_copies(prompt: str) -> set[str]:
    """Every path the envelope FETCHES the pusher TO -- `origin/main:tools/publish.py > X`.

    Read from the RAW logical line, never the masked one: masking exists to hide the READ from
    the shared-tree sweep, and the destination is exactly what this leg needs to see.
    """
    out: set[str] = set()
    for line in logical_lines(prompt):
        for match in PUSHER_FETCH_RE.finditer(line):
            out.add(match.group(1))
    return out

def _invocation_segment(line: str, start: int) -> str:
    """The COMMAND part of a logical line, from `start` to the first shell separator or sentence end.

    Needed because these envelopes carry prose on the SAME logical line as the command -- the live
    `factory-triage-patrol` row reads `... --timeout 1400. --repo is REQUIRED: the fetched copy
    lives in /tmp ...`. A tail scan that ran to the end of the line would find the WORD `--repo`
    in that explanation and vouch for a run that never passed it, which is the same class of
    proxy this gate exists to refuse. So the search stops at `;`, `&&`, `||`, `|` or `. `.
    """
    tail = line[start:]
    return re.split(r"(?:;|&&|\|\||\. )", tail)[0]

def _carries_repo_flag(segment: str) -> bool:
    """True when `--repo` is passed WITH A VALUE in this command segment."""
    return bool(re.search(r"--repo\s+(?!-)\S+", segment))

def unbound_pusher_runs(prompt: str) -> list[str]:
    """Runs of a FETCHED copy of the pusher that pass no `--repo`.

    A fetched copy lives outside the tree, so its `__file__`-derived repo root is the directory
    it was written to -- `/tmp` -- and `#525` made that a startup refusal naming `--repo`. An
    envelope that runs the copy WITHOUT the flag is therefore unrunnable, and it used to read
    clean because leg (a) only asked whether the pusher was mentioned anywhere.

    `--repo` is looked for in the INVOCATION SEGMENT -- the script token to the next shell
    separator or sentence end -- and it must carry a value, so neither a neighbouring sentence
    nor a bare `--repo` can vouch for the run.
    """
    copies = fetched_pusher_copies(prompt)
    if not copies:
        return []
    sites: list[str] = []
    for line in logical_lines(prompt):
        for match in PY_INVOKE_RE.finditer(line):
            target = match.group(1)
            if target in copies and not _carries_repo_flag(
                _invocation_segment(line, match.end())
            ):
                sites.append(target)
    return sites


def row_finding(row: dict) -> dict:
    """Judge ONE row. Pure: no disk, no clock, no environment."""
    name = text(row.get("name")) or "<unnamed>"
    prompt = text(row.get("prompt"))
    subject = receipt_subject(prompt)
    judged = in_population(prompt)
    stale = stale_sites(prompt)
    pusher = names_pusher(prompt)
    unbound = unbound_pusher_runs(prompt)
    problems: list[str] = []
    if stale:
        problems.append(
            f"{name}: route TARGET is the shared tree ({SHARED_TREE}), which is the READ "
            f"surface and whose pusher writes the legacy receipt -- the push lands and the "
            f"patrol still reads it UNGOVERNED PUSH. Sites: {'; '.join(stale)}"
        )
    if unbound:
        problems.append(
            f"{name}: route UNBOUND -- the envelope fetches the pusher to a copy OUTSIDE the "
            f"tree and runs it without `--repo`, so the copy derives its repo root from its own "
            f"location and refuses at startup (#525). Sites: {'; '.join(unbound)}"
        )
    if judged and not pusher:
        problems.append(
            f"{name}: route ABSENT -- declares `receipt_subject: {subject}` so it produces a "
            f"receipt row, and names no landing route ({census_hits(prompt)} census hit(s) "
            f"over {len(prompt)} chars, no `tools/publish.py`)"
        )
    return {
        "name": name,
        "subject": subject,
        "judged": judged,
        "hits": census_hits(prompt),
        "chars": len(prompt),
        "pusher": pusher,
        "stale": stale,
        "unbound": unbound,
        "problems": problems,
        "shape": (
            "route-stale" if stale
            else "route-unbound" if unbound
            else ("route-absent" if judged and not pusher else None)
        ),
    }


def landing_route_problems(rows: list[dict], declared: list[dict] | None = None) -> tuple[list[str], dict]:
    """Judge every row, then reconcile the live violations against the DECLARED ones.

    The reconciliation is what makes a live gate more than a report: an undeclared violation
    is a new instance of the class, and a declared one that no longer reproduces is a stale
    declaration that would otherwise mask a future regression at the same job.

    A violation that MATCHES its declaration is standing debt: it is PRINTED in the report and
    raises NO problem. A gate that cannot read green while its debt is declared is a gate
    nobody can run, so suppression is the whole point of declaring the debt -- while the row's
    own finding stays in `report`, so the debt is visible rather than hidden.
    """
    findings = [row_finding(row) for row in rows]
    problems: list[str] = []
    population = [f for f in findings if f["judged"]]
    excused = [
        f"{f['name']}: receipt_subject={f['subject']} -- produces nothing to land, excused"
        for f in findings
        if not f["judged"]
    ]
    by_name = {f["name"]: f for f in findings}
    violations = {f["name"]: f["shape"] for f in findings if f["shape"]}

    if declared is None:
        for finding in findings:
            problems.extend(finding["problems"])
    else:
        declared_shapes = {}
        for entry in declared:
            job = text(entry.get("job"))
            shape = text(entry.get("shape"))
            if not job or shape not in {"route-absent", "route-stale", "route-unbound"}:
                problems.append(
                    f"debt entry {job or '<unnamed>'!r}: shape must be route-absent, "
                    f"route-stale or route-unbound, read {shape!r}"
                )
                continue
            declared_shapes[job] = shape
        for job, shape in sorted(violations.items()):
            if job not in declared_shapes:
                problems.extend(by_name[job]["problems"])
                problems.append(
                    f"{job}: violation ({shape}) is NOT declared in {DEBT_REL} -- a new "
                    f"instance of the landing-route class; declare it with its measurement or "
                    f"repair the envelope"
                )
            elif declared_shapes[job] != shape:
                problems.extend(by_name[job]["problems"])
                problems.append(
                    f"{job}: declared {declared_shapes[job]} but reads {shape} -- the "
                    f"declaration is stale"
                )
        for job in sorted(set(declared_shapes) - set(violations)):
            problems.append(
                f"{job}: declared {declared_shapes[job]} in {DEBT_REL} but no longer "
                f"reproduces -- drop the declaration so a future regression at this job REDs"
            )

    report = {
        "rows": len(findings),
        "population": len(population),
        "judged": [f["name"] for f in population],
        "absent": [f["name"] for f in findings if f["shape"] == "route-absent"],
        "stale": [f["name"] for f in findings if f["shape"] == "route-stale"],
        "unbound": [f["name"] for f in findings if f["shape"] == "route-unbound"],
        "excused": excused,
        "declared": sorted(text(e.get("job")) for e in (declared or [])),
    }
    return problems, report


def read_rows(path: Path) -> list[dict]:
    """The envelope rows out of a state snapshot. Absent or malformed -> [] (the caller skips)."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return [job for job in jobs if isinstance(job, dict)] if isinstance(jobs, list) else []


def read_declared(path: Path) -> list[dict] | None:
    """The declared violations. None when the surface is absent (a bootstrapped factory)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    declared = data.get("declared") if isinstance(data, dict) else None
    return declared if isinstance(declared, list) else []

# --- fixtures -----------------------------------------------------------------------

# The recorded instance shapes. Each fixture carries the envelope's OWN shape as measured in
# `evidence/rework.md` (rows for #474/#479/#480/#481); the docstrings name the measurement so
# a reader can check the fixture against the record rather than against this file's opinion.
def _row(name: str, prompt: str) -> dict:
    return {"name": name, "prompt": prompt}


def _route_absent_474() -> dict:
    """#474's shape: `factory-registry-attest` named its read source, its notify route and its
    receipt, and withheld the landing route. Recorded: a sweep for push|publish|land|origin/main
    over all 48 lines returned ZERO."""
    lines = [
        "Duty 2 (registry attest) -- run the attestation, then report it.",
        "  python3 tools/registry_attest.py --check",
        "Report the result to the HQ lane with the daemon session_notify tool.",
        "Then append your receipt row:",
        "  python3 tools/ledger.py append --event run --subject '#...' --detail '...'",
    ]
    lines += [
        f"# envelope note {i}: the round's work, its sections and its notes are recorded here."
        for i in range(43)
    ]
    body = "\n".join(lines)
    assert len(lines) == 48, len(lines)
    return _row("factory-registry-attest", body + "\nreceipt_subject: registry-attest\n")


def _route_absent_479() -> dict:
    """#479's shape: `factory-measurement-daily`, a 2583-char prompt whose sweep returned ZERO,
    while the #474-repaired attest envelope returned 14 in the same call -- so the zero was a
    real absence, not a blind instrument."""
    body = (
        "Duty: run the daily measurement and record it.\n"
        "  python3 tools/audit.py --json > /tmp/audit.json\n"
        "  python3 tools/measure.py --out evidence/scores/\n"
        "Report the score to the Surveys topic with session_notify.\n"
        "Then append your receipt row with tools/ledger.py.\n"
    )
    suffix = "\nreceipt_subject: measurement-daily\n"
    filler = "# envelope detail: the score, its sections and the round's notes are recorded.\n"
    while len(body) < 2583:
        body += filler
    return _row("factory-measurement-daily", body[: 2583 - len(suffix)] + suffix)


def _route_stale_480() -> dict:
    """#480's shape: the envelope NAMED a route -- `cd /root/agent-factories && python3
    tools/publish.py --apply`, recorded at TWO sites -- and the shared tree's pusher is the
    pre-#445 copy that writes the LEGACY receipt, so the push landed and the patrol still read
    it UNGOVERNED PUSH. This is the shape a presence-only sweep passes."""
    body = (
        "Duty: run the daily measurement and land the result.\n"
        "  cd /root/agent-factories && python3 tools/publish.py --apply\n"
        "# If the first attempt fails, retry the same invocation:\n"
        "  cd /root/agent-factories && python3 tools/publish.py --apply\n"
    )
    return _row("factory-measurement-daily", body + "receipt_subject: measurement-daily\n")


def _route_stale_481() -> dict:
    """#481's shape: `factory-registry-attest` carried the #480 shape at line 38 (a route naming
    the shared tree), and `factory-insights-weekly` invoked a stale ABSOLUTE
    `/root/agent-factories/tools/synthesize_insights.py`."""
    body = (
        "Duty: attest the registry, then land the receipt.\n"
        "  cd /root/agent-factories && python3 tools/publish.py --apply --wait\n"
        "Refresh the insights first:\n"
        "  python3 /root/agent-factories/tools/synthesize_insights.py --out /tmp/insights.json\n"
    )
    return _row("factory-registry-attest", body + "receipt_subject: registry-attest\n")


def _repaired(name: str, subject: str) -> dict:
    """The post-#481 shape: the route is the pusher, from the lane's OWN worktree."""
    return _row(
        name,
        "Duty: do the round's work, then LAND your receipt row through the pusher, from YOUR "
        "OWN worktree:\n  python3 tools/publish.py --apply --wait\n"
        f"receipt_subject: {subject}\n",
    )


def _publish_row() -> dict:
    """`factory-publish`'s shape: it fetches the pusher FROM origin/main at run time and
    declares no receipt of its own. Asserted GREEN."""
    return _row(
        "factory-publish",
        "Fetch the pusher at run time -- never the shared tree's working copy:\n"
        "  git -C /root/agent-factories fetch origin main -q && \\\n"
        "  git -C /root/agent-factories show origin/main:tools/publish.py > /tmp/p.py && \\\n"
        "  python3 /tmp/p.py --repo /root/agent-factories --apply\n"
        "receipt_subject: none\n",
    )


def _judged_fetch_row() -> dict:
    """The SAME fetch shape on a row that DOES declare a receipt: the origin/main read is a
    lawful route, so the row must be CLEAN rather than excused."""
    prompt = _publish_row()["prompt"].replace("receipt_subject: none", "receipt_subject: patrol-verify")
    return _row("factory-triage-patrol", prompt)

def _fetch_then_run(repo_flag: bool) -> dict:
    """The MANDATED landing route, with and without `--repo` (#525).

    Both halves name the pusher -- the first inside the `git show` FETCH -- so leg (a) passes
    BOTH. The difference is whether the RUN of the fetched copy can find a repository at all,
    and before #525 the gate could not see it. Measured on the live envelopes 2026-10-20/21.
    """
    tail = " --repo /root/agent-factories --apply" if repo_flag else " --apply"
    prompt = (
        "Duty: do the round's work, then LAND the receipt.\n"
        "  git -C /root/agent-factories show origin/main:tools/publish.py > /tmp/p.py && \\\n"
        f"  python3 /tmp/p.py{tail}\n"
        "receipt_subject: patrol-verify\n"
    )
    return _row("factory-triage-patrol", prompt)


def test_the_474_shape_is_RED_route_ABSENT() -> None:
    """THE FIRST INSTANCE. A populated envelope that names everything but the landing route."""
    finding = row_finding(_route_absent_474())
    assert finding["hits"] == 0, finding
    assert finding["judged"], finding
    assert finding["shape"] == "route-absent", finding
    assert len(finding["problems"]) == 1, finding["problems"]
    assert "route ABSENT" in finding["problems"][0], finding["problems"]


def test_the_479_shape_is_RED_route_ABSENT_with_a_zero_that_is_not_blind() -> None:
    """THE SECOND INSTANCE, and the positive control for its own zero.

    The recorded evidence is a ZERO against a 14 -- the same sweep, same call, over the
    #474-repaired attest envelope. Both halves are asserted here, so the zero is a real
    absence rather than a predicate that cannot see the class.
    """
    absent = _route_absent_479()
    repaired = _repaired("factory-registry-attest", "registry-attest")
    assert len(absent["prompt"]) == 2583, len(absent["prompt"])
    assert census_hits(absent["prompt"]) == 0, census_hits(absent["prompt"])
    assert census_hits(repaired["prompt"]) > 0, "the control must register the class"
    assert row_finding(absent)["shape"] == "route-absent", row_finding(absent)


def test_the_480_shape_is_RED_route_STALE_and_a_PRESENCE_SWEEP_PASSES_it() -> None:
    """THE DISCRIMINATING PROBE. This is the whole reason the gate has two legs.

    The envelope NAMES a landing route -- so a presence sweep (`push|publish|land|origin/main`)
    reads it clean, which is exactly how the class survived #474's repair -- and the route's
    TARGET is the shared tree, whose pusher writes the receipt the patrol does not read.
    """
    row = _route_stale_480()
    finding = row_finding(row)
    assert census_hits(row["prompt"]) > 0, "the presence sweep must PASS this envelope"
    assert names_pusher(row["prompt"]), "it even names the pusher -- presence alone cannot see it"
    assert finding["shape"] == "route-stale", finding
    assert len(finding["stale"]) == 2, finding["stale"]
    assert "route TARGET is the shared tree" in finding["problems"][0], finding["problems"]


def test_the_481_shape_is_RED_route_STALE_on_two_different_sites() -> None:
    """THE FOURTH INSTANCE: a shared-tree `cd` AND a stale absolute script in one envelope."""
    finding = row_finding(_route_stale_481())
    assert finding["shape"] == "route-stale", finding
    assert len(finding["stale"]) == 2, finding["stale"]
    assert any("synthesize_insights.py" in site for site in finding["stale"]), finding["stale"]
    assert any(site.startswith("cd ") for site in finding["stale"]), finding["stale"]


def test_the_POST_FIX_state_of_all_four_is_GREEN() -> None:
    """THE CONTROL: every instance repaired reads clean, so the REDs above are the predicate's
    findings and not its default answer."""
    rows = [
        _repaired("factory-registry-attest", "registry-attest"),
        _repaired("factory-measurement-daily", "measurement-daily"),
        _repaired("factory-insights-weekly", "insights"),
        _repaired("factory-questions-redeliver", "questions-redeliver"),
    ]
    problems, report = landing_route_problems(rows)
    assert problems == [], problems
    assert report["population"] == 4, report
    assert report["absent"] == [] and report["stale"] == [], report


def test_factory_publish_is_GREEN_and_EXCUSED() -> None:
    """The pusher itself: it declares `receipt_subject: none`, so it produces nothing to land."""
    problems, report = landing_route_problems([_publish_row()])
    assert problems == [], problems
    assert report["population"] == 0, report
    assert len(report["excused"]) == 1 and "factory-publish" in report["excused"][0], report


def test_an_origin_main_FETCH_is_a_LAWFUL_route_on_a_JUDGED_row() -> None:
    """THE MASKING CONTROL. `git -C /root/agent-factories show origin/main:<path>` is a READ of
    a file AT a revision -- the correct landing shape -- so it must not read as an execution.
    The row IS judged, so an excusal cannot be what keeps it clean."""
    finding = row_finding(_judged_fetch_row())
    assert finding["judged"], finding
    assert finding["stale"] == [], finding["stale"]
    assert finding["pusher"], "the fetch names the pusher"
    assert finding["problems"] == [], finding["problems"]


# --- the FETCH/RUN split (#525) -------------------------------------------------------

def test_a_fetched_copy_run_WITHOUT_repo_is_RED() -> None:
    """THE BLIND SPOT (#525, ruling n=3895). The envelope FETCHES the pusher and runs the copy
    with no `--repo`. Leg (a) passes it -- the pusher IS named, inside the `git show` -- while
    the invocation is unrunnable: the copy derives `/` from its own `__file__` and the round
    stops at startup. Measured on the live envelopes 2026-10-20/21."""
    row = _fetch_then_run(repo_flag=False)
    finding = row_finding(row)
    assert names_pusher(row["prompt"]), "leg (a) MUST pass this -- that is the defect"
    assert finding["judged"], finding
    assert finding["stale"] == [], finding["stale"]
    assert finding["shape"] == "route-unbound", finding
    assert finding["unbound"] == ["/tmp/p.py"], finding["unbound"]
    assert "route UNBOUND" in finding["problems"][0], finding["problems"]

def test_the_SAME_envelope_WITH_repo_is_GREEN() -> None:
    """The discriminating half: one flag apart, so the RED above is the flag and not the shape."""
    row = _fetch_then_run(repo_flag=True)
    finding = row_finding(row)
    assert finding["unbound"] == [], finding["unbound"]
    assert finding["problems"] == [], finding["problems"]
    assert finding["shape"] is None, finding

def test_a_no_pusher_envelope_STILL_finds_the_absent_route() -> None:
    """THE POSITIVE CONTROL for the arm above: a fix that reds everything cannot pass this.
    The population must still catch the class it was built for -- an envelope that names no
    landing route at all."""
    finding = row_finding(_route_absent_474())
    assert finding["shape"] == "route-absent", finding
    assert finding["unbound"] == [], finding["unbound"]
    assert "route ABSENT" in finding["problems"][0], finding["problems"]

def test_the_UNBOUND_leg_bites_by_MUTATION() -> None:
    """The mutation control: neuter the new leg and the BAD envelope must go GREEN.

    A leg asserted only against a fixture that it happens to red proves the fixture, not the
    leg. Here the predicate itself is replaced with an always-empty answer and the same BAD
    envelope is re-judged -- if it still reads `route-unbound`, something other than this leg
    is producing the finding.
    """
    original = globals()["unbound_pusher_runs"]
    try:
        globals()["unbound_pusher_runs"] = lambda prompt: []
        neutered = row_finding(_fetch_then_run(repo_flag=False))
    finally:
        globals()["unbound_pusher_runs"] = original
    assert neutered["shape"] is None, neutered
    assert neutered["problems"] == [], neutered["problems"]
    assert row_finding(_fetch_then_run(repo_flag=False))["shape"] == "route-unbound"

# --- the debt reconciliation ----------------------------------------------------------

def test_an_UNDECLARED_violation_REDs() -> None:
    """A live gate over live data is a REPORT unless the standing violations are declared.
    An undeclared instance is the finding."""
    problems, report = landing_route_problems([_route_absent_479()], declared=[])
    assert report["absent"] == ["factory-measurement-daily"], report
    assert any("NOT declared" in p for p in problems), problems


def test_a_declared_violation_that_STOPPED_reproducing_REDs() -> None:
    """The other direction: a declaration left standing after the envelope is repaired would
    mask the NEXT regression at that job."""
    declared = [{"job": "factory-measurement-daily", "shape": "route-absent", "measured": "x"}]
    problems, _ = landing_route_problems(
        [_repaired("factory-measurement-daily", "measurement-daily")], declared=declared
    )
    assert any("no longer" in p for p in problems), problems


def test_a_MATCHING_declaration_is_CLEAN_and_PRINTS_its_population() -> None:
    """The declared pair reads clean, and the report names what it examined -- so a clean
    verdict is distinguishable from an empty read."""
    declared = [{"job": "factory-measurement-daily", "shape": "route-absent", "measured": "x"}]
    problems, report = landing_route_problems(
        [_route_absent_479(), _publish_row()], declared=declared
    )
    assert problems == [], problems
    assert report["declared"] == ["factory-measurement-daily"], report
    assert report["population"] == 1 and report["judged"] == ["factory-measurement-daily"], report
    assert len(report["excused"]) == 1, report


def test_a_MALFORMED_debt_entry_REDs() -> None:
    """A debt surface whose shape vocabulary drifts is a surface nobody can read."""
    declared = [{"job": "factory-x", "shape": "maybe"}]
    problems, _ = landing_route_problems([_repaired("factory-x", "x")], declared=declared)
    assert any("shape must be" in p for p in problems), problems


# --- the live leg, the registration, and the twin -------------------------------------

# STATED SKIP: registry/state.json (a generated SNAPSHOT, factory data)
def test_the_LIVE_envelopes_carry_no_UNDECLARED_violation() -> None:
    """Corroboration against the versioned snapshot this gate reads.

    `registry/state.json` is a generated SNAPSHOT, so a bootstrapped factory may have none.
    Stated as a SKIP with the artifact NAMED rather than a FileNotFoundError (#199): the
    predicate itself is proven by the fixtures above, and this arm is the live read.
    """
    rows = read_rows(REPO_ROOT / STATE_REL)
    if not rows:
        print(
            f"  SKIP  no {STATE_REL} in this tree -- the live arm is skipped; "
            "the predicate is proven by the fixtures above"
        )
        return
    declared = read_declared(REPO_ROOT / DEBT_REL)
    problems, report = landing_route_problems(rows, declared=declared)
    assert report["population"] > 0, f"a live read that judged nothing proves nothing: {report}"
    assert problems == [], problems


def test_the_gate_is_registered_in_BOTH_audits_and_the_manifest() -> None:
    """P29: an unregistered gate never runs, and a half-registered one runs nowhere.

    Four sites, all asserted, because each one fails differently: both `tools/audit.py` copies
    (the TEMPLATE copy is what ships, so a factory that registers only its own copy ships a
    gate nothing invokes), the trigger map (an unmapped gate is one no change can select), and
    `gate_registry.REQUIRED_GATES` (the manifest grain — this is what makes DROPPING the gate
    RED, so a factory cannot quietly keep the file and delete the runner).
    """
    # STATED SKIP: TEMPLATE/
    # This leg cross-reads the ROOT tree's four registration sites, two of which are FACTORY
    # DATA that no shipped tree carries: the twin audit (`TEMPLATE/tools/audit.py`) and the
    # live trigger map (`registry/gate_triggers.json`, of which only the `.example.json`
    # skeleton ships). The gate derives its root from its OWN file's location, so the shipped
    # copy -- which the shipped audit runs with `cwd=TEMPLATE` -- reads `TEMPLATE/` as its
    # root and both of those resolve under a second `TEMPLATE/` that no tree carries. A tree
    # with no nested `TEMPLATE/` (the shipped template itself, or a bootstrapped factory) is
    # therefore skipped BY NAME rather than reddening on a path that no tree carries (#199).
    if not (REPO_ROOT / "TEMPLATE").is_dir():
        print(
            f"  SKIP  no nested TEMPLATE/ at this depth -- this leg cross-reads "
            f"TEMPLATE/tools/audit.py and registry/gate_triggers.json, both FACTORY DATA "
            f"absent here; the predicate is proven by the fixtures above (#199)"
        )
        return
    for rel in ("tools/audit.py", "TEMPLATE/tools/audit.py"):
        source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "test_cron_landing_route.py" in source, f"gate not registered in {rel} (P29)"
    manifest = json.loads(
        (REPO_ROOT / "registry" / "gate_triggers.json").read_text(encoding="utf-8")
    )
    # The map's keys live UNDER `gates`; a top-level membership test reads every gate as
    # absent, so the level is asserted rather than assumed.
    gates = manifest.get("gates")
    assert isinstance(gates, dict), "registry/gate_triggers.json carries no `gates` map"
    assert GATE_NAME in gates, f"{GATE_NAME} absent from registry/gate_triggers.json"
    registry = (REPO_ROOT / "tests" / "gate_registry.py").read_text(encoding="utf-8")
    assert '"test_cron_landing_route.py"' in registry, (
        "the gate is not in gate_registry.REQUIRED_GATES — dropping it would not RED, so a "
        "factory could keep the file and delete the runner (the manifest grain)"
    )


def test_the_TEMPLATE_twin_is_BYTE_IDENTICAL() -> None:
    """The twin law: a gate that ships must ship as the same bytes it was verified as."""
    twin = REPO_ROOT / TEMPLATE_GATE_REL
    if not twin.is_file():
        print(f"  SKIP  no {TEMPLATE_GATE_REL} in this tree -- the twin arm is skipped")
        return
    assert twin.read_bytes() == Path(__file__).read_bytes(), (
        "TEMPLATE twin differs from the shipped gate -- re-copy it (twin-drift law)"
    )


def test_probe_is_offline() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = imported & {"sqlite3", "subprocess", "socket", "urllib", "http"}
    assert not forbidden, f"the predicate must stay pure and offline, imports: {sorted(forbidden)}"
