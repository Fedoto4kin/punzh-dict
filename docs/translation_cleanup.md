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
| Боевой dry-run ~13k | prod | **в процессе** (чистый перезапуск 13036, 2026-08-29) |

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
       │ LLM (DeepSeek)                 │ SYSTEM_PROMPT, gloss, sanitize
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
- Готово: строка `Готово. Статей: N. Ошибок: 0.` в логе.

### Заливка после dry-run

```bash
docker exec --user 1000:1000 -w /app punzh_web python manage.py migrate --noinput

docker exec --user 1000:1000 -w /app/agents punzh_web \
  python -u clean_translations.py --write --from-json clean_prod.json
```

При обрыве повторной заливки: `--skip-snapshot` (снимок уже есть).

---

## Post-LLM sanitize

Порядок в `sanitize_cleaned_translations()`:

1. dedupe, ё→е, снятие грамматических скобок
2. параллель глагола («менее трудным» → «делать менее трудным»)
3. subsumed aux / word fragments
4. восстановление однословных gloss-эквивалентов (olla)
5. «… и пр.» параллели из gloss
6. отсечение «корзин и пр.»
7. crossref (`см. …`)
8. **если `is_service_word`:** `_filter_service_word_translations` +
   `_preserve_original_service_equivalents`

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
| 7636 | `män||nä` | «выйти замуж» (◊) |
| 1717 | `enži|kandon'e` | скобки `(о корове)` |

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

## Открыто

- [ ] Дождаться «Готово» на prod → проверка json → migrate → `--from-json`
- [ ] DB-тест «корова» / 1717 (full vs exact vs тег)
- [ ] prio‑фильтр для «быть» (отдельно от cleanup)
- [ ] Ярлыки тегов и скобки в `split_by_coverage`

---

## Не смешивать с cleanup

В рабочем дереве могут лежать **несвязные** WIP (`classify_article`,
`audit_cyrillic_lemmas`, `deploy.sh`, nginx и т.д.). Не включать их в коммиты
и PR по очистке переводов без явного запроса.

См. также: `app/agents/AGENTS.md`, `backlog.md` §2, `cursor_project_overview.md`
(ссылка на этот файл).
