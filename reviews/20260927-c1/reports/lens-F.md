# LENS F — Tool Implementation Quality & Exit Contracts

**Repo under audit:** `/root/agent-factories` (READ-ONLY — nothing created, modified or deleted)
**Revision audited:** `33ca8d8464692721ef06de6af3c16a25d435836b` (`main`)
**Scope:** source of `tools/*.py` (32 files, 25 with a CLI entry point) and `tests/*.py` (89 files) — exit-code determinism, shell hygiene, atomic journaling.

> **The tree is live and HEAD moved mid-audit.** My first `git rev-parse HEAD` read
> `6bd9690d578c5bbc911537b95abe0ab0bc884c8c`; by the end it read `33ca8d8…` (other lens lanes were
> recording reports). `git diff --stat 6bd9690 33ca8d8 -- tools/ tests/` shows **no** change to
> `tools/` or `tests/` in that window (the commits touched only `docs/`, `evidence/`, `reviews/`), so
> every locator below is valid at both revisions. Each locator was re-read and re-pinned at
> `33ca8d8…` immediately before this report was written.

> **METHOD / READ-PATH NOTE (important for reproducing the quotes).** In this session the plain-text
> rendering of file content is *unreliable*: `sed`/`grep`/`cat`/`python print` of a line can display
> an identifier differently from the file's true bytes. I proved this with a hash test — the raw bytes
> of `tools/publish.py:399` hash (md5, with `\n`) to `3ccfeb3c…`, which equals the md5 of the string
> **`        branch=args.branch,`** built from *numeric* character codes, while `printf '        branch=args.branch,\n'`
> — and every `sed`/`cat`/`print` of that line — hashes to a *different* value. **Every verbatim quote
> below was therefore extracted at byte level** (`sed -n 'Np' FILE | xxd`, decoding the hex column, or
> `python3` byte lists) and cross-checked against the file's `md5sum`. Quote text below is the decoded
> hex = the file's true content. Counts are printed by the commands named beside them.

**Finding count: 8** (3 High, 3 Medium, 2 Low) + 2 scope/coverage notes.

---

## FINDING 1 — HIGH — Shell hygiene: neither shell script in the repo sets `-e`; the lens law requires `set -euo pipefail`

**(a) LOCATORS:** `tools/box/oc_questions_push.sh:56`; `tools/sigpipe_threshold.sh:39`

**(b) VERBATIM QUOTES:**
```
tools/box/oc_questions_push.sh:56
set -uo pipefail
```
```
tools/sigpipe_threshold.sh:39
set -o pipefail                      # the guard under test; the defect needs BOTH this and a pipe
```

**(c) DEFECT ANALYSIS:** Lens F's own law is explicit — `docs/review-lenses.md:94`:
> `  2. **Shell Hygiene:** Shell scripts must enforce strict error trapping (`set -euo pipefail`), quote variable expansions, and avoid non-portable constructs.`

Both scripts omit `-e`, and `sigpipe_threshold.sh` also omits `-u`. This is not a theoretical gap:
`oc_questions_push.sh` guards only ~6 commands with `|| exit N` (`:248`, `:256`, `:276` …) and lets
every other command fail silently — `sleep "$SETTLE"` (`:74`), the `ls … | wc -l` count (`:76`),
the `echo`s, and the `md5sum`/`find` pipelines inside `tree_digest()`/`fingerprint()` (`:103`, `:118`).
A failed `find` or `md5sum` inside those pipelines still yields a *value* (an empty or partial digest),
and `pipefail` cannot help because `-e` is absent, so the digest comparison can compare two wrong
digests and print `push: ok` (`:287`). This is a **measured** population, not a sample: `find . -name
'*.sh' -not -path './.git/*'` returns exactly **2** files, both in `tools/`, none in `TEMPLATE/` — so
**100 %** of the repo's shell scripts violate the law. (`sigpipe_threshold.sh` is a test harness, but
the law is unconditional; its `run_row` loop at `:58-63` also runs unguarded.)

**(d) REMEDIATION:** Add `-e` (and `-u`) to both: `set -euo pipefail`. For `oc_questions_push.sh`, the
one site that *reads* a non-zero status must be rewritten so `-e` does not abort on it — the render
call at `:194-195` (`"$CANON_CLI" publish …` then `rc=$?`) must become an explicit test, e.g.
`if ! "$CANON_CLI" publish --json >/dev/null 2>"$stage/render.err"; then rc=1; else rc=0; fi`.
`-u` requires auditing the `${VAR:-default}` sites (`:60-69` already use them) and the array expansion
`"${found[@]}"` (`:170`), which is safe under `-u` only with `${found[@]:-}`.

---

## FINDING 2 — HIGH — `audit.py` masks a failed ledger stamp with exit `0`

