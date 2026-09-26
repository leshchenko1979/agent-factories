#!/usr/bin/env python3
"""Gate: the hygiene gate only globs namespaces this factory owns.

`/tmp` is shared between every factory on the host. The OpenCrabs dev tooling
leaves its own `oc-snap-*` scratch files there by the thousand, and the first
version of `tools/hygiene.py` globbed `/tmp/oc-*` — so our audit went RED for
litter we never wrote. That is a false red: the mirror of issue #28's false
green, and just as corrosive, because a gate that cries wolf gets switched off.

The property under test is that a FOREIGN prefix cannot fail this factory's
audit. It is probed by planting litter under a prefix we do not own, inside a
throwaway directory, and asserting the audit neither reports it nor reaps it.

Run:  python3 -m pytest tests/test_hygiene_namespace.py -q
Exit: 0 clean, non-zero on a namespace regression.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HYGIENE = REPO / "tools" / "hygiene.py"
AUDIT = REPO / "tools" / "audit.py"
TOOLS = REPO / "tools"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_fixtures import stage_tool  # noqa: E402

FOREIGN_PREFIX = "oc-snap-oc-deploy-"


def _load_hygiene():
    """Import tools/hygiene.py as a module without it being a package."""
    spec = importlib.util.spec_from_file_location("hygiene_under_test", HYGIENE)
    assert spec and spec.loader, f"cannot load {HYGIENE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_owned_namespace_is_derived_not_hardcoded() -> None:
    """The owned prefix is this repo's directory name, so a fork owns its own."""
    hygiene = _load_hygiene()
    assert hygiene.NAMESPACE == REPO.name, (
        f"NAMESPACE is {hygiene.NAMESPACE!r}, expected the repo directory name "
        f"{REPO.name!r} — a bootstrapped factory must own its own prefix"
    )
    assert hygiene.SCRATCH_PATTERNS == [f"/tmp/{REPO.name}-*"], (
        f"unexpected scratch namespaces: {hygiene.SCRATCH_PATTERNS}"
    )


def test_no_foreign_prefix_is_globbed() -> None:
    """No declared pattern may match another tool's namespace."""
    hygiene = _load_hygiene()
    for pattern in hygiene.SCRATCH_PATTERNS:
        assert "oc-snap" not in pattern, (
            f"{pattern!r} globs the OpenCrabs dev namespace — foreign litter "
            f"would fail this factory's audit"
        )
        assert pattern.startswith(f"/tmp/{REPO.name}-"), (
            f"{pattern!r} is outside this factory's owned namespace"
        )


def test_foreign_litter_does_not_fail_our_audit() -> None:
    """Plant foreign litter; the audit must not see it, report it, or reap it."""
    hygiene = _load_hygiene()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        foreign = tmpdir / f"{FOREIGN_PREFIX}999999"
        foreign.write_text("another factory's scratch\n")
        stale = time.time() - (hygiene.MAX_AGE_HOURS + 6) * 3600
        os.utime(foreign, (stale, stale))

        # Point the owned-namespace glob at this throwaway dir so the real
        # owned prefix is also exercised by the same code path.
        ours = tmpdir / f"{REPO.name}-777777"
        ours.write_text("our own stale scratch\n")
        os.utime(ours, (stale, stale))

        reaped, found = hygiene.reap_stale_scratch(
            dry_run=True, patterns=[str(tmpdir / f"{REPO.name}-*")]
        )

        names = " ".join(found)
        assert FOREIGN_PREFIX not in names, (
            f"foreign litter was reported by our audit: {found}"
        )
        assert str(ours) in names, (
            f"our own stale scratch was NOT reported: {found} — the gate has "
            f"gone blind instead of scoped"
        )
        assert reaped == len(found)

        # dry_run=True is audit mode and must not delete; dry_run=False is the
        # clean path and must. Both are asserted, because a gate that reaps
        # during an audit destroys evidence, and one that never reaps is a
        # no-op wearing a gate's name.
        assert ours.exists(), "audit mode (dry_run=True) deleted a file"
        hygiene.reap_stale_scratch(
            dry_run=False, patterns=[str(tmpdir / f"{REPO.name}-*")]
        )
        assert not ours.exists(), "clean mode (dry_run=False) reaped nothing"


