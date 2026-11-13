# Offline mobile pack — контракт данных

Канон для **генерации и раздачи** пакета словаря (`dict.sqlite` + `manifest.json`).
Клиентское поведение поиска/UI — не здесь: см. sibling
[`punzh-dict-mobile/docs/DICTIONARY.md`](../../punzh-dict-mobile/docs/DICTIONARY.md).

**Источник правды DDL/версий:** [`app/dict/mobile/schema.py`](../../app/dict/mobile/schema.py).  
**Экспорт:** [`app/dict/mobile/export.py`](../../app/dict/mobile/export.py), `manage.py export_mobile_db`.  
**Publish:** [`scripts/publish_mobile_pack.sh`](../../scripts/publish_mobile_pack.sh).  
Тесты: `dict.tests.test_export_mobile_db`.

Flutter-клиент: **`../punzh-dict-mobile`**. Здесь — контракт, экспортёр и (позже)
одна актуальная APK на сайте для прямого скачивания.

## Пакет

```
manifest.json
dict.sqlite
```

Прод URL (host nginx → `~/punzh-dict/mobile-pack/`):

`https://punzhina.krc.karelia.ru/mobile-pack/manifest.json`

Клиент качает `url` из манифеста относительно base (`…/mobile-pack/`).

## Версии и совместимость

| Поле | Где | Смысл |
|------|-----|--------|
| `schema_version` | `schema.py`, `meta`, manifest | Ломающая схема sqlite. Сейчас **2**. |
| `min_app` | `schema.py`, `meta`, manifest | Минимальный `versionName` клиента (`X.Y.Z`). Сейчас `"0.1.0"`. |
| `data_version` | `meta`, manifest | Снимок данных: первые 12 hex sha256 файла **до** записи `data_version` в meta, затем финальный sha256 файла для манифеста. |
| `built_at` | `meta`, manifest | UTC ISO-8601 время сборки пакета. |

Клиент **обязан** отвергнуть пакет с неподдерживаемым `schema_version` и не
применять обновление при `min_app` выше установленного приложения.
Бамп приложения ≠ бамп схемы; смена схемы ≠ замена `versionCode` магазина.

## `manifest.json`

Пример полей (актуальные значения пишет экспортёр):

```json
{
  "schema_version": 2,
  "data_version": "…",
  "built_at": "…",
  "sha256": "…",
  "size": 0,
  "min_app": "0.1.0",
  "file": "dict.sqlite",
  "url": "dict.sqlite"
}
```

- `sha256` / `size` — от финального `dict.sqlite` (после записи `data_version` в meta).
- `url` — путь относительно base URL каталога пакета.

## Таблицы sqlite

Стабильные `articles.id` / `tags.id` = id в Django/Postgres (удобно для ссылок и диффов).

| Таблица | Назначение |
|--------|------------|
| `meta` | key/value: `schema_version`, `data_version`, `built_at`, `min_app` |
| `articles` | `word`, `word_normalized`, `first_letter`, `sort_key`, `article_html`, source fields, `linked_article_id` |
| `additions` | дополнительные блоки HTML статьи |
| `links` | исходящие связи `from_article_id` → `to_article_id`, `kind` (см./от и др. как в Postgres `ArticleLink`) |
| `words` | индексные формы для KRL-поиска (`ArticleIndexWord`) |
| `translations` | `rus_word` для RU-поиска (`ArticleIndexTranslate`; **без** `rus_lemmas`) |
| `tags` | `tag`, `name`, `type`, `sorting`, `level` |
| `article_tags` | M2M статья↔тег |

Индексы (из DDL): `(first_letter, sort_key)`, `words.word`, `translations.rus_word`,
`article_tags(tag_id, article_id)`, `additions(article_id)`, `links` from/to.

`sort_key` — карельский ключ сортировки (`krl_sort_key` при экспорте).

## Намеренно отсутствует

Не экспортировать и не допускать в пакете (см. `FORBIDDEN_TABLE_SUBSTRINGS`):

- semantic / ontology / keywords
- `rus_lemmas`
- FTS / `search_vector`

Live REST к Postgres с устройства — вне контракта.

## Команды

```bash
# экспорт в контейнере Django
docker exec -w /app punzh_django \
  python manage.py export_mobile_db --out /tmp/mobile-pack

# тесты контракта
docker exec -w /app punzh_django \
  python manage.py test dict.tests.test_export_mobile_db

# publish (detect punzh_web / punzh_django)
scripts/publish_mobile_pack.sh /tmp/mobile-pack
# prod: scripts/publish_mobile_pack.sh ~/punzh-dict/mobile-pack
```

Weekly cron на karielan-hub — в шапке `publish_mobile_pack.sh`.

## Ломающие изменения

1. Менять DDL / смысл колонок → поднять `SCHEMA_VERSION` в `schema.py`.
2. Обновить проверку в клиенте (`punzh-dict-mobile/lib/schema.dart`) под новую схему.
3. При необходимости поднять `MIN_APP`.
4. Прогнать `test_export_mobile_db`, опубликовать пакет, проверить что старый клиент
   отказывается ставить пакет (не портит runtime DB).
