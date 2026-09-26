# Ledger instrument review (plan 2646d31a step 14, E.1)

Produced by an independent read-only sub-agent (D.3 protocol), scoped to the TEMPLATE
copy and the TEMPLATE law. Verbatim report below; the disposition of every finding is in
ledger row n=1142 and commit 2f8c135.

---

# INDEPENDENT REVIEW OF SHIPPED INSTRUMENT: LEDGER

## 1. FACTORY-SPECIFIC ASSUMPTIONS

The shipped code in `/root/agent-factories/TEMPLATE/tools/ledger.py` (and its closure) embodies several assumptions specific to `/root/agent-factories` that break or degrade when copied into a member factory:

### 1.1 Inlined Meta-Factory Historical Exemptions
- **Severity:** BLOCKER
- **File & Line:** `TEMPLATE/tools/ledger.py:270-282`
- **Assumption / Mismatch:** The code ships with hardcoded exemptions specific to the meta-factory's early history:
  ```python
  EXEMPTIONS: list[tuple[str, str, str, str, str]] = [
      ("#6", "claim", "2026-09-12", ...),
      ("#8", "intake", "2026-09-12", ...),
      ("#8", "claim", "2026-09-12", ...),
  ]
  ```
- **What breaks in a member:** A member factory that happens to work on issue `#6` or `#8` without writing a `claim` or `intake` will have structural sequence defects silently excused by `verify` using meta-factory historical rulings (`ledger n=14`, `n=15`). While `BOOTSTRAP.md` advises clearing this list by hand, shipping it in `TEMPLATE/` directly violates the law stated in `SKILL.md` §11 (*"an exemption inherited from another factory's history excuses a defect your ledger does not have; an exemption table holds entries as factory data in its own file and never inline"*).
- **Smallest fix:** Initialize `EXEMPTIONS: list[tuple[str, str, str, str, str]] = []` in the template instrument, or load exemptions from a factory-local uncommitted/seed data file (e.g. `docs/ledger-exemptions.json`).

---

### 1.2 Lane Resolution Couples to Centralized Manifest & Telegram Topic Registry
- **Severity:** BLOCKER
- **File & Line:** `TEMPLATE/tools/ledger.py:181`, `TEMPLATE/tools/registry.py:248, 1512`
- **Assumption / Mismatch:** `session_to_role()` invokes `registry.load_fragment(path)` and indexes `chat_id = registry.FACTORY_CHATS.get(data.get("factory"))` to resolve a session ID via `registry.resolve_lane()`. `FACTORY_CHATS` is populated directly from `registry/fleet.json`.
- **What breaks in a member:** If a member factory has not yet enrolled itself into `registry/fleet.json` (or if it operates on a different chat substrate, or does not have a `registry/` tree populated identical to the meta-factory fleet manifest), `FACTORY_CHATS.get(...)` returns `None` or raises an exception. `resolve_lane` cannot bind the active `OPENCRABS_SESSION_ID` to a role card. Consequently, `session_to_role()` fails with `"session <id> matches no lane declared in N fragment(s)"`, completely blocking all ledger writes (`append` and `repair`) on the live ledger.
- **Smallest fix:** Allow a member factory to specify a local lane map fallback (e.g. `registry/local_lanes.json` or reading directly from its own local `registry/factories/<slug>.json` fragment without querying global fleet chats).

---

### 1.3 `verify --against` Assumes Specific Git Remote/Branch Topology
- **Severity:** FIX
- **File & Line:** `TEMPLATE/tools/ledger.py:321, 959-968`
- **Assumption / Mismatch:** `read_committed_rows()` loops over hardcoded refs `("origin/main", "HEAD")`, and `_read_rows_at()` executes git subprocesses assuming a git repo rooted at `REPO = Path(__file__).resolve().parent.parent` (`TEMPLATE/tools/ledger.py:64`).
- **What breaks in a member:** If a member uses default branch `master` or trunk branches other than `main` and has not pushed to `origin/main`, `read_committed_rows` falls back to `HEAD` (or fails open with a warning). If `verify --against <rev>` is called where the repo layout places `tools/` in a subdirectory other than direct child of the git root, `relative_to(REPO)` fails with `ValueError: ... is outside REPO`.
- **Smallest fix:** Determine the repo root dynamically via `git rev-parse --show-toplevel` instead of `parent.parent`, and detect the upstream default branch dynamically via `git symbolic-ref refs/remotes/origin/HEAD` before falling back to `HEAD`.