**(a) LOCATOR:** `tools/audit.py:2922` (with the return at `:2924`)

**(b) VERBATIM QUOTES:**
```
tools/audit.py:2922
            print(f"Failed to stamp ledger: {res.stderr.strip()}", file=sys.stderr)
```
```
tools/audit.py:2924
    return 0 if (healthy is None or healthy) else 1
```

**(c) DEFECT ANALYSIS:** The `--report` and `--stamp` steps are a contract: argparse help for
`--report` reads *"Write the dated report in evidence/scores/ AND record its telemetry run row"*
(`:2667`). The run row is written by a child process (`stamp_cmd` → `tools/ledger.py append`,
`stamp_cmd` built at `:2905`, run at `:2918`).
When that child fails, `audit.py` prints the failure to stderr (`:2922`) and then **falls through to
`:2924`, which returns 0 whenever the gates are healthy** (`healthy is None or healthy`). A caller that
reads only the exit code records a *successful* report step whose run row was never stamped — the exact
"soft error masked by exit 0" that lens F check #1 forbids (`docs/review-lenses.md:93`). No test covers
this path: `grep -rn "Failed to stamp\|stamp ledger" tests/` returns **0** hits.

**(d) REMEDIATION:** Capture the stamp result and fold it into the exit, e.g.
`stamp_ok = res.returncode == 0` … `return 0 if (healthy is None or healthy) and stamp_ok else 1`, or
return a **distinct** code (e.g. `4`) naming the failed stamp so it cannot be confused with a gate
failure (`1`). Add a gate that runs `audit.py --report` with `tools/ledger.py` forced to fail and
asserts a non-zero exit.

---

## FINDING 3 — HIGH — Atomic journaling: `review.py` writes its cycle state, report and receipt with no lock, no temp file and no fsync

**(a) LOCATORS:** `tools/review.py:901`, `tools/review.py:1157`, `tools/review.py:1169`

**(b) VERBATIM QUOTES:**
```
tools/review.py:901
    with open(state_file, "w", encoding="utf-8") as f:
```
```
tools/review.py:1157
    report_file.write_text(body + "\n", encoding="utf-8")
```
```
tools/review.py:1169
    with open(index_file, "a", encoding="utf-8") as f:
```

**(c) DEFECT ANALYSIS:** Lens F check #3 (`docs/review-lenses.md:95`): *"Tools performing state changes
must write their journal or ledger entry atomically before or alongside the mutation."* `review.py` is
the tool that records review reports and mutates the cycle's authoritative `state.json`. Measured:
`grep -c flock tools/review.py` → **0**; `fsync` → **0**; `os.replace` → **0**; `tempfile` → **0**.
`save_state` (`:878`) writes `state.json` with a **truncating** `open(state_file, "w")` + `json.dump`
(`:901-902`); `cmd_record` (`:1127`) writes the report with `write_text` (`:1157`) and appends the
receipt line to `review-index.log` with a plain `open(…, "a")` and **no flush/fsync** (`:1169`). A crash
or kill between `open()` truncation and the completed write leaves a half-written `state.json` — the one
outcome the repo's *own* reasoning condemns: `ledger.py:1891-1900` builds the new text beside the file
and swaps it with `os.replace` after `fsync`, and `insights.py:736-742` does the same, both with the
comment *"the replace is ATOMIC"*. `review.py` is the outlier on the very surface those instruments
protect. `cmd_record` also writes the report and the index line **before** it can fail on `save_state`
(`:1187`), so the three surfaces can be left mutually inconsistent (report on disk, `state.json`
unchanged).

**(d) REMEDIATION:** Mirror the ledger/insights pattern: write to a sibling temp, `fh.flush()` +
`os.fsync(fh.fileno())`, then `os.replace(tmp, state_file)` (and the same for `report_file`). Append the
index line with an explicit `f.flush(); os.fsync(f.fileno())`. Optionally hold the same
`fcntl.flock(LOCK_EX)` the ledger uses so two lanes cannot interleave a state rewrite.

---

## FINDING 4 — MEDIUM — `audit.py` silently drops malformed ledger rows that `ledger.py` treats as fatal

**(a) LOCATORS:** `tools/audit.py:426-428` and `tools/audit.py:546-548` (contrast `tools/ledger.py:574`)

**(b) VERBATIM QUOTES:**
```
tools/audit.py:426-428
                    events.append(json.loads(line))
                except Exception:
                    pass
```
```
tools/ledger.py:574
            sys.exit(f"ledger line {n} is not JSON: {exc}")
```

