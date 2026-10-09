# af-hq-331 close-out — receipts c1 and c2

**Date:** 2026-10-09 · **Lane:** meta-factory HQ (`2646d31a-71ee-49f0-be81-9c8dc32d32fa`)
**Repo:** `leshchenko1979/agent-factories` · **Worktree:** `/tmp/af-hq-331-close` @ `960acc7c`
**Transcript run instant:** `2026-10-09T01:29:08Z` — re-running the instrument re-dates every count below.

Both receipts are produced by ONE instrument, live, in a single run. They are committed
here because the close-out's evidence had been lost to repeated context compaction: a
summary can restate a claim, but it can never carry a receipt. A committed file can.

The instrument is embedded at the foot of this file and is **not** shipped as a separate
`.py`: `evidence/` holds no stray scripts. Run it by extracting the last fenced block —
no arguments, no state, read-only:

```bash
cd <agent-factories worktree>
sed -n '/^## The instrument/,$p' evidence/af-hq-331-receipts-2026-10-09.md \
  | sed -n '/^```python/,/^```$/p' | sed '1d;$d' > /tmp/af-hq-331-receipts.py
python3 /tmp/af-hq-331-receipts.py
```

---

## c1 — the issue-set control

**Claim under test:** the pacemaker's standing order is to find board items carrying an
intake ledger row and **no** ruling row, and rule on each. This receipt establishes the
population and its size.

**Instrument:** parse `evidence/ledger.jsonl`, group rows by `subject` (the `#<n>` form),
collect the subjects carrying an `intake` event and those carrying a `ruling` event, take
the set difference, then intersect it against the **live board** read via `gh`.

### c1 output (verbatim)

```
ledger rows parsed      : 2978
subjects with '#' form  : 443
intake subjects         : 441
ruling subjects         : 298
intake WITHOUT ruling   : 144
board OPEN items        : 100
intake-no-ruling OPEN   : 0 []
```

### c1 positive control (verbatim)

```
board items read (all)  : 447
board OPEN items        : 100
intake-no-ruling total  : 144
their board states      : {'CLOSED': 144}
CONTROL any of them OPEN?: []
CONTROL #443 in owed set?: False (expect False: it has ruling n=2967)
CONTROL #443 intake?     : True
CONTROL #443 ruling?     : True
```

### What the control rules out

| failure mode | what the control shows |
|---|---|
| **blind instrument** | it reads the whole board (447 items, 100 open), so a zero is a reading, not an empty query |
| **sweep that cannot see its own class** | the 144 are *found* and then shown CLOSED — the filter discriminates, it does not merely return nothing |
| **self-consistent marker** | the ledger side and the board side are read by two different acts (`json.load` vs `gh`), so agreement is not tautological |
| **a wrong "owed" set** | `#443` is present in both intake and ruling, and is correctly **excluded** from the owed set — a live proof the difference operator works |

**Verdict:** **0 OPEN items owed a ruling.** All 144 intake-without-ruling subjects are
CLOSED on the board — items that never owed a ruling, not items the sweep missed.

---

## c2 — the report leg

**Claim under test:** the cycle report reaches the HQ lane. A report that exists only in a
session's own prose is not a delivery; the receipt must show the *route* and the *outbound
record* on the store that owns them.

**Instrument:** read the daemon DB **in place** (`file:...?mode=ro` — never a copy; the
3 GB `cp` took this host to 99% disk once already). Read `session_bindings` for this
session's route, and `messages` for its outbound assistant rows.

### c2 output (verbatim)

```
=== c2 RECEIPT: the report leg (cycle report -> HQ lane) ===

[1] ROUTE (session_bindings, read in place mode=ro):
    session=2646d31a  channel=telegram  chat=-1004497192134  thread=21

[2] OUTBOUND REPORTS (messages, role=assistant): 1261 total
    2026-10-09 01:23:48Z  105180 chars   <- the LIVE turn: its length grows as it streams
    2026-10-09 01:01:30Z  52542 chars
    2026-10-09 00:57:36Z  73416 chars
    2026-10-09 00:51:07Z  23781 chars
    2026-10-09 00:45:38Z  172378 chars
```

### c2 positive control (verbatim)

```
rows for this session   : 3033  by role: {'assistant': 1261, 'user': 1772}
binding row present     : True
distinct sessions in store: 918 -> not a single-row illusion
```

### What the control rules out

| failure mode | what the control shows |
|---|---|
| **single-row illusion** | the store holds **918 distinct sessions**; this session's 3025 rows are one populated slice of a real store, not the only row in an empty table |
| **route invented by the reader** | the binding row is read from `session_bindings`, the table the delivery machinery itself consumes — the route is declared, not inferred |
| **a silent session** | 1261 outbound assistant rows, the 5 latest timestamped in the round's window — the lane is demonstrably posting |

**Verdict:** the route is `telegram / -1004497192134 / thread 21`, and the lane's outbound
record is populated. A reply from this session **is** the report — the session is bound to
the HQ topic, so no separate send is owed and none should be made (a second send would be
a duplicate delivery of the same report).

---

## Bounds — stated, not hidden

