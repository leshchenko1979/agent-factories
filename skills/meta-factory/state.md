# State — the one-writer process law

**Owns:** the process law that binds a lane writing to a surface this factory keeps — the
ledger's write discipline and its second object (the duty receipt), the four directions
that couple a close row to its board item, the ruling-head convention, the actor set, the
one-field-one-predicate rule, the gate exemption surfaces, and the claim/close write-path
refusals.

**Home:** these clauses are the clause tail of the **State — every surface has one writer**
section of the meta-factory law (`SKILL.md` §11), extracted into this file on 2026-10-03
(board #300) so the law body fits the 500-line budget `tools/brain_metrics.py` declares.
`SKILL.md` §11 keeps the surface table, its one-writer rule and the authorship split, and
points here; this file carries the process law. **Load it before writing any state row or
touching a surface's writer.**

---

**The ledger carries a SECOND object, and its author is not the append path.** `evidence/ledger.jsonl` has one *writer* — `tools/ledger.py append` — and two *objects*. The first is a state transition, authored by the lane that makes it. The second is a **duty receipt**: a `run` row written by the **woken lane** when a thin trigger's duty actually completes, on behalf of the duty rather than of the trigger. The distinction is load-bearing because the two are separated by a silent gap: a pacemaker's own run row records that the **trigger fired**, never that the **duty ran**, so a job can read `success` on every fire while the work it exists to produce fails every day (#147). Nothing in the trigger's own record can close that gap — only the duty's lane can, by declaring the receipt, and the receipt is what the patrol consumes. A lane that wakes, does the work and writes no receipt row leaves the duty **unproven**, not discharged.

**A duty receipt is DECLARED, and the declaration is one whole line.** The row states `receipt_subject: <stem>` on a line of its own — anchored, so a mid-sentence mention cannot satisfy it — and the reader keys on that declaration rather than on a job name, so no job name is hardcoded and a row that declares nothing is *counted and named* as NOT JUDGED. **The declaration is the whole mechanism, so its omission is the failure it cannot see:** a row that simply omits the line is not a duty that owed nothing, and a reader that cannot tell those apart has a leg that passes by silence. A pacemaker whose duty owes a receipt therefore STATES the declaration in its own prompt, and the round is read from the row's own `last_run_at` — never from a parsed schedule, which is a second derivation of a fact the row already carries.

**`attested_at` is RESULTING STATE, never the receipt.** It is a *consequence* of a completed round, and a consequence is not evidence that the round happened: four fragments carried an `attested_at` four days stale against a job firing daily at `0 6`, which is exactly what an unreceipted duty looks like from the registry side. So `attested_at` prints under the label RESULTING STATE, is never consumed as the receipt, and never stands in for one. When it cannot be read, the reader says *why* rather than printing a date — an unread field is not a clean one.

**The receipt's SUBJECT is canonical, and the reader's key is deliberately NOT widened to meet a deviation.** A receipt's subject is `<stem>-<round>`: `<stem>` is the job's own declared `receipt_subject`, and `<round>` is its own `last_run_at` UTC date. The key is a **boundary-checked prefix** — the subject must start with `<stem>-<round>`, and the character after it must not be a digit, so a different date whose subject merely extends this one's digits (`...-2026-09-250`) cannot match. That tolerance exists for **round-key variants**: an hour-bearing subject (`patrol-verify-2026-09-25T06`) names the same round, and so does a trailing word. It is never licence to decorate: a subject that puts words BETWEEN the stem and the round (`registry-attest-writeback-2026-09-25`) does not name the round at all and is **not a receipt**, and the leg reads MISSING — loud, and true. **Do not widen the key to a fuzzy token match.** A false MISSING costs one look; a false CLEAN is silent, and this leg exists precisely because silence is the failure it cannot see (#160). The writer is upstream of the reader: fix the convention, never the key.

**A subject match is not a receipt — the row must DECLARE its completion.** A receipt carries `duty=completed`, `failed` or `skipped`, read through the shared positional reader (`tools/field_predicate.py::declared_duty`) against the domain declared beside it (`DUTY_DOMAIN`). A row whose subject matches the round and declares nothing is **not** a receipt: the leg's first version accepted any subject match, so a DISPATCH record written before the round completed certified it, and a round with no receipt at all read clean. Absent is not a value, an out-of-domain value is an ERROR, and `failed`/`skipped` are both findings. **The key is a distinct field, never `outcome=`:** a duty receipt is selection-biased — written by a lane that completed a duty — so folding it into the first-pass yield's population makes that metric structurally optimistic, one real lane failure diluting it roughly twofold. One number answering two questions is the #143 class. **The requirement binds the WRITER, and the reader's positionality is only what makes it a requirement: the `duty=` token must sit INSIDE the row's canonical terminal run — the maximal run of `=`-carrying tokens at the end of `detail` — so no token without `=` may follow it, and the value is written VERBATIM, so `duty=completed` declares `completed` while `duty=completed.` declares `completed.`, which is outside `DUTY_DOMAIN` and therefore an ERROR rather than a silent pass.**

**A pacemaker's redirect log is named after ITS OWN JOB, and the leg's precondition is
stated rather than assumed (2026-09-25, #163).** The notify-receipt leg attributes a
trigger's log by taking the filename's stem as a **cron job name** and looking it up among
the rows this factory declares (`patrol_host_state.py`, `NOTIFY_LOG_RE`). That makes
*the redirect label equals the job name* a load-bearing contract between every pacemaker
prompt and the leg — and it was written nowhere, which is how one job carried a
hand-typed label for **16 rounds** and every one of its logs landed in `retired_logs` as
*history, never judged*. The leg examined **nothing** and printed the same shape as a leg
that examined everything and found it clean.

**A mechanism whose precondition is undocumented is a permanent silent exclusion**, and it
is the mirror of the receipt clauses above: there, a declaration without its instruction
is a permanent false RED; here, a mechanism without its stated precondition is a
permanent false CLEAN. Both are the same failure — a contract that lives only in one
side's implementation.

So a pacemaker whose prompt writes a `/tmp` log **names the redirect after the job**, never
after a description of its cadence (`/tmp/factory-triage-patrol-<ts>.log`, never
`/tmp/factory-triage-6h-<ts>.log`), and a label that names no row is a finding rather than
history. When a redirect is renamed, **the prose that justified the old label is rewritten
in the same edit** — a prompt arguing for a label it no longer carries is the half-fix
shape this section rules against twice.

_ **The ledger's write discipline is the instrument's own law: `docs/instruments/ledger.md` §9 — the single-writer lock and fsync, the settlement receipt the TOOL writes, the close refusal, the reconstructed claim's basis, the subject form and the one-board `#N` namespace, retirement as naming-not-deleting, the irreducible append→push residual after a fork and the re-mint protocol that answers it, and the ad-hoc probe seam.** This section keeps what is THIS factory's process law; the clauses above it that named the contract are stripped here and hold in the instrument's file, reloaded through the `skills/meta-factory/ledger.md` symlink. Two clauses deliberately stay below because surviving process law cites them as its own basis.
**Which pacemakers owe a receipt.** Every pacemaker whose duty is performed by a **woken lane** — because its own run row records that the trigger fired and nothing about the work. A `trigger_cmd` gate does not exempt a job: a gate is a **pre-condition** that decides whether the trigger fires, and it says nothing about whether the lane then woken did the duty. The test is not whether the duty's work is recorded *somewhere* — a woken lane's own run row usually exists — but whether the leg can **BIND** that row to *this* job's round. Without the declaration it cannot, which is exactly why the declaration is an attribution key rather than a claim that nothing else records the work. A job that declares no stem is NOT JUDGED, and is counted and named so its silence is visible. A duty whose lane writes an undated, ad-hoc subject predating this convention owes the convention going forward: the receipt carries the round.

**A close and its board are coupled in four directions, and each one has its own mechanism.** (1) A close ROW must name the board state it observed — gated by `tests/test_close_board_recorded.py`. That gate cannot call `gh`: the mechanical suite runs offline and against a tree, not a live board, so the settling lane records the board state it saw and the gate asserts the record exists. (2) A close must be preceded by its own intake and claim — gated by `tools/ledger.py verify`, which reads a subject's rows as a sequence and names the subject and the missing leg. (3) A CLOSED board item must have a close row — **no offline gate can reach this direction**, and each mechanism says why in its own code: a gate cannot call `gh` (1 above), and `verify` builds its sequence check by iterating close rows, so a subject with no close row is never visited. Its upholding mechanism is therefore a PROCESS: a standing patrol cross-reads the board against the ledger. P29 admits a process as readily as a gate — a rule needs one or the other, not specifically a gate. The patrol is a runner, and its legs print whether they ran. Directions (3) and (4)'s standing patrol is `tools/patrol_host_state.py`, invoked on the factory-triage-patrol cadence (0 */6 * * * UTC). It reads the board WHOLE — gh issue list --state all — because the reverse leg, an intake row naming no board issue, is sound only over the full board, and feeds it to board_intake_problems(..., complete_board=True). Each leg prints RAN or NOT RUN with its reason AND the population it examined, so a leg whose predicate was never written is never read as a clean one and a leg that examined nothing is never read as one that examined the population and found it clean; the runner states the instant it read the board so every claim it makes is re-checkable. A board that cannot be read exits 2 with NO verdict: an unreadable board is not an empty one, and an empty board is not a clean one.

**(4) A close row's `board=closed` declaration must be TRUE — the direction the offline gate cannot reach either, because that gate reads the ROW and never the board.** Recording a state is not verifying it: direction (1) makes the omission visible, and nothing made a FALSE declaration visible, so two close rows declared a board close that had never happened and the gate read clean over both (#117). Its upholding mechanism is the same standing patrol, which gained a `board-close` leg: it reads every post-invariant close row through the GATE's own `BOARD_TOKEN` and `INVARIANT_LANDED` — never a re-derived parser, because a canonical-trailer read sees only 40 of the 52 such rows and a re-derived leg would judge 12 rows fewer and go false-green over them — and reports each declaration the live board contradicts, printing the population it examined and the instant it read the board beside its verdict. A subject the board has never heard of is reported too: `absent` and `closed` are different facts, and only one of them is what the row declares.

**A ruling's head is a CONVENTION, and the patrol prints the spellings it could not place (#245).** A ruling posted as a board comment opens with a markdown heading; the accepted forms are `## RULED`, `## RULING` and `## Amendment`, and the convention NAMES `## RULED` as canonical so a lane writing a ruling converges rather than infers it. The canonical head is **DECLARED, never enforced** — the writer is an agent typing `gh issue comment` and there is no tool on that path, so a rule the writer cannot reach would be dead text (P29). What upholds it is the leg's own clause: every heading comment the predicate does **not** accept is PRINTED with its issue number, and the count travels beside the verdict, so a fourth spelling surfaces as a FINDING on the run that first meets it instead of being indistinguishable from absent. The accepted set's bound is a FLOOR and never a ceiling: it was widened to the spellings then in use, and the search that found them could not have found a head worded differently. Nothing is backfilled — the three existing `## Amendment` comments are the population the widened predicate now accepts, not comments rewritten to the canonical head.

**A patrol claim about the board names the time it read it.** A claim like "no closed item lacks a close row" describes a live board at an instant; without the instant it cannot be re-checked, and by the receipt rule in `verdicts-and-claims.md` an uncheckable receipt is testimony, not evidence. So the patrol states its read time beside its finding.

**A committed board snapshot was considered for direction (3) and rejected.** It would make the comparison offline and gate-able, but a snapshot carries a freshness dimension the gate cannot attribute: a stale snapshot REDs for a subject whose close row landed after it was taken, and passes for one closed since — the gate would name a board/ledger mismatch when the real cause is a stale file. A detector that cannot name its cause is worse than a process that can, because it fails in a way that reads as a finding.


**A commit message names the concern; it does not cite row numbers.** A ledger row's
number is assigned *inside* the append lock, so it cannot be known before the append —
and by the time the commit runs, another lane may have appended further rows. Three
instances in one day carried the same shape: `d763277` named `n=211` and added
`211/212/213`; `d75b19a` named `212/213` and added `214/215`; `b12047e` named `n=259`
and added `n=261`. That is structural, not carelessness. Where a row must be cited,
cite it in the ledger's own `detail` text — written after the append, where the real
number can be read — or read it back before committing. This follows from the ruling
that the commit is **transport, not identity**: the row's identity is its `n`, so a
message asserting row numbers is a claim that can be wrong, and obeying this clause
removes the claim rather than policing it. It is upheld forward-only by
`tests/test_ledger_commit_cites_no_rows.py` — a history-wide form would be permanently
red, since 55 of 146 historical ledger commits cite row numbers in their subject.

**A law file's `version:` field is a CONTRACT with the body beside it, and the two move in the SAME commit.** Every law file in this repo — `skills/*/SKILL.md` and `TEMPLATE/SKILL.md.tmpl` — declares its own `version:`, and each carries its OWN, because the two are not byte-paired: they are independent documents that happen to share a structure, so a version field shared between them would name two different bodies at once and could not be a contract. The contract has two arms and both are needed. **Arm 1:** a commit that changes a law file's BODY must move THAT file's version in the same commit. **Arm 2:** a commit that moves a version must change that file's body. Arm 1 alone catches an unbumped law change; arm 2 catches a bump that names no new bytes, which mints a version range with no content — the same ambiguity the contract exists to remove, seen from the other side. Together the arms force the version and the body to move together, which is what a field naming the bytes means. The predicate is a BYTE change and never a judgement about whether a change was substantive: deleting a duplicated paragraph IS a body change and DOES require a bump, because a lane holding the old copy genuinely has different bytes.

What the contract buys is a lane's own staleness check. After a compaction a lane has lost the law text it was working to, and the only durable thing it can hold is a version. The field therefore has to mean the bytes: a lane that reloaded after a compaction holds the version it last read, compares that against the file in front of it, and a mismatch says the law moved under it. A version that drifts from its body makes that comparison silently useless — it reports "no drift" for a law that changed, which is the exact failure the check exists to prevent.

Upheld forward-only by `tests/test_skill_version_contract.py`, whose boundary is declared in `docs/ledger-invariants.json` under `skill_version_contract` and which reads from its landing commit forward. The historical decouplings are excused and printed as excused, never repaired — a bump written after the fact would be a falsified record rather than a repair. Nothing is backfilled.

**The Law-Upholding Principle (P29):** Every codified law must be upheld by an active operational process or a deterministic mechanical gate (`tools/audit.py`). A rule without an upholding mechanism is dead text and will be removed.

**The Single Ownership Principle (P30):** Every declared process has exactly one named process owner role. Shared ownership is zero ownership.

**The actor set is the roles the law names, and it is closed.** A role that is not listed
cannot write a row, so adding one is a law change rather than a convenience. The core set
is the template's four role cards plus `owner`, who directs without being a lane; a factory
whose law names a lane beyond them declares it in `tools/actors.txt`, one role per line. It
is declared there and not in the constant because `tools/ledger.py` is copied
byte-identically into the template — a lane only one factory has cannot live in a value that
must match everywhere. This set was **wrong until 2026-09-12**: it named `delegate` and
`surveys`, which the template does not ship, and refused `worker` and `carrier`, which it
does — a gate rejecting the very roles its own template hands out. Both directions are now
probed in `tests/test_ledger.py`.

**Single-writer is a mechanism, not a habit.** The ledger has exactly one append path
because concurrent writers would each read the same last row and each write `n+1` — the
file silently gains two row 41s, and every count taken from it is wrong from then on in a
way that looks fine. `tools/ledger.py` takes an exclusive lock, computes the next row
number *inside* it, and fsyncs before releasing. `tests/test_ledger.py` runs twenty
concurrent appends and asserts the row numbers are still `1..N`: the property is tested,
not asserted.

**One field, one predicate — the read-side mirror of the rule above.** A telemetry field
read out of a row's `detail` has exactly ONE predicate, and it lives in
`tools/field_predicate.py` (`keyed_value`, `declared_field`, `trailer_tokens`,
`split_canonical_run`, `declared_telemetry`, `mentioned_telemetry`,
`telemetry_value_problem`, `telemetry_problems`). A module that reads such a field IMPORTS
that predicate; a private parse of the same field is the defect this law names, not a style
preference. The evidence is this factory's own record rather than a principle: the helper
was built at `n=405` PART 5 as "ONE field predicate, shared by all three call sites", and
the class recurred anyway — the aggregator, ruled a fourth site at `n=572` PART 2 and fixed
under #90, and `tools/synthesize_insights.py`, the fifth, under #99. Both were found by
SYMPTOM, a measured over-report, and neither by a rule, because until this sentence no rule
was readable. The predicate is scoped to the canonical trailer because `detail` is free
prose that QUOTES trailers as evidence, and a private scan takes a quotation for a
measurement: `n=586` aggregates `n=303`'s quoted trailer and over-reported cost 16x.

The gate that enforces it is `tests/test_telemetry_reader_registry.py`, and it must
distinguish a READER from a WRITER, must name the modules it permits in a stated
allow-list, and must PRINT that allow-list on every run — an unprinted allow-list is an
exempt-by-silence surface, the class ruled at `n=571`. Both halves are load-bearing
together: a blunt scan for telemetry-shaped strings reports three modules under `tools/`
that carry no predicate and only ONE is a genuine call site (`telemetry.py` is the WRITER,
and constructing a token is the opposite of reading one; `patrol_host_state.py`'s only hit
is the word `turns` inside a prose message), so a gate without the distinction would need
an exemption for a non-defect — and an exemption granted to something that is not a defect
is a permanent weakening.

**What that buys is the SYMBOL, not the semantics.** The law binds every reader to one
function; it does not promise that function reads correctly, and no probe over a shared
binding can show more than the binding. `tests/test_close_row_revision.py` states the bound
of its own probe — "a lookalike defined here would satisfy every behavioural probe above
and still leave the class unfixed" — and the same holds here: a lookalike that
re-implements the predicate and is imported under its name satisfies an identity probe of
the imported name and leaves the class open. Stated so the rule is not oversold: identity
of the function is what is codified, correctness of the reading is
`tools/field_predicate.py`'s own gate (#99, ruling n=599).

**A gate whose only exits are barred is a stop with no andon cord.** A gate that reads commit *subjects* across a range can be violated by a commit already PUSHED, and then no repair is available: the commit is immutable, a revert does not remove the offending subject from the range, and re-anchoring the marker past the violation would make the marker's own stated definition false and silently convert a live violation into an excused one — the exact silent-excuse failure the exemption design forbids. Left that way the suite stays permanently RED and the next lane learns to ignore a red gate, which destroys every other gate's signal; so the defect is the EMPTY REPAIR SPACE, not the violation. Every gate of that shape therefore carries a sanctioned, VISIBLE exit: an exemption table holding the entries as FACTORY DATA in its own file and never inline in the gate, because the gate is paired byte-identically with its template copy and a factory sha must not ship to every new factory, and each entry is keyed by the FULL 40-character sha copied from live git output. An exemption is a visible debt, not forgiveness: every entry that MATCHES is printed as an `excused:` line on EVERY run, and the closing line distinguishes clean from excused, so the two are never the same output. An entry that is malformed, or that matches NO violation in the range, is a gate ERROR rather than a silent pass — an exemption list that quietly fails to load is indistinguishable from no exemptions, and a stale entry inflates the visible debt while excusing nothing. Admission is by PROOF, as everywhere in this section: an exemption is granted only where the repair space is genuinely empty, and the entry STATES that proof; an exemption nobody would defend in that output is one that gets fixed instead. And a SECOND exemption of the same shape is a PROCESS DEFECT, not an exemption — one is a debt, two mean the mechanism is not biting, and the remedy is a mechanism, never a third row. That mechanism is a DERIVATION, not a manual run: `python3 tools/gate_select.py --staged` reads the commit's own changed paths and returns the gates that read them, and any changed path covered by no declared trigger hands over the FULL `tools/audit.py` to run DETACHED — the manual full-audit run this clause used to name was unexecutable inline, 1387.9 s measured against a 600 s ceiling, and an impossible instruction is exactly what leaves a lane hand-picking the subset that omits the gate reading its own edit (#294, ruling n=2106; the clause's origin is #47 clause 4, ruling n=328). Instances: `docs/ledger-commit-exemptions.json` for `tests/test_ledger_commit_cites_no_rows.py`, and `docs/ledger-no-shrink-exemptions.json` for `tests/test_ledger_no_shrink.py` (#47 clause 4, ruling n=328).

**The existence leg asks whether the declared object EXISTS in this repository, and its bound is the part a reader will overread: EXISTENCE is neither ANCESTRY nor TRUTH.** A declared revision that resolves is not thereby the revision the row MEASURED, and the leg cannot say that it is. Ancestry is refused as the predicate for a MEASURED reason rather than a taste: a history rewrite leaves an honest revision unreachable while its object survives, so an ancestry test would condemn exactly the rows a rewrite did not touch. The distinction is not hypothetical — the leg exists because a close row declared a token that resolves nowhere while its TRUE revision resolves, so the leg reports the difference and the retirement names it. And **a leg that cannot judge SAYS SO**: on a tree with no object database the leg reports a STATED inability and the run prints `NOT RUN` with its reason, never the verdict of a leg that examined the population and found it clean.

**"A close row is refused at the write path when its subject has no preceding intake and claim."** `tools/ledger.py append --event close` runs the same sequence predicate `verify` runs — one predicate, two call sites — and exits non-zero, naming the subject and the missing leg, without writing anything. The refusal carries no exemption surface and needs none: a close appended now can never predate the gate. EXEMPTIONS governs `verify`'s reading of history only, and stays printed there. This does not replace `verify`: the order leg (a claim after its close) and any row written around the append path remain `verify`'s. This section's guarantee is one append path, not tamper-proof (#98, ruling n=596).

**A claim is an ACCEPTANCE, and it is stamped by the lane that takes the work — when it takes it, and before its first edit.** The three legs answer three questions: intake is Triage's leg, claim is WHO took the work, close is its completion. HQ's dispatch names the lane, and the lane's claim answers it; HQ never stamps the claim of the lane that took the work, because a claim records a taking and two actors on one transition is the shape this section forbids, applied to an actor rather than to the append path. The write-path refusal above is the BACKSTOP, not the step: it makes an omission impossible to reach a close SILENTLY, which is how the shape first appeared twice. A claim stamped after the work is a RECONSTRUCTED record: it must declare itself in terms, carry the token `claim=reconstructed`, and name the basis it rests on with the canonical marker `BASIS:` — and `verify` prints those rows beside its `excused:` lines together with the interval it recomputes from the row's own `ts` and its close row's `ts`, so clean, excused and reconstructed are never the same output. Forward-only: a reconstruction written before this sentence existed is not retrofitted (#98, ruling n=602; the interval moved from DECLARED to RECOMPUTED-AND-PRINTED under #115, ruling n=687).

**A lane's bindings are a SUPERSESSION CHAIN, and the live session is the newest binding within its own profile: a topic re-opened several times carries one binding per generation, and the newest is the lane. Only a match across two PROFILES is ambiguous, because there the registry cannot tell which daemon's session owns the topic; a single-profile chain is resolved by recency and the resolution is reported, never suppressed. The exit code carries the verdict: unbound and no-thread-id mean a declared lane is unreachable and exit non-zero, while a superseded chain is a live lane and does not (#100).**

The `chat_id` narrowing is what makes the PROFILE the partition: `resolve_lane` filters by
the factory's own chat before it counts matches, so every survivor already shares one chat
and a set spanning two profiles is the only case left in which the registry cannot tell
which daemon owns the topic. So `superseded` counts as RESOLVED in the exit predicate
(`unresolved_total` in `tools/registry.py`) and carries its own counter on `resolve`'s
summary line — visible without being a verdict — while `unbound`, `ambiguous` and
`no-thread-id` keep rc=1. The fix does not delete the detector it was built around:
`tests/test_registry.py` drives both halves over synthetic bindings, one profile to a
chain and two to `ambiguous`, because a chain-only probe would pass a fix that had removed
the ambiguity branch entirely.

**The cron table is the one surface this factory shares with every other, and sharing is
why only half of this law can be gated.** A factory's own jobs are named
`<declared-prefix><what-it-does>`, and `<declared-prefix>` is that factory's entry in the
fleet manifest's `job_prefixes` — **the prefix, never the slug**, because the prefix is the
only token a reader can resolve: a job name is judged against `job_prefixes` and against
nothing else, so a row named after its slug leaves its own factory's census silently
(#126). The two tokens coincide for most factories, which is why the distinction stayed
invisible until one of them did not. Those prefixes are the only reason a job on a shared
box can be attributed to its
owner at all, so no two factories may claim the same prefix — and `load_fleet_manifest`
now refuses a manifest where two overlap, **including one prefix nesting inside another**,
which `str.startswith` cannot tell apart and which would make the OWNER a property of
manifest ORDER rather than of ownership (`tests/test_registry.py`, probes over synthetic
manifests). Never disable, delete, edit or repace a job that is attributed to another
factory — a job you cannot attribute is not yours to touch, and it is reported instead. The
naming half is checkable per factory, because a factory can read its own jobs; the edit ban
is not, because it governs a cron table no single factory owns, and its upholding mechanism
is the process rather than a gate (#101): before touching a cron row, resolve the job's
owner through the registry attribution, and report a job you cannot attribute. That process
rides the existing ≥6 h attest pacemaker's question set rather than a new job.

**A blocked decision goes in the register, and a prose line in the topic is NOT a registration.** A lane whose next action needs an owner decision registers it with `oc-questions ask --factory <key>` **in the same turn it stops** — because nothing aggregates a sentence in a topic, and the owner cannot see which lane is waiting on him. The factory key is this factory's **standing set**, reused and never re-minted; the tool resolves the *lane* from the lane's own session binding, so there is no `--lane` to mislabel and an unbound session is refused by name. Decisions are collected on the **rendered page**, never from card buttons: a tap is dropped while the target is mid-turn, and the register's own `asked_at` age is what re-surfaces a question, so a repeated topic ping is noise rather than pressure. **The count of open questions across all sets is the human-gate metric** — declared rather than inferred, which is why no heuristic over message traffic can substitute for it. **The contract — verbs, store path, the URL law, the clarify/amend obligation — is the instrument's own law: `docs/instruments/open-questions.md`** (reloaded through the `skills/meta-factory/open-questions.md` symlink, so it survives compaction).

Canonical clause (full contract, verbs, store path): `docs/instruments/open-questions.md` — the instrument's own law; `skills/opencrabs-dev/fleet-directives.md` keeps a `[LANE]` pointer only.
