# LENS E — Interface Topology & Command Merging

**Repo under audit:** `/root/agent-factories` (READ-ONLY)
**Revision audited:** `9ffe2114645a79bd9da81e5c1107f60cf91cb0ad` (`main`, working tree clean at read time)
**Scope:** the CLI tool surface across `tools/*.py` — chained invocations, overlapping flags/verbs, consolidation.

> **Revision is a moving target.** My first `git rev-parse HEAD` (start of audit) read
> `6bd9690d578c5bbc911537b95abe0ab0bc884c8c`; a commit landed mid-audit and every locator below was
> re-read and re-pinned against `9ffe211…`. The tree is live (a pacemaker/authoring lane is
> committing). All line numbers below were verified at `9ffe211…`, `git status --porcelain` = 0.

## Method (every count below is a measured command, not an estimate)

- `ls tools/*.py` → **32** python files; `grep -l '__main__' tools/*.py | wc -l` → **25** have a CLI entry point.
- `grep -l argparse tools/*.py | wc -l` → **24** use argparse; **1** (`tools/ledger-index.py`) hand-rolls `sys.argv`.
- `grep -l add_subparsers tools/*.py` → **4** subcommand tools: `insights.py` (10 verbs), `ledger.py` (4), `registry.py` (6), `review.py` (15).
- `grep -c '"--json"' tools/*.py` → the flag appears in **11** files.
- `python3 tools/registry.py show` → `error: argument command: invalid choice: 'show' (choose from 'validate','checks','resolve','enroll','mutate','render')`.
- `python3 tools/hygiene.py --check` → `error: unrecognized arguments: --check` (rc=2).

**Finding count: 8 defects** (2 High, 4 Medium, 2 Low) + a chained-invocation analysis and a consolidation proposal.

---

## FINDING 1 — HIGH — A law file names a `registry.py` verb that does not exist (ships to every member)

**(a) LOCATOR:** `skills/meta-factory/SKILL.md:378` (byte-twin at `TEMPLATE/SKILL.md.tmpl:325`)

**(b) VERBATIM QUOTE:**
```
| `registry/fleet.json` and `registry/factories/<slug>.json` | what each factory IS in a form a peer can read — its chat, its lanes, the substrates it owns, the cron prefixes it claims | `HQ` (the fleet manifest) and the lane that enrolls (`tools/registry.py enroll`) | read-only, via `tools/registry.py resolve` / `show` |
```

**(c) DEFECT ANALYSIS:** The read column names two verbs, `resolve` and `show`. `tools/registry.py`
defines exactly six subcommands — `validate`, `checks`, `resolve`, `enroll`, `mutate`, `render`
(`tools/registry.py:2282,2285,2287,2296,2309,2332`) — and **no `show`**. Running it proves the dead
pointer: `python3 tools/registry.py show` → `registry.py: error: argument command: invalid choice:
'show'`. A reader who follows the law reaches nothing. This is the exact rot class the same file
warns about at `:261` ("a raw uuid written here would be a value that rots"), one layer up: here the
thing that rots is a *verb*. It is not a one-file typo — the string is in the shipped template
(`TEMPLATE/SKILL.md.tmpl:325`), so every factory bootstrapped from this repo inherits a reference to
a command that cannot run.

**(d) REMEDIATION:** Either implement the missing verb — `registry.py show <slug>` printing one
fragment plus its resolved reachability (a genuine read the `resolve`/`render` pair does not give in
one call) — or, minimally, change the text to the verbs that exist: ``via `tools/registry.py
resolve`; the generated half via `render --check` ``. Apply the same edit to
`TEMPLATE/SKILL.md.tmpl:325`. Add a gate that extracts every `tools/*.py <verb>` reference from the
law and asserts the verb is in that tool's `add_parser` set (see Finding 8's remediation — nothing
currently catches this class).

---

## FINDING 2 — HIGH — `--stdout` means "also write" in one census and "do not write" in two others

**(a) LOCATOR:** `tools/instrument_census.py:358`, `tools/kit_census.py:559`, `tools/kit_names.py:394`

**(b) VERBATIM QUOTE:**
```
tools/instrument_census.py:358:    ap.add_argument("--stdout", action="store_true", help="also print the artifact")
tools/kit_census.py:559:    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
tools/kit_names.py:394:    ap.add_argument("--stdout", action="store_true")
```