**(c) DEFECT ANALYSIS:** Two readers of the same file (`evidence/ledger.jsonl`) disagree on a malformed
row. `ledger.py`'s own reader refuses **loudly** (`sys.exit(f"ledger line {n} is not JSON: …")`), but
`audit.py`'s `parse_ledger` (`:375`) — and the cadence reader at `:546-548` — swallow the exception and
`pass`. The audit then computes First-Pass Yield, change-fail rate, lead times and cadence over the
*surviving* rows without stating that rows were dropped. This is a silent population shrink, and it
contradicts a principle the repo states in its own words — `ledger.py:1944-1946`: *"a truncated log
window is not an empty one"*. An unreadable row is a fact about the ledger, not a row to be forgotten.

**(d) REMEDIATION:** Count skipped lines and either (a) refuse like `ledger.py` (match the loud path), or
(b) print a loud, unconditional line the audit's own "the population is PRINTED" rule demands — e.g.
`ledger: N unparseable line(s) skipped` — and surface `N` in the JSON payload so a consumer cannot read a
shrunk population as a clean one.

---

## FINDING 5 — MEDIUM — `audit.py --json` silently ignores `--report` / `--stamp`

**(a) LOCATORS:** `tools/audit.py:2770` and `tools/audit.py:2786` (blocks at `:2878`, `:2887`)

**(b) VERBATIM QUOTES:**
```
tools/audit.py:2770
    if args.json:
```
```
tools/audit.py:2786
        return 0 if (healthy is None or healthy) else 1
```

**(c) DEFECT ANALYSIS:** The three flags are independent argparse options with **no** mutual-exclusion
group (`grep -n "mutually_exclusive" tools/audit.py` → **0** hits). The `if args.json:` branch prints the
JSON and **returns at `:2786`, before** the `if args.report or args.output:` block (`:2878`) and the
`if args.stamp or args.report:` block (`:2887`). So `audit.py --json --report` prints JSON and writes
**no report file and no run row**, with no diagnostic. A requested side effect silently does nothing —
the interface equivalent of a masked error.

**(d) REMEDIATION:** Put `--json` in an `argparse` mutually-exclusive group with
`--report`/`--stamp`/`--output` (argparse then errors on the combination), **or** move the JSON emit so
the report/stamp blocks still execute before the return. Either way, the combination must not be a
silent no-op.

---

## FINDING 6 — MEDIUM — Exit-code collapse: no failure path in the tool surface exits a *distinct* non-zero code

**(a) LOCATOR:** `tools/ledger.py:574` (representative; the file carries 38 `sys.exit(…)` sites)

**(b) VERBATIM QUOTE:**
```
tools/ledger.py:574
            sys.exit(f"ledger line {n} is not JSON: {exc}")
```

**(c) DEFECT ANALYSIS:** Lens F check #1 (`docs/review-lenses.md:93`): *"Failures must exit distinct
non-zero codes."* An AST scan of all `tools/*.py` (`python3` walk over `sys.exit` calls) reports
`int-codes=[]` for **every** file — **no tool anywhere calls `sys.exit(<int>)`**. `sys.exit(<str>)` exits
**1** for *every* distinct refusal class. `grep -c "sys.exit(" tools/ledger.py` → **38**; all pass a
message (string or f-string), so schema violations, sequence violations, identity violations and
stale-refusals are indistinguishable to a caller reading only `$?`. A few tools do better in `main()`
(`audit.py` returns `2`/`3`; `review.py` returns `1`/`2`/`3`), but the *body* of the refusal surface does
not. **Note the internal contradiction:** `docs/best-practices.md:617` asks only for *"deterministic
exit codes (`0` vs `1`)"*, which the tools meet — so the repo's own docs disagree with the lens
criterion. The criterion is nonetheless the one lens F is judged by, so the gap is real.

**(d) REMEDIATION:** Define named exit constants per refusal class (`ledger.py` already names
`LOCK_HELD_EXIT_CODE = 3` in `audit.py`) and pass them: e.g. `EXIT_SCHEMA = 10`, `EXIT_SEQUENCE = 11`,
`EXIT_IDENTITY = 12`, then `sys.exit(EXIT_SEQUENCE)`. **Or** amend `docs/review-lenses.md:93` to the
`0`-vs-`1` bar `best-practices.md:617` already states — but pick one, because the two surfaces currently
mandate different things.

---

## FINDING 7 — LOW — `hygiene.py --clean` reports the same stranded violations that fail `--audit`, then exits 0

**(a) LOCATOR:** `tools/hygiene.py:1602-1606`

**(b) VERBATIM QUOTES:**
```
tools/hygiene.py:1602-1603
    if violations:
        print(f"warning: {len(violations)} stranded item(s) in the working tree:", file=sys.stderr)
```
```
tools/hygiene.py:1606
    return 0
```

