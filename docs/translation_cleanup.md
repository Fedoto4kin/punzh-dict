# Очистка переводов (backlog §2)

Handoff для агента: LLM-очистка `ArticleIndexTranslate.rus_word` перед боевой
заливкой и связанный exact-поиск.

## Статус (2026-08-29)

| Компонент | Где | Статус |
|-----------|-----|--------|
| Промпт + sanitize | `app/agents/translation_cleanup.py` | готово |
| Dry-run / write | `app/agents/clean_translations.py` | готово |
| Снимок + запись | `app/dict/translation_index_write.py`, миграция `0027` | готово |
| Exact-поиск | `find_exact_match_ids` в `app/dict/search.py` | готово |
| Service-word post-filter | `_keep_service_word_phrase` | упрощено, `9b92ba6` |
| Боевой dry-run + `--from-json` | prod | **готово** (2026-08) |

Коммиты (ветка `master`, хронология):

- `ac9ba86` — preserve однословных эквивалентов служебных лемм из index («но» у `da I`)
- `9b92ba6` — упрощение service-filter: `_keep_service_word_phrase` (≤3 слова)
- `30533af` — этот handoff + black/isort для cleanup-модуля
- ранее — основа cleanup, снимок `0027`, `find_exact_match_ids` (см. `git log --grep=cleanup`)

**Не в репо:** `pick_*_ids.py`, `pilot_selection.py` (разовые утилиты удалены).

---

## Архитектура

```
clean_translations.py          translation_cleanup.py
       │                                │
       │ LLM ×2 (draft + review)        │ SYSTEM_PROMPT(_REVIEW), gloss
       │ + ё→е sanitize                 │ sanitize (trim/dedupe only)
       ▼                                ▼
  data/*.json  ── --write --from-json ──► translation_index_write.py
                                              │ snapshot (0027)
                                              ▼
                                    ArticleIndexTranslate
```

- **Dry-run (default):** только json в `app/agents/data/` (gitignore).
- **Запись:** `--write` или `--write --from-json` (без повторного LLM).
- Рекомендуемый prod-путь: **dry-run в json (nohup) → проверка → `--from-json`**.

---

## Запуск

### Контейнер

| Окружение | Имя контейнера |
|-----------|----------------|
| dev (compose) | `punzh_django` |
| prod (karielan-hub) | **`punzh_web`** |

```bash
docker exec --user 1000:1000 -w /app/agents punzh_web \
  python -u clean_translations.py ...
```

### Dry-run (пилот / полный корпус)

Итоговый json (без `--debug`):

```json
{
  "report": {"articles": N, "changed": M, "unchanged": K, "errors": 0},
  "meta": {"dry_run": true, "model": "deepseek-chat", "review": true, ...},
  "errors": {},
  "results": {
    "1526": {"word": "…", "before": ["…"], "after": ["…"]}
  }
}
```

```bash
LOG=~/clean_prod_dry_$(date +%Y%m%d_%H%M%S).log

nohup docker exec --user 1000:1000 -w /app/agents punzh_web \
  python -u clean_translations.py --out clean_prod.json \
  >> "$LOG" 2>&1 &

echo $! > ~/clean_prod_dry.pid
```

- `python -u` — небуферизованный вывод в лог.
- **`LOG=...` задать до nohup** (пустой `$LOG` → Exit 1).
- Автодокат: id из `--out` json пропускаются; `--force` — перепроцессить.
- Dual-pass LLM включён; `--no-review` — один проход.
- Отладка пилота: `--debug` (after_llm*, pos, removed/added).
- Готово: `Готово. Статей: N. Изменено: M. Ошибок: 0.` в логе.

Пилот (dev):

```bash
./app/agents/run_cleanup_pilot_v2.sh
```

### Заливка после dry-run

1. Проверить `report` и выборочно `before`/`after` в `clean_prod.json`.
2. Миграции (если ещё не на проде): `migrate --noinput`.
3. Запись:

```bash
docker exec --user 1000:1000 -w /app/agents punzh_web \
  python -u clean_translations.py --write --from-json clean_prod.json
```

При обрыве повторной заливки: `--skip-snapshot` (снимок уже есть).

---

## Post-LLM sanitize

Порядок в `sanitize_cleaned_translations()`:

1. dedupe, ё→е, снятие грамматических скобок
2. параллель глагола («менее трудным» → «делать менее трудным»)
3. subsumed aux / word fragments (однословники из gloss `слово,` / `слово;` **не** срезаются)
4. восстановление однословных gloss-эквивалентов (olla, «глаз» при «дурной глаз»)
5. «… и пр.» параллели из gloss
6. отсечение «корзин и пр.»
7. crossref (`см. …`)
8. **если `is_service_word`:** `_filter_service_word_translations` +
   `_preserve_original_service_equivalents`

### Gloss → LLM (не audit)

`gloss_senses_from_html()` в `translation_cleanup.py` — единый источник и для
`build_cleanup_input`, и для post-sanitize. Правила отсечения иллюстраций
(длинные примеры, possessive «берлога медведя», `on ~ кто…` и т.д.) попадают в
промпт автоматически. **Блоки ◊ в LLM не передаются** — фразеологизмы не
подмешиваются отдельным полем.

Повторный прогон cleanup после правок gloss: новый dry-run json → проверка
выборочно → `--write --from-json`. Снимок `0027` сохранит предыдущий индекс.

