# AI-поиск: мягкий LLM re-rank

**Статус:** в коде (после альфы MVP).  
**Связано:** `docs/ai-search.md`, `docs/SPEC_ai_query_parse.md`,
`docs/plans/ai-search-async.md`, `app/dict/ai/rerank.py`.

## Зачем

Детерминированный score (focus / lexical / field) иногда ставит ложных
друзей выше нужных статей (многозначность, theme-only). Второй LLM-проход
**слегка** переставляет топ уже найденных карточек под исходный запрос.
Может опустить явно нерелевантные id (с полом keep). Не меняет оси parse
и не добавляет статьи.

## Пайплайн

```
parse → SQL + score → status=ranking → LLM order топа (±drop) → demote см./от
→ done
```

- `sort=alpha` — без LLM.
- `AI_SEARCH_LLM_RERANK=False` — без LLM.
- Сбой / битый JSON / слишком короткий order — SQL-порядок.

UI poll: `running` → «Разбираем запрос…»; `ranking` →
«Подбираем статьи по вашему запросу…». Карточки только на `done`.

## Кандидат

Без `article_html`. На статью:

- `id`, `word`
- **все** `rus_word` из индекса переводов (многозначность)
- `fields[]`, `tags[]` (компактно)

Пул: топ **30** главной группы. Хвост без LLM. Demote см./от — **после**.

## Контракт ответа

`{"order": [<id>, ...]}` — id только из входа, без дублей.
Можно короче входа (drop явного мусора). Минимум keep:
`max(8, ceil(n/2))` (не больше n). При сомнении / многозначности — оставить.

Промпт: `PROMPT_VERSION` в `rerank_prompts.py`. Модель:
`TIMEWEB_AI_MODEL_RERANK` (дефолт = `TIMEWEB_AI_MODEL_QUERY`).

## Пометы (parse → search)

- **Hard** (`tags`): ярлык есть в тексте запроса → AND-фильтр.
- **Soft** (`tags_soft`): выведено LLM, в тексте нет → только бонус ранга.
- **Relax-on-empty:** hard ∩ lexical = ∅ → снять hard, оставить lexical
  (не пустой fallback).