def scratch_name(line: str) -> str:
    """The filename a `stale scratch file:` violation line names.

    Parsed by LABEL, never by the LAST COLON (ai-antispam HQ, 2026-09-21).
    `reap_stale_scratch` freezes an age annotation into each entry before `basename`
    is applied, so the violation line reads

        '  - stale scratch file: <name> (age: 64h)'

    and the last colon belongs to the ANNOTATION, not to the label: an `rsplit(":")`
    returned `'64h)'` for every line, whatever the filename was. That read the guard RED
    on our OWN litter (a false RED) and left it blind to a foreign name at the same time.
    Factored out of the live loop so `test_scratch_name_parser_is_probed_offline` can
    drive it with synthetic lines — a probe is the only way this predicate is exercised
    on a box whose namespace happens to hold nothing, which is exactly the state that let
    the defect sit here unreported.
    """
    tail = line.split("stale scratch file:", 1)[1]
    return tail.split(" (age:", 1)[0].strip()

def test_scratch_name_parser_is_probed_offline() -> None:
    """The parser is driven by SYNTHETIC lines, so this file is never vacuous.

    The live loop below can only assert over lines the tool actually prints, and on a box
    whose `/tmp/<repo>-*` namespace holds nothing stale it examines ZERO lines — green
    because it saw nothing, not because the population was clean. That is the state that
    let the `rsplit` defect ship: the loop body had never run here, while it fired on the
    first run anywhere with real litter. So the predicate is probed directly, and the
    probe would FAIL on the defect it was written for.
    """
    # BOTH names are DERIVED, never literal. This file is copied into every factory, and
    # a literal here made the probe a property of the ORIGIN tree. Measured 2026-09-22 on
    # the byte-identical copy: with `agent-factories` hardcoded, the probe FAILS wherever
    # the containing directory name differs — a real destination factory, and even this
    # repo's own `TEMPLATE/tests/` — because `own` then carries a foreign name and
    # `foreign` carries ours, so the pair INVERTS and the assertion reds (#137).
    own = f"  - stale scratch file: {REPO.name}-probe.log (age: 30h)"
    foreign = f"  - stale scratch file: not-{REPO.name}-probe.log (age: 64h)"

    assert scratch_name(own) == f"{REPO.name}-probe.log", scratch_name(own)
    assert scratch_name(foreign) == f"not-{REPO.name}-probe.log", scratch_name(foreign)
    assert scratch_name(own).startswith(f"{REPO.name}-"), "our OWN litter must be accepted"
    assert not scratch_name(foreign).startswith(f"{REPO.name}-"), (
        "a FOREIGN name must be rejected by the namespace assertion"
    )

    # The defect itself, pinned so a regression to the old form cannot pass: the LAST
    # COLON belongs to the age annotation, so that parse can never yield a filename.
    assert own.rsplit(":", 1)[-1].strip() == "30h)", "the old parse is what the fix replaced"
    assert not own.rsplit(":", 1)[-1].strip().startswith(f"{REPO.name}-"), (
        "the old parse rejected our own file — a false RED, the half that made it visible"
    )

