# Очередь задач

Единственный индекс приоритетов. Детали — в связанных файлах. Ветки не смешивать в одном PR/чате без явной задачи.

**Не делаем в текущей версии семантики:** переклассификация полей; чистка keywords; фильтр `/ontology/` и AI-поиска по `from_translation`.

## Сейчас

| # | Статус | Задача | Где |
|---|--------|--------|-----|
| **1** | **альфа на prod** | **AI-поиск MVP:** async job+poll, разбор 1.14, retrieval (пометы/тема/говор), `/ai-search/` без пункта в меню | `docs/ai-search.md`, `SPEC_ai_query_parse.md`, `plans/ai-search-async.md` |
| 2 | параллельно | Связи «от» / `ArticleLink.kind` (подсветка на сайте) | `backlog.md` §1 — **отдельный контур**, не смешивать с AI |
| 3 | следующий по AI | **LLM soft re-rank** топа после SQL; обратная связь альфы / beta-логи 👍/👎 | `plans/ai-search-llm-rerank.md`, `SPEC_ai_query_parse.md` §6 |

**AI MVP (2026-10-23) на prod:** sync слой + async UI, migrate `0032`, скрытый URL
`/ai-search/`. Предпосылки по данным закрыты. Контракт — `SPEC_ai_query_parse.md`.

## Дальше (продукт)

| # | Статус | Задача | Где |
|---|--------|--------|-----|
| 4 | спека | Валидатор формы: сначала В2 (автокомплит «см.»), затем В1 | `docs/SPEC_article_form_validator.md` |
| 5 | бэклог | Поиск неразмеченных помет | `backlog.md` §3 |
| 6 | план | Аудит индекса переводов после cleanup (read-only) | `plans/translation_index_audit.md` |
| 6 | бэклог | **Стоп-токены в token-OR** (вариант A: «о корове» без раздува от «о») | `docs/plans/search-query-stopwords.md` |
| 7 | бэклог | KRL в русской транслитерации → формальные правила → «возможно вы искали» | `docs/ai-search.md` §Перспектива (Метрика) |
| 8 | бэклог AI | Пункт «умный поиск» в навигации; SSE/worker — по нагрузке | `plans/ai-search-async.md` |

## Лексический `/search/` — baseline готов

Основная ветка **не блокирует** AI-поиск. Доработки по желанию:
`docs/backlog-search.md` (**P1-stop** стоп-токены; **P3 леммы** запроса и
перевода вместо fuzzy; P4 keywords в индекс). Русский trigram (бывший P2)
**не делаем**. Не возвращаемся к Postgres FTS / `search_vector` ради морфологии.

## Сделано (не трогать без регрессии)

- **Стек:** Python 3.12 + Django 5.2 LTS, psycopg3, uWSGI 2.0.28.
- **AI-поиск MVP (prod 2026-10-23):** `/ai-search/` async (AiSearchJob + poll), REPL
  `ai_query`, пометы≠related, field∩tags, demote см./от, промпт 1.14 —
  `docs/ai-search.md`, `plans/ai-search-async.md`.
- **LLM soft re-rank** топа после SQL (`ranking`, все переводы кандидата) —
  `plans/ai-search-llm-rerank.md`.
- KRL `/search/`: фильтры по пометам `?t=` / `?ph=` — `plans/krl-search-tag-filters.md`.
- Массовая пометка `from_translation` на prod (`pick_translation_fields` + `load_translation_fields`) — `backlog.md` §4.
- Очистка переводов LLM + `--write` на prod, канон **е** в индексе (`translation_cleanup.md`).
- Русский поиск: ILIKE + **токенный OR** (не FTS `russian`), ё→е, `expand_by_links` только **см.+от**.
- Сужающие теги `?f=`, `find_exact_match_ids`, UI (блок «Уточнить запрос» только при наличии тегов).
- «Связанные запросы», prio «быть», эталон «корова»/1717 (тесты + fuzzy одна буква как временный суррогат, key без скобок, `?f=` AND).
- `kind` на `ArticleLink`, инвентаризация, автосоздание однозначных `deriv`, админка kind — `backlog.md` §1.
- Админка: браузер **Переводы** (карточки по `rus_word`) + **Отладка** русского поиска (`rus_search_core`) — `docs/searching_upgrade.md` §0.2.
- Решение (2026-09): морфология русского поиска — леммы токенов с обеих сторон; не FTS; без русского trigram — `backlog-search.md` (принятое решение + P3).

Подробно: `docs/searching_upgrade.md`, `docs/backlog-search.md`.