### Служебные леммы (`is_service_word`)

POS-тег содержит: союз, частица, предлог, послелог, междометие.

**Одно правило:** `_keep_service_word_phrase(text)`:

- ≤3 русских токена
- не crossref
- не 2-словные с «ну» («ну а», «а ну» — иллюстрации)

Применяется к выводу LLM **и** к восстановлению из `original_translations`
(исходный индекс — страховка против потери «но», «да и» и т.п.).

**Контрольные id:**

| id | lemma | проверка |
|----|-------|----------|
| 10786 | `a` | `а`, `но`, `а – а`; без иллюстраций |
| 1475 | `da I` | `да`, `и`, `но` |
| 1477 | `dai` | `да и`, `и` |
| 8992 | `olla` | `быть`, `существовать`, `имеется` |
| 4469 | `l'is'||t'ie` | нет «корзин и пр.»; полные «лучины…» |
| 1717 | `enži|kandon'e` | скобки `(о корове)` |
| 1526 | `doid’i||e` | нет осколка «до сердца» при «доходить до сердца» |
| 8998 | `olu||t` | «пиво»; без «крепкое пиво» из иллюстрации |
| 10460 | `bašk||a` | без «например» в индексе |
| 10949 | `ajua` | нет голого «деготь» / «вбить» |
| 12527 | `rakaš` | «охочий» и «любящий …» отдельными строками |

### Что улучшилось (sanitize + промпт)

- пометы (`перен.`, `всг.`, `техн.`, …) не остаются в индексе;
- карельские иллюстрации отсекаются; **остаток закрыт:** `Krl ~ adj+N`
  (`крепкое пиво`, `длинная дорога` после прилагательного) больше не считается gloss;
- осколки параллели (`до сердца`), «например»-мусор, orphan после усечения
  глагольных фраз — post-LLM sanitize.

---

## Тесты

```bash
docker exec --user 1000:1000 -w /app punzh_django python manage.py test \
  dict.tests.test_translation_cleanup \
  dict.tests.test_find_exact_match_ids \
  dict.tests.test_search_filter \
  --keepdb
```

`app/dict/tests/__init__.py` добавляет `agents/` в path для импорта
`translation_cleanup`.

---

## Линтер

**Перед коммитом изменений по cleanup** — только эти файлы (не `make format` на
весь `/app`, если в дереве есть несвязный WIP):

```bash
docker exec --user 1000:1000 -w /app punzh_django python -m isort \
  agents/translation_cleanup.py agents/clean_translations.py \
  dict/tests/test_translation_cleanup.py

docker exec --user 1000:1000 -w /app punzh_django python -m black \
  agents/translation_cleanup.py agents/clean_translations.py \
  dict/tests/test_translation_cleanup.py dict/translation_index_write.py
```

На prod-контейнере заменить `punzh_django` → `punzh_web`. isort обычно трогает
импорты в `clean_translations.py` и тестах; black — переносы длинных строк в
`translation_cleanup.py` (без изменения логики).

Проверка после форматирования:

```bash
docker exec --user 1000:1000 -w /app punzh_django python manage.py test \
  dict.tests.test_translation_cleanup --keepdb
```

---

## Поиск после cleanup

Семантика `?f=exact`: `find_exact_match_ids` — ILIKE на **целую** строку
`rus_word`, не подстрока. Подробно: `docs/searching_upgrade.md` §0.1.

---

## Восстановление поглощённых headword (после `--write`)

Cleanup иногда убирает однословную строку индекса, если в списке есть
многословная фраза с тем же токеном (`глаз` при наличии `дурной глаз`).
Exact-поиск по целой строке `rus_word` из‑за этого теряет соответствие.

**1. Цифры (снимок vs текущий индекс):**

По умолчанию — только слова, которые в `article_html` стоят в списке gloss
(`слово,` или `слово;` сразу после однословника). Широкий режим: `--broad`.

```bash
docker exec -w /app punzh_web python manage.py audit_subsumed_headwords
docker exec -w /app punzh_web python manage.py audit_subsumed_headwords --csv > subsumed.csv
```

**2. Интерактивное добавление** (нумерованный выбор, только add-only):

```bash
docker exec -i -w /app punzh_web python manage.py restore_subsumed_headwords --limit 20
```

Ввод: `1`, `1,2`, пусто — пропуск, `u` — отмена последнего сохранения по статье,
`q` — выход. Логика: `dict/subsumed_headword_audit.py`. Полезно **после** `--write`,
если sanitize ещё не восстановил однословник из gloss.

---

## Открыто

- [x] Prod `--from-json`, dedupe ё/е, регрессия поиска (см. `docs/searching_upgrade.md` §0.1)
- [ ] Повторный LLM-cleanup с улучшенным gloss (pahna, phraseme off, listed singles)
- [ ] Следующий фокус: **AI-поиск** (`docs/ai-search.md`)

---

## Не смешивать с cleanup

В рабочем дереве могут лежать **несвязные** WIP (`classify_article`,
`audit_cyrillic_lemmas`, `deploy.sh`, nginx и т.д.). Не включать их в коммиты
и PR по очистке переводов без явного запроса.

См. также: `app/agents/AGENTS.md`, `cursor_project_overview.md`
(ссылка на этот файл).
