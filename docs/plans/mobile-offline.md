# План: офлайн-приложение словаря (mobile)

Статус: **MVP готов** (указатель, поиск, карточка, seed, `sort_key`).  
Дальше — развитие на ветке `cursor/mobile-offline-mvp-wip` (не в master, не отдельный repo).  
Контур отдельный от лексического `/search/`, AI и ontology. Не смешивать с пунктами A/1–8 в одном PR.

## Локальное тестирование

Два независимых контура. Flutter SDK на машине пока может отсутствовать —
экспортёр и контракт проверяются без него.

### A. Пакет данных (Django, всегда первым)

| Что | Как |
|-----|-----|
| Юнит-тесты | `docker exec … punzh_django python manage.py test dict.tests.test_export_mobile_db` — маленькая фикстура в TestCase → sqlite во временный каталог → проверка таблиц, счётчиков, substring-полей, отсутствия семантики |
| Ручной снимок с dev-БД | Поднять `punzh_django` + `punzh_db`, затем `manage.py export_mobile_db --out /tmp/mobile-pack` → `sqlite3 dict.sqlite '.tables'` / выборки |
| Регрессия формата | В тесте читать `manifest.json`: `schema_version`, `sha256` совпадает с файлом |

Формат/линт Python — как обычно (`django-test` skill): black + `test dict`.

Артефакты полного снимка (~десятки МБ) **не коммитить**; в git — только код экспортёра и при необходимости крошечный fixture-sqlite для Flutter-тестов.

### B. Приложение (Flutter)

| Что | Как |
|-----|-----|
| Юнит Dart | `flutter test` против **мини-seed** (тот же файл, что собрал экспортёр из TestCase, или закоммиченный `mobile/test/fixtures/mini.sqlite`) |
| UI без устройства | `flutter test` + golden/widget на указатель/поиск |
| На устройстве/эмуляторе | `export_mobile_db` с dev-БД → скопировать в `mobile/assets/dict.sqlite` → `flutter run` (Android emulator / USB). Сеть не нужна для MVP seed |
| Обновление БД | Позже: локальный static (python -m http.server) с манифестом + пакетом; в приложении указать debug URL |

Bootstrap на этой машине: Flutter `~/sdk/flutter`, Android SDK `~/Android/Sdk`,
AVD `punzh_api36` (без KVM эмулятор медленный — см. `mobile/README.md`).

### C. Согласованность контракта

Один `schema_version` в Python (`dict/mobile/schema.py`) и в Dart-константе.
При bump — падают тесты экспортёра и/или Flutter, если клиент отстаёт.

## Цель MVP

Пользоваться словарём Пунжиной **без сети**: алфавитный указатель, фильтры по
пометам, простой поиск KRL/RU, карточка статьи. Семантика, AI-поиск и «умный»
русский поиск сайта — **не нужны**.

## Решения (зафиксировано)

| Вопрос | Решение |
|--------|---------|
| Репозиторий | **Клиент:** `~/Projects/KRL/punzh-dict-mobile`. **Данные/сайт:** этот monorepo (`export_mobile_db`, `/mobile-pack/`) |
| First-run | **БД в APK/assets** (seed). Сеть не обязательна для старта |
| Поиск RU | Ранний веб: **начальное** вхождение `foo%` в `rus_word` (ё→е). Без лемм, стопов, multi-word OR, expand «см.» |
| Поиск KRL | Как веб: `prepare_krl_ilike_query` + LIKE по `words` (без авто-`%`); пустая выдача → Levenshtein ≤ 2 («Возможно вы искали») |
| Платформа | **Flutter** с первого шага (Android сейчас, iOS заложен стеком). Не Kotlin-only |
| Обновление БД | Опционально после first-run: скачать новый пакет по манифесту и атомарно заменить локальный файл. Seed в билде остаётся fallback |

## Граница с сайтом

**Источник правды** — Django/Postgres (`Article`, индексы, `Tag`, связи).

Сайт **не** обслуживает live-запросы мобилки к Postgres. Связь — **пакет данных**:

```
manifest.json     # schema_version, data_version, built_at, sha256, size, min_app
dict.sqlite[.zst] # снимок для Room/sqflite
```

Сборка пакета: `export_mobile_db`. Раздача: `/mobile-pack/` на prod.
**Канон контракта:** [`mobile-pack-contract.md`](mobile-pack-contract.md).
Семантика клиента: [`punzh-dict-mobile/docs/DICTIONARY.md`](../../punzh-dict-mobile/docs/DICTIONARY.md).

Семантические таблицы (`SemanticField`, `ArticleSemanticField`, `ArticleKeyword`),
`rus_lemmas`, FTS/`search_vector` — **не экспортировать**.

## Схема sqlite (черновик)

Денормализация под UI, не 1:1 с Postgres. Стабильные `id` статей = id с сайта
(удобно для ссылок и диффов обновлений).

