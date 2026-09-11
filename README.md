# Agent Factories

Best practices for organizing **agent factories** — the structure that turns a
repository plus a Telegram group into a self-driving delivery line run by AI
agents under human supervision.

This repo is the **shared surface** for that work: one place to compare the
factories, extract what actually holds up, and turn it into a reusable pattern.

## The four factories

| Factory | Purpose | Factory chat | Primary repos |
|---|---|---|---|
| **OpenCrabs development** | Build and ship the OpenCrabs agent itself | `Crabs Kanban Board` (forum, topic per lane/role) | `leshchenko1979/opencrabs` (fork, issues home), `adolfousier/opencrabs` (upstream, PRs only), `opencrabs-skill`, `opencrabs-dev-state` |
| **InferHub Watch** | Daily probes + value ranking of InferHub routes (IQ per $) | `Inferhub watch` (forum: `HQ`, `Worker — #N …`, `Done — #N …`) | `leshchenko1979/inferhub-watch` |
| **Miidas** | Multi-tenant Telegram AI platform (warm-pool trial → managed bot per client) | *(not yet on the topic system)* | `leshchenko1979/miidas`, `leshchenko1979/miidas-template` |
| **AI AntiSpam** | LLM spam moderation bot + monoforum outreach campaign | `ai-antispam` (plain group, cron sink — *not yet on the topic system*) | `alexeyleshchenko/ai-antispam`, `leshchenko1979/ai-antispam-outreach` |

## Status

| # | Factory | On the topic system? | Process law lives in |
|---|---|---|---|
| 1 | OpenCrabs development | ✅ yes — 20+ topics, 4 roles | `skills/opencrabs-dev/` (SKILL.md + 4 role files + fleet-directives.md) |
| 2 | InferHub Watch | ✅ yes — HQ + one topic per worker | `skills/inferhub/SKILL.md` + `ONTOLOGY.md` + `WORKLOG.md` |
| 3 | Miidas | ❌ no | repo `AGENTS.md` + `docs/adr/` + per-component `AGENTS.md` |
| 4 | AI AntiSpam | ❌ no | repo `CLAUDE.md` + `memory-bank/` + `skills/outreach-reply-sweep/` |

## Contents

| Doc | What |
|---|---|
| [docs/factories.md](docs/factories.md) | Per-factory survey: purpose, surface, repos, roles, process law, automation, verification |
| [docs/survey-2026-09-11.md](docs/survey-2026-09-11.md) | The dated first survey with the receipts behind every claim |
| [docs/best-practices.md](docs/best-practices.md) | Derived patterns (v0.1 hypothesis — to be validated, not gospel) |
| [docs/gaps.md](docs/gaps.md) | What the two un-transferred factories are missing, and the migration shape |

## Working assumption

The factory is not the repo and not the chat — it is the **pairing** of a
versioned process law, a chat surface that carries state in its topic names,
and a repo whose issues are the task list. Remove any leg and the factory
degrades into "a repo some agent edits sometimes".
