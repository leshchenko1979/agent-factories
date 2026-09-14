# Field Notes from Five Autonomous AI Factories: Where Time Actually Goes

> **Context:** Engineering findings and operational telemetry from five agent factories running in production (OpenCrabs dev, InferHub Watch, AI AntiSpam, Miidas, and Meta-Factory).
> **Data source:** `evidence/insights.jsonl` and `docs/growth-stages.md`.

---

## The Reality of Multi-Agent Workflows

Benchmarking AI coding agents usually focuses on generation speed: how many seconds it takes a model to write a function or pass a test suite.

In an environment with five autonomous factories handling issues, pull requests, and background maintenance, that measurement turned out to be mostly irrelevant.

Tracking timestamps from issue intake to production merge showed that tasks were taking an average of **10.4 hours**. The model spent only 20 to 25 minutes writing code and running tests. The remaining ten hours were spent sitting in a backlog waiting for a human operator to notice the ticket and kick off a session.

Closing that gap required addressing traditional systems engineering problems rather than prompt tuning:
- Automated dispatchers without mutual exclusion cause race conditions on git branches.
- Centralized code auditing agents burn tokens and hallucinate findings; measurement works better as a local self-audit script with verifiable receipts.
- Orchestration patterns must evolve as daily throughput increases from five tasks a week to hundreds of events a day.

---

## Core Findings

### 1. Queue dwell time dominates task duration (`queue-lag-trap`)
* **Initial expectation:** Factory throughput depends on inference latency, prompt caching, and test run times.
* **Observed data:** In InferHub Watch, measuring task lead time revealed an average of 10.4 hours (`37,620s`). Active agent execution was 20–30 minutes. Tasks spent 95% of their duration waiting for triage.
* **Working solution:** A scheduled dispatcher that matches unassigned issues to persistent worker lanes on an hourly cycle, moving work from manual batches into an automated pipeline.

### 2. Autonomous dispatch causes git race conditions (`concurrency-locking-paradox`)
* **Initial expectation:** Once issue assignment is automated, workers can simply poll the backlog and pick up tasks.
* **Observed data:** When human coordination was removed, agents frequently picked the same issue simultaneously. They created divergent branches from the same commit, clobbered each other's work, and corrupted state files.
* **Working solution:** A single-writer ledger backed by `fcntl.flock(LOCK_EX)` and `os.fsync`. Every state transition (`intake` → `claim` → `run` → `close`) is an atomic append. A worker must hold an exclusive lock on the ledger row before creating a git branch.

### 3. External auditing agents fail to scale (`auditor-trap-iso9001`)
* **Initial expectation:** Fleet-wide compliance can be checked by a central agent that inspects other repositories from the outside.
* **Observed data:** External inspection spent thousands of tokens parsing file trees, frequently misidentified project structures, and produced false positives. Member teams ignored guidelines until an audit was run.
* **Working solution:** An internal self-audit script (`tools/audit.py`) provided in the factory template. Each project runs its own audit, computing first-pass yield, rework rate, and task lead time. The central layer verifies only that the ledger sequence is monotonic, file locks exist, and test execution receipts are present.

### 4. Topic binding requires native substrate support (`substrate-topic-binding`)
* **Initial expectation:** Standard messaging interfaces like Telegram topics work out of the box for multi-agent coordination.
* **Observed data:** Autonomous worker lanes deadlocked because the platform required an inbound user message before a session could bind to a forum topic.
* **Working solution:** A direct feedback loop between the factories and the OpenCrabs harness maintainers, resulting in native topic auto-binding on message ingestion (`telegram_send action: "bind_topic"`, Issue `#170`).

---

## Evolution of Factory Architecture

Factory tooling requirements change as throughput increases:

* **Stage 0 (1–5 tasks/week):** Single prompt sessions with an operator. Bottleneck is operator attention.
* **Stage 1 (5–50 tasks/week):** Scheduled issue polling. Bottleneck is queue dwell time and task claiming collisions.
* **Stage 2 (50–200 events/day):** Single-writer state ledgers and atomic OS file locks. Bottleneck is untracked rework and silent test failures.
* **Stage 3 (200–1,000 events/day):** Local self-audit tooling tracking lead time and first-pass yield. Bottleneck is runtime harness limitations and token cost.
* **Stage 4 (1,000+ events/day):** Multi-factory networks with shared feedback loops into core tooling and inference providers.

---

## Publication Drafts

### English Post / Thread

We run five software projects almost entirely on autonomous AI agents. For a long time we assumed throughput was high because code generation takes under a minute and unit tests pass quickly.

Then we started measuring real timestamps from issue creation to merge.

The average task took 10.4 hours.
Active agent coding was around 25 minutes.

For the other ten hours, the issue simply sat in GitHub waiting for someone to open a laptop, triage the ticket, and start an agent session. 95% of the lifecycle was queue wait time.

