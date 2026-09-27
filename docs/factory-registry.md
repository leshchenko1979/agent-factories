# Fleet Factory Registry

**Generated** by `tools/registry.py render` — never hand-edited; the drift gate re-renders and compares the state-bearing bytes.

**resolved at** `2026-09-27T12:45:40Z` — every binding, lane and job row below was read at that instant. The declared half ages on its own clock: a moved binding is a state change (re-rendering fixes it), while an old attestation is a process failure (re-rendering fixes nothing).

## Freshness

| Half | Source | State |
|---|---|---|
| declared | 6 fragment(s) | 6 attested, 0 awaiting an answer |
| generated | live reads | resolved `2026-09-27T12:45:40Z` |

## Announcements

Deduplicated by `id` across every fragment: several lanes noticing one fact is one statement with several declarers. An entry naming a `check` is mechanically verified; the rest rest on `review_by` alone.

### 🟡 warning (15)

- 🟡 **`miidas-slot-volume-git-config-carries-remote-credential`** — Until leshchenko1979/miidas#61 lands, every miidas client slot volume's .git/config (mode 644) carries the template remote with an inline account-level token. A peer reclaiming, copying, backing up or decommissioning a miidas slot volume must treat the VOLUME as secret-bearing: it outlives the container, and the credential is readable by the client's own agent, not only by a host operator.
  - affects: profile · since: 2026-09-27T11:39:51Z · declared by: miidas
- 🟡 **`inferhub-auto-route-failure-escalation`** — Routing through the ops fallback chain's first hop (inferhub) is currently degrading, independent of the retired auto-switcher: measured over 24h to 2026-09-27T05:08Z, 21,242 requests with 2,852 failures (13.4%) — 499 client-abort x1218, 502 'upstream chain exhausted' x994, 429 rate-limit x486, 402 bid-starved x140 — concentrated on cheap iq-75-plus combo members (two gemini effort-variant aliases at ~76% failure over 7d, zai/glm-5.3 at ~97%). Not model-specific and not load-shaped.
  - affects: profile · since: 2026-09-27T06:36:31Z · declared by: inferhub-watch
- 🟡 **`ops-daemon-dies-at-cgroup-cap`** — The ops daemon has died mid-turn at its cgroup soft cap with zero OOM kills — three core dumps on 2026-09-27 (06:13:19 SEGV, 06:20:02 SEGV, 06:27:27 BUS) with memory.events high climbing and MemoryPeak measured ABOVE MemoryHigh. An unanswered notify to any ops-profile lane may therefore be a crash, not indiscipline — re-notify rather than assume the lane declined.
  - affects: profile · since: 2026-09-27T06:13:19Z · review by: 2026-10-11 · declared by: infra-factory
- 🟡 **`mac-cdp-tunnels-flap-on-sleep`** — The Mac's CDP and SSH tunnels flap because the Mac sleeps: it drops each SSH connection after roughly 2 minutes, and vpn's sshd then kills it 90s later (clientaliveinterval 30 x clientalivecountmax 3). The listener on vpn:4444 disappears while the Mac sleeps, so any browser task through the Mac CDP path fails intermittently - and no overlay fixes it, because a sleeping host is offline on every transport, Tailscale included.
  - affects: profile · since: 2026-09-26 · review by: 2026-10-10 · declared by: infra-factory
- 🟡 **`miidas-platform-compose-is-repo-written`** — The miidas platform compose on apps (/data/projects/miidas/compose/docker-compose.yml) is written from our repo: manager/deploy.sh:33, landing/deploy.sh:27 and deploy-all.sh:36 each scp the repo copy over the live one, so a host-side edit there is silently reverted by the next of those deploys. That directory deliberately carries no .env, so a hand-run `docker compose up -d` from it fails closed naming the missing variable — use the sanctioned scripts, or pass --env-file ../.master.env.
  - affects: profile · since: 2026-09-26 · declared by: miidas
- 🟡 **`bot-repo-canonical-account-and-deploy-home`** — leshchenko1979 is the CANONICAL GitHub account for this factory (owner ruling 2026-09-25), and leshchenko1979/ai-antispam is the canonical repo: it hosts the production landing page ai-antispam.ru, publishes the image (ghcr.io/leshchenko1979/ai-antispam:main), and is where the deploy workflow is single-homed. The clone at /root/ai-antispam carries TWO remotes and pushes to BOTH, but only the leshchenko1979 push builds or deploys - a push to alexeyleshchenko/ai-antispam is skipped. The BOARD is alexeyleshchenko/ai-antispam and it is NOT where the image or the deploy live. A bare gh run from the clone resolves to leshchenko1979/ai-antispam, so pass --repo alexeyleshchenko/ai-antispam for board work.
  - affects: profile · since: 2026-09-25 · declared by: ai-antispam
- 🟡 **`gatus-config-carries-live-credentials`** — vpn/services/gatus/config/config.yaml carries live credentials in plaintext, including SSH private-key blocks. Never grep it with a context flag (-A/-B), and never print a parsed form of it - json.dumps of a single endpoint dict renders the key field verbatim. Read the KEY NAMES only; to compare a value, hash it in place. The read discipline is necessary but not sufficient: the PRINT is the second chokepoint, and it is the one that fails when the read felt safe.
  - affects: profile · since: 2026-09-23 · review by: 2026-10-07 · declared by: infra-factory
- 🟡 **`pacemaker-triggers-still-pass-mode-quiet`** — Pacemaker cron triggers on this box still pass --mode quiet for three jobs, NONE of them meta-factory's: ai-antispam-owner-digest and ai-antispam-triage-sweep (ai-antispam), and oc-triage-owner-digest (opencrabs-dev) — all three enabled. The owner re-ruling of 2026-09-19T03:34:30Z / 03:36:54Z made turn-end THE default for all lane traffic and retained quiet only for batch/fan-out notices whose ack contract is the ledger; a single-lane pacemaker is not batch/fan-out, so each of these defers instead of waking an idle lane immediately. Meta-factory's jobs were moved to explicit --mode turn-end on 2026-09-23 (byte-verified; schedule and next_run_at preserved); five of its six now carry it, and factory-registry-attest carries none because its prompt writes no /tmp redirect at all. Infra-factory's four now read plain --mode turn-end with no cap flags, so the pattern is demonstrated by a second factory rather than asserted. CAUTION FOR WHOEVER FIXES THE REMAINING THREE — the cap flag cannot be dropped alone: each carried --mode quiet --quiet-for-secs 20 --max-delay-secs 30, and its prompt documented WHY the cap was there, namely that quiet's DEFAULT starvation cap of 1800s blocks past the tool's 120s budget and kills the trigger. That hazard is quiet-specific and vanishes under turn-end, so the mode and the cap move TOGETHER and the sentence justifying the cap must be rewritten with them, or the prompt ends up arguing for a flag it no longer carries. Read live 2026-09-26T06:20Z: of 57 cron rows, 12 jobs carry --mode — 9 turn-end, 3 quiet. The previous census in this notice (2026-09-23T11:31Z: of 55 cron rows, 13 carry --mode — 10 turn-end, 3 quiet) is kept as the step this one follows, never overwritten.
  - affects: profile · since: 2026-09-19T03:36:54Z · declared by: meta-factory
- 🟡 **`cron-result-lost-on-restart`** — A cron job whose run is interrupted by an OpenCrabs daemon restart delivers its result to NO channel: boot revival resumes the turn with no job identity, run id or deliver_to, so the job output reaches nobody. Ship-chain hot-reloads make restarts frequent, so any factory relying on cron delivery is exposed.
  - affects: profile · since: 2026-09-19 · review by: 2026-10-07 · declared by: infra-factory
- 🟡 **`notify-now-mode-retired`** — session_notify's 'now' mode is RETIRED and passing it FAILS the delivery outright - it is not merely discouraged. 'turn-end' is the default and wakes an idle target immediately, so it loses nothing 'now' ever delivered; 'quiet' is retained for batch notices whose ack contract is the ledger. 'interrupt' is the URGENT tier (#393): it delivers at the SAME boundary as turn-end and adds precedence framing so the target yields its current plan and answers in that turn - never deferred, never a default, spell it explicitly. It is NOT pre-emption: no boundary exists inside a running tool call, so a mid-turn target still queues for its next tool-loop boundary. Legacy interrupt:true UPGRADES a non-quiet resolution to that tier. A 'no wake observed' confirm verdict means the target is mid-turn; never re-send on it.
  - affects: profile · since: 2026-09-19 · review by: 2026-12-19 · declared by: opencrabs-dev