| Таблица | Назначение |
|--------|------------|
| `meta` | `schema_version`, `data_version`, `built_at` |
| `articles` | word, word_normalized, first_letter, sort_key, html, source… |
| `additions` | html дополнений |
| `links` | see / cf / deriv → target article id / слово |
| `words` | варианты для KRL-поиска |
| `translations` | `rus_word` для substring-поиска |
| `tags` | id, tag, name, type, sorting, level |
| `article_tags` | M2M |

Индексы: `(first_letter, sort_key)`, `words.word`, `translations.rus_word`,
`article_tags(tag_id, article_id)`.

`schema_version` ломается только при несовместимой схеме; старое приложение
отказывается ставить пакет новее, чем умеет.

## UX MVP

1. **Указатель** — буквы KRL_ABC → список лемм (`first_letter`), пагинация/виртуализация.
2. **Фильтры** — пометы type 1–5 (как на сайте: POS, стиль, говор, НП, фразеол.); AND между типами; детали UX можно взять с KRL `?t=` / `?ph=` как ориентир, не копировать URL.
3. **Поиск** — KRL/RU: KRL по `words` как на вебе (полное LIKE + `.`/`?`); RU — префикс `foo%` по `translations.rus_word`; фильтры помет — к KRL-выдаче.
4. **Карточка** — HTML статьи (+ дополнения), переходы по внутренним ссылкам см./от при наличии id.
5. **Обновить словарь** — экран/пункт: проверка манифеста → download → проверка sha256 → замена файла БД. Без сети кнопка просто недоступна / ошибка; работа с seed продолжается.

## Стек клиента (`punzh-dict-mobile`)

- Flutter (Dart), Android primary target.
- Локальная БД: `sqflite` / drift над файлом пакета (или копирование seed из assets в documents при первом запуске).
- HTTP только для манифеста + скачивания пакета (опционально).
- Рендер HTML: WebView или эквивалент; стили — минимальный CSS под словарную вёрстку сайта.

Flutter-проект: `~/Projects/KRL/punzh-dict-mobile`. Фикстура экспортёра — в тестах Django; mini.sqlite — в app-repo `test/fixtures/`.

## Шаги

1. **Контракт** — `schema_version=1` в `app/dict/mobile/schema.py` + `mobile/README.md`. ✓
2. **Экспортёр** — `manage.py export_mobile_db` → sqlite + manifest; тесты `test_export_mobile_db`. ✓ (compress — позже при упаковке в assets)
3. **Skeleton Flutter** — `mobile/`: seed из assets, указатель, карточка, простой поиск KRL/RU. ✓ (`flutter test` / `analyze` зелёные)
4. **Фильтры** по `tags` / `article_tags`.
5. **Поиск** KRL + RU substring; сочетание с фильтрами.
6. **Update path** — манифест, download, атомарная замена, `min_app` / `schema_version` checks.
7. **Сборка APK** с актуальным seed; документ, как обновлять seed в CI/релизе.
8. *(после P2)* вынос `mobile/` в отдельный repo; в punzh — свежая APK + ссылки
   с главной (см. бэклог). iOS — в репо приложения.

## Бэклог развития (ближайшее)

Приоритеты зафиксированы (P0 → P8). Клиент вынесен в `punzh-dict-mobile`. **Следующее:** **P8** (магазины / APK на сайте). P7: ручной регресс ✓ + точечный KISS/DRY hygiene ✓; крупный split Home — в «не боли» ниже.
Инкременты / наблюдатель моделей — не в P2; полный пакет раз в неделю (`scripts/publish_mobile_pack.sh` + cron на prod).

| Pri | Что | Заметка |
|-----|-----|---------|
| **P0** | ~~**Стек переходов по см./от**~~ | Сделано: `_articleStack` — push по см./от, system back = pop, X/drag = закрыть лист |
| **P1** | ~~**Меню-оболочка**~~ | Сделано: Drawer — «Как искать» / «О словаре» / «О приложении» (in-pane), обновление БД, логотип + КарНЦ РАН (без ссылки) |
| **P2** | ~~**Update path** (полный пакет)~~ | Сделано и на prod: `…/mobile-pack/` + `DbUpdater` + UI в меню; seed = fallback; weekly cron. Далее — вынос приложения (см. ниже) |
| **P3** | ~~**Поиск: навигация по выдаче**~~ | Сделано: при большой выдаче — тот же n-gram scrubber / окна страниц, что у буквенного указателя |
| **P4** | ~~**Закладки**~~ | Сделано: `bookmarks.json` вне пакета; звезда на карточке; список в drawer (свайп удаляет); переживают update БД; лимит 100 |
| **P5** | ~~**Фильтры по пометам**~~ | Сделано: после KRL-поиска; фасеты из выдачи; radio/AND/ph; неприменимые чипы disabled; не для алфавитного указателя |
| **P6** | ~~**Fuzzy KRL**~~ | Сделано: при пустой KRL-выдаче — «Возможно вы искали» (Levenshtein ≤ 2 по `words`, без триграмм); чипы перезапускают поиск |
| **P7** | ~~**Рефакторинг + полный регресс**~~ | Ручной чеклист ✓ ([`MANUAL-REGRESSION.md`](../../punzh-dict-mobile/docs/MANUAL-REGRESSION.md)); hygiene ✓ (мёртвый `ArticleScreen`, shared fold/tags, mini-repo helper, MenuDrawer←session). Крупный split Home — см. «не боли» |
| **P8** | **Релизный контур** | Seed/CI/release-APK; раздача — сайт + магазины. Клиент уже в `punzh-dict-mobile`. В punzh — контракт/экспорт ([`mobile-pack-contract.md`](mobile-pack-contract.md)) + одна APK на сайте. Версии — app-repo `AGENTS.md` |