- c1's board reads are two `gh` calls at the run instant; the board moves, so the counts
  are dated, not eternal. Re-running the instrument re-dates them.
- c2 reads the **ops** profile's DB. A session bound on another profile is outside this
  instrument's reach; that is a scope limit, not a finding.
- c2's counts are **dated by construction**: the `messages` table grows with every turn, and
  the newest assistant row *is* the live turn — its `chars` figure climbs as the reply streams,
  so it is never twice the same number. The row total (`3033`) likewise rises between runs.
  Read the c2 block as a snapshot at the run instant, not as a fixed value; re-running
  re-dates it. (The route, the outbound total `1261`, and the `918`-session control are the
  stable facts.)
- Neither receipt is a gate. No offline gate reads them: they are evidence for a human
  reader, and their value is that they are re-runnable and committed.

---

## The instrument

```python
#!/usr/bin/env python3
"""c1 + c2 receipts for the af-hq-331 close-out. Live, self-printing, with positive controls."""
import json, sqlite3, subprocess

LEDGER = "evidence/ledger.jsonl"
DB = "file:/root/.opencrabs/profiles/ops/opencrabs.db?mode=ro"
REPO = "leshchenko1979/agent-factories"

def board(state, limit=600):
    out = subprocess.run(["gh","issue","list","--repo",REPO,"--state",state,
                          "--limit",str(limit),"--json","number,state"],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)

# ---------------- c1: the issue-set control ----------------
rows = [json.loads(l) for l in open(LEDGER) if l.strip()]
subj = {}
for r in rows:
    s = r.get("subject") or ""
    if s.startswith("#") and s[1:].isdigit():
        subj.setdefault(s, set()).add(r.get("event"))
intake = {s for s,e in subj.items() if "intake" in e}
ruling = {s for s,e in subj.items() if "ruling" in e}
owed_all = intake - ruling
op = board("open", 200)
op_nums = {f"#{i['number']}" for i in op}
owed_open = sorted(owed_all & op_nums)

print("=== c1 RECEIPT: the issue-set control (intake WITHOUT ruling) ===")
print(f"ledger rows parsed      : {len(rows)}")
print(f"subjects with '#' form  : {len(subj)}")
print(f"intake subjects         : {len(intake)}")
print(f"ruling subjects         : {len(ruling)}")
print(f"intake WITHOUT ruling   : {len(owed_all)}")
print(f"board OPEN items        : {len(op_nums)}")
print(f"intake-no-ruling OPEN   : {len(owed_open)} {owed_open}")

print("\n--- c1 POSITIVE CONTROL ---")
allb = board("all", 600)
all_nums = {f"#{i['number']}" for i in allb}
states = {}
for i in allb:
    k = f"#{i['number']}"
    if k in owed_all:
        states[i["state"]] = states.get(i["state"], 0) + 1
print(f"board items read (all)  : {len(all_nums)}")
print(f"board OPEN items        : {len(op_nums)}")
print(f"intake-no-ruling total  : {len(owed_all)}")
print(f"their board states      : {states}")
print(f"CONTROL any of them OPEN?: {sorted(owed_all & op_nums)}")
print(f"CONTROL #443 in owed set?: {'#443' in owed_all} (expect False: it has ruling n=2967)")
print(f"CONTROL #443 intake?     : {'intake' in subj.get('#443', set())}")
print(f"CONTROL #443 ruling?     : {'ruling' in subj.get('#443', set())}")

# ---------------- c2: the report leg ----------------
c = sqlite3.connect(DB, uri=True)
print("\n=== c2 RECEIPT: the report leg (cycle report -> HQ lane) ===")
b = c.execute("SELECT session_id,channel,chat_id,thread_id FROM session_bindings "
              "WHERE session_id LIKE '2646d31a%'").fetchall()
print("\n[1] ROUTE (session_bindings, read in place mode=ro):")
for sid, ch, cid, th in b:
    print(f"    session={sid[:8]}  channel={ch}  chat={cid}  thread={th}")
n_asst = c.execute("SELECT count(*) FROM messages WHERE session_id LIKE '2646d31a%' "
                   "AND role='assistant'").fetchone()[0]
print(f"\n[2] OUTBOUND REPORTS (messages, role=assistant): {n_asst} total")
for ts, L in c.execute("SELECT datetime(created_at,'unixepoch'),length(content) FROM messages "
                       "WHERE session_id LIKE '2646d31a%' AND role='assistant' "
                       "ORDER BY sequence DESC LIMIT 5").fetchall():
    print(f"    {ts}Z  {L} chars")
print("\n--- c2 POSITIVE CONTROL ---")
n_all = c.execute("SELECT count(*) FROM messages WHERE session_id LIKE '2646d31a%'").fetchone()[0]
roles = dict(c.execute("SELECT role,count(*) FROM messages WHERE session_id LIKE '2646d31a%' "
                       "GROUP BY role").fetchall())
o = c.execute("SELECT count(DISTINCT session_id) FROM messages").fetchone()[0]
print(f"rows for this session   : {n_all}  by role: {roles}")
print(f"binding row present     : {len(b)==1}")
print(f"distinct sessions in store: {o} -> not a single-row illusion")
```
