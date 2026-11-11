# Документация

Вход для агента: корневой `AGENTS.md`. Очередь работ: `docs/plans/INDEX.md`.

Файлы пока лежат плоско в `docs/` (перенос в `specs/` / `runbooks/` / `notes/` — позже, чтобы не ломать ссылки).

## Планы (живой бэклог)

| Файл | О чём |
|------|--------|
| [plans/INDEX.md](plans/INDEX.md) | Приоритеты, не смешивать ветки |
| [plans/translation_index_audit.md](plans/translation_index_audit.md) | Аудит `rus_word` после LLM-cleanup |
| [plans/search-query-stopwords.md](plans/search-query-stopwords.md) | Стоп-токены в token-OR (вариант A) |
| [plans/search-rus-lemmas.md](plans/search-rus-lemmas.md) | P3 леммы RU-поиска (pymorphy3, `rus_lemmas`) — сделано |
| [plans/search-module-split.md](plans/search-module-split.md) | Распил `search.py` (rus / krl / ontology) — бэклог, высокий риск |
| [../backlog.md](../backlog.md) | Продукт: связи «от», пометы; `from_translation` и очистка переводов закрыты |
| [backlog-search.md](backlog-search.md) | Лексический `/search/` (не семантика) |

## Спеки и UX

| Файл | О чём |
|------|--------|
| [ai-search.md](ai-search.md) | UX AI-поиска — **закрытая альфа на prod** |
| [SPEC_ai_query_parse.md](SPEC_ai_query_parse.md) | Контракт разбора, REPL; фазы A–C на prod |
| [plans/ai-search-async.md](plans/ai-search-async.md) | Async job+poll (сделано); SSE/worker — позже |
| [plans/ai-search-llm-rerank.md](plans/ai-search-llm-rerank.md) | LLM re-rank: гипотеза не подтвердилась, код удалён |
| [SPEC_article_form_validator.md](SPEC_article_form_validator.md) | Валидатор формы статьи в админке (ещё не в коде) |

## Runbook

| Файл | О чём |
|------|--------|
| [translation_cleanup.md](translation_cleanup.md) | Боевой путь очистки переводов (prod, `--write`) |

## Заметки и эталоны

| Файл | О чём |
|------|--------|
| [searching_upgrade.md](searching_upgrade.md) | Реализованные подсказки русского поиска, эталон «быстро»; staff: Переводы + Отладка (§0.2) |
| [method-onthlogy-markup.md](method-onthlogy-markup.md) | Как строили онтологию и разметку |
| [method-ai-search-retrieval.md](method-ai-search-retrieval.md) | Retrieval AI-поиска: схемы, эталоны, **журнал отказов** |

## Архив (не источник истины)

| Файл | Почему |
|------|--------|
| [context.md](context.md) | Черновик обзора, пути и стек расходятся с кодом. Актуальный обзор: `cursor_project_overview.md` |
| [plans/krl-search-tag-filters.md](plans/krl-search-tag-filters.md) | Фильтры `?t=` / `?ph=` в KRL `/search/` — сделано |
| ~~`docker-compose-prod.yml`~~ / ~~`init-letsencrypt.sh`~~ / bake `.env` в образе | **Удалены.** Prod = `docker-compose.internal.yml` (`punzh_web`, mount `.env`). См. `AGENTS.md` |