**(c) DEFECT ANALYSIS:** Under `--audit`, the same `violations` set returns `1` (`:1588`). Under
`--clean`, after reaping, the identical violations are downgraded to a `warning:` line and the process
returns `0` (`:1606`). A cron or wrapper reading `$?` cannot tell a clean tree from one that still
carries stranded items.

**(d) REMEDIATION:** If clean mode's contract is to leave a clean tree, `return 1 if violations else 0`
(matching the audit path); if best-effort is intended, state it in the `--clean` help text and document
the exit contract so the two modes are not read as equivalent.

---

## FINDING 8 — LOW — `registry_render.py` writes its three state surfaces non-atomically

**(a) LOCATOR:** `tools/registry_render.py:1161-1163`

**(b) VERBATIM QUOTES:**
```
tools/registry_render.py:1161
        MD_PATH.write_text(markdown, encoding="utf-8")
```
```
tools/registry_render.py:1162
        INDEX_PATH.write_text(index_text, encoding="utf-8")
```
```
tools/registry_render.py:1163
        STATE_PATH.write_text(snapshot_text, encoding="utf-8")
```

**(c) DEFECT ANALYSIS:** The generated `state` snapshot (and the index/markdown siblings) are written
with truncating `write_text` calls — no temp file, no `os.replace`, no `fsync`. A crash mid-write leaves
a truncated `STATE_PATH`, the same defect class as Finding 3. Same law (`docs/review-lenses.md:95`).

**(d) REMEDIATION:** Apply the temp + `fsync` + `os.replace` pattern used at `ledger.py:1898-1900` /
`insights.py:736-742` to each of the three writes.

---

## SCOPE / COVERAGE NOTES (brief premises that do not match the repo)

1. **The corpus manifest says `tests/` holds "89 pytest gate files" (`CORPUS.md`).** Measured:
   `ls tests/*.py | wc -l` → **89** total Python files, of which **84** are `test_*.py` and **5** are
   non-test helpers (`gate_fixtures.py`, `gate_registry.py`, `hook_installation.py`, `ledger_boundary.py`,
   `rework_table.py`). Only **40** of the `test_*.py` files declare pytest-style `def test_` functions;
   **66** carry a `__main__` block and are invoked as scripts (`python3 tests/test_x.py`, each with its
   own `main()` returning 0/1). So "pytest gate files" over-counts both the gate population (89 → 84)
   and the pytest-collected population (89 → 40). Minor premise drift; it does not change the findings.
2. **Lens F's "shell hygiene" target has a population of exactly 2 files.** `find` over the repo
   (excluding `.git`) returns `tools/box/oc_questions_push.sh` and `tools/sigpipe_threshold.sh`, nothing
   in `TEMPLATE/`. Both violate the law (Finding 1) — a whole-population finding, not a sample.

---

## SUMMARY

**8 findings: 3 High, 3 Medium, 2 Low.** The single most severe is **Finding 3** — `review.py`, the
tool that mutates the review cycle's authoritative `state.json`, writes its state, its report and its
receipt index with **zero** atomicity primitives (`flock`/`fsync`/`os.replace`/`tempfile` all measure 0),
so a crash can leave a truncated `state.json` on the one surface `ledger.py` and `insights.py` go out of
their way to protect with temp+fsync+replace. Close behind: **Finding 2**, where `audit.py` prints
`Failed to stamp ledger:` and then returns **0** (`:2922`→`:2924`), a soft error masked by exit 0; and
**Finding 1**, where both of the repo's shell scripts violate the lens's own `set -euo pipefail` law.

**Commands / reads that produced the measurements** (all run at `33ca8d8…`, read-only):
`git rev-parse HEAD`; `git diff --stat 6bd9690 33ca8d8 -- tools/ tests/`; `find . -name '*.sh' -not -path
'./.git/*'` (→2); `grep -rn "set -euo pipefail\|set -e\b" --include=*.sh .` (→0); `sed -n 'Np' FILE | xxd`
for every quote (byte-level, since plain text is unreliable here — see Method note); `grep -c
"sys.exit(" tools/ledger.py` (→38); a `python3` AST walk over `tools/*.py` collecting `sys.exit` call
arguments (`int-codes=[]` for every file); `grep -c flock|fsync|os.replace|tempfile tools/review.py`
(→0,0,0,0); `grep -n "mutually_exclusive" tools/audit.py` (→0); `ls tests/*.py | wc -l` (→89);
`grep -rlE "^def test_" tests/*.py | wc -l` (→40); `grep -rl "__main__" tests/*.py | wc -l` (→66);
`grep -rn "Failed to stamp\|stamp ledger" tests/` (→0); `python3 tools/audit.py --json --no-gates`
(rc=0, 12178-byte JSON payload, `healthy=None`).
