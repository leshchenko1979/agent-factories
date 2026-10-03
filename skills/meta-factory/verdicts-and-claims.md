# Verdicts and claims

**Owns:** how a claim about this factory's own state is made and checked — the verdict
verbs and their receipts, the canonicality ladder, the citation rule, and the four shapes
of a surface that reports success while the work did not happen.

**Home:** these clauses are the **Verdicts and claims** section of the meta-factory law
(`SKILL.md` §8), extracted into this file on 2026-10-03 (board #300) so the law body fits
the 500-line budget `tools/brain_metrics.py` declares. `SKILL.md` keeps the heading and a
pointer; this file carries the clauses. **Load it before any verdict, receipt, citation or
canonicality claim.**

---

- **Verdict verbs need a receipt — and the receipt must name the revision it measured.**
  "Green", "passing", "verified", "shipped" only with the same-turn tool output that shows
  it, and a receipt about a TREE must name the revision it describes: a gate count or a row
  count is true of the tree that produced it and unverifiable without the sha (issue #63).
- **Identifiers are never hand-assembled.** Copy the full value from live output.
- **No claim without a check.** Existence, absence and status all require a tool call in the
  same turn. "I have not verified" is acceptable; a confident guess is not.
- **A blocker a lane reports is CLAIMED STATE, and a plan's state is read from the plan — never
  from the lane's memory of it.** "Blocked on your approval", "awaiting `/execute`", "the card is
  pending" are status claims about a live session plan, so they carry the obligation the clause
  above puts on every other existence and status claim: a same-turn read of LIVE plan state, not
  a recollection that a plan was opened. A completed plan is ARCHIVED — its card reads completed
  and there is nothing left to approve — so a stale blocker sends the reader to a card that no
  longer exists, and whoever acts on it pays the cost. Measured 2026-09-23: a lane reported two
  workstreams as queued "behind your `/execute` on the plan card" eight hours after that plan had
  completed and been archived, and the owner went looking for a card that was gone. **The failure
  was DETECTED and not acted on** — the message carried the daemon's own phantom-blocked marker
  and nobody read it — which is the second half of the rule: a self-heal marker is a receipt, and
  a receipt nobody reads is not a check. **Approval routing is PER-SESSION:** `/execute` typed in
  one topic approves that topic's session plan and no other, so a lane asking for approval names
  WHERE the card lives, not merely that it exists.
- **A criterion is a claim too, and it is AUTHORED long before it is judged.** A plan
  acceptance criterion that names a path, a gate or a file asserts that the artefact RESOLVES,
  so the check the clause above requires is due **when the criterion is written** — not at
  completion, and not by whoever executes it days later. Resolve every name as you write it;
  where the artefact does not exist, name the MECHANISM by the behaviour you will observe
  rather than a filename that merely reads plausible. A name assembled from its neighbours is
  the same fabrication as a guessed sha, and it survives longer because **nothing runs a
  plan**: measured 2026-09-21, a Worker plan task carried as its third acceptance criterion a
  command naming a test file that exists under **no revision**. The name was assembled from
  the two real artefacts beside it — the ledger-invariants JSON and the ledger-boundary
  helper — which is exactly what made it read plausible rather than wrong. It stood for
  three days, and a patrol's report caught it, not a mechanical check. **No gate can uphold
  this and that is stated, not implied** — a session plan lives outside every tree the
  offline suite reads — so what upholds it is the process: the authoring lane resolves each
  name, and the lane that meets a criterion naming an absent artefact reports it and never
  silently re-words it (a judged acceptance is a record, and rewriting one is a backfill).
- **A citation is resolvable by a reader who holds ONLY this document.** A reference to
  tracked work carries its NUMBER, taken in full from the read that returned it; a reference
  to another document NAMES that document; a bare section number resolves only inside the file
  that holds it — which is precisely the reader an agent usually is: after a compaction, in
  another session, or in another factory. The mechanism is structural, not stylistic, so this is
  the citation half of the two bullets above: a numberless "see above" is unreadable to anyone
  who reached the law without the surrounding conversation, and it reads as knowledge while
  carrying none. Filed by the owner as `#135` half 2 on his own stated basis — a correlation
  observed in one factory, which he labelled a stated correlation rather than a measured chain —
  and MEASURED before it was written, in the direction that matters: this file's four section
  references are ALL compliant (three name their document, one is a same-file reference), so the
  clause is PREVENTIVE here rather than corrective, and it is stated that way rather than
  claiming a defect this tree does not carry.
- **Verification is scoped by load-bearing.** Verify what you will act on or report; accept
  receipted facts you will not. In a cross-lane pass, the value is the **contradiction** check.
- **An attribution names an ABSOLUTE sha, never a relative revision.** The receipt rule above
  governs RECEIPTS; this governs INVESTIGATION, which a probe that writes no receipt never
  reaches. `HEAD~1` means *the parent of whatever HEAD is when the probe runs*, so in a shared
  worktree where other lanes commit concurrently the revision it resolves is not the revision
  the author meant, and the verdict describes a commit nobody chose. Measured 2026-09-19: a
  stash-then-checkout probe read a `docs/` drift as PRE-EXISTING because a peer lane's commit
  landed between the stash and the checkout, so `HEAD~1` was this lane's OWN commit rather than
  its parent; the drift was attributed correctly only by reading both blobs at the NAMED
  commits. A claim about which commit introduced a change is established by reading that
  commit's own blob (`git show <sha>:<path>`), never by a relative revision, and a probe that
  must compare before and after resolves both sides to named commits. The same binds the
  RECORD: an `evidence/rework.md` entry that cites a relative-revision form must name the
  resolved absolute sha, upheld by `tests/test_rework_relative_revision.py` (#86, ruling n=558).
- **A message addressed to one factory cites only facts measured on THAT factory.** A
  per-factory report is a claim about a NAMED tree, so a figure, a file identity or a property
  measured on factory A and written into factory B's message is FALSE ABOUT B however true it
  was about A — and it is the half a reader cannot catch, because the sentence reads exactly
  like the true ones beside it. Measured 2026-09-25, TWICE inside one hour in the kit-drift
  round: miidas's byte-identical file was named to inferhub-watch, and infra-factory's
  stdlib-only `ledger.py` was asserted OF inferhub's, whose `ledger.py` imports the
  three-module closure at `:72`/`:82`/`:94`. Both were hand-composed from a pool of five
  replies, while the DISPATCH bodies — generated from each factory's own measured data —
  carried neither error, which is the whole finding. The form that prevents it: a per-factory
  body is BUILT FROM that factory's own reply, and every factual claim in it is traceable to
  that reply — a fact belonging to another factory NAMES that factory or is not written. No
  gate can uphold this and that is stated, not implied: a notify body lives in no tree the
  offline suite reads, so what upholds it is the build form and the reader.
- **A close row's trailer is DECLARED, never supplied.** The canonical close trailer is the
  run of `key=value` tokens at the end of a `close` row's `detail`. `tools/ledger.py` supplies
  only measurements it genuinely took (`cost_usd=`, `tokens_in=`, `tokens_out=`, `turns=`,
  `duration=`) — taking a number is not a judgement. Every VERDICT in the trailer is the
  author's, and the tool must never write one: it once appended `outcome=accepted` and
  `gate=all-pass` for silence, so both headline rates could only ever report success (#53,
  ruling n=333 clause 1). `rework=` joins that trailer on the same law — `rework=#N` names the
  rework entry the close produced, `rework=none` states it produced none, and either is
  legitimate only when the AUTHOR states it. ABSENCE stays `unstated`, never read as `none`:
  an unrecorded verdict is UNKNOWN, never a value (#53 clause 2). The marker is AVAILABLE, not
  REQUIRED — most closes resolve no defect, and a required field degrades to boilerplate — and
  nothing is backfilled, because a disposition reconstructed after the fact is a falsified
  record, not a repair (n=386 clauses 3/5/6; #53 clause 7).
- **A close row's `rework=#N` is a FORWARD REFERENCE to a file, so it and the entry it names land in the SAME commit (#286, ruling n=2032).** The token names a row of `evidence/rework.md`, not a ledger row, so nothing orders the two writes: a close row committed ahead of its entry leaves `main` RED for `tests/test_rework_declared_landed.py` until the entry lands — measured at **48.03 min** (`89b4692` → `1cbefd2`). **No hook is owed.** A pre-commit or pre-push leg is (i) bypassable with `--no-verify`, (ii) local-only (hooks are not cloned, so it cannot bind a lane that lacks it), and (iii) a PREVENTION where the class needs a DETECTOR (#247/#281; the #284 ruling at `n=2010`). The convention is this sentence; the detector is the gate that already exists (`tools/audit.py` block 41), and the residual is the audit's own LATENCY, ACCEPTED and STATED.
- **A repair must not terminate the canonical run.** The trailer is POSITIONAL, so text
  appended AFTER it ends the run and every trailer-scoped reader stops seeing the row's
  declared telemetry — the repair silently REMOVES a measurement from the fleet total.
  `tools/ledger.py repair` therefore inserts its appended text BEFORE the run, so a prose
  note lands in the head and the run stays terminal; a `key=value` append EXTENDS the run
  itself and is safe either way — **when its key is NEW**. An append that introduces a key
  the run ALREADY declares is **REFUSED**, non-zero, before any write, so the ledger is
  left byte-identical: one field carrying two values has no canonical reading, and a
  consumer that takes the last occurrence reads the appended one while the row's own
  declaration still stands beside it. Refusing costs nothing lawful, because repair's
  lawful case is a row **INCOMPLETE** against a declared invariant — and an incomplete row
  is MISSING the key, never carrying it twice. Both sides of the comparison are read
  through the shared predicate (`field_predicate.declared_keys`) and each is scoped to its
  own canonical run, so prose in the head is not a declaration of the field and a prose
  append that merely NAMES a field is not refused (#104, ruled at ledger n=620 PART 4).
  Measured precedent: n=303's two parenthetical `REPAIR NOTE`
  sentences displaced its own canonical `cost_usd=2.7719 tokens_out=9956523 turns=1 …`, which
  was canonical when the row was written. n=303 is **not** backfilled — the law above bars it
  — and stands as the measured precedent (#91, ruling n=572 PART 3).
- **A predicate's SCOPE is its reader's population, and the two are stated together.** A
  predicate that claims the box and reads one profile root answers about the profile root,
  and its evidence must name the population it read — the count and the homes — so a
  narrower read is visible as a narrower read rather than as a clean box. An enumeration
  that cannot name its own population is not allowed to report HOLDS, and a home it could
  not reach is reported as unreached, never omitted (#102).
- **A measurement whose EITHER SIDE reads live state is a property of the INSTANT, not of the
  revision — and naming the sha does not make it one.** It must name the instant it read, and it
  must not be generalized into a revision property: #63 governs the case where both sides are tree
  bytes, this governs the case where they are not. The two properties are then kept APART.
  REPRODUCIBILITY — a committed artifact against a replay from its OWN RECORDED INPUTS — is
  deterministic, offline, and belongs in the correctness pass. FRESHNESS — an artifact against live
  state — is true only near the instant of the render, and it is REPORTED, never folded into the
  correctness verdict, because a check that fails by construction carries no more information than
  one that cannot fail. The POPULATION half is the predicate clause above: a predicate's scope is
  its reader's population, and the two are stated together (#102, #103).
- **A gate's time budget is a DECLARED MULTIPLE of a MEASURED runtime, never a round number.**
  A cap picked by feel is uncalibrated in both directions: too low, it kills a healthy gate and
  reports a timeout as a verdict; too high, it hides a hung one. So each gate's cap is derived —
  `budget_sec = margin_x × measured_sec` — with the margin, the measured runtime and the
  ABSOLUTE sha the measurement was taken at declared together in the gate-budget manifest, so
  the number carries its own basis and a reader can recompute it. The budget VALUES are the
  process owner's, never the implementing lane's (n=574 PART 5). A gate with no entry uses the
  declared default and the audit PRINTS which gates used it — a declared default with a printed
  population is not an exempt-by-silence surface, an unprinted fallback would be. A budget
  exhausted is UNKNOWN: never green, never a plain failure, and its recorded duration is the
  MEASURED elapsed time, never a hardcoded zero — a timeout is a fact about a gate and must be
  readable as one (#94, ruling n=744).
- **A predicate that examined nothing has reported nothing, not HOLDS.** Naming a population and examining one are two properties, and the first does not carry the second: a predicate can name its population exactly and still read zero items inside it, and its clean verdict over that empty read is indistinguishable in the output from a verified one. So every predicate that reports a clean verdict over an enumerated population asserts that the enumeration was NON-EMPTY, prints the count it examined, and FAILS LOUDLY on a zero count, naming which population came back empty. A gate that examined zero items must never print the verdict of one that examined the population and found it clean. This generalises a property already stated for one gate (`tests/test_ledger_no_shrink.py`) and already practised across the suite; it is codified because a predicate that cannot name its own population is already barred from reporting HOLDS, and a predicate that names its population perfectly and examines nothing is the same failure one step further in.
  The clause is **two-part**, and the second part is what keeps it from being satisfied by an exit code: a gate PRINTS the population it examined, and it is proven to BITE by a probe that makes it fail. **NON-VACUITY IS A PROPERTY OF THE PROBE, and POPULATION VISIBILITY is the property of the run.** A gate whose only evidence of working is an exit 0 over a population it does not print has not been shown to work. The loud-fail-on-zero form is right for a gate whose population is the whole history — `tests/test_ledger_no_shrink.py`'s is — and **wrong for a forward-only gate whose population is legitimately empty until its next instance**, where the probe is the only thing that can show the gate bites (#112, ruling n=657 item 8).
- **A cited line is evidence of a FACT, never of a CAUSE.** A log line, a count or a config read can establish that something happened; it cannot establish what produced it, and a causal sentence built on top of a real observation is a separate assertion that needs its own support. A cause is established by varying it — the effect follows — or by its absence coinciding with the effect's absence, and the ruling or entry that asserts one names the disproof it rests on. The sharpest available test, and the one this factory lost a ruling to: **a cause that VANISHES while the effect persists at FULL RATE is not the cause.** No gate can read causation, so the upholding mechanism is a PROCESS (P29), not a gate — and the clause is the second half of the record law above: the RECORD of a defect states its cause, so the cause must be as checkable as the fact.
- **A claim about the FUTURE is a third assertion class, supported by neither a fact nor a cause.** A status residue — `delivery_failed`, a failure timestamp, a non-zero count — is a fact about the PAST; promoting it into a prediction (*"it will fail again on 10-01"*) requires reading the field's **current** value AND the **guard** that gates the path the prediction names, and stating both. A prediction resting on the residue alone cannot be falsified before its date and reads as a live defect to every reader until then. Measured 2026-09-24: an advisory asserted a job would fail again on its next scheduled fire on an unbaked target URL, while `deliver_to` had read `NULL` since an unrelated edit — the guard is unreachable from `NULL`, so the predicted failure could not occur, and the repair had landed by accident rather than by a repair. Its sibling claim failed identically in the same artifact (*"has been failing silently since …"*, derived from a create-time test fire 7.565 s after creation), so the two shapes travel together: a recurrence assertion is a claim about the future, and the artifact that asserts one usually asserts the other. Origin: raised by the lane that produced it, whose own rework entry named the missing clause rather than leaving the gap unwritten.
- **Canonicality: which of two contradicting states stands (the ladder, T0–T4).** A check that
  reports a discrepancy has found a *disagreement*, not a *direction* — and a lane that guesses
  the direction repairs the canonical side to match the stale one, which is worse than the
  discrepancy standing. So every such report carries the TIER that resolved it, cheapest rung
  first:
  - **T0 — identity.** Read the objects' own fields before arbitrating anything: the question is
    often malformed rather than the state (a quote attributed from row adjacency; a paired file
    where byte-identity *is* the property). One read, and the question dissolves.
  - **T1 — precedence.** Where one side is UPSTREAM of the other, upstream wins and no goal
    knowledge is needed: source over render, authored over generated, live over snapshot, and
    §11's one named writer over every other path to that surface. **T1 POINTS AT §11's table and
    never restates it** — a second copy would drift from the gate that reads the first, which is
    the defect this clause exists to prevent. Precedence is never RECENCY: the newer side does
    not win.
  - **T2 — metric.** Only where both sides are genuinely independent does the factory's own goal
    decide, and the resolution NAMES the metric. An unstated metric cannot decide, so a T2 claim
    that cannot name one is a T3 or a T4 by construction.
  - **T3 — strategy.** Where the goal is too abstract to decide, a declared strategy does. The
    strategy layer is **already machine-readable, and the ladder does not duplicate it**:
    `tests/test_law_coverage.py`'s `PRACTICE_GATES` maps every practice law to the artefacts that
    uphold it, and the gate prints its own mapped count on every run — so a lane holding a check
    **inverts that map** to read its strategies off the existing relation rather than adding a
    second one beside it. No count is written here: the figure belongs to the gate that measures
    it, and a number copied into this file would be stale the moment a law is typed. A per-check
    copy of that field is the drift this clause's T1 rule forbids, in the strategy layer.
  - **T4 — neither.** Neither side is canonical on the evidence available: one is superseded, or
    both, or the identity needed to decide was never recorded. **T4 is a VERDICT, not a failure.**
    Its two answers are *re-measure* and *UNRESOLVED with the open question named*. Forcing a pick
    is how a durable record acquires a false fact — where no surface records the actor, the honest
    outcome is a recorded `UNRESOLVED`, never a named culprit.
  **The verdict NAMES its tier, and a T4 is loud.** A resolution that does not say which rung
  decided it is unauditable and can never be re-litigated when the metric or strategy moves. A
  check that found a discrepancy and reached no tier prints that outcome the way the patrol prints
  its `RAN` / `NOT RUN` legs, so "no tier resolved it" is never readable as a clean result. Its
  upholding mechanism is a PROCESS (P29), not a gate: no gate can decide a metric comparison, and
  one that pretended to would fail in a way that reads as a finding — so the standing patrol
  reports each tier that went unresolved.
  **Canonicality is not ownership, and the two are read apart.** `ONTOLOGY.md` carries the pair:
  ownership (§11) is *authority over a surface*; canonicality is *truth about a pair*. Ownership
  supplies ONE of T1's four precedence forms — it decides only when one side derives from the
  other. Two readings of the SAME surface share an owner, so ownership cannot choose between them;
  and a disagreement whose owner is undecidable is a T4, not a licence to name one.
  **What this does NOT do:** it never pre-writes canonical state per surface. That is the one
  approach that goes stale silently, which is the disease rather than the cure; the ladder is
  walked lazily, at the site, only where a disagreement actually exists.

**FOUR SHAPES OF THE SAME FAILURE — a surface that reports SUCCESS while the work did not
happen (derived 2026-09-25 from the question register's own defects, agent-factories#165).**
They are one family and each is a distinct mechanism, so the family is stated once and the
shapes are named. The common thread with *a green receipt over an unverifiable check* is
that the surface is not merely wrong: it is **confidently wrong in the direction that stops
anyone looking**. And the measured weight of the family: **three of the four were found by
the human, not by a gate**, while the register's own selftests were green throughout.

- **(a) A state transition must carry the content that justifies it, or be refused.** A
  transition to `awaiting_clarification` with an empty payload is a *drop wearing a status
  field*: the machine changed state, the reader was told nothing, and the lane that owns the
  question received a request with nothing to act on. The test is mechanical — **name the
  payload the transition carries, and refuse the transition if it is empty.**
- **(b) Every state a machine can enter must be distinguishable in the surface the human
  reads.** If the renderer does not read the status field, the status does not exist for its
  only reader: a clarifying question rendered IDENTICALLY to an open one, so the human could
  not tell whether his own earlier tap had registered. **The renderer is the reader; a state
  with no reader is a state the human cannot act on, and the defect is invisible from the
  machine's side because the machine's own tests assert the value it wrote.**
- **(c) An error path must be rendered by the surface that triggers it.** Where a transport
  swaps only success responses, a refusal produces NO visible change — and **an invisible
  refusal reads as a no-op, so the user repeats the action**, which is worse than an error
  message because it also destroys his model of what the control does. The rule binds the
  transport, not the handler: a handler that returns a correct refusal has not rendered it.
- **(d) A field written but never read is a record that can only lie.** Before adding a
  state field, **name its reader**; if it has none, the field is a liability rather than a
  record, because it will be read by whoever finds it next and believed. Two instances of
  this shape in one day, on two different surfaces: `answer_kind` left stale by `amend`,
  asserting a state the question was not in, and the duty receipt's `outcome=` measured as
  dead code on real receipts (so a row declaring nothing certified the duty). **The check is
  cheap and it is the one nobody runs: grep for a reader before you write the field, and
  again when you change what writes it.**

**Why these belong in this section rather than in a testing section.** Each is a *claim* the
system makes about itself — the status says awaiting, the page says open, the transport says
nothing, the field says completed — and a claim with no reader is the failure mode this
whole section governs. A gate can hold (d) once the reader is named, and can hold (a) once
the payload is declared; **(b) and (c) are not gate-able at all**, because their subject is
what a HUMAN sees, and no offline suite reads the human's screen. That is why three of the
four were found by the human, and it is the reason the four are stated as design obligations
rather than as gates: the remedy is to name the reader while the surface is being built.

