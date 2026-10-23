# AI-поиск — разбор запроса, REPL, телеметрия (реализация)

**UX и опыт пользователя:** `docs/ai-search.md`.  
**Очередь:** `docs/plans/INDEX.md`.  
**Данные (поля, keywords):** `docs/method-onthlogy-markup.md`.

Здесь — контракт разбора, фазы разработки, интерактивная консольная утилита,
эталоны и сбор логов на beta. Не дублировать приоритеты из INDEX.

**Статус (2026-10-23):** фазы **A–C на prod** (parse + валидация, `ai_query`,
`dict/ai/search`, async `/ai-search/`). Закрытая альфа. Beta-логи (§6) и
отдельная keyword-группа — вне текущего scope. Данные не блокер — см.
«Готовность» в `docs/ai-search.md`.

---

## 1. Задача

Пользователи вводят **намерение**, а не лемму: «как ругаться по-карельски»,
«Найди все слова связанные с разведением коз», «чем режут хлеб».
AI-поиск — **отдельный контур** (`/ai-search/`), не расширение лексического
`/search/`. Вход широкий (естественный язык); доверие — к валидированным осям
на выходе (`docs/ai-search.md`, раздел про ввод и инъекции).

Пайплайн (UI — **async**, см. `docs/plans/ai-search-async.md`):

```
Запрос → POST /ai-search/jobs/ → thread: LLM-разбор → SQL → AiSearchJob
              ↓ poll partial/JSON
         страница /ai-search/?job=…
              ↓ fail / пусто
         fallback → /search/…
```

REPL `ai_query` по-прежнему синхронный. Обратная задача к `classify_article`:
не статья→поля, а **запрос→оси** (lexical, fields, tags, dialect).

---

## 2. Контракт JSON разбора

Модель: `TIMEWEB_AI_MODEL_QUERY` (YandexGPT через шлюз).  
Промпт (`PROMPT_VERSION`, сейчас **1.13**) знает замороженный список
`SemanticField` и справочник `Tag` (тип 1 areal / 2 грамматика / 3 стилистика /
4 говоры).

Ответ — **один JSON** (без markdown):

```json
{
  "lexical": ["хлеб", "резать"],
  "focus": ["нож"],
  "related": ["крошить", "ломоть"],
  "fields": ["Домашняя утварь и инструменты"],
  "tags": [],
  "dialect": null,
  "dropped": ["чем"],
  "display": "искали: хлеб · резать; темы: …"
}
```

| Поле | Тип | Правила |
|------|-----|---------|
| `lexical` | `[str]` | Отдельные русские **словарные** леммы (нач. форма) для `ArticleIndexTranslate`; не склеивать фразу («разведение коз» → `коза`, `разведение`). Сценарий запроса, не «ответ». |
| `focus` | `[str]` | 1–5 лемм **ответа** на вопрос («чем режут хлеб» → `нож`); может отсутствовать в тексте запроса. Сильнейший сигнал ранжирования (`dict/ai/rank.py`); в UI «Как поняли» не дублируется. |
| `related` | `[str]` | Тематические якоря **сценария** (нач. форма), не дубли `lexical`/`focus`. **Запрещено:** ярлыки пометок/POS и смысловые леммы, развёрнутые *от* пометы («примета» ≠ суеверие/погода). Запрос только про пометы → обычно `[]`. |
| `place` | `str\|null` | Ареальная помета (Tag type 1): точное или ближайшее село из списка. |
| `fields` | `[str]` | Имена **строго** из `SemanticField.name`. Для запросов только про пометы — обычно пусто. |
| `tags` | `[str]` | Краткие пометы **строго** из `Tag.tag` (type 2 и/или 3). Несколько = **AND** (`примета` ∩ `v`). Русские POS → краткий tag (`глагол`→`v`). |
| `dialect` | `str\|null` | Говор (Tag type 4), если явно назван / выводим из географии. |
| `dropped` | `[str]` | Служебное: «по-карельски», «найди», «все слова», «связанные с», «как сказать», «перевод» — не ищем буквально. |
| `display` | `str` | Строка для UI: собирается из проверенных осей; пометы — **`Tag.name`** («verbum, глагол»), не код `v`. |

**Валидация в коде (анти-инъекция + контракт):** неизвестные `fields` / `tags`
отбрасываются с предупреждением; `dialect`/`place` — только из closed lists;
леммы пометок/POS из `lexical`/`focus`/`related` → promote в `tags` (или drop);
лишние type-2 теги сужаются по тексту запроса; при tags-primary (есть `tags`,
нет `lexical`/`focus`) — `related` и speculative `fields` обнуляются (поиск
по пометам, не «рядом по теме»). Лимиты длины; `display` всегда из осей.
Пустые все оси → `parse_ok=false` → fallback на лексический поиск. Вход **не**
режем до «только леммы».

**Эвфемизмы:** промпт явно мапит «мат», «ругаться», «сквернословить» → `бран.` /
`неодобр.` (словарь документирует лексику, не цензурирует).

**Не фильтруем** выдачу по `from_translation` (`docs/plans/INDEX.md`).

---

## 3. Retrieval (группы)

Детерминированный SQL, без второго LLM. Переиспользование `dict/search.py` и
логики `/ontology/`, `/tags/`, `expand_by_links`.

| Группа UI | `kind` | Источник |
|-----------|--------|----------|
| Нашлось по запросу | `lexical` | объединение осей: translations / tags AND / field∩translations (keywords слабее) |
| (раньше отдельно) По помете | — | несколько `tags` → пересечение `ArticleIndexTag`; tags-only = весь AND-набор |
| (контур поля) | в составе main | поле ∩ переводы, затем ∩ keywords; enrich полей по частоте среди theme seeds |
| В иллюстрациях | — | keywords — слабый сигнал ранга, не отдельная MVP-группа |

Ранж (`dict/ai/rank.py`): exact `focus` ≫ exact `lexical` ≫ field∩translation ≫
soft / theme / слабые keyword; внутри яруса — карельский алфавит. UI:
`?sort=relevance|alpha` (дефолт relevance). Подпись main — «Нашлось по запросу»;
пометы в заголовке — `Tag.name` (`docs/ai-search.md`).

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

Файл: `app/dict/fixtures/custom/ai_query_benchmarks.json`.

Мягкие проверки (`lexical_contains`, `tags_any`, `dropped_contains`, `must_not_have_tags`) —
LLM не полностью детерминирован. Поле `source` — откуда кейс (ручной /
`metrika:organic` / `metrika:entry_/search/`).

Набор (2026-10): синтетические + выборка из Метрики 86319000 (квартал):
оболочки «по карельски», маты/ругательства, «дай мне», «любимая девочка»,
«лаз в подполье для кошки», опечатки («еревод», «язывка»), короткие леммы.

---

## 8. Вне scope (v1)

- подгруппы внутри поля, «похожие запросы», семантическое древо;
- ML-ранжирование;
- фильтр по `from_translation`;
- встраивание semantic в `/search/`;
- запись в БД из REPL;
- readline/curses UI;
- **русская транслитерация карельских слов** в запросе → формальные
  правила латиницы → подсказка «возможно вы искали» (часто в Метрике:
  `иел`, `кондега`, `ваштакаба`…). Не сейчас; см. `docs/ai-search.md`
  §«Перспектива».

---

## 9. Связанные команды (уже есть)

```bash
# канал Timeweb
docker exec -i -w /app punzh_django python manage.py test_timeweb

# классификация статьи (обратная задача)
docker exec --user 1000:1000 -w /app punzh_django \
  python manage.py classify_article --id 12345 --dry-run
```
