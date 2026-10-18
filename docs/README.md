# Документация

Вход для агента: корневой `AGENTS.md`. Очередь работ: `docs/plans/INDEX.md`.

Файлы пока лежат плоско в `docs/` (перенос в `specs/` / `runbooks/` / `notes/` — позже, чтобы не ломать ссылки).

## Планы (живой бэклог)

| Файл | О чём |
|------|--------|
| [plans/INDEX.md](plans/INDEX.md) | Приоритеты, не смешивать ветки |
| [plans/translation_index_audit.md](plans/translation_index_audit.md) | Аудит `rus_word` после LLM-cleanup |
| [plans/krl-search-tag-filters.md](plans/krl-search-tag-filters.md) | Фильтры помет в карельском `/search/` |
| [../backlog.md](../backlog.md) | Продукт: связи «от», пометы; `from_translation` и очистка переводов закрыты |
| [backlog-search.md](backlog-search.md) | Лексический `/search/` (не семантика) |

## Спеки (ещё не обязательно в коде)

| Файл | О чём |
|------|--------|
| [ai-search.md](ai-search.md) | UX AI-поиска — **следующий фокус разработки** |
| [SPEC_article_form_validator.md](SPEC_article_form_validator.md) | Валидатор формы статьи в админке |

## Runbook

| Файл | О чём |
|------|--------|
| [translation_cleanup.md](translation_cleanup.md) | Боевой путь очистки переводов (prod, `--write`) |

## Заметки и эталоны

| Файл | О чём |
|------|--------|
| [searching_upgrade.md](searching_upgrade.md) | Реализованные подсказки русского поиска, эталон «быстро»; staff: Переводы + Отладка (§0.2) |
| [method-onthlogy-markup.md](method-onthlogy-markup.md) | Как строили онтологию и разметку |

## Архив (не источник истины)

| Файл | Почему |
|------|--------|
| [context.md](context.md) | Черновик обзора, пути и стек расходятся с кодом. Актуальный обзор: `cursor_project_overview.md` |
