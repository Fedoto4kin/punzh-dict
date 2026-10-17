# Обновление стека (Python / Django)

**Статус:** сделано в коде (ветка `stack-upgrade`); prod — после пересборки образа  
**Было P0:** Python 3.8 + Django 3.1.7 (EOL) → Python 3.12 + Django 5.2 LTS.

## Итог

| Компонент | Было | Стало |
|-----------|------|-------|
| Python (образ) | 3.8 | 3.12-bookworm (`images/django/Dockerfile`) |
| Django | 3.1.7 | 5.2.7 |
| Драйвер БД | psycopg2 2.8.6 | `psycopg[binary]` 3.2.x |
| uWSGI | 2.0.19.1 | 2.0.28 |
| django-bootstrap4 | 2.3.1 | 25.1 |
| django-viewflow | 2.0.0a0 | удалён (не использовался) |
| PostgreSQL | 14 | без изменений |

Сопутствующие правки:

- `settings.py`: `DEFAULT_AUTO_FIELD=AutoField`, `CSRF_TRUSTED_ORIGINS`, без `USE_L10N`
- шаблоны: `{% ifequal %}` → `{% if … == … %}` (Django 4+)
- raw-string в regex helpers (SyntaxWarning на 3.12)

Тесты: `manage.py test dict` — OK (421).

## Деплой (internal compose)

На сервере используется **`docker-compose.internal.yml`**, не `docker-compose.yml` / `docker-compose-prod.yml`.

| | |
|--|--|
| Compose | `docker-compose.internal.yml` |
| Сервис Django | `django` → контейнер **`punzh_web`** (uWSGI) |
| БД | контейнер **`punzh_db`** (`ankane/pgvector`), volume `./db` — **не трогать** |
| Код | volume `./app:/app` — после `git pull` код на диске сразу виден |
| Пакеты Python/Django | **только в образе** — без `build` + recreate `punzh_web` стек не обновится |
| `./deploy.sh` | `git pull` + `migrate` + `collectstatic`; образ **не** собирает |

### Чеклист

#### 0. До начала

- [ ] Ветка/коммиты апгрейда уже в remote (`stack-upgrade` смержен в то, что тянет сервер, или деплой с этой ветки осознанно).
- [ ] Окно короткого даунтайма (recreate `punzh_web` ~1–2 мин; БД не рестартим без нужды).
- [ ] Есть SSH на хост, cwd = корень репо (где `docker-compose.internal.yml`, `.env`).
- [ ] Зафиксировать текущие версии на всякий случай:
  ```bash
  docker exec -w /app punzh_web python -c 'import sys,django; print(sys.version.split()[0], django.get_version())'
  docker images --format '{{.ID}} {{.Repository}}:{{.Tag}} {{.CreatedSince}}' | head -20
  ```
- [ ] (Рекомендуется) тег отката текущего образа Django, пока контейнер ещё на старом:
  ```bash
  IMG=$(docker inspect -f '{{.Image}}' punzh_web)
  docker tag "$IMG" punzh-web:pre-stack-upgrade
  ```

#### 1. Код на сервере

- [ ] `git fetch` и `git status` — чистое дерево или понятные локальные правки.
- [ ] Перейти на нужный ref (`git checkout …` / merge) **или** оставить pull на `./deploy.sh` (шаг 3).
- [ ] Убедиться, что на диске уже новые `images/django/Dockerfile` и `app/requirements.txt` (иначе build соберёт старое).

#### 2. Пересборка только Django (БД не трогать)

```bash
docker compose -f docker-compose.internal.yml build django
docker compose -f docker-compose.internal.yml up -d --force-recreate --no-deps django
```

- [ ] `build django` завершился без ошибки pip/uWSGI.
- [ ] `punzh_web` в `Up`, `punzh_db` не пересоздавался:
  ```bash
  docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}' | grep punzh
  ```
- [ ] В новом контейнере:
  ```bash
  docker exec -w /app punzh_web python -c 'import sys,django,psycopg; print(sys.version.split()[0], django.get_version(), psycopg.__version__)'
  ```
  Ожидание: **Python 3.12.x**, **Django 5.2.x**, psycopg 3.x.
- [ ] `docker exec -w /app punzh_web python manage.py check` — без ошибок.
- [ ] Логи uWSGI без traceback на старте: `docker logs --tail 80 punzh_web`

#### 3. Migrate + collectstatic

`./deploy.sh` сам сделает `git pull --ff-only` (если не `--no-pull`), найдёт `punzh_web`, затем migrate/collectstatic.

```bash
# если код уже на нужном commit:
./deploy.sh --no-pull

# или с pull + перезагрузкой nginx (если статика через host nginx):
./deploy.sh --reload-nginx
```

- [ ] migrate без ошибок (для этого апгрейда новых миграций схемы обычно нет).
- [ ] collectstatic отработал; в `app/staticfiles/` есть свежие файлы (в т.ч. admin).
- [ ] Если nginx на хосте отдаёт `staticfiles` — после `--reload-nginx` или ручного reload проверить URL статики (см. ниже).

#### 4. Smoke на проде

- [ ] Главная / список по букве, пагинация `/…/2` (бывший `ifequal`).
- [ ] `/search/` — русский и карельский запрос.
- [ ] `/ontology/` — поле, страница 2, статья.
- [ ] `/tags/…` — пагинация.
- [ ] Админка: логин, открытие статьи, сохранение (CSRF / HTTPS: `CSRF_TRUSTED_ORIGINS` для `punzhina.krc.karelia.ru`).
- [ ] Staff: Переводы + Отладка поиска, если пользуетесь.
- [ ] Статика 200: например `/static/admin/js/article_html_editor.js` (или ваш канонический путь после nginx → `staticfiles`).
- [ ] Иконки Font Awesome / Bootstrap не «голые».

#### 5. Откат (если дым красный)

БД (`./db`) не откатываем — схема не менялась. Откатываем **код + образ `punzh_web`**.

1. Вернуть код: `git checkout <commit-до-апгрейда>` (или revert merge).
2. Узнать имя образа сервиса:
   ```bash
   docker compose -f docker-compose.internal.yml images django
   ```
3. Навесить сохранённый тег на это имя (подставьте Repository:Tag из вывода):
   ```bash
   docker tag punzh-web:pre-stack-upgrade <repository>:<tag>
   ```
4. Пересоздать только Django:
   ```bash
   docker compose -f docker-compose.internal.yml up -d --force-recreate --no-deps django
   ```
5. `./deploy.sh --no-pull` при необходимости (collectstatic под старый код).
6. Проверить версии: снова Python 3.8 / Django 3.1.x.

### Чего не делать

- Не `docker compose … down -v` и не трогать volume `./db`.
- Не `build`/`recreate` сервиса `db` «заодно».
- Не рассчитывать, что одного `./deploy.sh` достаточно для смены Python/Django.
- Не `collectstatic --clear` в пике (краткий провал `/static/`).

## Вне скоупа (не трогали)

AI-поиск, фильтры помет, `ArticleLink`, схема `Article`/индексов, UI Bootstrap 4.