The obvious fix was automated dispatch: run a background process that checks for open issues and hands them to persistent worker agents automatically.

Queue wait time dropped from ten hours to minutes.
Immediately after that, we hit concurrency collisions.

Without human coordination, two agents waking up at the same time would grab the same issue, create conflicting git branches, and overwrite each other's commits. Telling them in a prompt not to touch tasks assigned to others failed whenever both read the issue list at the same moment.

The fix was standard systems programming: an OS-level file lock (`fcntl.flock`) on an immutable single-writer ledger. If an agent cannot acquire an exclusive lock and atomically record its claim on disk, it is not allowed to touch git.

Our second mistake was trying to enforce standards with an external "inspector" agent that reviewed other repositories. It burned tokens, misunderstood repo layouts, and hallucinated false issues.

We switched to a self-audit model: each factory repository runs its own measurement script (`audit.py`) tracking first-pass yield, rework rate, and task lead time. The central layer only verifies ledger sequence integrity and gate exit codes.

Autonomous agent fleets hit the exact same bottlenecks as traditional software engineering: queue dwell time, shared resource locking, and verifiable telemetry.

Repository and architecture notes: github.com/leshchenko1979/agent-factories

---

### Russian Article / Post (Telegram / Miidas)

Заметки о работе пяти автономных AI-фабрик: где на самом деле теряется время

У нас сейчас пять проектов работают почти полностью на автономных агентах: движок OpenCrabs, аналитика InferHub Watch, боты модерации, инфраструктура. Со стороны кажется, что общую скорость определяет модель: как быстро она генерирует код и проходит тесты. LLM выдает функцию за двадцать секунд, тесты отрабатывают за минуту. Кажется, что разработка идет с предельной скоростью.

Потом мы написали скрипт аудита и посчитали реальный lead time — время от момента, когда в GitHub заводится issue, до момента, когда готовый коммит оказывается в мастере.

Оказалось, средняя задача живет 10,4 часа. При этом модель пишет код и гоняет тесты от силы минут двадцать пять. Все остальные десять часов тикет просто лежит в репозитории и ждет, пока кто-то из нас зайдет в GitHub, разберется в контексте и запустит агента руками. Вся скорость уходила в ожидание в очереди.

Логичный шаг — убрать человека из диспетчеризации. Мы поставили фоновый процесс, который раз в час сканирует новые тикеты и сам передает их свободным воркерам.

Очередь сократилась с десяти часов до нескольких минут. Но следом вылезла проблема параллелизма: аг��нты начали конкурировать за задачи.

Когда человек распределяет работу руками, он держит контекст в голове: этот тикет делает один агент, тот — другой. Автономные агенты о существовании друг друга не знают. Если два воркера проснулись одновременно, они оба видят первый открытый issue, делают две разные ветки от одного коммита, параллельно пушат и ломают репозиторий. Попытки решить это промптами вроде «проверь, не делает ли эту задачу кто-то еще» не работают, если оба агента прочитали список тикетов в одну и ту же секунду.

Пришлось вернуться к базовым вещам из системного программирования. Мы сделали единый журнал состояний (`ledger.jsonl`), куда последовательно пишутся все этапы задачи: регистрация, взятие в работу, запуск тестов, закрытие. И закрыли его блокировкой на уровне операционной системы через `fcntl.flock` со сбросом буфера на диск (`os.fsync`). Если агент не смог захватить эксклюзивный лок на файл и атомарно записать строчку о том, что задача взята, он к коду и веткам вообще не прикасается.

Второй вопрос, с которым мы столкнулись — контроль качества. Сначала мы попробовали сделать отдельного агента-инспектора, который ходил по репозиториям всех пяти фабрик снаружи, смотрел коммиты и проверял соблюдение правил.

Это оказалось неэффективно. Внешний агент сжигал массу токенов на чтение чужих файлов, регулярно путался в незнакомой структуре папок и придумывал ошибки там, где их не было. А главное — команды проектов просто не следили за качеством до тех пор, пока инспектор не прих��дил с проверкой.

Мы перешли на схему внутреннего контроля. Вместо внешнего проверяющего каждый проект получил свой скрипт самоаудита (`tools/audit.py`). Проект сам на каждом цикле считает свой процент задач без доработок, частоту возвратов и реальное время выполнения. А центральный уровень проверяет только технические инварианты: что журнал событий не переписан задним числом, блокировки работают, а тесты действительно запускались, а не просто отмечены в отчете.

Когда один агент помогает писать код в редакторе, о таких вещах не задумываешься. Но когда агентов становится много и они работают сутками без присмотра, узкие места оказываются ровно там же, где и в обычной разработке: в очередях задач, блокировках общих ресурсов и надежности метр��к.

Код шаблона, скрипты блокировок и описание стадий роста фабрик лежат в открытом репозитории:
https://github.com/leshchenko1979/agent-factories
