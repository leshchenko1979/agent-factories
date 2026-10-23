# Линза E: топология интерфейсов командной строки

Объект: `projects/Брокерские-запросы/` — 10 `.py` в постоянном каталоге. Проверено чтением, `--help` каждого скрипта, `trigger_cmd` джобы `broker-requests-daily` и прогонами `--dry-run`.

**Побочный эффект:** `podborka_deck.py --help` не печатает справку, а пересобирает PDF — файл `prezentacii/podborka-GAB-…-10-06.pdf` изменён и восстановлен `git checkout --`, дерево чистое. Это и есть находка 1.

---

**1. CRITICAL** → `projects/Брокерские-запросы/podborka_deck.py:93`
> `slides = [` … `out = '/root/redevest-ai/…/podborka-GAB-kurchevskaya-2026-10-06.pdf'` (:98) … `print('OK', out, len(slides), 'slide(s)')` (:106)

**Дефект:** нет `argparse` и `__main__`. Сборка идёт при любом запуске и при импорте: `--help`, опечатка во флаге, `import` — всё перезаписывает версионированный артефакт. Проверено: `--help` → `OK … 1 slide(s)`, `git status` → `M` по PDF.
**Правка:** `main(argv)` + `argparse(--out, --dry-run)` под `__main__`; данные лота — параметром, не литералом.

**2. HIGH** → `podborka_map.py:50`
> `lat, lon = float(sys.argv[1]), float(sys.argv[2])`

**Дефект:** шесть позиционных аргументов без имён и умолчаний; `--help` даёт `ValueError: could not convert string to float: '--help'` и трассировку.
**Правка:** `argparse` с `lat lon --zoom --size --out`, при нехватке — `parser.error`.

**3. HIGH** → `reestr_touch.py:638`
> `if new_offer and event not in core.OFFER_EVENTS:`

**Дефект:** гейт стоит на одном флаге из шести. `--track`, `--customer`, `--topic`, `--analysis`, `--cp`, `--new-round` вне своего события молча проглатываются: проверено `--event party_touch_sent --track market` — rc=0, в сводке ни слова.
**Правка:** таблица `EVENT_FLAGS = {event: {allowed}}`, посторонний флаг → `TouchError`.

**4. HIGH** → `reestr_touch.py:1007` (и `reestr_send.py:155`)
> `party_id=args.party or args.peer,`

**Дефект:** при обоих флагах `--peer` молча игнорируется. Проверено: `--party agranov-svetly-a1 --peer agranov-svetly-p1` → записано автору, rc=0. Старый скрипт, куда дописали новый флаг, пишет не тому адресату без предупреждения.
**Правка:** расхождение значений → `parser.error`; `--peer` — в `SUPPRESS` с deprecation.

**5. HIGH** → `reestr_core.py:86`
> `OFFER_EVENTS = ("batch_sent", "broadcast_sent", … "refusal", "deal_closed", …)`

**Дефект:** `refusal`, `deal_closed`, `batch_sent`, `broadcast_sent` лежат и в `REQUEST_EVENTS`, и в `OFFER_EVENTS`; смысл выбирается наличием `--offer`. Проверено: `--event refusal` без `--offer` → `стадия closed` (закрывается вся строка), с `--offer` → отказ по предложению. Забытый флаг закрывает запрос, а `closed` не удаляется.
**Правка:** развести глаголы (`request_refusal` / `offer_refusal`), старые имена — алиасами.

**6. HIGH** → `reestr_send.py:177`
> `if not core.in_send_window() and not args.force:`

**Дефект:** окно 09:00–19:00 проверяется до ветки `if args.dry_run:` (:198). Планирование («сначала посмотреть план», README:50) после 19:00 МСК отказывает, хотя ничего не отправляет.
**Правка:** `if not args.dry_run and not core.in_send_window() and not args.force:`.

**7. HIGH** → `podborka_deck.py:78`
> `PLYUSHCHIHA = [('Округ', 'Хамовники (ЦАО)'), … ('Окупаемость', '11,3 года'), …]`

**Дефект:** цепочка «подборка → deck → PDF» не автоматизирована: цифры скопированы из `zaprosy-brokerov-GAB-2026-09-28.md` в литералы. Докстринг сам признаёт: «источник правды — разбор, а не этот скрипт». Расхождение уже есть: разбор:23 — «два слайда», скрипт после ревизии 08.10 даёт один.
**Правка:** читать секцию 3 разбора, литералы удалить, отсутствие ключа — ошибка.