**(c) DEFECT ANALYSIS:** Three census tools share the flag name `--stdout` with opposite write
semantics. In `instrument_census.py` the artifact is written **unconditionally** (`:372` refusal
path, `:392` success path `out.write_text(body, encoding="utf-8")`) and `--stdout` only *adds* a
print (`:379`, `:395`) — so the file is (over)written either way. In `kit_census.py:574` and
`kit_names.py:410` the code is `if args.stdout: print(...); return 0` — it returns **before** the
write, so `--stdout` suppresses the on-disk artifact entirely. An operator who runs
`… --stdout` to "just look" will, in `instrument_census`, silently overwrite the published evidence
artifact under `evidence/` (default path `evidence/instrument-census-<slug>-<date>.md`, `:370`) —
while in the sibling tools the identical flag protects it. Same token, opposite side effect.

**(d) REMEDIATION:** Fix one shared contract and make all three obey it. Recommended: `--stdout` =
"print only, never write" (the `kit_census`/`kit_names` behaviour) and add `--out -` (or a
`--dry-run`) for the path case; then change `instrument_census.py` so the `write_text` calls are
guarded by `if not args.stdout`. At minimum, give `kit_names.py:394` the missing `help=` so the
divergence is at least visible in `-h`. State the contract once in `docs/instruments/kit.md` and
reference it from all three.

---

## FINDING 3 — MEDIUM — `hygiene.py --audit --clean` deletes files while `--audit` says "without removing"

**(a) LOCATOR:** `tools/hygiene.py:1466`, `:1467`, `:1503`, `:1509`

**(b) VERBATIM QUOTE:**
```
1466:    parser.add_argument("--audit", action="store_true", help="Audit without removing")
1467:    parser.add_argument("--clean", action="store_true", help="Reap stale scratch items")
1503:    if not args.audit and not args.clean:
1509:    dry_run = args.audit and not args.clean
```

**(c) DEFECT ANALYSIS:** `--audit` and `--clean` are two mode flags that are **not** in an
`add_mutually_exclusive_group`. `dry_run` is computed as `args.audit and not args.clean` (`:1509`),
so passing both yields `dry_run = False` and the reaper **deletes**, even though `--audit`'s own
help promises "Audit without removing". The contradictory invocation is silently resolved in favour
of destruction instead of being refused. A second, smaller defect rides the same lines: `--audit`
is also the implicit default (`:1503`), so the flag carries no information — the tool audits whether
or not you pass it.

**(d) REMEDIATION:** Put the two in `parser.add_mutually_exclusive_group()` so `--audit --clean` is
refused with argparse's exit 2, or (if a precedence is genuinely wanted) keep the precedence but
reword `--audit`'s help to "audit unless `--clean` is also given". Given `--audit` is already the
default, prefer deleting the flag's redundancy: document "no flag = audit", keep `--clean` as the
only mode switch.

---

## FINDING 4 — MEDIUM — `roadmap.py --cadence` is a silent alias of `--audit` (two help texts, one code path)

**(a) LOCATOR:** `tools/roadmap.py:234`, `:235`, `:246`

**(b) VERBATIM QUOTE:**
```
234:    parser.add_argument("--audit", action="store_true", help="Audit product artifact existence")
235:    parser.add_argument("--cadence", action="store_true", help="Audit product delivery cadence status")
246:    if args.audit or args.cadence:
```

**(c) DEFECT ANALYSIS:** The two flags advertise *different* audits but collapse to one branch
(`:246` `if args.audit or args.cadence:`), over one precomputed `data = audit_products(REPO_ROOT)`
(`:240`). `--cadence` adds nothing `--audit` does not already do, and neither flag changes what is
computed — so a reader is invited to believe `--cadence` selects a cadence-specific check that does
not exist. This is not hypothetical duplication: `tools/audit.py:1287` invokes
`roadmap.py --audit` while the weekly cron row (`docs/factory-registry.md:382`) invokes
`roadmap.py --cadence` — two names for one behaviour, propagating the fiction into the schedule.

**(d) REMEDIATION:** Keep one verb. Delete `--cadence` and update the cron row
(`docs/factory-registry.md:382`) to `--audit`; or, if a cadence-only audit is genuinely wanted,
implement it as a distinct predicate instead of aliasing. Either way the two call sites
(`audit.py:1287`, the cron) must name the same flag.

---

## FINDING 5 — MEDIUM — Cross-script flag-name collisions: `--home` and `--stamp` each mean two unrelated things

**(a) LOCATOR:** `tools/brain_metrics.py:457`, `tools/compaction_rate.py:203`, `tools/review.py:2098`;
`tools/audit.py:2669`, `tools/review.py:2073`

