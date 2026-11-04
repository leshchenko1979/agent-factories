#!/usr/bin/env python3
"""Gate: a close on an item whose ruling comment is UNPAIRED is refused at the write path.

Origin (issue #611, HQ ruling n=4706). `docs/ruling-board-exemptions.json` carries three
entries and all three have ONE cause: a ruling was hand-posted with `gh issue comment`, and
no `ruling` row was ever stamped for it. `tools/rule.py` makes the two acts one invocation,
but it is OPTIONAL — so a lane that types the gh command directly produces the divergence
silently and a patrol finds it hours later. Measured: #609's ruling comment was posted at
2026-11-03T16:01:35Z and the close row `n=4692` was stamped 8 s later carrying the ruling's
SUBSTANCE in its `detail`; the lane held the whole act in hand and still bypassed the writer.
The leg in `tools/patrol_host_state.py` is the DETECTOR. This gate covers the WRITER.

THE THREE VERDICTS ARE THE WHOLE CONTRACT, and each one is a distinct arm here:

  * `clear`  — the item carries no ruling comment, its latest ruling comment is PAIRED with
               a `ruling` row naming it, is EXEMPTED, or predates the declared bound. The
               row records `board_ruling=clear`: an ASSERTION, not the absence of one, so a
               judged row is told apart from one written before this guard existed.
  * `refuse` — the latest ruling comment is at or after the bound and NOTHING pairs it. The
               append exits non-zero and names `tools/rule.py`. Nothing is written.
  * `unread` — the board could not be read at all. This is an INABILITY, never a block and
               never a pass: the row is WRITTEN and says `board_ruling=unread`, because a gh
               outage must not be able to stop work being recorded, and must not be able to
               masquerade as a clean read either.

WHY THE ARMS ARE DRIVEN THROUGH INJECTION. A guard whose verdicts can only be exercised by
a live board is a guard nobody can neuter-test, and an untestable gate is a claim. Every arm
below runs offline against `rows=` / `read_comments=` / `scope=` / `exemptions=`.

WHY THE NEUTER ARMS EXIST. Each one deletes a single load-bearing line from a COPY of
`tools/ledger.py` and asserts the arm that depends on it FLIPS. An arm that still passes
with its mechanism deleted was never testing that mechanism — the vacuous-pass shape this
repo files repeatedly. A neuter whose anchor no longer exists is a gate ERROR, never a
silent pass: the copy's `PATROL_TOOL` is rewritten to the real absolute path, so the neutered
module resolves the patrol exactly as the live one does.

WHY THE WIRING ARM EXISTS. #611 was implemented once as a guard that sat in the file and was
never called — declared, not wired — and a predicate-only test would have called that green.
So the last arm reads `cmd_append`'s own source and requires the call to be present and to
PRECEDE the flock: a board read taken inside the lock stalls every peer append on this box.
"""

import importlib.util
import inspect
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER_TOOL = REPO / "tools" / "ledger.py"
PATROL_TOOL = REPO / "tools" / "patrol_host_state.py"

# The copy must find the patrol where the live module does. Rewritten rather than copied so
# the neutered module is judged against the SAME predicate home the shipped one uses.
PATROL_LINE = 'PATROL_TOOL = Path(__file__).resolve().parent / "patrol_host_state.py"'

BOUND = "2026-10-02T18:07:38Z"


