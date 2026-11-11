# AI-поиск: декларативные схемы retrieval

**Статус:** формат согласован (2026-10-24); **реализация в коде** —
`app/dict/ai/retrieval_schemas.py` + интерпретатор в `search_by_parsed`.  
**Связано:** `app/dict/ai/search.py` (`search_by_parsed`), `docs/ai-search.md`,
`docs/SPEC_ai_query_parse.md`, `docs/plans/INDEX.md` §1a,
**`docs/method-ai-search-retrieval.md`** (методика + журнал отказов).

Параллельно с кодом схем вести method-файл: эталоны, **отказы гипотез**,
пределы данных. Не повторять ошибку разметки онтологии — «успех без фейлов».

## Зачем

Правила «говор + тема», soft/hard-пометы, POS-сужение, demote см./без перевода
сейчас размазаны по веткам в `search_by_parsed`. Нужны явные схемы: код только
исполняет профиль (оси → множества → union → demote/ранг), без новой
импровизации в if/else.

## Зафиксированное поведение (эталон dialect+тема)

Запрос: «весьегонские слова про погоду». Проверка: 68 всг., без
`dialect_relaxed`.

1. **anchors** = переводы `lexical | related | focus` ∩ поле (**не** KW).
2. **tier1** = anchors ∩ всг.; **tier2** = поле ∩ всг.
3. **Не** подменять говор не-всг. глоссами (relax только если
   `field ∩ dialect = ∅`).
4. **demote:** см./от pull-ins; статьи без `ArticleIndexTranslate`; KW
   «дождь» на муравейнике / чибисе — не в топ.
5. На данных пересечение «погода»∩всг. почти пусто → топ =
   ландшафт/смежное из «Природа и погода»∩всг. — **не баг**, ограничение
   разметки.

## Согласованный формат

### Носитель

Только **Python**, максимум читаемости: dataclasses / конфигурационные
классы в `app/dict/ai/retrieval_schemas.py` (имя модуля — при реализации).
YAML в hot path нет; при необходимости позже — экспорт документации из тех
же структур (не второй источник правды).

### Два слоя

| Слой | Роль |
|------|------|
| **A. Sets** | Именованные `set[id]` из parse + БД (`_resolve_*`) |
| **B. Profile** | Упорядоченная таблица профилей: `when` → `main` / content / demote / empty |

Pipeline (фиксированный порядок):

```text
parse → resolve sets → match first profile → apply main
  → POS tighten → soft union → expand см./от + demote → rank
```

**POS и soft — общие пост-шаги** после профиля (не дублировать в каждом
профиле). Rank (`rank.py`) и parse — вне схемы.

### Выражения: union-кортежи, без мини-DSL

- `main: ("tier1", "tier2")` = `tier1 ∪ tier2`.
- Пересечения — **отдельные resolved-имена** (`field_and_stylistic`,
  `tier1`, …), не строки вида `"A & B"`.
- Закрытый словарь имён множеств; опечатка = ошибка при загрузке/тесте.

### Контракт профиля (черновик API)

```python
@dataclass(frozen=True)
class ProfileWhen:
    label_theme: bool | None = None       # dialect|place + lemma∈field label
    has_stylistic_hard: bool | None = None
    has_theme: bool | None = None
    # None = «не важно для матча»

@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    when: ProfileWhen
    main: tuple[str, ...]                 # union → main_ids
    content: tuple[str, ...] = ()         # прямые хиты для score
    zero_kw_score: bool = False           # True → kw_lex/kw_focus = ∅
    demote_extra: tuple[str, ...] = ()    # вычесть из main → demote
    empty_policy: str = "none"            # browse_theme_dialect | relax_geo | dialect_all | none
```

Первый матч в упорядоченном `PROFILES` побеждает.

### Имена множеств (v1)

| Имя | Смысл |
|-----|--------|
| `anchors` | tr(`lexical∪focus∪related`) ∩ field_pool (не KW) |
| `tier1` | anchors ∩ dialect ∩ place |
| `tier2` | field_pool ∩ dialect ∩ place |
| `field_pool` | статьи поля (browse без referrers) |
| `field_tr` / `field_kw` | field ∩ theme tr/kw |
| `content` | lexical/focus hits (после контура поля) |
| `field_and_stylistic` | primary_field ∩ stylistic hard |
| `content_and_stylistic` | content ∩ stylistic (± field∩mark) |
| `stylistic` / `pos` / `soft` | пометы |
| `dialect` / `place` | гео-фильтры |

### Профили v1 (шесть; пока не сворачивать)

| # | name | when | main | empty_policy | заметки |
|---|------|------|------|--------------|---------|
| 1 | `label_theme` | label_theme, ¬stylistic | tier1∪tier2 | browse → else relax | эталон; `zero_kw_score`; demote ¬tier1 |
| 2 | `field_and_mark` | stylistic + field∩mark ≠∅ | field_and_stylistic | — | |
| 3 | `content_and_mark` | stylistic + content | content∩mark ∪ … | drop mark if empty | |
| 4 | `mark_browse` | stylistic, пустой content | stylistic | — | |
| 5 | `content_default` | иначе content/field | content ∪ field_tr ∪ field_kw | browse/relax/geo | |
| 6 | `geo_browse` | только dialect/place | dialect \| place | — | «весьегонский говор» |

## Критерии готовности

- Эталон «весьегонские слова про погоду»: те же 68 всг., без
  `dialect_relaxed`; demote см./без tr / KW-шум.
- `manage.py test dict.tests.test_ai_search` зелёный.
- Профили читаются как таблица правил; `search_by_parsed` — интерпретатор.
- Ссылка из `docs/ai-search.md` / `app/dict/ai/README.md` на схемы.

## Не сейчас / не смешивать

- Промпт 1.15; эксперимент «поля без definition» (откатан).
- LLM re-rank (снят; гипотеза не подтвердилась).
- Переразметка всг.×погода; `research/`; навигация AI (INDEX §8).