**(b) VERBATIM QUOTE:**
```
tools/brain_metrics.py:457:    ap.add_argument("--home", default=os.path.expanduser("~/.opencrabs/profiles/ops"),
tools/compaction_rate.py:203:    ap.add_argument("--home", default=os.path.expanduser("~/.opencrabs/profiles/ops"))
tools/review.py:2098:    p_codify.add_argument("--home", default=None, help="The file+section it landed in, or where it was routed")
tools/audit.py:2669:    parser.add_argument("--stamp", action="store_true", help="Record a run row only (no artifact; does not satisfy the report step)")
tools/review.py:2073:    p_close.add_argument("--stamp", action="store_true", help="Recompute the cadence stamp at close")
```

**(c) DEFECT ANALYSIS:** Two flag names are overloaded across scripts with **incompatible types and
meanings**:
- `--home` is a *profile root directory* in `brain_metrics.py` / `compaction_rate.py` (default
  `~/.opencrabs/profiles/ops`) but a *documentation home — "the file+section it landed in"* in
  `review.py codify`. Any wrapper that forwards `--home` between them passes a filesystem path where
  a file+section string is expected.
- `--stamp` is *"write a telemetry run row"* in `audit.py` but *"recompute the cadence boundary
  stamp"* in `review.py close`. Same token, unrelated side effects.
This is the class the lens asks for directly ("overlapping flags … across different scripts"); it
makes the flag namespace non-compositional and is invisible in each tool's own `-h`.

**(d) REMEDIATION:** Disambiguate by renaming: `--profile-home` (or `--profile`) for
`brain_metrics.py`/`compaction_rate.py`, and `--landed-in` (or `--codify-home`) for
`review.py codify`; `--run-row`/`--stamp-run` for `audit.py`, `--recompute-stamp` for
`review.py close`. If renaming is too disruptive, add a repo-wide convention line to
`ONTOLOGY.md`: a bare `--home` is reserved for the profile root, and no other meaning may reuse it.

---

## FINDING 6 — MEDIUM — A documented trigger command uses a flag `hygiene.py` does not define

**(a) LOCATOR:** `docs/proposals/01-cron-gated-goal-pipeline.md:113`

**(b) VERBATIM QUOTE:**
```
| **Meta-Factory** | `python3 tools/hygiene.py --check` | `exit_non_zero` | Dispatches workspace cleanup goal if stale scratch files exceed threshold. |
```

**(c) DEFECT ANALYSIS:** `tools/hygiene.py`'s parser defines `--audit`, `--clean`, `--scratch-glob`,
`--namespace`, `--grace-minutes`, `--require-committed` — and no `--check`. The documented trigger
therefore cannot fire: `python3 tools/hygiene.py --check` exits **rc=2** with
`hygiene.py: error: unrecognized arguments: --check`, and an `exit_non_zero` trigger would read
that usage error as "the tree is dirty" on every tick. The intended flag is `--audit` (the default),
which exits non-zero on a dirty tree. The proposal is orphaned — `grep` finds no live reference to
`01-cron-gated-goal-pipeline` anywhere in `docs/`, `skills/`, `registry/` or `tests/` — which is
why the drift went unnoticed.

**(d) REMEDIATION:** Change `--check` → `--audit` on this line; and either promote the proposal into
live law or mark it explicitly retired at the top, so a reader does not copy a non-runnable
command into a cron. (A `--check` alias is *not* the fix: `--check` and `--audit` would then be a
second name for one behaviour, the Finding-4 defect.)

---

## FINDING 7 — LOW — `synthesize_insights.py --audit` names a caller that never calls it

**(a) LOCATOR:** `tools/synthesize_insights.py:407`

**(b) VERBATIM QUOTE:**
```
    parser.add_argument("--audit", action="store_true", help="Audit mode for CI/audit.py")
```

