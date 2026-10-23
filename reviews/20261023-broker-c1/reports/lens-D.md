# Линза D — удаление и YAGNI

Объект: `projects/Брокерские-запросы/` (≈24 МБ, 19 строк реестра) и `skills/broker-requests/`. Метод: grep по репозиторию (README, план, `index.md`, `log.md`, `routing/telegram-projects.yaml`, `reestr.yaml`, скрипты, `scripts/test_classifier.py`), плюс `git ls-files`, `git log`, `diff`. «Выглядит старым» — гипотеза: у каждого вердикта либо локатор, либо доказанный ноль.

## Вердикты

| Кандидат | Размер | Ссылки | Вердикт | Чем доказано |
|---|---|---|---|---|
| `skills/broker-requests/SKILL.md.2026-10-20T105422.bak` | 15 093 Б | 0 живых; `scripts/law_lint.py` → `DELETION-CANDIDATE` | **DELETE-SAFE** | `diff` с текущим `SKILL.md` = 12 строк, все добавления в текущей версии; побайтово равен коммиту `319d90c` (`git show 319d90c:…SKILL.md \| diff -q - <bak>` → совпадение); untracked, уникального текста нет |
| `__pycache__/` (6 `.pyc`) | 434 358 Б | 0 | **DELETE-SAFE** | `.gitignore:25`; регенерируется импортом |
| `.pytest_cache/` | 6 246 Б | 0 | **DELETE-SAFE** | `.gitignore:28` |
| `migrate_reestr_v2.py` | 13 124 Б | `plan-sistema-napominanii.md:554` | **KEEP** | идемпотентен («реестр версии 2 он не трогает»), единственный конвертер v1→v2 |
| `gab-*.png` (3 карты) | 11 087 621 Б | `zaprosy-brokerov-GAB-2026-09-28.md:78,125,168` (`<img src>`), `index.md:13–15`, `skills/map-objects/examples/*.json` | **KEEP** | встроены в разбор = `analysis` трёх живых строк (`reestr.yaml:129,188,301`) |
| `tashyan/Кемерово_предложение_инвестору_2026.pdf` | 1 022 593 Б | `index.md:21`, `log.md:129` | **KEEP** | получен от контрагента 07.10, невосстановим |
| `bolvanka-dogovora-razmeshchenie-nekapitalnogo-obekta.md` | 66 756 Б | `2026-10-01_levzin…md:96,149`, `index.md:26` | **KEEP** | строка `levzin-sokolniki` живая: `next_touch: '2026-10-24'`, `touches: 0` |
| `osnovanie-praktiki.md` | 3 506 Б | `README.md:26`, `plan…md:589`, `index.md:25` | **KEEP** | обоснование каденции 3/7/14 |
| `2026-10-01_review-plana-crm-adversarial.md` | 43 894 Б | `README.md:27`, `index.md:24` | **KEEP** | история проектирования реализованной системы |
| `zaprosy-brokerov-GAB-2026-09-28.md` | 56 117 Б | `reestr.yaml:129,188,301`; `routing/telegram-projects.yaml:931,956,966`; `scripts/test_classifier.py:739,809,843` | **KEEP** | несущий, три независимых потребителя |
| `2026-10-01_levzin-uchastok-pod-sport-sokolniki.md` | 27 057 Б | `reestr.yaml:79`, `README.md:28`, `plan…md:96,597` | **KEEP** | несущий |
| `podborka_deck.py` | 5 805 Б | `index.md:19`, `log.md:115,131` | **KEEP** | пересобирает отданный `podborka-GAB-kurchevskaya-2026-10-06.pdf` из `prezentacii/assets/` (`:89`) |
| `podborka_map.py` | 2 119 Б | только докстринг `prezentaciya_presnya99_deck.py:9`; импортов 0 | **DELETE-SAFE** | `grep "import podborka_map\|from podborka_map\|podborka_map\."` → 0; тайлы дублируются `skills/map-objects/scripts/render_map.py:83` |
| `prezentaciya_presnya99_deck.py` | 7 519 Б | `index.md:19` | **ARCHIVE** | `SRC = '/tmp/presnya99'`, каталога нет; скрипт неисполним, результат уже в `ne-v-podborke/` |
| `prezentacii/` (9 PDF + 1 jpg) | 12 922 998 Б | `index.md:18–21` | **KEEP** | версия 05.10 — история; чистые листы без R4S (`pdftotext` → 0 вхождений) |

## Findings

**1. SEVERE** — `scripts/law_lint.py:315`

```python
    for base in (SKILLS, SCRIPTS):
```

