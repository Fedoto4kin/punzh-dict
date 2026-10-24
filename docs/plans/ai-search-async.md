# AI-поиск: асинхронный контур (план)

**Статус:** фазы A–C **на prod** (2026-10-23, закрытая альфа): job+PG+poll,
partial HTML, JS на `/ai-search/`. SSE / отдельный worker / WebSocket — позже.  
**Зачем:** синхронный `GET /ai-search/?query=…` → полный HTML упирается в
лимиты воркера и LLM; страница «висит» или обрывается.  
**Ограничение:** если WebSocket — **без сторонних SaaS** (Pusher/Ably/Cloudflare
Realtime и т.п.). Self-hosted Redis не вводим без отдельного решения — сейчас
его нет в стеке.

Связано: `docs/ai-search.md`, `docs/SPEC_ai_query_parse.md`, `app/dict/ai/`,
`app/uwsgi.ini`, уже есть прецедент фона: `dict/ai/classify_bg.py`.

---

## 0. Диагноз (почему рвётся сейчас)

| Слой | Лимит | Роль |
|------|-------|------|
| uWSGI | **`harakiri = 20`** | убивает запрос >20 с |
| LLM | `PARSE_TIMEOUT = 30` | разбор (дешёвые модели медленнее) |
| Nginx | `uwsgi_read_timeout 60s` | шире harakiri — не спасает |
| Prod | 4 process, threads on | WSGI, не ASGI |

Итог: форма + reload **архитектурно** не подходит для LLM на том же HTTP-запросе,
что отдаёт HTML. Retrieval (SQL) быстрый; узкое место — шлюз Timeweb.

Синхронный `/ai-search/` **удалён** — только job+poll; без JS → обычный `/search/`.

---

## 1. Цель продукта

1. Пользователь отправляет запрос → **сразу** видит «разбираем…» (страница не
   белый экран, не reload на 15 с).
2. По готовности — те же группы карточек, что сейчас (12 / 6 field, collapse).
3. Ошибка / timeout LLM → понятное сообщение + ссылка «искать буквально».
4. Без новых внешних сервисов; минимум новых процессов в compose.

Не цель этого плана: чат-бот с историей, стриминг токенов модели, Celery/RQ
как обязательный брокер.

---

## 2. Рекомендуемая архитектура (принятое направление)

### Job + Postgres + poll (или SSE поверх того же job)

```
Browser                         Django (uwsgi)                    PostgreSQL
  |-- POST /ai-search/jobs/ ---> create job (queued) ------------> AiSearchJob
  |<-- { id, status } --------- return 202 / JSON
  |                             spawn worker (thread*)
  |                             parse_query + search_by_parsed
  |                             status=done, result JSON ---------> AiSearchJob
  |-- GET /ai-search/jobs/<id>/ (poll 0.4–0.8 с) ---------------> read
  |<-- { status, parsed, groups… } или error
  |-- отрисовка групп в DOM (без полной перезагрузки)
```

\*Поток как в `classify_bg`: `enable-threads = true` уже есть. Состояние job —
**только в БД**, не в памяти процесса (иначе 4 uwsgi-воркера не увидят чужой
job).

Альтернатива транспорту «готово»: **SSE** `GET …/jobs/<id>/events` с событиями
`queued` → `parsing` → `done|error` (один long-lived HTTP). Poll проще за
nginx/uwsgi; SSE приятнее UX. Оба **без** WebSocket и без сторонних сервисов.

### Почему не Channels/WebSocket в первой очереди

| Вариант | Плюсы | Минусы для нас |
|---------|--------|----------------|
| **Job + poll/SSE** | Остаёмся на uwsgi; PG уже есть; паттерн как classify_bg | Poll чуть грубее; SSE держит воркер на время ожидания |
| Django Channels + Daphne | Настоящий WS | Второй runtime рядом с uwsgi; channel layer → **Redis** или InMemory (ломается на 4 workers) |
| WS «голый» ASGI | Без SaaS | Всё равно ASGI-сервер + sticky/multiplex; смена деплоя |

**Вывод:** фаза 1 — job API + poll (или SSE). WebSocket — **фаза 2 только если**
появится ASGI-контейнер своим ходом и явно понадобится двусторонний канал;
channel layer тогда — **InMemory недопустимо на prod**; Redis — только как
осознанное добавление в compose (свой контейнер, не SaaS), отдельным решением.

---

## 3. Модель данных

`AiSearchJob` (имя уточнить в реализации):

| Поле | Смысл |
|------|--------|
| `id` | UUID (не угадываемый pk) |
| `query` | исходная строка |
| `status` | `queued` \| `running` \| `done` \| `error` \| `expired` |
| `parsed` | JSON (валидированный разбор) или null |
| `groups` | JSON (лёгкий: titles, totals, article ids/words — **не** HTML) |
| `fallback_count` | int \| null |
| `error` | короткий код/текст |
| `created_at` / `finished_at` | TTL / GC |
| `client_key` | опц. анонимный ключ из cookie/session — антиспам |

Гидрация `wordCard` — на **сервере при отдаче HTML-фрагмента** или на клиенте
через уже существующий include: предпочтительно endpoint
`GET …/jobs/<id>/partial/` → HTML групп (Django template), чтобы не дублировать
разметку карточки в JS.

Хранение полного HTML в job — нет (раздув, устаревание).

TTL: удалять/помечать `expired` старше N часов (management command или
`created_at` filter при чтении).

---

## 4. API (черновик контракта)

Все под префиксом `/ai-search/` (тот же контур, не смешивать с `/search/`).

1. **`POST /ai-search/jobs/`**  
   Body: `query` (form или JSON).  
   Ответ: `202 { "id": "<uuid>", "status": "queued" }`.  
   Сразу после create — `schedule_ai_search_job(id)` (daemon thread).

