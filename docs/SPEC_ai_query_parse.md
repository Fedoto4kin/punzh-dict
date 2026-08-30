# AI-поиск — разбор запроса, REPL, телеметрия (реализация)

**UX и опыт пользователя:** `docs/ai-search.md`.  
**Очередь:** `docs/plans/INDEX.md`.  
**Данные (поля, keywords):** `docs/method-onthlogy-markup.md`.

Здесь — контракт разбора, фазы разработки, интерактивная консольная утилита,
эталоны и сбор логов на beta. Не дублировать приоритеты из INDEX.

**Статус:** спека зафиксирована (2026-08-30); код ещё не реализован.

---

## 1. Задача

Пользователи вводят **намерение**, а не лемму: «как ругаться по-карельски»,
«чем режут хлеб», «дует ветер». AI-поиск — **отдельный контур** (`/ai-search/`),
не расширение лексического `/search/`.

Пайплайн:

```
Запрос → LLM-разбор → SQL по осям → группы + ранж → страница
              ↓ fail / пусто
         fallback → /search/…
```

Обратная задача к `classify_article`: не статья→поля, а **запрос→оси** (lexical,
fields, tags, dialect).

---

## 2. Контракт JSON разбора

Модель: `TIMEWEB_AI_MODEL_QUERY` (YandexGPT через шлюз).  
Промпт знает замороженный список `SemanticField` и справочник `Tag`
(тип 3 — стилистика, тип 4 — говоры).

Ответ — **один JSON** (без markdown):

```json
{
  "lexical": ["ругаться", "брань"],
  "fields": ["Речь и общение"],
  "tags": ["бран.", "неодобр."],
  "dialect": null,
  "dropped": ["по-карельски"],
  "display": "искали: ругаться · брань; «пo-кarельски» пропущено"
}
```

| Поле | Тип | Правила |
|------|-----|---------|
| `lexical` | `[str]` | Русские леммы/синонимы для прямого поиска в `ArticleIndexTranslate`. |
| `fields` | `[str]` | Имена **строго** из `SemanticField.name`. |
| `tags` | `[str]` | Краткие пометы (`бран.`, `всг.`) **строго** из `Tag.tag`. |
| `dialect` | `str\|null` | Говор, если явно назван в запросе. |
| `dropped` | `[str]` | Служебное: «пo-karельски», «как сказать», «перевод» — не ищем буквально. |
| `display` | `str` | Строка для UI под строкой запроса. |

**Валидация в коде:** неизвестные `fields` / `tags` отбрасываются с предупреждением
(REPL / debug). Пустые все оси → `parse_ok=false` → fallback на лексический поиск.

**Эвфемизмы:** промпт явно мапит «мат», «ругаться», «сквернословить» → `бран.` /
`неодобр.` (словарь документирует лексику, не цензурирует).

**Не фильтруем** выдачу по `from_translation` (`docs/plans/INDEX.md`).

---

## 3. Retrieval (группы)

Детерминированный SQL, без второго LLM. Переиспользование `dict/search.py` и
логики `/ontology/`, `/tags/`, `expand_by_links`.

| Группа UI | `kind` | Источник |
|-----------|--------|----------|
| Прямое лексическое | `lexical` | OR по `lexical[]` в `ArticleIndexTranslate` |
| По помете | `tag` | `ArticleIndexTag` |
| По смысловому полю | `field` | `ArticleSemanticField` + «см.» (как `/ontology/`) |
| В иллюстрациях | `keyword` | `ArticleKeyword` ∩ `lexical[]` (опц. в MVP) |

Ранж: lexical > tag > field > keyword; бонус за несколько осей на одной статье.
Подписи групп — человеческие (`docs/ai-search.md`).

---

## 4. Фазы разработки

| Фаза | Deliverable | Проверка |
|------|-------------|----------|
| **A** | этот документ + `query_parse.py` + `manage.py ai_query` (REPL) | ручной прогон запросов |
| **B** | `search.py` + preview в REPL + `ai_query_benchmarks.json` | `--benchmark`, тесты с моком parse |
| **C** | `/ai-search/`, шаблон, ссылка «Умный поиск» | интеграционные тесты view |
| **Beta** | `AiSearchLog`, оценки 👍/👎, export | см. §6 |

Страница (C) — тонкая обёртка над тем же ядром, что REPL; логику не дублировать.

---

## 5. Интерактивная утилита `manage.py ai_query`

**Основной инструмент фаз A–B.** REPL: ввод запроса из консоли → разбор +
отладочная информация → (фаза B) preview выдачи.

### Запуск

```bash
docker exec -i -w /app punzh_django python manage.py ai_query
```

Флаг **`-i`** у `docker exec` обязателен (stdin для REPL).

Дополнительно (не REPL):