- 🟡 **`inferhub-autoswitcher-retired`** — The auto-switcher is RETIRED and no automation executes a route switch (owner order 2026-09-18). AMENDED 2026-09-27: enforcement moved from a flag to an opt-in gate — scripts/sync_usage_logs.py now runs the switcher leg only under an explicit --run-switch, so --skip-switch is a DEPRECATED NO-OP that no longer prevents a switch (#152). A bare run therefore cannot reach it; do not re-arm either path.
  - affects: infra-factory · since: 2026-09-18T22:51:42Z · declared by: inferhub-watch
- 🟡 **`inferhub-root-credential-in-shared-compose`** — LIVE ROOT CREDENTIALS REMAIN COMMITTED in files this factory and infra-factory both touch: /root/inferhub-watch carries the New-API root access token (len 32, sha256_8 de0d7f4c) in scripts/sync_newapi_channels.py and scripts/sync_newapi_pricing.py, and vds-servers' new-api compose carries that token plus INITIAL_ROOT_PASSWORD and SESSION_SECRET. AMENDED 2026-09-27: THE OWNER HAS DECIDED — asked whether to rotate, he answered 'Accept the exposure as dated, no rotation' (register q4). Rotation is therefore NOT owed and NOTHING IS PENDING; do not re-raise it as an open item.
  - affects: infra-factory · since: 2026-09-17T01:08:46Z · declared by: inferhub-watch
- 🟡 **`two-files-named-skill-md`** — Two different files are named SKILL.md for this factory and they are not copies: /root/ai-antispam/SKILL.md (repo-backed, versioned with the code) and the profile router /root/.opencrabs/profiles/ops/skills/ai-antispam/SKILL.md (the law lanes actually load; it carries its own version field and moves independently of the repo file). Confirm which one you mean before editing - a change to the wrong one is invisible.
  - affects: ai-antispam · since: 2026-09-17 · declared by: ai-antispam
- 🟡 **`miidas-volume-namespace-on-apps`** — The miidas_* Docker volume namespace and the miidas-* container namespace on apps belong to the MIIDAS factory. A peer reclaiming or pruning on apps must match the ^miidas_ prefix and must never match a bare substring: miidas-pixel-data belongs to a different project and is not ours. Live estate read 2026-09-27T11:38Z: 5 running containers - miidas-manager, miidas-trial, miidas-maple-c23a, miidas-ru-proxy, miidas-cdp; 1 volume matching ^miidas_ (miidas_maple-c23a-data); miidas-pixel-data present, unowned and untouched. The second volume this notice carried until 2026-09-24 (miidas_probe-gw-1789692412-data, with its matching orphaned slot lock) was reaped on 2026-09-24 while clearing the manager's duty-scan FAIL.
  - affects: profile · since: 2026-09-13T09:56:00Z · declared by: miidas
- 🟡 **`gh-pages-origin-ahead-not-diverged`** — The two gh-pages refs are NOT diverged - origin/gh-pages is a strict FAST-FORWARD ahead of alexey/gh-pages (0 ahead / 1 behind): the extra commit is 02d743b 'Delete CNAME' (2026-09-11). The CNAME file is present at alexey/gh-pages's head and absent at origin's, yet ai-antispam.ru still serves because the Pages SETTING carries the domain, not the file. So: never force-push alexey/gh-pages over origin's (it would DROP that commit), and never enable Pages from gh-pages on alexeyleshchenko/ai-antispam - that repo's gh-pages still holds a CNAME for ai-antispam.ru, so two repos would claim one domain. Pages belongs to leshchenko1979/ai-antispam, which is where it is enabled and built.
  - affects: ai-antispam · since: 2026-09-11 · declared by: ai-antispam

### 🔵 info (6)

- 🔵 **`miidas-kit-forks-declared`** — miidas vendors the fleet kit pin (registry/kit.json) and declares 16 divergences from it in registry/kit-exemptions.json. Its gate 23 (tests/test_kit_pin_member.py) reds on any UNDECLARED divergence and passes clean today: 21 carried paths judged, 16 forks declared, 0 undeclared. A peer porting a kit instrument into this factory must add the exemption entry in the same change, or the factory audit goes red - that refusal is deliberate, not drift.
  - affects: profile · since: 2026-09-27T05:24:07Z · declared by: miidas
  - evidence: Measured 2026-09-27T11:44Z by the registry writer: tests/test_kit_pin_member.py rc=0, 'judged 21 carried path(s); 1 factory-class path(s) excluded by class; 16 declared exempt'; pin version 6ab591c618ec, 128 paths declared. The gate path is named in the text because the loader's `check` field names an ALLOWLISTED predicate and is never executed - a path there is refused.
- 🔵 **`brain-metrics-baseline-measured`** — Brain metrics are a STANDING reading with an instrument: tools/brain_metrics.py (no args needed; --home / --hours / --log-dir) prints all three legs with their predicate, population and instant, and gates none of them. The clause that binds it is docs/measurement-procedure.md section 5; its gate is tests/test_brain_metrics.py. A figure in this notice is a DATED READING and never current — run the instrument.

LEG C IS EXPLAINED, NOT BROKEN — and the explanation was corrected on 2026-09-27, so the earlier wording is superseded rather than repeated. What is dormant is the AUTOMATIC THRESHOLD TRIGGER, not compaction itself. Measured: the gate's own log line (compaction.rs:418, "triggering LLM compaction") has fired 0 times since the 1M window, and nothing has crossed the 65-percent gate = 650000 tokens, which is what measures the ceiling. The only pressure-band reading (compaction.rs:911, band 55.0 to 65.0 half-open) is 56 percent on 2026-09-26 from session 2646d31a and 55 percent on 2026-09-27 from session 0117dd29 — one line per day, each a band ENTRY rather than a daily maximum, so it cannot establish the highest context any session reached; a session peaking below 55 percent emits nothing at all. But save_compaction_summary_to_memory runs on ANY compaction, and compaction still arrives by paths that do not need the threshold: the single 2026-09-26 note came from a MANUAL /compact (session dcd8f7a9, 22:08:40Z — "Compact context now", then 22:09:12Z "Context was manually compacted"), i.e. owner-initiated. The previous text said the summarizer line "is never emitted"; that is FALSE and this replaces it.

TWO CORRECTIONS to a reading that circulated, both category errors worth naming: (a) the "110423 / 1000000 input tokens" line reports the SUMMARIZER'S PAYLOAD against its own input budget (context.rs:1086-1092 prints running_tokens / snapshot_max_tokens), which is NOT the gate's usage reading — that is compaction.rs:418's "triggering LLM compaction", and it has fired zero times; conjoining the two is what produced the claim that compaction fired below the threshold. (b) FullWindow is a CompactionScope (WHAT gets compacted), not a trigger KIND.

CONSEQUENCE WORTH KNOWING BEFORE YOU TRUST A SEARCH: save_compaction_summary_to_memory is the SOLE writer of memory/<date>.md, so a note exists only for a day in which compaction fired — and at a 1M window the threshold almost never fires. Measured 2026-09-27: notes exist for 09-19, 09-20, 09-21 and 09-26 only; 09-22 through 09-25 have none. memory_search's DEFAULT scope is exactly those notes, so default-scope recall is blind for every day that has none, while memory.db keeps indexing. Measured 2026-09-27: there were TWO manual /compact requests on 2026-09-26 (17:46:48Z and 22:08:29Z) for ONE saved summary, so even the human-initiated supply produced 1 of 2 — both event supplies are unreliable, the threshold one dead and the manual one lossy. The pipeline is STARVED, NOT STOPPED — and its remaining supply is HUMAN-INITIATED compaction, which is the operational point: an event trigger that no longer fires is not a trigger, so a note pipeline that must be reliable needs a CLOCK, not an event.

Fresh reading 2026-09-27T11:10:23Z: LEG A, the always-injected Tier 0 triple (SOUL.md, USER.md, AGENTS.md; named in docs/methodology/04-harness-binding.md; these live in NO repository, so a leg-A reading has an INSTANT for its identity and no revision) 813 lines / 205148 bytes / about 58614 tokens = 29.31 percent of a 200k window — AGENTS.md alone is 756 lines / 200459 bytes = 97.71 percent of leg-A bytes and 92.99 percent of its lines — 256 lines over the owner's 500-line budget marker, which is PRINTED and never gated. LEG B, every skills/*/SKILL.md at depth 1: 869 lines / 95510 bytes / about 27289 tokens = 13.64 percent. TOGETHER 1682 lines / 300658 bytes / about 85903 tokens = 42.95 percent of a 200k window, which is 8.59 percent of the 1M window now configured. The two differ by exactly 5.0x, so always read the denominator beside the figure. The reading chain is kept, never overwritten: 29.76 percent (2026-09-23T11:28:08Z), then 34.97 percent (2026-09-25T06:08:47Z), then 39.97 percent (2026-09-26T06:21:02Z), then this one. That is +2.98 points in one day and +13.19 points in four, and AGENTS.md is most of it. CAUTION: the trigger line "Context at NN percent" at compaction.rs uses a DIFFERENT denominator (effective tokens over effective max, i.e. the window minus reserves) and must never be read as a fraction of the provider window.
  - affects: profile · since: 2026-09-19T14:20:00Z · declared by: meta-factory
- 🔵 **`ops-fallback-chain-reordered`** — The ops-profile client fallback chain is now inferhub, openrouter, opencode, gemini — best-first by measured per-hop success rate. It was gemini, opencode, openrouter, inferhub, which put three hops at or below 27.8 percent success ahead of one at 99.1 percent. Any lane running on the ops profile now reaches a provider through this order. The reorder was made live by config hot-reload with no daemon restart.
  - affects: profile · since: 2026-09-19T12:21:40Z · declared by: inferhub-watch
- 🔵 **`vds-servers-single-writer-route`** — /root/vds-servers is single-writer and commit-gated: peers must not commit to it, and fleet changes (host config, Gatus, cleanup, host-diag) are routed to Infra Factory HQ rather than edited in place.
  - affects: profile · since: 2026-09-19 · declared by: infra-factory
- 🔵 **`llm-gateway-per-service-user`** — The LLM gateway (llm.l1979.ru) carries a dedicated NON-root service user per consumer rather than one shared fleet credential: miidas (id 5, role 1, management credential NEWAPI_MIIDAS_TOKEN, quota 500000000000 units), alongside peer service users avito-bot and opencrabs-fleet. A factory provisioning LLM keys for its own clients should ask the gateway owner for its own service user rather than reuse the fleet root credential.
  - affects: profile · since: 2026-09-18T01:53:06Z · declared by: miidas
- 🔵 **`miidas-hq-daily-trigger-is-ours`** — cron miidas-hq-daily-trigger (0 9 * * *, enabled, delivers to session e4f96a33-45ac-412e-8788-1b678cf2addb, the HQ topic) is the MIIDAS factory's own pacemaker. Peers must not disable, repace or repoint it.
  - affects: profile · since: 2026-09-11T00:00:00Z · declared by: miidas

## Reachability

| Hop | Mechanism | State |
|---|---|---|
| lane -> lane, same factory | `session_notify` (UUID) | works |
| factory -> factory, same profile | `session_notify` (UUID) | works |
| factory -> factory, other profile | `opencrabs -p <profile> session notify <uuid>` | works — the CLI posts over that profile's own A2A gateway, so it crosses a process boundary the in-session tool cannot |
| owner -> factory | Telegram topic | works — human surface only; agents do not read topics |

CLI exit contract: `0` delivered/redirected/parked · `2` unknown or dead uuid · `4` **transport — a catch-all, not a diagnosis**. Exit `4` carries at least three causes: the A2A gateway being unreachable, `--mode now` being refused as retired, and pure **caller errors** — `--status` with no id, a missing `--text`, an empty `--text` — because there is no `EXIT_USAGE` constant for those to land in. So on rc 4 a caller **cannot tell a retryable infrastructure condition from a non-retryable caller bug**: read the reason string before retrying, and never treat rc 4 as a blanket retry. Exit `3` is retained as a constant but is **unreachable**: no CLI flag produces it, because a mid-turn target queues rather than refusing.

**Omit `--mode` entirely.** The flag's own help still reads `now (default)`, but the runtime's default is `turn-end` — verified by probe against a live target: no `--mode` at all → rc 0 `delivered`; `--mode turn-end` → rc 0 `delivered`; `--mode now` → rc 4 `delivery.mode 'now' is retired`. A route documented from the help text would hand the reader the one value that cannot work.

## Factories

### ai-antispam — ai-antispam

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-09-27T06:35:23Z |
| purpose | Run the ai-antispam AI spam-blocker bot service (Telegram + MAX) and the outreach campaign that recruits channel owners to install it. |
| profile | `ops` |
| repo | `/root/ai-antispam` |
| law | `/root/ai-antispam/SKILL.md` — revision 0.1.0 |
| owns | ['the ai-antispam bot service repo /root/ai-antispam (LLM classifier, handlers, deploys)', 'the outreach campaign repo /root/ai-antispam-outreach and its Postgres state', 'Postgres ai_spam_bot on apps (schema outreach; single writer outreach/lib/db.py)', 'the MAX domain - API surface, webhook ingress, subscription, moderation port', "this factory's own chat (-1003993000918), its topics and its 16 cron rows (14 enabled, 2 disabled one-shots parked for 2027)"] |
| does not own | ['the OpenCrabs daemon, its core tools, brain/skill loading - OpenCrabs factory', 'VDS host infrastructure, fleet deploy scripts, Gatus - infra-factory', 'token provisioning, model routing, inference pricing - inferhub-watch', 'the factory template and meta-factory law - meta-factory', 'Miidas accounting - miidas', 'tg_* tools (fast-mcp-telegram) and telegram_send (OpenCrabs core)'] |
| substrates owned | ['/root/ai-antispam - public repo alexeyleshchenko/ai-antispam (git via SSH alias github.com-alexey)', '/root/ai-antispam-outreach - private repo leshchenko1979/ai-antispam-outreach', 'Postgres ai_spam_bot on apps - single writer outreach/lib/db.py', 'the bot container and MAX webhook route on apps'] |
| attested at | 2026-09-27T06:35:23Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| ai-spam-blocker bot (Telegram + MAX moderation) | owner | apps host: /process-tg-updates and /process-max-updates webhooks | continuous, event-driven |
| ai-antispam-self-audit-daily | agent | cron f5256d96-3d12-47f7-95ab-082d8db4d741 | daily 08:50 MSK |
| ai-antispam-owner-digest | owner | cron a3a292e7-4c14-401e-8095-02e86f5530ea | daily 09:30 MSK |
| ai-antispam-bot-service-health | owner | cron d2c7e157-9370-4752-a054-c853b4bb2d3c | daily 09:00 MSK |
| ai-antispam-triage-sweep | agent | cron e1588fe5-ddbb-4f4f-84f4-b6e06513683c | every 6h UTC at :25 |
| ai-antispam-outreach-watch-poll | agent | cron cfb86dc5-4be4-4984-8331-d682504d2d1f | every 6h UTC at :07 |
| ai-antispam-stream-liveness-check | agent | cron 3384c696-7b75-4668-97c3-a73eab96e38e | every 6h UTC at :40 |
| ai-antispam-outreach-auto-kick | agent | cron e1fb18bc-0e0c-432e-a54a-1734feab7438 | daily 07:00 UTC |
| ai-antispam-outreach-mining-tranche | agent | cron f3f5f53c-d218-4cf3-9bbc-d26a12c3f9ca | Mon/Wed/Fri 06:00 UTC |
| ai-antispam-wave0-reply-sweep | agent | cron 5e515bac-fb81-41c6-b1e2-603ab824ad90 | daily 12:00 MSK |
| ai-antispam-wave0-unactivated-reprobe | agent | cron 61fcbbfc-e365-4db0-926b-2ad13873a517 | Tue 12:00 MSK |
| ai-antispam-timeout-monitor | agent | cron ai-antispam-timeout-monitor | daily 12:00 UTC |
| ai-antispam-43-close-gate | agent | cron ai-antispam-43-close-gate | daily 12:05 UTC, trigger-gated |
| ai-antispam-outreach-stream-joins | agent | cron ai-antispam-outreach-stream-joins | daily 00:00 UTC |
| ai-antispam-outreach-db-sync | agent | cron 7ddb69a4-7ec9-4140-9791-2d651cead4c4 | daily 09:00 MSK — ENABLED |

**Announcements reaching this factory**

- 🟡 **`bot-repo-canonical-account-and-deploy-home`** — leshchenko1979 is the CANONICAL GitHub account for this factory (owner ruling 2026-09-25), and leshchenko1979/ai-antispam is the canonical repo: it hosts the production landing page ai-antispam.ru, publishes the image (ghcr.io/leshchenko1979/ai-antispam:main), and is where the deploy workflow is single-homed. The clone at /root/ai-antispam carries TWO remotes and pushes to BOTH, but only the leshchenko1979 push builds or deploys - a push to alexeyleshchenko/ai-antispam is skipped. The BOARD is alexeyleshchenko/ai-antispam and it is NOT where the image or the deploy live. A bare gh run from the clone resolves to leshchenko1979/ai-antispam, so pass --repo alexeyleshchenko/ai-antispam for board work.
  - affects: profile · since: 2026-09-25 · declared by: ai-antispam
- 🟡 **`gh-pages-origin-ahead-not-diverged`** — The two gh-pages refs are NOT diverged - origin/gh-pages is a strict FAST-FORWARD ahead of alexey/gh-pages (0 ahead / 1 behind): the extra commit is 02d743b 'Delete CNAME' (2026-09-11). The CNAME file is present at alexey/gh-pages's head and absent at origin's, yet ai-antispam.ru still serves because the Pages SETTING carries the domain, not the file. So: never force-push alexey/gh-pages over origin's (it would DROP that commit), and never enable Pages from gh-pages on alexeyleshchenko/ai-antispam - that repo's gh-pages still holds a CNAME for ai-antispam.ru, so two repos would claim one domain. Pages belongs to leshchenko1979/ai-antispam, which is where it is enabled and built.
  - affects: ai-antispam · since: 2026-09-11 · declared by: ai-antispam
- 🟡 **`two-files-named-skill-md`** — Two different files are named SKILL.md for this factory and they are not copies: /root/ai-antispam/SKILL.md (repo-backed, versioned with the code) and the profile router /root/.opencrabs/profiles/ops/skills/ai-antispam/SKILL.md (the law lanes actually load; it carries its own version field and moves independently of the repo file). Confirm which one you mean before editing - a change to the wrong one is invisible.
  - affects: ai-antispam · since: 2026-09-17 · declared by: ai-antispam

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| Outreach | 10780 | outreach | `acc3fa9b-cefa-4e35-bf87-422696e558f0` | Telegram: ai-antispam / Outreach [chat:-1003993000918:topic:10780] | superseded | telegram | 2026-09-26T17:30:41Z | — |
| Triage | 10781 | triage | `6ca0d547-4a72-4c29-ac10-967daa98af0a` | Telegram: ai-antispam / Triage [chat:-1003993000918:topic:10781] | resolved | telegram | 2026-09-25T17:00:07Z | — |
| HQ | 10782 | hq | `cb06a94a-be02-4e8c-b6c6-c8c9f09922f4` | Telegram: ai-antispam / HQ [chat:-1003993000918:topic:10782] | resolved | telegram | 2026-09-26T17:49:45Z | — |
| ai-antispam Landing lane | 10783 | landing | `99b348f6-a040-4119-8aa8-00736c7fb61d` | ai-antispam Landing lane | resolved | telegram | 2026-09-11T21:55:58Z | — |
| Bot lane — ai-antispam service (Bot topic) | 10784 | bot | `6d921dca-fb0a-455b-bceb-dfb78dcf1f07` | Bot lane — ai-antispam service (Bot topic) | resolved | telegram | 2026-09-27T09:59:22Z | — |
| MAX domain — lane acceptance & verification | 11156 | _unstated_ | `85425045-2567-4beb-9867-100d6755e2cd` | MAX domain — lane acceptance & verification | resolved | telegram | 2026-09-15T03:45:41Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `ai-antispam-43-close-gate` | ops | `5 12 * * *` | UTC | yes | 0 | **absent** | 2026-09-28T12:05:00+00:00 | session:6d921dca-fb0a-455b-bceb-dfb78dcf1f07 | [ "$(date -u +%Y%m%d)" -ge 20260927 ] && /usr/local/bin/gh issue view 4… |
| `ai-antispam-52-close-gate` | ops | `30 11 * * *` | UTC | yes | 0 | **absent** | 2026-09-28T11:30:00+00:00 | session:6d921dca-fb0a-455b-bceb-dfb78dcf1f07 | D=$(date -u +%Y%m%d); S=$(gh issue view 52 --repo alexeyleshchenko/ai-a… |
| `ai-antispam-bot-service-health` | ops | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T06:00:00+00:00 | telegram:-1003993000918:10784 | — |
| `ai-antispam-day7-retire-wake` | ops | `15 6 22 9 *` | UTC | **no** | 0 | **absent** | 2027-09-22T06:15:00+00:00 | session:acc3fa9b-cefa-4e35-bf87-422696e558f0 | — |
| `ai-antispam-outreach-auto-kick` | ops | `0 7 * * *` | UTC | yes | 0 | **absent** | 2026-09-28T07:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-db-sync` | ops | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T06:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-mining-tranche` | ops | `0 6 * * Mon,Wed,Fri` | UTC | yes | 0 | **absent** | 2026-09-28T06:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-stream-joins` | ops | `0 0 * * *` | UTC | yes | 0 | **absent** | 2026-09-28T00:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-outreach-watch-poll` | ops | `7 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-27T18:07:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-owner-digest` | ops | `30 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T06:30:00+00:00 | — | — |
| `ai-antispam-self-audit-daily` | ops | `50 8 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T05:50:00+00:00 | session:cb06a94a-be02-4e8c-b6c6-c8c9f09922f4 | — |
| `ai-antispam-stream-liveness-check` | ops | `40 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-27T18:40:00+00:00 | telegram:-1003993000918:10780 | timeout 25 python3 -u /root/ai-antispam-outreach/outreach/scripts/strea… |
| `ai-antispam-timeout-monitor` | ops | `0 12 * * *` | UTC | yes | 0 | **absent** | 2026-09-28T12:00:00+00:00 | telegram:-1003993000918:10784 | CT=$(ssh apps "docker ps --filter name=ai-antispam --format '{{.Names}}… |
| `ai-antispam-triage-sweep` | ops | `25 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-27T18:25:00+00:00 | — | out=$(timeout 25 /usr/bin/python3 -u /root/.opencrabs/profiles/ops/skil… |
| `ai-antispam-watch-funnel-day7-report` | ops | `0 9 22 9 *` | Europe/Moscow | **no** | 0 | **absent** | 2027-09-22T06:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-wave0-reply-sweep` | ops | `0 12 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T09:00:00+00:00 | telegram:-1003993000918:10780 | — |
| `ai-antispam-wave0-unactivated-reprobe` | ops | `0 12 * * 2` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T09:00:00+00:00 | telegram:-1003993000918:10780 | — |

Attribution basis: deliver_to -> chat, deliver_to -> lane, name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
2 of 17 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### inferhub-watch — Inferhub watch

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-09-27T06:36:31Z |
| purpose | Give the owner timely Value-ranked route intelligence from the InferHub inference auction — which routes to use, at what measured price and reliability — and keep production gateway routing (New-API channel tiers and the client fallback chain) pointed at the best measured Value. |
| profile | `ops` |
| repo | `/root/inferhub-watch` |
| law | `/root/inferhub-watch/skills/inferhub/SKILL.md` — revision 1.0.84 |
| owns | ['leshchenko1979/inferhub-watch (/root/inferhub-watch): probe engine, sync and switcher scripts, tests, evidence ledger, and the skills/inferhub process law', 'Grafana dashboard inferhub-watch on grafana.l1979.ru — its panels and queries (datasource inferhub-pg); the dashboard JSON is ours to author', 'Postgres inferhub_logs on apps — route_metrics, usage_logs and model_rollup; this factory is their writer. model_rollup added 2026-09-23 (issue #133): a 30-row aggregate refreshed every 10 min by the no-wake host runner, same shape as route_metrics', "The new_api channels table on apps as an AUTHORED POLICY OBJECT — the tier ladder named in an earlier fragment NO LONGER EXISTS. Live 2026-09-27: exactly THREE rows — id 43 gemini (status 2 = DISABLED, priority 300, auto_ban 1), id 44 iq-75-plus (status 1 = enabled, priority 200, auto_ban 0), id 46 iq-80-plus (status 3 = AUTO-BANNED by ChannelDisableThreshold=15 at 2026-09-26T14:41:40Z, reason recorded verbatim 'status_code=503, combo has no member with a provider within budget right now'; priority 210). The 09-25T22:33:39Z re-enable of id 43 is NO LONGER UNATTRIBUTED: it was the owner's own admin session (new_api.audit_logs row 1121, auth_method=session, username=root, admin_id=1, role=100, matching other_info.status_time to the second, 14s after a failing test_time) — his own later message to a lane said he had been adjusting the config. It was disabled again 2026-09-26T07:03:33Z (audit row 1127) after measurement showed 43's members are a strict subset of 44's at an identical 0.003 bid while priority 300 made it the first call on every request. Nothing scheduled writes these rows: sync_newapi_channels.py declares only the ch-tierN-* names.", 'Client-side fallback-chain order and provider settings for all three OpenCrabs profiles (owner-granted 2026-09-19)', 'The Inferhub watch forum and its factory lanes (HQ thread 2, worker threads 32 and 559, Grafana thread 557)', "This factory's own crons and its daily GitHub Actions sweep"] |
| does not own | ['The New-API gateway itself — its container, config and serving behaviour on apps (Infra Factory / LLM Gateway lane). We author the channel policy; they run the gateway.', 'Grafana deployment and provisioning, and the generic /grafana skill tooling in /root/vds-servers (Infra Factory)', 'The upstream provider api.inferhub.dev — external; we measure it and never change it', 'OpenCrabs core source (/root/opencrabs): we may file fork issues for runtime anomalies we observe, but we never open PRs or edit source (external-lane boundary)', "Other member factories' repos, lanes and process law", 'Host and box infrastructure (owner)'] |
| substrates owned | ['leshchenko1979/inferhub-watch', "skills/inferhub/SKILL.md — this factory's process law; HQ-only authorship", 'Postgres inferhub_logs on apps — route_metrics, usage_logs, model_rollup', 'Grafana dashboard inferhub-watch — panels and queries', 'The new_api channels table — priority, auto_ban and model_mapping policy. Live 2026-09-27: three rows, ids 43 (disabled) / 44 (enabled) / 46 (auto-banned); the tier ladder is gone and no automatic writer runs.'] |
| attested at | 2026-09-27T06:36:31Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| inferhub-usage-logs-sync | agent | cron 2d9112a6-b697-4eeb-b6ac-3e2462e23483, expr 23 */6 * * *, enabled — TAIL-ONLY: its prompt carries --skip-data --skip-scoreboard --skip-switch, so it pages no API and writes no table; the usage_logs data leg belongs to the no-wake host runner /usr/local/bin/inferhub-usage-sync.sh (*/10 — no daemon, no session, no tokens). Do NOT read this cron as the writer of route_metrics or usage_logs | 6h |
| inferhub-hq-pacemaker | agent | cron 5c960cfb-16a5-4a35-918b-5acd1d30336f, expr 0 */6 * * *, enabled, delivers to session 359fe71b | 6h |
| inferhub-daily-report | owner | cron 0120d22f-9974-4f81-a687-e1c152141bea, expr 0 8 * * *, enabled, deliver_to session:359fe71b-c7a1-420b-b856-acfb49939a7b — the HQ lane re-posts it to Telegram thread 2; it does NOT deliver to the thread itself | daily |
| inferhub-self-audit-daily | agent | cron 3d1d00e1-6a41-4088-a1de-aeb6e9a4863c, expr 0 9 * * *, enabled, delivers to session 359fe71b | daily |
| inferhub-auto-switcher | agent | cron fef19c4f-ab16-442e-8ee9-e041d3d0919b, expr 33 */6 * * *, DISABLED | disabled |
| watch.yml scheduled sweep | agent | host crontab dispatcher /usr/local/bin/inferhub-sweep-dispatch.sh at 17 2 * * * (declared once in repo scripts/sweep_schedule.py), which calls gh workflow run; the workflow's own on.schedule line is a deduped BACKSTOP — measured over all 27 scheduled runs to 2026-09-22 it fires +0.7 h to +12.2 h late, mean +5.2 h, and the delay tracks the declaration. Do not treat 02:17Z as GitHub-side | daily 02:17Z (host crontab) |

**Announcements reaching this factory**

- 🔵 **`ops-fallback-chain-reordered`** — The ops-profile client fallback chain is now inferhub, openrouter, opencode, gemini — best-first by measured per-hop success rate. It was gemini, opencode, openrouter, inferhub, which put three hops at or below 27.8 percent success ahead of one at 99.1 percent. Any lane running on the ops profile now reaches a provider through this order. The reorder was made live by config hot-reload with no daemon restart.
  - affects: profile · since: 2026-09-19T12:21:40Z · declared by: inferhub-watch
- 🟡 **`inferhub-auto-route-failure-escalation`** — Routing through the ops fallback chain's first hop (inferhub) is currently degrading, independent of the retired auto-switcher: measured over 24h to 2026-09-27T05:08Z, 21,242 requests with 2,852 failures (13.4%) — 499 client-abort x1218, 502 'upstream chain exhausted' x994, 429 rate-limit x486, 402 bid-starved x140 — concentrated on cheap iq-75-plus combo members (two gemini effort-variant aliases at ~76% failure over 7d, zai/glm-5.3 at ~97%). Not model-specific and not load-shaped.
  - affects: profile · since: 2026-09-27T06:36:31Z · declared by: inferhub-watch

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| InferHub Watch: Fallback Publisher Diversity & Predictors | 2 | hq | `359fe71b-c7a1-420b-b856-acfb49939a7b` | InferHub Watch: Fallback Publisher Diversity & Predictors | resolved | telegram | 2026-09-27T07:49:47Z | — |
| Worker — HQ cycles | 32 | worker | `8cbe2d61-79c6-4ca7-8a71-805e2982d4b6` | Telegram: Inferhub watch / Worker — HQ cycles [chat:-1004379632866:topic:32] | resolved | telegram | 2026-09-17T00:37:10Z | — |
| Grafana | 557 | grafana | `7814fc64-e7ce-4274-a4ee-372563aa3c99` | Telegram: Inferhub watch / Worker — #23 Grafana management [chat:-1004379632866:topic:557] | resolved | telegram | 2026-09-25T14:15:57Z | — |
| worker: inferhub-watch-lane | 559 | worker | `1122b15e-0b26-420f-a7b3-d0719479bbd5` | worker: inferhub-watch-lane | resolved | telegram | 2026-09-27T07:51:07Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `inferhub-auto-switcher` | ops | `33 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:33:00+00:00 | — | — |
| `inferhub-daily-report` | ops | `0 8 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T05:00:00+00:00 | session:359fe71b-c7a1-420b-b856-acfb49939a7b | — |
| `inferhub-hq-pacemaker` | ops | `0 */6 * * *` | UTC | yes | 1 | **absent** | 2026-09-27T18:00:00+00:00 | session:359fe71b-c7a1-420b-b856-acfb49939a7b | — |
| `inferhub-self-audit-daily` | ops | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T06:00:00+00:00 | session:359fe71b-c7a1-420b-b856-acfb49939a7b | — |
| `inferhub-usage-logs-sync` | ops | `23 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-27T18:23:00+00:00 | — | — |

Attribution basis: deliver_to -> lane, name prefix.
2 of 5 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### infra-factory — Infra Factory

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-09-27T10:39:50Z |
| purpose | Keep the VDS fleet (vpn, apps, agents) and the services it hosts observable, healthy and self-healing: intake Gatus alerts, diagnose hosts, apply safe remediation, and own the fleet infrastructure source repo. |
| profile | `ops` |
| repo | `/root/vds-servers` |
| law | `/root/vds-servers/skills/infra-factory/SKILL.md` — revision 0.1.0 |
| owns | ['Fleet host operations on vpn, apps and agents - diagnosis (host-diag), service and container lifecycle, disk cleanup and safe remediation', 'Gatus monitoring: endpoint configuration, alert intake and recovery routing (gatus-notify on vpn)', 'The fleet infrastructure source repo /root/vds-servers - fleet configs, host scripts, the process register and the factory ledger', 'Host and workspace hygiene: the single reap policy (tools/hygiene.py), its derived gate line, and disk-threshold remediation', 'The Mac access path as fleet infrastructure - the CDP tunnel to the Mac and the route pin on its physical NIC', 'Infra Factory process law and its own lanes (HQ, Triage, Surveys)'] |
| does not own | ['OpenCrabs daemon and harness source, and its development process (/root/opencrabs) - that is opencrabs-dev', 'The factory template, cross-factory laws and fleet measurement - that is meta-factory', 'ai-antispam business logic, its outreach campaign and its Postgres state - that is ai-antispam', 'Miidas product and accounting logic - that is miidas; this factory owns only host-level uptime for its containers', 'InferHub model routing, pricing and token economics - that is inferhub-watch', 'Application logic of services hosted on the fleet (tg-scanner-hub, llm-gateway): hosted and monitored here, changed in their own repos', "Other profiles' brain files and configuration (default, family)", 'The OpenCrabs log-guard watchdog and its root-crontab line on agents (/usr/local/bin/opencrabs-log-guard.sh) - host infrastructure operated by the owner (Alexey). Its source exists in no factory repo, so no factory can declare it as code it owns; it mitigates a closed OpenCrabs daemon defect class (leshchenko1979/opencrabs#21).'] |
| substrates owned | ['/root/vds-servers - the fleet infrastructure source repo (single-writer: its ledger and evidence are appended by tools/ledger.py alone)', 'The fleet hosts vpn, apps and agents - host-level state: systemd units, containers, disk, /usr/local/bin scripts', 'Gatus monitoring configuration and alert routing on vpn', 'The Mac access path (vpn/mac-access: CDP tunnel and route pin)'] |
| attested at | 2026-09-27T10:39:50Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| Gatus fleet monitoring and alert intake | owner | vpn: vpn/services/gatus/config/config.yaml, delivered by gatus-notify.service (active) | continuous; alerts on endpoint failure |
| infra-triage-patrol | agent | cron d6119dbc-95d2-4341-aeb5-dc1c839cc9ed to the Triage lane; gate /root/vds-servers/tools/triage_preflight.py | 6-hourly (0 */6 * * *) |
| infra-surveys-daily | agent | cron 73e9a3d0-8dfe-48db-a169-3fae3d2a0405 to the Surveys topic (thread 7) | daily 09:00 MSK (0 9 * * *) |
| infra-sender-logs-check | agent | cron 8198815c-45e0-40ff-87d1-bfa19d038c5b to the Triage topic (thread 5) | daily 18:05 (05 18 * * *) |
| host-diag | agent | /usr/local/bin/host-diag on vpn, apps and agents (source vpn/services/gatus/scripts/host-diag) | on demand - alert or patrol |
| Fleet disk cleanup | owner | /usr/local/bin/vds-cleanup.sh on vpn, apps and agents; delegates to /root/vds-servers/scripts/cleanup-unified.sh | weekly, Sun 03:00 (root crontab) - plus on demand at disk >=89% |
| Scratch hygiene reaper | agent | root crontab on agents: python3 /root/vds-servers/tools/hygiene.py --clean | hourly - a host script, not a lane wake |
| infra-handler-escalation-check | agent | cron be4c38ce-d8f6-4d64-b4fe-eaa711af71cc - thin trigger that wakes the TG Hub lane (a360e13f-4e34-4fac-8a1d-770644040903) when a downstream handler goes unactioned past 24 h; delivers no report of its own | daily 00:00 (0 0 * * *) |
| questions.l1979.ru answer surface | owner | vpn: /etc/caddy/Caddyfile vhost questions.l1979.ru -> reverse_proxy 127.0.0.1:8099 (/opt/questions/backend.py under questions-backend.service), serving /srv/questions; the site is basic_auth gated (401 without credentials). Pages and register are pushed agents -> vpn by the oc-questions-push.path systemd USER unit on agents. | continuous; accepts a posted answer and returns it to the asking lane session |

**Announcements reaching this factory**

- 🟡 **`cron-result-lost-on-restart`** — A cron job whose run is interrupted by an OpenCrabs daemon restart delivers its result to NO channel: boot revival resumes the turn with no job identity, run id or deliver_to, so the job output reaches nobody. Ship-chain hot-reloads make restarts frequent, so any factory relying on cron delivery is exposed.
  - affects: profile · since: 2026-09-19 · review by: 2026-10-07 · declared by: infra-factory
- 🔵 **`vds-servers-single-writer-route`** — /root/vds-servers is single-writer and commit-gated: peers must not commit to it, and fleet changes (host config, Gatus, cleanup, host-diag) are routed to Infra Factory HQ rather than edited in place.
  - affects: profile · since: 2026-09-19 · declared by: infra-factory
- 🟡 **`gatus-config-carries-live-credentials`** — vpn/services/gatus/config/config.yaml carries live credentials in plaintext, including SSH private-key blocks. Never grep it with a context flag (-A/-B), and never print a parsed form of it - json.dumps of a single endpoint dict renders the key field verbatim. Read the KEY NAMES only; to compare a value, hash it in place. The read discipline is necessary but not sufficient: the PRINT is the second chokepoint, and it is the one that fails when the read felt safe.
  - affects: profile · since: 2026-09-23 · review by: 2026-10-07 · declared by: infra-factory
- 🟡 **`mac-cdp-tunnels-flap-on-sleep`** — The Mac's CDP and SSH tunnels flap because the Mac sleeps: it drops each SSH connection after roughly 2 minutes, and vpn's sshd then kills it 90s later (clientaliveinterval 30 x clientalivecountmax 3). The listener on vpn:4444 disappears while the Mac sleeps, so any browser task through the Mac CDP path fails intermittently - and no overlay fixes it, because a sleeping host is offline on every transport, Tailscale included.
  - affects: profile · since: 2026-09-26 · review by: 2026-10-10 · declared by: infra-factory
- 🟡 **`ops-daemon-dies-at-cgroup-cap`** — The ops daemon has died mid-turn at its cgroup soft cap with zero OOM kills — three core dumps on 2026-09-27 (06:13:19 SEGV, 06:20:02 SEGV, 06:27:27 BUS) with memory.events high climbing and MemoryPeak measured ABOVE MemoryHigh. An unanswered notify to any ops-profile lane may therefore be a crash, not indiscipline — re-notify rather than assume the lane declined.
  - affects: profile · since: 2026-09-27T06:13:19Z · review by: 2026-10-11 · declared by: infra-factory

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| HQ | 4 | hq | `6a314aac-94db-4b11-974c-f53decc25b9d` | Telegram: Infra Factory / HQ [chat:-1004486255170:topic:4] | resolved | telegram | 2026-09-26T18:44:13Z | — |
| Gatus alert routing and fleet triage | 5 | triage | `fb67ca75-8735-4c39-80be-06b59bd4365f` | Gatus alert routing and fleet triage | resolved | telegram | 2026-09-26T08:21:48Z | — |
| Surveys | 7 | surveys | `8daa376e-367c-452d-840f-0c18d66ef60a` | Telegram: Infra Factory / Surveys [chat:-1004486255170:topic:7] | resolved | telegram | 2026-09-25T11:08:30Z | — |
| LLM Gateway | 467 | gateway | `8b278a4f-531d-4d7b-8c79-87d30f9257bd` | Telegram: Infra Factory / LLM Gateway [chat:-1004486255170:topic:467] | resolved | telegram | 2026-09-26T14:14:04Z | — |
| TG Hub | 475 | _unstated_ | `a360e13f-4e34-4fac-8a1d-770644040903` | Telegram: Infra Factory / TG Hub [chat:-1004486255170:topic:475] | resolved | telegram | 2026-09-24T13:28:58Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `infra-handler-escalation-check` | ops | `0 0 * * *` | UTC | yes | 0 | **absent** | 2026-09-28T00:00:00+00:00 | — | P=$(XDG_RUNTIME_DIR=/run/user/0 systemctl --user show opencrabs.service… |
| `infra-sender-logs-check` | ops | `05 18 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-27T15:05:00+00:00 | — | — |
| `infra-surveys-daily` | ops | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T06:00:00+00:00 | — | — |
| `infra-triage-patrol` | ops | `0 */6 * * *` | UTC | yes | 0 | present | 2026-09-27T18:00:00+00:00 | — | /root/vds-servers/tools/triage_preflight.py |

Attribution basis: name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
4 of 4 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### meta-factory — Factories

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-09-27T12:18:15Z |
| purpose | Build, measure and evolve Autonomously Self-Improving Factories: maintain the ASIF template and rulebook that any repository can adopt, and consult member factories on their process health, cadence and autonomy. |
| profile | `ops` |
| repo | `/root/agent-factories` |
| law | `/root/agent-factories/skills/meta-factory/SKILL.md` — revision 0.1.30 |
| owns | ['the template instrument surface — methodology, development and cross-member deployment (owner-commissioned 2026-09-27)', 'the ASIF template and rulebook (TEMPLATE/ and the derived laws)', 'the fleet registry (registry/)', 'member-factory surveys, scores and the measurement cadence', 'the pacemaker and outer-trigger methodology (P28)', "this factory's own process law (skills/meta-factory/SKILL.md)"] |
| does not own | ["member factories' products, backlogs, repos and code", "member factories' ontologies and issue boards", 'the OpenCrabs runtime, daemon and core tools - a client-supplier loop, not ownership', 'token provisioning, model routing and inference pricing (InferHub Watch)', 'the tg_* tool surface (fast-mcp-telegram)'] |
| substrates owned | ['/root/agent-factories', '/root/agent-factories/skills/meta-factory/SKILL.md', '/root/agent-factories/registry/'] |
| attested at | 2026-09-27T12:18:15Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| factory-measurement-daily | agent | cron factory-measurement-daily | daily 09:00 MSK (06:00Z) |
| factory-triage-patrol | agent | cron factory-triage-patrol | every 6h |
| factory-insights-weekly | agent | cron factory-insights-weekly | weekly, Fri 18:00 MSK (15:00Z); fires only when its trigger_cmd exits 0 |
| factory-template-weekly | agent | cron factory-template-weekly | weekly, Mon 09:00 MSK (06:00Z); fires only when its trigger_cmd exits 0 |
| factory-growth-map-biweekly | agent | cron factory-growth-map-biweekly | 1st and 15th, 09:00 MSK (06:00Z) |
| factory-registry-attest | agent | cron factory-registry-attest | daily 06:00Z |
| factory-publish | agent | cron factory-publish | every 6h (UTC) |

**Announcements reaching this factory**

- 🟡 **`pacemaker-triggers-still-pass-mode-quiet`** — Pacemaker cron triggers on this box still pass --mode quiet for three jobs, NONE of them meta-factory's: ai-antispam-owner-digest and ai-antispam-triage-sweep (ai-antispam), and oc-triage-owner-digest (opencrabs-dev) — all three enabled. The owner re-ruling of 2026-09-19T03:34:30Z / 03:36:54Z made turn-end THE default for all lane traffic and retained quiet only for batch/fan-out notices whose ack contract is the ledger; a single-lane pacemaker is not batch/fan-out, so each of these defers instead of waking an idle lane immediately. Meta-factory's jobs were moved to explicit --mode turn-end on 2026-09-23 (byte-verified; schedule and next_run_at preserved); five of its six now carry it, and factory-registry-attest carries none because its prompt writes no /tmp redirect at all. Infra-factory's four now read plain --mode turn-end with no cap flags, so the pattern is demonstrated by a second factory rather than asserted. CAUTION FOR WHOEVER FIXES THE REMAINING THREE — the cap flag cannot be dropped alone: each carried --mode quiet --quiet-for-secs 20 --max-delay-secs 30, and its prompt documented WHY the cap was there, namely that quiet's DEFAULT starvation cap of 1800s blocks past the tool's 120s budget and kills the trigger. That hazard is quiet-specific and vanishes under turn-end, so the mode and the cap move TOGETHER and the sentence justifying the cap must be rewritten with them, or the prompt ends up arguing for a flag it no longer carries. Read live 2026-09-26T06:20Z: of 57 cron rows, 12 jobs carry --mode — 9 turn-end, 3 quiet. The previous census in this notice (2026-09-23T11:31Z: of 55 cron rows, 13 carry --mode — 10 turn-end, 3 quiet) is kept as the step this one follows, never overwritten.
  - affects: profile · since: 2026-09-19T03:36:54Z · declared by: meta-factory
- 🔵 **`brain-metrics-baseline-measured`** — Brain metrics are a STANDING reading with an instrument: tools/brain_metrics.py (no args needed; --home / --hours / --log-dir) prints all three legs with their predicate, population and instant, and gates none of them. The clause that binds it is docs/measurement-procedure.md section 5; its gate is tests/test_brain_metrics.py. A figure in this notice is a DATED READING and never current — run the instrument.

LEG C IS EXPLAINED, NOT BROKEN — and the explanation was corrected on 2026-09-27, so the earlier wording is superseded rather than repeated. What is dormant is the AUTOMATIC THRESHOLD TRIGGER, not compaction itself. Measured: the gate's own log line (compaction.rs:418, "triggering LLM compaction") has fired 0 times since the 1M window, and nothing has crossed the 65-percent gate = 650000 tokens, which is what measures the ceiling. The only pressure-band reading (compaction.rs:911, band 55.0 to 65.0 half-open) is 56 percent on 2026-09-26 from session 2646d31a and 55 percent on 2026-09-27 from session 0117dd29 — one line per day, each a band ENTRY rather than a daily maximum, so it cannot establish the highest context any session reached; a session peaking below 55 percent emits nothing at all. But save_compaction_summary_to_memory runs on ANY compaction, and compaction still arrives by paths that do not need the threshold: the single 2026-09-26 note came from a MANUAL /compact (session dcd8f7a9, 22:08:40Z — "Compact context now", then 22:09:12Z "Context was manually compacted"), i.e. owner-initiated. The previous text said the summarizer line "is never emitted"; that is FALSE and this replaces it.

TWO CORRECTIONS to a reading that circulated, both category errors worth naming: (a) the "110423 / 1000000 input tokens" line reports the SUMMARIZER'S PAYLOAD against its own input budget (context.rs:1086-1092 prints running_tokens / snapshot_max_tokens), which is NOT the gate's usage reading — that is compaction.rs:418's "triggering LLM compaction", and it has fired zero times; conjoining the two is what produced the claim that compaction fired below the threshold. (b) FullWindow is a CompactionScope (WHAT gets compacted), not a trigger KIND.

CONSEQUENCE WORTH KNOWING BEFORE YOU TRUST A SEARCH: save_compaction_summary_to_memory is the SOLE writer of memory/<date>.md, so a note exists only for a day in which compaction fired — and at a 1M window the threshold almost never fires. Measured 2026-09-27: notes exist for 09-19, 09-20, 09-21 and 09-26 only; 09-22 through 09-25 have none. memory_search's DEFAULT scope is exactly those notes, so default-scope recall is blind for every day that has none, while memory.db keeps indexing. Measured 2026-09-27: there were TWO manual /compact requests on 2026-09-26 (17:46:48Z and 22:08:29Z) for ONE saved summary, so even the human-initiated supply produced 1 of 2 — both event supplies are unreliable, the threshold one dead and the manual one lossy. The pipeline is STARVED, NOT STOPPED — and its remaining supply is HUMAN-INITIATED compaction, which is the operational point: an event trigger that no longer fires is not a trigger, so a note pipeline that must be reliable needs a CLOCK, not an event.

Fresh reading 2026-09-27T11:10:23Z: LEG A, the always-injected Tier 0 triple (SOUL.md, USER.md, AGENTS.md; named in docs/methodology/04-harness-binding.md; these live in NO repository, so a leg-A reading has an INSTANT for its identity and no revision) 813 lines / 205148 bytes / about 58614 tokens = 29.31 percent of a 200k window — AGENTS.md alone is 756 lines / 200459 bytes = 97.71 percent of leg-A bytes and 92.99 percent of its lines — 256 lines over the owner's 500-line budget marker, which is PRINTED and never gated. LEG B, every skills/*/SKILL.md at depth 1: 869 lines / 95510 bytes / about 27289 tokens = 13.64 percent. TOGETHER 1682 lines / 300658 bytes / about 85903 tokens = 42.95 percent of a 200k window, which is 8.59 percent of the 1M window now configured. The two differ by exactly 5.0x, so always read the denominator beside the figure. The reading chain is kept, never overwritten: 29.76 percent (2026-09-23T11:28:08Z), then 34.97 percent (2026-09-25T06:08:47Z), then 39.97 percent (2026-09-26T06:21:02Z), then this one. That is +2.98 points in one day and +13.19 points in four, and AGENTS.md is most of it. CAUTION: the trigger line "Context at NN percent" at compaction.rs uses a DIFFERENT denominator (effective tokens over effective max, i.e. the window minus reserves) and must never be read as a fraction of the provider window.
  - affects: profile · since: 2026-09-19T14:20:00Z · declared by: meta-factory

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| Surveys | 19 | surveys | `5c99ad51-8889-40cb-b589-fa13fd673c06` | Telegram: Factories / Surveys [chat:-1004497192134:topic:19] | resolved | telegram | 2026-09-23T10:47:40Z | — |
| Agent Factories Triage Lane | 20 | triage | `f4c192c9-a8e9-4268-9026-ee3e4970cc8a` | Agent Factories Triage Lane | resolved | telegram | 2026-09-27T03:10:12Z | — |
| Meta-Factory HQ: ASIF Architecture & Crons | 21 | hq | `2646d31a-71ee-49f0-be81-9c8dc32d32fa` | Meta-Factory HQ: ASIF Architecture & Crons | resolved | telegram | 2026-09-27T03:10:01Z | — |
| Delegate | 68 | delegate | `23549292-77ff-40d1-97e3-5aa0bdd19d74` | Telegram: Factories / Delegate [chat:-1004497192134:topic:68] | resolved | telegram | 2026-09-26T10:41:51Z | — |
| Worker | 1271 | worker | `dcd8f7a9-c1e7-48c3-b184-d901dc08eac7` | Telegram: Factories / Worker [chat:-1004497192134:topic:1271] | resolved | telegram | 2026-09-27T10:44:35Z | — |
| Factories / Ledger | 3981 | ledger | `d0cba805-92c9-4377-8808-a1cf715bce9e` | Telegram: Factories / Ledger [chat:-1004497192134:topic:3981] | resolved | telegram | 2026-09-27T03:28:19Z | — |
| Factories / Open Question Tool | 4087 | questions | `9f635151-4311-44ab-94f8-d4fd86e9b6c2` | Telegram: Factories / Open Question Tool [chat:-1004497192134:topic:4087] | resolved | telegram | 2026-09-27T11:34:31Z | — |
| Factories / Pacemakers / Crons | 4223 | pacemakers | `ee5cd2f5-6c1b-41bb-b031-1150a3132fb1` | Telegram: Factories / Pacemakers / Crons [chat:-1004497192134:topic:4223] | resolved | telegram | 2026-09-27T11:32:37Z | — |
| Factories / Instruments methodology | 4186 | methodology | `4515ea72-eb39-4a3c-9b05-a1dc02b1c977` | Telegram: Factories / Instruments methodology [chat:-1004497192134:topic:4186] | resolved | telegram | 2026-09-27T09:11:06Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `factory-growth-map-biweekly` | ops | `0 9 1,15 * *` | Europe/Moscow | yes | 0 | **absent** | 2026-10-01T06:00:00+00:00 | — | — |
| `factory-insights-weekly` | ops | `0 18 * * Fri` | Europe/Moscow | yes | 0 | **absent** | 2026-10-02T15:00:00+00:00 | — | python3 /root/agent-factories/tools/synthesize_insights.py --audit |
| `factory-measurement-daily` | ops | `0 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T06:00:00+00:00 | — | — |
| `factory-publish` | ops | `0 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-27T18:00:00+00:00 | — | — |
| `factory-registry-attest` | ops | `0 6 * * *` | UTC | yes | 0 | **absent** | 2026-09-28T06:00:00+00:00 | — | — |
| `factory-template-weekly` | ops | `0 9 * * Mon` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T06:00:00+00:00 | — | python3 /root/agent-factories/tools/roadmap.py --cadence |
| `factory-triage-patrol` | ops | `0 */6 * * *` | UTC | yes | 0 | **absent** | 2026-09-27T18:00:00+00:00 | — | out=$(gh issue list -R leshchenko1979/agent-factories --state open --li… |

Attribution basis: name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
7 of 7 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

### miidas — Miidas Factory

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-09-27T11:39:51Z |
| purpose | MIIDAS is an ecosystem of applied business AI for Russian SMB owners — dedicated Telegram AI executive assistants provisioned as per-client managed agent containers, plus the platform that mints, binds and bills them. |
| profile | `ops` |
| repo | `/root/miidas` |
| law | `/root/miidas/SKILL.md` — revision 1.1.26 |
| owns | ['/root/miidas platform repo (agent, landing, manager, cdp components) and its deploys to apps', 'leshchenko1979/miidas and leshchenko1979/miidas-template', 'per-client slot state: pool/slots/miidas-*.env on apps — apps root /data/projects/miidas/, so the live path is /data/projects/miidas/pool/slots/ — plus the miidas-* container and miidas_* volume namespaces', 'the Miidas Factory Telegram chat (-1003996392908) and its topics', '/root/miidas/SKILL.md — the live skill path is a symlink to it, so the repo file is the single writer', 'cron miidas-hq-daily-trigger', 'the miidas LLM-gateway service user and manager/llm_keys.py key lifecycle', 'leshchenko1979/miidas-landing — the public landing, recipe hub and course surface (miidas.ru) at /root/miidas-landing'] |
| does not own | ['client product surfaces — the per-client groups, the onboarding funnel, the client-facing forum. Those are the product, never the factory surface', "the LLM gateway itself (llm.l1979.ru) — consumed, not operated; we own only our service user's key lifecycle", "the apps host beyond our own compose stack — other projects' containers and volumes, host packages, other factories' cron rows", "other factories' repos, chats and processes", 'OpenCrabs core and the dev process'] |
| substrates owned | ['leshchenko1979/miidas', 'leshchenko1979/miidas-template', 'leshchenko1979/miidas-landing', '/root/miidas/SKILL.md (live skill path is a symlink to it)', 'apps: pool/slots/miidas-*.env at /data/projects/miidas/pool/slots/ and the miidas-* compose stack under /data/projects/miidas/compose/'] |
| attested at | 2026-09-27T11:39:51Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| miidas-manager | agent | ./manager/deploy.sh | always-on; slot projection into Postgres every 60s |
| miidas-cdp | agent | ./cdp/deploy.sh | always-on (shared headless Chrome) |
| miidas-ru-proxy | agent | docker compose, miidas-pool network port 8888 | always-on (WireGuard egress for RU portals) |
| miidas-<slug> | owner | ./agent/deploy.sh then restart.sh --slug <slug> | always-on, one per bound slot |
| miidas landing | owner | ./landing/deploy.sh | request-driven (nginx on miidas.l1979.ru) |
| miidas-hq-daily-trigger | owner | cron 0 9 * * * | daily 09:00 UTC |

**Announcements reaching this factory**

- 🟡 **`miidas-volume-namespace-on-apps`** — The miidas_* Docker volume namespace and the miidas-* container namespace on apps belong to the MIIDAS factory. A peer reclaiming or pruning on apps must match the ^miidas_ prefix and must never match a bare substring: miidas-pixel-data belongs to a different project and is not ours. Live estate read 2026-09-27T11:38Z: 5 running containers - miidas-manager, miidas-trial, miidas-maple-c23a, miidas-ru-proxy, miidas-cdp; 1 volume matching ^miidas_ (miidas_maple-c23a-data); miidas-pixel-data present, unowned and untouched. The second volume this notice carried until 2026-09-24 (miidas_probe-gw-1789692412-data, with its matching orphaned slot lock) was reaped on 2026-09-24 while clearing the manager's duty-scan FAIL.
  - affects: profile · since: 2026-09-13T09:56:00Z · declared by: miidas
- 🔵 **`llm-gateway-per-service-user`** — The LLM gateway (llm.l1979.ru) carries a dedicated NON-root service user per consumer rather than one shared fleet credential: miidas (id 5, role 1, management credential NEWAPI_MIIDAS_TOKEN, quota 500000000000 units), alongside peer service users avito-bot and opencrabs-fleet. A factory provisioning LLM keys for its own clients should ask the gateway owner for its own service user rather than reuse the fleet root credential.
  - affects: profile · since: 2026-09-18T01:53:06Z · declared by: miidas
- 🔵 **`miidas-hq-daily-trigger-is-ours`** — cron miidas-hq-daily-trigger (0 9 * * *, enabled, delivers to session e4f96a33-45ac-412e-8788-1b678cf2addb, the HQ topic) is the MIIDAS factory's own pacemaker. Peers must not disable, repace or repoint it.
  - affects: profile · since: 2026-09-11T00:00:00Z · declared by: miidas
- 🟡 **`miidas-platform-compose-is-repo-written`** — The miidas platform compose on apps (/data/projects/miidas/compose/docker-compose.yml) is written from our repo: manager/deploy.sh:33, landing/deploy.sh:27 and deploy-all.sh:36 each scp the repo copy over the live one, so a host-side edit there is silently reverted by the next of those deploys. That directory deliberately carries no .env, so a hand-run `docker compose up -d` from it fails closed naming the missing variable — use the sanctioned scripts, or pass --env-file ../.master.env.
  - affects: profile · since: 2026-09-26 · declared by: miidas
- 🔵 **`miidas-kit-forks-declared`** — miidas vendors the fleet kit pin (registry/kit.json) and declares 16 divergences from it in registry/kit-exemptions.json. Its gate 23 (tests/test_kit_pin_member.py) reds on any UNDECLARED divergence and passes clean today: 21 carried paths judged, 16 forks declared, 0 undeclared. A peer porting a kit instrument into this factory must add the exemption entry in the same change, or the factory audit goes red - that refusal is deliberate, not drift.
  - affects: profile · since: 2026-09-27T05:24:07Z · declared by: miidas
  - evidence: Measured 2026-09-27T11:44Z by the registry writer: tests/test_kit_pin_member.py rc=0, 'judged 21 carried path(s); 1 factory-class path(s) excluded by class; 16 declared exempt'; pin version 6ab591c618ec, 128 paths declared. The gate path is named in the text because the loader's `check` field names an ALLOWLISTED predicate and is never executed - a path there is refused.
- 🟡 **`miidas-slot-volume-git-config-carries-remote-credential`** — Until leshchenko1979/miidas#61 lands, every miidas client slot volume's .git/config (mode 644) carries the template remote with an inline account-level token. A peer reclaiming, copying, backing up or decommissioning a miidas slot volume must treat the VOLUME as secret-bearing: it outlives the container, and the credential is readable by the client's own agent, not only by a host operator.
  - affects: profile · since: 2026-09-27T11:39:51Z · declared by: miidas

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| HQ | 4 | hq | `e4f96a33-45ac-412e-8788-1b678cf2addb` | Telegram: Miidas Factory / HQ [chat:-1003996392908:topic:4] | resolved | telegram | 2026-09-24T10:04:41Z | — |
| Agent runtime | 6 | _unstated_ | `5a5335ee-db68-46fe-b13e-a082b2beadb5` | Telegram: Miidas Factory / Agent runtime [chat:-1003996392908:topic:6] | resolved | telegram | 2026-09-25T17:34:45Z | — |
| Manager | 9 | _unstated_ | `b64ca6ba-9ec0-47f7-8450-0d25b6c1d854` | Telegram: Miidas Factory / Manager [chat:-1003996392908:topic:9] | resolved | telegram | 2026-09-25T16:25:13Z | — |
| Worker | 56 | worker | `b57efabd-85df-4467-bed7-f5a596285f68` | Telegram: Miidas Factory / Worker — #25 CLIENT_KIND backfill + telemetry projection [chat:-1003996392908:topic:56] | resolved | telegram | 2026-09-25T22:49:43Z | — |
| Marketing | 393 | marketing | `39d2b612-dbfc-4953-ae02-609267c68c3e` | Telegram: Miidas Factory / Marketing [chat:-1003996392908:topic:393] | resolved | telegram | 2026-09-26T14:57:07Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `miidas-hq-daily-trigger` | ops | `0 9 * * *` | UTC | yes | 0 | **absent** | 2026-09-28T09:00:00+00:00 | session:e4f96a33-45ac-412e-8788-1b678cf2addb | — |

Attribution basis: deliver_to -> lane.

### opencrabs-dev — Opencrabs Dev Factory

| Field | Value |
|---|---|
| freshness | ✅ attested 2026-09-27T12:20:27Z |
| purpose | Build and ship the OpenCrabs daemon that every lane on this box runs on, and author the process law those lanes follow: a gated source-to-swap pipeline, a versioned skill set, and a workers-ledger that records who holds what. |
| profile | `ops` |
| repo | `/root/opencrabs` |
| law | `/root/.opencrabs/profiles/ops/skills/opencrabs-dev/SKILL.md` — revision 0.4.267 |
| owns | ['the OpenCrabs source fork leshchenko1979/opencrabs and its carrier build and swap pipeline', 'the opencrabs-dev skill set: SKILL.md, the five role files, fleet-directives.md and the runbooks', 'the workers-ledger and skill-version consensus', 'the CLI tool fleet under tools/, authored by the Toolsmith lane inside this factory', 'the fork issue board on leshchenko1979/opencrabs'] |
| does not own | ['the fast-mcp-telegram substrate and its tg_* tool family', 'the meta-factory registry, its surveys and its scoring surface', 'the live daemon configuration on this box: config.toml, keys.toml and the running units', "member factories' own process law, repos and backlogs", 'upstream adolfousier/opencrabs, which receives PRs only and never issues'] |
| substrates owned | ['the OpenCrabs source fork and its carrier build pipeline', 'the opencrabs-dev skill set and the workers-ledger'] |
| attested at | 2026-09-27T12:20:27Z |

**Services**

| name | audience | entry | cadence |
|---|---|---|---|
| Build and swap a new daemon binary | agent | the Editor lane's oc-deploy ship --sha <full-sha> --execute | on request |
| Process-law amendment | agent | session_notify to the HQ lane | on request |
| CLI tool defect intake and fix | agent | session_notify to the Toolsmith lane | on request |
| Version release and ledger consensus | agent | oc-ledger sync --version <v> | per skill version bump |
| Fork issue intake and triage | agent | the Triage lane on leshchenko1979/opencrabs | on request |
| Owner decision surfacing (Open Questions register) | agent | oc_questions ask --factory <KEY> (dynamic tool; the asking session comes from OPENCRABS_SESSION_ID and must NOT be passed by the caller) | on request |

**Announcements reaching this factory**

- 🟡 **`notify-now-mode-retired`** — session_notify's 'now' mode is RETIRED and passing it FAILS the delivery outright - it is not merely discouraged. 'turn-end' is the default and wakes an idle target immediately, so it loses nothing 'now' ever delivered; 'quiet' is retained for batch notices whose ack contract is the ledger. 'interrupt' is the URGENT tier (#393): it delivers at the SAME boundary as turn-end and adds precedence framing so the target yields its current plan and answers in that turn - never deferred, never a default, spell it explicitly. It is NOT pre-emption: no boundary exists inside a running tool call, so a mid-turn target still queues for its next tool-loop boundary. Legacy interrupt:true UPGRADES a non-quiet resolution to that tier. A 'no wake observed' confirm verdict means the target is mid-turn; never re-send on it.
  - affects: profile · since: 2026-09-19 · review by: 2026-12-19 · declared by: opencrabs-dev

**Lanes**

| topic | thread | role | session | session title | status | channel | last active | lane announcements |
|---|---|---|---|---|---|---|---|---|
| bash guard forced-variation design | 7198 | _unstated_ | `329bf3a3-6299-4173-b991-7ea0427563e3` | bash guard forced-variation design | resolved | telegram | 2026-09-27T10:23:23Z | — |
| Mermaid | 29947 | _unstated_ | `c6b1a539-6225-40ea-a514-67d21a446cd5` | Telegram: Opencrabs Dev Factory / Mermaid [chat:-1003936827469:topic:29947] | resolved | telegram | 2026-09-27T01:10:52Z | — |
| Gemini Reasoning and Flow Message Analysis | 30045 | _unstated_ | `127429e6-08de-439c-9162-2c8b0a9f73d9` | Gemini Reasoning and Flow Message Analysis | resolved | telegram | 2026-09-27T06:54:47Z | — |
| Telegram: Push | 30090 | editor | `d18ce16a-75a0-447c-90c7-ab7dabce4411` | Editor lane: #17/#19 channel-ownership PRs | resolved | telegram | 2026-09-24T11:58:12Z | — |
| OC Compiler | 30129 | _unstated_ | `1539f410-b844-4001-8e9d-b063d8469dcd` | Telegram: Crabs Kanban Board / OC Compiler [chat:-1003936827469:topic:30129] | superseded | telegram | 2026-08-28T17:08:16Z | — |
| Deploy #235 Option Collision Guard | 30134 | _unstated_ | `1a63f103-b899-4ad2-a5b3-c89f2902bf97` | Deploy #235 Option Collision Guard | resolved | telegram | 2026-09-22T21:16:18Z | — |
| OC DEV HQ | 30220 | hq | `0117dd29-5f4b-4184-9bf4-d19dc74ac266` | Telegram: Opencrabs Dev Factory / OC DEV HQ [chat:-1003936827469:topic:30220] | superseded | telegram | 2026-09-27T10:07:10Z | — |
| Subagents | 30517 | _unstated_ | `a5b34466-1c14-441f-b2c6-6eaf4f316dde` | Telegram: Opencrabs Dev Factory / Subagents [chat:-1003936827469:topic:30517] | resolved | telegram | 2026-09-25T12:42:43Z | — |
| Telegram: Throttling | 30679 | _unstated_ | `61161247-5b1d-4efe-979b-bf46ffc85c48` | Telegram: Opencrabs Dev Factory / Telegram: Throttling [chat:-1003936827469:topic:30679] | resolved | telegram | 2026-09-27T04:45:06Z | — |
| Graceful restart | 31683 | _unstated_ | `7e1ebbb6-68b3-478b-abc2-b697e70c2f37` | Telegram: Opencrabs Dev Factory / Graceful restart [chat:-1003936827469:topic:31683] | resolved | telegram | 2026-09-24T12:02:14Z | — |
| Plan tool | 31789 | _unstated_ | `462181e9-ad99-4163-bd3d-c983c48049a8` | Telegram: Opencrabs Dev Factory / Plan tool [chat:-1003936827469:topic:31789] | resolved | telegram | 2026-09-26T22:48:29Z | — |
| Issue #234: Review Implementation Button | 31847 | _unstated_ | `2fbfb2f8-9b08-417a-aae8-c75edc1de1ea` | Issue #234: Review Implementation Button | resolved | telegram | 2026-09-27T07:13:26Z | — |
| Memory: Compaction | 34653 | _unstated_ | `cbdfde4a-b3fe-457a-817b-5113b938f12d` | Telegram: Opencrabs Dev Factory / Compaction visibility [chat:-1003936827469:topic:34653] | superseded | telegram | 2026-09-27T10:16:52Z | — |
| Vector memory | 36841 | _unstated_ | `212b3c83-6659-49c8-9984-0cf849f769c1` | Telegram: Opencrabs Dev Factory / Vector memory [chat:-1003936827469:topic:36841] | resolved | telegram | 2026-09-27T03:06:11Z | — |
| Toolsmith Issue 255 and PR Dependency Laws | 39171 | toolsmith | `2fae1230-de9e-4fa5-aa24-822cf7188c3e` | Toolsmith Issue 255 and PR Dependency Laws | resolved | telegram | 2026-09-27T08:20:00Z | — |
| Harvesting upstream PRs into OpenCrabs | 39218 | _unstated_ | `4b0990b7-aff8-4744-8de5-e38e54de7693` | Harvesting upstream PRs into OpenCrabs | resolved | telegram | 2026-09-27T10:24:23Z | — |
| Rich resume wire | 39862 | _unstated_ | `c10cd97b-2c99-49fa-a1c4-d78a02dfd7d1` | Telegram: Opencrabs Dev Factory / Rich resume wire [chat:-1003936827469:topic:39862] | resolved | telegram | 2026-09-27T10:21:48Z | — |
| Loop guard | 39883 | _unstated_ | `40427d4f-af4a-48ba-993f-f5f0b21916c0` | Telegram: Opencrabs Dev Factory / Loop guard [chat:-1003936827469:topic:39883] | resolved | telegram | 2026-09-27T06:55:34Z | — |
| #83 config-manager-warn | 40011 | _unstated_ | `c2ba4ef2-eac3-406c-98d6-c861c5bebec2` | Telegram: Opencrabs Dev Factory / #83 config-manager-warn [chat:-1003936827469:topic:40011] | resolved | telegram | 2026-09-27T10:30:39Z | — |
| #87 config-write-types | 40479 | _unstated_ | `aff7ff41-a3a7-4c53-adc5-80fb7a33ba50` | Telegram: Opencrabs Dev Factory / #87 config-write-types [chat:-1003936827469:topic:40479] | resolved | telegram | 2026-09-27T07:17:18Z | — |
| #89 memory-search-parity | 40524 | _unstated_ | `42a44908-b8f3-42e1-bbd2-f2a672b8056e` | Telegram: Opencrabs Dev Factory / #89 memory-search-parity [chat:-1003936827469:topic:40524] | resolved | telegram | 2026-09-27T01:49:15Z | — |
| Harvest rich-host buttons | 40695 | _unstated_ | `aaa8d8ae-a4be-4b89-9f92-01a317075be3` | Telegram: Opencrabs Dev Factory / Harvest rich-host buttons [chat:-1003936827469:topic:40695] | resolved | telegram | 2026-09-27T08:24:13Z | — |
| Harvest retry-429 ladder | 40696 | _unstated_ | `afe476f8-279b-4d54-b628-c9d7e35873c8` | Telegram: Opencrabs Dev Factory / Harvest retry-429 ladder [chat:-1003936827469:topic:40696] | resolved | telegram | 2026-09-25T16:19:27Z | — |
| Core: Goal Loop | 42311 | _unstated_ | `9fa7c71a-f009-418a-ac06-d0336efcf491` | Telegram: Opencrabs Dev Factory / Core: Goal Loop [chat:-1003936827469:topic:42311] | resolved | telegram | 2026-09-27T10:21:20Z | — |
| Role split | 42360 | _unstated_ | `63d775f9-18e2-4097-8696-d9a2ca796f14` | Telegram: Opencrabs Dev Factory / Role split [chat:-1003936827469:topic:42360] | resolved | telegram | 2026-09-27T01:33:51Z | — |
| Triage: Issue Portfolio & Harvest Analysis | 42487 | triage | `530c29ec-596e-43a4-9c7e-1b6dfc3cd870` | Triage: Issue Portfolio & Harvest Analysis | resolved | telegram | 2026-09-27T08:22:58Z | — |
| oc-waiter + #111 durable-notify | 42744 | _unstated_ | `facd50af-0807-4fee-942b-008bff037f6f` | Telegram: Opencrabs Dev Factory / oc-waiter + #111 durable-notify [chat:-1003936827469:topic:42744] | resolved | telegram | 2026-09-18T17:39:21Z | — |
| #92 demoted-host guard | 42940 | _unstated_ | `c78e78e0-099e-455e-8dfb-7e9b8f7d13e5` | Telegram: Opencrabs Dev Factory / #92 demoted-host guard [chat:-1003936827469:topic:42940] | resolved | telegram | 2026-09-27T10:14:30Z | — |
| Telegram flow card metrics telemetry bar #232 | 43727 | _unstated_ | `95bec69b-0e96-46a9-9d91-dc355e8af18f` | Telegram flow card metrics telemetry bar #232 | resolved | telegram | 2026-09-27T01:24:38Z | — |
| Governance: Ontology & RSI | 43993 | _unstated_ | `6630dc9a-0eeb-46c2-95b8-bfae43e0766b` | Telegram: Opencrabs Dev Factory / Governance: Ontology & RSI [chat:-1003936827469:topic:43993] | resolved | telegram | 2026-09-27T10:12:47Z | — |
| Multicalls | 44326 | _unstated_ | `a38499fc-76a4-4aff-8953-fa5931ad0e5c` | Telegram: Opencrabs Dev Factory / Multicalls [chat:-1003936827469:topic:44326] | resolved | telegram | 2026-09-25T21:05:31Z | — |
| Fix #149: Cron Session Isolation | 49607 | _unstated_ | `6cd8175f-fb27-4cf3-a390-971ff2519a47` | Fix #149: Cron Session Isolation | resolved | telegram | 2026-09-27T10:27:41Z | — |
| Skills | 49643 | _unstated_ | `4b4463d5-381c-4458-aa0c-3cf199882084` | Telegram: Opencrabs Dev Factory / Skills [chat:-1003936827469:topic:49643] | resolved | telegram | 2026-09-27T10:22:21Z | — |
| Deploy issue 248 default group command scopes | 50566 | _unstated_ | `52058a75-e94b-4400-9e07-aac3a891bb1f` | Deploy issue 248 default group command scopes | resolved | telegram | 2026-09-27T01:37:50Z | — |
| FlowLine::System split — #291 header fix | 51188 | _unstated_ | `2ed8adeb-4784-4159-b68f-0e552490641e` | FlowLine::System split — #291 header fix | resolved | telegram | 2026-09-25T21:32:43Z | — |
| 🔍 PROBE review-155 | 51714 | _unstated_ | `fcfbcd89-1392-4234-9b88-e13afc30d474` | Telegram: Opencrabs Dev Factory / 🔍 PROBE review-155 [chat:-1003936827469:topic:51714] | resolved | telegram | 2026-09-11T14:55:01Z | — |
| JEV Classifier | 68049 | _unstated_ | `ef83024b-90c8-40fc-8490-e8c2879808ab` | Telegram: Opencrabs Dev Factory / JEV Classifier [chat:-1003936827469:topic:68049] | resolved | telegram | 2026-09-25T12:46:54Z | — |

**Pacemakers**

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `538-probe-boundary-delivery` | ops | `0 3 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T03:00:00+00:00 | telegram:-1003936827469:49607 | cat /tmp/538-payload.txt |
| `oc-harvest-18-resume` | ops | `0 7 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T07:00:00+00:00 | session:7e1ebbb6-68b3-478b-abc2-b697e70c2f37 | — |
| `oc-harvest-225-resume` | ops | `0 8 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T08:00:00+00:00 | session:a5b34466-1c14-441f-b2c6-6eaf4f316dde | — |
| `oc-harvest-250-resume` | ops | `15 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:15:00+00:00 | session:63d775f9-18e2-4097-8696-d9a2ca796f14 | echo HARVEST-PENDING-250 |
| `oc-harvest-318-resume` | ops | `20 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:20:00+00:00 | session:212b3c83-6659-49c8-9984-0cf849f769c1 | echo HARVEST-PENDING-318 |
| `oc-harvest-321-resume` | ops | `15 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:15:00+00:00 | session:cbdfde4a-b3fe-457a-817b-5113b938f12d | echo HARVEST-PENDING-321 |
| `oc-harvest-326-resume` | ops | `30 14 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T14:30:00+00:00 | session:aaa8d8ae-a4be-4b89-9f92-01a317075be3 | — |
| `oc-harvest-341-resume` | ops | `45 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:45:00+00:00 | session:facd50af-0807-4fee-942b-008bff037f6f | — |
| `oc-harvest-344-resume` | ops | `45 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:45:00+00:00 | session:127429e6-08de-439c-9162-2c8b0a9f73d9 | — |
| `oc-harvest-345-resume` | ops | `50 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:50:00+00:00 | session:6630dc9a-0eeb-46c2-95b8-bfae43e0766b | — |
| `oc-harvest-346-resume` | ops | `35 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:35:00+00:00 | session:aff7ff41-a3a7-4c53-adc5-80fb7a33ba50 | echo HARVEST-PENDING-346 |
| `oc-harvest-348-resume` | ops | `40 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:40:00+00:00 | session:c78e78e0-099e-455e-8dfb-7e9b8f7d13e5 | echo HARVEST-PENDING-348 |
| `oc-harvest-364-resume` | ops | `30 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:30:00+00:00 | session:9fa7c71a-f009-418a-ac06-d0336efcf491 | echo HARVEST-PENDING-364 |
| `oc-harvest-396-resume` | ops | `15 9 20 9 *` | UTC | **no** | 0 | **absent** | 2027-09-20T09:15:00+00:00 | session:1a63f103-b899-4ad2-a5b3-c89f2902bf97 | — |
| `oc-harvest-402-resume` | ops | `0 18 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T18:00:00+00:00 | session:52058a75-e94b-4400-9e07-aac3a891bb1f | L=/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-ledger; o… |
| `oc-harvest-403-resume` | ops | `45 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-26T15:45:00+00:00 | session:afe476f8-279b-4d54-b628-c9d7e35873c8 | D=/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools; L="$D/state… |
| `oc-harvest-421-resume` | ops | `25 15 * * *` | UTC | **no** | 0 | **absent** | 2026-09-25T15:25:00+00:00 | session:212b3c83-6659-49c8-9984-0cf849f769c1 | echo HARVEST-PENDING-421 |
| `oc-harvest-dispatch-4h` | ops | `15 3,9,15,21 * * *` | UTC | **no** | 1 | present | 2026-09-19T03:15:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | — |
| `oc-health-hourly` | ops | `0 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:00:00+00:00 | — | — |
| `oc-roster-detached-sweep` | ops | `5 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:05:00+00:00 | — | ROSTER=/root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-rost… |
| `oc-triage-factory-patrol` | ops | `0 */6 * * *` | UTC | yes | 1 | present | 2026-09-27T18:00:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | — |
| `oc-triage-owner-digest` | ops | `30 9 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-28T06:30:00+00:00 | — | — |
| `oc-upstream-delta-watch` | ops | `15 */6 * * *` | UTC | **no** | 1 | present | 2026-09-19T00:15:00+00:00 | session:530c29ec-596e-43a4-9c7e-1b6dfc3cd870 | /root/.opencrabs/profiles/ops/skills/opencrabs-dev/tools/oc-upstream-de… |

Attribution basis: deliver_to -> chat, deliver_to -> lane, name prefix.
`trigger_cmd` is truncated to 72 characters here; the full command is in `registry/index.json`.
3 of 23 job(s) carry no explicit `deliver_to`. The column is rendered as the live row holds it; whether a null falls back to the creating session or to nothing is the scheduler's contract, and this registry does not assert it.

## Unattributed jobs

Read from the declared profile homes: 3 home(s) opened, 61 job row(s). Homes read: family, oc348probe, ops.

These rows name no known factory in their `deliver_to` and match no naming prefix. They are rendered rather than dropped: a job the registry cannot place is a finding, not an omission. Each row carries the profile home it was read from, so a row that should not be here can be found and changed without guessing which home owns it.

| job | home | cron_expr | timezone | enabled | set_goal | goal_template | next_run_at | deliver_to | trigger_cmd |
|---|---|---|---|---|---|---|---|---|---|
| `tamara_accounting_sync` | family | `0 21 * * *` | Europe/Moscow | yes | 0 | **absent** | 2026-09-27T18:00:00+00:00 | telegram:-1004286036984 | — |
| `tmp-nulltrigger-probe` | ops | `4 */6 * * *` | UTC | **no** | 0 | **absent** | 2026-09-19T00:04:00+00:00 | — | — |
| `tmp-trigger-control-neg` | ops | `0 0 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T00:00:00+00:00 | — | printf 'BEHIND\t0\n' |
| `tmp-trigger-control-pos` | ops | `0 0 1 1 *` | UTC | **no** | 0 | **absent** | 2027-01-01T00:00:00+00:00 | — | printf 'BEHIND\t3\n' |

---

Generated file. Edit `registry/factories/<slug>.json` instead, then re-render.
