---
name: django-test
description: >-
  Runs Black/isort and Django tests for punzh-dict inside Docker. Use when
  changing Python under app/dict or app/punzh, before claiming a fix, before
  commit/push/deploy to prod, or when the user asks to lint or test.
---

# Тесты и формат (Docker)

Рабочий каталог внутри контейнера всегда **`/app`**. Контейнер dev: **`punzh_django`**. Ярлык тестов только **`dict`**.

```bash
docker exec --user 1000:1000 -w /app punzh_django python -m black dict/
docker exec --user 1000:1000 -w /app punzh_django python manage.py test dict
```

Уже смонтированный `/app`: можно без `-w /app` у `test`, если cwd контейнера — `/app`. Для `black`/`isort` пути относительно `/app`.

Полный формат (isort + black по `agents/` и `dict/`): `app/README.md` или `make format` из корня репо.

Не запускать `manage.py test` без `dict` — Django подхватит `test_*.py` в `agents/` и management commands.

Оффлайн-скрипты: `docker exec --user 1000:1000 -w /app/agents punzh_django python <tool>.py` — это не юнит-тесты.

## Перед push / деплоем

Когда пользователь просит **коммит и деплой**, **пуш** или **деплой** на prod
(`krl@karielan-hub`, `~/punzh-dict`, `./deploy.sh`):

1. Прогнать `python manage.py test dict` в **`punzh_django`** (локально).
2. Если менялся Python — ещё black по затронутым путям.
3. Только при зелёных тестах: commit (если просили) → `git push` → remote
   `./deploy.sh`.
4. При красных тестах — **не** пушить и **не** деплоить; сначала починить.

Прогон тестов на `punzh_web` / после pull на сервере этот шаг не заменяет.