**8. MEDIUM** → `README.md:99`
> `Скрипты печатают в stdout и **ничего не пишут в файлы, кроме реестра** через `reestr_touch.py`.`

**Дефект:** неверно: `podborka_deck.py:98` пишет PDF, `podborka_map.py:46` — PNG. Документ обещает read-only там, где запуск меняет версионированный файл.
**Правка:** оговорка «кроме сборщиков материалов».

**9. MEDIUM** → `migrate_reestr_v2.py:302`
> `path.write_text(text, encoding="utf-8")`

**Дефект:** второй писатель `reestr.yaml`, пишет мимо `core.save_atomic` (:215), существующего именно потому, что «прямая запись запрещена». Обрыв оставит битый YAML; линтер после записи не запускается.
**Правка:** `save_atomic` + `reestr_lint.check` перед выходом; после миграции — в архив.

**10. MEDIUM** → `reestr_due.py:342`
> `day = core.parse_date(args.today) if args.today else core.today_msk()`

**Дефект:** опечатка в `--today` даёт `ValueError: month must be in 1..12, not 13` трассировкой (проверено). В кроне `trigger_on: non_empty` считает stderr — трассировка сама подожжёт job и уйдёт агенту как «вывод обхода».
**Правка:** `type=` с обёрткой, дающей `parser.error`.

**11. MEDIUM** → `reestr_core.py` (нет `__main__`)
> `python3 reestr_core.py --help` → пусто, rc=0

**Дефект:** любой аргумент молча даёт успех. `python3 reestr_core.py due` «успешно» ничего не делает — успех без работы.
**Правка:** `__main__` с rc=2 и сообщением «библиотека, точка входа — reestr.py».

**12. MEDIUM** → `README.md:17`
> таблица «Что где лежит» — 5 строк реестра; `migrate_reestr_v2.py`, `podborka_deck.py`, `podborka_map.py`, `prezentaciya_presnya99_deck.py` не упомянуты (`grep -c` = 0)

**Дефект:** 4 из 10 скриптов без документированного места; два одноразовые — миграция завершена (`version: 2`), `prezentaciya_presnya99_deck.py` собирает лот, не идущий в подборку (12,7 года > порога 12).
**Правка:** строка на каждый; одноразовые — в `archive/`.

**13. MEDIUM** → `.opencrabs/skills/broker-requests/SKILL.md:41`
> `python3 projects/Брокерские-запросы/reestr_due.py --today <дата> --no-chats`

**Дефект:** ручной обход описан с `--today` и `--no-chats`, крон запускает без обоих. Две процедуры одной цепочки: ручная не увидит ответа в чате, крон увидит; расхождение не отмечено нигде.
**Правка:** один канон в SKILL.md, крон ссылается на него.

**14. LOW** → `trigger_cmd` джобы `broker-requests-daily`
> `… reestr_due.py; else … reestr_lint.py; fi; if [ "$(date +%u)" = "1" ]; then … reestr_due.py --summary; fi; git status --porcelain -- …/reestr.yaml`

**Дефект:** три интерпретатора и два чтения YAML на обход; сводка приклеена без разделителя, агент различает её по прозе. Звено «touch → commit» живёт только текстом промпта (шаг 3); `save_atomic` не блокирует файл, при двух писателях последний выигрывает молча.
**Правка:** `reestr.py walk` одной командой; коммит — подкомандой, чтобы пропуск был виден по rc.

---

## Единая точка входа

`reestr.py lint | due [--today D] [--no-chats] [--summary] | touch … | send … | walk`. Один `--path`, один `--date` вместо пары `--today`/`--date`, гейт «флаг ↔ событие» в одном месте. Тесты не ломаются: `test_reestr.py` импортирует модули, CLI не вызывает.

Ломается четыре места, первое — молча: **`trigger_cmd`** (три пути; после переименования `if` упадёт, `else` напечатает «can't open file» в stderr, `non_empty` подожжёт job с трассировкой — ежедневно), `SKILL.md:40–42`, `README.md:36–75` (11 вызовов), `plan-sistema-napominanii.md:472–476`. Порядок: шим поверх существующих `main()`, правка `trigger_cmd` тем же коммитом, документы, потом удаление старых точек входа.

---

FINDINGS: 14 — CRITICAL 1, HIGH 6, MEDIUM 6, LOW 1.
