# План: леммы в русском поиске (P3)

Статус: **сделано** (лексический `/search/`, не AI).  
Связь: `docs/backlog-search.md` §P3, `docs/searching_upgrade.md` §0 / §0.1,
`docs/plans/INDEX.md`.

## Проблема

Token-OR и вычитание в ярлыках шли по **поверхности**. Падежи/спряжения
(`корова`↔`корове`, `идти`↔`идёт`) ловились только хрупким one-letter fuzzy;
в `rus_word` часто не словарная форма.

## Решение

Леммы токенов **запроса и** `rus_word` через **pymorphy3** (ё→е).

| Слой | Правило |
|------|---------|
| Token-OR | `rus_lemmas__overlap` с леммами запроса |
| `?f=exact` | поверхность `rus_word` = запрос |
| Сужающие теги | вычитать токены с той же леммой, что у запроса |

Поле `ArticleIndexTranslate.rus_lemmas` (`ArrayField` + GIN). Заполняется в
`save` / `apply_translations`; backfill —
`manage.py rebuild_translate_lemmas`. Fuzzy из OR снят.

**Вне скоупа:** FTS; русский trigram; мост `быстро`↔`быстрый` — **не делаем**
(разные леммы, склеивать не нужно); P1 стоп-токены; P4 keywords.

## Зацепки

- `dict/helpers/rus_morph.py`, `dict/search/rus.py`, `dict/search_debug.py`
- запись: `translation_index_write.py`, модель `ArticleIndexTranslate`
- тесты: `test_rus_morph`, `test_search_korova` (LemmaMorphology*), `test_split_by_coverage`, `test_search_debug`
