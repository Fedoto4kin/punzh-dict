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

## Prod

`./deploy.sh` **не** пересобирает образ. На сервере: `docker compose build` + recreate контейнера, затем `./deploy.sh`. Откат = предыдущий image tag.

## Вне скоупа (не трогали)

AI-поиск, фильтры помет, `ArticleLink`, схема `Article`/индексов, UI Bootstrap 4.
