## Technical requirements

@todo

### Helpful commands

#### Dump fixtures 

```bash
docker compose -f docker-compose.internal.yml exec -w /app django \
  python manage.py dumpdata dict --indent 2 \
  --exclude dict.ArticleIndexWord \
  --exclude dict.ArticleIndexWordNormalization \
  -o /app/dict/fixtures/dict_seed.json
```

`dict_seed.json` is stored in **Git LFS**. The machine that commits the dump needs `git-lfs` (`apt install git-lfs && git lfs install`). Then:

```bash
git add --renormalize app/dict/fixtures/dict_seed.json
# git cat-file -s :app/dict/fixtures/dict_seed.json  → ~130 bytes, not ~28M
```

#### Load fixtures 

Одна команда: очистка `dict_*`, `loaddata`, пересборка индексов слов и `search_vector` переводов.

```bash
docker exec --user 1000:1000 -w /app punzh_django \
  python manage.py load_dict_seed --yes
```

На продакшене (`DEBUG=False`) команда выводит предупреждение и требует ввести `yes`
вручную; для скриптов — `--yes --allow-production` (только с бэкапом БД).

----


```bash
docker exec --user 1000:1000 punzh_django python manage.py makemigrations
```

```bash
docker exec --user 1000:1000  -it punzh_django python manage.py migrate
```


### Tests

Ярлык `dict` обязателен: иначе Django подхватит оффлайн-скрипты (`agents/`, management commands) с именем `test_*.py`.

```bash
docker exec --user 1000:1000 punzh_django python manage.py test dict
```

### LLM: `agents/` и `dict/ai/`

| | `app/agents/` | `app/dict/ai/` |
|---|----------------|----------------|
| Назначение | Пакетная подготовка данных (json) | Рантайм и команды «на лету» |
| Примеры | `clean_translations.py`, `translation_cleanup.py` | `classify.py`, `client.py` |
| DeepSeek | `agents/.env`, `-w /app/agents` | Timeweb через `client.py` |

Подробнее: `agents/AGENTS.md`, `dict/ai/README.md`.

### Lint code

```bash
docker exec --user 1000:1000 -w /app punzh_django python -m isort \
  agents/translation_cleanup.py agents/clean_translations.py dict/

docker exec --user 1000:1000 -w /app punzh_django python -m black \
  agents/ dict/
```

Или `make format` из корня репо (форматирует весь `/app` в контейнере).

Очистка переводов (§2): **`docs/translation_cleanup.md`**.

### Доклассификация одной статьи (`classify_article`)

Рантайм: разметить **одну** статью по онтологии из БД (основной текст +
аддендумы). Два LLM-вызова: поля/keywords по всей статье, затем флаг
`from_translation` на полях, подтверждённых переводами. Тот же промпт, что у
пакетной разметки; модель DeepSeek через шлюз Timeweb
(`TIMEWEB_AI_API_KEY`, `TIMEWEB_AI_MODEL_CLASSIFY`). Подробности:
`docs/method-onthlogy-markup.md` §5.

Имя контейнера: `punzh_django` (dev) или `punzh_web` (internal compose) —
подставьте своё. Канал: `manage.py test_timeweb`.

```bash
# дым (без записи)
docker exec --user 1000:1000 -w /app punzh_django \
  python manage.py classify_article --id 12345 --dry-run

# запись
docker exec --user 1000:1000 -w /app punzh_django \
  python manage.py classify_article --id 12345
```

### Поля из перевода (`from_translation`)

Оффлайн: пометить уже проставленные смысловые поля — из переводов леммы
или нет. **Не** переклассификация. Боевой прогон — после очистки переводов
(`backlog.md` §2, затем §4). Подробности: `agents/AGENTS.md`.

Нужны: доступ к БД в контейнере, `openai` (`pip install openai` разово),
ключ в `agents/.env` (`DEEPSEEK_API_KEY=...` без кавычек), миграция `0025`.

```bash
# дым (100 статей) → agents/data/translation_fields.json
docker exec --user 1000:1000 -w /app/agents punzh_django \
  python pick_translation_fields.py --limit 100 --order id --out translation_fields.json

# полный словарь (автодокат при обрыве)
docker exec --user 1000:1000 -w /app/agents punzh_django \
  python pick_translation_fields.py --order id --out translation_fields.json

# заливка флага (связи не создаёт и не удаляет)
docker exec --user 1000:1000 -w /app punzh_django \
  python manage.py load_translation_fields \
  --file /app/agents/data/translation_fields.json
```

JSON в `agents/data/` — не коммитить. `/ontology/` по флагу не фильтрует.