### P7+ — отложено («не боли», не блокирует P8)

Из ревью KISS/DRY/SOLID (ноя 2026). Делать **по касанию фичи**, не hygiene ради SOLID.

| Когда | Что | Не делать «просто так» |
|-------|-----|-------------------------|
| Следующая крупная UX-правка Home | Вынести letter window / n-gram rail из `_HomeScreenState` в обычный контроллер (без BLoC/Riverpod) | Полный rewrite Home «для красоты» |
| Новая ось поиска / фильтров (напр. RU+tags) | Тогда же — узкий split search-методов repo или общий `run(query, filters)`; **не** Strategy/SearchBackend заранее | Паттерн Strategy для KRL/RU «на вырост» |
| Второй backend или тяжёлый widget-тест Home | Abstract `IDictionaryRepository` / DI | Интерфейсы над одним sqlite |
| Рост SQL/поиска в одном файле + реальная новая ось | Sibling-классы / private helpers вокруг `DictionaryRepository` | Преждевременная нарезка «толстого» repo |
| Касание drawer/update UI | Вынести `_UpdateDbPane` в отдельный файл | — |
| Второй UI-потребитель preview | `formatPreview` рядом с `article_format` | Перенос `previewLine` без нужды |

**Сознательно раздельно:** `orthography` ≠ `prepareKrlIlikeQuery` (разные порты Django); sheet ≠ route для статьи.

### P1 — меню приложения ✓

| Пункт | Содержание |
|-------|------------|
| **Как искать** | Краткая офлайн-справка (KRL exact + `.`/`?`; RU префикс); без hint у поля |
| **О словаре** | Кратко о словаре Пунжиной; ссылка на сайт проекта |
| **О приложении** | Версия (`package_info`) + короткий текст офлайн-клиента |
| **Обновление БД** | Проверка манифеста / загрузка пакета (P2) |
| **Бренд** | Логотип; подпись **КарНЦ РАН** без гиперссылки |

### Сайт и отдельный repo

| Репозиторий | Знание / код |
|-------------|--------------|
| **punzh-dict** (этот) | Контракт ([`mobile-pack-contract.md`](mobile-pack-contract.md)), `export_mobile_db`, publish `/mobile-pack/`; stub [`mobile/README.md`](../../mobile/README.md); позже — одна APK на сайте |
| **punzh-dict-mobile** | Flutter, APK-история, [`DICTIONARY.md`](../../punzh-dict-mobile/docs/DICTIONARY.md) |

DDL в app-repo не дублировать как канон — ссылаться на контракт monorepo / `schema_version`.

### Сделано (не трогать)

- ~~Карельская сортировка~~ — `schema_version=2`, `articles.sort_key`,
  `ORDER BY sort_key, id`.

## Не делать (MVP)

- Ontology / semantic fields / keywords / AI-search.
- Леммы RU, pymorphy, стопы, `?f=`, expand по `ArticleLink` в поиске (ссылки на карточке — да).
- Live REST к Postgres; авторизация; админка в приложении.
- Держать Flutter-исходники снова внутри monorepo (клиент — `punzh-dict-mobile`).
- Сложный fuzzy KRL с триграммами сайта. Простой Levenshtein ≤ 2 — **P6** ✓.

## Риски

| Риск | Митигация |
|------|-----------|
| Размер APK из-за seed | gzip/zstd в assets + unpack при first launch; следить за лимитами Play |
| Расхождение HTML/CSS с сайтом | минимальный общий CSS; не тащить Bootstrap целиком |
| Ломающий schema bump | `schema_version` + `min_app`; старый клиент не применяет пакет |
| Дублирование логики поиска с сайтом | сознательно: мобилка проще; не шарить Python-поиск |

## Связь с очередью

Отдельный пункт в `docs/plans/INDEX.md`. Не блокирует AI/админку; экспортёр
трогает только read-path моделей статей/тегов/индексов.