---

### 1.4 Hardcoded Assumption of Evidence Path Layout
- **Severity:** NOTE
- **File & Line:** `TEMPLATE/tools/ledger.py:73-75`
- **Assumption / Mismatch:** Defaults state surfaces to `REPO / "evidence" / "ledger.jsonl"` and `REPO / "evidence" / "subprocesses"`.
- **What breaks in a member:** Works as long as the member adheres to standard ASIF layout or sets `OC_LEDGER_PATH` / `OC_SUBPROCESS_DIR`. If a member uses a customized layout without setting environment variables, state is created under `evidence/`.
- **Smallest fix:** No fix required (design choice conforming to ASIF layout standard), provided `OC_LEDGER_PATH` remains supported.

---

## 2. LAW vs CODE AS IT NOW STANDS

### (a) Derivation of ACTOR from `OPENCRABS_SESSION_ID`
- **Verdict:** **AGREE**. Both law and code mandate derivation from `OPENCRABS_SESSION_ID` and refuse a declared actor unless it matches the derived role (with the sole exception of empty-ledger bootstrap genesis and fixtures).
- **Law Reference (`SKILL.md:547`):**
  > *"THE WRITE PATH OWNS THE ACTOR, AND THE ACTOR IS DERIVED — identity is mechanical, never declared. A row's `actor` is a derived value, read from `OPENCRABS_SESSION_ID`... resolved through the registry's own lane resolver... the tool now enforces the matrix at append, so the row is refused when it is written rather than reported later, and a `--actor` is accepted only when it AGREES with the derivation."*
- **Code Reference (`TEMPLATE/tools/ledger.py:228-234`):**
  ```python
  derived, reason = session_to_role()
  if derived:
      if declared and declared != derived:
          return None, (
              f"actor '{declared}' does not match the role this session resolves to "
              f"('{derived}') — identity is derived from OPENCRABS_SESSION_ID, not declared"
          ), "derived"
      return derived, "", "derived"
  ```

---

### (b) SETTLEMENT Procedure & Verified Row Count
- **Verdict:** **AGREE**. Both law and code assign settlement verification and receipt generation to the tool under the same lock, retiring the requirement for the author to declare `rows=<count>`.
- **Law Reference (`SKILL.md:549`, `docs/processes.md:152`):**
  > `SKILL.md:549`: *"THE SETTLEMENT RECEIPT IS THE TOOL'S, NOT THE AUTHOR'S — and this retires the self-referential count (2026-09-25... The declaration is retired, and `append --event close` now writes a second row inside the same lock: a `run` row carrying `verified_rows=N`, where N is the count the sequence check covered with the close row present."*  
  > `docs/processes.md:152`: *"Its upholding mechanism is the WRITE PATH, not a declaration by the author (2026-09-25, superseding the `rows=` gate)... `append --event close` therefore writes a second row inside the same lock — a `run` row carrying `verified_rows=N`... and the declaration, its reader, its gate, its exemption files and its boundary are retired."*
- **Code Reference (`TEMPLATE/tools/ledger.py:702-714`):**
  ```python
  if args.event == "close" and target_ledger == LEDGER:
      receipt = {
          "n": row["n"] + 1,
          "ts": now_iso(),
          "event": "run",
          "actor": args.actor,
          "subject": args.subject,
          "detail": (
              f"SETTLEMENT RECEIPT for the close row at n={row['n']} — the sequence "
              f"check ran with that row present and covered verified_rows={row['n']} "
              f"row(s) of {args.subject}, and found no problem"
          ),
      }
      with open(target_ledger, "a", encoding="utf-8") as fh:
          fh.write(json.dumps(receipt, ensure_ascii=False) + "\n")
  ```

