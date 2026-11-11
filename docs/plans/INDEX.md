# Очередь задач

Единственный индекс приоритетов. Детали — в связанных файлах. Ветки не смешивать в одном PR/чате без явной задачи.

**Не делаем в текущей версии семантики:** переклассификация полей; чистка keywords; фильтр `/ontology/` и AI-поиска по `from_translation`.

## Сейчас

| # | Статус | Задача | Где |
|---|--------|--------|-----|
| **1** | **альфа на prod** (`eb95bc3`) | **AI-поиск:** async job+poll, hard/soft-пометы, POS-сужение, говор+тема (эталон «всг. про погоду»), см. входящие, session-bound job. LLM re-rank удалён | `docs/ai-search.md`, `SPEC_ai_query_parse.md`, `plans/ai-search-async.md`, `plans/ai-search-llm-rerank.md` |
| **1a** | **сделано (код)** | **Декларативные схемы retrieval** + методика/журнал отказов | `retrieval_schemas.py`, `plans/ai-search-retrieval-schemas.md`, `method-ai-search-retrieval.md` |
| 2 | **сделано** (хвост мелочь) | Связи «от» / `ArticleLink.kind` + подсветка; осталось уточнить «см от X» | `backlog.md` §1 |
| 3 | **сделано (код)** | Обратная связь альфы: `AiSearchLog` + инлайн 👍/👎 (`AI_SEARCH_FEEDBACK`); пункт в навигации — §8 | `SPEC_ai_query_parse.md` §6 |
| 3a | бэклог AI | Export/purge логов (`export_ai_search_logs` / retention) — в SPEC, команд ещё нет | `SPEC_ai_query_parse.md` §6 |

**AI на prod (2026-10-24):** скрытый `/ai-search/`. LLM re-rank удалён
(2026-11): гипотеза не подтвердилась — `plans/ai-search-llm-rerank.md`.
Контракт — `SPEC_ai_query_parse.md`.

## Дальше (продукт)

| # | Статус | Задача | Где |
|---|--------|--------|-----|
| 4 | спека | Валидатор формы: сначала В2 (автокомплит «см.»), затем В1 | `docs/SPEC_article_form_validator.md` |
| 5 | бэклог | Поиск неразмеченных помет | `backlog.md` §3 |
| 6 | план | Аудит индекса переводов после cleanup (read-only) | `plans/translation_index_audit.md` |
| 6 | **сделано** | **Стоп-токены в token-OR** (вариант A + `STOP_1C`) | `plans/search-query-stopwords.md` |
| 6a | **сделано** | **Леммы RU-поиска (P3):** pymorphy3, `rus_lemmas`, снят fuzzy | `plans/search-rus-lemmas.md` |
| 7 | бэклог | KRL в русской транслитерации → формальные правила → «возможно вы искали» | `docs/ai-search.md` §Перспектива (Метрика) |
| 8 | бэклог AI | Пункт «умный поиск» в навигации; SSE/worker — по нагрузке | `plans/ai-search-async.md` |

## Рефакторинг (техдолг)

| # | Статус | Задача | Где |
|---|--------|--------|-----|
| R1 | **сделано** | Распил `dict/search.py` → пакет `dict/search/` (common / rus / krl / ontology); публичный API через `__init__`; `test dict` зелёный | `plans/search-module-split.md` |

## Лексический `/search/` — baseline готов

Основная ветка **не блокирует** AI-поиск. Доработки по желанию:
`docs/backlog-search.md` (**P1-stop — сделано**; **P3 леммы — сделано**;
**P4 keywords в `/search/` — снято**, гипотеза не подтвердилась).
Русский trigram (бывший P2) **не делаем**. Не возвращаемся к Postgres FTS /
`search_vector` ради морфологии.

## Сделано (не трогать без регрессии)

- Удалён устаревший `docker-compose-prod.yml` / `init-letsencrypt.sh`; из
  Dockerfile убран `COPY ./.env` (секреты только mount в compose).
- **Стек:** Python 3.12 + Django 5.2 LTS, psycopg3, uWSGI 2.0.28.
- **AI-поиск (prod 2026-10-24):** `/ai-search/` async + session isolation;
  hard/soft-пометы, POS сужает, dialect relax, см. только входящие;
  UI «Как поняли» + «Что искали». LLM re-rank удалён (2026-11,
  гипотеза не подтвердилась) —
  `docs/ai-search.md`, `plans/ai-search-async.md`, `plans/ai-search-llm-rerank.md`.
- KRL `/search/`: фильтры по пометам `?t=` / `?ph=` — `plans/krl-search-tag-filters.md`.
- Массовая пометка `from_translation` на prod (`pick_translation_fields` + `load_translation_fields`) — `backlog.md` §4.
- Очистка переводов LLM + `--write` на prod, канон **е** в индексе (`translation_cleanup.md`).
- Русский поиск: ILIKE + **lemma-OR** по `rus_lemmas` (не FTS), ё→е,
  `expand_by_links` только **см.+от**; multi-word без стопов 1a∪1b∪1c.
- Русский UX: дефолт `?f=exact`, `?f=all`, сужающие теги; чипы «Точные» /
  «Расширенный»; `wide_equals_exact`; help partial + KRL tooltip — см.
  `searching_upgrade.md` §0 / §4.
- «Связанные запросы», prio «быть», эталон «корова»/1717.
- Админка: **Переводы** + **Отладка** (`rus_search_core`) —
  `searching_upgrade.md` §0.2.
- **P1 стопы** + **P3 леммы** (2026-11); **P4 keywords в `/search/`** снят.
- `kind` на `ArticleLink` — `backlog.md` §1.

Подробно: `docs/searching_upgrade.md`, `docs/backlog-search.md`.
