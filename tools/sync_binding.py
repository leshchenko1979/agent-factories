#!/usr/bin/env python3
r"""Sync the law-binding tree to `origin/main`, refusing when it carries work.

WHAT THIS UPHOLDS. Board #503, ordered by the ruling on #502: the tree that serves a
profile's law binding (`/root/.opencrabs/profiles/ops/skills/meta-factory` ->
`/root/agent-factories/skills/meta-factory`) is a SHARED WORKING TREE that nothing
fetches into and nothing checks out, so its currency was owned by nobody. Measured
2026-10-17T00:58Z on that tree: HEAD `a0ba409b` against `origin/main` `65d954fe`, the
loaded `state.md` at `8d354b69d8ac` against `a93fe1d4600f`, and its own
`evidence/ledger.jsonl` at 2657 rows against 3469. The blast radius is EXECUTED: two
crons (`factory-insights-weekly`, `factory-template-weekly`) resolve their REPO from
`__file__`, so both computed against a stale ledger.

THE PREDICATE, in three outcomes and nothing else.

  LEVEL        HEAD == the remote tip, read from the REMOTE this round. No action.
  FAST-FORWARD the tree is CLEAN and BEHIND: no local commits, no path differing from
               HEAD, and `origin/main` strictly ahead. `git merge --ff-only` moves it.
  REFUSE       the tree carries work not in `origin/main` -- any local-only commit, any
               path differing from HEAD (staged, unstaged or untracked), a detached
               HEAD, or a HEAD that is neither level, behind nor ahead. It changes
               NOTHING and names what it found.

A DESTRUCTIVE SYNC IS WORSE THAN A STALE ONE. The refusal is the point of the tool: the
2026-10-17 reconciliation of that tree was done by hand because a reset would have
destroyed 192 paths of displaced state, and a cron that reset automatically would have
done it silently. `--ff-only` is therefore the ONLY move this tool is allowed to make.

WHY THE RECEIPT IS A FILE AND NOT A LEDGER ROW. `docs/instruments/pacemaker.md` names the
duty receipt as a `run` row written by the WOKEN LANE, and the ledger's actor set is
closed and derived from a lane's own session. This job does not wake a lane: it runs on a
cron clock and needs no judgement, so there is no lane to derive an actor from. Its
receipt is therefore `<git-common-dir>/binding-sync-receipt.json`, the shape
`tools/publish.py` already uses for exactly the same two reasons: a receipt that rode the
pushed history would move the remote tip PAST the sha it records, and a receipt written
INSIDE this tree would make the tree dirty -- which is the one condition this tool
refuses on. The file sits in the COMMON dir so every worktree reads one record, and it
records the CHECKOUT that wrote it.

THE BOUND, stated not hidden. The tool cannot tell a lane's abandoned work from a lane's
work in flight; both read as REFUSE. That is deliberate -- the cron reports the paths and
a human or a lane decides. It also does not decide whether the declaration still names
this repository: it reports the binding rows it resolved and prints NOT RUN with its
reason when the declaration is absent, so an unbound tree is visible rather than clean.

Exit codes: 0 = level or moved, 3 = refused, 2 = could not read the facts at all.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REMOTE = "origin"
BRANCH = "main"
DECLARATION = "docs/harness-bindings.json"
RECEIPT_NAME = "binding-sync-receipt.json"
SYMLINK_MODE = "120000"
MAX_NAMED = 8


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run one git command in `repo`, never raising on a non-zero exit."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _out(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout.strip() if proc.returncode == 0 else ""


def read_binding(repo: Path) -> tuple[list[dict], str]:
    """The declaration rows that resolve INTO this tree, and a reason when none does.

    The schema is the one `tests/test_harness_bindings.py` reads, and it is NOT a list of
    absolute paths: `profile` names the OpenCrabs profile whose `skills/` directory carries
    the load paths, and each row names `skill` (the entry under that directory) and
    `repo_path` (the source, relative to this repo). So the question this function answers
    is "is a profile entry a SYMLINK whose realpath lands inside this tree" -- resolved
    through the filesystem, because that is where a binding exists or does not. A row
    carrying `loaded: false` declares a law DELIBERATELY not bound and is not counted: it
    is a statement about the tree's intent, never a load path that could be stale.
    """
    path = repo / DECLARATION
    if not path.is_file():
        return [], f"no declaration at {path}"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return [], f"declaration unreadable: {exc}"
    if not isinstance(data, dict):
        return [], "declaration is not an object with `profile` and `bindings`"
    profile = data.get("profile")
    rows = data.get("bindings")
    if not isinstance(rows, list):
        return [], "declaration carries no `bindings` list"
    if not isinstance(profile, str) or not profile:
        return [], "declaration names no `profile`, so no load path can be resolved"
    target = str(repo.resolve())
    found: list[dict] = []
    unresolved: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("loaded") is False:
            continue
        skill = row.get("skill")
        if not isinstance(skill, str) or not skill:
            continue
        entry = os.path.expanduser(
            f"~/.opencrabs/profiles/{profile}/skills/{skill}"
        )
        try:
            resolved = str(Path(entry).resolve())
        except OSError:
            unresolved.append(skill)
            continue
        if resolved == target or resolved.startswith(target + os.sep):
            found.append({**row, "entry": entry, "resolved": resolved})
        else:
            unresolved.append(skill)
    if found:
        return found, ""
    if unresolved:
        return [], (f"{len(unresolved)} binding(s) in {DECLARATION} resolve OUTSIDE "
                    f"{target}: {', '.join(unresolved[:MAX_NAMED])}")
    return [], f"no binding in {DECLARATION} resolves into {target}"


def verify_loaded(repo: Path, binding_rows: list[dict], ref: str,
                  remote: str = REMOTE, branch: str = BRANCH) -> dict:
    """Do the files ON DISK still hold the bytes `ref` records? Read per binding prefix.

    WHY THIS IS NOT HEAD EQUALITY. `HEAD == origin/main` says the tree's COMMIT matches.
    It does not say the working tree holds that commit's content: `assume-unchanged`, a
    `skip-worktree` bit from a sparse checkout, or a path restored from a backup all leave
    a tree whose HEAD is level and whose loaded bytes are stale. That is the failure mode
    this whole tool exists for -- a bound law file that loads OLD text while every git
    command reports currency -- so it is measured directly rather than inferred.

    The comparison is the WORKING TREE's bytes against `ref`'s blob, per tracked path under
    each declared `repo_path`. `git hash-object` computes the blob sha of the file on disk,
    which is the same digest `ls-tree` reports, so the two are directly comparable and no
    content is read into this process.
    """
    prefixes = [
        row["repo_path"] for row in binding_rows
        if isinstance(row.get("repo_path"), str) and row.get("repo_path")
    ]
    facts: dict = {"checked": 0, "differing": [], "missing": [], "prefixes": prefixes}
    if not prefixes:
        facts["reason"] = "no declared `repo_path` to verify"
        return facts
    listing = _out(_git(repo, "ls-tree", "-r", ref, "--", *prefixes))
    if not listing:
        facts["reason"] = f"`{ref}` records no tracked path under {prefixes}"
        return facts
    for line in listing.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or not path:
            continue
        mode, recorded = parts[0], parts[2]
        target = repo / path
        if not (target.is_symlink() or target.is_file()):
            facts["missing"].append(path)
            continue
        facts["checked"] += 1
        if mode == SYMLINK_MODE:
            # A symlink's blob is its LINK TARGET STRING, not the bytes it resolves to --
            # `git hash-object` would FOLLOW the link and hash the target file's content,
            # so comparing the two would report every correct symlink as stale (measured
            # 2026-10-17: 8 of 11 bound files "differing" on a level tree, all of them the
            # symlinked instrument docs). Read the recorded target and compare the link.
            if not target.is_symlink():
                facts["differing"].append(path)
                continue
            recorded_target = _out(_git(repo, "cat-file", "blob", recorded))
            if recorded_target != os.readlink(target):
                facts["differing"].append(path)
            continue
        on_disk = _out(_git(repo, "hash-object", "--", path))
        if on_disk and on_disk != recorded:
            facts["differing"].append(path)
    return facts


def gather(repo: Path, remote: str = REMOTE, branch: str = BRANCH,
           fetch: bool = True, read_at: str = "",
           binding_rows: list[dict] | None = None) -> dict:
    """Read every fact the predicate needs, from the repository itself.

    `binding_rows` is optional and, when given, adds the LOADED-FILE leg: the on-disk bytes
    under each declared `repo_path`, compared against the remote tip's own blobs. A caller
    that omits it gets the commit-level facts only, which is what the pure probes drive.
    """
    facts: dict = {
        "repo": str(repo.resolve()),
        "remote": remote,
        "branch": branch,
        "read_at": read_at,
    }
    if fetch:
        proc = _git(repo, "fetch", "--quiet", remote, branch)
        facts["fetch_rc"] = proc.returncode
        facts["fetch_stderr"] = proc.stderr.strip()
    facts["head"] = _out(_git(repo, "rev-parse", "HEAD")) or None
    facts["remote_tip"] = _out(_git(repo, "rev-parse", f"{remote}/{branch}")) or None
    facts["current_branch"] = _out(_git(repo, "rev-parse", "--abbrev-ref", "HEAD")) or None
    facts["local_only"] = [
        line.split("\t", 2)
        for line in _out(_git(repo, "log", "--format=%H%x09%cs%x09%s",
                              f"{remote}/{branch}..HEAD")).splitlines()
        if line.strip()
    ]
    facts["dirty"] = [
        line for line in _out(_git(repo, "status", "--porcelain")).splitlines() if line.strip()
    ]
    behind = _out(_git(repo, "rev-list", "--count", f"HEAD..{remote}/{branch}"))
    facts["behind"] = int(behind) if behind.isdigit() else None
    if binding_rows and facts.get("remote_tip"):
        facts["loaded"] = verify_loaded(repo, binding_rows, facts["remote_tip"],
                                        remote=remote, branch=branch)
    return facts


def assess(facts: dict) -> dict:
    """PURE over the facts: level, fast-forward, or refuse -- with the reasons named."""
    if not facts.get("head") or not facts.get("remote_tip"):
        return {"action": "refuse", "reasons": ["cannot read HEAD or the remote tip"]}
    if facts.get("current_branch") != facts.get("branch"):
        return {
            "action": "refuse",
            "reasons": [
                f"HEAD is on {facts.get('current_branch')!r}, not {facts.get('branch')!r}"
            ],
        }
    reasons: list[str] = []
    local_only = facts.get("local_only") or []
    dirty = facts.get("dirty") or []
    if local_only:
        named = ", ".join(sha[:8] for sha, *_ in local_only[:MAX_NAMED])
        more = f" (+{len(local_only) - MAX_NAMED} more)" if len(local_only) > MAX_NAMED else ""
        reasons.append(f"{len(local_only)} local-only commit(s) not in {facts['remote']}/"
                       f"{facts['branch']}: {named}{more}")
    if dirty:
        named = ", ".join(line for line in dirty[:MAX_NAMED])
        more = f" (+{len(dirty) - MAX_NAMED} more)" if len(dirty) > MAX_NAMED else ""
        reasons.append(f"{len(dirty)} path(s) differing from HEAD: {named}{more}")
    loaded = facts.get("loaded") or {}
    stale = list(loaded.get("differing") or []) + list(loaded.get("missing") or [])
    if stale:
        named = ", ".join(stale[:MAX_NAMED])
        more = f" (+{len(stale) - MAX_NAMED} more)" if len(stale) > MAX_NAMED else ""
        reasons.append(
            f"{len(stale)} loaded file(s) under the binding do NOT hold the bytes at "
            f"{facts['remote']}/{facts['branch']}: {named}{more}"
        )
    if reasons:
        return {"action": "refuse", "reasons": reasons}
    if facts["head"] == facts["remote_tip"]:
        return {"action": "level", "reasons": []}
    behind = facts.get("behind")
    if isinstance(behind, int) and behind > 0:
        return {"action": "fast-forward", "reasons": [], "target": facts["remote_tip"],
                "behind": behind}
    return {
        "action": "refuse",
        "reasons": [
            f"HEAD {facts['head'][:8]} differs from the remote tip "
            f"{facts['remote_tip'][:8]} but is neither behind nor ahead"
        ],
    }


def receipt_path(repo: Path) -> Path | None:
    """The per-repository receipt, in the git COMMON dir, or None when unresolvable."""
    common = _out(_git(repo, "rev-parse", "--git-common-dir"))
    if not common:
        return None
    path = Path(common)
    if not path.is_absolute():
        path = (repo / path).resolve()
    return path / RECEIPT_NAME


def write_receipt(path: Path | None, payload: dict) -> str:
    """Write the receipt atomically; report the path written or the reason it was not."""
    if path is None:
        return "receipt NOT WRITTEN: the git common dir could not be resolved"
    try:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        os.replace(tmp, path)
    except OSError as exc:
        return f"receipt NOT WRITTEN: {exc}"
    return f"receipt {path}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(REPO), help="the tree to sync (default: this repo)")
    parser.add_argument("--apply", action="store_true", help="make the move when it is lawful")
    parser.add_argument("--no-fetch", action="store_true", help="read the cached remote ref")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)

    import datetime
    repo = Path(args.repo)
    read_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not (repo / ".git").exists() and not _out(_git(repo, "rev-parse", "--git-dir")):
        print(f"NOT RUN -- {repo} is not a git repository")
        return 2

    binding_rows, binding_reason = read_binding(repo)
    facts = gather(repo, fetch=not args.no_fetch, read_at=read_at,
                   binding_rows=binding_rows)
    decision = assess(facts)

    before = facts.get("head")
    after = before
    moved = "no-move"
    if decision["action"] == "fast-forward" and args.apply:
        merge = _git(repo, "merge", "--ff-only", f"{facts['remote']}/{facts['branch']}")
        after = _out(_git(repo, "rev-parse", "HEAD")) or before
        if merge.returncode != 0:
            moved = f"fast-forward FAILED rc={merge.returncode}: {merge.stderr.strip()}"
            decision = {"action": "refuse", "reasons": [moved]}
        elif after != facts["remote_tip"]:
            moved = f"fast-forward moved HEAD to {after[:8]}, not the remote tip"
            decision = {"action": "refuse", "reasons": [moved]}
        else:
            moved = f"fast-forward {before[:8]} -> {after[:8]}"

    payload = {
        "read_at": read_at,
        "repo": facts["repo"],
        "binding_rows": binding_rows,
        "binding_reason": binding_reason,
        "before": before,
        "after": after,
        "remote_tip": facts.get("remote_tip"),
        "behind": facts.get("behind"),
        "local_only": facts.get("local_only"),
        "dirty": facts.get("dirty"),
        "loaded": facts.get("loaded"),
        "action": decision["action"],
        "reasons": decision.get("reasons", []),
        "move": moved,
        "applied": bool(args.apply),
    }
    receipt_note = write_receipt(receipt_path(repo), payload)
    payload["receipt"] = receipt_note

    if args.json:
        print(json.dumps(payload, indent=1, sort_keys=True))
    else:
        # A dry run that printed MOVED would be a receipt for a move that never happened,
        # and the receipt file would agree with it -- so the verb names the DECISION only
        # when `--apply` was given the power to carry it out.
        if decision["action"] == "fast-forward" and not args.apply:
            verb = "WOULD MOVE"
        else:
            verb = {"level": "LEVEL", "fast-forward": "MOVED", "refuse": "REFUSED"}[decision["action"]]
        print(f"{verb} -- binding sync of {facts['repo']} at {read_at}")
        print(f"  before {str(before)[:8]}  after {str(after)[:8]}  "
              f"remote {str(facts.get('remote_tip'))[:8]}  behind {facts.get('behind')}")
        if decision["action"] == "fast-forward" and not args.apply:
            print(f"  WOULD fast-forward to {facts['remote_tip'][:8]} (no --apply)")
        elif decision["action"] == "fast-forward":
            print(f"  {moved}")
        for reason in decision.get("reasons", []):
            print(f"  REFUSED -- {reason}")
        if binding_rows:
            print(f"  binding: {len(binding_rows)} row(s) resolve into this tree")
            loaded = facts.get("loaded") or {}
            if loaded.get("reason"):
                print(f"  loaded NOT RUN -- {loaded['reason']}")
            elif loaded:
                print(f"  loaded: {loaded.get('checked', 0)} file(s) hashed against "
                      f"{str(facts.get('remote_tip'))[:8]}")
        else:
            print(f"  binding NOT RUN -- {binding_reason}")
        print(f"  {receipt_note}")

    return 3 if decision["action"] == "refuse" else 0


if __name__ == "__main__":
    sys.exit(main())
