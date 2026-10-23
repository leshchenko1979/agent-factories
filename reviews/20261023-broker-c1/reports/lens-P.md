# LENS P — Pacemaker & Autonomous Convergence: `broker-requests-daily`

Объект: cron `4342f13d-5d23-458a-9f7d-c64472ca7274`, `0 10 * * *`, `Europe/Moscow`, `trigger_on=non_empty`, `set_goal=0`, `deliver_to=telegram:-1002928607356:18358`. Проверено 23.10: 21 прогон в `cron_job_runs`, ручной запуск `trigger_cmd` из БД, `src/cron/`, скилл, логи.

## FINDINGS

### 1. HIGH — Гейт падает открытым по таймауту, а его потолок ниже одного Telegram-чтения

**Locator:** `/root/opencrabs/src/cron/trigger.rs:88`; `/root/redevest-ai/projects/Брокерские-запросы/reestr_due.py:33`

**Verbatim Quote:**
```
timeout: Duration::from_secs(30),
CHAT_TIMEOUT = 40
```

**Defect Analysis.** Без `--no-chats` (`reestr_due.py:348`) скрипт делает `tg-mcp-call` на каждую строку с таймаутом 40 с (`reestr_due.py:192`), а весь `trigger_cmd` ограничен 30 с. Один зависший мост съедает бюджет, и `scheduler.rs:289` падает открытым (fail-open): сессия стартует с пустым `{output}` и платит полный бюджет (~$7.9) без строк и дефектов.

**Actionable Remediation.** Вернуть `--no-chats` либо поднять потолок до ≥260 с; на таймауте — fail-closed.

### 2. HIGH — Ручной обход в SKILL.md расходится с кроном по трём пунктам при заявлении «тем же порядком»

**Locator:** `/root/.opencrabs/skills/broker-requests/SKILL.md:36` (блок 38–43, утверждение на `:45`)

**Verbatim Quote:**
```
Обход идёт кроном `broker-requests-daily` (10:00 МСК, каждый день) и вручную тем же порядком:
```

**Defect Analysis.** Ручная версия зовёт `--summary` ежедневно (крон — по понедельникам), зовёт с `--no-chats` (крон — без, то есть с живыми чтениями Telegram внутри 30-секундного гейта) и не содержит шага `git status` с коммитом, хотя `:45` обещает ежедневный коммит реестра.

**Actionable Remediation.** Заменить блок дословной копией `trigger_cmd` либо вынести обход в `reestr_walk.sh` и звать из обоих мест.

### 3. HIGH — Одна cron-сессия с 03.10: ~130k токенов на каждый из 30 запросов

**Locator:** `/root/opencrabs/src/cron/scheduler.rs:706`; `cron_job_runs.id=8797a899`

**Verbatim Quote:**
```
Cron job 'broker-requests-daily' — using cron session 956b8df1-b9d9-400c-baea-baad3f35ce10
```

**Defect Analysis.** Сессия `956b8df1` не создаётся заново, а переиспользуется (первое сообщение 03.10, `seq` на старте 23.10 = 66), поэтому каждый из 30 запросов несёт ~130k входных токенов (`input=129606…130401`): 2 542 415 входных, $7.88 за 4 минуты. `set_goal=0`, терминального условия и cap на turns нет — только `thinking_loop_timeout_secs=600`. Ничто не ограничивает число шагов.

**Actionable Remediation.** Свежая сессия на прогон, явное «после шага 4 закончи» и hard cap итераций.

### 4. MEDIUM — Пропуски гейта пишутся как `success`

**Locator:** `cron_job_runs` — `4679cafa` (22.10), `29d5d57a` (21.10), `c205b21e` (04.10)

**Verbatim Quote:**
```
success | 0 | 0 | 0.0
```

**Defect Analysis.** Если обход сломается, первые дни это «успехи с нулём токенов», неотличимые от пустого дня. `HEARTBEAT.md` пуст: сторожевой проверки «обход реально был?» нет ни в кроне, ни в heartbeat.

**Actionable Remediation.** Статус `skipped` или `error='trigger:empty'`; строка в `HEARTBEAT.md`: «нет прогона с `input_tokens>0` за 3 суток — сказать владельцу».

### 5. MEDIUM — «Пустой день — молчи» недостижимо в норме и вредно при fail-open

**Locator:** `cron_jobs.prompt`, пункт 5 задания `broker-requests-daily`

**Verbatim Quote:**
```
5. Пустой день — молчи, ничего не постить.
```

**Defect Analysis.** При `non_empty` пустой день до сессии не доходит (проверено: 0 байт → снят, 0 токенов), значит в норме пункт мёртв. Пустой `{output}` сессия видит только при fail-open по таймауту — и именно тогда правило велит молчать: деньги потрачены, владелец не знает, что обхода не было.

