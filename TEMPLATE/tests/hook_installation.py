#!/usr/bin/env python3
"""Shared predicate: is a versioned git hook present, executable and wired?

A hook that is versioned but never installed is SILENT — git simply does not run
it, and every gate that rests on the hook's refusal reads green over a mechanism
that is not there. That is the vacuous-pass shape this factory forbids, so
absence is a RED gate rather than an advisory.

Two gates assert that property over two different hooks:

  tests/test_ledger_commit_cites_no_rows.py   tools/hooks/commit-msg   (#47)
  tests/test_commit_pair_hook.py              tools/hooks/pre-commit   (#92)

The first carried the predicate inline, hardcoded to its own hook path and its
own issue wording. The second needs the same three facts about a different hook.
Two implementations of one predicate drift, and the drift is silent (#92's own
class, applied to a predicate rather than to a byte pair) — so the predicate
lives here once and both gates bind their constants to it.

This module is deliberately NOT a gate: it declares nothing, registers nothing,
and its docstring does not open with the canonical `Gate` form, so
`tests/gate_registry.py` does not find it. It is a library the gates import.

Pure by construction. `hook_state_problems` takes the three facts as arguments
rather than reading them, so a synthetic state can drive every rejection path —
a rule that has only ever seen good input has not been shown to reject bad input.

Run:  imported, never executed directly.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

HOOKS_PATH_CONFIG = "tools/hooks"

def git_in(top: Path, *args: str) -> tuple[int, str, str]:
    """`git -C <top> <args>` — the one place this module shells out."""
    proc = subprocess.run(
        ["git", "-C", str(top), *args], capture_output=True, text=True
    )
    return proc.returncode, proc.stdout, proc.stderr

def hook_state_problems(
    *,
    hook_path: str,
    hooks_path_config: str,
    exists: bool,
    executable: bool,
    configured: str,
    missing_reason: str = "",
) -> list[str]:
    """The three facts an installed hook is made of, judged.

    `hook_path` and `hooks_path_config` are parameters rather than constants so
    this predicate is about the MECHANISM and not about one hook. The caller
    binds them, which is what lets two gates share one implementation while each
    keeps naming its own hook in its own failure message.

    `missing_reason` is the same idea applied to the wording: a hook is absent
    for a reason that is specific to the law it carries, and the gate that owns
    that law supplies the sentence. Without it the shared message would be
    generic, and a failure that no longer says WHICH law lost its refusal point
    is a worse failure — the pointer is the part a reader needs. Omitted, the
    generic sentence stands, so the parameter is an addition rather than a
    requirement.
    """
    problems: list[str] = []
    if not exists:
        problems.append(
            missing_reason
            or (
                f"{hook_path} is missing — the versioned hook is not shipped, so the "
                "refusal point that makes this law a mechanism rather than a hope "
                "never runs"
            )
        )
    elif not executable:
        problems.append(f"{hook_path} is not executable — git will not run it")
    shown = configured or "unset"
    if configured != hooks_path_config:
        problems.append(
            f"core.hooksPath is {shown!r} — the hook is versioned but not wired, so "
            "it never runs. Install it: "
            f"git config core.hooksPath {hooks_path_config}"
        )
    return problems

def hook_installation_problems(
    top: Path,
    hook_path: str,
    hooks_path_config: str = HOOKS_PATH_CONFIG,
    missing_reason: str = "",
) -> list[str]:
    """Read the installation state off the tree and git config, then judge it.

    Reading and judging are split so the judging half stays pure and probeable;
    this half is the thin I/O edge, and it is the only part a synthetic tree
    cannot drive.
    """
    hook = top / hook_path
    rc, out, _ = git_in(top, "config", "--get", "core.hooksPath")
    return hook_state_problems(
        hook_path=hook_path,
        hooks_path_config=hooks_path_config,
        exists=hook.is_file(),
        executable=os.access(hook, os.X_OK),
        configured=out.strip() if rc == 0 else "",
        missing_reason=missing_reason,
    )