**(c) DEFECT ANALYSIS:** The help claims the flag exists for `audit.py`. `audit.py` never invokes
the tool with `--audit`; it runs the *test* instead — `gates_to_run.append([sys.executable, "-m",
"pytest", "tests/test_synthesize_insights.py"])` (`tools/audit.py:2045-2046`). The flag's real
consumer is the weekly cron (`docs/factory-registry.md:377`, `factory-insights-weekly …
tools/synthesize_insights.py --audit`). A help string that names a caller which does not call it is
precisely the "advertised interface is not the real interface" defect this tool's own gate
(`tests/test_synthesize_interface.py`, header "the module advertised a capability it does not
have") was written to prevent — but that gate only diffs the docstring usage block against
`add_argument` names (`:67` `PARSER_FLAG`), so a false claim *inside* `help=` is un-gated.

**(d) REMEDIATION:** Reword to `help="gate mode: print a one-line clean verdict and exit (used by
the factory-insights-weekly cron)"`. Optionally extend `tests/test_synthesize_interface.py` to
assert the help text names a real caller, closing the same class for every tool.

---

## FINDING 8 — LOW — `ledger-index.py` is the odd dispatch style out, and its own docstring omits a verb it implements

**(a) LOCATOR:** `tools/ledger-index.py:30-38` (docstring `Commands`) and `:342` (`if cmd == "path":`)

**(b) VERBATIM QUOTE:**
```
30:Commands
32:  build                 (default) rebuild the index from the ledgers
33:  find TEXT             full-text search over `detail`
34:  subject S             every row whose subject is S, across all ledgers
35:  touching TEXT         every row with a ref whose VALUE contains TEXT
36:  check                 prove the index agrees with a plain scan of the JSONL
...
342:    if cmd == "path":
```

**(c) DEFECT ANALYSIS:** Two small drifts. (i) `ledger-index.py` is the **only** CLI in `tools/`
that hand-rolls `sys.argv` dispatch (`:337-357`) instead of argparse — measured: 25 tools have
`__main__`, 24 use argparse, this is the one exception — so it has no `-h`, no `--help`, and no
argument validation, unlike its four siblings (`ledger.py`, `insights.py`, `registry.py`,
`review.py`). (ii) Its docstring's `Commands` block lists five verbs but the code also implements
`path` (`:342`, prints `INDEX`), which is documented nowhere — a reader cannot discover the verb
that answers "where is the index".

**(d) REMEDIATION:** Add `  path                  print the index file's location` to the `Commands`
block, and migrate the dispatch to argparse for parity with the other four subcommand tools (which
also buys `-h` and a uniform `invalid choice` error). This is cheap and removes the only
non-conforming CLI in the surface.

---

## CHAINED-INVOCATION ANALYSIS (lens target 1)

Three chains are mandated as immediate-succession sequences. Two carry a redundant leg.

**Chain C1 — `ledger.py append` → `ledger.py verify`** (mandated twice):
`skills/meta-factory/SKILL.md:424` `"Stamp \`evidence/ledger.jsonl\`, run \`tools/ledger.py verify\`,
and commit/push to \`origin/main\`."` and `docs/best-practices.md:572` `"Ledger Stamp & Commit:
Stamp \`evidence/ledger.jsonl\`, run \`tools/ledger.py verify\`,"`. The pair is **partially
redundant**: `skills/meta-factory/state.md:148` records that `"tools/ledger.py append --event close"
runs the same sequence predicate `verify` runs — one predicate, two call sites"`. So for a `close`
the second command re-runs a predicate the first already ran; only non-`close` events (`run`,
`score`) genuinely need the follow-up. **Consolidation:** add `ledger.py append --verify` that
re-runs the predicate over the just-written row inline, collapsing the two-command ritual (present
in two law files) into one for the common case.

**Chain C2 — `registry.py enroll` → `render` → `validate`** (a three-command ritual):
`TEMPLATE/BOOTSTRAP.md:499-501`
```
python3 tools/registry.py enroll <slug>
python3 tools/registry.py render
python3 tools/registry.py validate
```
These are always run in immediate succession. The ordering implies `validate` depends on `render`'s
output, but it does not: `cmd_validate` (`tools/registry.py:2068-2086`) reads only *fragments* via
`fragment_paths`, never the generated `registry/index.json` that `render` writes. So the sequence
carries a false dependency, and a lane that forgets `render` is caught only later by the drift gate
(`tests/test_registry.py`). **Consolidation:** `registry.py enroll <slug> --render --validate`
(a `--render`/`--validate` post-step on `enroll`), or a `registry.py sync` that does all three.

**Chain C3 — `audit.py` → `hygiene.py --audit` (and `roadmap.py --audit`)**:
`tools/audit.py:1281` spawns `tools/hygiene.py --audit --namespace hygiene_namespace(repo_root)` as
gate 7, and `:1287` spawns `tools/roadmap.py --audit` as gate 8. The measurement procedure
*separately* mandates `python3 tools/hygiene.py --audit` as the closing invariant
(`docs/measurement-procedure.md:407`). Net effect: `hygiene.py --audit` runs **twice per run**, and
the two invocations differ in namespace semantics — the gate passes `--namespace` explicitly
(`audit.py:1282`, precisely because "the tool's own default follows its RUN SITE", `audit.py:1270`),
while the law's bare `hygiene.py --audit` uses the default. The law therefore prescribes the
*unsafe* form of an invocation its own tool warns against (#174). **Remediation:** the law's closing
invariant should pass `--namespace` (or `--require-committed` for the run's own artifacts) exactly
as the gate does; and the two hygiene invocations should be reconciled so the run does not audit
twice with two different scopes.

---

## PROPOSED CONSOLIDATED COMMAND SYNTAX (lens target 3)

The surface has four subcommand dispatchers (`ledger`, `insights`, `registry`, `review`), a
hand-rolled one (`ledger-index`), and ~20 flag-only tools, sharing a `--json` convention (11 files)
but no shared read-verb, output, or write-guard convention. Concretely:

1. **One read verb.** `ledger.py tail`, `insights.py list`, `review.py status`, and the *ghost*
   `registry.py show` (Finding 1) are four names for "print my store's current state". Standardise
   on `show` (which the law already expects) and implement it where missing: `registry.py show
   [<slug>]`, keep `ledger.py tail` as an alias of `show --n N`. This turns Finding 1 from a
   doc-edit into a real, uniform interface.

2. **One output contract.** `--json` (already in 11 tools) plus a single defined
   `--out PATH` / `--stdout` semantic (Finding 2): `--stdout` = print only, never write;
   `--out -` = stdout. Apply to `instrument_census.py`, `kit_census.py`, `kit_names.py`,
   `kit_surfaces.py` (which today has `--json` but no `--out`/`--stdout` at all).

3. **One census dispatcher.** `instrument_census.py`, `kit_census.py`, `kit_names.py` and
   `kit_surfaces.py` are four near-identical "scan the fleet and publish a dated artifact under
   `evidence/`" tools sharing `--out`/`--stdout`/`--json`. Collapse behind `census.py
   --scope kit|names|instrument|surfaces`, keeping the four modules as the scope implementations.

4. **Write-guard convention.** Every write verb should self-verify or offer to: `ledger.py append
   --verify` (Chain C1), `registry.py enroll --render --validate` (Chain C2). This removes the
   multi-command rituals that two law files currently mandate.

5. **A gate for the law→tool verb binding.** Add a check that extracts every `tools/<name>.py
   <verb>` reference from `skills/`, `docs/` and `TEMPLATE/` and asserts the verb is in that tool's
   `add_parser` set. Findings 1 and 6 are both instances of a law surface naming a command that does
   not exist, and **no current gate catches the class** (`grep -rn "registry.py show" tests/` → 0
   hits; the only verb-shaped gates are per-tool behaviour tests).

---

## SUMMARY

**8 findings** across the `tools/` CLI surface: 2 High, 4 Medium, 2 Low, plus a three-chain
invocation analysis and a consolidation proposal.

**Single most severe:** Finding 1 — `skills/meta-factory/SKILL.md:378` (and its shipped twin
`TEMPLATE/SKILL.md.tmpl:325`) tells every reader to run `tools/registry.py show`, a verb that does
not exist (`registry.py: error: argument command: invalid choice: 'show'`); the law ships a dead
command pointer to every factory bootstrapped from this repo.

**Commands/reads that produced the measurements:** `git rev-parse HEAD`;
`ls tools/*.py`; `grep -l '__main__' tools/*.py | wc -l` (25);
`grep -l argparse tools/*.py | wc -l` (24); `grep -l add_subparsers tools/*.py` (4);
`grep -c '"--json"' tools/*.py` (11 files);
`grep -n 'add_parser(' tools/{insights,ledger,registry,review}.py`;
`python3 tools/registry.py show` (invalid choice, rc from argparse error);
`python3 tools/hygiene.py --check` (rc=2, unrecognized);
`grep -n '"--stdout"' tools/{instrument_census,kit_census,kit_names}.py`;
`grep -n '"--home"' tools/{brain_metrics,compaction_rate,review}.py`;
`grep -n '"--stamp"' tools/{audit,review}.py`;
`grep -n '"--audit"\|"--clean"\|dry_run = args.audit' tools/hygiene.py`;
`grep -n '"--cadence"\|if args.audit or args.cadence' tools/roadmap.py`;
`sed -n '499,502p' TEMPLATE/BOOTSTRAP.md`; `sed -n '30,38p;342p' tools/ledger-index.py`;
`grep -n "run \`tools/ledger.py verify\`" skills/meta-factory/SKILL.md docs/best-practices.md`;
`grep -n "tools/hygiene.py\", \"--audit\"" tools/audit.py`.
