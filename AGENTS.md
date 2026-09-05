# Punzh-dict — вход для агента

Веб-словарь карельского языка (тверские говоры) Пунжиной А. В.: статьи, поиск, админка. ~16k статей.

**Людям:** корневой `README.md`. **Архитектура подробно:** `cursor_project_overview.md`. **Очередь задач:** `docs/plans/INDEX.md`. **Оглавление docs:** `docs/README.md`.

## Контуры (не смешивать без явной задачи)

| Контур | Где | Роль |
|--------|-----|------|
| Лексический поиск `/search/` | `app/dict/search.py`, views | ILIKE, token-OR, Левенштейн, `?f=` |
| Staff: переводы / отладка | админка Dict | индекс `rus_word`; explain `rus_search_core` |
| Онтология `/ontology/` | semantic-модели, views | поля/keywords; **не** фильтровать по `from_translation` |
| Рантайм-AI | `app/dict/ai/` | шлюз Timeweb; AI-поиск в URL ещё нет |
| Оффлайн LLM | `app/agents/` | пакет → JSON; в БД — management-команды (исключение: `clean_translations --write`) |

Подробнее: `app/agents/AGENTS.md`, `app/dict/ai/README.md`.

## Стек и запуск

Python 3.8, Django 3.1.7, PostgreSQL, шаблоны + Bootstrap 4. Dev: контейнеры `punzh_django` + `punzh_db`. `manage.py` и тесты: **`-w /app`**. Команды: `app/README.md`. Деплой: `./deploy.sh`. Статика: исходники `app/static` / `app/dict/static`, отдача Nginx — только `app/staticfiles`.

## Инварианты

- Не ломать структуру `Article`, индексов и семантических моделей.
- `from_translation` — не «одно главное поле»; `/ontology/` по нему не фильтровать, пока это не отдельная задача.
- Agents готовят JSON; запись в БД — management-команды, админка, `import.py`.
- Явный читаемый Python. Чат — русский; комментарии в коде — английские.
- В коммитах не указывать агента / Cursor / модель; без `Co-authored-by`. Автор — git config человека.
- После правок Python: black и тесты **только** `dict` (см. `.cursor/skills/django-test` и `app/README.md`). Скрипты в `agents/` не называть `test_*.py`.