**Actionable Remediation.** «Если `{output}` пуст — это сбой гейта: запусти обход сам; пустой результат — молчи».

### 6. MEDIUM — Стоимость прогона расходится в 11 раз на одной модели

**Locator:** `cron_job_runs` — `63f7e4f7` (19.10), `434a6179` (18.10), `e15dc997` (20.10)

**Verbatim Quote:**
```
19.10  1 994 276 in  $6.403  → $0.00321 / 1k
18.10  2 390 807 in  $0.666  → $0.00028 / 1k
```

**Defect Analysis.** Провайдер и модель у всех 18 платных прогонов одни (`inferhub / combo/iq-75-plus`), а цена за тысячу входных скачет в 11 раз: `combo/` маршрутизирует на разные апстримы. Бюджетный порог по `cost` считать нельзя.

**Actionable Remediation.** Считать бюджет по `input_tokens + output_tokens`, стоимость — от фактического апстрима.

### 7. MEDIUM — Неверная форма chat_id теряет сообщение в теме 18358 молча

**Locator:** `~/.opencrabs/logs/opencrabs.2026-10-23` (09:54:34, session `b8a02827`)

**Verbatim Quote:**
```
chat=2928607356 thread=Some(18358) len=406 error=A Telegram's error: Bad Request: chat not found
```

**Defect Analysis.** Правильная форма — `-1002928607356` (666 отправок за сегодня), но инструмент получил id без префикса `-100`, и сообщение не дошло — упало WARN'ом в лог, а не ошибкой в диалог.

**Actionable Remediation.** Нормализовать `chat_id` в `telegram_send` либо возвращать ошибку в диалог.

### 8. LOW — Разовое напоминание перевзведено на 2027 год и остаётся включённым

**Locator:** `cron_jobs.name='yadromino-call-reminder-20260922'`

**Verbatim Quote:**
```
enabled=1  last_run_at=2026-09-22T14:40:03Z  next_run_at=2027-09-22T14:40:00+00:00
```

**Defect Analysis.** Отработало 22.09.2026, но осталось `enabled=1`, и планировщик перенёс его на 22.09.2027 — через год разбудит сессию прошедшим звонком.

**Actionable Remediation.** `enabled=0` после согласования с владельцем; авто-выключение одноразовых.

### 9. INFO — Двое часов в одной команде

**Locator:** `cron_jobs.trigger_cmd` (`date +%u`) против `reestr_due.py:342` (`core.today_msk()`)

**Verbatim Quote:**
```
if [ "$(date +%u)" = "1" ]; then … reestr_due.py --summary; fi
```

**Defect Analysis.** `TZ` не задан, `/etc/timezone = Etc/UTC`; сегодня `date +%u` = 5 и `TZ=Europe/Moscow date +%u` = 5 — запуск в 07:00 UTC. Совпадение держится только на часе запуска < 21:00 UTC: сдвиг на вечер — и сводка уедет на вторник, а `--summary` посчитает день по МСК.

**Actionable Remediation.** `TZ=Europe/Moscow date +%u` вместо `date +%u`.

## Проверки с отрицательным результатом

- **Пустой день = ноль токенов.** `trigger_cmd` из БД, 23.10 10:21 UTC: stdout 0, stderr 0, rc=0, 1 с; `reestr_due.py:349` возвращает 0 без печати. stderr учтён (`combined_output()`, `trigger.rs:68–76`); pathspec с кириллицей работает (пусто на чистом реестре, rc=0).
- **Тема 18358 жива:** 666 отправок за сегодня, доставка крона прошла; зависших прогонов нет (18/21 `success`).

## Вердикт по пяти пунктам

| Пункт | Вердикт |
|---|---|
| 1. 0-token quiescence | **PASS** — 0 байт и 0 токенов, stderr учтён; но потолок гейта ниже одного чтения Telegram (н. 1) |
| 2. Понедельничная ветка | **PASS с оговоркой** — при 07:00 UTC совпадает, но на неявном совпадении часов (н. 9) |
| 3. Сходимость | **FAIL** — `set_goal=0`, терминального условия и cap на turns нет (н. 3, 5) |
| 4. Цель доставки | **PASS с оговоркой** — тема жива, но одна отправка ушла с битым `chat_id` (н. 7) |
| 5. Дублирование ручной/крон-версии | **FAIL** — три расхождения при «тем же порядком» (н. 2) |

**FINDINGS: 9** — HIGH: 3 (№1, 2, 3) · MEDIUM: 4 (№4, 5, 6, 7) · LOW: 1 (№8) · INFO: 1 (№9).

Ничего не отправлено, крон не изменён, `reestr_touch.py` на запись не запускался; единственная запись — этот файл.
