---
name: django-test
description: Runs Black/isort and Django tests for punzh-dict inside Docker. Use when changing Python under app/dict or app/punzh, before claiming a fix, or when the user asks to lint or test.
---

# Тесты и формат (Docker)

Рабочий каталог внутри контейнера всегда **`/app`**. Контейнер dev: **`punzh_django`**. Ярлык тестов только **`dict`**.

```bash
docker exec --user 1000:1000 -w /app punzh_django python -m black dict/
docker exec --user 1000:1000 punzh_django python manage.py test dict
```

Уже смонтированный `/app`: можно без `-w /app` у `test`, если cwd контейнера — `/app`. Для `black`/`isort` пути относительно `/app`.

Полный формат (isort + black по `agents/` и `dict/`): `app/README.md` или `make format` из корня репо.

Не запускать `manage.py test` без `dict` — Django подхватит `test_*.py` в `agents/` и management commands.

Оффлайн-скрипты: `docker exec --user 1000:1000 -w /app/agents punzh_django python <tool>.py` — это не юнит-тесты.