```bash
# один запрос и выход (скрипты, CI)
python manage.py ai_query --once "как ругаться по-карельски"

# эталоны из JSON
python manage.py ai_query --benchmark

# append событий в JSONL (dev, без БД)
python manage.py ai_query --log-file logs/ai_query.jsonl
```

Уровни вывода: `--verbose` (debug + raw), по умолчанию, `--quiet` (display + counts).

### Цикл REPL

После Enter вывод **блоками**:

1. **parse** — `display`, оси (`lexical`, `fields`, `tags`, `dialect`, `dropped`), время.
2. **debug** (verbose / по умолчанию в REPL) — модель, `prompt_version`, `parse_ok`,
   валидация полей/помет, сжатый `raw_json`.
3. **retrieval** (фаза B, `:preview on`) — группы, counts, top-N `word`, `fallback`.
4. При `parse_ok=false` или LLM down — блок **fallback** (сколько дал бы `/search/`).

Приглашение: `> `.

### Команды REPL (префикс `:`, не отправляются в LLM)

| Команда | Действие |
|---------|----------|
| `:help` | список команд |
| `:quit` / `:q` | выход |
| `:raw` | полный JSON последнего ответа модели |
| `:json` | последнее событие целиком (parse + groups + meta) |
| `:reload` | перечитать онтологию и пометы из БД |
| `:benchmark` | прогон `ai_query_benchmarks.json`, ✓/✗ |
| `:preview on/off` | preview SQL-групп (фаза A — off) |
| `:verbose` / `:quiet` | уровень вывода |
| `:history` | последние запросы в сессии |
| `:repeat N` | повторить N-й запрос из history |

Пустая строка — игнор.

### Модули (план)

| Модуль | Назначение |
|--------|------------|
| `dict/ai/query_parse.py` | `parse_query(text) → ParsedQuery + meta` |
| `dict/ai/query_prompts.py` | system + сбор онтологии/помет (или секция в `prompts.py`) |
| `dict/ai/search.py` | `search_by_parsed(parsed) → groups[]` |
| `dict/ai/telemetry.py` | `serialize_ai_search_event(...) → dict` |
| `management/commands/ai_query.py` | REPL и CLI |

**Не в `agents/`** — путь Timeweb, как `classify_article` и `test_timeweb`.

---

## 6. Телеметрия и оценки (beta, не MVP)

Цель: на closed beta собрать запросы и сигналы «плохо/хорошо» для итерации промпта.

### Две сущности

| | **AiSearchLog** (автомат) | **AiSearchFeedback** (кнопка) |
|---|---|---|
| Когда | каждый AI-запрос на beta | пользователь нажал 👍/👎 |
| Связь | — | FK → log |

### Поля лога (минимум)

- `query_raw`, `parsed_json`, `groups_json` (top article_ids по группе, не все 16k)
- `display`, `parse_ok`, `fallback_used`
- `model_query`, `prompt_version`, `latency_ms`, `created_at`
- `session_key` — анонимная cookie; **без** IP и user id

### UI beta (под выдачей)

«Помогло?» 👍 / 👎; при 👎 — короткий комментарий и опционально «разбор неверный» /
«не те слова» / «мало результатов». Одна оценка на log (upsert). Строка:
«Beta: ответы помогают улучшить поиск».

### Флаги

```python
AI_SEARCH_BETA = True
AI_SEARCH_LOG_QUERIES = True  # beta / dev
```

Prod после beta: логи выключить или только ошибки; feedback убрать или оставить
«сообщить об ошибке».

### Экспорт и итерация

```bash
manage.py export_ai_search_logs --since … --with-feedback
```

Кейсы с 👎 + comment → эталоны в `ai_query_benchmarks.json` → `--benchmark` в REPL.

**Retention:** например 90 дней beta → `purge_ai_search_logs`.

REPL и web используют **один** `serialize_ai_search_event()` (JSONL на dev, БД на beta).

---

## 7. Эталоны

Файл: `app/dict/fixtures/custom/ai_query_benchmarks.json` (создать на фазе B).

Мягкие проверки (`lexical_contains`, `tags_any`, `dropped_contains`, `must_not_have_tags`) —
LLM не полностью детерминирован.

Стартовый набор запросов:

- «как ругаться по-карельски»
- «чем режут хлеб»
- «чем режут хлеб в Весьегонске»
- «дует ветер»
- «нож», «корова», «быстро», «понизу», «da»

---

## 8. Вне scope (v1)

- подгруппы внутри поля, «похожие запросы», семантическое древо;
- ML-ранжирование;
- фильтр по `from_translation`;
- встраивание semantic в `/search/`;
- запись в БД из REPL;
- readline/curses UI.

---

## 9. Связанные команды (уже есть)

```bash
# канал Timeweb
docker exec -i -w /app punzh_django python manage.py test_timeweb

# классификация статьи (обратная задача)
docker exec --user 1000:1000 -w /app punzh_django \
  python manage.py classify_article --id 12345 --dry-run
```
