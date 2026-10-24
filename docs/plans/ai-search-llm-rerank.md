# AI-поиск: мягкий LLM re-rank

**Статус:** **на prod** (2026-10-24), `AI_SEARCH_LLM_RERANK=1`,
`TIMEWEB_AI_MODEL_RERANK=xiaomi/mimo-v2.6-flash` (parse по-прежнему
`TIMEWEB_AI_MODEL_QUERY`).  
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
- Сбой / битый JSON / чужие id в `order` — SQL-порядок.
- Префикс `order` дополняется остатком головы в prior-порядке.
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

Промпт: `PROMPT_VERSION` в `rerank_prompts.py` (1.3+). Модель:
`TIMEWEB_AI_MODEL_RERANK` (prod: MiMo V2.6 Flash; дефолт кода = QUERY).

## Пометы / POS (parse → search) — рядом с re-rank

- **Hard** (`tags`): ярлык в тексте → AND (стилистика/прочее).
- **Soft** (`tags_soft`): вывод модели → union `soft∩field` + бонус ранга,
  не AND-опустошение.
- **POS (Tag.type=2):** только сужение кандидатов, не `field∩v` как вся выдача.
- **Relax-on-empty:** hard ∩ lexical = ∅ → снять hard.