def test_cli_audit_never_reports_foreign_litter() -> None:
    """End-to-end: real /tmp litter from the dev tools is never our violation.

    The gate's return code also depends on the working tree, which is dirty
    while a change is in flight — so the assertion is on the reported scratch
    violations, not on the exit code. What must hold unconditionally: no
    violation line names a foreign prefix, and every scratch line that IS
    reported belongs to the namespace this factory owns.
    """
    res = subprocess.run(
        [sys.executable, str(HYGIENE), "--audit"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    output = res.stdout + res.stderr
    foreign_count = len(list(Path("/tmp").glob(f"{FOREIGN_PREFIX}*")))

    assert FOREIGN_PREFIX not in output, (
        f"hygiene --audit reported foreign litter ({foreign_count} "
        f"{FOREIGN_PREFIX}* files exist in /tmp)\n{output[:2000]}"
    )

    for line in output.splitlines():
        if "stale scratch file" in line:
            name = scratch_name(line)
            assert name.startswith(f"{REPO.name}-"), (
                f"audit reported a scratch file outside our namespace: {name!r}"
            )


def _audit(*, namespace: str | None = None, tool: Path | None = None) -> str:
    """Run the hygiene audit through its CLI and return the combined output.

    `tool` exists so a probe can drive a COPY of the tool living elsewhere: the
    namespace default is derived from the tool's OWN path, so the only way to
    exercise the run-site defect is to move the tool, never the cwd.
    """
    cmd = [sys.executable, str(tool or HYGIENE), "--audit"]
    if namespace is not None:
        cmd += ["--namespace", namespace]
    res = subprocess.run(
        cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return res.stdout + res.stderr


def _load_audit():
    """Import tools/audit.py as a module without it being a package."""
    spec = importlib.util.spec_from_file_location("audit_under_test", AUDIT)
    assert spec and spec.loader, f"cannot load {AUDIT}"
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE exec: the module's dataclasses resolve their own
    # `__module__` through sys.modules, and an unregistered module raises
    # AttributeError inside dataclasses._is_type.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_namespace_flag_moves_the_population() -> None:
    """`--namespace` must MOVE what is globbed, or it does nothing (#174).

    A flag whose population does not follow it is indistinguishable from a flag
    that is ignored, so BOTH directions are asserted. Both runs use a PROBE-ONLY
    namespace, never this factory's own, so a concurrent audit on a shared box
    cannot observe the planted file.
    """
    ns = f"hygiene-probe-{os.getpid()}"
    planted = Path("/tmp") / f"{ns}-stale.bin"
    try:
        planted.write_text("planted by the #174 probe\n")
        stale = time.time() - (24 + 6) * 3600
        os.utime(planted, (stale, stale))

        seen = _audit(namespace=ns)
        assert f"{ns}-stale.bin" in seen, (
            f"--namespace {ns!r} did not move the population — the planted "
            f"stale file was not reported:\n{seen}"
        )

        elsewhere = _audit(namespace=f"{ns}-empty")
        assert f"{ns}-stale.bin" not in elsewhere, (
            f"a namespace that does not own the file reported it anyway:\n{elsewhere}"
        )
        # Asserted on the NAMESPACE LINE, never on the audit being wholly clean:
        # the tree inspection is cwd-relative, so a run from a subdirectory
        # reports path artifacts that have nothing to do with the population
        # this probe moves.
        assert f"hygiene namespace: {ns}-empty (declared)" in elsewhere, elsewhere
    finally:
        planted.unlink(missing_ok=True)


def test_namespace_flag_overrides_the_run_site() -> None:
    """The declared namespace WINS over the directory the tool sits in (#174).

    The pair is the whole point: the same copy of the tool, run with the same
    cwd, reports the run site's directory name by DEFAULT and the declared
    namespace once the flag is given. Without the first arm this probe would pass
    on a tool whose default had silently become canonical, and the worktree
    defect it exists for would go unexercised.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # Staged WITH ITS IMPORT CLOSURE, never copied alone (P35, meta-factory
        # #60): a fixture that copies a tool by itself assumes a self-containment
        # nothing states, and breaks the moment the tool gains a neighbour import.
        tools_dir = Path(tmp) / "not-this-factory" / "tools"
        stage_tool(HYGIENE, tools_dir, TOOLS)
        tool = tools_dir / "hygiene.py"

        defaulted = _audit(tool=tool)
        assert "hygiene namespace: not-this-factory (default" in defaulted, (
            f"the default no longer follows the run site, so this probe has "
            f"stopped exercising the defect it was written for:\n{defaulted}"
        )

        declared = _audit(tool=tool, namespace=REPO.name)
        assert f"hygiene namespace: {REPO.name} (declared)" in declared, (
            f"--namespace did not override the run site:\n{declared}"
        )


def test_audit_resolves_the_canonical_namespace() -> None:
    """The audit grades the namespace this factory OWNS, from any run site (#174).

    `Path.name` is the naive derivation and it is WRONG for any run site other
    than the main worktree: from `tools/` it grades a namespace called `tools`,
    and from a linked worktree the worktree's own directory name. The canonical
    name comes from the main worktree, which `git rev-parse --git-common-dir`
    resolves from either.

    The probe is written as a PROPERTY, never as this repo's directory name: this
    file is byte-paired into `TEMPLATE/`, whose canonical namespace is still the
    main worktree's, so an assertion on `REPO.name` would red where it is copied.
    Both arms are asserted, because an invariant answer that happened to BE the
    run site's directory name would satisfy the invariance arm alone.
    """
    audit = _load_audit()

    # Arm 1 — a tree that is not a checkout falls back to its own directory name.
    # The fallback is the documented behaviour, so it is asserted rather than
    # left as the branch nobody exercises.
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "not-a-checkout"
        plain.mkdir()
        assert audit.hygiene_namespace(plain) == "not-a-checkout", (
            f"a tree that is not a checkout returned "
            f"{audit.hygiene_namespace(plain)!r} instead of its directory name"
        )

    # Arm 2 — inside a checkout the answer must NOT follow the run site.
    probe = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if probe.returncode != 0:
        print(
            "note: this tree is not a git checkout, so the run-site invariance "
            "is unobservable here — arm 1 covered the fallback instead"
        )
        return

    root = audit.hygiene_namespace(audit.REPO_ROOT)
    nested = audit.hygiene_namespace(audit.REPO_ROOT / "tools")
    assert root, "the helper returned an empty namespace"
    assert nested == root, (
        f"a run site inside the tree resolved to {nested!r} while the root "
        f"resolved to {root!r} — the namespace must not follow the run site"
    )
    assert root != (audit.REPO_ROOT / "tools").name, (
        f"the namespace followed the run site: {root!r} is the run site's own "
        f"directory name, which is the #174 defect"
    )

# --- the classifier (#153) -------------------------------------------------
#
# Every literal in tracked sources that names a path inside this factory's OWNED
# scratch namespace must be CLASSIFIED in the declaration. An unclassified one is
# a NEW live artifact: it fails CI rather than being reaped in silence. The
# predicate is one function, driven by the live leg AND by the probes below, so
# the probes cannot drift from the check they exist to probe.

# Read from the tool's own constant, never restated: a second copy would drift
# from the file the reaper actually consults.
DECLARATION_REL = _load_hygiene().PROTECTED_REL

def owned_literals(text: str, namespace: str) -> list[tuple[int, str]]:
    """Every (line number, literal) naming a path inside `namespace`."""
    pattern = re.compile(r"/tmp/" + re.escape(namespace) + r"-[A-Za-z0-9_.\-]*")
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for match in pattern.finditer(line):
            out.append((lineno, match.group(0)))
    return out

def classify(
    texts: dict[str, str], namespace: str, protected: set[str], scratch: set[str]
) -> tuple[list[str], int]:
    """(problems, literals examined) over {relative path: file text}.

    A literal is classified when it appears in EITHER list. Both lists are
    consulted, because a `scratch` entry is a literal somebody considered and
    decided was litter, which is exactly what a bare "protected" list could not
    express without a false declaration.
    """
    declared = set(protected) | set(scratch)
    problems: list[str] = []
    examined = 0
    for rel, body in sorted(texts.items()):
        for lineno, literal in owned_literals(body, namespace):
            examined += 1
            if literal not in declared:
                problems.append(
                    f"{rel}:{lineno}: {literal} is in this factory's scratch "
                    f"namespace and is NOT classified — declare it in "
                    f"{DECLARATION_REL} as `protected` (live state, never reaped) or "
                    f"`scratch` (genuinely reapable)"
                )
    return problems, examined

RECORD_PREFIX = "evidence/"

def _tracked_texts() -> dict[str, str]:
    """Every tracked file that decodes as UTF-8, as {relative path: text}.

    The append-only RECORD is excluded, and the distinction is principled rather
    than a carve-out: the evidence tree holds what was done and said — ledger
    rows, score artifacts, the rework log, delivered specs — and no file there
    can CREATE an artifact. A path merely MENTIONED in a ledger row is prose, not
    a live artifact, and the record is forward-only: it must never be edited to
    satisfy a gate. Measured when this leg was written: all six literals the scan
    first found were prose in the evidence tree, none of them a creator. The
    classifier exists to catch the file that MAKES the path.
    """
    res = subprocess.run(
        ["git", "ls-files"], cwd=REPO, stdout=subprocess.PIPE, text=True
    )
    assert res.returncode == 0, "git ls-files failed — the classifier cannot read the tree"
    out: dict[str, str] = {}
    for rel in res.stdout.splitlines():
        if rel.startswith(RECORD_PREFIX):
            continue
        path = REPO / rel
        try:
            out[rel] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return out

def test_every_owned_namespace_literal_is_classified() -> None:
    """Live leg — the population is PRINTED, so a clean verdict is never vacuous.

    This factory's namespace holds no literal today, which is the normal read for
    a forward-only surface: the check exists so the FIRST one cannot land
    unclassified. The population is printed for exactly that reason — "nothing to
    classify" and "a classifier that cannot see" must never be the same output.
    """
    hygiene = _load_hygiene()
    protected, scratch, problems = hygiene.load_declaration(REPO)
    assert not problems, f"the declaration is malformed: {problems}"

    found, examined = classify(
        _tracked_texts(),
        hygiene.NAMESPACE,
        {e["path"] for e in protected},
        {e["path"] for e in scratch},
    )
    print(
        f"hygiene classifier: {examined} literal(s) in the owned namespace "
        f"/tmp/{hygiene.NAMESPACE}-* over {len(_tracked_texts())} tracked file(s), "
        f"{len(protected)} declared live, {len(scratch)} declared scratch, "
        f"{len(found)} unclassified"
    )
    assert not found, "\n".join(found)

def test_a_new_owned_literal_is_unclassified() -> None:
    """The non-vacuity leg: a NEW live artifact must RED, not be reaped in silence.

    The literal is DERIVED, never written as one: this file is itself tracked, so a
    literal here would be a real member of the population the live leg classifies,
    and the probe would be testing its own fixture rather than the predicate.
    """
    hygiene = _load_hygiene()
    ns = hygiene.NAMESPACE
    new_live = "/tmp/" + ns + "-manager.lock"
    problems, examined = classify(
        {"tools/manager.py": f'LOCK = "{new_live}"\n'},
        ns, set(), set(),
    )
    assert examined == 1, f"the classifier did not see the literal: examined={examined}"
    assert problems, "a NEW literal in the owned namespace was classified by nothing"
    assert new_live in problems[0], problems[0]

def test_a_classified_literal_passes() -> None:
    """The control: the same literal, declared, is clean — so the RED above is a finding."""
    hygiene = _load_hygiene()
    ns = hygiene.NAMESPACE
    new_live = "/tmp/" + ns + "-manager.lock"
    problems, examined = classify(
        {"tools/manager.py": f'LOCK = "{new_live}"\n'},
        ns, {new_live}, set(),
    )
    assert examined == 1
    assert not problems, problems

    # And the `scratch` class is consulted too, or a factory could only ever
    # classify a path by falsely declaring it live.
    problems2, _ = classify(
        {"tools/manager.py": f'SCRATCH = "{new_live}"\n'},
        ns, set(), {new_live},
    )
    assert not problems2, problems2

def test_a_foreign_namespace_literal_is_not_ours() -> None:
    """A literal in ANOTHER factory's namespace is not this factory's to classify.

    This is the property the gate's own name is about: the reaper never globs a
    foreign prefix, so the classifier must not demand a declaration for one.
    """
    hygiene = _load_hygiene()
    foreign = "/tmp/" + "some-other-factory" + "-thing.lock"
    problems, examined = classify(
        {"tools/other.py": f'X = "{foreign}"\n'}, hygiene.NAMESPACE, set(), set()
    )
    assert examined == 0, f"a foreign literal was counted as ours: {examined}"
    assert not problems, problems


def test_a_protected_path_survives_the_reap() -> None:
    """The reaper SKIPS a declared-live path — the whole point of #153.

    Driven through `reap_stale_scratch` itself, with both arms in one probe: a
    protected stale file must survive, and an undeclared stale file beside it must
    be reaped in the same call. Without the second arm the probe would pass on a
    reaper that had simply stopped reaping.
    """
    hygiene = _load_hygiene()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        protected = tmpdir / f"{REPO.name}-live.lock"
        litter = tmpdir / f"{REPO.name}-scratch.log"
        stale = time.time() - (hygiene.MAX_AGE_HOURS + 6) * 3600
        for f in (protected, litter):
            f.write_text("probe\n")
            os.utime(f, (stale, stale))

        pattern = str(tmpdir / f"{REPO.name}-*")
        reaped, found = hygiene.reap_stale_scratch(
            dry_run=False, patterns=[pattern], protected={str(protected)}
        )

        assert protected.exists(), (
            "a path DECLARED LIVE was unlinked — the declaration did not hold"
        )
        assert not litter.exists(), "the undeclared stale file survived the reap"
        assert str(litter) in " ".join(found), (
            f"the reaped file was not reported: {found}"
        )
        assert str(protected) not in " ".join(found), (
            f"a PROTECTED path was reported as stale scratch: {found}"
        )
        assert reaped == 1, f"expected exactly one reap, got {reaped}"


def test_the_declaration_refuses_a_blank_why() -> None:
    """An entry nobody could defend in the output is refused, not honoured.

    `why` is the field that makes the declaration reviewable, so a blank one is a
    problem rather than an empty string that reads as satisfied.
    """
    hygiene = _load_hygiene()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        decl = root / hygiene.PROTECTED_REL
        decl.write_text(
            '{"protected": [{"path": "/tmp/x-live.lock", "why": "   "}], "scratch": []}',
            encoding="utf-8",
        )
        protected, scratch, problems = hygiene.load_declaration(root)
        assert problems, "a blank `why` was accepted"
        assert not protected, "the malformed entry was still honoured"
        assert not scratch

        # The control: a well-formed entry loads, so the refusal above is a
        # finding rather than a loader that rejects everything.
        decl.write_text(
            '{"protected": [{"path": "/tmp/x-live.lock", "why": "held long-term"}],'
            ' "scratch": []}',
            encoding="utf-8",
        )
        protected2, _scratch2, problems2 = hygiene.load_declaration(root)
        assert not problems2, problems2
        assert [e["path"] for e in protected2] == ["/tmp/x-live.lock"]
