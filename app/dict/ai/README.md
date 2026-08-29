# `dict/ai/` — рантайм LLM

Код, который участвует в **живых** сценариях сайта или management-командах
«на лету»: классификация статьи, будущий AI-поиск, шлюз к Timeweb.

**Не сюда:** разовая/пакетная подготовка данных на 16k статей — это
`app/agents/` (см. `agents/AGENTS.md`).

## Модули

| Модуль | Назначение |
|--------|------------|
| `client.py` | HTTP-клиент к шлюзу Timeweb (`chat_json`, настройки из env). |
| `prompts.py` | Замёрзший промпт и сбор входа для **классификации** по онтологии (включая аддендумы). Импортируется и рантаймом (`classify_article`), и пакетным `agents/build_ontology.py`. Промпт «по переводу» (`SYSTEM_PROMPT_TRANSLATION_FIELDS`) — общий с `pick_translation_fields.py`; вход — только `ArticleIndexTranslate`. |
| `classify.py` | Ядро классификации одной статьи: поля + keywords + `from_translation` (два LLM-вызова). |

## Исключение: общий промпт в `prompts.py`

`dict.ai.prompts` лежит здесь не потому, что это «оффлайн», а потому что **один
и тот же** замороженный текст нужен и пакетной разметке (`agents/build_ontology.py`),
и рантайму (`manage.py classify_article`). Если промпт используется **только**
оффлайн-скриптом — он живёт целиком в `agents/` (напр. `clean_translations.py`).
Промпт «по переводу» и сбор входа — в `dict.ai.prompts` (рантайм + `pick_translation_fields`).

## См. также

- `app/agents/AGENTS.md` — оффлайн-инструменты, DeepSeek, dry-run json.
- `docs/method-onthlogy-markup.md` — онтология и разметка.
- `cursor_project_overview.md` — обзор проекта.