2. **`GET /ai-search/jobs/<uuid>/`**  
   JSON: status + при `done` — `parsed`, `groups` (или флаг `html_ready`).  
   `404` если нет / expired. Не светить чужие job без ключа (см. §6).

3. **`GET /ai-search/jobs/<uuid>/partial/`** (опц.)  
   HTML фрагмент групп для вставки в `#ai-results` (те же шаблоны, что сейчас).

4. **Страница `GET /ai-search/`**  
   Оболочка: форма без full navigation submit (JS `preventDefault` → POST job).  
   Без JS — сообщение + ссылка на `/search/` (sync-legacy нет).

Опционально позже: **`GET …/events`** (SSE), `text/event-stream`, nginx
`proxy_buffering off` / `uwsgi_buffering off` для этого location.

---

## 5. Воркер выполнения

### Фаза 1 (MVP async) — thread per job

Как `classify_bg.schedule_classify_article`:

- `inflight` set по job id (in-process de-dupe).
- Внутри: `status=running` → `parse_query` → `search_by_parsed` → serialize →
  `status=done` (или `error`).
- Таймаут LLM оставить; при timeout — `error`, не harakiri страницы.

Риски: при рестарте uwsgi mid-job — job зависнет в `running` → watchdog
(при чтении: если `running` и `updated_at` старше 60 с → `error`).

### Фаза 1.5 (если нагрузка) — DB claim без брокера

Отдельный `manage.py run_ai_search_worker` в compose (один процесс):

```
SELECT … FOR UPDATE SKIP LOCKED WHERE status='queued'
```

Плюс: переживает рестарт web; минус: ещё один контейнер/процесс. **Не** Celery.

---

## 6. Антиспам и безопасность

- Лимит длины `query` (уже в parse).
- Rate limit: N job / IP / минуту (cache Django LocMem слабо на multi-worker →
  лучше счётчик в PG или nginx `limit_req` на `/ai-search/jobs/`).
- UUID job + опционально привязка к session key; не индексировать выдачу в
  sitemap.
- Модель по-прежнему не пишет в словарь; job — эфемерный кэш ответа.
- Не логировать полный payload в публичные логи; telemetry как сейчас (JSONL).

---

## 7. UX на странице

1. Submit → спиннер / «Как поняли: …» скелетон.
2. Poll до `done` / `error` (макс. ~25–30 с UI-таймаут; дальше «не дождались» +
   буквальный поиск).
3. Вставка partial HTML или JSON→DOM.
4. URL: `?job=<uuid>` или `history.replaceState` с query — чтобы можно было
   поделиться/обновить уже готовый job (пока не expired).
5. Сохранить текущие лимиты карточек (12 lexical, 6 field) и collapse «ещё N».

---

## 8. Деплой / nginx / uwsgi

- Для **poll** менять harakiri не обязательно (короткие запросы).
- Для **SSE**: отдельный `location` с выключенной буферизацией; учесть, что
  воркер занят на время стрима — при росте аудитории предпочтительнее poll или
  выделенный ASGI только под events.
- `deploy.sh` / restart `punzh_web` без нового сервиса в фазе 1.
- Миграция модели job — обычный migrate.

**Не** трогать лексический `/search/` и онтологию в этом PR.

---

## 9. Фазы реализации (чеклист для чата)

### A — контракт и модель
- [x] Модель `AiSearchJob` + миграция + TTL helper (`expire_old_jobs`).
- [x] Сериализация groups (ids + meta) без Article HTML в JSON.
- [x] `schedule_ai_search_job` (thread) + watchdog stale `running`.

### B — API
- [x] `POST/GET` jobs; тесты с моком `parse_query`.
- [x] Partial HTML endpoint (reuse hydrate + шаблон групп).
- [x] Rate limit (PG counter по `client_key` / session).

### C — UI
- [x] JS на `/ai-search/`: submit → poll → render; состояние loading/error.
- [x] `?job=` для готового результата.
- [x] Без JS: noscript → `/search/` (sync убран).

### D — наблюдаемость
- [ ] События telemetry: job_created / job_done / job_error / duration.
- [ ] Метрика «доля timeout» для решения о фазе 1.5 worker.

### E — (опц.) SSE
- [ ] Events endpoint; nginx buffering off; сравнить с poll на beta.

### F — (опц., отдельное решение) WebSocket
- [ ] Только если нужен ASGI-рантайм; **без SaaS**; channel layer = свой Redis
      в compose **или** отказ от multi-worker InMemory.
- [ ] Не смешивать с фазами A–C в одном PR.

---

## 10. Что сознательно не берём

- Celery / RQ / Dramatiq как обязательный стек.
- Внешние realtime-SaaS.
- Стриминг токенов YandexGPT в UI (разбор — один JSON).
- Переписывание всего сайта на ASGI.
- In-memory job store как единственный источник правды.

---

## 11. Критерий готовности

- При искусственной задержке LLM 12–18 с страница **не** получает 502/harakiri;
  пользователь видит прогресс и затем группы.
- 4 uwsgi-процесса: job создан на worker A, poll с worker B отдаёт `done`.
- Тесты `dict` без живого LLM (мок клиента).
- Документы: этот план + короткая пометка в `docs/ai-search.md` и
  `app/dict/ai/README.md` после внедрения.

---

## 12. Промпт для стартового чата реализации

> Реализуй фазы A–C из `docs/plans/ai-search-async.md`: job в Postgres,
> thread-воркер по образцу `classify_bg`, POST/GET API, partial HTML групп,
> JS poll на `/ai-search/` без full-page sync submit. Без Celery, без Redis,
> без WebSocket. Не менять `/search/` и онтологию. После Python — black и
> `manage.py test dict` в Docker по skill django-test.