*Defect Analysis:* единственный автоматический сторож орфанов и запасных копий обходит только `skills/` и `scripts/`: `check_orphan_files` (`:282`) смотрит корень каталогов скиллов, `check_deletion_candidates` (`:312`) ищет лишь `*.bak/*.orig/*~`. Каталог, где накапливается масса — 13 МБ PDF, 11 МБ PNG, 440 КБ `.pyc`, неисполнимый скрипт — вне гейта. Прогон сегодня: `rc=0`, одна информационная находка; 99% объёма проекта не проверяется ничем.
*Actionable Remediation:* добавить `PROJECTS = REPO / "projects"` в оба обхода с информационным классом `PROJECT-ARTIFACT` (rc не меняет).

**2. HIGH** — `projects/Брокерские-запросы/prezentaciya_presnya99_deck.py:26`

```python
SRC = '/tmp/presnya99'
```

*Defect Analysis:* сборщик читает исходники из `/tmp/presnya99`, которого больше нет (проверено `ls`): мёртвый код, не инструмент. При этом `index.md:19` описывает его как действующий — «у сборщика презентации «РОМБАБА» … исходники по-прежнему в `/tmp`», фиксируя нарушение правила «never park files you may need later in `/tmp`» как норму.
*Actionable Remediation:* перенести скрипт в `prezentacii/ne-v-podborke/` как провенанс (или удалить — он в git), убрать из `index.md:19` фразу про `/tmp`; исходники следующего лота — в `assets/`.

**3. MEDIUM** — `projects/Брокерские-запросы/podborka_map.py:1`

```python
"""Статичная карта локации из тайлов OSM: центр + пин, кроп под размер слайда."""
```

*Defect Analysis:* модуль не импортируется ни одним файлом репозитория, единственное упоминание — докстринг другого скрипта. Его функция реализована в `skills/map-objects/scripts/map_base.py` и `render_map.py`, породивших три PNG проекта; вторая копия логики разойдётся при первой правке.
*Actionable Remediation:* удалить (tracked, `git show` восстановит); `prezentaciya_presnya99_deck.py:9` — сослаться на `skills/map-objects/scripts/render_map.py`.

**4. MEDIUM** — `projects/Брокерские-запросы/__pycache__/` (434 358 Б) и `.pytest_cache/` (6 246 Б)

*Defect Analysis:* оба в `.gitignore` (`:25`, `:28`), в историю не попадают, но лежат в рабочем дереве и растут с каждым прогоном тестов; линза их не видит — это не `*.bak`.
*Actionable Remediation:* удалить; при желании — `PYTHONDONTWRITEBYTECODE=1` в кроне.

**5. LOW** — `/root/redevest-ai/.tmp` (2,8 МБ, 01–08.10.2026)

*Defect Analysis:* скретч в корне репозитория (`build_fryazino_table.py`, `fill_fryazino_table.py`, `bot-resolved.json`, `find_suv.json`); правило `.gitignore:47 *.tmp` прячет его и от git, и от `law_lint`, а удаление необратимо.
*Actionable Remediation:* просмотреть два скрипта по Фрязино, затем удалить; впредь — `~/.opencrabs/projects/`.

**6. LOW** — `projects/Брокерские-запросы/README.md:18–28`

```markdown
| `2026-10-01_levzin-uchastok-pod-sport-sokolniki.md` | разбор запроса Левзина |
```

*Defect Analysis:* таблица «Что где лежит» перечисляет 11 позиций без `migrate_reestr_v2.py`, `podborka_deck.py`, `prezentacii/`, карт `gab-*.png` и `index.md`: читатель не узнаёт про 13 МБ PDF и два сборщика.
*Actionable Remediation:* дописать пять строк со статусом (`история`, `генератор`, `материалы`).

**7. INFO** — `skills/broker-requests/SKILL.md.2026-10-20T105422.bak`: вердикт **DELETE-SAFE** (обоснование в таблице). `law_lint` держит его как `DELETION-CANDIDATE` («удалять только после вердикта линзы D») — вердикт дан, удаление за владельцем.

**8. INFO** — `projects/Брокерские-запросы/prezentacii/ne-v-podborke/` смешивает чистые листы продавца двух выпавших лотов и собранную презентацию «РОМБАБА»: имя описывает статус лота, а не вид файла. При следующем лоте — разложить по `clean/` и `built/`.

## Итог

Ни один файл истории сделки не приговорён: карты, PDF, разборы и болванка держатся живыми ссылками (три живые строки реестра, `next_touch` 24.10 по Левзину). Удалению подлежат регенерируемое (440 КБ кэшей), мёртвый модуль без импортов (2 КБ), запасная копия, равная коммиту `319d90c` (15 КБ), и после просмотра — скретч `.tmp` (2,8 МБ). Главный дефект не в файлах, а в гейте: он не смотрит в `projects/`.

FINDINGS: 8 — SEVERE 1, HIGH 1, MEDIUM 2, LOW 2, INFO 2.