def load_module(path: Path, name: str = "_close_ruling_ledger"):
    """Load the writer by PATH, with its own sibling imports resolvable.

    `tools/ledger.py` imports its siblings by bare name (`from ledger_declaration import …`),
    so `tools/` has to be on `sys.path` — the same reason the shipped script runs from
    there. A neutered COPY in a temp directory resolves those siblings through the SAME
    entry, which is what lets the copy behave exactly like the shipped module.
    """
    tools = str(REPO / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scope():
    """The declared pairing bound, as `(instant, text, refusal)`."""
    import datetime as dt

    bound = dt.datetime(2026, 10, 2, 18, 7, 38, tzinfo=dt.timezone.utc)
    return (bound, BOUND, "")


def comment(node: str, num: int, created: str, head: str = "## RULED") -> dict:
    return {
        "id": node,
        "url": f"https://github.com/example/repo/issues/1#issuecomment-{num}",
        "createdAt": created,
        "body": head + " — the ruling body",
    }


def _ruling_row(comment_id: int) -> dict:
    return {
        "n": 1,
        "event": "ruling",
        "subject": "#611",
        "detail": f"Ruled. comment={comment_id} board=#611",
    }


def _raise_reader(issue_number):
    raise RuntimeError("gh could not be reached")


# (label, kwargs, expected verdict). The kwargs are the WHOLE of what the arm varies.
ARMS = [
    (
        "an item with no ruling comment is clear",
        dict(rows=[], read_comments=lambda n: [comment("IC_note", 999, "2026-11-01T00:00:00Z",
                                                      head="just a note")]),
        "clear",
    ),
    (
        "a ruling comment PAIRED with its ledger row is clear",
        dict(rows=[_ruling_row(123)],
             read_comments=lambda n: [comment("IC_a", 123, "2026-11-01T00:00:00Z")]),
        "clear",
    ),
    (
        "an unpaired ruling comment after the bound is REFUSED",
        dict(rows=[],
             read_comments=lambda n: [comment("IC_a", 999, "2026-11-01T00:00:00Z")]),
        "refuse",
    ),
    (
        "an EXEMPTED ruling comment is clear",
        dict(rows=[],
             read_comments=lambda n: [comment("IC_a", 999, "2026-11-01T00:00:00Z")],
             exemptions={"IC_a": {"reason": "declared debt"}}),
        "clear",
    ),
    (
        "a ruling comment BEFORE the bound is clear (no row could have paired it)",
        dict(rows=[],
             read_comments=lambda n: [comment("IC_a", 999, "2026-09-01T00:00:00Z")]),
        "clear",
    ),
    (
        "an UNREADABLE board is an INABILITY, not a pass and not a block",
        dict(rows=[], read_comments=_raise_reader),
        "unread",
    ),
    (
        "an UNDECLARED pairing bound is an INABILITY",
        dict(rows=[], read_comments=lambda n: [],
             scope=(None, "", "`ruling_writer_landed` is UNDECLARED")),
        "unread",
    ),
    (
        "an AMENDMENT is judged on the LATEST comment (paired latest is clear)",
        dict(rows=[_ruling_row(222)],
             read_comments=lambda n: [comment("IC_a", 111, "2026-11-01T00:00:00Z"),
                                      comment("IC_b", 222, "2026-11-02T00:00:00Z")]),
        "clear",
    ),
    (
        "an AMENDMENT is judged on the LATEST comment (unpaired latest is REFUSED)",
        dict(rows=[_ruling_row(111)],
             read_comments=lambda n: [comment("IC_a", 111, "2026-11-01T00:00:00Z"),
                                      comment("IC_b", 222, "2026-11-02T00:00:00Z")]),
        "refuse",
    ),
    (
        "a subject naming NO board item is clear, and says so",
        dict(rows=[], read_comments=lambda n: [], subject="a-survey-slug"),
        "clear",
    ),
]


def run_arm(ledger, kwargs):
    """The verdict for one arm, with every injectable defaulted from the module."""
    call = dict(kwargs)
    call.setdefault("scope", scope())
    call.setdefault("exemptions", {})
    subject = call.pop("subject", "#611")
    verdict, _message = ledger.board_ruling_write_path_check(subject, **call)
    return verdict


# (label, anchor that must exist, its replacement, the arm label whose verdict must FLIP).
# The replacement disables exactly one mechanism; the arm that depends on it must stop
# passing. Anchors are full lines so a drifted source is a gate ERROR, never a silent pass.
NEUTER_ARMS = [
    (
        "the PAIRING arm",
        "    if comment_id and paired.get(comment_id):",
        "    if False and comment_id and paired.get(comment_id):",
        "a ruling comment PAIRED with its ledger row is clear",
    ),
    (
        "the EXEMPTION arm",
        "    if comment_node and comment_node in exemptions:",
        "    if False and comment_node and comment_node in exemptions:",
        "an EXEMPTED ruling comment is clear",
    ),
    (
        "the PRE-BOUNDARY arm",
        "    if latest_instant < bound:",
        "    if False and latest_instant < bound:",
        "a ruling comment BEFORE the bound is clear (no row could have paired it)",
    ),
    (
        "the INABILITY arm",
        '        return "unread", f"the board could not be read for #{issue_number}: {exc}"',
        '        return "clear", "swallowed"',
        "an UNREADABLE board is an INABILITY, not a pass and not a block",
    ),
]


def neutered_module(source: str, anchor: str, replacement: str, directory: Path,
                    slug: str):
    """A copy of the writer with ONE mechanism disabled, loadable in this process.

    ONE FILE PER ARM, and that is load-bearing rather than tidy: every neuter replacement
    below is a same-LENGTH edit, and a shared path would hand CPython a `__pycache__` entry
    keyed on (mtime, size) that matches the PREVIOUS arm's bytecode. Measured while writing
    this gate: two arms reported "did NOT bite" because they were executing the first arm's
    compiled body. `sys.dont_write_bytecode` would silence it here and only here.
    """
    if source.count(anchor) != 1:
        raise RuntimeError(
            f"the neuter anchor appears {source.count(anchor)} time(s), not once: {anchor!r}"
        )
    if source.count(PATROL_LINE) != 1:
        raise RuntimeError("the copy's patrol path could not be re-anchored")
    mutated = source.replace(PATROL_LINE, f'PATROL_TOOL = Path("{PATROL_TOOL}")')
    mutated = mutated.replace(anchor, replacement)
    path = directory / f"ledger_neutered_{slug}.py"
    path.write_text(mutated, encoding="utf-8")
    return load_module(path, f"_close_ruling_ledger_neutered_{slug}")


ARMS_BY_LABEL = {label: kwargs for label, kwargs, _want in ARMS}
WANT_BY_LABEL = {label: want for label, _kwargs, want in ARMS}


def cmd_append_slice(source: str) -> str:
    """`cmd_append`'s own body, sliced from a source TEXT, for the wiring neuter arm."""
    start = source.find("\ndef cmd_append(")
    if start < 0:
        return ""
    nxt = source.find("\ndef ", start + 1)
    return source[start: nxt if nxt > 0 else len(source)]


def wiring_problems(body: str) -> list:
    """The guard must be CALLED, and the call must precede the flock (#611).

    A predicate that no writer reaches is the exact defect this arm exists for: it was
    implemented once as a block sitting above `cmd_append` and never invoked, and every
    verdict arm passed while no close could ever be refused.
    """
    problems = []
    call = body.find("board_ruling_write_path_check(")
    if call < 0:
        return ["`cmd_append` never calls `board_ruling_write_path_check` — the guard is "
                "declared and not wired, so no close can be refused by it"]
    lock = body.find("with open(target_lock")
    if lock < 0:
        problems.append("`cmd_append` no longer takes `target_lock`, so the call's position "
                        "relative to the flock cannot be judged")
    elif call > lock:
        problems.append(
            "the board read is taken INSIDE the flock — a network call under the exclusive "
            "lock stalls every peer append on this box for its duration"
        )
    if "BOARD_RULING_KEY" not in body:
        problems.append("`cmd_append` never appends `board_ruling=…` to the row, so a judged "
                        "close is indistinguishable from one written before the guard")
    if body.find("sys.exit") < 0:
        problems.append("`cmd_append` never exits on the guard's refusal, so a refusal would "
                        "be written as an ordinary row")
    # THE SCOPE ARM, and it exists because its absence shipped a live defect. The first
    # wiring used `target_ledger == LEDGER`, which is a TAUTOLOGY: `LEDGER` IS the resolved
    # target, so the comparison excludes nothing and the guard ran on every throwaway ledger.
    # Ten arms of `tests/test_ledger.py` went RED in the commit that shipped it — each fixture
    # close drove a live `gh issue view`, and fixtures that stage a tool closure died reaching
    # for a `patrol_host_state.py` a fixture tree never carries. Every arm above still passed,
    # because "the call exists and precedes the flock" says nothing about WHEN it runs. A guard
    # that cannot be scoped cannot be a gate, so the scope is asserted rather than assumed.
    #
    # COMMENTS ARE STRIPPED FIRST, and that is not tidiness: the prose above QUOTES the
    # tautology it describes, so a raw substring read reds on the very comment explaining the
    # fix — the prose-as-data class this file has now paid for twice. The arm judges CODE.
    guard_at = body.find("board_ruling_write_path_check(")
    head = body[:guard_at] if guard_at > 0 else body
    code = "\n".join(
        line.split("#", 1)[0] for line in head.splitlines()
    )
    if "target_ledger == LEDGER" in code or "LEDGER == target_ledger" in code:
        problems.append(
            "the guard's condition compares the target against `LEDGER`, which is a "
            "TAUTOLOGY — `LEDGER` IS the resolved target, so it excludes nothing and every "
            "fixture close pays a live board read"
        )
    if "fixture" not in code:
        problems.append(
            "the guard is not scoped by the `fixture` seam, so a throwaway ledger reaches "
            "the board — the seam that excludes fixtures for identity and authorization "
            "must exclude them here too"
        )
    return problems


def main() -> int:
    if not LEDGER_TOOL.exists():
        print(f"close-ruling gate UNREADABLE: {LEDGER_TOOL} is absent", file=sys.stderr)
        return 1
    source = LEDGER_TOOL.read_text(encoding="utf-8")
    ledger = load_module(LEDGER_TOOL)
    problems = []

    if not hasattr(ledger, "board_ruling_write_path_check"):
        print("close-ruling gate UNREADABLE: the writer declares no guard at all",
              file=sys.stderr)
        return 1

    # THE POSITIVE CONTROL: the shipped module, unmutated, must satisfy every arm. Without
    # this the neuter arms below would be comparing against nothing.
    verdicts = {}
    for label, kwargs, want in ARMS:
        got = run_arm(ledger, kwargs)
        verdicts[label] = got
        if got != want:
            problems.append(f"shipped module: {label} — got {got!r}, want {want!r}")
    if verdicts.get("an unpaired ruling comment after the bound is REFUSED") == "refuse":
        _v, message = ledger.board_ruling_write_path_check(
            "#611", rows=[], scope=scope(), exemptions={},
            read_comments=lambda n: [comment("IC_a", 999, "2026-11-01T00:00:00Z")],
        )
        if "tools/rule.py" not in message:
            problems.append("the refusal does not name `tools/rule.py`, so the lane is told "
                            "what is wrong and not how to fix it")

    try:
        wired = inspect.getsource(ledger.cmd_append)
    except (OSError, TypeError) as exc:
        problems.append(f"`cmd_append` could not be read, so its wiring cannot be judged: {exc}")
        wired = None
    if wired is not None:
        problems.extend(wiring_problems(wired))

    # THE WIRING NEUTER ARM. Removing the call from a copy of the body must produce a
    # finding: an arm that passes with the call gone is an arm that only ever proved
    # `cmd_append` exists.
    unwired = cmd_append_slice(source).replace(
        "board_ruling_write_path_check(", "board_ruling_write_path_check_DISABLED(")
    if not unwired:
        problems.append("`cmd_append` could not be located in the source, so the wiring "
                        "arm cannot be neuter-tested")
    elif not wiring_problems(unwired):
        problems.append("the WIRING arm did NOT bite: with the call removed from "
                        "`cmd_append` it still reported nothing")

    # THE NEUTER ARMS: each disabled mechanism must cost exactly its own arm.
    flipped = 0
    with tempfile.TemporaryDirectory() as tmp:
        for index, (label, anchor, replacement, arm_label) in enumerate(NEUTER_ARMS):
            try:
                mutant = neutered_module(source, anchor, replacement, Path(tmp),
                                         f"a{index}")
            except (RuntimeError, SyntaxError) as exc:
                problems.append(f"neuter of {label} could not be applied: {exc}")
                continue
            want = WANT_BY_LABEL[arm_label]
            got = run_arm(mutant, dict(ARMS_BY_LABEL[arm_label]))
            if got == want:
                problems.append(
                    f"neuter of {label} did NOT bite: {arm_label!r} still returns "
                    f"{got!r}, so that arm was never testing the mechanism"
                )
            else:
                flipped += 1

    examined = len(ARMS)
    if problems:
        print("close-ruling gate FAILED:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"close-ruling gate: clean — {examined} verdict arm(s) driven through injection "
        f"(clear/refuse/unread each distinct), the writer's call WIRED before the flock and "
        f"its token appended, and {flipped}/{len(NEUTER_ARMS)} neuter arm(s) bit"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
