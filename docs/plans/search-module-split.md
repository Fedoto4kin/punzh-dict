# План: распил `dict/search.py` на rus / krl+facets / ontology

Статус: **сделано** (пакет `app/dict/search/`, поведение 1:1, публичный
реэкспорт в `__init__.py`).  
Связь: `docs/plans/INDEX.md`, `AGENTS.md` (контуры не смешивать).

## Зачем

Бывший `app/dict/search.py` (~1200 строк) смешивал:

- русский лексический pipeline (`rus_search_core`, сужающие `?f=`, related);
- карельский word search + фасеты тегов (`?t=` / `?ph=`);
- онтологию (`article_ids_for_semantic_field`, counts, listing);
- общие примитивы (пагинация, `Content`, `detect_direction`).

Главный выигрыш — читаемость и границы контуров. Риск **высокий**: ядро
выдачи, AI reuse (`rus_search_core`, `krl_article_ids`), staff debug.

## Целевая нарезка (предложение)

| Модуль | Содержимое |
|--------|------------|
| `dict/search/__init__.py` | реэкспорт публичного API (как сейчас из `search.py`) |
| `dict/search/rus.py` | `rus_search_core`, translate-linked, exact/related/`?f=` |
| `dict/search/krl.py` | `prepare_krl_ilike_query`, `word_search`, tag facets |
| `dict/search/ontology.py` | semantic field ids / counts / listing helpers |
| `dict/search/common.py` | `Content`, `sort_and_paginate`, `detect_direction` |

Точный список символов — по факту импортов из `views`, `ai/search`,
`search_debug`, admin, тестов. Поведение 1:1.

## Обязательные условия

1. **Отдельная задача / отдельный PR** — не смешивать с AI schemas, стоп-
   токенами, фичами выдачи.
2. **Жёсткий контракт тестов** до и после: весь `manage.py test dict`
   зелёный; особенно `test_search_*`, `test_krl_*`, `test_ontology_view`,
   `test_ai_search`, `test_search_debug`, `test_find_*`.
3. Публичные имена (`rus_search_core`, `word_search`, …) сохраняются через
   реэкспорт; без «тихого» переименования API.
4. Не менять семантику `/ontology/` / `from_translation` и AI retrieval.

## Шаги

1. Инвентарь: кто импортирует что из `dict.search` (grep + таблица).
2. Вынести `common` → `rus` → `krl` → `ontology` по одному коммиту или с
   промежуточным `search.py` как thin re-export.
3. Удалить монолит только когда все импорты идут через пакет.
4. black + `test dict`; при красном — стоп.

## Не делать здесь

Новые фичи поиска; declarative AI schemas; дробление `agents/translation_cleanup.py`.
