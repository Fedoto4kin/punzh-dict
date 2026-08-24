# PUNZH-DICT — Project overview for Cursor

## Purpose
Веб-версия словаря карельского языка (тверские говоры) Пунжиной А. В.: статьи, навигация, поиск, админка. ~16k статей.

Данные и возможности:
- словарные статьи (`Article`) с HTML-текстом, дополнениями (`ArticleAddition`) и связями «см.» (`ArticleLink`);
- русские переводы (`ArticleIndexTranslate`);
- пометы (`Tag`: населённые пункты, часть речи, стилистика, говоры, фразеологизмы);
- источники (`Source`);
- смысловые поля и ключевые слова (`SemanticField`, `ArticleSemanticField`, `ArticleKeyword`) — справочник и разметка для ветки AI-поиска, **не** для основного поиска.

Снимок разметки (dev и прод совпадали на 2026-08): 28 полей, ~28k привязок (~1.77/статью), ~48k keywords. `no_field` ~7% — норма (служебные слова и отсылки «см.»; доразметка не нужна, находятся через `ArticleLink`).

## Tech stack
- Python 3.8, Django 3.1.7, PostgreSQL (`django.contrib.postgres`: FTS, триграммы)
- Шаблоны Django + Bootstrap 4, Django Admin, uWSGI
- Docker: образ `images/django/Dockerfile`; dev-контейнеры `punzh_django` + `punzh_db`. Тесты и `manage.py` — с `-w /app`.
- Рантайм-AI: шлюз Timeweb, модуль `app/dict/ai/` (`openai==2.2.0`). В URL пока не подключён. Проверка канала: `test_timeweb`.
- LLM: рантайм (разбор запроса / классификация нового слова) → Timeweb (`TIMEWEB_AI_MODEL_QUERY` = yandexgpt-lite, `TIMEWEB_AI_MODEL_CLASSIFY` = deepseek-v4-flash). Пакетная разметка 16k → DeepSeek напрямую (`app/agents/.env`). Недоступность API не должна ронять сайт — fallback на лексический поиск.

## Structure
- `app/dict/` — основное приложение (models, views, search, templates, admin, tests, management commands).
- `app/punzh/` — Django-проект (settings, urls, wsgi/asgi).
- `app/agents/` — **оффлайн** скрипты (онтология, LLM). Не обслуживают живые запросы; заливку в БД делают management-команды.
- `app/utilites/` — разовые вспомогательные скрипты (имя каталога с опечаткой, не `utilities`).
- `app/import.py` — импорт данных.
- `docs/` — спеки (не обязательно реализованный код):
  - `ai-search.md` — UX отдельной страницы AI-поиска;
  - `searching_upgrade.md` — реализованные подсказки русского поиска + заметки;
  - `backlog-search.md` — бэклог лексического поиска;
  - `method-onthlogy-markup.md` — как строили онтологию и разметку;
  - `SPEC_article_form_validator.md` — валидатор формы статьи в админке.
- `db/` — volume БД, не код.

Статика собирается внутри `app/` (`STATICFILES_DIRS` / `staticfiles`), не в корне репозитория.

## Key models (`app/dict/models/`)
- `articles.py` — `ArticleBase` (abstract), `Article` (`save()` пересобирает индексы заголовка/нормализации), `ArticleAddition`, `ArticleIndexWord`, `ArticleIndexTranslate` (`search_vector`), `ArticleIndexWordNormalization`, `ArticleIndexTag`, `ArticleLink`.
- `semantic.py` — `SemanticField`, `ArticleSemanticField`, `ArticleKeyword`.
- `tags.py` — `Tag`.
- `source.py` — `Source`.
- `levenshtein.py` — **не модель**: SQL-обёртка `Func` над `levenshtein()`.

## Search (прод, `app/dict/search.py` + `views.py`)
- Алфавитный указатель по первой букве.
- Карельский запрос (автоопределение направления) → `ILIKE` по `ArticleIndexWord` (варианты написания заголовка, не лемматизация).
- Русский запрос → `ILIKE` + full-text по `ArticleIndexTranslate`; выдача расширяется через `ArticleLink`; уточняющие ярлыки по покрытиям перевода (`?f=`), не модель `Tag`.
- Нет точных попаданий по карельскому → пересечение Левенштейна (≤2) и триграмм.
- Пометы — отдельный маршрут `/tags/` (OR внутри типа пометы, AND между типами).

Поиск по смысловому полю / keywords в пользовательском поиске **не реализован**. Спека: `docs/ai-search.md`.

## Management commands (`app/dict/management/commands/`)
- `load_semantic_fields` — справочник из `dict/fixtures/custom/ontology_frozen.json` (формат `{"ontology":[...]}`, не Django-fixture). Мягко `update_or_create`; `--force` сносит поля и привязки каскадом.
- `load_semantic_classification --file` / `load_keywords --file` — жёсткая заливка из json (для статей из файла: delete + bulk_create). Keywords — сырьё, без чистки шума.
- `reindex_tags` — индекс помет из html: типы 1–4 игла `<i>{значение}</i>`, тип 5 — голый текст. Тот же матчинг нужен валидатору формы.
- `export_adjectives_by_field`, `fill_missing_translations`, `test_timeweb`.

## Next (не смешивать ветки)
1. AI-поиск, слой 1: разбор запроса + отдельная страница по `docs/ai-search.md` (клиент шлюза уже есть).
2. Валидатор формы по `docs/SPEC_article_form_validator.md`: сначала В2 (автокомплит «см.»), затем В1 и проверки html↔структура.

## Notes for AI (Cursor)
- Не ломать структуру `Article`, индексов и семантических моделей.
- Семантическая разметка и основной поиск — разные контуры; не смешивать их в одном UX без явной задачи.
- Agents готовят JSON; в БД пишут management-команды (также админка и `import.py`).
- Проект в реальной лексикографической работе; предпочитать явный читаемый Python.
- Язык общения — русский; комментарии в коде — английские.