---

### (c) Enforcing the AUTHORIZATION MATRIX
- **Verdict:** **AGREE**. Both law and code enforce the role-to-event matrix at the write path in `tools/ledger.py` rather than relying solely on post-hoc gate audits.
- **Law Reference (`SKILL.md:547`, `TEMPLATE/tools/ledger_declaration.py:46-52`):**
  > `SKILL.md:547`: *"The tool now enforces the matrix at append, so the row is refused when it is written rather than reported later..."*  
  > `ledger_declaration.py:48-50`: *"Two consumers must agree about it and neither may hold its own copy: the write path (`tools/ledger.py append`) refuses a row the matrix does not authorize, and `tests/test_ledger_schema.py` reports one written before that refusal existed."*
- **Code Reference (`TEMPLATE/tools/ledger.py:470-478`):**
  ```python
  authorized = AUTHORIZED_ACTORS_BY_EVENT.get(args.event, ())
  if authorized and actor_origin == "derived" and args.actor not in authorized:
      sys.exit(
          f"ledger append refused: actor '{args.actor}' is not authorized for a "
          f"'{args.event}' row (authorized: {', '.join(authorized)}) — membership is "
          "not authorization, and the matrix is enforced here so an unauthorized row "
          "is refused when it is written rather than reported a day later"
      )
  ```

---

## 3. THE REPAIR GAP

### 3.1 Subcommands Exposed in TEMPLATE Ledger CLI
Inspecting `main()` in `/root/agent-factories/TEMPLATE/tools/ledger.py`:
- Line 1195: `ap = sub.add_parser("append", ...)`
- Line 1205: `tp = sub.add_parser("tail", ...)`
- Line 1210: `vp = sub.add_parser("verify", ...)`
- Line 1222: `rp = sub.add_parser("repair", ...)`

The template CLI **does** expose `repair` in addition to `append`, `tail`, and `verify`.

### 3.2 Confirmation of the Member Factory Gap
- **Finding:** The prompt notes that **3 of 4 member factories expose only append/tail/verify and NO repair verb**.
- **Refutation / Confirmation:** 
  - **Refutation regarding current TEMPLATE:** The *template as it currently stands in `/root/agent-factories/TEMPLATE/tools/ledger.py`* includes the `repair` subcommand (implementing the exact logic prescribed by law: checking `docs/ledger-invariants.json`, requiring `--note` and `--append-detail`, verifying immutability of `ROW_IDENTITY`, checking for duplicate keys via `split_canonical_run`, and inserting before the canonical run).
  - **Confirmation regarding Member Factories:** Member factories that bootstrapped earlier received an older version of `tools/ledger.py` before `repair` was introduced.
- **What a member without `repair` is left with:**
  Without the `repair` subcommand in their installed `tools/ledger.py`, a member factory is left with:
  1. **Manual file editing:** They must edit `evidence/ledger.jsonl` by hand, violating the single-writer principle (§11: *"the ledger has one writer by construction rather than good intentions"*), risking concurrency races or corrupted line breaks.
  2. **Violating positional insertion laws:** An author manually appending fields or notes to the end of a line terminates the canonical trailer, silently displacing telemetry fields (the exact failure of `n=303` ruled at `n=572`).
  3. **No atomic swap or companion `run` row:** Manual edits cannot take `LOCK_EX` or append the companion audit `run` row required to document lawful boundary corrections under `#52 clause 2`.
  4. **Blocked state / permanent debt:** If an incomplete close row cannot be repaired mechanically, subsequent verification gates fail or force the factory to live with permanent debt or unprincipled deletions that trigger `test_ledger_no_shrink.py`.

---

## VERDICT
**NOT FIT TO SHIP AS-IS:** While the law and code are in tight agreement regarding derived actors, write-path authorization, and tool-owned settlement receipts, the template instrument embeds hardcoded meta-factory exemptions (`#6`, `#8`) and hard-depends on meta-factory global fleet fragments for session resolution, which immediately breaks execution for a clean downstream factory.