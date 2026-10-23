# AI-поиск: мягкий LLM re-rank

**Статус:** в коде (после альфы MVP).  
**Связано:** `docs/ai-search.md`, `docs/SPEC_ai_query_parse.md`,
`docs/plans/ai-search-async.md`, `app/dict/ai/rerank.py`.

## Зачем

Детерминированный score (focus / lexical / field) иногда ставит ложных
друзей выше нужных статей (многозначность, theme-only) и раздувает хвост
(поле ∩ POS). Второй LLM-проход: **переставляет голову**, решает
**оставить ли хвост**. Не меняет оси parse и не добавляет статьи.

## Пайплайн

```
parse → SQL + score → status=ranking
  → LLM: permute head + keep_tail?
  → demote см./от → done
```

- `sort=alpha` — без LLM.
- `AI_SEARCH_LLM_RERANK=False` — без LLM.
- Сбой / битый JSON / неполная перестановка головы — SQL-порядок.
- `keep_tail` отсутствует/битый → `true` (безопаснее оставить хвост).

UI poll: `running` → «Разбираем запрос…»; `ranking` →
«Подбираем статьи по вашему запросу…». Карточки только на `done`.

## Кандидат

Без `article_html`. На статью в **head**:

- `id`, `word`
- **все** `rus_word` из индекса переводов (многозначность)
- `fields[]`, `tags[]` (компактно)

Пул головы: топ **30**. В промпт также `tail_count` (длина хвоста), без
списка хвоста. Demote см./от — **после** merge.

## Контракт ответа

```json
{"order": [<id>, ...], "keep_tail": true|false}
```

- `order` — id из головы по релевантности (полная перестановка или
  префикс; недостающие id головы дописываются в prior-порядке).
  Из головы не удаляем.
- `keep_tail=false` — отбросить статьи после топ-30 целиком.

Промпт: `PROMPT_VERSION` в `rerank_prompts.py`. Модель:
`TIMEWEB_AI_MODEL_RERANK` (дефолт = `TIMEWEB_AI_MODEL_QUERY`).

## Пометы (parse → search)

- **Hard** (`tags`): ярлык есть в тексте запроса → AND-фильтр.
- **Soft** (`tags_soft`): выведено LLM, в тексте нет → только бонус ранга.
- **Relax-on-empty:** hard ∩ lexical = ∅ → снять hard, оставить lexical
  (не пустой fallback).
